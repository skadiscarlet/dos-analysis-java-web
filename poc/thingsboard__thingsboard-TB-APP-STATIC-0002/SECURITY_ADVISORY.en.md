# Security Advisory PoC: ThingsBoard authenticated REST attributes chunked bodies bypass default size checks and trigger OOM

## Summary

In the official single-container deployment, a client with a low-privilege role capable of writing device attributes, such as TENANT_ADMIN, can use a chunked attributes POST without Content-Length to bypass the default 16 MiB `/api/**` Content-Length check. With a 1.5 GiB heap, a 256 MiB body triggered Java heap OOM and HTTP unavailability.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `thingsboard/thingsboard` |
| Local true-positive ID | `thingsboard__thingsboard-TB-APP-STATIC-0002` |
| Dynamic batch | `new` |
| Dynamic status | `confirmed_oom` |
| Entry | `Authenticated HTTP POST /api/plugins/telemetry/DEVICE/{deviceId}/SERVER_SCOPE with Transfer-Encoding: chunked and no Content-Length` |
| Required privilege | low-privilege account or default token/API key |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: After authenticating as the default tenant administrator, send a JWT-authenticated chunked JSON attributes body to `/api/plugins/telemetry/DEVICE/{deviceId}/SERVER_SCOPE`.
- Root cause summary: PayloadSizeFilter relies on Content-Length; chunked no-Content-Length requests reach `@RequestBody String` and JSON conversion before memory pressure is bounded.
- Exploitation conditions: Requires a low-privilege or tenant-admin account that can write device attributes for an accessible deviceId, and no gateway limit on chunked bodies.
- Static source: `Ordinary authenticated /api telemetry/attribute POST body accepted as @RequestBody String.`
- Static sink: `TelemetryController.saveAttributes/saveTelemetry parses full body with JsonParser and converts all entries into lists before asynchronous save.`
- Attacker-controlled driver: `Body byte volume and JSON key/value count when Content-Length is unknown or not trusted.`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002
docker run -d --name tb-dos-thingsboard-static-0002 --memory=4096m --memory-swap=4096m -e JAVA_OPTS='-Xms512m -Xmx1536m -XX:+ExitOnOutOfMemoryError' -p 127.0.0.1:19090:9090 -v "$PWD/data:/data" -v "$PWD/container-logs:/var/log/thingsboard" thingsboard/tb-postgres:latest
./probe.py --endpoint attributes --sizes-mib 17,64,128,256 --control-mib 17 --value-len 8192
docker rm -f -v tb-dos-thingsboard-static-0002
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Java heap space` |
| Heap / memory evidence | `JVM -Xmx1536m; Docker --memory=4096m --memory-swap=4096m` |
| Requests sent | `5` |
| Strict 1 GiB evidence | `-xmx1536m` |
| Original log path | `logs/probe_events.jsonl` |

Evidence summary:

```text
In the official single-container deployment, a client with a low-privilege role capable of writing device attributes, such as TENANT_ADMIN, can use a chunked attributes POST without Content-Length to bypass the default 16 MiB `/api/**` Content-Length check. With a 1.5 GiB heap, a 256 MiB body triggered Java heap OOM and HTTP unavailability.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- Default PayloadSizeFilter rejected the same 17MiB request when Content-Length was present, but did not reject the chunked no-Content-Length variant.
- A reverse proxy, servlet container, or gateway that enforces body size for chunked requests before Spring @RequestBody materialization would mitigate this path.
- Reducing maximum JSON string length, adding per-user/per-device body quotas, rate limits, or streaming parser bounds would reduce exploitability.
- The exact OOM threshold depends on heap/container sizing; this validation used -Xmx1536m and a 4GiB container cap as a bounded harness.

Not affected or substantially reduced risk when:

- The REST /api/plugins/telemetry attributes/timeseries endpoints are not externally reachable.
- Only trusted users can write telemetry or attributes to the target entity.
- All inbound HTTP paths enforce body limits for chunked requests before request body materialization.
- Deployments set sufficiently strict upstream body limits or reject Transfer-Encoding: chunked for these API routes.

## Attachments

| Field | Value |
| --- | --- |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/source_result.json | copied dynamic result.json content |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/probe.py |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/start_commands.sh |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/case_plan.json |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/environment.md |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/thingsboard__thingsboard-TB-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/logs/probe_events.jsonl |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
