from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dosweb.artifacts.identifiers import sha256_canonical_json, stable_identifier
from dosweb.artifacts.schemas import SCHEMA_VERSION, validate_records
from dosweb.batch.aggregate import P0_ARTIFACTS, STAGES, aggregate, validate_manifest
from dosweb.growth.completeness import (
    CandidateDisposition,
    CandidateEntryLink,
    CandidateNegativeProof,
)


def canonical_fixture() -> tuple[dict, dict, dict]:
    semantic = {"index": 1, "name": "owner/repo", "fingerprint_type": "git-commit", "fingerprint": "a" * 40, "source_path": "sources/owner__repo", "database_path": "databases/owner__repo"}
    identity = {"target_id": stable_identifier("target", semantic), **semantic, "slug": "owner__repo"}
    capability = {"provider_eligible": False, "public_source_url": None, "attestation": "unavailable", "reason": None}
    item = {"target_id": identity["target_id"], "identity": identity, "output_path": "results/targets/001-owner__repo", "capability": capability, "initial_state": "queued"}
    unsigned = {"schema_version": 1, "tool_version": "dosweb-v2", "batch_schema_version": "java-web-dos-batch-v1", "run_id": "run-1", "mode": "entries", "output_root": "results", "inventory_digest": "b" * 64, "provider": {}, "analysis_mode": "exploratory_entries", "query_failure_policy": "coverage_gap", "targets": [item]}
    digest = sha256_canonical_json(unsigned)
    plan = {**unsigned, "plan_id": f"plan:{digest[:24]}", "plan_digest": digest}
    state = {"schema_version": 1, "batch_id": plan["plan_id"], "mode": "entries", "status": "completed", "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00", "targets": {item["target_id"]: {"target_id": item["target_id"], "state": "completed", "status": "completed", "attempt": 1}}}
    return item, plan, state


class BatchAggregationContractTests(unittest.TestCase):
    def _candidate_reference_status(self, records: dict[str, list[dict]]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item, plan, state = canonical_fixture()
            target = root / "targets" / "001-owner__repo"
            target.mkdir(parents=True)
            (target / ".stage-manifests").mkdir()
            (root / "manifest.normalized.jsonl").write_text(
                json.dumps(item) + "\n", encoding="utf-8"
            )
            (root / "batch_plan.json").write_text(
                json.dumps(plan), encoding="utf-8"
            )
            (root / "batch_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            (target / "batch_target.json").write_text(
                json.dumps(
                    {
                        "plan_id": plan["plan_id"],
                        "plan_digest": plan["plan_digest"],
                        "run_id": "run-1",
                        "mode": "entries",
                        "analysis_mode": "exploratory_entries",
                        "query_failure_policy": "coverage_gap",
                        "target": item,
                    }
                ),
                encoding="utf-8",
            )
            artifacts = {}
            for name in P0_ARTIFACTS:
                if name.endswith(".jsonl"):
                    data = "".join(
                        json.dumps(row) + "\n" for row in records.get(name, [])
                    ).encode()
                else:
                    data = ("{}\n" if name.endswith(".json") else "report\n").encode()
                path = target / name
                path.write_bytes(data)
                artifacts[name] = {
                    "path": name,
                    "schema_version": SCHEMA_VERSION,
                    "sha256": __import__("hashlib").sha256(data).hexdigest(),
                    "record_count": data.count(b"\n"),
                    "byte_count": len(data),
                }
            stage_files = {
                "entries": {
                    "configuration_coverage.json", "coverage.json",
                    "descriptor_coverage.json", "entry_facts.jsonl",
                    "entry_gap_facts.jsonl", "entry_interposition_facts.jsonl",
                    "entry_security_facts.jsonl", "modeled_configuration.jsonl",
                },
                "growth": {
                    "amplification_decisions.jsonl", "auth_contracts.jsonl",
                    "candidate_dispositions.jsonl", "candidate_entry_links.jsonl",
                    "candidate_negative_proofs.jsonl", "growth_candidates.jsonl",
                    "growth_static_facts.jsonl", "growth_contracts.jsonl",
                    "llm_audit.private.jsonl",
                    "reachability_decisions.jsonl", "repeatability_decisions.jsonl",
                    "verified_growth.jsonl",
                },
                "flows": {"flow_proofs.jsonl"},
                "lifecycle": {
                    "bound_candidates.jsonl", "guard_candidates.jsonl",
                    "lifecycle_coverage.jsonl", "lifecycle_evidence.jsonl",
                    "lifecycle_results.jsonl", "lifecycle_summaries.jsonl",
                    "resource_lifecycle_bindings.jsonl",
                    "release_candidates.jsonl",
                },
                "conclude": {
                    "finding_families.jsonl", "static_findings.jsonl",
                    "lifecycle_certificates.jsonl",
                },
                "report": {"summary.json", "report.md"},
            }
            stages = {}
            for stage in STAGES:
                entries = [
                    artifacts[name]
                    for name in P0_ARTIFACTS
                    if name in stage_files[stage]
                ]
                manifest = {
                    "stage": stage,
                    "status": "completed",
                    "artifacts": entries,
                    "output_hash": __import__("hashlib").sha256(
                        json.dumps(
                            entries, separators=(",", ":"), sort_keys=True
                        ).encode()
                    ).hexdigest(),
                }
                stages[stage] = manifest
                (target / ".stage-manifests" / f"{stage}.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
            (target / "run.json").write_text(
                json.dumps({"run_id": "run-1", "status": "completed", "stages": stages}),
                encoding="utf-8",
            )
            aggregate(root, format="p0")
            return json.loads(
                (root / "aggregate_status.jsonl").read_text().splitlines()[0]
            )

    @staticmethod
    def _growth(growth_id: str, evidence_id: str) -> dict:
        resource = {
            "dimension": "bytes",
            "receiver": f"fixture.{growth_id}",
            "field_path": "allocation",
        }
        return {
            "growth_id": growth_id,
            "site": {"file": "Handler.java", "start_line": 2},
            "kind": "direct_allocation",
            "operation": "allocate",
            "resource_point": {
                "resource_id": stable_identifier("resource", resource),
                **resource,
            },
            "demand_inputs": [{"name": "size", "role": "size"}],
            "escape_scope": "request",
            "candidate_evidence": [evidence_id],
            "coverage_status": "complete",
            "coverage_notes": ["fixture"],
        }

    @staticmethod
    def _entry(entry_id: str) -> dict:
        return {
            "entry_id": entry_id,
            "framework": "spring_mvc",
            "protocol": "http",
            "handler": {
                "callable": "fixture.Handler.handle",
                "file": "Handler.java",
                "start_line": 1,
            },
            "registration": {
                "kind": "annotation_mapping",
                "callable": "fixture.Handler.handle",
                "file": "Handler.java",
                "start_line": 1,
            },
            "registration_pattern_id": "entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
            "route_or_event": "/fixture",
            "auth_context": "unknown",
            "attacker_inputs": [],
            "materialization_phase": "in_handler",
        }

    @staticmethod
    def _rejected_disposition(growth_id: str, proof: dict) -> dict:
        return CandidateDisposition.create(
            growth_id,
            "rejected",
            canonical_entry_id="",
            local_growth_status="rejected",
            association_status="missing",
            link_ids=(),
            evidence_ids=(proof["negative_proof_id"],),
            negative_proof_ids=(proof["negative_proof_id"],),
            reason_codes=("MATURATION_SOURCE_PROVEN_NEGATIVE",),
        ).to_dict()

    @staticmethod
    def _link(growth_id: str, entry_id: str, status: str = "complete") -> dict:
        return CandidateEntryLink.create(
            growth_id,
            entry_id,
            status,
            ("fact:association",),
            ("ASSOCIATION_FIXTURE",),
        ).to_dict()

    @staticmethod
    def _eligible_disposition(
        growth_id: str, entry_id: str, link: dict
    ) -> dict:
        return CandidateDisposition.create(
            growth_id,
            "formal_eligible",
            canonical_entry_id=entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link["link_id"],),
            evidence_ids=("fact:growth", link["link_id"]),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        ).to_dict()

    @staticmethod
    def _unresolved_disposition(growth_id: str, evidence_id: str) -> dict:
        return CandidateDisposition.create(
            growth_id,
            "inventory_unresolved",
            canonical_entry_id="",
            local_growth_status="unknown",
            association_status="missing",
            link_ids=(),
            evidence_ids=(evidence_id,),
            negative_proof_ids=(),
            reason_codes=("MATURATION_UNRESOLVED_FIXTURE",),
        ).to_dict()

    @staticmethod
    def _linked_inventory_disposition(
        growth_id: str,
        *,
        association_status: str,
        canonical_entry_id: str,
        links: tuple[dict, ...],
    ) -> dict:
        return CandidateDisposition.create(
            growth_id,
            "inventory_unresolved",
            canonical_entry_id=canonical_entry_id,
            local_growth_status="unknown",
            association_status=association_status,
            link_ids=tuple(link["link_id"] for link in links),
            evidence_ids=(
                tuple(link["link_id"] for link in links)
                or ("fact:inventory",)
            ),
            negative_proof_ids=(),
            reason_codes=("MATURATION_UNRESOLVED_FIXTURE",),
        ).to_dict()

    def test_p0_requires_exactly_one_disposition_for_every_raw_growth_candidate(self) -> None:
        growth = self._growth("growth:first", "fact:first")
        first = self._unresolved_disposition("growth:first", "fact:first")
        phantom = self._unresolved_disposition("growth:phantom", "fact:phantom")
        cases = {
            "missing": {
                "growth_candidates.jsonl": [growth],
                "candidate_dispositions.jsonl": [],
            },
            "duplicate": {
                "growth_candidates.jsonl": [growth],
                "candidate_dispositions.jsonl": [first, first],
            },
            "phantom": {
                "growth_candidates.jsonl": [growth],
                "candidate_dispositions.jsonl": [first, phantom],
            },
        }
        for name, records in cases.items():
            with self.subTest(name=name):
                status = self._candidate_reference_status(records)
                self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_accepts_same_growth_typed_negative_proof(self) -> None:
        proof = CandidateNegativeProof.create(
            "growth:first",
            "server_controlled_source",
            evidence_ids=("fact:first",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        status = self._candidate_reference_status(
            {
                "growth_candidates.jsonl": [self._growth("growth:first", "fact:first")],
                "candidate_negative_proofs.jsonl": [proof],
                "candidate_dispositions.jsonl": [
                    self._rejected_disposition("growth:first", proof)
                ],
            }
        )
        self.assertEqual("completed", status["status"], status)

    def test_p0_reference_validation_accepts_empty_security_evidence_for_known_entry(self) -> None:
        status = self._candidate_reference_status(
            {
                "entry_facts.jsonl": [self._entry("entry:first")],
                "auth_contracts.jsonl": [
                    {
                        "auth_contract_id": "auth_contract:first",
                        "entry_id": "entry:first",
                        "auth_context": "unknown",
                        "evidence_ids": [],
                        "assumptions": ["fixture"],
                        "confidence": "low",
                    }
                ],
            }
        )
        self.assertEqual("completed", status["status"], status)

    def test_p0_reference_validation_rejects_cross_growth_negative_proof(self) -> None:
        proof = CandidateNegativeProof.create(
            "growth:first",
            "server_controlled_source",
            evidence_ids=("fact:first",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        status = self._candidate_reference_status(
            {
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first"),
                    self._growth("growth:second", "fact:second"),
                ],
                "candidate_negative_proofs.jsonl": [proof],
                "candidate_dispositions.jsonl": [
                    self._rejected_disposition("growth:second", proof)
                ],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_rejects_cross_growth_proof_evidence(self) -> None:
        proof = CandidateNegativeProof.create(
            "growth:first",
            "server_controlled_source",
            evidence_ids=("fact:second",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        status = self._candidate_reference_status(
            {
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first"),
                    self._growth("growth:second", "fact:second"),
                ],
                "candidate_negative_proofs.jsonl": [proof],
                "candidate_dispositions.jsonl": [
                    self._rejected_disposition("growth:first", proof)
                ],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_rejects_wrong_growth_candidate_link(self) -> None:
        link = self._link("growth:second", "entry:first")
        status = self._candidate_reference_status(
            {
                "entry_facts.jsonl": [self._entry("entry:first")],
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first"),
                    self._growth("growth:second", "fact:second"),
                ],
                "candidate_entry_links.jsonl": [link],
                "candidate_dispositions.jsonl": [
                    self._eligible_disposition(
                        "growth:first", "entry:first", link
                    )
                ],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_accepts_exact_candidate_link_ownership(self) -> None:
        link = self._link("growth:first", "entry:first")
        status = self._candidate_reference_status(
            {
                "entry_facts.jsonl": [self._entry("entry:first")],
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first")
                ],
                "candidate_entry_links.jsonl": [link],
                "candidate_dispositions.jsonl": [
                    self._eligible_disposition(
                        "growth:first", "entry:first", link
                    )
                ],
            }
        )
        self.assertEqual("completed", status["status"], status)

    def test_p0_rejects_candidate_link_semantic_tamper_with_valid_disposition_id(
        self,
    ) -> None:
        original = self._link("growth:first", "entry:first", "complete")
        cases = {
            "status": {**original, "status": "partial"},
            "evidence": {
                **original,
                "evidence_ids": sorted(
                    [*original["evidence_ids"], "fact:tampered"]
                ),
            },
            "reason": {
                **original,
                "reason_codes": sorted(
                    [*original["reason_codes"], "ASSOCIATION_TAMPERED"]
                ),
            },
        }
        for name, link in cases.items():
            with self.subTest(name=name):
                association_status = link["status"]
                disposition = self._linked_inventory_disposition(
                    "growth:first",
                    association_status=association_status,
                    canonical_entry_id="entry:first",
                    links=(link,),
                )
                disposition_semantic = {
                    key: value
                    for key, value in disposition.items()
                    if key != "disposition_id"
                }
                self.assertEqual(
                    disposition["disposition_id"],
                    stable_identifier("disposition", disposition_semantic),
                )
                validate_records(
                    "candidate_dispositions", [disposition]
                )
                status = self._candidate_reference_status(
                    {
                        "entry_facts.jsonl": [self._entry("entry:first")],
                        "growth_candidates.jsonl": [
                            self._growth("growth:first", "fact:first")
                        ],
                        "candidate_entry_links.jsonl": [link],
                        "candidate_dispositions.jsonl": [disposition],
                    }
                )
                self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_rejects_orphan_link_beside_unresolved_disposition(
        self,
    ) -> None:
        link = self._link("growth:first", "entry:first", "partial")
        status = self._candidate_reference_status(
            {
                "entry_facts.jsonl": [self._entry("entry:first")],
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first")
                ],
                "candidate_entry_links.jsonl": [link],
                "candidate_dispositions.jsonl": [
                    self._unresolved_disposition(
                        "growth:first", "fact:first"
                    )
                ],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_reconciles_noneligible_link_ownership(
        self,
    ) -> None:
        first_growth = self._growth("growth:first", "fact:first")
        second_growth = self._growth("growth:second", "fact:second")
        first_entry = self._entry("entry:first")
        second_entry = self._entry("entry:second")

        wrong_growth_link = self._link(
            "growth:second", "entry:first", "partial"
        )
        wrong_entry_link = self._link(
            "growth:first", "entry:second", "partial"
        )
        wrong_status_link = self._link(
            "growth:first", "entry:first", "complete"
        )
        duplicate_link = self._link(
            "growth:first", "entry:first", "partial"
        )
        cases = {
            "wrong_growth": {
                "growth_candidates.jsonl": [first_growth, second_growth],
                "candidate_entry_links.jsonl": [wrong_growth_link],
                "candidate_dispositions.jsonl": [
                    self._linked_inventory_disposition(
                        "growth:first",
                        association_status="partial",
                        canonical_entry_id="entry:first",
                        links=(wrong_growth_link,),
                    ),
                    self._unresolved_disposition(
                        "growth:second", "fact:second"
                    ),
                ],
            },
            "wrong_entry": {
                "growth_candidates.jsonl": [first_growth],
                "candidate_entry_links.jsonl": [wrong_entry_link],
                "candidate_dispositions.jsonl": [
                    self._linked_inventory_disposition(
                        "growth:first",
                        association_status="partial",
                        canonical_entry_id="entry:first",
                        links=(wrong_entry_link,),
                    )
                ],
            },
            "wrong_status": {
                "growth_candidates.jsonl": [first_growth],
                "candidate_entry_links.jsonl": [wrong_status_link],
                "candidate_dispositions.jsonl": [
                    self._linked_inventory_disposition(
                        "growth:first",
                        association_status="partial",
                        canonical_entry_id="entry:first",
                        links=(wrong_status_link,),
                    )
                ],
            },
            "duplicate_ownership": {
                "growth_candidates.jsonl": [first_growth, second_growth],
                "candidate_entry_links.jsonl": [duplicate_link],
                "candidate_dispositions.jsonl": [
                    self._linked_inventory_disposition(
                        "growth:first",
                        association_status="partial",
                        canonical_entry_id="entry:first",
                        links=(duplicate_link,),
                    ),
                    self._linked_inventory_disposition(
                        "growth:second",
                        association_status="ambiguous",
                        canonical_entry_id="",
                        links=(duplicate_link,),
                    ),
                ],
            },
        }
        for name, records in cases.items():
            with self.subTest(name=name):
                records["entry_facts.jsonl"] = [first_entry, second_entry]
                status = self._candidate_reference_status(records)
                self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_accepts_noneligible_production_link_shapes(
        self,
    ) -> None:
        first_entry = self._entry("entry:first")
        second_entry = self._entry("entry:second")
        partial_link = self._link(
            "growth:partial", "entry:first", "partial"
        )
        ambiguous_links = (
            self._link("growth:ambiguous", "entry:first", "partial"),
            self._link("growth:ambiguous", "entry:second", "complete"),
        )
        status = self._candidate_reference_status(
            {
                "entry_facts.jsonl": [first_entry, second_entry],
                "growth_candidates.jsonl": [
                    self._growth("growth:partial", "fact:partial"),
                    self._growth("growth:ambiguous", "fact:ambiguous"),
                ],
                "candidate_entry_links.jsonl": [
                    partial_link,
                    *ambiguous_links,
                ],
                "candidate_dispositions.jsonl": [
                    self._linked_inventory_disposition(
                        "growth:partial",
                        association_status="partial",
                        canonical_entry_id="entry:first",
                        links=(partial_link,),
                    ),
                    self._linked_inventory_disposition(
                        "growth:ambiguous",
                        association_status="ambiguous",
                        canonical_entry_id="",
                        links=ambiguous_links,
                    ),
                ],
            }
        )
        self.assertEqual("completed", status["status"], status)

    def test_p0_reference_validation_rejects_noncanonical_association_shapes(
        self,
    ) -> None:
        first_link = self._link(
            "growth:first", "entry:first", "partial"
        )
        second_link = self._link(
            "growth:first", "entry:second", "partial"
        )
        cases = {
            "missing_with_link": self._linked_inventory_disposition(
                "growth:first",
                association_status="missing",
                canonical_entry_id="",
                links=(first_link,),
            ),
            "missing_with_canonical_entry": self._linked_inventory_disposition(
                "growth:first",
                association_status="missing",
                canonical_entry_id="entry:first",
                links=(),
            ),
            "ambiguous_with_sole_link": self._linked_inventory_disposition(
                "growth:first",
                association_status="ambiguous",
                canonical_entry_id="",
                links=(first_link,),
            ),
            "ambiguous_with_canonical_entry": self._linked_inventory_disposition(
                "growth:first",
                association_status="ambiguous",
                canonical_entry_id="entry:first",
                links=(first_link, second_link),
            ),
            "partial_with_multiple_links": self._linked_inventory_disposition(
                "growth:first",
                association_status="partial",
                canonical_entry_id="entry:first",
                links=(first_link, second_link),
            ),
        }
        for name, disposition in cases.items():
            with self.subTest(name=name):
                link_ids = set(disposition["link_ids"])
                links = [
                    link
                    for link in (first_link, second_link)
                    if link["link_id"] in link_ids
                ]
                status = self._candidate_reference_status(
                    {
                        "entry_facts.jsonl": [
                            self._entry("entry:first"),
                            self._entry("entry:second"),
                        ],
                        "growth_candidates.jsonl": [
                            self._growth("growth:first", "fact:first")
                        ],
                        "candidate_entry_links.jsonl": links,
                        "candidate_dispositions.jsonl": [disposition],
                    }
                )
                self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_rejects_partial_link_masquerading_as_formal(self) -> None:
        link = self._link("growth:first", "entry:first", "partial")
        status = self._candidate_reference_status(
            {
                "entry_facts.jsonl": [self._entry("entry:first")],
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first")
                ],
                "candidate_entry_links.jsonl": [link],
                "candidate_dispositions.jsonl": [
                    self._eligible_disposition(
                        "growth:first", "entry:first", link
                    )
                ],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_rejects_wrong_entry_candidate_link(self) -> None:
        link = self._link("growth:first", "entry:second")
        status = self._candidate_reference_status(
            {
                "entry_facts.jsonl": [
                    self._entry("entry:first"),
                    self._entry("entry:second"),
                ],
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first")
                ],
                "candidate_entry_links.jsonl": [link],
                "candidate_dispositions.jsonl": [
                    self._eligible_disposition(
                        "growth:first", "entry:first", link
                    )
                ],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_rejects_extra_undeclared_negative_proof_evidence(self) -> None:
        growth = self._growth("growth:first", "fact:first")
        growth["candidate_evidence"] = ["fact:first", "fact:second"]
        first = CandidateNegativeProof.create(
            "growth:first",
            "server_controlled_source",
            evidence_ids=("fact:first",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        second = CandidateNegativeProof.create(
            "growth:first",
            "non_retained_owner",
            evidence_ids=("fact:second",),
            reason_codes=("NEGATIVE_NON_RETAINED_OWNER",),
        ).to_dict()
        disposition = self._rejected_disposition("growth:first", first)
        disposition["evidence_ids"] = sorted(
            [first["negative_proof_id"], second["negative_proof_id"]]
        )
        disposition["disposition_id"] = stable_identifier(
            "disposition",
            {
                key: value
                for key, value in disposition.items()
                if key != "disposition_id"
            },
        )
        status = self._candidate_reference_status(
            {
                "growth_candidates.jsonl": [growth],
                "candidate_negative_proofs.jsonl": [first, second],
                "candidate_dispositions.jsonl": [disposition],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_rejects_missing_negative_proof_evidence(self) -> None:
        proof = CandidateNegativeProof.create(
            "growth:first",
            "server_controlled_source",
            evidence_ids=("fact:first",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        disposition = self._rejected_disposition("growth:first", proof)
        disposition["evidence_ids"] = ["fact:ordinary"]
        semantic = {
            key: value
            for key, value in disposition.items()
            if key != "disposition_id"
        }
        disposition["disposition_id"] = stable_identifier(
            "disposition", semantic
        )
        status = self._candidate_reference_status(
            {
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first")
                ],
                "candidate_negative_proofs.jsonl": [proof],
                "candidate_dispositions.jsonl": [disposition],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_rejects_cross_growth_undeclared_proof_evidence(self) -> None:
        first = CandidateNegativeProof.create(
            "growth:first",
            "server_controlled_source",
            evidence_ids=("fact:first",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        second = CandidateNegativeProof.create(
            "growth:second",
            "server_controlled_source",
            evidence_ids=("fact:second",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        disposition = self._rejected_disposition("growth:first", first)
        disposition["evidence_ids"] = sorted(
            [first["negative_proof_id"], second["negative_proof_id"]]
        )
        disposition["disposition_id"] = stable_identifier(
            "disposition",
            {
                key: value
                for key, value in disposition.items()
                if key != "disposition_id"
            },
        )
        status = self._candidate_reference_status(
            {
                "growth_candidates.jsonl": [
                    self._growth("growth:first", "fact:first"),
                    self._growth("growth:second", "fact:second"),
                ],
                "candidate_negative_proofs.jsonl": [first, second],
                "candidate_dispositions.jsonl": [disposition],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_rejects_oracle_shaped_proof_evidence(self) -> None:
        proof = CandidateNegativeProof.create(
            "growth:first",
            "server_controlled_source",
            evidence_ids=("fact:oracle_label",),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        ).to_dict()
        status = self._candidate_reference_status(
            {
                "growth_candidates.jsonl": [self._growth("growth:first", "fact:first")],
                "candidate_negative_proofs.jsonl": [proof],
                "candidate_dispositions.jsonl": [
                    self._rejected_disposition("growth:first", proof)
                ],
            }
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_reference_validation_accounts_malformed_growth_evidence_without_crashing(self) -> None:
        malformed = self._growth("growth:first", "fact:first")
        malformed["candidate_evidence"] = None
        status = self._candidate_reference_status(
            {"growth_candidates.jsonl": [malformed]}
        )
        self.assertEqual("malformed", status["status"], status)

    def test_p0_artifact_contract_matches_current_production_files(self) -> None:
        self.assertEqual(set(P0_ARTIFACTS), {
            "configuration_coverage.json", "coverage.json", "descriptor_coverage.json",
            "entry_facts.jsonl", "entry_gap_facts.jsonl", "entry_interposition_facts.jsonl",
            "entry_security_facts.jsonl", "modeled_configuration.jsonl",
            "amplification_decisions.jsonl", "auth_contracts.jsonl",
            "candidate_dispositions.jsonl", "candidate_entry_links.jsonl",
            "candidate_negative_proofs.jsonl",
            "growth_candidates.jsonl", "growth_static_facts.jsonl",
            "growth_contracts.jsonl", "llm_audit.private.jsonl",
            "reachability_decisions.jsonl", "repeatability_decisions.jsonl",
            "verified_growth.jsonl", "flow_proofs.jsonl", "bound_candidates.jsonl",
            "guard_candidates.jsonl", "lifecycle_coverage.jsonl", "lifecycle_evidence.jsonl",
            "lifecycle_results.jsonl", "lifecycle_summaries.jsonl",
            "resource_lifecycle_bindings.jsonl",
            "release_candidates.jsonl",
            "finding_families.jsonl", "lifecycle_certificates.jsonl",
            "static_findings.jsonl", "report.md", "summary.json",
        })

    def test_p0_manifest_requires_nested_target_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.normalized.jsonl"
            manifest.write_text(json.dumps({"slug": "legacy"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "P0 manifest requires nested identity"):
                validate_manifest([{"slug": "legacy"}], manifest, "p0")

    def test_p0_requires_plan_and_authoritative_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.normalized.jsonl").write_text(
                json.dumps({
                    "target_id": "target:one",
                    "identity": {"name": "owner/repo", "slug": "owner__repo"},
                    "output_path": "targets/one",
                    "capability": {},
                    "initial_state": "queued",
                }) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "batch_plan.json and batch_state.json"):
                aggregate(root, format="p0")

    def test_valid_normative_aggregation_counts_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item, plan, state = canonical_fixture()
            target = root / "targets" / "001-owner__repo"
            target.mkdir(parents=True)
            (target / ".stage-manifests").mkdir()
            (root / "manifest.normalized.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
            (root / "batch_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            (root / "batch_state.json").write_text(json.dumps(state), encoding="utf-8")
            (target / "batch_target.json").write_text(json.dumps({"plan_id": plan["plan_id"], "plan_digest": plan["plan_digest"], "run_id": "run-1", "mode": "entries", "analysis_mode": "exploratory_entries", "query_failure_policy": "coverage_gap", "target": item}), encoding="utf-8")
            entry_id, growth_id = "entry:fixture", "growth:fixture"
            resource = {"resource_id": stable_identifier("resource", {"dimension": "bytes", "receiver": "fixture.Handler", "field_path": "buffer"}), "dimension": "bytes", "receiver": "fixture.Handler", "field_path": "buffer"}
            entry = {"entry_id": entry_id, "framework": "servlet", "protocol": "http", "handler": {"callable": "fixture.Handler", "file": "Handler.java", "start_line": 1}, "registration": {"kind": "annotation_mapping", "callable": "fixture.Handler", "file": "Handler.java", "start_line": 1}, "registration_pattern_id": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping", "route_or_event": "/fixture", "auth_context": "unauthenticated", "attacker_inputs": [], "materialization_phase": "in_handler"}
            growth = {"growth_id": growth_id, "site": {"file": "Handler.java", "start_line": 2}, "kind": "direct_allocation", "operation": "allocate", "resource_point": resource, "demand_inputs": [{"name": "size", "role": "size"}], "escape_scope": "request", "candidate_evidence": ["fact:fixture"], "coverage_status": "complete", "coverage_notes": ["fixture"]}
            flow_id = stable_identifier("flow", {"entry_id": entry_id, "growth_id": growth_id, "attacker_control": {"target": "size", "source": "request", "sink": "allocate"}, "call_path": ["fixture.Handler"], "phase_sequence": ["handler"], "confidence": "proven"})
            flow = {"path_id": flow_id, "entry_id": entry_id, "growth_id": growth_id, "attacker_control": {"target": "size", "source": "request", "sink": "allocate"}, "call_path": ["fixture.Handler"], "phase_sequence": ["handler"], "confidence": "proven", "flow_kind": "direct", "coverage_status": "complete", "coverage_note": "fixture"}
            certificate_id = "certificate:fixture"
            certificate = {"certificate_id": certificate_id, "entry_id": entry_id, "growth_id": growth_id, "attacker_inputs": [], "resource_point": resource, "path_ids": [flow_id], "guard_decision": {}, "bound_decision": {}, "release_decision": {}, "resource_lifecycle_decisions": [], "assertions": [], "verdict": "static_unknown", "reason_codes": [], "assumptions": [], "coverage_gaps": [], "unresolved_facts": [], "suggested_follow_up_measurements": []}
            family_semantic = {"verdict": "static_unknown", "priority": "P1", "primary_finding_id": "finding:fixture", "member_finding_ids": ["finding:fixture"], "member_certificate_ids": [certificate_id], "entry_ids": [entry_id], "growth_ids": [growth_id], "resource_id": resource["resource_id"], "reachability_status": "unknown", "amplification_class": "large_single_request", "reason_codes": []}
            family = {"family_id": stable_identifier("family", family_semantic), **family_semantic}
            records = {"entry_facts.jsonl": [entry], "growth_candidates.jsonl": [growth], "candidate_dispositions.jsonl": [self._unresolved_disposition(growth_id, "fact:fixture")], "flow_proofs.jsonl": [flow], "static_findings.jsonl": [{"finding_id": "finding:fixture", "certificate_id": certificate_id, "entry_id": entry_id, "growth_id": growth_id, "verdict": "static_unknown", "reason_codes": []}], "finding_families.jsonl": [family], "lifecycle_certificates.jsonl": [certificate]}
            artifacts = {}
            for name in P0_ARTIFACTS:
                if name.endswith(".jsonl"):
                    data = ("".join(json.dumps(row) + "\n" for row in records.get(name, []))).encode()
                else:
                    data = ("{}\n" if name.endswith(".json") else "report\n").encode()
                path = target / name
                path.write_bytes(data)
                artifacts[name] = {"path": name, "schema_version": SCHEMA_VERSION, "sha256": __import__("hashlib").sha256(data).hexdigest(), "record_count": data.count(b"\n"), "byte_count": len(data)}
            stage_files = {
                "entries": {"configuration_coverage.json", "coverage.json", "descriptor_coverage.json", "entry_facts.jsonl", "entry_gap_facts.jsonl", "entry_interposition_facts.jsonl", "entry_security_facts.jsonl", "modeled_configuration.jsonl"},
                "growth": {"amplification_decisions.jsonl", "auth_contracts.jsonl", "candidate_dispositions.jsonl", "candidate_entry_links.jsonl", "candidate_negative_proofs.jsonl", "growth_candidates.jsonl", "growth_static_facts.jsonl", "growth_contracts.jsonl", "llm_audit.private.jsonl", "reachability_decisions.jsonl", "repeatability_decisions.jsonl", "verified_growth.jsonl"},
                "flows": {"flow_proofs.jsonl"},
                "lifecycle": {"bound_candidates.jsonl", "guard_candidates.jsonl", "lifecycle_coverage.jsonl", "lifecycle_evidence.jsonl", "lifecycle_results.jsonl", "lifecycle_summaries.jsonl", "resource_lifecycle_bindings.jsonl", "release_candidates.jsonl"},
                "conclude": {"finding_families.jsonl", "static_findings.jsonl", "lifecycle_certificates.jsonl"},
                "report": {"summary.json", "report.md"},
            }
            for stage in STAGES:
                names = [name for name in P0_ARTIFACTS if name in stage_files[stage]]
                entries = [artifacts[name] for name in names]
                manifest = {"stage": stage, "status": "completed", "artifacts": entries, "output_hash": __import__("hashlib").sha256(json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()).hexdigest()}
                (target / ".stage-manifests" / f"{stage}.json").write_text(json.dumps(manifest), encoding="utf-8")
            run = {"run_id": "run-1", "status": "completed", "stages": {stage: json.loads((target / ".stage-manifests" / f"{stage}.json").read_text()) for stage in STAGES}}
            run["stages"]["entries"]["metadata"] = {
                "query_count": 2,
                "skipped_query_count": 1,
                "entry_evidence_scan_truncated": False,
                "query_diagnostics": [{"code": "CODEQL_QUERY_FAILED", "query_name": "ServletEntries.ql"}],
            }
            (target / "run.json").write_text(json.dumps(run), encoding="utf-8")
            aggregate(root, format="p0")
            inventory = json.loads((root / "aggregate_inventory.json").read_text())
            self.assertEqual("completed", inventory["targets"][0]["status"], inventory["targets"][0])
            self.assertEqual(1, inventory["verdict_counts"].get("static_unknown", 0))
            aggregate_families = [
                json.loads(line)
                for line in (root / "aggregate_finding_families.jsonl").read_text().splitlines()
            ]
            self.assertEqual(aggregate_families[0]["family_id"], family["family_id"])
            self.assertEqual(
                inventory["targets"][0]["stage_metrics"]["entries"],
                {
                    "entry_evidence_scan_truncated": False,
                    "query_count": 2,
                    "query_diagnostic_count": 1,
                    "skipped_query_count": 1,
                },
            )

    def test_p0_binding_mismatch_is_accounted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item, plan, state = canonical_fixture()
            (root / "manifest.normalized.jsonl").write_text(json.dumps(item) + "\n")
            (root / "batch_plan.json").write_text(json.dumps(plan))
            (root / "batch_state.json").write_text(json.dumps(state))
            target = root / "targets" / "001-owner__repo"; target.mkdir(parents=True)
            (target / "batch_target.json").write_text(json.dumps({"run_id": "wrong", "target": item}))
            aggregate(root, format="p0")
            status = json.loads((root / "aggregate_status.jsonl").read_text().splitlines()[0])
            self.assertEqual("malformed", status["status"])

    def test_inventory_retains_authoritative_status_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item, plan, state = canonical_fixture()
            state["status"] = "completed_with_failures"
            target_id = item["target_id"]
            state["targets"][target_id]["state"] = "failed"
            state["targets"][target_id]["status"] = "failed"
            state["targets"][target_id]["error_code"] = "CONFIG_PUBLIC_SOURCE_UNVERIFIED"
            state["targets"][target_id]["error_message"] = "Public GitHub source could not be verified."
            (root / "manifest.normalized.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
            (root / "batch_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            (root / "batch_state.json").write_text(json.dumps(state), encoding="utf-8")
            aggregate(root, format="p0")
            inventory = json.loads((root / "aggregate_inventory.json").read_text())
            self.assertEqual(inventory["authoritative_status_counts"]["failed"], 1)
            self.assertIn("authoritative=failed", (root / "aggregate_gaps.md").read_text())

    def test_format_must_be_explicitly_normative_for_p0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "unknown aggregation format"):
                aggregate(root, format="normative")


if __name__ == "__main__":
    unittest.main()
