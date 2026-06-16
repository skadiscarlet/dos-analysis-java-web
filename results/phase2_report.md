# Phase 2 Source Discovery Report

生成时间: 2026-06-17 00:20  
状态: ✅ 完成（Tomcat / Jetty / Undertow / Spring Boot / Jersey-JAX-RS）

## 概述

Phase 2 实现了自动化 HTTP entry point 发现和参数值空间分类（L2），并在真实框架数据库上补齐 Spring Boot 与 JAX-RS 入口点结果。

## 数据库状态

| Database | Source | Mode | finalised | Notes |
|---|---|---:|---:|---|
| `tomcat-9.0-db` | Tomcat | built | ✅ | Phase 1 既有数据库 |
| `jetty-11-db` | Jetty 11.0.15 | built | ✅ | Maven `-fn` 容错完成 |
| `undertow-2-db` | Undertow 2.3.7 | built | ✅ | 使用 JBoss Maven 仓库完成 |
| `spring-boot-2.7-db` | Spring Boot 2.7 | build-mode=none | ✅ | 固定 `JAVA_HOME=/usr/lib/jvm/java-17-openjdk` 修复 Gradle 7.6.3 与 Java 21 不兼容 |
| `jersey-3.1-db` | Jersey 3.1.3 | partial built + finalize | ✅ | 作为 JAX-RS 参考实现数据库 |

## 分析结果

| Dataset | Total parameter rows | servlet | spring | jetty | undertow | jaxrs |
|---|---:|---:|---:|---:|---:|---:|
| Tomcat | 736 | 736 | 0 | 0 | 0 | 0 |
| Jetty | 188 | 0 | 0 | 188 | 0 | 0 |
| Undertow | 95 | 0 | 0 | 0 | 95 | 0 |
| Spring Boot | 278 | 104 | 89 | 44 | 38 | 3 |
| Jersey | 31 | 0 | 0 | 28 | 0 | 3 |
| **Total** | **1328** | **840** | **89** | **260** | **133** | **6** |

> 这里的 Total 是“entry 参数行”数量；同一个入口方法有多个参数时会产生多行。当前查询用于 source discovery 和 L2 参数值空间标注。

## Spring Boot 入口点结果

Spring Boot 数据库修复后，Phase 2 主查询输出：

- `results/phase2/spring-boot_sources.csv`
- 278 条参数记录
- 其中：
  - Spring controller 参数记录：89
  - Servlet 参数记录：104
  - Jetty handler 参数记录：44
  - Undertow handler 参数记录：38
  - JAX-RS 参数记录：3

样例：

```text
Framework: servlet | Class: com.example.ResourceHandlingApplication$GetResourceServlet | Method: doGet | EntryType: servlet:doGet | Param[0]: req | Type: HttpServletRequest | ValueSpace: Unlimited
Framework: undertow | Class: io.undertow.server.HttpHandler | Method: handleRequest | EntryType: undertow:handler | Param[0]: p0 | Type: HttpServerExchange | ValueSpace: Unlimited
```

## JAX-RS 入口点结果

JAX-RS 查询已支持 `javax.ws.rs` 与 `jakarta.ws.rs` 两套包名。

- Jersey JAX-RS 测试查询：`results/test_jaxrs_jersey.csv`
- Jersey Phase 2 输出：`results/phase2/jersey_sources.csv`
- Spring Boot Phase 2 输出中也包含 3 条 JAX-RS 参数记录

Jersey 样例：

```text
Framework: jaxrs | Class: org.glassfish.jersey.server.wadl.internal.WadlResource | Method: getExternalGrammar | EntryType: jaxrs:resource | Param[1]: path | Type: String | ValueSpace: Unlimited
Framework: jaxrs | Class: org.glassfish.jersey.server.wadl.internal.WadlResource | Method: getWadl | EntryType: jaxrs:resource | Param[0]: uriInfo | Type: UriInfo | ValueSpace: Unlimited
```

## L2 参数值空间分类

实现了基于参数类型的自动分类逻辑：

```ql
paramValueSpace(Parameter p):
  - Stream: .*Stream|MultipartFile|Part|.*Channel
  - Unlimited: String|CharSequence|.*\[\]|Map|List|Set|Object|JsonNode|Bundle
  - Limited: boolean|Boolean|EnumType|数值类型
```

当前结果中大多数 Web handler 参数为 `Unlimited`，符合框架入口对象（`HttpServletRequest`、`HttpServerExchange`、`UriInfo`、`String` path 等）特征。

## 关键修复

1. **Spring Boot DB 修复**
   - 原因：Gradle 7.6.3 在 Java 21 下出现 `Unsupported class file major version 65`。
   - 修复：使用 `JAVA_HOME=/usr/lib/jvm/java-17-openjdk` 并采用 CodeQL `--build-mode=none` 成功 finalise。

2. **JAX-RS 包名支持**
   - 原查询只匹配 `javax.ws.rs`。
   - 修复后同时匹配 `javax.ws.rs` 与 `jakarta.ws.rs`，覆盖 Jersey 3.x。

3. **Jersey DB 完成**
   - Jersey 全量 Maven 构建中途停止，但已产出可用 TRAP。
   - 通过 `codeql database finalize databases/jersey-3.1-db` 成功完成数据库。

## 输出文件

```text
results/phase2/tomcat_sources.csv
results/phase2/jetty_sources.csv
results/phase2/undertow_sources.csv
results/phase2/spring-boot_sources.csv
results/phase2/jersey_sources.csv
results/test_jaxrs_jersey.csv
```

## 下一步

1. 运行 `python3 scripts/validate_phase2.py` 生成分框架采样审查清单。
2. 对 Spring/JAX-RS 结果做人工抽样 TP/FP 评估。
3. 进入 Phase 3：基于这些 source 做 L3 write target / retention sink 检测。
