#!/usr/bin/env python3
"""Assemble bounded post-hoc evidence using the existing PoC-33 evaluator.

Reads authenticated frozen facts and an already completed downstream replay.
Never runs target code, PoCs, CodeQL, a model, or a static-analysis discovery loop.
The oracle and historical dynamic records are used only after analysis.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from dosweb.benchmark import poc33_demo as evaluator


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def csv_rows(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("batch", "recall", "dynamic", "replay", "audit", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    batch, recall, dynamic, replay, audit, out = (
        getattr(args, name).resolve() for name in ("batch", "recall", "dynamic", "replay", "audit", "output")
    )
    if out.exists() or any(out == root or root in out.parents for root in (batch, recall, dynamic, replay, audit)):
        raise ValueError("Output must be new and outside every immutable input.")
    manifest = json.loads((replay / "run-manifest.json").read_text())
    if not manifest["source_stable_during_replay"] or any(p["status"] != "completed" for p in manifest["projects"]):
        raise ValueError("This final assembler requires a complete stable replay; inspect failed runs separately.")
    if digest(batch / "aggregate_status.jsonl") != manifest["input_status_sha256"]:
        raise ValueError("Frozen project status identity changed.")
    frozen_audit = json.loads((audit / "prerequisite-audit.json").read_text())
    for name, expected in frozen_audit["consumed_aggregate_sha256"].items():
        if digest(batch / name) != expected:
            raise ValueError("Frozen consumed artifact changed: " + name)
    statuses = jsonl(batch / "aggregate_status.jsonl")
    projects = {p["project_id"]: p for p in manifest["projects"]}
    if set(projects) != {p["batch_target_slug"] for p in statuses}:
        raise ValueError("Project cohort changed.")
    findings, families, certificates = [], [], []
    for slug, project in projects.items():
        directory = (replay / slug).resolve()
        if not directory.is_relative_to(replay):
            raise ValueError("Replay project escaped its root.")
        for name, destination in (("static_findings.jsonl", findings), ("finding_families.jsonl", families), ("lifecycle_certificates.jsonl", certificates)):
            path = directory / name
            if digest(path) != project["produced_artifacts"][name]:
                raise ValueError("Replay artifact changed: " + name)
            destination.extend({**row, "batch_target_slug": slug} for row in jsonl(path))
    transitions = jsonl(replay / "finding-transitions.jsonl")
    if any(t["before"] == "absent" or t["after"] == "absent" for t in transitions):
        raise ValueError("Candidate-set change requires separate review, not silent remapping.")
    remap = {t["old_finding_id"]: t["new_finding_id"] for t in transitions}
    if len(remap) != len(transitions) or len(set(remap.values())) != len(remap):
        raise ValueError("Finding identity remap is ambiguous.")
    current_findings = {r["finding_id"]: r for r in findings}
    if set(current_findings) != set(remap.values()):
        raise ValueError("Replay findings do not match the declared transitions.")
    original_truth = jsonl(recall / "truth_dispositions.jsonl")
    truth = []
    for row in original_truth:
        updated = dict(row)
        for field in ("finding_id", "member_finding_ids", "family_finding_ids", "matched_finding_ids"):
            value = row.get(field)
            if isinstance(value, str):
                updated[field] = remap.get(value, value)
            elif isinstance(value, list):
                updated[field] = [remap.get(item, item) for item in value]
        truth.append(updated)
    dynamic_rows = jsonl(dynamic / "findings.jsonl") + jsonl(dynamic / "blocked_or_rejected.jsonl")
    new_statuses = [{**r, "authoritative_status": projects[r["batch_target_slug"]]["status"], "status": projects[r["batch_target_slug"]]["status"]} for r in statuses]
    baseline = evaluator.build_demo_metrics(statuses=statuses, truth_dispositions=original_truth,
        static_findings=jsonl(batch / "aggregate_finding_families.jsonl"), dynamic_results=dynamic_rows,
        final_findings=jsonl(batch / "aggregate_findings.jsonl"))
    metrics = dict(evaluator.build_demo_metrics(statuses=new_statuses, truth_dispositions=truth,
        static_findings=families, dynamic_results=dynamic_rows, final_findings=findings))
    metrics.update(execution_scope="authenticated_frozen_downstream_replay", fresh_full_scan=False,
        queries_newly_executed=0, llm_calls_new=0, target_programs_executed=0,
        selected_queries_semantics="Inherited frozen entries-stage query selection, not new execution",
        findings=len(findings), bridge=frozen_audit["bridge"],
        paired_full_off_rerun=False, paired_full_off_gain=None,
        before_after_formal_match_gain=metrics["known_case_matches"] - baseline["known_case_matches"],
        overall_tool_acceptance="fail" if metrics["known_case_matches"] != len(original_truth) else "requires_quality_review")
    out.mkdir(parents=True)
    write_json(out / "corrected-baseline-metrics.json", baseline)
    write_json(out / "metrics.json", metrics)
    (out / "evaluation.md").write_text(evaluator._report(metrics))
    (out / "finding-transitions.jsonl").write_bytes((replay / "finding-transitions.jsonl").read_bytes())
    write_json(out / "frozen-prerequisite-audit.json", frozen_audit)
    write_json(out / "replay-run-manifest.json", manifest)
    by_member = {member: family["family_id"] for family in families for member in evaluator._finding_ids(family)}
    if set(by_member) != set(current_findings):
        raise ValueError("Family membership does not cover the complete finding population.")
    preconditions = []
    for row in csv_rows(audit / "prerequisite-status.csv"):
        previous = row["finding_id"]
        current = current_findings[remap[previous]]
        preconditions.append({**row, "baseline_finding_id": previous,
            "baseline_family_id": row["family_id"], "baseline_certificate_id": row["certificate_id"],
            "finding_id": current["finding_id"], "family_id": by_member[current["finding_id"]],
            "certificate_id": current["certificate_id"], "verdict": current["verdict"],
            "upstream_evidence_scope": "unchanged_authenticated_frozen_facts",
            "replay_evidence": f"{replay.name}/{current['batch_target_slug']}/lifecycle_certificates.jsonl#{current['certificate_id']}"})
    write_csv(out / "prerequisite-status.csv", preconditions)
    known = []
    for row in csv_rows(audit / "known-case-matches.csv"):
        previous = re.findall(r"finding:[0-9a-f]+", row["matched_finding_ids"])
        current = [remap.get(identifier, identifier) for identifier in previous]
        aliases = [r["record_id"] for r in original_truth if r.get("repository") == row["project_id"] and (r["record_id"] == row["record_id"] or r["record_id"].endswith("-" + row["record_id"]))]
        known.append({**row, "baseline_matched_finding_ids": row["matched_finding_ids"],
            "matched_finding_ids": json.dumps(current), "evaluator_record_id": aliases[0] if len(aliases) == 1 else "",
            "formal_detected": any(current_findings.get(identifier, {}).get("verdict") == "static_vulnerable" for identifier in current),
            "replay_run": replay.name})
    if len(known) != len(original_truth):
        raise ValueError("Known-case population changed.")
    write_csv(out / "known-case-matches.csv", known)
    unknown = [{"family_id": r["family_id"], "verdict": r["verdict"],
        "member_finding_ids": json.dumps(sorted(evaluator._finding_ids(r))),
        "prerequisite_evidence": "prerequisite-status.csv#family_id=" + r["family_id"]}
        for r in families if r["verdict"] == "static_unknown"]
    write_csv(out / "analysis-unknown.csv", unknown)
    positives = [{"family_id": r["family_id"], "review_status": "unreviewed", "evidence": ""}
        for r in families if r["verdict"] == "static_vulnerable"]
    write_csv(out / "positive-review.csv", positives, ["family_id", "review_status", "evidence"])
    write_json(out / "evaluation-inputs.json", {
        "batch": str(batch), "recall": str(recall), "dynamic": str(dynamic), "replay": str(replay), "audit": str(audit),
        "input_hashes": {str(p): digest(p) for p in [batch / "aggregate_status.jsonl", recall / "truth_dispositions.jsonl", dynamic / "findings.jsonl", dynamic / "blocked_or_rejected.jsonl", replay / "run-manifest.json", replay / "finding-transitions.jsonl", audit / "prerequisite-audit.json"]},
        "known_records_preserved": len(known), "known_aliases_resolved": sum(bool(r["evaluator_record_id"]) for r in known),
        "identity_changed_findings": sum(a != b for a, b in remap.items()),
        "oracle_used_by_production": False, "historical_dynamic_evidence_only": True,
        "assembler_sha256": digest(Path(__file__)),
    })
    print(json.dumps({key: metrics[key] for key in ["completed_targets", "findings", "analysis_unknown_families", "predicted_positive_families", "known_case_recall", "confirmed_precision", "precision_review_status", "overall_tool_acceptance"]}, indent=2))


if __name__ == "__main__":
    main()
