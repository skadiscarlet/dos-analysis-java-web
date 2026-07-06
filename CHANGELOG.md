# dos-analysis-web v2 CHANGELOG

This changelog starts at the v2 cleanup baseline. Older phase-based analyzer history was intentionally removed from the active project context.

---

## [2026-07-06] Stage0-Stage5 工具完整流程设计

### 修改时间
2026-07-06 13:34

### 变更类型
- [设计] 新增完整工具 pipeline spec
- [工程] 固化 Step0 + Stage1-5 执行边界
- [方法] 明确 CodeQL/LLM/ML/SMT 为阶段内技术依赖

### 核心改动
- 新增 `docs/superpowers/specs/2026-07-06-stage0-stage5-tool-pipeline-design.md`，将 docs 下 Stage1、Stage2/5、Stage3/4 设计整合为工具开发规格。
- 严格采用 `Step0 Project Profiling -> Stage1 E extraction -> Stage2 G detection -> Stage3 E->G flow proof -> Stage4 B candidate extraction -> Stage5 EffectiveB proof`。
- 明确 CodeQL、LLM、ML ranker、SMT/Max-SMT 不作为独立 worker 或旁路阶段，只能作为各 StageRunner 内部采用的技术。
- 明确第一版是完整实现：真实 CodeQL 查询、真实 LLM claim、真实 ML ranker、真实 GECG、真实 path proof、真实 bound extraction 和真实 obligation proof；缺失依赖时 run fail，不用 mock/stub/fallback 继续。
- 固化 run artifact 目录、CLI、preflight、状态机、schema、Stage5 verdict 规则、测试分层和验收标准。

### 交付成果
- 完成 Stage0-Stage5 工具开发总规格。
- 固定 `static_unknown` 与 run failure 的区别：前者是 Stage5 完整证明后的静态结论，后者是工具或依赖失败。
- 明确 Stage5 是唯一 `static_vulnerable/static_safe/static_unknown` producer。

### 依赖与影响
- 依赖：`docs/research/2026-07-04-stage1-design.md`、`docs/research/2026-07-04-stage2-stage5-design.md`、`docs/research/2026-07-04-stage3-stage4-design.md` 和 `docs/research/2026-07-03-poc-resource-growth-taxonomy.md`。
- 对后续工作的影响：后续 implementation plan 应从 schema/CLI/preflight 开始，再按 Stage0-5 顺序实现完整工具链。

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
