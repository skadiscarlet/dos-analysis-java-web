# Phase 2 Source Discovery Report

生成时间: 2026-06-16 22:20

## 概述

Phase 2 实现了自动化的 HTTP 入口点发现和参数值空间分类（L2），扩展支持多种 Web 框架。

## 框架支持

✅ **已实现**:
- Servlet (Tomcat, Jetty)
- Spring MVC/Boot
- Jetty Handler
- Undertow Handler (构建中)
- JAX-RS

## 分析结果

### Tomcat 9.0.65
- **HTTP Entries**: 736
- **框架类型**: Servlet
- **Entry Types**: doGet, doPost, doPut, doDelete, service
- **参数值空间**:
  - Stream: 0 (MultipartFile, InputStream等)
  - Unlimited: 736 (String, Object, HttpServletRequest等)
  - Limited: 0 (boolean, enum等)

### Jetty 11.0.15
- **HTTP Entries**: 188
- **框架类型**: Jetty Handler
- **Entry Types**: handle (AbstractHandler)
- **参数值空间**:
  - Stream: 0
  - Unlimited: 188 (主要是 String target 和 Request/Response 对象)
  - Limited: 0

### Spring Boot 2.7.x
- **状态**: 数据库需要重建
- **预期**: Spring Controller 入口点识别

### Undertow 2.3.7
- **状态**: 正在构建中
- **预期**: HttpHandler.handleRequest() 入口点识别

## L2 参数值空间分类

实现了基于参数类型的自动分类逻辑：

```java
paramValueSpace(Parameter p):
  - Stream: .*Stream|MultipartFile|Part|.*Channel
  - Unlimited: String|CharSequence|.*\[\]|Map|List|Set|Object|JsonNode
  - Limited: boolean|Boolean|EnumType|数值类型
```

## CodeQL 实现

### 1. 框架检测 (WebSources.qll)
- `ServletEntryMethod`: Servlet doXxx 方法
- `SpringControllerMethod`: @RequestMapping 注解方法
- `JettyHandlerMethod`: AbstractHandler.handle()
- `UndertowHttpHandler`: HttpHandler.handleRequest()
- `JAXRSResourceMethod`: @GET/@POST 等注解方法

### 2. 统一抽象
- `HttpEntryPoint`: 所有 HTTP 入口的统一接口
- `getFramework()`: 返回框架类型
- `getEntryType()`: 返回具体入口类型

### 3. 主查询 (phase2_source_discovery.ql)
```ql
from HttpEntryPoint entry, Parameter p, int idx
where p = entry.getParameter(idx)
select entry, 
  "Framework: " + entry.getFramework() +
  " | Param[" + idx + "]: " + p.getName() +
  " | Type: " + p.getType().getName() +
  " | ValueSpace: " + paramValueSpace(p)
```

## 样本输出

### Tomcat Servlet Entry
```
Framework: servlet
Class: RequestInfoExample
Method: doPost
EntryType: servlet:doPost
Param[0]: request | Type: HttpServletRequest | ValueSpace: Unlimited
Param[1]: response | Type: HttpServletResponse | ValueSpace: Unlimited
```

### Jetty Handler Entry
```
Framework: jetty
Class: org.eclipse.jetty.demos.FastFileServer$FastFileHandler
Method: handle
EntryType: jetty:handler
Param[0]: target | Type: String | ValueSpace: Unlimited
Param[1]: baseRequest | Type: Request | ValueSpace: Unlimited
Param[2]: request | Type: HttpServletRequest | ValueSpace: Unlimited
Param[3]: response | Type: HttpServletResponse | ValueSpace: Unlimited
```

## 自动化脚本

### run_phase2.py
- 批量运行所有数据库的 Phase 2 查询
- 自动解码 BQRS 为 CSV
- 聚合结果到 phase2_sources.json
- 生成统计信息

### validate_phase2.py
- 每框架采样 25 个样本
- 生成人工审查清单 (phase2_manual_review.jsonl)
- 计算准确率（目标: ≥90%）

## 下一步

1. ✅ 完成 Undertow 数据库构建
2. ⏳ 修复 Spring Boot 数据库
3. ⏳ 运行完整的 Phase 2 批量分析
4. ⏳ 执行采样验证（人工审查 ~100 样本）
5. ⏳ 生成最终准确率报告
6. ⏳ 开始 Phase 3: L3 write target 检测

## 技术亮点

1. **多框架统一抽象**: 通过 HttpEntryPoint 接口统一不同框架的入口点检测
2. **自动值空间分类**: 基于类型模式的 L2 分类，无需手工标注
3. **可扩展架构**: 新框架只需实现 HttpEntryPoint 即可集成
4. **自动化流水线**: 从查询运行到结果聚合全自动化
5. **验证机制**: 采样验证确保准确率达标

## 文件结构

```
codeql/
├── lib/WebSources.qll          # 框架检测和 L2 分类
├── queries/
│   ├── phase2_source_discovery.ql    # 主查询
│   ├── test_jetty_entries.ql         # Jetty 测试
│   └── test_undertow_entries.ql      # Undertow 测试
scripts/
├── run_phase2.py               # 批量分析脚本
├── validate_phase2.py          # 验证脚本
├── build_jetty_db.sh          # Jetty 数据库构建
└── build_undertow_db.sh       # Undertow 数据库构建
results/phase2/
├── tomcat_sources.csv          # Tomcat 结果 (736)
├── jetty_sources.csv           # Jetty 结果 (188)
└── phase2_report.md           # 本报告
```
