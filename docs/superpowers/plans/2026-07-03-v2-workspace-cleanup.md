# V2 Workspace Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove legacy analyzer code and context while preserving the database, source, PoC, and historical evidence assets required by the v2 static analyzer rewrite.

**Architecture:** This is a cleanup baseline, not a new analyzer implementation. The work deletes legacy tool surfaces, rewrites high-context documents to v2-only guidance, resets the changelog to a v2 baseline, and verifies that only the approved evidence/database directories remain from the old workflow.

**Tech Stack:** Shell, Git, Markdown, Python 3 for verification scripts.

---

## File Structure

Preserve these paths exactly:

- `databases/`: existing CodeQL databases.
- `frameworks/`: existing downloaded source trees and application source roots.
- `poc/`: existing advisory PoC archive, unchanged.
- `results/static_hunts/`: historical static-hunt evidence.
- `results/application*`: application-level database/static/dynamic evidence directories.
- `results/java_web_dos_batch/`: batch DoS analysis evidence.
- `docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md`: approved v2 design spec.
- `docs/superpowers/plans/2026-07-03-v2-workspace-cleanup.md`: this plan.

Delete or rewrite these legacy paths:

- Delete: `codeql/`
- Delete: `scripts/`
- Delete: `tests/`
- Delete: `dynamic-verification/`
- Delete: `security-disclosures/`
- Delete: `skills/`
- Delete: `dos-web-analyzer`
- Delete: `config.yaml`
- Delete: `docs/drd_inspired_rearchitecture_plan.md`
- Delete: `docs/superpowers/specs/2026-06-20-static-hunt-dynamic-verification-design.md`
- Delete: `docs/superpowers/plans/2026-06-21-static-hunt-dynamic-verification.md`
- Delete: `results/phase3_report.md`
- Delete: `results/phase4_report.md`
- Delete: `results/phase3/`
- Delete: `results/phase4/`
- Delete: `results/static.zip`
- Remove project-local legacy skills if present: `.codex/skills/java-web-dos-hunter/`, `.codex/skills/java-web-dos-batch-hunter/`, `.codex/skills/java-web-dos-dynamic-validator/`
- Rewrite: `AGENTS.md`
- Rewrite: `README.md`
- Rewrite: `CHANGELOG.md`

`poc/` must not be modified by this cleanup, even though many `poc/` files are currently dirty in the working tree.

## Task 1: Pre-Cleanup Inventory And Guard Rails

**Files:**
- Read: repository working tree
- No file modifications

- [ ] **Step 1: Capture the current dirty state**

Run:

```bash
git status --short
```

Expected: output includes existing dirty `poc/` advisory files, `.gitignore`, `CHANGELOG.md`, `scripts/generate_advisory_pocs.py`, legacy `skills/` deletion state, and possible `.codex/skills/` untracked directories.

- [ ] **Step 2: Confirm the preserve roots exist**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

required = [
    "databases",
    "frameworks",
    "poc",
    "docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md",
]
missing = [path for path in required if not Path(path).exists()]
if missing:
    raise SystemExit(f"missing preserved paths: {missing}")
print("preserve roots present")
PY
```

Expected: prints `preserve roots present`.

- [ ] **Step 3: Print the deletion manifest before deleting anything**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

delete_paths = [
    "codeql",
    "scripts",
    "tests",
    "dynamic-verification",
    "security-disclosures",
    "skills",
    "dos-web-analyzer",
    "config.yaml",
    "docs/drd_inspired_rearchitecture_plan.md",
    "docs/superpowers/specs/2026-06-20-static-hunt-dynamic-verification-design.md",
    "docs/superpowers/plans/2026-06-21-static-hunt-dynamic-verification.md",
    "results/phase3_report.md",
    "results/phase4_report.md",
    "results/static.zip",
    ".codex/skills/java-web-dos-hunter",
    ".codex/skills/java-web-dos-batch-hunter",
    ".codex/skills/java-web-dos-dynamic-validator",
]
for path in delete_paths:
    marker = "present" if Path(path).exists() else "absent"
    print(f"{marker}\t{path}")
PY
```

Expected: every path is printed with `present` or `absent`; no preserved path appears in this manifest.

## Task 2: Delete Legacy Tooling And Old Generated Outputs

**Files:**
- Delete: paths listed in Task 1 deletion manifest
- Preserve: `databases/`, `frameworks/`, `poc/`, `results/static_hunts/`, `results/application*`, `results/java_web_dos_batch/`

- [ ] **Step 1: Remove tracked legacy paths through Git**

Run:

```bash
git rm -r --ignore-unmatch \
  codeql \
  scripts \
  tests \
  dynamic-verification \
  security-disclosures \
  skills \
  dos-web-analyzer \
  config.yaml \
  docs/drd_inspired_rearchitecture_plan.md \
  docs/superpowers/specs/2026-06-20-static-hunt-dynamic-verification-design.md \
  docs/superpowers/plans/2026-06-21-static-hunt-dynamic-verification.md \
  results/phase3 \
  results/phase4 \
  results/phase3_report.md \
  results/phase4_report.md \
  results/static.zip
```

Expected: Git reports removals for tracked paths that exist. `scripts/generate_advisory_pocs.py` is deleted as part of `scripts/` even though it has dirty changes, because the user requested old tool removal.

- [ ] **Step 2: Remove project-local legacy skill directories**

Run:

```bash
rm -rf \
  .codex/skills/java-web-dos-hunter \
  .codex/skills/java-web-dos-batch-hunter \
  .codex/skills/java-web-dos-dynamic-validator
```

Expected: those project-local skill directories no longer exist if they were present.

- [ ] **Step 3: Verify preserved roots were not removed**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

preserved = [
    "databases",
    "frameworks",
    "poc",
    "docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md",
]
missing = [path for path in preserved if not Path(path).exists()]
if missing:
    raise SystemExit(f"preserved path was removed: {missing}")
print("preserved paths intact")
PY
```

Expected: prints `preserved paths intact`.

## Task 3: Rewrite `AGENTS.md` As V2-Only Context

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Replace `AGENTS.md` with concise v2 guidance**

Write this exact content to `AGENTS.md`:

```markdown
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
```

- [ ] **Step 2: Verify old context was removed from `AGENTS.md`**

Run:

```bash
! rg -n "Phase 3|Phase 4|WEB-REAL|五轴判定|client-state retention|动态验证 runner" AGENTS.md
```

Expected: command exits with status 0 because `rg` finds no old-context matches in `AGENTS.md`.

## Task 4: Rewrite `README.md` As A Minimal V2 Project Entry

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md` with v2 overview**

Write this exact content to `README.md`:

```markdown
# dos-analysis-web v2

Static analyzer for resource-exhaustion DoS patterns in Java Web and adjacent Java network applications.

## Model

```text
Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)
```

The v2 pipeline is static-only in its first release:

```text
entries -> growth -> flows -> bounds -> conclude -> benchmark -> report
```

`growth` follows the required sequence:

```text
CodeQL raw screening -> ML filter/ranker -> LLM summary -> rule/static verification
```

## Preserved Evidence

The rewrite preserves:

- `databases/`
- `frameworks/`
- `poc/`
- `results/static_hunts/`
- `results/application*`
- `results/java_web_dos_batch/`

`poc/` remains an unchanged evidence archive. Existing dynamic evidence is imported only as oracle material, ML seeds, and benchmark evidence. v2 does not run dynamic validation in its first release.

## Design

The approved v2 design is:

- `docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md`

## Status

The workspace is being cleaned for v2 implementation. Legacy phase-based analyzer code and reports are intentionally removed to avoid contaminating future agent context.
```

- [ ] **Step 2: Verify README no longer describes old workflows**

Run:

```bash
! rg -n "phase3|phase4|WEB-REAL|client-state retention|run_dynamic_verification|check_phase3_consistency" README.md
```

Expected: command exits with status 0 because the README no longer references old workflows.

## Task 5: Reset `CHANGELOG.md` To V2 Baseline

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Replace `CHANGELOG.md` with v2-only history**

Write this exact content to `CHANGELOG.md`:

```markdown
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
- 删除旧工具与旧上下文：`codeql/`、`scripts/`、`tests/`、`dynamic-verification/`、旧 `dos-web-analyzer`、旧 Phase 报告和旧文档。
- 重写上下文文档：`AGENTS.md`、`README.md`、`CHANGELOG.md`。
- 保留设计规格：`docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md`。

### 依赖与影响
- 依赖：已批准的 v2 重写设计规格。
- 对后续工作的影响：后续实现应从 v2 CLI/package/schema 基线开始，不再参考旧 Phase 工具。
- 破坏性变更：删除旧工具代码和旧报告；不删除指定保留资产，不修改 `poc/` 证据内容。
```

- [ ] **Step 2: Verify old changelog entries are gone**

Run:

```bash
! rg -n "2026-06|2026-07-01|Phase 3|Phase 4|WEB-REAL" CHANGELOG.md
```

Expected: command exits with status 0 because the changelog contains only the v2 cleanup baseline.

## Task 6: Verify Context Cleanup

**Files:**
- Read: repository tree
- No file modifications

- [ ] **Step 1: Assert removed paths are gone**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

removed = [
    "codeql",
    "scripts",
    "tests",
    "dynamic-verification",
    "security-disclosures",
    "skills",
    "dos-web-analyzer",
    "config.yaml",
    "docs/drd_inspired_rearchitecture_plan.md",
    "docs/superpowers/specs/2026-06-20-static-hunt-dynamic-verification-design.md",
    "docs/superpowers/plans/2026-06-21-static-hunt-dynamic-verification.md",
    "results/phase3_report.md",
    "results/phase4_report.md",
    "results/phase3",
    "results/phase4",
    "results/static.zip",
    ".codex/skills/java-web-dos-hunter",
    ".codex/skills/java-web-dos-batch-hunter",
    ".codex/skills/java-web-dos-dynamic-validator",
]
still_present = [path for path in removed if Path(path).exists()]
if still_present:
    raise SystemExit(f"legacy paths still present: {still_present}")
print("legacy paths removed")
PY
```

Expected: prints `legacy paths removed`.

- [ ] **Step 2: Assert preserved paths are present**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

preserved = [
    "databases",
    "frameworks",
    "poc",
    "docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md",
]
missing = [path for path in preserved if not Path(path).exists()]
if missing:
    raise SystemExit(f"preserved paths missing: {missing}")

result_roots = [path for path in Path("results").glob("application*")]
if not result_roots:
    raise SystemExit("no results/application* paths remain")
print("preserved paths present")
PY
```

Expected: prints `preserved paths present`.

- [ ] **Step 3: Check top-level old-context docs**

Run:

```bash
! rg -n "WEB-REAL|五轴|client-state retention|run_dynamic_verification|check_phase3_consistency|Phase 3|Phase 4" AGENTS.md README.md CHANGELOG.md
```

Expected: command exits with status 0 because top-level context docs no longer mention old workflows.

- [ ] **Step 4: Confirm `poc/` content was not modified by this cleanup**

Run:

```bash
git diff --name-only -- poc | sed -n '1,20p'
```

Expected: output may show pre-existing dirty `poc/` files from before this cleanup. The cleanup implementation must not add new `poc/` paths to the staged diff.

## Task 7: Commit Cleanup Baseline

**Files:**
- Commit all cleanup changes from Tasks 2-6

- [ ] **Step 1: Review unstaged and staged changes**

Run:

```bash
git status --short
```

Expected: deleted legacy files, rewritten top-level docs, and untouched pre-existing dirty `poc/` files are visible. `poc/` files should remain unstaged unless they were already staged before this plan.

- [ ] **Step 2: Stage cleanup files only**

Run:

```bash
git add -A \
  AGENTS.md \
  README.md \
  CHANGELOG.md \
  codeql \
  scripts \
  tests \
  dynamic-verification \
  security-disclosures \
  skills \
  dos-web-analyzer \
  config.yaml \
  docs \
  results/phase3 \
  results/phase4 \
  results/phase3_report.md \
  results/phase4_report.md \
  results/static.zip
```

Expected: cleanup deletions and doc rewrites are staged. Dirty `poc/` files are not staged by this command.

- [ ] **Step 3: Verify no `poc/` file is staged**

Run:

```bash
if git diff --cached --name-only | rg '^poc/'; then
  echo "poc files staged unexpectedly" >&2
  exit 1
fi
echo "no poc files staged"
```

Expected: prints `no poc files staged`.

- [ ] **Step 4: Verify diff does not contain whitespace errors**

Run:

```bash
git diff --cached --check
```

Expected: no output and exit status 0.

- [ ] **Step 5: Commit cleanup baseline**

Run:

```bash
git commit -m "chore: reset workspace for v2 analyzer"
```

Expected: commit succeeds and includes only cleanup deletions plus `AGENTS.md`, `README.md`, `CHANGELOG.md`, and retained v2 docs.

## Acceptance Criteria

- Legacy analyzer code, old scripts, old CodeQL queries, old tests, old dynamic verification harness, old reports, and old context docs are removed.
- `AGENTS.md`, `README.md`, and `CHANGELOG.md` contain only v2 context.
- `databases/`, `frameworks/`, `poc/`, `results/static_hunts/`, `results/application*`, and `results/java_web_dos_batch/` remain present.
- No `poc/` content is staged or modified by the cleanup implementation.
- The cleanup commit is separated from later v2 analyzer implementation.
