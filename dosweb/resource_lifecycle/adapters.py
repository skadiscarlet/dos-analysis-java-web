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
    CallBinding,
    Effect,
    Event,
    Holder,
    PopulationEffect,
    ProgramPoint,
    Program,
    ResourceFamily,
    SCHEMA_VERSION,
    SourceLocation,
    TaskBinding,
    TaskExit,
    Transition,
)


@dataclass(frozen=True)
class RawLifecycleFact:
    fact_id: str
    query_name: str
    query_sha256: str
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
    related_location: SourceLocation
    site_start_column: int
    related_start_column: int
    site_line_sha256: str
    program_point: str
    related_point: str
    relation_depth: int
    binding_index: int
    core_workers: str
    max_workers: str
    rejection_policy: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"lifecycle-fact:[0-9a-f]{24}", self.fact_id):
            raise ValueError("raw lifecycle fact identifier is invalid")
        if self.query_name not in {
            "resource_lifecycle",
            "resource_lifecycle_task_relations",
        }:
            raise ValueError("raw lifecycle fact query name is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.query_sha256):
            raise ValueError("raw lifecycle fact query digest is invalid")
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
        if (
            type(self.site_start_column) is not int
            or self.site_start_column < 1
            or type(self.related_start_column) is not int
            or self.related_start_column < 1
        ):
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
            (self.core_workers, "core worker limit"),
            (self.max_workers, "worker limit"),
        ):
            if re.fullmatch(r"-?[0-9]+", value) and (
                int(value) < 0 if label == "core worker limit" else int(value) <= 0
            ):
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
            self.core_workers,
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
    "program_point", "related_point", "related_file", "related_start_line", "related_start_column",
    "relation_depth", "binding_index", "fact_kind", "instance_key",
    "resource_type", "requires_close", "holder_kind", "holder_scope", "holder_key", "target_event",
    "capacity", "core_workers", "max_workers", "rejection_policy", "normal_path", "exceptional_path",
    "source_evidence", "coverage_status", "coverage_note",
}
_LEGACY_RAW_ROW_FIELDS = _RAW_ROW_FIELDS - {
    "site_callable",
    "program_point",
    "related_point",
    "related_file",
    "related_start_line",
    "related_start_column",
    "relation_depth",
    "binding_index",
    "core_workers",
    "max_workers",
    "rejection_policy",
}
_DECODED_ROW_METADATA_FIELDS = {
    "query_name",
    "query_sha256",
    "site_location",
    "related_location",
}
_DECODED_ROW_FIELDS = _RAW_ROW_FIELDS | _DECODED_ROW_METADATA_FIELDS
_V1_1_RAW_FACT_FIELDS = frozenset(
    {
        "query_name",
        "query_sha256",
        "site_callable",
        "program_point",
        "related_point",
        "related_location",
        "related_start_column",
        "relation_depth",
        "binding_index",
        "core_workers",
        "max_workers",
        "rejection_policy",
    }
)
_V1_1_EXECUTOR_CONTRACT_FIELDS = frozenset(
    {"core_workers", "max_workers", "rejection_policy", "termination"}
)
_FORMAL_QUERY_NAMES = (
    "resource_lifecycle",
    "resource_lifecycle_task_relations",
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _query_suite_sha256(
    identities: Sequence[tuple[str, str]],
) -> str:
    normalized: list[dict[str, str]] = []
    for query_name, query_sha256 in identities:
        if (
            not isinstance(query_name, str)
            or query_name not in _FORMAL_QUERY_NAMES
            or not isinstance(query_sha256, str)
            or not _SHA256.fullmatch(query_sha256)
        ):
            raise ValueError("query suite identity is invalid")
        normalized.append(
            {"query_name": query_name, "query_sha256": query_sha256}
        )
    if not normalized or len({item["query_name"] for item in normalized}) != len(
        normalized
    ):
        raise ValueError("query suite identity is invalid")
    return hashlib.sha256(canonical_json(normalized)).hexdigest()


def _normalize_query_provenance(
    values: Sequence[Mapping[str, object]],
) -> tuple[dict[str, str], ...]:
    if not isinstance(values, (list, tuple)) or len(values) != len(
        _FORMAL_QUERY_NAMES
    ):
        raise ValueError("formal query provenance is invalid")
    normalized: list[dict[str, str]] = []
    for expected_name, item in zip(_FORMAL_QUERY_NAMES, values):
        if not isinstance(item, Mapping) or set(item) != {
            "query_name",
            "query_sha256",
            "bqrs_sha256",
        }:
            raise ValueError("formal query provenance is invalid")
        record = {key: str(item[key]) for key in item}
        if (
            record["query_name"] != expected_name
            or not _SHA256.fullmatch(record["query_sha256"])
            or not _SHA256.fullmatch(record["bqrs_sha256"])
        ):
            raise ValueError("formal query provenance is invalid")
        normalized.append(record)
    return tuple(normalized)


def _formal_provenance_sha256(
    query_provenance: Sequence[Mapping[str, object]],
    query_suite_sha256: str,
    database_fingerprint: str,
    source_snapshot_sha256: str,
) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "query_provenance": [dict(item) for item in query_provenance],
                "query_suite_sha256": query_suite_sha256,
                "database_fingerprint": database_fingerprint,
                "source_snapshot_sha256": source_snapshot_sha256,
            }
        )
    ).hexdigest()


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


def _raw_fact(
    row: Mapping[str, object],
    source_root: Path,
    query_digests: Mapping[str, str],
    extractor_version: str,
) -> RawLifecycleFact:
    row_fields = set(row)
    if row_fields == _DECODED_ROW_FIELDS:
        query_name = row["query_name"]
        if not isinstance(query_name, str) or query_name not in query_digests:
            raise ValueError("CodeQL lifecycle row query name is invalid")
        query_sha256 = row["query_sha256"]
        if query_sha256 != query_digests[query_name]:
            raise ValueError(
                "CodeQL lifecycle row query digest is invalid (query SHA-256 mismatch)"
            )
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
        related_location = row["related_location"]
        if (
            not isinstance(related_location, Mapping)
            or set(related_location) != {"file", "start_line", "start_column"}
            or dict(related_location)
            != {
                "file": row["related_file"],
                "start_line": row["related_start_line"],
                "start_column": row["related_start_column"],
            }
        ):
            raise ValueError("CodeQL lifecycle row related location is invalid")
        raw_row = {key: row[key] for key in _RAW_ROW_FIELDS}
    elif row_fields == _RAW_ROW_FIELDS:
        if tuple(query_digests) != ("resource_lifecycle",):
            raise ValueError("formal CodeQL lifecycle rows require decoder provenance")
        query_name = "resource_lifecycle"
        query_sha256 = query_digests[query_name]
        raw_row = dict(row)
    elif row_fields == _LEGACY_RAW_ROW_FIELDS:
        if tuple(query_digests) != ("resource_lifecycle",):
            raise ValueError("formal CodeQL lifecycle rows require decoder provenance")
        query_name = "resource_lifecycle"
        query_sha256 = query_digests[query_name]
        raw_row = dict(row)
        raw_row.update(
            {
                "site_callable": raw_row["unit_id"],
                "program_point": (
                    f"legacy-point:{raw_row['site_file']}:{raw_row['site_start_line']}:"
                    f"{raw_row['site_start_column']}:{raw_row['fact_kind']}"
                ),
                "related_point": "none",
                "related_file": raw_row["site_file"],
                "related_start_line": raw_row["site_start_line"],
                "related_start_column": raw_row["site_start_column"],
                "relation_depth": 0,
                "binding_index": -1,
                "core_workers": "unknown",
                "max_workers": "unknown",
                "rejection_policy": "unknown",
            }
        )
    else:
        raise ValueError("CodeQL lifecycle row fields are invalid")
    for field in ("site_start_line", "related_start_line"):
        if isinstance(raw_row[field], bool) or not isinstance(raw_row[field], int):
            raise ValueError("CodeQL lifecycle row line is invalid")
    for field in ("site_start_column", "related_start_column"):
        if type(raw_row[field]) is not int or raw_row[field] < 1:
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
            "related_start_line",
            "related_start_column",
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
        extractor_version=extractor_version,
        source_kind="static_verified",
    )
    related_path = str(raw_row["related_file"])
    related_source_sha256, _related_line_sha256 = _source_digests(
        source_root,
        related_path,
        int(raw_row["related_start_line"]),
    )
    related_location = SourceLocation(
        path=related_path,
        start_line=int(raw_row["related_start_line"]),
        end_line=int(raw_row["related_start_line"]),
        source_sha256=related_source_sha256,
        extractor_version=extractor_version,
        source_kind="static_verified",
    )
    semantic = {
        key: raw_row[key]
        for key in (
            "unit_id", "site_file", "site_start_line", "site_start_column", "fact_kind", "instance_key",
            "site_callable", "program_point", "related_point", "relation_depth", "binding_index",
            "resource_type", "requires_close", "holder_kind", "holder_scope", "holder_key", "target_event",
            "capacity", "core_workers", "max_workers", "rejection_policy", "normal_path",
            "exceptional_path", "source_evidence", "coverage_status", "coverage_note",
        )
    }
    semantic.update(
        {
            "related_file": related_path,
            "related_start_line": int(raw_row["related_start_line"]),
            "related_start_column": int(raw_row["related_start_column"]),
        }
    )
    return RawLifecycleFact(
        fact_id=stable_identifier(
            "lifecycle-fact",
            {
                **semantic,
                "source_sha256": location.source_sha256,
                "query_name": query_name,
                "query_sha256": query_sha256,
            },
        ),
        query_name=query_name,
        query_sha256=query_sha256,
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
        related_location=related_location,
        site_start_column=raw_row["site_start_column"],
        related_start_column=raw_row["related_start_column"],
        site_line_sha256=site_line_sha256,
        program_point=str(raw_row["program_point"]),
        related_point=str(raw_row["related_point"]),
        relation_depth=raw_row["relation_depth"],
        binding_index=raw_row["binding_index"],
        core_workers=str(raw_row["core_workers"]),
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
    condition: str = "true",
) -> Effect:
    return Effect(
        effect_id=stable_identifier("effect", {"fact_id": fact.fact_id, "kind": kind, "holder_id": holder_id}),
        kind=kind,
        instance_id=instance_id,
        family_id=family_id,
        holder_id=holder_id,
        target_event_id=target_event_id,
        condition=condition,
        location=fact.location,
        evidence_ids=(fact.fact_id,),
        contract_id=contract_id,
    )


def _unit_from_rows(
    unit_id: str,
    rows: Sequence[RawLifecycleFact],
    *,
    external_entry: bool = False,
    legacy_executor_identity: bool = False,
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
    static_source_unit = not legacy_executor_identity and any(
        fact.fact_kind == "create" and fact.source_evidence.startswith("codeql_")
        for fact in rows
    )

    def field_holder(fact: RawLifecycleFact) -> Holder:
        if fact.holder_scope == "global" and not legacy_executor_identity:
            identity = {
                "holder_key": fact.holder_key.removesuffix("#static") + "#static",
                "kind": "field",
                "scope": "global",
            }
            precision = "exact"
        else:
            identity = {
                "unit_id": unit_id,
                "holder_key": fact.holder_key,
                "kind": "field",
                "scope": fact.holder_scope,
            }
            if not legacy_executor_identity:
                identity["receiver_evidence"] = fact.fact_id
            precision = "exact" if legacy_executor_identity else "unknown"
        holder_id = stable_identifier("holder", identity)
        return Holder(
            holder_id,
            "field",
            fact.holder_scope,  # type: ignore[arg-type]
            precision,  # type: ignore[arg-type]
        )

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
        if not legacy_executor_identity and fact.holder_key.endswith("#static"):
            return stable_identifier("executor-contract", {
                "executor_field": fact.holder_key,
                "capacity": fact.capacity,
                "core_workers": fact.core_workers,
                "max_workers": fact.max_workers,
                "rejection_policy": fact.rejection_policy,
            })
        identity = {
            "unit_id": unit_id,
            "holder_id": holder_id,
            "holder_key": fact.holder_key,
            "target_event": fact.target_event,
            "target_event_id": queue_event_id(fact),
            "capacity": fact.capacity,
        }
        if not legacy_executor_identity:
            identity.update(
                {
                    "core_workers": fact.core_workers,
                    "max_workers": fact.max_workers,
                    "rejection_policy": fact.rejection_policy,
                }
            )
        return stable_identifier(
            "executor-contract",
            identity,
        )

    for fact in sorted(
        rows,
        key=lambda item: (0, 0, 0, item.fact_id) if static_source_unit else (
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
            holder = field_holder(fact)
            holder_id = holder.holder_id
            holders[holder_id] = holder
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

    point_records: dict[str, tuple[str, str, SourceLocation]] = {}
    point_kind_priority = {
        "effect": 0,
        "entry": 1,
        "call": 1,
        "return": 2,
        "task_start": 2,
        "task_submit": 3,
        "task_exit": 4,
    }

    def record_point(
        point_id: str, callable_id: str, kind: str, location: SourceLocation
    ) -> None:
        if point_id == "none":
            return
        prior = point_records.get(point_id)
        if prior is None or point_kind_priority[kind] > point_kind_priority[prior[1]]:
            point_records[point_id] = (callable_id, kind, location)

    for fact in rows:
        primary_kind = (
            "task_exit"
            if fact.fact_kind == "task_exit"
            else "task_submit"
            if fact.fact_kind == "dispatch" and fact.related_point != "none"
            else "call"
            if fact.fact_kind == "call_binding"
            or fact.fact_kind == "unknown_call"
            and fact.coverage_note != "returned_resource_ownership_unmodeled"
            else "return"
            if fact.fact_kind == "unknown_call"
            and fact.coverage_note == "returned_resource_ownership_unmodeled"
            or fact.coverage_note == "returned_resource_identity_bound"
            else "effect"
        )
        record_point(
            fact.program_point, fact.site_callable, primary_kind, fact.location
        )
        related_callable = (
            fact.target_event
            if fact.fact_kind
            in {"call_binding", "dispatch", "cfg_edge", "task_exit"}
            and fact.target_event != "none"
            else fact.site_callable
        )
        related_kind = (
            "task_start"
            if fact.fact_kind in {"dispatch", "task_exit"}
            else "entry"
            if fact.fact_kind == "call_binding"
            else "effect"
        )
        record_point(
            fact.related_point,
            related_callable,
            related_kind,
            fact.related_location,
        )
    program_points = tuple(
        ProgramPoint(point_id, callable_id, kind, location)  # type: ignore[arg-type]
        for point_id, (callable_id, kind, location) in sorted(point_records.items())
    )

    call_bindings = tuple(
        CallBinding(
            stable_identifier("call-binding", {"fact_id": fact.fact_id}),
            fact.program_point,
            fact.related_point,
            fact.site_callable,
            fact.target_event,
            fact.binding_index,
            fact.binding_index,
            instance_by_key[fact.instance_key][1],
            fact.relation_depth,
            (fact.fact_id,),
        )
        for fact in rows
        if fact.fact_kind == "call_binding" and fact.coverage_status == "complete"
    )
    base_relation_point_ids = {
        point_id
        for fact in rows
        if fact.query_name == "resource_lifecycle"
        and fact.fact_kind in {"call_binding", "cfg_edge"}
        for point_id in (fact.program_point, fact.related_point)
        if point_id != "none"
    }
    base_point_event_ids = {
        point_id: stable_identifier(
            "event", {"unit_id": unit_id, "program_point": point_id}
        )
        for point_id in base_relation_point_ids
    }
    has_source_cfg = any(
        fact.source_evidence == "codeql_callable_cfg_entry"
        and fact.site_callable == unit_id for fact in rows
    )
    if has_source_cfg:
        for suffix, event_id in (
            ("#cfg_entry", entry_id),
            ("#cfg_normal_exit", normal_id),
            ("#cfg_exceptional_exit", error_id),
        ):
            if unit_id + suffix in base_point_event_ids:
                base_point_event_ids[unit_id + suffix] = event_id
    base_relation_events = tuple(
        Event(
            event_id,
            "method",
            point_records[point_id][0],
            point_id,
        )
        for point_id, event_id in sorted(base_point_event_ids.items())
    )

    task_bindings: list[TaskBinding] = []
    task_exits: list[TaskExit] = []
    task_events: list[Event] = []
    task_dispatch_by_id: dict[str, RawLifecycleFact] = {}
    task_point_event_ids: dict[str, dict[str, str]] = {}
    capture_instances: dict[tuple[str, str], set[str]] = defaultdict(set)
    for dispatch in dispatch_facts:
        if dispatch.query_name == "resource_lifecycle_task_relations":
            capture_instances[(dispatch.program_point, dispatch.target_event)].add(dispatch.instance_key)
    exit_facts_by_task: dict[tuple[str, str], list[RawLifecycleFact]] = defaultdict(list)
    for fact in rows:
        if fact.fact_kind != "task_exit" or fact.coverage_status != "complete":
            continue
        exit_facts_by_task[(fact.instance_key, fact.target_event)].append(fact)
    for dispatch in dispatch_facts:
        if (
            dispatch.query_name != "resource_lifecycle_task_relations"
            or dispatch.coverage_status != "complete"
            or dispatch.related_point == "none"
            or len(capture_instances[(dispatch.program_point, dispatch.target_event)]) != 1
        ):
            continue
        exit_facts = exit_facts_by_task.get(
            (dispatch.instance_key, dispatch.target_event), []
        )
        _family_id, instance_id = instance_by_key[dispatch.instance_key]
        holder_id = task_holder_id(dispatch)
        contract_id = queue_contract_id(dispatch, holder_id)
        task_id = stable_identifier(
            "task",
            {
                "unit_id": unit_id,
                "instance_id": instance_id,
                "submit_point": dispatch.program_point,
                "task_callable": dispatch.target_event,
                "executor_contract_id": contract_id,
            },
        )

        def stage_id(phase: str) -> str:
            return stable_identifier(
                "event", {"task_id": task_id, "phase": phase}
            )

        submit_id = stage_id("submit")
        queued_id = queue_event_id(dispatch)
        run_id = stage_id("run")
        normal_exit_id = stage_id("normal_exit")
        exceptional_exit_id = stage_id("exceptional_exit")
        rejected_id = stage_id("rejected")
        cancelled_id = stage_id("cancelled")
        task_events.extend(
            (
                Event(submit_id, "task_submit", dispatch.site_callable, "true"),
                Event(queued_id, "task_queue", dispatch.target_event, "accepted"),
                Event(run_id, "task_run", dispatch.target_event, "scheduled"),
                Event(normal_exit_id, "task_exit", dispatch.target_event, "normal"),
                Event(
                    exceptional_exit_id,
                    "task_exit",
                    dispatch.target_event,
                    "exceptional",
                ),
                Event(rejected_id, "task_reject", dispatch.target_event, "rejected"),
                Event(cancelled_id, "task_cancel", dispatch.target_event, "cancelled"),
            )
        )
        task_bindings.append(
            TaskBinding(
                stable_identifier("task-binding", {"fact_id": dispatch.fact_id}),
                task_id,
                instance_id,
                holder_id,
                contract_id,
                submit_id,
                queued_id,
                run_id,
                normal_exit_id,
                exceptional_exit_id,
                rejected_id,
                cancelled_id,
                dispatch.target_event,
                (dispatch.fact_id,),
            )
        )
        task_dispatch_by_id[task_id] = dispatch
        task_relation_facts = tuple(
            fact
            for fact in rows
            if fact.instance_key == dispatch.instance_key
            and fact.target_event == dispatch.target_event
            and fact.fact_kind in {"cfg_edge", "release", "task_exit"}
        )
        point_ids = {dispatch.related_point}
        point_ids.update(fact.program_point for fact in task_relation_facts)
        point_ids.update(
            fact.related_point
            for fact in task_relation_facts
            if fact.related_point != "none"
        )
        task_point_event_ids[task_id] = {
            point_id: stable_identifier(
                "event", {"task_id": task_id, "program_point": point_id}
            )
            for point_id in point_ids
        }
        task_events.extend(
            Event(event_id, "method", dispatch.target_event, point_id)
            for point_id, event_id in sorted(task_point_event_ids[task_id].items())
        )
        for exit_fact in exit_facts:
            kind = "normal" if exit_fact.normal_path and not exit_fact.exceptional_path else "exceptional"
            event_id = normal_exit_id if kind == "normal" else exceptional_exit_id
            task_exits.append(
                TaskExit(
                    stable_identifier("task-exit", {"fact_id": exit_fact.fact_id}),
                    task_id,
                    exit_fact.program_point,
                    event_id,
                    dispatch.target_event,
                    kind,  # type: ignore[arg-type]
                    (exit_fact.fact_id,),
                )
            )
    ordered_events: list[Event] = []
    seen_event_ids: set[str] = set()
    for event in base_events + queue_events + base_relation_events + tuple(
        sorted(task_events, key=lambda item: item.event_id)
    ):
        if event.event_id not in seen_event_ids:
            ordered_events.append(event)
            seen_event_ids.add(event.event_id)
    events = tuple(ordered_events)

    def path_effects(path_name: str) -> tuple[Effect, ...]:
        output: list[Effect] = []
        if static_source_unit and not has_source_cfg:
            for create in creates:
                family_id, instance_id = instance_by_key[create.instance_key]
                output.extend((
                    _effect(create, "create", family_id, instance_id),
                    _effect(create, "unknown_call", family_id, instance_id),
                ))
            return tuple(output)
        for fact, family_id, instance_id, holder_id in normalized:
            if fact.site_callable != unit_id:
                continue
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
    normalized_by_fact_id = {
        fact.fact_id: (fact, family_id, instance_id, holder_id)
        for fact, family_id, instance_id, holder_id in normalized
    }
    base_relation_transitions: list[Transition] = []
    for binding in call_bindings:
        base_relation_transitions.append(
            Transition(
                stable_identifier(
                    "transition",
                    {"call_binding_id": binding.binding_id},
                ),
                base_point_event_ids[binding.source_point_id],
                base_point_event_ids[binding.target_point_id],
                "exact call binding",
                (),
                "internal",
                (),
            )
        )
    for cfg_fact in rows:
        if (
            cfg_fact.query_name != "resource_lifecycle"
            or cfg_fact.fact_kind != "cfg_edge"
        ):
            continue
        attached: list[Effect] = []
        for effect_fact, family_id, instance_id, holder_id in normalized_by_fact_id.values():
            # Without caller CFG, real-source facts cannot establish an
            # executable release. Legacy synthetic complete facts retain their
            # old import semantics; partial facts never supply a negative effect.
            if effect_fact.fact_kind == "release" and (
                static_source_unit or effect_fact.coverage_status != "complete"
            ):
                continue
            if (
                effect_fact.site_callable != unit_id
                and effect_fact.program_point == cfg_fact.related_point
                and effect_fact.fact_kind in {"retain", "release", "unknown_call"}
                and (effect_fact.fact_kind != "retain" or holder_id is not None)
            ):
                condition = (
                    "true"
                    if effect_fact.normal_path and effect_fact.exceptional_path
                    else "normal_path"
                    if effect_fact.normal_path
                    else "exceptional_path"
                    if effect_fact.exceptional_path
                    else "unreachable_path"
                )
                effect = _effect(
                    effect_fact,
                    effect_fact.fact_kind,
                    family_id,
                    instance_id,
                    holder_id,
                    condition=condition,
                )
                attached.append(
                    replace(
                        effect,
                        effect_id=stable_identifier(
                            "effect",
                            {
                                "fact_id": effect_fact.fact_id,
                                "cfg_fact_id": cfg_fact.fact_id,
                            },
                        ),
                    )
                )
        base_relation_transitions.append(
            Transition(
                stable_identifier(
                    "transition", {"cfg_fact_id": cfg_fact.fact_id}
                ),
                base_point_event_ids[cfg_fact.program_point],
                base_point_event_ids[cfg_fact.related_point],
                "verified CFG edge",
                tuple(attached),
                "internal",
                (),
            )
        )
    transitions += tuple(
        sorted(base_relation_transitions, key=lambda item: item.transition_id)
    )
    verified_base_release_ids: set[str] = set()
    if has_source_cfg:
        # Execute facts on their actual CFG edges. Positions never define order.
        # Entering an exact call suspends its caller until the callee exit.
        cfg_transitions: list[Transition] = []
        scoped_events: dict[str, Event] = {}
        instance_keys_by_id = {instance: key for key, (_family, instance) in instance_by_key.items()}
        exact_instance_ids = {
            instance.instance_id for instance in instances
            if instance.abstraction == "recent" and instance.identity_confidence == "exact"
        }
        # Local-flow candidates are not necessarily unique receiver bindings.
        # Only the query's complete singleton-finally contract proves the
        # current base-query subset's exact local identity and covered release.
        verified_base_release_ids = {
            item.fact_id for item, _family, instance_id, _holder in normalized
            if item.query_name == "resource_lifecycle" and item.fact_kind == "release"
            and item.coverage_status == "complete" and instance_id in exact_instance_ids
            and item.site_callable == unit_id
            and item.location.source_kind == "static_verified"
            and item.source_evidence == "codeql_close_receiver_local_flow_candidate"
            and item.coverage_note == "singleton_finally_exact_local_release"
        }
        source_contexts: dict[tuple[str, str], set[tuple[str, ...]]] = defaultdict(set)
        for instance_key in instance_by_key:
            source_contexts[(instance_key, unit_id)].add(())
        expanded_bindings: list[tuple[CallBinding, tuple[str, ...], tuple[str, ...]]] = []
        for binding in sorted(call_bindings, key=lambda item: (item.context_depth, item.binding_id)):
            instance_key = instance_keys_by_id[binding.instance_id]
            for caller_context in sorted(source_contexts[(instance_key, binding.caller_callable)]):
                callee_context = caller_context + (binding.source_point_id,)
                source_contexts[(instance_key, binding.callee_callable)].add(callee_context)
                expanded_bindings.append((binding, caller_context, callee_context))

        def source_cfg_event(point_id: str, context: tuple[str, ...]) -> str:
            callable_id = point_records[point_id][0]
            if callable_id == unit_id:
                return base_point_event_ids[point_id]
            event_id = stable_identifier("event", {
                "unit_id": unit_id, "program_point": point_id,
                "call_context": context,
            })
            scoped_events[event_id] = Event(event_id, "method", callable_id, point_id)
            return event_id

        bindings_by_source: dict[tuple[str, tuple[str, ...]], list[tuple[CallBinding, tuple[str, ...]]]] = defaultdict(list)
        for binding, caller_context, callee_context in expanded_bindings:
            bindings_by_source[(binding.source_point_id, caller_context)].append((binding, callee_context))
            cfg_transitions.append(Transition(
                stable_identifier("transition", {"call_binding_id": binding.binding_id, "context": callee_context}),
                source_cfg_event(binding.source_point_id, caller_context),
                source_cfg_event(binding.target_point_id, callee_context),
                "exact call binding", (), "internal", (),
            ))

        def cfg_effects(fact: RawLifecycleFact, context: tuple[str, ...]) -> tuple[Effect, ...]:
            effects: list[Effect] = []
            for item, family_id, instance_id, holder_id in normalized:
                if item.query_name != "resource_lifecycle" or item.program_point != fact.program_point:
                    continue
                if context not in source_contexts[(item.instance_key, item.site_callable)]:
                    continue
                if fact.exceptional_path and not fact.normal_path and fact.source_evidence != "codeql_callable_cfg_exit_after_success":
                    continue
                if item.fact_kind == "create":
                    effects.extend((
                        _effect(item, "create", family_id, instance_id),
                        _effect(item, "retain", family_id, instance_id, local_holder_by_instance[instance_id]),
                    ))
                elif item.fact_kind == "retain" and holder_id is not None:
                    effects.append(_effect(item, "retain", family_id, instance_id, holder_id))
                elif item.fact_kind == "release":
                    call_succeeded = (
                        fact.source_evidence == "codeql_callable_cfg_exit_after_success"
                        or fact.source_evidence == "codeql_callable_cfg_edge"
                        and fact.normal_path and not fact.exceptional_path
                    )
                    if item.fact_id in verified_base_release_ids and call_succeeded:
                        effects.append(_effect(item, "release", family_id, instance_id))
                elif item.fact_kind == "unknown_call":
                    effects.append(_effect(item, "unknown_call", family_id, instance_id))
                elif item.fact_kind == "dispatch" and holder_id is not None:
                    effects.append(_effect(item, "dispatch", family_id, instance_id, holder_id,
                        target_event_id=queue_event_id(item), contract_id=queue_contract_id(item, holder_id)))
            if fact.related_point in {unit_id + "#cfg_normal_exit", unit_id + "#cfg_exceptional_exit"}:
                for create in creates:
                    family_id, instance_id = instance_by_key[create.instance_key]
                    effects.append(_effect(create, "drop", family_id, instance_id, local_holder_by_instance[instance_id]))
            return tuple(replace(effect, effect_id=stable_identifier("effect", {
                "cfg_fact_id": fact.fact_id, "effect_id": effect.effect_id, "context": context,
            })) for effect in effects)

        for fact in rows:
            if fact.query_name != "resource_lifecycle" or fact.fact_kind != "cfg_edge" or not (
                fact.source_evidence.startswith("codeql_callable_cfg_")
                or fact.source_evidence == "codeql_parameter_cfg_entry"
            ):
                continue
            for context in sorted(source_contexts[(fact.instance_key, fact.site_callable)]):
                sources = [source_cfg_event(fact.program_point, context)]
                bound_calls = bindings_by_source.get((fact.program_point, context), [])
                if bound_calls:
                    call_failed = (
                        fact.source_evidence == "codeql_callable_cfg_exit_after_exception"
                        or (
                            fact.exceptional_path and not fact.normal_path
                            and fact.source_evidence != "codeql_callable_cfg_exit_after_success"
                        )
                    )
                    suffix = "#cfg_exceptional_exit" if call_failed else "#cfg_normal_exit"
                    sources = sorted({
                        source_cfg_event(binding.callee_callable + suffix, callee_context)
                        for binding, callee_context in bound_calls
                        if binding.callee_callable + suffix in base_point_event_ids
                    })
                for source in sources:
                    cfg_transitions.append(Transition(
                        stable_identifier("transition", {"cfg_fact_id": fact.fact_id, "source": source, "context": context}),
                        source, source_cfg_event(fact.related_point, context),
                        "verified CFG return" if bound_calls else "verified CFG edge",
                        cfg_effects(fact, context),
                        "exceptional" if fact.related_point == unit_id + "#cfg_exceptional_exit"
                        else "normal" if fact.related_point == unit_id + "#cfg_normal_exit"
                        else "internal", (),
                    ))
        transitions = tuple(sorted(cfg_transitions, key=lambda item: item.transition_id))
        events += tuple(scoped_events.values())
    task_transitions: list[Transition] = []

    def population_effect(
        fact: RawLifecycleFact,
        task_id: str,
        executor_id: str,
        kind: str,
    ) -> PopulationEffect:
        semantics = {
            "direct_accept": ("a<C or (q>=K and a<W)", 0, 1, "absent", "reserved"),
            "enqueue": ("q<K", 1, 0, "absent", "queued"),
            "assign_slot": ("q>0 and a<W", -1, 1, "queued", "reserved"),
            "start": ("reserved", 0, 0, "reserved", "running"),
            "terminate": ("a>0", 0, -1, "running", "terminated"),
            "reject": ("queue_or_workers_full", 0, 0, "absent", "rejected"),
            "cancel_queued": ("queued", -1, 0, "queued", "cancelled"),
            "cancel_active": ("running", 0, -1, "running", "cancelled"),
        }
        guard, queue_delta, active_delta, source_phase, target_phase = semantics[kind]
        return PopulationEffect(
            stable_identifier(
                "population-effect",
                {"fact_id": fact.fact_id, "task_id": task_id, "kind": kind},
            ),
            kind,  # type: ignore[arg-type]
            executor_id,
            task_id,
            guard,
            queue_delta,
            active_delta,
            source_phase,  # type: ignore[arg-type]
            target_phase,  # type: ignore[arg-type]
            fact.location,
            (fact.fact_id,),
        )

    def task_transition(
        task_id: str,
        phase: str,
        source_id: str,
        target_id: str,
        exit_kind: str,
        fact: RawLifecycleFact,
        population_kind: str | None = None,
        effects: tuple[Effect, ...] = (),
    ) -> Transition:
        population = (
            (
                population_effect(
                    fact,
                    task_id,
                    next(
                        binding.executor_contract_id
                        for binding in task_bindings
                        if binding.task_id == task_id
                    ),
                    population_kind,
                ),
            )
            if population_kind is not None
            and fact.capacity.isdecimal() and int(fact.capacity) > 0
            and fact.core_workers.isdecimal()
            and fact.max_workers.isdecimal() and int(fact.max_workers) > 0
            and int(fact.core_workers) <= int(fact.max_workers)
            else ()
        )
        return Transition(
            stable_identifier(
                "transition",
                {
                    "task_id": task_id,
                    "phase": phase,
                    "source": source_id,
                    "target": target_id,
                    "fact_id": fact.fact_id,
                },
            ),
            source_id,
            target_id,
            phase,
            effects,
            exit_kind,  # type: ignore[arg-type]
            (),
            population,
        )

    for binding in task_bindings:
        dispatch = task_dispatch_by_id[binding.task_id]
        if has_source_cfg and dispatch.program_point in base_point_event_ids:
            for context in sorted(source_contexts[(dispatch.instance_key, dispatch.site_callable)]):
                task_transitions.append(task_transition(
                    binding.task_id, "source_submit_binding",
                    source_cfg_event(dispatch.program_point, context),
                    binding.submit_event_id, "internal", dispatch,
                ))
        task_transitions.extend(
            (
                task_transition(
                    binding.task_id,
                    "direct_accept",
                    binding.submit_event_id,
                    binding.run_event_id,
                    "internal",
                    dispatch,
                    "direct_accept",
                ),
                task_transition(
                    binding.task_id,
                    "enqueue",
                    binding.submit_event_id,
                    binding.queued_event_id,
                    "internal",
                    dispatch,
                    "enqueue",
                ),
                task_transition(
                    binding.task_id,
                    "assign_slot",
                    binding.queued_event_id,
                    binding.run_event_id,
                    "internal",
                    dispatch,
                    "assign_slot",
                ),
                task_transition(
                    binding.task_id,
                    "start",
                    binding.run_event_id,
                    binding.run_event_id,
                    "internal",
                    dispatch,
                    "start",
                ),
                task_transition(
                    binding.task_id,
                    "enter_task_cfg",
                    binding.run_event_id,
                    task_point_event_ids[binding.task_id][dispatch.related_point],
                    "internal",
                    dispatch,
                ),
            )
        )
        if dispatch.rejection_policy == "abort":
            task_transitions.append(
                task_transition(
                    binding.task_id,
                    "reject",
                    binding.submit_event_id,
                    binding.rejected_event_id,
                    "rejected",
                    dispatch,
                    "reject",
                )
            )
        for fact in rows:
            if (
                fact.fact_kind == "cfg_edge"
                and fact.query_name == "resource_lifecycle_task_relations"
                and fact.coverage_status == "complete"
                and fact.instance_key == dispatch.instance_key
                and fact.target_event == dispatch.target_event
            ):
                attached: list[Effect] = []
                for effect_fact, family_id, instance_id, holder_id in normalized_by_fact_id.values():
                    if (
                        effect_fact.query_name == "resource_lifecycle_task_relations"
                        and effect_fact.fact_kind == "release"
                        and effect_fact.coverage_status == "complete"
                        and effect_fact.source_evidence == "codeql_task_callback_close_finally"
                        and effect_fact.coverage_note == "exact_captured_task_finally_close"
                        and effect_fact.normal_path and not effect_fact.exceptional_path
                        and effect_fact.instance_key == dispatch.instance_key
                        and effect_fact.target_event == dispatch.target_event
                        and effect_fact.site_callable == dispatch.target_event
                        and effect_fact.program_point == fact.program_point
                        and "#normal-success:" not in fact.program_point
                        and effect_fact.related_point == fact.related_point
                        and effect_fact.relation_depth == fact.relation_depth
                        and effect_fact.location == fact.location
                        and effect_fact.related_location == fact.related_location
                        and effect_fact.site_start_column == fact.site_start_column
                        and effect_fact.related_start_column == fact.related_start_column
                        and fact.site_callable == dispatch.target_event
                        and (
                            fact.source_evidence == "codeql_task_cfg_successor"
                            and fact.coverage_note == "reachable_task_cfg_edge"
                            and "#normal-success:" not in fact.related_point
                            or
                            fact.source_evidence == "codeql_task_close_normal_successor"
                            and fact.coverage_note == "exact_close_normal_success_continuation"
                            and fact.related_point == fact.program_point + "#normal-success:call-cfg-v1"
                            and fact.location == fact.related_location
                            and fact.site_start_column == fact.related_start_column
                            and any(
                                terminal.query_name == "resource_lifecycle_task_relations"
                                and terminal.fact_kind == "task_exit"
                                and terminal.coverage_status == "complete"
                                and terminal.source_evidence == "codeql_task_annotated_cfg_exit"
                                and terminal.normal_path != terminal.exceptional_path
                                and terminal.coverage_note == (
                                    "normal_task_annotated_cfg_exit" if terminal.normal_path
                                    else "exceptional_task_annotated_cfg_exit"
                                )
                                and terminal.program_point == fact.related_point
                                and terminal.related_point == dispatch.related_point
                                and terminal.instance_key == fact.instance_key
                                and terminal.site_callable == fact.site_callable
                                and terminal.target_event == fact.target_event
                                and terminal.location == fact.location
                                and terminal.site_start_column == fact.site_start_column
                                for terminal in rows
                            )
                        )
                        and fact.normal_path and not fact.exceptional_path
                    ):
                        effect = _effect(
                            effect_fact,
                            "release",
                            family_id,
                            instance_id,
                            holder_id,
                            condition="true",
                        )
                        attached.append(
                            replace(
                                effect,
                                effect_id=stable_identifier(
                                    "effect",
                                    {
                                        "fact_id": effect_fact.fact_id,
                                        "cfg_fact_id": fact.fact_id,
                                    },
                                ),
                            )
                        )
                task_transitions.append(
                    task_transition(
                        binding.task_id,
                        "task_cfg_edge",
                        task_point_event_ids[binding.task_id][fact.program_point],
                        task_point_event_ids[binding.task_id][fact.related_point],
                        "internal",
                        fact,
                        effects=tuple(attached),
                    )
                )
        for task_exit in task_exits:
            if task_exit.task_id != binding.task_id:
                continue
            exit_fact = next(
                fact
                for fact in rows
                if fact.fact_id in task_exit.evidence_ids
            )
            # Exit kind is not a call-success proof. Terminal close operations
            # pass through their verified synthetic success CFG edge above.
            task_transitions.append(
                task_transition(
                    binding.task_id,
                    f"{task_exit.kind}_task_exit",
                    task_point_event_ids[binding.task_id][task_exit.point_id],
                    task_exit.event_id,
                    task_exit.kind,
                    exit_fact,
                )
            )
    transitions += tuple(
        sorted(task_transitions, key=lambda item: item.transition_id)
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
        rejection_drops_capture = (
            True
            if legacy_executor_identity
            else dispatch_fact.rejection_policy in {"abort", "discard"}
        )
        contract = ExecutorContract(
            contract_id=contract_id,
            scheduling="queued",
            queue_capacity=numeric_capacity,
            capacity_atomic=numeric_capacity is not None and matching_invariant,
            completion_drops_capture=False,
            rejection_drops_capture=rejection_drops_capture,
            cancellation="unknown",
            source_kind="static_verified",
            version="executor-contract-v1",
            core_workers=(
                int(dispatch_fact.core_workers)
                if dispatch_fact.core_workers.isdecimal()
                and int(dispatch_fact.core_workers) >= 0
                else None
            ),
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
            merged_rejection_policy = (
                prior_contract.rejection_policy
                if prior_contract.rejection_policy == contract.rejection_policy
                else "unknown"
            )
            executor_contracts_by_id[contract_id] = ExecutorContract(
                contract_id=contract.contract_id,
                scheduling=contract.scheduling,
                queue_capacity=contract.queue_capacity,
                capacity_atomic=prior_contract.capacity_atomic and contract.capacity_atomic,
                completion_drops_capture=False,
                rejection_drops_capture=(
                    True
                    if legacy_executor_identity
                    else merged_rejection_policy in {"abort", "discard"}
                ),
                cancellation="unknown",
                source_kind="static_verified",
                version=contract.version,
                core_workers=contract.core_workers,
                max_workers=contract.max_workers,
                rejection_policy=merged_rejection_policy,
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
        "call_binding": ("held_instances", "item_size_bytes", "close_obligation"),
        "cfg_edge": ("held_instances", "item_size_bytes", "close_obligation"),
        "task_exit": ("held_instances", "item_size_bytes", "close_obligation"),
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
    if static_source_unit and not has_source_cfg:
        for create in creates:
            family_id, _instance_id = instance_by_key[create.instance_key]
            for dimension in dimensions_by_fact_kind["create"]:
                if dimension != "close_obligation" or create.requires_close:
                    coverage_gaps.add((dimension, family_id, "*", "callable_cfg_unavailable", create.fact_id))
    for item, family_id, _instance_id, _holder_id in normalized:
        if ((static_source_unit or has_source_cfg) and item.query_name == "resource_lifecycle"
                and item.fact_kind == "release" and item.coverage_status == "complete"
                and item.fact_id not in verified_base_release_ids):
            coverage_gaps.add(("close_obligation", family_id, "*", "unverified_base_release", item.fact_id))
        if item.query_name == "resource_lifecycle_task_relations" and item.fact_kind == "release" and not (
            item.coverage_status == "complete"
            and item.source_evidence == "codeql_task_callback_close_finally"
            and item.coverage_note == "exact_captured_task_finally_close"
            and item.normal_path and not item.exceptional_path
        ):
            coverage_gaps.add(("close_obligation", family_id, "*", "unverified_task_release", item.fact_id))
        elif item.query_name == "resource_lifecycle_task_relations" and item.fact_kind == "release" and not any(
            item.fact_id in effect.evidence_ids
            for transition in transitions for effect in transition.effects
        ):
            coverage_gaps.add(("close_obligation", family_id, "*", "task_release_cfg_attachment_unavailable", item.fact_id))
    for item, family_id, _instance_id, holder_id in normalized:
        if (
            item.fact_kind == "retain"
            and item.holder_kind == "field"
            and item.holder_scope != "global"
            and holder_id is not None
            and not legacy_executor_identity
        ):
            coverage_gaps.add(
                (
                    "held_instances",
                    family_id,
                    "*",
                    "field_receiver_identity_unresolved",
                    item.fact_id,
                )
            )
    for item in rows:
        if item.fact_kind == "dispatch":
            family_id, _instance_id = instance_by_key[item.instance_key]
            if item.query_name == "resource_lifecycle_task_relations" and not (
                item.core_workers.isdecimal() and item.max_workers.isdecimal()
                and int(item.max_workers) > 0
                and int(item.core_workers) <= int(item.max_workers)
            ):
                coverage_gaps.add(("held_instances", family_id, "*", "executor_worker_limits_unknown", item.fact_id))
            if len(capture_instances.get((item.program_point, item.target_event), ())) > 1:
                for dimension in dimensions_by_fact_kind["task_exit"]:
                    if dimension != "close_obligation" or item.requires_close:
                        coverage_gaps.add((dimension, family_id, "*", "multiple_resource_task_capture_unmodeled", item.fact_id))
            if item.query_name == "resource_lifecycle_task_relations" and not exit_facts_by_task.get(
                (item.instance_key, item.target_event)
            ):
                for dimension in dimensions_by_fact_kind["task_exit"]:
                    if dimension != "close_obligation" or item.requires_close:
                        coverage_gaps.add((dimension, family_id, "*", "task_exit_coverage_unavailable", item.fact_id))
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
    if legacy_executor_identity:
        program_points = ()
        call_bindings = ()
        task_bindings = []
        task_exits = []
    modeled_exit_ids = (normal_id, error_id)
    if has_source_cfg:
        modeled_exit_ids = tuple(
            event_id for point_id, event_id in (
                (unit_id + "#cfg_normal_exit", normal_id),
                (unit_id + "#cfg_exceptional_exit", error_id),
            )
            if any(fact.query_name == "resource_lifecycle" and fact.fact_kind == "cfg_edge"
                   and fact.related_point == point_id
                   and fact.source_evidence in {
                       "codeql_callable_cfg_exit_after_success", "codeql_callable_cfg_exit_after_exception"
                   }
                   for fact in rows)
        ) or (normal_id, error_id)
    program = Program(
        SCHEMA_VERSION,
        tuple(families),
        tuple(instances),
        tuple(sorted(holders.values(), key=lambda item: item.holder_id)),
        events,
        transitions,
        (entry_id,),
        modeled_exit_ids,
        coverage_complete,
        "resource-lifecycle-contracts-v1",
        tuple(sorted(coverage_gaps)),
        program_points,
        tuple(sorted(call_bindings, key=lambda item: item.binding_id)),
        tuple(sorted(task_bindings, key=lambda item: item.binding_id)),
        tuple(sorted(task_exits, key=lambda item: item.exit_id)),
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
    query_sha256: str | None = None,
    query_provenance: Sequence[Mapping[str, object]] | None = None,
    database_fingerprint: str | None = None,
    source_snapshot_sha256: str | None = None,
    entry_methods: Sequence[str] = (),
) -> ExtractedFacts:
    formal_provenance: tuple[dict[str, str], ...] | None = None
    if query_provenance is None:
        if not isinstance(query_sha256, str) or not _SHA256.fullmatch(query_sha256):
            raise ValueError("query_sha256 is invalid")
        if database_fingerprint is not None or source_snapshot_sha256 is not None:
            raise ValueError("single-query provenance fields are invalid")
        query_digests = {"resource_lifecycle": query_sha256}
        extractor_version = f"resource-lifecycle-codeql:{query_sha256}"
    else:
        if query_sha256 is not None:
            raise ValueError("query provenance is ambiguous")
        formal_provenance = _normalize_query_provenance(query_provenance)
        if (
            not isinstance(database_fingerprint, str)
            or not _SHA256.fullmatch(database_fingerprint)
            or not isinstance(source_snapshot_sha256, str)
            or not _SHA256.fullmatch(source_snapshot_sha256)
        ):
            raise ValueError("formal artifact provenance is invalid")
        query_digests = {
            item["query_name"]: item["query_sha256"]
            for item in formal_provenance
        }
        suite_sha256 = _query_suite_sha256(
            tuple(
                (item["query_name"], item["query_sha256"])
                for item in formal_provenance
            )
        )
        extractor_version = f"resource-lifecycle-codeql-suite:{suite_sha256}"
    if (
        len(entry_methods) > 4096
        or any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 512 for item in entry_methods)
    ):
        raise ValueError("entry_methods are invalid")
    selected_entries = tuple(sorted(set(entry_methods)))
    selected_entry_set = set(selected_entries)
    facts = tuple(sorted(
        (
            _raw_fact(row, source_root, query_digests, extractor_version)
            for row in rows
        ),
        key=lambda item: item.fact_id,
    ))
    semantic_origins: dict[bytes, set[tuple[str, str]]] = defaultdict(set)
    for fact in facts:
        semantic = _fact_semantic(fact)
        semantic.pop("query_name")
        semantic.pop("query_sha256")
        semantic_origins[canonical_json(semantic)].add(
            (fact.query_name, fact.query_sha256)
        )
    if any(len(origins) > 1 for origins in semantic_origins.values()):
        raise ValueError("duplicate semantic row across lifecycle queries")
    if formal_provenance is not None:
        base_facts = tuple(
            fact for fact in facts if fact.query_name == "resource_lifecycle"
        )
        base_units = {fact.unit_id for fact in base_facts if fact.fact_kind == "create"}
        base_instances = {
            (fact.unit_id, fact.instance_key)
            for fact in base_facts
            if fact.fact_kind == "create"
        }
        dispatches = {
            (fact.unit_id, fact.instance_key, fact.target_event)
            for fact in facts
            if fact.query_name == "resource_lifecycle_task_relations"
            and fact.fact_kind == "dispatch"
        }
        for fact in facts:
            if fact.query_name != "resource_lifecycle_task_relations":
                continue
            if fact.unit_id not in base_units:
                raise ValueError("task relation references an unknown base unit")
            if (fact.unit_id, fact.instance_key) not in base_instances:
                raise ValueError("task relation has an orphan instance_key")
            if fact.fact_kind in {"cfg_edge", "release", "task_exit"} and (
                fact.unit_id,
                fact.instance_key,
                fact.target_event,
            ) not in dispatches:
                raise ValueError("task relation references a dangling task")
    grouped: dict[str, list[RawLifecycleFact]] = defaultdict(list)
    for fact in facts:
        grouped[fact.unit_id].append(fact)
    units = tuple(
        _unit_from_rows(unit_id, grouped[unit_id], external_entry=unit_id in selected_entry_set)
        for unit_id in sorted(grouped)
    )
    snapshot = hashlib.sha256(canonical_json([asdict(item) for item in facts])).hexdigest()
    gaps = sum(1 for item in facts if item.coverage_status != "complete")
    coverage: dict[str, object] = {
        "units": len(units),
        "facts": len(facts),
        "partial_or_unsupported": gaps,
        "dimension_gaps": sum(len(unit.program.coverage_gaps) for unit in units),
        "requested_entry_methods": list(selected_entries),
        "matched_entry_methods": sorted(selected_entry_set.intersection(grouped)),
        "external_entry_units": sum(unit.unit_id in selected_entry_set for unit in units),
        "local_method_units": sum(unit.unit_id not in selected_entry_set for unit in units),
        "end_to_end_mode": "real_source_codeql",
    }
    if formal_provenance is not None:
        coverage.update(
            {
                "query_provenance": [dict(item) for item in formal_provenance],
                "query_suite_sha256": suite_sha256,
                "database_fingerprint": database_fingerprint,
                "source_snapshot_sha256": source_snapshot_sha256,
                "provenance_sha256": _formal_provenance_sha256(
                    formal_provenance,
                    suite_sha256,
                    database_fingerprint,
                    source_snapshot_sha256,
                ),
            }
        )
    return ExtractedFacts(
        "static_verified",
        snapshot,
        extractor_version,
        AnalysisBudget(),
        units,
        facts,
        coverage,
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


def _executor_contract_from_dict(
    value: object, *, schema_version: str = SCHEMA_VERSION
) -> ExecutorContract:
    if not isinstance(value, Mapping):
        raise ValueError("executor contract must be an object")
    record = dict(value)
    expected = {
        "contract_id", "scheduling", "queue_capacity", "capacity_atomic",
        "completion_drops_capture", "rejection_drops_capture", "cancellation",
        "source_kind", "version", "core_workers", "max_workers",
        "rejection_policy", "termination",
    }
    if schema_version == SCHEMA_VERSION:
        if set(record) != expected:
            raise ValueError("schema 1.1 executor contract fields are invalid")
        if (
            record["rejection_policy"] == "unknown"
            and record["rejection_drops_capture"] is True
        ):
            raise ValueError(
                "executor rejection policy and legacy flag are inconsistent"
            )
    elif schema_version == "1.0":
        legacy_fields = expected - _V1_1_EXECUTOR_CONTRACT_FIELDS
        if set(record) != legacy_fields:
            raise ValueError("legacy executor contract fields are invalid")
        record.update(
            {
                "core_workers": None,
                "max_workers": None,
                "rejection_policy": "unknown",
                "termination": (
                    "drops_capture"
                    if record["completion_drops_capture"] is True
                    else "unknown"
                ),
            }
        )
    else:
        raise ValueError("executor contract schema is unsupported")
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
                "query_name": fact.query_name,
                "query_sha256": fact.query_sha256,
                "site_callable": fact.site_callable,
                "program_point": fact.program_point,
                "related_point": fact.related_point,
                "related_file": fact.related_location.path,
                "related_start_line": fact.related_location.start_line,
                "related_start_column": fact.related_start_column,
                "relation_depth": fact.relation_depth,
                "binding_index": fact.binding_index,
                "core_workers": fact.core_workers,
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
    legacy_query_sha256: str | None = None
    unit_values = value["units"]  # type: ignore[index]
    fact_values = value["facts"]  # type: ignore[index]
    if legacy_schema:
        _legacy_facts_are_relation_free(unit_values, fact_values)
        prefix = "resource-lifecycle-codeql:"
        extractor_version = str(value["extractor_version"])
        if not extractor_version.startswith(prefix):
            raise ValueError("legacy static facts extractor identity is invalid")
        legacy_query_sha256 = extractor_version[len(prefix):]
        if not _SHA256.fullmatch(legacy_query_sha256):
            raise ValueError("legacy static facts query digest is invalid")
    units: list[AnalysisUnit] = []
    for item in unit_values:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"unit_id", "program", "invariants", "executor_contracts"}
            or not isinstance(item["invariants"], list)
            or not isinstance(item["executor_contracts"], list)
        ):
            raise ValueError("analysis unit is invalid")
        program_value = item["program"]
        if (
            not isinstance(program_value, Mapping)
            or program_value.get("schema_version") != value.get("schema_version")
        ):
            raise ValueError("facts nested schema must match the outer schema")
        units.append(
            AnalysisUnit(
                str(item["unit_id"]),
                program_from_dict(program_value),
                tuple(_invariant_from_dict(row) for row in item["invariants"]),
                tuple(
                    _executor_contract_from_dict(
                        row,
                        schema_version="1.0" if legacy_schema else SCHEMA_VERSION,
                    )
                    for row in item["executor_contracts"]
                ),
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
            assert legacy_query_sha256 is not None
            record.update(
                {
                    "query_name": "resource_lifecycle",
                    "query_sha256": legacy_query_sha256,
                    "site_callable": str(record.get("unit_id")),
                    "program_point": (
                        f"legacy-point:{location.path}:{location.start_line}:"
                        f"{record.get('site_start_column')}:{record.get('fact_kind')}"
                    ),
                    "related_point": "none",
                    "related_location": location,
                    "related_start_column": record.get("site_start_column"),
                    "relation_depth": 0,
                    "binding_index": -1,
                    "core_workers": "unknown",
                    "max_workers": "unknown",
                    "rejection_policy": "unknown",
                }
            )
        else:
            record["related_location"] = location_from_dict(
                record.get("related_location")
            )
        facts.append(RawLifecycleFact(**record))  # type: ignore[arg-type]
    coverage = value.get("coverage")
    if not isinstance(coverage, Mapping):
        raise ValueError("coverage is invalid")
    snapshot_sha256 = str(value["snapshot_sha256"])
    if legacy_schema and facts:
        assert legacy_query_sha256 is not None
        query_sha256 = legacy_query_sha256
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
                legacy_executor_identity=True,
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
            if any(
                point.location.source_kind != "manual_fixture"
                for point in unit.program.program_points
            ):
                raise ValueError("manual fixture program point source is invalid")
            if any(
                effect.location.source_kind != "manual_fixture"
                for transition in unit.program.transitions
                for effect in transition.population_effects
            ):
                raise ValueError("manual fixture population effect source is invalid")
        return extracted
    if extracted.source_kind != "static_verified":
        raise ValueError("facts artifact source kind is unsupported")
    single_prefix = "resource-lifecycle-codeql:"
    suite_prefix = "resource-lifecycle-codeql-suite:"
    formal_provenance: tuple[dict[str, str], ...] | None = None
    if extracted.extractor_version.startswith(suite_prefix):
        suite_sha256 = extracted.extractor_version[len(suite_prefix):]
        if not _SHA256.fullmatch(suite_sha256):
            raise ValueError("static facts query suite digest is invalid")
        provenance_value = extracted.coverage.get("query_provenance")
        if not isinstance(provenance_value, (list, tuple)):
            raise ValueError("formal query provenance is invalid")
        formal_provenance = _normalize_query_provenance(provenance_value)
        expected_suite_sha256 = _query_suite_sha256(
            tuple(
                (item["query_name"], item["query_sha256"])
                for item in formal_provenance
            )
        )
        if (
            suite_sha256 != expected_suite_sha256
            or extracted.coverage.get("query_suite_sha256") != suite_sha256
        ):
            raise ValueError("formal query provenance suite identity is inconsistent")
        database_fingerprint = extracted.coverage.get("database_fingerprint")
        source_snapshot = extracted.coverage.get("source_snapshot_sha256")
        provenance_sha256 = extracted.coverage.get("provenance_sha256")
        if (
            not isinstance(database_fingerprint, str)
            or not _SHA256.fullmatch(database_fingerprint)
            or not isinstance(source_snapshot, str)
            or not _SHA256.fullmatch(source_snapshot)
            or not isinstance(provenance_sha256, str)
            or provenance_sha256
            != _formal_provenance_sha256(
                formal_provenance,
                suite_sha256,
                database_fingerprint,
                source_snapshot,
            )
        ):
            raise ValueError("formal artifact provenance is inconsistent")
        query_digests = {
            item["query_name"]: item["query_sha256"]
            for item in formal_provenance
        }
    elif extracted.extractor_version.startswith(single_prefix):
        query_sha256 = extracted.extractor_version[len(single_prefix):]
        if not _SHA256.fullmatch(query_sha256):
            raise ValueError("static facts query digest is invalid")
        query_digests = {"resource_lifecycle": query_sha256}
    else:
        raise ValueError("static facts extractor identity is invalid")
    for fact in extracted.facts:
        if fact.location.source_kind != "static_verified" or fact.location.extractor_version != extracted.extractor_version:
            raise ValueError("static fact source metadata is invalid")
        if query_digests.get(fact.query_name) != fact.query_sha256:
            raise ValueError("static fact row query provenance is inconsistent")
        expected_id = stable_identifier(
            "lifecycle-fact",
            {
                **_fact_semantic(fact),
                "source_sha256": fact.location.source_sha256,
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
    if formal_provenance is not None:
        expected_coverage.update(
            {
                "query_provenance": [dict(item) for item in formal_provenance],
                "query_suite_sha256": suite_sha256,
                "database_fingerprint": database_fingerprint,
                "provenance_sha256": provenance_sha256,
            }
        )
    if dict(extracted.coverage) != expected_coverage:
        raise ValueError("static facts coverage summary is inconsistent")
    return extracted
