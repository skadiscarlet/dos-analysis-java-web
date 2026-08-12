from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from dosweb.artifacts.identifiers import file_sha256, sha256_canonical_json
from dosweb.batch.corpus import _fingerprint
from dosweb.codeql.database import DatabaseInfo, validate_database

_NATIVE_TOOLS = frozenset({"mvn", "mvnw", "gradle", "gradlew", "ant"})
_FORBIDDEN_TOKENS = frozenset(
    {
        "autobuild",
        "build-mode=none",
        "codeql_bounded_javac",
        "allow_compilation_failure",
        "bootrun",
        "run",
        "test",
        "integrationtest",
        "deploy",
        "publish",
        "docker",
    }
)
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_NATIVE_MAVEN_SETTINGS = Path(__file__).resolve().parents[2] / "config/native_maven_settings.xml"


@dataclass(frozen=True)
class NativeBuildSpec:
    repository: str
    kind: str
    command: str
    java_homes: tuple[Path, ...]
    working_directory: str = "."
    setup_commands: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "kind": self.kind,
            "command": self.command,
            "java_homes": [str(path) for path in self.java_homes],
            "working_directory": self.working_directory,
            "setup_commands": list(self.setup_commands),
        }


@dataclass(frozen=True)
class NativeBuildResult:
    status: str
    record: Mapping[str, object]


def _native_invalid(message: str) -> ValueError:
    return ValueError(f"invalid native CodeQL build: {message}")


def validate_run_id(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_RUN_ID.fullmatch(value):
        raise ValueError("run id must contain only letters, digits, dots, underscores, or dashes")
    return value


def _command_words(command: str) -> list[str]:
    if not isinstance(command, str) or not command.strip():
        raise _native_invalid("command is required")
    try:
        words = shlex.split(command)
    except ValueError as exc:
        raise _native_invalid("command cannot be parsed") from exc
    if not words:
        raise _native_invalid("command is required")
    return words


def _effective_maven_command(command: str, repository: Path) -> str:
    words = _command_words(command)
    insertion = 2 if Path(words[0]).name == "sh" else 1
    words[insertion:insertion] = [
        "--settings",
        str(_NATIVE_MAVEN_SETTINGS),
        f"-Dmaven.repo.local={repository}",
    ]
    return shlex.join(words)


def validate_native_command(command: str, kind: str | None = None) -> tuple[str, str]:
    words = _command_words(command)
    executable = Path(words[0]).name
    if executable == "sh" and len(words) > 1:
        executable = Path(words[1]).name
    tool = executable.lstrip("./")
    normalized = " ".join(words).casefold()
    if tool not in _NATIVE_TOOLS:
        raise _native_invalid("only Maven, Gradle, or Ant commands are allowed")
    if any(token in normalized for token in ("|", ">", "<", "&&", ";", "`", "$(")):
        raise _native_invalid("shell composition is not allowed")
    excluded = {
        words[index + 1].casefold().lstrip("-:")
        for index, word in enumerate(words[:-1])
        if word in {"-x", "--exclude-task"}
    }
    compact = {
        word.casefold().lstrip("-:")
        for index, word in enumerate(words)
        if not (index > 0 and words[index - 1] in {"-x", "--exclude-task"})
    } - excluded
    if any(token in normalized for token in ("build-mode=none", "codeql_bounded_javac", "allow_compilation_failure")):
        raise _native_invalid("source-only or bounded extraction is not allowed")
    if compact & _FORBIDDEN_TOKENS:
        raise _native_invalid("tests, application launch, deployment, and Docker tasks are not allowed")
    inferred = "maven" if tool in {"mvn", "mvnw"} else "gradle" if tool in {"gradle", "gradlew"} else "ant"
    if kind is not None and kind != inferred:
        raise _native_invalid("declared build kind does not match command")
    return inferred, command.strip()


def default_java_homes() -> tuple[Path, ...]:
    roots = (
        Path("/usr/lib/jvm/java-25-openjdk"),
        Path("/usr/lib/jvm/java-22-openjdk"),
        Path("/usr/lib/jvm/java-21-openjdk"),
        Path("/usr/lib/jvm/java-17-openjdk"),
        Path("/usr/lib/jvm/java-11-openjdk"),
        Path("/usr/lib/jvm/java-8-openjdk"),
        Path("/usr/lib/jvm/default"),
    )
    return tuple(path for path in roots if (path / "bin/java").is_file())


def discover_native_build(source: Path, repository: str, override: Mapping[str, object] | None = None) -> NativeBuildSpec:
    value = dict(override or {})
    working_directory = value.get("working_directory", ".")
    if not isinstance(working_directory, str):
        raise _native_invalid(f"{repository}: working_directory must be a string")
    relative = Path(working_directory)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts if working_directory != "."):
        raise _native_invalid(f"{repository}: working_directory is unsafe")
    build_root = source if working_directory == "." else source / relative
    if not build_root.is_dir() or build_root.is_symlink():
        raise _native_invalid(f"{repository}: working_directory is missing or unsafe")
    command = value.get("command")
    kind = value.get("kind")
    if command is None:
        if (build_root / "mvnw").is_file():
            command = "sh ./mvnw -B -ntp -DskipTests -DskipITs -Dmaven.test.skip=true -Dlicense.skip=true -Drat.skip=true -Dcheckstyle.skip=true -Dspotbugs.skip=true -Dpmd.skip=true -Dspotless.check.skip=true -Denforcer.skip=true -Dgpg.skip=true -Dmaven.javadoc.skip=true -Dskip.npm=true -DskipNode=true -Dfrontend.skip=true -Ddocker.skip=true compile"
        elif (build_root / "pom.xml").is_file():
            command = "mvn -B -ntp -DskipTests -DskipITs -Dmaven.test.skip=true -Dlicense.skip=true -Drat.skip=true -Dcheckstyle.skip=true -Dspotbugs.skip=true -Dpmd.skip=true -Dspotless.check.skip=true -Denforcer.skip=true -Dgpg.skip=true -Dmaven.javadoc.skip=true -Dskip.npm=true -DskipNode=true -Dfrontend.skip=true -Ddocker.skip=true compile"
        elif (build_root / "gradlew").is_file():
            command = "sh ./gradlew --no-daemon --max-workers=2 -Dorg.gradle.jvmargs=-Xmx2g assemble -x test"
        elif (build_root / "build.gradle").is_file() or (build_root / "build.gradle.kts").is_file():
            if not shutil.which("gradle"):
                raise _native_invalid(f"{repository}: Gradle wrapper and system Gradle are unavailable")
            command = "gradle --no-daemon --max-workers=2 -Dorg.gradle.jvmargs=-Xmx2g assemble -x test"
        elif (build_root / "build.xml").is_file() and shutil.which("ant"):
            command = "ant -Dskip.tests=true jar"
        else:
            raise _native_invalid(f"{repository}: no supported native build was found")
    if not isinstance(command, str):
        raise _native_invalid(f"{repository}: command must be a string")
    declared = kind if isinstance(kind, str) else None
    inferred, checked = validate_native_command(command, declared)
    configured = value.get("java_homes")
    if configured is None:
        homes = default_java_homes()
    elif isinstance(configured, list) and all(isinstance(item, str) for item in configured):
        homes = tuple(Path(item) for item in configured if (Path(item) / "bin/java").is_file())
    else:
        raise _native_invalid(f"{repository}: java_homes must be a list of paths")
    if not homes:
        raise _native_invalid(f"{repository}: no configured JDK is available")
    setup_value = value.get("setup_commands", [])
    if not isinstance(setup_value, list) or not all(isinstance(item, str) for item in setup_value):
        raise _native_invalid(f"{repository}: setup_commands must be a list of commands")
    setup_commands: list[str] = []
    for setup_command in setup_value:
        setup_kind, setup_checked = validate_native_command(setup_command)
        if setup_kind != inferred:
            raise _native_invalid(f"{repository}: setup command build kind does not match command")
        setup_commands.append(setup_checked)
    return NativeBuildSpec(
        repository,
        inferred,
        checked,
        homes,
        working_directory,
        tuple(setup_commands),
    )


def load_override_file(path: Path | None) -> dict[str, Mapping[str, object]]:
    if path is None or not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        raise ValueError("native build override must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("native build override must be an object")
    result: dict[str, Mapping[str, object]] = {}
    for repository, row in value.items():
        if not isinstance(repository, str) or not isinstance(row, dict):
            raise ValueError("native build override rows are malformed")
        result[repository.casefold()] = row
    return result


def _safe_directory(path: Path, root: Path, *, must_exist: bool = False) -> Path:
    root_resolved = root.resolve(strict=True)
    current = root_resolved
    relative = path.resolve(strict=False).relative_to(root_resolved)
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlinked path is not allowed: {path}")
    if must_exist and not path.is_dir():
        raise ValueError(f"directory is missing: {path}")
    return path


def _run_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    log: Path,
    timeout_seconds: int,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> tuple[int, float]:
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open("ab") as stream:
        stream.write(("COMMAND " + " ".join(shlex.quote(item) for item in argv) + "\n").encode())
        stream.flush()
        try:
            completed = runner(
                list(argv),
                cwd=str(cwd),
                env=dict(env),
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
            return int(completed.returncode), time.monotonic() - started
        except subprocess.TimeoutExpired:
            stream.write(f"TIMEOUT {timeout_seconds}\n".encode())
            return 124, time.monotonic() - started


def _append_jsonl(path: Path, row: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def promote_database(candidate: Path, target: Path, quarantine: Path) -> str:
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("validated candidate database is missing or unsafe")
    target.parent.mkdir(parents=True, exist_ok=True)
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    moved_old = False
    if target.exists() or target.is_symlink():
        if target.is_symlink():
            raise ValueError("symlinked target database is not replaceable")
        if quarantine.exists():
            raise ValueError("quarantine destination already exists")
        target.rename(quarantine)
        moved_old = True
    try:
        candidate.rename(target)
    except Exception:
        if moved_old and quarantine.exists() and not target.exists():
            quarantine.rename(target)
        raise
    return "replaced_invalid" if moved_old else "installed_missing"


def build_native_database(
    *,
    repository: str,
    source: Path,
    target: Path,
    spec: NativeBuildSpec,
    run_id: str,
    database_root: Path,
    result_root: Path,
    timeout_seconds: int,
    codeql_binary: str = "codeql",
    process_runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    validator: Callable[[Path], DatabaseInfo] = validate_database,
) -> NativeBuildResult:
    validate_run_id(run_id)
    _safe_directory(source, source.parents[1], must_exist=True)
    _safe_directory(target.parent, database_root, must_exist=True)
    try:
        existing = validator(target)
    except Exception:
        existing = None
    if existing is not None:
        return NativeBuildResult("skipped_existing_valid", {"repository": repository, "status": "skipped_existing_valid", "database_fingerprint": existing.fingerprint})
    before_type, before_fingerprint = _fingerprint(source)
    name = repository.replace("/", "__")
    temp_parent = database_root / ".java-web-205-tmp" / run_id
    temp_parent.mkdir(parents=True, exist_ok=True)
    last_record: dict[str, object] = {}
    for attempt, java_home in enumerate(spec.java_homes, 1):
        candidate = temp_parent / f"{name}-attempt-{attempt}-{os.getpid()}"
        quarantine = (
            database_root
            / ".java-web-205-quarantine"
            / run_id
            / f"{target.name}.attempt-{attempt}-{os.getpid()}"
        )
        if candidate.exists():
            stale = candidate.with_name(f"{candidate.name}.stale")
            if stale.exists():
                raise ValueError(f"temporary database recovery path already exists: {stale}")
            candidate.rename(stale)
        log = result_root / "logs" / f"{name}.attempt{attempt}.codeql.log"
        env = os.environ.copy()
        for variable in (
            "DEEPSEEK_API_KEY",
            "JAVA_TOOL_OPTIONS",
            "JDK_JAVA_OPTIONS",
            "_JAVA_OPTIONS",
            "MAVEN_ARGS",
            "MAVEN_OPTS",
            "GRADLE_OPTS",
        ):
            env.pop(variable, None)
        env["JAVA_HOME"] = str(java_home)
        env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
        env["MAVEN_OPTS"] = "-Xmx2g"
        env["GRADLE_OPTS"] = "-Dorg.gradle.jvmargs=-Xmx2g"
        effective_command = spec.command
        effective_setup_commands = list(spec.setup_commands)
        if spec.kind == "maven":
            maven_repository = result_root / "maven-repository"
            maven_repository.mkdir(parents=True, exist_ok=True)
            effective_command = _effective_maven_command(spec.command, maven_repository)
            effective_setup_commands = [
                _effective_maven_command(command, maven_repository)
                for command in spec.setup_commands
            ]
        build_cwd = source if spec.working_directory == "." else source / spec.working_directory
        setup_records: list[dict[str, object]] = []
        setup_failed = False
        for setup_index, setup_command in enumerate(effective_setup_commands, 1):
            setup_log = result_root / "logs" / f"{name}.attempt{attempt}.setup{setup_index}.log"
            setup_code, setup_duration = _run_process(
                _command_words(setup_command),
                cwd=build_cwd,
                env=env,
                log=setup_log,
                timeout_seconds=timeout_seconds,
                runner=process_runner,
            )
            setup_records.append(
                {
                    "command": spec.setup_commands[setup_index - 1],
                    "exit_code": setup_code,
                    "duration_seconds": round(setup_duration, 3),
                    "log": str(setup_log),
                    "log_sha256": file_sha256(setup_log),
                }
            )
            if setup_code != 0:
                setup_failed = True
                break
        setup_duration_total = sum(float(row["duration_seconds"]) for row in setup_records)
        if setup_failed:
            code = int(setup_records[-1]["exit_code"])
            duration = setup_duration_total
            log.write_text("CODEQL_CAPTURE_SKIPPED_SETUP_FAILED\n", encoding="utf-8")
        else:
            argv = [
                codeql_binary,
                "database",
                "create",
                str(candidate),
                "--language=java",
                f"--source-root={source}",
                f"--working-dir={build_cwd}",
                "--command",
                effective_command,
            ]
            code, duration = _run_process(
                argv,
                cwd=build_cwd,
                env=env,
                log=log,
                timeout_seconds=timeout_seconds,
                runner=process_runner,
            )
        after_type, after_fingerprint = _fingerprint(source)
        last_record = {
            "schema_version": 1,
            "repository": repository,
            "status": "failed",
            "attempt": attempt,
            "build_kind": spec.kind,
            "build_command": spec.command,
            "working_directory": spec.working_directory,
            "java_home": str(java_home),
            "codeql_exit_code": None if setup_failed else code,
            "setup_commands": list(spec.setup_commands),
            "setup_results": setup_records,
            "duration_seconds": round(duration + (0 if setup_failed else setup_duration_total), 3),
            "source_fingerprint_type": before_type,
            "source_fingerprint_before": before_fingerprint,
            "source_fingerprint_after": after_fingerprint,
            "log": str(log),
            "log_sha256": file_sha256(log),
        }
        if (before_type, before_fingerprint) != (after_type, after_fingerprint):
            last_record["reason"] = "SOURCE_FINGERPRINT_DRIFT"
            if candidate.exists():
                drift_candidate = candidate.with_name(f"{candidate.name}.source-drift")
                if drift_candidate.exists():
                    raise ValueError(f"source-drift recovery path already exists: {drift_candidate}")
                candidate.rename(drift_candidate)
                last_record["recovery_candidate"] = str(drift_candidate)
            _append_jsonl(result_root / "status.jsonl", last_record)
            return NativeBuildResult("failed", last_record)
        if code != 0:
            last_record["reason"] = "NATIVE_SETUP_FAILED" if setup_failed else "NATIVE_BUILD_FAILED"
            _append_jsonl(result_root / "status.jsonl", last_record)
            if candidate.exists():
                shutil.rmtree(candidate)
            continue
        try:
            info = validator(candidate)
            if info.source_root.resolve(strict=False) != source.resolve(strict=True):
                raise ValueError("source root mismatch")
            if validator(candidate).fingerprint != info.fingerprint:
                raise ValueError("database fingerprint is unstable")
        except Exception as exc:
            last_record["reason"] = "DATABASE_VALIDATION_FAILED"
            last_record["diagnostic"] = type(exc).__name__
            _append_jsonl(result_root / "status.jsonl", last_record)
            if candidate.exists():
                shutil.rmtree(candidate)
            continue
        try:
            promotion = promote_database(candidate, target, quarantine)
        except Exception as exc:
            last_record["reason"] = "DATABASE_PROMOTION_FAILED"
            last_record["diagnostic"] = type(exc).__name__
            _append_jsonl(result_root / "status.jsonl", last_record)
            if candidate.exists():
                failed_candidate = candidate.with_name(f"{candidate.name}.promotion-failed")
                if not failed_candidate.exists():
                    candidate.rename(failed_candidate)
            return NativeBuildResult("failed", last_record)
        record = {
            **last_record,
            "status": "success",
            "reason": None,
            "database_path": str(target),
            "database_fingerprint": info.fingerprint,
            "promotion": promotion,
            "quarantine_path": str(quarantine) if promotion == "replaced_invalid" else None,
        }
        record["attestation_digest"] = sha256_canonical_json(record)
        _append_jsonl(result_root / "status.jsonl", record)
        _append_jsonl(result_root / "native_build_attestations.jsonl", record)
        return NativeBuildResult("success", record)
    return NativeBuildResult("failed", last_record)
