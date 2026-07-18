from __future__ import annotations

import json
import math
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

from dosweb.errors import AnalyzerError
from dosweb.top50 import EXACT_TARGET_COUNT, MAX_OLD_TOP50_OVERLAP, MIN_NEW_TARGETS

SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def normalize_slug(slug: object, location: str) -> str:
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise AnalyzerError("TOP50_INVALID_FIELD", f"{location}: expected owner/repository slug")
    return slug.casefold()


def _reject_nonfinite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite number")
    if isinstance(value, dict):
        for nested in value.values():
            _reject_nonfinite(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_nonfinite(nested)


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, nested in pairs:
        if key in value:
            raise ValueError(f"duplicate object key {key!r}")
        value[key] = nested
    return value


def _parse_json(text: str, location: str) -> object:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        _reject_nonfinite(value)
        return value
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise AnalyzerError("TOP50_INVALID_JSON", f"{location}: invalid JSON: {exc}") from exc


def _physical_jsonl_lines(text: str) -> list[str]:
    if not text:
        return []
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def read_jsonl_strict(path: Path, artifact_name: str) -> list[dict[str, object]]:
    try:
        lines = _physical_jsonl_lines(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise AnalyzerError("TOP50_INVALID_JSON", f"{path}: invalid UTF-8: {exc}") from exc
    except OSError as exc:
        raise AnalyzerError("TOP50_INVALID_JSONL", f"{path}: unable to read {artifact_name}: {exc}") from exc
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            raise AnalyzerError("TOP50_INVALID_JSONL", f"{path}:{line_no}: blank line in {artifact_name}")
        value = _parse_json(line, f"{path}:{line_no}")
        if not isinstance(value, dict):
            raise AnalyzerError("TOP50_RECORD_NOT_OBJECT", f"{path}:{line_no}: record must be an object")
        slug = value.get("slug_normalized")
        if slug is not None:
            normalized = normalize_slug(slug, f"{path}:{line_no}.slug_normalized")
            if normalized in seen:
                raise AnalyzerError("TOP50_DUPLICATE_SLUG", f"{path}:{line_no}: duplicate slug {normalized}")
            seen.add(normalized)
        records.append(value)
    return records


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def write_json_atomically(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_jsonl_atomically(path: Path, records: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for index, record in enumerate(records):
                if not isinstance(record, Mapping):
                    raise AnalyzerError("TOP50_RECORD_NOT_OBJECT", f"records[{index}]: record must be an object")
                json.dump(record, handle, ensure_ascii=False, sort_keys=True, allow_nan=False)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _validated_record_slug(record: Mapping[str, object], location: str) -> str:
    slug = record.get("slug")
    normalized = normalize_slug(slug, f"{location}.slug")
    slug_normalized = record.get("slug_normalized")
    if slug_normalized != normalized:
        raise AnalyzerError("TOP50_INVALID_FIELD", f"{location}.slug_normalized: must equal normalized slug")
    return normalized


def _validate_record_commit(record: Mapping[str, object], location: str) -> None:
    commit_sha = record.get("commit_sha")
    if not isinstance(commit_sha, str) or not COMMIT_SHA_RE.fullmatch(commit_sha):
        raise AnalyzerError("TOP50_INVALID_FIELD", f"{location}.commit_sha: expected 40-character SHA")


def validate_reviewed_candidates(records: Iterable[Mapping[str, object]]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records):
        location = f"records[{index}]"
        if not isinstance(record, Mapping):
            raise AnalyzerError("TOP50_RECORD_NOT_OBJECT", f"{location}: record must be an object")
        normalized = _validated_record_slug(record, location)
        _validate_record_commit(record, location)
        if normalized in seen:
            raise AnalyzerError("TOP50_DUPLICATE_SLUG", f"{location}: duplicate slug {normalized}")
        seen.add(normalized)


def _normalize_slug_set(slugs: Iterable[str], location: str) -> set[str]:
    return {normalize_slug(slug, f"{location}[{index}]") for index, slug in enumerate(slugs)}


def validate_selected_targets(document: Mapping[str, object], old_slugs: set[str], initial_slugs: set[str]) -> None:
    if not isinstance(document, Mapping):
        raise AnalyzerError("TOP50_INVALID_FIELD", "selected targets document must be an object")
    targets = document.get("targets")
    if not isinstance(targets, list) or len(targets) != EXACT_TARGET_COUNT:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", f"selected targets must contain exactly {EXACT_TARGET_COUNT} projects")
    normalized = []
    for index, item in enumerate(targets):
        if not isinstance(item, Mapping):
            raise AnalyzerError("TOP50_RECORD_NOT_OBJECT", f"targets[{index}]: record must be an object")
        location = f"targets[{index}]"
        normalized.append(_validated_record_slug(item, location))
        _validate_record_commit(item, location)
    if len(normalized) != EXACT_TARGET_COUNT or len(set(normalized)) != EXACT_TARGET_COUNT:
        raise AnalyzerError("TOP50_DUPLICATE_SLUG", "selected targets contain duplicate normalized slugs")
    overlap = len(set(normalized) & _normalize_slug_set(old_slugs, "old_slugs"))
    if overlap > MAX_OLD_TOP50_OVERLAP:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", f"old Top-50 overlap is {overlap}, maximum is {MAX_OLD_TOP50_OVERLAP}")
    new_count = len(set(normalized) - _normalize_slug_set(initial_slugs, "initial_slugs"))
    if new_count < MIN_NEW_TARGETS:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", f"selection requires at least {MIN_NEW_TARGETS} new projects, found {new_count}")
