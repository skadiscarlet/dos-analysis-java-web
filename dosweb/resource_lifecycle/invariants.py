from __future__ import annotations

from dataclasses import dataclass, replace
import time
from typing import Literal

from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.models import (
    AnalysisResult,
    CountInterval,
    DimensionResult,
    Effect,
    PopulationEffect,
    Program,
    PropertyPathResult,
    SOURCE_KINDS,
    SourceLocation,
    TaskBinding,
    TaskExit,
    Transition,
)
from dosweb.resource_lifecycle.solver import merge_states


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


@dataclass(frozen=True)
class PopulationTransitionEquation:
    transition_id: str
    effect_id: str
    task_id: str
    kind: str
    equation: str
    guard: str
    source_phase: str
    target_phase: str
    preserves_bounds: bool
    evidence_ids: tuple[str, ...]
    location: SourceLocation


@dataclass(frozen=True)
class PopulationProperty:
    property_id: str
    dimension: Literal["accepted_task_population"]
    scope: str
    initial_state: tuple[tuple[str, int], ...]
    queue_upper_bound: int | None
    active_upper_bound: int | None
    total_upper_bound: int | None
    transition_equations: tuple[PopulationTransitionEquation, ...]
    guards: tuple[str, ...]
    repeat_assumption: str
    initial_holds: bool
    transitions_preserve: bool
    covers_writers: bool
    lifecycle_status: Literal["bounded", "unknown"]
    assumptions: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    unknown_reasons: tuple[str, ...]
    transition_ids: tuple[str, ...]
    model_only: bool


@dataclass(frozen=True)
class ModelCountEffect:
    effect_id: str
    kind: Literal[
        "insert_fresh",
        "replace_fixed_position",
        "retain_same_object",
    ]
    container_id: str
    object_id: str
    slot_id: str | None
    identity_relation: Literal["fresh", "same", "unknown"]
    source_kind: Literal["manual_fixture"]
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(
            not isinstance(item, str) or not item
            for item in (self.effect_id, self.container_id, self.object_id)
        ):
            raise ValueError("model count effect identity is required")
        if self.kind not in {
            "insert_fresh",
            "replace_fixed_position",
            "retain_same_object",
        }:
            raise ValueError("model count effect kind is invalid")
        if self.identity_relation not in {"fresh", "same", "unknown"}:
            raise ValueError("model count identity relation is invalid")
        if self.kind == "replace_fixed_position":
            if not isinstance(self.slot_id, str) or not self.slot_id:
                raise ValueError("fixed replacement requires a slot identity")
        elif self.slot_id is not None:
            raise ValueError("non-replacement count effect cannot declare a slot")
        if self.source_kind != "manual_fixture":
            raise ValueError("model count effects must be explicitly model-only")
        if not self.evidence_ids or any(
            not isinstance(item, str) or not item for item in self.evidence_ids
        ):
            raise ValueError("model count effect requires evidence")


@dataclass(frozen=True)
class ModelCountProperty:
    effect_id: str
    dimension: Literal["distinct_instances", "occupied_positions"]
    scope: str
    relation: str | None
    repeat_assumption: str
    lifecycle_status: Literal["proven", "unknown"]
    assumptions: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    unknown_reasons: tuple[str, ...]
    source_kind: Literal["manual_fixture"]
    model_only: bool = True


_POPULATION_EQUATIONS: dict[str, str] = {
    "direct_accept": "q'=q, a'=a+1",
    "enqueue": "q'=q+1, a'=a",
    "assign_slot": "q'=q-1, a'=a+1",
    "start": "q'=q, a'=a",
    "terminate": "q'=q, a'=a-1",
    "reject": "q'=q, a'=a",
    "cancel_queued": "q'=q-1, a'=a",
    "cancel_active": "q'=q, a'=a-1",
}
_POPULATION_RAW_GUARDS: dict[str, str] = {
    "direct_accept": "a<C or (q>=K and a<W)",
    "enqueue": "q<K",
    "assign_slot": "q>0 and a<W",
    "start": "reserved",
    "terminate": "a>0",
    "reject": "queue_or_workers_full",
    "cancel_queued": "queued",
    "cancel_active": "running",
}


def _numeric_limit(value: int | str | None) -> int | None:
    if type(value) is int:
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _population_config_reasons(contract: ExecutorContract) -> tuple[str, ...]:
    reasons: list[str] = []
    capacity = _numeric_limit(contract.queue_capacity)
    core_workers = _numeric_limit(contract.core_workers)
    max_workers = _numeric_limit(contract.max_workers)
    if contract.source_kind not in {
        "static_verified",
        "trusted_contract",
        "manual_fixture",
    }:
        reasons.append("untrusted_executor_contract_source")
    if contract.scheduling != "queued":
        reasons.append("queue_scheduling_contract_mismatch")
    if capacity is None or capacity <= 0:
        reasons.append("executor_queue_capacity_unknown")
    if core_workers is None or core_workers < 0:
        reasons.append("executor_core_workers_unknown")
    if max_workers is None or max_workers <= 0:
        reasons.append("executor_max_workers_unknown")
    if (
        core_workers is not None
        and max_workers is not None
        and core_workers > max_workers
    ):
        reasons.append("executor_worker_limits_invalid")
    if not contract.capacity_atomic:
        reasons.append("capacity_not_atomic")
    if contract.rejection_policy == "caller_runs":
        reasons.append("caller_runs_population_unmodeled")
    elif contract.rejection_policy in {"discard_oldest", "unknown"}:
        reasons.append("executor_rejection_policy_unmodeled")
    return tuple(sorted(set(reasons)))


def _population_transition_equation(
    transition_id: str,
    effect: PopulationEffect,
    *,
    preserves_bounds: bool,
) -> PopulationTransitionEquation:
    equation = _POPULATION_EQUATIONS[effect.kind]
    return PopulationTransitionEquation(
        transition_id,
        effect.effect_id,
        effect.task_id,
        effect.kind,
        equation,
        effect.guard,
        effect.source_phase,
        effect.target_phase,
        preserves_bounds,
        effect.evidence_ids,
        effect.location,
    )


def _expected_population_guard(effect: PopulationEffect) -> str:
    if effect.kind == "cancel_active":
        return effect.source_phase
    return _POPULATION_RAW_GUARDS[effect.kind]


def _population_effect_preserves(
    transition_id: str,
    effect: PopulationEffect,
    contract: ExecutorContract,
    *,
    capacity: int | None,
    core_workers: int | None,
    max_workers: int | None,
    ambiguous_transition_ids: frozenset[str],
) -> bool:
    if (
        transition_id in ambiguous_transition_ids
        or effect.guard != _expected_population_guard(effect)
        or contract.source_kind
        not in {"static_verified", "trusted_contract", "manual_fixture"}
        or contract.scheduling != "queued"
        or not contract.capacity_atomic
        or contract.rejection_policy not in {"abort", "discard"}
        or capacity is None
        or capacity <= 0
        or core_workers is None
        or core_workers < 0
        or max_workers is None
        or max_workers <= 0
        or core_workers > max_workers
    ):
        return False
    if effect.kind == "direct_accept":
        return 0 <= core_workers <= max_workers
    if effect.kind == "enqueue":
        return capacity > 0
    if effect.kind == "assign_slot":
        return capacity > 0 and max_workers > 0
    if effect.kind in {
        "start",
        "terminate",
        "reject",
        "cancel_queued",
        "cancel_active",
    }:
        return True
    return False


def check_population_properties(
    program: Program,
    executor_contracts: tuple[ExecutorContract, ...],
    invariant_candidates: tuple[InvariantCandidate, ...] = (),
    *,
    timeout_ms: int | None = None,
) -> tuple[PopulationProperty, ...]:
    """Prove the bounded q/a executor template over arbitrary event repetition."""
    if timeout_ms is not None and timeout_ms < 0:
        raise ValueError("timeout_ms must be non-negative")
    deadline = (
        None
        if timeout_ms is None
        else time.monotonic() + timeout_ms / 1000.0
    )

    def timed_out() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    contracts = {item.contract_id: item for item in executor_contracts}
    if len(contracts) != len(executor_contracts):
        raise ValueError("duplicate executor contract identifier")
    bindings_by_contract: dict[str, list[TaskBinding]] = {
        contract_id: [] for contract_id in contracts
    }
    for binding in program.task_bindings:
        bindings_by_contract.setdefault(binding.executor_contract_id, []).append(binding)
    bindings_by_dispatch_identity: dict[
        tuple[str, str, str, str], list[TaskBinding]
    ] = {}
    for binding in program.task_bindings:
        for target_event_id in (binding.queued_event_id, binding.run_event_id):
            bindings_by_dispatch_identity.setdefault(
                (
                    binding.executor_contract_id,
                    binding.instance_id,
                    binding.holder_id,
                    target_event_id,
                ),
                [],
            ).append(binding)
    unknown_contracts = set(bindings_by_contract) - set(contracts)
    instances = {item.instance_id: item for item in program.instances}
    families = {item.family_id: item for item in program.families}
    events = {item.event_id: item for item in program.events}
    points = {item.point_id: item for item in program.program_points}
    transitions_by_target: dict[str, list[Transition]] = {}
    task_exits_by_task_kind: dict[str, dict[str, list[TaskExit]]] = {}
    terminal_transition_ids_by_exit: dict[str, set[str]] = {}
    retains_by_holder: dict[str, list[Effect]] = {}
    dispatches_by_contract: dict[str | None, list[Effect]] = {}
    dispatches_by_holder: dict[str | None, list[Effect]] = {}
    dispatches_by_target: dict[str | None, list[Effect]] = {}
    population_counts: dict[tuple[str, str], int] = {}
    for task_exit in program.task_exits:
        task_exits_by_task_kind.setdefault(task_exit.task_id, {}).setdefault(
            task_exit.kind, []
        ).append(task_exit)
    effects_by_contract: dict[
        str, list[tuple[str, PopulationEffect]]
    ] = {contract_id: [] for contract_id in contracts}
    for transition in program.transitions:
        transitions_by_target.setdefault(transition.target_event_id, []).append(
            transition
        )
        source = events[transition.source_event_id]
        source_point = points.get(source.activation_condition)
        for effect in transition.population_effects:
            effects_by_contract.setdefault(effect.executor_id, []).append(
                (transition.transition_id, effect)
            )
            identity = (transition.transition_id, effect.executor_id)
            population_counts[identity] = population_counts.get(identity, 0) + 1
            if effect.kind == "terminate" and source_point is not None:
                for task_exit in task_exits_by_task_kind.get(
                    effect.task_id, {}
                ).get(transition.exit_kind, ()):
                    if (
                        transition.target_event_id == task_exit.event_id
                        and source_point.point_id == task_exit.point_id
                    ):
                        terminal_transition_ids_by_exit.setdefault(
                            task_exit.exit_id, set()
                        ).add(transition.transition_id)
        for effect in transition.effects:
            if effect.kind == "retain":
                retains_by_holder.setdefault(effect.holder_id or "", []).append(
                    effect
                )
            elif effect.kind == "dispatch":
                dispatches_by_contract.setdefault(effect.contract_id, []).append(
                    effect
                )
                dispatches_by_holder.setdefault(effect.holder_id, []).append(effect)
                dispatches_by_target.setdefault(effect.target_event_id, []).append(
                    effect
                )
    ambiguous_transitions_by_contract: dict[str, frozenset[str]] = {}
    for transition_id, executor_id in population_counts:
        if population_counts[(transition_id, executor_id)] > 1:
            ambiguous_transitions_by_contract.setdefault(
                executor_id, frozenset()
            )
    for executor_id in tuple(ambiguous_transitions_by_contract):
        ambiguous_transitions_by_contract[executor_id] = frozenset(
            transition_id
            for (transition_id, candidate_executor_id), count in population_counts.items()
            if candidate_executor_id == executor_id and count > 1
        )
    properties: list[PopulationProperty] = []
    for contract_id, contract in sorted(contracts.items()):
        bindings = tuple(
            sorted(bindings_by_contract.get(contract_id, ()), key=lambda item: item.task_id)
        )
        effects = tuple(
            sorted(
                effects_by_contract.get(contract_id, ()),
                key=lambda item: (item[0], item[1].effect_id),
            )
        )
        family_ids = {
            instances[binding.instance_id].family_id for binding in bindings
        }
        binding_model_only = any(
            families[family_id].allocation.source_kind == "manual_fixture"
            for family_id in family_ids
        )
        bound_targets_by_holder: dict[str, set[str]] = {}
        for binding in bindings:
            bound_targets_by_holder.setdefault(binding.holder_id, set()).update(
                (binding.queued_event_id, binding.run_event_id)
            )
        unmodeled_retain_writers: list[Effect] = []
        unmodeled_dispatch_writers: list[Effect] = []
        reasons = list(_population_config_reasons(contract))
        if timed_out():
            reasons.append("population_solver_timeout")
        capacity = _numeric_limit(contract.queue_capacity)
        core_workers = _numeric_limit(contract.core_workers)
        max_workers = _numeric_limit(contract.max_workers)
        config_proven = not any(
            reason.startswith("executor_")
            or reason in {"capacity_not_atomic", "queue_scheduling_contract_mismatch"}
            for reason in reasons
        )
        if not bindings:
            reasons.append("executor_population_binding_unavailable")
        ambiguous_transition_ids = ambiguous_transitions_by_contract.get(
            contract_id, frozenset()
        )
        reasons.extend(
            f"population_transition_effects_ambiguous:{transition_id}"
            for transition_id in sorted(ambiguous_transition_ids)
        )
        for _transition_id, effect in effects:
            if effect.guard != _expected_population_guard(effect):
                reasons.append(f"population_guard_unverified:{effect.effect_id}")
        effects_by_task: dict[str, dict[str, list[tuple[str, PopulationEffect]]]] = {}
        for transition_id, effect in effects:
            effects_by_task.setdefault(effect.task_id, {}).setdefault(
                effect.kind, []
            ).append((transition_id, effect))
        coverage_complete = True
        for binding in bindings:
            by_kind = effects_by_task.get(binding.task_id, {})
            for kind in ("direct_accept", "enqueue", "assign_slot", "start"):
                if len(by_kind.get(kind, ())) != 1:
                    coverage_complete = False
                    suffix = "missing" if not by_kind.get(kind) else "ambiguous"
                    reasons.append(
                        f"population_transition_{suffix}:{binding.task_id}:{kind}"
                    )
            if contract.rejection_policy in {"abort", "discard"}:
                if len(by_kind.get("reject", ())) != 1:
                    coverage_complete = False
                    suffix = "missing" if not by_kind.get("reject") else "ambiguous"
                    reasons.append(
                        f"population_transition_{suffix}:{binding.task_id}:reject"
                    )
            exits_by_kind = task_exits_by_task_kind.get(binding.task_id, {})
            task_exits = tuple(
                task_exit
                for kind in sorted(exits_by_kind)
                for task_exit in exits_by_kind[kind]
            )
            for expected_kind in ("normal", "exceptional"):
                matching_exits = exits_by_kind.get(expected_kind, ())
                if not matching_exits:
                    coverage_complete = False
                    reasons.append(
                        f"population_task_exit_missing:{binding.task_id}:"
                        f"{expected_kind}"
                    )
            for task_exit in task_exits:
                matching = terminal_transition_ids_by_exit.get(
                    task_exit.exit_id, set()
                )
                if len(matching) != 1:
                    coverage_complete = False
                    suffix = "missing" if not matching else "ambiguous"
                    reasons.append(
                        f"population_transition_{suffix}:{binding.task_id}:"
                        f"terminate:{task_exit.kind}:{task_exit.exit_id}"
                    )
            cancellation_edges = tuple(
                transitions_by_target.get(binding.cancelled_event_id, ())
            )
            for transition in cancellation_edges:
                matching_cancellation = tuple(
                    effect
                    for effect in transition.population_effects
                    if effect.task_id == binding.task_id
                    and effect.executor_id == contract_id
                    and effect.kind in {"cancel_queued", "cancel_active"}
                )
                if len(matching_cancellation) != 1:
                    coverage_complete = False
                    suffix = "missing" if not matching_cancellation else "ambiguous"
                    reasons.append(
                        f"population_cancellation_effect_{suffix}:"
                        f"{binding.task_id}:{transition.transition_id}"
                    )
        relevant_writers: set[Effect] = set(
            dispatches_by_contract.get(contract_id, ())
        )
        for binding in bindings:
            for writer in retains_by_holder.get(binding.holder_id, ()):
                relevant_writers.add(writer)
            for writer in dispatches_by_holder.get(binding.holder_id, ()):
                writer_family_id = (
                    instances[writer.instance_id].family_id
                    if writer.instance_id is not None
                    else writer.family_id
                )
                if writer_family_id is None or writer_family_id in family_ids:
                    relevant_writers.add(writer)
            for target_event_id in (
                binding.queued_event_id,
                binding.run_event_id,
            ):
                relevant_writers.update(
                    dispatches_by_target.get(target_event_id, ())
                )
        for writer in sorted(
            relevant_writers, key=lambda item: (item.effect_id, repr(item))
        ):
            writer_family_id = (
                instances[writer.instance_id].family_id
                if writer.instance_id is not None
                else writer.family_id
            )
            if (
                writer.kind == "retain"
                and writer_family_id in family_ids
                and writer.holder_id in bound_targets_by_holder
            ):
                coverage_complete = False
                unmodeled_retain_writers.append(writer)
                reasons.append(
                    "population_retain_writer_unmodeled:"
                    f"{writer.effect_id}"
                )
                continue
            if writer.kind != "dispatch":
                continue
            matching_bindings = (
                tuple(
                    bindings_by_dispatch_identity.get(
                        (
                            contract_id,
                            writer.instance_id or "",
                            writer.holder_id or "",
                            writer.target_event_id or "",
                        ),
                        (),
                    )
                )
                if writer.contract_id == contract_id
                else ()
            )
            if len(matching_bindings) != 1:
                coverage_complete = False
                unmodeled_dispatch_writers.append(writer)
                reasons.append(
                    "population_dispatch_binding_unavailable:"
                    f"{writer.effect_id}"
                )
        if timed_out():
            coverage_complete = False
            reasons.append("population_solver_timeout")
        queue_scopes = {
            queue_result_scope(
                binding.executor_contract_id,
                binding.holder_id,
                binding.queued_event_id,
            )
            for binding in bindings
        }
        selected_gaps = tuple(
            item
            for item in program.coverage_gaps
            if item[0] == "held_instances" and item[1] in family_ids
            and item[2] in {"*", *queue_scopes}
        )
        if not program.coverage_complete and not program.coverage_gaps:
            coverage_complete = False
            reasons.append("population_coverage_incomplete")
        if selected_gaps:
            coverage_complete = False
            reasons.extend(item[3] for item in selected_gaps)
        equations = tuple(
            _population_transition_equation(
                transition_id,
                effect,
                preserves_bounds=_population_effect_preserves(
                    transition_id,
                    effect,
                    contract,
                    capacity=capacity,
                    core_workers=core_workers,
                    max_workers=max_workers,
                    ambiguous_transition_ids=ambiguous_transition_ids,
                ),
            )
            for transition_id, effect in effects
        )
        if timed_out():
            coverage_complete = False
            reasons.append("population_solver_timeout")
        initial_holds = bool(
            config_proven
            and capacity is not None
            and max_workers is not None
            and core_workers is not None
        )
        transitions_preserve = bool(
            initial_holds
            and equations
            and all(item.preserves_bounds for item in equations)
        )
        covers_writers = bool(bindings and coverage_complete)
        lifecycle_status: Literal["bounded", "unknown"] = (
            "bounded"
            if initial_holds and transitions_preserve and covers_writers and not reasons
            else "unknown"
        )
        evidence = {contract_id}
        evidence.update(
            evidence_id
            for binding in bindings
            for evidence_id in binding.evidence_ids
        )
        evidence.update(
            evidence_id
            for _transition_id, effect in effects
            for evidence_id in effect.evidence_ids
        )
        evidence.update(
            evidence_id
            for writer in relevant_writers
            for evidence_id in writer.evidence_ids
        )
        evidence.update(
            evidence_id
            for candidate in invariant_candidates
            if candidate.scope == "task_queue"
            and candidate.executor_contract_id == contract_id
            and candidate.upper_bound == contract.queue_capacity
            and candidate.source_kind in {"static_verified", "trusted_contract"}
            for evidence_id in candidate.evidence_ids
        )
        evidence.update(item[4] for item in selected_gaps)
        assumptions = (
            "q counts accepted tasks in the modeled executor queue",
            "a counts reserved or running tasks in the modeled executor",
            "each external acceptance denotes a fresh task population member",
            "task phase changes do not create a second population member",
            "derived invariants: 0 <= q <= K, 0 <= a <= W, q + a <= K + W",
            "proof is inductive for arbitrary finite repetitions, not one unrolling",
        )
        properties.append(
            PopulationProperty(
                f"population:{contract_id}",
                "accepted_task_population",
                f"executor:{contract_id}",
                (("q", 0), ("a", 0)),
                capacity if capacity is not None and capacity > 0 else None,
                max_workers if max_workers is not None and max_workers > 0 else None,
                (
                    capacity + max_workers
                    if capacity is not None
                    and capacity > 0
                    and max_workers is not None
                    and max_workers > 0
                    else None
                ),
                equations,
                tuple(dict.fromkeys(item.guard for item in equations)),
                "arbitrary_finite_repetitions_of_external_accept",
                initial_holds,
                transitions_preserve,
                covers_writers,
                lifecycle_status,
                assumptions,
                tuple(sorted(evidence)),
                tuple(sorted(set(reasons))),
                tuple(dict.fromkeys(item.transition_id for item in equations)),
                contract.source_kind == "manual_fixture"
                or binding_model_only
                or any(
                    effect.location.source_kind == "manual_fixture"
                    for _transition_id, effect in effects
                ),
            )
        )
    for contract_id in sorted(unknown_contracts):
        bindings = tuple(
            sorted(bindings_by_contract[contract_id], key=lambda item: item.task_id)
        )
        effects = tuple(
            sorted(
                effects_by_contract.get(contract_id, ()),
                key=lambda item: (item[0], item[1].effect_id),
            )
        )
        family_ids = {
            instances[binding.instance_id].family_id for binding in bindings
        }
        binding_model_only = any(
            families[family_id].allocation.source_kind == "manual_fixture"
            for family_id in family_ids
        )
        evidence = {
            evidence_id
            for binding in bindings
            for evidence_id in binding.evidence_ids
        }
        evidence.update(
            evidence_id
            for _transition_id, effect in effects
            for evidence_id in effect.evidence_ids
        )
        equations = tuple(
            _population_transition_equation(
                transition_id,
                effect,
                preserves_bounds=False,
            )
            for transition_id, effect in effects
        )
        properties.append(
            PopulationProperty(
                f"population:{contract_id}",
                "accepted_task_population",
                f"executor:{contract_id}",
                (("q", 0), ("a", 0)),
                None,
                None,
                None,
                equations,
                tuple(dict.fromkeys(item.guard for item in equations)),
                "arbitrary_finite_repetitions_of_external_accept",
                False,
                False,
                False,
                "unknown",
                ("executor contract is required for population induction",),
                tuple(sorted(evidence)),
                ("executor_contract_unavailable",),
                tuple(dict.fromkeys(item.transition_id for item in equations)),
                binding_model_only
                or any(
                    effect.location.source_kind == "manual_fixture"
                    for _transition_id, effect in effects
                ),
            )
        )
    return tuple(sorted(properties, key=lambda item: item.scope))


def check_model_count_effects(
    effects: tuple[ModelCountEffect, ...],
) -> tuple[ModelCountProperty, ...]:
    output: list[ModelCountProperty] = []
    for effect in effects:
        relation: str | None = None
        reasons: list[str] = []
        assumptions: tuple[str, ...] = ()
        dimension: Literal["distinct_instances", "occupied_positions"] = (
            "occupied_positions"
            if effect.kind == "replace_fixed_position"
            else "distinct_instances"
        )
        if effect.identity_relation == "unknown":
            reasons.append("model_object_identity_unknown")
        elif effect.kind == "insert_fresh":
            if effect.identity_relation != "fresh":
                reasons.append("model_freshness_not_proven")
            else:
                relation = "N'=N+1"
                assumptions = ("inserted object is distinct from every counted instance",)
        elif effect.kind == "replace_fixed_position":
            relation = "N'=N"
            assumptions = (
                "the fixed position was already occupied",
                "replacement changes the referenced object but not the position count",
            )
        elif effect.kind == "retain_same_object":
            if effect.identity_relation != "same":
                reasons.append("model_same_object_identity_not_proven")
            else:
                relation = "N'=N"
                assumptions = ("the added reference aliases an already counted object",)
        output.append(
            ModelCountProperty(
                effect.effect_id,
                dimension,
                f"model_only:{effect.container_id}",
                relation,
                "arbitrary_finite_repetitions",
                "proven" if relation is not None and not reasons else "unknown",
                assumptions,
                effect.evidence_ids,
                tuple(sorted(set(reasons))),
                effect.source_kind,
            )
        )
    return tuple(output)


def canonical_model_count_effects() -> tuple[ModelCountEffect, ...]:
    """Return the fixed, explicitly model-only repetition contrasts."""
    return (
        ModelCountEffect(
            "model:fresh",
            "insert_fresh",
            "container:list",
            "object:new",
            None,
            "fresh",
            "manual_fixture",
            ("model-fact:fresh-insert",),
        ),
        ModelCountEffect(
            "model:replace",
            "replace_fixed_position",
            "container:slot",
            "object:replacement",
            "slot:0",
            "fresh",
            "manual_fixture",
            ("model-fact:fixed-replacement",),
        ),
        ModelCountEffect(
            "model:alias",
            "retain_same_object",
            "container:aliases",
            "object:existing",
            None,
            "same",
            "manual_fixture",
            ("model-fact:same-object-retain",),
        ),
    )


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
        queue_bindings = tuple(
            binding
            for binding in program.task_bindings
            if instances[binding.instance_id].family_id == candidate.family_id
            and binding.holder_id == candidate.writer_holder_id
            and binding.queued_event_id == candidate.writer_target_event_id
            and binding.executor_contract_id == candidate.executor_contract_id
        )
        if not queue_bindings:
            related = tuple(
                binding
                for binding in program.task_bindings
                if instances[binding.instance_id].family_id == candidate.family_id
            )
            if any(
                binding.holder_id == candidate.writer_holder_id
                and binding.queued_event_id == candidate.writer_target_event_id
                for binding in related
            ):
                return ("queue_writer_contract_mismatch",)
            if related:
                return ("queue_writer_identity_mismatch",)
            return ("queue_writer_structure_unverified",)
        target = events.get(candidate.writer_target_event_id or "")
        holder = holders.get(candidate.writer_holder_id or "")
        if (
            target is None
            or target.kind != "task_queue"
            or holder is None
            or holder.kind != "task"
        ):
            return ("queue_writer_structure_unverified",)
        return ()

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


def _check_candidate(
    candidate: InvariantCandidate,
    program: Program,
    result: AnalysisResult,
    population_properties: dict[str, PopulationProperty],
) -> DimensionResult:
    reasons: list[str] = []
    if candidate.source_kind not in {"static_verified", "trusted_contract"}:
        reasons.append("untrusted_invariant_source")
    population_property = None
    if candidate.scope == "task_queue":
        population_property = population_properties.get(
            candidate.executor_contract_id or ""
        )
        if population_property is None:
            reasons.append("population_model_unavailable")
        else:
            reasons.extend(population_property.unknown_reasons)
            if population_property.lifecycle_status != "bounded":
                reasons.append("population_induction_unproven")
            if candidate.upper_bound != population_property.queue_upper_bound:
                reasons.append("queue_capacity_contract_mismatch")
    else:
        reasons.append("derived_invariant_model_unavailable")
    peak, peak_reasons = _observed_peak(candidate, result)
    reasons.extend(peak_reasons)
    observed_bound = (
        population_property.total_upper_bound
        if candidate.scope == "task_queue" and population_property is not None
        else candidate.upper_bound
    )
    if isinstance(observed_bound, int) and peak is not None:
        if peak > observed_bound:
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
                    .union(
                        population_property.evidence_ids
                        if population_property is not None
                        else ()
                    )
                    .union(coverage_evidence)
                    .union(_precision_evidence(program, precision_reasons, candidate.family_id))
                )
            ),
            candidate.family_id,
        )
    assumptions = (
        population_property.assumptions
        + (f"repeat assumption: {population_property.repeat_assumption}",)
        if population_property is not None
        else candidate.assumptions
    )
    upper_bound = (
        population_property.total_upper_bound
        if population_property is not None
        else candidate.upper_bound
    )
    if isinstance(upper_bound, str):
        assert peak is not None
        assumptions = tuple(
            dict.fromkeys(
                assumptions
                + (
                    f"symbolic upper bound {upper_bound} is finite and positive",
                    f"{upper_bound} >= observed peak {peak}",
                )
            )
        )
    return DimensionResult(
        candidate.dimension,
        candidate_result_scope(candidate),
        "bounded",
        upper_bound,
        assumptions=assumptions,
        evidence_ids=tuple(
            sorted(
                set(candidate.evidence_ids).union(
                    population_property.evidence_ids
                    if population_property is not None
                    else ()
                )
            )
        ),
        resource_family_id=candidate.family_id,
        transition_ids=(
            population_property.transition_ids
            if population_property is not None
            else ()
        ),
    )


def check_invariants_with_population(
    program: Program,
    result: AnalysisResult,
    candidates: tuple[InvariantCandidate, ...],
    *,
    timeout_ms: int,
    executor_contracts: tuple[ExecutorContract, ...] = (),
) -> tuple[tuple[DimensionResult, ...], tuple[PopulationProperty, ...]]:
    if timeout_ms < 0:
        raise ValueError("timeout_ms must be non-negative")
    family_ids = {item.family_id for item in program.families}
    if any(item.family_id not in family_ids for item in candidates):
        raise ValueError("invariant references an unknown resource family")
    contracts = {item.contract_id: item for item in executor_contracts}
    if len(contracts) != len(executor_contracts):
        raise ValueError("duplicate executor contract identifier")
    derived_population_properties = check_population_properties(
        program,
        executor_contracts,
        candidates,
        timeout_ms=timeout_ms,
    )
    dimensions = _check_invariants_from_population(
        program,
        result,
        candidates,
        timeout_ms=timeout_ms,
        population_properties=derived_population_properties,
    )
    return dimensions, derived_population_properties


def _check_invariants_from_population(
    program: Program,
    result: AnalysisResult,
    candidates: tuple[InvariantCandidate, ...],
    *,
    timeout_ms: int,
    population_properties: tuple[PopulationProperty, ...],
    allow_exact_population_cut: bool = False,
) -> tuple[DimensionResult, ...]:
    """Check dimensions while reusing internally derived population proofs."""
    if timeout_ms == 0:
        return tuple(
            _unknown(
                dimension,
                "analysis",
                ("solver_timeout",),
                family_id=resource.family_id,
            )
            for resource in sorted(program.families, key=lambda item: item.family_id)
            for dimension in (
                "held_instances",
                "item_size_bytes",
                "close_obligation",
            )
        )
    population_properties_by_contract = {
        item.scope.removeprefix("executor:"): item
        for item in population_properties
    }

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
                _check_candidate(
                    candidate,
                    program,
                    result,
                    population_properties_by_contract,
                )
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
            elif (allow_exact_population_cut and held and not count_reasons
                  and result.terminated and result.exit_states
                  and all(item.abstraction == "recent" and item.identity_confidence == "exact"
                          for item in program.instances if item.family_id == resource.family_id)
                  and all(not (state.repeated_instances & family_instances)
                          and dict(state.allocation_counts).get(resource.family_id, CountInterval()).upper is not None
                          and dict(state.held_counts).get(resource.family_id, CountInterval()).upper is not None
                          and dict(state.held_counts).get(resource.family_id, CountInterval()).upper
                              <= dict(state.allocation_counts).get(resource.family_id, CountInterval()).upper
                          for state in result.exit_states.values())):
                # An exhausted abstract worklist with exact, non-repeated
                # allocation identities proves a finite per-invocation cut.
                # It is not an executor population/repeated-request bound.
                upper = max(dict(state.held_counts)[resource.family_id].upper
                            for state in result.exit_states.values())
                evidence = _family_effect_evidence(program, resource.family_id,
                    frozenset({"create", "retain", "drop", "dispatch"}))
                output.append(DimensionResult("held_instances", "all_exits", "bounded", upper,
                    assumptions=("per_invocation_exact_allocation_population",),
                    evidence_ids=evidence, resource_family_id=resource.family_id))
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
            groups = ([tuple(sorted(exit_states))] if slice_name == "all_tasks_terminated_after_request" and exit_states
                      else [(event_id,) for event_id in sorted(exit_states)])
            for event_ids in groups:
                task_exit = task_exit_by_event.get(event_ids[0]) if len(event_ids) == 1 else None
                scope = slice_name
                family_id = None
                if task_exit is not None:
                    scope += f":{task_exit.task_id}:{task_exit.kind}"
                    instance_id = bindings[task_exit.task_id].instance_id
                    family_id = next(item.family_id for item in program.instances if item.instance_id == instance_id)
                records = []
                incomplete = False
                for event_id in event_ids:
                    paths = result.property_derivations.get(slice_name, {}).get(event_id, ())
                    traces = result.property_traces.get(slice_name, {}).get(event_id, ())
                    if (not paths or any(item.property_event_id != event_id for item in paths)
                            or tuple(item.trace for item in paths) != traces
                            or merge_states(tuple(item.state for item in paths)) != exit_states[event_id]):
                        incomplete = True
                    records.extend(enumerate(paths))
                # A recorded exit of this exact task does not require a future
                # queue-consumer progress guarantee. Exclude only that scoped
                # liveness gap; wildcard, other-task and precision gaps remain.
                conditional_program = program
                if task_exit is not None:
                    binding = bindings[task_exit.task_id]
                    consumed_scope = queue_result_scope(
                        binding.executor_contract_id, binding.holder_id, binding.queued_event_id
                    )
                    remaining_gaps = tuple(gap for gap in program.coverage_gaps if not (
                        gap[0] == "close_obligation" and gap[1] == family_id
                        and gap[2] == consumed_scope and gap[3] == "async_consumer_contract_unmodeled"
                    ))
                    if remaining_gaps != program.coverage_gaps:
                        conditional_program = replace(program, coverage_gaps=remaining_gaps,
                                                      coverage_complete=not remaining_gaps)
                path_results: dict[tuple[str, str], list[PropertyPathResult]] = {}
                path_assumptions: dict[tuple[str, str], set[str]] = {}
                for path_index, record in records:
                    sliced = replace(result, exit_states={record.property_event_id: record.state}, property_states={},
                        unknown_reasons=tuple(reason for reason in result.unknown_reasons
                            if not reason.startswith(("task_termination_not_guaranteed:", "task_cancellation_unmodeled:",
                                                      "task_rejection_continuation_unknown:"))))
                    selected = _check_invariants_from_population(
                        conditional_program,
                        sliced,
                        (),
                        timeout_ms=timeout_ms,
                        population_properties=population_properties,
                        allow_exact_population_cut=slice_name in {
                            "after_task_termination", "all_tasks_terminated_after_request"
                        },
                    )
                    for dimension in selected:
                        if (dimension.dimension == "item_size_bytes"
                                or family_id is not None and dimension.resource_family_id != family_id):
                            continue
                        _, coverage_evidence = _coverage_details(program, dimension.dimension, dimension.resource_family_id)
                        evidence = set(record.trace.evidence_ids) | set(coverage_evidence) | {dimension.resource_family_id}
                        evidence.update(item.instance_id for item in program.instances
                                        if item.family_id == dimension.resource_family_id)
                        if task_exit is not None:
                            # The path trace carries the exact reached TaskExit.
                            # An event may represent several same-kind returns;
                            # choosing one from the event lookup would mix them.
                            evidence.update(bindings[task_exit.task_id].evidence_ids)
                        path_assumptions.setdefault((dimension.dimension, dimension.resource_family_id), set()).update(dimension.assumptions)
                        path_results.setdefault((dimension.dimension, dimension.resource_family_id), []).append(
                            PropertyPathResult(record.property_event_id, path_index, record.trace, dimension.lifecycle_status,
                                               dimension.upper_bound, dimension.reason_codes, tuple(sorted(evidence))))
                for resource in sorted(program.families, key=lambda item: item.family_id):
                    if family_id is not None and resource.family_id != family_id:
                        continue
                    for dimension in ("held_instances", "close_obligation"):
                        paths = tuple(path_results.get((dimension, resource.family_id), ()))
                        statuses = {path.lifecycle_status for path in paths}
                        reasons = {reason for path in paths for reason in path.reason_codes}
                        evidence = {item for path in paths for item in path.evidence_ids} | {resource.family_id}
                        if incomplete or not paths:
                            status, upper = "unknown", None
                            reasons.add("property_path_evidence_incomplete")
                        elif "unknown" in statuses:
                            status, upper = "unknown", None
                        elif "obligation_gap" in statuses:
                            status, upper = "obligation_gap", None
                        elif statuses == {"not_applicable"}:
                            status, upper = "not_applicable", 0
                        elif statuses <= {"bounded", "not_applicable"} and all(type(path.upper_bound) is int for path in paths):
                            status, upper = "bounded", max(path.upper_bound for path in paths)
                        else:
                            status, upper = "unknown", None
                            reasons.add("property_path_bound_aggregation_unknown")
                        output.append(DimensionResult(dimension, scope, status, upper,
                            assumptions=("conditional on reaching the recorded exit slice; termination is not guaranteed",
                                         "result aggregates independently checked recorded derivations, not a concrete merged trace")
                                        + tuple(sorted(path_assumptions.get((dimension, resource.family_id), ()))),
                            reason_codes=tuple(sorted(reasons)), evidence_ids=tuple(sorted(evidence)),
                            resource_family_id=resource.family_id, property_event_ids=event_ids, property_paths=paths))
    identities = [(item.scope, item.dimension, item.resource_family_id) for item in output]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate resource lifecycle dimension identity")
    return tuple(output)


def check_invariants(
    program: Program,
    result: AnalysisResult,
    candidates: tuple[InvariantCandidate, ...],
    *,
    timeout_ms: int,
    executor_contracts: tuple[ExecutorContract, ...] = (),
) -> tuple[DimensionResult, ...]:
    dimensions, _population_properties = check_invariants_with_population(
        program,
        result,
        candidates,
        timeout_ms=timeout_ms,
        executor_contracts=executor_contracts,
    )
    return dimensions
