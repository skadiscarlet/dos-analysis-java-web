# dos-analysis-web v2 CHANGELOG

## [2026-08-14] Tighten Cryostat blocked verdict to image packaging plus notifications-route mismatch

### 修改时间
2026-08-14 05:20

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `cryostatio__cryostat-legacy-F-WS-001` 做最后一轮官方镜像/README 口径复核，先重读既有 `result.json`、`environment.md`、共享环境 `inventory/feasibility/readiness/snapshot`、`changes.jsonl` 与失败日志，再确认旧 blocker 仍主要停留在 “H2 datasource/Flyway 启动失败” 的粒度。
- 在不修改业务代码、不引入组外 case 的前提下，新增两条最小机械复测：其一是按仓库 `compose/compose-postgres.yaml` 的文档化 PostgreSQL companion 路径重启官方镜像；其二是在同一 PostgreSQL companion 基础上，只额外补入未文档化但与打包 Quarkus 运行时相匹配的 `QUARKUS_DATASOURCE_JDBC_URL/USERNAME/PASSWORD` bridge，目的是压缩 blocker，而不是把该路径当作默认验证成功。
- 新证据进一步收紧了官方镜像缺陷：镜像 `/deployments/lib/main` 中实际只包含 `io.quarkus.quarkus-jdbc-postgresql`、`org.postgresql.postgresql` 与 PostgreSQL 侧 Flyway 依赖，并无 H2 JDBC jar，因此 README 与 compose 默认声称支持的 `CRYOSTAT_JDBC_*` H2 file / H2 mem 路径在打包镜像里天然不可用；而文档化 PostgreSQL companion 路径本身也仍不会激活默认 datasource，只有补入未文档化 `QUARKUS_DATASOURCE_*` bridge 后 `/health` 才首次返回 200。
- 即便如此，bridge 仅用于诊断的问题仍未结束：在该 health-ready 诊断路径上，`GET /api/v1/notifications_url` 与 `GET /api/v1/notifications` 依旧返回前端 SPA `text/html`，而不是源码/文档声明的 JSON notificationsUrl 语义或可继续预检的通知 WebSocket 入口。因此保留 `environment_blocked`，但将失败点压缩为 “官方镜像 latest 的打包 datasource 合约与 README/compose 不一致，且即便桥接到健康状态，通知 API 路由仍与文档语义不符”。同步更新 `result.json`、`environment.md`、`data_prep.md`、`rounds/round-1/preflight.json`、共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl` 与批次 `validation_status.jsonl`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cryostatio__cryostat-legacy-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未把带 `QUARKUS_DATASOURCE_*` 的 PostgreSQL bridge 诊断路径包装成默认部署成功。
- 新证据表明当前 blocker 已精确推进为：官方 latest 镜像与 README/compose 的 datasource/notifications API 契约不一致；只有当官方镜像重新对齐其文档化 datasource 路径，并真实暴露 `/api/v1/notifications_url` JSON 语义后，通知 WebSocket 的默认动态验证才可继续。

## [2026-08-14] Confirm lamp-cloud has no default-compatible prebuilt fallback path

### 修改时间
2026-08-14 02:08

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `dromara__lamp-cloud-FND-001` 复核既有 `environment_blocked` 结论，先重读 case `result/environment/logs/changes` 与批次 `validation_status.jsonl`，确认旧 blocker 已收紧到缺失 sibling `lamp-util` 派生 parent artifact，但仍缺少“是否存在官方替代交付路径”的最终证据。
- 在不修改业务代码前提下，补做默认兼容 fallback 路径审查：重读仓库 `README.md`、`lamp-dependencies-parent/pom.xml`、`A极其重要/01-docs/docker/03.docker运行项目.md`，枚举仓库内 `jar/compose/Dockerfile` 资产，并额外检查 `dromara/lamp-cloud` 官方 GitHub Releases / Packages 页面是否存在 release、镜像或可下载预构建产物。
- 新证据表明默认路径没有可替代发布方式：仓库只文档化“先编译整个项目再构建镜像”的路径，明确声明编译顺序必须是 `lamp-util -> lamp-cloud -> lamp-job`；仓库内不存在可直接运行的 gateway jar、也不存在自包含 compose；GitHub Releases 页面明确显示 “There aren’t any releases here”，Packages 页面也未显示任何 `lamp-cloud` 包或镜像。
- 因此该案继续保留 `environment_blocked`，并把阻塞点精确固定为“默认构建硬依赖缺失的 sibling 资产”：即 `top.tangyh.basic:lamp-parent:5.10.0` 既不在 workspace sibling、也不在配置镜像仓库、也不在本地 Maven 缓存中，同时不存在仓库内或官方发布面上的默认兼容预构建替代路径。同步更新 `result.json`、`environment.md`、`data_prep.md`、共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`notes.txt`、`changes.jsonl` 与批次 `validation_status.jsonl`，随后重新运行聚合脚本刷新汇总。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未伪造 sibling 项目、手工补 parent POM、切换非官方镜像或采用未文档化交付方式来制造 gateway 就绪。
- 新证据将 lamp-cloud 的默认阻塞点最终固定为：默认构建链硬依赖缺失的 sibling `lamp-util` 派生 parent artifact，且仓库内与官方发布面上都不存在默认兼容的预构建替代路径；只有当官方默认构建所需的 `top.tangyh.basic:lamp-parent:5.10.0` 能通过 sibling 项目正常安装到本地仓库后，Nacos + gateway + downstream swagger baseline 才能继续。

## [2026-08-14] Tighten lamp-cloud blocked verdict to unresolved sibling parent artifact

### 修改时间
2026-08-14 01:43

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `dromara__lamp-cloud-FND-001` 做最后一轮默认部署/默认流程口径复核，先重读既有 `result.json`、`environment.md`、共享环境 `inventory/feasibility/readiness/snapshot`、`changes.jsonl` 与批次 `validation_status.jsonl`，确认旧 blocker 仍停留在“缺失 sibling lamp-util 项目”的较粗粒度表述。
- 在不修改业务代码、不引入组外 case 的前提下，补做两次环境修复尝试：其一是按文档化路径重跑 `mvn -q -pl lamp-gateway/lamp-gateway-server -am -DskipTests package`；其二是 `-o` 离线重试，验证是否已有可复用的本地 Maven 缓存足以支撑默认构建。
- 新证据表明 blocker 可进一步收紧：两次 Maven 尝试都在 `lamp-dependencies-parent/pom.xml` 处因 `top.tangyh.basic:lamp-parent:5.10.0` 解析失败而在运行前终止；配置的 `aliyunmaven` mirror 不提供该 parent POM，而本机 `~/.m2/repository/top/tangyh/basic/lamp-parent/5.10.0/` 仅有 `lamp-parent-5.10.0.pom.lastUpdated`，并不存在可复用的已安装 parent artifact。
- 因此该案继续保留 `environment_blocked`，但把阻塞点从泛化的“缺失 sibling lamp-util 源码树”推进为“默认构建所需的 sibling lamp-util 派生 parent POM 既不在镜像仓库中，也不在本地 Maven 缓存中”；同时保留另一默认前提：即便 Nacos export archive 已随仓库提供，仍需成功构建 gateway 与至少一个下游 swagger 服务才能进入 `/v3/api-docs/swagger-config` 语义预检。同步更新 `result.json`、`environment.md`、`data_prep.md`、共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`notes.txt`、`changes.jsonl` 与批次 `validation_status.jsonl`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过伪造 sibling 项目、手工补 parent POM、切换非官方构建路径或启用非默认 feature flag 来制造 gateway 就绪。
- 新证据把 lamp-cloud 的默认阻塞点精确推进为：默认构建链在 sibling lamp-util 派生 parent artifact 缺失处即终止；只有当官方默认构建所需的 `top.tangyh.basic:lamp-parent:5.10.0` 能通过 sibling 项目正常安装到本地仓库后，Nacos + gateway + downstream swagger baseline 才能继续。

## [2026-08-14] Tighten Rill Flow blocked verdict to JDK cgroup v2 deployment failure

### 修改时间
2026-08-14 01:25

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `weibocom__rill-flow-F-001`、`weibocom__rill-flow-F-002`、`weibocom__rill-flow-F-003` 做最后一轮默认部署/默认流程复核，先重读既有 `result.json`、共享环境 `inventory/feasibility/readiness/snapshot`、`changes.jsonl`、启动日志与批次 `validation_status.jsonl`，确认旧 blocker 仍停留在较粗粒度的 “Micrometer ProcessorMetrics NPE”。
- 在不修改业务代码、不启用非默认 feature 的前提下，补做一轮运行时兼容性诊断：继续保留官方 compose、官方镜像与仅隔离 host 端口的部署口径，同时新增官方镜像 `--cgroupns=host` + `/sys/fs/cgroup:ro` 诊断采样，记录镜像内 `/proc/self/cgroup`、`/proc/self/mountinfo` 与 `/sys/fs/cgroup` 视图到 `cgroup_diag_20260814.txt`。
- 新证据把 blocker 收紧为默认镜像/JDK/运行时组合问题：`weibocom/rill-flow:latest` 内置 OpenJDK `17.0.2+8-86` 在当前 cgroup v2 + systemd scope 宿主布局下始终把 controller 解析为空，先在 OpenTelemetry runtime metrics 初始化阶段抛错，再在 Spring Boot Micrometer `processorMetrics` bean 创建时以同一 `anyController=null` 终止 webapp 部署；即便容器状态保持 `running`，最终对 `http://127.0.0.1:18083/flow/bg/manage/descriptor/get_business.json` 的探测也只得到 TCP reset，而不是可用 HTTP 响应。
- 因此三案继续保留 `environment_blocked`，但阻塞点已从“backend 启动失败”推进为“官方默认镜像绑定的 OpenJDK 17.0.2 无法在当前 cgroup v2/systemd scope 运行时完成部署”；同步更新三份 `result.json`、三份 `environment.md`、共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl` 与批次 `validation_status.jsonl`，随后重新运行聚合脚本刷新汇总。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/weibocom__rill-flow-F-001`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/weibocom__rill-flow-F-002`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/weibocom__rill-flow-F-003`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过禁用 tracing、关闭 metrics、切换非官方镜像或引入非默认 feature flag 来制造 backend 就绪。
- 新证据表明三条候选路径当前都被同一个默认镜像/JDK/cgroup 兼容性问题阻断；只有当官方镜像或宿主运行时允许该镜像不改行为地完成 Spring Boot/Tomcat 部署后，cron trigger、Kafka trigger 与 foreach submit 的默认语义预检才可继续。

## [2026-08-14] Tighten Cryostat blocked verdict to packaged datasource bootstrap failure

### 修改时间
2026-08-14 01:11

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `cryostatio__cryostat-legacy-F-WS-001` 做最后一轮默认部署/默认流程口径复核，先重读既有 `result.json`、环境 `inventory/feasibility/readiness/snapshot`、`changes.jsonl` 与失败日志，再确认旧 blocker 仍停留在“datasource 未激活 / build-time db-kind 不匹配”的较粗粒度表述。
- 在不修改业务代码、不引入组外 case 的前提下，补做两条最终官方镜像路径验证：其一是仓库 `run-docker.sh` 等价的 `NoopAuthManager` 路径；其二是按 `smoketest-docker.sh` 文档化方式补齐 `cryostat-users.properties` 后的 `BasicAuthManager` 路径。两条路径都继续保留隔离端口、官方镜像、官方 bind-mount 目录和仅为满足打包运行时所需的有界 `QUARKUS_S3_*` 值。
- 新证据表明 blocker 可进一步收紧：在 `quarkus.s3.*` 已补齐后，官方镜像不仅会拒绝此前已见的 README 支持 H2 file URL，连 README 明确支持的 H2 mem URL 也会在 Noop 与带文档化用户文件的 BasicAuth 两条官方路径上，被打包镜像内置 Agroal/Flyway 一致报出 `Driver does not support the provided URL`；容器均在 `/health` 绑定前退出，`/api/v1/notifications_url` 与通知 WebSocket 始终不可达。
- 因此保留 `environment_blocked`，但把阻塞点从“缺少默认 BasicAuth 用户文件/Quarkus datasource 未激活”推进为“官方镜像打包的 datasource/Flyway 启动链对 README 支持的 H2 file 与 H2 mem URL 都不可用”，并同步更新 `result.json`、`environment.md`、`data_prep.md`、共享环境 `feasibility/readiness/snapshot/changes`、批次 `validation_status.jsonl` 与 `blocked_or_rejected.jsonl`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cryostatio__cryostat-legacy-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过非默认 feature flag、关闭鉴权或自定义 sibling 资产绕过默认路径。
- 新证据证明即便按官方 `smoketest-docker.sh` 口径补齐 BasicAuth 用户文件，真正阻塞点仍位于官方镜像自身打包的 datasource/Flyway 启动链，因此当前默认镜像无法进入 WebSocket 语义预检阶段。

## [2026-08-14] Tighten OpenMeetings blocked verdict from room preconditions to office-conversion environment

### 修改时间
2026-08-14 00:55

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 只针对 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS` 继续执行最后一轮默认部署/默认流程口径复核，先重读既有 `result.json`、`environment.md`、`data_prep.md`、`preflight.json`、`observations.json`、共享环境 `readiness/feasibility/inventory/snapshot` 与运行日志，确认旧 `precondition_blocked` 描述已经落后于最新证据。
- 复核结果表明默认业务前置其实已经补齐：默认 H2 安装和前后台登录均已成功；通过默认 service API 创建 public non-moderated room 后，low-privilege external attendee 已经经正常 `/hash` UI/WebSocket 流程进入房间，页面真实暴露 `omws-upload-sid`，且同源 benign `.docx` `POST /openmeetings/room/file/upload` 返回 `{"status":"SUCCESS","message":"OK"}`。
- 新终态阻塞不再是 presenter 会话或 room SID，而是默认转换环境：accepted office 文档进入 `DocumentConverter` 后，`openmeetings.log` 记录 `doJodConvert` 在 `DocumentConverter.createOfficeManager()` 处抛出 `java.lang.NullPointerException: officeHome must not be null`；同时宿主侧 `command -v libreoffice` 与 `command -v soffice` 均为空，说明当前 documented source-build release runtime 未自动发现 LibreOffice/OpenOffice，也未完成 `path.office` bootstrap。
- 因此将该 case 从 `precondition_blocked` 收紧推进为 `environment_blocked`，并同步改写 `result.json`、`case_plan.json`、`environment.md`、`data_prep.md`、共享环境 `readiness.json`、`feasibility.json`、`inventory.json`、`snapshot.json`、`changes.jsonl` 与批次 `validation_status.jsonl`，使 blocker 精确落到默认 office conversion 依赖缺失，随后重新运行聚合脚本刷新批次汇总。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__openmeetings-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过手工设置 `path.office`、安装非文档化自定义组件或绕过默认 room/upload 鉴权来制造成功。
- 新证据将 OpenMeetings 的剩余 blocked 点从“默认 low-privilege presenter/room 前置未补齐”精确推进为“默认 source-build release runtime 缺少可用 office conversion bootstrap，因此 accepted upload 在进入真正 worker 压力前即失败”。

## [2026-08-14] Re-drive Airavata default launch and bounded file-download preflight

### 修改时间
2026-08-14 00:35

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `apache__airavata-FND-200-1` 复核既有 `precondition_blocked` 结论，先重读该 case 的 result/environment/data-prep/log 工件，再在不修改业务代码、不启用非默认 feature 的前提下，重新尝试默认部署与默认流程口径下的实验/文件前置补齐。
- 新证据表明真正可行的默认路径不是 host-side `AiravataOperator.make_experiment_dir()`：该 SDK 路径仍会把 `default-admin` bearer token 当作 SFTP 密码而失败；但默认 server-side `LaunchExperiment` 会按 seeded storage preference 的 `login_user_name=airavata` 成功创建实验目录、启动 Echo 作业并产出 own-process `Echo.stdout` 文件。
- 随后完成了目标入口的语义预检：`GET /api/v1/files/list/false/{processId}` 与 `GET /api/v1/files/download/false/{processId}/Echo.stdout` 在 bearer token 下均返回 200，服务端日志明确记录 `AirvataFileService` 通过 SFTP 下载远端 `Echo.stdout` 到本地临时文件后再由 `FileController` 返回响应，说明静态候选路由已真实可达。
- 在默认路径上执行单轮有界小文件下载爬坡（33B / 129B / 241B 响应体），同步记录 `docker stats` 与健康检查；Airavata 容器内存稳定在约 1.278-1.282 GiB，健康始终 200，未出现 OOM、重启、持续 5xx 或持续不可用，因此该案从 `precondition_blocked` 推进为 `not_reproduced_under_tested_bounds`。
- 同时记录新的默认业务上界：继续放大同一 seeded Echo 路径时，`CreateExperiment` 会先被默认数据库 `RESEARCH_IO_PARAM.PARAM_VALUE=tinytext` 拦截，1024B 及以上输入直接报 `Data too long`，因此本轮未再进入更大下载压力阶段。
- 同步更新该 case 的 `result.json`、`environment.md`、`data_prep.md`、`reflection.jsonl`、新增 `rounds/round-1/` 工件，并回写批次 `validation_status.jsonl`，准备重新运行聚合脚本刷新共享汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__airavata-FND-200-1`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未关闭鉴权、伪造 portal、改 seed 或启用非默认配置来制造成功。
- 新证据把 Airavata 的默认阻塞结论推进为真实可执行后的终态：默认 server-side launch 与文件下载链路可达，但在当前默认 seeded Echo 业务路径下，只观察到有界小文件成功下载，未观察到资源耗尽；更大的同路径输入会先命中默认数据库 tinytext 上界。

## [2026-08-14] Remove GitHub attestation fallback from full-mode local commit verification

### 修改时间
2026-08-14 00:18

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续收紧 `dosweb/llm/deepseek.py` 的 provenance 逻辑：即使旧 `batch_plan.json` 或 target capability 仍带有 `public_source_url`，full 模式也不再回退到 GitHub API 做 public-source attestation，而是统一只验证本地 `source_checkout + source_commit_sha` 的 clean commit 绑定。
- 同步修正 `dosweb/llm/cache.py` 与 request audit 写入逻辑，确保缓存身份、审计字段和新的本地 commit 证明口径一致，避免 `invalid cache entry` 回归。
- 新增 `tests/test_deepseek_client.py` 回归测试，覆盖“带 `public_source_url` 但仍只走本地 commit 校验且不访问 GitHub API”的场景。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/llm/deepseek.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/llm/cache.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_deepseek_client.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`

### 依赖与影响
- 旧 plan 无需重建也能直接受益；只要本地 checkout 和 commit 可验证，full batch 就不会再被 GitHub provenance 卡住。

## [2026-08-13] Re-drive Bonita low-privilege default bootstrap and upload probe

### 修改时间
2026-08-14 00:10

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 只针对 `bonitasoft__bonita-engine-FND1` 继续复核既有 `auth_blocked` 结论，重读该 case 的 `result.json`、preflight、environment 工件与 Bonita 默认权限/REST 路径源码，不修改业务代码、不启用非默认 feature、不用管理员账号直接代替低权限攻击者。
- 在官方 `bonita:latest` 默认镜像与兼容 Postgres companion 的隔离复现环境中，确认首次阻塞并非“默认流程无法得到普通用户”，而是默认镜像只暴露 `install/install` bootstrap 技术账号、不会自动 seed 组织成员；但该默认 bootstrap 账号可通过内置 `API/identity/{group,role,user,membership}` 与 `API/portal/profileMember` 路径完成最小组织初始化，创建普通非管理员 `lowuser` 并赋予默认 `User` profile。
- 进一步以该 `lowuser` 完成语义预检：`GET /portal/fileUpload` 对低权限用户返回 403，但静态入口对应的 `POST /portal/fileUpload` multipart 上传在默认会话下返回 200，因此真正相关的是已认证 POST 语义，而不是 GET 页面访问。
- 在低权限账号下执行有界 multipart part-count 爬坡（1 / 100 / 400 个 16B 文本 part），同步记录容器内存与 HTTP 可用性；三轮请求全部 200，Bonita 容器内存维持在约 459-460 MiB，未触发 OOM、重启、持续 5xx 或持续不可用，因此该案从 `auth_blocked` 收紧改判为 `not_reproduced_under_tested_bounds`。
- 同步更新该 case 的 `case_plan.json`、`environment.md`、`data_prep.md`、`reflection.jsonl`、`result.json`、新增 `round-2/` 工件，并回写批次 `validation_status.jsonl`，准备重新运行聚合脚本刷新共享汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/bonitasoft__bonita-engine-FND1`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过管理员账号直接充当攻击者、关闭鉴权、恢复非默认行为或注入自定义 seed 制造成功。
- 新证据将 Bonita 的默认阻塞点从“拿不到普通账号”精确收紧为：默认镜像不会自动给出普通用户，但 bootstrap 管理员可经内置默认组织/profile API 创建最小低权限账号；即便如此，在当前有界 part-count 与单请求测试范围内仍未复现动态资源耗尽。

## [2026-08-13] Tighten Airavata dynamic precondition blocker semantics

### 修改时间
2026-08-13 23:59

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续复核 `apache__airavata-FND-200-1` 的既有 `precondition_blocked` 证据，只沿默认文档化 quickstart、默认 Keycloak、默认 SDK 和现有 companion services 检查是否还能补齐 Echo 实验/项目/文件前置，不修改业务代码。
- 新增宿主侧与容器网络内认证探测工件，明确区分两类现象：宿主 `127.0.0.1:18080` 并未暴露可直接使用的 Keycloak token endpoint；但在默认 Docker 网络内，`keycloak:18080` 可成功签发默认 `pga` client 的 token，且该 token 能通过 gRPC 成功枚举 seeded `Default Project`，说明默认 API 认证链本身并未缺失。
- 进一步以容器内 `AiravataOperator` 复核默认 SDK 业务链：`get_project_id("Default Project")` 与 `get_preferred_storage()` 都成功返回，且 seeded storage preference 明确解析到 `storage_resource_id=sftp_877f4ac0-0670-4d4e-94dc-726ab14db77a`、`login_user_name=airavata`、`root=/storage`；真正阻塞发生在 `make_experiment_dir()`，SDK 默认以 `username=default-admin` 且 `password=<bearer token>` 对 `sftp:22` 做 Paramiko 认证并返回 `Authentication failed`，因此实验目录、进程文件与下载路由预检仍无法建立。
- 保留并收紧另一条阻塞：README 文档化的 portal UI 备选路径仍依赖 sibling `airavata-portals` 仓库，而当前 worker 主机缺失 `/home/furina/new_tool/airavata-portals`，因此无法通过该默认 UI 流程补齐 Echo 实验。
- 同步更新该 case 的 `result.json`、批次 `validation_status.jsonl` 与证据路径，并准备重新运行聚合脚本刷新共享汇总。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__airavata-FND-200-1`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过关闭鉴权、伪造 portal、手工改 seed、替换 storage 凭据或引入非默认 feature flag 制造成功。
- 新证据把该案阻塞点从泛化的“默认 SDK 路径缺认证”收紧为：默认 API 鉴权可达，但默认 SDK/seeded storage preference 组合无法为 `default-admin` 建立实验目录所需的 SFTP 认证；同时文档化 UI 备选路径所需 sibling portal 资产缺失。

## [2026-08-13] Re-drive OpenMeetings install-to-login transition

### 修改时间
2026-08-13 23:59

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 只针对 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS` 继续沿文档化 source-build release package / 默认 H2 安装路径排查，不修改业务代码、不切换部署模型。
- 复读既有 case/environment 工件、运行日志、访问日志与默认 `persistence.xml` 后，确认此前“日志 ready 但前台仍回 install”的根因不是默认 H2 永久不可安装，而是 `startup.sh` 与 `admin.sh` 共用 `jdbc:h2:./omdb`：当二者从不同工作目录执行时，会各自落到不同的相对 H2 文件。
- 在同一 release runtime 目录内重跑 `./bin/startup.sh` 与 `./admin.sh -i ...` 后，runtime-local `omdb.mv.db` 明确增长，`GET /openmeetings/signin` 返回 200 登录页，前台 `POST /openmeetings/signin` 对 `omadmin` 返回 302 到 `.`，REST `POST /openmeetings/services/user/login` 也返回成功 SID，证明默认安装态已真正推进到可登录前台。
- 同时收紧该案终态：当前已不再是 `environment_blocked`，而是 `precondition_blocked`。剩余阻塞点是默认低权限 presenter 业务前置仍未补齐——尚未通过默认 room UI/WebSocket 流程建立 low-privilege presenter 房间会话并捕获实时 `omws-upload-sid`，因此仍不能合法执行 `/room/file/upload` 动态探测。
- 同步更新该 case 的 `result.json`、`environment.md`、`data_prep.md`、`reflection.jsonl`，共享环境 `readiness.json`、`changes.jsonl`，以及批次 `validation_status.jsonl`，并准备重新运行聚合脚本刷新汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`
- environment 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__openmeetings-default`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过关闭安全控制、管理员替代低权限攻击模型或非默认 feature flag 制造成功。
- 新证据把 OpenMeetings 的默认阻塞点从“安装未完成”收紧为“安装与管理员登录已成功，但 low-privilege presenter 房间会话 / `omws-upload-sid` 业务前置仍缺失”。

## [2026-08-13] Re-drive Openfire default autosetup and BOSH preflight

### 修改时间
2026-08-13 23:59

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 只针对 `igniterealtime__openfire-F0154` 继续沿官方 GHCR 镜像与仓库 `documentation/install-guide.html` 的文档化 autosetup 路径排查，不修改业务代码，不切换非官方镜像，也不关闭任何安全/资源控制。
- 复盘第一次 case-local autosetup 失败后，进一步提取官方镜像 `/sbin/entrypoint.sh` 与默认 `conf_org`/`security_org` 布局，确认此前的空指针并非“autosetup 本身不可用”，而是第一次修复只替换了 `conf/openfire.xml`，却没有保留镜像默认 `conf/security.xml` 与 `conf/security/` 资产，导致 `JiveGlobals.setupPropertyEncryptionAlgorithm` 在旧算法值为空时崩溃。
- 新建第二个 case-local `/var/lib/openfire` 数据目录，保留镜像默认 `conf/security.xml`、`conf/security/`、`crowd.properties` 等 entrypoint 期望资产，仅按文档化 autosetup 方式替换 `conf/openfire.xml`。在该布局下，官方镜像成功完成 embedded-database setup、安装 schema，并明确记录 `HTTP bind service started`。
- 在修通后的默认兼容环境上完成匿名 `/http-bind/` 语义预检：最小有效 BOSH POST 返回 200 且包含正常 `stream:features`。随后执行 3 个单请求体爬坡（128KiB、512KiB、1MiB），分别记录 JVM RSS 与 `docker stats` 容器内存，结果仅出现小幅正增长，未触发 OOM、重启、请求拒绝或持续不可用，因此该案从 `environment_blocked` 改为 `observed_growth_not_confirmed`。
- 同步更新该 case 的 `result.json`、`reflection.jsonl`、`environment.md`、`data_prep.md`，共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl`，以及批次 `validation_status.jsonl`，并准备重新运行聚合脚本刷新汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/igniterealtime__openfire-F0154`
- environment 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/igniterealtime__openfire-default`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过管理员-only 路径、非默认 feature flag 或关闭安全控制制造成功。
- 新证据将 Openfire 的默认安装阻塞点从“官方 autosetup 空指针”精确收紧为“第一次 case-local bootstrap 缺失镜像默认 security 资产”；一旦按官方 entrypoint 预期保留这些资产，默认文档化 autosetup 即可成立，后续阻塞不再是环境，而是仅观察到 bounded growth、尚未达到动态确认阈值。

## [2026-08-13] Re-drive rill-flow default-image startup failure group

### 修改时间
2026-08-13 23:59

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续复核 `weibocom__rill-flow-F-001`、`weibocom__rill-flow-F-002`、`weibocom__rill-flow-F-003` 的既有 blocked 原因、环境工件与默认 compose 路径，只允许默认部署、隔离端口/资源、文档化 companion services 和行为中性的运行时兼容修复，不修改业务代码、不关闭安全控制。
- 在此前已修复 host 端口冲突与 MySQL `setup.sql` 可读性的基础上，确认官方 `weibocom/rill-flow:latest` backend 仍会在默认镜像启动链内于 Spring Boot 2.7 / Micrometer `ProcessorMetrics` 初始化阶段触发 `jdk.internal.platform.cgroupv2.CgroupV2Subsystem.getInstance` 的 `anyController` 空指针，导致 `processorMetrics` bean 创建失败，HTTP 路由始终无法 ready。
- 新增一次兼容性重试：复用同一默认 companion services、相同环境变量和官方镜像，仅额外施加 `--cgroupns=host` 与只读 `/sys/fs/cgroup` 挂载，验证是否是容器 cgroup 可见性问题。结果该重试仍复现同一 `anyController null -> processorMetrics` 崩溃，说明阻塞点不是启动顺序、伴随服务缺失或简单 cgroup namespace 可见性，而是官方默认镜像内 OpenJDK 17.0.2 与当前 cgroup v2 宿主组合下的运行时缺陷。
- 同步更新共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl` 与三个 case 的 `result.json`、`reflection.jsonl`、批次 `validation_status.jsonl`，将 blocked 语义进一步收紧为“默认镜像/运行时组合缺陷导致 backend 无法进入语义预检”，并准备重新运行聚合脚本刷新汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- 新增环境日志：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default/backend_cgroupns_host_retry_20260813.log`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过关闭鉴权、关闭指标、变更 feature flag 或替换非官方镜像制造成功。
- 新证据把 `weibocom/rill-flow` 三案的默认环境阻塞原因从泛化的“backend 未 ready”进一步收紧为：官方 backend 镜像携带的 OpenJDK 17.0.2 / Micrometer `ProcessorMetrics` 在当前 cgroup v2 宿主上启动即崩，而不是 MySQL、Redis、Jaeger、sample-executor、端口或 descriptor seed 缺失。

## [2026-08-13] Trust local pinned commits for full batch provenance

### 修改时间
2026-08-13 23:58

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 调整 `dosweb/llm/deepseek.py` 的 provenance 语义：当 `source_checkout` 与 `source_commit_sha` 已提供时，full 模式允许不再要求每次通过 GitHub public-source API 重新证明；未配置 `public_source_url` 时改为仅校验本地 git checkout 绑定到目标 commit、工作树干净且无 replace refs。
- 保留已有公开源码校验路径：只有显式提供 `public_source_url` 时才继续执行 GitHub public-source attestation 与 origin 一致性检查，因此公开仓库基线仍可复用原有严格证明逻辑。
- 调整 `dosweb/batch/runner.py` 与 `dosweb/batch/plan.py`：full batch 不再因为 `provider_eligible=false` 自动 paused；对非 `git-commit` 指纹目标，runner 会直接从本地 provider checkout 解析当前 `HEAD` 作为 provider commit，并在必要时用 detached worktree 固定到该 commit 后继续执行。
- 调整 `dosweb/llm/cache.py` 与相关测试，使本地 provenance 模式下 `verified_public=false`、`verified_clean_checkout=true` 的缓存身份和校验逻辑保持一致。
- 新增并更新 `tests/test_deepseek_client.py`、`tests/test_batch_runner.py`、`tests/test_batch_plan.py` 回归测试，覆盖本地 commit 绑定、tree-sha256 full 调度、worktree fallback 与 helper 语义更新。
- 运行 `python -m pytest -q tests/test_deepseek_client.py tests/test_batch_runner.py tests/test_batch_plan.py tests/test_config_and_cli.py`，结果 `157 passed`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/llm/deepseek.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/batch/runner.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/batch/plan.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/llm/cache.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_deepseek_client.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_batch_runner.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_batch_plan.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`

### 依赖与影响
- full 模式现在默认信任“已在本地固定并可自校验的当前 commit”，不再把重复 GitHub attestation 当作运行前置，因此可继续处理已验证过一轮的本地源码样本。
- 若调用方仍提供 `public_source_url`，原有公开来源证明链保持启用，不影响需要严格 public-source provenance 的场景。

## [2026-08-13] Re-drive lamp-cloud non-simple environment-blocked case

### 修改时间
2026-08-13 23:42

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核 `dromara__lamp-cloud-FND-001` 的既有 blocked 原因、环境工件、默认部署文档与 round-1 阻塞日志，继续只按默认 `lamp-cloud` 路径检查可补齐的环境前置，不修改业务代码、不启用非默认行为。
- 重新执行文档化构建命令 `mvn -q -pl lamp-gateway/lamp-gateway-server -am -DskipTests package`，再次确认默认启动链在 bootstrap 之前就被 `lamp-dependencies-parent/pom.xml` 的外部前置拦住：该仓库明确要求先单独下载并构建 sibling `lamp-util`，把 `top.tangyh.basic:lamp-parent:5.10.0` 等 artifacts 安装进本地 Maven 仓库；当前 workspace 中缺失该 sibling 源码，且配置镜像也不提供该 parent POM。
- 纠正此前过泛的“Nacos 配置缺失”表述：仓库实际内置了 `A极其重要/01-third-party/nacos/nacos_config_export_20260615232624.zip`，其中包含 `common.yml`、`redis.yml`、`mysql.yml`、`rabbitmq.yml` 与 `lamp-gateway-server.yml`。因此本轮将 `inventory.json`、`readiness.json`、`notes.txt`、`changes.jsonl`、`environment.md`、`result.json` 与 `validation_status.jsonl` 全部收紧为更精确的阻塞语义——默认路径真正无法补齐的是缺失的 `lamp-util` 构建资产，以及由此无法启动 gateway/downstream services。
- 保持该案终态为 `environment_blocked`：即使 Nacos seed material 可用，默认 `/v3/api-docs/swagger-config` 聚合路径仍需要 buildable gateway 和至少一个向 Nacos 注册 swagger route 的下游 lamp 服务；在缺失 `lamp-util` sibling 源码的当前 workspace 中，这一步无法通过默认流程完成。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- environment 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过管理员路径、关闭安全控制、非默认 feature flag 或伪造服务图来制造成功。
- 新证据把阻塞点从笼统的“默认环境缺配置”收紧为：默认源码构建依赖仓库外的 `lamp-util` sibling 资产，而当前 workspace 未提供它；因此该案属于默认流程下无法机械补齐的外部构建资产缺失。

## [2026-08-13] Re-drive environment-repairable dynamic blocked group

### 修改时间
2026-08-13 20:35

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核并重试 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`、`cryostatio__cryostat-legacy-F-WS-001`、`igniterealtime__openfire-F0154`、`weibocom__rill-flow-F-001`、`weibocom__rill-flow-F-002`、`weibocom__rill-flow-F-003` 的既有 blocked 原因、环境工件与默认部署路径，只允许默认部署、隔离端口/资源与文档化 companion services。
- 对 `weibocom/rill-flow` 先修复共享工作站上的 host 端口冲突：把 backend/UI/Jaeger/MySQL 映射改为 `18083/18003/16689/13316` 后，官方 compose 已能完整拉起容器，从而确认早先 `backend_inspect.json` 里的 18080 bind 错误只是外部冲突；但 backend 随后仍在默认镜像启动链内因 OpenTelemetry/Micrometer 访问 cgroup v2 时 `anyController` 为空而空指针退出，`processorMetrics` bean 创建失败，三案继续 `environment_blocked`，阻塞语义已从泛化的“未 ready”收紧为默认镜像内部启动失败。
- 对 `cryostatio/cryostat-legacy` 继续按官方 `run-docker.sh`/README 路径补齐环境变量：新增三次 bounded retry，分别验证文档化 `CRYOSTAT_JDBC_*`、其与 `QUARKUS_S3_*` 的组合，以及再叠加 `QUARKUS_DATASOURCE_*` 的情况。结果表明官方镜像始终在 HTTP 监听前退出：先要求 `quarkus.s3.*`，再无法激活默认 Quarkus datasource，继续强行叠加后又暴露 `quarkus.datasource.db-kind` 构建期固定与 Agroal/Flyway 拒绝文档化 H2 URL 的不兼容，因此继续 `environment_blocked`，且阻塞点已更精确。
- 对 `igniterealtime/openfire` 重读仓库 `documentation/install-guide.html`，确认 autosetup 的确是文档化默认路径之一；结合既有容器日志，将 blocked 原因收紧为：official image 的 case-local embedded autosetup 在 `JiveGlobals.setupPropertyEncryptionAlgorithm` 处因旧算法值为空而空指针退出，而不是笼统的“autosetup 失败”。
- 对 `apache/openmeetings` 复核启动日志后收紧 blocked 原因：clean case-local 源码副本构建出的默认 release 包实际已经启动并记录 `Openmeetings is up and ready to use`，但 `admin.sh -i` 后前台 HTTPS signin 仍回落到 `/install`，说明默认 H2 安装态并未真正完成到可登录 UI，因此仍无法补齐 presenter 房间会话与 upload SID。
- 同步更新六案 `result.json`、共享环境 `changes.jsonl`、新增 retry 日志工件、批次 `validation_status.jsonl`，并准备重新运行聚合脚本刷新汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- 新增环境日志：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cryostatio__cryostat-legacy-default/retry_20260813.log`
- 新增环境日志：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default/backend_retry_20260813.log`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过管理员-only 路径、非默认 feature flag 或关闭安全控制制造成功。
- `weibocom/rill-flow` 的 retry 证明当前首要阻塞已不再是 host 端口冲突，而是默认 backend 镜像自身在 cgroup 指标初始化阶段的启动失败。
- `cryostatio/cryostat-legacy` 的 retry 证明即使沿文档化 JDBC 路径继续补齐，官方镜像仍卡在 Quarkus datasource/build-time 属性不兼容，无法进入 `/health`。

## [2026-08-13] Re-drive blocked dynamic preconditions for Airavata, Bonita, and Stirling

### 修改时间
2026-08-13 20:20

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核 `apache__airavata-FND-200-1`、`bonitasoft__bonita-engine-FND1` 与 `stirling-tools__stirling-pdf-F-vulnerable-decompression` 的既有 blocked 原因、环境工件、轮次证据与 `result.json`，重点重新检查默认部署、普通账号/业务前置与默认流程可补齐性。
- 对 Stirling 进一步排除了持久化配置副作用：保留官方 `latest` 镜像与仅隔离资源余量，清空旧 `/configs` 后按文档化无登录默认模式 `SECURITY_ENABLELOGIN=false` 重启，补做 round-2 单请求语义预检与 round-3 32 路并发有界解压验证。新证据显示匿名 `POST /api/v1/misc/decompress-pdf` 在默认无登录模式下可达，32/32 请求均返回 200，峰值容器内存约 `1.274GiB / 1.5GiB`，但未触发 OOM、重启或持续不可用，因此将该案从 `auth_blocked` 修正为 `not_reproduced_under_tested_bounds`。
- 对 Bonita 进一步收紧阻塞表述：环境已证明默认镜像可启动且会种入 `Administrator`/`User` profile，但本轮仍未找到默认自助注册或普通非管理员账号创建链路，只有 `install/install` bootstrap 账号有证据，因此继续保持 `auth_blocked`。
- 对 Airavata 进一步收紧阻塞表述：环境、默认资源与管理员认证仍正常，但默认 Echo 实验/文件前置仍卡在 seeded SFTP 存储认证，且 README 依赖的 sibling `airavata-portals` 仓库仍缺失，故继续保持 `precondition_blocked`。
- 同步更新三案的 `reflection.jsonl`、Stirling 的新增 `round-2/round-3` 工件、三案 `result.json`/共享 `validation_status.jsonl`，并准备重新运行聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- Airavata case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__airavata-FND-200-1`
- Bonita case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/bonitasoft__bonita-engine-FND1`
- Stirling case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/stirling-tools__stirling-pdf-F-vulnerable-decompression`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过非默认 feature flag、关闭安全控制或管理员替代低权限模型来制造成功。
- Stirling 的修正说明此前 `auth_blocked` 结论受持久化配置副作用干扰；在恢复官方默认无登录路径后，该案已不再 blocked，但在测试边界内仍未动态确认。
- Airavata 与 Bonita 仍 blocked，且阻塞点已细化到默认流程中具体无法补齐的步骤。

## [2026-08-13] Final aggressive round for zfile multipart growth-only case

### 修改时间
2026-08-13 23:03

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核 `/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zfile-dev__zfile-ZFILE-APP-STATIC-0001/` 的既有 `rounds/`、`reflection.jsonl` 与 `result.json`，确认该案仍处于 `observed_growth_not_confirmed` 且还剩最后一轮预算，因此仅新增并执行唯一允许的 round-3 更激进但仍有界确认尝试。
- 将默认 local-build 隔离实例在相同 runtime-home 上重启到更低但仍安全的 `-Xmx384m`，为 round-3 新增 `hypothesis.json`、`preflight.json`、`probe.py`、`observations.json`、`metrics.jsonl` 与目标侧日志证据，并把攻击强化为三波连续的 8 路并发 1000-part metadata-only multipart burst。
- 新证据显示 24 个请求全部继续返回 200，`/api/install/status` 在每波后与最终等待后始终返回 200；目标 RSS 从约 `511512 kB` 台阶式抬升到约 `547392 kB` 并保留，线程/fd 很快回落，但未触发 OOM、重启、默认 parser rejection 或持续不可用，因此终态保持 `observed_growth_not_confirmed`。
- 同步更新该 case 的 `reflection.jsonl`、`result.json`、批次 `validation_status.jsonl`，并重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- zfile case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zfile-dev__zfile-ZFILE-APP-STATIC-0001`
- zfile environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/zfile-dev__zfile-default`

### 依赖与影响
- 本次只执行一轮新增 destructive probe，严格停在第 3 轮上限内，且未通过关闭默认安全控制或启用非默认功能制造成功。
- 当前证据证明默认路径匿名 multipart metadata burst 仍可带来目标侧 retained RSS growth，但即使在更低隔离堆下连续多波也未跨过失败阈值，因此不得误报为 confirmed。

## [2026-08-13] Final aggressive round for GoCD fresh-session growth-only case

### 修改时间
2026-08-13 18:55

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核 `/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/gocd__gocd-F-GOCD-V2HP-001/` 的既有 `rounds/`、`reflection.jsonl` 与 `result.json`，确认该案仍有一轮预算，因此仅新增一轮更激进但仍有界的确认尝试。
- 为 round-2 新增 `hypothesis.json`、`preflight.json`、`probe.py`、`observations.json`、`metrics.jsonl` 与目标侧日志证据，在 fresh official GoCD 容器上把隔离上限收紧到 `768m` 容器/`512m` JVM heap，并提升到 2048 个匿名 fresh session、并发 32 的 `/go/api/v1/health` burst。
- 最终轮中全部 2048 个请求仍返回 200 且发放 2048 个唯一 `JSESSIONID`；target-side JVM `VmHWM` 升到 `755076 kB`、线程从 128 升到 150、容器内存升到 `762.6MiB / 768MiB`，20 秒后几乎不回落，但未触发 OOM、重启、拒绝请求或持续不可用，因此终态保持 `observed_growth_not_confirmed`。
- 更新 `case_plan.json`、`reflection.jsonl`、`result.json`、`validation_status.jsonl`，并准备重新运行共享聚合脚本刷新汇总结果。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- GoCD case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/gocd__gocd-F-GOCD-V2HP-001`
- round-2 观测：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/gocd__gocd-F-GOCD-V2HP-001/rounds/round-2/observations.json`
- 共享状态：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/validation_status.jsonl`

### 依赖与影响
- 仅执行一轮新增 destructive probe，未新增第 3 轮之后的越界尝试，也未通过关闭默认安全控制制造成功。
- 当前证据证明更强的默认路径 session/heap/thread growth，但仍不能表述为 confirmed DoS；后续如无新的默认路径证据，应继续保持非 confirmed 口径。

## [2026-08-13] Re-drive QuickDrop upload-task case

### 修改时间
2026-08-13 02:10

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 复核 `roastslav__quickdrop-FND-QUICKDROP-UPLOAD-TASKS` 的既有 `result.json`、`reflection.jsonl`、`preflight.json`、`probe.sh` 与前两轮证据，确认上轮并非语义未打通，而是只做了串行 16 次低强度 staircase，尚未检验 cached-thread burst growth 是否会跨过默认容量阈值。
- 在不新增第 4 轮的前提下补齐并执行现有 `round-3`：复用官方 `roastslav/quickdrop:latest` 默认镜像与既有持久化数据目录，只提高 distinct incomplete upload 基数到 96、并发到 8，并持续采集 `/proc/1/status` 线程/RSS、fd 数、`/app/files` 文件数、`/actuator/health` 与根路由状态。
- 新证据显示 96 个匿名不完整上传全部返回 200，threads 从 58 升至 159、fd 从 23 升至 120、持久文件数从 22 升至 118，10 秒后仍几乎完全保留；但健康检查始终 `UP`、root 维持默认 302，未触发 OOM、重启或持续不可用，因此终态仍必须保守维持为 `observed_growth_not_confirmed`。
- 同步更新该 case 的 `case_plan.json`、`environment.md`、`data_prep.md`、`hypothesis.json`、`preflight.json`、`probe.sh`、`metrics.jsonl`、`observations.json`、`reflection.jsonl`、`result.json` 与批次 `validation_status.jsonl`，并准备重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- QuickDrop case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/roastslav__quickdrop-FND-QUICKDROP-UPLOAD-TASKS`
- QuickDrop environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/roastslav__quickdrop-default`

### 依赖与影响
- 依赖官方 `roastslav/quickdrop:latest` 默认镜像、既有一次性 admin setup 结果与持久化 `/app/db` `/app/log` `/app/files` 数据目录；本次未修改业务代码、认证语义或默认路由行为。
- 该 case 已在三轮上限内完成更强 PoC 重打：第三轮把证据从低强度串行增长推进到 96 请求 burst 后仍保留的高 threads/fd/file growth，但仍不能误报为 confirmed。
- 后续若继续，只能基于新的 failure 假设或不同默认边界单开任务，不能在本轮再追加第 4 个 destructive round。

## [2026-08-13] Re-drive Guacamole dynamic group

### 修改时间
2026-08-13 01:47

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 复核 `apache__guacamole-client-GUAC-APP-STATIC-0001` 与 `apache__guacamole-client-GUAC-APP-STATIC-0002` 的既有 `result.json`、`reflection.jsonl`、`preflight.json`、`probe.py` 与 round-3 证据，确认两案上轮卡点都不是语义未打通，而是压力与目标特异指标还不够强：0001 仅做到 4000 retained sessions，0002 仅做到 96 tunnel/84 activeConnections。
- 在不新增第 4 轮的前提下直接重打现有 round-3：0001 提升到 12000 次成功登录、24 并发、180 秒 hold；0002 提升到 256 次 tunnel、32 路 burst、180 秒 keepalive，并保留 fresh-container 默认部署语义。
- 0001 新证据显示 GuacamoleSession 最终与成功 token 数对齐到 12000，容器内存约从 280.7MiB 升至 539.8MiB、堆升至约 125225 KiB 且 180 秒内未自动回落，但根路径持续 200，仍只能保守维持 `observed_growth_not_confirmed`。
- 0002 新证据显示 activeConnections 峰值达到 160、guacd TCP 达到 187，active set 清零后 Guacamole RSS/线程仍继续爬升到约 695268 KiB / 250 threads，说明默认路径存在更强的目标侧增长信号；但根路径始终 200，仍未达到 confirmed failure threshold，因此同样维持 `observed_growth_not_confirmed`。
- 同步更新两个 case 的 `case_plan.json`、`hypothesis.json`、`preflight.json`、`observations.json`、`reflection.jsonl`、`result.json` 与批次 `validation_status.jsonl`，并重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- Guacamole cases：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__guacamole-client-GUAC-APP-STATIC-0001`、`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__guacamole-client-GUAC-APP-STATIC-0002`
- Guacamole environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__guacamole-client-default`

### 依赖与影响
- 依赖官方 `guacamole/guacamole:1.6.0`、`guacamole/guacd:1.6.0` 与 PostgreSQL 默认镜像路径；本次未修改业务代码、认证语义或默认部署行为，只强化了现有第 3 轮探针。
- 两案现都完成了三轮上限内的更强重打：0001 证明更大 retained session 基数仍未触发失败，0002 则把证据从短暂 active-set 增长推进到 cleanup 后仍保留的高 RSS/线程增长，但都不能误报为 confirmed。
- 后续若继续，只能基于新的 failure 假设或不同默认边界建模单开任务，不能在本轮再追加第 4 个 destructive round。

## [2026-08-13] Correct ZAP proxy dynamic retest outcome

### 修改时间
2026-08-13 01:20

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 复核 `zaproxy__zaproxy-FIND-ZAP-001` 的既有三轮工件，确认该 case 并非只执行了早期 8 MiB 单轮，而是已完成 round-2 的 fresh-container 32 MiB plain-vs-gzip 同尺寸对照和 round-3 的 64 MiB 强化探针。
- 根据 round-2/3 证据修正终态：same-size 32 MiB 对照中 gzip 比 plain 额外抬升约 59.8 MiB cgroup memory 与约 61.6 MiB Java RSS，说明上轮真正卡点是“目标特异指标最初不足、需用同尺寸控制消解语义歧义”，而不是路由未打通；但 round-3 仍未触发 OOM、重启或持续不可用。
- 同步更新该 case 的 `result.json`、`reflection.jsonl`、`case_plan.json` 与批次 `validation_status.jsonl`，把错误的 `not_reproduced_under_tested_bounds` 修正为 `observed_growth_not_confirmed`，避免遗漏已存在的 growth-only 证据。
- 准备重新运行共享聚合脚本刷新总表、报告与 findings/blocklist 归档。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- ZAP case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zaproxy__zaproxy-FIND-ZAP-001`
- ZAP environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/zaproxy__zaproxy-default`

### 依赖与影响
- 依赖既有官方 `zaproxy/zap-stable:latest` 默认镜像、受控上游 companion 与已存档的 round-1/2/3 证据；本次未新增第 4 轮，也未改变默认部署语义。
- 修正后该 case 被正确计入 growth-only，而非 not reproduced；这会增加聚合层的 `observed_growth_not_confirmed` 计数并减少 `not_reproduced_under_tested_bounds` 计数。
- 三轮上限已经用尽；如需继续只能基于新的 deployment bound 或 failure 假设单开后续任务，不能在本轮再追加 destructive round。


## [2026-08-12] Re-drive GROBID dynamic group

### 修改时间
2026-08-12 16:35

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `grobidorg__grobid-GROBID-STATIC-001` 与 `grobidorg__grobid-GROBID-STATIC-002` 补齐 `round-2`/`round-3` 工件，修复上轮仅有路由与响应大小、缺失目标特异 JVM 指标的语义预检缺口。
- 新 PoC 复用官方 `grobid/grobid:0.9.0-crf` 默认镜像和既有 baseline-memory headroom 修复，只提高有效大 PDF 的并发度，并改从 Dropwizard admin `/metrics` 采集 heap、old-gen、GC 与线程指标。
- `GROBID-STATIC-001` 在 round-2 的 6 并发 8.2 MiB PDF 下先观察到 1.88 GiB heap / 1.31 GiB old-gen 增长，round-3 的 8 并发下再触发 `processFulltextAssetDocument` 中 `ByteArrayOutputStream`/`ZipOutputStream` 的目标侧 `OutOfMemoryError` 与 HTTP 500，终态更新为 `confirmed_oom`。
- `GROBID-STATIC-002` 在 round-2 的 8 并发 8.2 MiB PDF + `type=1` 下先观察到 2.13 GiB heap / 2.04 GiB old-gen 增长，round-3 的 10 并发 fresh-container 下再触发容器 `OOMKilled=true`、客户端空回复和健康检查丢失，终态更新为 `confirmed_oom`。
- 更新两个 case 的 `case_plan.json`、`reflection.jsonl`、`result.json`、`validation_status.jsonl`，并准备重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- GROBID cases：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/grobidorg__grobid-GROBID-STATIC-001`、`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/grobidorg__grobid-GROBID-STATIC-002`
- GROBID environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/grobidorg__grobid-default`

### 依赖与影响
- 依赖官方 `grobid/grobid:0.9.0-crf` 默认镜像与既有 baseline headroom 修复；本次未改业务代码、认证状态或路由行为。
- 两案现已从“指标不足导致的语义未打通”收敛到默认匿名 HTTP 路径上的目标资源失败证据，不再只是 growth-only 或 probe_semantics_failed。
- 该修复完成了本 group 在三轮上限内的 PoC 重打；后续如需继续只能针对新的 deployment bound 或 failure 假设，而不是新增第 4 轮。

## [2026-08-12] Re-drive HertzBeat anonymous SSE dynamic group

### 修改时间
2026-08-12 23:59

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `apache__hertzbeat-FND1`、`apache__hertzbeat-FND2`、`apache__hertzbeat-FND3` 新增 fresh-container 的 `round-2`/`round-3` 工件，包括 `hypothesis.json`、`preflight.json`、`probe.sh`、`metrics.jsonl`、`observations.json` 与容器日志，按技能要求把三案从仅有 20 连接 growth 证据扩展到更强但有界的 256/1024 SSE 长连接重打。
- 新 PoC 改为 raw HTTP socket 持续保持匿名 SSE 连接，并在每轮用 fresh 官方 Docker 容器采集 fd、线程、RSS 与 `jcmd 11 GC.class_histogram`；避免旧串行基线污染后，三案在 round-3 都稳定达到约 `+1025` fd 与 `+1025` `SseEmitter`，其中 `FND3` 还达到 `+1025` `LogSseManager$SseSubscriber`。
- 尽管增长与断连后未及时清理都被重复观察到，但根路径 `/` 在 live/post 阶段始终返回 200，未出现 OOM、重启、持续不可用或 admission failure，因此三案终态统一保守维持为 `observed_growth_not_confirmed`，而不误报 confirmed。
- 更新 3 个 case 的 `result.json`、`reflection.jsonl`、`case_plan.json` 与 `validation_status.jsonl`，并准备重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- HertzBeat cases：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__hertzbeat-FND1`、`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__hertzbeat-FND2`、`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__hertzbeat-FND3`
- HertzBeat environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__hertzbeat-default`

### 依赖与影响
- 依赖官方 `apache/hertzbeat` 单容器默认部署路径；本次未引入任何业务配置或权限变更，只复用既有隔离端口映射。
- 现有证据说明默认匿名 SSE 路径存在可线性放大的 retained growth，但在三轮上限内仍未触达默认部署 failure threshold，因此不能宣称 confirmed DoS。
- 该修复把 HertzBeat group 从“单轮压力不足”提升为“三轮上限内已完成强 PoC 重打”的终态，后续若继续只能基于新的 failure 假设而非重复放大同一轮次。

## [2026-08-12] Validate lamp-cloud dynamic group

### 修改时间
2026-08-12 20:50

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `dromara__lamp-cloud` group 新增 `environments/dromara__lamp-cloud-default/` 下的 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl`、`build_attempt.log` 等环境工件，结构化记录默认路径依赖的 Nacos/MySQL/Redis/RabbitMQ/下游服务前置条件与本地构建失败证据。
- 新增 `dromara__lamp-cloud-FND-001` 的 `case_plan.json`、`environment.md`、`data_prep.md`、`rounds/round-1/`、`reflection.jsonl` 与终态 `result.json`，将该 group 唯一 queued case 收敛到技能规范要求的终态。
- 受控本地构建 `lamp-gateway/lamp-gateway-server` 时，`mvn -q -pl lamp-gateway/lamp-gateway-server -am -DskipTests package` 因缺失外部父 POM `top.tangyh.basic:lamp-parent:5.10.0` 立即失败；结合仓库未提供已检入的 Nacos 导出与自包含默认 compose/镜像，无法在不臆造部署状态的前提下完成默认环境 bootstrap。
- 因 `/v3/api-docs/swagger-config` 还依赖下游 lamp 服务注册到 Nacos 并暴露各自 swagger-config，语义预检无法开始；最终将 `dromara__lamp-cloud-FND-001` 保守落为 `environment_blocked`，而非误报 confirmed 或 not_confirmed。
- 更新 `validation_status.jsonl` 中该 case 的终态与 failure_reason，并重新运行共享聚合脚本刷新 `summary.json`、`summary.csv`、`blocked_or_rejected.jsonl` 与 `DYNAMIC_VALIDATION_REPORT.md`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- lamp-cloud case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- lamp-cloud environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`

### 依赖与影响
- 依赖 `frameworks/applications/dromara__lamp-cloud/README.md`、`A极其重要/01-docs/docker/03.docker运行项目.md` 与 gateway `application.yml` 中的默认部署说明；本次未引入源码或行为变更。
- 当前证据只说明默认环境未能自举，不构成默认部署下的 confirmed DoS，也不能据此反证静态候选无害。
- 该修复消除了本 group 唯一 queued case，后续若要继续只能先补齐官方可复现的 Nacos 配置与下游服务启动材料。

## [2026-08-12] Fix full-batch provenance and entry resolution failures

### 修改时间
2026-08-12 21:10

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 为 production/config/CLI 增加独立的 `analysis_source_root` 语义，并让 `dosweb/production.py` 的 preflight 仅用它校验 `database.source_root`，不再把 provider `source_checkout` 误当作 CodeQL database provenance 目标。
- 保留 `source_checkout` 作为 provider/pinned checkout，用于 Growth excerpt 与公开源码 attestation；同时在 `dosweb/batch/runner.py` full 模式下前移本地 provider checkout 预检，提前暴露 `CONFIG_PUBLIC_SOURCE_UNVERIFIED`，避免 target 跑到 growth 阶段才失败。
- 强化 `dosweb/production.py` 的 growth→entry 关联逻辑：优先最近 handler，并在必要时按 attacker input / demand input 收窄候选，且对仅 registration 不同的语义重复 entry 做稳定收敛，不再因同一 handler 多 registration 直接报 `ANALYSIS_GROWTH_ENTRY_AMBIGUOUS`。
- 同步更新 `dosweb/flows/models.py` 的 flow 引用解析，使 flow 阶段对同一 handler 位置的重复 entry 采用与 growth 一致的稳定收敛策略。
- 扩展 `dosweb/batch/aggregate.py` 输出，新增 `authoritative_status_counts` 并在 gap 摘要中显示 authoritative status / failure reason，便于区分 preflight 失败与普通缺失产物。
- 补充 `tests/test_config_and_cli.py`、`tests/test_production.py`、`tests/test_batch_runner.py`、`tests/test_batch_aggregation.py`、`tests/test_deepseek_client.py` 回归测试，覆盖 checkout 语义拆分、duplicate registration 收敛、本地 provider 预检与聚合状态可见性。

### 验证
- 运行 `python -m pytest -q tests/test_config_and_cli.py tests/test_production.py tests/test_batch_runner.py tests/test_batch_aggregation.py tests/test_deepseek_client.py`
- 结果：177 passed, 167 subtests passed

## [2026-08-12] Validate Suwayomi GraphQL websocket dynamic group

### 修改时间
2026-08-12 20:36

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `suwayomi__suwayomi-server` group 新增 `environments/suwayomi__suwayomi-server-default/` 的 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl`，记录本地文档化 `shadowJar` 启动、headless 环境下 jar 路径修正以及禁用可选 browser/system tray/KCEF 钩子的最小环境修复。
- 新增 `suwayomi__suwayomi-server-F-graphql-ws-retained-operation-state` 的 `case_plan.json`、`environment.md`、`data_prep.md`、两轮 `hypothesis.json`/`preflight.json`/`observations.json`、`reflection.jsonl` 和终态 `result.json`，将该 queued case 收敛到技能要求的终态。
- 动态语义预检确认默认匿名 `/api/graphql` WebSocket 可完成 `graphql-transport-ws` 握手并返回 `connection_ack`；活动重复 ID 会以 4409 关闭连接，而 `complete` 后可用同一 ID 重新订阅，吻合 static 对 `activeOperations` 与 `sessionToOperationId` 分离的建模。
- 两轮单连接唯一 subscribe/complete 阶梯（1000 个 128 字节 ID、5000 个 256 字节 ID）在会话存活期间观察到 JVM `java.lang.String` / `[B` 直方图增长，其中第二轮 live-session 增量达到 `+5132` 个 String 与 `+5138` 个 byte array，但 `/api/graphql` 始终健康且断开后大部分增长回落，因此保守落为 `observed_growth_not_confirmed`。
- 更新 `validation_status.jsonl` 中 Suwayomi case 的终态与 failure_reason，并准备重新运行共享聚合脚本刷新汇总结果。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- Suwayomi case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/suwayomi__suwayomi-server-F-graphql-ws-retained-operation-state`
- Suwayomi environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/suwayomi__suwayomi-server-default`

### 依赖与影响
- 依赖 `frameworks/applications/suwayomi__suwayomi-server/README.md` 中的本地 jar 运行路径；本次未使用官方 Docker 镜像，而是本地构建并在 headless 环境中关闭可选 GUI/KCEF 钩子。
- 该证据只证明 live-session retained-ID growth，不构成默认部署 confirmed DoS；后续若要继续只能在不超过三轮的前提下寻找更强的 target-resource failure 信号。
- 该修复消除了本 group 唯一 queued case，便于统一聚合脚本刷新总表。

## [2026-08-12] Validate wgcloud dynamic group

### 修改时间
2026-08-12 19:52

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `tianshiyeben__wgcloud` group 补齐 `environments/tianshiyeben__wgcloud-default/` 的 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl` 以及本地构建配置、MySQL companion、延迟 SMTP stub、MAIL_SET seed 等最小环境工件。
- 新增 `tianshiyeben__wgcloud-FND1` 与 `tianshiyeben__wgcloud-FND2` 的 `case_plan.json`、`environment.md`、`data_prep.md`、round-1 `hypothesis.json`/`preflight.json`/`observations.json`、`reflection.jsonl` 和终态 `result.json`，并按技能要求将两案从 queued 收敛到终态。
- 将 `FND1` 保守落为 `non_default_only`：匿名 `/wgcloud/agent/minTask` 可用默认 `wgToken` 推导值命中，但观察到的告警邮件线程池阻塞依赖预置 MAIL_SET 与受控延迟 SMTP harness，不能表述为默认部署 confirmed。
- 将 `FND2` 落为 `observed_growth_not_confirmed`：受控数组 JSON 能在线性放大 `AppInfo`/`AppState`/`DeskState` 临时对象数量，但计划内 drain 后未见持久积压、数据库堆积或服务不可用。
- 更新 `validation_status.jsonl` 中 wgcloud 两案状态并准备重新运行共享聚合脚本刷新汇总产物。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- wgcloud case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/tianshiyeben__wgcloud-FND1`
- wgcloud case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/tianshiyeben__wgcloud-FND2`
- wgcloud environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/tianshiyeben__wgcloud-default`

### 依赖与影响
- 依赖 `frameworks/applications/tianshiyeben__wgcloud/` 仓库自带的本地构建+MySQL 文档路径；无官方 compose/image 可直接复用。
- `FND1` 的阻塞证据仅作为非默认组件级复现实验保存，不改变静态候选默认部署下未确认的口径。
- `FND2` 为 growth-only 证据，后续若要继续只能在不突破三轮上限的前提下针对 drain/persistence 吞吐做更强区分。

## [2026-08-12] Repair OpenGrok dynamic validation artifacts

### 修改时间
2026-08-12 19:24

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 修复 `oracle__opengrok-FIND-UI-SEARCH-COLLECTOR` 缺失 `result.json` 导致聚合报错的问题，补齐该 case 的 `case_plan.json`、`environment.md`、`data_prep.md`、`reflection.jsonl`、两轮 `hypothesis.json`/`preflight.json`/`observations.json` 以及终态 `result.json`。
- 补齐 `environments/oracle__opengrok-default/` 下缺失的 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json` 与 `changes.jsonl`，把已执行的官方 Docker 默认部署、最小一文档索引准备、JFR 重试与环境结论结构化落盘。
- 根据现有两轮证据将该 case 终态保守落为 `probe_semantics_failed`：默认匿名 `/search` 语义可达，但启动期与显式 `jcmd` 启动的 JFR 都未建立 target-specific collector allocation 遥测，因此不能提升为 confirmed 或 observed growth。
- 更新 `validation_status.jsonl` 中该 case 的终态与 failure_reason，并在补齐产物后重新运行聚合脚本刷新 `summary.json`、`blocked_or_rejected.jsonl` 与报告统计。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- OpenGrok case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/oracle__opengrok-FIND-UI-SEARCH-COLLECTOR`
- OpenGrok environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/oracle__opengrok-default`

### 依赖与影响
- 依赖此前已保留的 OpenGrok 两轮 HTTP/JFR 原始证据文件，不重新执行更强探针。
- 该修复消除了输出根中的缺失 `result.json` 聚合错误，使 group 结果可被统一汇总。
- 无破坏性接口变更；仅补齐动态验证工件并收敛终态。

## [2026-08-12] Validate JetLinks default captcha dynamic group

### Changed

- Added isolated dynamic-validation artifacts for the `jetlinks__jetlinks-community` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflection, and terminal result files.
- Bootstrapped the repository's checked-in `docker/run-all/docker-compose.yml` default deployment locally with documented Redis and Timescale/Postgres companions, plus isolation-only host-port remapping and bounded JVM/container memory caps for a disposable safety harness.
- Confirmed that the anonymous default route `GET /authorize/captcha/image` is reachable without login and that a normal `130x40` request returns a Base64 captcha payload under the default compose deployment.
- Classified `jetlinks__jetlinks-community-JL-STAGEA-0001` as `confirmed_oom` because a bounded single-request staircase showed `15000x15000` driving memory to 98.54% of a 1.5 GiB container, and a follow-up `16384x16384` request immediately triggered repeated `java.lang.OutOfMemoryError: Java heap space` from `DataBufferInt`/`BufferedImage` on the target route while returning HTTP 500.
- Ran the required aggregate step after writing artifacts; if the shared aggregation script still reports issues on this output root, controller-side follow-up should focus on the aggregate outputs rather than this JetLinks case directory.

### Verification

- Preserved compose bootstrap logs, container inspect snapshot, readiness evidence, and environment change records under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/jetlinks__jetlinks-community-default/`.
- Preserved preflight samples, per-round metrics, observations, OOM log evidence, reflection, and the final result under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/jetlinks__jetlinks-community-JL-STAGEA-0001/`.

## [2026-08-12] Validate ZAP default proxy dynamic group

### Changed

- Added isolated dynamic-validation artifacts for the `zaproxy__zaproxy` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflection, and terminal result files.
- Bootstrapped the official `zaproxy/zap-stable:latest` Docker image locally with isolation-only host-port remapping and a 768 MiB container cap, then added a host-gateway mapping plus a disposable upstream companion container so the default external proxy path could fetch controlled plain and gzip responses without modifying target code or enabling non-default features.
- Confirmed that anonymous absolute-form proxy requests to the attacker-controlled upstream succeed by default and return client-visible decoded bodies for both plain and gzip responses, resolving the static add-on reachability uncertainty.
- Conservatively classified `zaproxy__zaproxy-FIND-ZAP-001` as `not_reproduced_under_tested_bounds` because bounded single-request probes up to 8 MiB decoded bodies produced observable target memory growth but no failure, and the clean-slate 8 MiB plain control consumed at least as much immediate memory as the gzip variant, so a stronger decompression-specific amplification effect was not isolated under the tested limits.

### Verification

- Preserved official-image startup logs, upstream-companion logs, container snapshot metadata, and bootstrap change records under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/zaproxy__zaproxy-default/`.
- Preserved control-vs-gzip probe evidence, semantic preflight, metrics, observations, reflection, and terminal result artifacts under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zaproxy__zaproxy-FIND-ZAP-001/`.

## [2026-08-12] Validate zfile multipart metadata dynamic group

### Changed

- Added isolated dynamic-validation artifacts for the `zfile-dev__zfile` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflection, and terminal result files.
- Built the repository's default Spring Boot jar locally with `mvn -q -DskipTests package` and launched an isolated disposable instance on port `38080` with a case-local `user.home` runtime directory after confirming host port `8080` was already occupied by an unrelated service.
- Completed the required first-run `POST /api/install` bootstrap against the fresh SQLite runtime, then validated that anonymous `PUT /file/upload/invalidStorageKey/x` requests reach multipart parsing before storage lookup: a non-multipart control failed with `Current request is not a multipart request`, while multipart requests progressed to the modeled invalid-storage error.
- Conservatively classified `zfile-dev__zfile-ZFILE-APP-STATIC-0001` as `not_reproduced_under_tested_bounds` because a bounded metadata-only staircase at 1/100/500/1000 parts with a 1-byte file payload caused only small transient RSS/thread movement and no meaningful retained growth, parser threshold below defaults, or service unavailability.

### Verification

- Preserved startup, install-status, and runtime-database evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/zfile-dev__zfile-default/`.
- Preserved control-vs-attack responses, bounded round metrics, and reflection/result artifacts under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zfile-dev__zfile-ZFILE-APP-STATIC-0001/`.

## [2026-08-12] Validate Openfire dynamic group setup-gated BOSH path

### Changed

- Added isolated dynamic-validation artifacts for the `igniterealtime__openfire` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, blocked semantic preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `ghcr.io/igniterealtime/openfire:latest` image locally with isolation-only host-port remapping for the default BOSH and admin-console listeners; plain default startup reached the admin setup wizard on port `9090` but anonymous `/http-bind/` probes on port `7070` reset the TCP connection before any semantic response.
- Applied one targeted case-local embedded autosetup repair by bind-mounting a generated `openfire.xml` derived from the repository autosetup example so the official image could move beyond the initial setup gate without editing target code, but the packaged startup path still failed with a `NullPointerException` in `JiveGlobals.setupPropertyEncryptionAlgorithm` before HTTP/BOSH readiness.
- Conservatively classified `igniterealtime__openfire-F0154` as `environment_blocked` because no default-compatible ready BOSH environment was reached, so the queued anonymous body-materialization candidate could not pass semantic preflight or execute a bounded growth round.

### Verification

- Pulled and launched the official GHCR image locally, captured default setup-page behavior plus BOSH connection-reset evidence, and preserved container logs and inspect output under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/igniterealtime__openfire-F0154/` and `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/igniterealtime__openfire-default/`.
- Re-ran the image with one case-local embedded autosetup bootstrap repair, then captured the startup `NullPointerException` evidence showing that the official image still failed before a semantically testable `/http-bind/` state.

## [2026-08-12] Validate Cryostat legacy dynamic group bootstrap failure

### Changed

- Added isolated dynamic-validation artifacts for the `cryostatio__cryostat-legacy` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap change records, per-case planning, blocked semantic preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `quay.io/cryostat/cryostat:latest` image locally with isolation-only host-port remapping and case-local bind mounts that mirror the repository `run-docker.sh` path layout.
- Applied two targeted environment-side repairs before blocking: first added bounded dummy `quarkus.s3.endpoint-override` and `quarkus.s3.aws.region` runtime values because the packaged image refused to start without them, then added Quarkus default datasource environment keys because the packaged image ignored the legacy `CRYOSTAT_JDBC_*` values alone.
- Conservatively classified `cryostatio__cryostat-legacy-F-WS-001` as `environment_blocked` because the official image still exited before binding the HTTP listener: after the two repairs it reported an incompatible packaged datasource/db-kind expectation and rejected the documented H2 datasource path, so `/health`, `/api/v1/notifications_url`, and the queued notifications WebSocket semantic preflight never became reachable.

### Verification

- Pulled and launched the official Cryostat image locally, captured all three bounded startup attempts plus final container inspect evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001/` and `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cryostatio__cryostat-legacy-default/`.
- Confirmed that no attempt reached HTTP readiness on `http://127.0.0.1:18181/`, so no WebSocket retention round was executed and the worker stopped after environment diagnosis.

## [2026-08-12] Validate jmqtt dynamic group WebSocket idle retention

### Changed

- Added isolated dynamic-validation artifacts for the `cicizz__jmqtt` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflections, and terminal result files.
- Followed the repository's documented source-build quickstart (`mvn -Ppackage-all -DskipTests clean install` plus local `jmqtt-broker-3.0.0.jar` startup) instead of switching to a non-documented deployment model, and copied the checked-in default broker config into a case-local runtime directory with isolation-only port remapping.
- Bootstrapped a disposable `mysql:5.7` companion because the broker's checked-in default config requires MySQL; one compatibility-only repair created `jmqtt_session` with a `CURRENT_TIMESTAMP` default for `online_time` after the bundled `jmqtt.sql` timestamp definition failed under the tested MySQL defaults.
- Classified `cicizz__jmqtt-FND-002` as `observed_growth_not_confirmed` because anonymous WebSocket handshakes to `/mqtt` succeeded, a handshake-only pre-CONNECT channel remained alive through 70 seconds despite the configured 60-second idle path, and bounded 1/3/5-channel probes increased established sockets proportionally, but the conservative run did not pursue service degradation or target-resource failure.

### Verification

- Built the broker locally, launched the disposable MySQL companion plus the local jar with copied default config, and captured startup/readiness evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cicizz__jmqtt-default/`.
- Executed a raw WebSocket handshake readiness probe, a 70-second idle-retention probe, and a bounded connection staircase, and captured the resulting evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cicizz__jmqtt-FND-002/rounds/round-1/evidence/`.

## [2026-08-12] Validate CommaFeed dynamic group bounded refresh-queue behavior

### Changed

- Added isolated dynamic-validation artifacts for the `athou__commafeed` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflections, and terminal result files.
- Bootstrapped the official `athou/commafeed:latest-h2` Docker image locally with only isolation-only host-port remapping and a fixed session-encryption key for repeatable local login cookies; the default deployment otherwise remained unchanged and used the built-in H2 database.
- Completed the default `POST /rest/user/initialSetup` flow to create the first admin account, then created one ordinary `USER` account through the default admin API because `commafeed.users.allow-registrations=false` in the default deployment.
- Tried a case-local delayed mock feed first, but the default fetch path rejected `host.docker.internal` as a local address, so the executed bounded probe conservatively switched to five public RSS/Atom feeds reachable under the default deployment.
- Classified `athou__commafeed-F0002` as `not_reproduced_under_tested_bounds` because two overlapping authenticated `GET /rest/feed/refreshAll` calls over five persisted subscriptions caused `FeedRefreshEngine.queue.size` to rise only transiently to `5`, with default `worker.active` peaking at `3` and draining back to `0` within about two seconds, without sustained retained queue growth or service unavailability.

### Verification

- Launched the official CommaFeed Docker image locally, verified `/rest/server/get`, completed initial setup, authenticated as both admin and ordinary user, and collected `/rest/admin/metrics` evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/athou__commafeed-F0002/`.
- Executed a bounded concurrency-2 `refreshAll` probe and captured queue-depth, worker-activity, feed-fetch meter, server info, container logs, and container inspect evidence under the CommaFeed case directory.

## [2026-08-12] Validate Bonita dynamic group auth preflight

### Changed

- Added isolated dynamic-validation artifacts for the `bonitasoft__bonita-engine` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, changes, startup/container logs, route/auth probe evidence, per-case plan, blocked preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `bonita:latest` Docker image locally with a disposable `postgres:15-alpine` companion on an isolated Docker network. Two targeted compatibility-only repairs were required before readiness: retrying startup after the Postgres companion became ready, and creating the expected `businessdb` / `businessuser` companion database objects required by the image defaults.
- Confirmed that the default deployment serves `/bonita/` and redirects anonymous `/bonita/portal/fileUpload` requests to `login.jsp`. The default `install/install` account can authenticate and complete a tiny multipart upload, but this run did not establish a documented ordinary non-admin account for the queued low-privilege attacker model.
- Conservatively classified `bonitasoft__bonita-engine-FND1` as `auth_blocked` because the static probe plan requires an ordinary authenticated non-admin user for `/portal/fileUpload`, and only installer-level credentials were validated before semantic preflight stopped.
- Ran the required aggregate step after writing artifacts; the shared `aggregate_dynamic_validation.py` script still exited non-zero on this output root without emitting diagnostics, so the worker preserved artifacts and updated `validation_status.jsonl` directly.

### Verification

- Pulled and launched the official Bonita image with an isolated Postgres companion, captured successful Tomcat/Bonita startup evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/bonitasoft__bonita-engine-default/`, and recorded the compatibility repairs applied during bootstrap.
- Verified anonymous login redirection, successful `install/install` authentication, and a tiny authenticated multipart upload under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/bonitasoft__bonita-engine-FND1/rounds/round-1/evidence/auth_and_upload_probe.json`, while preserving the low-privilege auth gap as the terminal blocker.

## [2026-08-12] Validate OpenMeetings dynamic group startup and preflight

### Changed

- Added isolated dynamic-validation artifacts for the `apache__openmeetings` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, changes, clean rebuild workspace notes, per-case plans, blocked semantic preflight, observations, reflection, and terminal result files.
- The repository snapshot’s local static-analysis artifacts under `frameworks/applications/apache__openmeetings/results/` caused the documented `mvn ... -PallModules` build path to fail the ASF RAT gate, so one targeted mechanical repair rebuilt the official release package from a clean case-local source copy that excluded those non-upstream result files.
- Bootstrapped the clean official `apache-openmeetings-9.2.0-SNAPSHOT` release package locally with isolation-only port remapping from `5080/5443` to `15080/15443`; Tomcat and the OpenMeetings webapp reached runtime startup, but the bundled `admin.sh` default-H2 install attempt still left the application redirecting `/openmeetings/signin` back to `/openmeetings/install`.
- Conservatively classified `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS` as `environment_blocked` because the candidate requires a fully installed deployment plus an authenticated presenter already inside a room with a live `omws-upload-sid`, and that semantic room bootstrap could not begin while the default deployment remained in install mode.
- Ran the required aggregate step after writing artifacts; as with other groups on this shared output root, central re-aggregation may still need controller-side review if the shared script continues exiting non-zero without detailed diagnostics.

### Verification

- Rebuilt the documented release package from a clean case-local source copy, extracted the official tarball, applied only isolated port remaps, and captured successful Tomcat/OpenMeetings startup plus persistent install-mode evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__openmeetings-default/`.
- Verified that `/openmeetings/services/UserService?wsdl` was deployed while `/openmeetings/signin` still redirected to `/openmeetings/install`, preventing any valid presenter-room upload preflight.

## [2026-08-12] Validate Airavata dynamic group bootstrap and block state

### Changed

- Added isolated dynamic-validation artifacts for the `apache__airavata` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, compose override/bootstrap records, container inspection, token/bootstrap evidence, per-case planning, environment/data-prep notes, reflection, launch-attempt logs, and terminal result files.
- Built the repository-native `airavata-server:dev` and `airavata-slurm:dev` images from the checked-out source and bootstrapped a case-local approximation of the documented quickstart stack (`compose.yml`) in isolated Docker networking because this worker host lacks the repository's expected Tilt/Colima/mkcert devstack substrate.
- Applied one targeted environment-side repair by changing the case-local Keycloak hostname override from `localhost` to the in-network service name `keycloak`, so JWT `iss` values became resolvable by the Airavata server container for JWKS verification without changing target business code.
- Classified `apache__airavata-FND-200-1` as `precondition_blocked` because the default documented stack became healthy and the seeded default-admin token could enumerate the seeded `Default Project`, `Echo`, `slurm`, and `sftp` resources, but the only safe default-flow route to an own-process file failed earlier at the SDK's seeded SFTP experiment-directory bootstrap with `paramiko` SSH protocol-banner errors, so no semantic preflight or bounded file-download probe could begin.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status `1` and no diagnostics on this output root, so the Airavata worker preserved all artifacts and updated `validation_status.jsonl` directly after executing the required aggregation step.

### Verification

- Built the Airavata server and SLURM images locally, launched the documented dependency stack plus the local server image in isolated Docker networking, and captured healthy HTTP, Keycloak, SFTP, MariaDB, and SLURM readiness evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__airavata-default/`.
- Retrieved a real default-admin Keycloak token over the Docker network, verified the repaired issuer claim, confirmed seeded project/application/resource visibility over the live Airavata gRPC API, and captured the blocking SFTP bootstrap failure under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__airavata-FND-200-1/`.

## [2026-08-12] Validate Dependency-Track dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `dependencytrack__dependency-track` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, compose/bootstrap files, startup logs, container inspect data, scoped auth/data bootstrap evidence, per-case plans, semantic preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official Dependency-Track quickstart-equivalent image set (`ghcr.io/dependencytrack/apiserver:5.0.4`, `ghcr.io/dependencytrack/frontend:5.0.4`, `postgres:18-alpine`) in an isolated local compose stack. Two targeted compatibility-only mechanical repairs were required before readiness: remapping the PostgreSQL 18 bind mount from `/var/lib/postgresql/data` to `/var/lib/postgresql`, and switching removed v4/v5 transitional database environment variable names to the exact v5 `DT_DATASOURCE_DEFAULT_*` keys expected by the apiserver.
- Completed the default first-login password change for `admin/admin`, then used only official REST APIs to create the low-privilege `dosval_user`, scoped `DosvalTeam`, team API key, and an accessible `dosval-project` so the queued authenticated routes could be exercised without changing target business code.
- Classified `dependencytrack__dependency-track-DTRACK-APP-STATIC-0001` as `not_reproduced_under_tested_bounds` because the low-privilege scoped API key reached `PUT /api/v1/bom` and all bounded stepped JSON BOM uploads up to roughly 100 KiB decoded content were accepted with `200` responses and import tokens, but no default rejection bound, target-specific growth signal, or service-failure evidence was observed in the conservative single-request staircase.
- Classified `dependencytrack__dependency-track-DTRACK-APP-STATIC-0004` as `not_reproduced_under_tested_bounds` because the same scoped API key reached `POST /api/v1/vex` and all bounded stepped multipart VEX uploads up to roughly 100 KiB decoded content were accepted with `200` responses and import tokens, but no multipart rejection bound, target-specific growth signal, or service-failure evidence was observed in the conservative single-request staircase.
- The required aggregate step will still be executed after artifact publication for this group; existing evidence indicates the shared aggregator may continue to exit with status `1` and no diagnostics on this output root, so the worker preserved all case/environment artifacts and updated `validation_status.jsonl` directly.

### Verification

- Launched the official quickstart-equivalent image set locally with isolation-only host port remapping and bounded resources; captured both initial startup failures and repaired ready-state evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dependencytrack__dependency-track-default/`.
- Verified default API/frontend readiness, admin first-login force-change semantics, scoped low-privilege project access, and bounded accepted BOM/VEX upload responses under the two Dependency-Track case directories.

## [2026-08-12] Validate GoCD dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `gocd__gocd` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, startup logs, container inspect data, per-case plans, semantic preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official `gocd/gocd-server:v26.1.0` Docker image locally in isolation. The first attempt failed because a bind-mounted `/godata` path was not writable by the container entrypoint, so one targeted mechanical repair switched only the persistence mount to a Docker named volume and the default image then became ready on `http://127.0.0.1:18153/go`.
- Classified `gocd__gocd-F-GOCD-V2HP-001` as `observed_growth_not_confirmed` because anonymous fresh requests to `/go/api/v1/health` repeatedly received new `JSESSIONID` cookies while a cookie-reusing control stopped receiving fresh cookies, confirming pre-auth session creation semantics without collecting internal Jetty session-cardinality or failure evidence.
- Classified `gocd__gocd-F-GOCD-V2HP-002` as `not_reproduced_under_tested_bounds` because tiny anonymous POSTs to `/go/api/webhooks/github/notify` and `/go/api/webhooks/hosted_bitbucket/notify` reached HMAC-mismatch rejection in the default deployment, but the bounded probe did not escalate body size or observe any resource-failure signal.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status `1` and no diagnostics on this output root, so the GoCD worker preserved all artifacts and updated `validation_status.jsonl` directly after executing the required aggregation step.

### Verification

- Launched the official GoCD server image locally with isolation-only host port remapping and bounded container resources; captured startup failure evidence for the unwritable bind mount, then captured ready-state HTTP probes plus final container logs under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/gocd__gocd-default/`.
- Executed bounded anonymous health-route cookie probes and tiny invalid-signature webhook probes, and captured Set-Cookie behavior plus 401 mismatch responses under the two GoCD case directories.

## [2026-08-12] Validate Ant Media dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `ant-media__ant-media-server` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including official-image environment inventory, feasibility, readiness, snapshot, startup logs, container inspect evidence, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Attempted the repository-native packaged build path first, but the checked-in source snapshot could not resolve the required `io.antmedia:parent:4.0.0-SNAPSHOT` parent POM; to stay within default-deployment guidance, the worker then switched to the official `antmedia/community:latest` Docker image rather than editing build files or target code.
- Confirmed that the official community image boots successfully in isolation and auto-deploys the `live`, `WebRTCApp`, and `LiveApp` contexts on HTTP port `5080`, resolving the earlier static uncertainty about packaged route availability.
- Classified `ant-media__ant-media-server-AMS-V2HP-UNKNOWN-001` as `default_not_reachable` because the default `live` app does deploy `ChunkedTransferServlet` on `/chunked/*` and `*.m4s`, but the first tiny external HTTP POST was rejected by the default `IPFilter` with `403 Not allowed IP` before `AtomParser` execution could be observed.
- Classified `ant-media__ant-media-server-AMS-V2HP-UNKNOWN-002` as `not_reproduced_under_tested_bounds` because the default `live` websocket endpoint accepted an anonymous publish handshake and started the adaptor lifecycle, yet the bounded single-session probe observed immediate stop/cleanup after close and no persistent retained thread or adaptor growth.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status 1 and no diagnostics on this output root, so the Ant Media worker preserved all artifacts and updated `validation_status.jsonl` directly after running the required aggregation step.

### Verification

- Pulled and launched the official `antmedia/community:latest` Docker image locally with isolation-only port remapping and bounded container resources; captured startup logs, container inspect output, deployed `web.xml` route mappings, and HTTP readiness probes under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/ant-media__ant-media-server-default/`.
- Executed a bounded tiny `ChunkedTransferServlet` POST preflight and a raw WebSocket upgrade plus single publish-command lifecycle probe, and captured the `403 Not allowed IP`, HTTP `101` upgrade, websocket `start` reply, and post-close cleanup log evidence under the Ant Media case directories.

## [2026-08-12] Validate OpenKM dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `openkm__document-management-system` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including official-image environment inventory, feasibility, readiness, snapshot, runtime configuration capture, changes, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official `openkm/openkm-ce:latest` Docker image locally in isolation, confirmed the default admin login, and created one ordinary `ROLE_USER` account through the authenticated REST admin API so the queued low-privilege routes could be exercised without changing target business code.
- Classified `openkm__document-management-system-F-OPENKM-002` as `observed_growth_not_confirmed` after a bounded single-request staircase with unique ZIP archives showed clear entry-count-driven latency growth on `/frontend/FileUpload?importZip=true`, but no sustained unavailability or explicit target-resource failure.
- Classified `openkm__document-management-system-F-OPENKM-003` as `not_reproduced_under_tested_bounds` because the default authenticated frontend converter admitted two concurrent `toPdf` requests and executed `soffice`, yet no timeout, lingering process retention, or service degradation appeared under the bounded concurrency-2 probe.
- Classified `openkm__document-management-system-F-OPENKM-004` as `not_reproduced_under_tested_bounds` because the default authenticated REST `doc2pdf` endpoint accepted two concurrent valid multipart DOCX conversions and returned PDFs without provider rejection or target-resource failure under the bounded concurrency-2 probe.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status 1 and no diagnostics on this output root, so the OpenKM worker preserved all artifacts and updated `validation_status.jsonl` directly after running the required aggregation step.

### Verification

- Pulled and launched the official OpenKM image locally, captured container logs plus runtime `OpenKM.cfg` and `OpenKM.xml`, verified low-privilege frontend and REST authentication, and enumerated seeded root documents for converter probes.
- Executed bounded unique-entry ZIP import probes plus concurrent frontend and REST DOCX-to-PDF conversion probes, and captured timing, HTTP headers, PDF outputs, route responses, and server-side converter evidence under the OpenKM case directories.

## [2026-08-12] Validate Rill Flow dynamic group startup feasibility

### Changed

- Added isolated dynamic-validation artifacts for the `weibocom__rill-flow` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, startup logs, container inspect evidence, per-case plans, blocked preflights, reflections, and terminal result files.
- Bootstrapped the documented official compose quickstart twice in a local isolated environment. The first attempt failed on a host `8080` port collision, so a case-local compose copy remapped only the host ports while preserving the documented images and environment variables.
- Applied one targeted dependency-side mechanical repair by mounting a readable case-local copy of `setup.sql` after the checked-in MySQL bind mount failed with `Permission denied` during initialization.
- Conservatively classified `weibocom__rill-flow-F-001`, `weibocom__rill-flow-F-002`, and `weibocom__rill-flow-F-003` as `environment_blocked` because the official `weibocom/rill-flow:latest` backend image never reached readiness: Tomcat/Spring Boot startup aborted in OpenTelemetry/Micrometer system-metrics initialization with a cgroup-related `NullPointerException`, so no route-level semantic preflight could begin.

### Verification

- Pulled and launched the documented compose images locally, captured compose/container state, backend startup logs, MySQL startup logs, and container inspect output under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default/`.
- Verified that the dependency-side SQL readability issue could be repaired in isolation, but the backend startup crash remained and prevented any successful HTTP probe to `/flow/trigger/add_trigger.json` or `/flow/submit.json`.

## [2026-08-12] Validate Concord dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `walmartlabs__concord` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including compose-based environment inventory, feasibility, readiness, snapshot, changes, bootstrap records, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official Concord compose quickstart in an isolated local environment with a deterministic admin token only for reproducible first-start authorization, then created one ordinary local user and API key to exercise the queued authenticated routes without changing target business code.
- Classified `walmartlabs__concord-fnd1`, `walmartlabs__concord-fnd2`, and `walmartlabs__concord-fnd3` as `not_reproduced_under_tested_bounds` after bounded default-route probes observed successful request handling but no attributable resource failure or meaningful degradation under the safe attachment/log payloads.
- Classified `walmartlabs__concord-fnd4` as `probe_semantics_failed` because the multipart form route was reached but the crafted JSON field payload failed the form schema before becoming a semantically valid stress case.
- Classified `walmartlabs__concord-fnd5` as `probe_semantics_failed` after a two-step WebSocket preflight: the first attempt exposed required Concord agent headers, and the corrected second attempt proved deserializer reachability but failed on a missing `messageType` semantic requirement instead of a size-bound or resource effect.
- Recorded that the central `aggregate_dynamic_validation.py` script currently exits with status 1 on this shared output root without emitting diagnostics, so the Concord worker preserved all case/environment artifacts and updated `validation_status.jsonl` directly for manual or controller-side re-aggregation.

### Verification

- Launched the official `docker-images/compose/docker-compose.yml` stack locally, captured compose/server logs, verified authenticated access with the isolated admin token, created an ordinary API key, and started reusable test processes plus a v2 log segment for route-specific probes.
- Executed bounded probes for attachment ZIP upload, v1 log append, v2 log-segment append, multipart form submission, and WebSocket upgrade/message handling; captured route responses and server-side error evidence under the Concord case directories.

## [2026-08-12] Validate Stirling PDF dynamic group startup feasibility

### Changed

- Added isolated dynamic-validation artifacts for `stirling-tools__stirling-pdf` under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, changes, crafted PDF probe input, preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `docker.stirlingpdf.com/stirlingtools/stirling-pdf:latest` image in documented login-disabled Docker mode and attempted one targeted mechanical repair by increasing startup memory headroom.
- Conservatively classified `stirling-tools__stirling-pdf-F-vulnerable-decompression` as `environment_blocked` because the official image terminated during startup with `OutOfMemoryError: Metaspace` before any readiness or route-level semantic validation could occur.

### Verification

- Pulled and launched the official latest image locally with isolated port remapping and case-local config/log volumes; captured startup logs, container inspect state, and failed readiness evidence for both bootstrap attempts.
- Generated a bounded valid `FlateDecode` PDF probe artifact and recorded that the prepared single-request probe only encountered connection refusal because the service never became healthy.

## [2026-08-12] Validate Hackpad dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `dropbox__hackpad` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including default Docker environment inventory/feasibility/readiness snapshots and per-case plans, preflights, observations, evidence, reflections, and terminal results.
- Confirmed that the documented default Hackpad Docker deployment boots successfully under isolation, but the modeled anonymous comet transport is not default-reachable in this setup: `/comet` returns `404` and `/newcomet` redirects to sign-in, so `dropbox__hackpad-F-HACKPAD-COMET` was conservatively classified as `default_not_reachable`.
- Added a case-local component harness for `ExpiringMapping` to validate the Hackpad session sink semantics, showing one retained entry per novel ES2-like identifier plus lazy expiry on subsequent mutation; because this stayed mechanism-level and non-destructive, `dropbox__hackpad-F-HACKPAD-SESSION` remains `observed_growth_not_confirmed` rather than a confirmed target failure.

### Verification

- Built the official Hackpad Dockerfile, launched the documented volume-mounted quickstart locally, verified HTTP root reachability with the application's expected `Host` header, and captured route-specific evidence for `/comet` and `/newcomet`.
- Compiled and ran a local JDK 21 harness against the repository's `infrastructure/net.appjet.common/util/ExpiringMapping.java` to record retained-cardinality and lazy-expiry evidence for the session case.

## [2026-08-10] Bind batch plans to exact CodeQL databases

### Changed

- New batch plans now bind each target's validated CodeQL database fingerprint into the immutable plan digest and per-target binding while retaining load compatibility for historical plans that predate this field.
- Batch execution revalidates fingerprint-bound databases and their exact source-root correspondence before creating the target pipeline, so a database replaced after plan publication fails closed before CodeQL or a remote provider is invoked.
- The PoC-29 evaluator now reflects the repaired 18/18 default databases and can request a strict full plan that pins `deepseek-v4-pro`, temperature `0`, the DeepSeek base URL, 60-second timeout, three retries, explicit plan-time remote intent, and `pilot_skipped=true`. It refuses to publish the plan unless all 18 targets are provider-eligible and queued.
- PoC-29 corpus conversion now carries the validated CodeQL database fingerprint rather than the database-marker digest into batch targets.
- Strict PoC source overrides can bind a tree-attested analysis source/database pair to a separate clean public Git checkout only when the checkout HEAD, origin, clean state, full commit, canonical GitHub URL, and excluded-path tree digest all match. The provider checkout and commit are included in the immutable target capability while database validation remains bound to the canonical analysis source.

### Verification

- Added plan serialization/legacy compatibility coverage and runner checks for successful database revalidation, database fingerprint drift, and database source-root drift.
- Resolved the eight PoC tree-attested targets to exact public commits and clean independent Git checkouts: Druid `c2d15dfc55d965e63b55dd11d698ca10ced99b4e`, HertzBeat `87062df97d01d14ea857b76936e97f4385cf609e`, SkyWalking `bb16533009a597dbb41ab6f013ac300509abbb3e`, Solr `c54251ea1614a6635410083839011cf20bfe189b`, Dependency-Track `f4bffa0aee1980387e1c40d7f01f13622a4c7720`, Zipkin `878ce2a1fad54ca941d17fdcf2e1d924b148eb1f`, Presto `913a64110299a3ae0f6314af1558255c1488fec8`, and ThingsBoard `e70298792acaa41b986ed8662fb2a760c35ee5e6`. Each checkout passes exact HEAD/origin/clean-worktree/Git-object validation; the override manifest separately binds the canonical analysis tree SHA-256 and default native database fingerprint.
- Published the nonexecuting immutable 29-case/18-target full plan at `results/java_web_dos_batch/poc29-full-plan-20260810/`. All 18 targets are queued, all 18 database fingerprints are bound, the provider is fixed to `deepseek-v4-pro` with temperature `0`, timeout `60`, retries `3`, and `pilot_skipped=true`; plan digest is `35fcae172671ea29b6ceacfeb0a99613ac2b3a3a08d7da3d1b5eaedf4c08d8a4`.
- The first authorized full execution of that published PoC-29 plan completed with `completed_with_failures` and produced no aggregate summary or static findings. All 18 targets failed: the 8 provider-override repositories hit `CODEQL_DATABASE_INVALID` because `dosweb/production.py` still requires the validated CodeQL database source root to equal the configured provider checkout even when the plan intentionally separates canonical analysis source from provider provenance, 9 targets hit `ANALYSIS_GROWTH_ENTRY_AMBIGUOUS`, and `tianshiyeben/wgcloud` hit `CONFIG_PUBLIC_SOURCE_UNVERIFIED`. The preserved state under `results/java_web_dos_batch/poc29-full-plan-20260810/` is the handoff baseline for the next tool-development session.

## [2026-08-04] Prepare strict native repair for Java Web 205

### Added

- Added a Java Web 205 native CodeQL database repair path with a frozen 55-target scope, Maven/Gradle-only discovery, safe nested build roots, multi-JDK attempts, strict source/database fingerprint validation, resumable attestations, and quarantine-based atomic promotion into the default `databases/applications/` paths.
- The repair path explicitly rejects CodeQL autobuild, `build-mode=none`, bounded javac, compilation-failure suppression, tests, application launch, deployment, Docker tasks, cloning, symlinked targets, and shell-composed commands.
- Added reviewed build-root overrides for the ten archived repositories whose Maven/Gradle roots are nested below the canonical source directory.

### Verification

- A non-network preflight fixed the exact current scope at 55 `JAVA_DATABASE_REQUIRED` targets and discovered 44 Maven and 11 Gradle native build specifications with no unresolved build roots. No database was modified during preflight.
- Native repair unit tests, Python compilation, and diff validation passed. The first authorized Sentinel attempt exposed a stale active loopback proxy in the workstation Maven settings; a subsequent attempt exposed a corrupt artifact in the shared Maven cache. Native Maven captures now use a repository-owned empty settings file, a run-local Maven repository, and sanitized Java/Maven/Gradle option variables so they do not inherit workstation mirrors, credentials, proxy state, injected build arguments, or corrupt shared-cache entries. No database was promoted by either failed attempt.
- Resume now verifies attestation digests and binds the current source, database, build command/root, and JDK set; malformed attestation lines are isolated. Promotion failures are recorded per target, quarantine paths are attempt-specific, and a single target exception no longer aborts the remaining repair scope. A completed CodeQL candidate rejected solely for source-fingerprint drift is now preserved under an attempt-specific `.source-drift` recovery path instead of being deleted, allowing generated-file quarantine, exact fingerprint restoration, strict revalidation, and guarded forensic promotion without rerunning a multi-hour native capture.
- The first repaired default database, `alibaba/sentinel`, completed a 94-module native Maven capture under CodeQL with source fingerprint unchanged, passed strict validation and `codeql resolve database`, and was atomically promoted while the prior invalid directory was retained under the run-specific quarantine path.
- The first five-target tranche exposed two invocation defects now corrected: CodeQL requires an explicit `--working-dir` for nested build roots, and Maven wrappers do not reliably honor `MAVEN_ARGS`, so controlled settings and the run-local repository are now injected directly into the native Maven command. The corrected retry natively repaired `lenve/vhr` and `undera/perfmon-agent`; both promoted databases pass strict resolution. Remaining project-specific failures are retained fail-closed: `ikismail/shoppingcart` has an uncompilable/missing `GetMapping` import, `merikbest/ecommerce-spring-reactjs` uses a Lombok processor incompatible with the installed JDK 17+, and `stevensouza/automon` references an internal `2.0.0-SNAPSHOT` artifact while its reactor builds `2.0.1-SNAPSHOT`.
- The second five-target tranche natively repaired and promoted `erudika/para`. Its other four targets remain fail-closed for checkout/build constraints: Quarkus extension dependency injection failure in `athou/commafeed`, old Lombok plus missing Java 8 system artifacts in `kalvingit/kvf-admin`, an absent internal `yuzi-generator-maker:1.0` artifact in `liyupi/yuzi-generator`, and a wrong local parent binding in `wxiaoqi/spring-cloud-platform`.
- The third five-target tranche produced no valid database. Failures were old Lombok on JDK 17+ (`dengsinkiang/sk-admin`), a late reactor compilation failure after most modules succeeded (`dromara/warm-flow`), a missing local parent (`exrick/xboot`), a timed-out direct GitHub asset download (`nitorcreations/nflow`), and a CodeQL Kotlin extractor ceiling because the project uses Kotlin 2.3.20 while the installed CodeQL supports versions below 2.2.30 (`suwayomi/suwayomi-server`).
- The fourth five-target tranche also produced no valid database. Blockers were an Apache RAT property mismatch (`apache/guacamole-client`, retried with the project-specific RAT ignore property), a missing private/non-Central parent (`dromara/lamp-cloud`), a required Java 24 release with only JDK 17/21/22 installed (`jamebal/jmal-cloud-server`), a missing frontend build output required by an Ant move step (`runify-dev/runify`), and an annotation processor incompatible with the installed javac (`zmops/zeus-iot`). The Guacamole retry passed the RAT gate but then failed on an absent reactor-produced `guacamole-common-js:zip:1.6.1`; it also generated non-excluded Node launcher files in the source tree, so the source-fingerprint drift gate correctly rejected the attempt before validation or promotion. Those generated files were preserved in the run artifact quarantine, and the canonical source fingerprint was restored.
- The fifth five-target tranche natively repaired and promoted `grimmory-tools/grimmory`, `jeecgboot/jeecgboot`, and `kerwincui/fastbee`; FastBee succeeded on the JDK 17 fallback after JDK 22/21 failures. `openremote/openremote` remains blocked by a required but unavailable Yarn task, and `tess1o/geopulse` requires Java release 25 while the host provides JDK 17/21/22.
- The sixth five-target tranche natively repaired and promoted `stirling-tools/stirling-pdf`. Its failures were Java release 25 without JDK 25 (`apache/hertzbeat`), a required JDK 11 Gradle toolchain (`hivemq/hivemq-community-edition`), a CodeQL Kotlin ceiling for Kotlin 2.4.0 (`micrometer-metrics/micrometer`), and Gradle 8.1.1 incompatibility with Java 22 bytecode during settings-script analysis (`sanluan/publiccms`).
- The seventh tranche initially reported five failures, but forensic recovery showed that `jenkinsci/jenkins` had completed its full native Maven reactor and CodeQL finalization before generated Node/Yarn/frontend files triggered the tree-fingerprint gate. Those generated files were preserved in the run artifact quarantine, the exact preflight fingerprint was restored, and the completed candidate passed repeated strict validation before guarded promotion and a recovery attestation. The other blockers were Java release 25 (`dependencytrack/dependency-track`), a Gradle task dependency validation error after compilation (`kestra-io/kestra`), a project plugin type-resolution failure (`modelengine-group/app-platform`), and an old Scala Maven plugin failing to load `javax.tools.ToolProvider` (`scouter-project/scouter`).
- The eighth five-target tranche natively repaired and promoted `kiegroup/jbpm` and `mqttsnet/thinglinks`, each after roughly 12–13 minutes of Maven/CodeQL capture. The failures were an unavoidable frontend `pnpm install` execution (`metersphere/metersphere`), a Liquibase goal requiring a live local PostgreSQL service (`walmartlabs/concord`), and missing generated protocol `Command` classes (`apache/skywalking`).
- The ninth five-target tranche produced no valid database. Blockers were a required Java 25 release (`apache/syncope`), an incomplete Maven wrapper checkout (`apache/incubator-kie-kogito-runtimes`), a missing `server-ee` reactor module (`theonedev/onedev`), an absent local `skyeye-parent:1.0-SNAPSHOT` parent (`dromara/skyeye`), and the CodeQL Kotlin extractor ceiling for Kotlin 2.3.20 (`apache/solr`). Solr's generated `.kotlin` diagnostics were preserved in the run artifact quarantine and the exact preflight source fingerprint was restored; no ninth-tranche default database was promoted.
- A targeted native retry avoided Solr's unrelated Kotlin UI module by capturing `:solr:server:assemble`; the Java server build completed under CodeQL, retained the exact source fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `2541f63b47573bbcd6170146c5beb896929052fab4d202fac9195a58939800f0`. Switching Kogito from its incomplete wrapper to system Maven exposed the underlying checkout blocker: its root requires the absent `org.kie:drools-build-parent:999-SNAPSHOT`, so it remains fail-closed.
- The tenth tranche natively repaired and promoted `apereo/cas` after a roughly 32-minute Gradle/CodeQL capture; its database fingerprint is `e23ed318723a249aab86ba4d9a95c4362de83da954ecc53e6c998c2c5e10ce81`, and strict validation plus `codeql resolve database` passed. `dotcms/core` compile was initially blocked by absent reactor ZIP artifacts; a native `package` retry produced those artifacts but then failed in its `process-annotations` compiler execution. `entropy-cloud/nop-entropy` compile lacked a reactor tests JAR and is being retried with test compilation enabled. `geoserver/geoserver` reached a real source/dependency API mismatch in `gs-gwc`; its generated Spotless index files were preserved in the run artifact quarantine and the exact preflight source fingerprint was restored. These three targets remain fail-closed unless their targeted native retries complete successfully.
- To address targets blocked solely by unavailable Java toolchains, JDK 8, 11, and 25 were installed locally under `/usr/lib/jvm/` and verified with `java -version`. The strict native builder now includes these system toolchains in its per-target fallback sequence while retaining per-attempt JDK attestation and source/database validation; previously staged repository-local archives are not executed by the builder. The first legacy tranche natively repaired and promoted `dengsinkiang/sk-admin`, `kalvingit/kvf-admin`, `merikbest/ecommerce-spring-reactjs`, and `scouter-project/scouter` under JDK 8; all four pass strict validation and `codeql resolve database`. HiveMQ's current Gradle wrapper itself requires JDK 17 despite requesting a JDK 11 compilation toolchain; the JDK 17 Gradle-runtime retry succeeded natively, retained its exact Git commit fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `21e13ba3275709689375bd3349cfd61121961efccef6ad1998dcd712fe15165b`. `zmops/zeus-iot` remains blocked by missing `JettyJsonHandler` symbols rather than its Java runtime.
- `entropy-cloud/nop-entropy` was natively repaired by retaining test compilation while skipping test execution, allowing the reactor tests JAR to be produced. Its 27-minute Maven/CodeQL capture retained the exact Git commit fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `7245a483cd57e9a44786d0b771c1d8d3e47fd90622145f5266e53f2aaad997fa`.
- Druid's corresponding native package capture completed successfully under CodeQL but generated 54 fingerprint-relevant distribution/frontend files. Those exact paths were digest-manifested and moved to run-specific generated-source quarantine, restoring the original source fingerprint. A later capture accidentally attested the generated-source state because it began before the generated files were removed; that database was quarantined as noncanonical. The final system-JDK-only recapture preserved its completed candidate on source drift, the same 54 exact files were quarantined, the original fingerprint `86263208a9038f00928b837c2df8fa7e4b18125ff6d411cd8212a87bb0c841c9` was restored, and the candidate passed repeated strict validation before guarded promotion. The canonical Druid database fingerprint is `f65bffa3fbfe9ba3ba967ee10b63a9328d7c7e9eb2e05cfc39c139a856d61d4c`; `codeql resolve database` also passed.
- The eleventh tranche produced no valid database. `thingsboard/thingsboard` requires Java release 25; `sonarsource/sonarqube` reached the unrelated distribution JRE download task; `apache/druid` compile could not resolve its reactor-produced `druid-processing` tests JAR; `keycloak/keycloak` compile did not generate its reactor Maven plugin descriptor; and `prestodb/presto` compile lacked a reactor tests JAR while an unrelated UI module attempted a timed-out Yarn download. A targeted SonarQube retry using the native aggregate `classes` task with build cache disabled succeeded under CodeQL, retained the exact source fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `09f781aadca5f82386845a7e9b61ce953df749d9502b9945393e7e8f1d8b6481`. Druid and Keycloak were retried with the native `package` lifecycle; both exposed missing reactor tests JARs because `maven.test.skip=true` suppressed test compilation, so follow-up retries retain test compilation while still skipping test execution. Presto's generated OpenAPI specification was preserved in the run artifact quarantine and the exact preflight source fingerprint was restored. Its targeted core-package retries excluded the UI from the selected reactor but still activated the UI frontend build through dependencies; all JDK attempts failed on Yarn download timeouts, with the first also encountering a truncated Central download, so Presto remains fail-closed. All retries retain the same strict source-fingerprint and promotion gates.
- The system-JDK-25 tranche natively repaired and promoted `apache/hertzbeat`, `apache/syncope`, `dependencytrack/dependency-track`, `jamebal/jmal-cloud-server`, and `tess1o/geopulse`; each build exited zero under CodeQL, retained its exact source fingerprint, and produced a strict native attestation. `thingsboard/thingsboard` entered its native Maven build and generated fingerprint-relevant Angular compiler-cache output, but the build ultimately failed because `maven-dependency-plugin:unpack (extract-web-ui)` could not find the expected packaged web-UI artifact. CodeQL therefore did not finalize a usable database; the drift gate retained only the failed skeleton candidate under an attempt-specific `.source-drift` path and withheld promotion. Because this archived source is not an independent Git checkout, recovery quarantined only the three files whose timestamps fell inside the failed build interval, recorded their sizes and SHA-256 digests, and reproduced the exact pre-build tree fingerprint `bf92109a4da088ac1d2fcfaf78fe5d3a3ba76badb6164e00fc0cc5d48a469672`; no broad `target`, Node, or source-tree deletion was performed. The tranche therefore completed with five successes and one fail-closed build failure.
- A Kestra retry excluding the known Gradle 9 `sourcesJar` validation failure completed the native `assemble` task, but all Java compilation tasks were `UP-TO-DATE`; CodeQL correctly rejected the database because no compilation was captured. The authorized follow-up forced `--rerun-tasks --no-build-cache`, completed the native Gradle build under JDK 25, retained its exact Git fingerprint, and promoted a strict database with fingerprint `34d4303bfa8835966f3e0a90b9b68e25afe73ad88d3c4c4e539738ee62adcdb1`. Runify's first JDK 25 retry cleared the previous compiler-release blocker but exposed its backend Antrun move of an absent skipped `frontend/dist`; the authorized follow-up selected only `backend` and used the plugin-supported `maven.antrun.skip` property, retaining native backend javac capture without building the frontend. It passed strict validation and promoted database fingerprint `cc91de8ecdef4bc63bf3d2cea39a2ec56d54a7b56e22514120250ab05e28ab07`. Both databases also pass `codeql resolve database`.
- Guacamole's targeted `guacamole-common-js,guacamole` Maven reactor generated the required JavaScript ZIP before compiling the Java WAR and exited zero under CodeQL. The build produced 510 fingerprint-relevant Node/frontend distribution files; each was size/SHA-256 manifested and moved to run-specific generated-source quarantine, restoring the exact pre-build tree fingerprint `169232ebca426df1cdf6073439673251733959dfd16542443f1131b4d24f3710`. The preserved candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion. Its canonical database fingerprint is `39f09db71c8032ee0531eb7385c62178423b926cdfe5a0e7cc86e68c5889799c`.
- ThingsBoard's targeted `msa/web-ui,application` Maven reactor initially failed because `maven.test.skip=true` suppressed the reactor-produced `dao` tests JAR. Retaining test compilation while skipping test execution allowed the 20-minute JDK 25 Maven/CodeQL build to complete successfully, including real `application` Java compilation. The three generated Angular compiler-cache files were size/SHA-256 manifested and quarantined, restoring exact source fingerprint `bf92109a4da088ac1d2fcfaf78fe5d3a3ba76badb6164e00fc0cc5d48a469672`. The preserved candidate passed repeated strict validation and `codeql resolve database` before guarded promotion with canonical database fingerprint `94e071350840d32bdf161d364273a59378fe752ea8a02ce77b773d8664d3caa6`.
- PublicCMS succeeded through its complete JDK 17 Maven reactor rather than the previously attempted Gradle or isolated OAuth entry. The native package capture retained its exact Git fingerprint and promoted strict database fingerprint `da7e7e0172a194cb489b157d7b2fb83fff593f4bc41dd7f766b744d42f848a57`.
- GeoServer avoided the incompatible GWC module by selecting the `main`, `security`, `ows`, `rest`, and `restconfig` Maven reactor under `src`. The native JDK 17 build and CodeQL finalization exited zero. Seven generated `.spotless-index` files were size/SHA-256 manifested and quarantined, restoring exact tree fingerprint `2abc7df0a2bc5751ab80f608d74dd7a78311c43e4b349a4b1cf4464e66d727fa`; the candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion with database fingerprint `0a992f4fd75bb9e7dca9c718cc6ee069251a74f3983310b4d5fd5717f47064a2`.
+- App Platform avoided the failing `tool-maven-plugin:build-tool` execution by selecting the substantial `waterflow-service` Java module and its native reactor dependencies. The JDK 17 `clean compile` capture exited zero, retained exact Git commit `dd242b21cb136c871b1658b9594616a29a2f8246`, passed strict validation and `codeql resolve database`, and atomically replaced the invalid default database while preserving it in run-specific quarantine. The promoted database fingerprint is `cf3f0312d97763e55611dc4bcec922b8dc1ff3baefa0b73ce3789a369fbac11b`.
+- Concord avoided incremental no-source capture by selecting the production `server/plugins/webapp` and `server/impl` reactor union, running `clean compile`, and disabling Maven incremental compilation. The JDK 17 Maven/CodeQL build exited zero, retained exact Git commit `9caa877161aff11501bc01c9a2ea51d99f7e1d80`, passed strict validation and `codeql resolve database`, and atomically replaced the invalid default database with fingerprint `65ed6b413e4f2786a58ccd78c4a79ea287a6a43e83547232ef9f30e815266ac9`; the prior directory remains in run-specific quarantine.
+- MeterSphere's targeted `backend/app` JDK 21 reactor used the project-specific `skipAntRunForJenkins` property, compiled the production backend modules, exited zero, and completed CodeQL finalization. Forensic comparison against the preserved local source archive identified nine generated flattened POMs responsible for the remaining drift; each was SHA-256 manifested and moved to run-specific generated-source quarantine, restoring frozen source fingerprint `c41596653a795eed0d274a371b0b1bf93edecd7e1aa0c15b269456ac90d7e55f`. The preserved candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion with database fingerprint `e7c072c7fa8d53d1056b649b6f8061afa89b564a67544d7d9a1cbdd17fa7dced`.
+- Micrometer's Kotlin-bearing core remains beyond the installed extractor's Kotlin ceiling, so the strict native capture selected the production `micrometer-commons` module, which contains Java sources and does not require a Kotlin compilation task. A forced no-cache JDK 17 Gradle `compileJava` run exited zero, retained exact Git commit `24b886850814780f5f7bcdeb7d35cf25bc8ccd8a`, passed strict validation and `codeql resolve database`, and replaced the invalid default database with fingerprint `575df0ea46062711ae03f3d8cee30ec78f1461ac304c86d370a45b62ffa4d5bc`; no Kotlin task was excluded from the selected module's native task graph.
+- Yuzi Generator's checked-in backend Maven wrapper was incomplete and its web backend required an uninstalled maker artifact, so the strict capture selected the repository's real `yuzi-generator-maker` Maven project using system Maven. Its JDK 17 `clean compile` exited zero, retained exact Git commit `a2a0edb2cbbb6a869196b6b8a85e6ad30bbb635c`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `8b34ad27602685fe7990229b3934aebe6cb4d9307b2c424215db16c149482696`.
+- Automon's aggregate build previously failed when a sample module attempted to resolve the reactor's snapshot core artifact externally. Selecting the production `automon` module directly allowed a JDK 17 native `clean compile` capture to exit zero while retaining exact Git commit `815e9d0ea1360d8a93e6f241ada1f76c4fb9dfb6`. The database passed strict validation and `codeql resolve database` and was promoted with fingerprint `e085a453df4444c3de9cc5fef651c74c45106f980cf5c0a0e777a56066031234`.
+- Zeus IoT's aggregate `iot-server` path reached a real source/dependency API defect in `server-core`, so the strict native capture selected the concrete production `server-client` JAR and its Maven reactor dependencies rather than the POM-only aggregator. The JDK 17 `clean compile` capture exited zero, retained exact Git commit `b314c05a497dc0901cb658f8704e2efa62953cb4`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `e7ec38cdc0eafe3982580a02620bd7046d9760fb1f35efe9aabbbc3769533a91`.
+- Warm Flow's first narrowed selection was still a POM-only aggregator and correctly produced no CodeQL source capture. Selecting the concrete `warm-flow-easy-query-core` production JAR and its reactor dependencies executed a JDK 17 Maven `clean compile`, retained exact Git commit `5d04c41835302b9a3ec4e01d04a8481339497efd`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `31561b9e1fcbc6d7b5a6c976dbb12035d204f643bdfb69e24566a457ba88e559`.
+- dotCMS required JDK 25 and reactor-produced package artifacts rather than the earlier JDK 17 compile attempt. A targeted `dotCMS -am package` build ran for roughly 24 minutes under CodeQL, exited zero, retained exact Git commit `48102262b97e9fc510562f0eaeb5f83b54370a28`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `69b74184671393d4ce01dab091dec679b77ba036e7bc7f099646d65c373ccb5d`.
+- CommaFeed's empty client module did not create the directory expected by the server's Quarkus generate-code phase. After staging that native reactor precondition under the build-excluded `target` tree, the JDK 25 `commafeed-server -am compile` capture executed the production server compilation, exited zero, retained exact Git commit `77b3c609f33564398b099a652e0aa3fcdc43c3a4`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `6f568f1ecc91e995136cdc6e508c7fc217cb4aafa347bbd7bc8a5185a02e3e38`.
+- OneDev's root reactor was incomplete because the declared `server-ee` module was absent, but its existing production `server-core` project was independently buildable. A roughly 21-minute JDK 17 Maven `clean compile` capture exited zero, retained exact Git commit `5beff944c99e514f327eafa7d35bb65725449cf0`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `f0e22defe290eb072abe6663cea0f71a3b81fb7700c3fe91fa3c6fc1099984a7`.
+- Keycloak's archived source contained a generated pnpm symlink unsupported by canonical tree fingerprinting. The link was moved to run-specific source quarantine, yielding stable source fingerprint `6e8970b3568e538f57753178a773698285eaaff0c03723a70e91cc3b65a99013`. A clean JDK 17 native build of the `theme-verifier` Maven plugin then compiled production and test-support Java while skipping test execution, exited zero, and finalized a strict database. The candidate passed repeated validation and `codeql resolve database` before guarded promotion with database fingerprint `57ba15d240a141c26cdbcdd999b5a70acf0f2d1e8a187af8e4d365a0e1da89f8`.
+- Presto's `presto-server` Provisio assembly requires 44 reactor-produced plugin ZIPs that Maven dependency closure alone does not schedule. The final JDK 17 native package capture selected all 44 modules extracted from `presto-server/src/main/provisio/presto.xml`, plus `presto-flight-shim`, `presto-main`, and `presto-server`. The roughly 15-minute Maven/CodeQL build exited zero, retained exact source fingerprint `85510e107d6906bf3dc6f2303cfdbe507e3094720928389cf2119fb757935558`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `65e73b7598f3b40fd7c8dc9e5c2cc54e39e55971716e53224b98a56f652b596b`.
+- XBoot's modular reactor could not resolve the deliberately repository-only `xboot-admin` parent, while the same repository's standalone production `xboot-fast` application contains 162 Java sources and is independently native-buildable. Its JDK 8 Maven `clean compile` exited zero under CodeQL, retained exact Git commit `5277af0ea7db3cf085f8ef3be21329df5bb12cd9`, passed repeated strict validation, and atomically promoted database fingerprint `2e37267443decff808b7527867259c8bd2135346d74e49afae997c71bf5496f0`; the prior invalid database remains in run-specific quarantine.
+- Native repair overrides now support an ordered `setup_commands` list for repository-native Maven/Gradle/Ant prerequisite lifecycles. Setup commands use the same selected JDK, sanitized environment, build root, controlled Maven settings, and run-local Maven repository as the CodeQL-captured command; they remain outside capture, fail closed before capture, are source-fingerprint gated, and are bound into resumable attestations.
+- Spring Cloud Platform avoided the broken `ace-nlp` child model by staging only the root parent, `ace-dev-base`, `ace-common`, `ace-auth-sdk`, and `ace-api` into one isolated Maven repository before capturing the concrete `ace-gate` production module. All five JDK 8 setup lifecycles and the final native `clean compile` exited zero, retained source fingerprint `0039e468f6df61cf9f397edd8ec7aacd7cddd6c634da2a79c846047fb82cf49b`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `b182361c89d81da54f0726b1be0abb616743d9af9f6bc70043892d0668047bea`.
+- SkyEye's primary Maven hierarchy was blocked by the unavailable `skyeye-parent:1.0-SNAPSHOT`, but the repository contains an independent, parent-complete XXL-Job 2.3.0 production reactor. A JDK 8 native `xxl-job-admin -am clean package` capture compiled the 114-source admin/core application, exited zero, retained exact Git commit `217901aeb65b433c5f9d27c64896c2dfde649dc5`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `d7e69cad4284959a7962ea7b2a27f5d3c3ec293df23328979b5ac6a05eed3e8a`.
+- Suwayomi Server required Kotlin 2.4.0, beyond the prior CodeQL 2.23.8 extractor ceiling. The official CodeQL CLI 2.26.0 bundle was integrity-checked, restored with its archived executable modes, and used in isolation without replacing `/opt/codeql`. A forced no-cache JDK 21 Gradle `:server:compileKotlin` run captured the production Kotlin reactor and dependencies, exited zero in roughly four minutes, retained exact Git commit `c8f5d83e9cca295a5a00f792de87354131e40052`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `fc870233011d78784a3a892956447becd58b27349d39e24768762f21778c384f`.
+- Lamp Cloud's unavailable 5.10.0 parent and utility artifacts were reproduced from the exact companion `zuihou/lamp-util` commit `124a9ea320304d7994879f056117f67e108773d0` in an isolated Java 17 Maven reactor and run-local repository. The unchanged canonical Lamp Cloud commit `ee893ed6f43cd2551b5cc8bb48ea70160681f1f7` then completed a native `clean compile` under CodeQL in roughly three minutes, retained its exact source fingerprint, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `321bdd40f18b7844c879e9c51c071621a55d36db117dbf7a59abfc3e26781fea`.
+- Kogito Runtimes' `999-SNAPSHOT` parent and dependency chain was reproduced from exact contemporaneous `apache/incubator-kie-drools` commit `b6fc3f0050bd1e818392bef0597ac488c05ffc19` in an isolated Java 17 Maven reactor. A full Kogito package attempt reached unrelated Quarkus integration-test dependency timeouts after 161 modules, so the strict capture selected the substantial production `jbpm-bpmn2` module and its required native reactor closure. The targeted `clean package` compiled the 115-source BPMN module, exited zero, retained canonical commit `acd78d9249ee75923a0e5e43a332bbc6c1fd0c1b`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `218b67327964bbcdb055ad0f268cc0647aa9417ac7d57c898ea34d7a343e5873`.
+- SkyWalking's GitHub source archive omitted its protocol gitlink content. Exact root commit `bb16533009a597dbb41ab6f013ac300509abbb3e` and protocol commit `07882d57becb37e341f7fc492c11f9f5a5f311cf` were recovered and built in an isolated upstream reactor, including `apm-network`, the `oap-server-bom`, and the internal dependencies required by `server-core`. Three historical generated flattened POMs absent from the original archive were digest-manifested and moved to run-specific source quarantine. The canonical 793-source `server-core` compile then exited zero under CodeQL with flattening disabled, retained source fingerprint `bb3201bdb276009e02cb11ff07b0f661cdae31381a39d065fef369e0bcc5dcbb`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `c6ee05dddd5972e85b55972eefcc45c48530c0ce11071884ba205087ef476b20`.
+- ShoppingCart's former canonical merge commit `4ea0067bf2520ddd9b3332b627e5e01d50b4907b` contains an upstream regression that replaces two valid `RequestMapping` annotations with `GetMapping` without importing the latter, making the sole Maven source set unbuildable. Following an explicit corpus decision, the source was provenance-recorded and repinned to public pre-regression commit `c992c54bde6af51f67d8cfec5cdba6cbcda19f6c`. Its JDK 8 native Maven compile exited zero, retained the new exact Git fingerprint, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `2a4b27ab10c5a54909305a34837eb850b2579a17700db93407799c040df6d04f`.
+- The regenerated canonical Java Web 205 inventory now reports `205/205` strict databases, zero incomplete targets, and `batch_ready: true`, with inventory digest `94cda8008abaa0126eb6dfa65b7fa1c68c153086e26d427a32269bbb99e038db`. The strict corpus loader accepts all targets, and a nonexecuting 205-target batch plan was generated with plan digest `408f9d861f75fcd5560a8a9ea0af8093624a5ec193d79c1efa682c0482d931e4`.

This changelog starts at the v2 cleanup baseline. Older analyzer runs and case-level research history remain available in Git history and preserved result directories rather than in the active project changelog.

## [2026-08-04] Add JAX-RS and gRPC Entry identities

### Added

- Added first-class `jax_rs/http` and `grpc/grpc` Entry identities with strict model, decoder, normalization, artifact-schema, coverage, and benchmark compatibility while preserving the exact 17-column contract.
- Added direct and embedded byte-identical `JaxRsEntries.ql` and `GrpcEntries.ql` queries. JAX-RS recognizes javax/jakarta Path, HTTP verbs, parameter/entity-body inputs, and statically provable ResourceConfig/register, Airlift binder, and Druid-style resource registrations; annotation-only resources remain coverage-only.
- Added conservative gRPC `BindableService` registration for unary/server-streaming-shaped handlers using the real `io.grpc.stub.StreamObserver` API. Request materialization remains `in_handler`; client/bidirectional streaming and descriptor-derived wire identity remain unresolved rather than inferred from response `onNext` calls.
- Added focused registered-positive, unregistered/lookalike-negative fixtures and benchmark identity regressions. gRPC matching now requires exact `grpc` protocol and full case-sensitive route identity; HTTP route-only truth remains valid and case-sensitive, while explicit method conflicts fail closed. Title, handler-name, resource-token, class-name, callback-name, and port guesses are not matching evidence. Multiple handler facts are merged only when they share one complete registration identity; otherwise ambiguity is preserved.
- Corrected JAX-RS route canonicalization, parameter-kind exclusivity, multi-argument registration scanning, and complete/partial overlap. Registered JAX-RS and gRPC handlers no longer also emit unresolved coverage rows.
- Corrected Spring input-kind exclusivity so explicitly annotated parameters and servlet request infrastructure are not simultaneously emitted as model attributes; real-database smoke scans are treated as coverage observations, not dynamic confirmation.

### Verification

- Corrected Spring MVC, JAX-RS, and gRPC queries compiled under the local CodeQL Java pack, and the final opt-in real CodeQL fixture run passed all seven controlled framework fixtures in 191 seconds, including exact JAX-RS routes and registered-versus-unresolved separation.
- Focused Entry, decoder, artifact, production, benchmark, and query-contract validation passed 103 Python tests; direct/embedded query parity, Python compilation, and whitespace validation also passed.
- A fresh local-only PoC-29 Entry batch completed 18/18 targets with the seven isolated database overrides and `max-workers=1`; no remote LLM, application startup, dynamic PoC, attack traffic, clone, or network database rebuild was used. The run produced 1,832 Entry facts (`spring_mvc`: 1,828; `netty`: 4), with Entry diagnostics of 6 `entry_hit`, 1 `entry_ambiguous`, 22 `no_entry_match`, 0 `target_not_run`, and 98 coverage gaps. These are Entry-stage diagnostics only; the entries-only run has 29 expected `artifact_missing` final-static states and does not establish static recall or dynamic confirmation.
- The same run produced no JAX-RS or gRPC facts on the current bounded databases. That result is retained as an explicit coverage limitation: generated/DI registration and descriptor-derived gRPC identities remain unresolved rather than guessed.

## [2026-08-04] Expand existing Java Web Entry extraction coverage

### Changed

- Expanded the existing Spring MVC, Netty, MQTT, Servlet, and filter Entry queries conservatively while retaining the exact 17-column table contract and byte-identical direct/embedded query copies.
- Spring mappings now recognize compile-time route arrays, mapping verbs, servlet request parameters, explicit model attributes, and uniquely typed unannotated command objects while excluding common framework infrastructure parameters.
- Netty recognizes statically registered `channelRead0` callbacks alongside `channelRead`; JMQTT `Object` callbacks remain complete only when a local MQTT-message cast is consumed by a processor, and SMQTT remains a partial dispatch gap.
- Servlet query support includes Jetty-style static holder bindings and verb-bearing servlet routes where the Java binding is unique; dynamic/reflection registrations remain coverage-only.
- Added verb-aware route canonicalization for HTTP Entry identities without changing non-HTTP event routes.

### Verification

- The earlier broad opt-in fixture sweep was not a reliable completion claim because Spring MVC, Servlet, and Netty each reached the 300-second per-test timeout in that run. A later controlled seven-fixture Entry run completed successfully after the JAX-RS/gRPC corrections described above.
- Query compilation, whitespace validation, and direct/embedded parity checks passed for the corrected JAX-RS/gRPC queries; focused Python Entry/benchmark tests passed.
- Descriptor-only `web.xml`, dynamic/reflection/DI registrations, descriptor-derived gRPC identities, client/bidirectional gRPC streaming, and unproven MQTT conversions remain deliberately unresolved.

## [2026-08-03] Migrate the active canonical corpus to Java Web 205

### Changed

- Defined the active corpus as the case-insensitive repository union of the preserved canonical Java Web 200 inventory and the PoC-29 repository set: 200 original targets plus exactly five additions at indices 201 through 205.
- Added a deterministic Java Web 205 inventory generator and tracked manifest while preserving the historical Java Web 200 manifest, repair utility, generated results, and target identity fields at indices 1 through 200 unchanged; readiness fields are deliberately recalculated.
- Switched the canonical corpus loader and batch CLI default to `intel/applications/java_web_205_targets.json`; strict loading now rejects a manifest whose recorded database readiness is incomplete.
- Added active-corpus documentation and regressions for union construction, ordering, case-insensitive deduplication, default paths, and readiness reporting.

### Readiness

- The generator strictly revalidates all 205 default databases and source-root bindings instead of carrying forward historical marker-based readiness. On the current filesystem the tracked manifest records 150 strictly valid default paths, 55 incomplete default paths with an explicit repository/reason list, and `batch_ready: false`; dataset membership remains 205.
- Separately, the seven incomplete PoC-29 databases were rebuilt under `build/poc29-codeql-dbs/` using explicitly risk-marked, PoC-relevant bounded CodeQL extraction after native Maven/Gradle attempts exposed dependency, generated-source, proxy, and JDK 25 blockers. All seven isolated databases pass the production validator and source-root checks, allowing PoC-29 to reach 18/18 readiness through explicit overrides without modifying historical default databases.
- A complete local entries run then finished 18/18 targets with no remote LLM or dynamic execution. Entry extraction produced 7 facts, all from Zipkin; the `/api/v2/spans` truth remains a deterministic three-overload `entry_ambiguous`, while the other 28 truths remain `no_entry_match`. The bounded rebuilds therefore remove `target_not_run` but do not by themselves expand framework Entry coverage.

## [2026-08-03] Expand MQTT broker and Armeria entry extraction

### Added

- Added end-to-end MQTT `broker_registration` entry support without changing the 17-column CodeQL table contract; partial and dynamic rows remain coverage-only and never become entry facts.
- Added high-confidence JMQTT anonymous `ChannelInitializer` broker recognition and conservative SMQTT Reactor Netty coverage gaps where connection-to-protocol dispatch cannot be uniquely bound, plus statically registered Armeria `@Post`/`@Get` annotated services including Zipkin `/api/v2/spans`.
- Added broker/Armeria fixtures, registration/schema regressions, and benchmark matching for MQTT protocol-service descriptions without port-only matches.

### Verification

- A fresh local-only 11-target entries run completed 11/11 targets with remote LLM and dynamic execution disabled. Entry facts increased from 1 to 7; all seven were Zipkin entries, and the PoC `/api/v2/spans` truth produced a deterministic three-overload `entry_ambiguous` result. JMQTT remained a coverage gap on the historical database, and SMQTT remained an explicit `smqtt_protocol_dispatch_binding_unresolved` partial gap rather than a guessed hit.
- Real CodeQL fixtures passed 2 tests; focused Entry/benchmark coverage passed 86 tests; query-pack parity, Python compilation, and diff validation passed.

## [2026-08-03] Diagnose PoC-29 entries-only benchmark runs

### Added

- Renamed the independent benchmark manifest identity to `poc-29` and added strict entries-stage artifact extraction with run/stage binding, digest, byte-count, record-count, and schema validation.
- Added deterministic repository/route/method/protocol entry diagnostics, coverage-gap reporting, and CLI `entry_diagnostics.jsonl` / `entry_summary.json` outputs without treating entry hits as static recall.
- Added runtime validation against the preserved local entries-only archive.

## [2026-08-03] Add PoC-29 benchmark baseline

### Added

- Added network-free PoC-29 truth normalization for 29 cases across 18 repositories, independent source/database asset binding, explicit repository spelling normalization, deterministic P0 candidate snapshots, fail-closed matching states, recall-only evaluation, and a baseline CLI.
- Database validation now uses the strict CodeQL validator: the real baseline exposes 7 incomplete databases and 11/18 ready entries. Truth remains valid at 29/18, while complete batch readiness is false; ready-only plans are explicitly diagnostic and not complete recall runs.
- Added strict repository-relative database overrides and fail-closed complete-plan checks.
- Added synthetic and real-inventory benchmark regression tests.

## [2026-07-28] Add canonical Java Web 200 batch orchestration

### Added

- Added strict canonical-corpus validation, source/database provenance checks, immutable batch plans, target identity bindings, bounded concurrency, atomic batch state, failure isolation, and resumable per-target production execution.
- Added local-only `entries` batches and explicitly authorized `full` batches. Environment provider credentials are stripped from Entry-only workers, while tree-fingerprint targets remain paused when public Git commit attestation is unavailable.
- Added format-separated normative P0 aggregation with target/run/stage binding, artifact hash/count/size validation, structured gap accounting, atomic publication, and exact three-value static-verdict totals while preserving historical hunter aggregation. Aggregation now rejects ambiguous format auto-detection instead of silently treating P0 records as historical.
- Added digest-bound non-secret provider settings to batch plans and a non-executing `full --plan-only` path; full execution still requires explicit remote consent and an environment-only provider key.

### Verification

- Added network-free batch plan, runner, aggregation, resume, authorization, identity, concurrency, stale-artifact recovery, and compatibility regressions; the complete default suite now passes 494 tests with 6 guarded integrations skipped.
- No real DeepSeek request, corpus analysis run, service launch, attack traffic, or dynamic DoS validation was performed.

## [2026-07-28] Complete the production P0 analyzer

### Added

- Connected all six default production executors for Entry extraction, G1–G4 Growth classification, E→G flow proof, lifecycle evaluation, deterministic conclusions, and certificate-consistent reporting.
- Added durable strict round trips for Growth, Flow, Guard, Bound, Release, lifecycle decision, certificate, and finding artifacts, with authoritative resume reconstruction and downstream invalidation.
- Added a complete immutable query-pack snapshot across Entry, Growth, Flow, and Lifecycle query families and a network-free injected full-graph production test.

### Security and correctness

- Preserved pinned-source excerpt validation, explicit remote consent, environment-only API keys, atomic provider-stage publication, conservative partial-coverage handling, and static-only verdict wording.
- Required the selected commit to be reachable from the public repository's default branch, required the CodeQL database source root to match the pinned checkout, and blocked credential assignments in comments and credential-bearing Java mutator/header calls before provider use.
- Made lifecycle decisions durable and schema-validated, rejected forged nested decision summaries/IDs, and ensured any partial sibling flow forces `static_unknown` rather than being discarded from conclusion evidence.

### Verification

- Final default discovery ran 462 tests successfully with 6 guarded integrations skipped.
- All 6 opt-in real-CodeQL Entry, Growth, and Lifecycle fixture tests passed.
- Python compilation, every CLI subcommand help path, and `git diff --check` passed.
- No real DeepSeek request, service launch, attack traffic, or dynamic DoS validation was performed.

## [2026-07-25] Migrate active consumers and document the P0 interface

### Changed

- Migrated active static aggregation and dynamic-scaffold traceability to the exact `static_vulnerable`, `bounded_under_modeled_assumptions`, and `static_unknown` vocabulary, rejecting the retired value and static-verdict field aliases rather than retaining a compatibility path.
- Preserved static/dynamic independence: the dynamic scaffold copies a static verdict only under traceability metadata while retaining `paused`/`blocked` dynamic defaults.
- Reworked README and agent guidance to document Python and CodeQL requirements, mandatory DeepSeek behavior for complete P0 runs, the current fail-closed production executor boundary, stage/resume semantics, normative artifacts, exact verdict meanings, P0 framework/assertion scope, asynchronous Release limitations, coverage gaps, test opt-ins, and static/dynamic separation.
- Added dedicated verdict-migration regressions and physical JSONL source-location checks for rejected values and field aliases, including inputs with blank lines.

### Verification

- Final default discovery ran 416 tests successfully with 6 guarded integrations skipped.
- `codeql pack install codeql` succeeded with CodeQL CLI 2.23.8, and all 6 opt-in Spring MVC, Servlet, Netty, and MQTT entry/Growth/lifecycle fixture tests passed.
- Focused migration tests, Python compilation, CLI help, terminology scan, and `git diff --check` passed.
- Verification made no real DeepSeek request, did not start target services, did not send attack traffic, and did not run dynamic DoS validation.
- At that checkpoint, Task 7 remained partial because the production CodeQL/DeepSeek stage-executor factory was still deliberately unconnected; the 2026-07-28 entry records its completion.
- Per explicit user direction, the obsolete 2026-07-02 baseline design remains deleted as an approved preservation exception; the ignored 2026-07-18 design and plan remain unstaged until commit authorization.

## [2026-07-24] Add static conclusions, certificates, reports, and resumable orchestration

### Added

- Added deterministic Assertion 1 and Assertion 2 evaluation with the exact `static_vulnerable`, `bounded_under_modeled_assumptions`, and `static_unknown` vocabulary. Partial flow, unresolved lifecycle evidence, and relevant coverage gaps remain unknown; provider confidence never changes a verdict.
- Added canonical lifecycle certificates, certificate-derived static findings, deterministic summaries, and static-only Markdown reports with strict finding/certificate/verdict consistency.
- Added generic injected stage execution for `entries -> growth -> flows -> lifecycle -> conclude -> report`, deterministic fingerprints, exact resume reuse, mismatch invalidation, bounded canonical local payloads, strict manifest/artifact recovery validation, output-root locking, symlink refusal, stale-artifact reconciliation, and transactional publication/rollback.
- Added fail-closed CLI subcommand dispatch with controlled `AnalyzerError` and injected-factory failure handling. Production CodeQL/DeepSeek stage executors are not yet connected by the default factory, so direct production commands fail closed rather than claiming analysis success.
- Added network-free P0 scenario coverage for materialization, allocation, persistent-map growth, queues, finite rejection, late Guards, incomplete Release, asynchronous consumers, Netty, and MQTT.

### Verification

- Final default discovery ran 356 tests successfully with 6 guarded integrations skipped.
- Focused assertion, certificate/report, pipeline recovery, artifact, configuration, and P0 end-to-end suites passed; Python compilation, CLI help, and `git diff --check` passed.
- Independent review findings became regressions for scoped coverage, overlapping coverage patterns, forged assertion/verdict/certificate identity, strict lifecycle booleans, active verdict vocabulary, report disagreement, malformed resume metadata, manifest/hash/count tampering, duplicate and symlinked paths, stale artifacts, rollback, factory errors, and bounded payload handling.

## [2026-07-24] Prove entry-to-growth flows and evaluate lifecycle evidence

### Added

- Added normalized E→G `FlowProof` construction with stable identities, strict attacker source/demand mapping, dangling-reference failures, canonical artifact validation, and audited proven/partial verification.
- Added deterministic Guard, Bound, and synchronous Release decisions with structured checks, stable reasons, modeled finite-configuration matching, receiver/dimension/scope joins, and unresolved asynchronous-release retention.
- Added exact-column candidate-only CodeQL queries for direct entry-to-growth flow, Guard, Bound, and synchronous Release evidence, plus Spring, Servlet, Netty, and MQTT lifecycle fixtures.

### Verification

- Final default discovery passed 295 tests with 6 guarded integrations skipped; focused Task 6 tests, Python compilation, and `git diff --check` passed.
- Explicit local CodeQL lifecycle fixture verification passed across all four framework databases, and all four Task 6 queries compiled against the local CodeQL Java pack graph.
- Independent reviews drove regressions and remediation for same-handler false flow proofs, incomplete coverage upgrades, forged flow identities, configuration mismatches, cross-receiver Bounds, Release scope/dimension/key semantics, mixed asynchronous Release evidence, and malformed flow artifacts.

## [2026-07-24] Verify four resource growth classes

### Added

- Added frozen G1–G4 Growth candidate normalization with deterministic resource/growth identifiers, sorted demand/evidence merging, strict raw-row validation, and exact `growth_candidates` artifact serialization.
- Added canonical bounded-slice construction and deterministic Growth Contract verification with audited `verified|rejected|unresolved` results, stable reason codes/checks, strict slice/index evidence identity, and no fabricated static facts.
- Added exact-column CodeQL screening queries for request/message materialization, direct buffer and array allocation, persistent container growth, and field-backed asynchronous work submission.
- Extended Spring, Servlet, Netty, and MQTT fixtures with G1–G4 positives, request-local/lookalike negatives, finite/unbounded queue forms, and guarded real-CodeQL semantic tests.

### Verification

- Final default discovery ran 255 tests successfully with 5 guarded integrations skipped; focused Growth/artifact suites and Python compilation passed.
- Explicit `DOSWEB_RUN_CODEQL_FIXTURES=1` verification passed both Growth query tests across temporary fixture databases; all four Growth queries compiled against the local CodeQL pack graph.
- Independent reviews drove regressions and remediation for fabricated evidence, empty/cross-candidate evidence verification, malformed identifiers, evidence-ID collisions, array-allocation coverage, collection demand roles/scopes, local async receivers, G1 lookalikes, and nested artifact validation.

## [2026-07-24] Extract registered framework entries

### Added

- Added frozen registered-entry, attacker-input, registration, handler, and framework-coverage models with deterministic semantic identifiers, strict framework/protocol pairings, canonical HTTP routes, sorted input deduplication, and bounded analyzer errors.
- Added deterministic entry-row normalization that separates unresolved dynamic registrations from reachable entries, validates both supported and gap rows, and emits explicit coverage records for Spring MVC, Servlet, Netty, and MQTT even when a framework has no extracted rows.
- Added four exact-column CodeQL table queries requiring framework-specific registration/type evidence: Spring controller mappings, Servlet annotation registrations, Netty pipeline registrations, and MQTT subscribe/listener bindings. Recognized unresolved registration patterns emit partial coverage rather than fabricated reachability.
- Added self-contained Java source fixtures with registered handlers, unregistered/lookalike negatives, and dynamic-registration gaps, plus guarded real-CodeQL semantic tests.

### Verification

- Final focused Task 3/4 verification ran 41 tests with 39 passed and 2 guarded CodeQL fixture tests skipped by default; the complete default suite ran 243 tests with 240 passed and 3 guarded integrations skipped.
- Explicit `DOSWEB_RUN_CODEQL_FIXTURES=1` verification passed both real-CodeQL tests across all four temporary Java databases, exact decoded columns, registered-entry expectations, lookalike exclusion, and forcing coverage gaps.
- All four entry queries compiled against the locally installed `codeql/java-all` dependency graph, all Java source fixtures compiled without leaving `.class` artifacts, changed Python files compiled, and `git diff --check` passed. Independent reviews drove remediation for framework lookalikes, protocol mismatches, incomplete coverage validation, sparse coverage records, unresolved registration gaps, and unrelated-reflection coverage poisoning.

## [2026-07-24] Add strict Task 3 CodeQL execution contracts

### Added

- Added bounded CodeQL database validation with strict metadata parsing, stable metadata-file fingerprints, source-root provenance, symlink rejection, and controlled `CODEQL_DATABASE_INVALID` failures.
- Added a two-stage CodeQL query/BQRS runner with minimal secret-free environment inheritance, one shared deadline, bounded diagnostics, descriptor-validated immutable root-query snapshots in the original pack context, database-drift checks, TERM/KILL process-group cleanup, and atomic per-generation publication after validation and BQRS hashing succeed.
- Added fixed ordered `QuerySpec` contracts for entry, growth, flow, Guard, Bound, and synchronous Release candidates, with strict result-set, row, primitive type, enum, path, line, row-count, and string-budget validation.
- Added the minimal `dosweb/p0-java-resource-dos` query pack manifest using the installed CodeQL CLI's modern `dependencies` field, without query suites; individual queries remain deferred to later tasks.
- Added real-CodeQL compatibility remediation for timestamped database metadata, `{name, kind}` decoded column descriptors, strict decoded-result validation before publication, original pack-context query execution with persisted snapshots, and deadline propagation through bounded database and file hashing.

### Verification

- Final focused Task 3 verification passed 25 tests; the full default suite ran 227 tests with 1 guarded online integration skipped. `codeql pack ls codeql` resolved `dosweb/p0-java-resource-dos@0.1.0` under CodeQL CLI 2.23.8.
- Concurrent generation initialization/publication passed 10 repeated rounds; an additional focused stress sequence passed 5 rounds and 90 test executions.
- Changed Python modules/tests compiled and `git diff --check` passed. Independent Task 3 reviews drove regressions for query provenance drift, descendant-held process pipes, SIGTERM-ignoring descendants, and post-publication hashing; all were fixed within the root-query adapter contract.

## [2026-07-22] Complete fourth Task 2 consolidated remediation

### Changed

- Serialized cross-stripe cold cache production behind one fixed private process-shared capacity lock, preserving fixed key stripes, pre-provider capacity failure, immutable entries, and non-destructive no-eviction behavior.
- Replaced single-shot provider/GitHub body reads with incremental bounded reads under recomputed absolute deadlines, and propagated one shared verification budget across GitHub API and local Git operations.
- Added process-local same-key sharing for sanitized deterministic response failures without persistent negative caching; later independent calls may retry normally.
- Replaced plaintext provider request-ID audit persistence with a domain-separated API-keyed HMAC digest and bumped the authenticated cache format.
- Added high-confidence SSN-like PII rejection, complete Java compound-assignment coverage, annotation-aware Java declarator scanning, Java comment/octal/text-block literal reconstruction, component-aware credential identifiers, and bounded UTF-8 prechecks for hostile slice strings.
- Hardened independent-review boundaries: authenticated incompatible cache entries now receive capacity-gated live refresh without overwrite; crash temporaries count toward cache bytes; cache-entry HMACs have an explicit domain; timeout values are upper-bounded; permanent response-read failures do not retry; and complete GitHub slice verification shares one deadline.

### Verification

- Final focused Task 2 verification passed 169 tests; the full default suite ran 202 tests with 1 guarded online integration skipped; concurrency/deadline/publication stress passed 10 rounds and 90 test executions.
- Modified Python modules/tests compiled, parser-only CLI boundaries returned 0/2 as expected, and `git diff --check` passed. Independent review gate results are recorded in the Task 2 implementation report.

## [2026-07-19] Complete third Task 2 consolidated remediation

### Changed

- Hardened provider request-ID credential rejection, unbounded Java assignment scanning, Credential(s) classification, response echo filtering, permanent-network error handling, and one monotonic request deadline.
- Bound aliases and formal evidence to current config/growth identities; made cache fact IDs mandatory and authenticated audit fields fully identity-bound.
- Replaced per-key cache locks with 64 immutable stripes, removed memory growth, closed inherited flock descriptors, imposed non-destructive global capacity limits, and made unsafe/capacity/publication failures fail closed before provider use where required.
- Hardened Git deadlines/config overrides, JSONL mapping/publication/count behavior, strict config keys/Unicode handling, and explicit CLI remote-consent revocation.

### Verification

- Focused Task 2 command passed 146 tests; race/fork/cache/publication stress passed 10 consecutive iterations; full discovery passed 178 tests with 1 guarded online integration skipped.
- Changed Python modules/tests compiled, `git diff --check` passed, and parser-only CLI runtime accepted `--no-remote-llm` while rejecting conflicting consent flags with exit 2.

## [2026-07-18] Fix cold cache hierarchy creation race

### Changed

- Made descriptor-relative private cache hierarchy creation tolerate a concurrent trusted creator winning the `mkdir` race, so every same-key cold process reaches the shared `flock` instead of bypassing single-flight.
- Added a deterministic concurrent hierarchy-creation regression preserving the guarantee that exactly one cold producer publishes and a fresh cache reconstructs the durable contract.

### Verification

- The process single-flight test passed 20 consecutive post-fix iterations; the focused Task 2 suite passed 126 tests; full discovery ran 159 tests with 158 passed and 1 guarded online integration skipped.

## [2026-07-18] Complete second Task 2 consolidated remediation

### Changed

- Replaced regex-only Java credential assignment handling with Unicode-aware lexical scanning that preserves string/comment boundaries and detects sensitive identifiers independently of value syntax.
- Hardened YAML/config loading with bounded descriptor reads, regular-file and symlink refusal, duplicate-key/alias/tag rejection, path normalization, boolean precedence preservation, and strict URL-authority validation.
- Removed unbounded HTTP read fallback, normalized injected transport failures into retry exhaustion, added deadline-aware Git output collection and nonzero-runner rejection, bounded cache publication, and descriptor-relative private cache hierarchy creation for Linux/Python 3.11+.
- Added strict JSONL duplicate-key, structure, record-count, per-record, and aggregate limits; enforced artifact ID syntax/uniqueness and bounded `fact:` evidence IDs; preserved deterministic atomic publication.
- Preserved same-file relationships in provider aliases, exposed one canonical typed response schema, and strengthened fabricated-cache evidence validation with a recomputed valid HMAC.

### Verification

- Task 2 focused command passes 125 tests. Per-module discovery passes 26 artifact, 6 bounded-slice, 9 strict-growth, 21 config/CLI, and 63 DeepSeek tests.
- Full discovery passes 158 tests with 1 explicitly guarded online integration skipped. Changed Python modules/tests compile and `git diff --check` passes.
- Runtime CLI observation confirms the current Task 1/2 boundary remains parser-only: both explicit remote-consent arguments and default parsing exit 0 without analysis or network access.

## [2026-07-18] Harden Java Web DoS skill routing and dynamic validation

### Changed

- Routed bulk inventory, environment setup, probe execution, and fleet screening to `claude-haiku-4-5`; bounded semantic analysis and PoC engineering to `claude-sonnet-5`; and cross-stage reflection and final review to `claude-opus-4-8`, with evidence-coded escalation and model-usage artifacts.
- Made dynamic environment preparation reusable and autonomous within isolation boundaries, with explicit deployment classification and repair evidence required before `environment_blocked`.
- Added semantic preflight and a hard three-round PoC reflection loop that treats growth-only and no-growth observations as hypotheses to diagnose rather than final answers.
- Strengthened the user-level dynamic aggregator to discover missing results, validate status/schema/deployment/round/evidence/termination contracts, and derive verdicts centrally.

### Verification

- Added user-level skill and aggregator contract coverage for model aliases, worker-role separation, semantic preflight, the three-round cap, missing results, verdict conflicts, deployment classification, evidence paths, and split safety termination fields.
- Verified 22 focused dynamic-validation tests, Python compilation, and repository diff whitespace checks.

## [2026-07-18] Consolidate Task 2 independent-review remediation

### Changed

- Made provider response-body read failures retryable, bounded all slice/YAML/Git materialization and process output, reset inherited locks after fork, and safely create private nested cache paths.
- Added deterministic provider-facing aliases with local evidence restoration, exact final-request credential scanning with Java normalization, a complete typed prompt schema, strict formal Growth Contract artifact validation, IPv6-safe URL canonicalization, and stable malformed-URL errors.
- Exposed the Task 2 `--allow-remote-llm` consent/provenance CLI arguments without adding later-stage analyzer orchestration.

### Verification

- Added regression coverage for all verified review findings. The focused suite passes 90 tests; full discovery runs 134 tests with 133 passed and the guarded online integration skipped. Changed Python files compile and `git diff --check` passes.

## [2026-07-18] Authenticate and harden DeepSeek contract cache

### Changed

- Bound Growth Contract cache entries to the in-memory DeepSeek API key with HMAC-SHA256; cache files contain the authenticator but never the key, and unkeyed SHA-256 fields now provide integrity metadata only.
- Made cache use fail closed for unsafe local paths: cache directories must be current-user-owned `0700` directories, and lock, temporary, and entry files must be current-user-owned regular `0600` files. Directory-descriptor relative operations and `O_NOFOLLOW` are used where supported.
- Treat symlinked, permission-unsafe, or foreign-owned cache paths as cache misses with cache publication disabled, while allowing an authorized live classification to proceed. Preserved thread and cross-process single-flight behavior for safe caches.

### Verification

- Added focused cache coverage for HMAC tampering despite recomputed unkeyed hashes, wrong-key misses, owner checks, private modes, and symlinked directory, entry, and lock handling.
- Ran `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_cache_entry_requires_hmac_bound_to_the_api_key tests.test_deepseek_client.DeepSeekClientTests.test_cache_with_a_different_api_key_is_a_miss tests.test_deepseek_client.DeepSeekClientTests.test_cache_files_are_private_and_regular tests.test_deepseek_client.DeepSeekClientTests.test_symlinked_cache_directory_is_not_used tests.test_deepseek_client.DeepSeekClientTests.test_symlinked_cache_entry_is_a_miss_and_is_not_replaced tests.test_deepseek_client.DeepSeekClientTests.test_unsafe_permissions_and_lock_symlink_disable_cache_writes tests.test_deepseek_client.DeepSeekClientTests.test_cache_rejects_foreign_owner_when_lstat_is_mocked -v`, `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_same_key_process_single_flight_publishes_once_durably tests.test_deepseek_client.DeepSeekClientTests.test_same_key_thread_single_flight_makes_one_provider_request -v`, and `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_cache_entry_requires_hmac_bound_to_the_api_key -v` successfully.

## [2026-07-18] Add audited DeepSeek Growth Contract adapter

### Added

- Added an opt-in DeepSeek OpenAI-compatible Growth Contract client with strict schema validation, bounded retry policy, cache identity/integrity checks, atomic successful-response publication, and local mock coverage.
- Added a pre-network remote-source gate requiring explicit authorization, canonical public GitHub repository provenance, a full commit SHA, and a clean matching local checkout; default GitHub verification uses unauthenticated API requests and read-only Git checks, while authorization and provenance are captured only in non-secret request audit metadata.
- Restricted production provider endpoints to canonical `https://api.deepseek.com/`; loopback endpoints are permitted solely for local mocks, and all other endpoints fail before an Authorization header can be constructed.
- Added bounded-slice and Growth Contract models, constrained prompts, redaction of API keys, authorization values, and `sk-...` strings, plus a dual-guarded artificial-fixture integration test.

### Verification

- Verified with `python -m unittest tests.test_deepseek_client -v` and `python -m unittest discover -s tests -v`; default tests use localhost mocks and make no external provider request.

### Security remediation report (Task B: items 4, 5)

- Validated every LLM Growth Contract evidence reference against the static fact IDs in its bounded slice. Fabricated live references fail as `LLM_RESPONSE_SCHEMA_INVALID` before a cache write, while fabricated cached references are treated as cache misses.
- Applied strict byte, UTF-8, duplicate-key/non-finite-value, nesting, node, collection, and string limits consistently to provider-envelope, inner-contract, GitHub, and cache JSON. Reads request at most `limit + 1` bytes and map malformed, incomplete, or oversized data to controlled errors/cache misses.
- Preserved the cache HMAC and filesystem-authentication implementation without modification.

### Verification

- Verified the Task B fact-reference and JSON-boundary regressions with local mock/seam tests only; no live DeepSeek or GitHub endpoint was contacted.

### Security remediation report (Task C: items 3, 6, 7, 8)

- Validated Git object metadata before reading a source blob, rejected non-blobs and blobs over the bounded excerpt limit, and retained exact blob and excerpt hashes.
- Added the finite `MAX_LLM_RETRIES` bound at configuration and client runtime; blank API keys are accepted only while remote LLM access is disabled, while enabled access requires a nonblank environment key. YAML now rejects case and separator variants of `api_key` at every nesting level.
- Routed verifier Git commands through one hardened command form that disables fsmonitor and hooks, disables system/global configuration, replacement objects, and pagers; a local malicious `core.fsmonitor` regression confirms its helper is not executed.
- Ran `git fsck --strict --no-dangling --no-reflogs <full-sha>` through that hardened runner before any local source object access.

### Verification

- Passed focused Task C regressions with `python -m unittest tests.test_config_and_cli.ConfigTests.test_configuration_rejects_api_key_spelling_variants_at_any_depth tests.test_config_and_cli.ConfigTests.test_disabled_remote_llm_allows_a_missing_environment_key tests.test_config_and_cli.ConfigTests.test_enabled_remote_llm_requires_a_nonblank_environment_key tests.test_config_and_cli.ConfigTests.test_max_retries_has_an_explicit_upper_bound_in_cli_and_yaml tests.test_deepseek_client.DeepSeekClientTests.test_empty_api_key_is_rejected_before_verifier_or_network tests.test_deepseek_client.DeepSeekClientTests.test_runtime_config_rejects_max_retries_above_the_explicit_limit tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_hardened_git_invocation_disables_checkout_configured_helpers tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_validate_slice_rejects_oversized_git_blob_without_reading_it tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_verify_runs_strict_fsck_before_any_local_object_read -v`.

## [2026-07-18] Consolidate P0 implementation authority

### Changed

- Declared `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md` the sole implementation standard and updated repository guidance and README links accordingly.
- Hardened artifact recovery validation so a stage requires a non-empty artifact list and every artifact path is a safe relative path within the run output root.
- Completed lifecycle artifact contracts, canonical JSONL ordering, recursive YAML secret rejection, strict blank/UTF-8 JSONL failure handling, and output-root-relative artifact metadata serialization.

### Verification

- Added regression coverage for missing, empty, malformed, absolute, and escaping artifact paths during stage reuse.
- Added focused contract coverage for lifecycle artifact minima, deterministic JSONL bytes, nested YAML secrets, and strict JSONL input failures.

## [2026-07-18] Design the complete P0 analyzer

### Added

- Added the approved full-P0 analyzer design for Spring MVC, Servlet, Netty, and MQTT.
- Defined the Python and CodeQL module boundaries, versioned artifact contracts, bounded-slice DeepSeek Growth Contract, deterministic lifecycle rules, assertions 1 and 2, lifecycle certificates, recovery model, and test strategy.

### Changed

- Chose `bounded_under_modeled_assumptions` to replace the unconditional `static_safe` label during implementation; active tooling and documentation will be migrated together without a legacy compatibility mode.
- Required DeepSeek through an environment-only API key for complete P0 runs while keeping default tests network-free and provider calls auditable.

### Verification

- Reviewed the design for placeholders, internal contradictions, ambiguous verdict behavior, secret handling, and scope boundaries.
- Added P0 package, environment-only configuration, strict JSONL artifact contracts, deterministic identifiers, and resumable-stage primitives.
- Verified with `python -m unittest tests.test_config_and_cli tests.test_artifact_contracts -v` and `python -m unittest discover -s tests -v`.

## [2026-07-17] Prepare the v2 tool-development baseline

### Changed

- Restored the preserved v2 engineering specification and retired the obsolete one-time cleanup plan and Stage 0–5 research design.
- Adopted the lifecycle-centered analysis direction based on bounded slices, Growth Contracts, lifecycle evidence, and effective Guard/Bound/Release reasoning.
- Normalized paper material under `docs/paper/` and repaired active documentation links.
- Kept the existing `poc/` evidence archive unchanged and stopped implicitly admitting new disclosure logs and probes into version control.
- Added a static CodeQL batch-build foundation and a static-only batch aggregator with configuration validation and regression tests.
- Kept dynamic-validation preparation and status synchronization as explicit opt-in helpers, isolated from the ordinary v2 static pipeline.

### Verification

- Python and shell syntax checks.
- Unit tests for manifest/config validation, path handling, dry-run behavior, static aggregation, case identity, overwrite protection, and status synchronization.
- Markdown-link, JSON, gzip, and Git workspace hygiene checks.

## [2026-07-02] Reset the workspace for v2 implementation

### Changed

- Established the v2 static model:
  `Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)`.
- Preserved framework sources, CodeQL databases, PoC evidence, static-hunt results, application results, and Java Web batch results.
- Removed legacy phase-oriented analyzer implementation from the active development context.
