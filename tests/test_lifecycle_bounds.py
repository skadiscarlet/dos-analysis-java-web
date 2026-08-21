from __future__ import annotations

import unittest

from dosweb.lifecycle import BoundCandidate, ModeledConfiguration, evaluate_bound
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


if __name__ == "__main__":
    unittest.main()
