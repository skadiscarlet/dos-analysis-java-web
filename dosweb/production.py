"""Concrete, network-free-capable production pipeline adapters."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, cast

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.metadata import resolve_upstream_artifact
from dosweb.artifacts.schemas import validate_records
from dosweb.codeql.database import DatabaseInfo, validate_database as _validate_database
from dosweb.codeql.decoder import DecodeSource, decode_bqrs_json
from dosweb.codeql.runner import QueryResult, run_query as _run_query
from dosweb.config import AnalyzerConfig, load_config
from dosweb.conclude.assertions import evaluate_assertion_1, evaluate_assertion_2
from dosweb.conclude.verdicts import CandidateCoverage, derive_verdict
from dosweb.entries import EntryFact, FrameworkCoverage
from dosweb.entries.models import load_entry_facts
from dosweb.entries.normalize import normalize_entry_rows, normalize_framework_coverage
from dosweb.errors import AnalyzerError
from dosweb.flows.models import FlowProof, normalize_flow_rows
from dosweb.flows.verify import VerifiedFlow, verify_flow
from dosweb.growth.contracts import validate_contract_static_evidence
from dosweb.growth.evidence import adapt_growth_static_evidence
from dosweb.growth.excerpts import extract_source_excerpt
from dosweb.growth.models import BoundedSlice, BoundedSlicePayload, GrowthContract
from dosweb.growth.slices import DemandInput, GrowthCandidate, SourceLocation, normalize_growth_rows
from dosweb.growth.verify import VerificationCheck, VerifiedGrowthResult, verify_growth_contract
from dosweb.lifecycle.bounds import BoundCandidate, BoundDecision, evaluate_bound
from dosweb.lifecycle.certificates import LifecycleCertificate, StaticFinding, build_lifecycle_certificate
from dosweb.lifecycle.guards import DecisionCheck, GuardCandidate, GuardDecision, ModeledConfiguration, evaluate_guard
from dosweb.lifecycle.releases import ReleaseCandidate, ReleaseDecision, evaluate_synchronous_release
from dosweb.llm.deepseek import DeepSeekClient
from dosweb.pipeline import Executor, Pipeline, STAGES, StageContext, StageOutput
from dosweb.report.markdown import render_report
from dosweb.report.summary import build_summary

_IMPLEMENTATION_VERSIONS: Final = {stage: "production-v2" for stage in STAGES}
_QUERY_PACK_DIR: Final = Path(__file__).resolve().parent / "codeql" / "pack"
_ENTRY_QUERY_DIR: Final = _QUERY_PACK_DIR / "dosweb" / "Entries"
_ENTRY_QUERIES: Final = (
    "SpringMvcEntries.ql", "ServletEntries.ql", "NettyEntries.ql", "MqttEntries.ql",
    "JaxRsEntries.ql", "GrpcEntries.ql",
)
_QUERY_FAMILIES: Final[dict[str, tuple[str, ...]]] = {
    "growth": ("InputMaterialization.ql", "DirectAllocation.ql", "ContainerGrowth.ql", "AsyncWorkGrowth.ql"),
    "flows": ("EntryToGrowth.ql",),
    "lifecycle": ("GuardCandidates.ql", "BoundCandidates.ql", "SynchronousReleaseCandidates.ql"),
}
_QUERY_DIRS: Final[dict[str, str]] = {"growth": "Growth", "flows": "Flows", "lifecycle": "Lifecycle"}
_MAX_DECODED_BYTES: Final = 64 * 1024 * 1024
_MAX_QUERY_INPUT_BYTES: Final = 2 * 1024 * 1024
_MAX_ENTRY_ROWS: Final = 4096
_CODEQL_TIMEOUT_SECONDS: Final = 300

validate_database = _validate_database
run_query = _run_query


def _non_secret_config(config: AnalyzerConfig) -> dict[str, object]:
    return {
        "codeql_binary": config.codeql_binary, "database": str(config.database),
        "llm": {"allow_remote_llm": config.llm.allow_remote_llm, "analysis_source_root": str(config.llm.analysis_source_root) if config.llm.analysis_source_root else None, "base_url": config.llm.base_url,
                "cache_dir": str(config.llm.cache_dir), "max_retries": config.llm.max_retries,
                "model": config.llm.model, "public_source_url": config.llm.public_source_url,
                "source_checkout": str(config.llm.source_checkout) if config.llm.source_checkout else None,
                "source_commit_sha": config.llm.source_commit_sha, "temperature": config.llm.temperature,
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
            elif stage == "flows":
                family = "flow"
            else:
                lowered = query.stem.lower()
                family = "guard" if "guard" in lowered else "bound" if "bound" in lowered else "release"
            decoded = decode_bqrs_json(family, payload, DecodeSource(database.source_root, result.query_sha256))
            if len(rows) + len(decoded) > _MAX_ENTRY_ROWS:
                raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL output exceeds the aggregate row limit.")
            rows.extend(decoded)
    return rows


def make_entries_executor(config: AnalyzerConfig, *, validate_database_fn: Callable[..., DatabaseInfo] | None = None, run_query_fn: Callable[..., QueryResult] | None = None, database_info_fn: Callable[[], DatabaseInfo] | None = None, query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]] | None = None, query_dir: Path = _ENTRY_QUERY_DIR) -> Executor:
    validate = validate_database_fn or globals()["validate_database"]
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        database = database_info_fn() if database_info_fn else validate(config.database)
        if not isinstance(database, DatabaseInfo):
            raise AnalyzerError("CODEQL_DATABASE_INVALID", "CodeQL database validation failed.")
        with tempfile.TemporaryDirectory(prefix="dosweb-entry-queries-") as temporary:
            root = Path(temporary) / "pack"
            if query_pack_snapshot_fn:
                effective = _materialize_query_pack(root, query_pack_snapshot_fn()) / "dosweb" / "Entries"
            else:
                effective = query_dir
            rows: list[dict[str, object]] = []
            results = Path(temporary) / "results"; results.mkdir()
            for name in _ENTRY_QUERIES:
                result = runner(effective / name, database, results, codeql_binary=config.codeql_binary, timeout_seconds=_CODEQL_TIMEOUT_SECONDS)
                if not isinstance(result, QueryResult):
                    raise AnalyzerError("CODEQL_QUERY_FAILED", "The entry query runner returned an invalid result.")
                rows.extend(decode_bqrs_json("entries", _bounded_json_file(Path(result.decoded_path)), DecodeSource(database.source_root, result.query_sha256)))
                if len(rows) > _MAX_ENTRY_ROWS:
                    raise AnalyzerError("CODEQL_RESULT_INVALID", "Decoded CodeQL entry output exceeds the aggregate row limit.")
        entries = normalize_entry_rows(rows); coverage = normalize_framework_coverage(rows)
        validate_records("entry_facts", entries)
        return StageOutput({"entry_facts.jsonl": entries, "coverage.json": canonical_json(coverage) + b"\n"}, {"database_fingerprint": database.fingerprint, "query_count": len(_ENTRY_QUERIES)})
    return execute


def _upstream(context: StageContext, stage: str, artifact: str) -> Path:
    return resolve_upstream_artifact(context.output_root, context.upstream, stage, artifact, schema_version="2.0")


def _records(context: StageContext, stage: str, artifact: str, schema: str) -> list[dict[str, object]]:
    path = _upstream(context, stage, artifact)
    records = read_jsonl_strict(path, schema)
    validate_records(schema, records)
    return records


def _strict_records(context: StageContext, stage: str, artifact: str) -> list[dict[str, object]]:
    """Read a strict JSONL artifact whose richer model schema is self-validating."""
    return read_jsonl_strict(_upstream(context, stage, artifact), artifact.removesuffix(".jsonl"))


def _coverage(context: StageContext) -> tuple[FrameworkCoverage, ...]:
    path = _upstream(context, "entries", "coverage.json")
    value = json.loads(_bounded_regular_file(path, _MAX_DECODED_BYTES).decode("utf-8"))
    if not isinstance(value, list):
        raise AnalyzerError("ARTIFACT_INVALID_JSON", "Coverage artifact must be a list.")
    result = tuple(FrameworkCoverage(item["framework"], item["status"], tuple(item["supported_patterns"]), tuple(item["unsupported_patterns"]), item["effect_on_verdict"]) for item in value if isinstance(item, Mapping))
    if len(result) != len(value):
        raise AnalyzerError("ARTIFACT_INVALID_JSON", "Coverage artifact is malformed.")
    return result


def _load_entries(context: StageContext) -> dict[str, EntryFact]:
    path = _upstream(context, "entries", "entry_facts.jsonl")
    return {entry.entry_id: entry for entry in load_entry_facts(path)}


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
    matches = tuple(
        entry for entry in entries.values()
        if entry.handler.file == candidate.site.file and entry.handler.start_line <= candidate.site.start_line
    )
    if not matches:
        all_entries = tuple(sorted(entries.values(), key=lambda entry: entry.entry_id))
        if all_entries and len({_entry_semantic_key(entry) for entry in all_entries}) == 1:
            return _canonical_entry(all_entries, candidate)
        raise AnalyzerError(
            "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS",
            "Growth candidate must map to exactly one normalized entry.",
            {"growth_id": candidate.growth_id, "match_count": 0},
        )
    nearest_line = max(entry.handler.start_line for entry in matches)
    narrowed = tuple(sorted(
        (entry for entry in matches if entry.handler.start_line == nearest_line),
        key=lambda entry: entry.entry_id,
    ))
    return _canonical_entry(narrowed, candidate)


def _slice_for(
    config: AnalyzerConfig,
    entry: EntryFact,
    candidate: GrowthCandidate,
    source_excerpt_fn: Callable[[Path, str, str, int], SourceExcerpt] = extract_source_excerpt,
) -> BoundedSlice:
    checkout = config.llm.source_checkout
    commit = config.llm.source_commit_sha
    if checkout is None or commit is None:
        raise AnalyzerError("CONFIG_PUBLIC_SOURCE_UNVERIFIED", "Pinned source checkout is required for Growth classification.")
    locations = {(candidate.site.file, candidate.site.start_line), (entry.registration.file, entry.registration.start_line)}
    excerpts = tuple(
        source_excerpt_fn(checkout, commit, path, line)
        for path, line in sorted(locations)
    )
    evidence = adapt_growth_static_evidence(entry, candidate, excerpts)
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


def make_growth_executor(config: AnalyzerConfig, *, database_info_fn: Callable[[], DatabaseInfo], query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]], run_query_fn: Callable[..., QueryResult] | None = None, deepseek_client: object | None = None, deepseek_client_factory: Callable[[object], object] = DeepSeekClient, source_excerpt_fn: Callable[[Path, str, str, int], SourceExcerpt] = extract_source_excerpt) -> Executor:
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        database = database_info_fn()
        with tempfile.TemporaryDirectory(prefix="dosweb-pack-") as temporary:
            pack = _materialize_query_pack(Path(temporary), query_pack_snapshot_fn())
            rows = _run_codeql_family(config, database, "growth", pack, runner)
        candidate_records = normalize_growth_rows(rows); validate_records("growth_candidates", candidate_records)
        entries = _load_entries(context); classifier = deepseek_client or deepseek_client_factory(config.llm)
        contracts: list[dict[str, object]] = []; verified: list[dict[str, object]] = []
        for record in candidate_records:
            candidate = _candidate_from_record(record)
            entry = _entry_for_candidate(entries, candidate)
            bounded = _slice_for(config, entry, candidate, source_excerpt_fn)
            classify = getattr(classifier, "classify_growth", None)
            if not callable(classify):
                raise AnalyzerError("INTERNAL_STAGE_EXECUTORS_UNAVAILABLE", "Growth classifier is unavailable.")
            contract = classify(bounded)
            if not isinstance(contract, GrowthContract):
                raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Growth classifier returned an invalid contract.")
            contract = validate_contract_static_evidence(contract, frozenset(fact.fact_id for fact in bounded.payload.static_facts))
            contract_record = {"growth_contract_id": stable_identifier("contract", {"growth_id": candidate.growth_id, **contract.to_dict()}), "growth_id": candidate.growth_id, **contract.to_dict()}
            contracts.append(contract_record)
            result = verify_growth_contract(candidate, bounded, contract, {fact.fact_id: fact for fact in bounded.payload.static_facts})
            verified.append(result.to_dict())
        validate_records("growth_contracts", contracts); validate_records("verified_growth", verified)
        return StageOutput({"growth_candidates.jsonl": candidate_records, "growth_contracts.jsonl": contracts, "verified_growth.jsonl": verified}, {"candidate_count": len(candidate_records)})
    return execute


def make_flows_executor(config: AnalyzerConfig, *, database_info_fn: Callable[[], DatabaseInfo], query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]], run_query_fn: Callable[..., QueryResult] | None = None) -> Executor:
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        entries = _load_entries(context)
        candidates = _load_verified_growth(context)
        with tempfile.TemporaryDirectory(prefix="dosweb-pack-") as temporary:
            pack = _materialize_query_pack(Path(temporary), query_pack_snapshot_fn())
            rows = _run_codeql_family(config, database_info_fn(), "flows", pack, runner)
        proofs = normalize_flow_rows(rows, entries, candidates); validate_records("flow_proofs", proofs)
        return StageOutput({"flow_proofs.jsonl": proofs}, {"flow_count": len(proofs)})
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
    return {
        "status": decision.status,
        "reason_codes": list(decision.reason_codes),
        "checks": [
            {"name": check.name, "passed": check.passed, "reason_code": check.reason_code, "evidence_ids": list(check.evidence_ids)}
            for check in decision.checks
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


def make_lifecycle_executor(config: AnalyzerConfig, *, database_info_fn: Callable[[], DatabaseInfo], query_pack_snapshot_fn: Callable[[], Mapping[str, bytes]], run_query_fn: Callable[..., QueryResult] | None = None) -> Executor:
    runner = run_query_fn or globals()["run_query"]
    def execute(context: StageContext) -> StageOutput:
        with tempfile.TemporaryDirectory(prefix="dosweb-pack-") as temporary:
            pack = _materialize_query_pack(Path(temporary), query_pack_snapshot_fn())
            rows = _run_codeql_family(config, database_info_fn(), "lifecycle", pack, runner)
        # Re-query family rows by decoder provenance, retaining strict normalization.
        guards_raw, bounds_raw, releases_raw = [], [], []
        for row in rows:
            query = row.get("query_name", "")
            if query == "guard": guards_raw.append(row)
            elif query == "bound": bounds_raw.append(row)
            elif query == "release": releases_raw.append(row)
            else: raise AnalyzerError("CODEQL_RESULT_INVALID", "Lifecycle query family is unknown.")
        def normalized(raw: list[Mapping[str, object]], kind: str) -> list[dict[str, object]]:
            # Candidate schemas intentionally expose only the stable public subset.
            output = []
            for r in raw:
                site_key = {"file": r["site_file"], "start_line": r["site_start_line"]}
                if kind == "guard":
                    candidate = GuardCandidate.create(site_file=r["site_file"], site_start_line=r["site_start_line"], kind=r["guard_kind"], resource_dimension=r["resource_dimension"], scope=r["scope"], behavior=r["behavior"], dominates_growth=r["dominates_growth"], reject_path_reaches_growth=r["reject_path_reaches_growth"], configuration_key=r["configuration_key"], configuration_value=r["configuration_value"], representation=r["representation"], phase=r["phase"], covers_materialization=r["covers_materialization"], authorization_only=r["authorization_only"], evidence=[r["evidence"]], coverage_status=r["coverage_status"])
                    output.append(candidate.to_dict())
                elif kind == "bound":
                    candidate = BoundCandidate.create(site_file=r["site_file"], site_start_line=r["site_start_line"], kind=r["bound_kind"], resource_dimension=r["resource_dimension"], scope=r["scope"], behavior=r["behavior"], receiver=r["receiver"], field_path=r["field_path"], result_checked=r["result_checked"], configuration_key=r["configuration_key"], configuration_value=r["configuration_value"], phase=r["phase"], covers_flow=r["covers_flow"], request_encoding=r["request_encoding"], queue_resource=r["queue_resource"], product_bound=r["product_bound"], evidence=[r["evidence"]], coverage_status=r["coverage_status"])
                    output.append(candidate.to_dict())
                else:
                    candidate = ReleaseCandidate.create(site_file=r["site_file"], site_start_line=r["site_start_line"], kind=r["release_kind"], resource_dimension=r["resource_dimension"], scope=r["scope"], receiver=r["receiver"], key_identity=r["key_identity"], synchronous=r["synchronous"], normal_path=r["normal_path"], exceptional_path=r["exceptional_path"], actual_reduction=r["actual_reduction"], after_growth=r["after_growth"], transfer_only=r["transfer_only"], async_kind=r["async_kind"], evidence=[r["evidence"]], coverage_status=r["coverage_status"])
                    output.append(candidate.to_dict())
            return output
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
        lifecycle_records = []
        for flow in flows:
            entry, result = entries[flow.entry_id], growth[flow.growth_id]
            if not flow.satisfies_premise or result.status != "verified":
                reasons = tuple(sorted(set((*flow.reason_codes, *result.reason_codes, "LIFECYCLE_PREMISE_UNRESOLVED"))))
                guard = GuardDecision("unknown", reasons, (), (), reasons, ())
                bound = BoundDecision("unknown", reasons, (), (), reasons, ())
                release = ReleaseDecision("unknown", "unknown", reasons, (), (), reasons, ())
            else:
                guard = evaluate_guard(entry, result, flow, guards, ModeledConfiguration(()))
                bound = evaluate_bound(entry, result, flow, bounds, ModeledConfiguration(()))
                release = evaluate_synchronous_release(entry, result, flow, releases)
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
        validate_records("lifecycle_results", lifecycle_records)
        return StageOutput({"guard_candidates.jsonl": guard_records, "bound_candidates.jsonl": bound_records, "release_candidates.jsonl": release_records, "lifecycle_results.jsonl": lifecycle_records}, {"flow_count": len(flows)})
    return execute


def make_conclude_executor() -> Executor:
    def execute(context: StageContext) -> StageOutput:
        entries = _load_entries(context)
        growth = _load_verified_growth(context)
        flows = [verify_flow(FlowProof.from_dict(record), entries, growth) for record in _records(context, "flows", "flow_proofs.jsonl", "flow_proofs")]
        lifecycle = {record["path_id"]: record for record in _records(context, "lifecycle", "lifecycle_results.jsonl", "lifecycle_results")}
        guards = [GuardCandidate.from_dict(record) for record in _strict_records(context, "lifecycle", "guard_candidates.jsonl")]
        bounds = [BoundCandidate.from_dict(record) for record in _strict_records(context, "lifecycle", "bound_candidates.jsonl")]
        releases = [ReleaseCandidate.from_dict(record) for record in _strict_records(context, "lifecycle", "release_candidates.jsonl")]
        framework_coverage = {item.framework: item for item in _coverage(context)}
        certificates: list[dict[str, object]] = []
        findings: list[dict[str, object]] = []
        grouped: dict[tuple[str, str], list[VerifiedFlow]] = {}
        for flow in flows:
            if flow.path_id not in lifecycle:
                raise AnalyzerError("ARTIFACT_UPSTREAM_INVALID", "Lifecycle result is missing a flow path.")
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
                    evaluate_assertion_1(result, flow, guard, bound),
                    evaluate_assertion_2(result, flow, bound, release),
                )
            )
            coverage = CandidateCoverage.from_framework(framework_coverage.get(entry.framework, FrameworkCoverage(entry.framework, "unsupported", (), ("no_coverage",), "forces_unknown")), registration_pattern=entry.registration.kind)
            verdict = derive_verdict(assertions, coverage)
            certificate = build_lifecycle_certificate(
                entry, result, ordered, guard, bound, release,
                assertions, coverage, verdict,
            )
            finding = StaticFinding.from_certificate(certificate)
            certificates.append(certificate.to_dict()); findings.append(finding.to_dict())
        validate_records("lifecycle_certificates", certificates); validate_records("static_findings", findings)
        return StageOutput({"lifecycle_certificates.jsonl": certificates, "static_findings.jsonl": findings}, {"finding_count": len(findings), "unresolved_path_count": sum(not flow.satisfies_premise for flow in flows)})
    return execute


def make_report_executor() -> Executor:
    def execute(context: StageContext) -> StageOutput:
        cert_records = _records(context, "conclude", "lifecycle_certificates.jsonl", "lifecycle_certificates")
        finding_records = _records(context, "conclude", "static_findings.jsonl", "static_findings")
        certificates = [LifecycleCertificate(**{**record, "attacker_inputs": tuple(record["attacker_inputs"]), "path_ids": tuple(record["path_ids"]), "assertions": tuple(record["assertions"]), "reason_codes": tuple(record["reason_codes"]), "assumptions": tuple(record["assumptions"]), "coverage_gaps": tuple(record["coverage_gaps"]), "unresolved_facts": tuple(record["unresolved_facts"]), "suggested_follow_up_measurements": tuple(record["suggested_follow_up_measurements"])}) for record in cert_records]
        findings = [StaticFinding.from_dict(record) for record in finding_records]
        summary = build_summary(findings, _coverage(context))
        return StageOutput({"summary.json": canonical_json(summary) + b"\n", "report.md": render_report(summary, findings, certificates)})
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


def build_production_pipeline(values: Mapping[str, object], *, environ: Mapping[str, str] | None = None, stage_executors: Mapping[str, Executor] | None = None, validate_database_fn: Callable[..., DatabaseInfo] | None = None, run_query_fn: Callable[..., QueryResult] | None = None, deepseek_client: object | None = None, deepseek_client_factory: Callable[[object], object] | None = None, source_excerpt_fn: Callable[[Path, str, str, int], SourceExcerpt] = extract_source_excerpt) -> ProductionPipeline:
    config_path = values.get("config")
    if config_path is not None and not isinstance(config_path, Path): raise AnalyzerError("CONFIG_INVALID_VALUE", "config must be a path.")
    env = os.environ if environ is None else environ
    if values.get("command") == "entries":
        env = {key: value for key, value in env.items() if key != "DEEPSEEK_API_KEY"}; values = dict(values); values["allow_remote_llm"] = False
    config = load_config(values, config_path, env); validate = validate_database_fn or globals()["validate_database"]; runner = run_query_fn or globals()["run_query"]
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
    pipeline = Pipeline(config.output, executors, database_fingerprint="", query_pack_hash="", config_fingerprint=_digest(_non_secret_config(config)), model_fingerprint=_digest({"base_url": config.llm.base_url, "model": config.llm.model, "temperature": config.llm.temperature}), report_fingerprint=_digest({"renderer": "markdown-v1"}), implementation_versions=_IMPLEMENTATION_VERSIONS, resume=config.resume, preflight=preflight if stage_executors is None else None)
    # DeepSeekClient is constructed lazily by the Growth executor, so exposing
    # the complete graph here does not perform provider work during factory
    # construction or pipeline preflight.
    return ProductionPipeline(pipeline, config, frozenset(executors))


__all__ = ["ProductionPipeline", "build_production_pipeline", "make_entries_executor", "make_growth_executor", "make_flows_executor", "make_lifecycle_executor", "make_conclude_executor", "make_report_executor", "run_query", "validate_database"]
