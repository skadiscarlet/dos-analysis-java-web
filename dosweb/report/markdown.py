from __future__ import annotations

from collections.abc import Mapping, Sequence

from dosweb.errors import AnalyzerError
from dosweb.lifecycle.certificates import LifecycleCertificate, StaticFinding
from dosweb.report.families import FindingFamily


def _invalid(message: str) -> AnalyzerError:
    return AnalyzerError("ANALYSIS_REPORT_INVALID", message)


def render_report(
    summary: Mapping[str, object],
    families: Sequence[FindingFamily],
    findings: Sequence[StaticFinding],
    certificates: Sequence[LifecycleCertificate],
) -> str:
    if (
        not isinstance(summary, Mapping)
        or not isinstance(families, Sequence)
        or isinstance(families, (str, bytes))
        or not isinstance(findings, Sequence)
        or isinstance(findings, (str, bytes))
        or not isinstance(certificates, Sequence)
        or isinstance(certificates, (str, bytes))
        or any(not isinstance(item, FindingFamily) for item in families)
        or any(not isinstance(item, StaticFinding) for item in findings)
        or any(not isinstance(item, LifecycleCertificate) for item in certificates)
    ):
        raise _invalid("Report inputs are malformed.")

    ordered_families = tuple(sorted(families, key=lambda item: item.family_id))
    ordered_findings = tuple(sorted(findings, key=lambda item: item.finding_id))
    cert_by_id = {item.certificate_id: item for item in certificates}
    finding_by_id = {item.finding_id: item for item in ordered_findings}
    if len(cert_by_id) != len(certificates):
        raise _invalid("Report certificates are duplicated.")
    if len(finding_by_id) != len(ordered_findings):
        raise _invalid("Report findings are duplicated.")
    if len({item.family_id for item in ordered_families}) != len(ordered_families):
        raise _invalid("Report finding families are duplicated.")

    finding_certificate_ids = {item.certificate_id for item in ordered_findings}
    if any(item.certificate_id not in cert_by_id for item in ordered_findings):
        raise _invalid("Finding references an absent certificate.")
    if finding_certificate_ids != set(cert_by_id):
        raise _invalid("Report contains a certificate without a finding.")
    for finding in ordered_findings:
        certificate = cert_by_id[finding.certificate_id]
        if (
            finding.entry_id != certificate.entry_id
            or finding.growth_id != certificate.growth_id
            or finding.verdict != certificate.verdict
            or finding.reason_codes != certificate.reason_codes
        ):
            raise _invalid("Finding disagrees with its certificate.")

    covered_findings: list[str] = []
    for family in ordered_families:
        if any(item not in finding_by_id for item in family.member_finding_ids):
            raise _invalid("Finding family references an absent finding.")
        members = tuple(finding_by_id[item] for item in family.member_finding_ids)
        member_certificates = tuple(cert_by_id[item.certificate_id] for item in members)
        if (
            tuple(sorted(item.certificate_id for item in members))
            != family.member_certificate_ids
            or tuple(sorted({item.entry_id for item in members})) != family.entry_ids
            or tuple(sorted({item.growth_id for item in members})) != family.growth_ids
            or any(item.verdict != family.verdict for item in members)
            or any(
                certificate.resource_point.get("resource_id") != family.resource_id
                for certificate in member_certificates
            )
        ):
            raise _invalid("Finding family disagrees with exact audit artifacts.")
        covered_findings.extend(family.member_finding_ids)
    if (
        len(covered_findings) != len(set(covered_findings))
        or set(covered_findings) != set(finding_by_id)
    ):
        raise _invalid("Finding families do not exactly cover report findings.")

    expected_family_ids = [item.family_id for item in ordered_families]
    expected_finding_ids = [item.finding_id for item in ordered_findings]
    if summary.get("family_ids") != expected_family_ids:
        raise _invalid("Summary and finding families disagree.")
    if summary.get("finding_ids") != expected_finding_ids:
        raise _invalid("Summary and findings disagree.")
    counts = {
        "static_vulnerable": 0,
        "bounded_under_modeled_assumptions": 0,
        "static_unknown": 0,
    }
    priority_counts = {"P0": 0, "P1": 0, "P2": 0, "inventory": 0}
    for family in ordered_families:
        counts[family.verdict] += 1
        priority_counts[family.priority] += 1
    if summary.get("verdict_counts") != counts:
        raise _invalid("Summary verdict counts disagree.")
    if summary.get("priority_counts") != priority_counts:
        raise _invalid("Summary priority counts disagree.")

    lines = [
        "# Static resource-exhaustion analysis report",
        "",
        "This report contains static findings only. It does not provide dynamic confirmation or establish a runtime outcome.",
        "",
        "## Summary",
        "",
        f"- P0 families: {priority_counts['P0']}",
        f"- P1 families: {priority_counts['P1']}",
        f"- P2 families: {priority_counts['P2']}",
        f"- Inventory families: {priority_counts['inventory']}",
        f"- Static vulnerable families: {counts['static_vulnerable']}",
        f"- Bounded under modeled assumptions families: {counts['bounded_under_modeled_assumptions']}",
        f"- Static unknown families: {counts['static_unknown']}",
        "",
        "## Finding families",
        "",
        "| Priority | Family ID | Verdict | Amplification | Reachability | Bound status | Missing evidence / reasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for family in ordered_families:
        primary = finding_by_id[family.primary_finding_id]
        certificate = cert_by_id[primary.certificate_id]
        bound_status = certificate.bound_decision.get("status", "unknown")
        missing = tuple(
            sorted(
                set(
                    (
                        *certificate.coverage_gaps,
                        *certificate.unresolved_facts,
                        *family.reason_codes,
                    )
                )
            )
        )
        missing_text = ", ".join(f"`{item}`" for item in missing) if missing else "none"
        lines.append(
            f"| `{family.priority}` | `{family.family_id}` | `{family.verdict}` | "
            f"`{family.amplification_class}` | `{family.reachability_status}` | "
            f"`{bound_status}` | {missing_text} |"
        )

    lines.extend(
        [
            "",
            "## Exact finding audit",
            "",
            "| Finding ID | Verdict | Certificate ID | Entry ID | Growth ID |",
            "|---|---|---|---|---|",
        ]
    )
    for finding in ordered_findings:
        lines.append(
            f"| `{finding.finding_id}` | `{finding.verdict}` | `{finding.certificate_id}` | "
            f"`{finding.entry_id}` | `{finding.growth_id}` |"
        )

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
        lines.append(
            "Limitations: none recorded beyond static-only analysis and modeled assumptions."
        )
    if any(certificate.assumptions for certificate in certificates):
        lines.extend(["", "## Modeled assumptions in lifecycle certificates", ""])
        for certificate in sorted(certificates, key=lambda item: item.certificate_id):
            if certificate.assumptions:
                lines.append(f"### {certificate.certificate_id}")
                lines.extend(f"- {assumption}" for assumption in certificate.assumptions)
                lines.append("")
    return "\n".join(lines) + "\n"


__all__ = ["render_report"]
