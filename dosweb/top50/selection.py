from __future__ import annotations

import copy
import os
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from dosweb.errors import AnalyzerError
from dosweb.top50 import MIN_RESERVE_COUNT, TOP50_SCHEMA_VERSION
from dosweb.top50.contracts import (
    normalize_slug,
    read_json_strict,
    read_jsonl_strict,
    validate_reserve_candidates,
    validate_selected_targets,
)


def _safe_name_from_slug(slug: str) -> str:
    normalize_slug(slug, "slug")
    return slug.replace("/", "__")


def _slug_from_safe_name(name: str) -> str:
    if "__" not in name:
        raise AnalyzerError(
            "TOP50_INVALID_FIELD",
            f"source directory {name} does not use owner__repository naming",
        )
    owner, repository = name.split("__", 1)
    try:
        return normalize_slug(f"{owner}/{repository}", f"source directory {name}")
    except AnalyzerError as exc:
        raise AnalyzerError(
            "TOP50_INVALID_FIELD",
            f"source directory {name} does not use owner__repository naming",
        ) from exc


def capture_snapshot(source_root: Path, db_root: Path) -> dict[str, object]:
    """Capture the current first-level source inventory without following root identity."""
    root = source_root.resolve(strict=False)
    if not root.is_dir():
        raise AnalyzerError("TOP50_INVALID_FIELD", f"source root is not a directory: {source_root}")
    projects: list[dict[str, object]] = []
    seen_slugs: set[str] = set()
    for source in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if source.name.startswith(".") or not source.is_dir():
            continue
        slug = _slug_from_safe_name(source.name)
        if slug in seen_slugs:
            raise AnalyzerError("TOP50_DUPLICATE_SLUG", f"source root contains duplicate normalized slug {slug}")
        seen_slugs.add(slug)
        db = db_root / f"{source.name}-db"
        projects.append(
            {
                "slug_normalized": slug,
                "safe_name": source.name,
                "source_dir": str(source.resolve(strict=False)),
                "database_dir": str(db),
                "database_marker_present": (db / "codeql-database.yml").is_file(),
            }
        )
    return {"schema_version": TOP50_SCHEMA_VERSION, "projects": projects}


def _score_total(record: Mapping[str, object]) -> int:
    score = record.get("score")
    return int(score.get("total", 0)) if isinstance(score, Mapping) else 0


def _selection_key(record: Mapping[str, object]) -> tuple[int, int, str]:
    rank = record.get("selection_rank")
    slug = normalize_slug(record.get("slug"), "reviewed.slug")
    if isinstance(rank, int) and not isinstance(rank, bool) and rank > 0:
        return (0, rank, slug)
    return (1, -_score_total(record), slug)


def _project_reviewed(record: Mapping[str, object]) -> dict[str, object]:
    slug = normalize_slug(record.get("slug"), "reviewed.slug")
    selection_commit = record.get("selection_commit")
    if not isinstance(selection_commit, Mapping) or not isinstance(selection_commit.get("commit_sha"), str):
        raise AnalyzerError("TOP50_INVALID_FIELD", f"reviewed {slug}: canonical selection commit is required")
    result: dict[str, object] = {
        "candidate_id": record.get("candidate_id"),
        "slug": record.get("slug"),
        "slug_normalized": slug,
        "safe_name": _safe_name_from_slug(slug),
        "default_branch": selection_commit.get("default_branch"),
        "commit_sha": selection_commit["commit_sha"],
        "reviewed_selection_commit": dict(selection_commit),
    }
    for field in ("score", "deployment", "build_plan", "hard_gates", "negative_review", "review_outcome"):
        if field in record:
            result[field] = copy.deepcopy(record[field])
    return result


def select_targets(
    reviewed: Mapping[str, Mapping[str, object]],
    reserves: Iterable[Mapping[str, object]],
    old_slugs: set[str],
    initial_slugs: set[str],
) -> dict[str, object]:
    """Select a stable, eligible Top-50 and a validated ranked reserve pool."""
    reviewed_by_id = {candidate_id: dict(record) for candidate_id, record in reviewed.items()}
    eligible = [record for record in reviewed_by_id.values() if record.get("review_outcome") == "eligible"]
    eligible.sort(key=_selection_key)
    if len(eligible) < 50:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", "fewer than 50 reviewed eligible candidates are available")
    reserve_records = [dict(record) for record in reserves]
    declared_reserve_ids = {record.get("candidate_id") for record in reserve_records}
    declared_reserve_slugs = {normalize_slug(record.get("slug"), "reserve.slug") for record in reserve_records}
    normalized_old = {normalize_slug(slug, "old_slugs") for slug in old_slugs}
    normalized_initial = {normalize_slug(slug, "initial_slugs") for slug in initial_slugs}
    targets: list[dict[str, object]] = []
    old_count = 0
    new_count = 0
    for record in eligible:
        target = _project_reviewed(record)
        slug = str(target["slug_normalized"])
        if record.get("candidate_id") in declared_reserve_ids or slug in declared_reserve_slugs:
            continue
        is_old = slug in normalized_old
        is_new = slug not in normalized_initial
        slots_left_after = 50 - (len(targets) + 1)
        new_needed_after = max(0, 17 - (new_count + int(is_new)))
        if is_old and old_count >= 10:
            continue
        if not is_new and slots_left_after < new_needed_after:
            continue
        targets.append(target)
        old_count += int(is_old)
        new_count += int(is_new)
        if len(targets) == 50:
            break
    if len(targets) != 50:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", "eligible candidates cannot satisfy selection constraints")
    selected_slugs = {str(target["slug_normalized"]) for target in targets}
    validate_reserve_candidates(reserve_records, reviewed_by_id, selected_slugs)
    reserve_pool: list[dict[str, object]] = []
    for reserve in reserve_records:
        candidate_id = reserve["candidate_id"]
        reviewed_record = reviewed_by_id[str(candidate_id)]
        reserve_target = _project_reviewed(reviewed_record)
        reserve_target["reserve_rank"] = reserve["reserve_rank"]
        reserve_target["eligible_for_replacement"] = True
        reserve_pool.append(reserve_target)
    document: dict[str, object] = {
        "schema_version": TOP50_SCHEMA_VERSION,
        "targets": targets,
        "reserve_pool": reserve_pool,
        "replacement_history": [],
    }
    validate_selected_targets(document, old_slugs, initial_slugs)
    return document


def choose_replacement(
    document: dict[str, object],
    failed_slug: str,
    failed_slugs: set[str],
    old_slugs: set[str],
    initial_slugs: set[str],
) -> dict[str, object]:
    result = copy.deepcopy(document)
    outgoing = normalize_slug(failed_slug, "failed_slug")
    failed = {normalize_slug(slug, "failed_slugs") for slug in failed_slugs}
    targets = [
        item
        for item in result.get("targets", [])
        if isinstance(item, Mapping) and item.get("slug_normalized") != outgoing
    ]
    if len(targets) != 49:
        raise AnalyzerError("TOP50_CONSTRAINT_VIOLATION", f"failed slug {outgoing} is not a unique selected target")
    reserves = result.get("reserve_pool")
    if not isinstance(reserves, list):
        raise AnalyzerError("TOP50_INVALID_FIELD", "reserve_pool must be a list")
    for reserve in sorted(reserves, key=lambda item: int(item.get("reserve_rank", 0)) if isinstance(item, Mapping) else 0):
        if not isinstance(reserve, Mapping):
            continue
        slug = normalize_slug(reserve.get("slug"), "reserve.slug")
        if reserve.get("eligible_for_replacement") is not True or reserve.get("review_outcome") != "eligible":
            continue
        if slug in failed or any(item.get("slug_normalized") == slug for item in targets):
            continue
        remaining_reserves = [item for item in reserves if item is not reserve]
        remaining_target_slugs = {normalize_slug(item.get("slug"), "targets.slug") for item in targets} | {slug}
        usable_reserves = [
            item
            for item in remaining_reserves
            if isinstance(item, Mapping)
            and item.get("eligible_for_replacement") is True
            and item.get("review_outcome") == "eligible"
            and normalize_slug(item.get("slug"), "reserve.slug") not in failed
            and normalize_slug(item.get("slug"), "reserve.slug") not in remaining_target_slugs
        ]
        if len(usable_reserves) < MIN_RESERVE_COUNT:
            continue
        candidate = {
            **result,
            "targets": targets + [dict(reserve)],
            "reserve_pool": remaining_reserves,
        }
        try:
            validate_selected_targets(candidate, old_slugs, initial_slugs)
        except AnalyzerError:
            continue
        history = candidate.get("replacement_history")
        if not isinstance(history, list):
            history = []
            candidate["replacement_history"] = history
        history.append({"outgoing_slug": outgoing, "incoming_slug": slug})
        return candidate
    raise AnalyzerError(
        "TOP50_CONSTRAINT_VIOLATION",
        f"no eligible reserve preserves constraints after failure of {outgoing}",
    )


def _targets(document: Mapping[str, object]) -> list[Mapping[str, object]]:
    targets = document.get("targets")
    if not isinstance(targets, list) or not all(isinstance(item, Mapping) for item in targets):
        raise AnalyzerError("TOP50_INVALID_FIELD", "selected document targets must be a list of objects")
    return list(targets)


def overlap_report(document: Mapping[str, object], old_slugs: set[str], initial_slugs: set[str]) -> dict[str, object]:
    targets = _targets(document)
    target_slugs = {normalize_slug(item.get("slug"), "targets.slug") for item in targets}
    normalized_old = {normalize_slug(slug, "old_slugs") for slug in old_slugs}
    normalized_initial = {normalize_slug(slug, "initial_slugs") for slug in initial_slugs}
    return {
        "target_count": len(target_slugs),
        "old_top50_overlap_count": len(target_slugs & normalized_old),
        "old_top50_overlap_slugs": sorted(target_slugs & normalized_old),
        "new_since_initial_count": len(target_slugs - normalized_initial),
        "new_since_initial_slugs": sorted(target_slugs - normalized_initial),
    }


def render_markdown(document: Mapping[str, object]) -> str:
    targets = _targets(document)
    lines = [
        "# Java Web DoS Top-50 Selection",
        "",
        "| # | Repository | Commit |",
        "|---:|---|---|",
    ]
    for index, item in enumerate(targets, start=1):
        slug = normalize_slug(item.get("slug"), f"targets[{index - 1}].slug")
        commit_sha = item.get("commit_sha")
        if not isinstance(commit_sha, str):
            raise AnalyzerError("TOP50_INVALID_FIELD", f"targets[{index - 1}].commit_sha is required")
        lines.append(f"| {index} | `{slug}` | `{commit_sha}` |")
    return "\n".join(lines) + "\n"


def render_intel_json(document: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": document.get("schema_version", TOP50_SCHEMA_VERSION),
        "targets": [copy.deepcopy(dict(item)) for item in _targets(document)],
    }


def _latest_statuses(records: Iterable[Mapping[str, object]]) -> dict[str, tuple[int, Mapping[str, object]]]:
    latest: dict[str, tuple[int, Mapping[str, object]]] = {}
    for index, record in enumerate(records):
        slug = normalize_slug(record.get("slug"), f"status_events[{index}].slug")
        latest[slug] = (index, record)
    return latest


def _status_captures_selected_commit(
    records: Iterable[Mapping[str, object]], slug: str, commit_sha: str, success_index: int
) -> bool:
    for index, record in enumerate(records):
        if index > success_index or record.get("stage") != "source":
            continue
        if normalize_slug(record.get("slug"), f"status_events[{index}].slug") != slug:
            continue
        recorded_commit = record.get("commit")
        if isinstance(recorded_commit, str) and recorded_commit.casefold() == commit_sha.casefold():
            return True
    return False


def _git_head(source_dir: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(source_dir), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise AnalyzerError("TOP50_AUDIT_FAILED", f"unable to read git HEAD for {source_dir}") from exc


def audit_selection(
    document: Mapping[str, object],
    old_slugs: set[str],
    initial_slugs: set[str],
    source_root: Path,
    db_root: Path,
    status_events: Iterable[Mapping[str, object]],
    markdown_slugs: Iterable[str] | None = None,
    intel_document: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate every final target and return a report only after all checks pass."""
    validate_selected_targets(document, old_slugs, initial_slugs)
    targets = _targets(document)
    status_records = list(status_events)
    latest = _latest_statuses(status_records)
    target_slugs = {normalize_slug(item.get("slug"), "targets.slug") for item in targets}
    missing_status = sorted(target_slugs - set(latest))
    if missing_status:
        raise AnalyzerError("TOP50_AUDIT_FAILED", f"partial database status events; missing {', '.join(missing_status)}")
    for item in targets:
        slug = normalize_slug(item.get("slug"), "targets.slug")
        safe_name = item.get("safe_name")
        if safe_name != _safe_name_from_slug(slug):
            raise AnalyzerError("TOP50_AUDIT_FAILED", f"{slug}: selected safe_name does not match slug identity")
        source_dir = source_root / str(safe_name)
        if not source_dir.is_dir():
            raise AnalyzerError("TOP50_AUDIT_FAILED", f"{slug}: source directory is missing")
        commit_sha = item.get("commit_sha")
        if not isinstance(commit_sha, str) or _git_head(source_dir).casefold() != commit_sha.casefold():
            raise AnalyzerError("TOP50_AUDIT_FAILED", f"{slug}: git HEAD does not match selected commit")
        db_dir = db_root / f"{safe_name}-db"
        java_db = db_dir / "db-java"
        if not (db_dir / "codeql-database.yml").is_file() or not java_db.is_dir() or not any(java_db.iterdir()):
            raise AnalyzerError("TOP50_AUDIT_FAILED", f"{slug}: CodeQL database is not a nonempty Java database")
        success_index, status = latest[slug]
        if not (
            status.get("status") == "success"
            and status.get("verification_status") == "verified"
            and isinstance(status.get("compilation_unit_count"), int)
            and not isinstance(status.get("compilation_unit_count"), bool)
            and status.get("compilation_unit_count", 0) > 0
            and status.get("coverage_status") in {"complete", "limited"}
            and _status_captures_selected_commit(status_records, slug, commit_sha, success_index)
        ):
            raise AnalyzerError("TOP50_AUDIT_FAILED", f"{slug}: database does not have verified capture status")
    if markdown_slugs is not None:
        markdown_set = {normalize_slug(slug, "markdown.slug") for slug in markdown_slugs}
        if markdown_set != target_slugs:
            raise AnalyzerError("TOP50_AUDIT_FAILED", "Markdown slug set drifts from selected targets")
    if intel_document is not None:
        try:
            intel_targets = _targets(intel_document)
        except AnalyzerError as exc:
            raise AnalyzerError("TOP50_AUDIT_FAILED", f"intel JSON structure drifts from selected targets: {exc.message}") from exc
        intel_slugs = [normalize_slug(item.get("slug"), "intel.targets.slug") for item in intel_targets]
        if len(intel_slugs) != len(target_slugs) or len(set(intel_slugs)) != len(intel_slugs) or set(intel_slugs) != target_slugs:
            raise AnalyzerError("TOP50_AUDIT_FAILED", "intel JSON slug set drifts from selected targets")
    return {
        "schema_version": TOP50_SCHEMA_VERSION,
        "status": "passed",
        "target_count": len(target_slugs),
        "overlap": overlap_report(document, old_slugs, initial_slugs),
    }


def read_json_object(path: Path, label: str) -> dict[str, object]:
    return read_json_strict(path, label)


def read_status_events(path: Path) -> list[dict[str, object]]:
    records = read_jsonl_strict(path, "status events")
    for index, record in enumerate(records):
        normalize_slug(record.get("slug"), f"status_events[{index}].slug")
    return records


def write_text_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)
