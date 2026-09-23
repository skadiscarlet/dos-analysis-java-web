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

# Mixed duplicate-family rows keep a predicted positive visible; they never
# collapse a static_vulnerable family into unknown or bounded.
_FAMILY_VERDICT_PRIORITY = (
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
)

HARD_NEGATIVE_SPLIT_CLASSES = (
    "determined_bounded",
    "analysis_unknown",
    "false_positive",
    "extraction_failure",
    "unmatched_static_evidence",
)

REVIEW_STATUSES = (
    "confirmed_positive",
    "false_positive",
    "unresolved",
)

PRECISION_THRESHOLD = 0.8
PRECISION_THRESHOLD_ORIGIN = "proposed_default"
PRECISION_REVIEW_NO_POSITIVE = "not_evaluable_no_positive"
PRECISION_REVIEW_PENDING = "pending_manual_review"
PRECISION_REVIEW_PASS = "pass"
PRECISION_REVIEW_FAIL = "fail"
FPR_NOT_MEASURED = "not_measured"


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
    index = _family_index(static_findings)
    return index["verdicts_by_finding"], index["families"]


def _classify_family_verdict(verdicts: set[str]) -> str | None:
    for verdict in _FAMILY_VERDICT_PRIORITY:
        if verdict in verdicts:
            return verdict
    return None


def _family_index(
    static_findings: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    verdicts_by_finding: dict[str, set[str]] = defaultdict(set)
    family_verdicts: dict[str, set[str]] = defaultdict(set)
    family_findings: dict[str, set[str]] = defaultdict(set)
    finding_to_family: dict[str, str] = {}
    families: set[str] = set()
    for index, row in enumerate(static_findings):
        family_id = _family_identity(row, index)
        families.add(family_id)
        verdict = _static_verdict(row)
        if verdict is not None:
            family_verdicts[family_id].add(verdict)
        else:
            family_verdicts.setdefault(family_id, set())
        finding_ids = _finding_ids(row)
        family_findings[family_id].update(finding_ids)
        for finding_id in finding_ids:
            if finding_id in finding_to_family and finding_to_family[finding_id] != family_id:
                raise ValueError("One finding cannot belong to different families")
            finding_to_family[finding_id] = family_id
            if verdict is not None:
                verdicts_by_finding[finding_id].add(verdict)
            else:
                verdicts_by_finding.setdefault(finding_id, set())
    classified = {
        family_id: _classify_family_verdict(verdicts)
        for family_id, verdicts in family_verdicts.items()
    }
    return {
        "verdicts_by_finding": dict(verdicts_by_finding),
        "families": families,
        "family_findings": {key: set(value) for key, value in family_findings.items()},
        "finding_to_family": finding_to_family,
        "classified_family_verdicts": classified,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def classify_hard_negative_outcome(verdicts: set[str] | Sequence[str]) -> str:
    """Split a hard-negative by the joined static verdict.

    Not reporting a positive is not a bounded proof.  Unjoined or
    unrecognized verdicts lack a static join; they do not prove extraction failed.
    """

    verdict_set = set(verdicts)
    if "static_vulnerable" in verdict_set:
        return "false_positive"
    if "static_unknown" in verdict_set:
        return "analysis_unknown"
    if "bounded_under_modeled_assumptions" in verdict_set:
        return "determined_bounded"
    if "extraction_failure" in verdict_set:
        return "extraction_failure"
    return "unmatched_static_evidence"


def _sequence_ids(value: object) -> set[str]:
    if isinstance(value, str) and value:
        return {value}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {item for item in value if isinstance(item, str) and item}
    return set()


def _truth_finding_ids(row: Mapping[str, object]) -> set[str]:
    ids = _finding_ids(row)
    ids.update(_sequence_ids(row.get("matched_finding_ids")))
    return ids


def _review_identity_families(
    review: Mapping[str, object],
    *,
    finding_to_family: Mapping[str, str],
) -> set[str]:
    families: set[str] = set()
    for key in ("family_id", "family_key", "cluster_id"):
        value = review.get(key)
        if isinstance(value, str) and value:
            families.add(value)
    for finding_id in _finding_ids(review):
        family_id = finding_to_family.get(finding_id)
        if family_id is not None:
            families.add(family_id)
    return families


def _positive_review_status(
    reviews: Sequence[Mapping[str, object]],
    *,
    family_id: str,
    finding_to_family: Mapping[str, str],
) -> str | None:
    statuses: set[str] = set()
    for review in reviews:
        if family_id not in _review_identity_families(
            review, finding_to_family=finding_to_family
        ):
            continue
        status = review.get("review_status")
        if status in REVIEW_STATUSES:
            statuses.add(str(status))
    if not statuses:
        return None
    if statuses == {"confirmed_positive"}:
        return "confirmed_positive"
    if statuses == {"false_positive"}:
        return "false_positive"
    return "unresolved"


def precision_review_metrics(
    *,
    predicted_positive: int,
    true_positives: int,
    false_positives: int,
    unreviewed_positives: int,
    threshold: float = PRECISION_THRESHOLD,
    threshold_origin: str = PRECISION_THRESHOLD_ORIGIN,
) -> dict[str, object]:
    """Precision over reviewed predicted positives only.

    Unknown families are not part of the review denominator.  Zero predicted
    positives are not evaluable: both precision figures stay null.
    """

    counts = (predicted_positive, true_positives, false_positives, unreviewed_positives)
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in counts):
        raise ValueError("Review counts must be nonnegative integers")
    if predicted_positive != true_positives + false_positives + unreviewed_positives:
        raise ValueError("Reviewed and unreviewed positives must partition predictions")
    confirmed_denominator = true_positives + false_positives
    conservative_denominator = confirmed_denominator + unreviewed_positives
    if predicted_positive == 0:
        status = PRECISION_REVIEW_NO_POSITIVE
        confirmed = None
        conservative = None
    else:
        confirmed = _ratio(true_positives, confirmed_denominator)
        conservative = _ratio(true_positives, conservative_denominator)
        if unreviewed_positives > 0:
            status = PRECISION_REVIEW_PENDING
        elif confirmed is not None and confirmed >= threshold:
            status = PRECISION_REVIEW_PASS
        else:
            status = PRECISION_REVIEW_FAIL
    return {
        "confirmed_precision": confirmed,
        "conservative_precision_lower_bound": conservative,
        "precision_review_status": status,
        "precision_threshold": threshold,
        "threshold_origin": threshold_origin,
        "false_positive_rate": FPR_NOT_MEASURED,
    }


def _explicit_deferred(row: Mapping[str, object]) -> bool:
    reasons = row.get("reason_codes")
    reason_set = {
        value for value in reasons
        if isinstance(value, str)
    } if isinstance(reasons, Sequence) and not isinstance(reasons, (str, bytes)) else set()
    return (
        row.get("status") == "growth_only"
        and {
            "ENTRY_DYNAMIC_REGISTRATION_UNPROVEN",
            "GROWTH_SINK_MATCHED",
        }.issubset(reason_set)
    )


def build_demo_metrics(
    *,
    statuses: Sequence[Mapping[str, object]],
    truth_dispositions: Sequence[Mapping[str, object]],
    static_findings: Sequence[Mapping[str, object]],
    dynamic_results: Sequence[Mapping[str, object]],
    reviews: Sequence[Mapping[str, object]] = (),
    final_findings: Sequence[Mapping[str, object]] | None = None,
) -> Mapping[str, object]:
    """Build infrastructure, recall, hard-negative, queue, and dedup metrics.

    Formal predicted positives are unique families whose final verdict is
    ``static_vulnerable``.  ``static_unknown`` and bounded families stay
    outside the review-positive denominator.
    """

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
    deferred = [row for row in truth_dispositions if _explicit_deferred(row)]
    supported = [row for row in truth_dispositions if not _explicit_deferred(row)]
    supported_full_chain = sum(
        1 for row in supported if row.get("status") == "full_chain_finding"
    )

    family_index = _family_index(static_findings)
    static_by_finding = family_index["verdicts_by_finding"]
    families = family_index["families"]
    classified_family_verdicts = family_index["classified_family_verdicts"]
    family_findings = family_index["family_findings"]
    finding_to_family = family_index["finding_to_family"]
    static_verdict_counts = Counter(
        _static_verdict(row) or "missing" for row in static_findings
    )
    family_verdict_counts = Counter(
        verdict or "missing" for verdict in classified_family_verdicts.values()
    )
    predicted_positive_family_ids = sorted(
        family_id
        for family_id, verdict in classified_family_verdicts.items()
        if verdict == "static_vulnerable"
    )
    analysis_unknown_family_ids = sorted(
        family_id
        for family_id, verdict in classified_family_verdicts.items()
        if verdict == "static_unknown"
    )
    bounded_family_ids = sorted(
        family_id
        for family_id, verdict in classified_family_verdicts.items()
        if verdict == "bounded_under_modeled_assumptions"
    )
    predicted_positive_findings: set[str] = set()
    for family_id in predicted_positive_family_ids:
        predicted_positive_findings.update(family_findings.get(family_id, set()))
    # A family-level positive cannot prove that every member is positive.
    exact_verdicts: dict[str, set[str]] = defaultdict(set)
    for row in final_findings if final_findings is not None else static_findings:
        direct = row.get("finding_id")
        members = _finding_ids(row)
        ids = {direct} if isinstance(direct, str) and direct else members if len(members) == 1 else set()
        verdict = _static_verdict(row)
        for finding_id in ids:
            if verdict is not None:
                exact_verdicts[finding_id].add(verdict)
    truth_matched_findings: set[str] = set()
    known_case_matches = 0
    for row in truth_dispositions:
        finding_ids = _truth_finding_ids(row)
        truth_matched_findings.update(finding_ids)
        if any(
            exact_verdicts.get(finding_id) == {"static_vulnerable"}
            for finding_id in finding_ids
        ):
            known_case_matches += 1
    novel_positive_families = sum(
        1
        for family_id in predicted_positive_family_ids
        if family_findings.get(family_id, set()).isdisjoint(truth_matched_findings)
    )
    reviewed_true_positives = 0
    reviewed_false_positives = 0
    unreviewed_positives = 0
    for family_id in predicted_positive_family_ids:
        status = _positive_review_status(
            reviews,
            family_id=family_id,
            finding_to_family=finding_to_family,
        )
        if status == "confirmed_positive":
            reviewed_true_positives += 1
        elif status == "false_positive":
            reviewed_false_positives += 1
        else:
            unreviewed_positives += 1
    precision_metrics = precision_review_metrics(
        predicted_positive=len(predicted_positive_family_ids),
        true_positives=reviewed_true_positives,
        false_positives=reviewed_false_positives,
        unreviewed_positives=unreviewed_positives,
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
    hard_negative_split: Counter[str] = Counter()
    for row in dynamic_results:
        finding_id = row.get("finding_id")
        verdicts = static_by_finding.get(finding_id, set()) if isinstance(finding_id, str) else set()
        classification = classify_dynamic_case(row)
        if classification == "hard_negative":
            hard_negative_split[classify_hard_negative_outcome(verdicts)] += 1
        if "static_vulnerable" not in verdicts:
            continue
        if classification == "eligible_positive":
            eligible_positive_static_vulnerable += 1
        elif classification == "hard_negative":
            hard_negative_static_vulnerable += 1

    eligible_positive = taxonomy_counts["eligible_positive"]
    hard_negative = taxonomy_counts["hard_negative"]
    hard_negative_safe = hard_negative - hard_negative_static_vulnerable
    hard_negative_split_counts = {
        name: int(hard_negative_split[name]) for name in HARD_NEGATIVE_SPLIT_CLASSES
    }
    determined_bounded = hard_negative_split_counts["determined_bounded"]

    return {
        "format": "dosweb-poc33-demo-evaluation-v2",
        "targets": len(statuses),
        "completed_targets": completed_targets,
        "formal_completed": completed_targets == len(statuses) and bool(statuses),
        "selected_queries": selected_queries,
        "query_diagnostics": query_diagnostics,
        "skipped_queries": skipped_queries,
        "truth": len(truth_dispositions),
        "full_chain_finding": full_chain,
        "explicit_deferred": len(deferred),
        "supported_subset_members": [row.get("record_id") for row in supported],
        "supported_subset_exclusions": [{"record_id": row.get("record_id"), "reason_codes": row.get("reason_codes", [])} for row in deferred],
        "ordinary_positive_subset_members": [row.get("finding_id") for row in dynamic_results if classify_dynamic_case(row) == "eligible_positive"],
        "ordinary_positive_subset_exclusions": [{"finding_id": row.get("finding_id"), "case_class": classify_dynamic_case(row), "status": row.get("status")} for row in dynamic_results if classify_dynamic_case(row) != "eligible_positive"],
        "truth_status_counts": dict(sorted(truth_statuses.items())),
        "supported_chain_recall": {
            "numerator": supported_full_chain,
            "denominator": len(supported),
            "ratio": _ratio(supported_full_chain, len(supported)),
        },
        "queue": unreviewed_positives,
        "analyzed_static_rows": len(static_findings),
        "legacy_queue_metrics": {"queue": len(static_findings), "tp": tp, "fp": fp, "blocked": blocked, "precision": _ratio(tp, tp + fp), "interpretation": "historical finding-level dynamic outcomes, not formal predicted-positive precision"},
        "families": len(families),
        "static_verdict_counts": dict(sorted(static_verdict_counts.items())),
        "family_verdict_counts": dict(sorted(family_verdict_counts.items())),
        "predicted_positive_families": len(predicted_positive_family_ids),
        "predicted_positive_family_ids": predicted_positive_family_ids,
        "analysis_unknown_families": len(analysis_unknown_family_ids),
        "bounded_families": len(bounded_family_ids),
        "reviewed_true_positives": reviewed_true_positives,
        "reviewed_false_positives": reviewed_false_positives,
        "unreviewed_positives": unreviewed_positives,
        "novel_positive_families": novel_positive_families,
        "known_case_matches": known_case_matches,
        "known_case_recall": {
            "numerator": known_case_matches,
            "denominator": len(truth_dispositions),
            "ratio": _ratio(known_case_matches, len(truth_dispositions)),
        },
        "eligible_positive": eligible_positive,
        "hard_negative": hard_negative,
        "weak_negative": taxonomy_counts["weak_negative"],
        "unscored": taxonomy_counts["unscored"],
        "dynamic_case_class_counts": {
            name: taxonomy_counts[name] for name in DYNAMIC_CASE_CLASSES
        },
        "tp": reviewed_true_positives,
        "fp": reviewed_false_positives,
        "blocked": blocked,
        "precision": precision_metrics["confirmed_precision"],
        "reviewed_positive_tp": reviewed_true_positives,
        "reviewed_positive_fp": reviewed_false_positives,
        "unreviewed_positive": unreviewed_positives,
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
        "hard_negative_split": hard_negative_split_counts,
        "hard_negative_bounded_proof": {
            "numerator": determined_bounded,
            "denominator": hard_negative,
            "ratio": _ratio(determined_bounded, hard_negative),
        },
        "not_reporting_positive_does_not_prove_bounded": True,
        "dynamic_verdict_counts": dict(sorted(verdict_counts.items())),
        **precision_metrics,
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
        demo_class = classify_dynamic_case(result)
        rows.append(
            {
                "case_id": result.get("case_id"),
                "finding_id": finding_id,
                "target": result.get("target"),
                "dynamic_status": result.get("status"),
                "dynamic_verdict": result.get("verdict"),
                "demo_class": demo_class,
                "selected_by_static": bool(verdicts) or (
                    isinstance(finding_id, str) and finding_id in static_by_finding
                ),
                "static_verdicts": verdicts,
                "static_vulnerable": "static_vulnerable" in verdicts,
                "hard_negative_outcome": (
                    classify_hard_negative_outcome(verdicts)
                    if demo_class == "hard_negative"
                    else None
                ),
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
    bounded_proof = _mapping(metrics.get("hard_negative_bounded_proof"))
    known = _mapping(metrics.get("known_case_recall"))
    split = _mapping(metrics.get("hard_negative_split"))
    legacy = _mapping(metrics.get("legacy_queue_metrics"))
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
            "## Known-case oracle",
            "",
            f"- formal static_vulnerable matches: {known.get('numerator')}/{known.get('denominator')} ({known.get('ratio')})",
            f"- supported-chain subset: {recall.get('numerator')}/{recall.get('denominator')} ({recall.get('ratio')})",
            f"- explicit deferred: {metrics.get('explicit_deferred')}",
            "",
            "## Formal predicted positives",
            "",
            f"- predicted_positive_families (static_vulnerable, deduplicated): {metrics.get('predicted_positive_families')}",
            f"- analysis_unknown_families: {metrics.get('analysis_unknown_families')}",
            f"- bounded_families: {metrics.get('bounded_families')}",
            f"- reviewed TP / FP / unreviewed positives: {metrics.get('reviewed_true_positives')} / {metrics.get('reviewed_false_positives')} / {metrics.get('unreviewed_positives')}",
            f"- novel positives outside the oracle records: {metrics.get('novel_positive_families')}",
            f"- confirmed precision TP/(TP+FP): {metrics.get('confirmed_precision')}",
            f"- conservative precision lower bound TP/(TP+FP+unreviewed): {metrics.get('conservative_precision_lower_bound')}",
            f"- precision_review_status: {metrics.get('precision_review_status')}",
            f"- precision threshold: {metrics.get('precision_threshold')} ({metrics.get('threshold_origin')})",
            f"- FPR: {metrics.get('false_positive_rate')}",
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
            f"- ordinary positive recall subset: {positive.get('numerator')}/{positive.get('denominator')} ({positive.get('ratio')})",
            f"- hard-negative not-static_vulnerable (legacy, not a bounded proof): {negative.get('numerator')}/{negative.get('denominator')} ({negative.get('ratio')})",
            f"- hard-negative determined bounded: {bounded_proof.get('numerator')}/{bounded_proof.get('denominator')} ({bounded_proof.get('ratio')})",
            (
                "- hard-negative split: "
                f"determined_bounded={split.get('determined_bounded')}, "
                f"analysis_unknown={split.get('analysis_unknown')}, "
                f"false_positive={split.get('false_positive')}, "
                f"extraction_failure={split.get('extraction_failure')}, "
                f"unmatched_static_evidence={split.get('unmatched_static_evidence')}"
            ),
            "",
            "## Historical queue score",
            "",
            f"- raw analyzed rows (not review queue): {legacy.get('queue')}",
            f"- historical finding-level TP / FP / blocked: {legacy.get('tp')} / {legacy.get('fp')} / {legacy.get('blocked')}",
            f"- historical precision TP/(TP+FP): {legacy.get('precision')}",
            "",
            "Unknown families are not review positives. Dynamic evidence is used only for this post-hoc evaluation; it does not rewrite static artifacts.",
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
    parser.add_argument(
        "--reviews",
        type=Path,
        help="optional JSONL of predicted-positive family reviews; unknown families are ignored",
    )
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
    reviews_path = None
    if args.reviews is not None:
        reviews_path = args.reviews
        if reviews_path.is_symlink() or not reviews_path.is_file():
            raise ValueError(f"--reviews must be a regular JSONL file: {reviews_path}")
        input_roots.append(reviews_path.resolve().parent)
    output = _prepare_output(args.output, input_roots)

    status_path = static_batch / "aggregate_status.jsonl"
    if not status_path.is_file():
        status_path = static_batch / "status.jsonl"
    statuses = _read_jsonl(status_path)
    truth_dispositions = _read_jsonl(recall / "truth_dispositions.jsonl")
    if static_audit is not None:
        static_findings = _read_jsonl(static_audit / "static_positive_queue.jsonl")
    else:
        direct_families = static_batch / "finding_families.jsonl"
        aggregate_families = static_batch / "aggregate_finding_families.jsonl"
        if direct_families.is_file() and aggregate_families.is_file():
            raise ValueError("static batch has ambiguous finding family roots")
        family_path = direct_families if direct_families.is_file() else aggregate_families
        static_findings = _read_jsonl(family_path)
    dynamic_results = [
        *_read_jsonl(dynamic / "findings.jsonl"),
        *_read_jsonl(dynamic / "blocked_or_rejected.jsonl"),
    ]
    reviews: list[dict[str, object]] = (
        _read_jsonl(reviews_path) if reviews_path is not None else []
    )

    final_path = static_batch / "aggregate_findings.jsonl"
    final_findings = _read_jsonl(final_path) if static_audit is None and final_path.is_file() else None
    metrics = build_demo_metrics(
        statuses=statuses,
        truth_dispositions=truth_dispositions,
        static_findings=static_findings,
        dynamic_results=dynamic_results,
        reviews=reviews,
        final_findings=final_findings,
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
    "FPR_NOT_MEASURED",
    "HARD_NEGATIVE_SPLIT_CLASSES",
    "HARD_NEGATIVE_STATUSES",
    "PRECISION_REVIEW_FAIL",
    "PRECISION_REVIEW_NO_POSITIVE",
    "PRECISION_REVIEW_PASS",
    "PRECISION_REVIEW_PENDING",
    "PRECISION_THRESHOLD",
    "PRECISION_THRESHOLD_ORIGIN",
    "REVIEW_STATUSES",
    "WEAK_NEGATIVE_STATUSES",
    "build_case_matrix",
    "build_demo_metrics",
    "classify_dynamic_case",
    "classify_hard_negative_outcome",
    "main",
    "precision_review_metrics",
]
