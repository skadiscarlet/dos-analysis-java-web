# Dynamic Validation Environment

Case: `dependencytrack__dependency-track-DTRACK-APP-STATIC-0001`

Status: environment started successfully, probe stopped before BOM upload.

## Deployment Source

- Deployment model: official Docker Compose quickstart.
- Compose source: `https://dependencytrack.org/docker-compose.yml`
- Local copy: `docker-compose.yml`
- Compose project name: `codex_dtrack_dos_0001`
- Started command:
  - `docker compose -p codex_dtrack_dos_0001 -f docker-compose.yml up -d`
- Cleanup command:
  - `docker compose -p codex_dtrack_dos_0001 -f docker-compose.yml down -v`

## Images

- `ghcr.io/dependencytrack/apiserver:5.0.2`
  - Digest: `ghcr.io/dependencytrack/apiserver@sha256:a485cc6e41f0897b5be2593aea6bc07d3b697cf0bb3a3f5d32aaeee7d9e2476c`
  - Image ID: `sha256:5e9cad17d1999df955110d71da9213f013a648151d0d16f1effc32d222601368`
- `ghcr.io/dependencytrack/frontend:5.0.2`
  - Digest: `ghcr.io/dependencytrack/frontend@sha256:f03fc26f2b65ae93eb62b4fb32bc30ec850b0eac14b033b602648d0ea0b7b4d5`
  - Image ID: `sha256:1ed00fba57116035735d7b445c76f3aea39d0b9a760c2b9c2f76c0cfd712b00c`
- `postgres:18-alpine`
  - Digest: `postgres@sha256:1b1689b20d16a014a3d195653381cf2caa75a41a92d93b255a9d6ea29fd353aa`
  - Image ID: `sha256:99d320a6265d9f49e7166e21518b664b9291dc203b9d63416c5875c8e3db7150`

## Ports And Limits

- Apiserver: `127.0.0.1:8080 -> 8080/tcp`
- Frontend: `127.0.0.1:8081 -> 8080/tcp`
- Postgres: compose-internal `5432/tcp`
- Apiserver memory limit from official compose: `2g` (`2147483648` bytes)
- Apiserver JVM options from image:
  - `-XX:+UseG1GC -XX:+UseStringDeduplication -XX:+UseCompactObjectHeaders -XX:MaxGCPauseMillis=250 -XX:MaxRAMPercentage=80.0`
- No application source edits were made.
- No non-default vulnerable feature was enabled.
- No compose configuration change was made.

## Readiness And Logs

- `GET /api/version` returned HTTP 200.
- Reported Dependency-Track version: `5.0.2`.
- Startup log shows normal database migration, seeding, Jetty startup, and healthy container state.
- Relevant evidence:
  - `logs/readiness.json`
  - `logs/apiserver_startup.log`
  - `logs/apiserver_pre_cleanup.log`
  - `logs/apiserver_container_inspect.json`
  - `logs/apiserver_pre_cleanup_inspect.json`
  - `logs/docker_compose_ps_running.txt`

## Download And Runtime Notes

- `ghcr.io/dependencytrack/apiserver:5.0.2` and `ghcr.io/dependencytrack/frontend:5.0.2` pulled successfully.
- `postgres:18-alpine` initially failed or timed out through Docker Hub / mirror access, then succeeded on retry. Logs:
  - `logs/docker_pull_postgres_daocloud.log`
  - `logs/docker_pull_postgres_retry.log`
- Docker printed `iptables v1.8.13 (nf_tables): Could not fetch rule set generation id: Permission denied (you must be root)` to the terminal during compose operations, but compose returned success and containers reached healthy/running state.

## Cleanup

- Cleanup executed with `docker compose down -v`.
- Compose removed the apiserver, frontend, postgres containers, the case network, and both compose volumes.
- Post-cleanup compose state is empty:
  - `logs/docker_compose_down.log`
  - `logs/docker_compose_ps_after_cleanup.txt`
