"""Exact terminal-source contract, including malformed in-memory defense checks."""
from copy import copy
from dataclasses import replace
import json

import pytest

from dosweb.resource_lifecycle.adapters import extracted_to_dict
from dosweb.resource_lifecycle.commands import _analyze_payload, _evidence_payload, resource_analyze, resource_replay
from dosweb.resource_lifecycle.io import atomic_write_json
from dosweb.resource_lifecycle.models import AnalysisBudget, resolve_task_exit
from dosweb.resource_lifecycle.solver import solve
from tests.test_resource_lifecycle_async_solver import task_program
from tests.test_resource_lifecycle_task4_review import artifact


def terminal(program, kind):
    return next(edge for edge in program.transitions if edge.transition_id == "task:0:terminal:" + kind)


SOURCE_MISMATCHES = ["other_point", "missing_point", "wrong_kind", "wrong_callable", "unbound_task_run"]


def corrupt_source(program, kind, mismatch):
    other_kind = "exceptional" if kind == "normal" else "normal"
    changes = {
        "other_point": {"activation_condition": "task:0:point:" + other_kind},
        "missing_point": {"activation_condition": "point:missing"},
        "wrong_kind": {"kind": "request"},
        "wrong_callable": {"callable": "Wrong.task"},
        "unbound_task_run": {"kind": "task_run"},
    }
    source_id = terminal(program, kind).source_event_id
    return replace(program, events=tuple(replace(event, **changes[mismatch]) if event.event_id == source_id else event
                                        for event in program.events))


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
@pytest.mark.parametrize("mismatch", SOURCE_MISMATCHES)
def test_singleton_terminal_resolver_rejects_invalid_source(kind, mismatch):
    program = corrupt_source(task_program(reject=False), kind, mismatch)
    with pytest.raises(ValueError, match="task exit"):
        resolve_task_exit(program, terminal(program, kind))


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
@pytest.mark.parametrize("mismatch", SOURCE_MISMATCHES)
def test_invalid_source_is_scoped_unknown_and_both_evidence_consumers_reject(kind, mismatch):
    program = task_program(reject=False)
    extracted = artifact(program)
    result = _analyze_payload(extracted)
    changed = corrupt_source(program, kind, mismatch)
    solved = solve(changed, budget=AnalysisBudget())
    assert "task:0:" + kind not in solved.property_states["after_task_termination"]
    assert kind not in solved.async_states["task:0"]
    assert "task_exit_relation_unresolved:task:0" in solved.unknown_reasons
    assert solved.termination_guaranteed is False
    altered = replace(extracted, units=(replace(extracted.units[0], program=changed),))
    for include_async in (True, False):
        payload = copy(result)
        if not include_async:
            payload["units"] = [dict(unit, async_stages=[]) for unit in result["units"]]
        with pytest.raises(ValueError):
            _evidence_payload(altered, payload)


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
@pytest.mark.parametrize("source_kind", ["method", "task_run"])
def test_exact_active_source_resolves_and_keeps_phase_and_child_evidence(kind, source_kind):
    program = task_program(reject=False)
    selected = next(item for item in program.task_exits if item.kind == kind)
    if source_kind == "task_run":
        binding = program.task_bindings[0]
        selected_edge = terminal(program, kind)
        program = replace(program, events=tuple(replace(event, activation_condition=selected.point_id)
            if event.event_id == binding.run_event_id else event for event in program.events),
            transitions=tuple(replace(edge, source_event_id=binding.run_event_id) if edge == selected_edge
                else edge for edge in program.transitions if edge.transition_id != "task:0:body-edge"))
    assert resolve_task_exit(program, terminal(program, kind)) == selected
    solved = solve(program, budget=AnalysisBudget())
    assert "task:0:" + kind in solved.property_states["after_task_termination"]
    assert "task_exit_relation_unresolved:task:0" not in solved.unknown_reasons
    extracted = artifact(program)
    evidence = _evidence_payload(extracted, _analyze_payload(extracted))
    phases = [row for row in evidence["async_derivations"] if row["phase"] == kind]
    child = next(row for row in evidence["dimension_derivations"] if row["dimension"] == "close_obligation"
                 and row["scope"] == "after_task_termination:task:0:" + kind)
    assert phases and child["path_derivations"]
    for proof in phases + child["path_derivations"]:
        assert set(selected.evidence_ids) <= set(proof["evidence_ids"])
        relations = [evidence["facts"][item]["claims"][0]["claim"] for item in proof["relation_evidence"]]
        exits = [item for item in relations if item["kind"] == "task_exit"]
        assert {item["task_exit_id"] for item in exits} == {selected.exit_id}
        assert {item["point_id"] for item in exits} == {selected.point_id}


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
@pytest.mark.parametrize("mutation", ["point_callable", "point_kind", "target_kind", "target_callable",
    "exit_task", "exit_callable", "exit_event", "exit_kind", "missing_source", "missing_target", "duplicate_exit"])
def test_resolver_defends_relations_even_below_program_constructor(kind, mutation):
    program = task_program(reject=False)
    edge = terminal(program, kind)
    selected = next(item for item in program.task_exits if item.kind == kind)
    changes = {}
    if mutation.startswith("point_"):
        field = mutation.removeprefix("point_")
        changes["program_points"] = tuple(replace(point, **{field: "Wrong.task" if field == "callable" else "effect"})
            if point.point_id == selected.point_id else point for point in program.program_points)
    elif mutation.startswith("target_"):
        field = mutation.removeprefix("target_")
        changes["events"] = tuple(replace(event, **{field: "Wrong.task" if field == "callable" else "method"})
            if event.event_id == edge.target_event_id else event for event in program.events)
    elif mutation.startswith("exit_"):
        field, value = {"exit_task": ("task_id", "task:missing"), "exit_callable": ("task_callable", "Wrong.task"),
            "exit_event": ("event_id", "event:normal"),
            "exit_kind": ("kind", "exceptional" if kind == "normal" else "normal")}[mutation]
        changes["task_exits"] = tuple(replace(item, **{field: value}) if item == selected else item
                                      for item in program.task_exits)
    elif mutation == "duplicate_exit":
        changes["task_exits"] = program.task_exits + (replace(selected, exit_id="exit:duplicate"),)
    else:
        missing = edge.source_event_id if mutation == "missing_source" else edge.target_event_id
        changes["events"] = tuple(event for event in program.events if event.event_id != missing)
    # Constructor rejection is an existing boundary, not a new resolver RED.
    with pytest.raises(ValueError):
        replace(program, **changes)
    malformed = copy(program)
    for field, value in changes.items():
        object.__setattr__(malformed, field, value)
    with pytest.raises(ValueError, match="task exit"):
        resolve_task_exit(malformed, edge)


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
def test_wrong_terminal_transition_kind_or_target_is_rejected(kind):
    program = task_program(reject=False)
    edge = terminal(program, kind)
    for changed in (replace(edge, exit_kind="exceptional" if kind == "normal" else "normal"),
                    replace(edge, exit_kind="internal"), replace(edge, target_event_id="event:missing")):
        with pytest.raises(ValueError, match="task exit"):
            resolve_task_exit(program, changed)
    assert resolve_task_exit(program, next(item for item in program.transitions
        if item.transition_id == "task:0:return")) is None


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
@pytest.mark.parametrize("mutation", ["ordinary_target", "wrong_active_path"])
def test_misattached_terminal_is_scoped_unknown_and_evidence_rejects(kind, mutation):
    program = task_program(reject=False)
    edge = terminal(program, kind)
    extracted = artifact(program)
    result = _analyze_payload(extracted)
    if mutation == "ordinary_target":
        changed = replace(program, transitions=tuple(replace(item, target_event_id="event:normal")
            if item == edge else item for item in program.transitions))
    else:
        changed = replace(program, events=tuple(replace(event, callable="Wrong.task")
            if event.event_id == "task:0:body" else event for event in program.events))
    with pytest.raises(ValueError, match="task exit"):
        resolve_task_exit(changed, terminal(changed, kind))
    solved = solve(changed, budget=AnalysisBudget())
    assert "task:0:" + kind not in solved.property_states["after_task_termination"]
    assert "task_exit_relation_unresolved:task:0" in solved.unknown_reasons
    assert solved.termination_guaranteed is False
    altered = replace(extracted, units=(replace(extracted.units[0], program=changed),))
    with pytest.raises(ValueError, match="task exit|async derivation transition evidence"):
        _evidence_payload(altered, result)


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
def test_replay_rejects_singleton_source_relation_tampering(tmp_path, kind):
    facts, run = tmp_path / "facts.json", tmp_path / "run"
    atomic_write_json(facts, extracted_to_dict(artifact(task_program(reject=False))))
    resource_analyze({"facts": facts, "out": run, "llm": "off"})
    assert resource_replay({"run": run})["consistent"]
    stored = run / "evidence.json"
    evidence = json.loads(stored.read_text())
    proof = next(row for row in evidence["async_derivations"] if row["phase"] == kind)
    relation = evidence["facts"][proof["relation_evidence"][0]]["claims"][0]["claim"]
    relation["point_id"] = "task:0:point:" + ("exceptional" if kind == "normal" else "normal")
    atomic_write_json(stored, evidence)
    assert resource_replay({"run": run})["evidence_consistent"] is False
