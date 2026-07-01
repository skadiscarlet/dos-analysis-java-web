# Security Advisory PoC: SMQTT QoS2 half-handshake publish cache can exhaust heap

## Summary

SMQTT's QoS2 PUBLISH path caches publish payloads and retry-ack state until PUBREL is received. In the 1 GiB heap retest, half-handshake messages across five connections with roughly 1 MiB payloads triggered OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `quickmsg__smqtt` |
| Local true-positive ID | `SMQTT-APP-STATIC-0006` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `protocol service on port 18836` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Send QoS2 PUBLISH packets with distinct packetIds, omit PUBREL, and keep connections alive with PINGREQ.
- Root cause summary: `MqttChannel.qos2MsgCache` and `TimeAckManager.ackMap` lack per-connection in-flight byte/count limits and timeout-based release.
- Exploitation conditions: Anonymous QoS2 publish is allowed, half-open QoS2 state is retained, and no in-flight quota is enforced.
- Static source: `MQTT PUBLISH with QoS2 using attacker-controlled packetId and payload, then omitting PUBREL`
- Static sink: `MqttChannel.qos2MsgCache.put(packetId, wrappedPublishMessage) and TimeAckManager.ackMap via RetryAck.start for PUBREC retries`
- Attacker-controlled driver: `QoS2 packetId count per connection, payload bytes, number of connections, and missing PUBREL acknowledgements`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case SMQTT-APP-STATIC-0006 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `970` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/SMQTT-APP-STATIC-0006.log` |

Evidence summary:

```text
SMQTT's QoS2 PUBLISH path caches publish payloads and retry-ack state until PUBREL is received. In the 1 GiB heap retest, half-handshake messages across five connections with roughly 1 MiB payloads triggered OOM.
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
| poc/SMQTT-APP-STATIC-0006/attachments/source_record.json | binary truth record |
| poc/SMQTT-APP-STATIC-0006/attachments/evidence.json | normalized advisory evidence |
| poc/SMQTT-APP-STATIC-0006/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/SMQTT-APP-STATIC-0006/attachments/static_finding.json | copied application static finding |
| poc/SMQTT-APP-STATIC-0006/attachments/SMQTT-APP-STATIC-0006.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/SMQTT-APP-STATIC-0006.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
