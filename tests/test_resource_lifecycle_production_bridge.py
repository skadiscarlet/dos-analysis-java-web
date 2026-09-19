from __future__ import annotations

from dataclasses import replace
import hashlib

from dosweb.artifacts.schemas import validate_records
from dosweb.artifacts.identifiers import canonical_json
from dosweb.entries import (
    AttackerInputFact,
    EntryFact,
    HandlerFact,
    RegistrationFact,
)
from dosweb.flows import AttackerControl, FlowProof, verify_flow
from dosweb.growth import (
    DemandInput,
    GrowthCandidate,
    SourceLocation,
    VerificationCheck,
    VerifiedGrowthResult,
)
from dosweb.lifecycle.resource_properties import (
    ResourceLifecycleBackendRun,
    bind_resource_lifecycle_property,
)
from dosweb.resource_lifecycle.adapters import (
    AnalysisUnit,
    ExtractedFacts,
    RawLifecycleFact,
    extracted_to_dict,
)
from dosweb.resource_lifecycle.commands import _analyze_payload
from dosweb.resource_lifecycle.models import AnalysisBudget
from tests.test_resource_lifecycle_population import (
    executor_contract,
    population_program,
)
from tests.test_resource_lifecycle_solver import location


def _entry() -> EntryFact:
    return EntryFact.create(
        framework="spring_mvc",
        protocol="http",
        handler=HandlerFact(
            "Fixture.handle", "src/main/java/Fixture.java", 1
        ),
        registration=RegistrationFact(
            "annotation_mapping",
            "Fixture",
            "src/main/java/Fixture.java",
            1,
        ),
        registration_pattern_id=(
            "entry-registration-coverage:spring_mvc:"
            "annotation_mapping:spring_annotation_mapping"
        ),
        route_or_event="/submit",
        auth_context="unauthenticated",
        attacker_inputs=(
            AttackerInputFact("count", "int", "request_parameter"),
        ),
        materialization_phase="in_handler",
    )


def _growth(*, line: int = 3) -> GrowthCandidate:
    return GrowthCandidate.create(
        site=SourceLocation("src/main/java/Fixture.java", line),
        kind="async_work_growth",
        operation="executor.execute(task)",
        resource_dimension="tasks",
        receiver="this.executor",
        field_path="this.executor",
        demand_inputs=(DemandInput("count", "submission_count"),),
        escape_scope="instance",
        evidence_ids=frozenset({"fact:growth"}),
    )


def _verified(candidate: GrowthCandidate) -> VerifiedGrowthResult:
    return VerifiedGrowthResult.create(
        candidate=candidate,
        slice_id="slice:resource-bridge",
        status="verified",
        reason_codes=(),
        checks=(VerificationCheck("resource_growth", True),),
    )


def _flow(entry: EntryFact, result: VerifiedGrowthResult):
    proof = FlowProof.create(
        entry_id=entry.entry_id,
        growth_id=result.growth_id,
        attacker_control=AttackerControl(
            "submission_count", "count", "count"
        ),
        call_path=(entry.handler.callable,),
        phase_sequence=("in_handler",),
        confidence="proven",
    )
    return verify_flow(
        proof, {entry.entry_id: entry}, {result.growth_id: result}
    )


def _create_fact() -> RawLifecycleFact:
    source = replace(location(), source_kind="static_verified")
    return RawLifecycleFact(
        "lifecycle-fact:" + "1" * 24,
        "resource_lifecycle",
        "a" * 64,
        "Fixture.handle",
        "java-callable-v1:Fixture.handle()V",
        "create",
        "Fixture.java:3:1",
        "fixture.Task",
        True,
        "none",
        "none",
        "none",
        "none",
        "unknown",
        True,
        True,
        "fixture create",
        "complete",
        "modeled create",
        source,
        source,
        1,
        1,
        "b" * 64,
        "point:Fixture.java:3:1:create",
        "none",
        0,
        -1,
        "unknown",
        "unknown",
        "unknown",
    )


def _dispatch_fact() -> RawLifecycleFact:
    return replace(
        _create_fact(),
        fact_id="lifecycle-fact:" + "2" * 24,
        query_name="resource_lifecycle_task_relations",
        site_callable="Fixture.handle",
        fact_kind="dispatch",
        holder_kind="queue",
        holder_scope="task",
        holder_key="this.executor",
        target_event="Fixture.task",
        program_point="point:Fixture.java:3:1:dispatch",
        related_point="point:Fixture.task:entry",
        capacity="3",
        max_workers="2",
        rejection_policy="abort",
    )


def _run(*, bounded: bool = True) -> ResourceLifecycleBackendRun:
    contract = executor_contract(
        queue_capacity=3 if bounded else None,
        max_workers=2 if bounded else None,
    )
    program = population_program()
    program = replace(
        program,
        task_bindings=tuple(
            replace(
                item,
                evidence_ids=(_dispatch_fact().fact_id,),
            )
            for item in program.task_bindings
        ),
    )
    unit = AnalysisUnit("Fixture.handle", program, (), (contract,))
    extracted = ExtractedFacts(
        "static_verified",
        "c" * 64,
        "fixture-v1",
        AnalysisBudget(max_steps=10000),
        (unit,),
        (_create_fact(), _dispatch_fact()),
        {
            "database_fingerprint": "9" * 64,
            "source_snapshot_sha256": "d" * 64,
        },
    )
    facts_sha256 = hashlib.sha256(
        canonical_json(extracted_to_dict(extracted)) + b"\n"
    ).hexdigest()
    return ResourceLifecycleBackendRun(
        extracted,
        _analyze_payload(extracted),
        "e" * 64,
        facts_sha256,
    )


def _run_with_facts(*facts: RawLifecycleFact) -> ResourceLifecycleBackendRun:
    base = _run()
    extracted = replace(base.extracted, facts=tuple(facts))
    return ResourceLifecycleBackendRun(
        extracted,
        base.results,
        base.implementation_sha256,
        hashlib.sha256(
            canonical_json(extracted_to_dict(extracted)) + b"\n"
        ).hexdigest(),
    )


def test_exact_dispatch_task_population_property_refutes_a2_growth() -> None:
    entry = _entry()
    result = _verified(_growth())
    decision = bind_resource_lifecycle_property(
        entry, result, _flow(entry, result), _run()
    )

    assert decision.resource_decision.status == "refutes_relevant_growth"
    assert decision.resource_decision.upper_bound == 5
    assert decision.record["submit_program_point"] == "point:Fixture.java:3:1:dispatch"
    assert decision.record["property_dimension"] == "accepted_task_population"
    assert decision.record["property_cut"] == "arbitrary_finite_repetitions"
    assert decision.record["property_scope"] == "executor:executor"
    assert decision.record["binding_status"] == "refutes_relevant_growth"
    validate_records("resource_lifecycle_bindings", [decision.record])


def test_unknown_population_property_forces_candidate_local_unknown() -> None:
    entry = _entry()
    result = _verified(_growth())
    decision = bind_resource_lifecycle_property(
        entry, result, _flow(entry, result), _run(bounded=False)
    )

    assert decision.resource_decision.status == "unresolved"
    assert decision.resource_decision.unresolved_facts == (
        "RESOURCE_PROPERTY_TASK_POPULATION_UNRESOLVED",
    )
    assert decision.record["property_status"] == "unknown"
    validate_records("resource_lifecycle_bindings", [decision.record])


def test_source_snapshot_coverage_gap_is_candidate_local_and_never_refutes() -> None:
    from dosweb.lifecycle.resource_properties import (
        ResourceLifecycleCoverageGap,
        bind_resource_lifecycle_coverage_gap,
    )

    entry = _entry()
    result = _verified(_growth())
    gap = ResourceLifecycleCoverageGap(
        database_fingerprint="9" * 64,
        source_snapshot_sha256="d" * 64,
        implementation_sha256="e" * 64,
    )
    decision = bind_resource_lifecycle_coverage_gap(
        entry, result, _flow(entry, result), gap
    )

    assert decision.resource_decision.status == "unresolved"
    assert decision.resource_decision.property_id is None
    assert decision.resource_decision.upper_bound is None
    assert decision.record["coverage_gaps"] == [gap.reason_code]
    assert decision.record["reason_code"] == gap.reason_code
    validate_records("resource_lifecycle_bindings", [decision.record])

    unrelated = _verified(
        GrowthCandidate.create(
            site=SourceLocation("src/main/java/Fixture.java", 3),
            kind="input_materialization",
            operation="readAllBytes()",
            resource_dimension="bytes",
            receiver="request",
            field_path="request.body",
            demand_inputs=(DemandInput("body", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:unrelated"}),
        )
    )
    unrelated_entry = EntryFact.create(
        framework="spring_mvc",
        protocol="http",
        handler=entry.handler,
        registration=entry.registration,
        registration_pattern_id=entry.registration_pattern_id,
        route_or_event="/submit",
        auth_context="unauthenticated",
        attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
        materialization_phase="in_handler",
    )
    unrelated_flow = verify_flow(
        FlowProof.create(
            entry_id=unrelated_entry.entry_id,
            growth_id=unrelated.growth_id,
            attacker_control=AttackerControl("size", "body", "body"),
            call_path=(entry.handler.callable,),
            phase_sequence=("in_handler",),
            confidence="proven",
        ),
        {unrelated_entry.entry_id: unrelated_entry},
        {unrelated.growth_id: unrelated},
    )
    unrelated_decision = bind_resource_lifecycle_coverage_gap(
        unrelated_entry, unrelated, unrelated_flow, gap
    )
    assert unrelated_decision.resource_decision.status == "not_applicable"
    assert unrelated_decision.resource_decision.unresolved_facts == ()


def test_line_without_exact_dispatch_never_binds_property() -> None:
    entry = _entry()
    result = _verified(_growth(line=4))
    decision = bind_resource_lifecycle_property(
        entry, result, _flow(entry, result), _run()
    )

    assert decision.resource_decision.status == "unresolved"
    assert decision.record["reason_code"] == "RESOURCE_PROPERTY_DISPATCH_MISSING"
    assert decision.record["property_id"] is None
    validate_records("resource_lifecycle_bindings", [decision.record])


def test_same_line_wrong_callable_or_receiver_never_binds() -> None:
    entry = _entry()
    result = _verified(_growth())
    flow = _flow(entry, result)
    for changed in (
        replace(_dispatch_fact(), site_callable="Fixture.other"),
        replace(_dispatch_fact(), holder_key="this.otherExecutor"),
    ):
        decision = bind_resource_lifecycle_property(
            entry,
            result,
            flow,
            _run_with_facts(_create_fact(), changed),
        )
        assert decision.resource_decision.status == "unresolved"
        assert decision.record["reason_code"] == "RESOURCE_PROPERTY_DISPATCH_MISSING"


def test_ambiguous_dispatch_program_point_never_binds() -> None:
    entry = _entry()
    result = _verified(_growth())
    second = replace(
        _dispatch_fact(),
        fact_id="lifecycle-fact:" + "3" * 24,
        site_start_column=9,
        program_point="point:Fixture.java:3:9:dispatch",
    )
    decision = bind_resource_lifecycle_property(
        entry,
        result,
        _flow(entry, result),
        _run_with_facts(_create_fact(), _dispatch_fact(), second),
    )
    assert decision.resource_decision.status == "unresolved"
    assert decision.record["reason_code"] == "RESOURCE_PROPERTY_DISPATCH_AMBIGUOUS"
