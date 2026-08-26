from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dosweb.benchmark.disposition import DISPOSITION_STATUSES, TargetArtifacts, compute_disposition
from dosweb.errors import AnalyzerError
from scripts.generate_poc33_recall import (
    _bounded_sink_markers,
    _infer_protocol,
    _markers_for_record,
    _resolve_results_dir,
    _sink_locations_for_record,
)


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
    def test_resolve_results_dir_uses_p0_batch_target_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "targets" / "127-thingsboard__thingsboard"
            target.mkdir(parents=True)
            (target / "batch_target.json").write_text(json.dumps({
                "target": {"identity": {"slug": "thingsboard__thingsboard"}},
            }), encoding="utf-8")

            self.assertEqual(
                _resolve_results_dir(root, "thingsboard__thingsboard"),
                target,
            )

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

    def test_generic_port_service_truth_matches_only_linked_tcp_entry(self):
        tcp_entry = _entry(
            "entry:tcp", "channelRead", framework="netty", protocol="tcp"
        )
        http_entry = _entry("entry:http", "POST /trigger")
        growth = _growth("growth:queue", "triggerQueue.add")
        artifacts = _artifacts(
            entries=[http_entry, tcp_entry],
            growth_candidates=[growth],
            links=[{
                "entry_id": "entry:tcp",
                "growth_id": "growth:queue",
                "status": "partial",
            }],
            flow_proofs=[{
                "entry_id": "entry:tcp",
                "growth_id": "growth:queue",
                "path_id": "flow:queue",
                "confidence": "partial",
            }],
            findings=[{
                "entry_id": "entry:tcp",
                "growth_id": "growth:queue",
                "finding_id": "finding:queue",
                "verdict": "static_unknown",
                "certificate_id": "certificate:queue",
            }],
        )
        truth = {
            **_truth(
                "xxl-generic",
                "protocol service on port 9999",
                ["triggerQueue.add"],
            ),
            "protocol": "unknown",
        }

        result = compute_disposition(truth, artifacts)

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_entry_ids"], ["entry:tcp"])

    def test_generic_port_service_truth_does_not_match_http_entry(self):
        artifacts = _artifacts(
            entries=[_entry("entry:http", "POST /trigger")],
            growth_candidates=[_growth("growth:queue", "triggerQueue.add")],
        )
        truth = {
            **_truth(
                "xxl-generic-http-negative",
                "protocol service on port 9999",
                ["triggerQueue.add"],
            ),
            "protocol": "unknown",
        }

        result = compute_disposition(truth, artifacts)

        self.assertEqual(result["status"], "growth_only")
        self.assertEqual(result["reason_codes"], [
            "ENTRY_IDENTITY_NOT_MATCHED",
            "GROWTH_SINK_MATCHED",
        ])

    def test_generic_port_service_truth_matches_inferred_mqtt_entry(self):
        artifacts = _artifacts(
            entries=[_entry(
                "entry:mqtt", "mqtt_protocol", framework="mqtt", protocol="mqtt",
            )],
            growth_candidates=[_growth("growth:qos2", "qos2Receiving.put")],
            links=[{
                "entry_id": "entry:mqtt",
                "growth_id": "growth:qos2",
                "status": "partial",
            }],
            flow_proofs=[{
                "entry_id": "entry:mqtt",
                "growth_id": "growth:qos2",
                "path_id": "flow:qos2",
                "confidence": "partial",
            }],
            findings=[{
                "entry_id": "entry:mqtt",
                "growth_id": "growth:qos2",
                "finding_id": "finding:qos2",
                "verdict": "static_unknown",
                "certificate_id": "certificate:qos2",
            }],
        )
        truth = {
            **_truth(
                "jmqtt-generic",
                "protocol service on port 18842",
                ["qos2Receiving.put"],
            ),
            "protocol": "mqtt",
        }

        result = compute_disposition(truth, artifacts)

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_entry_ids"], ["entry:mqtt"])

    def test_netty_body_truth_uses_sink_semantics_not_route_text_in_source_path(self):
        entry = _entry("entry:trigger", "/trigger", framework="netty", protocol="tcp")
        body = {
            "growth_id": "growth:body",
            "kind": "input_materialization",
            "operation": "netty_full_http_request_string_materialization",
            "site": {"file": "server/EmbedServer.java", "start_line": 163},
            "resource_point": {
                "dimension": "bytes",
                "receiver": "content(...)",
                "field_path": "msg",
                "resource_id": "resource:body",
            },
        }
        unrelated = {
            **_growth("growth:unrelated", "int[]"),
            "operation": "array_creation",
            "site": {
                "file": "scheduler/trigger/JobTrigger.java",
                "start_line": 94,
            },
        }
        artifacts = _artifacts(
            entries=[entry],
            growth_candidates=[unrelated, body],
            links=[{
                "entry_id": "entry:trigger",
                "growth_id": "growth:body",
                "status": "complete",
            }],
            flow_proofs=[{
                "entry_id": "entry:trigger",
                "growth_id": "growth:body",
                "path_id": "flow:body",
                "confidence": "proven",
            }],
            findings=[{
                "entry_id": "entry:trigger",
                "growth_id": "growth:body",
                "finding_id": "finding:body",
                "verdict": "static_unknown",
                "certificate_id": "certificate:body",
            }],
        )
        truth = {
            **_truth(
                "xxl-body",
                "/trigger",
                [
                    "Netty HttpObjectAggregator(5MiB), FullHttpRequest content "
                    "to UTF-8 String, and bizThreadPool max 200/queue 2000"
                ],
            ),
            "protocol": "http",
        }

        result = compute_disposition(truth, artifacts)

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_growth_ids"], ["growth:body"])

    def test_truth_markers_prefer_sink_over_entry_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attachments = root / "poc" / "case" / "attachments"
            attachments.mkdir(parents=True)
            (attachments / "static_finding.json").write_text(json.dumps({
                "source": "POST /trigger",
                "sink": "FullHttpRequest content to UTF-8 String",
            }))

            markers = _markers_for_record(
                {"output_dir": "poc/case", "entry": "/trigger"}, root
            )

            self.assertEqual(markers, ["FullHttpRequest content to UTF-8 String"])

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

    def test_growth_link_disambiguates_overlapping_controller_and_filter_routes(self):
        controller = _entry("entry:controller", "/erupt-api/data/table/{}")
        overlapping = _entry("entry:overlapping", "/erupt-api/data/{}/{}")
        filter_entry = _entry("entry:filter", "/erupt-api/*", framework="servlet")
        growth = _growth("growth:body", "stringBuilder")
        artifacts = _artifacts(
            entries=[controller, overlapping, filter_entry],
            growth_candidates=[growth],
            links=[{"entry_id": "entry:filter", "growth_id": "growth:body", "status": "partial"}],
            verified_growth=[{"growth_id": "growth:body", "status": "unresolved"}],
            flow_proofs=[{
                "entry_id": "entry:filter", "growth_id": "growth:body",
                "path_id": "flow:body", "confidence": "partial",
            }],
            findings=[{
                "entry_id": "entry:filter", "growth_id": "growth:body",
                "finding_id": "finding:body", "verdict": "static_unknown",
                "certificate_id": "certificate:body",
            }],
        )

        result = compute_disposition(
            _truth("erupt", "/erupt-api/data/table/EruptUser", ["stringBuilder"]),
            artifacts,
        )

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_entry_ids"], ["entry:filter"])
        self.assertEqual(result["matched_growth_ids"], ["growth:body"])

    def test_growth_linked_wildcard_entry_outranks_exact_unlinked_business_route(self):
        exact = _entry("entry:controller", "/container/downloadContainerTemplate")
        filter_entry = _entry("entry:filter", "/*", framework="servlet")
        growth = _growth("growth:body", "stringBuilder")
        artifacts = _artifacts(
            entries=[exact, filter_entry],
            growth_candidates=[growth],
            links=[{"entry_id": "entry:filter", "growth_id": "growth:body", "status": "partial"}],
            flow_proofs=[{
                "entry_id": "entry:filter", "growth_id": "growth:body",
                "path_id": "flow:body", "confidence": "partial",
            }],
            findings=[{
                "entry_id": "entry:filter", "growth_id": "growth:body",
                "finding_id": "finding:body", "verdict": "static_unknown",
                "certificate_id": "certificate:body",
            }],
        )

        result = compute_disposition(
            _truth("powerjob", "/container/downloadContainerTemplate", ["stringBuilder"]),
            artifacts,
        )

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_entry_ids"], ["entry:filter"])
        self.assertEqual(result["matched_growth_ids"], ["growth:body"])

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

    def test_truth_seed_resolves_symbolic_sink_from_referenced_static_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attachments = root / "poc" / "case" / "attachments"
            static_result = root / "frameworks" / "app" / "results" / "run"
            attachments.mkdir(parents=True)
            static_result.mkdir(parents=True)
            findings = static_result / "findings.jsonl"
            findings.write_text(json.dumps({
                "finding_id": "JL-STAGEA-0001",
                "sink": "S-CAPTCHA-BITMAP",
            }) + "\n")
            (static_result / "sinks.jsonl").write_text(json.dumps({
                "sink_id": "S-CAPTCHA-BITMAP",
                "file": "authentication/ImageCaptchaProvider.java",
                "line": 115,
                "operation": "new SpecCaptcha(width,height,length)",
            }) + "\n")
            (attachments / "source_result.json").write_text(json.dumps({
                "static_traceability": {
                    "sink": "S-CAPTCHA-BITMAP",
                    "static_result_file": str(findings),
                },
            }))

            locations = _sink_locations_for_record(
                {"output_dir": "poc/case"}, root, ["S-CAPTCHA-BITMAP"],
            )

            self.assertEqual(locations, [{
                "file": "authentication/ImageCaptchaProvider.java",
                "start_line": 115,
                "end_line": 115,
            }])

    def test_truth_seed_resolves_symbolic_sink_string_line_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attachments = root / "poc" / "case" / "attachments"
            static_result = root / "frameworks" / "app" / "results" / "run"
            attachments.mkdir(parents=True)
            static_result.mkdir(parents=True)
            findings = static_result / "findings.jsonl"
            findings.write_text(json.dumps({
                "finding_id": "GROBID-STATIC-001",
                "sink": "SINK-FULLTEXT-ZIP",
            }) + "\n")
            (static_result / "sinks.jsonl").write_text(json.dumps({
                "sink_id": "SINK-FULLTEXT-ZIP",
                "file": "service/GrobidRestProcessFiles.java",
                "line": "712-751",
                "operation": "ByteArrayOutputStream.toByteArray",
            }) + "\n")
            (attachments / "source_result.json").write_text(json.dumps({
                "static_traceability": {
                    "sink": "SINK-FULLTEXT-ZIP",
                    "static_result_file": str(findings),
                },
            }))

            locations = _sink_locations_for_record(
                {"output_dir": "poc/case"}, root, ["SINK-FULLTEXT-ZIP"],
            )

            self.assertEqual(locations, [{
                "file": "service/GrobidRestProcessFiles.java",
                "start_line": 712,
                "end_line": 751,
            }])

    def test_truth_seed_resolves_decorated_symbolic_sink_string_line_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attachments = root / "poc" / "case" / "attachments"
            static_result = root / "frameworks" / "app" / "results" / "run"
            attachments.mkdir(parents=True)
            static_result.mkdir(parents=True)
            findings = static_result / "findings.jsonl"
            findings.write_text(json.dumps({
                "finding_id": "GROBID-STATIC-001",
                "sink": "SINK-FULLTEXT-ZIP",
            }) + "\n")
            (static_result / "sinks.jsonl").write_text(json.dumps({
                "sink_id": "SINK-FULLTEXT-ZIP",
                "file": "service/GrobidRestProcessFiles.java",
                "line": "712-751",
                "operation": "ByteArrayOutputStream.toByteArray",
            }) + "\n")
            (attachments / "source_result.json").write_text(json.dumps({
                "static_traceability": {
                    "sink": "SINK-FULLTEXT-ZIP: ByteArrayOutputStream then toByteArray",
                    "static_result_file": str(findings),
                },
            }))

            locations = _sink_locations_for_record(
                {"output_dir": "poc/case"}, root,
                ["SINK-FULLTEXT-ZIP: ByteArrayOutputStream then toByteArray"],
            )

            self.assertEqual(locations, [{
                "file": "service/GrobidRestProcessFiles.java",
                "start_line": 712,
                "end_line": 751,
            }])

    def test_truth_seed_reads_evidence_from_referenced_jsonl_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attachments = root / "poc" / "case" / "attachments"
            static_result = root / "results" / "dynamic_validation_queue.jsonl"
            attachments.mkdir(parents=True)
            static_result.parent.mkdir(parents=True)
            sink = "ZipkinHttpCollector.validateAndStoreSpans aggregates request"
            static_result.write_text(json.dumps({
                "sink": sink,
                "evidence": [
                    "zipkin-server/src/main/java/zipkin2/server/internal/ZipkinHttpCollector.java:100 aggregates the request",
                    "zipkin-server/src/main/java/zipkin2/server/internal/Unrelated.java:20 auth",
                ],
            }) + "\n")
            (attachments / "source_result.json").write_text(json.dumps({
                "static_traceability": {
                    "sink": sink,
                    "static_result_file": str(static_result),
                },
            }))

            locations = _sink_locations_for_record(
                {"output_dir": "poc/case"}, root, [sink],
            )

            self.assertEqual(locations, [{
                "file": "zipkin-server/src/main/java/zipkin2/server/internal/ZipkinHttpCollector.java",
                "start_line": 100,
                "end_line": 100,
            }])

    def test_truth_seed_reads_nested_case_plan_traceability_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attachments = root / "poc" / "case" / "attachments"
            attachments.mkdir(parents=True)
            (attachments / "source_result.json").write_text(json.dumps({
                "static_traceability": {
                    "sink": "BomResource uses IOUtils.toByteArray",
                },
            }))
            (attachments / "case_plan.json").write_text(json.dumps({
                "static_traceability": {
                    "sink": "BomResource uses IOUtils.toByteArray",
                    "evidence": [
                        "apiserver/src/main/java/example/BomResource.java:706-710 multipart read",
                        "apiserver/src/main/java/example/Unrelated.java:20-30 auth",
                    ],
                },
            }))

            locations = _sink_locations_for_record(
                {"output_dir": "poc/case"}, root,
                ["BomResource uses IOUtils.toByteArray"],
            )

            self.assertEqual(locations, [{
                "file": "apiserver/src/main/java/example/BomResource.java",
                "start_line": 706,
                "end_line": 710,
            }])

    def test_route_placeholder_and_wildcard_matching(self):
        from dosweb.benchmark.disposition import _routes_match
        self.assertTrue(_routes_match("/erupt-api/data/table/{}", "/erupt-api/data/table/EruptUser"))
        self.assertTrue(_routes_match("/api/push/prometheus/**", "/api/push/prometheus/job/{}/instance/{}"))
        self.assertTrue(_routes_match("/api/push/prometheus/*", "/api/push/prometheus/job/demo/instance/a"))
        self.assertTrue(_routes_match("/agent/minTask", "/wgcloud/agent/minTask"))
        self.assertTrue(_routes_match("/a/b", "/a/b"))
        self.assertFalse(_routes_match("/a/b", "/a/c"))

    def test_context_path_route_and_declaring_receiver_location_match_full_chain(self):
        entry = _entry("entry:min-task", "/agent/minTask")
        growth = {
            "growth_id": "growth:batch-data",
            "site": {"file": "controller/AgentController.java", "start_line": 111},
            "operation": "java.util.List<AppInfo>.add",
            "resource_point": {
                "dimension": "entries",
                "receiver": "com.wgcloud.util.staticvar.BatchData.APP_INFO_LIST",
                "field_path": "APP_INFO_LIST",
                "resource_id": "resource:batch-data",
            },
        }
        artifacts = _artifacts(
            entries=[entry],
            growth_candidates=[growth],
            links=[{"entry_id": "entry:min-task", "growth_id": "growth:batch-data", "status": "complete"}],
            flow_proofs=[{
                "entry_id": "entry:min-task", "growth_id": "growth:batch-data",
                "path_id": "flow:batch-data", "confidence": "partial",
            }],
            findings=[{
                "entry_id": "entry:min-task", "growth_id": "growth:batch-data",
                "finding_id": "finding:batch-data", "verdict": "static_unknown",
                "certificate_id": "certificate:batch-data",
            }],
        )
        truth = {
            **_truth(
                "wgcloud", "/wgcloud/agent/minTask",
                ["BatchData static synchronizedList additions"],
            ),
            "sink_locations": [{
                "file": "util/staticvar/BatchData.java", "start_line": 18, "end_line": 56,
            }],
        }

        result = compute_disposition(truth, artifacts)

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_growth_ids"], ["growth:batch-data"])

    def test_receiver_type_matches_semantic_sink_across_source_line_drift(self):
        entry = _entry("entry:barcode", "/commons/barcode/render")
        growth = {
            "growth_id": "growth:buffered-image",
            "site": {"file": "support/BarCodeSupport.java", "start_line": 208},
            "operation": "java.awt.image.BufferedImage.<init>",
            "resource_point": {
                "dimension": "bytes",
                "receiver": "java.awt.image.BufferedImage",
                "field_path": "allocation",
                "resource_id": "resource:buffered-image",
            },
        }
        artifacts = _artifacts(
            entries=[entry],
            growth_candidates=[growth],
            links=[{"entry_id": "entry:barcode", "growth_id": "growth:buffered-image", "status": "partial"}],
            flow_proofs=[{
                "entry_id": "entry:barcode", "growth_id": "growth:buffered-image",
                "path_id": "flow:buffered-image", "confidence": "partial",
            }],
            findings=[{
                "entry_id": "entry:barcode", "growth_id": "growth:buffered-image",
                "finding_id": "finding:buffered-image", "verdict": "static_unknown",
                "certificate_id": "certificate:buffered-image",
            }],
        )
        truth = {
            **_truth(
                "barcode", "/commons/barcode/render",
                ["MatrixToImageWriter.toBufferedImage after Code128 encoding"],
            ),
            "sink_locations": [{
                "file": "support/BarCodeSupport.java", "start_line": 125, "end_line": 180,
            }],
        }

        result = compute_disposition(truth, artifacts)

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_growth_ids"], ["growth:buffered-image"])

    def test_linked_alias_route_applies_to_same_registration_truth_route(self):
        registration = {
            "kind": "annotation_mapping",
            "callable": "BarCodeController.render",
            "file": "BarCodeController.java",
            "start_line": 59,
        }
        truth_route = {
            **_entry("entry:render", "/commons/barcode/render"),
            "registration": registration,
            "handler": {
                "callable": "BarCodeController.render",
                "file": "BarCodeController.java",
                "start_line": 60,
            },
        }
        linked_alias = {
            **_entry("entry:render-auto", "GET /commons/barcode/render-auto"),
            "registration": registration,
            "handler": truth_route["handler"],
        }
        artifacts = _artifacts(
            entries=[truth_route, linked_alias],
            growth_candidates=[_growth("growth:barcode", "BufferedImage")],
            links=[{
                "entry_id": "entry:render-auto", "growth_id": "growth:barcode",
                "status": "partial",
            }],
            flow_proofs=[{
                "entry_id": "entry:render-auto", "growth_id": "growth:barcode",
                "path_id": "flow:barcode", "confidence": "partial",
            }],
            findings=[{
                "entry_id": "entry:render-auto", "growth_id": "growth:barcode",
                "finding_id": "finding:barcode", "verdict": "static_unknown",
                "certificate_id": "certificate:barcode",
            }],
        )

        result = compute_disposition(
            _truth("barcode", "/commons/barcode/render", ["BufferedImage"]),
            artifacts,
        )

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_finding_ids"], ["finding:barcode"])

    def test_exact_literal_route_outranks_placeholder_and_keeps_methodless_variant(self):
        registration = {
            "kind": "annotation_mapping",
            "callable": "TestController.save",
            "file": "TestController.java",
            "start_line": 72,
        }
        exact = {**_entry("entry:exact", "/test/user/save"), "registration": registration}
        exact_method = {**_entry("entry:exact-post", "POST /test/user/save"), "registration": registration}
        placeholder = _entry("entry:placeholder", "/test/user/{userId}")
        artifacts = _artifacts(
            entries=[exact, exact_method, placeholder],
            growth_candidates=[_growth("growth:save", "users.put")],
            links=[{"entry_id": "entry:exact", "growth_id": "growth:save", "status": "complete"}],
            flow_proofs=[{
                "entry_id": "entry:exact",
                "growth_id": "growth:save",
                "path_id": "flow:save",
                "confidence": "proven",
            }],
            findings=[{
                "entry_id": "entry:exact",
                "growth_id": "growth:save",
                "finding_id": "finding:save",
                "verdict": "static_unknown",
                "certificate_id": "certificate:save",
            }],
        )

        result = compute_disposition(
            _truth("save", "/test/user/save", ["users.put"]),
            artifacts,
        )

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertEqual(result["matched_entry_ids"], ["entry:exact"])

    def test_growth_link_selects_the_route_variant_used_by_the_analysis_chain(self):
        form_registration = {
            "kind": "annotation_mapping",
            "callable": "DemoController.add",
            "file": "DemoController.java",
            "start_line": 40,
        }
        save_registration = {
            "kind": "annotation_mapping",
            "callable": "DemoController.addSave",
            "file": "DemoController.java",
            "start_line": 50,
        }
        artifacts = _artifacts(
            entries=[
                {**_entry("entry:form", "/demo/add"), "registration": form_registration},
                {**_entry("entry:form-get", "GET /demo/add"), "registration": form_registration},
                {**_entry("entry:save", "/demo/add"), "registration": save_registration},
                {**_entry("entry:save-post", "POST /demo/add"), "registration": save_registration},
            ],
            growth_candidates=[_growth("growth:save", "users.put")],
            links=[{"entry_id": "entry:save-post", "growth_id": "growth:save", "status": "complete"}],
            flow_proofs=[{
                "entry_id": "entry:save-post",
                "growth_id": "growth:save",
                "path_id": "flow:save",
                "confidence": "proven",
            }],
            findings=[{
                "entry_id": "entry:save-post",
                "growth_id": "growth:save",
                "finding_id": "finding:save",
                "verdict": "static_unknown",
                "certificate_id": "certificate:save",
            }],
        )

        result = compute_disposition(_truth("save", "/demo/add", ["users.put"]), artifacts)

        self.assertEqual(result["status"], "full_chain_finding")
        self.assertIn("entry:save-post", result["matched_entry_ids"])


if __name__ == "__main__":
    unittest.main()
