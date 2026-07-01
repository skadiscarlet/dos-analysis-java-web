# Security Advisory PoC: XXL-JOB executor trigger parameter queues can be exhausted with the default token

## Summary

With the default executor port 9999 and `default_token`, an attacker can submit many `/trigger` requests with large executorParams, growing retained queues and thread state. In the 1 GiB heap retest, 1025 triggers caused OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `xuxueli__xxl-job` |
| Local true-positive ID | `XXL-JOB-APP-STATIC-0002` |
| Dynamic batch | `p0` |
| Dynamic status | `verified_oom` |
| Entry | `protocol service on port 9999` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST to executor `/trigger` with the default token header, using unique jobIds or repeated triggers with large executorParams.
- Root cause summary: Executor job threads/queues retain executorParams, and default active job/thread count plus queued parameter bytes lack a hard bound.
- Exploitation conditions: Executor port 9999 is exposed, the default access token is unchanged or known, and trigger rate/parameter size are not limited.
- Static source: `external POST :9999/trigger for the same jobId with unique logId and payload fields`
- Static sink: `JobThread.pushTriggerQueue adds logId to triggerLogIdSet and TriggerRequest to an unbounded LinkedBlockingQueue`
- Attacker-controlled driver: `failed or slow trigger processing versus request rate; unique logId and executorParams/glueSource field size`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case XXL-JOB-APP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `1025` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p0/logs/XXL-JOB-APP-STATIC-0002.log` |

Evidence summary:

```text
With the default executor port 9999 and `default_token`, an attacker can submit many `/trigger` requests with large executorParams, growing retained queues and thread state. In the 1 GiB heap retest, 1025 triggers caused OOM.
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
| poc/XXL-JOB-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/XXL-JOB-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/XXL-JOB-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/XXL-JOB-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/XXL-JOB-APP-STATIC-0002/attachments/XXL-JOB-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/XXL-JOB-APP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
