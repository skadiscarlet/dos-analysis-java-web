# Security Advisory PoC：Apache HertzBeat Prometheus push 高基数 job/instance 导致 direct buffer OOM

## 摘要

默认 HertzBeat 1.8.0 Docker 部署中，匿名 Prometheus push path 会根据唯一 job/instance 自动创建监控项。1GiB heap/direct、2GiB 容器复测中，约 21.7k 个最小 push 请求触发 direct-buffer OOM 并造成 push 面重复 HTTP 502。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `apache/hertzbeat` |
| 本地真阳性 ID | `apache__hertzbeat-HERTZBEAT-DOS-0001` |
| 动态批次 | `new` |
| 动态状态 | `confirmed_oom` |
| 入口 | `POST /api/push/prometheus/job/{job}/instance/{instance}` |
| 权限前置 | 匿名 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：对 `/api/push/prometheus/job/{job}/instance/{instance}` 发送最小 Prometheus text body，并不断变化 job/instance path segment。
- 根因摘要：job/instance 组合被用于自动创建和保留 push monitor 状态，默认未观察到认证、速率、基数或淘汰边界。
- 利用条件：匿名可达 `/api/push/**`；push auto-create 开启；未限制 job/instance 基数或来源。
- 静态 source：`POST /api/push/prometheus/job/{job}/instance/{instance} through PushPrometheusStreamReadingFilter`
- 静态 sink：`PushGatewayServiceImpl.jobInstanceMap.computeIfAbsent(job + "_" + instance, ...)`
- 攻击者驱动变量：`attacker-controlled unique job and instance path segments`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001
docker run -d --name hbdos0001-hertzbeat --memory 2g --memory-swap 2g -e JAVA_OPTS="-Xms1g -Xmx1g -XX:MaxDirectMemorySize=1g --add-opens=java.base/java.nio=org.apache.arrow.memory.core,ALL-UNNAMED" -p 2157:1157 -p 2158:1158 docker.m.daocloud.io/apache/hertzbeat:1.8.0
./probe.py --count 30000 --start-index 1 --sample-every 250 --timeout 5 --concurrency 8 --case-dir .
docker rm -f hbdos0001-hertzbeat
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Cannot reserve 4194304 bytes of direct buffer memory (allocated: 1070396417, limit: 1073741824)` |
| 堆/内存口径 | `HertzBeat JAVA_OPTS=-Xms1g -Xmx1g -XX:MaxDirectMemorySize=1g; Docker --memory 2g --memory-swap 2g` |
| 请求数 | `21763` |
| 1GiB 严格证据 | `java_opts=-xms1g` |
| 原始日志路径 | `logs/container_full_reinforce.log` |

证据摘要：

```text
默认 HertzBeat 1.8.0 Docker 部署中，匿名客户端可访问 Prometheus push path；在 2g 容器、1g heap/direct 的严格补测下，约 21.7k 个唯一 job/instance 的最小 push 请求触发目标 JVM direct-buffer `OutOfMemoryError`，push 面出现重复 HTTP 502。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- This run used a 2GiB Docker memory cap and explicit 1GiB Java heap/direct memory as a strict validation harness; larger production containers may require more unique job/instance keys before OOM.
- No authentication, rate limit, per-IP quota, job/instance cardinality cap, or eviction was observed on the tested push path.
- The controller returned HTTP 400 for many successful side-effect requests, but logs confirmed monitor auto-creation before/around the response.
- Disabling unauthenticated push auto-create or bounding job/instance cardinality mitigates this path.

不受影响或风险显著降低的情况：

- /api/push/** is not exposed to low-trust clients or is protected by authentication.
- Prometheus push auto-create is disabled or constrained.
- Unique job/instance cardinality is capped per tenant, user, or source IP.
- Created push monitors are evicted or quota-managed.
- Reverse proxy or gateway rate limits prevent the required request volume.

## 附件

| Field | Value |
| --- | --- |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/source_record.json | binary truth record |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/evidence.json | normalized advisory evidence |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/probe.py |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/start_commands.sh |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/case_plan.json |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/environment.md |
| poc/apache__hertzbeat-HERTZBEAT-DOS-0001/attachments/apache__hertzbeat-HERTZBEAT-DOS-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/logs/container_full_reinforce.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
