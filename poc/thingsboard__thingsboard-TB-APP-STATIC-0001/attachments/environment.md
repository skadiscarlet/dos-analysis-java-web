# Environment

## Target

- Target: `thingsboard/thingsboard`
- Local source: `/home/furina/new_tool/dos-analysis-web/frameworks/applications/thingsboard__thingsboard`
- Source checkout observed during validation: `138f173-dirty`
- Static version in source `pom.xml`: `4.4.0-SNAPSHOT`
- Runtime image reported version: `ThingsBoard v4.3.1.3`

## Deployment

Used a case-local Docker Compose deployment in this directory:

- `thingsboard/tb-node:latest`
  - Image ID: `sha256:4dc3017d6bf3fa5686ff958f83cc3db098d996f1b69637b1cce862cb93f42413`
  - Repo digest: `thingsboard/tb-node@sha256:d4aee88fd6999eb54bee829fcd0699d4f42caaf26fc03c1447fbd434a5689da0`
- `postgres:16`
  - Image ID: `sha256:3ce79a779d23ce1c87202af4710c77b1ca882d4964ac680e4184956f2f945ca1`
  - Repo digest: `postgres@sha256:fe03a7605299a34ddf5e4f285dff78c3d7190a576b3c6b46f2fcff69f4bffd54`

Commands are captured in `start_commands.sh` and `docker-compose.yml`. The run used:

- `docker compose -p tb-dos-thingsboard-static-0001 up -d postgres`
- `docker compose -p tb-dos-thingsboard-static-0001 run --rm -e INSTALL_TB=true -e LOAD_DEMO=false ... tb-node`
- `docker compose -p tb-dos-thingsboard-static-0001 up -d tb-node`

## Configuration

Application behavior was left on default HTTP transport settings. The image config contains:

- `transport.http.max_payload_size`: `/api/v1/*/rpc/**=65536;/api/v1/**=52428800`
- `TB_SERVICE_TYPE`: `monolith`
- `TB_QUEUE_TYPE`: `in-memory`

Harness-specific settings:

- HTTP port mapped to `127.0.0.1:18080`.
- PostgreSQL was provided by the compose service.
- `LOAD_DEMO=false`.
- JVM was capped with `-Xms256m -Xmx384m`.
- Container memory limit was `768m`.
- Non-HTTP port mappings were removed after a host MQTT port collision; the validated entry used only HTTP.

## Evidence Files

- Startup and installation: `logs/startup.log`, `runtime/tb-logs/install.log`
- Image pull attempts and digests: `logs/docker_pull_attempts.log`
- Static source snippets: `evidence/static_code_snippets.txt`
- Runtime metrics: `logs/baseline_docker_stats.json`, `logs/post_probe_docker_stats.json`, `logs/final_docker_stats.json`
- Failure evidence: `logs/probe_results.jsonl`, `evidence/probe_summary.json`, `evidence/oom_excerpt.log`, `logs/final_availability_checks.log`
- Cleanup: `logs/cleanup.log`

## Cleanup

`docker compose down -v --remove-orphans` removed the case containers and network. A temporary `postgres:16` container removed the case-local PostgreSQL bind directory. The 638 MB heap dump was deleted after recording its creation in `evidence/oom_excerpt.log` and preserving GC/application logs. Remaining files are logs and evidence under this case directory only.
