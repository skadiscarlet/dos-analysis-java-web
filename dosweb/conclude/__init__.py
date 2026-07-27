"""Deterministic P0 assertion evaluation and static verdict derivation."""

from dosweb.conclude.assertions import (
    AssertionEvaluation,
    evaluate_assertion_1,
    evaluate_assertion_2,
)
from dosweb.conclude.verdicts import (
    CandidateCoverage,
    StaticVerdict,
    StaticVerdictName,
    derive_verdict,
)

__all__ = [
    "AssertionEvaluation",
    "CandidateCoverage",
    "StaticVerdict",
    "StaticVerdictName",
    "derive_verdict",
    "evaluate_assertion_1",
    "evaluate_assertion_2",
]
