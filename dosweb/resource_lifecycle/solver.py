from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import replace
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
            held_edges.discard((instance_id, effect.holder_id))
            if not any(edge[0] == instance_id for edge in held_edges):
                held_counts[family_id] = _decrement(held_counts.get(family_id, CountInterval()))
            rules.append("drop_exact_holder_edge")
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
            obligations[family_id] = _decrement(obligations.get(family_id, CountInterval()))
            if obligations[family_id].upper == 0:
                open_obligations.discard(instance_id)
                must_released.add(instance_id)
            else:
                open_obligations.add(instance_id)
                must_released.discard(instance_id)
            rules.append("release_exact_obligation")
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
        obligation_counts=_ordered_intervals(obligation_counts),
        allocation_counts=_ordered_intervals(allocation_counts),
        held_counts=_ordered_intervals(held_counts),
        peak_held_counts=tuple(sorted(peak_counts.items())),
        repeated_instances=frozenset().union(*(state.repeated_instances for state in states)),
        unknown_reasons=tuple(sorted(set().union(*(state.unknown_reasons for state in states)))),
    )


def _statuses(exit_states: dict[str, ResourceState], unknown: set[str]) -> tuple[str, ...]:
    if not exit_states:
        return ("unknown",) if unknown else ("not_applicable",)
    output: set[str] = set()
    if unknown or any(state.unknown_reasons for state in exit_states.values()):
        output.add("unknown")
    if any(
        state.open_obligations or any(interval.upper is None or interval.upper > 0 for _family, interval in state.obligation_counts)
        for state in exit_states.values()
    ):
        output.add("obligation_gap")
    if not output:
        output.add("bounded")
    return tuple(sorted(output))


def solve(program: Program, *, budget: AnalysisBudget) -> AnalysisResult:
    started = time.monotonic()
    initial = initial_state(program)
    states: dict[str, ResourceState] = {event_id: initial for event_id in program.entry_event_ids}
    traces: dict[str, Trace] = {event_id: Trace() for event_id in program.entry_event_ids}
    outgoing: dict[str, list[object]] = defaultdict(list)
    for transition in program.transitions:
        outgoing[transition.source_event_id].append(transition)
    for transitions in outgoing.values():
        transitions.sort(key=lambda item: item.transition_id)

    queue = deque(program.entry_event_ids)
    queued = set(program.entry_event_ids)
    updates: dict[str, int] = defaultdict(int)
    unknown: set[str] = set()
    steps = 0
    terminated = True

    while queue:
        if steps >= budget.max_steps:
            unknown.add("analysis_budget_exhausted")
            terminated = False
            break
        if (time.monotonic() - started) * 1000 >= budget.timeout_ms:
            unknown.add("solver_timeout")
            terminated = False
            break
        source = queue.popleft()
        queued.discard(source)
        source_state = states[source]
        source_trace = traces.get(source, Trace())
        for transition in outgoing.get(source, ()):
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
            rules: list[str] = []
            evidence: list[str] = []
            rule_dependencies: list[tuple[str, str]] = []
            for current in transition.effects:
                if (time.monotonic() - started) * 1000 >= budget.timeout_ms:
                    unknown.add("solver_timeout")
                    terminated = False
                    queue.clear()
                    break
                applied = apply_effect(next_state, current)
                next_state = applied.state
                rules.extend(applied.rule_ids)
                evidence.extend(applied.evidence_ids)
                rule_dependencies.extend(
                    (rule_id, evidence_id)
                    for rule_id in applied.rule_ids
                    for evidence_id in applied.evidence_ids
                )
            if not terminated:
                break
            prior = states.get(transition.target_event_id)
            merged = next_state if prior is None else merge_states((prior, next_state))
            next_trace = Trace(
                tuple(dict.fromkeys(source_trace.transition_ids + (transition.transition_id,))),
                tuple(dict.fromkeys(source_trace.rule_ids + tuple(rules))),
                tuple(sorted(set(source_trace.evidence_ids).union(evidence))),
                tuple(sorted(set(source_trace.rule_dependencies).union(rule_dependencies))),
            )
            prior_trace = traces.get(transition.target_event_id)
            if prior_trace is not None:
                next_trace = Trace(
                    tuple(sorted(set(prior_trace.transition_ids).union(next_trace.transition_ids))),
                    tuple(sorted(set(prior_trace.rule_ids).union(next_trace.rule_ids))),
                    tuple(sorted(set(prior_trace.evidence_ids).union(next_trace.evidence_ids))),
                    tuple(sorted(set(prior_trace.rule_dependencies).union(next_trace.rule_dependencies))),
                )
            if prior != merged or prior_trace != next_trace:
                states[transition.target_event_id] = merged
                traces[transition.target_event_id] = next_trace
                updates[transition.target_event_id] += 1
                if updates[transition.target_event_id] > budget.max_updates_per_event:
                    unknown.add(f"widening:{transition.target_event_id}")
                    terminated = False
                    queue.clear()
                    break
                if transition.target_event_id not in queued:
                    queue.append(transition.target_event_id)
                    queued.add(transition.target_event_id)
        if not terminated:
            break

    if not program.coverage_complete:
        unknown.add("coverage_incomplete")
    exit_states = {event_id: states[event_id] for event_id in program.exit_event_ids if event_id in states}
    unknown.update(f"exit_state_missing:{event_id}" for event_id in program.exit_event_ids if event_id not in states)
    unknown.update(reason for state in states.values() for reason in state.unknown_reasons)
    return AnalysisResult(exit_states, states, traces, terminated, tuple(sorted(unknown)), _statuses(exit_states, unknown), steps)
