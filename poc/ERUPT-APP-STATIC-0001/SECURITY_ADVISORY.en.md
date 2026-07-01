# Security Advisory PoC: Erupt captcha height parameter can drive BufferedImage allocation OOM

## Summary

In the Erupt sample default H2 deployment, the anonymous `/erupt-api/code-img` endpoint lets the `height` parameter directly affect captcha image height. In the 1 GiB heap retest, very large height values triggered `BufferedImage` allocation and OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `erupts__erupt` |
| Local true-positive ID | `ERUPT-APP-STATIC-0001` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `/erupt-api/code-img` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: GET `/erupt-api/code-img?mark=<x>&height=<large>` while increasing height.
- Root cause summary: The height value is not constrained to a normal captcha range and is passed to `new SpecCaptcha(150, height, 4)`, leading to huge `BufferedImage` allocation.
- Exploitation conditions: The anonymous captcha endpoint is exposed and does not cap height or total pixels.
- Static source: `GET /erupt-api/code-img?mark=...&height=...`
- Static sink: `EruptUserController.createCode -> new SpecCaptcha(150, height, 4) -> captcha.out(); EasyCaptcha SpecCaptcha.graphicsImage creates BufferedImage(width,height,TYPE_INT_RGB)`
- Attacker-controlled driver: `attacker-controlled height query parameter`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case ERUPT-APP-STATIC-0001 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `3` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/ERUPT-APP-STATIC-0001.log` |

Evidence summary:

```text
In the Erupt sample default H2 deployment, the anonymous `/erupt-api/code-img` endpoint lets the `height` parameter directly affect captcha image height. In the 1 GiB heap retest, very large height values triggered `BufferedImage` allocation and OOM.
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
| poc/ERUPT-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/ERUPT-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/ERUPT-APP-STATIC-0001/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/ERUPT-APP-STATIC-0001/attachments/static_finding.json | copied application static finding |
| poc/ERUPT-APP-STATIC-0001/attachments/ERUPT-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/ERUPT-APP-STATIC-0001.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
