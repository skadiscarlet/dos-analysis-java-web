# Security Advisory PoC：JMQTT QoS2 半握手保留消息可触发 OOM

## 摘要

JMQTT 默认匿名 MQTT 客户端可发送 QoS2 PUBLISH。攻击者选择不同 packetId，收到 PUBREC 后不发送 PUBREL 并用 PINGREQ 保活，可保留 DeviceMessage。1GiB heap 复测中 2030 条触发 OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `cicizz__jmqtt` |
| 本地真阳性 ID | `JMQTT-APP-STATIC-0002` |
| 动态批次 | `p1` |
| 动态状态 | `verified_oom` |
| 入口 | `protocol service on port 18842` |
| 权限前置 | 匿名或默认开放协议客户端 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：默认 MQTT TCP/WebSocket 上发送 payload 接近默认 maxMsgSize 的 QoS2 PUBLISH，保持半开放 QoS2 状态。
- 根因摘要：`MqttSession.qos2Receiving` 保留 packetId 到 DeviceMessage 的映射，缺少 inflight count/bytes quota 和超时清理。
- 利用条件：匿名 MQTT 连接可用；QoS2 启用；连接可通过 keepalive 维持。
- 静态 source：`默认开放 MQTT/TCP 或 WebSocket 客户端发送 QoS2 PUBLISH，选择不同 packetId，并在收到 PUBREC 后不发送 PUBREL 或延迟发送`
- 静态 sink：`MqttSession.qos2Receiving ConcurrentHashMap；MQTTConnection.processQos2 构造 DeviceMessage 并调用 receivedPublishQos2(originPacketId, deviceMessage)`
- 攻击者驱动变量：`每连接唯一 QoS2 packetId 数量、payload 字节数、并发连接数、保持连接活跃的 PINGREQ/keepalive`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case JMQTT-APP-STATIC-0002 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `2030` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p1/logs/JMQTT-APP-STATIC-0002.log` |

证据摘要：

```text
JMQTT 匿名 QoS2 PUBLISH 半握手，payload 保持在默认 maxMsgSize 512KiB 内，不发送 PUBREL 并用 PINGREQ 保活；只以目标 JVM OOM 为真阳。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- None recorded.

不受影响或风险显著降低的情况：

- None recorded.

## 附件

| Field | Value |
| --- | --- |
| poc/JMQTT-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/JMQTT-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/JMQTT-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/JMQTT-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/JMQTT-APP-STATIC-0002/attachments/JMQTT-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/JMQTT-APP-STATIC-0002.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
