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
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dosweb.artifacts.identifiers import canonical_json, sha256_canonical_json
from dosweb.errors import AnalyzerError
from dosweb.growth.contracts import validate_contract_static_evidence, validate_growth_contract
from dosweb.growth.models import BoundedSlice, GrowthContract
from dosweb.llm.schemas import PROMPT_VERSION, RESPONSE_SCHEMA_VERSION

_CACHE_FORMAT = "growth-contract-cache-v5"
_LOCK_STRIPES = 64
_LOCKS_GUARD = threading.Lock()
_LOCKS: tuple[threading.Lock, ...] = tuple(threading.Lock() for _ in range(_LOCK_STRIPES))
_CAPACITY_LOCK = threading.Lock()
_ACTIVE_RESERVATIONS = threading.local()
_ACTIVE_FLOCK_FDS: set[int] = set()
_LOCKS_PID = os.getpid()


def _reset_locks_after_fork() -> None:
    global _LOCKS_GUARD, _LOCKS, _CAPACITY_LOCK, _ACTIVE_RESERVATIONS, _ACTIVE_FLOCK_FDS, _LOCKS_PID
    for descriptor in tuple(_ACTIVE_FLOCK_FDS):
        try:
            os.close(descriptor)
        except OSError:
            pass
    _LOCKS_GUARD = threading.Lock()
    _LOCKS = tuple(threading.Lock() for _ in range(_LOCK_STRIPES))
    _CAPACITY_LOCK = threading.Lock()
    _ACTIVE_RESERVATIONS = threading.local()
    _ACTIVE_FLOCK_FDS = set()
    _LOCKS_PID = os.getpid()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_locks_after_fork)
_AUDIT_KEYS = frozenset({"method", "url", "requested_model", "actual_model", "provider_request_id_digest", "slice_content_hash", "allow_remote_llm", "public_source_url", "source_commit_sha", "verified_public", "verified_clean_checkout"})
_ENTRY_KEYS = frozenset({"cache_format", "cache_key", "response_schema_version", "identity", "identity_hash", "request_audit", "audit_hash", "contract", "contract_hash", "entry_hash", "entry_hmac"})
_UNSIGNED_ENTRY_KEYS = _ENTRY_KEYS - {"entry_hmac"}
_MAX_CACHE_BYTES = 524288
_MAX_CACHE_ENTRIES = 256
_MAX_CACHE_TOTAL_BYTES = _MAX_CACHE_ENTRIES * _MAX_CACHE_BYTES
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 8192
_MAX_JSON_COLLECTION = 256
_MAX_JSON_STRING_BYTES = 65536
_TEMPORARY_NAME = re.compile(r"^\.[0-9a-f]{64}\.[0-9a-f]{32}\.tmp$")


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
        "provider": "deepseek",
        "base_url": canonical_base_url(getattr(config, "base_url")),
        "model": getattr(config, "model"),
        "temperature": getattr(config, "temperature"),
        "timeout_seconds": getattr(config, "timeout_seconds"),
        "prompt_version": PROMPT_VERSION,
        "response_schema_version": RESPONSE_SCHEMA_VERSION,
        "attestation_schema_version": "public-source-attestation-v1",
        "public_source_url": getattr(config, "public_source_url"),
        "source_commit_sha": str(getattr(config, "source_commit_sha")).lower(),
        "slice_content_hash": sha256_canonical_json(normalized),
        "request_method": "POST",
        "request_url": f"{canonical_base_url(getattr(config, 'base_url'))}chat/completions",
        "allow_remote_llm": getattr(config, "allow_remote_llm"),
        "verified_public": False,
        "verified_clean_checkout": True,
    }
    return sha256_canonical_json(identity), identity


class ContractCache:
    """A cache that treats disk state as hostile until API-key authenticated."""

    def __init__(self, cache_dir: Path, authentication_key: str) -> None:
        if not isinstance(authentication_key, str):
            raise ValueError("cache authentication key must be a string")
        self._cache_dir = cache_dir
        self._authentication_key = authentication_key.encode("utf-8")

    def get(self, key: str, identity: Mapping[str, object], static_fact_ids: frozenset[str]) -> GrowthContract | None:
        contract = self.authenticated_contract(key, identity)
        if contract is None:
            return None
        try:
            return validate_contract_static_evidence(contract, static_fact_ids)
        except AnalyzerError:
            return None

    def authenticated_contract(self, key: str, identity: Mapping[str, object]) -> GrowthContract | None:
        """Return an authenticated typed entry without current-slice evidence checks."""
        if not _safe_key(key):
            return None
        directory = self._open_cache_dir(create=False)
        if directory is None:
            return None
        try:
            data = _read_private_regular_file(directory, f"{key}.json")
            if data is None:
                return None
            raw = _strict_load(data)
            if not isinstance(raw, dict) or set(raw) != _ENTRY_KEYS:
                return None
            if raw["cache_format"] != _CACHE_FORMAT or raw["cache_key"] != key or raw["response_schema_version"] != RESPONSE_SCHEMA_VERSION or raw["identity"] != identity:
                return None
            if raw["identity_hash"] != sha256_canonical_json(identity):
                return None
            audit = raw["request_audit"]
            if not _valid_audit(audit, identity) or raw["audit_hash"] != sha256_canonical_json(audit):
                return None
            contract_payload = raw["contract"]
            if raw["contract_hash"] != sha256_canonical_json(contract_payload):
                return None
            unsigned = {name: raw[name] for name in _UNSIGNED_ENTRY_KEYS}
            stable = {name: raw[name] for name in _UNSIGNED_ENTRY_KEYS if name != "entry_hash"}
            if raw["entry_hash"] != sha256_canonical_json(stable):
                return None
            if not isinstance(raw["entry_hmac"], str) or not hmac.compare_digest(raw["entry_hmac"], self._entry_hmac(unsigned)):
                return None
            return validate_growth_contract(contract_payload)
        except (OSError, RecursionError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError, AnalyzerError):
            return None
        finally:
            os.close(directory)

    def is_usable(self, key: str) -> bool:
        """Return whether the directory and fixed locks are safe to trust."""
        if not _safe_key(key):
            return False
        directory = self._open_cache_dir(create=False)
        if directory is None:
            return False
        stripe = int(key[:8], 16) % _LOCK_STRIPES
        try:
            return not _entry_is_unsafe(directory, f".stripe-{stripe:02d}.lock") and not _entry_is_unsafe(directory, ".capacity.lock")
        finally:
            os.close(directory)

    def require_capacity(self, key: str) -> None:
        with self.capacity_reservation(key):
            pass

    @contextmanager
    def capacity_reservation(self, key: str, *, allow_existing: bool = False) -> Iterator[None]:
        if not _safe_key(key):
            raise ValueError("invalid cache key")
        active = getattr(_ACTIVE_RESERVATIONS, "keys", set())
        marker = (str(self._cache_dir.absolute()), key)
        if marker in active:
            yield
            return
        with _CAPACITY_LOCK:
            directory = self._open_cache_dir(create=True)
            if directory is None:
                raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache directory is unsafe.")
            descriptor: int | None = None
            try:
                descriptor = _open_private_regular_file(directory, ".capacity.lock", create=True)
                if descriptor is None:
                    raise AnalyzerError("LLM_CACHE_LOCK_FAILED", "LLM cache capacity lock is unsafe.")
                _ACTIVE_FLOCK_FDS.add(descriptor)
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                destination = f"{key}.json"
                if _entry_is_unsafe(directory, destination):
                    raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache destination is unsafe.")
                exists = _entry_exists(directory, destination)
                if exists and not allow_existing:
                    raise AnalyzerError("LLM_CACHE_CONFLICT", "An existing LLM cache entry could not be reused safely.")
                capacity_destination = f".refresh-{key}" if exists else destination
                _require_cache_capacity(directory, capacity_destination, _MAX_CACHE_BYTES)
                next_active = set(active)
                next_active.add(marker)
                _ACTIVE_RESERVATIONS.keys = next_active
                try:
                    yield
                finally:
                    next_active.discard(marker)
                    _ACTIVE_RESERVATIONS.keys = next_active
            finally:
                if descriptor is not None:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    except OSError:
                        pass
                    _ACTIVE_FLOCK_FDS.discard(descriptor)
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                os.close(directory)

    @contextmanager
    def single_flight(self, key: str) -> Iterator[bool]:
        if not _safe_key(key):
            raise ValueError("invalid cache key")
        if getattr(_ACTIVE_RESERVATIONS, "keys", set()):
            raise AnalyzerError("LLM_CACHE_LOCK_FAILED", "LLM cache lock order is invalid.")
        global _LOCKS_PID
        if _LOCKS_PID != os.getpid():
            _reset_locks_after_fork()
        stripe = int(key[:8], 16) % _LOCK_STRIPES
        thread_lock = _LOCKS[stripe]
        with thread_lock:
            directory = self._open_cache_dir(create=True)
            if directory is None:
                raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache locking is unavailable.")
            lock_descriptor: int | None = None
            try:
                lock_descriptor = _open_private_regular_file(directory, f".stripe-{stripe:02d}.lock", create=True)
                if lock_descriptor is None:
                    raise AnalyzerError("LLM_CACHE_LOCK_FAILED", "LLM cache lock is unsafe.")
                _ACTIVE_FLOCK_FDS.add(lock_descriptor)
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
                try:
                    yield True
                finally:
                    fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            finally:
                if lock_descriptor is not None:
                    _ACTIVE_FLOCK_FDS.discard(lock_descriptor)
                    try:
                        os.close(lock_descriptor)
                    except OSError:
                        pass
                os.close(directory)

    def put(self, key: str, identity: Mapping[str, object], contract: GrowthContract, request_audit: Mapping[str, object]) -> bool:
        if not _safe_key(key) or not _valid_audit(request_audit, identity):
            raise ValueError("invalid cache entry")
        marker = (str(self._cache_dir.absolute()), key)
        if marker not in getattr(_ACTIVE_RESERVATIONS, "keys", set()):
            with self.capacity_reservation(key):
                return self.put(key, identity, contract, request_audit)
        directory = self._open_cache_dir(create=True)
        if directory is None:
            return False
        temporary_name: str | None = None
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
                "contract": contract_payload,
                "contract_hash": sha256_canonical_json(contract_payload),
            }
            entry["entry_hash"] = sha256_canonical_json(entry)
            entry["entry_hmac"] = self._entry_hmac(entry)
            serialized_entry = canonical_json(entry)
            if len(serialized_entry) > _MAX_CACHE_BYTES:
                raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "LLM cache entry exceeds its byte limit.")
            _require_cache_capacity(directory, destination, len(serialized_entry))
            temporary_name, temporary = _create_private_temporary(directory, key)
            try:
                temporary.write(serialized_entry)
                temporary.flush()
                os.fsync(temporary.fileno())
            finally:
                temporary.close()
            if _entry_is_unsafe(directory, destination):
                raise AnalyzerError("LLM_CACHE_UNSAFE", "LLM cache destination became unsafe.")
            if _entry_exists(directory, destination):
                raise AnalyzerError("LLM_CACHE_CONFLICT", "LLM cache entries are immutable once published.")
            os.link(temporary_name, destination, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.unlink(temporary_name, dir_fd=directory)
            temporary_name = None
            os.fsync(directory)
        except AnalyzerError:
            raise
        except OSError as exc:
            raise AnalyzerError("LLM_CACHE_WRITE_FAILED", "Could not publish LLM cache entry.") from exc
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=directory)
                except OSError:
                    pass
            os.close(directory)
        return True

    def provider_request_id_digest(self, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("provider request ID must be a string")
        return hmac.new(self._authentication_key, b"provider-request-id-v1\0" + value.encode("utf-8"), hashlib.sha256).hexdigest()

    def _entry_hmac(self, entry: Mapping[str, object]) -> str:
        return hmac.new(self._authentication_key, b"growth-contract-cache-entry-v5\0" + canonical_json(entry), hashlib.sha256).hexdigest()

    def _open_cache_dir(self, *, create: bool) -> int | None:
        try:
            if create and not _create_private_hierarchy(self._cache_dir):
                return None
            info = os.lstat(self._cache_dir)
            if not _safe_metadata(info, stat.S_ISDIR, 0o700):
                return None
            descriptor = os.open(self._cache_dir, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
            if not _safe_metadata(os.fstat(descriptor), stat.S_ISDIR, 0o700):
                os.close(descriptor)
                return None
            return descriptor
        except OSError:
            return None


def _create_private_hierarchy(path: Path) -> bool:
    """Create a Linux/Python 3.11+ private hierarchy via descriptor-relative traversal."""
    absolute = path.absolute()
    parts = absolute.parts
    descriptor = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    try:
        for index, component in enumerate(parts[1:], start=1):
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor)
            info = os.fstat(child)
            is_target_component = index == len(parts) - 1
            owner_is_trusted = info.st_uid in {0, os.getuid()}
            mode = stat.S_IMODE(info.st_mode)
            mode_is_trusted = mode & 0o022 == 0 or (info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX))
            if not stat.S_ISDIR(info.st_mode) or not owner_is_trusted or not mode_is_trusted or (is_target_component and not _safe_metadata(info, stat.S_ISDIR, 0o700)):
                os.close(child)
                return False
            os.close(descriptor)
            descriptor = child
        return True
    except OSError:
        return False
    finally:
        os.close(descriptor)


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
        is_entry = name.endswith(".json") and len(name) == 69
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
    descriptor = _open_private_regular_file(directory, name, create=False)
    if descriptor is None:
        return None
    try:
        chunks = bytearray()
        while len(chunks) <= _MAX_CACHE_BYTES:
            chunk = os.read(descriptor, _MAX_CACHE_BYTES + 1 - len(chunks))
            if not chunk:
                break
            chunks.extend(chunk)
        if len(chunks) > _MAX_CACHE_BYTES:
            raise ValueError("oversized cache")
        return bytes(chunks)
    finally:
        os.close(descriptor)


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
            os.close(descriptor)
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


def _create_private_temporary(directory: int, key: str) -> tuple[str, object]:
    for _ in range(16):
        name = f".{key}.{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory)
            os.fchmod(descriptor, 0o600)
            return name, os.fdopen(descriptor, "wb")
        except FileExistsError:
            continue
    raise OSError("could not create private cache temporary")


def _safe_key(key: str) -> bool:
    return isinstance(key, str) and len(key) == 64 and all(character in "0123456789abcdef" for character in key)


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
    safe_string_fields = ("method", "url", "requested_model", "actual_model", "slice_content_hash", "public_source_url", "source_commit_sha")
    if not all(isinstance(audit[field], str) and len(audit[field].encode("utf-8")) <= 512 for field in safe_string_fields):
        return False
    digest = audit["provider_request_id_digest"]
    if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        return False
    if (
        audit["method"] != identity.get("request_method")
        or audit["url"] != identity.get("request_url")
        or audit["slice_content_hash"] != identity.get("slice_content_hash")
        or audit["requested_model"] != identity.get("model")
        or audit["actual_model"] != identity.get("model")
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
