"""Growth-candidate models, bounded slices, and deterministic verification."""

from dosweb.growth.evidence import (
    GrowthStaticEvidence,
    adapt_growth_static_evidence,
)
from dosweb.growth.excerpts import extract_source_excerpt
from dosweb.growth.completeness import (
    AmplificationDecision,
    CandidateDisposition,
    CandidateEntryLink,
    RepeatabilityDecision,
)
from dosweb.growth.models import (
    AttackerInfluence,
    BoundedSlice,
    BoundedSlicePayload,
    CfgSummary,
    ConfigFact,
    GrowthContract,
    RegistrationFact,
    SourceExcerpt,
    StaticFact,
)
from dosweb.growth.relevance import RelevanceDecision, evaluate_candidate_relevance
from dosweb.growth.slices import (
    CoverageStatus,
    DemandInput,
    DemandRole,
    EscapeScope,
    GrowthCandidate,
    GrowthKind,
    ResourceDimension,
    SourceLocation,
    build_bounded_slice,
    normalize_growth_rows,
    load_growth_candidates,
)
from dosweb.growth.verify import (
    VerificationCheck,
    VerifiedGrowthResult,
    verify_growth_contract,
    load_verified_growth,
)

__all__ = [
    "AmplificationDecision",
    "AttackerInfluence",
    "CandidateDisposition",
    "CandidateEntryLink",
    "BoundedSlice",
    "BoundedSlicePayload",
    "CfgSummary",
    "ConfigFact",
    "CoverageStatus",
    "DemandInput",
    "DemandRole",
    "EscapeScope",
    "GrowthCandidate",
    "GrowthContract",
    "GrowthKind",
    "GrowthStaticEvidence",
    "RegistrationFact",
    "RelevanceDecision",
    "RepeatabilityDecision",
    "ResourceDimension",
    "SourceExcerpt",
    "SourceLocation",
    "StaticFact",
    "VerificationCheck",
    "VerifiedGrowthResult",
    "adapt_growth_static_evidence",
    "build_bounded_slice",
    "extract_source_excerpt",
    "evaluate_candidate_relevance",
    "normalize_growth_rows",
    "load_growth_candidates",
    "verify_growth_contract",
    "load_verified_growth",
]
