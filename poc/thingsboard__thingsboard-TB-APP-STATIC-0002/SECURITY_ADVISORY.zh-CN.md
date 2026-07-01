# Security Advisory PoC：ThingsBoard authenticated REST attributes chunked body 绕过默认大小检查导致 OOM

## 摘要

官方单容器部署中，具备 TENANT_ADMIN 等低权限写设备属性能力的客户端，可用无 Content-Length 的 chunked attributes POST 绕过默认 `/api/**` 16MiB Content-Length 检查。1.5GiB heap 复测中，256MiB body 触发 Java heap OOM 并导致 HTTP 不可用。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `thingsboard/thingsboard` |
| 本地真阳性 ID | `thingsboard__thingsboard-TB-APP-STATIC-0002` |
| 动态批次 | `new` |
| 动态状态 | `confirmed_oom` |
| 入口 | `Authenticated HTTP POST /api/plugins/telemetry/DEVICE/{deviceId}/SERVER_SCOPE with Transfer-Encoding: chunked and no Content-Length` |
| 权限前置 | 低权限账号或默认 token/API key |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：登录默认租户管理员账号后，对 `/api/plugins/telemetry/DEVICE/{deviceId}/SERVER_SCOPE` 发送带 JWT 的 chunked JSON attributes body。
- 根因摘要：PayloadSizeFilter 依赖 Content-Length，chunked no-Content-Length 请求进入 `@RequestBody String` 和 JSON 转换路径后才产生内存压力。
- 利用条件：需要低权限/租户管理员写设备属性能力和可访问 deviceId；chunked body 未由网关限制。
- 静态 source：`Ordinary authenticated /api telemetry/attribute POST body accepted as @RequestBody String.`
- 静态 sink：`TelemetryController.saveAttributes/saveTelemetry parses full body with JsonParser and converts all entries into lists before asynchronous save.`
- 攻击者驱动变量：`Body byte volume and JSON key/value count when Content-Length is unknown or not trusted.`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002
docker run -d --name tb-dos-thingsboard-static-0002 --memory=4096m --memory-swap=4096m -e JAVA_OPTS='-Xms512m -Xmx1536m -XX:+ExitOnOutOfMemoryError' -p 127.0.0.1:19090:9090 -v "$PWD/data:/data" -v "$PWD/container-logs:/var/log/thingsboard" thingsboard/tb-postgres:latest
./probe.py --endpoint attributes --sizes-mib 17,64,128,256 --control-mib 17 --value-len 8192
docker rm -f -v tb-dos-thingsboard-static-0002
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Java heap space` |
| 堆/内存口径 | `JVM -Xmx1536m; Docker --memory=4096m --memory-swap=4096m` |
| 请求数 | `5` |
| 1GiB 严格证据 | `-xmx1536m` |
| 原始日志路径 | `logs/probe_events.jsonl` |

证据摘要：

```text
官方单容器默认部署中，具备 TENANT_ADMIN 等低权限写设备属性能力的客户端，可用无 Content-Length 的 chunked REST attributes POST 绕过默认 /api/** 16MiB Content-Length 检查；在 1.5GiB 测试堆下 256MiB body 触发目标 JVM Java heap OOM 并导致 HTTP 不可用。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- Default PayloadSizeFilter rejected the same 17MiB request when Content-Length was present, but did not reject the chunked no-Content-Length variant.
- A reverse proxy, servlet container, or gateway that enforces body size for chunked requests before Spring @RequestBody materialization would mitigate this path.
- Reducing maximum JSON string length, adding per-user/per-device body quotas, rate limits, or streaming parser bounds would reduce exploitability.
- The exact OOM threshold depends on heap/container sizing; this validation used -Xmx1536m and a 4GiB container cap as a bounded harness.

不受影响或风险显著降低的情况：

- The REST /api/plugins/telemetry attributes/timeseries endpoints are not externally reachable.
- Only trusted users can write telemetry or attributes to the target entity.
- All inbound HTTP paths enforce body limits for chunked requests before request body materialization.
- Deployments set sufficiently strict upstream body limits or reject Transfer-Encoding: chunked for these API routes.

## 附件

| Field | Value |
| --- | --- |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/source_result.json | copied dynamic result.json content |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/probe.py |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/start_commands.sh |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/case_plan.json |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/environment.md |
| poc/thingsboard__thingsboard-TB-APP-STATIC-0002/attachments/thingsboard__thingsboard-TB-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002/logs/probe_events.jsonl |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
