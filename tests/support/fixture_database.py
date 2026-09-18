"""Reusable real Java fixture CodeQL databases for opt-in tests.

Every build consumes a helper-owned immutable source snapshot. The original
fixture checkout is read only while capturing bounded bytes and is never the
CodeQL or javac working directory.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import fcntl
import hashlib
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import tempfile
from typing import Iterator, Protocol

from dosweb.codeql.database import DatabaseInfo, validate_database
from dosweb.filesystem import (
    CloseRangeCapability,
    DeferredCloseFdOnceOutcome,
    open_owned_descriptor,
    release_owned_descriptor_once,
    renameat2_no_replace,
    require_close_fd_once,
    run_with_deferred_interrupts,
)


_CODEQL = shutil.which("codeql") or "/usr/bin/codeql"
_JAVAC = shutil.which("javac") or "/usr/bin/javac"
_CACHE_ROOT = Path(tempfile.gettempdir()) / "dosweb-fixture-codeql"
_MAX_JAVA_FILES = 4096
_MAX_JAVA_FILE_BYTES = 4 * 1024 * 1024
_MAX_JAVA_SOURCE_BYTES = 64 * 1024 * 1024
_MAX_TREE_ENTRIES = 65536
_MAX_RELATIVE_PATH_BYTES = 4096
_MAX_PATH_PARTS = 64
_MAX_PATH_COMPONENT_BYTES = 255
_MAX_RETAINED_CLEANUP_TOMBSTONES = 64
_MAX_RETAINED_CLEANUP_BYTES = 1024 * 1024 * 1024
_MAX_CACHE_ROOT_ENTRIES = 4096
_MAX_DIGEST_CANDIDATES = 8
_STABLE_CACHE_LEAF_PATTERN = (
    r"[0-9a-f]{64}\.(?:db|sources)-[0-9a-f]{32}"
)
_CACHE_LEAF_PATTERN = (
    rf"(?:{_STABLE_CACHE_LEAF_PATTERN}|"
    r"\.[0-9a-f]{64}\.classes\.tmp-[A-Za-z0-9_-]+)"
)
_CACHE_NAME = re.compile(rf"^{_CACHE_LEAF_PATTERN}$")
_STABLE_SOURCE_CACHE_NAME = re.compile(
    r"^(?P<digest>[0-9a-f]{64})\.sources-(?P<nonce>[0-9a-f]{32})$"
)
_STABLE_DATABASE_CACHE_NAME = re.compile(
    r"^(?P<digest>[0-9a-f]{64})\.db-(?P<nonce>[0-9a-f]{32})$"
)
_RETAINED_CACHE_NAME = re.compile(
    rf"^\.(?P<legal>{_CACHE_LEAF_PATTERN})\.retained-"
    r"(?P<device>[0-9a-f]+)-(?P<inode>[0-9a-f]+)-"
    r"(?P<nonce>[0-9a-f]{32})$"
)


class _Digest(Protocol):
    def update(self, value: bytes) -> None: ...


@dataclass(frozen=True)
class _SourceFile:
    relative: str
    data: bytes
    identity: tuple[int, ...]


@dataclass(frozen=True)
class _SourceSnapshot:
    files: tuple[_SourceFile, ...]
    digest: str


@dataclass(frozen=True)
class _SnapshotTreeState:
    root_identity: tuple[int, ...]
    directory_identities: tuple[tuple[str, tuple[int, ...]], ...]
    file_identities: tuple[tuple[str, tuple[int, ...]], ...]


@dataclass(frozen=True)
class _PinnedClassesDirectory:
    path: Path
    cache_root: Path
    cache_root_descriptor: int
    cache_root_identity: os.stat_result
    descriptor: int
    expected_identity: os.stat_result
    close_capability: CloseRangeCapability
    cache_root_owner: list[int]
    cache_root_release: DeferredCloseFdOnceOutcome
    descriptor_owner: list[int]
    descriptor_release: DeferredCloseFdOnceOutcome


def _fixture_descriptor_release_consumed(
    transaction: DeferredCloseFdOnceOutcome,
) -> bool:
    return transaction.explicitly_consumed or transaction.fallback_attempted


def _release_fixture_descriptor_owner_must_reach(
    owner: list[int],
    close_capability: CloseRangeCapability,
    transaction: DeferredCloseFdOnceOutcome,
) -> None:
    if not owner:
        return
    if len(owner) != 1:
        raise OSError("fixture descriptor owner is malformed")
    descriptor = owner[0]
    if descriptor < 0:
        owner.pop()
        return
    if not _fixture_descriptor_release_consumed(transaction):
        release_result = release_owned_descriptor_once(
            descriptor,
            close_capability,
            transaction=transaction,
        )
        if release_result is not transaction:
            raise OSError("fixture descriptor release transaction changed")
    consumed = _fixture_descriptor_release_consumed(transaction)
    if consumed:
        def clear_owner() -> None:
            if len(owner) != 1 or owner[0] != descriptor:
                raise OSError(
                    "fixture descriptor ownership changed before release"
                )
            owner.pop()

        run_with_deferred_interrupts(clear_owner)
    failures = transaction.failures
    if failures:
        raise failures[0]
    if not consumed:
        raise OSError("fixture descriptor release did not consume ownership")


def _digest_field(digest: _Digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _tool_identity(tool: str) -> bytes:
    path = Path(tool).resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise AssertionError(f"fixture tool is not a regular file: {path}")
    return (
        f"{path}\0{info.st_dev}\0{info.st_ino}\0{info.st_size}\0"
        f"{info.st_mtime_ns}"
    ).encode("utf-8")


def _stable_file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IMODE(info.st_mode),
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _checked_relative(parts: tuple[str, ...]) -> str:
    if not parts or len(parts) > _MAX_PATH_PARTS:
        raise AssertionError("fixture Java source path exceeds the part bound")
    encoded_parts = tuple(os.fsencode(part) for part in parts)
    if any(
        not part
        or part in {b".", b".."}
        or len(part) > _MAX_PATH_COMPONENT_BYTES
        for part in encoded_parts
    ):
        raise AssertionError("fixture Java source has an invalid path component")
    relative = "/".join(parts)
    if len(os.fsencode(relative)) > _MAX_RELATIVE_PATH_BYTES:
        raise AssertionError("fixture Java source path exceeds the byte bound")
    return relative


def _bounded_source_bytes(
    directory_fd: int,
    name: str,
    relative: str,
    discovered: os.stat_result,
) -> tuple[bytes, tuple[int, ...]]:
    descriptor = os.open(
        name,
        os.O_RDONLY
        | os.O_NONBLOCK
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=directory_fd,
    )
    try:
        before = os.fstat(descriptor)
        if _stable_file_identity(before) != _stable_file_identity(discovered):
            raise AssertionError(
                f"fixture Java source changed before reading: {relative}"
            )
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_JAVA_FILE_BYTES:
            raise AssertionError(f"fixture Java source is not bounded: {relative}")
        data = bytearray()
        while len(data) <= _MAX_JAVA_FILE_BYTES:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, _MAX_JAVA_FILE_BYTES + 1 - len(data)),
            )
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = _stable_file_identity(before)
    if (
        len(data) != before.st_size
        or len(data) > _MAX_JAVA_FILE_BYTES
        or _stable_file_identity(after) != identity
    ):
        raise AssertionError(f"fixture Java source changed while reading: {relative}")
    return bytes(data), identity


def _bounded_java_sources(source_root: Path) -> _SourceSnapshot:
    root_descriptor = os.open(
        source_root,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    java_files: list[_SourceFile] = []
    total_source_bytes = 0
    visited_entries = 0
    root_before = os.fstat(root_descriptor)

    def visit(directory_fd: int, parts: tuple[str, ...]) -> None:
        nonlocal total_source_bytes, visited_entries
        bounded_entries: list[os.DirEntry[str]] = []
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                visited_entries += 1
                if visited_entries > _MAX_TREE_ENTRIES:
                    raise AssertionError(
                        f"fixture exceeds {_MAX_TREE_ENTRIES} filesystem entries: {source_root}"
                    )
                bounded_entries.append(entry)
        bounded_entries.sort(key=lambda item: os.fsencode(item.name))
        for entry in bounded_entries:
            relative_parts = (*parts, entry.name)
            relative = _checked_relative(relative_parts)
            discovered = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(discovered.st_mode):
                continue
            if stat.S_ISDIR(discovered.st_mode):
                child = os.open(
                    entry.name,
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    child_before = os.fstat(child)
                    if _stable_file_identity(child_before) != _stable_file_identity(
                        discovered
                    ):
                        raise AssertionError(
                            f"fixture source directory changed before reading: {relative}"
                        )
                    visit(child, relative_parts)
                    if _stable_file_identity(os.fstat(child)) != _stable_file_identity(
                        child_before
                    ):
                        raise AssertionError(
                            f"fixture source directory changed while reading: {relative}"
                        )
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(discovered.st_mode) or not entry.name.endswith(".java"):
                continue
            if len(java_files) >= _MAX_JAVA_FILES:
                raise AssertionError(
                    f"fixture exceeds {_MAX_JAVA_FILES} Java sources: {source_root}"
                )
            data, identity = _bounded_source_bytes(
                directory_fd, entry.name, relative, discovered
            )
            total_source_bytes += len(data)
            if total_source_bytes > _MAX_JAVA_SOURCE_BYTES:
                raise AssertionError(
                    f"fixture exceeds {_MAX_JAVA_SOURCE_BYTES} source bytes: {source_root}"
                )
            java_files.append(_SourceFile(relative, data, identity))

    try:
        if not stat.S_ISDIR(root_before.st_mode):
            raise AssertionError(f"fixture source root is not a directory: {source_root}")
        visit(root_descriptor, ())
        root_after = os.fstat(root_descriptor)
    finally:
        os.close(root_descriptor)
    if _stable_file_identity(root_after) != _stable_file_identity(root_before):
        raise AssertionError(
            f"fixture source root changed while reading: {source_root}"
        )
    java_files.sort(key=lambda item: os.fsencode(item.relative))
    if not java_files:
        raise AssertionError(f"fixture has no Java sources: {source_root}")
    digest = hashlib.sha256()
    _digest_field(
        digest,
        b"dosweb-fixture-codeql-cache-v5-stable-unique-snapshot-and-database",
    )
    _digest_field(digest, os.fsencode(source_root))
    _digest_field(
        digest,
        "\0".join(str(value) for value in _stable_file_identity(root_before)).encode(
            "ascii"
        ),
    )
    _digest_field(digest, _tool_identity(_CODEQL))
    _digest_field(digest, _tool_identity(_JAVAC))
    for source in java_files:
        _digest_field(digest, source.relative.encode("utf-8", errors="surrogateescape"))
        _digest_field(
            digest,
            "\0".join(str(value) for value in source.identity).encode("ascii"),
        )
        _digest_field(digest, source.data)
    return _SourceSnapshot(tuple(java_files), digest.hexdigest())


def _prepare_cache_root(cache_root: Path) -> Path:
    lexical_root = Path(os.path.abspath(os.fspath(cache_root)))
    parent = lexical_root.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_discovered = parent.lstat()
    if stat.S_ISLNK(parent_discovered.st_mode) or not stat.S_ISDIR(
        parent_discovered.st_mode
    ):
        raise AssertionError("fixture cache root parent is not a directory")

    parent_descriptor: int | None = None
    root_descriptor: int | None = None

    def same_node(left: os.stat_result, right: os.stat_result) -> bool:
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

    try:
        try:
            parent_descriptor = os.open(
                parent,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
        except OSError as exc:
            raise AssertionError(
                "fixture cache root parent changed before pinning"
            ) from exc
        parent_opened = os.fstat(parent_descriptor)
        if (
            not same_node(parent_opened, parent_discovered)
            or not stat.S_ISDIR(parent_opened.st_mode)
        ):
            raise AssertionError("fixture cache root parent changed before pinning")

        try:
            os.mkdir(lexical_root.name, 0o700, dir_fd=parent_descriptor)
        except FileExistsError:
            pass
        try:
            root_discovered = os.stat(
                lexical_root.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            root_descriptor = os.open(
                lexical_root.name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise AssertionError(
                "fixture cache root changed before pinning"
            ) from exc
        root_opened = os.fstat(root_descriptor)
        if (
            not same_node(root_opened, root_discovered)
            or not stat.S_ISDIR(root_opened.st_mode)
            or root_opened.st_uid != os.getuid()
            or root_opened.st_nlink < 1
        ):
            raise AssertionError("fixture cache root changed before pinning")

        os.fchmod(root_descriptor, 0o700)
        root_after = os.fstat(root_descriptor)
        named_after = os.stat(
            lexical_root.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        lexical_after = lexical_root.lstat()
        parent_after = parent.lstat()
        if (
            not same_node(root_after, root_opened)
            or not same_node(named_after, root_opened)
            or not same_node(lexical_after, root_opened)
            or not same_node(parent_after, parent_opened)
            or not stat.S_ISDIR(root_after.st_mode)
            or root_after.st_uid != os.getuid()
            or root_after.st_nlink < 1
            or stat.S_IMODE(root_after.st_mode) != 0o700
            or stat.S_IMODE(named_after.st_mode) != 0o700
            or stat.S_IMODE(lexical_after.st_mode) != 0o700
        ):
            raise AssertionError("fixture cache root changed while pinning")
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    return lexical_root


def _bounded_digest_candidate_paths(
    cache_root: Path,
    digest: str,
    *,
    kind: str,
) -> tuple[Path, ...]:
    if kind == "sources":
        pattern = _STABLE_SOURCE_CACHE_NAME
        label = "source snapshot"
    elif kind == "db":
        pattern = _STABLE_DATABASE_CACHE_NAME
        label = "database"
    else:
        raise AssertionError("fixture cache candidate kind is invalid")
    prefix = f"{digest}.{kind}-"
    lexical_root = cache_root.lstat()
    cache_root_descriptor = os.open(
        cache_root,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    candidates: list[Path] = []
    try:
        opened_root = os.fstat(cache_root_descriptor)
        if (
            not _same_cleanup_binding(opened_root, lexical_root)
            or not stat.S_ISDIR(opened_root.st_mode)
            or opened_root.st_uid != os.getuid()
            or stat.S_IMODE(opened_root.st_mode) != 0o700
        ):
            raise AssertionError("fixture cache root changed before candidate scan")
        scanned_entries = 0
        with os.scandir(cache_root_descriptor) as entries:
            for entry in entries:
                scanned_entries += 1
                if scanned_entries > _MAX_CACHE_ROOT_ENTRIES:
                    raise AssertionError(
                        "fixture cache candidate scan entry bound exceeded"
                    )
                if not entry.name.startswith(prefix):
                    continue
                match = pattern.fullmatch(entry.name)
                if match is None or match.group("digest") != digest:
                    raise AssertionError(
                        f"fixture {label} candidate name is invalid"
                    )
                candidates.append(cache_root / entry.name)
                if len(candidates) > _MAX_DIGEST_CANDIDATES:
                    raise AssertionError(
                        f"fixture {label} candidate count bound exceeded"
                    )
        after_root = os.fstat(cache_root_descriptor)
        lexical_after = cache_root.lstat()
        if (
            _stable_file_identity(after_root) != _stable_file_identity(opened_root)
            or not _same_cleanup_binding(lexical_after, opened_root)
        ):
            raise AssertionError("fixture cache root changed during candidate scan")
    finally:
        os.close(cache_root_descriptor)
    return tuple(sorted(candidates, key=lambda item: os.fsencode(item.name)))


def _create_stable_cache_directory(
    cache_root: Path,
    digest: str,
    *,
    kind: str,
) -> Path:
    for _attempt in range(128):
        candidate = cache_root / f"{digest}.{kind}-{secrets.token_hex(16)}"
        if _CACHE_NAME.fullmatch(candidate.name) is None:
            raise AssertionError("fixture stable cache candidate name is invalid")
        try:
            candidate.mkdir(mode=0o700)
        except FileExistsError:
            continue
        return candidate
    raise AssertionError("fixture stable cache candidate namespace exhausted")


def _new_uncreated_stable_cache_path(
    cache_root: Path,
    digest: str,
    *,
    kind: str,
) -> Path:
    for _attempt in range(128):
        candidate = cache_root / f"{digest}.{kind}-{secrets.token_hex(16)}"
        if _CACHE_NAME.fullmatch(candidate.name) is None:
            raise AssertionError("fixture stable cache candidate name is invalid")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise AssertionError("fixture stable cache candidate namespace exhausted")


@contextmanager
def _digest_lock(cache_root: Path, digest: str) -> Iterator[None]:
    lock_path = cache_root / f"{digest}.lock"
    cache_root_before = cache_root.lstat()
    cache_root_descriptor = os.open(
        cache_root,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    descriptor: int | None = None
    locked = False
    try:
        opened_root = os.fstat(cache_root_descriptor)
        if (
            not _same_cleanup_binding(opened_root, cache_root_before)
            or not stat.S_ISDIR(opened_root.st_mode)
            or opened_root.st_uid != os.getuid()
            or stat.S_IMODE(opened_root.st_mode) != 0o700
        ):
            raise AssertionError("fixture cache root changed before digest lock")
        flags = (
            os.O_RDWR
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        created = False
        try:
            descriptor = os.open(
                lock_path.name,
                flags | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=cache_root_descriptor,
            )
            created = True
        except FileExistsError:
            descriptor = os.open(
                lock_path.name,
                flags,
                dir_fd=cache_root_descriptor,
            )
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise AssertionError(f"fixture cache lock is not private: {lock_path}")
        if created:
            os.fchmod(descriptor, 0o600)
            info = os.fstat(descriptor)
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise AssertionError(f"fixture cache lock is not private: {lock_path}")
        named_before = os.stat(
            lock_path.name,
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
        if not _same_cleanup_binding(named_before, info):
            raise AssertionError("fixture cache lock changed before flock")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        locked_info = os.fstat(descriptor)
        named_after = os.stat(
            lock_path.name,
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
        if (
            not _same_cleanup_binding(locked_info, info)
            or not _same_cleanup_binding(named_after, info)
            or not stat.S_ISREG(locked_info.st_mode)
            or locked_info.st_uid != os.getuid()
            or locked_info.st_nlink != 1
            or stat.S_IMODE(locked_info.st_mode) != 0o600
        ):
            raise AssertionError("fixture cache lock changed after flock")
        yield
    finally:
        try:
            if descriptor is not None and locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            try:
                if descriptor is not None:
                    os.close(descriptor)
            finally:
                os.close(cache_root_descriptor)


def _remove_helper_owned_cache_path(path: Path, cache_root: Path) -> None:
    if path.parent != cache_root or _CACHE_NAME.fullmatch(path.name) is None:
        raise AssertionError(f"refusing to clean non-fixture cache path: {path}")
    cache_root_before = cache_root.lstat()
    cache_root_descriptor = os.open(
        cache_root,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened_cache_root = os.fstat(cache_root_descriptor)
        if (
            not _same_cleanup_binding(opened_cache_root, cache_root_before)
            or not stat.S_ISDIR(opened_cache_root.st_mode)
            or opened_cache_root.st_uid != os.getuid()
            or stat.S_IMODE(opened_cache_root.st_mode) != 0o700
        ):
            raise AssertionError("fixture cache root changed before cleanup")
        with _cleanup_retention_lock(cache_root_descriptor):
            _retain_helper_owned_cache_path(
                path,
                cache_root_descriptor,
            )
    finally:
        try:
            current_cache_root = os.fstat(cache_root_descriptor)
        finally:
            os.close(cache_root_descriptor)
        if not _same_cleanup_binding(current_cache_root, cache_root_before):
            raise AssertionError("fixture cache root changed during cleanup")


@contextmanager
def _cleanup_retention_lock(
    cache_root_descriptor: int,
) -> Iterator[None]:
    descriptor = os.open(
        ".cleanup-retention.lock",
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=cache_root_descriptor,
    )
    try:
        info = os.fstat(descriptor)
        named = os.stat(
            ".cleanup-retention.lock",
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or _stable_file_identity(named) != _stable_file_identity(info)
        ):
            raise AssertionError(
                "fixture cleanup retention lock is not private"
            )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = os.stat(
            ".cleanup-retention.lock",
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
        if _stable_file_identity(locked) != _stable_file_identity(info):
            raise AssertionError(
                "fixture cleanup retention lock binding changed"
            )
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _retain_helper_owned_cache_path(
    path: Path,
    cache_root_descriptor: int,
    *,
    expected_root: os.stat_result | None = None,
) -> None:
    retained_count, _retained_bytes = _retained_cleanup_usage(
        cache_root_descriptor
    )
    if retained_count >= _MAX_RETAINED_CLEANUP_TOMBSTONES:
        raise AssertionError("fixture cleanup retention count bound reached")
    try:
        info = os.stat(
            path.name,
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if expected_root is not None and not _same_cleanup_binding(
        info,
        expected_root,
    ):
        raise AssertionError(
            "fixture cache path changed before captured-identity cleanup"
        )
    if not stat.S_ISDIR(info.st_mode):
        raise AssertionError(
            "refusing to retain non-directory fixture cache path"
        )
    if info.st_uid != os.getuid():
        raise AssertionError(
            f"refusing to retain foreign fixture cache path: {path}"
        )
    quarantine_name, quarantined = _quarantine_helper_cache_root(
        cache_root_descriptor,
        path.name,
        expected_root if expected_root is not None else info,
    )
    retained_root = _pin_retained_root_binding(
        cache_root_descriptor,
        quarantine_name,
        quarantined,
    )
    try:
        _retained_cleanup_usage(cache_root_descriptor)
    except (AssertionError, OSError):
        try:
            _restore_unrelated_cleanup_quarantine(
                cache_root_descriptor,
                path.name,
                quarantine_name,
                retained_root,
            )
        except (AssertionError, OSError) as restore_exc:
            raise AssertionError(
                "fixture cleanup retention bound failed with retained quarantine"
            ) from restore_exc
        raise
    os.fsync(cache_root_descriptor)
    try:
        os.stat(
            path.name,
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        pass
    else:
        raise AssertionError(
            "fixture cache root name was recreated during retention"
        )


def _require_owned_open_node(
    info: os.stat_result,
    *,
    kind: str,
    expected_identity: tuple[int, ...],
) -> None:
    if (
        _stable_file_identity(info) != expected_identity
        or info.st_uid != os.getuid()
        or (kind == "directory" and not stat.S_ISDIR(info.st_mode))
        or (
            kind == "file"
            and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)
        )
    ):
        raise AssertionError(f"fixture cache {kind} identity drifted during cleanup")


def _same_cleanup_binding(
    current: os.stat_result,
    expected: os.stat_result,
) -> bool:
    return (
        current.st_dev,
        current.st_ino,
        current.st_uid,
        stat.S_IFMT(current.st_mode),
        stat.S_IMODE(current.st_mode),
    ) == (
        expected.st_dev,
        expected.st_ino,
        expected.st_uid,
        stat.S_IFMT(expected.st_mode),
        stat.S_IMODE(expected.st_mode),
    )


def _same_owned_cleanup_directory(
    current: os.stat_result,
    expected: os.stat_result,
) -> bool:
    return (
        _same_cleanup_binding(current, expected)
        and stat.S_ISDIR(current.st_mode)
        and current.st_uid == os.getuid()
    )


def _pin_retained_root_binding(
    cache_root_descriptor: int,
    quarantine_name: str,
    expected_root: os.stat_result,
) -> os.stat_result:
    root_descriptor = os.open(
        quarantine_name,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=cache_root_descriptor,
    )
    try:
        opened = os.fstat(root_descriptor)
        named = os.stat(
            quarantine_name,
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
        if (
            not _same_cleanup_binding(opened, expected_root)
            or not _same_cleanup_binding(named, expected_root)
            or not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != os.getuid()
        ):
            raise AssertionError(
                "fixture cleanup retained root changed before pinning"
            )
        pinned_after = os.fstat(root_descriptor)
        named_after = os.stat(
            quarantine_name,
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
        if (
            not _same_owned_cleanup_directory(pinned_after, expected_root)
            or not _same_owned_cleanup_directory(named_after, expected_root)
        ):
            raise AssertionError(
                "fixture cleanup retained root changed while pinning"
            )
        return pinned_after
    finally:
        os.close(root_descriptor)


def _optional_cleanup_stat(
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


def _restore_unrelated_cleanup_quarantine(
    cache_root_descriptor: int,
    legal_name: str,
    quarantine_name: str,
    moved: os.stat_result,
) -> None:
    current_quarantine = _optional_cleanup_stat(
        cache_root_descriptor,
        quarantine_name,
    )
    if (
        current_quarantine is None
        or not _same_cleanup_binding(current_quarantine, moved)
        or _optional_cleanup_stat(cache_root_descriptor, legal_name) is not None
    ):
        raise AssertionError(
            "unrelated fixture cache inode retained in cleanup quarantine"
        )
    try:
        renameat2_no_replace(
            cache_root_descriptor,
            quarantine_name,
            cache_root_descriptor,
            legal_name,
        )
    except BaseException as exc:
        restored = _optional_cleanup_stat(cache_root_descriptor, legal_name)
        hidden = _optional_cleanup_stat(
            cache_root_descriptor,
            quarantine_name,
        )
        if (
            restored is not None
            and _same_cleanup_binding(restored, moved)
            and hidden is None
        ):
            return
        raise AssertionError(
            "unrelated fixture cache inode could not be restored"
        ) from exc
    restored = os.stat(
        legal_name,
        dir_fd=cache_root_descriptor,
        follow_symlinks=False,
    )
    if (
        not _same_cleanup_binding(restored, moved)
        or _optional_cleanup_stat(cache_root_descriptor, quarantine_name)
        is not None
    ):
        raise AssertionError(
            "unrelated fixture cache inode restore changed binding"
        )


def _quarantine_helper_cache_root(
    cache_root_descriptor: int,
    legal_name: str,
    expected_root: os.stat_result,
) -> tuple[str, os.stat_result]:
    for _attempt in range(128):
        quarantine_name = (
            f".{legal_name}.retained-{expected_root.st_dev:x}-"
            f"{expected_root.st_ino:x}-{secrets.token_hex(16)}"
        )
        try:
            renameat2_no_replace(
                cache_root_descriptor,
                legal_name,
                cache_root_descriptor,
                quarantine_name,
            )
        except FileExistsError:
            continue
        break
    else:
        raise AssertionError("fixture cache cleanup quarantine exhausted")
    quarantined = os.stat(
        quarantine_name,
        dir_fd=cache_root_descriptor,
        follow_symlinks=False,
    )
    if not _same_cleanup_binding(quarantined, expected_root):
        _restore_unrelated_cleanup_quarantine(
            cache_root_descriptor,
            legal_name,
            quarantine_name,
            quarantined,
        )
        raise AssertionError(
            "fixture cache root changed before cleanup quarantine"
        )
    return quarantine_name, quarantined


def _retained_cleanup_tree_bytes(
    directory_descriptor: int,
    budget: list[int],
    depth: int,
) -> int:
    if depth > _MAX_PATH_PARTS:
        raise AssertionError(
            "fixture cleanup retention inventory exceeds depth bound"
        )
    opened_directory = os.fstat(directory_descriptor)
    if (
        not stat.S_ISDIR(opened_directory.st_mode)
        or opened_directory.st_uid != os.getuid()
    ):
        raise AssertionError(
            "fixture cleanup retention directory is not owned"
        )
    total_bytes = opened_directory.st_size
    with os.scandir(directory_descriptor) as entries:
        for entry in entries:
            budget[0] += 1
            if budget[0] > _MAX_TREE_ENTRIES:
                raise AssertionError(
                    "fixture cleanup retention inventory exceeds entry bound"
                )
            discovered = entry.stat(follow_symlinks=False)
            discovered_identity = _stable_file_identity(discovered)
            if discovered.st_uid != os.getuid():
                raise AssertionError(
                    "fixture cleanup retention contains a foreign node"
                )
            total_bytes += discovered.st_size
            if total_bytes > _MAX_RETAINED_CLEANUP_BYTES:
                raise AssertionError(
                    "fixture cleanup retention aggregate size bound exceeded"
                )
            if stat.S_ISREG(discovered.st_mode):
                if discovered.st_nlink != 1:
                    raise AssertionError(
                        "fixture cleanup retention file has multiple links"
                    )
                child_descriptor = os.open(
                    entry.name,
                    os.O_RDONLY
                    | os.O_NONBLOCK
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_descriptor,
                )
                try:
                    opened = os.fstat(child_descriptor)
                    _require_owned_open_node(
                        opened,
                        kind="file",
                        expected_identity=discovered_identity,
                    )
                    after = os.fstat(child_descriptor)
                    current = os.stat(
                        entry.name,
                        dir_fd=directory_descriptor,
                        follow_symlinks=False,
                    )
                    _require_owned_open_node(
                        after,
                        kind="file",
                        expected_identity=discovered_identity,
                    )
                    _require_owned_open_node(
                        current,
                        kind="file",
                        expected_identity=discovered_identity,
                    )
                finally:
                    os.close(child_descriptor)
                continue
            if not stat.S_ISDIR(discovered.st_mode):
                raise AssertionError(
                    "fixture cleanup retention contains a link or special node"
                )
            child_descriptor = os.open(
                entry.name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_descriptor,
            )
            try:
                opened = os.fstat(child_descriptor)
                _require_owned_open_node(
                    opened,
                    kind="directory",
                    expected_identity=discovered_identity,
                )
                child_bytes = _retained_cleanup_tree_bytes(
                    child_descriptor,
                    budget,
                    depth + 1,
                )
                total_bytes += child_bytes - discovered.st_size
                current = os.stat(
                    entry.name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                if (
                    not _same_cleanup_binding(current, opened)
                    or not stat.S_ISDIR(current.st_mode)
                    or current.st_uid != os.getuid()
                ):
                    raise AssertionError(
                        "fixture cleanup retention directory changed"
                    )
            finally:
                os.close(child_descriptor)
            if total_bytes > _MAX_RETAINED_CLEANUP_BYTES:
                raise AssertionError(
                    "fixture cleanup retention aggregate size bound exceeded"
                )
    if _stable_file_identity(os.fstat(directory_descriptor)) != _stable_file_identity(
        opened_directory
    ):
        raise AssertionError("fixture cleanup retention directory changed")
    return total_bytes


def _retained_cleanup_usage(
    cache_root_descriptor: int,
) -> tuple[int, int]:
    cache_root_before = os.fstat(cache_root_descriptor)
    retained_count = 0
    retained_bytes = 0
    budget = [0]
    with os.scandir(cache_root_descriptor) as entries:
        for entry in entries:
            match = _RETAINED_CACHE_NAME.fullmatch(entry.name)
            if match is None:
                continue
            retained_count += 1
            if retained_count > _MAX_RETAINED_CLEANUP_TOMBSTONES:
                raise AssertionError(
                    "fixture cleanup retention count bound exceeded"
                )
            discovered = entry.stat(follow_symlinks=False)
            if (
                not stat.S_ISDIR(discovered.st_mode)
                or discovered.st_uid != os.getuid()
                or discovered.st_dev != int(match.group("device"), 16)
                or discovered.st_ino != int(match.group("inode"), 16)
            ):
                raise AssertionError(
                    "fixture cleanup retention name does not bind its audited root"
                )
            root_descriptor = os.open(
                entry.name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=cache_root_descriptor,
            )
            try:
                opened = os.fstat(root_descriptor)
                if not _same_owned_cleanup_directory(opened, discovered):
                    raise AssertionError(
                        "fixture cleanup retention root changed before inventory"
                    )
                retained_bytes += _retained_cleanup_tree_bytes(
                    root_descriptor,
                    budget,
                    0,
                )
                pinned_after = os.fstat(root_descriptor)
                named_after = os.stat(
                    entry.name,
                    dir_fd=cache_root_descriptor,
                    follow_symlinks=False,
                )
                if (
                    not _same_owned_cleanup_directory(
                        pinned_after,
                        opened,
                    )
                    or not _same_owned_cleanup_directory(
                        named_after,
                        opened,
                    )
                ):
                    raise AssertionError(
                        "fixture cleanup retention audited name changed"
                    )
            finally:
                os.close(root_descriptor)
            if retained_bytes > _MAX_RETAINED_CLEANUP_BYTES:
                raise AssertionError(
                    "fixture cleanup retention aggregate size bound exceeded"
                )
    if _stable_file_identity(os.fstat(cache_root_descriptor)) != _stable_file_identity(
        cache_root_before
    ):
        raise AssertionError(
            "fixture cleanup cache root changed during retention inventory"
        )
    return retained_count, retained_bytes


def _source_parts(relative: str) -> tuple[str, ...]:
    value = PurePosixPath(relative)
    parts = value.parts
    if value.is_absolute() or _checked_relative(parts) != relative:
        raise AssertionError(f"invalid captured fixture path: {relative}")
    return parts


def _expected_snapshot_directories(snapshot: _SourceSnapshot) -> set[str]:
    directories = {""}
    for source in snapshot.files:
        parts = _source_parts(source.relative)
        for length in range(1, len(parts)):
            directories.add("/".join(parts[:length]))
    return directories


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise AssertionError("fixture snapshot write made no progress")
        offset += written


def _directory_object_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        stat.S_IFMT(info.st_mode),
    )


def _require_temporary_snapshot_root_binding(
    temporary_snapshot: Path,
    pinned_root_descriptor: int,
    expected_root: os.stat_result,
) -> None:
    pinned = os.fstat(pinned_root_descriptor)
    lexical = temporary_snapshot.lstat()
    expected = _directory_object_identity(expected_root)
    if (
        _directory_object_identity(pinned) != expected
        or _directory_object_identity(lexical) != expected
        or not stat.S_ISDIR(pinned.st_mode)
        or pinned.st_uid != os.getuid()
    ):
        raise AssertionError("fixture temporary snapshot root binding changed")


def _open_materialized_snapshot_directory(
    pinned_root_descriptor: int,
    parts: tuple[str, ...],
    directory_identities: dict[str, tuple[int, int, int, int]],
) -> int:
    descriptor = os.open(
        ".",
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=pinned_root_descriptor,
    )
    traversed: list[str] = []
    try:
        for part in parts:
            child = os.open(
                part,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            traversed.append(part)
            relative = _checked_relative(tuple(traversed))
            opened = os.fstat(child)
            if (
                _directory_object_identity(opened)
                != directory_identities.get(relative)
                or opened.st_uid != os.getuid()
                or not stat.S_ISDIR(opened.st_mode)
            ):
                os.close(child)
                raise AssertionError(
                    "fixture temporary snapshot directory binding changed"
                )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _materialize_source_snapshot(
    temporary_snapshot: Path,
    pinned_root_descriptor: int,
    expected_root: os.stat_result,
    snapshot: _SourceSnapshot,
) -> None:
    _require_temporary_snapshot_root_binding(
        temporary_snapshot,
        pinned_root_descriptor,
        expected_root,
    )
    os.fchmod(pinned_root_descriptor, 0o700)
    directory_identities: dict[str, tuple[int, int, int, int]] = {
        "": _directory_object_identity(os.fstat(pinned_root_descriptor))
    }
    for directory in sorted(
        _expected_snapshot_directories(snapshot) - {""},
        key=lambda item: (item.count("/"), os.fsencode(item)),
    ):
        parts = PurePosixPath(directory).parts
        parent_descriptor = _open_materialized_snapshot_directory(
            pinned_root_descriptor,
            tuple(parts[:-1]),
            directory_identities,
        )
        try:
            os.mkdir(parts[-1], mode=0o700, dir_fd=parent_descriptor)
            child_descriptor = os.open(
                parts[-1],
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
            try:
                opened = os.fstat(child_descriptor)
                if opened.st_uid != os.getuid() or not stat.S_ISDIR(opened.st_mode):
                    raise AssertionError(
                        "fixture temporary snapshot directory is not owned"
                    )
                os.fchmod(child_descriptor, 0o700)
                directory_identities[directory] = _directory_object_identity(opened)
            finally:
                os.close(child_descriptor)
        finally:
            os.close(parent_descriptor)
    for source in snapshot.files:
        parts = _source_parts(source.relative)
        parent_descriptor = _open_materialized_snapshot_directory(
            pinned_root_descriptor,
            parts[:-1],
            directory_identities,
        )
        descriptor = os.open(
            parts[-1],
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
            ):
                raise AssertionError(
                    "fixture temporary snapshot file is not owned"
                )
            _write_all(descriptor, source.data)
            os.fchmod(descriptor, 0o400)
        finally:
            os.close(descriptor)
            os.close(parent_descriptor)
    for directory in sorted(
        _expected_snapshot_directories(snapshot),
        key=lambda item: (item.count("/"), os.fsencode(item)),
        reverse=True,
    ):
        parts = () if not directory else tuple(PurePosixPath(directory).parts)
        descriptor = _open_materialized_snapshot_directory(
            pinned_root_descriptor,
            parts,
            directory_identities,
        )
        try:
            os.fchmod(descriptor, 0o500)
        finally:
            os.close(descriptor)
    _require_temporary_snapshot_root_binding(
        temporary_snapshot,
        pinned_root_descriptor,
        expected_root,
    )


def _source_snapshot_state_from_descriptor(
    pinned_root_descriptor: int,
    snapshot: _SourceSnapshot,
) -> _SnapshotTreeState:
    expected_files = {source.relative: source.data for source in snapshot.files}
    expected_directories = _expected_snapshot_directories(snapshot)
    seen_files: set[str] = set()
    seen_directories = {""}
    directory_identities: dict[str, tuple[int, ...]] = {}
    file_identities: dict[str, tuple[int, ...]] = {}
    visited_entries = 0
    root_descriptor = os.open(
        ".",
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=pinned_root_descriptor,
    )

    def require_private(info: os.stat_result, relative: str, mode: int) -> None:
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != mode:
            raise AssertionError(
                f"fixture source snapshot node is not private: {relative or '.'}"
            )

    def visit(directory_fd: int, parts: tuple[str, ...]) -> None:
        nonlocal visited_entries
        with os.scandir(directory_fd) as entries:
            for _entry in entries:
                visited_entries += 1
                if visited_entries > _MAX_TREE_ENTRIES:
                    raise AssertionError(
                        "fixture source snapshot validation entry bound exceeded"
                    )
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                relative_parts = (*parts, entry.name)
                relative = _checked_relative(relative_parts)
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise AssertionError(
                        f"fixture source snapshot contains a symlink: {relative}"
                    )
                if stat.S_ISDIR(info.st_mode):
                    if relative not in expected_directories:
                        raise AssertionError(
                            f"fixture source snapshot contains an extra directory: {relative}"
                        )
                    require_private(info, relative, 0o500)
                    child = os.open(
                        entry.name,
                        os.O_RDONLY
                        | getattr(os, "O_CLOEXEC", 0)
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=directory_fd,
                    )
                    try:
                        child_before = os.fstat(child)
                        if _stable_file_identity(
                            child_before
                        ) != _stable_file_identity(info):
                            raise AssertionError(
                                f"fixture source snapshot directory drifted: {relative}"
                            )
                        seen_directories.add(relative)
                        visit(child, relative_parts)
                        if _stable_file_identity(
                            os.fstat(child)
                        ) != _stable_file_identity(child_before):
                            raise AssertionError(
                                f"fixture source snapshot directory changed: {relative}"
                            )
                        directory_identities[relative] = _stable_file_identity(
                            child_before
                        )
                    finally:
                        os.close(child)
                    continue
                if not stat.S_ISREG(info.st_mode) or relative not in expected_files:
                    raise AssertionError(
                        f"fixture source snapshot contains an extra node: {relative}"
                    )
                require_private(info, relative, 0o400)
                data, _identity = _bounded_source_bytes(
                    directory_fd, entry.name, relative, info
                )
                if data != expected_files[relative]:
                    raise AssertionError(
                        f"fixture source snapshot bytes do not match: {relative}"
                    )
                seen_files.add(relative)
                file_identities[relative] = _identity

    try:
        root_before = os.fstat(root_descriptor)
        if not stat.S_ISDIR(root_before.st_mode):
            raise AssertionError("fixture source snapshot is not a directory")
        require_private(root_before, "", 0o500)
        visit(root_descriptor, ())
        root_after = os.fstat(root_descriptor)
    finally:
        os.close(root_descriptor)
    if _stable_file_identity(root_after) != _stable_file_identity(root_before):
        raise AssertionError("fixture source snapshot root changed during validation")
    if seen_files != set(expected_files) or seen_directories != expected_directories:
        raise AssertionError("fixture source snapshot tree is incomplete")
    return _SnapshotTreeState(
        _stable_file_identity(root_before),
        tuple(sorted(directory_identities.items())),
        tuple(sorted(file_identities.items())),
    )


def _validate_source_snapshot(
    path: Path,
    snapshot: _SourceSnapshot,
) -> _SnapshotTreeState:
    root_descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        lexical_before = path.lstat()
        state = _source_snapshot_state_from_descriptor(root_descriptor, snapshot)
        lexical_after = path.lstat()
    finally:
        os.close(root_descriptor)
    if (
        _stable_file_identity(lexical_before) != state.root_identity
        or _stable_file_identity(lexical_after) != state.root_identity
    ):
        raise AssertionError("fixture source snapshot lexical binding changed")
    return state


def _open_pinned_source_snapshot(
    path: Path,
    snapshot: _SourceSnapshot,
    expected_state: _SnapshotTreeState | None = None,
) -> tuple[int, _SnapshotTreeState]:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        lexical_before = path.lstat()
        state = _source_snapshot_state_from_descriptor(descriptor, snapshot)
        lexical_after = path.lstat()
        if (
            _stable_file_identity(lexical_before) != state.root_identity
            or _stable_file_identity(lexical_after) != state.root_identity
            or (expected_state is not None and state != expected_state)
        ):
            raise AssertionError("fixture source snapshot binding drifted")
        return descriptor, state
    except BaseException:
        os.close(descriptor)
        raise


def _require_pinned_source_snapshot(
    path: Path,
    pinned_root_descriptor: int,
    snapshot: _SourceSnapshot,
    expected_state: _SnapshotTreeState,
) -> None:
    try:
        lexical_before = path.lstat()
        state = _source_snapshot_state_from_descriptor(
            pinned_root_descriptor,
            snapshot,
        )
        lexical_after = path.lstat()
        if (
            _stable_file_identity(lexical_before) != expected_state.root_identity
            or _stable_file_identity(lexical_after) != expected_state.root_identity
            or state != expected_state
        ):
            raise AssertionError("fixture source snapshot binding drifted")
    except (AssertionError, OSError) as exc:
        raise AssertionError(
            "fixture source snapshot changed during CodeQL fixture DB build"
        ) from exc


def _ensure_source_snapshot(
    cache_root: Path,
    snapshot: _SourceSnapshot,
) -> Path:
    candidates = _bounded_digest_candidate_paths(
        cache_root,
        snapshot.digest,
        kind="sources",
    )
    validated_candidates: list[Path] = []
    for candidate in candidates:
        try:
            _validate_source_snapshot(candidate, snapshot)
        except (AssertionError, OSError) as exc:
            raise AssertionError(
                "fixture source snapshot candidate is invalid"
            ) from exc
        validated_candidates.append(candidate)
    if validated_candidates:
        return validated_candidates[0]

    stable = _create_stable_cache_directory(
        cache_root,
        snapshot.digest,
        kind="sources",
    )
    candidate_validated = False
    stable_descriptor: int | None = None
    try:
        stable_before = stable.lstat()
        stable_descriptor = os.open(
            stable,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened_stable = os.fstat(stable_descriptor)
        if (
            _directory_object_identity(opened_stable)
            != _directory_object_identity(stable_before)
            or not stat.S_ISDIR(opened_stable.st_mode)
            or opened_stable.st_uid != os.getuid()
            or stat.S_IMODE(opened_stable.st_mode) != 0o700
        ):
            raise AssertionError("fixture stable snapshot was replaced after creation")
        _materialize_source_snapshot(
            stable,
            stable_descriptor,
            opened_stable,
            snapshot,
        )
        stable_state = _source_snapshot_state_from_descriptor(
            stable_descriptor,
            snapshot,
        )
        _require_pinned_source_snapshot(
            stable,
            stable_descriptor,
            snapshot,
            stable_state,
        )
        _validate_source_snapshot(stable, snapshot)
        final_state = _source_snapshot_state_from_descriptor(
            stable_descriptor,
            snapshot,
        )
        _require_pinned_source_snapshot(
            stable,
            stable_descriptor,
            snapshot,
            final_state,
        )
        _validate_source_snapshot(stable, snapshot)
        candidate_validated = True
        return stable
    finally:
        if stable_descriptor is not None:
            os.close(stable_descriptor)
        if not candidate_validated and (stable.exists() or stable.is_symlink()):
            _remove_helper_owned_cache_path(stable, cache_root)


def _require_database_source_root(info: DatabaseInfo, source_root: Path) -> None:
    if info.source_root.resolve(strict=True) != source_root.resolve(strict=True):
        raise AssertionError(
            "CodeQL fixture DB provenance does not match its private source snapshot"
        )


def _select_cached_database(
    cache_root: Path,
    snapshot: _SourceSnapshot,
    source_root: Path,
) -> DatabaseInfo | None:
    candidates = _bounded_digest_candidate_paths(
        cache_root,
        snapshot.digest,
        kind="db",
    )
    validated: list[DatabaseInfo] = []
    for database in candidates:
        try:
            info = validate_database(database)
            _require_database_source_root(info, source_root)
        except (AssertionError, OSError) as exc:
            raise AssertionError("fixture database candidate is invalid") from exc
        validated.append(info)
    return validated[0] if validated else None


def _require_pinned_classes_directory(
    pinned: _PinnedClassesDirectory,
) -> None:
    expected = _directory_object_identity(pinned.expected_identity)
    expected_cache_root = _directory_object_identity(pinned.cache_root_identity)
    try:
        descriptor_info = os.fstat(pinned.descriptor)
        named_info = os.stat(
            pinned.path.name,
            dir_fd=pinned.cache_root_descriptor,
            follow_symlinks=False,
        )
        lexical_info = pinned.path.lstat()
        cache_descriptor_info = os.fstat(pinned.cache_root_descriptor)
        cache_lexical_info = pinned.cache_root.lstat()
    except OSError as exc:
        raise AssertionError(
            "fixture classes directory binding changed"
        ) from exc
    if (
        _directory_object_identity(descriptor_info) != expected
        or _directory_object_identity(named_info) != expected
        or _directory_object_identity(lexical_info) != expected
        or any(
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            for info in (descriptor_info, named_info, lexical_info)
        )
        or _directory_object_identity(cache_descriptor_info)
        != expected_cache_root
        or _directory_object_identity(cache_lexical_info)
        != expected_cache_root
        or not stat.S_ISDIR(cache_descriptor_info.st_mode)
        or cache_descriptor_info.st_uid != os.getuid()
        or stat.S_IMODE(cache_descriptor_info.st_mode) != 0o700
        or not stat.S_ISDIR(cache_lexical_info.st_mode)
        or cache_lexical_info.st_uid != os.getuid()
        or stat.S_IMODE(cache_lexical_info.st_mode) != 0o700
    ):
        raise AssertionError("fixture classes directory binding changed")


def _open_pinned_classes_directory(
    cache_root: Path,
    digest: str,
    *,
    owner_holder: list[_PinnedClassesDirectory],
) -> _PinnedClassesDirectory:
    cache_root_identity = cache_root.lstat()
    close_capability = require_close_fd_once()
    cache_root_owner: list[int] = []
    descriptor_owner: list[int] = []
    cache_root_release = DeferredCloseFdOnceOutcome()
    descriptor_release = DeferredCloseFdOnceOutcome()
    cache_root_descriptor = -1
    classes_descriptor: int | None = None
    classes: Path | None = None
    expected_identity: os.stat_result | None = None
    transferred = False
    try:
        cache_root_descriptor = open_owned_descriptor(
            cache_root_owner,
            cache_root,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened_cache_root = os.fstat(cache_root_descriptor)
        if (
            _directory_object_identity(opened_cache_root)
            != _directory_object_identity(cache_root_identity)
            or not stat.S_ISDIR(opened_cache_root.st_mode)
            or opened_cache_root.st_uid != os.getuid()
            or stat.S_IMODE(opened_cache_root.st_mode) != 0o700
        ):
            raise AssertionError(
                "fixture classes cache root changed before pinning"
            )
        created = Path(
            tempfile.mkdtemp(
                prefix=f".{digest}.classes.tmp-",
                dir=f"/proc/self/fd/{cache_root_descriptor}",
            )
        )
        classes = cache_root / created.name
        if _CACHE_NAME.fullmatch(classes.name) is None:
            raise AssertionError("fixture classes directory name is invalid")
        expected_identity = os.stat(
            classes.name,
            dir_fd=cache_root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(expected_identity.st_mode)
            or expected_identity.st_uid != os.getuid()
            or stat.S_IMODE(expected_identity.st_mode) != 0o700
        ):
            raise AssertionError(
                "fixture classes directory is not a private owned directory"
            )
        try:
            classes_descriptor = open_owned_descriptor(
                descriptor_owner,
                classes.name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=cache_root_descriptor,
            )
        except OSError as exc:
            raise AssertionError(
                "fixture classes directory changed before pinning"
            ) from exc
        pinned = _PinnedClassesDirectory(
            path=classes,
            cache_root=cache_root,
            cache_root_descriptor=cache_root_descriptor,
            cache_root_identity=opened_cache_root,
            descriptor=classes_descriptor,
            expected_identity=expected_identity,
            close_capability=close_capability,
            cache_root_owner=cache_root_owner,
            cache_root_release=cache_root_release,
            descriptor_owner=descriptor_owner,
            descriptor_release=descriptor_release,
        )
        _require_pinned_classes_directory(pinned)
        os.fchmod(classes_descriptor, 0o700)
        _require_pinned_classes_directory(pinned)
        append_failure: BaseException | None = None

        def transfer_to_caller() -> None:
            nonlocal append_failure, transferred
            try:
                if owner_holder:
                    raise OSError(
                        "fixture classes caller owner is already populated"
                    )
                owner_holder.append(pinned)
            except BaseException as exc:
                append_failure = exc
            finally:
                transferred = any(
                    candidate is pinned for candidate in owner_holder
                )

        run_with_deferred_interrupts(transfer_to_caller)
        if append_failure is not None:
            raise append_failure
        return pinned
    except BaseException:
        if transferred:
            raise
        try:
            try:
                _release_fixture_descriptor_owner_must_reach(
                    descriptor_owner,
                    close_capability,
                    descriptor_release,
                )
            finally:
                _release_fixture_descriptor_owner_must_reach(
                    descriptor_owner,
                    close_capability,
                    descriptor_release,
                )
        finally:
            try:
                if (
                    cache_root_descriptor >= 0
                    and classes is not None
                    and expected_identity is not None
                ):
                    current = _optional_cleanup_stat(
                        cache_root_descriptor,
                        classes.name,
                    )
                    if current is not None and _same_cleanup_binding(
                        current,
                        expected_identity,
                    ):
                        try:
                            _retain_helper_owned_cache_path(
                                classes,
                                cache_root_descriptor,
                                expected_root=expected_identity,
                            )
                        except (AssertionError, OSError):
                            pass
            finally:
                try:
                    _release_fixture_descriptor_owner_must_reach(
                        cache_root_owner,
                        close_capability,
                        cache_root_release,
                    )
                finally:
                    _release_fixture_descriptor_owner_must_reach(
                        cache_root_owner,
                        close_capability,
                        cache_root_release,
                    )
        raise


def _cleanup_pinned_classes_directory(
    pinned: _PinnedClassesDirectory,
) -> None:
    try:
        _require_pinned_classes_directory(pinned)
        _retain_helper_owned_cache_path(
            pinned.path,
            pinned.cache_root_descriptor,
            expected_root=pinned.expected_identity,
        )
    except (AssertionError, OSError) as exc:
        raise AssertionError(
            "fixture classes directory changed before cleanup"
        ) from exc
    finally:
        try:
            try:
                _release_fixture_descriptor_owner_must_reach(
                    pinned.descriptor_owner,
                    pinned.close_capability,
                    pinned.descriptor_release,
                )
            finally:
                _release_fixture_descriptor_owner_must_reach(
                    pinned.descriptor_owner,
                    pinned.close_capability,
                    pinned.descriptor_release,
                )
        finally:
            try:
                _release_fixture_descriptor_owner_must_reach(
                    pinned.cache_root_owner,
                    pinned.close_capability,
                    pinned.cache_root_release,
                )
            finally:
                _release_fixture_descriptor_owner_must_reach(
                    pinned.cache_root_owner,
                    pinned.close_capability,
                    pinned.cache_root_release,
                )


def _cleanup_pinned_classes_owner_slot(
    owner_holder: list[_PinnedClassesDirectory],
) -> None:
    if not owner_holder:
        return
    if len(owner_holder) != 1 or not isinstance(
        owner_holder[0], _PinnedClassesDirectory
    ):
        raise OSError("fixture classes caller owner is malformed")
    pinned = owner_holder[0]
    cleanup_failure: BaseException | None = None
    descriptors_consumed = (
        _fixture_descriptor_release_consumed(pinned.descriptor_release)
        and _fixture_descriptor_release_consumed(pinned.cache_root_release)
    )
    if not descriptors_consumed:
        try:
            _cleanup_pinned_classes_directory(pinned)
        except BaseException as exc:
            cleanup_failure = exc
    descriptors_consumed = (
        _fixture_descriptor_release_consumed(pinned.descriptor_release)
        and _fixture_descriptor_release_consumed(pinned.cache_root_release)
    )
    if descriptors_consumed:
        def clear_owner() -> None:
            if len(owner_holder) != 1 or owner_holder[0] is not pinned:
                raise OSError(
                    "fixture classes caller ownership changed before release"
                )
            owner_holder.pop()

        run_with_deferred_interrupts(clear_owner)
    if cleanup_failure is not None:
        raise cleanup_failure
    if owner_holder:
        raise OSError("fixture classes caller ownership was not consumed")


def _build_database(
    cache_root: Path,
    snapshot: _SourceSnapshot,
    source_root: Path,
) -> DatabaseInfo:
    cached = _select_cached_database(cache_root, snapshot, source_root)
    if cached is not None:
        return cached

    database = _new_uncreated_stable_cache_path(
        cache_root,
        snapshot.digest,
        kind="db",
    )
    classes_owner: list[_PinnedClassesDirectory] = []
    classes: _PinnedClassesDirectory | None = None
    database_validated = False
    source_descriptor: int | None = None
    source_state: _SnapshotTreeState | None = None
    try:
        classes = _open_pinned_classes_directory(
            cache_root,
            snapshot.digest,
            owner_holder=classes_owner,
        )
        if len(classes_owner) != 1 or classes_owner[0] is not classes:
            raise OSError("fixture classes caller ownership transfer failed")
        java_files = tuple(source.relative for source in snapshot.files)
        # CodeQL's trace-command intermediary closes unrelated descriptors
        # before launching javac. Bind javac to this still-live helper process
        # instead of letting /proc/self resolve in that grandchild.
        pinned_classes = f"/proc/{os.getpid()}/fd/{classes.descriptor}"
        command = " ".join(
            [
                shlex.quote(_JAVAC),
                "-d",
                shlex.quote(pinned_classes),
                *(shlex.quote(item) for item in java_files),
            ]
        )
        source_descriptor, source_state = _open_pinned_source_snapshot(
            source_root,
            snapshot,
        )
        _require_pinned_source_snapshot(
            source_root,
            source_descriptor,
            snapshot,
            source_state,
        )
        _require_pinned_classes_directory(classes)
        pinned_cwd = f"/proc/self/fd/{source_descriptor}"
        if _stable_file_identity(Path(pinned_cwd).stat()) != source_state.root_identity:
            raise AssertionError("fixture source snapshot fd binding is invalid")
        if (
            _directory_object_identity(Path(pinned_classes).stat())
            != _directory_object_identity(classes.expected_identity)
        ):
            raise AssertionError("fixture classes directory fd binding is invalid")
        completed = subprocess.run(
            [
                _CODEQL,
                "database",
                "create",
                str(database),
                "--language=java",
                "--source-root=.",
                f"--command={command}",
            ],
            cwd=pinned_cwd,
            pass_fds=(source_descriptor, classes.descriptor),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=600,
        )
        _require_pinned_source_snapshot(
            source_root,
            source_descriptor,
            snapshot,
            source_state,
        )
        _require_pinned_classes_directory(classes)
        if completed.returncode:
            raise AssertionError(
                f"CodeQL fixture DB build failed for {source_root}:\n"
                f"{completed.stderr[-4000:]}"
            )
        os.close(source_descriptor)
        source_descriptor = None
        built_info = validate_database(database)
        _require_database_source_root(built_info, source_root)
        source_descriptor, reopened_state = _open_pinned_source_snapshot(
            source_root,
            snapshot,
            source_state,
        )
        if reopened_state != source_state:
            raise AssertionError(
                "fixture source snapshot changed during CodeQL fixture DB build"
            )
        finalized = validate_database(database)
        _require_database_source_root(finalized, source_root)
        _require_pinned_source_snapshot(
            source_root,
            source_descriptor,
            snapshot,
            source_state,
        )
        _require_pinned_classes_directory(classes)
        try:
            _cleanup_pinned_classes_owner_slot(classes_owner)
        finally:
            _cleanup_pinned_classes_owner_slot(classes_owner)
        classes = None
        database_validated = True
        return finalized
    finally:
        try:
            if source_descriptor is not None:
                os.close(source_descriptor)
        finally:
            try:
                if (
                    not database_validated
                    and (database.exists() or database.is_symlink())
                ):
                    _remove_helper_owned_cache_path(database, cache_root)
            finally:
                try:
                    _cleanup_pinned_classes_owner_slot(classes_owner)
                finally:
                    _cleanup_pinned_classes_owner_slot(classes_owner)


def fixture_database(source_root_text: str) -> DatabaseInfo:
    """Compile one bounded Java fixture snapshot into a finalized private DB."""
    source_root = Path(source_root_text).resolve(strict=True)
    snapshot = _bounded_java_sources(source_root)
    cache_root = _prepare_cache_root(_CACHE_ROOT)
    with _digest_lock(cache_root, snapshot.digest):
        immutable_source_root = _ensure_source_snapshot(cache_root, snapshot)
        return _build_database(cache_root, snapshot, immutable_source_root)


__all__ = ["fixture_database"]
