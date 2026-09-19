"""Concrete, network-free-capable production pipeline adapters."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

import dosweb.filesystem as filesystem
from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.artifacts.jsonl import read_jsonl_bytes_strict
from dosweb.artifacts.metadata import read_upstream_artifact_bytes
from dosweb.artifacts.schemas import SCHEMA_VERSION as ARTIFACT_SCHEMA_VERSION, validate_records, validate_references
from dosweb.codeql.database import (
    DatabaseInfo,
    cleanup_execution_database_snapshot as _cleanup_execution_database_snapshot,
    create_execution_database_snapshot as _create_execution_database_snapshot,
    validate_canonical_database as _validate_canonical_database,
    validate_database as _validate_database,
)
from dosweb.codeql.decoder import DecodeSource, decode_bqrs_json
from dosweb.codeql.runner import (
    QueryResult,
    _QueryOutputBinding,
    _pin_query_output_binding,
    run_query as _run_query,
)
from dosweb.config import AnalyzerConfig, _DEFAULT_SECRETS_PATH, load_config, resolve_api_key
from dosweb.configuration import extract_modeled_configuration_with_coverage
from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.reachability.models import EntrySecurityFact
from dosweb.reachability.extract import (
    bind_entry_security_rows,
    extract_entry_deployment_defaults,
    extract_entry_security_fallback,
)
from dosweb.conclude.assertions import evaluate_assertion_1, evaluate_assertion_2
from dosweb.conclude.verdicts import (
    CandidateCoverage,
    VerdictProofGate,
    apply_positive_proof_gate,
    derive_verdict,
)
from dosweb.entries import EntryFact, FrameworkCoverage
from dosweb.entries.coverage import registration_coverage_pattern_id
from dosweb.entries.jaxrs_source import augment_source_backed_jaxrs_entries
from dosweb.entries.normalize import normalize_entry_rows, normalize_framework_coverage, normalize_gap_entry_rows
from dosweb.errors import AnalyzerError
from dosweb.entries.webxml import resolve_webxml_servlet_candidates, validate_descriptor_coverage
from dosweb.flows.models import FlowProof, expression_binds_demand, normalize_flow_rows
from dosweb.flows.verify import VerifiedFlow, verify_flow
from dosweb.filesystem import (
    CloseRangeCapability,
    open_owned_descriptor as _open_owned_descriptor,
    renameat2_no_replace,
    release_owned_descriptor_once,
    require_close_fd_once,
    run_with_deferred_interrupts,
)
from dosweb.growth.contracts import validate_contract_static_evidence
from dosweb.growth.completeness import (
    CandidateDisposition,
    CandidateEntryLink,
    CandidateNegativeProof,
)
from dosweb.growth.evidence import adapt_growth_static_evidence
from dosweb.growth.excerpts import extract_source_excerpt
from dosweb.growth.models import BoundedSlice, BoundedSlicePayload, GrowthContract
from dosweb.growth.relevance import evaluate_candidate_relevance
from dosweb.growth.slices import DemandInput, GrowthCandidate, SourceLocation, normalize_growth_rows
from dosweb.growth.source_fallback import source_backed_same_handler_growth
from dosweb.growth.verify import VerificationCheck, VerifiedGrowthResult, verify_growth_contract
from dosweb.lifecycle.bounds import BoundCandidate, BoundDecision, evaluate_bound
from dosweb.lifecycle.certificates import LifecycleCertificate, StaticFinding, build_lifecycle_certificate
from dosweb.lifecycle.framework_limits import (
    is_framework_limit_candidate,
    normalize_framework_limit,
)
from dosweb.lifecycle.guards import DecisionCheck, GuardCandidate, GuardDecision, ModeledConfiguration, evaluate_guard
from dosweb.lifecycle.releases import ReleaseCandidate, ReleaseDecision, evaluate_synchronous_release
from dosweb.lifecycle.evidence import LifecycleCoverage, LifecycleEvidence, LifecycleSummary
from dosweb.lifecycle.resource_properties import (
    ResourceLifecycleBackendRun,
    ResourceLifecycleCoverageGap,
    ResourceLifecycleDecision,
    bind_resource_lifecycle_coverage_gap,
    bind_resource_lifecycle_property,
)
from dosweb.llm.deepseek import DeepSeekClient
from dosweb.pipeline import Executor, Pipeline, STAGES, StageContext, StageOutput
from dosweb.report.markdown import render_report
from dosweb.report.families import FindingFamily, build_finding_families
from dosweb.report.summary import build_summary

_IMPLEMENTATION_VERSIONS: Final = {
    stage: (
        "production-v2.8-open-world-maturation-growth-v32"
        if stage == "growth"
        else "production-v2.8-open-world-maturation-entries-v17"
        if stage == "entries"
        else "production-v2.8-open-world-maturation-conclude-v6"
        if stage == "conclude"
        else "production-v2.8-open-world-maturation-flows-v22"
        if stage == "flows"
        else f"production-v2.8-open-world-maturation-{stage}-v16"
        if stage == "lifecycle"
        else f"production-v2.8-open-world-maturation-{stage}-v1"
    )
    for stage in STAGES
}
_QUERY_PACK_DIR: Final = Path(__file__).resolve().parent / "codeql" / "pack"
_ENTRY_QUERY_DIR: Final = _QUERY_PACK_DIR / "dosweb" / "Entries"
_INTERPOSITION_QUERY: Final = "EntryInterpositions.ql"
_SECURITY_QUERY: Final = "EntrySecurity.ql"
_ENTRY_QUERIES: Final = (
    "SpringMvcEntries.ql", "ServletEntries.ql", "NettyEntries.ql", "MqttEntries.ql",
    "JaxRsEntries.ql", "GrpcEntries.ql",
)
_ENTRY_QUERY_FRAMEWORKS: Final[dict[str, tuple[str, str]]] = {
    "SpringMvcEntries.ql": ("spring_mvc", "http"),
    "ServletEntries.ql": ("servlet", "http"),
    "NettyEntries.ql": ("netty", "tcp"),
    "MqttEntries.ql": ("mqtt", "mqtt"),
    "JaxRsEntries.ql": ("jax_rs", "http"),
    "GrpcEntries.ql": ("grpc", "grpc"),
}
_QUERY_FAMILIES: Final[dict[str, tuple[str, ...]]] = {
    "growth": ("InputMaterialization.ql", "DirectAllocation.ql", "ContainerGrowth.ql", "AsyncWorkGrowth.ql"),
    "flows": ("EntryToGrowth.ql",),
    "associations": ("EntryToGrowthAssociations.ql",),
    "lifecycle": ("GuardCandidates.ql", "BoundCandidates.ql", "SynchronousReleaseCandidates.ql", "LifecycleCoverage.ql", "LifecycleSummary.ql"),
}
_QUERY_DIRS: Final[dict[str, str]] = {"growth": "Growth", "flows": "Flows", "associations": "Flows", "lifecycle": "Lifecycle"}
_MAX_DECODED_BYTES: Final = 64 * 1024 * 1024
_MAX_QUERY_INPUT_BYTES: Final = 2 * 1024 * 1024


def _same_java_callable(source_root: Path, relative_file: str, first_line: int, second_line: int) -> bool:
    """Conservatively bind two source locations to the same Java method body.

    This is intentionally a narrow parser: malformed/large files, lambdas and
    interprocedural code return ``False`` and therefore preserve partial
    lifecycle coverage. It prevents a global candidate with the same receiver
    spelling from being reused across handlers until CodeQL emits a stronger
    CFG/alias witness.
    """
    if first_line < 1 or second_line < 1 or ".." in Path(relative_file).parts:
        return False
    try:
        path = (source_root / relative_file).resolve(strict=True)
        if path.parent != source_root.resolve() and source_root.resolve() not in path.parents:
            return False
        if path.stat().st_size > 512 * 1024:
            return False
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError, ValueError):
        return False
    if max(first_line, second_line) > len(lines):
        return False
    # Identify the innermost brace scope whose header resembles a method. This
    # avoids treating class-level field initializers as a common callable.
    stack: list[tuple[int, bool]] = []
    scopes: list[tuple[int, int]] = []
    for index, line in enumerate(lines, 1):
        header = "(" in line and ")" in line and ("{" in line or index < len(lines) and "{" in lines[index])
        for _ in range(line.count("{")):
            stack.append((index, header))
        for _ in range(line.count("}")):
            if stack:
                start, is_method = stack.pop()
                if is_method:
                    scopes.append((start, index))
    common = [scope for scope in scopes if scope[0] <= first_line <= scope[1] and scope[0] <= second_line <= scope[1]]
    return bool(common)
_MAX_ENTRY_ROWS: Final = 4096
_CODEQL_TIMEOUT_SECONDS: Final = 300

validate_database = _validate_database
run_query = _run_query
create_execution_database_snapshot = _create_execution_database_snapshot
cleanup_execution_database_snapshot = _cleanup_execution_database_snapshot
validate_canonical_database = _validate_canonical_database



def _normalize_interposition_rows(
    rows: Sequence[Mapping[str, object]], entries: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Bind source-backed filter rows only to one complete extracted entry.

    A row with route-normalization duplicates or any other ambiguous handler
    identity is deliberately not published: interposition evidence must not
    invent an Entry identity.
    """
    by_location: dict[tuple[str, int], list[Mapping[str, object]]] = {}
    for entry in entries:
        handler = entry.get("handler")
        if not isinstance(handler, Mapping):
            continue
        file_name, line, entry_id = handler.get("file"), handler.get("start_line"), entry.get("entry_id")
        if isinstance(file_name, str) and isinstance(line, int) and isinstance(entry_id, str):
            by_location.setdefault((file_name, line), []).append(entry)
    output: list[dict[str, object]] = []
    for row in rows:
        entry_file, entry_line = row.get("entry_file"), row.get("entry_start_line")
        if not isinstance(entry_file, str) or not isinstance(entry_line, int):
            continue
        matches = by_location.get((entry_file, entry_line), ())
        if not matches:
            continue
        registration_identities = {
            (
                registration.get("kind"), registration.get("callable"),
                registration.get("file"), registration.get("start_line"),
            )
            for candidate in matches
            for registration in (candidate.get("registration"),)
            if isinstance(registration, Mapping)
        }
        # Route-normalization variants (for example `/x` and `POST /x`) are
        # one registration identity. Prefer the verb-qualified fact; truly
        # distinct registrations remain ambiguous and are not published.
        if len(registration_identities) != 1:
            continue
        ordered_matches = sorted(
            matches,
            key=lambda candidate: (
                0 if str(candidate.get("route_or_event", "")).split(" ", 1)[0] in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} else 1,
                str(candidate.get("entry_id", "")),
            ),
        )
        required_strings = (
            "interposer_fqn", "interposer_file", "registration_kind", "registration_fqn",
            "registration_file", "url_predicate_kind", "url_predicate_value", "order_status",
            "order_value", "action_fqn", "action_file", "chain_file", "phase",
            "coverage_status", "coverage_note",
        )
        required_lines = ("interposer_start_line", "registration_start_line", "action_start_line", "chain_start_line")
        if (not all(isinstance(row.get(key), str) and row[key] for key in required_strings)
                or not all(isinstance(row.get(key), int) and not isinstance(row[key], bool) and row[key] > 0 for key in required_lines)
                or not isinstance(row.get("action_before_chain"), bool)):
            continue
        entry_id = str(ordered_matches[0]["entry_id"])
        record = {
            "interposition_id": stable_identifier("interposition", {"entry_id": entry_id, "row": dict(row)}),
            "entry_id": entry_id,
            "kind": "filter_registration_bean",
            "interposer": {"callable": row["interposer_fqn"], "file": row["interposer_file"], "start_line": row["interposer_start_line"]},
            "registration": {"kind": row["registration_kind"], "callable": row["registration_fqn"], "file": row["registration_file"], "start_line": row["registration_start_line"]},
            "url_predicate": {"kind": row["url_predicate_kind"], "value": row["url_predicate_value"]},
            "order": {"status": row["order_status"], "value": row["order_value"]},
            "action": {"callable": row["action_fqn"], "file": row["action_file"], "start_line": row["action_start_line"]},
            "chain_call": {"file": row["chain_file"], "start_line": row["chain_start_line"]},
            "phase": row["phase"], "action_before_chain": row["action_before_chain"],
            "coverage_status": row["coverage_status"], "coverage_note": row["coverage_note"],
        }
        # A query cannot claim complete evidence without a strict CFG witness.
        if record["coverage_status"] == "complete" and not (record["phase"] == "before_handler" and record["action_before_chain"]):
            record["coverage_status"] = "partial"
            record["coverage_note"] = "interposition_complete_claim_rejected"
        output.append(record)
    return output


def _non_secret_config(config: AnalyzerConfig) -> dict[str, object]:
    return {
        "codeql_binary": config.codeql_binary, "database": str(config.database),
        "llm": {"allow_remote_llm": config.llm.allow_remote_llm, "analysis_source_root": str(config.llm.analysis_source_root) if config.llm.analysis_source_root else None, "base_url": config.llm.base_url,
                "cache_dir": str(config.llm.cache_dir), "max_retries": config.llm.max_retries,
                "model": config.llm.model,
                "public_source_url": config.llm.public_source_url,
                "source_commit_sha": config.llm.source_commit_sha,
                "source_checkout": str(config.llm.source_checkout) if config.llm.source_checkout else None,
                "temperature": config.llm.temperature,
                "timeout_seconds": config.llm.timeout_seconds},
        "output": str(config.output),
    }


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _bounded_regular_file(path: Path, limit: int) -> bytes:
    descriptor = -1
    descriptor_owner: list[int] = []
    try:
        descriptor = _open_owned_descriptor(
            descriptor_owner,
            path,
            os.O_RDONLY
            | os.O_NONBLOCK
            | getattr(os, "O_NOFOLLOW", 0),
        )
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("input is not a bounded regular file")
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > limit:
            raise ValueError("input exceeds limit")
        return bytes(raw)
    except (OSError, ValueError, MemoryError) as exc:
        raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.", {"path": path.name}) from exc
    finally:
        for descriptor in reversed(descriptor_owner):
            if descriptor >= 0:
                os.close(descriptor)


def _query_pack_snapshot(query_root: Path = _ENTRY_QUERY_DIR) -> tuple[str, dict[str, bytes]]:
    """Snapshot every bounded regular file in the containing CodeQL pack."""
    pack_root = query_root.parents[1]
    try:
        paths = sorted(path for path in pack_root.rglob("*") if path.is_file() and not path.is_symlink())
    except (OSError, RuntimeError) as exc:
        raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.") from exc
    if not paths:
        raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.")
    snapshot: dict[str, bytes] = {}
    manifest: list[dict[str, object]] = []
    for path in paths:
        try:
            relative = path.relative_to(pack_root).as_posix()
        except ValueError as exc:
            raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.") from exc
        data = _bounded_regular_file(path, _MAX_QUERY_INPUT_BYTES)
        snapshot[relative] = data
        manifest.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    return _digest({"format": "dosweb-query-pack-v3", "files": manifest}), snapshot


def _query_pack_hash(query_root: Path = _ENTRY_QUERY_DIR) -> str:
    return _query_pack_snapshot(query_root)[0]


def _materialize_query_pack(root: Path, snapshot: Mapping[str, bytes]) -> Path:
    if not snapshot or any(not isinstance(path, str) or not isinstance(data, bytes) for path, data in snapshot.items()):
        raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.")
    for relative, data in sorted(snapshot.items()):
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not relative:
            raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.")
        destination = root.joinpath(*path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as target:
                target.write(data); target.flush(); os.fsync(target.fileno())
        except (OSError, TypeError, ValueError, MemoryError) as exc:
            raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.") from exc
    return root


def _bounded_decoded_descriptor(descriptor: int) -> bytes:
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size > _MAX_DECODED_BYTES
        ):
            raise ValueError("decoded output is not a bounded regular file")
        raw = bytearray()
        offset = 0
        while len(raw) <= _MAX_DECODED_BYTES:
            chunk = os.pread(
                descriptor,
                min(
                    1024 * 1024,
                    _MAX_DECODED_BYTES + 1 - len(raw),
                ),
                offset,
            )
            if not chunk:
                break
            raw.extend(chunk)
            offset += len(chunk)
        if len(raw) > _MAX_DECODED_BYTES:
            raise ValueError("decoded output exceeds limit")
        return bytes(raw)
    except (OSError, ValueError, MemoryError) as exc:
        raise AnalyzerError(
            "CODEQL_RESULT_INVALID",
            "Decoded CodeQL output could not be read safely.",
        ) from exc


def _bounded_json_file(
    path: Path | QueryResult,
    workspace: _CodeqlQueryWorkspace | None = None,
) -> Mapping[str, object]:
    binding: _QueryOutputBinding | None = None
    if isinstance(path, QueryResult):
        if workspace is None:
            raise _workspace_query_failed(
                "query output binding is unavailable"
            )
        owned = workspace.result_bindings.get(id(path))
        if owned is None or owned[0] is not path:
            raise _workspace_query_failed("query output binding changed")
        binding = owned[1]
        if not _query_output_binding_current(
            workspace, binding
        ):
            raise _workspace_query_failed("query output binding changed")
        raw = binding.decoded_bytes
        if (
            len(raw) != binding.decoded_size
            or hashlib.sha256(raw).hexdigest()
            != binding.decoded_sha256
        ):
            raise _workspace_query_failed(
                "query decoded snapshot changed"
            )
        if not _query_output_binding_current(workspace, binding):
            raise _workspace_query_failed("query output binding changed")
    else:
        raw = _bounded_regular_file(path, _MAX_DECODED_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (AnalyzerError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, MemoryError, RecursionError) as exc:
        if isinstance(exc, AnalyzerError):
            raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL output could not be read safely.") from exc
        raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL output could not be read safely.") from exc
    if (
        binding is not None
        and workspace is not None
        and not _query_output_binding_current(workspace, binding)
    ):
        raise _workspace_query_failed("query output binding changed")
    if not isinstance(value, Mapping):
        raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL output must be an object.")
    return value


def _selected_entry_queries(source_root: Path, *, formal: bool) -> tuple[tuple[str, ...], bool]:
    del source_root, formal
    # Both formal runs and explicit exploratory coverage runs execute every
    # enabled P0 entry family.  Exploratory mode changes only the selected-query
    # failure policy; source-text hints must not silently reduce the canary gate.
    return _ENTRY_QUERIES, False


def _entry_gap_row(query_name: str, note: str, *, status: str = "partial") -> dict[str, object]:
    framework, protocol = _ENTRY_QUERY_FRAMEWORKS[query_name]
    return {
        "framework": framework,
        "protocol": protocol,
        "handler_fqn": f"{framework}.query_gap",
        "handler_file": f"gaps/{query_name}",
        "handler_start_line": 1,
        "registration_kind": "dynamic_unresolved",
        "registration_fqn": f"{framework}.query_gap",
        "registration_file": f"gaps/{query_name}",
        "registration_start_line": 1,
        "route_or_event": f"{framework}_query_gap",
        "auth_context": "unknown",
        "attacker_input_name": "unknown",
        "attacker_input_type": "unknown",
        "attacker_input_kind": "unknown",
        "materialization_phase": "unknown",
        "coverage_status": status,
        "coverage_note": note,
    }


def _query_files(stage: str, pack_root: Path) -> tuple[Path, ...]:
    if stage == "entries":
        return tuple(pack_root / "dosweb" / "Entries" / name for name in _ENTRY_QUERIES)
    directory = _QUERY_DIRS[stage]
    return tuple(pack_root / "dosweb" / directory / name for name in _QUERY_FAMILIES[stage])


@dataclass
class _LexicalDirectoryBinding:
    name: str
    descriptor: int
    info: os.stat_result


@dataclass
class _WorkspaceDescriptorOwner:
    """Persistent reverse-order owner for one workspace descriptor chain."""

    descriptors: list[int]
    close_capability: CloseRangeCapability
    transactions: dict[int, filesystem.DeferredCloseFdOnceOutcome] = field(
        default_factory=dict
    )
    failed: bool = False

    @staticmethod
    def _consumed(
        transaction: filesystem.DeferredCloseFdOnceOutcome,
    ) -> bool:
        return transaction.explicitly_consumed or transaction.fallback_attempted

    def close(self) -> bool:
        def release_all() -> None:
            while self.descriptors:
                descriptor = self.descriptors[-1]
                if descriptor < 0:
                    self.descriptors.pop()
                    continue
                transaction = self.transactions.get(descriptor)
                if transaction is None:
                    try:
                        transaction = filesystem.DeferredCloseFdOnceOutcome()
                    except BaseException:
                        self.failed = True
                        try:
                            os.closerange(descriptor, descriptor + 1)
                        except BaseException:
                            pass
                        self.descriptors.pop()
                        continue
                    self.transactions[descriptor] = transaction
                try:
                    succeeded = _release_workspace_descriptor_once(
                        descriptor,
                        self.close_capability,
                        transaction=transaction,
                    )
                except BaseException:
                    self.failed = True
                    if self._consumed(transaction):
                        self.descriptors.pop()
                        self.transactions.pop(descriptor, None)
                    raise
                if not self._consumed(transaction):
                    self.failed = True
                    return
                self.descriptors.pop()
                self.transactions.pop(descriptor, None)
                if not succeeded:
                    self.failed = True

        try:
            run_with_deferred_interrupts(release_all)
        except BaseException:
            self.failed = True
            try:
                run_with_deferred_interrupts(release_all)
            except BaseException:
                self.failed = True
        return not self.descriptors and not self.failed


@dataclass
class _CodeqlQueryWorkspace:
    output_root: Path
    stage: str
    name: str
    close_capability: CloseRangeCapability
    output_parent_descriptor: int
    output_parent_info: os.stat_result
    output_ancestry: tuple[_LexicalDirectoryBinding, ...]
    output_name: str
    output_descriptor: int
    output_info: os.stat_result
    workspace_descriptor: int
    workspace_info: os.stat_result
    results_descriptor: int
    results_info: os.stat_result
    query_bindings: list[_QueryOutputBinding] = field(default_factory=list)
    result_bindings: dict[int, tuple[QueryResult, _QueryOutputBinding]] = field(
        default_factory=dict
    )
    _descriptor_owner: _WorkspaceDescriptorOwner | None = field(
        default=None,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self._descriptor_owner is None:
            self._descriptor_owner = _WorkspaceDescriptorOwner(
                [
                    *(
                        lexical.descriptor
                        for lexical in self.output_ancestry
                    ),
                    self.output_descriptor,
                    self.workspace_descriptor,
                    self.results_descriptor,
                ],
                self.close_capability,
            )

    @property
    def path(self) -> Path:
        return Path(f"/proc/self/fd/{self.workspace_descriptor}")

    @property
    def results(self) -> Path:
        return Path(f"/proc/self/fd/{self.results_descriptor}")

    def close(self) -> bool:
        released = True

        def release_query_bindings() -> None:
            nonlocal released
            while self.query_bindings:
                binding = self.query_bindings[-1]
                if not _release_query_output_binding(self, binding):
                    released = False
                if any(
                    cast(int, getattr(binding, field)) >= 0
                    for field in (
                        "decoded_descriptor",
                        "generation_descriptor",
                        "generations_descriptor",
                    )
                ):
                    return
                self.query_bindings.pop()

        try:
            run_with_deferred_interrupts(release_query_bindings)
        except BaseException:
            released = False
            try:
                run_with_deferred_interrupts(release_query_bindings)
            except BaseException:
                released = False
        descriptor_owner = self._descriptor_owner
        assert descriptor_owner is not None
        descriptor_released = False
        descriptor_retry_released = False
        try:
            try:
                descriptor_released = _release_workspace_descriptors(
                    descriptor_owner,
                )
            finally:
                descriptor_retry_released = _release_workspace_descriptors(
                    descriptor_owner,
                )
        except BaseException:
            released = False
        remaining = set(descriptor_owner.descriptors)
        for field_name in (
            "results_descriptor",
            "workspace_descriptor",
            "output_descriptor",
        ):
            descriptor = cast(int, getattr(self, field_name))
            if descriptor not in remaining:
                setattr(self, field_name, -1)
        for lexical in self.output_ancestry:
            if lexical.descriptor not in remaining:
                lexical.descriptor = -1
        if not any(
            lexical.descriptor >= 0 for lexical in self.output_ancestry
        ):
            self.output_ancestry = ()
            self.output_parent_descriptor = -1
        elif self.output_parent_descriptor not in remaining:
            self.output_parent_descriptor = -1
        return (
            released
            and descriptor_released
            and descriptor_retry_released
            and not descriptor_owner.descriptors
        )


def _workspace_query_failed(
    diagnostic: str = "query workspace binding changed",
) -> AnalyzerError:
    return AnalyzerError(
        "CODEQL_QUERY_FAILED",
        "CodeQL query execution failed.",
        {
            "stage": "publication",
            "diagnostic": diagnostic,
        },
    )


def _release_workspace_descriptor_once(
    descriptor: int,
    capability: CloseRangeCapability,
    *,
    transaction: filesystem.DeferredCloseFdOnceOutcome | None = None,
) -> bool:
    if transaction is None:
        try:
            transaction = filesystem.DeferredCloseFdOnceOutcome()
        except BaseException:
            try:
                os.closerange(descriptor, descriptor + 1)
            except BaseException:
                pass
            return False
    return release_owned_descriptor_once(
        descriptor,
        capability,
        transaction=transaction,
    ).succeeded


def _release_workspace_descriptors(
    owner: _WorkspaceDescriptorOwner,
) -> bool:
    return owner.close()


def _open_owned_directory_descriptor(
    owner: list[int],
    name: str,
    *,
    dir_fd: int | None = None,
) -> int:
    """Open one directory only after reserving an owner slot.

    Trace/profile callbacks and SIGINT are deferred across the C-return to
    owner-slot assignment window.  Once instrumentation is restored, the fd is
    already reachable through ``owner`` even if restoration raises.
    """

    return _open_owned_descriptor(
        owner,
        name,
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=dir_fd,
    )


def _pin_lexical_output_ancestry(
    output_parent: Path,
    capability: CloseRangeCapability,
    owner_holder: list[tuple[_LexicalDirectoryBinding, ...]],
    descriptor_owner: _WorkspaceDescriptorOwner,
) -> tuple[_LexicalDirectoryBinding, ...]:
    owned_descriptors = descriptor_owner.descriptors
    bindings: list[_LexicalDirectoryBinding] = []
    transferred = False
    bound: tuple[_LexicalDirectoryBinding, ...] | None = None
    try:
        root_descriptor = _open_owned_directory_descriptor(
            owned_descriptors,
            "/",
        )
        root_info = os.fstat(root_descriptor)
        if not stat.S_ISDIR(root_info.st_mode):
            raise OSError("query workspace filesystem root is unsafe")
        bindings.append(
            _LexicalDirectoryBinding("", root_descriptor, root_info)
        )
        current_descriptor = root_descriptor
        for component in output_parent.parts[1:]:
            if component in {"", ".", ".."}:
                raise OSError("query workspace output ancestry is unsafe")
            descriptor = _open_owned_directory_descriptor(
                owned_descriptors,
                component,
                dir_fd=current_descriptor,
            )
            info = os.fstat(descriptor)
            named = os.stat(
                component,
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(info.st_mode) or not _same_inode(info, named):
                raise OSError("query workspace output ancestry is unsafe")
            bindings.append(
                _LexicalDirectoryBinding(component, descriptor, info)
            )
            current_descriptor = descriptor
        bound = tuple(bindings)
        append_failure: BaseException | None = None

        def transfer() -> None:
            nonlocal append_failure, transferred
            try:
                owner_holder.append(bound)
            except BaseException as exc:
                append_failure = exc
            finally:
                transferred = any(
                    item is bound
                    for item in list.__iter__(owner_holder)
                )

        run_with_deferred_interrupts(transfer)
        if append_failure is not None:
            raise append_failure
        return bound
    except BaseException as exc:
        if transferred:
            raise
        released = False
        retry_released = False
        try:
            released = _release_workspace_descriptors(descriptor_owner)
        finally:
            retry_released = _release_workspace_descriptors(descriptor_owner)
        if not released or not retry_released:
            raise _workspace_query_failed(
                "query workspace ancestry release failed"
            ) from exc
        raise


def _release_query_output_binding(
    workspace: _CodeqlQueryWorkspace,
    binding: _QueryOutputBinding,
) -> bool:
    released = True

    def release_binding() -> None:
        nonlocal released
        for binding_field in (
            "decoded_descriptor",
            "generation_descriptor",
            "generations_descriptor",
        ):
            descriptor = cast(int, getattr(binding, binding_field))
            setattr(binding, binding_field, -1)
            if descriptor >= 0 and not _release_workspace_descriptor_once(
                descriptor,
                workspace.close_capability,
            ):
                released = False

    try:
        run_with_deferred_interrupts(release_binding)
    except BaseException:
        released = False
    return released


def _same_inode(first: os.stat_result, second: os.stat_result) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _bound_owner_directory(
    current: os.stat_result,
    expected: os.stat_result,
    *,
    exact_mode: int | None,
) -> bool:
    return (
        stat.S_ISDIR(current.st_mode)
        and _same_inode(current, expected)
        and current.st_uid == os.getuid()
        and (
            exact_mode is None
            or stat.S_IMODE(current.st_mode) == exact_mode
        )
    )


def _optional_stat_at(
    directory_descriptor: int,
    name: str,
) -> os.stat_result | None:
    try:
        return os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None


def _workspace_bindings_current(workspace: _CodeqlQueryWorkspace) -> bool:
    try:
        if not workspace.output_ancestry:
            return False
        previous: _LexicalDirectoryBinding | None = None
        for lexical in workspace.output_ancestry:
            opened_ancestor = os.fstat(lexical.descriptor)
            if (
                not stat.S_ISDIR(opened_ancestor.st_mode)
                or not _same_inode(opened_ancestor, lexical.info)
                or opened_ancestor.st_uid != lexical.info.st_uid
                or stat.S_IMODE(opened_ancestor.st_mode)
                != stat.S_IMODE(lexical.info.st_mode)
            ):
                return False
            if previous is not None:
                named_ancestor = os.stat(
                    lexical.name,
                    dir_fd=previous.descriptor,
                    follow_symlinks=False,
                )
                if not _same_inode(named_ancestor, lexical.info):
                    return False
            previous = lexical
        assert previous is not None
        if (
            previous.descriptor != workspace.output_parent_descriptor
            or not _same_inode(previous.info, workspace.output_parent_info)
        ):
            return False
        opened_parent = os.fstat(workspace.output_parent_descriptor)
        output = os.fstat(workspace.output_descriptor)
        named_output = os.stat(
            workspace.output_name,
            dir_fd=workspace.output_parent_descriptor,
            follow_symlinks=False,
        )
        opened_workspace = os.fstat(workspace.workspace_descriptor)
        named_workspace = os.stat(
            workspace.name,
            dir_fd=workspace.output_descriptor,
            follow_symlinks=False,
        )
        opened_results = os.fstat(workspace.results_descriptor)
        named_results = os.stat(
            "results",
            dir_fd=workspace.workspace_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False
    return (
        stat.S_ISDIR(opened_parent.st_mode)
        and _same_inode(opened_parent, workspace.output_parent_info)
        and opened_parent.st_uid == workspace.output_parent_info.st_uid
        and stat.S_IMODE(opened_parent.st_mode)
        == stat.S_IMODE(workspace.output_parent_info.st_mode)
        and _same_inode(named_output, workspace.output_info)
        and _bound_owner_directory(
            output,
            workspace.output_info,
            exact_mode=stat.S_IMODE(workspace.output_info.st_mode),
        )
        and _bound_owner_directory(
            opened_workspace,
            workspace.workspace_info,
            exact_mode=0o700,
        )
        and _same_inode(named_workspace, workspace.workspace_info)
        and _bound_owner_directory(
            opened_results,
            workspace.results_info,
            exact_mode=0o700,
        )
        and _same_inode(named_results, workspace.results_info)
    )


def _query_output_binding_current(
    workspace: _CodeqlQueryWorkspace,
    binding: _QueryOutputBinding,
) -> bool:
    if not _workspace_bindings_current(workspace):
        return False
    try:
        if binding.generations_descriptor >= 0:
            opened_generations = os.fstat(
                binding.generations_descriptor
            )
            named_generations = os.stat(
                ".generations",
                dir_fd=workspace.results_descriptor,
                follow_symlinks=False,
            )
            if not (
                _bound_owner_directory(
                    opened_generations,
                    binding.generations_info,
                    exact_mode=0o700,
                )
                and _same_inode(
                    named_generations, binding.generations_info
                )
            ):
                return False
        if binding.generation_descriptor >= 0:
            if binding.generations_descriptor < 0:
                return False
            opened_generation = os.fstat(binding.generation_descriptor)
            named_generation = os.stat(
                binding.generation_name,
                dir_fd=binding.generations_descriptor,
                follow_symlinks=False,
            )
            if not (
                _bound_owner_directory(
                    opened_generation,
                    binding.generation_info,
                    exact_mode=0o700,
                )
                and _same_inode(
                    named_generation, binding.generation_info
                )
            ):
                return False
        if binding.decoded_parent == "generation":
            decoded_parent = binding.generation_descriptor
        elif binding.decoded_parent == "results":
            decoded_parent = workspace.results_descriptor
        else:
            return False
        if decoded_parent < 0:
            return False
        opened_decoded = os.fstat(binding.decoded_descriptor)
        named_decoded = os.stat(
            binding.decoded_name,
            dir_fd=decoded_parent,
            follow_symlinks=False,
        )
    except OSError:
        return False
    metadata_current = (
        stat.S_ISREG(opened_decoded.st_mode)
        and _same_inode(opened_decoded, binding.decoded_info)
        and _same_inode(named_decoded, binding.decoded_info)
        and opened_decoded.st_uid == os.getuid()
        and stat.S_IMODE(opened_decoded.st_mode)
        == stat.S_IMODE(binding.decoded_info.st_mode)
        and opened_decoded.st_size <= _MAX_DECODED_BYTES
    )
    if not metadata_current:
        return False
    try:
        current_bytes = _bounded_decoded_descriptor(
            binding.decoded_descriptor
        )
    except AnalyzerError:
        return False
    return (
        len(current_bytes) == binding.decoded_size
        and hashlib.sha256(current_bytes).hexdigest()
        == binding.decoded_sha256
    )


def _result_relative_to_workspace(
    workspace: _CodeqlQueryWorkspace,
    result: QueryResult,
) -> Path:
    decoded = Path(result.decoded_path)
    candidates = (workspace.results,)
    try:
        stable_results = Path(
            os.readlink(
                f"/proc/self/fd/{workspace.results_descriptor}"
            )
        )
    except OSError:
        stable_results = workspace.results
    candidates = (*candidates, stable_results)
    for root in candidates:
        try:
            relative = decoded.relative_to(root)
        except ValueError:
            continue
        if (
            relative != Path(".")
            and not relative.is_absolute()
            and ".." not in relative.parts
        ):
            return relative
    raise _workspace_query_failed("query result path is outside workspace")


def _register_query_output_binding(
    workspace: _CodeqlQueryWorkspace,
    result: QueryResult,
    binding: _QueryOutputBinding,
) -> _QueryOutputBinding:
    append_failure: BaseException | None = None
    try:
        workspace.query_bindings.append(binding)
    except BaseException as exc:
        append_failure = exc
    finally:
        registered = any(
            item is binding for item in workspace.query_bindings
        )
        if registered:
            binding.attached = True
    if append_failure is not None:
        if not registered:
            _release_query_output_binding(workspace, binding)
        raise _workspace_query_failed(
            "query output binding registration failed"
        ) from append_failure
    try:
        workspace.result_bindings[id(result)] = (result, binding)
    except BaseException as exc:
        raise _workspace_query_failed(
            "query output binding registration failed"
        ) from exc
    return binding


def _capture_query_output_binding(
    workspace: _CodeqlQueryWorkspace,
    result: QueryResult,
) -> _QueryOutputBinding:
    supplied = result._output_binding
    if supplied is not None:
        if supplied.attached:
            raise _workspace_query_failed(
                "query output binding was reused"
            )
        if not _query_output_binding_current(workspace, supplied):
            _release_query_output_binding(workspace, supplied)
            raise _workspace_query_failed(
                "query output binding changed"
            )
        return _register_query_output_binding(
            workspace,
            result,
            supplied,
        )

    relative = _result_relative_to_workspace(workspace, result)
    if len(relative.parts) == 3 and relative.parts[0] == ".generations":
        pin_owner: list[_QueryOutputBinding] = []
        try:
            _pin_query_output_binding(
                workspace.results_descriptor,
                relative.parts[1],
                relative.parts[2],
                workspace.close_capability,
                owner_holder=pin_owner,
            )
        except BaseException:
            if pin_owner:
                _release_query_output_binding(workspace, pin_owner[0])
            raise
        binding = pin_owner[0]
        if not _query_output_binding_current(workspace, binding):
            _release_query_output_binding(workspace, binding)
            raise _workspace_query_failed(
                "query output binding changed"
            )
        return _register_query_output_binding(
            workspace,
            result,
            binding,
        )
    if len(relative.parts) != 1:
        raise _workspace_query_failed("query result path is unsafe")

    fallback_owner: list[int] = []
    fallback_descriptor_owner = _WorkspaceDescriptorOwner(
        fallback_owner,
        workspace.close_capability,
    )
    generations_descriptor = -1
    binding: _QueryOutputBinding | None = None
    try:
        try:
            generations_descriptor = _open_owned_descriptor(
                fallback_owner,
                ".generations",
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=workspace.results_descriptor,
            )
        except FileNotFoundError:
            generations_info = workspace.results_info
        else:
            generations_info = os.fstat(generations_descriptor)
            named_generations = os.stat(
                ".generations",
                dir_fd=workspace.results_descriptor,
                follow_symlinks=False,
            )
            if not _bound_owner_directory(
                generations_info,
                named_generations,
                exact_mode=0o700,
            ):
                raise OSError("query generations binding changed")
        decoded_name = relative.parts[0]
        decoded_descriptor = _open_owned_descriptor(
            fallback_owner,
            decoded_name,
            os.O_RDONLY
            | os.O_NONBLOCK
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=workspace.results_descriptor,
        )
        decoded_info = os.fstat(decoded_descriptor)
        named_decoded = os.stat(
            decoded_name,
            dir_fd=workspace.results_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(decoded_info.st_mode)
            or not _same_inode(decoded_info, named_decoded)
            or decoded_info.st_uid != os.getuid()
            or decoded_info.st_size > _MAX_DECODED_BYTES
        ):
            raise OSError("query decoded output binding changed")
        decoded_bytes = _bounded_decoded_descriptor(decoded_descriptor)
        rebound_decoded = os.fstat(decoded_descriptor)
        rebound_name = os.stat(
            decoded_name,
            dir_fd=workspace.results_descriptor,
            follow_symlinks=False,
        )
        if (
            not _same_inode(rebound_decoded, decoded_info)
            or not _same_inode(rebound_name, decoded_info)
            or rebound_decoded.st_size != len(decoded_bytes)
        ):
            raise OSError("query decoded output changed during capture")
        binding = _QueryOutputBinding(
            close_capability=workspace.close_capability,
            generations_descriptor=generations_descriptor,
            generations_info=generations_info,
            generation_name="",
            generation_descriptor=-1,
            generation_info=workspace.results_info,
            decoded_name=decoded_name,
            decoded_descriptor=decoded_descriptor,
            decoded_info=rebound_decoded,
            decoded_size=len(decoded_bytes),
            decoded_sha256=hashlib.sha256(decoded_bytes).hexdigest(),
            decoded_bytes=decoded_bytes,
            decoded_parent="results",
        )
        if not _query_output_binding_current(workspace, binding):
            raise OSError("query output binding changed")
        return _register_query_output_binding(
            workspace,
            result,
            binding,
        )
    except BaseException as exc:
        registered = binding is not None and any(
            item is binding for item in workspace.query_bindings
        )
        if registered:
            released = True
        elif binding is not None:
            released = _release_query_output_binding(
                workspace,
                binding,
            )
        else:
            released = False
            retry_released = False
            try:
                released = _release_workspace_descriptors(
                    fallback_descriptor_owner,
                )
            finally:
                retry_released = _release_workspace_descriptors(
                    fallback_descriptor_owner,
                )
            released = released and retry_released
        if isinstance(exc, AnalyzerError) and released:
            raise
        raise _workspace_query_failed(
            "query output binding failed"
        ) from exc


def _create_codeql_query_workspace(
    output_root: Path,
    stage: str,
    *,
    owner_holder: list[_CodeqlQueryWorkspace] | None = None,
) -> _CodeqlQueryWorkspace:
    try:
        close_capability = require_close_fd_once()
    except BaseException as exc:
        raise _workspace_query_failed(
            "query workspace release capability unavailable"
        ) from exc
    absolute_output = output_root.absolute()
    output_name = absolute_output.name
    if not output_name:
        raise _workspace_query_failed("query workspace output root is unsafe")
    ancestry_owner: list[tuple[_LexicalDirectoryBinding, ...]] = []
    descriptor_owner = _WorkspaceDescriptorOwner([], close_capability)
    directory_owner = descriptor_owner.descriptors
    workspace: _CodeqlQueryWorkspace | None = None
    workspace_owned = False
    try:
        output_ancestry = _pin_lexical_output_ancestry(
            absolute_output.parent,
            close_capability,
            ancestry_owner,
            descriptor_owner,
        )
        output_parent_descriptor = output_ancestry[-1].descriptor
        output_parent_info = output_ancestry[-1].info
        output_descriptor = _open_owned_directory_descriptor(
            directory_owner,
            output_name,
            dir_fd=output_parent_descriptor,
        )
        output_info = os.fstat(output_descriptor)
        named_output = os.stat(
            output_name,
            dir_fd=output_parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(output_info.st_mode)
            or output_info.st_uid != os.getuid()
            or not _same_inode(named_output, output_info)
        ):
            raise OSError("query workspace output root is unsafe")
        name = ""
        for _ in range(128):
            candidate = f".dosweb-{stage}-queries-{uuid.uuid4().hex}"
            try:
                os.mkdir(
                    candidate,
                    mode=0o700,
                    dir_fd=output_descriptor,
                )
            except FileExistsError:
                continue
            name = candidate
            break
        if not name:
            raise OSError("could not allocate query workspace")
        workspace_descriptor = _open_owned_directory_descriptor(
            directory_owner,
            name,
            dir_fd=output_descriptor,
        )
        workspace_info = os.fstat(workspace_descriptor)
        named_workspace = os.stat(
            name,
            dir_fd=output_descriptor,
            follow_symlinks=False,
        )
        if (
            not _bound_owner_directory(
                workspace_info,
                named_workspace,
                exact_mode=0o700,
            )
        ):
            raise OSError("query workspace root changed")
        os.mkdir("results", mode=0o700, dir_fd=workspace_descriptor)
        results_descriptor = _open_owned_directory_descriptor(
            directory_owner,
            "results",
            dir_fd=workspace_descriptor,
        )
        results_info = os.fstat(results_descriptor)
        named_results = os.stat(
            "results",
            dir_fd=workspace_descriptor,
            follow_symlinks=False,
        )
        if not _bound_owner_directory(
            results_info,
            named_results,
            exact_mode=0o700,
        ):
            raise OSError("query workspace results changed")
        workspace = _CodeqlQueryWorkspace(
            output_root=absolute_output,
            stage=stage,
            name=name,
            close_capability=close_capability,
            output_parent_descriptor=output_parent_descriptor,
            output_parent_info=output_parent_info,
            output_ancestry=tuple(output_ancestry),
            output_name=output_name,
            output_descriptor=output_descriptor,
            output_info=output_info,
            workspace_descriptor=workspace_descriptor,
            workspace_info=workspace_info,
            results_descriptor=results_descriptor,
            results_info=results_info,
            _descriptor_owner=descriptor_owner,
        )
        if owner_holder is not None:
            append_failure: BaseException | None = None

            def transfer() -> None:
                nonlocal append_failure, workspace_owned
                try:
                    owner_holder.append(workspace)
                except BaseException as exc:
                    append_failure = exc
                finally:
                    workspace_owned = any(
                        item is workspace
                        for item in list.__iter__(owner_holder)
                    )

            run_with_deferred_interrupts(transfer)
            if append_failure is not None:
                raise _workspace_query_failed(
                    "query workspace owner registration failed"
                ) from append_failure
        return workspace
    except BaseException as exc:
        if workspace is not None and owner_holder is not None:
            workspace_owned = workspace_owned or any(
                item is workspace
                for item in list.__iter__(owner_holder)
            )
        if workspace_owned:
            raise
        released_workspace_chain = False
        retry_released_workspace_chain = False
        try:
            released_workspace_chain = _release_workspace_descriptors(
                descriptor_owner,
            )
        finally:
            retry_released_workspace_chain = _release_workspace_descriptors(
                descriptor_owner,
            )
        if (
            not released_workspace_chain
            or not retry_released_workspace_chain
            or isinstance(exc, Exception)
        ):
            raise _workspace_query_failed(
                "query workspace creation failed"
            ) from exc
        raise


def _workspace_has_safe_generation_inventory(
    workspace: _CodeqlQueryWorkspace,
) -> bool:
    if not _workspace_bindings_current(workspace):
        return False
    pinned = [
        binding
        for binding in workspace.query_bindings
        if binding.generations_descriptor >= 0
    ]
    if pinned:
        expected = pinned[0].generations_info
        if any(
            not _same_inode(binding.generations_info, expected)
            or not _query_output_binding_current(workspace, binding)
            for binding in workspace.query_bindings
        ):
            return False
        try:
            with os.scandir(
                pinned[0].generations_descriptor
            ) as entries:
                for index, entry in enumerate(entries):
                    if index >= _MAX_ENTRY_ROWS or entry.name.startswith("."):
                        return False
            rebound = os.fstat(pinned[0].generations_descriptor)
            named = os.stat(
                ".generations",
                dir_fd=workspace.results_descriptor,
                follow_symlinks=False,
            )
        except OSError:
            return False
        return (
            _bound_owner_directory(
                rebound,
                expected,
                exact_mode=0o700,
            )
            and _same_inode(named, expected)
            and all(
                _query_output_binding_current(workspace, binding)
                for binding in workspace.query_bindings
            )
            and _workspace_bindings_current(workspace)
        )
    inventory_owner: list[int] = []
    inventory_descriptor_owner = _WorkspaceDescriptorOwner(
        inventory_owner,
        workspace.close_capability,
    )
    safe = False
    try:
        try:
            generations_descriptor = _open_owned_descriptor(
                inventory_owner,
                ".generations",
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=workspace.results_descriptor,
            )
        except FileNotFoundError:
            return _workspace_bindings_current(workspace)
        except OSError:
            return False
        expected = os.fstat(generations_descriptor)
        named = os.stat(
            ".generations",
            dir_fd=workspace.results_descriptor,
            follow_symlinks=False,
        )
        safe = _bound_owner_directory(
            expected,
            named,
            exact_mode=0o700,
        )
        if safe:
            with os.scandir(generations_descriptor) as entries:
                for index, entry in enumerate(entries):
                    if index >= _MAX_ENTRY_ROWS or entry.name.startswith("."):
                        safe = False
                        break
        if safe:
            rebound_descriptor = os.fstat(generations_descriptor)
            rebound_name = os.stat(
                ".generations",
                dir_fd=workspace.results_descriptor,
                follow_symlinks=False,
            )
            safe = (
                _bound_owner_directory(
                    rebound_descriptor,
                    expected,
                    exact_mode=0o700,
                )
                and _same_inode(rebound_name, expected)
                and _workspace_bindings_current(workspace)
            )
    except OSError:
        safe = False
    finally:
        released_inventory = False
        retry_released_inventory = False
        try:
            released_inventory = _release_workspace_descriptors(
                inventory_descriptor_owner,
            )
        finally:
            retry_released_inventory = _release_workspace_descriptors(
                inventory_descriptor_owner,
            )
        if not released_inventory or not retry_released_inventory:
            safe = False
    return safe


def _isolate_codeql_query_workspace(
    workspace: _CodeqlQueryWorkspace,
) -> bool:
    if not _workspace_bindings_current(workspace):
        return False
    for _ in range(128):
        candidate = (
            f".dosweb-{workspace.stage}-quarantine-{uuid.uuid4().hex}"
        )
        failure: BaseException | None = None
        try:
            renameat2_no_replace(
                workspace.output_descriptor,
                workspace.name,
                workspace.output_descriptor,
                candidate,
            )
        except BaseException as exc:
            failure = exc
        source = _optional_stat_at(
            workspace.output_descriptor,
            workspace.name,
        )
        destination = _optional_stat_at(
            workspace.output_descriptor,
            candidate,
        )
        if (
            source is None
            and destination is not None
            and _same_inode(destination, workspace.workspace_info)
        ):
            workspace.name = candidate
            try:
                os.fsync(workspace.output_descriptor)
            except OSError:
                return False
            return _workspace_bindings_current(workspace)
        if (
            isinstance(failure, FileExistsError)
            and source is not None
            and _same_inode(source, workspace.workspace_info)
            and destination is not None
            and not _same_inode(destination, workspace.workspace_info)
        ):
            continue
        return False
    return False


def _cleanup_codeql_query_workspace(
    workspace: _CodeqlQueryWorkspace,
) -> bool:
    """Isolate and retain only a fully bound workspace with no hidden output."""

    safe = False
    try:
        if _workspace_has_safe_generation_inventory(workspace):
            safe = _isolate_codeql_query_workspace(workspace)
    except BaseException:
        safe = False
    finally:
        released = False
        retry_released = False
        try:
            released = workspace.close()
        finally:
            retry_released = workspace.close()
        released = released and retry_released
    return safe and released


def _require_workspace_bindings(
    workspace: _CodeqlQueryWorkspace,
) -> None:
    if not _workspace_bindings_current(workspace):
        raise _workspace_query_failed()


def _run_workspace_query(
    workspace: _CodeqlQueryWorkspace,
    runner: Callable[..., QueryResult],
    query: Path,
    database: DatabaseInfo,
    config: AnalyzerConfig,
) -> QueryResult:
    _require_workspace_bindings(workspace)
    def own_result(result: QueryResult) -> None:
        if not isinstance(result, QueryResult):
            raise _workspace_query_failed(
                "query runner ownership result is invalid"
            )
        owned = workspace.result_bindings.get(id(result))
        if owned is not None and owned[0] is result:
            raise _workspace_query_failed(
                "query output binding was reused"
            )
        _capture_query_output_binding(workspace, result)

    try:
        result = runner(
            query,
            database,
            workspace.results,
            output_descriptor=workspace.results_descriptor,
            retain_output_binding=True,
            result_owner_callback=own_result,
            codeql_binary=config.codeql_binary,
            timeout_seconds=_CODEQL_TIMEOUT_SECONDS,
        )
    except BaseException as exc:
        if not _workspace_bindings_current(workspace):
            raise _workspace_query_failed() from exc
        raise
    if isinstance(result, QueryResult):
        owned = workspace.result_bindings.get(id(result))
        if owned is None or owned[0] is not result:
            _capture_query_output_binding(workspace, result)
    _require_workspace_bindings(workspace)
    return result


def _run_codeql_family(config: AnalyzerConfig, database: DatabaseInfo, stage: str, query_root: Path, runner: Callable[..., QueryResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    workspace_owner: list[_CodeqlQueryWorkspace] = []
    workspace: _CodeqlQueryWorkspace | None = None
    try:
        workspace = _create_codeql_query_workspace(
            config.output,
            stage,
            owner_holder=workspace_owner,
        )
        for query in _query_files(stage, query_root):
            result = _run_workspace_query(
                workspace,
                runner,
                query,
                database,
                config,
            )
            if not isinstance(result, QueryResult):
                raise AnalyzerError("CODEQL_QUERY_FAILED", "The query runner returned an invalid result.")
            if not _workspace_has_safe_generation_inventory(workspace):
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                    {
                        "stage": "publication",
                        "diagnostic": "retained hidden query quarantine",
                    },
                )
            _require_workspace_bindings(workspace)
            payload = _bounded_json_file(result, workspace)
            _require_workspace_bindings(workspace)
            if stage == "growth":
                family = "growth"
            elif stage in {"flows", "associations"}:
                family = "flow"
            else:
                lowered = query.stem.lower()
                family = "lifecycle_summary" if "lifecyclesummary" in lowered else "lifecycle_coverage" if "lifecyclecoverage" in lowered else "guard" if "guard" in lowered else "bound" if "bound" in lowered else "release"
            decoded = decode_bqrs_json(family, payload, DecodeSource(database.source_root, result.query_sha256))
            _require_workspace_bindings(workspace)
            if len(rows) + len(decoded) > _MAX_ENTRY_ROWS:
                raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL output exceeds the aggregate row limit.")
            rows.extend({"query_name": family, **item} for item in decoded)
    except BaseException as exc:
        owned_workspace = (
            workspace_owner[0] if workspace_owner else workspace
        )
        cleanup_succeeded = owned_workspace is None
        cleanup_retry_succeeded = owned_workspace is None
        if owned_workspace is not None:
            try:
                cleanup_succeeded = _cleanup_codeql_query_workspace(
                    owned_workspace
                )
            finally:
                cleanup_retry_succeeded = _cleanup_codeql_query_workspace(
                    owned_workspace
                )
        if not cleanup_succeeded and not cleanup_retry_succeeded:
            raise _workspace_query_failed() from exc
        raise
    assert workspace is not None
    cleanup_succeeded = False
    cleanup_retry_succeeded = False
    try:
        cleanup_succeeded = _cleanup_codeql_query_workspace(workspace)
    finally:
        cleanup_retry_succeeded = _cleanup_codeql_query_workspace(workspace)
    if not cleanup_succeeded and not cleanup_retry_succeeded:
        raise AnalyzerError(
            "CODEQL_QUERY_FAILED",
            "CodeQL query execution failed.",
            {
                "stage": "publication",
                "diagnostic": "retained unsafe query workspace",
            },
        )
    return rows


def _extract_entry_security_facts(entries: Sequence[Mapping[str, object]], source_root: Path) -> list[dict[str, object]]:
    """Compatibility wrapper for the partial-only source text fallback."""
    return [fact.to_dict() for fact in extract_entry_security_fallback(entries, source_root)]


def make_entries_executor(config: AnalyzerConfig, *, validate_database_fn: Callable[..., DatabaseInfo] | None = None, run_query_fn: Callable[..., QueryResult] | None = None, database_info_fn: Callable[[], DatabaseInfo] | None = None, query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]] | None = None, query_dir: Path = _ENTRY_QUERY_DIR) -> Executor:
    validate = validate_database_fn or globals()["validate_database"]
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        database = database_info_fn() if database_info_fn else validate(config.database)
        if not isinstance(database, DatabaseInfo):
            raise AnalyzerError("CODEQL_DATABASE_INVALID", "CodeQL database validation failed.")
        selected_queries, evidence_scan_truncated = _selected_entry_queries(database.source_root, formal=not config.allow_partial_codeql)
        workspace_owner: list[_CodeqlQueryWorkspace] = []
        workspace: _CodeqlQueryWorkspace | None = None
        try:
            workspace = _create_codeql_query_workspace(
                config.output,
                "entry",
                owner_holder=workspace_owner,
            )
            with tempfile.TemporaryDirectory(prefix="dosweb-entry-pack-") as temporary:
                root = Path(temporary) / "pack"
                if query_pack_snapshot_fn:
                    effective = _materialize_query_pack(root, query_pack_snapshot_fn()) / "dosweb" / "Entries"
                else:
                    effective = query_dir
                rows: list[dict[str, object]] = []
                skipped_queries = 0
                query_diagnostics: list[dict[str, object]] = []
                selected_names = frozenset(selected_queries)
                for name in _ENTRY_QUERIES:
                    if name in selected_names:
                        continue
                    reason = "framework_evidence_scan_truncated" if evidence_scan_truncated else "framework_evidence_absent"
                    rows.append(_entry_gap_row(
                        name,
                        f"{reason}:{Path(name).stem}",
                        status="partial" if evidence_scan_truncated else "unsupported",
                    ))
                for name in selected_queries:
                    try:
                        result = _run_workspace_query(
                            workspace,
                            runner,
                            effective / name,
                            database,
                            config,
                        )
                    except AnalyzerError as exc:
                        if exc.code != "CODEQL_QUERY_FAILED" or not config.allow_partial_codeql:
                            # Formal runs never publish an entries stage after a selected query fails.
                            raise
                        skipped_queries += 1
                        rows.append(_entry_gap_row(name, f"query_failed:{Path(name).stem}"))
                        diagnostic: dict[str, object] = {
                            "code": exc.code,
                            "query_name": name,
                        }
                        for field in ("stage", "diagnostic", "returncode"):
                            value = exc.details.get(field)
                            if field == "returncode" and isinstance(value, int) and not isinstance(value, bool):
                                diagnostic[field] = value
                            elif field != "returncode" and isinstance(value, str) and value:
                                diagnostic[field] = value[:512]
                        query_diagnostics.append(diagnostic)
                        continue
                    if not isinstance(result, QueryResult):
                        raise AnalyzerError("CODEQL_QUERY_FAILED", "The entry query runner returned an invalid result.")
                    _require_workspace_bindings(workspace)
                    payload = _bounded_json_file(result, workspace)
                    _require_workspace_bindings(workspace)
                    rows.extend(decode_bqrs_json("entries", payload, DecodeSource(database.source_root, result.query_sha256)))
                    _require_workspace_bindings(workspace)
                    if len(rows) > _MAX_ENTRY_ROWS:
                        raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL entry output exceeds the aggregate row limit.")
                try:
                    result = _run_workspace_query(
                        workspace,
                        runner,
                        effective / _INTERPOSITION_QUERY,
                        database,
                        config,
                    )
                except AnalyzerError as exc:
                    if exc.code != "CODEQL_QUERY_FAILED" or not config.allow_partial_codeql:
                        raise
                    skipped_queries += 1
                    query_diagnostics.append({"code": exc.code, "query_name": _INTERPOSITION_QUERY})
                    interposition_rows: list[dict[str, object]] = []
                else:
                    if not isinstance(result, QueryResult):
                        raise AnalyzerError("CODEQL_QUERY_FAILED", "The interposition query runner returned an invalid result.")
                    _require_workspace_bindings(workspace)
                    payload = _bounded_json_file(result, workspace)
                    _require_workspace_bindings(workspace)
                    interposition_rows = decode_bqrs_json("entry_interposition", payload, DecodeSource(database.source_root, result.query_sha256))
                    _require_workspace_bindings(workspace)
                try:
                    result = _run_workspace_query(
                        workspace,
                        runner,
                        effective / _SECURITY_QUERY,
                        database,
                        config,
                    )
                except AnalyzerError as exc:
                    if exc.code != "CODEQL_QUERY_FAILED" or not config.allow_partial_codeql:
                        raise
                    skipped_queries += 1
                    query_diagnostics.append({"code": exc.code, "query_name": _SECURITY_QUERY})
                    security_rows: list[dict[str, object]] = []
                else:
                    if not isinstance(result, QueryResult):
                        raise AnalyzerError("CODEQL_QUERY_FAILED", "The Entry security query runner returned an invalid result.")
                    _require_workspace_bindings(workspace)
                    payload = _bounded_json_file(result, workspace)
                    _require_workspace_bindings(workspace)
                    security_rows = decode_bqrs_json("entry_security", payload, DecodeSource(database.source_root, result.query_sha256))
                    _require_workspace_bindings(workspace)
        except BaseException as exc:
            owned_workspace = (
                workspace_owner[0] if workspace_owner else workspace
            )
            cleanup_succeeded = owned_workspace is None
            cleanup_retry_succeeded = owned_workspace is None
            if owned_workspace is not None:
                try:
                    cleanup_succeeded = _cleanup_codeql_query_workspace(
                        owned_workspace
                    )
                finally:
                    cleanup_retry_succeeded = _cleanup_codeql_query_workspace(
                        owned_workspace
                    )
            if not cleanup_succeeded and not cleanup_retry_succeeded:
                raise _workspace_query_failed() from exc
            raise
        assert workspace is not None
        cleanup_succeeded = False
        cleanup_retry_succeeded = False
        try:
            cleanup_succeeded = _cleanup_codeql_query_workspace(workspace)
        finally:
            cleanup_retry_succeeded = _cleanup_codeql_query_workspace(
                workspace
            )
        retained_hidden_output = (
            not cleanup_succeeded and not cleanup_retry_succeeded
        )
        if retained_hidden_output and not config.allow_partial_codeql:
            raise AnalyzerError(
                "CODEQL_QUERY_FAILED",
                "CodeQL query execution failed.",
                {
                    "stage": "publication",
                    "diagnostic": "retained hidden query quarantine",
                },
            )
        rows, descriptor_coverage = resolve_webxml_servlet_candidates(rows, database.source_root)
        validate_descriptor_coverage(descriptor_coverage)
        rows = augment_source_backed_jaxrs_entries(rows, database.source_root)
        entries = normalize_entry_rows(rows); coverage = normalize_framework_coverage(rows)
        entry_gaps = normalize_gap_entry_rows(rows)
        interpositions = _normalize_interposition_rows(interposition_rows, entries)
        validate_records("entry_facts", entries)
        validate_records("entry_gap_facts", entry_gaps)
        validate_references("entry_interposition_facts", interpositions, {"entry_id": {str(entry["entry_id"]) for entry in entries}})
        modeled_defaults, configuration_coverage = extract_modeled_configuration_with_coverage(database.source_root, config.modeled_defaults)
        validate_records("modeled_configuration", modeled_defaults)
        typed_security = bind_entry_security_rows(security_rows, entries)
        explicit_deployment_entries = frozenset(
            fact.entry_id for fact in typed_security if fact.kind == "deployment_gate"
        )
        deployment_defaults = extract_entry_deployment_defaults(
            entries,
            excluded_entry_ids=explicit_deployment_entries,
        )
        complete_auth_entries = {
            fact.entry_id
            for fact in typed_security
            if fact.coverage == "complete" and fact.kind != "deployment_gate"
        }
        fallback_security = tuple(
            fact
            for fact in extract_entry_security_fallback(entries, database.source_root)
            if fact.entry_id not in complete_auth_entries
        )
        security_facts = {
            fact.fact_id: fact
            for fact in (*typed_security, *deployment_defaults, *fallback_security)
        }
        security = [fact.to_dict() for fact in sorted(security_facts.values(), key=lambda item: item.fact_id)]
        validate_references("entry_security_facts", security, {"entry_id": {str(entry["entry_id"]) for entry in entries}})
        return StageOutput(
            {"entry_facts.jsonl": entries, "entry_gap_facts.jsonl": entry_gaps, "entry_interposition_facts.jsonl": interpositions, "coverage.json": canonical_json(coverage) + b"\n", "configuration_coverage.json": canonical_json(configuration_coverage) + b"\n", "descriptor_coverage.json": canonical_json(descriptor_coverage) + b"\n", "modeled_configuration.jsonl": modeled_defaults, "entry_security_facts.jsonl": security},
            {
                "database_fingerprint": database.fingerprint,
                "query_count": len(selected_queries) + 2,
                "skipped_query_count": skipped_queries,
                "query_diagnostics": query_diagnostics,
                "entry_evidence_scan_truncated": evidence_scan_truncated,
                "analysis_mode": "exploratory_entries" if config.allow_partial_codeql else "formal",
                "query_failure_policy": "coverage_gap" if config.allow_partial_codeql else "fail_closed",
            },
        )
    return execute


def _upstream_bytes(context: StageContext, stage: str, artifact: str) -> bytes:
    return read_upstream_artifact_bytes(
        context.output_root,
        context.upstream,
        stage,
        artifact,
        schema_version=ARTIFACT_SCHEMA_VERSION,
    )


def _records(context: StageContext, stage: str, artifact: str, schema: str) -> list[dict[str, object]]:
    records = read_jsonl_bytes_strict(_upstream_bytes(context, stage, artifact), schema, source_name=artifact)
    validate_records(schema, records)
    return records


def _strict_records(context: StageContext, stage: str, artifact: str) -> list[dict[str, object]]:
    """Read a strict JSONL artifact from its authenticated byte snapshot."""
    schema = artifact.removesuffix(".jsonl")
    records = read_jsonl_bytes_strict(
        _upstream_bytes(context, stage, artifact),
        schema,
        source_name=artifact,
    )
    validate_records(schema, records)
    return records


def _coverage(context: StageContext) -> tuple[FrameworkCoverage, ...]:
    value = json.loads(_upstream_bytes(context, "entries", "coverage.json").decode("utf-8"))
    if not isinstance(value, list):
        raise AnalyzerError("ARTIFACT_INVALID_JSON", "Coverage artifact must be a list.")
    result = tuple(FrameworkCoverage(item["framework"], item["status"], tuple(item["supported_patterns"]), tuple(item["unsupported_patterns"]), item["effect_on_verdict"]) for item in value if isinstance(item, Mapping))
    if len(result) != len(value):
        raise AnalyzerError("ARTIFACT_INVALID_JSON", "Coverage artifact is malformed.")
    return result


def _load_entries(context: StageContext) -> dict[str, EntryFact]:
    facts = tuple(EntryFact.from_dict(record) for record in _records(context, "entries", "entry_facts.jsonl", "entry_facts"))
    if len({fact.entry_id for fact in facts}) != len(facts):
        raise AnalyzerError("ARTIFACT_SCHEMA_MISMATCH", "Entry artifact contains duplicate identifiers.")
    return {entry.entry_id: entry for entry in facts}


def _load_security_facts(context: StageContext) -> dict[str, tuple[EntrySecurityFact, ...]]:
    grouped: dict[str, list[EntrySecurityFact]] = {}
    for row in _strict_records(context, "entries", "entry_security_facts.jsonl"):
        fact = EntrySecurityFact.from_dict(row)
        grouped.setdefault(fact.entry_id, []).append(fact)
    return {entry_id: tuple(sorted(items, key=lambda item: item.fact_id)) for entry_id, items in grouped.items()}


def _load_configuration_facts(context: StageContext) -> tuple[dict[str, object], ...]:
    return tuple(_strict_records(context, "entries", "modeled_configuration.jsonl"))


def _candidate_from_record(record: Mapping[str, object]) -> GrowthCandidate:
    site = cast(Mapping[str, object], record["site"]); resource = cast(Mapping[str, object], record["resource_point"])
    demands = tuple(
        DemandInput(item["name"], item["role"])
        for item in cast(Sequence[Mapping[str, object]], record["demand_inputs"])
    )
    return GrowthCandidate.create(site=SourceLocation(site["file"], site["start_line"]), kind=record["kind"], operation=record["operation"], resource_dimension=resource["dimension"], receiver=resource["receiver"], field_path=resource["field_path"], demand_inputs=demands, escape_scope=record["escape_scope"], evidence_ids=frozenset(record["candidate_evidence"]), coverage_status=record["coverage_status"], coverage_notes=record["coverage_notes"])


def _entry_registration_identity(entry: EntryFact) -> tuple[str, str, str, int, str]:
    return (
        entry.registration.kind,
        entry.registration.callable,
        entry.registration.file,
        entry.registration.start_line,
        entry.registration_pattern_id,
    )


def _entry_registration_site_identity(entry: EntryFact) -> tuple[object, ...]:
    """Bind one installed handler while intentionally excluding route aliases."""
    return (
        entry.framework,
        entry.protocol,
        entry.handler.callable,
        entry.handler.file,
        entry.handler.start_line,
        entry.registration.kind,
        entry.registration.callable,
        entry.registration.file,
        entry.registration.start_line,
        entry.auth_context,
        tuple((item.name, item.type, item.kind) for item in entry.attacker_inputs),
        entry.materialization_phase,
    )


def _association_row_route(row: Mapping[str, object]) -> str | None:
    """Recover only the exact route carried by the modeled Netty switch path."""
    if (
        row.get("phase_sequence")
        != "entry>netty_json_switch>async>service>growth"
        or row.get("coverage_note")
        != "netty_json_switch_async_dispatch_requires_path_coverage"
    ):
        return None
    call_path = row.get("call_path")
    if not isinstance(call_path, str) or len(call_path) > 4096:
        return None
    start = call_path.find("[/")
    end = call_path.find("]", start + 2) if start >= 0 else -1
    if start < 0 or end < 0:
        return None
    route = call_path[start + 1 : end]
    if not route.startswith("/") or any(character.isspace() for character in route):
        return None
    return route


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
        entry.registration_pattern_id,
    )


def _candidate_demand_names(candidate: GrowthCandidate) -> frozenset[str]:
    return frozenset(item.name for item in candidate.demand_inputs)


def _canonical_entry(matches: Sequence[EntryFact], candidate: GrowthCandidate) -> EntryFact:
    demand_names = _candidate_demand_names(candidate)
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
    semantic_keys = {_entry_semantic_key(entry) for entry in narrowed}
    if len(semantic_keys) == 1:
        return min(narrowed, key=lambda entry: (_entry_registration_identity(entry), entry.entry_id))
    registration_keys = {_entry_registration_identity(entry) for entry in narrowed}
    if len(registration_keys) == 1:
        return min(narrowed, key=lambda entry: entry.entry_id)
    raise AnalyzerError(
        "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS",
        "Growth candidate must map to exactly one normalized entry.",
        {"growth_id": candidate.growth_id, "match_count": len(narrowed)},
    )


def _entry_for_candidate(entries: Mapping[str, EntryFact], candidate: GrowthCandidate) -> EntryFact:
    """Legacy helper retained for fixture compatibility; never evidence of a complete link."""
    matches = tuple(entry for entry in entries.values() if entry.handler.file == candidate.site.file and entry.handler.start_line <= candidate.site.start_line)
    if not matches:
        all_entries = tuple(sorted(entries.values(), key=lambda entry: entry.entry_id))
        if all_entries and len({_entry_semantic_key(entry) for entry in all_entries}) == 1:
            return _canonical_entry(all_entries, candidate)
        raise AnalyzerError("ANALYSIS_GROWTH_ENTRY_AMBIGUOUS", "Growth candidate must map to exactly one normalized entry.", {"growth_id": candidate.growth_id, "match_count": 0})
    nearest_line = max(entry.handler.start_line for entry in matches)
    return _canonical_entry(tuple(sorted((entry for entry in matches if entry.handler.start_line == nearest_line), key=lambda entry: entry.entry_id)), candidate)


def _formal_flow_row_matches(
    candidate: GrowthCandidate,
    association: Mapping[str, object],
    flow_rows: Sequence[Mapping[str, object]],
) -> bool:
    demand_names = {
        demand.name
        for demand in candidate.demand_inputs
        if demand.role == association.get("attacker_target")
    }
    if not demand_names or not any(
        expression_binds_demand(name, str(association.get("attacker_sink", "")))
        for name in demand_names
    ):
        return False
    identity_fields = (
        "source_file",
        "source_start_line",
        "sink_file",
        "sink_start_line",
        "attacker_target",
        "attacker_sink",
        "call_path",
        "phase_sequence",
    )
    return any(
        all(row.get(field) == association.get(field) for field in identity_fields)
        and row.get("flow_kind") in {"data_flow", "local_data_flow"}
        for row in flow_rows
    )


def _formal_flow_witness(
    entry: EntryFact,
    candidate: GrowthCandidate,
    association: Mapping[str, object],
    flow_rows: Sequence[Mapping[str, object]],
) -> bool:
    input_names = {item.name for item in entry.attacker_inputs}
    return _formal_flow_row_matches(candidate, association, flow_rows) and any(
        all(
            row.get(field) == association.get(field)
            for field in (
                "source_file",
                "source_start_line",
                "sink_file",
                "sink_start_line",
                "attacker_target",
                "attacker_sink",
                "call_path",
                "phase_sequence",
            )
        )
        and row.get("attacker_source") in input_names
        and row.get("flow_kind") in {"data_flow", "local_data_flow"}
        and row.get("confidence") == "proven"
        and row.get("coverage_status") == "complete"
        for row in flow_rows
    )


def _entry_candidate_has_formal_flow(
    entry: EntryFact,
    candidate: GrowthCandidate,
    flow_rows: Sequence[Mapping[str, object]],
) -> bool:
    input_names = {item.name for item in entry.attacker_inputs}
    return any(
        row.get("source_file") == entry.handler.file
        and row.get("source_start_line") == entry.handler.start_line
        and row.get("sink_file") == candidate.site.file
        and row.get("sink_start_line") == candidate.site.start_line
        and row.get("attacker_source") in input_names
        and _formal_flow_witness(entry, candidate, row, (row,))
        for row in flow_rows
    )


def _association_disposition(
    candidate: GrowthCandidate,
    links: Sequence[object],
    *,
    association_status: str,
    reason_codes: Sequence[str],
) -> CandidateDisposition:
    """Materialize one auditable maturation record for a raw candidate."""
    from dosweb.growth import CandidateEntryLink

    materialized = tuple(links)
    if any(not isinstance(link, CandidateEntryLink) for link in materialized):
        raise AnalyzerError(
            "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
            "Candidate association links are malformed.",
        )
    canonical_entry_id = (
        materialized[0].entry_id if len(materialized) == 1 else ""
    )
    local_growth_status = (
        "complete" if candidate.coverage_status == "complete" else "partial"
    )
    if canonical_entry_id and association_status in {"complete", "partial"}:
        status = (
            "formal_eligible"
            if local_growth_status == "complete" and association_status == "complete"
            else "gap_eligible"
        )
    else:
        status = "inventory_unresolved"
    evidence_ids = tuple(
        sorted(
            set(candidate.evidence_ids)
            | {link.link_id for link in materialized}
            | ({canonical_entry_id} if canonical_entry_id else set())
        )
    )
    return CandidateDisposition.create(
        candidate.growth_id,
        status,
        canonical_entry_id=canonical_entry_id,
        local_growth_status=local_growth_status,
        association_status=association_status,
        link_ids=tuple(link.link_id for link in materialized),
        evidence_ids=evidence_ids,
        negative_proof_ids=(),
        reason_codes=tuple(sorted(set(reason_codes))),
    )


def _candidate_association(
    entries: Mapping[str, EntryFact],
    candidate: GrowthCandidate,
    association_rows: Sequence[Mapping[str, object]] = (),
    flow_rows: Sequence[Mapping[str, object]] = (),
):
    """Return only auditable partial legacy links until the call-graph query lands.

    Same-file/source-order is useful triage evidence, not proof of an E->G association.
    Never select a nearest handler as a complete link.
    """
    from dosweb.growth import CandidateDisposition, CandidateEntryLink
    # Association query evidence is the only source of complete links.  The
    # source-order fallback below is retained solely as explicit partial triage.
    linked: list[CandidateEntryLink] = []
    for row in association_rows:
        if row.get("sink_file") != candidate.site.file or row.get("sink_start_line") != candidate.site.start_line:
            continue
        modeled_route = _association_row_route(row)
        for entry in entries.values():
            if (
                row.get("source_file") == entry.handler.file
                and row.get("source_start_line") == entry.handler.start_line
                and (modeled_route is None or entry.route_or_event == modeled_route)
            ):
                claimed_complete = (
                    row.get("coverage_status") == "complete"
                    and row.get("confidence") == "proven"
                )
                flow_witness = _formal_flow_witness(entry, candidate, row, flow_rows)
                flow_row_matches = _formal_flow_row_matches(candidate, row, flow_rows)
                status = "complete" if claimed_complete and flow_witness else "partial"
                reasons = {str(row.get("coverage_note", "ASSOCIATION_QUERY"))}
                if modeled_route is not None:
                    reasons.add("ASSOCIATION_QUERY_ROUTE_ALIAS_MATCHED")
                if not flow_row_matches:
                    reasons.add("FLOW_CODEQL_ROW_MISSING")
                elif claimed_complete and not flow_witness:
                    reasons.add("FLOW_FORMAL_PROOF_INCOMPLETE")
                linked.append(CandidateEntryLink.create(
                    candidate.growth_id,
                    entry.entry_id,
                    status,
                    (candidate.growth_id, entry.entry_id),
                    tuple(sorted(reasons)),
                ))
    if linked:
        # Recursive call paths can decode to the same semantic association row.
        # Artifact IDs are set-like identities, so collapse exact duplicates
        # before publication without merging distinct evidence/status claims.
        linked = list({link.link_id: link for link in linked}.values())
        # Entry queries may emit route-normalization variants (for example
        # `/path` and `GET /path`) for the exact same handler/registration.
        # They are one semantic entry association, not an ambiguity.
        linked_entries = tuple(entries[link.entry_id] for link in linked)
        netty_base_pattern = registration_coverage_pattern_id(
            "netty", "pipeline_registration", "netty_pipeline_registration"
        )
        base_links = tuple(
            link
            for link in linked
            if entries[link.entry_id].registration_pattern_id == netty_base_pattern
        )
        if (
            len(linked) > 1
            and len(base_links) == 1
            and len({_entry_registration_site_identity(entry) for entry in linked_entries}) == 1
            and len({link.status for link in linked}) == 1
        ):
            base_link = base_links[0]
            canonical_link = CandidateEntryLink.create(
                candidate.growth_id,
                base_link.entry_id,
                base_link.status,
                (candidate.growth_id, base_link.entry_id),
                tuple(
                    sorted(
                        set(base_link.reason_codes)
                        | {"ASSOCIATION_QUERY_HANDLER_BASE_CANONICALIZED"}
                    )
                ),
            )
            return (canonical_link,), _association_disposition(
                candidate,
                (canonical_link,),
                association_status=canonical_link.status,
                reason_codes=tuple(
                    sorted(
                        {"ASSOCIATION_QUERY_EVIDENCE"}
                        | set(canonical_link.reason_codes)
                    )
                ),
            )
        if (
            len(linked) > 1
            and len(
                {
                    _entry_registration_site_identity(entry)
                    for entry in linked_entries
                }
            )
            == 1
            and len({link.status for link in linked}) == 1
        ):
            canonical = _canonical_entry(linked_entries, candidate)
            canonical_status = "complete" if all(link.status == "complete" for link in linked) else "partial"
            canonical_link = CandidateEntryLink.create(
                candidate.growth_id, canonical.entry_id, canonical_status,
                (candidate.growth_id, canonical.entry_id),
                tuple(sorted(
                    {"ASSOCIATION_QUERY_DUPLICATE_REGISTRATION_CANONICALIZED"}
                    | {reason for link in linked for reason in link.reason_codes}
                )),
            )
            return (canonical_link,), _association_disposition(
                candidate,
                (canonical_link,),
                association_status=canonical_status,
                reason_codes=tuple(sorted({"ASSOCIATION_QUERY_EVIDENCE"} | set(canonical_link.reason_codes))),
            )
        if len(linked) > 64:
            return (), _association_disposition(
                candidate,
                (),
                association_status="ambiguous",
                reason_codes=("ASSOCIATION_ENTRY_FANOUT_PARTITION_AMBIGUOUS",),
            )
        association_status = (
            linked[0].status if len(linked) == 1 else "ambiguous"
        )
        return tuple(linked), _association_disposition(
            candidate,
            tuple(linked),
            association_status=association_status,
            reason_codes=tuple(sorted(
                {"ASSOCIATION_QUERY_EVIDENCE"}
                | {reason for link in linked for reason in link.reason_codes}
            )),
        )
    matches = tuple(sorted(
        (entry for entry in entries.values()
         if entry.handler.file == candidate.site.file and entry.handler.start_line <= candidate.site.start_line),
        key=lambda entry: entry.entry_id,
    ))
    if not matches:
        # Growth coverage says nothing about Entry extraction completeness.
        # Without an explicit candidate-scoped Entry coverage proof, absence of
        # a link remains unresolved rather than being mislabeled unreachable.
        return (), _association_disposition(
            candidate,
            (),
            association_status="missing",
            reason_codes=("ASSOCIATION_ENTRY_COVERAGE_UNPROVEN",),
        )
    # Duplicate registrations for one semantic handler are one candidate link.
    if len({_entry_semantic_key(entry) for entry in matches}) == 1:
        matches = (_canonical_entry(matches, candidate),)
    if len(matches) > 1:
        # Partition broad same-file fanout by the closest handler/source
        # anchor before deciding ambiguity.  Registration and route aliases at
        # that anchor are canonicalized; unrelated handlers remain inventory.
        nearest_line = max(entry.handler.start_line for entry in matches)
        nearest = tuple(
            entry for entry in matches if entry.handler.start_line == nearest_line
        )
        try:
            matches = (_canonical_entry(nearest, candidate),)
        except AnalyzerError as exc:
            if exc.code != "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS":
                raise
            return (), _association_disposition(
                candidate,
                (),
                association_status="ambiguous",
                reason_codes=("ASSOCIATION_ENTRY_FANOUT_PARTITION_AMBIGUOUS",),
            )
    missing_flow = any(
        not _entry_candidate_has_formal_flow(entry, candidate, flow_rows)
        for entry in matches
    )
    link_reasons = {"ASSOCIATION_LEGACY_SOURCE_ORDER_PARTIAL"}
    disposition_reasons = {"ASSOCIATION_CALL_GRAPH_UNAVAILABLE"}
    if missing_flow:
        link_reasons.add("FLOW_CODEQL_ROW_MISSING")
        disposition_reasons.add("FLOW_CODEQL_ROW_MISSING")
    links = tuple(
        CandidateEntryLink.create(
            candidate.growth_id,
            entry.entry_id,
            "partial",
            (candidate.growth_id, entry.entry_id),
            tuple(sorted(link_reasons)),
        )
        for entry in matches
    )
    return links, _association_disposition(
        candidate,
        links,
        association_status="partial" if len(links) == 1 else "ambiguous",
        reason_codes=tuple(sorted(disposition_reasons)),
    )


def _slice_for(
    config: AnalyzerConfig,
    entry: EntryFact,
    candidate: GrowthCandidate,
    source_excerpt_fn: Callable[[Path, str | None, str, int], SourceExcerpt] = extract_source_excerpt,
    flow_rows: Sequence[Mapping[str, object]] = (),
    configuration_facts: Sequence[ModeledConfigurationFact] = (),
) -> BoundedSlice:
    checkout = config.llm.source_checkout
    if checkout is None:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "source_checkout is required for Growth classification.")
    dimension_tokens = {
        "bytes": ("max", "limit", "size", "body", "payload", "request", "upload", "buffer"),
        "tasks": ("max", "limit", "capacity", "queue", "quota"),
        "entries": ("max", "limit", "capacity", "quota"),
        "connections": ("max", "limit", "capacity", "timeout"),
        "objects": ("max", "limit", "capacity", "quota"),
    }.get(candidate.resource_dimension, ())
    relevant_configuration = tuple(
        fact
        for fact in configuration_facts
        if fact.status == "known"
        and fact.default_effective
        and any(token in fact.key.lower() for token in dimension_tokens)
    )[:16]
    locations = {
        (candidate.site.file, candidate.site.start_line),
        (entry.handler.file, entry.handler.start_line),
        (entry.registration.file, entry.registration.start_line),
        *((fact.source_file, fact.source_line) for fact in relevant_configuration if fact.source_file and fact.source_line >= 1),
    }
    excerpts_list: list[SourceExcerpt] = []
    for path, line in sorted(locations):
        try:
            excerpts_list.append(source_excerpt_fn(checkout, None, path, line))
        except AnalyzerError as exc:
            if exc.code != "LLM_BOUNDED_SLICE_INVALID":
                raise
            details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            details.update({"candidate_id": candidate.growth_id, "repo_relative_path": path, "candidate_line": line})
            raise AnalyzerError(exc.code, exc.message, details) from exc
    excerpts = tuple(excerpts_list)
    evidence = adapt_growth_static_evidence(
        entry,
        candidate,
        excerpts,
        flow_rows,
        relevant_configuration,
    )
    payload = BoundedSlicePayload(
        entry.entry_id,
        candidate.growth_id,
        excerpts,
        evidence.static_facts,
        evidence.cfg_summary,
        evidence.registration_facts,
        evidence.config_facts,
    )
    return BoundedSlice(stable_identifier("slice", payload.to_dict()), payload)


def _amplification_decision_for_candidate(candidate: object) -> tuple[str, str]:
    """Require the exact CodeQL global-flow loop witness; roles alone never prove A1."""
    kind = getattr(candidate, "kind", "")
    notes = tuple(getattr(candidate, "coverage_notes", ()))
    loop_gap = any(
        note.endswith(":finite_capacity_prevents_amplification")
        or note.endswith(":loop_bound_not_attacker_proven")
        or note.endswith(":loop_multiplicity_unmodeled")
        for note in notes
    )
    if any(
        note.endswith(":attacker_controlled_loop_multiplicity_proven")
        for note in notes
    ) and not loop_gap:
        return "proven", "AMPLIFICATION_CFG_DATAFLOW_LOOP_WITNESS"
    if loop_gap:
        return "unknown", "AMPLIFICATION_LOOP_OR_BATCH_UNMODELED"
    if kind in {"input_materialization", "direct_allocation"} or any(
        note.endswith((":single_submission_no_enclosing_loop", ":single_operation_no_enclosing_loop"))
        for note in notes
    ):
        return "not_applicable", "AMPLIFICATION_DIRECT_DEMAND_ASSERTION"
    return "unknown", "AMPLIFICATION_LOOP_OR_BATCH_UNMODELED"


def _negative_proof_for_relevance(
    candidate: GrowthCandidate, reason_codes: Sequence[str]
) -> CandidateNegativeProof:
    reasons = set(reason_codes)
    mapping = (
        ("RELEVANCE_TEST_OR_BENCHMARK_ONLY", "generated_or_test_only", "NEGATIVE_GENERATED_OR_TEST_ONLY"),
        ("RELEVANCE_SERVER_SIZED_ALLOCATION", "server_controlled_source", "NEGATIVE_SERVER_CONTROLLED_SOURCE"),
        ("RELEVANCE_SERVER_SIDE_MATERIALIZATION", "server_controlled_source", "NEGATIVE_SERVER_CONTROLLED_SOURCE"),
        ("RELEVANCE_FIXED_KEY_RETENTION", "finite_keyspace", "NEGATIVE_FINITE_KEYSPACE"),
        ("RELEVANCE_FINITE_KEYSPACE", "finite_keyspace", "NEGATIVE_FINITE_KEYSPACE"),
        ("RELEVANCE_SYNCHRONOUS_CLEANUP", "guaranteed_synchronous_cleanup", "NEGATIVE_GUARANTEED_SYNCHRONOUS_CLEANUP"),
        ("RELEVANCE_FALSE_ENTRY_GROWTH_FLOW", "false_entry_growth_flow", "NEGATIVE_FALSE_ENTRY_GROWTH_FLOW"),
    )
    for trigger, kind, reason in mapping:
        if trigger in reasons:
            return CandidateNegativeProof.create(
                candidate.growth_id,
                cast(object, kind),
                evidence_ids=tuple(sorted(candidate.evidence_ids)),
                reason_codes=(reason,),
            )
    raise AnalyzerError(
        "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
        "Rejected relevance decision lacks a deterministic negative-proof mapping.",
        {"growth_id": candidate.growth_id},
    )


def _mature_disposition(
    candidate: GrowthCandidate,
    association: CandidateDisposition,
    *,
    status: str,
    relevance_status: str | None = None,
    reason_codes: Sequence[str],
    evidence_ids: Sequence[str] = (),
    negative_proof_ids: Sequence[str] = (),
) -> CandidateDisposition:
    local_growth_status = association.local_growth_status
    if status == "rejected" and negative_proof_ids:
        local_growth_status = "rejected"
    elif status == "gap_eligible" and relevance_status == "dos_relevant_partial":
        local_growth_status = "partial"
    return CandidateDisposition.create(
        candidate.growth_id,
        cast(object, status),
        canonical_entry_id=association.canonical_entry_id,
        local_growth_status=cast(object, local_growth_status),
        association_status=association.association_status,
        link_ids=association.link_ids,
        evidence_ids=tuple(
            sorted(set(association.evidence_ids) | set(evidence_ids) | set(negative_proof_ids))
        ),
        negative_proof_ids=tuple(sorted(set(negative_proof_ids))),
        reason_codes=tuple(sorted(set(association.reason_codes) | set(reason_codes))),
    )


def make_growth_executor(config: AnalyzerConfig, *, database_info_fn: Callable[[], DatabaseInfo], query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]], run_query_fn: Callable[..., QueryResult] | None = None, deepseek_client: object | None = None, deepseek_client_factory: Callable[[object], object] = DeepSeekClient, source_excerpt_fn: Callable[[Path, str, str, int], SourceExcerpt] = extract_source_excerpt) -> Executor:
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        database = database_info_fn()
        with tempfile.TemporaryDirectory(prefix="dosweb-pack-") as temporary:
            pack = _materialize_query_pack(Path(temporary), query_pack_snapshot_fn())
            rows = _run_codeql_family(config, database, "growth", pack, runner)
            association_rows = _run_codeql_family(config, database, "associations", pack, runner)
            preliminary_flow_rows = _run_codeql_family(config, database, "flows", pack, runner)
        entries = _load_entries(context)
        source_growth_rows, source_association_rows = source_backed_same_handler_growth(
            tuple(entries.values()), database.source_root,
        )
        rows.extend(source_growth_rows)
        association_rows.extend(source_association_rows)
        candidate_records = normalize_growth_rows(rows); validate_records("growth_candidates", candidate_records)
        classifier = deepseek_client or deepseek_client_factory(config.llm)
        security_by_entry = _load_security_facts(context)
        configuration_facts = _load_configuration_facts(context)
        configuration_models = tuple(ModeledConfigurationFact.from_dict(item) for item in configuration_facts)
        contracts: list[dict[str, object]] = []; verified: list[dict[str, object]] = []
        links: list[dict[str, object]] = []; dispositions: list[dict[str, object]] = []
        negative_proofs: list[dict[str, object]] = []
        repeatability: list[dict[str, object]] = []; amplification: list[dict[str, object]] = []
        auth_contracts: list[dict[str, object]] = []; reachability: list[dict[str, object]] = []; audits: list[dict[str, object]] = []
        auth_by_entry: dict[str, object] = {}
        for record in candidate_records:
            candidate = _candidate_from_record(record)
            candidate_links, association = _candidate_association(
                entries,
                candidate,
                association_rows,
                preliminary_flow_rows,
            )
            links.extend(link.to_dict() for link in candidate_links)
            relevance_entry = (
                entries[candidate_links[0].entry_id]
                if len(candidate_links) == 1
                else None
            )
            relevance = evaluate_candidate_relevance(
                relevance_entry,
                candidate,
                tuple(candidate_links),
            )
            relevance_reasons = tuple(
                sorted(
                    set(association.reason_codes)
                    | set(relevance.reason_codes)
                    | {
                        "RELEVANCE_AMPLIFICATION_"
                        + relevance.amplification_class.upper()
                    }
                )
            )
            if relevance.status == "rejected":
                proof = _negative_proof_for_relevance(candidate, relevance.reason_codes)
                negative_proofs.append(proof.to_dict())
                disposition = _mature_disposition(
                    candidate,
                    association,
                    status="rejected",
                    reason_codes=(*relevance_reasons, "MATURATION_SOURCE_PROVEN_NEGATIVE"),
                    negative_proof_ids=(proof.negative_proof_id,),
                )
                dispositions.append(disposition.to_dict())
                continue
            if (
                relevance.status == "unresolved"
                or association.status == "inventory_unresolved"
                or len(candidate_links) != 1
            ):
                disposition = _mature_disposition(
                    candidate,
                    association,
                    status="inventory_unresolved",
                    reason_codes=(*relevance_reasons, "MATURATION_INVENTORY_UNRESOLVED"),
                )
                dispositions.append(disposition.to_dict())
                continue
            entry = entries[candidate_links[0].entry_id]
            maturation_status = (
                "formal_eligible"
                if relevance.status == "contract_eligible"
                and association.status == "formal_eligible"
                else "gap_eligible"
            )
            maturation_reason = (
                "MATURATION_FORMAL_ELIGIBLE"
                if maturation_status == "formal_eligible"
                else "MATURATION_GAP_ELIGIBLE"
            )
            from dosweb.growth import RepeatabilityDecision, AmplificationDecision
            repeatable_registrations = {
                "annotation_mapping", "static_registration", "pipeline_registration",
                "subscription_registration", "broker_registration",
            }
            repeatability_status = (
                "proven"
                if candidate_links[0].status == "complete"
                and entry.protocol in {"http", "tcp", "mqtt"}
                and entry.registration.kind in repeatable_registrations
                else "unknown"
            )
            repeatability_reason = (
                "REPEATABILITY_REGISTERED_PROTOCOL_TRIGGER"
                if repeatability_status == "proven"
                else "REPEATABILITY_TRIGGER_SEMANTICS_UNMODELED"
            )
            repeatability.append(RepeatabilityDecision.create(
                "repeatability", entry.entry_id, candidate.growth_id, repeatability_status,
                (entry.entry_id, candidate.growth_id, candidate_links[0].link_id),
                (repeatability_reason,),
            ).to_dict())
            amplification_status, amplification_reason = _amplification_decision_for_candidate(candidate)
            amplification.append(AmplificationDecision.create(
                "amplification", entry.entry_id, candidate.growth_id, amplification_status,
                (candidate.growth_id, candidate_links[0].link_id), (amplification_reason,),
            ).to_dict())
            # Auth is constrained to the Entry's pre-extracted security/configuration facts.
            # Test-only classifiers without this optional transport remain conservatively unknown.
            cached_auth = auth_by_entry.get(entry.entry_id)
            if cached_auth is None:
                security_facts = security_by_entry.get(entry.entry_id, ())
                from dosweb.reachability.verify import derive_auth_contract_from_facts, verify_auth_contract
                auth = derive_auth_contract_from_facts(entry.entry_id, security_facts)
                auth_used_provider = False
                classify_auth = getattr(classifier, "classify_auth", None)
                if auth is None and callable(classify_auth):
                    auth = classify_auth(entry.entry_id, security_facts, configuration_facts)
                    auth_used_provider = True
                if auth is None:
                    from dosweb.reachability.models import AuthContract, ReachabilityDecision
                    auth = AuthContract("unknown", (), ("auth_transport_unavailable",), "low")
                    contract_id = "auth_contract:" + hashlib.sha256((entry.entry_id + repr(auth.to_dict())).encode()).hexdigest()
                    decision = ReachabilityDecision(entry.entry_id, contract_id, "unknown", "unknown", "unknown", (), ("REACH_AUTH_TRANSPORT_UNAVAILABLE", "REACH_DEPLOYMENT_UNKNOWN"))
                else:
                    decision = verify_auth_contract(entry.entry_id, auth, security_facts, slice_fact_ids=frozenset(item.fact_id for item in security_facts), configuration_facts=configuration_models)
                auth_by_entry[entry.entry_id] = (auth, decision)
                auth_contracts.append({"auth_contract_id": decision.auth_contract_id, "entry_id": entry.entry_id, **auth.to_dict()})
                reachability.append(decision.to_dict())
                last_audit = getattr(classifier, "last_audit", None)
                if auth_used_provider and callable(last_audit):
                    audit = last_audit()
                    if audit is not None:
                        audits.append(audit.to_dict())
            else:
                auth, decision = cached_auth
            if decision.status == "not_entry_reachable":
                proof = CandidateNegativeProof.create(
                    candidate.growth_id,
                    "not_entry_reachable",
                    evidence_ids=tuple(sorted(candidate.evidence_ids)),
                    reason_codes=("NEGATIVE_NOT_ENTRY_REACHABLE",),
                )
                negative_proofs.append(proof.to_dict())
                disposition = _mature_disposition(
                    candidate,
                    association,
                    status="rejected",
                    reason_codes=(*relevance_reasons, *decision.reason_codes, "MATURATION_NOT_ENTRY_REACHABLE"),
                    negative_proof_ids=(proof.negative_proof_id,),
                )
                dispositions.append(disposition.to_dict())
                continue
            bounded = _slice_for(
                config,
                entry,
                candidate,
                source_excerpt_fn,
                preliminary_flow_rows,
                configuration_models,
            )
            classify = getattr(classifier, "classify_growth", None)
            if not callable(classify):
                raise AnalyzerError("INTERNAL_STAGE_EXECUTORS_UNAVAILABLE", "Growth classifier is unavailable.")
            contract = classify(bounded)
            if not isinstance(contract, GrowthContract):
                raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Growth classifier returned an invalid contract.")
            contract = validate_contract_static_evidence(contract, frozenset(fact.fact_id for fact in bounded.payload.static_facts))
            contract_record = {"growth_contract_id": stable_identifier("contract", {"growth_id": candidate.growth_id, **contract.to_dict()}), "growth_id": candidate.growth_id, **contract.to_dict()}
            contracts.append(contract_record)
            last_audit = getattr(classifier, "last_audit", None)
            if callable(last_audit):
                audit = last_audit()
                if audit is not None:
                    audits.append(audit.to_dict())
            result = verify_growth_contract(candidate, bounded, contract, {fact.fact_id: fact for fact in bounded.payload.static_facts})
            verified.append(result.to_dict())
            disposition = _mature_disposition(
                candidate,
                association,
                status=maturation_status,
                relevance_status=relevance.status,
                reason_codes=(*relevance_reasons, maturation_reason),
                evidence_ids=(result.verified_growth_id,),
            )
            dispositions.append(disposition.to_dict())
        validate_records("growth_contracts", contracts); validate_records("verified_growth", verified)
        validate_records("candidate_entry_links", links)
        growth_ids = {str(record["growth_id"]) for record in candidate_records}
        growth_fact_ids = {
            str(record["growth_id"]): {
                str(value) for value in record["candidate_evidence"]
            }
            for record in candidate_records
        }
        negative_proof_growth_ids = {
            str(record["negative_proof_id"]): str(record["growth_id"])
            for record in negative_proofs
        }
        validate_references(
            "candidate_negative_proofs",
            negative_proofs,
            {
                "growth_id": growth_ids,
                "fact_id": {
                    fact_id
                    for fact_ids in growth_fact_ids.values()
                    for fact_id in fact_ids
                },
                "growth_fact_ids": growth_fact_ids,
            },
        )
        validate_references(
            "candidate_dispositions",
            dispositions,
            {
                "growth_id": growth_ids,
                "entry_id": set(entries),
                "link_id": {str(record["link_id"]) for record in links},
                "link_ownership": {
                    str(record["link_id"]): (
                        str(record["growth_id"]),
                        str(record["entry_id"]),
                        str(record["status"]),
                    )
                    for record in links
                },
                "negative_proof_id": set(negative_proof_growth_ids),
                "negative_proof_growth_ids": negative_proof_growth_ids,
            },
        )
        validate_records("repeatability_decisions", repeatability); validate_records("amplification_decisions", amplification)
        validate_records("auth_contracts", auth_contracts); validate_records("reachability_decisions", reachability); validate_records("llm_audit", audits)
        return StageOutput({"growth_candidates.jsonl": candidate_records, "candidate_entry_links.jsonl": links, "candidate_negative_proofs.jsonl": negative_proofs, "candidate_dispositions.jsonl": dispositions, "repeatability_decisions.jsonl": repeatability, "amplification_decisions.jsonl": amplification, "growth_contracts.jsonl": contracts, "verified_growth.jsonl": verified, "auth_contracts.jsonl": auth_contracts, "reachability_decisions.jsonl": reachability, "llm_audit.private.jsonl": audits}, {"candidate_count": len(candidate_records), "candidate_disposition_count": len(dispositions), "formal_eligible_candidate_count": sum(item["status"] == "formal_eligible" for item in dispositions), "gap_eligible_candidate_count": sum(item["status"] == "gap_eligible" for item in dispositions), "negative_proof_count": len(negative_proofs), "mapped_candidate_count": len(verified), "inventory_unresolved_candidate_count": sum(item["status"] == "inventory_unresolved" for item in dispositions), "auth_contract_count": len(auth_contracts), "llm_audit_count": len(audits)})
    return execute


def _reconcile_flow_rows(
    rows: Sequence[Mapping[str, object]],
    entries: Mapping[str, EntryFact],
    candidates: Mapping[str, VerifiedGrowthResult],
) -> list[Mapping[str, object]]:
    """Keep raw screening rows anchored to one extracted E and retained G domain.

    Source-backed fallbacks deliberately screen broader method shapes than the
    authoritative Entry extractor can register.  Exact file/line
    reconciliation therefore happens here, before strict flow normalization;
    a decoded row from an unregistered source method is screening noise, not a
    malformed formal artifact.
    """
    entry_sites = {
        (entry.handler.file, entry.handler.start_line)
        for entry in entries.values()
        if isinstance(entry, EntryFact)
    }
    candidate_sites = {
        (result.candidate.site.file, result.candidate.site.start_line)
        for result in candidates.values()
        if isinstance(result, VerifiedGrowthResult) and result.candidate is not None
    }
    return [
        row
        for row in rows
        if (row.get("source_file"), row.get("source_start_line")) in entry_sites
        and (row.get("sink_file"), row.get("sink_start_line")) in candidate_sites
    ]


def _canonical_flow_entry_ids(
    entries: Mapping[str, EntryFact],
    candidates: Mapping[str, VerifiedGrowthResult],
    link_records: Sequence[Mapping[str, object]],
    disposition_records: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    """Reconcile retained Growth results to authenticated canonical Entry links.

    The Growth stage owns route-alias canonicalization. Flow normalization must
    consume that exact decision rather than expanding a shared handler source
    location back into every route alias. All link/disposition records are
    checked before selecting retained candidates so non-eligible evidence
    cannot be silently filtered to conceal a corrupted upstream artifact.
    """

    try:
        links = tuple(
            CandidateEntryLink(
                cast(str, record["link_id"]),
                cast(str, record["growth_id"]),
                cast(str, record["entry_id"]),
                cast(object, record["status"]),
                tuple(cast(Sequence[str], record["evidence_ids"])),
                tuple(cast(Sequence[str], record["reason_codes"])),
            )
            for record in link_records
        )
        dispositions = tuple(
            CandidateDisposition(
                cast(str, record["disposition_id"]),
                cast(str, record["growth_id"]),
                cast(object, record["status"]),
                cast(str, record["canonical_entry_id"]),
                cast(object, record["local_growth_status"]),
                cast(object, record["association_status"]),
                tuple(cast(Sequence[str], record["link_ids"])),
                tuple(cast(Sequence[str], record["evidence_ids"])),
                tuple(cast(Sequence[str], record["negative_proof_ids"])),
                tuple(cast(Sequence[str], record["reason_codes"])),
            )
            for record in disposition_records
        )
    except (KeyError, TypeError) as exc:
        raise AnalyzerError(
            "ARTIFACT_UPSTREAM_INVALID",
            "Candidate link reconciliation records are malformed.",
        ) from exc

    candidate_growth_ids = frozenset(
        cast(
            object,
            getattr(candidates, "candidate_growth_ids", frozenset(candidates)),
        )
    )
    if not all(isinstance(growth_id, str) for growth_id in candidate_growth_ids):
        raise AnalyzerError(
            "ARTIFACT_UPSTREAM_INVALID",
            "Growth candidate domain is malformed.",
        )
    links_by_id = {link.link_id: link for link in links}
    dispositions_by_growth = {
        disposition.growth_id: disposition for disposition in dispositions
    }
    if len(links_by_id) != len(links) or len(dispositions_by_growth) != len(dispositions):
        raise AnalyzerError(
            "ARTIFACT_UPSTREAM_INVALID",
            "Candidate link reconciliation records are duplicated.",
        )
    disposition_growth_ids = set(dispositions_by_growth)
    if disposition_growth_ids - candidate_growth_ids:
        raise AnalyzerError(
            "ANALYSIS_DANGLING_FACT_REFERENCE",
            "Candidate disposition references a missing Growth candidate.",
        )
    if disposition_growth_ids != candidate_growth_ids:
        raise AnalyzerError(
            "ARTIFACT_UPSTREAM_INVALID",
            "Growth candidate domain is missing a candidate disposition.",
        )

    cited_link_ids: set[str] = set()
    retained_growth_ids = set(candidates)
    for link in links:
        if link.growth_id not in candidate_growth_ids:
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "Candidate Entry link references a missing Growth candidate.",
            )
    for disposition in dispositions:
        if disposition.growth_id not in candidate_growth_ids:
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "Candidate disposition references a missing Growth candidate.",
            )
        disposition_links: list[CandidateEntryLink] = []
        for link_id in disposition.link_ids:
            link = links_by_id.get(link_id)
            if link is None or link.growth_id != disposition.growth_id:
                raise AnalyzerError(
                    "ANALYSIS_DANGLING_FACT_REFERENCE",
                    "Candidate disposition references an incompatible Entry link.",
                )
            if link.entry_id not in entries:
                raise AnalyzerError(
                    "ANALYSIS_DANGLING_FACT_REFERENCE",
                    "Candidate Entry link references a missing Entry fact.",
                )
            disposition_links.append(link)
            cited_link_ids.add(link_id)
        if disposition.association_status in {"complete", "partial"}:
            if (
                len(disposition_links) != 1
                or not disposition.canonical_entry_id
                or disposition.canonical_entry_id not in entries
                or disposition_links[0].entry_id
                != disposition.canonical_entry_id
                or disposition_links[0].status
                != disposition.association_status
            ):
                raise AnalyzerError(
                    "ANALYSIS_DANGLING_FACT_REFERENCE",
                    "Candidate disposition association disagrees with its canonical link.",
                )
        elif disposition.association_status == "missing":
            if disposition_links or disposition.canonical_entry_id:
                raise AnalyzerError(
                    "ANALYSIS_DANGLING_FACT_REFERENCE",
                    "Missing candidate association cannot own Entry links.",
                )
        elif disposition.association_status == "ambiguous":
            if disposition.canonical_entry_id or len(disposition_links) == 1:
                raise AnalyzerError(
                    "ANALYSIS_DANGLING_FACT_REFERENCE",
                    "Ambiguous candidate association has a canonical Entry shape.",
                )
        if (
            disposition.status in {"formal_eligible", "gap_eligible"}
            and disposition.growth_id not in retained_growth_ids
        ):
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "Eligible candidate disposition references an unretained Growth result.",
            )
    if cited_link_ids != set(links_by_id):
        raise AnalyzerError(
            "ANALYSIS_DANGLING_FACT_REFERENCE",
            "Candidate Entry link is not owned by its Growth disposition.",
        )

    canonical: dict[str, str] = {}
    for growth_id, result in candidates.items():
        if (
            not isinstance(result, VerifiedGrowthResult)
            or result.candidate is None
            or result.growth_id != growth_id
        ):
            raise AnalyzerError(
                "ARTIFACT_UPSTREAM_INVALID",
                "Retained Growth result identity is malformed.",
            )
        disposition = dispositions_by_growth.get(growth_id)
        if (
            disposition is None
            or disposition.status not in {"formal_eligible", "gap_eligible"}
            or len(disposition.link_ids) != 1
        ):
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "Retained Growth result has no eligible canonical Entry disposition.",
            )
        link = links_by_id[disposition.link_ids[0]]
        if (
            link.growth_id != growth_id
            or link.entry_id != disposition.canonical_entry_id
            or link.status != disposition.association_status
        ):
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "Retained Growth canonical Entry link identity is inconsistent.",
            )
        canonical[growth_id] = link.entry_id
    return canonical


def _candidate_relevant_partial_flow_rows(
    entries: Mapping[str, EntryFact],
    candidates: Mapping[str, VerifiedGrowthResult],
    link_records: Sequence[Mapping[str, object]],
    disposition_records: Sequence[Mapping[str, object]],
    existing_pairs: set[tuple[str, str]],
) -> list[dict[str, object]]:
    """Carry one DoS-relevant partial E/G association as an explicit gap path.

    This is deliberately not a data-flow proof.  It publishes one deterministic
    ``unmodeled``/``partial`` path only after candidate relevance has reached
    ``gap_eligible`` and only when its single canonical association is
    itself partial.  Generic unresolved candidates and missing complete flows
    are never supplemented, so this cannot recover a vulnerable premise or
    hide a corrupted formal flow artifact.
    """

    links_by_id = {
        record.get("link_id"): record
        for record in link_records
        if isinstance(record.get("link_id"), str)
    }
    if len(links_by_id) != len(link_records):
        raise AnalyzerError(
            "ARTIFACT_UPSTREAM_INVALID",
            "Candidate Entry links are duplicated or malformed.",
        )
    allowed_targets = {"size", "key", "value", "iteration_count", "submission_count"}
    rows: list[dict[str, object]] = []
    emitted_pairs: set[tuple[str, str]] = set()
    for disposition in disposition_records:
        if disposition.get("status") != "gap_eligible":
            continue
        growth_id = disposition.get("growth_id")
        link_ids = disposition.get("link_ids")
        if (
            not isinstance(growth_id, str)
            or not isinstance(link_ids, list)
            or len(link_ids) != 1
            or not isinstance(link_ids[0], str)
            or link_ids[0] not in links_by_id
        ):
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "DoS-relevant partial disposition has no canonical Entry link.",
            )
        link = links_by_id[link_ids[0]]
        entry_id = link.get("entry_id")
        if link.get("growth_id") != growth_id or not isinstance(entry_id, str):
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "DoS-relevant partial disposition references an incompatible Entry link.",
            )
        pair = (entry_id, growth_id)
        if pair in existing_pairs or pair in emitted_pairs:
            continue
        # A complete link was admitted only with a formal preliminary flow
        # witness.  Its later absence is corruption/nondeterminism, not a gap
        # that this conservative supplement may conceal.
        if link.get("status") != "partial":
            continue
        entry = entries.get(entry_id)
        result = candidates.get(growth_id)
        candidate = result.candidate if isinstance(result, VerifiedGrowthResult) else None
        if not isinstance(entry, EntryFact) or candidate is None:
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "DoS-relevant partial flow references missing Entry or Growth evidence.",
            )
        demands = tuple(
            demand for demand in candidate.demand_inputs if demand.role in allowed_targets
        )
        if not demands or not entry.attacker_inputs:
            raise AnalyzerError(
                "ARTIFACT_UPSTREAM_INVALID",
                "DoS-relevant partial flow lacks a representable attacker-demand hypothesis.",
            )
        demand = min(demands)
        attacker_input = min(entry.attacker_inputs)
        rows.append(
            {
                "source_file": entry.handler.file,
                "source_start_line": entry.handler.start_line,
                "sink_file": candidate.site.file,
                "sink_start_line": candidate.site.start_line,
                "attacker_target": demand.role,
                "attacker_source": attacker_input.name,
                "attacker_sink": demand.name,
                "call_path": entry.handler.callable,
                "phase_sequence": "entry>candidate_relevant_partial>growth",
                "flow_kind": "unmodeled",
                "confidence": "partial",
                "coverage_status": "partial",
                "coverage_note": "candidate_relevant_partial_flow_gap",
            }
        )
        emitted_pairs.add(pair)
    return sorted(rows, key=canonical_json)


def make_flows_executor(config: AnalyzerConfig, *, database_info_fn: Callable[[], DatabaseInfo], query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]], run_query_fn: Callable[..., QueryResult] | None = None) -> Executor:
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        entries = _load_entries(context)
        candidates = _load_verified_growth(context)
        with tempfile.TemporaryDirectory(prefix="dosweb-pack-") as temporary:
            pack = _materialize_query_pack(Path(temporary), query_pack_snapshot_fn())
            rows = _run_codeql_family(config, database_info_fn(), "flows", pack, runner)
        # Raw screening may include a broad source-backed method shape or a
        # candidate the Growth stage did not retain.  Formal E/G artifacts are
        # authoritative at this boundary; strict normalization still applies
        # to every reconciled row.
        rows = _reconcile_flow_rows(rows, entries, candidates)
        link_records = _strict_records(
            context, "growth", "candidate_entry_links.jsonl"
        )
        disposition_records = _strict_records(
            context, "growth", "candidate_dispositions.jsonl"
        )
        canonical_entry_ids = _canonical_flow_entry_ids(
            entries,
            candidates,
            link_records,
            disposition_records,
        )
        proofs = normalize_flow_rows(
            rows,
            entries,
            candidates,
            canonical_entry_ids=canonical_entry_ids,
        )
        existing_pairs = {
            (record["entry_id"], record["growth_id"])
            for record in proofs
        }
        gap_rows = _candidate_relevant_partial_flow_rows(
            entries,
            candidates,
            link_records,
            disposition_records,
            existing_pairs,
        )
        gap_proofs = normalize_flow_rows(
            gap_rows,
            entries,
            candidates,
            canonical_entry_ids=canonical_entry_ids,
        )
        proofs_by_id = {record["path_id"]: record for record in proofs}
        for record in gap_proofs:
            previous = proofs_by_id.setdefault(record["path_id"], record)
            if previous != record:
                raise AnalyzerError(
                    "ARTIFACT_UPSTREAM_INVALID",
                    "Partial gap flow collides with a distinct formal flow path.",
                )
        proofs = sorted(proofs_by_id.values(), key=canonical_json)
        validate_records("flow_proofs", proofs)
        return StageOutput({"flow_proofs.jsonl": proofs}, {"flow_count": len(proofs), "partial_flow_count": sum(item["confidence"] == "partial" for item in proofs), "partial_gap_flow_count": len(gap_proofs)})
    return execute


class _VerifiedGrowthDomain(dict[str, VerifiedGrowthResult]):
    def __init__(
        self,
        values: Mapping[str, VerifiedGrowthResult],
        candidate_growth_ids: frozenset[str],
    ) -> None:
        super().__init__(values)
        self.candidate_growth_ids = candidate_growth_ids


def _load_verified_growth(context: StageContext) -> dict[str, VerifiedGrowthResult]:
    candidate_records = _records(
        context,
        "growth",
        "growth_candidates.jsonl",
        "growth_candidates",
    )
    candidate_growth_ids = tuple(record["growth_id"] for record in candidate_records)
    if (
        not all(isinstance(growth_id, str) for growth_id in candidate_growth_ids)
        or len(set(candidate_growth_ids)) != len(candidate_growth_ids)
    ):
        raise AnalyzerError(
            "ARTIFACT_UPSTREAM_INVALID",
            "Growth candidate records contain duplicate or malformed ownership.",
        )
    candidates = {
        cast(str, record["growth_id"]): _candidate_from_record(record)
        for record in candidate_records
    }
    verified_records = _records(
        context,
        "growth",
        "verified_growth.jsonl",
        "verified_growth",
    )
    if any(record["growth_id"] not in candidates for record in verified_records):
        raise AnalyzerError(
            "ANALYSIS_DANGLING_FACT_REFERENCE",
            "Verified Growth references a missing Growth candidate.",
        )
    materialized = tuple(
        VerifiedGrowthResult.from_dict(record, candidates.get(record["growth_id"]))
        for record in verified_records
    )
    if len({result.growth_id for result in materialized}) != len(materialized):
        raise AnalyzerError(
            "ARTIFACT_UPSTREAM_INVALID",
            "Verified Growth records contain duplicate Growth ownership.",
        )
    return _VerifiedGrowthDomain(
        {result.growth_id: result for result in materialized},
        frozenset(cast(str, growth_id) for growth_id in candidate_growth_ids),
    )


def _decision_record(decision: object) -> dict[str, object]:
    """Serialize a lifecycle decision without changing any proven field."""
    checks = sorted(
        decision.checks,
        key=lambda check: (
            check.name,
            not check.passed,
            check.reason_code or "",
            tuple(check.evidence_ids),
        ),
    )[:64]
    return {
        "status": decision.status,
        "reason_codes": list(decision.reason_codes),
        "checks": [
            {"name": check.name, "passed": check.passed, "reason_code": check.reason_code, "evidence_ids": list(check.evidence_ids)}
            for check in checks
        ],
        "evidence_ids": list(decision.evidence_ids),
        "unresolved_facts": list(decision.unresolved_facts),
        "candidate_ids": list(decision.candidate_ids),
        **({"classification": decision.classification} if hasattr(decision, "classification") else {}),
    }


def _decision_checks(record: Mapping[str, object]) -> tuple[DecisionCheck, ...]:
    checks = record.get("checks")
    if not isinstance(checks, list):
        raise AnalyzerError("ARTIFACT_UPSTREAM_INVALID", "Lifecycle decision checks are malformed.")
    parsed: list[DecisionCheck] = []
    for check in checks:
        if not isinstance(check, Mapping) or set(check) != {
            "name", "passed", "reason_code", "evidence_ids"
        }:
            raise AnalyzerError("ARTIFACT_UPSTREAM_INVALID", "Lifecycle decision checks are malformed.")
        evidence = check["evidence_ids"]
        if not isinstance(evidence, list):
            raise AnalyzerError("ARTIFACT_UPSTREAM_INVALID", "Lifecycle decision evidence is malformed.")
        parsed.append(
            DecisionCheck(
                check["name"], check["passed"], check["reason_code"], tuple(evidence)
            )
        )
    return tuple(parsed)


def _decision_values(record: Mapping[str, object]) -> tuple[tuple[str, ...], tuple[DecisionCheck, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    fields = ("reason_codes", "evidence_ids", "unresolved_facts", "candidate_ids")
    if any(not isinstance(record.get(field), list) for field in fields):
        raise AnalyzerError("ARTIFACT_UPSTREAM_INVALID", "Lifecycle decision is malformed.")
    return (
        tuple(record["reason_codes"]),
        _decision_checks(record),
        tuple(record["evidence_ids"]),
        tuple(record["unresolved_facts"]),
        tuple(record["candidate_ids"]),
    )


def _guard_decision(record: Mapping[str, object]) -> GuardDecision:
    reasons, checks, evidence, unresolved, candidates = _decision_values(record)
    return GuardDecision(record["status"], reasons, checks, evidence, unresolved, candidates)


def _bound_decision(record: Mapping[str, object]) -> BoundDecision:
    reasons, checks, evidence, unresolved, candidates = _decision_values(record)
    return BoundDecision(record["status"], reasons, checks, evidence, unresolved, candidates)


def _release_decision(record: Mapping[str, object]) -> ReleaseDecision:
    reasons, checks, evidence, unresolved, candidates = _decision_values(record)
    return ReleaseDecision(
        record["status"], record["classification"], reasons, checks,
        evidence, unresolved, candidates,
    )


def _modeled_configuration(context: StageContext) -> ModeledConfiguration:
    """Use only known, default-effective facts; ambiguous defaults stay unknown."""
    values: dict[str, str | int | bool] = {}
    for raw in _strict_records(context, "entries", "modeled_configuration.jsonl"):
        fact = ModeledConfigurationFact.from_dict(raw)
        if fact.status == "known" and fact.default_effective and fact.value is not None:
            # Extractor already applies CLI > config > source precedence. A duplicate
            # here means an ambiguous artifact and must not be silently selected.
            if fact.key in values and values[fact.key] != fact.value:
                raise AnalyzerError("ARTIFACT_SCHEMA_MISMATCH", "Modeled configuration has conflicting effective defaults.")
            values[fact.key] = fact.value
    return ModeledConfiguration(tuple(values.items()))


def _evaluate_path_bounds(
    entry: EntryFact,
    growth: VerifiedGrowthResult,
    flow: VerifiedFlow,
    candidates: Sequence[BoundCandidate],
    configuration: ModeledConfiguration,
    *,
    coverage_status: str,
) -> BoundDecision:
    """Evaluate exact framework limits through their path/domain normalizer."""
    ordered = tuple(sorted(candidates, key=lambda item: item.bound_id))
    if not ordered:
        return evaluate_bound(
            entry, growth, flow, (), configuration, coverage_status=coverage_status
        )

    individual: list[BoundDecision] = []
    for candidate in ordered:
        if is_framework_limit_candidate(candidate):
            individual.append(
                normalize_framework_limit(
                    entry=entry,
                    growth=growth,
                    flow=flow,
                    candidate=candidate,
                    configuration=configuration,
                )
            )
        else:
            individual.append(
                evaluate_bound(
                    entry,
                    growth,
                    flow,
                    (candidate,),
                    configuration,
                    coverage_status="complete",
                )
            )

    if any(decision.status == "effective" for decision in individual):
        return BoundDecision(
            "effective",
            (),
            tuple(check for decision in individual for check in decision.checks),
            tuple(sorted({item for decision in individual for item in decision.evidence_ids})),
            tuple(sorted({item for decision in individual for item in decision.unresolved_facts})),
            tuple(candidate.bound_id for candidate in ordered),
        )
    return evaluate_bound(
        entry,
        growth,
        flow,
        ordered,
        configuration,
        coverage_status=coverage_status,
    )


def make_lifecycle_executor(
    config: AnalyzerConfig,
    *,
    database_info_fn: Callable[[], DatabaseInfo],
    query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]],
    run_query_fn: Callable[..., QueryResult] | None = None,
    resource_lifecycle_provider: Callable[
        [DatabaseInfo, Path], ResourceLifecycleBackendRun
    ]
    | None = None,
    resource_lifecycle_propagation_enabled: bool = True,
) -> Executor:
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        database = database_info_fn()
        analysis_root = config.llm.analysis_source_root or database.source_root
        with tempfile.TemporaryDirectory(prefix="dosweb-pack-") as temporary:
            pack = _materialize_query_pack(Path(temporary), query_pack_snapshot_fn())
            rows = _run_codeql_family(config, database, "lifecycle", pack, runner)
        resource_run: ResourceLifecycleBackendRun | None = None
        resource_coverage_gap: ResourceLifecycleCoverageGap | None = None
        if resource_lifecycle_provider is not None:
            with tempfile.TemporaryDirectory(
                prefix="dosweb-resource-lifecycle-"
            ) as temporary:
                try:
                    resource_run = resource_lifecycle_provider(
                        database, Path(temporary) / "analysis"
                    )
                except ResourceLifecycleCoverageGap as exc:
                    resource_coverage_gap = exc
            if (
                resource_coverage_gap is not None
                and resource_coverage_gap.database_fingerprint
                != database.fingerprint
            ):
                raise AnalyzerError(
                    "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                    "Resource lifecycle coverage gap belongs to a different CodeQL database.",
                )
            if (
                resource_run is not None
                and
                resource_run.extracted.coverage.get("database_fingerprint")
                != database.fingerprint
            ):
                raise AnalyzerError(
                    "ANALYSIS_RESOURCE_LIFECYCLE_INVALID",
                    "Resource lifecycle evidence belongs to a different CodeQL database.",
                )
        # Re-query family rows by decoder provenance, retaining strict normalization.
        guards_raw, bounds_raw, releases_raw, coverage_raw, summaries_raw = [], [], [], [], []
        for row in rows:
            query = row.get("query_name", "")
            if query == "guard": guards_raw.append(row)
            elif query == "bound": bounds_raw.append(row)
            elif query == "release": releases_raw.append(row)
            elif query == "lifecycle_coverage": coverage_raw.append(row)
            elif query == "lifecycle_summary": summaries_raw.append(row)
            else: raise AnalyzerError("CODEQL_RESULT_INVALID", "Lifecycle query family is unknown.")
        # Candidate rows carry the exact CodeQL Growth anchor.  Do not recover
        # callable/CFG membership from source ordering or expression strings.
        candidate_anchors: dict[str, dict[str, set[tuple[str, int]]]] = {"guard": {}, "bound": {}, "release": {}}
        def normalized(raw: list[Mapping[str, object]], kind: str) -> list[dict[str, object]]:
            output: dict[str, dict[str, object]] = {}
            for r in raw:
                if kind == "guard":
                    candidate = GuardCandidate.create(site_file=r["site_file"], site_start_line=r["site_start_line"], kind=r["guard_kind"], resource_dimension=r["resource_dimension"], scope=r["scope"], behavior=r["behavior"], dominates_growth=r["dominates_growth"], reject_path_reaches_growth=r["reject_path_reaches_growth"], configuration_key=r["configuration_key"], configuration_value=r["configuration_value"], representation=r["representation"], phase=r["phase"], covers_materialization=r["covers_materialization"], authorization_only=r["authorization_only"], evidence=[r["evidence"]], coverage_status=r["coverage_status"])
                    candidate_id = candidate.guard_id
                elif kind == "bound":
                    candidate = BoundCandidate.create(site_file=r["site_file"], site_start_line=r["site_start_line"], kind=r["bound_kind"], resource_dimension=r["resource_dimension"], scope=r["scope"], behavior=r["behavior"], receiver=r["receiver"], field_path=r["field_path"], result_checked=r["result_checked"], configuration_key=r["configuration_key"], configuration_value=r["configuration_value"], phase=r["phase"], covers_flow=r["covers_flow"], request_encoding=r["request_encoding"], queue_resource=r["queue_resource"], product_bound=r["product_bound"], evidence=[r["evidence"]], coverage_status=r["coverage_status"])
                    candidate_id = candidate.bound_id
                else:
                    candidate = ReleaseCandidate.create(site_file=r["site_file"], site_start_line=r["site_start_line"], kind=r["release_kind"], resource_dimension=r["resource_dimension"], scope=r["scope"], receiver=r["receiver"], key_identity=r["key_identity"], synchronous=r["synchronous"], normal_path=r["normal_path"], exceptional_path=r["exceptional_path"], actual_reduction=r["actual_reduction"], after_growth=r["after_growth"], transfer_only=r["transfer_only"], async_kind=r["async_kind"], evidence=[r["evidence"]], coverage_status=r["coverage_status"])
                    candidate_id = candidate.release_id
                output[candidate_id] = candidate.to_dict()
                candidate_anchors[kind].setdefault(candidate_id, set()).add((r["anchor_file"], r["anchor_start_line"]))
            return [output[key] for key in sorted(output)]
        guard_records, bound_records, release_records = normalized(guards_raw, "guard"), normalized(bounds_raw, "bound"), normalized(releases_raw, "release")
        tuple(GuardCandidate.from_dict(record) for record in guard_records); tuple(BoundCandidate.from_dict(record) for record in bound_records); tuple(ReleaseCandidate.from_dict(record) for record in release_records)
        guards = [GuardCandidate.from_dict(record) for record in guard_records]
        bounds = [BoundCandidate.from_dict(record) for record in bound_records]
        releases = [ReleaseCandidate.from_dict(record) for record in release_records]
        entries = _load_entries(context)
        growth = _load_verified_growth(context)
        flows = [
            verify_flow(FlowProof.from_dict(record), entries, growth)
            for record in _records(
                context, "flows", "flow_proofs.jsonl", "flow_proofs"
            )
        ]
        # Lifecycle CodeQL results are candidate-only. Bind each row to one
        # concrete E->G path.  Filename equality is never a binding proof: a
        # candidate must share the Growth callable and (for resource families)
        # the canonical resource identity.  This deliberately leaves custom or
        # interprocedural lifecycle patterns partial rather than reusing a
        # same-named receiver from another handler.
        configuration = _modeled_configuration(context)
        lifecycle_evidence: list[dict[str, object]] = []
        lifecycle_coverage: list[dict[str, object]] = []
        lifecycle_summaries: list[dict[str, object]] = []
        resource_lifecycle_bindings: list[dict[str, object]] = []
        lifecycle_records = []
        # Strict one-wrapper Guard summaries are independent CodeQL evidence.
        # Promote only their complete, source/CFG/dimension-bearing form to a
        # real candidate; Bound/Release summaries remain partial audit facts.
        wrapper_guards: dict[str, GuardCandidate] = {}
        families = (("guard", guards), ("bound", bounds), ("release", releases))
        for flow in flows:
            entry, result = entries[flow.entry_id], growth[flow.growth_id]
            if result.candidate is None:
                raise AnalyzerError("ANALYSIS_DANGLING_FACT_REFERENCE", "Lifecycle flow has no Growth anchor.")
            anchor = result.candidate
            resource_binding = None
            if resource_run is not None and resource_lifecycle_propagation_enabled:
                resource_binding = bind_resource_lifecycle_property(
                    entry, result, flow, resource_run
                )
                resource_lifecycle_bindings.append(dict(resource_binding.record))
            elif (
                resource_coverage_gap is not None
                and resource_lifecycle_propagation_enabled
            ):
                resource_binding = bind_resource_lifecycle_coverage_gap(
                    entry, result, flow, resource_coverage_gap
                )
                resource_lifecycle_bindings.append(dict(resource_binding.record))
            # Summary rows are independently decoded source locations and are
            # re-bound here to the exact verified flow anchor. They are audit
            # evidence only until a family candidate with the same CodeQL
            # receiver/argument witness is available; never promote a summary
            # based on source ordering or expression text.
            for summary in summaries_raw:
                if summary["anchor_file"] != anchor.site.file or summary["anchor_start_line"] != anchor.site.start_line:
                    continue
                lifecycle_summaries.append(LifecycleSummary(
                    entry.entry_id, result.growth_id, flow.path_id, summary["family"],
                    summary["candidate_file"], summary["candidate_start_line"],
                    summary["callsite_file"], summary["callsite_start_line"],
                    summary["receiver_file"], summary["receiver_start_line"], summary["argument_index"],
                    summary["resource_dimension"], summary["scope"], summary["configuration_key"], summary["configuration_value"],
                    summary["representation"], summary["phase"], summary["covers_materialization"], summary["dominates_growth"],
                    summary["reject_path_reaches_growth"], summary["evidence"],
                    summary["cfg_relation"], summary["coverage_status"], summary["coverage_note"],
                ).to_dict())
                if (
                    summary["family"] == "guard" and summary["coverage_status"] == "complete"
                    and summary["cfg_relation"] == "one_wrapper" and summary["covers_materialization"]
                    and summary["resource_dimension"] == anchor.resource_dimension
                    and summary["scope"] == anchor.escape_scope
                    and summary["phase"] in {"before_growth", "inside_growth"}
                ):
                    wrapper = GuardCandidate.create(
                        site_file=summary["candidate_file"], site_start_line=summary["candidate_start_line"],
                        kind="input_validation", resource_dimension=summary["resource_dimension"], scope=summary["scope"],
                        behavior="reject", dominates_growth=summary["dominates_growth"],
                        reject_path_reaches_growth=summary["reject_path_reaches_growth"],
                        configuration_key=summary["configuration_key"], configuration_value=summary["configuration_value"],
                        representation=summary["representation"], phase=summary["phase"],
                        covers_materialization=summary["covers_materialization"], authorization_only=False,
                        evidence=[summary["evidence"]], coverage_status="complete",
                    )
                    if wrapper.guard_id not in wrapper_guards:
                        wrapper_guards[wrapper.guard_id] = wrapper
                        guards.append(wrapper)
                        guard_records.append(wrapper.to_dict())
                    candidate_anchors["guard"].setdefault(wrapper.guard_id, set()).add((anchor.site.file, anchor.site.start_line))
            linked: dict[str, list[object]] = {"guard": [], "bound": [], "release": []}
            coverage_by_family: dict[str, str] = {}
            for family, candidates_for_family in families:
                local = []
                complete = []
                for candidate in candidates_for_family:
                    candidate_id = getattr(candidate, f"{family}_id")
                    anchored = (anchor.site.file, anchor.site.start_line) in candidate_anchors[family].get(candidate_id, set())
                    candidate_receiver = getattr(candidate, "receiver", anchor.receiver)
                    # The query provides the anchored CFG witness.  For resource
                    # families retain canonical receiver equality; guard is
                    # representation-bound by its own complete witness.
                    # Guard rows are usable only for the exact anchored bytes
                    # demand; a dominating unrelated authorization/condition is
                    # never a resource-bound witness.
                    same_resource = (
                        candidate.resource_dimension == anchor.resource_dimension
                        if family == "guard"
                        else candidate_receiver == anchor.receiver
                    )
                    if anchored and same_resource:
                        local.append(candidate)
                        if candidate.coverage_status == "complete":
                            complete.append(candidate)
                modeled = [
                    item for item in coverage_raw
                    if item.get("anchor_file") == anchor.site.file
                    and item.get("anchor_start_line") == anchor.site.start_line
                    and item.get("family") == family
                ]
                # A candidate row alone never proves no-match coverage. Only the
                # explicit modeled-domain query may make a candidate-free family
                # complete, and it is tied to this exact Growth anchor.
                if complete:
                    status, reason = "complete", "LIFECYCLE_SAME_CALLABLE_RESOURCE_WITNESS"
                elif any(item.get("coverage_status") == "complete" for item in modeled):
                    status = "complete"
                    reason = str(next(item.get("coverage_note") for item in modeled if item.get("coverage_status") == "complete"))
                elif local:
                    status, reason = "partial", "LIFECYCLE_CANDIDATE_PARTIAL"
                elif modeled:
                    status, reason = "partial", str(modeled[0].get("coverage_note", "LIFECYCLE_CFG_OR_RESOURCE_ALIAS_UNPROVEN"))
                else:
                    status, reason = "partial", "LIFECYCLE_CFG_OR_RESOURCE_ALIAS_UNPROVEN"
                coverage_by_family[family] = status
                lifecycle_coverage.append(LifecycleCoverage(entry.entry_id, result.growth_id, flow.path_id, family, status, reason).to_dict())
                for candidate in local:
                    candidate_id = getattr(candidate, f"{family}_id")
                    receiver = getattr(candidate, "receiver", anchor.receiver)
                    field = getattr(candidate, "field_path", anchor.field_path) or anchor.field_path
                    key = getattr(candidate, "key_identity", "none")
                    relation = "same_cfg" if candidate in complete else "partial"
                    evidence_status = "complete" if candidate in complete else "partial"
                    lifecycle_evidence.append(LifecycleEvidence(entry.entry_id, result.growth_id, flow.path_id, family, candidate_id, anchor.site.file, anchor.site.start_line, candidate.site_file, candidate.site_start_line, receiver, field, key, relation, evidence_status).to_dict())
                    linked[family].append(candidate)
            if not flow.satisfies_premise or result.status != "verified":
                reasons = tuple(sorted(set((*flow.reason_codes, *result.reason_codes, "LIFECYCLE_PREMISE_UNRESOLVED"))))
                guard = GuardDecision("unknown", reasons, (), (), reasons, ())
                bound = BoundDecision("unknown", reasons, (), (), reasons, ())
                release = ReleaseDecision("unknown", "unknown", reasons, (), (), reasons, ())
            else:
                guard = evaluate_guard(entry, result, flow, cast(Sequence[GuardCandidate], linked["guard"]), configuration, coverage_status=coverage_by_family["guard"])
                bound = _evaluate_path_bounds(
                    entry,
                    result,
                    flow,
                    cast(Sequence[BoundCandidate], linked["bound"]),
                    configuration,
                    coverage_status=coverage_by_family["bound"],
                )
                release = evaluate_synchronous_release(entry, result, flow, cast(Sequence[ReleaseCandidate], linked["release"]), coverage_status=coverage_by_family["release"])
            semantic = {
                "entry_id": entry.entry_id,
                "growth_id": result.growth_id,
                "path_id": flow.path_id,
                "guard_decision": guard.status,
                "bound_decision": bound.status,
                "release_decision": release.status,
                "resource_decision": (
                    resource_binding.resource_decision.status
                    if resource_binding is not None
                    else None
                ),
                "reason_codes": sorted(
                    set(
                        (
                            *guard.reason_codes,
                            *bound.reason_codes,
                            *release.reason_codes,
                            *(
                                resource_binding.resource_decision.reason_codes
                                if resource_binding is not None
                                else ()
                            ),
                        )
                    )
                ),
                "guard": _decision_record(guard),
                "bound": _decision_record(bound),
                "release": _decision_record(release),
                "resource": (
                    resource_binding.resource_decision.to_dict()
                    if resource_binding is not None
                    else None
                ),
            }
            lifecycle_records.append({"lifecycle_result_id": stable_identifier("lifecycle", semantic), **semantic})
        validate_records("guard_candidates", guard_records)
        validate_records("bound_candidates", bound_records)
        validate_records("release_candidates", release_records)
        validate_records("lifecycle_evidence", lifecycle_evidence)
        validate_records("lifecycle_summaries", lifecycle_summaries)
        validate_records(
            "resource_lifecycle_bindings", resource_lifecycle_bindings
        )
        validate_records("lifecycle_coverage", lifecycle_coverage)
        validate_records("lifecycle_results", lifecycle_records)
        artifacts: dict[str, object] = {
            "guard_candidates.jsonl": guard_records,
            "bound_candidates.jsonl": bound_records,
            "release_candidates.jsonl": release_records,
            "lifecycle_summaries.jsonl": lifecycle_summaries,
            "resource_lifecycle_bindings.jsonl": resource_lifecycle_bindings,
            "lifecycle_evidence.jsonl": lifecycle_evidence,
            "lifecycle_coverage.jsonl": lifecycle_coverage,
            "lifecycle_results.jsonl": lifecycle_records,
        }
        if resource_run is not None:
            from dosweb.resource_lifecycle.adapters import extracted_to_dict

            artifacts["resource_lifecycle_facts.private.json"] = (
                canonical_json(extracted_to_dict(resource_run.extracted)) + b"\n"
            )
            artifacts["resource_lifecycle_results.private.json"] = (
                canonical_json(dict(resource_run.results)) + b"\n"
            )
        return StageOutput(
            artifacts,  # type: ignore[arg-type]
            {
                "flow_count": len(flows),
                "coverage_partial_count": len(lifecycle_coverage),
                "summary_count": len(lifecycle_summaries),
                "resource_lifecycle_binding_count": len(
                    resource_lifecycle_bindings
                ),
            },
        )
    return execute


def _eligible_conclusion_pairs(
    dispositions: Sequence[Mapping[str, object]],
    links: Sequence[Mapping[str, object]],
    flow_pairs: set[tuple[str, str]],
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], str]]:
    """Resolve the only disposition classes allowed to publish conclusions."""

    links_by_id = {
        record["link_id"]: record
        for record in links
        if isinstance(record, Mapping) and isinstance(record.get("link_id"), str)
    }
    if len(links_by_id) != len(links):
        raise AnalyzerError(
            "ARTIFACT_UPSTREAM_INVALID", "Candidate Entry links are duplicated or malformed."
        )
    eligible_pairs: set[tuple[str, str]] = set()
    statuses: dict[tuple[str, str], str] = {}
    for disposition in dispositions:
        status = disposition.get("status")
        if status not in {"formal_eligible", "gap_eligible"}:
            continue
        growth_id = disposition.get("growth_id")
        link_ids = disposition.get("link_ids")
        if (
            not isinstance(growth_id, str)
            or not isinstance(link_ids, list)
            or not link_ids
            or any(not isinstance(link_id, str) for link_id in link_ids)
            or any(link_id not in links_by_id for link_id in link_ids)
        ):
            raise AnalyzerError(
                "ANALYSIS_DANGLING_FACT_REFERENCE",
                "Candidate disposition references a missing Entry link.",
            )
        linked = [links_by_id[link_id] for link_id in link_ids]
        pairs: list[tuple[str, str]] = []
        for link in linked:
            entry_id = link.get("entry_id")
            link_growth_id = link.get("growth_id")
            if (
                not isinstance(entry_id, str)
                or link_growth_id != growth_id
                or (entry_id, growth_id) not in flow_pairs
            ):
                raise AnalyzerError(
                    "ARTIFACT_UPSTREAM_HASH_MISMATCH",
                    "Candidate-relevant Growth is missing its required flow artifact.",
                )
            pairs.append((entry_id, growth_id))
        for pair in pairs:
            previous = statuses.get(pair)
            if previous is not None and previous != status:
                raise AnalyzerError(
                    "ARTIFACT_UPSTREAM_INVALID",
                    "Candidate conclusion eligibility is ambiguous.",
                )
            eligible_pairs.add(pair)
            statuses[pair] = status
    return eligible_pairs, statuses


def _candidate_relevant_gap_free(disposition_status: str) -> bool:
    return disposition_status == "formal_eligible"


def _conclusion_amplification_classes(
    dispositions: Sequence[Mapping[str, object]],
    eligible_pairs: set[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    allowed = {
        "superlinear",
        "large_single_request",
        "concurrent_retention",
        "queue_instability",
        "high_cardinality_retention",
        "low_amplification",
        "unknown",
    }
    by_growth: dict[str, str] = {}
    prefix = "RELEVANCE_AMPLIFICATION_"
    for disposition in dispositions:
        growth_id = disposition.get("growth_id")
        reasons = disposition.get("reason_codes")
        if not isinstance(growth_id, str) or not isinstance(reasons, list):
            continue
        classes = {
            reason[len(prefix) :].lower()
            for reason in reasons
            if isinstance(reason, str) and reason.startswith(prefix)
        }
        classes &= allowed
        if len(classes) == 1:
            by_growth[growth_id] = classes.pop()
    return {pair: by_growth.get(pair[1], "unknown") for pair in eligible_pairs}


def make_conclude_executor() -> Executor:
    def execute(context: StageContext) -> StageOutput:
        entries = _load_entries(context)
        growth = _load_verified_growth(context)
        flows = [verify_flow(FlowProof.from_dict(record), entries, growth) for record in _records(context, "flows", "flow_proofs.jsonl", "flow_proofs")]
        lifecycle = {record["path_id"]: record for record in _records(context, "lifecycle", "lifecycle_results.jsonl", "lifecycle_results")}
        resource_by_path = {
            path_id: (
                ResourceLifecycleDecision.from_dict(record["resource"])
                if isinstance(record.get("resource"), Mapping)
                else None
            )
            for path_id, record in lifecycle.items()
        }
        coverage_records = [LifecycleCoverage.from_dict(record) for record in _strict_records(context, "lifecycle", "lifecycle_coverage.jsonl")]
        coverage_by_key = {
            (item.entry_id, item.growth_id, item.path_id, item.family): item.status
            for item in coverage_records
        }
        coverage_keys = set(coverage_by_key)
        guards = [GuardCandidate.from_dict(record) for record in _strict_records(context, "lifecycle", "guard_candidates.jsonl")]
        bounds = [BoundCandidate.from_dict(record) for record in _strict_records(context, "lifecycle", "bound_candidates.jsonl")]
        releases = [ReleaseCandidate.from_dict(record) for record in _strict_records(context, "lifecycle", "release_candidates.jsonl")]
        framework_coverage = {item.framework: item for item in _coverage(context)}
        from dosweb.reachability.models import ReachabilityDecision
        reachability = {record["entry_id"]: ReachabilityDecision(record["entry_id"], record["auth_contract_id"], record["auth_context"], record["deployment_status"], record["status"], tuple(record["evidence_ids"]), tuple(record["reason_codes"]), record["decision_id"]) for record in _strict_records(context, "growth", "reachability_decisions.jsonl")}
        from dosweb.growth import RepeatabilityDecision, AmplificationDecision
        repeatability = {(record["entry_id"], record["growth_id"]): RepeatabilityDecision(record["decision_id"], record["entry_id"], record["growth_id"], record["status"], tuple(record["evidence_ids"]), tuple(record["reason_codes"]), "repeatability") for record in _strict_records(context, "growth", "repeatability_decisions.jsonl")}
        amplification = {(record["entry_id"], record["growth_id"]): AmplificationDecision(record["decision_id"], record["entry_id"], record["growth_id"], record["status"], tuple(record["evidence_ids"]), tuple(record["reason_codes"]), "amplification") for record in _strict_records(context, "growth", "amplification_decisions.jsonl")}
        certificates: list[dict[str, object]] = []
        findings: list[dict[str, object]] = []
        certificate_objects: list[LifecycleCertificate] = []
        finding_objects: list[StaticFinding] = []
        link_records = _strict_records(context, "growth", "candidate_entry_links.jsonl")
        disposition_records = _strict_records(context, "growth", "candidate_dispositions.jsonl")
        flow_pairs = {(flow.entry_id, flow.growth_id) for flow in flows}
        eligible_pairs, disposition_statuses = _eligible_conclusion_pairs(
            disposition_records, link_records, flow_pairs
        )
        amplification_classes = _conclusion_amplification_classes(
            disposition_records, eligible_pairs
        )
        grouped: dict[tuple[str, str], list[VerifiedFlow]] = {}
        for flow in flows:
            if (flow.entry_id, flow.growth_id) not in eligible_pairs:
                continue
            if flow.path_id not in lifecycle:
                raise AnalyzerError("ARTIFACT_UPSTREAM_HASH_MISMATCH", "Lifecycle result is missing a flow path.")
            missing_families = {family for family in ("guard", "bound", "release") if (flow.entry_id, flow.growth_id, flow.path_id, family) not in coverage_keys}
            if missing_families:
                raise AnalyzerError("ARTIFACT_UPSTREAM_HASH_MISMATCH", "Lifecycle family coverage is missing for a relevant flow.")
            grouped.setdefault((flow.entry_id, flow.growth_id), []).append(flow)
        for (entry_id, growth_id), group in sorted(grouped.items()):
            ordered = tuple(sorted(group, key=lambda flow: flow.path_id))
            proven = tuple(flow for flow in ordered if flow.satisfies_premise)
            entry, result = entries[entry_id], growth[growth_id]
            durable = lifecycle[ordered[0].path_id]
            guard = _guard_decision(durable["guard"])
            bound = _bound_decision(durable["bound"])
            release = _release_decision(durable["release"])
            if any(
                lifecycle[flow.path_id][name] != durable[name]
                for flow in ordered[1:]
                for name in ("guard", "bound", "release")
            ):
                raise AnalyzerError(
                    "ARTIFACT_UPSTREAM_INVALID",
                    "Lifecycle decisions disagree across proven paths.",
                )
            evaluations_by_path = tuple(
                (
                    flow,
                    evaluate_assertion_1(
                        result,
                        flow,
                        guard,
                        bound,
                        amplification=amplification.get((entry_id, growth_id)),
                        reachability=reachability.get(entry_id),
                        resource_lifecycle=resource_by_path[flow.path_id],
                    ),
                    evaluate_assertion_2(
                        result,
                        flow,
                        bound,
                        release,
                        reachability=reachability.get(entry_id),
                        repeatability=repeatability.get((entry_id, growth_id)),
                        resource_lifecycle=resource_by_path[flow.path_id],
                    ),
                )
                for flow in ordered
            )
            assertions = tuple(
                evaluation
                for _flow, assertion_1, assertion_2 in evaluations_by_path
                for evaluation in (assertion_1, assertion_2)
            )
            framework_item = framework_coverage.get(entry.framework, FrameworkCoverage(entry.framework, "unsupported", (), ("no_coverage",), "forces_unknown"))
            registration_pattern_id = entry.registration_pattern_id
            # Framework-level dynamic/reflection gaps do not taint a concrete
            # Entry only when this Entry's exact persisted pattern identity is
            # present in the authenticated framework coverage artifact.
            coverage = CandidateCoverage.from_framework(
                framework_item,
                registration_pattern_id=registration_pattern_id,
                entry_id=entry.entry_id,
                growth_id=growth_id,
            )
            proof_gate = VerdictProofGate(
                entry_complete=coverage.status == "complete",
                ordinary_reachability=(
                    reachability.get(entry_id) is not None
                    and reachability[entry_id].status == "ordinary_attacker_reachable"
                ),
                growth_verified=result.status == "verified",
                flow_proven=bool(proven) and len(proven) == len(ordered),
                assertion_1_lifecycle_complete=all(
                    assertion_1.status == "not_applicable"
                    or (
                        resource_by_path[flow.path_id] is not None
                        and resource_by_path[flow.path_id].status
                        == "refutes_relevant_growth"
                    )
                    or all(
                        coverage_by_key.get((entry_id, growth_id, flow.path_id, family)) == "complete"
                        for family in ("guard", "bound")
                    )
                    for flow, assertion_1, _assertion_2 in evaluations_by_path
                ),
                assertion_2_lifecycle_complete=all(
                    assertion_2.status == "not_applicable"
                    or (
                        resource_by_path[flow.path_id] is not None
                        and resource_by_path[flow.path_id].status
                        == "refutes_relevant_growth"
                    )
                    or all(
                        coverage_by_key.get((entry_id, growth_id, flow.path_id, family)) == "complete"
                        for family in ("bound", "release")
                    )
                    for flow, _assertion_1, assertion_2 in evaluations_by_path
                ),
                candidate_relevant_gap_free=(
                    _candidate_relevant_gap_free(
                        disposition_statuses[(entry_id, growth_id)]
                    )
                ),
            )
            verdict = apply_positive_proof_gate(
                derive_verdict(assertions, coverage), proof_gate
            )
            certificate = build_lifecycle_certificate(
                entry, result, ordered, guard, bound, release,
                assertions, coverage, verdict,
                reachability=reachability.get(entry_id), repeatability=repeatability.get((entry_id, growth_id)), amplification=amplification.get((entry_id, growth_id)),
                resource_lifecycle={
                    flow.path_id: resource_by_path[flow.path_id]
                    for flow in ordered
                },
                proof_gate=proof_gate,
            )
            finding = StaticFinding.from_certificate(certificate)
            certificate_objects.append(certificate)
            finding_objects.append(finding)
            certificates.append(certificate.to_dict()); findings.append(finding.to_dict())
        families = build_finding_families(
            tuple(finding_objects),
            tuple(certificate_objects),
            entries,
            reachability,
            amplification_classes,
        )
        family_records = [family.to_dict() for family in families]
        validate_records("lifecycle_certificates", certificates)
        validate_records("static_findings", findings)
        validate_records("finding_families", family_records)
        return StageOutput(
            {
                "lifecycle_certificates.jsonl": certificates,
                "static_findings.jsonl": findings,
                "finding_families.jsonl": family_records,
            },
            {
                "finding_count": len(findings),
                "finding_family_count": len(family_records),
                "unresolved_path_count": sum(not flow.satisfies_premise for flow in flows),
            },
        )
    return execute


def make_report_executor() -> Executor:
    def execute(context: StageContext) -> StageOutput:
        cert_records = _records(context, "conclude", "lifecycle_certificates.jsonl", "lifecycle_certificates")
        finding_records = _records(context, "conclude", "static_findings.jsonl", "static_findings")
        family_records = _records(context, "conclude", "finding_families.jsonl", "finding_families")
        certificates = [LifecycleCertificate(**{**record, "attacker_inputs": tuple(record["attacker_inputs"]), "path_ids": tuple(record["path_ids"]), "resource_lifecycle_decisions": tuple(record["resource_lifecycle_decisions"]), "assertions": tuple(record["assertions"]), "reason_codes": tuple(record["reason_codes"]), "assumptions": tuple(record["assumptions"]), "coverage_gaps": tuple(record["coverage_gaps"]), "unresolved_facts": tuple(record["unresolved_facts"]), "suggested_follow_up_measurements": tuple(record["suggested_follow_up_measurements"])}) for record in cert_records]
        findings = [StaticFinding.from_dict(record) for record in finding_records]
        families = [FindingFamily.from_dict(record) for record in family_records]
        summary = build_summary(families, findings, _coverage(context))
        return StageOutput({"summary.json": canonical_json(summary) + b"\n", "report.md": render_report(summary, families, findings, certificates)})
    return execute


class ProductionPipeline:
    def __init__(self, pipeline: Pipeline, config: AnalyzerConfig, available_stages: frozenset[str]) -> None:
        self._pipeline, self.config, self._available_stages = pipeline, config, available_stages
    @property
    def output_root(self) -> Path: return self._pipeline.output_root
    def _fingerprint(self, stage: str, upstream: Mapping[str, str]): return self._pipeline._fingerprint(stage, upstream)  # noqa: SLF001
    def run(self, target: str = "analyze") -> Mapping[str, object]:
        last_stage = "report" if target == "analyze" else target
        if last_stage not in STAGES: raise AnalyzerError("CONFIG_INVALID_COMMAND", f"Unknown pipeline target: {target}.")
        if STAGES.index(last_stage) >= STAGES.index("growth") and not self.config.llm.allow_remote_llm:
            raise AnalyzerError("CONFIG_REMOTE_LLM_NOT_AUTHORIZED", "Remote LLM calls require explicit authorization.")
        required = set(STAGES[: STAGES.index(last_stage) + 1]); missing = sorted(required - self._available_stages)
        if missing: raise AnalyzerError("INTERNAL_STAGE_EXECUTORS_UNAVAILABLE", "Production stage executors are unavailable.", {"missing_stages": missing})
        return self._pipeline.run(target)


def build_production_pipeline(values: Mapping[str, object], *, environ: Mapping[str, str] | None = None, secrets_path: Path | None = None, stage_executors: Mapping[str, Executor] | None = None, validate_database_fn: Callable[..., DatabaseInfo] | None = None, run_query_fn: Callable[..., QueryResult] | None = None, resource_lifecycle_provider: Callable[[DatabaseInfo, Path], ResourceLifecycleBackendRun] | None = None, resource_lifecycle_provider_identity: str | None = None, resource_lifecycle_propagation_enabled: bool = True, create_execution_snapshot_fn: Callable[..., DatabaseInfo] | None = None, cleanup_execution_snapshot_fn: Callable[[DatabaseInfo], None] | None = None, deepseek_client: object | None = None, deepseek_client_factory: Callable[[object], object] | None = None, source_excerpt_fn: Callable[[Path, str, str, int], SourceExcerpt] = extract_source_excerpt) -> ProductionPipeline:
    config_path = values.get("config")
    if config_path is not None and not isinstance(config_path, Path): raise AnalyzerError("CONFIG_INVALID_VALUE", "config must be a path.")
    if secrets_path is None:
        secrets_path = _DEFAULT_SECRETS_PATH
    env = os.environ if environ is None else environ
    if values.get("command") == "entries":
        env = {key: value for key, value in env.items() if key != "DEEPSEEK_API_KEY"}; values = dict(values); values["allow_remote_llm"] = False
    config = load_config(values, config_path, env, secrets_path=secrets_path); validate = validate_database_fn or globals()["validate_database"]; runner = run_query_fn or globals()["run_query"]
    if not isinstance(resource_lifecycle_propagation_enabled, bool):
        raise AnalyzerError(
            "CONFIG_INVALID_VALUE",
            "Resource lifecycle propagation mode must be boolean.",
        )
    snapshot_factory = create_execution_snapshot_fn or globals()["create_execution_database_snapshot"]
    snapshot_cleanup = cleanup_execution_snapshot_fn or globals()["cleanup_execution_database_snapshot"]
    owned_database: DatabaseInfo | None = None
    validated_database: DatabaseInfo | None = None; validated_pack: dict[str, bytes] | None = None
    def current_database() -> DatabaseInfo:
        if validated_database is None: raise AnalyzerError("CODEQL_DATABASE_INVALID", "CodeQL database validation failed.")
        return validated_database
    def current_pack() -> Mapping[str, bytes]:
        if validated_pack is None: raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.")
        return validated_pack
    if stage_executors is None:
        client_factory = deepseek_client_factory or DeepSeekClient
        resource_provider = resource_lifecycle_provider
        resource_backend_identity = (
            resource_lifecycle_provider_identity
            if resource_provider is not None
            else "disabled"
        )
        if resource_provider is not None and (
            not isinstance(resource_backend_identity, str)
            or not resource_backend_identity
        ):
            raise AnalyzerError(
                "CONFIG_INVALID_VALUE",
                "Injected resource lifecycle provider requires a stable identity.",
            )
        # Real CLI execution selects the RC1 queries as part of the formal
        # lifecycle stage. Tests that inject a query runner must explicitly
        # inject a resource provider as well; an unrelated fake query family
        # must never be mistaken for RC1 evidence.
        if resource_provider is None and run_query_fn is None:
            from dosweb.resource_lifecycle.commands import _implementation_sha256
            from dosweb.resource_lifecycle.models import SCHEMA_VERSION as RESOURCE_SCHEMA_VERSION

            resource_backend_identity = (
                f"rc1:{RESOURCE_SCHEMA_VERSION}:{_implementation_sha256()}"
            )
            def resource_provider(
                database: DatabaseInfo, output: Path
            ) -> ResourceLifecycleBackendRun:
                from dosweb.resource_lifecycle.commands import (
                    analyze_codeql_database_in_memory,
                )

                resource_pack = _materialize_query_pack(
                    output.parent / "frozen-resource-pack", current_pack()
                )
                query_paths = (
                    resource_pack
                    / "dosweb/ResourceLifecycle/ResourceLifecycleFacts.ql",
                    resource_pack
                    / "dosweb/ResourceLifecycle/ResourceLifecycleTaskRelations.ql",
                )
                extracted, results, implementation_sha256, facts_sha256 = (
                    analyze_codeql_database_in_memory(
                        database,
                        output,
                        codeql_binary=config.codeql_binary,
                        query_paths=query_paths,
                    )
                )
                return ResourceLifecycleBackendRun(
                    extracted,
                    results,
                    implementation_sha256,
                    facts_sha256,
                )

        resource_backend_identity = (
            f"{resource_backend_identity}:propagation="
            f"{'on' if resource_lifecycle_propagation_enabled else 'off'}"
        )
        executors: dict[str, Executor] = {"entries": make_entries_executor(config, run_query_fn=runner, database_info_fn=current_database, query_pack_snapshot_fn=current_pack), "growth": make_growth_executor(config, database_info_fn=current_database, query_pack_snapshot_fn=current_pack, run_query_fn=runner, deepseek_client=deepseek_client, deepseek_client_factory=client_factory, source_excerpt_fn=source_excerpt_fn), "flows": make_flows_executor(config, database_info_fn=current_database, query_pack_snapshot_fn=current_pack, run_query_fn=runner), "lifecycle": make_lifecycle_executor(config, database_info_fn=current_database, query_pack_snapshot_fn=current_pack, run_query_fn=runner, resource_lifecycle_provider=resource_provider, resource_lifecycle_propagation_enabled=resource_lifecycle_propagation_enabled), "conclude": make_conclude_executor(), "report": make_report_executor()}
    else:
        resource_backend_identity = "stage-executors"
        executors = dict(stage_executors)
        if set(executors) != set(STAGES): raise AnalyzerError("INTERNAL_STAGE_EXECUTORS_UNAVAILABLE", "Production stage executors are unavailable.", {"missing_stages": sorted(set(STAGES) - set(executors))})
    pipeline: Pipeline
    def preflight() -> None:
        nonlocal owned_database, validated_database, validated_pack
        pack_hash, snapshot = _query_pack_snapshot(); database = validate(config.database)
        if not isinstance(database, DatabaseInfo): raise AnalyzerError("CODEQL_DATABASE_INVALID", "CodeQL database validation failed.")
        try:
            source_root = database.source_root.resolve(strict=True)
            analysis_root = config.llm.analysis_source_root.resolve(strict=True)
        except (AttributeError, OSError, RuntimeError) as exc:
            raise AnalyzerError(
                "CODEQL_DATABASE_INVALID",
                "CodeQL database source provenance does not match the configured checkout.",
            ) from exc
        if source_root != analysis_root:
            raise AnalyzerError(
                "CODEQL_DATABASE_INVALID",
                "CodeQL database source provenance does not match the configured checkout.",
            )
        def register_owner(candidate: DatabaseInfo) -> None:
            nonlocal owned_database
            if (
                not isinstance(candidate, DatabaseInfo)
                or candidate.execution is None
                or owned_database is not None
            ):
                raise TypeError("invalid execution snapshot ownership")
            owned_database = candidate

        validated_database = snapshot_factory(
            database,
            config.output,
            validate_database_fn=validate,
            owner_callback=register_owner,
        )
        if (
            not isinstance(validated_database, DatabaseInfo)
            or validated_database.execution is None
            or owned_database is not validated_database
        ):
            validated_database = None
            raise AnalyzerError(
                "CODEQL_EXECUTION_SNAPSHOT_FAILED",
                "Private CodeQL execution database snapshot failed.",
                {"stage": "validation", "reason": "EXECUTION_BINDING_REQUIRED"},
            )
        validated_pack = snapshot; pipeline.query_pack_hash = pack_hash; pipeline.database_fingerprint = database.fingerprint
        # Bounded best-effort metadata only; query execution remains authoritative.
        codeql_version = "unavailable"
        try:
            completed = subprocess.run([config.codeql_binary, "version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5, check=False)
            if completed.returncode == 0:
                codeql_version = completed.stdout.strip().replace("\x00", " ")[:256] or "unavailable"
        except (OSError, subprocess.SubprocessError):
            pass
        pipeline.run_identity.update({"codeql_cli_version": codeql_version, "query_pack_hash": pack_hash, "database_fingerprint": database.fingerprint, "source_root": str(source_root)})
    def finalizer() -> None:
        nonlocal owned_database, validated_database
        database = owned_database
        if not isinstance(database, DatabaseInfo) or database.execution is None:
            owned_database = None
            validated_database = None
            return
        validation_failure: BaseException | None = None
        try:
            validate_canonical_database(
                database,
                validate_database_fn=validate,
            )
        except BaseException as exc:
            validation_failure = exc
        try:
            try:
                snapshot_cleanup(database)
            finally:
                snapshot_cleanup(database)
        finally:
            owned_database = None
            validated_database = None
        if validation_failure is not None:
            raise validation_failure
    if config.allow_partial_codeql and values.get("command") != "entries":
        raise AnalyzerError("CONFIG_INVALID_VALUE", "Partial CodeQL execution is restricted to exploratory entries runs.")
    analysis_mode = "exploratory_entries" if config.allow_partial_codeql else "formal"
    pipeline = Pipeline(config.output, executors, database_fingerprint="", query_pack_hash="", config_fingerprint=_digest({**_non_secret_config(config), "analysis_mode": analysis_mode, "query_failure_policy": "coverage_gap" if config.allow_partial_codeql else "fail_closed", "resource_lifecycle_backend": resource_backend_identity}), model_fingerprint=_digest({"base_url": config.llm.base_url, "model": config.llm.model, "temperature": config.llm.temperature}), report_fingerprint=_digest({"renderer": "markdown-v1"}), implementation_versions=_IMPLEMENTATION_VERSIONS, resume=config.resume, preflight=preflight if stage_executors is None else None, finalizer=finalizer if stage_executors is None else None, run_identity={"analysis_mode": analysis_mode, "query_failure_policy": "coverage_gap" if config.allow_partial_codeql else "fail_closed", "codeql_binary": config.codeql_binary, "resource_lifecycle_backend": resource_backend_identity})
    # DeepSeekClient is constructed lazily by the Growth executor, so exposing
    # the complete graph here does not perform provider work during factory
    # construction or pipeline preflight.
    return ProductionPipeline(pipeline, config, frozenset(executors))


__all__ = ["ProductionPipeline", "build_production_pipeline", "make_entries_executor", "make_growth_executor", "make_flows_executor", "make_lifecycle_executor", "make_conclude_executor", "make_report_executor", "run_query", "validate_database"]
