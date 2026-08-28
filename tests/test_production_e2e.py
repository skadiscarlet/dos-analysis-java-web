from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from dosweb.production import build_production_pipeline
from tests.support.fixture_database import fixture_database
from tests.support.mock_deepseek import ScriptedDeepSeekTransport, StaticPublicVerifier, real_deepseek_factory


_ROOT = Path(__file__).resolve().parents[1]
_RUN = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql") or "/usr/bin/codeql"


@unittest.skipUnless(_RUN and Path(_CODEQL).exists(), "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with CodeQL available.")
class ProductionFixtureE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_root = (_ROOT / "tests/fixtures/p0/src/main/java").resolve()
        cls.database = fixture_database(str(cls.source_root))

    def _values(self, output: Path, *, source_root: Path | None = None, database: object | None = None) -> dict[str, object]:
        source_root = source_root or self.source_root
        database = database or self.database
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
                "candidate_dispositions.jsonl", "flow_proofs.jsonl", "lifecycle_results.jsonl",
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
                if item["status"] in {"verified_relevant", "dos_relevant_partial"}
                for link_id in item["link_ids"]
            }
            self.assertTrue(relevant)
            self.assertTrue(relevant.issubset({(item["entry_id"], item["growth_id"]) for item in flows}))
            flow_paths = {(item["entry_id"], item["growth_id"], item["path_id"]) for item in flows}
            self.assertTrue(all((item["entry_id"], item["growth_id"], item["path_id"]) in flow_paths for item in coverage))
            self.assertEqual({item["certificate_id"] for item in certificates}, {item["certificate_id"] for item in findings})
            verdicts = {item["verdict"] for item in findings}
            self.assertTrue(verdicts.issubset({"static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown"}))
            self.assertIn("static_unknown", verdicts)
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
                    ("/finite", "input_materialization"),
                    ("/post-guard", "input_materialization"),
                    ("/wrapper-guard", "direct_allocation"),
                    ("/wrapper-after", "direct_allocation"),
                    ("/wrapper-caught", "direct_allocation"),
                    ("/wrapper-depth3", "direct_allocation"),
                    ("/wrapper-return", "direct_allocation"),
                    ("/success-release", "container_growth"),
                    ("/async-consumer", "input_materialization"),
                },
            )
            self.assertEqual(set(route_pairs.values()), {"static_unknown"})
            self.assertTrue(
                all(
                    "VERDICT_UNRESOLVED_EVIDENCE" in item["reason_codes"]
                    for item in findings
                )
            )
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
            self._values(output, source_root=source, database=database),
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
            self.assertEqual(dispositions[allocation_id]["status"], "unresolved")
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
            self.assertTrue(all(item["status"] in {"verified_relevant", "dos_relevant_partial", "unresolved", "rejected", "not_entry_reachable"} for item in dispositions))
            candidates = {item["growth_id"]: item for item in [json.loads(line) for line in (output / "growth_candidates.jsonl").read_text().splitlines()]}
            findings = [json.loads(line) for line in (output / "static_findings.jsonl").read_text().splitlines()]
            certificates = {item["certificate_id"]: item for item in [json.loads(line) for line in (output / "lifecycle_certificates.jsonl").read_text().splitlines()]}
            finite = [item for item in dispositions if candidates[item["growth_id"]]["site"]["start_line"] == 54]
            self.assertEqual(len(finite), 1)
            self.assertEqual(finite[0]["status"], "rejected")
            self.assertIn("RELEVANCE_SINGLE_SUBMISSION", finite[0]["reason_codes"])
            self.assertEqual(
                {candidates[item["growth_id"]]["site"]["start_line"] for item in findings},
                {76, 118},
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


if __name__ == "__main__":
    unittest.main()
