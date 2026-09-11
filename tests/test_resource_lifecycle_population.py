from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
from pathlib import Path

import pytest

import dosweb.resource_lifecycle.invariants as lifecycle_invariants
from dosweb.resource_lifecycle.adapters import (
    AnalysisUnit,
    ExtractedFacts,
    extracted_from_dict,
    validate_extracted,
)
from dosweb.resource_lifecycle.commands import _analyze_payload, _evidence_payload
from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.invariants import (
    InvariantCandidate,
    ModelCountEffect,
    check_invariants,
    check_model_count_effects,
    check_population_properties,
)
from dosweb.resource_lifecycle.models import (
    AbstractInstance,
    AnalysisBudget,
    Effect,
    Event,
    PopulationEffect,
    ProgramPoint,
    TaskExit,
    Transition,
)
from dosweb.resource_lifecycle.solver import solve
from tests.test_resource_lifecycle_async_solver import task_program
from tests.test_resource_lifecycle_solver import location


def executor_contract(**overrides: object) -> ExecutorContract:
    values: dict[str, object] = {
        "contract_id": "executor",
        "scheduling": "queued",
        "queue_capacity": 3,
        "capacity_atomic": True,
        "completion_drops_capture": False,
        "rejection_drops_capture": True,
        "cancellation": "unknown",
        "source_kind": "trusted_contract",
        "version": "executor-contract-v1",
        "core_workers": 1,
        "max_workers": 2,
        "rejection_policy": "abort",
        "termination": "unknown",
    }
    values.update(overrides)
    return ExecutorContract(**values)  # type: ignore[arg-type]


def population_program(*, count: int = 1):
    program = task_program(count=count)
    canonical_guards = {
        "direct_accept": "a<C or (q>=K and a<W)",
        "enqueue": "q<K",
        "assign_slot": "q>0 and a<W",
        "start": "reserved",
        "reject": "queue_or_workers_full",
    }
    terminal_edges: list[Transition] = []
    for edge in program.transitions:
        if edge.population_effects:
            edge = replace(
                edge,
                population_effects=tuple(
                    replace(item, guard=canonical_guards[item.kind])
                    for item in edge.population_effects
                ),
            )
        if edge.exit_kind not in {"normal", "exceptional"} or not edge.transition_id.endswith(
            (":terminal:normal", ":terminal:exceptional")
        ):
            terminal_edges.append(edge)
            continue
        task_id = edge.transition_id.split(":terminal:", 1)[0]
        terminal_edges.append(
            replace(
                edge,
                population_effects=(
                    PopulationEffect(
                        f"{task_id}:terminate:{edge.exit_kind}",
                        "terminate",
                        "executor",
                        task_id,
                        "a>0",
                        0,
                        -1,
                        "running",
                        "terminated",
                        location(),
                        (f"{task_id}:fact:population:terminate:{edge.exit_kind}",),
                    ),
                ),
            )
        )
    return replace(program, transitions=tuple(terminal_edges))


def queue_candidate(**overrides: object) -> InvariantCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate:untrusted-proof-flags",
        "family_id": "family:stream",
        "dimension": "held_instances",
        "scope": "task_queue",
        "upper_bound": 3,
        "initial_holds": False,
        "transitions_preserve": False,
        "covers_writers": False,
        "atomic": False,
        "source_kind": "static_verified",
        "assumptions": ("candidate flags are compatibility input only",),
        "evidence_ids": ("fact:candidate",),
        "executor_contract_id": "executor",
        "writer_holder_id": "task:0:holder",
        "writer_target_event_id": "task:0:queue",
    }
    values.update(overrides)
    return InvariantCandidate(**values)  # type: ignore[arg-type]


def test_q_a_induction_is_derived_from_population_effects_and_contract() -> None:
    program = population_program(count=2)

    properties = check_population_properties(program, (executor_contract(),))

    assert len(properties) == 1
    proof = properties[0]
    assert proof.dimension == "accepted_task_population"
    assert proof.scope == "executor:executor"
    assert proof.initial_state == (("q", 0), ("a", 0))
    assert (proof.queue_upper_bound, proof.active_upper_bound, proof.total_upper_bound) == (3, 2, 5)
    assert proof.initial_holds is True
    assert proof.transitions_preserve is True
    assert proof.covers_writers is True
    assert proof.lifecycle_status == "bounded"
    assert proof.repeat_assumption == "arbitrary_finite_repetitions_of_external_accept"
    assert {item.kind for item in proof.transition_equations} == {
        "direct_accept",
        "enqueue",
        "assign_slot",
        "start",
        "terminate",
        "reject",
    }
    assert any(item.equation == "q'=q+1, a'=a" for item in proof.transition_equations)
    assert any(item.equation == "q'=q-1, a'=a+1" for item in proof.transition_equations)
    assert all(item.preserves_bounds for item in proof.transition_equations)


def test_candidate_proof_booleans_cannot_override_derived_population_proof() -> None:
    program = population_program()
    result = solve(program, budget=AnalysisBudget(max_steps=10_000))

    dimensions = check_invariants(
        program,
        result,
        (queue_candidate(),),
        timeout_ms=1_000,
        executor_contracts=(executor_contract(),),
    )

    queue = next(item for item in dimensions if item.scope.startswith("task_queue:"))
    assert queue.lifecycle_status == "bounded"
    assert queue.upper_bound == 5
    assert any("q + a <= K + W" in item for item in queue.assumptions)
    assert "candidate_initial_state_failed" not in queue.reason_codes
    assert "candidate_not_inductive" not in queue.reason_codes
    assert "writer_coverage_incomplete" not in queue.reason_codes
    assert "capacity_not_atomic" not in queue.reason_codes
    assert queue.transition_ids


def test_missing_population_writer_fails_closed_under_repetition() -> None:
    program = population_program()
    program = replace(
        program,
        transitions=tuple(
            replace(edge, population_effects=())
            if any(item.kind == "enqueue" for item in edge.population_effects)
            else edge
            for edge in program.transitions
        ),
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert "population_transition_missing:task:0:enqueue" in proof.unknown_reasons
    assert proof.repeat_assumption == "arbitrary_finite_repetitions_of_external_accept"


def test_second_task_binding_without_population_effects_fails_closed() -> None:
    program = population_program(count=2)
    program = replace(
        program,
        transitions=tuple(
            replace(edge, population_effects=())
            if any(item.task_id == "task:1" for item in edge.population_effects)
            else edge
            for edge in program.transitions
        ),
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    for kind in ("direct_accept", "enqueue", "assign_slot", "start", "reject"):
        assert f"population_transition_missing:task:1:{kind}" in proof.unknown_reasons


def test_each_task_exit_requires_its_own_terminate_effect() -> None:
    for missing_kind in ("normal", "exceptional"):
        program = population_program()
        program = replace(
            program,
            transitions=tuple(
                replace(edge, population_effects=())
                if edge.transition_id == f"task:0:terminal:{missing_kind}"
                else edge
                for edge in program.transitions
            ),
        )

        proof = check_population_properties(program, (executor_contract(),))[0]

        assert proof.lifecycle_status == "unknown"
        assert proof.covers_writers is False
        assert any(
            reason.startswith(
                f"population_transition_missing:task:0:terminate:{missing_kind}:"
            )
            for reason in proof.unknown_reasons
        )


def test_multiple_exact_same_kind_task_exits_are_not_ambiguous() -> None:
    program = population_program()
    original_exit = next(item for item in program.task_exits if item.kind == "normal")
    original_point = next(
        item for item in program.program_points if item.point_id == original_exit.point_id
    )
    original_terminal = next(
        item
        for item in program.transitions
        if item.transition_id == "task:0:terminal:normal"
    )
    original_enter = next(
        item
        for item in program.transitions
        if item.target_event_id == original_terminal.source_event_id
        and item.exit_kind == "internal"
    )
    second_point = ProgramPoint(
        "task:0:point:normal:second",
        original_point.callable,
        "task_exit",
        location(),
    )
    second_source = Event(
        "task:0:terminal-source:normal:second",
        "method",
        original_point.callable,
        second_point.point_id,
    )
    second_exit = TaskExit(
        "task:0:exit:normal:second",
        original_exit.task_id,
        second_point.point_id,
        original_exit.event_id,
        original_exit.task_callable,
        "normal",
        ("task:0:fact:exit:normal:second",),
    )
    second_population = replace(
        original_terminal.population_effects[0],
        effect_id="task:0:terminate:normal:second",
        evidence_ids=("task:0:fact:population:terminate:normal:second",),
    )
    program = replace(
        program,
        events=program.events + (second_source,),
        program_points=program.program_points + (second_point,),
        task_exits=program.task_exits + (second_exit,),
        transitions=program.transitions
        + (
            replace(
                original_enter,
                transition_id="task:0:terminal-enter:normal:second",
                target_event_id=second_source.event_id,
            ),
            replace(
                original_terminal,
                transition_id="task:0:terminal:normal:second",
                source_event_id=second_source.event_id,
                population_effects=(second_population,),
            ),
        ),
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "bounded"
    assert "population_task_exit_ambiguous:task:0:normal" not in (
        proof.unknown_reasons
    )


def test_normal_and_exceptional_task_exit_relations_are_both_required() -> None:
    for missing_kind in ("normal", "exceptional"):
        program = population_program()
        removed = next(
            item for item in program.task_exits if item.kind == missing_kind
        )
        program = replace(
            program,
            task_exits=tuple(item for item in program.task_exits if item != removed),
            transitions=tuple(
                edge
                for edge in program.transitions
                if edge.transition_id != f"task:0:terminal:{missing_kind}"
            ),
        )

        proof = check_population_properties(program, (executor_contract(),))[0]

        assert proof.lifecycle_status == "unknown"
        assert proof.covers_writers is False
        assert (
            f"population_task_exit_missing:task:0:{missing_kind}"
            in proof.unknown_reasons
        )


def test_unknown_configuration_and_unmodeled_rejection_are_unknown() -> None:
    program = population_program()

    unknown_variants = (
        (executor_contract(queue_capacity=None), "executor_queue_capacity_unknown"),
        (executor_contract(queue_capacity="K"), "executor_queue_capacity_unknown"),
        (executor_contract(core_workers="C"), "executor_core_workers_unknown"),
        (executor_contract(max_workers="W"), "executor_max_workers_unknown"),
    )
    for contract, reason in unknown_variants:
        proof = check_population_properties(program, (contract,))[0]
        assert proof.lifecycle_status == "unknown"
        assert reason in proof.unknown_reasons

    caller_runs = check_population_properties(
        program,
        (
            executor_contract(
                rejection_policy="caller_runs",
                rejection_drops_capture=False,
            ),
        ),
    )[0]
    discard_oldest = check_population_properties(
        program,
        (
            executor_contract(
                rejection_policy="discard_oldest",
                rejection_drops_capture=False,
            ),
        ),
    )[0]
    non_atomic = check_population_properties(
        program,
        (executor_contract(capacity_atomic=False),),
    )[0]

    assert caller_runs.lifecycle_status == "unknown"
    assert "caller_runs_population_unmodeled" in caller_runs.unknown_reasons
    assert discard_oldest.lifecycle_status == "unknown"
    assert "executor_rejection_policy_unmodeled" in discard_oldest.unknown_reasons
    assert non_atomic.lifecycle_status == "unknown"
    assert "capacity_not_atomic" in non_atomic.unknown_reasons


def test_population_timeout_is_reported_and_analyze_threads_budget_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = population_program()

    proof = check_population_properties(
        program,
        (executor_contract(),),
        timeout_ms=0,
    )[0]
    assert proof.lifecycle_status == "unknown"
    assert "population_solver_timeout" in proof.unknown_reasons

    original = lifecycle_invariants.check_population_properties
    received_timeouts: list[int | None] = []

    def recording_checker(*args: object, **kwargs: object):
        received_timeouts.append(kwargs.get("timeout_ms"))  # type: ignore[arg-type]
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        lifecycle_invariants,
        "check_population_properties",
        recording_checker,
    )
    extracted = ExtractedFacts(
        "manual_fixture",
        "a" * 64,
        "resource-lifecycle-population-timeout-test",
        AnalysisBudget(max_steps=10_000, timeout_ms=7),
        (AnalysisUnit("unit:population-timeout", program, (), (executor_contract(),)),),
        (),
        {"end_to_end_mode": "manual_fixture"},
    )
    _analyze_payload(extracted)

    assert received_timeouts == [7]


def test_population_timeout_after_equation_construction_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moments = iter((0.0, 0.0, 0.0, 2.0))
    monkeypatch.setattr(
        lifecycle_invariants.time,
        "monotonic",
        lambda: next(moments),
    )

    proof = check_population_properties(
        population_program(),
        (executor_contract(),),
        timeout_ms=1_000,
    )[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert "population_solver_timeout" in proof.unknown_reasons


def test_evidence_reuses_the_population_result_without_a_second_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = population_program()
    extracted = ExtractedFacts(
        "manual_fixture",
        "a" * 64,
        "resource-lifecycle-population-evidence-timeout-test",
        AnalysisBudget(max_steps=10_000, timeout_ms=1_000),
        (AnalysisUnit("unit:population-timeout", program, (), (executor_contract(),)),),
        (),
        {"end_to_end_mode": "manual_fixture"},
    )
    result = _analyze_payload(extracted)
    assert result["units"][0]["population_properties"][0][
        "lifecycle_status"
    ] == "bounded"

    moments = iter((0.0, 2.0))
    monkeypatch.setattr(
        lifecycle_invariants.time,
        "monotonic",
        lambda: next(moments),
    )

    evidence = _evidence_payload(extracted, result)

    assert evidence["population_derivations"][0]["lifecycle_status"] == "bounded"
    assert next(moments) == 0.0


def test_incomplete_manual_population_remains_model_only_in_artifacts() -> None:
    program = population_program()
    program = replace(
        program,
        transitions=tuple(
            replace(transition, population_effects=())
            for transition in program.transitions
        ),
    )
    trusted_contract = executor_contract(source_kind="trusted_contract")
    extracted = ExtractedFacts(
        "manual_fixture",
        "a" * 64,
        "resource-lifecycle-population-model-only-test",
        AnalysisBudget(max_steps=10_000),
        (AnalysisUnit("unit:population-model-only", program, (), (trusted_contract,)),),
        (),
        {"end_to_end_mode": "manual_fixture"},
    )

    result = _analyze_payload(extracted)
    proof = result["units"][0]["population_properties"][0]
    evidence = _evidence_payload(extracted, result)
    derivation = evidence["population_derivations"][0]

    assert proof["lifecycle_status"] == "unknown"
    assert proof["model_only"] is True
    assert derivation["model_only"] is True


def test_relevant_coverage_gap_and_explicit_cancellation_are_checked() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    cancellation = PopulationEffect(
        "task:0:cancel-queued",
        "cancel_queued",
        "executor",
        binding.task_id,
        "queued",
        -1,
        0,
        "queued",
        "cancelled",
        location(),
        ("fact:cancel-queued",),
    )
    program = replace(
        program,
        transitions=program.transitions
        + (
            Transition(
                "task:0:cancel-edge",
                binding.queued_event_id,
                binding.cancelled_event_id,
                "cancel queued",
                (),
                "cancelled",
                (),
                (cancellation,),
            ),
        ),
    )

    supported = check_population_properties(program, (executor_contract(),))[0]
    assert supported.lifecycle_status == "bounded"
    assert any(item.kind == "cancel_queued" for item in supported.transition_equations)

    gapped = replace(
        program,
        coverage_complete=False,
        coverage_gaps=(
            (
                "held_instances",
                "family:stream",
                "*",
                "population_writer_uncovered",
                "fact:coverage-gap",
            ),
        ),
    )
    gap_proof = check_population_properties(
        gapped,
        (executor_contract(),),
    )[0]
    assert gap_proof.lifecycle_status == "unknown"
    assert "population_writer_uncovered" in gap_proof.unknown_reasons

    unrelated_gap = replace(
        program,
        coverage_complete=False,
        coverage_gaps=(
            (
                "close_obligation",
                "family:stream",
                "*",
                "conditional_release_not_must",
                "fact:close-gap",
            ),
        ),
    )
    unrelated_proof = check_population_properties(
        unrelated_gap,
        (executor_contract(),),
    )[0]
    assert unrelated_proof.lifecycle_status == "bounded"
    assert "population_coverage_incomplete" not in unrelated_proof.unknown_reasons

    unrelated_queue_gap = replace(
        program,
        coverage_complete=False,
        coverage_gaps=(
            (
                "held_instances",
                "family:stream",
                "task_queue:unrelated:holder:event",
                "unrelated_queue_gap",
                "fact:unrelated-queue-gap",
            ),
        ),
    )
    isolated_proof = check_population_properties(
        unrelated_queue_gap,
        (executor_contract(),),
    )[0]
    assert isolated_proof.lifecycle_status == "bounded"
    assert "unrelated_queue_gap" not in isolated_proof.unknown_reasons


def test_explicit_cancellation_without_population_effect_fails_closed() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    cancellation = Transition(
        "task:0:cancel-without-count",
        binding.queued_event_id,
        binding.cancelled_event_id,
        "cancel queued",
        (),
        "cancelled",
        (),
    )
    program = replace(program, transitions=program.transitions + (cancellation,))

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert (
        "population_cancellation_effect_missing:task:0:"
        "task:0:cancel-without-count"
        in proof.unknown_reasons
    )


def test_unbound_dispatch_writer_for_same_executor_fails_closed() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    second = AbstractInstance(
        "instance:stream:unbound",
        "family:stream",
        "recent",
        "exact",
    )
    dispatch = Effect(
        "effect:dispatch:unbound",
        "dispatch",
        second.instance_id,
        "family:stream",
        binding.holder_id,
        binding.queued_event_id,
        "accepted",
        location(),
        ("fact:dispatch:unbound",),
        contract_id="executor",
    )
    first = program.transitions[0]
    program = replace(
        program,
        instances=program.instances + (second,),
        transitions=(replace(first, effects=first.effects + (dispatch,)),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert (
        "population_dispatch_binding_unavailable:effect:dispatch:unbound"
        in proof.unknown_reasons
    )


@pytest.mark.parametrize("contract_id", [None, "executor:wrong"])
def test_structurally_related_dispatch_with_wrong_contract_fails_closed(
    contract_id: str | None,
) -> None:
    program = population_program()
    binding = program.task_bindings[0]
    family_id = program.instances[0].family_id
    dispatch = Effect(
        "effect:dispatch:wrong-contract",
        "dispatch",
        binding.instance_id,
        family_id,
        binding.holder_id,
        binding.queued_event_id,
        "accepted",
        location(),
        ("fact:dispatch:wrong-contract",),
        contract_id=contract_id,
    )
    first = program.transitions[0]
    program = replace(
        program,
        transitions=(replace(first, effects=first.effects + (dispatch,)),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert (
        "population_dispatch_binding_unavailable:effect:dispatch:wrong-contract"
        in proof.unknown_reasons
    )
    assert "fact:dispatch:wrong-contract" in proof.evidence_ids


@pytest.mark.parametrize(
    ("holder_id", "target_kind"),
    [
        ("task:0:holder", "submit"),
        ("holder:request", "queue"),
    ],
)
def test_partially_related_dispatch_with_wrong_contract_fails_closed(
    holder_id: str,
    target_kind: str,
) -> None:
    program = population_program()
    binding = program.task_bindings[0]
    family_id = program.instances[0].family_id
    extra_instance = AbstractInstance(
        f"instance:stream:partial-{target_kind}",
        family_id,
        "recent",
        "exact",
    )
    dispatch = Effect(
        f"effect:dispatch:partial-{target_kind}",
        "dispatch",
        extra_instance.instance_id,
        family_id,
        holder_id,
        (
            binding.submit_event_id
            if target_kind == "submit"
            else binding.queued_event_id
        ),
        "accepted",
        location(),
        (f"fact:dispatch:partial-{target_kind}",),
        contract_id="executor:wrong",
    )
    first = program.transitions[0]
    program = replace(
        program,
        instances=program.instances + (extra_instance,),
        transitions=(replace(first, effects=first.effects + (dispatch,)),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert (
        f"population_dispatch_binding_unavailable:effect:dispatch:partial-{target_kind}"
        in proof.unknown_reasons
    )
    assert f"fact:dispatch:partial-{target_kind}" in proof.evidence_ids


def test_same_holder_identityless_dispatch_with_wrong_contract_fails_closed() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    dispatch = Effect(
        "effect:dispatch:same-holder-identityless",
        "dispatch",
        None,
        None,
        binding.holder_id,
        binding.submit_event_id,
        "accepted",
        location(),
        ("fact:dispatch:same-holder-identityless",),
        contract_id="executor:wrong",
    )
    first = program.transitions[0]
    program = replace(
        program,
        transitions=(replace(first, effects=first.effects + (dispatch,)),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert (
        "population_dispatch_binding_unavailable:"
        "effect:dispatch:same-holder-identityless"
        in proof.unknown_reasons
    )
    assert "fact:dispatch:same-holder-identityless" in proof.evidence_ids


def test_queue_target_dispatch_without_instance_or_family_fails_closed() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    dispatch = Effect(
        "effect:dispatch:identity-unknown",
        "dispatch",
        None,
        None,
        binding.holder_id,
        binding.queued_event_id,
        "accepted",
        location(),
        ("fact:dispatch:identity-unknown",),
        contract_id=None,
    )
    first = program.transitions[0]
    program = replace(
        program,
        transitions=(replace(first, effects=first.effects + (dispatch,)),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert (
        "population_dispatch_binding_unavailable:effect:dispatch:identity-unknown"
        in proof.unknown_reasons
    )
    assert "fact:dispatch:identity-unknown" in proof.evidence_ids


def test_same_effect_id_cannot_hide_an_unmodeled_dispatch_writer() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    family_id = program.instances[0].family_id
    extra_instance = AbstractInstance(
        "instance:stream:duplicate-effect-id",
        family_id,
        "recent",
        "exact",
    )
    bad = Effect(
        "effect:dispatch:shared-id",
        "dispatch",
        extra_instance.instance_id,
        family_id,
        binding.holder_id,
        binding.queued_event_id,
        "accepted",
        location(),
        ("fact:dispatch:shared-id:bad",),
        contract_id="executor",
    )
    good = replace(
        bad,
        instance_id=binding.instance_id,
        evidence_ids=("fact:dispatch:shared-id:good",),
    )
    first = program.transitions[0]
    program = replace(
        program,
        instances=program.instances + (extra_instance,),
        transitions=(replace(first, effects=first.effects + (bad, good)),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert "population_dispatch_binding_unavailable:effect:dispatch:shared-id" in (
        proof.unknown_reasons
    )
    assert "fact:dispatch:shared-id:bad" in proof.evidence_ids


def test_modeled_dispatch_writer_evidence_is_a_population_dependency() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    exact_dispatch = Effect(
        "effect:dispatch:modeled-extra",
        "dispatch",
        binding.instance_id,
        program.instances[0].family_id,
        binding.holder_id,
        binding.queued_event_id,
        "accepted",
        location(),
        ("fact:dispatch:modeled-extra",),
        contract_id=binding.executor_contract_id,
    )
    first = program.transitions[0]
    program = replace(
        program,
        transitions=(replace(first, effects=first.effects + (exact_dispatch,)),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "bounded"
    assert "fact:dispatch:modeled-extra" in proof.evidence_ids

    extracted = ExtractedFacts(
        "manual_fixture",
        "a" * 64,
        "resource-lifecycle-modeled-writer-evidence-test",
        AnalysisBudget(max_steps=10_000),
        (AnalysisUnit("unit:modeled-writer", program, (), (executor_contract(),)),),
        (),
        {"end_to_end_mode": "manual_fixture"},
    )
    result = _analyze_payload(extracted)
    evidence = _evidence_payload(extracted, result)
    derivation = evidence["population_derivations"][0]
    dependencies = {
        item["evidence_id"]
        for item in evidence["proof_dependencies"]
        if item["proof_id"] == derivation["proof_id"]
    }
    assert "fact:dispatch:modeled-extra" in derivation["evidence_ids"]
    assert "fact:dispatch:modeled-extra" in dependencies


def test_unmodeled_retain_writer_for_task_holder_fails_closed() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    family_id = program.instances[0].family_id
    extra_instances = tuple(
        AbstractInstance(
            f"instance:stream:extra:{index}",
            family_id,
            "recent",
            "exact",
        )
        for index in range(6)
    )
    extra_writers = tuple(
        Effect(
            f"effect:retain:extra:{index}",
            "retain",
            instance.instance_id,
            family_id,
            binding.holder_id,
            None,
            "true",
            location(),
            (f"fact:retain:extra:{index}",),
        )
        for index, instance in enumerate(extra_instances)
    )
    first = program.transitions[0]
    program = replace(
        program,
        instances=program.instances + extra_instances,
        transitions=(replace(first, effects=first.effects + extra_writers),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]
    result = solve(program, budget=AnalysisBudget(max_steps=10_000))
    dimensions = check_invariants(
        program,
        result,
        (queue_candidate(),),
        timeout_ms=1_000,
        executor_contracts=(executor_contract(),),
    )
    held = next(
        item
        for item in dimensions
        if item.dimension == "held_instances" and item.scope.startswith("task_queue:")
    )

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert "population_retain_writer_unmodeled:effect:retain:extra:0" in (
        proof.unknown_reasons
    )
    assert held.lifecycle_status == "unknown"
    assert held.upper_bound is None


def test_retain_writer_uses_instance_family_when_effect_family_is_absent() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    family_id = program.instances[0].family_id
    extra_instance = AbstractInstance(
        "instance:stream:implicit-family",
        family_id,
        "recent",
        "exact",
    )
    writer = Effect(
        "effect:retain:implicit-family",
        "retain",
        extra_instance.instance_id,
        None,
        binding.holder_id,
        None,
        "true",
        location(),
        ("fact:retain:implicit-family",),
    )
    first = program.transitions[0]
    program = replace(
        program,
        instances=program.instances + (extra_instance,),
        transitions=(replace(first, effects=first.effects + (writer,)),)
        + program.transitions[1:],
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert (
        "population_retain_writer_unmodeled:effect:retain:implicit-family"
        in proof.unknown_reasons
    )
    assert "fact:retain:implicit-family" in proof.evidence_ids


def test_bound_instance_retain_outside_task_phase_fails_closed() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    family_id = program.instances[0].family_id
    writer = Effect(
        "effect:retain:after-terminal",
        "retain",
        binding.instance_id,
        family_id,
        binding.holder_id,
        None,
        "true",
        location(),
        ("fact:retain:after-terminal",),
    )
    program = replace(
        program,
        transitions=program.transitions
        + (
            Transition(
                "task:0:retain-after-terminal",
                binding.normal_exit_event_id,
                binding.normal_exit_event_id,
                "true",
                (writer,),
                "internal",
                (),
            ),
        ),
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert proof.covers_writers is False
    assert (
        "population_retain_writer_unmodeled:effect:retain:after-terminal"
        in proof.unknown_reasons
    )
    assert "fact:retain:after-terminal" in proof.evidence_ids


def test_free_form_population_guard_cannot_prove_induction() -> None:
    program = population_program()
    program = replace(
        program,
        transitions=tuple(
            replace(
                edge,
                population_effects=tuple(
                    replace(item, guard="true")
                    if item.kind == "enqueue"
                    else item
                    for item in edge.population_effects
                ),
            )
            for edge in program.transitions
        ),
    )

    proof = check_population_properties(program, (executor_contract(),))[0]

    assert proof.lifecycle_status == "unknown"
    assert any(
        reason.startswith("population_guard_unverified:")
        for reason in proof.unknown_reasons
    )


def test_multiple_population_effects_on_one_executor_transition_fail_closed() -> None:
    for kind in ("terminate", "cancel_queued"):
        program = population_program()
        if kind == "cancel_queued":
            binding = program.task_bindings[0]
            effect_to_duplicate = PopulationEffect(
                "task:0:cancel-queued",
                "cancel_queued",
                "executor",
                binding.task_id,
                "queued",
                -1,
                0,
                "queued",
                "cancelled",
                location(),
                ("fact:cancel-queued",),
            )
            edge = Transition(
                "task:0:cancel-edge",
                binding.queued_event_id,
                binding.cancelled_event_id,
                "cancel queued",
                (),
                "cancelled",
                (),
                (
                    effect_to_duplicate,
                    replace(
                        effect_to_duplicate,
                        effect_id="task:0:cancel-queued:duplicate",
                        evidence_ids=("fact:cancel-queued:duplicate",),
                    ),
                ),
            )
            program = replace(program, transitions=program.transitions + (edge,))
        else:
            program = replace(
                program,
                transitions=tuple(
                    replace(
                        edge,
                        population_effects=edge.population_effects
                        + (
                            replace(
                                edge.population_effects[0],
                                effect_id="task:0:terminate:normal:duplicate",
                                evidence_ids=("fact:terminate:normal:duplicate",),
                            ),
                        ),
                    )
                    if edge.transition_id == "task:0:terminal:normal"
                    else edge
                    for edge in program.transitions
                ),
            )

        proof = check_population_properties(program, (executor_contract(),))[0]

        assert proof.lifecycle_status == "unknown"
        assert proof.transitions_preserve is False
        assert any(
            reason.startswith("population_transition_effects_ambiguous:")
            for reason in proof.unknown_reasons
        )


def test_active_cancellation_guard_must_match_the_source_phase() -> None:
    program = population_program()
    binding = program.task_bindings[0]
    reserved_cancel = PopulationEffect(
        "task:0:cancel-reserved",
        "cancel_active",
        "executor",
        binding.task_id,
        "reserved",
        0,
        -1,
        "reserved",
        "cancelled",
        location(),
        ("fact:cancel-reserved",),
    )
    cancel_edge = Transition(
        "task:0:cancel-reserved-edge",
        binding.run_event_id,
        binding.cancelled_event_id,
        "cancel reserved",
        (),
        "cancelled",
        (),
        (reserved_cancel,),
    )
    supported = replace(program, transitions=program.transitions + (cancel_edge,))

    proof = check_population_properties(supported, (executor_contract(),))[0]

    assert proof.lifecycle_status == "bounded"
    assert any(
        item.kind == "cancel_active" and item.guard == "reserved"
        for item in proof.transition_equations
    )

    forged = replace(
        supported,
        transitions=tuple(
            replace(
                edge,
                population_effects=(replace(reserved_cancel, guard="running"),),
            )
            if edge.transition_id == cancel_edge.transition_id
            else edge
            for edge in supported.transitions
        ),
    )
    forged_proof = check_population_properties(forged, (executor_contract(),))[0]
    assert forged_proof.lifecycle_status == "unknown"
    assert any(
        reason.startswith("population_guard_unverified:")
        for reason in forged_proof.unknown_reasons
    )


def test_analyze_and_evidence_publish_population_proof() -> None:
    program = population_program()
    extracted = ExtractedFacts(
        "manual_fixture",
        "a" * 64,
        "resource-lifecycle-population-test",
        AnalysisBudget(max_steps=10_000),
        (AnalysisUnit("unit:population", program, (), (executor_contract(),)),),
        (),
        {"end_to_end_mode": "manual_fixture"},
    )

    result = _analyze_payload(extracted)
    properties = result["units"][0]["population_properties"]
    assert len(properties) == 1
    assert properties[0]["lifecycle_status"] == "bounded"
    evidence = _evidence_payload(extracted, result)
    assert len(evidence["population_derivations"]) == 1
    proof = evidence["population_derivations"][0]
    assert proof["scope"] == "executor:executor"
    assert set(proof["evidence_ids"]) <= set(evidence["facts"])
    dependencies = {
        item["evidence_id"]
        for item in evidence["proof_dependencies"]
        if item["proof_id"] == proof["proof_id"]
    }
    assert dependencies == set(proof["evidence_ids"])
    model_properties = result["model_count_properties"]
    assert [item["relation"] for item in model_properties] == [
        "N'=N+1",
        "N'=N",
        "N'=N",
    ]
    assert all(item["model_only"] for item in model_properties)
    assert len(evidence["model_count_derivations"]) == 3


def test_conflicting_executor_contract_body_cannot_share_evidence_id() -> None:
    program = population_program()
    extracted = ExtractedFacts(
        "manual_fixture",
        "a" * 64,
        "resource-lifecycle-contract-conflict-test",
        AnalysisBudget(max_steps=10_000),
        (
            AnalysisUnit(
                "unit:contract:k3",
                program,
                (),
                (executor_contract(queue_capacity=3),),
            ),
            AnalysisUnit(
                "unit:contract:k4",
                program,
                (),
                (executor_contract(queue_capacity=4),),
            ),
        ),
        (),
        {"end_to_end_mode": "manual_fixture"},
    )
    result = _analyze_payload(extracted)

    with pytest.raises(ValueError, match="executor contract evidence conflict"):
        _evidence_payload(extracted, result)


def test_model_only_count_contrasts_are_derived_from_identity_and_operation() -> None:
    effects = (
        ModelCountEffect(
            "model:fresh",
            "insert_fresh",
            "container:list",
            "object:new",
            None,
            "fresh",
            "manual_fixture",
            ("fact:model:fresh",),
        ),
        ModelCountEffect(
            "model:replace",
            "replace_fixed_position",
            "container:slot",
            "object:replacement",
            "slot:0",
            "fresh",
            "manual_fixture",
            ("fact:model:replace",),
        ),
        ModelCountEffect(
            "model:alias",
            "retain_same_object",
            "container:aliases",
            "object:existing",
            None,
            "same",
            "manual_fixture",
            ("fact:model:alias",),
        ),
    )

    results = check_model_count_effects(effects)

    assert [item.relation for item in results] == ["N'=N+1", "N'=N", "N'=N"]
    assert [item.dimension for item in results] == [
        "distinct_instances",
        "occupied_positions",
        "distinct_instances",
    ]
    assert all(item.model_only for item in results)
    assert all(item.lifecycle_status == "proven" for item in results)
    assert all(item.repeat_assumption == "arbitrary_finite_repetitions" for item in results)
    assert all(asdict(item)["source_kind"] == "manual_fixture" for item in results)


def test_model_only_count_unknown_identity_does_not_invent_a_relation() -> None:
    result = check_model_count_effects(
        (
            ModelCountEffect(
                "model:unknown",
                "retain_same_object",
                "container:aliases",
                "object:unknown",
                None,
                "unknown",
                "manual_fixture",
                ("fact:model:unknown",),
            ),
        )
    )[0]

    assert result.lifecycle_status == "unknown"
    assert result.relation is None
    assert "model_object_identity_unknown" in result.unknown_reasons


@pytest.mark.skipif(
    not os.environ.get("DOSWEB_TASK5_CACHED_FACTS"),
    reason="requires cached raw CodeQL facts re-adapted by the current adapter",
)
def test_cached_raw_source_relations_publish_reviewable_population_equations() -> None:
    source = Path(os.environ["DOSWEB_TASK5_CACHED_FACTS"])
    extracted = validate_extracted(
        extracted_from_dict(json.loads(source.read_text(encoding="utf-8")))
    )
    assert extracted.source_kind == "static_verified"
    assert extracted.coverage["end_to_end_mode"] == "real_source_codeql"

    result = _analyze_payload(extracted)
    source_properties = [
        item
        for unit in result["units"]
        for item in unit["population_properties"]
    ]
    assert source_properties
    proof = source_properties[0]
    assert proof["model_only"] is False
    assert proof["initial_holds"] is True
    assert proof["transitions_preserve"] is True
    assert (
        proof["queue_upper_bound"],
        proof["active_upper_bound"],
        proof["total_upper_bound"],
    ) == (3, 2, 5)
    assert {
        "direct_accept",
        "enqueue",
        "assign_slot",
        "start",
        "terminate",
        "reject",
    } <= {item["kind"] for item in proof["transition_equations"]}
    assert proof["repeat_assumption"] == (
        "arbitrary_finite_repetitions_of_external_accept"
    )
    assert proof["lifecycle_status"] == "unknown"
    assert "task_terminal_coverage_incomplete" in proof["unknown_reasons"]

    source_unit = next(
        unit
        for unit in extracted.units
        if any(
            item.contract_id == proof["scope"].removeprefix("executor:")
            for item in unit.executor_contracts
        )
    )
    atomic_evidence = {
        evidence_id
        for candidate in source_unit.invariants
        if candidate.executor_contract_id
        == proof["scope"].removeprefix("executor:")
        for evidence_id in candidate.evidence_ids
    }
    assert atomic_evidence
    assert atomic_evidence <= set(proof["evidence_ids"])

    evidence = _evidence_payload(extracted, result)
    source_derivations = [
        item
        for item in evidence["population_derivations"]
        if item["scope"] == proof["scope"]
    ]
    assert len(source_derivations) == 1
    assert source_derivations[0]["transition_equations"] == proof[
        "transition_equations"
    ]
    proof_dependencies = {
        item["evidence_id"]
        for item in evidence["proof_dependencies"]
        if item["proof_id"] == source_derivations[0]["proof_id"]
    }
    assert atomic_evidence <= proof_dependencies
