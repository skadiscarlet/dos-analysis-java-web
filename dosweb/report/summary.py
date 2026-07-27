from __future__ import annotations

from collections.abc import Sequence

from dosweb.entries import FrameworkCoverage
from dosweb.errors import AnalyzerError
from dosweb.lifecycle.certificates import StaticFinding

_VERDICTS = ("static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown")


def build_summary(
    findings: Sequence[StaticFinding],
    coverage: Sequence[FrameworkCoverage],
) -> dict[str, object]:
    if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)) or any(
        not isinstance(finding, StaticFinding) for finding in findings
    ):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary findings are malformed.")
    if not isinstance(coverage, Sequence) or isinstance(coverage, (str, bytes)) or any(
        not isinstance(item, FrameworkCoverage) for item in coverage
    ):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary coverage is malformed.")
    ordered = tuple(sorted(findings, key=lambda item: item.finding_id))
    ids = tuple(item.finding_id for item in ordered)
    if len(ids) != len(set(ids)):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary finding identifiers are duplicated.")
    counts = {verdict: 0 for verdict in _VERDICTS}
    for finding in ordered:
        counts[finding.verdict] += 1
    ordered_coverage = tuple(sorted(coverage, key=lambda item: item.framework))
    if len({item.framework for item in ordered_coverage}) != len(ordered_coverage):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary framework coverage is duplicated.")
    limitations: set[str] = set()
    for item in ordered_coverage:
        limitations.update(f"{item.framework}:{pattern}" for pattern in item.unsupported_patterns)
    if counts["static_unknown"]:
        limitations.add("unresolved_static_evidence")
    return {
        "finding_ids": list(ids),
        "verdict_counts": counts,
        "coverage": [item.to_dict() for item in ordered_coverage],
        "limitations": sorted(limitations),
    }


__all__ = ["build_summary"]
