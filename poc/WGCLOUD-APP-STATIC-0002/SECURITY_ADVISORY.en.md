# Security Advisory PoC: WGCloud default agent-token minTask arrays can exhaust static lists

## Summary

In a full WGCloud server plus MySQL default-token environment, `POST /wgcloud/agent/minTask` accepts large arrays that pressure BatchData static lists. In the 1 GiB heap retest, 175 requests triggered OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `tianshiyeben__wgcloud` |
| Local true-positive ID | `WGCLOUD-APP-STATIC-0002` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `/wgcloud/agent/minTask` |
| Required privilege | low-privilege account or default token/API key |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Use the default agent token to POST large array payloads to `/wgcloud/agent/minTask`.
- Root cause summary: Agent report data enters process-level batch static lists without default body, array-element, queue-length, or per-agent quotas.
- Exploitation conditions: The server agent endpoint is exposed, the default token is unchanged or known to a low-trust party, and array/body sizes are not limited.
- Static source: `JSON request body authenticated only by default wgToken md5 65d05df102851c6535322e73b2f99c06`
- Static sink: `@RequestBody String plus JSONUtil.parse, JSONUtil.toList/BeanUtil.copyProperties, BatchData static synchronizedList additions, and commitTask addAll batch copies`
- Attacker-controlled driver: `JSON byte volume, array element count, repeated request rate, and object field sizes`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case WGCLOUD-APP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `175` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/WGCLOUD-APP-STATIC-0002.log` |

Evidence summary:

```text
In a full WGCloud server plus MySQL default-token environment, `POST /wgcloud/agent/minTask` accepts large arrays that pressure BatchData static lists. In the 1 GiB heap retest, 175 requests triggered OOM.
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
| poc/WGCLOUD-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/WGCLOUD-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/WGCLOUD-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/WGCLOUD-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/WGCLOUD-APP-STATIC-0002/attachments/WGCLOUD-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/WGCLOUD-APP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
