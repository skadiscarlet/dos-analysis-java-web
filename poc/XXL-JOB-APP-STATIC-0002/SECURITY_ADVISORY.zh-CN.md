# Security Advisory PoC：XXL-JOB executor trigger 参数队列可用默认 token 触发 OOM

## 摘要

默认 executor 9999 端口和 `default_token` 场景下，攻击者可通过 `/trigger` 提交大量带大 executorParams 的任务触发 retained queue/线程状态增长。1GiB heap 复测中 1025 次触发导致 OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `xuxueli__xxl-job` |
| 本地真阳性 ID | `XXL-JOB-APP-STATIC-0002` |
| 动态批次 | `p0` |
| 动态状态 | `verified_oom` |
| 入口 | `protocol service on port 9999` |
| 权限前置 | 匿名或默认开放协议客户端 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 executor `/trigger` POST 默认 token header，使用唯一 jobId 或重复触发并携带大 executorParams。
- 根因摘要：executor 任务线程/队列保留 executorParams，默认 active job/thread 和排队参数总字节缺少硬上限。
- 利用条件：executor 9999 暴露；默认 access token 未修改或攻击者持有 token；无触发速率和参数大小限制。
- 静态 source：`external POST :9999/trigger for the same jobId with unique logId and payload fields`
- 静态 sink：`JobThread.pushTriggerQueue adds logId to triggerLogIdSet and TriggerRequest to an unbounded LinkedBlockingQueue`
- 攻击者驱动变量：`failed or slow trigger processing versus request rate; unique logId and executorParams/glueSource field size`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case XXL-JOB-APP-STATIC-0002 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `1025` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p0/logs/XXL-JOB-APP-STATIC-0002.log` |

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
| poc/XXL-JOB-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/XXL-JOB-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/XXL-JOB-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/XXL-JOB-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/XXL-JOB-APP-STATIC-0002/attachments/XXL-JOB-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/XXL-JOB-APP-STATIC-0002.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
