# Security Advisory PoC：Zipkin HTTP collector gzip 高解压比 spans 请求导致 JVM OOM

## 摘要

默认 Zipkin HTTP collector 匿名开放时，小 wire-size 但大解压后体积的 Zipkin v2 spans gzip 请求可触发 Java heap OOM。1GiB heap、2GiB 容器复测中，约 3.37MiB gzip 请求解压为约 1.356GiB 后导致容器 exit 3 和持续 `/health` 502。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `openzipkin/zipkin` |
| 本地真阳性 ID | `openzipkin__zipkin-ZIPKIN-APP-STATIC-0001` |
| 动态批次 | `new_retest` |
| 动态状态 | `confirmed_oom` |
| 入口 | `POST /api/v2/spans with Content-Type: application/json and optional Content-Encoding: gzip` |
| 权限前置 | 匿名 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 `/api/v2/spans` POST 合法 Zipkin v2 JSON span list，使用 `Content-Encoding: gzip` 放大解压后体积。
- 根因摘要：collector 解压并解析完整 spans 列表，默认未对解压后大小、span 数量或 gzip ratio 做足够约束。
- 利用条件：HTTP collector 匿名可达；允许 gzip；未在 Zipkin 解码前限制解压后大小或 span 数量。
- 静态 source：`External POST /api/v2/spans or /api/v1/spans body with optional Content-Encoding: gzip`
- 静态 sink：`ZipkinHttpCollector.validateAndStoreSpans aggregates request, UnzippingBytesRequestConverter decodes gzip, Collector.acceptSpans decodes List<Span>`
- 攻击者驱动变量：`compressed/decompressed body byte volume and encoded span count in one request`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001
docker run --name dosval-openzipkin-zipkin-static-0001-1g -d --memory=2g --memory-swap=2g -e JAVA_OPTS='-Xms256m -Xmx1g -XX:+ExitOnOutOfMemoryError' -p 127.0.0.1:29411:9411 docker.m.daocloud.io/openzipkin/zipkin-slim:latest
python3 probe.py --base-url http://127.0.0.1:29411 --container dosval-openzipkin-zipkin-static-0001-1g --out logs/probe_results_1g_confirmed.jsonl --metrics-out evidence/metrics_snapshots_1g_confirmed.txt --mode plain --pause 1 --extra-gzip 160000:8192
docker rm -f dosval-openzipkin-zipkin-static-0001-1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Java heap space` |
| 堆/内存口径 | `JVM -Xms256m -Xmx1g -XX:+ExitOnOutOfMemoryError; Docker --memory=2g --memory-swap=2g` |
| 请求数 | `4` |
| 1GiB 严格证据 | `-xmx1g` |
| 原始日志路径 | `logs/probe_results_1g_confirmed.jsonl` |

证据摘要：

```text
默认 Zipkin HTTP collector 匿名开放时，带 gzip 的小 wire-size / 大解压后 Zipkin v2 spans 请求可触发目标 JVM Java heap OOM；1GiB JVM heap、2GiB 容器复测中，160000 spans / 8192-byte tag 的约 3.37MiB gzip 请求导致容器 exit 3 和持续 /health 502。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- Disable external exposure of the Zipkin HTTP collector for untrusted clients.
- Reject or strictly bound gzip Content-Encoding, decompressed size, span count, per-request body size, and request rate before collector decoding.
- Ingress or Armeria request-size limits may block larger plain requests, but this 1GiB retest shows gzip decompression can reach heap pressure before an effective decompressed-size rejection.

不受影响或风险显著降低的情况：

- HTTP collector is disabled or reachable only from trusted instrumentation clients.
- Authentication, network ACLs, or gateway controls block anonymous POST /api/v2/spans.
- A front proxy or application filter enforces decompressed-size, span-count, or gzip-ratio limits before Zipkin decodes spans.

## 附件

| Field | Value |
| --- | --- |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/probe.py |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/start_commands.sh |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/case_plan.json |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/environment.md |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/logs/probe_results_1g_confirmed.jsonl |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
