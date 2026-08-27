from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.schemas import validate_records
from typing import Literal, cast

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError
from dosweb.growth.models import BoundedSlice, GrowthContract, StaticFact
from dosweb.growth.slices import GrowthCandidate

VerificationStatus = Literal["verified", "rejected", "unresolved"]


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    reason_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "reason_code": self.reason_code}


@dataclass(frozen=True)
class VerifiedGrowthResult:
    verified_growth_id: str
    growth_id: str
    slice_id: str
    status: VerificationStatus
    reason_codes: tuple[str, ...]
    checks: tuple[VerificationCheck, ...]
    candidate: GrowthCandidate | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.verified_growth_id, str)
            or not self.verified_growth_id.startswith("verified_growth:")
            or not isinstance(self.growth_id, str)
            or not self.growth_id.startswith("growth:")
            or not isinstance(self.slice_id, str)
            or not self.slice_id.startswith("slice:")
            or self.status not in {"verified", "rejected", "unresolved"}
            or not isinstance(self.reason_codes, tuple)
            or not all(isinstance(item, str) and item for item in self.reason_codes)
            or not isinstance(self.checks, tuple)
            or not all(isinstance(item, VerificationCheck) for item in self.checks)
        ):
            raise AnalyzerError("ANALYSIS_GROWTH_VERIFICATION_INVALID", "Growth verification result is malformed.")
        if self.status == "verified" and (self.reason_codes or not self.checks or not all(check.passed for check in self.checks)):
            raise AnalyzerError("ANALYSIS_GROWTH_VERIFICATION_INVALID", "Verified growth requires successful checks and no failure reasons.")
        if self.status != "verified" and not self.reason_codes:
            raise AnalyzerError("ANALYSIS_GROWTH_VERIFICATION_INVALID", "Non-verified growth requires a reason.")
        if self.candidate is not None and (
            not isinstance(self.candidate, GrowthCandidate)
            or self.candidate.growth_id != self.growth_id
        ):
            raise AnalyzerError("ANALYSIS_GROWTH_VERIFICATION_INVALID", "Growth semantic context is incompatible.")

    @classmethod
    def create(
        cls,
        *,
        candidate: GrowthCandidate,
        slice_id: str,
        status: VerificationStatus,
        reason_codes: tuple[str, ...],
        checks: tuple[VerificationCheck, ...],
    ) -> VerifiedGrowthResult:
        identity = {
            "growth_id": candidate.growth_id,
            "slice_id": slice_id,
            "status": status,
            "reason_codes": list(reason_codes),
            "checks": [item.to_dict() for item in checks],
        }
        return cls(
            stable_identifier("verified_growth", identity),
            candidate.growth_id,
            slice_id,
            status,
            reason_codes,
            checks,
            candidate,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "verified_growth_id": self.verified_growth_id,
            "growth_id": self.growth_id,
            "slice_id": self.slice_id,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "checks": [item.to_dict() for item in self.checks],
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, object], candidate: GrowthCandidate | None = None) -> VerifiedGrowthResult:
        if not isinstance(record, Mapping) or set(record) != {"verified_growth_id", "growth_id", "slice_id", "status", "reason_codes", "checks"}:
            raise AnalyzerError("ANALYSIS_GROWTH_VERIFICATION_INVALID", "Growth verification record is malformed.")
        reasons = record["reason_codes"]; checks = record["checks"]
        if not isinstance(reasons, list) or not isinstance(checks, list):
            raise AnalyzerError("ANALYSIS_GROWTH_VERIFICATION_INVALID", "Growth verification record is malformed.")
        parsed = tuple(VerificationCheck(item["name"], item["passed"], item["reason_code"]) for item in checks if isinstance(item, Mapping) and set(item) == {"name", "passed", "reason_code"})
        result = cls(cast(str, record["verified_growth_id"]), cast(str, record["growth_id"]), cast(str, record["slice_id"]), cast(VerificationStatus, record["status"]), tuple(reasons), parsed, candidate)
        expected = stable_identifier("verified_growth", {"growth_id": result.growth_id, "slice_id": result.slice_id, "status": result.status, "reason_codes": list(result.reason_codes), "checks": [item.to_dict() for item in result.checks]})
        if result.verified_growth_id != expected: raise AnalyzerError("ANALYSIS_GROWTH_VERIFICATION_INVALID", "Growth verification identifier is not canonical.")
        return result


def load_verified_growth(path: Path, candidates: Mapping[str, GrowthCandidate] | None = None) -> tuple[VerifiedGrowthResult, ...]:
    records = read_jsonl_strict(path, "verified_growth")
    validate_records("verified_growth", records)
    results = tuple(VerifiedGrowthResult.from_dict(record, (candidates or {}).get(record["growth_id"])) for record in records)
    if len({item.verified_growth_id for item in results}) != len(results):
        raise AnalyzerError("ANALYSIS_GROWTH_VERIFICATION_INVALID", "Duplicate verified Growth identifier.")
    return results


def verify_growth_contract(
    candidate: GrowthCandidate,
    bounded_slice: BoundedSlice,
    contract: GrowthContract,
    static_fact_index: Mapping[str, StaticFact],
) -> VerifiedGrowthResult:
    if (
        not isinstance(candidate, GrowthCandidate)
        or not isinstance(bounded_slice, BoundedSlice)
        or not isinstance(contract, GrowthContract)
        or not isinstance(static_fact_index, Mapping)
        or bounded_slice.growth_id != candidate.growth_id
    ):
        raise AnalyzerError(
            "ANALYSIS_GROWTH_VERIFICATION_INVALID",
            "Growth verification inputs are incompatible.",
        )
    if any(not isinstance(key, str) or not isinstance(value, StaticFact) for key, value in static_fact_index.items()):
        raise AnalyzerError(
            "ANALYSIS_GROWTH_VERIFICATION_INVALID",
            "Static fact index is malformed.",
        )

    checks: list[VerificationCheck] = []
    if candidate.coverage_status != "complete":
        checks.append(
            VerificationCheck(
                "growth_coverage",
                False,
                "GROWTH_COVERAGE_INCOMPLETE",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_COVERAGE_INCOMPLETE",),
            checks,
        )
    checks.append(VerificationCheck("growth_coverage", True))

    if contract.contract_status == "growth_not_dos_relevant":
        checks.append(
            VerificationCheck(
                "dos_relevance",
                False,
                "GROWTH_NOT_DOS_RELEVANT",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "rejected",
            ("GROWTH_NOT_DOS_RELEVANT",),
            checks,
        )
    if contract.contract_status == "unknown":
        checks.append(
            VerificationCheck(
                "dos_relevance",
                False,
                "GROWTH_DOS_RELEVANCE_UNKNOWN",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_DOS_RELEVANCE_UNKNOWN",),
            checks,
        )
    checks.append(VerificationCheck("dos_relevance", True))

    if contract.is_resource_growth == "no":
        checks.append(VerificationCheck("resource_growth", False, "GROWTH_CONTRACT_NEGATED"))
        return _result(candidate, bounded_slice, "rejected", ("GROWTH_CONTRACT_NEGATED",), checks)
    if contract.is_resource_growth == "unknown":
        checks.append(VerificationCheck("resource_growth", False, "GROWTH_CONTRACT_UNKNOWN"))
        return _result(candidate, bounded_slice, "unresolved", ("GROWTH_CONTRACT_UNKNOWN",), checks)
    checks.append(VerificationCheck("resource_growth", True))

    if contract.growth_kind != candidate.kind:
        checks.append(VerificationCheck("growth_kind", False, "GROWTH_KIND_MISMATCH"))
        return _result(candidate, bounded_slice, "unresolved", ("GROWTH_KIND_MISMATCH",), checks)
    checks.append(VerificationCheck("growth_kind", True))

    if contract.resource_dimension != candidate.resource_dimension:
        checks.append(VerificationCheck("resource_dimension", False, "GROWTH_DIMENSION_MISMATCH"))
        return _result(candidate, bounded_slice, "unresolved", ("GROWTH_DIMENSION_MISMATCH",), checks)
    checks.append(VerificationCheck("resource_dimension", True))

    if contract.failure_mechanism in {"none", "unknown"}:
        checks.append(
            VerificationCheck(
                "failure_mechanism",
                False,
                "GROWTH_FAILURE_MECHANISM_UNPROVEN",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_FAILURE_MECHANISM_UNPROVEN",),
            checks,
        )
    checks.append(VerificationCheck("failure_mechanism", True))

    if contract.requests_to_pressure == "implausible":
        checks.append(
            VerificationCheck(
                "requests_to_pressure",
                False,
                "GROWTH_PRESSURE_IMPLAUSIBLE",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_PRESSURE_IMPLAUSIBLE",),
            checks,
        )
    checks.append(VerificationCheck("requests_to_pressure", True))

    if contract.attacker_value_space not in {"stream", "unlimited", "large"}:
        checks.append(
            VerificationCheck(
                "attacker_value_space",
                False,
                "GROWTH_ATTACKER_VALUE_SPACE_UNPROVEN",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_ATTACKER_VALUE_SPACE_UNPROVEN",),
            checks,
        )
    checks.append(VerificationCheck("attacker_value_space", True))

    if contract.amplification_class in {"low_amplification", "unknown"}:
        checks.append(
            VerificationCheck(
                "amplification_class",
                False,
                "GROWTH_AMPLIFICATION_NOT_DOS_RELEVANT",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_AMPLIFICATION_NOT_DOS_RELEVANT",),
            checks,
        )
    checks.append(VerificationCheck("amplification_class", True))

    slice_facts = {fact.fact_id: fact for fact in bounded_slice.payload.static_facts}
    required = tuple(contract.required_static_evidence)
    influence_ids = tuple(item.evidence_id for item in contract.attacker_influence)
    if not required or not influence_ids or any(
        fact_id not in slice_facts or fact_id not in static_fact_index
        for fact_id in (*required, *influence_ids)
    ):
        checks.append(VerificationCheck("required_static_evidence", False, "GROWTH_UNMAPPED_REQUIRED_EVIDENCE"))
        return _result(
            candidate, bounded_slice, "unresolved", ("GROWTH_UNMAPPED_REQUIRED_EVIDENCE",), checks
        )
    checks.append(VerificationCheck("required_static_evidence", True))

    allowed_locations = {excerpt.excerpt_id for excerpt in bounded_slice.source_excerpts}
    cited_ids = (*required, *influence_ids)
    if any(
        fact_id in static_fact_index
        and static_fact_index[fact_id].location_ref not in allowed_locations
        for fact_id in cited_ids
    ):
        checks.append(VerificationCheck("allowed_locations", False, "GROWTH_LOCATION_OUTSIDE_SLICE"))
        return _result(candidate, bounded_slice, "unresolved", ("GROWTH_LOCATION_OUTSIDE_SLICE",), checks)
    checks.append(VerificationCheck("allowed_locations", True))

    if any(static_fact_index[fact_id] != slice_facts[fact_id] for fact_id in cited_ids):
        checks.append(VerificationCheck("evidence_identity", False, "GROWTH_UNMAPPED_REQUIRED_EVIDENCE"))
        return _result(
            candidate, bounded_slice, "unresolved", ("GROWTH_UNMAPPED_REQUIRED_EVIDENCE",), checks
        )
    checks.append(VerificationCheck("evidence_identity", True))

    demand_roles = {item.role for item in candidate.demand_inputs}
    influence_ok = True
    for influence in contract.attacker_influence:
        indexed = static_fact_index.get(influence.evidence_id)
        sliced = slice_facts.get(influence.evidence_id)
        if (
            influence.target not in demand_roles
            or indexed is None
            or sliced is None
            or indexed.relation not in {"source", "flows_to"}
            or sliced.relation not in {"source", "flows_to"}
        ):
            influence_ok = False
            break
    if not influence_ok:
        checks.append(VerificationCheck("attacker_influence", False, "GROWTH_UNMAPPED_ATTACKER_INFLUENCE"))
        return _result(
            candidate, bounded_slice, "unresolved", ("GROWTH_UNMAPPED_ATTACKER_INFLUENCE",), checks
        )
    checks.append(VerificationCheck("attacker_influence", True))

    driver_ok = all(
        static_fact_index[item.evidence_id].kind in {"flow", "driver_origin"}
        and static_fact_index[item.evidence_id].normalized_value
        in {
            "request_body", "request_parameter", "request_path", "request_header",
            "request_stream", "network_message",
        }
        for item in contract.attacker_influence
    )
    if not driver_ok:
        checks.append(
            VerificationCheck(
                "driver_origin",
                False,
                "GROWTH_DRIVER_EVIDENCE_UNMAPPED",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_DRIVER_EVIDENCE_UNMAPPED",),
            checks,
        )
    checks.append(VerificationCheck("driver_origin", True))

    required_facts = tuple(static_fact_index[fact_id] for fact_id in required)
    value_space_ok = any(
        fact.kind == "value_space"
        and fact.normalized_value == contract.attacker_value_space
        and fact.relation in {"source", "flows_to"}
        for fact in required_facts
    )
    if not value_space_ok:
        checks.append(
            VerificationCheck(
                "value_space_evidence",
                False,
                "GROWTH_VALUE_SPACE_EVIDENCE_UNMAPPED",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_VALUE_SPACE_EVIDENCE_UNMAPPED",),
            checks,
        )
    checks.append(VerificationCheck("value_space_evidence", True))

    retention_ok = any(
        fact.kind == "retention"
        and fact.normalized_value == contract.retention_window
        and fact.relation == "sink"
        for fact in required_facts
    )
    if not retention_ok:
        checks.append(
            VerificationCheck(
                "retention_evidence",
                False,
                "GROWTH_RETENTION_EVIDENCE_UNMAPPED",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_RETENTION_EVIDENCE_UNMAPPED",),
            checks,
        )
    checks.append(VerificationCheck("retention_evidence", True))

    amplification_ok = any(
        fact.kind == "amplification"
        and fact.normalized_value == contract.amplification_class
        and fact.relation == "sink"
        for fact in required_facts
    )
    if not amplification_ok:
        checks.append(
            VerificationCheck(
                "amplification_evidence",
                False,
                "GROWTH_AMPLIFICATION_EVIDENCE_UNMAPPED",
            )
        )
        return _result(
            candidate,
            bounded_slice,
            "unresolved",
            ("GROWTH_AMPLIFICATION_EVIDENCE_UNMAPPED",),
            checks,
        )
    checks.append(VerificationCheck("amplification_evidence", True))
    return _result(candidate, bounded_slice, "verified", (), checks)


def _result(
    candidate: GrowthCandidate,
    bounded_slice: BoundedSlice,
    status: VerificationStatus,
    reason_codes: tuple[str, ...],
    checks: list[VerificationCheck],
) -> VerifiedGrowthResult:
    identity = {
        "growth_id": candidate.growth_id,
        "slice_id": bounded_slice.slice_id,
        "status": status,
        "reason_codes": list(reason_codes),
        "checks": [item.to_dict() for item in checks],
    }
    return VerifiedGrowthResult(
        stable_identifier("verified_growth", identity),
        candidate.growth_id,
        bounded_slice.slice_id,
        status,
        reason_codes,
        tuple(checks),
        candidate,
    )
