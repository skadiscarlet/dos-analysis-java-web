from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.schemas import validate_records

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.entries import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.flows.models import FlowProof
from dosweb.growth import VerifiedGrowthResult

FlowStatus = Literal["verified", "partial", "unresolved"]


@dataclass(frozen=True, order=True)
class FlowCheck:
    name: str
    passed: bool
    reason_code: str | None = None


@dataclass(frozen=True)
class VerifiedFlow:
    verified_flow_id: str
    path_id: str
    entry_id: str
    growth_id: str
    status: FlowStatus
    reason_codes: tuple[str, ...]
    checks: tuple[FlowCheck, ...]
    evidence_ids: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
    proof: FlowProof

    def __post_init__(self) -> None:
        if (
            not isinstance(self.proof, FlowProof)
            or self.path_id != self.proof.path_id
            or self.entry_id != self.proof.entry_id
            or self.growth_id != self.proof.growth_id
            or self.status not in {"verified", "partial", "unresolved"}
            or not isinstance(self.checks, tuple)
            or not self.checks
            or not all(isinstance(item, FlowCheck) for item in self.checks)
            or (self.status == "verified" and (self.reason_codes or not all(item.passed for item in self.checks)))
            or (self.status != "verified" and not self.reason_codes)
        ):
            raise AnalyzerError("ANALYSIS_FLOW_INVALID", "Verified flow result is malformed.")
        identity = {"path_id": self.path_id, "entry_id": self.entry_id, "growth_id": self.growth_id, "status": self.status, "reason_codes": list(self.reason_codes), "checks": [(item.name, item.passed, item.reason_code) for item in self.checks], "evidence_ids": list(self.evidence_ids), "unresolved_facts": list(self.unresolved_facts)}
        if self.verified_flow_id != stable_identifier("verified_flow", identity):
            raise AnalyzerError("ANALYSIS_FLOW_INVALID", "Verified flow identifier is malformed.")

    @property
    def satisfies_premise(self) -> bool:
        return self.status == "verified"

    def to_dict(self) -> dict[str, object]:
        return {"verified_flow_id": self.verified_flow_id, "path_id": self.path_id, "entry_id": self.entry_id, "growth_id": self.growth_id, "status": self.status, "reason_codes": list(self.reason_codes), "checks": [{"name": item.name, "passed": item.passed, "reason_code": item.reason_code} for item in self.checks], "evidence_ids": list(self.evidence_ids), "unresolved_facts": list(self.unresolved_facts), "proof": self.proof.to_dict()}


def load_verified_flows(path: Path, proofs: Mapping[str, FlowProof] | None = None) -> tuple[VerifiedFlow, ...]:
    records = read_jsonl_strict(path, "verified_flows")
    results: list[VerifiedFlow] = []
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {"verified_flow_id", "path_id", "entry_id", "growth_id", "status", "reason_codes", "checks", "evidence_ids", "unresolved_facts", "proof"}:
            raise AnalyzerError("ANALYSIS_FLOW_INVALID", "Verified flow record is malformed.")
        proof_record = record["proof"]
        proof = FlowProof.from_dict(proof_record) if isinstance(proof_record, Mapping) else None
        if proof is None or (proofs is not None and proofs.get(proof.path_id) != proof):
            raise AnalyzerError("ANALYSIS_FLOW_INVALID", "Verified flow proof is malformed.")
        checks = record["checks"]
        if not isinstance(checks, list): raise AnalyzerError("ANALYSIS_FLOW_INVALID", "Verified flow checks are malformed.")
        result = VerifiedFlow(cast(str, record["verified_flow_id"]), cast(str, record["path_id"]), cast(str, record["entry_id"]), cast(str, record["growth_id"]), cast(FlowStatus, record["status"]), tuple(record["reason_codes"]), tuple(FlowCheck(item["name"], item["passed"], item["reason_code"]) for item in checks), tuple(record["evidence_ids"]), tuple(record["unresolved_facts"]), proof)
        results.append(result)
    validate_records("flow_proofs", [result.proof.to_dict() for result in results])
    return tuple(results)


def _dangling(kind: str, identifier: str) -> AnalyzerError:
    return AnalyzerError("ANALYSIS_DANGLING_FACT_REFERENCE", "Flow proof refers to a missing normalized fact.", {"kind": kind, "identifier": identifier[:128]})


def verify_flow(flow: FlowProof, entries: Mapping[str, EntryFact], growth: Mapping[str, VerifiedGrowthResult]) -> VerifiedFlow:
    if not isinstance(flow, FlowProof) or not isinstance(entries, Mapping) or not isinstance(growth, Mapping):
        raise AnalyzerError("ANALYSIS_FLOW_INVALID", "Flow verification inputs are malformed.")
    if flow.entry_id not in entries:
        raise _dangling("entry", flow.entry_id)
    if flow.growth_id not in growth:
        raise _dangling("growth", flow.growth_id)
    entry = entries[flow.entry_id]
    growth_result = growth[flow.growth_id]
    if not isinstance(entry, EntryFact) or entry.entry_id != flow.entry_id or not isinstance(growth_result, VerifiedGrowthResult) or growth_result.growth_id != flow.growth_id:
        raise AnalyzerError("ANALYSIS_FLOW_INVALID", "Flow references are incompatible.")
    checks = [FlowCheck("entry_reference", True), FlowCheck("growth_reference", True)]
    evidence = tuple(sorted(growth_result.candidate.evidence_ids)) if growth_result.candidate else ()
    if growth_result.candidate is None:
        checks.append(FlowCheck("flow_semantics", False, "FLOW_GROWTH_CONTEXT_MISSING"))
        return _result(flow, "unresolved", ("FLOW_GROWTH_CONTEXT_MISSING",), checks, evidence, ("growth_context",))
    input_names = {item.name for item in entry.attacker_inputs}
    demand_names = {item.name for item in growth_result.candidate.demand_inputs if item.role == flow.attacker_control.target}
    if (
        flow.attacker_control.source not in input_names
        or not any(name in flow.attacker_control.sink for name in demand_names)
    ):
        checks.append(FlowCheck("flow_semantics", False, "FLOW_SEMANTIC_MAPPING_INVALID"))
        return _result(flow, "unresolved", ("FLOW_SEMANTIC_MAPPING_INVALID",), checks, evidence, ("attacker_control",))
    checks.append(FlowCheck("flow_semantics", True))
    if growth_result.status != "verified":
        checks.append(FlowCheck("verified_growth", False, "FLOW_GROWTH_NOT_VERIFIED"))
        return _result(flow, "unresolved", ("FLOW_GROWTH_NOT_VERIFIED",), checks, evidence, (growth_result.status,))
    checks.append(FlowCheck("verified_growth", True))
    if flow.flow_kind not in {"data_flow", "local_data_flow"}:
        checks.append(FlowCheck("data_flow_kind", False, "FLOW_KIND_NOT_PROVEN"))
        return _result(flow, "partial", ("FLOW_KIND_NOT_PROVEN",), checks, evidence, ("flow_kind",))
    checks.append(FlowCheck("data_flow_kind", True))
    if flow.coverage_status != "complete":
        checks.append(FlowCheck("complete_coverage", False, "FLOW_COVERAGE_INCOMPLETE"))
        reasons = ["FLOW_COVERAGE_INCOMPLETE"]
        if flow.confidence == "partial": reasons.append("FLOW_CONFIDENCE_PARTIAL")
        return _result(flow, "partial", tuple(reasons), checks, evidence, ("flow_coverage",))
    checks.append(FlowCheck("complete_coverage", True))
    if flow.confidence == "partial":
        checks.append(FlowCheck("proven_confidence", False, "FLOW_CONFIDENCE_PARTIAL"))
        return _result(flow, "partial", ("FLOW_CONFIDENCE_PARTIAL",), checks, evidence, ("flow_confidence",))
    checks.append(FlowCheck("proven_confidence", True))
    return _result(flow, "verified", (), checks, evidence, ())


def _result(flow: FlowProof, status: FlowStatus, reasons: tuple[str, ...], checks: list[FlowCheck], evidence: tuple[str, ...], unresolved: tuple[str, ...]) -> VerifiedFlow:
    reasons = tuple(sorted(set(reasons)))
    unresolved = tuple(sorted(set(unresolved)))
    identity = {"path_id": flow.path_id, "entry_id": flow.entry_id, "growth_id": flow.growth_id, "status": status, "reason_codes": list(reasons), "checks": [(item.name, item.passed, item.reason_code) for item in checks], "evidence_ids": list(evidence), "unresolved_facts": list(unresolved)}
    return VerifiedFlow(stable_identifier("verified_flow", identity), flow.path_id, flow.entry_id, flow.growth_id, status, reasons, tuple(checks), evidence, unresolved, flow)
