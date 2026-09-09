from __future__ import annotations

from dataclasses import dataclass, replace

from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.models import Effect, ResourceState
from dosweb.resource_lifecycle.solver import apply_effect


@dataclass(frozen=True)
class DispatchExpansion:
    submitted: ResourceState
    started: ResourceState
    completed: ResourceState
    rejected: ResourceState
    cancelled: ResourceState
    rule_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def _capture_effect(effect: Effect, kind: str) -> Effect:
    return Effect(
        effect_id=f"{effect.effect_id}:{kind}",
        kind=kind,
        instance_id=effect.instance_id,
        family_id=effect.family_id,
        holder_id=effect.holder_id,
        target_event_id=None,
        condition="true" if kind in {"drop", "release"} else effect.condition,
        location=effect.location,
        evidence_ids=effect.evidence_ids,
        contract_id=effect.contract_id,
    )


def _unknown(state: ResourceState, reason: str) -> ResourceState:
    return replace(state, unknown_reasons=tuple(sorted(set(state.unknown_reasons).union({reason}))))


def expand_dispatch(
    state: ResourceState,
    effect: Effect,
    contract: ExecutorContract | None,
) -> DispatchExpansion:
    if effect.kind != "dispatch":
        raise ValueError("dispatch expansion requires a dispatch effect")
    if effect.instance_id is None or effect.holder_id is None:
        unknown = _unknown(state, f"dispatch_identity_unknown:{effect.effect_id}")
        return DispatchExpansion(
            unknown,
            unknown,
            unknown,
            unknown,
            unknown,
            ("dispatch_identity_unknown",),
            tuple(sorted(set(effect.evidence_ids))),
        )
    if contract is None:
        contract_identity = effect.contract_id or effect.effect_id
        submitted_result = apply_effect(state, _capture_effect(effect, "retain"))
        submitted = _unknown(
            submitted_result.state,
            f"dispatch_contract_unavailable:{contract_identity}",
        )
        completed = _unknown(
            submitted,
            f"completion_contract_unknown:{contract_identity}",
        )
        rejected = _unknown(
            submitted,
            f"rejection_contract_unknown:{contract_identity}",
        )
        cancelled = _unknown(
            submitted,
            f"cancel_contract_unknown:{contract_identity}",
        )
        return DispatchExpansion(
            submitted,
            submitted,
            completed,
            rejected,
            cancelled,
            (
                "dispatch_capture_on_accept",
                "task_dequeue_is_phase_change",
                "task_completion_preserves_unknown_capture",
                "task_rejection_preserves_unknown_capture",
                "task_cancel_contract_unknown",
                "executor_contract_unavailable",
            ),
            tuple(sorted(set(effect.evidence_ids))),
        )
    if effect.contract_id != contract.contract_id:
        raise ValueError("dispatch contract identity does not match")
    if contract.source_kind not in {"static_verified", "trusted_contract", "manual_fixture"}:
        raise ValueError("dispatch semantics require a trusted contract")

    submitted_result = apply_effect(state, _capture_effect(effect, "retain"))
    submitted = submitted_result.state
    started = submitted
    rules = ["dispatch_capture_on_accept", "task_dequeue_is_phase_change"]

    if contract.termination == "drops_capture":
        completed_result = apply_effect(started, _capture_effect(effect, "drop"))
        completed = completed_result.state
        rules.append("task_completion_drops_capture")
    elif contract.termination == "retains_capture":
        completed = started
        rules.append("task_completion_retains_capture")
    else:
        completed = _unknown(started, f"completion_contract_unknown:{contract.contract_id}")
        rules.append("task_completion_preserves_unknown_capture")

    if contract.rejection_policy in {"abort", "discard"}:
        rejected = state
        rules.append("task_rejection_does_not_capture")
        rules.append(
            f"task_rejection_{contract.rejection_policy}_does_not_capture"
        )
    else:
        rejected = _unknown(
            submitted,
            f"rejection_policy_conservative:{contract.contract_id}:"
            f"{contract.rejection_policy}",
        )
        rules.append(
            f"task_rejection_{contract.rejection_policy}_preserves_unknown_capture"
        )

    if contract.cancellation == "drops_capture":
        cancelled = apply_effect(submitted, _capture_effect(effect, "drop")).state
        rules.append("task_cancel_drops_capture")
    elif contract.cancellation == "retains_capture":
        cancelled = submitted
        rules.append("task_cancel_retains_capture")
    else:
        cancelled = _unknown(submitted, f"cancel_contract_unknown:{contract.contract_id}")
        rules.append("task_cancel_contract_unknown")

    if contract.scheduling == "inline":
        rules.append("inline_execution_contract")
    else:
        rules.append("queued_execution_contract")
    return DispatchExpansion(
        submitted,
        started,
        completed,
        rejected,
        cancelled,
        tuple(rules),
        tuple(sorted(set(effect.evidence_ids))),
    )
