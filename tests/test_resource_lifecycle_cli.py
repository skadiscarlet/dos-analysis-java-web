from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest

from dosweb.cli import main, parse_cli_values
from dosweb.resource_lifecycle import io as lifecycle_io
from dosweb.resource_lifecycle import models as lifecycle_models
from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.io import program_from_dict, program_to_dict
from dosweb.resource_lifecycle.adapters import (
    AnalysisUnit,
    ExtractedFacts,
    adapt_codeql_rows,
    extracted_from_dict,
    extracted_to_dict,
    validate_extracted,
)
from dosweb.resource_lifecycle.commands import (
    _analyze_payload,
    _evidence_payload,
    _manual_facts,
)
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
    @staticmethod
    def _population_effect(
        kind: str, *, suffix: str = ""
    ) -> lifecycle_models.PopulationEffect:
        guard, queue_delta, active_delta, source_phase, target_phase = {
            "direct_accept": ("worker_available", 0, 1, "absent", "reserved"),
            "enqueue": ("q < K", 1, 0, "absent", "queued"),
            "assign_slot": ("worker_available", -1, 1, "queued", "reserved"),
            "start": ("scheduled", 0, 0, "reserved", "running"),
            "terminate": ("normal", 0, -1, "running", "terminated"),
            "reject": ("rejected", 0, 0, "absent", "rejected"),
            "cancel_queued": ("cancelled", -1, 0, "queued", "cancelled"),
            "cancel_active": ("cancelled", 0, -1, "running", "cancelled"),
        }[kind]
        return lifecycle_models.PopulationEffect(
            f"population:{kind}{suffix}",
            kind,
            "contract:executor",
            "task:stream",
            guard,
            queue_delta,
            active_delta,
            source_phase,
            target_phase,
            effect("create").location,
            (f"fact:{kind}{suffix}",),
        )

    @staticmethod
    def _schema_1_0_program_payload() -> dict[str, object]:
        current = replace(
            program_for(()),
            transitions=(
                Transition(
                    "transition:legacy",
                    "event:entry",
                    "event:normal",
                    "true",
                    (),
                    "normal",
                    (),
                ),
            ),
        )
        payload = json.loads(json.dumps(program_to_dict(current), sort_keys=True))
        payload["schema_version"] = "1.0"
        for name in (
            "program_points",
            "call_bindings",
            "task_bindings",
            "task_exits",
        ):
            payload.pop(name)
        payload["transitions"][0].pop("population_effects")
        return payload

    @staticmethod
    def _manual_relation_contract() -> ExecutorContract:
        return ExecutorContract(
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

    def _schema_1_1_relation_program(self) -> Program:
        TaskExit = getattr(lifecycle_models, "TaskExit")
        base = program_for(())
        task_events = (
            Event("event:submit", "task_submit", "Fixture.handle", "submitted"),
            Event("event:queue", "task_queue", "Fixture.task", "accepted"),
            Event("event:run", "task_run", "Fixture.task", "worker reserved"),
            Event("event:task-normal", "task_exit", "Fixture.task", "normal"),
            Event("event:task-error", "task_exit", "Fixture.task", "exceptional"),
            Event("event:task-rejected", "task_reject", "Fixture.task", "rejected"),
            Event("event:task-cancelled", "task_cancel", "Fixture.task", "cancelled"),
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
            binding_id="task-binding:stream",
            task_id="task:stream",
            instance_id="instance:stream",
            holder_id="holder:task",
            executor_contract_id="contract:executor",
            submit_event_id="event:submit",
            queued_event_id="event:queue",
            run_event_id="event:run",
            normal_exit_event_id="event:task-normal",
            exceptional_exit_event_id="event:task-error",
            rejected_event_id="event:task-rejected",
            cancelled_event_id="event:task-cancelled",
            task_callable="Fixture.task",
            evidence_ids=("fact:capture",),
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
                    "event:submit",
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
        self.assertEqual(
            {
                "binding_id",
                "task_id",
                "instance_id",
                "holder_id",
                "executor_contract_id",
                "submit_event_id",
                "queued_event_id",
                "run_event_id",
                "normal_exit_event_id",
                "exceptional_exit_event_id",
                "rejected_event_id",
                "cancelled_event_id",
                "task_callable",
                "evidence_ids",
            },
            set(program_to_dict(rebuilt)["task_bindings"][0]),
        )

    def test_manual_manifest_rejects_nonmanual_relation_locations(self) -> None:
        for relation, source_kind in (
            ("program_point", "static_verified"),
            ("program_point", "llm_proposed"),
            ("population_effect", "static_verified"),
            ("population_effect", "llm_proposed"),
        ):
            with self.subTest(relation=relation, source_kind=source_kind):
                program = json.loads(
                    json.dumps(
                        program_to_dict(self._schema_1_1_relation_program()),
                        sort_keys=True,
                    )
                )
                if relation == "program_point":
                    location = program["program_points"][0]["location"]
                else:
                    location = program["transitions"][0]["population_effects"][0][
                        "location"
                    ]
                location["source_kind"] = source_kind
                manifest = {
                    "schema_version": "1.1",
                    "mode": "manual_fixture",
                    "programs": [
                        {
                            "unit_id": "manual:relations",
                            "program": program,
                            "invariants": [],
                            "executor_contracts": [
                                asdict(self._manual_relation_contract())
                            ],
                        }
                    ],
                    "budget": {
                        "max_steps": 64,
                        "max_updates_per_event": 8,
                        "timeout_ms": 1000,
                    },
                }
                with tempfile.TemporaryDirectory() as tmp:
                    manifest_path = Path(tmp) / "manifest.json"
                    manifest_path.write_text(
                        json.dumps(manifest, sort_keys=True), encoding="utf-8"
                    )
                    with self.assertRaises(ValueError):
                        _manual_facts(manifest, manifest_path)

    def test_manual_artifact_validation_rejects_nonmanual_relation_locations(
        self,
    ) -> None:
        for relation, source_kind in (
            ("program_point", "static_verified"),
            ("program_point", "llm_proposed"),
            ("population_effect", "static_verified"),
            ("population_effect", "llm_proposed"),
        ):
            with self.subTest(relation=relation, source_kind=source_kind):
                program = self._schema_1_1_relation_program()
                if relation == "program_point":
                    location = program.program_points[0].location
                else:
                    location = program.transitions[0].population_effects[0].location
                object.__setattr__(location, "source_kind", source_kind)
                extracted = ExtractedFacts(
                    "manual_fixture",
                    "a" * 64,
                    "manual-fixture-import-v1",
                    AnalysisBudget(),
                    (
                        AnalysisUnit(
                            "manual:relations",
                            program,
                            (),
                            (self._manual_relation_contract(),),
                        ),
                    ),
                    (),
                    {"end_to_end_mode": "manual_ir"},
                )

                with self.assertRaisesRegex(
                    ValueError, "manual fixture (program point|population effect) source"
                ):
                    validate_extracted(extracted)

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

    def test_schema_1_1_binds_task_events_to_the_task_callable(self) -> None:
        valid = self._schema_1_1_relation_program()
        binding = valid.task_bindings[0]

        for event_id in (
            binding.queued_event_id,
            binding.run_event_id,
            binding.normal_exit_event_id,
            binding.exceptional_exit_event_id,
            binding.rejected_event_id,
            binding.cancelled_event_id,
        ):
            events = tuple(
                replace(event, callable="Fixture.otherTask")
                if event.event_id == event_id
                else event
                for event in valid.events
            )
            with self.subTest(event_id=event_id), self.assertRaisesRegex(
                ValueError, "task binding event callable"
            ):
                replace(valid, events=events)

    def test_schema_1_1_binds_all_task_stage_kinds(self) -> None:
        valid = self._schema_1_1_relation_program()
        binding = valid.task_bindings[0]
        expected = {
            binding.submit_event_id: "task_submit",
            binding.queued_event_id: "task_queue",
            binding.run_event_id: "task_run",
            binding.normal_exit_event_id: "task_exit",
            binding.exceptional_exit_event_id: "task_exit",
            binding.rejected_event_id: "task_reject",
            binding.cancelled_event_id: "task_cancel",
        }

        for event_id in expected:
            events = tuple(
                replace(event, kind="method") if event.event_id == event_id else event
                for event in valid.events
            )
            with self.subTest(event_id=event_id), self.assertRaisesRegex(
                ValueError, "task binding event kind"
            ):
                replace(valid, events=events)

    def test_schema_1_1_accepts_all_exact_population_attachments(self) -> None:
        valid = self._schema_1_1_relation_program()
        cases = {
            "direct_accept": ("event:submit", "event:run", "internal"),
            "enqueue": ("event:submit", "event:queue", "internal"),
            "assign_slot": ("event:queue", "event:run", "internal"),
            "start": ("event:run", "event:run", "internal"),
            "terminate": ("event:run", "event:task-normal", "normal"),
            "reject": ("event:submit", "event:task-rejected", "rejected"),
            "cancel_queued": ("event:queue", "event:task-cancelled", "cancelled"),
            "cancel_active": ("event:run", "event:task-cancelled", "cancelled"),
        }

        for kind, (source, target, exit_kind) in cases.items():
            transition = Transition(
                f"transition:{kind}",
                source,
                target,
                "true",
                (),
                exit_kind,
                (),
                (self._population_effect(kind),),
            )
            with self.subTest(kind=kind):
                self.assertEqual((transition,), replace(valid, transitions=(transition,)).transitions)

    def test_schema_1_1_rejects_any_inexact_population_attachment(self) -> None:
        valid = self._schema_1_1_relation_program()
        expected = {
            "direct_accept": ("event:submit", "event:run", "internal"),
            "enqueue": ("event:submit", "event:queue", "internal"),
            "assign_slot": ("event:queue", "event:run", "internal"),
            "start": ("event:run", "event:run", "internal"),
            "terminate": ("event:run", "event:task-normal", "normal"),
            "reject": ("event:submit", "event:task-rejected", "rejected"),
            "cancel_queued": ("event:queue", "event:task-cancelled", "cancelled"),
            "cancel_active": ("event:run", "event:task-cancelled", "cancelled"),
        }

        for kind, (source, target, exit_kind) in expected.items():
            wrong_source = "event:queue" if source != "event:queue" else "event:submit"
            wrong_target = "event:queue" if target != "event:queue" else "event:run"
            wrong_exit_kind = "normal" if exit_kind == "internal" else "internal"
            for dimension, candidate in (
                ("source", (wrong_source, target, exit_kind)),
                ("target", (source, wrong_target, exit_kind)),
                ("exit_kind", (source, target, wrong_exit_kind)),
            ):
                candidate_source, candidate_target, candidate_exit_kind = candidate
                transition = Transition(
                    f"transition:{kind}:{dimension}",
                    candidate_source,
                    candidate_target,
                    "true",
                    (),
                    candidate_exit_kind,
                    (),
                    (self._population_effect(kind, suffix=f":{dimension}"),),
                )
                with self.subTest(kind=kind, dimension=dimension), self.assertRaisesRegex(
                    ValueError, "population effect transition"
                ):
                    replace(valid, transitions=(transition,))

    def test_schema_1_1_allows_callback_internal_cfg_sources_for_active_exit(self) -> None:
        valid = self._schema_1_1_relation_program()
        body = Event("event:task-body", "method", "Fixture.task", "callback body")
        cfg = Transition(
            "transition:callback-body",
            "event:run",
            body.event_id,
            "true",
            (),
            "internal",
            (),
        )
        terminate = Transition(
            "transition:callback-normal",
            body.event_id,
            "event:task-normal",
            "true",
            (),
            "normal",
            (),
            (self._population_effect("terminate", suffix=":callback"),),
        )

        rebuilt = replace(
            valid,
            events=valid.events + (body,),
            transitions=(cfg, terminate),
        )

        self.assertEqual((cfg, terminate), rebuilt.transitions)

    def test_schema_1_1_rejects_disconnected_or_wrong_callable_callback_sources(self) -> None:
        valid = self._schema_1_1_relation_program()
        for label, callable_name, connect in (
            ("disconnected", "Fixture.task", False),
            ("wrong-callable", "Fixture.otherTask", True),
        ):
            body = Event(f"event:task-body:{label}", "method", callable_name, "callback body")
            transitions = []
            if connect:
                transitions.append(
                    Transition(
                        f"transition:callback-body:{label}",
                        "event:run",
                        body.event_id,
                        "true",
                        (),
                        "internal",
                        (),
                    )
                )
            transitions.append(
                Transition(
                    f"transition:callback-normal:{label}",
                    body.event_id,
                    "event:task-normal",
                    "true",
                    (),
                    "normal",
                    (),
                    (self._population_effect("terminate", suffix=f":{label}"),),
                )
            )
            with self.subTest(label=label), self.assertRaisesRegex(
                ValueError, "population effect transition"
            ):
                replace(valid, events=valid.events + (body,), transitions=tuple(transitions))

    def test_schema_1_1_rejects_task_stage_event_reuse_across_bindings(self) -> None:
        valid = self._schema_1_1_relation_program()
        original = valid.task_bindings[0]
        duplicate = replace(
            original,
            binding_id="task-binding:duplicate",
            task_id="task:duplicate",
            evidence_ids=("fact:capture:duplicate",),
        )
        duplicate_exits = tuple(
            replace(
                task_exit,
                exit_id=f"{task_exit.exit_id}:duplicate",
                task_id=duplicate.task_id,
                evidence_ids=(f"{task_exit.evidence_ids[0]}:duplicate",),
            )
            for task_exit in valid.task_exits
        )

        with self.assertRaisesRegex(ValueError, "task binding stage event ownership"):
            replace(
                valid,
                task_bindings=(original, duplicate),
                task_exits=valid.task_exits + duplicate_exits,
            )

    def test_versioned_program_and_transition_fields_are_explicit(self) -> None:
        legacy_program_fields = {
            "schema_version",
            "families",
            "instances",
            "holders",
            "events",
            "transitions",
            "entry_event_ids",
            "exit_event_ids",
            "coverage_complete",
            "contracts_version",
            "coverage_gaps",
        }
        legacy_transition_fields = {
            "transition_id",
            "source_event_id",
            "target_event_id",
            "guard",
            "effects",
            "exit_kind",
            "assumptions",
        }
        self.assertEqual(frozenset(legacy_program_fields), lifecycle_io._V1_0_PROGRAM_FIELDS)
        self.assertEqual(
            frozenset(
                legacy_program_fields
                | {"program_points", "call_bindings", "task_bindings", "task_exits"}
            ),
            lifecycle_io._V1_1_PROGRAM_FIELDS,
        )
        self.assertEqual(
            frozenset(legacy_transition_fields), lifecycle_io._V1_0_TRANSITION_FIELDS
        )
        self.assertEqual(
            frozenset(legacy_transition_fields | {"population_effects"}),
            lifecycle_io._V1_1_TRANSITION_FIELDS,
        )

    def test_schema_1_1_relation_identifiers_are_unique_across_relation_kinds(self) -> None:
        valid = self._schema_1_1_relation_program()
        cross_kind_collision = lifecycle_models.CallBinding(
            valid.task_bindings[0].binding_id,
            "point:call",
            "point:callee",
            "Fixture.handle",
            "Fixture.wrapper",
            0,
            0,
            "instance:stream",
            1,
            ("fact:call-binding",),
        )

        with self.assertRaisesRegex(ValueError, "duplicate relation identifier"):
            replace(valid, call_bindings=(cross_kind_collision,))

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
            core_workers=1,
            max_workers=2,
            rejection_policy="abort",
            termination="drops_capture",
        )

        self.assertEqual(1, contract.core_workers)
        self.assertEqual(2, contract.max_workers)
        self.assertEqual("abort", contract.rejection_policy)
        self.assertEqual("drops_capture", contract.termination)
        with self.assertRaisesRegex(ValueError, "capacity"):
            replace(contract, queue_capacity=-1)
        with self.assertRaisesRegex(ValueError, "worker"):
            replace(contract, max_workers=-1)
        with self.assertRaisesRegex(ValueError, "core worker"):
            replace(contract, core_workers=-1)
        with self.assertRaisesRegex(ValueError, "core worker.*maximum worker"):
            replace(contract, core_workers=3)
        with self.assertRaisesRegex(ValueError, "termination"):
            replace(contract, termination="guessed")

    def test_executor_contract_numeric_strings_follow_numeric_limit_rules(self) -> None:
        contract = ExecutorContract(
            "contract:executor",
            "queued",
            3,
            True,
            True,
            True,
            "drops_capture",
            "manual_fixture",
            "executor-contract-v1",
            2,
            "abort",
            "drops_capture",
        )
        for field, invalid, message in (
            ("queue_capacity", "0", "capacity"),
            ("queue_capacity", "-1", "capacity"),
            ("max_workers", "0", "worker"),
            ("max_workers", "-1", "worker"),
            ("core_workers", "-1", "core worker"),
            ("core_workers", "3", "core worker"),
            ("queue_capacity", True, "capacity"),
            ("max_workers", True, "worker"),
            ("core_workers", True, "core worker"),
        ):
            with self.subTest(field=field, invalid=invalid), self.assertRaisesRegex(
                ValueError, message
            ):
                replace(contract, **{field: invalid})
        self.assertEqual(
            "configuredCapacity",
            replace(contract, queue_capacity="configuredCapacity").queue_capacity,
        )
        self.assertEqual(
            "configuredWorkers",
            replace(contract, max_workers="configuredWorkers").max_workers,
        )
        self.assertEqual(
            "configuredCoreWorkers",
            replace(contract, core_workers="configuredCoreWorkers").core_workers,
        )
        self.assertEqual(0, replace(contract, core_workers=0).core_workers)
        self.assertEqual("0", replace(contract, core_workers="0").core_workers)

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

    def test_schema_1_0_program_accepts_only_the_exact_legacy_field_set(self) -> None:
        legacy = self._schema_1_0_program_payload()

        rebuilt = program_from_dict(legacy)

        self.assertEqual("1.1", rebuilt.schema_version)
        self.assertEqual((), rebuilt.coverage_gaps)
        self.assertEqual((), rebuilt.program_points)
        self.assertEqual((), rebuilt.call_bindings)
        self.assertEqual((), rebuilt.task_bindings)
        self.assertEqual((), rebuilt.task_exits)
        self.assertEqual((), rebuilt.transitions[0].population_effects)
        missing_coverage = json.loads(json.dumps(legacy, sort_keys=True))
        missing_coverage.pop("coverage_gaps")
        with self.assertRaisesRegex(ValueError, "schema 1.0 program fields"):
            program_from_dict(missing_coverage)
        for field in (
            "program_points",
            "call_bindings",
            "task_bindings",
            "task_exits",
        ):
            invalid = json.loads(json.dumps(legacy, sort_keys=True))
            invalid[field] = []
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "schema 1.0 program fields"
            ):
                program_from_dict(invalid)

    def test_schema_1_0_transition_rejects_empty_population_effects_field(self) -> None:
        legacy = self._schema_1_0_program_payload()
        legacy["transitions"][0]["population_effects"] = []

        with self.assertRaisesRegex(ValueError, "schema 1.0 transition fields"):
            program_from_dict(legacy)

    def test_schema_1_1_program_requires_every_v1_1_field(self) -> None:
        program = replace(
            program_for(()),
            transitions=(
                Transition(
                    "transition:empty-population",
                    "event:entry",
                    "event:normal",
                    "true",
                    (),
                    "normal",
                    (),
                ),
            ),
        )
        payload = json.loads(json.dumps(program_to_dict(program)))
        cases = (
            ("coverage_gaps", lambda value: value.pop("coverage_gaps")),
            ("program_points", lambda value: value.pop("program_points")),
            ("call_bindings", lambda value: value.pop("call_bindings")),
            ("task_bindings", lambda value: value.pop("task_bindings")),
            ("task_exits", lambda value: value.pop("task_exits")),
            (
                "population_effects",
                lambda value: value["transitions"][0].pop("population_effects"),
            ),
        )

        for field, remove in cases:
            invalid = json.loads(json.dumps(payload))
            remove(invalid)
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "schema 1.1"
            ):
                program_from_dict(invalid)

    def test_schema_1_1_facts_rejects_nested_schema_1_0_program(self) -> None:
        extracted = ExtractedFacts(
            "manual_fixture",
            "a" * 64,
            "manual-fixture-import-v1",
            AnalysisBudget(),
            (AnalysisUnit("manual:legacy-nested", program_for(()), ()),),
            (),
            {
                "units": 1,
                "facts": 0,
                "partial_or_unsupported": 0,
                "end_to_end_mode": "manual_ir",
            },
        )
        payload = json.loads(json.dumps(extracted_to_dict(extracted)))
        nested = payload["units"][0]["program"]
        nested["schema_version"] = "1.0"
        for field in (
            "program_points",
            "call_bindings",
            "task_bindings",
            "task_exits",
        ):
            nested.pop(field)

        with self.assertRaisesRegex(ValueError, "nested schema"):
            extracted_from_dict(payload)

    def test_schema_1_0_facts_rejects_nested_v1_1_relations(self) -> None:
        program = self._schema_1_1_relation_program()
        contract = ExecutorContract(
            "contract:executor",
            "queued",
            3,
            True,
            True,
            True,
            "drops_capture",
            "manual_fixture",
            "executor-contract-v1",
            2,
            "abort",
            "drops_capture",
        )
        extracted = ExtractedFacts(
            "manual_fixture",
            "a" * 64,
            "manual-fixture-import-v1",
            AnalysisBudget(),
            (AnalysisUnit("manual:relations", program, (), (contract,)),),
            (),
            {
                "units": 1,
                "facts": 0,
                "partial_or_unsupported": 0,
                "end_to_end_mode": "manual_ir",
            },
        )
        payload = json.loads(json.dumps(extracted_to_dict(extracted)))
        payload["schema_version"] = "1.0"

        with self.assertRaisesRegex(ValueError, "legacy facts schema"):
            extracted_from_dict(payload)

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
            rejection_policy="abort",
            termination="drops_capture",
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

    def test_manual_dispatch_without_task_binding_only_emits_solved_capture(self) -> None:
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
        self.assertEqual("event:normal", stage["target_event_id"])
        self.assertEqual("event:task", stage["dispatch_target_event_id"])
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
        for phase in ("submitted",):
            self.assertEqual(expected_state_fields, set(stage[phase]))
            self.assertIn("instance:stream", stage[phase]["open_obligations"])
        task_edge = ["instance:stream", "holder:task"]
        self.assertIn(task_edge, stage["submitted"]["held_edges"])
        for phase in ("started", "completed", "rejected", "cancelled"):
            self.assertIsNone(stage[phase])
        self.assertFalse(stage["termination_guaranteed"])
        self.assertIn("task_binding_unavailable:effect:dispatch:task", stage["submitted"]["unknown_reasons"])
        self.assertNotIn("task_completion_drops_capture", stage["rule_ids"])
        self.assertIn("create_instance", stage["rule_ids"])
        self.assertIn("retain_holder_edge", stage["rule_ids"])
        self.assertEqual(
            {
                ("create_instance", "fact:create"),
                ("retain_holder_edge", "fact:retain"),
                ("dispatch_capture_on_contract", "fact:dispatch"),
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
                self.assertIn(task_edge, stage["submitted"]["held_edges"])
                self.assertIn("task_binding_unavailable:effect:dispatch:task", stage["submitted"]["unknown_reasons"])
                for phase in ("started", "completed", "rejected", "cancelled"):
                    self.assertIsNone(stage[phase])

    def test_explicit_trusted_contract_cannot_replace_a_task_binding_and_exit(self) -> None:
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
        self.assertIsNone(stage["completed"])
        self.assertIsNone(stage["cancelled"])
        self.assertIn(task_edge, stage["submitted"]["held_edges"])
        self.assertIn("instance:stream", stage["submitted"]["open_obligations"])
        self.assertIn("task_binding_unavailable:effect:dispatch:task", results["units"][0]["unknown_reasons"])

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
