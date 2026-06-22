# dos-analysis-web 项目工作指南

**重要**：后续所有自动化助手在本仓库中工作时，必须**全程使用简体中文**与用户交流；代码、命令、报告字段名可保留英文。

---

## 项目定位

`dos-analysis-web` 是 Java Web 服务框架的 **client-state retention DoS** 检测工具，独立于 AOSP 侧 `dos-analysis/` 开发和运行。项目目标是在 Servlet、Spring、JAX-RS、Jetty、Undertow 等 Web 框架中发现由客户端可控状态长期保留导致的资源耗尽型 DoS，并为跨领域论文评估提供可复现数据。

### 与 AOSP 工具的关系

- **独立实现**：本仓库内的 CodeQL 查询、脚本、结果和报告均按 Web 场景维护，不直接修改 `../dos-analysis/`。
- **方法论复用**：复用五轴判定演算 `R/V/M/C/L` 和 verdict 语义。
- **权威 verdict 实现**：需要与 AOSP 侧 `../dos-analysis/eval/verdict.py` 保持一致；Web 侧可调用或镜像验证，但不得私自改变语义。
- **跨领域目标**：Web 结果用于证明 client-state retention DoS 是跨 AOSP 与 Java Web 的通用漏洞模式。

---

## 核心方法论

### Client-State Retention DoS 定义

```text
ClientStateRetentionDoS := (Entry, State, Container, R, V, M, C, L)
```

### Web 领域映射

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
- **`intel/`**：source 标注、回归材料和人工情报
- **`scripts/`**：构建、分析、验证和报告脚本
- **`dynamic-verification/`**：真实 HTTP 动态验证 Maven harness 源码；`target/` 为本地构建产物
- **`results/`**：当前保留最新 Phase 3/4 汇总结果、报告、复核队列、WEB-REAL 回归结果和动态验证证据；旧 Phase 1/2 与单查询中间产物可按需重新生成
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

### 后续扩展对象

- 其他 JAX-RS 实现作为 REST source 识别和 retained state 验证对象

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

# Phase 1：legacy 手工 source 快速验证
./dos-web-analyzer phase1

# Phase 2：HTTP source 自动发现
# 当前脚本覆盖 tomcat / spring-boot / jetty / undertow；准确率采样入口为 validate_phase2.py
./dos-web-analyzer phase2
python3 scripts/validate_phase2.py

# Phase 3：统一五轴建模
./dos-web-analyzer phase3
python3 scripts/check_phase3_consistency.py

# Phase 4：候选排序、复核队列和报告；推荐用 --refresh-phase3 刷新全量结果
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

---

## 已动态验证真阳

权威落库位置：

- 机器可读库：`results/phase4/verified_vulnerabilities.json`
- 人工摘要：`results/phase4/verified_vulnerabilities.md`
- 真实 HTTP harness 源码：`dynamic-verification/`
- PoC 归档副本：`results/phase4/dynamic_verification/poc/`
- 原始日志：`results/phase4/dynamic_verification/logs/`
- 最新统一摘要：`results/phase4/dynamic_verification/dynamic_verification_summary.json`

说明：`WEB-P4-*` 是 Phase 4 排序派生 ID，候选集或权重变化后可能移动；稳定锚点应以 `WEB-REAL-*`、sink/proof 和 `intel/regression/web_real_manifest.json` 为准。每个 `WEB-REAL-*` 必须带 `exploitability` 利用难度与条件说明；有真实 HTTP OOM 证据不等于默认应用可利用。下列 Phase4 ID 对应 2026-06-20 最新全量分析结果，`WEB-REAL-0007..0012` 来自 static-hunt 后续动态验证。

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
4. **不要删除最新权威结果或动态验证证据**；清理旧结果仅限用户明确要求或确认的旧中间文件，且必须确认不会影响复现实验。
5. **避免无界全量搜索**：不要在大型数据库、框架源码或结果目录上做不加限制的全仓 `rg`。
6. **CodeQL buildless 保守建模**：类型层级可能不完整，优先结合 source-defined 类型、名称字符串、方法名、注解名和局部数据流证据。
7. **优先高召回**：静态查询可保守多报，top 候选必须人工源码复核。
8. **动态验证选择性执行**：仅对 high-risk 候选或论文关键样例做动态验证。
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

核心贡献：

1. **形式化框架**：五轴判定演算和领域映射方法论。
2. **自动化 Source 识别**：跨 Servlet、Spring、JAX-RS、Jetty、Undertow 的分层 source discovery。
3. **大规模跨领域实证**：AOSP + 多个 Java Web 框架。
4. **开源工具链**：完整查询、pipeline、benchmark、PoC 和复现实验材料。

研究问题：

- **RQ1**：client-state retention DoS 是否能跨领域泛化？
- **RQ2**：Web source 自动识别是否足够准确？
- **RQ3**：五轴模型相比三轴模型是否有更强判别力？
- **RQ4**：能否发现真实、可复现、可报告的 Web 框架漏洞？

---

**文档版本**：2026-06-20
**维护者**：项目团队
