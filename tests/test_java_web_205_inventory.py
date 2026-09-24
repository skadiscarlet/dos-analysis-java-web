from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from dosweb.batch.corpus import _fingerprint, load_canonical_corpus
from dosweb.errors import AnalyzerError


from tests.support.offline_assets import require_java_web_205_assets

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_java_web_205_inventory", ROOT / "scripts/generate_java_web_205_inventory.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load generate_java_web_205_inventory.py")
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class JavaWeb205InventoryTests(unittest.TestCase):
    def test_tree_fingerprint_ignores_only_analyzer_owned_static_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "Main.java").write_text("class Main {}\n", encoding="utf-8")
            baseline = _fingerprint(source)

            analyzer_output = source / "results/applications_static_analysis/run-1"
            analyzer_output.mkdir(parents=True)
            (analyzer_output / "report.md").write_text("generated\n", encoding="utf-8")
            self.assertEqual(baseline, _fingerprint(source))

            project_result = source / "results/domain-result.json"
            project_result.write_text("{}\n", encoding="utf-8")
            self.assertNotEqual(baseline, _fingerprint(source))

    def test_tracked_manifest_preserves_200_and_appends_exact_poc_union_delta(self) -> None:
        base = json.loads((ROOT / "intel/applications/java_web_200_targets.json").read_text(encoding="utf-8"))
        active = json.loads((ROOT / "intel/applications/java_web_205_targets.json").read_text(encoding="utf-8"))

        self.assertEqual("java-web-205", active["corpus"])
        self.assertEqual(205, active["total"])
        identity_fields = (
            "index", "name", "origin", "source_path", "codeql_path", "coverage",
        )
        self.assertEqual(
            [{key: row.get(key) for key in identity_fields} for row in base["projects"]],
            [{key: row.get(key) for key in identity_fields} for row in active["projects"][:200]],
        )
        shoppingcart = next(row for row in active["projects"] if row["name"] == "ikismail/shoppingcart")
        self.assertEqual("git-commit", shoppingcart["fingerprint_type"])
        self.assertEqual(
            "c992c54bde6af51f67d8cfec5cdba6cbcda19f6c",
            shoppingcart["checkout_fingerprint"],
        )
        self.assertEqual(
            [
                (201, "apache/druid"),
                (202, "apache/skywalking"),
                (203, "apache/solr"),
                (204, "prestodb/presto"),
                (205, "dromara/datacompare"),
            ],
            [(row["index"], row["name"]) for row in active["projects"][200:]],
        )
        self.assertEqual(205, len({row["name"].lower() for row in active["projects"]}))
        poc = json.loads((ROOT / "poc/manifest.json").read_text(encoding="utf-8"))
        base_names = {GENERATOR.normalize_repository(row["name"]) for row in base["projects"]}
        poc_names = {GENERATOR.normalize_repository(row["app"]) for row in poc}
        self.assertEqual(len(base_names & poc_names), active["construction"]["overlap_count"])
        self.assertEqual(5, active["construction"]["added_count"])

    def test_compose_repository_names_normalizes_and_deduplicates_case_insensitively(self) -> None:
        base = [{"index": index, "name": f"owner/repo-{index}"} for index in range(1, 201)]
        cases = [
            {"app": "OWNER__REPO-1"},
            {"app": "new/a"},
            {"app": "New/A"},
            {"app": "new__b"},
            {"app": "new/c"},
            {"app": "new/d"},
            {"app": "new/e"},
        ]

        names = GENERATOR.compose_repository_names(base, cases)

        self.assertEqual(["new/a", "new/b", "new/c", "new/d", "new/e"], names[200:])
        self.assertEqual(205, len(names))

    def test_additions_use_default_paths_and_report_real_readiness(self) -> None:
        active = json.loads((ROOT / "intel/applications/java_web_205_targets.json").read_text(encoding="utf-8"))
        additions = active["projects"][200:]
        for row in additions:
            slug = row["name"].replace("/", "__")
            self.assertEqual(f"frameworks/applications/{slug}", row["source_path"])
            self.assertEqual(f"databases/applications/{slug}-db", row["codeql_path"])
        ready = sum(row["codeql_built"] is True for row in active["projects"])
        incomplete = [row for row in active["projects"] if row["codeql_built"] is not True]
        self.assertEqual(205, ready)
        self.assertEqual(0, len(incomplete))
        self.assertEqual(ready, active["valid_codeql_databases"])
        self.assertEqual(len(incomplete), active["database_incomplete_count"])
        self.assertEqual(
            [row["name"] for row in incomplete], active["database_incomplete_repositories"]
        )
        self.assertTrue(active["batch_ready"])

    def test_default_loader_accepts_tracked_ready_manifest(self) -> None:
        require_java_web_205_assets(ROOT)
        corpus = load_canonical_corpus(repo_root=ROOT)
        self.assertEqual(205, corpus.total)
        self.assertEqual(205, len(corpus.targets))

    def test_loader_accepts_ready_java_web_205_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "intel/applications/java_web_205_targets.json"
            manifest.parent.mkdir(parents=True)
            payload = {
                "schema_version": 1,
                "status": "canonical",
                "corpus": "java-web-205",
                "total": 205,
                "valid_codeql_databases": 205,
                "batch_ready": True,
                "projects": [{}] * 205,
            }
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                load_canonical_corpus(manifest, repo_root=root)
            self.assertEqual("PROJECT_IDENTITY_INVALID", raised.exception.details["reason"])


if __name__ == "__main__":
    unittest.main()
