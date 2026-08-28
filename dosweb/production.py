"""Concrete, network-free-capable production pipeline adapters."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, cast

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.artifacts.jsonl import read_jsonl_bytes_strict
from dosweb.artifacts.metadata import read_upstream_artifact_bytes
from dosweb.artifacts.schemas import SCHEMA_VERSION as ARTIFACT_SCHEMA_VERSION, validate_records, validate_references
from dosweb.codeql.database import DatabaseInfo, validate_database as _validate_database
from dosweb.codeql.decoder import DecodeSource, decode_bqrs_json
from dosweb.codeql.runner import QueryResult, run_query as _run_query
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
from dosweb.entries.jaxrs_source import augment_source_backed_jaxrs_entries
from dosweb.entries.normalize import normalize_entry_rows, normalize_framework_coverage, normalize_gap_entry_rows
from dosweb.errors import AnalyzerError
from dosweb.entries.webxml import resolve_webxml_servlet_candidates, validate_descriptor_coverage
from dosweb.flows.models import FlowProof, expression_binds_demand, normalize_flow_rows
from dosweb.flows.verify import VerifiedFlow, verify_flow
from dosweb.growth.contracts import validate_contract_static_evidence
from dosweb.growth.completeness import CandidateDisposition
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
from dosweb.llm.deepseek import DeepSeekClient
from dosweb.pipeline import Executor, Pipeline, STAGES, StageContext, StageOutput
from dosweb.report.markdown import render_report
from dosweb.report.families import FindingFamily, build_finding_families
from dosweb.report.summary import build_summary

_IMPLEMENTATION_VERSIONS: Final = {
    stage: (
        f"production-v2.6-poc33-demo-repair-{stage}-v2"
        if stage in {"entries", "flows"}
        else f"production-v2.6-poc33-demo-repair-{stage}-v1"
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
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
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


def _bounded_json_file(path: Path) -> Mapping[str, object]:
    try:
        raw = _bounded_regular_file(path, _MAX_DECODED_BYTES)
        value = json.loads(raw.decode("utf-8"))
    except (AnalyzerError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, MemoryError, RecursionError) as exc:
        if isinstance(exc, AnalyzerError):
            raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL output could not be read safely.") from exc
        raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL output could not be read safely.") from exc
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


def _run_codeql_family(config: AnalyzerConfig, database: DatabaseInfo, stage: str, query_root: Path, runner: Callable[..., QueryResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix=f"dosweb-{stage}-queries-") as temporary:
        output = Path(temporary) / "results"; output.mkdir(parents=True)
        for query in _query_files(stage, query_root):
            result = runner(query, database, output, codeql_binary=config.codeql_binary, timeout_seconds=_CODEQL_TIMEOUT_SECONDS)
            if not isinstance(result, QueryResult):
                raise AnalyzerError("CODEQL_QUERY_FAILED", "The query runner returned an invalid result.")
            payload = _bounded_json_file(Path(result.decoded_path))
            if stage == "growth":
                family = "growth"
            elif stage in {"flows", "associations"}:
                family = "flow"
            else:
                lowered = query.stem.lower()
                family = "lifecycle_summary" if "lifecyclesummary" in lowered else "lifecycle_coverage" if "lifecyclecoverage" in lowered else "guard" if "guard" in lowered else "bound" if "bound" in lowered else "release"
            decoded = decode_bqrs_json(family, payload, DecodeSource(database.source_root, result.query_sha256))
            if len(rows) + len(decoded) > _MAX_ENTRY_ROWS:
                raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL output exceeds the aggregate row limit.")
            rows.extend({"query_name": family, **item} for item in decoded)
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
        with tempfile.TemporaryDirectory(prefix="dosweb-entry-queries-") as temporary:
            root = Path(temporary) / "pack"
            if query_pack_snapshot_fn:
                effective = _materialize_query_pack(root, query_pack_snapshot_fn()) / "dosweb" / "Entries"
            else:
                effective = query_dir
            rows: list[dict[str, object]] = []
            results = Path(temporary) / "results"; results.mkdir()
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
                    result = runner(effective / name, database, results, codeql_binary=config.codeql_binary, timeout_seconds=_CODEQL_TIMEOUT_SECONDS)
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
                rows.extend(decode_bqrs_json("entries", _bounded_json_file(Path(result.decoded_path)), DecodeSource(database.source_root, result.query_sha256)))
                if len(rows) > _MAX_ENTRY_ROWS:
                    raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL entry output exceeds the aggregate row limit.")
            try:
                result = runner(effective / _INTERPOSITION_QUERY, database, results, codeql_binary=config.codeql_binary, timeout_seconds=_CODEQL_TIMEOUT_SECONDS)
            except AnalyzerError as exc:
                if exc.code != "CODEQL_QUERY_FAILED" or not config.allow_partial_codeql:
                    raise
                skipped_queries += 1
                query_diagnostics.append({"code": exc.code, "query_name": _INTERPOSITION_QUERY})
                interposition_rows: list[dict[str, object]] = []
            else:
                if not isinstance(result, QueryResult):
                    raise AnalyzerError("CODEQL_QUERY_FAILED", "The interposition query runner returned an invalid result.")
                interposition_rows = decode_bqrs_json("entry_interposition", _bounded_json_file(Path(result.decoded_path)), DecodeSource(database.source_root, result.query_sha256))
            try:
                result = runner(effective / _SECURITY_QUERY, database, results, codeql_binary=config.codeql_binary, timeout_seconds=_CODEQL_TIMEOUT_SECONDS)
            except AnalyzerError as exc:
                if exc.code != "CODEQL_QUERY_FAILED" or not config.allow_partial_codeql:
                    raise
                skipped_queries += 1
                query_diagnostics.append({"code": exc.code, "query_name": _SECURITY_QUERY})
                security_rows: list[dict[str, object]] = []
            else:
                if not isinstance(result, QueryResult):
                    raise AnalyzerError("CODEQL_QUERY_FAILED", "The Entry security query runner returned an invalid result.")
                security_rows = decode_bqrs_json("entry_security", _bounded_json_file(Path(result.decoded_path)), DecodeSource(database.source_root, result.query_sha256))
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
    return read_jsonl_bytes_strict(
        _upstream_bytes(context, stage, artifact),
        artifact.removesuffix(".jsonl"),
        source_name=artifact,
    )


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
        for entry in entries.values():
            if row.get("source_file") == entry.handler.file and row.get("source_start_line") == entry.handler.start_line:
                claimed_complete = (
                    row.get("coverage_status") == "complete"
                    and row.get("confidence") == "proven"
                )
                flow_witness = _formal_flow_witness(entry, candidate, row, flow_rows)
                flow_row_matches = _formal_flow_row_matches(candidate, row, flow_rows)
                status = "complete" if claimed_complete and flow_witness else "partial"
                reasons = {str(row.get("coverage_note", "ASSOCIATION_QUERY"))}
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
        if len(linked) > 1 and len({_entry_registration_identity(entry) for entry in linked_entries}) == 1:
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
            disposition_status = "verified_relevant" if canonical_status == "complete" else "unresolved"
            return (canonical_link,), CandidateDisposition.create(
                candidate.growth_id, disposition_status, (canonical_link.link_id,),
                tuple(sorted({"ASSOCIATION_QUERY_EVIDENCE"} | set(canonical_link.reason_codes))),
            )
        disposition_status = "verified_relevant" if len(linked) == 1 and linked[0].status == "complete" else "unresolved"
        return tuple(linked), CandidateDisposition.create(
            candidate.growth_id,
            disposition_status,
            tuple(link.link_id for link in linked),
            tuple(sorted(
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
        return (), CandidateDisposition.create(
            candidate.growth_id,
            "unresolved",
            (),
            ("ASSOCIATION_ENTRY_COVERAGE_UNPROVEN",),
        )
    # Duplicate registrations for one semantic handler are one candidate link.
    if len({_entry_semantic_key(entry) for entry in matches}) == 1:
        matches = (_canonical_entry(matches, candidate),)
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
    return links, CandidateDisposition.create(
        candidate.growth_id,
        "unresolved",
        tuple(link.link_id for link in links),
        tuple(sorted(disposition_reasons)),
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
    if kind in {"input_materialization", "direct_allocation"} or any(
        note.endswith((":single_submission_no_enclosing_loop", ":single_operation_no_enclosing_loop"))
        for note in notes
    ):
        return "not_applicable", "AMPLIFICATION_DIRECT_DEMAND_ASSERTION"
    if (
        any(note.endswith(":attacker_controlled_loop_multiplicity_proven") for note in notes)
        and not any(
            note.endswith(":finite_capacity_prevents_amplification")
            or note.endswith(":loop_bound_not_attacker_proven")
            for note in notes
        )
    ):
        return "proven", "AMPLIFICATION_CFG_DATAFLOW_LOOP_WITNESS"
    return "unknown", "AMPLIFICATION_LOOP_OR_BATCH_UNMODELED"


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
        repeatability: list[dict[str, object]] = []; amplification: list[dict[str, object]] = []
        auth_contracts: list[dict[str, object]] = []; reachability: list[dict[str, object]] = []; audits: list[dict[str, object]] = []
        auth_by_entry: dict[str, object] = {}
        for record in candidate_records:
            candidate = _candidate_from_record(record)
            candidate_links, disposition = _candidate_association(
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
                    set(disposition.reason_codes)
                    | set(relevance.reason_codes)
                    | {
                        "RELEVANCE_AMPLIFICATION_"
                        + relevance.amplification_class.upper()
                    }
                )
            )
            if relevance.status == "rejected":
                disposition = CandidateDisposition.create(
                    candidate.growth_id,
                    "rejected",
                    tuple(link.link_id for link in candidate_links),
                    relevance_reasons,
                )
                dispositions.append(disposition.to_dict())
                continue
            if relevance.status == "unresolved":
                disposition = CandidateDisposition.create(
                    candidate.growth_id,
                    "unresolved",
                    tuple(link.link_id for link in candidate_links),
                    relevance_reasons,
                )
                dispositions.append(disposition.to_dict())
                continue
            if (
                relevance.status == "dos_relevant_partial"
                or disposition.status != "verified_relevant"
                or len(candidate_links) != 1
            ):
                disposition_status = (
                    "dos_relevant_partial"
                    if relevance.status == "dos_relevant_partial"
                    and len(candidate_links) == 1
                    else "unresolved"
                )
                disposition_reasons = (
                    tuple(sorted(set(relevance_reasons) | {"GROWTH_DOS_RELEVANT_PARTIAL"}))
                    if disposition_status == "dos_relevant_partial"
                    else relevance_reasons
                )
                disposition = CandidateDisposition.create(
                    candidate.growth_id,
                    disposition_status,
                    tuple(link.link_id for link in candidate_links),
                    disposition_reasons,
                )
                dispositions.append(disposition.to_dict())
                # Only one canonical high-value partial family is eligible for a
                # downstream static_unknown gap. Multi-entry ambiguity remains
                # disposition inventory and never creates a cross product.
                if disposition_status == "dos_relevant_partial":
                    unresolved = VerifiedGrowthResult.create(
                        candidate=candidate,
                        slice_id=stable_identifier(
                            "slice",
                            {
                                "growth_id": candidate.growth_id,
                                "reason": "candidate_relevance_or_association_partial",
                            },
                        ),
                        status="unresolved",
                        reason_codes=("GROWTH_DOS_RELEVANT_PARTIAL",),
                        checks=(
                            VerificationCheck(
                                "candidate_relevance_and_entry_association",
                                False,
                                "GROWTH_DOS_RELEVANT_PARTIAL",
                            ),
                        ),
                    )
                    verified.append(unresolved.to_dict())
                continue
            entry = entries[candidate_links[0].entry_id]
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
                classify_auth = getattr(classifier, "classify_auth", None)
                if callable(classify_auth):
                    auth = classify_auth(entry.entry_id, security_facts, configuration_facts)
                    from dosweb.reachability.verify import verify_auth_contract
                    decision = verify_auth_contract(entry.entry_id, auth, security_facts, slice_fact_ids=frozenset(item.fact_id for item in security_facts), configuration_facts=configuration_models)
                else:
                    from dosweb.reachability.models import AuthContract, ReachabilityDecision
                    auth = AuthContract("unknown", (), ("auth_transport_unavailable",), "low")
                    contract_id = "auth_contract:" + hashlib.sha256((entry.entry_id + repr(auth.to_dict())).encode()).hexdigest()
                    decision = ReachabilityDecision(entry.entry_id, contract_id, "unknown", "unknown", "unknown", (), ("REACH_AUTH_TRANSPORT_UNAVAILABLE", "REACH_DEPLOYMENT_UNKNOWN"))
                auth_by_entry[entry.entry_id] = (auth, decision)
                auth_contracts.append({"auth_contract_id": decision.auth_contract_id, "entry_id": entry.entry_id, **auth.to_dict()})
                reachability.append(decision.to_dict())
                last_audit = getattr(classifier, "last_audit", None)
                if callable(last_audit):
                    audit = last_audit()
                    if audit is not None:
                        audits.append(audit.to_dict())
            else:
                auth, decision = cached_auth
            if decision.status == "not_entry_reachable":
                disposition = CandidateDisposition.create(
                    candidate.growth_id,
                    "not_entry_reachable",
                    tuple(link.link_id for link in candidate_links),
                    tuple(sorted(set(relevance_reasons) | set(decision.reason_codes))),
                )
                dispositions.append(disposition.to_dict())
                continue
            disposition = CandidateDisposition.create(
                candidate.growth_id,
                "verified_relevant",
                tuple(link.link_id for link in candidate_links),
                relevance_reasons,
            )
            dispositions.append(disposition.to_dict())
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
        validate_records("growth_contracts", contracts); validate_records("verified_growth", verified)
        validate_records("candidate_entry_links", links); validate_records("candidate_dispositions", dispositions)
        validate_records("repeatability_decisions", repeatability); validate_records("amplification_decisions", amplification)
        validate_records("auth_contracts", auth_contracts); validate_records("reachability_decisions", reachability); validate_records("llm_audit", audits)
        return StageOutput({"growth_candidates.jsonl": candidate_records, "candidate_entry_links.jsonl": links, "candidate_dispositions.jsonl": dispositions, "repeatability_decisions.jsonl": repeatability, "amplification_decisions.jsonl": amplification, "growth_contracts.jsonl": contracts, "verified_growth.jsonl": verified, "auth_contracts.jsonl": auth_contracts, "reachability_decisions.jsonl": reachability, "llm_audit.private.jsonl": audits}, {"candidate_count": len(candidate_records), "candidate_disposition_count": len(dispositions), "relevant_candidate_count": sum(item["status"] == "verified_relevant" for item in dispositions), "mapped_candidate_count": len(verified), "skipped_unmapped_candidate_count": sum(item["status"] == "not_entry_reachable" for item in dispositions), "auth_contract_count": len(auth_contracts), "llm_audit_count": len(audits)})
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
    ``dos_relevant_partial`` and only when its single canonical association is
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
        if disposition.get("status") != "dos_relevant_partial":
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
        proofs = normalize_flow_rows(rows, entries, candidates)
        existing_pairs = {
            (record["entry_id"], record["growth_id"])
            for record in proofs
        }
        gap_rows = _candidate_relevant_partial_flow_rows(
            entries,
            candidates,
            _strict_records(
                context, "growth", "candidate_entry_links.jsonl"
            ),
            _strict_records(
                context, "growth", "candidate_dispositions.jsonl"
            ),
            existing_pairs,
        )
        gap_proofs = normalize_flow_rows(gap_rows, entries, candidates)
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


def _load_verified_growth(context: StageContext) -> dict[str, VerifiedGrowthResult]:
    candidates = {
        record["growth_id"]: _candidate_from_record(record)
        for record in _records(
            context, "growth", "growth_candidates.jsonl", "growth_candidates"
        )
    }
    results: dict[str, VerifiedGrowthResult] = {}
    for record in _records(
        context, "growth", "verified_growth.jsonl", "verified_growth"
    ):
        candidate = candidates.get(record["growth_id"])
        result = VerifiedGrowthResult.from_dict(record, candidate)
        results[result.growth_id] = result
    return results


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


def make_lifecycle_executor(config: AnalyzerConfig, *, database_info_fn: Callable[[], DatabaseInfo], query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]], run_query_fn: Callable[..., QueryResult] | None = None) -> Executor:
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        database = database_info_fn()
        analysis_root = config.llm.analysis_source_root or database.source_root
        with tempfile.TemporaryDirectory(prefix="dosweb-pack-") as temporary:
            pack = _materialize_query_pack(Path(temporary), query_pack_snapshot_fn())
            rows = _run_codeql_family(config, database, "lifecycle", pack, runner)
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
                "reason_codes": sorted(set((*guard.reason_codes, *bound.reason_codes, *release.reason_codes))),
                "guard": _decision_record(guard),
                "bound": _decision_record(bound),
                "release": _decision_record(release),
            }
            lifecycle_records.append({"lifecycle_result_id": stable_identifier("lifecycle", semantic), **semantic})
        validate_records("guard_candidates", guard_records)
        validate_records("bound_candidates", bound_records)
        validate_records("release_candidates", release_records)
        validate_records("lifecycle_evidence", lifecycle_evidence)
        validate_records("lifecycle_summaries", lifecycle_summaries)
        validate_records("lifecycle_coverage", lifecycle_coverage)
        validate_records("lifecycle_results", lifecycle_records)
        return StageOutput({"guard_candidates.jsonl": guard_records, "bound_candidates.jsonl": bound_records, "release_candidates.jsonl": release_records, "lifecycle_summaries.jsonl": lifecycle_summaries, "lifecycle_evidence.jsonl": lifecycle_evidence, "lifecycle_coverage.jsonl": lifecycle_coverage, "lifecycle_results.jsonl": lifecycle_records}, {"flow_count": len(flows), "coverage_partial_count": len(lifecycle_coverage), "summary_count": len(lifecycle_summaries)})
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
        if status not in {"verified_relevant", "dos_relevant_partial"}:
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
            assertions = tuple(
                evaluation
                for flow in ordered
                for evaluation in (
                    evaluate_assertion_1(result, flow, guard, bound, amplification=amplification.get((entry_id, growth_id)), reachability=reachability.get(entry_id)),
                    evaluate_assertion_2(result, flow, bound, release, reachability=reachability.get(entry_id), repeatability=repeatability.get((entry_id, growth_id))),
                )
            )
            framework_item = framework_coverage.get(entry.framework, FrameworkCoverage(entry.framework, "unsupported", (), ("no_coverage",), "forces_unknown"))
            registration_pattern = entry.registration.kind
            # Framework-level dynamic/reflection gaps do not taint a concrete
            # entry whose exact registration pattern was proven complete.
            pattern_proven = any(registration_pattern in pattern for pattern in framework_item.supported_patterns)
            if pattern_proven and registration_pattern != "dynamic_unresolved":
                coverage = CandidateCoverage(
                    entry.framework, "complete", tuple(sorted(set(framework_item.supported_patterns))), (), "none",
                    registration_pattern=registration_pattern, entry_id=entry.entry_id, growth_id=growth_id,
                )
            else:
                coverage = CandidateCoverage.from_framework(framework_item, registration_pattern=registration_pattern, entry_id=entry.entry_id, growth_id=growth_id)
            proof_gate = VerdictProofGate(
                entry_complete=coverage.status == "complete",
                ordinary_reachability=(
                    reachability.get(entry_id) is not None
                    and reachability[entry_id].status == "ordinary_attacker_reachable"
                ),
                growth_verified=result.status == "verified",
                flow_proven=bool(proven) and len(proven) == len(ordered),
                lifecycle_families_complete=all(
                    coverage_by_key.get(
                        (entry_id, growth_id, flow.path_id, family)
                    )
                    == "complete"
                    for flow in ordered
                    for family in ("guard", "bound", "release")
                ),
                candidate_relevant_gap_free=(
                    disposition_statuses[(entry_id, growth_id)] == "verified_relevant"
                ),
            )
            verdict = apply_positive_proof_gate(
                derive_verdict(assertions, coverage), proof_gate
            )
            certificate = build_lifecycle_certificate(
                entry, result, ordered, guard, bound, release,
                assertions, coverage, verdict,
                reachability=reachability.get(entry_id), repeatability=repeatability.get((entry_id, growth_id)), amplification=amplification.get((entry_id, growth_id)),
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
        certificates = [LifecycleCertificate(**{**record, "attacker_inputs": tuple(record["attacker_inputs"]), "path_ids": tuple(record["path_ids"]), "assertions": tuple(record["assertions"]), "reason_codes": tuple(record["reason_codes"]), "assumptions": tuple(record["assumptions"]), "coverage_gaps": tuple(record["coverage_gaps"]), "unresolved_facts": tuple(record["unresolved_facts"]), "suggested_follow_up_measurements": tuple(record["suggested_follow_up_measurements"])}) for record in cert_records]
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


def build_production_pipeline(values: Mapping[str, object], *, environ: Mapping[str, str] | None = None, secrets_path: Path | None = None, stage_executors: Mapping[str, Executor] | None = None, validate_database_fn: Callable[..., DatabaseInfo] | None = None, run_query_fn: Callable[..., QueryResult] | None = None, deepseek_client: object | None = None, deepseek_client_factory: Callable[[object], object] | None = None, source_excerpt_fn: Callable[[Path, str, str, int], SourceExcerpt] = extract_source_excerpt) -> ProductionPipeline:
    config_path = values.get("config")
    if config_path is not None and not isinstance(config_path, Path): raise AnalyzerError("CONFIG_INVALID_VALUE", "config must be a path.")
    if secrets_path is None:
        secrets_path = _DEFAULT_SECRETS_PATH
    env = os.environ if environ is None else environ
    if values.get("command") == "entries":
        env = {key: value for key, value in env.items() if key != "DEEPSEEK_API_KEY"}; values = dict(values); values["allow_remote_llm"] = False
    config = load_config(values, config_path, env, secrets_path=secrets_path); validate = validate_database_fn or globals()["validate_database"]; runner = run_query_fn or globals()["run_query"]
    validated_database: DatabaseInfo | None = None; validated_pack: dict[str, bytes] | None = None
    def current_database() -> DatabaseInfo:
        if validated_database is None: raise AnalyzerError("CODEQL_DATABASE_INVALID", "CodeQL database validation failed.")
        return validated_database
    def current_pack() -> Mapping[str, bytes]:
        if validated_pack is None: raise AnalyzerError("CODEQL_QUERY_PACK_INVALID", "The production query pack is unavailable.")
        return validated_pack
    if stage_executors is None:
        client_factory = deepseek_client_factory or DeepSeekClient
        executors: dict[str, Executor] = {"entries": make_entries_executor(config, run_query_fn=runner, database_info_fn=current_database, query_pack_snapshot_fn=current_pack), "growth": make_growth_executor(config, database_info_fn=current_database, query_pack_snapshot_fn=current_pack, run_query_fn=runner, deepseek_client=deepseek_client, deepseek_client_factory=client_factory, source_excerpt_fn=source_excerpt_fn), "flows": make_flows_executor(config, database_info_fn=current_database, query_pack_snapshot_fn=current_pack, run_query_fn=runner), "lifecycle": make_lifecycle_executor(config, database_info_fn=current_database, query_pack_snapshot_fn=current_pack, run_query_fn=runner), "conclude": make_conclude_executor(), "report": make_report_executor()}
    else:
        executors = dict(stage_executors)
        if set(executors) != set(STAGES): raise AnalyzerError("INTERNAL_STAGE_EXECUTORS_UNAVAILABLE", "Production stage executors are unavailable.", {"missing_stages": sorted(set(STAGES) - set(executors))})
    pipeline: Pipeline
    def preflight() -> None:
        nonlocal validated_database, validated_pack
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
        validated_database, validated_pack = database, snapshot; pipeline.query_pack_hash = pack_hash; pipeline.database_fingerprint = database.fingerprint
        # Bounded best-effort metadata only; query execution remains authoritative.
        codeql_version = "unavailable"
        try:
            completed = subprocess.run([config.codeql_binary, "version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5, check=False)
            if completed.returncode == 0:
                codeql_version = completed.stdout.strip().replace("\x00", " ")[:256] or "unavailable"
        except (OSError, subprocess.SubprocessError):
            pass
        pipeline.run_identity.update({"codeql_cli_version": codeql_version, "query_pack_hash": pack_hash, "database_fingerprint": database.fingerprint, "source_root": str(source_root)})
    if config.allow_partial_codeql and values.get("command") != "entries":
        raise AnalyzerError("CONFIG_INVALID_VALUE", "Partial CodeQL execution is restricted to exploratory entries runs.")
    analysis_mode = "exploratory_entries" if config.allow_partial_codeql else "formal"
    pipeline = Pipeline(config.output, executors, database_fingerprint="", query_pack_hash="", config_fingerprint=_digest({**_non_secret_config(config), "analysis_mode": analysis_mode, "query_failure_policy": "coverage_gap" if config.allow_partial_codeql else "fail_closed"}), model_fingerprint=_digest({"base_url": config.llm.base_url, "model": config.llm.model, "temperature": config.llm.temperature}), report_fingerprint=_digest({"renderer": "markdown-v1"}), implementation_versions=_IMPLEMENTATION_VERSIONS, resume=config.resume, preflight=preflight if stage_executors is None else None, run_identity={"analysis_mode": analysis_mode, "query_failure_policy": "coverage_gap" if config.allow_partial_codeql else "fail_closed", "codeql_binary": config.codeql_binary})
    # DeepSeekClient is constructed lazily by the Growth executor, so exposing
    # the complete graph here does not perform provider work during factory
    # construction or pipeline preflight.
    return ProductionPipeline(pipeline, config, frozenset(executors))


__all__ = ["ProductionPipeline", "build_production_pipeline", "make_entries_executor", "make_growth_executor", "make_flows_executor", "make_lifecycle_executor", "make_conclude_executor", "make_report_executor", "run_query", "validate_database"]
