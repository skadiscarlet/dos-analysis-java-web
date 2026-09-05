from __future__ import annotations

import errno
import hashlib
import math
import os
import secrets
import stat
import threading
import time
import weakref
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

import fcntl

import yaml

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.errors import AnalyzerError
from dosweb.filesystem import (
    CloseRangeCapability,
    DeferredCloseFdOnceOutcome,
    close_fd_once,
    open_owned_descriptor,
    release_owned_descriptor_once,
    renameat2_no_replace,
    require_close_fd_once,
    run_with_deferred_interrupts,
)

_MAX_METADATA_BYTES: Final = 1024 * 1024
_MAX_METADATA_DEPTH: Final = 32
_MAX_METADATA_NODES: Final = 8192
_MAX_METADATA_FILES: Final = 8192
_MAX_METADATA_FILE_BYTES: Final = 256 * 1024 * 1024
_MUTABLE_NAMES: Final = frozenset({"log", "logs", "diagnostic", "diagnostics", "working"})
_EXECUTION_PREFIX: Final = ".codeql-execution-"
_FICLONE: Final = 0x40049409
_MAX_EXECUTION_TREE_ENTRIES: Final = 2_000_000
_MAX_EXECUTION_TREE_DEPTH: Final = 256


@dataclass
class _ExecutionCleanupState:
    closed: bool = False


@dataclass(frozen=True)
class ExecutionDatabaseBinding:
    """Private per-run CodeQL execution database, never part of run identity."""

    path: Path
    device: int
    inode: int
    uid: int
    source_root: Path
    parent_path: Path
    parent_device: int
    parent_inode: int
    parent_uid: int
    parent_descriptor: int = field(compare=False, repr=False)
    close_capability: CloseRangeCapability = field(compare=False, repr=False)
    parent_release: DeferredCloseFdOnceOutcome = field(
        compare=False,
        repr=False,
    )
    lock: threading.RLock = field(
        default_factory=threading.RLock,
        compare=False,
        repr=False,
    )
    cleanup_state: _ExecutionCleanupState = field(
        default_factory=_ExecutionCleanupState,
        compare=False,
        repr=False,
    )


def _require_deadline(deadline: float | None, monotonic: Callable[[], float]) -> None:
    if deadline is not None and deadline - monotonic() <= 0:
        raise TimeoutError("database validation deadline exceeded")


@dataclass(frozen=True)
class DatabaseInfo:
    path: Path
    source_root: Path
    fingerprint: str
    execution: ExecutionDatabaseBinding | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    canonical_device: int | None = field(default=None, compare=False, repr=False)
    canonical_inode: int | None = field(default=None, compare=False, repr=False)


def _release_database_descriptor_must_reach(
    descriptor: int,
    close_capability: CloseRangeCapability,
    transaction: DeferredCloseFdOnceOutcome,
) -> None:
    if transaction.status is None:
        release_result: DeferredCloseFdOnceOutcome | None = None

        def release_descriptor() -> None:
            nonlocal release_result
            release_result = release_owned_descriptor_once(
                descriptor,
                close_capability,
                transaction=transaction,
                close_fn=close_fd_once,
            )

        run_with_deferred_interrupts(release_descriptor)
        if release_result is not transaction:
            raise OSError("database descriptor release transaction failed")
    if transaction.succeeded:
        return
    failures = transaction.failures
    if failures:
        raise failures[0]
    raise OSError("database descriptor release failed")


def _database_descriptor_release_consumed(
    transaction: DeferredCloseFdOnceOutcome,
) -> bool:
    return transaction.explicitly_consumed or (
        transaction.fallback_attempted and transaction.fallback_error is None
    )


def _release_database_descriptor_owner_must_reach(
    owner: list[int],
    close_capability: CloseRangeCapability,
    transaction: DeferredCloseFdOnceOutcome,
) -> None:
    """Release the one fd already registered in a structural owner slot."""

    if not owner:
        return
    if len(owner) != 1:
        raise OSError("database descriptor owner is malformed")
    descriptor = owner[0]

    def clear_owner() -> None:
        if len(owner) != 1 or owner[0] != descriptor:
            raise OSError("database descriptor ownership changed before release")
        owner.pop()

    if descriptor < 0:
        run_with_deferred_interrupts(clear_owner)
        return
    release_failure: BaseException | None = None
    try:
        _release_database_descriptor_must_reach(
            descriptor,
            close_capability,
            transaction,
        )
    except BaseException as exc:
        release_failure = exc
    consumed = _database_descriptor_release_consumed(transaction)
    if consumed:
        run_with_deferred_interrupts(clear_owner)
    if release_failure is not None:
        raise release_failure
    if not consumed:
        raise OSError("database descriptor release did not consume ownership")


def _transfer_database_descriptor_owner(
    owner: list[int],
    descriptor: int,
) -> None:
    """Transfer one structurally owned fd to an already-built binding."""

    def transfer() -> None:
        if len(owner) != 1 or owner[0] != descriptor:
            raise OSError("database descriptor ownership transfer is invalid")
        owner.pop()

    run_with_deferred_interrupts(transfer)


class _StrictMetadataLoader(yaml.SafeLoader):
    yaml_implicit_resolvers = {
        key: [
            resolver
            for resolver in resolvers
            if resolver[0] != "tag:yaml.org,2002:timestamp"
        ]
        for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    def compose_node(self, parent: object, index: object) -> yaml.Node:
        nodes = getattr(self, "_dosweb_nodes", 0) + 1
        depth = getattr(self, "_dosweb_depth", 0) + 1
        if nodes > _MAX_METADATA_NODES or depth > _MAX_METADATA_DEPTH:
            raise yaml.YAMLError("metadata structure exceeds limits")
        self._dosweb_nodes = nodes
        self._dosweb_depth = depth
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("metadata aliases are not supported")
        try:
            node = super().compose_node(parent, index)
        finally:
            self._dosweb_depth = depth - 1
        if node.tag not in {
            "tag:yaml.org,2002:null",
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:float",
            "tag:yaml.org,2002:str",
            "tag:yaml.org,2002:seq",
            "tag:yaml.org,2002:map",
        }:
            raise yaml.YAMLError("unsupported metadata tag")
        return node

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=False)
            try:
                if key in seen:
                    raise yaml.YAMLError("duplicate metadata key")
                seen.add(key)
            except TypeError as exc:
                raise yaml.YAMLError("unhashable metadata key") from exc
        return super().construct_mapping(node, deep=deep)


def _invalid(reason: str, path: Path, field: str | None = None) -> AnalyzerError:
    details: dict[str, object] = {"reason": reason, "path": str(path)[:1024]}
    if field is not None:
        details["field"] = field
    return AnalyzerError(
        "CODEQL_DATABASE_INVALID",
        "CodeQL database validation failed.",
        details,
    )


def _bounded_regular_bytes(
    path: Path,
    limit: int,
    close_capability: CloseRangeCapability,
) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor_owner: list[int] = []
    descriptor_release = DeferredCloseFdOnceOutcome()
    try:
        descriptor = open_owned_descriptor(descriptor_owner, path, flags)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("not a bounded regular file")
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > limit:
            raise ValueError("file exceeds limit")
        return bytes(data)
    finally:
        try:
            _release_database_descriptor_owner_must_reach(
                descriptor_owner,
                close_capability,
                descriptor_release,
            )
        finally:
            _release_database_descriptor_owner_must_reach(
                descriptor_owner,
                close_capability,
                descriptor_release,
            )


def _check_metadata_shape(value: object) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if depth > _MAX_METADATA_DEPTH or nodes > _MAX_METADATA_NODES:
            raise ValueError("metadata structure exceeds limits")
        if isinstance(current, dict):
            if any(not isinstance(key, str) for key in current):
                raise ValueError("metadata keys must be strings")
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError("metadata floats must be finite")
        elif current is not None and not isinstance(current, (str, int, bool)):
            raise ValueError("unsupported metadata value")


def _load_metadata(
    path: Path,
    close_capability: CloseRangeCapability,
) -> dict[str, object]:
    try:
        raw = _bounded_regular_bytes(path, _MAX_METADATA_BYTES, close_capability)
        text = raw.decode("utf-8")
        metadata = yaml.load(text, Loader=_StrictMetadataLoader)
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a mapping")
        _check_metadata_shape(metadata)
        return metadata
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError, MemoryError, RecursionError) as exc:
        raise _invalid("INVALID_METADATA", path) from exc


def _bounded_file_hash(
    path: Path,
    deadline: float | None,
    monotonic: Callable[[], float],
    close_capability: CloseRangeCapability,
) -> tuple[int, str]:
    descriptor_owner: list[int] = []
    descriptor_release = DeferredCloseFdOnceOutcome()
    try:
        descriptor = open_owned_descriptor(
            descriptor_owner,
            path,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_METADATA_FILE_BYTES:
            raise ValueError("unsafe metadata file")
        digest = hashlib.sha256()
        total = 0
        while total <= _MAX_METADATA_FILE_BYTES:
            _require_deadline(deadline, monotonic)
            chunk = os.read(descriptor, min(1024 * 1024, _MAX_METADATA_FILE_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            total > _MAX_METADATA_FILE_BYTES
            or total != before.st_size
            or after.st_size != before.st_size
            or after.st_ino != before.st_ino
        ):
            raise ValueError("metadata file changed while hashing")
        return total, digest.hexdigest()
    finally:
        try:
            _release_database_descriptor_owner_must_reach(
                descriptor_owner,
                close_capability,
                descriptor_release,
            )
        finally:
            _release_database_descriptor_owner_must_reach(
                descriptor_owner,
                close_capability,
                descriptor_release,
            )


def _stable_metadata_manifest(
    database: Path,
    deadline: float | None,
    monotonic: Callable[[], float],
    close_capability: CloseRangeCapability,
) -> list[dict[str, object]]:
    manifest: list[dict[str, object]] = []
    count = 0
    roots = [database / "db-java"]
    baseline = database / "baseline-info.json"
    if baseline.exists() or baseline.is_symlink():
        roots.append(baseline)
    try:
        stack = list(reversed(roots))
        while stack:
            _require_deadline(deadline, monotonic)
            candidate = stack.pop()
            relative = candidate.relative_to(database)
            if any(part.lower() in _MUTABLE_NAMES for part in relative.parts):
                continue
            if tuple(part.lower() for part in relative.parts[:3]) == (
                "db-java",
                "default",
                "cache",
            ):
                continue
            if candidate.name.startswith(".") or candidate.suffix in {".lock", ".tmp"}:
                continue
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("symlinked database metadata is not supported")
            if stat.S_ISDIR(info.st_mode):
                children: list[Path] = []
                with os.scandir(candidate) as entries:
                    for entry in entries:
                        count += 1
                        if count > _MAX_METADATA_FILES:
                            raise ValueError("too many metadata entries")
                        children.append(candidate / entry.name)
                stack.extend(reversed(sorted(children, key=lambda path: path.name)))
                continue
            size, digest = _bounded_file_hash(
                candidate,
                deadline,
                monotonic,
                close_capability,
            )
            manifest.append(
                {"path": relative.as_posix(), "size": size, "sha256": digest}
            )
    except TimeoutError:
        raise
    except (OSError, ValueError, MemoryError) as exc:
        raise _invalid("UNSTABLE_DATABASE_METADATA", database) from exc
    manifest.sort(key=lambda item: str(item["path"]))
    return manifest


def validate_database(
    path: Path | str,
    *,
    deadline: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> DatabaseInfo:
    supplied = Path(path)
    _require_deadline(deadline, monotonic)
    close_capability = require_close_fd_once()
    try:
        _reject_symlink_components(supplied)
        supplied_info = supplied.lstat()
        if stat.S_ISLNK(supplied_info.st_mode):
            raise ValueError("database root symlink is not supported")
        database = supplied.resolve(strict=True)
        if not database.is_dir():
            raise ValueError("database is not a directory")
        root_before = database.lstat()
        if not stat.S_ISDIR(root_before.st_mode):
            raise ValueError("database is not a directory")
    except (OSError, ValueError) as exc:
        raise _invalid("DATABASE_DIRECTORY_REQUIRED", supplied) from exc

    metadata_path = database / "codeql-database.yml"
    java_database = database / "db-java"
    if not metadata_path.exists() or metadata_path.is_symlink():
        raise _invalid("METADATA_REQUIRED", metadata_path)
    if not java_database.is_dir() or java_database.is_symlink():
        raise _invalid("JAVA_DATABASE_REQUIRED", java_database)

    metadata = _load_metadata(metadata_path, close_capability)
    source_prefix = metadata.get("sourceLocationPrefix")
    if not isinstance(source_prefix, str) or not source_prefix.strip():
        raise _invalid("SOURCE_ROOT_REQUIRED", metadata_path, "sourceLocationPrefix")
    try:
        source_root = Path(source_prefix).expanduser()
        if not source_root.is_absolute():
            source_root = database / source_root
        source_root = source_root.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _invalid("SOURCE_ROOT_INVALID", metadata_path, "sourceLocationPrefix") from exc

    try:
        fingerprint = sha256_canonical_json(
            {
                "format": "dosweb-codeql-database-v1",
                "metadata": metadata,
                "stable_files": _stable_metadata_manifest(
                    database,
                    deadline,
                    monotonic,
                    close_capability,
                ),
            }
        )
    except (TypeError, ValueError, UnicodeEncodeError, MemoryError, RecursionError) as exc:
        raise _invalid("INVALID_METADATA", metadata_path) from exc
    try:
        root_after = database.lstat()
    except OSError as exc:
        raise _invalid("UNSTABLE_DATABASE_METADATA", database) from exc
    if (root_after.st_dev, root_after.st_ino) != (
        root_before.st_dev,
        root_before.st_ino,
    ):
        raise _invalid("UNSTABLE_DATABASE_METADATA", database)
    return DatabaseInfo(
        path=database,
        source_root=source_root,
        fingerprint=fingerprint,
        canonical_device=root_after.st_dev,
        canonical_inode=root_after.st_ino,
    )


def _execution_error(stage: str, reason: str) -> AnalyzerError:
    """Return a fixed, path-free fail-closed execution snapshot error."""

    return AnalyzerError(
        "CODEQL_EXECUTION_SNAPSHOT_FAILED",
        "Private CodeQL execution database snapshot failed.",
        {"stage": stage, "reason": reason},
    )


def _same_database_identity(actual: DatabaseInfo, expected: DatabaseInfo) -> bool:
    return (
        actual.fingerprint == expected.fingerprint
        and actual.source_root == expected.source_root
    )


def _same_canonical_identity(actual: DatabaseInfo, expected: DatabaseInfo) -> bool:
    same = _same_database_identity(actual, expected) and actual.path == expected.path
    if expected.canonical_device is not None:
        same = same and actual.canonical_device == expected.canonical_device
    if expected.canonical_inode is not None:
        same = same and actual.canonical_inode == expected.canonical_inode
    return same


def _require_canonical_tree_binding(
    database: DatabaseInfo,
    root: os.stat_result,
) -> None:
    """Bind descriptor-validated canonical root back to its attested inode."""

    if database.canonical_device is not None and root.st_dev != database.canonical_device:
        raise ValueError("canonical database device changed")
    if database.canonical_inode is not None and root.st_ino != database.canonical_inode:
        raise ValueError("canonical database inode changed")


def _tree_root_identity(
    path: Path,
    close_capability: CloseRangeCapability | None = None,
) -> os.stat_result:
    if close_capability is None:
        close_capability = require_close_fd_once()
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ValueError("tree root is not a real directory")
    descriptor_owner: list[int] = []
    descriptor_release = DeferredCloseFdOnceOutcome()
    try:
        descriptor = open_owned_descriptor(
            descriptor_owner,
            path,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
    finally:
        try:
            _release_database_descriptor_owner_must_reach(
                descriptor_owner,
                close_capability,
                descriptor_release,
            )
        finally:
            _release_database_descriptor_owner_must_reach(
                descriptor_owner,
                close_capability,
                descriptor_release,
            )
    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
        raise ValueError("tree root changed during validation")
    return info


def _reject_symlink_components(path: Path) -> None:
    absolute = path.expanduser().absolute()
    components = [absolute, *absolute.parents]
    for component in reversed(components):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("path contains a symlink component")


def _validate_safe_tree(
    path: Path,
    *,
    require_owner: bool,
    require_unaliased_regular_files: bool = False,
    close_capability: CloseRangeCapability | None = None,
) -> os.stat_result:
    """Reject links/special files and observable inode swaps without following links."""

    if close_capability is None:
        close_capability = require_close_fd_once()
    _reject_symlink_components(path)
    root_info = _tree_root_identity(path, close_capability)
    current_uid = os.getuid()
    seen = [0]

    def signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    def validate_directory(
        descriptor: int,
        expected: os.stat_result,
        depth: int,
    ) -> None:
        if depth > _MAX_EXECUTION_TREE_DEPTH:
            raise ValueError("tree exceeds depth bound")
        opened_directory = os.fstat(descriptor)
        if not stat.S_ISDIR(opened_directory.st_mode) or signature(
            opened_directory
        ) != signature(expected):
            raise ValueError("directory changed during validation")
        if require_owner and opened_directory.st_uid != current_uid:
            raise ValueError("tree entry has a foreign owner")
        with os.scandir(descriptor) as entries:
            for entry in entries:
                seen[0] += 1
                if seen[0] > _MAX_EXECUTION_TREE_ENTRIES:
                    raise ValueError("tree exceeds validation bound")
                name = entry.name
                before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if require_owner and before.st_uid != current_uid:
                    raise ValueError("tree entry has a foreign owner")
                if stat.S_ISREG(before.st_mode):
                    if require_unaliased_regular_files and before.st_nlink != 1:
                        raise ValueError("tree regular file has a hardlink alias")
                    child_owner: list[int] = []
                    child_release = DeferredCloseFdOnceOutcome()
                    try:
                        child = open_owned_descriptor(
                            child_owner,
                            name,
                            os.O_RDONLY
                            | os.O_NONBLOCK
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=descriptor,
                        )
                        opened = os.fstat(child)
                        if (
                            not stat.S_ISREG(opened.st_mode)
                            or signature(opened) != signature(before)
                            or (
                                require_unaliased_regular_files
                                and opened.st_nlink != 1
                            )
                        ):
                            raise ValueError("regular file changed during validation")
                    finally:
                        try:
                            _release_database_descriptor_owner_must_reach(
                                child_owner,
                                close_capability,
                                child_release,
                            )
                        finally:
                            _release_database_descriptor_owner_must_reach(
                                child_owner,
                                close_capability,
                                child_release,
                            )
                elif stat.S_ISDIR(before.st_mode):
                    child_owner = []
                    child_release = DeferredCloseFdOnceOutcome()
                    try:
                        child = open_owned_descriptor(
                            child_owner,
                            name,
                            os.O_RDONLY
                            | os.O_DIRECTORY
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=descriptor,
                        )
                        validate_directory(child, before, depth + 1)
                    finally:
                        try:
                            _release_database_descriptor_owner_must_reach(
                                child_owner,
                                close_capability,
                                child_release,
                            )
                        finally:
                            _release_database_descriptor_owner_must_reach(
                                child_owner,
                                close_capability,
                                child_release,
                            )
                else:
                    raise ValueError("tree contains a link or special file")
                after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if signature(after) != signature(before) or (
                    require_unaliased_regular_files
                    and stat.S_ISREG(after.st_mode)
                    and after.st_nlink != 1
                ):
                    raise ValueError("tree entry changed during validation")
        if signature(os.fstat(descriptor)) != signature(expected):
            raise ValueError("directory changed during validation")

    root_owner: list[int] = []
    root_release = DeferredCloseFdOnceOutcome()
    try:
        root_descriptor = open_owned_descriptor(
            root_owner,
            path,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        validate_directory(root_descriptor, root_info, 0)
    finally:
        try:
            _release_database_descriptor_owner_must_reach(
                root_owner,
                close_capability,
                root_release,
            )
        finally:
            _release_database_descriptor_owner_must_reach(
                root_owner,
                close_capability,
                root_release,
            )
    after = path.lstat()
    if signature(after) != signature(root_info):
        raise ValueError("tree root changed during validation")
    return root_info


def _assert_private_binding(binding: ExecutionDatabaseBinding) -> None:
    parent = os.fstat(binding.parent_descriptor)
    lexical_parent = _tree_root_identity(
        binding.parent_path,
        binding.close_capability,
    )
    expected_parent = (
        binding.parent_device,
        binding.parent_inode,
        binding.parent_uid,
    )
    if (
        not stat.S_ISDIR(parent.st_mode)
        or (parent.st_dev, parent.st_ino, parent.st_uid) != expected_parent
        or (
            lexical_parent.st_dev,
            lexical_parent.st_ino,
            lexical_parent.st_uid,
        )
        != expected_parent
    ):
        raise ValueError("execution snapshot parent binding changed")
    info = _validate_safe_tree(
        binding.path,
        require_owner=True,
        require_unaliased_regular_files=True,
        close_capability=binding.close_capability,
    )
    descriptor_bound = os.stat(
        binding.path.name,
        dir_fd=binding.parent_descriptor,
        follow_symlinks=False,
    )
    if (
        (info.st_dev, info.st_ino) != (binding.device, binding.inode)
        or (descriptor_bound.st_dev, descriptor_bound.st_ino)
        != (binding.device, binding.inode)
        or info.st_uid != binding.uid
        or stat.S_IMODE(info.st_mode) != 0o700
        or binding.uid != os.getuid()
    ):
        raise ValueError("execution snapshot root binding changed")


def _reflink_file(
    source_directory: int,
    destination_directory: int,
    name: str,
    expected: os.stat_result,
    close_capability: CloseRangeCapability,
) -> None:
    source_owner: list[int] = []
    source_release = DeferredCloseFdOnceOutcome()
    destination_owner: list[int] = []
    destination_release = DeferredCloseFdOnceOutcome()
    try:
        source_descriptor = open_owned_descriptor(
            source_owner,
            name,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=source_directory,
        )
        current = os.fstat(source_descriptor)
        if (
            not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino)
        ):
            raise OSError("source file changed before reflink")
        destination_descriptor = open_owned_descriptor(
            destination_owner,
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=destination_directory,
        )
        fcntl.ioctl(destination_descriptor, _FICLONE, source_descriptor)
        os.fchmod(destination_descriptor, stat.S_IMODE(current.st_mode))
        after = os.fstat(source_descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
        ):
            raise OSError("source file changed during reflink")
    finally:
        try:
            try:
                _release_database_descriptor_owner_must_reach(
                    destination_owner,
                    close_capability,
                    destination_release,
                )
            finally:
                _release_database_descriptor_owner_must_reach(
                    destination_owner,
                    close_capability,
                    destination_release,
                )
        finally:
            try:
                _release_database_descriptor_owner_must_reach(
                    source_owner,
                    close_capability,
                    source_release,
                )
            finally:
                _release_database_descriptor_owner_must_reach(
                    source_owner,
                    close_capability,
                    source_release,
                )


def _reflink_clone_tree(
    source: Path,
    destination: Path,
    *,
    destination_descriptor: int | None = None,
    expected_destination_root: os.stat_result | None = None,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    """Clone a validated tree using FICLONE only; never fall back to byte copying."""

    if close_capability is None:
        close_capability = require_close_fd_once()
    source_root = _tree_root_identity(source, close_capability)
    owns_destination_descriptor = destination_descriptor is None
    destination_root = (
        _tree_root_identity(destination, close_capability)
        if expected_destination_root is None
        else expected_destination_root
    )
    current_uid = os.getuid()
    if source_root.st_uid != current_uid or destination_root.st_uid != current_uid:
        raise OSError("clone roots have a foreign owner")
    seen = [0]

    def signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    def clone_directory(
        source_descriptor: int,
        destination_descriptor: int,
        expected: os.stat_result,
        depth: int,
    ) -> None:
        if depth > _MAX_EXECUTION_TREE_DEPTH:
            raise OSError("tree exceeds clone depth bound")
        opened = os.fstat(source_descriptor)
        if not stat.S_ISDIR(opened.st_mode) or signature(opened) != signature(expected):
            raise OSError("source directory changed during clone")
        if opened.st_uid != current_uid:
            raise OSError("source directory has a foreign owner")
        with os.scandir(source_descriptor) as entries:
            for entry in entries:
                seen[0] += 1
                if seen[0] > _MAX_EXECUTION_TREE_ENTRIES:
                    raise OSError("tree exceeds clone bound")
                name = entry.name
                source_info = os.stat(
                    name,
                    dir_fd=source_descriptor,
                    follow_symlinks=False,
                )
                if source_info.st_uid != current_uid:
                    raise OSError("source tree entry has a foreign owner")
                if stat.S_ISDIR(source_info.st_mode):
                    os.mkdir(name, mode=0o700, dir_fd=destination_descriptor)
                    source_child_owner: list[int] = []
                    source_child_release = DeferredCloseFdOnceOutcome()
                    destination_child_owner: list[int] = []
                    destination_child_release = DeferredCloseFdOnceOutcome()
                    try:
                        source_child = open_owned_descriptor(
                            source_child_owner,
                            name,
                            os.O_RDONLY
                            | os.O_DIRECTORY
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=source_descriptor,
                        )
                        destination_child = open_owned_descriptor(
                            destination_child_owner,
                            name,
                            os.O_RDONLY
                            | os.O_DIRECTORY
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=destination_descriptor,
                        )
                        os.fchmod(destination_child, stat.S_IMODE(source_info.st_mode))
                        clone_directory(
                            source_child,
                            destination_child,
                            source_info,
                            depth + 1,
                        )
                    finally:
                        try:
                            try:
                                _release_database_descriptor_owner_must_reach(
                                    destination_child_owner,
                                    close_capability,
                                    destination_child_release,
                                )
                            finally:
                                _release_database_descriptor_owner_must_reach(
                                    destination_child_owner,
                                    close_capability,
                                    destination_child_release,
                                )
                        finally:
                            try:
                                _release_database_descriptor_owner_must_reach(
                                    source_child_owner,
                                    close_capability,
                                    source_child_release,
                                )
                            finally:
                                _release_database_descriptor_owner_must_reach(
                                    source_child_owner,
                                    close_capability,
                                    source_child_release,
                                )
                elif stat.S_ISREG(source_info.st_mode):
                    _reflink_file(
                        source_descriptor,
                        destination_descriptor,
                        name,
                        source_info,
                        close_capability,
                    )
                else:
                    raise OSError("source tree contains a link or special file")
                source_after = os.stat(
                    name,
                    dir_fd=source_descriptor,
                    follow_symlinks=False,
                )
                if signature(source_after) != signature(source_info):
                    raise OSError("source tree changed during clone")
        if signature(os.fstat(source_descriptor)) != signature(expected):
            raise OSError("source directory changed during clone")

    source_owner: list[int] = []
    source_release = DeferredCloseFdOnceOutcome()
    destination_owner: list[int] = []
    destination_release = DeferredCloseFdOnceOutcome()
    try:
        source_descriptor = open_owned_descriptor(
            source_owner,
            source,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        if destination_descriptor is None:
            destination_descriptor = open_owned_descriptor(
                destination_owner,
                destination,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
        opened_destination = os.fstat(destination_descriptor)
        if (
            not stat.S_ISDIR(opened_destination.st_mode)
            or (opened_destination.st_dev, opened_destination.st_ino)
            != (destination_root.st_dev, destination_root.st_ino)
            or opened_destination.st_uid != current_uid
        ):
            raise OSError("clone destination root changed before clone")
        clone_directory(
            source_descriptor,
            destination_descriptor,
            source_root,
            0,
        )
        after_destination = os.fstat(destination_descriptor)
    finally:
        try:
            if owns_destination_descriptor:
                try:
                    _release_database_descriptor_owner_must_reach(
                        destination_owner,
                        close_capability,
                        destination_release,
                    )
                finally:
                    _release_database_descriptor_owner_must_reach(
                        destination_owner,
                        close_capability,
                        destination_release,
                    )
        finally:
            try:
                _release_database_descriptor_owner_must_reach(
                    source_owner,
                    close_capability,
                    source_release,
                )
            finally:
                _release_database_descriptor_owner_must_reach(
                    source_owner,
                    close_capability,
                    source_release,
                )
    after_source = source.lstat()
    if signature(after_source) != signature(source_root) or (
        after_destination.st_dev,
        after_destination.st_ino,
    ) != (
        destination_root.st_dev,
        destination_root.st_ino,
    ):
        raise OSError("clone root changed during clone")


def _remove_private_tree_at(
    parent_descriptor: int,
    name: str,
    *,
    expected: ExecutionDatabaseBinding | None = None,
    expected_root: os.stat_result | None = None,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    """Quarantine and delete one private tree through one pinned parent fd."""

    if close_capability is None:
        close_capability = (
            expected.close_capability
            if expected is not None
            else require_close_fd_once()
        )
    parent = os.fstat(parent_descriptor)
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid():
        raise ValueError("snapshot parent binding is unsafe")
    if expected is not None and (
        parent.st_dev,
        parent.st_ino,
        parent.st_uid,
    ) != (
        expected.parent_device,
        expected.parent_inode,
        expected.parent_uid,
    ):
        raise ValueError("snapshot parent binding changed")
    root = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    if expected_root is not None and (
        root.st_dev,
        root.st_ino,
        root.st_uid,
        root.st_mode,
    ) != (
        expected_root.st_dev,
        expected_root.st_ino,
        expected_root.st_uid,
        expected_root.st_mode,
    ):
        raise ValueError("snapshot root changed after stale scan")
    if (
        not stat.S_ISDIR(root.st_mode)
        or root.st_uid != os.getuid()
        or stat.S_IMODE(root.st_mode) != 0o700
    ):
        raise ValueError("snapshot root is unsafe")
    if expected is not None and (root.st_dev, root.st_ino) != (
        expected.device,
        expected.inode,
    ):
        raise ValueError("snapshot root binding changed")
    budget = [0]

    def same_inode(left: os.stat_result, right: os.stat_result) -> bool:
        return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)

    def same_private_root(
        current: os.stat_result,
        reference: os.stat_result,
    ) -> bool:
        return (
            current.st_dev,
            current.st_ino,
            current.st_uid,
            current.st_mode,
        ) == (
            reference.st_dev,
            reference.st_ino,
            reference.st_uid,
            reference.st_mode,
        ) and (
            stat.S_ISDIR(current.st_mode)
            and current.st_uid == os.getuid()
            and stat.S_IMODE(current.st_mode) == 0o700
        )

    def remove_contents(descriptor: int, depth: int) -> None:
        if depth > _MAX_EXECUTION_TREE_DEPTH:
            raise ValueError("cleanup exceeds depth bound")
        with os.scandir(descriptor) as entries:
            for entry in entries:
                budget[0] += 1
                if budget[0] > _MAX_EXECUTION_TREE_ENTRIES:
                    raise ValueError("cleanup exceeds bound")
                name = entry.name
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if info.st_uid != os.getuid():
                    raise ValueError("unsafe cleanup owner")
                if stat.S_ISREG(info.st_mode):
                    child_owner: list[int] = []
                    child_release = DeferredCloseFdOnceOutcome()
                    try:
                        child = open_owned_descriptor(
                            child_owner,
                            name,
                            os.O_RDONLY
                            | os.O_NONBLOCK
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=descriptor,
                        )
                        opened = os.fstat(child)
                        if not stat.S_ISREG(opened.st_mode) or not same_inode(
                            opened, info
                        ):
                            raise ValueError("cleanup file changed")
                        current = os.stat(
                            name, dir_fd=descriptor, follow_symlinks=False
                        )
                        if not same_inode(current, opened):
                            raise ValueError("cleanup file changed")
                        before_links = opened.st_nlink
                        os.unlink(name, dir_fd=descriptor)
                        after = os.fstat(child)
                        if not same_inode(after, opened) or after.st_nlink != max(
                            before_links - 1, 0
                        ):
                            raise ValueError("cleanup file unlink was not bound")
                    finally:
                        try:
                            _release_database_descriptor_owner_must_reach(
                                child_owner,
                                close_capability,
                                child_release,
                            )
                        finally:
                            _release_database_descriptor_owner_must_reach(
                                child_owner,
                                close_capability,
                                child_release,
                            )
                    continue
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError("unsafe cleanup entry")
                child_owner = []
                child_release = DeferredCloseFdOnceOutcome()
                try:
                    child = open_owned_descriptor(
                        child_owner,
                        name,
                        os.O_RDONLY
                        | os.O_DIRECTORY
                        | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=descriptor,
                    )
                    opened = os.fstat(child)
                    if not stat.S_ISDIR(opened.st_mode) or not same_inode(opened, info):
                        raise ValueError("cleanup directory changed")
                    remove_contents(child, depth + 1)
                    current = os.stat(
                        name, dir_fd=descriptor, follow_symlinks=False
                    )
                    if not same_inode(current, opened):
                        raise ValueError("cleanup directory changed")
                    os.rmdir(name, dir_fd=descriptor)
                    after = os.fstat(child)
                    if not same_inode(after, opened) or after.st_nlink != 0:
                        raise ValueError("cleanup directory removal was not bound")
                finally:
                    try:
                        _release_database_descriptor_owner_must_reach(
                            child_owner,
                            close_capability,
                            child_release,
                        )
                    finally:
                        _release_database_descriptor_owner_must_reach(
                            child_owner,
                            close_capability,
                            child_release,
                        )

    root_owner: list[int] = []
    root_release = DeferredCloseFdOnceOutcome()
    quarantine_name = f"{name}.quarantine-{secrets.token_hex(16)}"
    try:
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not same_inode(before, root):
            raise ValueError("snapshot root changed before quarantine")
        root_descriptor = open_owned_descriptor(
            root_owner,
            name,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        opened_root = os.fstat(root_descriptor)
        if not same_private_root(opened_root, root):
            raise ValueError("snapshot root changed before quarantine")
        renameat2_no_replace(
            parent_descriptor,
            name,
            parent_descriptor,
            quarantine_name,
        )
        quarantined = os.stat(
            quarantine_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        pinned_root = os.fstat(root_descriptor)
        if not same_private_root(pinned_root, opened_root) or not same_private_root(
            quarantined,
            opened_root,
        ):
            raise ValueError("snapshot quarantine binding changed")
        remove_contents(root_descriptor, 0)
        current = os.stat(
            quarantine_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        pinned_root = os.fstat(root_descriptor)
        if not same_private_root(current, opened_root) or not same_private_root(
            pinned_root,
            opened_root,
        ):
            raise ValueError("snapshot root changed during cleanup")
        os.rmdir(quarantine_name, dir_fd=parent_descriptor)
        after = os.fstat(root_descriptor)
        if not same_private_root(after, opened_root) or after.st_nlink != 0:
            raise ValueError("snapshot root removal was not bound")
        os.fsync(parent_descriptor)
        try:
            os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise ValueError("snapshot root name was recreated during cleanup")
    finally:
        try:
            _release_database_descriptor_owner_must_reach(
                root_owner,
                close_capability,
                root_release,
            )
        finally:
            _release_database_descriptor_owner_must_reach(
                root_owner,
                close_capability,
                root_release,
            )


def _remove_private_tree(
    path: Path,
    *,
    expected: ExecutionDatabaseBinding | None = None,
    parent_descriptor: int | None = None,
    close_capability: CloseRangeCapability | None = None,
) -> None:
    """Remove a private tree without reopening a supplied bound parent."""

    if close_capability is None:
        close_capability = (
            expected.close_capability
            if expected is not None
            else require_close_fd_once()
        )
    owns_parent_descriptor = parent_descriptor is None
    parent_owner: list[int] = []
    parent_release = DeferredCloseFdOnceOutcome()
    if parent_descriptor is None:
        _reject_symlink_components(path.parent)
        parent_info = _tree_root_identity(path.parent, close_capability)
    try:
        if parent_descriptor is None:
            parent_descriptor = open_owned_descriptor(
                parent_owner,
                path.parent,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
            opened_parent = os.fstat(parent_descriptor)
            if (opened_parent.st_dev, opened_parent.st_ino) != (
                parent_info.st_dev,
                parent_info.st_ino,
            ):
                raise ValueError("snapshot parent changed before cleanup")
        _remove_private_tree_at(
            parent_descriptor,
            path.name,
            expected=expected,
            close_capability=close_capability,
        )
    finally:
        if owns_parent_descriptor:
            try:
                _release_database_descriptor_owner_must_reach(
                    parent_owner,
                    close_capability,
                    parent_release,
                )
            finally:
                _release_database_descriptor_owner_must_reach(
                    parent_owner,
                    close_capability,
                    parent_release,
                )


def _cleanup_stale_execution_database_snapshots_at(
    output_descriptor: int,
    output_info: os.stat_result,
    close_capability: CloseRangeCapability,
) -> None:
    opened = os.fstat(output_descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.getuid()
        or (opened.st_dev, opened.st_ino)
        != (output_info.st_dev, output_info.st_ino)
    ):
        raise ValueError("output root changed during stale scan")
    candidates: list[tuple[str, os.stat_result]] = []
    seen = 0
    with os.scandir(output_descriptor) as entries:
        for entry in entries:
            seen += 1
            if seen > _MAX_EXECUTION_TREE_ENTRIES:
                raise ValueError("stale scan exceeds bound")
            if entry.name.startswith(_EXECUTION_PREFIX):
                candidate_info = os.stat(
                    entry.name,
                    dir_fd=output_descriptor,
                    follow_symlinks=False,
                )
                candidates.append((entry.name, candidate_info))
                if len(candidates) > 64:
                    raise ValueError("too many stale snapshots")
    for candidate, candidate_info in candidates:
        _remove_private_tree_at(
            output_descriptor,
            candidate,
            expected_root=candidate_info,
            close_capability=close_capability,
        )


def cleanup_stale_execution_database_snapshots(
    output_root: Path | str,
    *,
    _output_descriptor: int | None = None,
    _output_info: os.stat_result | None = None,
    _close_capability: CloseRangeCapability | None = None,
) -> None:
    output = Path(output_root)
    close_capability = _close_capability or require_close_fd_once()
    owns_output_descriptor = _output_descriptor is None
    output_descriptor = -1 if _output_descriptor is None else _output_descriptor
    output_owner: list[int] = []
    output_release = DeferredCloseFdOnceOutcome()
    try:
        output_info = _output_info or _tree_root_identity(
            output,
            close_capability,
        )
        if output_info.st_uid != os.getuid():
            raise ValueError("output root has a foreign owner")
        if output_descriptor < 0:
            output_descriptor = open_owned_descriptor(
                output_owner,
                output,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
        try:
            _cleanup_stale_execution_database_snapshots_at(
                output_descriptor,
                output_info,
                close_capability,
            )
        finally:
            if owns_output_descriptor:
                try:
                    _release_database_descriptor_owner_must_reach(
                        output_owner,
                        close_capability,
                        output_release,
                    )
                finally:
                    _release_database_descriptor_owner_must_reach(
                        output_owner,
                        close_capability,
                        output_release,
                    )
    except (OSError, ValueError, MemoryError) as exc:
        raise _execution_error("stale_cleanup", "UNSAFE_OR_UNREMOVABLE") from exc


def _remove_execution_snapshot_if_present(
    path: Path | None,
    *,
    expected: ExecutionDatabaseBinding | None,
    expected_root: os.stat_result | None,
    parent_descriptor: int,
    close_capability: CloseRangeCapability,
) -> None:
    """Idempotently remove the exact still-named private snapshot root."""

    if path is None:
        return
    try:
        current = os.stat(
            path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if expected is not None:
        expected_identity = (
            expected.device,
            expected.inode,
            expected.uid,
        )
        current_identity = (
            current.st_dev,
            current.st_ino,
            current.st_uid,
        )
        if current_identity != expected_identity:
            raise ValueError("execution snapshot root binding changed")
    elif expected_root is not None and (
        current.st_dev,
        current.st_ino,
        current.st_uid,
        current.st_mode,
    ) != (
        expected_root.st_dev,
        expected_root.st_ino,
        expected_root.st_uid,
        expected_root.st_mode,
    ):
        raise ValueError("execution snapshot root binding changed")
    _remove_private_tree(
        path,
        expected=expected,
        parent_descriptor=parent_descriptor,
        close_capability=close_capability,
    )


def create_execution_database_snapshot(
    database: DatabaseInfo,
    output_root: Path | str,
    *,
    clone_tree: Callable[[Path, Path], None] | None = None,
    validate_database_fn: Callable[..., DatabaseInfo] = validate_database,
    owner_callback: Callable[[DatabaseInfo], None] | None = None,
) -> DatabaseInfo:
    """Create one private reflink execution DB while retaining canonical identity."""

    if not isinstance(database, DatabaseInfo) or database.execution is not None:
        raise _execution_error("validation", "CANONICAL_DATABASE_REQUIRED")
    output = Path(output_root)
    snapshot: Path | None = None
    snapshot_name: str | None = None
    snapshot_root: os.stat_result | None = None
    binding: ExecutionDatabaseBinding | None = None
    owned_database: DatabaseInfo | None = None
    parent_descriptor = -1
    snapshot_descriptor = -1
    parent_descriptor_owner: list[int] = []
    snapshot_descriptor_owner: list[int] = []
    close_capability: CloseRangeCapability | None = None
    parent_release: DeferredCloseFdOnceOutcome | None = None
    snapshot_release: DeferredCloseFdOnceOutcome | None = None
    factory_succeeded = False

    def commit_closed_if_consumed() -> None:
        if (
            binding is None
            or parent_release is None
            or not _database_descriptor_release_consumed(parent_release)
        ):
            return

        def commit_closed() -> None:
            binding.cleanup_state.closed = True

        try:
            run_with_deferred_interrupts(commit_closed)
        finally:
            run_with_deferred_interrupts(commit_closed)

    def cleanup_failed_factory() -> None:
        nonlocal parent_descriptor
        if factory_succeeded or parent_release is None:
            return
        if _database_descriptor_release_consumed(parent_release):
            commit_closed_if_consumed()
            return
        if close_capability is None:
            raise OSError("factory parent release capability is unavailable")
        owned_parent_descriptor = (
            parent_descriptor_owner[0]
            if parent_descriptor_owner
            and parent_descriptor_owner[0] >= 0
            else (
                binding.parent_descriptor
                if binding is not None
                else parent_descriptor
            )
        )
        cleanup_failure: BaseException | None = None
        binding_lock = binding.lock if binding is not None else nullcontext()
        with binding_lock:
            try:
                if snapshot_release is not None:
                    try:
                        _release_database_descriptor_owner_must_reach(
                            snapshot_descriptor_owner,
                            close_capability,
                            snapshot_release,
                        )
                    finally:
                        _release_database_descriptor_owner_must_reach(
                            snapshot_descriptor_owner,
                            close_capability,
                            snapshot_release,
                        )
            finally:
                try:
                    if owned_parent_descriptor >= 0:
                        try:
                            _remove_execution_snapshot_if_present(
                                snapshot,
                                expected=binding,
                                expected_root=snapshot_root,
                                parent_descriptor=owned_parent_descriptor,
                                close_capability=close_capability,
                            )
                        except BaseException as cleanup_exc:
                            cleanup_failure = cleanup_exc
                finally:
                    try:
                        if parent_descriptor_owner:
                            try:
                                _release_database_descriptor_owner_must_reach(
                                    parent_descriptor_owner,
                                    close_capability,
                                    parent_release,
                                )
                            finally:
                                _release_database_descriptor_owner_must_reach(
                                    parent_descriptor_owner,
                                    close_capability,
                                    parent_release,
                                )
                            parent_descriptor = -1
                        elif (
                            binding is not None
                            and parent_release.status is None
                        ):
                            try:
                                _release_database_descriptor_must_reach(
                                    binding.parent_descriptor,
                                    close_capability,
                                    parent_release,
                                )
                            finally:
                                _release_database_descriptor_must_reach(
                                    binding.parent_descriptor,
                                    close_capability,
                                    parent_release,
                                )
                            parent_descriptor = -1
                    finally:
                        commit_closed_if_consumed()
        if cleanup_failure is not None:
            raise _execution_error(
                "cleanup", "UNSAFE_OR_UNREMOVABLE"
            ) from cleanup_failure

    def complete_factory_success() -> DatabaseInfo:
        if owned_database is None:
            raise OSError("execution snapshot ownership is unavailable")
        _transfer_database_descriptor_owner(
            parent_descriptor_owner,
            parent_descriptor,
        )
        return owned_database

    try:
        try:
            output.mkdir(parents=True, exist_ok=True)
            output = output.resolve(strict=True)
            _reject_symlink_components(output)
            close_capability = require_close_fd_once()
            parent_release = DeferredCloseFdOnceOutcome()
            snapshot_release = DeferredCloseFdOnceOutcome()
            parent_descriptor = open_owned_descriptor(
                parent_descriptor_owner,
                output,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
            opened_parent = os.fstat(parent_descriptor)
            lexical_parent = output.lstat()
            if (
                not stat.S_ISDIR(opened_parent.st_mode)
                or opened_parent.st_uid != os.getuid()
                or stat.S_ISLNK(lexical_parent.st_mode)
                or not stat.S_ISDIR(lexical_parent.st_mode)
                or (
                    opened_parent.st_dev,
                    opened_parent.st_ino,
                    opened_parent.st_uid,
                    opened_parent.st_mode,
                )
                != (
                    lexical_parent.st_dev,
                    lexical_parent.st_ino,
                    lexical_parent.st_uid,
                    lexical_parent.st_mode,
                )
            ):
                raise ValueError("output root changed before snapshot creation")
            output_info = opened_parent
            canonical_before = validate_database_fn(database.path)
            if (
                not isinstance(canonical_before, DatabaseInfo)
                or not _same_canonical_identity(canonical_before, database)
            ):
                raise ValueError("canonical database changed before clone")
            _require_canonical_tree_binding(
                database,
                _validate_safe_tree(
                    database.path,
                    require_owner=True,
                    close_capability=close_capability,
                ),
            )
            cleanup_stale_execution_database_snapshots(
                output,
                _output_descriptor=parent_descriptor,
                _output_info=output_info,
                _close_capability=close_capability,
            )
            for _ in range(128):
                candidate = f"{_EXECUTION_PREFIX}{secrets.token_hex(16)}"
                try:
                    os.mkdir(candidate, mode=0o700, dir_fd=parent_descriptor)
                except FileExistsError:
                    continue
                snapshot_name = candidate
                break
            if snapshot_name is None:
                raise OSError("could not allocate execution snapshot directory")
            snapshot = output / snapshot_name
            snapshot_descriptor = open_owned_descriptor(
                snapshot_descriptor_owner,
                snapshot_name,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
            try:
                snapshot_info = os.fstat(snapshot_descriptor)
                os.fchmod(snapshot_descriptor, 0o700)
                snapshot_info = os.fstat(snapshot_descriptor)
                snapshot_root = snapshot_info
                lexical_snapshot = _tree_root_identity(
                    snapshot, close_capability
                )
                if (lexical_snapshot.st_dev, lexical_snapshot.st_ino) != (
                    snapshot_info.st_dev,
                    snapshot_info.st_ino,
                ):
                    raise ValueError(
                        "execution snapshot parent changed during creation"
                    )
                binding = ExecutionDatabaseBinding(
                    path=snapshot,
                    device=snapshot_info.st_dev,
                    inode=snapshot_info.st_ino,
                    uid=os.getuid(),
                    source_root=database.source_root,
                    parent_path=output,
                    parent_device=opened_parent.st_dev,
                    parent_inode=opened_parent.st_ino,
                    parent_uid=opened_parent.st_uid,
                    parent_descriptor=parent_descriptor,
                    close_capability=close_capability,
                    parent_release=parent_release,
                )
                _assert_private_binding(binding)
                if clone_tree is None:
                    _reflink_clone_tree(
                        database.path,
                        snapshot,
                        destination_descriptor=snapshot_descriptor,
                        expected_destination_root=snapshot_info,
                        close_capability=close_capability,
                    )
                else:
                    clone_tree(database.path, snapshot)
            finally:
                try:
                    _release_database_descriptor_owner_must_reach(
                        snapshot_descriptor_owner,
                        close_capability,
                        snapshot_release,
                    )
                finally:
                    _release_database_descriptor_owner_must_reach(
                        snapshot_descriptor_owner,
                        close_capability,
                        snapshot_release,
                    )
            _assert_private_binding(binding)
            snapshot_database = validate_database_fn(snapshot)
            if (
                not isinstance(snapshot_database, DatabaseInfo)
                or not _same_database_identity(snapshot_database, database)
            ):
                raise ValueError(
                    "execution snapshot does not match canonical database"
                )
            canonical_after = validate_database_fn(database.path)
            if (
                not isinstance(canonical_after, DatabaseInfo)
                or not _same_canonical_identity(canonical_after, database)
            ):
                raise ValueError("canonical database changed during clone")
            _require_canonical_tree_binding(
                database,
                _validate_safe_tree(
                    database.path,
                    require_owner=True,
                    close_capability=close_capability,
                ),
            )
            owned_database = replace(database, execution=binding)
            ownership_finalizer = weakref.finalize(
                owned_database,
                _cleanup_execution_database_binding_finalizer,
                binding,
            )
            ownership_finalizer.atexit = False
            if owner_callback is not None:
                owner_callback(owned_database)
            try:
                completed_database = run_with_deferred_interrupts(
                    complete_factory_success
                )
                factory_succeeded = True
                return completed_database
            except BaseException:
                raise
        except BaseException as exc:
            if (
                isinstance(exc, AnalyzerError)
                and exc.code == "CODEQL_EXECUTION_SNAPSHOT_FAILED"
                and exc.details.get("stage") == "stale_cleanup"
            ):
                raise
            if isinstance(
                exc,
                (AnalyzerError, OSError, ValueError, TypeError, MemoryError),
            ):
                raise _execution_error(
                    "clone", "REFLINK_OR_VALIDATION_FAILED"
                ) from exc
            raise
    finally:
        try:
            cleanup_failed_factory()
        finally:
            cleanup_failed_factory()


def validate_execution_database(
    database: DatabaseInfo,
    *,
    require_initial_fingerprint: bool = False,
    validate_database_fn: Callable[..., DatabaseInfo] = validate_database,
    deadline: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    binding = database.execution if isinstance(database, DatabaseInfo) else None
    if binding is None:
        raise _execution_error("validation", "EXECUTION_BINDING_REQUIRED")
    try:
        _assert_private_binding(binding)
        actual = validate_database_fn(
            binding.path,
            deadline=deadline,
            monotonic=monotonic,
        )
        if not isinstance(actual, DatabaseInfo) or actual.source_root != database.source_root:
            raise ValueError("execution source provenance changed")
        if require_initial_fingerprint and actual.fingerprint != database.fingerprint:
            raise ValueError("execution snapshot fingerprint mismatch")
        _assert_private_binding(binding)
    except TimeoutError:
        raise
    except AnalyzerError as exc:
        raise _execution_error("validation", "EXECUTION_DATABASE_INVALID") from exc
    except (OSError, ValueError, TypeError, MemoryError) as exc:
        raise _execution_error("validation", "EXECUTION_DATABASE_INVALID") from exc


def validate_canonical_database(
    database: DatabaseInfo,
    *,
    actual_database: DatabaseInfo | None = None,
    validate_database_fn: Callable[..., DatabaseInfo] = validate_database,
    deadline: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    close_capability = require_close_fd_once()
    try:
        actual = actual_database
        if actual is None:
            actual = validate_database_fn(
                database.path,
                deadline=deadline,
                monotonic=monotonic,
            )
        if not isinstance(actual, DatabaseInfo) or not _same_canonical_identity(
            actual, database
        ):
            raise ValueError("canonical database identity changed")
        _require_canonical_tree_binding(
            database,
            _validate_safe_tree(
                database.path,
                require_owner=True,
                close_capability=close_capability,
            ),
        )
    except TimeoutError:
        raise
    except AnalyzerError as exc:
        raise _execution_error("canonical_validation", "CANONICAL_DATABASE_CHANGED") from exc
    except (OSError, ValueError, TypeError, MemoryError) as exc:
        raise _execution_error("canonical_validation", "CANONICAL_DATABASE_CHANGED") from exc


def _cleanup_execution_database_binding_must_reach(
    binding: ExecutionDatabaseBinding,
) -> None:
    def commit_closed_if_consumed() -> None:
        if not _database_descriptor_release_consumed(binding.parent_release):
            return

        def commit_closed() -> None:
            binding.cleanup_state.closed = True

        try:
            run_with_deferred_interrupts(commit_closed)
        finally:
            run_with_deferred_interrupts(commit_closed)

    if _database_descriptor_release_consumed(binding.parent_release):
        commit_closed_if_consumed()
        return
    cleanup_failure: BaseException | None = None
    with binding.lock:
        if _database_descriptor_release_consumed(binding.parent_release):
            commit_closed_if_consumed()
            return
        try:
            try:
                _remove_execution_snapshot_if_present(
                    binding.path,
                    expected=binding,
                    expected_root=None,
                    parent_descriptor=binding.parent_descriptor,
                    close_capability=binding.close_capability,
                )
            except BaseException as exc:
                cleanup_failure = exc
        finally:
            try:
                try:
                    _release_database_descriptor_must_reach(
                        binding.parent_descriptor,
                        binding.close_capability,
                        binding.parent_release,
                    )
                finally:
                    _release_database_descriptor_must_reach(
                        binding.parent_descriptor,
                        binding.close_capability,
                        binding.parent_release,
                    )
            finally:
                commit_closed_if_consumed()
    if cleanup_failure is not None:
        if isinstance(cleanup_failure, (OSError, ValueError, MemoryError)):
            raise _execution_error(
                "cleanup", "UNSAFE_OR_UNREMOVABLE"
            ) from cleanup_failure
        raise cleanup_failure


def _cleanup_execution_database_binding_finalizer(
    binding: ExecutionDatabaseBinding,
) -> None:
    """Best-effort non-cyclic GC owner for an unreturned database binding."""

    try:
        try:
            _cleanup_execution_database_binding_must_reach(binding)
        finally:
            _cleanup_execution_database_binding_must_reach(binding)
    except BaseException:
        # weakref callbacks cannot propagate; explicit/formal owners retain the
        # authoritative error channel and use the same idempotent binding.
        pass


def _cleanup_execution_database_snapshot(database: DatabaseInfo) -> None:
    try:
        binding = database.execution if isinstance(database, DatabaseInfo) else None
        if binding is None:
            return
        if not isinstance(binding, ExecutionDatabaseBinding):
            raise TypeError("execution database binding is invalid")
        _cleanup_execution_database_binding_must_reach(binding)
    finally:
        try:
            cleanup_binding = (
                database.execution
                if isinstance(database, DatabaseInfo)
                else None
            )
            if isinstance(cleanup_binding, ExecutionDatabaseBinding):
                _cleanup_execution_database_binding_must_reach(cleanup_binding)
        finally:
            fallback_binding = (
                database.execution
                if isinstance(database, DatabaseInfo)
                else None
            )
            if isinstance(fallback_binding, ExecutionDatabaseBinding):
                _cleanup_execution_database_binding_must_reach(
                    fallback_binding
                )


def cleanup_execution_database_snapshot(database: DatabaseInfo) -> None:
    try:
        _cleanup_execution_database_snapshot(database)
    finally:
        _cleanup_execution_database_snapshot(database)
