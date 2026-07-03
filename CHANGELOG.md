# dos-analysis-web v2 CHANGELOG

This changelog starts at the v2 cleanup baseline. Older phase-based analyzer history was intentionally removed from the active project context.

---

## [2026-07-03] v2 workspace cleanup baseline

### 修改时间
2026-07-03 22:19

### 变更类型
- [文档] v2 上下文清理
- [功能删除] 旧工具入口、旧脚本、旧查询、旧测试和旧报告清理

### 核心改动
- 清理旧 Phase 工具链和旧报告上下文，避免后续 agent 读取旧模型、旧 verdict 或旧动态验证流程。
- 将 `AGENTS.md`、`README.md` 和 `CHANGELOG.md` 重置为 v2-only 语义。
- 保留 `databases/`、`frameworks/`、`poc/`、`results/static_hunts/`、`results/application*`、`results/java_web_dos_batch/` 作为 v2 输入资产。

### 交付成果
- 删除旧工具与旧上下文：`codeql/`、`scripts/`、`tests/`、`dynamic-verification/`、旧 `dos-web-analyzer`、旧 Phase 结果/报告和旧文档。
- 重写上下文文档：`AGENTS.md`、`README.md`、`CHANGELOG.md`。
- 保留设计规格：`docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md`。

### 依赖与影响
- 依赖：已批准的 v2 重写设计规格。
- 对后续工作的影响：后续实现应从 v2 CLI/package/schema 基线开始，不再参考旧 Phase 工具。
- 破坏性变更：删除旧工具代码和旧报告；不删除指定保留资产，不修改 `poc/` 证据内容。
