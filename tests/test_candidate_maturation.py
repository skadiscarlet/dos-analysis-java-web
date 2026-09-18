from __future__ import annotations

import pytest

from dosweb.artifacts.schemas import SCHEMA_VERSION, validate_records
from dosweb.errors import AnalyzerError
from dosweb.growth.completeness import (
    CandidateDisposition,
    CandidateNegativeProof,
)
from dosweb.pipeline import TOOL_VERSION


def test_schema_and_tool_versions_identify_maturation_artifacts() -> None:
    assert SCHEMA_VERSION == "2.8"
    assert TOOL_VERSION == "0.7.0"


def test_formal_and_gap_dispositions_preserve_canonical_association_state() -> None:
    formal = CandidateDisposition.create(
        "growth:formal",
        "formal_eligible",
        canonical_entry_id="entry:formal",
        local_growth_status="complete",
        association_status="complete",
        link_ids=("candidate_link:formal",),
        evidence_ids=("fact:growth", "candidate_link:formal"),
        negative_proof_ids=(),
        reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
    )
    gap = CandidateDisposition.create(
        "growth:gap",
        "gap_eligible",
        canonical_entry_id="entry:gap",
        local_growth_status="partial",
        association_status="partial",
        link_ids=("candidate_link:gap",),
        evidence_ids=("fact:growth", "candidate_link:gap"),
        negative_proof_ids=(),
        reason_codes=("MATURATION_GAP_ELIGIBLE",),
    )

    assert formal.status == "formal_eligible"
    assert gap.status == "gap_eligible"
    validate_records("candidate_dispositions", [formal.to_dict(), gap.to_dict()])


@pytest.mark.parametrize(
    ("local_growth_status", "association_status"),
    (("partial", "complete"), ("complete", "partial")),
)
def test_gap_disposition_requires_one_explicitly_partial_dimension(
    local_growth_status: str,
    association_status: str,
) -> None:
    disposition = CandidateDisposition.create(
        "growth:gap-matrix",
        "gap_eligible",
        canonical_entry_id="entry:gap-matrix",
        local_growth_status=local_growth_status,
        association_status=association_status,
        link_ids=("candidate_link:gap-matrix",),
        evidence_ids=("candidate_link:gap-matrix", "fact:growth"),
        negative_proof_ids=(),
        reason_codes=("MATURATION_GAP_ELIGIBLE",),
    )

    assert disposition.status == "gap_eligible"


def test_gap_disposition_rejects_all_complete_evidence() -> None:
    with pytest.raises(AnalyzerError):
        CandidateDisposition.create(
            "growth:gap-all-complete",
            "gap_eligible",
            canonical_entry_id="entry:gap-all-complete",
            local_growth_status="complete",
            association_status="complete",
            link_ids=("candidate_link:gap-all-complete",),
            evidence_ids=("candidate_link:gap-all-complete", "fact:growth"),
            negative_proof_ids=(),
            reason_codes=("MATURATION_GAP_ELIGIBLE",),
        )


@pytest.mark.parametrize(
    ("local_growth_status", "association_status", "accepted"),
    (
        ("complete", "complete", True),
        ("partial", "complete", False),
        ("complete", "partial", False),
    ),
)
def test_formal_disposition_requires_both_dimensions_complete(
    local_growth_status: str,
    association_status: str,
    accepted: bool,
) -> None:
    def create() -> CandidateDisposition:
        return CandidateDisposition.create(
            "growth:formal-matrix",
            "formal_eligible",
            canonical_entry_id="entry:formal-matrix",
            local_growth_status=local_growth_status,
            association_status=association_status,
            link_ids=("candidate_link:formal-matrix",),
            evidence_ids=("candidate_link:formal-matrix", "fact:growth"),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )

    if accepted:
        assert create().status == "formal_eligible"
    else:
        with pytest.raises(AnalyzerError):
            create()


def test_rejected_disposition_references_a_deterministic_negative_proof() -> None:
    proof = CandidateNegativeProof.create(
        "growth:negative",
        "non_retained_owner",
        evidence_ids=("fact:local-owner",),
        reason_codes=("NEGATIVE_NON_RETAINED_OWNER",),
    )
    disposition = CandidateDisposition.create(
        "growth:negative",
        "rejected",
        canonical_entry_id="entry:negative",
        local_growth_status="rejected",
        association_status="complete",
        link_ids=("candidate_link:negative",),
        evidence_ids=(proof.negative_proof_id,),
        negative_proof_ids=(proof.negative_proof_id,),
        reason_codes=("MATURATION_SOURCE_PROVEN_NEGATIVE",),
    )

    validate_records("candidate_negative_proofs", [proof.to_dict()])
    validate_records("candidate_dispositions", [disposition.to_dict()])


def test_rejected_disposition_cannot_hide_undeclared_negative_proof_evidence() -> None:
    first = CandidateNegativeProof.create(
        "growth:negative",
        "server_controlled_source",
        evidence_ids=("fact:first",),
        reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
    )
    second = CandidateNegativeProof.create(
        "growth:negative",
        "non_retained_owner",
        evidence_ids=("fact:second",),
        reason_codes=("NEGATIVE_NON_RETAINED_OWNER",),
    )

    with pytest.raises(Exception):
        CandidateDisposition.create(
            "growth:negative",
            "rejected",
            canonical_entry_id="",
            local_growth_status="rejected",
            association_status="missing",
            link_ids=(),
            evidence_ids=(first.negative_proof_id, second.negative_proof_id),
            negative_proof_ids=(first.negative_proof_id,),
            reason_codes=("MATURATION_SOURCE_PROVEN_NEGATIVE",),
        )


def test_rejected_disposition_cannot_substitute_ordinary_evidence_for_negative_proof() -> None:
    with pytest.raises(Exception):
        CandidateDisposition.create(
            "growth:negative",
            "rejected",
            canonical_entry_id="entry:negative",
            local_growth_status="rejected",
            association_status="complete",
            link_ids=("candidate_link:negative",),
            evidence_ids=("fact:ordinary",),
            negative_proof_ids=(),
            reason_codes=("MATURATION_SOURCE_PROVEN_NEGATIVE",),
        )


def test_non_rejected_dispositions_cannot_carry_negative_proofs() -> None:
    with pytest.raises(Exception):
        CandidateDisposition.create(
            "growth:inventory",
            "inventory_unresolved",
            canonical_entry_id="",
            local_growth_status="unknown",
            association_status="ambiguous",
            link_ids=(),
            evidence_ids=("fact:growth", "negative_proof:unexpected"),
            negative_proof_ids=("negative_proof:unexpected",),
            reason_codes=("MATURATION_INVENTORY_UNRESOLVED",),
        )


@pytest.mark.parametrize(
    "evidence_id",
    ("reachability:decision", "fact:", "fact:not/source-backed"),
)
def test_negative_proof_requires_source_backed_growth_fact_ids(
    evidence_id: str,
) -> None:
    with pytest.raises(Exception):
        CandidateNegativeProof.create(
            "growth:negative",
            "server_controlled_source",
            evidence_ids=(evidence_id,),
            reason_codes=("NEGATIVE_SERVER_CONTROLLED_SOURCE",),
        )


def test_not_entry_reachable_negative_proof_has_a_growth_typed_kind() -> None:
    proof = CandidateNegativeProof.create(
        "growth:negative",
        "not_entry_reachable",
        evidence_ids=("fact:growth",),
        reason_codes=("NEGATIVE_NOT_ENTRY_REACHABLE",),
    )
    assert proof.kind == "not_entry_reachable"


def test_inventory_unresolved_cannot_masquerade_as_a_formal_pair() -> None:
    inventory = CandidateDisposition.create(
        "growth:inventory",
        "inventory_unresolved",
        canonical_entry_id="",
        local_growth_status="unknown",
        association_status="ambiguous",
        link_ids=(),
        evidence_ids=("fact:growth",),
        negative_proof_ids=(),
        reason_codes=("MATURATION_ASSOCIATION_AMBIGUOUS",),
    )
    assert inventory.canonical_entry_id == ""
    with pytest.raises(Exception):
        CandidateDisposition.create(
            "growth:bad",
            "formal_eligible",
            canonical_entry_id="",
            local_growth_status="complete",
            association_status="complete",
            link_ids=(),
            evidence_ids=("fact:growth",),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )
