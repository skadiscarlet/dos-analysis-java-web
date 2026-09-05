from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from itertools import islice
from dataclasses import dataclass
from pathlib import Path

from dosweb.artifacts.identifiers import canonical_json, file_sha256
import hashlib
from dosweb.artifacts.schemas import SCHEMA_VERSION, validate_references
from dosweb.errors import AnalyzerError


_MAX_ARTIFACT_RECORDS = 4096
_MAX_ARTIFACT_RECORD_BYTES = 262144
_MAX_ARTIFACT_TOTAL_BYTES = 16 * 1024 * 1024
_MAX_ARTIFACT_DEPTH = 32
_MAX_ARTIFACT_NODES = 8192
_MAX_ARTIFACT_COLLECTION = 4096
_MAX_ARTIFACT_STRING_BYTES = 262144


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    sha256: str
    record_count: int
    schema_version: str


def artifact_ref_for_metadata(ref: ArtifactRef, output_root: Path) -> dict[str, object]:
    try:
        root = output_root.resolve()
        artifact_path = Path(ref.path).resolve()
        relative_path = artifact_path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise AnalyzerError(
            "ARTIFACT_INVALID_PATH",
            "Artifact metadata path must be inside the output root.",
            {"path": ref.path, "output_root": str(output_root)},
        ) from exc
    return {
        "path": relative_path.as_posix(),
        "sha256": ref.sha256,
        "record_count": ref.record_count,
        "schema_version": ref.schema_version,
    }


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _check_artifact_value(value: object) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if depth > _MAX_ARTIFACT_DEPTH or nodes > _MAX_ARTIFACT_NODES:
            raise ValueError("artifact structure exceeds limits")
        if isinstance(current, str):
            if len(current.encode("utf-8")) > _MAX_ARTIFACT_STRING_BYTES:
                raise ValueError("artifact string exceeds limit")
        elif isinstance(current, dict):
            if len(current) > _MAX_ARTIFACT_COLLECTION:
                raise ValueError("artifact object exceeds limit")
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            if len(current) > _MAX_ARTIFACT_COLLECTION:
                raise ValueError("artifact array exceeds limit")
            stack.extend((item, depth + 1) for item in current)


def read_jsonl_strict(path: Path, artifact_name: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    line_number = 0
    try:
        total_bytes = 0
        with path.open("rb") as source:
            while True:
                raw_line = source.readline(_MAX_ARTIFACT_RECORD_BYTES + 1)
                if not raw_line:
                    break
                line_number += 1
                total_bytes += len(raw_line)
                if line_number > _MAX_ARTIFACT_RECORDS or len(raw_line) > _MAX_ARTIFACT_RECORD_BYTES or total_bytes > _MAX_ARTIFACT_TOTAL_BYTES or (not raw_line.endswith(b"\n") and source.peek(1)):
                    raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Artifact JSONL exceeds configured limits.", {"path": str(path), "line": line_number, "artifact_name": artifact_name})
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise AnalyzerError(
                        "ARTIFACT_INVALID_JSON",
                        "Artifact JSONL is not valid UTF-8.",
                        {"path": str(path), "line": line_number, "artifact_name": artifact_name},
                    ) from exc
                if not line.strip():
                    raise AnalyzerError(
                        "ARTIFACT_INVALID_JSON",
                        "Artifact JSONL must not contain blank records.",
                        {"path": str(path), "line": line_number, "artifact_name": artifact_name},
                    )
                try:
                    record = json.loads(line, parse_constant=_reject_json_constant, object_pairs_hook=_unique_json_object)
                    _check_artifact_value(record)
                except (json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
                    raise AnalyzerError(
                        "ARTIFACT_INVALID_JSON",
                        "Artifact JSONL contains invalid JSON.",
                        {"path": str(path), "line": line_number, "artifact_name": artifact_name},
                    ) from exc
                if not isinstance(record, dict):
                    raise AnalyzerError(
                        "ARTIFACT_RECORD_NOT_OBJECT",
                        "Artifact records must be JSON objects.",
                        {"path": str(path), "line": line_number, "artifact_name": artifact_name},
                    )
                records.append(record)
    except OSError as exc:
        raise AnalyzerError(
            "ARTIFACT_READ_FAILED",
            "Could not read artifact file.",
            {"path": str(path), "artifact_name": artifact_name},
        ) from exc
    return records


def read_jsonl_bytes_strict(payload: bytes, artifact_name: str, *, source_name: str = "verified-upstream") -> list[dict[str, object]]:
    """Parse an already authenticated byte snapshot without reopening its path."""
    if not isinstance(payload, bytes) or len(payload) > _MAX_ARTIFACT_TOTAL_BYTES:
        raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Artifact JSONL exceeds configured limits.", {"path": source_name, "artifact_name": artifact_name})
    records: list[dict[str, object]] = []
    lines = payload.splitlines(keepends=True)
    if len(lines) > _MAX_ARTIFACT_RECORDS:
        raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Artifact JSONL exceeds configured limits.", {"path": source_name, "artifact_name": artifact_name})
    for line_number, raw_line in enumerate(lines, 1):
        if len(raw_line) > _MAX_ARTIFACT_RECORD_BYTES:
            raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Artifact JSONL exceeds configured limits.", {"path": source_name, "line": line_number, "artifact_name": artifact_name})
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AnalyzerError("ARTIFACT_INVALID_JSON", "Artifact JSONL is not valid UTF-8.", {"path": source_name, "line": line_number, "artifact_name": artifact_name}) from exc
        if not line.strip():
            raise AnalyzerError("ARTIFACT_INVALID_JSON", "Artifact JSONL must not contain blank records.", {"path": source_name, "line": line_number, "artifact_name": artifact_name})
        try:
            record = json.loads(line, parse_constant=_reject_json_constant, object_pairs_hook=_unique_json_object)
            _check_artifact_value(record)
        except (json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
            raise AnalyzerError("ARTIFACT_INVALID_JSON", "Artifact JSONL contains invalid JSON.", {"path": source_name, "line": line_number, "artifact_name": artifact_name}) from exc
        if not isinstance(record, dict):
            raise AnalyzerError("ARTIFACT_RECORD_NOT_OBJECT", "Artifact records must be JSON objects.", {"path": source_name, "line": line_number, "artifact_name": artifact_name})
        records.append(record)
    return records


def write_jsonl_atomically(
    path: Path,
    artifact_name: str,
    records: Iterable[Mapping[str, object]],
    known_ids: Mapping[str, object],
) -> ArtifactRef:
    try:
        materialized = tuple(islice(iter(records), _MAX_ARTIFACT_RECORDS + 1))
    except (TypeError, ValueError, OverflowError, MemoryError, RecursionError) as exc:
        raise AnalyzerError("ARTIFACT_INVALID_RECORD", "Artifact records could not be bounded.", {"path": str(path), "artifact_name": artifact_name}) from exc
    if len(materialized) > _MAX_ARTIFACT_RECORDS:
        raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Artifact contains too many records.", {"path": str(path), "artifact_name": artifact_name})
    normalized: list[dict[str, object]] = []
    total_bytes = 0
    for index, record in enumerate(materialized, start=1):
        if not isinstance(record, dict):
            raise AnalyzerError("ARTIFACT_INVALID_RECORD", "Artifact record must be a plain bounded dict.", {"artifact_name": artifact_name, "line": index})
        item = record.copy()
        _check_artifact_value(item)
        encoded = canonical_json(item)
        if len(encoded) > _MAX_ARTIFACT_RECORD_BYTES:
            raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Artifact record exceeds byte limit.", {"artifact_name": artifact_name, "line": index})
        total_bytes += len(encoded) + 1
        if total_bytes > _MAX_ARTIFACT_TOTAL_BYTES:
            raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Artifact exceeds total byte limit.", {"artifact_name": artifact_name, "line": index})
        normalized.append(item)
    validate_references(artifact_name, normalized, known_ids)
    normalized.sort(key=canonical_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    published_sha256: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            for record in normalized:
                temporary.write(canonical_json(record))
                temporary.write(b"\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        published_sha256 = file_sha256(temporary_path)
        reread = read_jsonl_strict(temporary_path, artifact_name)
        validate_references(artifact_name, reread, known_ids)
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return ArtifactRef(
        path=str(path),
        sha256=published_sha256 or hashlib.sha256(b"").hexdigest(),
        record_count=len(normalized),
        schema_version=SCHEMA_VERSION,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
