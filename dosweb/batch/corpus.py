"""Strict loader for the tracked canonical Java Web corpus."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.codeql.database import DatabaseInfo, validate_database
from dosweb.errors import AnalyzerError
from dosweb.batch.models import CanonicalCorpus, CorpusTarget, TargetCapability, TargetIdentity

_DEFAULT_MANIFEST = "intel/applications/java_web_200_targets.json"
_FINGERPRINT_RE = {"git-commit": re.compile(r"^[0-9a-f]{40}$"), "tree-sha256": re.compile(r"^[0-9a-f]{64}$")}
_OWNER_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_EXCLUDED_TREE_PARTS = frozenset({".git", ".gradle", ".idea", ".mvn", "build", "node_modules", "out", "target"})
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 100_000


def _invalid(reason: str, **details: object) -> AnalyzerError:
    safe = {key: str(value)[:256] for key, value in details.items() if key not in {"secret", "api_key"}}
    safe["reason"] = reason
    return AnalyzerError("BATCH_CORPUS_INVALID", "Canonical corpus validation failed.", safe)


def _safe_relative(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise _invalid("PATH_REQUIRED", field=field)
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise _invalid("UNSAFE_RELATIVE_PATH", field=field)
    return path.as_posix()


def resolve_repo_relative(repo_root: Path | str, relative: str, *, field: str = "path") -> Path:
    """Resolve a manifest path while rejecting escapes and symlinked path components."""
    root = Path(repo_root).resolve(strict=True)
    rel = _safe_relative(relative, field)
    current = root
    for part in PurePosixPath(rel).parts:
        current = current / part
        try:
            if current.is_symlink():
                raise _invalid("SYMLINK_PATH_UNSUPPORTED", field=field)
        except OSError as exc:
            raise _invalid("PATH_STAT_FAILED", field=field) from exc
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _invalid("PATH_ESCAPE_OR_MISSING", field=field) from exc
    return resolved


def _own_git_head(source: Path) -> str | None:
    if not (source / ".git").exists() or (source / ".git").is_symlink():
        return None
    try:
        top = Path(subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL, timeout=30,
        ).strip()).resolve()
        if top != source.resolve():
            return None
        value = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL, timeout=30,
        ).strip()
        return value if re.fullmatch(r"[0-9a-f]{40}", value) else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _iter_source_files(source: Path):
    for path in source.rglob("*"):
        try:
            info = path.lstat()
        except OSError as exc:
            raise _invalid("SOURCE_STAT_FAILED", path=path.name) from exc
        if stat.S_ISLNK(info.st_mode):
            raise _invalid("SOURCE_SYMLINK_UNSUPPORTED", path=path.name)
        if not stat.S_ISREG(info.st_mode):
            continue
        relative = path.relative_to(source)
        if any(part in _EXCLUDED_TREE_PARTS for part in relative.parts):
            continue
        yield path


def _tree_fingerprint(source: Path) -> str:
    digest = hashlib.sha256()
    paths = sorted(_iter_source_files(source), key=lambda item: item.relative_to(source).as_posix())
    for path in paths:
        relative = path.relative_to(source).as_posix()
        digest.update(relative.encode("utf-8", "surrogateescape"))
        digest.update(b"\0")
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise _invalid("SOURCE_READ_FAILED", path=relative) from exc
        digest.update(b"\0")
    return digest.hexdigest()


def _fingerprint(source: Path) -> tuple[str, str]:
    try:
        head = _own_git_head(source)
        return ("git-commit", head) if head else ("tree-sha256", _tree_fingerprint(source))
    except (OSError, RuntimeError, ValueError, TypeError, MemoryError, RecursionError) as exc:
        if isinstance(exc, AnalyzerError):
            raise
        raise _invalid("FINGERPRINT_FAILED", path=source.name) from exc


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate JSON key")
        output[key] = value
    return output


def _strict_json_load(path: Path) -> object:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_MANIFEST_BYTES:
            raise _invalid("MANIFEST_FILE_UNSAFE")
        with path.open("rb") as stream:
            raw = stream.read(_MAX_MANIFEST_BYTES + 1)
        if len(raw) > _MAX_MANIFEST_BYTES:
            raise _invalid("MANIFEST_TOO_LARGE")
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)), object_pairs_hook=_unique_json_object)
    except AnalyzerError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
        raise _invalid("MANIFEST_READ_FAILED") from exc
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if depth > _MAX_JSON_DEPTH or nodes > _MAX_JSON_NODES:
            raise _invalid("MANIFEST_STRUCTURE_LIMIT")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
    return value


def _validate_row(row: Mapping[str, object], expected_index: int, repo_root: Path, db_validator: Callable[..., DatabaseInfo]) -> CorpusTarget:
    if not isinstance(row, Mapping):
        raise _invalid("PROJECT_ROW_NOT_OBJECT", index=expected_index)
    index = row.get("index")
    name = row.get("name", row.get("slug"))
    if index != expected_index or not isinstance(name, str) or not _OWNER_RE.fullmatch(name):
        raise _invalid("PROJECT_IDENTITY_INVALID", index=expected_index)
    fingerprint_type = row.get("fingerprint_type")
    fingerprint = row.get("checkout_fingerprint")
    if fingerprint_type not in _FINGERPRINT_RE or not isinstance(fingerprint, str) or not _FINGERPRINT_RE[fingerprint_type].fullmatch(fingerprint):
        raise _invalid("FINGERPRINT_FORMAT_INVALID", index=index)
    if row.get("codeql_built") is not True:
        raise _invalid("DATABASE_NOT_ATTESTED", index=index)
    source_path = _safe_relative(row.get("source_path"), "source_path")
    database_path = _safe_relative(row.get("codeql_path", row.get("database_path")), "codeql_path")
    source = resolve_repo_relative(repo_root, source_path, field="source_path")
    database = resolve_repo_relative(repo_root, database_path, field="codeql_path")
    actual_type, actual_fingerprint = _fingerprint(source)
    if actual_type != fingerprint_type or actual_fingerprint != fingerprint:
        raise _invalid("SOURCE_FINGERPRINT_DRIFT", index=index)
    try:
        info = db_validator(database)
    except AnalyzerError:
        raise
    except Exception as exc:
        raise _invalid("DATABASE_VALIDATION_FAILED", index=index) from exc
    if not isinstance(info, DatabaseInfo):
        raise _invalid("DATABASE_VALIDATOR_RESULT_INVALID", index=index)
    try:
        if info.source_root.resolve(strict=False) != source.resolve(strict=True):
            raise _invalid("DATABASE_SOURCE_ROOT_MISMATCH", index=index)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _invalid("DATABASE_SOURCE_ROOT_INVALID", index=index) from exc
    capability = TargetCapability(
        provider_eligible=fingerprint_type == "git-commit",
        public_source_url=f"https://github.com/{name}" if fingerprint_type == "git-commit" else None,
        attestation=fingerprint_type,
        reason=None if fingerprint_type == "git-commit" else "attestation_unavailable",
    )
    identity = TargetIdentity(index, name, fingerprint_type, fingerprint, source_path, database_path)
    return CorpusTarget(identity, source, database, capability, info.fingerprint)


def load_canonical_corpus(
    manifest_path: Path | str | None = None,
    *,
    repo_root: Path | str | None = None,
    expected_total: int = 200,
    database_validator: Callable[..., DatabaseInfo] = validate_database,
) -> CanonicalCorpus:
    """Load and validate the canonical inventory before any batch output is created."""
    manifest = Path(manifest_path or _DEFAULT_MANIFEST)
    if not manifest.is_absolute():
        base = Path(repo_root or Path.cwd()).resolve()
        manifest = base / manifest
    # A manifest is an input boundary too: reject a symlink before resolving it.
    try:
        if manifest.is_symlink():
            raise _invalid("MANIFEST_SYMLINK_UNSUPPORTED")
    except OSError as exc:
        raise _invalid("MANIFEST_STAT_FAILED") from exc
    manifest = manifest.resolve()
    root = Path(repo_root or manifest.parents[2]).resolve(strict=True)
    raw = _strict_json_load(manifest)
    if not isinstance(raw, Mapping):
        raise _invalid("MANIFEST_NOT_OBJECT")
    if raw.get("schema_version") != 1 or raw.get("status") != "canonical" or raw.get("corpus") != "java-web-200":
        raise _invalid("MANIFEST_IDENTITY_INVALID")
    if raw.get("total") != expected_total:
        raise _invalid("TOTAL_MISMATCH", expected=expected_total)
    projects = raw.get("projects")
    if not isinstance(projects, list) or len(projects) != expected_total:
        raise _invalid("PROJECT_COUNT_INVALID")
    targets: list[CorpusTarget] = []
    names: set[str] = set()
    indices: set[int] = set()
    for expected_index, row in enumerate(projects, 1):
        target = _validate_row(row, expected_index, root, database_validator)
        if target.name.lower() in names or target.index in indices:
            raise _invalid("PROJECT_DUPLICATE", index=target.index)
        names.add(target.name.lower())
        indices.add(target.index)
        targets.append(target)
    if indices != set(range(1, expected_total + 1)):
        raise _invalid("INDICES_NOT_CONTIGUOUS")
    inventory_digest = sha256_canonical_json(raw)
    return CanonicalCorpus(
        schema_version=1, status="canonical", corpus="java-web-200", total=expected_total,
        inventory_digest=inventory_digest, targets=tuple(targets), manifest_path=manifest,
        generated_at=raw.get("generated_at") if isinstance(raw.get("generated_at"), str) else None,
    )

load_corpus = load_canonical_corpus

__all__ = ["load_canonical_corpus", "load_corpus", "resolve_repo_relative"]
