"""Offline resource lifecycle state analysis.

This package is deliberately separate from :mod:`dosweb.lifecycle`, which
implements the existing P0 Guard/Bound/synchronous-Release candidate checks.
"""

from dosweb.resource_lifecycle.models import (
    AbstractInstance,
    AnalysisBudget,
    AnalysisResult,
    CallBinding,
    Effect,
    Event,
    Holder,
    PopulationEffect,
    Program,
    ProgramPoint,
    ResourceFamily,
    ResourceState,
    SourceLocation,
    TaskBinding,
    TaskExit,
    Transition,
)
from dosweb.resource_lifecycle.solver import apply_effect, initial_state, merge_states, solve

__all__ = [
    "AbstractInstance",
    "AnalysisBudget",
    "AnalysisResult",
    "CallBinding",
    "Effect",
    "Event",
    "Holder",
    "PopulationEffect",
    "Program",
    "ProgramPoint",
    "ResourceFamily",
    "ResourceState",
    "SourceLocation",
    "TaskBinding",
    "TaskExit",
    "Transition",
    "apply_effect",
    "initial_state",
    "merge_states",
    "solve",
]
