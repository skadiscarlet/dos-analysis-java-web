from __future__ import annotations

import unittest

from dosweb.lifecycle import GuardCandidate, ModeledConfiguration, evaluate_guard
from tests.test_flow_verification import FlowVerificationTests


class GuardEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        helper = FlowVerificationTests()
        self.entry = helper._entry()
        self.growth = helper._growth()
        record = helper._raw()
        from dosweb.flows import FlowProof, normalize_flow_rows, verify_flow
        proof = FlowProof.from_dict(normalize_flow_rows((record,), {self.entry.entry_id: self.entry}, {self.growth.growth_id: self.growth})[0])
        self.flow = verify_flow(proof, {self.entry.entry_id: self.entry}, {self.growth.growth_id: self.growth})
        self.config = ModeledConfiguration((('request.max-bytes', 1024),))

    def _candidate(self, **changes: object) -> GuardCandidate:
        values: dict[str, object] = {
            "site_file": "fixture/spring/SpringFixture.java", "site_start_line": 16,
            "kind": "input_validation", "resource_dimension": "bytes", "scope": "request",
            "behavior": "reject", "dominates_growth": True, "reject_path_reaches_growth": False,
            "configuration_key": "request.max-bytes", "configuration_value": "1024",
            "representation": "raw_body", "phase": "before_growth", "covers_materialization": True,
            "authorization_only": False, "evidence": ("fact:guard",), "coverage_status": "complete",
        }
        values.update(changes)
        return GuardCandidate.create(**values)

    def test_candidate_rejects_string_boolean_coercion(self) -> None:
        for field in (
            "dominates_growth",
            "reject_path_reaches_growth",
            "covers_materialization",
            "authorization_only",
        ):
            with self.subTest(field=field):
                with self.assertRaises(Exception):
                    self._candidate(**{field: "false"})

    def test_effective_guard_requires_all_checks(self) -> None:
        result = evaluate_guard(self.entry, self.growth, self.flow, (self._candidate(),), self.config)
        self.assertEqual(result.status, "effective")
        self.assertFalse(result.reason_codes)
        self.assertTrue(all(check.passed for check in result.checks))

    def test_known_false_safe_patterns_have_stable_reasons(self) -> None:
        cases = (
            ({"phase": "after_materialization"}, "GUARD_AFTER_MATERIALIZATION"),
            ({"dominates_growth": False}, "GUARD_DOES_NOT_DOMINATE_FLOW"),
            ({"reject_path_reaches_growth": True}, "GUARD_REJECT_PATH_REACHES_GROWTH"),
            ({"resource_dimension": "entries"}, "GUARD_DIMENSION_MISMATCH"),
            ({"representation": "multipart"}, "GUARD_REPRESENTATION_MISMATCH"),
            ({"authorization_only": True}, "GUARD_AUTHORIZATION_ONLY"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason):
                result = evaluate_guard(self.entry, self.growth, self.flow, (self._candidate(**changes),), self.config)
                self.assertEqual(result.status, "ineffective")
                self.assertIn(reason, result.reason_codes)

    def test_unknown_and_unbounded_configuration_do_not_verify(self) -> None:
        unknown = evaluate_guard(self.entry, self.growth, self.flow, (self._candidate(configuration_key="missing"),), self.config)
        unbounded = evaluate_guard(self.entry, self.growth, self.flow, (self._candidate(),), ModeledConfiguration((('request.max-bytes', 'unbounded'),)))
        self.assertEqual(unknown.status, "unknown")
        self.assertIn("GUARD_CONFIGURATION_UNKNOWN", unknown.reason_codes)
        self.assertEqual(unbounded.status, "ineffective")
        self.assertIn("GUARD_UNBOUNDED_CONFIGURATION", unbounded.reason_codes)

    def test_candidate_configuration_value_must_match_modeled_value(self) -> None:
        result = evaluate_guard(
            self.entry, self.growth, self.flow,
            (self._candidate(configuration_value="8192"),), self.config,
        )
        self.assertNotEqual(result.status, "effective")
        self.assertIn("GUARD_CONFIGURATION_MISMATCH", result.reason_codes)

    def test_candidate_order_does_not_change_decision_and_refs_are_retained(self) -> None:
        good = self._candidate()
        bad = self._candidate(site_start_line=17, dominates_growth=False, evidence=("fact:bad",))
        left = evaluate_guard(self.entry, self.growth, self.flow, (bad, good), self.config)
        right = evaluate_guard(self.entry, self.growth, self.flow, (good, bad), self.config)
        self.assertEqual(left, right)
        self.assertEqual(set(left.candidate_ids), {good.guard_id, bad.guard_id})


if __name__ == "__main__":
    unittest.main()
