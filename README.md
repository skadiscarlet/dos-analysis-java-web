# dos-analysis-web

Java Web 框架的 client-state retention DoS 检测工具。

## 目标

将 dos-analysis 从 AOSP 扩展到 Java Web 服务框架，验证 client-state retention DoS 是跨领域的通用漏洞模式。

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
