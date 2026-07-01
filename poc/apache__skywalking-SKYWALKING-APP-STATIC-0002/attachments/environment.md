# Environment

## Case

- Case ID: `apache__skywalking-SKYWALKING-APP-STATIC-0002`
- Target: `apache/skywalking`
- Local source path: `/home/furina/new_tool/dos-analysis-web/frameworks/applications/apache__skywalking`
- Local source revision observed: `138f173-dirty`
- Validation time: `2026-06-29 15:06:42 +0800`

## Deployment

The validation used an isolated Docker Compose environment under this case directory, derived from the SkyWalking repository's documented Docker quickstart/compose model.

- Compose file: `docker-compose.yml`
- Compose project: `sw-pprof-case`
- OAP container: `sw-pprof-case-oap`
- BanyanDB container: `sw-pprof-case-banyandb`
- OAP image: `ghcr.io/apache/skywalking/oap:latest`
- OAP image digest observed locally: `ghcr.io/apache/skywalking/oap@sha256:2e91ae75dbc774957bef7680d251d92fcc02dbcba872b2e8049eba5697571873`
- OAP image ID: `sha256:275ca1a10c65e4fc9dedf2b84ad11bf3a58c59a925f6c0cf2513f0c0a0721468`
- OAP image created: `2026-06-25T03:04:53.944272199Z`
- OAP runtime version from startup log: `11.0.0-SNAPSHOT-bb16533`
- BanyanDB image: `ghcr.io/apache/skywalking-banyandb:69c8f4d20ebb6532ea4c16a7ed7114dd6ec9770b`
- BanyanDB digest observed locally: `ghcr.io/apache/skywalking-banyandb@sha256:73a26d61754c537f5f86f7b52c6fd24caa73e940812112127b47ac5e3c39e027`

Ports were remapped only on the host side to avoid conflicts:

- OAP gRPC: container `11800`, host `127.0.0.1:19180`
- OAP HTTP/GraphQL: container `12800`, host `127.0.0.1:19280`

## Configuration

Semantic receiver/auth settings were left at their default values:

- `module.receiver-pprof.provider = default`
- `module.receiver-sharing-server.provider = default`
- `oap.external.grpc.port = 11800`
- `oap.external.http.port = 12800`
- `SW_AUTHENTICATION` was not set, matching the default empty authentication token.
- `SW_RECEIVER_PPROF_MEMORY_PARSER_ENABLED` was not set, so the default memory parser stayed enabled.
- `SW_RECEIVER_PPROF_MAX_SIZE` was not set, so the default `31457280` byte maximum stayed in effect.

Harness-only settings:

- `SW_STORAGE=banyandb`
- `SW_STORAGE_BANYANDB_TARGETS=banyandb:17912`
- `SW_HEALTH_CHECKER=default`
- `SW_TELEMETRY=prometheus`
- `JAVA_OPTS=-Xms512m -Xmx512m -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/skywalking/logs/heapdump.hprof -XX:+ExitOnOutOfMemoryError`
- Compose `mem_limit: 1g`

The 512 MiB heap and 1 GiB container limit were safety harness limits to make the resource failure bounded and disposable. They are not claimed as production defaults.

## Readiness

Startup and readiness artifacts:

- `logs/compose-up.log`
- `logs/compose-ps-after-up.log`
- `logs/readiness.log`
- `logs/oap-startup.log`
- `logs/banyandb-startup.log`
- `logs/compose-ps-ready.log`

The OAP gRPC and HTTP ports were open on `2026-06-29T15:02:56+08:00`; Docker health later reported healthy during the smoke and growth probes.

## Probe

Protocol evidence:

- `evidence/apm-network-11.0.0-SNAPSHOT.jar`
- `evidence/apm-network-pprof-classes.txt`
- `evidence/javap-pprof-api.txt`
- `evidence/pprof-proto.txt`
- `evidence/proto/pprof/Pprof.proto`
- `evidence/proto_py/pprof/Pprof_pb2.py`

Executed stages:

- Smoke: 1 stream, `contentSize=1048576`, hold 5 s, result `PPROF_PROFILING_SUCCESS`, service stayed healthy.
- Growth: 4 streams, `contentSize=31457280`, hold 15 s, 4/4 streams returned `PPROF_PROFILING_SUCCESS`, service stayed healthy.
- Failure: 20 streams, `contentSize=31457280`, hold cap 30 s, 9 streams returned `PPROF_PROFILING_SUCCESS` before the target JVM exited with `java.lang.OutOfMemoryError: Java heap space`.

Probe artifacts:

- `probe.py`
- `logs/probe-smoke-1stream-1m.json`
- `logs/probe-smoke-1stream-1m.stdout`
- `logs/probe-growth-4stream-30m.json`
- `logs/probe-growth-4stream-30m.stdout`
- `logs/probe-failure-20stream-30m.json`
- `logs/probe-failure-20stream-30m.stdout`

Failure evidence:

- `logs/oap-after-failure.log`
- `logs/oap-state-after-failure.json`
- `logs/compose-ps-after-failure.log`
- `evidence/oap-oom-excerpts.txt`
- `evidence/oap-oom-context.txt`

The OAP log contains:

```text
java.lang.OutOfMemoryError: Java heap space
Terminating due to java.lang.OutOfMemoryError: Java heap space
```

Docker state after the failure was `Status=exited`, `ExitCode=3`, `OOMKilled=false`, showing a target JVM heap OOM exit rather than a Docker cgroup OOM kill.

## Cleanup

Cleanup command:

```shell
docker compose -p sw-pprof-case down -v
```

Cleanup artifacts:

- `logs/compose-down.log`
- `logs/post-cleanup-containers.txt`

No `sw-pprof-case-*` containers remained after cleanup.
