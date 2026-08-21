from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dosweb.benchmark.disposition import DISPOSITION_STATUSES, TargetArtifacts, compute_disposition
from dosweb.errors import AnalyzerError
from scripts.generate_poc33_recall import _bounded_sink_markers, _infer_protocol, _sink_locations_for_record


def _entry(entry_id: str, route: str, framework: str = "spring_mvc", protocol: str = "http"):
    return {"entry_id": entry_id, "route_or_event": route, "protocol": protocol, "framework": framework}


def _growth(growth_id: str, marker: str = "queries.put"):
    return {"growth_id": growth_id, "site": {"file": "X.java", "start_line": 10}, "resource_point": {"dimension": "entries", "receiver": marker, "field_path": "m", "resource_id": "resource:x"}}
    # marker lives inside receiver for a trivial substring match


def _truth(record_id: str, entry: str, markers: list[str]):
    return {"record_id": record_id, "repository": "apache/presto", "app": "apache/presto", "entry": entry, "status": "confirmed_oom", "markers": markers, "truth_id": f"truth:{record_id}"}


def _artifacts(**overrides) -> TargetArtifacts:
    artifacts = TargetArtifacts(Path("/nonexistent"))
    defaults = {
        "entries": [],
        "growth_candidates": [],
        "links": [],
        "candidate_dispositions": [],
        "verified_growth": [],
        "flow_proofs": [],
        "findings": [],
        "certificates": [],
        "run_status": "completed",
        "run_error": None,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(artifacts, key, value)
    return artifacts


class DispositionTests(unittest.TestCase):
    def test_statuses_are_fixed(self):
        self.assertEqual(
            DISPOSITION_STATUSES,
            (
                "full_chain_finding", "entry_and_growth_linked", "entry_only",
                "growth_only", "association_missing", "flow_partial", "lifecycle_unknown",
                "stage_failed", "asset_missing", "unsupported_scope", "ambiguous_truth_match",
            ),
        )

    def test_asset_missing_when_error_supplied(self):
        artifacts = TargetArtifacts(Path("/definitely/not/a/real/dir"))
        result = compute_disposition(_truth("x", "POST /v1/statement", ["queries.put"]), artifacts, error="asset_missing")
        self.assertEqual(result["status"], "asset_missing")

    def test_stage_failed_when_run_not_completed(self):
        artifacts = _artifacts(run_status="failed", run_error={"code": "CODEQL_QUERY_FAILED"})
        result = compute_disposition(_truth("x", "POST /v1/statement", ["queries.put"]), artifacts)
        self.assertEqual(result["status"], "stage_failed")
        self.assertIn("CODEQL_QUERY_FAILED", result["reason_codes"])

    def test_full_chain_finding(self):
        entry = _entry("entry:a", "POST /v1/statement")
        artifacts = _artifacts(
            entries=[entry],
            growth_candidates=[_growth("growth:a", "queries.put")],
            links=[{"entry_id": "entry:a", "growth_id": "growth:a", "status": "complete"}],
            verified_growth=[{"growth_id": "growth:a", "status": "verified"}],
            flow_proofs=[{"entry_id": "entry:a", "growth_id": "growth:a", "path_id": "flow:a", "confidence": "proven"}],
            findings=[{"entry_id": "entry:a", "growth_id": "growth:a", "finding_id": "finding:a", "verdict": "static_unknown", "certificate_id": "certificate:a"}],
        )
        result = compute_disposition(_truth("x", "POST /v1/statement", ["queries.put"]), artifacts)
        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["verdicts"], ["static_unknown"])

    def test_chain_result_is_scoped_to_the_truth_growth_identity(self):
        entry = _entry("entry:a", "POST /v1/statement")
        target = _growth("growth:target", "queries.put")
        unrelated = _growth("growth:unrelated", "otherMap.put")
        artifacts = _artifacts(
            entries=[entry],
            growth_candidates=[target, unrelated],
            links=[
                {"entry_id": "entry:a", "growth_id": "growth:target", "status": "partial"},
                {"entry_id": "entry:a", "growth_id": "growth:unrelated", "status": "complete"},
            ],
            findings=[
                {"entry_id": "entry:a", "growth_id": "growth:target", "finding_id": "finding:target", "verdict": "static_unknown", "certificate_id": "certificate:target"},
                {"entry_id": "entry:a", "growth_id": "growth:unrelated", "finding_id": "finding:unrelated", "verdict": "static_vulnerable", "certificate_id": "certificate:unrelated"},
            ],
        )
        result = compute_disposition(_truth("x", "POST /v1/statement", ["queries.put"]), artifacts)
        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_growth_ids"], ["growth:target"])
        self.assertEqual(result["matched_finding_ids"], ["finding:target"])
        self.assertEqual(result["verdicts"], ["static_unknown"])

    def test_entry_only_when_no_growth_links(self):
        artifacts = _artifacts(entries=[_entry("entry:a", "POST /v1/statement")])
        result = compute_disposition(_truth("x", "POST /v1/statement", ["queries.put"]), artifacts)
        self.assertEqual(result["status"], "entry_only")

    def test_growth_only_when_entry_identity_does_not_match(self):
        artifacts = _artifacts(
            entries=[_entry("entry:a", "GET /other")],
            growth_candidates=[_growth("growth:a", "queries.put")],
        )
        result = compute_disposition(_truth("x", "POST /v1/statement", ["queries.put"]), artifacts)
        self.assertEqual(result["status"], "growth_only")

    def test_partial_dynamic_route_is_audited_without_becoming_complete_entry(self):
        artifacts = _artifacts(
            entry_gaps=[{
                "gap_id": "gap:a",
                "framework": "jax_rs",
                "protocol": "http",
                "route_or_event": "POST /api/v2/process/{id}/log/segment/{segmentId}",
                "coverage_status": "partial",
                "coverage_note": "annotation_only_jax_rs_resource",
            }],
        )
        result = compute_disposition(
            _truth("x", "POST /api/v2/process/abc/log/segment/0", ["readAllBytes"]),
            artifacts,
        )
        self.assertEqual(result["status"], "entry_only")
        self.assertEqual(result["reason_codes"], ["ENTRY_DYNAMIC_REGISTRATION_UNPROVEN"])
        self.assertEqual(result["matched_gap_ids"], ["gap:a"])

    def test_smqtt_protocol_gap_matches_protocol_truth_without_becoming_entry(self):
        artifacts = _artifacts(
            entry_gaps=[{
                "gap_id": "gap:smqtt",
                "framework": "mqtt",
                "protocol": "mqtt",
                "route_or_event": "mqtt_protocol",
                "handler_file": "smqtt-core/src/main/java/io/github/quickmsg/core/mqtt/MqttReceiver.java",
                "handler_start_line": 26,
                "coverage_status": "partial",
                "coverage_note": "smqtt_protocol_dispatch_binding_unresolved",
            }],
        )
        truth = {
            **_truth("smqtt", "protocol service on port 1883", ["retainMessages.put"]),
            "repository": "quickmsg/smqtt",
            "app": "quickmsg/smqtt",
            "protocol": "mqtt",
        }
        result = compute_disposition(truth, artifacts)
        self.assertEqual(result["status"], "entry_only")
        self.assertEqual(result["reason_codes"], ["ENTRY_DYNAMIC_REGISTRATION_UNPROVEN"])
        self.assertEqual(result["matched_gap_ids"], ["gap:smqtt"])

    def test_partial_dynamic_route_with_growth_preserves_furthest_stage(self):
        artifacts = _artifacts(
            entry_gaps=[{
                "gap_id": "gap:a",
                "framework": "jax_rs",
                "protocol": "http",
                "route_or_event": "POST /api/v2/process/{id}/log/segment/{segmentId}",
                "coverage_status": "partial",
                "coverage_note": "annotation_only_jax_rs_resource",
            }],
            growth_candidates=[_growth("growth:a", "readAllBytes")],
        )
        result = compute_disposition(
            _truth("x", "POST /api/v2/process/abc/log/segment/0", ["readAllBytes"]),
            artifacts,
        )
        self.assertEqual(result["status"], "growth_only")
        self.assertEqual(
            result["reason_codes"],
            ["ENTRY_DYNAMIC_REGISTRATION_UNPROVEN", "GROWTH_SINK_MATCHED"],
        )
        self.assertEqual(result["matched_growth_ids"], ["growth:a"])

    def test_unsupported_scope_for_out_of_scope_framework(self):
        artifacts = _artifacts(entries=[_entry("entry:a", "POST /x", framework="solr", protocol="http")])
        result = compute_disposition(_truth("x", "POST /x", ["solr"]), artifacts)
        self.assertEqual(result["status"], "unsupported_scope")

    def test_target_artifacts_loads_from_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "entry_facts.jsonl").write_text(json.dumps(_entry("entry:a", "POST /x")) + "\n")
            (root / "run.json").write_text(json.dumps({"status": "completed"}))
            artifacts = TargetArtifacts.load(root)
            self.assertEqual(artifacts.run_status, "completed")
            self.assertEqual(artifacts.entries[0]["entry_id"], "entry:a")

    def test_target_artifacts_rejects_corrupt_entry_gap_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "entry_gap_facts.jsonl").write_text("not-json\n")
            (root / "run.json").write_text(json.dumps({"status": "completed"}))
            with self.assertRaises(AnalyzerError) as raised:
                TargetArtifacts.load(root)
            self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_RECORD")

    def test_interposition_chain_collapses_route_variants_and_preserves_filter_link(self):
        registration = {"kind": "annotation_mapping", "callable": "Controller.push", "file": "Controller.java", "start_line": 10}
        controller = {
            **_entry("entry:controller", "POST /api/push/prometheus/**"),
            "handler": {"callable": "Controller.push", "file": "Controller.java", "start_line": 12},
            "registration": registration,
        }
        controller_variant = {
            **controller,
            "entry_id": "entry:controller-variant",
            "route_or_event": "/api/push/prometheus/**",
        }
        filter_entry = {
            **_entry("entry:filter", "/api/push/prometheus/*", framework="servlet"),
            "handler": {"callable": "RegisteredFilter.doFilter", "file": "RegisteredFilter.java", "start_line": 20},
            "registration": {"kind": "static_registration", "callable": "Config.setFilter", "file": "Config.java", "start_line": 30},
        }
        artifacts = _artifacts(
            entries=[controller, controller_variant, filter_entry],
            entry_interpositions=[{
                "interposition_id": "interposition:a",
                "entry_id": "entry:controller",
                "interposer": {"callable": "RegisteredFilter.doFilter", "file": "RegisteredFilter.java", "start_line": 20},
            }],
            growth_candidates=[_growth("growth:a", "jobInstanceMap")],
            links=[{"entry_id": "entry:filter", "growth_id": "growth:a", "status": "partial"}],
        )
        result = compute_disposition(
            _truth("x", "POST /api/push/prometheus/job/demo/instance/a", ["jobInstanceMap"]),
            artifacts,
        )
        self.assertEqual(result["status"], "entry_and_growth_linked")
        self.assertEqual(set(result["matched_entry_ids"]), {"entry:controller", "entry:filter"})
        self.assertEqual(result["matched_growth_ids"], ["growth:a"])

    def test_servlet_root_wildcard_matches_descendant_truth_route(self):
        artifacts = _artifacts(entries=[_entry("entry:solr", "/*", framework="servlet")])
        result = compute_disposition(
            _truth("solr", "POST /solr/doscore/select with Content-Type: application/x-www-form-urlencoded", ["sink"]),
            artifacts,
        )
        self.assertEqual(result["status"], "entry_only")
        self.assertEqual(result["matched_entry_ids"], ["entry:solr"])

    def test_truth_seed_extracts_nested_sink_and_protocol_without_dynamic_override(self):
        markers = _bounded_sink_markers({
            "static_traceability": {
                "source": "POST /api/push",
                "sink": "PushGatewayServiceImpl.jobInstanceMap.computeIfAbsent(job)",
            }
        })
        self.assertEqual(markers, ["PushGatewayServiceImpl.jobInstanceMap.computeIfAbsent(job)"])
        self.assertEqual(_infer_protocol("quickmsg__smqtt", "protocol service on port 1883"), "mqtt")
        self.assertEqual(_infer_protocol("apache__skywalking", "gRPC /Service/collect"), "grpc")

    def test_truth_seed_derives_sink_scoped_source_locations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attachments = root / "poc" / "case" / "attachments"
            attachments.mkdir(parents=True)
            (attachments / "static_finding.json").write_text(json.dumps({
                "sink": "CachingRequestBodyFilter.CustomWrapper reads the full body",
                "evidence": [
                    "CachingRequestBodyFilter.java:63-80",
                    "UnrelatedAuthFilter.java:10-20",
                ],
            }))
            locations = _sink_locations_for_record(
                {"output_dir": "poc/case"}, root,
                ["CachingRequestBodyFilter.CustomWrapper reads the full body"],
            )
            self.assertEqual(locations, [{
                "file": "CachingRequestBodyFilter.java", "start_line": 63, "end_line": 80,
            }])

    def test_route_placeholder_and_wildcard_matching(self):
        from dosweb.benchmark.disposition import _routes_match
        self.assertTrue(_routes_match("/erupt-api/data/table/{}", "/erupt-api/data/table/EruptUser"))
        self.assertTrue(_routes_match("/api/push/prometheus/**", "/api/push/prometheus/job/{}/instance/{}"))
        self.assertTrue(_routes_match("/api/push/prometheus/*", "/api/push/prometheus/job/demo/instance/a"))
        self.assertTrue(_routes_match("/a/b", "/a/b"))
        self.assertFalse(_routes_match("/a/b", "/a/c"))


if __name__ == "__main__":
    unittest.main()
