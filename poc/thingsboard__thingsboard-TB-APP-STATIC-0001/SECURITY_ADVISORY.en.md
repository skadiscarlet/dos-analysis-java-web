# Security Advisory PoC: ThingsBoard device telemetry chunked JSON can trigger OOM before token rejection

## Summary

In the official ThingsBoard tb-node single-node deployment, the HTTP device telemetry path reads and binds chunked JSON request bodies before token rejection completes. With -Xmx1024m and a 2 GiB container, one 512 MiB timeseries-large-value request triggered Java heap OOM and HTTP 500.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `thingsboard/thingsboard` |
| Local true-positive ID | `thingsboard__thingsboard-TB-APP-STATIC-0001` |
| Dynamic batch | `new` |
| Dynamic status | `confirmed_oom` |
| Entry | `POST /api/v1/{deviceToken}/telemetry` |
| Required privilege | anonymous |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Send chunked JSON without Content-Length to `/api/v1/{deviceToken}/telemetry`, with one very large string value.
- Root cause summary: Spring `@RequestBody String` and later JSON parsing materialize the request body before the authentication failure response; the default Content-Length check does not constrain no-Content-Length chunked requests.
- Exploitation conditions: HTTP device transport is exposed, chunked bodies are not limited by a gateway/container, and a valid device token is not needed to reach body binding.
- Static source: `Device HTTP transport POST bodies under /api/v1/{deviceToken}/telemetry and /api/v1/{deviceToken}/attributes.`
- Static sink: `Spring @RequestBody String followed by JsonParser.parseString and JsonConverter conversion in DeviceApiController.`
- Attacker-controlled driver: `Body byte volume and JSON key/value or timestamp-array count; especially requests without a positive Content-Length.`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001
docker compose -p tb-dos-thingsboard-static-0001 up -d postgres
docker compose -p tb-dos-thingsboard-static-0001 run --rm -e INSTALL_TB=true -e LOAD_DEMO=false -e JAVA_OPTS='-Xms512m -Xmx1024m -Xss384k' tb-node
docker compose -p tb-dos-thingsboard-static-0001 up -d tb-node
./probe.py --token <token-shaped-path-segment> --endpoint telemetry --payload-mode timeseries-large-value --sizes-mib 256,512 --timeout 240 --chunk-bytes 65536 --out logs/probe_results_reinforce_telemetry_large.jsonl
docker compose -p tb-dos-thingsboard-static-0001 down -v
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Java heap space` |
| Heap / memory evidence | `ThingsBoard tb-node JAVA_OPTS=-Xms512m -Xmx1024m -Xss384k; Docker compose mem_limit=2g` |
| Requests sent | `2` |
| Strict 1 GiB evidence | `mem_limit=2g` |
| Original log path | `logs/probe_results_reinforce_telemetry_large.jsonl` |

Evidence summary:

```text
In the official ThingsBoard tb-node single-node deployment, the HTTP device telemetry path reads and binds chunked JSON request bodies before token rejection completes. With -Xmx1024m and a 2 GiB container, one 512 MiB timeseries-large-value request triggered Java heap OOM and HTTP 500.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- Reverse proxy, servlet container, or Spring request limits that reject chunked/no-Content-Length bodies before controller binding mitigate this path.
- A lower ThingsBoard HTTP transport max payload enforced independently of Content-Length would mitigate this path.
- JSON string length/body complexity limits before @RequestBody String materialization would mitigate this path.
- Authentication alone is insufficient if request body binding precedes token rejection for this endpoint shape.

Not affected or substantially reduced risk when:

- HTTP device transport is not exposed to low-trust clients.
- Chunked request bodies without Content-Length are rejected or capped before Spring binds @RequestBody String.
- Telemetry JSON body size/string length is bounded before JsonParser.parseString and JsonConverter processing.

## Attachments

| Field | Value |
| --- | --- |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/probe.py |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/docker-compose.yml |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/start_commands.sh |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/case_plan.json |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/environment.md |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/thingsboard__thingsboard-TB-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/logs/probe_results_reinforce_telemetry_large.jsonl |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
