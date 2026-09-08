from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re
from typing import Final, Literal


SCHEMA_VERSION: Final = "1.0"
SOURCE_KINDS: Final = frozenset({"static_verified", "trusted_contract", "llm_proposed", "manual_fixture"})
EFFECT_KINDS: Final = frozenset({"create", "retain", "drop", "release", "dispatch", "unknown_call"})
EXIT_KINDS: Final = frozenset({"normal", "exceptional", "rejected", "cancelled", "internal"})
RESOURCE_DIMENSIONS: Final = frozenset({"held_instances", "item_size_bytes", "close_obligation"})
LIFECYCLE_STATUSES: Final = frozenset({"bounded", "obligation_gap", "unknown", "not_applicable"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 512:
        raise ValueError(f"{field_name} must be a non-empty bounded string")


def _unique_identifiers(values: tuple[object, ...], attribute: str, label: str) -> set[str]:
    output = {str(getattr(value, attribute)) for value in values}
    if len(output) != len(values):
        raise ValueError(f"duplicate {label} identifier")
    return output


@dataclass(frozen=True)
class SourceLocation:
    path: str
    start_line: int
    end_line: int
    source_sha256: str
    extractor_version: str
    source_kind: Literal["static_verified", "trusted_contract", "llm_proposed", "manual_fixture"]

    def __post_init__(self) -> None:
        path = PurePosixPath(self.path)
        if not self.path or path.is_absolute() or ".." in path.parts or "\\" in self.path:
            raise ValueError("source path must be a safe relative POSIX path")
        if (
            type(self.start_line) is not int
            or type(self.end_line) is not int
            or self.start_line < 1
            or self.end_line < self.start_line
        ):
            raise ValueError("source line range is invalid")
        if not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        _identifier(self.extractor_version, "extractor_version")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError("source_kind is invalid")


@dataclass(frozen=True)
class ResourceFamily:
    family_id: str
    allocation: SourceLocation
    context: tuple[str, ...]
    resource_type: str
    requires_close: bool
    item_size_upper: int | None = None

    def __post_init__(self) -> None:
        _identifier(self.family_id, "family_id")
        _identifier(self.resource_type, "resource_type")
        if not isinstance(self.requires_close, bool):
            raise ValueError("requires_close must be boolean")
        if not self.context or any(not isinstance(item, str) or not item for item in self.context):
            raise ValueError("resource context must be non-empty")
        if self.item_size_upper is not None and (isinstance(self.item_size_upper, bool) or self.item_size_upper < 0):
            raise ValueError("item_size_upper must be a non-negative integer")


@dataclass(frozen=True)
class AbstractInstance:
    instance_id: str
    family_id: str
    abstraction: Literal["recent", "summary"]
    identity_confidence: Literal["exact", "family", "unknown"]

    def __post_init__(self) -> None:
        _identifier(self.instance_id, "instance_id")
        _identifier(self.family_id, "family_id")
        if self.abstraction not in {"recent", "summary"}:
            raise ValueError("instance abstraction is invalid")
        if self.identity_confidence not in {"exact", "family", "unknown"}:
            raise ValueError("identity_confidence is invalid")
        if self.abstraction == "summary" and self.identity_confidence == "exact":
            raise ValueError("summary instance cannot have exact identity")


@dataclass(frozen=True)
class Holder:
    holder_id: str
    kind: Literal["request_stack", "task", "container", "field", "local"]
    scope: Literal["request", "task", "session", "connection", "instance", "global"]
    identity_precision: Literal["exact", "family", "unknown"]

    def __post_init__(self) -> None:
        _identifier(self.holder_id, "holder_id")
        if self.kind not in {"request_stack", "task", "container", "field", "local"}:
            raise ValueError("holder kind is invalid")
        if self.scope not in {"request", "task", "session", "connection", "instance", "global"}:
            raise ValueError("holder scope is invalid")
        if self.identity_precision not in {"exact", "family", "unknown"}:
            raise ValueError("holder identity precision is invalid")


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: Literal["request", "request_exit", "method", "task_submit", "task_queue", "task_run", "task_exit"]
    callable: str
    activation_condition: str

    def __post_init__(self) -> None:
        _identifier(self.event_id, "event_id")
        if self.kind not in {"request", "request_exit", "method", "task_submit", "task_queue", "task_run", "task_exit"}:
            raise ValueError("event kind is invalid")
        _identifier(self.callable, "event callable")
        _identifier(self.activation_condition, "activation_condition")


@dataclass(frozen=True)
class Effect:
    effect_id: str
    kind: Literal["create", "retain", "drop", "release", "dispatch", "unknown_call"]
    instance_id: str | None
    family_id: str | None
    holder_id: str | None
    target_event_id: str | None
    condition: str
    location: SourceLocation
    evidence_ids: tuple[str, ...]
    size_lower: int | None = None
    size_upper: int | None = None
    contract_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.effect_id, "effect_id")
        if self.kind not in EFFECT_KINDS:
            raise ValueError("effect kind is invalid")
        if self.kind != "dispatch" and self.instance_id is None:
            raise ValueError("non-dispatch effect requires instance_id")
        if self.kind in {"retain", "drop"} and self.holder_id is None:
            raise ValueError("retain/drop effect requires holder_id")
        if self.kind == "dispatch" and self.target_event_id is None:
            raise ValueError("dispatch effect requires target_event_id")
        if self.size_lower is not None and (isinstance(self.size_lower, bool) or self.size_lower < 0):
            raise ValueError("size_lower must be non-negative")
        if self.size_upper is not None and (isinstance(self.size_upper, bool) or self.size_upper < 0):
            raise ValueError("size_upper must be non-negative")
        if self.size_lower is not None and self.size_upper is not None and self.size_lower > self.size_upper:
            raise ValueError("effect size interval is invalid")
        _identifier(self.condition, "effect condition")
        if not self.evidence_ids or any(not isinstance(item, str) or not item for item in self.evidence_ids):
            raise ValueError("effect requires evidence identifiers")


@dataclass(frozen=True)
class Transition:
    transition_id: str
    source_event_id: str
    target_event_id: str
    guard: str
    effects: tuple[Effect, ...]
    exit_kind: Literal["normal", "exceptional", "rejected", "cancelled", "internal"]
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.transition_id, "transition_id")
        _identifier(self.source_event_id, "source_event_id")
        _identifier(self.target_event_id, "target_event_id")
        _identifier(self.guard, "transition guard")
        if self.exit_kind not in EXIT_KINDS:
            raise ValueError("transition exit kind is invalid")
        if any(not isinstance(item, str) or not item for item in self.assumptions):
            raise ValueError("transition assumptions are invalid")


@dataclass(frozen=True)
class Program:
    schema_version: str
    families: tuple[ResourceFamily, ...]
    instances: tuple[AbstractInstance, ...]
    holders: tuple[Holder, ...]
    events: tuple[Event, ...]
    transitions: tuple[Transition, ...]
    entry_event_ids: tuple[str, ...]
    exit_event_ids: tuple[str, ...]
    coverage_complete: bool
    contracts_version: str
    coverage_gaps: tuple[tuple[str, str, str, str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported resource lifecycle schema version")
        if not isinstance(self.coverage_complete, bool):
            raise ValueError("coverage_complete must be boolean")
        if self.coverage_complete and self.coverage_gaps:
            raise ValueError("complete coverage cannot contain dimension gaps")
        if not isinstance(self.coverage_gaps, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 5
            or item[0] not in RESOURCE_DIMENSIONS
            or not isinstance(item[1], str)
            or not item[1]
            or not isinstance(item[2], str)
            or not item[2]
            or not isinstance(item[3], str)
            or not item[3]
            or not isinstance(item[4], str)
            or not item[4]
            for item in self.coverage_gaps
        ):
            raise ValueError(
                "coverage_gaps must contain dimension, family, scope, reason, and evidence tuples"
            )
        family_ids = _unique_identifiers(self.families, "family_id", "family")
        if any(item[1] not in family_ids for item in self.coverage_gaps):
            raise ValueError("coverage gap references an unknown resource family")
        instance_ids = _unique_identifiers(self.instances, "instance_id", "instance")
        holder_ids = _unique_identifiers(self.holders, "holder_id", "holder")
        event_ids = _unique_identifiers(self.events, "event_id", "event")
        _unique_identifiers(self.transitions, "transition_id", "transition")
        if (
            len(self.families) > 4096
            or len(self.instances) > 16384
            or len(self.holders) > 16384
            or len(self.events) > 16384
            or len(self.transitions) > 65536
            or any(len(transition.effects) > 256 for transition in self.transitions)
        ):
            raise ValueError("program exceeds structural analysis limits")
        if not self.entry_event_ids or not set(self.entry_event_ids) <= event_ids:
            raise ValueError("entry event reference is invalid")
        if not self.exit_event_ids or not set(self.exit_event_ids) <= event_ids:
            raise ValueError("exit event reference is invalid")
        for instance in self.instances:
            if instance.family_id not in family_ids:
                raise ValueError("instance family reference is invalid")
        for transition in self.transitions:
            if transition.source_event_id not in event_ids or transition.target_event_id not in event_ids:
                raise ValueError("transition event reference is invalid")
            for effect in transition.effects:
                if effect.instance_id is not None and effect.instance_id not in instance_ids:
                    raise ValueError("effect instance reference is invalid")
                if effect.family_id is not None and effect.family_id not in family_ids:
                    raise ValueError("effect family reference is invalid")
                if effect.holder_id is not None and effect.holder_id not in holder_ids:
                    raise ValueError("effect holder reference is invalid")
                if effect.target_event_id is not None and effect.target_event_id not in event_ids:
                    raise ValueError("effect target event reference is invalid")
        _identifier(self.contracts_version, "contracts_version")


@dataclass(frozen=True)
class CountInterval:
    lower: int = 0
    upper: int | None = 0

    def __post_init__(self) -> None:
        if self.lower < 0 or (self.upper is not None and self.upper < self.lower):
            raise ValueError("count interval is invalid")


@dataclass(frozen=True)
class ResourceState:
    instance_families: tuple[tuple[str, str], ...]
    instance_abstractions: tuple[tuple[str, str], ...]
    instance_confidences: tuple[tuple[str, str], ...]
    family_requires_close: tuple[tuple[str, bool], ...]
    family_size_upper: tuple[tuple[str, int | None], ...]
    holder_kinds: tuple[tuple[str, str], ...]
    holder_scopes: tuple[tuple[str, str], ...]
    holder_precisions: tuple[tuple[str, str], ...]
    held_edges: frozenset[tuple[str, str]] = frozenset()
    created_instances: frozenset[str] = frozenset()
    open_obligations: frozenset[str] = frozenset()
    must_released: frozenset[str] = frozenset()
    obligation_counts: tuple[tuple[str, CountInterval], ...] = ()
    allocation_counts: tuple[tuple[str, CountInterval], ...] = ()
    held_counts: tuple[tuple[str, CountInterval], ...] = ()
    peak_held_counts: tuple[tuple[str, int | None], ...] = ()
    repeated_instances: frozenset[str] = frozenset()
    unknown_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepResult:
    state: ResourceState
    rule_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisBudget:
    max_steps: int = 1024
    max_updates_per_event: int = 32
    timeout_ms: int = 5000

    def __post_init__(self) -> None:
        if any(isinstance(item, bool) or item <= 0 for item in (self.max_steps, self.max_updates_per_event, self.timeout_ms)):
            raise ValueError("analysis budget values must be positive integers")


@dataclass(frozen=True)
class Trace:
    transition_ids: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    rule_dependencies: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AnalysisResult:
    exit_states: dict[str, ResourceState]
    event_states: dict[str, ResourceState]
    traces: dict[str, Trace]
    terminated: bool
    unknown_reasons: tuple[str, ...]
    lifecycle_statuses: tuple[str, ...]
    steps: int


@dataclass(frozen=True)
class DimensionResult:
    dimension: Literal["held_instances", "item_size_bytes", "close_obligation"]
    scope: str
    lifecycle_status: Literal["bounded", "obligation_gap", "unknown", "not_applicable"]
    upper_bound: int | str | None
    assumptions: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    impact_status: Literal["not_evaluated", "externally_documented"] = "not_evaluated"
    resource_family_id: str | None = None

    def __post_init__(self) -> None:
        if self.dimension not in RESOURCE_DIMENSIONS:
            raise ValueError("resource dimension is invalid")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError("lifecycle status is invalid")
