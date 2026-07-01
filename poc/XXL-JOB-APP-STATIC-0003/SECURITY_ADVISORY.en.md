# Security Advisory PoC: XXL-JOB GLUE_GROOVY unique jobIds can exhaust native threads

## Summary

The XXL-JOB default-token GLUE_GROOVY path can create many JobThread instances by using unique jobIds and a blocking glueSource. In the 1 GiB heap retest, 780 triggers caused native thread exhaustion / availability failure and were confirmed as resource-exhaustion true positive.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `xuxueli__xxl-job` |
| Local true-positive ID | `XXL-JOB-APP-STATIC-0003` |
| Dynamic batch | `p1` |
| Dynamic status | `confirmed_thread_exhaustion` |
| Entry | `protocol service on port 9999` |
| Required privilege | low-privilege account or default token/API key |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST to executor `/trigger` with the default token, glueType=GLUE_GROOVY, unique jobIds, and a blocking glueSource.
- Root cause summary: `jobThreadRepository` creates and retains JobThread instances keyed by jobId; no default active JobThread cap prevents blocking tasks from exhausting native threads.
- Exploitation conditions: Executor port 9999 is exposed, the default token is usable, the GLUE_GROOVY path is reachable, and jobId/thread counts are not limited.
- Static source: `external POST :9999/trigger with glueType=GLUE_GROOVY, unique glueSource and default token/appname`
- Static sink: `GlueFactory.getCodeSourceClass parses Groovy source and stores Class<?> in CLASS_CACHE by codeSource MD5`
- Attacker-controlled driver: `unique compilable glueSource contents and size`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case XXL-JOB-APP-STATIC-0003 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `780` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/XXL-JOB-APP-STATIC-0003.log` |

Evidence summary:

```text
The XXL-JOB default-token GLUE_GROOVY path can create many JobThread instances by using unique jobIds and a blocking glueSource. In the 1 GiB heap retest, 780 triggers caused native thread exhaustion / availability failure and were confirmed as resource-exhaustion true positive.
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
| poc/XXL-JOB-APP-STATIC-0003/attachments/source_record.json | binary truth record |
| poc/XXL-JOB-APP-STATIC-0003/attachments/evidence.json | normalized advisory evidence |
| poc/XXL-JOB-APP-STATIC-0003/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/XXL-JOB-APP-STATIC-0003/attachments/static_finding.json | copied application static finding |
| poc/XXL-JOB-APP-STATIC-0003/attachments/XXL-JOB-APP-STATIC-0003.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/XXL-JOB-APP-STATIC-0003.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
