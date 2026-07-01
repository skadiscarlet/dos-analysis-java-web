# Security Advisory PoC: Erupt operation-log filter copies JSON bodies before auth and can exhaust heap

## Summary

On anonymous POST `/erupt-api/data/table/EruptUser`, the operation-log filter copies the JSON body before authorization rejection. In the 1 GiB heap retest, repeated roughly 36 MiB bodies triggered Java heap OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `erupts__erupt` |
| Local true-positive ID | `ERUPT-APP-STATIC-0002` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `/erupt-api/data/table/EruptUser` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST a large JSON body to `/erupt-api/data/table/EruptUser`; even if the final response is 401, the body wrapper runs first.
- Root cause summary: `EruptRequestWrapper` reads the full JSON body in the filter and retains multiple String/byte[] copies without a default recorded-body length cap.
- Exploitation conditions: An anonymous `/erupt-api/*` JSON path is reachable, the operation-log filter is enabled, and no gateway body limit blocks the request.
- Static source: `Any /erupt-api/* request with Content-Type exactly application/json and attacker-controlled body`
- Static sink: `HttpServletRequestFilter.EruptRequestWrapper reads the full request body with StreamUtils.copyToString and later duplicates it via body.getBytes(); RequestBodyTL.remove is only reached in OperationService for @EruptRecordOperate handlers`
- Attacker-controlled driver: `request body byte volume, concurrent request count, servlet worker thread count`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case ERUPT-APP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `13` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/ERUPT-APP-STATIC-0002.log` |

Evidence summary:

```text
On anonymous POST `/erupt-api/data/table/EruptUser`, the operation-log filter copies the JSON body before authorization rejection. In the 1 GiB heap retest, repeated roughly 36 MiB bodies triggered Java heap OOM.
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
| poc/ERUPT-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/ERUPT-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/ERUPT-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/ERUPT-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/ERUPT-APP-STATIC-0002/attachments/ERUPT-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/ERUPT-APP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
