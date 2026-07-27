"""Growth-candidate models, bounded slices, and deterministic verification."""

from dosweb.growth.evidence import (
    GrowthStaticEvidence,
    adapt_growth_static_evidence,
)
from dosweb.growth.excerpts import extract_source_excerpt
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
    "AttackerInfluence",
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
    "ResourceDimension",
    "SourceExcerpt",
    "SourceLocation",
    "StaticFact",
    "VerificationCheck",
    "VerifiedGrowthResult",
    "adapt_growth_static_evidence",
    "build_bounded_slice",
    "extract_source_excerpt",
    "normalize_growth_rows",
    "load_growth_candidates",
    "verify_growth_contract",
    "load_verified_growth",
]
