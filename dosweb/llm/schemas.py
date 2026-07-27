PROMPT_VERSION = "growth-contract-v1"
RESPONSE_SCHEMA_VERSION = "growth-contract-schema-v1"

GROWTH_CONTRACT_RESPONSE_SCHEMA = {
    "is_resource_growth": ["yes", "no", "unknown"],
    "growth_kind": ["input_materialization", "direct_allocation", "container_growth", "async_work_growth", "unknown"],
    "resource_dimension": ["entries", "bytes", "tasks", "connections", "objects", "unknown"],
    "attacker_influence": [{"target": ["size", "key", "value", "iteration_count", "submission_count", "unknown"], "evidence_id": "fact:<ordinal>"}],
    "resource_effect": ["materializes_bytes", "allocates_objects", "adds_entries", "enqueues_tasks", "opens_connections", "unknown"],
    "required_static_evidence": ["fact:<ordinal>"],
    "confidence": ["high", "medium", "low"],
}
