from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.entries import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.flows import VerifiedFlow
from dosweb.growth import VerifiedGrowthResult
from dosweb.lifecycle.guards import DecisionCheck, ModeledConfiguration, _boolean, _evidence, _site, _validate_context

BoundStatus = Literal["absent", "scope_mismatched", "dimension_mismatched", "possibly_over_budget", "effective", "unknown"]


@dataclass(frozen=True)
class BoundCandidate:
    bound_id: str
    site_file: str
    site_start_line: int
    kind: str
    resource_dimension: str
    scope: str
    behavior: str
    receiver: str
    field_path: str
    result_checked: bool
    configuration_key: str
    configuration_value: str
    phase: str
    covers_flow: bool
    request_encoding: str
    queue_resource: str
    product_bound: bool
    evidence: tuple[str, ...]
    coverage_status: str

    @classmethod
    def create(cls, **values: object) -> BoundCandidate:
        file, line = _site(values["site_file"], values["site_start_line"]); evidence = _evidence(values["evidence"])
        semantic = {**values, "site_file": file, "site_start_line": line, "evidence": list(evidence)}
        return cls(stable_identifier("bound", semantic), file, line, str(values["kind"]), str(values["resource_dimension"]), str(values["scope"]), str(values["behavior"]), str(values["receiver"]), str(values["field_path"]), _boolean(values["result_checked"], "result_checked"), str(values["configuration_key"]), str(values["configuration_value"]), str(values["phase"]), _boolean(values["covers_flow"], "covers_flow"), str(values["request_encoding"]), str(values["queue_resource"]), _boolean(values["product_bound"], "product_bound"), evidence, str(values["coverage_status"]))

    def to_dict(self) -> dict[str, object]:
        return {"bound_id": self.bound_id, "site": {"file": self.site_file, "start_line": self.site_start_line}, "kind": self.kind, "resource_dimension": self.resource_dimension, "scope": self.scope, "behavior": self.behavior, "receiver": self.receiver, "field_path": self.field_path, "result_checked": self.result_checked, "configuration_key": self.configuration_key, "configuration_value": self.configuration_value, "phase": self.phase, "covers_flow": self.covers_flow, "request_encoding": self.request_encoding, "queue_resource": self.queue_resource, "product_bound": self.product_bound, "evidence": list(self.evidence), "coverage_status": self.coverage_status}

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> BoundCandidate:
        site = record.get("site") if isinstance(record, Mapping) else None
        if not isinstance(site, Mapping): raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Bound candidate site is malformed.")
        values = {**record, "site_file": site.get("file"), "site_start_line": site.get("start_line")}; values.pop("bound_id", None); values.pop("site", None)
        candidate = cls.create(**values)
        if record.get("bound_id") != candidate.bound_id: raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Bound candidate identifier is not canonical.")
        return candidate


@dataclass(frozen=True)
class BoundDecision:
    status: BoundStatus
    reason_codes: tuple[str, ...]
    checks: tuple[DecisionCheck, ...]
    evidence_ids: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
    candidate_ids: tuple[str, ...]


def evaluate_bound(entry: EntryFact, growth: VerifiedGrowthResult, flow: VerifiedFlow, candidates: Sequence[BoundCandidate], configuration: ModeledConfiguration, *, coverage_status: str = "complete") -> BoundDecision:
    _validate_context(entry, growth, flow)
    if coverage_status not in {"complete", "partial", "unsupported"}:
        raise AnalyzerError("ANALYSIS_LIFECYCLE_INVALID", "Bound coverage status is invalid.")
    ordered = tuple(sorted(candidates, key=lambda item: item.bound_id))
    if not ordered:
        if coverage_status == "complete": return BoundDecision("absent", ("BOUND_ABSENT",), (), (), (), ())
        return BoundDecision("unknown", ("BOUND_COVERAGE_UNKNOWN",), (), (), ("bound_coverage",), ())
    reasons: set[str] = set(); unresolved: set[str] = set(); checks: list[DecisionCheck] = []; effective = False
    has_scope = has_dimension = False
    for candidate in ordered:
        local: list[str] = []
        if candidate.scope != growth.candidate.escape_scope: local.append("BOUND_SCOPE_MISMATCH"); has_scope = True
        if candidate.resource_dimension != growth.candidate.resource_dimension: local.append("BOUND_DIMENSION_MISMATCH"); has_dimension = True
        if candidate.receiver != growth.candidate.receiver: local.append("BOUND_RECEIVER_MISMATCH")
        if not candidate.result_checked: local.append("BOUND_RESULT_IGNORED")
        if candidate.queue_resource != growth.candidate.field_path: local.append("BOUND_QUEUE_CONFIGURATION_MISMATCH")
        from dosweb.lifecycle.framework_limits import framework_limit_reason_codes
        framework_reasons = framework_limit_reason_codes(entry, candidate)
        if framework_reasons is None:
            if candidate.request_encoding not in {"raw_body", "any"}:
                local.append("BOUND_REQUEST_ENCODING_MISMATCH")
        else:
            local.extend(framework_reasons)
        if not candidate.product_bound: local.append("BOUND_MULTIPLICATIVE_DEMAND_UNCOVERED")
        if candidate.phase not in {"before_growth", "inside_growth"} or not candidate.covers_flow or candidate.behavior not in {"reject", "block", "evict"}: local.append("BOUND_POSSIBLY_OVER_BUDGET")
        if candidate.configuration_key == "literal":
            try:
                literal_capacity = int(candidate.configuration_value)
            except (TypeError, ValueError, OverflowError):
                literal_capacity = 0
            if literal_capacity <= 0:
                local.append("BOUND_CONFIGURATION_UNKNOWN"); unresolved.add("literal_capacity")
        else:
            config = configuration.get(candidate.configuration_key)
            if config is None: local.append("BOUND_CONFIGURATION_UNKNOWN"); unresolved.add(candidate.configuration_key)
            elif config in {False, "disabled"}: local.append("BOUND_DISABLED_CONFIGURATION")
            elif config == "unbounded": local.append("BOUND_UNBOUNDED_CONFIGURATION")
            elif not isinstance(config, int) or isinstance(config, bool) or config <= 0: local.append("BOUND_CONFIGURATION_UNKNOWN"); unresolved.add(candidate.configuration_key)
            elif str(config) != candidate.configuration_value: local.append("BOUND_CONFIGURATION_MISMATCH")
        if candidate.coverage_status != "complete": local.append("BOUND_COVERAGE_UNKNOWN"); unresolved.add(candidate.bound_id)
        reasons.update(local); checks.extend(DecisionCheck(reason.removeprefix("BOUND_").lower(), False, reason, candidate.evidence) for reason in local)
        if not local: effective = True; checks.append(DecisionCheck("bound_effective", True, None, candidate.evidence))
    if effective: status: BoundStatus = "effective"; output_reasons: tuple[str, ...] = ()
    elif any(reason.endswith("UNKNOWN") for reason in reasons): status = "unknown"; output_reasons = tuple(sorted(reasons))
    elif reasons == {"BOUND_SCOPE_MISMATCH"}: status = "scope_mismatched"; output_reasons = tuple(reasons)
    elif reasons == {"BOUND_DIMENSION_MISMATCH"}: status = "dimension_mismatched"; output_reasons = tuple(reasons)
    else: status = "possibly_over_budget"; reasons.add("BOUND_POSSIBLY_OVER_BUDGET"); output_reasons = tuple(sorted(reasons))
    return BoundDecision(status, output_reasons, tuple(checks), tuple(sorted({e for c in ordered for e in c.evidence})), tuple(sorted(unresolved)), tuple(c.bound_id for c in ordered))
