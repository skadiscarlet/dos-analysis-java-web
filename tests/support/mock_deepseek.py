"""Scriptable local transport for exercising the Responses API client.

It deliberately implements only the transport/verifier seam. Prompt creation,
response parsing, schema validation, HMAC cache handling and private audit
publication remain owned by :class:`dosweb.llm.deepseek.DeepSeekClient`.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dosweb.config import LlmConfig
from dosweb.llm.deepseek import DeepSeekClient, PublicSourceAttestation


ResponseFactory = Callable[[dict[str, object]], dict[str, object]]


@dataclass
class StaticPublicVerifier:
    """No-network verifier used only by the opt-in fixture suite."""

    source_url: str = "https://github.com/example/dosweb-fixture"
    commit: str = "a" * 40
    calls: int = 0
    slice_calls: int = 0

    def verify(self, _config: LlmConfig) -> PublicSourceAttestation:
        self.calls += 1
        return PublicSourceAttestation(self.source_url, self.commit, True, True)

    def validate_slice(self, _config: LlmConfig, _slice: object, _attestation: PublicSourceAttestation) -> None:
        self.slice_calls += 1


class ScriptedDeepSeekTransport:
    """In-memory Responses API transport with deterministic request count."""

    def __init__(self, *, growth: ResponseFactory | None = None, auth: ResponseFactory | None = None) -> None:
        self._growth = growth or growth_yes_from_slice
        self._auth = auth or auth_unauthenticated_from_facts
        self.requests: list[dict[str, object]] = []

    @property
    def request_count(self) -> int:
        return len(self.requests)

    def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
        request = json.loads(payload.decode("utf-8"))
        if not isinstance(request, dict):
            raise AssertionError("provider request must be an object")
        self.requests.append(request)
        instructions = request.get("instructions")
        if not isinstance(instructions, str) or not isinstance(request.get("input"), list):
            raise AssertionError("Responses request missing instructions/input")
        factory = self._auth if "Classify external reachability" in instructions else self._growth
        contract = factory(request)
        return json.dumps({"id": f"fixture-{self.request_count}", "status": "completed", "model": request.get("model", "grok-4.6"), "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(contract, separators=(",", ":"))}]}]}, separators=(",", ":"))


def _prompt_object(request: dict[str, object]) -> dict[str, object]:
    inputs = request["input"]
    assert isinstance(inputs, list) and len(inputs) == 1 and isinstance(inputs[0], dict)
    content = inputs[0].get("content")
    assert isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict)
    text = content[0].get("text")
    assert isinstance(text, str)
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    return parsed


def auth_unauthenticated_from_facts(request: dict[str, object]) -> dict[str, object]:
    prompt = _prompt_object(request)
    facts = prompt.get("security_facts")
    if not isinstance(facts, list) or not facts:
        return {"auth_context": "unknown", "evidence_ids": [], "assumptions": [], "confidence": "low"}
    first = facts[0]
    if not isinstance(first, dict) or first.get("coverage") != "complete" or first.get("value") != "unauthenticated_annotation":
        return {"auth_context": "unknown", "evidence_ids": [], "assumptions": [], "confidence": "low"}
    return {"auth_context": "unauthenticated", "evidence_ids": [first["fact_id"]], "assumptions": [], "confidence": "high"}


def growth_yes_from_slice(request: dict[str, object]) -> dict[str, object]:
    prompt = _prompt_object(request)
    bounded = prompt.get("bounded_slice")
    assert isinstance(bounded, dict)
    facts = bounded.get("static_facts")
    assert isinstance(facts, list)
    flows = [item for item in facts if isinstance(item, dict) and item.get("relation") == "flows_to"]
    sinks = [item for item in facts if isinstance(item, dict) and item.get("relation") == "sink"]
    if not flows or not sinks:
        return {
            "is_resource_growth": "unknown", "growth_kind": "unknown", "resource_dimension": "unknown",
            "attacker_influence": [], "resource_effect": "unknown", "required_static_evidence": [], "confidence": "low",
        }
    sink = sinks[0]
    mapping: dict[str, tuple[str, str, str, str]] = {
        "input_materialization": ("input_materialization", "bytes", "size", "materializes_bytes"),
        "allocation": ("direct_allocation", "bytes", "size", "allocates_objects"),
        "container_write": ("container_growth", "entries", "key", "adds_entries"),
        "async_submission": ("async_work_growth", "tasks", "value", "enqueues_tasks"),
    }
    kind, dimension, target, effect = mapping.get(str(sink.get("kind")), ("unknown", "unknown", "unknown", "unknown"))
    if kind == "unknown":
        return {
            "is_resource_growth": "unknown", "growth_kind": "unknown", "resource_dimension": "unknown",
            "attacker_influence": [], "resource_effect": "unknown", "required_static_evidence": [], "confidence": "low",
        }
    return {
        "is_resource_growth": "yes",
        "growth_kind": kind,
        "resource_dimension": dimension,
        "attacker_influence": [{"target": target, "evidence_id": flows[0]["fact_id"]}],
        "resource_effect": effect,
        "required_static_evidence": [sink["fact_id"]],
        "confidence": "high",
    }


def real_deepseek_factory(transport: ScriptedDeepSeekTransport, verifier: StaticPublicVerifier | None = None) -> Callable[[LlmConfig], DeepSeekClient]:
    verifier = verifier or StaticPublicVerifier()
    return lambda config: DeepSeekClient(config, verifier=verifier, transport=transport, sleep=lambda _delay: None)


__all__ = [
    "ScriptedDeepSeekTransport", "StaticPublicVerifier", "auth_unauthenticated_from_facts",
    "growth_yes_from_slice", "real_deepseek_factory",
]
