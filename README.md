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
./scripts/build_databases.sh tomcat spring-boot

# 运行 Phase 1 分析
./scripts/run_phase1.sh
```

## 依赖

- CodeQL CLI 2.23.8+
- Python 3.11+
- Git
- Java 11+（用于构建框架）
