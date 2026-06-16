# dos-analysis-web 变更日志

本文档记录 dos-analysis-web 项目的所有重要变更。

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

