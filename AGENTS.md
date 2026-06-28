# dos-analysis-web 项目工作指南

**重要**：后续所有自动化助手在本仓库中工作时，必须**全程使用简体中文**与用户交流；代码、命令、报告字段名可保留英文。

---

## 项目定位

`dos-analysis-web` 是 Java Web DoS 分析与验证工具，独立于 AOSP 侧 `dos-analysis/` 开发和运行。本仓库已经完成 Java Web 框架/基座层 **client-state retention DoS** 的一轮探索，当前将这些成果冻结为 `WEB-REAL-*` 回归集、证据库和方法论对照。

下一阶段主线转向 **具体 Java Web 应用默认部署下的直接 DoS 挖掘**：优先分析官方 Docker image、release package、quickstart compose 或默认配置即可启动的真实 Java 应用，寻找匿名或低权限 HTTP 入口在默认配置下直接造成 OOM、GC death、线程/连接池耗尽、磁盘耗尽、watchdog/restart 或持续服务不可用的问题。

### 与 AOSP 工具的关系

- **独立实现**：本仓库内的 CodeQL 查询、脚本、结果和报告均按 Web 场景维护，不直接修改 `../dos-analysis/`。
- **方法论复用**：复用五轴判定演算 `R/V/M/C/L` 和 verdict 语义。
- **权威 verdict 实现**：需要与 AOSP 侧 `../dos-analysis/eval/verdict.py` 保持一致；Web 侧可调用或镜像验证，但不得私自改变语义。
- **跨领域目标**：保留 AOSP + Java Web 基座结果作为通用漏洞模式证据；下一阶段重点证明默认部署真实应用中的可利用 DoS。

---

## 核心方法论

### 基座阶段：Client-State Retention DoS 定义

```text
ClientStateRetentionDoS := (Entry, State, Container, R, V, M, C, L)
```

### Web 基座领域映射

| 通用概念 | Java Web 实例 |
| --- | --- |
| Entry | Servlet `doGet/doPost`、Spring Controller、JAX-RS resource、handler 方法 |
| State | session key、request parameter、header、path variable、multipart part、stream |
| Container | `HttpSession`、`ServletContext`、static map、cache、connection/client destination map、framework registry |
| R - Open | 无认证或弱认证 HTTP endpoint |
| V - Stream | `InputStream`、multipart upload、request body stream |
| M - Amplifiable | 攻击者可控 attribute name、token、referer、origin、path、host、tag |
| C - Unbounded | 无 session size、map size、part count、destination count 或 per-client quota |
| L - RebootPersistent | Redis/DB/file-backed session、持久化 registry；否则通常为 process lifetime |

### 五轴判定演算

- **R 可达性**：`Blocked ⊏ PermGated ⊏ WeakGated ⊏ Open`
- **V 值空间**：`Uncontrollable ⊏ Limited ⊏ Unlimited ⊏ Stream`
- **M 放大性**：`CallerBounded ⊏ Amplifiable`
- **C 容量**：`Bounded ⊏ PerElementUnbounded ⊏ Unbounded`
- **L 生命周期**：`Evicted ⊏ ProcessLifetime ⊏ RebootPersistent`
- **Verdict**：`Unexploitable ⊏ Context-Constrained ⊏ Time-Constrained ⊏ Unconstrained ⊏ Irrecoverable`

### 下一阶段：Default-Deploy Application DoS

```text
DefaultDeployAppDoS := (Application, DefaultDeployment, Entry, State/Resource, Trigger, Bound, Impact)
```

核心判定：

- **Application**：具体真实 Java Web 应用，而非仅框架/容器源码。
- **DefaultDeployment**：官方镜像、release 包、quickstart compose 或默认配置；配置修改必须单独标注，不能混作默认可利用。
- **Entry**：匿名或低权限 HTTP 入口、默认管理面、安装后自然暴露流程、上传/导入/搜索/同步/webhook/callback/SSO/OAuth 等常见功能。
- **State/Resource**：retained map/cache/session、metrics tag、multipart/temp file、JSON/XML/parser、async/job queue、index、outbound client pool/cache、thread/connection pool。
- **Trigger**：低带宽、少量或中等请求即可驱动资源增长或阻塞。
- **Bound**：默认容量、TTL、quota、body limit、rate limit、auth、per-user/per-IP 限制。
- **Impact**：真实 HTTP 触发 OOM、GC death、watchdog/restart、线程/连接池耗尽、磁盘耗尽或持续服务不可用；单纯增长曲线只能标为中间证据。

---

## 目录说明

- **`codeql/lib/`**：Web 特定 CodeQL 库
  - `WebSources.qll`：HTTP entry 自动识别
  - `SessionState.qll`：session / attribute / retained state 建模
  - `Persistence.qll`：Web 长生命状态模型
  - `WebGuards.qll`：Web 访问控制和 guard 建模
  - `CommonDoS.qll`：跨领域通用抽象层
- **`codeql/queries/`**：Phase 1-4 查询与测试查询
- **`frameworks/`**：目标框架源码
- **`databases/`**：各框架 CodeQL 数据库
- **`frameworks/applications/`**：应用级真实 Java Web 目标源码，本地下载产物
- **`databases/applications/`**：应用级 build-mode CodeQL 数据库，本地生成产物
- **`intel/`**：source 标注、回归材料和人工情报
- **`intel/applications/`**：应用级目标 manifest，例如 `java_web_application_targets.json`
- **`scripts/`**：构建、分析、验证和报告脚本
- **`dynamic-verification/`**：真实 HTTP 动态验证 Maven harness 源码；`target/` 为本地构建产物
- **`results/`**：当前保留最新 Phase 3/4 汇总结果、报告、复核队列、WEB-REAL 回归结果和动态验证证据；旧 Phase 1/2 与单查询中间产物可按需重新生成
- **`results/application_dbs/`**：应用级 DB 批量构建状态、摘要和日志，本地生成产物
- **`tests/`**：一致性和单元测试
- **`config.yaml`**：pipeline 配置
- **`dos-web-analyzer`**：统一 CLI 入口

---

## 目标框架

### 当前权威全量对象

- Tomcat 9.x（`databases/tomcat-9.0-db`）
- Spring Boot 2.7.x（`databases/spring-boot-2.7-db`）
- Spring Boot 3.x（`databases/spring-boot-3-db`，当前 tag `v3.5.15`）
- Jetty 11.x（`databases/jetty-11-db`）
- Undertow 2.x（`databases/undertow-2-db`）
- Jersey 3.1.x（`databases/jersey-3.1-db`）
- Vert.x 4.x（`databases/vertx-4-db`，当前 tag `4.5.28`；build extraction 覆盖 `vert.x` core 与 `vertx-web` 聚焦源码视图）
- Micronaut 3.x（`databases/micronaut-3-db`，当前 tag `v3.10.8`）

### 基座阶段状态

上述框架/基座对象进入维护模式：默认只做回归、证据刷新、披露材料整理和必要 bug 修复。除非用户明确要求，不再继续扩展更多框架基座作为主线。

### 下一阶段目标应用

优先选择默认部署可复现、用户量大、HTTP 功能面丰富的真实 Java 应用，例如 CI/CD、制品库、代码质量、身份认证、低代码/管理平台、地理信息、数据流、后台管理系统等。新增目标必须记录官方启动方式、默认账号/权限、默认资源限制、入口路径和复现命令。

---

## 运行指南

```bash
cd /home/furina/new_tool/dos-analysis-web

# 构建或刷新数据库（按需执行）
./scripts/build_databases.sh tomcat spring-boot spring-boot-3 vertx micronaut
./scripts/build_jetty_db.sh
./scripts/build_undertow_db.sh
./scripts/build_jersey_db.sh --force

# 新增扩展框架使用真实编译抽取；Gradle/Maven 依赖缓存落在本地 ignored 的 .build-cache/

# 应用级真实 Java Web 目标采集与 build-mode DB 构建
python3 scripts/collect_application_targets.py --limit 50 --per-query 40
python3 scripts/build_application_databases.py \
  --threads 4 --ram 8192 --timeout 1800 \
  --use-default-github-accelerators \
  --java-home-candidate /usr/lib/jvm/java-22-openjdk \
  --java-home-candidate /usr/lib/jvm/java-21-openjdk \
  --java-home-candidate /usr/lib/jvm/java-17-openjdk
python3 scripts/build_application_databases.py --skip-clone --target diyhi__bbs
python3 scripts/build_application_databases.py --skip-clone --java-home /usr/lib/jvm/java-22-openjdk --target diyhi__bbs
python3 scripts/summarize_application_static_findings.py
python3 scripts/run_application_p0_dynamic_validation.py
python3 scripts/run_application_p0_dynamic_validation.py --case SMQTT-APP-STATIC-0002
python3 scripts/run_application_p1_dynamic_validation.py
python3 scripts/run_application_p1_dynamic_validation.py --case SMQTT-APP-STATIC-0003
python3 scripts/run_application_p2_dynamic_validation.py
python3 scripts/run_application_p2_dynamic_validation.py --case SBA-APP-STATIC-0002

# 基座 Phase 3：统一五轴建模
./dos-web-analyzer phase3
python3 scripts/check_phase3_consistency.py

# 基座 Phase 4：候选排序、复核队列和报告；推荐用 --refresh-phase3 刷新全量结果
./dos-web-analyzer analyze --refresh-phase3
./dos-web-analyzer report
./dos-web-analyzer verify --top 50

# WEB-REAL 已验证真阳回归门禁
python3 scripts/check_web_real_regression.py

# 真实 HTTP 动态验证（Maven 可自动下载依赖）
python3 scripts/run_dynamic_verification.py --profile smoke --heap 384m
python3 scripts/run_dynamic_verification.py --profile oom --heap 384m
```

### Phase 3 当前权威产物

- `results/phase3/phase3_candidate_features.csv`
- `results/phase3/phase3_consistency.json`
- `results/phase3/web_real_regression.json`
- `results/phase3_report.md`

### Phase 4 当前权威产物

- `results/phase4/ranked_candidates.csv`
- `results/phase4/ranked_candidates.json`
- `results/phase4/review_queue_top50.md`
- `results/phase4/review_queue_top50.json`
- `results/phase4/evaluation_summary.json`
- `results/phase4_report.md`
- `results/phase4/verified_vulnerabilities.json`
- `results/phase4/verified_vulnerabilities.md`
- `results/phase4/dynamic_verification/`

### 应用级当前权威产物

- 目标 manifest：`intel/applications/java_web_application_targets.json`
- 本地源码根：`frameworks/applications/`
- 本地数据库根：`databases/applications/`
- 构建状态：`results/application_dbs/application_db_build_status.jsonl`
- 构建摘要：`results/application_dbs/application_db_build_summary.md`
- 构建日志：`results/application_dbs/logs/`
- 应用级静态结果根：`results/applications_static_analysis/<target_id>/`
- 应用级静态汇总与默认 OOM 复核：`results/applications_static_analysis/_static_validation/`
- 应用级 P0 动态验证结果：`results/applications_dynamic_validation/p0/`
- 应用级 P1 动态验证结果：`results/applications_dynamic_validation/p1/`
- 应用级 P2 动态验证结果：`results/applications_dynamic_validation/p2/`

当前应用级 manifest 固定 50 个已经成功创建 build-mode CodeQL 数据库的 Java HTTP/Web 应用目标。构建脚本会优先使用中国境内 Maven/Gradle 源，重写 Gradle wrapper distribution 到腾讯云 Gradle 镜像，GitHub clone 失败时尝试默认加速前缀和 codeload archive fallback，并按 Java 22、21、17 顺序重试。`results/application_dbs/` 可保留超过 50 个成功或失败尝试记录；最终目标真相以 `intel/applications/java_web_application_targets.json` 为准。

应用级静态结果通常包含 `STATIC_DOS_HUNT_REPORT.md`、`source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv` 和按需生成的 `dynamic_probe_plan.md`。`scripts/summarize_application_static_findings.py` 会聚合已有 `findings.jsonl` / `findings.csv`，生成全量候选、应用汇总、默认外部 OOM 动态验证优先队列和 216 条候选 Markdown 准备清单；该脚本只做静态汇总，不会把候选提升为 confirmed。

应用级 P0 动态验证使用 `scripts/run_application_p0_dynamic_validation.py`，以 `results/applications_static_analysis/_static_validation/all_candidates_dynamic_validation.md` 的 P0 队列为输入，输出 `summary.json`、`summary.csv`、`findings.jsonl`、`P0_DYNAMIC_VALIDATION_REPORT.md` 和原始日志到 `results/applications_dynamic_validation/p0/`。当前 P0 冻结口径为：15 个候选中 5 个真实触发 OOM 真阳性，10 个因默认应用环境、登录态或特殊 agent/compose 前置条件未满足而保持环境阻塞；真实 OOM 证据必须来自外部协议/HTTP 请求触发目标 JVM 的 `OutOfMemoryError`。

应用级 P1 动态验证使用 `scripts/run_application_p1_dynamic_validation.py`，以 `results/applications_static_analysis/_static_validation/all_candidates_dynamic_validation.md` 的 P1 队列为输入，输出 `summary.json`、`summary.csv`、`findings.jsonl`、`P1_DYNAMIC_VALIDATION_REPORT.md` 和原始日志到 `results/applications_dynamic_validation/p1/`。当前 P1 冻结口径为：89 个候选中 17 个真实触发 OOM 真阳性，18 个已执行但未确认 OOM，0 个保持 `probe_error`，54 个因默认服务环境、业务数据、登录态、agent/compose 或协议 harness 前置条件未满足而保持 `precondition_blocked`；其中第一优先级补测 38 个候选，10 个真实 OOM、17 个已执行未确认 OOM、0 个探针错误、11 个前置条件阻塞；真实 OOM 证据必须来自外部协议/HTTP 请求触发目标 JVM 的 `OutOfMemoryError`。

应用级 P2 动态验证使用 `scripts/run_application_p2_dynamic_validation.py`，以 `results/applications_static_analysis/_static_validation/p2_dynamic_validation_triage.md` 为输入，输出 `summary.json`、`summary.csv`、`findings.jsonl`、`P2_DYNAMIC_VALIDATION_REPORT.md` 和原始日志到 `results/applications_dynamic_validation/p2/`。当前 P2 冻结口径为：34 个候选中 1 个真实触发 OOM 真阳性（`SBA-APP-STATIC-0002`），7 个 triage 推荐候选因默认服务环境、业务数据、登录态或依赖栈未补齐保持 `precondition_blocked`，26 个按 P2 triage 保持 `triage_not_selected`；真实 OOM 或服务不可用证据必须来自外部协议/HTTP 请求触发目标 JVM 的 `OutOfMemoryError`、GC death、线程/连接池耗尽或持续服务不可用。

---

## 已动态验证真阳

权威落库位置：

- 机器可读库：`results/phase4/verified_vulnerabilities.json`
- 人工摘要：`results/phase4/verified_vulnerabilities.md`
- 真实 HTTP harness 源码：`dynamic-verification/`
- PoC 归档副本：`results/phase4/dynamic_verification/poc/`
- 原始日志：`results/phase4/dynamic_verification/logs/`
- 最新统一摘要：`results/phase4/dynamic_verification/dynamic_verification_summary.json`

说明：`WEB-P4-*` 是 Phase 4 排序派生 ID，候选集或权重变化后可能移动；稳定锚点应以 `WEB-REAL-*`、sink/proof 和 `intel/regression/web_real_manifest.json` 为准。每个 `WEB-REAL-*` 必须带 `exploitability` 利用难度与条件说明；有真实 HTTP OOM 证据不等于默认应用可利用。

当前冻结口径：

- `intel/regression/web_real_manifest.json` 是 12 个 `WEB-REAL-*` 的权威索引和利用条件来源。
- `results/phase4/verified_vulnerabilities.json` / `.md` 是当前已整理的机器可读/人工摘要；若 manifest 与摘要数量不一致，以 manifest 为 ID 真相，以动态验证日志和 runner case 做证据刷新。
- `WEB-REAL-0007..0009` 标记为 `dynamic_only_pending_query`，保留为 context-constrained confirmed cases；如需完整 Phase 4 摘要和日志，应复跑对应动态 case 并同步 `verified_vulnerabilities.*`。
- `WEB-REAL-0010..0012` 来自新框架 static-hunt 动态验证，属于应用形态路径下可 OOM 的 context-constrained cases，不按默认开放漏洞表述。

### WEB-REAL-0001 - Jersey OAuth1 request token map

- **Phase4 ID**：`WEB-P4-0011`
- **Component**：`security/oauth1-server`
- **State**：request token map
- **Dynamic verdict**：真实 HTTP 384MiB 堆 OOM 已确认；保留旧默认堆 direct harness 日志
- **利用难度**：Medium；依赖应用启用 Jersey OAuth1 provider 并暴露 request-token issuing endpoint，普通非 OAuth1 应用不在影响面。

### WEB-REAL-0002 - Jersey multipart MIME parser

- **Phase4 IDs**：`WEB-P4-0001`、`WEB-P4-0002`、`WEB-P4-0003`
- **Component**：`media/multipart`
- **State**：multipart / mimepull part bookkeeping
- **Dynamic verdict**：真实 HTTP multipart 384MiB 堆 OOM 已确认；保留旧大磁盘 tempDir 默认堆日志
- **利用难度**：Medium；依赖应用存在 Jersey multipart upload endpoint，且代理/应用未限制 body size、part count 或上传配额。

### WEB-REAL-0003 - Undertow LearningPushHandler per-referer map

- **Phase4 ID**：`WEB-P4-0006`
- **Entry**：`LearningPushHandler.handleRequest`
- **State**：per-referer inner map
- **Dynamic verdict**：真实 HTTP 384MiB 堆 OOM 已确认；保留旧默认堆日志
- **利用难度**：High；依赖应用显式安装 Undertow `LearningPushHandler`，默认普通 Undertow handler 链不自动暴露该状态。

### WEB-REAL-0004 - Undertow mod_cluster MCMP registration state

- **Phase4 ID**：`WEB-P4-0010`
- **Entry**：`MCMPHandler.handleRequest`
- **State**：nodes / balancers / virtual hosts
- **Dynamic verdict**：真实 HTTP `CONFIG` 384MiB 堆 OOM 已确认；保留旧 direct harness 默认堆日志
- **利用难度**：Very High；MCMP 是管理面入口，正常部署应网络隔离或鉴权。
- **限制**：暴露面依赖 MCMP management endpoint 部署和配置

### WEB-REAL-0005 - Jetty ProxyServlet HttpClient destinations

- **Phase4 ID**：`WEB-P4-0004`
- **Component**：`jetty-proxy` / `jetty-client`
- **Entry**：`ProxyServlet.service`
- **State**：`HttpClient.destinations`
- **Dynamic verdict**：真实 HTTP 384MiB 堆 OOM 已确认；保留旧默认堆日志
- **利用难度**：High；依赖 ProxyServlet 或等价代理把攻击者可控数据映射到 upstream origin/tag，且 destination idle eviction/allowlist 不足以限制 key 空间。
- **限制**：harness 将攻击者 HTTP 参数映射到 Jetty `Request.tag()`，用于验证 retained `Origin.tag` / destination map 路径

### WEB-REAL-0006 - Tomcat WebdavServlet lock maps

- **Phase4 IDs**：`WEB-P4-0025`、`WEB-P4-0026`、`WEB-P4-0027`
- **Entry**：`WebdavServlet.service`
- **State**：`sharedLocks` / `resourceLocks`
- **Dynamic verdict**：真实 HTTP WebDAV `LOCK` 384MiB 堆 OOM 已确认
- **利用难度**：Very High；依赖 Tomcat `WebdavServlet` 写方法对低信任客户端可达，普通应用通常不应暴露可写 WebDAV。
- **说明**：`WEB-REAL-0006` 是稳定锚点，覆盖 `sharedLocks.put(lock.token, lock)` 与 `resourceLocks.put(path, lock/sharedLock)`；lock 暴露面依赖 WebDAV servlet 可写部署。

### WEB-REAL-0007 - Tomcat WebdavServlet dead properties

- **Source ID**：`TOMCAT-STATIC-0003`
- **Entry**：`WebdavServlet.service` -> `doProppatch`
- **State**：`MemoryPropertyStore.deadProperties`
- **Dynamic verdict**：真实 HTTP WebDAV `PROPPATCH` 384MiB 堆 OOM 已确认
- **利用难度**：Very High；必须部署 `WebdavServlet` 且配置 `readonly=false`，默认 read-only WebDAV 对该路径不可利用；攻击者还需要能创建或命中目标资源，并使用默认或无界 `propertyStore`。
- **说明**：这是 context-constrained confirmed case，不应按正常应用默认开启漏洞表述。

### WEB-REAL-0008 - Jetty PushSessionCacheFilter path cache

- **Source ID**：`JETTY-STATIC-0002`
- **Entry**：`PushSessionCacheFilter.doFilter` / servlet request listener
- **State**：filter `_cache` 与 per-target associated map
- **Dynamic verdict**：真实 HTTP + push-capable request wrapper 384MiB 堆 OOM 已确认
- **利用难度**：High；依赖应用显式安装 `PushSessionCacheFilter`、存在 `PushBuilder` 可用的 HTTP/2 servlet 环境，并允许同一 session 发送大量唯一 path 与同 host `Referer`。
- **说明**：HTTP/1.x 或无 `PushBuilder` 环境不触发同等路径。

### WEB-REAL-0009 - Jetty PushCacheFilter primary-resource cache

- **Source ID**：`JETTY-STATIC-0004`
- **Entry**：`PushCacheFilter.doFilter`
- **State**：filter `_cache` primary resource map 与 associated set
- **Dynamic verdict**：真实 HTTP + push-capable request wrapper 384MiB 堆 OOM 已确认
- **利用难度**：High；依赖应用显式安装 `PushCacheFilter` 且请求为 HTTP/2 / non-null `PushBuilder`，攻击者可制造大量唯一 primary path 与同 host `Referer`；`_maxAssociations` 只限制每个 primary 的子资源数，不限制 primary key 总数。
- **说明**：属于 context-constrained confirmed case，static Phase 3 查询覆盖仍待补齐。

### WEB-REAL-0010 - Spring Boot 3 HTTP client observation client.name cardinality

- **Source ID**：`SB3-STATIC-0002`
- **Entry**：应用 HTTP endpoint -> `RestTemplate` / `RestClient` / `WebClient` outbound request
- **State**：Micrometer `MeterRegistry` 中 `http.client.requests` meters 的 `client.name` tag cardinality
- **Dynamic verdict**：真实 HTTP entry -> outbound client observation 384MiB 堆 OOM 已确认
- **利用难度**：Medium；依赖应用把低信任 HTTP 输入映射到 outbound URL host，例如 fetch/proxy/callback/tenant upstream，并且未对 `client.name` tag、host allowlist、egress 或 per-user quota 做限制。
- **说明**：Spring Boot 自身不默认暴露 attacker-controlled outbound URL endpoint；固定 upstream 应用不在影响面。

### WEB-REAL-0011 - Micronaut InMemorySessionStore active-session count

- **Source ID**：`MN-STATIC-0002`
- **Entry**：会创建或保存 session 的 Micronaut HTTP route
- **State**：`InMemorySessionStore.sessions`
- **Dynamic verdict**：真实 HTTP session creation 384MiB 堆 OOM 已确认
- **利用难度**：Medium；依赖应用启用 in-memory session store，开放低信任 session 创建/保存路径，且未配置 `micronaut.session.max-active-sessions` 或等价 per-client/session quota；大 session attribute 会显著降低 OOM 门槛。
- **说明**：没有匿名 session 创建面或没有大 attribute 写入路径的普通应用不直接可利用。

### WEB-REAL-0012 - Vert.x CachingWebClient cache store

- **Source ID**：`VERTX-STATIC-0003`
- **Entry**：应用 HTTP endpoint -> `CachingWebClient` outbound request
- **State**：`CachingWebClient` cache store entries
- **Dynamic verdict**：真实 HTTP entry -> cacheable upstream response 384MiB 堆 OOM 已确认
- **利用难度**：High；依赖应用显式使用 `CachingWebClient`，低信任输入能影响 outbound host/path/query/cache key，upstream 返回可缓存响应，且无 cache store 容量、字节配额、TTL/eviction 或 per-user quota。
- **说明**：Vert.x 默认 server 不自动暴露该路径；开放 fetch/proxy/tenant-selected upstream 或 cache-busting query 可控的应用风险更高。

---

## 开发约束

1. **全程使用简体中文**与用户交流。
2. **不要修改 AOSP 工具**，除非用户明确要求跨仓库同步；Web 工作默认限制在 `dos-analysis-web/`。
3. **保持可复现性**：脚本、配置、最新汇总结果、日志、PoC 和报告都应版本化或明确归档；可再生成的旧中间产物可清理，但必须记录。
4. **不要删除最新权威结果或动态验证证据**；清理旧结果仅限过时 Phase 1/2 过程产物、obsolete docs/superpowers 或用户明确确认的旧中间文件，且必须确认不会影响复现实验。
5. **避免无界全量搜索**：不要在大型数据库、框架源码或结果目录上做不加限制的全仓 `rg`。
6. **CodeQL buildless 保守建模**：类型层级可能不完整，优先结合 source-defined 类型、名称字符串、方法名、注解名和局部数据流证据。
7. **优先高召回**：静态查询可保守多报，top 候选必须人工源码复核。
8. **动态验证选择性执行**：仅对 high-risk 候选或论文关键样例做动态验证。下一阶段应用真阳性必须以默认部署真实 HTTP 服务不可用为门槛；growth-only 不得提升为 confirmed DoS。
9. **同步更新文档**：工具、目录、脚本、数据库、PoC、流程或结果有重要变化时，更新 `README.md`、相关报告和本 `AGENTS.md`。
10. **每次项目修改后必须更新 `CHANGELOG.md`**。

---

## 验证要求

改动 CodeQL 规则、ranking、verdict、pipeline 或结果生成逻辑后，应按影响范围运行：

```bash
cd /home/furina/new_tool/dos-analysis-web

# Web Phase 3/4 一致性与 pipeline
python3 scripts/check_phase3_consistency.py
./dos-web-analyzer analyze

# 五轴演算单调性，依赖 AOSP 侧权威 eval 包
PYTHONPATH=/home/furina/new_tool/dos-analysis \
  python3 -m eval.monotonicity

# AOSP golden regression，确认未破坏共享 verdict 语义
PYTHONPATH=/home/furina/new_tool/dos-analysis \
  python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py
```

仅清理旧结果或同步文档、且未改 CodeQL/ranking/verdict/pipeline 逻辑时，至少运行：

```bash
python3 scripts/check_phase3_consistency.py
python3 scripts/check_web_real_regression.py
```

如果未运行某项验证，最终回复必须明确说明原因。

---

## 变更日志要求

每次修改本项目后，必须在 `CHANGELOG.md` 添加记录，并按时间倒序排列。一次完整工作对应一条记录，小修改可合并到最近记录中。

模板：

```markdown
## [YYYY-MM-DD] <变更主题>

### 修改时间
YYYY-MM-DD HH:MM

### 变更类型
- [新增功能] / [功能删除] / [功能改进] / [Bug 修复] / [重构] / [文档]

### 核心改动
- 简要描述核心思想、算法或重点改动
- 关键技术决策和理由
- 影响范围

### 交付成果
- 新增/修改的代码文件路径
- 设计文档位置
- 数据/结果文件位置
- 测试/验证结果

### 依赖与影响
- 依赖的前置工作
- 对后续工作的影响
- 破坏性变更（如有）
```

---

## 论文目标

目标投稿软件工程顶会：ICSE、FSE、ASE、ISSTA。

下一阶段论文贡献重心：

1. **默认部署应用 DoS 基准**：构建真实 Java Web 应用、官方启动方式、默认配置和默认权限下的可复现实验集。
2. **应用级资源耗尽模式**：覆盖 retained state、session/cache cardinality、metrics tag cardinality、multipart/temp file、parser expansion、async/job queue、index/import/export 和 outbound client cache/pool。
3. **默认可利用性判定**：区分默认可达、低权限可达、配置依赖、管理面依赖和仅框架可触发，避免把高条件基座样例过度包装。
4. **端到端动态证据**：每个 true positive 都提供默认部署真实 HTTP 触发的服务不可用证据、资源曲线、PoC 和复现命令。

研究问题：

- **RQ1**：真实 Java Web 应用默认部署中是否普遍存在可由低信任 HTTP 入口触发的资源耗尽 DoS？
- **RQ2**：这些问题主要来自应用逻辑、框架默认集成、组件组合，还是基座容器缺陷？
- **RQ3**：默认配置下的容量、TTL、quota、auth、rate limit 对可利用性有多大影响？
- **RQ4**：静态候选、默认部署配置抽取和动态验证结合后，能否形成可扩展、低误报的应用级 DoS 挖掘流程？

---

**文档版本**：2026-06-22
**维护者**：项目团队
