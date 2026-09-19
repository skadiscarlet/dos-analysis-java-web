"""Sound binding of RC1 resource properties to production Growth paths."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from typing import Literal

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.entries import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.flows import VerifiedFlow
from dosweb.growth import VerifiedGrowthResult
from dosweb.resource_lifecycle.adapters import (
    ExtractedFacts,
    RawLifecycleFact,
    extracted_to_dict,
)

_BACKEND_VERSION = "resource-lifecycle-production-bridge-v3"
ResourceDecisionStatus = Literal[
    "refutes_relevant_growth", "unresolved", "not_applicable"
]


class ResourceLifecycleCoverageGap(ValueError):
    """Typed, reviewable absence of RC1 coverage for one production database."""

    reason_code = "RESOURCE_LIFECYCLE_SOURCE_SNAPSHOT_COVERAGE_UNRESOLVED"

    def __init__(
        self,
        *,
        database_fingerprint: str,
        source_snapshot_sha256: str,
        implementation_sha256: str,
    ) -> None:
        self.database_fingerprint = _digest(
            database_fingerprint, "database_fingerprint"
        )
        self.source_snapshot_sha256 = _digest(
            source_snapshot_sha256, "source_snapshot_sha256"
        )
        self.implementation_sha256 = _digest(
            implementation_sha256, "implementation_sha256"
        )
        super().__init__(
            "CodeQL source snapshot has unarchived declarations or "
            "unclassified semantics; dependency coverage unresolved"
        )


def _digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AnalyzerError(
            "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
            f"Resource lifecycle {field} is malformed.",
        )
    return value


@dataclass(frozen=True)
class ResourceLifecycleBackendRun:
    """One immutable extraction/solve result reused for a whole project."""

    extracted: ExtractedFacts
    results: Mapping[str, object]
    implementation_sha256: str
    facts_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.extracted, ExtractedFacts) or not isinstance(
            self.results, Mapping
        ):
            raise AnalyzerError(
                "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                "Resource lifecycle backend result is malformed.",
            )
        _digest(self.implementation_sha256, "implementation_sha256")
        _digest(self.facts_sha256, "facts_sha256")
        expected_facts = hashlib.sha256(
            canonical_json(extracted_to_dict(self.extracted)) + b"\n"
        ).hexdigest()
        if self.facts_sha256 != expected_facts:
            raise AnalyzerError(
                "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                "Resource lifecycle facts digest does not match the extracted facts.",
            )
        _digest(self.results.get("result_sha256"), "result_sha256")
        _digest(
            self.extracted.coverage.get("database_fingerprint"),
            "database_fingerprint",
        )
        _digest(
            self.extracted.coverage.get("source_snapshot_sha256"),
            "source_snapshot_sha256",
        )


@dataclass(frozen=True)
class ResourceLifecycleDecision:
    """Independent A2 decision; never represented as a legacy Bound."""

    decision_id: str
    status: ResourceDecisionStatus
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
    binding_id: str
    property_id: str | None
    result_sha256: str
    dimension: str | None
    scope: str | None
    cut: str | None
    upper_bound: int | None

    @classmethod
    def create(cls, **values: object) -> "ResourceLifecycleDecision":
        status = values["status"]
        if status not in {
            "refutes_relevant_growth",
            "unresolved",
            "not_applicable",
        }:
            raise AnalyzerError(
                "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                "Resource lifecycle decision status is invalid.",
            )
        semantic = {
            "status": status,
            "reason_codes": sorted(set(values["reason_codes"])),  # type: ignore[arg-type]
            "evidence_ids": sorted(set(values["evidence_ids"])),  # type: ignore[arg-type]
            "unresolved_facts": sorted(set(values["unresolved_facts"])),  # type: ignore[arg-type]
            "binding_id": values["binding_id"],
            "property_id": values["property_id"],
            "result_sha256": _digest(values["result_sha256"], "result_sha256"),
            "dimension": values["dimension"],
            "scope": values["scope"],
            "cut": values["cut"],
            "upper_bound": values["upper_bound"],
        }
        return cls(
            stable_identifier("resource-decision", semantic),
            status,  # type: ignore[arg-type]
            tuple(semantic["reason_codes"]),
            tuple(semantic["evidence_ids"]),
            tuple(semantic["unresolved_facts"]),
            str(semantic["binding_id"]),
            semantic["property_id"],  # type: ignore[arg-type]
            str(semantic["result_sha256"]),
            semantic["dimension"],  # type: ignore[arg-type]
            semantic["scope"],  # type: ignore[arg-type]
            semantic["cut"],  # type: ignore[arg-type]
            semantic["upper_bound"],  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "evidence_ids": list(self.evidence_ids),
            "unresolved_facts": list(self.unresolved_facts),
            "binding_id": self.binding_id,
            "property_id": self.property_id,
            "result_sha256": self.result_sha256,
            "dimension": self.dimension,
            "scope": self.scope,
            "cut": self.cut,
            "upper_bound": self.upper_bound,
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> "ResourceLifecycleDecision":
        try:
            decision = cls.create(
                status=record["status"],
                reason_codes=tuple(record["reason_codes"]),  # type: ignore[arg-type]
                evidence_ids=tuple(record["evidence_ids"]),  # type: ignore[arg-type]
                unresolved_facts=tuple(record["unresolved_facts"]),  # type: ignore[arg-type]
                binding_id=record["binding_id"],
                property_id=record["property_id"],
                result_sha256=record["result_sha256"],
                dimension=record["dimension"],
                scope=record["scope"],
                cut=record["cut"],
                upper_bound=record["upper_bound"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalyzerError(
                "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                "Resource lifecycle decision is malformed.",
            ) from exc
        if record.get("decision_id") != decision.decision_id:
            raise AnalyzerError(
                "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                "Resource lifecycle decision identifier is not canonical.",
            )
        return decision


@dataclass(frozen=True)
class ResourceLifecycleBindingDecision:
    record: Mapping[str, object]
    resource_decision: ResourceLifecycleDecision


def _unit_results(run: ResourceLifecycleBackendRun) -> dict[str, Mapping[str, object]]:
    units = run.results.get("units")
    if not isinstance(units, list):
        raise AnalyzerError(
            "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
            "Resource lifecycle solver units are missing.",
        )
    output: dict[str, Mapping[str, object]] = {}
    for item in units:
        if not isinstance(item, Mapping) or not isinstance(item.get("unit_id"), str):
            raise AnalyzerError(
                "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                "Resource lifecycle solver unit is malformed.",
            )
        if item["unit_id"] in output:
            raise AnalyzerError(
                "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                "Resource lifecycle solver unit identity is duplicated.",
            )
        output[item["unit_id"]] = item
    return output


def _dispatch_matches(
    result: VerifiedGrowthResult, flow: VerifiedFlow, extracted: ExtractedFacts
) -> tuple[RawLifecycleFact, ...]:
    candidate = result.candidate
    if candidate is None:
        return ()
    call_path = set(flow.proof.call_path)
    return tuple(
        sorted(
            (
                fact
                for fact in extracted.facts
                if fact.fact_kind == "dispatch"
                and fact.query_name == "resource_lifecycle_task_relations"
                and fact.coverage_status == "complete"
                and fact.location.path == candidate.site.file
                and fact.location.start_line == candidate.site.start_line
                and fact.site_callable in call_path
                and fact.holder_key in {candidate.receiver, candidate.field_path}
            ),
            key=lambda fact: (
                fact.unit_id,
                fact.program_point,
                fact.site_start_column,
                fact.fact_id,
            ),
        )
    )


def _binding_context(dispatch: RawLifecycleFact, run: ResourceLifecycleBackendRun):
    unit = next(
        (item for item in run.extracted.units if item.unit_id == dispatch.unit_id),
        None,
    )
    if unit is None:
        return None
    bindings = tuple(
        item
        for item in unit.program.task_bindings
        if dispatch.fact_id in item.evidence_ids
    )
    if len(bindings) != 1:
        return None
    binding = bindings[0]
    instances = tuple(
        item
        for item in unit.program.instances
        if item.instance_id == binding.instance_id
    )
    if len(instances) != 1:
        return None
    families = tuple(
        item
        for item in unit.program.families
        if item.family_id == instances[0].family_id
    )
    if len(families) != 1:
        return None
    return unit, binding, instances[0], families[0]


def _properties(
    unit_result: Mapping[str, object], executor_id: str
) -> tuple[Mapping[str, object], ...]:
    values = unit_result.get("properties")
    if not isinstance(values, list):
        return ()
    return tuple(
        sorted(
            (
                item
                for item in values
                if isinstance(item, Mapping)
                and item.get("dimension") == "accepted_task_population"
                and item.get("cut") == "arbitrary_finite_repetitions"
                and item.get("scope") == f"executor:{executor_id}"
                and item.get("executor_id") == executor_id
            ),
            key=lambda item: str(item.get("property_id", "")),
        )
    )


def _record(
    *,
    entry: EntryFact,
    result: VerifiedGrowthResult,
    flow: VerifiedFlow,
    run: ResourceLifecycleBackendRun,
    status: ResourceDecisionStatus,
    reason: str,
    dispatch: RawLifecycleFact | None = None,
    context: tuple[object, object, object, object] | None = None,
    prop: Mapping[str, object] | None = None,
) -> dict[str, object]:
    candidate = result.candidate
    unit, binding, instance, family = context or (None, None, None, None)
    allocation = getattr(family, "allocation", None)
    coverage = run.extracted.coverage
    semantic = {
        "entry_id": entry.entry_id,
        "growth_id": result.growth_id,
        "path_id": flow.path_id,
        "analysis_unit_id": getattr(unit, "unit_id", None),
        "resource_family_id": getattr(family, "family_id", None),
        "instance_id": getattr(instance, "instance_id", None),
        "task_binding_id": getattr(binding, "binding_id", None),
        "executor_contract_id": getattr(binding, "executor_contract_id", None),
        "submit_program_point": dispatch.program_point if dispatch else None,
        "submit_callable": dispatch.site_callable if dispatch else None,
        "submit_file": dispatch.location.path if dispatch else None,
        "submit_line": dispatch.location.start_line if dispatch else None,
        "submit_column": dispatch.site_start_column if dispatch else None,
        "submit_line_sha256": dispatch.site_line_sha256 if dispatch else None,
        "allocation_file": getattr(allocation, "path", None),
        "allocation_line": getattr(allocation, "start_line", None),
        "allocation_source_sha256": getattr(allocation, "source_sha256", None),
        "growth_dimension": candidate.resource_dimension if candidate else None,
        "growth_scope": candidate.escape_scope if candidate else None,
        "property_id": prop.get("property_id") if prop else None,
        "property_dimension": prop.get("dimension") if prop else None,
        "property_scope": prop.get("scope") if prop else None,
        "property_cut": prop.get("cut") if prop else None,
        "property_status": prop.get("status") if prop else None,
        "upper_bound": prop.get("upper_bound") if prop else None,
        "assumptions": list(prop.get("assumptions", [])) if prop else [],
        "coverage_gaps": list(prop.get("coverage_gaps", [])) if prop else [],
        "evidence_refs": list(prop.get("evidence_refs", [])) if prop else [],
        "binding_status": status,
        "reason_code": reason,
        "backend_version": _BACKEND_VERSION,
        "backend_implementation_sha256": run.implementation_sha256,
        "facts_sha256": run.facts_sha256,
        "result_sha256": run.results["result_sha256"],
        "database_fingerprint": coverage["database_fingerprint"],
        "source_snapshot_sha256": coverage["source_snapshot_sha256"],
        "query_sha256": dispatch.query_sha256 if dispatch else None,
    }
    return {"binding_id": stable_identifier("resource-binding", semantic), **semantic}


def bind_resource_lifecycle_property(
    entry: EntryFact,
    result: VerifiedGrowthResult,
    flow: VerifiedFlow,
    run: ResourceLifecycleBackendRun,
) -> ResourceLifecycleBindingDecision:
    candidate = result.candidate
    dispatch = None
    context = None
    prop = None
    if candidate is None or result.status != "verified" or not flow.satisfies_premise:
        status, reason = "unresolved", "RESOURCE_PROPERTY_PREMISE_UNRESOLVED"
    elif candidate.kind != "async_work_growth" or candidate.resource_dimension != "tasks":
        status, reason = (
            "not_applicable",
            "RESOURCE_PROPERTY_DIMENSION_NOT_CONSUMED",
        )
    else:
        matches = _dispatch_matches(result, flow, run.extracted)
        if len(matches) != 1:
            status = "unresolved"
            reason = (
                "RESOURCE_PROPERTY_DISPATCH_MISSING"
                if not matches
                else "RESOURCE_PROPERTY_DISPATCH_AMBIGUOUS"
            )
        else:
            dispatch = matches[0]
            context = _binding_context(dispatch, run)
            if context is None:
                status, reason = (
                    "unresolved",
                    "RESOURCE_PROPERTY_TASK_BINDING_UNRESOLVED",
                )
            else:
                unit, binding, _instance, _family = context
                unit_result = _unit_results(run).get(unit.unit_id)
                if unit_result is None:
                    raise AnalyzerError(
                        "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                        "Resource lifecycle solver result is missing an extracted unit.",
                    )
                properties = _properties(unit_result, binding.executor_contract_id)
                if len(properties) != 1:
                    status = "unresolved"
                    reason = (
                        "RESOURCE_PROPERTY_TASK_POPULATION_MISSING"
                        if not properties
                        else "RESOURCE_PROPERTY_TASK_POPULATION_AMBIGUOUS"
                    )
                else:
                    prop = properties[0]
                    gaps = prop.get("coverage_gaps")
                    upper = prop.get("upper_bound")
                    if (
                        prop.get("status") == "bounded"
                        and isinstance(upper, int)
                        and not isinstance(upper, bool)
                        and upper > 0
                        and isinstance(gaps, list)
                        and not gaps
                    ):
                        status = "refutes_relevant_growth"
                        reason = (
                            "RESOURCE_PROPERTY_ACCEPTED_TASK_POPULATION_BOUNDED"
                        )
                    else:
                        status = "unresolved"
                        reason = "RESOURCE_PROPERTY_TASK_POPULATION_UNRESOLVED"
    record = _record(
        entry=entry,
        result=result,
        flow=flow,
        run=run,
        status=status,  # type: ignore[arg-type]
        reason=reason,
        dispatch=dispatch,
        context=context,
        prop=prop,
    )
    evidence = tuple(
        sorted(
            {
                str(record["binding_id"]),
                *(
                    str(item)
                    for item in record["evidence_refs"]
                    if isinstance(item, str)
                ),
                *(
                    (str(record["property_id"]),)
                    if isinstance(record["property_id"], str)
                    else ()
                ),
            }
        )
    )
    decision = ResourceLifecycleDecision.create(
        status=status,
        reason_codes=(reason,),
        evidence_ids=evidence,
        unresolved_facts=(reason,) if status == "unresolved" else (),
        binding_id=record["binding_id"],
        property_id=record["property_id"],
        result_sha256=record["result_sha256"],
        dimension=record["property_dimension"],
        scope=record["property_scope"],
        cut=record["property_cut"],
        upper_bound=record["upper_bound"],
    )
    return ResourceLifecycleBindingDecision(record, decision)


def bind_resource_lifecycle_coverage_gap(
    entry: EntryFact,
    result: VerifiedGrowthResult,
    flow: VerifiedFlow,
    gap: ResourceLifecycleCoverageGap,
) -> ResourceLifecycleBindingDecision:
    """Bind an RC1 backend coverage gap without inventing solver facts."""

    candidate = result.candidate
    if candidate is None or result.status != "verified" or not flow.satisfies_premise:
        status: ResourceDecisionStatus = "unresolved"
        reason = "RESOURCE_PROPERTY_PREMISE_UNRESOLVED"
    elif candidate.kind != "async_work_growth" or candidate.resource_dimension != "tasks":
        status = "not_applicable"
        reason = "RESOURCE_PROPERTY_DIMENSION_NOT_CONSUMED"
    else:
        status = "unresolved"
        reason = gap.reason_code
    gap_evidence = {
        "reason_code": gap.reason_code,
        "database_fingerprint": gap.database_fingerprint,
        "source_snapshot_sha256": gap.source_snapshot_sha256,
        "backend_implementation_sha256": gap.implementation_sha256,
    }
    facts_sha256 = hashlib.sha256(canonical_json(gap_evidence) + b"\n").hexdigest()
    result_sha256 = hashlib.sha256(
        canonical_json(
            {
                **gap_evidence,
                "entry_id": entry.entry_id,
                "growth_id": result.growth_id,
                "path_id": flow.path_id,
                "status": status,
            }
        )
        + b"\n"
    ).hexdigest()
    semantic = {
        "entry_id": entry.entry_id,
        "growth_id": result.growth_id,
        "path_id": flow.path_id,
        "analysis_unit_id": None,
        "resource_family_id": None,
        "instance_id": None,
        "task_binding_id": None,
        "executor_contract_id": None,
        "submit_program_point": None,
        "submit_callable": None,
        "submit_file": None,
        "submit_line": None,
        "submit_column": None,
        "submit_line_sha256": None,
        "allocation_file": None,
        "allocation_line": None,
        "allocation_source_sha256": None,
        "growth_dimension": candidate.resource_dimension if candidate else None,
        "growth_scope": candidate.escape_scope if candidate else None,
        "property_id": None,
        "property_dimension": None,
        "property_scope": None,
        "property_cut": None,
        "property_status": None,
        "upper_bound": None,
        "assumptions": [],
        "coverage_gaps": [gap.reason_code],
        "evidence_refs": [],
        "binding_status": status,
        "reason_code": reason,
        "backend_version": _BACKEND_VERSION,
        "backend_implementation_sha256": gap.implementation_sha256,
        "facts_sha256": facts_sha256,
        "result_sha256": result_sha256,
        "database_fingerprint": gap.database_fingerprint,
        "source_snapshot_sha256": gap.source_snapshot_sha256,
        "query_sha256": None,
    }
    record = {"binding_id": stable_identifier("resource-binding", semantic), **semantic}
    decision = ResourceLifecycleDecision.create(
        status=status,
        reason_codes=(reason,),
        evidence_ids=(record["binding_id"],),
        unresolved_facts=(reason,) if status == "unresolved" else (),
        binding_id=record["binding_id"],
        property_id=None,
        result_sha256=result_sha256,
        dimension=None,
        scope=None,
        cut=None,
        upper_bound=None,
    )
    return ResourceLifecycleBindingDecision(record, decision)


__all__ = [
    "ResourceLifecycleBackendRun",
    "ResourceLifecycleBindingDecision",
    "ResourceLifecycleCoverageGap",
    "ResourceLifecycleDecision",
    "bind_resource_lifecycle_coverage_gap",
    "bind_resource_lifecycle_property",
]
