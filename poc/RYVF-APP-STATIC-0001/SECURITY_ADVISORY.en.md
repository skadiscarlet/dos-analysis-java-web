# Security Advisory PoC: RuoYi-Vue-Fast test user static map can be exhausted by a low-privilege session

## Summary

After default database initialization and entry into a low-privilege authenticated session, the `/test/user/save` static-map sink can be filled by repeated requests. In the 1 GiB heap retest, about 2.9k requests triggered target JVM OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `yangzongzhuan__ruoyi-vue-fast` |
| Local true-positive ID | `RYVF-APP-STATIC-0001` |
| Dynamic batch | `p0` |
| Dynamic status | `verified_oom` |
| Entry | `/test/user/save` |
| Required privilege | low-privilege account or default token/API key |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Use a low-privilege login token to repeatedly POST `/test/user/save` with padded request bodies.
- Root cause summary: The test user-save path writes to a process-level static map without capacity, TTL, or account/IP quotas.
- Exploitation conditions: Requires an authenticated session; the local retest disabled the default captcha setting to reliably enter the path, and that condition should be disclosed separately.
- Static source: `authenticated low-privilege HTTP request parameters userId, username, password, mobile`
- Static sink: `TestController.users.put(user.getUserId(), user) where users is private static final LinkedHashMap`
- Attacker-controlled driver: `distinct userId values and UserEntity field sizes`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case RYVF-APP-STATIC-0001 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `2987` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p0/logs/RYVF-APP-STATIC-0001.log` |

Evidence summary:

```text
After default database initialization and entry into a low-privilege authenticated session, the `/test/user/save` static-map sink can be filled by repeated requests. In the 1 GiB heap retest, about 2.9k requests triggered target JVM OOM.
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
| poc/RYVF-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/RYVF-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/RYVF-APP-STATIC-0001/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/RYVF-APP-STATIC-0001/attachments/static_finding.json | copied application static finding |
| poc/RYVF-APP-STATIC-0001/attachments/RYVF-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/RYVF-APP-STATIC-0001.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
