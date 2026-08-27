from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.configuration.models import ModeledConfigurationFact
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

_INPUT_ORIGINS: Final = {
    "request_body": "request_body",
    "request_parameter": "request_parameter",
    "model_attribute": "request_parameter",
    "path_parameter": "request_path",
    "header": "request_header",
    "message_payload": "network_message",
    "stream": "request_stream",
    "unknown": "unknown",
}


def _driver_origin(entry: EntryFact, source_name: object) -> str:
    matches = tuple(
        item for item in entry.attacker_inputs
        if isinstance(source_name, str) and item.name == source_name
    )
    if len(matches) != 1:
        return "unknown"
    return _INPUT_ORIGINS[matches[0].kind]


def _value_space(candidate: GrowthCandidate, has_flow: bool) -> str:
    if not has_flow:
        return "unknown"
    roles = {item.role for item in candidate.demand_inputs}
    if candidate.kind == "input_materialization":
        return "stream" if candidate.resource_dimension == "bytes" else "large"
    if candidate.kind == "direct_allocation":
        return "large"
    if candidate.kind == "container_growth":
        return "unlimited" if "key" in roles else "large"
    if candidate.kind == "async_work_growth":
        return "unlimited" if roles & {"iteration_count", "submission_count"} else "large"
    return "unknown"


def _retention(candidate: GrowthCandidate) -> str:
    return {
        "request": "request",
        "session": "session",
        "instance": "process",
        "global": "process",
        "unknown": "unknown",
    }[candidate.escape_scope]


def _amplification(candidate: GrowthCandidate) -> str:
    roles = {item.role for item in candidate.demand_inputs}
    if candidate.kind in {"input_materialization", "direct_allocation"}:
        return "large_single_request"
    if candidate.kind == "container_growth":
        if "key" in roles:
            return "high_cardinality_retention"
        return "concurrent_retention" if candidate.escape_scope != "request" else "low_amplification"
    if candidate.kind == "async_work_growth":
        return "queue_instability" if roles & {"iteration_count", "submission_count"} else "low_amplification"
    return "unknown"


def _loop_multiplicity(candidate: GrowthCandidate) -> str:
    roles = {item.role for item in candidate.demand_inputs}
    if roles & {"iteration_count", "submission_count"}:
        return "attacker_controlled_loop"
    if candidate.kind in {"container_growth", "async_work_growth"}:
        return "repeated_requests"
    return "single_operation"


def _field_identity(candidate: GrowthCandidate) -> str:
    roles = {item.role for item in candidate.demand_inputs}
    if "key" in roles:
        return "attacker_key"
    if candidate.escape_scope == "request":
        return "request_local"
    if "value" in roles:
        return "attacker_value"
    return "field_backed" if candidate.field_path else "unknown"


def _configuration_kind(key: str) -> str:
    lowered = key.lower()
    if "timeout" in lowered:
        return "timeout"
    if any(token in lowered for token in ("capacity", "queue", "quota")):
        return "capacity"
    if any(token in lowered for token in ("max", "limit", "size", "body", "payload", "request")):
        return "request_limit"
    return "feature_state"


def _semantic_fact(
    entry: EntryFact,
    candidate: GrowthCandidate,
    *,
    kind: str,
    value: str,
    location_ref: str,
    relation: str,
    value_ref: str | None = None,
) -> StaticFact:
    return StaticFact(
        stable_identifier(
            "fact",
            {
                "entry_id": entry.entry_id,
                "growth_id": candidate.growth_id,
                "kind": kind,
                "value": value,
            },
        ),
        kind,
        location_ref,
        relation,
        value_ref,
        value,
    )


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
    flow_rows: Sequence[Mapping[str, object]] = (),
    configuration_facts: Sequence[ModeledConfigurationFact] = (),
) -> GrowthStaticEvidence:
    """Map attested Entry/Growth evidence into the strict bounded-slice model.

    Growth queries prove a typed resource operation at the candidate site. Only
    independently extracted, complete CodeQL flow rows may create attacker-flow
    facts; the candidate operation itself never fabricates a source fact.
    """
    if (
        not isinstance(entry, EntryFact)
        or not isinstance(candidate, GrowthCandidate)
        or not isinstance(source_excerpts, tuple)
        or not source_excerpts
        or not all(isinstance(item, SourceExcerpt) for item in source_excerpts)
        or not isinstance(flow_rows, (list, tuple))
        or not all(isinstance(item, Mapping) for item in flow_rows)
        or not isinstance(configuration_facts, (list, tuple))
        or not all(isinstance(item, ModeledConfigurationFact) for item in configuration_facts)
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
    handler_excerpt = _covering_excerpt(
        source_excerpts,
        entry.handler.file,
        entry.handler.start_line,
        reason="HANDLER_LOCATION_UNATTESTED",
    )
    fact_kind = _STATIC_FACT_KINDS.get(candidate.kind)
    if fact_kind is None:
        raise _invalid("GROWTH_KIND_UNSUPPORTED")

    demand_roles = {demand.role for demand in candidate.demand_inputs}
    matched_flows = tuple(sorted(
        (
            row for row in flow_rows
            if row.get("source_file") == entry.handler.file
            and row.get("source_start_line") == entry.handler.start_line
            and row.get("sink_file") == candidate.site.file
            and row.get("sink_start_line") == candidate.site.start_line
            and row.get("attacker_target") in demand_roles
            and row.get("flow_kind") in {"data_flow", "local_data_flow"}
            and row.get("confidence") == "proven"
            and row.get("coverage_status") == "complete"
        ),
        key=canonical_json,
    ))
    source_facts = tuple(
        StaticFact(
            fact_id=stable_identifier("fact", {
                "entry_id": entry.entry_id,
                "growth_id": candidate.growth_id,
                "target": row["attacker_target"],
                "source": row["attacker_source"],
                "sink": row["attacker_sink"],
                "call_path": row["call_path"],
            }),
            kind="flow",
            location_ref=handler_excerpt.excerpt_id,
            relation="flows_to",
            normalized_value=_driver_origin(entry, row["attacker_source"]),
        )
        for row in matched_flows
    )
    primary_source = source_facts[0].fact_id if source_facts else None
    sink_facts = tuple(
        StaticFact(
            fact_id=evidence_id,
            kind=fact_kind,
            location_ref=growth_excerpt.excerpt_id,
            relation="sink",
            value_ref=primary_source,
        )
        for evidence_id in sorted(candidate.evidence_ids)
    )
    origins = tuple(sorted({_driver_origin(entry, row["attacker_source"]) for row in matched_flows}))
    driver_facts = tuple(
        _semantic_fact(
            entry,
            candidate,
            kind="driver_origin",
            value=origin,
            location_ref=handler_excerpt.excerpt_id,
            relation="source",
        )
        for origin in origins
    )
    semantic_values = (
        (
            "value_space",
            _value_space(candidate, bool(matched_flows)),
            "flows_to" if matched_flows else "sink",
        ),
        ("escape_scope", candidate.escape_scope, "sink"),
        ("retention", _retention(candidate), "sink"),
        ("amplification", _amplification(candidate), "sink"),
        ("loop_multiplicity", _loop_multiplicity(candidate), "sink"),
        ("field_identity", _field_identity(candidate), "sink"),
        (
            "materialization_phase",
            entry.materialization_phase
            if entry.materialization_phase in {"before_handler", "in_handler", "streaming", "after_handler"}
            else "unknown",
            "sink",
        ),
        (
            "known_limit_location",
            (
                "configured_unknown_phase"
                if any(_configuration_kind(fact.key) in {"request_limit", "capacity"} for fact in configuration_facts)
                else "none"
            ),
            "bounds",
        ),
    )
    semantic_facts = tuple(
        _semantic_fact(
            entry,
            candidate,
            kind=kind,
            value=value,
            location_ref=growth_excerpt.excerpt_id,
            relation=relation,
            value_ref=primary_source,
        )
        for kind, value, relation in semantic_values
    )
    static_facts = tuple(sorted(
        (*source_facts, *sink_facts, *driver_facts, *semantic_facts),
        key=lambda fact: fact.fact_id,
    ))
    config_facts = tuple(
        ConfigFact(
            kind=_configuration_kind(fact.key),
            normalized_value=(
                fact.value
                if isinstance(fact.value, int) and not isinstance(fact.value, bool)
                else "enabled" if fact.value is True
                else "disabled" if fact.value is False
                else fact.value if fact.value in {"enabled", "disabled", "finite", "unbounded", "unknown"}
                else "unknown"
            ),
            source_location_ref=(
                _covering_excerpt(
                    source_excerpts,
                    fact.source_file,
                    fact.source_line,
                    reason="CONFIG_LOCATION_UNATTESTED",
                ).excerpt_id
                if fact.source_file and fact.source_line >= 1
                else fact.config_id
            ),
            config_id=fact.config_id,
        )
        for fact in configuration_facts
    )
    path_ids = tuple(dict.fromkeys(
        stable_identifier("path", {
            "entry_id": entry.entry_id,
            "growth_id": candidate.growth_id,
            "call_path": row["call_path"],
            "phase_sequence": row["phase_sequence"],
        })
        for row in matched_flows
    ))
    phases = (
        (entry.materialization_phase,)
        if entry.materialization_phase in {"before_handler", "in_handler", "streaming", "after_handler"}
        else ()
    )
    return GrowthStaticEvidence(
        static_facts=static_facts,
        cfg_summary=CfgSummary(
            path_ids,
            phases,
            tuple(fact.fact_id for fact in driver_facts) + tuple(
                fact.fact_id
                for fact in semantic_facts
                if fact.kind in {
                    "value_space", "escape_scope", "retention", "amplification", "loop_multiplicity",
                    "field_identity", "materialization_phase", "known_limit_location",
                }
            ),
        ),
        registration_facts=(
            RegistrationFact(entry.framework, registration_excerpt.excerpt_id),
        ),
        config_facts=config_facts,
        coverage_status=candidate.coverage_status,
        coverage_notes=candidate.coverage_notes,
    )


__all__ = ["GrowthStaticEvidence", "adapt_growth_static_evidence"]
