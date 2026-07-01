# Security Advisory PoC: SMQTT retained MQTT message map can be exhausted by anonymous retained publishes

## Summary

SMQTT accepts anonymous MQTT clients by default. Large retained PUBLISH messages with distinct topics are stored in the `retainMessages` map; in the 1 GiB heap retest, 260 messages triggered OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `quickmsg__smqtt` |
| Local true-positive ID | `SMQTT-APP-STATIC-0002` |
| Dynamic batch | `p0` |
| Dynamic status | `verified_oom` |
| Entry | `protocol service on port 1883` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Connect to the default MQTT TCP 1883 port and send retained PUBLISH messages with unique topics and large payloads.
- Root cause summary: Individual messages are capped by messageMaxSize, but retained topic count and aggregate retained bytes have no default bound.
- Exploitation conditions: Anonymous publish is allowed, retained messages are enabled, and no retained count/byte quota is enforced.
- Static source: `MQTT PUBLISH with retain=true, attacker-controlled distinct topicName and payload`
- Static sink: `PublishProtocol.filterRetainMessage -> DefaultMessageRegistry.retainMessages.put(topic, RetainMessage)`
- Attacker-controlled driver: `distinct retained topic cardinality and retained payload bytes up to the configured MQTT frame limit`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case SMQTT-APP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `260` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p0/logs/SMQTT-APP-STATIC-0002.log` |

Evidence summary:

```text
SMQTT accepts anonymous MQTT clients by default. Large retained PUBLISH messages with distinct topics are stored in the `retainMessages` map; in the 1 GiB heap retest, 260 messages triggered OOM.
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
| poc/SMQTT-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/SMQTT-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/SMQTT-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/SMQTT-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/SMQTT-APP-STATIC-0002/attachments/SMQTT-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/SMQTT-APP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
