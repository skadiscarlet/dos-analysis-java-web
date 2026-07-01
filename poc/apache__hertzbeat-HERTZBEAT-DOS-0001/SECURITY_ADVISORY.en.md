# Security Advisory PoC: Apache HertzBeat Prometheus push cardinality can exhaust direct memory

## Summary

In the default HertzBeat 1.8.0 Docker deployment, the anonymous Prometheus push path auto-creates monitors from unique job/instance values. With 1 GiB heap/direct memory and a 2 GiB container, about 21.7k minimal push requests triggered direct-buffer OOM and repeated HTTP 502 responses on the push plane.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `apache/hertzbeat` |
| Local true-positive ID | `apache__hertzbeat-HERTZBEAT-DOS-0001` |
| Dynamic batch | `new` |
| Dynamic status | `confirmed_oom` |
| Entry | `POST /api/push/prometheus/job/{job}/instance/{instance}` |
| Required privilege | anonymous |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Send minimal Prometheus text bodies to `/api/push/prometheus/job/{job}/instance/{instance}` while rotating job and instance path segments.
- Root cause summary: The job/instance pair drives automatic retained push-monitor state, and no default authentication, rate, cardinality, or eviction bound was observed.
- Exploitation conditions: `/api/push/**` is reachable anonymously, push auto-create is enabled, and job/instance cardinality is not bounded per source.
- Static source: `POST /api/push/prometheus/job/{job}/instance/{instance} through PushPrometheusStreamReadingFilter`
- Static sink: `PushGatewayServiceImpl.jobInstanceMap.computeIfAbsent(job + "_" + instance, ...)`
- Attacker-controlled driver: `attacker-controlled unique job and instance path segments`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001
docker run -d --name hbdos0001-hertzbeat --memory 2g --memory-swap 2g -e JAVA_OPTS="-Xms1g -Xmx1g -XX:MaxDirectMemorySize=1g --add-opens=java.base/java.nio=org.apache.arrow.memory.core,ALL-UNNAMED" -p 2157:1157 -p 2158:1158 docker.m.daocloud.io/apache/hertzbeat:1.8.0
./probe.py --count 30000 --start-index 1 --sample-every 250 --timeout 5 --concurrency 8 --case-dir .
docker rm -f hbdos0001-hertzbeat
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Cannot reserve 4194304 bytes of direct buffer memory (allocated: 1070396417, limit: 1073741824)` |
| Heap / memory evidence | `HertzBeat JAVA_OPTS=-Xms1g -Xmx1g -XX:MaxDirectMemorySize=1g; Docker --memory 2g --memory-swap 2g` |
| Requests sent | `21763` |
| Strict 1 GiB evidence | `java_opts=-xms1g` |
| Original log path | `logs/container_full_reinforce.log` |

Evidence summary:

```text
In the default HertzBeat 1.8.0 Docker deployment, the anonymous Prometheus push path auto-creates monitors from unique job/instance values. With 1 GiB heap/direct memory and a 2 GiB container, about 21.7k minimal push requests triggered direct-buffer OOM and repeated HTTP 502 responses on the push plane.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- This run used a 2GiB Docker memory cap and explicit 1GiB Java heap/direct memory as a strict validation harness; larger production containers may require more unique job/instance keys before OOM.
- No authentication, rate limit, per-IP quota, job/instance cardinality cap, or eviction was observed on the tested push path.
- The controller returned HTTP 400 for many successful side-effect requests, but logs confirmed monitor auto-creation before/around the response.
- Disabling unauthenticated push auto-create or bounding job/instance cardinality mitigates this path.

Not affected or substantially reduced risk when:

- /api/push/** is not exposed to low-trust clients or is protected by authentication.
- Prometheus push auto-create is disabled or constrained.
- Unique job/instance cardinality is capped per tenant, user, or source IP.
- Created push monitors are evicted or quota-managed.
- Reverse proxy or gateway rate limits prevent the required request volume.

## Attachments

| Field | Value |
| --- | --- |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/source_record.json | binary truth record |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/evidence.json | normalized advisory evidence |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/probe.py |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/start_commands.sh |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/case_plan.json |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/environment.md |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/apache__hertzbeat-HERTZBEAT-DOS-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/logs/container_full_reinforce.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
