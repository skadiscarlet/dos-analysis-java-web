from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from dosweb.errors import AnalyzerError
from dosweb.entries import FrameworkCoverage
from dosweb.entries.coverage import (
    registration_coverage_pattern_belongs_to_framework,
)

from .assertions import AssertionEvaluation

StaticVerdictName = Literal[
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
]


@dataclass(frozen=True)
class VerdictProofGate:
    """Proof obligations required for vulnerable or modeled-bounded output."""

    entry_complete: bool
    ordinary_reachability: bool
    growth_verified: bool
    flow_proven: bool
    assertion_1_lifecycle_complete: bool
    assertion_2_lifecycle_complete: bool
    candidate_relevant_gap_free: bool

    def __post_init__(self) -> None:
        if any(
            type(getattr(self, field)) is not bool
            for field in (
                "entry_complete",
                "ordinary_reachability",
                "growth_verified",
                "flow_proven",
                "assertion_1_lifecycle_complete",
                "assertion_2_lifecycle_complete",
                "candidate_relevant_gap_free",
            )
        ):
            raise AnalyzerError(
                "ANALYSIS_VERDICT_INVALID", "Verdict proof gate is malformed."
            )

    @property
    def missing_reason_codes(self) -> tuple[str, ...]:
        reasons = {
            "entry_complete": "VERDICT_ENTRY_COVERAGE_INCOMPLETE",
            "ordinary_reachability": "VERDICT_REACHABILITY_NOT_PROVEN",
            "growth_verified": "VERDICT_GROWTH_NOT_VERIFIED",
            "flow_proven": "VERDICT_FLOW_NOT_PROVEN",
            "assertion_1_lifecycle_complete": "VERDICT_ASSERTION_1_LIFECYCLE_COVERAGE_INCOMPLETE",
            "assertion_2_lifecycle_complete": "VERDICT_ASSERTION_2_LIFECYCLE_COVERAGE_INCOMPLETE",
            "candidate_relevant_gap_free": "VERDICT_CANDIDATE_RELEVANT_GAP",
        }
        return tuple(
            sorted(reason for field, reason in reasons.items() if not getattr(self, field))
        )


@dataclass(frozen=True)
class CandidateCoverage:
    """Coverage for a candidate, optionally narrowed to fact identifiers."""

    framework: str
    status: Literal["complete", "partial", "unsupported"]
    supported_patterns: tuple[str, ...]
    unsupported_patterns: tuple[str, ...]
    effect_on_verdict: Literal["none", "forces_unknown"]
    registration_pattern_id: str | None = None
    entry_id: str | None = None
    growth_id: str | None = None
    path_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"complete", "partial", "unsupported"}:
            raise AnalyzerError("COVERAGE_ENTRY_INVALID", "Candidate coverage status is invalid.")
        expected = "none" if self.status == "complete" else "forces_unknown"
        if self.effect_on_verdict != expected:
            raise AnalyzerError("COVERAGE_ENTRY_INVALID", "Candidate coverage effect does not match status.")
        for field in ("supported_patterns", "unsupported_patterns"):
            values = getattr(self, field)
            if not isinstance(values, tuple) or any(not isinstance(value, str) or not value for value in values):
                raise AnalyzerError("COVERAGE_ENTRY_INVALID", f"{field} is invalid.")
            if tuple(sorted(set(values))) != values:
                raise AnalyzerError("COVERAGE_ENTRY_INVALID", f"{field} must be deterministic.")
        if set(self.supported_patterns) & set(self.unsupported_patterns):
            raise AnalyzerError(
                "COVERAGE_ENTRY_INVALID",
                "Supported and unsupported candidate patterns must be disjoint.",
            )
        if any(
            not registration_coverage_pattern_belongs_to_framework(
                self.framework, pattern_id
            )
            for pattern_id in self.supported_patterns
        ):
            raise AnalyzerError(
                "COVERAGE_ENTRY_INVALID",
                "Supported candidate patterns must be exact modeled identities for their framework.",
            )
        if self.status == "complete" and self.unsupported_patterns:
            raise AnalyzerError("COVERAGE_ENTRY_INVALID", "Complete candidate coverage cannot contain gaps.")
        if self.status != "complete" and not self.unsupported_patterns:
            raise AnalyzerError("COVERAGE_ENTRY_INVALID", "Incomplete candidate coverage requires a gap.")
        for field in ("registration_pattern_id", "entry_id", "growth_id", "path_id"):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or not value):
                raise AnalyzerError("COVERAGE_ENTRY_INVALID", f"{field} is invalid.")
        if self.registration_pattern_id is not None and not registration_coverage_pattern_belongs_to_framework(
            self.framework, self.registration_pattern_id
        ):
            raise AnalyzerError(
                "COVERAGE_ENTRY_INVALID",
                "Candidate registration pattern identity is not modeled for its framework.",
            )
        if self.entry_id is not None and self.registration_pattern_id is None:
            raise AnalyzerError(
                "COVERAGE_ENTRY_INVALID",
                "Entry-scoped candidate coverage requires an exact registration pattern identity.",
            )
        if self.registration_pattern_id is not None and any(
            pattern_id != self.registration_pattern_id
            for pattern_id in self.supported_patterns
        ):
            raise AnalyzerError(
                "COVERAGE_ENTRY_INVALID",
                "Candidate coverage cannot cite a sibling registration pattern.",
            )
        if self.status == "complete" and self.entry_id is not None and (
            self.registration_pattern_id is None
            or self.supported_patterns != (self.registration_pattern_id,)
        ):
            raise AnalyzerError(
                "COVERAGE_ENTRY_INVALID",
                "Complete entry-scoped coverage requires exactly its registration pattern identity.",
            )

    @classmethod
    def from_framework(
        cls,
        coverage: FrameworkCoverage,
        *,
        registration_pattern_id: str | None = None,
        entry_id: str | None = None,
        growth_id: str | None = None,
        path_id: str | None = None,
    ) -> "CandidateCoverage":
        if not isinstance(coverage, FrameworkCoverage):
            raise AnalyzerError("COVERAGE_ENTRY_INVALID", "Framework coverage is malformed.")
        if registration_pattern_id is not None:
            if registration_pattern_id in coverage.supported_patterns:
                return cls(
                    coverage.framework,
                    "complete",
                    (registration_pattern_id,),
                    (),
                    "none",
                    registration_pattern_id,
                    entry_id,
                    growth_id,
                    path_id,
                )
            return cls(
                coverage.framework,
                "partial",
                (),
                (
                    "entry_registration_pattern_uncovered:"
                    f"{registration_pattern_id}",
                ),
                "forces_unknown",
                registration_pattern_id,
                entry_id,
                growth_id,
                path_id,
            )
        return cls(
            coverage.framework,
            coverage.status,
            coverage.supported_patterns,
            coverage.unsupported_patterns,
            coverage.effect_on_verdict,
            registration_pattern_id,
            entry_id,
            growth_id,
            path_id,
        )

    def relevant_to(
        self,
        *,
        framework: str,
        registration_pattern_id: str | None = None,
        entry_id: str | None = None,
        growth_id: str | None = None,
        path_id: str | None = None,
    ) -> bool:
        if self.framework != framework:
            return False
        if (
            self.registration_pattern_id is not None
            and self.registration_pattern_id != registration_pattern_id
        ):
            return False
        for scoped, candidate in (
            (self.entry_id, entry_id),
            (self.growth_id, growth_id),
            (self.path_id, path_id),
        ):
            if scoped is not None and scoped != candidate:
                return False
        return True

    @property
    def forces_unknown(self) -> bool:
        return self.effect_on_verdict == "forces_unknown"

    @property
    def coverage_gaps(self) -> tuple[str, ...]:
        return self.unsupported_patterns

    def to_dict(self) -> dict[str, object]:
        return {
            "framework": self.framework,
            "status": self.status,
            "supported_patterns": list(self.supported_patterns),
            "unsupported_patterns": list(self.unsupported_patterns),
            "effect_on_verdict": self.effect_on_verdict,
            "registration_pattern_id": self.registration_pattern_id,
            "entry_id": self.entry_id,
            "growth_id": self.growth_id,
            "path_id": self.path_id,
        }


@dataclass(frozen=True)
class StaticVerdict:
    verdict: StaticVerdictName
    reason_codes: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    unresolved_facts: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    modeled_configuration_refs: tuple[str, ...] = ()
    covered_entries: tuple[str, ...] = ()
    covered_paths: tuple[str, ...] = ()
    coverage_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in {"static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown"}:
            raise AnalyzerError("ANALYSIS_VERDICT_INVALID", "Static verdict is invalid.")
        for field in (
            "reason_codes", "evidence_ids", "unresolved_facts", "assumptions",
            "modeled_configuration_refs", "covered_entries", "covered_paths", "coverage_gaps",
        ):
            values = getattr(self, field)
            if not isinstance(values, tuple) or any(not isinstance(item, str) or not item for item in values):
                raise AnalyzerError("ANALYSIS_VERDICT_INVALID", f"{field} is invalid.")
            if tuple(sorted(set(values))) != values:
                raise AnalyzerError("ANALYSIS_VERDICT_INVALID", f"{field} must be deterministic.")

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
            "evidence_ids": list(self.evidence_ids),
            "unresolved_facts": list(self.unresolved_facts),
            "assumptions": list(self.assumptions),
            "modeled_configuration_refs": list(self.modeled_configuration_refs),
            "covered_entries": list(self.covered_entries),
            "covered_paths": list(self.covered_paths),
            "coverage_gaps": list(self.coverage_gaps),
        }


def _sorted(values: set[str]) -> tuple[str, ...]:
    return tuple(sorted(values))


def _relevant_gaps(assertions: Sequence[AssertionEvaluation], coverage: CandidateCoverage) -> tuple[str, ...]:
    if coverage.status == "complete":
        return ()
    return tuple(sorted(coverage.unsupported_patterns))


def derive_verdict(
    assertions: Sequence[AssertionEvaluation],
    coverage: CandidateCoverage,
) -> StaticVerdict:
    if (
        not isinstance(coverage, CandidateCoverage)
        or not isinstance(assertions, Sequence)
        or isinstance(assertions, (str, bytes))
        or not assertions
        or any(not isinstance(assertion, AssertionEvaluation) for assertion in assertions)
    ):
        raise AnalyzerError("ANALYSIS_VERDICT_INVALID", "Verdict inputs are malformed.")
    for field in ("entry_id", "growth_id", "path_id"):
        scoped = getattr(coverage, field)
        if scoped is not None and not any(scoped in assertion.evidence_ids for assertion in assertions):
            raise AnalyzerError("ANALYSIS_VERDICT_INVALID", "Candidate coverage does not match assertion evidence.")

    reasons: set[str] = set()
    evidence: set[str] = set()
    unresolved: set[str] = set()
    entries: set[str] = set()
    paths: set[str] = set()
    for assertion in assertions:
        reasons.update(assertion.reason_codes)
        evidence.update(assertion.evidence_ids)
        if assertion.status != "not_applicable":
            unresolved.update(assertion.unresolved_facts)
        entries.update(item for item in assertion.evidence_ids if item.startswith("entry:"))
        paths.update(item for item in assertion.evidence_ids if item.startswith("flow:"))

    gaps = set(_relevant_gaps(assertions, coverage))
    applicable = [item for item in assertions if item.status != "not_applicable"]
    has_unknown = bool(unresolved) or any(item.status == "unknown" for item in assertions) or bool(gaps)
    has_match = any(item.status == "matched" for item in assertions)
    all_refuted = bool(applicable) and all(item.status == "refuted" for item in applicable)

    if has_unknown:
        verdict: StaticVerdictName = "static_unknown"
        reasons.add("VERDICT_UNRESOLVED_EVIDENCE" if unresolved else "VERDICT_COVERAGE_GAP" if gaps else "VERDICT_ASSERTION_UNKNOWN")
    elif has_match:
        verdict = "static_vulnerable"
        reasons.add("VERDICT_ASSERTION_MATCHED")
    elif all_refuted:
        verdict = "bounded_under_modeled_assumptions"
        reasons.add("VERDICT_ASSERTIONS_REFUTED")
    else:
        verdict = "static_unknown"
        reasons.add("VERDICT_NO_APPLICABLE_ASSERTION")

    assumptions: set[str] = set()
    modeled: set[str] = set()
    if verdict == "bounded_under_modeled_assumptions":
        assumptions.update(("MODELED_DEFAULT_CONFIGURATION", "STATIC_EVIDENCE_COVERAGE_COMPLETE"))
        modeled.update(item for item in evidence if item.startswith(("guard:", "bound:", "release:")))
    return StaticVerdict(
        verdict=verdict,
        reason_codes=_sorted(reasons),
        evidence_ids=_sorted(evidence),
        unresolved_facts=_sorted(unresolved),
        assumptions=_sorted(assumptions),
        modeled_configuration_refs=_sorted(modeled),
        covered_entries=_sorted(entries),
        covered_paths=_sorted(paths),
        coverage_gaps=_sorted(gaps),
    )


def apply_positive_proof_gate(
    verdict: StaticVerdict,
    gate: VerdictProofGate,
) -> StaticVerdict:
    """Fail closed to unknown when any required proof obligation is missing.

    Both ``static_vulnerable`` and ``bounded_under_modeled_assumptions`` are
    determinate static conclusions and require the complete gate. An existing
    ``static_unknown`` remains unknown while receiving the exact missing reason
    codes for auditability. When a modeled-bounded conclusion is actually
    downgraded, its contradictory ``STATIC_EVIDENCE_COVERAGE_COMPLETE``
    assumption is removed while evidence-backed modeled-default references are
    preserved.
    """
    if not isinstance(verdict, StaticVerdict) or not isinstance(gate, VerdictProofGate):
        raise AnalyzerError("ANALYSIS_VERDICT_INVALID", "Verdict proof gate inputs are malformed.")
    missing = gate.missing_reason_codes
    if not missing:
        return verdict
    assumptions = verdict.assumptions
    if verdict.verdict == "bounded_under_modeled_assumptions":
        assumptions = tuple(
            assumption
            for assumption in assumptions
            if assumption != "STATIC_EVIDENCE_COVERAGE_COMPLETE"
        )
    return StaticVerdict(
        verdict="static_unknown",
        reason_codes=tuple(sorted(set((*verdict.reason_codes, *missing)))),
        evidence_ids=verdict.evidence_ids,
        unresolved_facts=verdict.unresolved_facts,
        assumptions=assumptions,
        modeled_configuration_refs=verdict.modeled_configuration_refs,
        covered_entries=verdict.covered_entries,
        covered_paths=verdict.covered_paths,
        coverage_gaps=verdict.coverage_gaps,
    )


__all__ = [
    "CandidateCoverage",
    "StaticVerdict",
    "StaticVerdictName",
    "VerdictProofGate",
    "apply_positive_proof_gate",
    "derive_verdict",
]
