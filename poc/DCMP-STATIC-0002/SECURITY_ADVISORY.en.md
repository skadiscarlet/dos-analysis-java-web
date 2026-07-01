# Security Advisory PoC: DataCompare Swagger test static map can be exhausted by an authenticated user

## Summary

After default Shiro login, requests to the Swagger test endpoint `/test/user/save` write into a static map. In the 1 GiB heap retest, about 15k requests triggered target JVM OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `dromara__datacompare` |
| Local true-positive ID | `DCMP-STATIC-0002` |
| Dynamic batch | `p0` |
| Dynamic status | `verified_oom` |
| Entry | `/test/user/save` |
| Required privilege | low-privilege account or default token/API key |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Use an authenticated session to repeatedly POST `/test/user/save` with unique fields or padded content.
- Root cause summary: The test endpoint stores user input in a process-level static map without a capacity, TTL, or per-user quota.
- Exploitation conditions: Requires a default authenticated session, and the test/Swagger endpoint is not disabled in the deployed package.
- Static source: `{'id': 'SRC-005', 'entry': 'POST /test/user/save', 'auth': 'low_privilege_authenticated', 'evidence': ['frameworks/applications/dromara__datacompare/src/main/resources/application.yml:204', 'frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/framework/config/ShiroConfig.java:310']}`
- Static sink: `{'id': 'SINK-005', 'operation': 'users.put(user.getUserId(), user)', 'resource_type': 'heap_retained_static_map', 'evidence': ['frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/project/tool/swagger/TestController.java:36', 'frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/project/tool/swagger/TestController.java:72']}`
- Attacker-controlled driver: `attacker-controlled userId key cardinality and retained UserEntity string fields`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case DCMP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `14994` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p0/logs/DCMP-STATIC-0002.log` |

Evidence summary:

```text
After default Shiro login, requests to the Swagger test endpoint `/test/user/save` write into a static map. In the 1 GiB heap retest, about 15k requests triggered target JVM OOM.
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
| poc/DCMP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/DCMP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/DCMP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/DCMP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/DCMP-STATIC-0002/attachments/DCMP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/DCMP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
