# dos-analysis-web v2 Agent Instructions

**重要**：本仓库内所有助手与用户交流必须使用简体中文；代码、命令、schema 字段和英文报告内容可保留英文。

## 当前定位

`dos-analysis-web` v2 是面向 Java Web 与相邻 Java 网络服务的资源耗尽型 DoS 静态分析平台。旧阶段化流程、legacy verdict compatibility、历史验证样例叙事和旧动态验证执行链不再作为当前上下文。

v2 核心模型：

```text
Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)
```

分析顺序固定为：

```text
E extraction
  -> G detection: CodeQL raw screening -> bounded slice -> LLM Growth Contract -> rule/static verification
  -> E -> G flow proof
  -> B candidate extraction
  -> lifecycle facts: CodeQL -> CFG/data flow -> Lifecycle Evidence Graph -> contract templates
  -> EffectiveB(E, G, path, B)
  -> static conclusion
```

## 本轮保留资产

不得删除或重写：

- `databases/`
- `frameworks/`
- `poc/`
- `results/static_hunts/`
- `results/application*`
- `results/java_web_dos_batch/`
- `docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md`

`poc/` 是证据归档，保持原样，不英文化、不重写 advisory。

## 当前禁止项

- 不恢复旧阶段化流程。
- 不恢复 legacy verdict compatibility。
- 不把静态结论表述为动态 confirmed。
- v2 工具本身不内置、不自动运行动态 DoS 验证；普通 v2 静态扫描只输出静态结论。
- 用户明确要求动态验证时，agent 可以在本地一次性、隔离、受控环境中执行动态验证，并将产物写入独立结果目录；动态结论必须与静态结论分开标注。
- 不修改 AOSP 侧 `../dos-analysis/`。
- 不对大型 `databases/`、`frameworks/`、`results/` 做无界全仓搜索。

## 输出口径

普通扫描输出：

- `static_vulnerable`
- `static_safe`
- `static_unknown`

Benchmark 模式才映射 oracle label。`binary_truth_collection` 可作为 static positive seeds 和评估 oracle，但不能等同于动态 confirmed vulnerability。

## 文档目录约定

- 论文相关内容统一放在 `docs/paper/`，包括论文设计、outline、中文/英文草稿、摘要、图表计划、rebuttal 草稿和 camera-ready 相关材料。
- `docs/research/` 只放研究笔记、taxonomy、Stage 设计、文献/方法调研和工程方案，不放论文正文或论文组织材料。
- 如果已在 `docs/research/` 下生成论文相关文档，应移动到 `docs/paper/` 并同步更新引用路径和 `CHANGELOG.md`。

## 变更要求

每次修改项目后必须更新 `CHANGELOG.md`。v2 实施期间 changelog 以 v2 baseline 重新开始，按时间倒序记录。
