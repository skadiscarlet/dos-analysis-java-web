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
- **`results/`**：分析结果、报告、复核队列、动态验证证据
- **`tests/`**：一致性和单元测试
- **`config.yaml`**：pipeline 配置
- **`dos-web-analyzer`**：统一 CLI 入口

---

## 目标框架

### 第一梯队

- Tomcat 9.x
- Spring Boot 2.7 / 3.x
- Jetty 11.x
- Undertow 2.x

### 第二梯队

- Vert.x 4.x
- Micronaut 3.x
- Jersey / JAX-RS 作为 REST source 识别和 retained state 验证对象

---

## 运行指南

```bash
cd /home/furina/new_tool/dos-analysis-web

# 构建 Tomcat 和 Spring Boot 数据库
./scripts/build_databases.sh tomcat spring-boot

# Phase 1：手工 source 快速验证
./dos-web-analyzer phase1 --framework tomcat
./dos-web-analyzer phase1 --framework spring-boot

# Phase 2：HTTP source 自动发现
./dos-web-analyzer phase2
python3 scripts/test_source_discovery.py

# Phase 3：统一五轴建模
./dos-web-analyzer phase3
python3 scripts/check_phase3_consistency.py

# Phase 4：候选排序、复核队列和报告
./dos-web-analyzer analyze
./dos-web-analyzer report
./dos-web-analyzer verify --top 50
```

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
- PoC 源码：`results/phase4/dynamic_verification/poc/`
- 原始日志：`results/phase4/dynamic_verification/logs/`

### WEB-REAL-0001 - Jersey OAuth1 request token map

- **Component**：`security/oauth1-server`
- **State**：request token map
- **Dynamic verdict**：默认堆 OOM 已确认

### WEB-REAL-0002 - Jersey multipart MIME parser

- **Component**：`media/multipart`
- **State**：multipart / mimepull part bookkeeping
- **Dynamic verdict**：大磁盘 tempDir 下默认堆 OOM 已确认

### WEB-REAL-0003 - Undertow LearningPushHandler per-referer map

- **Phase4 IDs**：`WEB-P4-0006`、`WEB-P4-0007`
- **Entry**：`LearningPushHandler.handleRequest`
- **State**：per-referer inner map
- **Dynamic verdict**：真实 HTTP 默认堆 OOM 已确认

### WEB-REAL-0004 - Undertow mod_cluster MCMP registration state

- **Phase4 ID**：`WEB-P4-0029`
- **Entry**：`MCMPHandler.handleRequest`
- **State**：nodes / balancers / virtual hosts
- **Dynamic verdict**：默认堆 OOM 已确认
- **限制**：暴露面依赖 MCMP management endpoint 部署和配置

### WEB-REAL-0005 - Jetty ProxyServlet HttpClient destinations

- **Component**：`jetty-proxy` / `jetty-client`
- **Entry**：`ProxyServlet.service`
- **State**：`HttpClient.destinations`
- **Dynamic verdict**：真实 HTTP 默认堆 OOM 已确认
- **限制**：harness 将攻击者 HTTP 参数映射到 Jetty `Request.tag()`，用于验证 retained `Origin.tag` / destination map 路径

---

## 开发约束

1. **全程使用简体中文**与用户交流。
2. **不要修改 AOSP 工具**，除非用户明确要求跨仓库同步；Web 工作默认限制在 `dos-analysis-web/`。
3. **保持可复现性**：脚本、配置、结果、日志、PoC 和报告都应版本化或明确归档。
4. **不要删除已有结果**；清理仅限临时文件，且必须确认不会影响复现实验。
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

**文档版本**：2026-06-18
**维护者**：项目团队
