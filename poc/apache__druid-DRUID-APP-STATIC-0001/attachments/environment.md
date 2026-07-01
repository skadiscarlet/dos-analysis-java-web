# Environment

## Target

- Case: `apache__druid-DRUID-APP-STATIC-0001`
- Target source: `/home/furina/new_tool/dos-analysis-web/frameworks/applications/apache__druid`
- Source tree version: `38.0.0-SNAPSHOT` from root `pom.xml`
- Validated release image: `apache/druid:37.0.0`
- Image digest: `apache/druid@sha256:0116fb802786649fc3635d6d4ab5be4da8abee3edafbe95c7f358a564d4c82e8`

The source tree's `distribution/docker/docker-compose.yml` references `apache/druid:38.0.0`, but Docker Hub returned `no such manifest` for that tag during this run. The nearest checked official release tag, `apache/druid:37.0.0`, was used for dynamic validation. The 38.0.0 manifest check is saved at `evidence/apache_druid_38_manifest_check.txt`.

## Deployment Model

The deployment is based on the official Druid Docker quickstart compose files in:

- `/home/furina/new_tool/dos-analysis-web/frameworks/applications/apache__druid/distribution/docker/docker-compose.yml`
- `/home/furina/new_tool/dos-analysis-web/frameworks/applications/apache__druid/distribution/docker/environment`

The case-local `docker-compose.yml` preserves the Druid service roles and internal ports. Only isolation edits were made:

- Container names were prefixed with `druiddos_apache_druid_`.
- Host ports were remapped to loopback to avoid conflicts:
  - Router: `127.0.0.1:19088 -> 8888`
  - Broker: `127.0.0.1:19082 -> 8082`
  - Coordinator: `127.0.0.1:19081 -> 8081`
  - Historical: `127.0.0.1:19083 -> 8083`
  - MiddleManager: `127.0.0.1:19091 -> 8091`, `127.0.0.1:19100-19105 -> 8100-8105`
  - PostgreSQL: `127.0.0.1:15432 -> 5432`
  - ZooKeeper: `127.0.0.1:12181 -> 2181`

No Druid semantic configuration was changed. The `environment` file leaves `DRUID_XMX`, `DRUID_XMS`, `DRUID_MAXNEWSIZE`, `DRUID_NEWSIZE`, and `DRUID_MAXDIRECTMEMORYSIZE` commented, preserving Docker image defaults. The quickstart `DRUID_SINGLE_NODE_CONF=micro-quickstart` setting was retained.

## Commands

```bash
cd /home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001
docker compose -p druiddos_apache_druid pull
docker compose -p druiddos_apache_druid up -d
curl -i http://127.0.0.1:19088/status/health
curl -i http://127.0.0.1:19082/status/health
./probe.py --max-size 134217728 --concurrency 1 --timeout 240
docker compose -p druiddos_apache_druid down -v
```

## Readiness

Before probing, both endpoints returned HTTP 200:

- Router `GET /status/health` on `127.0.0.1:19088`
- Broker `GET /status/health` on `127.0.0.1:19082`

Startup logs were saved in `logs/startup_router_broker_tail.log` and full post-failure compose logs in `logs/compose_all_after_failure.log`.

## Probe Summary

The probe sent external HTTP requests to Router `POST /druid/v2/sql/` with `Content-Type: text/plain` and increasing body sizes. The smaller bodies were accepted, including an 8MiB request that took about 43 seconds and returned HTTP 200. The 32MiB `text/plain` request caused the Router JVM to terminate with:

```text
Terminating due to java.lang.OutOfMemoryError: Java heap space
```

The OOM excerpt is saved in `evidence/router_oom_excerpt.txt`. The Router container exit state is saved in `evidence/router_exit_state.json`.

## Cleanup

`docker compose -p druiddos_apache_druid down -v` removed the case containers, network, and named volumes. Post-cleanup checks for container and volume names matching `druiddos_apache_druid` were empty:

- `evidence/cleanup_container_check.txt`
- `evidence/cleanup_volume_check.txt`

No case containers or volumes are intentionally left running.
