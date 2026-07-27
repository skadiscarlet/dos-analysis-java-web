from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from dosweb.artifacts.identifiers import file_sha256
from dosweb.codeql import DecodeSource, GROWTH_COLUMNS, decode_bqrs_json, run_query, validate_database
from dosweb.growth import normalize_growth_rows
from tests.test_codeql_entry_queries import _codeql_wrapper


_RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql")
_JAVAC = shutil.which("javac")


@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class CodeqlGrowthQueryTests(unittest.TestCase):
    def test_growth_queries_use_the_exact_shared_table_contract(self) -> None:
        root = Path(__file__).parents[1]
        query_root = root / "codeql" / "dosweb" / "Growth"
        query_names = (
            "InputMaterialization.ql",
            "DirectAllocation.ql",
            "ContainerGrowth.ql",
            "AsyncWorkGrowth.ql",
        )
        self.assertEqual(len(GROWTH_COLUMNS), 13)
        for query_name in query_names:
            with self.subTest(query=query_name):
                source = (query_root / query_name).read_text(encoding="utf-8")
                self.assertIn("@kind table", source)
                self.assertIn("import java", source)
                for column in GROWTH_COLUMNS:
                    self.assertIn(f'"{column}"', source)
                for forbidden in ("static_vulnerable", "bounded_under_modeled_assumptions", "lifecycle_result"):
                    self.assertNotIn(forbidden, source)

    def test_g1_through_g4_against_temporary_databases(self) -> None:
        root = Path(__file__).parents[1]
        cases = (
            ("spring", "InputMaterialization.ql", "input_materialization", "bytes", "value"),
            ("spring", "DirectAllocation.ql", "direct_allocation", "bytes", "size"),
            ("servlet", "ContainerGrowth.ql", "container_growth", "entries", "key"),
            ("netty", "AsyncWorkGrowth.ql", "async_work_growth", "tasks", "submission_count"),
            ("mqtt", "InputMaterialization.ql", "input_materialization", "bytes", "value"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            codeql_binary = _codeql_wrapper(temporary)
            databases: dict[str, object] = {}
            for fixture, query_name, kind, dimension, role in cases:
                with self.subTest(fixture=fixture, kind=kind):
                    source_root = root / "tests" / "fixtures" / fixture / "src" / "main" / "java"
                    database = databases.get(fixture)
                    if database is None:
                        database_path = temporary / f"{fixture}-database"
                        classes = temporary / f"{fixture}-classes"
                        classes.mkdir()
                        java_file = next(source_root.rglob("*.java"))
                        completed = subprocess.run(
                            [
                                _CODEQL, "database", "create", str(database_path), "--language=java",
                                f"--source-root={source_root}",
                                f"--command={_JAVAC} -d {classes} {java_file.relative_to(source_root)}",
                                "--overwrite",
                            ],
                            check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        )
                        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                        database = validate_database(database_path)
                        databases[fixture] = database
                    query = root / "codeql" / "dosweb" / "Growth" / query_name
                    output = temporary / f"{fixture}-{query.stem}-results"
                    try:
                        result = run_query(query, database, output, codeql_binary=str(codeql_binary))
                        decoded_path = result.decoded_path
                        query_sha256 = result.query_sha256
                    except Exception as exc:
                        if not (
                            getattr(exc, "code", None) == "CODEQL_QUERY_FAILED"
                            and getattr(exc, "details", {}).get("diagnostic")
                            == "database changed during query execution"
                        ):
                            raise
                        bqrs_path = temporary / f"{fixture}-{query.stem}.bqrs"
                        decoded_path = temporary / f"{fixture}-{query.stem}.json"
                        completed = subprocess.run(
                            [str(codeql_binary), "query", "run", str(query), "--database", str(database.path), "--output", str(bqrs_path)],
                            check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        )
                        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                        completed = subprocess.run(
                            [str(codeql_binary), "bqrs", "decode", str(bqrs_path), "--format=json", "--output", str(decoded_path)],
                            check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        )
                        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                        query_sha256 = file_sha256(query)
                    payload = json.loads(decoded_path.read_text(encoding="utf-8"))
                    decoded_columns = tuple(
                        column["name"] if isinstance(column, dict) else column
                        for column in payload["#select"]["columns"]
                    )
                    self.assertEqual(decoded_columns, GROWTH_COLUMNS)
                    rows = decode_bqrs_json("growth", payload, DecodeSource(database.source_root, query_sha256))
                    candidates = normalize_growth_rows(rows)
                    matching = [item for item in candidates if item["kind"] == kind]
                    self.assertTrue(matching, candidates)
                    self.assertTrue(any(item["resource_point"]["dimension"] == dimension for item in matching))
                    self.assertTrue(any(any(demand["role"] == role for demand in item["demand_inputs"]) for item in matching))
                    if kind == "input_materialization" and fixture == "spring":
                        self.assertFalse(
                            any("SpringLookalike" in item["resource_point"]["receiver"] for item in matching)
                        )
                    if kind == "direct_allocation":
                        self.assertTrue(any(item["operation"] == "array_creation" for item in matching), matching)
                    if kind == "container_growth":
                        self.assertFalse(any("requestLocal" in item["resource_point"]["receiver"] for item in matching))
                        self.assertTrue(
                            any(
                                item["escape_scope"] == "global"
                                and any(demand["role"] == "value" for demand in item["demand_inputs"])
                                for item in matching
                            ),
                            matching,
                        )
                    if kind == "async_work_growth":
                        self.assertTrue(any(row["coverage_status"] == "partial" for row in rows), rows)


if __name__ == "__main__":
    unittest.main()
