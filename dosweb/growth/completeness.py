"""Fail-closed candidate association and applicability decisions.

These records deliberately sit between raw CodeQL screening and formal findings.  They
make every candidate's disposition auditable without expanding the public verdict set.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError

_Association = frozenset({"complete", "partial"})
_Disposition = frozenset(
    {
        "formal_eligible",
        "gap_eligible",
        "rejected",
        "inventory_unresolved",
    }
)
_LocalGrowthStatus = frozenset({"complete", "partial", "rejected", "unknown"})
_AssociationStatus = frozenset({"complete", "partial", "missing", "ambiguous"})
_NegativeProofKinds = frozenset(
    {
        "server_controlled_source",
        "non_retained_owner",
        "finite_keyspace",
        "generated_or_test_only",
        "guaranteed_synchronous_cleanup",
        "effective_local_bound",
        "false_entry_growth_flow",
        "not_entry_reachable",
    }
)
_Decision = frozenset({"proven", "unknown", "not_applicable"})


def _strings(values: tuple[str, ...], name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, tuple) or (not allow_empty and not values) or any(not isinstance(v, str) or not v for v in values):
        raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", f"{name} is invalid.")
    result = tuple(sorted(set(values)))
    if result != values:
        raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", f"{name} must be deterministic.")
    return result


def _source_backed_fact_id(value: str) -> bool:
    suffix = value[5:] if value.startswith("fact:") else ""
    return bool(suffix) and all(
        character
        in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
        for character in suffix
    )


@dataclass(frozen=True)
class CandidateEntryLink:
    link_id: str
    growth_id: str
    entry_id: str
    status: Literal["complete", "partial"]
    evidence_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.growth_id, str) or not self.growth_id.startswith("growth:") or not isinstance(self.entry_id, str) or not self.entry_id.startswith("entry:") or self.status not in _Association:
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Candidate entry link is invalid.")
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes, "reason_codes"))
        expected = stable_identifier("candidate_link", self.semantic_identity)
        if self.link_id != expected:
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Candidate entry link id is invalid.")

    @property
    def semantic_identity(self) -> dict[str, object]:
        return {"growth_id": self.growth_id, "entry_id": self.entry_id, "status": self.status, "evidence_ids": list(self.evidence_ids), "reason_codes": list(self.reason_codes)}

    @classmethod
    def create(cls, growth_id: str, entry_id: str, status: Literal["complete", "partial"], evidence_ids: tuple[str, ...], reason_codes: tuple[str, ...]) -> "CandidateEntryLink":
        semantic = {"growth_id": growth_id, "entry_id": entry_id, "status": status, "evidence_ids": list(tuple(sorted(set(evidence_ids)))), "reason_codes": list(tuple(sorted(set(reason_codes))))}
        return cls(stable_identifier("candidate_link", semantic), growth_id, entry_id, status, tuple(sorted(set(evidence_ids))), tuple(sorted(set(reason_codes))))

    def to_dict(self) -> dict[str, object]:
        return {"link_id": self.link_id, **self.semantic_identity}


@dataclass(frozen=True)
class CandidateNegativeProof:
    negative_proof_id: str
    growth_id: str
    kind: Literal[
        "server_controlled_source",
        "non_retained_owner",
        "finite_keyspace",
        "generated_or_test_only",
        "guaranteed_synchronous_cleanup",
        "effective_local_bound",
        "false_entry_growth_flow",
        "not_entry_reachable",
    ]
    evidence_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.growth_id, str)
            or not self.growth_id.startswith("growth:")
            or self.kind not in _NegativeProofKinds
        ):
            raise AnalyzerError(
                "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
                "Candidate negative proof is invalid.",
            )
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes, "reason_codes"))
        if any(not _source_backed_fact_id(item) for item in self.evidence_ids):
            raise AnalyzerError(
                "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
                "Candidate negative proof evidence must be source-backed Growth facts.",
            )
        expected = stable_identifier("negative_proof", self.semantic_identity)
        if self.negative_proof_id != expected:
            raise AnalyzerError(
                "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
                "Candidate negative proof id is invalid.",
            )

    @property
    def semantic_identity(self) -> dict[str, object]:
        return {
            "growth_id": self.growth_id,
            "kind": self.kind,
            "evidence_ids": list(self.evidence_ids),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def create(
        cls,
        growth_id: str,
        kind: Literal[
            "server_controlled_source",
            "non_retained_owner",
            "finite_keyspace",
            "generated_or_test_only",
            "guaranteed_synchronous_cleanup",
            "effective_local_bound",
            "false_entry_growth_flow",
            "not_entry_reachable",
        ],
        *,
        evidence_ids: tuple[str, ...],
        reason_codes: tuple[str, ...],
    ) -> "CandidateNegativeProof":
        semantic = {
            "growth_id": growth_id,
            "kind": kind,
            "evidence_ids": list(tuple(sorted(set(evidence_ids)))),
            "reason_codes": list(tuple(sorted(set(reason_codes)))),
        }
        return cls(
            stable_identifier("negative_proof", semantic),
            growth_id,
            kind,
            tuple(sorted(set(evidence_ids))),
            tuple(sorted(set(reason_codes))),
        )

    def to_dict(self) -> dict[str, object]:
        return {"negative_proof_id": self.negative_proof_id, **self.semantic_identity}


@dataclass(frozen=True)
class CandidateDisposition:
    disposition_id: str
    growth_id: str
    status: Literal[
        "formal_eligible",
        "gap_eligible",
        "rejected",
        "inventory_unresolved",
    ]
    canonical_entry_id: str
    local_growth_status: Literal["complete", "partial", "rejected", "unknown"]
    association_status: Literal["complete", "partial", "missing", "ambiguous"]
    link_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    negative_proof_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.growth_id, str)
            or not self.growth_id.startswith("growth:")
            or self.status not in _Disposition
            or self.local_growth_status not in _LocalGrowthStatus
            or self.association_status not in _AssociationStatus
            or not isinstance(self.canonical_entry_id, str)
            or (
                self.canonical_entry_id
                and not self.canonical_entry_id.startswith("entry:")
            )
        ):
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Candidate disposition is invalid.")
        object.__setattr__(self, "link_ids", _strings(self.link_ids, "link_ids", allow_empty=True))
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "negative_proof_ids", _strings(self.negative_proof_ids, "negative_proof_ids", allow_empty=True))
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes, "reason_codes"))
        if any(not item.startswith("negative_proof:") for item in self.negative_proof_ids):
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Candidate negative proof reference is invalid.")
        if self.status in {"formal_eligible", "gap_eligible"} and (
            len(self.link_ids) != 1 or not self.canonical_entry_id
        ):
            raise AnalyzerError(
                "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
                "Eligible candidate needs one canonical Entry association.",
            )
        if self.status == "formal_eligible" and (
            self.local_growth_status != "complete"
            or self.association_status != "complete"
            or self.negative_proof_ids
        ):
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Formal candidate evidence is incomplete.")
        if self.status == "gap_eligible" and (
            self.local_growth_status not in {"complete", "partial"}
            or self.association_status not in {"complete", "partial"}
            or (
                self.local_growth_status == "complete"
                and self.association_status == "complete"
            )
            or self.negative_proof_ids
        ):
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Gap candidate evidence is invalid.")
        cited_negative_proofs = {
            item for item in self.evidence_ids if item.startswith("negative_proof:")
        }
        if self.status == "rejected" and (
            not self.negative_proof_ids
            or set(self.negative_proof_ids) != cited_negative_proofs
        ):
            raise AnalyzerError(
                "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
                "Rejected candidate must cite deterministic negative proof records.",
            )
        if self.status != "rejected" and (
            self.negative_proof_ids or cited_negative_proofs
        ):
            raise AnalyzerError(
                "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
                "Non-rejected candidate cannot carry negative proof records.",
            )
        expected = stable_identifier("disposition", self.semantic_identity)
        if self.disposition_id != expected:
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Candidate disposition id is invalid.")

    @property
    def semantic_identity(self) -> dict[str, object]:
        return {
            "growth_id": self.growth_id,
            "status": self.status,
            "canonical_entry_id": self.canonical_entry_id,
            "local_growth_status": self.local_growth_status,
            "association_status": self.association_status,
            "link_ids": list(self.link_ids),
            "evidence_ids": list(self.evidence_ids),
            "negative_proof_ids": list(self.negative_proof_ids),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def create(
        cls,
        growth_id: str,
        status: Literal[
            "formal_eligible",
            "gap_eligible",
            "rejected",
            "inventory_unresolved",
        ],
        *,
        canonical_entry_id: str,
        local_growth_status: Literal["complete", "partial", "rejected", "unknown"],
        association_status: Literal["complete", "partial", "missing", "ambiguous"],
        link_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        negative_proof_ids: tuple[str, ...],
        reason_codes: tuple[str, ...],
    ) -> "CandidateDisposition":
        semantic = {
            "growth_id": growth_id,
            "status": status,
            "canonical_entry_id": canonical_entry_id,
            "local_growth_status": local_growth_status,
            "association_status": association_status,
            "link_ids": list(tuple(sorted(set(link_ids)))),
            "evidence_ids": list(tuple(sorted(set(evidence_ids)))),
            "negative_proof_ids": list(tuple(sorted(set(negative_proof_ids)))),
            "reason_codes": list(tuple(sorted(set(reason_codes)))),
        }
        return cls(
            stable_identifier("disposition", semantic),
            growth_id,
            status,
            canonical_entry_id,
            local_growth_status,
            association_status,
            tuple(sorted(set(link_ids))),
            tuple(sorted(set(evidence_ids))),
            tuple(sorted(set(negative_proof_ids))),
            tuple(sorted(set(reason_codes))),
        )

    def to_dict(self) -> dict[str, object]: return {"disposition_id": self.disposition_id, **self.semantic_identity}


@dataclass(frozen=True)
class ApplicabilityDecision:
    decision_id: str
    entry_id: str
    growth_id: str
    status: Literal["proven", "unknown", "not_applicable"]
    evidence_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    kind: Literal["repeatability", "amplification"]

    def __post_init__(self) -> None:
        if self.kind not in {"repeatability", "amplification"} or self.status not in _Decision or not self.entry_id.startswith("entry:") or not self.growth_id.startswith("growth:"):
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Applicability decision is invalid.")
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes, "reason_codes"))
        if self.decision_id != stable_identifier("reachability", {"kind": self.kind, **self.semantic_identity}):
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Applicability decision id is invalid.")

    @property
    def semantic_identity(self) -> dict[str, object]: return {"entry_id": self.entry_id, "growth_id": self.growth_id, "status": self.status, "evidence_ids": list(self.evidence_ids), "reason_codes": list(self.reason_codes)}
    @classmethod
    def create(cls, kind: Literal["repeatability", "amplification"], entry_id: str, growth_id: str, status: Literal["proven", "unknown", "not_applicable"], evidence_ids: tuple[str, ...], reason_codes: tuple[str, ...]) -> "ApplicabilityDecision":
        semantic = {"entry_id": entry_id, "growth_id": growth_id, "status": status, "evidence_ids": list(tuple(sorted(set(evidence_ids)))), "reason_codes": list(tuple(sorted(set(reason_codes))))}
        return cls(stable_identifier("reachability", {"kind": kind, **semantic}), entry_id, growth_id, status, tuple(sorted(set(evidence_ids))), tuple(sorted(set(reason_codes))), kind)
    def to_dict(self) -> dict[str, object]: return {"decision_id": self.decision_id, **self.semantic_identity}

RepeatabilityDecision = ApplicabilityDecision
AmplificationDecision = ApplicabilityDecision
