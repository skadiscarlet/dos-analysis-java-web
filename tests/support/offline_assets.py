"""Small offline fixtures and explicit skip guards for optional large assets.

These helpers never mount or rewrite canonical frameworks/databases/results.
Integration tests must skip only when a named required asset is absent.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

from dosweb.artifacts.identifiers import file_sha256
from dosweb.batch.corpus import _fingerprint
from dosweb.benchmark.truth import repo_slug
from dosweb.codeql.database import DatabaseInfo, validate_database


POC29_TRUTH = Path("results/applications_dynamic_validation/binary_truth_collection.json")
POC29_ENTRIES_ARCHIVE = Path(
    "build/poc29-entries-poc29-entries-20260803-a/targets/010-openzipkin__zipkin"
)
POC29_SOURCE_OVERRIDES = Path("config/poc29_full_source_overrides.json")
JAVA_WEB_200_MANIFEST = Path("intel/applications/java_web_200_targets.json")
JAVA_WEB_205_MANIFEST = Path("intel/applications/java_web_205_targets.json")
POC29_SYNTHETIC_REPOS = tuple(f"fixture{index:02d}/app" for index in range(1, 19))


def skip_unless_present(path: Path, reason: str) -> None:
    if path.is_symlink():
        raise AssertionError(f"unsafe symbolic-link asset: {path}")
    if not path.exists():
        raise unittest.SkipTest(reason)


def write_minimal_codeql_database(database: Path, source: Path) -> Path:
    (database / "db-java").mkdir(parents=True, exist_ok=True)
    (database / "codeql-database.yml").write_text(
        yaml.safe_dump(
            {
                "primaryLanguage": "java",
                "sourceLocationPrefix": str(source.resolve()),
                "creationMetadata": {"cliVersion": "2.20.0"},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return database


def write_ready_application_pair(root: Path, repository: str) -> dict[str, str]:
    slug = repo_slug(repository)
    source_path = f"frameworks/applications/{slug}"
    database_path = f"databases/applications/{slug}-db"
    source = root / source_path
    database = root / database_path
    source.mkdir(parents=True, exist_ok=True)
    class_name = "".join(part.capitalize() for part in slug.replace("-", "_").split("_") if part)
    (source / f"{class_name or 'Main'}.java").write_text(
        f"class {class_name or 'Main'} {{}}\n",
        encoding="utf-8",
    )
    write_minimal_codeql_database(database, source)
    fingerprint_type, fingerprint = _fingerprint(source)
    info = validate_database(database)
    marker = database / "codeql-database.yml"
    return {
        "name": repository,
        "source_path": source_path,
        "codeql_path": database_path,
        "fingerprint_type": fingerprint_type,
        "checkout_fingerprint": fingerprint,
        "database_fingerprint": info.fingerprint,
        "marker_path": f"{database_path}/codeql-database.yml",
        "marker_sha256": file_sha256(marker),
    }


def write_synthetic_poc29_truth(root: Path) -> Path:
    """Create 29 historical-batch cases over 18 tiny ready source/database pairs."""
    for repository in POC29_SYNTHETIC_REPOS:
        write_ready_application_pair(root, repository)
    cases: list[dict[str, object]] = []
    case_id = 1
    for index, repository in enumerate(POC29_SYNTHETIC_REPOS):
        copies = 2 if index < 11 else 1
        for _ in range(copies):
            cases.append(
                {
                    "record_id": f"CASE-{case_id:04d}",
                    "app": repository,
                    "source_batch": "p0",
                    "status": "confirmed_oom",
                    "verdict": "confirmed",
                    "title": f"synthetic fixture case {case_id}",
                    "entry": "POST /fixture",
                    "finding_id": f"FIND-{case_id:04d}",
                }
            )
            case_id += 1
    if len(cases) != 29:
        raise AssertionError(f"synthetic PoC-29 oracle must contain 29 cases, got {len(cases)}")
    truth = root / POC29_TRUTH
    truth.parent.mkdir(parents=True, exist_ok=True)
    truth.write_text(json.dumps({"confirmed_true_positive": cases}), encoding="utf-8")
    return truth


def _require_manifest_assets(repo_root: Path, relative_manifest: Path, total: int) -> None:
    manifest = repo_root / relative_manifest
    if manifest.is_symlink() or not manifest.is_file():
        raise AssertionError(f"required tracked manifest missing or unsafe: {manifest}")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    projects = payload.get("projects")
    if not isinstance(projects, list) or len(projects) != total:
        raise AssertionError(f"tracked manifest must contain {total} projects")
    # Validate all declarations before optional-asset checks, so a missing
    # first checkout cannot conceal a malformed later manifest record.
    paths = []
    for project in projects:
        for field in ("source_path", "codeql_path"):
            raw = project[field]
            if not isinstance(raw, str) or not raw:
                raise AssertionError(f"invalid {field}")
            relative = Path(raw)
            if relative.is_absolute() or ".." in relative.parts:
                raise AssertionError(f"unsafe {field}")
            current = repo_root
            for part in relative.parts:
                current /= part
                if current.is_symlink():
                    raise AssertionError(f"unsafe symbolic-link asset: {current}")
            if current.exists() and not current.is_dir():
                raise AssertionError(f"asset is not a directory: {current}")
            paths.append(current)
    for path in paths:
        skip_unless_present(path, f"optional historical source/database asset missing: {path}")


def require_java_web_205_assets(repo_root: Path) -> None:
    _require_manifest_assets(repo_root, JAVA_WEB_205_MANIFEST, 205)


def require_java_web_200_assets(repo_root: Path) -> None:
    _require_manifest_assets(repo_root, JAVA_WEB_200_MANIFEST, 200)


def require_poc29_truth_assets(repo_root: Path) -> Path:
    truth = repo_root / POC29_TRUTH
    skip_unless_present(
        truth,
        f"PoC-29 truth collection missing: {POC29_TRUTH}",
    )
    skip_unless_present(
        repo_root / "frameworks/applications",
        "PoC-29 source assets missing: frameworks/applications",
    )
    skip_unless_present(
        repo_root / "databases/applications",
        "PoC-29 CodeQL databases missing: databases/applications",
    )
    return truth


def require_poc29_entries_archive(repo_root: Path) -> Path:
    target = repo_root / POC29_ENTRIES_ARCHIVE
    skip_unless_present(
        target,
        f"PoC-29 entries archive missing: {POC29_ENTRIES_ARCHIVE}",
    )
    return target


def require_poc29_source_override_checkouts(repo_root: Path) -> Path:
    overrides = repo_root / POC29_SOURCE_OVERRIDES
    if overrides.is_symlink() or not overrides.is_file():
        raise AssertionError("required tracked source override manifest missing or unsafe")
    payload = json.loads(overrides.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise AssertionError("source override manifest must be a nonempty mapping")
    for value in payload.values():
        relative = Path(value["source_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise AssertionError("unsafe source override path")
        skip_unless_present(repo_root / relative, f"source override checkout missing: {relative}")
    return overrides


def database_info_for(source: Path, database: Path) -> DatabaseInfo:
    return DatabaseInfo(database, source, "d" * 64)
