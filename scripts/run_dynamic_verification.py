#!/usr/bin/env python3
"""Run real-HTTP dynamic verification probes for Web DoS candidates."""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parents[1]
DYNAMIC_DIR = BASE_DIR / "dynamic-verification"
LOG_DIR = BASE_DIR / "results" / "phase4" / "dynamic_verification" / "logs"
SUMMARY_DIR = BASE_DIR / "results" / "phase4" / "dynamic_verification"
STATIC_HUNT_LOG_DIR = BASE_DIR / "results" / "static_hunts" / "dynamic_verification" / "logs"
STATIC_HUNT_SUMMARY_DIR = BASE_DIR / "results" / "static_hunts" / "dynamic_verification"
OOM_EXIT_CODE = 100


@dataclasses.dataclass(frozen=True)
class DynamicCase:
    case_id: str
    main_class: str
    log_name: str
    default_heap: str
    smoke_args: tuple[str, ...]
    oom_args: tuple[str, ...]

    def args_for(self, run_profile: str, port: int) -> tuple[str, ...]:
        selected = self.oom_args if run_profile == "oom" else self.smoke_args
        return (*selected, str(port), run_profile)


CASES: tuple[DynamicCase, ...] = (
    DynamicCase(
        "WEB-REAL-0001",
        "org.example.dos.dynamic.JerseyOAuth1HttpProbe",
        "jersey-oauth-real-http.log",
        "384m",
        ("32", "65536", "8"),
        ("-1", "524288", "64"),
    ),
    DynamicCase(
        "WEB-REAL-0002",
        "org.example.dos.dynamic.JerseyMultipartHttpProbe",
        "jersey-multipart-real-http.log",
        "384m",
        ("4096", "4096", "256"),
        ("-1", "4096", "4096"),
    ),
    DynamicCase(
        "WEB-REAL-0003",
        "org.example.dos.dynamic.UndertowLearningPushHttpProbe",
        "undertow-learning-push-real-http-rerun.log",
        "384m",
        ("256", "262144", "64"),
        ("-1", "524288", "256"),
    ),
    DynamicCase(
        "WEB-REAL-0004",
        "io.undertow.server.handlers.proxy.mod_cluster.UndertowModClusterHttpProbe",
        "undertow-mod-cluster-real-http.log",
        "384m",
        ("64", "1048576", "16"),
        ("-1", "2097152", "128"),
    ),
    DynamicCase(
        "WEB-REAL-0005",
        "org.example.dos.dynamic.JettyProxyServletHttpProbe",
        "jetty-proxyservlet-real-http-rerun.log",
        "384m",
        ("128", "1048576", "32"),
        ("-1", "2097152", "128"),
    ),
    DynamicCase(
        "WEB-REAL-0006",
        "org.example.dos.dynamic.TomcatWebdavLocksHttpProbe",
        "tomcat-webdav-locks-real-http.log",
        "384m",
        ("128", "256", "32"),
        ("-1", "65536", "256"),
    ),
    DynamicCase(
        "WEB-REAL-0007",
        "org.example.dos.dynamic.TomcatWebdavDeadPropertiesHttpProbe",
        "tomcat-webdav-dead-properties-real-http.log",
        "384m",
        ("64", "16", "512", "16"),
        ("-1", "4096", "2048", "128"),
    ),
    DynamicCase(
        "WEB-REAL-0008",
        "org.example.dos.dynamic.JettyPushSessionCacheHttpProbe",
        "jetty-push-session-cache-real-http.log",
        "384m",
        ("128", "1024", "32"),
        ("-1", "32768", "256"),
    ),
    DynamicCase(
        "WEB-REAL-0009",
        "org.example.dos.dynamic.JettyPushCacheFilterHttpProbe",
        "jetty-push-cache-filter-real-http.log",
        "384m",
        ("128", "1024", "32"),
        ("-1", "32768", "256"),
    ),
)

STATIC_HUNT_CASES: tuple[DynamicCase, ...] = (
    DynamicCase(
        "TOMCAT-STATIC-0003",
        "org.example.dos.dynamic.TomcatWebdavDeadPropertiesHttpProbe",
        "tomcat-webdav-dead-properties-real-http.log",
        "384m",
        ("64", "16", "512", "16"),
        ("-1", "4096", "2048", "128"),
    ),
    DynamicCase(
        "JETTY-STATIC-0002",
        "org.example.dos.dynamic.JettyPushSessionCacheHttpProbe",
        "jetty-push-session-cache-real-http.log",
        "384m",
        ("128", "1024", "32"),
        ("-1", "32768", "256"),
    ),
    DynamicCase(
        "JETTY-STATIC-0004",
        "org.example.dos.dynamic.JettyPushCacheFilterHttpProbe",
        "jetty-push-cache-filter-real-http.log",
        "384m",
        ("128", "1024", "32"),
        ("-1", "32768", "256"),
    ),
    DynamicCase(
        "UNDERTOW-STATIC-0003",
        "org.example.dos.dynamic.UndertowMultipartHttpProbe",
        "undertow-multipart-real-http.log",
        "384m",
        ("32", "4096", "16"),
        ("128", "4096", "32"),
    ),
)

CASE_ALIASES = {
    "WEB-P4-0025-0027": "WEB-REAL-0006",
    "TOMCAT-STATIC-0003": "WEB-REAL-0007",
    "JETTY-STATIC-0002": "WEB-REAL-0008",
    "JETTY-STATIC-0004": "WEB-REAL-0009",
}


def run(command: list[str], cwd: Path, stdout: object | None = None) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command))
    return subprocess.run(command, cwd=cwd, check=False, text=True, stdout=stdout, stderr=subprocess.STDOUT)


def ensure_built() -> str:
    mvn = ["mvn", "-q", "-DskipTests", "package", "dependency:build-classpath", "-Dmdep.outputFile=target/classpath.txt"]
    completed = run(mvn, DYNAMIC_DIR)
    if completed.returncode != 0:
        raise RuntimeError(f"Maven build failed with exit code {completed.returncode}")
    classpath_file = DYNAMIC_DIR / "target" / "classpath.txt"
    classpath = classpath_file.read_text(encoding="utf-8").strip()
    return f"{DYNAMIC_DIR / 'target' / 'classes'}:{classpath}"


def build_java_command(
    case: DynamicCase,
    classpath: str,
    heap: str | None,
    port_base: int,
    run_profile: str,
) -> list[str]:
    selected_heap = heap or case.default_heap
    return [
        "java",
        f"-Xmx{selected_heap}",
        "-cp",
        classpath,
        case.main_class,
        *case.args_for(run_profile, port_base),
    ]


def parse_log_values(log_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and all(ch.isalnum() or ch in "_-" for ch in key):
            values[key] = value
    return values


def parse_summary(
    completed: subprocess.CompletedProcess[str],
    log_path: Path,
    require_oom: bool = True,
) -> dict[str, str]:
    values = parse_log_values(log_path)
    verdict = values.get("verdict", "")
    confirmed = verdict.startswith("CONFIRMED_") and "OOM" in verdict
    if completed.returncode == OOM_EXIT_CODE and confirmed:
        return {"status": "verified", **values}
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    if require_oom and "java.lang.OutOfMemoryError: Java heap space" in log_text:
        return {
            "status": "verified",
            **values,
            "verdict": "CONFIRMED_HEAP_OOM_REAL_HTTP",
            "oomSignal": "server_thread_log",
            "processExitCode": str(completed.returncode),
        }
    if not require_oom and completed.returncode == 0 and values.get("verdict") == "COMPLETED":
        return {"status": "completed_without_oom", **values}
    raise RuntimeError(
        f"{log_path.name} did not confirm OOM: exit={completed.returncode}, verdict={verdict or '<missing>'}"
    )


def retained_metric(values: dict[str, str]) -> str:
    for key in (
        "deadPropertyPathsBeforeOom",
        "deadPropertyPaths",
        "cacheSizeBeforeOom",
        "cacheSize",
        "associatedPathsBeforeOom",
        "associatedPaths",
        "multipartFilesBeforeOom",
        "multipartFiles",
        "materializedPartsBeforeOom",
        "materializedParts",
    ):
        if key in values:
            return f"{key}={values[key]}"
    return ""


def parse_static_hunt_summary(
    candidate_id: str,
    completed: subprocess.CompletedProcess[str],
    log_path: Path,
    require_oom: bool,
) -> dict[str, str]:
    values = parse_log_values(log_path)
    verdict = values.get("verdict", "")
    if completed.returncode == 0 and require_oom and (
        verdict.startswith("NOT_VERIFIED_") or verdict.startswith("BLOCKED_")
    ):
        parsed = {"status": "not_verified", **values}
    else:
        parsed = parse_summary(completed, log_path, require_oom=require_oom)
    requests_sent = (
        parsed.get("requestsBeforeOom")
        or parsed.get("requestsCompleted")
        or parsed.get("requestsSent")
        or parsed.get("requests")
        or ""
    )
    notes = parsed.get("notes", "")
    if parsed.get("cleanupRemovedTempFiles"):
        notes = f"{notes}; cleanupRemovedTempFiles={parsed['cleanupRemovedTempFiles']}".strip("; ")
    return {
        "candidate_id": candidate_id,
        "status": parsed.get("status", "not_verified"),
        "verdict": parsed.get("verdict", ""),
        "oomSignal": parsed.get("oomSignal", "process_exit" if parsed.get("status") == "verified" else ""),
        "heap": parsed.get("maxHeapBytes", "unknown"),
        "requestsSent": requests_sent,
        "retainedMetric": retained_metric(parsed),
        "log": str(log_path),
        "notes": notes,
    }


def selected_cases(case_ids: Iterable[str], suite: str = "web-real") -> list[DynamicCase]:
    registry = STATIC_HUNT_CASES if suite == "static-hunt" else CASES
    wanted = [CASE_ALIASES.get(case_id, case_id) if suite == "web-real" else case_id for case_id in case_ids]
    if not wanted:
        return list(registry)
    by_id = {case.case_id: case for case in registry}
    missing = sorted(set(wanted) - set(by_id))
    if missing:
        raise ValueError(f"unknown dynamic verification case(s): {', '.join(missing)}")
    return [by_id[case_id] for case_id in wanted]


def output_paths_for(suite: str) -> tuple[Path, Path]:
    if suite == "static-hunt":
        return (
            STATIC_HUNT_LOG_DIR,
            STATIC_HUNT_SUMMARY_DIR / "static_hunt_dynamic_verification_summary.json",
        )
    if suite == "web-real":
        return (
            LOG_DIR,
            SUMMARY_DIR / "dynamic_verification_summary.json",
        )
    raise ValueError(f"unknown dynamic verification suite: {suite}")


def run_cases(
    cases: list[DynamicCase],
    heap: str | None,
    port_base: int,
    run_profile: str,
    suite: str = "web-real",
) -> list[dict[str, str]]:
    classpath = ensure_built()
    log_dir, summary_path = output_paths_for(suite)
    log_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, str]] = []
    for index, case in enumerate(cases):
        log_path = log_dir / case.log_name
        command = build_java_command(case, classpath, heap, port_base + index, run_profile)
        with log_path.open("w", encoding="utf-8") as handle:
            completed = run(command, DYNAMIC_DIR, stdout=handle)
        if suite == "static-hunt":
            summary = parse_static_hunt_summary(case.case_id, completed, log_path, require_oom=(run_profile == "oom"))
        else:
            summary = {
                "case_id": case.case_id,
                "log": str(log_path.relative_to(BASE_DIR)),
                **parse_summary(completed, log_path, require_oom=(run_profile == "oom")),
            }
        summaries.append(summary)
        print(f"{case.case_id}: {summary['status']} ({summary.get('verdict', 'no verdict')})")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {summary_path.relative_to(BASE_DIR)}")
    return summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[], help="case id to run; defaults to all")
    parser.add_argument("--heap", default=None, help="override JVM -Xmx value, e.g. 512m")
    parser.add_argument("--port-base", type=int, default=28080, help="first local port used by HTTP probes")
    parser.add_argument("--profile", choices=("smoke", "oom"), default="smoke", help="run bounded smoke or OOM profile")
    parser.add_argument(
        "--suite",
        choices=("web-real", "static-hunt"),
        default="web-real",
        help="verification case registry and output root",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_cases(selected_cases(args.case, suite=args.suite), args.heap, args.port_base, args.profile, suite=args.suite)
        return 0
    except Exception as exc:
        print(f"dynamic verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
