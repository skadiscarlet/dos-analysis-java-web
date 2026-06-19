# dos-analysis-web 变更日志

本文档记录 dos-analysis-web 项目的所有重要变更。

---

## [2026-06-19] 第三部分 WEB-REAL 回归门禁设计

### 修改时间
2026-06-19 22:01

### 变更类型
- [文档] 第三部分回归基准设计

### 核心改动
- 使用 brainstorming 梳理 `docs/drd_inspired_rearchitecture_plan.md` 第三部分的启动方式，确认第一轮采用回归门禁优先路线。
- 明确将现有 `scripts/check_web_real_coverage.py` 的 hard-coded smoke check 升级为 manifest 驱动的 known-vuln regression gate。
- 设计 `intel/regression/web_real_manifest.json`、`scripts/check_web_real_regression.py`、`results/phase3/web_real_regression.json` 的职责边界和判定语义。
- 关键技术决策：第一轮只固定 5 个 `WEB-REAL-*` 的静态覆盖事实，不同时重写 Phase 4 排序或生成完整 validation recipe，避免扩大范围。

### 交付成果
- 新增设计文档：`docs/superpowers/specs/2026-06-19-web-real-regression-gate-design.md`
- 修改文档：`CHANGELOG.md`
- 测试/验证结果：文档变更，未运行 CodeQL、Phase 3/4 pipeline 或 AOSP regression。

### 依赖与影响
- 依赖：第一部分 proof-carrying schema、第二部分 bridge 覆盖和当前 `python3 scripts/check_web_real_coverage.py` 5/5 hit 基线。
- 对后续工作的影响：下一步可按该设计新增 manifest 和 checker，并把 WEB-REAL smoke 升级为第三部分正式回归门禁。
- 破坏性变更：无。

---

## [2026-06-16] Phase 3 Unified Modeling 实施完成

### 修改时间
2026-06-16 23:59

### 变更类型
- [新增功能] Web 统一五轴候选提取
- [新增功能] Phase 3 自动化运行与一致性验证
- [文档] Phase 3 结果报告

### 核心改动
- 实现 Web 侧 `CommonDoS.qll` 五轴抽象、`SessionState.qll` retained state 写入模型、`WebGuards.qll` 可达性模型和 `phase3_candidate_features.ql` 主查询。
- 新增 `scripts/run_phase3.py` 批量运行 5 个 Web 数据库并生成统一候选 CSV；新增 `scripts/check_phase3_consistency.py` 使用 AOSP `eval/verdict.py` 校验 CodeQL verdict。
- 第一版采用方法内与一层 helper call 的最小统一闭环，输出 evidence 和保守假设，为 Phase 4 排序与人工复核提供输入。

### 交付成果
- 新增 CodeQL：`codeql/lib/CommonDoS.qll`、`codeql/lib/SessionState.qll`、`codeql/lib/WebGuards.qll`、`codeql/queries/phase3_candidate_features.ql`
- 修改 CodeQL：`codeql/lib/WebSources.qll`、`codeql/lib/Persistence.qll`
- 新增脚本：`scripts/run_phase3.py`、`scripts/check_phase3_consistency.py`
- 新增结果：`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase3_report.md`
- 验证结果：`python3 scripts/run_phase3.py` 对 Tomcat、Spring Boot、Jetty、Undertow、Jersey 运行完成，生成 103 条候选；`phase3_consistency.json` 记录 103/103 matched，consistency 100%
- 验证结果：`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过，288 个积格点单调性成立
- 验证结果：`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression(s)

### 依赖与影响
- 依赖：Phase 2 已完成的 5 个 Web CodeQL 数据库和 `results/phase2_report.md`。
- 输出：为 Phase 4 大规模挖掘、top candidate 排序、人工复核和论文 RQ1/RQ3/RQ4 评估提供统一候选 schema。
- 影响：不修改 AOSP 工具语义；仅复用 AOSP `eval/verdict.py` 作为 verdict 权威实现。
- 破坏性变更：无。

---

## [2026-06-17] Phase 2 补齐 Spring Boot 与 JAX-RS 入口结果

### 修改时间
2026-06-17 00:20

### 变更类型
- [功能改进] Source discovery 覆盖扩展
- [Bug 修复] Spring Boot 数据库构建修复
- [文档] Phase 2 结果报告更新

### 核心改动
- 修复 Spring Boot 数据库构建：原先 Gradle 7.6.3 在 Java 21 下触发 `Unsupported class file major version 65`，改为使用 `JAVA_HOME=/usr/lib/jvm/java-17-openjdk` 并采用 CodeQL `--build-mode=none`，成功生成 `finalised: true` 数据库。
- 扩展 JAX-RS 入口识别：`phase2_source_discovery.ql` 与 `WebSources.qll` 同时支持 `javax.ws.rs` 和 `jakarta.ws.rs`，覆盖 Jersey 3.x 的 Jakarta 包名。
- 将 Spring Boot 与 Jersey/JAX-RS 结果补入 Phase 2：Spring Boot 产生 278 条参数记录，其中 Spring controller 89 条、JAX-RS 3 条；Jersey 产生 31 条参数记录，其中 JAX-RS 3 条。

### 交付成果
- 修改查询：`codeql/queries/phase2_source_discovery.ql`
- 修改模型：`codeql/lib/WebSources.qll`
- 新增测试查询：`codeql/queries/test_jaxrs_entries.ql`
- 新增/修改构建脚本：`scripts/build_springboot_db.sh`、`scripts/build_jersey_db.sh`
- 新增结果：`results/phase2/spring-boot_sources.csv`、`results/phase2/spring-boot_sources.bqrs`
- 新增结果：`results/phase2/jersey_sources.csv`、`results/phase2/jersey_sources.bqrs`
- 更新报告：`results/phase2_report.md`

### 依赖与影响
- 依赖：本机 `/usr/lib/jvm/java-17-openjdk`，CodeQL 2.23.8。
- 影响：Phase 2 结果覆盖从 3 个数据集扩展到 5 个数据集；总参数记录达到 1328 条，其中 Spring controller 89 条、JAX-RS 6 条。
- 后续：Phase 3 可以基于 Spring/JAX-RS source 清单继续做 L3 write target / retention sink 检测。

---

