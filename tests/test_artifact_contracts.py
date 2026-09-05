import tempfile
import unittest
import threading
from collections.abc import Mapping, Iterator
from unittest import mock
from pathlib import Path

from dosweb.artifacts.identifiers import (
    file_sha256,
    sha256_canonical_json,
    stable_identifier,
)
from dosweb.artifacts.jsonl import (
    artifact_ref_for_metadata,
    read_jsonl_strict,
    write_jsonl_atomically,
)
from dosweb.artifacts.metadata import StageFingerprint, invalidate_from, reusable_stage
from dosweb.artifacts.schemas import ARTIFACT_SCHEMAS, SCHEMA_VERSION, validate_records, validate_references
from dosweb.errors import AnalyzerError
from dosweb.growth.completeness import (
    CandidateDisposition,
    CandidateEntryLink,
    CandidateNegativeProof,
)
from dosweb.growth.slices import DemandInput, GrowthCandidate, SourceLocation
from dosweb.lifecycle import BoundCandidate, GuardCandidate, ReleaseCandidate


class ArtifactContractTests(unittest.TestCase):
    def _growth_contract(self, **changes: object) -> dict[str, object]:
        record: dict[str, object] = {
            "growth_contract_id": "contract:1",
            "growth_id": "growth:1",
            "is_resource_growth": "yes",
            "growth_kind": "container_growth",
            "resource_dimension": "entries",
            "attacker_influence": [{"target": "key", "evidence_id": "fact:key"}],
            "resource_effect": "adds_entries",
            "attacker_variable": "request key",
            "attacker_value_space": "unlimited",
            "growth_unit": "one retained map entry",
            "growth_function": "distinct keys add retained entries",
            "amplification_class": "high_cardinality_retention",
            "requests_to_pressure": "many",
            "concurrency_model": "repeatable requests",
            "retention_window": "process",
            "failure_mechanism": "heap_exhaustion",
            "failure_signal": "retained entries exhaust heap",
            "required_static_evidence": ["fact:key"],
            "contract_status": "dos_relevant",
            "rejection_reason": "none",
            "confidence": "high",
        }
        record.update(changes)
        return record

    def _fingerprint(self):
        return StageFingerprint(
            schema_version=SCHEMA_VERSION,
            tool_version="0.1.0",
            implementation_version="entries-v1",
            database_fingerprint="db-a",
            query_pack_hash="ql-a",
            config_hash="config-a",
            upstream_hashes={"input": "old"},
        )

    def _completed_run(self, fingerprint, artifacts):
        return {
            "stages": {
                "entries": {
                    "status": "completed",
                    "fingerprint": fingerprint.to_dict(),
                    "artifacts": artifacts,
                }
            }
        }

    def test_hash_and_identifier_ignore_mapping_key_order(self):
        left = {"framework": "servlet", "handler": {"line": 10, "file": "A.java"}}
        right = {"handler": {"file": "A.java", "line": 10}, "framework": "servlet"}
        self.assertEqual(sha256_canonical_json(left), sha256_canonical_json(right))
        self.assertEqual(stable_identifier("entry", left), stable_identifier("entry", right))

    def test_reader_rejects_non_standard_json_with_path_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.jsonl"
            path.write_text('{"value": NaN}\n', encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "entry_facts")
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_JSON")
        self.assertEqual(raised.exception.details["line"], 1)

    def test_reader_rejects_duplicate_keys_and_bounded_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.jsonl"
            path.write_text('{"entry_id":"entry:1","entry_id":"entry:2"}\n', encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "entry_facts")
            self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_JSON")
            self.assertEqual(raised.exception.details["line"], 1)

    def test_writer_rejects_lazy_million_key_mapping_without_iteration(self):
        class HugeMapping(Mapping[str, object]):
            def __len__(self) -> int: return 1_000_000
            def __iter__(self) -> Iterator[str]:
                raise AssertionError("unbounded mapping must not be iterated")
            def __getitem__(self, key: str) -> object: raise KeyError(key)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entry_facts.jsonl"
            with self.assertRaises(AnalyzerError) as raised:
                write_jsonl_atomically(path, "entry_facts", [HugeMapping()], {})
            self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_RECORD")
            self.assertFalse(path.exists())

    def test_concurrent_publication_ref_hashes_own_bytes(self):
        records = [{
            "entry_id": "entry:a", "framework": "servlet", "protocol": "http",
            "handler": {"callable": "A.run", "file": "A.java", "start_line": 1},
            "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler.handle", "file": "fixture/Handler.java", "start_line": 1}, "route_or_event": "/a", "auth_context": "unknown",
            "registration_pattern_id": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
            "attacker_inputs": [], "materialization_phase": "unknown",
        }]
        other = [{**records[0], "entry_id": "entry:b", "route_or_event": "/b"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entry_facts.jsonl"
            barrier = threading.Barrier(2)
            original_replace = __import__("os").replace
            refs: list[object] = []
            def synchronized_replace(*args: object, **kwargs: object) -> None:
                barrier.wait(5)
                original_replace(*args, **kwargs)
            def publish(value: list[dict[str, object]]) -> None:
                refs.append(write_jsonl_atomically(path, "entry_facts", value, {}))
            with mock.patch("dosweb.artifacts.jsonl.os.replace", side_effect=synchronized_replace):
                workers = [threading.Thread(target=publish, args=(value,)) for value in (records, other)]
                for worker in workers: worker.start()
                for worker in workers: worker.join(5)
            expected = {
                sha256_canonical_json(records[0]) + "-line",
                sha256_canonical_json(other[0]) + "-line",
            }
            actual_bytes = [(__import__("json").dumps(value[0], sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode() for value in (records, other)]
            expected_hashes = {__import__("hashlib").sha256(data).hexdigest() for data in actual_bytes}
            self.assertEqual({ref.sha256 for ref in refs}, expected_hashes)

    def test_writer_rejects_unbounded_iterable_without_publication(self):
        consumed = 0
        def records():
            nonlocal consumed
            while True:
                consumed += 1
                yield {"entry_id": f"entry:{consumed}"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entry_facts.jsonl"
            with self.assertRaises(AnalyzerError) as raised:
                write_jsonl_atomically(path, "entry_facts", records(), {})
            self.assertTrue(raised.exception.code.startswith("ARTIFACT_"))
            self.assertFalse(path.exists())
        self.assertLess(consumed, 100000)

    def test_reader_rejects_non_object_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.jsonl"
            path.write_text('[1, 2, 3]\n', encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "entry_facts")
        self.assertEqual(raised.exception.code, "ARTIFACT_RECORD_NOT_OBJECT")

    def test_reader_rejects_blank_line_with_path_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.jsonl"
            path.write_text("\n", encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "entry_facts")
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_JSON")
        self.assertEqual(raised.exception.details["path"], str(path))
        self.assertEqual(raised.exception.details["line"], 1)

    def test_reader_wraps_invalid_utf8_with_path_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.jsonl"
            path.write_bytes(b'{"entry_id":"entry:1"}\n\xff')
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "entry_facts")
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_JSON")
        self.assertEqual(raised.exception.details["path"], str(path))
        self.assertEqual(raised.exception.details["line"], 2)

    def test_atomic_writer_does_not_publish_when_validation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entry_facts.jsonl"
            with self.assertRaises(AnalyzerError):
                write_jsonl_atomically(
                    path,
                    "entry_facts",
                    [{"entry_id": ""}],
                    known_ids={},
                )
            self.assertFalse(path.exists())

    def test_atomic_writer_sorts_records_by_canonical_bytes(self):
        records = [
            {
                "entry_id": "entry:b",
                "framework": "servlet",
                "protocol": "http",
                "handler": {"callable": "Handler.run", "file": "Handler.java", "start_line": 1},
                "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler.handle", "file": "fixture/Handler.java", "start_line": 1},
                "registration_pattern_id": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
                "route_or_event": "/b",
                "auth_context": "unknown",
                "attacker_inputs": [],
                "materialization_phase": "unknown",
            },
            {
                "entry_id": "entry:a",
                "framework": "servlet",
                "protocol": "http",
                "handler": {"callable": "Handler.run", "file": "Handler.java", "start_line": 1},
                "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler.handle", "file": "fixture/Handler.java", "start_line": 1},
                "registration_pattern_id": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
                "route_or_event": "/a",
                "auth_context": "unknown",
                "attacker_inputs": [],
                "materialization_phase": "unknown",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left.jsonl"
            right = Path(tmp) / "right.jsonl"
            left_ref = write_jsonl_atomically(left, "entry_facts", records, known_ids={})
            right_ref = write_jsonl_atomically(
                right, "entry_facts", list(reversed(records)), known_ids={}
            )
            self.assertEqual(left.read_bytes(), right.read_bytes())
        self.assertEqual(left_ref.sha256, right_ref.sha256)

    def test_schema_registry_covers_every_p0_jsonl_artifact(self):
        self.assertEqual("2.7", SCHEMA_VERSION)
        self.assertEqual(
            set(ARTIFACT_SCHEMAS),
            {
                "entry_facts",
                "entry_gap_facts",
                "entry_interposition_facts",
                "entry_security_facts",
                "modeled_configuration",
                "growth_candidates",
                "candidate_entry_links",
                "candidate_negative_proofs",
                "candidate_dispositions",
                "repeatability_decisions",
                "amplification_decisions",
                "growth_contracts",
                "auth_contracts",
                "reachability_decisions",
                "llm_audit",
                "verified_growth",
                "flow_proofs",
                "guard_candidates",
                "bound_candidates",
                "release_candidates",
                "lifecycle_summaries",
                "lifecycle_evidence",
                "lifecycle_coverage",
                "lifecycle_results",
                "static_findings",
                "finding_families",
                "lifecycle_certificates",
            },
        )

    def test_candidate_entry_link_semantic_identity_and_collections_are_strict(
        self,
    ) -> None:
        link = CandidateEntryLink.create(
            "growth:semantic-link",
            "entry:semantic-link",
            "complete",
            ("fact:a", "fact:b"),
            ("ASSOCIATION_A", "ASSOCIATION_B"),
        ).to_dict()
        validate_records("candidate_entry_links", [link])

        cases = {
            "status_tamper": {**link, "status": "partial"},
            "evidence_tamper": {
                **link,
                "evidence_ids": ["fact:a", "fact:b", "fact:c"],
            },
            "reason_tamper": {
                **link,
                "reason_codes": [
                    "ASSOCIATION_A",
                    "ASSOCIATION_B",
                    "ASSOCIATION_C",
                ],
            },
            "empty_evidence": {**link, "evidence_ids": []},
            "duplicate_evidence": {
                **link,
                "evidence_ids": ["fact:a", "fact:a"],
            },
            "unsorted_evidence": {
                **link,
                "evidence_ids": ["fact:b", "fact:a"],
            },
            "empty_reasons": {**link, "reason_codes": []},
            "duplicate_reasons": {
                **link,
                "reason_codes": ["ASSOCIATION_A", "ASSOCIATION_A"],
            },
            "unsorted_reasons": {
                **link,
                "reason_codes": ["ASSOCIATION_B", "ASSOCIATION_A"],
            },
        }
        for name, record in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(AnalyzerError):
                    validate_records("candidate_entry_links", [record])

    def test_finding_family_allowlist_is_strict_before_publication(self):
        semantic = {
            "verdict": "static_unknown",
            "priority": "inventory",
            "primary_finding_id": "finding:primary",
            "member_finding_ids": ["finding:primary"],
            "member_certificate_ids": ["certificate:primary"],
            "entry_ids": ["entry:primary"],
            "growth_ids": ["growth:primary"],
            "resource_id": "resource:primary",
            "reachability_status": "unknown",
            "amplification_class": "unknown",
            "reason_codes": ["FIXTURE_UNKNOWN"],
        }
        record = {
            "family_id": stable_identifier("family", semantic),
            **semantic,
        }

        validate_records("finding_families", [record])
        with self.assertRaises(AnalyzerError) as raised:
            validate_records("finding_families", [{**record, "unexpected": True}])
        self.assertEqual("ARTIFACT_INVALID_RECORD", raised.exception.code)
        with self.assertRaises(AnalyzerError):
            validate_records(
                "finding_families", [{**record, "family_id": "family:forged"}]
            )

    def test_candidate_disposition_schema_preserves_gap_and_negative_proof(self):
        record = CandidateDisposition.create(
            "growth:partial",
            "gap_eligible",
            canonical_entry_id="entry:partial",
            local_growth_status="partial",
            association_status="complete",
            link_ids=("candidate_link:partial",),
            evidence_ids=("candidate_link:partial", "fact:partial"),
            negative_proof_ids=(),
            reason_codes=("MATURATION_GAP_ELIGIBLE",),
        ).to_dict()
        validate_records("candidate_dispositions", [record])
        with self.assertRaises(AnalyzerError):
            validate_records(
                "candidate_dispositions",
                [{**record, "link_ids": []}],
            )

        negative = CandidateNegativeProof.create(
            "growth:rejected",
            "server_controlled_source",
            evidence_ids=("fact:server-sized",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        rejected = CandidateDisposition.create(
            "growth:rejected",
            "rejected",
            canonical_entry_id="",
            local_growth_status="rejected",
            association_status="missing",
            link_ids=(),
            evidence_ids=(negative["negative_proof_id"],),
            negative_proof_ids=(negative["negative_proof_id"],),
            reason_codes=("MATURATION_SOURCE_PROVEN_NEGATIVE",),
        ).to_dict()
        validate_records("candidate_negative_proofs", [negative])
        validate_references(
            "candidate_dispositions",
            [rejected],
            {
                "growth_id": {"growth:rejected"},
                "entry_id": set(),
                "link_id": set(),
                "negative_proof_id": {negative["negative_proof_id"]},
                "negative_proof_growth_ids": {
                    negative["negative_proof_id"]: "growth:rejected"
                },
            },
        )

    def test_candidate_disposition_artifact_enforces_maturation_matrix(self):
        cases = (
            ("gap_eligible", "partial", "complete", True),
            ("gap_eligible", "complete", "partial", True),
            ("gap_eligible", "complete", "complete", False),
            ("formal_eligible", "complete", "complete", True),
            ("formal_eligible", "partial", "complete", False),
            ("formal_eligible", "complete", "partial", False),
        )
        for status, local_status, association_status, accepted in cases:
            semantic = {
                "growth_id": "growth:maturation-matrix",
                "status": status,
                "canonical_entry_id": "entry:maturation-matrix",
                "local_growth_status": local_status,
                "association_status": association_status,
                "link_ids": ["candidate_link:maturation-matrix"],
                "evidence_ids": [
                    "candidate_link:maturation-matrix",
                    "fact:growth",
                ],
                "negative_proof_ids": [],
                "reason_codes": [
                    "MATURATION_FORMAL_ELIGIBLE"
                    if status == "formal_eligible"
                    else "MATURATION_GAP_ELIGIBLE"
                ],
            }
            record = {
                "disposition_id": stable_identifier("disposition", semantic),
                **semantic,
            }
            with self.subTest(
                status=status,
                local_status=local_status,
                association_status=association_status,
            ):
                if accepted:
                    validate_records("candidate_dispositions", [record])
                else:
                    with self.assertRaises(AnalyzerError):
                        validate_records("candidate_dispositions", [record])

    def test_candidate_artifact_schema_enforces_negative_proof_status_contract(self):
        proof = CandidateNegativeProof.create(
            "growth:negative",
            "server_controlled_source",
            evidence_ids=("fact:growth",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        rejected = CandidateDisposition.create(
            "growth:negative",
            "rejected",
            canonical_entry_id="",
            local_growth_status="rejected",
            association_status="missing",
            link_ids=(),
            evidence_ids=(proof["negative_proof_id"],),
            negative_proof_ids=(proof["negative_proof_id"],),
            reason_codes=("MATURATION_SOURCE_PROVEN_NEGATIVE",),
        ).to_dict()

        ordinary_only = {
            **rejected,
            "evidence_ids": ["fact:ordinary"],
            "negative_proof_ids": [],
        }
        ordinary_semantic = {
            key: value
            for key, value in ordinary_only.items()
            if key != "disposition_id"
        }
        ordinary_only["disposition_id"] = stable_identifier(
            "disposition", ordinary_semantic
        )
        with self.assertRaises(AnalyzerError):
            validate_records("candidate_dispositions", [ordinary_only])

        inventory_with_proof = {
            **rejected,
            "status": "inventory_unresolved",
            "local_growth_status": "unknown",
        }
        inventory_semantic = {
            key: value
            for key, value in inventory_with_proof.items()
            if key != "disposition_id"
        }
        inventory_with_proof["disposition_id"] = stable_identifier(
            "disposition", inventory_semantic
        )
        with self.assertRaises(AnalyzerError):
            validate_records("candidate_dispositions", [inventory_with_proof])

        non_fact_proof = {**proof, "evidence_ids": ["reachability:decision"]}
        proof_semantic = {
            key: value for key, value in non_fact_proof.items()
            if key != "negative_proof_id"
        }
        non_fact_proof["negative_proof_id"] = stable_identifier(
            "negative_proof", proof_semantic
        )
        with self.assertRaises(AnalyzerError):
            validate_records("candidate_negative_proofs", [non_fact_proof])

    def test_candidate_disposition_schema_requires_exact_negative_proof_evidence(self):
        first = CandidateNegativeProof.create(
            "growth:negative",
            "server_controlled_source",
            evidence_ids=("fact:first",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        )
        second = CandidateNegativeProof.create(
            "growth:negative",
            "non_retained_owner",
            evidence_ids=("fact:second",),
            reason_codes=("NEGATIVE_NON_RETAINED_OWNER",),
        )
        valid = CandidateDisposition.create(
            "growth:negative",
            "rejected",
            canonical_entry_id="",
            local_growth_status="rejected",
            association_status="missing",
            link_ids=(),
            evidence_ids=(first.negative_proof_id,),
            negative_proof_ids=(first.negative_proof_id,),
            reason_codes=("MATURATION_SOURCE_PROVEN_NEGATIVE",),
        ).to_dict()

        cases = (
            {
                **valid,
                "evidence_ids": sorted(
                    [first.negative_proof_id, second.negative_proof_id]
                ),
            },
            {**valid, "evidence_ids": ["fact:ordinary"]},
        )
        for malformed in cases:
            semantic = {
                key: value
                for key, value in malformed.items()
                if key != "disposition_id"
            }
            malformed["disposition_id"] = stable_identifier(
                "disposition", semantic
            )
            with self.subTest(evidence_ids=malformed["evidence_ids"]):
                with self.assertRaises(AnalyzerError):
                    validate_records("candidate_dispositions", [malformed])

    def test_eligible_disposition_link_must_own_growth_and_canonical_entry(self):
        cases = (
            ("growth:other", "entry:formal"),
            ("growth:formal", "entry:other"),
        )
        for link_growth_id, link_entry_id in cases:
            link = CandidateEntryLink.create(
                link_growth_id,
                link_entry_id,
                "complete",
                ("fact:association",),
                ("ASSOCIATION_FIXTURE",),
            )
            disposition = CandidateDisposition.create(
                "growth:formal",
                "formal_eligible",
                canonical_entry_id="entry:formal",
                local_growth_status="complete",
                association_status="complete",
                link_ids=(link.link_id,),
                evidence_ids=("fact:growth", link.link_id),
                negative_proof_ids=(),
                reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
            )
            known = {
                "growth_id": {"growth:formal", "growth:other"},
                "entry_id": {"entry:formal", "entry:other"},
                "link_id": {link.link_id},
                "link_ownership": {
                    link.link_id: (link.growth_id, link.entry_id, link.status)
                },
                "negative_proof_id": set(),
                "negative_proof_growth_ids": {},
            }
            with self.subTest(
                link_growth_id=link_growth_id,
                link_entry_id=link_entry_id,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    validate_references(
                        "candidate_dispositions",
                        [disposition.to_dict()],
                        known,
                    )
                self.assertEqual(
                    "ANALYSIS_DANGLING_FACT_REFERENCE", raised.exception.code
                )

    def test_eligible_disposition_accepts_exact_link_ownership(self):
        link = CandidateEntryLink.create(
            "growth:formal",
            "entry:formal",
            "complete",
            ("fact:association",),
            ("ASSOCIATION_FIXTURE",),
        )
        disposition = CandidateDisposition.create(
            "growth:formal",
            "formal_eligible",
            canonical_entry_id="entry:formal",
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=("fact:growth", link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )

        validate_references(
            "candidate_dispositions",
            [disposition.to_dict()],
            {
                "growth_id": {"growth:formal"},
                "entry_id": {"entry:formal"},
                "link_id": {link.link_id},
                "link_ownership": {
                    link.link_id: (link.growth_id, link.entry_id, link.status)
                },
                "negative_proof_id": set(),
                "negative_proof_growth_ids": {},
            },
        )

    def test_partial_link_cannot_masquerade_as_formal_complete_association(self):
        link = CandidateEntryLink.create(
            "growth:formal",
            "entry:formal",
            "partial",
            ("fact:association",),
            ("ASSOCIATION_PARTIAL_FIXTURE",),
        )
        disposition = CandidateDisposition.create(
            "growth:formal",
            "formal_eligible",
            canonical_entry_id="entry:formal",
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=("fact:growth", link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )

        with self.assertRaises(AnalyzerError) as raised:
            validate_references(
                "candidate_dispositions",
                [disposition.to_dict()],
                {
                    "growth_id": {"growth:formal"},
                    "entry_id": {"entry:formal"},
                    "link_id": {link.link_id},
                    "link_ownership": {
                        link.link_id: (link.growth_id, link.entry_id, link.status)
                    },
                    "negative_proof_id": set(),
                    "negative_proof_growth_ids": {},
                },
            )
        self.assertEqual(
            "ANALYSIS_DANGLING_FACT_REFERENCE", raised.exception.code
        )

    def test_gap_link_status_must_exactly_match_association_status(self):
        cases = (
            ("partial", "complete", "complete", True),
            ("complete", "partial", "partial", True),
            ("partial", "complete", "partial", False),
            ("complete", "partial", "complete", False),
        )
        for local_status, association_status, link_status, accepted in cases:
            link = CandidateEntryLink.create(
                "growth:gap",
                "entry:gap",
                link_status,
                ("fact:association",),
                ("ASSOCIATION_GAP_FIXTURE",),
            )
            disposition = CandidateDisposition.create(
                "growth:gap",
                "gap_eligible",
                canonical_entry_id="entry:gap",
                local_growth_status=local_status,
                association_status=association_status,
                link_ids=(link.link_id,),
                evidence_ids=("fact:growth", link.link_id),
                negative_proof_ids=(),
                reason_codes=("MATURATION_GAP_ELIGIBLE",),
            )
            known = {
                "growth_id": {"growth:gap"},
                "entry_id": {"entry:gap"},
                "link_id": {link.link_id},
                "link_ownership": {
                    link.link_id: (link.growth_id, link.entry_id, link.status)
                },
                "negative_proof_id": set(),
                "negative_proof_growth_ids": {},
            }
            with self.subTest(
                local_status=local_status,
                association_status=association_status,
                link_status=link_status,
            ):
                if accepted:
                    validate_references(
                        "candidate_dispositions", [disposition.to_dict()], known
                    )
                else:
                    with self.assertRaises(AnalyzerError):
                        validate_references(
                            "candidate_dispositions",
                            [disposition.to_dict()],
                            known,
                        )

    def test_negative_proof_references_are_scoped_to_the_same_growth_candidate(self):
        first = GrowthCandidate.create(
            site=SourceLocation("src/First.java", 10),
            kind="direct_allocation",
            operation="array_creation",
            resource_dimension="bytes",
            receiver="byte[]",
            field_path="allocation",
            demand_inputs=(DemandInput("size", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:first"}),
            coverage_notes=("direct_allocation:server_metadata_size",),
        )
        second = GrowthCandidate.create(
            site=SourceLocation("src/Second.java", 20),
            kind="direct_allocation",
            operation="array_creation",
            resource_dimension="bytes",
            receiver="byte[]",
            field_path="allocation",
            demand_inputs=(DemandInput("size", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:second"}),
            coverage_notes=("direct_allocation:server_metadata_size",),
        )
        wrong_evidence = CandidateNegativeProof.create(
            first.growth_id,
            "server_controlled_source",
            evidence_ids=("fact:second",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        )
        known = {
            "growth_id": {first.growth_id, second.growth_id},
            "fact_id": {"fact:first", "fact:second"},
            "growth_fact_ids": {
                first.growth_id: {"fact:first"},
                second.growth_id: {"fact:second"},
            },
        }
        with self.assertRaises(AnalyzerError) as raised:
            validate_references(
                "candidate_negative_proofs",
                [wrong_evidence.to_dict()],
                known,
            )
        self.assertEqual(
            "ANALYSIS_DANGLING_FACT_REFERENCE", raised.exception.code
        )

        second_proof = CandidateNegativeProof.create(
            second.growth_id,
            "server_controlled_source",
            evidence_ids=("fact:second",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        )
        mismatched = CandidateDisposition.create(
            first.growth_id,
            "rejected",
            canonical_entry_id="",
            local_growth_status="rejected",
            association_status="missing",
            link_ids=(),
            evidence_ids=(second_proof.negative_proof_id,),
            negative_proof_ids=(second_proof.negative_proof_id,),
            reason_codes=("MATURATION_SOURCE_PROVEN_NEGATIVE",),
        )
        with self.assertRaises(AnalyzerError) as raised:
            validate_references(
                "candidate_dispositions",
                [mismatched.to_dict()],
                {
                    "growth_id": {first.growth_id, second.growth_id},
                    "entry_id": set(),
                    "link_id": set(),
                    "negative_proof_id": {second_proof.negative_proof_id},
                    "negative_proof_growth_ids": {
                        second_proof.negative_proof_id: second.growth_id
                    },
                },
            )
        self.assertEqual(
            "ANALYSIS_DANGLING_FACT_REFERENCE", raised.exception.code
        )

    def test_lifecycle_candidate_models_match_published_artifact_schemas(self):
        guard = GuardCandidate.create(
            site_file="fixture/Handler.java",
            site_start_line=10,
            kind="input_validation",
            resource_dimension="bytes",
            scope="request",
            behavior="reject",
            dominates_growth=True,
            reject_path_reaches_growth=False,
            configuration_key="request.max-bytes",
            configuration_value="1024",
            representation="raw_body",
            phase="before_growth",
            covers_materialization=True,
            authorization_only=False,
            evidence=("fact:guard",),
            coverage_status="complete",
        )
        bound = BoundCandidate.create(
            site_file="fixture/Handler.java",
            site_start_line=20,
            kind="capacity",
            resource_dimension="tasks",
            scope="instance",
            behavior="block",
            receiver="fixture.Handler.queue",
            field_path="fixture.Handler.queue",
            result_checked=True,
            configuration_key="queue.capacity",
            configuration_value="64",
            phase="inside_growth",
            covers_flow=True,
            request_encoding="any",
            queue_resource="fixture.Handler.queue",
            product_bound=True,
            evidence=("fact:bound",),
            coverage_status="complete",
        )
        release = ReleaseCandidate.create(
            site_file="fixture/Handler.java",
            site_start_line=30,
            kind="remove",
            resource_dimension="entries",
            scope="instance",
            receiver="fixture.Handler.cache",
            key_identity="key",
            synchronous=True,
            normal_path=True,
            exceptional_path=True,
            actual_reduction=True,
            after_growth=True,
            transfer_only=False,
            async_kind="none",
            evidence=("fact:release",),
            coverage_status="complete",
        )

        validate_references("guard_candidates", [guard.to_dict()], known_ids={})
        validate_references("bound_candidates", [bound.to_dict()], known_ids={})
        validate_references("release_candidates", [release.to_dict()], known_ids={})

    def test_bound_candidate_schema_accepts_numeric_clamp(self) -> None:
        clamp = BoundCandidate.create(
            site_file="fixture/Handler.java",
            site_start_line=20,
            kind="limit",
            resource_dimension="bytes",
            scope="request",
            behavior="clamp",
            receiver="java.nio.ByteBuffer",
            field_path="allocation",
            result_checked=True,
            configuration_key="literal",
            configuration_value="1024",
            phase="inside_growth",
            covers_flow=True,
            request_encoding="any",
            queue_resource="allocation",
            product_bound=True,
            evidence=("numeric_min_literal",),
            coverage_status="complete",
        )

        validate_records("bound_candidates", [clamp.to_dict()])

    def test_entry_schema_requires_p0_fields_and_enum_values(self):
        record = {
            "entry_id": "entry:abc",
            "framework": "spring_mvc",
            "protocol": "http",
            "handler": {"callable": "a", "file": "A.java", "start_line": 1},
            "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler.handle", "file": "fixture/Handler.java", "start_line": 1},
            "registration_pattern_id": "entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
            "route_or_event": "/a",
            "auth_context": "unauthenticated",
            "attacker_inputs": [],
            "materialization_phase": "before_handler",
        }
        validate_references("entry_facts", [record], known_ids={})
        record["framework"] = "unsupported"
        with self.assertRaises(AnalyzerError) as raised:
            validate_references("entry_facts", [record], known_ids={})
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_ENUM")

    def test_schema_rejects_malformed_p0_nested_fields(self):
        entry = {
            "entry_id": "entry:1",
            "framework": "servlet",
            "protocol": "http",
            "handler": {"callable": "Handler.run", "file": "Handler.java", "start_line": 1},
            "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler.handle", "file": "fixture/Handler.java", "start_line": 1},
            "registration_pattern_id": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
            "route_or_event": "/",
            "auth_context": "unknown",
            "attacker_inputs": [],
            "materialization_phase": "unknown",
        }
        malformed_entries = (
            {**entry, "handler": {"callable": "Handler.run"}},
            {**entry, "registration": []},
            {**entry, "attacker_inputs": {}},
        )
        for record in malformed_entries:
            with self.subTest(record=record):
                with self.assertRaises(AnalyzerError) as raised:
                    validate_references("entry_facts", [record], {})
                self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_RECORD")

        growth = {
            "growth_id": "growth:1",
            "site": {},
            "kind": "container_growth",
            "operation": "Map.put",
            "resource_point": {
                "resource_id": "resource:1",
                "dimension": "entries",
                "receiver": "cache",
                "field_path": "Cache.values",
            },
            "demand_inputs": [],
            "escape_scope": "global",
            "candidate_evidence": [],
            "coverage_status": "complete",
            "coverage_notes": ["fixture"],
        }
        with self.assertRaises(AnalyzerError) as raised:
            validate_references(
                "growth_candidates", [{**growth, "resource_point": {}}], {}
            )
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_RECORD")

        flow = {
            "path_id": "flow:1",
            "entry_id": "entry:1",
            "growth_id": "growth:1",
            "attacker_control": {"target": "size", "source": "body", "sink": "capacity"},
            "call_path": [],
            "phase_sequence": [],
            "confidence": "proven", "flow_kind": "data_flow", "coverage_status": "complete", "coverage_note": "normalized",
        }
        with self.assertRaises(AnalyzerError) as raised:
            validate_references(
                "flow_proofs",
                [{**flow, "attacker_control": {"target": "invalid", "source": "body", "sink": "capacity"}}],
                {"entry_id": {"entry:1"}, "growth_id": {"growth:1"}},
            )
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_ENUM")

    def test_reference_validator_rejects_non_string_and_unhashable_values(self):
        flow = {
            "path_id": "flow:1",
            "entry_id": [],
            "growth_id": "growth:1",
            "attacker_control": {"target": "size", "source": "body", "sink": "capacity"},
            "call_path": [],
            "phase_sequence": [],
            "confidence": "proven", "flow_kind": "data_flow", "coverage_status": "complete", "coverage_note": "normalized",
        }
        with self.assertRaises(AnalyzerError) as raised:
            validate_references(
                "flow_proofs", [flow], {"entry_id": {"entry:1"}, "growth_id": {"growth:1"}}
            )
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_RECORD")

        certificate = {
            "certificate_id": "certificate:1",
            "entry_id": "entry:1",
            "growth_id": "growth:1",
            "attacker_inputs": [],
            "resource_point": {},
            "path_ids": ["flow:1", {}],
            "guard_decision": {},
            "bound_decision": {},
            "release_decision": {},
            "assertions": [],
            "verdict": "static_unknown",
            "reason_codes": [],
            "assumptions": [],
            "coverage_gaps": [],
            "unresolved_facts": [],
            "suggested_follow_up_measurements": [],
        }
        with self.assertRaises(AnalyzerError) as raised:
            validate_references(
                "lifecycle_certificates",
                [certificate],
                {"entry_id": {"entry:1"}, "growth_id": {"growth:1"}, "path_id": {"flow:1"}},
            )
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_RECORD")

    def test_growth_resource_dimension_requires_concrete_value_but_contract_allows_unknown(self):
        growth = {
            "growth_id": "growth:1",
            "site": {},
            "kind": "container_growth",
            "operation": "Map.put",
            "resource_point": {
                "resource_id": "resource:1",
                "dimension": "unknown",
                "receiver": "cache",
                "field_path": "Cache.values",
            },
            "demand_inputs": [],
            "escape_scope": "global",
            "candidate_evidence": [],
            "coverage_status": "complete",
            "coverage_notes": ["fixture"],
        }
        with self.assertRaises(AnalyzerError) as raised:
            validate_references("growth_candidates", [growth], {})
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_ENUM")

        contract = self._growth_contract(
            is_resource_growth="unknown",
            growth_kind="unknown",
            resource_dimension="unknown",
            attacker_influence=[],
            resource_effect="unknown",
            attacker_variable="unknown",
            attacker_value_space="unknown",
            growth_unit="unknown",
            growth_function="unknown",
            amplification_class="unknown",
            requests_to_pressure="unknown",
            concurrency_model="unknown",
            retention_window="unknown",
            failure_mechanism="unknown",
            failure_signal="unknown",
            required_static_evidence=[],
            contract_status="unknown",
            rejection_reason="unknown",
            confidence="low",
        )
        validate_references("growth_contracts", [contract], {"growth_id": {"growth:1"}, "fact_id": set(), "growth_fact_ids": {"growth:1": set()}})

    def test_artifact_ids_are_unique_prefixed_and_growth_evidence_is_fact_syntax(self):
        entry = {
            "entry_id": "entry:1", "framework": "servlet", "protocol": "http",
            "handler": {"callable": "Handler.run", "file": "Handler.java", "start_line": 1},
            "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler.handle", "file": "fixture/Handler.java", "start_line": 1}, "route_or_event": "/", "auth_context": "unknown",
            "registration_pattern_id": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
            "attacker_inputs": [], "materialization_phase": "unknown",
        }
        for records in ((entry, entry), ({**entry, "entry_id": "wrong"},)):
            with self.subTest(records=records), self.assertRaises(AnalyzerError) as raised:
                validate_references("entry_facts", records, {})
            self.assertTrue(raised.exception.code.startswith("ARTIFACT_"))

        contract = self._growth_contract(
            attacker_influence=[{"target": "key", "evidence_id": "not-a-fact"}],
            required_static_evidence=["fact:" + "x" * 257],
        )
        with self.assertRaises(AnalyzerError) as raised:
            validate_references("growth_contracts", [contract], {"growth_id": {"growth:1"}, "fact_id": set(), "growth_fact_ids": {"growth:1": set()}})
        self.assertTrue(raised.exception.code.startswith("ARTIFACT_"))

    def test_growth_contract_evidence_is_bound_to_its_growth(self):
        contract = self._growth_contract(
            growth_id="growth:a",
            attacker_influence=[{"target": "key", "evidence_id": "fact:b"}],
            required_static_evidence=["fact:b"],
        )
        known = {
            "growth_id": {"growth:a", "growth:b"},
            "fact_id": {"fact:a", "fact:b"},
            "growth_fact_ids": {"growth:a": {"fact:a"}, "growth:b": {"fact:b"}},
        }
        with self.assertRaises(AnalyzerError) as raised:
            validate_references("growth_contracts", [contract], known)
        self.assertEqual(raised.exception.code, "ANALYSIS_DANGLING_FACT_REFERENCE")
        missing = {"growth_id": {"growth:a"}, "fact_id": {"fact:a"}}
        with self.assertRaises(AnalyzerError):
            validate_references("growth_contracts", [{**contract, "attacker_influence": [], "required_static_evidence": []}], missing)

    def test_growth_contract_artifact_rejects_free_text_fabricated_evidence_and_extra_provider_fields(self):
        contract = self._growth_contract()
        known = {"growth_id": {"growth:1"}, "fact_id": {"fact:key"}, "growth_fact_ids": {"growth:1": {"fact:key"}}}
        validate_references("growth_contracts", [contract], known)
        invalid = (
            {**contract, "resource_effect": "free form private text"},
            {**contract, "attacker_influence": [{"target": "key", "evidence_id": "fact:invented"}]},
            {**contract, "attacker_influence": [{"target": "key", "evidence_id": ["fact:key"]}]},
            {**contract, "required_static_evidence": ["fact:invented"]},
            {**contract, "raw_response": {"choices": []}},
            {**contract, "provider_envelope": "private"},
        )
        for record in invalid:
            with self.subTest(record=record):
                with self.assertRaises(AnalyzerError):
                    validate_references("growth_contracts", [record], known)

    def test_lifecycle_artifact_schemas_reject_id_only_and_accept_minimum_records(self):
        cases = {
            "guard_candidates": (
                {"guard_id": "guard:1"},
                {
                    "guard_id": "guard:1",
                    "site": {"file": "fixture/Handler.java", "start_line": 10},
                    "kind": "request_limit",
                    "resource_dimension": "bytes",
                    "scope": "request",
                    "behavior": "reject",
                    "dominates_growth": True,
                    "reject_path_reaches_growth": False,
                    "configuration_key": "request.max-bytes",
                    "configuration_value": "1024",
                    "representation": "raw_body",
                    "phase": "before_growth",
                    "covers_materialization": True,
                    "authorization_only": False,
                    "evidence": ["fact:guard"],
                    "coverage_status": "complete",
                },
                {},
            ),
            "bound_candidates": (
                {"bound_id": "bound:1"},
                {
                    "bound_id": "bound:1",
                    "site": {"file": "fixture/Handler.java", "start_line": 20},
                    "kind": "capacity",
                    "resource_dimension": "tasks",
                    "scope": "instance",
                    "behavior": "block",
                    "receiver": "fixture.Handler.queue",
                    "field_path": "fixture.Handler.queue",
                    "result_checked": True,
                    "configuration_key": "queue.capacity",
                    "configuration_value": "64",
                    "phase": "inside_growth",
                    "covers_flow": True,
                    "request_encoding": "any",
                    "queue_resource": "fixture.Handler.queue",
                    "product_bound": True,
                    "evidence": ["fact:bound"],
                    "coverage_status": "complete",
                },
                {},
            ),
            "release_candidates": (
                {"release_id": "release:1"},
                {
                    "release_id": "release:1",
                    "site": {"file": "fixture/Handler.java", "start_line": 30},
                    "kind": "remove",
                    "resource_dimension": "entries",
                    "scope": "instance",
                    "receiver": "fixture.Handler.cache",
                    "key_identity": "key",
                    "synchronous": True,
                    "normal_path": True,
                    "exceptional_path": True,
                    "actual_reduction": True,
                    "after_growth": True,
                    "transfer_only": False,
                    "async_kind": "none",
                    "evidence": ["fact:release"],
                    "coverage_status": "complete",
                },
                {},
            ),
            "lifecycle_results": (
                {"lifecycle_result_id": "lifecycle:1"},
                (lambda semantic: {
                    "lifecycle_result_id": stable_identifier("lifecycle", semantic),
                    **semantic,
                })({
                    "entry_id": "entry:1",
                    "growth_id": "growth:1",
                    "path_id": "flow:1",
                    "guard_decision": "absent",
                    "bound_decision": "effective",
                    "release_decision": "unknown",
                    "reason_codes": [],
                    "guard": {"status": "absent", "reason_codes": [], "checks": [], "evidence_ids": [], "unresolved_facts": [], "candidate_ids": []},
                    "bound": {"status": "effective", "reason_codes": [], "checks": [], "evidence_ids": [], "unresolved_facts": [], "candidate_ids": []},
                    "release": {"status": "unknown", "classification": "unknown", "reason_codes": [], "checks": [], "evidence_ids": [], "unresolved_facts": [], "candidate_ids": []},
                }),
                {
                    "entry_id": {"entry:1"},
                    "growth_id": {"growth:1"},
                    "path_id": {"flow:1"},
                },
            ),
            "static_findings": (
                {"finding_id": "finding:1"},
                {
                    "finding_id": "finding:1",
                    "certificate_id": "certificate:1",
                    "entry_id": "entry:1",
                    "growth_id": "growth:1",
                    "verdict": "static_vulnerable",
                    "reason_codes": [],
                },
                {
                    "certificate_id": {"certificate:1"},
                    "entry_id": {"entry:1"},
                    "growth_id": {"growth:1"},
                },
            ),
            "lifecycle_certificates": (
                {"certificate_id": "certificate:1"},
                {
                    "certificate_id": "certificate:1",
                    "entry_id": "entry:1",
                    "growth_id": "growth:1",
                    "attacker_inputs": [],
                    "resource_point": {},
                    "path_ids": ["flow:1"],
                    "guard_decision": {},
                    "bound_decision": {},
                    "release_decision": {},
                    "assertions": [],
                    "verdict": "static_unknown",
                    "reason_codes": [],
                    "assumptions": [],
                    "coverage_gaps": [],
                    "unresolved_facts": [],
                    "suggested_follow_up_measurements": [],
                },
                {
                    "entry_id": {"entry:1"},
                    "growth_id": {"growth:1"},
                    "path_id": {"flow:1"},
                },
            ),
        }
        for artifact_name, (id_only, minimum, known_ids) in cases.items():
            with self.subTest(artifact_name=artifact_name):
                with self.assertRaises(AnalyzerError) as raised:
                    validate_references(artifact_name, [id_only], known_ids)
                self.assertEqual(raised.exception.code, "ARTIFACT_REQUIRED_FIELD_MISSING")
                validate_references(artifact_name, [minimum], known_ids)

    def test_lifecycle_certificate_requires_p0_evidence_fields(self):
        record = {
            "certificate_id": "certificate:1",
            "entry_id": "entry:1",
            "growth_id": "growth:1",
            "path_ids": ["flow:1"],
            "assertions": [],
            "verdict": "static_unknown",
            "reason_codes": [],
            "assumptions": [],
            "coverage_gaps": [],
            "unresolved_facts": [],
        }
        known_ids = {
            "entry_id": {"entry:1"},
            "growth_id": {"growth:1"},
            "path_id": {"flow:1"},
        }
        with self.assertRaises(AnalyzerError) as raised:
            validate_references("lifecycle_certificates", [record], known_ids)
        self.assertEqual(raised.exception.code, "ARTIFACT_REQUIRED_FIELD_MISSING")
        record.update(
            {
                "attacker_inputs": [],
                "resource_point": {},
                "guard_decision": {},
                "bound_decision": {},
                "release_decision": {},
                "suggested_follow_up_measurements": [],
            }
        )
        validate_references("lifecycle_certificates", [record], known_ids)

    def test_reference_validator_rejects_dangling_upstream_identifiers(self):
        identity = {
            "entry_id": "entry:missing",
            "growth_id": "growth:known",
            "attacker_control": {"target": "size", "source": "a", "sink": "b"},
            "call_path": ["fixture.Handler.handle"],
            "phase_sequence": ["in_handler", "growth"],
            "confidence": "proven", "flow_kind": "data_flow", "coverage_status": "complete", "coverage_note": "normalized",
        }
        semantic_identity = {
            key: identity[key]
            for key in (
                "entry_id", "growth_id", "attacker_control", "call_path",
                "phase_sequence", "confidence",
            )
        }
        record = {"path_id": stable_identifier("flow", semantic_identity), **identity}
        with self.assertRaises(AnalyzerError) as raised:
            validate_references(
                "flow_proofs",
                [record],
                known_ids={"entry_id": {"entry:known"}, "growth_id": {"growth:known"}},
            )
        self.assertEqual(raised.exception.code, "ANALYSIS_DANGLING_FACT_REFERENCE")

    def test_reusable_stage_rejects_missing_empty_or_non_list_artifacts(self):
        fingerprint = self._fingerprint()
        for artifacts in (None, [], {"path": "entry_facts.jsonl", "sha256": "digest"}):
            run = self._completed_run(fingerprint, artifacts)
            if artifacts is None:
                del run["stages"]["entries"]["artifacts"]
            self.assertFalse(reusable_stage(run, "entries", fingerprint, Path(".")))

    def test_metadata_serialization_makes_absolute_output_artifact_reusable(self):
        record = {
            "entry_id": "entry:1",
            "framework": "servlet",
            "protocol": "http",
            "handler": {"callable": "Handler.run", "file": "Handler.java", "start_line": 1},
            "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler.handle", "file": "fixture/Handler.java", "start_line": 1},
            "registration_pattern_id": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
            "route_or_event": "/",
            "auth_context": "unknown",
            "attacker_inputs": [],
            "materialization_phase": "unknown",
        }
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "run"
            output_root.mkdir()
            ref = write_jsonl_atomically(
                output_root / "facts" / "entry_facts.jsonl",
                "entry_facts",
                [record],
                known_ids={},
            )
            metadata_ref = artifact_ref_for_metadata(ref, output_root)
            self.assertEqual(metadata_ref["path"], "facts/entry_facts.jsonl")
            fingerprint = self._fingerprint()
            run = self._completed_run(fingerprint, [metadata_ref])
            self.assertTrue(reusable_stage(run, "entries", fingerprint, output_root))

    def test_reusable_stage_verifies_actual_jsonl_record_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "records.jsonl"
            artifact.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
            fingerprint = self._fingerprint()
            metadata = {"path": artifact.name, "sha256": file_sha256(artifact), "record_count": 999, "schema_version": SCHEMA_VERSION}
            self.assertFalse(reusable_stage(self._completed_run(fingerprint, [metadata]), "entries", fingerprint, root))

    def test_reusable_stage_requires_complete_artifact_metadata(self):
        record = {
            "entry_id": "entry:1",
            "framework": "servlet",
            "protocol": "http",
            "handler": {"callable": "Handler.run", "file": "Handler.java", "start_line": 1},
            "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler.handle", "file": "fixture/Handler.java", "start_line": 1},
            "registration_pattern_id": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
            "route_or_event": "/",
            "auth_context": "unknown",
            "attacker_inputs": [],
            "materialization_phase": "unknown",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = write_jsonl_atomically(root / "entry_facts.jsonl", "entry_facts", [record], {})
            metadata = artifact_ref_for_metadata(ref, root)
            fingerprint = self._fingerprint()
            for field, invalid in (
                ("schema_version", None),
                ("schema_version", "wrong"),
                ("record_count", None),
                ("record_count", True),
                ("record_count", -1),
            ):
                with self.subTest(field=field, invalid=invalid):
                    malformed = {**metadata, field: invalid}
                    run = self._completed_run(fingerprint, [malformed])
                    self.assertFalse(reusable_stage(run, "entries", fingerprint, root))
            self.assertTrue(reusable_stage(self._completed_run(fingerprint, [metadata]), "entries", fingerprint, root))

    def test_reusable_stage_returns_false_when_hash_io_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "entry_facts.jsonl"
            artifact.write_text("content", encoding="utf-8")
            fingerprint = self._fingerprint()
            run = self._completed_run(
                fingerprint,
                [{"path": artifact.name, "sha256": file_sha256(artifact)}],
            )
            with mock.patch(
                "dosweb.artifacts.metadata.file_sha256", side_effect=OSError("read failed")
            ):
                self.assertFalse(reusable_stage(run, "entries", fingerprint, root))

    def test_reusable_stage_rejects_absolute_artifact_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            external = Path(tmp) / "external.jsonl"
            external.write_text("content", encoding="utf-8")
            fingerprint = self._fingerprint()
            run = self._completed_run(
                fingerprint,
                [{"path": str(external), "sha256": file_sha256(external)}],
            )
            self.assertFalse(reusable_stage(run, "entries", fingerprint, root))

    def test_reusable_stage_rejects_parent_traversal_artifact_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            external = Path(tmp) / "external.jsonl"
            external.write_text("content", encoding="utf-8")
            fingerprint = self._fingerprint()
            run = self._completed_run(
                fingerprint,
                [{"path": "../external.jsonl", "sha256": file_sha256(external)}],
            )
            self.assertFalse(reusable_stage(run, "entries", fingerprint, root))

    def test_resume_rejects_changed_upstream_hash_and_invalidates_downstream(self):
        fingerprint = StageFingerprint(
            schema_version="2.0",
            tool_version="0.1.0",
            implementation_version="entries-v1",
            database_fingerprint="db-a",
            query_pack_hash="ql-a",
            config_hash="config-a",
            upstream_hashes={"input": "old"},
        )
        run = {
            "stages": {
                "entries": {"status": "completed", "fingerprint": fingerprint.to_dict()},
                "growth": {"status": "completed"},
                "flows": {"status": "completed"},
            }
        }
        changed = StageFingerprint(**{**fingerprint.__dict__, "upstream_hashes": {"input": "new"}})
        self.assertFalse(reusable_stage(run, "entries", changed, Path(".")))
        invalidate_from(run, "entries", ["entries", "growth", "flows"])
        self.assertEqual(run["stages"]["entries"]["status"], "invalid")
        self.assertEqual(run["stages"]["growth"]["status"], "invalid")
