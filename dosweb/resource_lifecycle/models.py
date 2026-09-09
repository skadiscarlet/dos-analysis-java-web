from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re
from typing import Final, Literal


SCHEMA_VERSION: Final = "1.1"
SOURCE_KINDS: Final = frozenset({"static_verified", "trusted_contract", "llm_proposed", "manual_fixture"})
RELATION_SOURCE_KINDS: Final = frozenset(
    {"static_verified", "trusted_contract", "manual_fixture"}
)
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
class ProgramPoint:
    point_id: str
    callable: str
    kind: Literal["entry", "effect", "call", "return", "task_submit", "task_start", "task_exit"]
    location: SourceLocation

    def __post_init__(self) -> None:
        _identifier(self.point_id, "program point identifier")
        _identifier(self.callable, "program point callable")
        if self.kind not in {
            "entry",
            "effect",
            "call",
            "return",
            "task_submit",
            "task_start",
            "task_exit",
        }:
            raise ValueError("program point kind is invalid")


@dataclass(frozen=True)
class CallBinding:
    binding_id: str
    source_point_id: str
    target_point_id: str
    caller_callable: str
    callee_callable: str
    argument_index: int
    parameter_index: int
    instance_id: str
    context_depth: int
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.binding_id, "call binding identifier"),
            (self.source_point_id, "call binding source point"),
            (self.target_point_id, "call binding target point"),
            (self.caller_callable, "call binding caller"),
            (self.callee_callable, "call binding callee"),
            (self.instance_id, "call binding instance"),
        ):
            _identifier(value, label)
        if (
            type(self.argument_index) is not int
            or type(self.parameter_index) is not int
            or self.argument_index < 0
            or self.parameter_index < 0
            or self.argument_index != self.parameter_index
        ):
            raise ValueError("call binding argument and parameter positions are invalid")
        if type(self.context_depth) is not int or self.context_depth not in {1, 2}:
            raise ValueError("call binding context depth is unsupported")
        if not self.evidence_ids or any(not isinstance(item, str) or not item for item in self.evidence_ids):
            raise ValueError("call binding requires evidence identifiers")


@dataclass(frozen=True)
class TaskBinding:
    binding_id: str
    task_id: str
    instance_id: str
    holder_id: str
    executor_contract_id: str
    queued_event_id: str
    run_event_id: str
    normal_exit_event_id: str
    exceptional_exit_event_id: str
    task_callable: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.binding_id, "task binding identifier"),
            (self.task_id, "task identifier"),
            (self.instance_id, "task binding instance"),
            (self.holder_id, "task binding holder"),
            (self.executor_contract_id, "task executor contract"),
            (self.queued_event_id, "task queued event"),
            (self.run_event_id, "task run event"),
            (self.normal_exit_event_id, "task normal exit event"),
            (self.exceptional_exit_event_id, "task exceptional exit event"),
            (self.task_callable, "task callable"),
        ):
            _identifier(value, label)
        if self.normal_exit_event_id == self.exceptional_exit_event_id:
            raise ValueError("task normal and exceptional exits must be distinct")
        if not self.evidence_ids or any(not isinstance(item, str) or not item for item in self.evidence_ids):
            raise ValueError("task binding requires evidence identifiers")


@dataclass(frozen=True)
class TaskExit:
    exit_id: str
    task_id: str
    point_id: str
    event_id: str
    task_callable: str
    kind: Literal["normal", "exceptional"]
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.exit_id, "task exit identifier"),
            (self.task_id, "task exit task"),
            (self.point_id, "task exit program point"),
            (self.event_id, "task exit event"),
            (self.task_callable, "task exit callable"),
        ):
            _identifier(value, label)
        if self.kind not in {"normal", "exceptional"}:
            raise ValueError("task exit kind is invalid")
        if not self.evidence_ids or any(
            not isinstance(item, str) or not item for item in self.evidence_ids
        ):
            raise ValueError("task exit requires evidence identifiers")


@dataclass(frozen=True)
class PopulationEffect:
    effect_id: str
    kind: Literal[
        "direct_accept",
        "enqueue",
        "assign_slot",
        "start",
        "terminate",
        "reject",
        "cancel_queued",
        "cancel_active",
    ]
    executor_id: str
    task_id: str
    guard: str
    queue_delta: int
    active_delta: int
    source_phase: Literal["absent", "queued", "reserved", "running"]
    target_phase: Literal["queued", "reserved", "running", "terminated", "rejected", "cancelled"]
    location: SourceLocation
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.effect_id, "population effect identifier"),
            (self.executor_id, "population executor identifier"),
            (self.task_id, "population task identifier"),
            (self.guard, "population guard"),
        ):
            _identifier(value, label)
        expected = {
            "direct_accept": ((0, 1), {("absent", "reserved")}),
            "enqueue": ((1, 0), {("absent", "queued")}),
            "assign_slot": ((-1, 1), {("queued", "reserved")}),
            "start": ((0, 0), {("reserved", "running")}),
            "terminate": ((0, -1), {("running", "terminated")}),
            "reject": ((0, 0), {("absent", "rejected")}),
            "cancel_queued": ((-1, 0), {("queued", "cancelled")}),
            "cancel_active": ((0, -1), {("reserved", "cancelled"), ("running", "cancelled")}),
        }
        if self.kind not in expected:
            raise ValueError("population effect kind is invalid")
        deltas, phase_pairs = expected[self.kind]
        if (
            type(self.queue_delta) is not int
            or type(self.active_delta) is not int
            or (self.queue_delta, self.active_delta) != deltas
            or (self.source_phase, self.target_phase) not in phase_pairs
        ):
            raise ValueError("population deltas or phases are invalid")
        if not self.evidence_ids or any(not isinstance(item, str) or not item for item in self.evidence_ids):
            raise ValueError("population effect requires evidence identifiers")


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
    population_effects: tuple[PopulationEffect, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.transition_id, "transition_id")
        _identifier(self.source_event_id, "source_event_id")
        _identifier(self.target_event_id, "target_event_id")
        _identifier(self.guard, "transition guard")
        if self.exit_kind not in EXIT_KINDS:
            raise ValueError("transition exit kind is invalid")
        if any(not isinstance(item, str) or not item for item in self.assumptions):
            raise ValueError("transition assumptions are invalid")
        if not isinstance(self.population_effects, tuple):
            raise ValueError("transition population effects must be a tuple")
        _unique_identifiers(self.population_effects, "effect_id", "population effect")


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
    program_points: tuple[ProgramPoint, ...] = ()
    call_bindings: tuple[CallBinding, ...] = ()
    task_bindings: tuple[TaskBinding, ...] = ()
    task_exits: tuple[TaskExit, ...] = ()

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
        if any(
            not isinstance(items, tuple)
            for items in (
                self.program_points,
                self.call_bindings,
                self.task_bindings,
                self.task_exits,
            )
        ):
            raise ValueError("program relation collections must be tuples")
        family_ids = _unique_identifiers(self.families, "family_id", "family")
        if any(item[1] not in family_ids for item in self.coverage_gaps):
            raise ValueError("coverage gap references an unknown resource family")
        instance_ids = _unique_identifiers(self.instances, "instance_id", "instance")
        holder_ids = _unique_identifiers(self.holders, "holder_id", "holder")
        event_ids = _unique_identifiers(self.events, "event_id", "event")
        point_ids = _unique_identifiers(self.program_points, "point_id", "program point")
        call_binding_ids = _unique_identifiers(
            self.call_bindings, "binding_id", "call binding"
        )
        task_binding_ids = _unique_identifiers(
            self.task_bindings, "binding_id", "task binding"
        )
        task_ids = _unique_identifiers(self.task_bindings, "task_id", "task")
        task_exit_ids = _unique_identifiers(self.task_exits, "exit_id", "task exit")
        relation_ids = point_ids | call_binding_ids | task_binding_ids | task_exit_ids
        if len(relation_ids) != sum(
            map(len, (point_ids, call_binding_ids, task_binding_ids, task_exit_ids))
        ):
            raise ValueError("duplicate relation identifier")
        _unique_identifiers(self.transitions, "transition_id", "transition")
        population_effects = tuple(
            effect
            for transition in self.transitions
            for effect in transition.population_effects
        )
        _unique_identifiers(population_effects, "effect_id", "population effect")
        if (
            len(self.families) > 4096
            or len(self.instances) > 16384
            or len(self.holders) > 16384
            or len(self.events) > 16384
            or len(self.transitions) > 65536
            or len(self.program_points) > 65536
            or len(self.call_bindings) > 65536
            or len(self.task_bindings) > 16384
            or len(self.task_exits) > 32768
            or any(len(transition.effects) > 256 for transition in self.transitions)
            or any(len(transition.population_effects) > 16 for transition in self.transitions)
        ):
            raise ValueError("program exceeds structural analysis limits")
        if not self.entry_event_ids or not set(self.entry_event_ids) <= event_ids:
            raise ValueError("entry event reference is invalid")
        if not self.exit_event_ids or not set(self.exit_event_ids) <= event_ids:
            raise ValueError("exit event reference is invalid")
        for instance in self.instances:
            if instance.family_id not in family_ids:
                raise ValueError("instance family reference is invalid")
        points = {item.point_id: item for item in self.program_points}
        if any(
            point.location.source_kind not in RELATION_SOURCE_KINDS
            for point in self.program_points
        ):
            raise ValueError("program point requires a trusted source kind")
        for binding in self.call_bindings:
            if binding.source_point_id not in point_ids or binding.target_point_id not in point_ids:
                raise ValueError("call binding references an unknown program point")
            if (
                points[binding.source_point_id].callable != binding.caller_callable
                or points[binding.target_point_id].callable != binding.callee_callable
            ):
                raise ValueError("call binding callable and program point are inconsistent")
            if binding.instance_id not in instance_ids:
                raise ValueError("call binding references an unknown instance")
        holders = {item.holder_id: item for item in self.holders}
        events = {item.event_id: item for item in self.events}
        tasks = {item.task_id: item for item in self.task_bindings}
        for binding in self.task_bindings:
            if binding.instance_id not in instance_ids:
                raise ValueError("task binding references an unknown instance")
            if binding.holder_id not in holder_ids or holders[binding.holder_id].kind != "task":
                raise ValueError("task binding references an invalid task holder")
            if not {
                binding.queued_event_id,
                binding.run_event_id,
                binding.normal_exit_event_id,
                binding.exceptional_exit_event_id,
            } <= event_ids:
                raise ValueError("task binding event reference is invalid")
            if (
                events[binding.queued_event_id].kind != "task_queue"
                or events[binding.run_event_id].kind != "task_run"
                or events[binding.normal_exit_event_id].kind != "task_exit"
                or events[binding.exceptional_exit_event_id].kind != "task_exit"
            ):
                raise ValueError("task binding event kind is invalid")
        exits_by_task: dict[str, dict[str, TaskExit]] = {}
        for task_exit in self.task_exits:
            binding = tasks.get(task_exit.task_id)
            if binding is None:
                raise ValueError("task exit references an unknown task")
            point = points.get(task_exit.point_id)
            if point is None or point.kind != "task_exit":
                raise ValueError("task exit references an invalid program point")
            event = events.get(task_exit.event_id)
            if event is None or event.kind != "task_exit":
                raise ValueError("task exit references an invalid event")
            if (
                task_exit.task_callable != binding.task_callable
                or point.callable != binding.task_callable
            ):
                raise ValueError("task exit callable is inconsistent")
            exits = exits_by_task.setdefault(task_exit.task_id, {})
            if task_exit.kind in exits:
                raise ValueError("duplicate task exit kind")
            exits[task_exit.kind] = task_exit
        for binding in self.task_bindings:
            exits = exits_by_task.get(binding.task_id, {})
            if set(exits) != {"normal", "exceptional"}:
                raise ValueError("task binding requires normal and exceptional task exits")
            if (
                exits["normal"].event_id != binding.normal_exit_event_id
                or exits["exceptional"].event_id
                != binding.exceptional_exit_event_id
            ):
                raise ValueError("task binding and task exits are inconsistent")
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
            for effect in transition.population_effects:
                if effect.task_id not in task_ids:
                    raise ValueError("population effect references an unknown task")
                if effect.executor_id != tasks[effect.task_id].executor_contract_id:
                    raise ValueError("population effect executor reference is invalid")
                if effect.location.source_kind not in RELATION_SOURCE_KINDS:
                    raise ValueError("population effect requires a trusted source kind")
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
    instance_obligation_counts: tuple[tuple[str, CountInterval], ...] = ()
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
