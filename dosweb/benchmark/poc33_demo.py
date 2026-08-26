"""Read-only post-hoc evaluator for the PoC-33 21-library demo.

This module is benchmark-only.  Production analysis must never import it or
consume any dynamic result passed to it.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


DYNAMIC_CASE_CLASSES = (
    "eligible_positive",
    "hard_negative",
    "weak_negative",
    "unscored",
)

HARD_NEGATIVE_STATUSES = frozenset(
    {
        "effective_bound_confirmed",
        "default_not_reachable",
        "auth_blocked",
        "precondition_blocked",
    }
)

WEAK_NEGATIVE_STATUSES = frozenset(
    {
        "observed_growth_not_confirmed",
        "probe_semantics_failed",
        "not_reproduced_under_tested_bounds",
        "inconclusive_probe",
    }
)

ORDINARY_ATTACKER_MODELS = frozenset(
    {"anonymous", "low_privilege", "device_token"}
)

STATIC_VERDICTS = frozenset(
    {
        "static_vulnerable",
        "bounded_under_modeled_assumptions",
        "static_unknown",
    }
)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def classify_dynamic_case(result: Mapping[str, object]) -> str:
    """Return eligible_positive, hard_negative, weak_negative, or unscored.

    A dynamic failure is eligible only when the evidence establishes a default
    deployment and an ordinary attacker model without an admin, optional
    component, or configuration-change prerequisite.  A mere failure to
    reproduce is deliberately not a hard negative.
    """

    status = result.get("status")
    if status in HARD_NEGATIVE_STATUSES:
        return "hard_negative"

    if result.get("verdict") == "confirmed":
        deployment = _mapping(result.get("default_deployment"))
        reachability = _mapping(result.get("reachability"))
        conditions = _mapping(result.get("utilization_conditions"))
        if (
            deployment.get("is_default") is True
            and reachability.get("attacker_model") in ORDINARY_ATTACKER_MODELS
            and conditions.get("requires_admin") is False
            and conditions.get("requires_config_change") is False
            and conditions.get("requires_optional_component") is False
        ):
            return "eligible_positive"
        return "unscored"

    if status in WEAK_NEGATIVE_STATUSES:
        return "weak_negative"
    return "unscored"


def _static_verdict(row: Mapping[str, object]) -> str | None:
    for key in ("verdict", "static_conclusion", "pipeline_verdict"):
        value = row.get(key)
        if value in STATIC_VERDICTS:
            return str(value)
    return None


def _finding_ids(row: Mapping[str, object]) -> set[str]:
    result: set[str] = set()
    direct = row.get("finding_id")
    if isinstance(direct, str) and direct:
        result.add(direct)
    for key in ("member_finding_ids", "family_finding_ids"):
        values = row.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            result.update(value for value in values if isinstance(value, str) and value)
    return result


def _family_identity(row: Mapping[str, object], index: int) -> str:
    for key in ("family_id", "family_key", "cluster_id", "finding_id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return f"row:{index}"


def _static_index(
    static_findings: Sequence[Mapping[str, object]],
) -> tuple[dict[str, set[str]], set[str]]:
    verdicts_by_finding: dict[str, set[str]] = defaultdict(set)
    families: set[str] = set()
    for index, row in enumerate(static_findings):
        families.add(_family_identity(row, index))
        verdict = _static_verdict(row)
        for finding_id in _finding_ids(row):
            if verdict is not None:
                verdicts_by_finding[finding_id].add(verdict)
            else:
                verdicts_by_finding.setdefault(finding_id, set())
    return dict(verdicts_by_finding), families


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def build_demo_metrics(
    *,
    statuses: Sequence[Mapping[str, object]],
    truth_dispositions: Sequence[Mapping[str, object]],
    static_findings: Sequence[Mapping[str, object]],
    dynamic_results: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    """Build infrastructure, recall, hard-negative, queue, and dedup metrics."""

    completed_targets = sum(
        1
        for row in statuses
        if row.get("authoritative_status", row.get("status")) == "completed"
    )
    selected_queries = 0
    query_diagnostics = 0
    skipped_queries = 0
    for row in statuses:
        entries = _mapping(_mapping(row.get("stage_metrics")).get("entries"))
        selected_queries += int(entries.get("query_count") or 0)
        query_diagnostics += int(entries.get("query_diagnostic_count") or 0)
        skipped_queries += int(entries.get("skipped_query_count") or 0)

    truth_statuses = Counter(
        str(row.get("status") or "missing") for row in truth_dispositions
    )
    full_chain = truth_statuses["full_chain_finding"]

    static_by_finding, families = _static_index(static_findings)
    static_verdict_counts = Counter(
        _static_verdict(row) or "missing" for row in static_findings
    )

    taxonomy_counts = Counter(
        classify_dynamic_case(row) for row in dynamic_results
    )
    selected_dynamic = [
        row
        for row in dynamic_results
        if isinstance(row.get("finding_id"), str)
        and row.get("finding_id") in static_by_finding
    ]
    verdict_counts = Counter(
        str(row.get("verdict") or "missing") for row in selected_dynamic
    )
    tp = verdict_counts["confirmed"]
    fp = verdict_counts["not_confirmed"]
    blocked = verdict_counts["blocked"]

    eligible_positive_static_vulnerable = 0
    hard_negative_static_vulnerable = 0
    for row in dynamic_results:
        finding_id = row.get("finding_id")
        verdicts = static_by_finding.get(finding_id, set()) if isinstance(finding_id, str) else set()
        if "static_vulnerable" not in verdicts:
            continue
        classification = classify_dynamic_case(row)
        if classification == "eligible_positive":
            eligible_positive_static_vulnerable += 1
        elif classification == "hard_negative":
            hard_negative_static_vulnerable += 1

    eligible_positive = taxonomy_counts["eligible_positive"]
    hard_negative = taxonomy_counts["hard_negative"]
    hard_negative_safe = hard_negative - hard_negative_static_vulnerable

    return {
        "format": "dosweb-poc33-demo-evaluation-v1",
        "targets": len(statuses),
        "completed_targets": completed_targets,
        "formal_completed": completed_targets == len(statuses) and bool(statuses),
        "selected_queries": selected_queries,
        "query_diagnostics": query_diagnostics,
        "skipped_queries": skipped_queries,
        "truth": len(truth_dispositions),
        "full_chain_finding": full_chain,
        "truth_status_counts": dict(sorted(truth_statuses.items())),
        "supported_chain_recall": {
            "numerator": full_chain,
            "denominator": len(truth_dispositions),
            "ratio": _ratio(full_chain, len(truth_dispositions)),
        },
        "queue": len(static_findings),
        "families": len(families),
        "static_verdict_counts": dict(sorted(static_verdict_counts.items())),
        "eligible_positive": eligible_positive,
        "hard_negative": hard_negative,
        "weak_negative": taxonomy_counts["weak_negative"],
        "unscored": taxonomy_counts["unscored"],
        "dynamic_case_class_counts": {
            name: taxonomy_counts[name] for name in DYNAMIC_CASE_CLASSES
        },
        "tp": tp,
        "fp": fp,
        "blocked": blocked,
        "precision": _ratio(tp, tp + fp),
        "eligible_positive_static_vulnerable": eligible_positive_static_vulnerable,
        "hard_negative_static_vulnerable": hard_negative_static_vulnerable,
        "ordinary_positive_recall": {
            "numerator": eligible_positive_static_vulnerable,
            "denominator": eligible_positive,
            "ratio": _ratio(eligible_positive_static_vulnerable, eligible_positive),
        },
        "hard_negative_safety": {
            "numerator": hard_negative_safe,
            "denominator": hard_negative,
            "ratio": _ratio(hard_negative_safe, hard_negative),
        },
        "dynamic_verdict_counts": dict(sorted(verdict_counts.items())),
    }


def build_case_matrix(
    *,
    static_findings: Sequence[Mapping[str, object]],
    dynamic_results: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Join dynamic cases to static output without mutating either input."""

    static_by_finding, _ = _static_index(static_findings)
    rows: list[dict[str, object]] = []
    for result in dynamic_results:
        finding_id = result.get("finding_id")
        verdicts = (
            sorted(static_by_finding.get(finding_id, set()))
            if isinstance(finding_id, str)
            else []
        )
        deployment = _mapping(result.get("default_deployment"))
        reachability = _mapping(result.get("reachability"))
        conditions = _mapping(result.get("utilization_conditions"))
        rows.append(
            {
                "case_id": result.get("case_id"),
                "finding_id": finding_id,
                "target": result.get("target"),
                "dynamic_status": result.get("status"),
                "dynamic_verdict": result.get("verdict"),
                "demo_class": classify_dynamic_case(result),
                "selected_by_static": bool(verdicts) or (
                    isinstance(finding_id, str) and finding_id in static_by_finding
                ),
                "static_verdicts": verdicts,
                "static_vulnerable": "static_vulnerable" in verdicts,
                "default_deployment": deployment.get("is_default"),
                "attacker_model": reachability.get("attacker_model"),
                "requires_admin": conditions.get("requires_admin"),
                "requires_config_change": conditions.get("requires_config_change"),
                "requires_optional_component": conditions.get("requires_optional_component"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("target") or ""),
            str(row.get("finding_id") or ""),
            str(row.get("case_id") or ""),
        ),
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: expected a regular JSONL file")
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        rows.append(value)
    return rows


def _input_root(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} must be a regular directory: {path}")
    return path.resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _prepare_output(path: Path, input_roots: Sequence[Path]) -> Path:
    if path.is_symlink():
        raise ValueError(f"output must not be a symlink: {path}")
    output = path.resolve()
    if any(_is_relative_to(output, root) for root in input_roots):
        raise ValueError("output must be outside all read-only input roots")
    if output.exists() and not output.is_dir():
        raise ValueError(f"output must be a directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    return output


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _report(metrics: Mapping[str, object]) -> str:
    recall = _mapping(metrics.get("supported_chain_recall"))
    positive = _mapping(metrics.get("ordinary_positive_recall"))
    negative = _mapping(metrics.get("hard_negative_safety"))
    return "\n".join(
        [
            "# PoC-33 21-Library Demo Evaluation",
            "",
            "## Infrastructure",
            "",
            f"- targets: {metrics['completed_targets']}/{metrics['targets']} completed",
            f"- selected queries: {metrics['selected_queries']}",
            f"- query diagnostics: {metrics['query_diagnostics']}",
            f"- skipped queries: {metrics['skipped_queries']}",
            "",
            "## Supported-chain recall",
            "",
            f"- full chain: {recall.get('numerator')}/{recall.get('denominator')} ({recall.get('ratio')})",
            "",
            "## Dynamic case taxonomy",
            "",
            f"- eligible positives: {metrics['eligible_positive']}",
            f"- hard negatives: {metrics['hard_negative']}",
            f"- weak negatives: {metrics['weak_negative']}",
            f"- unscored: {metrics['unscored']}",
            "",
            "## Static gates",
            "",
            f"- ordinary positive recall: {positive.get('numerator')}/{positive.get('denominator')} ({positive.get('ratio')})",
            f"- hard-negative safety: {negative.get('numerator')}/{negative.get('denominator')} ({negative.get('ratio')})",
            "",
            "## Historical queue score",
            "",
            f"- queue: {metrics['queue']}",
            f"- TP / FP / blocked: {metrics['tp']} / {metrics['fp']} / {metrics['blocked']}",
            f"- precision TP/(TP+FP): {metrics['precision']}",
            "",
            "Dynamic evidence is used only for this post-hoc evaluation; it does not rewrite static artifacts.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-batch", type=Path, required=True)
    parser.add_argument("--recall", type=Path, required=True)
    parser.add_argument(
        "--static-audit",
        type=Path,
        help="historical baseline only; otherwise read finding_families.jsonl from --static-batch",
    )
    parser.add_argument("--dynamic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    static_batch = _input_root(args.static_batch, "--static-batch")
    recall = _input_root(args.recall, "--recall")
    dynamic = _input_root(args.dynamic, "--dynamic")
    input_roots = [static_batch, recall, dynamic]
    static_audit = None
    if args.static_audit is not None:
        static_audit = _input_root(args.static_audit, "--static-audit")
        input_roots.append(static_audit)
    output = _prepare_output(args.output, input_roots)

    status_path = static_batch / "aggregate_status.jsonl"
    if not status_path.is_file():
        status_path = static_batch / "status.jsonl"
    statuses = _read_jsonl(status_path)
    truth_dispositions = _read_jsonl(recall / "truth_dispositions.jsonl")
    if static_audit is not None:
        static_findings = _read_jsonl(static_audit / "static_positive_queue.jsonl")
    else:
        static_findings = _read_jsonl(static_batch / "finding_families.jsonl")
    dynamic_results = [
        *_read_jsonl(dynamic / "findings.jsonl"),
        *_read_jsonl(dynamic / "blocked_or_rejected.jsonl"),
    ]

    metrics = build_demo_metrics(
        statuses=statuses,
        truth_dispositions=truth_dispositions,
        static_findings=static_findings,
        dynamic_results=dynamic_results,
    )
    case_matrix = build_case_matrix(
        static_findings=static_findings,
        dynamic_results=dynamic_results,
    )
    _write_jsonl(output / "case_matrix.jsonl", case_matrix)
    _write_json(output / "metrics.json", metrics)
    (output / "REPORT.md").write_text(_report(metrics), encoding="utf-8")
    return 0


__all__ = [
    "DYNAMIC_CASE_CLASSES",
    "HARD_NEGATIVE_STATUSES",
    "WEAK_NEGATIVE_STATUSES",
    "build_case_matrix",
    "build_demo_metrics",
    "classify_dynamic_case",
    "main",
]

