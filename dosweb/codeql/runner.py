from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import dosweb.filesystem as filesystem
from dosweb.artifacts.identifiers import file_sha256
from dosweb.codeql.database import (
    DatabaseInfo,
    validate_canonical_database,
    validate_database,
    validate_execution_database,
)
from dosweb.codeql.decoder import DecodeSource, decode_bqrs_json
from dosweb.errors import AnalyzerError
from dosweb.filesystem import (
    CloseRangeCapability,
    OwnedTemporaryFile,
    create_owned_tempfile as _create_owned_tempfile,
    duplicate_owned_descriptor as _duplicate_owned_descriptor,
    open_owned_descriptor as _open_owned_descriptor,
    renameat2_exchange,
    renameat2_no_replace,
    release_owned_descriptor_once,
    require_close_fd_once,
    run_with_deferred_interrupts,
)

_MAX_DIAGNOSTIC_BYTES: Final = 2048
_MAX_PROCESS_OUTPUT_BYTES: Final = 1024 * 1024
_MAX_QUERY_BYTES: Final = 16 * 1024 * 1024
_MAX_BQRS_BYTES: Final = 256 * 1024 * 1024
_MAX_DECODED_BYTES: Final = 64 * 1024 * 1024
_ALLOWED_ENVIRONMENT: Final = frozenset(
    {"PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "JAVA_HOME", "CODEQL_HOME"}
)
_SAFE_QUERY_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_QUERY_FAMILY_PATTERNS: Final = (
    (re.compile(r"^resourcelifecyclecallables$", re.IGNORECASE), "resource_lifecycle_callables"),
    (re.compile(r"^resourcelifecycletaskrelations$", re.IGNORECASE), "resource_lifecycle_task_relations"),
    (re.compile(r"^resourcelifecyclefacts$", re.IGNORECASE), "resource_lifecycle"),
    (re.compile(r"entrytogrowth|flow", re.IGNORECASE), "flow"),
    (re.compile(r"entryinterpositions?", re.IGNORECASE), "entry_interposition"),
    (re.compile(r"entrysecurity", re.IGNORECASE), "entry_security"),
    (re.compile(r"entries?$", re.IGNORECASE), "entries"),
    (re.compile(r"growth|materialization|allocation", re.IGNORECASE), "growth"),
    (re.compile(r"lifecyclesummary", re.IGNORECASE), "lifecycle_summary"),
    (re.compile(r"lifecyclecoverage", re.IGNORECASE), "lifecycle_coverage"),
    (re.compile(r"guard", re.IGNORECASE), "guard"),
    (re.compile(r"bound", re.IGNORECASE), "bound"),
    (re.compile(r"release", re.IGNORECASE), "release"),
)


@dataclass
class _QueryOutputBinding:
    """In-memory-only ownership for one published decoded result."""

    close_capability: CloseRangeCapability
    generations_descriptor: int
    generations_info: os.stat_result
    generation_name: str
    generation_descriptor: int
    generation_info: os.stat_result
    decoded_name: str
    decoded_descriptor: int
    decoded_info: os.stat_result
    decoded_size: int
    decoded_sha256: str
    decoded_bytes: bytes = field(repr=False)
    decoded_parent: str = "generation"
    attached: bool = False


@dataclass(frozen=True)
class _DecodedOutputSnapshot:
    descriptor: int
    info: os.stat_result
    size: int
    sha256: str
    payload: bytes = field(repr=False)


class _QueryResultPrivate:
    __slots__ = ("_output_binding",)


@dataclass(frozen=True, init=False, slots=True)
class QueryResult(_QueryResultPrivate):
    query_name: str
    query_path: Path
    bqrs_path: Path
    decoded_path: Path
    query_sha256: str
    bqrs_sha256: str

    def __init__(
        self,
        query_name: str,
        query_path: Path,
        bqrs_path: Path,
        decoded_path: Path,
        query_sha256: str,
        bqrs_sha256: str,
        *,
        _output_binding: _QueryOutputBinding | None = None,
    ) -> None:
        object.__setattr__(self, "query_name", query_name)
        object.__setattr__(self, "query_path", query_path)
        object.__setattr__(self, "bqrs_path", bqrs_path)
        object.__setattr__(self, "decoded_path", decoded_path)
        object.__setattr__(self, "query_sha256", query_sha256)
        object.__setattr__(self, "bqrs_sha256", bqrs_sha256)
        object.__setattr__(self, "_output_binding", _output_binding)

    def __del__(self) -> None:
        try:
            binding = getattr(self, "_output_binding", None)
            if binding is not None and not binding.attached:
                _release_owned_query_output_binding(binding)
        except BaseException:
            pass

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        return (
            type(self),
            (
                self.query_name,
                self.query_path,
                self.bqrs_path,
                self.decoded_path,
                self.query_sha256,
                self.bqrs_sha256,
            ),
        )


@dataclass
class _RollbackExchangeState:
    published_name: str
    published_info: os.stat_result
    slot_name: str
    slot_info: os.stat_result
    exchange_committed: bool = False
    placeholder_removed: bool = False


@dataclass
class _PublicationReplaceState:
    pending_name: str
    published_name: str
    expected_info: os.stat_result
    attempted: bool = False
    rollback_required: bool = False
    rollback_started: bool = False
    slot_retired: bool = False
    slot_tombstone_name: str | None = None
    resolved: bool = False


@dataclass
class _ExchangeProbeState:
    slot_name: str
    slot_info: os.stat_result
    probe_name: str
    probe_info: os.stat_result
    exchange_attempted: bool = False
    exchange_committed: bool = False
    restore_attempted: bool = False
    restore_committed: bool = False


def _query_family(stem: str) -> str:
    for pattern, family in _QUERY_FAMILY_PATTERNS:
        if pattern.search(stem):
            return family
    raise AnalyzerError(
        "CODEQL_QUERY_FAILED",
        "CodeQL query execution failed.",
        {"stage": "validation", "diagnostic": "query family is unknown"},
    )


def _safe_diagnostic(value: object, secrets: tuple[str, ...]) -> str:
    if isinstance(value, bytes):
        text = value[-_MAX_DIAGNOSTIC_BYTES:].decode("utf-8", errors="replace")
    elif isinstance(value, str):
        text = value[-_MAX_DIAGNOSTIC_BYTES:]
    else:
        text = ""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[-_MAX_DIAGNOSTIC_BYTES:]


def _decode_contract_diagnostic(reason: object, details: Mapping[str, object]) -> str:
    """Serialize only safe decoder contract fields; never paths or source content."""
    fields: dict[str, object] = {}
    if isinstance(reason, str) and reason:
        fields["reason"] = reason[:128]
    for key in ("query_name", "column"):
        value = details.get(key)
        if isinstance(value, str) and value:
            fields[key] = value[:256]
    for key in ("row", "row_count", "row_limit"):
        value = details.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            fields[key] = value
    if not fields:
        fields["reason"] = "decoded result violates its query contract"
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def _query_failed(
    stage: str,
    *,
    returncode: int | None = None,
    diagnostic: object = "",
    secrets: tuple[str, ...] = (),
) -> AnalyzerError:
    details: dict[str, object] = {"stage": stage, "diagnostic": _safe_diagnostic(diagnostic, secrets)}
    if returncode is not None:
        details["returncode"] = returncode
    return AnalyzerError("CODEQL_QUERY_FAILED", "CodeQL query execution failed.", details)


def _minimal_environment(environment: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in environment.items() if key in _ALLOWED_ENVIRONMENT and isinstance(value, str)}


def _same_owned_node(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_uid,
        stat.S_IFMT(left.st_mode),
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_uid,
        stat.S_IFMT(right.st_mode),
    )


def _harden_owned_path(
    path: Path,
    *,
    kind: str,
    mode: int,
    size_limit: int | None = None,
    create_directory: bool = False,
    parent_descriptor: int | None = None,
    expected_parent: os.stat_result | None = None,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    """Pin one owned leaf before changing its mode and rebind every name."""

    if kind not in {"directory", "regular"}:
        raise ValueError("owned path kind is invalid")
    if close_capability is None:
        close_capability = require_close_fd_once()
    lexical_path = Path(os.path.abspath(os.fspath(path)))
    parent = lexical_path.parent
    descriptor_owner: list[int] = []
    owns_parent = parent_descriptor is None
    try:
        if parent_descriptor is None:
            parent_discovered = parent.lstat()
            if (
                not stat.S_ISDIR(parent_discovered.st_mode)
                or parent_discovered.st_uid != os.getuid()
                or parent_discovered.st_nlink < 1
            ):
                raise OSError("owned path parent is unsafe")
            parent_descriptor = _open_owned_descriptor(
                descriptor_owner,
                parent,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            parent_opened = os.fstat(parent_descriptor)
            if (
                not _same_owned_node(parent_opened, parent_discovered)
                or stat.S_IMODE(parent_opened.st_mode)
                != stat.S_IMODE(parent_discovered.st_mode)
            ):
                raise OSError("owned path parent changed before pinning")
        else:
            parent_opened = os.fstat(parent_descriptor)
            if expected_parent is not None and (
                not _same_owned_node(parent_opened, expected_parent)
                or stat.S_IMODE(parent_opened.st_mode)
                != stat.S_IMODE(expected_parent.st_mode)
            ):
                raise OSError("owned path parent changed before pinning")
            if (
                not stat.S_ISDIR(parent_opened.st_mode)
                or parent_opened.st_uid != os.getuid()
                or parent_opened.st_nlink < 1
            ):
                raise OSError("owned path parent is unsafe")

        if create_directory:
            try:
                os.mkdir(
                    lexical_path.name,
                    mode=mode,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                pass
        discovered = os.stat(
            lexical_path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        if kind == "directory":
            flags |= getattr(os, "O_DIRECTORY", 0)
        else:
            flags |= getattr(os, "O_NONBLOCK", 0)
        leaf_descriptor = _open_owned_descriptor(
            descriptor_owner,
            lexical_path.name,
            flags,
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(leaf_descriptor)
        kind_valid = (
            stat.S_ISDIR(opened.st_mode)
            if kind == "directory"
            else stat.S_ISREG(opened.st_mode)
        )
        link_valid = (
            opened.st_nlink >= 1
            if kind == "directory"
            else opened.st_nlink == 1
        )
        size_valid = (
            size_limit is None
            or (kind == "regular" and opened.st_size <= size_limit)
        )
        if (
            not kind_valid
            or not link_valid
            or not size_valid
            or opened.st_uid != os.getuid()
            or not _same_owned_node(opened, discovered)
        ):
            raise OSError("owned path binding is unsafe")

        os.fchmod(leaf_descriptor, mode)
        rebound = os.fstat(leaf_descriptor)
        rebound_name = os.stat(
            lexical_path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        lexical_rebound = lexical_path.lstat()
        parent_rebound = os.fstat(parent_descriptor)
        if (
            not _same_owned_node(rebound, opened)
            or not _same_owned_node(rebound_name, opened)
            or not _same_owned_node(lexical_rebound, opened)
            or not _same_owned_node(parent_rebound, parent_opened)
            or stat.S_IMODE(rebound.st_mode) != mode
            or stat.S_IMODE(rebound_name.st_mode) != mode
            or stat.S_IMODE(lexical_rebound.st_mode) != mode
            or (kind == "regular" and rebound.st_nlink != 1)
            or (kind == "directory" and rebound.st_nlink < 1)
            or (
                size_limit is not None
                and (
                    rebound.st_size > size_limit
                    or rebound.st_size != opened.st_size
                )
            )
        ):
            raise OSError("owned path binding changed while hardening")
        if owns_parent:
            parent_lexical_rebound = parent.lstat()
            if (
                not _same_owned_node(parent_lexical_rebound, parent_opened)
                or stat.S_IMODE(parent_lexical_rebound.st_mode)
                != stat.S_IMODE(parent_opened.st_mode)
            ):
                raise OSError("owned path parent changed while hardening")
    finally:
        try:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "owned path descriptor release failed",
            )
        finally:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "owned path descriptor release failed",
            )


def _require_regular_output(
    path: Path,
    limit: int,
    stage: str,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    try:
        _harden_owned_path(
            path,
            kind="regular",
            mode=0o600,
            size_limit=limit,
            close_capability=close_capability,
        )
    except FileNotFoundError as exc:
        raise _query_failed(stage, diagnostic="expected output was not created") from exc
    except OSError as exc:
        raise _query_failed(
            stage,
            diagnostic="expected output is not a bounded regular file",
        ) from exc


def _fsync_file(
    path: Path,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    if close_capability is None:
        close_capability = require_close_fd_once()
    descriptor_owner: list[int] = []
    try:
        descriptor = _open_owned_descriptor(
            descriptor_owner,
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("not a regular file")
        os.fsync(descriptor)
    finally:
        try:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "file fsync descriptor release failed",
            )
        finally:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "file fsync descriptor release failed",
            )


def _fsync_directory(
    path: Path | int,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    if isinstance(path, int):
        os.fsync(path)
        return
    if close_capability is None:
        close_capability = require_close_fd_once()
    descriptor_owner: list[int] = []
    try:
        descriptor = _open_owned_descriptor(
            descriptor_owner,
            path,
            os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        os.fsync(descriptor)
    finally:
        try:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "directory fsync descriptor release failed",
            )
        finally:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "directory fsync descriptor release failed",
            )


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        pass


def _bounded_process(
    argv: list[str],
    environment: Mapping[str, str],
    timeout: float,
    pass_fds: tuple[int, ...] = (),
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        argv,
        env=dict(environment),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        pass_fds=pass_fds,
    )
    streams = (process.stdout, process.stderr)
    output = [bytearray(), bytearray()]
    total = 0
    lock = threading.Lock()
    overflow = threading.Event()

    def read_stream(index: int) -> None:
        nonlocal total
        stream = streams[index]
        assert stream is not None
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                with lock:
                    total += len(chunk)
                    if total > _MAX_PROCESS_OUTPUT_BYTES:
                        overflow.set()
                    output[index].extend(chunk)
                    if len(output[index]) > _MAX_DIAGNOSTIC_BYTES:
                        del output[index][:-_MAX_DIAGNOSTIC_BYTES]
                if overflow.is_set():
                    break
        except (OSError, ValueError):
            return

    readers = [threading.Thread(target=read_stream, args=(index,), daemon=True) for index in range(2)]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    failure: BaseException | None = None
    try:
        while True:
            if overflow.is_set():
                failure = OSError("process output exceeded limit")
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = subprocess.TimeoutExpired(argv, timeout)
                break
            if process.poll() is None:
                try:
                    process.wait(timeout=min(remaining, 0.05))
                except subprocess.TimeoutExpired:
                    continue
            else:
                for reader in readers:
                    reader.join(timeout=min(remaining, 0.05))
                if not any(reader.is_alive() for reader in readers):
                    break
        if failure is not None:
            _terminate_group(process)
    finally:
        for reader in readers:
            reader.join(timeout=0.5)
        for stream in streams:
            if stream is not None:
                stream.close()
        for reader in readers:
            reader.join(timeout=0.1)
    if failure is not None:
        raise failure
    if overflow.is_set():
        raise OSError("process output exceeded limit")
    return subprocess.CompletedProcess(
        argv,
        process.returncode,
        output[0].decode("utf-8", errors="replace"),
        output[1].decode("utf-8", errors="replace"),
    )


def _invoke(
    argv: list[str],
    *,
    stage: str,
    timeout_seconds: float,
    environment: Mapping[str, str],
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]],
    secrets: tuple[str, ...],
    pass_fds: tuple[int, ...] = (),
) -> None:
    if timeout_seconds <= 0:
        raise _query_failed(stage, diagnostic="command deadline exceeded")
    try:
        if subprocess_run is subprocess.run:
            result = _bounded_process(
                argv,
                environment,
                timeout_seconds,
                pass_fds,
            )
        else:
            result = subprocess_run(
                argv,
                env=dict(environment),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                pass_fds=pass_fds,
            )
    except subprocess.TimeoutExpired as exc:
        raise _query_failed(stage, diagnostic="command deadline exceeded", secrets=secrets) from exc
    except (OSError, ValueError) as exc:
        raise _query_failed(stage, diagnostic="command could not be completed", secrets=secrets) from exc
    if not isinstance(result, subprocess.CompletedProcess):
        raise _query_failed(stage, diagnostic="subprocess runner returned an invalid result")
    if result.returncode != 0:
        diagnostic = result.stderr if isinstance(result.stderr, str) else result.stdout
        raise _query_failed(stage, returncode=result.returncode, diagnostic=diagnostic, secrets=secrets)


def _require_deadline(deadline: float, monotonic: Callable[[], float], stage: str) -> None:
    if deadline - monotonic() <= 0:
        raise _query_failed(stage, diagnostic="query deadline exceeded")


def _pin_decoded_output(
    parent_descriptor: int,
    decoded_name: str,
    capability: CloseRangeCapability,
    owner_holder: list[_DecodedOutputSnapshot],
) -> _DecodedOutputSnapshot:
    local_owner: list[int] = []
    snapshot: _DecodedOutputSnapshot | None = None
    transferred = False
    append_failure: BaseException | None = None
    try:
        descriptor = _open_owned_descriptor(
            local_owner,
            decoded_name,
            os.O_RDONLY
            | os.O_NONBLOCK
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        info = os.fstat(descriptor)
        named = os.stat(
            decoded_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(info.st_mode)
            or not _same_inode(info, named)
            or info.st_uid != os.getuid()
            or info.st_size > _MAX_DECODED_BYTES
        ):
            raise OSError("decoded output binding changed")
        os.fchmod(descriptor, 0o600)
        rebound = os.fstat(descriptor)
        rebound_name = os.stat(
            decoded_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(rebound.st_mode)
            or not _same_inode(rebound, info)
            or not _same_inode(rebound_name, info)
            or rebound.st_uid != os.getuid()
            or stat.S_IMODE(rebound.st_mode) != 0o600
            or rebound.st_size > _MAX_DECODED_BYTES
        ):
            raise OSError("decoded output binding changed")
        snapshot = _DecodedOutputSnapshot(
            descriptor=descriptor,
            info=rebound,
            size=0,
            sha256=hashlib.sha256(b"").hexdigest(),
            payload=b"",
        )

        def transfer() -> None:
            nonlocal append_failure, transferred
            try:
                owner_holder.append(snapshot)
            except BaseException as exc:
                append_failure = exc
            finally:
                transferred = any(
                    item is snapshot
                    for item in list.__iter__(owner_holder)
                )
                if transferred:
                    local_owner[0] = -1

        run_with_deferred_interrupts(transfer)
        if append_failure is not None:
            raise append_failure
        return snapshot
    except BaseException as exc:
        if snapshot is not None:
            transferred = transferred or any(
                item is snapshot
                for item in list.__iter__(owner_holder)
            )
        if transferred:
            raise
        released = True

        def release_local_owner() -> None:
            nonlocal released
            while local_owner:
                descriptor = local_owner.pop()
                if descriptor >= 0 and not _release_query_output_descriptor(
                    descriptor,
                    capability,
                ):
                    released = False

        try:
            run_with_deferred_interrupts(release_local_owner)
        except BaseException:
            released = False
        if not released:
            raise _query_failed(
                "bqrs_decode",
                diagnostic="decoded output descriptor release failed",
            ) from exc
        if isinstance(exc, AnalyzerError):
            raise
        raise _query_failed(
            "bqrs_decode",
            diagnostic="decoded output binding failed",
        ) from exc


def _read_decoded_json(
    path: Path,
    query_name: str,
    database: DatabaseInfo,
    query_sha256: str,
    deadline: float,
    monotonic: Callable[[], float],
    descriptor_owner: list[_DecodedOutputSnapshot],
) -> None:
    if not descriptor_owner:
        raise _query_failed(
            "bqrs_decode",
            diagnostic="decoded output binding is unavailable",
        )
    snapshot = descriptor_owner[0]
    descriptor = snapshot.descriptor
    try:
        named_before = path.stat(follow_symlinks=False)
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or not _same_inode(opened_before, snapshot.info)
            or not _same_inode(named_before, snapshot.info)
            or opened_before.st_uid != os.getuid()
            or stat.S_IMODE(opened_before.st_mode) != 0o600
            or opened_before.st_size > _MAX_DECODED_BYTES
        ):
            raise ValueError("decoded output binding changed")
        raw = bytearray()
        offset = 0
        while len(raw) <= _MAX_DECODED_BYTES:
            _require_deadline(deadline, monotonic, "bqrs_decode")
            chunk = os.pread(
                descriptor,
                min(
                    1024 * 1024,
                    _MAX_DECODED_BYTES + 1 - len(raw),
                ),
                offset,
            )
            if not chunk:
                break
            raw.extend(chunk)
            offset += len(chunk)
        if len(raw) > _MAX_DECODED_BYTES:
            raise ValueError("decoded output exceeds limit")
        raw_bytes = bytes(raw)
        payload = json.loads(raw_bytes.decode("utf-8"))
        decode_bqrs_json(
            query_name,
            payload,
            DecodeSource(source_root=database.source_root, query_sha256=query_sha256),
        )
        opened_after = os.fstat(descriptor)
        named_after = path.stat(follow_symlinks=False)
        if (
            not _same_inode(opened_after, snapshot.info)
            or not _same_inode(named_after, snapshot.info)
            or opened_after.st_uid != os.getuid()
            or stat.S_IMODE(opened_after.st_mode) != 0o600
            or opened_after.st_size != len(raw_bytes)
            or opened_after.st_size != opened_before.st_size
            or opened_after.st_mtime_ns != opened_before.st_mtime_ns
            or opened_after.st_ctime_ns != opened_before.st_ctime_ns
        ):
            raise ValueError("decoded output changed during validation")
        validated = _DecodedOutputSnapshot(
            descriptor=descriptor,
            info=opened_after,
            size=len(raw_bytes),
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            payload=raw_bytes,
        )
        for index, owned in enumerate(list.__iter__(descriptor_owner)):
            if owned is snapshot:
                descriptor_owner[index] = validated
                break
        else:
            raise ValueError("decoded output owner changed")
    except AnalyzerError as exc:
        details = exc.details if isinstance(exc.details, Mapping) else {}
        diagnostic = _decode_contract_diagnostic(details.get("reason"), details)
        raise _query_failed("bqrs_decode", diagnostic=diagnostic) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, MemoryError, RecursionError) as exc:
        raise _query_failed("bqrs_decode", diagnostic="decoded result violates its query contract") from exc


def _require_decoded_snapshot_current(
    parent_descriptor: int,
    decoded_name: str,
    snapshot: _DecodedOutputSnapshot,
    *,
    stage: str,
) -> None:
    try:
        opened = os.fstat(snapshot.descriptor)
        named = os.stat(
            decoded_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or not _same_inode(opened, snapshot.info)
            or not _same_inode(named, snapshot.info)
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_size != snapshot.size
        ):
            raise OSError("decoded output binding changed")
        raw = bytearray()
        offset = 0
        while len(raw) <= _MAX_DECODED_BYTES:
            chunk = os.pread(
                snapshot.descriptor,
                min(
                    1024 * 1024,
                    _MAX_DECODED_BYTES + 1 - len(raw),
                ),
                offset,
            )
            if not chunk:
                break
            raw.extend(chunk)
            offset += len(chunk)
        if (
            len(raw) != snapshot.size
            or hashlib.sha256(raw).hexdigest() != snapshot.sha256
            or bytes(raw) != snapshot.payload
        ):
            raise OSError("decoded output content changed")
        rebound = os.fstat(snapshot.descriptor)
        rebound_name = os.stat(
            decoded_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not _same_inode(rebound, snapshot.info)
            or not _same_inode(rebound_name, snapshot.info)
            or rebound.st_size != snapshot.size
        ):
            raise OSError("decoded output changed during verification")
    except OSError as exc:
        raise _query_failed(
            stage,
            diagnostic="decoded output binding changed",
        ) from exc


def _deadline_file_sha256(
    path: Path,
    deadline: float,
    monotonic: Callable[[], float],
    stage: str,
    close_capability: CloseRangeCapability | None = None,
) -> str:
    if close_capability is None:
        close_capability = require_close_fd_once()
    digest = hashlib.sha256()
    descriptor_owner: list[int] = []
    try:
        descriptor = _open_owned_descriptor(
            descriptor_owner,
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        while True:
            _require_deadline(deadline, monotonic, stage)
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)
    finally:
        try:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "file hash descriptor release failed",
            )
        finally:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "file hash descriptor release failed",
            )


def _validate_publication_databases(
    database: DatabaseInfo,
    deadline: float,
    monotonic: Callable[[], float],
) -> None:
    """Rebind canonical/private DB state at one path-free publication checkpoint."""

    try:
        actual = validate_database(
            database.path,
            deadline=deadline,
            monotonic=monotonic,
        )
        if (
            actual.fingerprint != database.fingerprint
            or actual.source_root != database.source_root
        ):
            raise ValueError("canonical database identity changed")
        validate_canonical_database(
            database,
            actual_database=actual,
            deadline=deadline,
            monotonic=monotonic,
        )
        if database.execution is not None:
            validate_execution_database(
                database,
                deadline=deadline,
                monotonic=monotonic,
            )
    except TimeoutError as exc:
        raise _query_failed(
            "publication", diagnostic="query deadline exceeded"
        ) from exc
    except (AnalyzerError, OSError, ValueError, TypeError, MemoryError) as exc:
        raise _query_failed(
            "publication",
            diagnostic="database changed during output publication",
        ) from exc


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _pin_generation_directory(
    generations: Path,
    close_capability: CloseRangeCapability | None = None,
) -> tuple[int, os.stat_result]:
    if close_capability is None:
        close_capability = require_close_fd_once()
    before = generations.lstat()
    if (
        not stat.S_ISDIR(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o700
    ):
        raise OSError("generation directory is unsafe")
    descriptor_owner: list[int] = []
    try:
        descriptor = _open_owned_descriptor(
            descriptor_owner,
            generations,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if not _same_inode(opened, before):
            raise OSError("generation directory changed while pinning")
        return descriptor, opened
    except BaseException:
        try:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "generation directory descriptor release failed",
            )
        finally:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "generation directory descriptor release failed",
            )
        raise


def _require_generation_directory_binding(
    generations: Path,
    descriptor: int,
    expected: os.stat_result,
) -> None:
    opened = os.fstat(descriptor)
    current = generations.lstat()
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not _same_inode(opened, expected)
        or not _same_inode(current, expected)
        or opened.st_uid != os.getuid()
        or current.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or stat.S_IMODE(current.st_mode) != 0o700
    ):
        raise OSError("generation directory binding changed")


def _publication_replace_completed(
    generations_descriptor: int,
    pending_name: str,
    generation_name: str,
    expected: os.stat_result,
) -> bool:
    def optional_stat(name: str) -> os.stat_result | None:
        try:
            return os.stat(
                name,
                dir_fd=generations_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None

    source = optional_stat(pending_name)
    destination = optional_stat(generation_name)
    source_matches = source is not None and _same_inode(source, expected)
    destination_matches = destination is not None and _same_inode(
        destination, expected
    )
    if destination_matches:
        return True
    if source_matches and destination is None:
        return False
    raise OSError("publication replace state is ambiguous")


def _probe_rename_noreplace(
    generations_descriptor: int,
    retained_directory_descriptor: int,
    close_capability: CloseRangeCapability,
    probe_descriptor_owner: list[int],
) -> None:
    """Verify no-replace rename support before exposing a normal generation."""

    source_descriptor = -1
    source_name = f".rename-noreplace-probe-source-{uuid.uuid4().hex}"
    target_name = f".rename-noreplace-probe-target-{uuid.uuid4().hex}"
    source_info: os.stat_result | None = None
    try:
        os.mkdir(source_name, mode=0o700, dir_fd=generations_descriptor)
        source_info = os.stat(
            source_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        source_descriptor = _open_owned_descriptor(
            probe_descriptor_owner,
            source_name,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=generations_descriptor,
        )
        opened_source = os.fstat(source_descriptor)
        if (
            not stat.S_ISDIR(opened_source.st_mode)
            or not _same_inode(opened_source, source_info)
            or opened_source.st_uid != os.getuid()
            or stat.S_IMODE(opened_source.st_mode) != 0o700
        ):
            raise OSError("no-replace capability probe source changed")
        renameat2_no_replace(
            generations_descriptor,
            source_name,
            generations_descriptor,
            target_name,
        )
        target_info = os.stat(
            target_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if not _same_inode(target_info, opened_source):
            raise OSError("no-replace capability probe target changed")
    finally:
        isolation_failure: BaseException | None = None
        try:
            if source_info is not None and source_descriptor >= 0:
                source = _optional_stat_at(
                    generations_descriptor,
                    source_name,
                )
                target = _optional_stat_at(
                    generations_descriptor,
                    target_name,
                )
                source_matches = (
                    source is not None
                    and _same_inode(source, source_info)
                )
                target_matches = (
                    target is not None
                    and _same_inode(target, source_info)
                )
                if source_matches == target_matches:
                    raise OSError(
                        "no-replace capability probe state is ambiguous"
                    )
                _isolate_bound_empty_directory_no_replace(
                    generations_descriptor,
                    source_name if source_matches else target_name,
                    source_info,
                    retained_directory_descriptor,
                    ".rename-noreplace-probe-tombstone-",
                    pinned_descriptor=source_descriptor,
                )
        except BaseException as exc:
            isolation_failure = exc
        try:
            os.fsync(generations_descriptor)
        except BaseException as exc:
            if isolation_failure is None:
                isolation_failure = exc
        release_failure = _release_local_descriptor_owners_once(
            probe_descriptor_owner,
            close_capability,
        )
        if isolation_failure is not None:
            raise OSError(
                "no-replace capability probe isolation failed"
            ) from isolation_failure
        if release_failure is not None:
            raise OSError(
                "no-replace capability probe descriptor release failed"
            ) from release_failure


def _release_local_descriptor_owners_once(
    descriptor_owner: list[int],
    close_capability: CloseRangeCapability,
) -> BaseException | None:
    """Release owned fds or preserve unretired slots for caller recovery."""

    release_failure: BaseException | None = None

    def remember_failure(failure: BaseException) -> None:
        nonlocal release_failure
        if release_failure is None:
            release_failure = failure

    def release_all() -> None:
        while descriptor_owner:
            descriptor = descriptor_owner.pop()
            if descriptor < 0:
                continue
            try:
                transaction = filesystem.DeferredCloseFdOnceOutcome()
            except BaseException as exc:
                remember_failure(exc)
                try:
                    os.closerange(descriptor, descriptor + 1)
                except BaseException as fallback_exc:
                    remember_failure(fallback_exc)
                continue
            result = release_owned_descriptor_once(
                descriptor,
                close_capability,
                transaction=transaction,
            )
            for failure in result.failures:
                remember_failure(failure)

    try:
        run_with_deferred_interrupts(release_all)
    except BaseException as exc:
        remember_failure(exc)
        if descriptor_owner:

            def release_remaining_after_outer_escape() -> None:
                while descriptor_owner:
                    descriptor = descriptor_owner.pop()
                    if descriptor < 0:
                        continue
                    try:
                        os.closerange(descriptor, descriptor + 1)
                    except BaseException as fallback_exc:
                        remember_failure(fallback_exc)

            try:
                run_with_deferred_interrupts(
                    release_remaining_after_outer_escape
                )
            except BaseException as fallback_transaction_exc:
                remember_failure(fallback_transaction_exc)
    return release_failure


def _release_descriptor_owners_or_raise(
    descriptor_owner: list[int],
    close_capability: CloseRangeCapability,
    diagnostic: str,
) -> None:
    failure = _release_local_descriptor_owners_once(
        descriptor_owner,
        close_capability,
    )
    if failure is not None:
        raise OSError(diagnostic) from failure


def _probe_rename_exchange(
    generations_descriptor: int,
    rollback_slot_name: str,
    rollback_slot_info: os.stat_result,
    rollback_slot_descriptor: int,
    retained_directory_descriptor: int,
    close_capability: CloseRangeCapability,
    probe_descriptor_owner: list[int],
) -> None:
    """Verify the pre-bound rollback exchange primitive before publication."""

    probe_name = f".rollback-exchange-probe-{uuid.uuid4().hex}"
    probe_descriptor = -1
    try:
        os.mkdir(probe_name, mode=0o700, dir_fd=generations_descriptor)
        probe_info = os.stat(
            probe_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        probe_descriptor = _open_owned_descriptor(
            probe_descriptor_owner,
            probe_name,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=generations_descriptor,
        )
        opened_probe = os.fstat(probe_descriptor)
        rebound_probe = os.stat(
            probe_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(opened_probe.st_mode)
            or not _same_inode(opened_probe, probe_info)
            or not _same_inode(rebound_probe, probe_info)
            or opened_probe.st_uid != os.getuid()
            or rebound_probe.st_uid != os.getuid()
            or stat.S_IMODE(opened_probe.st_mode) != 0o700
            or stat.S_IMODE(rebound_probe.st_mode) != 0o700
        ):
            raise OSError("rollback exchange probe is unsafe")
        state = _ExchangeProbeState(
            slot_name=rollback_slot_name,
            slot_info=rollback_slot_info,
            probe_name=probe_name,
            probe_info=probe_info,
        )

        def phase() -> str:
            slot = os.stat(
                state.slot_name,
                dir_fd=generations_descriptor,
                follow_symlinks=False,
            )
            probe = os.stat(
                state.probe_name,
                dir_fd=generations_descriptor,
                follow_symlinks=False,
            )
            if _same_inode(slot, state.slot_info) and _same_inode(
                probe, state.probe_info
            ):
                return "prepared"
            if _same_inode(slot, state.probe_info) and _same_inode(
                probe, state.slot_info
            ):
                state.exchange_committed = True
                return "exchanged"
            raise OSError("rollback exchange probe state is ambiguous")

        def isolate_bound_empty(
            name: str,
            expected: os.stat_result,
            hidden_prefix: str,
            pinned_descriptor: int,
        ) -> None:
            _isolate_bound_empty_directory_no_replace(
                generations_descriptor,
                name,
                expected,
                retained_directory_descriptor,
                hidden_prefix,
                pinned_descriptor=pinned_descriptor,
            )

        completed = False
        try:
            state.exchange_attempted = True
            try:
                renameat2_exchange(
                    generations_descriptor,
                    state.slot_name,
                    generations_descriptor,
                    state.probe_name,
                )
            except BaseException:
                if phase() != "exchanged":
                    raise
                raise
            if phase() != "exchanged":
                raise OSError("rollback exchange probe binding changed")
            state.restore_attempted = True
            try:
                renameat2_exchange(
                    generations_descriptor,
                    state.slot_name,
                    generations_descriptor,
                    state.probe_name,
                )
            except BaseException:
                restored_phase = phase()
                if restored_phase == "prepared":
                    state.restore_committed = True
                raise
            if phase() != "prepared":
                raise OSError("rollback exchange probe restore changed")
            state.restore_committed = True
            completed = True
        finally:
            current_phase = phase()
            if completed:
                isolate_bound_empty(
                    state.probe_name,
                    state.probe_info,
                    ".rollback-exchange-probe-tombstone-",
                    probe_descriptor,
                )
            elif current_phase == "prepared":
                isolate_bound_empty(
                    state.slot_name,
                    state.slot_info,
                    ".rollback-slot-probe-quarantine-",
                    rollback_slot_descriptor,
                )
                isolate_bound_empty(
                    state.probe_name,
                    state.probe_info,
                    ".rollback-exchange-probe-quarantine-",
                    probe_descriptor,
                )
            else:
                isolate_bound_empty(
                    state.slot_name,
                    state.probe_info,
                    ".rollback-exchange-probe-quarantine-",
                    probe_descriptor,
                )
                isolate_bound_empty(
                    state.probe_name,
                    state.slot_info,
                    ".rollback-slot-probe-quarantine-",
                    rollback_slot_descriptor,
                )
            os.fsync(generations_descriptor)
    finally:
        release_failure = _release_local_descriptor_owners_once(
            probe_descriptor_owner,
            close_capability,
        )
        if release_failure is not None:
            raise OSError(
                "rollback exchange probe descriptor release failed"
            ) from release_failure


def _cleanup_rollback_quarantine(
    generations_descriptor: int,
    quarantine_name: str,
    expected: os.stat_result,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    """Verify and retain one hidden rollback generation without name deletion."""

    if close_capability is None:
        close_capability = require_close_fd_once()
    root_owner: list[int] = []
    try:
        root_descriptor = _open_owned_descriptor(
            root_owner,
            quarantine_name,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=generations_descriptor,
        )
        opened_root = os.fstat(root_descriptor)
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or not _same_inode(opened_root, expected)
            or opened_root.st_uid != os.getuid()
            or stat.S_IMODE(opened_root.st_mode) != 0o700
        ):
            raise OSError("rollback quarantine root changed")
        current_root = os.stat(
            quarantine_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if not _same_inode(current_root, opened_root):
            raise OSError("rollback quarantine root changed")
        raise OSError("rollback quarantine retained for safe recovery")
    finally:
        try:
            _release_descriptor_owners_or_raise(
                root_owner,
                close_capability,
                "rollback quarantine descriptor release failed",
            )
        finally:
            _release_descriptor_owners_or_raise(
                root_owner,
                close_capability,
                "rollback quarantine descriptor release failed",
            )


def _optional_stat_at(
    directory_descriptor: int,
    name: str,
) -> os.stat_result | None:
    try:
        return os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None


def _require_name_absent(
    directory_descriptor: int,
    name: str,
) -> None:
    """Double-check absence so a leaf recreated after the first check fails."""

    for _ in range(2):
        if _optional_stat_at(directory_descriptor, name) is not None:
            raise OSError("pending generation name was recreated")


def _isolate_bound_leaf_no_replace(
    directory_descriptor: int,
    source_name: str,
    expected: os.stat_result,
    hidden_prefix: str,
    *,
    destination_descriptor: int | None = None,
) -> str:
    """Atomically isolate one expected leaf for retained quarantine."""

    target_descriptor = (
        directory_descriptor
        if destination_descriptor is None
        else destination_descriptor
    )

    def restore_unrelated(candidate: str, moved: os.stat_result) -> None:
        try:
            renameat2_no_replace(
                target_descriptor,
                candidate,
                directory_descriptor,
                source_name,
            )
        except BaseException as restore_failure:
            restored = _optional_stat_at(directory_descriptor, source_name)
            hidden = _optional_stat_at(target_descriptor, candidate)
            if (
                restored is not None
                and _same_inode(restored, moved)
                and hidden is None
            ):
                return
            raise OSError(
                "leaf isolation could not restore unrelated inode"
            ) from restore_failure
        restored = os.stat(
            source_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if not _same_inode(restored, moved):
            raise OSError("leaf isolation restore changed")
        if _optional_stat_at(target_descriptor, candidate) is not None:
            raise OSError("leaf isolation restore retained hidden name")

    for _ in range(128):
        candidate = f"{hidden_prefix}{uuid.uuid4().hex}"
        try:
            renameat2_no_replace(
                directory_descriptor,
                source_name,
                target_descriptor,
                candidate,
            )
        except BaseException as isolation_failure:
            source = _optional_stat_at(directory_descriptor, source_name)
            hidden = _optional_stat_at(target_descriptor, candidate)
            if (
                source is None
                and hidden is not None
                and _same_inode(hidden, expected)
            ):
                _require_name_absent(directory_descriptor, source_name)
                return candidate
            if source is None and hidden is not None:
                restore_unrelated(candidate, hidden)
                raise OSError(
                    "leaf isolation source changed"
                ) from isolation_failure
            if (
                isinstance(isolation_failure, FileExistsError)
                and source is not None
                and _same_inode(source, expected)
                and hidden is not None
                and not _same_inode(hidden, expected)
            ):
                continue
            if (
                source is not None
                and _same_inode(source, expected)
                and hidden is None
            ):
                raise
            raise OSError(
                "leaf isolation state is ambiguous"
            ) from isolation_failure

        hidden = os.stat(
            candidate,
            dir_fd=target_descriptor,
            follow_symlinks=False,
        )
        if not _same_inode(hidden, expected):
            restore_unrelated(candidate, hidden)
            raise OSError("leaf isolation source changed")
        _require_name_absent(directory_descriptor, source_name)
        return candidate
    raise OSError("could not allocate leaf isolation name")


def _isolate_bound_empty_directory_no_replace(
    source_directory_descriptor: int,
    source_name: str,
    expected: os.stat_result,
    destination_directory_descriptor: int,
    hidden_prefix: str,
    *,
    pinned_descriptor: int,
) -> str:
    """Move one pinned empty directory without deleting a mutable name."""

    descriptor = pinned_descriptor
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not _same_inode(opened, expected)
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
    ):
        raise OSError("empty-directory isolation binding changed")
    with os.scandir(descriptor) as entries:
        if next(entries, None) is not None:
            raise OSError("empty-directory isolation source is not empty")
    rebound = os.stat(
        source_name,
        dir_fd=source_directory_descriptor,
        follow_symlinks=False,
    )
    if not _same_inode(rebound, opened):
        raise OSError("empty-directory isolation binding changed")

    hidden_name = _isolate_bound_leaf_no_replace(
        source_directory_descriptor,
        source_name,
        opened,
        hidden_prefix,
        destination_descriptor=destination_directory_descriptor,
    )
    retained = os.fstat(descriptor)
    named_hidden = os.stat(
        hidden_name,
        dir_fd=destination_directory_descriptor,
        follow_symlinks=False,
    )
    if (
        not _same_inode(retained, opened)
        or not _same_inode(named_hidden, opened)
        or not stat.S_ISDIR(retained.st_mode)
        or not stat.S_ISDIR(named_hidden.st_mode)
        or retained.st_uid != os.getuid()
        or named_hidden.st_uid != os.getuid()
        or stat.S_IMODE(retained.st_mode) != 0o700
        or stat.S_IMODE(named_hidden.st_mode) != 0o700
    ):
        raise OSError("empty-directory isolation target changed")
    with os.scandir(descriptor) as entries:
        if next(entries, None) is not None:
            raise OSError("empty-directory isolation target is not empty")
    _require_name_absent(source_directory_descriptor, source_name)
    os.fsync(destination_directory_descriptor)
    if destination_directory_descriptor != source_directory_descriptor:
        os.fsync(source_directory_descriptor)
    return hidden_name


def _cleanup_bound_pending_generation(
    generations_descriptor: int,
    pending_descriptor: int,
    pending_name: str,
    expected: os.stat_result,
    *,
    allow_expected_removal: bool,
) -> None:
    """Verify and retain an owned hidden inode without namespace deletion."""

    opened_root = os.fstat(pending_descriptor)
    if (
        not stat.S_ISDIR(opened_root.st_mode)
        or not _same_inode(opened_root, expected)
        or opened_root.st_uid != os.getuid()
        or stat.S_IMODE(opened_root.st_mode) != 0o700
    ):
        raise OSError("pending generation descriptor changed")
    current = _optional_stat_at(generations_descriptor, pending_name)
    if current is None:
        _require_name_absent(generations_descriptor, pending_name)
        return
    if not _same_inode(current, opened_root):
        raise OSError("pending generation name was replaced")
    if allow_expected_removal:
        raise OSError("pending generation retained for safe recovery")
    raise OSError("completed publication retained its pending name")


def _rollback_published_generation(
    generations_descriptor: int,
    state: _RollbackExchangeState,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    """Hide a published generation durably and retain its quarantine."""

    if close_capability is None:
        close_capability = require_close_fd_once()
    generations_info = os.fstat(generations_descriptor)
    if (
        not stat.S_ISDIR(generations_info.st_mode)
        or generations_info.st_uid != os.getuid()
        or stat.S_IMODE(generations_info.st_mode) != 0o700
    ):
        raise OSError("rollback generation directory is unsafe")
    def optional_stat(name: str) -> os.stat_result | None:
        try:
            return os.stat(
                name,
                dir_fd=generations_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None

    def exchange_phase() -> str:
        published = optional_stat(state.published_name)
        slot = optional_stat(state.slot_name)
        if (
            published is not None
            and slot is not None
            and _same_inode(published, state.published_info)
            and _same_inode(slot, state.slot_info)
        ):
            return "prepared"
        if (
            published is not None
            and slot is not None
            and _same_inode(published, state.slot_info)
            and _same_inode(slot, state.published_info)
        ):
            state.exchange_committed = True
            return "exchanged"
        if (
            published is None
            and slot is not None
            and _same_inode(slot, state.published_info)
        ):
            state.exchange_committed = True
            state.placeholder_removed = True
            return "placeholder_removed"
        raise OSError("rollback exchange state is ambiguous")

    phase = exchange_phase()
    if phase == "prepared":
        published_info = state.published_info
        if (
            not stat.S_ISDIR(published_info.st_mode)
            or published_info.st_uid != os.getuid()
            or stat.S_IMODE(published_info.st_mode) != 0o700
        ):
            raise OSError("published generation changed before rollback")
    else:
        published_info = state.published_info
    quarantine_name: str | None = None
    if phase == "prepared":
        for _ in range(128):
            candidate = f".rollback-{uuid.uuid4().hex}"
            try:
                renameat2_no_replace(
                    generations_descriptor,
                    state.published_name,
                    generations_descriptor,
                    candidate,
                )
            except FileExistsError:
                continue
            except OSError:
                if _publication_replace_completed(
                    generations_descriptor,
                    state.published_name,
                    candidate,
                    published_info,
                ):
                    quarantine_name = candidate
                break
            quarantine_name = candidate
            break
    if phase == "prepared" and quarantine_name is None:
        current_slot = os.stat(
            state.slot_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(current_slot.st_mode)
            or not _same_inode(current_slot, state.slot_info)
            or current_slot.st_uid != os.getuid()
            or stat.S_IMODE(current_slot.st_mode) != 0o700
        ):
            raise OSError("rollback exchange slot changed")
        try:
            renameat2_exchange(
                generations_descriptor,
                state.published_name,
                generations_descriptor,
                state.slot_name,
            )
        except BaseException:
            phase = exchange_phase()
            if phase == "prepared":
                raise
        else:
            state.exchange_committed = True
            phase = "exchanged"
    if quarantine_name is None and phase in {
        "exchanged",
        "placeholder_removed",
    }:
        exchanged_slot = os.stat(
            state.slot_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if not _same_inode(exchanged_slot, published_info):
            raise OSError("rollback exchange binding changed")
        if phase == "exchanged":
            exchanged_publication = os.stat(
                state.published_name,
                dir_fd=generations_descriptor,
                follow_symlinks=False,
            )
            if not _same_inode(exchanged_publication, state.slot_info):
                raise OSError("rollback exchange binding changed")
        os.fsync(generations_descriptor)
        if phase == "exchanged":
            placeholder_owner: list[int] = []
            try:
                placeholder_descriptor = _open_owned_descriptor(
                    placeholder_owner,
                    state.published_name,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=generations_descriptor,
                )
                opened_placeholder = os.fstat(placeholder_descriptor)
                if (
                    not stat.S_ISDIR(opened_placeholder.st_mode)
                    or not _same_inode(opened_placeholder, state.slot_info)
                    or opened_placeholder.st_uid != os.getuid()
                    or stat.S_IMODE(opened_placeholder.st_mode) != 0o700
                ):
                    raise OSError("rollback placeholder binding changed")
                hidden_placeholder = _isolate_bound_leaf_no_replace(
                    generations_descriptor,
                    state.published_name,
                    state.slot_info,
                    ".rollback-placeholder-",
                )
                state.placeholder_removed = True
                _cleanup_bound_pending_generation(
                    generations_descriptor,
                    placeholder_descriptor,
                    hidden_placeholder,
                    state.slot_info,
                    allow_expected_removal=True,
                )
            finally:
                try:
                    _release_descriptor_owners_or_raise(
                        placeholder_owner,
                        close_capability,
                        "rollback placeholder descriptor release failed",
                    )
                finally:
                    _release_descriptor_owners_or_raise(
                        placeholder_owner,
                        close_capability,
                        "rollback placeholder descriptor release failed",
                    )
        if optional_stat(state.published_name) is not None:
            raise OSError("rollback exchange placeholder survived")
        os.fsync(generations_descriptor)
        quarantine_name = state.slot_name
    if quarantine_name is None:
        raise OSError("could not allocate rollback quarantine")
    quarantined = os.stat(
        quarantine_name,
        dir_fd=generations_descriptor,
        follow_symlinks=False,
    )
    if not _same_inode(quarantined, published_info):
        raise OSError("rollback quarantine binding changed")
    current_generations = os.fstat(generations_descriptor)
    if (
        not _same_inode(current_generations, generations_info)
        or current_generations.st_uid != os.getuid()
        or stat.S_IMODE(current_generations.st_mode) != 0o700
    ):
        raise OSError("rollback generation directory changed")
    os.fsync(generations_descriptor)
    _cleanup_rollback_quarantine(
        generations_descriptor,
        quarantine_name,
        published_info,
        close_capability,
    )
    os.fsync(generations_descriptor)


def _read_query_source(
    supplied: Path,
    deadline: float,
    monotonic: Callable[[], float],
    close_capability: CloseRangeCapability | None = None,
) -> tuple[Path, bytes, str]:
    if close_capability is None:
        close_capability = require_close_fd_once()
    descriptor_owner: list[int] = []
    try:
        descriptor = _open_owned_descriptor(
            descriptor_owner,
            supplied,
            os.O_RDONLY
            | os.O_NONBLOCK
            | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_QUERY_BYTES:
            raise ValueError("query is not a bounded regular file")
        resolved = supplied.resolve(strict=True)
        current = resolved.lstat()
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_dev != before.st_dev
            or current.st_ino != before.st_ino
        ):
            raise ValueError("query changed during validation")
        raw = bytearray()
        while len(raw) <= _MAX_QUERY_BYTES:
            _require_deadline(deadline, monotonic, "validation")
            chunk = os.read(
                descriptor,
                min(1024 * 1024, _MAX_QUERY_BYTES + 1 - len(raw)),
            )
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        if (
            len(raw) > _MAX_QUERY_BYTES
            or len(raw) != before.st_size
            or after.st_size != before.st_size
            or after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
        ):
            raise ValueError("query changed while reading")
        payload = bytes(raw)
        return resolved, payload, hashlib.sha256(payload).hexdigest()
    finally:
        try:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "query source descriptor release failed",
            )
        finally:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "query source descriptor release failed",
            )


def _write_query_snapshot(
    payload: bytes,
    destination: Path,
    deadline: float,
    monotonic: Callable[[], float],
    close_capability: CloseRangeCapability | None = None,
) -> None:
    if close_capability is None:
        close_capability = require_close_fd_once()
    lexical_destination = Path(os.path.abspath(os.fspath(destination)))
    parent = lexical_destination.parent
    parent_discovered = parent.lstat()
    if (
        not stat.S_ISDIR(parent_discovered.st_mode)
        or parent_discovered.st_uid != os.getuid()
        or parent_discovered.st_nlink < 1
    ):
        raise OSError("query snapshot parent is unsafe")
    descriptor_owner: list[int] = []
    try:
        parent_descriptor = _open_owned_descriptor(
            descriptor_owner,
            parent,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        parent_opened = os.fstat(parent_descriptor)
        if (
            not _same_owned_node(parent_opened, parent_discovered)
            or stat.S_IMODE(parent_opened.st_mode)
            != stat.S_IMODE(parent_discovered.st_mode)
        ):
            raise OSError("query snapshot parent changed before creation")

        descriptor_owner.append(-1)
        destination_slot = len(descriptor_owner) - 1

        def acquire_destination() -> int:
            try:
                descriptor = os.open(
                    lexical_destination.name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except BaseException:
                descriptor_owner.pop()
                raise
            descriptor_owner[destination_slot] = descriptor
            return descriptor

        descriptor = run_with_deferred_interrupts(acquire_destination)
        discovered = os.stat(
            lexical_destination.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or not _same_owned_node(opened, discovered)
        ):
            raise OSError("query snapshot binding is unsafe")
        os.fchmod(descriptor, 0o600)
        for offset in range(0, len(payload), 1024 * 1024):
            _require_deadline(deadline, monotonic, "query_run")
            view = memoryview(payload[offset : offset + 1024 * 1024])
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("query snapshot write made no progress")
                view = view[written:]
        os.fsync(descriptor)
        rebound = os.fstat(descriptor)
        rebound_name = os.stat(
            lexical_destination.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        lexical_rebound = lexical_destination.lstat()
        parent_rebound = parent.lstat()
        if (
            not _same_owned_node(rebound, opened)
            or not _same_owned_node(rebound_name, opened)
            or not _same_owned_node(lexical_rebound, opened)
            or not _same_owned_node(parent_rebound, parent_opened)
            or rebound.st_nlink != 1
            or rebound.st_size != len(payload)
            or stat.S_IMODE(rebound.st_mode) != 0o600
            or stat.S_IMODE(rebound_name.st_mode) != 0o600
            or stat.S_IMODE(lexical_rebound.st_mode) != 0o600
        ):
            raise OSError("query snapshot binding changed while writing")
    finally:
        try:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "query snapshot descriptor release failed",
            )
        finally:
            _release_descriptor_owners_or_raise(
                descriptor_owner,
                close_capability,
                "query snapshot descriptor release failed",
            )


def _release_execution_snapshot_descriptor(
    descriptor: int,
    capability: CloseRangeCapability,
) -> BaseException | None:
    """Release a completed snapshot fd without blocking path ownership transfer.

    The raw close has a proved pre-action error class.  Only a structurally
    stored released/post-action state permits path transfer; a setup escape
    before the action uses the still-owned fallback.
    """

    try:
        transaction = filesystem.DeferredCloseFdOnceOutcome()
    except BaseException as exc:
        try:
            os.closerange(descriptor, descriptor + 1)
        except BaseException:
            pass
        return exc
    release = release_owned_descriptor_once(
        descriptor,
        capability,
        transaction=transaction,
    )
    if release.explicitly_consumed:
        return None
    if release.primary_error is not None:
        return release.primary_error
    if release.transaction_error is not None:
        return release.transaction_error
    if release.callback_error is not None:
        return release.callback_error
    if release.fallback_error is not None:
        return release.fallback_error
    return OSError("execution snapshot descriptor release failed")


def _create_execution_snapshot(
    snapshot: Path,
    query_path: Path,
    deadline: float,
    monotonic: Callable[[], float],
) -> Path:
    close_capability = require_close_fd_once()
    destination_owner: list[OwnedTemporaryFile] = []
    source = -1
    source_owner: list[int] = []
    execution_path: Path | None = None
    completed = False
    try:
        destination = _create_owned_tempfile(
            destination_owner,
            directory=query_path.parent,
            prefix=f".{query_path.stem}.dosweb.",
            suffix=query_path.suffix,
        )
        descriptor = destination.descriptor
        execution_path = Path(destination.path)
        os.fchmod(descriptor, 0o400)
        source = _open_owned_descriptor(
            source_owner,
            snapshot,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        while True:
            _require_deadline(deadline, monotonic, "query_run")
            chunk = os.read(source, 1024 * 1024)
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
        os.fsync(descriptor)
        completed = True
    finally:
        release_failure: BaseException | None = None

        def release_snapshot_owners() -> None:
            nonlocal completed, release_failure
            cleanup_path = execution_path
            try:
                while source_owner:
                    owned_source = source_owner.pop()
                    if owned_source >= 0:
                        failure = _release_execution_snapshot_descriptor(
                            owned_source,
                            close_capability,
                        )
                        if release_failure is None and failure is not None:
                            release_failure = failure
            finally:
                try:
                    while destination_owner:
                        owned_destination = destination_owner.pop()
                        if cleanup_path is None:
                            cleanup_path = Path(owned_destination.path)
                        if owned_destination.descriptor >= 0:
                            failure = _release_execution_snapshot_descriptor(
                                owned_destination.descriptor,
                                close_capability,
                            )
                            if (
                                release_failure is None
                                and failure is not None
                            ):
                                release_failure = failure
                finally:
                    if release_failure is not None:
                        completed = False
                    if not completed and cleanup_path is not None:
                        cleanup_path.unlink(missing_ok=True)
                    if release_failure is not None:
                        raise release_failure

        run_with_deferred_interrupts(release_snapshot_owners)
    assert execution_path is not None
    return execution_path


def _descriptor_output_binding(
    output: Path,
    descriptor: int,
) -> os.stat_result:
    if (
        isinstance(descriptor, bool)
        or not isinstance(descriptor, int)
        or descriptor < 0
        or output != Path(f"/proc/self/fd/{descriptor}")
    ):
        raise ValueError("output descriptor binding is invalid")
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("output descriptor is not a private directory")
    return info


def _release_query_output_descriptor(
    descriptor: int,
    capability: CloseRangeCapability,
) -> bool:
    try:
        transaction = filesystem.DeferredCloseFdOnceOutcome()
    except BaseException:
        try:
            os.closerange(descriptor, descriptor + 1)
        except BaseException:
            pass
        return False
    return release_owned_descriptor_once(
        descriptor,
        capability,
        transaction=transaction,
    ).succeeded


def _release_owned_query_output_binding(
    binding: _QueryOutputBinding,
) -> bool:
    released = True

    def release_binding() -> None:
        nonlocal released
        for field in (
            "decoded_descriptor",
            "generation_descriptor",
            "generations_descriptor",
        ):
            descriptor = getattr(binding, field)
            setattr(binding, field, -1)
            if descriptor >= 0 and not _release_query_output_descriptor(
                descriptor,
                binding.close_capability,
            ):
                released = False

    try:
        run_with_deferred_interrupts(release_binding)
    except BaseException:
        released = False
    return released


def _pin_query_output_binding(
    results_descriptor: int,
    generation_name: str,
    decoded_name: str,
    capability: CloseRangeCapability,
    *,
    source_generations_descriptor: int | None = None,
    expected_generations_info: os.stat_result | None = None,
    expected_generation_info: os.stat_result | None = None,
    source_decoded_descriptor: int | None = None,
    expected_decoded_info: os.stat_result | None = None,
    expected_decoded_size: int | None = None,
    expected_decoded_sha256: str | None = None,
    expected_decoded_bytes: bytes | None = None,
    owner_holder: list[_QueryOutputBinding] | None = None,
) -> _QueryOutputBinding:
    if (
        not _SAFE_QUERY_NAME.fullmatch(generation_name)
        or not _SAFE_QUERY_NAME.fullmatch(decoded_name)
    ):
        raise _query_failed(
            "publication", diagnostic="published output name is unsafe"
        )
    generations_descriptor = -1
    generation_descriptor = -1
    decoded_descriptor = -1
    local_owner: list[int] = []
    binding: _QueryOutputBinding | None = None
    binding_owned = False
    borrowed_decoded = source_decoded_descriptor is not None
    if borrowed_decoded and (
        expected_decoded_info is None
        or expected_decoded_size is None
        or expected_decoded_sha256 is None
        or expected_decoded_bytes is None
        or owner_holder is None
    ):
        raise _query_failed(
            "publication",
            diagnostic="published decoded output owner is invalid",
        )
    try:
        if source_generations_descriptor is None:
            generations_descriptor = _open_owned_descriptor(
                local_owner,
                ".generations",
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=results_descriptor,
            )
        else:
            generations_descriptor = _open_owned_descriptor(
                local_owner,
                ".",
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=source_generations_descriptor,
            )
        generations_info = os.fstat(generations_descriptor)
        named_generations = os.stat(
            ".generations",
            dir_fd=results_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(generations_info.st_mode)
            or not _same_inode(generations_info, named_generations)
            or (
                expected_generations_info is not None
                and not _same_inode(
                    generations_info, expected_generations_info
                )
            )
            or generations_info.st_uid != os.getuid()
            or stat.S_IMODE(generations_info.st_mode) != 0o700
        ):
            raise OSError("published generations binding changed")
        generation_descriptor = _open_owned_descriptor(
            local_owner,
            generation_name,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=generations_descriptor,
        )
        generation_info = os.fstat(generation_descriptor)
        named_generation = os.stat(
            generation_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(generation_info.st_mode)
            or not _same_inode(generation_info, named_generation)
            or (
                expected_generation_info is not None
                and not _same_inode(
                    generation_info, expected_generation_info
                )
            )
            or generation_info.st_uid != os.getuid()
            or stat.S_IMODE(generation_info.st_mode) != 0o700
        ):
            raise OSError("published generation binding changed")
        if source_decoded_descriptor is None:
            decoded_descriptor = _open_owned_descriptor(
                local_owner,
                decoded_name,
                os.O_RDONLY
                | os.O_NONBLOCK
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=generation_descriptor,
            )
        else:
            decoded_descriptor = source_decoded_descriptor
        decoded_info = os.fstat(decoded_descriptor)
        named_decoded = os.stat(
            decoded_name,
            dir_fd=generation_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(decoded_info.st_mode)
            or not _same_inode(decoded_info, named_decoded)
            or (
                expected_decoded_info is not None
                and not _same_inode(
                    decoded_info, expected_decoded_info
                )
            )
            or decoded_info.st_uid != os.getuid()
            or decoded_info.st_size > _MAX_DECODED_BYTES
        ):
            raise OSError("published decoded output binding changed")
        raw = bytearray()
        offset = 0
        while len(raw) <= _MAX_DECODED_BYTES:
            chunk = os.pread(
                decoded_descriptor,
                min(
                    1024 * 1024,
                    _MAX_DECODED_BYTES + 1 - len(raw),
                ),
                offset,
            )
            if not chunk:
                break
            raw.extend(chunk)
            offset += len(chunk)
        if len(raw) > _MAX_DECODED_BYTES:
            raise OSError("published decoded output exceeds limit")
        current_decoded_bytes = bytes(raw)
        current_decoded_sha256 = hashlib.sha256(
            current_decoded_bytes
        ).hexdigest()
        if expected_decoded_bytes is None:
            decoded_bytes = current_decoded_bytes
            decoded_size = len(decoded_bytes)
            decoded_sha256 = current_decoded_sha256
        else:
            decoded_bytes = expected_decoded_bytes
            decoded_size = expected_decoded_size
            decoded_sha256 = expected_decoded_sha256
        if (
            decoded_size is None
            or decoded_sha256 is None
            or decoded_size != len(decoded_bytes)
            or decoded_info.st_size != decoded_size
            or hashlib.sha256(decoded_bytes).hexdigest()
            != decoded_sha256
            or len(current_decoded_bytes) != decoded_size
            or current_decoded_sha256 != decoded_sha256
        ):
            raise OSError("published decoded content binding changed")
        binding = _QueryOutputBinding(
            close_capability=capability,
            generations_descriptor=generations_descriptor,
            generations_info=generations_info,
            generation_name=generation_name,
            generation_descriptor=generation_descriptor,
            generation_info=generation_info,
            decoded_name=decoded_name,
            decoded_descriptor=decoded_descriptor,
            decoded_info=decoded_info,
            decoded_size=decoded_size,
            decoded_sha256=decoded_sha256,
            decoded_bytes=decoded_bytes,
        )
        if owner_holder is not None:
            append_failure: BaseException | None = None

            def transfer() -> None:
                nonlocal append_failure, binding_owned
                try:
                    owner_holder.append(binding)
                except BaseException as exc:
                    append_failure = exc
                finally:
                    binding_owned = any(
                        item is binding
                        for item in list.__iter__(owner_holder)
                    )

            run_with_deferred_interrupts(transfer)
            if append_failure is not None:
                raise append_failure
        return binding
    except BaseException as exc:
        if binding is not None and owner_holder is not None:
            binding_owned = binding_owned or any(
                item is binding for item in owner_holder
            )
        if binding_owned:
            raise _query_failed(
                "publication", diagnostic="published output binding failed"
            ) from exc
        released = True
        if binding is not None:
            if not borrowed_decoded:
                binding.decoded_descriptor = -1
            binding.generation_descriptor = -1
            binding.generations_descriptor = -1

        def release_local_owner() -> None:
            nonlocal released
            while local_owner:
                descriptor = local_owner.pop()
                if descriptor >= 0 and not _release_query_output_descriptor(
                    descriptor,
                    capability,
                ):
                    released = False

        try:
            run_with_deferred_interrupts(release_local_owner)
        except BaseException:
            released = False
        if not released:
            raise _query_failed(
                "publication",
                diagnostic="published output descriptor release failed",
            ) from exc
        if isinstance(exc, AnalyzerError):
            raise
        raise _query_failed(
            "publication", diagnostic="published output binding failed"
        ) from exc


def _require_output_descriptor_binding(
    descriptor: int | None,
    expected: os.stat_result | None,
    *,
    stage: str,
) -> None:
    if descriptor is None:
        return
    assert expected is not None
    try:
        current = os.fstat(descriptor)
    except OSError as exc:
        raise _query_failed(
            stage,
            diagnostic="output descriptor binding changed",
        ) from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or not _same_inode(current, expected)
        or current.st_uid != expected.st_uid
        or stat.S_IMODE(current.st_mode) != stat.S_IMODE(expected.st_mode)
    ):
        raise _query_failed(
            stage,
            diagnostic="output descriptor binding changed",
        )


def run_query(
    query: Path | str,
    database: DatabaseInfo,
    output_dir: Path | str,
    *,
    output_descriptor: int | None = None,
    retain_output_binding: bool = False,
    result_owner_callback: Callable[[QueryResult], None] | None = None,
    codeql_binary: str = "codeql",
    timeout_seconds: int = 300,
    environment: Mapping[str, str] | None = None,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    monotonic: Callable[[], float] = time.monotonic,
) -> QueryResult:
    supplied_query = Path(query)
    if not isinstance(database, DatabaseInfo):
        raise _query_failed("validation", diagnostic="database has not been validated")
    binding = database.execution
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 3600:
        raise _query_failed("validation", diagnostic="timeout is outside the supported range")
    try:
        close_capability = require_close_fd_once()
    except OSError as exc:
        raise _query_failed(
            "validation",
            diagnostic="descriptor release capability is unavailable",
        ) from exc
    deadline = monotonic() + timeout_seconds
    try:
        query_path, query_payload, initial_query_sha256 = _read_query_source(
            supplied_query,
            deadline,
            monotonic,
            close_capability,
        )
    except (OSError, ValueError) as exc:
        raise _query_failed("validation", diagnostic="query file is invalid") from exc
    stem = query_path.stem
    if not _SAFE_QUERY_NAME.fullmatch(stem):
        raise _query_failed("validation", diagnostic="query name is unsafe")
    query_name = _query_family(stem)

    output = Path(output_dir)
    output_descriptor_info: os.stat_result | None = None
    inherited_output_fds: tuple[int, ...] = ()
    if not isinstance(retain_output_binding, bool):
        raise _query_failed(
            "validation", diagnostic="output binding policy is invalid"
        )
    if retain_output_binding and output_descriptor is None:
        raise _query_failed(
            "validation", diagnostic="output descriptor binding is required"
        )
    if result_owner_callback is not None and (
        not retain_output_binding or not callable(result_owner_callback)
    ):
        raise _query_failed(
            "validation", diagnostic="output binding owner is invalid"
        )
    if output_descriptor is not None:
        try:
            output_descriptor_info = _descriptor_output_binding(
                output,
                output_descriptor,
            )
        except (OSError, ValueError) as exc:
            raise _query_failed(
                "validation", diagnostic="output directory is invalid"
            ) from exc
        inherited_output_fds = (output_descriptor,)
    if binding is not None:
        try:
            resolved_execution_root = binding.path.resolve(strict=True)
            resolved_candidate_output = output.resolve(strict=False)
            resolved_candidate_output.relative_to(resolved_execution_root)
        except ValueError:
            pass
        except (OSError, RuntimeError) as exc:
            raise _query_failed(
                "validation", diagnostic="output directory is invalid"
            ) from exc
        else:
            raise _query_failed(
                "validation",
                diagnostic="output directory overlaps execution database",
            )
    try:
        if output_descriptor is None:
            if output.exists() and output.is_symlink():
                raise ValueError("output symlink is not supported")
            output.mkdir(parents=True, exist_ok=True)
            output = output.resolve(strict=True)
            if not output.is_dir():
                raise ValueError("output is not a directory")
        else:
            _require_output_descriptor_binding(
                output_descriptor,
                output_descriptor_info,
                stage="validation",
            )
        if binding is not None:
            try:
                output.resolve(strict=True).relative_to(
                    resolved_execution_root
                )
            except ValueError:
                pass
            else:
                raise ValueError("output overlaps execution database")
        generations = output / ".generations"
        _harden_owned_path(
            generations,
            kind="directory",
            mode=0o700,
            create_directory=True,
            parent_descriptor=output_descriptor,
            expected_parent=output_descriptor_info,
            close_capability=close_capability,
        )
    except (OSError, ValueError) as exc:
        raise _query_failed("validation", diagnostic="output directory is invalid") from exc

    try:
        current_database = validate_database(
            database.path, deadline=deadline, monotonic=monotonic
        )
    except TimeoutError as exc:
        raise _query_failed("validation", diagnostic="query deadline exceeded") from exc
    if current_database.fingerprint != database.fingerprint or current_database.source_root != database.source_root:
        raise _query_failed("validation", diagnostic="database changed after validation")
    try:
        validate_canonical_database(
            database,
            actual_database=current_database,
            deadline=deadline,
            monotonic=monotonic,
        )
    except (AnalyzerError, TimeoutError) as exc:
        raise _query_failed("validation", diagnostic="database changed after validation") from exc

    execution_database_path = database.path if binding is None else binding.path

    source_environment = dict(os.environ if environment is None else environment)
    minimal_environment = _minimal_environment(source_environment)
    secrets = tuple(
        value for key, value in source_environment.items()
        if isinstance(value, str) and value and any(marker in key.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH"))
    )
    if binding is not None:
        secrets = (*secrets, str(binding.path))
    _require_deadline(deadline, monotonic, "validation")
    pending: Path | None = None
    pending_name: str | None = None
    pending_descriptor = -1
    pending_identity_anchor = -1
    pending_info: os.stat_result | None = None
    snapshot_query: Path | None = None
    temporary_bqrs: Path | None = None
    temporary_json: Path | None = None
    query_sha256 = ""
    bqrs_sha256 = ""
    published: Path | None = None
    execution_query: Path | None = None
    generations_descriptor = -1
    generations_rollback_descriptor = -1
    generations_rollback_anchor = -1
    generations_cleanup_anchor = -1
    rollback_slot_descriptor = -1
    generations_rollback_descriptor_owner: list[int] = []
    generations_rollback_anchor_owner: list[int] = []
    generations_cleanup_anchor_owner: list[int] = []
    rollback_slot_descriptor_owner: list[int] = []
    noreplace_probe_descriptor_owner: list[int] = []
    exchange_probe_descriptor_owner: list[int] = []
    generations_descriptor_owner: list[int] = []
    pending_descriptor_owner: list[int] = []
    pending_identity_anchor_owner: list[int] = []
    generations_info: os.stat_result | None = None
    generation_name: str | None = None
    committed = False
    rollback_slot_name: str | None = None
    rollback_slot_info: os.stat_result | None = None
    rollback_state: _RollbackExchangeState | None = None
    publication_state: _PublicationReplaceState | None = None
    private_output_bindings: list[_QueryOutputBinding] = []
    decoded_output_owners: list[_DecodedOutputSnapshot] = []
    publication_exit_failure = False

    def rollback_attempted_publication(descriptor: int) -> None:
        nonlocal published, committed
        state = publication_state
        if state is None or not state.attempted or state.resolved:
            return
        if state.slot_retired:
            force_descriptor_bound_recovery(descriptor)
            return
        if state.rollback_started:
            assert rollback_state is not None
            _rollback_published_generation(
                descriptor,
                rollback_state,
                close_capability,
            )
            published = None
        else:
            replace_completed = _publication_replace_completed(
                descriptor,
                state.pending_name,
                state.published_name,
                state.expected_info,
            )
            if replace_completed:
                state.rollback_started = True
                assert rollback_state is not None
                _rollback_published_generation(
                    descriptor,
                    rollback_state,
                    close_capability,
                )
                published = None
        state.resolved = True
        state.rollback_required = False
        committed = False

    def pending_cleanup_is_safe() -> bool:
        state = publication_state
        return (
            state is None
            or not state.attempted
            or state.resolved
        )

    def finalize_pending_generation(
        descriptor: int,
        *,
        allow_expected_removal: bool,
    ) -> None:
        actual_descriptor = (
            pending_identity_anchor
            if pending_identity_anchor >= 0
            else pending_descriptor
        )
        if (
            actual_descriptor < 0
            or pending_name is None
            or pending_info is None
        ):
            return
        _cleanup_bound_pending_generation(
            descriptor,
            actual_descriptor,
            pending_name,
            pending_info,
            allow_expected_removal=allow_expected_removal,
        )

    def require_expected_generation_not_normal(descriptor: int) -> None:
        state = publication_state
        if state is None:
            return
        for _ in range(2):
            normal = _optional_stat_at(descriptor, state.published_name)
            if normal is not None:
                if _same_inode(normal, state.expected_info):
                    raise OSError("expected generation remains published")
                raise OSError("published generation name was replaced")

    def require_published_generation_binding(
        descriptor: int,
    ) -> os.stat_result:
        state = publication_state
        if state is None:
            raise OSError("publication state is unavailable")
        actual_descriptor = (
            pending_identity_anchor
            if pending_identity_anchor >= 0
            else pending_descriptor
        )
        if actual_descriptor < 0:
            raise OSError("published generation descriptor is unavailable")
        opened = os.fstat(actual_descriptor)
        named = os.stat(
            state.published_name,
            dir_fd=descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or not _same_inode(opened, state.expected_info)
            or not _same_inode(named, state.expected_info)
            or not _same_inode(opened, named)
            or opened.st_uid != os.getuid()
            or named.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != 0o700
            or stat.S_IMODE(named.st_mode) != 0o700
        ):
            raise OSError("published generation binding changed")
        return opened

    def recover_attempted_publication(descriptor: int) -> None:
        """Final inode-bound recovery independent of the caller rebuild helper."""

        nonlocal published, committed
        state = publication_state
        if state is None or not state.attempted or state.resolved:
            return
        if state.slot_retired:
            force_descriptor_bound_recovery(descriptor)
            return
        actual_descriptor = (
            pending_identity_anchor
            if pending_identity_anchor >= 0
            else pending_descriptor
        )
        if actual_descriptor < 0:
            raise OSError("pending generation ownership is unavailable")
        opened = os.fstat(actual_descriptor)
        if not _same_inode(opened, state.expected_info):
            raise OSError("pending generation ownership changed")
        pending_at_name = _optional_stat_at(descriptor, state.pending_name)
        published_at_name = _optional_stat_at(
            descriptor, state.published_name
        )
        pending_matches = pending_at_name is not None and _same_inode(
            pending_at_name, state.expected_info
        )
        published_matches = published_at_name is not None and _same_inode(
            published_at_name, state.expected_info
        )
        if published_matches or state.rollback_started:
            state.rollback_started = True
            try:
                assert rollback_state is not None
                _rollback_published_generation(
                    descriptor,
                    rollback_state,
                    close_capability,
                )
            except BaseException:
                require_expected_generation_not_normal(descriptor)
                state.resolved = True
                state.rollback_required = False
                published = None
                committed = False
                raise
            require_expected_generation_not_normal(descriptor)
        elif pending_matches and published_at_name is None:
            try:
                finalize_pending_generation(
                    descriptor,
                    allow_expected_removal=True,
                )
            except BaseException:
                require_expected_generation_not_normal(descriptor)
                state.resolved = True
                state.rollback_required = False
                published = None
                committed = False
                raise
        else:
            require_expected_generation_not_normal(descriptor)
            if pending_at_name is not None:
                raise OSError("pending generation name was replaced")
        state.resolved = True
        state.rollback_required = False
        published = None
        committed = False

    def force_descriptor_bound_recovery(descriptor: int) -> None:
        """Last-resort isolation of any recognizable normal generation leaf."""

        nonlocal published, committed
        state = publication_state
        if state is None or not state.attempted or state.resolved:
            return
        actual_descriptor = (
            pending_identity_anchor
            if pending_identity_anchor >= 0
            else pending_descriptor
        )
        if actual_descriptor < 0:
            raise OSError("actual generation ownership is unavailable")
        actual = os.fstat(actual_descriptor)
        if not _same_inode(actual, state.expected_info):
            raise OSError("actual generation ownership changed")

        def remove_empty_placeholder(
            normal_info: os.stat_result,
        ) -> None:
            placeholder_owner: list[int] = []
            try:
                placeholder = _open_owned_descriptor(
                    placeholder_owner,
                    state.published_name,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
                opened = os.fstat(placeholder)
                if (
                    not _same_inode(opened, normal_info)
                    or opened.st_uid != os.getuid()
                    or stat.S_IMODE(opened.st_mode) != 0o700
                ):
                    raise OSError("rollback placeholder binding changed")
                with os.scandir(placeholder) as entries:
                    if next(entries, None) is not None:
                        raise OSError("rollback placeholder is not empty")
                quarantine_name = _isolate_bound_leaf_no_replace(
                    descriptor,
                    state.published_name,
                    opened,
                    ".rollback-placeholder-",
                )
                _cleanup_bound_pending_generation(
                    descriptor,
                    placeholder,
                    quarantine_name,
                    opened,
                    allow_expected_removal=True,
                )
            finally:
                try:
                    _release_descriptor_owners_or_raise(
                        placeholder_owner,
                        close_capability,
                        "rollback placeholder descriptor release failed",
                    )
                finally:
                    _release_descriptor_owners_or_raise(
                        placeholder_owner,
                        close_capability,
                        "rollback placeholder descriptor release failed",
                    )

        try:
            normal = _optional_stat_at(descriptor, state.published_name)
            if normal is None:
                _require_name_absent(descriptor, state.published_name)
            elif _same_inode(normal, state.expected_info):
                quarantine_name = _isolate_bound_leaf_no_replace(
                    descriptor,
                    state.published_name,
                    state.expected_info,
                    ".rollback-final-",
                )
                _cleanup_bound_pending_generation(
                    descriptor,
                    actual_descriptor,
                    quarantine_name,
                    state.expected_info,
                    allow_expected_removal=True,
                )
            elif (
                rollback_state is not None
                and _same_inode(normal, rollback_state.slot_info)
            ):
                remove_empty_placeholder(normal)
            else:
                raise OSError("published generation name was replaced")
            _require_name_absent(descriptor, state.published_name)
        except BaseException:
            _require_name_absent(descriptor, state.published_name)
            state.resolved = True
            state.rollback_required = False
            published = None
            committed = False
            raise
        state.resolved = True
        state.rollback_required = False
        published = None
        committed = False

    if binding is not None:
        binding.lock.acquire()
    try:
        generations_descriptor_owner.append(-1)

        def acquire_generations_directory() -> None:
            nonlocal generations_descriptor, generations_info
            try:
                descriptor, info = _pin_generation_directory(
                    generations,
                    close_capability,
                )
            except BaseException:
                generations_descriptor_owner.pop()
                raise
            generations_descriptor_owner[0] = descriptor
            generations_descriptor = descriptor
            generations_info = info

        run_with_deferred_interrupts(acquire_generations_directory)
        for _ in range(128):
            candidate = f".{stem}.pending.{uuid.uuid4().hex}"
            try:
                os.mkdir(
                    candidate,
                    mode=0o700,
                    dir_fd=generations_descriptor,
                )
            except FileExistsError:
                continue
            pending_name = candidate
            break
        if pending_name is None:
            raise OSError("could not allocate pending generation")
        pending_descriptor = _open_owned_descriptor(
            pending_descriptor_owner,
            pending_name,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=generations_descriptor,
        )
        pending_info = os.fstat(pending_descriptor)
        current_pending = os.stat(
            pending_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(pending_info.st_mode)
            or not _same_inode(pending_info, current_pending)
            or pending_info.st_uid != os.getuid()
            or stat.S_IMODE(pending_info.st_mode) != 0o700
        ):
            raise OSError("pending generation binding changed")
        pending_identity_anchor = _open_owned_descriptor(
            pending_identity_anchor_owner,
            ".",
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=pending_descriptor,
        )
        identity_info = os.fstat(pending_identity_anchor)
        if not _same_inode(identity_info, pending_info):
            raise OSError("pending generation identity anchor changed")
        pending = generations / pending_name
        snapshot_query = pending / query_path.name
        temporary_bqrs = pending / f"{stem}.bqrs"
        temporary_json = pending / f"{stem}.json"
        if binding is not None:
            validate_execution_database(
                database,
                deadline=deadline,
                monotonic=monotonic,
            )
        query_sha256 = initial_query_sha256
        assert snapshot_query is not None
        assert temporary_bqrs is not None
        assert temporary_json is not None
        _write_query_snapshot(
            query_payload,
            snapshot_query,
            deadline,
            monotonic,
            close_capability,
        )

        def acquire_execution_query() -> None:
            nonlocal execution_query
            execution_query = _create_execution_snapshot(
                snapshot_query,
                query_path,
                deadline,
                monotonic,
            )

        run_with_deferred_interrupts(acquire_execution_query)
        if deadline - monotonic() <= 0:
            raise _query_failed("query_run", diagnostic="query deadline exceeded")
        query_failure: BaseException | None = None
        try:
            _require_output_descriptor_binding(
                output_descriptor,
                output_descriptor_info,
                stage="query_run",
            )
            _invoke(
                [codeql_binary, "query", "run", str(execution_query), "--database", str(execution_database_path), "--output", str(temporary_bqrs)],
                stage="query_run",
                timeout_seconds=deadline - monotonic(),
                environment=minimal_environment,
                subprocess_run=subprocess_run,
                secrets=secrets,
                pass_fds=inherited_output_fds,
            )
        except BaseException as exc:
            query_failure = exc
        _require_output_descriptor_binding(
            output_descriptor,
            output_descriptor_info,
            stage="query_run",
        )
        try:
            after_query_database = validate_database(
                database.path, deadline=deadline, monotonic=monotonic
            )
        except TimeoutError as exc:
            raise _query_failed("validation", diagnostic="query deadline exceeded") from exc
        if (
            after_query_database.fingerprint != database.fingerprint
            or after_query_database.source_root != database.source_root
        ):
            raise _query_failed(
                "validation", diagnostic="database changed during query execution"
            )
        try:
            validate_canonical_database(
                database,
                actual_database=after_query_database,
                deadline=deadline,
                monotonic=monotonic,
            )
        except (AnalyzerError, TimeoutError) as exc:
            raise _query_failed(
                "validation", diagnostic="database changed during query execution"
            ) from exc
        if binding is not None:
            validate_execution_database(
                database,
                deadline=deadline,
                monotonic=monotonic,
            )
        if query_failure is not None:
            raise query_failure
        try:
            current_query_sha256 = _deadline_file_sha256(
                query_path,
                deadline,
                monotonic,
                "query_run",
                close_capability,
            )
        except AnalyzerError:
            raise
        except OSError as exc:
            raise _query_failed("query_run", diagnostic="query could not be revalidated") from exc
        if current_query_sha256 != query_sha256:
            raise _query_failed("query_run", diagnostic="query changed during execution")
        _require_regular_output(
            temporary_bqrs,
            _MAX_BQRS_BYTES,
            "query_run",
            close_capability,
        )
        _require_output_descriptor_binding(
            output_descriptor,
            output_descriptor_info,
            stage="bqrs_decode",
        )
        _invoke(
            [codeql_binary, "bqrs", "decode", str(temporary_bqrs), "--format=json", "--output", str(temporary_json)],
            stage="bqrs_decode",
            timeout_seconds=deadline - monotonic(),
            environment=minimal_environment,
            subprocess_run=subprocess_run,
            secrets=secrets,
            pass_fds=inherited_output_fds,
        )
        _require_output_descriptor_binding(
            output_descriptor,
            output_descriptor_info,
            stage="bqrs_decode",
        )
        assert pending_descriptor >= 0
        assert close_capability is not None
        _pin_decoded_output(
            pending_descriptor,
            temporary_json.name,
            close_capability,
            decoded_output_owners,
        )
        _read_decoded_json(
            temporary_json,
            query_name,
            database,
            query_sha256,
            deadline,
            monotonic,
            descriptor_owner=decoded_output_owners,
        )
        if deadline - monotonic() <= 0:
            raise _query_failed("validation", diagnostic="query deadline exceeded")
        after_database = validate_database(
            database.path, deadline=deadline, monotonic=monotonic
        )
        if after_database.fingerprint != database.fingerprint or after_database.source_root != database.source_root:
            raise _query_failed("validation", diagnostic="database changed during query execution")
        try:
            validate_canonical_database(
                database,
                actual_database=after_database,
                deadline=deadline,
                monotonic=monotonic,
            )
        except (AnalyzerError, TimeoutError) as exc:
            raise _query_failed(
                "validation", diagnostic="database changed during query execution"
            ) from exc
        if binding is not None:
            validate_execution_database(
                database,
                deadline=deadline,
                monotonic=monotonic,
            )
        _require_output_descriptor_binding(
            output_descriptor,
            output_descriptor_info,
            stage="publication",
        )
        bqrs_sha256 = _deadline_file_sha256(
            temporary_bqrs,
            deadline,
            monotonic,
            "publication",
            close_capability,
        )
        _validate_publication_databases(database, deadline, monotonic)
        if deadline - monotonic() <= 0:
            raise _query_failed("publication", diagnostic="query deadline exceeded")
        for path in (snapshot_query, temporary_bqrs):
            _require_deadline(deadline, monotonic, "publication")
            _fsync_file(path, close_capability)
        assert decoded_output_owners
        decoded_snapshot = decoded_output_owners[0]
        _require_deadline(deadline, monotonic, "publication")
        _require_decoded_snapshot_current(
            pending_descriptor,
            temporary_json.name,
            decoded_snapshot,
            stage="publication",
        )
        os.fsync(decoded_snapshot.descriptor)
        _require_decoded_snapshot_current(
            pending_descriptor,
            temporary_json.name,
            decoded_snapshot,
            stage="publication",
        )
        _validate_publication_databases(database, deadline, monotonic)
        _require_deadline(deadline, monotonic, "publication")
        _fsync_directory(pending, close_capability)
        _validate_publication_databases(database, deadline, monotonic)
        generation_name = f"{stem}-{uuid.uuid4().hex}"
        published = generations / generation_name
        _require_deadline(deadline, monotonic, "publication")
        _validate_publication_databases(database, deadline, monotonic)
        assert generations_info is not None
        assert pending_name is not None
        assert pending_info is not None
        _require_generation_directory_binding(
            generations,
            generations_descriptor,
            generations_info,
        )
        def acquire_rollback_anchors() -> None:
            nonlocal generations_rollback_descriptor
            nonlocal generations_rollback_anchor
            generations_rollback_descriptor = (
                _duplicate_owned_descriptor(
                    generations_rollback_descriptor_owner,
                    generations_descriptor,
                )
            )
            generations_rollback_anchor = _duplicate_owned_descriptor(
                generations_rollback_anchor_owner,
                generations_rollback_descriptor,
            )

        run_with_deferred_interrupts(acquire_rollback_anchors)
        current_pending = os.stat(
            pending_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        opened_pending = os.fstat(pending_descriptor)
        if (
            not _same_inode(current_pending, pending_info)
            or not _same_inode(opened_pending, pending_info)
            or opened_pending.st_uid != os.getuid()
            or stat.S_IMODE(opened_pending.st_mode) != 0o700
        ):
            raise OSError("pending generation binding changed")
        _probe_rename_noreplace(
            generations_descriptor,
            pending_identity_anchor,
            close_capability,
            noreplace_probe_descriptor_owner,
        )
        for _ in range(128):
            candidate = f".rollback-slot-{uuid.uuid4().hex}"
            try:
                os.mkdir(
                    candidate,
                    mode=0o700,
                    dir_fd=generations_descriptor,
                )
            except FileExistsError:
                continue
            rollback_slot_name = candidate
            break
        if rollback_slot_name is None:
            raise OSError("could not allocate rollback exchange slot")
        rollback_slot_info = os.stat(
            rollback_slot_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(rollback_slot_info.st_mode)
            or rollback_slot_info.st_uid != os.getuid()
            or stat.S_IMODE(rollback_slot_info.st_mode) != 0o700
        ):
            raise OSError("rollback exchange slot is unsafe")
        rollback_slot_descriptor = _open_owned_descriptor(
            rollback_slot_descriptor_owner,
            rollback_slot_name,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=generations_descriptor,
        )
        opened_rollback_slot = os.fstat(rollback_slot_descriptor)
        rebound_rollback_slot = os.stat(
            rollback_slot_name,
            dir_fd=generations_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(opened_rollback_slot.st_mode)
            or not _same_inode(opened_rollback_slot, rollback_slot_info)
            or not _same_inode(rebound_rollback_slot, rollback_slot_info)
            or opened_rollback_slot.st_uid != os.getuid()
            or rebound_rollback_slot.st_uid != os.getuid()
            or stat.S_IMODE(opened_rollback_slot.st_mode) != 0o700
            or stat.S_IMODE(rebound_rollback_slot.st_mode) != 0o700
        ):
            raise OSError("rollback exchange slot binding changed")
        try:
            _probe_rename_exchange(
                generations_descriptor,
                rollback_slot_name,
                rollback_slot_info,
                rollback_slot_descriptor,
                pending_identity_anchor,
                close_capability,
                exchange_probe_descriptor_owner,
            )
        except BaseException as probe_failure:
            raise _query_failed(
                "publication",
                diagnostic="rollback exchange capability probe failed",
            ) from probe_failure
        rollback_state = _RollbackExchangeState(
            published_name=generation_name,
            published_info=pending_info,
            slot_name=rollback_slot_name,
            slot_info=rollback_slot_info,
        )
        publication_state = _PublicationReplaceState(
            pending_name=pending_name,
            published_name=generation_name,
            expected_info=pending_info,
        )
        os.fsync(generations_descriptor)
        _require_deadline(deadline, monotonic, "publication")
        _validate_publication_databases(database, deadline, monotonic)
        _require_generation_directory_binding(
            generations,
            generations_descriptor,
            generations_info,
        )
        _require_decoded_snapshot_current(
            pending_descriptor,
            temporary_json.name,
            decoded_snapshot,
            stage="publication",
        )
        try:
            publication_state.attempted = True
            publication_state.rollback_required = True
            os.replace(
                pending_name,
                generation_name,
                src_dir_fd=generations_descriptor,
                dst_dir_fd=generations_descriptor,
            )
            _validate_publication_databases(database, deadline, monotonic)
            _require_generation_directory_binding(
                generations,
                generations_descriptor,
                generations_info,
            )
            _require_decoded_snapshot_current(
                pending_descriptor,
                temporary_json.name,
                decoded_snapshot,
                stage="publication",
            )
            _fsync_directory(generations_descriptor, close_capability)
            _validate_publication_databases(database, deadline, monotonic)
            _require_generation_directory_binding(
                generations,
                generations_descriptor,
                generations_info,
            )
        except BaseException as publication_failure:
            publication_state.rollback_required = True
            try:
                rollback_attempted_publication(generations_descriptor)
            except BaseException as rollback_failure:
                raise _query_failed(
                    "publication",
                    diagnostic="published generation rollback failed",
                ) from rollback_failure
            raise publication_failure
        committed = True
        publication_state.rollback_required = False
        if retain_output_binding:
            assert output_descriptor is not None
            assert close_capability is not None
            assert generation_name is not None
            assert generations_info is not None
            assert pending_info is not None
            assert decoded_output_owners
            decoded_snapshot = decoded_output_owners[0]
            _require_decoded_snapshot_current(
                pending_descriptor,
                temporary_json.name,
                decoded_snapshot,
                stage="publication",
            )
            _pin_query_output_binding(
                output_descriptor,
                generation_name,
                temporary_json.name,
                close_capability,
                source_generations_descriptor=generations_descriptor,
                expected_generations_info=generations_info,
                expected_generation_info=pending_info,
                source_decoded_descriptor=decoded_snapshot.descriptor,
                expected_decoded_info=decoded_snapshot.info,
                expected_decoded_size=decoded_snapshot.size,
                expected_decoded_sha256=decoded_snapshot.sha256,
                expected_decoded_bytes=decoded_snapshot.payload,
                owner_holder=private_output_bindings,
            )
    except AnalyzerError:
        publication_exit_failure = True
        raise
    except Exception as exc:
        publication_exit_failure = True
        raise _query_failed("publication", diagnostic="query outputs could not be published") from exc
    except BaseException:
        publication_exit_failure = True
        raise
    finally:
        housekeeping_succeeded = False
        try:
            try:
                if execution_query is not None:
                    execution_query.unlink(missing_ok=True)
            except BaseException as housekeeping_failure:
                if publication_state is not None:
                    publication_state.rollback_required = True
                try:
                    rollback_attempted_publication(generations_descriptor)
                except BaseException as rollback_failure:
                    raise _query_failed(
                        "publication",
                        diagnostic="published generation rollback failed",
                    ) from rollback_failure
                if isinstance(housekeeping_failure, Exception):
                    raise _query_failed(
                        "publication",
                        diagnostic="query housekeeping failed",
                    ) from housekeeping_failure
                raise
            housekeeping_succeeded = True
        finally:
            release_failure: BaseException | None = None
            rollback_failure: BaseException | None = None
            release_transaction_complete = False
            release_owned_state_completed = False
            def release_owned_state() -> None:
                nonlocal release_failure
                nonlocal rollback_failure
                nonlocal release_transaction_complete
                nonlocal release_owned_state_completed
                nonlocal pending_descriptor
                nonlocal pending_identity_anchor
                nonlocal generations_descriptor
                nonlocal generations_rollback_descriptor
                nonlocal generations_rollback_anchor
                nonlocal generations_cleanup_anchor
                nonlocal rollback_slot_descriptor
                try:
                    def attempt_rollback(descriptor: int) -> None:
                        nonlocal rollback_failure
                        try:
                            rollback_attempted_publication(descriptor)
                        except BaseException as exc:
                            rollback_failure = exc
                        else:
                            rollback_failure = None

                    def remember_release_failure(exc: BaseException) -> None:
                        nonlocal release_failure
                        if release_failure is None:
                            release_failure = exc

                    def remember_release_outcome(result) -> bool:
                        failed = False
                        if result.primary_error is not None:
                            remember_release_failure(result.primary_error)
                            failed = True
                        if result.transaction_error is not None:
                            remember_release_failure(
                                result.transaction_error
                            )
                            failed = True
                        if result.callback_error is not None:
                            remember_release_failure(result.callback_error)
                            failed = True
                        if result.fallback_error is not None:
                            remember_release_failure(result.fallback_error)
                            failed = True
                        return failed

                    def retire_owner_slot(
                        owner: list[int], descriptor: int
                    ) -> None:
                        if owner and owner[0] == descriptor:
                            owner[0] = -1

                    def release_descriptor(
                        descriptor: int,
                        *,
                        before_fallback: Callable[[], None] | None = None,
                    ):
                        try:
                            transaction = (
                                filesystem.DeferredCloseFdOnceOutcome()
                            )
                        except BaseException as exc:
                            remember_release_failure(exc)
                            if before_fallback is not None:
                                try:
                                    before_fallback()
                                except BaseException as callback_exc:
                                    remember_release_failure(callback_exc)
                            try:
                                os.closerange(
                                    descriptor,
                                    descriptor + 1,
                                )
                            except BaseException as fallback_exc:
                                remember_release_failure(fallback_exc)
                            return None
                        result = release_owned_descriptor_once(
                            descriptor,
                            close_capability,
                            transaction=transaction,
                            before_fallback=before_fallback,
                        )
                        remember_release_outcome(result)
                        return result

                    while noreplace_probe_descriptor_owner:
                        owned_probe_descriptor = (
                            noreplace_probe_descriptor_owner.pop()
                        )
                        if owned_probe_descriptor >= 0:
                            release_descriptor(owned_probe_descriptor)

                    while exchange_probe_descriptor_owner:
                        owned_probe_descriptor = (
                            exchange_probe_descriptor_owner.pop()
                        )
                        if owned_probe_descriptor >= 0:
                            release_descriptor(owned_probe_descriptor)

                    if generations_rollback_anchor < 0:
                        try:
                            finalize_pending_generation(
                                generations_descriptor,
                                allow_expected_removal=not committed
                            )
                        except BaseException as exc:
                            remember_release_failure(exc)

                    try:
                        if (
                            pending_cleanup_is_safe()
                            and generations_descriptor >= 0
                            and rollback_slot_name is not None
                            and rollback_slot_info is not None
                        ):
                            try:
                                current_slot = os.stat(
                                    rollback_slot_name,
                                    dir_fd=generations_descriptor,
                                    follow_symlinks=False,
                                )
                            except FileNotFoundError:
                                pass
                            else:
                                if not _same_inode(
                                    current_slot,
                                    rollback_slot_info,
                                ):
                                    raise OSError(
                                        "rollback exchange slot changed"
                                    )
                                retained_directory_descriptor = (
                                    pending_identity_anchor
                                    if pending_identity_anchor >= 0
                                    else pending_descriptor
                                )
                                if retained_directory_descriptor < 0:
                                    raise OSError(
                                        "rollback slot retained directory missing"
                                    )
                                if rollback_slot_descriptor < 0:
                                    raise OSError(
                                        "rollback slot descriptor missing"
                                    )
                                _isolate_bound_empty_directory_no_replace(
                                    generations_descriptor,
                                    rollback_slot_name,
                                    rollback_slot_info,
                                    retained_directory_descriptor,
                                    ".rollback-slot-prepublication-tombstone-",
                                    pinned_descriptor=rollback_slot_descriptor,
                                )
                    except BaseException as exc:
                        remember_release_failure(exc)
                        if publication_state is not None:
                            publication_state.rollback_required = True
                            attempt_rollback(generations_descriptor)

                    if (
                        pending_descriptor >= 0
                        and generations_rollback_anchor < 0
                    ):
                        assert close_capability is not None
                        owned_pending = pending_descriptor
                        pending_descriptor = -1
                        retire_owner_slot(
                            pending_descriptor_owner,
                            owned_pending,
                        )
                        release_descriptor(owned_pending)
                    if (
                        pending_identity_anchor >= 0
                        and generations_rollback_anchor < 0
                    ):
                        assert close_capability is not None
                        owned_identity_anchor = pending_identity_anchor
                        pending_identity_anchor = -1
                        retire_owner_slot(
                            pending_identity_anchor_owner,
                            owned_identity_anchor,
                        )
                        release_descriptor(owned_identity_anchor)
                    if generations_descriptor >= 0:
                        assert close_capability is not None

                        def rollback_before_generations_fallback() -> None:
                            if publication_state is None:
                                return
                            publication_state.rollback_required = True
                            attempt_rollback(
                                generations_rollback_descriptor
                            )

                        owned_generations = generations_descriptor
                        generations_descriptor = -1
                        retire_owner_slot(
                            generations_descriptor_owner,
                            owned_generations,
                        )
                        generations_release = release_descriptor(
                            owned_generations,
                            before_fallback=(
                                rollback_before_generations_fallback
                            ),
                        )
                        if (
                            generations_release is not None
                            and not generations_release.succeeded
                        ):
                            if (
                                publication_state is not None
                                and generations_release.explicitly_consumed
                            ):
                                publication_state.rollback_required = True
                                attempt_rollback(
                                    generations_rollback_descriptor
                                )
                    if (
                        generations_rollback_descriptor >= 0
                        and generations_rollback_anchor >= 0
                        and not private_output_bindings
                    ):
                        try:
                            generations_cleanup_anchor = (
                                _duplicate_owned_descriptor(
                                    generations_cleanup_anchor_owner,
                                    generations_rollback_descriptor,
                                )
                            )
                        except BaseException as exc:
                            remember_release_failure(exc)
                            if publication_state is not None:
                                publication_state.rollback_required = True
                                attempt_rollback(
                                    generations_rollback_anchor
                                )

                    if generations_rollback_descriptor >= 0:
                        assert close_capability is not None

                        def rollback_before_descriptor_fallback() -> None:
                            if publication_state is None:
                                return
                            publication_state.rollback_required = True
                            attempt_rollback(
                                generations_rollback_anchor
                            )

                        owned_rollback_descriptor = (
                            generations_rollback_descriptor
                        )
                        generations_rollback_descriptor = -1
                        retire_owner_slot(
                            generations_rollback_descriptor_owner,
                            owned_rollback_descriptor,
                        )
                        rollback_descriptor_release = (
                            release_descriptor(
                                owned_rollback_descriptor,
                                before_fallback=(
                                    rollback_before_descriptor_fallback
                                ),
                            )
                        )
                        if (
                            rollback_descriptor_release is not None
                            and not rollback_descriptor_release.succeeded
                        ):
                            if (
                                publication_state is not None
                                and rollback_descriptor_release.explicitly_consumed
                            ):
                                publication_state.rollback_required = True
                                attempt_rollback(
                                    generations_rollback_anchor
                                )
                finally:
                    try:
                        if generations_rollback_anchor >= 0:
                            assert close_capability is not None
                            slot_recovery_anchor = -1
                            def recover_with_anchor(anchor: int) -> None:
                                nonlocal rollback_failure
                                if (
                                    publication_state is not None
                                    and publication_state.attempted
                                    and not publication_state.resolved
                                    and (
                                        publication_state.rollback_required
                                        or release_failure is not None
                                        or not committed
                                    )
                                ):
                                    attempt_rollback(anchor)
                                if (
                                    publication_state is not None
                                    and publication_state.attempted
                                    and not publication_state.resolved
                                    and (
                                        publication_state.rollback_required
                                        or rollback_failure is not None
                                        or release_failure is not None
                                        or not committed
                                    )
                                ):
                                    try:
                                        recover_attempted_publication(anchor)
                                    except BaseException as exc:
                                        rollback_failure = exc
                                    else:
                                        rollback_failure = None

                            def unresolved_required_rollback() -> bool:
                                return (
                                    publication_state is not None
                                    and publication_state.attempted
                                    and not publication_state.resolved
                                    and (
                                        publication_state.rollback_required
                                        or rollback_failure is not None
                                        or release_failure is not None
                                        or not committed
                                    )
                                )

                            def force_with_anchor(anchor: int) -> None:
                                nonlocal rollback_failure
                                if not unresolved_required_rollback():
                                    return
                                try:
                                    force_descriptor_bound_recovery(anchor)
                                except BaseException as exc:
                                    rollback_failure = exc

                            try:
                                finalize_pending_generation(
                                    generations_rollback_anchor,
                                    allow_expected_removal=not committed
                                )
                            except BaseException as exc:
                                remember_release_failure(exc)
                                if publication_state is not None:
                                    publication_state.rollback_required = True
                            recover_with_anchor(
                                generations_rollback_anchor
                            )
                            force_with_anchor(
                                generations_rollback_anchor
                            )

                            def recover_before_owned_fallback() -> None:
                                if publication_state is None:
                                    return
                                publication_state.rollback_required = True
                                recover_with_anchor(
                                    generations_rollback_anchor
                                )
                                force_with_anchor(
                                    generations_rollback_anchor
                                )

                            if pending_descriptor >= 0:
                                owned_pending = pending_descriptor
                                pending_descriptor = -1
                                retire_owner_slot(
                                    pending_descriptor_owner,
                                    owned_pending,
                                )
                                pending_release = release_descriptor(
                                    owned_pending,
                                    before_fallback=(
                                        recover_before_owned_fallback
                                    ),
                                )
                                if (
                                    pending_release is not None
                                    and not pending_release.succeeded
                                ):
                                    if (
                                        publication_state is not None
                                        and pending_release.explicitly_consumed
                                    ):
                                        publication_state.rollback_required = True
                                        recover_with_anchor(
                                            generations_rollback_anchor
                                        )
                                        force_with_anchor(
                                            generations_rollback_anchor
                                        )
                            def rollback_before_final_fallback() -> None:
                                if publication_state is None:
                                    return
                                publication_state.rollback_required = True
                                attempt_rollback(owned_final_anchor)

                            owned_final_anchor = generations_rollback_anchor
                            generations_rollback_anchor = -1
                            retire_owner_slot(
                                generations_rollback_anchor_owner,
                                owned_final_anchor,
                            )
                            final_anchor_release = (
                                release_descriptor(
                                    owned_final_anchor,
                                    before_fallback=(
                                        rollback_before_final_fallback
                                    ),
                                )
                            )
                            if (
                                final_anchor_release is not None
                                and final_anchor_release.succeeded
                                and release_failure is None
                                and rollback_failure is None
                                and committed
                                and publication_state is not None
                                and publication_state.attempted
                                and not publication_state.resolved
                                and not publication_state.rollback_required
                            ):
                                cleanup_anchor = generations_cleanup_anchor
                                if private_output_bindings:
                                    cleanup_anchor = (
                                        private_output_bindings[0]
                                        .generations_descriptor
                                    )
                                if cleanup_anchor < 0:
                                    raise OSError(
                                        "rollback slot cleanup anchor missing"
                                    )
                                slot_recovery_anchor = cleanup_anchor
                                assert generations_info is not None
                                assert rollback_slot_name is not None
                                assert rollback_slot_info is not None
                                if rollback_slot_descriptor < 0:
                                    raise OSError(
                                        "rollback slot descriptor missing"
                                    )
                                try:
                                    _require_generation_directory_binding(
                                        generations,
                                        cleanup_anchor,
                                        generations_info,
                                    )
                                    require_published_generation_binding(
                                        cleanup_anchor,
                                    )
                                    current_slot = os.stat(
                                        rollback_slot_name,
                                        dir_fd=cleanup_anchor,
                                        follow_symlinks=False,
                                    )
                                    opened_slot = os.fstat(
                                        rollback_slot_descriptor
                                    )
                                    if (
                                        not stat.S_ISDIR(
                                            current_slot.st_mode
                                        )
                                        or not stat.S_ISDIR(
                                            opened_slot.st_mode
                                        )
                                        or not _same_inode(
                                            current_slot,
                                            rollback_slot_info,
                                        )
                                        or not _same_inode(
                                            opened_slot,
                                            rollback_slot_info,
                                        )
                                        or not _same_inode(
                                            current_slot,
                                            opened_slot,
                                        )
                                        or current_slot.st_uid != os.getuid()
                                        or opened_slot.st_uid != os.getuid()
                                        or stat.S_IMODE(
                                            current_slot.st_mode
                                        )
                                        != 0o700
                                        or stat.S_IMODE(
                                            opened_slot.st_mode
                                        )
                                        != 0o700
                                    ):
                                        raise OSError(
                                            "rollback slot binding changed"
                                        )
                                    with os.scandir(
                                        rollback_slot_descriptor
                                    ) as entries:
                                        if next(entries, None) is not None:
                                            raise OSError(
                                                "rollback slot is not empty"
                                            )
                                    generation_identity = (
                                        pending_identity_anchor
                                        if pending_identity_anchor >= 0
                                        else pending_descriptor
                                    )
                                    if generation_identity < 0:
                                        raise OSError(
                                            "published generation identity missing"
                                        )

                                    def restore_moved_substitute(
                                        candidate: str,
                                        moved: os.stat_result,
                                    ) -> None:
                                        try:
                                            renameat2_no_replace(
                                                generation_identity,
                                                candidate,
                                                cleanup_anchor,
                                                rollback_slot_name,
                                            )
                                        except BaseException as restore_failure:
                                            restored = _optional_stat_at(
                                                cleanup_anchor,
                                                rollback_slot_name,
                                            )
                                            retained = _optional_stat_at(
                                                generation_identity,
                                                candidate,
                                            )
                                            if not (
                                                restored is not None
                                                and _same_inode(
                                                    restored,
                                                    moved,
                                                )
                                                and retained is None
                                            ):
                                                raise OSError(
                                                    "rollback slot substitute could not be restored"
                                                ) from restore_failure
                                        restored = os.stat(
                                            rollback_slot_name,
                                            dir_fd=cleanup_anchor,
                                            follow_symlinks=False,
                                        )
                                        if not _same_inode(restored, moved):
                                            raise OSError(
                                                "rollback slot substitute restore changed"
                                            )
                                        if _optional_stat_at(
                                            generation_identity,
                                            candidate,
                                        ) is not None:
                                            raise OSError(
                                                "rollback slot substitute remained isolated"
                                            )
                                        os.fsync(generation_identity)
                                        os.fsync(cleanup_anchor)

                                    tombstone_name: str | None = None
                                    for _ in range(128):
                                        candidate = (
                                            ".rollback-slot-tombstone-"
                                            f"{uuid.uuid4().hex}"
                                        )
                                        isolation_failure: (
                                            BaseException | None
                                        ) = None
                                        try:
                                            renameat2_no_replace(
                                                cleanup_anchor,
                                                rollback_slot_name,
                                                generation_identity,
                                                candidate,
                                            )
                                        except FileExistsError as exc:
                                            source = _optional_stat_at(
                                                cleanup_anchor,
                                                rollback_slot_name,
                                            )
                                            retained = _optional_stat_at(
                                                generation_identity,
                                                candidate,
                                            )
                                            if (
                                                source is not None
                                                and _same_inode(
                                                    source,
                                                    rollback_slot_info,
                                                )
                                                and retained is not None
                                                and not _same_inode(
                                                    retained,
                                                    rollback_slot_info,
                                                )
                                            ):
                                                continue
                                            isolation_failure = exc
                                        except BaseException as exc:
                                            isolation_failure = exc

                                        source = _optional_stat_at(
                                            cleanup_anchor,
                                            rollback_slot_name,
                                        )
                                        retained = _optional_stat_at(
                                            generation_identity,
                                            candidate,
                                        )
                                        if (
                                            retained is not None
                                            and _same_inode(
                                                retained,
                                                rollback_slot_info,
                                            )
                                        ):
                                            publication_state.slot_retired = (
                                                True
                                            )
                                            publication_state.slot_tombstone_name = (
                                                candidate
                                            )
                                            if source is not None:
                                                raise OSError(
                                                    "rollback slot name was recreated"
                                                ) from isolation_failure
                                            tombstone_name = candidate
                                            break
                                        if retained is not None:
                                            publication_state.slot_retired = (
                                                True
                                            )
                                            if source is None:
                                                restore_moved_substitute(
                                                    candidate,
                                                    retained,
                                                )
                                            raise OSError(
                                                "rollback slot source changed during isolation"
                                            ) from isolation_failure
                                        if (
                                            source is not None
                                            and _same_inode(
                                                source,
                                                rollback_slot_info,
                                            )
                                        ):
                                            if isolation_failure is None:
                                                raise OSError(
                                                    "rollback slot isolation did not move source"
                                                )
                                            raise isolation_failure
                                        publication_state.slot_retired = True
                                        raise OSError(
                                            "rollback slot namespace became ambiguous"
                                        ) from isolation_failure
                                    if tombstone_name is None:
                                        raise OSError(
                                            "rollback slot tombstone allocation failed"
                                        )
                                    os.fsync(generation_identity)
                                    os.fsync(cleanup_anchor)
                                    retained_slot = os.fstat(
                                        rollback_slot_descriptor
                                    )
                                    named_tombstone = os.stat(
                                        tombstone_name,
                                        dir_fd=generation_identity,
                                        follow_symlinks=False,
                                    )
                                    if (
                                        not _same_inode(
                                            retained_slot,
                                            rollback_slot_info,
                                        )
                                        or not _same_inode(
                                            named_tombstone,
                                            rollback_slot_info,
                                        )
                                        or not stat.S_ISDIR(
                                            retained_slot.st_mode
                                        )
                                        or not stat.S_ISDIR(
                                            named_tombstone.st_mode
                                        )
                                        or retained_slot.st_uid != os.getuid()
                                        or named_tombstone.st_uid != os.getuid()
                                        or stat.S_IMODE(
                                            retained_slot.st_mode
                                        )
                                        != 0o700
                                        or stat.S_IMODE(
                                            named_tombstone.st_mode
                                        )
                                        != 0o700
                                    ):
                                        raise OSError(
                                            "rollback slot tombstone binding changed"
                                        )
                                    with os.scandir(
                                        rollback_slot_descriptor
                                    ) as entries:
                                        if next(entries, None) is not None:
                                            raise OSError(
                                                "rollback slot tombstone is not empty"
                                            )
                                    _require_generation_directory_binding(
                                        generations,
                                        cleanup_anchor,
                                        generations_info,
                                    )
                                    require_published_generation_binding(
                                        cleanup_anchor,
                                    )
                                    _require_name_absent(
                                        cleanup_anchor,
                                        rollback_slot_name,
                                    )
                                except BaseException as exc:
                                    remember_release_failure(exc)
                                    publication_state.rollback_required = True
                                    recover_with_anchor(cleanup_anchor)
                                    force_with_anchor(cleanup_anchor)

                            if rollback_slot_descriptor >= 0:
                                owned_slot_descriptor = (
                                    rollback_slot_descriptor
                                )
                                rollback_slot_descriptor = -1
                                retire_owner_slot(
                                    rollback_slot_descriptor_owner,
                                    owned_slot_descriptor,
                                )

                                def recover_before_slot_fallback() -> None:
                                    if (
                                        publication_state is None
                                        or slot_recovery_anchor < 0
                                    ):
                                        return
                                    publication_state.rollback_required = True
                                    recover_with_anchor(
                                        slot_recovery_anchor
                                    )
                                    force_with_anchor(
                                        slot_recovery_anchor
                                    )

                                slot_release = release_descriptor(
                                    owned_slot_descriptor,
                                    before_fallback=(
                                        recover_before_slot_fallback
                                    ),
                                )
                                if (
                                    publication_state is not None
                                    and publication_state.slot_retired
                                    and not publication_state.resolved
                                    and slot_recovery_anchor >= 0
                                    and (
                                        slot_release is None
                                        or not slot_release.succeeded
                                    )
                                ):
                                    publication_state.rollback_required = True
                                    recover_with_anchor(
                                        slot_recovery_anchor
                                    )
                                    force_with_anchor(
                                        slot_recovery_anchor
                                    )

                            if generations_cleanup_anchor >= 0:
                                cleanup_anchor = generations_cleanup_anchor
                                generations_cleanup_anchor = -1
                                retire_owner_slot(
                                    generations_cleanup_anchor_owner,
                                    cleanup_anchor,
                                )

                                def recover_before_cleanup_fallback() -> None:
                                    if publication_state is not None:
                                        publication_state.rollback_required = (
                                            True
                                        )
                                    recover_with_anchor(cleanup_anchor)
                                    force_with_anchor(cleanup_anchor)

                                release_descriptor(
                                    cleanup_anchor,
                                    before_fallback=(
                                        recover_before_cleanup_fallback
                                    ),
                                )

                            if pending_identity_anchor >= 0:
                                owned_identity_anchor = (
                                    pending_identity_anchor
                                )
                                pending_identity_anchor = -1
                                retire_owner_slot(
                                    pending_identity_anchor_owner,
                                    owned_identity_anchor,
                                )
                                release_descriptor(
                                    owned_identity_anchor,
                                )
                        release_transaction_complete = True
                    finally:
                        for assigned, owner, label in (
                            (
                                -1,
                                noreplace_probe_descriptor_owner,
                                "no-replace probe",
                            ),
                            (
                                -1,
                                exchange_probe_descriptor_owner,
                                "exchange probe",
                            ),
                            (
                                generations_descriptor,
                                generations_descriptor_owner,
                                "generation directory",
                            ),
                            (
                                generations_rollback_anchor,
                                generations_rollback_anchor_owner,
                                "final rollback anchor",
                            ),
                            (
                                generations_rollback_descriptor,
                                generations_rollback_descriptor_owner,
                                "rollback directory",
                            ),
                            (
                                generations_cleanup_anchor,
                                generations_cleanup_anchor_owner,
                                "rollback slot cleanup anchor",
                            ),
                            (
                                rollback_slot_descriptor,
                                rollback_slot_descriptor_owner,
                                "rollback slot",
                            ),
                            (
                                pending_identity_anchor,
                                pending_identity_anchor_owner,
                                "pending identity anchor",
                            ),
                            (
                                pending_descriptor,
                                pending_descriptor_owner,
                                "pending generation",
                            ),
                        ):
                            if assigned >= 0 or not owner or owner[0] < 0:
                                continue
                            assert close_capability is not None
                            unassigned_descriptor = owner[0]
                            owner[0] = -1
                            if not _release_query_output_descriptor(
                                unassigned_descriptor,
                                close_capability,
                            ) and release_failure is None:
                                release_failure = OSError(
                                    f"unassigned {label} descriptor release failed"
                                )
                        private_binding_owns_decoded = bool(
                            private_output_bindings
                            and decoded_output_owners
                            and private_output_bindings[0].decoded_descriptor
                            == decoded_output_owners[0].descriptor
                        )
                        if (
                            private_output_bindings
                            and (
                                publication_exit_failure
                                or not housekeeping_succeeded
                                or not release_transaction_complete
                                or rollback_failure is not None
                                or release_failure is not None
                                or not committed
                            )
                        ):
                            private_binding = private_output_bindings.pop()
                            if not _release_owned_query_output_binding(
                                private_binding
                            ) and release_failure is None:
                                release_failure = OSError(
                                    "query output binding release failed"
                                )
                        if decoded_output_owners:
                            decoded_snapshot = decoded_output_owners.pop()
                            if (
                                not private_binding_owns_decoded
                                and not _release_query_output_descriptor(
                                    decoded_snapshot.descriptor,
                                    close_capability,
                                )
                                and release_failure is None
                            ):
                                release_failure = OSError(
                                    "decoded output descriptor release failed"
                                )
                        if binding is not None:
                            binding.lock.release()
                        release_owned_state_completed = True

            def remember_emergency_release_failure(
                exc: BaseException,
            ) -> None:
                nonlocal release_failure
                if release_failure is None:
                    release_failure = exc

            def emergency_close_descriptor(descriptor: int) -> None:
                if descriptor < 0:
                    return
                try:
                    os.closerange(descriptor, descriptor + 1)
                except BaseException as exc:
                    remember_emergency_release_failure(exc)

            def emergency_drain_descriptor_owner(
                owner: list[int],
            ) -> None:
                while owner:
                    emergency_close_descriptor(owner.pop())

            def emergency_drain_probe_descriptor_owners() -> None:
                try:
                    emergency_drain_descriptor_owner(
                        noreplace_probe_descriptor_owner
                    )
                finally:
                    emergency_drain_descriptor_owner(
                        exchange_probe_descriptor_owner
                    )

            def emergency_drain_decoded_owners() -> None:
                while decoded_output_owners:
                    decoded_owner = decoded_output_owners.pop()
                    for private_binding in private_output_bindings:
                        if (
                            private_binding.decoded_descriptor
                            == decoded_owner.descriptor
                        ):
                            private_binding.decoded_descriptor = -1
                    emergency_close_descriptor(decoded_owner.descriptor)

            def emergency_drain_private_bindings() -> None:
                while private_output_bindings:
                    private_binding = private_output_bindings.pop()
                    decoded_descriptor = private_binding.decoded_descriptor
                    private_binding.decoded_descriptor = -1
                    emergency_close_descriptor(decoded_descriptor)
                    generation_descriptor = (
                        private_binding.generation_descriptor
                    )
                    private_binding.generation_descriptor = -1
                    emergency_close_descriptor(generation_descriptor)
                    bound_generations_descriptor = (
                        private_binding.generations_descriptor
                    )
                    private_binding.generations_descriptor = -1
                    emergency_close_descriptor(
                        bound_generations_descriptor
                    )

            def emergency_recover_publication() -> None:
                nonlocal rollback_failure
                state = publication_state
                if state is None or not state.attempted or state.resolved:
                    return
                state.rollback_required = True
                recovery_descriptor = generations_rollback_anchor
                if recovery_descriptor < 0:
                    recovery_descriptor = generations_rollback_descriptor
                if recovery_descriptor < 0:
                    recovery_descriptor = generations_descriptor
                if recovery_descriptor < 0:
                    rollback_failure = OSError(
                        "publication recovery descriptor is unavailable"
                    )
                    return
                recovery_error: BaseException | None = None
                try:
                    rollback_attempted_publication(recovery_descriptor)
                except BaseException as exc:
                    recovery_error = exc
                if not state.resolved:
                    try:
                        recover_attempted_publication(recovery_descriptor)
                    except BaseException as exc:
                        recovery_error = exc
                if not state.resolved:
                    try:
                        force_descriptor_bound_recovery(
                            recovery_descriptor
                        )
                    except BaseException as exc:
                        recovery_error = exc
                rollback_failure = (
                    None if state.resolved else recovery_error
                )
                if rollback_failure is None and not state.resolved:
                    rollback_failure = OSError(
                        "published generation emergency recovery failed"
                    )

            def emergency_drain_after_entry_escape() -> None:
                try:
                    emergency_drain_probe_descriptor_owners()
                finally:
                    try:
                        emergency_drain_decoded_owners()
                    finally:
                        try:
                            emergency_drain_private_bindings()
                        finally:
                            try:
                                emergency_drain_descriptor_owner(
                                    generations_rollback_anchor_owner
                                )
                            finally:
                                try:
                                    emergency_drain_descriptor_owner(
                                        generations_rollback_descriptor_owner
                                    )
                                finally:
                                    try:
                                        emergency_drain_descriptor_owner(
                                            generations_cleanup_anchor_owner
                                        )
                                    finally:
                                        try:
                                            emergency_drain_descriptor_owner(
                                                rollback_slot_descriptor_owner
                                            )
                                        finally:
                                            try:
                                                emergency_drain_descriptor_owner(
                                                    pending_identity_anchor_owner
                                                )
                                            finally:
                                                try:
                                                    emergency_drain_descriptor_owner(
                                                        pending_descriptor_owner
                                                    )
                                                finally:
                                                    try:
                                                        emergency_drain_descriptor_owner(
                                                            generations_descriptor_owner
                                                        )
                                                    finally:
                                                        if (
                                                            binding is not None
                                                            and binding.lock._is_owned()
                                                        ):
                                                            try:
                                                                binding.lock.release()
                                                            except BaseException as exc:
                                                                remember_emergency_release_failure(
                                                                    exc
                                                                )

            try:
                run_with_deferred_interrupts(release_owned_state)
            except BaseException as exc:
                if not (
                    release_owned_state_completed
                    and release_transaction_complete
                    and release_failure is None
                    and rollback_failure is None
                    and housekeeping_succeeded
                    and committed
                ):
                    if release_failure is None:
                        release_failure = exc
                    try:
                        try:
                            emergency_recover_publication()
                        finally:
                            emergency_drain_after_entry_escape()
                    except BaseException as emergency_exc:
                        remember_emergency_release_failure(emergency_exc)
            if rollback_failure is not None:
                raise _query_failed(
                    "publication",
                    diagnostic="published generation rollback failed",
                ) from rollback_failure
            if release_failure is not None:
                raise _query_failed(
                    "publication",
                    diagnostic="generation directory release failed",
                ) from release_failure

    private_output_binding = (
        private_output_bindings[0] if private_output_bindings else None
    )
    try:
        _require_output_descriptor_binding(
            output_descriptor,
            output_descriptor_info,
            stage="publication",
        )
        assert published is not None
        final_query = published / snapshot_query.name
        final_bqrs = published / temporary_bqrs.name
        final_json = published / temporary_json.name
        result = QueryResult(
            query_name=query_name,
            query_path=final_query,
            bqrs_path=final_bqrs,
            decoded_path=final_json,
            query_sha256=query_sha256,
            bqrs_sha256=bqrs_sha256,
            _output_binding=private_output_binding,
        )
        if result_owner_callback is not None:
            result_owner_callback(result)
        return result
    except BaseException:
        if (
            private_output_binding is not None
            and not private_output_binding.attached
        ):
            _release_owned_query_output_binding(private_output_binding)
        raise
