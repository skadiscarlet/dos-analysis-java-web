from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dosweb.artifacts.identifiers import canonical_json, sha256_canonical_json
from dosweb.config import DEFAULT_MODEL, SUPPORTED_MODELS, model_response_matches
from dosweb.errors import AnalyzerError
from dosweb.filesystem import CloseRangePreActionError
from dosweb.growth.contracts import validate_contract_static_evidence, validate_growth_contract
from dosweb.growth.models import BoundedSlice, GrowthContract
from dosweb.llm.schemas import GROWTH_CONTRACT_JSON_SCHEMA, PROMPT_VERSION, RESPONSE_SCHEMA_VERSION

_CACHE_FORMAT = "growth-contract-cache-v14"
AUTH_CACHE_FORMAT = "auth-contract-cache-v5"
PROVIDER_ID = "rightapi_responses"
_AUTH_CACHE_HMAC_DOMAIN = f"{AUTH_CACHE_FORMAT}\0".encode("ascii")
_LOCK_STRIPES = 64
_LOCKS_GUARD = threading.Lock()
_LOCKS: tuple[threading.Lock, ...] = tuple(threading.Lock() for _ in range(_LOCK_STRIPES))
_CAPACITY_LOCK = threading.Lock()
_FORK_OWNERSHIP_GUARD = threading.Lock()
_ACTIVE_RESERVATIONS = threading.local()
_ACTIVE_FLOCK_FDS: dict[int, _ActiveFlockOwnership] = {}
_ACTIVE_CACHE_DIRECTORIES: dict[int, _ActiveCacheDirectory] = {}
_ACTIVE_TRANSIENT_FDS: dict[int, _TransientDescriptorOwnership] = {}
_LOCKS_PID = os.getpid()


@dataclass(frozen=True)
class _ActiveFlockOwnership:
    descriptor: int
    pid: int


@dataclass(frozen=True)
class _TransientDescriptorOwnership:
    descriptor: int
    pid: int


@dataclass
class _TemporaryNameOwnership:
    name: str | None


@dataclass
class _ActiveCacheDirectory:
    path_key: str
    descriptor: int
    device: int
    inode: int
    owner_pid: int
    owner_thread_id: int
    reservations: set[str]


def _reset_locks_after_fork() -> None:
    global _LOCKS_GUARD, _LOCKS, _CAPACITY_LOCK, _FORK_OWNERSHIP_GUARD, _ACTIVE_RESERVATIONS, _ACTIVE_FLOCK_FDS, _ACTIVE_CACHE_DIRECTORIES, _ACTIVE_TRANSIENT_FDS, _LOCKS_PID
    for descriptor in tuple(_ACTIVE_FLOCK_FDS):
        try:
            os.close(descriptor)
        except OSError:
            pass
    for state in tuple(_ACTIVE_CACHE_DIRECTORIES.values()):
        descriptor = state.descriptor
        state.descriptor = -1
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
    for descriptor in tuple(_ACTIVE_TRANSIENT_FDS):
        try:
            os.close(descriptor)
        except OSError:
            pass
    _LOCKS_GUARD = threading.Lock()
    _LOCKS = tuple(threading.Lock() for _ in range(_LOCK_STRIPES))
    _CAPACITY_LOCK = threading.Lock()
    _FORK_OWNERSHIP_GUARD = threading.Lock()
    _ACTIVE_RESERVATIONS = threading.local()
    _ACTIVE_FLOCK_FDS = {}
    _ACTIVE_CACHE_DIRECTORIES = {}
    _ACTIVE_TRANSIENT_FDS = {}
    _LOCKS_PID = os.getpid()


def _lock_ownership_before_fork() -> None:
    _FORK_OWNERSHIP_GUARD.acquire()


def _unlock_ownership_after_fork_parent() -> None:
    _FORK_OWNERSHIP_GUARD.release()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        before=_lock_ownership_before_fork,
        after_in_parent=_unlock_ownership_after_fork_parent,
        after_in_child=_reset_locks_after_fork,
    )
_AUDIT_KEYS = frozenset({"method", "url", "provider", "protocol", "requested_model", "actual_model", "provider_request_id_digest", "slice_content_hash", "allow_remote_llm", "public_source_url", "source_commit_sha", "verified_public", "verified_clean_checkout"})
_ENTRY_KEYS = frozenset({"cache_format", "cache_key", "response_schema_version", "identity", "identity_hash", "request_audit", "audit_hash", "accepted_prompt_variant", "raw_response", "raw_response_hash", "contract", "contract_hash", "entry_hash", "entry_hmac"})
_UNSIGNED_ENTRY_KEYS = _ENTRY_KEYS - {"entry_hmac"}
_MAX_CACHE_BYTES = 524288
_MAX_CACHE_ENTRIES = 256
_MAX_CACHE_TOTAL_BYTES = _MAX_CACHE_ENTRIES * _MAX_CACHE_BYTES
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 8192
_MAX_JSON_COLLECTION = 256
MAX_RAW_RESPONSE_BYTES = 131072
_MAX_JSON_STRING_BYTES = MAX_RAW_RESPONSE_BYTES
_TEMPORARY_NAME = re.compile(r"^\.[0-9a-f]{64}\.[0-9a-f]{32}\.tmp$")


@dataclass(frozen=True)
class GrowthCacheSnapshot:
    contract: GrowthContract
    raw_response: str
    accepted_prompt_variant: str
    actual_model: str
    request_id: str


def canonical_base_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("base URL must be a string")
    parsed = urlsplit(value)
    raw_authority = parsed.netloc
    if (
        not raw_authority or "@" in raw_authority or raw_authority.endswith(":")
        or parsed.scheme not in {"http", "https"} or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment
    ):
        raise ValueError("invalid base URL")
    try:
        host = parsed.hostname.lower()
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid base URL port") from exc
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port is None else f"{rendered_host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, f"{parsed.path.rstrip('/')}/", "", ""))


def cache_identity(config: object, slice_: BoundedSlice) -> tuple[str, dict[str, object]]:
    normalized = _normalized_slice(slice_)
    identity = {
        "provider": PROVIDER_ID,
        "protocol": "responses-v1",
        "base_url": canonical_base_url(getattr(config, "base_url")),
        "model": getattr(config, "model"),
        "temperature": getattr(config, "temperature"),
        "timeout_seconds": getattr(config, "timeout_seconds"),
        "cache_format": _CACHE_FORMAT,
        "prompt_version": PROMPT_VERSION,
        "response_schema_version": RESPONSE_SCHEMA_VERSION,
        "text_format": "json_schema_strict",
        "response_format_schema_hash": sha256_canonical_json(GROWTH_CONTRACT_JSON_SCHEMA),
        "attestation_schema_version": "public-source-attestation-v1",
        "public_source_url": getattr(config, "public_source_url") or "",
        "source_commit_sha": (getattr(config, "source_commit_sha") or "").lower(),
        "slice_content_hash": sha256_canonical_json(normalized),
        "request_method": "POST",
        "request_url": f"{canonical_base_url(getattr(config, 'base_url'))}responses",
        "allow_remote_llm": getattr(config, "allow_remote_llm"),
        "verified_public": False,
        "verified_clean_checkout": False,
    }
    return sha256_canonical_json(identity), identity


class ContractCache:
    """A cache that treats disk state as hostile until API-key authenticated."""

    def __init__(self, cache_dir: Path, authentication_key: str) -> None:
        if not isinstance(authentication_key, str):
            raise ValueError("cache authentication key must be a string")
        # Freeze cwd-dependent input exactly once without resolving symlinks.
        self._cache_dir = Path(cache_dir).absolute()
        self._authentication_key = authentication_key.encode("utf-8")

    def get(self, key: str, identity: Mapping[str, object], static_fact_ids: frozenset[str]) -> GrowthContract | None:
        snapshot = self.snapshot(key, identity, static_fact_ids)
        return None if snapshot is None else snapshot.contract

    def snapshot(
        self,
        key: str,
        identity: Mapping[str, object],
        static_fact_ids: frozenset[str],
    ) -> GrowthCacheSnapshot | None:
        snapshot = self.authenticated_snapshot(key, identity)
        if snapshot is None:
            return None
        try:
            contract = validate_contract_static_evidence(snapshot.contract, static_fact_ids)
        except AnalyzerError:
            return None
        return GrowthCacheSnapshot(
            contract,
            snapshot.raw_response,
            snapshot.accepted_prompt_variant,
            snapshot.actual_model,
            snapshot.request_id,
        )

    def authenticated_contract(self, key: str, identity: Mapping[str, object]) -> GrowthContract | None:
        """Return an authenticated typed entry without current-slice evidence checks."""
        snapshot = self.authenticated_snapshot(key, identity)
        return None if snapshot is None else snapshot.contract

    def authenticated_snapshot(
        self,
        key: str,
        identity: Mapping[str, object],
    ) -> GrowthCacheSnapshot | None:
        """Return one fully authenticated immutable Growth cache snapshot."""
        return self._strict_growth_entry(key, identity)

    def _strict_growth_entry(
        self,
        key: str,
        identity: Mapping[str, object],
    ) -> GrowthCacheSnapshot | None:
        """Read one Growth entry only after every authenticated field is valid."""
        if not _safe_key(key):
            return None
        directory_ownership = self._open_cache_dir(create=False)
        if directory_ownership is None:
            return None
        directory = directory_ownership.descriptor
        try:
            data = _read_private_regular_file(directory, f"{key}.json")
            if data is None:
                return None
            raw = _strict_load(data)
            if not isinstance(raw, dict) or set(raw) != _ENTRY_KEYS:
                return None
            if (
                raw["cache_format"] != _CACHE_FORMAT
                or raw["cache_key"] != key
                or raw["response_schema_version"] != RESPONSE_SCHEMA_VERSION
                or raw["identity"] != identity
            ):
                return None
            if raw["identity_hash"] != sha256_canonical_json(identity):
                return None
            audit = raw["request_audit"]
            if not _valid_audit(audit, identity) or raw["audit_hash"] != sha256_canonical_json(audit):
                return None
            actual_model = audit["actual_model"]
            if not isinstance(actual_model, str):
                return None
            raw_response = raw["raw_response"]
            if not isinstance(raw_response, str) or len(raw_response.encode("utf-8")) > MAX_RAW_RESPONSE_BYTES or raw["raw_response_hash"] != hashlib.sha256(raw_response.encode("utf-8")).hexdigest():
                return None
            prompt_variant = raw["accepted_prompt_variant"]
            if not isinstance(prompt_variant, str) or prompt_variant not in {"initial", "correction"}:
                return None
            contract_payload = raw["contract"]
            if not isinstance(contract_payload, dict) or raw["contract_hash"] != sha256_canonical_json(contract_payload):
                return None
            unsigned = {name: raw[name] for name in _UNSIGNED_ENTRY_KEYS}
            stable = {name: raw[name] for name in _UNSIGNED_ENTRY_KEYS if name != "entry_hash"}
            if raw["entry_hash"] != sha256_canonical_json(stable):
                return None
            if not isinstance(raw["entry_hmac"], str) or not hmac.compare_digest(raw["entry_hmac"], self._entry_hmac(unsigned)):
                return None
            return GrowthCacheSnapshot(
                validate_growth_contract(contract_payload),
                raw_response,
                prompt_variant,
                actual_model,
                "",
            )
        except (OSError, RecursionError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError, AnalyzerError):
            return None
        finally:
            _close_transient_descriptor(directory_ownership)

    def is_usable(self, key: str) -> bool:
        """Return whether the directory and fixed locks are safe to trust."""
        if not _safe_key(key):
            return False
        directory_ownership = self._open_cache_dir(create=False)
        if directory_ownership is None:
            return False
        directory = directory_ownership.descriptor
        stripe = int(key[:8], 16) % _LOCK_STRIPES
        try:
            return not _entry_is_unsafe(directory, f".stripe-{stripe:02d}.lock") and not _entry_is_unsafe(directory, ".capacity.lock")
        finally:
            _close_transient_descriptor(directory_ownership)

    def require_capacity(self, key: str) -> None:
        with self.capacity_reservation(key):
            pass

    @contextmanager
    def capacity_reservation(self, key: str, *, allow_existing: bool = False, entry_prefix: str = "") -> Iterator[None]:
        if not _safe_key(key):
            raise ValueError("invalid cache key")
        if entry_prefix not in {"", "auth-"}:
            raise ValueError("invalid cache entry prefix")
        reservation = f"{entry_prefix}{key}"
        active_directory = _active_cache_directory(self._cache_dir)
        reserved_directories = tuple(
            state
            for state in getattr(_ACTIVE_RESERVATIONS, "directories", {}).values()
            if state.reservations
        )
        if reserved_directories:
            if (
                reserved_directories == (active_directory,)
                and active_directory.reservations == {reservation}
            ):
                yield
                return
            raise AnalyzerError("LLM_CACHE_LOCK_FAILED", "LLM cache lock order is invalid.")
        with _CAPACITY_LOCK:
            transaction = _begin_cache_directory_transaction(self._cache_dir, create=True)
            if transaction is None:
                raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache directory is unsafe.")
            active_directory, owns_transaction = transaction
            directory = active_directory.descriptor
            descriptor: int | None = None
            ownership: _ActiveFlockOwnership | None = None
            try:
                opened = _open_active_flock(directory, ".capacity.lock")
                if opened is None:
                    raise AnalyzerError("LLM_CACHE_LOCK_FAILED", "LLM cache capacity lock is unsafe.")
                descriptor, ownership = opened
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                destination = f"{entry_prefix}{key}.json"
                if _entry_is_unsafe(directory, destination):
                    raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache destination is unsafe.")
                exists = _entry_exists(directory, destination)
                if exists and not allow_existing:
                    raise AnalyzerError("LLM_CACHE_CONFLICT", "An existing LLM cache entry could not be reused safely.")
                capacity_destination = f".refresh-{key}" if exists else destination
                _require_cache_capacity(directory, capacity_destination, _MAX_CACHE_BYTES)
                active_directory.reservations.add(reservation)
                try:
                    yield
                finally:
                    active_directory.reservations.discard(reservation)
            finally:
                try:
                    try:
                        if _active_flock_is_owned(ownership):
                            try:
                                fcntl.flock(ownership.descriptor, fcntl.LOCK_UN)
                            except OSError:
                                pass
                    finally:
                        _close_active_flock(ownership)
                finally:
                    _end_cache_directory_transaction(active_directory, owns_transaction)

    @contextmanager
    def single_flight(self, key: str) -> Iterator[bool]:
        if not _safe_key(key):
            raise ValueError("invalid cache key")
        if getattr(_ACTIVE_RESERVATIONS, "directories", {}):
            raise AnalyzerError("LLM_CACHE_LOCK_FAILED", "LLM cache lock order is invalid.")
        global _LOCKS_PID
        if _LOCKS_PID != os.getpid():
            _reset_locks_after_fork()
        stripe = int(key[:8], 16) % _LOCK_STRIPES
        thread_lock = _LOCKS[stripe]
        with thread_lock:
            transaction = _begin_cache_directory_transaction(self._cache_dir, create=True)
            if transaction is None:
                raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache locking is unavailable.")
            active_directory, owns_transaction = transaction
            directory = active_directory.descriptor
            lock_descriptor: int | None = None
            ownership: _ActiveFlockOwnership | None = None
            try:
                opened = _open_active_flock(directory, f".stripe-{stripe:02d}.lock")
                if opened is None:
                    raise AnalyzerError("LLM_CACHE_LOCK_FAILED", "LLM cache lock is unsafe.")
                lock_descriptor, ownership = opened
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
                try:
                    yield True
                finally:
                    if _active_flock_is_owned(ownership):
                        fcntl.flock(ownership.descriptor, fcntl.LOCK_UN)
            finally:
                try:
                    _close_active_flock(ownership)
                finally:
                    _end_cache_directory_transaction(active_directory, owns_transaction)

    def audit_payload(self, key: str, identity: Mapping[str, object]) -> tuple[str, dict[str, object], str] | None:
        """Return authenticated response, contract, and accepted prompt variant."""
        validated = self._strict_growth_entry(key, identity)
        if validated is None:
            return None
        return (
            validated.raw_response,
            validated.contract.to_dict(),
            validated.accepted_prompt_variant,
        )

    def put(self, key: str, identity: Mapping[str, object], contract: GrowthContract, request_audit: Mapping[str, object], *, raw_response: str = "", accepted_prompt_variant: str = "initial") -> bool:
        if not _safe_key(key) or not _valid_audit(request_audit, identity) or accepted_prompt_variant not in {"initial", "correction"}:
            raise ValueError("invalid cache entry")
        if not isinstance(raw_response, str):
            raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "LLM cache response is invalid.")
        try:
            raw_response_bytes = raw_response.encode("utf-8")
        except UnicodeError:
            raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "LLM cache response is invalid.") from None
        if len(raw_response_bytes) > MAX_RAW_RESPONSE_BYTES:
            raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "LLM cache response exceeds its byte limit.")
        active_directory = _active_cache_directory(self._cache_dir)
        if active_directory is None or key not in active_directory.reservations:
            with self.capacity_reservation(key):
                return self.put(
                    key,
                    identity,
                    contract,
                    request_audit,
                    raw_response=raw_response,
                    accepted_prompt_variant=accepted_prompt_variant,
                )
        directory_ownership = self._open_cache_dir(create=True)
        if directory_ownership is None:
            return False
        directory = directory_ownership.descriptor
        temporary_name_ownership: _TemporaryNameOwnership | None = None
        try:
            destination = f"{key}.json"
            if _entry_is_unsafe(directory, destination):
                raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache destination is unsafe.")
            if _entry_exists(directory, destination):
                raise AnalyzerError("LLM_CACHE_CONFLICT", "LLM cache entries are immutable once published.")
            contract_payload = contract.to_dict()
            entry: dict[str, object] = {
                "cache_format": _CACHE_FORMAT,
                "cache_key": key,
                "response_schema_version": RESPONSE_SCHEMA_VERSION,
                "identity": dict(identity),
                "identity_hash": sha256_canonical_json(identity),
                "request_audit": dict(request_audit),
                "audit_hash": sha256_canonical_json(request_audit),
                "accepted_prompt_variant": accepted_prompt_variant,
                "raw_response": raw_response,
                "raw_response_hash": hashlib.sha256(raw_response_bytes).hexdigest(),
                "contract": contract_payload,
                "contract_hash": sha256_canonical_json(contract_payload),
            }
            entry["entry_hash"] = sha256_canonical_json(entry)
            entry["entry_hmac"] = self._entry_hmac(entry)
            serialized_entry = canonical_json(entry)
            if len(serialized_entry) > _MAX_CACHE_BYTES:
                raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "LLM cache entry exceeds its byte limit.")
            _require_cache_capacity(directory, destination, len(serialized_entry))
            temporary_name, temporary_ownership = _create_private_temporary(directory, key)
            temporary_name_ownership = _TemporaryNameOwnership(temporary_name)
            try:
                _write_all(temporary_ownership.descriptor, serialized_entry)
                os.fsync(temporary_ownership.descriptor)
            finally:
                _close_transient_descriptor(temporary_ownership)
            if _entry_is_unsafe(directory, destination):
                raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache destination became unsafe.")
            if _entry_exists(directory, destination):
                raise AnalyzerError("LLM_CACHE_CONFLICT", "LLM cache entries are immutable once published.")
            os.link(temporary_name, destination, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            _retire_temporary_name(directory, temporary_name_ownership)
            os.fsync(directory)
        except AnalyzerError:
            raise
        except OSError as exc:
            raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "Could not publish LLM cache entry.") from exc
        finally:
            try:
                try:
                    _retire_temporary_name(directory, temporary_name_ownership)
                except OSError:
                    pass
            finally:
                _close_transient_descriptor(directory_ownership)
        return True

    def get_auth_record(self, key: str, identity: Mapping[str, object]) -> dict[str, object] | None:
        """Read only v5 Auth records; older authenticated identities stay cold."""
        if not _safe_key(key):
            return None
        directory_ownership = self._open_cache_dir(create=False)
        if directory_ownership is None:
            return None
        directory = directory_ownership.descriptor
        name = f"auth-{key}.json"
        try:
            loaded = _read_private_regular_file_with_stat(directory, name)
            if loaded is None:
                return None
            data, info = loaded
            raw = _strict_load(data)
            required = {"cache_format", "cache_key", "identity", "contract", "raw_response", "accepted_prompt_variant", "actual_model", "entry_hash", "entry_hmac"}
            if not isinstance(raw, dict) or set(raw) != required or raw.get("cache_key") != key or raw.get("identity") != identity:
                return None
            unsigned = {name: raw[name] for name in required - {"entry_hmac"}}
            valid = (
                raw.get("entry_hash") == sha256_canonical_json({name: raw[name] for name in unsigned if name != "entry_hash"})
                and isinstance(raw.get("entry_hmac"), str)
                and isinstance(raw.get("contract"), dict)
                and isinstance(raw.get("raw_response"), str)
                and raw.get("accepted_prompt_variant") in {"initial", "correction"}
                and _valid_auth_actual_model(identity, raw.get("actual_model"))
            )
            if not valid:
                return None
            format_ = raw.get("cache_format")
            if format_ == AUTH_CACHE_FORMAT:
                if not hmac.compare_digest(raw["entry_hmac"], hmac.new(self._authentication_key, _AUTH_CACHE_HMAC_DOMAIN + canonical_json(unsigned), hashlib.sha256).hexdigest()):
                    return None
                return {"contract": dict(raw["contract"]), "raw_response": raw["raw_response"], "accepted_prompt_variant": raw["accepted_prompt_variant"], "actual_model": raw["actual_model"]}
            return None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError):
            return None
        finally:
            _close_transient_descriptor(directory_ownership)

    def put_auth_record(self, key: str, identity: Mapping[str, object], contract: Mapping[str, object], raw_response: str, *, accepted_prompt_variant: str = "initial", actual_model: str = DEFAULT_MODEL) -> bool:
        """Atomically persist a bounded Auth Contract response; no credentials are accepted."""
        if not _safe_key(key) or not isinstance(contract, Mapping) or not isinstance(raw_response, str) or len(raw_response.encode()) > _MAX_JSON_STRING_BYTES or accepted_prompt_variant not in {"initial", "correction"} or not _valid_auth_actual_model(identity, actual_model):
            raise ValueError("invalid auth cache entry")
        with self.capacity_reservation(key, entry_prefix="auth-"):
            directory_ownership = self._open_cache_dir(create=True)
            if directory_ownership is None:
                return False
            directory = directory_ownership.descriptor
            temporary_name_ownership: _TemporaryNameOwnership | None = None
            try:
                destination = f"auth-{key}.json"
                if _entry_is_unsafe(directory, destination) or _entry_exists(directory, destination):
                    return False
                entry: dict[str, object] = {"cache_format": AUTH_CACHE_FORMAT, "cache_key": key, "identity": dict(identity), "contract": dict(contract), "raw_response": raw_response, "accepted_prompt_variant": accepted_prompt_variant, "actual_model": actual_model}
                entry["entry_hash"] = sha256_canonical_json(entry)
                entry["entry_hmac"] = hmac.new(self._authentication_key, _AUTH_CACHE_HMAC_DOMAIN + canonical_json(entry), hashlib.sha256).hexdigest()
                payload = canonical_json(entry)
                if len(payload) > _MAX_CACHE_BYTES:
                    raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "Auth cache entry exceeds its byte limit.")
                temporary_name, temporary_ownership = _create_private_temporary(directory, key)
                temporary_name_ownership = _TemporaryNameOwnership(temporary_name)
                try:
                    _write_all(temporary_ownership.descriptor, payload)
                    os.fsync(temporary_ownership.descriptor)
                finally:
                    _close_transient_descriptor(temporary_ownership)
                os.link(temporary_name, destination, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                _retire_temporary_name(directory, temporary_name_ownership)
                os.fsync(directory)
                return True
            except OSError as exc:
                raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "Could not publish Auth Contract cache entry.") from exc
            finally:
                try:
                    try:
                        _retire_temporary_name(directory, temporary_name_ownership)
                    except OSError:
                        pass
                finally:
                    _close_transient_descriptor(directory_ownership)

    def provider_request_id_digest(self, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("provider request ID must be a string")
        return hmac.new(self._authentication_key, b"provider-request-id-v1\0" + value.encode("utf-8"), hashlib.sha256).hexdigest()

    def _entry_hmac(self, entry: Mapping[str, object]) -> str:
        return hmac.new(self._authentication_key, b"growth-contract-cache-entry-v14\0" + canonical_json(entry), hashlib.sha256).hexdigest()

    def _open_cache_dir(self, *, create: bool) -> _TransientDescriptorOwnership | None:
        ownership: _TransientDescriptorOwnership | None = None
        try:
            with _FORK_OWNERSHIP_GUARD:
                active_directory = _active_cache_directory(self._cache_dir)
                descriptor = (
                    _create_private_hierarchy(self._cache_dir, create=create)
                    if active_directory is None
                    else os.dup(active_directory.descriptor)
                )
                if descriptor is None:
                    return None
                try:
                    ownership = _register_transient_descriptor(descriptor)
                except BaseException:
                    _close_unregistered_descriptor(descriptor)
                    raise
            info = os.fstat(ownership.descriptor)
            if (
                not _safe_metadata(info, stat.S_ISDIR, 0o700)
                or (
                    active_directory is not None
                    and (info.st_dev, info.st_ino)
                    != (active_directory.device, active_directory.inode)
                )
            ):
                return None
            result = ownership
            ownership = None
            return result
        except (OSError, AnalyzerError):
            return None
        finally:
            if ownership is not None:
                _close_transient_descriptor(ownership)


def _cache_directory_path_key(path: Path) -> str:
    if not path.is_absolute():
        raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache path is not absolute.")
    return str(path)


def _register_active_flock(descriptor: int) -> _ActiveFlockOwnership:
    ownership = _ActiveFlockOwnership(descriptor=descriptor, pid=os.getpid())
    if descriptor in _ACTIVE_FLOCK_FDS:
        raise AnalyzerError("LLM_CACHE_LOCK_FAILED", "LLM cache lock ownership is unsafe.")
    _ACTIVE_FLOCK_FDS[descriptor] = ownership
    return ownership


def _register_transient_descriptor(descriptor: int) -> _TransientDescriptorOwnership:
    ownership = _TransientDescriptorOwnership(descriptor=descriptor, pid=os.getpid())
    if descriptor in _ACTIVE_TRANSIENT_FDS:
        raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache descriptor ownership is unsafe.")
    _ACTIVE_TRANSIENT_FDS[descriptor] = ownership
    return ownership


def _retire_registered_descriptor(
    registry: dict[int, object],
    ownership: object,
) -> BaseException | None:
    descriptor = getattr(ownership, "descriptor", -1)
    owner_pid = getattr(
        ownership,
        "pid",
        getattr(ownership, "owner_pid", -1),
    )
    with _FORK_OWNERSHIP_GUARD:
        if (
            owner_pid != os.getpid()
            or descriptor < 0
            or registry.get(descriptor) is not ownership
        ):
            return None
        release_error: BaseException | None = None
        try:
            os.close(descriptor)
        except CloseRangePreActionError as exc:
            release_error = exc
            try:
                os.closerange(descriptor, descriptor + 1)
            except BaseException as fallback_exc:
                release_error = fallback_exc
        except BaseException as exc:
            # close(2) outcome is ambiguous after any non-pre-action escape.
            # Retire the token and never touch this fd number again.
            release_error = exc
        registry.pop(descriptor, None)
        return release_error


def _raise_async_release_error(error: BaseException | None) -> None:
    if error is not None and not isinstance(error, OSError):
        raise error


def _open_active_flock(
    directory: int,
    name: str,
) -> tuple[int, _ActiveFlockOwnership] | None:
    with _FORK_OWNERSHIP_GUARD:
        descriptor = _open_private_regular_file(directory, name, create=True)
        if descriptor is None:
            return None
        try:
            ownership = _register_active_flock(descriptor)
        except BaseException:
            _close_unregistered_descriptor(descriptor)
            raise
        return descriptor, ownership


def _active_flock_is_owned(ownership: _ActiveFlockOwnership | None) -> bool:
    return (
        ownership is not None
        and ownership.pid == os.getpid()
        and _ACTIVE_FLOCK_FDS.get(ownership.descriptor) is ownership
    )


def _close_active_flock(ownership: _ActiveFlockOwnership | None) -> None:
    if ownership is None:
        return
    _raise_async_release_error(
        _retire_registered_descriptor(_ACTIVE_FLOCK_FDS, ownership)
    )


def _close_transient_descriptor(
    ownership: _TransientDescriptorOwnership | None,
) -> None:
    if ownership is None:
        return
    _raise_async_release_error(
        _retire_registered_descriptor(_ACTIVE_TRANSIENT_FDS, ownership)
    )


def _close_unregistered_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except CloseRangePreActionError:
        try:
            os.closerange(descriptor, descriptor + 1)
        except BaseException:
            pass
    except BaseException:
        # Ambiguous/post-action: never retry this fd number.
        pass


def _open_transient_private_regular_file(
    directory: int,
    name: str,
    *,
    create: bool,
) -> _TransientDescriptorOwnership | None:
    with _FORK_OWNERSHIP_GUARD:
        descriptor = _open_private_regular_file(directory, name, create=create)
        if descriptor is None:
            return None
        try:
            return _register_transient_descriptor(descriptor)
        except BaseException:
            _close_unregistered_descriptor(descriptor)
            raise


def _active_cache_directory(path: Path) -> _ActiveCacheDirectory | None:
    directories = getattr(_ACTIVE_RESERVATIONS, "directories", None)
    if not directories:
        return None
    state = directories.get(_cache_directory_path_key(path))
    if state is None:
        return None
    if (
        state.owner_pid != os.getpid()
        or state.owner_thread_id != threading.get_ident()
        or state.descriptor < 0
        or _ACTIVE_CACHE_DIRECTORIES.get(state.descriptor) is not state
    ):
        raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache directory transaction is unsafe.")
    try:
        info = os.fstat(state.descriptor)
    except OSError:
        raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache directory transaction is unsafe.") from None
    if (
        not _safe_metadata(info, stat.S_ISDIR, 0o700)
        or (info.st_dev, info.st_ino) != (state.device, state.inode)
    ):
        raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache directory transaction is unsafe.")
    return state


def _begin_cache_directory_transaction(
    path: Path,
    *,
    create: bool,
) -> tuple[_ActiveCacheDirectory, bool] | None:
    active = _active_cache_directory(path)
    if active is not None:
        return active, False
    _FORK_OWNERSHIP_GUARD.acquire()
    descriptor: int | None = None
    state: _ActiveCacheDirectory | None = None
    registered = False
    directories: dict[str, _ActiveCacheDirectory] | None = None
    try:
        descriptor = _create_private_hierarchy(path, create=create)
        if descriptor is None:
            return None
        info = os.fstat(descriptor)
        if not _safe_metadata(info, stat.S_ISDIR, 0o700):
            return None
        state = _ActiveCacheDirectory(
            path_key=_cache_directory_path_key(path),
            descriptor=descriptor,
            device=info.st_dev,
            inode=info.st_ino,
            owner_pid=os.getpid(),
            owner_thread_id=threading.get_ident(),
            reservations=set(),
        )
        directories = getattr(_ACTIVE_RESERVATIONS, "directories", None)
        if directories is None:
            directories = {}
            _ACTIVE_RESERVATIONS.directories = directories
        if state.path_key in directories or descriptor in _ACTIVE_CACHE_DIRECTORIES:
            raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache directory transaction is unsafe.")
        _ACTIVE_CACHE_DIRECTORIES[descriptor] = state
        registered = True
        directories[state.path_key] = state
        descriptor = -1
        return state, True
    finally:
        try:
            if descriptor is not None and descriptor >= 0:
                if (
                    registered
                    and state is not None
                    and _ACTIVE_CACHE_DIRECTORIES.get(descriptor) is state
                ):
                    _ACTIVE_CACHE_DIRECTORIES.pop(descriptor, None)
                if (
                    directories is not None
                    and state is not None
                    and directories.get(state.path_key) is state
                ):
                    directories.pop(state.path_key, None)
                _close_unregistered_descriptor(descriptor)
        finally:
            _FORK_OWNERSHIP_GUARD.release()


def _end_cache_directory_transaction(
    state: _ActiveCacheDirectory,
    owns_transaction: bool,
) -> None:
    if not owns_transaction:
        return
    directories = getattr(_ACTIVE_RESERVATIONS, "directories", None)
    if directories is not None and directories.get(state.path_key) is state:
        directories.pop(state.path_key, None)
    try:
        _raise_async_release_error(
            _retire_registered_descriptor(_ACTIVE_CACHE_DIRECTORIES, state)
        )
    finally:
        state.descriptor = -1


def _create_private_hierarchy(path: Path, *, create: bool = True) -> int | None:
    """Open a verified private target, transferring its descriptor to the caller."""
    if not path.is_absolute():
        return None
    parts = path.parts
    descriptor: int | None = None
    foreign_sticky_requires_anchor = False
    foreign_readonly_requires_anchor = False

    def component_is_safe(info: os.stat_result, *, is_target: bool) -> bool:
        nonlocal foreign_sticky_requires_anchor, foreign_readonly_requires_anchor
        if not stat.S_ISDIR(info.st_mode):
            return False
        owner_is_trusted = info.st_uid in {0, os.getuid()}
        mode = stat.S_IMODE(info.st_mode)
        sticky_shared = bool(info.st_mode & stat.S_ISVTX) and bool(mode & 0o002)
        mode_is_trusted = mode & 0o022 == 0 or (owner_is_trusted and sticky_shared)
        private_anchor = info.st_uid == os.getuid() and mode == 0o700
        current_owned_safe_anchor = info.st_uid == os.getuid() and mode & 0o022 == 0
        foreign_sticky = sticky_shared and not owner_is_trusted
        foreign_readonly = not owner_is_trusted and mode & 0o022 == 0
        if foreign_sticky:
            foreign_sticky_requires_anchor = True
        elif foreign_sticky_requires_anchor and private_anchor:
            foreign_sticky_requires_anchor = False
        elif foreign_sticky_requires_anchor:
            return False
        if foreign_readonly:
            foreign_readonly_requires_anchor = True
        elif foreign_readonly_requires_anchor and current_owned_safe_anchor:
            foreign_readonly_requires_anchor = False
        return not (
            (not owner_is_trusted and not foreign_sticky and not foreign_readonly)
            or (not mode_is_trusted and not foreign_sticky)
            or (is_target and not _safe_metadata(info, stat.S_ISDIR, 0o700))
        )

    try:
        descriptor = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
        if not component_is_safe(os.fstat(descriptor), is_target=len(parts) == 1):
            return None
        for index, component in enumerate(parts[1:], start=1):
            child: int | None = None
            try:
                try:
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor)
                except FileNotFoundError:
                    # Foreign namespace prefixes are traversal-only.  Missing
                    # components are created only after an existing safe
                    # current-uid anchor has been opened and verified.
                    if (
                        not create
                        or foreign_sticky_requires_anchor
                        or foreign_readonly_requires_anchor
                    ):
                        return None
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor)
                if not component_is_safe(
                    os.fstat(child),
                    is_target=index == len(parts) - 1,
                ):
                    return None
                previous = descriptor
                descriptor = child
                child = None
                _close_unregistered_descriptor(previous)
            finally:
                if child is not None:
                    _close_unregistered_descriptor(child)
        result = descriptor
        descriptor = None
        return result
    except OSError:
        return None
    finally:
        if descriptor is not None:
            _close_unregistered_descriptor(descriptor)


def _require_cache_capacity(directory: int, destination: str, new_size: int) -> None:
    entries = 0
    total_bytes = 0
    try:
        names = os.listdir(directory)
    except OSError as exc:
        raise AnalyzerError("LLM_CACHE_CAPACITY_UNAVAILABLE", "Could not inspect LLM cache capacity.") from exc
    for name in names:
        if not isinstance(name, str):
            continue
        is_entry = (
            name.endswith(".json")
            and (
                (len(name) == 69 and _safe_key(name[:-5]))
                or (len(name) == 74 and name.startswith("auth-") and _safe_key(name[5:-5]))
            )
        )
        is_temporary = _TEMPORARY_NAME.fullmatch(name) is not None
        if not is_entry and not is_temporary:
            continue
        try:
            info = os.lstat(name, dir_fd=directory)
        except OSError as exc:
            raise AnalyzerError("LLM_CACHE_CAPACITY_UNAVAILABLE", "Could not inspect LLM cache capacity.") from exc
        if not _safe_metadata(info, stat.S_ISREG, 0o600):
            raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache contains an unsafe entry.")
        if is_entry:
            entries += 1
        total_bytes += info.st_size
        if entries > _MAX_CACHE_ENTRIES or total_bytes > _MAX_CACHE_TOTAL_BYTES:
            raise AnalyzerError("LLM_CACHE_CAPACITY_EXHAUSTED", "LLM cache capacity is exhausted.")
    replacing = destination in names
    if (not replacing and entries >= _MAX_CACHE_ENTRIES) or total_bytes + (0 if replacing else new_size) > _MAX_CACHE_TOTAL_BYTES:
        raise AnalyzerError("LLM_CACHE_CAPACITY_EXHAUSTED", "LLM cache capacity is exhausted.")


def _safe_metadata(info: os.stat_result, type_check: object, required_mode: int) -> bool:
    return type_check(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == required_mode


def _read_private_regular_file(directory: int, name: str) -> bytes | None:
    loaded = _read_private_regular_file_with_stat(directory, name)
    return None if loaded is None else loaded[0]


def _read_private_regular_file_with_stat(directory: int, name: str) -> tuple[bytes, os.stat_result] | None:
    ownership = _open_transient_private_regular_file(directory, name, create=False)
    if ownership is None:
        return None
    descriptor = ownership.descriptor
    try:
        info = os.fstat(descriptor)
        chunks = bytearray()
        while len(chunks) <= _MAX_CACHE_BYTES:
            chunk = os.read(descriptor, _MAX_CACHE_BYTES + 1 - len(chunks))
            if not chunk:
                break
            chunks.extend(chunk)
        if len(chunks) > _MAX_CACHE_BYTES:
            raise ValueError("oversized cache")
        return bytes(chunks), info
    finally:
        _close_transient_descriptor(ownership)


def _retire_temporary_name(
    directory: int,
    ownership: _TemporaryNameOwnership | None,
) -> None:
    """Attempt one destructive unlink without ever retrying an ambiguous name."""
    if ownership is None:
        return
    name = ownership.name
    ownership.name = None
    if name is not None:
        os.unlink(name, dir_fd=directory)


def _unlink_same_private_file(directory: int, name: str, expected: os.stat_result) -> None:
    """Remove only the exact authenticated owner-only file read through this dir_fd."""
    try:
        current = os.lstat(name, dir_fd=directory)
        if not _safe_metadata(current, stat.S_ISREG, 0o600) or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
            return
        os.unlink(name, dir_fd=directory)
        os.fsync(directory)
    except OSError:
        return


def _open_private_regular_file(directory: int, name: str, *, create: bool) -> int | None:
    flags = (os.O_RDWR if create else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
    if create:
        flags |= os.O_CREAT
    try:
        try:
            existing = os.lstat(name, dir_fd=directory)
        except FileNotFoundError:
            if not create:
                return None
        else:
            if not _safe_metadata(existing, stat.S_ISREG, 0o600):
                return None
        descriptor = os.open(name, flags, 0o600, dir_fd=directory)
        if not _safe_metadata(os.fstat(descriptor), stat.S_ISREG, 0o600):
            _close_unregistered_descriptor(descriptor)
            return None
        return descriptor
    except OSError:
        return None


def _entry_exists(directory: int, name: str) -> bool:
    try:
        os.lstat(name, dir_fd=directory)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise AnalyzerError("LLM_CACHE_CAPACITY_UNAVAILABLE", "Could not inspect LLM cache entry.") from exc


def _entry_is_unsafe(directory: int, name: str) -> bool:
    try:
        info = os.lstat(name, dir_fd=directory)
    except FileNotFoundError:
        return False
    return not _safe_metadata(info, stat.S_ISREG, 0o600)


def _create_private_temporary(
    directory: int,
    key: str,
) -> tuple[str, _TransientDescriptorOwnership]:
    for _ in range(16):
        name = f".{key}.{secrets.token_hex(16)}.tmp"
        with _FORK_OWNERSHIP_GUARD:
            descriptor = -1
            try:
                descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory)
                os.fchmod(descriptor, 0o600)
                return name, _register_transient_descriptor(descriptor)
            except FileExistsError:
                continue
            except BaseException:
                if descriptor >= 0:
                    _close_unregistered_descriptor(descriptor)
                raise
    raise OSError("could not create private cache temporary")


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("could not write cache entry")
        offset += written


def _safe_key(key: str) -> bool:
    return isinstance(key, str) and len(key) == 64 and all(character in "0123456789abcdef" for character in key)


def _valid_auth_actual_model(identity: Mapping[str, object], actual_model: object) -> bool:
    requested_model = identity.get("model", DEFAULT_MODEL)
    if not isinstance(actual_model, str):
        return False
    try:
        actual_model_bytes = len(actual_model.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    return (
        isinstance(requested_model, str)
        and requested_model in SUPPORTED_MODELS
        and 0 < actual_model_bytes <= 512
        and model_response_matches(requested_model, actual_model)
    )


def _strict_load(data: bytes) -> object:
    if len(data) > _MAX_CACHE_BYTES:
        raise ValueError("oversized cache")
    value = json.loads(data.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    _check_json_bounds(value)
    return value


def _check_json_bounds(value: object, depth: int = 0, nodes: list[int] | None = None) -> None:
    nodes = [] if nodes is None else nodes
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("cache JSON is too deeply nested")
    nodes.append(1)
    if len(nodes) > _MAX_JSON_NODES:
        raise ValueError("cache JSON has too many values")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _MAX_JSON_STRING_BYTES:
            raise ValueError("cache JSON string is too large")
    elif isinstance(value, dict):
        if len(value) > _MAX_JSON_COLLECTION:
            raise ValueError("cache JSON object is too large")
        for child in value.values():
            _check_json_bounds(child, depth + 1, nodes)
    elif isinstance(value, list):
        if len(value) > _MAX_JSON_COLLECTION:
            raise ValueError("cache JSON array is too large")
        for child in value:
            _check_json_bounds(child, depth + 1, nodes)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _valid_audit(audit: object, identity: Mapping[str, object]) -> bool:
    if not isinstance(audit, Mapping) or set(audit) != _AUDIT_KEYS:
        return False
    safe_string_fields = (
        "method",
        "url",
        "provider",
        "protocol",
        "requested_model",
        "actual_model",
        "slice_content_hash",
        "public_source_url",
        "source_commit_sha",
    )
    if not all(isinstance(audit[field], str) and len(audit[field].encode("utf-8")) <= 512 for field in safe_string_fields):
        return False
    digest = audit["provider_request_id_digest"]
    if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        return False
    if (
        audit["method"] != identity.get("request_method")
        or audit["url"] != identity.get("request_url")
        or audit["provider"] != identity.get("provider")
        or audit["protocol"] != identity.get("protocol")
        or audit["slice_content_hash"] != identity.get("slice_content_hash")
        or audit["requested_model"] != identity.get("model")
        or not isinstance(identity.get("model"), str)
        or not model_response_matches(str(identity.get("model")), audit["actual_model"])
        or audit["public_source_url"] != identity.get("public_source_url")
        or audit["source_commit_sha"] != identity.get("source_commit_sha")
    ):
        return False
    for field in ("allow_remote_llm", "verified_public", "verified_clean_checkout"):
        if not isinstance(audit[field], bool) or audit[field] != identity.get(field):
            return False
    return True


def _normalized_slice(slice_: BoundedSlice) -> dict[str, object]:
    # Deliberately excludes caller-controlled slice_id and all excerpt content.
    return {
        "entry_id": slice_.entry_id,
        "growth_id": slice_.growth_id,
        "typed_facts": {
            "static_facts": [item.to_dict() for item in slice_.payload.static_facts],
            "cfg_summary": slice_.payload.cfg_summary.to_dict(),
            "registration_facts": [item.to_dict() for item in slice_.payload.registration_facts],
            "config_facts": [item.to_dict() for item in slice_.payload.config_facts],
        },
        "excerpt_provenance": [{"excerpt_id": item.excerpt_id, "path": item.repo_relative_path, "start_line": item.start_line, "end_line": item.end_line, "git_blob_sha256": item.git_blob_sha256, "excerpt_sha256": item.excerpt_sha256, "content_byte_length": len(item.content.encode("utf-8"))} for item in slice_.source_excerpts],
    }
