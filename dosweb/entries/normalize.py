from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.codeql import ENTRY_COLUMNS
from dosweb.errors import AnalyzerError
from dosweb.entries.models import EntryFact, FrameworkCoverage


_MAX_ROWS: Final = 4096
_PROVENANCE_FIELDS: Final = frozenset(
    {"query_name", "query_sha256", "handler_location", "registration_location"}
)
_FRAMEWORKS: Final = ("grpc", "jax_rs", "mqtt", "netty", "servlet", "spring_mvc")
_COVERAGE_STATUSES: Final = frozenset({"complete", "partial", "unsupported"})


def _invalid(reason: str, *, field: str | None = None, row: int | None = None) -> AnalyzerError:
    details: dict[str, object] = {"reason": reason[:128]}
    if field is not None:
        details["field"] = field[:128]
    if row is not None:
        details["row"] = row
    return AnalyzerError(
        "ANALYSIS_ENTRY_INVALID",
        "Entry rows cannot be normalized safely.",
        details,
    )


def _coverage_invalid(
    reason: str, *, field: str | None = None, row: int | None = None
) -> AnalyzerError:
    details: dict[str, object] = {"reason": reason[:128]}
    if field is not None:
        details["field"] = field[:128]
    if row is not None:
        details["row"] = row
    return AnalyzerError(
        "COVERAGE_ENTRY_INVALID",
        "Entry coverage rows cannot be normalized safely.",
        details,
    )


def _materialize_rows(rows: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    if not isinstance(rows, (list, tuple)) or len(rows) > _MAX_ROWS:
        raise _invalid("ROWS_INVALID")
    materialized: list[Mapping[str, object]] = []
    expected = set(ENTRY_COLUMNS)
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise _invalid("ROW_NOT_MAPPING", row=number)
        fields = set(row)
        missing = expected - fields
        extra = fields - expected - _PROVENANCE_FIELDS
        if missing or extra:
            raise _invalid("ROW_FIELDS_INVALID", field=sorted(missing or extra)[0], row=number)
        materialized.append(row)
    return materialized


def normalize_entry_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    materialized = _materialize_rows(rows)
    grouped: dict[
        tuple[object, ...],
        list[EntryFact],
    ] = {}
    for row in materialized:
        registration_kind = row["registration_kind"]
        coverage_status = row["coverage_status"]
        if not isinstance(registration_kind, str) or not isinstance(coverage_status, str):
            raise _invalid("ROW_FIELD_TYPE_INVALID", field="coverage_status")
        if registration_kind == "dynamic_unresolved" or coverage_status != "complete":
            _validate_gap_row(row)
            continue
        fact = EntryFact.from_raw(row)
        key = (
            fact.framework,
            fact.protocol,
            fact.handler,
            fact.registration,
            fact.route_or_event,
            fact.auth_context,
            fact.materialization_phase,
        )
        grouped.setdefault(key, []).append(fact)

    normalized: list[EntryFact] = []
    for facts in grouped.values():
        first = facts[0]
        attacker_inputs = tuple(
            sorted({item for fact in facts for item in fact.attacker_inputs})
        )
        normalized.append(
            EntryFact.create(
                framework=first.framework,
                protocol=first.protocol,
                handler=first.handler,
                registration=first.registration,
                route_or_event=first.route_or_event,
                auth_context=first.auth_context,
                attacker_inputs=attacker_inputs,
                materialization_phase=first.materialization_phase,
            )
        )
    normalized.sort(key=lambda fact: canonical_json(fact.semantic_identity()))
    return [fact.to_dict() for fact in normalized]


_PLACEHOLDER_GAP_ROUTES: Final = frozenset({
    "unresolved_jax_rs_resource", "dynamic_route", "dynamic_topic",
    "dynamic_servlet_mapping", "web_xml_servlet_mapping", "grpc_dynamic_unresolved", "channelRead",
})
# ``mqtt_protocol`` normally carries too little route information to identify a
# service. SMQTT's Reactor registration is the narrow exception: the query has
# a source-backed receiver location and this diagnostic identifies the specific
# unresolved decoder/dispatcher binding. Keep it as a partial gap only.
_SMqtt_PROTOCOL_GAP_NOTE: Final = "smqtt_protocol_dispatch_binding_unresolved"


def normalize_gap_entry_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Persist partial/dynamic entry gaps that still carry a concrete route.

    A dynamic JAX-RS/Servlet/MQTT resource whose registration is unproven is a
    coverage gap, not a complete entry, but its annotation-derived route is still
    recall evidence and must not be silently dropped.
    """
    materialized = _materialize_rows(rows)
    gaps: dict[str, dict[str, object]] = {}
    for row in materialized:
        registration_kind = row["registration_kind"]
        coverage_status = row["coverage_status"]
        if registration_kind != "dynamic_unresolved" and coverage_status == "complete":
            continue
        _validate_gap_row(row)
        route = row.get("route_or_event")
        if not isinstance(route, str) or not route or route in _PLACEHOLDER_GAP_ROUTES:
            continue
        handler_file = row.get("handler_file")
        handler_start_line = row.get("handler_start_line")
        if not isinstance(handler_file, str) or not handler_file.endswith(".java") or not isinstance(handler_start_line, int):
            continue
        if route == "mqtt_protocol" and not (
            row.get("framework") == "mqtt"
            and row.get("protocol") == "mqtt"
            and row.get("coverage_note") == _SMqtt_PROTOCOL_GAP_NOTE
            and row.get("handler_fqn") == row.get("registration_fqn")
            and row.get("handler_file") == row.get("registration_file")
            and row.get("handler_fqn") == "io.github.quickmsg.core.mqtt.MqttReceiver.newTcpServer"
            and isinstance(row.get("handler_file"), str)
            and "/mqtt/MqttReceiver.java" in row["handler_file"]
            and isinstance(row.get("registration_start_line"), int)
            and row["registration_start_line"] > 0
        ):
            continue
        identity = {
            "framework": row["framework"],
            "protocol": row["protocol"],
            "route_or_event": route,
            "handler_file": handler_file,
            "handler_start_line": handler_start_line,
            "coverage_status": coverage_status,
            "coverage_note": row["coverage_note"],
        }
        gap_id = stable_identifier("gap", identity)
        gaps[gap_id] = {"gap_id": gap_id, **identity}
    return [gaps[gap_id] for gap_id in sorted(gaps)]


def normalize_framework_coverage(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    materialized = _materialize_rows(rows)
    by_framework: dict[str, dict[str, object]] = {
        framework: {"supported": set(), "unsupported": set(), "statuses": set()}
        for framework in _FRAMEWORKS
    }
    for number, row in enumerate(materialized, start=1):
        framework = row["framework"]
        status = row["coverage_status"]
        note = row["coverage_note"]
        if not isinstance(framework, str) or framework not in _FRAMEWORKS:
            raise _coverage_invalid("FRAMEWORK_INVALID", field="framework", row=number)
        if not isinstance(status, str) or status not in _COVERAGE_STATUSES:
            raise _coverage_invalid("STATUS_INVALID", field="coverage_status", row=number)
        if not isinstance(note, str) or not note or "\x00" in note:
            raise _coverage_invalid("NOTE_REQUIRED", field="coverage_note", row=number)
        try:
            if len(note.encode("utf-8")) > 65536:
                raise _coverage_invalid("NOTE_LIMIT", field="coverage_note", row=number)
        except UnicodeEncodeError as exc:
            raise _coverage_invalid("NOTE_INVALID", field="coverage_note", row=number) from exc
        if status == "complete":
            EntryFact.from_raw(row)
        else:
            _validate_gap_row(row, row_number=number)
        state = by_framework[framework]
        statuses = state["statuses"]
        assert isinstance(statuses, set)
        statuses.add(status)
        target_name = "supported" if status == "complete" else "unsupported"
        target = state[target_name]
        assert isinstance(target, set)
        target.add(note)

    coverage: list[FrameworkCoverage] = []
    for framework, state in by_framework.items():
        supported = tuple(sorted(state["supported"]))  # type: ignore[arg-type]
        unsupported = tuple(sorted(state["unsupported"]))  # type: ignore[arg-type]
        statuses = state["statuses"]
        assert isinstance(statuses, set)
        if not supported and not unsupported:
            status = "unsupported"
            unsupported = ("no_entry_query_evidence",)
        elif not unsupported:
            status = "complete"
        elif supported or "partial" in statuses:
            status = "partial"
        else:
            status = "unsupported"
        coverage.append(
            FrameworkCoverage(
                framework=framework,
                status=status,
                supported_patterns=supported,
                unsupported_patterns=unsupported,
                effect_on_verdict="none" if status == "complete" else "forces_unknown",
            )
        )
    coverage.sort(key=lambda item: item.framework)
    return [item.to_dict() for item in coverage]


def _validate_gap_row(
    row: Mapping[str, object], *, row_number: int | None = None
) -> None:
    status = row["coverage_status"]
    note = row["coverage_note"]
    if not isinstance(status, str) or status not in {"partial", "unsupported"}:
        raise _coverage_invalid(
            "GAP_STATUS_INVALID", field="coverage_status", row=row_number
        )
    if not isinstance(note, str) or not note or "\x00" in note:
        raise _coverage_invalid("NOTE_REQUIRED", field="coverage_note", row=row_number)
    registration_kind = row["registration_kind"]
    if not isinstance(registration_kind, str) or registration_kind != "dynamic_unresolved":
        raise _coverage_invalid(
            "GAP_REGISTRATION_KIND_INVALID",
            field="registration_kind",
            row=row_number,
        )
    _validate_gap_fields(row, row_number=row_number)


def _validate_gap_fields(
    row: Mapping[str, object], *, row_number: int | None = None
) -> None:
    framework = row["framework"]
    protocol = row["protocol"]
    expected_protocols = {
        "spring_mvc": "http",
        "servlet": "http",
        "netty": "tcp",
        "mqtt": "mqtt",
        "jax_rs": "http",
        "grpc": "grpc",
    }
    if not isinstance(framework, str) or framework not in expected_protocols:
        raise _coverage_invalid("FRAMEWORK_INVALID", field="framework", row=row_number)
    if not isinstance(protocol, str) or protocol != expected_protocols[framework]:
        raise _coverage_invalid("PROTOCOL_INVALID", field="protocol", row=row_number)
    for field in (
        "handler_fqn",
        "handler_file",
        "registration_fqn",
        "registration_file",
        "route_or_event",
        "auth_context",
        "attacker_input_name",
        "attacker_input_type",
        "attacker_input_kind",
        "materialization_phase",
    ):
        value = row[field]
        if not isinstance(value, str) or not value or "\x00" in value:
            raise _coverage_invalid("GAP_FIELD_INVALID", field=field, row=row_number)
    for field in ("handler_start_line", "registration_start_line"):
        value = row[field]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise _coverage_invalid("GAP_LINE_INVALID", field=field, row=row_number)
    for field in ("handler_file", "registration_file"):
        value = row[field]
        assert isinstance(value, str)
        parts = value.replace("\\", "/").split("/")
        if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            raise _coverage_invalid("GAP_PATH_INVALID", field=field, row=row_number)
    if row["auth_context"] not in {
        "unauthenticated",
        "low_privilege",
        "privileged",
        "unknown",
    }:
        raise _coverage_invalid("GAP_ENUM_INVALID", field="auth_context", row=row_number)
    if row["attacker_input_kind"] not in {
        "request_body",
        "request_parameter",
        "path_parameter",
        "header",
        "model_attribute",
        "message_payload",
        "stream",
        "unknown",
    }:
        raise _coverage_invalid(
            "GAP_ENUM_INVALID", field="attacker_input_kind", row=row_number
        )
    if row["materialization_phase"] not in {
        "before_handler",
        "in_handler",
        "streaming",
        "unknown",
    }:
        raise _coverage_invalid(
            "GAP_ENUM_INVALID", field="materialization_phase", row=row_number
        )


__all__ = ["normalize_entry_rows", "normalize_framework_coverage", "normalize_gap_entry_rows"]
