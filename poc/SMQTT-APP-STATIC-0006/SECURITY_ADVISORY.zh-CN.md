# Security Advisory PoC：SMQTT QoS2 半握手缓存 publish payload 可触发 OOM

## 摘要

SMQTT QoS2 PUBLISH 路径会在收到 PUBREL 前缓存 publish payload 和 retry ack 状态。1GiB heap 复测中，5 条连接、payload 约 1MiB 的半握手消息触发 OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `quickmsg__smqtt` |
| 本地真阳性 ID | `SMQTT-APP-STATIC-0006` |
| 动态批次 | `p1` |
| 动态状态 | `verified_oom` |
| 入口 | `protocol service on port 18836` |
| 权限前置 | 匿名或默认开放协议客户端 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：发送不同 packetId 的 QoS2 PUBLISH 后省略 PUBREL，用 PINGREQ 保持连接。
- 根因摘要：`MqttChannel.qos2MsgCache` 与 `TimeAckManager.ackMap` 缺少 per-connection inflight bytes/count 和超时释放。
- 利用条件：匿名 QoS2 publish 允许；半开放 QoS2 状态可保留；未设置 inflight quota。
- 静态 source：`MQTT PUBLISH with QoS2 using attacker-controlled packetId and payload, then omitting PUBREL`
- 静态 sink：`MqttChannel.qos2MsgCache.put(packetId, wrappedPublishMessage) and TimeAckManager.ackMap via RetryAck.start for PUBREC retries`
- 攻击者驱动变量：`QoS2 packetId count per connection, payload bytes, number of connections, and missing PUBREL acknowledgements`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case SMQTT-APP-STATIC-0006 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `970` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p1/logs/SMQTT-APP-STATIC-0006.log` |

证据摘要：

```text
java.lang.OutOfMemoryError
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
| poc/SMQTT-APP-STATIC-0006/attachments/source_record.json | binary truth record |
| poc/SMQTT-APP-STATIC-0006/attachments/evidence.json | normalized advisory evidence |
| poc/SMQTT-APP-STATIC-0006/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/SMQTT-APP-STATIC-0006/attachments/static_finding.json | copied application static finding |
| poc/SMQTT-APP-STATIC-0006/attachments/SMQTT-APP-STATIC-0006.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/SMQTT-APP-STATIC-0006.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
