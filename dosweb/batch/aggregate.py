"""Format-aware aggregation for historical and normative P0 batch outputs.

This module intentionally consumes only JSON/JSONL files.  It does not import the
pipeline or runner, so a batch archive can be checked independently of the code
that produced it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from dosweb.artifacts.schemas import validate_records, validate_references
from dosweb.batch.plan import load_batch_plan
from dosweb.batch.state import BatchState, batch_lock

STATIC_VERDICTS = frozenset({
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
})
FORMATS = frozenset({"historical", "p0"})
STAGES = ("entries", "growth", "flows", "lifecycle", "conclude", "report")
P0_ARTIFACTS = (
    "coverage.json",
    "entry_facts.jsonl",
    "growth_candidates.jsonl",
    "growth_contracts.jsonl",
    "verified_growth.jsonl",
    "flow_proofs.jsonl",
    "guard_candidates.jsonl",
    "bound_candidates.jsonl",
    "release_candidates.jsonl",
    "lifecycle_results.jsonl",
    "static_findings.jsonl",
    "lifecycle_certificates.jsonl",
    "summary.json",
    "report.md",
)
P0_JSONL_OUTPUTS = {
    "entry_facts.jsonl": "aggregate_entries.jsonl",
    "growth_candidates.jsonl": "aggregate_growth_candidates.jsonl",
    "growth_contracts.jsonl": "aggregate_growth_contracts.jsonl",
    "verified_growth.jsonl": "aggregate_verified_growth.jsonl",
    "flow_proofs.jsonl": "aggregate_flows.jsonl",
    "guard_candidates.jsonl": "aggregate_guard_candidates.jsonl",
    "bound_candidates.jsonl": "aggregate_bounds.jsonl",
    "release_candidates.jsonl": "aggregate_releases.jsonl",
    "lifecycle_results.jsonl": "aggregate_lifecycle_evidence.jsonl",
    "static_findings.jsonl": "aggregate_findings.jsonl",
    "lifecycle_certificates.jsonl": "aggregate_lifecycle_certificates.jsonl",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read historical JSONL strictly, preserving its old exception behavior."""
    rows, errors = _read_jsonl_accounted(path)
    if errors:
        raise ValueError(errors[0])
    return rows


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: expected a non-symlink regular file")
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def _read_jsonl_accounted(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return rows, errors
    if path.is_symlink() or not path.is_file():
        return rows, [f"{path}: expected a regular file"]
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    # Historical archives permit empty separators; P0 artifact
                    # manifests still account for records by their physical bytes.
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}:{line_no}: invalid JSON: {exc.msg}")
                    continue
                if not isinstance(value, dict):
                    errors.append(f"{path}:{line_no}: JSONL record must be an object")
                    continue
                rows.append(value)
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path}: cannot read file: {exc}")
    return rows, errors


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Write one output atomically; callers only invoke this after validation."""
    _atomic_write(path, _jsonl_bytes(rows))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _resolve(root: Path, raw: str, *, allow_absolute: bool = False) -> Path:
    """Resolve an archive path without following symlink components."""
    path = Path(raw)
    if path.is_absolute() and not allow_absolute:
        raise ValueError(f"unsafe absolute path: {raw}")
    if not path.is_absolute():
        if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"unsafe path outside batch root: {raw}")
        path = root / path
    elif any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe path: {raw}")
    # Check the lexical path first, then the resolved containment.  The first
    # check is what prevents a symlink from silently changing the archive root.
    current = Path(path.anchor) if path.anchor else root
    for part in path.parts[1:] if path.anchor else path.relative_to(root).parts:
        current = current / part
        try:
            if current.is_symlink():
                raise ValueError(f"unsafe symlink path component: {raw}")
        except OSError as exc:
            raise ValueError(f"cannot inspect path: {raw}") from exc
    resolved = path.resolve(strict=False)
    if not allow_absolute:
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"unsafe path outside batch root: {raw}") from exc
    return resolved


def _child(root: Path, *parts: str) -> Path:
    """Join a known archive child while rejecting symlinked parents."""
    return _resolve(root, str(Path(*parts)))


def _p0_identity(item: Mapping[str, Any]) -> Mapping[str, Any]:
    identity = item.get("identity")
    if not isinstance(identity, Mapping):
        return item
    return identity


def _target_meta(item: Mapping[str, Any], *, run_id: str | None = None, output_dir: str | None = None, plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    identity = _p0_identity(item)
    name = identity.get("name") or item.get("target") or item.get("slug") or item.get("target_id", "")
    result = {
        "batch_target_index": identity.get("index", item.get("index", "")),
        "batch_target_slug": identity.get("slug") or name,
        "batch_target_name": name,
        "batch_target_owner": name.split("/", 1)[0] if isinstance(name, str) and "/" in name else "",
        "batch_target_repository": name.split("/", 1)[1] if isinstance(name, str) and "/" in name else "",
        "batch_repo_path": identity.get("source_path") or item.get("repo_path", ""),
        "batch_database_path": identity.get("database_path", item.get("database_path", "")),
    }
    if plan is not None:
        result.update({"batch_plan_id": plan.get("plan_id", ""), "batch_plan_digest": plan.get("plan_digest", ""), "batch_mode": plan.get("mode", "")})
    historical_dir = item.get("hunter_output_dir") or item.get("output_dir")
    if historical_dir is not None:
        result["batch_hunter_output_dir"] = historical_dir
    if output_dir is not None:
        result["batch_output_dir"] = output_dir
    if run_id:
        result["batch_run_id"] = run_id
    return result


def validate_manifest(manifest: list[dict[str, Any]], manifest_path: Path, format: str = "historical") -> None:
    if format not in FORMATS:
        raise ValueError(f"unknown aggregation format {format!r}; expected historical or p0")
    if not manifest:
        raise ValueError(f"{manifest_path}: manifest contains no targets")
    if format == "historical":
        # A canonical archive must never be silently interpreted through the
        # compatibility reader, even when a caller explicitly requests it.
        markers = manifest_path.parent / "batch_plan.json", manifest_path.parent / "batch_state.json"
        if any(path.exists() for path in markers) or any(
            any(key in row for key in ("target_id", "identity", "capability", "initial_state", "output_path"))
            for row in manifest if isinstance(row, dict)
        ):
            raise ValueError("canonical batch markers are present; use format='p0'")
    seen: dict[str, int] = {}
    required = ("slug", "target", "repo_path", "hunter_output_dir") if format == "historical" else ("target_id", "identity", "output_path", "capability", "initial_state")
    for line_no, row in enumerate(manifest, 1):
        if not isinstance(row, dict):
            raise ValueError(f"{manifest_path}:{line_no}: manifest record must be an object")
        if format == "p0":
            identity = row.get("identity")
            if not isinstance(identity, dict) or not isinstance(identity.get("name"), str) or not isinstance(identity.get("slug"), str):
                raise ValueError(f"{manifest_path}:{line_no}: P0 manifest requires nested identity name and slug")
            if not isinstance(row.get("output_path"), str) or not row["output_path"]:
                raise ValueError(f"{manifest_path}:{line_no}: P0 manifest requires output_path")
        missing = [key for key in required if not isinstance(row.get(key), str) or not row[key].strip()] if format == "historical" else [key for key in required if key not in row]
        if missing:
            raise ValueError(f"{manifest_path}:{line_no}: missing required manifest fields: {', '.join(missing)}")
        slug = row.get("slug") if format == "historical" else row["identity"]["slug"]
        if slug in seen:
            raise ValueError(f"{manifest_path}:{line_no}: duplicate slug {slug}; first declared at line {seen[slug]}")
        seen[slug] = line_no


def target_meta(manifest_row: dict[str, Any]) -> dict[str, Any]:
    """Historical public helper retained for callers of the old script."""
    return _target_meta(manifest_row)


def add_meta(row: dict[str, Any], manifest_row: dict[str, Any], source_file: str) -> dict[str, Any]:
    return {**row, **target_meta(manifest_row), "batch_source_file": source_file}


def record_static_verdict(row: dict[str, Any], path: Path, line_no: int) -> str:
    aliases = [key for key in ("static_verdict", "static_status", "static_conclusion") if key in row]
    if aliases:
        raise ValueError(f"{path}:{line_no}: unsupported static verdict field alias {aliases[0]!r}; use 'verdict'")
    verdict = row.get("verdict")
    if not isinstance(verdict, str) or verdict not in STATIC_VERDICTS:
        raise ValueError(f"{path}:{line_no}: invalid static verdict {verdict!r}; expected one of {', '.join(sorted(STATIC_VERDICTS))}")
    return verdict


def read_findings(path: Path) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows, errors = _read_jsonl_accounted(path)
    if errors:
        raise ValueError(errors[0])
    counts: Counter[str] = Counter()
    physical_line = 0
    try:
        with path.open("r", encoding="utf-8") as stream:
            for physical_line, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    counts[f"verdict:{record_static_verdict(row, path, physical_line)}"] += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}:{physical_line}: invalid JSON: {exc}") from exc
    return rows, counts


def latest_status_by_slug(batch_root: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(batch_root / "batch_status.jsonl"):
        slug = row.get("slug")
        if not isinstance(slug, str) or not slug:
            raise ValueError(f"{batch_root / 'batch_status.jsonl'}: status record requires non-empty slug")
        latest[slug] = row
    return latest


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label}: expected a non-symlink regular file")


def _validate_artifact_metadata(root: Path, artifact: Any, *, stage: str) -> tuple[Path | None, str | None]:
    if not isinstance(artifact, dict):
        return None, f"{stage}: artifact entry must be an object"
    raw_path = artifact.get("path")
    if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute() or ".." in Path(raw_path).parts:
        return None, f"{stage}: artifact path is invalid: {raw_path!r}"
    schema_version = artifact.get("schema_version")
    if schema_version != "2.0":
        return None, f"{stage}:{raw_path}: schema_version must be '2.0'"
    digest = artifact.get("sha256")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        return None, f"{stage}:{raw_path}: sha256 is invalid"
    record_count = artifact.get("record_count")
    byte_count = artifact.get("byte_count")
    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count < 0:
        return None, f"{stage}:{raw_path}: record_count is invalid"
    if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
        return None, f"{stage}:{raw_path}: byte_count is invalid"
    try:
        path = _resolve(root, raw_path)
        stat = path.stat()
        if path.is_symlink() or not path.is_file() or stat.st_size != byte_count:
            return None, f"{stage}:{raw_path}: byte_count or file type mismatch"
        data = path.read_bytes()
        digest_actual = hashlib.sha256(data).hexdigest()
        if digest_actual != digest:
            return None, f"{stage}:{raw_path}: sha256 mismatch"
        actual_records = data.count(b"\n")
        if data and not data.endswith(b"\n"):
            actual_records += 1
        if actual_records != record_count:
            return None, f"{stage}:{raw_path}: record_count mismatch"
    except OSError as exc:
        return None, f"{stage}:{raw_path}: artifact is missing or unreadable: {exc}"
    return path, None


def _p0_target(item: dict[str, Any], batch_root: Path, *, plan: Mapping[str, Any], batch_state: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], list[str], list[str], Counter[str]]:
    output_raw = item.get("output_path")
    if not isinstance(output_raw, str) or not output_raw.strip():
        return _target_meta(item, plan=plan), {}, ["output_path"], [], Counter()
    try:
        output_dir = _resolve(batch_root, output_raw)
        # The runner resolves a plan output path to its deterministic target
        # leaf under <batch-root>/targets, so aggregation must use that same
        # target directory rather than joining the plan path verbatim.
        planned = plan.get("targets", [])
        planned_item = next((row for row in planned if isinstance(row, dict) and row.get("target_id") == item.get("target_id")), None)
        if not isinstance(planned_item, dict):
            raise ValueError("target is absent from canonical plan")
        output_path = PurePosixPath(output_raw)
        output_root = PurePosixPath(str(plan.get("output_root", "")))
        prefix = output_root.parts + ("targets",)
        planned_path = PurePosixPath(str(planned_item.get("output_path", "")))
        if planned_path.parts[: len(prefix)] != prefix or len(planned_path.parts) != len(prefix) + 1:
            raise ValueError("canonical plan output_path is outside output_root/targets layout")
        if output_path != planned_path:
            raise ValueError("manifest output_path differs from canonical plan")
        relative_target = PurePosixPath(*planned_path.parts[len(output_root.parts):])
        if relative_target.parts[:1] != ("targets",) or len(relative_target.parts) != 2:
            raise ValueError("canonical output_path must use targets/<leaf> layout")
        leaf = relative_target.name
        if not leaf or leaf in {".", ".."}:
            raise ValueError("canonical output_path has no target leaf")
        output_dir = _resolve(batch_root, f"targets/{leaf}")
    except ValueError as exc:
        return _target_meta(item, plan=plan), {}, [], [str(exc)], Counter()
    binding_path = output_dir / "batch_target.json"
    if binding_path.is_symlink() or not binding_path.is_file():
        return _target_meta(item, output_dir=str(output_dir), plan=plan), {}, ["batch_target.json"], [], Counter()
    try:
        binding = _read_json(binding_path)
    except ValueError as exc:
        return _target_meta(item, output_dir=str(output_dir), plan=plan), {}, [], [str(exc)], Counter()
    expected_binding = {"plan_id": plan.get("plan_id"), "plan_digest": plan.get("plan_digest"), "run_id": plan.get("run_id"), "mode": plan.get("mode"), "target": item}
    legacy_binding = {"run_id": plan.get("run_id"), "target": item}
    binding_ok = binding == expected_binding if plan.get("plan_digest") else binding == legacy_binding
    if not isinstance(binding, dict) or not binding_ok:
        return _target_meta(item, output_dir=str(output_dir), plan=plan), {}, [], [f"{binding_path}: target/plan/run/mode binding mismatch"], Counter()
    target_id = item.get("target_id")
    target_state = batch_state.get("targets", {}).get(target_id) if isinstance(batch_state.get("targets"), dict) else None
    if not isinstance(target_state, dict) or target_state.get("state") not in {"completed", "completed_with_gaps"}:
        return _target_meta(item, output_dir=str(output_dir), plan=plan), {}, [], [f"{batch_root / 'batch_state.json'}: target is not terminal-complete"], Counter()
    meta = _target_meta(item, output_dir=str(output_dir), plan=plan)
    missing: list[str] = []
    malformed: list[str] = []
    artifacts_by_name: dict[str, list[dict[str, Any]]] = {}
    run_path = output_dir / "run.json"
    if run_path.is_symlink() or not run_path.is_file():
        missing.append("run.json")
        return meta, artifacts_by_name, missing, malformed, Counter()
    try:
        run = _read_json(run_path)
    except (FileNotFoundError, ValueError) as exc:
        malformed.append(str(exc))
        return meta, artifacts_by_name, missing, malformed, Counter()
    if not isinstance(run, dict):
        malformed.append(f"{run_path}: expected JSON object")
        return meta, artifacts_by_name, missing, malformed, Counter()
    run_id = run.get("run_id")
    if isinstance(run_id, str) and run_id:
        meta["batch_run_id"] = run_id
    if run.get("status") != "completed":
        malformed.append(f"{run_path}: status must be 'completed'")
    stages = run.get("stages")
    if not isinstance(stages, dict):
        malformed.append(f"{run_path}: stages must be an object")
        stages = {}
    stage_manifest_root = output_dir / ".stage-manifests"
    if stage_manifest_root.is_symlink() or not stage_manifest_root.is_dir():
        malformed.append(f"{stage_manifest_root}: stage manifest directory must be a non-symlink directory")
    for stage in STAGES:
        stage_meta = stages.get(stage)
        stage_manifest_path = stage_manifest_root / f"{stage}.json"
        if not isinstance(stage_meta, dict) or stage_meta.get("status") != "completed":
            malformed.append(f"{run_path}: stage {stage} is not completed")
            continue
        if stage_manifest_path.is_symlink() or not stage_manifest_path.is_file():
            missing.append(f".stage-manifests/{stage}.json")
            continue
        try:
            stage_manifest = _read_json(stage_manifest_path)
        except ValueError as exc:
            malformed.append(str(exc))
            continue
        if not isinstance(stage_manifest, dict):
            malformed.append(f"{stage_manifest_path}: expected JSON object")
            continue
        if stage_manifest.get("stage") != stage or stage_manifest.get("status") != "completed":
            malformed.append(f"{stage_manifest_path}: stage/status mismatch")
        artifacts = stage_manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            malformed.append(f"{stage_manifest_path}: completed stage must list artifacts")
            continue
        expected_hash = hashlib.sha256(json.dumps(artifacts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if stage_manifest.get("output_hash") != expected_hash:
            malformed.append(f"{stage_manifest_path}: output_hash mismatch")
        run_artifacts = stage_meta.get("artifacts")
        if run_artifacts != artifacts:
            malformed.append(f"{run_path}: stage {stage} artifact list differs from stage manifest")
        for artifact in artifacts:
            path, error = _validate_artifact_metadata(output_dir, artifact, stage=stage)
            if error:
                malformed.append(error)
                continue
            assert path is not None
            name = path.name
            if name not in P0_ARTIFACTS:
                malformed.append(f"{stage}:{name}: unexpected artifact")
                continue
            artifacts_by_name.setdefault(name, []).append({"path": path, "metadata": artifact})
    for name in P0_ARTIFACTS:
        if name not in artifacts_by_name:
            missing.append(name)
        elif len(artifacts_by_name[name]) != 1:
            malformed.append(f"{name}: artifact must be listed exactly once")
    counts: Counter[str] = Counter()
    parsed_rows: dict[str, list[dict[str, Any]]] = {}
    for name, refs in artifacts_by_name.items():
        path = refs[0]["path"]
        if name.endswith(".jsonl"):
            rows, errors = _read_jsonl_accounted(path)
            if errors:
                malformed.extend(errors)
            parsed_rows[name.removesuffix(".jsonl")] = rows
            try:
                validate_records(name.removesuffix(".jsonl"), rows)
            except Exception as exc:
                malformed.append(f"{name}: artifact schema validation failed: {exc}")
            counts[name] = len(rows)
            if name == "static_findings.jsonl":
                for line_no, row in enumerate(rows, 1):
                    try:
                        counts[f"verdict:{record_static_verdict(row, path, line_no)}"] += 1
                    except ValueError as exc:
                        malformed.append(str(exc))
        elif name.endswith(".json"):
            try:
                value = _read_json(path)
                if not isinstance(value, (dict, list)):
                    malformed.append(f"{path}: expected JSON object or array")
            except ValueError as exc:
                malformed.append(str(exc))
    if parsed_rows:
        known: dict[str, Any] = {"fact_id": set()}
        def collect_fact_ids(value: Any) -> None:
            if isinstance(value, Mapping):
                for key, nested in value.items():
                    if key.endswith("_id") and isinstance(nested, str) and nested.startswith("fact:"):
                        known["fact_id"].add(nested)
                    collect_fact_ids(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect_fact_ids(nested)
        for rows in parsed_rows.values():
            collect_fact_ids(rows)
        for schema_name, rows in parsed_rows.items():
            if schema_name in {"entry_facts", "growth_candidates", "growth_contracts", "verified_growth", "flow_proofs", "guard_candidates", "bound_candidates", "release_candidates", "lifecycle_results", "static_findings", "lifecycle_certificates"}:
                id_field = {"entry_facts": "entry_id", "growth_candidates": "growth_id", "growth_contracts": "growth_contract_id", "verified_growth": "verified_growth_id", "flow_proofs": "path_id", "guard_candidates": "guard_id", "bound_candidates": "bound_id", "release_candidates": "release_id", "lifecycle_results": "lifecycle_result_id", "static_findings": "finding_id", "lifecycle_certificates": "certificate_id"}[schema_name]
                known.setdefault(id_field, set()).update(row.get(id_field) for row in rows if isinstance(row.get(id_field), str))
        growth_fact_ids: dict[str, set[str]] = {}
        for row in parsed_rows.get("growth_candidates", []):
            if isinstance(row.get("growth_id"), str):
                growth_fact_ids[row["growth_id"]] = {value for value in row.get("candidate_evidence", []) if isinstance(value, str)}
        known["growth_fact_ids"] = growth_fact_ids
        for schema_name, rows in parsed_rows.items():
            if not rows or schema_name not in known:
                continue
            try:
                validate_references(schema_name, rows, known)
            except Exception as exc:
                malformed.append(f"{schema_name}: semantic schema/reference validation failed: {exc}")
    return meta, artifacts_by_name, sorted(set(missing)), malformed, counts


def _aggregate_p0(batch_root: Path, manifest: list[dict[str, Any]]) -> None:
    plan_path = batch_root / "batch_plan.json"
    state_path = batch_root / "batch_state.json"
    if not plan_path.is_file() or not state_path.is_file():
        raise ValueError("P0 aggregation requires batch_plan.json and batch_state.json")
    raw_plan = _read_json(plan_path)
    batch_state = _read_json(state_path)
    if not isinstance(raw_plan, dict) or not isinstance(batch_state, dict):
        raise ValueError("P0 plan/state must be JSON objects")
    # P0 is normative: never downgrade a malformed or incomplete canonical
    # plan to the pre-P0 compatibility interpretation.
    try:
        loaded_plan = load_batch_plan(plan_path)
    except Exception as exc:
        raise ValueError(f"batch_plan.json identity/digest validation failed: {exc}") from exc
    if not loaded_plan.verify_digest() or loaded_plan.mode not in {"entries", "full"}:
        raise ValueError("batch_plan.json digest or mode is invalid")
    plan = loaded_plan.to_dict()
    if not isinstance(plan.get("inventory_digest"), str) or not _DIGEST.fullmatch(plan["inventory_digest"]):
        raise ValueError("batch_plan.json inventory_digest is invalid")
    canonical_plan = True
    if plan.get("status") not in (None, "planned", "running", "completed"):
        raise ValueError("P0 batch plan status is invalid")
    plan_targets = plan.get("targets")
    if not isinstance(plan_targets, list):
        raise ValueError("P0 batch plan targets must be an array")
    plan_by_id = {row.get("target_id"): row for row in plan_targets if isinstance(row, dict) and isinstance(row.get("target_id"), str)}
    manifest_by_id = {row.get("target_id"): row for row in manifest if isinstance(row, dict) and isinstance(row.get("target_id"), str)}
    if len(plan_by_id) != len(plan_targets) or len(manifest_by_id) != len(manifest):
        raise ValueError("P0 plan or manifest contains malformed or duplicate target ids")
    plan_order = [row["target_id"] for row in plan_targets]
    manifest_order = [row["target_id"] for row in manifest]
    if plan_order != manifest_order:
        raise ValueError("P0 manifest target order does not match batch_plan.json")
    if set(plan_by_id) != set(manifest_by_id):
        raise ValueError("P0 manifest and batch_plan target sets differ")
    for target_id, item in manifest_by_id.items():
        if plan_by_id[target_id] != item:
            raise ValueError(f"P0 manifest target {target_id!r} does not match batch_plan.json")
    if canonical_plan:
        state_required = {"schema_version", "batch_id", "mode", "status", "created_at", "updated_at", "targets"}
        state_targets = batch_state.get("targets")
        if set(batch_state) != state_required or batch_state.get("batch_id") != plan.get("plan_id") or batch_state.get("mode") != plan.get("mode") or not isinstance(state_targets, dict) or set(state_targets) != set(plan_by_id):
            raise ValueError("batch_state.json identity/mode/target set does not match batch_plan.json")
        try:
            BatchState.from_dict(batch_state)
        except ValueError as exc:
            raise ValueError(f"batch_state.json schema validation failed: {exc}") from exc
    aggregate_rows: dict[str, list[dict[str, Any]]] = {output: [] for output in P0_JSONL_OUTPUTS.values()}
    status_rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    target_outputs: list[tuple[dict[str, Any], dict[str, list[dict[str, Any]]], bool]] = []
    for item in manifest:
        meta, refs, missing, malformed, counts = _p0_target(item, batch_root, plan=plan, batch_state=batch_state)
        status = "completed" if not missing and not malformed else "malformed" if malformed else "missing"
        target_id = item.get("target_id")
        authoritative = batch_state.get("targets", {}).get(target_id, {}) if isinstance(batch_state.get("targets"), dict) else {}
        record = {
            **meta, "status": status,
            "authoritative_status": authoritative.get("status", authoritative.get("state")),
            "failure_reason": authoritative.get("error_message") or authoritative.get("error_code"),
            "missing_artifacts": missing, "missing_files": missing,
            "malformed_artifacts": malformed, "malformed": malformed,
            "counts": dict(counts),
            "verdict_counts": {key.removeprefix("verdict:"): value for key, value in counts.items() if key.startswith("verdict:")},
        }
        status_rows.append(record)
        if status == "completed":
            totals.update(counts)
        target_outputs.append((meta, refs, status == "completed"))
    for meta, refs, complete in target_outputs:
        if not complete:
            continue
        for name, output in P0_JSONL_OUTPUTS.items():
            if name not in refs:
                continue
            path = refs[name][0]["path"]
            rows, errors = _read_jsonl_accounted(path)
            if errors:
                continue
            aggregate_rows[output].extend({**row, **meta, "batch_source_file": name} for row in rows)
    _publish_outputs(batch_root, aggregate_rows, status_rows, totals, manifest, format="p0")


def _aggregate_historical(batch_root: Path, manifest: list[dict[str, Any]]) -> None:
    required_files = ["summary.md", "target_profile.json", "sinks.jsonl", "sources.jsonl", "flows.jsonl", "findings.jsonl", "rejected.jsonl", "subagent_reviews.jsonl", "gaps.md"]
    source_outputs = {"sinks.jsonl": "aggregate_sinks.jsonl", "sources.jsonl": "aggregate_sources.jsonl", "flows.jsonl": "aggregate_flows.jsonl", "findings.jsonl": "aggregate_findings.jsonl", "rejected.jsonl": "aggregate_rejected.jsonl", "subagent_reviews.jsonl": "aggregate_subagent_reviews.jsonl"}
    aggregate_rows = {output: [] for output in source_outputs.values()}
    profiles: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    gap_sections = ["# Aggregate Gaps", ""]
    prior_statuses = latest_status_by_slug(batch_root)
    for item in manifest:
        directory = _resolve(batch_root, item["hunter_output_dir"], allow_absolute=True)
        missing = [name for name in required_files if (directory / name).is_symlink() or not (directory / name).is_file()]
        counts: Counter[str] = Counter()
        prior = prior_statuses.get(item["slug"], {})
        prior_status = prior.get("status")
        contributes = prior_status in {None, "completed", "completed_with_gaps"}
        if not missing:
            try:
                profile = _read_json(directory / "target_profile.json")
                if not isinstance(profile, dict):
                    raise ValueError(f"{directory / 'target_profile.json'}: expected JSON object")
                if contributes:
                    profiles.append(add_meta(profile, item, "target_profile.json"))
                for source, output in source_outputs.items():
                    rows, errors = _read_jsonl_accounted(directory / source)
                    if errors:
                        raise ValueError(errors[0])
                    if source == "findings.jsonl" and contributes:
                        _finding_rows, verdict_counts = read_findings(directory / source)
                        totals.update(verdict_counts)
                    counts[source] = len(rows)
                    if contributes:
                        aggregate_rows[output].extend(add_meta(row, item, source) for row in rows)
            except ValueError:
                raise
        status = str(prior_status or ("failed" if missing else "completed"))
        if missing and status not in {"queued", "running", "retrying", "paused", "skipped", "failed", "completed_with_gaps"}:
            status = "failed"
        gap_path = directory / "gaps.md"
        if gap_path.is_file() and not gap_path.is_symlink():
            gap_text = gap_path.read_text(encoding="utf-8").strip()
            if gap_text:
                gap_sections.extend([f"## {item.get('target', item.get('slug', 'unknown'))}", "", gap_text, ""])
        statuses.append({**target_meta(item), "status": status, "failure_reason": prior.get("failure_reason", item.get("failure_reason")), "missing_files": missing, "missing_artifacts": missing, "malformed": [], "malformed_artifacts": [], "counts": dict(counts)})
    _publish_outputs(batch_root, aggregate_rows, statuses, totals, manifest, format="historical", profiles=profiles, historical_gaps="\n".join(gap_sections).rstrip() + "\n")


def _recover_publication(batch_root: Path) -> None:
    """Repair compatibility root files after pointer/root partial publication."""
    pointer = batch_root / ".aggregate-current.json"
    if pointer.is_symlink() or not pointer.is_file():
        return
    try:
        document = _read_json(pointer)
        manifest_path = _resolve(batch_root, str(document["manifest"]))
        generation = _read_json(manifest_path)
        files = generation["files"]
        if not isinstance(files, dict):
            return
        generation_dir = manifest_path.parent
        for name, digest in files.items():
            if not isinstance(name, str) or Path(name).name != name or not isinstance(digest, str):
                return
            source = generation_dir / name
            if source.is_symlink() or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                return
        for name in files:
            source = generation_dir / name
            destination = batch_root / name
            if destination.is_symlink() or not destination.is_file() or hashlib.sha256(destination.read_bytes()).hexdigest() != files[name]:
                _atomic_write(destination, source.read_bytes())
    except (OSError, TypeError, KeyError, ValueError):
        return


def _publish_outputs(batch_root: Path, aggregate_rows: dict[str, list[dict[str, Any]]], statuses: list[dict[str, Any]], totals: Counter[str], manifest: list[dict[str, Any]], *, format: str, profiles: list[dict[str, Any]] | None = None, historical_gaps: str | None = None) -> None:
    with batch_lock(batch_root / ".aggregate.lock"):
        _recover_publication(batch_root)
        _publish_outputs_unlocked(batch_root, aggregate_rows, statuses, totals, manifest, format=format, profiles=profiles, historical_gaps=historical_gaps)


def _publish_outputs_unlocked(batch_root: Path, aggregate_rows: dict[str, list[dict[str, Any]]], statuses: list[dict[str, Any]], totals: Counter[str], manifest: list[dict[str, Any]], *, format: str, profiles: list[dict[str, Any]] | None = None, historical_gaps: str | None = None) -> None:
    outputs: dict[str, bytes] = {}
    if profiles is not None:
        outputs["aggregate_target_profiles.jsonl"] = _jsonl_bytes(profiles)
    for name, rows in aggregate_rows.items():
        outputs[name] = _jsonl_bytes(rows)
    outputs["aggregate_status.jsonl"] = _jsonl_bytes(statuses)
    gaps = [row for row in statuses if row.get("status") != "completed"]
    inventory = {"batch_root": str(batch_root), "format": format, "targets": statuses, "status_counts": dict(Counter(row["status"] for row in statuses)), "totals": dict(totals), "verdict_counts": {key.removeprefix("verdict:"): value for key, value in totals.items() if key.startswith("verdict:")}}
    outputs["aggregate_inventory.json"] = (json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    summary = ["# Java Web DoS Static Batch Summary", "", f"Format: `{format}`", "", "## Status", ""]
    summary.extend(f"- {key}: {value}" for key, value in sorted(inventory["status_counts"].items()))
    summary.extend(["", "## Targets", "", f"- targets: {len(manifest)}"])
    for verdict in sorted(STATIC_VERDICTS):
        summary.append(f"- {verdict}: {totals[f'verdict:{verdict}']}")
    outputs["batch_summary.md"] = ("\n".join(summary) + "\n").encode()
    gap_lines = ["# Aggregate Gaps", ""]
    if not gaps:
        gap_lines.append("No target gaps.")
    else:
        for row in gaps:
            gap_lines.append(f"- `{row.get('batch_target_name', row.get('batch_target_slug', 'unknown'))}`: {row.get('status')}; missing={row.get('missing_artifacts', [])}; malformed={row.get('malformed_artifacts', [])}")
    outputs["aggregate_gaps.md"] = (historical_gaps if historical_gaps is not None else "\n".join(gap_lines) + "\n").encode()
    quality = {
        "format": format, "target_count": len(manifest), "completed": inventory["status_counts"].get("completed", 0),
        "gap_count": len(gaps), "malformed_target_count": inventory["status_counts"].get("malformed", 0),
        "missing_target_count": inventory["status_counts"].get("missing", 0), "verdict_counts": inventory["verdict_counts"],
    }
    outputs["batch_quality_report.md"] = ("# Batch Quality Report\n\n" + "\n".join(f"- {key}: {value}" for key, value in quality.items()) + "\n").encode()
    for name, data in outputs.items():
        if not isinstance(data, bytes) or not name or Path(name).name != name:
            raise ValueError(f"invalid aggregate output {name!r}")

    owner = batch_root / ".aggregate-owned.json"
    owned = False
    prior_files: dict[str, str] = {}
    if owner.exists():
        if not owner.is_file() or owner.is_symlink():
            raise ValueError(".aggregate-owned.json is not a regular file")
        try:
            owned = _read_json(owner) == {"owner": "dosweb.batch.aggregate", "version": 1}
        except ValueError:
            owned = False
        if not owned:
            raise ValueError(".aggregate-owned.json is not provably owned by this aggregator")
    compatibility_paths = [batch_root / name for name in outputs]
    current_path = batch_root / ".aggregate-current.json"
    compatibility_paths.append(current_path)
    if not owned:
        unknown = [path for path in compatibility_paths if path.exists()]
        if unknown:
            raise ValueError(f"refusing to replace unknown pre-existing aggregate output: {unknown[0]}")
    else:
        # Ownership is attested by the marker and the prior generation manifest;
        # a newly introduced or tampered root file must still fail closed.
        try:
            pointer = _read_json(current_path)
            manifest_raw = pointer.get("manifest")
            if not isinstance(manifest_raw, str):
                raise ValueError("aggregate pointer manifest is invalid")
            manifest_path = _resolve(batch_root, manifest_raw)
            if manifest_path.parent.parent != (batch_root / ".aggregate-generations").resolve():
                raise ValueError("aggregate pointer escapes generation root")
            generation_manifest = _read_json(manifest_path)
            prior_files = generation_manifest["files"]
            if not isinstance(prior_files, dict):
                raise ValueError("generation files missing")
            prior_format = generation_manifest.get("format")
            if prior_format not in FORMATS:
                raise ValueError("generation format is invalid")
            for path in compatibility_paths[:-1]:
                if path.exists():
                    prior_digest = prior_files.get(path.name)
                    staged_digest = hashlib.sha256(outputs[path.name]).hexdigest() if path.name in outputs else None
                    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() not in {prior_digest, staged_digest}:
                        raise ValueError(f"refusing to replace unowned or tampered aggregate output: {path}")
            if prior_format != format:
                stale = [batch_root / name for name in prior_files if name not in outputs and (batch_root / name).exists()]
                if stale:
                    raise ValueError(f"format switch would leave owned stale output; refusing without deletion: {stale[0]}")
        except (KeyError, TypeError, ValueError, OSError) as exc:
            if any(path.exists() for path in compatibility_paths[:-1]):
                raise ValueError("cannot prove ownership of existing aggregate outputs") from exc

    generation_root = batch_root / ".aggregate-generations"
    generation_root.mkdir(parents=True, exist_ok=True)
    generation = f"generation-{uuid.uuid4().hex}"
    pending = Path(tempfile.mkdtemp(prefix=".pending-", dir=generation_root))
    try:
        for name, data in outputs.items():
            _atomic_write(pending / name, data)
        generation_manifest = {"generation": generation, "format": format, "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(outputs.items())}}
        _atomic_write(pending / "generation_manifest.json", (json.dumps(generation_manifest, sort_keys=True, indent=2) + "\n").encode())
        published = generation_root / generation
        os.replace(pending, published)
        pending = published
        # Compatibility files are the externally consumed view. Publish them
        # before advancing the pointer, so a crash leaves a recoverable prior
        # generation rather than a pointer to an unpublished generation.
        staged_hashes = generation_manifest["files"]
        for name, data in outputs.items():
            destination = batch_root / name
            if destination.exists() and (destination.is_symlink() or not destination.is_file()):
                raise ValueError(f"aggregate output is not a regular file: {destination}")
            _atomic_write(destination, data)
        pointer = {"generation": generation, "manifest": f".aggregate-generations/{generation}/generation_manifest.json"}
        _atomic_write(batch_root / ".aggregate-current.json", (json.dumps(pointer, sort_keys=True, indent=2) + "\n").encode())
        _atomic_write(owner, b'{"owner":"dosweb.batch.aggregate","version":1}\n')
    finally:
        if pending.name.startswith(".pending-"):
            import shutil
            shutil.rmtree(pending, ignore_errors=True)


def aggregate(batch_root: Path, format: str = "historical", *, p0: bool | None = None) -> None:
    """Aggregate one batch using an explicit ``historical`` or ``p0`` contract."""
    if p0 is not None:
        if format != "historical":
            raise ValueError("use either format or p0, not both")
        format = "p0" if p0 else "historical"
    if format not in FORMATS:
        raise ValueError(f"unknown aggregation format {format!r}; expected historical or p0")
    batch_root = Path(batch_root).resolve()
    manifest_path = batch_root / "manifest.normalized.jsonl"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError(f"missing required normalized manifest: {manifest_path}")
    manifest = read_jsonl(manifest_path)
    validate_manifest(manifest, manifest_path, format)
    if format == "p0":
        _aggregate_p0(batch_root, manifest)
    else:
        _aggregate_historical(batch_root, manifest)
