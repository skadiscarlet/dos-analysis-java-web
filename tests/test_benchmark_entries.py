import tempfile
import unittest
from pathlib import Path

from dosweb.artifacts.identifiers import file_sha256
from dosweb.artifacts.schemas import SCHEMA_VERSION
from dosweb.benchmark.entries import _CURRENT_ENTRY_ARTIFACTS, _safe_artifact, extract_entries_from_target
from dosweb.benchmark.matching import match_entry_case, normalize_route


from tests.support.offline_assets import require_poc29_entries_archive

ROOT = Path(__file__).resolve().parents[1]


class BenchmarkEntryDiagnosticsTests(unittest.TestCase):
    def test_current_entry_artifact_contract_includes_gap_interposition_and_configuration(self):
        self.assertIn("entry_gap_facts.jsonl", _CURRENT_ENTRY_ARTIFACTS)
        self.assertIn("entry_interposition_facts.jsonl", _CURRENT_ENTRY_ARTIFACTS)
        self.assertIn("configuration_coverage.json", _CURRENT_ENTRY_ARTIFACTS)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "entry_gap_facts.jsonl"
            path.write_text("", encoding="utf-8")
            metadata = {
                "path": path.name,
                "sha256": file_sha256(path),
                "byte_count": 0,
                "record_count": 0,
                "schema_version": SCHEMA_VERSION,
            }
            self.assertEqual(_safe_artifact(root, metadata, schema_version=SCHEMA_VERSION), path)
            with self.assertRaises(ValueError):
                _safe_artifact(root, metadata, schema_version="2.0")

    def _entry(self, entry_id: str, *, registration_line: int | None = None) -> dict:
        entry = {
            "entry_id": entry_id,
            "route_or_event": "POST /api/items/{id}",
            "protocol": "http",
        }
        if registration_line is not None:
            entry["registration"] = {
                "kind": "static_registration",
                "callable": "fixture.Bootstrap.register",
                "file": "fixture/Bootstrap.java",
                "start_line": registration_line,
            }
        return {"repository": "owner/repo", "entry": entry}

    def test_real_entries_archive_reads_completed_stage_without_p0_artifacts(self):
        target = require_poc29_entries_archive(ROOT)
        entries, gaps, error = extract_entries_from_target(
            target,
            target_id="target:b33ff3794549c3f1f8238930",
            repository="openzipkin/zipkin",
        )
        self.assertIsNone(error)
        self.assertEqual(len(entries), 1)
        self.assertTrue(gaps)
        self.assertFalse((target / "static_findings.jsonl").exists())

    def test_normalizes_route_and_matches_repository_method_protocol(self):
        self.assertEqual(normalize_route("POST https://host/api/items/42"), "/api/items/42")
        result = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": "POST /api/items/{key}"},
            [self._entry("entry:one")],
        )
        self.assertEqual(result["status"], "entry_hit")
        self.assertEqual(result["entry_ids"], ["entry:one"])

    def test_duplicate_identity_is_ambiguous_without_registration_identity(self):
        result = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": "POST /api/items/{key}"},
            [self._entry("entry:a"), self._entry("entry:b")],
        )
        self.assertEqual(result["status"], "entry_ambiguous")

    def test_duplicate_handlers_merge_only_for_the_same_registration(self):
        truth = {
            "case_id": "case",
            "repository": "owner/repo",
            "entry": "POST /api/items/{key}",
        }
        merged = match_entry_case(
            truth,
            [
                self._entry("entry:a", registration_line=10),
                self._entry("entry:b", registration_line=10),
            ],
        )
        ambiguous = match_entry_case(
            truth,
            [
                self._entry("entry:a", registration_line=10),
                self._entry("entry:b", registration_line=11),
            ],
        )
        self.assertEqual(merged["status"], "entry_hit")
        self.assertEqual(merged["entry_ids"], ["entry:a", "entry:b"])
        self.assertEqual(merged["merged_entry_ids"], ["entry:b"])
        self.assertEqual(ambiguous["status"], "entry_ambiguous")

    def test_mqtt_protocol_service_matches_without_port_guessing(self):
        entry = {
            "repository": "owner/repo",
            "entry": {
                "entry_id": "entry:mqtt",
                "route_or_event": "mqtt_protocol",
                "protocol": "mqtt",
            },
        }
        result = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": "anonymous MQTT broker protocol service"},
            [entry],
        )
        self.assertEqual(result["status"], "entry_hit")
        self.assertEqual(result["entry_ids"], ["entry:mqtt"])
        port_only = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": "TCP port 1883"},
            [entry],
        )
        self.assertEqual(port_only["status"], "no_entry_match")

    def test_route_only_http_truth_matches_unique_entry(self):
        entry = {
            "repository": "owner/repo",
            "entry": {
                "entry_id": "entry:route-only",
                "route_or_event": "/rest/verify/captcha",
                "protocol": "http",
            },
        }
        result = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": "/rest/verify/captcha"},
            [entry],
        )
        self.assertEqual(result["status"], "entry_hit")
        self.assertEqual(result["entry_ids"], ["entry:route-only"])

    def test_http_and_grpc_routes_are_case_sensitive(self):
        http = {
            "repository": "owner/repo",
            "entry": {
                "entry_id": "entry:http-case",
                "route_or_event": "/API/items",
                "protocol": "http",
            },
        }
        grpc = {
            "repository": "owner/repo",
            "entry": {
                "entry_id": "entry:grpc-case",
                "route_or_event": "/fixture.Service/Upload",
                "protocol": "grpc",
            },
        }
        self.assertEqual(
            match_entry_case(
                {"case_id": "http", "repository": "owner/repo", "entry": "/api/items"},
                [http],
            )["status"],
            "no_entry_match",
        )
        self.assertEqual(
            match_entry_case(
                {
                    "case_id": "grpc",
                    "repository": "owner/repo",
                    "entry": "gRPC /fixture.Service/upload",
                },
                [grpc],
            )["status"],
            "no_entry_match",
        )

    def test_route_only_http_truth_rejects_conflicting_candidate_method(self):
        entry = {
            "repository": "owner/repo",
            "entry": {
                "entry_id": "entry:method-conflict",
                "route_or_event": "GET /rest/verify/captcha",
                "protocol": "http",
            },
        }
        result = match_entry_case(
            {
                "case_id": "case",
                "repository": "owner/repo",
                "entry": "POST /rest/verify/captcha",
            },
            [entry],
        )
        self.assertEqual(result["status"], "no_entry_match")

    def test_zipkin_route_matches_real_collector_path(self):
        entry = {
            "repository": "openzipkin/zipkin",
            "entry": {
                "entry_id": "entry:zipkin",
                "route_or_event": "/api/v2/spans",
                "protocol": "http",
            },
        }
        result = match_entry_case(
            {"case_id": "case", "repository": "openzipkin/zipkin", "entry": "POST /api/v2/spans"},
            [entry],
        )
        self.assertEqual(result["status"], "entry_hit")

    def test_grpc_service_method_identity_matches_without_http_aliasing(self):
        entry = {
            "repository": "owner/repo",
            "entry": {
                "entry_id": "entry:grpc",
                "route_or_event": "/fixture.Service/Upload",
                "protocol": "grpc",
            },
        }
        result = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": "gRPC /fixture.Service/Upload"},
            [entry],
        )
        self.assertEqual(result["status"], "entry_hit")
        http_alias = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": "POST /fixture.Service/Upload"},
            [entry],
        )
        self.assertEqual(http_alias["status"], "no_entry_match")

    def test_incomplete_truth_identity_is_distinct_from_query_miss(self):
        incomplete = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": ""},
            [self._entry("entry:one")],
        )
        query_miss = match_entry_case(
            {"case_id": "case", "repository": "owner/repo", "entry": "POST /missing"},
            [],
        )
        self.assertEqual(incomplete["status"], "no_entry_match")
        self.assertEqual(incomplete["reason"], "truth_entry_identity_incomplete")
        self.assertEqual(query_miss["status"], "no_entry_match")
        self.assertNotIn("reason", query_miss)

    def test_target_and_artifact_states_are_preserved(self):
        truth = {"case_id": "case", "repository": "owner/repo", "entry": "POST /x"}
        self.assertEqual(match_entry_case(truth, [], error="target_not_run")["status"], "target_not_run")
        self.assertEqual(match_entry_case(truth, [], error="artifact_missing")["status"], "artifact_missing")
