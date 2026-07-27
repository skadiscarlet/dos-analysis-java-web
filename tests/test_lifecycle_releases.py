from __future__ import annotations

import unittest

from dosweb.lifecycle import ReleaseCandidate, evaluate_synchronous_release
from tests.test_lifecycle_guards import GuardEvaluationTests


class ReleaseEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        helper = GuardEvaluationTests()
        helper.setUp()
        self.entry, self.growth, self.flow = helper.entry, helper.growth, helper.flow

    def _candidate(self, **changes: object) -> ReleaseCandidate:
        values: dict[str, object] = {
            "site_file": "fixture/servlet/ServletFixture.java", "site_start_line": 32,
            "kind": "remove", "resource_dimension": "bytes", "scope": "request",
            "receiver": "java.nio.ByteBuffer", "key_identity": "limit", "synchronous": True,
            "normal_path": True, "exceptional_path": True, "actual_reduction": True,
            "after_growth": True, "transfer_only": False, "async_kind": "none",
            "evidence": ("fact:release",), "coverage_status": "complete",
        }
        values.update(changes)
        return ReleaseCandidate.create(**values)

    def test_candidate_rejects_string_boolean_coercion(self) -> None:
        for field in (
            "synchronous",
            "normal_path",
            "exceptional_path",
            "actual_reduction",
            "after_growth",
            "transfer_only",
        ):
            with self.subTest(field=field):
                with self.assertRaises(Exception):
                    self._candidate(**{field: "false"})

    def test_matching_try_finally_release_is_synchronous_effective(self) -> None:
        result = evaluate_synchronous_release(self.entry, self.growth, self.flow, (self._candidate(),))
        self.assertEqual(result.status, "effective")
        self.assertEqual(result.classification, "synchronous_effective")

    def test_success_only_and_receiver_or_key_mismatch(self) -> None:
        success_only = evaluate_synchronous_release(self.entry, self.growth, self.flow, (self._candidate(exceptional_path=False),))
        mismatch = evaluate_synchronous_release(self.entry, self.growth, self.flow, (self._candidate(receiver="other"),))
        self.assertEqual(success_only.classification, "insufficient_path_coverage")
        self.assertIn("RELEASE_INSUFFICIENT_PATH_COVERAGE", success_only.reason_codes)
        self.assertEqual(mismatch.classification, "receiver_or_key_mismatched")
        self.assertIn("RELEASE_RECEIVER_OR_KEY_MISMATCHED", mismatch.reason_codes)

    def test_release_requires_same_dimension_scope_and_known_sync_semantics(self) -> None:
        cases = (
            {"resource_dimension": "tasks"},
            {"scope": "global"},
            {"async_kind": "unknown"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                result = evaluate_synchronous_release(self.entry, self.growth, self.flow, (self._candidate(**changes),))
                self.assertNotEqual(result.status, "effective")

    def test_whole_resource_clear_does_not_require_a_key(self) -> None:
        result = evaluate_synchronous_release(
            self.entry, self.growth, self.flow,
            (self._candidate(kind="clear", key_identity="none"),),
        )
        self.assertEqual(result.classification, "synchronous_effective")

    def test_effective_candidate_wins_without_corrupting_classification(self) -> None:
        good = self._candidate()
        bad = self._candidate(site_start_line=33, receiver="other", evidence=("fact:bad",))
        result = evaluate_synchronous_release(self.entry, self.growth, self.flow, (good, bad))
        self.assertEqual(result.status, "effective")
        self.assertEqual(result.classification, "synchronous_effective")
        self.assertEqual(set(result.candidate_ids), {good.release_id, bad.release_id})

    def test_transfer_and_async_release_never_verify(self) -> None:
        transfer = evaluate_synchronous_release(self.entry, self.growth, self.flow, (self._candidate(transfer_only=True),))
        self.assertEqual(transfer.status, "unknown")
        for async_kind in ("worker", "timer", "callback", "consumer", "ack"):
            with self.subTest(async_kind=async_kind):
                result = evaluate_synchronous_release(self.entry, self.growth, self.flow, (self._candidate(synchronous=False, async_kind=async_kind),))
                self.assertEqual(result.classification, "potential_async")
                self.assertNotEqual(result.status, "effective")
                self.assertIn("RELEASE_POTENTIAL_ASYNC", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
