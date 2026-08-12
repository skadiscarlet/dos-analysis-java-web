import unittest

from dosweb.benchmark.evaluator import evaluate_matches


class BenchmarkEvaluatorTests(unittest.TestCase):
    def test_only_recall_metrics_are_emitted_with_eligibility(self):
        result = evaluate_matches(
            [
                {"status": "hit", "repository": "a/a"},
                {"status": "matched_static_unknown", "repository": "b/b"},
                {"status": "no_candidate", "repository": "c/c"},
                {"status": "target_not_run", "repository": "d/d"},
                {"status": "artifact_missing", "repository": "e/e"},
            ]
        )
        self.assertEqual(
            set(result["metrics"]),
            {"positive_recall", "global_recall", "matched_any_rate"},
        )
        self.assertEqual(result["eligible"], 3)
        self.assertEqual(result["hits"], 1)
        self.assertEqual(result["targets_completed"], 3)
        self.assertEqual(result["metrics"]["positive_recall"], 1 / 3)
        self.assertEqual(result["metrics"]["global_recall"], 1 / 29)
        self.assertEqual(result["metrics"]["matched_any_rate"], 2 / 3)

    def test_empty_is_safe(self):
        result = evaluate_matches([])
        self.assertEqual(result["metrics"]["global_recall"], 0.0)
        self.assertEqual(result["eligible"], 0)
