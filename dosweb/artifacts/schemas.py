from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError


SCHEMA_VERSION: Final = "2.5"
_CONCRETE_RESOURCE_DIMENSIONS: Final = frozenset(
    {"entries", "bytes", "tasks", "connections", "objects"}
)
_RESOURCE_DIMENSIONS: Final = _CONCRETE_RESOURCE_DIMENSIONS | frozenset({"unknown"})
_RESOURCE_SCOPES: Final = frozenset(
    {"request", "session", "connection", "instance", "global", "unknown"}
)
_GROWTH_KINDS: Final = frozenset(
    {"input_materialization", "direct_allocation", "container_growth", "async_work_growth"}
)
_FLOW_TARGETS: Final = frozenset(
    {"size", "key", "value", "iteration_count", "submission_count"}
)
_ID_PREFIXES: Final = {
    "entry_id": "entry:", "growth_id": "growth:", "growth_contract_id": "contract:",
    "verified_growth_id": "verified_growth:",
    "path_id": "flow:", "guard_id": "guard:", "bound_id": "bound:",
    "release_id": "release:", "lifecycle_result_id": "lifecycle:",
    "finding_id": "finding:", "certificate_id": "certificate:",
    "config_id": "config:", "fact_id": "security:", "auth_contract_id": "auth_contract:",
    "decision_id": "reachability:", "audit_id": "llm_audit:",
    "link_id": "candidate_link:", "disposition_id": "disposition:",
    "evidence_id": "lifecycle-evidence:", "coverage_id": "lifecycle-coverage:", "summary_id": "lifecycle-summary:",
    "gap_id": "gap:", "interposition_id": "interposition:",
}
_MAX_ARTIFACT_ID_BYTES: Final = 256


@dataclass(frozen=True)
class ReferenceSpec:
    id_kind: str
    multiple: bool = False


@dataclass(frozen=True)
class ArtifactSchema:
    id_field: str
    required_fields: frozenset[str]
    enum_fields: Mapping[str, frozenset[str]]
    reference_fields: Mapping[str, ReferenceSpec]
    field_kinds: Mapping[str, str]
    record_validator: Callable[[Mapping[str, object], str, int], None] | None = None


def _field_kinds(**kinds: str) -> dict[str, str]:
    return kinds


_COMMON_GROWTH_FIELD_KINDS: Final = _field_kinds(
    growth_id="string",
    site="object",
    kind="string",
    operation="string",
    resource_point="object",
    demand_inputs="list",
    escape_scope="string",
    candidate_evidence="list",
    coverage_status="string",
    coverage_notes="list",
)


ARTIFACT_SCHEMAS: Final[dict[str, ArtifactSchema]] = {
    "entry_facts": ArtifactSchema(
        id_field="entry_id",
        required_fields=frozenset(
            {
                "entry_id", "framework", "protocol", "handler", "registration",
                "route_or_event", "auth_context", "attacker_inputs", "materialization_phase",
            }
        ),
        enum_fields={
            "framework": frozenset({"spring_mvc", "servlet", "netty", "mqtt", "jax_rs", "grpc"}),
            "protocol": frozenset({"http", "tcp", "mqtt", "grpc"}),
            "auth_context": frozenset(
                {"unauthenticated", "low_privilege", "privileged", "unknown"}
            ),
            "materialization_phase": frozenset(
                {"before_handler", "in_handler", "streaming", "unknown"}
            ),
        },
        reference_fields={},
        field_kinds=_field_kinds(
            entry_id="string", framework="string", protocol="string", handler="object",
            registration="object", route_or_event="string", auth_context="string",
            attacker_inputs="list", materialization_phase="string",
        ),
        record_validator=lambda record, artifact_name, line: _validate_entry(
            record, artifact_name, line
        ),
    ),
    "modeled_configuration": ArtifactSchema(
        id_field="config_id",
        required_fields=frozenset({"config_id", "key", "value", "source_file", "source_line", "profile", "provenance", "default_effective", "status"}),
        enum_fields={"profile": frozenset({"default", "unknown"}), "provenance": frozenset({"cli_override", "config_file", "extracted_default", "unknown"}), "status": frozenset({"known", "unknown"})},
        reference_fields={}, field_kinds=_field_kinds(config_id="string", key="string", value="any", source_file="string_or_empty", source_line="int", profile="string", provenance="string", default_effective="bool", status="string"),
    ),
    "entry_gap_facts": ArtifactSchema(
        id_field="gap_id",
        required_fields=frozenset({"gap_id", "framework", "protocol", "route_or_event", "handler_file", "handler_start_line", "coverage_status", "coverage_note"}),
        enum_fields={
            "framework": frozenset({"spring_mvc", "servlet", "netty", "mqtt", "jax_rs", "grpc"}),
            "protocol": frozenset({"http", "tcp", "mqtt", "grpc"}),
            "coverage_status": frozenset({"partial", "unsupported"}),
        },
        reference_fields={},
        field_kinds=_field_kinds(gap_id="string", framework="string", protocol="string", route_or_event="string", handler_file="string", handler_start_line="int", coverage_status="string", coverage_note="string"),
        record_validator=lambda record, artifact_name, line: _validate_entry_gap(
            record, artifact_name, line
        ),
    ),
    "entry_interposition_facts": ArtifactSchema(
        id_field="interposition_id",
        required_fields=frozenset({"interposition_id", "entry_id", "kind", "interposer", "registration", "url_predicate", "order", "action", "chain_call", "phase", "action_before_chain", "coverage_status", "coverage_note"}),
        enum_fields={
            "kind": frozenset({"filter_registration_bean", "servlet_filter", "once_per_request_filter"}),
            "phase": frozenset({"before_handler", "after_handler", "unknown"}),
            "coverage_status": frozenset({"complete", "partial"}),
        },
        reference_fields={"entry_id": ReferenceSpec("entry_id")},
        field_kinds=_field_kinds(interposition_id="string", entry_id="string", kind="string", interposer="object", registration="object", url_predicate="object", order="object", action="object", chain_call="object", phase="string", action_before_chain="bool", coverage_status="string", coverage_note="string"),
        record_validator=lambda record, artifact_name, line: _validate_entry_interposition(record, artifact_name, line),
    ),
    "entry_security_facts": ArtifactSchema(
        id_field="fact_id", required_fields=frozenset({"fact_id", "entry_id", "kind", "location", "line", "value", "coverage"}),
        enum_fields={"kind": frozenset({"annotation", "filter", "servlet_constraint", "netty_gate", "mqtt_gate", "configuration", "dependency_coverage"}), "coverage": frozenset({"complete", "partial", "unsupported"})},
        reference_fields={"entry_id": ReferenceSpec("entry_id")}, field_kinds=_field_kinds(fact_id="string", entry_id="string", kind="string", location="string", line="int", value="string", coverage="string"),
    ),
    "auth_contracts": ArtifactSchema(
        id_field="auth_contract_id", required_fields=frozenset({"auth_contract_id", "entry_id", "auth_context", "evidence_ids", "assumptions", "confidence"}),
        enum_fields={"auth_context": frozenset({"unauthenticated", "low_privilege", "privileged", "unknown"}), "confidence": frozenset({"high", "medium", "low"})}, reference_fields={"entry_id": ReferenceSpec("entry_id")}, field_kinds=_field_kinds(auth_contract_id="string", entry_id="string", auth_context="string", evidence_ids="list", assumptions="list", confidence="string"),
    ),
    "reachability_decisions": ArtifactSchema(
        id_field="decision_id", required_fields=frozenset({"decision_id", "entry_id", "auth_contract_id", "auth_context", "status", "evidence_ids"}),
        enum_fields={"auth_context": frozenset({"unauthenticated", "low_privilege", "privileged", "unknown"}), "status": frozenset({"ordinary_attacker_reachable", "not_entry_reachable", "unknown"})}, reference_fields={"entry_id": ReferenceSpec("entry_id"), "auth_contract_id": ReferenceSpec("auth_contract_id")}, field_kinds=_field_kinds(decision_id="string", entry_id="string", auth_contract_id="string", auth_context="string", status="string", evidence_ids="list"),
    ),
    "llm_audit": ArtifactSchema(
        id_field="audit_id", required_fields=frozenset({"audit_id", "contract_kind", "request_id", "normalized_prompt", "response_schema", "raw_response", "parsed_response", "settings", "attestation", "cache_hit"}),
        enum_fields={"contract_kind": frozenset({"growth", "auth"})}, reference_fields={}, field_kinds=_field_kinds(audit_id="string", contract_kind="string", request_id="string_or_empty", normalized_prompt="string", response_schema="object", raw_response="string", parsed_response="object", settings="object", attestation="object", cache_hit="bool"),
    ),
    "growth_candidates": ArtifactSchema(
        id_field="growth_id",
        required_fields=frozenset(_COMMON_GROWTH_FIELD_KINDS),
        enum_fields={
            "kind": _GROWTH_KINDS,
            "escape_scope": frozenset({"request", "session", "instance", "global", "unknown"}),
            "coverage_status": frozenset({"complete", "partial"}),
        },
        reference_fields={},
        field_kinds=_COMMON_GROWTH_FIELD_KINDS,
        record_validator=lambda record, artifact_name, line: _validate_growth(
            record, artifact_name, line
        ),
    ),
    "candidate_entry_links": ArtifactSchema(
        id_field="link_id", required_fields=frozenset({"link_id", "growth_id", "entry_id", "status", "evidence_ids", "reason_codes"}),
        enum_fields={"status": frozenset({"complete", "partial"})},
        reference_fields={"growth_id": ReferenceSpec("growth_id"), "entry_id": ReferenceSpec("entry_id")},
        field_kinds=_field_kinds(link_id="string", growth_id="string", entry_id="string", status="string", evidence_ids="list", reason_codes="list"),
    ),
    "candidate_dispositions": ArtifactSchema(
        id_field="disposition_id", required_fields=frozenset({"disposition_id", "growth_id", "status", "link_ids", "reason_codes"}),
        enum_fields={"status": frozenset({"rejected", "verified_relevant", "not_entry_reachable", "unresolved"})},
        reference_fields={"growth_id": ReferenceSpec("growth_id"), "link_ids": ReferenceSpec("link_id", multiple=True)},
        field_kinds=_field_kinds(disposition_id="string", growth_id="string", status="string", link_ids="list", reason_codes="list"),
    ),
    "repeatability_decisions": ArtifactSchema(
        id_field="decision_id", required_fields=frozenset({"decision_id", "entry_id", "growth_id", "status", "evidence_ids", "reason_codes"}),
        enum_fields={"status": frozenset({"proven", "unknown", "not_applicable"})},
        reference_fields={"entry_id": ReferenceSpec("entry_id"), "growth_id": ReferenceSpec("growth_id")},
        field_kinds=_field_kinds(decision_id="string", entry_id="string", growth_id="string", status="string", evidence_ids="list", reason_codes="list"),
    ),
    "amplification_decisions": ArtifactSchema(
        id_field="decision_id", required_fields=frozenset({"decision_id", "entry_id", "growth_id", "status", "evidence_ids", "reason_codes"}),
        enum_fields={"status": frozenset({"proven", "unknown", "not_applicable"})},
        reference_fields={"entry_id": ReferenceSpec("entry_id"), "growth_id": ReferenceSpec("growth_id")},
        field_kinds=_field_kinds(decision_id="string", entry_id="string", growth_id="string", status="string", evidence_ids="list", reason_codes="list"),
    ),
    "growth_contracts": ArtifactSchema(
        id_field="growth_contract_id",
        required_fields=frozenset(
            {
                "growth_contract_id", "growth_id", "is_resource_growth", "growth_kind",
                "resource_dimension", "attacker_influence", "resource_effect",
                "required_static_evidence", "confidence",
            }
        ),
        enum_fields={
            "is_resource_growth": frozenset({"yes", "no", "unknown"}),
            "growth_kind": _GROWTH_KINDS | frozenset({"unknown"}),
            "resource_dimension": _RESOURCE_DIMENSIONS,
            "resource_effect": frozenset({"materializes_bytes", "allocates_objects", "adds_entries", "enqueues_tasks", "opens_connections", "unknown"}),
            "confidence": frozenset({"high", "medium", "low"}),
        },
        reference_fields={"growth_id": ReferenceSpec("growth_id")},
        field_kinds=_field_kinds(
            growth_contract_id="string", growth_id="string", is_resource_growth="string",
            growth_kind="string", resource_dimension="string", attacker_influence="list",
            resource_effect="string", required_static_evidence="list", confidence="string",
        ),
        record_validator=lambda record, artifact_name, line: _validate_growth_contract(record, artifact_name, line),
    ),
    "verified_growth": ArtifactSchema(
        id_field="verified_growth_id",
        required_fields=frozenset(
            {
                "verified_growth_id", "growth_id", "slice_id", "status",
                "reason_codes", "checks",
            }
        ),
        enum_fields={
            "status": frozenset({"verified", "rejected", "unresolved"}),
        },
        reference_fields={"growth_id": ReferenceSpec("growth_id")},
        field_kinds=_field_kinds(
            verified_growth_id="string", growth_id="string", slice_id="string",
            status="string", reason_codes="list", checks="list",
        ),
        record_validator=lambda record, artifact_name, line: _validate_verified_growth(
            record, artifact_name, line
        ),
    ),
    "flow_proofs": ArtifactSchema(
        id_field="path_id",
        required_fields=frozenset(
            {
                "path_id", "entry_id", "growth_id", "attacker_control", "call_path",
                "phase_sequence", "confidence", "flow_kind", "coverage_status", "coverage_note",
            }
        ),
        enum_fields={"confidence": frozenset({"proven", "partial"}), "coverage_status": frozenset({"complete", "partial", "unsupported"})},
        reference_fields={
            "entry_id": ReferenceSpec("entry_id"),
            "growth_id": ReferenceSpec("growth_id"),
        },
        field_kinds=_field_kinds(
            path_id="string", entry_id="string", growth_id="string", attacker_control="object",
            call_path="list", phase_sequence="list", confidence="string", flow_kind="string", coverage_status="string", coverage_note="string",
        ),
        record_validator=lambda record, artifact_name, line: _validate_flow_proof(
            record, artifact_name, line
        ),
    ),
    "guard_candidates": ArtifactSchema(
        id_field="guard_id",
        required_fields=frozenset(
            {
                "guard_id", "site", "kind", "resource_dimension", "scope", "behavior",
                "dominates_growth", "reject_path_reaches_growth", "configuration_key",
                "configuration_value", "representation", "phase", "covers_materialization",
                "authorization_only", "evidence", "coverage_status",
            }
        ),
        enum_fields={
            "kind": frozenset({"request_limit", "input_validation", "rate_limit", "configuration"}),
            "resource_dimension": _RESOURCE_DIMENSIONS,
            "scope": _RESOURCE_SCOPES,
            "behavior": frozenset({"reject", "block", "unknown"}),
            "coverage_status": frozenset({"complete", "partial"}),
        },
        reference_fields={},
        field_kinds=_field_kinds(
            guard_id="string", site="object", kind="string", resource_dimension="string",
            scope="string", behavior="string", dominates_growth="bool",
            reject_path_reaches_growth="bool", configuration_key="string",
            configuration_value="string", representation="string", phase="string",
            covers_materialization="bool", authorization_only="bool", evidence="list",
            coverage_status="string",
        ),
    ),
    "bound_candidates": ArtifactSchema(
        id_field="bound_id",
        required_fields=frozenset(
            {
                "bound_id", "site", "kind", "resource_dimension", "scope", "behavior",
                "receiver", "field_path", "result_checked", "configuration_key",
                "configuration_value", "phase", "covers_flow", "request_encoding",
                "queue_resource", "product_bound", "evidence", "coverage_status",
            }
        ),
        enum_fields={
            "kind": frozenset({"limit", "quota", "capacity", "backpressure", "rate"}),
            "resource_dimension": _RESOURCE_DIMENSIONS,
            "scope": _RESOURCE_SCOPES,
            "behavior": frozenset({"reject", "block", "evict", "unknown"}),
            "coverage_status": frozenset({"complete", "partial"}),
        },
        reference_fields={},
        field_kinds=_field_kinds(
            bound_id="string", site="object", kind="string", resource_dimension="string",
            scope="string", behavior="string", receiver="string", field_path="string",
            result_checked="bool", configuration_key="string", configuration_value="string",
            phase="string", covers_flow="bool", request_encoding="string",
            queue_resource="string", product_bound="bool", evidence="list",
            coverage_status="string",
        ),
    ),
    "release_candidates": ArtifactSchema(
        id_field="release_id",
        required_fields=frozenset(
            {
                "release_id", "site", "kind", "resource_dimension", "scope", "receiver",
                "key_identity", "synchronous", "normal_path", "exceptional_path",
                "actual_reduction", "after_growth", "transfer_only", "async_kind",
                "evidence", "coverage_status",
            }
        ),
        enum_fields={
            "kind": frozenset({"remove", "clear", "evict", "close", "unknown"}),
            "resource_dimension": _RESOURCE_DIMENSIONS,
            "scope": _RESOURCE_SCOPES,
            "coverage_status": frozenset({"complete", "partial"}),
        },
        reference_fields={},
        field_kinds=_field_kinds(
            release_id="string", site="object", kind="string", resource_dimension="string",
            scope="string", receiver="string", key_identity="string", synchronous="bool",
            normal_path="bool", exceptional_path="bool", actual_reduction="bool",
            after_growth="bool", transfer_only="bool", async_kind="string", evidence="list",
            coverage_status="string",
        ),
    ),
    "lifecycle_summaries": ArtifactSchema(
        id_field="summary_id",
        required_fields=frozenset({"summary_id", "entry_id", "growth_id", "path_id", "family", "candidate_file", "candidate_start_line", "callsite_file", "callsite_start_line", "receiver_file", "receiver_start_line", "argument_index", "resource_dimension", "scope", "configuration_key", "configuration_value", "representation", "phase", "covers_materialization", "dominates_growth", "reject_path_reaches_growth", "evidence", "cfg_relation", "coverage_status", "coverage_note"}),
        enum_fields={"family": frozenset({"guard", "bound", "release"}), "cfg_relation": frozenset({"one_wrapper", "partial"}), "coverage_status": frozenset({"complete", "partial", "unsupported"})},
        reference_fields={"entry_id": ReferenceSpec("entry_id"), "growth_id": ReferenceSpec("growth_id"), "path_id": ReferenceSpec("path_id")},
        field_kinds=_field_kinds(summary_id="string", entry_id="string", growth_id="string", path_id="string", family="string", candidate_file="string", candidate_start_line="int", callsite_file="string", callsite_start_line="int", receiver_file="string", receiver_start_line="int", argument_index="int", resource_dimension="string", scope="string", configuration_key="string", configuration_value="string", representation="string", phase="string", covers_materialization="bool", dominates_growth="bool", reject_path_reaches_growth="bool", evidence="string", cfg_relation="string", coverage_status="string", coverage_note="string"),
    ),
    "lifecycle_evidence": ArtifactSchema(
        id_field="evidence_id",
        required_fields=frozenset({"evidence_id", "entry_id", "growth_id", "path_id", "family", "candidate_id", "growth_file", "growth_line", "candidate_file", "candidate_line", "resource_identity", "field_identity", "key_identity", "cfg_relation", "coverage_status"}),
        enum_fields={"family": frozenset({"guard", "bound", "release"}), "cfg_relation": frozenset({"same_cfg", "partial", "ambiguous"}), "coverage_status": frozenset({"complete", "partial", "unsupported"})},
        reference_fields={"entry_id": ReferenceSpec("entry_id"), "growth_id": ReferenceSpec("growth_id"), "path_id": ReferenceSpec("path_id")},
        field_kinds=_field_kinds(evidence_id="string", entry_id="string", growth_id="string", path_id="string", family="string", candidate_id="string", growth_file="string", growth_line="int", candidate_file="string", candidate_line="int", resource_identity="string", field_identity="string", key_identity="string", cfg_relation="string", coverage_status="string"),
    ),
    "lifecycle_coverage": ArtifactSchema(
        id_field="coverage_id",
        required_fields=frozenset({"coverage_id", "entry_id", "growth_id", "path_id", "family", "status", "reason"}),
        enum_fields={"family": frozenset({"guard", "bound", "release"}), "status": frozenset({"complete", "partial", "unsupported"})},
        reference_fields={"entry_id": ReferenceSpec("entry_id"), "growth_id": ReferenceSpec("growth_id"), "path_id": ReferenceSpec("path_id")},
        field_kinds=_field_kinds(coverage_id="string", entry_id="string", growth_id="string", path_id="string", family="string", status="string", reason="string"),
    ),
    "lifecycle_results": ArtifactSchema(
        id_field="lifecycle_result_id",
        required_fields=frozenset(
            {
                "lifecycle_result_id", "entry_id", "growth_id", "path_id", "guard_decision",
                "bound_decision", "release_decision", "reason_codes", "guard", "bound", "release",
            }
        ),
        enum_fields={
            "guard_decision": frozenset({"effective", "ineffective", "absent", "unknown"}),
            "bound_decision": frozenset(
                {"absent", "scope_mismatched", "dimension_mismatched", "possibly_over_budget", "effective", "unknown"}
            ),
            "release_decision": frozenset({"effective", "ineffective", "absent", "unknown"}),
        },
        reference_fields={
            "entry_id": ReferenceSpec("entry_id"),
            "growth_id": ReferenceSpec("growth_id"),
            "path_id": ReferenceSpec("path_id"),
        },
        field_kinds=_field_kinds(
            lifecycle_result_id="string", entry_id="string", growth_id="string", path_id="string",
            guard_decision="string", bound_decision="string", release_decision="string",
            reason_codes="list", guard="object", bound="object", release="object",
        ),
        record_validator=lambda record, artifact_name, line: _validate_lifecycle_result(
            record, artifact_name, line
        ),
    ),
    "static_findings": ArtifactSchema(
        id_field="finding_id",
        required_fields=frozenset(
            {"finding_id", "certificate_id", "entry_id", "growth_id", "verdict", "reason_codes"}
        ),
        enum_fields={
            "verdict": frozenset(
                {"static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown"}
            )
        },
        reference_fields={
            "certificate_id": ReferenceSpec("certificate_id"),
            "entry_id": ReferenceSpec("entry_id"),
            "growth_id": ReferenceSpec("growth_id"),
        },
        field_kinds=_field_kinds(
            finding_id="string", certificate_id="string", entry_id="string", growth_id="string",
            verdict="string", reason_codes="list",
        ),
    ),
    "lifecycle_certificates": ArtifactSchema(
        id_field="certificate_id",
        required_fields=frozenset(
            {
                "certificate_id", "entry_id", "growth_id", "attacker_inputs", "resource_point",
                "path_ids", "guard_decision", "bound_decision", "release_decision", "assertions",
                "verdict", "reason_codes", "assumptions", "coverage_gaps", "unresolved_facts",
                "suggested_follow_up_measurements",
            }
        ),
        enum_fields={
            "verdict": frozenset(
                {"static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown"}
            )
        },
        reference_fields={
            "entry_id": ReferenceSpec("entry_id"),
            "growth_id": ReferenceSpec("growth_id"),
            "path_ids": ReferenceSpec("path_id", multiple=True),
        },
        field_kinds=_field_kinds(
            certificate_id="string", entry_id="string", growth_id="string", attacker_inputs="list",
            resource_point="object", path_ids="nonempty_string_list", guard_decision="object",
            bound_decision="object", release_decision="object", assertions="list", verdict="string",
            reason_codes="list", assumptions="list", coverage_gaps="list", unresolved_facts="list",
            suggested_follow_up_measurements="list",
        ),
    ),
}


def validate_records(artifact_name: str, records: Iterable[Mapping[str, object]]) -> None:
    schema = _schema_for(artifact_name)
    seen_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise _error("ARTIFACT_RECORD_NOT_OBJECT", "Artifact record must be an object.", artifact_name, index)
        actual_fields = set(record)
        missing = schema.required_fields - actual_fields
        extra = actual_fields - schema.required_fields
        if missing or extra:
            field = sorted(extra or missing)[0]
            code = "ARTIFACT_INVALID_RECORD" if extra else "ARTIFACT_REQUIRED_FIELD_MISSING"
            raise _error(code, "Artifact record fields do not exactly match the schema.", artifact_name, index, field)
        for field in schema.required_fields:
            if field not in record:
                raise _error(
                    "ARTIFACT_REQUIRED_FIELD_MISSING", f"Artifact record requires {field}.",
                    artifact_name, index, field,
                )
        identifier = record[schema.id_field]
        prefix = _ID_PREFIXES[schema.id_field]
        if (
            not isinstance(identifier, str) or len(identifier.encode("utf-8")) > _MAX_ARTIFACT_ID_BYTES
            or not identifier.startswith(prefix) or len(identifier) == len(prefix)
            or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for character in identifier[len(prefix):])
            or identifier in seen_ids
        ):
            raise _error("ARTIFACT_INVALID_RECORD", "Artifact identifier is malformed or duplicated.", artifact_name, index, schema.id_field)
        seen_ids.add(identifier)
        for field, kind in schema.field_kinds.items():
            if not _matches_kind(record[field], kind):
                raise _error(
                    "ARTIFACT_INVALID_RECORD", f"Artifact field {field} must be a {kind}.",
                    artifact_name, index, field,
                )
        for field, choices in schema.enum_fields.items():
            value = record[field]
            if not isinstance(value, str) or value not in choices:
                raise _error(
                    "ARTIFACT_INVALID_ENUM", f"Artifact field {field} has an invalid value.",
                    artifact_name, index, field,
                )
        if schema.record_validator is not None:
            schema.record_validator(record, artifact_name, index)


def validate_references(
    artifact_name: str,
    records: Iterable[Mapping[str, object]],
    known_ids: Mapping[str, object],
) -> None:
    materialized = list(records)
    validate_records(artifact_name, materialized)
    schema = _schema_for(artifact_name)
    for index, record in enumerate(materialized, start=1):
        if artifact_name == "auth_contracts":
            known_security = known_ids.get("security_fact_ids")
            entry_security = known_ids.get("entry_security_fact_ids")
            entry_id = record["entry_id"]
            if not isinstance(known_security, (set, frozenset)) or not isinstance(entry_security, Mapping) or not isinstance(entry_security.get(entry_id), (set, frozenset)) or any(not isinstance(value, str) or value not in known_security or value not in entry_security[entry_id] for value in record["evidence_ids"]):
                raise _dangling_reference(artifact_name, index, "evidence_ids", record["evidence_ids"])
        if artifact_name == "growth_contracts":
            known_facts = known_ids.get("fact_id")
            growth_fact_ids = known_ids.get("growth_fact_ids")
            growth_id = record["growth_id"]
            if not isinstance(known_facts, (set, frozenset)) or not isinstance(growth_fact_ids, Mapping):
                raise _dangling_reference(artifact_name, index, "required_static_evidence", record["required_static_evidence"])
            current_facts = growth_fact_ids.get(growth_id)
            if not isinstance(current_facts, (set, frozenset)):
                raise _dangling_reference(artifact_name, index, "required_static_evidence", record["required_static_evidence"])
            influence_ids = [item["evidence_id"] for item in record["attacker_influence"]]
            cited = (*influence_ids, *record["required_static_evidence"])
            if any(item not in known_facts or item not in current_facts for item in cited):
                raise _dangling_reference(artifact_name, index, "required_static_evidence", record["required_static_evidence"])
        for field, spec in schema.reference_fields.items():
            values = _reference_values(record[field], spec, artifact_name, index, field)
            known = known_ids.get(spec.id_kind)
            if not isinstance(known, (set, frozenset)):
                raise _dangling_reference(artifact_name, index, field, record[field])
            if any(value not in known for value in values):
                raise _dangling_reference(artifact_name, index, field, record[field])


def _matches_kind(value: object, kind: str) -> bool:
    if kind == "string":
        return isinstance(value, str) and bool(value)
    if kind == "string_or_empty":
        return isinstance(value, str)
    if kind == "object":
        return isinstance(value, Mapping)
    if kind == "list":
        return isinstance(value, list)
    if kind == "nonempty_string_list":
        return isinstance(value, list) and bool(value) and all(
            isinstance(item, str) and bool(item) for item in value
        )
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "any":
        return value is None or isinstance(value, (str, int, bool)) and not isinstance(value, float)
    raise RuntimeError(f"Unknown field kind: {kind}")


def _validate_entry_gap(record: Mapping[str, object], artifact_name: str, line: int) -> None:
    handler_file = record["handler_file"]
    handler_start_line = record["handler_start_line"]
    coverage_note = record["coverage_note"]
    route_or_event = record["route_or_event"]
    assert isinstance(handler_file, str) and isinstance(handler_start_line, int)
    assert isinstance(coverage_note, str) and isinstance(route_or_event, str)
    path = PurePosixPath(handler_file)
    if (
        handler_start_line <= 0
        or path.is_absolute()
        or "\\" in handler_file
        or any(part in {"", ".", ".."} for part in path.parts)
        or len(handler_file.encode("utf-8")) > 4096
        or len(route_or_event.encode("utf-8")) > 4096
        or len(coverage_note.encode("utf-8")) > 1024
    ):
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Entry gap record is not safely source-backed.",
            artifact_name, line, "handler_file",
        )


def _validate_source_location(value: object, artifact_name: str, line: int, field: str, *, callable_required: bool) -> None:
    if not isinstance(value, Mapping):
        raise _error("ARTIFACT_INVALID_RECORD", "Interposition location is invalid.", artifact_name, line, field)
    required = {"file", "start_line"} | ({"callable"} if callable_required else set())
    if set(value) != required:
        raise _error("ARTIFACT_INVALID_RECORD", "Interposition location fields are not exact.", artifact_name, line, field)
    file_name, start = value.get("file"), value.get("start_line")
    if not isinstance(file_name, str) or not file_name.endswith(".java") or not _safe_relative_java_path(file_name) or not _matches_nested_kind(start, "positive_int"):
        raise _error("ARTIFACT_INVALID_RECORD", "Interposition location must be source-backed.", artifact_name, line, field)
    if callable_required and not isinstance(value.get("callable"), str):
        raise _error("ARTIFACT_INVALID_RECORD", "Interposition callable is invalid.", artifact_name, line, field)


def _safe_relative_java_path(value: str) -> bool:
    path = PurePosixPath(value)
    return not path.is_absolute() and "\\" not in value and all(part not in {"", ".", ".."} for part in path.parts)


def _validate_entry_interposition(record: Mapping[str, object], artifact_name: str, line: int) -> None:
    for field in ("interposer", "action"):
        _validate_source_location(record[field], artifact_name, line, field, callable_required=True)
    registration = record["registration"]
    if not isinstance(registration, Mapping) or set(registration) != {"kind", "callable", "file", "start_line"} or registration.get("kind") not in {"filter_registration_bean", "servlet_filter", "once_per_request_filter"}:
        raise _error("ARTIFACT_INVALID_RECORD", "Interposition registration is invalid.", artifact_name, line, "registration")
    _validate_source_location({"callable": registration.get("callable"), "file": registration.get("file"), "start_line": registration.get("start_line")}, artifact_name, line, "registration", callable_required=True)
    _validate_source_location(record["chain_call"], artifact_name, line, "chain_call", callable_required=False)
    url, order = record["url_predicate"], record["order"]
    if not isinstance(url, Mapping) or set(url) != {"kind", "value"} or url.get("kind") not in {"exact", "prefix", "servlet_pattern", "regex", "unknown"} or not isinstance(url.get("value"), str) or not url["value"]:
        raise _error("ARTIFACT_INVALID_RECORD", "Interposition URL predicate is invalid.", artifact_name, line, "url_predicate")
    if not isinstance(order, Mapping) or set(order) != {"status", "value"} or order.get("status") not in {"known", "unknown"} or not isinstance(order.get("value"), str):
        raise _error("ARTIFACT_INVALID_RECORD", "Interposition order is invalid.", artifact_name, line, "order")
    if record["coverage_status"] == "complete" and not (record["phase"] == "before_handler" and record["action_before_chain"]):
        raise _error("ARTIFACT_INVALID_RECORD", "Complete interposition requires a proven pre-handler action.", artifact_name, line, "coverage_status")


def _validate_entry(record: Mapping[str, object], artifact_name: str, line: int) -> None:
    handler = record["handler"]
    registration = record["registration"]
    assert isinstance(handler, Mapping) and isinstance(registration, Mapping)
    nested_specs = {
        "handler": (handler, {"callable": "string", "file": "string", "start_line": "positive_int"}),
        "registration": (
            registration,
            {"kind": "string", "callable": "string", "file": "string", "start_line": "positive_int"},
        ),
    }
    for nested_name, (nested, fields) in nested_specs.items():
        if set(nested) != set(fields):
            raise _error(
                "ARTIFACT_INVALID_RECORD", f"Entry {nested_name} fields are not exact.",
                artifact_name, line, nested_name,
            )
        for field, kind in fields.items():
            if not _matches_nested_kind(nested[field], kind):
                raise _error(
                    "ARTIFACT_INVALID_RECORD", f"Entry {nested_name} requires {field}.",
                    artifact_name, line, nested_name,
                )
    registration_kind = registration["kind"]
    allowed_registration_kinds = {
        "spring_mvc": {"annotation_mapping", "static_registration"},
        "servlet": {"annotation_mapping", "static_registration"},
        "netty": {"pipeline_registration"},
        "mqtt": {"subscription_registration", "broker_registration"},
        "jax_rs": {"annotation_mapping", "static_registration"},
        "grpc": {"static_registration"},
    }
    if registration_kind not in allowed_registration_kinds[record["framework"]]:
        raise _error(
            "ARTIFACT_INVALID_ENUM", "Entry registration kind is invalid for its framework.",
            artifact_name, line, "registration",
        )


def _validate_growth(record: Mapping[str, object], artifact_name: str, line: int) -> None:
    resource_point = record["resource_point"]
    site = record["site"]
    demands = record["demand_inputs"]
    evidence = record["candidate_evidence"]
    coverage_notes = record["coverage_notes"]
    assert isinstance(resource_point, Mapping) and isinstance(site, Mapping)
    assert isinstance(demands, list) and isinstance(evidence, list)
    assert isinstance(coverage_notes, list)
    if "dimension" not in resource_point:
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Growth resource_point requires dimension.",
            artifact_name, line, "resource_point",
        )
    dimension = resource_point.get("dimension")
    if not isinstance(dimension, str) or dimension not in _CONCRETE_RESOURCE_DIMENSIONS:
        raise _error(
            "ARTIFACT_INVALID_ENUM", "Growth resource_point dimension has an invalid value.",
            artifact_name, line, "resource_point",
        )
    if (
        set(site) != {"file", "start_line"}
        or not _matches_kind(site.get("file"), "string")
        or not _matches_nested_kind(site.get("start_line"), "positive_int")
        or not demands
        or len(demands) > 64
        or not evidence
        or len(evidence) > 64
    ):
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Growth site, demand inputs, or evidence are malformed.",
            artifact_name, line,
        )
    for demand in demands:
        if (
            not isinstance(demand, Mapping)
            or set(demand) != {"name", "role"}
            or not _matches_kind(demand.get("name"), "string")
            or demand.get("role") not in (_FLOW_TARGETS | {"unknown"})
        ):
            raise _error(
                "ARTIFACT_INVALID_RECORD", "Growth demand input is malformed.",
                artifact_name, line, "demand_inputs",
            )
    if not all(_valid_fact_id(item) for item in evidence):
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Growth candidate evidence is malformed.",
            artifact_name, line, "candidate_evidence",
        )
    if not coverage_notes or len(coverage_notes) > 64 or not all(
        isinstance(item, str)
        and bool(item)
        and len(item.encode("utf-8")) <= 65536
        for item in coverage_notes
    ):
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Growth coverage notes are malformed.",
            artifact_name, line, "coverage_notes",
        )
    if set(resource_point) != {"resource_id", "dimension", "receiver", "field_path"}:
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Growth resource_point fields are not exact.",
            artifact_name, line, "resource_point",
        )
    for field in ("resource_id", "receiver", "field_path"):
        if field not in resource_point or not _matches_kind(resource_point[field], "string"):
            raise _error(
                "ARTIFACT_INVALID_RECORD", f"Growth resource_point requires {field}.",
                artifact_name, line, "resource_point",
            )
    resource_id = resource_point.get("resource_id")
    expected_resource_id = stable_identifier(
        "resource",
        {
            "dimension": dimension,
            "receiver": resource_point["receiver"],
            "field_path": resource_point["field_path"],
        },
    )
    if resource_id != expected_resource_id:
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Growth resource identifier is malformed.",
            artifact_name, line, "resource_point",
        )


def _validate_verified_growth(record: Mapping[str, object], artifact_name: str, line: int) -> None:
    reasons = record["reason_codes"]
    checks = record["checks"]
    status = record["status"]
    assert isinstance(reasons, list) and isinstance(checks, list) and isinstance(status, str)
    if len(reasons) > 32 or len(checks) > 32 or not all(
        isinstance(reason, str) and bool(reason) and len(reason.encode("utf-8")) <= 128
        for reason in reasons
    ):
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Verified Growth audit collections are malformed.",
            artifact_name, line,
        )
    if (status == "verified" and (reasons or not checks)) or (status != "verified" and not reasons):
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Verified Growth status and reasons are inconsistent.",
            artifact_name, line, "reason_codes",
        )
    for check in checks:
        if (
            not isinstance(check, Mapping)
            or set(check) != {"name", "passed", "reason_code"}
            or not isinstance(check.get("name"), str)
            or not check.get("name")
            or not isinstance(check.get("passed"), bool)
            or (check.get("reason_code") is not None and not isinstance(check.get("reason_code"), str))
            or (status == "verified" and check.get("passed") is not True)
        ):
            raise _error(
                "ARTIFACT_INVALID_RECORD", "Verified Growth check is malformed.",
                artifact_name, line, "checks",
            )


def _validate_growth_contract(record: Mapping[str, object], artifact_name: str, line: int) -> None:
    influences = record["attacker_influence"]
    required = record["required_static_evidence"]
    assert isinstance(influences, list) and isinstance(required, list)
    if len(influences) > 16 or len(required) > 32:
        raise _error("ARTIFACT_INVALID_RECORD", "Growth Contract collections exceed their bounds.", artifact_name, line)
    for influence in influences:
        if not isinstance(influence, Mapping) or set(influence) != {"target", "evidence_id"} or influence.get("target") not in (_FLOW_TARGETS | {"unknown"}) or not _valid_fact_id(influence.get("evidence_id")):
            raise _error("ARTIFACT_INVALID_RECORD", "Growth Contract attacker influence is malformed.", artifact_name, line, "attacker_influence")
    if not all(_valid_fact_id(item) for item in required):
        raise _error("ARTIFACT_INVALID_RECORD", "Growth Contract evidence references are malformed.", artifact_name, line, "required_static_evidence")


def _valid_fact_id(value: object) -> bool:
    return isinstance(value, str) and len(value.encode("utf-8")) <= 256 and value.startswith("fact:") and len(value) > 5 and all(character in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for character in value[5:])


def _validate_flow_proof(record: Mapping[str, object], artifact_name: str, line: int) -> None:
    value = record["attacker_control"]
    call_path = record["call_path"]
    phases = record["phase_sequence"]
    assert isinstance(value, Mapping) and isinstance(call_path, list) and isinstance(phases, list)
    if set(value) != {"target", "source", "sink"}:
        raise _error("ARTIFACT_INVALID_RECORD", "Flow attacker_control fields are not exact.", artifact_name, line, "attacker_control")
    for field in ("target", "source", "sink"):
        if field not in value or not _matches_kind(value[field], "string") or "\x00" in value[field] or len(value[field].encode("utf-8")) > 65536:
            raise _error(
                "ARTIFACT_INVALID_RECORD", f"Flow attacker_control requires {field}.",
                artifact_name, line, "attacker_control",
            )
    if value["target"] not in _FLOW_TARGETS:
        raise _error(
            "ARTIFACT_INVALID_ENUM", "Flow attacker_control target has an invalid value.",
            artifact_name, line, "attacker_control",
        )
    if not call_path or not phases or len(call_path) > 64 or len(phases) > 64 or not all(
        isinstance(item, str) and bool(item) and "\x00" not in item and len(item.encode("utf-8")) <= 65536
        for item in (*call_path, *phases)
    ):
        raise _error("ARTIFACT_INVALID_RECORD", "Flow paths or phases are malformed.", artifact_name, line)
    expected = stable_identifier(
        "flow",
        {
            "entry_id": record["entry_id"],
            "growth_id": record["growth_id"],
            "attacker_control": dict(value),
            "call_path": call_path,
            "phase_sequence": phases,
            "confidence": record["confidence"],
        },
    )
    if record["path_id"] != expected:
        raise _error("ARTIFACT_INVALID_RECORD", "Flow proof identifier is malformed.", artifact_name, line, "path_id")


def _validate_lifecycle_result(
    record: Mapping[str, object], artifact_name: str, line: int
) -> None:
    decision_specs = {
        "guard": frozenset({"effective", "ineffective", "absent", "unknown"}),
        "bound": frozenset(
            {
                "absent", "scope_mismatched", "dimension_mismatched",
                "possibly_over_budget", "effective", "unknown",
            }
        ),
        "release": frozenset({"effective", "ineffective", "absent", "unknown"}),
    }
    for name, statuses in decision_specs.items():
        decision = record[name]
        assert isinstance(decision, Mapping)
        required = {
            "status", "reason_codes", "checks", "evidence_ids",
            "unresolved_facts", "candidate_ids",
        }
        if name == "release":
            required.add("classification")
        if set(decision) != required or decision.get("status") not in statuses:
            raise _error(
                "ARTIFACT_INVALID_RECORD", "Lifecycle decision is malformed.",
                artifact_name, line, name,
            )
        if decision["status"] != record[f"{name}_decision"]:
            raise _error(
                "ARTIFACT_INVALID_RECORD", "Lifecycle decision summary is inconsistent.",
                artifact_name, line, name,
            )
        for field in ("reason_codes", "evidence_ids", "unresolved_facts", "candidate_ids"):
            values = decision[field]
            if not isinstance(values, list) or len(values) > 256 or not all(
                isinstance(value, str) and bool(value) and len(value.encode("utf-8")) <= 65536
                for value in values
            ):
                raise _error(
                    "ARTIFACT_INVALID_RECORD", "Lifecycle decision collection is malformed.",
                    artifact_name, line, name,
                )
        checks = decision["checks"]
        if not isinstance(checks, list) or len(checks) > 256:
            raise _error(
                "ARTIFACT_INVALID_RECORD", "Lifecycle decision checks are malformed.",
                artifact_name, line, name,
            )
        for check in checks:
            if (
                not isinstance(check, Mapping)
                or set(check) != {"name", "passed", "reason_code", "evidence_ids"}
                or not _matches_kind(check.get("name"), "string")
                or not isinstance(check.get("passed"), bool)
                or (
                    check.get("reason_code") is not None
                    and not _matches_kind(check.get("reason_code"), "string")
                )
                or not isinstance(check.get("evidence_ids"), list)
                or not all(
                    isinstance(value, str) and bool(value)
                    for value in check["evidence_ids"]
                )
            ):
                raise _error(
                    "ARTIFACT_INVALID_RECORD", "Lifecycle decision check is malformed.",
                    artifact_name, line, name,
                )
        if name == "release" and decision.get("classification") not in {
            "synchronous_effective", "insufficient_path_coverage",
            "receiver_or_key_mismatched", "potential_async", "not_effective",
            "unknown", "absent",
        }:
            raise _error(
                "ARTIFACT_INVALID_ENUM", "Release classification is invalid.",
                artifact_name, line, name,
            )
    reasons = record["reason_codes"]
    assert isinstance(reasons, list)
    expected_reasons = sorted(
        {
            reason
            for name in decision_specs
            for reason in record[name]["reason_codes"]
        }
    )
    if reasons != expected_reasons:
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Lifecycle result reasons are inconsistent.",
            artifact_name, line, "reason_codes",
        )
    semantic = {key: value for key, value in record.items() if key != "lifecycle_result_id"}
    if record["lifecycle_result_id"] != stable_identifier("lifecycle", semantic):
        raise _error(
            "ARTIFACT_INVALID_RECORD", "Lifecycle result identifier is malformed.",
            artifact_name, line, "lifecycle_result_id",
        )


def _matches_nested_kind(value: object, kind: str) -> bool:
    if kind == "positive_int":
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    return _matches_kind(value, kind)


def _reference_values(
    value: object,
    spec: ReferenceSpec,
    artifact_name: str,
    line: int,
    field: str,
) -> list[str]:
    if spec.multiple:
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and bool(item) for item in value
        ):
            raise _error(
                "ARTIFACT_INVALID_RECORD", f"Artifact reference {field} must be a non-empty list of strings.",
                artifact_name, line, field,
            )
        return value
    if not isinstance(value, str) or not value:
        raise _error(
            "ARTIFACT_INVALID_RECORD", f"Artifact reference {field} must be a non-empty string.",
            artifact_name, line, field,
        )
    return [value]


def _dangling_reference(
    artifact_name: str, line: int, field: str, value: object
) -> AnalyzerError:
    return AnalyzerError(
        "ANALYSIS_DANGLING_FACT_REFERENCE",
        "Artifact record references an absent upstream fact.",
        {"artifact_name": artifact_name, "line": line, "field": field, "value": value},
    )


def _schema_for(artifact_name: str) -> ArtifactSchema:
    try:
        return ARTIFACT_SCHEMAS[artifact_name]
    except KeyError as exc:
        raise AnalyzerError("ARTIFACT_UNKNOWN_SCHEMA", f"Unknown artifact schema: {artifact_name}.") from exc


def _error(
    code: str,
    message: str,
    artifact_name: str,
    line: int,
    field: str | None = None,
) -> AnalyzerError:
    details: dict[str, object] = {"artifact_name": artifact_name, "line": line}
    if field is not None:
        details["field"] = field
    return AnalyzerError(code, message, details)
