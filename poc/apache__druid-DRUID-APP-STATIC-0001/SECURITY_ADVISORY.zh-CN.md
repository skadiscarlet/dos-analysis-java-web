# Security Advisory PoC：Apache Druid Router SQL 请求体无上限导致 JVM OOM

## 摘要

默认未启用认证的 Druid Router `POST /druid/v2/sql/` 会在处理 SQL 请求前完整物化攻击者控制的请求体。1GiB Router heap 复测中，单个 512MiB `text/plain` SQL body 触发 `OutOfMemoryError: Java heap space` 并导致 Router 退出。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `apache/druid` |
| 本地真阳性 ID | `apache__druid-DRUID-APP-STATIC-0001` |
| 动态批次 | `new` |
| 动态状态 | `confirmed_oom` |
| 入口 | `POST /druid/v2/sql/ on Druid Router HTTP port 8888` |
| 权限前置 | 匿名 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 Router SQL endpoint 顺序发送逐步增大的 `text/plain` SQL 请求体，失败样本为 512MiB body。
- 根因摘要：`SqlQuery.from` 路径使用 `IOUtils.toByteArray(request.getInputStream())` 并构造完整字符串，缺少默认请求体大小上限。
- 利用条件：匿名可达 Router；无前置账号；上游代理或 Druid 配置未在阈值以下拒绝大请求体。
- 静态 source：`POST /druid/v2/sql/ with Content-Type text/plain or application/x-www-form-urlencoded; Router path also calls SqlQuery.from(HttpServletRequest,ObjectMapper).`
- 静态 sink：`SqlQuery.from rawQueryExtractor uses IOUtils.toByteArray(request.getInputStream()) and constructs a String before trim/decode.`
- 攻击者驱动变量：`HTTP request body byte volume; concurrent body submissions multiply live byte[]/String pressure.`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001
docker compose -p druiddos_apache_druid up -d
./probe.py --max-size 536870912 --size-steps 1048576,8388608,33554432,67108864,134217728,268435456,536870912 --content-types text/plain --concurrency 1 --timeout 360 --chunk-size 1048576 --stop-on-failure
docker compose -p druiddos_apache_druid down -v
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Java heap space` |
| 堆/内存口径 | `Druid Router DRUID_XMS=1g and DRUID_XMX=1g; no Docker mem_limit set in the case compose` |
| 请求数 | `7` |
| 1GiB 严格证据 | `druid_xmx=1g` |
| 原始日志路径 | `logs/compose_all_reinforce.log` |

证据摘要：

```text
官方 Druid Docker quickstart 派生部署中，Router /druid/v2/sql/ 匿名可达；在 DRUID_XMS=1g / DRUID_XMX=1g 的严格补测下，单个 512MiB text/plain SQL body 触发 Router JVM `OutOfMemoryError: Java heap space` 并退出。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- Default quickstart did not reject the probed text/plain SQL body before Router heap OOM.
- Reverse proxy, Jetty, or Druid-level request body limits below the failure threshold would block this exact trigger.
- Authentication, authorization, per-client rate limits, or network isolation of Router reduce external reachability.
- Different Druid versions or a fix that streams or caps raw SQL bodies may change exploitability.

不受影响或风险显著降低的情况：

- The Router /druid/v2/sql/ endpoint is not exposed to low-trust clients.
- Requests with text/plain or form-urlencoded SQL bodies are capped below the memory-pressure threshold.
- The deployment requires authenticated roles not available to the attacker.
- A front proxy rejects large bodies before they reach the Druid JVM.

## 附件

| Field | Value |
| --- | --- |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/probe.py |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/docker-compose.yml |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/case_plan.json |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/environment.md |
| poc/apache__druid-DRUID-APP-STATIC-0001/attachments/apache__druid-DRUID-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/logs/compose_all_reinforce.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
