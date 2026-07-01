# Security Advisory PoC: XXL-JOB /trigger large payloads can trigger executor JVM OOM

## Summary

The XXL-JOB executor `/trigger` path protected only by the default token accepts large payloads. In the 1 GiB heap retest, 199 requests with roughly 4 MiB payloads triggered target JVM OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `xuxueli__xxl-job` |
| Local true-positive ID | `XXL-JOB-APP-STATIC-0004` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `/trigger` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST a TriggerRequest with large parameter fields to `/trigger` using the default token header.
- Root cause summary: Trigger request parameters are retained in scheduling/execution queues without default limits on per-request parameter size, queued aggregate bytes, or per-token rate.
- Exploitation conditions: The executor endpoint is exposed, the default token is unchanged or known, and body/parameter size plus trigger rate are not limited.
- Static source: `external POST :9999/{trigger,beat,log,...} with near-5MiB body and high concurrency`
- Static sink: `Netty HttpObjectAggregator(5MiB), FullHttpRequest content to UTF-8 String, and bizThreadPool max 200/queue 2000`
- Attacker-controlled driver: `body byte volume, concurrency, queued Runnable count`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case XXL-JOB-APP-STATIC-0004 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `199` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/XXL-JOB-APP-STATIC-0004.log` |

Evidence summary:

```text
The XXL-JOB executor `/trigger` path protected only by the default token accepts large payloads. In the 1 GiB heap retest, 199 requests with roughly 4 MiB payloads triggered target JVM OOM.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- None recorded.

Not affected or substantially reduced risk when:

- None recorded.

## Attachments

| Field | Value |
| --- | --- |
| poc/XXL-JOB-APP-STATIC-0004/attachments/source_record.json | binary truth record |
| poc/XXL-JOB-APP-STATIC-0004/attachments/evidence.json | normalized advisory evidence |
| poc/XXL-JOB-APP-STATIC-0004/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/XXL-JOB-APP-STATIC-0004/attachments/static_finding.json | copied application static finding |
| poc/XXL-JOB-APP-STATIC-0004/attachments/XXL-JOB-APP-STATIC-0004.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/XXL-JOB-APP-STATIC-0004.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
