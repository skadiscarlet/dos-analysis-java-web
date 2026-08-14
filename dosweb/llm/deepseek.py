from __future__ import annotations

import http.client
import json
import math
import os
import re
import socket
import ssl
import errno
import subprocess
import time
import threading
import selectors
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dosweb.config import LlmConfig, MAX_LLM_RETRIES, MAX_LLM_TIMEOUT_SECONDS, SUPPORTED_MODELS
from dosweb.errors import AnalyzerError
from dosweb.growth.contracts import parse_growth_contract_json, validate_contract_static_evidence
from dosweb.growth.models import AttackerInfluence, BoundedSlice, GrowthContract
from dosweb.llm.cache import ContractCache, cache_identity, canonical_base_url
from dosweb.llm.prompts import build_growth_messages, build_provider_payload

_MAX_RESPONSE_BYTES = 131072
_MAX_GIT_BLOB_BYTES = 16384
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 256
_MAX_JSON_STRING_BYTES = 65536
_MAX_REQUEST_BYTES = 131072
_MAX_REQUEST_SCAN_DEPTH = 16
_MAX_REQUEST_SCAN_NODES = 8192
_MAX_GIT_OUTPUT_BYTES = 65536
_MAX_GIT_STATUS_BYTES = 4096
_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]+")
# Match exact credential-bearing labels in snake, kebab, camel and conventional header forms.
_CREDENTIAL_ASSIGNMENT = re.compile(r'''(?ix)(?<![a-z0-9_-])(?!feature[_-]password\b|logging[_-]token\b)(?:authorization|api[_-]?key|private[_-]?key|access[_-]?(?:token|key)|refresh[_-]?token|aws[_-]?(?:secret[_-]?access[_-]?key|access[_-]?key[_-]?id)|client[_-]?secret|db[_-]?password|password|passwd|oauth[_-]?token|token|secret|x[_-]?api[_-]?key|(?:[a-z0-9]+[_-])+(?:api[_-]?key|private[_-]?key|access[_-]?(?:token|key)|refresh[_-]?token|client[_-]?secret|password|passwd|oauth[_-]?token|token|secret))\b(?:\\?["'])?(?:\s*(?:\[\s*\])?)*\s*[:=]\s*(?:\{\s*)?(?:\\?["'])?[^\s"';,}]+''')
_JAVA_UNICODE_ESCAPE = re.compile(r"(?:\\)+u+([0-9a-fA-F]{4})")
_JAVA_COMMENT = re.compile(r"/\*.*?\*/|//[^\r\n]*", re.DOTALL)
_JAVA_STRING_CHAIN = re.compile(r'''(?sx)(?:""".*?"""|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')(?:\s*\+\s*(?:""".*?"""|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'))+''')
_JAVA_LITERAL = re.compile(r'''(?sx)""".*?"""|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' ''')
_SENSITIVE_MUTATOR_CALL = re.compile(
    r"(?ix)\b(?:set|with|add|put|update|configure)[_$-]*"
    r"(?:authorization|api[_$-]*key|private[_$-]*key|access[_$-]*(?:token|key)|"
    r"refresh[_$-]*token|client[_$-]*secret|password|passwd|oauth[_$-]*token|"
    r"token|secret|credential|credentials)\s*\("
)
_GENERIC_CREDENTIAL_CALL = re.compile(
    r'''(?ix)\b(?:set|add|put|header)\s*\(\s*
    (?P<quote>["'])(?:authorization|x[_-]?api[_-]?key|api[_-]?key|private[_-]?key|access[_-]?(?:token|key)|
    refresh[_-]?token|client[_-]?secret|password|passwd|oauth[_-]?token|token|secret|credential|credentials)(?P=quote)\s*,'''
)
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_CREDENTIAL_URI_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?)?\d{3}[ .-]\d{4}(?!\w)")
_SSN_PATTERN = re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)")
_SLICE_CREDENTIAL_PATTERNS = (
    ("credential_assignment", _CREDENTIAL_ASSIGNMENT),
    ("authorization_value", re.compile(r'''(?i)\b(?:bearer|basic)\s+["']?\S+''')),
    ("deepseek_key", _SECRET_PATTERN),
    ("github_token", re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("aws_access_key", re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", _JWT_PATTERN),
    ("credential_uri", _CREDENTIAL_URI_PATTERN),
    ("email", _EMAIL_PATTERN),
    ("phone", _PHONE_PATTERN),
    ("ssn", _SSN_PATTERN),
)
_GITHUB_SOURCE_PATTERN = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
_FULL_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_PRODUCTION_ENDPOINT = "https://api.deepseek.com/"
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class PublicSourceAttestation:
    public_source_url: str | None
    source_commit_sha: str
    verified_public: bool
    verified_clean_checkout: bool


@dataclass(frozen=True)
class ProviderReply:
    body: str
    headers: dict[str, str]


@dataclass
class _InFlightState:
    event: threading.Event
    result: GrowthContract | None = None
    error: tuple[str, str, dict[str, object]] | None = None
    retry: bool = False


_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT: dict[str, _InFlightState] = {}
_SHAREABLE_FAILURES = frozenset({"LLM_RESPONSE_INVALID", "LLM_RESPONSE_SCHEMA_INVALID", "LLM_RESPONSE_SENSITIVE_CONTENT"})


def _reset_inflight_after_fork() -> None:
    global _INFLIGHT_LOCK, _INFLIGHT
    _INFLIGHT_LOCK = threading.Lock()
    _INFLIGHT = {}


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_inflight_after_fork)


class ProviderTransport(Protocol):
    def post(self, endpoint: str, payload: bytes, headers: dict[str, str], timeout: int) -> str | ProviderReply:
        raise NotImplementedError


class PublicSourceVerifier(Protocol):
    def verify(self, config: LlmConfig) -> PublicSourceAttestation: ...
    def validate_slice(self, config: LlmConfig, slice_: BoundedSlice, attestation: PublicSourceAttestation) -> None: ...


class GitHubPublicSourceVerifier:
    """Verifies a clean checkout against public GitHub without credentials."""
    def __init__(self, *, opener: Callable[..., Any] | None = None, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None, process_factory: Callable[..., Any] | None = None, git_timeout_seconds: float = 10.0, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._opener = opener or build_opener(_NoRedirect()).open
        self._runner = runner
        self._process_factory = process_factory or (None if runner is not None else subprocess.Popen)
        self._git_timeout_seconds = git_timeout_seconds
        self._monotonic = monotonic

    def verify(self, config: LlmConfig) -> PublicSourceAttestation:
        return self._verify(config, self._monotonic() + self._git_timeout_seconds)

    def verify_slice(self, config: LlmConfig, slice_: BoundedSlice) -> PublicSourceAttestation:
        deadline = self._monotonic() + self._git_timeout_seconds
        attestation = self._verify(config, deadline)
        self._validate_slice(config, slice_, attestation, deadline)
        return attestation

    def _verify(self, config: LlmConfig, deadline: float) -> PublicSourceAttestation:
        source_url, source_sha, checkout = _source_requirements(config)
        self._verify_checkout(checkout, source_sha, deadline=deadline)
        return PublicSourceAttestation(source_url, source_sha, False, True)

    def validate_slice(self, config: LlmConfig, slice_: BoundedSlice, attestation: PublicSourceAttestation) -> None:
        self._validate_slice(config, slice_, attestation, self._monotonic() + self._git_timeout_seconds)

    def _validate_slice(self, config: LlmConfig, slice_: BoundedSlice, attestation: PublicSourceAttestation, deadline: float) -> None:
        source_url, source_sha, checkout = _source_requirements(config)
        if (
            attestation.public_source_url != source_url
            or attestation.source_commit_sha.lower() != source_sha
            or not attestation.verified_clean_checkout
        ):
            _unverified()
        self._verify_checkout(checkout, source_sha, deadline=deadline)
        for excerpt in slice_.source_excerpts:
            object_id = f"{source_sha}:{excerpt.repo_relative_path}"
            object_type, object_size = self._git_object_metadata(checkout, object_id, deadline=deadline)
            if object_type != "blob" or object_size > _MAX_GIT_BLOB_BYTES:
                _unverified()
            blob = self._git_bytes(checkout, "show", object_id, deadline=deadline)
            if len(blob) != object_size or __import__("hashlib").sha256(blob).hexdigest() != excerpt.git_blob_sha256: _unverified()
            try:
                lines = blob.splitlines(keepends=True)
                if excerpt.start_line < 1 or excerpt.end_line < excerpt.start_line or excerpt.end_line > len(lines): _unverified()
                actual_bytes = b"".join(lines[excerpt.start_line - 1:excerpt.end_line])
                actual = actual_bytes.decode("utf-8")
            except (UnicodeDecodeError, IndexError): _unverified()
            if actual != excerpt.content or __import__("hashlib").sha256(actual_bytes).hexdigest() != excerpt.excerpt_sha256: _unverified()

    def _github_json(self, path: str, *, deadline: float | None = None) -> dict[str, object]:
        deadline = self._monotonic() + self._git_timeout_seconds if deadline is None else deadline
        request = Request(f"https://api.github.com/{path}", headers={"Accept": "application/vnd.github+json", "User-Agent": "dosweb-public-source-verifier"}, method="GET")
        try:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError("verification deadline exceeded")
            with self._opener(request, timeout=remaining) as response:
                status = getattr(response, "status", None)
                if status is None:
                    getcode = getattr(response, "getcode", None)
                    status = getcode() if callable(getcode) else None
                if status != 200 or getattr(response, "geturl", lambda: request.full_url)() != request.full_url: _unverified()
                payload = _bounded_json(_read_bounded_bytes(response, _MAX_RESPONSE_BYTES, deadline=deadline, monotonic=self._monotonic))
        except AnalyzerError as exc:
            if exc.code in {"LLM_RESPONSE_INVALID", "LLM_NETWORK_RETRYABLE"}:
                raise AnalyzerError("CONFIG_PUBLIC_SOURCE_UNVERIFIED", "Public GitHub source could not be verified.") from exc
            raise
        except (HTTPError, URLError, OSError, TimeoutError, http.client.IncompleteRead, http.client.RemoteDisconnected, UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise AnalyzerError("CONFIG_PUBLIC_SOURCE_UNVERIFIED", "Public GitHub source could not be verified.") from exc
        if not isinstance(payload, dict): _unverified()
        return payload

    def _verify_checkout(self, checkout: Path, source_sha: str, *, source_url: str | None = None, deadline: float | None = None) -> None:
        self._git(checkout, "fsck", "--strict", "--no-dangling", "--no-reflogs", "--", source_sha, deadline=deadline)
        if self._git(checkout, "replace", "-l", deadline=deadline): _unverified()
        if Path(self._git(checkout, "rev-parse", "--show-toplevel", deadline=deadline)).resolve() != checkout.resolve(): _unverified()
        if source_url is not None and _canonical_origin_url(self._git(checkout, "remote", "get-url", "origin", deadline=deadline)) != source_url: _unverified()
        if self._git(checkout, "rev-parse", "HEAD", deadline=deadline).lower() != source_sha or self._git(checkout, "status", "--porcelain", deadline=deadline): _unverified()

    def _git_object_metadata(self, checkout: Path, object_id: str, *, deadline: float | None = None) -> tuple[str, int]:
        output = self._git_bytes(
            checkout,
            "cat-file",
            "--batch-check=%(objecttype) %(objectsize)",
            object_id,
            deadline=deadline,
        )
        try:
            line = output.rstrip(b"\n")
            object_type, size_text = line.split(b" ", 1)
            if object_type != b"blob" or not size_text.isdigit():
                raise ValueError
            object_size = int(size_text)
        except (ValueError, OverflowError):
            _unverified()
        return object_type.decode("ascii"), object_size

    def _git_bytes(self, checkout: Path, *arguments: str, deadline: float | None = None) -> bytes:
        completed = self._run(checkout, *arguments, deadline=deadline)
        output = completed.stdout
        return output if isinstance(output, bytes) else output.encode("utf-8")

    def _git(self, checkout: Path, *arguments: str, deadline: float | None = None) -> str:
        output = self._run(checkout, *arguments, deadline=deadline).stdout
        return output.decode("utf-8").strip() if isinstance(output, bytes) else output.strip()

    def _run(self, checkout: Path, *arguments: str, deadline: float | None = None) -> subprocess.CompletedProcess[str]:
        command_arguments = arguments[:-1] if arguments[0] == "cat-file" else arguments
        command = [
            "git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-c", "status.showUntrackedFiles=all", "-c", "fsck.missingEmail=error",
            "-c", "fsck.badEmail=error", "-c", "fsck.zeroPaddedFilemode=error",
            "--no-pager", "-C", str(checkout), *command_arguments,
        ]
        environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "", "GIT_NO_REPLACE_OBJECTS": "1"}
        binary = arguments[0] == "show"
        limit = _MAX_GIT_STATUS_BYTES if arguments[:2] == ("status", "--porcelain") else (_MAX_GIT_BLOB_BYTES + 1 if binary else _MAX_GIT_OUTPUT_BYTES)
        deadline = self._monotonic() + self._git_timeout_seconds if deadline is None else deadline
        try:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, self._git_timeout_seconds)
            if self._process_factory is None:
                completed = self._runner(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=not binary, env=environment, timeout=remaining)
                if completed.returncode != 0: _unverified()
                output = completed.stdout if isinstance(completed.stdout, bytes) else completed.stdout.encode("utf-8")
                if len(output) > limit: _unverified()
                return completed
            process = self._process_factory(command, stdin=subprocess.PIPE if arguments[0] == "cat-file" else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment)
            if arguments[0] == "cat-file":
                process.stdin.write((arguments[-1] + "\n").encode("utf-8")); process.stdin.close()
            output = bytearray()
            read_result: list[object] = []
            read_ready = threading.Event()
            def reader() -> None:
                collected = bytearray()
                try:
                    while len(collected) <= limit:
                        chunk = process.stdout.read(min(4096, limit + 1 - len(collected)))
                        if isinstance(chunk, str): chunk = chunk.encode("utf-8")
                        if not isinstance(chunk, bytes): raise ValueError("git output was not bytes")
                        if not chunk: break
                        collected.extend(chunk)
                    read_result.append(bytes(collected))
                except BaseException as exc:
                    read_result.append(exc)
                finally:
                    read_ready.set()
            threading.Thread(target=reader, daemon=True).start()
            while not read_ready.wait(min(0.01, max(0.0, deadline - self._monotonic()))):
                if self._monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, self._git_timeout_seconds)
            if not read_result:
                raise ValueError("git reader produced no result")
            if isinstance(read_result[0], BaseException):
                raise read_result[0]
            chunk = read_result[0]
            if isinstance(chunk, str): chunk = chunk.encode("utf-8")
            if not isinstance(chunk, bytes):
                raise ValueError("git output was not bytes")
            output.extend(chunk)
            if len(output) > limit or (arguments[:2] == ("status", "--porcelain") and b"\n" in output):
                raise ValueError("git output exceeded command limit")
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, self._git_timeout_seconds)
            returncode = process.wait(timeout=remaining)
            if self._monotonic() > deadline:
                raise subprocess.TimeoutExpired(command, self._git_timeout_seconds)
            process.stdout.close()
            if returncode != 0: _unverified()
            rendered = bytes(output) if binary else bytes(output).decode("utf-8")
            return subprocess.CompletedProcess(command, returncode, rendered, None)
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError, ValueError) as exc:
            if 'process' in locals():
                cleanup_deadline = locals().get("deadline", self._monotonic())
                try:
                    process.terminate()
                    process.wait(timeout=max(0.0, cleanup_deadline - self._monotonic()))
                except Exception:
                    try:
                        process.kill()
                        process.wait(timeout=max(0.0, cleanup_deadline - self._monotonic()))
                    except Exception:
                        pass
            raise AnalyzerError("CONFIG_PUBLIC_SOURCE_UNVERIFIED", "Local source checkout could not be verified.") from exc


class DeepSeekClient:
    def __init__(self, config: LlmConfig, *, verifier: PublicSourceVerifier | None = None, transport: ProviderTransport | None = None, extra_secret_patterns: tuple[tuple[str, re.Pattern[str]], ...] = (), sleep: Callable[[float], None] = time.sleep, jitter: Callable[[], float] = lambda: 0.0, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._config, self._verifier, self._transport = config, verifier or GitHubPublicSourceVerifier(), transport
        self._sleep, self._jitter, self._monotonic, self._cache = sleep, jitter, monotonic, ContractCache(config.cache_dir, config.api_key)
        self._opener = build_opener(_NoRedirect())
        if not all(isinstance(name, str) and isinstance(pattern, re.Pattern) for name, pattern in extra_secret_patterns): raise TypeError("extra_secret_patterns must contain compiled regular expressions")
        self._extra_secret_patterns = extra_secret_patterns

    def classify_growth(self, slice_: BoundedSlice) -> GrowthContract:
        _validate_runtime_config(self._config)
        provider_payload = build_provider_payload(slice_)
        request_payload = {"model": self._config.model, "messages": provider_payload.messages, "temperature": self._config.temperature}
        request_body = _encode_request(request_payload)
        _scan_transmitted_request(request_body, self._config.api_key, self._extra_secret_patterns)
        self._validate_remote_gate()
        attestation = self._verified_attestation(slice_)
        cache_key, identity = cache_identity(self._config, slice_)
        static_fact_ids = frozenset(fact.fact_id for fact in slice_.payload.static_facts)
        cached = self._cache.get(cache_key, identity, static_fact_ids) if self._cache.is_usable(cache_key) else None
        if cached is not None: return cached
        state, owner = _join_inflight(cache_key)
        if not owner:
            state.event.wait()
            if state.result is not None:
                return state.result
            if state.error is not None:
                code, message, details = state.error
                raise AnalyzerError(code, message, details)
            return self.classify_growth(slice_)
        try:
            with self._cache.single_flight(cache_key) as cache_available:
                authenticated_entry = None
                if cache_available:
                    cached = self._cache.get(cache_key, identity, static_fact_ids)
                    if cached is not None:
                        _finish_inflight(cache_key, state, result=cached)
                        return cached
                    authenticated_entry = self._cache.authenticated_contract(cache_key, identity)
                reservation = self._cache.capacity_reservation(cache_key, allow_existing=authenticated_entry is not None)
                with reservation:
                    reply = self._post_with_retries(request_body, slice_)
                    content, actual_model, request_id = self._response_content(reply)
                    _reject_sensitive_response(content, slice_, self._config.api_key, self._extra_secret_patterns)
                    _reject_sensitive_provider_id(request_id, self._config.api_key, self._extra_secret_patterns)
                    if not re.fullmatch(r"[A-Za-z0-9._:-]*", request_id):
                        raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM response contained an invalid request identifier.")
                    contract = _restore_contract_aliases(parse_growth_contract_json(content), provider_payload.fact_alias_to_original)
                    contract = validate_contract_static_evidence(contract, static_fact_ids)
                    audit = {"method": "POST", "url": self._endpoint(), "requested_model": self._config.model, "actual_model": actual_model, "provider_request_id_digest": self._cache.provider_request_id_digest(request_id), "slice_content_hash": identity["slice_content_hash"], "allow_remote_llm": self._config.allow_remote_llm, "public_source_url": attestation.public_source_url, "source_commit_sha": attestation.source_commit_sha, "verified_public": False, "verified_clean_checkout": attestation.verified_clean_checkout}
                    if authenticated_entry is None:
                        self._cache.put(cache_key, identity, contract, audit)
                    _finish_inflight(cache_key, state, result=contract)
                    return contract
        except AnalyzerError as exc:
            if exc.code in _SHAREABLE_FAILURES:
                _finish_inflight(cache_key, state, error=(exc.code, exc.message, _redact_mapping(exc.details, self._config.api_key)))
            else:
                _finish_inflight(cache_key, state, retry=True)
            raise
        except BaseException:
            _finish_inflight(cache_key, state, retry=True)
            raise

    def _validate_remote_gate(self) -> None:
        validate_provider_endpoint(self._config.base_url, allow_test_transport=self._transport is not None)
        if not self._config.allow_remote_llm: raise AnalyzerError("CONFIG_REMOTE_LLM_NOT_AUTHORIZED", "Remote LLM calls require explicit authorization.")
        if not isinstance(self._config.api_key, str) or not self._config.api_key.strip(): raise AnalyzerError("CONFIG_MISSING_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY must be set to a non-empty value in the environment.")
        _source_requirements(self._config)

    def _verified_attestation(self, slice_: BoundedSlice | None = None) -> PublicSourceAttestation:
        verify_slice = getattr(self._verifier, "verify_slice", None)
        if slice_ is not None and callable(verify_slice):
            attestation = verify_slice(self._config, slice_)
        else:
            attestation = self._verifier.verify(self._config)
            if slice_ is not None:
                self._verifier.validate_slice(self._config, slice_, attestation)
        source_url, source_sha, _ = _source_requirements(self._config)
        if (
            not isinstance(attestation, PublicSourceAttestation)
            or attestation.public_source_url != source_url
            or attestation.source_commit_sha.lower() != source_sha
            or not attestation.verified_clean_checkout
        ):
            _unverified()
        return attestation

    def _endpoint(self) -> str: return urljoin(canonical_base_url(self._config.base_url), "chat/completions")

    def _post_with_retries(self, body: bytes, slice_: BoundedSlice) -> ProviderReply:
        failure: AnalyzerError | None = None
        for attempt in range(self._config.max_retries):
            try:
                self._verified_attestation(slice_)
                return self._post_once(body)
            except AnalyzerError as exc:
                if exc.code not in {"LLM_RETRYABLE_HTTP", "LLM_NETWORK_RETRYABLE"}: raise
                failure = exc
            if attempt + 1 < self._config.max_retries: self._sleep(min(2 ** attempt + max(0.0, self._jitter()), 8.0))
        raise AnalyzerError("LLM_RETRIES_EXHAUSTED", "The remote LLM did not return a successful response after retrying.", _redact_mapping(failure.details if failure else {}, self._config.api_key))

    def _post_once(self, payload: dict[str, object] | bytes) -> ProviderReply:
        body = payload if isinstance(payload, bytes) else _encode_request(payload)
        deadline = self._monotonic() + self._config.timeout_seconds
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._config.api_key}"}
        if self._transport is not None:
            try:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise TimeoutError("request deadline exceeded")
                result = self._transport.post(self._endpoint(), body, headers, remaining)
                if self._monotonic() > deadline:
                    raise TimeoutError("request deadline exceeded")
            except BaseException as exc:
                if _is_retryable_network_error(exc):
                    raise AnalyzerError("LLM_NETWORK_RETRYABLE", "Remote LLM request failed transiently.") from exc
                if isinstance(exc, (OSError, URLError, ssl.SSLError)):
                    raise AnalyzerError("LLM_NETWORK_FAILED", "Remote LLM request failed permanently.") from exc
                raise
            return result if isinstance(result, ProviderReply) else ProviderReply(result, {})
        request = Request(self._endpoint(), data=body, headers=headers, method="POST")
        try:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError("request deadline exceeded")
            with self._opener.open(request, timeout=remaining) as response:
                return ProviderReply(_read_bounded_utf8(response, deadline=deadline, monotonic=self._monotonic), {str(k).lower(): str(v) for k, v in response.headers.items()})
        except HTTPError as exc:
            exc.close()
            if exc.code in {401, 403}: raise AnalyzerError("LLM_AUTHENTICATION_FAILED", "Remote LLM authentication failed.") from exc
            if exc.code == 429 or 500 <= exc.code <= 599: raise AnalyzerError("LLM_RETRYABLE_HTTP", "Remote LLM returned a retryable HTTP response.", {"status": exc.code}) from exc
            raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM returned an unsuccessful HTTP response.", {"status": exc.code}) from exc
        except BaseException as exc:
            if _is_retryable_network_error(exc):
                raise AnalyzerError("LLM_NETWORK_RETRYABLE", "Remote LLM request failed transiently.") from exc
            if isinstance(exc, (OSError, URLError, ssl.SSLError)):
                raise AnalyzerError("LLM_NETWORK_FAILED", "Remote LLM request failed permanently.") from exc
            if isinstance(exc, UnicodeDecodeError):
                raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM response was not UTF-8 JSON.") from exc
            raise

    def _response_content(self, reply: ProviderReply) -> tuple[object, str, str]:
        if not isinstance(reply.body, str) or len(reply.body.encode("utf-8")) > _MAX_RESPONSE_BYTES: raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM response exceeds the safe size limit.")
        try: envelope = _bounded_json(reply.body.encode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc: raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM response envelope was not valid JSON.") from exc
        try:
            if not isinstance(envelope, dict) or not isinstance(envelope["model"], str) or envelope["model"] != self._config.model: raise TypeError
            choices = envelope["choices"]
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict) or not isinstance(choices[0]["message"], dict): raise TypeError
            content, model = choices[0]["message"]["content"], envelope["model"]
            request_id = reply.headers.get("x-request-id", reply.headers.get("request-id", envelope.get("id", "")))
            if not isinstance(request_id, str) or len(request_id.encode("utf-8")) > 512: raise TypeError
        except (KeyError, TypeError): raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM response envelope was malformed or has a mismatched model.")
        return content, model, request_id


def _join_inflight(key: str) -> tuple[_InFlightState, bool]:
    with _INFLIGHT_LOCK:
        state = _INFLIGHT.get(key)
        if state is not None:
            return state, False
        state = _InFlightState(threading.Event())
        _INFLIGHT[key] = state
        return state, True


def _finish_inflight(key: str, state: _InFlightState, *, result: GrowthContract | None = None, error: tuple[str, str, dict[str, object]] | None = None, retry: bool = False) -> None:
    with _INFLIGHT_LOCK:
        if _INFLIGHT.get(key) is state:
            del _INFLIGHT[key]
        state.result = result
        state.error = error
        state.retry = retry
        state.event.set()


def _encode_request(payload: dict[str, object]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(body) > _MAX_REQUEST_BYTES: raise AnalyzerError("LLM_REQUEST_INVALID", "Serialized LLM request exceeds the safe size limit.")
    return body


def _translate_java_unicode(content: str) -> str:
    for _ in range(8):
        decoded = _JAVA_UNICODE_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), content)
        if decoded == content:
            return content
        content = decoded
    return content


def _java_code_only(content: str) -> str:
    source = _translate_java_unicode(content)
    output = list(source)
    index = 0
    state = "code"
    while index < len(source):
        if state == "code":
            if source.startswith("//", index):
                output[index:index + 2] = "  "; index += 2; state = "line_comment"; continue
            if source.startswith("/*", index):
                output[index:index + 2] = "  "; index += 2; state = "block_comment"; continue
            if source.startswith('"""', index):
                output[index:index + 3] = "   "; index += 3; state = "text_block"; continue
            if source[index] == '"':
                output[index] = " "; index += 1; state = "string"; continue
            if source[index] == "'":
                output[index] = " "; index += 1; state = "char"; continue
            index += 1; continue
        output[index] = "\n" if source[index] in "\r\n" else " "
        if state == "line_comment" and source[index] in "\r\n": state = "code"
        elif state == "block_comment" and source.startswith("*/", index):
            if index + 1 < len(output): output[index + 1] = " "
            index += 1; state = "code"
        elif state == "text_block" and source.startswith('"""', index):
            output[index:index + 3] = "   "; index += 2; state = "code"
        elif state in {"string", "char"} and source[index] == "\\":
            if index + 1 < len(output): output[index + 1] = " "
            index += 1
        elif state == "string" and source[index] == '"': state = "code"
        elif state == "char" and source[index] == "'": state = "code"
        index += 1
    return "".join(output)


def _skip_java_annotation(code: str, index: int) -> int:
    if index >= len(code) or code[index] != "@":
        return index
    index += 1
    name = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\s*\.\s*[A-Za-z_$][A-Za-z0-9_$]*)*", code[index:])
    if name is None:
        return index - 1
    index += name.end()
    while index < len(code) and code[index].isspace():
        index += 1
    if index >= len(code) or code[index] != "(":
        return index
    depth = 0
    while index < len(code):
        if code[index] == "(":
            depth += 1
        elif code[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(code)


def _java_assignment_after_identifier(code: str, index: int) -> bool:
    while True:
        while index < len(code) and code[index].isspace():
            index += 1
        if code.startswith("[]", index):
            index += 2
            continue
        if index < len(code) and code[index] == "@":
            next_index = _skip_java_annotation(code, index)
            if next_index == index:
                return False
            index = next_index
            continue
        break
    for operator in (">>>=", "<<=", ">>=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "="):
        if code.startswith(operator, index):
            if operator == "=" and index + 1 < len(code) and code[index + 1] == "=":
                return False
            return True
    return False


def _java_without_annotation_arguments(code: str) -> str:
    output = list(code)
    index = 0
    while index < len(code):
        if code[index] != "@":
            index += 1
            continue
        name = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\s*\.\s*[A-Za-z_$][A-Za-z0-9_$]*)*", code[index + 1:])
        if name is None:
            index += 1
            continue
        cursor = index + 1 + name.end()
        while cursor < len(code) and code[cursor].isspace():
            cursor += 1
        if cursor >= len(code) or code[cursor] != "(":
            index = cursor
            continue
        depth = 0
        start = cursor + 1
        while cursor < len(code):
            if code[cursor] == "(": depth += 1
            elif code[cursor] == ")":
                depth -= 1
                if depth == 0:
                    output[start:cursor] = " " * (cursor - start)
                    cursor += 1
                    break
            cursor += 1
        index = cursor
    return "".join(output)


def _sensitive_java_assignment(content: str) -> bool:
    code = _java_without_annotation_arguments(_java_code_only(content))
    identifier_pattern = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*(?:[-_][A-Za-z0-9_$]+)*")
    for match in identifier_pattern.finditer(code):
        identifier = match.group(0)
        normalized = re.sub(r"[^a-z0-9]", "", identifier.lower())
        separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", identifier).lower()
        components = tuple(component for component in re.split(r"[^a-z0-9]+", separated) if component)
        sensitive_component = any(component in {"authorization", "password", "passwd", "token", "secret", "credential", "credentials"} for component in components)
        sensitive_pair = any(pair in {("api", "key"), ("private", "key"), ("access", "key"), ("client", "secret"), ("refresh", "token"), ("oauth", "token")} for pair in zip(components, components[1:]))
        sensitive = normalized not in {"featurepassword", "loggingtoken"} and (
            sensitive_component or sensitive_pair
            or normalized in {"authorization", "apikey", "privatekey", "accesskey", "accesstoken", "refreshtoken", "clientsecret", "password", "passwd", "oauthtoken", "token", "secret", "credential", "credentials", "awssecretaccesskey", "awsaccesskeyid"}
            or any(normalized.endswith(suffix) for suffix in ("apikey", "privatekey", "accesstoken", "refreshtoken", "clientsecret", "password", "passwd", "oauthtoken", "token", "secret", "credential", "credentials"))
        )
        if sensitive and _java_assignment_after_identifier(code, match.end()):
            return True
    return False


def _normalize_source_for_scan(content: str) -> str:
    return _java_code_only(content)


def _java_comments_as_space(content: str) -> str:
    source = _translate_java_unicode(content)
    output = list(source)
    index = 0
    state = "code"
    while index < len(source):
        if state == "code":
            if source.startswith("//", index):
                output[index:index + 2] = "  "; index += 2; state = "line_comment"; continue
            if source.startswith("/*", index):
                output[index:index + 2] = "  "; index += 2; state = "block_comment"; continue
            if source.startswith('"""', index):
                index += 3; state = "text_block"; continue
            if source[index] == '"':
                index += 1; state = "string"; continue
            if source[index] == "'":
                index += 1; state = "char"; continue
            index += 1; continue
        if state in {"line_comment", "block_comment"}:
            output[index] = "\n" if source[index] in "\r\n" else " "
        if state == "line_comment" and source[index] in "\r\n": state = "code"
        elif state == "block_comment" and source.startswith("*/", index):
            if index + 1 < len(output): output[index + 1] = " "
            index += 1; state = "code"
        elif state == "text_block" and source.startswith('"""', index): index += 2; state = "code"
        elif state in {"string", "char"} and source[index] == "\\": index += 1
        elif state == "string" and source[index] == '"': state = "code"
        elif state == "char" and source[index] == "'": state = "code"
        index += 1
    return "".join(output)


def _decode_java_literal(literal: str) -> str:
    if literal.startswith('"""'):
        value = literal[3:-3]
    else:
        value = literal[1:-1]
    value = re.sub(r"\\([0-7]{1,3})", lambda match: chr(int(match.group(1), 8)), value)
    escapes = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "'": "'", "\\": "\\"}
    return re.sub(r"\\(.)", lambda match: escapes.get(match.group(1), match.group(1)), value, flags=re.DOTALL)


def _java_decoded_literal_values(content: str) -> list[str]:
    translated = _java_comments_as_space(content)
    values: list[str] = [translated]
    for chain in _JAVA_STRING_CHAIN.finditer(translated):
        values.append("".join(_decode_java_literal(literal.group(0)) for literal in _JAVA_LITERAL.finditer(chain.group(0))))
    for literal in _JAVA_LITERAL.finditer(translated):
        values.append(_decode_java_literal(literal.group(0)))
    return values


def _scan_transmitted_request(body: bytes, configured_api_key: str, extra_patterns: tuple[tuple[str, re.Pattern[str]], ...] = ()) -> None:
    try:
        serialized = body.decode("utf-8")
        decoded = json.loads(serialized)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AnalyzerError("LLM_REQUEST_INVALID", "Serialized LLM request is invalid.") from exc
    try:
        strings = _all_strings(decoded)
        nested_strings = list(strings)
        for item in strings:
            try:
                nested_strings.extend(_all_strings(json.loads(item)))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        strings = nested_strings
    except RecursionError as exc:
        raise AnalyzerError("LLM_REQUEST_INVALID", "Serialized LLM request exceeds safe structural limits.") from exc
    if any(_sensitive_java_assignment(item) for item in strings):
        raise AnalyzerError("LLM_BOUNDED_SLICE_SECRET_DETECTED", "Bounded slice credential scan failed.", {"pattern_id": "credential_assignment"})
    if any(
        _SENSITIVE_MUTATOR_CALL.search(_java_comments_as_space(item))
        or _GENERIC_CREDENTIAL_CALL.search(_java_comments_as_space(item))
        for item in strings
    ):
        raise AnalyzerError(
            "LLM_BOUNDED_SLICE_SECRET_DETECTED",
            "Bounded slice credential scan failed.",
            {"pattern_id": "credential_method_call"},
        )
    if any(
        _CREDENTIAL_ASSIGNMENT.search(comment.group(0))
        for item in strings
        for comment in _JAVA_COMMENT.finditer(_translate_java_unicode(item))
    ):
        raise AnalyzerError(
            "LLM_BOUNDED_SLICE_SECRET_DETECTED",
            "Bounded slice credential scan failed.",
            {"pattern_id": "credential_assignment_comment"},
        )
    normalized_strings = [_normalize_source_for_scan(item) for item in strings]
    decoded_literal_strings = [value for item in strings for value in _java_decoded_literal_values(item)]
    content = "\n".join((serialized, *strings, *normalized_strings, *decoded_literal_strings))
    credential_content = "\n".join(_java_without_annotation_arguments(_java_comments_as_space(item)) for item in strings)
    if configured_api_key and configured_api_key in content: raise AnalyzerError("LLM_BOUNDED_SLICE_SECRET_DETECTED", "Bounded slice credential scan failed.", {"pattern_id": "configured_api_key"})
    for pattern_id, pattern in (*_SLICE_CREDENTIAL_PATTERNS, *extra_patterns):
        target = credential_content if pattern_id == "credential_assignment" else content
        if pattern.search(target): raise AnalyzerError("LLM_BOUNDED_SLICE_SECRET_DETECTED", "Bounded slice credential scan failed.", {"pattern_id": pattern_id})


def scan_slice_for_credentials(slice_: BoundedSlice, configured_api_key: str, extra_patterns: tuple[tuple[str, re.Pattern[str]], ...] = ()) -> None:
    payload = {"model": "deepseek-v4-pro", "messages": build_growth_messages(slice_), "temperature": 0}
    _scan_transmitted_request(_encode_request(payload), configured_api_key, extra_patterns)


def _restore_contract_aliases(contract: GrowthContract, aliases: dict[str, str]) -> GrowthContract:
    try:
        influences = tuple(AttackerInfluence(item.target, aliases[item.evidence_id]) for item in contract.attacker_influence)
        required = tuple(aliases[item] for item in contract.required_static_evidence)
    except KeyError as exc:
        raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Growth Contract cites an unknown provider alias.") from exc
    return GrowthContract(contract.is_resource_growth, contract.growth_kind, contract.resource_dimension, influences, contract.resource_effect, required, contract.confidence)


def _reject_sensitive_response(content: object, slice_: BoundedSlice, configured_api_key: str, extra_patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> None:
    if not isinstance(content, str): return
    if configured_api_key and configured_api_key in content: raise AnalyzerError("LLM_RESPONSE_SENSITIVE_CONTENT", "Provider response contains sensitive content.")
    meaningful_echo = any(len(excerpt.content.encode("utf-8")) >= 64 and excerpt.content in content for excerpt in slice_.source_excerpts)
    if any(pattern.search(content) for _, pattern in (*_SLICE_CREDENTIAL_PATTERNS, *extra_patterns)) or re.search(r"eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]+\.", content) or re.search(r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@", content) or meaningful_echo: raise AnalyzerError("LLM_RESPONSE_SENSITIVE_CONTENT", "Provider response contains sensitive content.")


def _reject_sensitive_provider_id(value: str, configured_api_key: str, extra_patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> None:
    if not value:
        return
    if configured_api_key and value == configured_api_key:
        raise AnalyzerError("LLM_RESPONSE_SENSITIVE_CONTENT", "Provider response contains sensitive content.")
    if _sensitive_java_assignment(value) or any(pattern.search(value) for _, pattern in (*_SLICE_CREDENTIAL_PATTERNS, *extra_patterns)):
        raise AnalyzerError("LLM_RESPONSE_SENSITIVE_CONTENT", "Provider response contains sensitive content.")


def _is_retryable_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, InterruptedError, http.client.RemoteDisconnected, http.client.IncompleteRead)):
        return True
    if isinstance(exc, ssl.SSLError):
        return False
    if isinstance(exc, socket.gaierror):
        return exc.errno == getattr(socket, "EAI_AGAIN", None)
    if isinstance(exc, URLError):
        return _is_retryable_network_error(exc.reason) if isinstance(exc.reason, BaseException) else False
    if isinstance(exc, ConnectionError):
        return True
    if isinstance(exc, OSError):
        return exc.errno in {errno.EINTR, errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE}
    return False


def _all_strings(value: object) -> list[str]:
    result: list[str] = []
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if depth > _MAX_REQUEST_SCAN_DEPTH or nodes > _MAX_REQUEST_SCAN_NODES:
            raise RecursionError("request JSON exceeds safe structural limits")
        if isinstance(current, str):
            result.append(current)
        elif isinstance(current, dict):
            for key, nested in current.items():
                result.append(str(key))
                stack.append((nested, depth + 1))
        elif isinstance(current, (list, tuple)):
            stack.extend((nested, depth + 1) for nested in reversed(current))
    return result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: object, code: int, msg: str, headers: object, newurl: str) -> None: return None


def validate_provider_endpoint(base_url: str, *, allow_test_transport: bool = False) -> str:
    try:
        canonical = canonical_base_url(base_url)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "The LLM base URL is invalid.") from exc
    parsed = urlparse(canonical)
    if canonical == _PRODUCTION_ENDPOINT: return canonical
    if not allow_test_transport or parsed.hostname not in _LOOPBACK_HOSTS: raise AnalyzerError("CONFIG_UNSAFE_LLM_ENDPOINT", "The LLM endpoint must be the canonical production endpoint or a loopback test server.")
    return canonical


def _validate_runtime_config(config: LlmConfig) -> None:
    if not isinstance(config.api_key, str) or not config.api_key.strip():
        raise AnalyzerError("CONFIG_MISSING_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY must be set to a non-empty value in the environment.")
    if (
        config.model not in SUPPORTED_MODELS
        or not isinstance(config.timeout_seconds, int)
        or isinstance(config.timeout_seconds, bool)
        or not 1 <= config.timeout_seconds <= MAX_LLM_TIMEOUT_SECONDS
        or not isinstance(config.max_retries, int)
        or isinstance(config.max_retries, bool)
        or not 1 <= config.max_retries <= MAX_LLM_RETRIES
        or not isinstance(config.temperature, (int, float))
        or isinstance(config.temperature, bool)
        or not math.isfinite(config.temperature)
        or not 0 <= config.temperature <= 2
    ):
        raise AnalyzerError("CONFIG_INVALID_VALUE", "LLM configuration contains an invalid bounded value.")


def _source_requirements(config: LlmConfig) -> tuple[str | None, str, Path]:
    source_url, source_sha, checkout = config.public_source_url, config.source_commit_sha, config.source_checkout
    if not isinstance(source_sha, str) or _FULL_SHA_PATTERN.fullmatch(source_sha) is None or not isinstance(checkout, Path):
        _unverified()
    if source_url is None:
        return None, source_sha.lower(), checkout
    if not isinstance(source_url, str) or _GITHUB_SOURCE_PATTERN.fullmatch(source_url) is None:
        _unverified()
    canonical = _canonical_origin_url(source_url)
    if canonical is None:
        _unverified()
    return canonical, source_sha.lower(), checkout


def _canonical_origin_url(value: str) -> str | None:
    if value.startswith("git@github.com:"):
        value = f"https://github.com/{value.removeprefix('git@github.com:')}"
    embedded = "https://github.com/"
    if embedded in value and not value.startswith(embedded):
        value = value[value.index(embedded):]
    if value.endswith(".git"):
        value = value[:-4]
    match = _GITHUB_SOURCE_PATTERN.fullmatch(value)
    return None if match is None else f"https://github.com/{match.group(1).lower()}/{match.group(2).lower()}"


def verify_local_checkout_at_commit(checkout: Path, source_commit_sha: str, public_source_url: str | None = None) -> None:
    if _FULL_SHA_PATTERN.fullmatch(source_commit_sha) is None:
        _unverified()
    canonical_url = None
    if public_source_url is not None:
        if _GITHUB_SOURCE_PATTERN.fullmatch(public_source_url) is None:
            _unverified()
        canonical_url = _canonical_origin_url(public_source_url)
        if canonical_url is None:
            _unverified()
    GitHubPublicSourceVerifier()._verify_checkout(checkout, source_commit_sha.lower(), source_url=canonical_url)


def verify_local_checkout_against_public_source(checkout: Path, public_source_url: str, source_commit_sha: str) -> None:
    verify_local_checkout_at_commit(checkout, source_commit_sha, public_source_url)


def _unverified() -> None: raise AnalyzerError("CONFIG_PUBLIC_SOURCE_UNVERIFIED", "Public source provenance and local checkout could not be verified.")


def _read_bounded_utf8(response: Any, *, deadline: float | None = None, monotonic: Callable[[], float] = time.monotonic) -> str:
    try:
        return _read_bounded_bytes(response, _MAX_RESPONSE_BYTES, deadline=deadline, monotonic=monotonic).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM response was not UTF-8 JSON.") from exc


def _read_bounded_bytes(response: Any, limit: int, *, deadline: float | None = None, monotonic: Callable[[], float] = time.monotonic) -> bytes:
    headers = getattr(response, "headers", {})
    if headers is None or not hasattr(headers, "get"):
        raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote response headers were malformed.")
    length = headers.get("Content-Length")
    if length is not None:
        if not isinstance(length, str) or len(length) > 20 or not length.isdigit():
            raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote response headers were malformed.")
        try:
            content_length = int(length)
        except (ValueError, OverflowError) as exc:
            raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote response headers were malformed.") from exc
        if content_length > limit:
            raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM response exceeds the safe size limit.")
    collected = bytearray()
    reader = getattr(response, "read1", None)
    if not callable(reader):
        reader = getattr(response, "read", None)
    if not callable(reader):
        raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote response does not support bounded reads.")
    try:
        while len(collected) <= limit:
            if deadline is not None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError("request deadline exceeded")
                socket_object = getattr(getattr(response, "fp", None), "raw", None)
                socket_object = getattr(socket_object, "_sock", None)
                if socket_object is not None and hasattr(socket_object, "settimeout"):
                    socket_object.settimeout(remaining)
            size = min(4096, limit + 1 - len(collected))
            chunk = reader(size)
            if deadline is not None and monotonic() > deadline:
                raise TimeoutError("request deadline exceeded")
            if not isinstance(chunk, bytes):
                raise TypeError("response chunk was not bytes")
            if not chunk:
                break
            collected.extend(chunk)
    except TypeError as exc:
        raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote response does not support bounded reads.") from exc
    except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout) as exc:
        raise AnalyzerError("LLM_NETWORK_RETRYABLE", "Remote response body read failed transiently.") from exc
    except OSError as exc:
        if _is_retryable_network_error(exc):
            raise AnalyzerError("LLM_NETWORK_RETRYABLE", "Remote response body read failed transiently.") from exc
        raise AnalyzerError("LLM_NETWORK_FAILED", "Remote LLM response body read failed permanently.") from exc
    if len(collected) > limit:
        raise AnalyzerError("LLM_RESPONSE_INVALID", "Remote LLM response exceeds the safe size limit.")
    return bytes(collected)


def _bounded_json(data: bytes) -> object:
    if len(data) > _MAX_RESPONSE_BYTES: raise ValueError("too large")
    value = json.loads(data.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    _check_json_bounds(value)
    return value


def _check_json_bounds(value: object, depth: int = 0, seen: list[int] | None = None) -> None:
    seen = [] if seen is None else seen
    if depth > _MAX_JSON_DEPTH: raise ValueError("too deeply nested")
    seen.append(1)
    if len(seen) > _MAX_JSON_NODES: raise ValueError("too many JSON values")
    if isinstance(value, str) and len(value.encode("utf-8")) > _MAX_JSON_STRING_BYTES: raise ValueError("string too large")
    if isinstance(value, dict):
        if len(value) > 64: raise ValueError("object too large")
        for child in value.values(): _check_json_bounds(child, depth + 1, seen)
    elif isinstance(value, list):
        if len(value) > 64: raise ValueError("array too large")
        for child in value: _check_json_bounds(child, depth + 1, seen)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result: raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None: raise ValueError(f"invalid JSON constant: {value}")


def _redact_mapping(details: object, api_key: str) -> dict[str, object]:
    if not isinstance(details, dict): return {}
    return {str(key): _redact(value, api_key, str(key).lower() == "authorization") for key, value in details.items()}


def _redact(value: object, api_key: str, authorization: bool = False) -> object:
    if isinstance(value, str):
        result = "[REDACTED]" if authorization else value.replace(api_key, "[REDACTED]") if api_key else value
        return _SECRET_PATTERN.sub("[REDACTED]", result)
    if isinstance(value, dict): return {str(key): _redact(item, api_key, authorization or str(key).lower() == "authorization") for key, item in value.items()}
    if isinstance(value, list): return [_redact(item, api_key, authorization) for item in value]
    return value


__all__ = [
    "ContractCache", "DeepSeekClient", "GitHubPublicSourceVerifier", "ProviderReply",
    "PublicSourceAttestation", "build_provider_payload", "cache_identity",
    "parse_growth_contract_json", "validate_provider_endpoint", "verify_local_checkout_at_commit",
    "verify_local_checkout_against_public_source",
]
