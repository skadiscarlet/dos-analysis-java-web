#!/usr/bin/env python3
"""Generate chain-level truth dispositions for the PoC-33 recall.

This script is benchmark-only and never changes an ordinary scan verdict.  It
reads the frozen ``poc/manifest.json`` truth, resolves case-preserving source and
database assets, loads each target's production artifacts, and writes a
``truth_dispositions.jsonl`` plus a summary and Markdown report into a new,
immutable recall directory.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.benchmark.disposition import DISPOSITION_STATUSES, TargetArtifacts, compute_disposition
from dosweb.benchmark.truth import normalize_repo, repo_slug, resolve_asset_directory

_ORACLE_FORMAT = "dosweb-poc33-recall-oracle-v2"


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _bounded_sink_markers(value: object) -> list[str]:
    markers: list[str] = []
    stack: list[tuple[object, int, bool]] = [(value, 0, False)]
    nodes = 0
    while stack:
        current, depth, sink_context = stack.pop()
        nodes += 1
        if depth > 8 or nodes > 512:
            break
        if isinstance(current, str):
            if sink_context and current.strip():
                markers.append(current.strip())
            continue
        if isinstance(current, dict):
            for key, nested in current.items():
                normalized = str(key).casefold().replace("-", "_")
                nested_sink = sink_context or normalized in {"sink", "static_sink", "growth_sink"}
                stack.append((nested, depth + 1, nested_sink))
        elif isinstance(current, list):
            stack.extend((nested, depth + 1, sink_context) for nested in current[:64])
    return markers[:64]


def _markers_for_record(manifest_record: dict[str, object], repo_root: Path) -> list[str]:
    output_dir = manifest_record.get("output_dir")
    entry = manifest_record.get("entry")
    markers: list[str] = []
    if isinstance(output_dir, str) and output_dir and isinstance(entry, str):
        markers.append(entry)
    if isinstance(output_dir, str) and output_dir:
        attachment_dir = repo_root / output_dir / "attachments"
        for name in ("static_finding.json", "source_record.json", "source_result.json"):
            value = _read_json(attachment_dir / name)
            if isinstance(value, dict):
                markers.extend(_bounded_sink_markers(value))
    return sorted(set(markers))


def _sink_locations_for_record(
    manifest_record: dict[str, object], repo_root: Path, markers: list[str],
) -> list[dict[str, object]]:
    output_dir = manifest_record.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir:
        return []
    attachment_dir = repo_root / output_dir / "attachments"
    sink_text = " ".join(markers).casefold()
    locations: list[dict[str, object]] = []
    for name in ("static_finding.json", "source_result.json"):
        value = _read_json(attachment_dir / name)
        if not isinstance(value, dict):
            continue
        evidence = value.get("evidence")
        if not isinstance(evidence, list):
            continue
        for item in evidence[:128]:
            if not isinstance(item, str):
                continue
            match = re.search(r"(?P<file>[A-Za-z0-9_./$-]+\.java):(?P<start>\d+)(?:-(?P<end>\d+))?", item)
            if not match:
                continue
            file_name = match.group("file")
            stem = Path(file_name).stem.casefold()
            if stem not in sink_text:
                continue
            start = int(match.group("start")); end = int(match.group("end") or start)
            if 0 < start <= end <= 2**31 - 1:
                locations.append({"file": file_name, "start_line": start, "end_line": end})
    return sorted(
        {json.dumps(item, sort_keys=True): item for item in locations}.values(),
        key=lambda item: (str(item["file"]), int(item["start_line"]), int(item["end_line"])),
    )


def _infer_protocol(app: str, entry: str) -> str:
    text = f"{app} {entry}".casefold()
    if "grpc" in text:
        return "grpc"
    if "mqtt" in text or "smqtt" in text or "jmqtt" in text:
        return "mqtt"
    if "tcp" in text:
        return "tcp"
    if "/" in entry or "http" in text:
        return "http"
    return "unknown"


def _build_truth(manifest_record: dict[str, object], repo_root: Path) -> dict[str, object]:
    app = manifest_record.get("app")
    record_id = manifest_record.get("record_id")
    entry = manifest_record.get("entry")
    if not isinstance(app, str) or not isinstance(record_id, str) or not isinstance(entry, str):
        raise ValueError(f"invalid manifest record: {record_id!r}")
    repository = normalize_repo(app)
    slug = repo_slug(app)
    markers = _markers_for_record(manifest_record, repo_root)
    sink_locations = _sink_locations_for_record(manifest_record, repo_root, markers)
    identity = {
        "record_id": record_id,
        "repository": repository,
        "entry": entry,
    }
    truth = {
        "record_id": record_id,
        "app": app,
        "repository": repository,
        "repo_slug": slug,
        "entry": entry,
        "protocol": _infer_protocol(app, entry),
        "status": manifest_record.get("status"),
        "markers": markers,
        "sink_locations": sink_locations,
        "output_dir": manifest_record.get("output_dir"),
        "truth_id": stable_identifier("truth", identity),
    }
    asset_error = None
    try:
        truth["source_path"] = resolve_asset_directory(repo_root, "frameworks/applications", slug)
    except ValueError:
        asset_error = "asset_missing"
    try:
        truth["database_path"] = resolve_asset_directory(repo_root, "databases/applications", f"{slug}-db")
    except ValueError:
        asset_error = "asset_missing"
    truth["asset_error"] = asset_error
    return truth


def _resolve_results_dir(results_root: Path, slug: str) -> Path | None:
    if not results_root.is_dir():
        return None
    target = slug.casefold()
    for entry in results_root.iterdir():
        if entry.is_dir() and entry.name.casefold() == target:
            return entry
    return None


def _load_manifest(manifest_path: Path) -> list[dict[str, object]]:
    value = _read_json(manifest_path)
    if not isinstance(value, list):
        raise SystemExit(f"manifest must be a JSON list: {manifest_path}")
    return [item for item in value if isinstance(item, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(_REPO_ROOT / "poc" / "manifest.json"))
    parser.add_argument("--results-root", default=str(_REPO_ROOT / "results" / "java_web_dos_batch" / "poc33-recall"))
    parser.add_argument("--output", default=None, help="Recall output directory (defaults to a timestamped immutable dir).")
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    results_root = Path(args.results_root).resolve()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = repo_root / manifest_path

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = Path(args.output) if args.output else (results_root.parent / f"poc33-recall-v2-{timestamp}")
    output_root.mkdir(parents=True, exist_ok=False)

    records = _load_manifest(manifest_path)
    dispositions: list[dict[str, object]] = []
    for manifest_record in records:
        try:
            truth = _build_truth(manifest_record, repo_root)
        except ValueError as exc:
            dispositions.append({"record_id": manifest_record.get("record_id"), "status": "truth_invalid", "reason_codes": [str(exc)]})
            continue
        results_dir = _resolve_results_dir(results_root, str(truth["repo_slug"]))
        if results_dir is None:
            artifacts = TargetArtifacts(Path("/nonexistent"))
        else:
            artifacts = TargetArtifacts.load(results_dir)
        disposition = compute_disposition(truth, artifacts, error=truth.get("asset_error"))
        dispositions.append(disposition)

    summary = {
        "format": _ORACLE_FORMAT,
        "generated_at": timestamp,
        "total": len(dispositions),
        "status_counts": {status: sum(1 for d in dispositions if d.get("status") == status) for status in DISPOSITION_STATUSES},
        "static_vulnerable_count": sum(1 for d in dispositions if "static_vulnerable" in d.get("verdicts", [])),
        "full_chain_finding_count": sum(1 for d in dispositions if d.get("status") == "full_chain_finding"),
    }

    dispositions_path = output_root / "truth_dispositions.jsonl"
    dispositions_path.write_text(
        "".join(json.dumps(d, sort_keys=True, ensure_ascii=False) + "\n" for d in dispositions),
        encoding="utf-8",
    )
    (output_root / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _write_report(output_root, summary, dispositions)

    print(f"wrote {len(dispositions)} dispositions to {output_root}")
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


def _write_report(output_root: Path, summary: dict[str, object], dispositions: list[dict[str, object]]) -> None:
    lines = [
        "# PoC-33 chain-level recall report",
        "",
        f"Format: `{_ORACLE_FORMAT}`",
        f"Total truth records: {summary['total']}",
        "",
        "## Disposition counts",
        "",
    ]
    for status in DISPOSITION_STATUSES:
        count = summary["status_counts"].get(status, 0)
        if count:
            lines.append(f"- `{status}`: {count}")
    lines += [
        "",
        "## Per-record disposition",
        "",
        "| record_id | repository | status | verdicts | reason_codes |",
        "|---|---|---|---|---|",
    ]
    for d in dispositions:
        verdicts = ",".join(d.get("verdicts", []) or []) or "-"
        reasons = ",".join(d.get("reason_codes", []) or []) or "-"
        lines.append(
            f"| {d.get('record_id', '?')} | {d.get('repository', '?')} | {d.get('status', '?')} | {verdicts} | {reasons} |"
        )
    lines.append("")
    (output_root / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
