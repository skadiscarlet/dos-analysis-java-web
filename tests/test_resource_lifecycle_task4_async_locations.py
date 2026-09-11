from dataclasses import asdict, replace
import json

import pytest

from dosweb.resource_lifecycle.adapters import extracted_to_dict
from dosweb.resource_lifecycle.commands import _analyze_payload, _evidence_payload, resource_analyze, resource_replay
from dosweb.resource_lifecycle.io import atomic_write_json
from dosweb.resource_lifecycle.models import AnalysisBudget, Event
from dosweb.resource_lifecycle.solver import solve
from tests.test_resource_lifecycle_task4_locations import located_program
from tests.test_resource_lifecycle_task4_review import artifact


def same_kind_program(kind):
    program = located_program(False)
    original = next(item for item in program.task_exits if item.kind == kind)
    point = next(item for item in program.program_points if item.point_id == original.point_id)
    other_point = replace(point, point_id="point:other:" + kind,
                          location=replace(point.location, start_line=point.location.start_line + 20,
                                           end_line=point.location.end_line + 20))
    other_event = Event("event:other:" + kind, "method", "Fixture.task", other_point.point_id)
    other_exit = replace(original, exit_id="exit:other:" + kind, point_id=other_point.point_id,
                         evidence_ids=("fact:other-exit:" + kind,))
    enter = next(edge for edge in program.transitions if edge.transition_id == "edge:cfg:" + kind)
    terminal = next(edge for edge in program.transitions if edge.transition_id == "task:0:terminal:" + kind)
    program = replace(program, events=tuple(replace(event, activation_condition=original.point_id)
        if event.event_id == terminal.source_event_id else event for event in program.events) + (other_event,),
        program_points=program.program_points + (other_point,), task_exits=program.task_exits + (other_exit,),
        transitions=program.transitions + (
            replace(enter, transition_id="edge:other:" + kind, target_event_id=other_event.event_id),
            replace(terminal, transition_id="terminal:other:" + kind, source_event_id=other_event.event_id)))
    return program, original, other_exit


@pytest.mark.parametrize("kind", ["normal", "exceptional"])
def test_async_phase_and_child_proofs_resolve_one_same_kind_terminal(kind):
    program, original, other = same_kind_program(kind)
    extracted = artifact(program)
    evidence = _evidence_payload(extracted, _analyze_payload(extracted))
    points = {point.point_id: point for point in program.program_points}
    stages = [row for row in evidence["async_derivations"] if row["phase"] == kind]
    child = next(row for row in evidence["dimension_derivations"] if row["dimension"] == "close_obligation"
                 and row["scope"] == "after_task_termination:task:0:" + kind)
    assert stages and child["path_derivations"]
    seen = set()
    for row in stages + child["path_derivations"]:
        trace = row.get("trace", row)
        selected, excluded = (other, original) if "terminal:other:" + kind in trace["transition_ids"] else (original, other)
        seen.add(selected.exit_id)
        lines = {item["start_line"] for item in row["code_locations"]}
        assert points[selected.point_id].location.start_line in lines
        assert points[excluded.point_id].location.start_line not in lines
        assert set(selected.evidence_ids) <= set(row["evidence_ids"])
        assert not set(excluded.evidence_ids).intersection(row["evidence_ids"])
        relations = [evidence["facts"][relation_id]["claims"][0]["claim"]
                     for relation_id in row["relation_evidence"]]
        terminals = [relation for relation in relations if relation["kind"] == "task_exit"]
        assert {relation["task_exit_id"] for relation in terminals} == {selected.exit_id}
        assert all(relation["transition_id"] in trace["transition_ids"] for relation in relations)
        assert all(relation["point_id"] == selected.point_id for relation in terminals)
    assert seen == {original.exit_id, other.exit_id}


@pytest.mark.parametrize("missing", [False, True])
def test_async_evidence_rejects_ambiguous_or_missing_terminal_relation(missing):
    program, original, other = same_kind_program("normal")
    extracted = artifact(program)
    result = _analyze_payload(extracted)
    if missing:
        changed = replace(program, task_exits=tuple(item for item in program.task_exits if item.kind != "normal"))
    else:
        changed = replace(program, events=tuple(replace(event, activation_condition="unresolved")
            if event.activation_condition in {original.point_id, other.point_id} else event for event in program.events))
    extracted = replace(extracted, units=(replace(extracted.units[0], program=changed),))
    solved = solve(changed, budget=AnalysisBudget())
    assert "task:0:normal" not in solved.property_states["after_task_termination"]
    assert "task_exit_relation_unresolved:task:0" in solved.unknown_reasons
    with pytest.raises(ValueError, match="(task exit|dependency).*(missing|ambiguous|unresolved)"):
        _evidence_payload(extracted, result)


@pytest.mark.parametrize("tamper", ["async_location", "registry_relation"])
def test_replay_rejects_async_location_or_selected_registry_relation_tampering(tmp_path, tamper):
    program, original, other = same_kind_program("normal")
    extracted = artifact(program)
    facts, run = tmp_path / "facts.json", tmp_path / "run"
    atomic_write_json(facts, extracted_to_dict(extracted))
    resource_analyze({"facts": facts, "out": run, "llm": "off"})
    assert resource_replay({"run": run})["consistent"]
    stored = run / "evidence.json"
    evidence = json.loads(stored.read_text())
    proof = next(row for row in evidence["async_derivations"] if row["phase"] == "normal"
                 and "terminal:other:normal" not in row["transition_ids"])
    if tamper == "async_location":
        other_point = next(point for point in program.program_points if point.point_id == other.point_id)
        proof["code_locations"].append(asdict(other_point.location))
    else:
        relation = evidence["facts"][proof["relation_evidence"][0]]["claims"][0]["claim"]
        assert relation["point_id"] == original.point_id
        relation["point_id"] = other.point_id
    atomic_write_json(stored, evidence)
    assert resource_replay({"run": run})["evidence_consistent"] is False
