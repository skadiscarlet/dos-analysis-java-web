from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.schemas import validate_records
from typing import Literal, TypeAlias, cast

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.codeql.decoder import FLOW_COLUMNS
from dosweb.entries import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.growth import VerifiedGrowthResult

AttackerTarget: TypeAlias = Literal["size", "key", "value", "iteration_count", "submission_count"]
FlowConfidence: TypeAlias = Literal["proven", "partial"]

_TARGETS = frozenset({"size", "key", "value", "iteration_count", "submission_count"})
_CONFIDENCE = frozenset({"proven", "partial"})
_COVERAGE = frozenset({"complete", "partial", "unsupported"})
_RAW_FIELDS = frozenset(FLOW_COLUMNS)
_PROVENANCE_FIELDS = frozenset({"query_name", "query_sha256", "source_location", "sink_location"})
_MAX_ROWS = 4096
_MAX_ITEMS = 64
_MAX_STRING_BYTES = 65536


def _invalid(reason: str, field: str | None = None) -> AnalyzerError:
    details: dict[str, object] = {"reason": reason[:128]}
    if field is not None:
        details["field"] = field[:128]
    return AnalyzerError("ANALYSIS_FLOW_INVALID", "Flow proof violates the normalized static-analysis contract.", details)


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
    value = _string(value, field)
    if value not in allowed:
        raise _invalid("ENUM_INVALID", field)
    return value


def _path(value: object, field: str) -> str:
    value = _string(value, field).replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise _invalid("PATH_INVALID", field)
    return path.as_posix()


def _line(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0 or value > 2**31 - 1:
        raise _invalid("POSITIVE_LINE_REQUIRED", field)
    return value


def _sequence(value: object, field: str, separator: str = ">") -> tuple[str, ...]:
    if isinstance(value, str):
        values = tuple(part.strip() for part in value.split(separator))
    elif isinstance(value, (tuple, list)):
        values = tuple(value)
    else:
        raise _invalid("SEQUENCE_INVALID", field)
    if not values or len(values) > _MAX_ITEMS:
        raise _invalid("SEQUENCE_LIMIT", field)
    return tuple(_string(item, field) for item in values)


@dataclass(frozen=True, order=True)
class AttackerControl:
    target: AttackerTarget
    source: str
    sink: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", cast(AttackerTarget, _enum(self.target, _TARGETS, "attacker_target")))
        object.__setattr__(self, "source", _string(self.source, "attacker_source"))
        object.__setattr__(self, "sink", _string(self.sink, "attacker_sink"))

    def to_dict(self) -> dict[str, str]:
        return {"target": self.target, "source": self.source, "sink": self.sink}


@dataclass(frozen=True)
class FlowProof:
    path_id: str
    entry_id: str
    growth_id: str
    attacker_control: AttackerControl
    call_path: tuple[str, ...]
    phase_sequence: tuple[str, ...]
    confidence: FlowConfidence
    flow_kind: str = "data_flow"
    coverage_status: str = "complete"
    coverage_note: str = "normalized"

    def __post_init__(self) -> None:
        if not isinstance(self.attacker_control, AttackerControl):
            raise _invalid("ATTACKER_CONTROL_INVALID")
        if not isinstance(self.entry_id, str) or not self.entry_id.startswith("entry:"):
            raise _invalid("ENTRY_ID_INVALID", "entry_id")
        if not isinstance(self.growth_id, str) or not self.growth_id.startswith("growth:"):
            raise _invalid("GROWTH_ID_INVALID", "growth_id")
        object.__setattr__(self, "call_path", _sequence(self.call_path, "call_path"))
        object.__setattr__(self, "phase_sequence", _sequence(self.phase_sequence, "phase_sequence"))
        object.__setattr__(self, "confidence", cast(FlowConfidence, _enum(self.confidence, _CONFIDENCE, "confidence")))
        object.__setattr__(self, "flow_kind", _string(self.flow_kind, "flow_kind"))
        object.__setattr__(self, "coverage_status", _enum(self.coverage_status, _COVERAGE, "coverage_status"))
        object.__setattr__(self, "coverage_note", _string(self.coverage_note, "coverage_note"))
        if self.confidence == "proven" and (
            self.flow_kind not in {"data_flow", "local_data_flow"} or self.coverage_status != "complete"
        ):
            raise _invalid("PROVEN_FLOW_REQUIRES_COMPLETE_DATA_FLOW")
        if self.path_id != stable_identifier("flow", self.semantic_identity):
            raise _invalid("PATH_ID_MISMATCH", "path_id")

    @property
    def semantic_identity(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "growth_id": self.growth_id,
            "attacker_control": self.attacker_control.to_dict(),
            "call_path": list(self.call_path),
            "phase_sequence": list(self.phase_sequence),
            "confidence": self.confidence,
        }

    @classmethod
    def create(cls, *, entry_id: str, growth_id: str, attacker_control: AttackerControl, call_path: Sequence[str], phase_sequence: Sequence[str], confidence: FlowConfidence, flow_kind: str = "data_flow", coverage_status: str = "complete", coverage_note: str = "normalized") -> FlowProof:
        normalized_call = _sequence(tuple(call_path), "call_path")
        normalized_phases = _sequence(tuple(phase_sequence), "phase_sequence")
        identity = {"entry_id": entry_id, "growth_id": growth_id, "attacker_control": attacker_control.to_dict(), "call_path": list(normalized_call), "phase_sequence": list(normalized_phases), "confidence": confidence}
        return cls(stable_identifier("flow", identity), entry_id, growth_id, attacker_control, normalized_call, normalized_phases, confidence, flow_kind, coverage_status, coverage_note)

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> FlowProof:
        if not isinstance(record, Mapping) or set(record) not in ({"path_id", "entry_id", "growth_id", "attacker_control", "call_path", "phase_sequence", "confidence"}, {"path_id", "entry_id", "growth_id", "attacker_control", "call_path", "phase_sequence", "confidence", "flow_kind", "coverage_status", "coverage_note"}):
            raise _invalid("RECORD_FIELDS_INVALID")
        control = record["attacker_control"]
        if not isinstance(control, Mapping) or set(control) != {"target", "source", "sink"}:
            raise _invalid("ATTACKER_CONTROL_INVALID")
        return cls(
            cast(str, record["path_id"]), cast(str, record["entry_id"]), cast(str, record["growth_id"]),
            AttackerControl(cast(AttackerTarget, control["target"]), cast(str, control["source"]), cast(str, control["sink"])),
            _sequence(record["call_path"], "call_path"), _sequence(record["phase_sequence"], "phase_sequence"), cast(FlowConfidence, record["confidence"]), cast(str, record.get("flow_kind", "data_flow")), cast(str, record.get("coverage_status", "complete")), cast(str, record.get("coverage_note", "normalized")),
        )

    def to_dict(self) -> dict[str, object]:
        return {"path_id": self.path_id, "entry_id": self.entry_id, "growth_id": self.growth_id, "attacker_control": self.attacker_control.to_dict(), "call_path": list(self.call_path), "phase_sequence": list(self.phase_sequence), "confidence": self.confidence, "flow_kind": self.flow_kind, "coverage_status": self.coverage_status, "coverage_note": self.coverage_note}


def load_flow_proofs(path: Path) -> tuple[FlowProof, ...]:
    records = read_jsonl_strict(path, "flow_proofs")
    validate_records("flow_proofs", records)
    proofs = tuple(FlowProof.from_dict(record) for record in records)
    if len({item.path_id for item in proofs}) != len(proofs):
        raise _invalid("DUPLICATE_PATH_ID")
    return proofs


def _entry_registration_identity(entry: EntryFact) -> tuple[str, str, str, int]:
    return (
        entry.registration.kind,
        entry.registration.callable,
        entry.registration.file,
        entry.registration.start_line,
    )


def _entry_semantic_key(entry: EntryFact) -> tuple[object, ...]:
    return (
        entry.framework,
        entry.protocol,
        entry.handler.callable,
        entry.handler.file,
        entry.handler.start_line,
        entry.route_or_event,
        entry.auth_context,
        tuple((item.name, item.type, item.kind) for item in entry.attacker_inputs),
        entry.materialization_phase,
    )


def _canonical_entry_for_growth(matches: Sequence[EntryFact], growth_result: VerifiedGrowthResult) -> EntryFact:
    candidate = growth_result.candidate
    if candidate is None:
        raise _invalid("FLOW_REFERENCE_AMBIGUOUS")
    demand_names = frozenset(item.name for item in candidate.demand_inputs)
    narrowed = tuple(matches)
    if demand_names:
        demand_matched = tuple(
            entry for entry in narrowed
            if demand_names & {item.name for item in entry.attacker_inputs}
        )
        if demand_matched:
            narrowed = demand_matched
    if len(narrowed) == 1:
        return narrowed[0]
    if len({_entry_semantic_key(entry) for entry in narrowed}) == 1:
        return min(narrowed, key=lambda entry: (_entry_registration_identity(entry), entry.entry_id))
    if len({_entry_registration_identity(entry) for entry in narrowed}) == 1:
        return min(narrowed, key=lambda entry: entry.entry_id)
    raise _invalid("FLOW_REFERENCE_AMBIGUOUS")


def normalize_flow_rows(rows: Sequence[Mapping[str, object]], entries: Mapping[str, EntryFact], growth: Mapping[str, VerifiedGrowthResult]) -> list[dict[str, object]]:
    materialized = tuple(rows[: _MAX_ROWS + 1])
    if len(materialized) > _MAX_ROWS:
        raise _invalid("ROW_LIMIT")
    proofs: dict[str, FlowProof] = {}
    for row in materialized:
        if not isinstance(row, Mapping):
            raise _invalid("ROW_NOT_MAPPING")
        fields = set(row)
        extra = fields - _RAW_FIELDS - _PROVENANCE_FIELDS
        missing = _RAW_FIELDS - fields
        if missing or extra:
            raise _invalid("RAW_FIELDS_INVALID", sorted(missing or extra)[0])
        source_file = _path(row["source_file"], "source_file")
        source_line = _line(row["source_start_line"], "source_start_line")
        sink_file = _path(row["sink_file"], "sink_file")
        sink_line = _line(row["sink_start_line"], "sink_start_line")
        entry_matches = [item for item in entries.values() if isinstance(item, EntryFact) and item.handler.file == source_file and item.handler.start_line == source_line]
        growth_matches = [item for item in growth.values() if isinstance(item, VerifiedGrowthResult) and item.candidate is not None and item.candidate.site.file == sink_file and item.candidate.site.start_line == sink_line]
        if len(growth_matches) != 1 or not entry_matches:
            raise _invalid("FLOW_REFERENCE_AMBIGUOUS")
        growth_result = growth_matches[0]
        entry = _canonical_entry_for_growth(tuple(sorted(entry_matches, key=lambda item: item.entry_id)), growth_result)
        control = AttackerControl(cast(AttackerTarget, row["attacker_target"]), _string(row["attacker_source"], "attacker_source"), _string(row["attacker_sink"], "attacker_sink"))
        roles = {item.role for item in growth_result.candidate.demand_inputs}
        input_names = {item.name for item in entry.attacker_inputs}
        demand_names = {item.name for item in growth_result.candidate.demand_inputs if item.role == control.target}
        if control.target not in roles:
            raise _invalid("ATTACKER_TARGET_NOT_GROWTH_DEMAND", "attacker_target")
        if control.source not in input_names:
            raise _invalid("ATTACKER_SOURCE_NOT_ENTRY_INPUT", "attacker_source")
        if not any(name in control.sink for name in demand_names):
            raise _invalid("ATTACKER_SINK_NOT_GROWTH_DEMAND", "attacker_sink")
        coverage = _enum(row["coverage_status"], _COVERAGE, "coverage_status")
        confidence = cast(FlowConfidence, _enum(row["confidence"], _CONFIDENCE, "confidence"))
        flow_kind = _string(row["flow_kind"], "flow_kind")
        if coverage != "complete" or flow_kind not in {"data_flow", "local_data_flow"}:
            confidence = "partial"
        proof = FlowProof.create(entry_id=entry.entry_id, growth_id=growth_result.growth_id, attacker_control=control, call_path=_sequence(row["call_path"], "call_path"), phase_sequence=_sequence(row["phase_sequence"], "phase_sequence"), confidence=confidence, flow_kind=flow_kind, coverage_status=coverage, coverage_note=_string(row["coverage_note"], "coverage_note"))
        proofs[proof.path_id] = proof
    return [proofs[key].to_dict() for key in sorted(proofs, key=lambda item: canonical_json(proofs[item].semantic_identity))]
