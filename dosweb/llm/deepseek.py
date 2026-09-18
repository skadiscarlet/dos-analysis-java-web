from __future__ import annotations

import http.client
import hashlib
import json
import math
import os
import re
import socket
import ssl
import stat
import errno
import subprocess
import time
import threading
import selectors
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.config import DEFAULT_MODEL, LlmConfig, MAX_LLM_RETRIES, MAX_LLM_TIMEOUT_SECONDS, SUPPORTED_MODELS, model_response_matches
from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.errors import AnalyzerError
from dosweb.growth.contracts import (
    bind_provider_growth_contract,
    parse_growth_contract_json,
    validate_contract_static_evidence,
    validate_provider_growth_contract,
)
from dosweb.growth.models import BoundedSlice, GrowthContract
from dosweb.llm.cache import (
    AUTH_CACHE_FORMAT,
    MAX_RAW_RESPONSE_BYTES,
    ContractCache,
    GrowthCacheSnapshot,
    PROVIDER_ID,
    cache_identity,
    canonical_base_url,
)
from dosweb.llm.prompts import build_auth_correction_messages, build_auth_messages, build_growth_correction_payload, build_growth_messages, build_provider_payload
from dosweb.llm.schemas import (
    AUTH_CONTRACT_JSON_SCHEMA,
    AUTH_CONTRACT_RESPONSE_SCHEMA,
    AUTH_PROMPT_VERSION,
    AUTH_RESPONSE_SCHEMA_VERSION,
    GROWTH_CONTRACT_JSON_SCHEMA,
    GROWTH_CONTRACT_RESPONSE_SCHEMA,
)
from dosweb.reachability.models import AuthContract, EntrySecurityFact, LlmAuditRecord

_MAX_RESPONSE_BYTES = MAX_RAW_RESPONSE_BYTES
_MAX_GIT_BLOB_BYTES = 1_048_576
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 256
_MAX_JSON_STRING_BYTES = 65536
_MAX_REQUEST_BYTES = 131072
_MAX_REQUEST_SCAN_DEPTH = 16
_MAX_REQUEST_SCAN_NODES = 8192
_MAX_GIT_OUTPUT_BYTES = 65536
_MAX_GIT_STATUS_BYTES = 4096
_SECRET_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]+")
# Match exact credential-bearing labels in snake, kebab, camel and conventional header forms.
_CREDENTIAL_ASSIGNMENT = re.compile(r'''(?ix)(?<![a-z0-9_-])(?!feature[_-]password\b|logging[_-]token\b)(?:authorization|api[_-]?key|private[_-]?key|access[_-]?(?:token|key)|refresh[_-]?token|aws[_-]?(?:secret[_-]?access[_-]?key|access[_-]?key[_-]?id)|client[_-]?secret|db[_-]?password|password|passwd|oauth[_-]?token|token|secret|x[_-]?api[_-]?key|(?:[a-z0-9]+[_-])+(?:api[_-]?key|private[_-]?key|access[_-]?(?:token|key)|refresh[_-]?token|client[_-]?secret|password|passwd|oauth[_-]?token|token|secret))\b(?:\\?["'])?(?:\s*(?:\[\s*\])?)*\s*[:=]\s*(?:\{\s*)?(?:\\?["'])?(?!\[REDACTED\])[^\s"';,}]+''')
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
_RESPONSE_CREDENTIAL_PATTERNS = (
    ("credential_assignment", _CREDENTIAL_ASSIGNMENT),
    ("authorization_value", re.compile(r'''(?i)\b(?:bearer|basic)\s+["']?\S+''')),
    ("deepseek_key", _SECRET_PATTERN),
    ("github_token", re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("aws_access_key", re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", _JWT_PATTERN),
    ("credential_uri", _CREDENTIAL_URI_PATTERN),
)
_PII_PATTERNS = (
    ("email", _EMAIL_PATTERN),
    ("phone", _PHONE_PATTERN),
    ("ssn", _SSN_PATTERN),
)
_SLICE_CREDENTIAL_PATTERNS = (*_RESPONSE_CREDENTIAL_PATTERNS, *_PII_PATTERNS)
_GITHUB_SOURCE_PATTERN = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
_FULL_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_PRODUCTION_ENDPOINTS = frozenset({"https://apibasis.com/v1/"})
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class PublicSourceAttestation:
    public_source_url: str | None
    source_commit_sha: str | None
    verified_public: bool
    verified_clean_checkout: bool


@dataclass(frozen=True)
class ProviderReply:
    body: str
    headers: dict[str, str]


@dataclass(frozen=True)
class _CanonicalResponse:
    content: str
    semantic: object
    actual_model: str
    request_id: str


@dataclass
class _InFlightState:
    event: threading.Event
    snapshot: GrowthCacheSnapshot | None = None
    error: tuple[str, str, dict[str, object]] | None = None
    retry: bool = False


@dataclass(frozen=True)
class _AuthCacheSnapshot:
    contract: AuthContract
    raw_response: str
    accepted_prompt_variant: str
    actual_model: str
    request_id: str


@dataclass
class _AuthInFlightState:
    event: threading.Event
    snapshot: _AuthCacheSnapshot | None = None
    error: tuple[str, str, dict[str, object]] | None = None
    retry: bool = False


def _bind_auth_evidence_aliases(
    contract: AuthContract,
    alias_to_original: dict[str, str],
) -> AuthContract:
    """Bind only exact aliases owned by the current Auth bounded slice."""
    try:
        evidence_ids = tuple(alias_to_original[item] for item in contract.evidence_ids)
    except KeyError:
        contract = None  # type: ignore[assignment]
        raise AnalyzerError(
            "LLM_RESPONSE_SCHEMA_INVALID",
            "Auth Contract response violates schema.",
        ) from None
    return AuthContract(
        contract.auth_context,
        evidence_ids,
        contract.assumptions,
        contract.confidence,
    )


def _validate_auth_contract_ownership(
    contract: AuthContract,
    owned_security_ids: frozenset[str],
) -> AuthContract:
    """Reject authenticated replay that cites a different bounded security slice."""
    if any(item not in owned_security_ids for item in contract.evidence_ids):
        contract = None  # type: ignore[assignment]
        raise AnalyzerError(
            "LLM_RESPONSE_SCHEMA_INVALID",
            "Auth Contract response violates schema.",
        ) from None
    return contract


_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT: dict[str, _InFlightState] = {}
_AUTH_INFLIGHT_LOCK = threading.Lock()
_AUTH_INFLIGHT: dict[str, _AuthInFlightState] = {}
_SHAREABLE_FAILURES = frozenset(
    {
        "LLM_RESPONSE_INVALID",
        "LLM_RESPONSE_SCHEMA_INVALID",
        "LLM_RESPONSE_SENSITIVE_CONTENT",
    }
)
_CORRECTABLE_GROWTH_RESPONSE_ERRORS = frozenset(
    {"LLM_RESPONSE_SCHEMA_INVALID", "LLM_RESPONSE_SENSITIVE_CONTENT"}
)
_TERMINAL_GROWTH_RESPONSE_MESSAGES = {
    "LLM_RESPONSE_SCHEMA_INVALID": "The provider response does not match the Growth Contract schema.",
    "LLM_RESPONSE_SENSITIVE_CONTENT": "Provider response contains sensitive content.",
}
_CORRECTABLE_AUTH_RESPONSE_ERRORS = frozenset(
    {"LLM_RESPONSE_SCHEMA_INVALID", "LLM_RESPONSE_SENSITIVE_CONTENT"}
)
_TERMINAL_AUTH_RESPONSE_MESSAGES = {
    "LLM_RESPONSE_SCHEMA_INVALID": "The provider response does not match the Auth Contract schema.",
    "LLM_RESPONSE_SENSITIVE_CONTENT": "Provider response contains sensitive content.",
}


def _reset_inflight_after_fork() -> None:
    global _INFLIGHT_LOCK, _INFLIGHT, _AUTH_INFLIGHT_LOCK, _AUTH_INFLIGHT
    _INFLIGHT_LOCK = threading.Lock()
    _INFLIGHT = {}
    _AUTH_INFLIGHT_LOCK = threading.Lock()
    _AUTH_INFLIGHT = {}


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
    def __init__(self, *, opener: Callable[..., Any] | None = None, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None, process_factory: Callable[..., Any] | None = None, git_timeout_seconds: float = 60.0, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._opener = opener or build_opener(_NoRedirect()).open
        self._runner = runner
        self._process_factory = process_factory or (None if runner is not None else subprocess.Popen)
        self._git_timeout_seconds = git_timeout_seconds
        self._monotonic = monotonic
        self._attestation_cache: dict[tuple[str | None, str, str], PublicSourceAttestation] = {}

    def verify(self, config: LlmConfig) -> PublicSourceAttestation:
        return self._verify(config, self._monotonic() + self._git_timeout_seconds)

    def verify_slice(self, config: LlmConfig, slice_: BoundedSlice) -> PublicSourceAttestation:
        deadline = self._monotonic() + self._git_timeout_seconds
        attestation = self._verify(config, deadline)
        self._validate_slice(config, slice_, attestation, deadline)
        return attestation

    def _verify(self, config: LlmConfig, deadline: float) -> PublicSourceAttestation:
        source_url, source_sha, checkout = _source_requirements(config)
        if source_sha is None:
            # Local source-tree semantics: no git-commit provenance is required.
            return PublicSourceAttestation(source_url, None, False, False)
        cache_key = (source_url, source_sha, str(checkout.resolve()))
        cached = self._attestation_cache.get(cache_key)
        if cached is not None:
            return cached
        self._verify_checkout(checkout, source_sha, source_url=source_url, deadline=deadline)
        if source_url is None:
            attestation = PublicSourceAttestation(None, source_sha, False, True)
            self._attestation_cache[cache_key] = attestation
            return attestation
        owner, repository = source_url.removeprefix("https://github.com/").split("/", 1)
        repository_info = self._github_json(f"repos/{owner}/{repository}", deadline=deadline)
        commit_info = self._github_json(f"repos/{owner}/{repository}/git/commits/{source_sha}", deadline=deadline)
        if repository_info.get("private") is not False or str(commit_info.get("sha", "")).lower() != source_sha:
            _unverified()
        attestation = PublicSourceAttestation(source_url, source_sha, True, True)
        self._attestation_cache[cache_key] = attestation
        return attestation

    def validate_slice(self, config: LlmConfig, slice_: BoundedSlice, attestation: PublicSourceAttestation) -> None:
        self._validate_slice(config, slice_, attestation, self._monotonic() + self._git_timeout_seconds)

    def _validate_slice(self, config: LlmConfig, slice_: BoundedSlice, attestation: PublicSourceAttestation, deadline: float) -> None:
        source_url, source_sha, checkout = _source_requirements(config)
        if source_sha is None:
            # Local source-tree semantics: verify excerpts against the on-disk tree.
            for excerpt in slice_.source_excerpts:
                self._verify_local_excerpt(checkout, excerpt)
            return
        if (
            attestation.public_source_url != source_url
            or (attestation.source_commit_sha or "").lower() != source_sha
            or not attestation.verified_clean_checkout
        ):
            _unverified()
        self._verify_checkout(checkout, source_sha, source_url=source_url, deadline=deadline)
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

    def _verify_local_excerpt(self, checkout: Path, excerpt: object) -> None:
        relative = getattr(excerpt, "repo_relative_path", None)
        start_line = getattr(excerpt, "start_line", None)
        end_line = getattr(excerpt, "end_line", None)
        content = getattr(excerpt, "content", None)
        excerpt_sha256 = getattr(excerpt, "excerpt_sha256", None)
        if not isinstance(relative, str) or not isinstance(content, str) or not isinstance(excerpt_sha256, str):
            _unverified()
        if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1:
            _unverified()
        if isinstance(end_line, bool) or not isinstance(end_line, int) or end_line < start_line:
            _unverified()
        path = checkout / relative
        try:
            resolved = path.resolve(strict=True)
            root = checkout.resolve(strict=True)
            if not resolved.is_relative_to(root):
                _unverified()
            if resolved.is_symlink() or not resolved.is_file():
                _unverified()
            descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_GIT_BLOB_BYTES:
                    _unverified()
                raw = bytearray()
                while len(raw) <= _MAX_GIT_BLOB_BYTES:
                    chunk = os.read(descriptor, min(1024 * 1024, _MAX_GIT_BLOB_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                if len(raw) > _MAX_GIT_BLOB_BYTES:
                    _unverified()
            finally:
                os.close(descriptor)
        except OSError:
            _unverified()
        try:
            lines = bytes(raw).splitlines(keepends=True)
            if end_line > len(lines):
                _unverified()
            actual_bytes = b"".join(lines[start_line - 1:end_line])
            actual = actual_bytes.decode("utf-8")
        except (UnicodeDecodeError, IndexError):
            _unverified()
        if actual != content or hashlib.sha256(actual_bytes).hexdigest() != excerpt_sha256:
            _unverified()

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
                payload = _bounded_github_json(_read_bounded_bytes(response, _MAX_RESPONSE_BYTES, deadline=deadline, monotonic=self._monotonic))
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
        self._last_audit: LlmAuditRecord | None = None
        self._auth_cache: dict[str, _AuthCacheSnapshot] = {}

    def last_audit(self) -> LlmAuditRecord | None:
        """Return the non-secret audit record for the immediately preceding contract call."""
        return self._last_audit

    def _audit(self, kind: str, messages: list[dict[str, str]], raw: str, parsed: dict[str, object], attestation: PublicSourceAttestation, *, cache_hit: bool, request_id: str = "", actual_model: str | None = None) -> LlmAuditRecord:
        prompt = json.dumps(messages, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        schema = GROWTH_CONTRACT_RESPONSE_SCHEMA if kind == "growth" else AUTH_CONTRACT_RESPONSE_SCHEMA
        settings = {"provider": PROVIDER_ID, "protocol": "responses-v1", "base_url": canonical_base_url(self._config.base_url), "requested_model": self._config.model, "actual_model": actual_model or self._config.model, "temperature": self._config.temperature, "text_format": "json_schema_strict", "prompt_version": __import__("dosweb.llm.schemas", fromlist=["PROMPT_VERSION"]).PROMPT_VERSION if kind == "growth" else AUTH_PROMPT_VERSION, "response_schema_version": __import__("dosweb.llm.schemas", fromlist=["RESPONSE_SCHEMA_VERSION"]).RESPONSE_SCHEMA_VERSION if kind == "growth" else AUTH_RESPONSE_SCHEMA_VERSION}
        att = {"public_source_url": attestation.public_source_url or "", "source_commit_sha": attestation.source_commit_sha or "", "verified_public": attestation.verified_public, "verified_clean_checkout": attestation.verified_clean_checkout}
        return LlmAuditRecord(kind, request_id, prompt, schema, raw, parsed, settings, att, cache_hit)

    def _accept_growth_snapshot(
        self,
        snapshot: GrowthCacheSnapshot,
        slice_: BoundedSlice,
        provider_payload: Any,
        attestation: PublicSourceAttestation,
        *,
        cache_hit: bool = True,
    ) -> GrowthContract:
        """Apply this client's policy and audit settings to one immutable result."""
        response: _CanonicalResponse | None = None
        provider_contract: object = None
        rebound: GrowthContract | None = None
        rejection_code: str | None = None
        try:
            response = self._canonical_response(
                ProviderReply(snapshot.raw_response, {}),
                slice_,
                self._config.api_key,
                self._extra_secret_patterns,
            )
            _reject_sensitive_provider_id(
                snapshot.request_id,
                self._config.api_key,
                self._extra_secret_patterns,
            )
            if response.actual_model != snapshot.actual_model:
                raise AnalyzerError(
                    "LLM_RESPONSE_INVALID",
                    "Cached response model does not match its typed snapshot.",
                )
            provider_contract = validate_provider_growth_contract(response.semantic)
            rebound = bind_provider_growth_contract(
                provider_contract,
                slice_,
                provider_payload.fact_alias_to_original,
            )
            static_fact_ids = frozenset(
                fact.fact_id for fact in slice_.payload.static_facts
            )
            rebound = validate_contract_static_evidence(rebound, static_fact_ids)
            if rebound.to_dict() != snapshot.contract.to_dict():
                raise AnalyzerError(
                    "LLM_RESPONSE_SCHEMA_INVALID",
                    "Cached response does not match its typed Growth Contract.",
                )
        except AnalyzerError as exc:
            rejection_code = exc.code
        if rejection_code is not None:
            snapshot = None  # type: ignore[assignment]
            response = None
            provider_contract = None
            rebound = None
            if rejection_code == "LLM_RESPONSE_SENSITIVE_CONTENT":
                message = "Provider response contains sensitive content."
            elif rejection_code == "LLM_RESPONSE_SCHEMA_INVALID":
                message = "Cached response does not match its typed Growth Contract."
            else:
                message = "Cached Responses API envelope is invalid."
            raise AnalyzerError(rejection_code, message) from None
        assert rebound is not None
        contract = rebound
        response = None
        provider_contract = None
        rebound = None
        audit_messages = (
            provider_payload.messages
            if snapshot.accepted_prompt_variant == "initial"
            else build_growth_correction_payload(slice_).messages
        )
        self._last_audit = self._audit(
            "growth",
            audit_messages,
            snapshot.raw_response,
            contract.to_dict(),
            attestation,
            cache_hit=cache_hit,
            request_id=snapshot.request_id,
            actual_model=snapshot.actual_model,
        )
        return contract

    def classify_growth(self, slice_: BoundedSlice) -> GrowthContract:
        _validate_runtime_config(self._config)
        provider_payload = build_provider_payload(slice_)
        request_body = _encode_request(_responses_request(self._config.model, provider_payload.messages, self._config.temperature))
        _scan_transmitted_request(request_body, self._config.api_key, ())
        self._validate_remote_gate()
        attestation = self._verified_attestation(slice_)
        cache_key, identity = cache_identity(self._config, slice_)
        static_fact_ids = frozenset(fact.fact_id for fact in slice_.payload.static_facts)
        cached_snapshot = (
            self._cache.snapshot(cache_key, identity, static_fact_ids)
            if self._cache.is_usable(cache_key)
            else None
        )
        if cached_snapshot is not None:
            try:
                return self._accept_growth_snapshot(
                    cached_snapshot,
                    slice_,
                    provider_payload,
                    attestation,
                )
            except BaseException:
                cached_snapshot = None
                raise
        state, owner = _join_inflight(cache_key)
        if not owner:
            state.event.wait()
            waiter_snapshot = state.snapshot
            waiter_error = state.error
            state = None  # type: ignore[assignment]
            if waiter_snapshot is not None:
                try:
                    return self._accept_growth_snapshot(
                        waiter_snapshot,
                        slice_,
                        provider_payload,
                        attestation,
                    )
                except BaseException:
                    waiter_snapshot = None
                    raise
            if waiter_error is not None:
                code, message, details = waiter_error
                raise AnalyzerError(code, message, details)
            return self.classify_growth(slice_)
        flight_finished = False
        try:
            with self._cache.single_flight(cache_key) as cache_available:
                authenticated_entry = None
                if cache_available:
                    cached_snapshot = self._cache.snapshot(
                        cache_key,
                        identity,
                        static_fact_ids,
                    )
                    if cached_snapshot is not None:
                        _finish_inflight(cache_key, state, snapshot=cached_snapshot)
                        flight_finished = True
                        state = None  # type: ignore[assignment]
                        try:
                            return self._accept_growth_snapshot(
                                cached_snapshot,
                                slice_,
                                provider_payload,
                                attestation,
                            )
                        except BaseException:
                            cached_snapshot = None
                            raise
                    authenticated_entry = self._cache.authenticated_snapshot(
                        cache_key,
                        identity,
                    )
                reservation = self._cache.capacity_reservation(cache_key, allow_existing=authenticated_entry is not None)
                with reservation:
                    accepted_prompt_variant = "initial"
                    for response_attempt in range(2):
                        reply: ProviderReply | None = None
                        content: object = None
                        actual_model: str | None = None
                        request_id: str | None = None
                        canonical: _CanonicalResponse | None = None
                        contract: GrowthContract | None = None
                        current_payload = (
                            provider_payload
                            if response_attempt == 0
                            else build_growth_correction_payload(slice_)
                        )
                        current_body = (
                            request_body
                            if response_attempt == 0
                            else _encode_request(
                                _responses_request(
                                    self._config.model,
                                    current_payload.messages,
                                    self._config.temperature,
                                )
                            )
                        )
                        if response_attempt:
                            _scan_transmitted_request(
                                current_body,
                                self._config.api_key,
                                (),
                            )
                        terminal_response_code: str | None = None
                        try:
                            reply = self._post_with_retries(current_body, slice_)
                            canonical = self._canonical_response(
                                reply,
                                slice_,
                                self._config.api_key,
                                (),
                            )
                            content = canonical.content
                            actual_model = canonical.actual_model
                            request_id = canonical.request_id
                            contract = bind_provider_growth_contract(
                                validate_provider_growth_contract(canonical.semantic),
                                slice_,
                                current_payload.fact_alias_to_original,
                            )
                            contract = validate_contract_static_evidence(contract, static_fact_ids)
                        except AnalyzerError as exc:
                            response_code = exc.code
                            reply = None
                            content = None
                            actual_model = None
                            request_id = None
                            canonical = None
                            contract = None
                            if response_code not in _CORRECTABLE_GROWTH_RESPONSE_ERRORS:
                                current_body = None
                                request_body = None
                                raise
                            if response_attempt == 0:
                                continue
                            terminal_response_code = response_code
                        if terminal_response_code is not None:
                            current_body = None
                            request_body = None
                            raise AnalyzerError(
                                terminal_response_code,
                                _TERMINAL_GROWTH_RESPONSE_MESSAGES[terminal_response_code],
                            ) from None
                        accepted_prompt_variant = (
                            "initial" if response_attempt == 0 else "correction"
                        )
                        break
                    else:  # pragma: no cover - both loop exits are explicit
                        raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Growth Contract correction failed.")
                    audit = {"method": "POST", "url": self._endpoint(), "provider": PROVIDER_ID, "protocol": "responses-v1", "requested_model": self._config.model, "actual_model": actual_model, "provider_request_id_digest": self._cache.provider_request_id_digest(request_id), "slice_content_hash": identity["slice_content_hash"], "allow_remote_llm": self._config.allow_remote_llm, "public_source_url": attestation.public_source_url or "", "source_commit_sha": attestation.source_commit_sha or "", "verified_public": attestation.verified_public, "verified_clean_checkout": attestation.verified_clean_checkout}
                    accepted_snapshot: GrowthCacheSnapshot | None = None
                    publication_failed = False
                    published: object = True
                    if authenticated_entry is None:
                        try:
                            published = self._cache.put(
                                cache_key,
                                identity,
                                contract,
                                audit,
                                raw_response=reply.body,
                                accepted_prompt_variant=accepted_prompt_variant,
                            )
                        except BaseException:
                            publication_failed = True
                        if published is not True:
                            publication_failed = True
                    if publication_failed:
                        reply = None
                        content = None
                        actual_model = None
                        request_id = None
                        canonical = None
                        contract = None
                        accepted_snapshot = None
                        authenticated_entry = None
                        audit = None
                        published = None
                        current_payload = None
                        current_body = None
                        raise AnalyzerError(
                            "LLM_CACHE_WRITE_FAILED",
                            "Could not publish Growth Contract cache entry.",
                        ) from None
                    accepted_snapshot = GrowthCacheSnapshot(
                        contract,
                        reply.body,
                        accepted_prompt_variant,
                        actual_model,
                        request_id,
                    )
                    _finish_inflight(cache_key, state, snapshot=accepted_snapshot)
                    flight_finished = True
                    state = None  # type: ignore[assignment]
                    reply = None
                    content = None
                    actual_model = None
                    request_id = None
                    canonical = None
                    contract = None
                    authenticated_entry = None
                    audit = None
                    published = None
                    current_payload = None
                    current_body = None
                    try:
                        return self._accept_growth_snapshot(
                            accepted_snapshot,
                            slice_,
                            provider_payload,
                            attestation,
                            cache_hit=False,
                        )
                    except BaseException:
                        accepted_snapshot = None
                        raise
        except AnalyzerError as exc:
            if not flight_finished:
                if exc.code in _SHAREABLE_FAILURES:
                    _finish_inflight(cache_key, state, error=(exc.code, exc.message, _redact_mapping(exc.details, self._config.api_key)))
                else:
                    _finish_inflight(cache_key, state, retry=True)
            raise
        except BaseException:
            if not flight_finished:
                _finish_inflight(cache_key, state, retry=True)
            raise

    def _accept_auth_snapshot(
        self,
        snapshot: _AuthCacheSnapshot,
        initial_messages: list[dict[str, str]],
        correction_messages: list[dict[str, str]],
        attestation: PublicSourceAttestation,
        alias_to_original: dict[str, str],
        *,
        cache_hit: bool = True,
    ) -> AuthContract:
        """Apply this client's policy and rebuild the exact accepted Auth prompt."""
        response: _CanonicalResponse | None = None
        provider_contract: AuthContract | None = None
        rebound: AuthContract | None = None
        rejection_code: str | None = None
        try:
            response = self._canonical_response(
                ProviderReply(snapshot.raw_response, {}),
                None,
                self._config.api_key,
                self._extra_secret_patterns,
            )
            _reject_sensitive_provider_id(
                snapshot.request_id,
                self._config.api_key,
                self._extra_secret_patterns,
            )
            if response.actual_model != snapshot.actual_model:
                raise AnalyzerError(
                    "LLM_RESPONSE_INVALID",
                    "Cached response model does not match its typed snapshot.",
                )
            if not isinstance(response.semantic, dict):
                raise AnalyzerError(
                    "LLM_RESPONSE_SCHEMA_INVALID",
                    "Cached Auth Contract response violates schema.",
                )
            provider_contract = AuthContract.from_dict(response.semantic)
            rebound = _bind_auth_evidence_aliases(
                provider_contract,
                alias_to_original,
            )
            if rebound.to_dict() != snapshot.contract.to_dict():
                raise AnalyzerError(
                    "LLM_RESPONSE_SCHEMA_INVALID",
                    "Cached response does not match its typed Auth Contract.",
                )
        except AnalyzerError as exc:
            rejection_code = exc.code
        if rejection_code is not None:
            snapshot = None  # type: ignore[assignment]
            response = None
            provider_contract = None
            rebound = None
            if rejection_code == "LLM_RESPONSE_SENSITIVE_CONTENT":
                message = "Provider response contains sensitive content."
            elif rejection_code == "LLM_RESPONSE_SCHEMA_INVALID":
                message = "Cached response does not match its typed Auth Contract."
            else:
                message = "Cached Responses API envelope is invalid."
            raise AnalyzerError(rejection_code, message) from None
        assert rebound is not None
        messages = (
            initial_messages
            if snapshot.accepted_prompt_variant == "initial"
            else correction_messages
        )
        contract = rebound
        response = None
        provider_contract = None
        rebound = None
        self._last_audit = self._audit(
            "auth",
            messages,
            snapshot.raw_response,
            contract.to_dict(),
            attestation,
            cache_hit=cache_hit,
            request_id=snapshot.request_id,
            actual_model=snapshot.actual_model,
        )
        return contract

    def classify_auth(self, entry_id: str, facts: tuple[EntrySecurityFact, ...], config_facts: tuple[dict[str, object], ...] = ()) -> AuthContract:
        """Remote Auth Contract constrained to supplied security/configuration facts.

        This intentionally has a separate identity and never reuses Growth cache entries.
        """
        _validate_runtime_config(self._config)
        self._validate_remote_gate()
        attestation = self._verified_attestation()
        aliases = {fact.fact_id: f"security:{index}" for index, fact in enumerate(facts, 1)}
        alias_to_original = {alias: original for original, alias in aliases.items()}
        owned_security_ids = frozenset(aliases)
        security_locations = {
            location: f"source/security/{index}"
            for index, location in enumerate(dict.fromkeys(fact.location for fact in facts), 1)
        }
        prompt_facts = [{"fact_id": aliases[f.fact_id], "kind": f.kind, "location": security_locations[f.location], "line": f.line, "value": f.value, "coverage": f.coverage} for f in facts]
        configuration_models = tuple(
            ModeledConfigurationFact.from_dict(item) for item in config_facts
        )
        configuration_aliases = {
            config_id: f"config:{index}"
            for index, config_id in enumerate(
                dict.fromkeys(fact.config_id for fact in configuration_models), 1
            )
        }
        configuration_locations = {
            source_file: f"source/config/{index}"
            for index, source_file in enumerate(
                dict.fromkeys(fact.source_file for fact in configuration_models), 1
            )
        }
        prompt_configuration = [
            {
                "config_id": configuration_aliases[fact.config_id],
                "key": fact.key,
                "value": fact.value,
                "source_file": configuration_locations[fact.source_file],
                "source_line": fact.source_line,
                "profile": fact.profile,
                "provenance": fact.provenance,
                "default_effective": fact.default_effective,
                "status": fact.status,
            }
            for fact in configuration_models
        ]
        messages = build_auth_messages(entry_id, prompt_facts, prompt_configuration)
        correction_messages = build_auth_correction_messages(entry_id, prompt_facts, prompt_configuration)
        ownership_binding_hash = sha256_canonical_json(
            {
                "entry_id": entry_id,
                "security_bindings": [
                    {
                        "alias": aliases[fact.fact_id],
                        "fact_id": fact.fact_id,
                        "semantic_identity": fact.semantic_identity(),
                    }
                    for fact in facts
                ],
                "configuration_bindings": [
                    {
                        "alias": configuration_aliases[fact.config_id],
                        "config_id": fact.config_id,
                        "semantic_identity": fact.semantic_identity(),
                    }
                    for fact in configuration_models
                ],
            }
        )
        auth_identity = {"kind": "auth", "provider": PROVIDER_ID, "protocol": "responses-v1", "auth_cache_format": AUTH_CACHE_FORMAT, "prompt_version": AUTH_PROMPT_VERSION, "schema_version": AUTH_RESPONSE_SCHEMA_VERSION, "model": self._config.model, "temperature": self._config.temperature, "base_url": canonical_base_url(self._config.base_url), "text_format": "json_schema_strict", "response_format_schema_hash": sha256_canonical_json(AUTH_CONTRACT_JSON_SCHEMA), "messages": messages, "sha": attestation.source_commit_sha or "", "ownership_binding_hash": ownership_binding_hash}
        identity = hashlib.sha256(json.dumps(auth_identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        persisted = self._cache.get_auth_record(identity, auth_identity)
        if persisted is not None:
            try:
                contract = _validate_auth_contract_ownership(
                    AuthContract.from_dict(persisted["contract"]),
                    owned_security_ids,
                )
                cached_snapshot = _AuthCacheSnapshot(
                    contract,
                    cast(str, persisted["raw_response"]),
                    cast(str, persisted["accepted_prompt_variant"]),
                    cast(str, persisted["actual_model"]),
                    "",
                )
            except (AnalyzerError, KeyError, TypeError):
                cached_snapshot = None
            persisted = None
            if cached_snapshot is not None:
                try:
                    accepted = self._accept_auth_snapshot(
                        cached_snapshot,
                        messages,
                        correction_messages,
                        attestation,
                        alias_to_original,
                    )
                except BaseException:
                    cached_snapshot = None
                    raise
                self._auth_cache[identity] = cached_snapshot
                return accepted
        cached = self._auth_cache.get(identity)
        if cached is not None:
            cached_snapshot = cached
            cached = None
            try:
                return self._accept_auth_snapshot(
                    cached_snapshot,
                    messages,
                    correction_messages,
                    attestation,
                    alias_to_original,
                )
            except BaseException:
                cached_snapshot = None
                raise
        state, owner = _join_auth_inflight(identity)
        if not owner:
            state.event.wait()
            waiter_snapshot = state.snapshot
            waiter_error = state.error
            state = None  # type: ignore[assignment]
            if waiter_snapshot is not None:
                try:
                    accepted = self._accept_auth_snapshot(
                        waiter_snapshot,
                        messages,
                        correction_messages,
                        attestation,
                        alias_to_original,
                    )
                except BaseException:
                    waiter_snapshot = None
                    raise
                self._auth_cache[identity] = waiter_snapshot
                return accepted
            if waiter_error is not None:
                code, message, details = waiter_error
                raise AnalyzerError(code, message, details)
            return self.classify_auth(entry_id, facts, config_facts)
        flight_finished = False
        try:
            with self._cache.single_flight(identity):
                persisted = self._cache.get_auth_record(identity, auth_identity)
                if persisted is not None:
                    try:
                        contract = _validate_auth_contract_ownership(
                            AuthContract.from_dict(persisted["contract"]),
                            owned_security_ids,
                        )
                        cached_snapshot = _AuthCacheSnapshot(
                            contract,
                            cast(str, persisted["raw_response"]),
                            cast(str, persisted["accepted_prompt_variant"]),
                            cast(str, persisted["actual_model"]),
                            "",
                        )
                    except (AnalyzerError, KeyError, TypeError):
                        cached_snapshot = None
                    persisted = None
                    if cached_snapshot is not None:
                        _finish_auth_inflight(identity, state, snapshot=cached_snapshot)
                        flight_finished = True
                        state = None  # type: ignore[assignment]
                        try:
                            accepted = self._accept_auth_snapshot(
                                cached_snapshot,
                                messages,
                                correction_messages,
                                attestation,
                                alias_to_original,
                            )
                        except BaseException:
                            cached_snapshot = None
                            raise
                        self._auth_cache[identity] = cached_snapshot
                        return accepted

                with self._cache.capacity_reservation(
                    identity,
                    entry_prefix="auth-",
                ):
                    accepted_prompt_variant = "initial"
                    cache_contract: AuthContract | None = None
                    for response_attempt in range(2):
                        reply: ProviderReply | None = None
                        content: object = None
                        actual_model: str | None = None
                        request_id: str | None = None
                        canonical: _CanonicalResponse | None = None
                        parsed: object = None
                        raw: dict[str, object] | None = None
                        provider_contract: AuthContract | None = None
                        contract: AuthContract | None = None
                        current_messages = messages if response_attempt == 0 else correction_messages
                        body = _encode_request(
                            _responses_request(
                                self._config.model,
                                current_messages,
                                self._config.temperature,
                                contract_kind="auth",
                            )
                        )
                        _scan_transmitted_request(
                            body,
                            self._config.api_key,
                            (),
                        )
                        terminal_response_code: str | None = None
                        try:
                            reply = self._post_with_retries(body, None)
                            canonical = self._canonical_response(
                                reply,
                                None,
                                self._config.api_key,
                                (),
                            )
                            content = canonical.content
                            actual_model = canonical.actual_model
                            request_id = canonical.request_id
                            parsed = canonical.semantic
                            if not isinstance(parsed, dict):
                                raise AnalyzerError(
                                    "LLM_RESPONSE_SCHEMA_INVALID",
                                    "Auth Contract response violates schema.",
                                )
                            raw = parsed
                            provider_contract = AuthContract.from_dict(raw)
                            contract = _bind_auth_evidence_aliases(
                                provider_contract,
                                alias_to_original,
                            )
                        except AnalyzerError as exc:
                            response_code = exc.code
                            reply = None
                            content = None
                            actual_model = None
                            request_id = None
                            canonical = None
                            parsed = None
                            raw = None
                            provider_contract = None
                            contract = None
                            cache_contract = None
                            if response_code not in _CORRECTABLE_AUTH_RESPONSE_ERRORS:
                                raise
                            if response_attempt == 0:
                                continue
                            terminal_response_code = response_code
                        if terminal_response_code is not None:
                            raise AnalyzerError(
                                terminal_response_code,
                                _TERMINAL_AUTH_RESPONSE_MESSAGES[terminal_response_code],
                            ) from None
                        accepted_prompt_variant = (
                            "initial" if response_attempt == 0 else "correction"
                        )
                        cache_contract = contract
                        break
                    else:  # pragma: no cover - both loop exits are explicit
                        raise AnalyzerError(
                            "LLM_RESPONSE_SCHEMA_INVALID",
                            "Auth Contract correction failed.",
                        )
                    assert reply is not None and raw is not None and contract is not None
                    assert cache_contract is not None
                    assert actual_model is not None and request_id is not None
                    accepted_snapshot: _AuthCacheSnapshot | None = None
                    publication_failed = False
                    published: object = None
                    try:
                        published = self._cache.put_auth_record(
                            identity,
                            auth_identity,
                            cache_contract.to_dict(),
                            reply.body,
                            accepted_prompt_variant=accepted_prompt_variant,
                            actual_model=actual_model,
                        )
                    except BaseException:
                        publication_failed = True
                    if published is not True:
                        publication_failed = True
                    if publication_failed:
                        reply = None
                        content = None
                        actual_model = None
                        request_id = None
                        canonical = None
                        parsed = None
                        raw = None
                        provider_contract = None
                        contract = None
                        cache_contract = None
                        accepted_snapshot = None
                        published = None
                        body = None
                        raise AnalyzerError(
                            "LLM_CACHE_WRITE_FAILED",
                            "Could not publish Auth Contract cache entry.",
                        ) from None
                    accepted_snapshot = _AuthCacheSnapshot(
                        contract,
                        reply.body,
                        accepted_prompt_variant,
                        actual_model,
                        request_id,
                    )
                    _finish_auth_inflight(identity, state, snapshot=accepted_snapshot)
                    flight_finished = True
                    state = None  # type: ignore[assignment]
                    reply = None
                    content = None
                    actual_model = None
                    request_id = None
                    canonical = None
                    parsed = None
                    raw = None
                    provider_contract = None
                    contract = None
                    cache_contract = None
                    published = None
                    body = None
                    try:
                        accepted = self._accept_auth_snapshot(
                            accepted_snapshot,
                            messages,
                            correction_messages,
                            attestation,
                            alias_to_original,
                            cache_hit=False,
                        )
                    except BaseException:
                        accepted_snapshot = None
                        raise
                    self._auth_cache[identity] = accepted_snapshot
                    return accepted
        except AnalyzerError as exc:
            if not flight_finished:
                if exc.code in _SHAREABLE_FAILURES:
                    _finish_auth_inflight(
                        identity,
                        state,
                        error=(
                            exc.code,
                            exc.message,
                            _redact_mapping(exc.details, self._config.api_key),
                        ),
                    )
                else:
                    _finish_auth_inflight(identity, state, retry=True)
            raise
        except BaseException:
            if not flight_finished:
                _finish_auth_inflight(identity, state, retry=True)
            raise

    def _validate_remote_gate(self) -> None:
        validate_provider_endpoint(self._config.base_url, allow_test_transport=self._transport is not None)
        if not self._config.allow_remote_llm: raise AnalyzerError("CONFIG_REMOTE_LLM_NOT_AUTHORIZED", "Remote LLM calls require explicit authorization.")
        if not isinstance(self._config.api_key, str) or not self._config.api_key.strip(): raise AnalyzerError("CONFIG_MISSING_DEEPSEEK_API_KEY", "Provider API key must be set in the environment or config/local_secrets.json.")
        checkout = self._config.source_checkout
        if not isinstance(checkout, Path) or not checkout.is_dir() or not os.access(checkout, os.R_OK | os.X_OK):
            raise AnalyzerError("CONFIG_SOURCE_CHECKOUT_UNREADABLE", "Local source checkout must be a readable directory.")

    def _verified_attestation(self, slice_: BoundedSlice | None = None) -> PublicSourceAttestation:
        # Git commit provenance is optional metadata, not a gate. Record config
        # values verbatim (SHA lower-cased) so cache/audit identity stays consistent.
        url = self._config.public_source_url
        sha = self._config.source_commit_sha
        return PublicSourceAttestation(
            url if isinstance(url, str) and url else None,
            sha.lower() if isinstance(sha, str) and sha else None,
            False,
            False,
        )

    def _endpoint(self) -> str: return urljoin(canonical_base_url(self._config.base_url), "responses")

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
        headers = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {self._config.api_key}", "User-Agent": "pi-coding-agent"}
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
        body: str | None = None
        encoded: bytes | None = None
        envelope: object = None
        model: object = None
        output: object = None
        messages: list[dict[str, object]] | None = None
        parts: object = None
        text_parts: list[str] | None = None
        part: object = None
        text: object = None
        content: str | None = None
        headers: dict[str, str] | None = None
        request_id: object = None
        malformed = False
        try:
            body = reply.body
            if not isinstance(body, str):
                raise TypeError
            encoded = body.encode("utf-8")
            if len(encoded) > _MAX_RESPONSE_BYTES:
                raise ValueError
            envelope = _bounded_json(encoded)
            if not isinstance(envelope, dict) or envelope.get("status") != "completed":
                raise TypeError
            model = envelope.get("model")
            if not isinstance(model, str) or not model_response_matches(self._config.model, model):
                raise TypeError
            output = envelope.get("output")
            if not isinstance(output, list):
                raise TypeError
            messages = [item for item in output if isinstance(item, dict) and item.get("type") == "message" and item.get("role") == "assistant"]
            if len(messages) != 1:
                raise TypeError
            parts = messages[0].get("content")
            if not isinstance(parts, list):
                raise TypeError
            text_parts: list[str] = []
            for part in parts:
                if not isinstance(part, dict):
                    raise TypeError
                if part.get("type") != "output_text":
                    raise TypeError
                text = part.get("text")
                if not isinstance(text, str):
                    raise TypeError
                text_parts.append(text)
            content = "".join(text_parts)
            if not content:
                raise TypeError
            headers = reply.headers
            request_id = headers.get("x-request-id", headers.get("request-id", envelope.get("id", "")))
            if not isinstance(request_id, str) or len(request_id.encode("utf-8")) > 512:
                raise TypeError
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError, KeyError, TypeError):
            malformed = True
        if malformed:
            reply = None
            body = None
            encoded = None
            envelope = None
            model = None
            output = None
            messages = None
            parts = None
            text_parts = None
            part = None
            text = None
            content = None
            headers = None
            request_id = None
            raise AnalyzerError(
                "LLM_RESPONSE_INVALID",
                "Remote Responses API envelope was malformed, incomplete, or has a mismatched model.",
            ) from None
        return cast(str, content), cast(str, model), cast(str, request_id)

    def _canonical_response(
        self,
        reply: ProviderReply,
        slice_: BoundedSlice | None,
        configured_api_key: str,
        extra_patterns: tuple[tuple[str, re.Pattern[str]], ...],
    ) -> _CanonicalResponse:
        """Parse and scan one decoded Responses envelope and its semantic JSON."""
        content: object = None
        actual_model: object = None
        request_id: object = None
        envelope: object = None
        semantic: object = None
        response: _CanonicalResponse | None = None
        failure_code: str | None = None
        try:
            content, actual_model, request_id = self._response_content(reply)
            envelope = _bounded_json(reply.body.encode("utf-8"))
            _reject_sensitive_decoded_layer(
                envelope,
                slice_=None,
                configured_api_key=configured_api_key,
                extra_patterns=extra_patterns,
                semantic=False,
            )
            _reject_sensitive_response(
                content,
                slice_,
                configured_api_key,
                extra_patterns,
            )
            try:
                semantic = _bounded_json(cast(str, content).encode("utf-8"))
            except (json.JSONDecodeError, RecursionError, UnicodeError, TypeError, ValueError):
                semantic = None
                failure_code = "LLM_RESPONSE_SCHEMA_INVALID"
            if failure_code is None:
                _reject_sensitive_decoded_layer(
                    semantic,
                    slice_=slice_,
                    configured_api_key=configured_api_key,
                    extra_patterns=extra_patterns,
                    semantic=True,
                )
                _reject_sensitive_provider_id(
                    cast(str, request_id),
                    configured_api_key,
                    extra_patterns,
                )
                if not re.fullmatch(r"[A-Za-z0-9._:-]*", cast(str, request_id)):
                    failure_code = "LLM_RESPONSE_INVALID"
            if failure_code is None:
                response = _CanonicalResponse(
                    cast(str, content),
                    semantic,
                    cast(str, actual_model),
                    cast(str, request_id),
                )
        except AnalyzerError as exc:
            failure_code = exc.code
        except (json.JSONDecodeError, RecursionError, UnicodeError, TypeError, ValueError):
            failure_code = "LLM_RESPONSE_INVALID"
        if failure_code is not None:
            reply = None  # type: ignore[assignment]
            content = None
            actual_model = None
            request_id = None
            envelope = None
            semantic = None
            response = None
            if failure_code == "LLM_RESPONSE_SENSITIVE_CONTENT":
                message = "Provider response contains sensitive content."
            elif failure_code == "LLM_RESPONSE_SCHEMA_INVALID":
                message = "The provider response does not match the contract schema."
            else:
                message = "Remote Responses API envelope was malformed, incomplete, or has a mismatched model."
            raise AnalyzerError(failure_code, message) from None
        assert response is not None
        return response


def _join_inflight(key: str) -> tuple[_InFlightState, bool]:
    with _INFLIGHT_LOCK:
        state = _INFLIGHT.get(key)
        if state is not None:
            return state, False
        state = _InFlightState(threading.Event())
        _INFLIGHT[key] = state
        return state, True


def _finish_inflight(key: str, state: _InFlightState, *, snapshot: GrowthCacheSnapshot | None = None, error: tuple[str, str, dict[str, object]] | None = None, retry: bool = False) -> None:
    with _INFLIGHT_LOCK:
        if _INFLIGHT.get(key) is state:
            del _INFLIGHT[key]
        state.snapshot = snapshot
        state.error = error
        state.retry = retry
        state.event.set()


def _join_auth_inflight(key: str) -> tuple[_AuthInFlightState, bool]:
    with _AUTH_INFLIGHT_LOCK:
        state = _AUTH_INFLIGHT.get(key)
        if state is not None:
            return state, False
        state = _AuthInFlightState(threading.Event())
        _AUTH_INFLIGHT[key] = state
        return state, True


def _finish_auth_inflight(
    key: str,
    state: _AuthInFlightState,
    *,
    snapshot: _AuthCacheSnapshot | None = None,
    error: tuple[str, str, dict[str, object]] | None = None,
    retry: bool = False,
) -> None:
    with _AUTH_INFLIGHT_LOCK:
        if _AUTH_INFLIGHT.get(key) is state:
            del _AUTH_INFLIGHT[key]
        state.snapshot = snapshot
        state.error = error
        state.retry = retry
        state.event.set()


def _responses_request(
    model: str,
    messages: object,
    temperature: object,
    *,
    contract_kind: str = "growth",
) -> dict[str, object]:
    if not isinstance(messages, list) or len(messages) != 2:
        raise AnalyzerError("LLM_REQUEST_INVALID", "Responses request requires exactly one system and one user prompt.")
    system, user = messages
    if not isinstance(system, dict) or not isinstance(user, dict) or system.get("role") != "system" or user.get("role") != "user":
        raise AnalyzerError("LLM_REQUEST_INVALID", "Responses request prompt roles are invalid.")
    instructions, user_text = system.get("content"), user.get("content")
    if not isinstance(instructions, str) or not instructions or not isinstance(user_text, str) or not user_text:
        raise AnalyzerError("LLM_REQUEST_INVALID", "Responses request prompt content is invalid.")
    if contract_kind == "growth":
        name, schema = "growth_contract", GROWTH_CONTRACT_JSON_SCHEMA
    elif contract_kind == "auth":
        name, schema = "auth_contract", AUTH_CONTRACT_JSON_SCHEMA
    else:
        raise AnalyzerError("LLM_REQUEST_INVALID", "Responses request contract kind is invalid.")
    return {
        "model": model,
        "instructions": instructions,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
        "temperature": temperature,
        "text": {
            "format": {
                "type": "json_schema",
                "name": name,
                "strict": True,
                "schema": schema,
            }
        },
        "store": False,
        "stream": False,
    }


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
            # An assignment whose value was already redacted to the fixed token is
            # not a live credential and must not trigger the gate.
            value_index = index + len(operator)
            while value_index < len(code) and code[value_index].isspace():
                value_index += 1
            return not code.startswith("[REDACTED]", value_index)
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


def _redacted_value_at(content: str, index: int) -> bool:
    i = index
    while i < len(content) and content[i] in " \t":
        i += 1
    return content.startswith("[REDACTED]", i)


def _sensitive_method_call(item: str) -> bool:
    """Flag a credential mutator/header call only when its value is not already redacted."""
    masked = _java_comments_as_space(item)
    for match in _SENSITIVE_MUTATOR_CALL.finditer(masked):
        if not _redacted_value_at(masked, match.end()):
            return True
    for match in _GENERIC_CREDENTIAL_CALL.finditer(masked):
        if not _redacted_value_at(masked, match.end()):
            return True
    return False


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
    if any(_sensitive_method_call(item) for item in strings):
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
    if configured_api_key and configured_api_key in content: raise AnalyzerError("LLM_BOUNDED_SLICE_SECRET_DETECTED", "Bounded slice credential scan failed.", {"pattern_id": "configured_credential"})
    for pattern_id, pattern in (*_SLICE_CREDENTIAL_PATTERNS, *extra_patterns):
        target = credential_content if pattern_id == "credential_assignment" else content
        if pattern.search(target): raise AnalyzerError("LLM_BOUNDED_SLICE_SECRET_DETECTED", "Bounded slice credential scan failed.", {"pattern_id": pattern_id})


def scan_slice_for_credentials(slice_: BoundedSlice, configured_api_key: str, extra_patterns: tuple[tuple[str, re.Pattern[str]], ...] = ()) -> None:
    payload = _responses_request(DEFAULT_MODEL, build_growth_messages(slice_), 0)
    _scan_transmitted_request(_encode_request(payload), configured_api_key, extra_patterns)


def _response_text_is_sensitive(
    content: object,
    configured_api_key: str,
    extra_patterns: tuple[tuple[str, re.Pattern[str]], ...],
    *,
    include_pii: bool,
) -> bool:
    """Canonical response predicate shared by envelope, semantic and ID scans."""
    if not isinstance(content, str):
        return False
    patterns = (
        (*_RESPONSE_CREDENTIAL_PATTERNS, *_PII_PATTERNS, *extra_patterns)
        if include_pii
        else (*_RESPONSE_CREDENTIAL_PATTERNS, *extra_patterns)
    )
    return bool(
        (configured_api_key and configured_api_key in content)
        or _sensitive_java_assignment(content)
        or any(pattern.search(content) for _, pattern in patterns)
    )


def _reject_sensitive_envelope(content: object, configured_api_key: str, extra_patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> None:
    """Scan a Responses envelope for credentials, not generic metadata PII."""
    if _response_text_is_sensitive(
        content,
        configured_api_key,
        extra_patterns,
        include_pii=False,
    ):
        raise AnalyzerError("LLM_RESPONSE_SENSITIVE_CONTENT", "Provider response contains sensitive content.")


def _reject_sensitive_response(content: object, slice_: BoundedSlice | None, configured_api_key: str, extra_patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> None:
    if not isinstance(content, str):
        return
    meaningful_echo = slice_ is not None and any(
        len(excerpt.content.encode("utf-8")) >= 64 and excerpt.content in content
        for excerpt in slice_.source_excerpts
    )
    if _response_text_is_sensitive(
        content,
        configured_api_key,
        extra_patterns,
        include_pii=True,
    ) or meaningful_echo:
        raise AnalyzerError("LLM_RESPONSE_SENSITIVE_CONTENT", "Provider response contains sensitive content.")


def _reject_sensitive_provider_id(value: str, configured_api_key: str, extra_patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> None:
    if value and _response_text_is_sensitive(
        value,
        configured_api_key,
        extra_patterns,
        include_pii=False,
    ):
        raise AnalyzerError("LLM_RESPONSE_SENSITIVE_CONTENT", "Provider response contains sensitive content.")


def _reject_sensitive_decoded_layer(
    value: object,
    *,
    slice_: BoundedSlice | None,
    configured_api_key: str,
    extra_patterns: tuple[tuple[str, re.Pattern[str]], ...],
    semantic: bool,
) -> None:
    """Scan both decoded values and canonical key/value context."""
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    texts = (rendered, *_all_strings(value))
    for text in texts:
        if semantic:
            _reject_sensitive_response(
                text,
                slice_,
                configured_api_key,
                extra_patterns,
            )
        else:
            _reject_sensitive_envelope(
                text,
                configured_api_key,
                extra_patterns,
            )


def _is_retryable_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, InterruptedError, http.client.RemoteDisconnected, http.client.IncompleteRead)):
        return True
    if isinstance(exc, (ssl.SSLEOFError, ssl.SSLZeroReturnError)):
        return True
    if isinstance(exc, ssl.SSLError):
        return False
    if isinstance(exc, socket.gaierror):
        return exc.errno == getattr(socket, "EAI_AGAIN", None)
    if isinstance(exc, URLError):
        return (
            _is_retryable_network_error(exc.reason)
            if isinstance(exc.reason, BaseException)
            else _transient_network_message(exc.reason)
        )
    if isinstance(exc, ConnectionError):
        return True
    if isinstance(exc, OSError):
        return exc.errno in {errno.EINTR, errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE} or (
            exc.errno is None and _transient_network_message(exc)
        )
    return False


def _transient_network_message(value: object) -> bool:
    """Recognize bounded proxy/gateway failures that urllib exposes without errno."""
    try:
        text = str(value).casefold()[:512]
    except (TypeError, ValueError, RuntimeError):
        return False
    return any(
        marker in text
        for marker in (
            "timed out",
            "timeout",
            "temporar",
            "connection reset",
            "connection aborted",
            "remote end closed",
            "unexpected eof",
            "tunnel connection failed: 408",
            "tunnel connection failed: 425",
            "tunnel connection failed: 429",
            "tunnel connection failed: 500",
            "tunnel connection failed: 502",
            "tunnel connection failed: 503",
            "tunnel connection failed: 504",
        )
    )


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
    if canonical in _PRODUCTION_ENDPOINTS: return canonical
    if not allow_test_transport or parsed.hostname not in _LOOPBACK_HOSTS: raise AnalyzerError("CONFIG_UNSAFE_LLM_ENDPOINT", "The LLM endpoint must be the canonical production endpoint or a loopback test server.")
    return canonical


def _validate_runtime_config(config: LlmConfig) -> None:
    if not isinstance(config.api_key, str) or not config.api_key.strip():
        raise AnalyzerError("CONFIG_MISSING_DEEPSEEK_API_KEY", "Provider API key must be set in the environment or config/local_secrets.json.")
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


def _source_requirements(config: LlmConfig) -> tuple[str | None, str | None, Path]:
    source_url, source_sha, checkout = config.public_source_url, config.source_commit_sha, config.source_checkout
    if not isinstance(checkout, Path):
        _unverified()
    if not isinstance(source_sha, str) or _FULL_SHA_PATTERN.fullmatch(source_sha) is None:
        source_sha = None
    else:
        source_sha = source_sha.lower()
    if source_url is None:
        return None, source_sha, checkout
    if not isinstance(source_url, str) or _GITHUB_SOURCE_PATTERN.fullmatch(source_url) is None:
        source_url = None
    else:
        source_url = _canonical_origin_url(source_url)
    return source_url, source_sha, checkout


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


def _bounded_github_json(data: bytes) -> object:
    """Parse bounded GitHub API metadata without the provider envelope's 64-key cap."""
    if len(data) > _MAX_RESPONSE_BYTES:
        raise ValueError("too large")
    value = json.loads(data.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    seen = [0]
    def check(item: object, depth: int = 0) -> None:
        seen[0] += 1
        if seen[0] > 4096 or depth > 32:
            raise ValueError("github metadata too large")
        if isinstance(item, str) and len(item.encode("utf-8")) > _MAX_JSON_STRING_BYTES:
            raise ValueError("string too large")
        if isinstance(item, dict):
            if len(item) > 256:
                raise ValueError("object too large")
            for child in item.values():
                check(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 256:
                raise ValueError("array too large")
            for child in item:
                check(child, depth + 1)
        elif isinstance(item, str):
            pass
        elif item is not None and not isinstance(item, (bool, int, float)):
            raise ValueError("unsupported json value")
    check(value)
    return value


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
