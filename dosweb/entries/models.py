from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.schemas import validate_records
from dosweb.entries.coverage import (
    registration_coverage_pattern_belongs_to_framework,
    registration_coverage_pattern_id,
    registration_coverage_pattern_ids,
)
from dosweb.errors import AnalyzerError


_FRAMEWORKS: Final = frozenset({"spring_mvc", "servlet", "netty", "mqtt", "jax_rs", "grpc"})
_PROTOCOLS: Final = frozenset({"http", "tcp", "mqtt", "grpc"})
_AUTH_CONTEXTS: Final = frozenset(
    {"unauthenticated", "low_privilege", "privileged", "unknown"}
)
_MATERIALIZATION_PHASES: Final = frozenset(
    {"before_handler", "in_handler", "streaming", "unknown"}
)
_INPUT_KINDS: Final = frozenset(
    {
        "request_body",
        "request_parameter",
        "model_attribute",
        "path_parameter",
        "header",
        "message_payload",
        "stream",
        "unknown",
    }
)
_REGISTRATION_KINDS: Final = frozenset(
    {
        "annotation_mapping",
        "static_registration",
        "pipeline_registration",
        "subscription_registration",
        "broker_registration",
    }
)
_FRAMEWORK_PROTOCOLS: Final = {
    "spring_mvc": "http",
    "servlet": "http",
    "netty": "tcp",
    "mqtt": "mqtt",
    "jax_rs": "http",
    "grpc": "grpc",
}
_FRAMEWORK_REGISTRATIONS: Final = {
    "spring_mvc": frozenset({"annotation_mapping", "static_registration"}),
    "servlet": frozenset({"annotation_mapping", "static_registration"}),
    "netty": frozenset({"pipeline_registration"}),
    "mqtt": frozenset({"subscription_registration", "broker_registration"}),
    "jax_rs": frozenset({"annotation_mapping", "static_registration"}),
    "grpc": frozenset({"static_registration"}),
}
_COVERAGE_STATUSES: Final = frozenset({"complete", "partial", "unsupported"})
_COVERAGE_EFFECTS: Final = frozenset({"none", "forces_unknown"})
_MAX_STRING_BYTES: Final = 65536
_HTTP_METHODS: Final = frozenset(
    {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE", "CONNECT"}
)

_RAW_FIELDS: Final = frozenset(
    {
        "framework",
        "protocol",
        "handler_fqn",
        "handler_file",
        "handler_start_line",
        "registration_kind",
        "registration_fqn",
        "registration_file",
        "registration_start_line",
        "route_or_event",
        "auth_context",
        "attacker_input_name",
        "attacker_input_type",
        "attacker_input_kind",
        "materialization_phase",
        "coverage_status",
        "coverage_note",
    }
)
_PROVENANCE_FIELDS: Final = frozenset(
    {"query_name", "query_sha256", "handler_location", "registration_location"}
)


def _entry_invalid(reason: str, *, field: str | None = None) -> AnalyzerError:
    details: dict[str, object] = {"reason": reason[:128]}
    if field is not None:
        details["field"] = field[:128]
    return AnalyzerError(
        "ANALYSIS_ENTRY_INVALID",
        "Entry fact violates the registered-entry contract.",
        details,
    )


def _coverage_invalid(reason: str, *, field: str | None = None) -> AnalyzerError:
    details: dict[str, object] = {"reason": reason[:128]}
    if field is not None:
        details["field"] = field[:128]
    return AnalyzerError(
        "COVERAGE_ENTRY_INVALID",
        "Framework entry coverage is inconsistent.",
        details,
    )


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise _entry_invalid("STRING_REQUIRED", field=field)
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise _entry_invalid("STRING_INVALID", field=field) from exc
    if size > _MAX_STRING_BYTES:
        raise _entry_invalid("STRING_LIMIT", field=field)
    return value


def _positive_line(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _entry_invalid("POSITIVE_LINE_REQUIRED", field=field)
    return value


def _enum(value: object, allowed: frozenset[str], field: str) -> str:
    normalized = _nonempty_string(value, field)
    if normalized not in allowed:
        raise _entry_invalid("ENUM_INVALID", field=field)
    return normalized


def _source_path(value: object, field: str) -> str:
    normalized = _nonempty_string(value, field).replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise _entry_invalid("PATH_INVALID", field=field)
    return path.as_posix()


def canonical_route(value: object, framework: str) -> str:
    route = _nonempty_string(value, "route_or_event")
    if framework in {"spring_mvc", "servlet", "jax_rs"}:
        head, separator, path = route.partition(" ")
        method = head.upper() if separator and head.upper() in _HTTP_METHODS else ""
        raw_path = path if method else route
        parts = [part for part in raw_path.replace("\\", "/").split("/") if part]
        normalized = "/" + "/".join(parts) if parts else "/"
        return f"{method} {normalized}" if method else normalized
    if framework == "netty":
        head, separator, path = route.partition(" ")
        if separator and head.upper() in _HTTP_METHODS and path.startswith("/"):
            parts = [part for part in path.replace("\\", "/").split("/") if part]
            return head.upper() + " /" + "/".join(parts) if parts else head.upper() + " /"
    return route


@dataclass(frozen=True, order=True)
class HandlerFact:
    callable: str
    file: str
    start_line: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "callable", _nonempty_string(self.callable, "handler.callable"))
        object.__setattr__(self, "file", _source_path(self.file, "handler.file"))
        object.__setattr__(self, "start_line", _positive_line(self.start_line, "handler.start_line"))

    def to_dict(self) -> dict[str, object]:
        return {"callable": self.callable, "file": self.file, "start_line": self.start_line}


@dataclass(frozen=True, order=True)
class RegistrationFact:
    kind: str
    callable: str
    file: str
    start_line: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(self.kind, _REGISTRATION_KINDS, "registration.kind"))
        object.__setattr__(self, "callable", _nonempty_string(self.callable, "registration.callable"))
        object.__setattr__(self, "file", _source_path(self.file, "registration.file"))
        object.__setattr__(self, "start_line", _positive_line(self.start_line, "registration.start_line"))

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "callable": self.callable,
            "file": self.file,
            "start_line": self.start_line,
        }


@dataclass(frozen=True, order=True)
class AttackerInputFact:
    name: str
    type: str
    kind: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty_string(self.name, "attacker_input.name"))
        object.__setattr__(self, "type", _nonempty_string(self.type, "attacker_input.type"))
        object.__setattr__(self, "kind", _enum(self.kind, _INPUT_KINDS, "attacker_input.kind"))

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "type": self.type, "kind": self.kind}


@dataclass(frozen=True)
class EntryFact:
    entry_id: str
    framework: str
    protocol: str
    handler: HandlerFact
    registration: RegistrationFact
    registration_pattern_id: str
    route_or_event: str
    auth_context: str
    attacker_inputs: tuple[AttackerInputFact, ...]
    materialization_phase: str

    def __post_init__(self) -> None:
        framework = _enum(self.framework, _FRAMEWORKS, "framework")
        protocol = _enum(self.protocol, _PROTOCOLS, "protocol")
        auth_context = _enum(self.auth_context, _AUTH_CONTEXTS, "auth_context")
        if protocol != _FRAMEWORK_PROTOCOLS[framework]:
            raise _entry_invalid("PROTOCOL_NOT_MODELED_FOR_FRAMEWORK", field="protocol")
        phase = _enum(
            self.materialization_phase, _MATERIALIZATION_PHASES, "materialization_phase"
        )
        if not isinstance(self.handler, HandlerFact) or not isinstance(
            self.registration, RegistrationFact
        ):
            raise _entry_invalid("NESTED_FACT_INVALID")
        if self.registration.kind not in _FRAMEWORK_REGISTRATIONS[framework]:
            raise _entry_invalid("REGISTRATION_NOT_MODELED_FOR_FRAMEWORK", field="registration_kind")
        pattern_id = _nonempty_string(
            self.registration_pattern_id, "registration_pattern_id"
        )
        if pattern_id not in registration_coverage_pattern_ids(
            framework, self.registration.kind
        ):
            raise _coverage_invalid(
                "REGISTRATION_PATTERN_UNMODELED", field="registration_pattern_id"
            )
        if not isinstance(self.attacker_inputs, tuple) or not self.attacker_inputs or not all(
            isinstance(item, AttackerInputFact) for item in self.attacker_inputs
        ):
            raise _entry_invalid("ATTACKER_INPUT_REQUIRED", field="attacker_inputs")
        inputs = tuple(sorted(set(self.attacker_inputs)))
        route = canonical_route(self.route_or_event, framework)
        object.__setattr__(self, "framework", framework)
        object.__setattr__(self, "protocol", protocol)
        object.__setattr__(self, "registration_pattern_id", pattern_id)
        object.__setattr__(self, "route_or_event", route)
        object.__setattr__(self, "auth_context", auth_context)
        object.__setattr__(self, "attacker_inputs", inputs)
        object.__setattr__(self, "materialization_phase", phase)
        expected = stable_identifier("entry", self.semantic_identity())
        if self.entry_id != expected:
            raise _entry_invalid("ENTRY_ID_MISMATCH", field="entry_id")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object]) -> EntryFact:
        if not isinstance(raw, Mapping):
            raise _entry_invalid("ROW_NOT_MAPPING")
        fields = set(raw)
        missing = _RAW_FIELDS - fields
        extra = fields - _RAW_FIELDS - _PROVENANCE_FIELDS
        if missing or extra:
            field = sorted(missing or extra)[0]
            raise _entry_invalid("ROW_FIELDS_INVALID", field=field)
        registration_kind = raw["registration_kind"]
        if registration_kind == "dynamic_unresolved":
            raise _entry_invalid("UNRESOLVED_REGISTRATION", field="registration_kind")
        if raw["coverage_status"] != "complete":
            raise _entry_invalid("ENTRY_COVERAGE_INCOMPLETE", field="coverage_status")
        framework = _enum(raw["framework"], _FRAMEWORKS, "framework")
        protocol = _enum(raw["protocol"], _PROTOCOLS, "protocol")
        if protocol != _FRAMEWORK_PROTOCOLS[framework]:
            raise _entry_invalid(
                "PROTOCOL_NOT_MODELED_FOR_FRAMEWORK", field="protocol"
            )
        handler = HandlerFact(
            _nonempty_string(raw["handler_fqn"], "handler_fqn"),
            _source_path(raw["handler_file"], "handler_file"),
            _positive_line(raw["handler_start_line"], "handler_start_line"),
        )
        registration = RegistrationFact(
            _nonempty_string(registration_kind, "registration_kind"),
            _nonempty_string(raw["registration_fqn"], "registration_fqn"),
            _source_path(raw["registration_file"], "registration_file"),
            _positive_line(raw["registration_start_line"], "registration_start_line"),
        )
        if registration.kind not in _FRAMEWORK_REGISTRATIONS[framework]:
            raise _entry_invalid(
                "REGISTRATION_NOT_MODELED_FOR_FRAMEWORK",
                field="registration_kind",
            )
        coverage_note = _nonempty_string(raw["coverage_note"], "coverage_note")
        pattern_id = registration_coverage_pattern_id(
            framework, registration.kind, coverage_note
        )
        if pattern_id is None:
            raise _coverage_invalid(
                "REGISTRATION_PATTERN_UNMODELED", field="coverage_note"
            )
        attacker_input = AttackerInputFact(
            _nonempty_string(raw["attacker_input_name"], "attacker_input_name"),
            _nonempty_string(raw["attacker_input_type"], "attacker_input_type"),
            _nonempty_string(raw["attacker_input_kind"], "attacker_input_kind"),
        )
        provisional = cls.__new__(cls)
        object.__setattr__(provisional, "entry_id", "")
        object.__setattr__(provisional, "framework", framework)
        object.__setattr__(provisional, "protocol", protocol)
        object.__setattr__(provisional, "handler", handler)
        object.__setattr__(provisional, "registration", registration)
        object.__setattr__(provisional, "registration_pattern_id", pattern_id)
        object.__setattr__(provisional, "route_or_event", canonical_route(raw["route_or_event"], framework))
        object.__setattr__(provisional, "auth_context", _enum(raw["auth_context"], _AUTH_CONTEXTS, "auth_context"))
        object.__setattr__(provisional, "attacker_inputs", (attacker_input,))
        object.__setattr__(
            provisional,
            "materialization_phase",
            _enum(raw["materialization_phase"], _MATERIALIZATION_PHASES, "materialization_phase"),
        )
        identity = provisional.semantic_identity()
        return cls(
            entry_id=stable_identifier("entry", identity),
            framework=provisional.framework,
            protocol=provisional.protocol,
            handler=handler,
            registration=registration,
            registration_pattern_id=pattern_id,
            route_or_event=provisional.route_or_event,
            auth_context=provisional.auth_context,
            attacker_inputs=(attacker_input,),
            materialization_phase=provisional.materialization_phase,
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> EntryFact:
        expected_fields = {
            "entry_id",
            "framework",
            "protocol",
            "handler",
            "registration",
            "registration_pattern_id",
            "route_or_event",
            "auth_context",
            "attacker_inputs",
            "materialization_phase",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected_fields:
            raise _entry_invalid("RECORD_FIELDS_INVALID")

        handler_raw = raw["handler"]
        if not isinstance(handler_raw, Mapping) or set(handler_raw) != {
            "callable",
            "file",
            "start_line",
        }:
            raise _entry_invalid("NESTED_FACT_INVALID", field="handler")
        registration_raw = raw["registration"]
        if not isinstance(registration_raw, Mapping) or set(registration_raw) != {
            "kind",
            "callable",
            "file",
            "start_line",
        }:
            raise _entry_invalid("NESTED_FACT_INVALID", field="registration")
        inputs_raw = raw["attacker_inputs"]
        if not isinstance(inputs_raw, list) or not inputs_raw or len(inputs_raw) > 64:
            raise _entry_invalid("ATTACKER_INPUT_REQUIRED", field="attacker_inputs")

        attacker_inputs: list[AttackerInputFact] = []
        for item in inputs_raw:
            if not isinstance(item, Mapping) or set(item) != {"name", "type", "kind"}:
                raise _entry_invalid("NESTED_FACT_INVALID", field="attacker_inputs")
            attacker_inputs.append(
                AttackerInputFact(
                    item["name"],
                    item["type"],
                    item["kind"],
                )
            )

        return cls(
            entry_id=_nonempty_string(raw["entry_id"], "entry_id"),
            framework=raw["framework"],
            protocol=raw["protocol"],
            handler=HandlerFact(
                handler_raw["callable"],
                handler_raw["file"],
                handler_raw["start_line"],
            ),
            registration=RegistrationFact(
                registration_raw["kind"],
                registration_raw["callable"],
                registration_raw["file"],
                registration_raw["start_line"],
            ),
            registration_pattern_id=raw["registration_pattern_id"],
            route_or_event=raw["route_or_event"],
            auth_context=raw["auth_context"],
            attacker_inputs=tuple(attacker_inputs),
            materialization_phase=raw["materialization_phase"],
        )

    @classmethod
    def create(
        cls,
        *,
        framework: str,
        protocol: str,
        handler: HandlerFact,
        registration: RegistrationFact,
        registration_pattern_id: str,
        route_or_event: str,
        auth_context: str,
        attacker_inputs: tuple[AttackerInputFact, ...],
        materialization_phase: str,
    ) -> EntryFact:
        if not isinstance(handler, HandlerFact) or not isinstance(
            registration, RegistrationFact
        ):
            raise _entry_invalid("NESTED_FACT_INVALID")
        if not isinstance(attacker_inputs, tuple) or not attacker_inputs or not all(
            isinstance(item, AttackerInputFact) for item in attacker_inputs
        ):
            raise _entry_invalid("ATTACKER_INPUT_REQUIRED", field="attacker_inputs")
        identity = {
            "framework": framework,
            "protocol": protocol,
            "handler": handler.to_dict(),
            "registration": registration.to_dict(),
            "registration_pattern_id": registration_pattern_id,
            "route_or_event": canonical_route(route_or_event, framework),
            "auth_context": auth_context,
            "attacker_inputs": [item.to_dict() for item in sorted(set(attacker_inputs))],
            "materialization_phase": materialization_phase,
        }
        return cls(entry_id=stable_identifier("entry", identity), **{
            "framework": framework,
            "protocol": protocol,
            "handler": handler,
            "registration": registration,
            "registration_pattern_id": registration_pattern_id,
            "route_or_event": route_or_event,
            "auth_context": auth_context,
            "attacker_inputs": attacker_inputs,
            "materialization_phase": materialization_phase,
        })

    def semantic_identity(self) -> dict[str, object]:
        return {
            "framework": self.framework,
            "protocol": self.protocol,
            "handler": self.handler.to_dict(),
            "registration": self.registration.to_dict(),
            "registration_pattern_id": self.registration_pattern_id,
            "route_or_event": self.route_or_event,
            "auth_context": self.auth_context,
            "attacker_inputs": [item.to_dict() for item in self.attacker_inputs],
            "materialization_phase": self.materialization_phase,
        }

    def to_dict(self) -> dict[str, object]:
        return {"entry_id": self.entry_id, **self.semantic_identity()}


def load_entry_facts(path: Path) -> tuple[EntryFact, ...]:
    records = read_jsonl_strict(path, "entry_facts")
    validate_records("entry_facts", records)
    facts = tuple(EntryFact.from_dict(record) for record in records)
    if len({fact.entry_id for fact in facts}) != len(facts):
        raise _entry_invalid("DUPLICATE_ENTRY_ID", field="entry_id")
    return facts


@dataclass(frozen=True)
class FrameworkCoverage:
    framework: str
    status: Literal["complete", "partial", "unsupported"]
    supported_patterns: tuple[str, ...]
    unsupported_patterns: tuple[str, ...]
    effect_on_verdict: Literal["none", "forces_unknown"]

    def __post_init__(self) -> None:
        if not isinstance(self.framework, str) or self.framework not in _FRAMEWORKS:
            raise _coverage_invalid("FRAMEWORK_INVALID", field="framework")
        if not isinstance(self.status, str) or self.status not in _COVERAGE_STATUSES:
            raise _coverage_invalid("STATUS_INVALID", field="status")
        if (
            not isinstance(self.effect_on_verdict, str)
            or self.effect_on_verdict not in _COVERAGE_EFFECTS
        ):
            raise _coverage_invalid("EFFECT_INVALID", field="effect_on_verdict")
        supported = _coverage_patterns(self.supported_patterns, "supported_patterns")
        unsupported = _coverage_patterns(self.unsupported_patterns, "unsupported_patterns")
        expected_effect = "none" if self.status == "complete" else "forces_unknown"
        if self.effect_on_verdict != expected_effect:
            raise _coverage_invalid("EFFECT_STATUS_MISMATCH", field="effect_on_verdict")
        if set(supported) & set(unsupported):
            raise _coverage_invalid("PATTERN_OVERLAP", field="unsupported_patterns")
        if self.status == "complete" and unsupported:
            raise _coverage_invalid("COMPLETE_HAS_GAPS", field="unsupported_patterns")
        if self.status != "complete" and not unsupported:
            raise _coverage_invalid("GAP_PATTERN_REQUIRED", field="unsupported_patterns")
        if any(
            not registration_coverage_pattern_belongs_to_framework(
                self.framework, pattern_id
            )
            for pattern_id in supported
        ):
            raise _coverage_invalid(
                "SUPPORTED_PATTERN_ID_INVALID", field="supported_patterns"
            )
        object.__setattr__(self, "supported_patterns", supported)
        object.__setattr__(self, "unsupported_patterns", unsupported)

    def to_dict(self) -> dict[str, object]:
        return {
            "framework": self.framework,
            "status": self.status,
            "supported_patterns": list(self.supported_patterns),
            "unsupported_patterns": list(self.unsupported_patterns),
            "effect_on_verdict": self.effect_on_verdict,
        }


def _coverage_patterns(values: object, field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise _coverage_invalid("PATTERNS_NOT_TUPLE", field=field)
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise _coverage_invalid("PATTERN_INVALID", field=field)
        try:
            if len(value.encode("utf-8")) > _MAX_STRING_BYTES:
                raise _coverage_invalid("PATTERN_LIMIT", field=field)
        except UnicodeEncodeError as exc:
            raise _coverage_invalid("PATTERN_INVALID", field=field) from exc
        normalized.append(value)
    return tuple(sorted(set(normalized)))


__all__ = [
    "AttackerInputFact",
    "EntryFact",
    "FrameworkCoverage",
    "HandlerFact",
    "RegistrationFact",
    "canonical_route",
]
