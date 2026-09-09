from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
from typing import TYPE_CHECKING, Literal

from dosweb.artifacts.identifiers import canonical_json
from dosweb.resource_lifecycle.io import atomic_write_json, effect_from_dict, location_from_dict
from dosweb.resource_lifecycle.models import Effect, SCHEMA_VERSION, SourceLocation

if TYPE_CHECKING:
    from dosweb.resource_lifecycle.adapters import ExtractedFacts


SUMMARY_RECORDING_SCHEMA_VERSION = SCHEMA_VERSION
SUMMARY_VALIDATION_SCHEMA_VERSION = SCHEMA_VERSION
_LEGACY_SUMMARY_RECORDING_SCHEMA_VERSION = (
    "resource-lifecycle-summary-recording-v1"
)
_MAX_SNIPPET_BYTES = 64 * 1024
_MAX_RECORDING_RESPONSES = 4096
_OperationIdentity = tuple[
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str,
    int | None,
    int | None,
    tuple[str, ...],
]


@dataclass(frozen=True)
class FactIndex:
    fact_ids: frozenset[str]
    locations: frozenset[tuple[str, int]]
    parameters: frozenset[str]
    supported_effects: frozenset[tuple[str, str | None, str | None]]
    identity_exact: bool
    normal_exit_covered: bool
    exceptional_exit_covered: bool
    supported_operations: frozenset[_OperationIdentity] = frozenset()
    normal_supported_operations: frozenset[_OperationIdentity] | None = None
    exceptional_supported_operations: frozenset[_OperationIdentity] | None = None
    source_locations: frozenset[tuple[str, int, int, str]] | None = None
    exact_preconditions: frozenset[str] | None = None
    field_holder_ids: frozenset[str] | None = None


@dataclass(frozen=True)
class SummaryProposal:
    summary_id: str
    method: str
    preconditions: tuple[str, ...]
    normal_effects: tuple[Effect, ...]
    exceptional_effects: tuple[Effect, ...]
    captures: tuple[str, ...]
    field_saves: tuple[str, ...]
    location: SourceLocation
    evidence_ids: tuple[str, ...]
    source_kind: Literal["llm_proposed"]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.summary_id, str)
            or not isinstance(self.method, str)
            or not self.summary_id
            or not self.method
            or len(self.summary_id.encode("utf-8")) > 512
            or len(self.method.encode("utf-8")) > 512
            or self.source_kind != "llm_proposed"
        ):
            raise ValueError("summary proposal identity or source is invalid")
        if (
            not self.preconditions
            or not self.evidence_ids
            or any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 2048 for item in self.preconditions)
            or any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 512 for item in self.evidence_ids)
            or any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 512 for item in self.captures + self.field_saves)
        ):
            raise ValueError("summary proposal requires preconditions and evidence")
        if self.location.source_kind != "llm_proposed":
            raise ValueError("summary proposal location must be llm_proposed")
        if any(effect.location.source_kind != "llm_proposed" for effect in self.normal_effects + self.exceptional_effects):
            raise ValueError("summary proposal effect source must be llm_proposed")
        effects_by_id: dict[str, Effect] = {}
        for effect in self.normal_effects + self.exceptional_effects:
            prior = effects_by_id.setdefault(effect.effect_id, effect)
            if prior != effect:
                raise ValueError("summary proposal effect identity is ambiguous")
        if (
            len({effect.effect_id for effect in self.normal_effects}) != len(self.normal_effects)
            or len({effect.effect_id for effect in self.exceptional_effects}) != len(self.exceptional_effects)
        ):
            raise ValueError("summary proposal effect identity is duplicated")


@dataclass(frozen=True)
class ValidationLayer:
    layer: Literal["schema", "location", "parameters", "operation_dataflow", "identity", "exit_coverage"]
    status: Literal["verified", "unresolved", "rejected"]
    reason_code: str | None = None


@dataclass(frozen=True)
class SummaryValidation:
    status: Literal["verified", "unresolved", "rejected"]
    layers: tuple[ValidationLayer, ...]
    usable_effects: tuple[Effect, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class SummaryRequest:
    unknown_effect_id: str
    method: str
    source_path: str
    start_line: int
    end_line: int
    start_column: int
    source_sha256: str
    source_snapshot_sha256: str
    snippet_sha256: str
    signature: str
    model: str
    contract_version: str

    def __post_init__(self) -> None:
        strings = (
            self.unknown_effect_id,
            self.method,
            self.source_path,
            self.signature,
            self.model,
            self.contract_version,
        )
        path = PurePosixPath(self.source_path)
        if (
            any(not isinstance(value, str) or not value for value in strings)
            or any(len(value.encode("utf-8")) > 1024 or any(ord(char) < 32 for char in value) for value in strings)
            or not re.fullmatch(r"effect:[0-9a-f]{24}", self.unknown_effect_id)
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in self.source_path
            or type(self.start_line) is not int
            or type(self.end_line) is not int
            or self.start_line < 1
            or self.end_line < self.start_line
            or type(self.start_column) is not int
            or self.start_column < 1
        ):
            raise ValueError("summary request identity is incomplete")
        if any(
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in (
                self.source_sha256,
                self.source_snapshot_sha256,
                self.snippet_sha256,
            )
        ):
            raise ValueError("summary request hashes are invalid")


@dataclass(frozen=True)
class SummaryBudget:
    max_calls: int
    max_tokens: int
    timeout_ms: int
    max_retries: int

    def __post_init__(self) -> None:
        if (
            type(self.max_calls) is not int
            or type(self.max_tokens) is not int
            or type(self.timeout_ms) is not int
            or type(self.max_retries) is not int
            or self.max_calls <= 0
            or self.max_tokens <= 0
            or self.timeout_ms <= 0
            or not 0 <= self.max_retries <= 3
        ):
            raise ValueError("summary budget is invalid")


@dataclass(frozen=True)
class RecordedUsage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if (
            type(self.input_tokens) is not int
            or type(self.output_tokens) is not int
            or self.input_tokens < 0
            or self.output_tokens < 0
        ):
            raise ValueError("recorded summary usage is invalid")


@dataclass(frozen=True)
class RecordedSummaryResponse:
    unknown_effect_id: str
    snippet: str
    request: SummaryRequest
    proposal: SummaryProposal
    usage: RecordedUsage

    def __post_init__(self) -> None:
        if not isinstance(self.snippet, str):
            raise ValueError("recorded summary response identity is invalid")
        snippet_bytes = self.snippet.encode("utf-8")
        if (
            not isinstance(self.unknown_effect_id, str)
            or not self.unknown_effect_id
            or not self.snippet
            or len(snippet_bytes) > _MAX_SNIPPET_BYTES
            or hashlib.sha256(snippet_bytes).hexdigest() != self.request.snippet_sha256
        ):
            raise ValueError("recorded summary response identity is invalid")


@dataclass(frozen=True)
class SummaryRecording:
    provider: str
    model: str
    contract_version: str
    budget: SummaryBudget
    responses: tuple[RecordedSummaryResponse, ...]

    def __post_init__(self) -> None:
        for value in (self.provider, self.model, self.contract_version):
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256 or any(ord(char) < 32 for char in value):
                raise ValueError("recorded summary provider identity is invalid")
        if len(self.responses) > min(self.budget.max_calls, _MAX_RECORDING_RESPONSES):
            raise ValueError("recorded summary call budget is exhausted")
        if len({item.unknown_effect_id for item in self.responses}) != len(self.responses):
            raise ValueError("recorded summary response target is duplicated")
        if any(
            item.request.model != self.model
            or item.request.contract_version != self.contract_version
            for item in self.responses
        ):
            raise ValueError("recorded summary request provider identity is inconsistent")
        if sum(item.usage.input_tokens + item.usage.output_tokens for item in self.responses) > self.budget.max_tokens:
            raise ValueError("recorded summary token budget is exhausted")


@dataclass(frozen=True)
class AppliedSummaries:
    extracted: ExtractedFacts
    artifact: Mapping[str, object]
    summary_effect_ids: tuple[str, ...]


def _layer(name: str, status: str, reason: str | None = None) -> ValidationLayer:
    return ValidationLayer(name, status, reason)  # type: ignore[arg-type]


def _operation_identity(effect: Effect) -> _OperationIdentity:
    return (
        effect.kind,
        effect.instance_id,
        effect.family_id,
        effect.holder_id,
        effect.target_event_id,
        effect.contract_id,
        effect.condition,
        effect.size_lower,
        effect.size_upper,
        effect.evidence_ids,
    )


def validate_summary(proposal: SummaryProposal, facts: FactIndex) -> SummaryValidation:
    layers: list[ValidationLayer] = [_layer("schema", "verified")]
    all_effects = tuple(dict.fromkeys(proposal.normal_effects + proposal.exceptional_effects))
    if facts.source_locations is not None:
        location_supported = (
            {
                (
                    proposal.location.path,
                    proposal.location.start_line,
                    proposal.location.end_line,
                    proposal.location.source_sha256,
                )
            }
            | {
                (
                    effect.location.path,
                    effect.location.start_line,
                    effect.location.end_line,
                    effect.location.source_sha256,
                )
                for effect in all_effects
            }
        ) <= facts.source_locations
    else:
        location_supported = (
            {(proposal.location.path, proposal.location.start_line)}
            | {(effect.location.path, effect.location.start_line) for effect in all_effects}
        ) <= facts.locations
    if location_supported:
        layers.append(_layer("location", "verified"))
    else:
        layers.append(_layer("location", "rejected", "location_not_in_static_slice"))

    expected_captures = {
        effect.instance_id
        for effect in all_effects
        if effect.kind == "dispatch" and effect.instance_id is not None
    }
    expected_field_saves = {
        effect.holder_id
        for effect in all_effects
        if effect.kind == "retain" and effect.holder_id is not None
    }
    field_saves_are_fields = (
        facts.field_holder_ids is None
        or expected_field_saves <= facts.field_holder_ids
    )
    if facts.exact_preconditions is not None:
        referenced_parameters = (
            len(proposal.preconditions) == len(set(proposal.preconditions))
            and set(proposal.preconditions) == facts.exact_preconditions
            and len(proposal.captures) == len(set(proposal.captures))
            and set(proposal.captures) == expected_captures
            and expected_captures <= facts.parameters
            and len(proposal.field_saves) == len(set(proposal.field_saves))
            and set(proposal.field_saves) == expected_field_saves
            and field_saves_are_fields
        )
    else:
        referenced_parameters = bool({
            parameter
            for parameter in facts.parameters
            if any(parameter in precondition for precondition in proposal.preconditions)
        })
    if referenced_parameters:
        layers.append(_layer("parameters", "verified"))
    else:
        layers.append(
            _layer(
                "parameters",
                "unresolved",
                "field_save_holder_kind_unresolved"
                if not field_saves_are_fields
                else "parameter_mapping_unresolved",
            )
        )

    effect_evidence = {evidence_id for effect in all_effects for evidence_id in effect.evidence_ids}
    if (
        facts.normal_supported_operations is not None
        and facts.exceptional_supported_operations is not None
    ):
        supported_effects = all(
            _operation_identity(effect) in facts.normal_supported_operations
            for effect in proposal.normal_effects
        ) and all(
            _operation_identity(effect) in facts.exceptional_supported_operations
            for effect in proposal.exceptional_effects
        )
    elif facts.supported_operations:
        supported_effects = all(
            _operation_identity(effect) in facts.supported_operations
            for effect in all_effects
        )
    else:
        supported_effects = all(
            (effect.kind, effect.instance_id, effect.holder_id) in facts.supported_effects
            for effect in all_effects
        )
    supported = supported_effects and set(proposal.evidence_ids).union(effect_evidence) <= facts.fact_ids
    if supported:
        layers.append(_layer("operation_dataflow", "verified"))
    else:
        layers.append(_layer("operation_dataflow", "unresolved", "operation_or_dataflow_unresolved"))

    if facts.identity_exact:
        layers.append(_layer("identity", "verified"))
    else:
        layers.append(_layer("identity", "unresolved", "resource_identity_unresolved"))

    normal_exit_covered = not proposal.normal_effects or facts.normal_exit_covered
    exceptional_exit_covered = not proposal.exceptional_effects or facts.exceptional_exit_covered
    if normal_exit_covered and exceptional_exit_covered:
        layers.append(_layer("exit_coverage", "verified"))
    else:
        reason = "exceptional_exit_uncovered" if not exceptional_exit_covered else "normal_exit_uncovered"
        layers.append(_layer("exit_coverage", "unresolved", reason))

    if any(item.status == "rejected" for item in layers):
        status: Literal["verified", "unresolved", "rejected"] = "rejected"
    elif any(item.status == "unresolved" for item in layers):
        status = "unresolved"
    else:
        status = "verified"

    reason_codes = [item.reason_code for item in layers if item.reason_code]
    usable: tuple[Effect, ...] = ()
    if status == "verified":
        usable = tuple(effect for effect in all_effects if effect.kind in {"create", "retain", "dispatch"})
        if any(effect.kind == "release" for effect in all_effects):
            reason_codes.append("llm_proposed_release_cannot_prove_must_release")
        if any(effect.kind == "drop" for effect in all_effects):
            reason_codes.append("llm_proposed_drop_cannot_remove_may_hold")
    return SummaryValidation(status, tuple(layers), usable, tuple(sorted(set(reason_codes))))


def cache_key(request: SummaryRequest, manifest: Mapping[str, object]) -> str:
    identity = {
        "request": asdict(request),
        "tool_version": manifest.get("tool_version"),
        "implementation_sha256": manifest.get("implementation_sha256"),
        "budget": manifest.get("budget"),
    }
    return hashlib.sha256(canonical_json(identity)).hexdigest()


def _proposal_from_dict(value: object) -> SummaryProposal:
    if not isinstance(value, Mapping) or set(value) != {
        "summary_id", "method", "preconditions", "normal_effects", "exceptional_effects",
        "captures", "field_saves", "location", "evidence_ids", "source_kind",
    }:
        raise ValueError("cached summary proposal is invalid")
    record = dict(value)
    for key in ("preconditions", "normal_effects", "exceptional_effects", "captures", "field_saves", "evidence_ids"):
        if not isinstance(record[key], list):
            raise ValueError("cached summary array is invalid")
    for key in ("preconditions", "captures", "field_saves", "evidence_ids"):
        if any(not isinstance(item, str) for item in record[key]):
            raise ValueError("cached summary string array is invalid")
    for key in ("normal_effects", "exceptional_effects"):
        for effect in record[key]:
            if (
                not isinstance(effect, Mapping)
                or not isinstance(effect.get("evidence_ids"), list)
                or any(not isinstance(item, str) for item in effect["evidence_ids"])
            ):
                raise ValueError("cached summary effect array is invalid")
    record["preconditions"] = tuple(record["preconditions"])
    record["normal_effects"] = tuple(effect_from_dict(item) for item in record["normal_effects"])
    record["exceptional_effects"] = tuple(effect_from_dict(item) for item in record["exceptional_effects"])
    record["captures"] = tuple(record["captures"])
    record["field_saves"] = tuple(record["field_saves"])
    record["evidence_ids"] = tuple(record["evidence_ids"])
    record["location"] = location_from_dict(record["location"])
    return SummaryProposal(**record)  # type: ignore[arg-type]


def _request_from_dict(value: object) -> SummaryRequest:
    if not isinstance(value, Mapping) or set(value) != {
        "unknown_effect_id", "method", "source_path", "start_line", "end_line", "start_column",
        "source_sha256", "source_snapshot_sha256", "snippet_sha256", "signature",
        "model", "contract_version",
    }:
        raise ValueError("recorded summary request is invalid")
    return SummaryRequest(**dict(value))  # type: ignore[arg-type]


def _usage_from_dict(value: object) -> RecordedUsage:
    if not isinstance(value, Mapping) or set(value) != {"input_tokens", "output_tokens"}:
        raise ValueError("recorded summary usage is invalid")
    return RecordedUsage(**dict(value))  # type: ignore[arg-type]


def recording_from_dict(value: object) -> SummaryRecording:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "provider", "model", "contract_version", "budget", "responses",
    }:
        raise ValueError("recorded summary configuration fields are invalid")
    if value.get("schema_version") not in {
        SUMMARY_RECORDING_SCHEMA_VERSION,
        _LEGACY_SUMMARY_RECORDING_SCHEMA_VERSION,
    }:
        raise ValueError("recorded summary schema version is invalid")
    budget_value = value.get("budget")
    if not isinstance(budget_value, Mapping) or set(budget_value) != {
        "max_calls", "max_tokens", "timeout_ms", "max_retries",
    }:
        raise ValueError("recorded summary budget fields are invalid")
    responses_value = value.get("responses")
    if not isinstance(responses_value, list) or len(responses_value) > _MAX_RECORDING_RESPONSES:
        raise ValueError("recorded summary responses are invalid")
    responses: list[RecordedSummaryResponse] = []
    for item in responses_value:
        if not isinstance(item, Mapping) or set(item) != {
            "unknown_effect_id", "snippet", "request", "proposal", "usage",
        }:
            raise ValueError("recorded summary response fields are invalid")
        responses.append(
            RecordedSummaryResponse(
                unknown_effect_id=item["unknown_effect_id"],  # type: ignore[arg-type]
                snippet=item["snippet"],  # type: ignore[arg-type]
                request=_request_from_dict(item["request"]),
                proposal=_proposal_from_dict(item["proposal"]),
                usage=_usage_from_dict(item["usage"]),
            )
        )
    return SummaryRecording(
        provider=value["provider"],  # type: ignore[arg-type]
        model=value["model"],  # type: ignore[arg-type]
        contract_version=value["contract_version"],  # type: ignore[arg-type]
        budget=SummaryBudget(**dict(budget_value)),  # type: ignore[arg-type]
        responses=tuple(responses),
    )


def recording_to_dict(recording: SummaryRecording) -> dict[str, object]:
    return {
        "schema_version": SUMMARY_RECORDING_SCHEMA_VERSION,
        "provider": recording.provider,
        "model": recording.model,
        "contract_version": recording.contract_version,
        "budget": asdict(recording.budget),
        "responses": [asdict(item) for item in recording.responses],
    }


def apply_recorded_summaries(extracted: ExtractedFacts, recording: SummaryRecording) -> AppliedSummaries:
    from dosweb.resource_lifecycle.adapters import AnalysisUnit, RawLifecycleFact

    if extracted.source_kind != "static_verified":
        raise ValueError("recorded summaries require static verified facts")
    source_snapshot_sha256 = extracted.coverage.get("source_snapshot_sha256")
    if not isinstance(source_snapshot_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", source_snapshot_sha256
    ):
        raise ValueError("recorded summaries require a verified Java source snapshot")
    raw_by_id = {fact.fact_id: fact for fact in extracted.facts}
    unit_by_unknown: dict[str, AnalysisUnit] = {}
    unknown_by_id: dict[str, Effect] = {}
    source_fact_by_unknown: dict[str, RawLifecycleFact] = {}
    existing_effect_ids: set[str] = set()
    for unit in extracted.units:
        for transition in unit.program.transitions:
            for effect in transition.effects:
                existing_effect_ids.add(effect.effect_id)
                if effect.kind != "unknown_call":
                    continue
                prior = unknown_by_id.setdefault(effect.effect_id, effect)
                if prior != effect or (
                    effect.effect_id in unit_by_unknown
                    and unit_by_unknown[effect.effect_id].unit_id != unit.unit_id
                ):
                    raise ValueError("unknown call effect identity is ambiguous")
                unit_by_unknown[effect.effect_id] = unit

    for effect_id, unknown in unknown_by_id.items():
        source_facts = tuple(
            raw_by_id[evidence_id]
            for evidence_id in unknown.evidence_ids
            if evidence_id in raw_by_id
        )
        if (
            len(source_facts) == 1
            and source_facts[0].fact_kind == "unknown_call"
            and source_facts[0].source_evidence == "codeql_unmodeled_argument_escape"
            and source_facts[0].coverage_note == "callee_resource_effects_unmodeled"
            and source_facts[0].target_event.startswith("java-callable-v1:")
            and source_facts[0].location == unknown.location
        ):
            source_fact_by_unknown[effect_id] = source_facts[0]

    response_ids = {item.unknown_effect_id for item in recording.responses}
    if not response_ids <= set(source_fact_by_unknown):
        raise ValueError("recorded summary response does not target an eligible unknown call")

    proposed_effect_owners: dict[str, str] = {}
    for response in recording.responses:
        for effect in set(response.proposal.normal_effects + response.proposal.exceptional_effects):
            owner = proposed_effect_owners.setdefault(effect.effect_id, response.unknown_effect_id)
            if owner != response.unknown_effect_id:
                raise ValueError("recorded summary effect identity is reused across unknown calls")
    if set(proposed_effect_owners).intersection(existing_effect_ids):
        raise ValueError("recorded summary effect identity collides with static effects")

    path_effects: dict[str, tuple[Effect, ...]] = {}
    records: list[dict[str, object]] = []
    used_effect_ids: set[str] = set()
    for response in sorted(recording.responses, key=lambda item: item.unknown_effect_id):
        unknown = unknown_by_id[response.unknown_effect_id]
        unit = unit_by_unknown[response.unknown_effect_id]
        source_fact = source_fact_by_unknown[response.unknown_effect_id]
        expected_request = SummaryRequest(
            unknown_effect_id=response.unknown_effect_id,
            method=source_fact.target_event,
            source_path=unknown.location.path,
            start_line=unknown.location.start_line,
            end_line=unknown.location.end_line,
            start_column=source_fact.site_start_column,
            source_sha256=unknown.location.source_sha256,
            source_snapshot_sha256=source_snapshot_sha256,
            snippet_sha256=source_fact.site_line_sha256,
            signature=source_fact.target_event,
            model=recording.model,
            contract_version=recording.contract_version,
        )
        if response.request != expected_request or response.proposal.method != expected_request.method:
            raise ValueError("recorded summary request identity does not match the unknown call")

        slice_facts = tuple(
            fact
            for fact in extracted.facts
            if fact.unit_id == unit.unit_id
            and fact.instance_key == source_fact.instance_key
            and fact.location == unknown.location
            and fact.site_start_column == source_fact.site_start_column
        )
        supported_program_effects = tuple(
            effect
            for transition in unit.program.transitions
            for effect in transition.effects
            if effect.kind != "unknown_call"
            and effect.instance_id == unknown.instance_id
            and effect.location == unknown.location
            and effect.location.source_kind == "static_verified"
            and effect.evidence_ids
            and set(effect.evidence_ids) <= {fact.fact_id for fact in slice_facts}
        )
        normal_supported_effects = tuple(
            effect
            for transition in unit.program.transitions
            if transition.exit_kind != "exceptional"
            for effect in transition.effects
            if effect.kind != "unknown_call"
            and effect.instance_id == unknown.instance_id
            and effect.location == unknown.location
            and effect.location.source_kind == "static_verified"
            and effect.evidence_ids
            and set(effect.evidence_ids) <= {fact.fact_id for fact in slice_facts}
        )
        exceptional_supported_effects: tuple[Effect, ...] = ()
        referenced_instances = {
            effect.instance_id
            for effect in response.proposal.normal_effects + response.proposal.exceptional_effects
            if effect.instance_id is not None
        }
        instance_confidence = {
            instance.instance_id: instance.identity_confidence for instance in unit.program.instances
        }
        index = FactIndex(
            fact_ids=frozenset(fact.fact_id for fact in slice_facts),
            locations=frozenset({(unknown.location.path, unknown.location.start_line)}),
            parameters=frozenset({unknown.instance_id} if unknown.instance_id is not None else ()),
            supported_effects=frozenset(
                (effect.kind, effect.instance_id, effect.holder_id)
                for effect in supported_program_effects
            ),
            identity_exact=unknown.instance_id is not None
            and bool(referenced_instances)
            and referenced_instances == {unknown.instance_id}
            and instance_confidence.get(unknown.instance_id) == "exact",
            normal_exit_covered=source_fact.normal_path,
            exceptional_exit_covered=False,
            supported_operations=frozenset(
                (
                    effect.kind,
                    effect.instance_id,
                    effect.family_id,
                    effect.holder_id,
                    effect.target_event_id,
                    effect.contract_id,
                    effect.condition,
                    effect.size_lower,
                    effect.size_upper,
                    effect.evidence_ids,
                )
                for effect in supported_program_effects
            ),
            normal_supported_operations=frozenset(
                (
                    effect.kind,
                    effect.instance_id,
                    effect.family_id,
                    effect.holder_id,
                    effect.target_event_id,
                    effect.contract_id,
                    effect.condition,
                    effect.size_lower,
                    effect.size_upper,
                    effect.evidence_ids,
                )
                for effect in normal_supported_effects
            ),
            exceptional_supported_operations=frozenset(
                (
                    effect.kind,
                    effect.instance_id,
                    effect.family_id,
                    effect.holder_id,
                    effect.target_event_id,
                    effect.contract_id,
                    effect.condition,
                    effect.size_lower,
                    effect.size_upper,
                    effect.evidence_ids,
                )
                for effect in exceptional_supported_effects
            ),
            source_locations=frozenset(
                {
                    (
                        unknown.location.path,
                        unknown.location.start_line,
                        unknown.location.end_line,
                        unknown.location.source_sha256,
                    )
                }
            ),
            exact_preconditions=frozenset(
                {f"resource identity is {unknown.instance_id}"}
                if unknown.instance_id is not None
                else ()
            ),
            field_holder_ids=frozenset(
                holder.holder_id
                for holder in unit.program.holders
                if holder.kind == "field"
            ),
        )
        validation = validate_summary(response.proposal, index)
        static_operation_identities = {
            _operation_identity(effect) for effect in supported_program_effects
        }
        nonduplicated_usable_effects = tuple(
            effect
            for effect in validation.usable_effects
            if _operation_identity(effect) not in static_operation_identities
        )
        if nonduplicated_usable_effects != validation.usable_effects:
            validation = replace(
                validation,
                usable_effects=nonduplicated_usable_effects,
                reason_codes=tuple(
                    sorted(
                        set(validation.reason_codes).union(
                            {"llm_proposed_effect_already_static"}
                        )
                    )
                ),
            )
        usable_ids = {effect.effect_id for effect in validation.usable_effects}
        normal_effects = tuple(effect for effect in response.proposal.normal_effects if effect.effect_id in usable_ids)
        exceptional_effects = tuple(effect for effect in response.proposal.exceptional_effects if effect.effect_id in usable_ids)
        path_effects[response.unknown_effect_id] = tuple(
            dict.fromkeys(normal_effects + exceptional_effects)
        )
        used_effect_ids.update(usable_ids)
        record_body = {
            "unknown_effect_id": response.unknown_effect_id,
            "trigger_evidence_ids": sorted(unknown.evidence_ids),
            "request": asdict(response.request),
            "proposal": asdict(response.proposal),
            "validation": asdict(validation),
            "display_effect_ids": sorted(
                {effect.effect_id for effect in response.proposal.normal_effects + response.proposal.exceptional_effects}
            ),
            "usable_effect_ids": sorted(usable_ids),
            "usage": asdict(response.usage),
        }
        records.append(
            {
                "record_id": hashlib.sha256(canonical_json(record_body)).hexdigest(),
                **record_body,
            }
        )

    units: list[AnalysisUnit] = []
    for unit in extracted.units:
        transitions = []
        for transition in unit.program.transitions:
            effects: list[Effect] = []
            for effect in transition.effects:
                if effect.effect_id in path_effects:
                    effects.extend(path_effects[effect.effect_id])
                effects.append(effect)
            transitions.append(replace(transition, effects=tuple(effects)))
        units.append(replace(unit, program=replace(unit.program, transitions=tuple(transitions))))

    artifact: dict[str, object] = {
        "schema_version": SUMMARY_VALIDATION_SCHEMA_VERSION,
        "provider": recording.provider,
        "model": recording.model,
        "contract_version": recording.contract_version,
        "budget": asdict(recording.budget),
        "calls": len(recording.responses),
        "total_tokens": sum(
            item.usage.input_tokens + item.usage.output_tokens for item in recording.responses
        ),
        "records": records,
    }
    return AppliedSummaries(
        replace(extracted, units=tuple(units)),
        artifact,
        tuple(sorted(used_effect_ids)),
    )


class SummaryCache:
    def __init__(self, root: Path, *, version: str, max_entries: int = 128, max_bytes: int = 4 * 1024 * 1024) -> None:
        if not version or max_entries <= 0 or max_bytes <= 0:
            raise ValueError("summary cache configuration is invalid")
        if root.exists() and root.is_symlink():
            raise ValueError("summary cache root cannot be a symlink")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        self.root = root
        self.version = version
        self.max_entries = max_entries
        self.max_bytes = max_bytes

    def _path(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("summary cache key is invalid")
        return self.root / f"{key}.json"

    def get(self, key: str) -> SummaryProposal | None:
        path = self._path(key)
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > self.max_bytes or stat.S_IMODE(info.st_mode) & 0o077:
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping) or set(value) != {"version", "key", "proposal"}:
                return None
            if value.get("version") != self.version or value.get("key") != key:
                return None
            return _proposal_from_dict(value["proposal"])
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, KeyError):
            return None

    def put(self, key: str, proposal: SummaryProposal) -> None:
        existing = list(self.root.glob("*.json"))
        if len(existing) >= self.max_entries and not self._path(key).exists():
            raise ValueError("summary cache entry budget exhausted")
        payload = {"version": self.version, "key": key, "proposal": asdict(proposal)}
        raw = canonical_json(payload)
        if len(raw) > self.max_bytes:
            raise ValueError("summary cache byte budget exhausted")
        path = self._path(key)
        atomic_write_json(path, payload)
        os.chmod(path, 0o600)
