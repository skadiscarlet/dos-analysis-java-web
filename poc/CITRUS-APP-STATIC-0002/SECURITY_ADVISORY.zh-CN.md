# Security Advisory PoC：Citrus 匿名认证 JSON body buffering 可触发 JVM OOM

## 摘要

Citrus `/rest/authenticate` 匿名认证路径会缓冲/解析请求体。1GiB heap 复测中，约 20MiB JSON body 的并发/重复提交触发目标 JVM OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `yiuman__citrus` |
| 本地真阳性 ID | `CITRUS-APP-STATIC-0002` |
| 动态批次 | `p1` |
| 动态状态 | `verified_oom` |
| 入口 | `/rest/authenticate` |
| 权限前置 | 匿名或默认开放协议客户端 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 `/rest/authenticate` 发送大 JSON body，保持普通匿名认证请求形态。
- 根因摘要：认证入口在拒绝前完整物化请求体和 JSON 结构，默认未对普通 JSON body 设置足够低的上限。
- 利用条件：匿名认证入口暴露；普通 JSON body 未被 server/proxy 体积限制拦截。
- 静态 source：`permitAll authenticate endpoint request body`
- 静态 sink：`RequestWrapperFilter.RequestWrapper reads full body; AuthenticateProcessorImpl creates JsonServletRequestWrapper which reads String/byte[] and Jackson Map`
- 攻击者驱动变量：`request body byte volume, JSON object/key count, parser work`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case CITRUS-APP-STATIC-0002 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `19` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p1/logs/CITRUS-APP-STATIC-0002.log` |

证据摘要：

```text
完整 MySQL/Redis 环境启动，复用 Citrus P0 的 MDA classpath workaround；目标为匿名认证 JSON body buffering/parsing。
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
| poc/CITRUS-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/CITRUS-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/CITRUS-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/CITRUS-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/CITRUS-APP-STATIC-0002/attachments/CITRUS-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/CITRUS-APP-STATIC-0002.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
