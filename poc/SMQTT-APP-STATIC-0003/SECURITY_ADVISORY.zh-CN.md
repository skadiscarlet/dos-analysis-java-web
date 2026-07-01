# Security Advisory PoC：SMQTT 长 topic 订阅索引可由匿名订阅触发 OOM

## 摘要

SMQTT 默认匿名订阅路径可接收大量唯一或超长 topic filter。1GiB heap 复测中，约 127k 次请求触发目标 JVM OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `quickmsg__smqtt` |
| 本地真阳性 ID | `SMQTT-APP-STATIC-0003` |
| 动态批次 | `p1` |
| 动态状态 | `verified_oom` |
| 入口 | `protocol service on port 18833` |
| 权限前置 | 匿名或默认开放协议客户端 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：通过 MQTT SUBSCRIBE 创建大量唯一/长 topic filter，持续增长 broker 订阅索引。
- 根因摘要：订阅 topic 索引的 key/节点数量缺少默认全局、per-client 或 per-IP 容量上限。
- 利用条件：匿名 subscribe 允许；订阅索引未配置总量限制；连接/速率未被外部限制。
- 静态 source：`MQTT PUBLISH with attacker-controlled distinct fixed topicName, retain=false is sufficient`
- 静态 sink：`PublishProtocol always calls topicRegistry.getSubscribesByTopic; FixedTopicFilter.getSubscribeByTopic uses topicChannels.computeIfAbsent(topic, ...)`
- 攻击者驱动变量：`distinct PUBLISH topicName cardinality`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case SMQTT-APP-STATIC-0003 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `127062` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p1/logs/SMQTT-APP-STATIC-0003.log` |

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
| poc/SMQTT-APP-STATIC-0003/attachments/source_record.json | binary truth record |
| poc/SMQTT-APP-STATIC-0003/attachments/evidence.json | normalized advisory evidence |
| poc/SMQTT-APP-STATIC-0003/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/SMQTT-APP-STATIC-0003/attachments/static_finding.json | copied application static finding |
| results/applications_dynamic_validation/p1/logs/SMQTT-APP-STATIC-0003.log | not copied; log is 33536166 bytes, above 8388608 byte attachment threshold |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
