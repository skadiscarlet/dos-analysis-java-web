# Bumped after the Growth provider wire schema was flattened for provider
# compatibility; cross-field invariants remain enforced by the prompt and local
# typed validation.
PROMPT_VERSION = "growth-contract-v9"
RESPONSE_SCHEMA_VERSION = "growth-contract-schema-v5"
AUTH_PROMPT_VERSION = "auth-contract-v5"
AUTH_RESPONSE_SCHEMA_VERSION = "auth-contract-schema-v3"

AUTH_CONTRACT_RESPONSE_SCHEMA = {
    "auth_context": ["unauthenticated", "low_privilege", "privileged", "unknown"],
    "evidence_ids": ["security:<ordinal>"],
    "assumptions": ["bounded text"],
    "confidence": ["high", "medium", "low"],
}

GROWTH_CONTRACT_RESPONSE_SCHEMA = {
    "is_resource_growth": ["yes", "no", "unknown"],
    "attacker_evidence_ids": ["fact:<ordinal>"],
    "resource_effect": ["materializes_bytes", "allocates_objects", "adds_entries", "enqueues_tasks", "opens_connections", "unknown"],
    "attacker_variable": "bounded safe text",
    "attacker_value_space": ["stream", "unlimited", "large", "limited", "server_controlled", "unknown"],
    "growth_unit": "bounded safe text",
    "growth_function": "bounded safe text",
    "amplification_class": ["superlinear", "large_single_request", "concurrent_retention", "queue_instability", "high_cardinality_retention", "low_amplification", "unknown"],
    "requests_to_pressure": ["one", "few", "many", "implausible", "unknown"],
    "concurrency_model": "bounded safe text",
    "retention_window": ["request", "session", "process", "until_release", "unknown"],
    "failure_mechanism": ["heap_exhaustion", "gc_thrashing", "cpu_starvation", "thread_exhaustion", "connection_exhaustion", "queue_latency_collapse", "none", "unknown"],
    "failure_signal": "bounded safe text",
    "required_static_evidence": ["fact:<ordinal>"],
    "contract_status": ["dos_relevant", "growth_not_dos_relevant", "unknown"],
    "rejection_reason": ["none", "request_local_bounded", "server_controlled", "fixed_cardinality", "effective_precondition", "low_amplification", "no_failure_mechanism", "unknown"],
    "confidence": ["high", "medium", "low"],
}


def _enum(values: list[str]) -> dict[str, object]:
    return {"type": "string", "enum": values}


_FACT_ALIAS = {
    "type": "array",
    "items": {"type": "string", "pattern": r"^fact:[1-9][0-9]*$"},
    "uniqueItems": True,
}
_BOUNDED_TEXT = {
    "type": "string",
    "minLength": 1,
    "maxLength": 4096,
    "pattern": r"^[^\r\n]+$",
}


GROWTH_CONTRACT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "is_resource_growth": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["is_resource_growth"]),
        "attacker_evidence_ids": {**_FACT_ALIAS, "maxItems": 16},
        "resource_effect": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["resource_effect"]),
        "attacker_variable": _BOUNDED_TEXT,
        "attacker_value_space": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["attacker_value_space"]),
        "growth_unit": _BOUNDED_TEXT,
        "growth_function": _BOUNDED_TEXT,
        "amplification_class": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["amplification_class"]),
        "requests_to_pressure": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["requests_to_pressure"]),
        "concurrency_model": _BOUNDED_TEXT,
        "retention_window": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["retention_window"]),
        "failure_mechanism": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["failure_mechanism"]),
        "failure_signal": _BOUNDED_TEXT,
        "required_static_evidence": {**_FACT_ALIAS, "maxItems": 32},
        "contract_status": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["contract_status"]),
        "rejection_reason": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["rejection_reason"]),
        "confidence": _enum(GROWTH_CONTRACT_RESPONSE_SCHEMA["confidence"]),
    },
    "required": sorted(GROWTH_CONTRACT_RESPONSE_SCHEMA),
    "additionalProperties": False,
}


AUTH_CONTRACT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "auth_context": _enum(AUTH_CONTRACT_RESPONSE_SCHEMA["auth_context"]),
        "evidence_ids": {
            "type": "array",
            "items": {"type": "string", "pattern": r"^security:[1-9][0-9]*$"},
            "maxItems": 32,
            "uniqueItems": True,
        },
        "assumptions": {
            "type": "array",
            "items": _BOUNDED_TEXT,
            "maxItems": 32,
        },
        "confidence": _enum(AUTH_CONTRACT_RESPONSE_SCHEMA["confidence"]),
    },
    "required": sorted(AUTH_CONTRACT_RESPONSE_SCHEMA),
    "additionalProperties": False,
}
