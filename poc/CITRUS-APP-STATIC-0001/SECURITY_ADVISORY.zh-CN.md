# Security Advisory PoC：Citrus captcha session verification store 可导致 HttpSession 堆耗尽

## 摘要

完整 MySQL/Redis 环境启动并使用 session verification store 时，匿名 `/rest/verify/captcha` 请求会持续创建/保留 session captcha 状态。1GiB heap 复测中约 48.9k 次请求触发目标 JVM OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `yiuman__citrus` |
| 本地真阳性 ID | `CITRUS-APP-STATIC-0001` |
| 动态批次 | `p0` |
| 动态状态 | `verified_oom` |
| 入口 | `/rest/verify/captcha` |
| 权限前置 | 匿名或默认开放协议客户端 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：重复请求 `/rest/verify/captcha`，不复用 cookie，使服务端创建大量带验证码状态的 HttpSession。
- 根因摘要：验证码状态写入 HttpSession，默认未观察到足够的 session 数量、来源或总字节配额。
- 利用条件：验证码功能使用 session store；入口匿名可达；session 创建/保留未被网关或应用配额限制。
- 静态 source：`permitAll verification endpoint path variable type=caption`
- 静态 sink：`CaptchaProcessor.send -> SessionVerificationRepository.save -> request.getSession().setAttribute(SESSION_VERIFY_ID, Captcha)`
- 攻击者驱动变量：`number of fresh sessions created by requests that omit or vary the session cookie`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case CITRUS-APP-STATIC-0001 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `48950` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p0/logs/CITRUS-APP-STATIC-0001.log` |

证据摘要：

```text
完整 MySQL/Redis 环境启动，显式使用 session verification store 触发 HttpSession-retained captcha 路径。
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
| poc/CITRUS-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/CITRUS-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/CITRUS-APP-STATIC-0001/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/CITRUS-APP-STATIC-0001/attachments/static_finding.json | copied application static finding |
| poc/CITRUS-APP-STATIC-0001/attachments/CITRUS-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/CITRUS-APP-STATIC-0001.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
