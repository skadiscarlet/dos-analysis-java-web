# Security Advisory PoC：ThingsBoard device telemetry chunked JSON 在认证失败前可触发 OOM

## 摘要

官方 ThingsBoard tb-node 单节点部署中，HTTP device telemetry path 在认证结果返回前读取并绑定 chunked JSON body。-Xmx1024m、2GiB 容器复测中，单个 512MiB timeseries-large-value 请求触发 Java heap OOM 并返回 HTTP 500。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `thingsboard/thingsboard` |
| 本地真阳性 ID | `thingsboard__thingsboard-TB-APP-STATIC-0001` |
| 动态批次 | `new` |
| 动态状态 | `confirmed_oom` |
| 入口 | `POST /api/v1/{deviceToken}/telemetry` |
| 权限前置 | 匿名 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 `/api/v1/{deviceToken}/telemetry` 发送无 Content-Length 的 chunked JSON，其中单个字符串值非常大。
- 根因摘要：Spring `@RequestBody String` 和后续 JSON parser 在认证失败响应前完整物化请求体，默认 Content-Length 检查不能约束无 Content-Length chunked 请求。
- 利用条件：HTTP device transport 暴露；chunked body 未被网关/容器提前限制；无需有效 device token 即可触发 body binding。
- 静态 source：`Device HTTP transport POST bodies under /api/v1/{deviceToken}/telemetry and /api/v1/{deviceToken}/attributes.`
- 静态 sink：`Spring @RequestBody String followed by JsonParser.parseString and JsonConverter conversion in DeviceApiController.`
- 攻击者驱动变量：`Body byte volume and JSON key/value or timestamp-array count; especially requests without a positive Content-Length.`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001
docker compose -p tb-dos-thingsboard-static-0001 up -d postgres
docker compose -p tb-dos-thingsboard-static-0001 run --rm -e INSTALL_TB=true -e LOAD_DEMO=false -e JAVA_OPTS='-Xms512m -Xmx1024m -Xss384k' tb-node
docker compose -p tb-dos-thingsboard-static-0001 up -d tb-node
./probe.py --token <token-shaped-path-segment> --endpoint telemetry --payload-mode timeseries-large-value --sizes-mib 256,512 --timeout 240 --chunk-bytes 65536 --out logs/probe_results_reinforce_telemetry_large.jsonl
docker compose -p tb-dos-thingsboard-static-0001 down -v
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Java heap space` |
| 堆/内存口径 | `ThingsBoard tb-node JAVA_OPTS=-Xms512m -Xmx1024m -Xss384k; Docker compose mem_limit=2g` |
| 请求数 | `2` |
| 1GiB 严格证据 | `mem_limit=2g` |
| 原始日志路径 | `logs/probe_results_reinforce_telemetry_large.jsonl` |

证据摘要：

```text
官方 ThingsBoard tb-node 单节点部署中，HTTP device telemetry path 会在认证结果返回前读取并绑定 chunked JSON body；在 -Xmx1024m / 2g 容器补测下，单个 512MiB timeseries-large-value telemetry 请求触发目标 JVM `OutOfMemoryError: Java heap space` 并返回 HTTP 500。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- Reverse proxy, servlet container, or Spring request limits that reject chunked/no-Content-Length bodies before controller binding mitigate this path.
- A lower ThingsBoard HTTP transport max payload enforced independently of Content-Length would mitigate this path.
- JSON string length/body complexity limits before @RequestBody String materialization would mitigate this path.
- Authentication alone is insufficient if request body binding precedes token rejection for this endpoint shape.

不受影响或风险显著降低的情况：

- HTTP device transport is not exposed to low-trust clients.
- Chunked request bodies without Content-Length are rejected or capped before Spring binds @RequestBody String.
- Telemetry JSON body size/string length is bounded before JsonParser.parseString and JsonConverter processing.

## 附件

| Field | Value |
| --- | --- |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/probe.py |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/docker-compose.yml |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/start_commands.sh |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/case_plan.json |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/environment.md |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0001/attachments/thingsboard__thingsboard-TB-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/logs/probe_results_reinforce_telemetry_large.jsonl |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
