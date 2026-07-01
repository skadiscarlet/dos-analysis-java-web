# Security Advisory PoC：DataCompare demo operate static map 可由登录用户触发 OOM

## 摘要

默认 Shiro 登录后访问 `/demo/operate/add` 会写入 demo static map。1GiB heap 复测中约 40.3k 次请求触发目标 JVM OOM。

## 影响对象

| Field | Value |
| --- | --- |
| 项目 | `dromara__datacompare` |
| 本地真阳性 ID | `DCMP-STATIC-0001` |
| 动态批次 | `p0` |
| 动态状态 | `verified_oom` |
| 入口 | `/demo/operate/add` |
| 权限前置 | 低权限账号或默认 token/API key |
| 建议 CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## 技术细节

- 触发方式：使用默认登录态重复调用 `/demo/operate/add`，让每次请求写入唯一 static map 项。
- 根因摘要：demo 操作路径存在进程级 static map retained state，缺少默认容量、TTL 或用户/IP 配额。
- 利用条件：需要可登录默认应用；demo endpoint 对该登录用户可达。
- 静态 source：`{'id': 'SRC-003', 'entry': 'POST /demo/operate/add', 'auth': 'low_privilege_authenticated', 'evidence': ['frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/framework/config/ShiroConfig.java:310', 'frameworks/applications/dromara__datacompare/src/main/resources/application.yml:10']}`
- 静态 sink：`{'id': 'SINK-002', 'operation': 'users.put(userId, user)', 'resource_type': 'heap_retained_static_map', 'evidence': ['frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/project/demo/controller/DemoOperateController.java:39', 'frameworks/applications/dromara__datacompare/src/main/java/com/vince/xq/project/demo/controller/DemoOperateController.java:149']}`
- 攻击者驱动变量：`number of requests or imported rows; each add gets a new Integer key from users.size()+1`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

```bash
python3 scripts/run_application_p0_dynamic_validation.py --case DCMP-STATIC-0001 --min-heap 1g
```

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

| Field | Value |
| --- | --- |
| 失败信号 | `java.lang.OutOfMemoryError` |
| 堆/内存口径 | `1g` |
| 请求数 | `40307` |
| 1GiB 严格证据 | `1g` |
| 原始日志路径 | `results/applications_dynamic_validation/p0/logs/DCMP-STATIC-0001.log` |

证据摘要：

```text
默认 Shiro 登录后访问 demo static map 写入路径。
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
| poc/DCMP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/DCMP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/DCMP-STATIC-0001/attachments/dynamic_finding.json | copied P0/P1 dynamic finding |
| poc/DCMP-STATIC-0001/attachments/static_finding.json | copied application static finding |
| poc/DCMP-STATIC-0001/attachments/DCMP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/p0/logs/DCMP-STATIC-0001.log |

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
