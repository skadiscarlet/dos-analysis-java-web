from dataclasses import replace
import json

import pytest

from dosweb.resource_lifecycle.commands import _analyze_payload, _evidence_payload
from dosweb.resource_lifecycle.invariants import check_invariants
from dosweb.resource_lifecycle.io import analysis_result_to_dict, program_from_dict, program_to_dict
from dosweb.resource_lifecycle.models import AnalysisBudget
from dosweb.resource_lifecycle.solver import solve
from tests.test_resource_lifecycle_async_solver import task_program
from tests.test_resource_lifecycle_solver import effect
from tests.test_resource_lifecycle_task4_review import artifact, caller_outcome_program


def assert_single_accept_path(trace):
    edges = set(trace.transition_ids if hasattr(trace, "transition_ids") else trace["transition_ids"])
    assert not {"task:0:edge:direct_accept", "task:0:edge:enqueue"} <= edges


@pytest.mark.parametrize("scope,event", [
    ("after_task_termination", "task:0:normal"),
    ("all_tasks_terminated_after_request", "event:normal"),
])
def test_a_property_trace_cannot_merge_exclusive_accept_routes(scope, event):
    result = solve(task_program(reject=False), budget=AnalysisBudget())
    traces = result.property_traces[scope][event]
    for trace in traces if isinstance(traces, tuple) else (traces,):
        assert_single_accept_path(trace)


@pytest.mark.parametrize("scope", ["after_task_termination:task:0:normal", "all_tasks_terminated_after_request"])
def test_a_conditional_bound_has_separate_path_proofs(scope):
    extracted = artifact(task_program(reject=False))
    evidence = _evidence_payload(extracted, _analyze_payload(extracted))
    proof = next(row for row in evidence["dimension_derivations"] if row["dimension"] == "close_obligation"
                 and row["scope"] == scope)
    assert proof["lifecycle_status"] == "bounded"
    paths = proof.get("path_derivations", ())
    assert paths, "conditional bound has no independent path derivations"
    for path in paths:
        assert_single_accept_path(path["trace"])
    assert proof["transition_ids"] == [], "aggregate bound must not fabricate a single transition path"


def test_a_serializer_keeps_each_property_state_paired_with_its_trace():
    result = solve(task_program(reject=False), budget=AnalysisBudget())
    serialized = json.loads(json.dumps(analysis_result_to_dict(result)))
    for scope, events in result.property_derivations.items():
        for event_id, records in events.items():
            output = serialized["property_derivations"][scope][event_id]
            assert len(output) == len(records)
            assert [item["trace"] for item in output] == serialized["property_traces"][scope][event_id]
            for item in output:
                assert item["property_event_id"] == event_id
                assert "held_edges" in item["state"]
                assert_single_accept_path(item["trace"])


@pytest.mark.parametrize("field", ["property_derivations", "property_traces"])
def test_a_missing_path_evidence_cannot_produce_conditional_bound(field):
    program = task_program(reject=False)
    result = replace(solve(program, budget=AnalysisBudget()), **{field: {}})
    rows = [row for row in check_invariants(program, result, (), timeout_ms=1000) if row.property_event_ids]
    assert rows
    assert all(row.lifecycle_status == "unknown" and "property_path_evidence_incomplete" in row.reason_codes for row in rows)


def test_a_replay_recomputes_each_property_path_and_detects_trace_tampering(tmp_path):
    from dosweb.resource_lifecycle.adapters import extracted_to_dict
    from dosweb.resource_lifecycle.commands import resource_analyze, resource_replay
    from dosweb.resource_lifecycle.io import atomic_write_json
    extracted = artifact(task_program(reject=False))
    unit = extracted.units[0]
    extracted = replace(extracted, units=(replace(unit, executor_contracts=tuple(
        replace(contract, source_kind="manual_fixture") for contract in unit.executor_contracts)),))
    facts = tmp_path / "facts.json"
    run = tmp_path / "run"
    atomic_write_json(facts, extracted_to_dict(extracted))
    resource_analyze({"facts": facts, "out": run, "llm": "off"})
    assert resource_replay({"run": run})["consistent"]
    stored = run / "evidence.json"
    evidence = json.loads(stored.read_text())
    proof = next(row for row in evidence["dimension_derivations"] if row["scope"] == "all_tasks_terminated_after_request")
    proof["path_derivations"][0]["trace"]["transition_ids"].append("fabricated:mutually-exclusive-edge")
    atomic_write_json(stored, evidence)
    assert resource_replay({"run": run})["evidence_consistent"] is False


def reject_only_program():
    program = caller_outcome_program()
    return replace(program, exit_event_ids=("event:error",), transitions=tuple(
        edge for edge in program.transitions if not any(
            population.kind in {"direct_accept", "enqueue"} for population in edge.population_effects)))


def test_b_abort_only_open_obligation_is_not_reported_bounded():
    program = reject_only_program()
    result = solve(program, budget=AnalysisBudget())
    assert result.exit_states["event:error"].open_obligations
    row = next(row for row in check_invariants(program, result, (), timeout_ms=1000)
               if row.scope == "all_exits" and row.dimension == "close_obligation")
    assert row.lifecycle_status == "obligation_gap"
    assert "obligation_gap" in result.lifecycle_statuses
    assert "bounded" not in result.lifecycle_statuses


@pytest.mark.parametrize("via_json", [False, True])
def test_c_program_rejects_dispatch_instance_family_mismatch(via_json):
    program = task_program()
    binding = program.task_bindings[0]
    other = replace(program.families[0], family_id="family:other")
    dispatch = replace(effect("retain", holder_id=binding.holder_id), kind="dispatch", effect_id="source:dispatch",
        contract_id=binding.executor_contract_id, target_event_id=binding.queued_event_id,
        family_id=other.family_id, evidence_ids=("fact:source-dispatch",))
    transitions = tuple(replace(edge, effects=(dispatch,) + edge.effects)
                        if edge.guard == "task_submit_success" else edge for edge in program.transitions)
    if via_json:
        valid = replace(program, families=program.families + (other,))
        raw = program_to_dict(valid)
        from dataclasses import asdict
        edge = next(edge for edge in raw["transitions"] if edge["guard"] == "task_submit_success")
        edge["effects"] = (asdict(dispatch),) + edge["effects"]
        with pytest.raises(ValueError, match="instance.*family|family.*instance"):
            program_from_dict(json.loads(json.dumps(raw)))
    else:
        with pytest.raises(ValueError, match="instance.*family|family.*instance"):
            replace(program, families=program.families + (other,), transitions=transitions)
