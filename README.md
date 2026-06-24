# dos-analysis-web

Java Web DoS 分析与验证工具。

## 当前定位

本仓库已完成一轮 Java Web 框架/基座层 client-state retention DoS 探索，并冻结为 `WEB-REAL-*` 证据库。下一阶段主线转向具体 Java Web 应用在默认部署、默认配置或官方 quickstart 下的直接 DoS 挖掘，重点验证“低信任 HTTP 入口是否无需小众 handler 配置即可造成服务不可用”。

基座层结果继续作为方法论种子、回归集和对照组保留；除非用户明确要求刷新证据或补齐回归，不再把新增框架基座候选作为主要研究方向。

## 与 dos-analysis 的关系

本项目与 AOSP 侧 `../dos-analysis/` 保持独立实现，只复用五轴判定演算 `R/V/M/C/L` 和 verdict 语义。Web 侧不得私自修改 AOSP 权威 verdict；涉及共享语义时使用 AOSP 回归测试确认一致性。

## 目录结构

- `codeql/` - CodeQL 查询和库
- `frameworks/` - 框架源码
- `databases/` - CodeQL 数据库
- `intel/` - 情报和标注数据；应用级目标清单位于 `intel/applications/`
- `scripts/` - 自动化脚本
- `results/` - 当前保留的 Phase 3/4 权威结果、WEB-REAL 证据、static-hunt 本地归档和应用级建库日志

## 运行

```bash
# 构建数据库
./scripts/build_databases.sh tomcat spring-boot spring-boot-3 vertx micronaut
./scripts/build_jersey_db.sh --force

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

Spring Boot 3.x、Vert.x 4.x 和 Micronaut 3.x 使用固定 tag 的 CodeQL build extraction 数据库：Spring Boot `v3.5.15` -> `databases/spring-boot-3-db`，Vert.x `4.5.28` core + `vertx-web` 聚焦源码视图 `frameworks/vertx-4.5.28-build-sources` -> `databases/vertx-4-db`，Micronaut Core `v3.10.8` -> `databases/micronaut-3-db`。构建 helper 位于 `scripts/codeql_build_spring_boot_3.sh`、`scripts/codeql_build_vertx_4.sh` 和 `scripts/codeql_build_micronaut_3.sh`，会把 Gradle/Maven 依赖缓存写入本地 ignored 的 `.build-cache/`，避免污染用户 home。Spring Boot 3 当前 build-mode 目标先覆盖可稳定编译的 core 模块；autoconfigure/actuator 的 optional integration 依赖面较宽，后续需在 Maven/Gradle 缓存或 mirror 稳定后再扩展。

当前 Phase 3 会合并普通 retained-state 查询、Jersey parser/body 查询、Jersey OAuth provider-state 查询、Undertow bridge 查询和 Jetty ProxyServlet bridge 查询，统一输出到 `results/phase3/phase3_candidate_features.csv`。这些框架/基座查询进入维护模式，主要用于回归和对照，不再默认扩展为新的论文主线。

## 应用级目标与数据库

应用级默认部署 DoS 挖掘的首批目标清单位于 `intel/applications/java_web_application_targets.json`，当前固定为 50 个已经成功创建 build-mode CodeQL 数据库的 GitHub Java HTTP/Web 应用目标。源码默认下载到 `frameworks/applications/<target_id>`，build-mode CodeQL 数据库写入 `databases/applications/<target_id>-db`，构建状态、摘要和日志写入 `results/application_dbs/`。

```bash
# 重新采集 50 个目标
python3 scripts/collect_application_targets.py --limit 50 --per-query 40

# 使用国内依赖源、GitHub 加速/archive fallback 和 Java 22/21/17 重试构建 build-mode CodeQL DB
python3 scripts/build_application_databases.py \
  --threads 4 --ram 8192 --timeout 1800 \
  --use-default-github-accelerators \
  --java-home-candidate /usr/lib/jvm/java-22-openjdk \
  --java-home-candidate /usr/lib/jvm/java-21-openjdk \
  --java-home-candidate /usr/lib/jvm/java-17-openjdk

# 只重跑指定目标
python3 scripts/build_application_databases.py --skip-clone --target diyhi__bbs

# 对需要特定 JDK 的目标指定 JAVA_HOME
python3 scripts/build_application_databases.py --skip-clone \
  --java-home /usr/lib/jvm/java-22-openjdk \
  --target diyhi__bbs
```

构建脚本会生成 `.build-cache/m2/settings-china.xml` 和 `.build-cache/gradle/init-china.gradle`，优先使用阿里云、腾讯云 Maven/Gradle 相关源，并将 Gradle wrapper distribution URL 改写到腾讯云 Gradle 镜像。GitHub clone 会依次尝试直连、默认加速前缀和 codeload archive fallback；Maven/Gradle 构建会跳过测试、前端、GPG、license、antrun 等非 Java 抽取步骤，降低真实应用 build-mode 建库被非 Java 生命周期阻断的概率。

当前批量结果：本地状态中 51 个目标成功创建 build-mode CodeQL 数据库，最终 manifest 固定其中 50 个更贴近 HTTP/Web 应用的目标；每个 manifest 目标都带有 `build_status=build_succeeded`、`codeql_database_ready=true`、`database_dir`、`build_log`、`build_java_home` 和 `build_root`。最新机器状态以 `results/application_dbs/application_db_build_status.jsonl` 为准，人工摘要见 `results/application_dbs/application_db_build_summary.md`。

## 冻结的基座成果

权威索引：

- `intel/regression/web_real_manifest.json`：12 个 `WEB-REAL-*` 的稳定 ID、静态回归规则和利用条件。
- `results/phase4/verified_vulnerabilities.json`：当前机器可读 verified 摘要，已归档早期 6 个基座项和 3 个新框架项；完整冻结清单以 manifest 为准。
- `results/phase4/dynamic_verification/`：早期基座 `WEB-REAL-0001..0006` 与新框架 `WEB-REAL-0010..0012` 的 Phase 4 证据根。
- `results/static_hunts/dynamic_verification/`：新框架 static-hunt 动态验证摘要和日志。

冻结口径：

- `WEB-REAL-0001..0012` 都必须带 `exploitability`，并明确 `default_exploitable`、前置条件和限制因素。
- 真实 HTTP OOM 证明只说明 sink 可造成服务 JVM heap OOM，不等于默认应用直接可利用。
- `WEB-REAL-0007..0009` 当前在 manifest 和 dynamic runner 中保留为 `dynamic_only_pending_query`，如需完整 Phase 4 日志归档，应复跑对应 case 后再同步 `verified_vulnerabilities.*`。
- 后续论文叙事不得把高条件基座样例包装成默认开放漏洞。

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

最新真实 HTTP 证据写入 `results/phase4/dynamic_verification/dynamic_verification_summary.json`、`results/phase4/dynamic_verification/logs/` 或 static-hunt 对应目录。当前动态 runner 覆盖 `WEB-REAL-0001` 至 `WEB-REAL-0012`；其中 `WEB-REAL-0007` 至 `WEB-REAL-0012` 是 context-constrained confirmed cases。`intel/regression/web_real_manifest.json` 为每个 `WEB-REAL-*` 明确记录 `exploitability`，包括利用难度、默认是否可利用、必要前置条件和限制因素；高条件样例不得按默认开放漏洞解读。

## 下一阶段方向

主线改为具体 Java Web 应用默认部署 DoS 挖掘：

- 目标对象：官方 Docker image、release package、quickstart compose 或默认配置可启动的真实 Java 应用。
- 优先应用族：CI/CD、代码质量、制品库、身份认证、低代码/管理平台、地理信息、数据流和后台管理系统。
- 入口要求：匿名或低权限 HTTP 路由、默认启用功能、默认管理面或安装后自然暴露流程。
- Sink 范围：retained state、session/cache cardinality、metrics tag cardinality、multipart/temp file、JSON/XML/parser expansion、async/job queue、index/import/export、outbound client pool/cache。
- 真阳性门槛：默认部署真实 HTTP 触发 OOM、GC death、watchdog/restart、线程/连接池耗尽、磁盘耗尽或持续服务不可用；单纯增长曲线只能作为中间证据。

## 设计文档

- `docs/drd_inspired_rearchitecture_plan.md`：基座阶段的 Dr.D-inspired 改造记录，保留为方法论背景和对照，不作为下一阶段主线计划。

## 依赖

- CodeQL CLI 2.23.8+
- Python 3.11+
- Git
- Java 17/21/22（应用级 build-mode DB 会按 Java 22、21、17 顺序重试）
