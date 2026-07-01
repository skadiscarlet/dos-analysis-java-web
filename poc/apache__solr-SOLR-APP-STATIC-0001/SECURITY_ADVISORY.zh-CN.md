# Security Advisory PoC：Apache Solr form-urlencoded /select 大表单导致 JVM OOM

## 摘要

官方 Solr Docker 默认安全关闭部署中，匿名客户端可向默认 core 的 `/select` 发送大型 form-url-encoded POST。SOLR_HEAP=1g、2GiB 容器复测中，256MiB 表单请求触发 Java heap OOM 并导致服务退出。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `apache/solr` |
| 本地真阳性 ID | `apache__solr-SOLR-APP-STATIC-0001` |
| 动态批次 | `new` |
| 动态状态 | `confirmed_oom` |
| 入口 | `POST /solr/doscore/select with Content-Type: application/x-www-form-urlencoded` |
| 权限前置 | 匿名 |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：向 `/solr/{core}/select` POST `application/x-www-form-urlencoded`，包含 `q=*:*` 和大量攻击者控制参数。
- 根因摘要：`SolrRequestParsers.parseFormDataContent` 在 handler 执行前累积 key/value bytes、解码字符串和参数数组，默认路径未在阈值以下拒绝大表单。
- 利用条件：Solr HTTP endpoint 匿名可达；默认 core 存在；未配置严格 formdataUploadLimit 或代理 body limit。
- 静态 source：`External POST application/x-www-form-urlencoded body to default core handlers such as /solr/{core}/select or /solr/{core}/query`
- 静态 sink：`SolrRequestParsers.parseFormDataContent accumulates key/value bytes, optional charset buffer entries, decoded strings, and MultiMapSolrParams arrays before handler execution`
- 攻击者驱动变量：`form body byte length, parameter count, key length, and value length`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001
docker run -d --name dos-solr-form-apache-solr-static-0001-1g --memory=2g --memory-swap=2g -e SOLR_HEAP=1g -p 127.0.0.1:28983:8983 solr:9.8.1 solr-precreate doscore
python3 probe.py --case-dir "$PWD" --container dos-solr-form-apache-solr-static-0001-1g --base-url http://127.0.0.1:28983/solr --core doscore --sizes 134217728,268435456,536870912,805306368 --request-timeout 300 --ready-timeout 60
docker rm -f -v dos-solr-form-apache-solr-static-0001-1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Java heap space` |
| 堆/内存口径 | `SOLR_HEAP=1g; Docker --memory=2g --memory-swap=2g` |
| 请求数 | `2` |
| 1GiB 严格证据 | `solr_heap=1g` |
| 原始日志路径 | `logs/container_logs_after_probe.txt` |

证据摘要：

```text
匿名 HTTP 客户端在官方 Solr Docker 默认安全关闭部署中，对默认 core 的 /select 发送 form-url-encoded POST，可在 SOLR_HEAP=1g、2GiB 容器复测下由 256MiB 表单请求触发目标 JVM Java heap space OOM 并导致服务退出。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- Validation was repeated with SOLR_HEAP=1g; larger production heaps raise the required body-size threshold.
- Default _default configset did not enforce a small formdataUploadLimitInKB in this deployment path.
- Reverse-proxy/client body limits, Solr requestParsers formdataUploadLimitInKB, authentication, rate limits, or per-client quotas can block or raise the attack cost.
- Strict binary-truth reproduction used SOLR_HEAP=1g and Docker memory/swap limits of 2g; the confirmed signal is Java heap OOM, not Docker OOMKilled.

不受影响或风险显著降低的情况：

- Solr HTTP endpoints are not reachable by low-trust clients.
- A strict form-url-encoded body-size limit rejects the request before SolrRequestParsers materializes parameters.
- Authentication/authorization, reverse proxy controls, or rate limits prevent anonymous large POST requests.

## 附件

| Field | Value |
| --- | --- |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/probe.py |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/start_commands.sh |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/case_plan.json |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/environment.md |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/apache__solr-SOLR-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/logs/container_logs_after_probe.txt |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
