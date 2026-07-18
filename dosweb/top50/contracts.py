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


OFFICIAL_EVIDENCE_KINDS = {
    "repository_readme",
    "official_deployment_doc",
    "official_compose",
    "official_dockerfile",
    "default_config",
    "repository_metadata",
}
SCORE_LIMITS = {
    "default_public_entry": (0, 25, 18),
    "dos_relevance": (0, 30, 18),
    "low_privilege_reachability": (0, 15, 8),
    "impact_usage": (0, 15, None),
    "codeql_feasibility": (0, 10, None),
    "maintenance_evidence": (0, 5, None),
}


def _validate_reviewed_commit(record: Mapping[str, object], location: str) -> None:
    selection_commit = record.get("selection_commit")
    selection_sha: object = None
    if selection_commit is not None:
        if not isinstance(selection_commit, Mapping):
            raise AnalyzerError("TOP50_INVALID_FIELD", f"{location}.selection_commit: expected object")
        selection_sha = selection_commit.get("commit_sha")
        if not isinstance(selection_sha, str) or not COMMIT_SHA_RE.fullmatch(selection_sha):
            raise AnalyzerError(
                "TOP50_INVALID_FIELD",
                f"{location}.selection_commit.commit_sha: expected 40-character SHA",
            )

    legacy_sha = record.get("commit_sha")
    if legacy_sha is not None:
        if not isinstance(legacy_sha, str) or not COMMIT_SHA_RE.fullmatch(legacy_sha):
            raise AnalyzerError("TOP50_INVALID_FIELD", f"{location}.commit_sha: expected 40-character SHA")
        if selection_sha is not None and legacy_sha != selection_sha:
            raise AnalyzerError(
                "TOP50_INVALID_FIELD",
                f"{location}.commit_sha: must match selection_commit.commit_sha",
            )
    elif selection_sha is None:
        raise AnalyzerError(
            "TOP50_INVALID_FIELD",
            f"{location}.selection_commit.commit_sha: expected 40-character SHA",
        )


def _official_evidence_ids(record: Mapping[str, object]) -> tuple[set[str], set[str]]:
    evidence = record.get("evidence")
    hard_gate_evidence_ids = record.get("hard_gate_evidence_ids")
    if not isinstance(evidence, list) or not isinstance(hard_gate_evidence_ids, list):
        return set(), set()
    hard_ids = {item for item in hard_gate_evidence_ids if isinstance(item, str)}
    if len(hard_ids) != len(hard_gate_evidence_ids):
        return set(), set()
    official_ids = {
        item["evidence_id"]
        for item in evidence
        if isinstance(item, Mapping)
        and isinstance(item.get("evidence_id"), str)
        and item.get("official") is True
        and item.get("source_kind") in OFFICIAL_EVIDENCE_KINDS
    }
    return hard_ids, official_ids


def validate_reviewed_candidates(records: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    reviewed: dict[str, dict[str, object]] = {}
    seen_slugs: set[str] = set()
    for index, record in enumerate(records):
        location = f"reviewed[{index}]"
        if not isinstance(record, Mapping):
            raise AnalyzerError("TOP50_RECORD_NOT_OBJECT", f"{location}: record must be an object")
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in reviewed:
            raise AnalyzerError("TOP50_INVALID_REVIEW", f"{location}: unique candidate_id is required")
        normalized = _validated_record_slug(record, location)
        if normalized in seen_slugs:
            raise AnalyzerError("TOP50_DUPLICATE_SLUG", f"{location}: duplicate slug {normalized}")
        _validate_reviewed_commit(record, location)

        deployment = record.get("deployment")
        dependencies = deployment.get("required_external_dependencies") if isinstance(deployment, Mapping) else None
        if not isinstance(dependencies, list) or not 0 <= len(dependencies) <= 3:
            raise AnalyzerError("TOP50_INVALID_REVIEW", f"{location}: zero to three external dependencies are required")

        score = record.get("score")
        if not isinstance(score, Mapping):
            raise AnalyzerError("TOP50_INVALID_REVIEW", f"{location}: score object is required")
        total = 0
        for name, (minimum, maximum, gate) in SCORE_LIMITS.items():
            value = score.get(name)
            if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
                raise AnalyzerError("TOP50_INVALID_REVIEW", f"{location}: invalid score {name}")
            if gate is not None and value < gate:
                raise AnalyzerError("TOP50_INVALID_REVIEW", f"{location}: score {name} is below hard gate {gate}")
            total += value
        if score.get("total") != total or total < 70:
            raise AnalyzerError("TOP50_INVALID_REVIEW", f"{location}: score total must equal {total} and be at least 70")

        hard_ids, official_ids = _official_evidence_ids(record)
        if not hard_ids or not hard_ids <= official_ids:
            raise AnalyzerError("TOP50_INVALID_EVIDENCE", f"{location}: hard gates require official evidence")
        if record.get("hard_gates") != {"passed": True} or record.get("negative_review") != {"outcome": "passed"}:
            raise AnalyzerError("TOP50_INVALID_REVIEW", f"{location}: hard gates and negative review must pass")

        reviewed[candidate_id] = record if isinstance(record, dict) else dict(record)
        seen_slugs.add(normalized)
    return reviewed


def validate_reserve_candidates(
    records: Iterable[Mapping[str, object]],
    reviewed_by_id: Mapping[str, Mapping[str, object]],
    selected_slugs: set[str],
) -> None:
    reserve_records = list(records)
    if [item.get("reserve_rank") if isinstance(item, Mapping) else None for item in reserve_records] != list(
        range(1, len(reserve_records) + 1)
    ):
        raise AnalyzerError("TOP50_INVALID_REVIEW", "reserve ranks must be contiguous starting at one")
    normalized_selected_slugs = _normalize_slug_set(selected_slugs, "selected_slugs")
    for index, item in enumerate(reserve_records):
        location = f"reserve[{index}]"
        if not isinstance(item, Mapping):
            raise AnalyzerError("TOP50_RECORD_NOT_OBJECT", f"{location}: record must be an object")
        candidate_id = item.get("candidate_id")
        reviewed = reviewed_by_id.get(candidate_id) if isinstance(candidate_id, str) else None
        if reviewed is None or item.get("eligible_for_replacement") is not True:
            raise AnalyzerError("TOP50_INVALID_REVIEW", "every reserve must reference a fully reviewed eligible candidate")
        if _validated_record_slug(reviewed, f"{location}.reviewed") in normalized_selected_slugs:
            raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", "main selection and reserve pool overlap")


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
