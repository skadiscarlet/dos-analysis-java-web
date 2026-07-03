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
  -> G detection: CodeQL raw screening -> ML filter/ranker -> LLM summary -> rule/static verification
  -> E -> G flow proof
  -> B candidate extraction
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
- 不运行动态 DoS 验证；v2 第一版只输出静态结论。
- 不修改 AOSP 侧 `../dos-analysis/`。
- 不对大型 `databases/`、`frameworks/`、`results/` 做无界全仓搜索。

## 输出口径

普通扫描输出：

- `static_vulnerable`
- `static_safe`
- `static_unknown`

Benchmark 模式才映射 oracle label。`binary_truth_collection` 全量可作为 ML static positive seeds，但不能等同于动态 confirmed vulnerability。

## 变更要求

每次修改项目后必须更新 `CHANGELOG.md`。v2 实施期间 changelog 以 v2 baseline 重新开始，按时间倒序记录。
