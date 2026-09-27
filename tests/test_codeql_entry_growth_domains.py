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


@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class EntryGrowthDomainFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.source_root = (
            cls.root / "tests/fixtures/entry_growth_domains/src/main/java"
        ).resolve()
        cls.fixture = (
            cls.source_root / "fixture/flow/EntryGrowthDomainFixture.java"
        )
        cls.lines = cls.fixture.read_text(encoding="utf-8").splitlines()
        cls.database = fixture_database(str(cls.source_root))
        cls.temporary = tempfile.TemporaryDirectory()
        cls.flow_rows = cls.query_rows("EntryToGrowth.ql")
        cls.association_rows = cls.query_rows("EntryToGrowthAssociations.ql")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @classmethod
    def marker_line(cls, marker: str) -> int:
        return next(
            number
            for number, line in enumerate(cls.lines, 1)
            if marker in line
        )

    @classmethod
    def query_rows(cls, query_name: str) -> list[dict[str, object]]:
        query = cls.root / "codeql/dosweb/Flows" / query_name
        temporary = Path(cls.temporary.name)
        result = run_query(
            query,
            cls.database,
            temporary / query.stem,
            codeql_binary=str(_codeql_wrapper(temporary)),
        )
        return decode_bqrs_json(
            "flow",
            json.loads(result.decoded_path.read_text(encoding="utf-8")),
            DecodeSource(cls.database.source_root, result.query_sha256),
        )

    def test_generic_request_helper_to_parser_has_complete_flow(self) -> None:
        sink_line = self.marker_line("helper-parser-positive")
        direct = [
            row for row in self.flow_rows
            if row["sink_start_line"] == sink_line
        ]
        self.assertEqual(len(direct), 1, self.flow_rows)
        self.assertEqual(direct[0]["attacker_target"], "size")
        self.assertEqual(direct[0]["attacker_source"], "request")
        self.assertEqual(direct[0]["attacker_sink"], "request")
        self.assertEqual(direct[0]["confidence"], "proven")
        self.assertEqual(direct[0]["coverage_status"], "complete")
        self.assertEqual(
            direct[0]["coverage_note"], "same_handler_global_dataflow"
        )

        associated = [
            row for row in self.association_rows
            if row["sink_start_line"] == sink_line
            and row["confidence"] == "proven"
            and row["coverage_status"] == "complete"
        ]
        self.assertEqual(len(associated), 1, self.association_rows)
        self.assertTrue(
            associated[0]["attacker_source"].endswith(".helperParser"), associated
        )
        self.assertEqual(associated[0]["attacker_sink"], "request")

    def test_derived_extent_flow_ends_at_growth_dimension_expression(self) -> None:
        sink_line = self.marker_line("derived-flow-positive")
        direct = [
            row for row in self.flow_rows
            if row["sink_start_line"] == sink_line
        ]
        self.assertEqual(len(direct), 1, self.flow_rows)
        self.assertEqual(direct[0]["attacker_target"], "size")
        self.assertEqual(direct[0]["attacker_source"], "content")
        self.assertEqual(direct[0]["attacker_sink"], "width")
        self.assertEqual(direct[0]["confidence"], "proven")
        self.assertEqual(direct[0]["coverage_status"], "complete")
        self.assertEqual(
            direct[0]["coverage_note"],
            "same_handler_derived_dimension_dataflow",
        )

        associated = [
            row for row in self.association_rows
            if row["sink_start_line"] == sink_line
            and row["confidence"] == "proven"
            and row["coverage_status"] == "complete"
        ]
        self.assertEqual(len(associated), 1, self.association_rows)
        self.assertEqual(associated[0]["attacker_sink"], "width")

    def test_server_selected_content_does_not_become_direct_dimension_control(self) -> None:
        sink_line = self.marker_line("shared-derived-flow")
        direct_handler_line = self.marker_line("directDerivedHelper(HttpServletRequest")
        selected_handler_line = self.marker_line("serverSelectedDerived(HttpServletRequest")

        for rows in (self.flow_rows, self.association_rows):
            shared = [row for row in rows if row["sink_start_line"] == sink_line]
            self.assertTrue(shared, rows)
            complete = [
                row
                for row in shared
                if row["confidence"] == "proven"
                and row["coverage_status"] == "complete"
            ]
            self.assertEqual(
                {row["source_start_line"] for row in complete},
                {direct_handler_line},
                complete,
            )
            selected = [
                row
                for row in shared
                if row["source_start_line"] == selected_handler_line
            ]
            if rows is self.flow_rows:
                self.assertFalse(selected, shared)
            else:
                self.assertTrue(selected, shared)
                self.assertTrue(
                    all(
                        row["confidence"] == "partial"
                        and row["coverage_status"] == "partial"
                        for row in selected
                    ),
                    selected,
                )

    def test_lookalikes_without_the_complete_chain_emit_no_flow(self) -> None:
        forbidden_lines = {
            self.marker_line("metadata-helper-negative"),
            self.marker_line("unparsed-helper-negative"),
            self.marker_line("ordinary-extent-negative"),
            self.marker_line("fixed-producer-negative"),
        }
        for rows in (self.flow_rows, self.association_rows):
            self.assertTrue(
                forbidden_lines.isdisjoint(
                    {row["sink_start_line"] for row in rows}
                ),
                rows,
            )

    def test_direct_and_embedded_flow_sources_are_identical(self) -> None:
        for relative in (
            "Flows/EntryGrowthDomain.qll",
            "Flows/EntryToGrowthAssociations.ql",
        ):
            with self.subTest(relative=relative):
                self.assertEqual(
                    (self.root / "codeql/dosweb" / relative).read_bytes(),
                    (
                        self.root / "dosweb/codeql/pack/dosweb" / relative
                    ).read_bytes(),
                )


if __name__ == "__main__":
    unittest.main()
