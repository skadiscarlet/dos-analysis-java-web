from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest

from dosweb.cli import main, parse_cli_values
from dosweb.resource_lifecycle import models as lifecycle_models
from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.io import program_from_dict, program_to_dict
from dosweb.resource_lifecycle.adapters import (
    AnalysisUnit,
    ExtractedFacts,
    adapt_codeql_rows,
    extracted_from_dict,
)
from dosweb.resource_lifecycle.commands import _analyze_payload, _evidence_payload
from dosweb.resource_lifecycle.models import (
    AnalysisBudget,
    Effect,
    Event,
    Holder,
    Program,
    Transition,
)
from tests.test_resource_lifecycle_solver import effect, program_for


class ResourceLifecycleCliTests(unittest.TestCase):
    def _schema_1_1_relation_program(self) -> Program:
        TaskExit = getattr(lifecycle_models, "TaskExit")
        base = program_for(())
        task_events = (
            Event("event:queue", "task_queue", "Fixture.task", "accepted"),
            Event("event:run", "task_run", "Fixture.task", "worker reserved"),
            Event("event:task-normal", "task_exit", "Fixture.task", "normal"),
            Event("event:task-error", "task_exit", "Fixture.task", "exceptional"),
        )
        points = (
            lifecycle_models.ProgramPoint(
                "point:call", "Fixture.handle", "call", effect("create").location
            ),
            lifecycle_models.ProgramPoint(
                "point:callee", "Fixture.wrapper", "entry", effect("create").location
            ),
            lifecycle_models.ProgramPoint(
                "point:task-normal", "Fixture.task", "task_exit", effect("create").location
            ),
            lifecycle_models.ProgramPoint(
                "point:task-error", "Fixture.task", "task_exit", effect("create").location
            ),
        )
        task_binding = lifecycle_models.TaskBinding(
            "task-binding:stream",
            "task:stream",
            "instance:stream",
            "holder:task",
            "contract:executor",
            "event:queue",
            "event:run",
            "event:task-normal",
            "event:task-error",
            "Fixture.task",
            ("fact:capture",),
        )
        task_exits = (
            TaskExit(
                "task-exit:normal",
                "task:stream",
                "point:task-normal",
                "event:task-normal",
                "Fixture.task",
                "normal",
                ("fact:normal-exit",),
            ),
            TaskExit(
                "task-exit:exceptional",
                "task:stream",
                "point:task-error",
                "event:task-error",
                "Fixture.task",
                "exceptional",
                ("fact:exceptional-exit",),
            ),
        )
        population = lifecycle_models.PopulationEffect(
            "population:enqueue",
            "enqueue",
            "contract:executor",
            "task:stream",
            "q < K",
            1,
            0,
            "absent",
            "queued",
            effect("create").location,
            ("fact:enqueue",),
        )
        return replace(
            base,
            holders=base.holders + (Holder("holder:task", "task", "task", "exact"),),
            events=base.events + task_events,
            transitions=(
                Transition(
                    "transition:enqueue",
                    "event:entry",
                    "event:queue",
                    "accepted",
                    (),
                    "internal",
                    (),
                    (population,),
                ),
            ),
            program_points=points,
            task_bindings=(task_binding,),
            task_exits=task_exits,
        )

    def test_schema_1_1_round_trips_task_exits_and_population(self) -> None:
        self.assertEqual("1.1", lifecycle_models.SCHEMA_VERSION)
        self.assertTrue(hasattr(lifecycle_models, "TaskExit"), "missing TaskExit")
        program = self._schema_1_1_relation_program()

        rebuilt = program_from_dict(
            json.loads(json.dumps(program_to_dict(program), sort_keys=True))
        )

        self.assertEqual(program, rebuilt)
        self.assertEqual("1.1", program_to_dict(rebuilt)["schema_version"])
        self.assertEqual({"normal", "exceptional"}, {item.kind for item in rebuilt.task_exits})

    def test_schema_1_1_rejects_dangling_task_executor_callable_and_untrusted_relations(self) -> None:
        self.assertTrue(hasattr(lifecycle_models, "TaskExit"), "missing TaskExit")
        base = program_for(())
        untrusted_location = replace(effect("create").location, source_kind="llm_proposed")
        with self.assertRaisesRegex(ValueError, "trusted source"):
            replace(
                base,
                program_points=(
                    lifecycle_models.ProgramPoint(
                        "point:untrusted", "Fixture.handle", "effect", untrusted_location
                    ),
                ),
            )

        population = lifecycle_models.PopulationEffect(
            "population:dangling-executor",
            "enqueue",
            "contract:missing",
            "task:missing",
            "q < K",
            1,
            0,
            "absent",
            "queued",
            effect("create").location,
            ("fact:enqueue",),
        )
        with self.assertRaisesRegex(ValueError, "unknown task"):
            replace(
                base,
                transitions=(
                    Transition(
                        "transition:dangling-task",
                        "event:entry",
                        "event:normal",
                        "true",
                        (),
                        "internal",
                        (),
                        (population,),
                    ),
                ),
            )

        valid = self._schema_1_1_relation_program()
        duplicate_point = valid.program_points[0]
        with self.assertRaisesRegex(ValueError, "duplicate program point"):
            replace(valid, program_points=valid.program_points + (duplicate_point,))
        with self.assertRaisesRegex(ValueError, "callable"):
            replace(
                valid,
                task_exits=(
                    replace(valid.task_exits[0], task_callable="Fixture.otherTask"),
                    valid.task_exits[1],
                ),
            )
        with self.assertRaisesRegex(ValueError, "executor contract"):
            AnalysisUnit("manual:relations", valid, (), ())
        with self.assertRaisesRegex(ValueError, "executor"):
            replace(
                valid,
                transitions=(
                    replace(
                        valid.transitions[0],
                        population_effects=(
                            replace(
                                valid.transitions[0].population_effects[0],
                                executor_id="contract:other",
                            ),
                        ),
                    ),
                ),
            )
        with self.assertRaisesRegex(ValueError, "population effect"):
            replace(
                valid,
                transitions=valid.transitions
                + (
                    replace(
                        valid.transitions[0],
                        transition_id="transition:duplicate-population",
                    ),
                ),
            )
        with self.assertRaisesRegex(ValueError, "task exit kind"):
            replace(valid.task_exits[0], kind="guessed")

    def test_schema_1_1_executor_contract_has_explicit_termination_semantics(self) -> None:
        contract = ExecutorContract(
            contract_id="contract:executor",
            scheduling="queued",
            queue_capacity=3,
            capacity_atomic=True,
            completion_drops_capture=True,
            rejection_drops_capture=True,
            cancellation="drops_capture",
            source_kind="manual_fixture",
            version="executor-contract-v1",
            max_workers=2,
            rejection_policy="abort",
            termination="drops_capture",
        )

        self.assertEqual(2, contract.max_workers)
        self.assertEqual("abort", contract.rejection_policy)
        self.assertEqual("drops_capture", contract.termination)
        with self.assertRaisesRegex(ValueError, "capacity"):
            replace(contract, queue_capacity=-1)
        with self.assertRaisesRegex(ValueError, "worker"):
            replace(contract, max_workers=-1)
        with self.assertRaisesRegex(ValueError, "termination"):
            replace(contract, termination="guessed")

    def test_schema_1_1_loader_rejects_non_string_relation_evidence(self) -> None:
        payload = json.loads(
            json.dumps(program_to_dict(self._schema_1_1_relation_program()))
        )
        payload["task_exits"][0]["evidence_ids"] = [7]
        with self.assertRaisesRegex(ValueError, "evidence"):
            program_from_dict(payload)

        payload = json.loads(
            json.dumps(program_to_dict(self._schema_1_1_relation_program()))
        )
        payload["transitions"][0]["population_effects"][0]["evidence_ids"] = [7]
        with self.assertRaisesRegex(ValueError, "evidence"):
            program_from_dict(payload)

    def test_schema_1_1_loader_rejects_v1_1_relations_labeled_as_v1_0(self) -> None:
        payload = json.loads(
            json.dumps(program_to_dict(self._schema_1_1_relation_program()))
        )
        payload["schema_version"] = "1.0"

        with self.assertRaisesRegex(ValueError, "legacy schema"):
            program_from_dict(payload)

    def test_precision_unknown_depends_on_the_effect_evidence(self) -> None:
        program = program_for(
            (
                Transition(
                    "transition:normal",
                    "event:entry",
                    "event:normal",
                    "normal",
                    (effect("create"), effect("unknown_call")),
                    "normal",
                    (),
                ),
                Transition(
                    "transition:error",
                    "event:entry",
                    "event:error",
                    "exceptional",
                    (effect("create"), effect("unknown_call")),
                    "exceptional",
                    (),
                ),
            )
        )
        extracted = ExtractedFacts(
            "manual_fixture",
            "a" * 64,
            "manual-fixture-v1",
            AnalysisBudget(),
            (AnalysisUnit("manual:precision", program, ()),),
            (),
            {"end_to_end_mode": "manual_ir"},
        )

        evidence = _evidence_payload(extracted, _analyze_payload(extracted))

        self.assertTrue(evidence["dimension_derivations"])
        self.assertTrue(
            all(
                "fact:unknown_call" in derivation["evidence_ids"]
                for derivation in evidence["dimension_derivations"]
            )
        )

    def test_dimension_coverage_unknown_depends_on_the_partial_static_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "final class Fixture {\n}\n",
                encoding="utf-8",
            )
            common = {
                "unit_id": "java-callable-v1:Fixture.handle()V",
                "site_file": "Fixture.java",
                "site_start_line": 1,
                "site_start_column": 1,
                "instance_key": "Fixture.java:1:1",
                "resource_type": "fixture.Resource",
                "requires_close": True,
                "holder_kind": "none",
                "holder_scope": "none",
                "holder_key": "none",
                "target_event": "none",
                "capacity": "unknown",
                "normal_path": True,
                "exceptional_path": True,
                "source_evidence": "test",
                "coverage_status": "complete",
                "coverage_note": "allocation_identity_exact",
            }
            extracted = adapt_codeql_rows(
                (
                    {**common, "fact_kind": "create"},
                    {
                        **common,
                        "site_start_line": 2,
                        "fact_kind": "release",
                        "normal_path": False,
                        "exceptional_path": False,
                        "coverage_status": "partial",
                        "coverage_note": "conditional_release_not_must",
                    },
                ),
                source_root=source_root,
                query_sha256="a" * 64,
            )

        results = _analyze_payload(extracted)
        evidence = _evidence_payload(extracted, results)
        release_fact_id = next(fact.fact_id for fact in extracted.facts if fact.fact_kind == "release")
        close_proof = next(
            item
            for item in evidence["dimension_derivations"]
            if item["dimension"] == "close_obligation"
        )

        self.assertIn(release_fact_id, close_proof["evidence_ids"])
        self.assertIn(
            {"proof_id": close_proof["proof_id"], "evidence_id": release_fact_id},
            evidence["proof_dependencies"],
        )

    def test_published_aggregate_statuses_are_derived_from_dimension_results(self) -> None:
        program = replace(
            program_for(
                (
                    Transition(
                        "transition:normal",
                        "event:entry",
                        "event:normal",
                        "normal",
                        (effect("create"), effect("release")),
                        "normal",
                        (),
                    ),
                    Transition(
                        "transition:error",
                        "event:entry",
                        "event:error",
                        "exceptional",
                        (effect("create"), effect("release")),
                        "exceptional",
                        (),
                    ),
                )
            ),
            coverage_complete=False,
            coverage_gaps=(
                (
                    "close_obligation",
                    "family:stream",
                    "*",
                    "conditional_release_not_must",
                    "fact:conditional-release",
                ),
            ),
        )
        extracted = ExtractedFacts(
            "manual_fixture",
            "a" * 64,
            "manual-fixture-v1",
            AnalysisBudget(),
            (AnalysisUnit("manual:aggregate", program, ()),),
            (),
            {"end_to_end_mode": "manual_ir"},
        )

        unit = _analyze_payload(extracted)["units"][0]
        dimension_statuses = sorted({item["lifecycle_status"] for item in unit["dimensions"]})

        self.assertEqual(dimension_statuses, unit["lifecycle_statuses"])

    def _manifest(self, root: Path) -> Path:
        program = program_for(
            (
                Transition(
                    "transition:normal",
                    "event:entry",
                    "event:normal",
                    "normal",
                    (effect("create"), effect("retain", holder_id="holder:request"), effect("release")),
                    "normal",
                    (),
                ),
                Transition(
                    "transition:error",
                    "event:entry",
                    "event:error",
                    "exception",
                    (effect("create"), effect("retain", holder_id="holder:request"), effect("release")),
                    "exceptional",
                    (),
                ),
            )
        )
        path = root / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "mode": "manual_fixture",
                    "programs": [
                        {
                            "unit_id": "manual:sync",
                            "program": program_to_dict(program),
                            "invariants": [],
                            "executor_contracts": [],
                        }
                    ],
                    "budget": {"max_steps": 64, "max_updates_per_event": 8, "timeout_ms": 1000},
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path

    def _async_manifest(
        self,
        root: Path,
        *,
        contract_source_kind: str = "manual_fixture",
    ) -> Path:
        dispatch = Effect(
            effect_id="effect:dispatch:task",
            kind="dispatch",
            instance_id="instance:stream",
            family_id="family:stream",
            holder_id="holder:task",
            target_event_id="event:task",
            condition="accepted",
            location=effect("create").location,
            evidence_ids=("fact:dispatch",),
            contract_id="contract:manual-executor",
        )
        base = program_for(())
        program = replace(
            base,
            holders=base.holders + (Holder("holder:task", "task", "task", "exact"),),
            events=base.events + (Event("event:task", "task_run", "Fixture.task", "accepted"),),
            transitions=(
                Transition(
                    "transition:dispatch",
                    "event:entry",
                    "event:normal",
                    "normal",
                    (
                        effect("create"),
                        effect("retain", holder_id="holder:request"),
                        dispatch,
                        effect("drop", holder_id="holder:request"),
                    ),
                    "normal",
                    (),
                ),
            ),
            exit_event_ids=("event:normal",),
        )
        contract = ExecutorContract(
            contract_id="contract:manual-executor",
            scheduling="queued",
            queue_capacity=4,
            capacity_atomic=True,
            completion_drops_capture=True,
            rejection_drops_capture=True,
            cancellation="drops_capture",
            source_kind=contract_source_kind,
            version="executor-contract-v1",
        )
        path = root / "async-manifest.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "mode": "manual_fixture",
                    "programs": [
                        {
                            "unit_id": "manual:async",
                            "program": program_to_dict(program),
                            "invariants": [],
                            "executor_contracts": [asdict(contract)],
                        }
                    ],
                    "budget": {"max_steps": 64, "max_updates_per_event": 8, "timeout_ms": 1000},
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path

    def _static_facts(self, root: Path, *, normal_path: object = True) -> Path:
        source = root / "source"
        source.mkdir()
        (source / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
        rows = root / "rows.json"
        rows.write_text(
            json.dumps(
                [
                    {
                        "unit_id": "java-callable-v1:fixture.Imported.handle()V",
                        "site_file": "Fixture.java",
                        "site_start_line": 1,
                        "site_start_column": 1,
                        "fact_kind": "create",
                        "instance_key": "Fixture.java:1:1",
                        "resource_type": "fixture.Resource",
                        "requires_close": True,
                        "holder_kind": "none",
                        "holder_scope": "none",
                        "holder_key": "none",
                        "target_event": "none",
                        "capacity": "unknown",
                        "normal_path": normal_path,
                        "exceptional_path": True,
                        "source_evidence": "recorded_static_fact",
                        "coverage_status": "complete",
                        "coverage_note": "offline import fixture",
                    }
                ]
            ),
            encoding="utf-8",
        )
        manifest = root / "static-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "mode": "static_verified_json",
                    "rows": "rows.json",
                    "source_root": "source",
                    "query_sha256": "a" * 64,
                    "entry_methods": ["java-callable-v1:fixture.Imported.handle()V"],
                    "budget": {"max_steps": 64, "max_updates_per_event": 8, "timeout_ms": 1000},
                }
            ),
            encoding="utf-8",
        )
        facts = root / "facts"
        self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(facts)]))
        return facts / "facts.json"

    def test_schema_1_1_is_used_by_all_resource_cli_json_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = root / "facts"
            run = root / "run"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-extract",
                        "--manifest",
                        str(self._manifest(root)),
                        "--out",
                        str(facts),
                    ]
                ),
            )
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts / "facts.json"),
                        "--out",
                        str(run),
                        "--llm",
                        "off",
                    ]
                ),
            )
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))

            artifacts = {
                "facts": json.loads(
                    (facts / "facts.json").read_text(encoding="utf-8")
                ),
                "facts_snapshot": json.loads(
                    (run / "facts.snapshot.json").read_text(encoding="utf-8")
                ),
                "manifest": json.loads(
                    (run / "run-manifest.json").read_text(encoding="utf-8")
                ),
                "results": json.loads(
                    (run / "lifecycle-results.json").read_text(encoding="utf-8")
                ),
                "evidence": json.loads(
                    (run / "evidence.json").read_text(encoding="utf-8")
                ),
                "replay": json.loads(
                    (run / "replay.json").read_text(encoding="utf-8")
                ),
            }

        self.assertTrue(
            all(artifact["schema_version"] == "1.1" for artifact in artifacts.values())
        )
        self.assertEqual("resource-lifecycle-v1.1", artifacts["manifest"]["tool_version"])

    def test_parser_accepts_resource_commands_without_p0_database(self) -> None:
        values = parse_cli_values(["resource-extract", "--manifest", "fixture.json", "--out", "facts"])

        self.assertEqual("resource-extract", values["command"])
        self.assertEqual(Path("fixture.json"), values["manifest"])
        self.assertEqual(Path("facts"), values["out"])
        self.assertIsNone(values["database"])

    def test_manual_extract_analyze_and_replay_recompute_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            facts = root / "facts"
            run = root / "run"

            self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(facts)]))
            self.assertEqual(
                0,
                main(["resource-analyze", "--facts", str(facts / "facts.json"), "--out", str(run), "--llm", "off"]),
            )
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))

            facts_payload = json.loads((facts / "facts.json").read_text(encoding="utf-8"))
            manifest_payload = json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))

        self.assertEqual("manual_fixture", facts_payload["source_kind"])
        self.assertEqual("off", manifest_payload["llm"]["mode"])
        self.assertEqual("bounded", next(item for item in results["units"][0]["dimensions"] if item["dimension"] == "close_obligation")["lifecycle_status"])
        self.assertTrue(
            all(item["resource_family_id"] == "family:stream" for item in results["units"][0]["dimensions"])
        )
        exit_state = next(iter(results["units"][0]["exit_states"].values()))
        self.assertIn("held_counts", exit_state)
        self.assertIn("allocation_counts", exit_state)
        self.assertIn("peak_held_counts", exit_state)
        self.assertRegex(manifest_payload["implementation_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(replay["consistent"])
        self.assertEqual(results["result_sha256"], replay["recomputed_result_sha256"])

    def test_manual_async_contract_emits_five_complete_production_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = root / "facts"
            run = root / "run"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-extract",
                        "--manifest",
                        str(self._async_manifest(root)),
                        "--out",
                        str(facts),
                    ]
                ),
            )
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts / "facts.json"),
                        "--out",
                        str(run),
                        "--llm",
                        "off",
                    ]
                ),
            )
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        stages = results["units"][0]["async_stages"]
        self.assertEqual(1, len(stages))
        stage = stages[0]
        self.assertRegex(stage["stage_id"], r"^async-stage:[0-9a-f]{24}$")
        self.assertEqual("transition:dispatch", stage["transition_id"])
        self.assertEqual("effect:dispatch:task", stage["dispatch_effect_id"])
        self.assertEqual("contract:manual-executor", stage["contract_id"])
        self.assertEqual("event:task", stage["target_event_id"])
        expected_state_fields = {
            "instance_families",
            "instance_abstractions",
            "instance_confidences",
            "family_requires_close",
            "family_size_upper",
            "holder_kinds",
            "holder_scopes",
            "holder_precisions",
            "held_edges",
            "created_instances",
            "open_obligations",
            "must_released",
            "instance_obligation_counts",
            "obligation_counts",
            "allocation_counts",
            "held_counts",
            "peak_held_counts",
            "repeated_instances",
            "unknown_reasons",
        }
        for phase in ("submitted", "started", "completed", "rejected", "cancelled"):
            self.assertEqual(expected_state_fields, set(stage[phase]))
            self.assertIn("instance:stream", stage[phase]["open_obligations"])
        task_edge = ["instance:stream", "holder:task"]
        self.assertIn(task_edge, stage["submitted"]["held_edges"])
        self.assertIn(task_edge, stage["started"]["held_edges"])
        self.assertNotIn(task_edge, stage["completed"]["held_edges"])
        self.assertNotIn(task_edge, stage["rejected"]["held_edges"])
        self.assertNotIn(task_edge, stage["cancelled"]["held_edges"])
        self.assertIn("task_completion_drops_capture", stage["rule_ids"])
        self.assertIn("create_instance", stage["rule_ids"])
        self.assertIn("retain_holder_edge", stage["rule_ids"])
        self.assertEqual(
            {
                ("create_instance", "fact:create"),
                ("retain_holder_edge", "fact:retain"),
                ("dispatch_capture_on_accept", "fact:dispatch"),
                ("task_dequeue_is_phase_change", "fact:dispatch"),
                ("task_completion_drops_capture", "fact:dispatch"),
                ("task_rejection_does_not_capture", "fact:dispatch"),
                ("task_cancel_drops_capture", "fact:dispatch"),
                ("queued_execution_contract", "fact:dispatch"),
            },
            {tuple(item) for item in stage["rule_dependencies"]},
        )
        self.assertEqual(
            ["fact:create", "fact:dispatch", "fact:retain"],
            stage["evidence_ids"],
        )

    def test_missing_or_untrusted_executor_contract_keeps_conservative_async_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = root / "facts"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-extract",
                        "--manifest",
                        str(self._async_manifest(root)),
                        "--out",
                        str(facts),
                    ]
                ),
            )
            extracted = extracted_from_dict(
                json.loads((facts / "facts.json").read_text(encoding="utf-8"))
            )

        contract = extracted.units[0].executor_contracts[0]
        variants = {
            "missing": (),
            "untrusted": (replace(contract, source_kind="llm_proposed"),),
        }
        task_edge = ["instance:stream", "holder:task"]
        for expected_status, contracts in variants.items():
            with self.subTest(expected_status=expected_status):
                unit = replace(extracted.units[0], executor_contracts=contracts)
                stage = _analyze_payload(replace(extracted, units=(unit,)))["units"][0][
                    "async_stages"
                ][0]

                self.assertEqual(expected_status, stage["contract_status"])
                for phase in ("submitted", "started", "completed", "rejected", "cancelled"):
                    self.assertIn(task_edge, stage[phase]["held_edges"])
                    self.assertTrue(stage[phase]["unknown_reasons"])
                self.assertIn(
                    "completion_contract_unknown:contract:manual-executor",
                    stage["completed"]["unknown_reasons"],
                )
                self.assertIn(
                    "rejection_contract_unknown:contract:manual-executor",
                    stage["rejected"]["unknown_reasons"],
                )
                self.assertIn(
                    "cancel_contract_unknown:contract:manual-executor",
                    stage["cancelled"]["unknown_reasons"],
                )

    def test_explicit_trusted_contract_drops_only_task_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = root / "facts"
            run = root / "run"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-extract",
                        "--manifest",
                        str(
                            self._async_manifest(
                                root,
                                contract_source_kind="trusted_contract",
                            )
                        ),
                        "--out",
                        str(facts),
                    ]
                ),
            )
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts / "facts.json"),
                        "--out",
                        str(run),
                        "--llm",
                        "off",
                    ]
                ),
            )
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        stage = results["units"][0]["async_stages"][0]
        task_edge = ["instance:stream", "holder:task"]
        self.assertEqual("trusted_contract", stage["contract_source_kind"])
        self.assertNotIn(task_edge, stage["completed"]["held_edges"])
        self.assertNotIn(task_edge, stage["cancelled"]["held_edges"])
        self.assertIn("instance:stream", stage["completed"]["open_obligations"])
        self.assertIn("instance:stream", stage["cancelled"]["open_obligations"])

    def test_tracked_manual_manifest_is_a_runnable_offline_chain(self) -> None:
        manifest = Path("tests/fixtures/resource_lifecycle/manual-manifest.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = root / "facts"
            run = root / "run"

            self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(facts)]))
            self.assertEqual(0, main(["resource-analyze", "--facts", str(facts / "facts.json"), "--out", str(run), "--llm", "off"]))
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        by_dimension = {item["dimension"]: item["lifecycle_status"] for item in results["units"][0]["dimensions"]}
        self.assertEqual("bounded", by_dimension["held_instances"])
        self.assertEqual("bounded", by_dimension["close_obligation"])
        self.assertEqual("unknown", by_dimension["item_size_bytes"])

    def test_resource_analyze_rejects_live_llm_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            facts = root / "facts"
            self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(facts)]))

            status = main(
                ["resource-analyze", "--facts", str(facts / "facts.json"), "--out", str(root / "run"), "--llm", "live"]
            )

        self.assertEqual(2, status)

    def test_manual_extract_rejects_llm_proposed_executor_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["programs"][0]["executor_contracts"] = [
                {
                    "contract_id": "contract:untrusted",
                    "scheduling": "queued",
                    "queue_capacity": 4,
                    "capacity_atomic": True,
                    "completion_drops_capture": True,
                    "rejection_drops_capture": True,
                    "cancellation": "drops_capture",
                    "source_kind": "llm_proposed",
                    "version": "executor-contract-v1",
                }
            ]
            manifest.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

            status = main(
                ["resource-extract", "--manifest", str(manifest), "--out", str(root / "facts")]
            )

        self.assertEqual(5, status)

    def test_resource_analyze_rejects_tampered_derived_static_program(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._static_facts(root)
            payload = json.loads(facts.read_text(encoding="utf-8"))
            payload["units"][0]["program"]["coverage_complete"] = False
            facts.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

            status = main(["resource-analyze", "--facts", str(facts), "--out", str(root / "run"), "--llm", "off"])

        self.assertEqual(5, status)

    def test_static_import_rejects_string_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(AssertionError):
                self._static_facts(root, normal_path="false")

    def test_imported_static_rows_remain_distinct_from_manual_ir_and_real_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            rows = root / "rows.json"
            rows.write_text(
                json.dumps(
                    [
                        {
                            "unit_id": "java-callable-v1:fixture.Imported.handle()V",
                            "site_file": "Fixture.java",
                            "site_start_line": 1,
                            "site_start_column": 1,
                            "fact_kind": "create",
                            "instance_key": "Fixture.java:1:1",
                            "resource_type": "fixture.Resource",
                            "requires_close": True,
                            "holder_kind": "none",
                            "holder_scope": "none",
                            "holder_key": "none",
                            "target_event": "none",
                            "capacity": "unknown",
                            "normal_path": True,
                            "exceptional_path": True,
                            "source_evidence": "recorded_static_fact",
                            "coverage_status": "complete",
                            "coverage_note": "offline import fixture",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "mode": "static_verified_json",
                        "rows": "rows.json",
                        "source_root": "source",
                        "query_sha256": "a" * 64,
                        "entry_methods": ["java-callable-v1:fixture.Imported.handle()V"],
                        "budget": {"max_steps": 64, "max_updates_per_event": 8, "timeout_ms": 1000},
                    }
                ),
                encoding="utf-8",
            )
            output = root / "facts"

            self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(output)]))
            payload = json.loads((output / "facts.json").read_text(encoding="utf-8"))

        self.assertEqual("static_verified", payload["source_kind"])
        self.assertEqual("imported_static_facts", payload["coverage"]["end_to_end_mode"])
        self.assertTrue(all(fact["location"]["source_kind"] == "static_verified" for fact in payload["facts"]))

    def test_extract_rejects_symlink_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            link = root / "manifest-link.json"
            link.symlink_to(manifest)

            status = main(["resource-extract", "--manifest", str(link), "--out", str(root / "facts")])

        self.assertEqual(5, status)

    def test_static_import_rejects_parent_traversal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested"
            nested.mkdir()
            (root / "rows.json").write_text("[]", encoding="utf-8")
            (root / "source").mkdir()
            manifest = nested / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "mode": "static_verified_json",
                        "rows": "../rows.json",
                        "source_root": "../source",
                        "query_sha256": "a" * 64,
                        "budget": {"max_steps": 64, "max_updates_per_event": 8, "timeout_ms": 1000},
                    }
                ),
                encoding="utf-8",
            )

            status = main(["resource-extract", "--manifest", str(manifest), "--out", str(root / "facts")])

        self.assertEqual(5, status)


if __name__ == "__main__":
    unittest.main()
