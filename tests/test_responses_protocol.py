from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from dosweb.config import LlmConfig
from dosweb.errors import AnalyzerError
from dosweb.llm.deepseek import (
    DeepSeekClient,
    ProviderReply,
    _reject_sensitive_envelope,
    _reject_sensitive_provider_id,
    _reject_sensitive_response,
    _responses_request,
)
from dosweb.llm.prompts import build_auth_messages
from dosweb.llm import schemas as llm_schemas
from dosweb.llm.schemas import AUTH_PROMPT_VERSION


def _client() -> DeepSeekClient:
    directory = Path(tempfile.mkdtemp())
    return DeepSeekClient(LlmConfig("grok-4.6", "http://127.0.0.1:12345/", "test-key", 1, 1, 0, directory, True, source_checkout=directory), transport=object())  # type: ignore[arg-type]



def _response(*, output: list[object], status: str = "completed", model: str = "grok-4.6") -> ProviderReply:
    return ProviderReply(json.dumps({"id": "request-1", "status": status, "model": model, "output": output}), {})


def test_auth_prompt_requires_all_four_keys_and_v5_prompt_version() -> None:
    system = build_auth_messages("entry:ignored", [], [])[0]["content"]
    assert AUTH_PROMPT_VERSION == "auth-contract-v5"
    assert "exactly these four keys: auth_context, evidence_ids, assumptions, confidence" in system
    assert "confidence must be exactly one of high, medium, low" in system
    assert "auth_context unknown and confidence low" in system
    assert "never omit any of the four keys" in system


def test_responses_request_has_only_strict_responses_fields() -> None:
    body = _responses_request("grok-4.6", [{"role": "system", "content": "rule"}, {"role": "user", "content": "facts"}], 0)
    assert body["input"] == [{"role": "user", "content": [{"type": "input_text", "text": "facts"}]}]
    assert body["text"] == {
        "format": {
            "type": "json_schema",
            "name": "growth_contract",
            "strict": True,
            "schema": llm_schemas.GROWTH_CONTRACT_JSON_SCHEMA,
        }
    }
    assert body["store"] is False and body["stream"] is False
    assert "messages" not in body and "response_format" not in body
    assert set(body["text"]["format"]["schema"]) == {
        "type",
        "properties",
        "required",
        "additionalProperties",
    }


def test_auth_responses_request_uses_its_own_strict_json_schema() -> None:
    body = _responses_request(
        "grok-4.6",
        [{"role": "system", "content": "rule"}, {"role": "user", "content": "facts"}],
        0,
        contract_kind="auth",
    )

    assert body["text"] == {
        "format": {
            "type": "json_schema",
            "name": "auth_contract",
            "strict": True,
            "schema": llm_schemas.AUTH_CONTRACT_JSON_SCHEMA,
        }
    }


def test_growth_json_schema_is_flat_and_requires_exactly_all_seventeen_keys() -> None:
    assert llm_schemas.GROWTH_CONTRACT_JSON_SCHEMA["required"] == sorted(
        llm_schemas.GROWTH_CONTRACT_JSON_SCHEMA["properties"]
    )
    assert len(llm_schemas.GROWTH_CONTRACT_JSON_SCHEMA["required"]) == 17
    assert llm_schemas.GROWTH_CONTRACT_JSON_SCHEMA["additionalProperties"] is False
    assert set(llm_schemas.GROWTH_CONTRACT_JSON_SCHEMA) == {
        "type",
        "properties",
        "required",
        "additionalProperties",
    }

    composition_keywords = frozenset(
        {"allOf", "anyOf", "oneOf", "not", "if", "then", "else", "const"}
    )

    def assert_flat(value: object) -> None:
        if isinstance(value, dict):
            assert composition_keywords.isdisjoint(value)
            for child in value.values():
                assert_flat(child)
        elif isinstance(value, list):
            for child in value:
                assert_flat(child)

    assert_flat(llm_schemas.GROWTH_CONTRACT_JSON_SCHEMA)


def test_responses_parser_accepts_reasoning_and_concatenates_output_text() -> None:
    response = _response(output=[
        {"type": "reasoning", "summary": []},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "{"}, {"type": "output_text", "text": "}"},
        ]},
    ])
    assert _client()._response_content(response) == ("{}", "grok-4.6", "request-1")


def test_responses_parser_rejects_unknown_assistant_content_part() -> None:
    response = _response(
        output=[
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "{}"},
                    {
                        "type": "future_protocol_part",
                        "payload": "unknown-part-owner@example.test",
                    },
                ],
            }
        ]
    )

    with pytest.raises(AnalyzerError) as raised:
        _client()._response_content(response)

    assert raised.value.code == "LLM_RESPONSE_INVALID"


@pytest.mark.parametrize(
    "pii",
    ["owner@example.test", "+1 415-555-2671", "123-45-6789"],
)
def test_raw_envelope_metadata_omits_generic_pii_but_semantic_content_rejects(
    pii: str,
) -> None:
    _reject_sensitive_envelope(json.dumps({"metadata": pii}), "configured-key", ())

    with pytest.raises(AnalyzerError, match="sensitive content"):
        _reject_sensitive_response(pii, None, "configured-key", ())


def test_phone_like_provider_request_id_omits_generic_phone_pii_rule() -> None:
    _reject_sensitive_provider_id("415-555-2671", "configured-key", ())


@pytest.mark.parametrize(
    ("marker", "configured_key"),
    [
        ("configured-key-value", "configured-key-value"),
        ("api_key=credential-value", "different-key"),
        ("Authorization: Bearer credential-value", "different-key"),
        ("-----BEGIN PRIVATE KEY-----", "different-key"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature", "different-key"),
        ("postgresql://user:password@datastore.example/app", "different-key"),
    ],
)
def test_fixed_credential_rules_remain_active_in_all_response_layers(
    marker: str,
    configured_key: str,
) -> None:
    with pytest.raises(AnalyzerError, match="sensitive content"):
        _reject_sensitive_envelope(marker, configured_key, ())
    with pytest.raises(AnalyzerError, match="sensitive content"):
        _reject_sensitive_response(marker, None, configured_key, ())
    with pytest.raises(AnalyzerError, match="sensitive content"):
        _reject_sensitive_provider_id(marker, configured_key, ())


def test_extra_secret_pattern_remains_active_in_all_response_layers() -> None:
    marker = "caller-private-marker"
    extra = (("caller-policy", re.compile(marker)),)

    with pytest.raises(AnalyzerError, match="sensitive content"):
        _reject_sensitive_envelope(marker, "configured-key", extra)
    with pytest.raises(AnalyzerError, match="sensitive content"):
        _reject_sensitive_response(marker, None, "configured-key", extra)
    with pytest.raises(AnalyzerError, match="sensitive content"):
        _reject_sensitive_provider_id(marker, "configured-key", extra)


@pytest.mark.parametrize("response", [
    _response(output=[]),
    _response(status="in_progress", output=[]),
    _response(output=[{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": "no"}]}]),
    _response(output=[{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "x"}]}, {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "y"}]}]),
    _response(model="other", output=[{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "x"}]}]),
])
def test_responses_parser_rejects_incomplete_refusal_ambiguous_or_wrong_model(response: ProviderReply) -> None:
    with pytest.raises(AnalyzerError, match="Responses API"):
        _client()._response_content(response)
