from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.models import AnalysisResult, DimensionResult, Program, SOURCE_KINDS


@dataclass(frozen=True)
class InvariantCandidate:
    candidate_id: str
    family_id: str
    dimension: Literal["held_instances", "item_size_bytes", "close_obligation"]
    scope: str
    upper_bound: int | str
    initial_holds: bool
    transitions_preserve: bool
    covers_writers: bool
    atomic: bool
    source_kind: Literal["static_verified", "trusted_contract", "llm_proposed", "manual_fixture"]
    assumptions: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    executor_contract_id: str | None = None
    writer_holder_id: str | None = None
    writer_target_event_id: str | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.family_id or not self.scope:
            raise ValueError("invariant identity and scope are required")
        if self.dimension not in {"held_instances", "item_size_bytes", "close_obligation"}:
            raise ValueError("invariant dimension is invalid")
        if isinstance(self.upper_bound, int):
            if isinstance(self.upper_bound, bool) or self.upper_bound < 0:
                raise ValueError("invariant upper bound must be non-negative")
        elif not isinstance(self.upper_bound, str) or not self.upper_bound:
            raise ValueError("symbolic invariant upper bound must be non-empty")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError("invariant source kind is invalid")
        if any(
            not isinstance(item, bool)
            for item in (self.initial_holds, self.transitions_preserve, self.covers_writers, self.atomic)
        ):
            raise ValueError("invariant proof flags must be boolean")
        if not self.evidence_ids:
            raise ValueError("invariant requires evidence")
        queue_identity = (
            self.executor_contract_id,
            self.writer_holder_id,
            self.writer_target_event_id,
        )
        if self.scope == "task_queue":
            if any(not isinstance(item, str) or not item for item in queue_identity):
                raise ValueError("task queue invariant requires contract, holder, and target identity")
        elif any(item is not None for item in queue_identity):
            raise ValueError("non-queue invariant cannot declare queue identity")


def _unknown(
    dimension: str,
    scope: str,
    reasons: tuple[str, ...],
    evidence: tuple[str, ...] = (),
    family_id: str | None = None,
) -> DimensionResult:
    return DimensionResult(
        dimension,
        scope,
        "unknown",
        None,
        reason_codes=tuple(sorted(set(reasons))),
        evidence_ids=evidence,
        resource_family_id=family_id,
    )


def _analysis_precision_reasons(result: AnalysisResult) -> tuple[str, ...]:
    relevant = tuple(
        sorted(
            reason
            for reason in result.unknown_reasons
            if reason.startswith(("analysis_budget", "solver_timeout", "iteration_limit:", "exit_state_", "unknown_call:", "dispatch_contract_", "dispatch_identity_", "holder_scope_identity_unknown:", "weak_update:", "untrusted_negative_effect:", "conditional_negative_effect:", "repeated_abstract_instance:"))
        )
    )
    return relevant


def _coverage_details(
    program: Program,
    dimension: str,
    family_id: str,
    scope: str | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if program.coverage_complete:
        return (), ()
    if not program.coverage_gaps:
        return ("coverage_incomplete",), ()
    selected = tuple(
        item
        for item in program.coverage_gaps
        if item[0] == dimension
        and item[1] == family_id
        and (scope is None or item[2] in {"*", scope})
    )
    return (
        tuple(
            sorted(
                {
                    reason
                    for _gap_dimension, _family_id, _scope, reason, _evidence_id in selected
                }
            )
        ),
        tuple(
            sorted(
                {
                    evidence_id
                    for _gap_dimension, _family_id, _scope, _reason, evidence_id in selected
                }
            )
        ),
    )


def _precision_evidence(program: Program, reasons: tuple[str, ...], family_id: str) -> tuple[str, ...]:
    selected: set[str] = set()
    for transition in program.transitions:
        for effect in transition.effects:
            if effect.family_id != family_id:
                continue
            if any(
                effect.effect_id in reason
                or (effect.instance_id is not None and reason.endswith(effect.instance_id))
                or (effect.holder_id is not None and reason.endswith(effect.holder_id))
                for reason in reasons
            ):
                selected.update(effect.evidence_ids)
    return tuple(sorted(selected))


def _family_effect_evidence(program: Program, family_id: str, kinds: frozenset[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                evidence_id
                for transition in program.transitions
                for effect in transition.effects
                if effect.family_id == family_id and effect.kind in kinds
                for evidence_id in effect.evidence_ids
            }
        )
    )


def _observed_peak(candidate: InvariantCandidate, result: AnalysisResult) -> tuple[int | None, tuple[str, ...]]:
    if candidate.scope == "task_queue":
        observed = [
            sum(
                1
                for instance_id, holder_id in state.held_edges
                if holder_id == candidate.writer_holder_id
                and dict(state.instance_families).get(instance_id) == candidate.family_id
            )
            for state in result.event_states.values()
        ]
        return max(observed, default=0), ()
    observed = [
        dict(state.peak_held_counts).get(candidate.family_id, 0)
        for state in result.event_states.values()
    ]
    if any(value is None for value in observed):
        return None, ("observed_upper_unknown",)
    return max((value for value in observed if value is not None), default=0), ()


def queue_result_scope(
    contract_id: str | None,
    holder_id: str | None,
    target_event_id: str | None,
) -> str:
    return ":".join(
        (
            "task_queue",
            contract_id or "missing-contract",
            holder_id or "missing-holder",
            target_event_id or "missing-target",
        )
    )


def candidate_result_scope(candidate: InvariantCandidate) -> str:
    if candidate.scope != "task_queue":
        return candidate.scope
    return queue_result_scope(
        candidate.executor_contract_id,
        candidate.writer_holder_id,
        candidate.writer_target_event_id,
    )


def _writer_structure_reasons(program: Program, candidate: InvariantCandidate) -> tuple[str, ...]:
    holders = {item.holder_id: item for item in program.holders}
    events = {item.event_id: item for item in program.events}
    instances = {item.instance_id: item for item in program.instances}
    writers = tuple(
        effect
        for transition in program.transitions
        for effect in transition.effects
        if effect.family_id == candidate.family_id and effect.kind in {"retain", "dispatch"}
    )

    if candidate.scope == "task_queue":
        queue_writers = tuple(
            effect
            for effect in writers
            if effect.holder_id is not None and holders[effect.holder_id].kind == "task"
        )
        if not queue_writers:
            return ("queue_writer_structure_unverified",)
        matching_writers = tuple(
            effect
            for effect in queue_writers
            if effect.contract_id == candidate.executor_contract_id
            and effect.holder_id == candidate.writer_holder_id
            and effect.target_event_id == candidate.writer_target_event_id
        )
        if not matching_writers:
            if any(
                effect.holder_id == candidate.writer_holder_id
                and effect.target_event_id == candidate.writer_target_event_id
                for effect in queue_writers
            ):
                return ("queue_writer_contract_mismatch",)
            return ("queue_writer_identity_mismatch",)
        reasons: list[str] = []
        for effect in matching_writers:
            target = events.get(effect.target_event_id or "")
            if effect.kind != "dispatch" or target is None or target.kind != "task_queue":
                reasons.append("queue_writer_structure_unverified")
            elif effect.location.source_kind not in {"static_verified", "trusted_contract", "manual_fixture"}:
                reasons.append("untrusted_queue_writer_source")
        return tuple(sorted(set(reasons)))

    if candidate.scope in {"field", "fixed_field"}:
        field_writers = tuple(
            effect
            for effect in writers
            if effect.holder_id is not None and holders[effect.holder_id].kind == "field"
        )
        if not field_writers:
            return ("fixed_replacement_structure_unverified",)
        holder_ids = {effect.holder_id for effect in field_writers}
        exact_instances = all(
            effect.instance_id is not None
            and instances[effect.instance_id].abstraction == "recent"
            and instances[effect.instance_id].identity_confidence == "exact"
            for effect in field_writers
        )
        exact_holder = len(holder_ids) == 1 and all(holders[holder_id].identity_precision == "exact" for holder_id in holder_ids)
        trusted_writers = all(
            effect.location.source_kind in {"static_verified", "trusted_contract", "manual_fixture"}
            for effect in field_writers
        )
        if candidate.upper_bound != 1 or not exact_holder or not exact_instances or not trusted_writers:
            return ("fixed_replacement_structure_unverified",)
        return ()

    return ("unsupported_invariant_scope",)


def _executor_contract_reasons(
    candidate: InvariantCandidate,
    contracts: dict[str, ExecutorContract],
) -> tuple[str, ...]:
    if candidate.scope != "task_queue":
        return ()
    contract = contracts.get(candidate.executor_contract_id or "")
    if contract is None:
        return ("executor_contract_unavailable",)
    reasons: list[str] = []
    if contract.source_kind not in {"static_verified", "trusted_contract", "manual_fixture"}:
        reasons.append("untrusted_executor_contract_source")
    if contract.scheduling != "queued":
        reasons.append("queue_scheduling_contract_mismatch")
    if contract.queue_capacity != candidate.upper_bound:
        reasons.append("queue_capacity_contract_mismatch")
    if not contract.capacity_atomic:
        reasons.append("capacity_not_atomic")
    return tuple(reasons)


def _check_candidate(
    candidate: InvariantCandidate,
    program: Program,
    result: AnalysisResult,
    contracts: dict[str, ExecutorContract],
) -> DimensionResult:
    reasons: list[str] = []
    if candidate.source_kind not in {"static_verified", "trusted_contract"}:
        reasons.append("untrusted_invariant_source")
    if not candidate.initial_holds:
        reasons.append("candidate_initial_state_failed")
    if not candidate.transitions_preserve:
        reasons.append("candidate_not_inductive")
    if not candidate.covers_writers:
        reasons.append("writer_coverage_incomplete")
    if not candidate.atomic:
        reasons.append("capacity_not_atomic")
    reasons.extend(_executor_contract_reasons(candidate, contracts))
    peak, peak_reasons = _observed_peak(candidate, result)
    reasons.extend(peak_reasons)
    if isinstance(candidate.upper_bound, int) and peak is not None:
        if peak > candidate.upper_bound:
            reasons.append("observed_upper_exceeds_candidate")
    precision_reasons = _analysis_precision_reasons(result)
    reasons.extend(_writer_structure_reasons(program, candidate))
    reasons.extend(precision_reasons)
    coverage_reasons, coverage_evidence = _coverage_details(
        program,
        candidate.dimension,
        candidate.family_id,
        candidate_result_scope(candidate),
    )
    reasons.extend(coverage_reasons)
    if reasons:
        return _unknown(
            candidate.dimension,
            candidate_result_scope(candidate),
            tuple(reasons),
            tuple(
                sorted(
                    set(candidate.evidence_ids)
                    .union(coverage_evidence)
                    .union(_precision_evidence(program, precision_reasons, candidate.family_id))
                )
            ),
            candidate.family_id,
        )
    assumptions = candidate.assumptions
    if isinstance(candidate.upper_bound, str):
        assert peak is not None
        assumptions = tuple(
            dict.fromkeys(
                assumptions
                + (
                    f"symbolic upper bound {candidate.upper_bound} is finite and positive",
                    f"{candidate.upper_bound} >= observed peak {peak}",
                )
            )
        )
    return DimensionResult(
        candidate.dimension,
        candidate_result_scope(candidate),
        "bounded",
        candidate.upper_bound,
        assumptions=assumptions,
        evidence_ids=candidate.evidence_ids,
        resource_family_id=candidate.family_id,
    )


def check_invariants(
    program: Program,
    result: AnalysisResult,
    candidates: tuple[InvariantCandidate, ...],
    *,
    timeout_ms: int,
    executor_contracts: tuple[ExecutorContract, ...] = (),
) -> tuple[DimensionResult, ...]:
    if timeout_ms < 0:
        raise ValueError("timeout_ms must be non-negative")
    family_ids = {item.family_id for item in program.families}
    if any(item.family_id not in family_ids for item in candidates):
        raise ValueError("invariant references an unknown resource family")
    contracts = {item.contract_id: item for item in executor_contracts}
    if len(contracts) != len(executor_contracts):
        raise ValueError("duplicate executor contract identifier")
    if timeout_ms == 0:
        return tuple(
            _unknown(dimension, "analysis", ("solver_timeout",), family_id=resource.family_id)
            for resource in sorted(program.families, key=lambda item: item.family_id)
            for dimension in ("held_instances", "item_size_bytes", "close_obligation")
        )

    output: list[DimensionResult] = []
    precision_reasons = _analysis_precision_reasons(result)
    holders = {item.holder_id: item for item in program.holders}
    for resource in sorted(program.families, key=lambda item: item.family_id):
        precision_evidence = _precision_evidence(program, precision_reasons, resource.family_id)
        family_instances = {item.instance_id for item in program.instances if item.family_id == resource.family_id}
        relevant_tasks = [item for item in program.task_bindings if item.instance_id in family_instances]
        relevant_dispatches = [effect for transition in program.transitions for effect in transition.effects
                               if effect.kind == "dispatch" and effect.instance_id in family_instances]
        temporal_reasons = tuple(reason for reason in result.unknown_reasons if
            reason.startswith("task_") and any(reason.endswith(item.task_id) for item in relevant_tasks)
            or reason.startswith("task_binding_unavailable:") and any(reason.endswith(item.effect_id) for item in relevant_dispatches))
        temporal_evidence = tuple(sorted({evidence for item in relevant_tasks for evidence in item.evidence_ids}
                                        | {evidence for item in relevant_dispatches for evidence in item.evidence_ids}))
        if resource.allocation.source_kind == "llm_proposed":
            output.extend(
                _unknown(dimension, scope, ("untrusted_resource_family",), (resource.family_id,), resource.family_id)
                for dimension, scope in (
                    ("held_instances", "all_exits"),
                    ("item_size_bytes", "per_instance"),
                    ("close_obligation", "all_exits"),
                )
            )
            continue
        count_candidates = sorted(
            (item for item in candidates if item.family_id == resource.family_id and item.dimension == "held_instances"),
            key=lambda item: item.candidate_id,
        )
        if count_candidates:
            output.extend(
                _check_candidate(candidate, program, result, contracts)
                for candidate in count_candidates
            )
            queue_candidates = {
                (
                    candidate.executor_contract_id,
                    candidate.writer_holder_id,
                    candidate.writer_target_event_id,
                )
                for candidate in count_candidates
                if candidate.scope == "task_queue"
            }
            uncovered_queue_writers: dict[tuple[str | None, str | None, str | None], set[str]] = {}
            for transition in program.transitions:
                for effect in transition.effects:
                    holder = holders.get(effect.holder_id or "")
                    writer_identity = (
                        effect.contract_id,
                        effect.holder_id,
                        effect.target_event_id,
                    )
                    if (
                        effect.family_id == resource.family_id
                        and effect.kind == "dispatch"
                        and holder is not None
                        and holder.kind == "task"
                        and writer_identity not in queue_candidates
                    ):
                        uncovered_queue_writers.setdefault(writer_identity, set()).update(effect.evidence_ids)
            for writer_identity, evidence_ids in sorted(
                uncovered_queue_writers.items(),
                key=lambda item: tuple(value or "" for value in item[0]),
            ):
                scope = queue_result_scope(*writer_identity)
                coverage_reasons, coverage_evidence = _coverage_details(
                    program,
                    "held_instances",
                    resource.family_id,
                    scope,
                )
                output.append(
                    _unknown(
                        "held_instances",
                        scope,
                        tuple(
                            sorted(
                                {"queue_writer_not_covered"}.union(coverage_reasons)
                            )
                        ),
                        tuple(sorted(evidence_ids.union(coverage_evidence))),
                        resource.family_id,
                    )
                )
        else:
            count_coverage, count_evidence = _coverage_details(
                program, "held_instances", resource.family_id
            )
            count_reasons = tuple(sorted(set(precision_reasons).union(count_coverage, temporal_reasons)))
            held = any(
                dict(state.instance_families).get(instance_id) == resource.family_id
                for state in result.exit_states.values()
                for instance_id, _holder_id in state.held_edges
            )
            if not held and not count_reasons:
                output.append(DimensionResult("held_instances", "all_exits", "bounded", 0, evidence_ids=(), resource_family_id=resource.family_id))
            else:
                reasons = count_reasons or (("no_verified_count_invariant",) if held else ("coverage_incomplete",))
                held_evidence = set(count_evidence).union(precision_evidence, temporal_evidence)
                if held:
                    held_evidence.update(
                        _family_effect_evidence(program, resource.family_id, frozenset({"retain", "dispatch"}))
                    )
                output.append(
                    _unknown(
                        "held_instances",
                        "all_exits",
                        tuple(reasons),
                        tuple(sorted(held_evidence)),
                        resource.family_id,
                    )
                )

        size_coverage, size_evidence = _coverage_details(
            program, "item_size_bytes", resource.family_id
        )
        size_reasons = tuple(sorted(set(precision_reasons).union(size_coverage)))
        if size_reasons:
            output.append(
                _unknown(
                    "item_size_bytes",
                    "per_instance",
                    size_reasons,
                    tuple(sorted(set(size_evidence).union(precision_evidence))),
                    resource.family_id,
                )
            )
        elif resource.item_size_upper is None:
            output.append(
                _unknown(
                    "item_size_bytes",
                    "per_instance",
                    ("item_size_unknown",),
                    (resource.family_id,),
                    resource.family_id,
                )
            )
        else:
            output.append(
                DimensionResult(
                    "item_size_bytes",
                    "per_instance",
                    "bounded",
                    resource.item_size_upper,
                    evidence_ids=(resource.family_id,),
                    resource_family_id=resource.family_id,
                )
            )

        family_instances = {item.instance_id for item in program.instances if item.family_id == resource.family_id}
        open_at_exit = any(
            state.open_obligations & family_instances
            or (lambda interval: interval is not None and (interval.upper is None or interval.upper > 0))(
                dict(state.obligation_counts).get(resource.family_id)
            )
            for state in result.exit_states.values()
        )
        close_coverage, close_evidence = _coverage_details(
            program, "close_obligation", resource.family_id
        )
        close_reasons = tuple(sorted(set(precision_reasons).union(close_coverage, temporal_reasons)))
        if not resource.requires_close:
            output.append(DimensionResult("close_obligation", "all_exits", "not_applicable", 0, resource_family_id=resource.family_id))
        elif close_reasons:
            output.append(
                _unknown(
                    "close_obligation",
                    "all_exits",
                    close_reasons,
                    tuple(sorted(set(close_evidence).union(precision_evidence, temporal_evidence))),
                    resource.family_id,
                )
            )
        elif open_at_exit:
            output.append(
                DimensionResult(
                    "close_obligation",
                    "all_exits",
                    "obligation_gap",
                    None,
                    reason_codes=("open_obligation_at_exit",),
                    evidence_ids=tuple(sorted(family_instances)),
                    resource_family_id=resource.family_id,
                )
            )
        else:
            output.append(DimensionResult("close_obligation", "all_exits", "bounded", 0, evidence_ids=tuple(sorted(family_instances)), resource_family_id=resource.family_id))
    # Conditional exit properties use states saved by the same main worklist.
    # Liveness/cancel/rejection gaps remain on the overall result, while solver
    # precision and source coverage gaps still apply to these conditional slices.
    if result.property_states:
        task_exit_by_event = {item.event_id: item for item in program.task_exits}
        bindings = {item.task_id: item for item in program.task_bindings}
        for slice_name, exit_states in result.property_states.items():
            if slice_name not in {"after_task_termination", "all_tasks_terminated_after_request"}:
                continue
            for event_id, state in sorted(exit_states.items()):
                task_exit = task_exit_by_event.get(event_id)
                sliced = replace(result, exit_states={event_id: state}, property_states={},
                    unknown_reasons=tuple(reason for reason in result.unknown_reasons
                        if not reason.startswith(("task_termination_not_guaranteed:", "task_cancellation_unmodeled:",
                                                  "task_rejection_continuation_unknown:"))))
                selected = check_invariants(program, sliced, (), timeout_ms=timeout_ms,
                                            executor_contracts=executor_contracts)
                scope = slice_name
                family_id = None
                if task_exit is not None:
                    scope += f":{task_exit.task_id}:{task_exit.kind}"
                    instance_id = bindings[task_exit.task_id].instance_id
                    family_id = next(item.family_id for item in program.instances if item.instance_id == instance_id)
                for dimension in selected:
                    if dimension.dimension == "item_size_bytes" or family_id is not None and dimension.resource_family_id != family_id:
                        continue
                    output.append(replace(dimension, scope=scope,
                        assumptions=dimension.assumptions + ("conditional on reaching the recorded exit slice; termination is not guaranteed",),
                        evidence_ids=tuple(sorted(set(dimension.evidence_ids) | (
                            set(task_exit.evidence_ids) | set(bindings[task_exit.task_id].evidence_ids) if task_exit else set()
                        )))))
    return tuple(output)
