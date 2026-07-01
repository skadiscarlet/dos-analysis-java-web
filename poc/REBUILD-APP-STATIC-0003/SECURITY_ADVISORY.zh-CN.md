# Security Advisory PoC：Rebuild API gateway 在签名校验前解析大 JSON body 导致 OOM

## 摘要

Rebuild 匿名 `/gw/api/system-time?appid=bad&sign=bad` 会在签名拒绝前读取并解析 raw JSON body。1GiB heap 复测中，约 24MiB body 的重复请求触发 OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `getrebuild__rebuild` |
| 本地真阳性 ID | `REBUILD-APP-STATIC-0003` |
| 动态批次 | `p1` |
| 动态状态 | `verified_oom` |
| 入口 | `/gw/api/system-time?appid=bad&sign=bad` |
| 权限前置 | 匿名或默认开放协议客户端 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向存在的 `/gw/api/system-time` API 名称 POST 大 JSON body，appid/sign 使用无效值。
- 根因摘要：`ApiGateway.buildBaseApiContext` 在验证 appid/sign 之前调用 `ServletUtils.getRequestString` 和 `JSON.parse`。
- 利用条件：匿名 API gateway path 暴露；API 名称存在；未由 body limit 或 JSON limit 拦截。
- 静态 source：`raw request body on /gw/api/** plus query appid/sign`
- 静态 sink：`ApiGateway.buildBaseApiContext calls ServletUtils.getRequestString(request) and JSON.parse(postData) before verfiy checks appid/sign/appSecret`
- 攻击者驱动变量：`attacker-controlled body byte volume, JSON nesting, and repeated requests to any existing API name`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p1_dynamic_validation.py --case REBUILD-APP-STATIC-0003 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `10` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p1/logs/REBUILD-APP-STATIC-0003.log` |

证据摘要：

```text
匿名 /gw/api/system-time 在签名校验前读取并解析 JSON body；未 OOM 则不提升。
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
| poc/REBUILD-APP-STATIC-0003/attachments/source_record.json | binary truth record |
| poc/REBUILD-APP-STATIC-0003/attachments/evidence.json | normalized advisory evidence |
| poc/REBUILD-APP-STATIC-0003/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/REBUILD-APP-STATIC-0003/attachments/static_finding.json | copied application static finding |
| poc/REBUILD-APP-STATIC-0003/attachments/REBUILD-APP-STATIC-0003.log.gz | gzip copy of results/applications_dynamic_validation/p1/logs/REBUILD-APP-STATIC-0003.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
