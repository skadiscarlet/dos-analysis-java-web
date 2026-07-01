# Security Advisory PoC：Erupt operation-log filter 在鉴权前复制 JSON body 导致 OOM

## 摘要

匿名 POST `/erupt-api/data/table/EruptUser` 时，operation-log filter 会在权限拒绝前复制 JSON body。1GiB heap 复测中，约 36MiB body 的重复请求触发 Java heap OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `erupts__erupt` |
| 本地真阳性 ID | `ERUPT-APP-STATIC-0002` |
| 动态批次 | `p1` |
| 动态状态 | `verified_oom` |
| 入口 | `/erupt-api/data/table/EruptUser` |
| 权限前置 | 匿名或默认开放协议客户端 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 `/erupt-api/data/table/EruptUser` POST 大 JSON body，即使最终返回 401，也会先经过 body wrapper。
- 根因摘要：`EruptRequestWrapper` 在 filter 中读取完整 JSON body，并保留 String/byte[] 多份副本，默认无 body 记录长度上限。
- 利用条件：匿名 `/erupt-api/*` JSON path 可达；operation-log filter 启用；未由网关限制 body。
- 静态 source：`Any /erupt-api/* request with Content-Type exactly application/json and attacker-controlled body`
- 静态 sink：`HttpServletRequestFilter.EruptRequestWrapper reads the full request body with StreamUtils.copyToString and later duplicates it via body.getBytes(); RequestBodyTL.remove is only reached in OperationService for @EruptRecordOperate handlers`
- 攻击者驱动变量：`request body byte volume, concurrent request count, servlet worker thread count`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case ERUPT-APP-STATIC-0002 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `13` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p1/logs/ERUPT-APP-STATIC-0002.log` |

证据摘要：

```text
匿名 POST /erupt-api/data/table/EruptUser JSON body 先经过 operation-log filter 复制；未 OOM 则不提升。
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
| poc/ERUPT-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/ERUPT-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/ERUPT-APP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/ERUPT-APP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/ERUPT-APP-STATIC-0002/attachments/ERUPT-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/ERUPT-APP-STATIC-0002.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
