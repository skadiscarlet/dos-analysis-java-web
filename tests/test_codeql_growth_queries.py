from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import dosweb.production as production
from dosweb.artifacts.identifiers import file_sha256
from dosweb.codeql import DecodeSource, GROWTH_COLUMNS, decode_bqrs_json, run_query, validate_database
from dosweb.entries import AttackerInputFact, EntryFact, HandlerFact, RegistrationFact
from dosweb.growth import CandidateEntryLink, GrowthCandidate, normalize_growth_rows
from dosweb.growth.relevance import evaluate_candidate_relevance
from tests.support.fixture_database import fixture_database
from tests.test_codeql_entry_queries import _codeql_wrapper


_RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql")
_JAVAC = shutil.which("javac")


@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class CodeqlGrowthQueryTests(unittest.TestCase):
    def _direct_allocation_fixture(self) -> tuple[Path, Path]:
        root = Path(__file__).parents[1]
        source_root = (
            root
            / "tests"
            / "fixtures"
            / "direct_allocation_edges"
            / "src"
            / "main"
            / "java"
        ).resolve()
        return source_root, source_root / "fixture" / "DirectAllocationEdgeFixture.java"

    def _fixture_query_rows(
        self,
        query_relative: str,
        family: str,
    ) -> list[dict[str, object]]:
        root = Path(__file__).parents[1]
        source_root, _fixture = self._direct_allocation_fixture()
        database = fixture_database(str(source_root))
        query = root / "codeql" / "dosweb" / query_relative
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            result = run_query(
                query,
                database,
                temporary / (query.stem + "-direct-allocation-edge-results"),
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
            return decode_bqrs_json(
                family,
                payload,
                DecodeSource(database.source_root, result.query_sha256),
            )

    def _direct_allocation_edge_rows(self) -> tuple[list[dict[str, object]], Path]:
        _source_root, fixture = self._direct_allocation_fixture()
        return self._fixture_query_rows("Growth/DirectAllocation.ql", "growth"), fixture

    def _named_fixture_query_rows(
        self,
        fixture_name: str,
        query_relative: str,
        family: str,
    ) -> list[dict[str, object]]:
        root = Path(__file__).parents[1]
        source_root = (
            root
            / "tests"
            / "fixtures"
            / fixture_name
            / "src"
            / "main"
            / "java"
        ).resolve()
        database = fixture_database(str(source_root))
        query = root / "codeql" / "dosweb" / query_relative
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            result = run_query(
                query,
                database,
                temporary / (query.stem + f"-{fixture_name}-results"),
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
            return decode_bqrs_json(
                family,
                payload,
                DecodeSource(database.source_root, result.query_sha256),
            )

    def _direct_allocation_relevance(
        self,
        candidate: GrowthCandidate,
        *,
        input_name: str,
        handler_line: int,
        route: str,
    ):
        entry = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact(
                f"fixture.DirectAllocationEdgeFixture.{input_name}",
                candidate.site.file,
                handler_line,
            ),
            registration=RegistrationFact(
                "annotation_mapping",
                f"fixture.DirectAllocationEdgeFixture.{input_name}",
                candidate.site.file,
                handler_line - 1,
            ),
            registration_pattern_id=(
                "entry-registration-coverage:"
                "spring_mvc:annotation_mapping:spring_annotation_mapping"
            ),
            route_or_event=route,
            auth_context="unknown",
            attacker_inputs=(
                AttackerInputFact(input_name, "int", "request_parameter"),
            ),
            materialization_phase="in_handler",
        )
        link = CandidateEntryLink.create(
            candidate.growth_id,
            entry.entry_id,
            "complete",
            (candidate.growth_id, entry.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        return evaluate_candidate_relevance(entry, candidate, (link,))

    def test_multidimensional_array_enumerates_the_attacker_controlled_second_dimension(self) -> None:
        rows, fixture = self._direct_allocation_edge_rows()
        lines = fixture.read_text(encoding="utf-8").splitlines()
        sink_line = next(
            number
            for number, line in enumerate(lines, 1)
            if "new byte[1][width]" in line
        )
        handler_line = next(
            number
            for number, line in enumerate(lines, 1)
            if "multidimensionalArray(" in line
        )
        matching = [
            row
            for row in rows
            if row["site_file"].endswith("DirectAllocationEdgeFixture.java")
            and row["site_start_line"] == sink_line
        ]

        self.assertEqual(len(matching), 2, matching)
        self.assertEqual(
            {
                (
                    row["demand_input_name"],
                    row["demand_input_role"],
                    row["coverage_status"],
                    row["coverage_note"],
                )
                for row in matching
            },
            {
                (
                    "1",
                    "size",
                    "complete",
                    "direct_allocation:server_controlled_fixed_size",
                ),
                (
                    "width",
                    "size",
                    "complete",
                    "direct_allocation:handler_parameter_size",
                ),
            },
        )
        normalized = normalize_growth_rows(matching)
        self.assertEqual(len(normalized), 1)
        candidate = GrowthCandidate.from_dict(normalized[0])

        decision = self._direct_allocation_relevance(
            candidate,
            input_name="width",
            handler_line=handler_line,
            route="/multidimensional-array",
        )

        self.assertEqual(decision.status, "contract_eligible")
        self.assertNotIn("RELEVANCE_SERVER_SIZED_ALLOCATION", decision.reason_codes)

    def test_fixed_allocation_in_attacker_controlled_loop_emits_multiplicity_driver(self) -> None:
        rows, fixture = self._direct_allocation_edge_rows()
        lines = fixture.read_text(encoding="utf-8").splitlines()
        sink_line = next(
            number
            for number, line in enumerate(lines, 1)
            if "safe-assignment allocation" in line
        )
        handler_line = next(
            number
            for number, line in enumerate(lines, 1)
            if "void safeAssignmentLoop(" in line
        )
        matching = [
            row
            for row in rows
            if row["site_file"].endswith("DirectAllocationEdgeFixture.java")
            and row["site_start_line"] == sink_line
        ]

        self.assertEqual(len(matching), 2, matching)
        self.assertIn(
            (
                "count",
                "iteration_count",
                "complete",
                "direct_allocation:attacker_controlled_loop_multiplicity_proven",
            ),
            {
                (
                    row["demand_input_name"],
                    row["demand_input_role"],
                    row["coverage_status"],
                    row["coverage_note"],
                )
                for row in matching
            },
        )
        normalized = normalize_growth_rows(matching)
        self.assertEqual(len(normalized), 1)
        candidate = GrowthCandidate.from_dict(normalized[0])

        decision = self._direct_allocation_relevance(
            candidate,
            input_name="count",
            handler_line=handler_line,
            route="/safe-assignment-loop",
        )

        self.assertEqual(decision.status, "contract_eligible")
        self.assertNotIn("RELEVANCE_SERVER_SIZED_ALLOCATION", decision.reason_codes)

    def test_fixed_allocation_in_unmodeled_loop_is_partial_not_a_hard_negative(self) -> None:
        rows, fixture = self._direct_allocation_edge_rows()
        lines = fixture.read_text(encoding="utf-8").splitlines()
        sink_line = next(
            number
            for number, line in enumerate(lines, 1)
            if "server-only allocation" in line
        )
        matching = [
            row
            for row in rows
            if row["site_file"].endswith("DirectAllocationEdgeFixture.java")
            and row["site_start_line"] == sink_line
        ]

        self.assertTrue(matching)
        normalized = normalize_growth_rows(matching)
        self.assertEqual(len(normalized), 1)
        candidate = GrowthCandidate.from_dict(normalized[0])
        self.assertEqual(candidate.coverage_status, "partial")
        self.assertIn(
            "direct_allocation:loop_multiplicity_unmodeled",
            candidate.coverage_notes,
        )
        self.assertNotIn(
            "RELEVANCE_SERVER_SIZED_ALLOCATION",
            self._direct_allocation_relevance(
                candidate,
                input_name="ignored",
                handler_line=next(
                    number
                    for number, line in enumerate(lines, 1)
                    if "void unmodeledLoop(" in line
                ),
                route="/unmodeled-loop",
            ).reason_codes,
        )

    def test_only_strict_canonical_unconditional_loop_proves_multiplicity(self) -> None:
        rows, fixture = self._direct_allocation_edge_rows()
        lines = fixture.read_text(encoding="utf-8").splitlines()
        unsafe_markers = (
            "argument-subexpression allocation",
            "return allocation",
            "throw allocation",
            "conditional-rhs allocation",
            "bound-mutation allocation",
            "break-limited allocation",
            "server-capped allocation",
            "nested-lambda allocation",
            "nested-callable allocation",
        )
        for marker in unsafe_markers:
            with self.subTest(marker=marker):
                sink_line = next(
                    number
                    for number, line in enumerate(lines, 1)
                    if marker in line
                )
                matching = [
                    row
                    for row in rows
                    if row["site_file"].endswith(
                        "DirectAllocationEdgeFixture.java"
                    )
                    and row["site_start_line"] == sink_line
                ]
                self.assertTrue(matching, marker)
                notes = {
                    (
                        row["demand_input_role"],
                        row["coverage_status"],
                        row["coverage_note"],
                    )
                    for row in matching
                }
                self.assertNotIn(
                    (
                        "iteration_count",
                        "complete",
                        "direct_allocation:"
                        "attacker_controlled_loop_multiplicity_proven",
                    ),
                    notes,
                )
                self.assertIn(
                    (
                        "iteration_count",
                        "partial",
                        "direct_allocation:loop_multiplicity_unmodeled",
                    ),
                    notes,
                )

    def test_real_direct_allocation_rows_mature_only_through_real_flow_proofs(self) -> None:
        growth_rows = self._fixture_query_rows(
            "Growth/DirectAllocation.ql", "growth"
        )
        association_rows = self._fixture_query_rows(
            "Flows/EntryToGrowthAssociations.ql", "flow"
        )
        flow_rows = self._fixture_query_rows("Flows/EntryToGrowth.ql", "flow")
        _source_root, fixture = self._direct_allocation_fixture()
        lines = fixture.read_text(encoding="utf-8").splitlines()
        fixture_file = "fixture/DirectAllocationEdgeFixture.java"

        cases = (
            (
                "multidimensionalArray",
                "width",
                "/multidimensional-array",
                "new byte[1][width]",
                "size",
            ),
            (
                "safeAssignmentLoop",
                "count",
                "/safe-assignment-loop",
                "safe-assignment allocation",
                "iteration_count",
            ),
        )
        for method_name, input_name, route, sink_marker, target in cases:
            with self.subTest(method=method_name):
                handler_line = next(
                    number
                    for number, line in enumerate(lines, 1)
                    if f" {method_name}(" in line
                )
                sink_line = next(
                    number
                    for number, line in enumerate(lines, 1)
                    if sink_marker in line
                )
                site_rows = [
                    row
                    for row in growth_rows
                    if row["site_file"] == fixture_file
                    and row["site_start_line"] == sink_line
                ]
                normalized = normalize_growth_rows(site_rows)
                self.assertEqual(len(normalized), 1, site_rows)
                candidate = GrowthCandidate.from_dict(normalized[0])
                entry = EntryFact.create(
                    framework="spring_mvc",
                    protocol="http",
                    handler=HandlerFact(
                        f"fixture.DirectAllocationEdgeFixture.{method_name}",
                        fixture_file,
                        handler_line,
                    ),
                    registration=RegistrationFact(
                        "annotation_mapping",
                        f"fixture.DirectAllocationEdgeFixture.{method_name}",
                        fixture_file,
                        handler_line - 1,
                    ),
                    registration_pattern_id=(
                        "entry-registration-coverage:"
                        "spring_mvc:annotation_mapping:spring_annotation_mapping"
                    ),
                    route_or_event=route,
                    auth_context="unknown",
                    attacker_inputs=(
                        AttackerInputFact(
                            input_name, "int", "request_parameter"
                        ),
                    ),
                    materialization_phase="in_handler",
                )
                matching_associations = [
                    row
                    for row in association_rows
                    if row["source_file"] == fixture_file
                    and row["source_start_line"] == handler_line
                    and row["sink_file"] == fixture_file
                    and row["sink_start_line"] == sink_line
                    and row["attacker_target"] == target
                ]
                matching_flows = [
                    row
                    for row in flow_rows
                    if row["source_file"] == fixture_file
                    and row["source_start_line"] == handler_line
                    and row["sink_file"] == fixture_file
                    and row["sink_start_line"] == sink_line
                    and row["attacker_target"] == target
                    and row["attacker_source"] == input_name
                ]
                self.assertEqual(len(matching_associations), 1, matching_associations)
                self.assertEqual(len(matching_flows), 1, matching_flows)
                links, association = production._candidate_association(  # noqa: SLF001
                    {entry.entry_id: entry},
                    candidate,
                    matching_associations,
                    matching_flows,
                )
                self.assertEqual(len(links), 1)
                self.assertEqual(links[0].status, "complete")
                self.assertEqual(association.status, "formal_eligible")
                relevance = evaluate_candidate_relevance(entry, candidate, links)
                self.assertEqual(relevance.status, "contract_eligible")
                matured = production._mature_disposition(  # noqa: SLF001
                    candidate,
                    association,
                    status="formal_eligible",
                    relevance_status=relevance.status,
                    reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
                )
                self.assertEqual(matured.status, "formal_eligible")

    def test_real_exact_container_and_async_rows_mature_through_shared_loop_flows(self) -> None:
        growth_rows_by_query = {
            query: self._named_fixture_query_rows("spring", query, "growth")
            for query in (
                "Growth/ContainerGrowth.ql",
                "Growth/AsyncWorkGrowth.ql",
            )
        }
        association_rows = self._named_fixture_query_rows(
            "spring", "Flows/EntryToGrowthAssociations.ql", "flow"
        )
        flow_rows = self._named_fixture_query_rows(
            "spring", "Flows/EntryToGrowth.ql", "flow"
        )
        root = Path(__file__).parents[1]
        fixture = (
            root
            / "tests"
            / "fixtures"
            / "spring"
            / "src"
            / "main"
            / "java"
            / "fixture"
            / "spring"
            / "SpringFixture.java"
        )
        lines = fixture.read_text(encoding="utf-8").splitlines()
        fixture_file = "fixture/spring/SpringFixture.java"
        cases = (
            (
                "Growth/ContainerGrowth.ql",
                "requestLocalExactInduction",
                "/request-local-exact-induction",
                "requestLocalExactInduction.put(index, body);",
                "iteration_count",
            ),
            (
                "Growth/AsyncWorkGrowth.ql",
                "asyncExactLoop",
                "/async-exact-loop",
                "exactExecutor.execute(() -> consume(body));",
                "submission_count",
            ),
        )
        for query, method_name, route, sink_marker, target in cases:
            with self.subTest(method=method_name):
                handler_line = next(
                    number
                    for number, line in enumerate(lines, 1)
                    if f" {method_name}(" in line
                )
                sink_line = next(
                    number
                    for number, line in enumerate(lines, 1)
                    if sink_marker in line
                )
                site_rows = [
                    row
                    for row in growth_rows_by_query[query]
                    if row["site_file"] == fixture_file
                    and row["site_start_line"] == sink_line
                ]
                normalized = normalize_growth_rows(site_rows)
                self.assertEqual(len(normalized), 1, site_rows)
                candidate = GrowthCandidate.from_dict(normalized[0])
                self.assertIn(
                    ("count", target),
                    {(item.name, item.role) for item in candidate.demand_inputs},
                )
                self.assertEqual(candidate.coverage_status, "complete")
                entry = EntryFact.create(
                    framework="spring_mvc",
                    protocol="http",
                    handler=HandlerFact(
                        f"fixture.spring.SpringFixture.{method_name}",
                        fixture_file,
                        handler_line,
                    ),
                    registration=RegistrationFact(
                        "annotation_mapping",
                        f"fixture.spring.SpringFixture.{method_name}",
                        fixture_file,
                        handler_line - 1,
                    ),
                    registration_pattern_id=(
                        "entry-registration-coverage:"
                        "spring_mvc:annotation_mapping:spring_annotation_mapping"
                    ),
                    route_or_event=route,
                    auth_context="unauthenticated",
                    attacker_inputs=(
                        AttackerInputFact("count", "int", "request_parameter"),
                        AttackerInputFact("body", "byte[]", "request_body"),
                    ),
                    materialization_phase="in_handler",
                )
                matching_associations = [
                    row
                    for row in association_rows
                    if row["source_file"] == fixture_file
                    and row["source_start_line"] == handler_line
                    and row["sink_file"] == fixture_file
                    and row["sink_start_line"] == sink_line
                    and row["attacker_target"] == target
                ]
                matching_flows = [
                    row
                    for row in flow_rows
                    if row["source_file"] == fixture_file
                    and row["source_start_line"] == handler_line
                    and row["sink_file"] == fixture_file
                    and row["sink_start_line"] == sink_line
                    and row["attacker_target"] == target
                    and row["attacker_source"] == "count"
                ]
                self.assertEqual(len(matching_associations), 1, matching_associations)
                self.assertEqual(len(matching_flows), 1, matching_flows)
                links, association = production._candidate_association(  # noqa: SLF001
                    {entry.entry_id: entry},
                    candidate,
                    matching_associations,
                    matching_flows,
                )
                self.assertEqual(len(links), 1)
                self.assertEqual(links[0].status, "complete")
                self.assertEqual(association.status, "formal_eligible")
                relevance = evaluate_candidate_relevance(entry, candidate, links)
                self.assertEqual(relevance.status, "contract_eligible")
                matured = production._mature_disposition(  # noqa: SLF001
                    candidate,
                    association,
                    status="formal_eligible",
                    relevance_status=relevance.status,
                    reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
                )
                self.assertEqual(matured.status, "formal_eligible")

    def test_mixed_image_dimensions_keep_the_attacker_controlled_row_after_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            source_root = temporary / "source"
            annotation_root = (
                source_root / "org" / "springframework" / "web" / "bind" / "annotation"
            )
            annotation_root.mkdir(parents=True)
            (annotation_root / "RequestMapping.java").write_text(
                """package org.springframework.web.bind.annotation;
public @interface RequestMapping { String[] value() default {}; }
""",
                encoding="utf-8",
            )
            (annotation_root / "RequestParam.java").write_text(
                """package org.springframework.web.bind.annotation;
public @interface RequestParam { String value() default \"\"; }
""",
                encoding="utf-8",
            )
            fixture = source_root / "fixture" / "MixedDimensionFixture.java"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                """package fixture;
import java.awt.image.BufferedImage;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
public class MixedDimensionFixture {
  @RequestMapping("/image")
  public BufferedImage image(@RequestParam("width") int width) {
    return new BufferedImage(width, 1, BufferedImage.TYPE_INT_RGB);
  }
}
""",
                encoding="utf-8",
            )
            sink_line = next(
                number
                for number, line in enumerate(
                    fixture.read_text(encoding="utf-8").splitlines(), 1
                )
                if "new BufferedImage" in line
            )
            database_path = temporary / "mixed-dimension-database"
            classes = temporary / "classes"
            classes.mkdir()
            java_files = sorted(source_root.rglob("*.java"))
            completed = subprocess.run(
                [
                    _CODEQL,
                    "database",
                    "create",
                    str(database_path),
                    "--language=java",
                    f"--source-root={source_root}",
                    f"--command={_JAVAC} -d {classes} "
                    + " ".join(str(path.relative_to(source_root)) for path in java_files),
                    "--overwrite",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            database = validate_database(database_path)
            query = (
                Path(__file__).parents[1]
                / "codeql"
                / "dosweb"
                / "Growth"
                / "DirectAllocation.ql"
            )
            result = run_query(
                query,
                database,
                temporary / "mixed-dimension-results",
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
            if row["site_file"].endswith("MixedDimensionFixture.java")
            and row["site_start_line"] == sink_line
        ]
        self.assertEqual(len(matching), 2, matching)
        self.assertEqual(
            {(row["demand_input_name"], row["coverage_note"]) for row in matching},
            {
                ("width", "direct_allocation:handler_parameter_size"),
                ("1", "direct_allocation:server_controlled_fixed_size"),
            },
        )
        normalized = normalize_growth_rows(matching)
        self.assertEqual(len(normalized), 1)
        candidate = GrowthCandidate.from_dict(normalized[0])
        entry = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact(
                "fixture.MixedDimensionFixture.image",
                candidate.site.file,
                7,
            ),
            registration=RegistrationFact(
                "annotation_mapping",
                "fixture.MixedDimensionFixture.image",
                candidate.site.file,
                6,
            ),
            registration_pattern_id=(
                "entry-registration-coverage:"
                "spring_mvc:annotation_mapping:spring_annotation_mapping"
            ),
            route_or_event="/image",
            auth_context="unknown",
            attacker_inputs=(
                AttackerInputFact("width", "int", "request_parameter"),
            ),
            materialization_phase="in_handler",
        )
        link = CandidateEntryLink.create(
            candidate.growth_id,
            entry.entry_id,
            "complete",
            (candidate.growth_id, entry.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )

        decision = evaluate_candidate_relevance(entry, candidate, (link,))

        self.assertEqual(decision.status, "contract_eligible")
        self.assertIn("RELEVANCE_ATTACKER_SIZED_ALLOCATION", decision.reason_codes)
        self.assertNotIn("RELEVANCE_SERVER_SIZED_ALLOCATION", decision.reason_codes)

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
            "http_session_attribute_write:fixed_attribute_fresh_session_unproven",
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

        expected_markers = {
            "DirectAllocation.ql": (
                "p0AttackerParameter",
                "getADimension",
                "direct_allocation:handler_parameter_size",
                "direct_allocation:server_controlled_fixed_size",
                "direct_allocation:size_origin_unclassified",
                "allocation_loop_multiplicity",
                "provenAttackerLoopMultiplicity",
                "direct_allocation:attacker_controlled_loop_multiplicity_proven",
                "direct_allocation:loop_multiplicity_unmodeled",
            ),
            "ContainerGrowth.ql": (
                "import LoopAmplification",
                "persistent_field_container_write:fixed_key",
                "persistent_field_container_write:attacker_key_driver",
                "persistent_field_container_write:attacker_value_driver",
                "persistent_field_container_write:key_driver_unclassified",
                'evidence = "request_local_container_write"',
                'driverNote = "attacker_key_driver"',
                "stableRequestLocalInstance",
                "emptyHashMapAllocation",
                "canonicalAttackerBoundForLoop",
                "provenAttackerLoopMultiplicity",
                "call.getNumArgument() = 1",
                "requestLocalUnconditionalIteration",
                'cardinalityNote = "attacker_controlled_loop_cardinality_proven"',
                'cardinalityNote = "attacker_controlled_loop_per_iteration_execution_unproven"',
                'cardinalityNote = "attacker_controlled_loop_new_entry_unproven"',
                'cardinalityNote = "attacker_controlled_loop_instance_stability_unproven"',
            ),
            "AsyncWorkGrowth.ql": (
                '"submission_count"',
                "provenAttackerLoopMultiplicity",
                "single_submission_no_enclosing_loop",
                "attacker_controlled_loop_multiplicity_proven",
            ),
            "InputMaterialization.ql": (
                "request_stream_origin_proven",
                "stream_origin_unclassified",
                "server_side_file_materialization",
            ),
        }
        for query_name, markers in expected_markers.items():
            source = (query_root / query_name).read_text(encoding="utf-8")
            for marker in markers:
                with self.subTest(query=query_name, marker=marker):
                    self.assertIn(marker, source)
        shared_loop = (query_root / "LoopAmplification.qll").read_text(
            encoding="utf-8"
        )
        for marker in (
            'induction.getType().hasName("int")',
            "PostIncExpr",
            "PreIncExpr",
        ):
            with self.subTest(query="LoopAmplification.qll", marker=marker):
                self.assertIn(marker, shared_loop)
        self.assertNotIn(
            "getDimension(0)",
            (query_root / "DirectAllocation.ql").read_text(encoding="utf-8"),
        )

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
                        if fixture == "spring":
                            spring_fixture = (
                                source_root / "fixture" / "spring" / "SpringFixture.java"
                            )
                            spring_lines = spring_fixture.read_text(
                                encoding="utf-8"
                            ).splitlines()
                            request_loop_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalLoop.put(" in line
                            )
                            request_once_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalOnce.put(" in line
                            )
                            request_exact_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalExactInduction.put(" in line
                            )
                            request_byte_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalByteCyclic.put(" in line
                            )
                            request_float_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalFloatCyclic.put(" in line
                            )
                            request_long_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalLongInduction.put(" in line
                            )
                            request_non_zero_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalNonZeroInduction.put(" in line
                            )
                            request_derived_bound_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalDerivedBound.put(" in line
                            )
                            request_decrement_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalDecrement.put(" in line
                            )
                            request_multi_statement_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalMultiStatement.put(" in line
                            )
                            request_same_key_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalSameKey.put(" in line
                            )
                            request_fresh_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalFreshEachIteration.put(" in line
                            )
                            request_list_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalListLoop.add(" in line
                            )
                            request_list_indexed_add_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalListIndexedAdd.add(" in line
                            )
                            request_list_fixed_two_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalListFixedTwoAttackerBound.add(" in line
                            )
                            request_list_infeasible_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalListInfeasible.add(" in line
                            )
                            request_list_tautology_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalListFixedTwoTautology.add(" in line
                            )
                            request_list_infeasible_condition_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalListInfeasibleCondition.add(" in line
                            )
                            request_conditional_map_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalConditionalMap.put(" in line
                            )
                            request_conditional_list_line = next(
                                number
                                for number, line in enumerate(spring_lines, 1)
                                if "requestLocalConditionalList.add(" in line
                            )
                            request_local_lines = {
                                request_loop_line,
                                request_once_line,
                                request_exact_line,
                                request_byte_line,
                                request_float_line,
                                request_long_line,
                                request_non_zero_line,
                                request_derived_bound_line,
                                request_decrement_line,
                                request_multi_statement_line,
                                request_same_key_line,
                                request_fresh_line,
                                request_list_line,
                                request_list_indexed_add_line,
                                request_list_fixed_two_line,
                                request_list_infeasible_line,
                                request_list_tautology_line,
                                request_list_infeasible_condition_line,
                                request_conditional_map_line,
                                request_conditional_list_line,
                            }
                            request_local = {
                                item["site"]["start_line"]: item
                                for item in matching
                                if item["site"]["file"].endswith("SpringFixture.java")
                                and item["site"]["start_line"]
                                in request_local_lines
                            }
                            self.assertEqual(
                                request_local_lines,
                                set(request_local),
                                matching,
                            )
                            loop_candidate = request_local[request_loop_line]
                            self.assertEqual(
                                {
                                    "dimension": "entries",
                                    "receiver": "fixture.spring.SpringFixture.requestLocalLoop",
                                    "field_path": "requestLocalLoop",
                                },
                                {
                                    key: loop_candidate["resource_point"][key]
                                    for key in ("dimension", "receiver", "field_path")
                                },
                            )
                            self.assertEqual("request", loop_candidate["escape_scope"])
                            self.assertEqual("partial", loop_candidate["coverage_status"])
                            self.assertIn(
                                "request_local_container_write:attacker_key_driver:"
                                "attacker_controlled_loop_new_entry_unproven",
                                loop_candidate["coverage_notes"],
                            )
                            exact_candidate = request_local[request_exact_line]
                            self.assertEqual("request", exact_candidate["escape_scope"])
                            self.assertEqual("complete", exact_candidate["coverage_status"])
                            self.assertIn(
                                "request_local_container_write:key_driver_unclassified:"
                                "attacker_controlled_loop_cardinality_proven",
                                exact_candidate["coverage_notes"],
                            )
                            for noncanonical_line in (
                                request_byte_line,
                                request_float_line,
                                request_long_line,
                                request_non_zero_line,
                                request_derived_bound_line,
                                request_decrement_line,
                            ):
                                noncanonical_candidate = request_local[noncanonical_line]
                                self.assertEqual(
                                    "partial", noncanonical_candidate["coverage_status"]
                                )
                                self.assertFalse(
                                    any(
                                        note.endswith(
                                            ":attacker_controlled_loop_cardinality_proven"
                                        )
                                        for note in noncanonical_candidate[
                                            "coverage_notes"
                                        ]
                                    ),
                                    noncanonical_candidate,
                                )
                            multi_statement_candidate = request_local[
                                request_multi_statement_line
                            ]
                            self.assertEqual(
                                "partial", multi_statement_candidate["coverage_status"]
                            )
                            self.assertIn(
                                "request_local_container_write:key_driver_unclassified:"
                                "attacker_controlled_loop_per_iteration_execution_unproven",
                                multi_statement_candidate["coverage_notes"],
                            )
                            once_candidate = request_local[request_once_line]
                            self.assertEqual("request", once_candidate["escape_scope"])
                            self.assertEqual("partial", once_candidate["coverage_status"])
                            self.assertIn(
                                "request_local_container_write:attacker_key_driver:"
                                "single_operation_no_enclosing_loop",
                                once_candidate["coverage_notes"],
                            )
                            same_key_candidate = request_local[
                                request_same_key_line
                            ]
                            self.assertEqual(
                                "partial", same_key_candidate["coverage_status"]
                            )
                            self.assertIn(
                                "request_local_container_write:attacker_key_driver:"
                                "attacker_controlled_loop_new_entry_unproven",
                                same_key_candidate["coverage_notes"],
                            )
                            fresh_candidate = request_local[request_fresh_line]
                            self.assertEqual(
                                "partial", fresh_candidate["coverage_status"]
                            )
                            self.assertIn(
                                "request_local_container_write:attacker_key_driver:"
                                "attacker_controlled_loop_instance_stability_unproven",
                                fresh_candidate["coverage_notes"],
                            )
                            list_candidate = request_local[request_list_line]
                            self.assertEqual(
                                "complete", list_candidate["coverage_status"]
                            )
                            self.assertIn(
                                "request_local_container_write:attacker_value_driver:"
                                "attacker_controlled_loop_cardinality_proven",
                                list_candidate["coverage_notes"],
                            )
                            indexed_add_candidate = request_local[
                                request_list_indexed_add_line
                            ]
                            self.assertEqual(
                                "partial", indexed_add_candidate["coverage_status"]
                            )
                            self.assertFalse(
                                any(
                                    note.endswith(
                                        ":attacker_controlled_loop_cardinality_proven"
                                    )
                                    for note in indexed_add_candidate[
                                        "coverage_notes"
                                    ]
                                ),
                                indexed_add_candidate,
                            )
                            for noncanonical_list_line in (
                                request_list_fixed_two_line,
                                request_list_infeasible_line,
                                request_list_tautology_line,
                                request_list_infeasible_condition_line,
                            ):
                                noncanonical_list = request_local[
                                    noncanonical_list_line
                                ]
                                self.assertEqual(
                                    "partial", noncanonical_list["coverage_status"]
                                )
                                self.assertFalse(
                                    any(
                                        note.endswith(
                                            ":attacker_controlled_loop_cardinality_proven"
                                        )
                                        for note in noncanonical_list[
                                            "coverage_notes"
                                        ]
                                    ),
                                    noncanonical_list,
                                )
                            for conditional_line, driver_note in (
                                (request_conditional_map_line, "key_driver_unclassified"),
                                (request_conditional_list_line, "attacker_value_driver"),
                            ):
                                conditional_candidate = request_local[conditional_line]
                                self.assertEqual(
                                    "partial", conditional_candidate["coverage_status"]
                                )
                                self.assertIn(
                                    "request_local_container_write:"
                                    f"{driver_note}:"
                                    "attacker_controlled_loop_per_iteration_execution_unproven",
                                    conditional_candidate["coverage_notes"],
                                )
                            notes = {note for item in matching for note in item["coverage_notes"]}
                            self.assertTrue(
                                any(
                                    "persistent_field_container_write:attacker_key_driver:"
                                    "attacker_controlled_loop_multiplicity_proven" == note
                                    for note in notes
                                ),
                                notes,
                            )
                            self.assertTrue(
                                any(note.endswith(":loop_bound_not_attacker_proven") for note in notes),
                                notes,
                            )
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
