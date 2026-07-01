# Environment

## Target

- Case ID: `apache__hertzbeat-HERTZBEAT-DOS-0001`
- Target: `apache/hertzbeat`
- Local source snapshot: `/home/furina/new_tool/dos-analysis-web/frameworks/applications/apache__hertzbeat`
- Source commit observed locally: `138f1737e8ea2ffd0bf5629563a54310c1dbb460`
- Local Maven version string: `2.0-SNAPSHOT`

## Default Deployment Source

The repository README documents a one-command Docker deployment:

```bash
docker run -d -p 1157:1157 -p 1158:1158 --name hertzbeat apache/hertzbeat
```

The repository Docker Compose quickstarts pin `apache/hertzbeat:1.8.0`. This validation used that official image tag through a Docker mirror after Docker Hub direct pull failed with EOF.

Selected image:

```text
docker.m.daocloud.io/apache/hertzbeat:1.8.0
upstream tag: apache/hertzbeat:1.8.0
local image id: sha256:1ffeef8f0dce79c971943e19d2de1ef94f49d5079d0ceebe5292542d65eb63cb
mirror digest: docker.m.daocloud.io/apache/hertzbeat@sha256:75d48a62748fe42e4b2354e393ce567f51f7d46764b404763ec885cd23d74a0d
upstream digest recorded locally: apache/hertzbeat@sha256:5dc47b823e95b38d0b1b32e155b58ae1e5f811cbed025dfeebc1ae4414e89283
created: 2026-02-06T05:13:02.326845844Z
entrypoint: ./bin/entrypoint.sh
```

Evidence:

- `logs/image_inspect.json`
- `logs/startup_tail.log`
- `logs/container_inspect.json`

## Start Command

The target was started as a single isolated container:

```bash
docker run -d \
  --name hbdos0001-hertzbeat \
  --memory 768m \
  --memory-swap 768m \
  -p 2157:1157 \
  -p 2158:1158 \
  docker.m.daocloud.io/apache/hertzbeat:1.8.0
```

Harness-only changes:

- Host ports were mapped to `2157` and `2158` to avoid collisions with other local work.
- Docker memory and swap were capped at `768m` for safe reproduction.
- No HertzBeat source files or application config files were edited.
- No auth or feature flag was changed.

## Readiness

The service reached HTTP readiness on `http://127.0.0.1:2157/` with `HTTP 200`. Startup logs show default H2 storage and Tomcat on port `1157`.

Baseline resource snapshot after startup and before bulk probing:

```text
docker stats: 501.3MiB / 768MiB after smoke request
Java VmRSS: 565512 kB
Java VmHWM: 586764 kB
Threads: 106
GC heap: PSYoungGen 14270K/57344K, ParOldGen 93517K/122368K
```

The image includes `jcmd` and `jstat`, so Java process resource snapshots were collected through `docker exec`.

## Network And Auth

- Entry tested: `POST /api/push/prometheus/job/{job}/instance/{instance}`
- Attacker privilege: anonymous HTTP client
- Auth evidence: source config excludes `/api/push/**===*`; the running container accepted unauthenticated POST requests and logged automatic monitor creation.
- Default credentials were not needed for the attack path.

## Cleanup

The case container was removed:

```bash
docker rm -f hbdos0001-hertzbeat
```

`logs/container_status_after_cleanup.txt` shows no remaining container with the case name. The pulled image cache was left in Docker.
