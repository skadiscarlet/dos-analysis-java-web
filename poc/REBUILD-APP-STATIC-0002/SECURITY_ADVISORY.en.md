# Security Advisory PoC: Rebuild anonymous barcode rendering can exhaust heap through text length

## Summary

Rebuild anonymous `/commons/barcode/render` renders a Code128 barcode from request text. In the 1 GiB heap retest, long text values triggered large image/encoding allocations and OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `getrebuild__rebuild` |
| Local true-positive ID | `REBUILD-APP-STATIC-0002` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `/commons/barcode/render` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: GET or POST `/commons/barcode/render` with progressively larger text parameters.
- Root cause summary: Barcode rendering lacks a sufficiently low default bound on text length, output pixels, or encoding complexity before allocation.
- Exploitation conditions: The anonymous barcode endpoint is exposed, and request-line/header limits still permit the triggering length.
- Static source: `anonymous query parameters t and w`
- Static sink: `BarCodeSupport.createBarCodeImage computes Code128 auto width from new Code128Writer().encode(content).length and then calls MultiFormatWriter.encode, followed by MatrixToImageWriter.toBufferedImage`
- Attacker-controlled driver: `attacker-controlled content length and height parameter; width is recomputed from encoded content length after the fixed 1200 width cap, so long t can drive large matrix/image allocation`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case REBUILD-APP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `3` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/REBUILD-APP-STATIC-0002.log` |

Evidence summary:

```text
Rebuild anonymous `/commons/barcode/render` renders a Code128 barcode from request text. In the 1 GiB heap retest, long text values triggered large image/encoding allocations and OOM.
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
| poc/REBUILD-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/REBUILD-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/REBUILD-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/REBUILD-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/REBUILD-APP-STATIC-0002/attachments/REBUILD-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/REBUILD-APP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
