from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest

from dosweb.config import LlmConfig
from dosweb.errors import AnalyzerError
from dosweb.llm.deepseek import DeepSeekClient, ProviderReply, _responses_request
from dosweb.llm.prompts import build_auth_messages
from dosweb.llm.schemas import AUTH_PROMPT_VERSION


def _client() -> DeepSeekClient:
    directory = Path(tempfile.mkdtemp())
    return DeepSeekClient(LlmConfig("grok-4.6", "http://127.0.0.1:12345/", "test-key", 1, 1, 0, directory, True, source_checkout=directory), transport=object())  # type: ignore[arg-type]



def _response(*, output: list[object], status: str = "completed", model: str = "grok-4.6") -> ProviderReply:
    return ProviderReply(json.dumps({"id": "request-1", "status": status, "model": model, "output": output}), {})


def test_auth_prompt_requires_all_four_keys_and_v3_cache_version() -> None:
    system = build_auth_messages("entry:ignored", [], [])[0]["content"]
    assert AUTH_PROMPT_VERSION == "auth-contract-v3"
    assert "exactly these four keys: auth_context, evidence_ids, assumptions, confidence" in system
    assert "confidence must be exactly one of high, medium, low" in system
    assert "auth_context unknown and confidence low" in system
    assert "never omit any of the four keys" in system


def test_responses_request_has_only_strict_responses_fields() -> None:
    body = _responses_request("grok-4.6", [{"role": "system", "content": "rule"}, {"role": "user", "content": "facts"}], 0)
    assert body["input"] == [{"role": "user", "content": [{"type": "input_text", "text": "facts"}]}]
    assert body["text"] == {"format": {"type": "json_object"}}
    assert body["store"] is False and body["stream"] is False
    assert "messages" not in body and "response_format" not in body


def test_responses_parser_accepts_reasoning_and_concatenates_output_text() -> None:
    response = _response(output=[
        {"type": "reasoning", "summary": []},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "{"}, {"type": "output_text", "text": "}"},
        ]},
    ])
    assert _client()._response_content(response) == ("{}", "grok-4.6", "request-1")


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
