from dataclasses import asdict, replace
import json
import os
from pathlib import Path

import pytest

from dosweb.artifacts.identifiers import canonical_json
from dosweb.resource_lifecycle.adapters import extracted_from_dict, extracted_to_dict, validate_extracted
from dosweb.resource_lifecycle.commands import _analyze_payload, _evidence_payload, resource_analyze, resource_replay
from dosweb.resource_lifecycle.io import atomic_write_json, load_json_regular
from dosweb.resource_lifecycle.models import AnalysisBudget, Event, ProgramPoint
from dosweb.resource_lifecycle.solver import solve
from tests.test_resource_lifecycle_async_solver import task_program
from tests.test_resource_lifecycle_task4_rereview import reject_only_program
from tests.test_resource_lifecycle_task4_review import artifact


def located_program(closed=True):
    program = task_program(close_normal=closed, close_exceptional=closed, reject=False)
    points = [replace(point, location=replace(point.location,
              start_line=99 if point.point_id.endswith("normal") else 109,
              end_line=99 if point.point_id.endswith("normal") else 109)) for point in program.program_points]
    events = list(program.events)
    transitions = []
    for edge in program.transitions:
        if not edge.transition_id.startswith("task:0:terminal-enter:"):
            transitions.append(edge)
            continue
        kind = edge.transition_id.rsplit(":", 1)[-1]
        point_id = "point:cfg:" + kind
        event_id = "event:cfg:" + kind
        line = 77 if kind == "normal" else 88
        points.append(ProgramPoint(point_id, "Fixture.task", "effect",
                                   replace(points[0].location, start_line=line, end_line=line)))
        events.append(Event(event_id, "method", "Fixture.task", point_id))
        transitions.extend((replace(edge, transition_id="edge:cfg:" + kind, target_event_id=event_id,
                                    exit_kind="internal", effects=()),
                            replace(edge, source_event_id=event_id)))
    return replace(program, program_points=tuple(points), events=tuple(events), transitions=tuple(transitions))


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("kind", ["normal", "exceptional"])
def test_child_proof_keeps_exact_cfg_and_terminal_locations_without_other_branch(closed, kind):
    program = located_program(closed)
    extracted = artifact(program)
    evidence = _evidence_payload(extracted, _analyze_payload(extracted))
    proof = next(row for row in evidence["dimension_derivations"] if row["dimension"] == "close_obligation"
                 and row["scope"] == "after_task_termination:task:0:" + kind)
    selected_exit = next(item for item in program.task_exits if item.kind == kind)
    required = {77, 99} if kind == "normal" else {88, 109}
    excluded = {88, 109} if kind == "normal" else {77, 99}
    assert proof["path_derivations"]
    for path in proof["path_derivations"]:
        lines = {item["start_line"] for item in path["code_locations"]}
        assert required <= lines
        assert not excluded.intersection(lines)
        assert set(selected_exit.evidence_ids) <= set(path["evidence_ids"])
        relations = [evidence["facts"][relation_id]["claims"][0]["claim"]
                     for relation_id in path.get("relation_evidence", [])]
        assert {"point:cfg:" + kind, selected_exit.point_id} <= {row["point_id"] for row in relations}


def test_abort_only_without_pending_task_can_guarantee_task_termination():
    result = solve(reject_only_program(), budget=AnalysisBudget())
    assert result.terminated
    assert not result.unknown_reasons
    assert result.termination_guaranteed is True
    assert "obligation_gap" in result.lifecycle_statuses


def test_same_kind_terminal_relations_do_not_mix_mutually_exclusive_exit_evidence():
    program = located_program(False)
    original_exit = next(item for item in program.task_exits if item.kind == "normal")
    original_point = next(item for item in program.program_points if item.point_id == original_exit.point_id)
    second_point = replace(original_point, point_id="point:second-normal", location=replace(
        original_point.location, start_line=119, end_line=119))
    second_event = Event("event:second-normal", "method", "Fixture.task", second_point.point_id)
    second_exit = replace(original_exit, exit_id="exit:second-normal", point_id=second_point.point_id,
                          evidence_ids=("fact:second-normal-exit",))
    enter = next(edge for edge in program.transitions if edge.transition_id == "edge:cfg:normal")
    terminal = next(edge for edge in program.transitions if edge.transition_id == "task:0:terminal:normal")
    program = replace(program, events=tuple(replace(event, activation_condition=original_exit.point_id)
        if event.event_id == terminal.source_event_id else event for event in program.events) + (second_event,),
        program_points=program.program_points + (second_point,), task_exits=program.task_exits + (second_exit,),
        transitions=program.transitions + (
            replace(enter, transition_id="edge:second-normal", target_event_id=second_event.event_id),
            replace(terminal, transition_id="terminal:second-normal", source_event_id=second_event.event_id)))
    extracted = artifact(program)
    proof = next(row for row in _evidence_payload(extracted, _analyze_payload(extracted))["dimension_derivations"]
                 if row["dimension"] == "close_obligation" and row["scope"] == "after_task_termination:task:0:normal")
    for path in proof["path_derivations"]:
        is_second = "terminal:second-normal" in path["trace"]["transition_ids"]
        chosen, other = (second_exit, original_exit) if is_second else (original_exit, second_exit)
        assert set(chosen.evidence_ids) <= set(path["evidence_ids"])
        assert not set(other.evidence_ids).intersection(path["evidence_ids"])
        assert not set(other.evidence_ids).intersection(path["trace"]["evidence_ids"])
        assert (119 if is_second else 99) in {item["start_line"] for item in path["code_locations"]}
        assert (99 if is_second else 119) not in {item["start_line"] for item in path["code_locations"]}


@pytest.mark.parametrize("tampered_field", ["code_locations", "relation_evidence"])
def test_replay_detects_child_terminal_location_or_relation_tampering(tmp_path, tampered_field):
    extracted = artifact(located_program(False))
    facts, run = tmp_path / "facts.json", tmp_path / "run"
    atomic_write_json(facts, extracted_to_dict(extracted))
    resource_analyze({"facts": facts, "out": run, "llm": "off"})
    assert resource_replay({"run": run})["consistent"]
    stored = run / "evidence.json"
    evidence = json.loads(stored.read_text())
    proof = next(row for row in evidence["dimension_derivations"]
                 if row["dimension"] == "close_obligation" and row["scope"] == "after_task_termination:task:0:normal")
    proof["path_derivations"][0][tampered_field] = []
    atomic_write_json(stored, evidence)
    assert resource_replay({"run": run})["evidence_consistent"] is False


@pytest.mark.skipif(not os.environ.get("DOSWEB_TASK4_CACHED_FACTS"), reason="requires recorded real SourcePairs facts")
def test_cached_source_child_proof_includes_actual_terminal_program_point():
    extracted = validate_extracted(extracted_from_dict(load_json_regular(Path(os.environ["DOSWEB_TASK4_CACHED_FACTS"]))))
    evidence = _evidence_payload(extracted, _analyze_payload(extracted))
    assert len(canonical_json(evidence)) + 1 <= 16 * 1024 * 1024
    checked = 0
    for unit in extracted.units:
        points = {point.point_id: point for point in unit.program.program_points}
        for task_exit in unit.program.task_exits:
            proof = next(row for row in evidence["dimension_derivations"] if row["unit_id"] == unit.unit_id
                         and row["dimension"] == "close_obligation"
                         and row["scope"] == f"after_task_termination:{task_exit.task_id}:{task_exit.kind}")
            for path in proof["path_derivations"]:
                assert asdict(points[task_exit.point_id].location) in path["code_locations"]
                assert set(task_exit.evidence_ids) <= set(path["evidence_ids"])
                checked += 1
    assert checked
