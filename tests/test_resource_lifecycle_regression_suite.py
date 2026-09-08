from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from dosweb.cli import main
from dosweb.artifacts.identifiers import file_sha256
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.evaluation import EVALUATION_MODES, evaluate_suite, load_suite


SUITE = Path("tests/fixtures/resource_lifecycle/regression-suite.json")
HISTORICAL = Path("evaluation/historical_manifest.json")


class ResourceLifecycleRegressionSuiteTests(unittest.TestCase):
    def test_suite_has_twelve_independent_pairs_and_property_first_expectations(self) -> None:
        suite = load_suite(SUITE)

        groups: dict[int, list[str]] = {}
        for case in suite.cases:
            groups.setdefault(case.group, []).append(case.case_id)
            self.assertTrue(case.transitions)
            self.assertTrue(case.expected.dimension)
            self.assertTrue(case.expected.lifecycle_status)

        self.assertEqual(set(range(1, 13)), set(groups))
        self.assertTrue(all(len(case_ids) >= 2 for case_ids in groups.values()))
        self.assertGreaterEqual(len(suite.cases), 24)

    def test_full_mode_matches_all_prior_expectations_and_ablations_only_lose_precision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evaluation = evaluate_suite(SUITE, Path(tmp))

        self.assertEqual(24, evaluation["metrics"]["full"]["expected_matches"])
        self.assertEqual(24, evaluation["metrics"]["full"]["analyzed"])
        self.assertEqual(set(EVALUATION_MODES), set(evaluation["metrics"]))
        by_case: dict[str, dict[str, str]] = {}
        for result in evaluation["cases"]:
            by_case.setdefault(result["case_id"], {})[result["mode"]] = result["lifecycle_status"]
        for modes in by_case.values():
            for mode in EVALUATION_MODES:
                if mode != "full":
                    self.assertIn(modes[mode], {modes["full"], "unknown"})
        self.assertTrue(
            all(evaluation["metrics"][mode]["unknown"] >= evaluation["metrics"]["full"]["unknown"] for mode in EVALUATION_MODES if mode != "full")
        )
        fixed_replacement = next(
            row
            for row in evaluation["cases"]
            if row["case_id"] == "g09-fixed-replacement" and row["mode"] == "without_scope"
        )
        self.assertEqual("unknown", fixed_replacement["lifecycle_status"])
        self.assertIn("holder_scope_identity_unknown:holder:field", fixed_replacement["reason_codes"])
        self.assertNotIn("coverage_incomplete", fixed_replacement["reason_codes"])

    def test_evaluation_writes_consistent_json_csv_markdown_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            evaluation = evaluate_suite(SUITE, output)
            metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
            manifest = json.loads((output / "run-manifest.json").read_text(encoding="utf-8"))
            with (output / "cases.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            summary = (output / "summary.md").read_text(encoding="utf-8")

        self.assertEqual(evaluation["metrics"], metrics["modes"])
        self.assertEqual(evaluation["suite_sha256"], manifest["suite_sha256"])
        self.assertEqual(len(evaluation["cases"]), len(rows))
        self.assertEqual(24 * len(EVALUATION_MODES), len(rows))
        self.assertEqual("off", manifest["llm"]["mode"])
        self.assertEqual("N/A", manifest["legacy_baseline"]["status"])
        self.assertIn("人工 IR 回归", summary)
        self.assertIn("不能证明服务可用性", summary)

    def test_resource_evaluate_cli_runs_without_database_or_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = main(["resource-evaluate", "--suite", str(SUITE), "--out", tmp])

            self.assertEqual(0, status)
            self.assertTrue((Path(tmp) / "run-manifest.json").is_file())

    def test_invalid_suite_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            value = json.loads(SUITE.read_text(encoding="utf-8"))
            value["schema_version"] = "999"
            path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaises(AnalyzerError) as raised:
                load_suite(path)

        self.assertEqual("ARTIFACT_INPUT_INVALID", raised.exception.code)

    def test_historical_manifest_is_metadata_only_and_not_synthetic_ground_truth(self) -> None:
        value = json.loads(HISTORICAL.read_text(encoding="utf-8"))

        self.assertEqual("1.0", value["schema_version"])
        self.assertEqual(29, len(value["cases"]))
        self.assertTrue(all(case["label_source"] == "archived_source_record" for case in value["cases"]))
        self.assertTrue(all(case["usable_for_offline_evaluation"] is False for case in value["cases"]))
        self.assertTrue(all(file_sha256(Path(case["material_path"])) == case["material_sha256"] for case in value["cases"]))
        self.assertEqual(29, value["summary"]["pending_independent_lifecycle_labels"])


if __name__ == "__main__":
    unittest.main()
