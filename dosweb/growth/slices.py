from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, TypeAlias, cast

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.schemas import validate_records
from dosweb.codeql.decoder import GROWTH_COLUMNS
from dosweb.errors import AnalyzerError
from dosweb.growth.models import (
    BoundedSlice,
    BoundedSlicePayload,
    CfgSummary,
    ConfigFact,
    RegistrationFact,
    SourceExcerpt,
    StaticFact,
)

GrowthKind: TypeAlias = Literal[
    "input_materialization", "direct_allocation", "container_growth", "async_work_growth"
]
ResourceDimension: TypeAlias = Literal["entries", "bytes", "tasks", "connections", "objects"]
DemandRole: TypeAlias = Literal["size", "key", "value", "iteration_count", "submission_count", "unknown"]
EscapeScope: TypeAlias = Literal["request", "session", "instance", "global", "unknown"]
CoverageStatus: TypeAlias = Literal["complete", "partial"]

_GROWTH_KINDS = frozenset({"input_materialization", "direct_allocation", "container_growth", "async_work_growth"})
_RESOURCE_DIMENSIONS = frozenset({"entries", "bytes", "tasks", "connections", "objects"})
_DEMAND_ROLES = frozenset({"size", "key", "value", "iteration_count", "submission_count", "unknown"})
_ESCAPE_SCOPES = frozenset({"request", "session", "instance", "global", "unknown"})
_COVERAGE = frozenset({"complete", "partial"})
_PROVENANCE_FIELDS = frozenset({"query_name", "query_sha256", "site_location"})
_RAW_FIELDS = frozenset(GROWTH_COLUMNS)
_MAX_ROWS = 4096
_MAX_STRING_BYTES = 65536
_MAX_LINE = 2**31 - 1


def _invalid(reason: str, field: str | None = None) -> AnalyzerError:
    details: dict[str, object] = {"reason": reason[:128]}
    if field is not None:
        details["field"] = field[:128]
    return AnalyzerError(
        "ANALYSIS_GROWTH_INVALID",
        "Growth candidate violates the normalized static-analysis contract.",
        details,
    )


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise _invalid("STRING_REQUIRED", field)
    try:
        if len(value.encode("utf-8")) > _MAX_STRING_BYTES:
            raise _invalid("STRING_LIMIT", field)
    except UnicodeEncodeError as exc:
        raise _invalid("STRING_INVALID", field) from exc
    return value


def _enum(value: object, allowed: frozenset[str], field: str) -> str:
    normalized = _string(value, field)
    if normalized not in allowed:
        raise _invalid("ENUM_INVALID", field)
    return normalized


def _path(value: object, field: str) -> str:
    normalized = _string(value, field).replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise _invalid("PATH_INVALID", field)
    return path.as_posix()


def _line(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= _MAX_LINE:
        raise _invalid("POSITIVE_LINE_REQUIRED", field)
    return value


def _evidence_id(value: object, *, site: SourceLocation | None = None) -> str:
    evidence = _string(value, "candidate_evidence")
    if evidence.startswith("fact:"):
        suffix = evidence[5:]
        if not suffix or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for character in suffix):
            raise _invalid("EVIDENCE_ID_INVALID", "candidate_evidence")
        return evidence
    if site is None:
        raise _invalid("EVIDENCE_SITE_REQUIRED", "candidate_evidence")
    return stable_identifier(
        "fact",
        {"candidate_evidence": evidence, "site": site.to_dict()},
    )


@dataclass(frozen=True, order=True)
class SourceLocation:
    file: str
    start_line: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "file", _path(self.file, "site_file"))
        object.__setattr__(self, "start_line", _line(self.start_line, "site_start_line"))

    def to_dict(self) -> dict[str, object]:
        return {"file": self.file, "start_line": self.start_line}


@dataclass(frozen=True, order=True)
class DemandInput:
    name: str
    role: DemandRole

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _string(self.name, "demand_input_name"))
        object.__setattr__(self, "role", cast(DemandRole, _enum(self.role, _DEMAND_ROLES, "demand_input_role")))

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "role": self.role}


@dataclass(frozen=True)
class GrowthCandidate:
    growth_id: str
    site: SourceLocation
    kind: GrowthKind
    operation: str
    resource_id: str
    resource_dimension: ResourceDimension
    receiver: str
    field_path: str
    demand_inputs: tuple[DemandInput, ...]
    escape_scope: EscapeScope
    evidence_ids: frozenset[str]
    coverage_status: CoverageStatus = "complete"
    coverage_notes: tuple[str, ...] = ("normalized",)

    def __post_init__(self) -> None:
        if not isinstance(self.site, SourceLocation):
            raise _invalid("SITE_INVALID", "site")
        object.__setattr__(self, "kind", cast(GrowthKind, _enum(self.kind, _GROWTH_KINDS, "growth_kind")))
        object.__setattr__(self, "operation", _string(self.operation, "operation"))
        object.__setattr__(self, "resource_dimension", cast(ResourceDimension, _enum(self.resource_dimension, _RESOURCE_DIMENSIONS, "resource_dimension")))
        object.__setattr__(self, "escape_scope", cast(EscapeScope, _enum(self.escape_scope, _ESCAPE_SCOPES, "escape_scope")))
        object.__setattr__(self, "coverage_status", cast(CoverageStatus, _enum(self.coverage_status, _COVERAGE, "coverage_status")))
        object.__setattr__(self, "receiver", _string(self.receiver, "receiver"))
        object.__setattr__(self, "field_path", _string(self.field_path, "field_path"))
        try:
            demands = tuple(sorted(set(self.demand_inputs)))
            evidence = frozenset(self.evidence_ids)
            coverage_notes = tuple(sorted(set(self.coverage_notes)))
        except (TypeError, ValueError, MemoryError, RecursionError) as exc:
            raise _invalid("COLLECTION_INVALID") from exc
        if not demands or len(demands) > 64 or not all(isinstance(item, DemandInput) for item in demands):
            raise _invalid("DEMAND_INPUTS_INVALID", "demand_inputs")
        if not evidence or len(evidence) > 64 or not all(
            isinstance(item, str)
            and item.startswith("fact:")
            and bool(item[5:])
            and all(
                character in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
                for character in item[5:]
            )
            for item in evidence
        ):
            raise _invalid("EVIDENCE_INVALID", "evidence_ids")
        if not coverage_notes or len(coverage_notes) > 64 or not all(
            _string(item, "coverage_notes") for item in coverage_notes
        ):
            raise _invalid("COVERAGE_NOTES_INVALID", "coverage_notes")
        object.__setattr__(self, "demand_inputs", demands)
        object.__setattr__(self, "evidence_ids", evidence)
        object.__setattr__(self, "coverage_notes", coverage_notes)
        expected_resource = stable_identifier("resource", self.resource_identity)
        expected_growth = stable_identifier("growth", self.semantic_identity)
        if self.resource_id != expected_resource:
            raise _invalid("RESOURCE_ID_MISMATCH", "resource_id")
        if self.growth_id != expected_growth:
            raise _invalid("GROWTH_ID_MISMATCH", "growth_id")

    @property
    def resource_identity(self) -> dict[str, object]:
        return {
            "dimension": self.resource_dimension,
            "receiver": self.receiver,
            "field_path": self.field_path,
        }

    @property
    def semantic_identity(self) -> dict[str, object]:
        return {
            "site": self.site.to_dict(),
            "kind": self.kind,
            "operation": self.operation,
            "resource_id": self.resource_id,
            "resource_dimension": self.resource_dimension,
            "receiver": self.receiver,
            "field_path": self.field_path,
            "demand_inputs": [item.to_dict() for item in self.demand_inputs],
            "escape_scope": self.escape_scope,
            "evidence_ids": sorted(self.evidence_ids),
            "coverage_status": self.coverage_status,
            "coverage_notes": list(self.coverage_notes),
        }

    @classmethod
    def create(
        cls,
        *,
        site: SourceLocation,
        kind: GrowthKind,
        operation: str,
        resource_dimension: ResourceDimension,
        receiver: str,
        field_path: str,
        demand_inputs: Sequence[DemandInput],
        escape_scope: EscapeScope,
        evidence_ids: frozenset[str],
        coverage_status: CoverageStatus = "complete",
        coverage_notes: Sequence[str] = ("normalized",),
    ) -> GrowthCandidate:
        resource_identity = {"dimension": resource_dimension, "receiver": receiver, "field_path": field_path}
        resource_id = stable_identifier("resource", resource_identity)
        normalized_demands = tuple(sorted(set(demand_inputs)))
        normalized_notes = tuple(sorted(set(coverage_notes)))
        semantic_identity = {
            "site": site.to_dict(), "kind": kind, "operation": operation,
            "resource_id": resource_id, "resource_dimension": resource_dimension,
            "receiver": receiver, "field_path": field_path,
            "demand_inputs": [item.to_dict() for item in normalized_demands],
            "escape_scope": escape_scope, "evidence_ids": sorted(evidence_ids),
            "coverage_status": coverage_status, "coverage_notes": list(normalized_notes),
        }
        return cls(
            stable_identifier("growth", semantic_identity), site, kind, operation, resource_id,
            resource_dimension, receiver, field_path, normalized_demands, escape_scope, evidence_ids,
            coverage_status, normalized_notes,
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, object]) -> GrowthCandidate:
        return _candidate_from_rows((raw,))

    def to_dict(self) -> dict[str, object]:
        return {
            "growth_id": self.growth_id,
            "site": self.site.to_dict(),
            "kind": self.kind,
            "operation": self.operation,
            "resource_point": {
                "resource_id": self.resource_id,
                "dimension": self.resource_dimension,
                "receiver": self.receiver,
                "field_path": self.field_path,
            },
            "demand_inputs": [item.to_dict() for item in self.demand_inputs],
            "escape_scope": self.escape_scope,
            "candidate_evidence": sorted(self.evidence_ids),
            "coverage_status": self.coverage_status,
            "coverage_notes": list(self.coverage_notes),
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> GrowthCandidate:
        if not isinstance(record, Mapping) or set(record) != {"growth_id", "site", "kind", "operation", "resource_point", "demand_inputs", "escape_scope", "candidate_evidence", "coverage_status", "coverage_notes"}:
            raise _invalid("RECORD_FIELDS_INVALID")
        site = record["site"]; point = record["resource_point"]
        demands = record["demand_inputs"]; evidence = record["candidate_evidence"]
        if not isinstance(site, Mapping) or set(site) != {"file", "start_line"} or not isinstance(point, Mapping) or set(point) != {"resource_id", "dimension", "receiver", "field_path"} or not isinstance(demands, list) or not isinstance(evidence, list) or not isinstance(record["coverage_notes"], list):
            raise _invalid("RECORD_FIELDS_INVALID")
        candidate = cls.create(
            site=SourceLocation(site["file"], site["start_line"]), kind=cast(GrowthKind, record["kind"]), operation=record["operation"], resource_dimension=cast(ResourceDimension, point["dimension"]), receiver=point["receiver"], field_path=point["field_path"], demand_inputs=tuple(DemandInput(item["name"], item["role"]) for item in demands if isinstance(item, Mapping) and set(item) == {"name", "role"}), escape_scope=cast(EscapeScope, record["escape_scope"]), evidence_ids=frozenset(evidence), coverage_status=cast(CoverageStatus, record["coverage_status"]), coverage_notes=tuple(record["coverage_notes"]),
        )
        if record["growth_id"] != candidate.growth_id or point["resource_id"] != candidate.resource_id:
            raise _invalid("IDENTIFIER_MISMATCH")
        return candidate


def load_growth_candidates(path: Path) -> tuple[GrowthCandidate, ...]:
    records = read_jsonl_strict(path, "growth_candidates")
    validate_records("growth_candidates", records)
    candidates = tuple(GrowthCandidate.from_dict(record) for record in records)
    if len({item.growth_id for item in candidates}) != len(candidates):
        raise _invalid("DUPLICATE_GROWTH_ID")
    return candidates


def _validated_raw(raw: Mapping[str, object]) -> dict[str, object]:
    try:
        fields = set(raw) if isinstance(raw, Mapping) else set()
    except (TypeError, ValueError, MemoryError, RecursionError) as exc:
        raise _invalid("RAW_FIELDS_INVALID") from exc
    if not isinstance(raw, Mapping) or fields != (_RAW_FIELDS | _PROVENANCE_FIELDS):
        raise _invalid("RAW_FIELDS_INVALID")
    status = _enum(raw["coverage_status"], _COVERAGE, "coverage_status")
    _string(raw["coverage_note"], "coverage_note")
    site = SourceLocation(_path(raw["site_file"], "site_file"), _line(raw["site_start_line"], "site_start_line"))
    return {
        "site": site,
        "kind": cast(GrowthKind, _enum(raw["growth_kind"], _GROWTH_KINDS, "growth_kind")),
        "operation": _string(raw["operation"], "operation"),
        "resource_dimension": cast(ResourceDimension, _enum(raw["resource_dimension"], _RESOURCE_DIMENSIONS, "resource_dimension")),
        "receiver": _string(raw["receiver"], "receiver"),
        "field_path": _string(raw["field_path"], "field_path"),
        "demand": DemandInput(_string(raw["demand_input_name"], "demand_input_name"), cast(DemandRole, _enum(raw["demand_input_role"], _DEMAND_ROLES, "demand_input_role"))),
        "escape_scope": cast(EscapeScope, _enum(raw["escape_scope"], _ESCAPE_SCOPES, "escape_scope")),
        "evidence_id": _evidence_id(raw["candidate_evidence"], site=site),
        "coverage_status": status,
        "coverage_note": _string(raw["coverage_note"], "coverage_note"),
    }


def _candidate_from_rows(rows: Sequence[Mapping[str, object]]) -> GrowthCandidate:
    normalized = [_validated_raw(row) for row in rows]
    if not normalized:
        raise _invalid("ROWS_REQUIRED")
    first = normalized[0]
    identity_fields = ("site", "kind", "operation", "resource_dimension", "receiver", "field_path", "escape_scope")
    if any(any(item[field] != first[field] for field in identity_fields) for item in normalized[1:]):
        raise _invalid("ROW_GROUP_MISMATCH")
    coverage_status: CoverageStatus = (
        "partial"
        if any(item["coverage_status"] != "complete" for item in normalized)
        else "complete"
    )
    return GrowthCandidate.create(
        site=cast(SourceLocation, first["site"]),
        kind=cast(GrowthKind, first["kind"]),
        operation=cast(str, first["operation"]),
        resource_dimension=cast(ResourceDimension, first["resource_dimension"]),
        receiver=cast(str, first["receiver"]),
        field_path=cast(str, first["field_path"]),
        demand_inputs=tuple(cast(DemandInput, item["demand"]) for item in normalized),
        escape_scope=cast(EscapeScope, first["escape_scope"]),
        evidence_ids=frozenset(cast(str, item["evidence_id"]) for item in normalized),
        coverage_status=coverage_status,
        coverage_notes=tuple(cast(str, item["coverage_note"]) for item in normalized),
    )


def normalize_growth_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    try:
        materialized = tuple(rows[: _MAX_ROWS + 1])
    except (TypeError, ValueError, OverflowError, MemoryError, RecursionError) as exc:
        raise _invalid("ROWS_INVALID") from exc
    if len(materialized) > _MAX_ROWS:
        raise _invalid("ROW_LIMIT")
    groups: dict[bytes, list[Mapping[str, object]]] = {}
    for row in materialized:
        normalized = _validated_raw(row)
        key = canonical_json({
            field: normalized[field]
            if field != "site"
            else cast(SourceLocation, normalized[field]).to_dict()
            for field in ("site", "kind", "operation", "resource_dimension", "receiver", "field_path", "escape_scope")
        })
        groups.setdefault(key, []).append(row)
    candidates = [_candidate_from_rows(group) for _, group in sorted(groups.items())]
    return [candidate.to_dict() for candidate in sorted(candidates, key=lambda item: canonical_json(item.semantic_identity))]


def build_bounded_slice(
    *,
    entry_id: str,
    candidate: GrowthCandidate,
    source_excerpts: Sequence[SourceExcerpt],
    static_facts: Sequence[StaticFact],
    cfg_summary: CfgSummary,
    registration_facts: Sequence[RegistrationFact],
    config_facts: Sequence[ConfigFact],
) -> BoundedSlice:
    if not isinstance(entry_id, str) or not entry_id.startswith("entry:") or not isinstance(candidate, GrowthCandidate):
        raise _invalid("SLICE_IDENTITY_INVALID")
    excerpts = tuple(sorted(source_excerpts, key=lambda item: canonical_json(item.to_dict())))
    facts = tuple(sorted(static_facts, key=lambda item: item.fact_id))
    registrations = tuple(sorted(registration_facts, key=lambda item: canonical_json(item.to_dict())))
    configs = tuple(sorted(config_facts, key=lambda item: canonical_json(item.to_dict())))
    if not excerpts or not any(
        excerpt.repo_relative_path == candidate.site.file
        and excerpt.start_line <= candidate.site.start_line <= excerpt.end_line
        for excerpt in excerpts
    ):
        raise _invalid("CANDIDATE_LOCATION_OUTSIDE_SLICE")
    fact_ids = {fact.fact_id for fact in facts}
    if not candidate.evidence_ids <= fact_ids:
        raise _invalid("CANDIDATE_EVIDENCE_UNMAPPED", "evidence_ids")
    normalized_cfg = CfgSummary(
        tuple(cfg_summary.path_ids),
        tuple(cfg_summary.phases),
        tuple(sorted(set(cfg_summary.branch_facts))),
    )
    payload = BoundedSlicePayload(
        entry_id=entry_id,
        growth_id=candidate.growth_id,
        source_excerpts=excerpts,
        static_facts=facts,
        cfg_summary=normalized_cfg,
        registration_facts=registrations,
        config_facts=configs,
    )
    return BoundedSlice(stable_identifier("slice", payload.to_dict()), payload)
