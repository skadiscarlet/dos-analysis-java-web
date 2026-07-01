# Security Advisory PoC: Apache Druid Router SQL request body can exhaust JVM heap

## Summary

The default unauthenticated Druid Router `POST /druid/v2/sql/` path materializes attacker-controlled SQL request bodies before processing. In the 1 GiB Router heap retest, one 512 MiB `text/plain` body triggered `OutOfMemoryError: Java heap space` and terminated the Router.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `apache/druid` |
| Local true-positive ID | `apache__druid-DRUID-APP-STATIC-0001` |
| Dynamic batch | `new` |
| Dynamic status | `confirmed_oom` |
| Entry | `POST /druid/v2/sql/ on Druid Router HTTP port 8888` |
| Required privilege | anonymous |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Send progressively larger `text/plain` SQL bodies to the Router SQL endpoint; the failing local sample used a 512 MiB body.
- Root cause summary: The `SqlQuery.from` path reads the full input stream with `IOUtils.toByteArray(request.getInputStream())` and constructs a full string without a default body-size cap.
- Exploitation conditions: Router is reachable anonymously; no account is required; no proxy or Druid setting rejects large bodies below the failure threshold.
- Static source: `POST /druid/v2/sql/ with Content-Type text/plain or application/x-www-form-urlencoded; Router path also calls SqlQuery.from(HttpServletRequest,ObjectMapper).`
- Static sink: `SqlQuery.from rawQueryExtractor uses IOUtils.toByteArray(request.getInputStream()) and constructs a String before trim/decode.`
- Attacker-controlled driver: `HTTP request body byte volume; concurrent body submissions multiply live byte[]/String pressure.`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001
docker compose -p druiddos_apache_druid up -d
./probe.py --max-size 536870912 --size-steps 1048576,8388608,33554432,67108864,134217728,268435456,536870912 --content-types text/plain --concurrency 1 --timeout 360 --chunk-size 1048576 --stop-on-failure
docker compose -p druiddos_apache_druid down -v
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Java heap space` |
| Heap / memory evidence | `Druid Router DRUID_XMS=1g and DRUID_XMX=1g; no Docker mem_limit set in the case compose` |
| Requests sent | `7` |
| Strict 1 GiB evidence | `druid_xmx=1g` |
| Original log path | `logs/compose_all_reinforce.log` |

Evidence summary:

```text
The default unauthenticated Druid Router `POST /druid/v2/sql/` path materializes attacker-controlled SQL request bodies before processing. In the 1 GiB Router heap retest, one 512 MiB `text/plain` body triggered `OutOfMemoryError: Java heap space` and terminated the Router.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- Default quickstart did not reject the probed text/plain SQL body before Router heap OOM.
- Reverse proxy, Jetty, or Druid-level request body limits below the failure threshold would block this exact trigger.
- Authentication, authorization, per-client rate limits, or network isolation of Router reduce external reachability.
- Different Druid versions or a fix that streams or caps raw SQL bodies may change exploitability.

Not affected or substantially reduced risk when:

- The Router /druid/v2/sql/ endpoint is not exposed to low-trust clients.
- Requests with text/plain or form-urlencoded SQL bodies are capped below the memory-pressure threshold.
- The deployment requires authenticated roles not available to the attacker.
- A front proxy rejects large bodies before they reach the Druid JVM.

## Attachments

| Field | Value |
| --- | --- |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/probe.py |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/docker-compose.yml |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/case_plan.json |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/environment.md |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/apache__druid-DRUID-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/logs/compose_all_reinforce.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
