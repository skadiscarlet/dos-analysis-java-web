from __future__ import annotations

from collections.abc import Mapping, Sequence

from dosweb.errors import AnalyzerError
from dosweb.lifecycle.certificates import LifecycleCertificate, StaticFinding


def render_report(
    summary: Mapping[str, object],
    findings: Sequence[StaticFinding],
    certificates: Sequence[LifecycleCertificate],
) -> str:
    if not isinstance(summary, Mapping) or not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)) or not isinstance(certificates, Sequence) or isinstance(certificates, (str, bytes)):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Report inputs are malformed.")
    if any(not isinstance(item, StaticFinding) for item in findings) or any(not isinstance(item, LifecycleCertificate) for item in certificates):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Report artifacts are malformed.")
    cert_by_id = {item.certificate_id: item for item in certificates}
    if len(cert_by_id) != len(certificates):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Report certificates are duplicated.")
    ordered = tuple(sorted(findings, key=lambda item: item.finding_id))
    if any(item.certificate_id not in cert_by_id for item in ordered):
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Finding references an absent certificate.")
    for finding in ordered:
        certificate = cert_by_id[finding.certificate_id]
        if (
            finding.entry_id != certificate.entry_id
            or finding.growth_id != certificate.growth_id
            or finding.verdict != certificate.verdict
            or finding.reason_codes != certificate.reason_codes
        ):
            raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Finding disagrees with its certificate.")
    expected_ids = [item.finding_id for item in ordered]
    if summary.get("finding_ids") != expected_ids:
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary and findings disagree.")
    counts = {"static_vulnerable": 0, "bounded_under_modeled_assumptions": 0, "static_unknown": 0}
    for item in ordered:
        counts[item.verdict] += 1
    if summary.get("verdict_counts") != counts:
        raise AnalyzerError("ANALYSIS_REPORT_INVALID", "Summary verdict counts disagree.")

    lines = [
        "# Static resource-exhaustion analysis report",
        "",
        "This report contains static findings only. It does not provide dynamic confirmation or establish a runtime outcome.",
        "",
        "## Summary",
        "",
        f"- Static vulnerable: {counts['static_vulnerable']}",
        f"- Bounded under modeled assumptions: {counts['bounded_under_modeled_assumptions']}",
        f"- Static unknown: {counts['static_unknown']}",
        "",
        "## Findings",
        "",
        "| Finding ID | Verdict | Certificate ID | Entry ID | Growth ID |",
        "|---|---|---|---|---|",
    ]
    for finding in ordered:
        lines.append(f"| `{finding.finding_id}` | `{finding.verdict}` | `{finding.certificate_id}` | `{finding.entry_id}` | `{finding.growth_id}` |")
    lines.extend(["", "## Coverage and limitations", ""])
    coverage = summary.get("coverage", [])
    limitations = summary.get("limitations", [])
    lines.append("Coverage is reported from the modeled static-analysis framework set.")
    if coverage:
        for item in coverage:
            if isinstance(item, Mapping):
                lines.append(f"- {item.get('framework')}: {item.get('status')}")
    else:
        lines.append("- No framework coverage records were supplied.")
    if limitations:
        lines.append("Limitations:")
        lines.extend(f"- {item}" for item in limitations if isinstance(item, str))
    else:
        lines.append("Limitations: none recorded beyond static-only analysis and modeled assumptions.")
    return "\n".join(lines) + "\n"


__all__ = ["render_report"]
