# Security Advisory PoC: PowerJob pre-auth request body caching can be exhausted by ordinary POST bodies

## Summary

PowerJob paths such as `/container/downloadContainerTemplate` pass through a request-body caching filter before authentication. In the 1 GiB heap retest, a small number of large non-form request bodies triggered target JVM OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `powerjob__powerjob` |
| Local true-positive ID | `POWERJOB-APP-STATIC-0002` |
| Dynamic batch | `p0` |
| Dynamic status | `verified_oom` |
| Entry | `/container/downloadContainerTemplate` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Send large POST bodies with a non-form, non-multipart Content-Type to `/container/downloadContainerTemplate`.
- Root cause summary: `CachingRequestBodyFilter` copies the full body into String/StringBuilder/byte[] before authentication, while ordinary JSON/text/raw bodies are not constrained by multipart limits.
- Exploitation conditions: The entry is anonymous or pre-auth reachable, and non-multipart/form bodies are not limited by the server or proxy.
- Static source: `Any Spring MVC request with Content-Type not exactly application/x-www-form-urlencoded or multipart/form-data, including anonymous /openApi/* and /container/downloadContainerTemplate`
- Static sink: `CachingRequestBodyFilter.CustomHttpServletRequestWrapper reads the full body into StringBuilder/String and later body.getBytes()`
- Attacker-controlled driver: `attacker-controlled request body byte volume and concurrent request count`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case POWERJOB-APP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `8` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p0/logs/POWERJOB-APP-STATIC-0002.log` |

Evidence summary:

```text
PowerJob paths such as `/container/downloadContainerTemplate` pass through a request-body caching filter before authentication. In the 1 GiB heap retest, a small number of large non-form request bodies triggered target JVM OOM.
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
| poc/POWERJOB-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/POWERJOB-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/POWERJOB-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/POWERJOB-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/POWERJOB-APP-STATIC-0002/attachments/POWERJOB-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/POWERJOB-APP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
