#!/usr/bin/env python3
import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STRICT_MIN_MEMORY_MIB = 1024
STRICT_AUDITED_BATCHES = {"new_retest", "new", "p2", "p1", "p0"}

BATCH_PRIORITY = {
    "new_retest": 0,
    "new": 1,
    "p2": 2,
    "p1": 3,
    "p0": 4,
}


@dataclass
class Record:
    record_id: str
    app: str
    title: str
    source_batch: str
    source_file: str
    schema: str
    status: str
    verdict: str
    category: str
    reason: str
    finding_id: str | None = None
    probe_id: str | None = None
    entry: str | None = None
    failure_signal: str = ""
    heap_or_limit: str = ""
    requests_sent: int | None = None
    log_path: str = ""
    evidence_summary: str = ""
    strict_1g_evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "app": self.app,
            "title": self.title,
            "source_batch": self.source_batch,
            "source_file": self.source_file,
            "schema": self.schema,
            "status": self.status,
            "verdict": self.verdict,
            "category": self.category,
            "reason": self.reason,
            "finding_id": self.finding_id,
            "probe_id": self.probe_id,
            "entry": self.entry,
            "failure_signal": self.failure_signal,
            "heap_or_limit": self.heap_or_limit,
            "requests_sent": self.requests_sent,
            "log_path": self.log_path,
            "evidence_summary": self.evidence_summary,
            "strict_1g_evidence": self.strict_1g_evidence,
        }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[Any]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def memory_value_to_mib(amount: int, unit: str) -> int:
    normalized = unit.lower()
    if normalized in {"g", "gb", "gib"}:
        return amount * 1024
    if normalized in {"m", "mb", "mib"}:
        return amount
    if normalized in {"k", "kb", "kib"}:
        return max(1, amount // 1024)
    return amount


def strict_1g_memory_evidence(*values: object, allow_exact: bool = True) -> str:
    if allow_exact:
        for value in values:
            value_text = str(value or "").lower()
            exact_value = re.fullmatch(r"\s*(\d+)\s*(gib|gb|g|mib|mb|m)\s*", value_text)
            if not exact_value:
                continue
            mib = memory_value_to_mib(int(exact_value.group(1)), exact_value.group(2))
            if mib >= STRICT_MIN_MEMORY_MIB:
                return exact_value.group(0).strip()
    text = " ".join(str(value or "") for value in values)
    if not text.strip():
        return ""
    normalized = text.lower()
    exact = re.fullmatch(r"\s*(\d+)\s*(gib|gb|g|mib|mb|m)\s*", normalized)
    if allow_exact and exact:
        mib = memory_value_to_mib(int(exact.group(1)), exact.group(2))
        if mib >= STRICT_MIN_MEMORY_MIB:
            return exact.group(0).strip()
    patterns = (
        r"(?:-xmx|xmx|druid_xmx|solr_heap|java_opts|heap(?:\s+(?:max|limit|default|was|=|:))?|java heap|jvm heap)[^\n;,.]{0,100}?(\d+)\s*(gib|gb|g|mib|mb|m)",
        r"(\d+)\s*(gib|gb|g|mib|mb|m)[^\n;,.]{0,100}?(?:heap|java heap|jvm heap|-xmx|xmx|druid_xmx|solr_heap)",
        r"(?:docker\s+--memory(?:=|\s+)|docker memory(?:=|\s+)|container\s+--memory(?:=|\s+)|container memory(?:=|\s+)|compose .*memory limit|memory limit|mem_limit)[^\n;,.]{0,100}?(\d+)\s*(gib|gb|g|mib|mb|m)",
        r"(\d+)\s*(gib|gb|g|mib|mb|m)[^\n;,.]{0,100}?(?:docker memory|container memory|compose .*memory limit|memory limit|mem_limit)",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        mib = memory_value_to_mib(int(match.group(1)), match.group(2))
        if mib >= STRICT_MIN_MEMORY_MIB:
            return match.group(0).strip()
    return ""


def is_strict_audited_batch(batch: str) -> bool:
    return batch in STRICT_AUDITED_BATCHES


def is_confirmed_status(status: str, verdict: str) -> bool:
    return (
        status.startswith("confirmed_")
        or status in {"verified_oom", "verified_service_unavailable"}
        or verdict == "confirmed"
        or verdict.startswith("confirmed_")
    )


def category_from_new_style(batch: str, data: dict[str, Any]) -> str:
    status = str(data.get("status", ""))
    verdict = str(data.get("verdict", ""))
    evidence = strict_1g_memory_evidence(
        data.get("safety", {}).get("heap_or_container_limit"),
        allow_exact=False,
    )
    if is_strict_audited_batch(batch) and is_confirmed_status(status, verdict) and evidence:
        return "confirmed_true_positive"
    return "unconfirmed_or_non_oom"


def category_from_legacy(batch: str, data: dict[str, Any]) -> str:
    dynamic_verdict = str(data.get("dynamic_verdict", ""))
    status = str(data.get("status", ""))
    evidence = strict_1g_memory_evidence(data.get("heap"), data.get("evidence", {}).get("heap"))
    if is_strict_audited_batch(batch) and is_confirmed_status(status, dynamic_verdict) and evidence:
        return "confirmed_true_positive"
    return "unconfirmed_or_non_oom"


def compact(value: Any, max_len: int = 240) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def md_cell(value: Any, max_len: int = 240) -> str:
    return compact(value, max_len).replace("|", "\\|")


def first_existing_path(paths: Any) -> str:
    if isinstance(paths, list):
        for item in paths:
            if item:
                return str(item)
    if isinstance(paths, str):
        return paths
    return ""


def summarize_legacy_evidence(row: dict[str, Any]) -> str:
    evidence = row.get("evidence", {})
    parts: list[str] = []
    for key in (
        "endpoint",
        "payloadBytes",
        "payloadBytesApprox",
        "testedTextLengths",
        "testedHeights",
        "workerThreads",
        "loopsPerWorker",
        "lastHttpStatus",
    ):
        if key in evidence and evidence[key] not in ("", None):
            parts.append(f"{key}={evidence[key]}")
    process_status = evidence.get("processStatus")
    if isinstance(process_status, dict):
        for key in ("VmHWM", "VmRSS", "Threads"):
            if process_status.get(key):
                parts.append(f"{key}={process_status[key]}")
    return compact("; ".join(parts))


def summarize_new_style_evidence(data: dict[str, Any]) -> str:
    trigger = data.get("trigger", {})
    observation = data.get("resource_observation", {})
    parts: list[str] = []
    if trigger.get("request_count") not in ("", None):
        parts.append(f"request_count={trigger.get('request_count')}")
    if trigger.get("duration_seconds") not in ("", None):
        parts.append(f"duration_seconds={trigger.get('duration_seconds')}")
    if observation.get("metric"):
        parts.append(f"metric={observation.get('metric')}")
    if observation.get("baseline") not in ("", None):
        parts.append(f"baseline={observation.get('baseline')}")
    if observation.get("peak") not in ("", None):
        parts.append(f"peak={observation.get('peak')}")
    return compact("; ".join(parts))


def normalize_new_style(batch: str, path: Path, root: Path) -> Record:
    data = load_json(path)
    observation = data.get("resource_observation", {})
    safety = data.get("safety", {})
    trigger = data.get("trigger", {})
    reason = (
        data.get("utilization_conditions", {}).get("summary")
        or "; ".join(data.get("notes", [])[:2])
        or ""
    )
    return Record(
        record_id=str(data["case_id"]),
        app=str(data.get("target", "")),
        title=str(data.get("finding_id", data["case_id"])),
        source_batch=batch,
        source_file=str(path.relative_to(root)),
        schema="new_style_result_json",
        status=str(data.get("status", "")),
        verdict=str(data.get("verdict", "")),
        category=category_from_new_style(batch, data),
        reason=reason,
        finding_id=data.get("finding_id"),
        probe_id=data.get("probe_id"),
        entry=data.get("reachability", {}).get("entry"),
        failure_signal=str(observation.get("failure_signal") or ""),
        heap_or_limit=str(safety.get("heap_or_container_limit") or ""),
        requests_sent=trigger.get("request_count") if isinstance(trigger.get("request_count"), int) else None,
        log_path=first_existing_path(observation.get("log_paths")),
        evidence_summary=summarize_new_style_evidence(data),
        strict_1g_evidence=strict_1g_memory_evidence(
            safety.get("heap_or_container_limit"),
            allow_exact=False,
        ),
    )


def normalize_legacy(batch: str, row: dict[str, Any], source_file: str) -> Record:
    evidence = row.get("evidence", {})
    reason = str(
        evidence.get("blockedReason")
        or row.get("notes")
        or row.get("oom_signal")
        or ""
    )
    return Record(
        record_id=str(row["candidate_id"]),
        app=str(row.get("app", "")),
        title=str(row.get("title", row["candidate_id"])),
        source_batch=batch,
        source_file=source_file,
        schema="legacy_findings_jsonl",
        status=str(row.get("status", "")),
        verdict=str(row.get("dynamic_verdict", "")),
        category=category_from_legacy(batch, row),
        reason=reason,
        entry=str(evidence.get("endpoint", "")),
        failure_signal=str(row.get("oom_signal") or ""),
        heap_or_limit=str(row.get("heap") or evidence.get("heap") or ""),
        requests_sent=row.get("requests_sent") if isinstance(row.get("requests_sent"), int) else None,
        log_path=str(row.get("log") or ""),
        evidence_summary=summarize_legacy_evidence(row),
        strict_1g_evidence=strict_1g_memory_evidence(row.get("heap"), evidence.get("heap")),
    )


def gather_records(root: Path) -> list[Record]:
    records: list[Record] = []
    for batch in ("new_retest", "new"):
        batch_dir = root / batch / "cases"
        if not batch_dir.exists():
            continue
        for path in sorted(batch_dir.glob("*/result.json")):
            records.append(normalize_new_style(batch, path, root))
    for batch in ("p2", "p1", "p0"):
        findings = root / batch / "findings.jsonl"
        if not findings.exists():
            continue
        for row in load_jsonl(findings):
            records.append(
                normalize_legacy(
                    batch=batch,
                    row=row,
                    source_file=str(findings.relative_to(root)),
                )
            )
    return records


def dedupe_records(records: list[Record]) -> tuple[list[Record], list[dict[str, Any]]]:
    chosen: dict[str, Record] = {}
    duplicates: dict[str, list[Record]] = {}
    for record in records:
        current = chosen.get(record.record_id)
        if current is None:
            chosen[record.record_id] = record
            continue
        keep_current = BATCH_PRIORITY[current.source_batch] <= BATCH_PRIORITY[record.source_batch]
        if keep_current:
            duplicates.setdefault(record.record_id, [current]).append(record)
            continue
        duplicates.setdefault(record.record_id, [current]).append(record)
        chosen[record.record_id] = record

    resolved = []
    for record_id, dup_records in sorted(duplicates.items()):
        all_records = {item.source_batch + ":" + item.status + ":" + item.source_file: item for item in dup_records}
        chosen_record = chosen[record_id]
        discarded = []
        for item in all_records.values():
            if item.source_batch == chosen_record.source_batch and item.source_file == chosen_record.source_file:
                continue
            discarded.append(
                {
                    "source_batch": item.source_batch,
                    "status": item.status,
                    "verdict": item.verdict,
                    "source_file": item.source_file,
                }
            )
        resolved.append(
            {
                "record_id": record_id,
                "chosen": {
                    "source_batch": chosen_record.source_batch,
                    "status": chosen_record.status,
                    "verdict": chosen_record.verdict,
                    "source_file": chosen_record.source_file,
                },
                "discarded": sorted(
                    discarded,
                    key=lambda item: (BATCH_PRIORITY[item["source_batch"]], item["source_file"]),
                ),
            }
        )
    deduped = sorted(
        chosen.values(),
        key=lambda item: (
            item.category != "confirmed_true_positive",
            item.source_batch,
            item.record_id,
        ),
    )
    return deduped, resolved


def render_markdown(
    raw_count: int,
    deduped: list[Record],
    duplicates: list[dict[str, Any]],
    output_json: Path,
) -> str:
    confirmed = [item for item in deduped if item.category == "confirmed_true_positive"]
    unconfirmed = [item for item in deduped if item.category == "unconfirmed_or_non_oom"]
    lines = [
        "# Dynamic Validation Binary Truth Collection",
        "",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Raw records scanned: `{raw_count}`",
        f"- Unique records after dedupe: `{len(deduped)}`",
        f"- Duplicate ids resolved: `{len(duplicates)}`",
        f"- JSON output: `{output_json}`",
        f"- True-positive criterion: audited batch `{', '.join(sorted(STRICT_AUDITED_BATCHES))}` plus confirmed target failure and explicit JVM heap, `-Xmx`, or target container/process memory evidence of at least `{STRICT_MIN_MEMORY_MIB} MiB`; smaller-heap OOM and low-memory-only historical evidence are counted under `unconfirmed_or_non_oom`.",
        "",
        "## Counts",
        "",
        "| Category | Count |",
        "| --- | ---: |",
        f"| `confirmed_true_positive` | {len(confirmed)} |",
        f"| `unconfirmed_or_non_oom` | {len(unconfirmed)} |",
        "",
        "## Confirmed True Positives",
        "",
        "| ID | App | Source | Status | Heap/Limit | Requests | Failure | Evidence |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for item in confirmed:
        lines.append(
            f"| `{md_cell(item.record_id)}` | `{md_cell(item.app)}` | `{md_cell(item.source_batch)}` | "
            f"`{md_cell(item.status)}` | `{md_cell(item.heap_or_limit)}` | "
            f"{item.requests_sent if item.requests_sent is not None else ''} | "
            f"`{md_cell(item.failure_signal)}` | {md_cell(item.strict_1g_evidence, 180)} |"
        )
    lines.extend(["", "## Confirmed Evidence Paths", ""])
    if confirmed:
        for item in confirmed:
            entry = f"；entry `{item.entry}`" if item.entry else ""
            log_path = f"；log `{item.log_path}`" if item.log_path else ""
            lines.append(f"- `{item.record_id}`：{compact(item.reason, 220)}{entry}{log_path}")
    else:
        lines.append("No confirmed true positives.")
    lines.extend(
        [
            "",
            "## Unconfirmed Or Non-OOM",
            "",
            "| ID | App | Source | Status | Entry |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in unconfirmed:
        lines.append(
            f"| `{md_cell(item.record_id)}` | `{md_cell(item.app)}` | `{md_cell(item.source_batch)}` | "
            f"`{md_cell(item.status)}` | `{md_cell(item.entry or '')}` |"
        )
    if duplicates:
        lines.extend(
            [
                "",
                "## Duplicate Resolution",
                "",
                "| ID | Chosen | Discarded |",
                "| --- | --- | --- |",
            ]
        )
        for item in duplicates:
            chosen = item["chosen"]
            discarded = ", ".join(
                f"{row['source_batch']}:{row['status']}" for row in item["discarded"]
            )
            lines.append(
                f"| `{item['record_id']}` | `{chosen['source_batch']}:{chosen['status']}` | `{discarded}` |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="results/applications_dynamic_validation",
        help="dynamic validation root directory",
    )
    parser.add_argument(
        "--json-out",
        default="results/applications_dynamic_validation/binary_truth_collection.json",
        help="output JSON path",
    )
    parser.add_argument(
        "--md-out",
        default="results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md",
        help="output Markdown path",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    json_out = Path(args.json_out).resolve()
    md_out = Path(args.md_out).resolve()

    records = gather_records(root)
    deduped, duplicates = dedupe_records(records)

    confirmed = [item.to_dict() for item in deduped if item.category == "confirmed_true_positive"]
    unconfirmed = [item.to_dict() for item in deduped if item.category == "unconfirmed_or_non_oom"]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_root": str(root),
        "raw_record_count": len(records),
        "unique_record_count": len(deduped),
        "counts": {
            "confirmed_true_positive": len(confirmed),
            "unconfirmed_or_non_oom": len(unconfirmed),
        },
        "truth_criteria": {
            "confirmed_true_positive": (
                "audited p0/p1/p2/new/new_retest record plus confirmed target failure and explicit JVM heap, -Xmx, "
                f"or target container/process memory evidence of at least {STRICT_MIN_MEMORY_MIB} MiB; "
                "smaller-heap OOM and low-memory-only historical evidence are "
                "counted as unconfirmed_or_non_oom"
            ),
            "minimum_heap_mib": STRICT_MIN_MEMORY_MIB,
            "audited_batches": sorted(STRICT_AUDITED_BATCHES),
        },
        "dedupe_policy": {
            "unique_key": "case_id or candidate_id",
            "preferred_batch_order": ["new_retest", "new", "p2", "p1", "p0"],
            "note": "When the same record id appears in multiple batches, the newer batch wins.",
        },
        "duplicates_resolved": duplicates,
        "confirmed_true_positive": confirmed,
        "unconfirmed_or_non_oom": unconfirmed,
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_out.write_text(
        render_markdown(len(records), deduped, duplicates, json_out),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
