#!/usr/bin/env python3
import base64
import datetime as dt
import http.client
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import requests


CASE_DIR = Path(__file__).resolve().parent
LOG_DIR = CASE_DIR / "logs"
EVIDENCE_DIR = CASE_DIR / "evidence"
LOG_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("DTRACK_BASE_URL", "http://127.0.0.1:8080")
HOST = os.environ.get("DTRACK_HOST", "127.0.0.1")
PORT = int(os.environ.get("DTRACK_PORT", "8080"))
PROJECT_NAME = os.environ.get("DTRACK_TEST_PROJECT", "codex-dos-bom-heap-0001")
TEAM_NAME = os.environ.get("DTRACK_TEST_TEAM", "codex-dos-bom-upload-team-0001")
ADMIN_PASSWORD = os.environ.get("DTRACK_ADMIN_PASSWORD", "Codex_DTrack_Bootstrap_0001!")
COMPOSE_PROJECT = os.environ.get("DTRACK_COMPOSE_PROJECT", "codex_dtrack_dos_0001")
APISERVER_CONTAINER = os.environ.get("DTRACK_APISERVER_CONTAINER", f"{COMPOSE_PROJECT}-apiserver-1")

REQUEST_TIMEOUT = int(os.environ.get("DTRACK_REQUEST_TIMEOUT", "300"))
PUT_DECODED_MIB = [int(x) for x in os.environ.get("DTRACK_PUT_DECODED_MIB", "1,14").split(",") if x]
POST_PART_MIB = [int(x) for x in os.environ.get("DTRACK_POST_PART_MIB", "1,4,16,64,128").split(",") if x]


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(cmd, timeout=30):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get_json(response):
    if not response.text:
        return None
    try:
        return response.json()
    except Exception:
        return response.text


def wait_ready(timeout=300):
    deadline = time.time() + timeout
    attempts = []
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/api/version", timeout=5)
            attempts.append({"ts": now_iso(), "status": r.status_code, "body": r.text[:200]})
            if r.status_code == 200:
                write_json(LOG_DIR / "readiness.json", {"ready": True, "attempts": attempts})
                return r.text.strip()
        except Exception as exc:
            attempts.append({"ts": now_iso(), "error": repr(exc)})
        time.sleep(3)
    write_json(LOG_DIR / "readiness.json", {"ready": False, "attempts": attempts})
    raise RuntimeError("Dependency-Track API did not become ready")


def login_admin():
    login_url = f"{BASE_URL}/api/v1/user/login"
    r = requests.post(login_url, data={"username": "admin", "password": "admin"}, timeout=30)
    events = [{"step": "login_default_admin", "status": r.status_code, "body": r.text[:200]}]
    if r.status_code == 200:
        write_json(LOG_DIR / "admin_bootstrap_login.json", {"events": events, "password_changed": False})
        return r.text.strip(), False
    if r.status_code in (401, 403) and "FORCE_PASSWORD_CHANGE" in r.text:
        cr = requests.post(
            f"{BASE_URL}/api/v1/user/forceChangePassword",
            data={
                "username": "admin",
                "password": "admin",
                "newPassword": ADMIN_PASSWORD,
                "confirmPassword": ADMIN_PASSWORD,
            },
            timeout=30,
        )
        events.append({"step": "force_change_password", "status": cr.status_code, "body": cr.text[:200]})
        if cr.status_code not in (200, 204):
            write_json(LOG_DIR / "admin_bootstrap_login.json", {"events": events, "password_changed": False})
            raise RuntimeError(f"forceChangePassword failed: {cr.status_code} {cr.text[:200]}")
        r2 = requests.post(login_url, data={"username": "admin", "password": ADMIN_PASSWORD}, timeout=30)
        events.append({"step": "login_changed_admin", "status": r2.status_code, "body": r2.text[:200]})
        if r2.status_code != 200:
            write_json(LOG_DIR / "admin_bootstrap_login.json", {"events": events, "password_changed": True})
            raise RuntimeError(f"admin login after password change failed: {r2.status_code} {r2.text[:200]}")
        write_json(LOG_DIR / "admin_bootstrap_login.json", {"events": events, "password_changed": True})
        return r2.text.strip(), True
    if r.status_code in (401, 403):
        r2 = requests.post(login_url, data={"username": "admin", "password": ADMIN_PASSWORD}, timeout=30)
        events.append({"step": "login_changed_admin_existing_run", "status": r2.status_code, "body": r2.text[:200]})
        if r2.status_code == 200:
            write_json(LOG_DIR / "admin_bootstrap_login.json", {"events": events, "password_changed": True})
            return r2.text.strip(), True
    write_json(LOG_DIR / "admin_bootstrap_login.json", {"events": events, "password_changed": False})
    raise RuntimeError(f"admin login failed: {r.status_code} {r.text[:200]}")


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def api_key_headers(key):
    return {"X-Api-Key": key, "Accept": "application/json"}


def bootstrap_low_privilege(token):
    headers = auth_headers(token) | {"Content-Type": "application/json"}
    events = []

    r = requests.put(f"{BASE_URL}/api/v1/team", headers=headers, json={"name": TEAM_NAME}, timeout=30)
    events.append({"step": "create_team", "status": r.status_code, "body": r.text[:500]})
    if r.status_code not in (200, 201, 409):
        raise RuntimeError(f"create team failed: {r.status_code} {r.text[:200]}")
    if r.status_code == 409:
        teams = requests.get(f"{BASE_URL}/api/v1/team", headers=auth_headers(token), timeout=30)
        teams.raise_for_status()
        team = next(t for t in teams.json() if t.get("name") == TEAM_NAME)
    else:
        team = r.json()
    team_uuid = team["uuid"]

    permissions_payload = {"team": team_uuid, "permissions": ["BOM_UPLOAD"]}
    r = requests.put(f"{BASE_URL}/api/v1/permission/team", headers=headers, json=permissions_payload, timeout=30)
    events.append({"step": "set_team_permissions", "status": r.status_code, "body": r.text[:500]})
    if r.status_code not in (200, 304):
        raise RuntimeError(f"set team permissions failed: {r.status_code} {r.text[:200]}")

    r = requests.put(f"{BASE_URL}/api/v1/team/{team_uuid}/key", headers=auth_headers(token), timeout=30)
    events.append({"step": "generate_api_key", "status": r.status_code, "body": redact_key_body(r.text)})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"generate API key failed: {r.status_code} {r.text[:200]}")
    api_key_doc = r.json()
    api_key = api_key_doc.get("key") or api_key_doc.get("apiKey")
    public_id = api_key_doc.get("publicId")
    if not api_key:
        raise RuntimeError(f"API key response did not contain key: {api_key_doc}")

    project_payload = {
        "name": PROJECT_NAME,
        "version": "1.0",
        "classifier": "APPLICATION",
        "accessTeams": [{"uuid": team_uuid}],
    }
    r = requests.put(f"{BASE_URL}/api/v1/project", headers=headers, json=project_payload, timeout=30)
    events.append({"step": "create_project", "status": r.status_code, "body": r.text[:500]})
    if r.status_code not in (200, 201, 409):
        raise RuntimeError(f"create project failed: {r.status_code} {r.text[:200]}")
    if r.status_code == 409:
        lookup = requests.get(
            f"{BASE_URL}/api/v1/project/lookup",
            headers=auth_headers(token),
            params={"name": PROJECT_NAME, "version": "1.0"},
            timeout=30,
        )
        lookup.raise_for_status()
        project = lookup.json()
    else:
        project = r.json()
    project_uuid = project["uuid"]

    r = requests.get(f"{BASE_URL}/api/v1/team/self", headers=api_key_headers(api_key), timeout=30)
    events.append({"step": "low_privilege_team_self", "status": r.status_code, "body": r.text[:500]})
    if r.status_code != 200:
        raise RuntimeError(f"low privilege API key verification failed: {r.status_code} {r.text[:200]}")

    bootstrap = {
        "team_name": TEAM_NAME,
        "team_uuid": team_uuid,
        "api_key_public_id": public_id,
        "api_key_secret_recorded": False,
        "project_name": PROJECT_NAME,
        "project_uuid": project_uuid,
        "events": events,
    }
    write_json(EVIDENCE_DIR / "bootstrap_summary.json", bootstrap)
    return api_key, project_uuid, bootstrap


def redact_key_body(text):
    try:
        doc = json.loads(text)
        if "key" in doc:
            doc["key"] = "<redacted>"
        if "apiKey" in doc:
            doc["apiKey"] = "<redacted>"
        return json.dumps(doc, sort_keys=True)
    except Exception:
        return re.sub(r'"key"\\s*:\\s*"[^"]+"', '"key":"<redacted>"', text)[:500]


def docker_inspect_state():
    proc = run([
        "docker",
        "inspect",
        APISERVER_CONTAINER,
        "--format",
        "{{json .State}}",
    ], timeout=15)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    try:
        state = json.loads(proc.stdout)
    except Exception:
        return {"raw": proc.stdout.strip()}
    return {
        "status": state.get("Status"),
        "running": state.get("Running"),
        "restart_count": state.get("RestartCount"),
        "oom_killed": state.get("OOMKilled"),
        "exit_code": state.get("ExitCode"),
        "health": (state.get("Health") or {}).get("Status"),
    }


def docker_stats_once():
    proc = run([
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
        APISERVER_CONTAINER,
    ], timeout=20)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    try:
        doc = json.loads(proc.stdout)
    except Exception:
        return {"raw": proc.stdout.strip()}
    doc["mem_usage_mib"] = parse_mem_mib(doc.get("MemUsage", ""))
    return doc


def parse_mem_mib(value):
    match = re.match(r"\\s*([0-9.]+)\\s*([KMGT]i?B|B)", value)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    scale = {
        "B": 1 / 1024 / 1024,
        "KiB": 1 / 1024,
        "KB": 1 / 1024,
        "MiB": 1,
        "MB": 1,
        "GiB": 1024,
        "GB": 1024,
        "TiB": 1024 * 1024,
        "TB": 1024 * 1024,
    }.get(unit, 1)
    return amount * scale


def proc_status_once():
    proc = run(["docker", "exec", APISERVER_CONTAINER, "cat", "/proc/1/status"], timeout=15)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    out = {}
    for line in proc.stdout.splitlines():
        if line.startswith(("VmRSS:", "VmHWM:", "Threads:", "VmSize:")):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                out[parts[0].rstrip(":")] = int(parts[1])
            else:
                out[parts[0].rstrip(":")] = " ".join(parts[1:])
    return out


def availability_once():
    started = time.time()
    try:
        r = requests.get(f"{BASE_URL}/api/version", timeout=5)
        return {"status": r.status_code, "latency_s": round(time.time() - started, 3), "body": r.text[:80]}
    except Exception as exc:
        return {"error": repr(exc), "latency_s": round(time.time() - started, 3)}


def snapshot(label):
    return {
        "ts": now_iso(),
        "label": label,
        "container_state": docker_inspect_state(),
        "docker_stats": docker_stats_once(),
        "proc_status": proc_status_once(),
        "availability": availability_once(),
    }


class Sampler:
    def __init__(self, label, interval=0.75):
        self.label = label
        self.interval = interval
        self.samples = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                self.samples.append(snapshot(self.label))
            except Exception as exc:
                self.samples.append({"ts": now_iso(), "label": self.label, "error": repr(exc)})
            self._stop.wait(self.interval)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        self._thread.join(timeout=5)
        try:
            self.samples.append(snapshot(self.label + "_after"))
        except Exception as exc:
            self.samples.append({"ts": now_iso(), "label": self.label + "_after", "error": repr(exc)})


def iter_padding_payload(total_bytes):
    prefix = b'{"padding":"'
    suffix = b'"}'
    if total_bytes < len(prefix) + len(suffix):
        yield b"{}"
        return
    yield prefix
    remaining = total_bytes - len(prefix) - len(suffix)
    chunk = b"A" * (1024 * 1024)
    while remaining > 0:
        n = min(remaining, len(chunk))
        yield chunk[:n]
        remaining -= n
    yield suffix


def send_put_bom(api_key, project_uuid, decoded_mib):
    decoded_bytes = decoded_mib * 1024 * 1024
    payload = b"".join(iter_padding_payload(decoded_bytes))
    bom_b64 = base64.b64encode(payload).decode("ascii")
    body = json.dumps({"project": project_uuid, "bom": bom_b64}).encode("utf-8")
    started = time.time()
    try:
        r = requests.put(
            f"{BASE_URL}/api/v1/bom",
            headers=api_key_headers(api_key) | {"Content-Type": "application/json"},
            data=body,
            timeout=REQUEST_TIMEOUT,
        )
        return {
            "method": "PUT",
            "path": "/api/v1/bom",
            "decoded_mib": decoded_mib,
            "request_bytes": len(body),
            "status": r.status_code,
            "latency_s": round(time.time() - started, 3),
            "response_body_prefix": r.text[:500],
        }
    except Exception as exc:
        return {
            "method": "PUT",
            "path": "/api/v1/bom",
            "decoded_mib": decoded_mib,
            "request_bytes": len(body),
            "status": None,
            "latency_s": round(time.time() - started, 3),
            "error": repr(exc),
        }


def send_multipart_bom(api_key, project_uuid, payload_mib=None, valid=False):
    boundary = "----codex-dtrack-bom-boundary"
    if valid:
        payload = (
            b'{"bomFormat":"CycloneDX","specVersion":"1.6","version":1,'
            b'"metadata":{"component":{"type":"application","name":"codex-smoke"}}}'
        )
        payload_size = len(payload)
        payload_iter = [payload]
        label_size = "valid-smoke"
    else:
        payload_size = int(payload_mib) * 1024 * 1024
        payload_iter = iter_padding_payload(payload_size)
        label_size = f"{payload_mib}MiB"

    pre = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="project"\r\n\r\n'
        f"{project_uuid}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="bom"; filename="bom.json"\r\n'
        f"Content-Type: application/json\r\n\r\n"
    ).encode("utf-8")
    post = f"\r\n--{boundary}--\r\n".encode("utf-8")
    content_length = len(pre) + payload_size + len(post)

    started = time.time()
    status = None
    response_prefix = ""
    error = None
    try:
        conn = http.client.HTTPConnection(HOST, PORT, timeout=REQUEST_TIMEOUT)
        conn.putrequest("POST", "/api/v1/bom")
        conn.putheader("X-Api-Key", api_key)
        conn.putheader("Accept", "application/json")
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(content_length))
        conn.endheaders()
        conn.send(pre)
        bytes_sent = len(pre)
        for chunk in payload_iter:
            conn.send(chunk)
            bytes_sent += len(chunk)
            if not valid and payload_size >= 64 * 1024 * 1024:
                time.sleep(0.01)
        conn.send(post)
        bytes_sent += len(post)
        resp = conn.getresponse()
        status = resp.status
        response_prefix = resp.read(512).decode("utf-8", errors="replace")
        conn.close()
    except Exception as exc:
        bytes_sent = None
        error = repr(exc)

    result = {
        "method": "POST",
        "path": "/api/v1/bom",
        "payload_label": label_size,
        "payload_mib": payload_mib if not valid else round(payload_size / 1024 / 1024, 6),
        "content_length": content_length,
        "bytes_sent": bytes_sent,
        "status": status,
        "latency_s": round(time.time() - started, 3),
        "response_body_prefix": response_prefix,
    }
    if error:
        result["error"] = error
    return result


def detect_failure(log_text, before_state, after_state, availability_samples):
    if "OutOfMemoryError" in log_text or "Java heap space" in log_text:
        return "OutOfMemoryError"
    if "GC overhead limit exceeded" in log_text:
        return "GC overhead"
    if after_state.get("oom_killed"):
        return "OOMKilled"
    before_restarts = before_state.get("restart_count") or 0
    after_restarts = after_state.get("restart_count") or 0
    if after_restarts > before_restarts:
        return "restart"
    failed = 0
    for sample in availability_samples[-6:]:
        status = sample.get("availability", {}).get("status")
        if status is None or status >= 500:
            failed += 1
    if len(availability_samples[-6:]) >= 6 and failed == 6:
        return "5xx_sustained"
    return "none"


def docker_logs_tail():
    proc = run(["docker", "logs", "--tail", "400", APISERVER_CONTAINER], timeout=30)
    return (proc.stdout or "") + (proc.stderr or "")


def main():
    start_ts = time.time()
    version = wait_ready()
    admin_token, password_changed = login_admin()
    api_key, project_uuid, bootstrap = bootstrap_low_privilege(admin_token)

    results = {
        "started_at": now_iso(),
        "version": version,
        "password_changed": password_changed,
        "bootstrap_summary": bootstrap,
        "baseline": snapshot("baseline"),
        "requests": [],
        "snapshots": [],
    }
    before_state = docker_inspect_state()

    probe_sequence = [("POST_SMOKE", None)]
    probe_sequence.extend(("PUT", mib) for mib in PUT_DECODED_MIB)
    probe_sequence.extend(("POST", mib) for mib in POST_PART_MIB)

    for kind, size_mib in probe_sequence:
        if time.time() - start_ts > 1800:
            results["stop_reason"] = "time_cap_seconds"
            break
        label = f"{kind}_{size_mib if size_mib is not None else 'valid_smoke'}"
        with Sampler(label) as sampler:
            if kind == "POST_SMOKE":
                req = send_multipart_bom(api_key, project_uuid, valid=True)
            elif kind == "PUT":
                req = send_put_bom(api_key, project_uuid, size_mib)
            else:
                req = send_multipart_bom(api_key, project_uuid, payload_mib=size_mib, valid=False)
        req["samples"] = sampler.samples
        results["requests"].append(req)
        results["snapshots"].append(snapshot(f"after_{label}"))

        state_after_req = docker_inspect_state()
        log_tail = docker_logs_tail()
        failure_signal = detect_failure(log_tail, before_state, state_after_req, sampler.samples)
        if failure_signal != "none":
            results["stop_reason"] = f"failure_signal:{failure_signal}"
            break
        if req.get("status") == 413:
            results["stop_reason"] = "HTTP 413 body-size rejection"
            break

    final_logs = docker_logs_tail()
    (LOG_DIR / "apiserver_tail_after_probe.log").write_text(final_logs, encoding="utf-8", errors="replace")
    final_snapshot = snapshot("final")
    results["final"] = final_snapshot
    results["finished_at"] = now_iso()
    results["duration_seconds"] = round(time.time() - start_ts, 3)
    results["failure_signal"] = detect_failure(
        final_logs,
        before_state,
        final_snapshot.get("container_state", {}),
        [s for req in results["requests"] for s in req.get("samples", [])],
    )
    write_json(EVIDENCE_DIR / "probe_observations.json", results)
    print(json.dumps({
        "version": version,
        "project_uuid": project_uuid,
        "request_count": len(results["requests"]),
        "failure_signal": results["failure_signal"],
        "duration_seconds": results["duration_seconds"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
