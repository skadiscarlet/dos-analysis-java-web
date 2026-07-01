# Security Advisory PoC：DataCompare Swagger test static map 可由登录用户触发 OOM

## 摘要

默认 Shiro 登录后访问 Swagger test `/test/user/save` 会写入 static map。1GiB heap 复测中约 15k 次请求触发目标 JVM OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `dromara__datacompare` |
| 本地真阳性 ID | `DCMP-STATIC-0002` |
| 动态批次 | `p0` |
| 动态状态 | `verified_oom` |
| 入口 | `/test/user/save` |
| 权限前置 | 低权限账号或默认 token/API key |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：使用登录态重复 POST `/test/user/save`，提交带唯一字段/填充内容的请求。
- 根因摘要：测试接口把用户输入写入进程级 static map，未设置容量、TTL 或 per-user quota。
- 利用条件：需要默认登录态；测试/Swagger endpoint 未在生产包中禁用。
- 静态 source：`{'id': 'SRC-005', 'entry': 'POST /test/user/save', 'auth': 'low_privilege_authenticated', 'evidence': ['frameworks/applications/dromara__datacompare/src/main/resources/application.yml:204', 'frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/framework/config/ShiroConfig.java:310']}`
- 静态 sink：`{'id': 'SINK-005', 'operation': 'users.put(user.getUserId(), user)', 'resource_type': 'heap_retained_static_map', 'evidence': ['frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/project/tool/swagger/TestController.java:36', 'frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/project/tool/swagger/TestController.java:72']}`
- 攻击者驱动变量：`attacker-controlled userId key cardinality and retained UserEntity string fields`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case DCMP-STATIC-0002 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `14994` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p0/logs/DCMP-STATIC-0002.log` |

证据摘要：

```text
默认 Shiro 登录后访问 Swagger test static map 写入路径。
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

- None recorded.

不受影响或风险显著降低的情况：

- None recorded.

## 附件

| Field | Value |
| --- | --- |
| poc/DCMP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/DCMP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/DCMP-STATIC-0002/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/DCMP-STATIC-0002/attachments/static_finding.json | copied application static finding |
| poc/DCMP-STATIC-0002/attachments/DCMP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/DCMP-STATIC-0002.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
