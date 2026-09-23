from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from dosweb.errors import AnalyzerError
from dosweb.flows import VerifiedFlow
from dosweb.growth import VerifiedGrowthResult
from dosweb.lifecycle import BoundDecision, GuardDecision, ReleaseDecision
from dosweb.lifecycle.resource_properties import (
    ResourceLifecycleDecision,
    bounded_task_population_semantics,
)

AssertionName = Literal["assertion_1", "assertion_2"]
AssertionStatus = Literal["matched", "refuted", "unknown", "not_applicable"]


@dataclass(frozen=True)
class AssertionEvaluation:
    assertion: AssertionName
    status: AssertionStatus
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.assertion not in {"assertion_1", "assertion_2"}:
            raise AnalyzerError("ANALYSIS_ASSERTION_INVALID", "Assertion name is invalid.")
        if self.status not in {"matched", "refuted", "unknown", "not_applicable"}:
            raise AnalyzerError("ANALYSIS_ASSERTION_INVALID", "Assertion status is invalid.")
        for field, values in (
            ("reason_codes", self.reason_codes),
            ("evidence_ids", self.evidence_ids),
            ("unresolved_facts", self.unresolved_facts),
            ("assumptions", self.assumptions),
        ):
            if not isinstance(values, tuple) or any(not isinstance(value, str) or not value for value in values):
                raise AnalyzerError("ANALYSIS_ASSERTION_INVALID", f"{field} is invalid.")
            object.__setattr__(self, field, tuple(sorted(set(values))))


def _context(growth: VerifiedGrowthResult, flow: VerifiedFlow) -> None:
    if not isinstance(growth, VerifiedGrowthResult) or not isinstance(flow, VerifiedFlow):
        raise AnalyzerError("ANALYSIS_ASSERTION_INVALID", "Assertion inputs are malformed.")
    if flow.growth_id != growth.growth_id:
        raise AnalyzerError(
            "ANALYSIS_DANGLING_FACT_REFERENCE",
            "Assertion flow and Growth facts do not match.",
            {"growth_id": growth.growth_id, "flow_growth_id": flow.growth_id},
        )


def _ids(
    growth: VerifiedGrowthResult,
    flow: VerifiedFlow,
    *decisions: object,
) -> tuple[str, ...]:
    values: set[str] = {
        growth.verified_growth_id,
        growth.growth_id,
        flow.verified_flow_id,
        flow.path_id,
        flow.entry_id,
        *flow.evidence_ids,
    }
    for decision in decisions:
        values.update(getattr(decision, "evidence_ids", ()))
        values.update(getattr(decision, "candidate_ids", ()))
        decision_id = getattr(decision, "decision_id", None)
        if isinstance(decision_id, str):
            values.add(decision_id)
    return tuple(sorted(values))


def _unresolved(growth: VerifiedGrowthResult, flow: VerifiedFlow, *decisions: object) -> tuple[str, ...]:
    values: set[str] = set(flow.unresolved_facts)
    if growth.status != "verified":
        values.add(growth.status)
    values.update(growth.reason_codes)
    for decision in decisions:
        values.update(getattr(decision, "unresolved_facts", ()))
    return tuple(sorted(values))


def _result(
    assertion: AssertionName,
    status: AssertionStatus,
    reasons: Iterable[str],
    growth: VerifiedGrowthResult,
    flow: VerifiedFlow,
    unresolved: Iterable[str] = (),
    *decisions: object,
) -> AssertionEvaluation:
    return AssertionEvaluation(
        assertion,
        status,
        tuple(sorted(set(reasons))),
        _ids(growth, flow, *decisions),
        tuple(sorted(set(unresolved))),
        tuple(sorted({a for decision in decisions if status == "refuted" and isinstance(decision, ResourceLifecycleDecision) for a in decision.assumptions})),
    )


def _decision_status(decision: object | None) -> str | None:
    return getattr(decision, "status", None) if decision is not None else None


def _decision_ids(decision: object | None) -> tuple[str, ...]:
    identifier = getattr(decision, "decision_id", None) if decision is not None else None
    return (identifier,) if isinstance(identifier, str) and identifier else ()


def _resource_lifecycle_refutation(
    decision: ResourceLifecycleDecision | None,
    growth: VerifiedGrowthResult,
    flow: VerifiedFlow,
) -> Literal["refute", "unknown"] | None:
    """Consume a resource decision only when identity and supported semantics still hold.

    Status ``refutes_relevant_growth`` is not enough: a decision bound to
    another growth/flow/executor, a non-task dimension, or a mutated cut that
    kept the old identifier must not be borrowed as a current-input bound.
    """
    if decision is None:
        return None
    if decision.status == "unresolved":
        return "unknown"
    if decision.status != "refutes_relevant_growth":
        return None
    try:
        ResourceLifecycleDecision.from_dict(decision.to_dict())
    except AnalyzerError:
        return "unknown"
    candidate = growth.candidate
    if (
        decision.matches_input(
            entry_id=flow.entry_id,
            growth_id=growth.growth_id,
            path_id=flow.path_id,
        )
        and bounded_task_population_semantics(
            status=decision.status,
            dimension=decision.dimension,
            scope=decision.scope,
            cut=decision.cut,
            upper_bound=decision.upper_bound,
            assumptions=decision.assumptions,
            property_id=decision.property_id,
        )
        and candidate is not None
        and candidate.kind == "async_work_growth"
        and candidate.resource_dimension == "tasks"
    ):
        return "refute"
    return "unknown"


def evaluate_assertion_1(
    growth: VerifiedGrowthResult,
    flow: VerifiedFlow,
    guard: GuardDecision,
    bound: BoundDecision,
    *,
    amplification: object | None = None,
    reachability: object | None = None,
    resource_lifecycle: ResourceLifecycleDecision | None = None,
) -> AssertionEvaluation:
    """Evaluate P0 assertion 1: only externally reachable direct demand or amplification."""
    _context(growth, flow)
    if not isinstance(guard, GuardDecision) or not isinstance(bound, BoundDecision):
        raise AnalyzerError("ANALYSIS_ASSERTION_INVALID", "Assertion 1 decisions are malformed.")
    if resource_lifecycle is not None and not isinstance(
        resource_lifecycle, ResourceLifecycleDecision
    ):
        raise AnalyzerError(
            "ANALYSIS_ASSERTION_INVALID",
            "Assertion 1 resource lifecycle decision is malformed.",
        )
    reach = _decision_status(reachability)
    if reach is not None and reach != "ordinary_attacker_reachable":
        if reach == "not_entry_reachable":
            return _result("assertion_1", "not_applicable", ("A1_NOT_ORDINARY_ATTACKER_REACHABLE",), growth, flow, (), guard, bound)
        return _result("assertion_1", "unknown", ("A1_REACHABILITY_UNKNOWN",), growth, flow, _decision_ids(reachability), guard, bound)
    target = flow.proof.attacker_control.target
    direct = growth.candidate is not None and growth.candidate.kind in {"input_materialization", "direct_allocation"} and target == "size"
    amplified = growth.candidate is not None and growth.candidate.kind in {"container_growth", "async_work_growth"} and _decision_status(amplification) == "proven"
    if not direct and not amplified:
        if growth.candidate is not None and growth.candidate.kind in {"container_growth", "async_work_growth"} and _decision_status(amplification) == "unknown":
            return _result("assertion_1", "unknown", ("A1_AMPLIFICATION_UNKNOWN",), growth, flow, _decision_ids(amplification), guard, bound)
        return _result("assertion_1", "not_applicable", ("A1_SINGLE_OPERATION_NOT_AMPLIFYING",), growth, flow, (), guard, bound)
    if growth.status != "verified":
        return _result(
            "assertion_1", "unknown", ("A1_GROWTH_NOT_VERIFIED",), growth, flow,
            _unresolved(growth, flow, guard, bound), guard, bound,
        )
    if flow.status != "verified":
        return _result(
            "assertion_1", "unknown", ("A1_FLOW_NOT_PROVEN",), growth, flow,
            (*flow.unresolved_facts, *flow.reason_codes), guard, bound,
        )
    if flow.unresolved_facts:
        return _result(
            "assertion_1", "unknown", ("A1_FLOW_UNRESOLVED",), growth, flow,
            flow.unresolved_facts, guard, bound,
        )
    if guard.status == "unknown" or guard.unresolved_facts:
        return _result(
            "assertion_1", "unknown", ("A1_GUARD_UNKNOWN",), growth, flow,
            _unresolved(growth, flow, guard, bound), guard, bound,
        )
    if guard.status == "effective":
        return _result("assertion_1", "refuted", ("A1_EFFECTIVE_GUARD",), growth, flow, (), guard, bound)
    resource_refutation = _resource_lifecycle_refutation(
        resource_lifecycle, growth, flow
    )
    if resource_refutation == "unknown":
        reasons = (
            ("A1_RESOURCE_LIFECYCLE_UNKNOWN",)
            if resource_lifecycle is not None
            and resource_lifecycle.status == "unresolved"
            else ("A1_RESOURCE_LIFECYCLE_BINDING_MISMATCH",)
        )
        unresolved = (
            resource_lifecycle.unresolved_facts
            if resource_lifecycle is not None
            and resource_lifecycle.unresolved_facts
            else _decision_ids(resource_lifecycle)
        )
        return _result(
            "assertion_1",
            "unknown",
            reasons,
            growth,
            flow,
            unresolved,
            guard,
            bound,
            resource_lifecycle,
        )
    if resource_refutation == "refute":
        return _result(
            "assertion_1",
            "refuted",
            ("A1_BOUNDED_ACCEPTED_TASK_POPULATION",),
            growth,
            flow,
            (),
            guard,
            bound,
            resource_lifecycle,
        )
    if bound.status == "unknown" or bound.unresolved_facts:
        return _result(
            "assertion_1", "unknown", ("A1_BOUND_UNKNOWN",), growth, flow,
            _unresolved(growth, flow, guard, bound), guard, bound,
        )
    if bound.status == "effective":
        return _result("assertion_1", "refuted", ("A1_EFFECTIVE_BOUND",), growth, flow, (), guard, bound)
    return _result(
        "assertion_1", "matched",
        ("A1_FLOW_PROVEN", "A1_GROWTH_VERIFIED", "A1_NO_EFFECTIVE_GUARD", "A1_NO_EFFECTIVE_BOUND"),
        growth, flow, (), guard, bound,
    )


def evaluate_assertion_2(
    growth: VerifiedGrowthResult,
    flow: VerifiedFlow,
    bound: BoundDecision,
    release: ReleaseDecision,
    *,
    reachability: object | None = None,
    repeatability: object | None = None,
    resource_lifecycle: ResourceLifecycleDecision | None = None,
) -> AssertionEvaluation:
    """Evaluate P0 assertion 2: repeatable persistent accumulation."""
    _context(growth, flow)
    if not isinstance(bound, BoundDecision) or not isinstance(release, ReleaseDecision):
        raise AnalyzerError("ANALYSIS_ASSERTION_INVALID", "Assertion 2 decisions are malformed.")
    if resource_lifecycle is not None and not isinstance(
        resource_lifecycle, ResourceLifecycleDecision
    ):
        raise AnalyzerError(
            "ANALYSIS_ASSERTION_INVALID",
            "Assertion 2 resource lifecycle decision is malformed.",
        )
    reach = _decision_status(reachability)
    if reach is not None and reach != "ordinary_attacker_reachable":
        if reach == "not_entry_reachable":
            return _result("assertion_2", "not_applicable", ("A2_NOT_ORDINARY_ATTACKER_REACHABLE",), growth, flow, (), bound, release)
        return _result("assertion_2", "unknown", ("A2_REACHABILITY_UNKNOWN",), growth, flow, _decision_ids(reachability), bound, release)
    repeat = _decision_status(repeatability)
    if repeat is not None and repeat != "proven":
        if repeat == "not_applicable":
            return _result("assertion_2", "not_applicable", ("A2_NOT_REPEATABLE",), growth, flow, (), bound, release)
        return _result("assertion_2", "unknown", ("A2_REPEATABILITY_UNKNOWN",), growth, flow, _decision_ids(repeatability), bound, release)
    if growth.status != "verified":
        return _result(
            "assertion_2", "unknown", ("A2_GROWTH_NOT_VERIFIED",), growth, flow,
            _unresolved(growth, flow, bound, release), bound, release,
        )
    if flow.status != "verified":
        return _result(
            "assertion_2", "unknown", ("A2_FLOW_NOT_PROVEN",), growth, flow,
            (*flow.unresolved_facts, *flow.reason_codes), bound, release,
        )
    if flow.unresolved_facts:
        return _result(
            "assertion_2", "unknown", ("A2_FLOW_UNRESOLVED",), growth, flow,
            flow.unresolved_facts, bound, release,
        )
    target = flow.proof.attacker_control.target
    if target not in {"key", "value", "submission_count"}:
        return _result("assertion_2", "not_applicable", ("A2_NONPERSISTENT_DEMAND",), growth, flow, (), bound, release)
    if growth.candidate is None or growth.candidate.escape_scope == "request":
        return _result("assertion_2", "not_applicable", ("A2_NONESCAPING_GROWTH",), growth, flow, (), bound, release)
    if growth.candidate.escape_scope == "unknown":
        return _result("assertion_2", "unknown", ("A2_ESCAPE_SCOPE_UNKNOWN",), growth, flow, ("escape_scope",), bound, release)
    resource_refutation = _resource_lifecycle_refutation(
        resource_lifecycle, growth, flow
    )
    if resource_refutation == "unknown":
        reasons = (
            ("A2_RESOURCE_LIFECYCLE_UNKNOWN",)
            if resource_lifecycle is not None
            and resource_lifecycle.status == "unresolved"
            else ("A2_RESOURCE_LIFECYCLE_BINDING_MISMATCH",)
        )
        unresolved = (
            resource_lifecycle.unresolved_facts
            if resource_lifecycle is not None
            and resource_lifecycle.unresolved_facts
            else _decision_ids(resource_lifecycle)
        )
        return _result(
            "assertion_2",
            "unknown",
            reasons,
            growth,
            flow,
            unresolved,
            bound,
            release,
            resource_lifecycle,
        )
    if resource_refutation == "refute":
        return _result(
            "assertion_2",
            "refuted",
            ("A2_BOUNDED_ACCEPTED_TASK_POPULATION",),
            growth,
            flow,
            (),
            bound,
            release,
            resource_lifecycle,
        )
    if bound.status == "unknown" or bound.unresolved_facts:
        return _result("assertion_2", "unknown", ("A2_BOUND_UNKNOWN",), growth, flow, _unresolved(growth, flow, bound, release), bound, release)
    if bound.status == "effective":
        return _result("assertion_2", "refuted", ("A2_EFFECTIVE_BOUND",), growth, flow, (), bound, release)
    if release.classification == "potential_async":
        return _result("assertion_2", "unknown", ("A2_POTENTIAL_ASYNC_RELEASE",), growth, flow, _unresolved(growth, flow, bound, release), bound, release)
    if release.status == "unknown" or release.unresolved_facts or release.classification == "unknown":
        return _result("assertion_2", "unknown", ("A2_RELEASE_UNKNOWN",), growth, flow, _unresolved(growth, flow, bound, release), bound, release)
    if release.status == "effective":
        return _result("assertion_2", "refuted", ("A2_EFFECTIVE_SYNCHRONOUS_RELEASE",), growth, flow, (), bound, release)
    return _result(
        "assertion_2", "matched",
        ("A2_FLOW_PROVEN", "A2_GROWTH_ESCAPES", "A2_NO_EFFECTIVE_BOUND", "A2_NO_EFFECTIVE_RELEASE"),
        growth, flow, (), bound, release,
    )


__all__ = ["AssertionEvaluation", "evaluate_assertion_1", "evaluate_assertion_2"]
