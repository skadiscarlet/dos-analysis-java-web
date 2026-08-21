from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.conclude.assertions import (
    AssertionEvaluation,
    evaluate_assertion_1,
    evaluate_assertion_2,
)
from dosweb.conclude.verdicts import CandidateCoverage, StaticVerdict
from dosweb.entries import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.flows import VerifiedFlow
from dosweb.growth import VerifiedGrowthResult

from .bounds import BoundDecision
from .guards import DecisionCheck, GuardDecision
from .releases import ReleaseDecision


_DECISION_TYPES: Final = (GuardDecision, BoundDecision, ReleaseDecision)


def _strings(values: object, field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or any(not isinstance(value, str) or not value for value in values):
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", f"{field} is malformed.")
    normalized = tuple(sorted(set(values)))
    if normalized != values:
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", f"{field} is not deterministic.")
    return normalized


def _snapshot(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _snapshot(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_snapshot(item) for item in value)
    return value


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _check_to_dict(check: DecisionCheck) -> dict[str, object]:
    return {
        "name": check.name,
        "passed": check.passed,
        "reason_code": check.reason_code,
        "evidence_ids": list(check.evidence_ids),
    }


def _decision_to_dict(decision: GuardDecision | BoundDecision | ReleaseDecision) -> dict[str, object]:
    result: dict[str, object] = {
        "status": decision.status,
        "reason_codes": list(decision.reason_codes),
        "checks": [_check_to_dict(check) for check in decision.checks],
        "evidence_ids": list(decision.evidence_ids),
        "unresolved_facts": list(decision.unresolved_facts),
        "candidate_ids": list(decision.candidate_ids),
    }
    if isinstance(decision, ReleaseDecision):
        result["classification"] = decision.classification
    return result


def _assertion_to_dict(assertion: AssertionEvaluation) -> dict[str, object]:
    return {
        "assertion": assertion.assertion,
        "status": assertion.status,
        "reason_codes": list(assertion.reason_codes),
        "evidence_ids": list(assertion.evidence_ids),
        "unresolved_facts": list(assertion.unresolved_facts),
    }


def _follow_ups(verdict: StaticVerdict, release: ReleaseDecision) -> tuple[str, ...]:
    suggestions: set[str] = set()
    if verdict.verdict == "static_vulnerable":
        suggestions.add("authorized_resource_growth_measurement")
    elif verdict.verdict == "bounded_under_modeled_assumptions":
        suggestions.add("review_modeled_configuration_against_deployment")
    else:
        suggestions.add("resolve_unresolved_static_facts")
    if release.classification == "potential_async":
        suggestions.add("trace_async_consumer_and_release_ownership")
    if verdict.coverage_gaps:
        suggestions.add("complete_framework_registration_coverage")
    return tuple(sorted(suggestions))


@dataclass(frozen=True)
class StaticFinding:
    """Small certificate reference used by machine-readable findings."""

    finding_id: str
    certificate_id: str
    entry_id: str
    growth_id: str
    verdict: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.finding_id, str) or not self.finding_id.startswith("finding:"):
            raise AnalyzerError("ANALYSIS_FINDING_INVALID", "Finding identifier is malformed.")
        if not isinstance(self.certificate_id, str) or not self.certificate_id.startswith("certificate:"):
            raise AnalyzerError("ANALYSIS_FINDING_INVALID", "Finding certificate reference is malformed.")
        if not isinstance(self.entry_id, str) or not self.entry_id.startswith("entry:"):
            raise AnalyzerError("ANALYSIS_FINDING_INVALID", "Finding entry reference is malformed.")
        if not isinstance(self.growth_id, str) or not self.growth_id.startswith("growth:"):
            raise AnalyzerError("ANALYSIS_FINDING_INVALID", "Finding Growth reference is malformed.")
        if self.verdict not in {"static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown"}:
            raise AnalyzerError("ANALYSIS_FINDING_INVALID", "Finding verdict is invalid.")
        _strings(self.reason_codes, "reason_codes")
        expected = stable_identifier("finding", {"certificate_id": self.certificate_id})
        if self.finding_id != expected:
            raise AnalyzerError("ANALYSIS_FINDING_INVALID", "Finding identifier is not certificate-derived.")

    @classmethod
    def from_certificate(cls, certificate: "LifecycleCertificate") -> "StaticFinding":
        if not isinstance(certificate, LifecycleCertificate):
            raise AnalyzerError("ANALYSIS_FINDING_INVALID", "Finding certificate is malformed.")
        return cls(
            stable_identifier("finding", {"certificate_id": certificate.certificate_id}),
            certificate.certificate_id,
            certificate.entry_id,
            certificate.growth_id,
            certificate.verdict,
            certificate.reason_codes,
        )

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> StaticFinding:
        if not isinstance(record, Mapping) or set(record) != {"finding_id", "certificate_id", "entry_id", "growth_id", "verdict", "reason_codes"}:
            raise AnalyzerError("ANALYSIS_FINDING_INVALID", "Finding record is malformed.")
        return cls(record["finding_id"], record["certificate_id"], record["entry_id"], record["growth_id"], record["verdict"], tuple(record["reason_codes"]))

    def to_dict(self) -> dict[str, object]:
        return {
            "finding_id": self.finding_id,
            "certificate_id": self.certificate_id,
            "entry_id": self.entry_id,
            "growth_id": self.growth_id,
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class LifecycleCertificate:
    """Immutable, auditable conclusion over one entry-to-growth lifecycle."""

    certificate_id: str
    entry_id: str
    growth_id: str
    attacker_inputs: tuple[Mapping[str, object], ...]
    resource_point: Mapping[str, object]
    path_ids: tuple[str, ...]
    guard_decision: Mapping[str, object]
    bound_decision: Mapping[str, object]
    release_decision: Mapping[str, object]
    assertions: tuple[Mapping[str, object], ...]
    verdict: str
    reason_codes: tuple[str, ...]
    assumptions: tuple[str, ...]
    coverage_gaps: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
    suggested_follow_up_measurements: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.certificate_id, str) or not self.certificate_id.startswith("certificate:"):
            raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate identifier is malformed.")
        if not isinstance(self.entry_id, str) or not self.entry_id.startswith("entry:"):
            raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate entry reference is malformed.")
        if not isinstance(self.growth_id, str) or not self.growth_id.startswith("growth:"):
            raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate Growth reference is malformed.")
        if not isinstance(self.path_ids, tuple) or not self.path_ids or any(
            not isinstance(path_id, str) or not path_id.startswith("flow:") for path_id in self.path_ids
        ) or len(set(self.path_ids)) != len(self.path_ids) or tuple(sorted(self.path_ids)) != self.path_ids:
            raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate paths are malformed.")
        if not isinstance(self.attacker_inputs, tuple) or not self.attacker_inputs or any(
            not isinstance(item, Mapping) for item in self.attacker_inputs
        ):
            raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate attacker inputs are malformed.")
        for field in ("resource_point", "guard_decision", "bound_decision", "release_decision"):
            if not isinstance(getattr(self, field), Mapping):
                raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", f"Certificate {field} is malformed.")
        if not isinstance(self.assertions, tuple) or not self.assertions or any(
            not isinstance(item, Mapping) for item in self.assertions
        ):
            raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate assertions are malformed.")
        if self.verdict not in {
            "static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown"
        }:
            raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate verdict is invalid.")
        for field in (
            "reason_codes", "assumptions", "coverage_gaps", "unresolved_facts",
            "suggested_follow_up_measurements",
        ):
            _strings(getattr(self, field), field)
        object.__setattr__(self, "attacker_inputs", tuple(_snapshot(item) for item in self.attacker_inputs))
        object.__setattr__(self, "resource_point", _snapshot(self.resource_point))
        object.__setattr__(self, "guard_decision", _snapshot(self.guard_decision))
        object.__setattr__(self, "bound_decision", _snapshot(self.bound_decision))
        object.__setattr__(self, "release_decision", _snapshot(self.release_decision))
        object.__setattr__(self, "assertions", tuple(_snapshot(item) for item in self.assertions))
        semantic = self.to_dict()
        semantic.pop("certificate_id")
        if self.certificate_id != stable_identifier("certificate", semantic):
            raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate identifier is not canonical.")

    def to_dict(self) -> dict[str, object]:
        return {
            "certificate_id": self.certificate_id,
            "entry_id": self.entry_id,
            "growth_id": self.growth_id,
            "attacker_inputs": [_plain(item) for item in self.attacker_inputs],
            "resource_point": _plain(self.resource_point),
            "path_ids": list(self.path_ids),
            "guard_decision": _plain(self.guard_decision),
            "bound_decision": _plain(self.bound_decision),
            "release_decision": _plain(self.release_decision),
            "assertions": [_plain(item) for item in self.assertions],
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
            "assumptions": list(self.assumptions),
            "coverage_gaps": list(self.coverage_gaps),
            "unresolved_facts": list(self.unresolved_facts),
            "suggested_follow_up_measurements": list(self.suggested_follow_up_measurements),
        }


def build_lifecycle_certificate(
    entry: EntryFact,
    growth: VerifiedGrowthResult,
    flows: Sequence[VerifiedFlow],
    guard: GuardDecision,
    bound: BoundDecision,
    release: ReleaseDecision,
    assertions: Sequence[AssertionEvaluation],
    coverage: CandidateCoverage,
    verdict: StaticVerdict,
    *,
    reachability: object | None = None,
    repeatability: object | None = None,
    amplification: object | None = None,
) -> LifecycleCertificate:
    if not isinstance(entry, EntryFact) or not isinstance(growth, VerifiedGrowthResult):
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate facts are malformed.")
    if not isinstance(flows, Sequence) or isinstance(flows, (str, bytes)) or not flows or any(
        not isinstance(flow, VerifiedFlow) for flow in flows
    ):
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate flows are malformed.")
    if any(
        flow.entry_id != entry.entry_id or flow.growth_id != growth.growth_id
        for flow in flows
    ):
        raise AnalyzerError(
            "ANALYSIS_CERTIFICATE_INVALID",
            "Certificate paths must reference one entry and Growth.",
        )
    if any(not flow.satisfies_premise for flow in flows) and getattr(verdict, "verdict", None) != "static_unknown":
        raise AnalyzerError(
            "ANALYSIS_CERTIFICATE_INVALID",
            "Incomplete paths require a static unknown certificate.",
        )
    if any(not isinstance(decision, _DECISION_TYPES) for decision in (guard, bound, release)):
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Lifecycle decisions are malformed.")
    if not isinstance(assertions, Sequence) or isinstance(assertions, (str, bytes)) or not assertions or any(
        not isinstance(assertion, AssertionEvaluation) for assertion in assertions
    ):
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate assertions are malformed.")
    if not isinstance(coverage, CandidateCoverage) or not isinstance(verdict, StaticVerdict):
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Coverage or verdict is malformed.")
    expected_assertions = tuple(
        evaluation
        for flow in flows
        for evaluation in (
            evaluate_assertion_1(growth, flow, guard, bound, amplification=amplification, reachability=reachability),
            evaluate_assertion_2(growth, flow, bound, release, reachability=reachability, repeatability=repeatability),
        )
    )
    if Counter(assertions) != Counter(expected_assertions):
        raise AnalyzerError(
            "ANALYSIS_CERTIFICATE_INVALID",
            "Certificate assertions do not match deterministic lifecycle evaluation.",
        )
    if growth.candidate is None:
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Certificate requires a Growth resource point.")
    path_ids = tuple(sorted({flow.path_id for flow in flows}))
    if not coverage.relevant_to(
        framework=entry.framework,
        registration_pattern=entry.registration.kind,
        entry_id=entry.entry_id,
        growth_id=growth.growth_id,
        path_id=coverage.path_id,
    ):
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Coverage does not match certificate facts.")
    if coverage.path_id is not None and coverage.path_id not in path_ids:
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Coverage path is absent from certificate paths.")
    from dosweb.conclude.verdicts import derive_verdict
    expected_verdict = derive_verdict(assertions, coverage)
    if verdict != expected_verdict:
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Supplied verdict does not match deterministic derivation.")
    if coverage.forces_unknown and verdict.verdict != "static_unknown":
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Incomplete coverage must force a static unknown verdict.")
    if verdict.covered_entries != (entry.entry_id,):
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Verdict does not exactly cover certificate entry.")
    if verdict.covered_paths != path_ids:
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Verdict does not exactly cover certificate paths.")
    expected_evidence = {item for assertion in assertions for item in assertion.evidence_ids}
    if set(verdict.evidence_ids) != expected_evidence:
        raise AnalyzerError("ANALYSIS_CERTIFICATE_INVALID", "Verdict evidence does not match certificate assertions.")

    assertion_dicts = tuple(_assertion_to_dict(assertion) for assertion in assertions)
    reason_codes = tuple(sorted(set((*verdict.reason_codes, *(reason for item in assertions for reason in item.reason_codes), *guard.reason_codes, *bound.reason_codes, *release.reason_codes))))
    unresolved = tuple(sorted(set((*verdict.unresolved_facts, *(fact for item in assertions for fact in item.unresolved_facts), *guard.unresolved_facts, *bound.unresolved_facts, *release.unresolved_facts))))
    assumptions = tuple(sorted(set(verdict.assumptions)))
    gaps = tuple(sorted(set((*verdict.coverage_gaps, *coverage.coverage_gaps))))
    semantic = {
        "entry_id": entry.entry_id,
        "growth_id": growth.growth_id,
        "attacker_inputs": [item.to_dict() for item in entry.attacker_inputs],
        "resource_point": growth.candidate.to_dict()["resource_point"],
        "path_ids": list(path_ids),
        "guard_decision": _decision_to_dict(guard),
        "bound_decision": _decision_to_dict(bound),
        "release_decision": _decision_to_dict(release),
        "assertions": list(assertion_dicts),
        "verdict": verdict.verdict,
        "reason_codes": list(reason_codes),
        "assumptions": list(assumptions),
        "coverage_gaps": list(gaps),
        "unresolved_facts": list(unresolved),
        "suggested_follow_up_measurements": list(_follow_ups(verdict, release)),
    }
    return LifecycleCertificate(
        stable_identifier("certificate", semantic),
        entry.entry_id,
        growth.growth_id,
        tuple(semantic["attacker_inputs"]),
        semantic["resource_point"],
        path_ids,
        semantic["guard_decision"],
        semantic["bound_decision"],
        semantic["release_decision"],
        assertion_dicts,
        verdict.verdict,
        reason_codes,
        assumptions,
        gaps,
        unresolved,
        tuple(semantic["suggested_follow_up_measurements"]),
    )


__all__ = ["LifecycleCertificate", "StaticFinding", "build_lifecycle_certificate"]
