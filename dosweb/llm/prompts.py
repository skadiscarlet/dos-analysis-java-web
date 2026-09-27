from __future__ import annotations

import json
from dataclasses import dataclass

from dosweb.growth.models import BoundedSlice
from dosweb.llm.schemas import AUTH_CONTRACT_RESPONSE_SCHEMA, AUTH_RESPONSE_SCHEMA_VERSION, GROWTH_CONTRACT_RESPONSE_SCHEMA, RESPONSE_SCHEMA_VERSION

_SYSTEM_MESSAGE = (
    "You classify one bounded public-source static-analysis slice as a DoS Growth Contract. "
    "Use only supplied typed facts and return exactly one JSON object with exactly the seventeen "
    "schema keys, no Markdown, no extra fields, and no source code or secrets in free-text fields. "
    "In particular, collection mutation alone is not DoS. A dos_relevant result requires mapped driver, value-space, "
    "retention, amplification, pressure, and failure-mechanism evidence. Cite attacker-controlled flow "
    "facts only through attacker_evidence_ids. Never return growth_kind, resource_dimension, or an attacker "
    "demand role: those values are digest-fixed and derived locally. growth_not_dos_relevant requires a "
    "concrete rejection_reason other than none or unknown. "
    "Use attacker_evidence_ids only from attacker_evidence_options and return only each option's evidence_id; "
    "the paired attacker_target is local binding context, not a response field. If no option exists, "
    "attacker_evidence_ids must be empty and contract_status must not be dos_relevant. "
    "For every dos_relevant result, attacker_value_space must exactly equal a value_space fact cited in "
    "required_static_evidence whose value_ref is the same flow cited in attacker_evidence_ids; a cross-flow "
    "value_space fact never supports that claim. "
    "When evidence is insufficient use contract_status unknown and is_resource_growth unknown; unknown "
    "must never masquerade as no. Claims needing proof must cite supplied fact aliases. Schema: "
    + json.dumps(GROWTH_CONTRACT_RESPONSE_SCHEMA, sort_keys=True, separators=(",", ":"))
)

_CORRECTION_FREE_TEXT_VALUES = {
    "attacker_variable": "typed attacker controlled input",
    "growth_unit": "typed resource units",
    "growth_function": "growth described by cited typed facts",
    "concurrency_model": "request repetition described by cited typed facts",
    "failure_signal": "resource pressure from cited typed facts",
}

_GROWTH_CORRECTION_INVARIANTS = (
    " This is the one correction attempt after the prior response was rejected; "
    "the rejected response is unavailable and must not be discussed, reconstructed, or reproduced. "
    "Re-read only the unchanged bounded_slice. Return one JSON object with exactly these seventeen keys "
    "and no others: "
    + ",".join(GROWTH_CONTRACT_RESPONSE_SCHEMA)
    + ". attacker_evidence_ids must contain at most 16 unique exact fact:<ordinal> aliases, and "
    "required_static_evidence must contain at most 32 unique exact fact:<ordinal> aliases; every alias "
    "must occur in bounded_slice.static_facts. Each attacker_evidence_ids alias must name a flow or "
    "driver_origin fact with relation source or flows_to and must resolve through attacker_target "
    "value_ref links to exactly one attacker target enum value. Do not return original fact IDs, "
    "excerpt/path/config aliases, growth_kind, "
    "resource_dimension, attacker_influence, or any inferred attacker target; those are bound locally. "
    "For contract_status=dos_relevant use is_resource_growth=yes, rejection_reason=none, and non-empty "
    "attacker_evidence_ids and required_static_evidence. For contract_status=growth_not_dos_relevant "
    "use one concrete rejection_reason other than none or unknown. For contract_status=unknown use "
    "is_resource_growth=unknown and rejection_reason=unknown. To prevent source echo, all five free-text "
    "values must exactly equal this fixed abstract mapping: "
    + json.dumps(_CORRECTION_FREE_TEXT_VALUES, sort_keys=True, separators=(",", ":"))
    + ". Never include source code, source paths, URLs, email addresses, phone numbers, personal data, "
    "credentials, authorization data, or secrets. "
    "Use only an evidence_id from attacker_evidence_options for attacker_evidence_ids. "
    "For contract_status=dos_relevant, the cited same-flow value_space fact MUST exactly match attacker_value_space: "
    "it must be in required_static_evidence and its value_ref must equal one cited attacker_evidence_ids alias. "
    "A cross-flow value_space citation is invalid even when its normalized value matches. "
    "A non-empty CFG path with one exact request/network-controlled flow bound by the same value_ref "
    "to an allocation or input_materialization sink, attacker_target=size, value_space in "
    "stream|large|unlimited, retention=request, amplification=large_single_request, and "
    "known_limit_location=none MUST return contract_status=dos_relevant, is_resource_growth=yes, "
    "rejection_reason=none, a concrete failure_mechanism, and requests_to_pressure=one|few. It MUST "
    "cite that exact flow in attacker_evidence_ids and cite the same-flow sink, value_space, retention, "
    "amplification, and known_limit_location facts in required_static_evidence. It must not return "
    "unknown, growth_not_dos_relevant, or splice evidence from another flow. Actual Guard/Bound "
    "effectiveness is decided only by the later Lifecycle stage. "
    "A non-empty CFG path with one exact request/network-controlled flow bound by the same value_ref "
    "to a container_write sink, attacker_target=key|value, value_space=unlimited, retention=process, "
    "amplification=high_cardinality_retention, known_limit_location=none, field_identity=attacker_key, "
    "escape_scope=global, and loop_multiplicity=repeated_requests MUST return contract_status=dos_relevant, "
    "is_resource_growth=yes, resource_effect=adds_entries, rejection_reason=none, a concrete "
    "failure_mechanism, and requests_to_pressure=many. It MUST cite that exact flow in "
    "attacker_evidence_ids and cite the same-flow sink, value_space, retention, amplification, no-limit, "
    "field-identity, escape-scope, and loop-multiplicity facts in required_static_evidence. It must not "
    "return unknown, growth_not_dos_relevant, or splice evidence from another flow. Actual Guard/Bound "
    "effectiveness is decided only by the later Lifecycle stage. "
    "confidence is mandatory and must be exactly high, medium, or low; never omit it. Return JSON only."
)

_EMPTY_ATTACKER_CORRECTION_CONTRACT = {
    "is_resource_growth": "unknown",
    "attacker_evidence_ids": [],
    "resource_effect": "unknown",
    "attacker_variable": _CORRECTION_FREE_TEXT_VALUES["attacker_variable"],
    "attacker_value_space": "unknown",
    "growth_unit": _CORRECTION_FREE_TEXT_VALUES["growth_unit"],
    "growth_function": _CORRECTION_FREE_TEXT_VALUES["growth_function"],
    "amplification_class": "unknown",
    "requests_to_pressure": "unknown",
    "concurrency_model": _CORRECTION_FREE_TEXT_VALUES["concurrency_model"],
    "retention_window": "unknown",
    "failure_mechanism": "unknown",
    "failure_signal": _CORRECTION_FREE_TEXT_VALUES["failure_signal"],
    "required_static_evidence": [],
    "contract_status": "unknown",
    "rejection_reason": "unknown",
    "confidence": "low",
}

_GROWTH_EMPTY_ATTACKER_CORRECTION = (
    " For this exact request attacker_evidence_options is empty. This makes attacker control unproved. "
    "Do not infer, cite, or describe any positive or negative Growth mechanism. Return exactly this "
    "conservative JSON object and no other values: "
    + json.dumps(
        _EMPTY_ATTACKER_CORRECTION_CONTRACT,
        sort_keys=True,
        separators=(",", ":"),
    )
    + ". This fixed unknown object overrides every contrary inference."
)

_AUTH_CORRECTION_INVARIANTS = (
    " This is the one correction attempt after the prior Auth response was rejected; "
    "the rejected response and provider request identifier are unavailable and must not be discussed, "
    "reconstructed, or reproduced. Re-read only the unchanged security_facts and configuration_facts. "
    "Return one JSON object with exactly these four keys and no others: "
    "auth_context,evidence_ids,assumptions,confidence. evidence_ids must be a JSON array containing "
    "at most 32 unique exact security:<ordinal> aliases from security_facts and may be empty. "
    "assumptions must be a JSON array of bounded non-empty text strings and may be empty; never return "
    "a scalar, object, or null for either array. auth_context must be exactly unauthenticated, "
    "low_privilege, privileged, or unknown. confidence must be exactly high, medium, or low. "
    "Do not return source paths, source code, URLs, personal data, credentials, authorization data, "
    "or secrets. Return JSON only."
)


@dataclass(frozen=True)
class ProviderPayload:
    messages: list[dict[str, str]]
    fact_alias_to_original: dict[str, str]
    attacker_evidence_option_ids: tuple[str, ...] = ()


def build_provider_payload(slice_: BoundedSlice) -> ProviderPayload:
    payload = slice_.normalized_payload
    excerpt_aliases = {item["excerpt_id"]: f"excerpt:{index}" for index, item in enumerate(payload["source_excerpts"], 1)}
    file_aliases = {path: f"source/{index}.java" for index, path in enumerate(dict.fromkeys(item["repo_relative_path"] for item in payload["source_excerpts"]), 1)}
    fact_aliases = {item["fact_id"]: f"fact:{index}" for index, item in enumerate(payload["static_facts"], 1)}
    attacker_targets: dict[str, set[str]] = {}
    for item in payload["static_facts"]:
        if item["kind"] == "attacker_target" and item["value_ref"] is not None and item["normalized_value"] is not None:
            attacker_targets.setdefault(item["value_ref"], set()).add(item["normalized_value"])
    attacker_evidence_options = []
    for item in payload["static_facts"]:
        targets = attacker_targets.get(item["fact_id"], set())
        if item["kind"] in {"flow", "driver_origin"} and item["relation"] in {"source", "flows_to"} and len(targets) == 1:
            attacker_evidence_options.append({
                "evidence_id": fact_aliases[item["fact_id"]],
                "attacker_target": next(iter(targets)),
            })
    path_aliases = {item: f"path:{index}" for index, item in enumerate(payload["cfg_summary"]["path_ids"], 1)}
    config_aliases = {config_id: f"config:{index}" for index, config_id in enumerate(dict.fromkeys(item["config_id"] for item in payload["config_facts"] if item["config_id"] is not None), 1)}
    aliased = {
        "entry_id": "entry:1", "growth_id": "growth:1",
        "source_excerpts": [{**item, "excerpt_id": excerpt_aliases[item["excerpt_id"]], "repo_relative_path": file_aliases[item["repo_relative_path"]]} for item in payload["source_excerpts"]],
        "static_facts": [{**item, "fact_id": fact_aliases[item["fact_id"]], "location_ref": excerpt_aliases[item["location_ref"]], "value_ref": fact_aliases.get(item["value_ref"]) if item["value_ref"] is not None else None} for item in payload["static_facts"]],
        "cfg_summary": {"path_ids": [path_aliases[item] for item in payload["cfg_summary"]["path_ids"]], "phases": payload["cfg_summary"]["phases"], "branch_facts": [fact_aliases[item] for item in payload["cfg_summary"]["branch_facts"]]},
        "registration_facts": [{**item, "location_ref": excerpt_aliases[item["location_ref"]]} for item in payload["registration_facts"]],
        "config_facts": [
            {
                **item,
                "config_id": config_aliases.get(item["config_id"]),
                "source_location_ref": (
                    excerpt_aliases[item["source_location_ref"]]
                    if item["source_location_ref"].startswith("excerpt:")
                    else config_aliases[item["source_location_ref"]]
                ),
            }
            for item in payload["config_facts"]
        ],
    }
    user = {"response_schema_version": RESPONSE_SCHEMA_VERSION, "response_schema": GROWTH_CONTRACT_RESPONSE_SCHEMA, "attacker_evidence_options": attacker_evidence_options, "bounded_slice": aliased}
    messages = [{"role": "system", "content": _SYSTEM_MESSAGE}, {"role": "user", "content": json.dumps(user, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}]
    return ProviderPayload(
        messages,
        {alias: original for original, alias in fact_aliases.items()},
        tuple(item["evidence_id"] for item in attacker_evidence_options),
    )


def build_growth_messages(slice_: BoundedSlice) -> list[dict[str, str]]:
    return build_provider_payload(slice_).messages


def build_growth_correction_payload(slice_: BoundedSlice) -> ProviderPayload:
    """Build the sole safe response-correction request without invalid output."""
    initial = build_provider_payload(slice_)
    system = initial.messages[0]["content"] + _GROWTH_CORRECTION_INVARIANTS
    if not initial.attacker_evidence_option_ids:
        system += _GROWTH_EMPTY_ATTACKER_CORRECTION
    return ProviderPayload(
        [
            {"role": "system", "content": system},
            dict(initial.messages[1]),
        ],
        initial.fact_alias_to_original,
        initial.attacker_evidence_option_ids,
    )


def build_auth_messages(entry_id: str, facts: list[dict[str, object]], config_facts: list[dict[str, object]]) -> list[dict[str, str]]:
    """Build a fact-only security prompt; no caller source is accepted outside the slice."""
    user = {
        "response_schema_version": AUTH_RESPONSE_SCHEMA_VERSION,
        "response_schema": AUTH_CONTRACT_RESPONSE_SCHEMA,
        "entry_id": "entry:1",
        "security_facts": facts,
        "configuration_facts": config_facts,
    }
    system = (
        "Classify external reachability using only supplied security/configuration facts. "
        "Return exactly one JSON object with exactly these four keys: auth_context, evidence_ids, assumptions, confidence. "
        "confidence must be exactly one of high, medium, low. Do not infer public access merely "
        "because a security marker is absent; cite fact aliases or return unknown. When evidence is insufficient, "
        "use auth_context unknown and confidence low, but never omit any of the four keys. Schema: "
        + json.dumps(AUTH_CONTRACT_RESPONSE_SCHEMA, sort_keys=True, separators=(",", ":"))
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}]


def build_auth_correction_messages(entry_id: str, facts: list[dict[str, object]], config_facts: list[dict[str, object]]) -> list[dict[str, str]]:
    """Build the sole Auth correction prompt without any rejected response state."""
    initial = build_auth_messages(entry_id, facts, config_facts)
    return [
        {"role": "system", "content": initial[0]["content"] + _AUTH_CORRECTION_INVARIANTS},
        dict(initial[1]),
    ]
