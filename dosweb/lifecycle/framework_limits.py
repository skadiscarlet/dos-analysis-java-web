"""Path-exact normalization for framework-enforced request limits."""
from __future__ import annotations

from dataclasses import dataclass

from dosweb.entries import EntryFact
from dosweb.flows import VerifiedFlow
from dosweb.growth import VerifiedGrowthResult
from dosweb.lifecycle.bounds import BoundCandidate, BoundDecision, evaluate_bound
from dosweb.lifecycle.guards import DecisionCheck, ModeledConfiguration, _validate_context


@dataclass(frozen=True)
class _FrameworkLimitDomain:
    evidence: str
    frameworks: frozenset[str]
    request_encoding: str
    configuration_key: str


_DOMAINS = (
    _FrameworkLimitDomain(
        "jackson_stream_read_constraints_literal",
        frozenset({"spring_mvc", "servlet", "jax_rs", "netty"}),
        "json",
        "literal",
    ),
    _FrameworkLimitDomain(
        "netty_http_object_aggregator_literal",
        frozenset({"netty"}),
        "aggregated_http",
        "literal",
    ),
    _FrameworkLimitDomain(
        "servlet_multipart_config_literal",
        frozenset({"spring_mvc", "servlet"}),
        "multipart",
        "literal",
    ),
    _FrameworkLimitDomain(
        "solr_formdata_upload_limit_literal",
        frozenset({"servlet"}),
        "form_urlencoded",
        "literal",
    ),
)


def _domain(candidate: BoundCandidate) -> _FrameworkLimitDomain | None:
    matches = tuple(
        domain for domain in _DOMAINS if domain.evidence in candidate.evidence
    )
    return matches[0] if len(matches) == 1 and candidate.kind == "limit" else None


def is_framework_limit_candidate(candidate: BoundCandidate) -> bool:
    """Return whether ``candidate`` names one exact modeled framework domain."""
    return _domain(candidate) is not None


def framework_limit_reason_codes(
    entry: EntryFact,
    candidate: BoundCandidate,
) -> tuple[str, ...] | None:
    """Return exact-domain failures, or ``None`` for a non-framework bound."""
    domain = _domain(candidate)
    if domain is None:
        return None
    reasons: list[str] = []
    if entry.framework not in domain.frameworks:
        reasons.append("BOUND_FRAMEWORK_MISMATCH")
    if candidate.request_encoding != domain.request_encoding:
        reasons.append("BOUND_REQUEST_ENCODING_MISMATCH")
    if candidate.configuration_key != domain.configuration_key:
        reasons.append("BOUND_CONFIGURATION_PROVENANCE_MISMATCH")
    return tuple(reasons)


def normalize_framework_limit(
    *,
    entry: EntryFact,
    growth: VerifiedGrowthResult,
    flow: VerifiedFlow,
    candidate: BoundCandidate,
    configuration: ModeledConfiguration,
) -> BoundDecision:
    """Return effective only for the exact path, driver, encoding, and provenance."""
    _validate_context(entry, growth, flow)
    domain_reasons = framework_limit_reason_codes(entry, candidate)
    if domain_reasons is None:
        reason = "BOUND_FRAMEWORK_LIMIT_DOMAIN_UNMODELED"
        return BoundDecision(
            "unknown",
            (reason,),
            (DecisionCheck("framework_limit_domain", False, reason, candidate.evidence),),
            candidate.evidence,
            ("framework_limit_domain",),
            (candidate.bound_id,),
        )
    return evaluate_bound(entry, growth, flow, (candidate,), configuration)


__all__ = ["is_framework_limit_candidate", "normalize_framework_limit"]
