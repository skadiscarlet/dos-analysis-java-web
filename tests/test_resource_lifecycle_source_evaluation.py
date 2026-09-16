from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from dosweb.cli import main, parse_cli_values
from dosweb.codeql.database import DatabaseInfo
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.adapters import AnalysisUnit, ExtractedFacts
from dosweb.resource_lifecycle.models import AnalysisBudget
from dosweb.resource_lifecycle.solver import solve
from dosweb.resource_lifecycle.source_evaluation import (
    SOURCE_EVALUATION_MODES,
    SourceExpectedOutcome,
    _dimension_observation,
    _disable_cross_event_propagation,
    _population_observation,
    _state_observation,
    _write_csv,
    load_source_suite,
)
from tests.support.fixture_database import fixture_database
from tests.test_resource_lifecycle_async_solver import task_program
from tests.test_resource_lifecycle_events import contract


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/resource_lifecycle_v1_1"
SOURCE_ROOT = FIXTURE / "src/main/java"
SUITE = FIXTURE / "source-cases.json"
RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"


class ResourceLifecycleSourceEvaluationContractTests(unittest.TestCase):
    def test_manifest_freezes_six_source_pairs_and_both_mode_expectations(self) -> None:
        suite = load_source_suite(SUITE, source_root=SOURCE_ROOT)

        groups: dict[str, list[str]] = {}
        for case in suite.cases:
            groups.setdefault(case.group, []).append(case.case_id)
            self.assertEqual(
                set(SOURCE_EVALUATION_MODES),
                {expected.mode for expected in case.expectations},
            )
            self.assertTrue(case.entry_callable.startswith("java-callable-v1:"))
            for expected in case.expectations:
                self.assertTrue(expected.dimension)
                self.assertTrue(expected.scope)
                self.assertTrue(expected.cut)
                self.assertTrue(expected.lifecycle_status)

        self.assertEqual({f"S{index}" for index in range(1, 7)}, set(groups))
        self.assertTrue(all(len(case_ids) == 2 for case_ids in groups.values()))
        self.assertEqual(12, len(suite.cases))
        self.assertEqual(
            hashlib.sha256(SUITE.read_bytes()).hexdigest(), suite.suite_sha256
        )

    def test_cross_event_ablation_only_deletes_relations_and_records_gaps(self) -> None:
        program = task_program()
        executor = replace(contract(), contract_id="executor")
        unit = AnalysisUnit("Fixture.handle", program, (), (executor,))
        original_transition_ids = {
            transition.transition_id for transition in program.transitions
        }

        ablated, metadata = _disable_cross_event_propagation(unit)

        self.assertEqual(program, unit.program)
        self.assertFalse(ablated.program.call_bindings)
        self.assertFalse(ablated.program.task_bindings)
        self.assertFalse(ablated.program.task_exits)
        self.assertTrue(
            {
                transition.transition_id
                for transition in ablated.program.transitions
            }
            < original_transition_ids
        )
        self.assertTrue(
            all(
                not transition.population_effects
                for transition in ablated.program.transitions
            )
        )
        self.assertTrue(
            any(
                gap[3] == "cross_event_propagation_disabled"
                for gap in ablated.program.coverage_gaps
            )
        )
        self.assertGreater(metadata["removed_task_bindings"], 0)
        self.assertGreater(metadata["removed_transitions"], 0)
        self.assertEqual(program.families, ablated.program.families)
        self.assertEqual(program.instances, ablated.program.instances)
        self.assertEqual(program.holders, ablated.program.holders)
        self.assertEqual(program.events, ablated.program.events)
        self.assertEqual(program.program_points, ablated.program.program_points)
        self.assertEqual(program.entry_event_ids, ablated.program.entry_event_ids)
        self.assertEqual(program.exit_event_ids, ablated.program.exit_event_ids)
        self.assertEqual(program.contracts_version, ablated.program.contracts_version)
        self.assertEqual(unit.invariants, ablated.invariants)
        self.assertEqual(unit.executor_contracts, ablated.executor_contracts)
        self.assertEqual(
            set(metadata["removed_transition_ids"]),
            original_transition_ids
            - {
                transition.transition_id
                for transition in ablated.program.transitions
            },
        )
        self.assertEqual(
            {
                transition.transition_id: transition
                for transition in program.transitions
                if transition.transition_id
                not in set(metadata["removed_transition_ids"])
            },
            {
                transition.transition_id: transition
                for transition in ablated.program.transitions
            },
        )
        self.assertTrue(
            solve(program, budget=AnalysisBudget(max_steps=10000)).property_states[
                "after_task_termination"
            ]
        )
        self.assertFalse(
            solve(
                ablated.program, budget=AnalysisBudget(max_steps=10000)
            ).property_states["after_task_termination"]
        )

    def test_state_observation_fails_closed_on_incomplete_or_unknown_state(self) -> None:
        unit = AnalysisUnit("Fixture.handle", task_program(), (), (replace(contract(), contract_id="executor"),))
        expected = SourceExpectedOutcome(
            "full",
            "held_instances",
            "resource_family",
            "all_tasks_terminated_after_request",
            "bounded",
            0,
            None,
        )
        state = {
            "held_counts": [["family:stream", {"lower": 0, "upper": 0}]],
            "unknown_reasons": [],
        }
        incomplete = _state_observation(
            expected,
            {
                "terminated": False,
                "unknown_reasons": ["analysis_budget_exhausted"],
                "property_states": {
                    "all_tasks_terminated_after_request": {"event:normal": state}
                },
            },
            unit,
            "family:stream",
        )
        self.assertEqual("unknown", incomplete["lifecycle_status"])
        self.assertIn("analysis_budget_exhausted", incomplete["reason_codes"])

        unknown_state = _state_observation(
            expected,
            {
                "terminated": True,
                "unknown_reasons": [],
                "property_states": {
                    "all_tasks_terminated_after_request": {
                        "event:normal": {
                            **state,
                            "unknown_reasons": ["unmodeled_resource_effect"],
                        }
                    }
                },
            },
            unit,
            "family:stream",
        )
        self.assertEqual("unknown", unknown_state["lifecycle_status"])
        self.assertEqual(
            ["expected_property_unavailable", "missing_property"], unknown_state["reason_codes"]
        )

    def test_internal_tuple_reasons_are_preserved_and_unknown_population_has_no_bound(self) -> None:
        unit = AnalysisUnit(
            "Fixture.handle",
            task_program(),
            (),
            (replace(contract(), contract_id="executor"),),
        )
        dimension_expected = SourceExpectedOutcome(
            "full",
            "close_obligation",
            "all_exits",
            "all_modeled_exits",
            "unknown",
            None,
            "release_missing_exceptional_path",
        )
        dimension = _dimension_observation(
            dimension_expected,
            {
                "properties": [
                    {
                        "property_id": "published:close",
                        "cut": "all_modeled_exits",
                        "dimension": "close_obligation",
                        "resource_family_id": "family:stream",
                        "scope": "all_exits",
                        "status": "unknown",
                        "upper_bound": None,
                        "unknown_reasons": ("release_missing_exceptional_path",),
                    }
                ]
            },
            unit,
            "family:stream",
        )
        self.assertEqual(
            ["release_missing_exceptional_path"], dimension["reason_codes"]
        )

        population_expected = SourceExpectedOutcome(
            "full",
            "accepted_task_population",
            "executor",
            "arbitrary_finite_repetitions",
            "unknown",
            None,
            "executor_population_binding_unavailable",
        )
        population = _population_observation(
            population_expected,
            {
                "properties": [
                    {
                        "property_id": "published:population",
                        "resource_family_id": None,
                        "cut": "arbitrary_finite_repetitions",
                        "dimension": "accepted_task_population",
                        "scope": "executor:executor",
                        "repeat_assumption": (
                            "arbitrary_finite_repetitions_of_external_accept"
                        ),
                        "status": "unknown",
                        "upper_bound": None,
                        "unknown_reasons": (
                            "executor_population_binding_unavailable",
                        ),
                    }
                ]
            },
            unit,
            "family:stream",
        )
        self.assertEqual("unknown", population["lifecycle_status"])
        self.assertIsNone(population["upper_bound"])
        self.assertEqual(
            ["executor_population_binding_unavailable"],
            population["reason_codes"],
        )

    def test_source_cases_csv_preserves_frozen_property(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source-cases.csv"
            _write_csv(
                path,
                [
                    {
                        "case_id": "case",
                        "group": "S1",
                        "pair": "positive",
                        "property": "frozen lifecycle property",
                        "entry_callable": "java-callable-v1:Fixture.case(I)V",
                        "mode": "full",
                        "dimension": "held_instances",
                        "scope": "resource_family",
                        "cut": "all_tasks_terminated_after_request",
                        "observed_scope": "all_tasks_terminated_after_request",
                        "lifecycle_status": "bounded",
                        "upper_bound": 0,
                        "reason_codes": [],
                        "expected_status": "bounded",
                        "expected_upper_bound": 0,
                        "reason_contains": None,
                        "matches_expected": True,
                        "change_from_full": False,
                    }
                ],
            )
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))

        self.assertEqual("frozen lifecycle property", rows[0]["property"])

    def test_source_evaluation_wraps_internal_solver_failure(self) -> None:
        suite = load_source_suite(SUITE, source_root=SOURCE_ROOT)
        program = task_program()
        extracted = ExtractedFacts(
            "static_verified",
            "0" * 64,
            "resource-lifecycle-codeql-v1",
            suite.budget,
            (
                AnalysisUnit(
                    suite.cases[0].entry_callable,
                    program,
                    (),
                    (replace(contract(), contract_id="executor"),),
                ),
            ),
            (),
            {
                "end_to_end_mode": "real_source_codeql",
                "database_fingerprint": "1" * 64,
                "matched_entry_methods": sorted(
                    item.entry_callable for item in suite.cases
                ),
            },
        )
        database = DatabaseInfo(Path("fixture.db"), SOURCE_ROOT, "1" * 64)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "dosweb.resource_lifecycle.source_evaluation.validate_database",
            return_value=database,
        ), patch(
            "dosweb.resource_lifecycle.source_evaluation._codeql_facts",
            return_value=extracted,
        ), patch(
            "dosweb.resource_lifecycle.source_evaluation._analyze_payload",
            side_effect=ValueError("invalid derived graph"),
        ):
            from dosweb.resource_lifecycle.source_evaluation import (
                evaluate_source_suite,
            )

            with self.assertRaises(AnalyzerError) as raised:
                evaluate_source_suite(
                    SUITE,
                    SOURCE_ROOT,
                    Path("fixture.db"),
                    Path(tmp),
                )

        self.assertEqual(
            "INTERNAL_RESOURCE_EVALUATION_FAILED", raised.exception.code
        )

    def test_source_evaluation_success_path_writes_complete_artifact_set(self) -> None:
        from dosweb.resource_lifecycle.source_evaluation import evaluate_source_suite

        suite = load_source_suite(SUITE, source_root=SOURCE_ROOT)
        program = task_program()
        executor = replace(contract(), contract_id="executor")
        extracted = ExtractedFacts(
            "static_verified",
            "0" * 64,
            "resource-lifecycle-codeql-v1",
            suite.budget,
            tuple(
                AnalysisUnit(item.entry_callable, program, (), (executor,))
                for item in suite.cases
            ),
            (),
            {
                "end_to_end_mode": "real_source_codeql",
                "database_fingerprint": "1" * 64,
                "matched_entry_methods": sorted(
                    item.entry_callable for item in suite.cases
                ),
                "source_snapshot_sha256": "2" * 64,
                "query_provenance": [],
                "query_suite_sha256": "3" * 64,
                "provenance_sha256": "6" * 64,
            },
        )
        result_units = [
            {
                "unit_id": item.entry_callable,
                "terminated": True,
                "unknown_reasons": [],
                "dimensions": [],
                "population_properties": [],
                "property_states": {},
            }
            for item in suite.cases
        ]
        results = (
            {"schema_version": "1.1", "units": result_units, "result_sha256": "4" * 64},
            {"schema_version": "1.1", "units": result_units, "result_sha256": "5" * 64},
        )
        database = DatabaseInfo(Path("fixture.db"), SOURCE_ROOT, "1" * 64)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "dosweb.resource_lifecycle.source_evaluation.validate_database",
            return_value=database,
        ), patch(
            "dosweb.resource_lifecycle.source_evaluation._codeql_facts",
            return_value=extracted,
        ), patch(
            "dosweb.resource_lifecycle.source_evaluation._analyze_payload",
            side_effect=results,
        ):
            output = Path(tmp)
            artifact = evaluate_source_suite(
                SUITE,
                SOURCE_ROOT,
                Path("fixture.db"),
                output,
            )
            files = {
                path.name
                for path in output.iterdir()
                if path.is_file()
            }
            manifest = json.loads(
                (output / "run-manifest.json").read_text(encoding="utf-8")
            )
            with (output / "source-cases.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                csv_rows = list(csv.DictReader(stream))

        self.assertEqual(
            {
                "facts.json",
                "coverage.json",
                "full-results.json",
                "disable-cross-event-results.json",
                "source-evaluation.json",
                "source-cases.csv",
                "metrics.json",
                "run-manifest.json",
                "summary.md",
            },
            files,
        )
        self.assertEqual(24, len(artifact["cases"]))
        self.assertEqual(24, len(csv_rows))
        self.assertTrue(all(row["property"] for row in csv_rows))
        self.assertEqual(
            {"full": "4" * 64, "disable_cross_event_propagation": "5" * 64},
            manifest["result_sha256"],
        )
        self.assertEqual("6" * 64, manifest["provenance_sha256"])

    def test_source_evaluation_cli_has_explicit_local_source_surface(self) -> None:
        values = parse_cli_values(
            [
                "resource-source-evaluate",
                "--suite",
                str(SUITE),
                "--source-root",
                str(SOURCE_ROOT),
                "--database",
                "fixture.db",
                "--out",
                "report",
            ]
        )

        self.assertEqual("resource-source-evaluate", values["command"])
        self.assertEqual(SOURCE_ROOT, values["source_root"])

    def test_source_evaluation_cli_rejects_missing_database_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = main(
                [
                    "resource-source-evaluate",
                    "--suite",
                    str(SUITE),
                    "--source-root",
                    str(SOURCE_ROOT),
                    "--out",
                    tmp,
                ]
            )

        self.assertNotEqual(0, status)

@unittest.skipUnless(
    RUN_FIXTURES and shutil.which("codeql") and shutil.which("javac"),
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class ResourceLifecycleSourceEvaluationCodeqlTests(unittest.TestCase):
    def test_twelve_source_variants_preserve_oracle_and_wrapper_exceptions(self) -> None:
        database = fixture_database(str(SOURCE_ROOT))
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "source-evaluation"
            status = main(
                [
                    "resource-source-evaluate",
                    "--suite",
                    str(SUITE),
                    "--source-root",
                    str(SOURCE_ROOT),
                    "--database",
                    str(database.path),
                    "--out",
                    str(output),
                ]
            )
            artifact = json.loads(
                (output / "source-evaluation.json").read_text(encoding="utf-8")
            )
            facts = json.loads((output / "facts.json").read_text(encoding="utf-8"))
            full_results = json.loads(
                (output / "full-results.json").read_text(encoding="utf-8")
            )
            run_manifest = json.loads(
                (output / "run-manifest.json").read_text(encoding="utf-8")
            )
            with (output / "source-cases.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                csv_rows = list(csv.DictReader(stream))

        self.assertEqual(0, status)
        self.assertEqual(24, len(artifact["cases"]))
        mismatches = [
            row for row in artifact["cases"] if not row["matches_expected"]
        ]
        # RC1 restores exact wrapper rejection returns without modifying the
        # frozen source or oracle. All bounds come from ordinary properties.
        self.assertEqual([], mismatches, json.dumps(mismatches, ensure_ascii=False, indent=2))
        self.assertEqual(12, artifact["metrics"]["modes"]["full"]["cases"])
        self.assertEqual(
            12,
            artifact["metrics"]["modes"]["full"]["expected_matches"],
        )
        self.assertGreaterEqual(artifact["metrics"]["determinacy_gains"], 1)
        self.assertEqual("static_verified", facts["source_kind"])
        self.assertEqual("real_source_codeql", facts["coverage"]["end_to_end_mode"])
        self.assertEqual(2, len(facts["coverage"]["query_provenance"]))
        self.assertEqual(12, facts["coverage"]["external_entry_units"])
        self.assertEqual(
            artifact["ablation"]["input_fact_snapshot_sha256"],
            artifact["ablation"]["output_fact_snapshot_sha256"],
        )
        self.assertEqual(0, artifact["ablation"]["facts_added"])
        self.assertEqual(0, artifact["ablation"]["facts_removed"])
        self.assertTrue(full_results["units"])
        self.assertEqual(24, len(csv_rows))
        self.assertTrue(all(row["property"] for row in csv_rows))
        self.assertEqual(64, len(run_manifest["implementation_sha256"]))
        self.assertEqual(
            full_results["result_sha256"],
            run_manifest["result_sha256"]["full"],
        )

        by_case_mode = {
            (row["case_id"], row["mode"]): row for row in artifact["cases"]
        }
        self.assertEqual(0, by_case_mode[("s2-task-only", "full")]["upper_bound"])
        self.assertEqual(1, by_case_mode[("s2-field-holder", "full")]["upper_bound"])
        self.assertEqual(
            "unknown",
            by_case_mode[("s3-missing-exceptional-close", "full")][
                "lifecycle_status"
            ],
        )
        self.assertEqual(
            "unknown",
            by_case_mode[
                ("s4-depth-two", "disable_cross_event_propagation")
            ]["lifecycle_status"],
        )
        self.assertEqual(
            5, by_case_mode[("s5-verified-capacity", "full")]["upper_bound"]
        )


if __name__ == "__main__":
    unittest.main()
