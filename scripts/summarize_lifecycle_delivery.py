#!/usr/bin/env python3
"""Derive public lifecycle delivery metrics from completed local runs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import xml.etree.ElementTree as ET


def load(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def profile(facts):
    kinds = Counter(row["fact_kind"] for row in facts["facts"])
    return {
        "raw_facts": len(facts["facts"]), "fact_kinds": dict(sorted(kinds.items())),
        "units": len(facts["units"]),
        "relations": {key: sum(len(unit["program"].get(key, [])) for unit in facts["units"]) for key in ("call_bindings", "task_bindings", "task_exits", "program_points")},
        "source_snapshot_sha256": facts["coverage"]["source_snapshot_sha256"],
        "matched_entries": facts["coverage"]["matched_entry_methods"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("manual_run", type=Path)
    parser.add_argument("final_xml", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ready-for-push", action="store_true", help="Record completed delivery review; does not claim a push occurred")
    args = parser.parse_args()
    before = profile(load(args.baseline))
    after = profile(load(args.source_run / "facts.json"))
    assert before["source_snapshot_sha256"] == after["source_snapshot_sha256"]
    assert before["matched_entries"] == after["matched_entries"]
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output / "extraction-coverage-diff.json", {
        "baseline_commit": "f62d6f2343d160a320dbb7aaec6d22c307d892f0",
        "baseline": before, "current": after,
        "comparison": "Same Java database and twelve entries; old versus current extractor. Separate from fixed-facts propagation ablation; fact counts are not detection rates.",
    })
    metrics = load(args.source_run / "metrics.json")
    manual = load(args.manual_run / "metrics.json")
    metrics["manual_ir"] = {"cases": manual["source_breakdown"]["manual_ir"], "full": manual["modes"]["full"], "suite_sha256": manual["suite_sha256"], "source_kind": "manual_fixture"}
    contract_counts = Counter()
    for case in ET.fromstring(args.final_xml.read_bytes()).iter("testcase"):
        if case.get("classname", "").endswith(("ResourceLifecycleCodeqlContractTests", "ResourceLifecycleSourceEvaluationContractTests")):
            outcome = "failed" if case.find("failure") is not None else "error" if case.find("error") is not None else "skipped" if case.find("skipped") is not None else "passed"
            contract_counts[outcome] += 1
    metrics["contract_tests"] = {"counts": dict(contract_counts), "scope": "ResourceLifecycleCodeqlContractTests and ResourceLifecycleSourceEvaluationContractTests; separate from Java/CodeQL cases."}
    metrics["source_rates"] = {mode: values["unknown"] / values["cases"] for mode, values in metrics["modes"].items()}
    metrics["entry_extraction"] = {"matched": len(after["matched_entries"]), "requested": len(load(args.source_run / "run-manifest.json")["entry_methods"])}
    metrics["external_project_count"] = 0
    write(args.output / "metrics.json", metrics)
    manifest = load(args.source_run / "run-manifest.json")
    manifest["contracts_versions"] = sorted({unit["program"]["contracts_version"] for unit in load(args.source_run / "facts.json")["units"]})
    manifest["analyzed_code_parent_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest["analyzed_worktree_modified_paths"] = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], text=True).splitlines()
    manifest["code_identity_note"] = "implementation_sha256 binds actual analyzed files, including uncommitted changes; parent commit alone is not the analyzed implementation."
    manifest["environment"] = {"python": platform.python_version(), "platform": platform.system(), "codeql": subprocess.check_output(["codeql", "version", "--format=json"], text=True).strip(), "javac": subprocess.check_output(["javac", "-version"], stderr=subprocess.STDOUT, text=True).strip()}
    manifest["commands"] = {
        "source": "python3 -m dosweb.cli resource-source-evaluate --suite tests/fixtures/resource_lifecycle_v1_1/source-cases.json --source-root tests/fixtures/resource_lifecycle_v1_1/src/main/java --database /tmp/dosweb-fixture-codeql-2/fcdd115f927f99bf.db --out " + str(args.source_run),
        "baseline_tests": "python3 -m pytest -q --continue-on-collection-errors --junitxml=/tmp/lifecycle-v11-baseline-continued-20260914.xml",
        "final_tests": "DOSWEB_G8_CACHED_FACTS=/tmp/lifecycle-v11-g8-single-facts/facts.json python3 -m pytest -q --continue-on-collection-errors --junitxml=" + str(args.final_xml),
        "manual": "python3 -m dosweb.cli resource-evaluate --suite tests/fixtures/resource_lifecycle/regression-suite.json --out /tmp/lifecycle-v11-g8-manual-20260914",
    }
    manifest["final_test_xml_sha256"] = hashlib.sha256(args.final_xml.read_bytes()).hexdigest()
    manifest["delivery_state_at_commit"] = "ready_for_push" if args.ready_for_push else "blocked"
    write(args.output / "run-manifest.json", manifest)


if __name__ == "__main__":
    main()
