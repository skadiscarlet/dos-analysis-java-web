#!/usr/bin/env python3
"""Build Java CodeQL databases from an explicit, validated manifest.

The builder is resumable but never clones unless --clone-missing is supplied.
``--dry-run`` is read-only: it prints actions without creating logs, results, or
CodeQL database directories.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "frameworks/applications"
DEFAULT_DB_ROOT = REPO_ROOT / "databases/applications"
DEFAULT_RESULT_ROOT = REPO_ROOT / "results/application_dbs/top50_20260704"
DEFAULT_OVERRIDE_FILE = REPO_ROOT / "config/top50_codeql_build_overrides.json"
BOUNDED_JAVAC_HELPER = REPO_ROOT / "scripts/codeql_bounded_javac.sh"
SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_SLUG_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:[/?#)`]|$)")
INLINE_SLUG_RE = re.compile(r"`([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)`")

MAVEN_FLAGS = [
    "-DskipTests",
    "-DskipITs",
    "-DskipIT",
    "-DskipIntegrationTests",
    "-Dmaven.test.skip=true",
    "-Dlicense.skip=true",
    "-Drat.skip=true",
    "-DskipRat=true",
    "-Dcheckstyle.skip=true",
    "-Dspotbugs.skip=true",
    "-Dpmd.skip=true",
    "-Dcpd.skip=true",
    "-Dspotless.check.skip=true",
    "-Dspotless.apply.skip=true",
    "-Denforcer.skip=true",
    "-Dgpg.skip=true",
    "-Dmaven.javadoc.skip=true",
    "-Dskip.npm=true",
    "-DskipNode=true",
    "-Dfrontend.skip=true",
    "-DskipFrontend=true",
    "-Ddocker.skip=true",
    "-DskipDocker=true",
    "-DskipDockerBuild=true",
]
GRADLE_ARGS = ["--no-daemon", "-Dorg.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8", "assemble", "-x", "test"]
PRUNED_SOURCE_DIRS = {".git", ".gradle", ".mvn", "build", "node_modules", "out", "target"}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def safe_name(slug: str) -> str:
    return slug.replace("/", "__")


def display_path(path: Path) -> str:
    """Display paths relative to this checkout when possible, otherwise absolute."""
    resolved = path.resolve(strict=False)
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def validate_slug(slug: object, location: str) -> str:
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError(f"{location}: expected repository slug in owner/repository format")
    return slug


def manifest_slug(line: str, path: Path, line_no: int) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("<!--"):
        return None
    if stripped.startswith("|"):
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(not cell or set(cell) <= {"-", ":"} for cell in cells):
            return None
        if any(cell.lower() == "repository" for cell in cells):
            return None
        matches = GITHUB_SLUG_RE.findall(stripped)
        if not matches:
            matches = INLINE_SLUG_RE.findall(stripped)
    else:
        if path.suffix.lower() in {".md", ".markdown"}:
            return None
        matches = [stripped] if SLUG_RE.fullmatch(stripped) else []
    location = f"{path.name}:{line_no}"
    if len(matches) != 1:
        raise ValueError(f"{location}: expected exactly one repository slug in owner/repository format")
    return validate_slug(matches[0], location)


def load_slugs(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"manifest not found: {display_path(path)}")
    slugs: list[str] = []
    seen: dict[str, int] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        slug = manifest_slug(line, path, line_no)
        if slug is None:
            continue
        if slug in seen:
            raise ValueError(
                f"{path.name}:{line_no}: duplicate repository slug {slug}; first declared at {path.name}:{seen[slug]}"
            )
        seen[slug] = line_no
        slugs.append(slug)
    if not slugs:
        raise ValueError(f"{display_path(path)}: manifest contains no repository slugs")
    return slugs


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{display_path(path)}:{exc.lineno}: invalid {label} JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{display_path(path)}: {label} must be a JSON object")
    return data


def validate_override(slug: str, value: object, location: str) -> dict[str, Any]:
    validate_slug(slug, location)
    if not isinstance(value, dict):
        raise ValueError(f"{location}: override for {slug} must be a JSON object")
    command = value.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError(f"{location}: override for {slug} requires a non-empty command")
    if not isinstance(value.get("allow_compilation_failure", False), bool):
        raise ValueError(f"{location}: allow_compilation_failure must be boolean")
    if "build_risks" in value and (
        not isinstance(value["build_risks"], list) or not all(isinstance(note, str) and note for note in value["build_risks"])
    ):
        raise ValueError(f"{location}: build_risks must be a list of non-empty strings")
    homes = value.get("java_homes")
    if homes is not None and (not isinstance(homes, list) or not all(isinstance(home, str) and home for home in homes)):
        raise ValueError(f"{location}: java_homes must be a list of paths")
    return dict(value)


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    origins: dict[str, Path] = {}

    def add(slug: str, value: object, source: Path) -> None:
        location = display_path(source)
        if slug in overrides:
            raise ValueError(
                f"duplicate override for {slug}: {display_path(origins[slug])} and {location}"
            )
        overrides[slug] = validate_override(slug, value, location)
        origins[slug] = source

    if path.exists():
        for slug, value in read_json_object(path, "override file").items():
            add(str(slug), value, path)
    override_dir = path.parent / f"{path.stem}.d"
    if override_dir.exists():
        if not override_dir.is_dir():
            raise ValueError(f"override fragment path is not a directory: {display_path(override_dir)}")
        for item in sorted(override_dir.glob("*.json")):
            data = read_json_object(item, "override fragment")
            if set(data) == {"slug", "command"} or "slug" in data:
                slug = validate_slug(data.get("slug"), display_path(item))
                add(slug, {key: value for key, value in data.items() if key != "slug"}, item)
            else:
                for slug, value in data.items():
                    add(str(slug), value, item)
    return overrides


def select_range(slugs: list[str], range_text: str | None) -> list[str]:
    if not range_text:
        return slugs
    if ":" not in range_text:
        raise ValueError("--range must be START:END using 1-based inclusive indexes")
    start_text, end_text = range_text.split(":", 1)
    try:
        start, end = int(start_text), int(end_text)
    except ValueError as exc:
        raise ValueError("--range must be START:END using integers") from exc
    if start < 1 or end < start:
        raise ValueError("--range must satisfy 1 <= START <= END")
    return slugs[start - 1 : end]


def run_command(args: list[str], log_path: Path, *, cwd: Path, env: dict[str, str], timeout_seconds: int) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("ab") as log:
        log.write(f"\n===== {utc_now()} cwd={cwd} =====\n".encode())
        log.write((" ".join(args) + "\n").encode())
        log.flush()
        try:
            proc = subprocess.run(args, cwd=str(cwd), env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout_seconds, check=False)
            return proc.returncode, time.monotonic() - started
        except subprocess.TimeoutExpired:
            log.write(f"\nTIMEOUT after {timeout_seconds} seconds\n".encode())
            return 124, time.monotonic() - started


def append_status(status_path: Path, record: dict[str, Any]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def existing_commit(source_dir: Path) -> str | None:
    if not (source_dir / ".git").exists():
        return None
    try:
        return subprocess.check_output(["git", "-C", str(source_dir), "rev-parse", "HEAD"], text=True, timeout=60).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def git_clone(slug: str, source_dir: Path, log_path: Path, timeout_seconds: int) -> tuple[bool, str | None]:
    source_dir.parent.mkdir(parents=True, exist_ok=True)
    code, _ = run_command(["git", "clone", "--depth", "1", f"https://github.com/{slug}.git", str(source_dir)], log_path, cwd=REPO_ROOT, env=os.environ.copy(), timeout_seconds=timeout_seconds)
    return code == 0, existing_commit(source_dir)


def shell_join(parts: list[str]) -> str:
    return " ".join(sh_quote(part) for part in parts)


def sh_quote(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z0-9_./:=+@%,-]+", value) else "'" + value.replace("'", "'\"'\"'") + "'"


def find_build_command(source_dir: Path, override: dict[str, Any]) -> tuple[str | None, str]:
    command = override.get("command")
    if isinstance(command, str) and command.strip():
        return command.strip(), "override"
    if (source_dir / "mvnw").exists():
        return shell_join(["sh", "./mvnw", "-B", "-ntp", *MAVEN_FLAGS, "compile"]), "maven-wrapper"
    if (source_dir / "pom.xml").exists():
        return shell_join(["mvn", "-B", "-ntp", *MAVEN_FLAGS, "compile"]), "maven"
    if (source_dir / "gradlew").exists():
        return shell_join(["sh", "./gradlew", *GRADLE_ARGS]), "gradle-wrapper"
    if (source_dir / "build.gradle").exists() or (source_dir / "build.gradle.kts").exists():
        return (shell_join(["gradle", *GRADLE_ARGS]), "gradle") if shutil.which("gradle") else (None, "gradle-no-system-gradle")
    if (source_dir / "build.xml").exists() and shutil.which("ant"):
        return shell_join(["ant", "-Dskip.tests=true", "-Dtest.skip=true", "jar"]), "ant"
    return None, "autobuild"


def default_java_homes() -> list[Path]:
    return [path for path in (Path("/usr/lib/jvm/java-17-openjdk"), Path("/usr/lib/jvm/java-21-openjdk"), Path("/usr/lib/jvm/java-22-openjdk"), Path("/usr/lib/jvm/default")) if path.exists()]


def override_java_homes(override: dict[str, Any]) -> list[Path] | None:
    homes = [Path(home) for home in override.get("java_homes", []) if Path(home).exists()]
    return homes or None


def count_java_files(source_dir: Path) -> int:
    return sum(1 for path in source_dir.rglob("*.java") if not any(parent.name in PRUNED_SOURCE_DIRS for parent in path.parents))


def codeql_database_status(db_dir: Path) -> dict[str, str]:
    if not db_dir.exists():
        return {"database_structure": "missing", "coverage_status": "not_available"}
    if not db_dir.is_dir() or not (db_dir / "codeql-database.yml").is_file() or not (db_dir / "db-java").is_dir():
        return {"database_structure": "invalid", "coverage_status": "not_available"}
    java_db = db_dir / "db-java"
    if not ((java_db / "default").exists() or (java_db / "semmlecode.dbscheme").is_file() or any(java_db.iterdir())):
        return {"database_structure": "invalid", "coverage_status": "not_available"}
    return {"database_structure": "valid", "coverage_status": "unverified"}


def codeql_database_info(db_dir: Path) -> bool:
    return codeql_database_status(db_dir)["database_structure"] == "valid"


def base_record(slug: str, source_dir: Path, db_dir: Path, java_file_count: int | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "slug": slug,
        "safe_name": safe_name(slug),
        "source_dir": display_path(source_dir),
        "db_dir": display_path(db_dir),
        **codeql_database_status(db_dir),
    }
    if java_file_count is not None:
        record["java_file_count"] = java_file_count
    return record


def create_codeql_db(slug: str, source_dir: Path, db_dir: Path, tmp_root: Path, log_dir: Path, override: dict[str, Any], status_path: Path, timeout_seconds: int, java_file_count: int, dry_run: bool) -> bool:
    name = safe_name(slug)
    build_cmd, build_kind = find_build_command(source_dir, override)
    if build_cmd is None and build_kind != "autobuild":
        if dry_run:
            print(f"{slug}: would fail selecting build command ({build_kind})")
            return False
        record = base_record(slug, source_dir, db_dir, java_file_count)
        record.update({"status": "failed", "stage": "select-build-command", "build_kind": build_kind, "ended_at": utc_now()})
        append_status(status_path, record)
        return False
    if dry_run:
        print(f"{slug}: {build_kind}: {build_cmd or 'CodeQL autobuild'}")
        return True

    attempts = (override_java_homes(override) or default_java_homes()) if build_kind != "autobuild" else [None]
    if not attempts:
        attempts = [None]
    tmp_root.mkdir(parents=True, exist_ok=True)
    for attempt_index, java_home in enumerate(attempts, start=1):
        tmp_db = tmp_root / f"{name}-db-attempt{attempt_index}-{os.getpid()}"
        if tmp_db.exists():
            shutil.rmtree(tmp_db)
        log_path = log_dir / f"{name}.attempt{attempt_index}.codeql.log"
        env = os.environ.copy()
        env.setdefault("MAVEN_OPTS", "-Xmx2g")
        env.setdefault("GRADLE_OPTS", "-Dorg.gradle.jvmargs=-Xmx2g")
        env["CODEQL_BOUNDED_JAVAC_HELPER"] = str(BOUNDED_JAVAC_HELPER)
        env["CODEQL_BOUNDED_JAVAC_WORK_DIR"] = str(tmp_root / f"{name}-javac-attempt{attempt_index}-{os.getpid()}")
        env["CODEQL_BOUNDED_JAVAC_ALLOW_COMPILATION_FAILURE"] = "1" if override.get("allow_compilation_failure", False) else "0"
        if java_home is not None:
            env["JAVA_HOME"] = str(java_home)
            env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
        codeql_args = ["codeql", "database", "create", str(tmp_db), "--language=java", f"--source-root={source_dir}"]
        codeql_args.extend(["--build-mode=autobuild"] if build_kind == "autobuild" else ["--command", build_cmd or ""])
        started_at = utc_now()
        code, duration = run_command(codeql_args, log_path, cwd=source_dir, env=env, timeout_seconds=timeout_seconds)
        record = base_record(slug, source_dir, db_dir, java_file_count)
        record.update({
            "attempt": attempt_index, "build_kind": build_kind, "build_command": build_cmd,
            "allow_compilation_failure": bool(override.get("allow_compilation_failure", False)),
            "build_risks": override.get("build_risks", []), "duration_seconds": round(duration, 2),
            "exit_code": code, "java_home": str(java_home) if java_home else None,
            "log": display_path(log_path), "started_at": started_at, "ended_at": utc_now(),
        })
        if code == 0 and codeql_database_info(tmp_db):
            db_dir.parent.mkdir(parents=True, exist_ok=True)
            if db_dir.exists():
                record.update({"status": "failed", "stage": "promote-db", "reason": "target-db-exists"})
                append_status(status_path, record)
                return False
            tmp_db.rename(db_dir)
            record.update({"status": "success", "stage": "codeql-create", "database_structure": "valid", "coverage_status": "capture_completed"})
            append_status(status_path, record)
            return True
        record.update({"status": "failed", "stage": "codeql-create", "coverage_status": "not_available"})
        append_status(status_path, record)
        if tmp_db.exists():
            shutil.rmtree(tmp_db)
    return False


def latest_status(status_path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not status_path.exists():
        return latest
    for line_no, line in enumerate(status_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{display_path(status_path)}:{line_no}: invalid status JSON: {exc.msg}") from exc
        if isinstance(record, dict) and isinstance(record.get("slug"), str):
            latest[record["slug"]] = record
    return latest


def write_summary(slugs: list[str], status_path: Path, summary_path: Path) -> None:
    latest = latest_status(status_path)
    lines = ["# Top50 CodeQL DB Build Summary", "", f"Updated: {utc_now()}", "", "| # | Repository | Status | Structure | Coverage | Java files | DB | Log |", "|---:|---|---|---|---|---:|---|---|"]
    counts: dict[str, int] = {}
    for index, slug in enumerate(slugs, start=1):
        record = latest.get(slug, {})
        status = str(record.get("status", "not_started"))
        counts[status] = counts.get(status, 0) + 1
        lines.append(f"| {index} | `{slug}` | `{status}` | `{record.get('database_structure', 'missing')}` | `{record.get('coverage_status', 'not_available')}` | {record.get('java_file_count', '')} | `{record.get('db_dir', '')}` | `{record.get('log', '')}` |")
    lines.extend(["", "## Counts", "", *[f"- `{key}`: {value}" for key, value in sorted(counts.items())]])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def process_slug(slug: str, args: argparse.Namespace, overrides: dict[str, dict[str, Any]]) -> bool:
    name = safe_name(slug)
    source_dir = args.source_root / name
    db_dir = args.db_root / f"{name}-db"
    status_path = args.result_root / "status.jsonl"
    java_file_count = count_java_files(source_dir) if source_dir.is_dir() else None
    record = base_record(slug, source_dir, db_dir, java_file_count)
    if codeql_database_info(db_dir):
        if args.dry_run:
            print(f"{slug}: would skip existing valid database at {display_path(db_dir)}")
        else:
            record.update({"status": "skipped_existing_db", "stage": "precheck", "ended_at": utc_now()})
            append_status(status_path, record)
        return True
    if not source_dir.exists():
        if args.dry_run:
            action = f"would clone https://github.com/{slug}.git" if args.clone_missing else "would fail (source missing; use --clone-missing)"
            print(f"{slug}: {action} -> {display_path(source_dir)}")
            return args.clone_missing
        if not args.clone_missing:
            record.update({"status": "failed", "stage": "precheck", "reason": "source-missing-use-clone-missing", "ended_at": utc_now()})
            append_status(status_path, record)
            return False
        clone_log = args.result_root / "logs" / f"{name}.clone.log"
        started_at = utc_now()
        ok, commit = git_clone(slug, source_dir, clone_log, args.clone_timeout_minutes * 60)
        clone_record = dict(record)
        clone_record.update({"status": "success" if ok else "failed", "stage": "clone", "commit": commit, "log": display_path(clone_log), "started_at": started_at, "ended_at": utc_now()})
        append_status(status_path, clone_record)
        if not ok:
            return False
    if not source_dir.is_dir():
        record.update({"status": "failed", "stage": "precheck", "reason": "source-path-not-directory", "ended_at": utc_now()})
        append_status(status_path, record)
        return False
    java_file_count = count_java_files(source_dir)
    commit = existing_commit(source_dir)
    if not args.dry_run and commit:
        source_record = base_record(slug, source_dir, db_dir, java_file_count)
        source_record.update({"status": "source_ready", "stage": "source", "commit": commit, "ended_at": utc_now()})
        append_status(status_path, source_record)
    return create_codeql_db(slug, source_dir, db_dir, args.db_root / ".top50-tmp", args.result_root / "logs", overrides.get(slug, {}), status_path, args.build_timeout_minutes * 60, java_file_count, args.dry_run)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Explicit manifest with unique owner/repository slugs.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT)
    parser.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    parser.add_argument("--override-file", type=Path, default=DEFAULT_OVERRIDE_FILE)
    parser.add_argument("--only", action="append", default=[], help="Repository slug to process; may be repeated.")
    parser.add_argument("--range", help="1-based inclusive range, for example 1:10.")
    parser.add_argument("--clone-missing", action="store_true", help="Explicitly permit network cloning for missing sources.")
    parser.add_argument("--clone-timeout-minutes", type=int, default=30)
    parser.add_argument("--build-timeout-minutes", type=int, default=120)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing files or running CodeQL.")
    args = parser.parse_args(argv)
    if args.summary_only and args.dry_run:
        parser.error("--summary-only writes a summary and cannot be combined with --dry-run")
    if args.clone_timeout_minutes <= 0 or args.build_timeout_minutes <= 0:
        parser.error("timeout minutes must be positive")
    for name in ("manifest", "source_root", "db_root", "result_root", "override_file"):
        setattr(args, name, getattr(args, name).resolve())
    return args


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        all_slugs = load_slugs(args.manifest)
        if args.only:
            requested = [validate_slug(slug, "--only") for slug in args.only]
            unknown = sorted(set(requested).difference(all_slugs))
            if unknown:
                raise ValueError(f"--only contains slug(s) missing from manifest: {', '.join(unknown)}")
            slugs = [slug for slug in all_slugs if slug in set(requested)]
        else:
            slugs = all_slugs
        slugs = select_range(slugs, args.range)
        if not slugs:
            raise ValueError("No repositories selected.")
        if args.summary_only:
            write_summary(all_slugs, args.result_root / "status.jsonl", args.result_root / "summary.md")
            print(display_path(args.result_root / "summary.md"))
            return 0
        overrides = load_overrides(args.override_file)
        overall_ok = True
        for slug in slugs:
            print(f"===== {slug} =====", flush=True)
            overall_ok = process_slug(slug, args, overrides) and overall_ok
            if not args.dry_run:
                write_summary(all_slugs, args.result_root / "status.jsonl", args.result_root / "summary.md")
        return 0 if overall_ok else 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
