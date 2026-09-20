#!/usr/bin/env python3
"""Run the layered, static-only PoC-33 demo acceptance gates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.artifacts.schemas import SCHEMA_VERSION
from dosweb.batch.corpus import load_canonical_corpus
from dosweb.batch.models import CanonicalCorpus
from dosweb.batch.plan import build_batch_plan, load_batch_plan, publish_batch_plan
from dosweb.batch.state import BatchState
from dosweb.config import DEFAULT_BASE_URL, DEFAULT_MODEL, resolve_api_key
from dosweb.errors import AnalyzerError
from dosweb.pipeline import TOOL_VERSION


_SELECTION_FORMAT = "dosweb-poc33-selection-v1"
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_ACCEPTANCE_FORMAT = "dosweb-poc33-acceptance-v1"
_REAL_PROVIDER_TIMEOUT_SECONDS = 180
_REAL_PROVIDER_MAX_RETRIES = 5
_REAL_PROVIDER_MAX_TARGET_ATTEMPTS = 2
_MAX_ARCHIVE_TARGET_ATTEMPTS = 64
PAUSED_EXIT_STATUS = 3


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _read_manifest(path: Path) -> tuple[object, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"manifest is not a regular file: {path}")
    raw = path.read_bytes()
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise ValueError(f"manifest exceeds {_MAX_MANIFEST_BYTES} bytes: {path}")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON manifest: {path}") from exc
    return value, raw


def _read_object(path: Path) -> dict[str, object]:
    value, _ = _read_manifest(path)
    if not isinstance(value, dict):
        raise ValueError(f"JSON document is not an object: {path}")
    return value


def _project_name(row: object, *, expected_index: int) -> str:
    if not isinstance(row, Mapping):
        raise ValueError("canonical project row is not an object")
    index = row.get("index")
    name = row.get("name")
    if index != expected_index or not isinstance(name, str) or not _PROJECT_NAME.fullmatch(name):
        raise ValueError("canonical project identity is invalid")
    return name


def build_poc33_selection(
    canonical_manifest: Path,
    truth_manifest: Path,
    *,
    run_id: str,
) -> dict[str, object]:
    """Join the 33 truth records to exactly 21 canonical targets.

    The returned project rows retain their canonical 205 indices.  This helper
    is benchmark-only and is never imported by the production analyzer.
    """
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id is invalid")
    canonical_value, canonical_raw = _read_manifest(canonical_manifest)
    truth_value, truth_raw = _read_manifest(truth_manifest)
    if not isinstance(canonical_value, Mapping) or (
        canonical_value.get("schema_version") != 1
        or canonical_value.get("status") != "canonical"
        or canonical_value.get("corpus") != "java-web-205"
        or canonical_value.get("total") != 205
        or canonical_value.get("valid_codeql_databases") != 205
        or canonical_value.get("batch_ready") is not True
    ):
        raise ValueError("canonical Java Web 205 manifest identity is invalid")
    projects = canonical_value.get("projects")
    if not isinstance(projects, list) or len(projects) != 205:
        raise ValueError("canonical Java Web 205 project count is invalid")

    by_name: dict[str, Mapping[str, Any]] = {}
    by_slug: dict[str, Mapping[str, Any]] = {}
    for expected_index, row in enumerate(projects, 1):
        name = _project_name(row, expected_index=expected_index)
        assert isinstance(row, Mapping)
        name_key = name.casefold()
        slug_key = name.replace("/", "__").casefold()
        if name_key in by_name or slug_key in by_slug:
            raise ValueError("canonical project identity is ambiguous")
        by_name[name_key] = row
        by_slug[slug_key] = row

    if not isinstance(truth_value, list) or len(truth_value) != 33:
        raise ValueError("PoC truth manifest must contain 33 records")
    selected: dict[str, Mapping[str, Any]] = {}
    record_ids: set[str] = set()
    for record in truth_value:
        if not isinstance(record, Mapping):
            raise ValueError("PoC truth record is not an object")
        record_id = record.get("record_id")
        app = record.get("app")
        if (
            not isinstance(record_id, str)
            or not record_id
            or record_id in record_ids
            or not isinstance(app, str)
            or not app
        ):
            raise ValueError("PoC truth identity is invalid")
        record_ids.add(record_id)
        key = app.casefold()
        direct = by_name.get(key)
        slug = by_slug.get(key)
        if direct is not None and slug is not None and direct is not slug:
            raise ValueError("PoC app identity is ambiguous")
        project = direct or slug
        if project is None:
            raise ValueError(f"PoC app is absent from canonical corpus: {app}")
        name = str(project["name"])
        selected[name.casefold()] = project

    if len(selected) != 21:
        raise ValueError("PoC truth manifest must resolve to exactly 21 targets")
    targets = sorted(selected.values(), key=lambda row: int(row["index"]))
    unsigned = {
        "format": _SELECTION_FORMAT,
        "run_id": run_id,
        "canonical_manifest_sha256": hashlib.sha256(canonical_raw).hexdigest(),
        "canonical_inventory_digest": sha256_canonical_json(canonical_value),
        "truth_manifest_sha256": hashlib.sha256(truth_raw).hexdigest(),
        "truth_record_count": len(truth_value),
        "target_count": len(targets),
        "targets": [dict(target) for target in targets],
    }
    return {**unsigned, "selection_digest": sha256_canonical_json(unsigned)}


def build_poc33_input_manifest(
    selection: Mapping[str, object],
    truth_manifest: Path,
    *,
    repo_root: Path,
) -> dict[str, object]:
    """Freeze analyzer inputs while retaining only oracle-free record identity."""
    truth_value, _truth_raw = _read_manifest(truth_manifest)
    targets = selection.get("targets")
    if not isinstance(truth_value, list) or len(truth_value) != 33:
        raise ValueError("PoC truth manifest must contain 33 records")
    if not isinstance(targets, list) or len(targets) != 21:
        raise ValueError("PoC selection must contain 21 targets")
    by_identity: dict[str, Mapping[str, object]] = {}
    projects: list[dict[str, object]] = []
    for row in targets:
        index, name, source_path, database_path, fingerprint_type, fingerprint = (
            _selection_identity(row)
        )
        by_identity[name.casefold()] = row
        by_identity[name.replace("/", "__").casefold()] = row
        source = repo_root / source_path
        database = repo_root / database_path
        projects.append(
            {
                "canonical_index": index,
                "normalized_project_id": name,
                "source_path": source_path,
                "database_path": database_path,
                "fingerprint_type": fingerprint_type,
                "fingerprint": fingerprint,
                "source_present": source.is_dir() and not source.is_symlink(),
                "database_present": database.is_dir() and not database.is_symlink(),
                "analysis_scope": "canonical_project_scope",
                "modules": [],
                "known_record_version_match": "unknown",
                "version_match_reason": (
                    "poc_manifest_has_no_source_version_provenance"
                ),
                "exclusions": [],
            }
        )
    records: list[dict[str, str]] = []
    for raw in truth_value:
        if not isinstance(raw, Mapping):
            raise ValueError("PoC truth record is not an object")
        record_id = raw.get("record_id")
        app = raw.get("app")
        if not isinstance(record_id, str) or not isinstance(app, str):
            raise ValueError("PoC truth identity is invalid")
        project = by_identity.get(app.casefold())
        if project is None:
            raise ValueError("PoC record is absent from frozen project selection")
        records.append(
            {
                "record_id": record_id,
                "normalized_project_id": str(project["name"]),
            }
        )
    try:
        implementation_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        implementation_commit = "unavailable"
    unsigned = {
        "format": "dosweb-poc33-input-manifest-v1",
        "run_id": selection["run_id"],
        "selection_digest": selection["selection_digest"],
        "canonical_manifest_sha256": selection["canonical_manifest_sha256"],
        "truth_manifest_sha256": selection["truth_manifest_sha256"],
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "implementation_commit": implementation_commit,
        "oracle_separation": {
            "analyzer_inputs": (
                "repository identity, source/database paths, fingerprints, "
                "configuration and canonical analysis scope"
            ),
            "evaluation_only": (
                "truth status, expected endpoint/location, root cause and prior verdict"
            ),
            "record_mapping_consumed_by_analyzer": False,
        },
        "records": sorted(records, key=lambda item: item["record_id"]),
        "projects": sorted(
            projects, key=lambda item: int(item["canonical_index"])
        ),
    }
    return {**unsigned, "manifest_digest": sha256_canonical_json(unsigned)}


def _selection_identity(row: object) -> tuple[int, str, str, str, str, str]:
    if not isinstance(row, Mapping):
        raise ValueError("selection target is not an object")
    index = row.get("index")
    name = row.get("name")
    source_path = row.get("source_path")
    database_path = row.get("codeql_path")
    fingerprint_type = row.get("fingerprint_type")
    fingerprint = row.get("checkout_fingerprint")
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or index < 1
        or not isinstance(name, str)
        or not _PROJECT_NAME.fullmatch(name)
        or not all(
            isinstance(value, str) and value
            for value in (source_path, database_path, fingerprint_type, fingerprint)
        )
    ):
        raise ValueError("selection target identity is invalid")
    return (
        index,
        name,
        str(source_path),
        str(database_path),
        str(fingerprint_type),
        str(fingerprint),
    )


def validate_entries_archive(root: Path, *, run_id: str) -> dict[str, object]:
    """Require the immutable 21-target entries archive to pass its 8-query gate."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id is invalid")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("entries archive is not a directory")
    plan = load_batch_plan(root / "batch_plan.json")
    if (
        plan.run_id != run_id
        or plan.mode != "entries"
        or plan.analysis_mode != "exploratory_entries"
        or plan.query_failure_policy != "coverage_gap"
        or plan.provider.get("allow_remote_llm", False) is not False
        or len(plan.targets) != 21
    ):
        raise ValueError("entries batch plan does not match the PoC-33 gate")

    selection = _read_object(root / "selection.json")
    digest = selection.get("selection_digest")
    unsigned_selection = {
        key: value for key, value in selection.items() if key != "selection_digest"
    }
    selection_targets = selection.get("targets")
    if (
        selection.get("format") != _SELECTION_FORMAT
        or selection.get("run_id") != run_id
        or selection.get("truth_record_count") != 33
        or selection.get("target_count") != 21
        or not isinstance(selection_targets, list)
        or len(selection_targets) != 21
        or not isinstance(digest, str)
        or digest != sha256_canonical_json(unsigned_selection)
    ):
        raise ValueError("selection manifest does not match the PoC-33 gate")
    selected_identities = {_selection_identity(row) for row in selection_targets}
    planned_identities = {
        (
            target.identity.index,
            target.identity.name,
            target.identity.source_path,
            target.identity.database_path,
            target.identity.fingerprint_type,
            target.identity.fingerprint,
        )
        for target in plan.targets
    }
    if selected_identities != planned_identities:
        raise ValueError("selection and batch plan target identities differ")

    state = BatchState.load(root / "batch_state.json")
    if (
        state.batch_id != plan.plan_id
        or state.mode != "entries"
        or state.status != "completed"
        or set(state.targets) != {target.target_id for target in plan.targets}
    ):
        raise ValueError("entries batch state is incomplete or mismatched")

    selected_queries = 0
    diagnostics = 0
    skipped = 0
    for target in plan.targets:
        state_row = state.targets[target.target_id]
        if state_row.get("state") != "completed" or state_row.get("status") != "completed":
            raise ValueError("entries target did not complete")
        target_root = root / "targets" / Path(target.output_path).name
        expected_binding = {
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "run_id": plan.run_id,
            "mode": plan.mode,
            "analysis_mode": plan.analysis_mode,
            "query_failure_policy": plan.query_failure_policy,
            "target": target.to_dict(),
        }
        if _read_object(target_root / "batch_target.json") != expected_binding:
            raise ValueError("entries target binding is invalid")
        run = _read_object(target_root / "run.json")
        identity = run.get("identity")
        stages = run.get("stages")
        entries = stages.get("entries") if isinstance(stages, Mapping) else None
        metadata = entries.get("metadata") if isinstance(entries, Mapping) else None
        if (
            run.get("schema_version") != SCHEMA_VERSION
            or run.get("tool_version") != TOOL_VERSION
            or run.get("status") != "completed"
            or not isinstance(identity, Mapping)
            or identity.get("analysis_mode") != "exploratory_entries"
            or identity.get("query_failure_policy") != "coverage_gap"
            or not isinstance(entries, Mapping)
            or entries.get("status") != "completed"
            or not isinstance(metadata, Mapping)
        ):
            raise ValueError("entries target run contract is invalid")
        query_count = metadata.get("query_count")
        query_diagnostics = metadata.get("query_diagnostics")
        skipped_count = metadata.get("skipped_query_count")
        if query_count != 8:
            raise ValueError("each entries target must execute exactly 8 selected queries")
        if not isinstance(query_diagnostics, list) or query_diagnostics:
            raise ValueError("entries target has query diagnostics")
        if skipped_count != 0:
            raise ValueError("entries target skipped a selected query")
        selected_queries += query_count
        diagnostics += len(query_diagnostics)
        skipped += skipped_count
    return {
        "status": "completed",
        "run_id": run_id,
        "target_count": len(plan.targets),
        "completed_targets": len(plan.targets),
        "selected_queries": selected_queries,
        "query_diagnostics": diagnostics,
        "skipped_queries": skipped,
    }


def validate_full_archive(
    root: Path,
    *,
    run_id: str,
    max_target_attempts: int = _REAL_PROVIDER_MAX_TARGET_ATTEMPTS,
) -> dict[str, object]:
    """Require 21 formal, fail-closed targets with owner-only private audits."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id is invalid")
    if (
        isinstance(max_target_attempts, bool)
        or not isinstance(max_target_attempts, int)
        or not 1 <= max_target_attempts <= _MAX_ARCHIVE_TARGET_ATTEMPTS
    ):
        raise ValueError("max_target_attempts is invalid")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("full archive is not a directory")
    plan = load_batch_plan(root / "batch_plan.json")
    if (
        plan.run_id != run_id
        or plan.mode != "full"
        or plan.analysis_mode != "formal"
        or plan.query_failure_policy != "fail_closed"
        or dict(plan.provider) != {
            "allow_remote_llm": True,
            "model": DEFAULT_MODEL,
            "base_url": DEFAULT_BASE_URL,
            "timeout_seconds": _REAL_PROVIDER_TIMEOUT_SECONDS,
            "max_retries": _REAL_PROVIDER_MAX_RETRIES,
        }
        or len(plan.targets) != 21
    ):
        raise ValueError("full batch plan does not match the PoC-33 gate")

    selection = _read_object(root / "selection.json")
    digest = selection.get("selection_digest")
    unsigned_selection = {
        key: value for key, value in selection.items() if key != "selection_digest"
    }
    selection_targets = selection.get("targets")
    if (
        selection.get("format") != _SELECTION_FORMAT
        or selection.get("run_id") != run_id
        or selection.get("truth_record_count") != 33
        or selection.get("target_count") != 21
        or not isinstance(selection_targets, list)
        or len(selection_targets) != 21
        or not isinstance(digest, str)
        or digest != sha256_canonical_json(unsigned_selection)
    ):
        raise ValueError("selection manifest does not match the PoC-33 gate")
    if {_selection_identity(row) for row in selection_targets} != {
        (
            target.identity.index,
            target.identity.name,
            target.identity.source_path,
            target.identity.database_path,
            target.identity.fingerprint_type,
            target.identity.fingerprint,
        )
        for target in plan.targets
    }:
        raise ValueError("selection and full plan target identities differ")

    state = BatchState.load(root / "batch_state.json")
    if (
        state.batch_id != plan.plan_id
        or state.mode != "full"
        or state.status != "completed"
        or set(state.targets) != {target.target_id for target in plan.targets}
    ):
        raise ValueError("full batch state is incomplete or mismatched")

    stages_required = (
        "entries",
        "growth",
        "flows",
        "lifecycle",
        "conclude",
        "report",
    )
    selected_queries = 0
    retried_targets = 0
    for target in plan.targets:
        state_row = state.targets[target.target_id]
        attempt = state_row.get("attempt")
        if (
            state_row.get("state") != "completed"
            or state_row.get("status") != "completed"
            or isinstance(attempt, bool)
            or not isinstance(attempt, int)
            or not 1 <= attempt <= max_target_attempts
        ):
            raise ValueError("full target did not complete")
        retried_targets += int(attempt > 1)
        target_root = root / "targets" / Path(target.output_path).name
        expected_binding = {
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "run_id": plan.run_id,
            "mode": plan.mode,
            "analysis_mode": plan.analysis_mode,
            "query_failure_policy": plan.query_failure_policy,
            "target": target.to_dict(),
        }
        if _read_object(target_root / "batch_target.json") != expected_binding:
            raise ValueError("full target binding is invalid")
        run = _read_object(target_root / "run.json")
        identity = run.get("identity")
        stages = run.get("stages")
        if (
            run.get("schema_version") != SCHEMA_VERSION
            or run.get("tool_version") != TOOL_VERSION
            or run.get("status") != "completed"
            or not isinstance(identity, Mapping)
            or identity.get("analysis_mode") != "formal"
            or identity.get("query_failure_policy") != "fail_closed"
            or not isinstance(stages, Mapping)
            or any(
                not isinstance(stages.get(stage), Mapping)
                or stages[stage].get("status") != "completed"
                for stage in stages_required
            )
        ):
            raise ValueError("full target run contract is invalid")
        entries = stages["entries"]
        metadata = entries.get("metadata")
        if not isinstance(metadata, Mapping):
            raise ValueError("full target entries metadata is missing")
        if metadata.get("query_count") != 8:
            raise ValueError("each full target must execute exactly 8 selected queries")
        if metadata.get("query_diagnostics") != [] or metadata.get("skipped_query_count") != 0:
            raise ValueError("full target has a selected query gap")
        selected_queries += 8
        audit = target_root / "llm_audit.private.jsonl"
        if (
            audit.is_symlink()
            or not audit.is_file()
            or stat.S_IMODE(audit.stat().st_mode) != 0o600
        ):
            raise ValueError("full target private audit is not owner-only")
    return {
        "status": "completed",
        "run_id": run_id,
        "target_count": 21,
        "completed_targets": 21,
        "selected_queries": selected_queries,
        "query_diagnostics": 0,
        "skipped_queries": 0,
        "private_audit_mode": "0600",
        "max_target_attempts": max_target_attempts,
        "retried_targets": retried_targets,
    }


def validate_p0_aggregate(root: Path, *, run_id: str) -> dict[str, object]:
    """Require one completed aggregate status per planned target."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id is invalid")
    plan = load_batch_plan(root / "batch_plan.json")
    if plan.run_id != run_id or plan.mode != "full" or len(plan.targets) != 21:
        raise ValueError("P0 aggregate plan run identity is invalid")
    status_path = root / "aggregate_status.jsonl"
    if status_path.is_symlink() or not status_path.is_file():
        raise ValueError("P0 aggregate status is missing")
    rows: list[dict[str, object]] = []
    for line in status_path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("P0 aggregate status row is invalid")
        rows.append(value)
    identities = {
        (
            row.get("batch_target_index"),
            row.get("batch_target_name"),
            row.get("batch_target_slug"),
        )
        for row in rows
    }
    expected_identities = {
        (target.identity.index, target.identity.name, target.identity.slug)
        for target in plan.targets
    }
    if (
        len(rows) != 21
        or len(identities) != 21
        or identities != expected_identities
        or any(
            row.get("batch_plan_id") != plan.plan_id
            or row.get("batch_plan_digest") != plan.plan_digest
            or row.get("batch_mode") != "full"
            or row.get("status") != "completed"
            or row.get("authoritative_status") != "completed"
            for row in rows
        )
    ):
        raise ValueError("P0 aggregate does not contain 21 completed targets")
    families = root / "aggregate_finding_families.jsonl"
    if families.is_symlink() or not families.is_file():
        raise ValueError("P0 aggregate finding families are missing")
    return {"aggregate_completed_targets": 21}


def _read_jsonl_objects(path: Path) -> list[dict[str, object]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"JSONL input is missing: {path}")
    rows: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"invalid JSONL object at {path}:{number}")
        rows.append(value)
    return rows


def _validate_recall_output(root: Path) -> dict[str, object]:
    summary = _read_object(root / "summary.json")
    rows = _read_jsonl_objects(root / "truth_dispositions.jsonl")
    record_ids = [row.get("record_id") for row in rows]
    if (
        summary.get("total") != 33
        or len(rows) != 33
        or len(set(record_ids)) != 33
        or any(not isinstance(value, str) or not value for value in record_ids)
    ):
        raise ValueError("recall output does not contain 33 unique truth dispositions")
    return {"truth_records": 33}


def _validate_family_dedup(path: Path) -> dict[str, object]:
    rows = _read_jsonl_objects(path)
    family_ids: set[str] = set()
    member_ids: set[str] = set()
    for row in rows:
        family_id = row.get("family_id")
        members = row.get("member_finding_ids")
        if (
            not isinstance(family_id, str)
            or not family_id
            or family_id in family_ids
            or not isinstance(members, list)
            or not members
            or any(not isinstance(value, str) or not value for value in members)
            or len(set(members)) != len(members)
            or member_ids.intersection(members)
        ):
            raise ValueError("finding family dedup contract failed")
        family_ids.add(family_id)
        member_ids.update(members)
    return {"finding_families": len(rows), "family_members": len(member_ids)}


def _gate_blockers(metrics: Mapping[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    supported = metrics.get("supported_chain_recall")
    positive = metrics.get("ordinary_positive_recall")
    negative = metrics.get("hard_negative_safety")
    supported_map = supported if isinstance(supported, Mapping) else {}
    positive_map = positive if isinstance(positive, Mapping) else {}
    negative_map = negative if isinstance(negative, Mapping) else {}
    precision = metrics.get("precision")
    checks = {
        "infrastructure": (
            metrics.get("targets") == 21
            and metrics.get("completed_targets") == 21
            and metrics.get("formal_completed") is True
            and metrics.get("selected_queries") == 168
            and metrics.get("query_diagnostics") == 0
            and metrics.get("skipped_queries") == 0
        ),
        "supported_chain_recall": (
            metrics.get("truth") == 33
            and metrics.get("explicit_deferred") == 4
            and supported_map.get("numerator") == 29
            and supported_map.get("denominator") == 29
        ),
        "ordinary_positive_recall": (
            metrics.get("eligible_positive") == 6
            and positive_map.get("denominator") == 6
            and isinstance(positive_map.get("numerator"), int)
            and int(positive_map["numerator"]) >= 5
        ),
        "hard_negative_safety": (
            metrics.get("hard_negative") == 15
            and negative_map.get("numerator") == 15
            and negative_map.get("denominator") == 15
            and metrics.get("hard_negative_static_vulnerable") == 0
        ),
        "actionable_precision": (
            isinstance(precision, (int, float))
            and not isinstance(precision, bool)
            and float(precision) >= 0.50
        ),
    }
    stage_for_check = {
        "infrastructure": "entry",
        "supported_chain_recall": "association",
        "ordinary_positive_recall": "reach",
        "hard_negative_safety": "bound",
        "actionable_precision": "conclude",
    }
    stages = (
        "entry",
        "relevance",
        "association",
        "contract",
        "flow",
        "reach",
        "bound",
        "lifecycle",
        "conclude",
    )
    by_stage: dict[str, list[str]] = {stage: [] for stage in stages}
    for check, passed in checks.items():
        if not passed:
            by_stage[stage_for_check[check]].append(check)
    total = sum(len(values) for values in by_stage.values())
    gate = {
        "format": "dosweb-poc33-rollout-gate-v1",
        "status": "passed" if total == 0 else "failed",
        "rollout_178_target_full": total == 0,
        "checks": checks,
    }
    matrix = {
        "format": "dosweb-poc33-blocker-matrix-v1",
        "total_blockers": total,
        "by_stage": by_stage,
    }
    return gate, matrix


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "layer",
        choices=(
            "fast",
            "codeql-fixtures",
            "poc33-entries",
            "poc33-real-provider-full",
            "poc33-offline-eval",
        ),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--canonical-manifest", type=Path)
    parser.add_argument("--truth-manifest", type=Path)
    parser.add_argument("--dynamic", type=Path)
    parser.add_argument("--allow-remote-llm", action="store_true")
    parser.add_argument("--max-workers", type=int)
    return parser


def _write_new_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _provider_prerequisites(
    *,
    allow_remote_llm: bool,
    environment: Mapping[str, str],
    repo_root: Path,
) -> list[str]:
    reasons: list[str] = []
    if not allow_remote_llm:
        reasons.append("REMOTE_LLM_AUTHORIZATION_MISSING")
    if not resolve_api_key(environment, repo_root / "config" / "local_secrets.json"):
        reasons.append("REMOTE_LLM_API_KEY_MISSING")
    return reasons


def _command_summary(output: str) -> dict[str, int]:
    def total(pattern: str) -> int:
        return sum(int(value) for value in re.findall(pattern, output))

    return {
        "passed": total(r"\b(\d+) passed\b"),
        "skipped": total(r"\b(\d+) skipped\b"),
        "subtests_passed": total(r"\b(\d+) subtests passed\b"),
    }


def _run_commands(
    commands: list[list[str]],
    *,
    layer: str,
    repo_root: Path,
    environment: Mapping[str, str],
    command_runner: Any,
) -> int:
    started = time.monotonic()
    combined_stdout: list[str] = []
    for command in commands:
        completed = command_runner(
            command,
            cwd=repo_root,
            env=dict(environment),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        stdout = completed.stdout if isinstance(completed.stdout, str) else ""
        stderr = completed.stderr if isinstance(completed.stderr, str) else ""
        if stdout:
            print(stdout, end="" if stdout.endswith("\n") else "\n")
            combined_stdout.append(stdout)
        if stderr:
            print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
        if completed.returncode != 0:
            return int(completed.returncode) or 1
    summary = {
        "format": _ACCEPTANCE_FORMAT,
        "layer": layer,
        "status": "completed",
        "wall_time_seconds": round(max(0.0, time.monotonic() - started), 3),
        **_command_summary("\n".join(combined_stdout)),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _manifest_path(value: Path | None, *, default: Path, repo_root: Path) -> Path:
    path = default if value is None else value
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _selected_corpus(
    corpus: CanonicalCorpus,
    selection: Mapping[str, object],
    *,
    manifest_path: Path,
) -> CanonicalCorpus:
    if corpus.corpus != "java-web-205" or corpus.total != 205 or len(corpus.targets) != 205:
        raise ValueError("corpus loader did not return canonical Java Web 205")
    rows = selection.get("targets")
    if not isinstance(rows, list) or len(rows) != 21:
        raise ValueError("selection target list is invalid")
    by_name = {target.name.casefold(): target for target in corpus.targets}
    selected = []
    for row in rows:
        identity = _selection_identity(row)
        target = by_name.get(identity[1].casefold())
        if target is None or identity != (
            target.identity.index,
            target.identity.name,
            target.identity.source_path,
            target.identity.database_path,
            target.identity.fingerprint_type,
            target.identity.fingerprint,
        ):
            raise ValueError("validated corpus differs from the immutable selection")
        selected.append(target)
    digest = selection.get("selection_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("selection digest is invalid")
    return CanonicalCorpus(
        schema_version=1,
        status="canonical",
        corpus="poc33-21",
        total=21,
        inventory_digest=digest,
        targets=tuple(selected),
        manifest_path=manifest_path,
    )


def _new_output_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(mode=0o700, exist_ok=False)


def _plan_output_root(output: Path, repo_root: Path) -> str:
    try:
        return output.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return output.name


def _invoke_command(
    command: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    command_runner: Any,
) -> int:
    completed = command_runner(
        command,
        cwd=cwd,
        env=dict(environment),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    stdout = completed.stdout if isinstance(completed.stdout, str) else ""
    stderr = completed.stderr if isinstance(completed.stderr, str) else ""
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
    return int(completed.returncode)


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    command_runner: Any = subprocess.run,
    corpus_loader: Any = load_canonical_corpus,
) -> int:
    arguments = _parser().parse_args(argv)
    environment = dict(os.environ if environ is None else environ)
    repo_root = arguments.repo_root.resolve()
    results_root = (
        arguments.results_root.resolve()
        if arguments.results_root is not None
        else repo_root / "results" / "java_web_dos_batch"
    )
    try:
        if arguments.layer in {"fast", "codeql-fixtures"}:
            network_free_environment = dict(environment)
            network_free_environment.pop("DEEPSEEK_API_KEY", None)
            if arguments.layer == "fast":
                commands = [
                    [
                        sys.executable,
                        "-m",
                        "compileall",
                        "-q",
                        "dosweb",
                        "scripts",
                        "tests",
                    ],
                    [sys.executable, "-m", "pytest", "-q"],
                ]
            else:
                network_free_environment["DOSWEB_RUN_CODEQL_FIXTURES"] = "1"
                commands = [[
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_codeql_entry_queries.py",
                    "tests/test_codeql_growth_queries.py",
                    "tests/test_codeql_lifecycle_queries.py",
                    "tests/test_production_e2e.py",
                ]]
            return _run_commands(
                commands,
                layer=arguments.layer,
                repo_root=repo_root,
                environment=network_free_environment,
                command_runner=command_runner,
            )
        if arguments.layer == "poc33-entries":
            if not isinstance(arguments.run_id, str) or not _RUN_ID.fullmatch(arguments.run_id):
                raise ValueError("--run-id is required and must be safe")
            canonical_manifest = _manifest_path(
                arguments.canonical_manifest,
                default=repo_root / "intel/applications/java_web_205_targets.json",
                repo_root=repo_root,
            )
            truth_manifest = _manifest_path(
                arguments.truth_manifest,
                default=repo_root / "poc/manifest.json",
                repo_root=repo_root,
            )
            selection = build_poc33_selection(
                canonical_manifest,
                truth_manifest,
                run_id=arguments.run_id,
            )
            corpus = corpus_loader(canonical_manifest, repo_root=repo_root)
            selected_corpus = _selected_corpus(
                corpus,
                selection,
                manifest_path=canonical_manifest,
            )
            output = results_root / f"{arguments.run_id}-entries"
            _new_output_directory(output)
            plan = build_batch_plan(
                selected_corpus,
                run_id=arguments.run_id,
                mode="entries",
                output_root=_plan_output_root(output, repo_root),
                provider_settings={"allow_remote_llm": False},
            )
            publish_batch_plan(plan, output)
            _write_new_json(output / "selection.json", selection)
            _write_new_json(
                output / "input-manifest.json",
                build_poc33_input_manifest(
                    selection, truth_manifest, repo_root=repo_root
                ),
            )
            batch_environment = dict(environment)
            batch_environment.pop("DEEPSEEK_API_KEY", None)
            max_workers = arguments.max_workers if arguments.max_workers is not None else 3
            if max_workers < 1:
                raise ValueError("--max-workers must be positive")
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts/run_java_web_dos_batch.py"),
                "entries",
                "--plan",
                str(output / "batch_plan.json"),
                "--output",
                str(output),
                "--repo-root",
                str(repo_root),
                "--max-workers",
                str(max_workers),
                "--no-resume",
            ]
            returncode = _invoke_command(
                command,
                cwd=REPO_ROOT,
                environment=batch_environment,
                command_runner=command_runner,
            )
            if returncode != 0:
                return returncode or 1
            gate = validate_entries_archive(output, run_id=arguments.run_id)
            acceptance = {
                "format": _ACCEPTANCE_FORMAT,
                "layer": arguments.layer,
                "selection_digest": selection["selection_digest"],
                "plan_digest": plan.plan_digest,
                **gate,
            }
            _write_new_json(output / "acceptance_manifest.json", acceptance)
            print(output)
            return 0
        if arguments.layer == "poc33-offline-eval":
            if not isinstance(arguments.run_id, str) or not _RUN_ID.fullmatch(arguments.run_id):
                raise ValueError("--run-id is required and must be safe")
            full = results_root / f"{arguments.run_id}-full"
            archive_acceptance = _read_object(full / "acceptance_manifest.json")
            archive_attempt_limit = archive_acceptance.get(
                "max_target_attempts"
            )
            if (
                archive_acceptance.get("format") != _ACCEPTANCE_FORMAT
                or archive_acceptance.get("run_id") != arguments.run_id
                or archive_acceptance.get("status") != "completed"
            ):
                raise ValueError("full acceptance manifest is invalid")
            validate_full_archive(
                full,
                run_id=arguments.run_id,
                max_target_attempts=archive_attempt_limit,
            )
            validate_p0_aggregate(full, run_id=arguments.run_id)
            plan = load_batch_plan(full / "batch_plan.json")
            selection = _read_object(full / "selection.json")
            truth_manifest = _manifest_path(
                arguments.truth_manifest,
                default=repo_root / "poc/manifest.json",
                repo_root=repo_root,
            )
            if arguments.dynamic is None:
                raise ValueError("--dynamic is required for offline evaluation")
            dynamic = arguments.dynamic.resolve()
            if dynamic.is_symlink() or not dynamic.is_dir():
                raise ValueError("--dynamic must be a regular directory")
            recall = results_root / f"{arguments.run_id}-recall"
            evaluation = results_root / f"{arguments.run_id}-eval"
            if recall.exists() or evaluation.exists():
                raise ValueError("recall/evaluation output already exists; use a new run ID")
            offline_environment = dict(environment)
            offline_environment.pop("DEEPSEEK_API_KEY", None)
            recall_command = [
                sys.executable,
                str(REPO_ROOT / "scripts/generate_poc33_recall.py"),
                "--manifest",
                str(truth_manifest),
                "--results-root",
                str(full),
                "--output",
                str(recall),
                "--repo-root",
                str(repo_root),
            ]
            returncode = _invoke_command(
                recall_command,
                cwd=REPO_ROOT,
                environment=offline_environment,
                command_runner=command_runner,
            )
            if returncode != 0:
                return returncode or 1
            recall_gate = _validate_recall_output(recall)
            derived_common = {
                "format": "dosweb-poc33-derived-run-v1",
                "run_id": arguments.run_id,
                "selection_digest": selection["selection_digest"],
                "plan_digest": plan.plan_digest,
                "static_batch": str(full),
            }
            _write_new_json(recall / "run_manifest.json", {
                **derived_common,
                "artifact_kind": "recall",
                **recall_gate,
            })
            evaluate_command = [
                sys.executable,
                str(REPO_ROOT / "scripts/evaluate_poc33_demo.py"),
                "--static-batch",
                str(full),
                "--recall",
                str(recall),
                "--dynamic",
                str(dynamic),
                "--output",
                str(evaluation),
            ]
            returncode = _invoke_command(
                evaluate_command,
                cwd=REPO_ROOT,
                environment=offline_environment,
                command_runner=command_runner,
            )
            if returncode != 0:
                return returncode or 1
            metrics = _read_object(evaluation / "metrics.json")
            gate, blockers = _gate_blockers(metrics)
            try:
                dedup = _validate_family_dedup(
                    full / "aggregate_finding_families.jsonl"
                )
                dedup_ok = True
            except ValueError:
                dedup = {"finding_families": 0, "family_members": 0}
                dedup_ok = False
            gate_checks = gate["checks"]
            assert isinstance(gate_checks, dict)
            gate_checks["finding_family_dedup"] = dedup_ok
            if not dedup_ok:
                blocker_stages = blockers["by_stage"]
                assert isinstance(blocker_stages, dict)
                conclude = blocker_stages["conclude"]
                assert isinstance(conclude, list)
                conclude.append("finding_family_dedup")
                blockers["total_blockers"] = int(blockers["total_blockers"]) + 1
                gate["status"] = "failed"
                gate["rollout_178_target_full"] = False
            gate.update(dedup)
            gate["run_id"] = arguments.run_id
            blockers["run_id"] = arguments.run_id
            _write_new_json(evaluation / "gate.json", gate)
            _write_new_json(evaluation / "blocker_matrix.json", blockers)
            _write_new_json(evaluation / "run_manifest.json", {
                **derived_common,
                "artifact_kind": "evaluation",
                "dynamic_input": str(dynamic),
                "gate_status": gate["status"],
            })
            print(evaluation)
            return 0 if gate["status"] == "passed" else 1
        if arguments.layer == "poc33-real-provider-full":
            if not isinstance(arguments.run_id, str) or not _RUN_ID.fullmatch(arguments.run_id):
                raise ValueError("--run-id is required and must be safe")
            reasons = _provider_prerequisites(
                allow_remote_llm=bool(arguments.allow_remote_llm),
                environment=environment,
                repo_root=repo_root,
            )
            if reasons:
                document = {
                    "format": _ACCEPTANCE_FORMAT,
                    "layer": arguments.layer,
                    "run_id": arguments.run_id,
                    "status": "paused_by_provider_prerequisite",
                    "reason_codes": reasons,
                }
                _write_new_json(
                    results_root / f"{arguments.run_id}-provider-prerequisite.json",
                    document,
                )
                print(json.dumps(document, ensure_ascii=False, sort_keys=True))
                return PAUSED_EXIT_STATUS
            canonical_manifest = _manifest_path(
                arguments.canonical_manifest,
                default=repo_root / "intel/applications/java_web_205_targets.json",
                repo_root=repo_root,
            )
            truth_manifest = _manifest_path(
                arguments.truth_manifest,
                default=repo_root / "poc/manifest.json",
                repo_root=repo_root,
            )
            selection = build_poc33_selection(
                canonical_manifest,
                truth_manifest,
                run_id=arguments.run_id,
            )
            corpus = corpus_loader(canonical_manifest, repo_root=repo_root)
            selected_corpus = _selected_corpus(
                corpus,
                selection,
                manifest_path=canonical_manifest,
            )
            output = results_root / f"{arguments.run_id}-full"
            _new_output_directory(output)
            plan = build_batch_plan(
                selected_corpus,
                run_id=arguments.run_id,
                mode="full",
                output_root=_plan_output_root(output, repo_root),
                provider_settings={
                    "allow_remote_llm": True,
                    "model": DEFAULT_MODEL,
                    "base_url": DEFAULT_BASE_URL,
                    "timeout_seconds": _REAL_PROVIDER_TIMEOUT_SECONDS,
                    "max_retries": _REAL_PROVIDER_MAX_RETRIES,
                },
            )
            publish_batch_plan(plan, output)
            _write_new_json(output / "selection.json", selection)
            _write_new_json(
                output / "input-manifest.json",
                build_poc33_input_manifest(
                    selection, truth_manifest, repo_root=repo_root
                ),
            )
            max_workers = arguments.max_workers if arguments.max_workers is not None else 1
            if max_workers != 1:
                raise ValueError("real-provider full canary requires --max-workers 1")
            provider_environment = dict(environment)
            provider_key = resolve_api_key(
                provider_environment,
                repo_root / "config" / "local_secrets.json",
            )
            if not provider_key:
                raise ValueError("provider credential disappeared after prerequisite gate")
            provider_environment["DEEPSEEK_API_KEY"] = provider_key
            batch_command = [
                sys.executable,
                str(REPO_ROOT / "scripts/run_java_web_dos_batch.py"),
                "full",
                "--plan",
                str(output / "batch_plan.json"),
                "--output",
                str(output),
                "--repo-root",
                str(repo_root),
                "--max-workers",
                "1",
                "--retry-failed",
                "--max-attempts",
                str(_REAL_PROVIDER_MAX_TARGET_ATTEMPTS),
                "--no-resume",
                "--allow-remote-llm",
            ]
            returncode = _invoke_command(
                batch_command,
                cwd=REPO_ROOT,
                environment=provider_environment,
                command_runner=command_runner,
            )
            if returncode != 0:
                return returncode or 1
            gate = validate_full_archive(output, run_id=arguments.run_id)
            aggregate_command = [
                sys.executable,
                str(REPO_ROOT / "scripts/aggregate_java_web_dos_batch.py"),
                "--batch-root",
                str(output),
                "--format",
                "p0",
            ]
            returncode = _invoke_command(
                aggregate_command,
                cwd=REPO_ROOT,
                environment={
                    key: value
                    for key, value in provider_environment.items()
                    if key != "DEEPSEEK_API_KEY"
                },
                command_runner=command_runner,
            )
            if returncode != 0:
                return returncode or 1
            aggregate_gate = validate_p0_aggregate(output, run_id=arguments.run_id)
            acceptance = {
                "format": _ACCEPTANCE_FORMAT,
                "layer": arguments.layer,
                "selection_digest": selection["selection_digest"],
                "plan_digest": plan.plan_digest,
                **gate,
                **aggregate_gate,
            }
            _write_new_json(output / "acceptance_manifest.json", acceptance)
            print(output)
            return 0
        raise ValueError(f"acceptance layer is not implemented yet: {arguments.layer}")
    except (AnalyzerError, OSError, ValueError) as exc:
        message = exc.message if isinstance(exc, AnalyzerError) else str(exc)
        print(message, file=sys.stderr)
        return 1


__all__ = [
    "PAUSED_EXIT_STATUS",
    "build_poc33_selection",
    "build_poc33_input_manifest",
    "main",
    "validate_entries_archive",
]


if __name__ == "__main__":
    raise SystemExit(main())
