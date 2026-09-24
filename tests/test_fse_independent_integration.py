"""Independent synthetic integration: route facts -> reach -> solver -> certificate.

All facts are synthetic. These tests do not run Java, CodeQL, network requests,
third-party targets, or the analyzer's remote classifier.
"""
from __future__ import annotations

import pytest

from dosweb.conclude import CandidateCoverage, derive_verdict, evaluate_assertion_1, evaluate_assertion_2
from dosweb.entries import EntryFact, FrameworkCoverage
from dosweb.lifecycle import GuardDecision
from dosweb.lifecycle.certificates import StaticFinding, build_lifecycle_certificate
from dosweb.lifecycle.resource_properties import bind_resource_lifecycle_property
from dosweb.reachability import AuthContract, EntrySecurityFact
from dosweb.reachability.extract import bind_entry_security_rows
from dosweb.reachability.verify import derive_auth_contract_from_facts, verify_auth_contract
from dosweb.report.families import build_finding_families
from dosweb.report.markdown import render_report
from dosweb.report.summary import build_summary
from tests.test_resource_lifecycle_binding_consumer_isolation import no_bound, no_release
from tests.test_resource_lifecycle_production_bridge import _entry, _flow, _growth, _run, _verified


def _aliases() -> tuple[EntryFact, EntryFact]:
    base = _entry()
    return tuple(EntryFact.create(
        framework=base.framework, protocol=base.protocol, handler=base.handler,
        registration=base.registration, registration_pattern_id=base.registration_pattern_id,
        route_or_event=route, auth_context="unknown", attacker_inputs=base.attacker_inputs,
        materialization_phase=base.materialization_phase,
    ) for route in ("GET /work", "POST /work"))


def _typed_row(entry: EntryFact, **changes: object) -> dict[str, object]:
    return {
        "handler_fqn": entry.handler.callable, "handler_file": entry.handler.file,
        "handler_start_line": entry.handler.start_line, "route_or_event": "",
        "fact_file": entry.handler.file, "fact_start_line": entry.handler.start_line,
        "kind": "annotation", "value": "unauthenticated_annotation",
        "coverage_status": "complete", "coverage_note": "synthetic_typed_annotation",
        **changes,
    }


def _reach(entry: EntryFact, facts: tuple[EntrySecurityFact, ...]):
    local = tuple(f for f in facts if f.entry_id == entry.entry_id)
    contract = derive_auth_contract_from_facts(entry.entry_id, local)
    if contract is None:
        contract = AuthContract("unknown", (), ("synthetic_unresolved_auth",), "low")
    return verify_auth_contract(entry.entry_id, contract, local,
        slice_fact_ids=frozenset(f.fact_id for f in local))


@pytest.mark.parametrize("mode", ["complete", "auth_partial", "auth_conflict", "deployment_partial"])
def test_repaired_alias_binding_reaches_real_solver_and_retains_proof_gates(mode):
    entries = _aliases()
    auth_coverage = "partial" if mode == "auth_partial" else "complete"
    gate_coverage = "partial" if mode == "deployment_partial" else "complete"
    rows = [
        _typed_row(entries[0], coverage_status=auth_coverage),
        _typed_row(entries[0], kind="deployment_gate", value="default_enabled",
                   coverage_status=gate_coverage, fact_start_line=2),
    ]
    if mode == "auth_conflict":
        rows.append(_typed_row(entries[0], value="privileged_annotation", fact_start_line=4))
    facts = bind_entry_security_rows(rows, [e.to_dict() for e in entries])
    growth, backend = _verified(_growth()), _run()
    decisions = []
    for entry in entries:
        reach = _reach(entry, facts)
        flow = _flow(entry, growth)
        bound = bind_resource_lifecycle_property(entry, growth, flow, backend)
        decision = bound.resource_decision
        assert decision.status == "refutes_relevant_growth"
        decisions.append(decision)
        guard = GuardDecision("ineffective", ("GUARD_ABSENT",), (), (), (), ())
        assertions = (
            evaluate_assertion_1(growth, flow, guard, no_bound(), reachability=reach, resource_lifecycle=decision),
            evaluate_assertion_2(growth, flow, no_bound(), no_release(), reachability=reach, resource_lifecycle=decision),
        )
        coverage = CandidateCoverage(entry.framework, "complete", (entry.registration_pattern_id,), (), "none",
                                     entry.registration_pattern_id, entry.entry_id, growth.growth_id, flow.path_id)
        verdict = derive_verdict(assertions, coverage)
        if mode != "complete":
            assert reach.status == "unknown"
            assert all(a.status == "unknown" for a in assertions)
            assert verdict.verdict == "static_unknown"
            continue
        assert reach.status == "ordinary_attacker_reachable"
        assert assertions[1].status == "refuted"
        assert verdict.verdict == "bounded_under_modeled_assumptions"
        cert = build_lifecycle_certificate(entry, growth, (flow,), guard, no_bound(), no_release(),
            assertions, coverage, verdict, resource_lifecycle={flow.path_id: decision})
        assert set(decision.assumptions).issubset(cert.assumptions)
        finding = StaticFinding.from_certificate(cert)
        families = build_finding_families((finding,), (cert,), {entry.entry_id: entry}, {}, {})
        summary = build_summary(families, (finding,),
            (FrameworkCoverage(entry.framework, "complete", (entry.registration_pattern_id,), (), "none"),))
        report = render_report(summary, families, (finding,), (cert,))
        assert all(assumption in report for assumption in decision.assumptions)
    assert decisions[0].decision_id != decisions[1].decision_id


def test_method_scoped_conflict_does_not_pollute_other_alias():
    entries = _aliases()
    rows = [_typed_row(entries[0]), _typed_row(entries[0], kind="deployment_gate", value="default_enabled", fact_start_line=2),
            _typed_row(entries[0], kind="security_filter_chain", value="privileged_filter",
                       route_or_event="POST /work", fact_start_line=4)]
    facts = bind_entry_security_rows(rows, [entry.to_dict() for entry in entries])
    first, second = (_reach(entry, facts) for entry in entries)
    assert first.status == "ordinary_attacker_reachable"
    assert second.status == "unknown"
    assert "REACH_AUTH_CONFLICT" in second.reason_codes
    assert "REACH_AUTH_CONFLICT" not in first.reason_codes
