"""PoC-29 oracle normalization and reproducible corpus binding."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from dosweb.artifacts.identifiers import file_sha256, sha256_canonical_json, stable_identifier
from dosweb.batch.corpus import _tree_fingerprint
from dosweb.batch.models import CanonicalCorpus, CorpusTarget, TargetCapability, TargetIdentity
from dosweb.codeql.database import DatabaseInfo, validate_database
from dosweb.errors import AnalyzerError

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_EXCLUDED = frozenset({".agents", ".git", ".gradle", ".idea", ".mvn", "build", "node_modules", "out", "target"})


def normalize_repo(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("repository must be a string")
    normalized = value.strip().replace("\\", "/")
    if "/" not in normalized and "__" in normalized:
        normalized = normalized.replace("__", "/", 1)
    if not _REPOSITORY.fullmatch(normalized):
        raise ValueError(f"invalid repository: {value!r}")
    owner, repository = normalized.split("/", 1)
    return f"{owner.lower()}/{repository.lower()}"


def repo_slug(value: object) -> str:
    return normalize_repo(value).replace("/", "__")


def _safe_relative(value: str) -> str:
    if "\x00" in value:
        raise ValueError(f"unsafe asset path: {value!r}")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe asset path: {value!r}")
    return path.as_posix()


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate override key: {key}")
        result[key] = value
    return result


def load_source_overrides(path: Path | str, repo_root: Path) -> dict[str, dict[str, str]]:
    """Load strict provider checkout bindings for tree-attested analysis sources."""
    override_path = Path(path)
    if override_path.is_symlink() or not override_path.is_file():
        raise ValueError("source overrides must be a regular non-symlink file")
    try:
        raw = json.loads(
            override_path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("source overrides must be strict JSON") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("source overrides must be a JSON object")
    result: dict[str, dict[str, str]] = {}
    for repository, value in raw.items():
        normalized = normalize_repo(repository)
        if not isinstance(value, Mapping) or set(value) != {
            "source_path", "commit", "public_source_url", "analysis_tree_sha256",
        }:
            raise ValueError(f"source override for {normalized} has invalid fields")
        source_path = value.get("source_path")
        commit = value.get("commit")
        public_source_url = value.get("public_source_url")
        analysis_tree_sha256 = value.get("analysis_tree_sha256")
        if not isinstance(source_path, str):
            raise ValueError(f"source override for {normalized} must have a string path")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError(f"source override for {normalized} must have a full commit")
        if not isinstance(analysis_tree_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", analysis_tree_sha256):
            raise ValueError(f"source override for {normalized} must bind an analysis tree digest")
        expected_url = f"https://github.com/{normalized}"
        if public_source_url not in {expected_url, f"{expected_url}.git"}:
            raise ValueError(f"source override for {normalized} must use its canonical GitHub URL")
        relative = _safe_relative(source_path)
        checkout = _assert_nonsymlink(repo_root, relative)
        if not checkout.is_dir() or not (checkout / ".git").exists() or (checkout / ".git").is_symlink():
            raise ValueError(f"source override checkout missing or unsafe: {relative}")
        try:
            top = Path(subprocess.check_output(
                ["git", "-C", str(checkout), "rev-parse", "--show-toplevel"],
                text=True, stderr=subprocess.DEVNULL, timeout=30,
            ).strip()).resolve()
            head = subprocess.check_output(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                text=True, stderr=subprocess.DEVNULL, timeout=30,
            ).strip()
            origin = subprocess.check_output(
                ["git", "-C", str(checkout), "remote", "get-url", "origin"],
                text=True, stderr=subprocess.DEVNULL, timeout=30,
            ).strip().removesuffix(".git").lower()
            dirty = subprocess.check_output(
                ["git", "-C", str(checkout), "status", "--porcelain"],
                text=True, stderr=subprocess.DEVNULL, timeout=30,
            )
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise ValueError(f"source override checkout cannot be attested: {relative}") from exc
        if top != checkout.resolve() or head != commit or origin != expected_url or dirty:
            raise ValueError(f"source override checkout attestation mismatch: {relative}")
        result[normalized] = {
            "source_path": relative,
            "commit": commit,
            "public_source_url": expected_url,
            "analysis_tree_sha256": analysis_tree_sha256,
        }
    return result


def load_database_overrides(path: Path | str, repo_root: Path) -> dict[str, str]:
    """Load a strict repo -> repository-relative database path mapping."""
    override_path = Path(path)
    if override_path.is_symlink() or not override_path.is_file():
        raise ValueError("database overrides must be a regular non-symlink file")
    try:
        raw = json.loads(
            override_path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("database overrides must be strict JSON") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("database overrides must be a JSON object")
    result: dict[str, str] = {}
    for repository, database_path in raw.items():
        normalized = normalize_repo(repository)
        if not isinstance(database_path, str):
            raise ValueError(f"database override for {normalized} must be a string")
        result[normalized] = _safe_relative(database_path)
    return result


def _database_error(exc: BaseException) -> str:
    if isinstance(exc, AnalyzerError):
        reason = exc.details.get("reason") if isinstance(exc.details, Mapping) else None
        return str(reason or exc.code)
    return type(exc).__name__


def _assert_nonsymlink(repo_root: Path, relative: str) -> Path:
    current = repo_root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlinked asset path is not allowed: {relative}")
    return current


def _load(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: expected a regular file")
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: expected object")
    return value


def _source_fingerprint(source: Path) -> tuple[str, str]:
    git_dir = source / ".git"
    if git_dir.is_dir() and not git_dir.is_symlink():
        try:
            top = Path(
                subprocess.check_output(
                    ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                ).strip()
            ).resolve()
            head = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=30,
            ).strip()
            if top == source.resolve() and re.fullmatch(r"[0-9a-f]{40}", head):
                return "git-commit", head
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return "tree-sha256", _tree_fingerprint(source)


def build_asset_manifest(
    repositories: list[str],
    repo_root: Path,
    *,
    database_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    projects: list[dict[str, Any]] = []
    incomplete: list[dict[str, str]] = []
    overrides = {normalize_repo(key): value for key, value in (database_overrides or {}).items()}
    normalized_repositories = sorted({normalize_repo(repository) for repository in repositories})
    unknown_overrides = set(overrides) - set(normalized_repositories)
    if unknown_overrides:
        raise ValueError(f"database override has unknown repositories: {sorted(unknown_overrides)!r}")
    for index, repository in enumerate(normalized_repositories, 1):
        slug = repo_slug(repository)
        source_path = _safe_relative(f"frameworks/applications/{slug}")
        default_database_path = _safe_relative(f"databases/applications/{slug}-db")
        database_path = _safe_relative(overrides[repository]) if repository in overrides else default_database_path
        source = _assert_nonsymlink(repo_root, source_path)
        database = _assert_nonsymlink(repo_root, database_path)
        if not source.is_dir():
            raise ValueError(f"source asset missing or unsafe: {source_path}")
        info: DatabaseInfo | None = None
        incomplete_reason: str | None = None
        try:
            info = validate_database(database)
            if info.source_root.resolve(strict=False) != source.resolve(strict=False):
                incomplete_reason = "SOURCE_ROOT_MISMATCH"
        except (AnalyzerError, OSError, ValueError) as exc:
            incomplete_reason = _database_error(exc)
        if incomplete_reason:
            incomplete.append({"name": repository, "codeql_path": database_path, "reason": incomplete_reason})
        marker = database / "codeql-database.yml"
        if marker.is_symlink() or not marker.is_file():
            raise ValueError(f"database marker missing or unsafe: {database_path}")
        fingerprint_type, fingerprint = _source_fingerprint(source)
        row: dict[str, Any] = {
            "index": index,
            "name": repository,
            "source_path": source_path,
            "fingerprint_type": fingerprint_type,
            "checkout_fingerprint": fingerprint,
            "codeql_path": database_path,
            "codeql_built": info is not None and incomplete_reason is None,
            "database_origin": "override" if repository in overrides else "default",
            "coverage": "poc-29-truth-asset",
            "database_marker": {
                "path": f"{database_path}/codeql-database.yml",
                "sha256": file_sha256(marker),
            },
        }
        if info is not None and incomplete_reason is None:
            row["database_fingerprint"] = info.fingerprint
        projects.append(row)
    return {
        "schema_version": 1,
        "status": "canonical",
        "corpus": "poc-29",
        "total": len(normalized_repositories),
        "projects": projects,
        "source_asset_count": len(normalized_repositories),
        "database_ready_count": sum(1 for project in projects if project.get("codeql_built") is True),
        "database_incomplete": incomplete,
        "database_incomplete_repositories": [item["name"] for item in incomplete],
        "batch_ready": not incomplete and len(projects) == len(normalized_repositories),
    }


def corpus_from_manifest(
    manifest: Mapping[str, Any],
    repo_root: Path,
    *,
    source_overrides: Mapping[str, Mapping[str, str]] | None = None,
) -> CanonicalCorpus:
    projects = manifest.get("projects")
    source_asset_count = manifest.get("source_asset_count", manifest.get("total"))
    if (
        manifest.get("schema_version") != 1
        or manifest.get("status") != "canonical"
        or manifest.get("corpus") != "poc-29"
        or not isinstance(projects, list)
        or not isinstance(source_asset_count, int)
        or manifest.get("database_ready_count") != len(projects)
        or manifest.get("batch_ready") is not True
        or any(not isinstance(row, Mapping) for row in projects)
    ):
        raise ValueError("invalid or incomplete PoC-29 target manifest")
    overrides = {normalize_repo(key): value for key, value in (source_overrides or {}).items()}
    project_names = {normalize_repo(row.get("name")) for row in projects}
    unknown_overrides = set(overrides) - project_names
    if unknown_overrides:
        raise ValueError(f"source override has unknown repositories: {sorted(unknown_overrides)!r}")
    targets: list[CorpusTarget] = []
    for expected_index, row in enumerate(projects, 1):
        if not isinstance(row, Mapping) or row.get("index") != expected_index:
            raise ValueError("invalid PoC-29 target row")
        source_path = _safe_relative(str(row.get("source_path", "")))
        database_path = _safe_relative(str(row.get("codeql_path", "")))
        source = repo_root / source_path
        database = repo_root / database_path
        marker = row.get("database_marker")
        if not isinstance(marker, Mapping):
            raise ValueError("database marker is missing")
        marker_path = _safe_relative(str(marker.get("path", "")))
        if marker_path != f"{database_path}/codeql-database.yml":
            raise ValueError("database marker path mismatch")
        marker_file = repo_root / marker_path
        if marker.get("sha256") != file_sha256(marker_file):
            raise ValueError("database marker digest mismatch")
        try:
            info = validate_database(database)
        except (AnalyzerError, OSError, ValueError) as exc:
            raise ValueError(f"database validation failed: {_database_error(exc)}") from exc
        try:
            if info.source_root.resolve(strict=False) != source.resolve(strict=True):
                raise ValueError("database source root mismatch")
        except (OSError, RuntimeError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc) == "database source root mismatch":
                raise
            raise ValueError("database source root invalid") from exc
        actual_type, actual_fingerprint = _source_fingerprint(source)
        if (
            row.get("fingerprint_type") != actual_type
            or row.get("checkout_fingerprint") != actual_fingerprint
            or row.get("codeql_built") is not True
            or row.get("database_fingerprint") != info.fingerprint
        ):
            raise ValueError("source or database attestation drift")
        name = normalize_repo(row.get("name"))
        identity = TargetIdentity(
            expected_index,
            name,
            actual_type,
            actual_fingerprint,
            source_path,
            database_path,
        )
        source_override = overrides.get(name)
        if source_override is not None:
            provider_source_path = _safe_relative(str(source_override.get("source_path", "")))
            provider_source_commit = str(source_override.get("commit", ""))
            public_source_url = str(source_override.get("public_source_url", ""))
            expected_tree = str(source_override.get("analysis_tree_sha256", ""))
            if (
                not re.fullmatch(r"[0-9a-f]{40}", provider_source_commit)
                or public_source_url != f"https://github.com/{name}"
                or expected_tree != _tree_fingerprint(source)
            ):
                raise ValueError("source override attestation invalid")
        else:
            provider_source_path = source_path if actual_type == "git-commit" else None
            provider_source_commit = actual_fingerprint if actual_type == "git-commit" else None
            public_source_url = f"https://github.com/{name}" if actual_type == "git-commit" else None
        provider_eligible = provider_source_path is not None and provider_source_commit is not None
        capability = TargetCapability(
            provider_eligible=provider_eligible,
            public_source_url=public_source_url,
            attestation="git-commit" if provider_eligible else actual_type,
            reason=None if provider_eligible else "attestation_unavailable",
            provider_source_path=provider_source_path,
            provider_source_commit=provider_source_commit,
        )
        targets.append(
            CorpusTarget(
                identity,
                source,
                database,
                capability,
                info.fingerprint,
            )
        )
    return CanonicalCorpus(
        schema_version=1,
        status="canonical",
        corpus="poc-29",
        total=len(targets),
        inventory_digest=sha256_canonical_json(manifest),
        targets=tuple(targets),
        manifest_path=Path("targets.manifest.json"),
    )


def normalize_truth(
    source: Path,
    *,
    repo_root: Path | None = None,
    database_overrides: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    root = (repo_root or Path.cwd()).resolve()
    raw = _load(source)
    rows = raw.get("confirmed_true_positive")
    if not isinstance(rows, list):
        raise ValueError("confirmed_true_positive must be a list")
    source_digest = file_sha256(source)
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            errors.append("truth record is not an object")
            continue
        try:
            case_id = str(row.get("record_id") or row.get("finding_id") or row.get("title") or "").strip()
            if not case_id or case_id in seen:
                raise ValueError("missing or duplicate case id")
            repository = normalize_repo(row.get("app"))
            item = {
                "case_id": case_id,
                "repository": repository,
                "repo_slug": repo_slug(repository),
                "title": row.get("title") or row.get("finding_id") or case_id,
                "finding_id": row.get("finding_id"),
                "probe_id": row.get("probe_id"),
                "entry": row.get("entry"),
                "oracle": "dynamic.confirmed_true_positive",
                "dynamic_status": row.get("status"),
                "dynamic_verdict": row.get("verdict"),
                "dynamic_evidence": {
                    "failure_signal": row.get("failure_signal"),
                    "heap_or_limit": row.get("heap_or_limit"),
                    "strict_1g_evidence": row.get("strict_1g_evidence"),
                    "evidence_summary": row.get("evidence_summary"),
                    "requests_sent": row.get("requests_sent"),
                },
                "source_batch": row.get("source_batch"),
                "source_file": row.get("source_file"),
                "source_digest": source_digest,
            }
            identity = {
                key: item[key]
                for key in ("case_id", "repository", "title", "entry", "finding_id", "source_digest")
            }
            item["truth_id"] = stable_identifier("truth", identity)
            normalized.append(item)
            seen.add(case_id)
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
    normalized.sort(key=lambda item: item["case_id"])
    repositories = sorted({item["repository"] for item in normalized})
    try:
        manifest = build_asset_manifest(repositories, root, database_overrides=database_overrides)
    except ValueError as exc:
        errors.append(str(exc))
        manifest = {
            "schema_version": 1,
            "status": "invalid",
            "corpus": "poc-29",
            "total": len(repositories),
            "projects": [],
            "source_asset_count": len(repositories),
            "database_ready_count": 0,
            "database_incomplete": [],
            "batch_ready": False,
            "database_incomplete": [],
        }
    validation = {
        "schema_version": 1,
        "case_count": len(normalized),
        "repository_count": len(repositories),
        "repositories": repositories,
        "asset_count": manifest.get("source_asset_count", len(manifest["projects"])),
        "source_asset_count": manifest.get("source_asset_count", len(repositories)),
        "database_ready_count": manifest.get("database_ready_count", len(manifest["projects"])),
        "database_incomplete": manifest.get("database_incomplete", []),
        "database_incomplete_repositories": manifest.get("database_incomplete_repositories", []),
        "batch_ready": manifest.get("batch_ready", False),
        "source_digest": source_digest,
        "valid": not errors and len(normalized) == 29 and len(repositories) == 18,
        "errors": errors,
    }
    return normalized, validation, manifest
