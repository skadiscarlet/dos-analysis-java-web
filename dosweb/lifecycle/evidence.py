"""Path-bound lifecycle evidence and coverage contracts.

Raw CodeQL lifecycle rows are screening evidence only.  They become usable only
when this module binds them to one concrete E->G path and records the coverage
that made the binding possible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError

Family = Literal["guard", "bound", "release"]
Coverage = Literal["complete", "partial", "unsupported"]


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value.encode()) > 1024:
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", f"Lifecycle {name} is invalid.")
    return value


@dataclass(frozen=True)
class LifecycleCoverage:
    entry_id: str
    growth_id: str
    path_id: str
    family: Family
    status: Coverage
    reason: str
    coverage_id: str = ""

    def __post_init__(self) -> None:
        if self.family not in {"guard", "bound", "release"} or self.status not in {"complete", "partial", "unsupported"}:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle coverage enum is invalid.")
        for name in ("entry_id", "growth_id", "path_id", "reason"):
            _text(getattr(self, name), name)
        expected = stable_identifier("lifecycle-coverage", self.semantic_identity())
        if self.coverage_id and self.coverage_id != expected:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle coverage identifier is not canonical.")
        object.__setattr__(self, "coverage_id", expected)

    def semantic_identity(self) -> dict[str, object]:
        return {"entry_id": self.entry_id, "growth_id": self.growth_id, "path_id": self.path_id, "family": self.family, "status": self.status, "reason": self.reason}

    def to_dict(self) -> dict[str, object]:
        return {"coverage_id": self.coverage_id, **self.semantic_identity()}

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "LifecycleCoverage":
        if set(raw) != {"coverage_id", "entry_id", "growth_id", "path_id", "family", "status", "reason"}:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle coverage record is malformed.")
        return cls(**raw)  # type: ignore[arg-type]


@dataclass(frozen=True)
class LifecycleSummary:
    entry_id: str
    growth_id: str
    path_id: str
    family: Family
    candidate_file: str
    candidate_start_line: int
    callsite_file: str
    callsite_start_line: int
    receiver_file: str
    receiver_start_line: int
    argument_index: int
    resource_dimension: str
    scope: str
    configuration_key: str
    configuration_value: str
    representation: str
    phase: str
    covers_materialization: bool
    dominates_growth: bool
    reject_path_reaches_growth: bool
    evidence: str
    cfg_relation: Literal["one_wrapper", "partial"]
    coverage_status: Coverage
    coverage_note: str
    summary_id: str = ""

    def __post_init__(self) -> None:
        if self.family not in {"guard", "bound", "release"} or self.cfg_relation not in {"one_wrapper", "partial"} or self.coverage_status not in {"complete", "partial", "unsupported"}:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle summary enum is invalid.")
        for name in ("entry_id", "growth_id", "path_id", "candidate_file", "callsite_file", "receiver_file", "resource_dimension", "scope", "configuration_key", "configuration_value", "representation", "phase", "evidence", "coverage_note"):
            _text(getattr(self, name), name)
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in (self.candidate_start_line, self.callsite_start_line, self.receiver_start_line, self.argument_index)):
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle summary location is invalid.")
        if any(type(value) is not bool for value in (self.covers_materialization, self.dominates_growth, self.reject_path_reaches_growth)):
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle summary CFG flags are invalid.")
        if any(value < 1 for value in (self.candidate_start_line, self.callsite_start_line, self.receiver_start_line)):
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle summary source location is invalid.")
        expected = stable_identifier("lifecycle-summary", self.semantic_identity())
        if self.summary_id and self.summary_id != expected:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle summary identifier is not canonical.")
        object.__setattr__(self, "summary_id", expected)

    def semantic_identity(self) -> dict[str, object]:
        return {"entry_id": self.entry_id, "growth_id": self.growth_id, "path_id": self.path_id, "family": self.family, "candidate_file": self.candidate_file, "candidate_start_line": self.candidate_start_line, "callsite_file": self.callsite_file, "callsite_start_line": self.callsite_start_line, "receiver_file": self.receiver_file, "receiver_start_line": self.receiver_start_line, "argument_index": self.argument_index, "resource_dimension": self.resource_dimension, "scope": self.scope, "configuration_key": self.configuration_key, "configuration_value": self.configuration_value, "representation": self.representation, "phase": self.phase, "covers_materialization": self.covers_materialization, "dominates_growth": self.dominates_growth, "reject_path_reaches_growth": self.reject_path_reaches_growth, "evidence": self.evidence, "cfg_relation": self.cfg_relation, "coverage_status": self.coverage_status, "coverage_note": self.coverage_note}

    def to_dict(self) -> dict[str, object]:
        return {"summary_id": self.summary_id, **self.semantic_identity()}

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "LifecycleSummary":
        if set(raw) != {"summary_id", "entry_id", "growth_id", "path_id", "family", "candidate_file", "candidate_start_line", "callsite_file", "callsite_start_line", "receiver_file", "receiver_start_line", "argument_index", "resource_dimension", "scope", "configuration_key", "configuration_value", "representation", "phase", "covers_materialization", "dominates_growth", "reject_path_reaches_growth", "evidence", "cfg_relation", "coverage_status", "coverage_note"}:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle summary record is malformed.")
        return cls(**raw)  # type: ignore[arg-type]


@dataclass(frozen=True)
class LifecycleEvidence:
    entry_id: str
    growth_id: str
    path_id: str
    family: Family
    candidate_id: str
    growth_file: str
    growth_line: int
    candidate_file: str
    candidate_line: int
    resource_identity: str
    field_identity: str
    key_identity: str
    cfg_relation: Literal["same_cfg", "partial", "ambiguous"]
    coverage_status: Coverage
    evidence_id: str = ""

    def __post_init__(self) -> None:
        if self.family not in {"guard", "bound", "release"} or self.cfg_relation not in {"same_cfg", "partial", "ambiguous"} or self.coverage_status not in {"complete", "partial", "unsupported"}:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle evidence enum is invalid.")
        for name in ("entry_id", "growth_id", "path_id", "candidate_id", "growth_file", "candidate_file", "resource_identity", "field_identity", "key_identity"):
            _text(getattr(self, name), name)
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in (self.growth_line, self.candidate_line)):
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle evidence location is invalid.")
        expected = stable_identifier("lifecycle-evidence", self.semantic_identity())
        if self.evidence_id and self.evidence_id != expected:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle evidence identifier is not canonical.")
        object.__setattr__(self, "evidence_id", expected)

    def semantic_identity(self) -> dict[str, object]:
        return {"entry_id": self.entry_id, "growth_id": self.growth_id, "path_id": self.path_id, "family": self.family, "candidate_id": self.candidate_id, "growth_file": self.growth_file, "growth_line": self.growth_line, "candidate_file": self.candidate_file, "candidate_line": self.candidate_line, "resource_identity": self.resource_identity, "field_identity": self.field_identity, "key_identity": self.key_identity, "cfg_relation": self.cfg_relation, "coverage_status": self.coverage_status}

    def to_dict(self) -> dict[str, object]:
        return {"evidence_id": self.evidence_id, **self.semantic_identity()}

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "LifecycleEvidence":
        required = set(cls.__dataclass_fields__.keys())
        if set(raw) != required:
            raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle evidence record is malformed.")
        return cls(**raw)  # type: ignore[arg-type]
