#!/usr/bin/env python3
"""Clone selected Java Web applications and build CodeQL build-mode databases."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "intel" / "applications" / "java_web_application_targets.json"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "application_dbs"
CODEQL_BIN = "/usr/bin/codeql"
DEFAULT_GITHUB_ACCELERATOR_PREFIXES = [
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://hub.gitmirror.com/",
]
DEFAULT_GRADLE_DISTRIBUTION_MIRROR = "https://mirrors.cloud.tencent.com/gradle/"


@dataclass(frozen=True)
class ApplicationTarget:
    id: str
    full_name: str
    clone_url: str
    source_dir: str
    database_dir: str
    build_systems: list[str]
    build_command: str | None = None

    @classmethod
    def from_record(cls, record: dict) -> "ApplicationTarget":
        return cls(
            id=record["id"],
            full_name=record["full_name"],
            clone_url=record["clone_url"],
            source_dir=record["source_dir"],
            database_dir=record["database_dir"],
            build_systems=list(record.get("build_systems") or ["auto"]),
            build_command=record.get("build_command"),
        )


@dataclass(frozen=True)
class BuildPlan:
    command: list[str]
    cwd: Path
    build_root: Path


@dataclass(frozen=True)
class MirrorConfig:
    maven_settings: Path
    gradle_init: Path


def existing_java_homes(requested: Iterable[str | None]) -> list[str]:
    homes: list[str] = []
    for home in requested:
        if not home:
            continue
        if home not in homes and (Path(home) / "bin" / "java").exists():
            homes.append(home)
    return homes


def normalize_requested_java_homes(requested: Iterable[str | None]) -> list[str]:
    homes: list[str] = []
    for home in requested:
        if home and home not in homes:
            homes.append(home)
    return homes


def default_java_homes() -> list[str]:
    env_java_home = os.environ.get("JAVA_HOME")
    return existing_java_homes(
        [
            env_java_home,
            "/usr/lib/jvm/java-22-openjdk",
            "/usr/lib/jvm/java-21-openjdk",
            "/usr/lib/jvm/java-17-openjdk",
        ]
    ) or [env_java_home or "/usr/lib/jvm/java-17-openjdk"]


def ensure_mirror_config(project_root: Path) -> MirrorConfig:
    maven_dir = project_root / ".build-cache" / "m2"
    gradle_dir = project_root / ".build-cache" / "gradle"
    maven_dir.mkdir(parents=True, exist_ok=True)
    gradle_dir.mkdir(parents=True, exist_ok=True)

    maven_settings = maven_dir / "settings-china.xml"
    maven_settings.write_text(
        """<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
  <mirrors>
    <mirror>
      <id>aliyun-public</id>
      <mirrorOf>central</mirrorOf>
      <url>https://maven.aliyun.com/repository/public</url>
    </mirror>
  </mirrors>
  <profiles>
    <profile>
      <id>china-first</id>
      <repositories>
        <repository>
          <id>aliyun-public</id>
          <url>https://maven.aliyun.com/repository/public</url>
          <releases><enabled>true</enabled></releases>
          <snapshots><enabled>true</enabled></snapshots>
        </repository>
        <repository>
          <id>aliyun-spring</id>
          <url>https://maven.aliyun.com/repository/spring</url>
          <releases><enabled>true</enabled></releases>
          <snapshots><enabled>true</enabled></snapshots>
        </repository>
        <repository>
          <id>aliyun-gradle-plugin</id>
          <url>https://maven.aliyun.com/repository/gradle-plugin</url>
          <releases><enabled>true</enabled></releases>
          <snapshots><enabled>true</enabled></snapshots>
        </repository>
        <repository>
          <id>tencent-public</id>
          <url>https://mirrors.tencent.com/nexus/repository/maven-public/</url>
          <releases><enabled>true</enabled></releases>
          <snapshots><enabled>true</enabled></snapshots>
        </repository>
        <repository>
          <id>maven-central</id>
          <url>https://repo.maven.apache.org/maven2</url>
          <releases><enabled>true</enabled></releases>
          <snapshots><enabled>false</enabled></snapshots>
        </repository>
      </repositories>
      <pluginRepositories>
        <pluginRepository>
          <id>aliyun-gradle-plugin</id>
          <url>https://maven.aliyun.com/repository/gradle-plugin</url>
          <releases><enabled>true</enabled></releases>
          <snapshots><enabled>true</enabled></snapshots>
        </pluginRepository>
        <pluginRepository>
          <id>aliyun-public</id>
          <url>https://maven.aliyun.com/repository/public</url>
          <releases><enabled>true</enabled></releases>
          <snapshots><enabled>true</enabled></snapshots>
        </pluginRepository>
        <pluginRepository>
          <id>maven-central</id>
          <url>https://repo.maven.apache.org/maven2</url>
          <releases><enabled>true</enabled></releases>
          <snapshots><enabled>false</enabled></snapshots>
        </pluginRepository>
      </pluginRepositories>
    </profile>
  </profiles>
  <activeProfiles>
    <activeProfile>china-first</activeProfile>
  </activeProfiles>
</settings>
""",
        encoding="utf-8",
    )

    gradle_init = gradle_dir / "init-china.gradle"
    gradle_init.write_text(
        """settingsEvaluated { settings ->
    settings.pluginManagement {
        repositories {
            maven { url = uri("https://maven.aliyun.com/repository/gradle-plugin") }
            maven { url = uri("https://maven.aliyun.com/repository/public") }
            maven { url = uri("https://mirrors.tencent.com/nexus/repository/maven-public/") }
            gradlePluginPortal()
            mavenCentral()
        }
    }
}

allprojects {
    buildscript {
        repositories {
            maven { url = uri("https://maven.aliyun.com/repository/gradle-plugin") }
            maven { url = uri("https://maven.aliyun.com/repository/public") }
            maven { url = uri("https://mirrors.tencent.com/nexus/repository/maven-public/") }
            gradlePluginPortal()
            mavenCentral()
        }
    }
    repositories {
        maven { url = uri("https://maven.aliyun.com/repository/public") }
        maven { url = uri("https://maven.aliyun.com/repository/spring") }
        maven { url = uri("https://mirrors.tencent.com/nexus/repository/maven-public/") }
        mavenCentral()
    }
}
""",
        encoding="utf-8",
    )
    return MirrorConfig(maven_settings=maven_settings, gradle_init=gradle_init)


def rewrite_gradle_wrapper_distributions(source_dir: Path, mirror_base_url: str = DEFAULT_GRADLE_DISTRIBUTION_MIRROR) -> list[Path]:
    rewritten: list[Path] = []
    mirror_base_url = mirror_base_url.rstrip("/") + "/"
    for wrapper_properties in source_dir.rglob("gradle-wrapper.properties"):
        text = wrapper_properties.read_text(encoding="utf-8", errors="replace")
        lines: list[str] = []
        changed = False
        for line in text.splitlines():
            if line.startswith("distributionUrl="):
                value = line.split("=", 1)[1]
                zip_name = value.rsplit("/", 1)[-1]
                if zip_name.startswith("gradle-") and zip_name.endswith(".zip"):
                    escaped_url = (mirror_base_url + zip_name).replace(":", "\\:")
                    line = f"distributionUrl={escaped_url}"
                    changed = True
            lines.append(line)
        if changed:
            wrapper_properties.write_text("\n".join(lines) + "\n", encoding="utf-8")
            rewritten.append(wrapper_properties)
    return rewritten


def load_manifest(path: Path, selected_ids: set[str] | None = None, limit: int | None = None) -> list[ApplicationTarget]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    targets = [ApplicationTarget.from_record(record) for record in payload.get("targets", [])]
    if selected_ids:
        targets = [target for target in targets if target.id in selected_ids or target.full_name in selected_ids]
    if limit is not None:
        targets = targets[:limit]
    return targets


def detect_build_systems(source_dir: Path) -> list[str]:
    systems: list[str] = []
    if (source_dir / "pom.xml").exists() or (source_dir / "mvnw").exists():
        systems.append("maven")
    if (
        (source_dir / "build.gradle").exists()
        or (source_dir / "build.gradle.kts").exists()
        or (source_dir / "gradlew").exists()
    ):
        systems.append("gradle")
    return systems


def nested_build_root_score(path: Path) -> tuple[int, str]:
    name = path.as_posix().lower()
    score = 0
    for token, weight in {
        "java21": 30,
        "java17": 28,
        "springboot3": 26,
        "spring-boot": 24,
        "backend": 22,
        "boot": 20,
        "server": 18,
        "api": 16,
        "service": 14,
        "auth": 12,
        "module": 10,
        "java8": 4,
    }.items():
        if token in name:
            score += weight
    for token in ("agent", "client", "front", "frontend", "ui", "webapp", "docs", "example", "demo"):
        if token in name:
            score -= 20
    return (-score, name)


def detect_nested_build_root(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    candidates: list[Path] = []
    for child in source_dir.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if detect_build_systems(child):
            candidates.append(child)
        for grandchild in child.iterdir():
            if grandchild.is_dir() and not grandchild.name.startswith(".") and detect_build_systems(grandchild):
                candidates.append(grandchild)
    if not candidates:
        return None
    return sorted(candidates, key=nested_build_root_score)[0]


def is_complete_source_tree(source_dir: Path) -> bool:
    if not source_dir.exists():
        return False
    if not any(path.name != ".git" for path in source_dir.iterdir()):
        return False
    if detect_build_systems(source_dir) or detect_nested_build_root(source_dir):
        return True
    return any((source_dir / name).exists() for name in ("src", "backend", "server", "api"))


def build_command_for_target(target: ApplicationTarget, project_root: Path) -> list[str]:
    return build_plan_for_target(target, project_root).command


def build_plan_for_target(target: ApplicationTarget, project_root: Path) -> BuildPlan:
    source_dir = project_root / target.source_dir
    mirror_config = ensure_mirror_config(project_root)
    if target.build_command:
        return BuildPlan(["bash", "-lc", target.build_command], source_dir, source_dir)

    build_root = source_dir
    systems = [system for system in target.build_systems if system != "auto"]
    if not systems:
        systems = detect_build_systems(source_dir)
        if not systems:
            nested_build_root = detect_nested_build_root(source_dir)
            if nested_build_root is not None:
                build_root = nested_build_root
                systems = detect_build_systems(build_root)

    if "maven" in systems:
        if build_root == source_dir:
            mvn = "./mvnw" if (build_root / "mvnw").exists() else "mvn"
            build_root_args: list[str] = []
        else:
            relative_build_root = build_root.relative_to(source_dir).as_posix()
            mvn = f"{relative_build_root}/mvnw" if (build_root / "mvnw").exists() else "mvn"
            build_root_args = ["-f", f"{relative_build_root}/pom.xml"]
        return BuildPlan([
            mvn,
            *build_root_args,
            "-s",
            str(mirror_config.maven_settings),
            f"-Dmaven.repo.local={project_root / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "-Dmaven.test.skip=true",
            "-DskipITs",
            "-Dmaven.javadoc.skip=true",
            "-Dgpg.skip=true",
            "-Dskip.gpg=true",
            "-Denforcer.skip=true",
            "-Dcheckstyle.skip=true",
            "-Dspotbugs.skip=true",
            "-Dpmd.skip=true",
            "-Dlicense.skip=true",
            "-Dfrontend.skip=true",
            "-Dskip.installnodenpm=true",
            "-Dskip.npm=true",
            "-Dskip.yarn=true",
            "-Dskip.gulp=true",
            "-Dskip.bower=true",
            "-Dskip.webpack=true",
            "-Dmaven.antrun.skip=true",
            "compile",
        ], source_dir, build_root)

    if "gradle" in systems:
        if build_root == source_dir:
            gradle = "./gradlew" if (build_root / "gradlew").exists() else "gradle"
            build_root_args = []
        else:
            relative_build_root = build_root.relative_to(source_dir).as_posix()
            gradle = f"{relative_build_root}/gradlew" if (build_root / "gradlew").exists() else "gradle"
            build_root_args = ["-p", relative_build_root]
        return BuildPlan([
            gradle,
            "--no-daemon",
            "--max-workers=4",
            "-I",
            str(mirror_config.gradle_init),
            *build_root_args,
            "-x",
            "test",
            "classes",
        ], source_dir, build_root)

    return BuildPlan([], source_dir, source_dir)


def codeql_database_command(
    target: ApplicationTarget,
    project_root: Path,
    threads: int,
    ram_mb: int,
    overwrite: bool,
    build_command: list[str],
) -> list[str]:
    command = [
        CODEQL_BIN,
        "database",
        "create",
        str(project_root / target.database_dir),
        "--language=java",
        f"--source-root={project_root / target.source_dir}",
        f"--command={shlex.join(build_command)}",
        f"--threads={threads}",
        f"--ram={ram_mb}",
    ]
    if overwrite:
        command.append("--overwrite")
    return command


def run_command(
    command: list[str],
    cwd: Path,
    log_path: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> tuple[str, int | None, float]:
    started = time.monotonic()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"$ {shlex.join(command)}\n")
        log_file.flush()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
            status = "succeeded" if completed.returncode == 0 else "failed"
            return status, completed.returncode, time.monotonic() - started
        except subprocess.TimeoutExpired:
            log_file.write(f"\n[TIMEOUT] exceeded {timeout_seconds} seconds\n")
            return "timeout", None, time.monotonic() - started


def build_environment(project_root: Path, java_home: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GRADLE_USER_HOME", str(project_root / ".build-cache" / "gradle"))
    env.setdefault("MAVEN_OPTS", f"-Dmaven.repo.local={project_root / '.build-cache' / 'm2' / 'repository'}")
    resolved_java_home = java_home or env.get("JAVA_HOME") or "/usr/lib/jvm/java-17-openjdk"
    env["JAVA_HOME"] = resolved_java_home
    env["PATH"] = f"{resolved_java_home}/bin:{env.get('PATH', '')}"
    return env


def accelerated_clone_url(clone_url: str, accelerator_prefix: str | None) -> str:
    if not accelerator_prefix:
        return clone_url
    return f"{accelerator_prefix.rstrip('/')}/{clone_url}"


def archive_urls_for_target(target: ApplicationTarget, accelerator_prefixes: list[str] | None = None) -> list[str]:
    owner_repo = target.full_name
    direct = [
        f"https://codeload.github.com/{owner_repo}/zip/refs/heads/main",
        f"https://codeload.github.com/{owner_repo}/zip/refs/heads/master",
    ]
    urls = list(direct)
    for prefix in accelerator_prefixes or []:
        for url in direct:
            urls.append(f"{prefix.rstrip('/')}/{url}")
    return urls


def download_archive_source(url: str, source_dir: Path, timeout_seconds: int, log_path: Path) -> tuple[str, int | None, float]:
    started = time.monotonic()
    deadline = started + timeout_seconds
    log_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path = log_path.with_suffix(".zip")
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"$ download {url}\n")
        try:
            with urlopen(url, timeout=timeout_seconds) as response:
                with archive_path.open("wb") as archive_file:
                    while True:
                        if time.monotonic() > deadline:
                            raise TimeoutError(f"archive download exceeded {timeout_seconds} seconds")
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        archive_file.write(chunk)
            extract_root = source_dir.parent / f"{source_dir.name}.archive-tmp"
            if extract_root.exists():
                shutil.rmtree(extract_root)
            extract_root.mkdir(parents=True)
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_root)
            children = [child for child in extract_root.iterdir() if child.is_dir()]
            if not children:
                log_file.write("archive has no top-level directory\n")
                return "failed", 1, time.monotonic() - started
            if source_dir.exists():
                shutil.rmtree(source_dir)
            shutil.move(str(children[0]), str(source_dir))
            shutil.rmtree(extract_root, ignore_errors=True)
            log_file.write(f"extracted archive to {source_dir}\n")
            return "succeeded", 0, time.monotonic() - started
        except Exception as exc:  # noqa: BLE001 - all download errors become retryable status.
            log_file.write(f"archive download failed: {exc}\n")
            return "failed", 1, time.monotonic() - started


def clone_command(
    target: ApplicationTarget,
    source_dir: Path,
    use_partial_clone: bool,
    clone_url: str | None = None,
) -> list[str]:
    command = [
        "git",
        "clone",
        "--depth",
        "1",
    ]
    if use_partial_clone:
        command.extend(["--filter=blob:none"])
    command.extend([
        "--single-branch",
        clone_url or target.clone_url,
        str(source_dir),
    ])
    return command


def clone_target(
    target: ApplicationTarget,
    project_root: Path,
    results_dir: Path,
    timeout_seconds: int,
    attempts: int = 2,
    accelerator_prefixes: list[str] | None = None,
) -> dict:
    source_dir = project_root / target.source_dir
    if is_complete_source_tree(source_dir):
        return {"status": "already_present", "returncode": 0, "seconds": 0.0, "log": None}

    source_dir.parent.mkdir(parents=True, exist_ok=True)
    attempts = max(attempts, 1)
    attempt_logs: list[str] = []
    last_status = "failed"
    last_returncode: int | None = 1
    total_seconds = 0.0

    clone_urls = [target.clone_url]
    for prefix in accelerator_prefixes or []:
        clone_urls.append(accelerated_clone_url(target.clone_url, prefix))

    for url_index, clone_url in enumerate(clone_urls, start=1):
        for attempt in range(1, attempts + 1):
            if source_dir.exists():
                shutil.rmtree(source_dir)
            use_partial_clone = url_index == 1 and attempt == 1
            command = clone_command(target, source_dir, use_partial_clone, clone_url)
            suffix = "clone" if url_index == 1 and attempt == 1 else f"clone.url{url_index}.retry{attempt}"
            log_path = results_dir / "logs" / f"{target.id}.{suffix}.log"
            attempt_logs.append(str(log_path))
            status, returncode, seconds = run_command(command, project_root, log_path, timeout_seconds)
            total_seconds += seconds
            last_status = status
            last_returncode = returncode
            if status == "succeeded":
                return {
                    "status": status,
                    "returncode": returncode,
                    "seconds": round(total_seconds, 3),
                    "attempts": attempt,
                    "url_attempts": url_index,
                    "clone_url": clone_url,
                    "log": str(log_path),
                    "logs": attempt_logs,
                }

    for archive_index, archive_url in enumerate(archive_urls_for_target(target, accelerator_prefixes), start=1):
        if source_dir.exists():
            shutil.rmtree(source_dir)
        log_path = results_dir / "logs" / f"{target.id}.archive{archive_index}.log"
        attempt_logs.append(str(log_path))
        status, returncode, seconds = download_archive_source(archive_url, source_dir, timeout_seconds, log_path)
        total_seconds += seconds
        last_status = status
        last_returncode = returncode
        if status == "succeeded" and is_complete_source_tree(source_dir):
            return {
                "status": status,
                "returncode": returncode,
                "seconds": round(total_seconds, 3),
                "attempts": attempts,
                "url_attempts": len(clone_urls),
                "archive_attempts": archive_index,
                "archive_url": archive_url,
                "log": str(log_path),
                "logs": attempt_logs,
            }

    if source_dir.exists() and not is_complete_source_tree(source_dir):
        shutil.rmtree(source_dir)
    return {
        "status": last_status,
        "returncode": last_returncode,
        "seconds": round(total_seconds, 3),
        "attempts": attempts,
        "url_attempts": len(clone_urls),
        "log": attempt_logs[-1] if attempt_logs else None,
        "logs": attempt_logs,
    }


def build_target(
    target: ApplicationTarget,
    project_root: Path,
    results_dir: Path,
    threads: int,
    ram_mb: int,
    overwrite: bool,
    timeout_seconds: int,
    dry_run: bool,
    java_home: str | None = None,
    java_homes: list[str] | None = None,
) -> dict:
    source_dir = project_root / target.source_dir
    database_dir = project_root / target.database_dir
    database_dir.parent.mkdir(parents=True, exist_ok=True)
    rewritten_wrappers = rewrite_gradle_wrapper_distributions(source_dir)
    build_plan = build_plan_for_target(target, project_root)
    build_command = build_plan.command
    if not build_command:
        return {
            "target_id": target.id,
            "full_name": target.full_name,
            "status": "no_build_system",
            "source_dir": str(source_dir),
            "database_dir": str(database_dir),
            "build_command": None,
        }

    codeql_command = codeql_database_command(target, project_root, threads, ram_mb, overwrite, build_command)
    log_path = results_dir / "logs" / f"{target.id}.codeql.log"
    requested_java_homes = java_homes or ([java_home] if java_home else default_java_homes())
    candidate_java_homes = (
        normalize_requested_java_homes(requested_java_homes)
        if java_homes or java_home
        else existing_java_homes(requested_java_homes)
    ) or [java_home or "/usr/lib/jvm/java-17-openjdk"]

    if dry_run:
        status, returncode, seconds = "dry_run", 0, 0.0
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"$ {shlex.join(codeql_command)}\n", encoding="utf-8")
        selected_java_home = candidate_java_homes[0]
        attempts_used = 1
    else:
        status = "failed"
        returncode: int | None = 1
        seconds = 0.0
        selected_java_home = candidate_java_homes[0]
        attempts_used = 0
        for attempt_index, candidate_java_home in enumerate(candidate_java_homes, start=1):
            attempt_log_path = log_path
            if len(candidate_java_homes) > 1:
                java_name = Path(candidate_java_home).name.replace("/", "_")
                attempt_log_path = results_dir / "logs" / f"{target.id}.java{attempt_index}.{java_name}.codeql.log"
            env = build_environment(project_root, candidate_java_home)
            status, returncode, attempt_seconds = run_command(
                codeql_command,
                build_plan.cwd,
                attempt_log_path,
                timeout_seconds,
                env,
            )
            seconds += attempt_seconds
            attempts_used = attempt_index
            selected_java_home = candidate_java_home
            log_path = attempt_log_path
            if status == "succeeded":
                break

    return {
        "target_id": target.id,
        "full_name": target.full_name,
        "status": f"build_{status}",
        "returncode": returncode,
        "seconds": round(seconds, 3),
        "source_dir": str(source_dir),
        "database_dir": str(database_dir),
        "build_cwd": str(build_plan.cwd),
        "build_root": str(build_plan.build_root),
        "build_command": shlex.join(build_command),
        "codeql_command": shlex.join(codeql_command),
        "java_home": selected_java_home,
        "attempts": attempts_used,
        "rewritten_gradle_wrappers": [str(path) for path in rewritten_wrappers],
        "log": str(log_path),
    }


def append_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def latest_status_records(path: Path) -> list[dict]:
    if not path.exists():
        return []

    latest: dict[str, dict] = {}
    order: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        target_id = record.get("target_id")
        if not target_id:
            continue

        normalized: dict | None = None
        if record.get("phase") == "clone":
            if record.get("status") not in {"already_present", "succeeded"}:
                normalized = {**record, "status": f"clone_{record.get('status')}"}
        else:
            normalized = record

        if normalized is None:
            continue
        if target_id not in latest:
            order.append(target_id)
        latest[target_id] = normalized

    return [latest[target_id] for target_id in order]


def write_summary(path: Path, records: list[dict]) -> None:
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1

    lines = [
        "# Java 应用 CodeQL build-mode 数据库构建摘要",
        "",
        f"- 生成时间：{datetime.now(timezone.utc).isoformat()}",
        f"- 目标数量：{len(records)}",
        "",
        "## 状态统计",
        "",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## 目标明细", "", "| Target | Status | DB | Log |", "| --- | --- | --- | --- |"])
    for record in records:
        lines.append(
            f"| `{record.get('full_name')}` | `{record['status']}` | "
            f"`{record.get('database_dir', '')}` | `{record.get('log') or ''}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--target", action="append", default=[], help="Target id or owner/repo. Repeatable.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--ram", type=int, default=8192)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--clone-timeout", type=int, default=600)
    parser.add_argument("--clone-attempts", type=int, default=2)
    parser.add_argument("--java-home", help="JAVA_HOME used while CodeQL runs the build command.")
    parser.add_argument("--java-home-candidate", action="append", default=[], help="JAVA_HOME candidate for build retry. Repeatable.")
    parser.add_argument(
        "--github-accelerator",
        action="append",
        default=[],
        help="GitHub clone accelerator prefix, for example https://gh-proxy.com/. Repeatable.",
    )
    parser.add_argument("--use-default-github-accelerators", action="store_true")
    parser.add_argument("--no-overwrite", action="store_true")
    parser.add_argument("--skip-clone", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset-status", action="store_true")
    args = parser.parse_args()

    selected = set(args.target) if args.target else None
    targets = load_manifest(args.manifest, selected, args.limit)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    status_path = args.results_dir / "application_db_build_status.jsonl"
    summary_path = args.results_dir / "application_db_build_summary.md"
    if args.reset_status:
        status_path.unlink(missing_ok=True)
        summary_path.unlink(missing_ok=True)

    for index, target in enumerate(targets, start=1):
        print(f"[{index}/{len(targets)}] {target.full_name}", file=sys.stderr)
        clone_record = None
        if not args.skip_clone:
            clone_record = {
                "target_id": target.id,
                "full_name": target.full_name,
                "phase": "clone",
                **clone_target(
                    target,
                    PROJECT_ROOT,
                    args.results_dir,
                    args.clone_timeout,
                    args.clone_attempts,
                    (DEFAULT_GITHUB_ACCELERATOR_PREFIXES if args.use_default_github_accelerators else []) + args.github_accelerator,
                ),
            }
            append_jsonl(status_path, [clone_record])
            if clone_record["status"] not in {"already_present", "succeeded"}:
                write_summary(summary_path, latest_status_records(status_path))
                continue

        build_record = build_target(
            target=target,
            project_root=PROJECT_ROOT,
            results_dir=args.results_dir,
            threads=args.threads,
            ram_mb=args.ram,
            overwrite=not args.no_overwrite,
            timeout_seconds=args.timeout,
            dry_run=args.dry_run,
            java_home=args.java_home,
            java_homes=args.java_home_candidate or ([args.java_home] if args.java_home else None),
        )
        if clone_record:
            build_record["clone_status"] = clone_record["status"]
        append_jsonl(status_path, [build_record])
        write_summary(summary_path, latest_status_records(status_path))

    print(f"[build] wrote status to {status_path}")
    print(f"[build] wrote summary to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
