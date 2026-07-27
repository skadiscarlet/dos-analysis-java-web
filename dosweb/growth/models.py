from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Iterable, Literal, Mapping, cast

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.schemas import validate_records
from dosweb.errors import AnalyzerError

_ID = re.compile(r"^[a-z_]+:[A-Za-z0-9._-]+$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")
_MAX_ID_BYTES = 256
_MAX_PATH_BYTES = 512
_MAX_SOURCE_EXCERPTS = 64
_MAX_STATIC_FACTS = 256
_MAX_REGISTRATION_FACTS = 64
_MAX_CONFIG_FACTS = 64
_MAX_CFG_PATH_IDS = 64
_MAX_CFG_PHASES = 16
_MAX_CFG_BRANCH_FACTS = 256
_MAX_SOURCE_BYTES = 65536
_MAX_CANONICAL_PAYLOAD_BYTES = 131072
_MAX_CONFIG_INTEGER = 2**31 - 1
_MAX_LINE_NUMBER = 2**31 - 1


def _fail() -> None:
    raise AnalyzerError("LLM_BOUNDED_SLICE_INVALID", "Bounded slice violates the strict public-source schema.")


def _utf8_bytes_at_most(value: object, limit: int) -> bytes | None:
    if not isinstance(value, str) or len(value) > limit:
        return None
    encoded = value.encode("utf-8")
    return encoded if len(encoded) <= limit else None


def _id(value: object, prefix: str) -> bool:
    return isinstance(value, str) and _utf8_bytes_at_most(value, _MAX_ID_BYTES) is not None and value.startswith(prefix) and bool(_ID.fullmatch(value))


def _bounded_tuple(values: Iterable[object], limit: int) -> tuple[object, ...]:
    try:
        result = tuple(islice(iter(values), limit + 1))
    except (TypeError, ValueError, OverflowError, MemoryError, RecursionError):
        _fail()
    if len(result) > limit:
        _fail()
    return result


def _unique(values: Iterable[str]) -> bool:
    materialized = tuple(values)
    return len(materialized) == len(set(materialized))


@dataclass(frozen=True)
class SourceExcerpt:
    excerpt_id: str; repo_relative_path: str; start_line: int; end_line: int; content: str; git_blob_sha256: str; excerpt_sha256: str
    def __post_init__(self) -> None:
        try:
            path_bytes = _utf8_bytes_at_most(self.repo_relative_path, _MAX_PATH_BYTES)
            content_bytes = _utf8_bytes_at_most(self.content, 16384)
            valid = (_id(self.excerpt_id, "excerpt:") and isinstance(self.repo_relative_path, str) and bool(self.repo_relative_path) and path_bytes is not None and not self.repo_relative_path.startswith("/") and ".." not in self.repo_relative_path.split("/") and bool(_PATH.fullmatch(self.repo_relative_path)) and isinstance(self.start_line, int) and not isinstance(self.start_line, bool) and 1 <= self.start_line <= _MAX_LINE_NUMBER and isinstance(self.end_line, int) and not isinstance(self.end_line, bool) and self.start_line <= self.end_line <= _MAX_LINE_NUMBER and isinstance(self.content, str) and bool(self.content) and content_bytes is not None and bool(_SHA.fullmatch(self.git_blob_sha256)) and bool(_SHA.fullmatch(self.excerpt_sha256)) and hashlib.sha256(content_bytes).hexdigest() == self.excerpt_sha256)
        except (UnicodeError, ValueError, OverflowError, MemoryError):
            _fail()
        if not valid: _fail()
    def to_dict(self) -> dict[str, object]: return self.__dict__.copy()

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> SourceExcerpt:
        if not isinstance(record, Mapping) or set(record) != {"excerpt_id", "repo_relative_path", "start_line", "end_line", "content", "git_blob_sha256", "excerpt_sha256"}:
            _fail()
        return cls(cast(str, record["excerpt_id"]), cast(str, record["repo_relative_path"]), cast(int, record["start_line"]), cast(int, record["end_line"]), cast(str, record["content"]), cast(str, record["git_blob_sha256"]), cast(str, record["excerpt_sha256"]))


@dataclass(frozen=True)
class StaticFact:
    fact_id: str; kind: Literal["container_write", "allocation", "input_materialization", "async_submission", "flow", "guard", "bound", "release"]; location_ref: str; relation: Literal["source", "sink", "flows_to", "guards", "bounds", "releases"]; value_ref: str | None = None
    def __post_init__(self) -> None:
        if not _id(self.fact_id, "fact:") or self.kind not in {"container_write", "allocation", "input_materialization", "async_submission", "flow", "guard", "bound", "release"} or not _id(self.location_ref, "excerpt:") or self.relation not in {"source", "sink", "flows_to", "guards", "bounds", "releases"} or (self.value_ref is not None and not _id(self.value_ref, "fact:")): _fail()
    def to_dict(self) -> dict[str, object]: return self.__dict__.copy()

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> StaticFact:
        if not isinstance(record, Mapping) or set(record) != {"fact_id", "kind", "location_ref", "relation", "value_ref"}:
            _fail()
        return cls(cast(str, record["fact_id"]), cast(str, record["kind"]), cast(str, record["location_ref"]), cast(str, record["relation"]), cast(str | None, record["value_ref"]))


@dataclass(frozen=True)
class CfgSummary:
    path_ids: tuple[str, ...]; phases: tuple[Literal["before_handler", "in_handler", "streaming", "after_handler"], ...]; branch_facts: tuple[str, ...]
    def __post_init__(self) -> None:
        object.__setattr__(self, "path_ids", _bounded_tuple(self.path_ids, _MAX_CFG_PATH_IDS)); object.__setattr__(self, "phases", _bounded_tuple(self.phases, _MAX_CFG_PHASES)); object.__setattr__(self, "branch_facts", _bounded_tuple(self.branch_facts, _MAX_CFG_BRANCH_FACTS))
        if not all(_id(x, "path:") for x in self.path_ids) or not _unique(self.path_ids) or not all(x in {"before_handler", "in_handler", "streaming", "after_handler"} for x in self.phases) or not all(_id(x, "fact:") for x in self.branch_facts): _fail()
    def to_dict(self) -> dict[str, object]: return {"path_ids": list(self.path_ids), "phases": list(self.phases), "branch_facts": list(self.branch_facts)}

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> CfgSummary:
        if not isinstance(record, Mapping) or set(record) != {"path_ids", "phases", "branch_facts"}:
            _fail()
        return cls(tuple(cast(list[str], record["path_ids"])), tuple(cast(list[str], record["phases"])), tuple(cast(list[str], record["branch_facts"])))


@dataclass(frozen=True)
class RegistrationFact:
    kind: Literal["spring_mvc", "servlet", "netty", "mqtt"]; location_ref: str
    def __post_init__(self) -> None:
        if self.kind not in {"spring_mvc", "servlet", "netty", "mqtt"} or not _id(self.location_ref, "excerpt:"): _fail()
    def to_dict(self) -> dict[str, object]: return self.__dict__.copy()

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> RegistrationFact:
        if not isinstance(record, Mapping) or set(record) != {"kind", "location_ref"}:
            _fail()
        return cls(cast(Literal["spring_mvc", "servlet", "netty", "mqtt"], record["kind"]), cast(str, record["location_ref"]))


@dataclass(frozen=True)
class ConfigFact:
    kind: Literal["request_limit", "timeout", "capacity", "feature_state"]; normalized_value: Literal["enabled", "disabled", "finite", "unbounded", "unknown"] | int; source_location_ref: str; config_id: str | None = None
    def __post_init__(self) -> None:
        value = self.normalized_value
        valid_value = (isinstance(value, str) and value in {"enabled", "disabled", "finite", "unbounded", "unknown"}) or (isinstance(value, int) and not isinstance(value, bool) and -_MAX_CONFIG_INTEGER <= value <= _MAX_CONFIG_INTEGER)
        if self.kind not in {"request_limit", "timeout", "capacity", "feature_state"} or not valid_value or not _id(self.source_location_ref, "excerpt:") or (self.config_id is not None and not _id(self.config_id, "config:")): _fail()
    def to_dict(self) -> dict[str, object]: return self.__dict__.copy()

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> ConfigFact:
        if not isinstance(record, Mapping) or set(record) != {"kind", "normalized_value", "source_location_ref", "config_id"}:
            _fail()
        return cls(cast(Literal["request_limit", "timeout", "capacity", "feature_state"], record["kind"]), cast(Literal["enabled", "disabled", "finite", "unbounded", "unknown"] | int, record["normalized_value"]), cast(str, record["source_location_ref"]), cast(str | None, record["config_id"]))


@dataclass(frozen=True)
class BoundedSlicePayload:
    entry_id: str; growth_id: str; source_excerpts: tuple[SourceExcerpt, ...]; static_facts: tuple[StaticFact, ...]; cfg_summary: CfgSummary; registration_facts: tuple[RegistrationFact, ...]; config_facts: tuple[ConfigFact, ...]
    def __post_init__(self) -> None:
        limits = {"source_excerpts": _MAX_SOURCE_EXCERPTS, "static_facts": _MAX_STATIC_FACTS, "registration_facts": _MAX_REGISTRATION_FACTS, "config_facts": _MAX_CONFIG_FACTS}
        for name, limit in limits.items(): object.__setattr__(self, name, _bounded_tuple(getattr(self, name), limit))
        if not all(isinstance(x, SourceExcerpt) for x in self.source_excerpts) or not all(isinstance(x, StaticFact) for x in self.static_facts) or not all(isinstance(x, RegistrationFact) for x in self.registration_facts) or not all(isinstance(x, ConfigFact) for x in self.config_facts) or not isinstance(self.cfg_summary, CfgSummary): _fail()
        refs = {x.excerpt_id for x in self.source_excerpts}; facts = {x.fact_id for x in self.static_facts}; locs = [x.location_ref for x in self.static_facts] + [x.location_ref for x in self.registration_facts] + [x.source_location_ref for x in self.config_facts]
        if not _id(self.entry_id, "entry:") or not _id(self.growth_id, "growth:") or not refs or len(refs) != len(self.source_excerpts) or len(facts) != len(self.static_facts) or not all(x in refs for x in locs) or not all(x in facts for x in self.cfg_summary.branch_facts) or not all(x.value_ref is None or x.value_ref in facts for x in self.static_facts): _fail()
        source_size = 0
        for excerpt in self.source_excerpts:
            content_bytes = _utf8_bytes_at_most(excerpt.content, 16384)
            if content_bytes is None: _fail()
            source_size += len(content_bytes)
            if source_size > _MAX_SOURCE_BYTES: _fail()
        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False).iterencode(self.to_dict())
        encoded_size = 0
        for chunk in encoder:
            encoded_size += len(chunk.encode())
            if encoded_size > _MAX_CANONICAL_PAYLOAD_BYTES: _fail()
    def to_dict(self) -> dict[str, object]: return {"entry_id": self.entry_id, "growth_id": self.growth_id, "source_excerpts": [x.to_dict() for x in self.source_excerpts], "static_facts": [x.to_dict() for x in self.static_facts], "cfg_summary": self.cfg_summary.to_dict(), "registration_facts": [x.to_dict() for x in self.registration_facts], "config_facts": [x.to_dict() for x in self.config_facts]}

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> BoundedSlicePayload:
        if not isinstance(record, Mapping) or set(record) != {"entry_id", "growth_id", "source_excerpts", "static_facts", "cfg_summary", "registration_facts", "config_facts"}:
            _fail()
        try:
            return cls(cast(str, record["entry_id"]), cast(str, record["growth_id"]), tuple(SourceExcerpt.from_dict(item) for item in cast(list[Mapping[str, object]], record["source_excerpts"])), tuple(StaticFact.from_dict(item) for item in cast(list[Mapping[str, object]], record["static_facts"])), CfgSummary.from_dict(cast(Mapping[str, object], record["cfg_summary"])), tuple(RegistrationFact.from_dict(item) for item in cast(list[Mapping[str, object]], record["registration_facts"])), tuple(ConfigFact.from_dict(item) for item in cast(list[Mapping[str, object]], record["config_facts"])))
        except (TypeError, ValueError, KeyError, AnalyzerError) as exc:
            if isinstance(exc, AnalyzerError): raise
            _fail()


@dataclass(frozen=True)
class BoundedSlice:
    slice_id: str; payload: BoundedSlicePayload
    def __post_init__(self) -> None:
        if not _id(self.slice_id, "slice:") or not isinstance(self.payload, BoundedSlicePayload): _fail()
    @property
    def entry_id(self) -> str: return self.payload.entry_id
    @property
    def growth_id(self) -> str: return self.payload.growth_id
    @property
    def normalized_payload(self) -> dict[str, object]: return self.payload.to_dict()
    @property
    def source_excerpts(self) -> tuple[SourceExcerpt, ...]: return self.payload.source_excerpts

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> BoundedSlice:
        if not isinstance(record, Mapping) or set(record) != {"slice_id", "entry_id", "growth_id", "source_excerpts", "static_facts", "cfg_summary", "registration_facts", "config_facts"}:
            _fail()
        payload_record = {field: record[field] for field in set(record) - {"slice_id"}}
        payload = BoundedSlicePayload.from_dict(payload_record)
        expected = stable_identifier("slice", payload.to_dict())
        if record["slice_id"] != expected: _fail()
        return cls(cast(str, record["slice_id"]), payload)

    def to_dict(self) -> dict[str, object]: return {"slice_id": self.slice_id, **self.payload.to_dict()}


@dataclass(frozen=True)
class AttackerInfluence:
    target: Literal["size", "key", "value", "iteration_count", "submission_count", "unknown"]; evidence_id: str
    def __post_init__(self) -> None:
        if self.target not in {"size", "key", "value", "iteration_count", "submission_count", "unknown"} or not _id(self.evidence_id, "fact:"): raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Invalid attacker influence.")
    def to_dict(self) -> dict[str, str]: return self.__dict__.copy()


@dataclass(frozen=True)
class GrowthContract:
    is_resource_growth: Literal["yes", "no", "unknown"]; growth_kind: Literal["input_materialization", "direct_allocation", "container_growth", "async_work_growth", "unknown"]; resource_dimension: Literal["entries", "bytes", "tasks", "connections", "objects", "unknown"]; attacker_influence: tuple[AttackerInfluence, ...]; resource_effect: Literal["materializes_bytes", "allocates_objects", "adds_entries", "enqueues_tasks", "opens_connections", "unknown"]; required_static_evidence: tuple[str, ...]; confidence: Literal["high", "medium", "low"]
    def __post_init__(self) -> None:
        try:
            influences = tuple(islice(iter(self.attacker_influence), 17))
            evidence = tuple(islice(iter(self.required_static_evidence), 33))
        except (TypeError, ValueError, OverflowError, MemoryError, RecursionError) as exc:
            raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Invalid Growth Contract.") from exc
        object.__setattr__(self, "attacker_influence", influences); object.__setattr__(self, "required_static_evidence", evidence)
        if self.is_resource_growth not in {"yes", "no", "unknown"} or self.growth_kind not in {"input_materialization", "direct_allocation", "container_growth", "async_work_growth", "unknown"} or self.resource_dimension not in {"entries", "bytes", "tasks", "connections", "objects", "unknown"} or self.resource_effect not in {"materializes_bytes", "allocates_objects", "adds_entries", "enqueues_tasks", "opens_connections", "unknown"} or self.confidence not in {"high", "medium", "low"} or len(self.attacker_influence) > 16 or not all(isinstance(x, AttackerInfluence) for x in self.attacker_influence) or len(self.required_static_evidence) > 32 or not all(_id(x, "fact:") for x in self.required_static_evidence): raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Invalid Growth Contract.")
    def to_dict(self) -> dict[str, object]: return {"is_resource_growth": self.is_resource_growth, "growth_kind": self.growth_kind, "resource_dimension": self.resource_dimension, "attacker_influence": [x.to_dict() for x in self.attacker_influence], "resource_effect": self.resource_effect, "required_static_evidence": list(self.required_static_evidence), "confidence": self.confidence}
