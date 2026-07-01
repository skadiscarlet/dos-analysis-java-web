#!/usr/bin/env python3
import argparse
import base64
import http.client
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

BASE_REQUEST_B64 = (
    "Cj9vcmcuYXBhY2hlLmNhbGNpdGUuYXZhdGljYS5wcm90by5SZXF1ZXN0cyRPcGVu"
    "Q29ubmVjdGlvblJlcXVlc3QSFAoSZG9zLXZhbGlkYXRvci1jb25u"
)


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
      byte = value & 0x7F
      value >>= 7
      if value:
          out.append(byte | 0x80)
      else:
          out.append(byte)
          return bytes(out)


def make_body(target_total_size: int) -> bytes:
    base = base64.b64decode(BASE_REQUEST_B64)
    if target_total_size <= len(base):
        return base
    field_key = (2047 << 3) | 2
    # Account for varint length changing as padding grows.
    padding_len = target_total_size - len(base) - len(varint(field_key)) - 1
    while True:
        overhead = len(varint(field_key)) + len(varint(max(0, padding_len)))
        new_padding_len = max(0, target_total_size - len(base) - overhead)
        if new_padding_len == padding_len:
            break
        padding_len = new_padding_len
    return base + varint(field_key) + varint(padding_len) + (b"P" * padding_len)


def run(cmd, cwd=None, timeout=30):
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def compose_container_id(args, service):
    res = run(["docker", "compose", "-p", args.compose_project, "-f", args.compose_file, "ps", "-q", service], timeout=20)
    cid = res["stdout"].strip().splitlines()
    return cid[0] if cid else None


def docker_json(args_list, timeout=20):
    res = run(args_list, timeout=timeout)
    if res["returncode"] != 0 or not res["stdout"].strip():
        return {"error": res}
    try:
        return json.loads(res["stdout"])
    except json.JSONDecodeError:
        return {"raw": res["stdout"], "stderr": res["stderr"], "returncode": res["returncode"]}


def append_jsonl(path: Path, obj):
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def http_request(base_url, method, path, body=None, headers=None, timeout=20):
    parsed = urlparse(base_url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    conn = conn_cls(parsed.hostname, port, timeout=timeout)
    started = time.time()
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        sample = resp.read(2048)
        return {
            "ok": True,
            "status": resp.status,
            "reason": resp.reason,
            "duration_seconds": round(time.time() - started, 3),
            "response_sample": sample.decode("utf-8", "replace"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": repr(exc),
            "duration_seconds": round(time.time() - started, 3),
        }
    finally:
        conn.close()


def collect_snapshot(args, label):
    logs_dir = Path(args.case_dir) / "logs"
    router_cid = compose_container_id(args, "router")
    broker_cid = compose_container_id(args, "broker")
    snapshot = {
        "ts": time.time(),
        "label": label,
        "router_container_id": router_cid,
        "broker_container_id": broker_cid,
    }
    if router_cid:
        snapshot["router_inspect"] = docker_json(["docker", "inspect", router_cid])
        stats = run(["docker", "stats", "--no-stream", "--format", "{{json .}}", router_cid], timeout=20)
        snapshot["router_stats_raw"] = stats
        append_jsonl(logs_dir / "docker_stats.jsonl", {"label": label, "service": "router", "stats": stats})
        heap = run(["docker", "exec", router_cid, "sh", "-lc", "jcmd 1 GC.heap_info 2>&1 || true"], timeout=20)
        snapshot["router_heap_info"] = heap
        append_jsonl(logs_dir / "router_heap_info.jsonl", {"label": label, "heap": heap})
    if broker_cid:
        stats = run(["docker", "stats", "--no-stream", "--format", "{{json .}}", broker_cid], timeout=20)
        append_jsonl(logs_dir / "docker_stats.jsonl", {"label": label, "service": "broker", "stats": stats})
    health = http_request(args.router_url, "GET", "/status/health", timeout=5)
    snapshot["router_health"] = health
    append_jsonl(logs_dir / "availability_checks.jsonl", {"label": label, "health": health})
    append_jsonl(logs_dir / "probe_observations.jsonl", snapshot)
    return snapshot


def wait_ready(args):
    deadline = time.time() + args.ready_timeout
    while time.time() < deadline:
        router = http_request(args.router_url, "GET", "/status/health", timeout=5)
        broker = http_request(args.broker_url, "GET", "/status/health", timeout=5)
        append_jsonl(Path(args.case_dir) / "logs" / "readiness_checks.jsonl", {
            "ts": time.time(),
            "router": router,
            "broker": broker,
        })
        if router.get("ok") and router.get("status") == 200 and broker.get("ok") and broker.get("status") == 200:
            return True
        time.sleep(5)
    return False


def save_container_logs(args, label):
    logs_dir = Path(args.case_dir) / "logs"
    for service in ["router", "broker", "coordinator", "postgres", "zookeeper"]:
        cid = compose_container_id(args, service)
        if not cid:
            continue
        res = run(["docker", "logs", "--tail", "800", cid], timeout=30)
        (logs_dir / f"{label}_{service}.docker.log").write_text(
            res["stdout"] + "\n--- STDERR ---\n" + res["stderr"],
            encoding="utf-8",
            errors="replace",
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--compose-project", default="druid_avatica_case")
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--router-url", default="http://127.0.0.1:28888")
    parser.add_argument("--broker-url", default="http://127.0.0.1:28082")
    parser.add_argument("--ready-timeout", type=int, default=240)
    parser.add_argument("--wait-only", action="store_true")
    parser.add_argument("--sizes", default="87,1048576,8388608,16777216,33554432,67108864,100663296")
    parser.add_argument("--request-timeout", type=int, default=30)
    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    (case_dir / "logs").mkdir(parents=True, exist_ok=True)
    (case_dir / "evidence").mkdir(parents=True, exist_ok=True)

    ready = wait_ready(args)
    collect_snapshot(args, "after_readiness_wait")
    save_container_logs(args, "startup")
    if args.wait_only:
        print(json.dumps({"ready": ready}))
        return 0 if ready else 2
    if not ready:
        print(json.dumps({"ready": False, "error": "readiness timeout"}))
        return 2

    endpoint = "/druid/v2/sql/avatica-protobuf/"
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    responses_path = case_dir / "logs" / "http_responses.log"
    request_count = 0
    collect_snapshot(args, "baseline")

    for size in sizes:
        body = make_body(size)
        request_count += 1
        label = f"before_post_{len(body)}"
        collect_snapshot(args, label)
        response = http_request(
            args.router_url,
            "POST",
            endpoint,
            body=body,
            headers={
                "Content-Type": "application/x-protobuf",
                "Content-Length": str(len(body)),
                "Connection": "close",
            },
            timeout=args.request_timeout,
        )
        record = {
            "ts": time.time(),
            "request_index": request_count,
            "target_size": size,
            "actual_size": len(body),
            "response": response,
        }
        append_jsonl(case_dir / "logs" / "http_responses.jsonl", record)
        with responses_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        after = collect_snapshot(args, f"after_post_{len(body)}")
        save_container_logs(args, f"after_post_{len(body)}")
        state = after.get("router_inspect")
        if isinstance(state, list) and state:
            running = state[0].get("State", {}).get("Running")
            exit_code = state[0].get("State", {}).get("ExitCode")
            oom_killed = state[0].get("State", {}).get("OOMKilled")
            if not running:
                append_jsonl(case_dir / "logs" / "probe_observations.jsonl", {
                    "ts": time.time(),
                    "label": "stop_router_not_running",
                    "exit_code": exit_code,
                    "oom_killed": oom_killed,
                    "request_count": request_count,
                })
                break
        if not after.get("router_health", {}).get("ok"):
            time.sleep(3)
            health2 = http_request(args.router_url, "GET", "/status/health", timeout=5)
            append_jsonl(case_dir / "logs" / "availability_checks.jsonl", {
                "label": f"post_failure_recheck_{len(body)}",
                "health": health2,
            })
            if not health2.get("ok"):
                break

    save_container_logs(args, "final")
    collect_snapshot(args, "final")
    print(json.dumps({"ready": ready, "request_count": request_count}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
