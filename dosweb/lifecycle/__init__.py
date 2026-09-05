"""Deterministic P0 Guard, Bound, and synchronous Release evaluation."""

from dosweb.lifecycle.bounds import BoundCandidate, BoundDecision, BoundStatus, evaluate_bound
from dosweb.lifecycle.guards import (
    DecisionCheck,
    GuardCandidate,
    GuardDecision,
    ModeledConfiguration,
    evaluate_guard,
)
from dosweb.lifecycle.releases import ReleaseCandidate, ReleaseDecision, evaluate_synchronous_release
from dosweb.lifecycle.evidence import LifecycleCoverage, LifecycleEvidence, LifecycleSummary
from dosweb.lifecycle.framework_limits import normalize_framework_limit

__all__ = [
    "BoundCandidate", "BoundDecision", "BoundStatus", "DecisionCheck",
    "GuardCandidate", "GuardDecision", "ModeledConfiguration", "ReleaseCandidate",
    "ReleaseDecision", "LifecycleCoverage", "LifecycleEvidence", "LifecycleSummary", "evaluate_bound", "evaluate_guard", "evaluate_synchronous_release", "normalize_framework_limit",
    "LifecycleCertificate", "StaticFinding", "build_lifecycle_certificate",
]


def __getattr__(name: str):
    if name in {"LifecycleCertificate", "StaticFinding", "build_lifecycle_certificate"}:
        from dosweb.lifecycle.certificates import (
            LifecycleCertificate,
            StaticFinding,
            build_lifecycle_certificate,
        )
        return {
            "LifecycleCertificate": LifecycleCertificate,
            "StaticFinding": StaticFinding,
            "build_lifecycle_certificate": build_lifecycle_certificate,
        }[name]
    raise AttributeError(name)
