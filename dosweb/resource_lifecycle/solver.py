from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, replace
import time

from dosweb.resource_lifecycle.models import (
    AnalysisBudget,
    AnalysisResult,
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
            held_counts[family_id] = CountInterval(prior.lower + 1, None)
            unknown.add(f"repeated_abstract_instance:{instance_id}")
            rules.append("retain_repeated_instance_multiplicity")
        current_upper = held_counts[family_id].upper
        prior_peak = peaks.get(family_id, 0)
        peaks[family_id] = None if current_upper is None or prior_peak is None else max(prior_peak, current_upper)
        rules.append("retain_holder_edge")
    elif effect.kind == "drop":
        assert instance_id is not None and family_id is not None and effect.holder_id is not None
        trusted_negative = effect.location.source_kind in {"static_verified", "trusted_contract", "manual_fixture"}
        exact = abstractions.get(instance_id) == "recent" and confidences.get(instance_id) == "exact"
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
            unknown.add(f"weak_update:{instance_id}")
            rules.append("weak_drop_summary")
    elif effect.kind == "release":
        assert instance_id is not None and family_id is not None
        trusted_negative = effect.location.source_kind in {"static_verified", "trusted_contract", "manual_fixture"}
        exact = abstractions.get(instance_id) == "recent" and confidences.get(instance_id) == "exact"
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
                held_counts[family_id] = CountInterval(prior.lower + 1, None)
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
        task_phases=frozenset().union(*(state.task_phases for state in states)),
    )


def _statuses(exit_states: dict[str, ResourceState], unknown: set[str], pending_instances: frozenset[str] = frozenset()) -> tuple[str, ...]:
    if not exit_states:
        return ("unknown",) if unknown else ("not_applicable",)
    output: set[str] = set()
    if unknown or any(state.unknown_reasons for state in exit_states.values()):
        output.add("unknown")
    if any(
        state.open_obligations - pending_instances
        or any(interval.upper is None for _family, interval in state.obligation_counts)
        for state in exit_states.values()
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


def _join_trace(left: Trace, right: Trace) -> Trace:
    return Trace(*(tuple(sorted(set(a).union(b))) for a, b in (
        (left.transition_ids, right.transition_ids),
        (left.rule_ids, right.rule_ids),
        (left.evidence_ids, right.evidence_ids),
        (left.rule_dependencies, right.rule_dependencies),
    )))


def _trace_step(trace: Trace, transition: Transition, applied: StepResult) -> Trace:
    return _join_trace(trace, Trace(
        (transition.transition_id,), applied.rule_ids, applied.evidence_ids,
        tuple((rule, evidence) for rule in applied.rule_ids for evidence in applied.evidence_ids),
    ))


def _task_step(program: Program, binding: TaskBinding, transition: Transition,
               state: ResourceState) -> tuple[ResourceState, str, StepResult] | None:
    """Check the task phase, then use the same resource operations as the caller.

    Population deltas stay attached and audited; no q/a induction is claimed here.
    A run cursor initially means a reserved slot. Only start enters the callback.
    """
    phase = dict(state.task_phases).get(binding.task_id, "absent")
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
    elif target in {binding.normal_exit_event_id, binding.exceptional_exit_event_id}:
        exits = [item for item in program.task_exits if item.task_id == binding.task_id
                 and item.event_id == target and item.kind == transition.exit_kind]
        if phase != "running" or not exits:
            return None
        phase_out, operation = "terminated", "drop"
        evidence.update(item for task_exit in exits for item in task_exit.evidence_ids)
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
    next_state = replace(next_state, task_phases=frozenset(
        (task, value) for task, value in next_state.task_phases if task != binding.task_id
    ) | {(binding.task_id, phase_out)})
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
    configurations: dict[tuple[tuple[_Cursor, ...], ResourceState], Trace] = {}
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
    async_traces: dict[str, Trace] = {}
    async_origins: dict[str, str] = {}
    property_traces: dict[str, dict[str, Trace]] = {name: {} for name in property_states}

    def snapshot(store: dict[str, ResourceState], key: str, state: ResourceState) -> None:
        prior = store.get(key)
        store[key] = state if prior is None else merge_states((prior, state))

    def record(event: str, state: ResourceState, trace: Trace) -> None:
        snapshot(states, event, state)
        traces[event] = _join_trace(traces.get(event, Trace()), trace)

    def record_property(scope: str, event: str, state: ResourceState, trace: Trace) -> None:
        snapshot(property_states[scope], event, state)
        property_traces[scope][event] = _join_trace(property_traces[scope].get(event, Trace()), trace)

    def enqueue(cursors: tuple[_Cursor, ...], state: ResourceState, trace: Trace) -> None:
        nonlocal terminated
        control = tuple(sorted(cursors))
        key = (control, state)
        prior = configurations.get(key)
        combined = trace if prior is None else _join_trace(prior, trace)
        if prior == combined:
            return
        if prior is None:
            updates[control] += 1
        if updates[control] > budget.max_updates_per_event:
            unknown.add("iteration_limit:" + ",".join(cursor.event_id for cursor in control))
            terminated = False
            return
        configurations[key] = combined
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
        cursors, source_state = key
        source_trace = configurations[key]
        phase_map = dict(source_state.task_phases)
        caller = next(cursor for cursor in cursors if cursor.actor == "caller")
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
                    phase = phase_map.get(cursor.submitted_task, "absent")
                    if phase in {"absent", "rejected", "cancelled"}:
                        if phase == "rejected":
                            unknown.add("task_rejection_continuation_unknown:" + cursor.submitted_task)
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
                    if current.kind == "dispatch" and (
                        current.instance_id, current.holder_id, current.contract_id
                    ) == (binding.instance_id, binding.holder_id, binding.executor_contract_id):
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
                result = _task_step(program, binding, transition, source_state)
                if result is None:
                    continue
                next_state, phase, applied = result
                next_trace = _trace_step(source_trace, transition, applied)
                next_cursors[index] = replace(cursor, event_id=transition.target_event_id)
                record(transition.target_event_id, next_state, next_trace)
                stage = {"queued": "submitted", "reserved": "submitted", "running": "started",
                         "terminated": transition.exit_kind, "rejected": "rejected", "cancelled": "cancelled"}[phase]
                if phase != phase_map.get(binding.task_id, "absent"):
                    snapshot(async_states[binding.task_id], stage, next_state)
                async_traces[binding.task_id] = _join_trace(async_traces.get(binding.task_id, Trace()), next_trace)
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
            for current in transition.effects:
                if (time.monotonic() - started) * 1000 >= budget.timeout_ms:
                    unknown.add("solver_timeout")
                    terminated = False
                    queue.clear()
                    break
                applied = apply_effect(next_state, current)
                next_state = applied.state
                next_trace = _trace_step(next_trace, transition, applied)
                if current.kind == "dispatch":
                    reason = "task_binding_unavailable:" + current.effect_id
                    unknown.add(reason)
                    next_state = replace(next_state, unknown_reasons=tuple(sorted(set(next_state.unknown_reasons) | {reason})))
                    snapshot(async_states[current.effect_id], "submitted", next_state)
                    async_traces[current.effect_id] = _join_trace(async_traces.get(current.effect_id, Trace()), next_trace)
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
    pending_instances = frozenset(binding.instance_id for binding in tasks.values()
                                  if binding.task_id in async_states)
    return AnalysisResult(exit_states, states, traces, terminated, tuple(sorted(unknown)),
                          _statuses(exit_states, unknown, pending_instances), steps, property_states,
                          dict(async_states), async_traces,
                          termination_guaranteed=not async_states and not unknown,
                          property_traces=property_traces, async_origins=async_origins)
