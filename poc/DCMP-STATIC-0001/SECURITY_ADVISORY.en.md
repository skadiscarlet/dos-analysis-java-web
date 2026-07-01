# Security Advisory PoC: DataCompare demo operate static map can be exhausted by an authenticated user

## Summary

After default Shiro login, requests to `/demo/operate/add` write into a demo static map. In the 1 GiB heap retest, about 40.3k requests triggered target JVM OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `dromara__datacompare` |
| Local true-positive ID | `DCMP-STATIC-0001` |
| Dynamic batch | `p0` |
| Dynamic status | `verified_oom` |
| Entry | `/demo/operate/add` |
| Required privilege | low-privilege account or default token/API key |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Use an authenticated default session to repeatedly call `/demo/operate/add`, causing each request to write a unique static-map entry.
- Root cause summary: The demo operation path retains process-level static-map state without a default capacity, TTL, or user/IP quota.
- Exploitation conditions: Requires a login-capable default application state, and the demo endpoint must be reachable to that user.
- Static source: `{'id': 'SRC-003', 'entry': 'POST /demo/operate/add', 'auth': 'low_privilege_authenticated', 'evidence': ['frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/framework/config/ShiroConfig.java:310', 'frameworks/applications/dromara__datacompare/src/main/resources/application.yml:10']}`
- Static sink: `{'id': 'SINK-002', 'operation': 'users.put(userId, user)', 'resource_type': 'heap_retained_static_map', 'evidence': ['frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/project/demo/controller/DemoOperateController.java:39', 'frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/project/demo/controller/DemoOperateController.java:149']}`
- Attacker-controlled driver: `number of requests or imported rows; each add gets a new Integer key from users.size()+1`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case DCMP-STATIC-0001 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `40307` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p0/logs/DCMP-STATIC-0001.log` |

Evidence summary:

```text
After default Shiro login, requests to `/demo/operate/add` write into a demo static map. In the 1 GiB heap retest, about 40.3k requests triggered target JVM OOM.
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
| poc/DCMP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/DCMP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/DCMP-STATIC-0001/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/DCMP-STATIC-0001/attachments/static_finding.json | copied application static finding |
| poc/DCMP-STATIC-0001/attachments/DCMP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/DCMP-STATIC-0001.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
