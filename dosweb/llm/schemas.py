# Bumped after audit artifacts became part of formal reproducibility.
PROMPT_VERSION = "growth-contract-v4"
RESPONSE_SCHEMA_VERSION = "growth-contract-schema-v4"
AUTH_PROMPT_VERSION = "auth-contract-v3"
AUTH_RESPONSE_SCHEMA_VERSION = "auth-contract-schema-v2"

AUTH_CONTRACT_RESPONSE_SCHEMA = {
    "auth_context": ["unauthenticated", "low_privilege", "privileged", "unknown"],
    "evidence_ids": ["security:<ordinal>"],
    "assumptions": ["bounded text"],
    "confidence": ["high", "medium", "low"],
}

GROWTH_CONTRACT_RESPONSE_SCHEMA = {
    "is_resource_growth": ["yes", "no", "unknown"],
    "growth_kind": ["input_materialization", "direct_allocation", "container_growth", "async_work_growth", "unknown"],
    "resource_dimension": ["entries", "bytes", "tasks", "connections", "objects", "unknown"],
    "attacker_influence": [{"target": ["size", "key", "value", "iteration_count", "submission_count", "unknown"], "evidence_id": "fact:<ordinal>"}],
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
