#!/usr/bin/env python3
import argparse
import io
import gzip
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def http_request(method, url, body=None, headers=None, timeout=10):
    req = urllib.request.Request(url, data=body, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(4096)
            return {
                "ok": True,
                "status": resp.status,
                "reason": resp.reason,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "body_prefix": data.decode("utf-8", "replace"),
            }
    except urllib.error.HTTPError as exc:
        data = exc.read(4096)
        return {
            "ok": False,
            "status": exc.code,
            "reason": exc.reason,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "body_prefix": data.decode("utf-8", "replace"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "reason": type(exc).__name__,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "body_prefix": str(exc),
        }


def run_cmd(args):
    try:
        proc = subprocess.run(args, text=True, capture_output=True, timeout=10)
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"returncode": None, "stdout": "", "stderr": repr(exc)}


def container_state(name):
    inspect = run_cmd([
        "docker",
        "inspect",
        name,
        "--format",
        "{{.State.Status}} {{.State.Running}} {{.State.ExitCode}} {{.State.OOMKilled}} {{.State.Restarting}} {{.State.StartedAt}} {{.State.FinishedAt}}",
    ])
    stats = run_cmd([
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
        name,
    ])
    return {"inspect": inspect, "stats": stats}


def parse_inspect_stdout(stdout):
    parts = (stdout or "").split()
    return {
        "status": parts[0] if len(parts) > 0 else None,
        "running": parts[1].lower() == "true" if len(parts) > 1 else False,
        "exit_code": int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else None,
        "oom_killed": parts[3].lower() == "true" if len(parts) > 3 else False,
        "restarting": parts[4].lower() == "true" if len(parts) > 4 else False,
    }


def make_spans(count, tag_bytes):
    tag_value = "A" * tag_bytes
    spans = []
    base_ts = int(time.time() * 1000000)
    for idx in range(count):
        trace_id = f"{idx + 1:032x}"
        span_id = f"{idx + 1:016x}"
        spans.append({
            "traceId": trace_id,
            "id": span_id,
            "name": "dynamic-validation",
            "timestamp": base_ts + idx,
            "duration": 1000,
            "localEndpoint": {
                "serviceName": "dos-validation",
                "ipv4": "127.0.0.1",
            },
            "tags": {
                "case": "openzipkin__zipkin-ZIPKIN-APP-STATIC-0001",
                "payload": tag_value,
            },
        })
    return json.dumps(spans, separators=(",", ":")).encode("utf-8")


def make_spans_gzip(count, tag_bytes):
    tag_value = "A" * tag_bytes
    base_ts = int(time.time() * 1000000)
    plain_bytes = 2
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9) as gz:
        gz.write(b"[")
        for idx in range(count):
            trace_id = f"{idx + 1:032x}"
            span_id = f"{idx + 1:016x}"
            item = json.dumps(
                {
                    "traceId": trace_id,
                    "id": span_id,
                    "name": "dynamic-validation",
                    "timestamp": base_ts + idx,
                    "duration": 1000,
                    "localEndpoint": {
                        "serviceName": "dos-validation",
                        "ipv4": "127.0.0.1",
                    },
                    "tags": {
                        "case": "openzipkin__zipkin-ZIPKIN-APP-STATIC-0001",
                        "payload": tag_value,
                    },
                },
                separators=(",", ":"),
            ).encode("utf-8")
            if idx:
                gz.write(b",")
                plain_bytes += 1
            gz.write(item)
            plain_bytes += len(item)
        gz.write(b"]")
    return buf.getvalue(), plain_bytes


def write_jsonl(path, record):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:19411")
    parser.add_argument("--container", default="dosval-openzipkin-zipkin-static-0001")
    parser.add_argument("--out", default="logs/probe_results.jsonl")
    parser.add_argument("--metrics-out", default="evidence/metrics_snapshots.txt")
    parser.add_argument("--mode", choices=["plain", "gzip", "both"], default="both")
    parser.add_argument("--pause", type=float, default=2.0)
    parser.add_argument(
        "--extra-gzip",
        action="append",
        default=[],
        metavar="SPAN_COUNT:TAG_BYTES",
        help="append an extra gzip scenario without materializing the uncompressed JSON in memory",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path = Path(args.metrics_out)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)

    scenarios = []
    if args.mode in ("plain", "both"):
        scenarios.extend([
            {"mode": "plain", "span_count": 200, "tag_bytes": 256},
            {"mode": "plain", "span_count": 1000, "tag_bytes": 1024},
            {"mode": "plain", "span_count": 2500, "tag_bytes": 2048},
        ])
    if args.mode in ("gzip", "both"):
        scenarios.extend([
            {"mode": "gzip", "span_count": 500, "tag_bytes": 1024},
            {"mode": "gzip", "span_count": 2500, "tag_bytes": 4096},
            {"mode": "gzip", "span_count": 6000, "tag_bytes": 8192},
            {"mode": "gzip", "span_count": 10000, "tag_bytes": 8192},
        ])
    for item in args.extra_gzip:
        span_count, tag_bytes = item.split(":", 1)
        scenarios.append({"mode": "gzip_stream", "span_count": int(span_count), "tag_bytes": int(tag_bytes)})

    health = http_request("GET", f"{args.base_url}/health", timeout=5)
    write_jsonl(out_path, {
        "event": "initial_health",
        "time": time.time(),
        "health": health,
        "container": container_state(args.container),
    })

    request_count = 0
    stop_reason = None
    for scenario in scenarios:
        plain_bytes = None
        if scenario["mode"] == "gzip_stream":
            body, plain_bytes = make_spans_gzip(scenario["span_count"], scenario["tag_bytes"])
            payload = b""
        else:
            payload = make_spans(scenario["span_count"], scenario["tag_bytes"])
            body = payload
        headers = {"Content-Type": "application/json", "User-Agent": "dos-dynamic-validator/zipkin"}
        if scenario["mode"] == "gzip":
            body = gzip.compress(payload, compresslevel=9)
            headers["Content-Encoding"] = "gzip"
        elif scenario["mode"] == "gzip_stream":
            headers["Content-Encoding"] = "gzip"

        before = container_state(args.container)
        response = http_request(
            "POST",
            f"{args.base_url}/api/v2/spans",
            body=body,
            headers=headers,
            timeout=30,
        )
        request_count += 1
        after_health = http_request("GET", f"{args.base_url}/health", timeout=5)
        after = container_state(args.container)
        metrics = http_request("GET", f"{args.base_url}/metrics", timeout=5)
        with metrics_path.open("a", encoding="utf-8") as mf:
            mf.write(f"\n--- scenario {request_count} {scenario} ---\n")
            mf.write(metrics.get("body_prefix", ""))
            mf.write("\n")

        record = {
            "event": "probe_request",
            "time": time.time(),
            "scenario": scenario,
            "plain_bytes": plain_bytes if plain_bytes is not None else len(payload),
            "wire_bytes": len(body),
            "gzip_ratio": round((plain_bytes if plain_bytes is not None else len(payload)) / len(body), 2) if len(body) else None,
            "response": response,
            "health_after": after_health,
            "container_before": before,
            "container_after": after,
        }
        write_jsonl(out_path, record)

        status = response.get("status")
        state = parse_inspect_stdout(after["inspect"].get("stdout", ""))
        running = state["running"]
        oom = state["oom_killed"]
        if status in (400, 413, 414, 415, 429):
            stop_reason = f"rejected_status_{status}"
            break
        if response.get("status") is None or after_health.get("status") != 200 or not running or oom:
            stop_reason = "availability_or_container_failure"
            break
        time.sleep(args.pause)

    final_health_checks = []
    for _ in range(5):
        final_health_checks.append(http_request("GET", f"{args.base_url}/health", timeout=5))
        time.sleep(1)
    write_jsonl(out_path, {
        "event": "final",
        "time": time.time(),
        "request_count": request_count,
        "stop_reason": stop_reason or "completed_safety_cap",
        "final_health_checks": final_health_checks,
        "container": container_state(args.container),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
