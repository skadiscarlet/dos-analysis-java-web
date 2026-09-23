"""Synthetic proof preservation through the production consuming interfaces."""
from dataclasses import replace
import json
import pytest
from dosweb.artifacts.identifiers import stable_identifier
from dosweb.conclude import CandidateCoverage, derive_verdict, evaluate_assertion_1, evaluate_assertion_2
from dosweb.entries import FrameworkCoverage
from dosweb.errors import AnalyzerError
from dosweb.lifecycle import GuardDecision
from dosweb.lifecycle.certificates import LifecycleCertificate, StaticFinding, build_lifecycle_certificate
from dosweb.lifecycle.resource_properties import bind_resource_lifecycle_property, validate_resource_binding
from dosweb.report.families import build_finding_families
from dosweb.report.markdown import render_report
from dosweb.report.summary import build_summary
from tests.test_resource_lifecycle_binding_consumer_isolation import context, no_bound, no_release
from tests.test_resource_lifecycle_production_bridge import _run


def certificate_context():
    entry, growth, flow, decision = context()
    guard = GuardDecision('ineffective', ('GUARD_ABSENT',), (), (), (), ())
    bound, release = no_bound(), no_release()
    coverage = CandidateCoverage(entry.framework, 'complete', (entry.registration_pattern_id,), (), 'none', entry.registration_pattern_id, entry.entry_id, growth.growth_id, flow.path_id)
    assertions = (
        evaluate_assertion_1(growth, flow, guard, bound, resource_lifecycle=decision),
        evaluate_assertion_2(growth, flow, bound, release, resource_lifecycle=decision),
    )
    verdict = derive_verdict(assertions, coverage)
    cert = build_lifecycle_certificate(entry, growth, (flow,), guard, bound, release, assertions, coverage, verdict, resource_lifecycle={flow.path_id:decision})
    return entry, growth, flow, decision, assertions, verdict, cert


def test_nontrivial_solver_meaning_reaches_certificate_and_report():
    entry, growth, flow, decision, assertions, verdict, cert = certificate_context()
    binding = bind_resource_lifecycle_property(entry, growth, flow, _run())
    validate_resource_binding(decision, binding.record)
    expected = set(binding.record['assumptions'])
    assert len(expected) >= 2
    assert expected == set(decision.assumptions)
    assert expected.issubset({a for assertion in assertions for a in assertion.assumptions})
    assert expected.issubset(verdict.assumptions)
    assert expected.issubset(cert.assumptions)
    assert verdict.verdict == cert.verdict == 'bounded_under_modeled_assumptions'
    finding = StaticFinding.from_certificate(cert)
    families = build_finding_families((finding,), (cert,), {entry.entry_id:entry}, {}, {})
    summary = build_summary(families, (finding,), (FrameworkCoverage(entry.framework, 'complete', (entry.registration_pattern_id,), (), 'none'),))
    report = render_report(summary, families, (finding,), (cert,))
    assert all(a in report for a in expected)
    assert 'Modeled assumptions in lifecycle certificates' in report


@pytest.mark.parametrize('field,value', [('assumptions', ('unproven assumption instead',)), ('upper_bound', 999)])
def test_in_memory_mutation_cannot_keep_old_decision_id(field, value):
    _, growth, flow, decision = context()
    result = evaluate_assertion_2(growth, flow, no_bound(), no_release(), resource_lifecycle=replace(decision, **{field:value}))
    assert result.status == 'unknown'


def test_binding_cannot_be_swapped_even_after_rehashing_it():
    entry, growth, flow, decision = context()
    record = dict(bind_resource_lifecycle_property(entry, growth, flow, _run()).record)
    record['assumptions'] = ['unrelated execution semantics']
    with pytest.raises(AnalyzerError):
        validate_resource_binding(decision, record)
    record['binding_id'] = stable_identifier('resource-binding', {k:v for k,v in record.items() if k!='binding_id'})
    with pytest.raises(AnalyzerError):
        validate_resource_binding(decision, record)


def test_missing_binding_cannot_support_a_consumed_proof():
    _, _, _, decision = context()
    with pytest.raises(AnalyzerError):
        validate_resource_binding(decision, None)


def test_certificate_cannot_remove_assumptions_even_when_rehashed():
    *_, cert = certificate_context()
    record = cert.to_dict()
    record['assumptions'] = ['MODELED_DEFAULT_CONFIGURATION', 'STATIC_EVIDENCE_COVERAGE_COMPLETE']
    record['certificate_id'] = stable_identifier('certificate', {k:v for k,v in record.items() if k!='certificate_id'})
    for field in ['attacker_inputs','path_ids','resource_lifecycle_decisions','assertions','reason_codes','assumptions','coverage_gaps','unresolved_facts','suggested_follow_up_measurements']:
        record[field] = tuple(record[field])
    with pytest.raises(AnalyzerError, match='assumptions'):
        LifecycleCertificate(**record)


def test_old_resource_record_is_not_silently_promoted():
    from dosweb.lifecycle.resource_properties import ResourceLifecycleDecision
    *_, decision = context()
    record = decision.to_dict()
    for field in ['assumptions','entry_id','growth_id','path_id']:
        record.pop(field)
    with pytest.raises(AnalyzerError):
        ResourceLifecycleDecision.from_dict(record)
