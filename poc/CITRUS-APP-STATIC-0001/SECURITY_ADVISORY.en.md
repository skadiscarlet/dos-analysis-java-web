# Security Advisory PoC: Citrus captcha session verification store can exhaust heap through HttpSession state

## Summary

With the full MySQL/Redis environment and session verification store enabled, anonymous `/rest/verify/captcha` requests continuously create and retain session captcha state. In the 1 GiB heap retest, about 48.9k requests triggered target JVM OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `yiuman__citrus` |
| Local true-positive ID | `CITRUS-APP-STATIC-0001` |
| Dynamic batch | `p0` |
| Dynamic status | `verified_oom` |
| Entry | `/rest/verify/captcha` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Repeatedly request `/rest/verify/captcha` without reusing cookies so the server creates many HttpSessions containing captcha state.
- Root cause summary: Captcha state is written to HttpSession, and no sufficient default quota was observed for session count, source, or aggregate bytes.
- Exploitation conditions: Captcha uses the session store, the entry is anonymous, and session creation/retention is not bounded by gateway or application quotas.
- Static source: `permitAll verification endpoint path variable type=caption`
- Static sink: `CaptchaProcessor.send -> SessionVerificationRepository.save -> request.getSession().setAttribute(SESSION_VERIFY_ID, Captcha)`
- Attacker-controlled driver: `number of fresh sessions created by requests that omit or vary the session cookie`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case CITRUS-APP-STATIC-0001 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `48950` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p0/logs/CITRUS-APP-STATIC-0001.log` |

Evidence summary:

```text
With the full MySQL/Redis environment and session verification store enabled, anonymous `/rest/verify/captcha` requests continuously create and retain session captcha state. In the 1 GiB heap retest, about 48.9k requests triggered target JVM OOM.
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
| poc/CITRUS-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/CITRUS-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/CITRUS-APP-STATIC-0001/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/CITRUS-APP-STATIC-0001/attachments/static_finding.json | copied application static finding |
| poc/CITRUS-APP-STATIC-0001/attachments/CITRUS-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/CITRUS-APP-STATIC-0001.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
