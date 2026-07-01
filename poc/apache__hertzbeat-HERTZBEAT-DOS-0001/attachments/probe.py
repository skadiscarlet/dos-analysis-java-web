#!/usr/bin/env python3
import argparse
import concurrent.futures
import csv
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def run_cmd(args, timeout=8):
    try:
        proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "timeout"


def http_request(url, method="GET", body=None, content_type=None, timeout=5):
    headers = {}
    data = None
    if body is not None:
        data = body.encode("utf-8")
        headers["Content-Type"] = content_type or "text/plain"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read(512).decode("utf-8", errors="replace")
            return resp.status, time.monotonic() - started, payload, None
    except urllib.error.HTTPError as exc:
        payload = exc.read(512).decode("utf-8", errors="replace")
        return exc.code, time.monotonic() - started, payload, None
    except Exception as exc:  # noqa: BLE001 - evidence collection should record transport failures.
        return 0, time.monotonic() - started, "", repr(exc)


def docker_stats(container):
    rc, out, err = run_cmd(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", container],
        timeout=10,
    )
    if rc != 0:
        return {"error": err or out}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out}


def container_state(container):
    rc, out, err = run_cmd(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .State}}",
            container,
        ],
        timeout=8,
    )
    if rc != 0:
        return {"error": err or out}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out}


def java_pid(container):
    rc, out, _ = run_cmd(
        ["docker", "exec", container, "sh", "-lc", "pgrep -f HertzBeatApplication | head -n1"],
        timeout=8,
    )
    if rc == 0 and out.strip():
        return out.strip()
    return None


def java_status(container, pid):
    if not pid:
        return {}
    script = (
        f"cat /proc/{pid}/status | egrep 'VmRSS|VmHWM|Threads' || true; "
        f"jcmd {pid} GC.heap_info 2>/dev/null | sed -n '1,40p' || true"
    )
    rc, out, err = run_cmd(["docker", "exec", container, "sh", "-lc", script], timeout=12)
    data = {"rc": rc}
    if err:
        data["stderr"] = err
    for line in out.splitlines():
        if line.startswith("VmRSS:"):
            data["vmrss_kb"] = int(re.findall(r"\d+", line)[0])
        elif line.startswith("VmHWM:"):
            data["vmhwm_kb"] = int(re.findall(r"\d+", line)[0])
        elif line.startswith("Threads:"):
            data["threads"] = int(re.findall(r"\d+", line)[0])
        elif "PSYoungGen" in line:
            match = re.search(r"total (\d+)K, used (\d+)K", line)
            if match:
                data["young_total_kb"] = int(match.group(1))
                data["young_used_kb"] = int(match.group(2))
        elif "ParOldGen" in line:
            match = re.search(r"total (\d+)K, used (\d+)K", line)
            if match:
                data["old_total_kb"] = int(match.group(1))
                data["old_used_kb"] = int(match.group(2))
        elif "Metaspace" in line and "used" in line:
            match = re.search(r"used (\d+)K, committed (\d+)K", line)
            if match:
                data["metaspace_used_kb"] = int(match.group(1))
                data["metaspace_committed_kb"] = int(match.group(2))
    return data


def push_once(base_url: str, idx: int, timeout: float) -> dict:
    job = f"dosjob{idx:06d}"
    instance = f"inst{idx:06d}"
    url = f"{base_url}/api/push/prometheus/job/{job}/instance/{instance}"
    status, latency, payload, error = http_request(
        url,
        method="POST",
        body="sample_metric 1\n",
        content_type="text/plain",
        timeout=timeout,
    )
    return {
        "index": idx,
        "url": url,
        "status": status,
        "latency": latency,
        "payload": payload,
        "error": error,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:2157")
    parser.add_argument("--container", default="hbdos0001-hertzbeat")
    parser.add_argument("--case-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--count", type=int, default=1500)
    parser.add_argument("--start-index", type=int, default=2)
    parser.add_argument("--sample-every", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    logs_dir = case_dir / "logs"
    evidence_dir = case_dir / "evidence"
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    observations_path = evidence_dir / "probe_observations.csv"
    samples_path = logs_dir / "probe_response_samples.txt"
    summary_path = evidence_dir / "probe_summary.json"

    pid = java_pid(args.container)
    total_sent = 0
    status_counts = {}
    first_error = None
    unavailable_streak = 0
    stop_reason = "request_cap_reached"
    started = time.time()

    fields = [
        "timestamp",
        "index",
        "http_status",
        "latency_ms",
        "transport_error",
        "availability_status",
        "availability_latency_ms",
        "availability_error",
        "docker_mem_usage",
        "docker_mem_perc",
        "docker_pids",
        "java_vmrss_kb",
        "java_vmhwm_kb",
        "java_threads",
        "young_used_kb",
        "young_total_kb",
        "old_used_kb",
        "old_total_kb",
        "metaspace_used_kb",
        "container_status",
        "container_oom_killed",
        "container_exit_code",
    ]

    with observations_path.open("w", newline="", encoding="utf-8") as csv_file, samples_path.open(
        "w", encoding="utf-8"
    ) as samples:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        idx = args.start_index
        end_index = args.start_index + args.count
        while idx < end_index:
            batch = list(range(idx, min(end_index, idx + max(1, args.concurrency))))
            if args.concurrency <= 1:
                results = [push_once(args.base_url, batch[0], args.timeout)]
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                    futures = [executor.submit(push_once, args.base_url, item, args.timeout) for item in batch]
                    results = [future.result() for future in concurrent.futures.as_completed(futures)]
                results.sort(key=lambda item: item["index"])

            total_sent += len(results)
            for result in results:
                status_counts[str(result["status"])] = status_counts.get(str(result["status"]), 0) + 1
                if result["error"] and first_error is None:
                    first_error = {"index": result["index"], "error": result["error"]}

            idx = batch[-1]
            representative = results[-1]
            status = int(representative["status"])
            latency = float(representative["latency"])
            payload = str(representative["payload"])
            error = representative["error"]
            url = str(representative["url"])
            batch_had_error = any(item["error"] or int(item["status"]) == 0 or int(item["status"]) >= 500 for item in results)

            should_sample = (
                total_sent <= len(results)
                or total_sent % args.sample_every == 0
                or batch_had_error
            )
            if should_sample:
                avail_status, avail_latency, _, avail_error = http_request(
                    f"{args.base_url}/", timeout=args.timeout
                )
                stats = docker_stats(args.container)
                state = container_state(args.container)
                pid = pid or java_pid(args.container)
                jstat = java_status(args.container, pid)
                row = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "index": idx,
                    "http_status": status,
                    "latency_ms": round(latency * 1000, 3),
                    "transport_error": error or "",
                    "availability_status": avail_status,
                    "availability_latency_ms": round(avail_latency * 1000, 3),
                    "availability_error": avail_error or "",
                    "docker_mem_usage": stats.get("MemUsage", ""),
                    "docker_mem_perc": stats.get("MemPerc", ""),
                    "docker_pids": stats.get("PIDs", ""),
                    "java_vmrss_kb": jstat.get("vmrss_kb", ""),
                    "java_vmhwm_kb": jstat.get("vmhwm_kb", ""),
                    "java_threads": jstat.get("threads", ""),
                    "young_used_kb": jstat.get("young_used_kb", ""),
                    "young_total_kb": jstat.get("young_total_kb", ""),
                    "old_used_kb": jstat.get("old_used_kb", ""),
                    "old_total_kb": jstat.get("old_total_kb", ""),
                    "metaspace_used_kb": jstat.get("metaspace_used_kb", ""),
                    "container_status": state.get("Status", ""),
                    "container_oom_killed": state.get("OOMKilled", ""),
                    "container_exit_code": state.get("ExitCode", ""),
                }
                writer.writerow(row)
                csv_file.flush()
                samples.write(
                    json.dumps(
                        {
                            "index": idx,
                            "batch_size": len(results),
                            "batch_status_counts": {
                                str(code): sum(1 for item in results if str(item["status"]) == str(code))
                                for code in sorted({item["status"] for item in results})
                            },
                            "url": url,
                            "status": status,
                            "latency_ms": round(latency * 1000, 3),
                            "payload_prefix": payload[:240],
                            "error": error,
                            "availability_status": avail_status,
                            "availability_error": avail_error,
                            "docker_stats": stats,
                            "container_state": state,
                            "java_status": jstat,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                samples.flush()

                if state.get("OOMKilled") is True:
                    stop_reason = "container_oom_killed"
                    break
                if state.get("Status") not in ("running", None, ""):
                    stop_reason = f"container_state_{state.get('Status')}"
                    break
                if avail_status == 0 or avail_status >= 500:
                    unavailable_streak += 1
                else:
                    unavailable_streak = 0
                if unavailable_streak >= 3:
                    stop_reason = "sustained_unavailable"
                    break

            if args.sleep:
                time.sleep(args.sleep)
            idx += 1

    final_state = container_state(args.container)
    final_pid = java_pid(args.container)
    final_java = java_status(args.container, final_pid)
    final_stats = docker_stats(args.container)
    summary = {
        "base_url": args.base_url,
        "container": args.container,
        "total_sent": total_sent,
        "start_index": args.start_index,
        "request_cap": args.count,
        "concurrency": args.concurrency,
        "duration_seconds": round(time.time() - started, 3),
        "status_counts": status_counts,
        "first_error": first_error,
        "stop_reason": stop_reason,
        "final_container_state": final_state,
        "final_docker_stats": final_stats,
        "final_java_status": final_java,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
