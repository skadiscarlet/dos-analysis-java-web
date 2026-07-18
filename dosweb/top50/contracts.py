from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

from dosweb.errors import AnalyzerError
from dosweb.top50 import EXACT_TARGET_COUNT, MAX_OLD_TOP50_OVERLAP, MIN_NEW_TARGETS

SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def normalize_slug(slug: object, location: str) -> str:
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise AnalyzerError("TOP50_INVALID_FIELD", f"{location}: expected owner/repository slug")
    return slug.casefold()


def _parse_json(text: str, location: str) -> object:
    try:
        return json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AnalyzerError("TOP50_INVALID_JSON", f"{location}: invalid JSON: {exc}") from exc


def read_jsonl_strict(path: Path, artifact_name: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
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


def write_json_atomically(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_jsonl_atomically(path: Path, records: Iterable[Mapping[str, object]]) -> None:
    document = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for record in records)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(document, encoding="utf-8")
    os.replace(temporary, path)


def validate_selected_targets(document: Mapping[str, object], old_slugs: set[str], initial_slugs: set[str]) -> None:
    targets = document.get("targets")
    if not isinstance(targets, list) or len(targets) != EXACT_TARGET_COUNT:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", f"selected targets must contain exactly {EXACT_TARGET_COUNT} projects")
    normalized = [normalize_slug(item.get("slug_normalized"), f"targets[{index}]") for index, item in enumerate(targets) if isinstance(item, dict)]
    if len(normalized) != EXACT_TARGET_COUNT or len(set(normalized)) != EXACT_TARGET_COUNT:
        raise AnalyzerError("TOP50_DUPLICATE_SLUG", "selected targets contain duplicate normalized slugs")
    overlap = len(set(normalized) & old_slugs)
    if overlap > MAX_OLD_TOP50_OVERLAP:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", f"old Top-50 overlap is {overlap}, maximum is {MAX_OLD_TOP50_OVERLAP}")
    new_count = len(set(normalized) - initial_slugs)
    if new_count < MIN_NEW_TARGETS:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", f"selection requires at least {MIN_NEW_TARGETS} new projects, found {new_count}")
