# Environment

## Target

- Case ID: `apache__druid-DRUID-APP-STATIC-0002`
- Target: Apache Druid Router/Broker Avatica protobuf path
- Source checkout: `/home/furina/new_tool/dos-analysis-web/frameworks/applications/apache__druid`
- Validation time: `2026-06-29 22:25-22:28 CST`

## Deployment Source

The repository quickstart compose file at `distribution/docker/docker-compose.yml` referenced `apache/druid:38.0.0`, but Docker Hub returned `no such manifest` for that tag at validation time. The isolated run used the official available Docker image:

- Druid image: `apache/druid:37.0.0`
- Druid image digest: `apache/druid@sha256:0116fb802786649fc3635d6d4ab5be4da8abee3edafbe95c7f358a564d4c82e8`
- Image ID: `sha256:33bf0f2def52a3c56d253414764c95c5adf6d94923725ca41b98e3d66bec0e4e`
- Companion images: `postgres:17.6`, `zookeeper:3.5.10`
- Docker Engine: `29.5.2`
- Docker Compose: `5.1.4`

The compose file in this case directory preserves the official Docker quickstart environment values (`DRUID_SINGLE_NODE_CONF=micro-quickstart`, PostgreSQL metadata store, ZooKeeper discovery, and Druid extension list). Harness-only isolation changes:

- Removed fixed `container_name` values to avoid collisions with other workers.
- Bound host ports to `127.0.0.1` and shifted ports:
  - Router: `127.0.0.1:28888 -> 8888`
  - Broker: `127.0.0.1:28082 -> 8082`
  - Coordinator: `127.0.0.1:28081 -> 8081`
  - PostgreSQL: `127.0.0.1:25432 -> 5432`
  - ZooKeeper: `127.0.0.1:22181 -> 2181`
- Started the Router/Broker/Coordinator/PostgreSQL/ZooKeeper subset needed for this Router-to-Broker Avatica path.

No Druid application configuration was changed to enable the vulnerable endpoint.

## Heap And Limits

- Router default micro-quickstart JVM heap: `-Xms128m -Xmx128m`
- Router direct memory: `-XX:MaxDirectMemorySize=128m`
- Broker default micro-quickstart JVM heap: `-Xms512m -Xmx512m`
- Docker container memory limit: none set by this harness (`HostConfig.Memory=0`)
- Router startup log records `os.memory.max=128MB`.

## Commands

```bash
cd /home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002
docker compose -p druid_avatica_case -f docker-compose.yml up -d postgres zookeeper coordinator broker router
python3 probe.py --case-dir "$PWD" --compose-project druid_avatica_case --compose-file "$PWD/docker-compose.yml" --wait-only
python3 probe.py --case-dir "$PWD" --compose-project druid_avatica_case --compose-file "$PWD/docker-compose.yml"
docker compose -p druid_avatica_case -f docker-compose.yml down -v
```

## Readiness

Router and Broker `/status/health` returned HTTP 200 before the probe. Router discovery detected the Broker at `http://172.21.0.5:8082` before the first POST.

## Probe Summary

The probe used `POST /druid/v2/sql/avatica-protobuf/` with `Content-Type: application/x-protobuf`. Payloads were valid Avatica `OpenConnectionRequest` protobuf messages with an appended protobuf unknown length-delimited padding field.

Observed request outcomes:

| Request | Body bytes | Result |
| --- | ---: | --- |
| 1 | 87 | HTTP 200 `OpenConnectionResponse` |
| 2 | 1,048,576 | HTTP 500 from Broker because the connection ID was already open; request was forwarded |
| 3 | 8,388,608 | HTTP 500 from Broker; request was forwarded |
| 4 | 16,777,216 | HTTP 500 from Broker; request was forwarded |
| 5 | 33,554,432 | Client saw remote disconnect; Router exited |

No HTTP 413/body-size rejection was observed before the Router OOM.

## Failure Evidence

- Router RSS rose from about `391.6MiB` baseline to `449.2MiB` after the 16MiB body.
- After the 32MiB body, Router docker stats showed `0B / 0B`, `/status/health` returned connection refused, and Docker inspect reported `ExitCode=3`.
- Router log contains: `Terminating due to java.lang.OutOfMemoryError: Java heap space`.
- Docker `OOMKilled=false`, consistent with JVM `-XX:+ExitOnOutOfMemoryError` exiting due Java heap OOM rather than the container runtime killing the process.

## Cleanup

`docker compose down -v` removed all `druid_avatica_case-*` containers, the project network, and named volumes. Post-cleanup checks found no remaining `druid_avatica_case` containers or volumes.
