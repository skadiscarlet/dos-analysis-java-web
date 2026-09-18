from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from pathlib import Path

import pytest

from dosweb.artifacts.identifiers import canonical_json, sha256_canonical_json
from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.config import LlmConfig
from dosweb.errors import AnalyzerError
from dosweb.llm.cache import AUTH_CACHE_FORMAT, ContractCache
from dosweb.llm.deepseek import DeepSeekClient, ProviderReply
from dosweb.llm.schemas import AUTH_PROMPT_VERSION, AUTH_RESPONSE_SCHEMA_VERSION
from dosweb.reachability.models import EntrySecurityFact
from tests.support.mock_deepseek import ScriptedDeepSeekTransport, StaticPublicVerifier


def _fact() -> EntrySecurityFact:
    return EntrySecurityFact(
        "entry:1",
        "annotation",
        "Fixture.java",
        7,
        "unauthenticated_annotation",
        "complete",
    )


def _valid_auth() -> dict[str, object]:
    return {
        "auth_context": "unauthenticated",
        "evidence_ids": ["security:1"],
        "assumptions": [],
        "confidence": "high",
    }


def _auth_json_with_unicode_escaped_value(payload: dict[str, object], value: str) -> str:
    placeholder = "unicode-escape-placeholder"

    def replace_value(item: object) -> object:
        if isinstance(item, dict):
            return {key: replace_value(child) for key, child in item.items()}
        if isinstance(item, list):
            return [replace_value(child) for child in item]
        return placeholder if item == value else item

    serialized = json.dumps(replace_value(payload), separators=(",", ":"))
    escaped = "".join(f"\\u{ord(character):04x}" for character in value)
    needle = json.dumps(placeholder)
    assert needle in serialized
    return serialized.replace(needle, f'"{escaped}"')


def _auth_envelope(request: dict[str, object], content: str, request_id: str) -> str:
    return json.dumps(
        {
            "id": request_id,
            "status": "completed",
            "model": request["model"],
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content}],
                }
            ],
        },
        separators=(",", ":"),
    )


def _client(
    tmp_path: Path,
    transport: object,
    *,
    extra_secret_patterns: tuple[tuple[str, re.Pattern[str]], ...] = (),
) -> DeepSeekClient:
    return DeepSeekClient(
        LlmConfig(
            model="grok-4.6",
            base_url="http://127.0.0.1:1/",
            api_key="test-api-key",
            timeout_seconds=3,
            max_retries=1,
            temperature=0,
            cache_dir=tmp_path / "cache",
            allow_remote_llm=True,
            source_checkout=tmp_path,
        ),
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        extra_secret_patterns=extra_secret_patterns,
        sleep=lambda _delay: None,
    )


def _prompt_object(request: dict[str, object]) -> dict[str, object]:
    inputs = request["input"]
    assert isinstance(inputs, list) and len(inputs) == 1
    content = inputs[0]["content"]  # type: ignore[index]
    assert isinstance(content, list) and len(content) == 1
    text = content[0]["text"]  # type: ignore[index]
    assert isinstance(text, str)
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    return parsed


def _contains_marker(value: object, marker: str, seen: set[int] | None = None) -> bool:
    if isinstance(value, str):
        return marker in value
    if isinstance(value, bytes):
        return marker.encode() in value
    seen = set() if seen is None else seen
    if id(value) in seen:
        return False
    seen.add(id(value))
    if isinstance(value, ProviderReply):
        return _contains_marker(value.body, marker, seen) or _contains_marker(value.headers, marker, seen)
    if isinstance(value, dict):
        return any(_contains_marker(item, marker, seen) for pair in value.items() for item in pair)
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_marker(item, marker, seen) for item in value)
    if hasattr(value, "__dict__") and value.__class__.__module__ == "dosweb.llm.deepseek":
        return _contains_marker(vars(value), marker, seen)
    return False


def _assert_traceback_clean(error: BaseException, marker: str) -> None:
    current: BaseException | None = error
    seen_errors: set[int] = set()
    while current is not None and id(current) not in seen_errors:
        seen_errors.add(id(current))
        traceback = current.__traceback__
        while traceback is not None:
            if traceback.tb_frame.f_globals.get("__name__") != __name__:
                for name, value in tuple(traceback.tb_frame.f_locals.items()):
                    assert not _contains_marker(value, marker), (
                        f"rejected marker retained in {traceback.tb_frame.f_code.co_name}:{name}"
                    )
            traceback = traceback.tb_next
        current = current.__cause__ or current.__context__


def test_auth_schema_invalid_gets_one_safe_correction_and_cache_replays_prompt(
    tmp_path: Path,
) -> None:
    attempts = 0
    marker = "first-invalid-auth-assumptions-scalar"

    def auth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return {**_valid_auth(), "assumptions": marker}
        return _valid_auth()

    transport = ScriptedDeepSeekTransport(auth=auth)
    fresh = _client(tmp_path, transport)
    fact = _fact()

    contract = fresh.classify_auth("entry:1", (fact,))

    assert contract.evidence_ids == (fact.fact_id,)
    assert transport.request_count == 2
    initial, correction = transport.requests
    assert _prompt_object(initial) == _prompt_object(correction)
    assert marker not in str(correction)
    assert "fixture-1" not in str(correction)
    instructions = correction["instructions"]
    assert isinstance(instructions, str)
    assert "one correction attempt" in instructions
    assert "exactly these four keys" in instructions
    assert "evidence_ids must be a JSON array" in instructions
    assert "assumptions must be a JSON array" in instructions
    assert "may be empty" in instructions
    assert "high, medium, or low" in instructions
    fresh_audit = fresh.last_audit()
    assert fresh_audit is not None
    assert "one correction attempt" in fresh_audit.normalized_prompt

    cache_file = next((tmp_path / "cache").glob("auth-*.json"))
    cache_record = json.loads(cache_file.read_text(encoding="utf-8"))
    assert AUTH_CACHE_FORMAT == "auth-contract-cache-v5"
    assert cache_record["cache_format"] == AUTH_CACHE_FORMAT
    assert cache_record["identity"]["auth_cache_format"] == AUTH_CACHE_FORMAT
    assert cache_record["accepted_prompt_variant"] == "correction"
    assert marker not in cache_file.read_text(encoding="utf-8")

    replay = _client(tmp_path, transport)
    assert replay.classify_auth("entry:1", (fact,)) == contract
    replay_audit = replay.last_audit()
    assert replay_audit is not None and replay_audit.cache_hit is True
    assert replay_audit.normalized_prompt == fresh_audit.normalized_prompt
    assert transport.request_count == 2


def test_auth_disk_replay_preserves_provider_model_alias(tmp_path: Path) -> None:
    class AliasModelTransport(ScriptedDeepSeekTransport):
        def post(
            self,
            endpoint: str,
            payload: bytes,
            headers: dict[str, str],
            timeout: int,
        ) -> str:
            response = json.loads(super().post(endpoint, payload, headers, timeout))
            response["model"] = "grok-4.6-build"
            return json.dumps(response, separators=(",", ":"))

    transport = AliasModelTransport(auth=lambda _request: _valid_auth())
    fact = _fact()

    fresh = _client(tmp_path, transport)
    expected = fresh.classify_auth("entry:1", (fact,))
    fresh_audit = fresh.last_audit()
    assert fresh_audit is not None
    assert fresh_audit.settings["actual_model"] == "grok-4.6-build"

    cache_file = next((tmp_path / "cache").glob("auth-*.json"))
    cache_record = json.loads(cache_file.read_text(encoding="utf-8"))
    assert cache_record["actual_model"] == "grok-4.6-build"

    replay = _client(tmp_path, transport)
    assert replay.classify_auth("entry:1", (fact,)) == expected
    replay_audit = replay.last_audit()
    assert replay_audit is not None and replay_audit.cache_hit is True
    assert replay_audit.settings["actual_model"] == "grok-4.6-build"
    assert transport.request_count == 1


def test_auth_cache_rejects_hmac_valid_unapproved_actual_model(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache = ContractCache(cache_dir, "test-api-key")
    key = "b" * 64
    identity = {"kind": "auth", "model": "grok-4.6"}
    assert cache.put_auth_record(
        key,
        identity,
        _valid_auth(),
        "{}",
        actual_model="grok-4.6-build",
    )

    path = cache_dir / f"auth-{key}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["actual_model"] = "unapproved-provider-model"
    unsigned = {
        name: value for name, value in record.items() if name != "entry_hmac"
    }
    unsigned["entry_hash"] = sha256_canonical_json(
        {name: value for name, value in unsigned.items() if name != "entry_hash"}
    )
    record.update(unsigned)
    record["entry_hmac"] = hmac.new(
        b"test-api-key",
        b"auth-contract-cache-v5\0" + canonical_json(unsigned),
        hashlib.sha256,
    ).hexdigest()
    path.write_bytes(canonical_json(record))

    assert cache.get_auth_record(key, identity) is None


def test_auth_sensitive_response_gets_one_safe_correction_without_echo(
    tmp_path: Path,
) -> None:
    attempts = 0
    marker = "first-sensitive-auth@example.test"

    def auth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return {**_valid_auth(), "assumptions": [marker]} if attempts == 1 else _valid_auth()

    transport = ScriptedDeepSeekTransport(auth=auth)
    client = _client(tmp_path, transport)

    client.classify_auth("entry:1", (_fact(),))

    assert transport.request_count == 2
    assert marker not in str(transport.requests[1])
    assert marker not in next((tmp_path / "cache").glob("auth-*.json")).read_text(encoding="utf-8")
    assert client.last_audit() is not None
    assert marker not in client.last_audit().raw_response  # type: ignore[union-attr]


def test_unicode_escaped_configured_key_gets_one_safe_auth_correction(
    tmp_path: Path,
) -> None:
    marker = "test-api-key"

    class EscapedThenSafeTransport:
        def __init__(self) -> None:
            self.request_count = 0
            self.requests: list[dict[str, object]] = []

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            self.requests.append(request)
            contract = {
                **_valid_auth(),
                "assumptions": [marker] if self.request_count == 1 else [],
            }
            content = (
                _auth_json_with_unicode_escaped_value(contract, marker)
                if self.request_count == 1
                else json.dumps(contract)
            )
            return _auth_envelope(request, content, f"auth-escaped-key-{self.request_count}")

    transport = EscapedThenSafeTransport()
    client = _client(tmp_path, transport)

    contract = client.classify_auth("entry:1", (_fact(),))

    assert contract.auth_context == "unauthenticated"
    assert transport.request_count == 2
    assert marker not in str(transport.requests[1])
    audit = client.last_audit()
    assert audit is not None and marker not in audit.raw_response
    cache_file = next((tmp_path / "cache").glob("auth-*.json"))
    assert marker not in cache_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "marker",
    ["unknown-auth-part-owner@example.test", "unknown-auth-part-plain-marker"],
)
def test_auth_unknown_assistant_content_part_is_permanent_protocol_failure(
    tmp_path: Path,
    marker: str,
) -> None:
    class UnknownPartTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            return json.dumps(
                {
                    "id": "auth-unknown-part",
                    "status": "completed",
                    "model": request["model"],
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(_valid_auth()),
                                },
                                {
                                    "type": "future_protocol_part",
                                    "payload": marker,
                                },
                            ],
                        }
                    ],
                },
                separators=(",", ":"),
            )

    transport = UnknownPartTransport()
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_RESPONSE_INVALID"
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 1
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("auth-*.json")) == []


def _resign_auth_cache_record(
    cache_file: Path,
    mutate: object,
) -> dict[str, object]:
    record = json.loads(cache_file.read_text(encoding="utf-8"))
    assert isinstance(record, dict) and callable(mutate)
    mutate(record)
    unsigned = {name: value for name, value in record.items() if name != "entry_hmac"}
    unsigned["entry_hash"] = sha256_canonical_json(
        {name: value for name, value in unsigned.items() if name != "entry_hash"}
    )
    record.update(unsigned)
    record["entry_hmac"] = hmac.new(
        b"test-api-key",
        b"auth-contract-cache-v5\0" + canonical_json(unsigned),
        hashlib.sha256,
    ).hexdigest()
    cache_file.write_bytes(canonical_json(record))
    return record


def test_auth_cache_replay_scans_unicode_decoded_semantic_before_audit(
    tmp_path: Path,
) -> None:
    marker = "escaped-auth-cache-owner@example.test"
    transport = ScriptedDeepSeekTransport(auth=lambda _request: _valid_auth())
    _client(tmp_path, transport).classify_auth("entry:1", (_fact(),))
    cache_file = next((tmp_path / "cache").glob("auth-*.json"))

    def mutate(record: dict[str, object]) -> None:
        envelope = json.loads(record["raw_response"])
        content = envelope["output"][0]["content"][0]["text"]
        semantic = json.loads(content)
        semantic["assumptions"] = [marker]
        envelope["output"][0]["content"][0]["text"] = (
            _auth_json_with_unicode_escaped_value(semantic, marker)
        )
        record["raw_response"] = json.dumps(envelope, separators=(",", ":"))
        record["contract"]["assumptions"] = [marker]

    _resign_auth_cache_record(cache_file, mutate)
    replay = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        replay.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 1
    assert replay.last_audit() is None


def test_auth_cache_replay_rejects_hmac_valid_raw_typed_mismatch(
    tmp_path: Path,
) -> None:
    transport = ScriptedDeepSeekTransport(auth=lambda _request: _valid_auth())
    _client(tmp_path, transport).classify_auth("entry:1", (_fact(),))
    cache_file = next((tmp_path / "cache").glob("auth-*.json"))

    def mutate(record: dict[str, object]) -> None:
        record["contract"]["assumptions"] = ["typed-only-mismatch"]

    _resign_auth_cache_record(cache_file, mutate)
    replay = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        replay.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert transport.request_count == 1
    assert replay.last_audit() is None


def test_unicode_escaped_auth_semantic_extra_is_rechecked_on_cache_replay(
    tmp_path: Path,
) -> None:
    marker = "escaped-auth-caller-policy-marker"

    class EscapedSemanticTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            semantic = {**_valid_auth(), "assumptions": [marker]}
            return _auth_envelope(
                request,
                _auth_json_with_unicode_escaped_value(semantic, marker),
                "auth-escaped-extra",
            )

    transport = EscapedSemanticTransport()
    lax = _client(tmp_path, transport)
    lax.classify_auth("entry:1", (_fact(),))
    strict = _client(
        tmp_path,
        transport,
        extra_secret_patterns=(("caller-policy", re.compile(marker)),),
    )

    with pytest.raises(AnalyzerError) as raised:
        strict.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 1
    assert strict.last_audit() is None


@pytest.mark.parametrize("failure_kind", ["schema", "sensitive"])
def test_second_auth_correction_failure_is_terminal_without_cache_or_audit(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    marker = (
        "terminal-auth-schema-assumptions-scalar"
        if failure_kind == "schema"
        else "+1 415-555-2671"
    )

    def auth(_request: dict[str, object]) -> dict[str, object]:
        return {
            **_valid_auth(),
            "assumptions": marker if failure_kind == "schema" else [marker],
        }

    transport = ScriptedDeepSeekTransport(auth=auth)
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == (
        "LLM_RESPONSE_SCHEMA_INVALID"
        if failure_kind == "schema"
        else "LLM_RESPONSE_SENSITIVE_CONTENT"
    )
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 2
    assert list((tmp_path / "cache").glob("auth-*.json")) == []
    assert client.last_audit() is None


def test_first_rejected_auth_body_is_cleared_when_correction_transport_fails(
    tmp_path: Path,
) -> None:
    marker = "first-auth-sensitive-before-network@example.test"

    class SensitiveThenFailure:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            if self.request_count == 2:
                raise OSError("deterministic correction failure")
            body = {**_valid_auth(), "assumptions": [marker]}
            return json.dumps({
                "id": "first-auth-request-id",
                "status": "completed",
                "model": request["model"],
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(body)}]}],
            })

    transport = SensitiveThenFailure()
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_NETWORK_FAILED"
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 2
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("auth-*.json")) == []


def test_auth_cache_hit_applies_each_clients_custom_policy_without_network(
    tmp_path: Path,
) -> None:
    marker = "auth-cache-custom-policy-marker"

    class OneShotMetadataTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            if self.request_count != 1:
                raise AssertionError("cache policy rejection must not call provider")
            request = json.loads(payload)
            return json.dumps({
                "id": "auth-cache-fixture",
                "status": "completed",
                "model": request["model"],
                "metadata": marker,
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(_valid_auth())}]}],
            })

    transport = OneShotMetadataTransport()
    _client(tmp_path, transport).classify_auth("entry:1", (_fact(),))
    strict = _client(
        tmp_path,
        transport,
        extra_secret_patterns=(("custom", re.compile(marker)),),
    )

    with pytest.raises(AnalyzerError) as raised:
        strict.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 1
    assert strict.last_audit() is None


def test_auth_thread_single_flight_shares_snapshot_but_rechecks_waiter_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "auth-single-flight-policy-marker"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    waiter_joined = threading.Event()

    class BlockingTransport:
        def __init__(self) -> None:
            self.request_count = 0
            self.lock = threading.Lock()

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            with self.lock:
                self.request_count += 1
            provider_entered.set()
            assert release_provider.wait(5)
            request = json.loads(payload)
            return json.dumps({
                "id": "auth-single-flight-fixture",
                "status": "completed",
                "model": request["model"],
                "metadata": marker,
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(_valid_auth())}]}],
            })

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_auth_inflight

    def observed_join(key: str):
        state, owner = original_join(key)
        if not owner:
            waiter_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_auth_inflight", observed_join)
    transport = BlockingTransport()
    owner = _client(tmp_path, transport)
    strict = _client(
        tmp_path,
        transport,
        extra_secret_patterns=(("custom", re.compile(marker)),),
    )
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_auth("entry:1", (_fact(),))
        except BaseException as exc:
            results[name] = exc

    owner_thread = threading.Thread(target=classify, args=("owner", owner))
    waiter_thread = threading.Thread(target=classify, args=("strict", strict))
    owner_thread.start()
    assert provider_entered.wait(5)
    waiter_thread.start()
    assert waiter_joined.wait(5)
    release_provider.set()
    for worker in (owner_thread, waiter_thread):
        worker.join(5)
        assert not worker.is_alive()

    assert transport.request_count == 1
    assert not isinstance(results["owner"], BaseException)
    assert owner.last_audit() is not None and owner.last_audit().cache_hit is False
    assert isinstance(results["strict"], AnalyzerError)
    assert results["strict"].code == "LLM_RESPONSE_SENSITIVE_CONTENT"  # type: ignore[union-attr]
    _assert_traceback_clean(results["strict"], marker)  # type: ignore[arg-type]
    assert strict.last_audit() is None


def test_auth_strict_owner_does_not_force_lax_waiter_to_refetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "auth-strict-owner-policy-marker"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    waiter_joined = threading.Event()

    class BlockingTransport:
        def __init__(self) -> None:
            self.request_count = 0
            self.lock = threading.Lock()

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            with self.lock:
                self.request_count += 1
            provider_entered.set()
            assert release_provider.wait(5)
            request = json.loads(payload)
            return json.dumps({
                "id": "auth-strict-owner-fixture",
                "status": "completed",
                "model": request["model"],
                "metadata": marker,
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(_valid_auth())}]}],
            })

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_auth_inflight

    def observed_join(key: str):
        state, owner = original_join(key)
        if not owner:
            waiter_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_auth_inflight", observed_join)
    transport = BlockingTransport()
    strict_owner = _client(
        tmp_path,
        transport,
        extra_secret_patterns=(("custom", re.compile(marker)),),
    )
    lax_waiter = _client(tmp_path, transport)
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_auth("entry:1", (_fact(),))
        except BaseException as exc:
            results[name] = exc

    owner_thread = threading.Thread(target=classify, args=("strict", strict_owner))
    waiter_thread = threading.Thread(target=classify, args=("lax", lax_waiter))
    owner_thread.start()
    assert provider_entered.wait(5)
    waiter_thread.start()
    assert waiter_joined.wait(5)
    release_provider.set()
    for worker in (owner_thread, waiter_thread):
        worker.join(5)
        assert not worker.is_alive()

    assert transport.request_count == 1
    assert isinstance(results["strict"], AnalyzerError)
    assert results["strict"].code == "LLM_RESPONSE_SENSITIVE_CONTENT"  # type: ignore[union-attr]
    _assert_traceback_clean(results["strict"], marker)  # type: ignore[arg-type]
    assert not isinstance(results["lax"], BaseException)
    assert strict_owner.last_audit() is None
    lax_audit = lax_waiter.last_audit()
    assert lax_audit is not None and lax_audit.cache_hit is True
    assert marker in lax_audit.raw_response
    assert len(list((tmp_path / "cache").glob("auth-*.json"))) == 1


def test_auth_response_extra_matching_correction_prompt_does_not_restart_flight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt_marker = "one correction attempt"
    response_marker = "auth-response-only-policy-marker"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    waiter_joined = threading.Event()

    class BlockingCorrectionTransport:
        def __init__(self) -> None:
            self.request_count = 0
            self.lock = threading.Lock()

        def post(
            self,
            _endpoint: str,
            payload: bytes,
            _headers: dict[str, str],
            _timeout: int,
        ) -> str:
            with self.lock:
                self.request_count += 1
                count = self.request_count
            request = json.loads(payload)
            if count == 1:
                provider_entered.set()
                assert release_provider.wait(5)
            correction = prompt_marker in str(request["instructions"])
            contract = (
                _valid_auth()
                if correction
                else {**_valid_auth(), "assumptions": "schema-invalid"}
            )
            envelope: dict[str, object] = {
                "id": f"auth-outbound-extra-{count}",
                "status": "completed",
                "model": request["model"],
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(contract),
                            }
                        ],
                    }
                ],
            }
            if correction:
                envelope["metadata"] = response_marker
            return json.dumps(envelope)

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_auth_inflight

    def observed_join(key: str):
        state, owner = original_join(key)
        if not owner:
            waiter_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_auth_inflight", observed_join)
    transport = BlockingCorrectionTransport()
    strict_owner = _client(
        tmp_path,
        transport,
        extra_secret_patterns=(
            ("correction-prompt-only", re.compile(prompt_marker)),
            ("response-only", re.compile(response_marker)),
        ),
    )
    lax_waiter = _client(tmp_path, transport)
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_auth("entry:1", (_fact(),))
        except BaseException as exc:
            results[name] = exc

    owner_thread = threading.Thread(target=classify, args=("strict", strict_owner))
    waiter_thread = threading.Thread(target=classify, args=("lax", lax_waiter))
    owner_thread.start()
    assert provider_entered.wait(5)
    waiter_thread.start()
    assert waiter_joined.wait(5)
    release_provider.set()
    for worker in (owner_thread, waiter_thread):
        worker.join(5)
        assert not worker.is_alive()

    assert transport.request_count == 2
    assert isinstance(results["strict"], AnalyzerError)
    assert results["strict"].code == "LLM_RESPONSE_SENSITIVE_CONTENT"  # type: ignore[union-attr]
    assert not isinstance(results["lax"], BaseException)
    assert strict_owner.last_audit() is None
    lax_audit = lax_waiter.last_audit()
    assert lax_audit is not None and lax_audit.cache_hit is True
    assert response_marker in lax_audit.raw_response
    assert len(list((tmp_path / "cache").glob("auth-*.json"))) == 1


def test_auth_universal_sensitive_terminal_is_shared_without_waiter_refetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "universal-auth-terminal@example.test"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    waiter_joined = threading.Event()

    class BlockingSensitiveTransport:
        def __init__(self) -> None:
            self.request_count = 0
            self.lock = threading.Lock()

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            with self.lock:
                self.request_count += 1
                count = self.request_count
            if count == 1:
                provider_entered.set()
                assert release_provider.wait(5)
            request = json.loads(payload)
            return json.dumps({
                "id": f"auth-universal-sensitive-{count}",
                "status": "completed",
                "model": request["model"],
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps({**_valid_auth(), "assumptions": [marker]})}]}],
            })

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_auth_inflight

    def observed_join(key: str):
        state, owner = original_join(key)
        if not owner:
            waiter_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_auth_inflight", observed_join)
    transport = BlockingSensitiveTransport()
    owner = _client(tmp_path, transport)
    waiter = _client(tmp_path, transport)
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_auth("entry:1", (_fact(),))
        except BaseException as exc:
            results[name] = exc

    owner_thread = threading.Thread(target=classify, args=("owner", owner))
    waiter_thread = threading.Thread(target=classify, args=("waiter", waiter))
    owner_thread.start()
    assert provider_entered.wait(5)
    waiter_thread.start()
    assert waiter_joined.wait(5)
    release_provider.set()
    for worker in (owner_thread, waiter_thread):
        worker.join(5)
        assert not worker.is_alive()

    assert transport.request_count == 2
    for name, client in (("owner", owner), ("waiter", waiter)):
        assert isinstance(results[name], AnalyzerError)
        assert results[name].code == "LLM_RESPONSE_SENSITIVE_CONTENT"  # type: ignore[union-attr]
        _assert_traceback_clean(results[name], marker)  # type: ignore[arg-type]
        assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("auth-*.json")) == []


def test_auth_phone_like_envelope_id_is_audited_and_cached_privately(
    tmp_path: Path,
) -> None:
    request_id = "415-555-2671"

    class PhoneLikeIdTransport(ScriptedDeepSeekTransport):
        def post(
            self,
            endpoint: str,
            payload: bytes,
            headers: dict[str, str],
            timeout: int,
        ) -> str:
            envelope = json.loads(super().post(endpoint, payload, headers, timeout))
            envelope["id"] = request_id
            return json.dumps(envelope, separators=(",", ":"))

    transport = PhoneLikeIdTransport(auth=lambda _request: _valid_auth())
    client = _client(tmp_path, transport)

    contract = client.classify_auth("entry:1", (_fact(),))

    assert contract.auth_context == "unauthenticated"
    assert transport.request_count == 1
    audit = client.last_audit()
    assert audit is not None and audit.cache_hit is False
    assert audit.request_id == request_id
    assert request_id in audit.raw_response
    cache_file = next((tmp_path / "cache").glob("auth-*.json"))
    assert cache_file.stat().st_mode & 0o777 == 0o600
    serialized = cache_file.read_text(encoding="utf-8")
    assert request_id in serialized
    assert "test-api-key" not in serialized


def _duplicate_auth_contract(marker: str) -> str:
    return (
        '{"auth_context":"unauthenticated","evidence_ids":["security:1"],'
        '"assumptions":[],"assumptions":["'
        + marker
        + '"],"confidence":"high"}'
    )


def test_auth_duplicate_key_response_gets_one_safe_correction(tmp_path: Path) -> None:
    marker = "first-auth-duplicate-key-marker"

    class DuplicateThenValidTransport:
        def __init__(self) -> None:
            self.request_count = 0
            self.requests: list[dict[str, object]] = []

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            self.requests.append(request)
            content = (
                _duplicate_auth_contract(marker)
                if self.request_count == 1
                else json.dumps(_valid_auth())
            )
            return json.dumps({
                "id": f"auth-duplicate-{self.request_count}",
                "status": "completed",
                "model": request["model"],
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": content}]}],
            })

    transport = DuplicateThenValidTransport()
    client = _client(tmp_path, transport)

    contract = client.classify_auth("entry:1", (_fact(),))

    assert contract.auth_context == "unauthenticated"
    assert transport.request_count == 2
    assert marker not in str(transport.requests[1])
    assert "one correction attempt" in str(transport.requests[1]["instructions"])
    audit = client.last_audit()
    assert audit is not None and marker not in audit.raw_response
    cache_file = next((tmp_path / "cache").glob("auth-*.json"))
    assert marker not in cache_file.read_text(encoding="utf-8")


def test_auth_initial_correction_and_cache_replay_use_same_deterministic_aliases(
    tmp_path: Path,
) -> None:
    original_entry_id = "entry:private-original"
    original_security_path = "src/private/SecurityFixture.java"
    original_config_path = "config/private/application.yml"
    fact = EntrySecurityFact(
        original_entry_id,
        "annotation",
        original_security_path,
        17,
        "unauthenticated_annotation",
        "complete",
    )
    config = ModeledConfigurationFact(
        "feature.enabled",
        True,
        original_config_path,
        9,
        "default",
        "extracted_default",
        True,
        "known",
    )
    attempts = 0

    def auth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return (
            {**_valid_auth(), "assumptions": "force-safe-correction"}
            if attempts == 1
            else _valid_auth()
        )

    transport = ScriptedDeepSeekTransport(auth=auth)
    fresh = _client(tmp_path, transport)
    contract = fresh.classify_auth(original_entry_id, (fact,), (config.to_dict(),))

    assert transport.request_count == 2
    initial_user = _prompt_object(transport.requests[0])
    correction_user = _prompt_object(transport.requests[1])
    assert initial_user == correction_user
    serialized_requests = json.dumps(transport.requests, sort_keys=True)
    for private_value in (
        original_entry_id,
        fact.fact_id,
        config.config_id,
        original_security_path,
        original_config_path,
    ):
        assert private_value not in serialized_requests
    assert initial_user["entry_id"] == "entry:1"
    security = initial_user["security_facts"]
    assert isinstance(security, list) and len(security) == 1
    assert security[0] == {
        "fact_id": "security:1",
        "kind": "annotation",
        "location": "source/security/1",
        "line": 17,
        "value": "unauthenticated_annotation",
        "coverage": "complete",
    }
    configuration = initial_user["configuration_facts"]
    assert isinstance(configuration, list) and len(configuration) == 1
    assert configuration[0] == {
        "config_id": "config:1",
        "key": "feature.enabled",
        "value": True,
        "source_file": "source/config/1",
        "source_line": 9,
        "profile": "default",
        "provenance": "extracted_default",
        "default_effective": True,
        "status": "known",
    }
    fresh_audit = fresh.last_audit()
    assert fresh_audit is not None and fresh_audit.cache_hit is False

    replay = _client(tmp_path, transport)
    assert replay.classify_auth(original_entry_id, (fact,), (config.to_dict(),)) == contract
    replay_audit = replay.last_audit()
    assert replay_audit is not None and replay_audit.cache_hit is True
    assert replay_audit.normalized_prompt == fresh_audit.normalized_prompt
    assert transport.request_count == 2


def test_auth_identity_binds_original_entry_and_fact_ownership(tmp_path: Path) -> None:
    first = EntrySecurityFact(
        "entry:owner-a",
        "annotation",
        "src/SameShape.java",
        11,
        "unauthenticated_annotation",
        "complete",
    )
    second = EntrySecurityFact(
        "entry:owner-b",
        "annotation",
        "src/SameShape.java",
        11,
        "unauthenticated_annotation",
        "complete",
    )
    transport = ScriptedDeepSeekTransport(auth=lambda _request: _valid_auth())
    client = _client(tmp_path, transport)

    first_contract = client.classify_auth(first.entry_id, (first,))
    second_contract = client.classify_auth(second.entry_id, (second,))

    assert transport.request_count == 2
    assert first_contract.evidence_ids == (first.fact_id,)
    assert second_contract.evidence_ids == (second.fact_id,)
    assert first.fact_id != second.fact_id
    cache_files = list((tmp_path / "cache").glob("auth-*.json"))
    assert len(cache_files) == 2
    for cache_file in cache_files:
        serialized = cache_file.read_text(encoding="utf-8")
        assert first.entry_id not in serialized
        assert second.entry_id not in serialized
        assert "ownership_binding_hash" in serialized

    replay = _client(tmp_path, transport)
    assert replay.classify_auth(first.entry_id, (first,)).evidence_ids == (first.fact_id,)
    assert replay.classify_auth(second.entry_id, (second,)).evidence_ids == (second.fact_id,)
    assert transport.request_count == 2


def test_auth_identity_binds_original_configuration_ownership(tmp_path: Path) -> None:
    first = ModeledConfigurationFact(
        "feature.enabled",
        True,
        "config/owner-a.yml",
        3,
        "default",
        "extracted_default",
        True,
        "known",
    )
    second = ModeledConfigurationFact(
        "feature.enabled",
        True,
        "config/owner-b.yml",
        3,
        "default",
        "extracted_default",
        True,
        "known",
    )
    transport = ScriptedDeepSeekTransport(auth=lambda _request: _valid_auth())
    client = _client(tmp_path, transport)

    client.classify_auth("entry:1", (_fact(),), (first.to_dict(),))
    client.classify_auth("entry:1", (_fact(),), (second.to_dict(),))

    assert transport.request_count == 2
    assert _prompt_object(transport.requests[0]) == _prompt_object(transport.requests[1])
    assert len(list((tmp_path / "cache").glob("auth-*.json"))) == 2


def test_auth_disk_replay_rejects_foreign_owned_evidence_id(tmp_path: Path) -> None:
    fact = _fact()
    transport = ScriptedDeepSeekTransport(auth=lambda _request: _valid_auth())
    fresh = _client(tmp_path, transport)
    fresh.classify_auth(fact.entry_id, (fact,))

    foreign = EntrySecurityFact(
        "entry:foreign-owner",
        "annotation",
        "Foreign.java",
        9,
        "unauthenticated_annotation",
        "complete",
    )
    path = next((tmp_path / "cache").glob("auth-*.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["contract"]["evidence_ids"] = [foreign.fact_id]
    unsigned = {
        name: value for name, value in record.items() if name != "entry_hmac"
    }
    unsigned["entry_hash"] = sha256_canonical_json(
        {name: value for name, value in unsigned.items() if name != "entry_hash"}
    )
    record.update(unsigned)
    record["entry_hmac"] = hmac.new(
        b"test-api-key",
        b"auth-contract-cache-v5\0" + canonical_json(unsigned),
        hashlib.sha256,
    ).hexdigest()
    path.write_bytes(canonical_json(record))

    replay = _client(tmp_path, transport)
    with pytest.raises(AnalyzerError) as raised:
        replay.classify_auth(fact.entry_id, (fact,))

    assert raised.value.code == "LLM_CACHE_CONFLICT"
    assert transport.request_count == 1
    assert replay.last_audit() is None


def test_auth_unknown_evidence_alias_gets_one_safe_correction(tmp_path: Path) -> None:
    attempts = 0

    def auth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return (
            {**_valid_auth(), "evidence_ids": ["security:999"]}
            if attempts == 1
            else _valid_auth()
        )

    transport = ScriptedDeepSeekTransport(auth=auth)
    client = _client(tmp_path, transport)

    contract = client.classify_auth("entry:1", (_fact(),))

    assert transport.request_count == 2
    assert contract.evidence_ids == (_fact().fact_id,)
    assert "security:999" not in next((tmp_path / "cache").glob("auth-*.json")).read_text(encoding="utf-8")


def test_second_auth_unknown_evidence_alias_is_terminal_and_clean(tmp_path: Path) -> None:
    marker = "security:999"
    transport = ScriptedDeepSeekTransport(
        auth=lambda _request: {**_valid_auth(), "evidence_ids": [marker]}
    )
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 2
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("auth-*.json")) == []


def test_auth_capacity_is_reserved_before_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dosweb.llm import cache as cache_module

    transport = ScriptedDeepSeekTransport(auth=lambda _request: _valid_auth())
    client = _client(tmp_path, transport)
    monkeypatch.setattr(cache_module, "_MAX_CACHE_ENTRIES", 0)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_CACHE_CAPACITY_EXHAUSTED"
    assert transport.request_count == 0
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("auth-*.json")) == []


@pytest.mark.parametrize("failure_mode", ["os_link", "false_return"])
def test_auth_publication_failure_precedes_custom_policy_and_clears_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    from dosweb.llm import cache as cache_module

    marker = "auth-publication-policy-marker"
    transport = ScriptedDeepSeekTransport(
        auth=lambda _request: {**_valid_auth(), "assumptions": [marker]}
    )
    client = _client(
        tmp_path,
        transport,
        extra_secret_patterns=(("custom", re.compile(marker)),),
    )
    if failure_mode == "os_link":
        monkeypatch.setattr(
            cache_module.os,
            "link",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("publish failed")),
        )
    else:
        monkeypatch.setattr(
            client._cache,  # noqa: SLF001
            "put_auth_record",
            lambda *_args, **_kwargs: False,
        )

    with pytest.raises(AnalyzerError) as raised:
        client.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_CACHE_WRITE_FAILED"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 1
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("auth-*.json")) == []


def test_second_auth_duplicate_key_response_is_terminal_and_clean(tmp_path: Path) -> None:
    marker = "terminal-auth-duplicate-key-marker"

    class AlwaysDuplicateTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            return json.dumps({
                "id": f"auth-terminal-duplicate-{self.request_count}",
                "status": "completed",
                "model": request["model"],
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": _duplicate_auth_contract(marker)}]}],
            })

    transport = AlwaysDuplicateTransport()
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_auth("entry:1", (_fact(),))

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    _assert_traceback_clean(raised.value, marker)
    assert transport.request_count == 2
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("auth-*.json")) == []


def test_auth_v4_cache_is_cold_and_auth_identities_are_rotated(tmp_path: Path) -> None:
    from dosweb import production

    assert AUTH_PROMPT_VERSION == "auth-contract-v5"
    assert AUTH_RESPONSE_SCHEMA_VERSION == "auth-contract-schema-v3"
    assert production._IMPLEMENTATION_VERSIONS["growth"] == (  # noqa: SLF001
        "production-v2.8-open-world-maturation-growth-v32"
    )

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(mode=0o700)
    key = "a" * 64
    identity = {"kind": "auth", "prompt_version": "auth-contract-v4"}
    entry = {
        "cache_format": "auth-contract-cache-v4",
        "cache_key": key,
        "identity": identity,
        "contract": _valid_auth(),
        "raw_response": "{}",
    }
    entry["entry_hash"] = sha256_canonical_json(entry)
    entry["entry_hmac"] = hmac.new(
        b"test-api-key",
        b"auth-contract-cache-v4\\0" + canonical_json(entry),
        hashlib.sha256,
    ).hexdigest()
    path = cache_dir / f"auth-{key}.json"
    path.write_bytes(canonical_json(entry))
    path.chmod(0o600)

    assert ContractCache(cache_dir, "test-api-key").get_auth_record(key, identity) is None


def test_real_auth_v4_identity_is_cold_without_blocking_v5_publication(
    tmp_path: Path,
) -> None:
    transport = ScriptedDeepSeekTransport(auth=lambda _request: _valid_auth())
    seed_root = tmp_path / "seed"
    seed_root.mkdir()
    _client(seed_root, transport).classify_auth("entry:1", (_fact(),))
    seed_record = json.loads(
        next((seed_root / "cache").glob("auth-*.json")).read_text(encoding="utf-8")
    )

    old_identity = dict(seed_record["identity"])
    old_identity["auth_cache_format"] = "auth-contract-cache-v4"
    old_identity["prompt_version"] = "auth-contract-v4"
    old_identity["text_format"] = "json_object"
    old_identity.pop("response_format_schema_hash", None)
    old_key = hashlib.sha256(
        json.dumps(
            old_identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    old_entry: dict[str, object] = {
        "cache_format": "auth-contract-cache-v4",
        "cache_key": old_key,
        "identity": old_identity,
        "contract": seed_record["contract"],
        "raw_response": seed_record["raw_response"],
        "accepted_prompt_variant": seed_record["accepted_prompt_variant"],
        "actual_model": seed_record["actual_model"],
    }
    old_entry["entry_hash"] = sha256_canonical_json(old_entry)
    old_entry["entry_hmac"] = hmac.new(
        b"test-api-key",
        b"auth-contract-cache-v4\\0" + canonical_json(old_entry),
        hashlib.sha256,
    ).hexdigest()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(mode=0o700)
    old_path = cache_dir / f"auth-{old_key}.json"
    old_path.write_bytes(canonical_json(old_entry))
    old_path.chmod(0o600)
    old_bytes = old_path.read_bytes()

    contract = _client(tmp_path, transport).classify_auth("entry:1", (_fact(),))

    assert contract.auth_context == "unauthenticated"
    assert transport.request_count == 2
    assert old_path.read_bytes() == old_bytes
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in cache_dir.glob("auth-*.json")
    ]
    assert len(records) == 2
    current = next(record for record in records if record["cache_format"] == "auth-contract-cache-v5")
    assert current["cache_key"] != old_key
    assert current["identity"]["auth_cache_format"] == "auth-contract-cache-v5"
