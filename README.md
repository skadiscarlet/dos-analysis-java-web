# dos-analysis-web

Java Web 框架的 client-state retention DoS 检测工具。

## 目标

将 dos-analysis 从 AOSP 扩展到 Java Web 服务框架，验证 client-state retention DoS 是跨领域的通用漏洞模式。

## 与 dos-analysis 的关系

本项目是 dos-analysis（AOSP DoS 检测工具）的扩展：

- **代码复用**：从 `../dos-analysis/` 复用以下组件：
  - `codeql/lib/Persistence.qll` - 长生命存储模型（需适配 Web 场景）
  - `eval/verdict.py` - 五轴判定演算（直接复用）
  - `rank_candidates.py` - 候选排序逻辑（直接复用）

- **方法论复用**：使用相同的五轴模型（R/V/M/C/L）和 verdict 判定

- **独立性**：dos-analysis-web 是独立项目，不修改 dos-analysis 代码

## Phase 1 目标

在 Tomcat 和 Spring Boot 上快速验证方法可行性：
- 手工标注 10-20 个 HTTP entry source
- 复用 AOSP 的 persistence/guard 模型
- 运行 CodeQL 查询
- 验证能否发现候选

## 目录结构

- `codeql/` - CodeQL 查询和库
- `frameworks/` - 框架源码
- `databases/` - CodeQL 数据库
- `intel/` - 情报和标注数据
- `scripts/` - 自动化脚本
- `results/` - 分析结果

## 运行

```bash
# 构建数据库
./scripts/build_databases.sh tomcat spring-boot spring-boot-3 vertx micronaut
./scripts/build_jersey_db.sh --force

# 运行 Phase 1 分析
./scripts/run_phase1.sh

# 运行 Phase 3 统一候选提取
./dos-web-analyzer phase3

# Phase 3 之后生成 Phase 4 排序、复核队列和报告
./dos-web-analyzer analyze

# 只刷新报告
./dos-web-analyzer report

# 生成 top-50 人工复核队列
./dos-web-analyzer verify --top 50
```

Jersey 使用聚焦 buildless 数据库视图 `frameworks/jersey-3.1.3-analysis-sources`，默认复制 `core-*`、`media/multipart` 和 `security/oauth1-*` 的源码，以稳定覆盖 provider/parser/OAuth 路径。

Spring Boot 3.x、Vert.x 4.x 和 Micronaut 3.x 使用固定 tag 的 CodeQL build extraction 数据库：Spring Boot `v3.5.15` -> `databases/spring-boot-3-db`，Vert.x `4.5.28` core + `vertx-web` -> `databases/vertx-4-db`，Micronaut Core `v3.10.8` -> `databases/micronaut-3-db`。构建 helper 位于 `scripts/codeql_build_spring_boot_3.sh`、`scripts/codeql_build_vertx_4.sh` 和 `scripts/codeql_build_micronaut_3.sh`，会把 Gradle/Maven 依赖缓存写入本地 ignored 的 `.build-cache/`，避免污染用户 home。Spring Boot 3 当前 build-mode 目标先覆盖可稳定编译的 core 模块；autoconfigure/actuator 的 optional integration 依赖面较宽，后续需在 Maven/Gradle 缓存或 mirror 稳定后再扩展。

当前 Phase 3 会合并普通 retained-state 查询、Jersey parser/body 查询、Jersey OAuth provider-state 查询、Undertow bridge 查询和 Jetty ProxyServlet bridge 查询，统一输出到 `results/phase3/phase3_candidate_features.csv`。最新基线为 37 条候选，其中 3 条为 Jersey multipart `candidate_family=parser_body`，1 条为 Jersey OAuth1 `candidate_family=provider_state`，1 条为 Undertow LearningPush `candidate_family=listener_state`，2 条为 Undertow MCMP `candidate_family=management_state`，1 条为 Jetty ProxyServlet / HttpClient destination map `candidate_family=client_destination`。

## Phase 4 产物

- `results/phase4/ranked_candidates.csv`：全部候选排序表
- `results/phase4/ranked_candidates.json`：全部候选排序 JSON
- `results/phase4/review_queue_top50.md`：人工复核队列
- `results/phase4/evaluation_summary.json`：论文评估统计摘要
- `results/phase4_report.md`：Phase 4 大规模挖掘报告

## 动态验证

真实 HTTP 动态验证 harness 位于 `dynamic-verification/`，使用 Maven 拉取 Tomcat、Jersey、Undertow 和 Jetty 运行依赖。默认 smoke profile 用小规模请求验证真实 HTTP 入口和 retained state 增长；oom profile 使用受控 JVM 堆确认 OOM。

```bash
# 构建并运行全部真实 HTTP smoke
python3 scripts/run_dynamic_verification.py --profile smoke --heap 384m

# 运行全部真实 HTTP OOM 验证
python3 scripts/run_dynamic_verification.py --profile oom --heap 384m

# 只验证 Tomcat WebDAV WEB-REAL-0006
python3 scripts/run_dynamic_verification.py --profile oom --heap 384m --case WEB-REAL-0006

# static-hunt 提升后的 WEB-REAL ID 也可直接运行；旧 static ID 会映射到稳定 WEB-REAL ID
python3 scripts/run_dynamic_verification.py --profile oom --heap 384m --case WEB-REAL-0007
python3 scripts/run_dynamic_verification.py --profile oom --heap 384m --case TOMCAT-STATIC-0003
python3 scripts/run_dynamic_verification.py --profile oom --heap 384m --case WEB-REAL-0010
python3 scripts/run_dynamic_verification.py --profile oom --heap 384m --case SB3-STATIC-0002
```

兼容说明：旧的 `--case WEB-P4-0025-0027` 仍会映射到 `WEB-REAL-0006`；`TOMCAT-STATIC-0003`、`JETTY-STATIC-0002`、`JETTY-STATIC-0004` 分别映射到 `WEB-REAL-0007`、`WEB-REAL-0008`、`WEB-REAL-0009`；`SB3-STATIC-0002`、`MN-STATIC-0002`、`VERTX-STATIC-0003` 分别映射到 `WEB-REAL-0010`、`WEB-REAL-0011`、`WEB-REAL-0012`。

最新真实 HTTP 证据写入 `results/phase4/dynamic_verification/dynamic_verification_summary.json` 和 `results/phase4/dynamic_verification/logs/`。当前动态 runner 覆盖 `WEB-REAL-0001` 至 `WEB-REAL-0012`；其中 `WEB-REAL-0007` 至 `WEB-REAL-0012` 是由 static-hunt 动态验证提升的 context-constrained confirmed cases。`intel/regression/web_real_manifest.json` 为每个 `WEB-REAL-*` 明确记录 `exploitability`，包括利用难度、默认是否可利用、必要前置条件和限制因素；高条件样例不得按默认开放漏洞解读。

## 设计文档

- `docs/drd_inspired_rearchitecture_plan.md`：继承 Dr.D 方法论的三阶段改造计划，优先推进 long-lived object proof，再补 entry/data-flow/parser，最后重做回归与排序。

## 依赖

- CodeQL CLI 2.23.8+
- Python 3.11+
- Git
- Java 11+（用于构建框架）
