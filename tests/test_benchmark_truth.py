import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
import importlib.util

from dosweb.batch.plan import build_batch_plan
from dosweb.benchmark.truth import (
    corpus_from_manifest,
    load_database_overrides,
    load_source_overrides,
    normalize_repo,
    normalize_truth,
)


ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("evaluate_poc29", ROOT / "scripts/evaluate_java_web_dos_benchmark.py")
assert _SPEC and _SPEC.loader
_EVALUATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_EVALUATOR)


class BenchmarkTruthTests(unittest.TestCase):
    def test_explicit_repository_normalization(self):
        self.assertEqual(
            normalize_repo("DependencyTrack/dependency-track"),
            "dependencytrack/dependency-track",
        )
        self.assertEqual(
            normalize_repo("dependencytrack__dependency-track"),
            "dependencytrack/dependency-track",
        )

    def test_real_truth_is_29_cases_and_18_repositories_with_assets(self):
        root = Path(__file__).parents[1]
        rows, validation, manifest = normalize_truth(
            root / "results/applications_dynamic_validation/binary_truth_collection.json",
            repo_root=root,
        )
        self.assertEqual(len(rows), 29)
        self.assertEqual(validation["repository_count"], 18)
        self.assertEqual(validation["asset_count"], 18)
        self.assertEqual(validation["source_asset_count"], 18)
        self.assertEqual(validation["database_ready_count"], 18)
        self.assertEqual(len(validation["database_incomplete"]), 0)
        self.assertTrue(validation["batch_ready"])
        self.assertTrue(validation["valid"])
        self.assertTrue(all(row["source_digest"] for row in rows))
        self.assertTrue(all(row["dynamic_status"] for row in rows))
        self.assertEqual(len(manifest["projects"]), 18)
        self.assertTrue(all(project["database_marker"]["sha256"] for project in manifest["projects"]))

    def test_complete_database_manifest_builds_batch_corpus(self):
        root = Path(__file__).parents[1]
        _, validation, manifest = normalize_truth(
            root / "results/applications_dynamic_validation/binary_truth_collection.json",
            repo_root=root,
        )
        self.assertTrue(validation["batch_ready"])
        corpus = corpus_from_manifest(manifest, root)
        self.assertEqual(18, len(corpus.targets))
        self.assertTrue(all(target.database_fingerprint for target in corpus.targets))

    def test_generated_inventory_builds_runnable_18_target_plan(self):
        root = Path(__file__).parents[1]
        _, validation, manifest = normalize_truth(
            root / "results/applications_dynamic_validation/binary_truth_collection.json",
            repo_root=root,
        )
        self.assertTrue(validation["valid"])
        corpus = corpus_from_manifest(manifest, root)
        plan = build_batch_plan(corpus, run_id="poc29-test", mode="entries")
        self.assertEqual(len(plan.targets), 18)
        self.assertTrue(plan.verify_digest())
        self.assertTrue(all(target.initial_state == "queued" for target in plan.targets))

    def test_database_override_requires_safe_relative_path_and_is_recorded(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.json"
            path.write_text(json.dumps({"cicizz/jmqtt": "databases/applications/cicizz__jmqtt-db"}), encoding="utf-8")
            overrides = load_database_overrides(path, root)
            _, validation, manifest = normalize_truth(
                root / "results/applications_dynamic_validation/binary_truth_collection.json",
                repo_root=root,
                database_overrides=overrides,
            )
            row = next(project for project in manifest["projects"] if project["name"] == "cicizz/jmqtt")
            self.assertEqual(row["database_origin"], "override")
            self.assertEqual(row["codeql_path"], overrides["cicizz/jmqtt"])
            self.assertTrue(validation["valid"])
            path.write_text(json.dumps({"cicizz/jmqtt": "../escape"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_database_overrides(path, root)

    def test_source_override_manifest_loads_strict_provider_bindings(self):
        overrides = load_source_overrides(ROOT / "config/poc29_full_source_overrides.json", ROOT)
        self.assertEqual(8, len(overrides))
        self.assertEqual(
            "bb16533009a597dbb41ab6f013ac300509abbb3e",
            overrides["apache/skywalking"]["commit"],
        )
        self.assertRegex(overrides["apache/skywalking"]["analysis_tree_sha256"], r"^[0-9a-f]{64}$")

    def test_corpus_revalidates_database_source_and_fingerprint(self):
        root = Path(__file__).parents[1]
        _, _, manifest = normalize_truth(
            root / "results/applications_dynamic_validation/binary_truth_collection.json",
            repo_root=root,
        )
        ready = dict(manifest)
        ready["projects"] = [row for row in manifest["projects"] if row["codeql_built"]]
        ready["total"] = ready["database_ready_count"] = len(ready["projects"])
        ready["batch_ready"] = True
        for index, row in enumerate(ready["projects"], 1):
            row["index"] = index
        with mock.patch("dosweb.benchmark.truth.validate_database", side_effect=ValueError("incomplete")):
            with self.assertRaisesRegex(ValueError, "database validation failed"):
                corpus_from_manifest(ready, root)

    def test_entries_plan_uses_all_ready_targets_and_ready_only_is_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "entries"
            self.assertEqual(0, _EVALUATOR.main(["--output-dir", str(output), "--plan-run-id", "entries-plan"]))
            plan = json.loads((output / "batch_plan.json").read_text(encoding="utf-8"))
            self.assertEqual("entries", plan["mode"])
            self.assertEqual(18, len(plan["targets"]))
            ready = Path(tmp) / "ready"
            self.assertEqual(0, _EVALUATOR.main(["--output-dir", str(ready), "--plan-ready-only"]))
            ready_plan = json.loads((ready / "batch_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(18, len(ready_plan["targets"]))
            run_manifest = json.loads((ready / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(run_manifest["plan_ready_only"])
            self.assertFalse(run_manifest["plan_is_complete_recall_run"])

    def test_full_plan_fails_closed_until_all_sources_have_public_commit_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "full"
            self.assertEqual(
                2,
                _EVALUATOR.main([
                    "--output-dir", str(output),
                    "--plan-run-id", "poc29-full",
                    "--plan-mode", "full",
                    "--allow-remote-llm",
                ]),
            )
            self.assertFalse((output / "batch_plan.json").exists())

    def test_full_plan_succeeds_with_strict_source_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "full"
            overrides = ROOT / "config/poc29_full_source_overrides.json"
            self.assertEqual(
                0,
                _EVALUATOR.main([
                    "--output-dir", str(output),
                    "--plan-run-id", "poc29-full-plan-20260810",
                    "--plan-mode", "full",
                    "--allow-remote-llm",
                    "--source-overrides", str(overrides),
                ]),
            )
            plan = json.loads((output / "batch_plan.json").read_text(encoding="utf-8"))
            self.assertEqual("35fcae172671ea29b6ceacfeb0a99613ac2b3a3a08d7da3d1b5eaedf4c08d8a4", plan["plan_digest"])
            self.assertEqual(18, len(plan["targets"]))
            self.assertTrue(all(target["initial_state"] == "queued" for target in plan["targets"]))
            run_manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("full", run_manifest["plan_mode"])
            self.assertFalse(run_manifest["plan_ready_only"])
            self.assertTrue(run_manifest["plan_is_complete_recall_run"])

    def test_invalid_truth_is_reported_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truth.json"
            path.write_text(
                json.dumps(
                    {
                        "confirmed_true_positive": [
                            {"record_id": "x", "app": "nobody/nope"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rows, validation, _ = normalize_truth(
                path,
                repo_root=Path(__file__).parents[1],
            )
        self.assertEqual(len(rows), 1)
        self.assertFalse(validation["valid"])
        self.assertTrue(validation["errors"])
