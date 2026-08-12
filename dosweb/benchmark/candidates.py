"""Candidate extraction from validated canonical P0 target artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from dosweb.artifacts.identifiers import canonical_json, file_sha256, sha256_canonical_json
from dosweb.artifacts.jsonl import read_jsonl_strict
from dosweb.artifacts.schemas import validate_records

_REQUIRED = {
    "entry_facts.jsonl": "entry_facts",
    "growth_candidates.jsonl": "growth_candidates",
    "flow_proofs.jsonl": "flow_proofs",
    "lifecycle_certificates.jsonl": "lifecycle_certificates",
    "static_findings.jsonl": "static_findings",
}
_VALID_VERDICTS = {
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
}


def _read_json(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing or unsafe artifact metadata: {path.name}")
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid artifact metadata: {path.name}")
    return value


def _artifact_paths(target_dir: Path, run: Mapping[str, Any]) -> dict[str, Path]:
    stages = run.get("stages")
    if not isinstance(stages, Mapping):
        raise ValueError("run stages are missing")
    found: dict[str, Path] = {}
    for stage, stage_run in stages.items():
        if not isinstance(stage, str) or not isinstance(stage_run, Mapping):
            raise ValueError("run stage is malformed")
        if stage_run.get("status") != "completed":
            continue
        manifest = _read_json(target_dir / ".stage-manifests" / f"{stage}.json")
        if manifest.get("stage") != stage or manifest.get("status") != "completed":
            raise ValueError("stage manifest binding mismatch")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or artifacts != stage_run.get("artifacts"):
            raise ValueError("stage artifact manifest mismatch")
        expected_output_hash = hashlib.sha256(canonical_json(artifacts)).hexdigest()
        if manifest.get("output_hash") != expected_output_hash:
            raise ValueError("stage output hash mismatch")
        for metadata in artifacts:
            if not isinstance(metadata, Mapping):
                raise ValueError("artifact metadata is malformed")
            raw_path = metadata.get("path")
            if not isinstance(raw_path, str):
                raise ValueError("artifact path is missing")
            relative = PurePosixPath(raw_path)
            if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
                raise ValueError("artifact path is unsafe")
            path = target_dir.joinpath(*relative.parts)
            if path.is_symlink() or not path.is_file():
                raise ValueError("artifact is missing")
            if metadata.get("sha256") != file_sha256(path):
                raise ValueError("artifact digest mismatch")
            data = path.read_bytes()
            if metadata.get("byte_count") != len(data):
                raise ValueError("artifact byte count mismatch")
            record_count = data.count(b"\n")
            if data and not data.endswith(b"\n"):
                record_count += 1
            if metadata.get("record_count") != record_count:
                raise ValueError("artifact record count mismatch")
            if path.name in _REQUIRED:
                if path.name in found:
                    raise ValueError("artifact is listed more than once")
                found[path.name] = path
    if set(found) != set(_REQUIRED):
        raise ValueError("required candidate artifacts are incomplete")
    return found


def extract_candidates_from_target(
    target_dir: Path,
    *,
    target_id: str,
    repository: str,
) -> tuple[list[dict[str, Any]], str | None]:
    run_path = target_dir / "run.json"
    if run_path.is_symlink() or not run_path.is_file():
        return [], "target_not_run"
    try:
        run = _read_json(run_path)
        if run.get("status") != "completed":
            return [], "target_not_run"
        paths = _artifact_paths(target_dir, run)
        records: dict[str, list[dict[str, object]]] = {}
        for filename, schema_name in _REQUIRED.items():
            rows = read_jsonl_strict(paths[filename], schema_name)
            validate_records(schema_name, rows)
            records[schema_name] = rows
    except Exception:
        # AnalyzerError from strict readers and schema validation is intentionally
        # collapsed into the benchmark's fail-closed artifact state.
        return [], "artifact_missing"

    entries = {row["entry_id"]: row for row in records["entry_facts"]}
    growth = {row["growth_id"]: row for row in records["growth_candidates"]}
    flows = {row["path_id"]: row for row in records["flow_proofs"]}
    certificates = {
        row["certificate_id"]: row
        for row in records["lifecycle_certificates"]
    }
    candidates: list[dict[str, Any]] = []
    for finding in records["static_findings"]:
        verdict = finding.get("verdict")
        if verdict not in _VALID_VERDICTS:
            return [], "artifact_missing"
        certificate = certificates.get(finding.get("certificate_id"))
        entry = entries.get(finding.get("entry_id"))
        growth_record = growth.get(finding.get("growth_id"))
        if certificate is None or entry is None or growth_record is None:
            return [], "artifact_missing"
        if certificate.get("entry_id") != finding.get("entry_id"):
            return [], "artifact_missing"
        if certificate.get("growth_id") != finding.get("growth_id"):
            return [], "artifact_missing"
        path_ids = certificate.get("path_ids")
        if not isinstance(path_ids, list) or not path_ids:
            return [], "artifact_missing"
        joined_flows = [flows.get(path_id) for path_id in path_ids]
        if any(flow is None for flow in joined_flows):
            return [], "artifact_missing"
        if any(
            flow.get("entry_id") != finding.get("entry_id")
            or flow.get("growth_id") != finding.get("growth_id")
            for flow in joined_flows
            if flow is not None
        ):
            return [], "artifact_missing"
        semantic = {
            "target_id": target_id,
            "finding_id": finding["finding_id"],
            "certificate_id": finding["certificate_id"],
        }
        candidates.append(
            {
                "candidate_id": "candidate:" + sha256_canonical_json(semantic)[:24],
                "target_id": target_id,
                "repository": repository,
                "verdict": verdict,
                "finding": finding,
                "certificate": certificate,
                "entry": entry,
                "growth": growth_record,
                "flows": joined_flows,
                "route_or_event": entry.get("route_or_event"),
                "protocol": entry.get("protocol"),
                "handler": entry.get("handler"),
                "resource_point": certificate.get("resource_point"),
                "locations": {
                    "handler": entry.get("handler"),
                    "growth": growth_record.get("site"),
                },
            }
        )
    candidates.sort(key=lambda item: item["candidate_id"])
    return candidates, None


def extract_candidates(
    batch_root: Path,
    target: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str | None]:
    output = target.get("output_path")
    identity = target.get("identity")
    if not isinstance(output, str) or not isinstance(identity, Mapping):
        return [], "target_not_run"
    relative = PurePosixPath(output)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return [], "artifact_missing"
    target_dir = batch_root / "targets" / relative.name
    repository = identity.get("name")
    target_id = target.get("target_id")
    if not isinstance(repository, str) or not isinstance(target_id, str):
        return [], "artifact_missing"
    return extract_candidates_from_target(
        target_dir,
        target_id=target_id,
        repository=repository,
    )
