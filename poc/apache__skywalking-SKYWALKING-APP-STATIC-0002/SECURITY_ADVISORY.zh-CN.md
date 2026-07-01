# Security Advisory PoC：Apache SkyWalking OAP pprof collect 流可触发 heap OOM

## 摘要

默认 OAP gRPC 11800 匿名可达且 pprof receiver 使用内存 parser 时，多个未完成 collect 流只需发送 metadata.contentSize 即可在上传内容和任务校验前分配堆内存。1GiB heap、2GiB 容器复测中 48 条流触发 OAP exit 3。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `apache/skywalking` |
| 本地真阳性 ID | `apache__skywalking-SKYWALKING-APP-STATIC-0002` |
| 动态批次 | `new` |
| 动态状态 | `confirmed_oom` |
| 入口 | `gRPC /skywalking.v10.PprofTask/collect on OAP core gRPC port 11800` |
| 权限前置 | 匿名 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：打开多个 `/skywalking.v10.PprofTask/collect` 双向 gRPC 流，发送 contentSize 接近默认 30MiB 的 metadata frame 后保持流未完成。
- 根因摘要：`PprofByteBufCollectionObserver.onNext` 在 contentSize 未超过默认上限时直接 `ByteBuffer.allocate(contentSize)`，并发流数量未被默认配额约束。
- 利用条件：OAP gRPC receiver 暴露给低信任客户端；认证为空；pprof receiver 和 memory parser 可用。
- 静态 source：`External gRPC PprofTask.collect stream on default receiver/core gRPC surface with PprofData metadata.`
- 静态 sink：`PprofByteBufCollectionObserver.onNext allocates ByteBuffer.allocate(contentSize) when contentSize <= pprofMaxSize.`
- 攻击者驱动变量：`PprofData.metadata.contentSize, up to default pprofMaxSize 31457280 bytes per stream.`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002
docker compose -p sw-pprof-case up -d
python3 probe.py --streams 48 --content-size 31457280 --hold-seconds 35 --stagger-seconds 0.05 --sample-interval 0.5 --out logs/probe-failure-1g-48stream-30m.json
docker compose -p sw-pprof-case down -v
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Java heap space` |
| 堆/内存口径 | `OAP JAVA_OPTS=-Xms1g -Xmx1g -XX:+ExitOnOutOfMemoryError; Docker mem_limit 2g` |
| 请求数 | `48` |
| 1GiB 严格证据 | `java_opts=-xms1g` |
| 原始日志路径 | `logs/probe-failure-1g-48stream-30m.json` |

证据摘要：

```text
匿名客户端可访问默认 OAP gRPC 11800 且 pprof receiver 使用默认内存 parser、认证为空时，多个未完成 collect 流用不超过默认 30MiB 的 metadata.contentSize 即可在上传内容和任务完成校验前消耗堆；1GiB JVM heap、2GiB OAP 容器复测中 48 条流触发 Java heap OOM 和 OAP exit 3。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- SW_AUTHENTICATION non-empty requires matching gRPC authentication token.
- Not exposing OAP core/receiver gRPC port 11800 to low-trust clients blocks the tested path.
- Disabling receiver-pprof or setting SW_RECEIVER_PPROF_MEMORY_PARSER_ENABLED=false avoids this specific heap-buffer allocation path.
- Lowering SW_RECEIVER_PPROF_MAX_SIZE reduces per-stream heap allocation.
- gRPC concurrent-call limits, rate limits, ingress policy, or per-client quotas can bound the number of held streams.
- The reproduction was repeated with a 1GiB JVM heap; larger heaps raise the stream count needed for OOM but do not add a per-client bound.

不受影响或风险显著降低的情况：

- The pprof receiver is disabled or not packaged.
- The OAP gRPC port is reachable only by trusted agents.
- gRPC authentication is enforced and the attacker lacks the token.
- The pprof receiver uses file mode instead of the memory parser for this path.
- Ingress or OAP configuration bounds concurrent collect streams and declared content size sufficiently.

## 附件

| Field | Value |
| --- | --- |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/probe.py |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/docker-compose.yml |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/case_plan.json |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/environment.md |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/apache__skywalking-SKYWALKING-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/logs/probe-failure-1g-48stream-30m.json |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
