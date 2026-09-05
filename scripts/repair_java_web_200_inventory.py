#!/usr/bin/env python3
"""Repair and publish the preserved canonical 200-project Java Web corpus.

This utility retains the original Java Web 200 repair and publication semantics.
The active 205-project inventory is constructed separately by
``generate_java_web_205_inventory.py``.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OLD_RUN = REPO_ROOT / "results/application_dbs/java_web_200_20260718"
DEFAULT_RUN_ROOT = REPO_ROOT / "results/application_dbs/java_web_200_20260725"
DEFAULT_SOURCE_ROOT = REPO_ROOT / "frameworks/applications"
DEFAULT_DB_ROOT = REPO_ROOT / "databases/applications"
DEFAULT_TRACKED_MANIFEST = REPO_ROOT / "intel/applications/java_web_200_targets.json"
REMOVED_SLUG = "jeecgboot/qiaoqiaoyun"
EXCLUDED_TREE_PARTS = {".git", ".gradle", ".idea", ".mvn", "build", "node_modules", "out", "target"}


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def normalize_slug(slug: str) -> str:
    return slug.strip().lower()


def safe_name(slug: str) -> str:
    return slug.replace("/", "__")


def run_command(command: list[str], *, cwd: Path, log: Path | None = None, timeout: int = 2700) -> subprocess.CompletedProcess[bytes]:
    output = subprocess.PIPE
    handle = None
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        handle = log.open("ab")
        handle.write((f"\n===== {now()} =====\n{' '.join(command)}\n").encode())
        output = handle
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            env={**os.environ, "JAVA_HOME": "/usr/lib/jvm/java-21-openjdk"},
        )
    finally:
        if handle is not None:
            handle.close()


def own_git_head(source: Path) -> str | None:
    if not (source / ".git").exists():
        return None
    try:
        top = Path(
            subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=30,
            ).strip()
        ).resolve()
        if top != source.resolve():
            return None
        return subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def iter_source_files(source: Path) -> Iterable[Path]:
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part in EXCLUDED_TREE_PARTS for part in relative.parts):
            continue
        yield path


def java_file_count(source: Path) -> int:
    return sum(1 for path in iter_source_files(source) if path.suffix == ".java")


def tree_fingerprint(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(iter_source_files(source), key=lambda item: str(item.relative_to(source))):
        relative = str(path.relative_to(source))
        digest.update(relative.encode("utf-8", "surrogateescape"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def source_fingerprint(source: Path) -> tuple[str, str]:
    head = own_git_head(source)
    if head:
        return "git-commit", head
    if source.is_dir():
        return "tree-sha256", tree_fingerprint(source)
    return "missing", ""


def database_present(database: Path) -> bool:
    """Match the historical corpus build-status convention."""
    return (database / "codeql-database.yml").is_file()


def database_valid(database: Path) -> bool:
    """Require verified Java extraction for newly created databases."""
    relation = database / "db-java/default/compilation_compiling_files.rel"
    return (
        database_present(database)
        and (database / "db-java").is_dir()
        and relation.is_file()
        and relation.stat().st_size > 0
    )


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def ensure_source(slug: str, source_root: Path, run_root: Path) -> tuple[Path, str]:
    source = source_root / safe_name(slug)
    if not source.exists():
        result = run_command(
            ["git", "clone", "--depth", "1", f"https://github.com/{slug}.git", str(source)],
            cwd=REPO_ROOT,
            log=run_root / "logs" / f"{safe_name(slug)}.clone.log",
            timeout=1200,
        )
        if result.returncode != 0:
            if source.exists() and own_git_head(source) is None:
                shutil.rmtree(source)
            raise RuntimeError(f"clone failed for {slug} with exit code {result.returncode}")
    head = own_git_head(source)
    if not head:
        raise RuntimeError(f"{source} is not an independent Git checkout")
    count = java_file_count(source)
    if count == 0:
        raise RuntimeError(f"{source} contains no Java source files")
    return source, head


def ensure_database(slug: str, source: Path, db_root: Path, run_root: Path) -> Path:
    database = db_root / f"{safe_name(slug)}-db"
    if database.exists():
        if database_valid(database):
            return database
        raise RuntimeError(f"refusing to overwrite invalid existing database: {database}")

    db_root.mkdir(parents=True, exist_ok=True)
    temporary_parent = db_root / ".java-web-200-repair-tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f"{safe_name(slug)}-", dir=temporary_parent))
    shutil.rmtree(temporary)
    try:
        result = run_command(
            [
                "codeql",
                "database",
                "create",
                str(temporary),
                "--language=java",
                "--build-mode=none",
                f"--source-root={source}",
            ],
            cwd=source,
            log=run_root / "logs" / f"{safe_name(slug)}.codeql-none.log",
            timeout=2700,
        )
        if result.returncode != 0 or not database_valid(temporary):
            raise RuntimeError(f"CodeQL source-only build failed for {slug} with exit code {result.returncode}")
        # CodeQL CLI 2.23.8 has no `database check` subcommand. The finalized
        # marker, Java DB directory, and non-empty compilation relation are the
        # strongest locally available source-extraction checks.
        temporary.rename(database)
        return database
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def load_old_projects(old_run: Path) -> list[dict[str, str]]:
    payload = json.loads((old_run / "final_200.json").read_text(encoding="utf-8"))
    projects = payload.get("projects")
    if not isinstance(projects, list):
        raise ValueError("old final_200.json does not contain a projects list")
    return projects


def compose_projects(old_projects: list[dict[str, str]], replacement: str) -> list[dict[str, str]]:
    removed = normalize_slug(REMOVED_SLUG)
    output = [dict(project) for project in old_projects if normalize_slug(project["slug"]) != removed]
    if len(output) != len(old_projects) - 1:
        raise ValueError(f"expected exactly one {REMOVED_SLUG} entry")
    existing = {normalize_slug(project["slug"]) for project in output}
    if normalize_slug(replacement) in existing:
        raise ValueError(f"replacement is already selected: {replacement}")
    output.append({"slug": replacement, "origin": "new"})
    normalized = [normalize_slug(project["slug"]) for project in output]
    if len(output) != 200 or len(set(normalized)) != 200:
        raise ValueError("canonical corpus must contain exactly 200 unique projects")
    return output


def directory_map(root: Path, suffix: str = "") -> dict[str, Path]:
    return {
        path.name.lower(): path
        for path in root.iterdir()
        if path.is_dir() and (not suffix or path.name.lower().endswith(suffix.lower()))
    }


def build_inventory(projects: list[dict[str, str]], source_root: Path, db_root: Path) -> list[dict[str, Any]]:
    sources = directory_map(source_root)
    databases = directory_map(db_root, "-db")
    rows: list[dict[str, Any]] = []
    for index, project in enumerate(projects, 1):
        slug = project["slug"]
        name = safe_name(slug)
        source = sources.get(name.lower(), source_root / name)
        database = databases.get(f"{name}-db".lower(), db_root / f"{name}-db")
        kind, fingerprint = source_fingerprint(source)
        built = database_valid(database) if project.get("origin") == "new" else database_present(database)
        rows.append(
            {
                "index": index,
                "name": slug,
                "origin": project.get("origin", "existing"),
                "source_path": str(source.relative_to(REPO_ROOT)),
                "fingerprint_type": kind,
                "checkout_fingerprint": fingerprint,
                "codeql_path": str(database.relative_to(REPO_ROOT)),
                "codeql_built": built,
                "coverage": "source_only" if project.get("origin") == "new" else "existing_database",
            }
        )
    return rows


def write_inventory(run_root: Path, projects: list[dict[str, str]], rows: list[dict[str, Any]], replacement: str) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    retained = [project["slug"] for project in projects if project.get("origin") != "new"]
    selected_new = [project["slug"] for project in projects if project.get("origin") == "new"]
    (run_root / "retained_existing_149.txt").write_text("\n".join(retained) + "\n", encoding="utf-8")
    (run_root / "selected_new_51.txt").write_text("\n".join(selected_new) + "\n", encoding="utf-8")
    (run_root / "selected_new_51.json").write_text(json.dumps(selected_new, indent=2) + "\n", encoding="utf-8")
    (run_root / "final_200.txt").write_text("\n".join(project["slug"] for project in projects) + "\n", encoding="utf-8")
    final_payload = {
        "generated_at": now(),
        "total": 200,
        "retained_existing_count": len(retained),
        "new_count": len(selected_new),
        "removed": REMOVED_SLUG,
        "replacement": replacement,
        "projects": projects,
    }
    (run_root / "final_200.json").write_text(json.dumps(final_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_root / "final_200_inventory.json").write_text(json.dumps({"count": len(rows), "projects": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (run_root / "final_200_inventory.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Canonical Java Web 200 Project Inventory",
        "",
        f"- Total: **{len(rows)}**",
        f"- CodeQL built: **{sum(row['codeql_built'] for row in rows)}**",
        f"- Replacement: `{REMOVED_SLUG}` → `{replacement}`",
        "",
        "| # | Name | Source | Checkout fingerprint | CodeQL DB | Built | Coverage |",
        "|---:|---|---|---|---|:---:|---|",
    ]
    for row in rows:
        prefix = "git:" if row["fingerprint_type"] == "git-commit" else "tree-sha256:"
        lines.append(
            f"| {row['index']} | `{row['name']}` | `{row['source_path']}` | "
            f"`{prefix}{row['checkout_fingerprint']}` | `{row['codeql_path']}` | "
            f"{'yes' if row['codeql_built'] else 'no'} | `{row['coverage']}` |"
        )
    (run_root / "final_200_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {
        "generated_at": now(),
        "total": len(rows),
        "built": sum(row["codeql_built"] for row in rows),
        "retained_existing": len(retained),
        "new": len(selected_new),
        "removed": REMOVED_SLUG,
        "replacement": replacement,
    }
    (run_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (run_root / "summary.md").write_text(
        "# Canonical Java Web 200 Corpus\n\n"
        f"- Projects: **{summary['total']}**\n"
        f"- Valid CodeQL databases: **{summary['built']}**\n"
        f"- Retained existing: **{summary['retained_existing']}**\n"
        f"- New/source-only: **{summary['new']}**\n"
        f"- Replacement: `{REMOVED_SLUG}` → `{replacement}`\n",
        encoding="utf-8",
    )


def write_tracked_manifest(path: Path, run_root: Path, rows: list[dict[str, Any]], replacement: str) -> None:
    payload = {
        "schema_version": 1,
        "status": "canonical",
        "generated_at": now(),
        "corpus": "java-web-200",
        "total": len(rows),
        "valid_codeql_databases": sum(row["codeql_built"] for row in rows),
        "canonical_run": str(run_root.relative_to(REPO_ROOT)),
        "supersedes": "results/application_dbs/java_web_200_20260718",
        "removed": {"slug": REMOVED_SLUG, "reason": "packaged deployment repository with no Java source files"},
        "replacement": replacement,
        "projects": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replacement", required=True, help="Validated owner/repository replacement slug")
    parser.add_argument("--old-run", type=Path, default=DEFAULT_OLD_RUN)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT)
    parser.add_argument("--tracked-manifest", type=Path, default=DEFAULT_TRACKED_MANIFEST)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    replacement = normalize_slug(args.replacement)
    status_path = args.run_root / "status.jsonl"
    try:
        old_projects = load_old_projects(args.old_run)
        projects = compose_projects(old_projects, replacement)
        source, commit = ensure_source(replacement, args.source_root, args.run_root)
        database = ensure_database(replacement, source, args.db_root, args.run_root)
        append_jsonl(status_path, {"at": now(), "slug": replacement, "status": "built", "commit": commit, "database": str(database)})
        rows = build_inventory(projects, args.source_root, args.db_root)
        failures = [row["name"] for row in rows if not row["codeql_built"] or not row["checkout_fingerprint"]]
        if failures:
            raise RuntimeError(f"canonical inventory validation failed: {', '.join(failures)}")
        write_inventory(args.run_root, projects, rows, replacement)
        write_tracked_manifest(args.tracked_manifest, args.run_root, rows, replacement)
        append_jsonl(status_path, {"at": now(), "status": "published", "total": len(rows), "built": len(rows)})
        return 0
    except Exception as error:
        append_jsonl(status_path, {"at": now(), "slug": replacement, "status": "failed", "reason": str(error)})
        print(f"error: {error}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
