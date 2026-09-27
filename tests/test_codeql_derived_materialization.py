from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query
from tests.support.fixture_database import fixture_database
from tests.test_codeql_entry_queries import _codeql_wrapper


_RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql")
_JAVAC = shutil.which("javac")
_ROOT = Path(__file__).parents[1]
_SOURCE_ROOT = (
    _ROOT
    / "tests"
    / "fixtures"
    / "derived_materialization"
    / "src"
    / "main"
    / "java"
).resolve()
_FIXTURE = _SOURCE_ROOT / "fixture" / "derived" / "DerivedMaterializationFixture.java"


def _marker_line(marker: str) -> int:
    return next(
        line_number
        for line_number, line in enumerate(
            _FIXTURE.read_text(encoding="utf-8").splitlines(), start=1
        )
        if marker in line
    )


@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class DerivedMaterializationQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database = fixture_database(str(_SOURCE_ROOT))

    def _rows(self, query_name: str) -> list[dict[str, object]]:
        query = _ROOT / "codeql" / "dosweb" / "Growth" / query_name
        with tempfile.TemporaryDirectory() as temporary:
            result = run_query(
                query,
                self.database,
                Path(temporary) / query.stem,
                codeql_binary=str(_codeql_wrapper(Path(temporary))),
            )
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
            return decode_bqrs_json(
                "growth",
                payload,
                DecodeSource(self.database.source_root, result.query_sha256),
            )

    def test_direct_servlet_request_body_helper_followed_by_parser_is_complete(self) -> None:
        rows = self._rows("InputMaterialization.ql")
        positive = [
            row
            for row in rows
            if row["site_file"].endswith("DerivedMaterializationFixture.java")
            and row["site_start_line"] == _marker_line("body-helper-positive")
        ]
        self.assertEqual(len(positive), 1, positive)
        self.assertEqual(positive[0]["coverage_status"], "complete")
        self.assertEqual(
            positive[0]["coverage_note"],
            "servlet_request_body_helper_then_structured_parser",
        )

        forbidden_lines = {
            _marker_line(marker)
            for marker in (
                "uri-negative",
                "query-negative",
                "header-negative",
                "cookie-negative",
                "session-negative",
            )
        }
        self.assertTrue(
            forbidden_lines.isdisjoint(
                {
                    row["site_start_line"]
                    for row in rows
                    if row["site_file"].endswith("DerivedMaterializationFixture.java")
                }
            ),
            rows,
        )

    def test_encoded_extent_must_feed_a_real_dimensioned_materializer(self) -> None:
        rows = self._rows("DirectAllocation.ql")
        fixture_rows = [
            row
            for row in rows
            if row["site_file"].endswith("DerivedMaterializationFixture.java")
        ]
        by_line = {row["site_start_line"]: row for row in fixture_rows}
        positive_line = _marker_line("materializer-positive")
        self.assertIn(positive_line, by_line, fixture_rows)
        self.assertEqual(by_line[positive_line]["coverage_status"], "complete")
        self.assertEqual(
            by_line[positive_line]["coverage_note"],
            "derived_dimension_materialization:uncapped_after_derivation",
        )
        self.assertNotIn(_marker_line("ordinary-length-negative"), by_line)

        cap_after = by_line[_marker_line("cap-after-materializer")]
        self.assertEqual(
            cap_after["coverage_note"],
            "derived_dimension_materialization:post_derivation_cap_present",
        )
        cap_before = by_line[_marker_line("cap-before-materializer")]
        self.assertEqual(
            cap_before["coverage_note"],
            "derived_dimension_materialization:uncapped_after_derivation",
        )

    def test_direct_and_embedded_domains_and_queries_remain_identical(self) -> None:
        relative_paths = (
            "Growth/RequestMaterializationDomain.qll",
            "Growth/DerivedAllocationDomain.qll",
            "Growth/InputMaterialization.ql",
            "Growth/DirectAllocation.ql",
        )
        for relative in relative_paths:
            with self.subTest(relative=relative):
                self.assertEqual(
                    (_ROOT / "codeql" / "dosweb" / relative).read_bytes(),
                    (_ROOT / "dosweb" / "codeql" / "pack" / "dosweb" / relative).read_bytes(),
                )
