from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, replace
import time

from dosweb.resource_lifecycle.models import (
    AnalysisBudget,
    AnalysisResult,
    AsyncDerivation,
    PropertyDerivation,
    resolve_task_exit,
    CountInterval,
    Effect,
    Program,
    ResourceState,
    StepResult,
    Trace,
    TaskBinding,
    Transition,
)


def _intervals(values: tuple[tuple[str, CountInterval], ...]) -> dict[str, CountInterval]:
    return dict(values)


def _peaks(values: tuple[tuple[str, int | None], ...]) -> dict[str, int | None]:
    return dict(values)


def _ordered_intervals(values: dict[str, CountInterval]) -> tuple[tuple[str, CountInterval], ...]:
    return tuple(sorted(values.items()))


def _increment(interval: CountInterval, amount: int = 1) -> CountInterval:
    return CountInterval(interval.lower + amount, None if interval.upper is None else interval.upper + amount)


def _decrement(interval: CountInterval, amount: int = 1) -> CountInterval:
    upper = None if interval.upper is None else max(0, interval.upper - amount)
    return CountInterval(max(0, interval.lower - amount), upper)


def initial_state(program: Program) -> ResourceState:
    families = tuple(sorted((item.instance_id, item.family_id) for item in program.instances))
    abstractions = tuple(sorted((item.instance_id, item.abstraction) for item in program.instances))
    confidences = tuple(sorted((item.instance_id, item.identity_confidence) for item in program.instances))
    close = tuple(sorted((item.family_id, item.requires_close) for item in program.families))
    sizes = tuple(sorted((item.family_id, item.item_size_upper) for item in program.families))
    holder_kinds = tuple(sorted((item.holder_id, item.kind) for item in program.holders))
    holder_scopes = tuple(sorted((item.holder_id, item.scope) for item in program.holders))
    holder_precisions = tuple(sorted((item.holder_id, item.identity_precision) for item in program.holders))
    zero = tuple(sorted((item.family_id, CountInterval()) for item in program.families))
    instance_zero = tuple(sorted((item.instance_id, CountInterval()) for item in program.instances))
    peaks = tuple(sorted((item.family_id, 0) for item in program.families))
    return ResourceState(
        families,
        abstractions,
        confidences,
        close,
        sizes,
        holder_kinds,
        holder_scopes,
        holder_precisions,
        instance_obligation_counts=instance_zero,
        obligation_counts=zero,
        allocation_counts=zero,
        held_counts=zero,
        peak_held_counts=peaks,
    )


def apply_effect(state: ResourceState, effect: Effect) -> StepResult:
    families = dict(state.instance_families)
    abstractions = dict(state.instance_abstractions)
    confidences = dict(state.instance_confidences)
    requires_close = dict(state.family_requires_close)
    allocations = _intervals(state.allocation_counts)
    obligations = _intervals(state.obligation_counts)
    instance_obligations = _intervals(state.instance_obligation_counts)
    held_counts = _intervals(state.held_counts)
    peaks = _peaks(state.peak_held_counts)
    held_edges = set(state.held_edges)
    created = set(state.created_instances)
    repeated_instances = set(state.repeated_instances)
    open_obligations = set(state.open_obligations)
    must_released = set(state.must_released)
    unknown = set(state.unknown_reasons)
    rules: list[str] = []
    holder_precisions = dict(state.holder_precisions)

    instance_id = effect.instance_id
    family_id = effect.family_id or (families.get(instance_id) if instance_id is not None else None)

    if effect.kind == "create":
        assert instance_id is not None and family_id is not None
        if instance_id in created:
            # Allocation-site identity is recent only after the previous object
            # has lost every holder and every close obligation. History alone is
            # not multiplicity. Once summarized, never regain strong updates.
            retired = (instance_id not in repeated_instances
                       and not any(edge[0] == instance_id for edge in held_edges)
                       and instance_obligations.get(instance_id, CountInterval()).upper == 0)
            if retired:
                rules.append("create_recycles_retired_recent_instance")
            else:
                repeated_instances.add(instance_id)
                rules.append("create_reuses_abstract_instance")
        created.add(instance_id)
        allocations[family_id] = _increment(allocations.get(family_id, CountInterval()))
        if requires_close.get(family_id, False):
            obligations[family_id] = _increment(obligations.get(family_id, CountInterval()))
            instance_obligations[instance_id] = _increment(
                instance_obligations.get(instance_id, CountInterval())
            )
            open_obligations.add(instance_id)
            must_released.discard(instance_id)
        rules.append("create_instance")
    elif effect.kind == "retain":
        assert instance_id is not None and family_id is not None and effect.holder_id is not None
        already_held = any(edge[0] == instance_id for edge in held_edges)
        held_edges.add((instance_id, effect.holder_id))
        if holder_precisions.get(effect.holder_id) == "unknown":
            unknown.add(f"holder_scope_identity_unknown:{effect.holder_id}")
        if not already_held:
            held_counts[family_id] = _increment(held_counts.get(family_id, CountInterval()))
        elif instance_id in repeated_instances and dict(state.holder_kinds).get(effect.holder_id) != "field":
            prior = held_counts.get(family_id, CountInterval())
            held_counts[family_id] = CountInterval(prior.lower, None)
            unknown.add(f"repeated_abstract_instance:{instance_id}")
            rules.append("retain_repeated_instance_multiplicity")
        current_upper = held_counts[family_id].upper
        prior_peak = peaks.get(family_id, 0)
        peaks[family_id] = None if current_upper is None or prior_peak is None else max(prior_peak, current_upper)
        rules.append("retain_holder_edge")
    elif effect.kind == "drop":
        assert instance_id is not None and family_id is not None and effect.holder_id is not None
        trusted_negative = effect.location.source_kind in {"static_verified", "trusted_contract", "manual_fixture"}
        exact = (abstractions.get(instance_id) == "recent"
                 and confidences.get(instance_id) == "exact"
                 and instance_id not in repeated_instances)
        if not trusted_negative:
            unknown.add(f"untrusted_negative_effect:{effect.effect_id}")
            rules.append("untrusted_drop_preserves_may_hold")
        elif effect.condition != "true":
            unknown.add(f"conditional_negative_effect:{effect.effect_id}")
            rules.append("conditional_drop_preserves_may_hold")
        elif exact:
            edge = (instance_id, effect.holder_id)
            edge_existed = edge in held_edges
            held_edges.discard(edge)
            if edge_existed and not any(edge[0] == instance_id for edge in held_edges):
                held_counts[family_id] = _decrement(held_counts.get(family_id, CountInterval()))
                rules.append("drop_exact_holder_edge")
            elif edge_existed:
                rules.append("drop_exact_holder_edge_preserves_other_holders")
            else:
                rules.append("drop_missing_holder_edge_noop")
        else:
            prior_family = held_counts.get(family_id, CountInterval())
            held_counts[family_id] = CountInterval(max(0, prior_family.lower - 1), prior_family.upper)
            unknown.add(f"weak_update:{instance_id}")
            rules.append("weak_drop_summary")
    elif effect.kind == "release":
        assert instance_id is not None and family_id is not None
        trusted_negative = effect.location.source_kind in {"static_verified", "trusted_contract", "manual_fixture"}
        exact = (abstractions.get(instance_id) == "recent"
                 and confidences.get(instance_id) == "exact"
                 and instance_id not in repeated_instances)
        if not trusted_negative:
            unknown.add(f"untrusted_negative_effect:{effect.effect_id}")
            rules.append("untrusted_release_preserves_obligation")
        elif effect.condition != "true":
            unknown.add(f"conditional_negative_effect:{effect.effect_id}")
            rules.append("conditional_release_preserves_obligation")
        elif exact:
            instance_interval = instance_obligations.get(instance_id, CountInterval())
            if instance_interval.upper == 0:
                rules.append("release_already_closed_noop")
            else:
                instance_interval = _decrement(instance_interval)
                instance_obligations[instance_id] = instance_interval
                obligations[family_id] = _decrement(
                    obligations.get(family_id, CountInterval())
                )
                rules.append("release_exact_obligation")
            if instance_interval.upper == 0:
                open_obligations.discard(instance_id)
                must_released.add(instance_id)
            else:
                open_obligations.add(instance_id)
                must_released.discard(instance_id)
        else:
            # At most one represented obligation is discharged by this call.
            # Its object may already be closed, so only the lower bound falls.
            prior_instance = instance_obligations.get(instance_id, CountInterval())
            instance_obligations[instance_id] = CountInterval(max(0, prior_instance.lower - 1), prior_instance.upper)
            prior_family = obligations.get(family_id, CountInterval())
            obligations[family_id] = CountInterval(max(0, prior_family.lower - 1), prior_family.upper)
            unknown.add(f"weak_update:{instance_id}")
            rules.append("weak_release_summary")
    elif effect.kind == "dispatch":
        if instance_id is not None and family_id is not None and effect.holder_id is not None:
            already_held = any(edge[0] == instance_id for edge in held_edges)
            held_edges.add((instance_id, effect.holder_id))
            if holder_precisions.get(effect.holder_id) == "unknown":
                unknown.add(f"holder_scope_identity_unknown:{effect.holder_id}")
            if not already_held:
                held_counts[family_id] = _increment(held_counts.get(family_id, CountInterval()))
            elif instance_id in repeated_instances and dict(state.holder_kinds).get(effect.holder_id) != "field":
                prior = held_counts.get(family_id, CountInterval())
                held_counts[family_id] = CountInterval(prior.lower, None)
                unknown.add(f"repeated_abstract_instance:{instance_id}")
                rules.append("dispatch_repeated_instance_multiplicity")
            current_upper = held_counts[family_id].upper
            prior_peak = peaks.get(family_id, 0)
            peaks[family_id] = None if current_upper is None or prior_peak is None else max(prior_peak, current_upper)
            rules.append("dispatch_capture_on_contract" if effect.contract_id else "dispatch_capture_may_hold")
        else:
            unknown.add(f"dispatch_identity_unknown:{effect.effect_id}")
            rules.append("dispatch_identity_unknown")
        if effect.contract_id is None:
            unknown.add(f"dispatch_contract_unknown:{effect.effect_id}")
    elif effect.kind == "unknown_call":
        unknown.add(f"unknown_call:{effect.effect_id}")
        rules.append("unknown_call_preserve_relevant_state")

    output = replace(
        state,
        held_edges=frozenset(held_edges),
        created_instances=frozenset(created),
        open_obligations=frozenset(open_obligations),
        must_released=frozenset(must_released),
        instance_obligation_counts=_ordered_intervals(instance_obligations),
        obligation_counts=_ordered_intervals(obligations),
        allocation_counts=_ordered_intervals(allocations),
        held_counts=_ordered_intervals(held_counts),
        peak_held_counts=tuple(sorted(peaks.items())),
        repeated_instances=frozenset(repeated_instances),
        unknown_reasons=tuple(sorted(unknown)),
    )
    return StepResult(output, tuple(rules), tuple(sorted(set(effect.evidence_ids))))


def merge_states(states: Sequence[ResourceState]) -> ResourceState:
    if not states:
        raise ValueError("at least one state is required")
    first = states[0]
    metadata = (
        first.instance_families,
        first.instance_abstractions,
        first.instance_confidences,
        first.family_requires_close,
        first.family_size_upper,
        first.holder_kinds,
        first.holder_scopes,
        first.holder_precisions,
    )
    if any(
        (
            state.instance_families,
            state.instance_abstractions,
            state.instance_confidences,
            state.family_requires_close,
            state.family_size_upper,
            state.holder_kinds,
            state.holder_scopes,
            state.holder_precisions,
        ) != metadata
        for state in states[1:]
    ):
        raise ValueError("states use different resource universes")

    allocation_maps = [_intervals(item.allocation_counts) for item in states]
    obligation_maps = [_intervals(item.obligation_counts) for item in states]
    instance_obligation_maps = [
        _intervals(item.instance_obligation_counts) for item in states
    ]
    held_maps = [_intervals(item.held_counts) for item in states]
    peak_maps = [_peaks(item.peak_held_counts) for item in states]
    family_ids = set().union(
        *(mapping for mapping in allocation_maps),
        *(mapping for mapping in obligation_maps),
        *(mapping for mapping in held_maps),
    )

    def merge_interval(mappings: list[dict[str, CountInterval]], family_id: str) -> CountInterval:
        intervals = [mapping.get(family_id, CountInterval()) for mapping in mappings]
        upper = None if any(item.upper is None for item in intervals) else max(item.upper for item in intervals if item.upper is not None)
        return CountInterval(min(item.lower for item in intervals), upper)

    allocation_counts = {family_id: merge_interval(allocation_maps, family_id) for family_id in family_ids}
    obligation_counts = {family_id: merge_interval(obligation_maps, family_id) for family_id in family_ids}
    instance_ids = set().union(*(mapping for mapping in instance_obligation_maps))
    instance_obligation_counts = {
        instance_id: merge_interval(instance_obligation_maps, instance_id)
        for instance_id in instance_ids
    }
    held_counts = {family_id: merge_interval(held_maps, family_id) for family_id in family_ids}
    peak_counts: dict[str, int | None] = {}
    for family_id in family_ids:
        values = [mapping.get(family_id, 0) for mapping in peak_maps]
        peak_counts[family_id] = None if any(value is None for value in values) else max(value for value in values if value is not None)

    must_released = set(first.must_released)
    for state in states[1:]:
        must_released.intersection_update(state.must_released)

    return replace(
        first,
        held_edges=frozenset().union(*(state.held_edges for state in states)),
        created_instances=frozenset().union(*(state.created_instances for state in states)),
        open_obligations=frozenset().union(*(state.open_obligations for state in states)),
        must_released=frozenset(must_released),
        instance_obligation_counts=_ordered_intervals(instance_obligation_counts),
        obligation_counts=_ordered_intervals(obligation_counts),
        allocation_counts=_ordered_intervals(allocation_counts),
        held_counts=_ordered_intervals(held_counts),
        peak_held_counts=tuple(sorted(peak_counts.items())),
        repeated_instances=frozenset().union(*(state.repeated_instances for state in states)),
        unknown_reasons=tuple(sorted(set().union(*(state.unknown_reasons for state in states)))),
    )



def _relational_partition(state: ResourceState) -> tuple[object, ...]:
    """Do not join alternatives that authorize different negative effects.

    Numeric intervals are joined only with identical holder/object/obligation
    relationships. In particular, closing A on one branch and B on another
    cannot create a state in which both objects are known closed.
    """
    return (state.held_edges, state.created_instances, state.open_obligations,
            state.must_released, state.repeated_instances)


def state_subsumes(cover: ResourceState, candidate: ResourceState) -> bool:
    """Abstract inclusion within one resource universe and relational partition."""
    if _relational_partition(cover) != _relational_partition(candidate):
        return False
    numeric = {"allocation_counts", "obligation_counts", "instance_obligation_counts",
               "held_counts", "peak_held_counts", "unknown_reasons"}
    if any(getattr(cover, name) != getattr(candidate, name)
           for name in ResourceState.__dataclass_fields__ if name not in numeric):
        return False
    if not set(cover.unknown_reasons).issuperset(candidate.unknown_reasons):
        return False
    for name in ("allocation_counts", "obligation_counts", "instance_obligation_counts", "held_counts"):
        left, right = dict(getattr(cover, name)), dict(getattr(candidate, name))
        if left.keys() != right.keys():
            return False
        for identity, interval in right.items():
            bound = left[identity]
            if bound.lower > interval.lower or (bound.upper is not None and
                    (interval.upper is None or interval.upper > bound.upper)):
                return False
    left = dict(cover.peak_held_counts)
    return all(identity in left and (left[identity] is None or
               (upper is not None and left[identity] >= upper))
               for identity, upper in candidate.peak_held_counts)


def widen_state(prior: ResourceState, incoming: ResourceState) -> ResourceState:
    """Interval widening; infinity is loss of precision, never a growth proof."""
    if _relational_partition(prior) != _relational_partition(incoming):
        raise ValueError("widening requires the same resource relationships")
    joined = merge_states((prior, incoming))
    changes = {}
    for name in ("allocation_counts", "obligation_counts", "instance_obligation_counts", "held_counts"):
        old = dict(getattr(prior, name))
        changes[name] = tuple((identity, CountInterval(
            0 if interval.lower < old[identity].lower else interval.lower,
            None if old[identity].upper is None or interval.upper is None
            or interval.upper > old[identity].upper else interval.upper,
        )) for identity, interval in getattr(joined, name))
    old_peaks = dict(prior.peak_held_counts)
    changes["peak_held_counts"] = tuple((identity, None if upper is None
        or old_peaks[identity] is None or upper > old_peaks[identity] else upper)
        for identity, upper in joined.peak_held_counts)
    return replace(joined, **changes)


def _cyclic_events(program: Program) -> frozenset[str]:
    """Iterative Kosaraju; every vertex in a cyclic SCC is a widening point.

    Selecting all cyclic vertices is a finite feedback set even for irreducible
    CFGs, and avoids recursion depth depending on extracted method size.
    """
    edges = {event.event_id: [] for event in program.events}
    reverse = {event: [] for event in edges}
    for transition in program.transitions:
        edges[transition.source_event_id].append(transition.target_event_id)
        reverse[transition.target_event_id].append(transition.source_event_id)
    visited, order = set(), []
    for root in sorted(edges):
        stack = [(root, False)]
        while stack:
            event, expanded = stack.pop()
            if expanded:
                order.append(event)
            elif event not in visited:
                visited.add(event)
                stack.append((event, True))
                stack.extend((child, False) for child in reversed(edges[event]) if child not in visited)
    visited, cyclic = set(), set()
    for root in reversed(order):
        if root in visited:
            continue
        component, stack = set(), [root]
        while stack:
            event = stack.pop()
            if event in visited:
                continue
            visited.add(event)
            component.add(event)
            stack.extend(reverse[event])
        if len(component) > 1 or root in edges[root]:
            cyclic.update(component)
    return frozenset(cyclic)


def _statuses(exit_states: dict[str, ResourceState], unknown: set[str],
              exit_cuts: Sequence[tuple[ResourceState, frozenset[str]]] = ()) -> tuple[str, ...]:
    if not exit_states:
        return ("unknown",) if unknown else ("not_applicable",)
    output: set[str] = set()
    if unknown or any(state.unknown_reasons for state in exit_states.values()):
        output.add("unknown")
    if any(
        state.open_obligations - pending_instances
        or any(interval.upper is None for _family, interval in state.obligation_counts)
        for state, pending_instances in (exit_cuts or tuple((state, frozenset()) for state in exit_states.values()))
    ):
        output.add("obligation_gap")
    if not output:
        output.add("bounded")
    return tuple(sorted(output))


@dataclass(frozen=True, order=True)
class _Cursor:
    actor: str
    event_id: str
    # A caller remains at the source site until its submission branch resolves.
    submitted_task: str = ""
    phase: str = "absent"
    submission_outcome: str = "pending"


def _join_trace(left: Trace, right: Trace) -> Trace:
    return Trace(*(tuple(sorted(set(a).union(b))) for a, b in (
        (left.transition_ids, right.transition_ids),
        (left.rule_ids, right.rule_ids),
        (left.evidence_ids, right.evidence_ids),
        (left.rule_dependencies, right.rule_dependencies),
        (left.abstraction_steps, right.abstraction_steps),
    )))


def _trace_step(trace: Trace, transition: Transition, applied: StepResult) -> Trace:
    combined = _join_trace(trace, Trace(
        (transition.transition_id,), applied.rule_ids, applied.evidence_ids,
        tuple((rule, evidence) for rule in applied.rule_ids for evidence in applied.evidence_ids),
    ))
    return replace(combined, transition_ids=tuple(dict.fromkeys(trace.transition_ids + (transition.transition_id,))))


def _binding_dispatch(effect: Effect, binding: TaskBinding, family_id: str) -> bool:
    return effect.kind == "dispatch" and (
        effect.instance_id, effect.family_id, effect.holder_id, effect.contract_id
    ) == (binding.instance_id, family_id, binding.holder_id, binding.executor_contract_id) and (
        effect.target_event_id in {binding.queued_event_id, binding.run_event_id}
    )


def _task_step(program: Program, binding: TaskBinding, transition: Transition,
               state: ResourceState, phase: str) -> tuple[ResourceState, str, StepResult] | None:
    """Check the task phase, then use the same resource operations as the caller.

    Population deltas stay attached and audited; no q/a induction is claimed here.
    A run cursor initially means a reserved slot. Only start enters the callback.
    """
    source, target = transition.source_event_id, transition.target_event_id
    phase_out = phase
    operation = None
    evidence = set(binding.evidence_ids)
    rules = []
    if source == binding.submit_event_id:
        if phase != "absent":
            return None
        if target == binding.queued_event_id:
            phase_out, operation = "queued", "retain"
        elif target == binding.run_event_id:
            phase_out, operation = "reserved", "retain"
        elif target == binding.rejected_event_id and transition.exit_kind == "rejected":
            phase_out = "rejected"
            rules.append("task_rejection_does_not_capture")
        else:
            return None
    elif source == binding.queued_event_id and target == binding.run_event_id:
        if phase != "queued":
            return None
        phase_out = "reserved"
        rules.append("task_dequeue_is_phase_change")
    elif source == target == binding.run_event_id:
        if phase != "reserved":
            return None
        phase_out = "running"
        rules.append("task_start_preserves_capture")
    elif (target in {binding.normal_exit_event_id, binding.exceptional_exit_event_id}
          or transition.exit_kind in {"normal", "exceptional"}):
        try:
            task_exit = resolve_task_exit(program, transition)
        except ValueError:
            return None
        if phase != "running" or task_exit is None or task_exit.task_id != binding.task_id:
            return None
        phase_out, operation = "terminated", "drop"
        evidence.update(task_exit.evidence_ids)
        rules.append("task_exit_drops_own_capture")
    elif target == binding.cancelled_event_id:
        # Only an explicit, phase-matched removal relation proves cancellation.
        matching = [item for item in transition.population_effects
                    if item.kind in {"cancel_queued", "cancel_active"} and item.source_phase == phase]
        if not matching:
            return None
        phase_out, operation = "cancelled", "drop"
        rules.append("task_explicit_cancel_drops_capture")
    elif phase != "running":
        return None
    for population in transition.population_effects:
        if population.task_id != binding.task_id or population.source_phase != phase:
            return None
        if population.target_phase != phase_out:
            return None
        evidence.update(population.evidence_ids)
        rules.append("task_population_transition:" + population.kind)
    # The exit's actual CFG effects run before the holder-lifetime operation.
    next_state = state
    for effect in transition.effects:
        step = apply_effect(next_state, effect)
        next_state = step.state
        evidence.update(step.evidence_ids)
        rules.extend(step.rule_ids)
    if operation is not None:
        family = next(item for item in program.instances if item.instance_id == binding.instance_id).family_id
        location = next(item for item in program.families if item.family_id == family).allocation
        step = apply_effect(next_state, Effect(
            f"{binding.binding_id}:{transition.transition_id}:{operation}", operation,
            binding.instance_id, family, binding.holder_id, None, "true", location,
            tuple(sorted(evidence)), contract_id=binding.executor_contract_id,
        ))
        next_state = step.state
        rules.extend(step.rule_ids)
        if operation == "retain":
            rules.append("dispatch_capture_on_accept")
    return next_state, phase_out, StepResult(next_state, tuple(sorted(set(rules))), tuple(sorted(evidence)))


def solve(program: Program, *, budget: AnalysisBudget) -> AnalysisResult:
    started = time.monotonic()
    initial = initial_state(program)
    states: dict[str, ResourceState] = {}
    traces: dict[str, Trace] = {}
    outgoing: dict[str, list[Transition]] = defaultdict(list)
    for transition in program.transitions:
        outgoing[transition.source_event_id].append(transition)
    for transitions in outgoing.values():
        transitions.sort(key=lambda item: item.transition_id)

    tasks = {item.task_id: item for item in program.task_bindings}
    instance_families = {item.instance_id: item.family_id for item in program.instances}
    submits = {item.submit_event_id: item for item in program.task_bindings}
    events = {item.event_id: item for item in program.events}
    connectors: dict[str, TaskBinding] = {}
    connector_gaps = set()
    for binding in program.task_bindings:
        incoming = [edge for edge in program.transitions if edge.target_event_id == binding.submit_event_id]
        if len(incoming) == 1 and (
            incoming[0].exit_kind == "internal"
            and incoming[0].guard == "source_submit_binding"
            and not incoming[0].population_effects
            and events[incoming[0].source_event_id].callable == events[binding.submit_event_id].callable
        ):
            connectors[incoming[0].transition_id] = binding
        else:
            connector_gaps.add("task_source_binding_unavailable:" + binding.task_id)
    # Exact disjuncts at a control configuration avoid combining incompatible
    # callback branches before their negative effects. Reports alone join states.
    configurations: dict[tuple[tuple[_Cursor, ...], ResourceState, frozenset[str]], Trace] = {}
    cyclic_events = _cyclic_events(program)
    loop_states: dict[tuple[object, ...], ResourceState] = {}
    loop_updates: dict[tuple[object, ...], int] = defaultdict(int)
    widening_count = subsumption_count = 0
    queue = deque()
    queued = set()
    updates: dict[tuple[_Cursor, ...], int] = defaultdict(int)
    unknown: set[str] = set(connector_gaps)
    steps = 0
    terminated = True
    property_states: dict[str, dict[str, ResourceState]] = {
        "after_task_termination": {}, "all_tasks_terminated_after_request": {},
        "after_task_rejection": {}, "after_task_cancellation": {},
    }
    async_states: dict[str, dict[str, ResourceState]] = defaultdict(dict)
    async_derivations: dict[str, list[AsyncDerivation]] = defaultdict(list)
    async_origins: dict[str, str] = {}
    property_derivations: dict[str, dict[str, list[PropertyDerivation]]] = {name: {} for name in property_states}
    exit_cuts: set[tuple[ResourceState, frozenset[str]]] = set()

    def snapshot(store: dict[str, ResourceState], key: str, state: ResourceState) -> None:
        prior = store.get(key)
        store[key] = state if prior is None else merge_states((prior, state))

    def record(event: str, state: ResourceState, trace: Trace) -> None:
        snapshot(states, event, state)
        traces[event] = _join_trace(traces.get(event, Trace()), trace)

    def record_property(scope: str, event: str, state: ResourceState, trace: Trace) -> None:
        snapshot(property_states[scope], event, state)
        records = property_derivations[scope].setdefault(event, [])
        derivation = PropertyDerivation(event, state, trace)
        if derivation not in records:
            records.append(derivation)

    def record_async(identity: str, phase: str, transition: Transition, state: ResourceState, trace: Trace) -> None:
        snapshot(async_states[identity], phase, state)
        derivation = AsyncDerivation(phase, transition.transition_id, transition.source_event_id,
                                    transition.target_event_id, state, trace)
        if derivation not in async_derivations[identity]:
            async_derivations[identity].append(derivation)

    def enqueue(cursors: tuple[_Cursor, ...], state: ResourceState, trace: Trace) -> None:
        nonlocal terminated, widening_count, subsumption_count
        control = tuple(sorted(cursors))
        if any(cursor.event_id in cyclic_events for cursor in control):
            # Task phases, negative-effect relationships and executed branch
            # choices remain separate. Evidence IDs never enter this key.
            partition = (control, _relational_partition(state), frozenset(trace.transition_ids))
            prior_loop = loop_states.get(partition)
            if prior_loop is not None:
                if state_subsumes(prior_loop, state):
                    subsumption_count += 1
                    return
                loop_updates[partition] += 1
                if loop_updates[partition] >= 2:
                    state = widen_state(prior_loop, state)
                    widening_count += 1
                    trace = replace(trace, abstraction_steps=tuple(sorted(set(
                        trace.abstraction_steps + ("interval_widening:" + ",".join(
                            cursor.event_id for cursor in control),)))))
                else:
                    state = merge_states((prior_loop, state))
                    trace = replace(trace, abstraction_steps=tuple(sorted(set(
                        trace.abstraction_steps + ("interval_join:" + ",".join(
                            cursor.event_id for cursor in control),)))))
            loop_states[partition] = state
            # Snapshots of the abstract transfer inputs must agree with replay.
            for cursor in control:
                record(cursor.event_id, state, trace)
        # A synchronous transfer depends on control and the complete resource
        # state, not how an equivalent state was reached. Keep one witness for
        # exact duplicates; do not union incompatible states or release facts.
        # Task derivations retain their phase/path witness partition unchanged.
        key = (control, state, frozenset(trace.transition_ids) if tasks else frozenset())
        prior = configurations.get(key)
        if prior is not None:
            subsumption_count += 1
            return
        if prior is None:
            updates[control] += 1
        if updates[control] > budget.max_updates_per_event:
            unknown.add("iteration_limit:" + ",".join(cursor.event_id for cursor in control))
            terminated = False
            return
        configurations[key] = trace
        if key not in queued:
            queue.append(key)
            queued.add(key)

    for event_id in program.entry_event_ids:
        record(event_id, initial, Trace())
        enqueue((_Cursor("caller", event_id),), initial, Trace())
        updates[(_Cursor("caller", event_id),)] = 0

    while queue:
        if steps >= budget.max_steps:
            unknown.add("analysis_budget_exhausted")
            terminated = False
            break
        if (time.monotonic() - started) * 1000 >= budget.timeout_ms:
            unknown.add("solver_timeout")
            terminated = False
            break
        key = queue.popleft()
        queued.discard(key)
        cursors, source_state, _path = key
        source_trace = configurations[key]
        phase_map = {cursor.actor: cursor.phase for cursor in cursors if cursor.actor in tasks}
        caller = next(cursor for cursor in cursors if cursor.actor == "caller")
        if caller.event_id in program.exit_event_ids:
            pending = frozenset(tasks[task].instance_id for task, phase in phase_map.items()
                                if phase in {"queued", "reserved", "running"})
            exit_cuts.add((source_state, pending))
        if caller.event_id in program.exit_event_ids and phase_map and all(
            phase == "terminated" for phase in phase_map.values()
        ):
            record_property("all_tasks_terminated_after_request", caller.event_id, source_state, source_trace)
        choices = []
        for cursor in cursors:
            if cursor.actor == "caller":
                if cursor.event_id in program.exit_event_ids:
                    continue
                bound = [edge for edge in outgoing.get(cursor.event_id, ()) if edge.transition_id in connectors]
                if bound and not cursor.submitted_task:
                    choices.extend((cursor, edge) for edge in bound)
                    continue
                if cursor.submitted_task:
                    if cursor.submission_outcome == "pending":
                        continue
                    binding = tasks[cursor.submitted_task]
                    expected_guard = ("task_submit_success" if cursor.submission_outcome == "accepted"
                                      else "task_submit_exceptional")
                    continuation_edges = [edge for edge in outgoing.get(cursor.event_id, ())
                        if edge.guard == expected_guard
                        and f"task_binding:{binding.binding_id}" in edge.assumptions
                        and any(item.startswith("cfg_fact:") for item in edge.assumptions)]
                    if not continuation_edges:
                        reason = ("task_success_continuation_unknown:" if cursor.submission_outcome == "accepted"
                                  else "task_rejection_continuation_unknown:")
                        unknown.add(reason + cursor.submitted_task)
                    choices.extend((cursor, edge) for edge in continuation_edges)
                    continue
                choices.extend((cursor, edge) for edge in outgoing.get(cursor.event_id, ())
                               if edge.target_event_id not in submits)
            else:
                choices.extend((cursor, edge) for edge in outgoing.get(cursor.event_id, ()))
        for cursor, transition in choices:
            if steps >= budget.max_steps:
                unknown.add("analysis_budget_exhausted")
                terminated = False
                queue.clear()
                break
            if (time.monotonic() - started) * 1000 >= budget.timeout_ms:
                unknown.add("solver_timeout")
                terminated = False
                queue.clear()
                break
            steps += 1
            next_state = source_state
            next_cursors = list(cursors)
            index = next_cursors.index(cursor)
            binding = connectors.get(transition.transition_id)
            if binding is not None:
                if cursor.actor != "caller" or binding.task_id in phase_map or any(
                    item.actor == binding.task_id for item in cursors
                ):
                    unknown.add("task_context_reentry_unsupported:" + binding.task_id)
                    continue
                next_cursors[index] = replace(cursor, submitted_task=binding.task_id)
                next_cursors.append(_Cursor(binding.task_id, binding.submit_event_id))
                async_origins[binding.task_id] = transition.transition_id
                next_trace = source_trace
                for current in transition.effects:
                    if _binding_dispatch(current, binding, instance_families[binding.instance_id]):
                        next_trace = _trace_step(next_trace, transition, StepResult(next_state,
                            ("task_capture_deferred_to_accept",), current.evidence_ids))
                        continue  # The accepted branch owns this capture operation.
                    step = apply_effect(next_state, current)
                    next_state = step.state
                    next_trace = _trace_step(next_trace, transition, step)
                    if current.kind == "dispatch":
                        unknown.add("task_connector_dispatch_unsupported:" + binding.task_id)
                step = StepResult(next_state, ("task_source_binding",), binding.evidence_ids)
                next_trace = _trace_step(next_trace, transition, step)
                record(binding.submit_event_id, next_state, next_trace)
                enqueue(tuple(next_cursors), next_state, next_trace)
                continue
            if cursor.actor in tasks:
                binding = tasks[cursor.actor]
                result = _task_step(program, binding, transition, source_state, cursor.phase)
                if result is None:
                    if (cursor.phase == "running" and (transition.target_event_id
                            in {binding.normal_exit_event_id, binding.exceptional_exit_event_id}
                            or transition.exit_kind in {"normal", "exceptional"})):
                        unknown.add("task_exit_relation_unresolved:" + binding.task_id)
                    continue
                next_state, phase, applied = result
                next_trace = _trace_step(source_trace, transition, applied)
                next_cursors[index] = replace(cursor, event_id=transition.target_event_id, phase=phase)
                if cursor.phase == "absent":
                    outcome = "rejected" if phase == "rejected" else "accepted"
                    next_cursors = [replace(item, submission_outcome=outcome)
                        if item.submitted_task == binding.task_id else item for item in next_cursors]
                record(transition.target_event_id, next_state, next_trace)
                stage = {"queued": "queued", "reserved": "reserved", "running": "running",
                         "terminated": transition.exit_kind, "rejected": "rejected", "cancelled": "cancelled"}[phase]
                if phase != phase_map.get(binding.task_id, "absent"):
                    record_async(binding.task_id, stage, transition, next_state, next_trace)
                if phase in {"queued", "reserved", "running"}:
                    unknown.add("task_termination_not_guaranteed:" + binding.task_id)
                    if not any(population.task_id == binding.task_id
                               and population.kind in {"cancel_queued", "cancel_active"}
                               and population.source_phase == phase
                               for edge in outgoing.get(transition.target_event_id, ())
                               for population in edge.population_effects):
                        unknown.add("task_cancellation_unmodeled:" + binding.task_id)
                if phase == "terminated":
                    record_property("after_task_termination", transition.target_event_id, next_state, next_trace)
                elif phase in {"rejected", "cancelled"}:
                    record_property("after_task_rejection" if phase == "rejected" else "after_task_cancellation",
                                    transition.target_event_id, next_state, next_trace)
                enqueue(tuple(next_cursors), next_state, next_trace)
                continue
            next_trace = source_trace
            if cursor.submitted_task:
                cfg_evidence = tuple(item.removeprefix("cfg_fact:") for item in transition.assumptions
                                     if item.startswith("cfg_fact:"))
                next_trace = _trace_step(next_trace, transition, StepResult(next_state,
                    ("task_caller_continuation:" + cursor.submission_outcome,), cfg_evidence))
            for current in transition.effects:
                if (time.monotonic() - started) * 1000 >= budget.timeout_ms:
                    unknown.add("solver_timeout")
                    terminated = False
                    queue.clear()
                    break
                if (cursor.submitted_task and cursor.submission_outcome == "accepted"
                        and _binding_dispatch(current, tasks[cursor.submitted_task],
                                              instance_families[tasks[cursor.submitted_task].instance_id])):
                    next_trace = _trace_step(next_trace, transition, StepResult(next_state,
                        ("task_capture_already_applied_on_accept",), current.evidence_ids))
                    continue
                applied = apply_effect(next_state, current)
                next_state = applied.state
                next_trace = _trace_step(next_trace, transition, applied)
                if current.kind == "dispatch":
                    reason = "task_binding_unavailable:" + current.effect_id
                    unknown.add(reason)
                    next_state = replace(next_state, unknown_reasons=tuple(sorted(set(next_state.unknown_reasons) | {reason})))
                    record_async(current.effect_id, "submitted", transition, next_state, next_trace)
            if not terminated:
                break
            next_trace = _trace_step(next_trace, transition, StepResult(next_state, (), ()))
            next_cursors[index] = _Cursor(cursor.actor, transition.target_event_id)
            record(transition.target_event_id, next_state, next_trace)
            enqueue(tuple(next_cursors), next_state, next_trace)
        if not terminated:
            break

    if not program.coverage_complete:
        unknown.add("coverage_incomplete")
    exit_states = {event_id: states[event_id] for event_id in program.exit_event_ids if event_id in states}
    unknown.update(f"exit_state_missing:{event_id}" for event_id in program.exit_event_ids if event_id not in states)
    unknown.update(reason for state in states.values() for reason in state.unknown_reasons)
    property_traces = {scope: {event: tuple(record.trace for record in records) for event, records in events.items()}
                       for scope, events in property_derivations.items()}
    async_traces = {task: {phase: tuple(dict.fromkeys(item.trace for item in records if item.phase == phase))
                          for phase in sorted({item.phase for item in records})}
                    for task, records in async_derivations.items()}
    return AnalysisResult(exit_states, states, traces, terminated, tuple(sorted(unknown)),
                          _statuses(exit_states, unknown, tuple(exit_cuts)), steps, property_states,
                          dict(async_states), async_traces,
                          termination_guaranteed=(terminated and bool(exit_cuts) and not unknown and not loop_states
                                                  and not any(pending for _state, pending in exit_cuts)),
                          property_traces=property_traces, async_origins=async_origins,
                          async_derivations={task: tuple(records) for task, records in async_derivations.items()},
                          property_derivations={scope: {event: tuple(records) for event, records in events.items()}
                                                for scope, events in property_derivations.items()},
                          solver_metrics={"abstract_configurations": len(configurations),
                                          "cyclic_event_count": len(cyclic_events),
                                          "loop_partitions": len(loop_states),
                                          "widening_count": widening_count,
                                          "subsumption_count": subsumption_count})
