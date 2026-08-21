from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.artifacts.schemas import validate_records
from dosweb.entries import (
    AttackerInputFact,
    EntryFact,
    FrameworkCoverage,
    load_entry_facts,
    normalize_entry_rows,
    normalize_framework_coverage,
    normalize_gap_entry_rows,
)
from dosweb.errors import AnalyzerError


class EntryNormalizationTests(unittest.TestCase):
    def _row(self, **overrides: object) -> dict[str, object]:
        row: dict[str, object] = {
            "framework": "spring_mvc",
            "protocol": "http",
            "handler_fqn": "fixture.spring.SpringFixture.handle",
            "handler_file": "fixture/spring/SpringFixture.java",
            "handler_start_line": 10,
            "registration_kind": "annotation_mapping",
            "registration_fqn": "fixture.spring.SpringFixture.handle",
            "registration_file": "fixture/spring/SpringFixture.java",
            "registration_start_line": 8,
            "route_or_event": "/items",
            "auth_context": "unknown",
            "attacker_input_name": "body",
            "attacker_input_type": "byte[]",
            "attacker_input_kind": "request_body",
            "materialization_phase": "before_handler",
            "coverage_status": "complete",
            "coverage_note": "spring_annotation_mapping",
            "query_name": "entries",
            "query_sha256": "a" * 64,
            "handler_location": {
                "file": "fixture/spring/SpringFixture.java",
                "start_line": 10,
            },
            "registration_location": {
                "file": "fixture/spring/SpringFixture.java",
                "start_line": 8,
            },
        }
        row.update(overrides)
        return row

    def test_entry_fact_matches_the_stable_semantic_identity(self):
        fact = EntryFact.from_raw(self._row())
        semantic_identity = {
            "framework": "spring_mvc",
            "protocol": "http",
            "handler": {
                "callable": "fixture.spring.SpringFixture.handle",
                "file": "fixture/spring/SpringFixture.java",
                "start_line": 10,
            },
            "registration": {
                "kind": "annotation_mapping",
                "callable": "fixture.spring.SpringFixture.handle",
                "file": "fixture/spring/SpringFixture.java",
                "start_line": 8,
            },
            "route_or_event": "/items",
            "auth_context": "unknown",
            "attacker_inputs": [
                {"name": "body", "type": "byte[]", "kind": "request_body"}
            ],
            "materialization_phase": "before_handler",
        }
        self.assertEqual(fact.entry_id, stable_identifier("entry", semantic_identity))
        self.assertEqual(fact.to_dict(), {"entry_id": fact.entry_id, **semantic_identity})
        self.assertIsInstance(fact.attacker_inputs[0], AttackerInputFact)

    def test_normalized_entry_round_trips_through_strict_deserialization(self):
        fact = EntryFact.from_raw(self._row())
        self.assertEqual(EntryFact.from_dict(fact.to_dict()), fact)

    def test_normalized_entry_deserialization_rejects_shape_and_identity_changes(self):
        record = EntryFact.from_raw(self._row()).to_dict()
        variants: list[dict[str, object]] = []

        extra = dict(record)
        extra["unexpected"] = "value"
        variants.append(extra)

        malformed_handler = dict(record)
        malformed_handler["handler"] = {
            "callable": "fixture.Handler.handle",
            "file": "fixture/Handler.java",
        }
        variants.append(malformed_handler)

        malformed_inputs = dict(record)
        malformed_inputs["attacker_inputs"] = {
            "name": "body",
            "type": "byte[]",
            "kind": "request_body",
        }
        variants.append(malformed_inputs)

        wrong_identity = dict(record)
        wrong_identity["entry_id"] = "entry:" + "0" * 24
        variants.append(wrong_identity)

        for variant in variants:
            with self.subTest(variant=variant):
                with self.assertRaises(AnalyzerError) as raised:
                    EntryFact.from_dict(variant)
                self.assertEqual(raised.exception.code, "ANALYSIS_ENTRY_INVALID")

    def test_normalized_entry_loader_composes_strict_jsonl_and_identity_validation(self):
        fact = EntryFact.from_raw(self._row())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry_facts.jsonl"
            path.write_bytes(canonical_json(fact.to_dict()) + b"\n")
            self.assertEqual(load_entry_facts(path), (fact,))

            malformed = fact.to_dict()
            malformed["entry_id"] = "entry:" + "0" * 24
            path.write_bytes(canonical_json(malformed) + b"\n")
            with self.assertRaises(AnalyzerError) as raised:
                load_entry_facts(path)
            self.assertEqual(raised.exception.code, "ANALYSIS_ENTRY_INVALID")

    def test_normalization_is_row_order_independent_and_deduplicates_inputs(self):
        body = self._row()
        parameter = self._row(
            attacker_input_name="limit",
            attacker_input_type="int",
            attacker_input_kind="request_parameter",
        )
        first = normalize_entry_rows([parameter, body, parameter])
        second = normalize_entry_rows([body, parameter])
        self.assertEqual(first, second)
        self.assertEqual(
            first[0]["attacker_inputs"],
            [
                {"name": "body", "type": "byte[]", "kind": "request_body"},
                {"name": "limit", "type": "int", "kind": "request_parameter"},
            ],
        )
        validate_records("entry_facts", first)

    def test_http_routes_preserve_optional_method_during_canonicalization(self):
        cases = (
            (self._row(route_or_event="//api///items/"), "/api/items"),
            (self._row(route_or_event="POST //api///items/"), "POST /api/items"),
            (
                self._row(
                    framework="jax_rs",
                    protocol="http",
                    registration_kind="static_registration",
                    route_or_event="GET //api//items/{id}",
                ),
                "GET /api/items/{id}",
            ),
        )
        for row, expected in cases:
            with self.subTest(framework=row["framework"], route=row["route_or_event"]):
                normalized = normalize_entry_rows([row])
                self.assertEqual(normalized[0]["route_or_event"], expected)

    def test_framework_specific_registration_is_required(self):
        cases = (
            self._row(framework="servlet", registration_kind="pipeline_registration"),
            self._row(
                framework="netty",
                protocol="tcp",
                route_or_event="channelRead",
                materialization_phase="streaming",
                registration_kind="static_registration",
            ),
            self._row(
                framework="mqtt",
                protocol="mqtt",
                route_or_event="topic/items",
                materialization_phase="streaming",
                registration_kind="static_registration",
            ),
        )
        for row in cases:
            with self.subTest(framework=row["framework"]):
                with self.assertRaises(AnalyzerError) as raised:
                    EntryFact.from_raw(row)
                self.assertEqual(raised.exception.code, "ANALYSIS_ENTRY_INVALID")

    def test_registered_servlet_netty_and_mqtt_rows_are_accepted(self):
        rows = (
            self._row(
                framework="servlet",
                handler_fqn="fixture.servlet.RegisteredServlet.doPost",
                registration_kind="annotation_mapping",
                registration_fqn="fixture.servlet.RegisteredServlet",
            ),
            self._row(
                framework="netty",
                protocol="tcp",
                handler_fqn="fixture.netty.RegisteredHandler.channelRead",
                registration_kind="pipeline_registration",
                registration_fqn="fixture.netty.FixtureInitializer.initChannel",
                route_or_event="channelRead",
                attacker_input_name="msg",
                attacker_input_type="java.lang.Object",
                attacker_input_kind="message_payload",
                materialization_phase="streaming",
            ),
            self._row(
                framework="mqtt",
                protocol="mqtt",
                handler_fqn="fixture.mqtt.RegisteredListener.messageArrived",
                registration_kind="subscription_registration",
                registration_fqn="fixture.mqtt.MqttFixture.register",
                route_or_event="items/topic",
                attacker_input_name="message",
                attacker_input_type="MqttMessage",
                attacker_input_kind="message_payload",
                materialization_phase="streaming",
            ),
            self._row(
                framework="mqtt",
                protocol="mqtt",
                handler_fqn="org.jmqtt.mqtt.netty.NettyMqttHandler.channelRead",
                registration_kind="broker_registration",
                registration_fqn="org.jmqtt.mqtt.netty.MqttRemotingServer.initChannel",
                route_or_event="mqtt_protocol",
                attacker_input_name="message",
                attacker_input_type="io.netty.handler.codec.mqtt.MqttMessage",
                attacker_input_kind="message_payload",
                materialization_phase="streaming",
            ),
        )
        normalized = normalize_entry_rows(rows)
        self.assertEqual({entry["framework"] for entry in normalized}, {"servlet", "netty", "mqtt"})
        self.assertIn("broker_registration", {entry["registration"]["kind"] for entry in normalized})

    def test_unknown_auth_is_not_promoted_to_unauthenticated(self):
        normalized = normalize_entry_rows([self._row(auth_context="unknown")])
        self.assertEqual(normalized[0]["auth_context"], "unknown")

    def test_framework_protocol_pairs_are_strict(self):
        invalid = (
            self._row(protocol="tcp"),
            self._row(framework="servlet", protocol="mqtt"),
            self._row(
                framework="netty",
                protocol="http",
                registration_kind="pipeline_registration",
            ),
            self._row(
                framework="mqtt",
                protocol="tcp",
                registration_kind="subscription_registration",
            ),
        )
        for row in invalid:
            with self.subTest(framework=row["framework"], protocol=row["protocol"]):
                with self.assertRaises(AnalyzerError) as raised:
                    normalize_entry_rows([row])
                self.assertEqual(raised.exception.code, "ANALYSIS_ENTRY_INVALID")

    def test_dynamic_registration_only_emits_forcing_coverage(self):
        dynamic = self._row(
            registration_kind="dynamic_unresolved",
            coverage_status="partial",
            coverage_note="reflection_controller_registration",
        )
        self.assertEqual(normalize_entry_rows([dynamic]), [])
        coverage = normalize_framework_coverage([dynamic])
        self.assertEqual(len(coverage), 6)
        self.assertIn(
            {
                "framework": "spring_mvc",
                "status": "partial",
                "supported_patterns": [],
                "unsupported_patterns": ["reflection_controller_registration"],
                "effect_on_verdict": "forces_unknown",
            },
            coverage,
        )

    def test_dynamic_registration_persists_concrete_route_as_gap_only(self):
        dynamic = self._row(
            framework="jax_rs",
            registration_kind="dynamic_unresolved",
            route_or_event="POST /api/v2/process/{id}/log/segment/{segmentId}",
            coverage_status="partial",
            coverage_note="annotation_only_jax_rs_resource",
        )
        self.assertEqual(normalize_entry_rows([dynamic]), [])
        gaps = normalize_gap_entry_rows([
            dynamic,
            dict(dynamic),
            {**dynamic, "attacker_input_name": "other-parameter"},
        ])
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["framework"], "jax_rs")
        self.assertEqual(gaps[0]["route_or_event"], dynamic["route_or_event"])
        validate_records("entry_gap_facts", gaps)

    def test_smqtt_protocol_gap_is_persisted_only_for_specific_source_diagnostic(self):
        smqtt = self._row(
            framework="mqtt",
            protocol="mqtt",
            registration_kind="dynamic_unresolved",
            route_or_event="mqtt_protocol",
            handler_fqn="io.github.quickmsg.core.mqtt.MqttReceiver.newTcpServer",
            handler_file="smqtt-core/src/main/java/io/github/quickmsg/core/mqtt/MqttReceiver.java",
            handler_start_line=26,
            registration_fqn="io.github.quickmsg.core.mqtt.MqttReceiver.newTcpServer",
            registration_file="smqtt-core/src/main/java/io/github/quickmsg/core/mqtt/MqttReceiver.java",
            registration_start_line=42,
            coverage_status="partial",
            coverage_note="smqtt_protocol_dispatch_binding_unresolved",
        )
        gaps = normalize_gap_entry_rows([smqtt])
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["route_or_event"], "mqtt_protocol")
        validate_records("entry_gap_facts", gaps)

        generic = {**smqtt, "coverage_note": "generic_mqtt_protocol_gap"}
        self.assertEqual(normalize_gap_entry_rows([generic]), [])
        exact_note_but_not_query_shape = {
            **smqtt,
            "handler_fqn": "example.MqttReceiver.newTcpServer",
            "registration_fqn": "example.MqttReceiver.newTcpServer",
        }
        self.assertEqual(normalize_gap_entry_rows([exact_note_but_not_query_shape]), [])
        exact_note_but_mismatched_registration = {
            **smqtt,
            "registration_fqn": "io.github.quickmsg.core.mqtt.OtherReceiver.newTcpServer",
        }
        self.assertEqual(normalize_gap_entry_rows([exact_note_but_mismatched_registration]), [])

    def test_dynamic_placeholder_route_is_not_persisted_as_gap_identity(self):
        dynamic = self._row(
            framework="servlet",
            registration_kind="dynamic_unresolved",
            route_or_event="dynamic_servlet_mapping",
            coverage_status="partial",
            coverage_note="dynamic_servlet_mapping",
        )
        self.assertEqual(normalize_gap_entry_rows([dynamic]), [])

    def test_entry_gap_schema_rejects_unsafe_location_and_nonpositive_line(self):
        dynamic = self._row(
            framework="jax_rs",
            registration_kind="dynamic_unresolved",
            route_or_event="POST /items",
            coverage_status="partial",
            coverage_note="annotation_only_jax_rs_resource",
        )
        gap = normalize_gap_entry_rows([dynamic])[0]
        invalid_records = [
            {**gap, "gap_id": "entry:not-a-gap"},
            {**gap, "handler_file": "../outside.java"},
            {**gap, "handler_file": "/absolute.java"},
            {**gap, "handler_start_line": 0},
        ]
        for record in invalid_records:
            with self.subTest(record=record):
                with self.assertRaises(AnalyzerError):
                    validate_records("entry_gap_facts", [record])

    def test_coverage_aggregates_supported_and_unsupported_patterns(self):
        coverage = normalize_framework_coverage(
            [
                self._row(coverage_note="spring_annotation_mapping"),
                self._row(
                    registration_kind="dynamic_unresolved",
                    coverage_status="partial",
                    coverage_note="dynamic_route_expression",
                ),
                self._row(coverage_note="spring_annotation_mapping"),
            ]
        )
        self.assertEqual(len(coverage), 6)
        self.assertIn(
            {
                "framework": "spring_mvc",
                "status": "partial",
                "supported_patterns": ["spring_annotation_mapping"],
                "unsupported_patterns": ["dynamic_route_expression"],
                "effect_on_verdict": "forces_unknown",
            },
            coverage,
        )

    def test_framework_coverage_rejects_inconsistent_effect(self):
        with self.assertRaises(AnalyzerError) as raised:
            FrameworkCoverage(
                framework="netty",
                status="partial",
                supported_patterns=(),
                unsupported_patterns=("dynamic_pipeline_registration",),
                effect_on_verdict="none",
            )
        self.assertEqual(raised.exception.code, "COVERAGE_ENTRY_INVALID")

    def test_coverage_validates_complete_and_gap_rows(self):
        malformed_complete = self._row(registration_kind="pipeline_registration")
        malformed_gap = self._row(
            registration_kind="dynamic_unresolved",
            coverage_status="partial",
            coverage_note="dynamic_route",
            handler_start_line=0,
        )
        hostile_status = self._row(coverage_status=[])
        for row in (malformed_complete, malformed_gap, hostile_status):
            with self.subTest(row=row):
                with self.assertRaises(AnalyzerError) as raised:
                    normalize_framework_coverage([row])
                self.assertIn(
                    raised.exception.code,
                    {"ANALYSIS_ENTRY_INVALID", "COVERAGE_ENTRY_INVALID"},
                )

    def test_empty_coverage_emits_all_framework_unknown_records(self):
        coverage = normalize_framework_coverage([])
        self.assertEqual(
            {record["framework"] for record in coverage},
            {"spring_mvc", "servlet", "netty", "mqtt", "jax_rs", "grpc"},
        )
        self.assertTrue(
            all(
                record["status"] == "unsupported"
                and record["effect_on_verdict"] == "forces_unknown"
                and record["unsupported_patterns"] == ["no_entry_query_evidence"]
                for record in coverage
            )
        )

    def test_entry_create_rejects_invalid_nested_inputs_cleanly(self):
        with self.assertRaises(AnalyzerError) as raised:
            EntryFact.create(
                framework="spring_mvc",
                protocol="http",
                handler=object(),  # type: ignore[arg-type]
                registration=object(),  # type: ignore[arg-type]
                route_or_event="/items",
                auth_context="unknown",
                attacker_inputs=(object(),),  # type: ignore[arg-type]
                materialization_phase="before_handler",
            )
        self.assertEqual(raised.exception.code, "ANALYSIS_ENTRY_INVALID")

    def test_malformed_rows_fail_with_stable_bounded_errors(self):
        variants = []
        missing = self._row()
        del missing["handler_fqn"]
        variants.append(missing)
        variants.append(self._row(handler_start_line=True))
        variants.append(self._row(route_or_event=""))
        variants.append(self._row(unexpected="value"))
        variants.append(
            self._row(
                registration_kind="dynamic_unresolved",
                coverage_status="complete",
                coverage_note="dynamic_registration",
            )
        )
        for row in variants:
            with self.subTest(row=row):
                with self.assertRaises(AnalyzerError) as raised:
                    normalize_entry_rows([row])
                self.assertIn(raised.exception.code, {"ANALYSIS_ENTRY_INVALID", "COVERAGE_ENTRY_INVALID"})
                self.assertLess(len(repr(raised.exception.details)), 1000)


if __name__ == "__main__":
    unittest.main()
