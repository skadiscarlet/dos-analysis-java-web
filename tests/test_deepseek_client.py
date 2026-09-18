from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import stat
import tempfile
import subprocess
import threading
import multiprocessing
import time
import unittest
import errno
import socket
import ssl
from urllib.error import URLError
from dataclasses import replace
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path

from dosweb.config import LlmConfig
from dosweb.errors import AnalyzerError
from dosweb.growth.models import (
    BoundedSlice, BoundedSlicePayload, CfgSummary, ConfigFact, RegistrationFact, SourceExcerpt, StaticFact,
)
from dosweb.growth.contracts import parse_growth_contract_json, validate_growth_contract
from dosweb.llm.cache import ContractCache, cache_identity
from dosweb.llm.prompts import build_growth_messages
from dosweb.llm.schemas import AUTH_PROMPT_VERSION
from dosweb.reachability.models import EntrySecurityFact, LlmAuditRecord
from dosweb.llm.deepseek import (
    DeepSeekClient,
    GitHubPublicSourceVerifier,
    ProviderReply,
    PublicSourceAttestation,
    validate_provider_endpoint,
)


VALID_CONTRACT = {
    "is_resource_growth": "yes",
    "growth_kind": "container_growth",
    "resource_dimension": "entries",
    "attacker_influence": [{"target": "key", "evidence_id": "fact:key"}],
    "resource_effect": "adds_entries",
    "attacker_variable": "request key",
    "attacker_value_space": "unlimited",
    "growth_unit": "one retained map entry",
    "growth_function": "distinct keys add retained entries",
    "amplification_class": "high_cardinality_retention",
    "requests_to_pressure": "many",
    "concurrency_model": "repeatable requests",
    "retention_window": "process",
    "failure_mechanism": "heap_exhaustion",
    "failure_signal": "retained entries exhaust heap",
    "required_static_evidence": ["fact:key", "fact:put"],
    "contract_status": "dos_relevant",
    "rejection_reason": "none",
    "confidence": "high",
}

PROVIDER_CONTRACT = {
    **{
        key: value
        for key, value in VALID_CONTRACT.items()
        if key not in {"growth_kind", "resource_dimension", "attacker_influence"}
    },
    "attacker_evidence_ids": ["fact:1"],
    "required_static_evidence": ["fact:1", "fact:2"],
}

UNKNOWN_CONTRACT = {
    **PROVIDER_CONTRACT,
    "is_resource_growth": "unknown",
    "resource_effect": "unknown",
    "attacker_variable": "unknown",
    "attacker_value_space": "unknown",
    "growth_unit": "unknown",
    "growth_function": "unknown",
    "amplification_class": "unknown",
    "requests_to_pressure": "unknown",
    "concurrency_model": "unknown",
    "retention_window": "unknown",
    "failure_mechanism": "unknown",
    "failure_signal": "unknown",
    "contract_status": "unknown",
    "rejection_reason": "unknown",
    "confidence": "low",
}


class _ScriptedHandler(BaseHTTPRequestHandler):
    scripted_responses: list[tuple[int, object]] = []
    requests: list[dict[str, object]] = []
    lock = threading.Lock()

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size).decode("utf-8")
        with self.lock:
            self.requests.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers.items()),
                    "body": body,
                }
            )
            status, payload = self.scripted_responses.pop(0)
        encoded = (
            payload.encode("utf-8")
            if isinstance(payload, str)
            else json.dumps(payload).encode("utf-8")
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def _process_cache_producer(cache_dir: str, key: str, identity: dict[str, object], ready: object, start: object, produced: object) -> None:
    """Test worker: flock serializes recheck and lets exactly one worker publish."""
    cache = ContractCache(Path(cache_dir), "test-api-key")
    ready.put(True)
    start.wait(10)
    with cache.single_flight(key):
        if cache.get(key, identity, frozenset({"fact:key", "fact:put"})) is None:
            time.sleep(0.2)
            cache.put(
                key,
                identity,
                validate_growth_contract(VALID_CONTRACT),
                {
                    "method": identity["request_method"], "url": identity["request_url"], "provider": identity["provider"], "protocol": "responses-v1",
                    "requested_model": "grok-4.6", "actual_model": "grok-4.6",
                    "provider_request_id_digest": cache.provider_request_id_digest("fixture"), "slice_content_hash": identity["slice_content_hash"],
                    "allow_remote_llm": True, "public_source_url": identity["public_source_url"],
                    "source_commit_sha": identity["source_commit_sha"], "verified_public": identity["verified_public"], "verified_clean_checkout": identity["verified_clean_checkout"],
                },
            )
            produced.put(True)


class _VerifierJsonResponse:
    status = 200
    headers: dict[str, str] = {}

    def __init__(self, url: str, payload: object) -> None:
        self._url = url
        self._payload = json.dumps(payload).encode("utf-8")

    def getcode(self) -> int: return 200
    def geturl(self) -> str: return self._url
    def read(self, size: int) -> bytes:
        chunk, self._payload = self._payload[:size], self._payload[size:]
        return chunk
    def __enter__(self): return self
    def __exit__(self, *args: object) -> None: return None


class _LoopbackTransport:
    def post(self, endpoint: str, payload: bytes, headers: dict[str, str], timeout: int) -> str:
        request = Request(endpoint, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise AnalyzerError("LLM_AUTHENTICATION_FAILED", "mock authentication") from exc
            if exc.code == 429 or 500 <= exc.code <= 599:
                raise AnalyzerError("LLM_RETRYABLE_HTTP", "mock retry", {"status": exc.code}) from exc
            raise AnalyzerError("LLM_RESPONSE_INVALID", "mock response", {"status": exc.code}) from exc


class _FakeVerifier:
    def __init__(self, attestation: PublicSourceAttestation | None = None, error: AnalyzerError | None = None) -> None:
        self.attestation = attestation
        self.error = error
        self.calls = 0
        self.slice_calls = 0

    def verify(self, config: LlmConfig) -> PublicSourceAttestation:
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.attestation is None:
            raise AssertionError("A test verifier must have an attestation.")
        return self.attestation

    def validate_slice(
        self,
        config: LlmConfig,
        slice_: BoundedSlice,
        attestation: PublicSourceAttestation,
    ) -> None:
        self.slice_calls += 1
        if self.error is not None:
            raise self.error


class DeepSeekClientTests(unittest.TestCase):
    def setUp(self) -> None:
        _ScriptedHandler.scripted_responses = []
        _ScriptedHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ScriptedHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temporary_directory.name) / "cache"
        self.config = LlmConfig(
            model="grok-4.6",
            base_url=f"http://127.0.0.1:{self.server.server_port}/",
            api_key="test-api-key",
            timeout_seconds=1,
            max_retries=3,
            temperature=0,
            cache_dir=self.cache_dir,
            allow_remote_llm=True,
            public_source_url="https://github.com/example/public-repository",
            source_commit_sha="a" * 40,
            source_checkout=Path(self.temporary_directory.name),
        )
        self.attestation = PublicSourceAttestation(
            public_source_url="https://github.com/example/public-repository",
            source_commit_sha="a" * 40,
            verified_public=True,
            verified_clean_checkout=True,
        )
        excerpt_content = "map.put(key, value);"
        self.slice = BoundedSlice(
            "slice:1",
            BoundedSlicePayload(
                entry_id="entry:1",
                growth_id="growth:1",
                source_excerpts=(
                    SourceExcerpt(
                        "excerpt:1",
                        "Example.java",
                        1,
                        1,
                        excerpt_content,
                        "a" * 64,
                        hashlib.sha256(excerpt_content.encode()).hexdigest(),
                    ),
                ),
                static_facts=(
                    StaticFact("fact:key", "flow", "excerpt:1", "source"),
                    StaticFact("fact:put", "container_write", "excerpt:1", "sink"),
                    StaticFact("fact:target", "attacker_target", "excerpt:1", "source", "fact:key", "key"),
                ),
                cfg_summary=CfgSummary(("path:1",), ("in_handler",), ("fact:key",)),
                registration_facts=(RegistrationFact("spring_mvc", "excerpt:1"),),
                config_facts=(),
            ),
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary_directory.cleanup()

    def _client(self, verifier: _FakeVerifier | None = None, **overrides: object) -> DeepSeekClient:
        return DeepSeekClient(
            replace(self.config, **overrides),
            verifier=verifier or _FakeVerifier(self.attestation),
            transport=_LoopbackTransport(),
            sleep=lambda _: None,
            jitter=lambda: 0,
        )

    @staticmethod
    def _success(content: object) -> dict[str, object]:
        return {"model": "grok-4.6", "id": "req_fixture_1", "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(content)}]}]}

    @staticmethod
    def _slice_with_content(content: str) -> BoundedSlice:
        return BoundedSlice(
            "slice:sensitive",
            BoundedSlicePayload(
                "entry:sensitive", "growth:sensitive",
                (SourceExcerpt("excerpt:sensitive", "Example.java", 1, 1, content, "a" * 64, hashlib.sha256(content.encode()).hexdigest()),),
                (
                    StaticFact("fact:sensitive", "flow", "excerpt:sensitive", "source"),
                    StaticFact("fact:sink", "container_write", "excerpt:sensitive", "sink"),
                    StaticFact("fact:target", "attacker_target", "excerpt:sensitive", "source", "fact:sensitive", "key"),
                ),
                CfgSummary(("path:sensitive",), ("in_handler",), ("fact:sensitive",)),
                (RegistrationFact("spring_mvc", "excerpt:sensitive"),), (),
            ),
        )

    def test_valid_contract_uses_rightapi_responses(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        client = self._client()
        result = client.classify_growth(self.slice)

        self.assertEqual(result.is_resource_growth, "yes")
        self.assertEqual(len(_ScriptedHandler.requests), 1)
        request = _ScriptedHandler.requests[0]
        self.assertEqual(request["path"], "/responses")
        headers = request["headers"]
        self.assertEqual(headers["Authorization"], "Bearer test-api-key")
        self.assertEqual(headers["User-Agent"], "pi-coding-agent")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertNotIn("Cookie", headers)
        self.assertNotIn("test-api-key", request["body"])
        body = json.loads(request["body"])
        self.assertEqual(body["model"], "grok-4.6")
        self.assertEqual(body["temperature"], 0)
        self.assertIn("instructions", body)
        self.assertEqual(body["input"][0]["content"][0]["type"], "input_text")
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertEqual(client.last_audit().settings["provider"], "rightapi_responses")
        _, identity = cache_identity(self.config, self.slice)
        self.assertEqual(identity["provider"], "rightapi_responses")
        self.assertEqual(body["text"]["format"]["name"], "growth_contract")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(
            set(body["text"]["format"]["schema"]),
            {"type", "properties", "required", "additionalProperties"},
        )
        self.assertEqual(len(body["text"]["format"]["schema"]["required"]), 17)
        self.assertFalse(body["store"])
        self.assertFalse(body["stream"])
        self.assertNotIn("messages", body)
        self.assertNotIn("response_format", body)

    def test_semantic_unknown_is_a_successful_contract(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(UNKNOWN_CONTRACT))]

        result = self._client().classify_growth(self.slice)

        self.assertEqual(result.is_resource_growth, "unknown")
        self.assertEqual(result.growth_kind, "container_growth")
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_429_and_500_are_retried_up_to_configured_attempts(self) -> None:
        _ScriptedHandler.scripted_responses = [(429, {}), (500, {}), (500, {})]

        with self.assertRaises(AnalyzerError) as raised:
            self._client(max_retries=3).classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_RETRIES_EXHAUSTED")
        self.assertEqual(len(_ScriptedHandler.requests), 3)

    def test_401_fails_without_retry(self) -> None:
        _ScriptedHandler.scripted_responses = [(401, {"error": "invalid key"})]

        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_AUTHENTICATION_FAILED")
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_empty_or_non_json_content_fails_schema_validation(self) -> None:
        for content in ("", "not-json"):
            with self.subTest(content=content):
                response = (200, {"model": "grok-4.6", "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": content}]}]})
                _ScriptedHandler.scripted_responses = [response] if not content else [response, response]
                with self.assertRaises(AnalyzerError) as raised:
                    self._client().classify_growth(self.slice)
                self.assertIn(raised.exception.code, {"LLM_RESPONSE_INVALID", "LLM_RESPONSE_SCHEMA_INVALID"})

    def test_cache_rejects_response_with_tampered_hash(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        client = self._client()
        client.classify_growth(self.slice)
        cache_file = next(self.cache_dir.glob("*.json"))
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        entry["entry_hash"] = "tampered"
        cache_file.write_text(json.dumps(entry), encoding="utf-8")
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        with self.assertRaises(AnalyzerError) as raised:
            client.classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_CACHE_CONFLICT")
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_cache_entry_requires_hmac_bound_to_the_api_key(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client(api_key="cache-auth-key").classify_growth(self.slice)
        cache_file = next(self.cache_dir.glob("*.json"))
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertNotIn("cache-auth-key", cache_file.read_text(encoding="utf-8"))
        self.assertIn("entry_hmac", entry)
        # An attacker can recompute every unkeyed SHA-256 value but cannot forge entry_hmac.
        entry["contract"]["resource_effect"] = "forged effect"
        entry["contract_hash"] = hashlib.sha256(
            json.dumps(entry["contract"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        stable = {name: entry[name] for name in entry if name not in {"entry_hash", "entry_hmac"}}
        entry["entry_hash"] = hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        cache_file.write_text(json.dumps(entry), encoding="utf-8")

        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        with self.assertRaises(AnalyzerError) as raised:
            self._client(api_key="cache-auth-key").classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_CACHE_CONFLICT")
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_cache_with_a_different_api_key_is_a_miss(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client(api_key="first-key").classify_growth(self.slice)
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        with self.assertRaises(AnalyzerError) as raised:
            self._client(api_key="second-key").classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_CACHE_CONFLICT")
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_cache_files_are_private_and_regular(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client().classify_growth(self.slice)
        cache_file = next(self.cache_dir.glob("*.json"))

        self.assertEqual(stat.S_IMODE(self.cache_dir.stat().st_mode), 0o700)
        lock_file = next(self.cache_dir.glob(".stripe-*.lock"))
        self.assertEqual(stat.S_IMODE(cache_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(lock_file.stat().st_mode), 0o600)
        self.assertEqual(cache_file.stat().st_uid, os.getuid())
        self.assertEqual(lock_file.stat().st_uid, os.getuid())

    def test_symlinked_cache_directory_is_not_used(self) -> None:
        real_cache = self.cache_dir.parent / "real-cache"
        real_cache.mkdir(mode=0o700)
        self.cache_dir.symlink_to(real_cache, target_is_directory=True)
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_CACHE_UNSAFE")
        self.assertEqual(len(_ScriptedHandler.requests), 0)
        self.assertEqual(list(real_cache.glob("*.json")), [])

    def test_symlinked_cache_entry_is_a_miss_and_is_not_replaced(self) -> None:
        key, identity = cache_identity(self.config, self.slice)
        self.cache_dir.mkdir(mode=0o700)
        target = self.cache_dir.parent / "outside-entry.json"
        target.write_text("{}", encoding="utf-8")
        (self.cache_dir / f"{key}.json").symlink_to(target)
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_CACHE_UNSAFE")
        self.assertEqual(len(_ScriptedHandler.requests), 0)
        self.assertTrue((self.cache_dir / f"{key}.json").is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "{}")

    def test_unsafe_permissions_and_lock_symlink_disable_cache_writes(self) -> None:
        key, _ = cache_identity(self.config, self.slice)
        self.cache_dir.mkdir(mode=0o755)
        lock_target = self.cache_dir.parent / "outside-lock"
        lock_target.write_bytes(b"")
        (self.cache_dir / f".stripe-{int(key[:8], 16) % 64:02d}.lock").symlink_to(lock_target)
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)

        self.assertIn(raised.exception.code, {"LLM_CACHE_UNSAFE", "LLM_CACHE_LOCK_FAILED"})
        self.assertEqual(len(_ScriptedHandler.requests), 0)
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])
        self.assertTrue((self.cache_dir / f".stripe-{int(key[:8], 16) % 64:02d}.lock").is_symlink())

    def test_unsafe_lock_invalidates_an_existing_cache_hit(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client().classify_growth(self.slice)
        key, _ = cache_identity(self.config, self.slice)
        target = self.cache_dir.parent / "outside-lock"
        target.write_bytes(b"")
        lock_path = self.cache_dir / f".stripe-{int(key[:8], 16) % 64:02d}.lock"
        lock_path.unlink()
        lock_path.symlink_to(target)
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_CACHE_LOCK_FAILED")
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_cache_rejects_foreign_owner_when_lstat_is_mocked(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client().classify_growth(self.slice)
        key, identity = cache_identity(self.config, self.slice)
        original_lstat = os.lstat

        def foreign_owner(path: object, *args: object, **kwargs: object) -> os.stat_result:
            result = original_lstat(path, *args, **kwargs)
            if Path(path).name == f"{key}.json":
                values = list(result)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return result

        with mock.patch("dosweb.llm.cache.os.lstat", side_effect=foreign_owner):
            self.assertIsNone(ContractCache(self.cache_dir, "test-api-key").get(key, identity, frozenset({"fact:key", "fact:put"})))

    def test_successful_cache_hit_skips_second_http_request(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        client = self._client()

        first = client.classify_growth(self.slice)
        second = client.classify_growth(self.slice)

        self.assertEqual(first, second)
        self.assertEqual(len(_ScriptedHandler.requests), 1)
        self.assertEqual(len(list(self.cache_dir.glob("*.json"))), 1)

    def test_v9_cache_entry_is_a_miss_even_with_a_valid_old_domain_hmac(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client(api_key="cache-auth-key").classify_growth(self.slice)
        key, identity = cache_identity(self.config, self.slice)
        cache_file = self.cache_dir / f"{key}.json"
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        entry["cache_format"] = "growth-contract-cache-v9"
        entry.pop("accepted_prompt_variant")
        stable = {
            name: value
            for name, value in entry.items()
            if name not in {"entry_hash", "entry_hmac"}
        }
        entry["entry_hash"] = hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        unsigned = {name: value for name, value in entry.items() if name != "entry_hmac"}
        entry["entry_hmac"] = hmac.new(
            b"cache-auth-key",
            b"growth-contract-cache-entry-v9\0"
            + json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        cache_file.write_text(json.dumps(entry), encoding="utf-8")

        self.assertIsNone(
            ContractCache(self.cache_dir, "cache-auth-key").get(
                key,
                identity,
                frozenset({"fact:key", "fact:put"}),
            )
        )

    def test_fresh_client_reuses_cache_when_only_caller_slice_id_changes(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        first = self._client().classify_growth(self.slice)
        equivalent_slice = BoundedSlice("slice:untrusted-caller-value", self.slice.payload)

        second = self._client().classify_growth(equivalent_slice)

        self.assertEqual(first, second)
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_growth_messages_exclude_caller_controlled_slice_id(self) -> None:
        caller_slice_id = "slice:untrusted-caller-value"
        messages = build_growth_messages(BoundedSlice(caller_slice_id, self.slice.payload))

        serialized_request = json.dumps(messages, separators=(",", ":"), ensure_ascii=False)

        self.assertNotIn(caller_slice_id, serialized_request)

    def test_serialized_request_scan_blocks_credentials_and_pii_before_side_effects(self) -> None:
        api_key = "configured-api-key"
        examples = (
            api_key,
            'apiKey="camel-secret"',
            'privateKey="camel-private"',
            'refreshToken="camel-refresh"',
            'dbPassword="database-secret"',
            'DB_PASSWORD="database-secret"',
            'oauthToken="oauth-secret"',
            'api_key="snake-secret"',
            'private_key="snake-private"',
            'refresh_token="snake-refresh"',
            'api-key="hyphen-secret"',
            'private-key="hyphen-private"',
            'refresh-token="hyphen-refresh"',
            'AWS_SECRET_ACCESS_KEY="aws-secret"',
            'X-Api-Key: header-secret',
            '-----BEGIN PRIVATE KEY-----',
            'ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN',
            'sk-deepseek-provider-secret',
            'AKIAABCDEFGHIJKLMNOP',
            'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature',
            'jdbc:postgresql://user:password@datastore.example:5432/app',
            'owner@example.com',
            '+1 (415) 555-2671',
        )
        for sensitive_value in examples:
            with self.subTest(sensitive_value=sensitive_value):
                _ScriptedHandler.requests = []
                verifier = _FakeVerifier(self.attestation)
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier, api_key=api_key).classify_growth(self._slice_with_content(sensitive_value))
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
                self.assertNotIn(sensitive_value, f"{raised.exception.message} {raised.exception.details}")
                self.assertEqual(verifier.calls, 0)
                self.assertEqual(verifier.slice_calls, 0)
                self.assertEqual(_ScriptedHandler.requests, [])
                self.assertEqual(list(self.cache_dir.glob("*")), [])

    def test_deepseek_key_scan_allows_task_configuration_names(self) -> None:
        examples = (
            "dt.dex-engine.task-event-buffer.flush-interval-ms",
            "dt.dex-engine.activity-task-heartbeat-buffer.max-batch-size",
            "dt.task-scheduler.shutdown-max-wait-ms",
        )
        for source in examples:
            with self.subTest(source=source):
                _ScriptedHandler.requests = []
                _ScriptedHandler.scripted_responses = [
                    (200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))
                ]

                self._client().classify_growth(self._slice_with_content(source))

                self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_ssn_like_pii_is_rejected_before_any_side_effect(self) -> None:
        verifier = _FakeVerifier(self.attestation)
        value = "123-45-6789"

        _ScriptedHandler.scripted_responses = [(200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))] * 3
        with self.assertRaises(AnalyzerError) as raised:
            self._client(verifier).classify_growth(self._slice_with_content(value))

        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
        self.assertEqual(raised.exception.details, {"pattern_id": "ssn"})
        self.assertNotIn(value, f"{raised.exception.message} {raised.exception.details}")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(_ScriptedHandler.requests, [])
        self.assertEqual(list(self.cache_dir.glob("*")), [])

    def test_split_java_string_literal_pii_is_rejected_before_any_side_effect(self) -> None:
        examples = (
            'String email = "owner@" + "example.com";',
            'String ssn = "123-" + "45-6789";',
            'String phone = "+1 (415) " + "555-2671";',
            'String email = "owner\\u0040example.com";',
            '''String email = "owner" + '@' + "example.com";''',
            '''String email = "owner" + '\\u0040' + "example.com";''',
            'String email = "owner@" /*comment*/ + "example.com";',
            'String email = "owner\\100" + "example.com";',
            'String email = """owner@""" + """example.com""";',
        )
        for source in examples:
            with self.subTest(source=source):
                _ScriptedHandler.requests = []
                verifier = _FakeVerifier(self.attestation)
                _ScriptedHandler.scripted_responses = [(200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))] * 3
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier).classify_growth(self._slice_with_content(source))
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
                self.assertEqual(verifier.calls, 0)
                self.assertEqual(_ScriptedHandler.requests, [])

    def test_invalid_ssn_like_numbers_are_not_rejected(self) -> None:
        for value in ("000-12-3456", "666-12-3456", "900-12-3456", "123-00-3456", "123-45-0000", "2026-07-22"):
            with self.subTest(value=value):
                _ScriptedHandler.requests = []
                _ScriptedHandler.scripted_responses = [(200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))]
                self._client().classify_growth(self._slice_with_content(value))
                self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_deeply_nested_json_string_maps_to_controlled_request_error(self) -> None:
        from dosweb.llm.deepseek import _scan_transmitted_request

        nested = '"leaf"'
        for _ in range(1100):
            nested = f'[{nested}]'
        with mock.patch("dosweb.llm.deepseek.build_provider_payload") as build:
            build.return_value.messages = ({"role": "user", "content": nested},)
            with self.assertRaises(AnalyzerError) as raised:
                self._client().classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_REQUEST_INVALID")
        with self.assertRaises(AnalyzerError) as raised:
            _scan_transmitted_request(("[" * 10000 + '"x"' + "]" * 10000).encode(), "")
        self.assertEqual(raised.exception.code, "LLM_REQUEST_INVALID")
        self.assertEqual(_ScriptedHandler.requests, [])

    def test_final_encoded_request_limit_rejects_without_transport(self) -> None:
        from dosweb.llm.deepseek import _MAX_REQUEST_BYTES

        with self.assertRaises(AnalyzerError) as raised:
            self._client()._post_once({"messages": "x" * _MAX_REQUEST_BYTES})

        self.assertEqual(raised.exception.code, "LLM_REQUEST_INVALID")
        self.assertEqual(_ScriptedHandler.requests, [])

    def test_same_key_thread_single_flight_makes_one_provider_request(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        barrier = threading.Barrier(2)
        results: list[object] = []
        failures: list[BaseException] = []

        def classify() -> None:
            try:
                barrier.wait()
                results.append(self._client().classify_growth(self.slice))
            except BaseException as exc:
                failures.append(exc)

        workers = [threading.Thread(target=classify) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        self.assertEqual(failures, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_same_key_waiters_share_deterministic_failure_without_negative_cache(self) -> None:
        invalid = {"is_resource_growth": "yes"}
        _ScriptedHandler.scripted_responses = [(200, self._success(invalid))] * 2
        barrier = threading.Barrier(3)
        errors: list[AnalyzerError] = []

        def classify() -> None:
            barrier.wait()
            try:
                self._client().classify_growth(self.slice)
            except AnalyzerError as exc:
                errors.append(exc)

        workers = [threading.Thread(target=classify) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(5)

        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual([error.code for error in errors], ["LLM_RESPONSE_SCHEMA_INVALID"] * 2)
        self.assertEqual(len(_ScriptedHandler.requests), 2)
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])

        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self.assertEqual(self._client().classify_growth(self.slice).is_resource_growth, "yes")
        self.assertEqual(len(_ScriptedHandler.requests), 3)

    @unittest.skipUnless(hasattr(os, "fork"), "requires os.fork")
    def test_inherited_locked_thread_lock_is_reset_after_fork(self) -> None:
        from dosweb.llm import cache as cache_module

        key, identity = cache_identity(self.config, self.slice)
        inherited = threading.Lock()
        inherited.acquire()
        stripe = int(key[:8], 16) % cache_module._LOCK_STRIPES
        locks = list(cache_module._LOCKS)
        locks[stripe] = inherited
        cache_module._LOCKS = tuple(locks)
        pid = os.fork()
        if pid == 0:
            try:
                cache = ContractCache(self.cache_dir, "test-api-key")
                with cache.single_flight(key):
                    pass
                os._exit(0)
            except BaseException:
                os._exit(1)
        deadline = time.monotonic() + 3
        status = None
        while time.monotonic() < deadline:
            waited, child_status = os.waitpid(pid, os.WNOHANG)
            if waited:
                status = child_status
                break
            time.sleep(0.01)
        inherited.release()
        cache_module._reset_locks_after_fork()
        if status is None:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            self.fail("forked child deadlocked on inherited cache lock")
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)

    def test_same_key_process_single_flight_publishes_once_durably(self) -> None:
        """Two forked cold producers race after a start barrier; one holds flock and publishes."""
        from dosweb.llm.cache import cache_identity

        key, identity = cache_identity(self.config, self.slice)
        context = multiprocessing.get_context("spawn")
        ready, produced = context.Queue(), context.Queue()
        start = context.Event()
        workers = [context.Process(target=_process_cache_producer, args=(str(self.cache_dir), key, identity, ready, start, produced)) for _ in range(2)]
        for worker in workers:
            worker.start()
        for _ in workers:
            self.assertTrue(ready.get(timeout=5))
        start.set()
        for worker in workers:
            worker.join(10)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual([produced.get(timeout=1)], [True])
        with self.assertRaises(__import__("queue").Empty):
            produced.get_nowait()
        self.assertEqual(ContractCache(self.cache_dir, "test-api-key").get(key, identity, frozenset({"fact:key", "fact:put"})), validate_growth_contract(VALID_CONTRACT))
        self.assertEqual(len(list(self.cache_dir.glob("*.json"))), 1)

    def test_concurrent_private_hierarchy_creation_treats_racing_creator_as_success(self) -> None:
        from dosweb.llm.cache import _create_private_hierarchy

        target = self.cache_dir.parent / "concurrent-cache"
        mkdir_barrier = threading.Barrier(2)
        original_mkdir = os.mkdir
        results: list[bool] = []

        def racing_mkdir(path: object, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
            if path == target.name:
                mkdir_barrier.wait(timeout=5)
            original_mkdir(path, mode, dir_fd=dir_fd)

        def create_and_release() -> None:
            descriptor = _create_private_hierarchy(target)
            if descriptor is None:
                results.append(False)
                return
            try:
                info = os.fstat(descriptor)
                results.append(
                    stat.S_ISDIR(info.st_mode)
                    and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o700
                )
            finally:
                os.close(descriptor)

        with mock.patch("dosweb.llm.cache.os.mkdir", side_effect=racing_mkdir):
            workers = [threading.Thread(target=create_and_release) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(5)

        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual(results, [True, True])
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)

    def test_capacity_reservation_pins_auth_publication_directory_across_anchor_substitution(self) -> None:
        base = self.cache_dir.parent
        foreign = base / "foreign-capacity"
        foreign.mkdir(mode=0o755)
        anchor = foreign / "owned-anchor"
        anchor.mkdir(mode=0o755)
        cache_dir = anchor / "cache"
        detached_anchor = foreign / "detached-anchor"
        redirect_anchor = base / "redirect-capacity"
        redirect_cache = redirect_anchor / "cache"
        redirect_cache.mkdir(parents=True, mode=0o700)
        key = "3" * 64
        cache = ContractCache(cache_dir, "test-api-key")
        baseline_fds = len(os.listdir("/proc/self/fd"))

        with cache.capacity_reservation(key, entry_prefix="auth-"):
            self.assertTrue((cache_dir / ".capacity.lock").is_file())
            anchor.rename(detached_anchor)
            anchor.symlink_to(redirect_anchor, target_is_directory=True)
            self.assertTrue(
                cache.put_auth_record(
                    key,
                    {"kind": "auth"},
                    {
                        "auth_context": "unknown",
                        "evidence_ids": [],
                        "assumptions": [],
                        "confidence": "low",
                    },
                    "{}",
                )
            )

        original_cache = detached_anchor / "cache"
        self.assertTrue((original_cache / ".capacity.lock").is_file())
        self.assertTrue((original_cache / f"auth-{key}.json").is_file())
        self.assertFalse((redirect_cache / f"auth-{key}.json").exists())
        self.assertEqual(list(redirect_cache.iterdir()), [])
        self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_single_flight_pins_growth_publication_directory_across_anchor_substitution(self) -> None:
        base = self.cache_dir.parent
        foreign = base / "foreign-stripe"
        foreign.mkdir(mode=0o755)
        anchor = foreign / "owned-anchor"
        anchor.mkdir(mode=0o755)
        cache_dir = anchor / "cache"
        detached_anchor = foreign / "detached-anchor"
        redirect_anchor = base / "redirect-stripe"
        redirect_cache = redirect_anchor / "cache"
        redirect_cache.mkdir(parents=True, mode=0o700)
        key, identity = cache_identity(
            replace(self.config, cache_dir=cache_dir),
            self.slice,
        )
        cache = ContractCache(cache_dir, "test-api-key")
        audit = {
            "method": identity["request_method"],
            "url": identity["request_url"],
            "provider": identity["provider"],
            "protocol": identity["protocol"],
            "requested_model": identity["model"],
            "actual_model": identity["model"],
            "provider_request_id_digest": cache.provider_request_id_digest("fixture"),
            "slice_content_hash": identity["slice_content_hash"],
            "allow_remote_llm": identity["allow_remote_llm"],
            "public_source_url": identity["public_source_url"],
            "source_commit_sha": identity["source_commit_sha"],
            "verified_public": identity["verified_public"],
            "verified_clean_checkout": identity["verified_clean_checkout"],
        }
        baseline_fds = len(os.listdir("/proc/self/fd"))

        with cache.single_flight(key):
            stripe = int(key[:8], 16) % 64
            self.assertTrue((cache_dir / f".stripe-{stripe:02d}.lock").is_file())
            anchor.rename(detached_anchor)
            anchor.symlink_to(redirect_anchor, target_is_directory=True)
            self.assertTrue(
                cache.put(
                    key,
                    identity,
                    validate_growth_contract(VALID_CONTRACT),
                    audit,
                    raw_response="{}",
                )
            )

        original_cache = detached_anchor / "cache"
        self.assertTrue((original_cache / f"{key}.json").is_file())
        self.assertFalse((redirect_cache / f"{key}.json").exists())
        self.assertEqual(list(redirect_cache.iterdir()), [])
        self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_nested_default_cache_path_supports_process_reuse(self) -> None:
        nested = self.cache_dir.parent / "output" / "cache" / "llm"
        key, identity = cache_identity(replace(self.config, cache_dir=nested), self.slice)
        cache = ContractCache(nested, "test-api-key")
        with cache.single_flight(key):
            self.assertTrue(cache.put(key, identity, validate_growth_contract(VALID_CONTRACT), {
                "method": identity["request_method"], "url": identity["request_url"], "provider": identity["provider"], "protocol": "responses-v1",
                "requested_model": "grok-4.6", "actual_model": "grok-4.6",
                "provider_request_id_digest": cache.provider_request_id_digest("fixture"), "slice_content_hash": identity["slice_content_hash"],
                "allow_remote_llm": True, "public_source_url": identity["public_source_url"],
                "source_commit_sha": identity["source_commit_sha"], "verified_public": identity["verified_public"], "verified_clean_checkout": identity["verified_clean_checkout"],
            }))
        self.assertEqual(ContractCache(nested, "test-api-key").get(key, identity, frozenset({"fact:key", "fact:put"})), validate_growth_contract(VALID_CONTRACT))
        self.assertEqual(stat.S_IMODE((nested.parent.parent).stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(nested.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(nested.stat().st_mode), 0o700)

    def test_cache_supports_more_than_sixty_four_valid_facts(self) -> None:
        facts = tuple(StaticFact(f"fact:f{index}", "flow", "excerpt:1", "source") for index in range(65)) + (
            StaticFact("fact:sink", "container_write", "excerpt:1", "sink"),
            StaticFact("fact:target", "attacker_target", "excerpt:1", "source", "fact:f0", "key"),
        )
        payload = replace(self.slice.payload, static_facts=facts, cfg_summary=CfgSummary(("path:1",), ("in_handler",), ("fact:f0",)))
        slice_ = BoundedSlice("slice:many-facts", payload)
        contract = {**PROVIDER_CONTRACT, "attacker_evidence_ids": ["fact:1"], "required_static_evidence": ["fact:1", "fact:66"]}
        _ScriptedHandler.scripted_responses = [(200, self._success(contract))]
        first = self._client().classify_growth(slice_)
        second = self._client().classify_growth(slice_)
        self.assertEqual(first, second)
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_cross_stripe_capacity_reservation_allows_only_one_provider_call(self) -> None:
        from dosweb.llm import cache as cache_module

        first_key, _ = cache_identity(self.config, self.slice)
        second_slice = BoundedSlice("slice:other", replace(self.slice.payload, growth_id="growth:other"))
        second_key, _ = cache_identity(self.config, second_slice)
        suffix = 0
        while int(second_key[:8], 16) % cache_module._LOCK_STRIPES == int(first_key[:8], 16) % cache_module._LOCK_STRIPES:
            suffix += 1
            second_slice = BoundedSlice("slice:other", replace(self.slice.payload, growth_id=f"growth:other{suffix}"))
            second_key, _ = cache_identity(self.config, second_slice)

        entered = threading.Event()
        release = threading.Event()
        calls: list[str] = []
        calls_lock = threading.Lock()

        class BlockingTransport:
            def post(inner_self, endpoint: str, payload: bytes, headers: dict[str, str], timeout: int) -> str:
                with calls_lock:
                    calls.append(endpoint)
                    entered.set()
                release.wait(5)
                return json.dumps(self._success(PROVIDER_CONTRACT))

        results: list[object] = []
        failures: list[AnalyzerError] = []

        def classify(slice_: BoundedSlice) -> None:
            client = DeepSeekClient(replace(self.config, cache_dir=self.cache_dir), verifier=_FakeVerifier(self.attestation), transport=BlockingTransport(), sleep=lambda _: None, jitter=lambda: 0)
            try:
                results.append(client.classify_growth(slice_))
            except AnalyzerError as exc:
                failures.append(exc)

        with mock.patch.object(cache_module, "_MAX_CACHE_ENTRIES", 1):
            first = threading.Thread(target=classify, args=(self.slice,))
            second = threading.Thread(target=classify, args=(second_slice,))
            first.start()
            self.assertTrue(entered.wait(5))
            second.start()
            time.sleep(0.1)
            self.assertEqual(len(calls), 1)
            release.set()
            first.join(5)
            second.join(5)

        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(len(results), 1)
        self.assertEqual([failure.code for failure in failures], ["LLM_CACHE_CAPACITY_EXHAUSTED"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(list(self.cache_dir.glob("*.json"))), 1)

    def test_crash_leaked_cache_temporaries_count_toward_byte_capacity(self) -> None:
        from dosweb.llm import cache as cache_module

        self.cache_dir.mkdir(mode=0o700)
        key, _ = cache_identity(self.config, self.slice)
        temporary = self.cache_dir / f".{key}.{'0' * 32}.tmp"
        temporary.write_bytes(b"x" * 17)
        temporary.chmod(0o600)
        with mock.patch.object(cache_module, "_MAX_CACHE_TOTAL_BYTES", 16):
            with self.assertRaises(AnalyzerError) as raised:
                ContractCache(self.cache_dir, "test-api-key").require_capacity(key)
        self.assertEqual(raised.exception.code, "LLM_CACHE_CAPACITY_EXHAUSTED")
        self.assertTrue(temporary.exists())

    def test_cache_capacity_exhaustion_prevents_provider_request_without_deletion(self) -> None:
        from dosweb.llm import cache as cache_module
        self.cache_dir.mkdir(mode=0o700)
        existing = self.cache_dir / ("0" * 64 + ".json")
        existing.write_bytes(b"preserve-me")
        existing.chmod(0o600)
        before = existing.read_bytes()
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        with mock.patch.object(cache_module, "_MAX_CACHE_ENTRIES", 1):
            with self.assertRaises(AnalyzerError) as raised:
                self._client().classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_CACHE_CAPACITY_EXHAUSTED")
        self.assertEqual(_ScriptedHandler.requests, [])
        self.assertEqual(existing.read_bytes(), before)

    def test_incompatible_authenticated_entry_still_checks_capacity_before_provider(self) -> None:
        from dosweb.llm import cache as cache_module

        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client().classify_growth(self.slice)
        cache_file = next(self.cache_dir.glob("*.json"))
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        entry["contract"]["required_static_evidence"] = ["fact:invented"]
        from dosweb.artifacts.identifiers import sha256_canonical_json
        entry["contract_hash"] = sha256_canonical_json(entry["contract"])
        stable = {name: entry[name] for name in entry if name not in {"entry_hash", "entry_hmac"}}
        entry["entry_hash"] = sha256_canonical_json(stable)
        unsigned = {name: entry[name] for name in entry if name != "entry_hmac"}
        entry["entry_hmac"] = ContractCache(self.cache_dir, "test-api-key")._entry_hmac(unsigned)
        cache_file.write_text(json.dumps(entry), encoding="utf-8")
        _ScriptedHandler.requests = []
        with mock.patch.object(cache_module, "_MAX_CACHE_ENTRIES", 1):
            with self.assertRaises(AnalyzerError) as raised:
                self._client().classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_CACHE_CAPACITY_EXHAUSTED")
        self.assertEqual(_ScriptedHandler.requests, [])

    def test_capacity_to_stripe_lock_order_is_rejected_without_deadlock(self) -> None:
        key, _ = cache_identity(self.config, self.slice)
        cache = ContractCache(self.cache_dir, "test-api-key")
        with cache.capacity_reservation(key):
            with self.assertRaises(AnalyzerError) as raised:
                with cache.single_flight(key):
                    pass
        self.assertEqual(raised.exception.code, "LLM_CACHE_LOCK_FAILED")

    def test_cache_directory_transaction_releases_once_after_context_exception(self) -> None:
        from dosweb.llm import cache as cache_module

        for kind in ("capacity", "stripe"):
            with self.subTest(kind=kind):
                cache_dir = self.cache_dir.parent / f"exception-{kind}"
                cache = ContractCache(cache_dir, "test-api-key")
                key = hashlib.sha256(kind.encode()).hexdigest()
                baseline_fds = len(os.listdir("/proc/self/fd"))
                captured_state = None
                with self.assertRaisesRegex(RuntimeError, "injected transaction failure"):
                    context = (
                        cache.capacity_reservation(key)
                        if kind == "capacity"
                        else cache.single_flight(key)
                    )
                    with context:
                        states = cache_module._ACTIVE_RESERVATIONS.directories
                        captured_state = next(iter(states.values()))
                        raise RuntimeError("injected transaction failure")
                self.assertIsNotNone(captured_state)
                self.assertEqual(captured_state.descriptor, -1)
                self.assertEqual(
                    getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {}),
                    {},
                )
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_cache_stripes_and_memory_are_globally_bounded(self) -> None:
        from dosweb.llm import cache as cache_module
        cache = ContractCache(self.cache_dir, "test-api-key")
        for index in range(256):
            key = hashlib.sha256(str(index).encode()).hexdigest()
            with cache.single_flight(key):
                pass
        self.assertLessEqual(len(list(self.cache_dir.glob(".stripe-*.lock"))), cache_module._LOCK_STRIPES)
        self.assertEqual(len(cache_module._LOCKS), cache_module._LOCK_STRIPES)
        self.assertFalse(hasattr(cache, "_memory"))

    def test_cache_publication_replace_failure_is_controlled(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        with mock.patch("dosweb.llm.cache.os.link", side_effect=OSError("publication failed")):
            with self.assertRaises(AnalyzerError) as raised:
                self._client().classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_CACHE_WRITE_FAILED")
        self.assertEqual(len(_ScriptedHandler.requests), 1)
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])

    @unittest.skipUnless(hasattr(os, "fork"), "requires os.fork")
    def test_at_fork_child_closes_inherited_real_flock_descriptor(self) -> None:
        from dosweb.llm import cache as cache_module
        key, _ = cache_identity(self.config, self.slice)
        cache = ContractCache(self.cache_dir, "test-api-key")
        with cache.single_flight(key):
            descriptor = next(iter(cache_module._ACTIVE_FLOCK_FDS))
            directory_descriptor = next(
                iter(cache_module._ACTIVE_RESERVATIONS.directories.values())
            ).descriptor
            pid = os.fork()
            if pid == 0:
                try:
                    os.fstat(descriptor)
                except OSError:
                    try:
                        os.fstat(directory_descriptor)
                    except OSError:
                        os._exit(0)
                os._exit(1)
            _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)

    def test_live_contract_rejects_fabricated_static_fact_references_without_caching(self) -> None:
        fabricated = {**PROVIDER_CONTRACT, "attacker_evidence_ids": ["fact:invented"]}
        _ScriptedHandler.scripted_responses = [(200, self._success(fabricated))] * 2

        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SCHEMA_INVALID")
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])

    def test_cache_with_fabricated_static_fact_reference_is_missed_and_refreshed_live(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client().classify_growth(self.slice)
        cache_file = next(self.cache_dir.glob("*.json"))
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        entry["contract"]["required_static_evidence"] = ["fact:invented"]
        from dosweb.artifacts.identifiers import sha256_canonical_json
        entry["contract_hash"] = sha256_canonical_json(entry["contract"])
        stable = {name: entry[name] for name in entry if name not in {"entry_hash", "entry_hmac"}}
        entry["entry_hash"] = sha256_canonical_json(stable)
        unsigned = {name: entry[name] for name in entry if name != "entry_hmac"}
        entry["entry_hmac"] = ContractCache(self.cache_dir, "test-api-key")._entry_hmac(unsigned)
        cache_file.write_text(json.dumps(entry), encoding="utf-8")
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        refreshed = self._client().classify_growth(self.slice)

        self.assertEqual(refreshed, validate_growth_contract(VALID_CONTRACT))
        self.assertEqual(len(_ScriptedHandler.requests), 2)
        self.assertEqual(json.loads(cache_file.read_text(encoding="utf-8"))["contract"]["required_static_evidence"], ["fact:invented"])

    def test_nested_contract_json_is_schema_invalid_without_caching(self) -> None:
        nested: object = PROVIDER_CONTRACT
        for _ in range(17):
            nested = [nested]
        _ScriptedHandler.scripted_responses = [(200, self._success(nested))] * 2

        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SCHEMA_INVALID")
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])

    def test_contract_json_rejects_duplicate_keys_and_nonfinite_values(self) -> None:
        for content in (
            '{"is_resource_growth":"yes","is_resource_growth":"no"}',
            '{"is_resource_growth":NaN}',
        ):
            with self.subTest(content=content):
                with self.assertRaises(AnalyzerError) as raised:
                    parse_growth_contract_json(content)
                self.assertEqual(raised.exception.code, "LLM_RESPONSE_SCHEMA_INVALID")

    def test_failed_response_is_not_written_as_success_cache(self) -> None:
        invalid = (200, self._success({"is_resource_growth": "yes"}))
        _ScriptedHandler.scripted_responses = [invalid, invalid]

        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SCHEMA_INVALID")
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])

    def test_cache_identity_persists_only_slice_hash_and_provenance(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client().classify_growth(self.slice)
        serialized = next(self.cache_dir.glob("*.json")).read_text(encoding="utf-8")
        entry = json.loads(serialized)
        identity = entry["identity"]
        self.assertEqual(identity["prompt_version"], "growth-contract-v9")
        self.assertIn("slice_content_hash", identity)
        self.assertNotIn("normalized_slice", identity)
        identity_serialized = json.dumps(identity, sort_keys=True)
        for value in ("fact:key", "fact:put", "entry:1", "growth:1", "path:1"):
            self.assertNotIn(value, identity_serialized)

    def test_cache_and_error_text_do_not_contain_api_key_or_authorization(self) -> None:
        secret = "sk-secret-value"
        client = self._client(api_key=secret)
        unsafe_response = {**self._success({"is_resource_growth": "yes", "note": secret}), "Authorization": f"Bearer {secret}"}
        _ScriptedHandler.scripted_responses = [(200, unsafe_response)] * 2

        with self.assertRaises(AnalyzerError) as raised:
            client.classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SENSITIVE_CONTENT")
        error_text = f"{raised.exception.message} {raised.exception.details}"
        self.assertNotIn(secret, error_text)
        self.assertNotIn("Bearer", error_text)
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])

    def test_sensitive_envelope_metadata_is_never_cached_or_audited_for_growth_or_auth(self) -> None:
        secret = "sk-envelope-secret"
        growth_envelope = {**self._success(PROVIDER_CONTRACT), "reasoning": {"metadata": f"Bearer {secret}"}}
        _ScriptedHandler.scripted_responses = [(200, growth_envelope)] * 2
        growth_client = self._client(api_key=secret)

        with self.assertRaises(AnalyzerError) as raised:
            growth_client.classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SENSITIVE_CONTENT")
        self.assertNotIn(secret, f"{raised.exception.message} {raised.exception.details}")
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])
        self.assertIsNone(growth_client.last_audit())

        auth_contract = {"auth_context": "unknown", "evidence_ids": [], "assumptions": [], "confidence": "low"}
        auth_envelope = {**self._success(auth_contract), "metadata": {"api_key_echo": secret}}
        _ScriptedHandler.scripted_responses = [(200, auth_envelope)] * 2
        auth_client = self._client(api_key=secret)

        with self.assertRaises(AnalyzerError) as raised:
            auth_client.classify_auth("entry:1", ())
        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SENSITIVE_CONTENT")
        self.assertNotIn(secret, f"{raised.exception.message} {raised.exception.details}")
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])
        self.assertIsNone(auth_client.last_audit())

    def test_llm_audit_record_rejects_bearer_or_key_shaped_raw_envelope(self) -> None:
        for raw in ('{"metadata":"Bearer synthetic-token-value"}', '{"metadata":"sk-synthetic-token"}'):
            with self.subTest(raw=raw):
                with self.assertRaises(AnalyzerError):
                    LlmAuditRecord("auth", "", "{}", {}, raw, {}, {}, {}, False)

    def test_sensitive_model_text_is_not_cached(self) -> None:
        secret = "sk-response-secret"
        payload = {**PROVIDER_CONTRACT, "resource_effect": f"Stores {secret} as a map key."}
        _ScriptedHandler.scripted_responses = [(200, self._success(payload))] * 2

        with self.assertRaises(AnalyzerError) as raised:
            self._client(api_key="another-secret").classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SENSITIVE_CONTENT")
        self.assertEqual(list(self.cache_dir.glob("*.json")), [])

    def test_unsafe_external_provider_endpoint_is_rejected_before_verifier_or_network(self) -> None:
        verifier = _FakeVerifier(self.attestation)

        with self.assertRaises(AnalyzerError) as raised:
            self._client(verifier, base_url="https://evil.example/").classify_growth(self.slice)

        self.assertEqual(raised.exception.code, "CONFIG_UNSAFE_LLM_ENDPOINT")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(_ScriptedHandler.requests, [])

    def test_verifier_failure_does_not_prevent_deepseek_request(self) -> None:
        verifier = _FakeVerifier(error=AnalyzerError("CONFIG_PUBLIC_SOURCE_UNVERIFIED", "not public"))
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        result = self._client(verifier).classify_growth(self.slice)

        # Git commit provenance is optional metadata, not a gate: the verifier
        # is no longer consulted on the remote path.
        self.assertEqual(result.is_resource_growth, "yes")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_attestation_mismatch_does_not_prevent_deepseek_request(self) -> None:
        mismatched = PublicSourceAttestation(
            public_source_url="https://github.com/other/repository",
            source_commit_sha="a" * 40,
            verified_public=True,
            verified_clean_checkout=True,
        )
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        result = self._client(_FakeVerifier(mismatched)).classify_growth(self.slice)

        self.assertEqual(result.is_resource_growth, "yes")
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_short_sha_falls_back_to_local_source_tree(self) -> None:
        verifier = _FakeVerifier(self.attestation)
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]

        result = self._client(verifier, source_commit_sha="a1b2c3d4").classify_growth(self.slice)

        # A non-40-hex SHA is treated as local-source-tree semantics, not a hard failure.
        self.assertEqual(result.is_resource_growth, "yes")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_secret_scan_blocks_credentials_before_verifier_cache_or_provider(self) -> None:
        secret = "ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
        content = f"String token = \"{secret}\";\n"
        bad_slice = BoundedSlice(
            "slice:secret",
            BoundedSlicePayload(
                "entry:secret", "growth:secret",
                (SourceExcerpt("excerpt:secret", "Example.java", 1, 1, content, "a" * 64, hashlib.sha256(content.encode()).hexdigest()),),
                (StaticFact("fact:secret", "flow", "excerpt:secret", "source"),),
                CfgSummary(("path:secret",), ("in_handler",), ("fact:secret",)),
                (RegistrationFact("spring_mvc", "excerpt:secret"),), (),
            ),
        )
        verifier = _FakeVerifier(self.attestation)
        with self.assertRaises(AnalyzerError) as raised:
            self._client(verifier).classify_growth(bad_slice)
        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
        self.assertNotIn(secret, f"{raised.exception.message} {raised.exception.details}")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(_ScriptedHandler.requests, [])

    def test_secret_scan_blocks_credential_assignment_syntaxes(self) -> None:
        examples = (
            'password="hunter2-value"',
            "token:'secretvalue-long'",
            'api_key = "long-secret-value"',
            '"token":"json-secret-value"',
            'String password = "java-secret-value"',
            'Authorization: "Bearer quoted-token-value"',
            'password="example-production-secret"',
            'token=${API_KEY}',
            '"token":"json-secret-value"',
            '"password":"json-password-value"',
            '"api_key":"json-api-key-value"',
            '"authorization":"json-authorization-value"',
            'access_key = raw-access-value',
            'String client_secret = "java-client-secret-value"',
            'api-key: hyphen-api-key-value',
            'access-key = hyphen-access-key-value',
            'client-secret: hyphen-client-secret-value',
            'refresh-token: hyphen-refresh-token-value',
            'refresh_token: underscore-refresh-token-value',
            '"refresh_token":"quoted-refresh-token-value"',
        )
        for assignment in examples:
            with self.subTest(assignment=assignment):
                content = f"{assignment};\n"
                slice_ = BoundedSlice(
                    "slice:assignment",
                    BoundedSlicePayload(
                        "entry:assignment", "growth:assignment",
                        (SourceExcerpt("excerpt:assignment", "Example.java", 1, 1, content, "a" * 64, hashlib.sha256(content.encode()).hexdigest()),),
                        (StaticFact("fact:assignment", "flow", "excerpt:assignment", "source"),),
                        CfgSummary(("path:assignment",), ("in_handler",), ("fact:assignment",)),
                        (RegistrationFact("spring_mvc", "excerpt:assignment"),), (),
                    ),
                )
                verifier = _FakeVerifier(self.attestation)
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier).classify_growth(slice_)
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
                self.assertEqual(verifier.calls, 0)
                self.assertEqual(_ScriptedHandler.requests, [])

    def test_secret_scan_blocks_credential_assignments_inside_comments(self) -> None:
        for source in (
            '// password = "hunter2-value"',
            '/* api_key: production-secret-value */',
        ):
            with self.subTest(source=source):
                verifier = _FakeVerifier(self.attestation)
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier).classify_growth(self._slice_with_content(source))
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
                self.assertEqual(verifier.calls, 0)
                self.assertEqual(_ScriptedHandler.requests, [])

    def test_secret_scan_blocks_credential_mutator_calls(self) -> None:
        for source in (
            'client.setPassword("hunter2-value");',
            'client.setApiKey("production-key-value");',
            'headers.add("X-Api-Key", "production-key-value");',
            'headers.add("Authorization", "opaque-credential-value");',
            'credentials.put("password", "hunter2-value");',
            'client.set("client_secret", "production-secret-value");',
        ):
            with self.subTest(source=source):
                verifier = _FakeVerifier(self.attestation)
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier).classify_growth(self._slice_with_content(source))
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
                self.assertEqual(verifier.calls, 0)
                self.assertEqual(_ScriptedHandler.requests, [])

    def test_secret_scan_blocks_sensitive_identifier_with_trailing_qualifier(self) -> None:
        for source in (
            'String feature_password_backup = "hunter2";',
            'String logging_token_value = "ordinary-secret";',
            'String apiKeyBackup = "opaque-production-credential";',
            'String private_key_value = "opaque-production-credential";',
            'String access-key-copy = "opaque-production-credential";',
        ):
            with self.subTest(source=source):
                verifier = _FakeVerifier(self.attestation)
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier).classify_growth(self._slice_with_content(source))
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
                self.assertEqual(verifier.calls, 0)
                self.assertEqual(_ScriptedHandler.requests, [])

    def test_secret_scan_allows_non_deny_hyphenated_keys(self) -> None:
        for assignment in ("feature-password = safe", "logging-token: safe", "client-feature: safe"):
            with self.subTest(assignment=assignment):
                content = f"{assignment}\n"
                slice_ = BoundedSlice(
                    "slice:non-deny",
                    BoundedSlicePayload(
                        "entry:non-deny", "growth:non-deny",
                        (SourceExcerpt("excerpt:non-deny", "Example.java", 1, 1, content, "a" * 64, hashlib.sha256(content.encode()).hexdigest()),),
                        (
                            StaticFact("fact:non-deny", "flow", "excerpt:non-deny", "source"),
                            StaticFact("fact:sink", "container_write", "excerpt:non-deny", "sink"),
                            StaticFact("fact:target", "attacker_target", "excerpt:non-deny", "source", "fact:non-deny", "key"),
                        ),
                        CfgSummary(("path:non-deny",), ("in_handler",), ("fact:non-deny",)),
                        (RegistrationFact("spring_mvc", "excerpt:non-deny"),), (),
                    ),
                )
                _ScriptedHandler.requests = []
                contract = {**PROVIDER_CONTRACT, "attacker_evidence_ids": ["fact:1"], "required_static_evidence": ["fact:1", "fact:2"]}
                _ScriptedHandler.scripted_responses = [(200, self._success(contract))]
                self._client().classify_growth(slice_)
                self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_authorized_provider_model_alias_is_accepted_but_other_mismatches_fail(self) -> None:
        client = self._client(model="grok-4.6", base_url="https://rightapi.ai/grok/v1/")
        reply = ProviderReply(
            json.dumps({
                "id": "req_alias_1",
                "model": "grok-4.6-build",
                "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{}"}]}],
            }),
            {},
        )
        content, actual_model, request_id = client._response_content(reply)
        self.assertEqual(content, "{}")
        self.assertEqual(actual_model, "grok-4.6-build")
        self.assertEqual(request_id, "req_alias_1")

    def test_authorized_model_alias_is_cache_authenticated_and_replayable(self) -> None:
        response = {
            "id": "req_alias_cache",
            "model": "grok-4.6-build",
            "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(PROVIDER_CONTRACT)}]}],
        }
        _ScriptedHandler.scripted_responses = [(200, response)]
        client = self._client(model="grok-4.6")
        first = client.classify_growth(self.slice)
        self.assertEqual(first.growth_kind, "container_growth")
        cache_entry = json.loads(next(self.cache_dir.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(cache_entry["request_audit"]["requested_model"], "grok-4.6")
        self.assertEqual(cache_entry["request_audit"]["actual_model"], "grok-4.6-build")
        request_count = len(_ScriptedHandler.requests)
        replay_client = self._client(model="grok-4.6")
        second = replay_client.classify_growth(self.slice)
        self.assertEqual(second.to_dict(), first.to_dict())
        self.assertEqual(len(_ScriptedHandler.requests), request_count)
        self.assertIsNotNone(replay_client.last_audit())
        self.assertEqual(
            replay_client.last_audit().settings["actual_model"],
            "grok-4.6-build",
        )

    def test_response_requires_matching_model_and_persists_only_request_id_digest(self) -> None:
        bad = {"model": "not-allowed-model", "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(PROVIDER_CONTRACT)}]}]}
        _ScriptedHandler.scripted_responses = [(200, bad)]
        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_RESPONSE_INVALID")

        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        self._client().classify_growth(self.slice)
        entry = json.loads(next(self.cache_dir.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(entry["request_audit"]["requested_model"], "grok-4.6")
        self.assertEqual(entry["request_audit"]["actual_model"], "grok-4.6")
        digest = entry["request_audit"]["provider_request_id_digest"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        serialized = json.dumps(entry, sort_keys=True)
        # Private cache v6 retains the exact bounded provider body for audit replay.
        self.assertIn("req_fixture_1", serialized)
        self.assertIn("raw_response_hash", entry)
        self.assertNotIn("provider_request_id\"", serialized)
        self.assertNotIn("choices", entry)
        self.assertEqual(digest, ContractCache(self.cache_dir, "test-api-key").provider_request_id_digest("req_fixture_1"))
        self.assertNotEqual(digest, ContractCache(self.cache_dir, "different-key").provider_request_id_digest("req_fixture_1"))

    def test_remote_gate_rejects_missing_authorization_but_provenance_is_optional(self) -> None:
        unauthorized = self.config.__class__(**{**self.config.__dict__, "allow_remote_llm": False})
        with self.assertRaises(AnalyzerError) as raised:
            DeepSeekClient(
                unauthorized,
                verifier=_FakeVerifier(self.attestation),
                transport=_LoopbackTransport(),
                sleep=lambda _: None,
                jitter=lambda: 0,
            ).classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "CONFIG_REMOTE_LLM_NOT_AUTHORIZED")
        self.assertEqual(_ScriptedHandler.requests, [])

        # Missing/irregular git-commit provenance is optional and no longer blocks
        # the remote path (local source-tree semantics).
        optional_provenance_configs = (
            self.config.__class__(**{**self.config.__dict__, "public_source_url": None}),
            self.config.__class__(**{**self.config.__dict__, "public_source_url": "https://example.com/repo"}),
            self.config.__class__(**{**self.config.__dict__, "source_commit_sha": ""}),
        )
        for config in optional_provenance_configs:
            with self.subTest(config=config):
                _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
                _ScriptedHandler.requests = []
                result = DeepSeekClient(
                    config,
                    verifier=_FakeVerifier(self.attestation),
                    transport=_LoopbackTransport(),
                    sleep=lambda _: None,
                    jitter=lambda: 0,
                ).classify_growth(self.slice)
                self.assertEqual(result.is_resource_growth, "yes")
                self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_empty_api_key_is_rejected_before_verifier_or_network(self) -> None:
        verifier = _FakeVerifier(self.attestation)
        for api_key in ("", "   "):
            with self.subTest(api_key=repr(api_key)):
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier, api_key=api_key).classify_growth(self.slice)
                self.assertEqual(raised.exception.code, "CONFIG_MISSING_DEEPSEEK_API_KEY")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(_ScriptedHandler.requests, [])

    def test_runtime_config_rejects_max_retries_above_the_explicit_limit(self) -> None:
        from dosweb.config import MAX_LLM_RETRIES

        verifier = _FakeVerifier(self.attestation)
        with self.assertRaises(AnalyzerError) as raised:
            self._client(verifier, max_retries=MAX_LLM_RETRIES + 1).classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_VALUE")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(_ScriptedHandler.requests, [])

    def test_injected_transport_oserror_retries_and_exhausts(self) -> None:
        transport = mock.Mock()
        transport.post.side_effect = ConnectionResetError(errno.ECONNRESET, "connection reset")
        client = self._client(max_retries=3)
        client._transport = transport
        with self.assertRaises(AnalyzerError) as raised:
            client.classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_RETRIES_EXHAUSTED")
        self.assertEqual(transport.post.call_count, 3)

    def test_one_monotonic_deadline_covers_connect_and_response_read(self) -> None:
        clock_values = iter((0.0, 0.2, 0.8, 1.1))
        clock = lambda: next(clock_values, 1.1)
        class SlowResponse:
            headers: dict[str, str] = {}
            status = 200
            def getcode(self) -> int: return 200
            def read(self, size: int) -> bytes:
                return json.dumps(self._payload).encode()
            def __enter__(self): return self
            def __exit__(self, *args: object) -> None: return None
            _payload = DeepSeekClientTests._success(PROVIDER_CONTRACT)
        client = DeepSeekClient(replace(self.config, base_url="https://rightapi.ai/grok/v1/", max_retries=1), verifier=_FakeVerifier(self.attestation), sleep=lambda _: None, jitter=lambda: 0, monotonic=clock)
        client._opener = mock.Mock()
        client._opener.open.return_value = SlowResponse()
        with self.assertRaises(AnalyzerError) as raised:
            client.classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_RETRIES_EXHAUSTED")
        self.assertLess(client._opener.open.call_args.kwargs["timeout"], self.config.timeout_seconds)

    def test_provider_slow_drip_body_obeys_absolute_deadline(self) -> None:
        from dosweb.llm.deepseek import _read_bounded_bytes

        chunks = [b"12345678"] * 16
        clock_values = iter((0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.1))
        clock = lambda: next(clock_values, 1.1)

        class SlowDripResponse:
            headers: dict[str, str] = {}
            def __init__(self) -> None: self.calls: list[int] = []
            def read(self, size: int) -> bytes:
                self.calls.append(size)
                return chunks.pop(0) if chunks else b""

        response = SlowDripResponse()
        with self.assertRaises(AnalyzerError) as raised:
            _read_bounded_bytes(response, 1024, deadline=1.0, monotonic=clock)

        self.assertEqual(raised.exception.code, "LLM_NETWORK_RETRYABLE")
        self.assertGreater(len(response.calls), 1)
        self.assertTrue(all(size <= 4096 for size in response.calls))

    def test_permanent_response_body_oserror_fails_without_retry(self) -> None:
        class InvalidResponse:
            headers: dict[str, str] = {}
            status = 200
            def getcode(self) -> int: return 200
            def read(self, size: int) -> bytes: raise OSError(errno.EINVAL, "permanent read failure")
            def __enter__(self): return self
            def __exit__(self, *args: object) -> None: return None

        client = DeepSeekClient(replace(self.config, base_url="https://rightapi.ai/grok/v1/", max_retries=3), verifier=_FakeVerifier(self.attestation), sleep=lambda _: None, jitter=lambda: 0)
        client._opener = mock.Mock()
        client._opener.open.return_value = InvalidResponse()
        with self.assertRaises(AnalyzerError) as raised:
            client.classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_NETWORK_FAILED")
        self.assertEqual(client._opener.open.call_count, 1)

    def test_response_body_timeout_retries_and_exhausts(self) -> None:
        class TimeoutResponse:
            headers: dict[str, str] = {}
            status = 200
            def getcode(self) -> int: return 200
            def read(self, size: int) -> bytes: raise TimeoutError("read timed out")
            def __enter__(self): return self
            def __exit__(self, *args: object) -> None: return None

        client = self._client(max_retries=3, base_url="https://rightapi.ai/grok/v1/")
        client._transport = None
        client._opener = mock.Mock()
        client._opener.open.return_value = TimeoutResponse()
        with self.assertRaises(AnalyzerError) as raised:
            client.classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_RETRIES_EXHAUSTED")
        self.assertEqual(client._opener.open.call_count, 3)

    def test_exact_final_request_scan_covers_all_fields_before_side_effects(self) -> None:
        verifier = _FakeVerifier(self.attestation)
        client = self._client(verifier, model="SERVICE_TOKEN=transmitted-secret")
        with mock.patch("dosweb.llm.deepseek.SUPPORTED_MODELS", frozenset({"SERVICE_TOKEN=transmitted-secret"})):
            with self.assertRaises(AnalyzerError) as raised:
                client.classify_growth(self.slice)
        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(_ScriptedHandler.requests, [])
        self.assertEqual(list(self.cache_dir.glob("*")), [])

    def test_provider_payload_uses_aliases_and_translates_evidence_back(self) -> None:
        private_id = "fact:QmFzZTY0VVJMLXByaXZhdGUtZGF0YQ"
        facts = (
            StaticFact(private_id, "flow", "excerpt:1", "source"),
            StaticFact("fact:put", "container_write", "excerpt:1", "sink"),
            StaticFact("fact:target", "attacker_target", "excerpt:1", "source", private_id, "key"),
        )
        payload = replace(self.slice.payload, entry_id="entry:private", growth_id="growth:private", static_facts=facts, cfg_summary=CfgSummary(("path:private",), ("in_handler",), (private_id,)))
        slice_ = BoundedSlice("slice:private", payload)
        aliased_contract = {**PROVIDER_CONTRACT, "attacker_evidence_ids": ["fact:1"], "required_static_evidence": ["fact:1", "fact:2"]}
        _ScriptedHandler.scripted_responses = [(200, self._success(aliased_contract))]

        result = self._client().classify_growth(slice_)

        request = _ScriptedHandler.requests[0]["body"]
        self.assertNotIn(private_id, request)
        self.assertNotIn("entry:private", request)
        self.assertNotIn("growth:private", request)
        self.assertEqual(result.attacker_influence[0].evidence_id, private_id)
        self.assertEqual(result.required_static_evidence, (private_id, "fact:put"))

    def test_provider_aliases_preserve_same_file_relationship(self) -> None:
        from dosweb.llm.prompts import build_provider_payload

        first = self.slice.source_excerpts[0]
        second_content = "map.remove(key);\n"
        second = SourceExcerpt("excerpt:private-second", first.repo_relative_path, 2, 2, second_content, "b" * 64, hashlib.sha256(second_content.encode()).hexdigest())
        payload = replace(
            self.slice.payload,
            source_excerpts=(first, second),
            static_facts=(StaticFact("fact:key", "flow", "excerpt:1", "source"), StaticFact("fact:remove", "release", "excerpt:private-second", "releases")),
            cfg_summary=CfgSummary(("path:1",), ("in_handler",), ("fact:key",)),
        )
        provider = build_provider_payload(BoundedSlice("slice:same-file", payload))
        user = json.loads(provider.messages[1]["content"])
        excerpts = user["bounded_slice"]["source_excerpts"]
        self.assertEqual(excerpts[0]["repo_relative_path"], excerpts[1]["repo_relative_path"])
        self.assertNotIn(first.repo_relative_path, provider.messages[1]["content"])
        self.assertNotIn("excerpt:private-second", provider.messages[1]["content"])

    def test_prompt_contains_exact_typed_contract_schema(self) -> None:
        from dosweb.llm.schemas import GROWTH_CONTRACT_RESPONSE_SCHEMA, RESPONSE_SCHEMA_VERSION

        self.assertEqual("growth-contract-schema-v5", RESPONSE_SCHEMA_VERSION)
        messages = build_growth_messages(self.slice)
        user = json.loads(messages[1]["content"])
        self.assertEqual(user["response_schema_version"], RESPONSE_SCHEMA_VERSION)
        self.assertEqual(user["response_schema"], GROWTH_CONTRACT_RESPONSE_SCHEMA)
        self.assertEqual(
            set(user["response_schema"]),
            {
                "is_resource_growth", "attacker_evidence_ids", "resource_effect", "attacker_variable",
                "attacker_value_space", "growth_unit", "growth_function",
                "amplification_class", "requests_to_pressure",
                "concurrency_model", "retention_window", "failure_mechanism",
                "failure_signal", "required_static_evidence", "contract_status",
                "rejection_reason", "confidence",
            },
        )
        self.assertEqual(user["response_schema"]["attacker_evidence_ids"], ["fact:<ordinal>"])
        canonical = json.dumps(GROWTH_CONTRACT_RESPONSE_SCHEMA, sort_keys=True, separators=(",", ":"))
        self.assertIn(canonical, messages[0]["content"])
        self.assertIn("collection mutation alone is not DoS", messages[0]["content"])
        self.assertIn("growth_not_dos_relevant", messages[0]["content"])

    def test_request_id_credentials_are_rejected_without_cache_persistence(self) -> None:
        api_key = "exact-provider-key"
        credential_ids = (
            api_key,
            "Authorization: Bearer header-token-value",
            "serviceCredential=private-value",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
            "postgresql://user:password@datastore.example/app",
        )
        for request_id in credential_ids:
            with self.subTest(request_id=request_id):
                _ScriptedHandler.requests = []
                _ScriptedHandler.scripted_responses = [(200, {**self._success(PROVIDER_CONTRACT), "id": request_id})] * 2
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(api_key=api_key).classify_growth(self.slice)
                self.assertEqual(raised.exception.code, "LLM_RESPONSE_SENSITIVE_CONTENT")
                self.assertNotIn(api_key, f"{raised.exception.message} {raised.exception.details}")
                self.assertNotIn(request_id, f"{raised.exception.message} {raised.exception.details}")
                self.assertEqual(list(self.cache_dir.glob("*.json")), [])

    def test_java_assignment_scanner_handles_long_gap_compounds_and_comparisons(self) -> None:
        long_gap = "/*" + ("x" * 5000) + "*/ @Deprecated "
        blocked = (
            f'String serviceCredentials {long_gap}= "secret-value";',
            'serviceCredential += "secret-value";',
            'SERVICE_CREDENTIALS -= other;',
            'service_credential *= factor;',
            'service-credentials /= divisor;',
            'serviceCredential %= modulus;',
            'serviceCredential &= mask;',
            'serviceCredential |= mask;',
            'serviceCredential ^= mask;',
            'serviceCredential <<= shift;',
            'serviceCredential >>= shift;',
            'serviceCredential >>>= shift;',
        )
        for source in blocked:
            with self.subTest(source=source[:80]):
                _ScriptedHandler.requests = []
                _ScriptedHandler.scripted_responses = [(200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))] * 3
                verifier = _FakeVerifier(self.attestation)
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier).classify_growth(self._slice_with_content(source))
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
                self.assertEqual(verifier.calls, 0)
        benign = (
            "serviceCredential == other",
            "serviceCredential != other",
            "serviceCredential <= other",
            "serviceCredential >= other",
            "serviceCredential -> other",
        )
        for source in benign:
            with self.subTest(source=source):
                _ScriptedHandler.requests = []
                _ScriptedHandler.scripted_responses = [(200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))]
                self._client().classify_growth(self._slice_with_content(source))
                self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_java_type_annotation_argument_is_not_sensitive_assignment(self) -> None:
        source = "String credentials @Size(max = 5) [];"
        _ScriptedHandler.scripted_responses = [(200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))] * 3

        self._client().classify_growth(self._slice_with_content(source))

        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_sensitive_annotation_argument_is_not_a_credential_assignment(self) -> None:
        source = "@interface Ann { int token(); } @Ann(token = 5) class Example {}"
        _ScriptedHandler.scripted_responses = [(200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))]

        self._client().classify_growth(self._slice_with_content(source))

        self.assertEqual(len(_ScriptedHandler.requests), 1)

    def test_java_assignment_after_type_annotation_is_rejected(self) -> None:
        source = "String credentials @Size(max = 5) [] = values;"
        verifier = _FakeVerifier(self.attestation)

        with self.assertRaises(AnalyzerError) as raised:
            self._client(verifier).classify_growth(self._slice_with_content(source))

        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(_ScriptedHandler.requests, [])

    def test_short_source_excerpt_does_not_reject_valid_typed_response(self) -> None:
        for excerpt in ("}", "{", "unknown", ";"):
            with self.subTest(excerpt=excerpt):
                _ScriptedHandler.requests = []
                _ScriptedHandler.scripted_responses = [(200, self._success({**PROVIDER_CONTRACT, "required_static_evidence": ["fact:1"]}))]
                result = self._client().classify_growth(self._slice_with_content(excerpt))
                self.assertEqual(result.is_resource_growth, "yes")
        long_echo = "unique-source-echo-" + "x" * 96
        _ScriptedHandler.scripted_responses = [(200, {"model": "grok-4.6", "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": long_echo}]}]})] * 2
        with self.assertRaises(AnalyzerError) as raised:
            self._client().classify_growth(self._slice_with_content(long_echo))
        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SENSITIVE_CONTENT")

    def test_permanent_network_failures_do_not_retry_or_leak_details(self) -> None:
        failures = (
            socket.gaierror(getattr(socket, "EAI_NONAME", -2), "secret-host.invalid"),
            ssl.SSLCertVerificationError("certificate failed for secret-host.invalid"),
            URLError(OSError(errno.EACCES, "permission denied secret-token")),
            OSError(errno.EINVAL, "permanent secret-token"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                transport = mock.Mock()
                transport.post.side_effect = failure
                client = self._client(max_retries=3, api_key="secret-token")
                client._transport = transport
                with self.assertRaises(AnalyzerError) as raised:
                    client.classify_growth(self.slice)
                self.assertEqual(raised.exception.code, "LLM_NETWORK_FAILED")
                self.assertEqual(transport.post.call_count, 1)
                self.assertNotIn("secret-token", f"{raised.exception.message} {raised.exception.details}")

    def test_transient_proxy_and_tls_eof_failures_are_retried(self) -> None:
        transient_failures = (
            URLError(OSError("Tunnel connection failed: 502 Bad Gateway")),
            ssl.SSLEOFError(ssl.SSL_ERROR_EOF, "unexpected provider EOF"),
        )
        for index, failure in enumerate(transient_failures, 1):
            with self.subTest(failure=type(failure).__name__):
                transport = mock.Mock()
                transport.post.side_effect = [
                    failure,
                    json.dumps(self._success(PROVIDER_CONTRACT), separators=(",", ":")),
                ]
                client = self._client(
                    max_retries=3,
                    cache_dir=Path(self.temporary_directory.name) / f"transient-cache-{index}",
                )
                client._transport = transport

                result = client.classify_growth(self.slice)

                self.assertEqual(result.contract_status, "dos_relevant")
                self.assertEqual(transport.post.call_count, 2)

    def test_repeated_config_id_uses_one_provider_alias(self) -> None:
        from dosweb.llm.prompts import build_provider_payload
        facts = (
            ConfigFact("capacity", 10, "excerpt:1", "config:private"),
            ConfigFact("timeout", 20, "excerpt:1", "config:private"),
        )
        payload = replace(self.slice.payload, config_facts=facts)
        provider = build_provider_payload(BoundedSlice("slice:config-alias", payload))
        serialized = provider.messages[1]["content"]
        bounded = json.loads(serialized)["bounded_slice"]["config_facts"]
        self.assertEqual(bounded[0]["config_id"], bounded[1]["config_id"])
        self.assertNotIn("config:private", serialized)

    def test_config_backed_source_reference_uses_config_alias(self) -> None:
        from dosweb.llm.prompts import build_provider_payload

        fact = ConfigFact("request_limit", 1024, "config:private", "config:private")
        payload = replace(self.slice.payload, config_facts=(fact,))

        provider = build_provider_payload(BoundedSlice("slice:config-source-alias", payload))

        serialized = provider.messages[1]["content"]
        bounded = json.loads(serialized)["bounded_slice"]["config_facts"][0]
        self.assertEqual(bounded["config_id"], bounded["source_location_ref"])
        self.assertNotIn("config:private", serialized)

    def test_java_unicode_comments_annotations_and_compound_secret_names_are_blocked(self) -> None:
        examples = (
            'String STRIPE_API_KEY /* comment */ = "secret-value";',
            'String SERVICE_TOKEN/**/[] = {"secret-value"};',
            '@Deprecated String MY_PASSWORD /*x*/ = "secret-value";',
            'String API\\u005fKEY = "secret-value";',
            'String apiKey = " opaque-secret-value";',
            'String API_KEY = """\n opaque-secret-value\n """;',
            'String marker = "safe \\u002f\\u002f"; String api\\u004bey = "opaque-secret-value";',
            'String marker = "not // a comment"; String oauthToken = "opaque-secret-value";',
        )
        for source in examples:
            with self.subTest(source=source):
                verifier = _FakeVerifier(self.attestation)
                with self.assertRaises(AnalyzerError) as raised:
                    self._client(verifier).classify_growth(self._slice_with_content(source))
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_SECRET_DETECTED")
                self.assertNotIn("secret-value", str(raised.exception.details))
                self.assertEqual(verifier.calls, 0)


    def test_auth_cache_entries_count_toward_global_capacity(self) -> None:
        cache = ContractCache(self.cache_dir, "test-api-key")
        contract = {"auth_context": "unknown", "evidence_ids": [], "assumptions": [], "confidence": "low"}
        for index in range(256):
            key = f"{index:064x}"
            self.assertTrue(cache.put_auth_record(key, {"index": index}, contract, "{}"))
        with self.assertRaises(AnalyzerError) as raised:
            cache.put_auth_record("f" * 64, {"index": 257}, contract, "{}")
        self.assertEqual("LLM_CACHE_CAPACITY_EXHAUSTED", raised.exception.code)

    def test_authenticated_auth_v2_is_cold_then_v4_can_publish_under_new_identity(self) -> None:
        from dosweb.artifacts.identifiers import canonical_json, sha256_canonical_json

        self.cache_dir.mkdir(mode=0o700)
        cache = ContractCache(self.cache_dir, "test-api-key")
        key, identity = "a" * 64, {"kind": "auth", "version": 2}
        contract = {"auth_context": "unknown", "evidence_ids": [], "assumptions": [], "confidence": "low"}
        entry = {"cache_format": "auth-contract-cache-v2", "cache_key": key, "identity": identity, "contract": contract, "raw_response": "{}"}
        entry["entry_hash"] = sha256_canonical_json(entry)
        entry["entry_hmac"] = hmac.new(b"test-api-key", b"auth-contract-cache-v2\\0" + canonical_json(entry), hashlib.sha256).hexdigest()
        destination = self.cache_dir / f"auth-{key}.json"
        destination.write_bytes(canonical_json(entry))
        destination.chmod(0o600)

        self.assertIsNone(cache.get_auth_record(key, identity))
        self.assertTrue(destination.exists())
        new_key, new_identity = "c" * 64, {"kind": "auth", "version": 3}
        self.assertTrue(cache.put_auth_record(new_key, new_identity, contract, "{}"))
        self.assertEqual(
            cache.get_auth_record(new_key, new_identity),
            {"contract": contract, "raw_response": "{}", "accepted_prompt_variant": "initial", "actual_model": "grok-4.6"},
        )
        published = self.cache_dir / f"auth-{new_key}.json"
        self.assertEqual(json.loads(published.read_text(encoding="utf-8"))["cache_format"], "auth-contract-cache-v5")

    def test_tampered_auth_v1_is_not_deleted(self) -> None:
        self.cache_dir.mkdir(mode=0o700)
        key, identity = "b" * 64, {"kind": "auth", "version": 1}
        destination = self.cache_dir / f"auth-{key}.json"
        destination.write_text(json.dumps({"cache_format": "auth-contract-cache-v1", "cache_key": key, "identity": identity, "contract": {}, "raw_response": "{}", "entry_hash": "tampered", "entry_hmac": "tampered"}), encoding="utf-8")
        destination.chmod(0o600)

        self.assertIsNone(ContractCache(self.cache_dir, "test-api-key").get_auth_record(key, identity))
        self.assertTrue(destination.exists())

    def test_growth_audit_records_raw_response_and_cache_hit_without_credentials(self) -> None:
        _ScriptedHandler.scripted_responses = [(200, self._success(PROVIDER_CONTRACT))]
        client = self._client()
        client.classify_growth(self.slice)
        first = client.last_audit()
        self.assertIsNotNone(first)
        assert first is not None
        self.assertFalse(first.cache_hit)
        self.assertIn('"output"', first.raw_response)
        self.assertNotIn("test-api-key", first.normalized_prompt)
        client.classify_growth(self.slice)
        second = client.last_audit()
        self.assertIsNotNone(second)
        assert second is not None
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.raw_response, second.raw_response)
        self.assertIn('"output"', second.raw_response)

    def test_auth_contract_uses_security_aliases_and_cache(self) -> None:
        fact = EntrySecurityFact("entry:1", "dependency_coverage", "Example.java", 1, "public-security-coverage", "complete")
        response = {"auth_context": "unauthenticated", "evidence_ids": ["security:1"], "assumptions": [], "confidence": "high"}
        _ScriptedHandler.scripted_responses = [(200, self._success(response))]
        client = self._client()
        contract = client.classify_auth("entry:1", (fact,))
        self.assertEqual((fact.fact_id,), contract.evidence_ids)
        self.assertEqual(len(_ScriptedHandler.requests), 1)
        request = _ScriptedHandler.requests[0]
        self.assertEqual(request["path"], "/responses")
        body = json.loads(request["body"])
        self.assertIn("instructions", body)
        self.assertEqual(body["input"][0]["role"], "user")
        self.assertEqual(len(body["input"][0]["content"]), 1)
        self.assertEqual(body["input"][0]["content"][0]["type"], "input_text")
        self.assertIsInstance(body["input"][0]["content"][0]["text"], str)
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertEqual(body["text"]["format"]["name"], "auth_contract")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertFalse(body["store"])
        self.assertFalse(body["stream"])
        self.assertNotIn("messages", body)
        self.assertNotIn("response_format", body)
        self.assertFalse(client.last_audit().cache_hit)  # type: ignore[union-attr]
        client.classify_auth("entry:1", (fact,))
        self.assertTrue(client.last_audit().cache_hit)  # type: ignore[union-attr]
        # A new process/client must replay the authenticated private entry, including raw body.
        second_client = self._client()
        second_client.classify_auth("entry:1", (fact,))
        audit = second_client.last_audit()
        self.assertTrue(audit.cache_hit)  # type: ignore[union-attr]
        self.assertIn('"output"', audit.raw_response)  # type: ignore[union-attr]
        auth_files = list(self.cache_dir.glob("auth-*.json"))
        self.assertEqual(1, len(auth_files))
        cached_record = json.loads(auth_files[0].read_text(encoding="utf-8"))
        self.assertEqual(AUTH_PROMPT_VERSION, cached_record["identity"]["prompt_version"])
        self.assertEqual("auth-contract-v5", cached_record["identity"]["prompt_version"])
        self.assertEqual("initial", cached_record["accepted_prompt_variant"])
        self.assertNotIn("test-api-key", auth_files[0].read_text(encoding="utf-8"))


class JsonBoundaryTests(unittest.TestCase):
    def test_bounded_provider_read_rejects_oversize_invalid_utf8_and_incomplete_response(self) -> None:
        from dosweb.llm.deepseek import _MAX_RESPONSE_BYTES, _read_bounded_utf8

        class _Response:
            def __init__(self, body: bytes | BaseException, content_length: str | None = None) -> None:
                self.body, self.headers = body, {} if content_length is None else {"Content-Length": content_length}

            def read(self, size: int) -> bytes:
                self.requested_size = size
                if isinstance(self.body, BaseException):
                    raise self.body
                return self.body

        for response in (
            _Response(b"x" * (_MAX_RESPONSE_BYTES + 1)),
            _Response(b"\xff"),
            _Response(http.client.IncompleteRead(b"partial")),
            _Response(b"{}", str(_MAX_RESPONSE_BYTES + 1)),
        ):
            with self.subTest(response=response):
                with self.assertRaises(AnalyzerError) as raised:
                    _read_bounded_utf8(response)
                expected = "LLM_NETWORK_RETRYABLE" if isinstance(response.body, (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, OSError)) else "LLM_RESPONSE_INVALID"
                self.assertEqual(raised.exception.code, expected)
                if hasattr(response, "requested_size"):
                    self.assertLessEqual(response.requested_size, 4096)
                    self.assertGreater(response.requested_size, 0)

    def test_bounded_provider_read_never_calls_no_size_read(self) -> None:
        from dosweb.llm.deepseek import _read_bounded_bytes

        class OddResponse:
            headers: dict[str, str] = {}
            def __init__(self) -> None: self.calls: list[object] = []
            def read(self, *args: object) -> bytes:
                self.calls.append(args)
                if args: raise TypeError("sized read unsupported")
                raise AssertionError("unbounded read must never be called")

        response = OddResponse()
        with self.assertRaises(AnalyzerError):
            _read_bounded_bytes(response, 32)
        self.assertEqual(response.calls, [(33,)])

    def test_github_slow_drip_read_obeys_shared_deadline(self) -> None:
        payload = b'{"private":false}'
        chunks = [payload[:4], payload[4:8], payload[8:]]
        clock_values = iter((0.0, 0.2, 0.6, 1.1))
        clock = lambda: next(clock_values, 1.1)

        class Response:
            status = 200
            headers: dict[str, str] = {}
            def getcode(self) -> int: return 200
            def geturl(self) -> str: return "https://api.github.com/repos/example/repository"
            def read(self, size: int) -> bytes: return chunks.pop(0) if chunks else b""
            def __enter__(self): return self
            def __exit__(self, *args: object) -> None: return None

        verifier = GitHubPublicSourceVerifier(opener=lambda *_args, **_kwargs: Response(), monotonic=clock, git_timeout_seconds=1)
        with self.assertRaises(AnalyzerError) as raised:
            verifier._github_json("repos/example/repository", deadline=1.0)
        self.assertEqual(raised.exception.code, "CONFIG_PUBLIC_SOURCE_UNVERIFIED")

    def test_malformed_response_headers_map_to_controlled_error(self) -> None:
        from dosweb.llm.deepseek import _read_bounded_bytes

        class Response:
            def __init__(self, headers: object) -> None: self.headers = headers
            def read(self, size: int) -> bytes: return b""

        for headers in (None, {"Content-Length": "9" * 5000}, {"Content-Length": object()}):
            with self.subTest(headers_type=type(headers).__name__):
                with self.assertRaises(AnalyzerError) as raised:
                    _read_bounded_bytes(Response(headers), 32)
                self.assertEqual(raised.exception.code, "LLM_RESPONSE_INVALID")

    def test_cache_json_parser_rejects_bounded_invalid_and_recursive_input(self) -> None:
        from dosweb.llm.cache import _MAX_CACHE_BYTES, _strict_load

        deeply_nested: object = 0
        for _ in range(17):
            deeply_nested = [deeply_nested]
        for data in (
            b"x" * (_MAX_CACHE_BYTES + 1),
            b"\xff",
            b'{"entry":1,"entry":2}',
            b'{"entry":NaN}',
            json.dumps(deeply_nested).encode("utf-8"),
        ):
            with self.subTest(data=data[:30]):
                with self.assertRaises((UnicodeDecodeError, ValueError, RecursionError)):
                    _strict_load(data)

    def test_github_json_rejects_bounded_read_failures_and_invalid_json(self) -> None:
        class _Response:
            status = 200
            headers: dict[str, str] = {}

            def __init__(self, body: bytes | BaseException) -> None:
                self.body = body

            def getcode(self) -> int:
                return 200

            def geturl(self) -> str:
                return "https://api.github.com/repos/example/repository"

            def read(self, size: int) -> bytes:
                self.requested_size = size
                if isinstance(self.body, BaseException):
                    raise self.body
                return self.body

            def __enter__(self) -> _Response:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        for body in (b"\xff", http.client.IncompleteRead(b"partial"), b'{"private":NaN}'):
            response = _Response(body)
            verifier = GitHubPublicSourceVerifier(opener=lambda *_args, **_kwargs: response)
            with self.subTest(body=body):
                with self.assertRaises(AnalyzerError) as raised:
                    verifier._github_json("repos/example/repository")
                self.assertEqual(raised.exception.code, "CONFIG_PUBLIC_SOURCE_UNVERIFIED")
                self.assertLessEqual(response.requested_size, 4096)
                self.assertGreater(response.requested_size, 0)

    def test_provider_envelope_json_rejects_depth_duplicate_keys_and_nonfinite_values(self) -> None:
        client = DeepSeekClient(
            LlmConfig("grok-4.6", "http://127.0.0.1:8000/", "test-api-key", 1, 1, 0, Path("cache"), True, "https://github.com/example/public-repository", "a" * 40, Path(".")),
            verifier=_FakeVerifier(PublicSourceAttestation("https://github.com/example/public-repository", "a" * 40, True, True)),
            transport=_LoopbackTransport(),
        )
        deeply_nested: object = {"model": "grok-4.6", "choices": [{"message": {"content": "{}"}}]}
        for _ in range(17):
            deeply_nested = [deeply_nested]
        for body in (
            json.dumps(deeply_nested),
            '{"model":"grok-4.6","model":"grok-4.6","choices":[]}',
            '{"model":NaN,"choices":[]}',
        ):
            with self.subTest(body=body[:30]):
                with self.assertRaises(AnalyzerError) as raised:
                    client._response_content(ProviderReply(body, {}))
                self.assertEqual(raised.exception.code, "LLM_RESPONSE_INVALID")


class GitHubPublicSourceVerifierTests(unittest.TestCase):
    def test_default_verifier_requires_public_matching_commit_and_clean_checkout(self) -> None:
        config = LlmConfig(
            model="grok-4.6",
            base_url="https://rightapi.ai/grok/v1/",
            api_key="test-api-key",
            timeout_seconds=1,
            max_retries=3,
            temperature=0,
            cache_dir=Path("cache"),
            allow_remote_llm=True,
            public_source_url="https://github.com/example/public-repository",
            source_commit_sha="b" * 40,
            source_checkout=Path("/fixture"),
        )

        class _Response:
            status = 200

            def __init__(self, payload: object) -> None:
                self._payload = json.dumps(payload).encode("utf-8")

            def getcode(self) -> int:
                return 200

            def read(self, size: int) -> bytes:
                if not self._payload:
                    return b""
                chunk, self._payload = self._payload[:size], self._payload[size:]
                return chunk

            def __enter__(self) -> _Response:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        requests: list[object] = []

        def opener(request: object, timeout: int) -> _Response:
            requests.append(request)
            payloads = (
                {"private": False, "default_branch": "main"},
                {"sha": "b" * 40},
                {"status": "ahead"},
            )
            return _Response(payloads[len(requests) - 1])

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(command[:5], ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"])
            self.assertIn("status.showUntrackedFiles=all", command)
            self.assertEqual(command[command.index("--no-pager"):command.index("--no-pager") + 3], ["--no-pager", "-C", "/fixture"])
            self.assertEqual(
                kwargs["env"],
                {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "", "GIT_NO_REPLACE_OBJECTS": "1"},
            )
            arguments = command[command.index("/fixture") + 1:]
            if arguments[:1] == ["remote"]:
                output = "https://github.com/example/public-repository.git"
            elif arguments[:2] == ["rev-parse", "--show-toplevel"]:
                output = "/fixture"
            elif arguments[:1] == ["rev-parse"]:
                output = "b" * 40
            else:
                output = ""
            return subprocess.CompletedProcess(command, 0, output, "")

        attestation = GitHubPublicSourceVerifier(opener=opener, runner=runner).verify(config)

        self.assertTrue(attestation.verified_public)
        self.assertTrue(attestation.verified_clean_checkout)
        self.assertEqual(attestation.public_source_url, "https://github.com/example/public-repository")
        self.assertEqual(len(requests), 2)

    def test_verify_local_checkout_against_public_source_reuses_strict_checkout_checks(self) -> None:
        calls: list[tuple[str, ...]] = []

        with mock.patch("dosweb.llm.deepseek.GitHubPublicSourceVerifier") as verifier_cls:
            verifier = verifier_cls.return_value
            verifier._verify_checkout.side_effect = lambda checkout, sha, source_url=None: calls.append((str(checkout), sha, source_url))
            from dosweb.llm.deepseek import verify_local_checkout_against_public_source
            verify_local_checkout_against_public_source(Path("/fixture"), "https://github.com/example/public-repository", "B" * 40)
        self.assertEqual(calls, [("/fixture", "b" * 40, "https://github.com/example/public-repository")])

    def test_default_verifier_allows_local_commit_binding_without_public_source_url(self) -> None:
        config = LlmConfig(
            "grok-4.6", "https://api.deepseek.com/", "test-api-key", 1, 3, 0,
            Path("cache"), True,
            None, "b" * 40, Path("/fixture"),
        )

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            arguments = command[command.index("/fixture") + 1:]
            if arguments[:2] == ["rev-parse", "--show-toplevel"]:
                output = "/fixture"
            elif arguments[:1] == ["rev-parse"]:
                output = "b" * 40
            else:
                output = ""
            return subprocess.CompletedProcess(command, 0, output, "")

        attestation = GitHubPublicSourceVerifier(runner=runner).verify(config)

        self.assertFalse(attestation.verified_public)
        self.assertTrue(attestation.verified_clean_checkout)
        self.assertIsNone(attestation.public_source_url)

    def test_default_verifier_rejects_public_url_not_bound_to_checkout_origin(self) -> None:
        config = LlmConfig(
            "grok-4.6", "https://api.deepseek.com/", "test-api-key", 1, 3, 0,
            Path("cache"), True,
            "https://github.com/example/public-repository", "b" * 40, Path("/fixture"),
        )

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            arguments = command[command.index("/fixture") + 1:]
            if arguments[:2] == ["rev-parse", "--show-toplevel"]:
                output = "/fixture"
            elif arguments[:1] == ["rev-parse"]:
                output = "b" * 40
            else:
                output = ""
            return subprocess.CompletedProcess(command, 0, output, "")

        opener = mock.Mock(side_effect=AssertionError("GitHub API must not run after origin mismatch"))
        with self.assertRaises(AnalyzerError) as raised:
            GitHubPublicSourceVerifier(opener=opener, runner=runner).verify(config)
        self.assertEqual("CONFIG_PUBLIC_SOURCE_UNVERIFIED", raised.exception.code)
        opener.assert_not_called()

    def test_source_requirements_canonicalize_public_github_url(self) -> None:
        config = LlmConfig(
            "grok-4.6", "https://api.deepseek.com/", "test-api-key", 1, 3, 0,
            Path("cache"), True,
            "https://github.com/Cicizz/jmqtt", "b" * 40, Path("/fixture"),
        )
        from dosweb.llm.deepseek import _source_requirements
        self.assertEqual(
            _source_requirements(config),
            ("https://github.com/cicizz/jmqtt", "b" * 40, Path("/fixture")),
        )

    def test_default_verifier_accepts_public_pinned_commit_without_branch_assumption(self) -> None:
        config = LlmConfig(
            "grok-4.6", "https://api.deepseek.com/", "test-api-key", 1, 3, 0,
            Path("cache"), True,
            "https://github.com/example/public-repository", "b" * 40, Path("/fixture"),
        )

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            arguments = command[command.index("/fixture") + 1:]
            if arguments[:2] == ["remote", "get-url"]:
                output = "https://github.com/example/public-repository.git"
            elif arguments[:2] == ["rev-parse", "--show-toplevel"]:
                output = "/fixture"
            elif arguments[:1] == ["rev-parse"]:
                output = "b" * 40
            else:
                output = ""
            return subprocess.CompletedProcess(command, 0, output, "")

        requests = 0
        def opener(request: object, timeout: int) -> _VerifierJsonResponse:
            nonlocal requests
            requests += 1
            payload = {"private": False} if requests == 1 else {"sha": "b" * 40}
            return _VerifierJsonResponse(request.full_url, payload)

        attestation = GitHubPublicSourceVerifier(opener=opener, runner=runner).verify(config)
        self.assertTrue(attestation.verified_public)
        self.assertTrue(attestation.verified_clean_checkout)
        self.assertEqual(2, requests)

    def test_verify_local_git_steps_share_one_absolute_deadline(self) -> None:
        config = LlmConfig("grok-4.6", "https://api.deepseek.com/", "test-api-key", 1, 3, 0, Path("cache"), True, None, "b" * 40, Path("/fixture"))
        current = -0.01
        def clock() -> float:
            nonlocal current
            current += 0.01
            return current
        timeouts: list[float] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            timeouts.append(float(kwargs["timeout"]))
            arguments = command[command.index("/fixture") + 1:]
            if arguments[:2] == ["rev-parse", "--show-toplevel"]:
                output = "/fixture"
            elif arguments[:1] == ["rev-parse"]:
                output = "b" * 40
            else:
                output = ""
            return subprocess.CompletedProcess(command, 0, output, "")

        verifier = GitHubPublicSourceVerifier(opener=mock.Mock(), runner=runner, monotonic=clock, git_timeout_seconds=1)
        attestation = verifier.verify(config)
        self.assertFalse(attestation.verified_public)
        self.assertGreaterEqual(len(timeouts), 3)
        self.assertTrue(all(later <= earlier for earlier, later in zip(timeouts, timeouts[1:])))
        self.assertLess(timeouts[-1], timeouts[0])

    def test_verify_slice_shares_one_deadline_across_authorization_and_blob_validation(self) -> None:
        config = LlmConfig("grok-4.6", "https://api.deepseek.com/", "test-api-key", 1, 3, 0, Path("cache"), True, "https://github.com/example/public-repository", "b" * 40, Path("/fixture"))
        verifier = GitHubPublicSourceVerifier(monotonic=lambda: 5.0, git_timeout_seconds=2)
        attestation = PublicSourceAttestation(config.public_source_url, config.source_commit_sha, True, True)
        slice_ = mock.Mock(spec=BoundedSlice)
        with mock.patch.object(verifier, "_verify", return_value=attestation) as verify, mock.patch.object(verifier, "_validate_slice") as validate:
            self.assertEqual(verifier.verify_slice(config, slice_), attestation)
        verify.assert_called_once_with(config, 7.0)
        validate.assert_called_once_with(config, slice_, attestation, 7.0)

    def test_default_verifier_rejects_private_repository_without_commit_or_deepseek_call(self) -> None:
        config = LlmConfig(
            model="grok-4.6",
            base_url="https://rightapi.ai/grok/v1/",
            api_key="test-api-key",
            timeout_seconds=1,
            max_retries=3,
            temperature=0,
            cache_dir=Path("cache"),
            allow_remote_llm=True,
            public_source_url="https://github.com/example/public-repository",
            source_commit_sha="b" * 40,
            source_checkout=Path("/fixture"),
        )
        response = mock.MagicMock()
        response.status = 200
        response.getcode.return_value = 200
        response.read.return_value = b'{"private": true}'
        response.__enter__.return_value = response
        with self.assertRaises(AnalyzerError) as raised:
            GitHubPublicSourceVerifier(
                opener=lambda *_args, **_kwargs: response,
                runner=mock.Mock(),
            ).verify(config)
        self.assertEqual(raised.exception.code, "CONFIG_PUBLIC_SOURCE_UNVERIFIED")

    def test_injected_git_runner_nonzero_is_rejected(self) -> None:
        runner = mock.Mock(return_value=subprocess.CompletedProcess(["git"], 1, "", "failed"))
        verifier = GitHubPublicSourceVerifier(runner=runner)
        with self.assertRaises(AnalyzerError) as raised:
            verifier._run(Path("/fixture"), "status", "--porcelain")
        self.assertEqual(raised.exception.code, "CONFIG_PUBLIC_SOURCE_UNVERIFIED")

    def test_endpoint_validation_allows_only_production_or_loopback(self) -> None:
        self.assertEqual(
            validate_provider_endpoint("https://rightapi.ai/grok/v1"),
            "https://rightapi.ai/grok/v1/",
        )
        with self.assertRaises(AnalyzerError):
            validate_provider_endpoint("https://apibasis.com/v1/")
        with self.assertRaises(AnalyzerError):
            validate_provider_endpoint("https://api.deepseek.com/")
        self.assertEqual(validate_provider_endpoint("http://[::1]:8000/", allow_test_transport=True), "http://[::1]:8000/")
        self.assertEqual(
            validate_provider_endpoint("http://localhost:8000/", allow_test_transport=True),
            "http://localhost:8000/",
        )
        for endpoint in ("https://evil.example/", "https://api.deepseek.com.evil.example/", "http://api.deepseek.com/"):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(AnalyzerError) as raised:
                    validate_provider_endpoint(endpoint)
                self.assertEqual(raised.exception.code, "CONFIG_UNSAFE_LLM_ENDPOINT")

    def test_hardened_git_invocation_disables_checkout_configured_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp)
            marker = checkout / "fsmonitor-executed"
            subprocess.run(["git", "init", str(checkout)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(checkout), "config", "core.fsmonitor", f"sh -c 'touch {marker}'"], check=True)
            verifier = GitHubPublicSourceVerifier()
            verifier._run(checkout, "status", "--porcelain")
            self.assertFalse(marker.exists())

    def test_real_git_cat_file_metadata_uses_supported_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp)
            subprocess.run(["git", "init", str(checkout)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(checkout), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(checkout), "config", "user.name", "Test"], check=True)
            (checkout / "Example.java").write_text("class Example {}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(checkout), "add", "Example.java"], check=True)
            subprocess.run(["git", "-C", str(checkout), "commit", "-m", "fixture"], check=True, stdout=subprocess.DEVNULL)
            sha = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
            object_type, object_size = GitHubPublicSourceVerifier()._git_object_metadata(checkout, f"{sha}:Example.java")
        self.assertEqual(object_type, "blob")
        self.assertEqual(object_size, len("class Example {}\n".encode()))

    def test_silent_git_process_times_out_without_blocking_read(self) -> None:
        released = threading.Event()
        class Process:
            def __init__(self) -> None:
                self.stdout = self
                self.returncode = None
            def read(self, size: int) -> bytes:
                released.wait(2)
                return b""
            def poll(self): return self.returncode
            def terminate(self): self.returncode = -15; released.set()
            def kill(self): self.returncode = -9; released.set()
            def wait(self, timeout=None): return self.returncode or 0
            def close(self): pass

        verifier = GitHubPublicSourceVerifier(process_factory=lambda *args, **kwargs: Process(), git_timeout_seconds=0.05)
        started = time.monotonic()
        with self.assertRaises(AnalyzerError) as raised:
            verifier._run(Path("/fixture"), "status", "--porcelain")
        self.assertEqual(raised.exception.code, "CONFIG_PUBLIC_SOURCE_UNVERIFIED")
        self.assertLess(time.monotonic() - started, 1)

    def test_git_process_that_closes_stdout_but_stays_alive_obeys_deadline(self) -> None:
        class Process:
            def __init__(self) -> None:
                self.stdout = mock.Mock()
                self.stdout.read.return_value = b""
                self.returncode = None
            def wait(self, timeout=None):
                if self.returncode is None:
                    raise subprocess.TimeoutExpired("git", timeout)
                return self.returncode
            def terminate(self): self.returncode = -15
            def kill(self): self.returncode = -9
        verifier = GitHubPublicSourceVerifier(process_factory=lambda *args, **kwargs: Process(), git_timeout_seconds=0.05)
        started = time.monotonic()
        with self.assertRaises(AnalyzerError) as raised:
            verifier._run(Path("/fixture"), "status", "--porcelain")
        self.assertEqual(raised.exception.code, "CONFIG_PUBLIC_SOURCE_UNVERIFIED")
        self.assertLess(time.monotonic() - started, 0.5)

    def test_canonical_origin_url_accepts_github_proxy_wrapper(self) -> None:
        from dosweb.llm.deepseek import _canonical_origin_url
        self.assertEqual(
            _canonical_origin_url("https://gh-proxy.com/https://github.com/Cicizz/jmqtt.git"),
            "https://github.com/cicizz/jmqtt",
        )

    def test_git_command_overrides_malicious_status_and_fsck_config(self) -> None:
        runner = mock.Mock(return_value=subprocess.CompletedProcess(["git"], 0, "", ""))
        verifier = GitHubPublicSourceVerifier(runner=runner)
        verifier._run(Path("/fixture"), "status", "--porcelain")
        command = runner.call_args.args[0]
        self.assertIn("status.showUntrackedFiles=all", command)
        self.assertIn("fsck.missingEmail=error", command)

    def test_git_output_overflow_is_rejected_with_bounded_collection(self) -> None:
        class Process:
            def __init__(self) -> None:
                self.stdout = mock.Mock()
                self.stdout.read.side_effect = [b"x" * 4096] * 100
                self.returncode = None
            def poll(self): return self.returncode
            def terminate(self): self.returncode = -15
            def kill(self): self.returncode = -9
            def wait(self, timeout=None): self.returncode = self.returncode or 0; return self.returncode

        verifier = GitHubPublicSourceVerifier(process_factory=lambda *args, **kwargs: Process())
        with self.assertRaises(AnalyzerError) as raised:
            verifier._run(Path("/fixture"), "status", "--porcelain")
        self.assertEqual(raised.exception.code, "CONFIG_PUBLIC_SOURCE_UNVERIFIED")

    def test_validate_slice_rejects_oversized_git_blob_without_reading_it(self) -> None:
        content = "map.put(key, value);"
        slice_ = BoundedSlice(
            "slice:1",
            BoundedSlicePayload(
                "entry:1", "growth:1",
                (SourceExcerpt("excerpt:1", "Example.java", 1, 1, content, "a" * 64, hashlib.sha256(content.encode()).hexdigest()),),
                (StaticFact("fact:1", "flow", "excerpt:1", "source"),),
                CfgSummary(("path:1",), ("in_handler",), ("fact:1",)),
                (RegistrationFact("spring_mvc", "excerpt:1"),), (),
            ),
        )
        config = LlmConfig("grok-4.6", "https://api.deepseek.com/", "test-api-key", 1, 3, 0, Path("cache"), True, "https://github.com/example/public-repository", "a" * 40, Path("/fixture"))
        attestation = PublicSourceAttestation("https://github.com/example/public-repository", "a" * 40, True, True)
        calls: list[tuple[str, ...]] = []
        verifier = GitHubPublicSourceVerifier()
        verifier._verify_checkout = mock.Mock()  # type: ignore[method-assign]

        def git_bytes(checkout: Path, *arguments: str, deadline: float | None = None) -> bytes:
            calls.append(arguments)
            if arguments[0] == "cat-file":
                return b"blob 1048577\n"
            raise AssertionError(f"full blob must not be read: {arguments}")

        verifier._git_bytes = git_bytes  # type: ignore[method-assign]
        with self.assertRaises(AnalyzerError) as raised:
            verifier.validate_slice(config, slice_, attestation)
        self.assertEqual(raised.exception.code, "CONFIG_PUBLIC_SOURCE_UNVERIFIED")
        self.assertEqual(calls, [("cat-file", "--batch-check=%(objecttype) %(objectsize)", "a" * 40 + ":Example.java")])

    def test_verify_runs_strict_fsck_before_any_local_object_read(self) -> None:
        config = LlmConfig("grok-4.6", "https://api.deepseek.com/", "test-api-key", 1, 3, 0, Path("cache"), True, "https://github.com/example/public-repository", "b" * 40, Path("/fixture"))
        calls: list[tuple[str, ...]] = []
        github_calls = 0

        def opener(request: object, timeout: int) -> object:
            nonlocal github_calls
            github_calls += 1
            payload = json.dumps(
                {"private": False, "default_branch": "main"}
                if github_calls == 1
                else ({"sha": "b" * 40} if github_calls == 2 else {"status": "ahead"})
            ).encode()
            class Response:
                status = 200
                headers: dict[str, str] = {}
                def __init__(self) -> None: self.remaining = payload
                def getcode(self) -> int: return 200
                def geturl(self) -> str: return request.full_url
                def read(self, size: int) -> bytes:
                    chunk, self.remaining = self.remaining[:size], self.remaining[size:]
                    return chunk
                def __enter__(self): return self
                def __exit__(self, *args: object) -> None: return None
            return Response()

        verifier = GitHubPublicSourceVerifier(opener=opener)

        def run(checkout: Path, *arguments: str, deadline: float | None = None) -> subprocess.CompletedProcess[str]:
            calls.append(arguments)
            if arguments[:2] == ("rev-parse", "--show-toplevel"):
                output = "/fixture"
            elif arguments[:2] == ("remote", "get-url"):
                output = "https://github.com/example/public-repository.git"
            elif arguments[:1] == ("rev-parse",):
                output = "b" * 40
            else:
                output = ""
            return subprocess.CompletedProcess(["git"], 0, output, "")

        verifier._run = run  # type: ignore[method-assign]
        verifier.verify(config)
        self.assertEqual(calls[0], ("fsck", "--strict", "--no-dangling", "--no-reflogs", "--", "b" * 40))


if __name__ == "__main__":
    unittest.main()
