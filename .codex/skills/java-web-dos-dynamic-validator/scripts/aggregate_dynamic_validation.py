#!/usr/bin/env python3
"""Aggregate Java Web DoS dynamic validation case results."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


FINDING_STATUSES = {
    "confirmed_oom",
    "confirmed_gc_death",
    "confirmed_restart",
    "confirmed_thread_exhaustion",
    "confirmed_connection_exhaustion",
    "confirmed_sustained_unavailable",
    "observed_growth_not_confirmed",
}


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"json_error:{exc}"
    if not isinstance(data, dict):
        return None, "not_object"
    return data, None


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def flatten_row(record: dict[str, Any]) -> dict[str, Any]:
    default_deployment = record.get("default_deployment") or {}
    reachability = record.get("reachability") or {}
    trigger = record.get("trigger") or {}
    resource = record.get("resource_observation") or {}
    conditions = record.get("utilization_conditions") or {}
    return {
        "case_id": record.get("case_id"),
        "target": record.get("target"),
        "slug": record.get("slug"),
        "finding_id": record.get("finding_id"),
        "probe_id": record.get("probe_id"),
        "status": record.get("status"),
        "verdict": record.get("verdict"),
        "resource_dimension": record.get("resource_dimension"),
        "default_is_default": default_deployment.get("is_default"),
        "deployment_source": default_deployment.get("source"),
        "image_or_version": default_deployment.get("image_or_version"),
        "attacker_model": reachability.get("attacker_model"),
        "entry": reachability.get("entry"),
        "auth_required": reachability.get("auth_required"),
        "request_count": trigger.get("request_count"),
        "duration_seconds": trigger.get("duration_seconds"),
        "metric": resource.get("metric"),
        "failure_signal": resource.get("failure_signal"),
        "utilization_conditions": conditions.get("summary"),
    }


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def render_report(output_root: Path, records: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    status_counts = Counter(str(r.get("status") or "unknown") for r in records)
    verdict_counts = Counter(str(r.get("verdict") or "unknown") for r in records)
    confirmed = [r for r in records if str(r.get("status") or "").startswith("confirmed_")]
    growth = [r for r in records if r.get("status") == "observed_growth_not_confirmed"]
    blocked = [r for r in records if r.get("status") not in FINDING_STATUSES]

    lines: list[str] = []
    lines.append("# Java Web DoS Dynamic Validation Report")
    lines.append("")
    lines.append(f"- Output root: `{output_root}`")
    lines.append(f"- Cases with result: {len(records)}")
    lines.append(f"- Case result errors: {len(errors)}")
    lines.append("")
    lines.append("## Status Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("| --- | ---: |")
    for status, count in sorted(status_counts.items()):
        lines.append(f"| `{status}` | {count} |")
    lines.append("")
    lines.append("## Verdict Summary")
    lines.append("")
    lines.append("| Verdict | Count |")
    lines.append("| --- | ---: |")
    for verdict, count in sorted(verdict_counts.items()):
        lines.append(f"| `{verdict}` | {count} |")

    lines.append("")
    lines.append("## Confirmed Cases")
    lines.append("")
    if confirmed:
        lines.append("| Case | Target | Entry | Failure | Utilization Conditions |")
        lines.append("| --- | --- | --- | --- | --- |")
        for record in confirmed:
            reachability = record.get("reachability") or {}
            resource = record.get("resource_observation") or {}
            conditions = record.get("utilization_conditions") or {}
            lines.append(
                "| {case} | {target} | {entry} | {failure} | {conditions} |".format(
                    case=record.get("case_id") or "",
                    target=record.get("target") or "",
                    entry=str(reachability.get("entry") or "").replace("|", "\\|"),
                    failure=str(resource.get("failure_signal") or record.get("status") or "").replace("|", "\\|"),
                    conditions=str(conditions.get("summary") or "").replace("|", "\\|"),
                )
            )
    else:
        lines.append("No dynamically confirmed DoS cases.")

    lines.append("")
    lines.append("## Growth-Only Cases")
    lines.append("")
    if growth:
        lines.append("| Case | Target | Metric | Utilization Conditions |")
        lines.append("| --- | --- | --- | --- |")
        for record in growth:
            resource = record.get("resource_observation") or {}
            conditions = record.get("utilization_conditions") or {}
            lines.append(
                "| {case} | {target} | {metric} | {conditions} |".format(
                    case=record.get("case_id") or "",
                    target=record.get("target") or "",
                    metric=str(resource.get("metric") or "").replace("|", "\\|"),
                    conditions=str(conditions.get("summary") or "").replace("|", "\\|"),
                )
            )
    else:
        lines.append("No growth-only cases.")

    lines.append("")
    lines.append("## Blocked Or Not Confirmed")
    lines.append("")
    if blocked:
        lines.append("| Case | Target | Status | Reason |")
        lines.append("| --- | --- | --- | --- |")
        for record in blocked:
            conditions = record.get("utilization_conditions") or {}
            notes = record.get("notes") or []
            reason = conditions.get("summary") or "; ".join(str(n) for n in notes[:3])
            lines.append(
                "| {case} | {target} | `{status}` | {reason} |".format(
                    case=record.get("case_id") or "",
                    target=record.get("target") or "",
                    status=record.get("status") or "",
                    reason=str(reason).replace("|", "\\|"),
                )
            )
    else:
        lines.append("No blocked or not-confirmed cases.")

    if errors:
        lines.append("")
        lines.append("## Result File Errors")
        lines.append("")
        lines.append("| Path | Error |")
        lines.append("| --- | --- |")
        for error in errors:
            lines.append(f"| `{error.get('path')}` | `{error.get('error')}` |")

    lines.append("")
    lines.append("Static candidates not listed as confirmed remain unconfirmed until dynamic evidence satisfies the failure threshold.")
    lines.append("")
    return "\n".join(lines)


def aggregate(output_root: Path) -> int:
    cases_root = output_root / "cases"
    output_root.mkdir(parents=True, exist_ok=True)
    cases_root.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for result_path in sorted(cases_root.glob("*/result.json")):
        record, error = load_json(result_path)
        if error:
            errors.append({"path": str(result_path), "error": error})
            continue
        assert record is not None
        record.setdefault("case_id", result_path.parent.name)
        record["_result_json"] = str(result_path)
        records.append(record)

    findings = [r for r in records if r.get("status") in FINDING_STATUSES]
    blocked = [r for r in records if r.get("status") not in FINDING_STATUSES]

    write_jsonl(output_root / "findings.jsonl", findings)
    write_jsonl(output_root / "blocked_or_rejected.jsonl", blocked + errors)

    rows = [flatten_row(r) for r in records]
    fieldnames = [
        "case_id",
        "target",
        "slug",
        "finding_id",
        "probe_id",
        "status",
        "verdict",
        "resource_dimension",
        "default_is_default",
        "deployment_source",
        "image_or_version",
        "attacker_model",
        "entry",
        "auth_required",
        "request_count",
        "duration_seconds",
        "metric",
        "failure_signal",
        "utilization_conditions",
    ]
    with (output_root / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})

    status_counts = Counter(str(r.get("status") or "unknown") for r in records)
    verdict_counts = Counter(str(r.get("verdict") or "unknown") for r in records)
    summary = {
        "output_root": str(output_root),
        "cases_root": str(cases_root),
        "case_count": len(records),
        "result_errors": errors,
        "status_counts": dict(sorted(status_counts.items())),
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "finding_count": len(findings),
        "blocked_or_rejected_count": len(blocked),
        "confirmed_count": sum(1 for r in records if str(r.get("status") or "").startswith("confirmed_")),
        "growth_only_count": sum(1 for r in records if r.get("status") == "observed_growth_not_confirmed"),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "DYNAMIC_VALIDATION_REPORT.md").write_text(
        render_report(output_root, records, errors),
        encoding="utf-8",
    )
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, help="Dynamic validation output root")
    args = parser.parse_args()
    return aggregate(Path(args.output_root).expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
