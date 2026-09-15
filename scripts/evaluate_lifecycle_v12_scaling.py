#!/usr/bin/env python3
"""Real 1x/2x/4x renamed-fixture storage/replay experiment (offline, LLM off).

Copies are performance units, never independent projects or generalization data.
The >16 MiB acceptance condition is measured, not synthesized or presumed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dosweb.artifacts.identifiers import canonical_json
from dosweb.resource_lifecycle import commands
from dosweb.resource_lifecycle.adapters import extracted_from_dict, validate_extracted
from dosweb.resource_lifecycle.io import atomic_write_json, load_json_regular
from dosweb.resource_lifecycle.models import SCHEMA_VERSION
from dosweb.resource_lifecycle.sharded_run import _single, analyze_sharded, replay_sharded, iter_run_units
from dosweb.resource_lifecycle.shards import ShardBudget, ShardReader

FIXTURE = ROOT / "tests/fixtures/resource_lifecycle_v1_1"
SOURCE = FIXTURE / "src/main/java/fixture/lifecyclev11/SourcePairs.java"
CASES = FIXTURE / "source-cases.json"
OLD_LIMIT = 16 * 1024 * 1024


def run_command(argv: list[str], cwd: Path, log: Path, timeout: int) -> float:
    """Persist exact command and combined process output, including failures."""
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"argv": argv, "cwd": str(cwd)}, ensure_ascii=False) + "\n")
        stream.flush()
        completed = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        stream.write(f"\nexit_code={completed.returncode}\n")
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}); see {log.name}")
    return time.monotonic() - started


def select_requested(extracted, requested):
    """Filter unrelated methods while retaining independently checked coverage."""
    selected = [_single(extracted, unit) for unit in extracted.units if unit.unit_id in requested]
    matched = {single.units[0].unit_id for single in selected}
    if matched != set(requested):
        raise ValueError(f"requested methods missing from real extraction: {sorted(set(requested) - matched)}")
    facts = tuple(sorted((fact for single in selected for fact in single.facts), key=lambda fact: fact.fact_id))
    coverage = dict(extracted.coverage)
    coverage.update(units=len(selected), facts=len(facts),
        partial_or_unsupported=sum(f.coverage_status != "complete" for f in facts),
        dimension_gaps=sum(len(single.units[0].program.coverage_gaps) for single in selected),
        requested_entry_methods=sorted(requested), matched_entry_methods=sorted(requested),
        external_entry_units=len(selected), local_method_units=0)
    return validate_extracted(replace(extracted, units=tuple(single.units[0] for single in selected),
        facts=facts, coverage=coverage,
        snapshot_sha256=hashlib.sha256(canonical_json([asdict(fact) for fact in facts])).hexdigest()))


def reuse_extraction(root: Path, factor: int, source: Path, requested: list[str], suite: dict, metric: dict):
    """Restore verified raw facts from the earlier real extraction, never old results."""
    root = root.resolve(strict=True)
    old = root / f"scale-{factor}x"
    prior = load_json_regular(old / "metrics.json")
    selected_methods = load_json_regular(old / "selection.json")
    if prior.get("status") != "complete" or prior.get("factor") != factor:
        raise ValueError("reuse requires a completed matching prior scale group")
    if prior.get("base_source_sha256") != metric["base_source_sha256"] or prior.get("cases_sha256") != metric["cases_sha256"]:
        raise ValueError("frozen base source or case manifest changed since extraction")
    if selected_methods.get("entry_methods") != requested or selected_methods.get("renamed_copies") != factor:
        raise ValueError("prior selection differs from the exact frozen method set")
    reader = ShardReader(old / "run")
    identity = reader.index["identity"]
    if identity.get("analysis_status") != "complete" or identity.get("source_kind") != "static_verified" or identity.get("unit_count") != len(requested):
        raise ValueError("prior source extraction identity is incomplete")
    files, source_hash = commands._java_source_snapshot(old / "source")
    if source_hash != identity.get("source_snapshot_sha256") or source_hash != prior.get("source_snapshot_sha256"):
        raise ValueError("prior source does not match frozen extraction")
    if set(files) != {f"fixture/lifecyclev11/SourcePairsScale{i:03d}.java" for i in range(1, factor + 1)}:
        raise ValueError("prior source contains unexpected files")
    for name in sorted(files):
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old / "source" / name, target)
    if commands._java_source_snapshot(source)[1] != source_hash:
        raise ValueError("copied source changed identity")
    singles = []
    observed_ids = set()
    query_provenance = None
    # Historical v1 store has no mandatory catalog. Validate its complete unit
    # inventory against frozen selection here; new outputs use iter_run_units.
    records = iter_run_units(reader) if identity.get("run_format") == "lifecycle-run-2" else reader.iter_objects()
    for unit_id, payload in records:
        if unit_id not in requested or unit_id in observed_ids or payload.get("status") != "analyzed":
            raise ValueError("prior unit inventory is missing, duplicated, or foreign")
        single = validate_extracted(extracted_from_dict(payload["facts"]))
        if len(single.units) != 1 or single.units[0].unit_id != unit_id:
            raise ValueError("prior facts disagree with the requested unit identity")
        if single.source_kind != "static_verified" or single.coverage.get("source_snapshot_sha256") != source_hash:
            raise ValueError("prior facts are not bound to the verified real source")
        if asdict(single.budget) != suite["budget"] or single.extractor_version != identity.get("extractor_version"):
            raise ValueError("prior facts changed extraction/budget identity")
        provenance = single.coverage.get("query_provenance")
        if query_provenance is None:
            query_provenance = provenance
        if not provenance or provenance != query_provenance:
            raise ValueError("prior unit query provenance is inconsistent")
        singles.append(single)
        observed_ids.add(unit_id)
    if observed_ids != set(requested):
        raise ValueError("prior raw facts do not cover every requested method")
    combined = replace(singles[0], units=tuple(item.units[0] for item in singles),
                       facts=tuple(fact for item in singles for fact in item.facts))
    extracted = select_requested(combined, requested)
    if extracted.snapshot_sha256 != identity.get("input_snapshot_sha256") or len(extracted.facts) != prior.get("raw_fact_count"):
        raise ValueError("restored whole-run raw fact identity differs from original")
    def record(path):
        try:
            name = path.relative_to(ROOT).as_posix()
        except ValueError:
            name = str(path)
        return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    metric.update(extraction_reused=True, database_seconds=None, extraction_seconds=None,
        all_extracted_raw_facts=prior.get("all_extracted_raw_facts"), all_extracted_units=prior.get("all_extracted_units"),
        excluded_unit_count=prior.get("excluded_unit_count"),
        reused_extraction={"metrics": record(old / "metrics.json"), "selection": record(old / "selection.json"),
            "run_index": record(old / "run/run-index.json"),
            "compilation_log": record(old / "logs/database-create.log"),
            "prior_database_seconds": prior.get("database_seconds"), "prior_extraction_seconds": prior.get("extraction_seconds"),
            "database_fingerprint": extracted.coverage.get("database_fingerprint"), "query_provenance": query_provenance,
            "source_snapshot_sha256": source_hash,
            "note": "Original real javac/CodeQL extraction reused; no compilation or query execution in this run."})
    return extracted


def worker(args) -> int:
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    logs = output / "logs"
    logs.mkdir()
    metric = {"factor": args.worker_factor, "status": "running", "independent_projects": 0,
        "interpretation": "renamed copies of one compiled fixture; storage/performance only",
        "base_source": SOURCE.relative_to(ROOT).as_posix(),
        "base_source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest()}
    atomic_write_json(output / "metrics.json", metric)
    started = time.monotonic()
    try:
        suite = load_json_regular(CASES)
        cases = suite["cases"]
        entries = sorted({case["entry_callable"] for case in cases})
        if len(entries) != 12:
            raise ValueError("frozen v1.1 source suite must declare exactly twelve methods")
        source = output / "source"
        package = source / "fixture/lifecyclev11"
        original = SOURCE.read_text(encoding="utf-8")
        requested = []
        for index in range(1, args.worker_factor + 1):
            name = f"SourcePairsScale{index:03d}"
            requested.extend(entry.replace(".SourcePairs.", f".{name}.") for entry in entries)
        metric["requested_units"] = len(requested)
        atomic_write_json(output / "selection.json", {"source_fixture": metric["base_source"],
            "renamed_copies": args.worker_factor, "entry_methods": requested,
            "expected_labels_used_by_analysis": False})
        if args.reuse_from is not None:
            restored_start = time.monotonic()
            selected = reuse_extraction(args.reuse_from, args.worker_factor, source, requested, suite, metric)
            metric["fact_restore_seconds"] = time.monotonic() - restored_start
        else:
            metric["extraction_reused"] = False
            package.mkdir(parents=True)
            for index in range(1, args.worker_factor + 1):
                name = f"SourcePairsScale{index:03d}"
                (package / f"{name}.java").write_text(re.sub(r"\bSourcePairs\b", name, original), encoding="utf-8")
            database = output / "database"
            classes = output / "classes"
            classes.mkdir()
            java_files = sorted(path.relative_to(source).as_posix() for path in source.rglob("*.java"))
            javac = shutil.which(args.javac)
            codeql = shutil.which(args.codeql_binary)
            if javac is None or codeql is None:
                raise RuntimeError("configured javac or codeql executable is unavailable")
            compile_argv = [javac, "-d", str(classes), *java_files]
            database_argv = [codeql, "database", "create", str(database), "--language=java",
                f"--source-root={source}", "--command=" + shlex.join(compile_argv)]
            metric["database_seconds"] = run_command(database_argv, source, logs / "database-create.log", args.timeout_seconds)
            extraction_start = time.monotonic()
            extracted = commands._codeql_facts({"schema_version": SCHEMA_VERSION, "mode": "codeql_database",
                "database": str(database), "entry_methods": requested, "budget": suite["budget"]},
                {"codeql_binary": codeql}, output / "extraction")
            metric["extraction_seconds"] = time.monotonic() - extraction_start
            metric["all_extracted_raw_facts"] = len(extracted.facts)
            metric["all_extracted_units"] = len(extracted.units)
            selected = select_requested(extracted, requested)
            metric["excluded_unit_count"] = len(extracted.units) - len(selected.units)
            del extracted
        metric["raw_fact_count"] = len(selected.facts)
        metric["source_snapshot_sha256"] = selected.coverage["source_snapshot_sha256"]
        run_dir = output / "run"
        shard_budget = ShardBudget()
        solve = commands.solve
        observations = []

        def observe_solve(*positional, **keyword):
            analysis = solve(*positional, **keyword)
            observations.append({"event_states": len(analysis.event_states),
                "property_states": sum(len(states) for states in analysis.property_states.values()),
                "async_states": sum(len(states) for states in analysis.async_states.values()),
                "steps": analysis.steps, "terminated": analysis.terminated})
            return analysis

        analysis_start = time.monotonic()
        commands.solve = observe_solve
        try:
            receipt = analyze_sharded(selected, run_dir, source_root=source, budget=shard_budget)
        finally:
            commands.solve = solve
        metric["analysis_seconds"] = time.monotonic() - analysis_start
        metric["solver_event_state_count"] = sum(item["event_states"] for item in observations)
        metric["solver_property_state_count"] = sum(item["property_states"] for item in observations)
        metric["solver_async_state_count"] = sum(item["async_states"] for item in observations)
        metric["solver_steps"] = sum(item["steps"] for item in observations)
        metric["state_count_definition"] = "event_states at solver return; property/async views reported separately, not added as independent states"
        metric["analysis_receipt"] = {key: value for key, value in receipt.items() if key != "index"}
        property_count = 0
        for _unit_id, payload in iter_run_units(ShardReader(run_dir, shard_budget)):
            if payload.get("status") == "analyzed":
                property_count += sum(len(unit["properties"]) for unit in payload["results"]["units"])
        metric["property_count"] = property_count
        files = [path for path in run_dir.rglob("*") if path.is_file()]
        metric["serialized_bytes"] = sum(path.stat().st_size for path in files)
        metric["max_shard_bytes"] = max((path.stat().st_size for path in files), default=0)
        metric["shard_file_count"] = len(files)
        metric["exceeds_old_single_file_limit"] = metric["serialized_bytes"] > OLD_LIMIT
        metric["every_shard_within_old_limit"] = metric["max_shard_bytes"] <= OLD_LIMIT
        relocated = output / "relocated"
        relocated.mkdir()
        shutil.copytree(run_dir, relocated / "run")
        shutil.copytree(source, relocated / "source")
        replay_start = time.monotonic()
        metric["replay"] = replay_sharded(relocated / "run", relocated / "source", budget=shard_budget)
        metric["replay_seconds"] = time.monotonic() - replay_start
        if receipt["analysis_status"] != "complete" or metric["replay"]["mode"] != "semantic_replay":
            raise RuntimeError("analysis or full relocated semantic replay did not complete")
        metric["status"] = "complete"
    except Exception as exc:
        (logs / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        metric.update(status="failed", failure_type=type(exc).__name__, failure=str(exc))
    metric["total_seconds"] = time.monotonic() - started
    # Worker per factor gives an independent high-water mark. RUSAGE_SELF omits javac/CodeQL children.
    metric["peak_analyzer_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    metric["rss_scope"] = "fresh Python worker (extraction, analysis, serialization, replay); excludes external compiler/CodeQL processes"
    atomic_write_json(output / "metrics.json", metric)
    return 0 if metric["status"] == "complete" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new persistent experiment directory")
    parser.add_argument("--codeql-binary", default="codeql")
    parser.add_argument("--javac", default="javac")
    parser.add_argument("--timeout-seconds", type=int, default=1800, help="database-create subprocess deadline")
    parser.add_argument("--reuse-from", type=Path, help="completed earlier scaling root; reuse verified real extraction without javac/CodeQL")
    parser.add_argument("--worker-factor", type=int, choices=(1, 2, 4), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    if args.worker_factor is not None:
        return worker(args)
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for factor in (1, 2, 4):
        group = output / f"scale-{factor}x"
        argv = [sys.executable, str(Path(__file__).resolve()), "--out", str(group),
                "--worker-factor", str(factor), "--codeql-binary", args.codeql_binary,
                "--javac", args.javac, "--timeout-seconds", str(args.timeout_seconds)]
        if args.reuse_from is not None:
            argv.extend(["--reuse-from", str(args.reuse_from.resolve(strict=True))])
        with (output / f"scale-{factor}x-worker.log").open("w", encoding="utf-8") as log:
            log.write(json.dumps({"argv": argv}) + "\n")
            log.flush()
            process = subprocess.run(argv, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=False)
        if (group / "metrics.json").is_file():
            row = load_json_regular(group / "metrics.json")
        else:
            row = {"factor": factor, "status": "failed", "failure": "worker produced no metric receipt"}
        row["worker_exit_code"] = process.returncode
        rows.append(row)
        atomic_write_json(output / "scaling-results.json", {"status": "running", "groups": rows})
    all_complete = all(row["status"] == "complete" and row["worker_exit_code"] == 0 for row in rows)
    scale_gate = any(row.get("exceeds_old_single_file_limit") and row.get("every_shard_within_old_limit")
                     and row["status"] == "complete" for row in rows)
    report = {"experiment": "lifecycle-v1.2-fixed-fixture-scaling", "independent_projects": 0,
        "interpretation": "1x/2x/4x renamed copies; no generalization claim", "groups": rows,
        "old_single_file_limit_bytes": OLD_LIMIT, "all_groups_complete": all_complete,
        "real_bytes_exceed_old_limit_with_full_replay": scale_gate,
        "status": "passed" if all_complete and scale_gate else "acceptance_not_met"}
    atomic_write_json(output / "scaling-results.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "groups"}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
