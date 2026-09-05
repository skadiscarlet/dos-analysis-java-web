#!/usr/bin/env python3
"""Preflight or natively rebuild incomplete Java Web 205 CodeQL databases."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dosweb.artifacts.identifiers import file_sha256, sha256_canonical_json
from dosweb.batch.corpus import _fingerprint
from dosweb.codeql.database import validate_database
from dosweb.codeql.native_builder import (
    build_native_database,
    discover_native_build,
    load_override_file,
    validate_run_id,
)
from dosweb.errors import AnalyzerError

DEFAULT_MANIFEST = REPO_ROOT / "intel/applications/java_web_205_targets.json"
DEFAULT_DATABASE_ROOT = REPO_ROOT / "databases/applications"
DEFAULT_OVERRIDE = REPO_ROOT / "config/java_web_205_codeql_build_overrides.json"


def _read_object(path: Path) -> Mapping[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"manifest is missing or unsafe: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("manifest must be an object")
    return value


def _scope(manifest: Mapping[str, object]) -> list[Mapping[str, object]]:
    projects = manifest.get("projects")
    incomplete = manifest.get("database_incomplete")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("corpus") != "java-web-205"
        or manifest.get("total") != 205
        or not isinstance(projects, list)
        or not isinstance(incomplete, list)
    ):
        raise ValueError("invalid Java Web 205 manifest")
    by_name = {
        str(row.get("name", "")).casefold(): row
        for row in projects
        if isinstance(row, Mapping)
    }
    result: list[Mapping[str, object]] = []
    for item in incomplete:
        if not isinstance(item, Mapping) or item.get("reason") != "JAVA_DATABASE_REQUIRED":
            raise ValueError("repair scope contains an unsupported readiness reason")
        row = by_name.get(str(item.get("name", "")).casefold())
        if row is None or row.get("index") != item.get("index"):
            raise ValueError("repair scope does not bind to a canonical project")
        result.append(row)
    if len(result) != manifest.get("database_incomplete_count"):
        raise ValueError("repair scope count mismatch")
    return result


def _relative_path(row: Mapping[str, object], field: str) -> Path:
    value = row.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{field} is missing")
    path = Path(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{field} is unsafe")
    return path


def _valid_attestation(row: object) -> bool:
    if not isinstance(row, Mapping) or row.get("schema_version") != 1 or row.get("status") != "success":
        return False
    required_strings = (
        "repository",
        "source_fingerprint_type",
        "source_fingerprint_before",
        "source_fingerprint_after",
        "database_path",
        "database_fingerprint",
        "build_kind",
        "build_command",
        "working_directory",
        "java_home",
        "attestation_digest",
    )
    if not all(isinstance(row.get(key), str) and row.get(key) for key in required_strings):
        return False
    setup_commands = row.get("setup_commands")
    setup_results = row.get("setup_results")
    if (
        not isinstance(setup_commands, list)
        or not all(isinstance(item, str) and item for item in setup_commands)
        or not isinstance(setup_results, list)
        or len(setup_results) != len(setup_commands)
    ):
        return False
    expected = str(row["attestation_digest"])
    unsigned = dict(row)
    unsigned.pop("attestation_digest", None)
    return sha256_canonical_json(unsigned) == expected


def _latest_attestations(path: Path) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                print(
                    f"JAVA_WEB_205_NATIVE_ATTESTATION_IGNORED: malformed line {line_number} in {path}",
                    file=sys.stderr,
                )
                continue
            if _valid_attestation(row):
                result[str(row["repository"]).casefold()] = row
    return result


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _preflight_row(row: Mapping[str, object], overrides: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    repository = str(row["name"])
    source_relative = _relative_path(row, "source_path")
    database_relative = _relative_path(row, "codeql_path")
    source = REPO_ROOT / source_relative
    database = REPO_ROOT / database_relative
    if not source.is_dir() or source.is_symlink():
        raise ValueError(f"source is missing or unsafe: {source_relative}")
    if database.is_symlink():
        raise ValueError(f"database path is symlinked: {database_relative}")
    try:
        spec = discover_native_build(source, repository, overrides.get(repository.casefold()))
        build = spec.to_dict()
        build_error = None
    except ValueError as exc:
        build = None
        build_error = str(exc)
    fingerprint_type, fingerprint = _fingerprint(source)
    try:
        info = validate_database(database)
        database_status = "valid"
        database_fingerprint = info.fingerprint
    except (AnalyzerError, OSError, ValueError) as exc:
        database_status = (
            str(exc.details.get("reason", exc.code)) if isinstance(exc, AnalyzerError) else type(exc).__name__
        )
        database_fingerprint = None
    return {
        "index": row["index"],
        "repository": repository,
        "source_path": source_relative.as_posix(),
        "database_path": database_relative.as_posix(),
        "source_fingerprint_type": fingerprint_type,
        "source_fingerprint": fingerprint,
        "java_file_count": sum(1 for path in source.rglob("*.java") if path.is_file()),
        "database_status": database_status,
        "database_fingerprint": database_fingerprint,
        "build": build,
        "build_discovery_error": build_error,
    }


def _summary(result_root: Path, rows: list[Mapping[str, object]], status: str) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get("status", row.get("database_status", "unknown")))
        counts[value] = counts.get(value, 0) + 1
    lines = [
        "# Java Web 205 native CodeQL database repair",
        "",
        f"- status: `{status}`",
        f"- scope: {len(rows)}",
        "- acceptance: native Maven/Gradle/Ant build and strict CodeQL validation only",
        "- bounded/source-only/autobuild fallback: disabled",
        "",
        "## Counts",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(counts.items())],
    ]
    (result_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--result-root", type=Path)
    parser.add_argument("--override-file", type=Path, default=DEFAULT_OVERRIDE)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--build-timeout-minutes", type=int, default=120)
    parser.add_argument("--codeql-binary", default="codeql")
    parser.add_argument("--execute", action="store_true", help="Run native builds. Without this flag, only preflight is performed.")
    args = parser.parse_args(argv)
    try:
        run_id = validate_run_id(args.run_id)
        if args.build_timeout_minutes <= 0:
            raise ValueError("build timeout must be positive")
        result_root = (args.result_root or REPO_ROOT / f"results/application_dbs/java_web_205_native_{run_id}").resolve()
        if result_root.exists() and result_root.is_symlink():
            raise ValueError("result root cannot be a symlink")
        result_root.mkdir(parents=True, exist_ok=True)
        manifest = _read_object(args.manifest.resolve())
        scope = _scope(manifest)
        requested = {value.casefold() for value in args.only}
        if requested:
            known = {str(row["name"]).casefold() for row in scope}
            unknown = requested - known
            if unknown:
                raise ValueError(f"--only contains repositories outside repair scope: {sorted(unknown)}")
            scope = [row for row in scope if str(row["name"]).casefold() in requested]
        overrides = load_override_file(args.override_file.resolve())
        preflight = [_preflight_row(row, overrides) for row in scope]
        baseline = {
            "schema_version": 1,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "manifest": str(args.manifest.resolve()),
            "manifest_sha256": file_sha256(args.manifest.resolve()),
            "canonical_scope_count": len(_scope(manifest)),
            "selected_scope_count": len(scope),
            "network_build_execution": bool(args.execute),
            "clone_missing": False,
            "targets": preflight,
        }
        _write_json(result_root / "preflight.json", baseline)
        _write_json(result_root / "repair_scope.json", [
            {key: row[key] for key in ("index", "repository", "source_path", "database_path", "source_fingerprint_type", "source_fingerprint")}
            for row in preflight
        ])
        if not args.execute:
            _summary(result_root, preflight, "preflight_complete")
            return 0
        attestations_path = result_root / "native_build_attestations.jsonl"
        completed = _latest_attestations(attestations_path)
        outcomes: list[Mapping[str, object]] = []
        for item in preflight:
            repository = str(item["repository"])
            previous = completed.get(repository.casefold())
            database = REPO_ROOT / str(item["database_path"])
            source = REPO_ROOT / str(item["source_path"])
            spec = discover_native_build(source, repository, overrides.get(repository.casefold()))
            if previous is not None:
                try:
                    info = validate_database(database)
                except Exception:
                    pass
                else:
                    resume_bindings = (
                        previous.get("repository") == repository,
                        previous.get("source_fingerprint_type") == item["source_fingerprint_type"],
                        previous.get("source_fingerprint_before") == item["source_fingerprint"],
                        previous.get("source_fingerprint_after") == item["source_fingerprint"],
                        previous.get("database_path") == str(database),
                        previous.get("database_fingerprint") == info.fingerprint,
                        previous.get("build_kind") == spec.kind,
                        previous.get("build_command") == spec.command,
                        previous.get("setup_commands") == list(spec.setup_commands),
                        previous.get("working_directory") == spec.working_directory,
                        previous.get("java_home") in {str(path) for path in spec.java_homes},
                    )
                    if all(resume_bindings) and info.source_root.resolve(strict=False) == source.resolve(strict=True):
                        outcomes.append({"repository": repository, "status": "resumed_success"})
                        continue
            try:
                result = build_native_database(
                    repository=repository,
                    source=source,
                    target=database,
                    spec=spec,
                    run_id=run_id,
                    database_root=DEFAULT_DATABASE_ROOT,
                    result_root=result_root,
                    timeout_seconds=args.build_timeout_minutes * 60,
                    codeql_binary=args.codeql_binary,
                )
            except Exception as exc:
                outcomes.append({
                    "repository": repository,
                    "status": "failed",
                    "reason": "TARGET_EXECUTION_FAILED",
                    "diagnostic": type(exc).__name__,
                })
                continue
            outcomes.append(dict(result.record))
        failed = [row for row in outcomes if row.get("status") not in {"success", "resumed_success", "skipped_existing_valid"}]
        status = "completed" if not failed and len(outcomes) == len(scope) else "completed_with_failures"
        _write_json(result_root / "run.json", {"schema_version": 1, "run_id": run_id, "status": status, "target_count": len(scope), "failed_count": len(failed)})
        _summary(result_root, outcomes, status)
        return 0 if status == "completed" else 1
    except (AnalyzerError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"JAVA_WEB_205_NATIVE_REPAIR_INVALID: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
