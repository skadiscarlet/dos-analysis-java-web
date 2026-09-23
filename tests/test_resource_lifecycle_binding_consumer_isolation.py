"""Consumer isolation for resource-lifecycle decisions.

Copied from the independent 20260922 check
``docs/execution/lifecycle-semantic-repair/checks/test_binding_consumer_isolation.py``.
Imports resolve against this 20260923 worktree. Synthetic fixtures only.
These cases do not claim a frozen-batch false bounded finding.
"""
from dataclasses import replace

from dosweb.conclude import evaluate_assertion_1, evaluate_assertion_2
from dosweb.errors import AnalyzerError
from dosweb.flows import AttackerControl, FlowProof, verify_flow
from dosweb.growth import DemandInput, GrowthCandidate
from dosweb.lifecycle import BoundDecision, GuardDecision, ReleaseDecision
from dosweb.lifecycle.resource_properties import bind_resource_lifecycle_property
from tests.test_resource_lifecycle_production_bridge import (
    _entry,
    _flow,
    _growth,
    _run,
    _verified,
)


def context():
    entry = _entry()
    growth = _verified(_growth())
    flow = _flow(entry, growth)
    decision = bind_resource_lifecycle_property(
        entry, growth, flow, _run()
    ).resource_decision
    return entry, growth, flow, decision


def no_bound():
    return BoundDecision("absent", ("BOUND_ABSENT",), (), (), (), ())


def no_release():
    return ReleaseDecision("absent", "absent", ("RELEASE_ABSENT",), (), (), (), ())


def safely_rejected(call):
    try:
        outcome = call()
    except AnalyzerError:
        return
    assert outcome.status in {"unknown", "not_applicable"}, outcome


def test_exact_original_context_remains_refuted():
    _, growth, flow, decision = context()
    result = evaluate_assertion_2(
        growth, flow, no_bound(), no_release(), resource_lifecycle=decision
    )
    assert result.status == "refuted"


def test_bound_for_one_executor_cannot_refute_another_executor():
    entry, growth, _, decision = context()
    old = growth.candidate
    other = _verified(
        GrowthCandidate.create(
            site=old.site,
            kind=old.kind,
            operation=old.operation,
            resource_dimension=old.resource_dimension,
            receiver="this.otherExecutor",
            field_path="this.otherExecutor",
            demand_inputs=old.demand_inputs,
            escape_scope=old.escape_scope,
            evidence_ids=old.evidence_ids,
        )
    )
    flow = _flow(entry, other)
    assert flow.satisfies_premise
    assert other.growth_id != growth.growth_id
    safely_rejected(
        lambda: evaluate_assertion_2(
            other, flow, no_bound(), no_release(), resource_lifecycle=decision
        )
    )


def test_task_population_cannot_refute_byte_allocation():
    entry, growth, _, decision = context()
    allocation = _verified(
        GrowthCandidate.create(
            site=growth.candidate.site,
            kind="direct_allocation",
            operation="allocate(count)",
            resource_dimension="bytes",
            receiver="buffer",
            field_path="buffer",
            demand_inputs=(DemandInput("count", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:synthetic-allocation"}),
        )
    )
    proof = FlowProof.create(
        entry_id=entry.entry_id,
        growth_id=allocation.growth_id,
        attacker_control=AttackerControl("size", "count", "count"),
        call_path=(entry.handler.callable,),
        phase_sequence=("in_handler",),
        confidence="proven",
    )
    flow = verify_flow(
        proof, {entry.entry_id: entry}, {allocation.growth_id: allocation}
    )
    assert flow.satisfies_premise
    guard = GuardDecision("ineffective", ("GUARD_ABSENT",), (), (), (), ())
    safely_rejected(
        lambda: evaluate_assertion_1(
            allocation, flow, guard, no_bound(), resource_lifecycle=decision
        )
    )


def test_changed_execution_cut_cannot_keep_original_refutation():
    _, growth, flow, decision = context()
    safely_rejected(
        lambda: evaluate_assertion_2(
            growth,
            flow,
            no_bound(),
            no_release(),
            resource_lifecycle=replace(decision, cut="method_exit"),
        )
    )


def test_real_solver_assumptions_survive_into_decision():
    entry, growth, flow, _ = context()
    bound = bind_resource_lifecycle_property(entry, growth, flow, _run())
    assert len(bound.record["assumptions"]) >= 1
    assert set(bound.record["assumptions"]).issubset(
        set(bound.resource_decision.to_dict().get("assumptions", []))
    )


def test_altered_serialized_assumptions_cannot_reuse_old_decision_id():
    from dosweb.lifecycle.resource_properties import ResourceLifecycleDecision

    _, _, _, decision = context()
    record = decision.to_dict()
    record["assumptions"] = ["different unproven execution assumption"]
    safely_rejected(lambda: ResourceLifecycleDecision.from_dict(record))
