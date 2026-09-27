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
class CodeqlBindingCardinalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.source_root = (
            cls.root
            / "tests/fixtures/binding_cardinality/src/main/java"
        ).resolve()
        cls.fixture_file = (
            cls.source_root
            / "fixture/binding/BindingCardinalityController.java"
        )
        cls.lines = cls.fixture_file.read_text(encoding="utf-8").splitlines()
        cls.database = fixture_database(str(cls.source_root))
        cls.temporary = tempfile.TemporaryDirectory()

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

    def query_rows(self, relative: str, family: str) -> list[dict[str, object]]:
        query = self.root / "codeql/dosweb" / relative
        temporary = Path(self.temporary.name)
        result = run_query(
            query,
            self.database,
            temporary / (query.stem + "-results"),
            codeql_binary=str(_codeql_wrapper(temporary)),
        )
        return decode_bqrs_json(
            family,
            json.loads(result.decoded_path.read_text(encoding="utf-8")),
            DecodeSource(self.database.source_root, result.query_sha256),
        )

    def test_direct_and_embedded_binding_cardinality_sources_match(self) -> None:
        relative_paths = (
            "Entries/SpringMvcRequestBinding.qll",
            "Entries/SpringMvcEntries.ql",
            "Growth/ContainerCardinalityDomain.qll",
            "Growth/LoopAmplification.qll",
            "Growth/ContainerGrowth.ql",
            "Flows/EntryGrowthDomain.qll",
        )
        for relative in relative_paths:
            with self.subTest(relative=relative):
                self.assertEqual(
                    (self.root / "codeql/dosweb" / relative).read_bytes(),
                    (
                        self.root
                        / "dosweb/codeql/pack/dosweb"
                        / relative
                    ).read_bytes(),
                )

    def test_implicit_and_explicit_model_attributes_are_entry_sources(self) -> None:
        rows = self.query_rows("Entries/SpringMvcEntries.ql", "entries")
        modeled = {
            (row["handler_fqn"].rsplit(".", 1)[-1], row["attacker_input_name"]): row
            for row in rows
            if row["handler_fqn"].startswith(
                "fixture.binding.BindingCardinalityController."
            )
        }
        for method in ("implicit", "explicit"):
            with self.subTest(method=method):
                self.assertEqual(
                    "model_attribute",
                    modeled[(method, "user")]["attacker_input_kind"],
                )
                self.assertEqual("complete", modeled[(method, "user")]["coverage_status"])

        framework_values = [
            row
            for row in rows
            if row["handler_fqn"].endswith(".frameworkValues")
        ]
        self.assertFalse(
            any(row["attacker_input_kind"] == "model_attribute" for row in framework_values),
            framework_values,
        )

    def test_model_attribute_getter_keys_have_complete_flow_proof(self) -> None:
        growth_rows = self.query_rows("Growth/ContainerGrowth.ql", "growth")
        flow_rows = self.query_rows("Flows/EntryToGrowth.ql", "flow")
        association_rows = self.query_rows(
            "Flows/EntryToGrowthAssociations.ql", "flow"
        )
        for marker in ("implicit-getter-growth", "explicit-getter-growth"):
            sink_line = self.marker_line(marker)
            with self.subTest(marker=marker):
                rows = [
                    row for row in growth_rows
                    if row["site_start_line"] == sink_line
                ]
                self.assertTrue(rows, growth_rows)
                self.assertTrue(
                    any(
                        row["demand_input_role"] == "key"
                        and row["coverage_status"] == "complete"
                        and "attacker_key_driver" in row["coverage_note"]
                        for row in rows
                    ),
                    rows,
                )
                for evidence, expected_source in (
                    (flow_rows, "user"),
                    (
                        association_rows,
                        f"fixture.binding.BindingCardinalityController.{marker.split('-', 1)[0]}",
                    ),
                ):
                    matching = [
                        row for row in evidence
                        if row["sink_start_line"] == sink_line
                    ]
                    self.assertTrue(matching, evidence)
                    self.assertTrue(
                        any(
                            row["attacker_target"] == "key"
                            and row["attacker_source"] == expected_source
                            and row["confidence"] == "proven"
                            and row["coverage_status"] == "complete"
                            and row["coverage_note"] == "same_handler_global_dataflow"
                            for row in matching
                        ),
                        matching,
                    )

    def test_dense_size_plus_positive_constant_proves_fresh_key_and_value(self) -> None:
        growth_rows = self.query_rows("Growth/ContainerGrowth.ql", "growth")
        flow_rows = self.query_rows("Flows/EntryToGrowth.ql", "flow")
        association_rows = self.query_rows(
            "Flows/EntryToGrowthAssociations.ql", "flow"
        )
        for marker in ("dense-fresh-growth", "dense-plus-two-growth"):
            sink_line = self.marker_line(marker)
            with self.subTest(marker=marker):
                rows = [
                    row for row in growth_rows
                    if row["site_start_line"] == sink_line
                ]
                self.assertEqual(
                    {("key", "complete"), ("value", "complete")},
                    {
                        (row["demand_input_role"], row["coverage_status"])
                        for row in rows
                    },
                    rows,
                )
                notes = {row["coverage_note"] for row in rows}
                self.assertTrue(
                    any("server_derived_fresh_key" in note for note in notes), notes
                )
                self.assertTrue(
                    any("attacker_value_driver" in note for note in notes), notes
                )
                self.assertFalse(
                    any("key_driver_unclassified" in note for note in notes), notes
                )
                flow_matching = [
                    row for row in flow_rows
                    if row["sink_start_line"] == sink_line
                ]
                self.assertTrue(flow_matching, flow_rows)
                self.assertTrue(
                    any(
                        row["attacker_target"] == "value"
                        and row["attacker_source"] == "user"
                        and row["attacker_sink"] == "user"
                        and row["confidence"] == "proven"
                        and row["coverage_status"] == "complete"
                        for row in flow_matching
                    ),
                    flow_matching,
                )
                self.assertFalse(
                    any(row["attacker_target"] == "key" for row in flow_matching),
                    flow_matching,
                )

                association_matching = [
                    row for row in association_rows
                    if row["sink_start_line"] == sink_line
                ]
                self.assertTrue(association_matching, association_rows)
                self.assertTrue(
                    any(
                        row["attacker_target"] == "value"
                        and row["attacker_source"].startswith(
                            "fixture.binding.BindingCardinalityController."
                        )
                        and row["attacker_sink"] == "user"
                        and row["confidence"] == "proven"
                        and row["coverage_status"] == "complete"
                        for row in association_matching
                    ),
                    association_matching,
                )
                self.assertFalse(
                    any(
                        row["attacker_target"] == "key"
                        and row["confidence"] == "proven"
                        and row["coverage_status"] == "complete"
                        for row in association_matching
                    ),
                    association_matching,
                )

    def test_non_proven_cardinality_shapes_never_gain_complete_value_demand(self) -> None:
        rows = self.query_rows("Growth/ContainerGrowth.ql", "growth")
        for marker in (
            "different-map-growth",
            "zero-offset-growth",
            "subtraction-growth",
            "unknown-offset-growth",
            "request-local-growth",
            "sparse-growth",
            "unknown-init-growth",
            "selected-handler-mutation-growth",
            "fixed-key-growth",
        ):
            sink_line = self.marker_line(marker)
            matching = [row for row in rows if row["site_start_line"] == sink_line]
            with self.subTest(marker=marker):
                self.assertFalse(
                    any(
                        row["demand_input_role"] == "value"
                        and row["coverage_status"] == "complete"
                        for row in matching
                    ),
                    matching,
                )
                self.assertFalse(
                    any("server_derived_fresh_key" in row["coverage_note"] for row in matching),
                    matching,
                )


if __name__ == "__main__":
    unittest.main()
