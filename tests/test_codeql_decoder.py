from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dosweb.codeql import (
    BOUND_COLUMNS,
    ENTRY_COLUMNS,
    FLOW_COLUMNS,
    GROWTH_COLUMNS,
    GUARD_COLUMNS,
    RELEASE_COLUMNS,
    DecodeSource,
    decode_bqrs_json,
    decode_rows,
)
from dosweb.errors import AnalyzerError


class CodeqlDecoderTests(unittest.TestCase):
    def _entry_row(self, handler_file: str = "src/Handler.java") -> tuple[object, ...]:
        return (
            "servlet",
            "http",
            "fixture.Handler.handle",
            handler_file,
            10,
            "annotation_mapping",
            "fixture.Handler.handle",
            "src/Handler.java",
            8,
            "/items",
            "unknown",
            "body",
            "byte[]",
            "request_body",
            "before_handler",
            "complete",
            "",
        )

    def _source(self, root: Path) -> DecodeSource:
        return DecodeSource(source_root=root.resolve(), query_sha256="a" * 64)

    def test_decoder_rejects_missing_extra_or_reordered_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            variants = (
                ENTRY_COLUMNS[:-1],
                ENTRY_COLUMNS + ("unexpected",),
                (ENTRY_COLUMNS[1], ENTRY_COLUMNS[0], *ENTRY_COLUMNS[2:]),
            )
            for columns in variants:
                with self.subTest(columns=columns):
                    with self.assertRaises(AnalyzerError) as raised:
                        decode_rows("entries", columns, [], source)
                    self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")
                    self.assertEqual(raised.exception.details["reason"], "COLUMN_MISMATCH")

    def test_decoder_rejects_invalid_enums_and_non_integer_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            invalid_framework = list(self._entry_row())
            invalid_framework[0] = "jax_rs"
            invalid_line = list(self._entry_row())
            invalid_line[4] = "10"
            boolean_line = list(self._entry_row())
            boolean_line[4] = True
            zero_line = list(self._entry_row())
            zero_line[4] = 0
            for row in (invalid_framework, invalid_line, boolean_line, zero_line):
                with self.subTest(row=row):
                    with self.assertRaises(AnalyzerError) as raised:
                        decode_rows("entries", ENTRY_COLUMNS, [row], source)
                    self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")

    def test_decoder_normalizes_paths_relative_to_database_source_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source_file = root / "src" / "Handler.java"
            source_file.parent.mkdir()
            source_file.write_text("class Handler {}", encoding="utf-8")
            decoded = decode_rows(
                "entries",
                ENTRY_COLUMNS,
                [self._entry_row(str(source_file))],
                self._source(root),
            )
            self.assertEqual(len(decoded), 1)
            fact = decoded[0]
            self.assertEqual(fact["handler_file"], "src/Handler.java")
            self.assertEqual(fact["registration_file"], "src/Handler.java")
            self.assertEqual(
                fact["handler_location"],
                {"file": "src/Handler.java", "start_line": 10},
            )
            self.assertEqual(fact["query_name"], "entries")
            self.assertEqual(fact["query_sha256"], "a" * 64)
            self.assertNotIn("entry_id", fact)
            self.assertFalse(any("verdict" in key for key in fact))

    def test_decoder_rejects_row_arity_null_and_source_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = self._source(root)
            null_row = list(self._entry_row())
            null_row[2] = None
            escape_row = list(self._entry_row())
            escape_row[3] = "../outside.java"
            for row in (self._entry_row()[:-1], null_row, escape_row):
                with self.subTest(row=row):
                    with self.assertRaises(AnalyzerError) as raised:
                        decode_rows("entries", ENTRY_COLUMNS, [row], source)
                    self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")

    def test_decoder_rejects_unknown_query_and_invalid_query_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaises(AnalyzerError) as raised:
                decode_rows("unknown", ENTRY_COLUMNS, [], self._source(root))
            self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")
            with self.assertRaises(AnalyzerError) as raised:
                decode_rows(
                    "entries",
                    ENTRY_COLUMNS,
                    [],
                    DecodeSource(source_root=root, query_sha256="not-a-hash"),
                )
            self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")

    def test_decode_bqrs_json_accepts_real_column_descriptors(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            payload = {
                "#select": {
                    "columns": [
                        {"name": name, "kind": "String"} for name in ENTRY_COLUMNS
                    ],
                    "tuples": [list(self._entry_row())],
                }
            }
            decoded = decode_bqrs_json("entries", payload, source)
            self.assertEqual(decoded[0]["handler_file"], "src/Handler.java")

    def test_decode_bqrs_json_requires_exact_result_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            with self.assertRaises(AnalyzerError) as raised:
                decode_bqrs_json(
                    "entries",
                    {"wrong": {"columns": list(ENTRY_COLUMNS), "tuples": []}},
                    source,
                )
            self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")
            decoded = decode_bqrs_json(
                "entries",
                {"#select": {"columns": list(ENTRY_COLUMNS), "tuples": []}},
                source,
            )
            self.assertEqual(decoded, [])

    def test_decoder_bounds_rows_strings_lines_and_malformed_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = self._source(root)
            huge_line = list(self._entry_row())
            huge_line[4] = 2**31
            huge_string = list(self._entry_row())
            huge_string[2] = "x" * 70000
            for query_name, row, context in (
                ("entries", huge_line, source),
                ("entries", huge_string, source),
                ([], self._entry_row(), source),
                ("entries", self._entry_row(), DecodeSource(source_root="bad", query_sha256="a" * 64)),
            ):
                with self.subTest(query_name=query_name):
                    with self.assertRaises(AnalyzerError) as raised:
                        decode_rows(query_name, ENTRY_COLUMNS, [row], context)
                    self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")

            with self.assertRaises(AnalyzerError) as raised:
                decode_rows("entries", ENTRY_COLUMNS, [self._entry_row()] * 4097, source)
            self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")

    def test_all_downstream_column_contracts_are_fixed_and_semantic_free(self):
        families = {
            "growth": GROWTH_COLUMNS,
            "flow": FLOW_COLUMNS,
            "guard": GUARD_COLUMNS,
            "bound": BOUND_COLUMNS,
            "release": RELEASE_COLUMNS,
        }
        for name, columns in families.items():
            with self.subTest(name=name):
                self.assertIsInstance(columns, tuple)
                self.assertGreater(len(columns), 0)
                self.assertEqual(len(columns), len(set(columns)))
                self.assertFalse(
                    {"entry_id", "growth_id", "effective", "assertion", "verdict"}
                    & set(columns)
                )


if __name__ == "__main__":
    unittest.main()
