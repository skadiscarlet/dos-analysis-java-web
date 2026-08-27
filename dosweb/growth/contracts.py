from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal, cast

from dosweb.errors import AnalyzerError
from dosweb.growth.models import AttackerInfluence, GrowthContract


_CONTRACT_KEYS = frozenset(
    {
        "is_resource_growth",
        "growth_kind",
        "resource_dimension",
        "attacker_influence",
        "resource_effect",
        "attacker_variable",
        "attacker_value_space",
        "growth_unit",
        "growth_function",
        "amplification_class",
        "requests_to_pressure",
        "concurrency_model",
        "retention_window",
        "failure_mechanism",
        "failure_signal",
        "required_static_evidence",
        "contract_status",
        "rejection_reason",
        "confidence",
    }
)
_GROWTH_VALUES = frozenset({"yes", "no", "unknown"})
_GROWTH_KIND_VALUES = frozenset(
    {
        "input_materialization",
        "direct_allocation",
        "container_growth",
        "async_work_growth",
        "unknown",
    }
)
_RESOURCE_DIMENSION_VALUES = frozenset(
    {"entries", "bytes", "tasks", "connections", "objects", "unknown"}
)
_CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})
_RESOURCE_EFFECT_VALUES = frozenset({"materializes_bytes", "allocates_objects", "adds_entries", "enqueues_tasks", "opens_connections", "unknown"})
_VALUE_SPACE_VALUES = frozenset({"stream", "unlimited", "large", "limited", "server_controlled", "unknown"})
_AMPLIFICATION_VALUES = frozenset({"superlinear", "large_single_request", "concurrent_retention", "queue_instability", "high_cardinality_retention", "low_amplification", "unknown"})
_REQUEST_PRESSURE_VALUES = frozenset({"one", "few", "many", "implausible", "unknown"})
_RETENTION_VALUES = frozenset({"request", "session", "process", "until_release", "unknown"})
_FAILURE_VALUES = frozenset({"heap_exhaustion", "gc_thrashing", "cpu_starvation", "thread_exhaustion", "connection_exhaustion", "queue_latency_collapse", "none", "unknown"})
_CONTRACT_STATUS_VALUES = frozenset({"dos_relevant", "growth_not_dos_relevant", "unknown"})
_REJECTION_VALUES = frozenset({"none", "request_local_bounded", "server_controlled", "fixed_cardinality", "effective_precondition", "low_amplification", "no_failure_mechanism", "unknown"})
_INFLUENCE_TARGETS = frozenset({"size", "key", "value", "iteration_count", "submission_count", "unknown"})
_MAX_CONTRACT_BYTES = 131072
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 256
_MAX_JSON_COLLECTION = 64
_MAX_JSON_STRING_BYTES = 65536


def validate_growth_contract(payload: object) -> GrowthContract:
    if not isinstance(payload, Mapping) or set(payload) != _CONTRACT_KEYS:
        _schema_error()
    is_resource_growth = _enum(payload, "is_resource_growth", _GROWTH_VALUES)
    growth_kind = _enum(payload, "growth_kind", _GROWTH_KIND_VALUES)
    resource_dimension = _enum(payload, "resource_dimension", _RESOURCE_DIMENSION_VALUES)
    confidence = _enum(payload, "confidence", _CONFIDENCE_VALUES)
    resource_effect = _enum(payload, "resource_effect", _RESOURCE_EFFECT_VALUES)
    attacker_value_space = _enum(payload, "attacker_value_space", _VALUE_SPACE_VALUES)
    amplification_class = _enum(payload, "amplification_class", _AMPLIFICATION_VALUES)
    requests_to_pressure = _enum(payload, "requests_to_pressure", _REQUEST_PRESSURE_VALUES)
    retention_window = _enum(payload, "retention_window", _RETENTION_VALUES)
    failure_mechanism = _enum(payload, "failure_mechanism", _FAILURE_VALUES)
    contract_status = _enum(payload, "contract_status", _CONTRACT_STATUS_VALUES)
    rejection_reason = _enum(payload, "rejection_reason", _REJECTION_VALUES)
    attacker_variable = _text(payload, "attacker_variable")
    growth_unit = _text(payload, "growth_unit")
    growth_function = _text(payload, "growth_function")
    concurrency_model = _text(payload, "concurrency_model")
    failure_signal = _text(payload, "failure_signal")
    influence = payload["attacker_influence"]
    if not isinstance(influence, list) or len(influence) > 16:
        _schema_error()
    typed_influence: list[AttackerInfluence] = []
    for item in influence:
        if not isinstance(item, Mapping) or set(item) != {"target", "evidence_id"}:
            _schema_error()
        target = _enum(item, "target", _INFLUENCE_TARGETS)
        evidence_id = item["evidence_id"]
        if not isinstance(evidence_id, str) or len(evidence_id.encode("utf-8")) > 256:
            _schema_error()
        typed_influence.append(AttackerInfluence(target, evidence_id))
    required_evidence = payload["required_static_evidence"]
    if not isinstance(required_evidence, list) or len(required_evidence) > 32 or any(
        not isinstance(item, str) or len(item.encode("utf-8")) > 256 for item in required_evidence
    ):
        _schema_error()
    return GrowthContract(
        is_resource_growth=cast(Literal["yes", "no", "unknown"], is_resource_growth),
        growth_kind=cast(
            Literal[
                "input_materialization",
                "direct_allocation",
                "container_growth",
                "async_work_growth",
                "unknown",
            ],
            growth_kind,
        ),
        resource_dimension=cast(
            Literal["entries", "bytes", "tasks", "connections", "objects", "unknown"],
            resource_dimension,
        ),
        attacker_influence=tuple(typed_influence),
        resource_effect=resource_effect,
        attacker_variable=attacker_variable,
        attacker_value_space=attacker_value_space,
        growth_unit=growth_unit,
        growth_function=growth_function,
        amplification_class=amplification_class,
        requests_to_pressure=requests_to_pressure,
        concurrency_model=concurrency_model,
        retention_window=retention_window,
        failure_mechanism=failure_mechanism,
        failure_signal=failure_signal,
        required_static_evidence=tuple(required_evidence),
        contract_status=contract_status,
        rejection_reason=rejection_reason,
        confidence=cast(Literal["high", "medium", "low"], confidence),
    )


def parse_growth_contract_json(content: object) -> GrowthContract:
    if not isinstance(content, str) or not content.strip():
        _schema_error()
    try:
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_CONTRACT_BYTES:
            raise ValueError("contract JSON exceeds safe size limit")
        payload = json.loads(encoded.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        _check_json_bounds(payload)
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError) as exc:
        raise AnalyzerError(
            "LLM_RESPONSE_SCHEMA_INVALID",
            "The provider response content is not a strict JSON contract.",
        ) from exc
    return validate_growth_contract(payload)


def _check_json_bounds(value: object, depth: int = 0, nodes: list[int] | None = None) -> None:
    nodes = [] if nodes is None else nodes
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("contract JSON is too deeply nested")
    nodes.append(1)
    if len(nodes) > _MAX_JSON_NODES:
        raise ValueError("contract JSON has too many values")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _MAX_JSON_STRING_BYTES:
            raise ValueError("contract JSON string is too large")
    elif isinstance(value, dict):
        if len(value) > _MAX_JSON_COLLECTION:
            raise ValueError("contract JSON object is too large")
        for child in value.values():
            _check_json_bounds(child, depth + 1, nodes)
    elif isinstance(value, list):
        if len(value) > _MAX_JSON_COLLECTION:
            raise ValueError("contract JSON array is too large")
        for child in value:
            _check_json_bounds(child, depth + 1, nodes)


def validate_contract_static_evidence(contract: GrowthContract, static_fact_ids: object) -> GrowthContract:
    if not isinstance(static_fact_ids, frozenset) or not all(isinstance(fact_id, str) for fact_id in static_fact_ids):
        _schema_error()
    referenced_ids = [item.evidence_id for item in contract.attacker_influence]
    referenced_ids.extend(contract.required_static_evidence)
    if not all(fact_id in static_fact_ids for fact_id in referenced_ids):
        _schema_error()
    return contract


def _enum(payload: Mapping[str, object], name: str, values: frozenset[str]) -> str:
    value = payload[name]
    if not isinstance(value, str) or value not in values:
        _schema_error()
    return value


def _text(payload: Mapping[str, object], name: str) -> str:
    value = payload[name]
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 4096:
        _schema_error()
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate JSON key")
        output[key] = value
    return output


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _schema_error() -> None:
    raise AnalyzerError(
        "LLM_RESPONSE_SCHEMA_INVALID",
        "The provider response does not match the Growth Contract schema.",
    )
