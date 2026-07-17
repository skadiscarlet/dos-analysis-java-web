#!/usr/bin/env python3
"""Atomically sync an opt-in dynamic-validation status index from local evidence files."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


MANIFEST_NAME = "manifest.normalized.jsonl"
STATUS_NAME = "validation_status.jsonl"
CASE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
ALLOWED_STATUS_VERDICTS = {
    "paused": {"blocked"},
    "completed": {"confirmed", "not_confirmed", "blocked"},
    "failed": {"blocked", "unknown"},
    "environment_blocked": {"blocked"},
}


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r} is not allowed")


def json_loads_strict(value: str, location: str) -> Any:
    try:
        return json.loads(value, parse_constant=reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{location}: invalid JSON: {exc.msg}") from exc
    except ValueError as exc:
        raise ValueError(f"{location}: invalid JSON: {exc}") from exc


def json_dumps_strict(value: Any, **kwargs: Any) -> str:
    return json.dumps(value, allow_nan=False, **kwargs)


@contextlib.contextmanager
def output_lock(output_root: Path):
    lock_path = output_root.parent / f".{output_root.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json_loads_strict(path.read_text(encoding="utf-8"), str(path))
    except FileNotFoundError as exc:
        raise ValueError(f"missing result file: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                data = json_loads_strict(stripped, f"{path}:{line_no}")
                if not isinstance(data, dict):
                    raise ValueError(f"{path}:{line_no}: expected JSON object")
                case_id = data.get("case_id")
                if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id) or case_id in {".", ".."}:
                    raise ValueError(f"{path}:{line_no}: invalid case_id; expected a safe filename component")
                rows.append((line_no, data))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required normalized manifest: {path}") from exc
    return rows


def write_jsonl_atomically(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write status to a same-directory temporary file, then atomically replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", prefix=f".{path.name}.", dir=path.parent, delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            for row in rows:
                handle.write(json_dumps_strict(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temporary_path, path.stat().st_mode & 0o777)
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise RuntimeError(f"failed to atomically replace {path}: {exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def sync(output_root: Path) -> None:
    """Create a status-only index; this does not run probes or modify case evidence."""
    output_root = output_root.resolve()
    with output_lock(output_root):
        sync_locked(output_root)


def sync_locked(output_root: Path) -> None:
    manifest_rows = read_jsonl(output_root / MANIFEST_NAME)
    status_rows: list[dict[str, Any]] = []
    observed_case_ids: dict[str, int] = {}
    cases_path = output_root / "cases"
    if cases_path.is_symlink() or not cases_path.is_dir():
        raise ValueError(f"{cases_path}: missing cases directory or symbolic links are not allowed")
    cases_root = cases_path.resolve()
    for line_no, manifest in manifest_rows:
        case_id = manifest["case_id"]
        if case_id in observed_case_ids:
            raise ValueError(
                f"{output_root / MANIFEST_NAME}:{line_no}: duplicate case_id {case_id!r}; "
                f"first declared at line {observed_case_ids[case_id]}"
            )
        observed_case_ids[case_id] = line_no
        for key in ("target", "slug", "finding_id", "probe_id"):
            value = manifest.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{output_root / MANIFEST_NAME}: {key} must be a string when present")
        case_dir = cases_root / case_id
        if not case_dir.is_dir() or case_dir.is_symlink():
            raise ValueError(f"{case_dir}: missing case directory or symbolic links are not allowed")
        if case_dir.parent != cases_root:
            raise ValueError(f"{case_dir}: case directory escapes the cases root")
        result_path = case_dir / "result.json"
        if not result_path.is_file() or result_path.is_symlink():
            raise ValueError(f"missing regular result file (symbolic links are not allowed): {result_path}")
        row: dict[str, Any] = {
            "case_id": case_id,
            "case_dir": str(case_dir),
            "target": manifest.get("target"),
            "slug": manifest.get("slug"),
            "finding_id": manifest.get("finding_id"),
            "probe_id": manifest.get("probe_id"),
            "status": "paused",
            "verdict": "blocked",
            "failure_reason": "awaiting_dynamic_worker",
        }
        result = load_json(result_path)
        result_case_id = result.get("case_id")
        if result_case_id != case_id:
            raise ValueError(
                f"{result_path}: case_id {result_case_id!r} does not match expected {case_id!r}"
            )
        status = result.get("status")
        verdict = result.get("verdict")
        if not isinstance(status, str) or status not in ALLOWED_STATUS_VERDICTS:
            raise ValueError(f"{result_path}: invalid status {status!r}")
        if not isinstance(verdict, str) or verdict not in ALLOWED_STATUS_VERDICTS[status]:
            raise ValueError(f"{result_path}: verdict {verdict!r} is incompatible with status {status!r}")
        row["status"] = status
        row["verdict"] = verdict
        conditions = result.get("utilization_conditions", {})
        if not isinstance(conditions, dict):
            raise ValueError(f"{result_path}: utilization_conditions must be an object when present")
        summary = conditions.get("summary")
        if summary is not None and not isinstance(summary, str):
            raise ValueError(f"{result_path}: utilization_conditions.summary must be a string when present")
        row["utilization_conditions_summary"] = summary
        resource = result.get("resource_observation", {})
        if not isinstance(resource, dict):
            raise ValueError(f"{result_path}: resource_observation must be an object when present")
        failure_signal = resource.get("failure_signal")
        if failure_signal is not None and not isinstance(failure_signal, str):
            raise ValueError(f"{result_path}: resource_observation.failure_signal must be a string when present")
        row["failure_signal"] = failure_signal
        failure_reason = result.get("failure_reason")
        if failure_reason is not None and not isinstance(failure_reason, str):
            raise ValueError(f"{result_path}: failure_reason must be a string when present")
        if status == "paused":
            row["failure_reason"] = failure_reason or "awaiting_dynamic_worker"
        elif status in {"failed", "environment_blocked"}:
            row["failure_reason"] = failure_reason or status
        else:
            row["failure_reason"] = failure_reason
        status_rows.append(row)
    actual_case_ids = {item.name for item in cases_path.iterdir() if item.is_dir() and not item.is_symlink()}
    orphaned = sorted(actual_case_ids - set(observed_case_ids))
    if orphaned:
        raise ValueError(f"{cases_path}: case directories absent from manifest: {', '.join(orphaned)}")
    write_jsonl_atomically(output_root / STATUS_NAME, status_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    sync(args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
