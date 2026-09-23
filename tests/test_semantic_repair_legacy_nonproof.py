"""Offline compatibility tests: reconstruct non-proofs, never accept stale bounds."""
from copy import deepcopy
import pytest
from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError
from dosweb.growth import GrowthCandidate, DemandInput
from dosweb.flows import FlowProof, AttackerControl, verify_flow
from dosweb.lifecycle.resource_properties import (
    bind_resource_lifecycle_property, ResourceLifecycleDecision,
    load_resource_decision_for_context,
)
from tests.test_resource_lifecycle_production_bridge import _entry, _growth, _verified, _flow, _run


def fixture(kind="unresolved"):
    entry = _entry()
    candidate = _growth(line=4 if kind == "unresolved" else 3)
    if kind == "not_applicable":
        candidate = GrowthCandidate.create(site=candidate.site, kind="direct_allocation",
            operation="allocate(count)", resource_dimension="bytes", receiver="buffer",
            field_path="buffer", demand_inputs=(DemandInput("count", "size"),),
            escape_scope="request", evidence_ids=frozenset({"fact:allocation"}))
    growth = _verified(candidate)
    flow = _flow(entry, growth)
    if kind == "not_applicable":
        proof = FlowProof.create(entry_id=entry.entry_id, growth_id=growth.growth_id,
            attacker_control=AttackerControl("size", "count", "count"),
            call_path=(entry.handler.callable,), phase_sequence=("in_handler",), confidence="proven")
        flow = verify_flow(proof, {entry.entry_id: entry}, {growth.growth_id: growth})
        assert flow.satisfies_premise
    result = bind_resource_lifecycle_property(entry, growth, flow, _run())
    context = dict(entry_id=entry.entry_id, growth_id=growth.growth_id, path_id=flow.path_id)
    return result.resource_decision.to_dict(), dict(result.record), context


def legacy(record):
    result = {key: value for key, value in record.items()
              if key not in {"decision_id", "assumptions", "entry_id", "growth_id", "path_id"}}
    return {"decision_id": stable_identifier("resource-decision", result), **result}


@pytest.mark.parametrize("kind", ["unresolved", "not_applicable"])
def test_exact_legacy_nonproof_reconstructed_without_promoting_or_mutating(kind):
    modern, binding, context = fixture(kind)
    assert modern["status"] == kind
    old = legacy(modern)
    original = deepcopy((old, binding))
    with pytest.raises(AnalyzerError):
        ResourceLifecycleDecision.from_dict(old)
    result = load_resource_decision_for_context(old, binding, **context)
    assert result.status == kind and result.property_id is None and result.upper_bound is None
    assert result.assumptions == () and result.decision_id != old["decision_id"]
    assert result.to_dict() == modern
    assert (old, binding) == original


def test_current_bounded_still_requires_and_preserves_full_binding():
    modern, binding, context = fixture("bounded")
    assert modern["status"] == "refutes_relevant_growth"
    assert load_resource_decision_for_context(modern, binding, **context).to_dict() == modern
    with pytest.raises(AnalyzerError):
        load_resource_decision_for_context(legacy(modern), binding, **context)


@pytest.mark.parametrize("change", ["old_id", "binding", "context", "partial_current", "nonproof_with_bound", "missing_binding"])
def test_malformed_stale_or_mismatched_evidence_is_not_migrated(change):
    modern, binding, context = fixture()
    old = legacy(modern)
    if change == "old_id":
        old["reason_codes"] = ["CHANGED_WITH_OLD_ID"]
    elif change == "binding":
        binding["growth_id"] = "growth:other"
    elif change == "context":
        context["growth_id"] = "growth:other"
    elif change == "partial_current":
        old = modern.copy()
        del old["assumptions"]
    elif change == "nonproof_with_bound":
        old["upper_bound"] = 5
        old["decision_id"] = stable_identifier("resource-decision", {k:v for k,v in old.items() if k != "decision_id"})
    elif change == "missing_binding":
        binding = None
    with pytest.raises(AnalyzerError):
        load_resource_decision_for_context(old, binding, **context)
