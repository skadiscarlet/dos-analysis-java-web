from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time
from typing import Final
import zipfile

from dosweb.artifacts.identifiers import canonical_json, file_sha256, stable_identifier
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database
from dosweb.codeql.database import DatabaseInfo
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.adapters import (
    AnalysisUnit,
    ExtractedFacts,
    adapt_codeql_rows,
    extracted_from_dict,
    extracted_to_dict,
    validate_extracted,
)
from dosweb.resource_lifecycle.invariants import (
    candidate_result_scope,
    check_invariants,
    queue_result_scope,
)
from dosweb.resource_lifecycle.events import expand_dispatch
from dosweb.resource_lifecycle.io import (
    atomic_write_json,
    atomic_write_text,
    budget_from_dict,
    ensure_output_directory,
    load_json_regular,
    load_json_regular_with_sha256,
    load_regular_bytes_with_sha256,
    load_text_regular,
    program_from_dict,
    state_to_dict,
)
from dosweb.resource_lifecycle.models import AnalysisBudget, AnalysisResult, SCHEMA_VERSION
from dosweb.resource_lifecycle.solver import apply_effect, initial_state, solve
from dosweb.resource_lifecycle.summaries import (
    AppliedSummaries,
    SummaryRecording,
    apply_recorded_summaries,
    recording_from_dict,
    recording_to_dict,
)


TOOL_VERSION: Final = "resource-lifecycle-v1.1"
_SUPPORTED_INPUT_SCHEMA_VERSIONS: Final = frozenset({"1.0", SCHEMA_VERSION})
_QUERY = Path(__file__).resolve().parents[1] / "codeql/pack/dosweb/ResourceLifecycle/ResourceLifecycleFacts.ql"
_MAX_SOURCE_FILES: Final = 200_000
_MAX_SOURCE_BYTES: Final = 2 * 1024 * 1024 * 1024
_MAX_SUMMARY_BYTES: Final = 1024 * 1024
_ANALYZE_COMMON_ARTIFACTS: Final = (
    "facts.snapshot.json",
    "run-manifest.json",
    "lifecycle-results.json",
    "evidence.json",
    "summary.md",
)
_ANALYZE_REPLAY_ARTIFACTS: Final = (
    "llm-recording.private.json",
    "llm-summaries.json",
)
_ANALYZE_STALE_REPLAY_ARTIFACT: Final = "replay.json"
_RUN_LOCK_NAME: Final = ".resource-lifecycle.lock"
_RUN_LOCK_TIMEOUT_SECONDS: Final = 5.0
_RUN_LOCK_POLL_SECONDS: Final = 0.01


def _required_path(values: Mapping[str, object], name: str) -> Path:
    value = values.get(name)
    if not isinstance(value, Path):
        raise AnalyzerError("CONFIG_INVALID_VALUE", f"--{name.replace('_', '-')} is required for this command.")
    return value


def _manifest_relative(manifest_path: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label} must be a safe relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must be a safe relative path")
    base = manifest_path.parent.resolve(strict=True)
    candidate = (base / relative).resolve(strict=True)
    if candidate != base and base not in candidate.parents:
        raise ValueError(f"{label} escapes the manifest directory")
    return candidate


def _java_source_snapshot(source_root: Path) -> tuple[dict[str, str], str]:
    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir() or source_root.is_symlink():
        raise ValueError("Java source snapshot root is invalid")
    current: dict[str, str] = {}
    current_bytes = 0
    for path in source_root.rglob("*.java"):
        if len(current) >= _MAX_SOURCE_FILES:
            raise ValueError("CodeQL source snapshot exceeds file limit")
        resolved = path.resolve(strict=True)
        if source_root not in resolved.parents or path.is_symlink():
            raise ValueError("CodeQL source snapshot contains an unsafe path")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("CodeQL source snapshot contains a non-regular file")
        current_bytes += info.st_size
        if current_bytes > _MAX_SOURCE_BYTES:
            raise ValueError("Java source snapshot exceeds byte limit")
        current[path.relative_to(source_root).as_posix()] = file_sha256(path)
    if not current:
        raise ValueError("Java source snapshot is empty")
    return current, hashlib.sha256(canonical_json(current)).hexdigest()


def _verify_database_source_snapshot(database: DatabaseInfo) -> str:
    source_root = database.source_root.resolve(strict=True)
    current, source_snapshot_sha256 = _java_source_snapshot(source_root)

    archive_path = database.path / "src.zip"
    archive_info = archive_path.lstat()
    if not stat.S_ISREG(archive_info.st_mode) or archive_path.is_symlink():
        raise ValueError("CodeQL source snapshot archive is invalid")
    prefix = source_root.as_posix().lstrip("/") + "/"
    archived: dict[str, str] = {}
    archived_bytes = 0
    with zipfile.ZipFile(archive_path) as archive:
        java_entries = [item for item in archive.infolist() if not item.is_dir() and item.filename.endswith(".java")]
        if len(java_entries) > _MAX_SOURCE_FILES:
            raise ValueError("CodeQL source snapshot archive exceeds file limit")
        for item in java_entries:
            name = item.filename
            if "\\" in name or name.startswith("/") or ".." in Path(name).parts or not name.startswith(prefix):
                raise ValueError("CodeQL source snapshot archive path is invalid")
            relative = name[len(prefix):]
            archived_bytes += item.file_size
            if archived_bytes > _MAX_SOURCE_BYTES or relative in archived:
                raise ValueError("CodeQL source snapshot archive exceeds verification limits")
            digest = hashlib.sha256()
            read_bytes = 0
            with archive.open(item) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    read_bytes += len(chunk)
                    if read_bytes > item.file_size or archived_bytes - item.file_size + read_bytes > _MAX_SOURCE_BYTES:
                        raise ValueError("CodeQL source snapshot archive entry is invalid")
                    digest.update(chunk)
            if read_bytes != item.file_size:
                raise ValueError("CodeQL source snapshot archive entry is truncated")
            archived[relative] = digest.hexdigest()
    if current != archived:
        raise ValueError("CodeQL database source snapshot does not match the live source tree")
    return source_snapshot_sha256


def _manual_facts(manifest: Mapping[str, object], manifest_path: Path) -> ExtractedFacts:
    if set(manifest) != {"schema_version", "mode", "programs", "budget"}:
        raise ValueError("manual fixture manifest fields are invalid")
    programs = manifest.get("programs")
    if manifest.get("schema_version") not in _SUPPORTED_INPUT_SCHEMA_VERSIONS or not isinstance(programs, list):
        raise ValueError("manual fixture manifest schema is invalid")
    units: list[AnalysisUnit] = []
    for item in programs:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"unit_id", "program", "invariants", "executor_contracts"}
            or not isinstance(item["invariants"], list)
            or not isinstance(item["executor_contracts"], list)
        ):
            raise ValueError("manual fixture analysis unit is invalid")
        program = program_from_dict(item["program"])
        if any(
            effect.location.source_kind != "manual_fixture"
            for transition in program.transitions
            for effect in transition.effects
        ):
            raise ValueError("manual fixture effects must declare manual_fixture source")
        if any(
            point.location.source_kind != "manual_fixture"
            for point in program.program_points
        ):
            raise ValueError(
                "manual fixture program points must declare manual_fixture source"
            )
        if any(
            effect.location.source_kind != "manual_fixture"
            for transition in program.transitions
            for effect in transition.population_effects
        ):
            raise ValueError(
                "manual fixture population effects must declare manual_fixture source"
            )
        from dosweb.resource_lifecycle.adapters import _executor_contract_from_dict, _invariant_from_dict

        executor_contracts = tuple(
            _executor_contract_from_dict(value) for value in item["executor_contracts"]
        )
        if any(
            contract.source_kind not in {"manual_fixture", "trusted_contract"}
            for contract in executor_contracts
        ):
            raise ValueError("manual fixture executor contract source is invalid")

        units.append(
            AnalysisUnit(
                str(item["unit_id"]),
                program,
                tuple(_invariant_from_dict(value) for value in item["invariants"]),
                executor_contracts,
            )
        )
    budget = budget_from_dict(manifest["budget"])
    return ExtractedFacts(
        "manual_fixture",
        file_sha256(manifest_path),
        "manual-fixture-import-v1",
        budget,
        tuple(units),
        (),
        {"units": len(units), "facts": 0, "partial_or_unsupported": 0, "end_to_end_mode": "manual_ir"},
    )


def _static_json_facts(manifest: Mapping[str, object], manifest_path: Path) -> ExtractedFacts:
    if set(manifest) != {"schema_version", "mode", "rows", "source_root", "query_sha256", "entry_methods", "budget"}:
        raise ValueError("static fact manifest fields are invalid")
    if manifest.get("schema_version") not in _SUPPORTED_INPUT_SCHEMA_VERSIONS or manifest.get("mode") != "static_verified_json":
        raise ValueError("static fact manifest schema is invalid")
    rows_path = _manifest_relative(manifest_path, manifest["rows"], "rows")
    source_root = _manifest_relative(manifest_path, manifest["source_root"], "source_root")
    _source_files, source_snapshot_sha256 = _java_source_snapshot(source_root)
    rows = load_json_regular(rows_path)
    if not isinstance(rows, list) or any(not isinstance(item, Mapping) for item in rows):
        raise ValueError("static fact rows are invalid")
    entry_methods = manifest["entry_methods"]
    if not isinstance(entry_methods, list):
        raise ValueError("static fact entry_methods are invalid")
    extracted = adapt_codeql_rows(
        rows,
        source_root=source_root,
        query_sha256=str(manifest["query_sha256"]),
        entry_methods=entry_methods,
    )
    if _java_source_snapshot(source_root)[1] != source_snapshot_sha256:
        raise ValueError("Java source snapshot changed during static fact import")
    return ExtractedFacts(
        extracted.source_kind,
        extracted.snapshot_sha256,
        extracted.extractor_version,
        budget_from_dict(manifest["budget"]),
        extracted.units,
        extracted.facts,
        {
            **extracted.coverage,
            "end_to_end_mode": "imported_static_facts",
            "source_snapshot_sha256": source_snapshot_sha256,
        },
    )


def _codeql_facts(manifest: Mapping[str, object], values: Mapping[str, object], output: Path) -> ExtractedFacts:
    if set(manifest) != {"schema_version", "mode", "database", "entry_methods", "budget"}:
        raise ValueError("CodeQL manifest fields are invalid")
    if manifest.get("schema_version") not in _SUPPORTED_INPUT_SCHEMA_VERSIONS or manifest.get("mode") != "codeql_database":
        raise ValueError("CodeQL manifest schema is invalid")
    entry_methods = manifest["entry_methods"]
    if not isinstance(entry_methods, list):
        raise ValueError("CodeQL manifest entry_methods are invalid")
    database = validate_database(Path(str(manifest["database"])))
    source_snapshot_sha256 = _verify_database_source_snapshot(database)
    result = run_query(
        _QUERY,
        database,
        output / "codeql",
        codeql_binary=str(values.get("codeql_binary") or "codeql"),
    )
    payload = load_json_regular(result.decoded_path, max_bytes=64 * 1024 * 1024)
    if not isinstance(payload, Mapping):
        raise ValueError("CodeQL decoded result is invalid")
    rows = decode_bqrs_json("resource_lifecycle", payload, DecodeSource(database.source_root, result.query_sha256))
    extracted = adapt_codeql_rows(
        rows,
        source_root=database.source_root,
        query_sha256=result.query_sha256,
        entry_methods=entry_methods,
    )
    if _verify_database_source_snapshot(database) != source_snapshot_sha256:
        raise ValueError("CodeQL source snapshot changed during extraction")
    return ExtractedFacts(
        extracted.source_kind,
        extracted.snapshot_sha256,
        extracted.extractor_version,
        budget_from_dict(manifest["budget"]),
        extracted.units,
        extracted.facts,
        {**extracted.coverage, "source_snapshot_sha256": source_snapshot_sha256},
    )


def resource_extract(values: Mapping[str, object]) -> dict[str, object]:
    manifest_path = _required_path(values, "manifest")
    output = ensure_output_directory(_required_path(values, "out"))
    payload = load_json_regular(manifest_path)
    if not isinstance(payload, Mapping):
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle manifest must be an object.")
    try:
        mode = payload.get("mode")
        if mode == "manual_fixture":
            extracted = _manual_facts(payload, manifest_path)
        elif mode == "static_verified_json":
            extracted = _static_json_facts(payload, manifest_path)
        elif mode == "codeql_database":
            extracted = _codeql_facts(payload, values, output)
        else:
            raise ValueError("manifest mode is unsupported")
    except AnalyzerError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle manifest could not be adapted.") from exc
    artifact = extracted_to_dict(extracted)
    atomic_write_json(output / "facts.json", artifact)
    atomic_write_json(output / "coverage.json", dict(extracted.coverage))
    return artifact


def _async_stages(unit: AnalysisUnit, analysis: AnalysisResult) -> list[dict[str, object]]:
    event_states = analysis.event_states
    contracts = {contract.contract_id: contract for contract in unit.executor_contracts}
    stages: list[dict[str, object]] = []
    for transition in sorted(unit.program.transitions, key=lambda item: item.transition_id):
        if not any(effect.kind == "dispatch" for effect in transition.effects):
            continue
        source_state = event_states.get(transition.source_event_id)
        if source_state is None:
            source_state = replace(
                initial_state(unit.program),
                unknown_reasons=(f"dispatch_source_state_missing:{transition.transition_id}",),
            )
        replay_state = source_state
        prefix_rule_ids: list[str] = []
        prefix_evidence_ids: set[str] = set()
        prefix_rule_dependencies: set[tuple[str, str]] = set()
        for index, effect in enumerate(transition.effects):
            if effect.kind != "dispatch":
                applied = apply_effect(replay_state, effect)
                replay_state = applied.state
                prefix_rule_ids.extend(applied.rule_ids)
                prefix_evidence_ids.update(applied.evidence_ids)
                prefix_rule_dependencies.update(
                    (rule_id, evidence_id)
                    for rule_id in applied.rule_ids
                    for evidence_id in applied.evidence_ids
                )
                continue
            contract = contracts.get(effect.contract_id or "")
            trusted = contract is not None and contract.source_kind in {
                "static_verified",
                "trusted_contract",
                "manual_fixture",
            }
            expansion = expand_dispatch(replay_state, effect, contract if trusted else None)
            stage_identity = {
                "unit_id": unit.unit_id,
                "transition_id": transition.transition_id,
                "effect_index": index,
                "dispatch_effect_id": effect.effect_id,
            }
            dispatch_rule_dependencies = {
                (rule_id, evidence_id)
                for rule_id in expansion.rule_ids
                for evidence_id in expansion.evidence_ids
            }
            rule_ids = tuple(dict.fromkeys((*prefix_rule_ids, *expansion.rule_ids)))
            rule_dependencies = prefix_rule_dependencies.union(
                dispatch_rule_dependencies
            )
            stages.append(
                {
                    "stage_id": stable_identifier("async-stage", stage_identity),
                    "transition_id": transition.transition_id,
                    "effect_index": index,
                    "dispatch_effect_id": effect.effect_id,
                    "source_event_id": transition.source_event_id,
                    "target_event_id": effect.target_event_id,
                    "contract_id": effect.contract_id,
                    "contract_source_kind": contract.source_kind if contract is not None else None,
                    "contract_status": (
                        "trusted" if trusted else "untrusted" if contract is not None else "missing"
                    ),
                    "prefix_effect_ids": [item.effect_id for item in transition.effects[:index]],
                    "submitted": state_to_dict(expansion.submitted),
                    "started": state_to_dict(expansion.started),
                    "completed": state_to_dict(expansion.completed),
                    "rejected": state_to_dict(expansion.rejected),
                    "cancelled": state_to_dict(expansion.cancelled),
                    "rule_ids": list(rule_ids),
                    "prefix_rule_ids": list(dict.fromkeys(prefix_rule_ids)),
                    "rule_dependencies": [
                        list(item) for item in sorted(rule_dependencies)
                    ],
                    "evidence_ids": sorted(prefix_evidence_ids.union(expansion.evidence_ids)),
                }
            )
            applied_dispatch = apply_effect(replay_state, effect)
            replay_state = applied_dispatch.state
            prefix_rule_ids.extend(applied_dispatch.rule_ids)
            prefix_evidence_ids.update(applied_dispatch.evidence_ids)
            prefix_rule_dependencies.update(
                (rule_id, evidence_id)
                for rule_id in applied_dispatch.rule_ids
                for evidence_id in applied_dispatch.evidence_ids
            )
    return stages


def _analyze_payload(
    extracted: ExtractedFacts,
    *,
    summary_effect_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    units: list[dict[str, object]] = []
    for unit in extracted.units:
        analysis = solve(unit.program, budget=extracted.budget)
        dimensions = check_invariants(
            unit.program,
            analysis,
            unit.invariants,
            timeout_ms=extracted.budget.timeout_ms,
            executor_contracts=unit.executor_contracts,
        )
        dimension_statuses = sorted({item.lifecycle_status for item in dimensions})
        units.append(
            {
                "unit_id": unit.unit_id,
                "terminated": analysis.terminated,
                "steps": analysis.steps,
                "unknown_reasons": list(analysis.unknown_reasons),
                "lifecycle_statuses": dimension_statuses,
                "dimensions": [asdict(item) for item in dimensions],
                "async_stages": _async_stages(unit, analysis),
                "exit_states": {
                    event_id: {
                        "held_edges": [list(edge) for edge in sorted(state.held_edges)],
                        "open_obligations": sorted(state.open_obligations),
                        "instance_obligation_counts": [
                            [instance_id, {"lower": interval.lower, "upper": interval.upper}]
                            for instance_id, interval in state.instance_obligation_counts
                        ],
                        "obligation_counts": [
                            [family_id, {"lower": interval.lower, "upper": interval.upper}]
                            for family_id, interval in state.obligation_counts
                        ],
                        "allocation_counts": [
                            [family_id, {"lower": interval.lower, "upper": interval.upper}]
                            for family_id, interval in state.allocation_counts
                        ],
                        "held_counts": [
                            [family_id, {"lower": interval.lower, "upper": interval.upper}]
                            for family_id, interval in state.held_counts
                        ],
                        "peak_held_counts": [list(item) for item in state.peak_held_counts],
                        "unknown_reasons": list(state.unknown_reasons),
                    }
                    for event_id, state in sorted(analysis.exit_states.items())
                },
                "traces": {event_id: asdict(trace) for event_id, trace in sorted(analysis.traces.items()) if event_id in analysis.exit_states},
            }
        )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "summary_effect_ids": list(summary_effect_ids),
        "units": units,
    }
    payload["result_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    return payload


def _evidence_payload(
    extracted: ExtractedFacts,
    results: Mapping[str, object],
    *,
    summary_artifact: Mapping[str, object] | None = None,
) -> dict[str, object]:
    facts = {item.fact_id: asdict(item) for item in extracted.facts}
    rules: set[str] = set()
    dependency_pairs: set[tuple[str, str]] = set()
    proof_dependency_pairs: set[tuple[str, str]] = set()
    derivations: list[dict[str, object]] = []
    dimension_derivations: list[dict[str, object]] = []
    async_derivations: list[dict[str, object]] = []
    summary_derivations: list[dict[str, object]] = []
    async_rules: set[str] = set()
    units_by_id = {unit.unit_id: unit for unit in extracted.units}
    for source_unit in extracted.units:
        for resource in source_unit.program.families:
            facts.setdefault(
                resource.family_id,
                {
                    "kind": "resource_family",
                    "resource_type": resource.resource_type,
                    "location": asdict(resource.allocation),
                },
            )
        for instance in source_unit.program.instances:
            facts.setdefault(
                instance.instance_id,
                {"kind": "abstract_instance", **asdict(instance)},
            )
        for candidate in source_unit.invariants:
            for evidence_id in candidate.evidence_ids:
                facts.setdefault(
                    evidence_id,
                    {
                        "kind": "invariant_evidence",
                        "candidate_id": candidate.candidate_id,
                        "source_kind": candidate.source_kind,
                        "assumptions": list(candidate.assumptions),
                    },
                )
        for transition in source_unit.program.transitions:
            for effect in transition.effects:
                for evidence_id in effect.evidence_ids:
                    facts.setdefault(
                        evidence_id,
                        {
                            "kind": "effect_evidence",
                            "effect_id": effect.effect_id,
                            "effect_kind": effect.kind,
                            "location": asdict(effect.location),
                        },
                    )
    for unit in results.get("units", []):
        if not isinstance(unit, Mapping):
            continue
        unit_id = unit.get("unit_id")
        source_unit = units_by_id.get(str(unit_id))
        if source_unit is None:
            continue
        transitions = {item.transition_id: item for item in source_unit.program.transitions}
        traces = unit.get("traces")
        exit_states = unit.get("exit_states")
        effects_by_id = {
            effect.effect_id: effect
            for transition in source_unit.program.transitions
            for effect in transition.effects
        }
        stages = unit.get("async_stages")
        if isinstance(stages, list):
            for stage in stages:
                if not isinstance(stage, Mapping):
                    continue
                dispatch_effect = effects_by_id.get(str(stage.get("dispatch_effect_id") or ""))
                if dispatch_effect is None:
                    continue
                evidence_ids = tuple(
                    sorted(
                        {
                            str(item)
                            for item in stage.get("evidence_ids", [])
                            if isinstance(item, str)
                        }
                    )
                )
                rule_ids = tuple(
                    dict.fromkeys(
                        str(item)
                        for item in stage.get("rule_ids", [])
                        if isinstance(item, str)
                    )
                )
                prefix_rule_ids = {
                    str(item)
                    for item in stage.get("prefix_rule_ids", [])
                    if isinstance(item, str)
                }
                rule_dependencies = {
                    (str(pair[0]), str(pair[1]))
                    for pair in stage.get("rule_dependencies", [])
                    if isinstance(pair, (list, tuple))
                    and len(pair) == 2
                    and isinstance(pair[0], str)
                    and isinstance(pair[1], str)
                }
                if {item[0] for item in rule_dependencies} != set(rule_ids):
                    raise ValueError("async stage rule dependencies are incomplete")
                if {item[1] for item in rule_dependencies} != set(evidence_ids):
                    raise ValueError("async stage evidence dependencies are incomplete")
                conclusions = {
                    phase: dict(stage[phase])
                    for phase in ("submitted", "started", "completed", "rejected", "cancelled")
                    if isinstance(stage.get(phase), Mapping)
                }
                derivation_body = {
                    "unit_id": unit_id,
                    "stage_id": stage.get("stage_id"),
                    "transition_id": stage.get("transition_id"),
                    "dispatch_effect_id": dispatch_effect.effect_id,
                    "contract_id": stage.get("contract_id"),
                    "contract_status": stage.get("contract_status"),
                    "target_event_id": stage.get("target_event_id"),
                    "rule_ids": list(rule_ids),
                    "evidence_ids": list(evidence_ids),
                    "conclusions": conclusions,
                    "code_locations": [asdict(dispatch_effect.location)],
                }
                derivation_id = hashlib.sha256(canonical_json(derivation_body)).hexdigest()
                async_derivations.append(
                    {"derivation_id": derivation_id, **derivation_body}
                )
                async_rules.update(set(rule_ids) - prefix_rule_ids)
                rules.update(rule_ids)
                dependency_pairs.update(rule_dependencies)
                proof_dependency_pairs.update(
                    (derivation_id, evidence_id) for evidence_id in evidence_ids
                )
        if not isinstance(traces, Mapping):
            continue
        for exit_event_id, trace in sorted(traces.items()):
            if not isinstance(trace, Mapping):
                continue
            selected = [transitions[item] for item in trace.get("transition_ids", []) if item in transitions]
            effects = [effect for transition in selected for effect in transition.effects]
            premises = sorted(
                set(
                    [f"guard:{transition.guard}" for transition in selected]
                    + [f"assumption:{item}" for transition in selected for item in transition.assumptions]
                    + [f"effect_condition:{effect.condition}" for effect in effects]
                )
            )
            locations_by_key = {
                (
                    effect.location.path,
                    effect.location.start_line,
                    effect.location.end_line,
                    effect.location.source_sha256,
                    effect.location.extractor_version,
                    effect.location.source_kind,
                ): asdict(effect.location)
                for effect in effects
            }
            conclusion = {}
            if isinstance(exit_states, Mapping) and isinstance(exit_states.get(exit_event_id), Mapping):
                conclusion = dict(exit_states[exit_event_id])
            derivation_body = {
                "unit_id": unit_id,
                "exit_event_id": exit_event_id,
                "transition_ids": list(trace.get("transition_ids", [])),
                "rule_ids": list(trace.get("rule_ids", [])),
                "evidence_ids": list(trace.get("evidence_ids", [])),
                "premises": premises,
                "conclusion": conclusion,
                "code_locations": [locations_by_key[key] for key in sorted(locations_by_key)],
            }
            derivations.append(
                {
                    "derivation_id": hashlib.sha256(canonical_json(derivation_body)).hexdigest(),
                    **derivation_body,
                }
            )
            for pair in trace.get("rule_dependencies", []):
                if (
                    isinstance(pair, (list, tuple))
                    and len(pair) == 2
                    and isinstance(pair[0], str)
                    and isinstance(pair[1], str)
                ):
                    rules.add(pair[0])
                    dependency_pairs.add((pair[0], pair[1]))
        dimensions = unit.get("dimensions")
        if not isinstance(dimensions, list):
            continue
        family_by_id = {item.family_id: item for item in source_unit.program.families}
        for dimension in dimensions:
            if not isinstance(dimension, Mapping):
                continue
            family_id = str(dimension.get("resource_family_id") or "")
            resource = family_by_id.get(family_id)
            if resource is None:
                continue
            candidates = [
                candidate
                for candidate in source_unit.invariants
                if candidate.family_id == family_id
                and candidate.dimension == dimension.get("dimension")
                and candidate_result_scope(candidate) == dimension.get("scope")
            ]
            evidence_ids = tuple(
                sorted(
                    set(
                        [family_id]
                        + [str(item) for item in dimension.get("evidence_ids", []) if isinstance(item, str)]
                        + [item for candidate in candidates for item in candidate.evidence_ids]
                    )
                )
            )
            locations = {
                (
                    resource.allocation.path,
                    resource.allocation.start_line,
                    resource.allocation.end_line,
                    resource.allocation.source_sha256,
                ): asdict(resource.allocation)
            }
            for transition in source_unit.program.transitions:
                for effect in transition.effects:
                    dimension_scope = str(dimension.get("scope") or "")
                    if effect.family_id == family_id and (
                        not dimension_scope.startswith("task_queue:")
                        or (
                            effect.kind == "dispatch"
                            and queue_result_scope(
                                effect.contract_id,
                                effect.holder_id,
                                effect.target_event_id,
                            )
                            == dimension_scope
                        )
                    ):
                        locations.setdefault(
                            (
                                effect.location.path,
                                effect.location.start_line,
                                effect.location.end_line,
                                effect.location.source_sha256,
                            ),
                            asdict(effect.location),
                        )
            proof_body = {
                "unit_id": unit_id,
                "resource_family_id": family_id,
                "dimension": dimension.get("dimension"),
                "scope": dimension.get("scope"),
                "lifecycle_status": dimension.get("lifecycle_status"),
                "upper_bound": dimension.get("upper_bound"),
                "assumptions": list(dimension.get("assumptions", [])),
                "reason_codes": list(dimension.get("reason_codes", [])),
                "candidate_ids": [item.candidate_id for item in candidates],
                "evidence_ids": list(evidence_ids),
                "code_locations": [locations[key] for key in sorted(locations)],
            }
            proof_id = hashlib.sha256(canonical_json(proof_body)).hexdigest()
            dimension_derivations.append({"proof_id": proof_id, **proof_body})
            proof_dependency_pairs.update((proof_id, evidence_id) for evidence_id in evidence_ids)
    if summary_artifact is not None:
        records = summary_artifact.get("records")
        if not isinstance(records, list):
            raise ValueError("resource lifecycle summary evidence is malformed")
        for record in records:
            if not isinstance(record, Mapping):
                raise ValueError("resource lifecycle summary evidence record is malformed")
            proposal = record.get("proposal")
            validation = record.get("validation")
            claimed_evidence_ids = (
                tuple(str(item) for item in proposal.get("evidence_ids", []) if isinstance(item, str))
                if isinstance(proposal, Mapping)
                else ()
            )
            effect_evidence_ids = tuple(
                dict.fromkeys(
                    str(evidence_id)
                    for path_name in ("normal_effects", "exceptional_effects")
                    for effect in (
                        proposal.get(path_name, [])
                        if isinstance(proposal, Mapping)
                        and isinstance(proposal.get(path_name), (list, tuple))
                        else []
                    )
                    if isinstance(effect, Mapping)
                    and isinstance(effect.get("evidence_ids"), (list, tuple))
                    for evidence_id in effect["evidence_ids"]
                    if isinstance(evidence_id, str)
                )
            )
            trigger_evidence_ids = tuple(
                str(item)
                for item in record.get("trigger_evidence_ids", [])
                if isinstance(item, str)
            )
            evidence_ids = tuple(
                dict.fromkeys(
                    item
                    for item in claimed_evidence_ids
                    + effect_evidence_ids
                    + trigger_evidence_ids
                    if item in facts
                )
            )
            code_locations = (
                [dict(proposal["location"])]
                if isinstance(proposal, Mapping) and isinstance(proposal.get("location"), Mapping)
                else []
            )
            summary_body = {
                "record_id": record.get("record_id"),
                "unknown_effect_id": record.get("unknown_effect_id"),
                "summary_id": proposal.get("summary_id") if isinstance(proposal, Mapping) else None,
                "validation_status": validation.get("status") if isinstance(validation, Mapping) else None,
                "validation_layers": list(validation.get("layers", [])) if isinstance(validation, Mapping) else [],
                "usable_effect_ids": list(record.get("usable_effect_ids", [])),
                "trigger_evidence_ids": list(trigger_evidence_ids),
                "claimed_evidence_ids": list(claimed_evidence_ids),
                "effect_evidence_ids": list(effect_evidence_ids),
                "evidence_ids": list(evidence_ids),
                "code_locations": code_locations,
            }
            derivation_id = hashlib.sha256(canonical_json(summary_body)).hexdigest()
            summary_derivations.append({"derivation_id": derivation_id, **summary_body})
            proof_dependency_pairs.update((derivation_id, evidence_id) for evidence_id in evidence_ids)
    dependencies = [
        {"rule_id": rule_id, "evidence_id": evidence_id}
        for rule_id, evidence_id in sorted(dependency_pairs)
    ]
    proof_dependencies = [
        {"proof_id": proof_id, "evidence_id": evidence_id}
        for proof_id, evidence_id in sorted(proof_dependency_pairs)
    ]
    referenced_evidence = {
        evidence_id for _rule_id, evidence_id in dependency_pairs
    }.union(evidence_id for _proof_id, evidence_id in proof_dependency_pairs)
    if not referenced_evidence <= set(facts):
        raise ValueError("resource lifecycle evidence dependency is unresolved")
    return {
        "schema_version": SCHEMA_VERSION,
        "facts": facts,
        "rules": [
            {
                "rule_id": item,
                "implementation": (
                    "resource_lifecycle.events.expand_dispatch"
                    if item in async_rules
                    else "resource_lifecycle.solver.apply_effect"
                ),
            }
            for item in sorted(rules)
        ],
        "dependencies": dependencies,
        "proof_dependencies": proof_dependencies,
        "derivations": sorted(derivations, key=lambda item: (str(item["unit_id"]), str(item["exit_event_id"]))),
        "dimension_derivations": sorted(
            dimension_derivations,
            key=lambda item: (
                str(item["unit_id"]),
                str(item["resource_family_id"]),
                str(item["dimension"]),
                str(item["scope"]),
            ),
        ),
        "async_derivations": sorted(
            async_derivations,
            key=lambda item: (str(item["unit_id"]), str(item["stage_id"])),
        ),
        "summary_derivations": sorted(
            summary_derivations,
            key=lambda item: (str(item["unknown_effect_id"]), str(item["summary_id"])),
        ),
        "result_sha256": results.get("result_sha256"),
    }


def _implementation_sha256() -> str:
    package = Path(__file__).resolve().parent
    dosweb_root = package.parent
    paths = tuple(sorted(package.glob("*.py"))) + (
        dosweb_root / "cli.py",
        dosweb_root / "codeql" / "decoder.py",
        dosweb_root / "codeql" / "runner.py",
        _QUERY,
    )
    identity = [
        {
            "path": str(path.relative_to(dosweb_root)),
            "sha256": load_regular_bytes_with_sha256(path)[1],
        }
        for path in sorted(paths, key=lambda item: str(item))
    ]
    return hashlib.sha256(canonical_json(identity)).hexdigest()


def _run_cache_key(
    extracted: ExtractedFacts,
    facts_hash: str,
    implementation_sha256: str,
    llm_identity: Mapping[str, object],
) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "facts_sha256": facts_hash,
                "tool_version": TOOL_VERSION,
                "implementation_sha256": implementation_sha256,
                "contracts_versions": sorted({unit.program.contracts_version for unit in extracted.units}),
                "budget": asdict(extracted.budget),
                "llm": dict(llm_identity),
            }
        )
    ).hexdigest()


def _summary(
    extracted: ExtractedFacts,
    results: Mapping[str, object],
    llm_identity: Mapping[str, object],
) -> str:
    units = results.get("units") if isinstance(results.get("units"), list) else []
    counts: dict[str, int] = {}
    for unit in units:
        if not isinstance(unit, Mapping) or not isinstance(unit.get("dimensions"), list):
            continue
        for item in unit["dimensions"]:
            if isinstance(item, Mapping):
                status = str(item.get("lifecycle_status"))
                counts[status] = counts.get(status, 0) + 1
    lines = [
        "# Resource Lifecycle Analysis",
        "",
        f"- 输入模式：`{extracted.coverage.get('end_to_end_mode', 'unknown')}`",
        f"- source_kind：`{extracted.source_kind}`",
        f"- 分析单元：{len(units)}",
        f"- 维度状态：{json.dumps(counts, ensure_ascii=False, sort_keys=True)}",
        f"- LLM：`{llm_identity.get('mode', 'off')}`，calls={llm_identity.get('calls', 0)}",
        "- impact_status：`not_evaluated`",
        "",
        "`bounded` 只对记录的 dimension、scope 和 assumptions 成立，不表示服务可用性或实际 DoS 结论。",
        "",
    ]
    return "\n".join(lines)


def _off_llm_identity() -> dict[str, object]:
    return {"mode": "off", "provider": None, "model": None, "calls": 0, "cost": None}


def _artifact_file_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value) + b"\n").hexdigest()


@contextmanager
def _run_directory_lock(run_dir: Path) -> Iterator[None]:
    directory_descriptor = -1
    lock_descriptor = -1
    locked = False
    try:
        directory_descriptor = os.open(
            run_dir,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        directory_info = os.fstat(directory_descriptor)
        if (
            not stat.S_ISDIR(directory_info.st_mode)
            or directory_info.st_uid != os.geteuid()
        ):
            raise OSError("run directory is not owner-safe")
        lock_descriptor = os.open(
            _RUN_LOCK_NAME,
            os.O_RDWR
            | os.O_CREAT
            | os.O_NONBLOCK
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory_descriptor,
        )
        lock_info = os.fstat(lock_descriptor)
        if (
            not stat.S_ISREG(lock_info.st_mode)
            or stat.S_IMODE(lock_info.st_mode) != 0o600
            or lock_info.st_uid != os.geteuid()
            or lock_info.st_nlink != 1
        ):
            raise OSError("run lock is not an owner-only regular file")
        deadline = time.monotonic() + _RUN_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError as exc:
                if exc.errno == errno.EINTR:
                    continue
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AnalyzerError(
                        "ARTIFACT_LOCK_TIMEOUT",
                        "Resource lifecycle run directory lock timed out.",
                        {"path": str(run_dir / _RUN_LOCK_NAME)},
                    ) from exc
                time.sleep(min(_RUN_LOCK_POLL_SECONDS, remaining))
        yield
    except AnalyzerError:
        raise
    except OSError as exc:
        raise AnalyzerError(
            "ARTIFACT_UNSAFE_OUTPUT_PATH",
            "Resource lifecycle run directory lock is unsafe.",
            {"path": str(run_dir / _RUN_LOCK_NAME)},
        ) from exc
    finally:
        if locked:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        if lock_descriptor >= 0:
            os.close(lock_descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _prepare_analyze_output(output: Path, llm_mode: str) -> None:
    managed_names = (
        *_ANALYZE_COMMON_ARTIFACTS,
        *_ANALYZE_REPLAY_ARTIFACTS,
        _ANALYZE_STALE_REPLAY_ARTIFACT,
    )
    stale_names = {_ANALYZE_STALE_REPLAY_ARTIFACT}
    if llm_mode == "off":
        stale_names.update(_ANALYZE_REPLAY_ARTIFACTS)
    existing: dict[str, tuple[int, int]] = {}
    current_path = output
    try:
        for name in managed_names:
            current_path = output / name
            try:
                info = current_path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode):
                raise OSError("managed artifact is not a regular file")
            existing[name] = (info.st_dev, info.st_ino)
        for name in sorted(stale_names.intersection(existing)):
            current_path = output / name
            info = current_path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or (info.st_dev, info.st_ino) != existing[name]
            ):
                raise OSError("managed artifact changed before cleanup")
            current_path.unlink()
    except OSError as exc:
        raise AnalyzerError(
            "ARTIFACT_UNSAFE_OUTPUT_PATH",
            "Resource lifecycle analyze output contains an unsafe managed artifact.",
            {"path": str(current_path)},
        ) from exc


def _recorded_summary_run(
    values: Mapping[str, object],
    extracted: ExtractedFacts,
) -> tuple[AppliedSummaries, Mapping[str, object], Mapping[str, object]]:
    config_path = _required_path(values, "config")
    try:
        recording = recording_from_dict(load_json_regular(config_path))
        applied = apply_recorded_summaries(extracted, recording)
    except AnalyzerError:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise AnalyzerError(
            "ARTIFACT_INPUT_INVALID",
            "Recorded resource lifecycle summary input is invalid.",
        ) from exc
    recording_artifact = recording_to_dict(recording)
    llm_identity: dict[str, object] = {
        "mode": "replay",
        "provider": recording.provider,
        "model": recording.model,
        "calls": len(recording.responses),
        "cost": None,
        "live_call_verified": False,
        "contract_version": recording.contract_version,
        "budget": asdict(recording.budget),
        "recording_snapshot": _ANALYZE_REPLAY_ARTIFACTS[0],
        "recording_sha256": _artifact_file_sha256(recording_artifact),
        "summaries_sha256": _artifact_file_sha256(applied.artifact),
    }
    return applied, llm_identity, recording_artifact


def resource_analyze(values: Mapping[str, object]) -> dict[str, object]:
    llm_mode = values.get("llm") or "off"
    provider_overrides = (
        "allow_remote_llm",
        "public_source_url",
        "source_commit_sha",
        "source_checkout",
        "model",
        "base_url",
        "timeout_seconds",
        "max_retries",
        "temperature",
        "cache_dir",
    )
    if any(values.get(name) is not None for name in provider_overrides):
        raise AnalyzerError(
            "CONFIG_INVALID_VALUE",
            "Resource lifecycle LLM provider settings must come from the recording; live overrides are unsupported.",
        )
    if llm_mode == "live":
        raise AnalyzerError(
            "CONFIG_INVALID_VALUE",
            "Resource lifecycle v1 live LLM calls are not implemented; use --llm off or --llm replay.",
        )
    if llm_mode not in {"off", "replay"}:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "Resource lifecycle LLM mode is invalid.")
    if llm_mode == "off" and values.get("config") is not None:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "--config is only valid with --llm replay.")
    facts_path = _required_path(values, "facts")
    output = ensure_output_directory(_required_path(values, "out"))
    try:
        extracted = validate_extracted(extracted_from_dict(load_json_regular(facts_path)))
    except AnalyzerError:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle facts artifact is invalid.") from exc
    facts_artifact = extracted_to_dict(extracted)
    facts_hash = _artifact_file_sha256(facts_artifact)
    recording_artifact: Mapping[str, object] | None = None
    if llm_mode == "replay":
        applied, llm_identity, recording_artifact = _recorded_summary_run(
            values, extracted
        )
        analysis_input = applied.extracted
        summary_artifact: Mapping[str, object] | None = applied.artifact
        summary_effect_ids = applied.summary_effect_ids
    else:
        llm_identity = _off_llm_identity()
        analysis_input = extracted
        summary_artifact = None
        summary_effect_ids = ()
    results = _analyze_payload(analysis_input, summary_effect_ids=summary_effect_ids)
    implementation_sha256 = _implementation_sha256()
    run_manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "implementation_sha256": implementation_sha256,
        "facts_sha256": facts_hash,
        "input_snapshot_sha256": extracted.snapshot_sha256,
        "source_snapshot_sha256": extracted.coverage.get("source_snapshot_sha256"),
        "extractor_version": extracted.extractor_version,
        "contracts_versions": sorted({unit.program.contracts_version for unit in extracted.units}),
        "budget": asdict(extracted.budget),
        "llm": dict(llm_identity),
        "cache_key": _run_cache_key(extracted, facts_hash, implementation_sha256, llm_identity),
    }
    evidence = _evidence_payload(
        analysis_input,
        results,
        summary_artifact=summary_artifact,
    )
    summary = _summary(extracted, results, llm_identity)
    with _run_directory_lock(output):
        _prepare_analyze_output(output, llm_mode)
        atomic_write_json(output / "facts.snapshot.json", facts_artifact)
        if recording_artifact is not None and summary_artifact is not None:
            recording_path = output / _ANALYZE_REPLAY_ARTIFACTS[0]
            summaries_path = output / _ANALYZE_REPLAY_ARTIFACTS[1]
            atomic_write_json(recording_path, recording_artifact)
            atomic_write_json(summaries_path, summary_artifact)
            os.chmod(recording_path, 0o600)
            os.chmod(summaries_path, 0o600)
        atomic_write_json(output / "run-manifest.json", run_manifest)
        atomic_write_json(output / "lifecycle-results.json", results)
        atomic_write_json(output / "evidence.json", evidence)
        atomic_write_text(output / "summary.md", summary)
    return results


def resource_replay(values: Mapping[str, object]) -> dict[str, object]:
    run_dir = _required_path(values, "run").absolute()
    with _run_directory_lock(run_dir):
        return _resource_replay_locked(run_dir)


def _resource_replay_locked(run_dir: Path) -> dict[str, object]:
    manifest = load_json_regular(run_dir / "run-manifest.json")
    stored = load_json_regular(run_dir / "lifecycle-results.json")
    stored_evidence = load_json_regular(run_dir / "evidence.json")
    if not isinstance(manifest, Mapping) or not isinstance(stored, Mapping) or not isinstance(stored_evidence, Mapping):
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle run is invalid.")
    facts_artifact, facts_hash = load_json_regular_with_sha256(
        run_dir / "facts.snapshot.json"
    )
    if manifest.get("facts_sha256") != facts_hash:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle replay facts hash does not match manifest.")
    try:
        extracted = validate_extracted(extracted_from_dict(facts_artifact))
    except (ValueError, TypeError, KeyError) as exc:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle replay facts are invalid.") from exc
    expected_contracts = sorted({unit.program.contracts_version for unit in extracted.units})
    expected_budget = asdict(extracted.budget)
    implementation_sha256 = _implementation_sha256()
    llm = manifest.get("llm")
    if not isinstance(llm, Mapping):
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle replay LLM identity is invalid.")
    summary_consistent = True
    stored_summary_sha: str | None = None
    recomputed_summary_sha: str | None = None
    llm_mode = llm.get("mode")
    if llm_mode == "off":
        if dict(llm) != _off_llm_identity():
            raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle replay LLM identity is inconsistent.")
        analysis_input = extracted
        summary_artifact: Mapping[str, object] | None = None
        summary_effect_ids: tuple[str, ...] = ()
    elif llm_mode == "replay":
        if set(llm) != {
            "mode", "provider", "model", "calls", "cost", "live_call_verified",
            "contract_version", "budget", "recording_snapshot", "recording_sha256",
            "summaries_sha256",
        } or llm.get("recording_snapshot") != "llm-recording.private.json":
            raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle replay recording identity is malformed.")
        recording_path = run_dir / "llm-recording.private.json"
        try:
            recording_artifact, recording_sha = load_json_regular_with_sha256(
                recording_path,
                required_mode=0o600,
            )
            if llm.get("recording_sha256") != recording_sha:
                raise ValueError("recording snapshot hash mismatch")
            recording = recording_from_dict(recording_artifact)
            applied = apply_recorded_summaries(extracted, recording)
            summaries_path = run_dir / "llm-summaries.json"
            stored_summary, stored_summary_sha = load_json_regular_with_sha256(
                summaries_path,
                required_mode=0o600,
            )
            if not isinstance(stored_summary, Mapping):
                raise ValueError("stored summary artifact is invalid")
            expected_llm = {
                "mode": "replay",
                "provider": recording.provider,
                "model": recording.model,
                "calls": len(recording.responses),
                "cost": None,
                "live_call_verified": False,
                "contract_version": recording.contract_version,
                "budget": asdict(recording.budget),
                "recording_snapshot": recording_path.name,
                "recording_sha256": recording_sha,
                "summaries_sha256": llm.get("summaries_sha256"),
            }
            if dict(llm) != expected_llm:
                raise ValueError("recording manifest identity mismatch")
            recomputed_summary_sha = _artifact_file_sha256(applied.artifact)
            summary_consistent = (
                llm.get("summaries_sha256")
                == stored_summary_sha
                == recomputed_summary_sha
            )
            analysis_input = applied.extracted
            summary_artifact = applied.artifact
            summary_effect_ids = applied.summary_effect_ids
        except AnalyzerError:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise AnalyzerError(
                "ARTIFACT_INPUT_INVALID",
                "Resource lifecycle recorded summary replay is invalid.",
            ) from exc
    else:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle replay LLM mode is unsupported.")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("tool_version") != TOOL_VERSION
        or manifest.get("implementation_sha256") != implementation_sha256
        or manifest.get("input_snapshot_sha256") != extracted.snapshot_sha256
        or manifest.get("source_snapshot_sha256") != extracted.coverage.get("source_snapshot_sha256")
        or manifest.get("extractor_version") != extracted.extractor_version
        or manifest.get("contracts_versions") != expected_contracts
        or manifest.get("budget") != expected_budget
        or manifest.get("cache_key") != _run_cache_key(
            extracted,
            str(manifest.get("facts_sha256")),
            implementation_sha256,
            llm,
        )
    ):
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle replay manifest identity is inconsistent.")
    recomputed = _analyze_payload(analysis_input, summary_effect_ids=summary_effect_ids)
    recomputed_evidence = _evidence_payload(
        analysis_input,
        recomputed,
        summary_artifact=summary_artifact,
    )
    stored_summary_markdown = load_text_regular(
        run_dir / "summary.md",
        max_bytes=_MAX_SUMMARY_BYTES,
    )
    recomputed_summary_markdown = _summary(extracted, recomputed, llm)
    stored_summary_markdown_sha = hashlib.sha256(
        stored_summary_markdown.encode("utf-8")
    ).hexdigest()
    recomputed_summary_markdown_sha = hashlib.sha256(
        recomputed_summary_markdown.encode("utf-8")
    ).hexdigest()
    summary_markdown_consistent = (
        stored_summary_markdown_sha == recomputed_summary_markdown_sha
    )
    stored_body = dict(stored)
    stored_declared = stored_body.pop("result_sha256", None)
    stored_observed = hashlib.sha256(canonical_json(stored_body)).hexdigest()
    stored_evidence_sha = hashlib.sha256(canonical_json(stored_evidence)).hexdigest()
    recomputed_evidence_sha = hashlib.sha256(canonical_json(recomputed_evidence)).hexdigest()
    evidence_consistent = (
        stored_evidence_sha == recomputed_evidence_sha
        and stored_evidence.get("result_sha256") == stored_observed
        and recomputed_evidence.get("result_sha256") == recomputed.get("result_sha256")
    )
    replay = {
        "schema_version": SCHEMA_VERSION,
        "consistent": (
            stored_declared == stored_observed == recomputed.get("result_sha256")
            and evidence_consistent
            and summary_consistent
            and summary_markdown_consistent
        ),
        "stored_declared_result_sha256": stored_declared,
        "stored_result_sha256": stored_observed,
        "recomputed_result_sha256": recomputed.get("result_sha256"),
        "evidence_consistent": evidence_consistent,
        "stored_evidence_sha256": stored_evidence_sha,
        "recomputed_evidence_sha256": recomputed_evidence_sha,
        "summary_consistent": summary_consistent,
        "stored_summary_sha256": stored_summary_sha,
        "recomputed_summary_sha256": recomputed_summary_sha,
        "summary_markdown_consistent": summary_markdown_consistent,
        "stored_summary_markdown_sha256": stored_summary_markdown_sha,
        "recomputed_summary_markdown_sha256": recomputed_summary_markdown_sha,
        "recomputed": True,
    }
    atomic_write_json(run_dir / "replay.json", replay)
    return replay


def dispatch_resource_command(values: Mapping[str, object]) -> dict[str, object]:
    command = values.get("command")
    if command == "resource-extract":
        return resource_extract(values)
    if command == "resource-analyze":
        return resource_analyze(values)
    if command == "resource-replay":
        return resource_replay(values)
    if command == "resource-evaluate":
        from dosweb.resource_lifecycle.evaluation import evaluate_command

        return evaluate_command(values)
    raise AnalyzerError("CONFIG_INVALID_COMMAND", "A valid resource lifecycle command is required.")
