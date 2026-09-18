from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.conclude.verdicts import StaticVerdictName
from dosweb.entries import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.lifecycle.certificates import LifecycleCertificate, StaticFinding
from dosweb.reachability import ReachabilityDecision

FindingPriority = Literal["P0", "P1", "P2", "inventory"]
AmplificationClass = Literal[
    "superlinear",
    "large_single_request",
    "concurrent_retention",
    "queue_instability",
    "high_cardinality_retention",
    "low_amplification",
    "unknown",
]

_VERDICTS = frozenset(
    {"static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown"}
)
_PRIORITIES = frozenset({"P0", "P1", "P2", "inventory"})
_REACHABILITY = frozenset(
    {"ordinary_attacker_reachable", "not_entry_reachable", "unknown"}
)
_AMPLIFICATION = frozenset(
    {
        "superlinear",
        "large_single_request",
        "concurrent_retention",
        "queue_instability",
        "high_cardinality_retention",
        "low_amplification",
        "unknown",
    }
)
_AMPLIFICATION_RANK = {
    "superlinear": 6,
    "large_single_request": 5,
    "queue_instability": 4,
    "concurrent_retention": 3,
    "high_cardinality_retention": 2,
    "low_amplification": 1,
    "unknown": 0,
}


def _invalid(message: str) -> AnalyzerError:
    return AnalyzerError("ANALYSIS_FINDING_FAMILY_INVALID", message)


def _strings(
    values: object,
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if (
        not isinstance(values, tuple)
        or (not allow_empty and not values)
        or any(not isinstance(value, str) or not value for value in values)
        or tuple(sorted(set(values))) != values
    ):
        raise _invalid(f"Finding family {field} is malformed.")
    return values


@dataclass(frozen=True)
class FindingFamily:
    family_id: str
    verdict: StaticVerdictName
    priority: FindingPriority
    primary_finding_id: str
    member_finding_ids: tuple[str, ...]
    member_certificate_ids: tuple[str, ...]
    entry_ids: tuple[str, ...]
    growth_ids: tuple[str, ...]
    resource_id: str
    reachability_status: str
    amplification_class: AmplificationClass
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.family_id, str) or not self.family_id.startswith("family:"):
            raise _invalid("Finding family identifier is malformed.")
        if self.verdict not in _VERDICTS or self.priority not in _PRIORITIES:
            raise _invalid("Finding family verdict or priority is malformed.")
        if self.reachability_status not in _REACHABILITY:
            raise _invalid("Finding family reachability is malformed.")
        if self.amplification_class not in _AMPLIFICATION:
            raise _invalid("Finding family amplification is malformed.")
        for field in (
            "member_finding_ids",
            "member_certificate_ids",
            "entry_ids",
            "growth_ids",
        ):
            _strings(getattr(self, field), field)
        _strings(self.reason_codes, "reason_codes", allow_empty=True)
        if self.primary_finding_id not in self.member_finding_ids:
            raise _invalid("Finding family primary finding is not a member.")
        if not isinstance(self.resource_id, str) or not self.resource_id.startswith(
            "resource:"
        ):
            raise _invalid("Finding family resource identifier is malformed.")
        if self.family_id != stable_identifier("family", self.semantic_identity):
            raise _invalid("Finding family identifier is not canonical.")

    @property
    def semantic_identity(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "priority": self.priority,
            "primary_finding_id": self.primary_finding_id,
            "member_finding_ids": list(self.member_finding_ids),
            "member_certificate_ids": list(self.member_certificate_ids),
            "entry_ids": list(self.entry_ids),
            "growth_ids": list(self.growth_ids),
            "resource_id": self.resource_id,
            "reachability_status": self.reachability_status,
            "amplification_class": self.amplification_class,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, object]) -> "FindingFamily":
        fields = {
            "family_id",
            "verdict",
            "priority",
            "primary_finding_id",
            "member_finding_ids",
            "member_certificate_ids",
            "entry_ids",
            "growth_ids",
            "resource_id",
            "reachability_status",
            "amplification_class",
            "reason_codes",
        }
        if not isinstance(record, Mapping) or set(record) != fields:
            raise _invalid("Finding family record is malformed.")
        collections = (
            "member_finding_ids",
            "member_certificate_ids",
            "entry_ids",
            "growth_ids",
            "reason_codes",
        )
        if any(not isinstance(record[field], list) for field in collections):
            raise _invalid("Finding family record collections are malformed.")
        return cls(
            cast(str, record["family_id"]),
            cast(StaticVerdictName, record["verdict"]),
            cast(FindingPriority, record["priority"]),
            cast(str, record["primary_finding_id"]),
            tuple(cast(list[str], record["member_finding_ids"])),
            tuple(cast(list[str], record["member_certificate_ids"])),
            tuple(cast(list[str], record["entry_ids"])),
            tuple(cast(list[str], record["growth_ids"])),
            cast(str, record["resource_id"]),
            cast(str, record["reachability_status"]),
            cast(AmplificationClass, record["amplification_class"]),
            tuple(cast(list[str], record["reason_codes"])),
        )

    def to_dict(self) -> dict[str, object]:
        return {"family_id": self.family_id, **self.semantic_identity}


def _registration_identity(
    entry: EntryFact,
    reachability: ReachabilityDecision | None,
) -> dict[str, object]:
    if reachability is not None and reachability.entry_id != entry.entry_id:
        raise _invalid("Finding family reachability references another Entry.")
    return {
        "framework": entry.framework,
        "protocol": entry.protocol,
        "registration": entry.registration.to_dict(),
        "handler": entry.handler.to_dict(),
        "auth_context": (
            reachability.auth_context if reachability is not None else entry.auth_context
        ),
        "deployment_status": (
            reachability.deployment_status if reachability is not None else "unknown"
        ),
    }


def _priority(
    verdict: StaticVerdictName,
    reachability_status: str,
    amplification_class: AmplificationClass,
) -> FindingPriority:
    if reachability_status == "not_entry_reachable":
        return "inventory"
    if verdict == "static_vulnerable" and reachability_status == "ordinary_attacker_reachable":
        return "P0"
    if verdict == "static_unknown" and amplification_class not in {
        "low_amplification",
        "unknown",
    }:
        return "P1"
    if verdict in {"static_unknown", "bounded_under_modeled_assumptions"}:
        return "P2"
    return "inventory"


def _primary_key(
    finding: StaticFinding,
    certificate: LifecycleCertificate,
    amplification_class: AmplificationClass,
) -> tuple[object, ...]:
    return (
        bool(certificate.coverage_gaps),
        len(certificate.coverage_gaps),
        bool(certificate.unresolved_facts),
        len(certificate.unresolved_facts),
        -_AMPLIFICATION_RANK[amplification_class],
        finding.finding_id,
    )


def build_finding_families(
    findings: Sequence[StaticFinding],
    certificates: Sequence[LifecycleCertificate],
    entries: Mapping[str, EntryFact],
    reachability: Mapping[str, ReachabilityDecision],
    amplification_classes: Mapping[tuple[str, str], str],
) -> tuple[FindingFamily, ...]:
    """Aggregate exact findings without using route aliases or benchmark truth."""

    if (
        not isinstance(findings, Sequence)
        or isinstance(findings, (str, bytes))
        or not isinstance(certificates, Sequence)
        or isinstance(certificates, (str, bytes))
        or not isinstance(entries, Mapping)
        or not isinstance(reachability, Mapping)
        or not isinstance(amplification_classes, Mapping)
        or any(not isinstance(item, StaticFinding) for item in findings)
        or any(not isinstance(item, LifecycleCertificate) for item in certificates)
        or any(not isinstance(item, EntryFact) for item in entries.values())
        or any(not isinstance(item, ReachabilityDecision) for item in reachability.values())
    ):
        raise _invalid("Finding family inputs are malformed.")

    finding_by_id = {item.finding_id: item for item in findings}
    certificate_by_id = {item.certificate_id: item for item in certificates}
    if len(finding_by_id) != len(findings) or len(certificate_by_id) != len(certificates):
        raise _invalid("Finding family inputs contain duplicate identifiers.")
    if {item.certificate_id for item in findings} != set(certificate_by_id):
        raise _invalid("Finding family findings and certificates are not a bijection.")

    grouped: dict[
        str,
        tuple[dict[str, object], list[tuple[StaticFinding, LifecycleCertificate, AmplificationClass]]],
    ] = {}
    for finding in findings:
        certificate = certificate_by_id[finding.certificate_id]
        if (
            finding.entry_id != certificate.entry_id
            or finding.growth_id != certificate.growth_id
            or finding.verdict != certificate.verdict
            or finding.reason_codes != certificate.reason_codes
        ):
            raise _invalid("Finding family member disagrees with its certificate.")
        entry = entries.get(finding.entry_id)
        if not isinstance(entry, EntryFact):
            raise _invalid("Finding family member references an absent Entry.")
        point = certificate.resource_point
        resource_id = point.get("resource_id") if isinstance(point, Mapping) else None
        if not isinstance(resource_id, str) or not resource_id.startswith("resource:"):
            raise _invalid("Finding family member has no canonical resource.")
        reach = reachability.get(entry.entry_id)
        if reach is not None and not isinstance(reach, ReachabilityDecision):
            raise _invalid("Finding family reachability is malformed.")
        reachability_status = reach.status if reach is not None else "unknown"
        amplification = amplification_classes.get(
            (finding.entry_id, finding.growth_id), "unknown"
        )
        if not isinstance(amplification, str) or amplification not in _AMPLIFICATION:
            raise _invalid("Finding family amplification is malformed.")
        identity = {
            **_registration_identity(entry, reach),
            "resource_id": resource_id,
            "reachability_status": reachability_status,
            "verdict": finding.verdict,
        }
        key = stable_identifier("family_group", identity)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = (identity, [(finding, certificate, cast(AmplificationClass, amplification))])
        else:
            existing[1].append(
                (finding, certificate, cast(AmplificationClass, amplification))
            )

    families: list[FindingFamily] = []
    for identity, members in grouped.values():
        ordered = tuple(
            sorted(
                members,
                key=lambda item: _primary_key(item[0], item[1], item[2]),
            )
        )
        primary = ordered[0]
        finding_ids = tuple(sorted(item[0].finding_id for item in ordered))
        certificate_ids = tuple(sorted(item[1].certificate_id for item in ordered))
        entry_ids = tuple(sorted({item[0].entry_id for item in ordered}))
        growth_ids = tuple(sorted({item[0].growth_id for item in ordered}))
        reason_codes = tuple(
            sorted({reason for item in ordered for reason in item[0].reason_codes})
        )
        verdict = primary[0].verdict
        reachability_status = cast(str, identity["reachability_status"])
        amplification = primary[2]
        priority = _priority(
            cast(StaticVerdictName, verdict), reachability_status, amplification
        )
        semantic = {
            "verdict": verdict,
            "priority": priority,
            "primary_finding_id": primary[0].finding_id,
            "member_finding_ids": list(finding_ids),
            "member_certificate_ids": list(certificate_ids),
            "entry_ids": list(entry_ids),
            "growth_ids": list(growth_ids),
            "resource_id": cast(str, identity["resource_id"]),
            "reachability_status": reachability_status,
            "amplification_class": amplification,
            "reason_codes": list(reason_codes),
        }
        families.append(
            FindingFamily(
                stable_identifier("family", semantic),
                cast(StaticVerdictName, verdict),
                priority,
                primary[0].finding_id,
                finding_ids,
                certificate_ids,
                entry_ids,
                growth_ids,
                cast(str, identity["resource_id"]),
                reachability_status,
                amplification,
                reason_codes,
            )
        )
    return tuple(sorted(families, key=lambda item: item.family_id))


__all__ = ["FindingFamily", "FindingPriority", "build_finding_families"]
