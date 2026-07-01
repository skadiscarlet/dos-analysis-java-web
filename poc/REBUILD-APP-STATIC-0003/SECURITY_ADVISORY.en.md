# Security Advisory PoC: Rebuild API gateway parses large JSON bodies before signature verification

## Summary

Rebuild anonymous `/gw/api/system-time?appid=bad&sign=bad` reads and parses the raw JSON body before signature rejection. In the 1 GiB heap retest, repeated roughly 24 MiB bodies triggered OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `getrebuild__rebuild` |
| Local true-positive ID | `REBUILD-APP-STATIC-0003` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `/gw/api/system-time?appid=bad&sign=bad` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST a large JSON body to an existing `/gw/api/system-time` API name with invalid appid/sign values.
- Root cause summary: `ApiGateway.buildBaseApiContext` calls `ServletUtils.getRequestString` and `JSON.parse` before verifying appid/sign.
- Exploitation conditions: The anonymous API gateway path is exposed, the API name exists, and no body or JSON limit blocks the request.
- Static source: `raw request body on /gw/api/** plus query appid/sign`
- Static sink: `ApiGateway.buildBaseApiContext calls ServletUtils.getRequestString(request) and JSON.parse(postData) before verfiy checks appid/sign/appSecret`
- Attacker-controlled driver: `attacker-controlled body byte volume, JSON nesting, and repeated requests to any existing API name`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case REBUILD-APP-STATIC-0003 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `10` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/REBUILD-APP-STATIC-0003.log` |

Evidence summary:

```text
Rebuild anonymous `/gw/api/system-time?appid=bad&sign=bad` reads and parses the raw JSON body before signature rejection. In the 1 GiB heap retest, repeated roughly 24 MiB bodies triggered OOM.
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
| poc/REBUILD-APP-STATIC-0003/attachments/source_record.json | binary truth record |
| poc/REBUILD-APP-STATIC-0003/attachments/evidence.json | normalized advisory evidence |
| poc/REBUILD-APP-STATIC-0003/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/REBUILD-APP-STATIC-0003/attachments/static_finding.json | copied application static finding |
| poc/REBUILD-APP-STATIC-0003/attachments/REBUILD-APP-STATIC-0003.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/REBUILD-APP-STATIC-0003.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
