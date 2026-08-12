"""Benchmark metrics intentionally limited to recall-oriented measures."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

_MATCHED = {"hit", "matched_static_unknown", "matched_bounded"}
_INELIGIBLE = {"target_not_run", "artifact_missing", "truth_invalid"}


def evaluate_matches(
    matches: list[Mapping[str, Any]],
    *,
    truth_valid: bool = True,
    oracle_total: int = 29,
    repository_total: int = 18,
) -> dict[str, Any]:
    status_counts = Counter(str(row.get("status")) for row in matches)
    eligible = sum(1 for row in matches if row.get("status") not in _INELIGIBLE)
    hits = status_counts["hit"]
    matched_any = sum(status_counts[status] for status in _MATCHED)
    targets_completed = len(
        {
            str(row.get("repository"))
            for row in matches
            if row.get("status") not in {"target_not_run", "artifact_missing"}
        }
    )
    metrics = {
        "positive_recall": hits / eligible if eligible else 0.0,
        "global_recall": hits / oracle_total if oracle_total else 0.0,
        "matched_any_rate": matched_any / eligible if eligible else 0.0,
    }
    return {
        "schema_version": 1,
        "truth_valid": truth_valid,
        "oracle_total": oracle_total,
        "repository_total": repository_total,
        "eligible": eligible,
        "hits": hits,
        "targets_completed": targets_completed,
        "status_counts": dict(sorted(status_counts.items())),
        "metrics": metrics,
    }
