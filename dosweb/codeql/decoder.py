from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

from dosweb.errors import AnalyzerError

ENTRY_COLUMNS: Final = (
    "framework", "protocol", "handler_fqn", "handler_file",
    "handler_start_line", "registration_kind", "registration_fqn",
    "registration_file", "registration_start_line", "route_or_event",
    "auth_context", "attacker_input_name", "attacker_input_type",
    "attacker_input_kind", "materialization_phase", "coverage_status",
    "coverage_note",
)
GROWTH_COLUMNS: Final = (
    "site_file", "site_start_line", "growth_kind", "operation",
    "resource_dimension", "receiver", "field_path", "demand_input_name",
    "demand_input_role", "escape_scope", "candidate_evidence",
    "coverage_status", "coverage_note",
)
INTERPOSITION_COLUMNS: Final = (
    "entry_file", "entry_start_line", "interposer_fqn", "interposer_file",
    "interposer_start_line", "registration_kind", "registration_fqn", "registration_file",
    "registration_start_line", "url_predicate_kind", "url_predicate_value", "order_status",
    "order_value", "action_fqn", "action_file", "action_start_line", "chain_file",
    "chain_start_line", "phase", "action_before_chain", "coverage_status", "coverage_note",
)
SECURITY_COLUMNS: Final = (
    "handler_fqn", "handler_file", "handler_start_line", "route_or_event",
    "fact_file", "fact_start_line", "kind", "value", "coverage_status",
    "coverage_note",
)
FLOW_COLUMNS: Final = (
    "source_file", "source_start_line", "sink_file", "sink_start_line",
    "attacker_target", "attacker_source", "attacker_sink", "call_path",
    "phase_sequence", "flow_kind", "confidence", "coverage_status",
    "coverage_note",
)
GUARD_COLUMNS: Final = (
    "anchor_file", "anchor_start_line", "site_file", "site_start_line", "guard_kind", "resource_dimension",
    "scope", "behavior", "dominates_growth", "reject_path_reaches_growth",
    "configuration_key", "configuration_value", "representation", "phase",
    "covers_materialization", "authorization_only", "evidence",
    "coverage_status", "coverage_note",
)
BOUND_COLUMNS: Final = (
    "anchor_file", "anchor_start_line", "site_file", "site_start_line", "bound_kind", "resource_dimension",
    "scope", "behavior", "receiver", "field_path", "result_checked",
    "configuration_key", "configuration_value", "phase", "covers_flow",
    "request_encoding", "queue_resource", "product_bound", "evidence",
    "coverage_status", "coverage_note",
)
RELEASE_COLUMNS: Final = (
    "anchor_file", "anchor_start_line", "site_file", "site_start_line", "release_kind", "resource_dimension",
    "scope", "receiver", "key_identity", "synchronous", "normal_path",
    "exceptional_path", "actual_reduction", "after_growth", "transfer_only",
    "async_kind", "evidence", "coverage_status", "coverage_note",
)
LIFECYCLE_COVERAGE_COLUMNS: Final = (
    "anchor_file", "anchor_start_line", "family", "coverage_status", "coverage_note",
)
LIFECYCLE_SUMMARY_COLUMNS: Final = (
    "anchor_file", "anchor_start_line", "family", "candidate_file", "candidate_start_line",
    "callsite_file", "callsite_start_line", "receiver_file", "receiver_start_line",
    "argument_index", "resource_dimension", "scope", "configuration_key", "configuration_value",
    "representation", "phase", "covers_materialization", "dominates_growth",
    "reject_path_reaches_growth", "evidence", "cfg_relation", "coverage_status", "coverage_note",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ROWS: Final = 4096
_MAX_STRING_BYTES: Final = 65536
_MAX_TOTAL_STRING_BYTES: Final = 16 * 1024 * 1024
_MAX_LINE_NUMBER: Final = 2**31 - 1


@dataclass(frozen=True)
class DecodeSource:
    source_root: Path
    query_sha256: str


@dataclass(frozen=True)
class QuerySpec:
    name: str
    result_set: str
    columns: tuple[str, ...]
    field_types: Mapping[str, str]
    enum_fields: Mapping[str, frozenset[str]]
    path_fields: frozenset[str]
    line_fields: frozenset[str]


def _types(columns: tuple[str, ...], *, integers: set[str] = set(), booleans: set[str] = set()) -> Mapping[str, str]:
    values = {
        column: "integer" if column in integers else "boolean" if column in booleans else "string"
        for column in columns
    }
    return MappingProxyType(values)


def _spec(
    name: str,
    columns: tuple[str, ...],
    *,
    integers: set[str] = set(),
    booleans: set[str] = set(),
    enums: Mapping[str, frozenset[str]] | None = None,
    paths: frozenset[str] = frozenset(),
    lines: frozenset[str] = frozenset(),
) -> QuerySpec:
    return QuerySpec(
        name=name,
        result_set="#select",
        columns=columns,
        field_types=_types(columns, integers=integers, booleans=booleans),
        enum_fields=MappingProxyType(dict(enums or {})),
        path_fields=paths,
        line_fields=lines,
    )


_COVERAGE = frozenset({"complete", "partial", "unsupported"})
_RESOURCE_DIMENSIONS = frozenset({"entries", "bytes", "tasks", "connections", "objects", "unknown"})
_SCOPES = frozenset({"request", "session", "connection", "instance", "global", "unknown"})

QUERY_SPECS: Final[Mapping[str, QuerySpec]] = MappingProxyType(
    {
        "entries": _spec(
            "entries", ENTRY_COLUMNS,
            integers={"handler_start_line", "registration_start_line"},
            enums={
                "framework": frozenset({"spring_mvc", "servlet", "netty", "mqtt", "jax_rs", "grpc"}),
                "protocol": frozenset({"http", "tcp", "mqtt", "grpc"}),
                "registration_kind": frozenset({"annotation_mapping", "static_registration", "pipeline_registration", "subscription_registration", "broker_registration", "dynamic_unresolved"}),
                "auth_context": frozenset({"unauthenticated", "low_privilege", "privileged", "unknown"}),
                "attacker_input_kind": frozenset({"request_body", "request_parameter", "path_parameter", "header", "model_attribute", "message_payload", "stream", "unknown"}),
                "materialization_phase": frozenset({"before_handler", "in_handler", "streaming", "unknown"}),
                "coverage_status": _COVERAGE,
            },
            paths=frozenset({"handler_file", "registration_file"}),
            lines=frozenset({"handler_start_line", "registration_start_line"}),
        ),
        "growth": _spec(
            "growth", GROWTH_COLUMNS,
            integers={"site_start_line"},
            enums={
                "growth_kind": frozenset({"input_materialization", "direct_allocation", "container_growth", "async_work_growth"}),
                "resource_dimension": _RESOURCE_DIMENSIONS,
                "demand_input_role": frozenset({"size", "key", "value", "iteration_count", "submission_count", "unknown"}),
                "escape_scope": frozenset({"request", "session", "instance", "global", "unknown"}),
                "coverage_status": _COVERAGE,
            },
            paths=frozenset({"site_file"}), lines=frozenset({"site_start_line"}),
        ),
        "entry_interposition": _spec(
            "entry_interposition", INTERPOSITION_COLUMNS,
            integers={"entry_start_line", "interposer_start_line", "registration_start_line", "action_start_line", "chain_start_line"},
            booleans={"action_before_chain"},
            enums={
                "registration_kind": frozenset({"filter_registration_bean", "servlet_filter", "once_per_request_filter"}),
                "url_predicate_kind": frozenset({"exact", "prefix", "servlet_pattern", "regex", "unknown"}),
                "order_status": frozenset({"known", "unknown"}),
                "phase": frozenset({"before_handler", "after_handler", "unknown"}),
                "coverage_status": frozenset({"complete", "partial"}),
            },
            paths=frozenset({"entry_file", "interposer_file", "registration_file", "action_file", "chain_file"}),
            lines=frozenset({"entry_start_line", "interposer_start_line", "registration_start_line", "action_start_line", "chain_start_line"}),
        ),
        "entry_security": _spec(
            "entry_security", SECURITY_COLUMNS,
            integers={"handler_start_line", "fact_start_line"},
            enums={
                "kind": frozenset({
                    "annotation", "filter", "security_filter_chain",
                    "servlet_constraint", "netty_gate", "mqtt_gate",
                    "configuration", "deployment_gate", "dependency_coverage",
                }),
                "coverage_status": frozenset({"complete", "partial"}),
            },
            paths=frozenset({"handler_file", "fact_file"}),
            lines=frozenset({"handler_start_line", "fact_start_line"}),
        ),
        "flow": _spec(
            "flow", FLOW_COLUMNS,
            integers={"source_start_line", "sink_start_line"},
            enums={
                "attacker_target": frozenset({"size", "key", "value", "iteration_count", "submission_count"}),
                "confidence": frozenset({"proven", "partial"}),
                "coverage_status": _COVERAGE,
            },
            paths=frozenset({"source_file", "sink_file"}),
            lines=frozenset({"source_start_line", "sink_start_line"}),
        ),
        "guard": _spec(
            "guard", GUARD_COLUMNS,
            integers={"anchor_start_line", "site_start_line"}, booleans={"dominates_growth", "reject_path_reaches_growth", "covers_materialization", "authorization_only"},
            enums={
                "guard_kind": frozenset({"request_limit", "input_validation", "rate_limit", "configuration"}),
                "resource_dimension": _RESOURCE_DIMENSIONS, "scope": _SCOPES,
                "behavior": frozenset({"reject", "block", "unknown"}), "coverage_status": _COVERAGE,
            },
            paths=frozenset({"anchor_file", "site_file"}), lines=frozenset({"anchor_start_line", "site_start_line"}),
        ),
        "bound": _spec(
            "bound", BOUND_COLUMNS,
            integers={"anchor_start_line", "site_start_line"}, booleans={"result_checked", "covers_flow", "product_bound"},
            enums={
                "bound_kind": frozenset({"limit", "quota", "capacity", "backpressure", "rate"}),
                "resource_dimension": _RESOURCE_DIMENSIONS, "scope": _SCOPES,
                "behavior": frozenset({"reject", "block", "evict", "unknown"}), "coverage_status": _COVERAGE,
            },
            paths=frozenset({"anchor_file", "site_file"}), lines=frozenset({"anchor_start_line", "site_start_line"}),
        ),
        "lifecycle_coverage": _spec(
            "lifecycle_coverage", LIFECYCLE_COVERAGE_COLUMNS,
            integers={"anchor_start_line"},
            enums={"family": frozenset({"guard", "bound", "release"}), "coverage_status": _COVERAGE},
            paths=frozenset({"anchor_file"}), lines=frozenset({"anchor_start_line"}),
        ),
        "lifecycle_summary": _spec(
            "lifecycle_summary", LIFECYCLE_SUMMARY_COLUMNS,
            integers={"anchor_start_line", "candidate_start_line", "callsite_start_line", "receiver_start_line", "argument_index"}, booleans={"covers_materialization", "dominates_growth", "reject_path_reaches_growth"},
            enums={"family": frozenset({"guard", "bound", "release"}), "cfg_relation": frozenset({"one_wrapper", "partial"}), "coverage_status": _COVERAGE},
            paths=frozenset({"anchor_file", "candidate_file", "callsite_file", "receiver_file"}),
            lines=frozenset({"anchor_start_line", "candidate_start_line", "callsite_start_line", "receiver_start_line"}),
        ),
        "release": _spec(
            "release", RELEASE_COLUMNS,
            integers={"anchor_start_line", "site_start_line"},
            booleans={"synchronous", "normal_path", "exceptional_path", "actual_reduction", "after_growth", "transfer_only"},
            enums={
                "release_kind": frozenset({"remove", "clear", "evict", "close", "unknown"}),
                "resource_dimension": _RESOURCE_DIMENSIONS, "scope": _SCOPES,
                "coverage_status": _COVERAGE,
            },
            paths=frozenset({"anchor_file", "site_file"}), lines=frozenset({"anchor_start_line", "site_start_line"}),
        ),
    }
)


def _invalid(reason: str, query_name: str, **details: object) -> AnalyzerError:
    bounded: dict[str, object] = {"reason": reason, "query_name": query_name[:128]}
    for key, value in details.items():
        if isinstance(value, str):
            bounded[key] = value[:256]
        elif isinstance(value, (int, bool)) or value is None:
            bounded[key] = value
    return AnalyzerError(
        "CODEQL_RESULT_INVALID",
        "Decoded CodeQL result violates its query contract.",
        bounded,
    )


def _normalized_source(source: DecodeSource, query_name: str) -> DecodeSource:
    if (
        not isinstance(source, DecodeSource)
        or not isinstance(source.source_root, Path)
        or not isinstance(source.query_sha256, str)
        or not _SHA256.fullmatch(source.query_sha256)
    ):
        raise _invalid("SOURCE_CONTEXT_INVALID", query_name)
    try:
        root = source.source_root.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _invalid("SOURCE_CONTEXT_INVALID", query_name) from exc
    if not root.is_absolute():
        raise _invalid("SOURCE_CONTEXT_INVALID", query_name)
    return DecodeSource(root, source.query_sha256)


def _normalize_path(value: str, source_root: Path, query_name: str, column: str, row: int) -> str:
    if not value or "\x00" in value:
        raise _invalid("PATH_INVALID", query_name, column=column, row=row)
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = source_root / candidate
    try:
        resolved = candidate.resolve(strict=False)
        relative = resolved.relative_to(source_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _invalid("PATH_OUTSIDE_SOURCE_ROOT", query_name, column=column, row=row) from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise _invalid("PATH_INVALID", query_name, column=column, row=row)
    return relative.as_posix()


def _validate_type(kind: str, value: object) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return False


def decode_rows(
    query_name: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    source: DecodeSource,
) -> list[dict[str, object]]:
    if not isinstance(query_name, str) or len(query_name) > 128:
        raise _invalid("UNKNOWN_QUERY", "invalid")
    spec = QUERY_SPECS.get(query_name)
    if spec is None:
        raise _invalid("UNKNOWN_QUERY", query_name)
    if not isinstance(columns, (list, tuple)) or tuple(columns) != spec.columns:
        raise _invalid("COLUMN_MISMATCH", query_name)
    if not isinstance(rows, (list, tuple)) or len(rows) > _MAX_ROWS:
        raise _invalid("ROWS_INVALID", query_name)
    normalized_source = _normalized_source(source, query_name)
    decoded: list[dict[str, object]] = []
    total_string_bytes = 0
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, (list, tuple)) or len(row) != len(spec.columns):
            raise _invalid("ROW_ARITY", query_name, row=row_number)
        fact: dict[str, object] = {}
        for column, value in zip(spec.columns, row):
            if not _validate_type(spec.field_types[column], value):
                raise _invalid("FIELD_TYPE", query_name, row=row_number, column=column)
            if isinstance(value, str):
                try:
                    encoded_size = len(value.encode("utf-8"))
                except UnicodeEncodeError as exc:
                    raise _invalid("STRING_INVALID", query_name, row=row_number, column=column) from exc
                total_string_bytes += encoded_size
                if encoded_size > _MAX_STRING_BYTES or total_string_bytes > _MAX_TOTAL_STRING_BYTES:
                    raise _invalid("STRING_LIMIT", query_name, row=row_number, column=column)
            if (
                column in spec.line_fields
                and isinstance(value, int)
                and not 1 <= value <= _MAX_LINE_NUMBER
            ):
                raise _invalid("LINE_INVALID", query_name, row=row_number, column=column)
            allowed = spec.enum_fields.get(column)
            if allowed is not None and value not in allowed:
                raise _invalid("ENUM_INVALID", query_name, row=row_number, column=column)
            if column in spec.path_fields:
                value = _normalize_path(value, normalized_source.source_root, query_name, column, row_number)  # type: ignore[arg-type]
            fact[column] = value
        fact["query_name"] = query_name
        fact["query_sha256"] = normalized_source.query_sha256
        for column in spec.path_fields:
            prefix = column.removesuffix("_file")
            line_column = f"{prefix}_start_line"
            if line_column in fact:
                fact[f"{prefix}_location"] = {
                    "file": fact[column],
                    "start_line": fact[line_column],
                }
        decoded.append(fact)
    return decoded


def decode_bqrs_json(
    query_name: str,
    payload: Mapping[str, object],
    source: DecodeSource,
) -> list[dict[str, object]]:
    if not isinstance(query_name, str) or len(query_name) > 128:
        raise _invalid("UNKNOWN_QUERY", "invalid")
    spec = QUERY_SPECS.get(query_name)
    if spec is None:
        raise _invalid("UNKNOWN_QUERY", query_name)
    if not isinstance(payload, dict) or set(payload) != {spec.result_set}:
        raise _invalid("RESULT_SET_MISMATCH", query_name)
    result = payload.get(spec.result_set)
    if not isinstance(result, dict) or set(result) != {"columns", "tuples"}:
        raise _invalid("RESULT_SET_INVALID", query_name)
    columns = result.get("columns")
    rows = result.get("tuples")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise _invalid("RESULT_SET_INVALID", query_name)
    normalized_columns: list[str] = []
    for column in columns:
        if isinstance(column, str):
            normalized_columns.append(column)
        elif (
            isinstance(column, dict)
            and set(column) <= {"name", "kind"}
            and isinstance(column.get("name"), str)
            and isinstance(column.get("kind"), str)
        ):
            normalized_columns.append(column["name"])
        else:
            raise _invalid("RESULT_SET_INVALID", query_name)
    return decode_rows(query_name, normalized_columns, rows, source)
