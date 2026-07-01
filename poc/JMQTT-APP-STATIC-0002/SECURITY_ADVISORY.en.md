# Security Advisory PoC: JMQTT QoS2 half-handshake retained messages can trigger OOM

## Summary

JMQTT accepts anonymous MQTT clients by default. An attacker can send QoS2 PUBLISH packets with distinct packetIds, omit PUBREL after PUBREC, and keep the connection alive with PINGREQ, retaining DeviceMessage objects. In the 1 GiB heap retest, 2030 messages triggered OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `cicizz__jmqtt` |
| Local true-positive ID | `JMQTT-APP-STATIC-0002` |
| Dynamic batch | `p1` |
| Dynamic status | `verified_oom` |
| Entry | `protocol service on port 18842` |
| Required privilege | anonymous or default-open protocol client |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Send QoS2 PUBLISH packets with payload near the default maxMsgSize over the default MQTT TCP/WebSocket surface and keep QoS2 state half-open.
- Root cause summary: `MqttSession.qos2Receiving` retains packetId-to-DeviceMessage entries without an in-flight count/byte quota or timeout cleanup.
- Exploitation conditions: Anonymous MQTT connections are allowed, QoS2 is enabled, and the connection can be kept alive.
- Static source: `默认开放 MQTT/TCP 或 WebSocket 客户端发送 QoS2 PUBLISH，选择不同 packetId，并在收到 PUBREC 后不发送 PUBREL 或延迟发送`
- Static sink: `MqttSession.qos2Receiving ConcurrentHashMap；MQTTConnection.processQos2 构造 DeviceMessage 并调用 receivedPublishQos2(originPacketId, deviceMessage)`
- Attacker-controlled driver: `每连接唯一 QoS2 packetId 数量、payload 字节数、并发连接数、保持连接活跃的 PINGREQ/keepalive`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case JMQTT-APP-STATIC-0002 --min-heap 1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `java.lang.OutOfMemoryError` |
| Heap / memory evidence | `1g` |
| Requests sent | `2030` |
| Strict 1 GiB evidence | `1g` |
| Original log path | `results/applications_dynamic_validation/p1/logs/JMQTT-APP-STATIC-0002.log` |

Evidence summary:

```text
JMQTT accepts anonymous MQTT clients by default. An attacker can send QoS2 PUBLISH packets with distinct packetIds, omit PUBREL after PUBREC, and keep the connection alive with PINGREQ, retaining DeviceMessage objects. In the 1 GiB heap retest, 2030 messages triggered OOM.
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
| poc/JMQTT-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/JMQTT-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/JMQTT-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/JMQTT-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/JMQTT-APP-STATIC-0002/attachments/JMQTT-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/JMQTT-APP-STATIC-0002.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
