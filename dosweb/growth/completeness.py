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
_Disposition = frozenset({"rejected", "verified_relevant", "not_entry_reachable", "unresolved"})
_Decision = frozenset({"proven", "unknown", "not_applicable"})


def _strings(values: tuple[str, ...], name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, tuple) or (not allow_empty and not values) or any(not isinstance(v, str) or not v for v in values):
        raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", f"{name} is invalid.")
    result = tuple(sorted(set(values)))
    if result != values:
        raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", f"{name} must be deterministic.")
    return result


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
class CandidateDisposition:
    disposition_id: str
    growth_id: str
    status: Literal["rejected", "verified_relevant", "not_entry_reachable", "unresolved"]
    link_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.growth_id, str) or not self.growth_id.startswith("growth:") or self.status not in _Disposition:
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Candidate disposition is invalid.")
        object.__setattr__(self, "link_ids", _strings(self.link_ids, "link_ids", allow_empty=True))
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes, "reason_codes"))
        if self.status == "verified_relevant" and not self.link_ids:
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Relevant candidate needs an entry link.")
        expected = stable_identifier("disposition", self.semantic_identity)
        if self.disposition_id != expected:
            raise AnalyzerError("ANALYSIS_CANDIDATE_COMPLETENESS_INVALID", "Candidate disposition id is invalid.")

    @property
    def semantic_identity(self) -> dict[str, object]:
        return {"growth_id": self.growth_id, "status": self.status, "link_ids": list(self.link_ids), "reason_codes": list(self.reason_codes)}

    @classmethod
    def create(cls, growth_id: str, status: Literal["rejected", "verified_relevant", "not_entry_reachable", "unresolved"], link_ids: tuple[str, ...], reason_codes: tuple[str, ...]) -> "CandidateDisposition":
        semantic = {"growth_id": growth_id, "status": status, "link_ids": list(tuple(sorted(set(link_ids)))), "reason_codes": list(tuple(sorted(set(reason_codes))))}
        return cls(stable_identifier("disposition", semantic), growth_id, status, tuple(sorted(set(link_ids))), tuple(sorted(set(reason_codes))))

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
