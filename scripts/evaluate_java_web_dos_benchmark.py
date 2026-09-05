#!/usr/bin/env python3
"""Generate and optionally evaluate the network-free PoC-29 benchmark."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dosweb.artifacts.identifiers import canonical_json, sha256_canonical_json
from dosweb.batch.plan import build_batch_plan
from dosweb.benchmark.candidates import extract_candidates
from dosweb.benchmark.entries import extract_entries
from dosweb.benchmark.evaluator import evaluate_matches
from dosweb.benchmark.matching import match_cases, match_entry_cases
from dosweb.benchmark.truth import (
    corpus_from_manifest,
    load_database_overrides,
    load_source_overrides,
    normalize_repo,
    normalize_truth,
)
from dosweb.config import DEFAULT_BASE_URL, DEFAULT_MODEL


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json(value) + b"\n")


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.write_bytes(b"".join(canonical_json(dict(row)) + b"\n" for row in rows))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _batch_targets(batch_root: Path | None) -> dict[str, dict[str, Any]]:
    if batch_root is None:
        return {}
    rows = _read_jsonl(batch_root / "manifest.normalized.jsonl")
    result = {}
    for row in rows:
        identity = row.get("identity")
        if not isinstance(identity, Mapping):
            continue
        try:
            repository = normalize_repo(identity.get("name"))
        except ValueError:
            continue
        result[repository] = row
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--truth",
        type=Path,
        default=ROOT / "results/applications_dynamic_validation/binary_truth_collection.json",
    )
    parser.add_argument("--batch-root", type=Path)
    parser.add_argument("--database-overrides", type=Path, help="strict JSON mapping repository to relative CodeQL database path")
    parser.add_argument("--source-overrides", type=Path, help="strict JSON mapping repository to clean public Git checkout provenance")
    parser.add_argument("--plan-run-id", help="emit an immutable PoC-29 batch plan")
    parser.add_argument("--plan-mode", choices=("entries", "full"), default="entries")
    parser.add_argument("--allow-remote-llm", action="store_true", help="record explicit remote-provider intent in a full plan; execution must authorize again")
    parser.add_argument("--plan-ready-only", action="store_true", help="emit a diagnostic entries plan for only validated databases; not a complete PoC-29 recall run")
    args = parser.parse_args(argv)

    if args.plan_ready_only and args.plan_mode != "entries":
        parser.error("--plan-ready-only is only valid for entries plans")
    if args.plan_mode == "full" and not args.plan_run_id:
        parser.error("--plan-mode full requires --plan-run-id")
    if args.allow_remote_llm and args.plan_mode != "full":
        parser.error("--allow-remote-llm is only valid with --plan-mode full")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        overrides = load_database_overrides(args.database_overrides, ROOT) if args.database_overrides else None
        source_overrides = load_source_overrides(args.source_overrides, ROOT) if args.source_overrides else None
        truth, validation, target_manifest = normalize_truth(
            args.truth.resolve(),
            repo_root=ROOT,
            database_overrides=overrides,
        )
    except (OSError, ValueError) as exc:
        print(f"BENCHMARK_INVALID: {exc}", file=sys.stderr)
        return 2
    manifest_path = output / "targets.manifest.json"
    _write_json(manifest_path, target_manifest)

    if args.plan_run_id or args.plan_ready_only:
        incomplete = validation.get("database_incomplete", [])
        if args.plan_run_id and incomplete:
            names = ", ".join(item["name"] for item in incomplete)
            print(f"BATCH_PLAN_INVALID: cannot create complete PoC-29 plan: incomplete databases ({names})", file=sys.stderr)
            return 2
        corpus_manifest = target_manifest
        if args.plan_ready_only:
            ready = [
                {**row, "index": index}
                for index, row in enumerate(
                    (row for row in target_manifest["projects"] if row.get("codeql_built") is True),
                    1,
                )
            ]
            corpus_manifest = dict(target_manifest)
            corpus_manifest["projects"] = ready
            corpus_manifest["total"] = len(ready)
            corpus_manifest["source_asset_count"] = validation["source_asset_count"]
            corpus_manifest["database_ready_count"] = len(ready)
            corpus_manifest["batch_ready"] = True
        corpus = corpus_from_manifest(corpus_manifest, ROOT, source_overrides=source_overrides)
        plan_mode = "entries" if args.plan_ready_only else args.plan_mode
        provider_settings = None
        if plan_mode == "full":
            provider_settings = {
                "model": DEFAULT_MODEL,
                "base_url": DEFAULT_BASE_URL,
                "temperature": 0,
                "timeout_seconds": 60,
                "max_retries": 3,
                "allow_remote_llm": bool(args.allow_remote_llm),
                "pilot_skipped": True,
            }
        plan = build_batch_plan(
            corpus,
            run_id=args.plan_run_id or "ready-only-diagnostic",
            mode=plan_mode,
            output_root=f"results/java_web_dos_batch/{args.plan_run_id or 'ready-only-diagnostic'}",
            provider_settings=provider_settings,
        )
        if plan_mode == "full":
            if not args.allow_remote_llm:
                print("BATCH_PLAN_INVALID: full PoC-29 plan requires explicit --allow-remote-llm intent", file=sys.stderr)
                return 2
            if len(plan.targets) != 18 or any(target.initial_state != "queued" for target in plan.targets):
                unavailable = ", ".join(
                    target.identity.name for target in plan.targets if target.initial_state != "queued"
                )
                print(
                    "BATCH_PLAN_INVALID: full PoC-29 requires exactly 18 provider-eligible targets"
                    + (f"; unavailable: {unavailable}" if unavailable else ""),
                    file=sys.stderr,
                )
                return 2
        _write_json(output / "batch_plan.json", plan.to_dict())
        _write_jsonl(
            output / "manifest.normalized.jsonl",
            [target.to_dict() for target in plan.targets],
        )

    batch_root = args.batch_root.resolve() if args.batch_root else None
    batch_targets = _batch_targets(batch_root)
    candidates_by_repo: dict[str, tuple[list[dict[str, Any]], str | None]] = {}
    entries_by_repo: dict[str, tuple[list[dict[str, Any]], str | None]] = {}
    snapshots: list[dict[str, Any]] = []
    coverage_gaps: list[dict[str, Any]] = []
    completed_targets = 0
    entry_fact_count = 0
    for project in target_manifest["projects"]:
        repository = project["name"]
        batch_target = batch_targets.get(repository)
        if batch_root is None or batch_target is None:
            candidates, error = [], "target_not_run"
            entries, entry_gaps, entry_error = [], [], "target_not_run"
        else:
            candidates, error = extract_candidates(batch_root, batch_target)
            entries, entry_gaps, entry_error = extract_entries(batch_root, batch_target)
        if entry_error is None:
            completed_targets += 1
            entry_fact_count += len(entries)
        coverage_gaps.extend({"repository": repository, **gap} for gap in entry_gaps)
        candidates_by_repo[repository] = (candidates, error)
        entries_by_repo[repository] = (entries, entry_error)
        snapshots.append(
            {
                "repository": repository,
                "target_id": batch_target.get("target_id") if batch_target else None,
                "status": "ok" if error is None else error,
                "entry_status": "ok" if entry_error is None else entry_error,
                "entry_fact_count": len(entries),
                "coverage_gaps": entry_gaps,
                "candidates": candidates,
            }
        )
    matches = match_cases(truth, candidates_by_repo)
    entry_diagnostics = match_entry_cases(truth, entries_by_repo)
    entry_status_counts = {}
    for row in entry_diagnostics:
        status = str(row.get("status"))
        entry_status_counts[status] = entry_status_counts.get(status, 0) + 1
    entry_summary = {
        "schema_version": 1,
        "completed_target_count": completed_targets,
        "entry_fact_count": entry_fact_count,
        "truth_entry_status_counts": dict(sorted(entry_status_counts.items())),
        "coverage_gap_count": len(coverage_gaps),
        "coverage_gaps": coverage_gaps,
    }
    evaluation = evaluate_matches(
        matches,
        truth_valid=bool(validation["valid"]),
        oracle_total=29,
        repository_total=18,
    )
    failures = [row for row in matches if row.get("status") != "hit"]
    run_manifest = {
        "schema_version": 1,
        "benchmark": "poc-29",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "truth_path": str(args.truth.resolve()),
        "truth_source_digest": validation["source_digest"],
        "batch_root": str(batch_root) if batch_root else None,
        "output_dir": str(output),
        "network": "disabled",
        "dynamic_execution": "disabled",
        "truth_digest": sha256_canonical_json(truth),
        "target_manifest_digest": sha256_canonical_json(target_manifest),
        "target_count": target_manifest["total"],
        "source_asset_count": validation["source_asset_count"],
        "database_ready_count": validation["database_ready_count"],
        "database_incomplete": validation["database_incomplete"],
        "database_incomplete_repositories": validation["database_incomplete_repositories"],
        "batch_ready": validation["batch_ready"],
        "plan_mode": args.plan_mode if args.plan_run_id else ("entries" if args.plan_ready_only else None),
        "plan_ready_only": bool(args.plan_ready_only),
        "plan_is_complete_recall_run": bool(
            args.plan_run_id
            and args.plan_mode == "full"
            and validation["batch_ready"]
            and "plan" in locals()
            and len(plan.targets) == 18
            and all(target.initial_state == "queued" for target in plan.targets)
        ),
        "entry_diagnostics": "entry_diagnostics.jsonl" if batch_root else None,
        "entry_summary": "entry_summary.json" if batch_root else None,
        "entry_diagnostics_are_not_static_metrics": True,
    }
    _write_json(output / "run_manifest.json", run_manifest)
    _write_jsonl(output / "truth.normalized.jsonl", truth)
    _write_json(output / "truth.validation.json", validation)
    _write_jsonl(output / "candidate_snapshot.jsonl", snapshots)
    _write_jsonl(output / "matches.jsonl", matches)
    _write_json(output / "evaluation.json", evaluation)
    _write_jsonl(output / "failures.jsonl", failures)
    if batch_root is not None:
        _write_jsonl(output / "entry_diagnostics.jsonl", entry_diagnostics)
        _write_json(output / "entry_summary.json", entry_summary)

    report = [
        "# PoC-29 Benchmark Report",
        "",
        f"- oracle_total: {evaluation['oracle_total']}",
        f"- repositories: {evaluation['repository_total']}",
        f"- eligible: {evaluation['eligible']}",
        f"- hits: {evaluation['hits']}",
        f"- targets_completed: {evaluation['targets_completed']}",
        f"- truth_valid: {validation['valid']}",
        f"- source_asset_count: {validation['source_asset_count']}",
        f"- database_ready_count: {validation['database_ready_count']}",
        f"- batch_ready: {validation['batch_ready']}",
        "",
        "## Entry diagnostics",
        "",
        f"- completed_target_count: {entry_summary['completed_target_count']}",
        f"- entry_fact_count: {entry_summary['entry_fact_count']}",
        f"- truth_entry_status_counts: {entry_summary['truth_entry_status_counts']}",
        f"- coverage_gap_count: {entry_summary['coverage_gap_count']}",
        "- Entry diagnostics are independent of final static hit/recall metrics.",
        "",
        "## Status",
        "",
    ]
    report.extend(
        f"- {key}: {value}"
        for key, value in sorted(evaluation["status_counts"].items())
    )
    report.extend(["", "## Metrics", ""])
    report.extend(
        f"- {key}: {value:.6f}"
        for key, value in evaluation["metrics"].items()
    )
    report.append("")
    (output / "report.md").write_text("\n".join(report), encoding="utf-8")
    return 0 if validation["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
