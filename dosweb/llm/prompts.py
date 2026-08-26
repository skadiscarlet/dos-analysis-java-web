from __future__ import annotations

import json
from dataclasses import dataclass

from dosweb.growth.models import BoundedSlice
from dosweb.llm.schemas import AUTH_CONTRACT_RESPONSE_SCHEMA, AUTH_RESPONSE_SCHEMA_VERSION, GROWTH_CONTRACT_RESPONSE_SCHEMA, RESPONSE_SCHEMA_VERSION

_SYSTEM_MESSAGE = "You classify one bounded public-source static-analysis slice. Use only supplied facts. Return exactly one JSON object with exactly the seven schema keys and no Markdown, extra fields, or prose values. Claims needing proof must cite supplied fact aliases; otherwise answer unknown. Each attacker_influence item has target as exactly one scalar enum string, never an array. growth_kind and resource_dimension must match the cited sink fact; do not infer a different growth kind. Schema: " + json.dumps(GROWTH_CONTRACT_RESPONSE_SCHEMA, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ProviderPayload:
    messages: list[dict[str, str]]
    fact_alias_to_original: dict[str, str]


def build_provider_payload(slice_: BoundedSlice) -> ProviderPayload:
    payload = slice_.normalized_payload
    excerpt_aliases = {item["excerpt_id"]: f"excerpt:{index}" for index, item in enumerate(payload["source_excerpts"], 1)}
    file_aliases = {path: f"source/{index}.java" for index, path in enumerate(dict.fromkeys(item["repo_relative_path"] for item in payload["source_excerpts"]), 1)}
    fact_aliases = {item["fact_id"]: f"fact:{index}" for index, item in enumerate(payload["static_facts"], 1)}
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
    user = {"response_schema_version": RESPONSE_SCHEMA_VERSION, "response_schema": GROWTH_CONTRACT_RESPONSE_SCHEMA, "bounded_slice": aliased}
    messages = [{"role": "system", "content": _SYSTEM_MESSAGE}, {"role": "user", "content": json.dumps(user, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}]
    return ProviderPayload(messages, {alias: original for original, alias in fact_aliases.items()})


def build_growth_messages(slice_: BoundedSlice) -> list[dict[str, str]]:
    return build_provider_payload(slice_).messages


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
