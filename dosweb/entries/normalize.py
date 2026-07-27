from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from dosweb.artifacts.identifiers import canonical_json
from dosweb.codeql import ENTRY_COLUMNS
from dosweb.errors import AnalyzerError
from dosweb.entries.models import EntryFact, FrameworkCoverage


_MAX_ROWS: Final = 4096
_PROVENANCE_FIELDS: Final = frozenset(
    {"query_name", "query_sha256", "handler_location", "registration_location"}
)
_FRAMEWORKS: Final = ("mqtt", "netty", "servlet", "spring_mvc")
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


__all__ = ["normalize_entry_rows", "normalize_framework_coverage"]
