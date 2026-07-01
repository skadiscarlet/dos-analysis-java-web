# Security Advisory PoC: Citrus anonymous authentication JSON body buffering can trigger JVM OOM

## Summary

The Citrus anonymous `/rest/authenticate` path buffers/parses request bodies. In the 1 GiB heap retest, repeated or concurrent submissions of roughly 20 MiB JSON bodies triggered target JVM OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `yiuman__citrus` |
| Local true-positive ID | `CITRUS-APP-STATIC-0002` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `/rest/authenticate` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Send large JSON bodies to `/rest/authenticate` in the ordinary anonymous authentication request shape.
- Root cause summary: The authentication entry materializes the full request body and JSON structure before rejection, without a sufficiently low default cap for ordinary JSON bodies.
- Exploitation conditions: The anonymous authentication entry is exposed, and ordinary JSON bodies are not rejected by server/proxy size limits.
- Static source: `permitAll authenticate endpoint request body`
- Static sink: `RequestWrapperFilter.RequestWrapper reads full body; AuthenticateProcessorImpl creates JsonServletRequestWrapper which reads String/byte[] and Jackson Map`
- Attacker-controlled driver: `request body byte volume, JSON object/key count, parser work`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case CITRUS-APP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `19` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/CITRUS-APP-STATIC-0002.log` |

Evidence summary:

```text
The Citrus anonymous `/rest/authenticate` path buffers/parses request bodies. In the 1 GiB heap retest, repeated or concurrent submissions of roughly 20 MiB JSON bodies triggered target JVM OOM.
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
| poc/CITRUS-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/CITRUS-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/CITRUS-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/CITRUS-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/CITRUS-APP-STATIC-0002/attachments/CITRUS-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/CITRUS-APP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
