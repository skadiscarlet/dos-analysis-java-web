from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
import hashlib
from pathlib import Path
import re
import stat

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.invariants import InvariantCandidate, queue_result_scope
from dosweb.resource_lifecycle.io import budget_from_dict, location_from_dict, program_from_dict, program_to_dict
from dosweb.resource_lifecycle.models import (
    AbstractInstance,
    AnalysisBudget,
    Effect,
    Event,
    Holder,
    Program,
    ResourceFamily,
    SCHEMA_VERSION,
    SourceLocation,
    Transition,
)


@dataclass(frozen=True)
class RawLifecycleFact:
    fact_id: str
    unit_id: str
    site_callable: str
    fact_kind: str
    instance_key: str
    resource_type: str
    requires_close: bool
    holder_kind: str
    holder_scope: str
    holder_key: str
    target_event: str
    capacity: str
    normal_path: bool
    exceptional_path: bool
    source_evidence: str
    coverage_status: str
    coverage_note: str
    location: SourceLocation
    site_start_column: int
    site_line_sha256: str
    program_point: str
    related_point: str
    relation_depth: int
    binding_index: int
    max_workers: str
    rejection_policy: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"lifecycle-fact:[0-9a-f]{24}", self.fact_id):
            raise ValueError("raw lifecycle fact identifier is invalid")
        if self.fact_kind not in {"create", "retain", "drop", "release", "dispatch", "unknown_call", "invariant", "call_binding", "cfg_edge", "task_exit"}:
            raise ValueError("raw lifecycle fact kind is invalid")
        if self.holder_kind not in {"none", "local", "field", "queue", "task"}:
            raise ValueError("raw lifecycle holder kind is invalid")
        if self.holder_scope not in {"none", "instance", "global", "task"}:
            raise ValueError("raw lifecycle holder scope is invalid")
        expected_scopes = {
            "none": {"none"},
            "local": {"instance"},
            "field": {"instance", "global"},
            "queue": {"task"},
            "task": {"task"},
        }
        if self.holder_scope not in expected_scopes[self.holder_kind]:
            raise ValueError("raw lifecycle holder kind and scope are inconsistent")
        if self.coverage_status not in {"complete", "partial", "unsupported"}:
            raise ValueError("raw lifecycle coverage status is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.site_line_sha256):
            raise ValueError("raw lifecycle site line digest is invalid")
        if type(self.site_start_column) is not int or self.site_start_column < 1:
            raise ValueError("raw lifecycle site column is invalid")
        if type(self.relation_depth) is not int or self.relation_depth not in {0, 1, 2}:
            raise ValueError("raw lifecycle relation depth is invalid")
        if type(self.binding_index) is not int or not -1 <= self.binding_index <= 255:
            raise ValueError("raw lifecycle binding index is invalid")
        if self.rejection_policy not in {
            "abort",
            "caller_runs",
            "discard",
            "discard_oldest",
            "unknown",
        }:
            raise ValueError("raw lifecycle rejection policy is invalid")
        for value, label in (
            (self.capacity, "capacity"),
            (self.max_workers, "worker limit"),
        ):
            if re.fullmatch(r"-?[0-9]+", value) and int(value) <= 0:
                raise ValueError(f"raw lifecycle {label} must be positive")
        if self.fact_kind == "call_binding" and (
            self.relation_depth not in {1, 2}
            or self.binding_index < 0
            or self.target_event == "none"
            or self.related_point == "none"
        ):
            raise ValueError("raw lifecycle call binding is invalid")
        if self.fact_kind == "cfg_edge" and self.related_point == "none":
            raise ValueError("raw lifecycle CFG edge is invalid")
        if self.fact_kind == "dispatch" and (
            self.holder_kind != "queue"
            or self.holder_scope != "task"
            or self.holder_key == "none"
            or self.target_event == "none"
        ):
            raise ValueError("static dispatch queue identity is invalid")
        if (
            not isinstance(self.requires_close, bool)
            or not isinstance(self.normal_path, bool)
            or not isinstance(self.exceptional_path, bool)
        ):
            raise ValueError("raw lifecycle path flags must be boolean")
        for value in (
            self.unit_id,
            self.site_callable,
            self.program_point,
            self.related_point,
            self.instance_key,
            self.resource_type,
            self.holder_key,
            self.target_event,
            self.capacity,
            self.max_workers,
            self.source_evidence,
            self.coverage_note,
        ):
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 2048:
                raise ValueError("raw lifecycle fact string is invalid")


@dataclass(frozen=True)
class AnalysisUnit:
    unit_id: str
    program: Program
    invariants: tuple[InvariantCandidate, ...]
    executor_contracts: tuple[ExecutorContract, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.executor_contracts, tuple)
            or len(self.executor_contracts) > 4096
            or any(not isinstance(contract, ExecutorContract) for contract in self.executor_contracts)
        ):
            raise ValueError("executor contract collection is invalid")
        contract_ids = {contract.contract_id for contract in self.executor_contracts}
        if len(contract_ids) != len(self.executor_contracts):
            raise ValueError("duplicate executor contract identifier")
        referenced_contract_ids = {
            binding.executor_contract_id for binding in self.program.task_bindings
        }
        if not referenced_contract_ids <= contract_ids:
            raise ValueError("task binding references an unknown executor contract")


@dataclass(frozen=True)
class ExtractedFacts:
    source_kind: str
    snapshot_sha256: str
    extractor_version: str
    budget: AnalysisBudget
    units: tuple[AnalysisUnit, ...]
    facts: tuple[RawLifecycleFact, ...]
    coverage: Mapping[str, object]


_RAW_ROW_FIELDS = {
    "unit_id", "site_callable", "site_file", "site_start_line", "site_start_column",
    "program_point", "related_point", "relation_depth", "binding_index", "fact_kind", "instance_key",
    "resource_type", "requires_close", "holder_kind", "holder_scope", "holder_key", "target_event",
    "capacity", "max_workers", "rejection_policy", "normal_path", "exceptional_path", "source_evidence", "coverage_status",
    "coverage_note",
}
_LEGACY_RAW_ROW_FIELDS = _RAW_ROW_FIELDS - {
    "site_callable",
    "program_point",
    "related_point",
    "relation_depth",
    "binding_index",
    "max_workers",
    "rejection_policy",
}
_DECODED_ROW_METADATA_FIELDS = {"query_name", "query_sha256", "site_location"}
_DECODED_ROW_FIELDS = _RAW_ROW_FIELDS | _DECODED_ROW_METADATA_FIELDS
_V1_1_RAW_FACT_FIELDS = frozenset(
    {
        "site_callable",
        "program_point",
        "related_point",
        "relation_depth",
        "binding_index",
        "max_workers",
        "rejection_policy",
    }
)
_V1_1_EXECUTOR_CONTRACT_FIELDS = frozenset(
    {"max_workers", "rejection_policy", "termination"}
)


def _source_digests(source_root: Path, relative_path: str, site_line: int) -> tuple[str, str]:
    root = source_root.resolve(strict=True)
    path = (root / relative_path).resolve(strict=True)
    if root != path.parent and root not in path.parents:
        raise ValueError("CodeQL fact source path escapes source root")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024 * 1024:
        raise ValueError("CodeQL fact source is not a bounded regular file")
    source_bytes = path.read_bytes()
    lines = source_bytes.splitlines(keepends=True)
    if site_line > len(lines):
        raise ValueError("CodeQL fact site line is outside the source file")
    return (
        hashlib.sha256(source_bytes).hexdigest(),
        hashlib.sha256(lines[site_line - 1]).hexdigest(),
    )


def _raw_fact(row: Mapping[str, object], source_root: Path, query_sha256: str) -> RawLifecycleFact:
    row_fields = set(row)
    if row_fields == _DECODED_ROW_FIELDS:
        if row["query_name"] != "resource_lifecycle":
            raise ValueError("CodeQL lifecycle row query name is invalid")
        if row["query_sha256"] != query_sha256:
            raise ValueError("CodeQL lifecycle row query SHA-256 is invalid")
        site_location = row["site_location"]
        if (
            not isinstance(site_location, Mapping)
            or set(site_location) != {"file", "start_line", "start_column"}
            or dict(site_location)
            != {
                "file": row["site_file"],
                "start_line": row["site_start_line"],
                "start_column": row["site_start_column"],
            }
        ):
            raise ValueError("CodeQL lifecycle row site location is invalid")
        raw_row = {key: row[key] for key in _RAW_ROW_FIELDS}
    elif row_fields == _RAW_ROW_FIELDS:
        raw_row = dict(row)
    elif row_fields == _LEGACY_RAW_ROW_FIELDS:
        raw_row = dict(row)
        raw_row.update(
            {
                "site_callable": raw_row["unit_id"],
                "program_point": (
                    f"legacy-point:{raw_row['site_file']}:{raw_row['site_start_line']}:"
                    f"{raw_row['site_start_column']}:{raw_row['fact_kind']}"
                ),
                "related_point": "none",
                "relation_depth": 0,
                "binding_index": -1,
                "max_workers": "unknown",
                "rejection_policy": "unknown",
            }
        )
    else:
        raise ValueError("CodeQL lifecycle row fields are invalid")
    if isinstance(raw_row["site_start_line"], bool) or not isinstance(raw_row["site_start_line"], int):
        raise ValueError("CodeQL lifecycle row line is invalid")
    if (
        type(raw_row["site_start_column"]) is not int
        or raw_row["site_start_column"] < 1
    ):
        raise ValueError("CodeQL lifecycle row column is invalid")
    if (
        not isinstance(raw_row["requires_close"], bool)
        or not isinstance(raw_row["normal_path"], bool)
        or not isinstance(raw_row["exceptional_path"], bool)
    ):
        raise ValueError("CodeQL lifecycle row path flags must be boolean")
    if any(
        not isinstance(raw_row[key], str) or not raw_row[key]
        for key in _RAW_ROW_FIELDS
        - {
            "site_start_line",
            "site_start_column",
            "relation_depth",
            "binding_index",
            "requires_close",
            "normal_path",
            "exceptional_path",
        }
    ):
        raise ValueError("CodeQL lifecycle row strings are invalid")
    path = str(raw_row["site_file"])
    source_sha256, site_line_sha256 = _source_digests(
        source_root,
        path,
        int(raw_row["site_start_line"]),
    )
    location = SourceLocation(
        path=path,
        start_line=int(raw_row["site_start_line"]),
        end_line=int(raw_row["site_start_line"]),
        source_sha256=source_sha256,
        extractor_version=f"resource-lifecycle-codeql:{query_sha256}",
        source_kind="static_verified",
    )
    semantic = {
        key: raw_row[key]
        for key in (
            "unit_id", "site_file", "site_start_line", "site_start_column", "fact_kind", "instance_key",
            "site_callable", "program_point", "related_point", "relation_depth", "binding_index",
            "resource_type", "requires_close", "holder_kind", "holder_scope", "holder_key", "target_event",
            "capacity", "max_workers", "rejection_policy", "normal_path", "exceptional_path", "source_evidence", "coverage_status",
            "coverage_note",
        )
    }
    return RawLifecycleFact(
        fact_id=stable_identifier("lifecycle-fact", {**semantic, "source_sha256": location.source_sha256, "query_sha256": query_sha256}),
        unit_id=str(raw_row["unit_id"]),
        site_callable=str(raw_row["site_callable"]),
        fact_kind=str(raw_row["fact_kind"]),
        instance_key=str(raw_row["instance_key"]),
        resource_type=str(raw_row["resource_type"]),
        requires_close=raw_row["requires_close"],
        holder_kind=str(raw_row["holder_kind"]),
        holder_scope=str(raw_row["holder_scope"]),
        holder_key=str(raw_row["holder_key"]),
        target_event=str(raw_row["target_event"]),
        capacity=str(raw_row["capacity"]),
        normal_path=raw_row["normal_path"],
        exceptional_path=raw_row["exceptional_path"],
        source_evidence=str(raw_row["source_evidence"]),
        coverage_status=str(raw_row["coverage_status"]),
        coverage_note=str(raw_row["coverage_note"]),
        location=location,
        site_start_column=raw_row["site_start_column"],
        site_line_sha256=site_line_sha256,
        program_point=str(raw_row["program_point"]),
        related_point=str(raw_row["related_point"]),
        relation_depth=raw_row["relation_depth"],
        binding_index=raw_row["binding_index"],
        max_workers=str(raw_row["max_workers"]),
        rejection_policy=str(raw_row["rejection_policy"]),
    )


def _effect(
    fact: RawLifecycleFact,
    kind: str,
    family_id: str,
    instance_id: str,
    holder_id: str | None = None,
    *,
    target_event_id: str | None = None,
    contract_id: str | None = None,
) -> Effect:
    return Effect(
        effect_id=stable_identifier("effect", {"fact_id": fact.fact_id, "kind": kind, "holder_id": holder_id}),
        kind=kind,
        instance_id=instance_id,
        family_id=family_id,
        holder_id=holder_id,
        target_event_id=target_event_id,
        condition="true",
        location=fact.location,
        evidence_ids=(fact.fact_id,),
        contract_id=contract_id,
    )


def _unit_from_rows(
    unit_id: str,
    rows: Sequence[RawLifecycleFact],
    *,
    external_entry: bool = False,
) -> AnalysisUnit:
    creates_by_instance_key: dict[str, list[RawLifecycleFact]] = defaultdict(list)
    for fact in rows:
        if fact.fact_kind == "create":
            creates_by_instance_key[fact.instance_key].append(fact)
    for fact in rows:
        matching_creates = creates_by_instance_key.get(fact.instance_key, [])
        if len(matching_creates) != 1:
            raise ValueError(
                "CodeQL lifecycle fact instance_key must bind to exactly one create fact"
            )
        create = matching_creates[0]
        if fact.resource_type != create.resource_type:
            raise ValueError("CodeQL lifecycle resource_type is inconsistent for one allocation")
        if fact.requires_close != create.requires_close:
            raise ValueError("CodeQL lifecycle requires_close is inconsistent for one allocation")
    creates = sorted(
        (item for item in rows if item.fact_kind == "create"),
        key=lambda item: (
            item.location.path,
            item.location.start_line,
            item.site_start_column,
            item.fact_id,
        ),
    )
    if not creates:
        raise ValueError("CodeQL analysis unit has no resource creation fact")
    instance_by_key: dict[str, tuple[str, str]] = {}
    families: list[ResourceFamily] = []
    instances: list[AbstractInstance] = []
    holders: dict[str, Holder] = {}
    local_holder_by_instance: dict[str, str] = {}
    for create in creates:
        family_id = stable_identifier(
            "family",
            {
                "allocation": asdict(create.location),
                "instance_key": create.instance_key,
                "context": unit_id,
                "type": create.resource_type,
            },
        )
        instance_id = stable_identifier("instance", {"family_id": family_id, "kind": "recent"})
        instance_by_key[create.instance_key] = (family_id, instance_id)
        families.append(
            ResourceFamily(
                family_id,
                create.location,
                (unit_id,),
                create.resource_type,
                create.requires_close,
                None,
            )
        )
        instances.append(AbstractInstance(instance_id, family_id, "recent", "exact"))
        local_kind = "request_stack" if external_entry else "local"
        local_scope = "request" if external_entry else "instance"
        local_holder = stable_identifier("holder", {"unit_id": unit_id, "instance": create.instance_key, "kind": local_kind})
        holders[local_holder] = Holder(local_holder, local_kind, local_scope, "exact")  # type: ignore[arg-type]
        local_holder_by_instance[instance_id] = local_holder

    invariants: list[InvariantCandidate] = []
    normalized: list[tuple[RawLifecycleFact, str, str, str | None]] = []

    def task_holder_id(fact: RawLifecycleFact) -> str:
        return stable_identifier(
            "holder",
            {
                "unit_id": unit_id,
                "holder_key": fact.holder_key,
                "kind": "task",
                "scope": fact.holder_scope,
            },
        )

    def queue_event_id(fact: RawLifecycleFact) -> str:
        return stable_identifier(
            "event",
            {
                "unit_id": unit_id,
                "phase": "task_queue",
                "target_event": fact.target_event,
            },
        )

    def queue_contract_id(fact: RawLifecycleFact, holder_id: str) -> str:
        return stable_identifier(
            "executor-contract",
            {
                "unit_id": unit_id,
                "holder_id": holder_id,
                "holder_key": fact.holder_key,
                "target_event": fact.target_event,
                "target_event_id": queue_event_id(fact),
                "capacity": fact.capacity,
                "max_workers": fact.max_workers,
                "rejection_policy": fact.rejection_policy,
            },
        )

    for fact in sorted(
        rows,
        key=lambda item: (
            item.location.start_line,
            item.site_start_column,
            {"create": 0, "retain": 1, "dispatch": 2, "unknown_call": 3, "release": 4, "invariant": 5}.get(item.fact_kind, 9),
            item.fact_id,
        ),
    ):
        identity = instance_by_key.get(fact.instance_key)
        if identity is None:
            continue
        family_id, instance_id = identity
        holder_id: str | None = None
        if fact.fact_kind == "retain" and fact.holder_kind == "field":
            holder_id = stable_identifier(
                "holder",
                {
                    "unit_id": unit_id,
                    "holder_key": fact.holder_key,
                    "kind": "field",
                    "scope": fact.holder_scope,
                },
            )
            holders[holder_id] = Holder(holder_id, "field", fact.holder_scope, "exact")  # type: ignore[arg-type]
        elif fact.fact_kind in {"dispatch", "invariant"} and fact.holder_kind == "queue":
            holder_id = task_holder_id(fact)
            holders[holder_id] = Holder(holder_id, "task", fact.holder_scope, "exact")  # type: ignore[arg-type]
        normalized.append((fact, family_id, instance_id, holder_id))
        if (
            fact.fact_kind == "invariant"
            and fact.coverage_status == "complete"
            and fact.capacity.isdecimal()
            and int(fact.capacity) > 0
        ):
            invariants.append(
                InvariantCandidate(
                    candidate_id=stable_identifier("invariant", {"fact_id": fact.fact_id, "capacity": fact.capacity}),
                    family_id=family_id,
                    dimension="held_instances",
                    scope="task_queue",
                    upper_bound=int(fact.capacity),
                    initial_holds=True,
                    transitions_preserve=True,
                    covers_writers=True,
                    atomic=True,
                    source_kind="static_verified",
                    assumptions=("exact java.util.concurrent bounded queue implementation",),
                    evidence_ids=(fact.fact_id,),
                    executor_contract_id=queue_contract_id(fact, holder_id),
                    writer_holder_id=holder_id,
                    writer_target_event_id=queue_event_id(fact),
                )
            )

    dispatch_facts = tuple(item for item in rows if item.fact_kind == "dispatch")
    queue_events_by_id = {
        queue_event_id(fact): Event(
            queue_event_id(fact),
            "task_queue",
            fact.target_event,
            "submission accepted",
        )
        for fact in dispatch_facts
    }
    has_dispatch = bool(dispatch_facts)
    entry_id = stable_identifier("event", {"unit_id": unit_id, "phase": "entry"})
    normal_id = stable_identifier("event", {"unit_id": unit_id, "phase": "normal_exit"})
    error_id = stable_identifier("event", {"unit_id": unit_id, "phase": "exceptional_exit"})
    queue_ids = tuple(sorted(queue_events_by_id))
    queue_id = (
        queue_ids[0]
        if len(queue_ids) == 1
        else stable_identifier("event", {"unit_id": unit_id, "phase": "task_queue_join"})
        if queue_ids
        else None
    )
    base_events = (
        Event(entry_id, "request" if external_entry else "method", unit_id, "true"),
        Event(normal_id, "request_exit" if external_entry else "method", f"{unit_id}#normal", "normal"),
        Event(error_id, "request_exit" if external_entry else "method", f"{unit_id}#exceptional", "exceptional"),
    )
    queue_events = tuple(queue_events_by_id[item] for item in queue_ids)
    if queue_id is not None and queue_id not in queue_events_by_id:
        queue_events += (
            Event(
                queue_id,
                "task_queue",
                f"{unit_id}#queue-join",
                "submission accepted",
            ),
        )
    events = base_events + queue_events

    def path_effects(path_name: str) -> tuple[Effect, ...]:
        output: list[Effect] = []
        for fact, family_id, instance_id, holder_id in normalized:
            enabled = fact.normal_path if path_name == "normal" else fact.exceptional_path
            if not enabled:
                continue
            if fact.fact_kind == "create":
                output.append(_effect(fact, "create", family_id, instance_id))
                output.append(_effect(fact, "retain", family_id, instance_id, local_holder_by_instance[instance_id]))
            elif fact.fact_kind == "retain" and holder_id is not None:
                output.append(_effect(fact, "retain", family_id, instance_id, holder_id))
            elif fact.fact_kind == "dispatch" and holder_id is not None:
                assert queue_id is not None
                output.append(
                    _effect(
                        fact,
                        "dispatch",
                        family_id,
                        instance_id,
                        holder_id,
                        target_event_id=queue_event_id(fact),
                        contract_id=queue_contract_id(fact, holder_id),
                    )
                )
            elif fact.fact_kind == "release":
                output.append(_effect(fact, "release", family_id, instance_id))
            elif fact.fact_kind == "unknown_call":
                output.append(_effect(fact, "unknown_call", family_id, instance_id))
        for create in creates:
            family_id, instance_id = instance_by_key[create.instance_key]
            output.append(_effect(create, "drop", family_id, instance_id, local_holder_by_instance[instance_id]))
        return tuple(output)

    normal_effects = path_effects("normal")
    transitions = (
        (
            Transition(
                stable_identifier("transition", {"unit_id": unit_id, "phase": "queue_capture"}),
                entry_id,
                queue_id,
                "queue submission accepted or may retain",
                normal_effects,
                "internal",
                ("queue capture persists until a supported consumer contract is present",),
            ),
            Transition(
                stable_identifier("transition", {"unit_id": unit_id, "exit": "normal"}),
                queue_id,
                normal_id,
                "request returns after queue submission",
                (),
                "normal",
                (),
            ),
        )
        if queue_id is not None
        else (
            Transition(
                stable_identifier("transition", {"unit_id": unit_id, "exit": "normal"}),
                entry_id,
                normal_id,
                "normal completion",
                normal_effects,
                "normal",
                (),
            ),
        )
    ) + (
        Transition(
            stable_identifier("transition", {"unit_id": unit_id, "exit": "exceptional"}),
            entry_id,
            error_id,
            "exceptional completion",
            path_effects("exceptional"),
            "exceptional",
            (),
        ),
    )
    executor_contracts_by_id: dict[str, ExecutorContract] = {}
    invariant_facts = tuple(item for item in rows if item.fact_kind == "invariant")
    normalized_dispatches = tuple(item for item in normalized if item[0].fact_kind == "dispatch")
    for dispatch_fact, _family_id, _instance_id, dispatch_holder_id in normalized_dispatches:
        if dispatch_holder_id is None:
            raise ValueError("static dispatch queue identity is invalid")
        numeric_capacity = (
            int(dispatch_fact.capacity)
            if dispatch_fact.capacity.isdecimal() and int(dispatch_fact.capacity) > 0
            else None
        )
        contract_id = queue_contract_id(dispatch_fact, dispatch_holder_id)
        matching_invariant = any(
            invariant.instance_key == dispatch_fact.instance_key
            and invariant.holder_kind == dispatch_fact.holder_kind
            and invariant.holder_scope == dispatch_fact.holder_scope
            and invariant.holder_key == dispatch_fact.holder_key
            and invariant.target_event == dispatch_fact.target_event
            and invariant.capacity == dispatch_fact.capacity
            and invariant.coverage_status == "complete"
            for invariant in invariant_facts
        )
        contract = ExecutorContract(
            contract_id=contract_id,
            scheduling="queued",
            queue_capacity=numeric_capacity,
            capacity_atomic=numeric_capacity is not None and matching_invariant,
            completion_drops_capture=False,
            rejection_drops_capture=True,
            cancellation="unknown",
            source_kind="static_verified",
            version="executor-contract-v1",
            max_workers=(
                int(dispatch_fact.max_workers)
                if dispatch_fact.max_workers.isdecimal()
                and int(dispatch_fact.max_workers) > 0
                else None
            ),
            rejection_policy=dispatch_fact.rejection_policy,  # type: ignore[arg-type]
            termination="unknown",
        )
        prior_contract = executor_contracts_by_id.get(contract_id)
        if prior_contract is None:
            executor_contracts_by_id[contract_id] = contract
        elif prior_contract != contract:
            executor_contracts_by_id[contract_id] = ExecutorContract(
                contract_id=contract.contract_id,
                scheduling=contract.scheduling,
                queue_capacity=contract.queue_capacity,
                capacity_atomic=prior_contract.capacity_atomic and contract.capacity_atomic,
                completion_drops_capture=False,
                rejection_drops_capture=True,
                cancellation="unknown",
                source_kind="static_verified",
                version=contract.version,
                max_workers=contract.max_workers,
                rejection_policy=(
                    prior_contract.rejection_policy
                    if prior_contract.rejection_policy == contract.rejection_policy
                    else "unknown"
                ),
                termination="unknown",
            )
    dimensions_by_fact_kind = {
        "create": ("held_instances", "item_size_bytes", "close_obligation"),
        "retain": ("held_instances",),
        "drop": ("held_instances",),
        "release": ("close_obligation",),
        "dispatch": ("held_instances",),
        "unknown_call": ("held_instances", "item_size_bytes", "close_obligation"),
        "invariant": ("held_instances",),
    }
    coverage_gaps = {
        (
            dimension,
            family_id,
            queue_result_scope(
                queue_contract_id(item, holder_id), holder_id, queue_event_id(item)
            )
            if item.fact_kind in {"dispatch", "invariant"} and holder_id is not None
            else "*",
            item.coverage_note,
            item.fact_id,
        )
        for item, family_id, _instance_id, holder_id in normalized
        if item.coverage_status != "complete"
        for dimension in dimensions_by_fact_kind[item.fact_kind]
        if dimension != "close_obligation" or item.requires_close
    }
    for item in rows:
        if item.fact_kind == "dispatch":
            family_id, _instance_id = instance_by_key[item.instance_key]
            holder_id = task_holder_id(item)
            scope = queue_result_scope(
                queue_contract_id(item, holder_id), holder_id, queue_event_id(item)
            )
            if item.requires_close:
                coverage_gaps.add(
                    (
                        "close_obligation",
                        family_id,
                        scope,
                        "async_consumer_contract_unmodeled",
                        item.fact_id,
                    )
                )
            if not item.capacity.isdecimal() or int(item.capacity) <= 0:
                coverage_gaps.add(
                    (
                        "held_instances",
                        family_id,
                        scope,
                        "queue_capacity_unknown",
                        item.fact_id,
                    )
                )
    coverage_complete = not coverage_gaps
    program = Program(
        SCHEMA_VERSION,
        tuple(families),
        tuple(instances),
        tuple(sorted(holders.values(), key=lambda item: item.holder_id)),
        events,
        transitions,
        (entry_id,),
        (normal_id, error_id),
        coverage_complete,
        "resource-lifecycle-contracts-v1",
        tuple(sorted(coverage_gaps)),
    )
    return AnalysisUnit(
        unit_id,
        program,
        tuple(sorted(invariants, key=lambda item: item.candidate_id)),
        tuple(sorted(executor_contracts_by_id.values(), key=lambda item: item.contract_id)),
    )


def adapt_codeql_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    source_root: Path,
    query_sha256: str,
    entry_methods: Sequence[str] = (),
) -> ExtractedFacts:
    if not re.fullmatch(r"[0-9a-f]{64}", query_sha256):
        raise ValueError("query_sha256 is invalid")
    if (
        len(entry_methods) > 4096
        or any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 512 for item in entry_methods)
    ):
        raise ValueError("entry_methods are invalid")
    selected_entries = tuple(sorted(set(entry_methods)))
    selected_entry_set = set(selected_entries)
    facts = tuple(sorted(
        (_raw_fact(row, source_root, query_sha256) for row in rows),
        key=lambda item: item.fact_id,
    ))
    grouped: dict[str, list[RawLifecycleFact]] = defaultdict(list)
    for fact in facts:
        grouped[fact.unit_id].append(fact)
    units = tuple(
        _unit_from_rows(unit_id, grouped[unit_id], external_entry=unit_id in selected_entry_set)
        for unit_id in sorted(grouped)
    )
    snapshot = hashlib.sha256(canonical_json([asdict(item) for item in facts])).hexdigest()
    gaps = sum(1 for item in facts if item.coverage_status != "complete")
    return ExtractedFacts(
        "static_verified",
        snapshot,
        f"resource-lifecycle-codeql:{query_sha256}",
        AnalysisBudget(),
        units,
        facts,
        {
            "units": len(units),
            "facts": len(facts),
            "partial_or_unsupported": gaps,
            "dimension_gaps": sum(len(unit.program.coverage_gaps) for unit in units),
            "requested_entry_methods": list(selected_entries),
            "matched_entry_methods": sorted(selected_entry_set.intersection(grouped)),
            "external_entry_units": sum(unit.unit_id in selected_entry_set for unit in units),
            "local_method_units": sum(unit.unit_id not in selected_entry_set for unit in units),
            "end_to_end_mode": "real_source_codeql",
        },
    )


def extracted_to_dict(extracted: ExtractedFacts) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_kind": extracted.source_kind,
        "snapshot_sha256": extracted.snapshot_sha256,
        "extractor_version": extracted.extractor_version,
        "budget": asdict(extracted.budget),
        "units": [
            {
                "unit_id": unit.unit_id,
                "program": program_to_dict(unit.program),
                "invariants": [asdict(item) for item in unit.invariants],
                "executor_contracts": [asdict(item) for item in unit.executor_contracts],
            }
            for unit in extracted.units
        ],
        "facts": [asdict(item) for item in extracted.facts],
        "coverage": dict(extracted.coverage),
    }


def _invariant_from_dict(value: object) -> InvariantCandidate:
    if not isinstance(value, Mapping):
        raise ValueError("invariant must be an object")
    record = dict(value)
    if set(record) != {
        "candidate_id", "family_id", "dimension", "scope", "upper_bound", "initial_holds",
        "transitions_preserve", "covers_writers", "atomic", "source_kind", "assumptions", "evidence_ids",
        "executor_contract_id", "writer_holder_id", "writer_target_event_id",
    }:
        raise ValueError("invariant fields are invalid")
    if not isinstance(record["assumptions"], list) or not isinstance(record["evidence_ids"], list):
        raise ValueError("invariant arrays are invalid")
    record["assumptions"] = tuple(str(item) for item in record["assumptions"])
    record["evidence_ids"] = tuple(str(item) for item in record["evidence_ids"])
    return InvariantCandidate(**record)  # type: ignore[arg-type]


def _executor_contract_from_dict(value: object) -> ExecutorContract:
    if not isinstance(value, Mapping):
        raise ValueError("executor contract must be an object")
    record = dict(value)
    expected = {
        "contract_id", "scheduling", "queue_capacity", "capacity_atomic",
        "completion_drops_capture", "rejection_drops_capture", "cancellation",
        "source_kind", "version", "max_workers", "rejection_policy", "termination",
    }
    optional = {"max_workers", "rejection_policy", "termination"}
    if not set(record) <= expected or not expected - optional <= set(record):
        raise ValueError("executor contract fields are invalid")
    record.setdefault("max_workers", None)
    record.setdefault("rejection_policy", "unknown")
    record.setdefault("termination", "unknown")
    return ExecutorContract(**record)  # type: ignore[arg-type]


def _fact_semantic(fact: RawLifecycleFact, *, legacy: bool = False) -> dict[str, object]:
    semantic: dict[str, object] = {
        "unit_id": fact.unit_id,
        "site_file": fact.location.path,
        "site_start_line": fact.location.start_line,
        "site_start_column": fact.site_start_column,
        "fact_kind": fact.fact_kind,
        "instance_key": fact.instance_key,
        "resource_type": fact.resource_type,
        "requires_close": fact.requires_close,
        "holder_kind": fact.holder_kind,
        "holder_scope": fact.holder_scope,
        "holder_key": fact.holder_key,
        "target_event": fact.target_event,
        "capacity": fact.capacity,
        "normal_path": fact.normal_path,
        "exceptional_path": fact.exceptional_path,
        "source_evidence": fact.source_evidence,
        "coverage_status": fact.coverage_status,
        "coverage_note": fact.coverage_note,
    }
    if not legacy:
        semantic.update(
            {
                "site_callable": fact.site_callable,
                "program_point": fact.program_point,
                "related_point": fact.related_point,
                "relation_depth": fact.relation_depth,
                "binding_index": fact.binding_index,
                "max_workers": fact.max_workers,
                "rejection_policy": fact.rejection_policy,
            }
        )
    return semantic


def _legacy_facts_are_relation_free(units: list[object], facts: list[object]) -> None:
    for item in units:
        if not isinstance(item, Mapping):
            raise ValueError("analysis unit is invalid")
        program = item.get("program")
        contracts = item.get("executor_contracts")
        if not isinstance(program, Mapping) or program.get("schema_version") != "1.0":
            raise ValueError("legacy facts schema cannot contain a v1.1 program")
        if any(
            program.get(field) not in (None, [])
            for field in ("program_points", "call_bindings", "task_bindings", "task_exits")
        ):
            raise ValueError("legacy facts schema cannot contain v1.1 relations")
        transitions = program.get("transitions")
        if isinstance(transitions, list) and any(
            isinstance(transition, Mapping)
            and transition.get("population_effects") not in (None, [])
            for transition in transitions
        ):
            raise ValueError("legacy facts schema cannot contain v1.1 population effects")
        if not isinstance(contracts, list) or any(
            not isinstance(contract, Mapping)
            or bool(set(contract).intersection(_V1_1_EXECUTOR_CONTRACT_FIELDS))
            for contract in contracts
        ):
            raise ValueError("legacy facts schema cannot contain v1.1 executor semantics")
    for item in facts:
        if (
            not isinstance(item, Mapping)
            or bool(set(item).intersection(_V1_1_RAW_FACT_FIELDS))
            or item.get("fact_kind") in {"call_binding", "cfg_edge", "task_exit"}
        ):
            raise ValueError("legacy facts schema cannot contain v1.1 raw relations")


def extracted_from_dict(value: object) -> ExtractedFacts:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "source_kind", "snapshot_sha256", "extractor_version", "budget", "units", "facts", "coverage",
    }:
        raise ValueError("facts artifact fields are invalid")
    if value.get("schema_version") not in {"1.0", SCHEMA_VERSION} or not isinstance(value.get("units"), list) or not isinstance(value.get("facts"), list):
        raise ValueError("facts artifact schema is invalid")
    legacy_schema = value.get("schema_version") == "1.0"
    unit_values = value["units"]  # type: ignore[index]
    fact_values = value["facts"]  # type: ignore[index]
    if legacy_schema:
        _legacy_facts_are_relation_free(unit_values, fact_values)
    units: list[AnalysisUnit] = []
    for item in unit_values:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"unit_id", "program", "invariants", "executor_contracts"}
            or not isinstance(item["invariants"], list)
            or not isinstance(item["executor_contracts"], list)
        ):
            raise ValueError("analysis unit is invalid")
        units.append(
            AnalysisUnit(
                str(item["unit_id"]),
                program_from_dict(item["program"]),
                tuple(_invariant_from_dict(row) for row in item["invariants"]),
                tuple(_executor_contract_from_dict(row) for row in item["executor_contracts"]),
            )
        )
    facts: list[RawLifecycleFact] = []
    for item in fact_values:
        if not isinstance(item, Mapping):
            raise ValueError("raw lifecycle fact is invalid")
        record = dict(item)
        location = location_from_dict(record.get("location"))
        record["location"] = location
        if legacy_schema:
            record.update(
                {
                    "site_callable": str(record.get("unit_id")),
                    "program_point": (
                        f"legacy-point:{location.path}:{location.start_line}:"
                        f"{record.get('site_start_column')}:{record.get('fact_kind')}"
                    ),
                    "related_point": "none",
                    "relation_depth": 0,
                    "binding_index": -1,
                    "max_workers": "unknown",
                    "rejection_policy": "unknown",
                }
            )
        facts.append(RawLifecycleFact(**record))  # type: ignore[arg-type]
    coverage = value.get("coverage")
    if not isinstance(coverage, Mapping):
        raise ValueError("coverage is invalid")
    snapshot_sha256 = str(value["snapshot_sha256"])
    if legacy_schema and facts:
        prefix = "resource-lifecycle-codeql:"
        extractor_version = str(value["extractor_version"])
        if not extractor_version.startswith(prefix):
            raise ValueError("legacy static facts extractor identity is invalid")
        query_sha256 = extractor_version[len(prefix):]
        for fact in facts:
            expected_id = stable_identifier(
                "lifecycle-fact",
                {
                    **_fact_semantic(fact, legacy=True),
                    "source_sha256": fact.location.source_sha256,
                    "query_sha256": query_sha256,
                },
            )
            if fact.fact_id != expected_id:
                raise ValueError("legacy static fact identifier is inconsistent")
        expected_legacy_snapshot = hashlib.sha256(
            canonical_json(
                [
                    {
                        key: field_value
                        for key, field_value in asdict(fact).items()
                        if key not in _V1_1_RAW_FACT_FIELDS
                    }
                    for fact in facts
                ]
            )
        ).hexdigest()
        if snapshot_sha256 != expected_legacy_snapshot:
            raise ValueError("legacy static facts snapshot digest is inconsistent")
        requested_entries = coverage.get("requested_entry_methods")
        if not isinstance(requested_entries, list) or any(
            not isinstance(item, str) for item in requested_entries
        ):
            raise ValueError("legacy static facts entry selection is invalid")
        grouped_legacy: dict[str, list[RawLifecycleFact]] = defaultdict(list)
        for fact in facts:
            grouped_legacy[fact.unit_id].append(fact)
        rebuilt_legacy_units = tuple(
            _unit_from_rows(
                unit_id,
                grouped_legacy[unit_id],
                external_entry=unit_id in set(requested_entries),
            )
            for unit_id in sorted(grouped_legacy)
        )
        if tuple(units) != rebuilt_legacy_units:
            raise ValueError("legacy derived analysis units do not match raw static facts")
        normalized_facts = tuple(
            replace(
                fact,
                fact_id=stable_identifier(
                    "lifecycle-fact",
                    {
                        **_fact_semantic(fact),
                        "source_sha256": fact.location.source_sha256,
                        "query_sha256": query_sha256,
                    },
                ),
            )
            for fact in facts
        )
        grouped_current: dict[str, list[RawLifecycleFact]] = defaultdict(list)
        for fact in normalized_facts:
            grouped_current[fact.unit_id].append(fact)
        units = [
            _unit_from_rows(
                unit_id,
                grouped_current[unit_id],
                external_entry=unit_id in set(requested_entries),
            )
            for unit_id in sorted(grouped_current)
        ]
        facts = list(normalized_facts)
        snapshot_sha256 = hashlib.sha256(
            canonical_json([asdict(item) for item in facts])
        ).hexdigest()
    return ExtractedFacts(
        str(value["source_kind"]),
        snapshot_sha256,
        str(value["extractor_version"]),
        budget_from_dict(value["budget"]),
        tuple(units),
        tuple(facts),
        dict(coverage),
    )


def validate_extracted(extracted: ExtractedFacts) -> ExtractedFacts:
    if not re.fullmatch(r"[0-9a-f]{64}", extracted.snapshot_sha256):
        raise ValueError("facts snapshot digest is invalid")
    if extracted.source_kind == "manual_fixture":
        if extracted.facts or extracted.coverage.get("end_to_end_mode") != "manual_ir":
            raise ValueError("manual fixture artifact provenance is invalid")
        for unit in extracted.units:
            if any(
                contract.source_kind not in {"manual_fixture", "trusted_contract"}
                for contract in unit.executor_contracts
            ):
                raise ValueError("manual fixture executor contract source is invalid")
            if any(resource.allocation.source_kind != "manual_fixture" for resource in unit.program.families):
                raise ValueError("manual fixture resource source is invalid")
            if any(
                effect.location.source_kind != "manual_fixture"
                for transition in unit.program.transitions
                for effect in transition.effects
            ):
                raise ValueError("manual fixture effect source is invalid")
        return extracted
    if extracted.source_kind != "static_verified":
        raise ValueError("facts artifact source kind is unsupported")
    prefix = "resource-lifecycle-codeql:"
    if not extracted.extractor_version.startswith(prefix):
        raise ValueError("static facts extractor identity is invalid")
    query_sha256 = extracted.extractor_version[len(prefix):]
    if not re.fullmatch(r"[0-9a-f]{64}", query_sha256):
        raise ValueError("static facts query digest is invalid")
    for fact in extracted.facts:
        if fact.location.source_kind != "static_verified" or fact.location.extractor_version != extracted.extractor_version:
            raise ValueError("static fact source metadata is invalid")
        expected_id = stable_identifier(
            "lifecycle-fact",
            {
                **_fact_semantic(fact),
                "source_sha256": fact.location.source_sha256,
                "query_sha256": query_sha256,
            },
        )
        if fact.fact_id != expected_id:
            raise ValueError("static fact identifier is inconsistent")
    expected_snapshot = hashlib.sha256(canonical_json([asdict(item) for item in extracted.facts])).hexdigest()
    if extracted.snapshot_sha256 != expected_snapshot:
        raise ValueError("static facts snapshot digest is inconsistent")
    grouped: dict[str, list[RawLifecycleFact]] = defaultdict(list)
    for fact in extracted.facts:
        grouped[fact.unit_id].append(fact)
    requested_entries = extracted.coverage.get("requested_entry_methods")
    if (
        not isinstance(requested_entries, list)
        or len(requested_entries) > 4096
        or requested_entries != sorted(set(requested_entries))
        or any(not isinstance(item, str) or not item for item in requested_entries)
    ):
        raise ValueError("static facts entry selection is invalid")
    requested_entry_set = set(requested_entries)
    rebuilt_units = tuple(
        _unit_from_rows(unit_id, grouped[unit_id], external_entry=unit_id in requested_entry_set)
        for unit_id in sorted(grouped)
    )
    if extracted.units != rebuilt_units:
        raise ValueError("derived analysis units do not match raw static facts")
    mode = extracted.coverage.get("end_to_end_mode")
    if mode not in {"real_source_codeql", "imported_static_facts"}:
        raise ValueError("static facts end-to-end mode is invalid")
    expected_coverage = {
        "units": len(rebuilt_units),
        "facts": len(extracted.facts),
        "partial_or_unsupported": sum(1 for item in extracted.facts if item.coverage_status != "complete"),
        "dimension_gaps": sum(len(unit.program.coverage_gaps) for unit in rebuilt_units),
        "requested_entry_methods": requested_entries,
        "matched_entry_methods": sorted(requested_entry_set.intersection(grouped)),
        "external_entry_units": sum(unit.unit_id in requested_entry_set for unit in rebuilt_units),
        "local_method_units": sum(unit.unit_id not in requested_entry_set for unit in rebuilt_units),
        "end_to_end_mode": mode,
    }
    source_snapshot = extracted.coverage.get("source_snapshot_sha256")
    if not isinstance(source_snapshot, str) or not re.fullmatch(r"[0-9a-f]{64}", source_snapshot):
        raise ValueError("Java source snapshot digest is invalid")
    expected_coverage["source_snapshot_sha256"] = source_snapshot
    if dict(extracted.coverage) != expected_coverage:
        raise ValueError("static facts coverage summary is inconsistent")
    return extracted
