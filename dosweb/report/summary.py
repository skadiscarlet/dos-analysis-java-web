from __future__ import annotations

from collections.abc import Sequence

from dosweb.entries import FrameworkCoverage
from dosweb.errors import AnalyzerError
from dosweb.lifecycle.certificates import StaticFinding
from dosweb.report.families import FindingFamily

_VERDICTS = ("static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown")


def build_summary(
    families: Sequence[FindingFamily],
    findings: Sequence[StaticFinding],
    coverage: Sequence[FrameworkCoverage],
) -> dict[str, object]:
    if not isinstance(families, Sequence) or isinstance(families, (str, bytes)) or any(
        not isinstance(family, FindingFamily) for family in families
    ):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary finding families are malformed.")
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
    ordered_families = tuple(sorted(families, key=lambda item: item.family_id))
    family_ids = tuple(item.family_id for item in ordered_families)
    if len(family_ids) != len(set(family_ids)):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary family identifiers are duplicated.")
    member_ids = [
        finding_id
        for family in ordered_families
        for finding_id in family.member_finding_ids
    ]
    if len(member_ids) != len(set(member_ids)) or set(member_ids) != set(ids):
        raise AnalyzerError(
            "ANALYSIS_REPORT_INVALID",
            "Summary finding families do not exactly cover findings.",
        )
    finding_by_id = {item.finding_id: item for item in ordered}
    for family in ordered_families:
        members = [finding_by_id[item] for item in family.member_finding_ids]
        if (
            any(item.verdict != family.verdict for item in members)
            or tuple(sorted({item.entry_id for item in members})) != family.entry_ids
            or tuple(sorted({item.growth_id for item in members})) != family.growth_ids
        ):
            raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary family members disagree.")
    counts = {verdict: 0 for verdict in _VERDICTS}
    exact_counts = {verdict: 0 for verdict in _VERDICTS}
    priority_counts = {priority: 0 for priority in ("P0", "P1", "P2", "inventory")}
    for family in ordered_families:
        counts[family.verdict] += 1
        priority_counts[family.priority] += 1
    for finding in ordered:
        exact_counts[finding.verdict] += 1
    ordered_coverage = tuple(sorted(coverage, key=lambda item: item.framework))
    if len({item.framework for item in ordered_coverage}) != len(ordered_coverage):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary framework coverage is duplicated.")
    limitations: set[str] = set()
    for item in ordered_coverage:
        limitations.update(f"{item.framework}:{pattern}" for pattern in item.unsupported_patterns)
    if counts["static_unknown"]:
        limitations.add("unresolved_static_evidence")
    return {
        "family_ids": list(family_ids),
        "finding_ids": list(ids),
        "verdict_counts": counts,
        "exact_finding_verdict_counts": exact_counts,
        "priority_counts": priority_counts,
        "coverage": [item.to_dict() for item in ordered_coverage],
        "limitations": sorted(limitations),
    }


__all__ = ["build_summary"]
