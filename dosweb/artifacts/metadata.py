from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dosweb.artifacts.identifiers import canonical_json, file_sha256
from dosweb.errors import AnalyzerError


@dataclass(frozen=True)
class StageFingerprint:
    schema_version: str
    tool_version: str
    implementation_version: str
    database_fingerprint: str
    query_pack_hash: str
    config_hash: str
    upstream_hashes: Mapping[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "implementation_version": self.implementation_version,
            "database_fingerprint": self.database_fingerprint,
            "query_pack_hash": self.query_pack_hash,
            "config_hash": self.config_hash,
            "upstream_hashes": dict(self.upstream_hashes),
        }


def _upstream_error(code: str, message: str, **details: object) -> AnalyzerError:
    return AnalyzerError(code, message, {key: value for key, value in details.items()})


def _safe_upstream_path(output_root: Path, raw: str) -> Path:
    relative = Path(raw)
    normalized = Path(os.path.normpath(raw))
    if (
        not raw
        or "\x00" in raw
        or relative.is_absolute()
        or relative == Path(".")
        or ".." in relative.parts
        or normalized.as_posix() != raw
    ):
        raise _upstream_error(
            "ARTIFACT_INVALID_PATH",
            "Upstream artifact path is invalid.",
            path=raw,
        )
    path = output_root / normalized
    current = output_root.absolute()
    try:
        root_info = os.lstat(current)
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise ValueError("unsafe output root")
        for part in normalized.parts:
            current /= part
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("symlinked upstream artifact")
    except (OSError, ValueError) as exc:
        raise _upstream_error(
            "ARTIFACT_INVALID_PATH",
            "Upstream artifact path could not be validated safely.",
            path=raw,
        ) from exc
    return path


def _verify_upstream_file(
    path: Path,
    *,
    expected_sha256: str,
    expected_records: int,
    expected_bytes: int,
) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_bytes:
            raise ValueError("upstream artifact size mismatch")
        digest = hashlib.sha256()
        records = 0
        last = b""
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
            records += chunk.count(b"\n")
            last = chunk[-1:]
        if last and last != b"\n":
            records += 1
        after = os.fstat(descriptor)
        if (
            total != expected_bytes
            or records != expected_records
            or digest.hexdigest() != expected_sha256
            or after.st_size != before.st_size
            or after.st_ino != before.st_ino
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            raise ValueError("upstream artifact integrity mismatch")
    except (OSError, ValueError) as exc:
        raise _upstream_error(
            "ARTIFACT_UPSTREAM_INVALID",
            "Upstream artifact failed its integrity check.",
            path=path.name,
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def resolve_upstream_artifact(
    output_root: Path,
    upstream: Mapping[str, Mapping[str, object]],
    stage_name: str,
    artifact_path: str,
    *,
    schema_version: str,
) -> Path:
    """Resolve one named upstream artifact only after verifying its manifest entry."""
    stage = upstream.get(stage_name)
    if not isinstance(stage, Mapping) or stage.get("status") != "completed":
        raise _upstream_error(
            "ARTIFACT_UPSTREAM_MISSING",
            "Required upstream stage metadata is unavailable.",
            stage=stage_name,
        )
    artifacts = stage.get("artifacts")
    if (
        stage.get("stage") != stage_name
        or not isinstance(artifacts, list)
        or not artifacts
        or stage.get("output_hash")
        != hashlib.sha256(canonical_json(artifacts)).hexdigest()
    ):
        raise _upstream_error(
            "ARTIFACT_UPSTREAM_INVALID",
            "Upstream stage metadata is malformed.",
            stage=stage_name,
        )
    matches = [
        item
        for item in artifacts
        if isinstance(item, Mapping) and item.get("path") == artifact_path
    ]
    if len(matches) != 1:
        raise _upstream_error(
            "ARTIFACT_UPSTREAM_MISSING",
            "Required upstream artifact is unavailable.",
            stage=stage_name,
            path=artifact_path,
        )
    item = matches[0]
    digest = item.get("sha256")
    record_count = item.get("record_count")
    byte_count = item.get("byte_count")
    if (
        item.get("schema_version") != schema_version
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(record_count, int)
        or isinstance(record_count, bool)
        or record_count < 0
        or not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count < 0
    ):
        raise _upstream_error(
            "ARTIFACT_UPSTREAM_INVALID",
            "Upstream artifact metadata is malformed.",
            stage=stage_name,
            path=artifact_path,
        )
    path = _safe_upstream_path(output_root, artifact_path)
    _verify_upstream_file(
        path,
        expected_sha256=digest,
        expected_records=record_count,
        expected_bytes=byte_count,
    )
    return path


def reusable_stage(
    run: Mapping[str, object],
    stage_name: str,
    expected: StageFingerprint,
    output_root: Path,
) -> bool:
    stages = run.get("stages")
    if not isinstance(stages, Mapping):
        return False
    stage = stages.get(stage_name)
    if not isinstance(stage, Mapping) or stage.get("status") != "completed":
        return False
    if stage.get("fingerprint") != expected.to_dict():
        return False
    artifacts = stage.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return False
    try:
        root = output_root.resolve()
    except OSError:
        return False
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            return False
        path = artifact.get("path")
        digest = artifact.get("sha256")
        schema_version = artifact.get("schema_version")
        record_count = artifact.get("record_count")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(digest, str)
            or not digest
            or schema_version != expected.schema_version
            or isinstance(record_count, bool)
            or not isinstance(record_count, int)
            or record_count < 0
        ):
            return False
        relative_path = Path(path)
        if relative_path.is_absolute():
            return False
        try:
            artifact_path = (root / relative_path).resolve()
            artifact_path.relative_to(root)
        except (OSError, ValueError):
            return False
        try:
            if not artifact_path.is_file() or file_sha256(artifact_path) != digest:
                return False
            actual_count = 0
            with artifact_path.open("rb") as source:
                while source.readline():
                    actual_count += 1
                    if actual_count > record_count:
                        return False
            if actual_count != record_count:
                return False
        except OSError:
            return False
    return True


def invalidate_from(
    run: MutableMapping[str, object],
    first_stage: str,
    ordered_stages: Iterable[str],
) -> None:
    stages = run.get("stages")
    if not isinstance(stages, MutableMapping):
        return
    invalidate = False
    for stage_name in ordered_stages:
        if stage_name == first_stage:
            invalidate = True
        if invalidate:
            stage = stages.get(stage_name)
            if isinstance(stage, MutableMapping):
                stage["status"] = "invalid"
