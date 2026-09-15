"""Publish solver-checked properties; consumers only select these records.

No oracle, path count, or inferred zero belongs in this interface. Legacy
DimensionResult and PopulationProperty remain the checking backend.
"""
from __future__ import annotations

from collections.abc import Mapping

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.resource_lifecycle.invariants import PopulationProperty
from dosweb.resource_lifecycle.models import DimensionResult


def publish_properties(
    unit_id: str,
    dimensions: tuple[DimensionResult, ...],
    populations: tuple[PopulationProperty, ...],
    *, input_identity: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for item in dimensions:
        cut = "all_modeled_exits"
        if item.scope.startswith("after_task_termination:"):
            cut = "after_task_termination:" + item.scope.rsplit(":", 1)[1]
        elif item.scope == "all_tasks_terminated_after_request":
            cut = item.scope
        records.append({
            "analysis_unit_id": unit_id,
            "resource_family_id": item.resource_family_id,
            "executor_id": None,
            "dimension": item.dimension,
            "scope": item.scope,
            "cut": cut,
            "status": item.lifecycle_status,
            "upper_bound": item.upper_bound,
            "relation": None,
            "assumptions": list(item.assumptions),
            "coverage_gaps": list(item.reason_codes),
            "unknown_reasons": list(item.reason_codes),
            "evidence_refs": list(item.evidence_ids),
        })
    for item in populations:
        records.append({
            "analysis_unit_id": unit_id,
            "resource_family_id": None,
            "executor_id": item.scope.removeprefix("executor:"),
            "dimension": item.dimension,
            "scope": item.scope,
            "cut": "arbitrary_finite_repetitions",
            "status": item.lifecycle_status,
            "upper_bound": item.total_upper_bound if item.lifecycle_status == "bounded" else None,
            "relation": "q<=K, a<=W, q+a<=K+W" if item.lifecycle_status == "bounded" else None,
            "assumptions": list(item.assumptions) + [item.repeat_assumption],
            "coverage_gaps": list(item.unknown_reasons),
            "unknown_reasons": list(item.unknown_reasons),
            "evidence_refs": list(item.evidence_ids),
        })
    for record in records:
        record["property_id"] = stable_identifier("resource-property-v1.2", {
            **{"input_identity": input_identity},
            **{key: record[key] for key in (
                "analysis_unit_id", "resource_family_id", "executor_id", "dimension", "scope", "cut"
            )}
        })
    if len({record["property_id"] for record in records}) != len(records):
        raise ValueError("duplicate published property identity")
    return sorted(records, key=lambda item: str(item["property_id"]))


def select_properties(
    result: Mapping[str, object], *, dimension: str, scope: str, cut: str,
    family_id: str | None = None, executor_id: str | None = None,
) -> list[Mapping[str, object]]:
    """Select records without changing their semantics or synthesizing results."""
    properties = result.get("properties", [])
    if not isinstance(properties, list):
        return []
    selected = []
    for item in properties:
        if not isinstance(item, Mapping):
            continue
        if item.get("dimension") != dimension or item.get("cut") != cut:
            continue
        if family_id is not None and item.get("resource_family_id") != family_id:
            continue
        if executor_id is not None and item.get("executor_id") != executor_id:
            continue
        actual_scope = item.get("scope")
        matches_scope = actual_scope == scope
        if scope == "executor":
            matches_scope = isinstance(actual_scope, str) and actual_scope.startswith("executor:")
        elif scope in {"task", "resource_family"}:
            matches_scope = actual_scope == cut or (
                isinstance(actual_scope, str) and actual_scope.startswith("after_task_termination:")
            )
        if matches_scope:
            selected.append(item)
    return selected
