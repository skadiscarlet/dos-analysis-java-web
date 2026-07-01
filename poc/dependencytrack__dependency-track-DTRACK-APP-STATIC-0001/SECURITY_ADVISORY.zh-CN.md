# Security Advisory PoC：Dependency-Track BOM multipart 上传可触发 apiserver JVM OOM

## 摘要

官方 Dependency-Track 5.0.2 compose 默认 apiserver 2GiB 内存下，持有 BOM_UPLOAD 的低权限 API key 可通过单个约 768MiB multipart BOM part 触发 Java heap OOM；请求返回 HTTP 500，日志确认 OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `DependencyTrack/dependency-track` |
| 本地真阳性 ID | `dependencytrack__dependency-track-DTRACK-APP-STATIC-0001` |
| 动态批次 | `new_retest` |
| 动态状态 | `confirmed_oom` |
| 入口 | `POST /api/v1/bom multipart/form-data` |
| 权限前置 | 低权限账号或默认 token/API key |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：使用仅具备 BOM_UPLOAD 的 API key 向 `/api/v1/bom` 发送包含大 BOM file part 的 multipart/form-data 请求。
- 根因摘要：`BomResource` 在校验和处理前将 multipart part 读入 `byte[]`，缺少默认 BOM part 字节上限。
- 利用条件：需要低权限 BOM_UPLOAD API key 和可访问 project；未由代理或应用限制 multipart/BOM 大小。
- 静态 source：`PUT /v1/bom JSON base64 and POST /v1/bom multipart require BOM_UPLOAD; multipart bom part is attacker-controlled by that principal.`
- 静态 sink：`BomResource reads decoded BOM or multipart part with IOUtils.toByteArray into byte[] before validateBom and processUpload.`
- 攻击者驱动变量：`BOM byte volume per request; repeated accepted uploads also create workflow run metadata with unique upload tokens.`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
cd results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001
docker compose -p codex_dtrack_dos_retest_0001 -f docker-compose.yml up -d
DTRACK_COMPOSE_PROJECT=codex_dtrack_dos_retest_0001 DTRACK_APISERVER_CONTAINER=codex_dtrack_dos_retest_0001-apiserver-1 DTRACK_PUT_DECODED_MIB= DTRACK_POST_PART_MIB=768 DTRACK_REQUEST_TIMEOUT=900 ./probe.py
docker compose -p codex_dtrack_dos_retest_0001 -f docker-compose.yml down -v --remove-orphans
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `OutOfMemoryError: Java heap space` |
| 堆/内存口径 | `Official compose apiserver memory limit 2g` |
| 请求数 | `10` |
| 1GiB 严格证据 | `compose apiserver memory limit 2g` |
| 原始日志路径 | `logs/docker_compose_up.log` |

证据摘要：

```text
官方 Dependency-Track 5.0.2 compose 默认 apiserver 2GiB 内存下，持有 BOM_UPLOAD 的低权限 API key 可通过单个约 768MiB multipart BOM part 触发目标 JVM Java heap OutOfMemoryError；进程未退出但请求返回 500，日志确认 OOM。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- BOM upload requires an authenticated principal with BOM_UPLOAD.
- Limit multipart body size, BOM part size, upload rate, and per-project/per-user upload quota before BomResource accumulates the stream.
- Avoid granting BOM_UPLOAD to low-trust users or restrict it to trusted automation paths.
- A reverse proxy or gateway body-size limit below the observed threshold would block this proof.

不受影响或风险显著降低的情况：

- No low-privilege principal has BOM_UPLOAD.
- No accessible project exists for the API key.
- Ingress rejects large multipart requests before they reach the apiserver.
- The application enforces a strict BOM byte limit before IOUtils.toByteArray materializes the part.

## 附件

| Field | Value |
| --- | --- |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/probe.py |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/docker-compose.yml |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/case_plan.json |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/environment.md |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/logs/docker_compose_up.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
