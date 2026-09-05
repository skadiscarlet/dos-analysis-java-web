from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from dosweb.growth.contracts import (
    bind_provider_growth_contract,
    parse_growth_contract_json,
    validate_provider_growth_contract,
)
from dosweb.growth.models import (
    BoundedSlice,
    BoundedSlicePayload,
    CfgSummary,
    ProviderGrowthContract,
    RegistrationFact,
    SourceExcerpt,
    StaticFact,
)
from dosweb.llm.schemas import GROWTH_CONTRACT_RESPONSE_SCHEMA, RESPONSE_SCHEMA_VERSION
from dosweb.artifacts.identifiers import canonical_json, sha256_canonical_json
from dosweb.config import LlmConfig
from dosweb.errors import AnalyzerError
from dosweb.llm.cache import ContractCache, GrowthCacheSnapshot, cache_identity
from dosweb.llm.deepseek import DeepSeekClient, ProviderReply, _InFlightState
from tests.support.mock_deepseek import ScriptedDeepSeekTransport, StaticPublicVerifier


def _contains_rejected_marker(
    value: object,
    marker: str,
    seen: set[int] | None = None,
) -> bool:
    """Inspect only rejected-body-bearing values retained by traceback frames."""
    if isinstance(value, str):
        return marker in value
    if isinstance(value, bytes):
        return marker.encode("utf-8") in value
    seen = set() if seen is None else seen
    if id(value) in seen:
        return False
    seen.add(id(value))
    if isinstance(value, ProviderReply):
        return _contains_rejected_marker(value.body, marker, seen) or _contains_rejected_marker(
            value.headers,
            marker,
            seen,
        )
    if isinstance(value, GrowthCacheSnapshot):
        return _contains_rejected_marker(
            value.raw_response,
            marker,
            seen,
        ) or _contains_rejected_marker(value.request_id, marker, seen)
    if isinstance(value, _InFlightState):
        return _contains_rejected_marker(value.snapshot, marker, seen)
    if isinstance(value, dict):
        return any(
            _contains_rejected_marker(item, marker, seen)
            for pair in value.items()
            for item in pair
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_rejected_marker(item, marker, seen) for item in value)
    return False


def _assert_traceback_locals_do_not_retain_marker(
    error: BaseException,
    marker: str,
) -> None:
    current: BaseException | None = error
    seen_errors: set[int] = set()
    while current is not None and id(current) not in seen_errors:
        seen_errors.add(id(current))
        traceback = current.__traceback__
        while (
            traceback is not None
            and traceback.tb_frame.f_globals.get("__name__") == __name__
            and traceback.tb_frame.f_code.co_name.startswith("test_")
        ):
            traceback = traceback.tb_next
        while traceback is not None:
            for name, value in tuple(traceback.tb_frame.f_locals.items()):
                assert not _contains_rejected_marker(value, marker), (
                    f"rejected provider body marker retained in traceback local {name!r} "
                    f"of {traceback.tb_frame.f_code.co_name}"
                )
            traceback = traceback.tb_next
        current = current.__cause__ or current.__context__


def _provider_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "is_resource_growth": "yes",
        "attacker_evidence_ids": ["fact:flow"],
        "resource_effect": "adds_entries",
        "attacker_variable": "request key",
        "attacker_value_space": "unlimited",
        "growth_unit": "one retained entry",
        "growth_function": "distinct requests add retained entries",
        "amplification_class": "high_cardinality_retention",
        "requests_to_pressure": "many",
        "concurrency_model": "repeatable requests",
        "retention_window": "process",
        "failure_mechanism": "heap_exhaustion",
        "failure_signal": "retained entries exhaust heap",
        "required_static_evidence": [
            "fact:sink",
            "fact:value-space",
            "fact:retention",
            "fact:amplification",
        ],
        "contract_status": "dos_relevant",
        "rejection_reason": "none",
        "confidence": "high",
    }
    payload.update(changes)
    return payload


def _slice() -> BoundedSlice:
    content = "registry.put(key, value);\n"
    excerpt = SourceExcerpt(
        "excerpt:1",
        "src/Fixture.java",
        1,
        1,
        content,
        "a" * 64,
        hashlib.sha256(content.encode()).hexdigest(),
    )
    facts = (
        StaticFact("fact:flow", "flow", "excerpt:1", "flows_to", None, "request_parameter"),
        StaticFact("fact:target", "attacker_target", "excerpt:1", "source", "fact:flow", "key"),
        StaticFact("fact:sink", "container_write", "excerpt:1", "sink", "fact:flow"),
        StaticFact("fact:value-space", "value_space", "excerpt:1", "flows_to", "fact:flow", "unlimited"),
        StaticFact("fact:retention", "retention", "excerpt:1", "sink", None, "process"),
        StaticFact("fact:amplification", "amplification", "excerpt:1", "sink", None, "high_cardinality_retention"),
    )
    payload = BoundedSlicePayload(
        "entry:1",
        "growth:1",
        (excerpt,),
        facts,
        CfgSummary(("path:1",), ("in_handler",), tuple(f.fact_id for f in facts)),
        (RegistrationFact("spring_mvc", "excerpt:1"),),
        (),
    )
    return BoundedSlice("slice:1", payload)


def test_provider_schema_v5_excludes_local_candidate_shape_and_demand_role() -> None:
    assert RESPONSE_SCHEMA_VERSION == "growth-contract-schema-v5"
    assert "growth_kind" not in GROWTH_CONTRACT_RESPONSE_SCHEMA
    assert "resource_dimension" not in GROWTH_CONTRACT_RESPONSE_SCHEMA
    assert "attacker_influence" not in GROWTH_CONTRACT_RESPONSE_SCHEMA
    assert set(GROWTH_CONTRACT_RESPONSE_SCHEMA) == set(_provider_payload())

    parsed = validate_provider_growth_contract(_provider_payload())
    assert isinstance(parsed, ProviderGrowthContract)
    with pytest.raises(Exception):
        validate_provider_growth_contract(
            {**_provider_payload(), "growth_kind": "container_growth"}
        )


@pytest.mark.parametrize("growth_value", ["no", "unknown"])
def test_provider_and_bound_models_reject_dos_relevant_without_positive_growth(
    growth_value: str,
) -> None:
    provider = validate_provider_growth_contract(_provider_payload())
    bound = bind_provider_growth_contract(provider, _slice())

    with pytest.raises(AnalyzerError) as provider_error:
        replace(provider, is_resource_growth=growth_value)
    assert provider_error.value.code == "LLM_RESPONSE_SCHEMA_INVALID"

    with pytest.raises(AnalyzerError) as bound_error:
        replace(bound, is_resource_growth=growth_value)
    assert bound_error.value.code == "LLM_RESPONSE_SCHEMA_INVALID"

    with pytest.raises(AnalyzerError) as parsed_error:
        parse_growth_contract_json(
            json.dumps(
                _provider_payload(is_resource_growth=growth_value),
                separators=(",", ":"),
            )
        )
    assert parsed_error.value.code == "LLM_RESPONSE_SCHEMA_INVALID"


def test_local_typed_schema_rejects_unknown_status_cross_field_inconsistency() -> None:
    with pytest.raises(AnalyzerError) as raised:
        validate_provider_growth_contract(
            _provider_payload(
                contract_status="unknown",
                is_resource_growth="yes",
                rejection_reason="none",
            )
        )

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"


def test_growth_prompt_exposes_only_binder_eligible_attacker_aliases() -> None:
    from dosweb.llm.prompts import (
        build_growth_correction_payload,
        build_provider_payload,
    )
    from dosweb.llm.schemas import PROMPT_VERSION

    initial = build_provider_payload(_slice())
    user = json.loads(initial.messages[1]["content"])

    assert PROMPT_VERSION == "growth-contract-v9"
    assert user["attacker_evidence_options"] == [
        {"evidence_id": "fact:1", "attacker_target": "key"}
    ]
    correction = build_growth_correction_payload(_slice())
    instructions = correction.messages[0]["content"]
    assert "Use only an evidence_id from attacker_evidence_options" in instructions
    assert "confidence is mandatory" in instructions


def test_growth_prompt_filters_exact_binder_matrix_and_zero_option() -> None:
    from dataclasses import replace

    from dosweb.llm.prompts import build_provider_payload

    base = _slice()
    facts = (
        StaticFact("fact:eligible", "flow", "excerpt:1", "flows_to", None, "request_parameter"),
        StaticFact("fact:eligible-target", "attacker_target", "excerpt:1", "source", "fact:eligible", "key"),
        StaticFact("fact:wrong-relation", "flow", "excerpt:1", "guards", None, "request_parameter"),
        StaticFact("fact:wrong-target", "attacker_target", "excerpt:1", "source", "fact:wrong-relation", "key"),
        StaticFact("fact:missing-target", "driver_origin", "excerpt:1", "source", None, "request_parameter"),
        StaticFact("fact:multiple-targets", "flow", "excerpt:1", "source", None, "request_parameter"),
        StaticFact("fact:multiple-key", "attacker_target", "excerpt:1", "source", "fact:multiple-targets", "key"),
        StaticFact("fact:multiple-value", "attacker_target", "excerpt:1", "source", "fact:multiple-targets", "value"),
        StaticFact("fact:sink", "container_write", "excerpt:1", "sink", "fact:eligible"),
    )
    matrix_payload = replace(
        base.payload,
        static_facts=facts,
        cfg_summary=CfgSummary(
            ("path:1",), ("in_handler",), tuple(fact.fact_id for fact in facts)
        ),
    )
    matrix = BoundedSlice("slice:matrix", matrix_payload)
    matrix_user = json.loads(build_provider_payload(matrix).messages[1]["content"])

    assert matrix_user["attacker_evidence_options"] == [
        {"evidence_id": "fact:1", "attacker_target": "key"}
    ]

    zero_facts = tuple(
        replace(fact, value_ref="fact:wrong-relation")
        if fact.fact_id == "fact:sink"
        else fact
        for fact in facts
        if fact.fact_id not in {"fact:eligible", "fact:eligible-target"}
    )
    zero_payload = replace(
        base.payload,
        static_facts=zero_facts,
        cfg_summary=CfgSummary(
            ("path:1",), ("in_handler",), tuple(fact.fact_id for fact in zero_facts)
        ),
    )
    zero = BoundedSlice("slice:zero-options", zero_payload)
    zero_provider = build_provider_payload(zero)
    zero_user = json.loads(zero_provider.messages[1]["content"])

    assert zero_user["attacker_evidence_options"] == []
    assert "If no option exists" in zero_provider.messages[0]["content"]
    assert "contract_status must not be dos_relevant" in zero_provider.messages[0]["content"]


def test_binder_invalid_initial_response_can_use_safe_alias_options_on_correction(
    tmp_path: Path,
) -> None:
    attempts = 0

    def prompt_object(request: dict[str, object]) -> dict[str, object]:
        inputs = request["input"]
        assert isinstance(inputs, list) and len(inputs) == 1
        content = inputs[0]["content"]
        assert isinstance(content, list) and len(content) == 1
        parsed = json.loads(content[0]["text"])
        assert isinstance(parsed, dict)
        return parsed

    def growth(request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _provider_payload(
                attacker_evidence_ids=["fact:3"],
                required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
            )
        options = prompt_object(request).get("attacker_evidence_options", [])
        if not isinstance(options, list) or not options:
            return _provider_payload(
                is_resource_growth="unknown",
                attacker_evidence_ids=[],
                resource_effect="unknown",
                attacker_variable="unknown",
                attacker_value_space="unknown",
                growth_unit="unknown",
                growth_function="unknown",
                amplification_class="unknown",
                requests_to_pressure="unknown",
                concurrency_model="unknown",
                retention_window="unknown",
                failure_mechanism="unknown",
                failure_signal="unknown",
                required_static_evidence=[],
                contract_status="unknown",
                rejection_reason="unknown",
                confidence="low",
            )
        option = options[0]
        assert isinstance(option, dict)
        return _provider_payload(
            attacker_evidence_ids=[option["evidence_id"]],
            required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
        )

    transport = ScriptedDeepSeekTransport(growth=growth)
    contract = _client(tmp_path, transport).classify_growth(_slice())

    assert contract.contract_status == "dos_relevant"
    assert contract.attacker_influence[0].evidence_id == "fact:flow"
    assert transport.request_count == 2


def test_binder_invalid_then_missing_confidence_fails_closed_without_local_fill(
    tmp_path: Path,
) -> None:
    attempts = 0

    def growth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _provider_payload(
                attacker_evidence_ids=["fact:3"],
                required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
            )
        missing_confidence = _provider_payload(
            attacker_evidence_ids=["fact:1"],
            required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
        )
        missing_confidence.pop("confidence")
        assert len(missing_confidence) == 16
        return missing_confidence

    transport = ScriptedDeepSeekTransport(growth=growth)
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert transport.request_count == 2
    assert list((tmp_path / "cache").glob("*.json")) == []
    assert client.last_audit() is None


def test_local_slice_binds_kind_dimension_and_attacker_target() -> None:
    provider = validate_provider_growth_contract(_provider_payload())
    contract = bind_provider_growth_contract(provider, _slice())

    assert contract.growth_kind == "container_growth"
    assert contract.resource_dimension == "entries"
    assert contract.attacker_influence[0].target == "key"
    assert contract.attacker_influence[0].evidence_id == "fact:flow"


def test_strict_growth_invariant_rotates_growth_cache_authentication_domain(tmp_path) -> None:
    from dosweb.llm import cache as cache_module

    cache = cache_module.ContractCache(tmp_path / "cache", "cache-key")
    unsigned = {"cache_format": "growth-contract-cache-v14", "contract": {}}

    assert cache_module._CACHE_FORMAT == "growth-contract-cache-v14"
    assert cache._entry_hmac(unsigned) == hmac.new(
        b"cache-key",
        b"growth-contract-cache-entry-v14\0" + canonical_json(unsigned),
        hashlib.sha256,
    ).hexdigest()


def test_growth_cache_identity_rotates_with_authenticated_cache_format(
    tmp_path, monkeypatch
) -> None:
    from dosweb.llm import cache as cache_module

    config = LlmConfig(
        model="grok-4.6",
        base_url="http://127.0.0.1:1/",
        api_key="test-api-key",
        timeout_seconds=3,
        max_retries=1,
        temperature=0,
        cache_dir=tmp_path / "cache",
        allow_remote_llm=True,
        source_checkout=tmp_path,
    )
    current_key, current_identity = cache_module.cache_identity(config, _slice())

    assert current_identity["cache_format"] == "growth-contract-cache-v14"
    monkeypatch.setattr(cache_module, "_CACHE_FORMAT", "growth-contract-cache-v13")
    previous_key, previous_identity = cache_module.cache_identity(config, _slice())
    assert previous_identity["cache_format"] == "growth-contract-cache-v13"
    assert previous_key != current_key


@pytest.mark.parametrize(
    "malformation",
    (
        "cache_format",
        "cache_key",
        "response_schema_version",
        "identity",
        "identity_hash",
        "request_audit",
        "audit_provider_type",
        "audit_provider_value",
        "audit_protocol_type",
        "audit_protocol_value",
        "audit_hash",
        "accepted_prompt_variant",
        "raw_response_hash",
        "contract_hash",
        "typed_contract",
        "entry_hash",
        "entry_hmac",
        "extra_field",
        "missing_field",
    ),
)
def test_signed_malformed_growth_cache_entry_is_rejected_by_both_readers(
    tmp_path: Path,
    malformation: str,
) -> None:
    config = LlmConfig(
        model="grok-4.6",
        base_url="http://127.0.0.1:1/",
        api_key="test-api-key",
        timeout_seconds=3,
        max_retries=1,
        temperature=0,
        cache_dir=tmp_path / "cache",
        allow_remote_llm=True,
        source_checkout=tmp_path,
    )
    transport = ScriptedDeepSeekTransport(
        growth=lambda _request: _provider_payload(
            attacker_evidence_ids=["fact:1"],
            required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
        )
    )
    DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,
        sleep=lambda _delay: None,
    ).classify_growth(_slice())
    key, identity = cache_identity(config, _slice())
    cache = ContractCache(config.cache_dir, config.api_key)
    cache_file = config.cache_dir / f"{key}.json"
    entry = json.loads(cache_file.read_text(encoding="utf-8"))

    if malformation == "cache_format":
        entry["cache_format"] = "growth-contract-cache-v999"
    elif malformation == "cache_key":
        entry["cache_key"] = "0" * 64 if key != "0" * 64 else "1" * 64
    elif malformation == "response_schema_version":
        entry["response_schema_version"] = "growth-contract-schema-v999"
    elif malformation == "identity":
        entry["identity"] = {**entry["identity"], "model": "wrong-model"}
        entry["identity_hash"] = sha256_canonical_json(entry["identity"])
    elif malformation == "identity_hash":
        entry["identity_hash"] = "0" * 64
    elif malformation == "request_audit":
        entry["request_audit"] = {**entry["request_audit"], "method": "GET"}
        entry["audit_hash"] = sha256_canonical_json(entry["request_audit"])
    elif malformation == "audit_provider_type":
        entry["request_audit"] = {**entry["request_audit"], "provider": ["wrong-type"]}
        entry["audit_hash"] = sha256_canonical_json(entry["request_audit"])
    elif malformation == "audit_provider_value":
        entry["request_audit"] = {**entry["request_audit"], "provider": "wrong-provider"}
        entry["audit_hash"] = sha256_canonical_json(entry["request_audit"])
    elif malformation == "audit_protocol_type":
        entry["request_audit"] = {**entry["request_audit"], "protocol": ["wrong-type"]}
        entry["audit_hash"] = sha256_canonical_json(entry["request_audit"])
    elif malformation == "audit_protocol_value":
        entry["request_audit"] = {**entry["request_audit"], "protocol": "wrong-protocol"}
        entry["audit_hash"] = sha256_canonical_json(entry["request_audit"])
    elif malformation == "audit_hash":
        entry["audit_hash"] = "0" * 64
    elif malformation == "accepted_prompt_variant":
        entry["accepted_prompt_variant"] = "illegal"
    elif malformation == "raw_response_hash":
        entry["raw_response_hash"] = "0" * 64
    elif malformation == "contract_hash":
        entry["contract_hash"] = "0" * 64
    elif malformation == "typed_contract":
        entry["contract"] = {**entry["contract"], "resource_dimension": "invalid"}
        entry["contract_hash"] = sha256_canonical_json(entry["contract"])
    elif malformation == "extra_field":
        entry["unexpected"] = "signed-but-not-allowed"
    elif malformation == "missing_field":
        entry.pop("audit_hash")
    elif malformation not in {"entry_hash", "entry_hmac"}:  # pragma: no cover - parametrization is closed
        raise AssertionError(malformation)

    stable = {
        name: value
        for name, value in entry.items()
        if name not in {"entry_hash", "entry_hmac"}
    }
    entry["entry_hash"] = sha256_canonical_json(stable)
    if malformation == "entry_hash":
        entry["entry_hash"] = "0" * 64
    unsigned = {name: value for name, value in entry.items() if name != "entry_hmac"}
    entry["entry_hmac"] = cache._entry_hmac(unsigned)  # noqa: SLF001
    if malformation == "entry_hmac":
        entry["entry_hmac"] = "0" * 64
    cache_file.write_text(json.dumps(entry), encoding="utf-8")

    assert cache.authenticated_contract(key, identity) is None
    assert cache.audit_payload(key, identity) is None


def _aliased_provider_payload(**changes: object) -> dict[str, object]:
    return _provider_payload(
        attacker_evidence_ids=["fact:1"],
        required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
        **changes,
    )


def _json_with_unicode_escaped_value(payload: dict[str, object], value: str) -> str:
    placeholder = "unicode-escape-placeholder"
    assert placeholder not in json.dumps(payload)

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


def _growth_envelope(request: dict[str, object], content: str, request_id: str) -> str:
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


def _resign_growth_cache_record(
    cache_file: Path,
    mutate: object,
) -> dict[str, object]:
    cache = ContractCache(cache_file.parent, "test-api-key")
    record = json.loads(cache_file.read_text(encoding="utf-8"))
    assert isinstance(record, dict) and callable(mutate)
    mutate(record)
    record["raw_response_hash"] = hashlib.sha256(
        record["raw_response"].encode("utf-8")
    ).hexdigest()
    record["contract_hash"] = sha256_canonical_json(record["contract"])
    stable = {
        name: value
        for name, value in record.items()
        if name not in {"entry_hash", "entry_hmac"}
    }
    record["entry_hash"] = sha256_canonical_json(stable)
    unsigned = {name: value for name, value in record.items() if name != "entry_hmac"}
    record["entry_hmac"] = cache._entry_hmac(unsigned)  # noqa: SLF001
    cache_file.write_bytes(canonical_json(record))
    return record


def test_growth_cache_replay_scans_unicode_decoded_semantic_before_audit(
    tmp_path: Path,
) -> None:
    marker = "escaped-cache-owner@example.test"
    transport = ScriptedDeepSeekTransport(
        growth=lambda _request: _aliased_provider_payload()
    )
    _client(tmp_path, transport).classify_growth(_slice())
    cache_file = next((tmp_path / "cache").glob("*.json"))

    def mutate(record: dict[str, object]) -> None:
        envelope = json.loads(record["raw_response"])
        content = envelope["output"][0]["content"][0]["text"]
        semantic = json.loads(content)
        semantic["attacker_variable"] = marker
        envelope["output"][0]["content"][0]["text"] = (
            _json_with_unicode_escaped_value(semantic, marker)
        )
        record["raw_response"] = json.dumps(envelope, separators=(",", ":"))
        record["contract"]["attacker_variable"] = marker

    _resign_growth_cache_record(cache_file, mutate)
    replay = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        replay.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    _assert_traceback_locals_do_not_retain_marker(raised.value, marker)
    assert transport.request_count == 1
    assert replay.last_audit() is None


def test_growth_cache_replay_rejects_hmac_valid_raw_typed_mismatch(
    tmp_path: Path,
) -> None:
    transport = ScriptedDeepSeekTransport(
        growth=lambda _request: _aliased_provider_payload()
    )
    _client(tmp_path, transport).classify_growth(_slice())
    cache_file = next((tmp_path / "cache").glob("*.json"))

    def mutate(record: dict[str, object]) -> None:
        record["contract"]["attacker_variable"] = "typed-only-mismatch"

    _resign_growth_cache_record(cache_file, mutate)
    replay = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        replay.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert transport.request_count == 1
    assert replay.last_audit() is None


def test_legal_large_provider_envelope_is_cached_and_replayed(tmp_path: Path) -> None:
    class LargeEnvelopeTransport:
        def __init__(self) -> None:
            self.request_count = 0
            self.response_body = ""

        def post(
            self,
            _endpoint: str,
            payload: bytes,
            _headers: dict[str, str],
            _timeout: int,
        ) -> str:
            self.request_count += 1
            request = json.loads(payload.decode("utf-8"))
            self.response_body = json.dumps(
                {
                    "id": "fixture-large-envelope",
                    "status": "completed",
                    "model": request["model"],
                    "padding": ["x" * 4000 for _ in range(20)],
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        _aliased_provider_payload(),
                                        separators=(",", ":"),
                                    ),
                                }
                            ],
                        }
                    ],
                },
                separators=(",", ":"),
            )
            assert 80_000 < len(self.response_body.encode("utf-8")) < 131_072
            return self.response_body

    transport = LargeEnvelopeTransport()
    first_client = _client(tmp_path, transport)  # type: ignore[arg-type]
    first = first_client.classify_growth(_slice())
    second_client = _client(tmp_path, transport)  # type: ignore[arg-type]
    second = second_client.classify_growth(_slice())

    assert second == first
    assert transport.request_count == 1
    assert second_client.last_audit() is not None
    assert second_client.last_audit().raw_response == transport.response_body


def test_oversized_direct_cache_response_fails_with_controlled_error(tmp_path: Path) -> None:
    transport = ScriptedDeepSeekTransport(
        growth=lambda _request: _aliased_provider_payload()
    )
    client = _client(tmp_path, transport)
    contract = client.classify_growth(_slice())
    key, identity = cache_identity(client._config, _slice())  # noqa: SLF001
    cache_file = next((tmp_path / "cache").glob("*.json"))
    audit = json.loads(cache_file.read_text(encoding="utf-8"))["request_audit"]
    marker = "oversized-cache-response-marker"
    oversized = marker + "x" * (131_073 - len(marker))

    with pytest.raises(AnalyzerError) as raised:
        ContractCache(tmp_path / "cache", "test-api-key").put(
            key,
            identity,
            contract,
            audit,
            raw_response=oversized,
        )

    assert raised.value.code == "LLM_CACHE_WRITE_FAILED"
    assert marker not in f"{raised.value.message} {raised.value.details}"


def test_disk_cache_policy_rejection_traceback_does_not_retain_raw_body(
    tmp_path: Path,
) -> None:
    marker = "disk-cache-policy-rejected-body-marker"

    class MarkerEnvelopeTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(
            self,
            _endpoint: str,
            payload: bytes,
            _headers: dict[str, str],
            _timeout: int,
        ) -> str:
            self.request_count += 1
            request = json.loads(payload.decode("utf-8"))
            return json.dumps(
                {
                    "id": "fixture-disk-policy",
                    "status": "completed",
                    "model": request["model"],
                    "metadata": marker,
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        _aliased_provider_payload(),
                                        separators=(",", ":"),
                                    ),
                                }
                            ],
                        }
                    ],
                },
                separators=(",", ":"),
            )

    transport = MarkerEnvelopeTransport()
    accepted = _client(tmp_path, transport)  # type: ignore[arg-type]
    accepted.classify_growth(_slice())
    accepted_audit = accepted.last_audit()
    assert accepted_audit is not None
    assert marker in accepted_audit.raw_response

    strict = DeepSeekClient(
        accepted._config,  # noqa: SLF001
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        extra_secret_patterns=(("disk-policy-marker", re.compile(marker)),),
        sleep=lambda _delay: None,
    )
    with pytest.raises(AnalyzerError) as raised:
        strict.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    _assert_traceback_locals_do_not_retain_marker(raised.value, marker)
    assert transport.request_count == 1
    assert strict.last_audit() is None


def test_growth_publication_failure_precedes_custom_policy_and_clears_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "growth-publication-policy-marker"

    class MarkerEnvelopeTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(
            self,
            _endpoint: str,
            payload: bytes,
            _headers: dict[str, str],
            _timeout: int,
        ) -> str:
            self.request_count += 1
            request = json.loads(payload.decode("utf-8"))
            return json.dumps(
                {
                    "id": "growth-publication-failure",
                    "status": "completed",
                    "model": request["model"],
                    "metadata": marker,
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(_aliased_provider_payload()),
                                }
                            ],
                        }
                    ],
                }
            )

    transport = MarkerEnvelopeTransport()
    config = LlmConfig(
        model="grok-4.6",
        base_url="http://127.0.0.1:1/",
        api_key="test-api-key",
        timeout_seconds=3,
        max_retries=1,
        temperature=0,
        cache_dir=tmp_path / "cache",
        allow_remote_llm=True,
        source_checkout=tmp_path,
    )
    client = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        extra_secret_patterns=(("custom", re.compile(marker)),),
        sleep=lambda _delay: None,
    )

    def fail_publication(*_args: object, **kwargs: object) -> bool:
        assert marker in str(kwargs["raw_response"])
        raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "synthetic publication failure")

    monkeypatch.setattr(client._cache, "put", fail_publication)  # noqa: SLF001

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_CACHE_WRITE_FAILED"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    _assert_traceback_locals_do_not_retain_marker(raised.value, marker)
    assert transport.request_count == 1
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("*.json")) == []


def test_thread_single_flight_applies_each_waiter_secret_policy_and_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "reviewer-concurrent-policy-marker"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    both_waiters_joined = threading.Event()
    joined_lock = threading.Lock()
    joined_count = 0

    class BlockingTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(
            self,
            _endpoint: str,
            payload: bytes,
            _headers: dict[str, str],
            _timeout: int,
        ) -> str:
            self.request_count += 1
            request = json.loads(payload.decode("utf-8"))
            provider_entered.set()
            assert release_provider.wait(5)
            return json.dumps(
                {
                    "id": "fixture-single-flight",
                    "status": "completed",
                    "model": request["model"],
                    "metadata": marker,
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(_aliased_provider_payload()),
                                }
                            ],
                        }
                    ],
                }
            )

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_inflight

    def observed_join(key: str):
        nonlocal joined_count
        state, owner = original_join(key)
        if not owner:
            with joined_lock:
                joined_count += 1
                if joined_count == 2:
                    both_waiters_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_inflight", observed_join)
    transport = BlockingTransport()
    config = LlmConfig(
        model="grok-4.6",
        base_url="http://127.0.0.1:1/",
        api_key="test-api-key",
        timeout_seconds=3,
        max_retries=1,
        temperature=0,
        cache_dir=tmp_path / "cache",
        allow_remote_llm=True,
        source_checkout=tmp_path,
    )
    owner = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        sleep=lambda _delay: None,
    )
    safe_waiter = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        extra_secret_patterns=(("nonmatching", re.compile("never-present")),),
        sleep=lambda _delay: None,
    )
    strict_waiter = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        extra_secret_patterns=(("reviewer-marker", re.compile(marker)),),
        sleep=lambda _delay: None,
    )
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_growth(_slice())
        except BaseException as exc:  # test captures exact cross-thread outcome
            results[name] = exc

    owner_thread = threading.Thread(target=classify, args=("owner", owner))
    owner_thread.start()
    assert provider_entered.wait(5)
    safe_thread = threading.Thread(target=classify, args=("safe", safe_waiter))
    strict_thread = threading.Thread(target=classify, args=("strict", strict_waiter))
    safe_thread.start()
    strict_thread.start()
    assert both_waiters_joined.wait(5)
    release_provider.set()
    for worker in (owner_thread, safe_thread, strict_thread):
        worker.join(5)
        assert not worker.is_alive()

    assert transport.request_count == 1
    assert not isinstance(results["owner"], BaseException)
    assert owner.last_audit() is not None and owner.last_audit().cache_hit is False
    assert not isinstance(results["safe"], BaseException)
    assert safe_waiter.last_audit() is not None and safe_waiter.last_audit().cache_hit is True
    assert isinstance(results["strict"], AnalyzerError)
    assert results["strict"].code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    _assert_traceback_locals_do_not_retain_marker(results["strict"], marker)
    assert safe_waiter.last_audit() is not None
    assert marker in safe_waiter.last_audit().raw_response
    assert strict_waiter.last_audit() is None


def test_thread_single_flight_strict_owner_does_not_force_lax_waiter_refetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "growth-strict-owner-policy-marker"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    waiter_joined = threading.Event()

    class BlockingTransport:
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
            provider_entered.set()
            assert release_provider.wait(5)
            request = json.loads(payload.decode("utf-8"))
            return json.dumps(
                {
                    "id": "growth-strict-owner-fixture",
                    "status": "completed",
                    "model": request["model"],
                    "metadata": marker,
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(_aliased_provider_payload()),
                                }
                            ],
                        }
                    ],
                }
            )

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_inflight

    def observed_join(key: str):
        state, owner = original_join(key)
        if not owner:
            waiter_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_inflight", observed_join)
    transport = BlockingTransport()
    config = LlmConfig(
        model="grok-4.6",
        base_url="http://127.0.0.1:1/",
        api_key="test-api-key",
        timeout_seconds=3,
        max_retries=1,
        temperature=0,
        cache_dir=tmp_path / "cache",
        allow_remote_llm=True,
        source_checkout=tmp_path,
    )
    strict_owner = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        extra_secret_patterns=(("custom", re.compile(marker)),),
        sleep=lambda _delay: None,
    )
    lax_waiter = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        sleep=lambda _delay: None,
    )
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_growth(_slice())
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
    assert results["strict"].code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    _assert_traceback_locals_do_not_retain_marker(results["strict"], marker)
    assert not isinstance(results["lax"], BaseException)
    assert strict_owner.last_audit() is None
    lax_audit = lax_waiter.last_audit()
    assert lax_audit is not None and lax_audit.cache_hit is True
    assert marker in lax_audit.raw_response
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_unicode_escaped_semantic_extra_is_rechecked_per_growth_waiter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "escaped-growth-caller-policy-marker"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    waiter_joined = threading.Event()

    class BlockingEscapedTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            provider_entered.set()
            assert release_provider.wait(5)
            contract = _aliased_provider_payload(attacker_variable=marker)
            return _growth_envelope(
                request,
                _json_with_unicode_escaped_value(contract, marker),
                "growth-escaped-waiter",
            )

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_inflight

    def observed_join(key: str):
        state, owner = original_join(key)
        if not owner:
            waiter_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_inflight", observed_join)
    transport = BlockingEscapedTransport()
    config = LlmConfig(
        model="grok-4.6",
        base_url="http://127.0.0.1:1/",
        api_key="test-api-key",
        timeout_seconds=3,
        max_retries=1,
        temperature=0,
        cache_dir=tmp_path / "cache",
        allow_remote_llm=True,
        source_checkout=tmp_path,
    )
    strict_owner = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        extra_secret_patterns=(("escaped-semantic", re.compile(marker)),),
        sleep=lambda _delay: None,
    )
    lax_waiter = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        sleep=lambda _delay: None,
    )
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_growth(_slice())
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
    assert results["strict"].code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    _assert_traceback_locals_do_not_retain_marker(results["strict"], marker)
    assert not isinstance(results["lax"], BaseException)
    assert strict_owner.last_audit() is None
    lax_audit = lax_waiter.last_audit()
    assert lax_audit is not None and lax_audit.cache_hit is True
    assert marker not in lax_audit.raw_response
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


@pytest.mark.parametrize(
    ("prompt_marker", "correction_required", "expected_requests"),
    [
        ("collection mutation alone is not DoS", False, 1),
        ("one correction attempt", True, 2),
    ],
)
def test_growth_response_extra_matching_outbound_prompt_does_not_break_shared_flight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_marker: str,
    correction_required: bool,
    expected_requests: int,
) -> None:
    response_marker = "growth-response-only-policy-marker"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    waiter_joined = threading.Event()

    class BlockingTransport:
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
            request = json.loads(payload.decode("utf-8"))
            if count == 1:
                provider_entered.set()
                assert release_provider.wait(5)
            correction = "one correction attempt" in str(request["instructions"])
            contract = (
                {"is_resource_growth": "yes"}
                if correction_required and not correction
                else _aliased_provider_payload()
            )
            envelope: dict[str, object] = {
                "id": f"growth-outbound-extra-{count}",
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
            if not correction_required or correction:
                envelope["metadata"] = response_marker
            return json.dumps(envelope)

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_inflight

    def observed_join(key: str):
        state, owner = original_join(key)
        if not owner:
            waiter_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_inflight", observed_join)
    transport = BlockingTransport()
    config = LlmConfig(
        model="grok-4.6",
        base_url="http://127.0.0.1:1/",
        api_key="test-api-key",
        timeout_seconds=3,
        max_retries=1,
        temperature=0,
        cache_dir=tmp_path / "cache",
        allow_remote_llm=True,
        source_checkout=tmp_path,
    )
    strict_owner = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        extra_secret_patterns=(
            ("prompt-only", re.compile(re.escape(prompt_marker))),
            ("response-only", re.compile(response_marker)),
        ),
        sleep=lambda _delay: None,
    )
    lax_waiter = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        sleep=lambda _delay: None,
    )
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_growth(_slice())
        except BaseException as exc:
            results[name] = exc

    owner_thread = threading.Thread(target=classify, args=("strict", strict_owner))
    waiter_thread = threading.Thread(target=classify, args=("lax", lax_waiter))
    owner_thread.start()
    assert provider_entered.wait(1), "response-only policy must not scan outbound prompt"
    waiter_thread.start()
    assert waiter_joined.wait(5)
    release_provider.set()
    for worker in (owner_thread, waiter_thread):
        worker.join(5)
        assert not worker.is_alive()

    assert transport.request_count == expected_requests
    assert isinstance(results["strict"], AnalyzerError)
    assert results["strict"].code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    assert not isinstance(results["lax"], BaseException)
    assert strict_owner.last_audit() is None
    lax_audit = lax_waiter.last_audit()
    assert lax_audit is not None and lax_audit.cache_hit is True
    assert response_marker in lax_audit.raw_response
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_thread_single_flight_shares_universal_sensitive_terminal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "universal-growth-terminal@example.test"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    waiter_joined = threading.Event()

    class BlockingSensitiveTransport:
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
            if count == 1:
                provider_entered.set()
                assert release_provider.wait(5)
            request = json.loads(payload.decode("utf-8"))
            return json.dumps(
                {
                    "id": f"growth-universal-sensitive-{count}",
                    "status": "completed",
                    "model": request["model"],
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        _aliased_provider_payload(
                                            attacker_variable=marker,
                                        )
                                    ),
                                }
                            ],
                        }
                    ],
                }
            )

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_inflight

    def observed_join(key: str):
        state, owner = original_join(key)
        if not owner:
            waiter_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_inflight", observed_join)
    transport = BlockingSensitiveTransport()
    config = LlmConfig(
        model="grok-4.6",
        base_url="http://127.0.0.1:1/",
        api_key="test-api-key",
        timeout_seconds=3,
        max_retries=1,
        temperature=0,
        cache_dir=tmp_path / "cache",
        allow_remote_llm=True,
        source_checkout=tmp_path,
    )
    owner = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        sleep=lambda _delay: None,
    )
    waiter = DeepSeekClient(
        config,
        verifier=StaticPublicVerifier(),
        transport=transport,  # type: ignore[arg-type]
        sleep=lambda _delay: None,
    )
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_growth(_slice())
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
        assert results[name].code == "LLM_RESPONSE_SENSITIVE_CONTENT"
        _assert_traceback_locals_do_not_retain_marker(results[name], marker)
        assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("*.json")) == []


def test_growth_phone_like_envelope_id_is_audited_and_cached_privately(
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

    transport = PhoneLikeIdTransport()
    client = _client(tmp_path, transport)

    contract = client.classify_growth(_slice())

    assert contract.contract_status == "dos_relevant"
    assert transport.request_count == 1
    audit = client.last_audit()
    assert audit is not None and audit.cache_hit is False
    assert audit.request_id == request_id
    assert request_id in audit.raw_response
    cache_file = next((tmp_path / "cache").glob("*.json"))
    assert cache_file.stat().st_mode & 0o777 == 0o600
    serialized = cache_file.read_text(encoding="utf-8")
    assert request_id in serialized
    assert "test-api-key" not in serialized


def test_thread_single_flight_applies_each_waiter_policy_to_provider_request_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waiter_api_key = "waiter-api-key-123456"
    request_id = f"provider-{waiter_api_key}-header"
    provider_entered = threading.Event()
    release_provider = threading.Event()
    all_waiters_joined = threading.Event()
    joined_lock = threading.Lock()
    joined_count = 0

    class HeaderOnlyTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(
            self,
            _endpoint: str,
            payload: bytes,
            _headers: dict[str, str],
            _timeout: int,
        ) -> ProviderReply:
            self.request_count += 1
            request = json.loads(payload.decode("utf-8"))
            provider_entered.set()
            assert release_provider.wait(5)
            body = json.dumps(
                {
                    "id": "safe-envelope-id",
                    "status": "completed",
                    "model": request["model"],
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(_aliased_provider_payload()),
                                }
                            ],
                        }
                    ],
                }
            )
            return ProviderReply(body, {"x-request-id": request_id})

    from dosweb.llm import deepseek as deepseek_module

    original_join = deepseek_module._join_inflight

    def observed_join(key: str):
        nonlocal joined_count
        state, owner = original_join(key)
        if not owner:
            with joined_lock:
                joined_count += 1
                if joined_count == 3:
                    all_waiters_joined.set()
        return state, owner

    monkeypatch.setattr(deepseek_module, "_join_inflight", observed_join)
    transport = HeaderOnlyTransport()

    def config(api_key: str) -> LlmConfig:
        return LlmConfig(
            model="grok-4.6",
            base_url="http://127.0.0.1:1/",
            api_key=api_key,
            timeout_seconds=3,
            max_retries=1,
            temperature=0,
            cache_dir=tmp_path / "cache",
            allow_remote_llm=True,
            source_checkout=tmp_path,
        )

    owner = DeepSeekClient(
        config("owner-api-key"),
        verifier=StaticPublicVerifier(),
        transport=transport,
        sleep=lambda _delay: None,
    )
    safe_waiter = DeepSeekClient(
        config("safe-waiter-key"),
        verifier=StaticPublicVerifier(),
        transport=transport,
        extra_secret_patterns=(("nonmatching", re.compile("never-present")),),
        sleep=lambda _delay: None,
    )
    api_key_waiter = DeepSeekClient(
        config(waiter_api_key),
        verifier=StaticPublicVerifier(),
        transport=transport,
        sleep=lambda _delay: None,
    )
    pattern_waiter = DeepSeekClient(
        config("pattern-waiter-key"),
        verifier=StaticPublicVerifier(),
        transport=transport,
        extra_secret_patterns=(("request-id-marker", re.compile(request_id)),),
        sleep=lambda _delay: None,
    )
    results: dict[str, object] = {}

    def classify(name: str, client: DeepSeekClient) -> None:
        try:
            results[name] = client.classify_growth(_slice())
        except BaseException as exc:  # test captures exact cross-thread outcome
            results[name] = exc

    owner_thread = threading.Thread(target=classify, args=("owner", owner))
    owner_thread.start()
    assert provider_entered.wait(5)
    waiter_threads = (
        threading.Thread(target=classify, args=("safe", safe_waiter)),
        threading.Thread(target=classify, args=("api_key", api_key_waiter)),
        threading.Thread(target=classify, args=("pattern", pattern_waiter)),
    )
    for worker in waiter_threads:
        worker.start()
    assert all_waiters_joined.wait(5)
    release_provider.set()
    for worker in (owner_thread, *waiter_threads):
        worker.join(5)
        assert not worker.is_alive()

    assert transport.request_count == 1
    assert not isinstance(results["owner"], BaseException)
    assert not isinstance(results["safe"], BaseException)
    for name in ("api_key", "pattern"):
        assert isinstance(results[name], AnalyzerError)
        assert results[name].code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    _assert_traceback_locals_do_not_retain_marker(results["api_key"], waiter_api_key)
    _assert_traceback_locals_do_not_retain_marker(results["pattern"], request_id)
    assert safe_waiter.last_audit() is not None
    assert safe_waiter.last_audit().request_id == request_id
    assert api_key_waiter.last_audit() is None
    assert pattern_waiter.last_audit() is None
    cache_file = next((tmp_path / "cache").glob("*.json"))
    assert request_id not in cache_file.read_text(encoding="utf-8")

    replay_client = DeepSeekClient(
        config("owner-api-key"),
        verifier=StaticPublicVerifier(),
        transport=transport,
        sleep=lambda _delay: None,
    )
    replayed = replay_client.classify_growth(_slice())
    assert replayed == results["owner"]
    assert transport.request_count == 1
    assert replay_client.last_audit() is not None
    assert replay_client.last_audit().request_id == ""


def test_cache_hit_uses_one_authenticated_snapshot_during_file_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_transport = ScriptedDeepSeekTransport(
        growth=lambda _request: _aliased_provider_payload(attacker_variable="snapshot-a")
    )
    contract_a = _client(tmp_path, first_transport).classify_growth(_slice())
    cache_a = next((tmp_path / "cache").glob("*.json"))

    other_root = tmp_path / "other"
    other_root.mkdir()
    second_transport = ScriptedDeepSeekTransport(
        growth=lambda _request: _aliased_provider_payload(attacker_variable="snapshot-b")
    )
    contract_b = _client(other_root, second_transport).classify_growth(_slice())
    cache_b = next((other_root / "cache").glob("*.json"))
    replacement = cache_b.read_bytes()
    assert contract_a != contract_b

    replay_transport = ScriptedDeepSeekTransport(
        growth=lambda _request: pytest.fail("cache replay must not call provider")
    )
    replay_client = _client(tmp_path, replay_transport)
    original_read = replay_client._cache._strict_growth_entry  # noqa: SLF001
    read_count = 0

    def replace_after_first_read(key: str, identity: object):
        nonlocal read_count
        read_count += 1
        snapshot = original_read(key, identity)
        if read_count == 1:
            cache_a.write_bytes(replacement)
        return snapshot

    monkeypatch.setattr(replay_client._cache, "_strict_growth_entry", replace_after_first_read)  # noqa: SLF001

    replayed = replay_client.classify_growth(_slice())
    audit = replay_client.last_audit()

    assert replayed == contract_a
    assert audit is not None
    assert audit.parsed_response == contract_a.to_dict()
    assert "snapshot-a" in audit.raw_response
    assert "snapshot-b" not in audit.raw_response
    assert read_count == 1
    assert replay_transport.request_count == 0


def _client(tmp_path: Path, transport: ScriptedDeepSeekTransport) -> DeepSeekClient:
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
        transport=transport,
        sleep=lambda _delay: None,
    )


def test_semantic_invalid_growth_response_gets_one_bounded_correction_retry(tmp_path) -> None:
    attempts = 0

    def growth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return (
            {"is_resource_growth": "yes"}
            if attempts == 1
            else _provider_payload(
                attacker_evidence_ids=["fact:1"],
                required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
            )
        )

    transport = ScriptedDeepSeekTransport(growth=growth)
    client = _client(tmp_path, transport)

    contract = client.classify_growth(_slice())

    assert contract.growth_kind == "container_growth"
    assert transport.request_count == 2
    assert "one correction attempt" in str(transport.requests[1]["instructions"])
    cache_files = list((tmp_path / "cache").glob("*.json"))
    assert len(cache_files) == 1
    cached = cache_files[0].read_text(encoding="utf-8")
    assert "fixture-2" in cached
    assert "fixture-1" not in cached


def test_second_semantic_invalid_growth_response_fails_closed_without_cache(tmp_path) -> None:
    marker = "second-schema-rejected-body-marker"
    transport = ScriptedDeepSeekTransport(
        growth=lambda _request: {
            "is_resource_growth": "yes",
            "unexpected": marker,
        }
    )

    with pytest.raises(AnalyzerError) as raised:
        _client(tmp_path, transport).classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    _assert_traceback_locals_do_not_retain_marker(raised.value, marker)
    assert transport.request_count == 2
    assert list((tmp_path / "cache").glob("*.json")) == []


def test_sensitive_growth_response_gets_one_safe_correction_without_echo(tmp_path) -> None:
    attempts = 0
    sensitive_marker = "first-response-sensitive@example.test"

    def growth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _provider_payload(attacker_variable=sensitive_marker)
        return _provider_payload(
            attacker_evidence_ids=["fact:1"],
            required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
        )

    transport = ScriptedDeepSeekTransport(growth=growth)
    client = _client(tmp_path, transport)

    contract = client.classify_growth(_slice())

    assert contract.growth_kind == "container_growth"
    assert transport.request_count == 2
    correction = transport.requests[1]
    assert sensitive_marker not in str(correction)
    instructions = str(correction["instructions"])
    assert "exactly these seventeen keys" in instructions
    assert "at most 16 unique" in instructions
    assert "at most 32 unique" in instructions
    assert "exact fact:<ordinal> aliases" in instructions
    assert "exactly one attacker target enum value" in instructions
    assert "contract_status=dos_relevant" in instructions
    assert "contract_status=growth_not_dos_relevant" in instructions
    assert "contract_status=unknown" in instructions
    cache_files = list((tmp_path / "cache").glob("*.json"))
    assert len(cache_files) == 1
    cached = cache_files[0].read_text(encoding="utf-8")
    assert sensitive_marker not in cached
    assert "fixture-1" not in cached
    assert "fixture-2" in cached
    assert client.last_audit() is not None
    assert sensitive_marker not in client.last_audit().raw_response


def test_unicode_escaped_configured_key_gets_one_safe_growth_correction(
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
            contract = _aliased_provider_payload(
                attacker_variable=marker if self.request_count == 1 else "request key"
            )
            content = (
                _json_with_unicode_escaped_value(contract, marker)
                if self.request_count == 1
                else json.dumps(contract)
            )
            return _growth_envelope(request, content, f"growth-escaped-key-{self.request_count}")

    transport = EscapedThenSafeTransport()
    client = _client(tmp_path, transport)

    contract = client.classify_growth(_slice())

    assert contract.contract_status == "dos_relevant"
    assert transport.request_count == 2
    assert marker not in str(transport.requests[1])
    audit = client.last_audit()
    assert audit is not None and marker not in audit.raw_response
    cache_file = next((tmp_path / "cache").glob("*.json"))
    assert marker not in cache_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "sensitive_marker",
    [
        "api_key=credential-value",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
        "postgresql://user:password@datastore.example/app",
        "owner@example.test",
        "+1 415-555-2671",
        "123-45-6789",
    ],
)
def test_repeated_unicode_escaped_growth_semantic_sensitive_value_is_terminal(
    tmp_path: Path,
    sensitive_marker: str,
) -> None:
    class AlwaysEscapedTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            contract = _aliased_provider_payload(attacker_variable=sensitive_marker)
            content = _json_with_unicode_escaped_value(contract, sensitive_marker)
            return _growth_envelope(request, content, f"growth-escaped-{self.request_count}")

    transport = AlwaysEscapedTransport()
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    assert sensitive_marker not in f"{raised.value.message} {raised.value.details}"
    _assert_traceback_locals_do_not_retain_marker(raised.value, sensitive_marker)
    assert transport.request_count == 2
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("*.json")) == []


def test_repeated_unicode_escaped_growth_source_echo_is_terminal(tmp_path: Path) -> None:
    marker = "unique-source-echo-" + "x" * 96
    slice_ = _slice()
    excerpt = replace(
        slice_.source_excerpts[0],
        content=marker,
        excerpt_sha256=hashlib.sha256(marker.encode()).hexdigest(),
        original_excerpt_sha256=hashlib.sha256(marker.encode()).hexdigest(),
    )
    slice_ = replace(slice_, payload=replace(slice_.payload, source_excerpts=(excerpt,)))

    class AlwaysEscapedEchoTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            contract = _aliased_provider_payload(attacker_variable=marker)
            return _growth_envelope(
                request,
                _json_with_unicode_escaped_value(contract, marker),
                f"growth-escaped-echo-{self.request_count}",
            )

    transport = AlwaysEscapedEchoTransport()
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(slice_)

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    _assert_traceback_locals_do_not_retain_marker(raised.value, marker)
    assert transport.request_count == 2
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("*.json")) == []


@pytest.mark.parametrize("unknown_case", ["pii", "source_echo", "plain"])
def test_growth_unknown_assistant_content_part_is_permanent_protocol_failure(
    tmp_path: Path,
    unknown_case: str,
) -> None:
    marker = (
        "unknown-part-owner@example.test"
        if unknown_case == "pii"
        else "unknown-part-source-echo-" + "x" * 96
        if unknown_case == "source_echo"
        else "unknown-part-plain-marker"
    )
    slice_ = _slice()
    if unknown_case == "source_echo":
        excerpt = replace(
            slice_.source_excerpts[0],
            content=marker,
            excerpt_sha256=hashlib.sha256(marker.encode()).hexdigest(),
            original_excerpt_sha256=hashlib.sha256(marker.encode()).hexdigest(),
        )
        slice_ = replace(
            slice_,
            payload=replace(slice_.payload, source_excerpts=(excerpt,)),
        )

    class UnknownPartTransport:
        def __init__(self) -> None:
            self.request_count = 0

        def post(self, _endpoint: str, payload: bytes, _headers: dict[str, str], _timeout: int) -> str:
            self.request_count += 1
            request = json.loads(payload)
            return json.dumps(
                {
                    "id": "growth-unknown-part",
                    "status": "completed",
                    "model": request["model"],
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(_aliased_provider_payload()),
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
    client = _client(tmp_path, transport)  # type: ignore[arg-type]

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(slice_)

    assert raised.value.code == "LLM_RESPONSE_INVALID"
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    _assert_traceback_locals_do_not_retain_marker(raised.value, marker)
    assert transport.request_count == 1
    assert client.last_audit() is None
    assert list((tmp_path / "cache").glob("*.json")) == []


@pytest.mark.parametrize(
    "sensitive_marker",
    ["owner@example.test", "+1 415-555-2671", "123-45-6789"],
)
def test_second_sensitive_growth_response_is_terminal_without_cache_or_audit(
    tmp_path: Path,
    sensitive_marker: str,
) -> None:
    transport = ScriptedDeepSeekTransport(
        growth=lambda _request: _provider_payload(attacker_variable=sensitive_marker)
    )
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert sensitive_marker not in f"{raised.value.message} {raised.value.details}"
    _assert_traceback_locals_do_not_retain_marker(raised.value, sensitive_marker)
    assert transport.request_count == 2
    assert list((tmp_path / "cache").glob("*.json")) == []
    assert client.last_audit() is None


def test_first_sensitive_response_is_not_retained_when_correction_transport_fails(
    tmp_path,
) -> None:
    marker = "first-sensitive-before-transport-failure@example.test"
    first_body = json.dumps(
        {
            "id": "fixture-sensitive-first",
            "status": "completed",
            "model": "grok-4.6",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                _provider_payload(attacker_variable=marker),
                                separators=(",", ":"),
                            ),
                        }
                    ],
                }
            ],
        },
        separators=(",", ":"),
    )

    class SensitiveThenFailureTransport:
        def __init__(self, response: str) -> None:
            self.request_count = 0
            self._response = response

        def post(
            self,
            _endpoint: str,
            payload: bytes,
            _headers: dict[str, str],
            _timeout: int,
        ) -> str:
            self.request_count += 1
            if self.request_count == 2:
                raise OSError("deterministic correction transport failure")
            json.loads(payload.decode("utf-8"))
            return self._response

    transport = SensitiveThenFailureTransport(first_body)
    client = _client(tmp_path, transport)  # type: ignore[arg-type]

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_NETWORK_FAILED"
    assert transport.request_count == 2
    _assert_traceback_locals_do_not_retain_marker(raised.value, marker)
    assert list((tmp_path / "cache").glob("*.json")) == []
    assert client.last_audit() is None


def test_sensitive_then_schema_invalid_growth_response_is_terminal_without_cache(tmp_path) -> None:
    attempts = 0
    sensitive_marker = "first-only-sensitive@example.test"

    def growth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return (
            _provider_payload(attacker_variable=sensitive_marker)
            if attempts == 1
            else {"is_resource_growth": "yes"}
        )

    transport = ScriptedDeepSeekTransport(growth=growth)
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert transport.request_count == 2
    assert sensitive_marker not in str(transport.requests[1])
    assert list((tmp_path / "cache").glob("*.json")) == []
    assert client.last_audit() is None


def test_schema_invalid_then_sensitive_growth_response_is_terminal_without_cache(tmp_path) -> None:
    attempts = 0
    schema_marker = "first-schema-response-marker"
    sensitive_marker = "second-sensitive@example.test"

    def growth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return (
            {"is_resource_growth": "yes", "unexpected": schema_marker}
            if attempts == 1
            else _provider_payload(attacker_variable=sensitive_marker)
        )

    transport = ScriptedDeepSeekTransport(growth=growth)
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SENSITIVE_CONTENT"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert transport.request_count == 2
    assert schema_marker not in str(transport.requests[1])
    assert sensitive_marker not in f"{raised.value.message} {raised.value.details}"
    assert list((tmp_path / "cache").glob("*.json")) == []
    assert client.last_audit() is None


def test_correction_success_cache_hit_replays_identical_accepted_prompt(tmp_path) -> None:
    attempts = 0

    def growth(_request: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return (
            {"is_resource_growth": "yes"}
            if attempts == 1
            else _provider_payload(
                attacker_evidence_ids=["fact:1"],
                required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
            )
        )

    transport = ScriptedDeepSeekTransport(growth=growth)
    fresh_client = _client(tmp_path, transport)
    fresh_contract = fresh_client.classify_growth(_slice())
    fresh_audit = fresh_client.last_audit()
    assert fresh_audit is not None
    assert "one correction attempt" in fresh_audit.normalized_prompt

    cached_client = _client(tmp_path, transport)
    cached_contract = cached_client.classify_growth(_slice())
    cached_audit = cached_client.last_audit()

    assert cached_contract == fresh_contract
    assert transport.request_count == 2
    assert cached_audit is not None
    assert cached_audit.cache_hit is True
    assert cached_audit.normalized_prompt == fresh_audit.normalized_prompt
    assert cached_audit.raw_response == fresh_audit.raw_response
    assert cached_audit.parsed_response == fresh_audit.parsed_response
    cache_record = json.loads(next((tmp_path / "cache").glob("*.json")).read_text())
    assert cache_record["cache_format"] == "growth-contract-cache-v14"
    assert cache_record["accepted_prompt_variant"] == "correction"


def test_terminal_malformed_schema_error_chain_does_not_retain_rejected_body(tmp_path) -> None:
    marker = "malformed-rejected-body-marker"

    class MalformedSchemaTransport:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(
            self,
            _endpoint: str,
            payload: bytes,
            _headers: dict[str, str],
            _timeout: int,
        ) -> str:
            request = json.loads(payload.decode("utf-8"))
            assert isinstance(request, dict)
            self.requests.append(request)
            malformed = '{"is_resource_growth":"yes","marker":"' + marker + '"'
            return json.dumps(
                {
                    "id": f"fixture-{len(self.requests)}",
                    "status": "completed",
                    "model": "grok-4.6",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": malformed}],
                        }
                    ],
                },
                separators=(",", ":"),
            )

    transport = MalformedSchemaTransport()
    client = _client(tmp_path, transport)  # type: ignore[arg-type]

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert len(transport.requests) == 2
    current: BaseException | None = raised.value
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        diagnostic = " ".join(
            (
                str(current),
                repr(current),
                repr(getattr(current, "args", ())),
                str(getattr(current, "doc", "")),
            )
        )
        assert marker not in diagnostic
        current = current.__cause__ or current.__context__
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert list((tmp_path / "cache").glob("*.json")) == []


def test_malformed_responses_envelope_traceback_locals_do_not_retain_body(tmp_path) -> None:
    marker = "malformed-envelope-rejected-body-marker"
    client = _client(tmp_path, ScriptedDeepSeekTransport())
    reply = ProviderReply(
        '{"status":"completed","marker":"' + marker + '"',
        {},
    )

    with pytest.raises(AnalyzerError) as raised:
        client._response_content(reply)

    assert raised.value.code == "LLM_RESPONSE_INVALID"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    _assert_traceback_locals_do_not_retain_marker(raised.value, marker)


@pytest.mark.parametrize("growth_value", ["no", "unknown"])
def test_dos_relevant_without_positive_growth_gets_one_correction_then_terminal(
    tmp_path,
    growth_value: str,
) -> None:
    transport = ScriptedDeepSeekTransport(
        growth=lambda _request: _provider_payload(
            is_resource_growth=growth_value,
            attacker_evidence_ids=["fact:1"],
            required_static_evidence=["fact:3", "fact:4", "fact:5", "fact:6"],
        )
    )
    client = _client(tmp_path, transport)

    with pytest.raises(AnalyzerError) as raised:
        client.classify_growth(_slice())

    assert raised.value.code == "LLM_RESPONSE_SCHEMA_INVALID"
    assert transport.request_count == 2
    assert "one correction attempt" in str(transport.requests[1]["instructions"])
    assert list((tmp_path / "cache").glob("*.json")) == []
    assert client.last_audit() is None
    assert client.last_audit() is None
