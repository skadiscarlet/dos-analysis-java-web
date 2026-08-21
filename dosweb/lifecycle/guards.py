from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.entries import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.flows import VerifiedFlow
from dosweb.growth import VerifiedGrowthResult


@dataclass(frozen=True, order=True)
class DecisionCheck:
    name: str
    passed: bool
    reason_code: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModeledConfiguration:
    values: tuple[tuple[str, str | int | bool], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple) or len(self.values) > 256 or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0]
            or not isinstance(item[1], (str, int, bool))
            or isinstance(item[1], float)
            for item in self.values
        ):
            raise AnalyzerError("ANALYSIS_CONFIGURATION_INVALID", "Modeled configuration is malformed.")
        normalized = tuple(sorted(self.values, key=lambda item: item[0]))
        if len({item[0] for item in normalized}) != len(normalized):
            raise AnalyzerError("ANALYSIS_CONFIGURATION_INVALID", "Modeled configuration contains duplicate keys.")
        object.__setattr__(self, "values", normalized)

    def get(self, key: str) -> str | int | bool | None:
        return dict(self.values).get(key)


def _site(file: object, line: object) -> tuple[str, int]:
    if not isinstance(file, str) or not file or PurePosixPath(file).is_absolute() or ".." in PurePosixPath(file).parts:
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle candidate path is invalid.")
    if not isinstance(line, int) or isinstance(line, bool) or line <= 0:
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle candidate line is invalid.")
    return file, line


def _boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise AnalyzerError(
            "ANALYSIS_LIFECYCLE_INVALID",
            f"Lifecycle field {field} must be a boolean.",
        )
    return value


def _evidence(values: object) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list, frozenset)) or not values or len(values) > 64:
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle evidence is invalid.")
    result = tuple(sorted(set(values)))
    if any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 256 for item in result):
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle evidence is invalid.")
    return result


def _validate_context(entry: EntryFact, growth: VerifiedGrowthResult, flow: VerifiedFlow) -> None:
    if not isinstance(entry, EntryFact) or not isinstance(growth, VerifiedGrowthResult) or not isinstance(flow, VerifiedFlow) or flow.entry_id != entry.entry_id or flow.growth_id != growth.growth_id:
        raise AnalyzerError("ANALYSIS_DANGLING_FACT_REFERENCE", "Lifecycle decision inputs do not reference the same E-to-G path.")
    if not flow.satisfies_premise or growth.status != "verified" or growth.candidate is None:
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Lifecycle evaluation requires a proven flow and verified Growth.")


@dataclass(frozen=True)
class GuardCandidate:
    guard_id: str
    site_file: str
    site_start_line: int
    kind: str
    resource_dimension: str
    scope: str
    behavior: str
    dominates_growth: bool
    reject_path_reaches_growth: bool
    configuration_key: str
    configuration_value: str
    representation: str
    phase: str
    covers_materialization: bool
    authorization_only: bool
    evidence: tuple[str, ...]
    coverage_status: str

    @classmethod
    def create(cls, **values: object) -> GuardCandidate:
        file, line = _site(values["site_file"], values["site_start_line"])
        evidence = _evidence(values["evidence"])
        semantic = {**values, "site_file": file, "site_start_line": line, "evidence": list(evidence)}
        return cls(stable_identifier("guard", semantic), file, line, str(values["kind"]), str(values["resource_dimension"]), str(values["scope"]), str(values["behavior"]), _boolean(values["dominates_growth"], "dominates_growth"), _boolean(values["reject_path_reaches_growth"], "reject_path_reaches_growth"), str(values["configuration_key"]), str(values["configuration_value"]), str(values["representation"]), str(values["phase"]), _boolean(values["covers_materialization"], "covers_materialization"), _boolean(values["authorization_only"], "authorization_only"), evidence, str(values["coverage_status"]))

    def to_dict(self) -> dict[str, object]:
        return {"guard_id": self.guard_id, "site": {"file": self.site_file, "start_line": self.site_start_line}, "kind": self.kind, "resource_dimension": self.resource_dimension, "scope": self.scope, "behavior": self.behavior, "dominates_growth": self.dominates_growth, "reject_path_reaches_growth": self.reject_path_reaches_growth, "configuration_key": self.configuration_key, "configuration_value": self.configuration_value, "representation": self.representation, "phase": self.phase, "covers_materialization": self.covers_materialization, "authorization_only": self.authorization_only, "evidence": list(self.evidence), "coverage_status": self.coverage_status}

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> GuardCandidate:
        if not isinstance(record, Mapping): raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Guard candidate record is malformed.")
        site = record.get("site")
        if not isinstance(site, Mapping): raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Guard candidate site is malformed.")
        values = {**record, "site_file": site.get("file"), "site_start_line": site.get("start_line")}
        values.pop("guard_id", None); values.pop("site", None)
        candidate = cls.create(**values)
        if record.get("guard_id") != candidate.guard_id: raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Guard candidate identifier is not canonical.")
        return candidate


@dataclass(frozen=True)
class GuardDecision:
    status: Literal["effective", "ineffective", "unknown"]
    reason_codes: tuple[str, ...]
    checks: tuple[DecisionCheck, ...]
    evidence_ids: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
    candidate_ids: tuple[str, ...]


def evaluate_guard(entry: EntryFact, growth: VerifiedGrowthResult, flow: VerifiedFlow, candidates: Sequence[GuardCandidate], configuration: ModeledConfiguration, *, coverage_status: str = "complete") -> GuardDecision:
    _validate_context(entry, growth, flow)
    if coverage_status not in {"complete", "partial", "unsupported"}:
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Guard coverage status is invalid.")
    ordered = tuple(sorted(candidates, key=lambda item: item.guard_id))
    if not ordered:
        if coverage_status == "complete":
            return GuardDecision("ineffective", ("GUARD_ABSENT",), (), (), (), ())
        return GuardDecision("unknown", ("GUARD_COVERAGE_UNKNOWN",), (), (), ("guard_coverage",), ())
    all_checks: list[DecisionCheck] = []
    reasons: set[str] = set()
    unresolved: set[str] = set()
    effective = False
    for candidate in ordered:
        candidate_reasons: list[str] = []
        if candidate.phase not in {"before_growth", "inside_growth"}: candidate_reasons.append("GUARD_AFTER_MATERIALIZATION")
        if not candidate.dominates_growth: candidate_reasons.append("GUARD_DOES_NOT_DOMINATE_FLOW")
        if candidate.reject_path_reaches_growth: candidate_reasons.append("GUARD_REJECT_PATH_REACHES_GROWTH")
        if candidate.resource_dimension != growth.candidate.resource_dimension: candidate_reasons.append("GUARD_DIMENSION_MISMATCH")
        if candidate.scope != growth.candidate.escape_scope: candidate_reasons.append("GUARD_SCOPE_MISMATCH")
        if candidate.representation not in {"raw_body", "same", growth.candidate.field_path}: candidate_reasons.append("GUARD_REPRESENTATION_MISMATCH")
        if candidate.behavior not in {"reject", "block"}: candidate_reasons.append("GUARD_FAIL_OPEN")
        if not candidate.covers_materialization:
            candidate_reasons.append("GUARD_DOES_NOT_COVER_GROWTH" if candidate.coverage_status == "complete" else "GUARD_COVERAGE_UNKNOWN")
        if candidate.authorization_only: candidate_reasons.append("GUARD_AUTHORIZATION_ONLY")
        if candidate.configuration_key == "literal":
            try:
                literal_limit = int(candidate.configuration_value)
            except (TypeError, ValueError, OverflowError):
                literal_limit = 0
            if literal_limit <= 0:
                candidate_reasons.append("GUARD_CONFIGURATION_UNKNOWN"); unresolved.add("literal_limit")
        else:
            config = configuration.get(candidate.configuration_key)
            if config is None:
                candidate_reasons.append("GUARD_CONFIGURATION_UNKNOWN"); unresolved.add(candidate.configuration_key)
            elif config in {False, "disabled"}: candidate_reasons.append("GUARD_DISABLED_CONFIGURATION")
            elif config == "unbounded": candidate_reasons.append("GUARD_UNBOUNDED_CONFIGURATION")
            elif not isinstance(config, int) or isinstance(config, bool) or config <= 0:
                candidate_reasons.append("GUARD_CONFIGURATION_UNKNOWN"); unresolved.add(candidate.configuration_key)
            elif str(config) != candidate.configuration_value:
                candidate_reasons.append("GUARD_CONFIGURATION_MISMATCH")
        if candidate.coverage_status != "complete": candidate_reasons.append("GUARD_COVERAGE_UNKNOWN"); unresolved.add(candidate.guard_id)
        reasons.update(candidate_reasons)
        all_checks.extend(DecisionCheck(reason.removeprefix("GUARD_").lower(), False, reason, candidate.evidence) for reason in candidate_reasons)
        if not candidate_reasons:
            effective = True
            all_checks.append(DecisionCheck("guard_effective", True, None, candidate.evidence))
    status: Literal["effective", "ineffective", "unknown"] = "effective" if effective else "unknown" if any(reason.endswith("UNKNOWN") for reason in reasons) else "ineffective"
    return GuardDecision(status, () if effective else tuple(sorted(reasons)), tuple(all_checks), tuple(sorted({e for c in ordered for e in c.evidence})), tuple(sorted(unresolved)), tuple(c.guard_id for c in ordered))
