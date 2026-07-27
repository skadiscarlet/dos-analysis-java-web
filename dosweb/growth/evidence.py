from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from dosweb.artifacts.identifiers import canonical_json
from dosweb.entries.models import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.growth.models import (
    CfgSummary,
    ConfigFact,
    RegistrationFact,
    SourceExcerpt,
    StaticFact,
)
from dosweb.growth.slices import CoverageStatus, GrowthCandidate


_STATIC_FACT_KINDS: Final = {
    "input_materialization": "input_materialization",
    "direct_allocation": "allocation",
    "container_growth": "container_write",
    "async_work_growth": "async_submission",
}


def _invalid(reason: str) -> AnalyzerError:
    return AnalyzerError(
        "ANALYSIS_GROWTH_INVALID",
        "Growth static evidence cannot be constructed safely.",
        {"reason": reason},
    )


def _covering_excerpt(
    excerpts: tuple[SourceExcerpt, ...],
    file: str,
    line: int,
    *,
    reason: str,
) -> SourceExcerpt:
    matches = tuple(
        sorted(
            (
                excerpt
                for excerpt in excerpts
                if excerpt.repo_relative_path == file
                and excerpt.start_line <= line <= excerpt.end_line
            ),
            key=lambda excerpt: canonical_json(excerpt.to_dict()),
        )
    )
    if not matches:
        raise _invalid(reason)
    return matches[0]


@dataclass(frozen=True)
class GrowthStaticEvidence:
    """Typed facts derivable without inventing flow, CFG, or configuration proof."""

    static_facts: tuple[StaticFact, ...]
    cfg_summary: CfgSummary
    registration_facts: tuple[RegistrationFact, ...]
    config_facts: tuple[ConfigFact, ...]
    coverage_status: CoverageStatus
    coverage_notes: tuple[str, ...]


def adapt_growth_static_evidence(
    entry: EntryFact,
    candidate: GrowthCandidate,
    source_excerpts: tuple[SourceExcerpt, ...],
) -> GrowthStaticEvidence:
    """Map attested Entry/Growth evidence into the strict bounded-slice model.

    Growth queries prove a typed resource operation at the candidate site. They
    do not prove an Entry-to-Growth path, CFG branch, or configuration value, so
    this adapter deliberately leaves those collections empty.
    """
    if (
        not isinstance(entry, EntryFact)
        or not isinstance(candidate, GrowthCandidate)
        or not isinstance(source_excerpts, tuple)
        or not source_excerpts
        or not all(isinstance(item, SourceExcerpt) for item in source_excerpts)
    ):
        raise _invalid("INPUT_INVALID")
    if len({excerpt.excerpt_id for excerpt in source_excerpts}) != len(source_excerpts):
        raise _invalid("DUPLICATE_EXCERPT_ID")

    growth_excerpt = _covering_excerpt(
        source_excerpts,
        candidate.site.file,
        candidate.site.start_line,
        reason="CANDIDATE_LOCATION_UNATTESTED",
    )
    registration_excerpt = _covering_excerpt(
        source_excerpts,
        entry.registration.file,
        entry.registration.start_line,
        reason="REGISTRATION_LOCATION_UNATTESTED",
    )
    fact_kind = _STATIC_FACT_KINDS.get(candidate.kind)
    if fact_kind is None:
        raise _invalid("GROWTH_KIND_UNSUPPORTED")

    static_facts = tuple(
        StaticFact(
            fact_id=evidence_id,
            kind=fact_kind,
            location_ref=growth_excerpt.excerpt_id,
            relation="sink",
        )
        for evidence_id in sorted(candidate.evidence_ids)
    )
    return GrowthStaticEvidence(
        static_facts=static_facts,
        cfg_summary=CfgSummary((), (), ()),
        registration_facts=(
            RegistrationFact(entry.framework, registration_excerpt.excerpt_id),
        ),
        config_facts=(),
        coverage_status=candidate.coverage_status,
        coverage_notes=candidate.coverage_notes,
    )


__all__ = ["GrowthStaticEvidence", "adapt_growth_static_evidence"]
