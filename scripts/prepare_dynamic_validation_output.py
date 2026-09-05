#!/usr/bin/env python3
"""Prepare opt-in dynamic-validation evidence scaffolding; never execute a probe."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


CASE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
STATIC_VERDICTS = {
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
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


def required_text(row: dict[str, Any], keys: tuple[str, ...], default: str, location: str) -> str:
    value = next((row[key] for key in keys if row.get(key) is not None), default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location}: {keys[-1]} must be a non-empty string when present")
    return value


def optional_text(row: dict[str, Any], key: str, location: str) -> str | None:
    value = row.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{location}: {key} must be a string when present")
    return value


def read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    """Read JSONL objects, retaining source line numbers for diagnostics."""
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
                rows.append((line_no, data))
    except FileNotFoundError as exc:
        raise ValueError(f"input JSONL file does not exist: {path}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json_dumps_strict(row, ensure_ascii=False, sort_keys=True) + "\n")


def sanitize(value: str) -> str:
    cleaned = CASE_ID_RE.sub("_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "none"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json_dumps_strict(value, ensure_ascii=False, sort_keys=True)


def stable_fingerprint(row: dict[str, Any]) -> str:
    """Produce a deterministic collision guard independent of input position."""
    canonical = json_dumps_strict(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def normalize_record(
    row: dict[str, Any], input_path: Path, output_root: Path, line_no: int
) -> dict[str, Any]:
    location = f"{input_path}:{line_no}"
    target = required_text(row, ("batch_target_name", "target"), "unknown", location)
    slug = required_text(row, ("batch_target_slug", "slug"), sanitize(target), location)
    finding_id = optional_text(row, "finding_id", location)
    if row.get("probe_id") is not None:
        probe_id = optional_text(row, "probe_id", location)
    else:
        probe_id = optional_text(row, "dynamic_probe_id", location)
    aliases = [key for key in ("static_verdict", "static_status", "static_conclusion") if key in row]
    if aliases:
        raise ValueError(
            f"{location}: unsupported static verdict field alias {aliases[0]!r}; use 'verdict'"
        )
    static_verdict = row.get("verdict")
    if static_verdict is not None and (
        not isinstance(static_verdict, str) or static_verdict not in STATIC_VERDICTS
    ):
        raise ValueError(f"{location}: invalid static verdict {static_verdict!r}")
    case_id = "-".join(
        (
            sanitize(str(slug)),
            sanitize(str(finding_id)) if finding_id is not None else "no-finding",
            sanitize(str(probe_id)) if probe_id is not None else "no-probe",
            stable_fingerprint(row),
        )
    )
    case_dir = output_root / "cases" / case_id
    return {
        "case_id": case_id,
        "case_dir": str(case_dir),
        "target": target,
        "slug": slug,
        "repo_path": row.get("batch_repo_path") or row.get("repo_path"),
        "static_output_dir": row.get("batch_hunter_output_dir") or row.get("static_output_dir"),
        "static_result_file": str(input_path),
        "finding_id": finding_id,
        "probe_id": probe_id,
        "title": row.get("title"),
        "static_verdict": static_verdict,
        "resource_dimension": row.get("resource_dimension"),
        "source": row.get("source"),
        "sink": row.get("sink"),
        "driver": row.get("driver"),
        "request_shape": row.get("request_shape"),
        "parameters": row.get("parameters"),
        "loop_variable": row.get("loop_variable"),
        "resource_metric": row.get("resource_metric"),
        "expected_growth": row.get("expected_growth"),
        "safety_limit": row.get("safety_limit"),
        "isolation_requirements": row.get("isolation_requirements"),
        "success_condition": row.get("success_condition"),
        "stop_condition": row.get("stop_condition"),
        "cleanup": row.get("cleanup"),
        "evidence": row.get("evidence"),
        "missing_evidence": row.get("missing_evidence"),
        "status": "paused",
        "raw_static_record": row,
    }


def initial_result(record: dict[str, Any]) -> dict[str, Any]:
    request_shape = record.get("request_shape") or "unknown static request shape"
    summary = "尚未执行动态验证；该记录只是从静态候选规范化而来，不能视为动态确认。"
    return {
        "case_id": record["case_id"],
        "target": record.get("target"),
        "slug": record.get("slug"),
        "finding_id": record.get("finding_id"),
        "probe_id": record.get("probe_id"),
        "status": "paused",
        "verdict": "blocked",
        "resource_dimension": record.get("resource_dimension"),
        "default_deployment": {
            "is_default": None,
            "source": "unknown",
            "image_or_version": None,
            "commands": [],
            "config_changes": [],
            "non_default_reason": None,
        },
        "reachability": {
            "attacker_model": "unknown",
            "entry": request_shape,
            "auth_required": None,
            "account_used": None,
            "network_exposure": "unknown",
            "required_roles": [],
        },
        "data_preparation": {
            "required": None,
            "steps": [],
            "seed_data": [],
            "low_privilege_account": None,
            "default_credentials_used": False,
        },
        "trigger": {
            "request_shape": request_shape,
            "parameters": record.get("parameters") or {},
            "loop_variable": record.get("loop_variable"),
            "request_count": 0,
            "duration_seconds": 0,
            "bandwidth_notes": None,
        },
        "resource_observation": {
            "metric": record.get("resource_metric") or record.get("resource_dimension"),
            "baseline": None,
            "peak": None,
            "failure_signal": "none",
            "log_paths": [],
            "evidence_paths": [],
        },
        "utilization_conditions": {
            "summary": summary,
            "requires_default_exposure": False,
            "requires_low_privilege_account": False,
            "requires_admin": False,
            "requires_config_change": False,
            "requires_optional_component": False,
            "requires_seed_data": False,
            "limits_or_mitigations": [],
            "not_affected_when": ["未执行默认部署和外部请求探针时，不能得出动态可利用结论。"],
        },
        "safety": {
            "request_cap": None,
            "time_cap_seconds": None,
            "heap_or_container_limit": None,
            "stop_condition_hit": False,
            "cleanup_done": True,
        },
        "static_traceability": {
            "static_result_file": record.get("static_result_file"),
            "static_verdict": record.get("static_verdict"),
            "source": as_text(record.get("source")),
            "sink": as_text(record.get("sink")),
            "driver": as_text(record.get("driver")),
            "missing_static_evidence": as_list(record.get("missing_evidence")),
        },
        "notes": [
            "initial paused placeholder",
            "this helper never runs probes or contacts targets",
            "an independently authorized operator must replace this result after controlled validation",
        ],
    }


def case_plan(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": record["case_id"],
        "status": "paused",
        "static_candidate": record,
        "dynamic_goal": "record evidence for or against service unavailability under default deployment",
        "operator_notice": (
            "This scaffold is not part of the static analysis pipeline and does not execute probes. "
            "Any validation requires separate authorization and an isolated local target."
        ),
    }


def write_case_scaffold(output_root: Path, record: dict[str, Any]) -> None:
    case_dir = output_root / "cases" / record["case_id"]
    (case_dir / "logs").mkdir(parents=True, exist_ok=True)
    (case_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (case_dir / "case_plan.json").write_text(
        json_dumps_strict(case_plan(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (case_dir / "environment.md").write_text(
        "# Environment\n\nDynamic validation has not run for this case yet.\n",
        encoding="utf-8",
    )
    (case_dir / "data_prep.md").write_text(
        "# Data Preparation\n\nDynamic validation has not run for this case yet.\n",
        encoding="utf-8",
    )
    (case_dir / "result.json").write_text(
        json_dumps_strict(initial_result(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_plan(output_root: Path, input_path: Path, records: list[dict[str, Any]]) -> str:
    lines = [
        "# Opt-in Dynamic Validation Evidence Scaffold",
        "",
        "This directory is independent of the static analysis pipeline and is not part of the static analysis pipeline.",
        "This helper does not execute probes, start services, generate load, or contact external targets.",
        "Any dynamic work requires separate authorization and must use an isolated local/disposable target.",
        "",
        f"- Input file: `{input_path}`",
        f"- Output root: `{output_root}`",
        f"- Candidate count: {len(records)}",
        "",
        "Every case is initialized as `paused`. Updating a case is a manual, separately authorized workflow; "
        "a static verdict is never dynamic confirmation.",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## {record['case_id']}",
                "",
                f"- Target: `{record.get('target')}`",
                f"- Finding: `{record.get('finding_id')}`",
                f"- Probe: `{record.get('probe_id')}`",
                f"- Static verdict: `{record.get('static_verdict')}`",
                f"- Case directory: `{output_root / 'cases' / record['case_id']}`",
                "- Required before changing this case: separate authorization, isolated local target, explicit caps, "
                "stop conditions, and cleanup plan.",
                "",
            ]
        )
    return "\n".join(lines)


def build_output(
    output_root: Path, display_root: Path, input_path: Path, records: list[dict[str, Any]]
) -> None:
    write_jsonl(output_root / "manifest.normalized.jsonl", records)
    write_jsonl(
        output_root / "validation_status.jsonl",
        [
            {
                "case_id": record["case_id"],
                "case_dir": str(display_root / "cases" / record["case_id"]),
                "target": record.get("target"),
                "slug": record.get("slug"),
                "finding_id": record.get("finding_id"),
                "probe_id": record.get("probe_id"),
                "status": "paused",
                "verdict": "blocked",
                "failure_reason": "awaiting_dynamic_worker",
                "utilization_conditions_summary": "尚未执行动态验证；该记录只是从静态候选规范化而来，不能视为动态确认。",
                "failure_signal": "none",
            }
            for record in records
        ],
    )
    for record in records:
        write_case_scaffold(output_root, record)
    (output_root / "DYNAMIC_VALIDATION_PLAN.md").write_text(
        render_plan(display_root, input_path, records), encoding="utf-8"
    )


def files_match(left: Path, right: Path) -> bool:
    if left.is_symlink() or right.is_symlink():
        return False
    if left.is_dir() != right.is_dir() or left.is_file() != right.is_file():
        return False
    if left.is_file():
        return left.read_bytes() == right.read_bytes()
    left_children = sorted(item.name for item in left.iterdir())
    right_children = sorted(item.name for item in right.iterdir())
    return left_children == right_children and all(files_match(left / name, right / name) for name in left_children)


def reject_completed_evidence(output_root: Path) -> None:
    for result_path in output_root.glob("cases/*/result.json"):
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and result.get("status") != "paused":
            raise ValueError(
                f"{result_path}: contains completed evidence (status={result.get('status')!r}); "
                "--force only permits replacing an exact untouched paused scaffold"
            )


def ensure_unique_case_ids(
    rows: list[tuple[int, dict[str, Any]]], input_path: Path, output_root: Path
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    source_lines: dict[str, int] = {}
    for line_no, row in rows:
        record = normalize_record(row, input_path, output_root, line_no)
        case_id = record["case_id"]
        if case_id in source_lines:
            raise ValueError(
                f"{input_path}:{source_lines[case_id]} and {input_path}:{line_no}: "
                f"duplicate case_id {case_id!r}; deduplicate the static candidates"
            )
        source_lines[case_id] = line_no
        records.append(record)
    return records


def prepare(input_path: Path, output_root: Path, force: bool = False) -> None:
    input_path = input_path.resolve()
    output_root = output_root.resolve()
    if output_root == Path(output_root.anchor):
        raise ValueError(f"refusing dangerous filesystem-root output path: {output_root}")
    rows = read_jsonl(input_path)
    records = ensure_unique_case_ids(rows, input_path, output_root)
    output_root.parent.mkdir(parents=True, exist_ok=True)

    with output_lock(output_root):
        with tempfile.TemporaryDirectory(prefix=f".{output_root.name}.prepare-", dir=output_root.parent) as temp:
            staging = Path(temp) / output_root.name
            staging.mkdir()
            build_output(staging, output_root, input_path, records)

            if output_root.exists():
                contents = sorted(item.name for item in output_root.iterdir())
                if contents and not force:
                    raise ValueError(
                        f"output root {output_root} is non-empty ({', '.join(contents)}); "
                        "refusing to overwrite existing cases or results without --force"
                    )
                if contents and force:
                    reject_completed_evidence(output_root)
                    if not files_match(output_root, staging):
                        raise ValueError(
                            f"output root {output_root} is not an exact untouched paused scaffold; "
                            "--force may only accept the same untouched paused scaffold"
                        )
                    return
                if not contents:
                    output_root.rmdir()
            os.replace(staging, output_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="accept an existing exact untouched paused scaffold; never rewrite case evidence",
    )
    args = parser.parse_args(argv)
    prepare(args.input, args.output_root, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
