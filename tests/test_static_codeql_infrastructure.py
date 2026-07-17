#!/usr/bin/env python3
"""Regression tests for static CodeQL and batch aggregation infrastructure."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "scripts" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = load_script("build_top50_codeql_dbs", "build_top50_codeql_dbs.py")
AGGREGATE = load_script("aggregate_java_web_dos_batch", "aggregate_java_web_dos_batch.py")


class BuildInfrastructureTests(unittest.TestCase):
    def test_manifest_rejects_duplicate_slug_with_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.md"
            manifest.write_text(
                "| # | Repository |\n"
                "|---:|---|\n"
                "| 1 | `owner/repo` |\n"
                "| 2 | `owner/repo` |\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"manifest\.md:4.*duplicate.*owner/repo"):
                BUILD.load_slugs(manifest)

    def test_markdown_manifest_ignores_prose_and_loads_repository_table(self) -> None:
        manifest = REPO_ROOT / "frameworks" / "2026-07-04-github-java-web-app-top50.md"

        slugs = BUILD.load_slugs(manifest)

        self.assertEqual(50, len(slugs))
        self.assertEqual("apolloconfig/apollo", slugs[0])
        self.assertEqual("MarkerHub/vueblog", slugs[-1])

    def test_manifest_rejects_invalid_repository_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.txt"
            manifest.write_text("not-a-repository\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"manifest\.txt:1.*owner/repository"):
                BUILD.load_slugs(manifest)

    def test_override_fragments_reject_duplicate_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            override = Path(tmp) / "overrides.json"
            override.write_text("{}", encoding="utf-8")
            fragment_dir = Path(tmp) / "overrides.d"
            fragment_dir.mkdir()
            for filename in ("one.json", "two.json"):
                (fragment_dir / filename).write_text(
                    json.dumps({"slug": "owner/repo", "command": "mvn compile"}), encoding="utf-8"
                )

            with self.assertRaisesRegex(ValueError, r"duplicate override.*owner/repo.*one\.json.*two\.json"):
                BUILD.load_overrides(override)

    def test_dry_run_writes_no_result_or_database_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.md"
            manifest.write_text("| # | Repository |\n|---:|---|\n| 1 | `owner/repo` |\n", encoding="utf-8")
            source_root = root / "sources"
            (source_root / "owner__repo").mkdir(parents=True)
            (source_root / "owner__repo" / "pom.xml").write_text("<project/>", encoding="utf-8")
            result_root = root / "results"
            db_root = root / "databases"

            exit_code = BUILD.main(
                [
                    "--manifest", str(manifest),
                    "--source-root", str(source_root),
                    "--db-root", str(db_root),
                    "--result-root", str(result_root),
                    "--dry-run",
                ]
            )

            self.assertEqual(0, exit_code)
            self.assertFalse(result_root.exists())
            self.assertFalse(db_root.exists())

    def test_database_structure_and_coverage_status_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_dir = Path(tmp) / "db"
            self.assertEqual(
                {"database_structure": "missing", "coverage_status": "not_available"},
                BUILD.codeql_database_status(db_dir),
            )
            db_dir.mkdir()
            (db_dir / "codeql-database.yml").write_text("", encoding="utf-8")
            (db_dir / "db-java").mkdir()
            (db_dir / "db-java" / "default").mkdir()
            self.assertEqual("valid", BUILD.codeql_database_status(db_dir)["database_structure"])
            self.assertEqual("unverified", BUILD.codeql_database_status(db_dir)["coverage_status"])


class AggregationTests(unittest.TestCase):
    def write_static_target(self, batch_root: Path, verdict: str) -> None:
        target_dir = batch_root / "target-a"
        target_dir.mkdir()
        (batch_root / "manifest.normalized.jsonl").write_text(
            json.dumps(
                {
                    "slug": "owner/repo",
                    "target": "Target A",
                    "repo_path": "/example/repo",
                    "hunter_output_dir": str(target_dir),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (target_dir / "target_profile.json").write_text("{}\n", encoding="utf-8")
        for name in ("sinks.jsonl", "sources.jsonl", "flows.jsonl", "rejected.jsonl", "subagent_reviews.jsonl"):
            (target_dir / name).write_text("", encoding="utf-8")
        (target_dir / "findings.jsonl").write_text(
            json.dumps({"finding_id": "F-1", "verdict": verdict}) + "\n", encoding="utf-8"
        )
        (target_dir / "summary.md").write_text("summary\n", encoding="utf-8")
        (target_dir / "gaps.md").write_text("gaps\n", encoding="utf-8")

    def test_aggregate_accepts_static_verdicts_without_dynamic_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = Path(tmp)
            self.write_static_target(batch_root, "static_vulnerable")

            AGGREGATE.aggregate(batch_root)

            self.assertTrue((batch_root / "aggregate_findings.jsonl").exists())
            self.assertFalse((batch_root / "dynamic_validation_queue.jsonl").exists())
            inventory = json.loads((batch_root / "aggregate_inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(1, inventory["totals"]["verdict:static_vulnerable"])

    def test_aggregate_rejects_non_static_verdict_at_source_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = Path(tmp)
            self.write_static_target(batch_root, "likely")

            with self.assertRaisesRegex(ValueError, r"target-a/findings\.jsonl:1.*likely"):
                AGGREGATE.aggregate(batch_root)


if __name__ == "__main__":
    unittest.main()
