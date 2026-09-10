from dataclasses import replace

import pytest

from dosweb.resource_lifecycle.adapters import AnalysisUnit, ExtractedFacts
from dosweb.resource_lifecycle.commands import _analyze_payload, _async_stages, _evidence_payload
from dosweb.resource_lifecycle.invariants import check_invariants
from dosweb.resource_lifecycle.io import analysis_result_to_dict
from dosweb.resource_lifecycle.models import AnalysisBudget, Event, Holder, PopulationEffect, Transition
from dosweb.resource_lifecycle.solver import solve
from tests.test_resource_lifecycle_async_solver import task_program
from tests.test_resource_lifecycle_events import contract
from tests.test_resource_lifecycle_solver import effect, location


def artifact(program):
    unit = AnalysisUnit("manual:review", program, (), (replace(contract(), contract_id="executor"),))
    return ExtractedFacts("manual_fixture", "a" * 64, "manual-fixture-import-v1", AnalysisBudget(),
                          (unit,), (), {"end_to_end_mode": "manual_ir"})


def test_i1_submission_snapshot_cannot_merge_exclusive_task_phases():
    result = solve(task_program(), budget=AnalysisBudget())
    # A phase-bearing snapshot cannot claim the same task queued AND reserved.
    for state in result.async_states["task:0"].values():
        phases = getattr(state, "task_phases", ())
        assert len({task for task, phase in phases}) == len(phases)


def test_i1_normal_derivation_cannot_include_reject_or_exception_only_path():
    program = task_program(close_exceptional=False)
    result = solve(program, budget=AnalysisBudget())
    stage = _async_stages(artifact(program).units[0], result)[0]
    normal = stage.get("phase_derivations", {}).get("normal", [])
    assert normal, "missing phase-bound solved derivation"
    by_id = {edge.transition_id: edge for edge in program.transitions}
    for derivation in normal:
        trace = derivation["trace"]
        assert "task:0:terminal:exceptional" not in trace["transition_ids"]
        assert "task:0:edge:reject" not in trace["transition_ids"]
        edge = by_id[derivation["transition_id"]]
        assert derivation["source_event_id"] == edge.source_event_id
        assert derivation["target_event_id"] == edge.target_event_id


def caller_outcome_program():
    program = task_program()
    binding = program.task_bindings[0]
    original = next(edge for edge in program.transitions if edge.transition_id == "task:0:return")
    success = replace(original, guard="task_submit_success", assumptions=(
        f"task_binding:{binding.binding_id}", "cfg_fact:fact:success"), effects=(
            effect("retain", holder_id="holder:accepted"), effect("drop", holder_id="holder:request")))
    rejected = replace(original, transition_id="caller:reject", target_event_id="event:error", exit_kind="exceptional",
        guard="task_submit_exceptional", assumptions=(f"task_binding:{binding.binding_id}", "cfg_fact:fact:failure"),
        effects=(effect("retain", holder_id="holder:rejected"), effect("drop", holder_id="holder:request")))
    return replace(program, holders=program.holders + (
        Holder("holder:accepted", "field", "instance", "exact"), Holder("holder:rejected", "field", "instance", "exact")),
        exit_event_ids=("event:normal", "event:error"), transitions=tuple(success if edge == original else edge
            for edge in program.transitions) + (rejected,))


def test_i2_accept_and_abort_rejection_follow_only_matching_caller_cfg():
    result = solve(caller_outcome_program(), budget=AnalysisBudget(max_steps=10000))
    rejected = result.exit_states["event:error"]
    assert ("instance:stream", "task:0:holder") not in rejected.held_edges
    assert ("instance:stream", "holder:rejected") in rejected.held_edges
    assert ("instance:stream", "holder:accepted") not in rejected.held_edges
    assert "task:0:edge:reject" in result.traces["event:error"].transition_ids
    assert "task_rejection_continuation_unknown:task:0" not in result.unknown_reasons


def test_i2_success_continuation_dispatch_is_not_a_second_capture():
    program = caller_outcome_program()
    binding = program.task_bindings[0]
    dispatch = replace(effect("retain", holder_id=binding.holder_id), kind="dispatch", effect_id="source:dispatch",
        contract_id=binding.executor_contract_id, target_event_id=binding.queued_event_id,
        evidence_ids=("fact:source-dispatch",))
    program = replace(program, transitions=tuple(replace(edge, effects=(dispatch,) + edge.effects)
        if edge.guard == "task_submit_success" else edge for edge in program.transitions))
    result = solve(program, budget=AnalysisBudget(max_steps=10000))
    assert "task_binding_unavailable:source:dispatch" not in result.unknown_reasons
    assert "fact:source-dispatch" in result.traces["event:normal"].evidence_ids
    assert (binding.instance_id, binding.holder_id) not in result.property_states[
        "all_tasks_terminated_after_request"]["event:normal"].held_edges


@pytest.mark.parametrize("mismatch", ["instance_id", "holder_id", "contract_id", "target_event_id"])
def test_i2_mismatching_continuation_dispatch_stays_unknown(mismatch):
    program = task_program(reject=False)
    binding = program.task_bindings[0]
    dispatch = replace(effect("retain", holder_id=binding.holder_id), kind="dispatch", effect_id="source:dispatch",
        contract_id=binding.executor_contract_id, target_event_id=binding.queued_event_id,
        evidence_ids=("fact:source-dispatch",))
    wrong = {"instance_id": None, "holder_id": "holder:field", "contract_id": "wrong", "target_event_id": "event:normal"}
    dispatch = replace(dispatch, **{mismatch: wrong[mismatch]})
    program = replace(program, transitions=tuple(replace(edge, effects=(dispatch,) + edge.effects)
        if edge.guard == "task_submit_success" else edge for edge in program.transitions))
    result = solve(program, budget=AnalysisBudget())
    assert "task_binding_unavailable:source:dispatch" in result.unknown_reasons


def test_i2_cancellation_after_accept_does_not_block_caller_success():
    program = task_program(reject=False)
    binding = program.task_bindings[0]
    pop = PopulationEffect("cancel:population", "cancel_queued", "executor", binding.task_id,
        "queued removal", -1, 0, "queued", "cancelled", location(), ("fact:cancel",))
    cancel = Transition("cancel:edge", binding.queued_event_id, binding.cancelled_event_id,
                        "queued removal", (), "cancelled", (), (pop,))
    program = replace(program, transitions=tuple(edge for edge in program.transitions if not
        any(item.kind in {"direct_accept", "assign_slot"} for item in edge.population_effects)) + (cancel,))
    result = solve(program, budget=AnalysisBudget())
    assert "event:normal" in result.exit_states
    assert "task_success_continuation_unknown:task:0" not in result.unknown_reasons
    assert "cancel:edge" in result.traces["event:normal"].transition_ids


def test_i3_all_tasks_slice_has_one_identity_across_caller_exits():
    program = task_program(close_normal=False, close_exceptional=False, reject=False)
    original = next(edge for edge in program.transitions if edge.transition_id == "task:0:return")
    continuation = replace(original, target_event_id="caller:after", effects=(), exit_kind="internal")
    program = replace(program, events=program.events + (Event("caller:after", "method", "Fixture.handle", "true"),),
        exit_event_ids=("event:normal", "event:error"), transitions=tuple(continuation if edge == original else edge
            for edge in program.transitions) + (
                Transition("caller:closed", "caller:after", "event:normal", "normal", (effect("release"),), "normal", ()),
                Transition("caller:open", "caller:after", "event:error", "exceptional", (), "exceptional", ())))
    result = solve(program, budget=AnalysisBudget(max_steps=10000))
    rows = [row for row in check_invariants(program, result, (), timeout_ms=1000)
            if row.scope == "all_tasks_terminated_after_request"]
    identities = [(row.scope, row.dimension, row.resource_family_id) for row in rows]
    assert len(identities) == len(set(identities)), "contradictory duplicate dimension identities"
    assert next(row for row in rows if row.dimension == "close_obligation").lifecycle_status == "obligation_gap"


def test_i4_task_exit_evidence_type_is_not_overwritten_by_exit_kind():
    program = task_program()
    program = replace(program, task_exits=tuple(replace(exit, evidence_ids=(f"fact:exit:{exit.kind}",)) for exit in program.task_exits))
    extracted = artifact(program)
    evidence = _evidence_payload(extracted, _analyze_payload(extracted))
    assert evidence["facts"]["fact:exit:normal"].get("evidence_kind") == "task_relation_evidence"


def test_i4_shared_evidence_id_with_conflicting_locations_is_rejected():
    program = task_program()
    changed = replace(effect("release"), effect_id="conflicting-release", evidence_ids=("fact:create",),
                      location=replace(effect("release").location, start_line=9, end_line=9))
    program = replace(program, transitions=tuple(replace(edge, effects=(changed,))
        if edge.transition_id == "task:0:terminal:normal" else edge for edge in program.transitions))
    extracted = artifact(program)
    with pytest.raises(ValueError, match="evidence.*conflict"):
        _evidence_payload(extracted, _analyze_payload(extracted))


def test_i4_conditional_close_evidence_comes_from_the_matching_property_trace():
    program = task_program(close_exceptional=False)
    program = replace(program, transitions=tuple(replace(edge, effects=tuple(
        replace(current, evidence_ids=("fact:normal-only-close",)) if current.kind == "release" else current
        for current in edge.effects)) for edge in program.transitions))
    result = solve(program, budget=AnalysisBudget())
    rows = check_invariants(program, result, (), timeout_ms=1000)
    normal = next(row for row in rows if row.scope == "after_task_termination:task:0:normal" and row.dimension == "close_obligation")
    exceptional = next(row for row in rows if row.scope == "after_task_termination:task:0:exceptional" and row.dimension == "close_obligation")
    assert "fact:normal-only-close" in normal.evidence_ids
    assert "fact:normal-only-close" not in exceptional.evidence_ids


def test_i4_phase_proofs_and_conditional_locations_are_bound_to_executed_path():
    program = task_program()
    program = replace(program, transitions=tuple(replace(edge, effects=tuple(
        replace(current, evidence_ids=("fact:close:" + edge.exit_kind,),
                location=replace(current.location, start_line=11 if edge.exit_kind == "normal" else 17,
                                 end_line=11 if edge.exit_kind == "normal" else 17))
        if current.kind == "release" else current for current in edge.effects)) for edge in program.transitions))
    extracted = artifact(program)
    evidence = _evidence_payload(extracted, _analyze_payload(extracted))
    by_id = {edge.transition_id: edge for edge in program.transitions}
    normal_proofs = [row for row in evidence["async_derivations"] if row["phase"] == "normal"]
    assert normal_proofs
    for row in normal_proofs:
        assert set(row["conclusions"]) == {"normal"}
        edge = by_id[row["transition_id"]]
        assert (row["source_event_id"], row["target_event_id"]) == (edge.source_event_id, edge.target_event_id)
        assert "task:0:terminal:exceptional" not in row["transition_ids"]
        assert "task:0:edge:reject" not in row["transition_ids"]
        assert "fact:close:normal" in row["evidence_ids"]
        assert "fact:close:exceptional" not in row["evidence_ids"]
    proof = next(row for row in evidence["dimension_derivations"] if row["dimension"] == "close_obligation"
                 and row["scope"] == "after_task_termination:task:0:normal")
    assert "task:0:terminal:normal" in proof["transition_ids"]
    assert proof["property_event_ids"] == ["task:0:normal"]
    assert 11 in {item["start_line"] for item in proof["code_locations"]}
    assert 17 not in {item["start_line"] for item in proof["code_locations"]}


def test_i4_shared_source_keeps_multiple_claims_without_overwriting_them():
    program = task_program()
    program = replace(program, transitions=tuple(replace(edge, effects=tuple(
        replace(current, evidence_ids=("fact:allocation",)) if current.kind in {"create", "retain", "drop"} else current
        for current in edge.effects)) for edge in program.transitions))
    extracted = artifact(program)
    evidence = _evidence_payload(extracted, _analyze_payload(extracted))
    assert {item["claim"]["kind"] for item in evidence["facts"]["fact:allocation"]["claims"]} == {"create", "retain", "drop"}


def test_i4_same_effect_identity_cannot_bind_conflicting_holders():
    program = task_program()
    original = next(current for edge in program.transitions for current in edge.effects if current.kind == "retain")
    changed = replace(original, holder_id="holder:field")
    program = replace(program, transitions=tuple(replace(edge, effects=edge.effects + (changed,))
        if edge.transition_id == "task:0:return" else edge for edge in program.transitions))
    extracted = artifact(program)
    with pytest.raises(ValueError, match="evidence.*conflict"):
        _evidence_payload(extracted, _analyze_payload(extracted))


def test_minor_public_result_serializer_preserves_solver_cuts_and_async_evidence():
    result = solve(task_program(), budget=AnalysisBudget())
    serialized = analysis_result_to_dict(result)
    assert {"property_states", "property_traces", "async_states", "async_traces", "async_origins", "termination_guaranteed"} <= set(serialized)
