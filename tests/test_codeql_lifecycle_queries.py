from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from dosweb.artifacts.identifiers import file_sha256
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database
from dosweb.codeql.decoder import BOUND_COLUMNS, FLOW_COLUMNS, GUARD_COLUMNS, RELEASE_COLUMNS
from tests.test_codeql_entry_queries import _codeql_wrapper

_ROOT = Path(__file__).resolve().parents[1]
_RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql")
_JAVAC = shutil.which("javac")


class CodeqlLifecycleQueryContractTests(unittest.TestCase):
    def test_queries_use_exact_candidate_only_contracts(self) -> None:
        queries = (
            ("codeql/dosweb/Flows/EntryToGrowth.ql", FLOW_COLUMNS),
            ("codeql/dosweb/Lifecycle/GuardCandidates.ql", GUARD_COLUMNS),
            ("codeql/dosweb/Lifecycle/BoundCandidates.ql", BOUND_COLUMNS),
            ("codeql/dosweb/Lifecycle/SynchronousReleaseCandidates.ql", RELEASE_COLUMNS),
        )
        forbidden = ("static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown", "assertion", "verdict", "lifecycle_result")
        for relative, columns in queries:
            with self.subTest(query=relative):
                content = (_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("@kind table", content)
                self.assertIn("import java", content)
                positions = [content.index(f"as {column}") for column in columns]
                self.assertEqual(positions, sorted(positions))
                for term in forbidden:
                    self.assertNotIn(term, content.lower())


@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class CodeqlLifecycleFixtureTests(unittest.TestCase):
    def _database(self, source_root: Path, temporary: Path, name: str):
        database_path = temporary / f"{name}-database"
        classes = temporary / f"{name}-classes"
        classes.mkdir()
        java_file = next(source_root.rglob("*.java"))
        completed = subprocess.run(
            [
                _CODEQL, "database", "create", str(database_path), "--language=java",
                f"--source-root={source_root}",
                f"--command={_JAVAC} -d {classes} {java_file.relative_to(source_root)}",
                "--overwrite",
            ], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
        return validate_database(database_path)

    def _rows(self, query_name: str, database, temporary: Path) -> list[dict[str, object]]:
        query = _ROOT / "codeql" / "dosweb" / query_name
        try:
            result = run_query(query, database, temporary / query_name.replace("/", "-"), codeql_binary=str(_codeql_wrapper(temporary)))
            decoded_path, query_sha256 = result.decoded_path, result.query_sha256
        except Exception as exc:
            if not (getattr(exc, "code", None) == "CODEQL_QUERY_FAILED" and getattr(exc, "details", {}).get("diagnostic") == "database changed during query execution"):
                raise
            bqrs = temporary / f"{query.stem}.bqrs"
            decoded_path = temporary / f"{query.stem}.json"
            completed = subprocess.run([str(_codeql_wrapper(temporary)), "query", "run", str(query), "--database", str(database.path), "--output", str(bqrs)], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            completed = subprocess.run([str(_codeql_wrapper(temporary)), "bqrs", "decode", str(bqrs), "--format=json", "--output", str(decoded_path)], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            query_sha256 = file_sha256(query)
        payload = json.loads(decoded_path.read_text(encoding="utf-8"))
        return decode_bqrs_json(
            {"EntryToGrowth": "flow", "GuardCandidates": "guard", "BoundCandidates": "bound", "SynchronousReleaseCandidates": "release"}[query.stem],
            payload,
            DecodeSource(database.source_root, query_sha256),
        )

    def test_fixture_semantics(self) -> None:
        cases = {
            "spring": {"flow": True, "guard": True, "bound": False, "release": False},
            "servlet": {"flow": True, "guard": True, "bound": False, "release": True},
            "netty": {"flow": True, "guard": False, "bound": True, "release": True},
            "mqtt": {"flow": True, "guard": True, "bound": False, "release": False},
        }
        query_names = {
            "flow": "Flows/EntryToGrowth.ql",
            "guard": "Lifecycle/GuardCandidates.ql",
            "bound": "Lifecycle/BoundCandidates.ql",
            "release": "Lifecycle/SynchronousReleaseCandidates.ql",
        }
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            wrapper = _codeql_wrapper(temporary)
            self.assertTrue(wrapper.exists())
            for fixture, expectations in cases.items():
                source_root = _ROOT / "tests" / "fixtures" / fixture / "src" / "main" / "java"
                database = self._database(source_root, temporary, fixture)
                for family, query_name in query_names.items():
                    with self.subTest(fixture=fixture, query=family):
                        rows = self._rows(query_name, database, temporary)
                        if expectations[family]:
                            self.assertTrue(rows, f"expected {family} candidates for {fixture}")
                        for row in rows:
                            self.assertIn("coverage_status", row)
                            self.assertNotIn("verdict", row)
                            self.assertNotIn("assertion", row)


if __name__ == "__main__":
    unittest.main()
