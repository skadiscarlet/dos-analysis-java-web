#!/usr/bin/env python3
"""Aggregate static Java Web DoS batch outputs without dynamic-validation coupling."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_HUNTER_FILES = [
    "summary.md", "target_profile.json", "sinks.jsonl", "sources.jsonl", "flows.jsonl",
    "findings.jsonl", "rejected.jsonl", "subagent_reviews.jsonl", "gaps.md",
]
JSONL_AGGREGATES = {
    "sinks.jsonl": "aggregate_sinks.jsonl",
    "sources.jsonl": "aggregate_sources.jsonl",
    "flows.jsonl": "aggregate_flows.jsonl",
    "findings.jsonl": "aggregate_findings.jsonl",
    "rejected.jsonl": "aggregate_rejected.jsonl",
    "subagent_reviews.jsonl": "aggregate_subagent_reviews.jsonl",
}
STATIC_VERDICTS = {
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    if not path.is_file():
        raise ValueError(f"{path}: expected a file")
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"{path}:{line_no}: JSONL record must be an object")
            rows.append(data)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def latest_status_by_slug(batch_root: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(batch_root / "batch_status.jsonl"):
        slug = row.get("slug")
        if not isinstance(slug, str) or not slug:
            raise ValueError(f"{batch_root / 'batch_status.jsonl'}: status record requires non-empty slug")
        latest[slug] = row
    return latest


def target_meta(manifest_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_target_slug": manifest_row["slug"],
        "batch_target_name": manifest_row["target"],
        "batch_repo_path": manifest_row["repo_path"],
        "batch_hunter_output_dir": manifest_row["hunter_output_dir"],
    }


def validate_manifest(manifest: list[dict[str, Any]], manifest_path: Path) -> None:
    if not manifest:
        raise ValueError(f"{manifest_path}: manifest contains no targets")
    seen: dict[str, int] = {}
    required = ("slug", "target", "repo_path", "hunter_output_dir")
    for line_no, row in enumerate(manifest, 1):
        missing = [key for key in required if not isinstance(row.get(key), str) or not row[key].strip()]
        if missing:
            raise ValueError(f"{manifest_path}:{line_no}: missing required manifest fields: {', '.join(missing)}")
        slug = row["slug"]
        if slug in seen:
            raise ValueError(f"{manifest_path}:{line_no}: duplicate slug {slug}; first declared at line {seen[slug]}")
        seen[slug] = line_no


def add_meta(row: dict[str, Any], manifest_row: dict[str, Any], source_file: str) -> dict[str, Any]:
    return {**row, **target_meta(manifest_row), "batch_source_file": source_file}


def record_static_verdict(row: dict[str, Any], path: Path, line_no: int) -> str:
    aliases = [key for key in ("static_verdict", "static_status", "static_conclusion") if key in row]
    if aliases:
        raise ValueError(
            f"{path}:{line_no}: unsupported static verdict field alias {aliases[0]!r}; use 'verdict'"
        )
    if "verdict" not in row:
        raise ValueError(f"{path}:{line_no}: finding requires the canonical verdict field")
    verdict = row["verdict"]
    if not isinstance(verdict, str) or verdict not in STATIC_VERDICTS:
        raise ValueError(f"{path}:{line_no}: invalid static verdict {verdict!r}; expected one of {', '.join(sorted(STATIC_VERDICTS))}")
    return verdict


def read_findings(path: Path) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    if not path.exists():
        return rows, counts
    if not path.is_file():
        raise ValueError(f"{path}: expected a file")
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: JSONL record must be an object")
            counts[f"verdict:{record_static_verdict(row, path, line_no)}"] += 1
            rows.append(row)
    return rows, counts


def aggregate(batch_root: Path) -> None:
    manifest_path = batch_root / "manifest.normalized.jsonl"
    if not manifest_path.is_file():
        raise ValueError(f"missing required normalized manifest: {manifest_path}")
    manifest = read_jsonl(manifest_path)
    validate_manifest(manifest, manifest_path)
    statuses = latest_status_by_slug(batch_root)
    aggregate_rows: dict[str, list[dict[str, Any]]] = {output: [] for output in JSONL_AGGREGATES.values()}
    target_profiles: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    gap_sections = ["# Aggregate Gaps", ""]
    totals: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for item in manifest:
        slug = item["slug"]
        hunter_dir = Path(item["hunter_output_dir"])
        if not hunter_dir.is_absolute():
            hunter_dir = (batch_root / hunter_dir).resolve()
        missing = [name for name in REQUIRED_HUNTER_FILES if not (hunter_dir / name).is_file()]
        malformed: list[str] = []
        counts: Counter[str] = Counter()
        prior_status = statuses.get(slug, {})
        effective_status = str(prior_status.get("status") or "completed")
        failure_reason = prior_status.get("failure_reason")

        if missing:
            if effective_status not in {"queued", "running", "retrying", "paused", "skipped"}:
                effective_status, failure_reason = "failed", failure_reason or "missing_required_files"
        else:
            try:
                try:
                    profile = json.loads((hunter_dir / "target_profile.json").read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{hunter_dir / 'target_profile.json'}:{exc.lineno}: invalid JSON: {exc.msg}") from exc
                if not isinstance(profile, dict):
                    raise ValueError(f"{hunter_dir / 'target_profile.json'}: expected JSON object")
                target_profiles.append(add_meta(profile, item, "target_profile.json"))
                for source_name, output_name in JSONL_AGGREGATES.items():
                    path = hunter_dir / source_name
                    if source_name == "findings.jsonl":
                        rows, verdict_counts = read_findings(path)
                        counts.update(verdict_counts)
                    else:
                        rows = read_jsonl(path)
                    counts[source_name] = len(rows)
                    aggregate_rows[output_name].extend(add_meta(row, item, source_name) for row in rows)
            except ValueError as exc:
                raise ValueError(f"{item['slug']}: malformed static artifact: {exc}") from exc

        gaps_path = hunter_dir / "gaps.md"
        if gaps_path.is_file():
            gap_text = gaps_path.read_text(encoding="utf-8").strip()
            if gap_text:
                gap_sections.extend([f"## {item['target']}", "", gap_text, ""])
        record = {
            **target_meta(item), "status": effective_status, "failure_reason": failure_reason,
            "missing_files": missing, "malformed": malformed, "counts": dict(counts),
        }
        status_rows.append(record)
        status_counts[effective_status] += 1
        totals.update(counts)

    write_jsonl(batch_root / "aggregate_target_profiles.jsonl", target_profiles)
    for output_name, rows in aggregate_rows.items():
        write_jsonl(batch_root / output_name, rows)
    write_jsonl(batch_root / "aggregate_status.jsonl", status_rows)
    (batch_root / "aggregate_gaps.md").write_text("\n".join(gap_sections).rstrip() + "\n", encoding="utf-8")
    inventory = {
        "batch_root": str(batch_root), "targets": status_rows, "status_counts": dict(status_counts), "totals": dict(totals),
    }
    (batch_root / "aggregate_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = ["# Java Web DoS Static Batch Summary", "", f"Batch root: `{batch_root}`", "", "## Status", ""]
    summary.extend(f"- {key}: {value}" for key, value in sorted(status_counts.items()))
    summary.extend(["", "## Aggregate Counts", "", f"- targets: {len(manifest)}"])
    for name in ("sinks", "sources", "flows", "findings", "rejected"):
        summary.append(f"- {name}: {len(aggregate_rows[f'aggregate_{name}.jsonl'])}")
    for verdict in sorted(STATIC_VERDICTS):
        summary.append(f"- {verdict}: {totals[f'verdict:{verdict}']}")
    summary.extend(["", "## Attention", ""])
    attention = [row for row in status_rows if row["status"] not in {"completed", "completed_with_gaps", "skipped"} or row["missing_files"] or row["malformed"]]
    summary.extend(
        f"- {row['batch_target_name']}: {row['status']} reason={row.get('failure_reason')} missing={','.join(row['missing_files']) or '-'} malformed={'; '.join(row['malformed']) or '-'}"
        for row in attention
    )
    if not attention:
        summary.append("- none")
    (batch_root / "batch_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        aggregate(args.batch_root.resolve())
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
