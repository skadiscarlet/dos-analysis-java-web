#!/usr/bin/env python3
"""Generate the active Java Web 205 inventory from preserved source manifests."""
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dosweb.batch.corpus import _fingerprint
from dosweb.codeql.database import validate_database
from dosweb.errors import AnalyzerError

DEFAULT_BASE_MANIFEST = REPO_ROOT / "intel/applications/java_web_200_targets.json"
DEFAULT_POC_MANIFEST = REPO_ROOT / "poc/manifest.json"
DEFAULT_OUTPUT = REPO_ROOT / "intel/applications/java_web_205_targets.json"
_BASE_CORPUS = "java-web-200"
_ACTIVE_CORPUS = "java-web-205"
_BASE_TOTAL = 200
_ACTIVE_TOTAL = 205
_GENERATED_AT = "2026-08-03T00:00:00+00:00"


def normalize_repository(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("repository identity must be a string")
    normalized = value.strip().replace("\\", "/")
    if "/" not in normalized and "__" in normalized:
        normalized = normalized.replace("__", "/", 1)
    parts = normalized.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"invalid repository identity: {value!r}")
    return f"{parts[0].lower()}/{parts[1].lower()}"


def compose_repository_names(base_projects: Sequence[Mapping[str, object]], poc_cases: Sequence[Mapping[str, object]]) -> list[str]:
    """Preserve the original 200 identities and append the PoC-union delta."""
    if len(base_projects) != _BASE_TOTAL:
        raise ValueError("base manifest must contain exactly 200 projects")
    names: list[str] = []
    seen: set[str] = set()
    for expected_index, project in enumerate(base_projects, 1):
        if project.get("index") != expected_index:
            raise ValueError("base project indices must remain contiguous")
        name = project.get("name")
        normalized = normalize_repository(name)
        if normalized in seen:
            raise ValueError(f"duplicate base repository: {name}")
        seen.add(normalized)
        names.append(str(name))
    for case in poc_cases:
        name = case.get("app")
        normalized = normalize_repository(name)
        if normalized not in seen:
            seen.add(normalized)
            names.append(normalized)
    if len(names) != _ACTIVE_TOTAL:
        raise ValueError(f"original 200 plus PoC repository union must contain exactly 205 projects, got {len(names)}")
    return names


def _strict_readiness(row: Mapping[str, object], repo_root: Path) -> dict[str, object]:
    """Revalidate one row without changing its source or target identity fields."""
    result = dict(row)
    result.pop("database_fingerprint", None)
    result.pop("database_readiness_reason", None)
    source_path = result.get("source_path")
    database_path = result.get("codeql_path", result.get("database_path"))
    if not isinstance(source_path, str) or not isinstance(database_path, str):
        raise ValueError(f"target paths missing at index {result.get('index')}")
    source = repo_root / source_path
    database = repo_root / database_path
    if not source.is_dir() or source.is_symlink():
        raise ValueError(f"source snapshot missing or unsafe: {source_path}")
    fingerprint_type, checkout_fingerprint = _fingerprint(source)
    result["fingerprint_type"] = fingerprint_type
    result["checkout_fingerprint"] = checkout_fingerprint
    try:
        info = validate_database(database)
        if info.source_root.resolve(strict=False) != source.resolve(strict=True):
            result["codeql_built"] = False
            result["database_readiness_reason"] = "SOURCE_ROOT_MISMATCH"
        else:
            result["codeql_built"] = True
            result["database_fingerprint"] = info.fingerprint
    except (AnalyzerError, OSError, ValueError) as exc:
        result["codeql_built"] = False
        result["database_readiness_reason"] = (
            str(exc.details.get("reason", exc.code)) if isinstance(exc, AnalyzerError) else type(exc).__name__
        )
    return result


def _addition_row(index: int, name: str, repo_root: Path) -> dict[str, object]:
    slug = name.replace("/", "__")
    source_path = f"frameworks/applications/{slug}"
    source = repo_root / source_path
    if not source.is_dir() or source.is_symlink():
        raise ValueError(f"source snapshot missing or unsafe: {source_path}")
    fingerprint_type, checkout_fingerprint = _fingerprint(source)
    return _strict_readiness({
        "index": index,
        "name": name,
        "origin": "poc-29-union",
        "source_path": source_path,
        "fingerprint_type": fingerprint_type,
        "checkout_fingerprint": checkout_fingerprint,
        "codeql_path": f"databases/applications/{slug}-db",
        "coverage": "poc-29-repository-union",
    }, repo_root)


def build_manifest(base: Mapping[str, object], poc_cases: Sequence[Mapping[str, object]], repo_root: Path) -> dict[str, object]:
    projects = base.get("projects")
    if (
        base.get("schema_version") != 1
        or base.get("status") != "canonical"
        or base.get("corpus") != _BASE_CORPUS
        or base.get("total") != _BASE_TOTAL
        or not isinstance(projects, list)
        or any(not isinstance(row, Mapping) for row in projects)
    ):
        raise ValueError("invalid canonical Java Web 200 base manifest")
    names = compose_repository_names(projects, poc_cases)
    normalized_base = {normalize_repository(row.get("name")) for row in projects}
    normalized_poc = {normalize_repository(case.get("app")) for case in poc_cases}
    rows = [_strict_readiness(row, repo_root) for row in projects]
    rows.extend(_addition_row(index, name, repo_root) for index, name in enumerate(names[_BASE_TOTAL:], _BASE_TOTAL + 1))
    ready_count = sum(row.get("codeql_built") is True for row in rows)
    incomplete = [
        {
            "index": row["index"],
            "name": row["name"],
            "codeql_path": row["codeql_path"],
            "reason": row.get("database_readiness_reason", "DATABASE_NOT_READY"),
        }
        for row in rows if row.get("codeql_built") is not True
    ]
    return {
        "schema_version": 1,
        "status": "canonical",
        "generated_at": _GENERATED_AT,
        "corpus": _ACTIVE_CORPUS,
        "total": _ACTIVE_TOTAL,
        "valid_codeql_databases": ready_count,
        "database_incomplete_count": len(incomplete),
        "database_incomplete": incomplete,
        "database_incomplete_repositories": [item["name"] for item in incomplete],
        "batch_ready": ready_count == _ACTIVE_TOTAL,
        "construction": {
            "base_manifest": "intel/applications/java_web_200_targets.json",
            "base_total": _BASE_TOTAL,
            "union_manifest": "poc/manifest.json",
            "union_case_count": len(poc_cases),
            "union_repository_count": len(normalized_poc),
            "overlap_count": len(normalized_base & normalized_poc),
            "added_count": len(normalized_poc - normalized_base),
            "deduplication": "case-insensitive normalized owner/repository identity",
        },
        "projects": rows,
    }


def _read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", type=Path, default=DEFAULT_BASE_MANIFEST)
    parser.add_argument("--poc-manifest", type=Path, default=DEFAULT_POC_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        base = _read_json(args.base_manifest)
        cases = _read_json(args.poc_manifest)
        if not isinstance(base, Mapping) or not isinstance(cases, list) or any(not isinstance(case, Mapping) for case in cases):
            raise ValueError("inventory inputs have invalid JSON structure")
        manifest = build_manifest(base, cases, REPO_ROOT)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (AnalyzerError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"JAVA_WEB_205_INVENTORY_INVALID: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
