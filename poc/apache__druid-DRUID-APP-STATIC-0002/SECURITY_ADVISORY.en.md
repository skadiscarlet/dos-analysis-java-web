# Security Advisory PoC: Apache Druid Router Avatica protobuf requests can exhaust JVM heap

## Summary

The default unauthenticated Druid Router Avatica protobuf endpoint accepts large valid protobuf POST bodies. In the 1 GiB Router heap retest, a 128 MiB request left the service running, while a 256 MiB request triggered Java heap OOM, Router exit code 3, and refused health checks.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `apache/druid` |
| Local true-positive ID | `apache__druid-DRUID-APP-STATIC-0002` |
| Dynamic batch | `new` |
| Dynamic status | `confirmed_oom` |
| Entry | `POST /druid/v2/sql/avatica-protobuf/ through Router port 8888` |
| Required privilege | anonymous |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST an `application/x-protobuf` Avatica OpenConnectionRequest to `/druid/v2/sql/avatica-protobuf/` with large protobuf unknown-field padding.
- Root cause summary: The Router forwarding path stores the full Avatica request body in a `byte[]` request attribute and lacks a default body/byte quota.
- Exploitation conditions: The Router Avatica endpoint is anonymously reachable and not blocked by authentication, proxy limits, or request body caps.
- Static source: `POST /druid/v2/sql/avatica-protobuf through Router.`
- Static sink: `AsyncQueryForwardingServlet.service reads the full InputStream into byte[] requestBytes and stores it as AVATICA_QUERY_ATTRIBUTE for proxying.`
- Attacker-controlled driver: `Avatica protobuf request body byte volume; repeated concurrent requests retain byte arrays during broker selection/proxy forwarding.`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002
docker compose -p druid_avatica_case_1g -f docker-compose.yml up -d postgres zookeeper coordinator broker router
python3 probe.py --case-dir "$PWD" --compose-project druid_avatica_case_1g --compose-file "$PWD/docker-compose.yml" --wait-only --ready-timeout 300
python3 probe.py --case-dir "$PWD" --compose-project druid_avatica_case_1g --compose-file "$PWD/docker-compose.yml" --sizes 134217728,268435456,536870912,805306368 --request-timeout 300 --ready-timeout 60
docker compose -p druid_avatica_case_1g -f docker-compose.yml down -v
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Java heap space` |
| Heap / memory evidence | `Druid Router DRUID_XMS=1g and DRUID_XMX=1g; Docker HostConfig.Memory=0, no container memory limit` |
| Requests sent | `2` |
| Strict 1 GiB evidence | `druid_xmx=1g` |
| Original log path | `logs/router_after_1g_oom.log` |

Evidence summary:

```text
The default unauthenticated Druid Router Avatica protobuf endpoint accepts large valid protobuf POST bodies. In the 1 GiB Router heap retest, a 128 MiB request left the service running, while a 256 MiB request triggered Java heap OOM, Router exit code 3, and refused health checks.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- HTTP request body size limit or reverse proxy limit below the OOM threshold
- Authentication/authorization preventing anonymous access to /druid/v2/sql/avatica-protobuf/
- Network isolation of Router or JDBC endpoint
- Rate limiting or per-client quota on large POST bodies
- Higher Router heap may raise the threshold but does not remove the unbounded full-body buffering behavior

Not affected or substantially reduced risk when:

- Router is not exposed to low-trust clients
- Avatica protobuf endpoint is blocked or protected by authentication
- A front proxy or server setting rejects large request bodies before they reach Router
- Druid deployment does not route JDBC/Avatica traffic through Router

## Attachments

| Field | Value |
| --- | --- |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/probe.py |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/docker-compose.yml |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/start_commands.sh |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/case_plan.json |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/environment.md |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/apache__druid-DRUID-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/logs/router_after_1g_oom.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
