from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.entries import EntryFact
from dosweb.flows import VerifiedFlow
from dosweb.growth import VerifiedGrowthResult
from dosweb.lifecycle.guards import DecisionCheck, _boolean, _evidence, _site, _validate_context


@dataclass(frozen=True)
class ReleaseCandidate:
    release_id: str
    site_file: str
    site_start_line: int
    kind: str
    resource_dimension: str
    scope: str
    receiver: str
    key_identity: str
    synchronous: bool
    normal_path: bool
    exceptional_path: bool
    actual_reduction: bool
    after_growth: bool
    transfer_only: bool
    async_kind: str
    evidence: tuple[str, ...]
    coverage_status: str

    @classmethod
    def create(cls, **values: object) -> ReleaseCandidate:
        file, line = _site(values["site_file"], values["site_start_line"]); evidence = _evidence(values["evidence"])
        semantic = {**values, "site_file": file, "site_start_line": line, "evidence": list(evidence)}
        return cls(stable_identifier("release", semantic), file, line, str(values["kind"]), str(values["resource_dimension"]), str(values["scope"]), str(values["receiver"]), str(values["key_identity"]), _boolean(values["synchronous"], "synchronous"), _boolean(values["normal_path"], "normal_path"), _boolean(values["exceptional_path"], "exceptional_path"), _boolean(values["actual_reduction"], "actual_reduction"), _boolean(values["after_growth"], "after_growth"), _boolean(values["transfer_only"], "transfer_only"), str(values["async_kind"]), evidence, str(values["coverage_status"]))

    def to_dict(self) -> dict[str, object]:
        return {"release_id": self.release_id, "site": {"file": self.site_file, "start_line": self.site_start_line}, "kind": self.kind, "resource_dimension": self.resource_dimension, "scope": self.scope, "receiver": self.receiver, "key_identity": self.key_identity, "synchronous": self.synchronous, "normal_path": self.normal_path, "exceptional_path": self.exceptional_path, "actual_reduction": self.actual_reduction, "after_growth": self.after_growth, "transfer_only": self.transfer_only, "async_kind": self.async_kind, "evidence": list(self.evidence), "coverage_status": self.coverage_status}

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> ReleaseCandidate:
        site = record.get("site") if isinstance(record, Mapping) else None
        if not isinstance(site, Mapping): raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Release candidate site is malformed.")
        values = {**record, "site_file": site.get("file"), "site_start_line": site.get("start_line")}; values.pop("release_id", None); values.pop("site", None)
        candidate = cls.create(**values)
        if record.get("release_id") != candidate.release_id: raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Release candidate identifier is not canonical.")
        return candidate


@dataclass(frozen=True)
class ReleaseDecision:
    status: Literal["effective", "ineffective", "unknown", "absent"]
    classification: Literal["synchronous_effective", "insufficient_path_coverage", "receiver_or_key_mismatched", "potential_async", "not_effective", "unknown", "absent"]
    reason_codes: tuple[str, ...]
    checks: tuple[DecisionCheck, ...]
    evidence_ids: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
    candidate_ids: tuple[str, ...]


def evaluate_synchronous_release(entry: EntryFact, growth: VerifiedGrowthResult, flow: VerifiedFlow, candidates: Sequence[ReleaseCandidate], *, coverage_status: str = "complete") -> ReleaseDecision:
    _validate_context(entry, growth, flow)
    if coverage_status not in {"complete", "partial", "unsupported"}:
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Release coverage status is invalid.")
    ordered = tuple(sorted(candidates, key=lambda item: item.release_id))
    if not ordered:
        if coverage_status == "complete": return ReleaseDecision("absent", "absent", ("RELEASE_ABSENT",), (), (), (), ())
        return ReleaseDecision("unknown", "unknown", ("RELEASE_COVERAGE_UNKNOWN",), (), (), ("release_coverage",), ())
    reasons: set[str] = set(); checks: list[DecisionCheck] = []; unresolved: set[str] = set(); effective = False
    classification = "not_effective"
    for candidate in ordered:
        local: list[str] = []
        if not candidate.synchronous or candidate.async_kind != "none":
            local.append("RELEASE_POTENTIAL_ASYNC"); unresolved.add(candidate.async_kind); classification = "potential_async"
        whole_resource = candidate.kind in {"clear", "close"} and candidate.key_identity == "none"
        if (
            candidate.resource_dimension != growth.candidate.resource_dimension
            or candidate.scope != growth.candidate.escape_scope
            or candidate.receiver != growth.candidate.receiver
            or (not whole_resource and candidate.key_identity not in {item.name for item in growth.candidate.demand_inputs})
        ):
            local.append("RELEASE_RECEIVER_OR_KEY_MISMATCHED"); classification = "receiver_or_key_mismatched"
        if not candidate.after_growth or not candidate.normal_path or not candidate.exceptional_path:
            local.append("RELEASE_INSUFFICIENT_PATH_COVERAGE"); classification = "insufficient_path_coverage"
        if not candidate.actual_reduction: local.append("RELEASE_NO_ACTUAL_REDUCTION")
        if candidate.transfer_only: local.append("RELEASE_PAYLOAD_TRANSFER_ONLY"); unresolved.add(candidate.release_id); classification = "unknown"
        if candidate.coverage_status != "complete": local.append("RELEASE_COVERAGE_UNKNOWN"); unresolved.add(candidate.release_id); classification = "unknown"
        reasons.update(local); checks.extend(DecisionCheck(reason.removeprefix("RELEASE_").lower(), False, reason, candidate.evidence) for reason in local)
        if not local:
            effective = True; classification = "synchronous_effective"; checks.append(DecisionCheck("synchronous_release", True, None, candidate.evidence))
    unresolved_release = bool(reasons & {"RELEASE_POTENTIAL_ASYNC", "RELEASE_PAYLOAD_TRANSFER_ONLY", "RELEASE_COVERAGE_UNKNOWN"})
    if effective and not unresolved_release:
        status: Literal["effective", "ineffective", "unknown", "absent"] = "effective"
        classification = "synchronous_effective"
        output_reasons: tuple[str, ...] = ()
    else:
        if "RELEASE_POTENTIAL_ASYNC" in reasons:
            classification = "potential_async"
        elif "RELEASE_PAYLOAD_TRANSFER_ONLY" in reasons or "RELEASE_COVERAGE_UNKNOWN" in reasons:
            classification = "unknown"
        elif "RELEASE_RECEIVER_OR_KEY_MISMATCHED" in reasons:
            classification = "receiver_or_key_mismatched"
        elif "RELEASE_INSUFFICIENT_PATH_COVERAGE" in reasons:
            classification = "insufficient_path_coverage"
        status = "unknown" if classification in {"potential_async", "unknown"} else "ineffective"
        output_reasons = tuple(sorted(reasons))
    return ReleaseDecision(status, classification, output_reasons, tuple(checks), tuple(sorted({e for c in ordered for e in c.evidence})), tuple(sorted(unresolved)), tuple(c.release_id for c in ordered))
