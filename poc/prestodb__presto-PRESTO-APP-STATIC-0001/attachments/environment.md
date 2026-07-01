# Environment

- Case: `prestodb__presto-PRESTO-APP-STATIC-0001`
- Host date/time: 2026-06-29, Asia/Shanghai
- Repository root: `/home/furina/new_tool/dos-analysis-web`
- Target source: `/home/furina/new_tool/dos-analysis-web/frameworks/applications/prestodb__presto`
- Local source revision: `138f173-dirty`, Maven version in `pom.xml`: `0.299-SNAPSHOT`
- Dynamic deployment: official Docker image `prestodb/presto:0.298.1`
- Image repo digest: `prestodb/presto@sha256:aff53afed348be30818735646c0b73be639b24a5c97e1cf2562a68de527dc34a`
- Image ID: `sha256:db3f0b6b91f6002db354f79cadf709936d2fd7d83cb8614e5b7e738a8d27ff15`
- Runtime Presto version from `/v1/info`: `0.298.1-9e1b45f`
- Container name: `dos-presto-prestodb-presto-static-0001`
- Port mapping: `127.0.0.1:18080` to container `8080`
- Presto config changes: none.
- Harness limit: Docker `--memory=2g --memory-swap=2g`; this is a local safety limit, not a Presto default claim.
- JVM heap: image default `/opt/presto-server/etc/jvm.config` includes `-Xmx1G`, `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:+ExitOnOutOfMemoryError`.
- Default coordinator config: `coordinator=true`, `node-scheduler.include-coordinator=true`, `http-server.http.port=8080`, `discovery-server.enabled=true`, no `http-server.authentication.type`.

## Commands

See `start_commands.sh` and `probe.py`.

## Evidence

- `evidence/container_inspect_start.json`
- `evidence/container_inspect_final.json`
- `evidence/default_config.txt`
- `evidence/v1_info_ready.json`
- `logs/startup.log`
- `logs/container_final.log`
- `logs/probe_events.jsonl`
- `logs/responses_sample.jsonl`
- `logs/jcmd_heap_*.txt`
- `logs/class_histogram_*.txt`

## Download Notes

The Docker Hub pull for `prestodb/presto:0.298.1` retried several layers but completed successfully. No mirror substitution was used.

## Cleanup

The test container and anonymous Docker volume were removed with `docker rm -v dos-presto-prestodb-presto-static-0001`. An accidental full copy of `/var/lib/presto/data` contained `java_pid7.hprof` of 1,019,819,640 bytes; only `evidence/presto_data_copy_listing.txt` was retained and the large copy was deleted.
