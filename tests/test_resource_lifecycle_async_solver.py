from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from dosweb.resource_lifecycle.models import (
    AnalysisBudget, Event, Holder, PopulationEffect, ProgramPoint, TaskBinding,
    TaskExit, Transition,
)
from dosweb.resource_lifecycle.solver import solve
from dosweb.resource_lifecycle.invariants import check_invariants
from tests.test_resource_lifecycle_solver import effect, location, program_for


def task_program(*, close_normal=True, close_exceptional=True, field=False,
                 terminal=True, reject=True, count=1):
    """Manual relation fixture; no source extraction claim or executor liveness axiom."""
    base = program_for(())
    events = [Event("caller:submit", "method", "Fixture.handle", "true")]
    holders = []
    bindings = []
    points = []
    exits = []
    transitions = [Transition("allocate", "event:entry", "caller:submit", "true",
        (effect("create"), effect("retain", holder_id="holder:request"))
        + ((effect("retain", holder_id="holder:field"),) if field else ()), "internal", ())]
    for index in range(count):
        prefix = f"task:{index}"
        caller = "caller:submit" if index == 0 else f"caller:submit:{index}"
        continuation = f"caller:submit:{index + 1}" if index + 1 < count else "event:normal"
        if index:
            events.append(Event(caller, "method", "Fixture.handle", "true"))
        ids = [f"{prefix}:{stage}" for stage in ("submit", "queue", "run", "normal", "exceptional", "rejected", "cancelled")]
        events.extend(Event(event_id, kind, "Fixture.handle" if kind == "task_submit" else "Fixture.task", "true") for event_id, kind in zip(ids,
            ("task_submit", "task_queue", "task_run", "task_exit", "task_exit", "task_reject", "task_cancel")))
        events.append(Event(prefix + ":body", "method", "Fixture.task", "true"))
        holders.append(Holder(prefix + ":holder", "task", "task", "exact"))
        binding = TaskBinding(prefix + ":binding", prefix, "instance:stream", prefix + ":holder",
            "executor", *ids, "Fixture.task", (prefix + ":fact:binding",))
        bindings.append(binding)
        transitions.append(Transition(prefix + ":bind", caller, ids[0], "source_submit_binding", (), "internal", ()))
        transitions.append(Transition(prefix + ":return", caller, continuation, "task_submit_success",
            (effect("drop", holder_id="holder:request"),) if continuation == "event:normal" else (),
            "normal" if continuation == "event:normal" else "internal",
            (f"task_binding:{binding.binding_id}", f"cfg_fact:{prefix}:caller-success")))
        for name, source, target, phase_source, phase_target, q, a, exit_kind in (
            ("direct_accept", ids[0], ids[2], "absent", "reserved", 0, 1, "internal"),
            ("enqueue", ids[0], ids[1], "absent", "queued", 1, 0, "internal"),
            ("assign_slot", ids[1], ids[2], "queued", "reserved", -1, 1, "internal"),
            ("start", ids[2], ids[2], "reserved", "running", 0, 0, "internal"),
            *(([("reject", ids[0], ids[5], "absent", "rejected", 0, 0, "rejected")]) if reject else []),
        ):
            pop = PopulationEffect(prefix + ":" + name, name, "executor", prefix, "contract guard", q, a,
                phase_source, phase_target, location(), (prefix + ":fact:population:" + name,))
            transitions.append(Transition(prefix + ":edge:" + name, source, target, name, (), exit_kind, (), (pop,)))
        transitions.append(Transition(prefix + ":body-edge", ids[2], prefix + ":body", "true", (), "internal", ()))
        for kind, closed in (("normal", close_normal), ("exceptional", close_exceptional)):
            point = prefix + ":point:" + kind
            target = ids[3 if kind == "normal" else 4]
            points.append(ProgramPoint(point, "Fixture.task", "task_exit", location()))
            exits.append(TaskExit(prefix + ":exit:" + kind, prefix, point, target, "Fixture.task", kind,
                                  (prefix + ":fact:exit:" + kind,)))
            if terminal:
                transitions.append(Transition(prefix + ":terminal:" + kind, prefix + ":body", target, kind,
                    (replace(effect("release"), effect_id=prefix + ":close:" + kind),) if closed else (), kind, ()))
    return replace(base, events=base.events + tuple(events), holders=base.holders + tuple(holders),
        transitions=tuple(transitions), exit_event_ids=("event:normal",),
        task_bindings=tuple(bindings), task_exits=tuple(exits), program_points=tuple(points))


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
def test_task_terminal_changes_main_solver_state(kind):
    result = solve(task_program(), budget=AnalysisBudget(max_steps=10000))
    state = result.property_states["after_task_termination"][f"task:0:{kind}"]
    assert not state.open_obligations
    assert ("instance:stream", "task:0:holder") not in state.held_edges
    assert "release_exact_obligation" in result.traces[f"task:0:{kind}"].rule_ids
    assert result.property_states["after_task_termination"]
    assert result.termination_guaranteed is False
    assert "task_termination_not_guaranteed:task:0" in result.unknown_reasons


def test_missing_terminal_does_not_discharge_or_invent_completed_slice():
    result = solve(task_program(terminal=False), budget=AnalysisBudget())
    assert "task:0:normal" not in result.property_states["after_task_termination"]
    assert not result.property_states["after_task_termination"]
    assert ("instance:stream", "task:0:holder") in result.event_states["task:0:body"].held_edges


def test_callback_close_and_extra_field_change_solved_termination_dimensions():
    closed = solve(task_program(), budget=AnalysisBudget(max_steps=10000))
    missing = solve(task_program(close_exceptional=False), budget=AnalysisBudget(max_steps=10000))
    escaped = solve(task_program(field=True), budget=AnalysisBudget(max_steps=10000))
    assert closed.property_states["after_task_termination"]["task:0:exceptional"].obligation_counts != missing.property_states["after_task_termination"]["task:0:exceptional"].obligation_counts
    assert not closed.property_states["all_tasks_terminated_after_request"]["event:normal"].held_edges
    assert ("instance:stream", "holder:field") in escaped.property_states["all_tasks_terminated_after_request"]["event:normal"].held_edges


def test_accept_start_request_return_and_reject_have_distinct_holder_states():
    result = solve(task_program(), budget=AnalysisBudget(max_steps=10000))
    task_edge = ("instance:stream", "task:0:holder")
    assert task_edge in result.event_states["task:0:queue"].held_edges
    assert task_edge in result.event_states["task:0:run"].held_edges
    assert task_edge in result.event_states["event:normal"].held_edges
    assert ("instance:stream", "holder:request") not in result.event_states["event:normal"].held_edges
    assert task_edge not in result.property_states["after_task_rejection"]["task:0:rejected"].held_edges
    assert result.property_states["after_task_rejection"]["task:0:rejected"].open_obligations
    without_reject = solve(task_program(reject=False), budget=AnalysisBudget(max_steps=10000))
    assert "task:0:rejected" not in without_reject.property_states["after_task_rejection"]


def test_repeated_submit_contexts_keep_separate_holders_and_exit_states():
    result = solve(task_program(count=2), budget=AnalysisBudget(max_steps=20000))
    assert result.terminated
    for index in range(2):
        assert ("instance:stream", f"task:{index}:holder") not in result.property_states["after_task_termination"][f"task:{index}:normal"].held_edges
    assert ("instance:stream", "task:1:holder") in result.property_states["after_task_termination"]["task:0:normal"].held_edges
    assert not result.property_states["all_tasks_terminated_after_request"]["event:normal"].held_edges


def dimensions(program):
    result = solve(program, budget=AnalysisBudget(max_steps=10000))
    return {(item.scope, item.dimension, item.resource_family_id): item for item in
            check_invariants(program, result, (), timeout_ms=1000)}


def test_conditional_dimensions_change_but_inflight_request_is_unknown():
    closed = dimensions(task_program())
    missing = dimensions(task_program(close_exceptional=False))
    field = dimensions(task_program(field=True))
    scope = "after_task_termination:task:0:exceptional"
    assert closed[scope, "close_obligation", "family:stream"].lifecycle_status == "bounded"
    assert missing[scope, "close_obligation", "family:stream"].lifecycle_status == "obligation_gap"
    scope = "all_tasks_terminated_after_request"
    assert closed[scope, "held_instances", "family:stream"].upper_bound == 0
    assert field[scope, "held_instances", "family:stream"].lifecycle_status == "unknown"
    assert closed["all_exits", "close_obligation", "family:stream"].lifecycle_status == "unknown"
    assert "task_termination_not_guaranteed:task:0" in closed["all_exits", "close_obligation", "family:stream"].reason_codes


@pytest.mark.parametrize("reason", ["task_callback_effect_unmodeled", "nested_task_unsupported", "configuration_unknown"])
def test_source_coverage_gap_remains_unknown_even_on_reached_terminal(reason):
    program = replace(task_program(), coverage_complete=False, coverage_gaps=(
        ("close_obligation", "family:stream", "*", reason, "fact:gap"),))
    row = dimensions(program)["after_task_termination:task:0:normal", "close_obligation", "family:stream"]
    assert row.lifecycle_status == "unknown"
    assert reason in row.reason_codes
    assert "fact:gap" in row.evidence_ids


def test_unrelated_sync_resource_does_not_inherit_task_temporal_unknown():
    program = task_program()
    sync_instance = replace(program.instances[0], instance_id="instance:sync", family_id="family:sync")
    sync_family = replace(program.families[0], family_id="family:sync")
    sync_create = replace(effect("create"), instance_id=sync_instance.instance_id,
                          family_id=sync_family.family_id, effect_id="sync:create")
    sync_close = replace(effect("release"), instance_id=sync_instance.instance_id,
                         family_id=sync_family.family_id, effect_id="sync:close")
    program = replace(program, families=program.families + (sync_family,),
        instances=program.instances + (sync_instance,), transitions=tuple(
            replace(edge, effects=edge.effects + (sync_create, sync_close)) if edge.transition_id == "allocate" else edge
            for edge in program.transitions))
    row = dimensions(program)["all_exits", "close_obligation", "family:sync"]
    assert row.lifecycle_status == "bounded"
    assert not row.reason_codes


def test_low_budget_never_fabricates_termination_or_a_global_bound():
    program = task_program()
    result = solve(program, budget=AnalysisBudget(max_steps=2))
    assert not result.terminated
    assert "analysis_budget_exhausted" in result.unknown_reasons
    assert not result.property_states["after_task_termination"]
    assert not result.property_states["all_tasks_terminated_after_request"]
    assert all(item.lifecycle_status == "unknown" for item in check_invariants(program, result, (), timeout_ms=100))


def test_connector_effects_are_applied_and_start_snapshot_precedes_callback_close():
    program = task_program()
    program = replace(program, transitions=tuple(
        replace(edge, effects=(effect("retain", holder_id="holder:field"),))
        if edge.transition_id == "task:0:bind" else edge for edge in program.transitions))
    result = solve(program, budget=AnalysisBudget())
    assert ("instance:stream", "holder:field") in result.async_states["task:0"]["normal"].held_edges
    assert result.async_states["task:0"]["running"].open_obligations
    assert not result.async_states["task:0"]["normal"].open_obligations
    assert not hasattr(result.async_states["task:0"]["running"], "task_phases")
    assert all("task_population_transition:start" in trace.rule_ids
               for trace in result.async_traces["task:0"]["running"])


def test_explicit_queued_cancellation_is_solved_without_closing_resource():
    program = task_program()
    binding = program.task_bindings[0]
    pop = PopulationEffect("cancel:population", "cancel_queued", "executor", binding.task_id,
        "queued removal", -1, 0, "queued", "cancelled", location(), ("fact:cancel",))
    cancellation = Transition("cancel:edge", binding.queued_event_id, binding.cancelled_event_id,
                              "queued removal", (), "cancelled", (), (pop,))
    program = replace(program, transitions=tuple(edge for edge in program.transitions if not
        any(item.kind in {"direct_accept", "assign_slot", "reject"} for item in edge.population_effects)) + (cancellation,))
    result = solve(program, budget=AnalysisBudget())
    state = result.property_states["after_task_cancellation"][binding.cancelled_event_id]
    assert (binding.instance_id, binding.holder_id) not in state.held_edges
    assert binding.instance_id in state.open_obligations
    assert "task_cancellation_unmodeled:task:0" not in result.unknown_reasons


def test_async_report_uses_solved_states_without_executing_effects(monkeypatch):
    from dosweb.resource_lifecycle.adapters import AnalysisUnit
    from dosweb.resource_lifecycle.commands import _async_stages
    from dosweb.resource_lifecycle import solver, events
    from tests.test_resource_lifecycle_events import contract
    program = task_program()
    solved = solve(program, budget=AnalysisBudget())
    def fail(*args, **kwargs):
        raise AssertionError("report must not execute resource semantics")
    monkeypatch.setattr(solver, "apply_effect", fail)
    monkeypatch.setattr(events, "expand_dispatch", fail)
    executor = replace(contract(), contract_id="executor")
    stage = _async_stages(AnalysisUnit("manual:task4", program, (), (executor,)), solved)[0]
    assert stage["completed"]["open_obligations"] == []
    assert "task_phases" not in stage["normal"]
    assert all(record["phase"] == "normal" for record in stage["phase_derivations"]["normal"])
    assert stage["property_slice"] == "after_task_termination"
    assert stage["termination_guaranteed"] is False


@pytest.mark.parametrize("variant", ["missing", "duplicate", "wrong_guard", "wrong_exit_kind", "wrong_callable"])
def test_unproven_or_ambiguous_source_connector_fails_closed(variant):
    program = task_program()
    binding = program.task_bindings[0]
    connector = next(edge for edge in program.transitions if edge.target_event_id == binding.submit_event_id)
    if variant == "missing":
        program = replace(program, transitions=tuple(edge for edge in program.transitions if edge != connector))
    elif variant == "duplicate":
        program = replace(program, transitions=program.transitions + (replace(connector, transition_id="duplicate:connector"),))
    elif variant == "wrong_callable":
        program = replace(program, events=tuple(replace(event, callable="Wrong.caller")
            if event.event_id == connector.source_event_id else event for event in program.events))
    else:
        changed = replace(connector, **({"guard": "guessed"} if variant == "wrong_guard" else {"exit_kind": "exceptional"}))
        program = replace(program, transitions=tuple(changed if edge == connector else edge for edge in program.transitions))
    result = solve(program, budget=AnalysisBudget())
    assert not result.property_states["after_task_termination"]
    assert "task_source_binding_unavailable:task:0" in result.unknown_reasons
    assert dimensions(program)["all_exits", "close_obligation", "family:stream"].lifecycle_status == "unknown"


@pytest.mark.skipif(not os.environ.get("DOSWEB_TASK4_CACHED_FACTS"), reason="requires a recorded real Task 3 CodeQL facts path")
def test_cached_source_facts_analyze_and_replay(tmp_path):
    from dosweb.resource_lifecycle.adapters import extracted_from_dict, extracted_to_dict, validate_extracted
    from dosweb.resource_lifecycle.commands import resource_analyze, resource_replay
    from dosweb.resource_lifecycle.io import atomic_write_json
    source = Path(os.environ["DOSWEB_TASK4_CACHED_FACTS"])
    extracted = validate_extracted(extracted_from_dict(json.loads(source.read_text())))
    assert extracted.source_kind == "static_verified"
    assert extracted.coverage["end_to_end_mode"] == "real_source_codeql"
    # Product-state exploration needs an explicitly recorded larger budget for
    # repeated captures; the independent single-task source test uses defaults.
    extracted = replace(extracted, budget=AnalysisBudget(max_steps=50000, max_updates_per_event=64, timeout_ms=15000))
    input_path = tmp_path / "facts.json"
    atomic_write_json(input_path, extracted_to_dict(extracted))
    run = tmp_path / "run"
    resource_analyze({"facts": input_path, "out": run, "llm": "off"})
    report = json.loads((run / "lifecycle-results.json").read_text())
    by_id = {item["unit_id"]: item for item in report["units"]}
    for unit in extracted.units:
        if not unit.program.task_bindings:
            continue
        result = by_id[unit.unit_id]
        assert result["terminated"], result["unknown_reasons"]
        assert result["termination_guaranteed"] is False
        cuts = result["property_states"]["after_task_termination"]
        assert set(cuts) == {item.event_id for item in unit.program.task_exits}
        for task in unit.program.task_bindings:
            assert [task.instance_id, task.holder_id] not in cuts[task.normal_exit_event_id]["held_edges"]
            assert task.instance_id not in cuts[task.normal_exit_event_id]["open_obligations"]
        assert len(result["async_stages"]) == len(unit.program.task_bindings)
    assert resource_replay({"run": run})["consistent"]
