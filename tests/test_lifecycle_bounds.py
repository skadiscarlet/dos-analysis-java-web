from __future__ import annotations

import unittest

from dosweb.entries import AttackerInputFact, EntryFact, HandlerFact, RegistrationFact
from dosweb.flows import AttackerControl, FlowProof, verify_flow
from dosweb.lifecycle import (
    BoundCandidate,
    ModeledConfiguration,
    evaluate_bound,
    normalize_framework_limit,
)
from tests.test_lifecycle_guards import GuardEvaluationTests


class BoundEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        helper = GuardEvaluationTests()
        helper.setUp()
        self.entry, self.growth, self.flow = helper.entry, helper.growth, helper.flow
        self.config = ModeledConfiguration((('queue.capacity', 64),))

    def _candidate(self, **changes: object) -> BoundCandidate:
        values: dict[str, object] = {
            "site_file": "fixture/netty/NettyFixture.java", "site_start_line": 41,
            "kind": "capacity", "resource_dimension": "bytes", "scope": "request",
            "behavior": "reject", "receiver": "java.nio.ByteBuffer", "field_path": "allocation",
            "result_checked": True, "configuration_key": "queue.capacity", "configuration_value": "64",
            "phase": "inside_growth", "covers_flow": True, "request_encoding": "raw_body",
            "queue_resource": "allocation", "product_bound": True, "evidence": ("fact:bound",),
            "coverage_status": "complete",
        }
        values.update(changes)
        return BoundCandidate.create(**values)

    def _framework_path(self, framework: str):
        protocol = {"spring_mvc": "http", "servlet": "http", "netty": "tcp"}[framework]
        registration_kind = (
            "pipeline_registration" if framework == "netty" else "annotation_mapping"
        )
        entry = EntryFact.create(
            framework=framework,
            protocol=protocol,
            handler=HandlerFact(
                f"fixture.{framework}.Handler.handle",
                f"fixture/{framework}/Handler.java",
                15,
            ),
            registration=RegistrationFact(
                registration_kind,
                f"fixture.{framework}.Handler",
                f"fixture/{framework}/Handler.java",
                8,
            ),
            registration_pattern_id={
                "spring_mvc": "entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
                "servlet": "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
                "netty": "entry-registration-coverage:netty:pipeline_registration:netty_pipeline_registration",
            }[framework],
            route_or_event="/bounded",
            auth_context="unauthenticated",
            attacker_inputs=(
                AttackerInputFact(
                    "limit",
                    "int",
                    "message_payload" if framework == "netty" else "request_parameter",
                ),
            ),
            materialization_phase="in_handler",
        )
        proof = FlowProof.create(
            entry_id=entry.entry_id,
            growth_id=self.growth.growth_id,
            attacker_control=AttackerControl("size", "limit", "allocate(limit)"),
            call_path=(entry.handler.callable,),
            phase_sequence=("in_handler", "growth"),
            confidence="proven",
        )
        flow = verify_flow(
            proof,
            {entry.entry_id: entry},
            {self.growth.growth_id: self.growth},
        )
        return entry, flow

    def test_candidate_rejects_string_boolean_coercion(self) -> None:
        for field in ("result_checked", "covers_flow", "product_bound"):
            with self.subTest(field=field):
                with self.assertRaises(Exception):
                    self._candidate(**{field: "false"})

    def test_all_bound_states(self) -> None:
        cases = (
            ((), "absent"),
            ((self._candidate(scope="global"),), "scope_mismatched"),
            ((self._candidate(resource_dimension="entries"),), "dimension_mismatched"),
            ((self._candidate(result_checked=False),), "possibly_over_budget"),
            ((self._candidate(),), "effective"),
            ((self._candidate(coverage_status="partial"),), "unknown"),
        )
        for candidates, status in cases:
            with self.subTest(status=status):
                self.assertEqual(evaluate_bound(self.entry, self.growth, self.flow, candidates, self.config).status, status)

    def test_empty_partial_coverage_is_unknown_but_complete_is_absent(self) -> None:
        self.assertEqual(
            evaluate_bound(self.entry, self.growth, self.flow, (), self.config, coverage_status="partial").status,
            "unknown",
        )
        self.assertEqual(
            evaluate_bound(self.entry, self.growth, self.flow, (), self.config, coverage_status="complete").status,
            "absent",
        )

    def test_positive_literal_capacity_does_not_require_external_configuration(self) -> None:
        effective = evaluate_bound(
            self.entry,
            self.growth,
            self.flow,
            (self._candidate(configuration_key="literal", configuration_value="64"),),
            ModeledConfiguration(()),
        )
        self.assertEqual("effective", effective.status)
        invalid = evaluate_bound(
            self.entry,
            self.growth,
            self.flow,
            (self._candidate(configuration_key="literal", configuration_value="0"),),
            ModeledConfiguration(()),
        )
        self.assertEqual("unknown", invalid.status)

    def test_numeric_clamp_is_an_effective_literal_bound(self) -> None:
        clamp = self._candidate(
            kind="limit",
            behavior="clamp",
            configuration_key="literal",
            configuration_value="1024",
        )

        decision = evaluate_bound(
            self.entry,
            self.growth,
            self.flow,
            (clamp,),
            ModeledConfiguration(()),
        )

        self.assertEqual("effective", decision.status)

    def test_bound_requires_same_receiver_and_consistent_enabled_configuration(self) -> None:
        cases = (
            ({"receiver": "other"}, self.config, "BOUND_RECEIVER_MISMATCH"),
            ({"configuration_value": "1024"}, self.config, "BOUND_CONFIGURATION_MISMATCH"),
            ({}, ModeledConfiguration((('queue.capacity', 'disabled'),)), "BOUND_DISABLED_CONFIGURATION"),
        )
        for changes, config, reason in cases:
            with self.subTest(reason=reason):
                result = evaluate_bound(self.entry, self.growth, self.flow, (self._candidate(**changes),), config)
                self.assertNotEqual(result.status, "effective")
                self.assertIn(reason, result.reason_codes)

    def test_required_false_safe_bound_examples(self) -> None:
        cases = (
            ({"result_checked": False}, "BOUND_RESULT_IGNORED"),
            ({"queue_resource": "executor_pool"}, "BOUND_QUEUE_CONFIGURATION_MISMATCH"),
            ({"request_encoding": "multipart"}, "BOUND_REQUEST_ENCODING_MISMATCH"),
            ({"request_encoding": "content_length_only"}, "BOUND_REQUEST_ENCODING_MISMATCH"),
            ({"product_bound": False}, "BOUND_MULTIPLICATIVE_DEMAND_UNCOVERED"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason):
                result = evaluate_bound(self.entry, self.growth, self.flow, (self._candidate(**changes),), self.config)
                self.assertEqual(result.status, "possibly_over_budget")
                self.assertIn(reason, result.reason_codes)

    def test_known_framework_limits_are_effective_only_on_the_exact_path(self) -> None:
        cases = (
            (
                "spring_mvc",
                "json",
                "jackson_stream_read_constraints_literal",
                ModeledConfiguration(()),
                "literal",
            ),
            (
                "netty",
                "aggregated_http",
                "netty_http_object_aggregator_literal",
                ModeledConfiguration(()),
                "literal",
            ),
            (
                "spring_mvc",
                "multipart",
                "servlet_multipart_config_literal",
                ModeledConfiguration(()),
                "literal",
            ),
            (
                "servlet",
                "form_urlencoded",
                "solr_formdata_upload_limit_literal",
                ModeledConfiguration(()),
                "literal",
            ),
        )
        for framework, encoding, evidence, configuration, key in cases:
            with self.subTest(evidence=evidence):
                entry, flow = self._framework_path(framework)
                candidate = self._candidate(
                    kind="limit",
                    configuration_key=key,
                    configuration_value="1024",
                    phase="before_growth",
                    request_encoding=encoding,
                    evidence=(evidence,),
                )
                result = normalize_framework_limit(
                    entry=entry,
                    growth=self.growth,
                    flow=flow,
                    candidate=candidate,
                    configuration=configuration,
                )
                self.assertEqual(result.status, "effective", result.reason_codes)

    def test_framework_limit_mismatch_fail_open_and_unknown_value_do_not_verify(self) -> None:
        entry, flow = self._framework_path("spring_mvc")
        base = {
            "kind": "limit",
            "configuration_key": "literal",
            "configuration_value": "1024",
            "phase": "before_growth",
            "request_encoding": "multipart",
            "evidence": ("servlet_multipart_config_literal",),
        }
        cases = (
            ({"request_encoding": "raw_body"}, ModeledConfiguration(()), "BOUND_REQUEST_ENCODING_MISMATCH"),
            ({"behavior": "unknown"}, ModeledConfiguration(()), "BOUND_POSSIBLY_OVER_BUDGET"),
            ({"phase": "post_growth"}, ModeledConfiguration(()), "BOUND_POSSIBLY_OVER_BUDGET"),
            ({"scope": "global"}, ModeledConfiguration(()), "BOUND_SCOPE_MISMATCH"),
            ({"configuration_value": "unknown"}, ModeledConfiguration(()), "BOUND_CONFIGURATION_UNKNOWN"),
            ({"coverage_status": "partial"}, ModeledConfiguration(()), "BOUND_COVERAGE_UNKNOWN"),
            ({"configuration_key": "spring.servlet.multipart.max-request-size"}, ModeledConfiguration((("spring.servlet.multipart.max-request-size", 1024),)), "BOUND_CONFIGURATION_PROVENANCE_MISMATCH"),
        )
        for changes, configuration, reason in cases:
            with self.subTest(reason=reason):
                candidate = self._candidate(**{**base, **changes})
                result = normalize_framework_limit(
                    entry=entry,
                    growth=self.growth,
                    flow=flow,
                    candidate=candidate,
                    configuration=configuration,
                )
                self.assertNotEqual(result.status, "effective")
                self.assertIn(reason, result.reason_codes)

        wrong_framework = normalize_framework_limit(
            entry=entry,
            growth=self.growth,
            flow=flow,
            candidate=self._candidate(
                kind="limit",
                configuration_key="literal",
                configuration_value="1024",
                phase="before_growth",
                request_encoding="aggregated_http",
                evidence=("netty_http_object_aggregator_literal",),
            ),
            configuration=ModeledConfiguration(()),
        )
        self.assertNotEqual(wrong_framework.status, "effective")
        self.assertIn("BOUND_FRAMEWORK_MISMATCH", wrong_framework.reason_codes)


if __name__ == "__main__":
    unittest.main()
