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
)

CASE_ALIASES = {
    "WEB-P4-0025-0027": "WEB-REAL-0006",
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


def selected_cases(case_ids: Iterable[str]) -> list[DynamicCase]:
    wanted = [CASE_ALIASES.get(case_id, case_id) for case_id in case_ids]
    if not wanted:
        return list(CASES)
    by_id = {case.case_id: case for case in CASES}
    missing = sorted(set(wanted) - set(by_id))
    if missing:
        raise ValueError(f"unknown dynamic verification case(s): {', '.join(missing)}")
    return [by_id[case_id] for case_id in wanted]


def run_cases(cases: list[DynamicCase], heap: str | None, port_base: int, run_profile: str) -> list[dict[str, str]]:
    classpath = ensure_built()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, str]] = []
    for index, case in enumerate(cases):
        log_path = LOG_DIR / case.log_name
        command = build_java_command(case, classpath, heap, port_base + index, run_profile)
        with log_path.open("w", encoding="utf-8") as handle:
            completed = run(command, DYNAMIC_DIR, stdout=handle)
        summary = {
            "case_id": case.case_id,
            "log": str(log_path.relative_to(BASE_DIR)),
            **parse_summary(completed, log_path, require_oom=(run_profile == "oom")),
        }
        summaries.append(summary)
        print(f"{case.case_id}: {summary['status']} ({summary.get('verdict', 'no verdict')})")
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = SUMMARY_DIR / "dynamic_verification_summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {summary_path.relative_to(BASE_DIR)}")
    return summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[], help="case id to run; defaults to all")
    parser.add_argument("--heap", default=None, help="override JVM -Xmx value, e.g. 512m")
    parser.add_argument("--port-base", type=int, default=28080, help="first local port used by HTTP probes")
    parser.add_argument("--profile", choices=("smoke", "oom"), default="smoke", help="run bounded smoke or OOM profile")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_cases(selected_cases(args.case), args.heap, args.port_base, args.profile)
        return 0
    except Exception as exc:
        print(f"dynamic verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
