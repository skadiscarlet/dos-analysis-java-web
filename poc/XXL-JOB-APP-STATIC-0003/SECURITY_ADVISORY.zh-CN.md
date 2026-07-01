# Security Advisory PoC：XXL-JOB GLUE_GROOVY 唯一 jobId 可造成线程耗尽

## 摘要

XXL-JOB default-token GLUE_GROOVY 路径使用唯一 jobId 与阻塞型 glueSource 创建大量 JobThread。1GiB heap 复测中 780 次触发导致 native thread exhaustion/可用性失败，作为确认资源耗尽真阳性。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `xuxueli__xxl-job` |
| 本地真阳性 ID | `XXL-JOB-APP-STATIC-0003` |
| 动态批次 | `p1` |
| 动态状态 | `confirmed_thread_exhaustion` |
| 入口 | `protocol service on port 9999` |
| 权限前置 | 低权限账号或默认 token/API key |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 executor `/trigger` 发送默认 token，glueType=GLUE_GROOVY，使用唯一 jobId 和阻塞 glueSource。
- 根因摘要：`jobThreadRepository` 按 jobId 创建并保留 JobThread，默认无 active JobThread 上限，阻塞任务可快速耗尽 native threads。
- 利用条件：executor 9999 暴露；默认 token 可用；GLUE_GROOVY 执行路径可达；未限制 jobId/thread 数。
- 静态 source：`external POST :9999/trigger with glueType=GLUE_GROOVY, unique glueSource and default token/appname`
- 静态 sink：`GlueFactory.getCodeSourceClass parses Groovy source and stores Class<?> in CLASS_CACHE by codeSource MD5`
- 攻击者驱动变量：`unique compilable glueSource contents and size`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case XXL-JOB-APP-STATIC-0003 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `780` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p1/logs/XXL-JOB-APP-STATIC-0003.log` |

证据摘要：

```text
XXL-JOB default-token GLUE_GROOVY 使用唯一 jobId 与阻塞型 glueSource 创建大量 JobThread；以线程耗尽/可用性失败为确认信号，不限于 Java heap OOM。
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
| poc/XXL-JOB-APP-STATIC-0003/attachments/source_record.json | binary truth record |
| poc/XXL-JOB-APP-STATIC-0003/attachments/evidence.json | normalized advisory evidence |
| poc/XXL-JOB-APP-STATIC-0003/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/XXL-JOB-APP-STATIC-0003/attachments/static_finding.json | copied application static finding |
| poc/XXL-JOB-APP-STATIC-0003/attachments/XXL-JOB-APP-STATIC-0003.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/XXL-JOB-APP-STATIC-0003.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
