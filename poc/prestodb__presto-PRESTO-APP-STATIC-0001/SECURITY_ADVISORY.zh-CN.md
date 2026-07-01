# Security Advisory PoC：Presto /v1/statement 未轮询查询保留导致默认 1GiB heap OOM

## 摘要

默认官方 Presto coordinator 无认证暴露 `/v1/statement` 时，匿名客户端连续提交约 700KiB SQL 且不轮询返回的 `nextUri`，会线性保留 Query/session 对象并触发默认 1GiB heap OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `prestodb/presto` |
| 本地真阳性 ID | `prestodb__presto-PRESTO-APP-STATIC-0001` |
| 动态批次 | `new` |
| 动态状态 | `confirmed_oom` |
| 入口 | `POST /v1/statement` |
| 权限前置 | 匿名 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：POST `/v1/statement`，带 `X-Presto-User`，提交唯一 padded SQL，并故意不访问返回的 queued `nextUri`。
- 根因摘要：queued statement 被放入 `queries` map 并保留请求 SQL 与 session/header 状态，未轮询或未完成查询缺少有效默认保留上限。
- 利用条件：`/v1/statement` 匿名或低信任可达；未启用 HTTP auth；未由代理限制大 SQL 或提交速率。
- 静态 source：`External POST /v1/statement with SQL body and X-Presto-* headers`
- 静态 sink：`presto-main/src/main/java/com/facebook/presto/server/protocol/QueuedStatementResource.java:269 queries.put(query.getQueryId(), query)`
- 攻击者驱动变量：`number of distinct POST submissions that do not poll their queued nextUri; retained bytes include SQL body up to dispatch-time maxQueryLength and parsed session/header state`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001
docker run -d --name dos-presto-prestodb-presto-static-0001 --memory=2g --memory-swap=2g -p 127.0.0.1:18080:8080 prestodb/presto:0.298.1
curl -fsS http://127.0.0.1:18080/v1/info
./probe.py
docker rm -f -v dos-presto-prestodb-presto-static-0001
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError` |
| 堆/内存口径 | `Presto image default -Xmx1G; Docker harness --memory=2g --memory-swap=2g` |
| 请求数 | `974` |
| 1GiB 严格证据 | `-xmx1g` |
| 原始日志路径 | `logs/container_final.log` |

证据摘要：

```text
默认官方 Presto coordinator 无认证暴露 /v1/statement 时，匿名 HTTP 客户端带 X-Presto-User 连续提交大量约 700KiB SQL 且不轮询 nextUri，可线性保留 Query/session 对象并触发默认 1GiB heap OOM。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- Default query.max-length is 1,000,000 characters, but the observed abandoned-initial-POST path retains the statement before dispatch-time maxQueryLength enforcement.
- The probe did not observe a pre-dispatch request-body cap below 700000 bytes.
- Enabling HTTP authentication or putting /v1/statement behind trusted network access changes attacker reachability.
- Reverse-proxy body-size, rate, or per-client request quotas can raise or remove exploitability.
- A server-side TTL/quota for unpolled queued statements would mitigate this retention path.

不受影响或风险显著降低的情况：

- /v1/statement is not reachable by anonymous or low-trust clients.
- HTTP authentication is enabled and only trusted users can submit statements.
- A proxy or gateway rejects large or high-rate statement submissions before Presto allocates Query state.
- The implementation removes or bounds unpolled queued statements independently of query dispatch completion.

## 附件

| Field | Value |
| --- | --- |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/probe.py |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/start_commands.sh |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/case_plan.json |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/environment.md |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/prestodb__presto-PRESTO-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/logs/container_final.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
