# Security Advisory PoC: SMQTT long-topic subscription index can be exhausted by anonymous subscribes

## Summary

SMQTT's default anonymous subscribe path accepts many unique or long topic filters. In the 1 GiB heap retest, about 127k requests triggered target JVM OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `quickmsg__smqtt` |
| Local true-positive ID | `SMQTT-APP-STATIC-0003` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `protocol service on port 18833` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Use MQTT SUBSCRIBE to create many unique or long topic filters, continuously growing broker subscription indexes.
- Root cause summary: Subscription topic-index keys/nodes lack default global, per-client, or per-IP capacity limits.
- Exploitation conditions: Anonymous subscribe is allowed, subscription indexes are not globally bounded, and connection/rate is not externally limited.
- Static source: `MQTT PUBLISH with attacker-controlled distinct fixed topicName, retain=false is sufficient`
- Static sink: `PublishProtocol always calls topicRegistry.getSubscribesByTopic; FixedTopicFilter.getSubscribeByTopic uses topicChannels.computeIfAbsent(topic, ...)`
- Attacker-controlled driver: `distinct PUBLISH topicName cardinality`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case SMQTT-APP-STATIC-0003 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `127062` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/SMQTT-APP-STATIC-0003.log` |

Evidence summary:

```text
SMQTT's default anonymous subscribe path accepts many unique or long topic filters. In the 1 GiB heap retest, about 127k requests triggered target JVM OOM.
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
| poc/SMQTT-APP-STATIC-0003/attachments/source_record.json | binary truth record |
| poc/SMQTT-APP-STATIC-0003/attachments/evidence.json | normalized advisory evidence |
| poc/SMQTT-APP-STATIC-0003/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/SMQTT-APP-STATIC-0003/attachments/static_finding.json | copied application static finding |
| results/applications_dynamic_validation/p1/logs/SMQTT-APP-STATIC-0003.log | not copied; log is 33536166 bytes, above 8388608 byte attachment threshold |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
