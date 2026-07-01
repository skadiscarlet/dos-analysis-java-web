# Security Advisory PoC：Apache Druid Router Avatica protobuf 大请求导致 JVM OOM

## 摘要

默认未启用认证的 Druid Router Avatica protobuf endpoint 可被匿名客户端提交大型合法 protobuf POST。1GiB Router heap 复测中，128MiB 请求后服务仍运行，256MiB 请求触发 Java heap OOM、Router exit 3 和健康检查连接拒绝。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `apache/druid` |
| 本地真阳性 ID | `apache__druid-DRUID-APP-STATIC-0002` |
| 动态批次 | `new` |
| 动态状态 | `confirmed_oom` |
| 入口 | `POST /druid/v2/sql/avatica-protobuf/ through Router port 8888` |
| 权限前置 | 匿名 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 `/druid/v2/sql/avatica-protobuf/` 发送 `application/x-protobuf` Avatica OpenConnectionRequest，并附带大型 protobuf unknown field padding。
- 根因摘要：Router 转发路径把 Avatica 请求完整读入 `byte[]` 并挂到 request attribute，缺少默认 body/bytes quota。
- 利用条件：匿名可达 Router Avatica endpoint；无前置账号；未由代理、认证或 body limit 拦截。
- 静态 source：`POST /druid/v2/sql/avatica-protobuf through Router.`
- 静态 sink：`AsyncQueryForwardingServlet.service reads the full InputStream into byte[] requestBytes and stores it as AVATICA_QUERY_ATTRIBUTE for proxying.`
- 攻击者驱动变量：`Avatica protobuf request body byte volume; repeated concurrent requests retain byte arrays during broker selection/proxy forwarding.`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002
docker compose -p druid_avatica_case_1g -f docker-compose.yml up -d postgres zookeeper coordinator broker router
python3 probe.py --case-dir "$PWD" --compose-project druid_avatica_case_1g --compose-file "$PWD/docker-compose.yml" --wait-only --ready-timeout 300
python3 probe.py --case-dir "$PWD" --compose-project druid_avatica_case_1g --compose-file "$PWD/docker-compose.yml" --sizes 134217728,268435456,536870912,805306368 --request-timeout 300 --ready-timeout 60
docker compose -p druid_avatica_case_1g -f docker-compose.yml down -v
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Java heap space` |
| 堆/内存口径 | `Druid Router DRUID_XMS=1g and DRUID_XMX=1g; Docker HostConfig.Memory=0, no container memory limit` |
| 请求数 | `2` |
| 1GiB 严格证据 | `druid_xmx=1g` |
| 原始日志路径 | `logs/router_after_1g_oom.log` |

证据摘要：

```text
默认未启用认证的 Druid Router Avatica protobuf endpoint 可由匿名客户端用大型合法 protobuf POST 触发 Router JVM heap OOM；1GiB Router heap 复测中，128MiB 请求后 Router 仍运行，256MiB 请求导致 Java heap OOM、Router exit 3 和 HTTP health connection refused。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- HTTP request body size limit or reverse proxy limit below the OOM threshold
- Authentication/authorization preventing anonymous access to /druid/v2/sql/avatica-protobuf/
- Network isolation of Router or JDBC endpoint
- Rate limiting or per-client quota on large POST bodies
- Higher Router heap may raise the threshold but does not remove the unbounded full-body buffering behavior

不受影响或风险显著降低的情况：

- Router is not exposed to low-trust clients
- Avatica protobuf endpoint is blocked or protected by authentication
- A front proxy or server setting rejects large request bodies before they reach Router
- Druid deployment does not route JDBC/Avatica traffic through Router

## 附件

| Field | Value |
| --- | --- |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/probe.py |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/docker-compose.yml |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/start_commands.sh |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/case_plan.json |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/environment.md |
| poc/apache__druid-DRUID-APP-STATIC-0002/attachments/apache__druid-DRUID-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/logs/router_after_1g_oom.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
