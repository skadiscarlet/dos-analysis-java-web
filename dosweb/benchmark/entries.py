"""Strict entry-stage extraction for PoC-29 benchmark diagnostics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from dosweb.artifacts.identifiers import canonical_json, file_sha256
from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.schemas import SCHEMA_VERSION, validate_records
from dosweb.batch.plan import load_batch_plan
from dosweb.entries.models import FrameworkCoverage

_LEGACY_ENTRY_ARTIFACTS = {"coverage.json", "entry_facts.jsonl"}
_CURRENT_ENTRY_ARTIFACTS = {
    "coverage.json", "entry_facts.jsonl", "entry_gap_facts.jsonl",
    "entry_interposition_facts.jsonl", "configuration_coverage.json",
    "modeled_configuration.jsonl", "entry_security_facts.jsonl",
}


def _read_object(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing or unsafe JSON artifact: {path.name}")
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON artifact is not an object: {path.name}")
    return value


def _record_count(path: Path) -> int:
    data = path.read_bytes()
    count = data.count(b"\n")
    if data and not data.endswith(b"\n"):
        count += 1
    return count


def _safe_artifact(target_dir: Path, metadata: Mapping[str, Any], *, schema_version: str) -> Path:
    raw_path = metadata.get("path")
    if not isinstance(raw_path, str):
        raise ValueError("entry artifact path is missing")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("entry artifact path is unsafe")
    path = target_dir.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        raise ValueError("entry artifact is missing")
    if metadata.get("sha256") != file_sha256(path):
        raise ValueError("entry artifact digest mismatch")
    if metadata.get("byte_count") != path.stat().st_size:
        raise ValueError("entry artifact byte count mismatch")
    if metadata.get("record_count") != _record_count(path):
        raise ValueError("entry artifact record count mismatch")
    if metadata.get("schema_version") != schema_version:
        raise ValueError("entry artifact schema version mismatch")
    return path


def _entry_paths(target_dir: Path, run: Mapping[str, Any], *, target_id: str, repository: str) -> dict[str, Path]:
    binding = _read_object(target_dir / "batch_target.json")
    bound_target = binding.get("target")
    if not isinstance(bound_target, Mapping) or bound_target.get("target_id") != target_id:
        raise ValueError("target binding mismatch")
    identity = bound_target.get("identity")
    if not isinstance(identity, Mapping) or identity.get("name") != repository:
        raise ValueError("target identity mismatch")
    if binding.get("mode") != "entries" or not isinstance(binding.get("plan_id"), str) or not isinstance(binding.get("plan_digest"), str):
        raise ValueError("batch target binding is malformed")
    plan = load_batch_plan(target_dir.parent.parent / "batch_plan.json")
    if binding.get("plan_id") != plan.plan_id or binding.get("plan_digest") != plan.plan_digest:
        raise ValueError("batch target plan binding mismatch")
    bound_plan_target = next((item for item in plan.targets if item.target_id == target_id), None)
    if bound_plan_target is None or bound_plan_target.to_dict() != dict(bound_target):
        raise ValueError("batch target plan target mismatch")
    stages = run.get("stages")
    if not isinstance(stages, Mapping):
        raise ValueError("run stages are missing")
    stage_run = stages.get("entries")
    if not isinstance(stage_run, Mapping) or stage_run.get("status") != "completed":
        raise ValueError("entry stage is not completed")
    manifest = _read_object(target_dir / ".stage-manifests" / "entries.json")
    if manifest.get("stage") != "entries" or manifest.get("status") != "completed":
        raise ValueError("entry stage manifest is incomplete")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or artifacts != stage_run.get("artifacts"):
        raise ValueError("entry stage artifact manifest mismatch")
    if manifest.get("output_hash") != hashlib.sha256(canonical_json(artifacts)).hexdigest():
        raise ValueError("entry stage output hash mismatch")
    artifact_names = {item.get("path") for item in artifacts if isinstance(item, Mapping)}
    if artifact_names == _LEGACY_ENTRY_ARTIFACTS:
        expected_artifacts, schema_version = _LEGACY_ENTRY_ARTIFACTS, "2.0"
    elif artifact_names == _CURRENT_ENTRY_ARTIFACTS:
        expected_artifacts, schema_version = _CURRENT_ENTRY_ARTIFACTS, SCHEMA_VERSION
    else:
        raise ValueError("entry stage artifact set mismatch")
    found: dict[str, Path] = {}
    for item in artifacts:
        if not isinstance(item, Mapping):
            raise ValueError("entry artifact metadata is malformed")
        path = _safe_artifact(target_dir, item, schema_version=schema_version)
        if path.name in found:
            raise ValueError("entry artifact is listed more than once")
        found[path.name] = path
    if set(found) != expected_artifacts:
        raise ValueError("entry stage artifacts are incomplete")
    return found


def _coverage_records(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("coverage artifact must be a list")
    result: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise ValueError("coverage row is malformed")
        coverage = FrameworkCoverage(
            row.get("framework"),
            row.get("status"),
            tuple(row.get("supported_patterns", [])),
            tuple(row.get("unsupported_patterns", [])),
            row.get("effect_on_verdict"),
        )
        result.append(coverage.to_dict())
    return result


def extract_entries_from_target(
    target_dir: Path,
    *,
    target_id: str,
    repository: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Read only the completed entries stage; later P0 artifacts are irrelevant."""
    run_path = target_dir / "run.json"
    if run_path.is_symlink() or not run_path.is_file():
        return [], [], "target_not_run"
    try:
        run = _read_object(run_path)
        if run.get("status") != "completed":
            return [], [], "target_not_run"
        paths = _entry_paths(target_dir, run, target_id=target_id, repository=repository)
        coverage = _coverage_records(paths["coverage.json"])
        facts = read_jsonl_strict(paths["entry_facts.jsonl"], "entry_facts")
        validate_records("entry_facts", facts)
    except Exception:
        return [], [], "artifact_missing"
    gaps = [
        {"framework": row["framework"], "status": row["status"], "unsupported_patterns": row["unsupported_patterns"], "effect_on_verdict": row["effect_on_verdict"]}
        for row in coverage
        if row["status"] != "complete"
    ]
    entries = [
        {"target_id": target_id, "repository": repository, "entry": row}
        for row in facts
    ]
    return entries, gaps, None


def extract_entries(batch_root: Path, target: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    output = target.get("output_path")
    identity = target.get("identity")
    target_id = target.get("target_id")
    if not isinstance(output, str) or not isinstance(identity, Mapping) or not isinstance(target_id, str):
        return [], [], "target_not_run"
    relative = PurePosixPath(output)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return [], [], "artifact_missing"
    repository = identity.get("name")
    if not isinstance(repository, str):
        return [], [], "artifact_missing"
    return extract_entries_from_target(batch_root / "targets" / relative.name, target_id=target_id, repository=repository)
