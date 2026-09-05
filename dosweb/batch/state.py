"""Durable state primitives for the Java Web batch runner.

The state file is deliberately small and boring: it is a coordination record,
not an artifact manifest.  Every publication uses a same-directory temporary
file, fsync, replace, and a directory fsync so a killed worker cannot leave
half a JSON document behind.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterator

STATE_SCHEMA_VERSION = 1
_ALLOWED_BATCH_STATUSES = frozenset(
    {
        "pending",
        "running",
        "completed",
        "completed_with_gaps",
        "completed_with_failures",
        "interrupted",
    }
)
_ALLOWED_TARGET_STATES = frozenset(
    {"queued", "running", "retrying", "paused", "completed", "completed_with_gaps", "failed", "interrupted"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _reject_nonfinite(value: object) -> None:
    if isinstance(value, float):
        if not value.is_integer() or not (float("-1e308") < value < float("1e308")):
            raise ValueError("non-finite state value")
    elif isinstance(value, Mapping):
        for nested in value.values():
            _reject_nonfinite(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_nonfinite(nested)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path | str, document: Mapping[str, object]) -> None:
    """Publish a JSON object atomically and durably."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("state path must not be a symlink")
    _reject_nonfinite(document)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        _fsync_directory(destination.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def read_json(path: Path | str) -> dict[str, object]:
    source = Path(path)
    if source.is_symlink():
        raise ValueError("state path must not be a symlink")
    with source.open("r", encoding="utf-8") as stream:
        value = json.load(stream, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if not isinstance(value, dict):
        raise ValueError("state document must be an object")
    _reject_nonfinite(value)
    return value


@contextmanager
def batch_lock(path: Path | str, *, blocking: bool = True) -> Iterator[None]:
    """Take an inter-process exclusive lock for one batch output directory."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_symlink():
        raise ValueError("batch lock must not be a symlink")
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(descriptor, flags)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


# A class form is convenient for callers that want ``with BatchLock(path)``.
class BatchLock:
    def __init__(self, path: Path | str, *, blocking: bool = True) -> None:
        self.path = Path(path)
        self.blocking = blocking
        self._context = None

    def __enter__(self) -> None:
        self._context = batch_lock(self.path, blocking=self.blocking)
        return self._context.__enter__()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        assert self._context is not None
        return bool(self._context.__exit__(exc_type, exc, traceback))


class BatchState:
    """In-memory representation of a resumable batch state document."""

    def __init__(
        self,
        *,
        batch_id: str,
        mode: str,
        targets: Mapping[str, Mapping[str, object]] | None = None,
        status: str = "pending",
        created_at: str | None = None,
        updated_at: str | None = None,
        schema_version: int = STATE_SCHEMA_VERSION,
    ) -> None:
        if not isinstance(batch_id, str) or not batch_id:
            raise ValueError("batch_id is required")
        if mode not in {"entries", "full"}:
            raise ValueError("mode must be entries or full")
        if status not in _ALLOWED_BATCH_STATUSES:
            raise ValueError("status is invalid")
        if schema_version != STATE_SCHEMA_VERSION:
            raise ValueError("unsupported state schema version")
        self.schema_version = schema_version
        self.batch_id = batch_id
        self.mode = mode
        self.status = status
        self.created_at = created_at or _now()
        self.updated_at = updated_at or self.created_at
        self.targets: dict[str, dict[str, object]] = {
            str(key): dict(value) for key, value in (targets or {}).items()
        }

    @classmethod
    def new(cls, batch_id: str, mode: str, target_records: Mapping[str, Mapping[str, object]]) -> "BatchState":
        return cls(batch_id=batch_id, mode=mode, targets=target_records)

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> "BatchState":
        required = {
            "schema_version", "batch_id", "mode", "status", "created_at",
            "updated_at", "targets",
        }
        if set(document) != required or document.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError("unsupported or malformed batch state schema")
        targets = document.get("targets")
        status = document.get("status")
        if not isinstance(targets, Mapping) or status not in _ALLOWED_BATCH_STATUSES:
            raise ValueError("batch state fields are invalid")
        normalized: dict[str, dict[str, object]] = {}
        for key, value in targets.items():
            if not isinstance(key, str) or not key or not isinstance(value, Mapping):
                raise ValueError("state target record is invalid")
            record = dict(value)
            if record.get("target_id") != key or record.get("state") not in _ALLOWED_TARGET_STATES:
                raise ValueError("state target identity or state is invalid")
            attempt = record.get("attempt")
            if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
                raise ValueError("state target attempt is invalid")
            normalized[key] = record
        batch_id = document.get("batch_id")
        mode = document.get("mode")
        created_at = document.get("created_at")
        updated_at = document.get("updated_at")
        if (
            not isinstance(batch_id, str) or not batch_id
            or mode not in {"entries", "full"}
            or not isinstance(created_at, str) or not created_at
            or not isinstance(updated_at, str) or not updated_at
        ):
            raise ValueError("batch state identity is invalid")
        return cls(
            batch_id=batch_id,
            mode=mode,
            targets=normalized,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            schema_version=STATE_SCHEMA_VERSION,
        )

    @classmethod
    def load(cls, path: Path | str) -> "BatchState":
        return cls.from_dict(read_json(path))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "mode": self.mode,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "targets": {key: dict(self.targets[key]) for key in sorted(self.targets)},
        }

    def save(self, path: Path | str) -> None:
        self.updated_at = _now()
        atomic_write_json(path, self.to_dict())

    def update_target(self, key: str, **fields: object) -> None:
        if key not in self.targets:
            raise KeyError(key)
        if "state" in fields and fields["state"] not in _ALLOWED_TARGET_STATES:
            raise ValueError("target state is invalid")
        record = self.targets[key]
        record.update(fields)
        record.setdefault("updated_at", _now())

    def set_status(self, status: str, *, updated_at: str | None = None) -> None:
        if status not in _ALLOWED_BATCH_STATUSES:
            raise ValueError("batch status is invalid")
        self.status = status
        self.updated_at = updated_at or _now()


def load_state(path: Path | str) -> BatchState:
    return BatchState.load(path)


def save_state(path: Path | str, state: BatchState) -> None:
    state.save(path)


__all__ = [
    "STATE_SCHEMA_VERSION",
    "BatchLock",
    "BatchState",
    "atomic_write_json",
    "batch_lock",
    "load_state",
    "read_json",
    "save_state",
]
