# Environment

## Case

- `case_id`: `openzipkin__zipkin-ZIPKIN-APP-STATIC-0001`
- `target`: `openzipkin/zipkin`
- `finding_id`: `ZIPKIN-APP-STATIC-0001`
- `recorded_at`: `2026-06-29 21:53:38 CST`
- Allowed write scope: this case directory only.

## Intended Default Deployment

The intended deployment model was the documented Zipkin Docker quickstart:

- Image family: `openzipkin/zipkin-slim`
- Mirrored image family documented by the project: `ghcr.io/openzipkin/zipkin-slim`
- Default storage: in-memory (`STORAGE_TYPE=mem`)
- Default HTTP API/UI port: `9411`
- Default HTTP collector: enabled, including anonymous `POST /api/v2/spans`
- Documented default heap for `openzipkin/zipkin-slim`: `32m`

No application source files were edited. No Zipkin configuration changes were applied. No `JAVA_OPTS` override was used.

## Image Pull Attempts

Pull logs already present under `logs/` were used for this record:

1. `logs/docker_pull.log`
   - Command attempted: `docker pull ghcr.io/openzipkin/zipkin-slim:latest`
   - Log only shows layer pull/waiting state.
   - No digest or successful completion was recorded.
2. `logs/docker_pull_dockerhub.log`
   - Command attempted: `docker pull openzipkin/zipkin-slim:latest`
   - Log only shows layer pull/waiting state.
   - No digest or successful completion was recorded.
3. `logs/docker_pull_daocloud.log`
   - Command attempted: `docker pull docker.m.daocloud.io/openzipkin/zipkin-slim:latest`
   - The accelerator pull completed.
   - Recorded digest: `sha256:fc29b9862c14f4fc241cf0259c585e1cfd4e9b18f01ad36d86adaabb7d01815c`
   - Recorded image reference: `docker.m.daocloud.io/openzipkin/zipkin-slim:latest`

The Daocloud image was used only as a Docker Hub accelerator for the same upstream image/tag. The service was not started after the pull completed because the user explicitly requested no further pulls, no probe rerun, and only completion of missing case files.

## Runtime State

- Container name reserved for the case: `dosval-openzipkin-zipkin-static-0001`
- Port mapping planned: `127.0.0.1:19411 -> 9411`
- Container memory limit planned: `384m`
- Application heap planned: image default (`openzipkin/zipkin-slim` documented default max heap `32m`)
- Service start: not executed
- Readiness check: not executed
- POST probe: not executed
- Plain/gzip request evidence: none
- Observed heap/RSS/latency: none
- Observed Armeria or application rejection: none
- Confirmed failure signal: none

## Cleanup

No case container was started, so there was no case container to remove. A Docker status check for `dosval-openzipkin-zipkin-static-0001` returned no matching container.
