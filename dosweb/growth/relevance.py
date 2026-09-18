"""Deterministic DoS relevance gate before any Growth Contract call."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from dosweb.entries import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.growth.completeness import CandidateEntryLink
from dosweb.growth.slices import GrowthCandidate


RelevanceStatus = Literal[
    "contract_eligible", "dos_relevant_partial", "rejected", "unresolved"
]
AmplificationClass = Literal[
    "superlinear",
    "large_single_request",
    "queue_instability",
    "concurrent_retention",
    "high_cardinality_retention",
    "low_amplification",
    "unknown",
]

_STATUSES = frozenset(
    {"contract_eligible", "dos_relevant_partial", "rejected", "unresolved"}
)
_AMPLIFICATIONS = frozenset(
    {
        "superlinear",
        "large_single_request",
        "queue_instability",
        "concurrent_retention",
        "high_cardinality_retention",
        "low_amplification",
        "unknown",
    }
)
_TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_REQUEST_LOCAL_CARDINALITY_PROVEN_NOTES = frozenset(
    {
        "request_local_container_write:key_driver_unclassified:"
        "attacker_controlled_loop_cardinality_proven",
        "request_local_container_write:attacker_value_driver:"
        "attacker_controlled_loop_cardinality_proven",
        "request_local_container_write:value_driver_unclassified:"
        "attacker_controlled_loop_cardinality_proven",
    }
)
_SERVER_CONTROLLED_ALLOCATION_NOTES = frozenset(
    {
        "direct_allocation:server_metadata_size",
        "direct_allocation:server_controlled_fixed_size",
    }
)


@dataclass(frozen=True)
class RelevanceDecision:
    status: RelevanceStatus
    amplification_class: AmplificationClass
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.status not in _STATUSES
            or self.amplification_class not in _AMPLIFICATIONS
            or not self.reason_codes
            or len(self.reason_codes) > 16
            or tuple(sorted(set(self.reason_codes))) != self.reason_codes
            or any(
                not isinstance(reason, str)
                or not reason
                or len(reason.encode("utf-8")) > 128
                for reason in self.reason_codes
            )
        ):
            raise AnalyzerError(
                "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
                "Growth relevance decision is invalid.",
            )


def _decision(
    status: RelevanceStatus,
    amplification: AmplificationClass,
    *reasons: str,
) -> RelevanceDecision:
    return RelevanceDecision(status, amplification, tuple(sorted(set(reasons))))


def _test_or_benchmark_path(path: str) -> bool:
    parts = tuple(part.lower() for part in PurePosixPath(path).parts)
    root = parts[0] if parts else ""
    return (
        root in {"test", "tests", "benchmark", "benchmarks"}
        or len(parts) >= 2
        and parts[:2] in {("src", "test"), ("src", "jmh"), ("src", "benchmark")}
    )


def _canonical_link(
    entry: EntryFact | None,
    candidate: GrowthCandidate,
    links: tuple[CandidateEntryLink, ...],
) -> CandidateEntryLink | None:
    if entry is None or len(links) != 1:
        return None
    link = links[0]
    if link.entry_id != entry.entry_id or link.growth_id != candidate.growth_id:
        return None
    return link


def _demand_matches_entry(entry: EntryFact, candidate: GrowthCandidate) -> bool:
    attacker_names = {item.name for item in entry.attacker_inputs}
    for demand in candidate.demand_inputs:
        if demand.name in attacker_names:
            return True
        tokens = set(_TOKEN.findall(demand.name))
        if len(tokens & attacker_names) == 1:
            return True
    return False


def _partial_or_eligible(
    candidate: GrowthCandidate,
    amplification: AmplificationClass,
    reason: str,
) -> RelevanceDecision:
    if candidate.coverage_status == "complete":
        return _decision("contract_eligible", amplification, reason)
    return _decision(
        "dos_relevant_partial",
        amplification,
        reason,
        "RELEVANCE_STATIC_EVIDENCE_PARTIAL",
    )


def evaluate_candidate_relevance(
    entry: EntryFact | None,
    candidate: GrowthCandidate,
    links: Sequence[CandidateEntryLink],
) -> RelevanceDecision:
    """Reject benign screening rows without project, oracle, or truth identities.

    Hard rejection is restricted to complete source-backed facts (or the
    source-set fact that the sink is test/benchmark-only). Partial high-value
    families remain auditable as ``dos_relevant_partial``; other uncertainty
    never reaches the LLM.
    """

    if not isinstance(candidate, GrowthCandidate) or isinstance(links, (str, bytes)):
        raise AnalyzerError(
            "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
            "Growth relevance input is invalid.",
        )
    try:
        materialized_links = tuple(links)
    except (TypeError, ValueError, MemoryError, RecursionError) as exc:
        raise AnalyzerError(
            "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
            "Growth relevance links are invalid.",
        ) from exc
    if any(not isinstance(link, CandidateEntryLink) for link in materialized_links):
        raise AnalyzerError(
            "ANALYSIS_CANDIDATE_COMPLETENESS_INVALID",
            "Growth relevance links are invalid.",
        )
    # A high-fanout association is an unresolved candidate, not a target failure.
    # Rebuild-class apps can emit hundreds of same-file source-order links.
    if len(materialized_links) > 64:
        return _decision(
            "unresolved",
            "unknown",
            "RELEVANCE_LINK_FANOUT_EXCEEDED",
        )
    if _test_or_benchmark_path(candidate.site.file):
        return _decision(
            "rejected", "low_amplification", "RELEVANCE_TEST_OR_BENCHMARK_ONLY"
        )

    notes = set(candidate.coverage_notes)
    note_text = "\n".join(notes)

    # These facts are self-contained and can be rejected even without a
    # canonical Entry association.
    if (
        candidate.kind == "direct_allocation"
        and bool(notes)
        and notes <= _SERVER_CONTROLLED_ALLOCATION_NOTES
    ):
        if candidate.coverage_status == "complete":
            return _decision(
                "rejected",
                "low_amplification",
                "RELEVANCE_SERVER_SIZED_ALLOCATION",
            )
        return _decision(
            "unresolved", "unknown", "RELEVANCE_ALLOCATION_SIZE_ORIGIN_PARTIAL"
        )
    if "server_side_file_materialization" in note_text:
        if candidate.coverage_status == "complete":
            return _decision(
                "rejected",
                "low_amplification",
                "RELEVANCE_SERVER_SIDE_MATERIALIZATION",
            )
        return _decision(
            "unresolved", "unknown", "RELEVANCE_MATERIALIZATION_ORIGIN_PARTIAL"
        )
    if "fixed_key" in note_text:
        if candidate.coverage_status == "complete":
            return _decision(
                "rejected", "low_amplification", "RELEVANCE_FIXED_KEY_RETENTION"
            )
        return _decision(
            "unresolved", "low_amplification", "RELEVANCE_FIXED_KEY_PARTIAL"
        )
    if any(
        marker in note_text
        for marker in (
            "finite_enum_keyspace",
            "finite_class_keyspace",
            "finite_keyspace_complete",
        )
    ):
        if candidate.coverage_status == "complete":
            return _decision(
                "rejected", "low_amplification", "RELEVANCE_FINITE_KEYSPACE"
            )
        return _decision(
            "unresolved", "low_amplification", "RELEVANCE_FINITE_KEYSPACE_PARTIAL"
        )
    link = _canonical_link(entry, candidate, materialized_links)
    if link is None or entry is None:
        return _decision(
            "unresolved", "unknown", "RELEVANCE_CANONICAL_ENTRY_UNPROVEN"
        )
    if link.status != "complete":
        association_partial = True
    else:
        association_partial = False

    if candidate.kind == "input_materialization":
        request_materialization = (
            candidate.operation
            in {
                "spring_request_body_materialization",
                "spring_request_body_string_materialization",
                "netty_full_http_request_string_materialization",
                "servlet_request_string_builder_materialization",
            }
            or any(
                marker in note_text
                for marker in (
                    "recognized_mqtt_payload_api",
                    "recognized_armeria_request_aggregation",
                    "request_stream_origin_proven",
                    "recognized_request_wrapper_string_materialization",
                )
            )
        )
        parser_or_read_all = any(
            marker in note_text
            for marker in (
                "stream_origin_unclassified",
                "recognized_read_all_materialization_api",
                "recognized_byte_array_output_stream_materialization",
                "parser_materialization_partial",
            )
        )
        if request_materialization and not association_partial:
            return _partial_or_eligible(
                candidate,
                "large_single_request",
                "RELEVANCE_REQUEST_MATERIALIZATION",
            )
        if request_materialization or parser_or_read_all:
            return _decision(
                "dos_relevant_partial",
                "large_single_request",
                "RELEVANCE_PARSER_OR_READ_ALL_PARTIAL",
            )
        return _decision(
            "unresolved", "unknown", "RELEVANCE_MATERIALIZATION_ORIGIN_UNKNOWN"
        )

    if candidate.kind == "direct_allocation":
        request_sized = "request_derived_size" in note_text or _demand_matches_entry(
            entry, candidate
        )
        if request_sized and not association_partial:
            return _partial_or_eligible(
                candidate,
                "large_single_request",
                "RELEVANCE_ATTACKER_SIZED_ALLOCATION",
            )
        if request_sized:
            return _decision(
                "dos_relevant_partial",
                "large_single_request",
                "RELEVANCE_ATTACKER_SIZED_ALLOCATION_PARTIAL",
            )
        return _decision(
            "unresolved", "unknown", "RELEVANCE_ALLOCATION_SIZE_ORIGIN_UNKNOWN"
        )

    if candidate.kind == "container_growth":
        if candidate.escape_scope == "request":
            attacker_cardinality = not notes.isdisjoint(
                _REQUEST_LOCAL_CARDINALITY_PROVEN_NOTES
            )
            if attacker_cardinality and not association_partial:
                return _partial_or_eligible(
                    candidate,
                    "superlinear",
                    "RELEVANCE_ATTACKER_CARDINALITY_REQUEST_LOCAL",
                )
            if attacker_cardinality:
                return _decision(
                    "dos_relevant_partial",
                    "superlinear",
                    "RELEVANCE_ATTACKER_CARDINALITY_REQUEST_LOCAL",
                    "RELEVANCE_STATIC_EVIDENCE_PARTIAL",
                )
            return _decision(
                "unresolved",
                "unknown",
                "RELEVANCE_REQUEST_LOCAL_CARDINALITY_UNPROVEN",
            )
        if candidate.escape_scope == "session" and "fresh_session" in note_text:
            return _decision(
                "unresolved",
                "low_amplification",
                "RELEVANCE_SESSION_CARDINALITY_UNPROVEN",
            )
        field_backed = candidate.escape_scope in {"instance", "global"} and (
            "field" in note_text or candidate.receiver.endswith("." + candidate.field_path)
        )
        attacker_driver = (
            "attacker_key_driver" in note_text
            or "attacker_value_driver" in note_text
            or _demand_matches_entry(entry, candidate)
        )
        if field_backed and attacker_driver and not association_partial:
            amplification: AmplificationClass = (
                "superlinear"
                if "attacker_controlled_loop_multiplicity_proven" in note_text
                else "high_cardinality_retention"
            )
            return _partial_or_eligible(
                candidate, amplification, "RELEVANCE_HIGH_CARDINALITY_RETENTION"
            )
        if field_backed:
            return _decision(
                "dos_relevant_partial",
                "high_cardinality_retention",
                "RELEVANCE_FIELD_RETENTION_PARTIAL",
            )
        return _decision(
            "unresolved", "low_amplification", "RELEVANCE_REQUEST_LOCAL_OR_UNKNOWN_RETENTION"
        )

    if candidate.kind == "async_work_growth":
        attacker_loop = "attacker_controlled_loop_multiplicity_proven" in note_text
        if attacker_loop and not association_partial:
            return _partial_or_eligible(
                candidate, "queue_instability", "RELEVANCE_ATTACKER_LOOP_SUBMISSION"
            )
        return _decision(
            "dos_relevant_partial",
            "queue_instability",
            "RELEVANCE_QUEUE_CAPACITY_OR_MULTIPLICITY_PARTIAL",
        )

    return _decision("unresolved", "unknown", "RELEVANCE_FAMILY_UNMODELED")


__all__ = ["RelevanceDecision", "evaluate_candidate_relevance"]
