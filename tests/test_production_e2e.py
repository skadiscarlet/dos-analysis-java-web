from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from dosweb.entries import EntryFact, FrameworkCoverage
from dosweb.growth import (
    AmplificationDecision,
    CandidateDisposition,
    CandidateEntryLink,
    RepeatabilityDecision,
)
from dosweb.lifecycle import (
    BoundDecision,
    DecisionCheck,
    GuardDecision,
    LifecycleCoverage,
    ReleaseDecision,
)
from dosweb.pipeline import StageContext, StageFingerprint
from dosweb.reachability import ReachabilityDecision
from dosweb.production import build_production_pipeline
import dosweb.production as production
from tests.support.fixture_database import fixture_database
from tests.support.mock_deepseek import ScriptedDeepSeekTransport, StaticPublicVerifier, real_deepseek_factory
from tests.test_flow_verification import FlowVerificationTests


_ROOT = Path(__file__).resolve().parents[1]
_RUN = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql") or "/usr/bin/codeql"


@unittest.skipUnless(_RUN and Path(_CODEQL).exists(), "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with CodeQL available.")
class ProductionFixtureE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_root = (_ROOT / "tests/fixtures/p0/src/main/java").resolve()
        cls.database = fixture_database(str(cls.source_root))

    def _values(self, output: Path, *, database: object | None = None) -> dict[str, object]:
        database = database or self.database
        source_root = database.source_root
        return {
            "command": "analyze",
            "database": database.path,
            "output": output,
            "allow_remote_llm": True,
            "public_source_url": "https://github.com/example/dosweb-fixture",
            "source_commit_sha": "a" * 40,
            "source_checkout": source_root,
            "analysis_source_root": source_root,
            "base_url": "http://127.0.0.1:1/",
            "cache_dir": output / "cache/llm",
            "timeout_seconds": 30,
            "max_retries": 1,
        }

    def test_real_database_real_queries_real_client_cover_p0_scenarios_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            transport = ScriptedDeepSeekTransport()
            verifier = StaticPublicVerifier()
            factory = real_deepseek_factory(transport, verifier)
            pipeline = build_production_pipeline(
                self._values(output), environ={"DEEPSEEK_API_KEY": "fixture-key"},
                deepseek_client_factory=factory,
            )
            run = pipeline.run("analyze")
            self.assertEqual("completed", run["status"])
            expected = {
                "entry_facts.jsonl", "growth_candidates.jsonl", "candidate_entry_links.jsonl",
                "candidate_dispositions.jsonl", "candidate_negative_proofs.jsonl",
                "flow_proofs.jsonl", "lifecycle_results.jsonl",
                "lifecycle_coverage.jsonl", "lifecycle_certificates.jsonl", "static_findings.jsonl",
                "report.md", "summary.json", "llm_audit.private.jsonl",
            }
            self.assertTrue(expected.issubset({path.name for path in output.iterdir()}))
            self.assertEqual(0o600, (output / "llm_audit.private.jsonl").stat().st_mode & 0o777)
            audits = [json.loads(line) for line in (output / "llm_audit.private.jsonl").read_text().splitlines()]
            self.assertGreater(transport.request_count, 0)
            self.assertEqual(transport.request_count, len(audits))
            self.assertTrue(all(set(item) == {"audit_id", "contract_kind", "request_id", "normalized_prompt", "response_schema", "raw_response", "parsed_response", "settings", "attestation", "cache_hit"} for item in audits))
            self.assertTrue(all(item["contract_kind"] in {"growth", "auth"} and not item["cache_hit"] for item in audits))
            candidates = [json.loads(line) for line in (output / "growth_candidates.jsonl").read_text().splitlines()]
            dispositions = [json.loads(line) for line in (output / "candidate_dispositions.jsonl").read_text().splitlines()]
            negative_proofs = [json.loads(line) for line in (output / "candidate_negative_proofs.jsonl").read_text().splitlines()]
            links = [json.loads(line) for line in (output / "candidate_entry_links.jsonl").read_text().splitlines()]
            flows = [json.loads(line) for line in (output / "flow_proofs.jsonl").read_text().splitlines()]
            coverage = [json.loads(line) for line in (output / "lifecycle_coverage.jsonl").read_text().splitlines()]
            findings = [json.loads(line) for line in (output / "static_findings.jsonl").read_text().splitlines()]
            certificates = [json.loads(line) for line in (output / "lifecycle_certificates.jsonl").read_text().splitlines()]
            self.assertGreaterEqual(len(candidates), 8)
            self.assertEqual({item["growth_id"] for item in candidates}, {item["growth_id"] for item in dispositions})
            links_by_id = {item["link_id"]: item for item in links}
            relevant = {
                (links_by_id[link_id]["entry_id"], item["growth_id"])
                for item in dispositions
                if item["status"] in {"formal_eligible", "gap_eligible"}
                for link_id in item["link_ids"]
            }
            self.assertTrue(relevant)
            self.assertTrue(relevant.issubset({(item["entry_id"], item["growth_id"]) for item in flows}))
            flow_paths = {(item["entry_id"], item["growth_id"], item["path_id"]) for item in flows}
            self.assertTrue(all((item["entry_id"], item["growth_id"], item["path_id"]) in flow_paths for item in coverage))
            self.assertEqual({item["certificate_id"] for item in certificates}, {item["certificate_id"] for item in findings})
            verdicts = {item["verdict"] for item in findings}
            self.assertEqual(
                {
                    "static_vulnerable",
                    "bounded_under_modeled_assumptions",
                    "static_unknown",
                },
                verdicts,
            )
            self.assertTrue(
                any(item["status"] == "rejected" for item in dispositions),
                "production fixture must prune at least one source-proven negative",
            )
            disposition_by_growth = {item["growth_id"]: item for item in dispositions}
            proof_by_id = {item["negative_proof_id"]: item for item in negative_proofs}
            fixed_allocations = {
                item["site"]["start_line"]: item
                for item in candidates
                if item["kind"] == "direct_allocation"
                and item["site"]["start_line"] in {36, 115}
            }
            self.assertEqual(set(fixed_allocations), {36, 115})
            for line, candidate in fixed_allocations.items():
                with self.subTest(fixed_allocation_line=line):
                    self.assertEqual(candidate["coverage_status"], "complete")
                    self.assertEqual(
                        candidate["coverage_notes"],
                        ["direct_allocation:server_controlled_fixed_size"],
                    )
                    disposition = disposition_by_growth[candidate["growth_id"]]
                    self.assertEqual(disposition["status"], "rejected")
                    self.assertEqual(disposition["local_growth_status"], "rejected")
                    self.assertIn(
                        "RELEVANCE_SERVER_SIZED_ALLOCATION",
                        disposition["reason_codes"],
                    )
                    self.assertEqual(len(disposition["negative_proof_ids"]), 1)
                    proof_id = disposition["negative_proof_ids"][0]
                    self.assertIn(proof_id, disposition["evidence_ids"])
                    proof = proof_by_id[proof_id]
                    self.assertEqual(proof["growth_id"], candidate["growth_id"])
                    self.assertEqual(proof["kind"], "server_controlled_source")
                    self.assertEqual(
                        proof["reason_codes"],
                        ["NEGATIVE_SERVER_CONTROLLED_SOURCE"],
                    )
                    self.assertEqual(
                        proof["evidence_ids"],
                        candidate["candidate_evidence"],
                    )
            self.assertIn("Static resource-exhaustion analysis report", (output / "report.md").read_text(encoding="utf-8"))
            entries = {item["entry_id"]: item for item in [json.loads(line) for line in (output / "entry_facts.jsonl").read_text().splitlines()]}
            candidate_by_id = {item["growth_id"]: item for item in candidates}
            route_pairs = {
                (entries[entry_id]["route_or_event"], candidate_by_id[growth_id]["kind"]): finding["verdict"]
                for (entry_id, growth_id), finding in {(item["entry_id"], item["growth_id"]): item for item in findings}.items()
            }
            self.assertEqual(
                {"/materialize", "/allocate", "/map", "/executor", "/finite", "/post-guard", "/wrapper-guard", "/wrapper-after", "/wrapper-caught", "/wrapper-depth3", "/wrapper-return", "/success-release", "/async-consumer"},
                {item["route_or_event"] for item in entries.values()},
            )
            self.assertEqual(
                set(route_pairs),
                {
                    ("/materialize", "input_materialization"),
                    ("/allocate", "direct_allocation"),
                    ("/map", "container_growth"),
                    ("/executor", "input_materialization"),
                    ("/executor", "async_work_growth"),
                    ("/finite", "input_materialization"),
                    ("/finite", "async_work_growth"),
                    ("/post-guard", "input_materialization"),
                    ("/post-guard", "direct_allocation"),
                    ("/wrapper-guard", "direct_allocation"),
                    ("/wrapper-after", "direct_allocation"),
                    ("/wrapper-caught", "direct_allocation"),
                    ("/wrapper-depth3", "direct_allocation"),
                    ("/wrapper-return", "direct_allocation"),
                    ("/success-release", "container_growth"),
                    ("/async-consumer", "input_materialization"),
                    ("/async-consumer", "async_work_growth"),
                },
            )
            self.assertTrue(
                all(
                    route_pairs[(route, "async_work_growth")] == "static_unknown"
                    for route in ("/executor", "/finite", "/async-consumer")
                ),
                "one-shot async submissions remain candidate-relevant until capacity/release proof closes them",
            )
            self.assertIn("static_vulnerable", route_pairs.values())
            self.assertIn("bounded_under_modeled_assumptions", route_pairs.values())
            self.assertIn("static_unknown", route_pairs.values())
            first_stage_times = {name: stage["ended_at"] for name, stage in run["stages"].items()}
            first_stage_hashes = {name: stage["output_hash"] for name, stage in run["stages"].items()}
            request_count = transport.request_count
            resumed = build_production_pipeline(
                {**self._values(output), "resume": True}, environ={"DEEPSEEK_API_KEY": "fixture-key"},
                deepseek_client_factory=factory,
            ).run("analyze")
            self.assertEqual("completed", resumed["status"])
            self.assertEqual(request_count, transport.request_count)
            self.assertEqual(first_stage_times, {name: stage["ended_at"] for name, stage in resumed["stages"].items()})
            self.assertEqual(first_stage_hashes, {name: stage["output_hash"] for name, stage in resumed["stages"].items()})

    def _framework_run(self, fixture: str) -> tuple[Path, tempfile.TemporaryDirectory[str], ScriptedDeepSeekTransport]:
        holder = tempfile.TemporaryDirectory()
        output = Path(holder.name) / "output"
        source = (_ROOT / f"tests/fixtures/{fixture}/src/main/java").resolve()
        database = fixture_database(str(source))
        transport = ScriptedDeepSeekTransport()
        factory = real_deepseek_factory(transport, StaticPublicVerifier())
        run = build_production_pipeline(
            self._values(output, database=database),
            environ={"DEEPSEEK_API_KEY": "fixture-key"}, deepseek_client_factory=factory,
        ).run("analyze")
        self.assertEqual("completed", run["status"])
        return output, holder, transport

    def test_servlet_allocation_and_release_paths_produce_certificates(self) -> None:
        output, holder, _transport = self._framework_run("servlet")
        try:
            entries = {item["entry_id"]: item for item in [json.loads(line) for line in (output / "entry_facts.jsonl").read_text().splitlines()]}
            candidates = {item["growth_id"]: item for item in [json.loads(line) for line in (output / "growth_candidates.jsonl").read_text().splitlines()]}
            dispositions = {item["growth_id"]: item for item in [json.loads(line) for line in (output / "candidate_dispositions.jsonl").read_text().splitlines()]}
            findings = [json.loads(line) for line in (output / "static_findings.jsonl").read_text().splitlines()]
            certificates = {item["certificate_id"]: item for item in [json.loads(line) for line in (output / "lifecycle_certificates.jsonl").read_text().splitlines()]}
            upload = [item for item in entries.values() if item["route_or_event"] == "/upload"]
            self.assertTrue(upload)
            requested_allocation = [
                item
                for item in candidates.values()
                if item["kind"] == "direct_allocation"
                and item["site"]["file"] == "fixture/servlet/ServletFixture.java"
                and item["site"]["start_line"] == 27
            ]
            self.assertEqual(len(requested_allocation), 1)
            allocation_id = requested_allocation[0]["growth_id"]
            self.assertEqual(dispositions[allocation_id]["status"], "inventory_unresolved")
            self.assertFalse(any(item["growth_id"] == allocation_id for item in findings))
            self.assertTrue(findings)
            self.assertTrue(all(item["verdict"] == "static_unknown" for item in findings))
            self.assertTrue(all(item["certificate_id"] in certificates for item in findings))
            releases = [json.loads(line) for line in (output / "release_candidates.jsonl").read_text().splitlines()]
            self.assertTrue(any(item["site"]["file"] == "fixture/servlet/ServletFixture.java" and item["site"]["start_line"] == 36 and item["receiver"].endswith(".registry") for item in releases))
            release_evidence = [json.loads(line) for line in (output / "lifecycle_evidence.jsonl").read_text().splitlines()]
            self.assertFalse(any(item["family"] == "release" and item["resource_identity"].endswith("requestLocal") for item in release_evidence))
        finally:
            holder.cleanup()

    def test_netty_registration_finite_bound_and_uninstalled_negative(self) -> None:
        output, holder, _transport = self._framework_run("netty")
        try:
            entries = [json.loads(line) for line in (output / "entry_facts.jsonl").read_text().splitlines()]
            self.assertTrue(any("RegisteredHandler.channelRead" in item["handler"]["callable"] for item in entries))
            self.assertFalse(any("UnregisteredHandler.channelRead" in item["handler"]["callable"] for item in entries))
            bounds = [json.loads(line) for line in (output / "bound_candidates.jsonl").read_text().splitlines()]
            self.assertTrue(any(item["result_checked"] and item["configuration_value"] == "8" for item in bounds))
            dispositions = [json.loads(line) for line in (output / "candidate_dispositions.jsonl").read_text().splitlines()]
            self.assertTrue(dispositions)
            self.assertTrue(all(item["status"] in {"formal_eligible", "gap_eligible", "rejected", "inventory_unresolved"} for item in dispositions))
            candidates = {item["growth_id"]: item for item in [json.loads(line) for line in (output / "growth_candidates.jsonl").read_text().splitlines()]}
            findings = [json.loads(line) for line in (output / "static_findings.jsonl").read_text().splitlines()]
            certificates = {item["certificate_id"]: item for item in [json.loads(line) for line in (output / "lifecycle_certificates.jsonl").read_text().splitlines()]}
            finite = [item for item in dispositions if candidates[item["growth_id"]]["site"]["start_line"] == 54]
            self.assertEqual(len(finite), 1)
            self.assertEqual(finite[0]["status"], "gap_eligible")
            self.assertIn(
                "RELEVANCE_QUEUE_CAPACITY_OR_MULTIPLICITY_PARTIAL",
                finite[0]["reason_codes"],
            )
            finite_growth_id = finite[0]["growth_id"]
            repeatability = [
                json.loads(line)
                for line in (output / "repeatability_decisions.jsonl").read_text().splitlines()
            ]
            self.assertTrue(
                any(item["growth_id"] == finite_growth_id for item in repeatability)
            )
            lifecycle = [
                json.loads(line)
                for line in (output / "lifecycle_results.jsonl").read_text().splitlines()
            ]
            finite_lifecycle = [
                item for item in lifecycle if item["growth_id"] == finite_growth_id
            ]
            self.assertEqual(len(finite_lifecycle), 1)
            finite_findings = [
                item for item in findings if item["growth_id"] == finite_growth_id
            ]
            self.assertEqual(len(finite_findings), 1)
            self.assertEqual(finite_findings[0]["verdict"], "static_unknown")
            self.assertIn(
                "VERDICT_CANDIDATE_RELEVANT_GAP",
                finite_findings[0]["reason_codes"],
            )
            self.assertEqual(
                {candidates[item["growth_id"]]["site"]["start_line"] for item in findings},
                {52, 53, 54, 76, 118},
            )
            self.assertTrue(all(item["verdict"] == "static_unknown" for item in findings))
            self.assertTrue(all(item["certificate_id"] in certificates for item in findings))
        finally:
            holder.cleanup()

    def test_mqtt_registration_repeatability_and_static_unknown_are_audited(self) -> None:
        output, holder, _transport = self._framework_run("mqtt")
        try:
            entries = [json.loads(line) for line in (output / "entry_facts.jsonl").read_text().splitlines()]
            self.assertTrue(any(item["framework"] == "mqtt" for item in entries))
            repeatability = [json.loads(line) for line in (output / "repeatability_decisions.jsonl").read_text().splitlines()]
            self.assertTrue(repeatability)
            self.assertTrue(any(item["status"] == "proven" and "REPEATABILITY_REGISTERED_PROTOCOL_TRIGGER" in item["reason_codes"] for item in repeatability))
            candidates = {item["growth_id"]: item for item in [json.loads(line) for line in (output / "growth_candidates.jsonl").read_text().splitlines()]}
            findings = [json.loads(line) for line in (output / "static_findings.jsonl").read_text().splitlines()]
            certificates = {item["certificate_id"]: item for item in [json.loads(line) for line in (output / "lifecycle_certificates.jsonl").read_text().splitlines()]}
            materialization = [item for item in findings if candidates[item["growth_id"]]["kind"] == "input_materialization"]
            self.assertTrue(materialization)
            self.assertTrue(all(item["verdict"] == "static_unknown" for item in findings))
            self.assertTrue(all("VERDICT_UNRESOLVED_EVIDENCE" in item["reason_codes"] and item["certificate_id"] in certificates for item in findings))
        finally:
            holder.cleanup()


class ProductionProofGateE2ETests(unittest.TestCase):
    def test_other_supported_pattern_of_same_registration_kind_cannot_complete_entry(self) -> None:
        helper = FlowVerificationTests()
        entry = EntryFact.from_raw({
            "framework": "spring_mvc",
            "protocol": "http",
            "handler_fqn": "fixture.spring.SpringFixture.create",
            "handler_file": "fixture/spring/SpringFixture.java",
            "handler_start_line": 15,
            "registration_kind": "annotation_mapping",
            "registration_fqn": "fixture.spring.SpringFixture.create",
            "registration_file": "fixture/spring/SpringFixture.java",
            "registration_start_line": 15,
            "route_or_event": "/items",
            "auth_context": "unauthenticated",
            "attacker_input_name": "limit",
            "attacker_input_type": "int",
            "attacker_input_kind": "request_parameter",
            "materialization_phase": "in_handler",
            "coverage_status": "complete",
            "coverage_note": "spring_spel_source_default_modeled_entry",
        })
        growth = helper._growth()  # noqa: SLF001
        from dosweb.flows import FlowProof

        flow = FlowProof.from_dict(production.normalize_flow_rows(  # noqa: SLF001
            (helper._raw(),),  # noqa: SLF001
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )[0])
        link = CandidateEntryLink.create(
            growth.growth_id,
            entry.entry_id,
            "complete",
            (entry.entry_id, growth.growth_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        disposition = CandidateDisposition.create(
            growth.growth_id,
            "formal_eligible",
            canonical_entry_id=entry.entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=(growth.growth_id, link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )
        guard = GuardDecision("ineffective", ("GUARD_ABSENT",), (), (), (), ())
        bound = BoundDecision(
            "effective",
            (),
            (DecisionCheck("bound_effective", True, None, ("fact:bound",)),),
            ("fact:bound",),
            (),
            ("bound:fixture",),
        )
        release = ReleaseDecision(
            "absent", "absent", ("RELEASE_ABSENT",), (), (), (), ()
        )
        lifecycle_record = {
            "entry_id": entry.entry_id,
            "growth_id": growth.growth_id,
            "path_id": flow.path_id,
            "guard": production._decision_record(guard),  # noqa: SLF001
            "bound": production._decision_record(bound),  # noqa: SLF001
            "release": production._decision_record(release),  # noqa: SLF001
        }
        lifecycle_coverage = [
            LifecycleCoverage(
                entry.entry_id,
                growth.growth_id,
                flow.path_id,
                family,
                "complete",
                "fixture_complete",
            ).to_dict()
            for family in ("guard", "bound", "release")
        ]
        reachability = ReachabilityDecision(
            entry.entry_id,
            "auth_contract:fixture",
            "unauthenticated",
            "default_enabled",
            "ordinary_attacker_reachable",
            (),
            ("REACH_ORDINARY_ATTACKER",),
        )
        repeatability = RepeatabilityDecision.create(
            "repeatability",
            entry.entry_id,
            growth.growth_id,
            "proven",
            (entry.entry_id, growth.growth_id),
            ("REPEATABILITY_FIXTURE",),
        )
        amplification = AmplificationDecision.create(
            "amplification",
            entry.entry_id,
            growth.growth_id,
            "not_applicable",
            (growth.growth_id,),
            ("AMPLIFICATION_DIRECT_DEMAND_ASSERTION",),
        )
        strict_records = {
            "lifecycle_coverage.jsonl": lifecycle_coverage,
            "guard_candidates.jsonl": [],
            "bound_candidates.jsonl": [],
            "release_candidates.jsonl": [],
            "reachability_decisions.jsonl": [reachability.to_dict()],
            "repeatability_decisions.jsonl": [repeatability.to_dict()],
            "amplification_decisions.jsonl": [amplification.to_dict()],
            "candidate_entry_links.jsonl": [link.to_dict()],
            "candidate_dispositions.jsonl": [disposition.to_dict()],
        }
        ordinary_records = {
            "flow_proofs.jsonl": [flow.to_dict()],
            "lifecycle_results.jsonl": [lifecycle_record],
        }
        context = StageContext(
            "conclude",
            Path("/tmp/entry-exact-coverage-e2e"),
            StageFingerprint.for_stage("conclude"),
            {},
            {},
        )
        selected_coverage = [
            FrameworkCoverage(
                "spring_mvc",
                "complete",
                (
                    "entry-registration-coverage:"
                    "spring_mvc:annotation_mapping:spring_annotation_mapping",
                ),
                (),
                "none",
            )
        ]

        with (
            mock.patch.object(
                production,
                "_load_entries",
                return_value={entry.entry_id: entry},
            ),
            mock.patch.object(
                production,
                "_load_verified_growth",
                return_value={growth.growth_id: growth},
            ),
            mock.patch.object(
                production,
                "_records",
                side_effect=lambda _context, _stage, artifact, _schema: ordinary_records[artifact],
            ),
            mock.patch.object(
                production,
                "_strict_records",
                side_effect=lambda _context, _stage, artifact: strict_records[artifact],
            ),
            mock.patch.object(
                production,
                "_coverage",
                return_value=selected_coverage,
            ),
        ):
            output = production.make_conclude_executor()(context)
            selected_coverage[:] = [
                FrameworkCoverage(
                    "spring_mvc",
                    "complete",
                    (entry.registration_pattern_id,),
                    (),
                    "none",
                )
            ]
            exact_output = production.make_conclude_executor()(context)

        finding = output.artifacts["static_findings.jsonl"][0]
        self.assertEqual(finding["verdict"], "static_unknown")
        self.assertIn(
            "VERDICT_ENTRY_COVERAGE_INCOMPLETE",
            finding["reason_codes"],
        )
        exact_finding = exact_output.artifacts["static_findings.jsonl"][0]
        exact_certificate = exact_output.artifacts["lifecycle_certificates.jsonl"][0]
        self.assertEqual(
            exact_finding["verdict"], "bounded_under_modeled_assumptions"
        )
        self.assertEqual(
            exact_finding["certificate_id"], exact_certificate["certificate_id"]
        )

    def test_gap_eligible_effective_bound_is_still_static_unknown(self) -> None:
        helper = FlowVerificationTests()
        entry = helper._entry()  # noqa: SLF001
        growth = helper._growth()  # noqa: SLF001
        proof = production.normalize_flow_rows(  # noqa: SLF001
            (helper._raw(),),  # noqa: SLF001
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )[0]
        from dosweb.flows import FlowProof

        flow = FlowProof.from_dict(proof)
        link = CandidateEntryLink.create(
            growth.growth_id,
            entry.entry_id,
            "complete",
            (entry.entry_id, growth.growth_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        disposition = CandidateDisposition.create(
            growth.growth_id,
            "gap_eligible",
            canonical_entry_id=entry.entry_id,
            local_growth_status="partial",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=(growth.growth_id, link.link_id),
            negative_proof_ids=(),
            reason_codes=(
                "MATURATION_GAP_ELIGIBLE",
                "RELEVANCE_AMPLIFICATION_LARGE_SINGLE_REQUEST",
            ),
        )
        guard = GuardDecision("ineffective", ("GUARD_ABSENT",), (), (), (), ())
        bound = BoundDecision(
            "effective",
            (),
            (DecisionCheck("bound_effective", True, None, ("fact:bound",)),),
            ("fact:bound",),
            (),
            ("bound:fixture",),
        )
        release = ReleaseDecision(
            "absent", "absent", ("RELEASE_ABSENT",), (), (), (), ()
        )
        lifecycle_record = {
            "entry_id": entry.entry_id,
            "growth_id": growth.growth_id,
            "path_id": flow.path_id,
            "guard": production._decision_record(guard),  # noqa: SLF001
            "bound": production._decision_record(bound),  # noqa: SLF001
            "release": production._decision_record(release),  # noqa: SLF001
        }
        lifecycle_coverage = [
            LifecycleCoverage(
                entry.entry_id,
                growth.growth_id,
                flow.path_id,
                family,
                "complete",
                "fixture_complete",
            ).to_dict()
            for family in ("guard", "bound", "release")
        ]
        reachability = ReachabilityDecision(
            entry.entry_id,
            "auth_contract:fixture",
            "unauthenticated",
            "default_enabled",
            "ordinary_attacker_reachable",
            (),
            ("REACH_ORDINARY_ATTACKER",),
        )
        repeatability = RepeatabilityDecision.create(
            "repeatability",
            entry.entry_id,
            growth.growth_id,
            "proven",
            (entry.entry_id, growth.growth_id),
            ("REPEATABILITY_FIXTURE",),
        )
        amplification = AmplificationDecision.create(
            "amplification",
            entry.entry_id,
            growth.growth_id,
            "not_applicable",
            (growth.growth_id,),
            ("AMPLIFICATION_DIRECT_DEMAND_ASSERTION",),
        )

        strict_records = {
            "lifecycle_coverage.jsonl": lifecycle_coverage,
            "guard_candidates.jsonl": [],
            "bound_candidates.jsonl": [],
            "release_candidates.jsonl": [],
            "reachability_decisions.jsonl": [reachability.to_dict()],
            "repeatability_decisions.jsonl": [repeatability.to_dict()],
            "amplification_decisions.jsonl": [amplification.to_dict()],
            "candidate_entry_links.jsonl": [link.to_dict()],
            "candidate_dispositions.jsonl": [disposition.to_dict()],
        }
        ordinary_records = {
            "flow_proofs.jsonl": [flow.to_dict()],
            "lifecycle_results.jsonl": [lifecycle_record],
        }
        context = StageContext(
            "conclude",
            Path("/tmp/proof-gate-e2e"),
            StageFingerprint.for_stage("conclude"),
            {},
            {},
        )

        with (
            mock.patch.object(
                production,
                "_load_entries",
                return_value={entry.entry_id: entry},
            ),
            mock.patch.object(
                production,
                "_load_verified_growth",
                return_value={growth.growth_id: growth},
            ),
            mock.patch.object(
                production,
                "_records",
                side_effect=lambda _context, _stage, artifact, _schema: ordinary_records[artifact],
            ),
            mock.patch.object(
                production,
                "_strict_records",
                side_effect=lambda _context, _stage, artifact: strict_records[artifact],
            ),
            mock.patch.object(
                production,
                "_coverage",
                return_value=(
                    FrameworkCoverage(
                        "spring_mvc",
                        "complete",
                        (entry.registration_pattern_id,),
                        (),
                        "none",
                    ),
                ),
            ),
        ):
            output = production.make_conclude_executor()(context)

        findings = output.artifacts["static_findings.jsonl"]
        certificates = output.artifacts["lifecycle_certificates.jsonl"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["verdict"], "static_unknown")
        self.assertIn("VERDICT_CANDIDATE_RELEVANT_GAP", findings[0]["reason_codes"])
        self.assertEqual(certificates[0]["bound_decision"]["status"], "effective")
        self.assertNotIn(
            "STATIC_EVIDENCE_COVERAGE_COMPLETE",
            certificates[0]["assumptions"],
        )
        self.assertIn(
            "MODELED_DEFAULT_CONFIGURATION", certificates[0]["assumptions"]
        )


if __name__ == "__main__":
    unittest.main()
