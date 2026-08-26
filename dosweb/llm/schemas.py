# Bumped after audit artifacts became part of formal reproducibility.
PROMPT_VERSION = "growth-contract-v3"
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
    "required_static_evidence": ["fact:<ordinal>"],
    "confidence": ["high", "medium", "low"],
}
