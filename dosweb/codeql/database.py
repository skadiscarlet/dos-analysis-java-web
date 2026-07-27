from __future__ import annotations

import hashlib
import math
import os
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.errors import AnalyzerError

_MAX_METADATA_BYTES: Final = 1024 * 1024
_MAX_METADATA_DEPTH: Final = 32
_MAX_METADATA_NODES: Final = 8192
_MAX_METADATA_FILES: Final = 8192
_MAX_METADATA_FILE_BYTES: Final = 256 * 1024 * 1024
_MUTABLE_NAMES: Final = frozenset({"log", "logs", "diagnostic", "diagnostics", "working"})


def _require_deadline(deadline: float | None, monotonic: Callable[[], float]) -> None:
    if deadline is not None and deadline - monotonic() <= 0:
        raise TimeoutError("database validation deadline exceeded")


@dataclass(frozen=True)
class DatabaseInfo:
    path: Path
    source_root: Path
    fingerprint: str


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


def _bounded_regular_bytes(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
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
        os.close(descriptor)


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


def _load_metadata(path: Path) -> dict[str, object]:
    try:
        raw = _bounded_regular_bytes(path, _MAX_METADATA_BYTES)
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
) -> tuple[int, str]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
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
        os.close(descriptor)


def _stable_metadata_manifest(
    database: Path,
    deadline: float | None,
    monotonic: Callable[[], float],
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
            size, digest = _bounded_file_hash(candidate, deadline, monotonic)
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
    try:
        database = supplied.resolve(strict=True)
        if not database.is_dir():
            raise ValueError("database is not a directory")
    except (OSError, ValueError) as exc:
        raise _invalid("DATABASE_DIRECTORY_REQUIRED", supplied) from exc

    metadata_path = database / "codeql-database.yml"
    java_database = database / "db-java"
    if not metadata_path.exists() or metadata_path.is_symlink():
        raise _invalid("METADATA_REQUIRED", metadata_path)
    if not java_database.is_dir() or java_database.is_symlink():
        raise _invalid("JAVA_DATABASE_REQUIRED", java_database)

    metadata = _load_metadata(metadata_path)
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
                "stable_files": _stable_metadata_manifest(database, deadline, monotonic),
            }
        )
    except (TypeError, ValueError, UnicodeEncodeError, MemoryError, RecursionError) as exc:
        raise _invalid("INVALID_METADATA", metadata_path) from exc
    return DatabaseInfo(path=database, source_root=source_root, fingerprint=fingerprint)
