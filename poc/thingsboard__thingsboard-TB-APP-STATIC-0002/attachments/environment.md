# Environment

- Case: `thingsboard__thingsboard-TB-APP-STATIC-0002`
- Host-only target URL: `http://127.0.0.1:19090`
- Deployment source: official ThingsBoard single Docker image documented under `msa/tb/README.md`.
- Image: `thingsboard/tb-postgres:latest`
- Repo digest: `thingsboard/tb-postgres@sha256:2d17e4e36edcc1652592d48a3ab25dc7c9d13442b9f8283bc0594eb7b290b65b`
- Image id: `sha256:08decb7b3671c3857c75ba88eac1a27d9c97ed651a073a6c94123454ccd37baf`
- Runtime version observed in startup log: ThingsBoard `v4.2.1.1`
- Java observed in container: OpenJDK 17.0.17
- Container name used: `tb-dos-thingsboard-static-0002`

## Commands

The recorded reproduction command is in `start_commands.sh`. The successful run used:

```bash
docker run -d --name tb-dos-thingsboard-static-0002 \
  --memory=4096m --memory-swap=4096m \
  -e JAVA_OPTS='-Xms512m -Xmx1536m -XX:+ExitOnOutOfMemoryError' \
  -p 127.0.0.1:19090:9090 \
  -p 127.0.0.1:11883:1883 \
  -p 127.0.0.1:15683:5683/udp \
  -p 127.0.0.1:15685:5685/udp \
  -p 127.0.0.1:15686:5686/udp \
  -v "$CASE_DIR/data:/data" \
  -v "$CASE_DIR/container-logs:/var/log/thingsboard" \
  thingsboard/tb-postgres:latest
```

## Configuration Changes

No ThingsBoard application source or `server.http.max_payload_size` configuration was changed.

Harness-only limits were added to keep the validation bounded:

- Docker memory limit: `4096m`
- Docker memory swap limit: `4096m`
- JVM heap: `-Xms512m -Xmx1536m`
- JVM OOM behavior: `-XX:+ExitOnOutOfMemoryError`
- Host ports were mapped to high localhost-only ports to avoid collisions.

These limits affect the exact OOM threshold. They do not enable the vulnerable endpoint, change auth, or disable the default `/api/**=16777216` payload filter.

## Startup Notes

- First attempt with `--memory=1800m` OOM-killed during startup; this was a harness sizing failure, not counted as candidate evidence. See `logs/startup_exit_full.log`.
- Second attempt reused the half-initialized data directory and failed on duplicate bootstrap data. See `logs/startup_second_exit_full.log`.
- Third clean attempt with the limits above reached readiness. See `logs/readiness_third.log` and `logs/startup_third_ready.log`.

## Evidence Files

- `logs/image_inspect.json`
- `logs/container_processes_ready.txt`
- `logs/docker_stats_ready.txt`
- `logs/docker_stats_probe_baseline.txt`
- `logs/container_state_after_oom.txt`
- `container-logs/gc.log`
- `container-logs/thingsboard.2026-06-29.0.log.gz`
- `logs/container_logs_full_after_oom.log.gz`
- `evidence/payload_filter_excerpts.txt`
- `evidence/oom_excerpts.txt`
- `evidence/http_results.csv`
- `evidence/probe_summary.json`

## Cleanup

The case container was removed and the disposable data directory was cleared. See `logs/cleanup.log`.
