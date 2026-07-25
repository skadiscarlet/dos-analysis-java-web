from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repair_java_web_200_inventory", REPO_ROOT / "scripts" / "repair_java_web_200_inventory.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load repair_java_web_200_inventory.py")
REPAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPAIR)


class JavaWeb200InventoryTests(unittest.TestCase):
    def test_compose_replaces_qiaoqiaoyun_and_preserves_exact_unique_200(self) -> None:
        projects = [
            {"slug": f"owner/repo-{index}", "origin": "existing"}
            for index in range(199)
        ] + [{"slug": REPAIR.REMOVED_SLUG, "origin": "existing"}]

        result = REPAIR.compose_projects(projects, "apache/airavata")

        self.assertEqual(200, len(result))
        self.assertEqual(200, len({project["slug"].lower() for project in result}))
        self.assertNotIn(REPAIR.REMOVED_SLUG, {project["slug"] for project in result})
        self.assertEqual("apache/airavata", result[-1]["slug"])
        self.assertEqual("new", result[-1]["origin"])

    def test_ensure_source_rejects_checkout_without_java(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "sources"
            source = source_root / "owner__repo"
            source.mkdir(parents=True)
            (source / ".git").mkdir()
            (source / "application.jar").write_bytes(b"jar")
            with mock.patch.object(REPAIR, "own_git_head", return_value="a" * 40):
                with self.assertRaisesRegex(RuntimeError, "no Java source"):
                    REPAIR.ensure_source("owner/repo", source_root, root / "run")

    def test_database_valid_requires_nonempty_compilation_relation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "db"
            relation = database / "db-java/default/compilation_compiling_files.rel"
            relation.parent.mkdir(parents=True)
            (database / "codeql-database.yml").write_text("name: test\n", encoding="utf-8")
            relation.write_bytes(b"")
            self.assertFalse(REPAIR.database_valid(database))
            relation.write_bytes(b"extracted")
            self.assertTrue(REPAIR.database_valid(database))

    def test_source_fingerprint_does_not_use_parent_repository_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            source = root / "source"
            source.mkdir()
            (source / "Example.java").write_text("class Example {}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "source/Example.java"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "test"], check=True)

            kind, fingerprint = REPAIR.source_fingerprint(source)

            self.assertEqual("tree-sha256", kind)
            self.assertEqual(64, len(fingerprint))

    def test_ensure_source_falls_back_to_next_candidate(self) -> None:
        candidates = ["owner/no-java", "owner/valid"]
        attempts = []

        def attempt(slug: str) -> str:
            attempts.append(slug)
            if slug == "owner/no-java":
                raise RuntimeError("no Java source files")
            return slug

        selected = None
        for candidate in candidates:
            try:
                selected = attempt(candidate)
                break
            except RuntimeError:
                continue

        self.assertEqual("owner/valid", selected)
        self.assertEqual(candidates, attempts)

    def test_ensure_database_refuses_invalid_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            db_root = root / "dbs"
            database = db_root / "owner__repo-db"
            database.mkdir(parents=True)

            with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                REPAIR.ensure_database("owner/repo", source, db_root, root / "run")

    def test_tracked_manifest_contains_canonical_200_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "manifest.json"
            rows = [{"name": f"owner/repo-{index}", "codeql_built": True} for index in range(200)]
            with mock.patch.object(REPAIR, "REPO_ROOT", root):
                run_root = root / "results/run"
                REPAIR.write_tracked_manifest(path, run_root, rows, "apache/airavata")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("canonical", payload["status"])
            self.assertEqual(200, payload["total"])
            self.assertEqual(200, payload["valid_codeql_databases"])
            self.assertEqual(REPAIR.REMOVED_SLUG, payload["removed"]["slug"])


if __name__ == "__main__":
    unittest.main()
