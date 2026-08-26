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
    def test_http_session_attribute_write_is_partial_session_growth(self) -> None:
        root = Path(__file__).parents[1]
        source_root = root / "tests" / "fixtures" / "spring" / "src" / "main" / "java"
        fixture = source_root / "fixture" / "spring" / "CitrusFixture.java"
        sink_line = next(
            number
            for number, line in enumerate(fixture.read_text(encoding="utf-8").splitlines(), 1)
            if 'session.setAttribute("SESSION_VERIFY_ID", verification)' in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database_path = temporary / "session-growth-database"
            classes = temporary / "session-growth-classes"
            classes.mkdir()
            java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
            completed = subprocess.run(
                [
                    _CODEQL,
                    "database",
                    "create",
                    str(database_path),
                    "--language=java",
                    f"--source-root={source_root}",
                    f"--command={_JAVAC} -d {classes} "
                    + " ".join(str(path) for path in java_files),
                    "--overwrite",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            database = validate_database(database_path)
            query = root / "codeql" / "dosweb" / "Growth" / "ContainerGrowth.ql"
            result = run_query(
                query,
                database,
                temporary / "session-growth-results",
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
            rows = decode_bqrs_json(
                "growth",
                payload,
                DecodeSource(database.source_root, result.query_sha256),
            )

        matching = [
            row
            for row in rows
            if row["site_file"].endswith("CitrusFixture.java")
            and row["site_start_line"] == sink_line
        ]
        self.assertEqual(len(matching), 1, matching)
        self.assertEqual(matching[0]["growth_kind"], "container_growth")
        self.assertEqual(matching[0]["operation"], "javax.servlet.http.HttpSession.setAttribute")
        self.assertEqual(matching[0]["resource_dimension"], "objects")
        self.assertEqual(matching[0]["demand_input_name"], "verification")
        self.assertEqual(matching[0]["demand_input_role"], "value")
        self.assertEqual(matching[0]["escape_scope"], "session")
        self.assertEqual(matching[0]["coverage_status"], "partial")
        self.assertEqual(
            matching[0]["coverage_note"],
            "http_session_attribute_write:fresh_session_cardinality_requires_entry_path",
        )

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
            ("spring", "InputMaterialization.ql", "input_materialization", "bytes", "size"),
            ("spring", "DirectAllocation.ql", "direct_allocation", "bytes", "size"),
            ("spring", "ContainerGrowth.ql", "container_growth", "entries", "key"),
            ("servlet", "ContainerGrowth.ql", "container_growth", "entries", "key"),
            ("servlet", "InputMaterialization.ql", "input_materialization", "bytes", "size"),
            ("netty", "AsyncWorkGrowth.ql", "async_work_growth", "tasks", "value"),
            ("netty", "InputMaterialization.ql", "input_materialization", "bytes", "size"),
            ("mqtt", "InputMaterialization.ql", "input_materialization", "bytes", "size"),
            ("armeria", "InputMaterialization.ql", "input_materialization", "bytes", "size"),
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
                        java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
                        completed = subprocess.run(
                            [
                                _CODEQL, "database", "create", str(database_path), "--language=java",
                                f"--source-root={source_root}",
                                f"--command={_JAVAC} -d {classes} " + " ".join(str(path) for path in java_files),
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
                        string_fixture = source_root / "fixture" / "spring" / "RequestBodyStringController.java"
                        string_lines = string_fixture.read_text(encoding="utf-8").splitlines()
                        string_body_line = next(
                            number for number, line in enumerate(string_lines, 1)
                            if "void stringBody(" in line
                        )
                        unannotated_line = next(
                            number for number, line in enumerate(string_lines, 1)
                            if "void unannotatedString(" in line
                        )
                        lookalike_line = next(
                            number for number, line in enumerate(string_lines, 1)
                            if "void stringLookalike(" in line
                        )
                        string_rows = [
                            row for row in rows
                            if row["site_file"].endswith("RequestBodyStringController.java")
                        ]
                        self.assertEqual(
                            [row["site_start_line"] for row in string_rows],
                            [string_body_line],
                            string_rows,
                        )
                        self.assertEqual(
                            string_rows[0]["operation"],
                            "spring_request_body_string_materialization",
                        )
                        self.assertEqual(string_rows[0]["resource_dimension"], "bytes")
                        self.assertEqual(string_rows[0]["demand_input_role"], "size")
                        self.assertEqual(string_rows[0]["escape_scope"], "request")
                        self.assertEqual(string_rows[0]["coverage_status"], "complete")
                        self.assertNotIn(unannotated_line, {row["site_start_line"] for row in string_rows})
                        self.assertNotIn(lookalike_line, {row["site_start_line"] for row in string_rows})
                        self.assertFalse(
                            any("SpringLookalike" in item["resource_point"]["receiver"] for item in matching)
                        )
                        self.assertTrue(
                            {
                                "cn.devezhao.commons.web.ServletUtils.getRequestString",
                                "cn.hutool.core.io.IoUtil.readBytes",
                                "org.apache.commons.io.IOUtils.toByteArray",
                                "org.springframework.util.StreamUtils.copyToByteArray",
                                "org.springframework.util.StreamUtils.copyToString",
                                "java.io.InputStream.readAllBytes",
                                "java.io.ByteArrayOutputStream.toByteArray",
                            }.issubset({item["operation"] for item in matching}),
                            matching,
                        )
                    if kind == "input_materialization" and fixture == "servlet":
                        self.assertTrue(
                            any(item["operation"] == "servlet_request_string_builder_materialization" for item in matching),
                            matching,
                        )
                    if kind == "input_materialization" and fixture == "netty":
                        netty_fixture = source_root / "fixture" / "netty" / "NettyFixture.java"
                        netty_lines = netty_fixture.read_text(encoding="utf-8").splitlines()
                        materialization_lines = [
                            number for number, line in enumerate(netty_lines, 1)
                            if "request.content().toString(CharsetUtil.UTF_8)" in line
                        ]
                        self.assertEqual(len(materialization_lines), 2)
                        positive_line, lookalike_line = materialization_lines
                        fixture_rows = [
                            row for row in rows
                            if row["site_file"].endswith("NettyFixture.java")
                            and row["operation"] == "netty_full_http_request_string_materialization"
                        ]
                        self.assertEqual(
                            [row["site_start_line"] for row in fixture_rows],
                            [positive_line],
                            fixture_rows,
                        )
                        self.assertEqual(fixture_rows[0]["resource_dimension"], "bytes")
                        self.assertEqual(fixture_rows[0]["demand_input_role"], "size")
                        self.assertEqual(fixture_rows[0]["escape_scope"], "request")
                        self.assertEqual(fixture_rows[0]["coverage_status"], "complete")
                        self.assertNotIn(
                            lookalike_line,
                            {row["site_start_line"] for row in fixture_rows},
                        )
                    if kind == "direct_allocation":
                        self.assertTrue(any(item["operation"] == "array_creation" for item in matching), matching)
                    if kind == "container_growth":
                        self.assertFalse(any("requestLocal" in item["resource_point"]["receiver"] for item in matching))
                        if fixture == "spring":
                            notes = {note for item in matching for note in item["coverage_notes"]}
                            self.assertIn("persistent_field_container_write:attacker_controlled_loop_multiplicity_proven", notes)
                            self.assertIn("persistent_field_container_write:loop_bound_not_attacker_proven", notes)
                        if fixture == "servlet":
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
