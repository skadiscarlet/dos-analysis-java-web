# Dr.D-Inspired Web DoS Analyzer 改造计划

生成时间: 2026-06-18 23:53

更新时间: 2026-06-19 21:40

本文档将当前工具改造任务按论文优先级重排为三部分。第一部分必须首先实施，目标是在继承 Dr.D 设计优势的基础上形成 Web 侧新抽象；第二部分是支撑第一部分落地的工程化覆盖；第三部分才是回归、capacity/lifespan 证明和 Phase 4 排序。

## 总体判断

当前 Phase 3/4 的核心缺口不是 sink 数量不足，而是缺少 `request handler -> long-lived object -> request data flow` 的中间层。现有模型主要在 HTTP entry 附近寻找 `Map/List/Set` 的 `put/add`，因此容易把 `HeaderMap`、局部集合、测试和示例路径排到高分，同时无法稳定发现已经动态验证的 Jersey OAuth1、Jersey multipart、Jetty ProxyServlet 等真实路径。

Dr.D 的可继承点是：先定位容器内部 request handler，再识别 long-lived class/object，最后证明 request data 能写入 long-lived object。Web 侧需要进一步创新：把 long-lived object 从简单 static/singleton 扩展为 Servlet/filter/handler/provider/client/container manager 生命周期对象，并显式建模 nested retained state、DI provider、framework lifecycle root 和 parser-processing lifetime。

## 第一部分：Proof-Carrying Retention Sink 改造

优先级: 必须首先做。

对应原始任务: P2。

论文定位: 这是本工具区别于简单 sink 扫描、并继承和扩展 Dr.D 的主要创新点。第一部分的直接产物不是抽象图本身，而是一组可供后续污点分析使用的具体 retention sink。

### 目标

- 将 Phase 3 的 sink 从语法上的 `Map.put/add` 升级为带生命周期证明的具体 `WebRetentionSink`。
- 明确后续 taint analysis 的终点：必须是具体 mutation call，并携带 `receiver_proof` 和 `growth_driver`。
- 从“写入方法声明类型像 Map/Cache”改为“写入 receiver 可追溯到跨请求、跨连接、跨组件或跨进程保留对象”。
- 让候选能解释真实漏洞的 retained state，而不是只在同文件附近打出无关 `HeaderMap.add`。

### Brainstorming 结论

本部分采用“先产出可证明 sink，再接入完整 taint”的路线。原因是当前 Phase 3 已经能找到大量 mutation call，但排序噪声主要来自 receiver 生命周期不可解释；如果先扩展 source/data-flow，会把更多 request-local 写入带入 Phase 4，继续扩大人工复核成本。

第一部分的最小闭环应同时回答四个问题：

1. `call` 是否是真实增长点，而不是 getter、builder 或 header copy。
2. `receiver` 是否能证明来自跨请求保留对象。
3. `growth_driver` 是否能被后续 request taint 追踪。
4. 输出 schema 是否足够稳定，可被 Phase 4、回归 manifest 和论文表格共同消费。

因此，本部分不追求一次覆盖所有 Web 框架语义，而是先建立 proof-carrying sink 的接口边界：宁可把无法证明 receiver 的写入降级到 debug，也不把它们作为 P0/P1 high-risk 候选。

### 核心抽象

```text
WebRetentionSink :=
  (call, receiver, growth_driver, sink_shape, growth_dimension,
   lifecycle_root, retained_object, receiver_proof, proof_source)
```

其中 `call` 必须是源码中的具体 mutation call，例如 `Map.put`、`List.add`、`setAttribute`、`register`、`bodyParts.add` 或 protocol/session table update。`growth_driver` 是后续污点分析需要追踪到 sink 的参数、字段或大小驱动；`receiver_proof` 证明 receiver 会在 request 结束后继续保留。没有 `receiver_proof` 的调用点不进入 high-risk sink 集合。

建议新增或改造 CodeQL 抽象接口：

```ql
abstract class WebRetentionSink extends MethodCall {
  abstract Expr getReceiverExpr();
  abstract Expr getGrowthDriver();
  abstract string getSinkShape();
  abstract string getGrowthDimension();
  abstract string getGrowthDriverKind();
  abstract string getLifecycleRoot();
  abstract string getRetainedObject();
  abstract string getRetentionPath();
  abstract string getReceiverProof();
  abstract string getProofSource();
  abstract string getProofConfidence();
}
```

`growth_driver` 按 sink 形态选择：

- `Map.put(k, v)`、`compute`、`merge`：`k` 或 `v`。
- `List.add(v)`、`Set.add(v)`、`Queue.offer(v)`：`v`。
- `setAttribute(k, v)`：attribute name 或 stored value。
- `register(name, obj)`、`addNode`、`addHost`、`addDestination`：registry key、host、origin、token 或 path。
- `bodyParts.add(part)`、MIME header accumulator：part count、header count 或 part metadata。
- temp file / stream write：byte volume 或 temp file volume。

### CodeQL 落地接口草案

建议把第一部分拆成三层库，避免把生命周期事实、receiver 追踪和 sink 形态全部塞回 `SessionState.qll`。

```text
Persistence.qll
  LifecycleRootFact
  WebLifecycleRoot
  RetainedField
  RetainedObjectExpr

RetentionSinks.qll
  WebRetentionSink
  CollectionRetainedSink
  AttributeRetentionSink
  RegistryRetentionSink
  NestedRetentionSink
  ParserRetentionSink
  ProtocolSessionRetentionSink
  ReceiverProof

SessionState.qll
  WebClientStateWrite consumes WebRetentionSink
  Axis/value derivation keeps existing CommonDoS contract
```

建议接口：

```ql
abstract class LifecycleRootFact extends TTop {
  abstract string getSource();
  abstract RefType getRootType();
  abstract Field getRootField();
  abstract string getLifetime();
  abstract string getConfidence();
  abstract string getEvidence();
}

abstract class ReceiverProof extends TTop {
  abstract Expr getReceiverExpr();
  abstract Field getRetainedField();
  abstract string getLifecycleRoot();
  abstract string getRetainedObject();
  abstract string getRetentionPath();
  abstract string getProofKind();
  abstract string getProofSource();
  abstract string getConfidence();
}
```

实现上先使用字段和调用表达式的轻量匹配，不依赖完整类型层级：

- receiver 是 `this.field`、`Type.staticField`、`field` 的直接访问时，绑定到 `RetainedField`。
- receiver 是 `this.getX()` 或 `obj.getX()` 时，检查 getter body 是否返回 retained field，第一阶段深度限制为 1。
- receiver 是 `this.field.getX().put(...)` 时，将 `this.field` 作为 lifecycle root，`getX()` 作为 retained object chain 的一环。
- receiver 是 `outer.get(k).put(...)` 时，保留 outer receiver proof，并把 inner mutation 标记为 `nested_retained_map_put`。
- 对 parser/protocol lifetime，允许以 enclosing type 为 root，但 proof 必须明确为 `parser_lifetime` 或 `protocol_session_lifetime`，不能混同为 process-lifetime。

### Proof Schema

Phase 3 新 schema 至少保留以下字段。字段名保持英文，便于 CSV/JSON/paper table 共用。

```text
sink_id
framework
entry_fqn
entry_file
entry_line
sink_fqn
sink_file
sink_line
sink_shape
growth_dimension
growth_driver_kind
growth_driver_expr
growth_driver_index
receiver_expr
receiver_type
lifecycle_root
retained_object
retained_field
retention_path
receiver_proof
proof_source
proof_confidence
proof_evidence
request_flow_kind
container_kind
demotion_reason
axis_r
axis_v
axis_m
axis_c
axis_l
verdict
debug_notes
```

其中：

- `sink_shape` 描述 mutation 形态，例如 `retained_map_put`、`retained_map_compute`、`nested_retained_map_put`、`registry_register`、`session_attribute_set`、`parser_part_accumulator`。
- `growth_dimension` 描述增长维度，例如 `key_cardinality`、`value_size`、`element_count`、`part_count`、`header_count`、`destination_count`、`node_count`、`host_count`、`byte_volume`。
- `growth_driver_kind` 描述后续 taint 入口，例如 `map_key`、`stored_value`、`attribute_name`、`registry_key`、`part_metadata`、`stream_bytes`。
- `sink_id` 建议由 `sink_file:sink_line:method:name` 组成，便于人工复核、动态验证和 known-vuln 表关联。
- `receiver_proof` 是可读证明摘要，例如 `static_field:DefaultOAuth1Provider.requestTokenByTokenString`。
- `proof_source` 是机器可聚合来源，例如 `static_field`、`servlet_field`、`handler_field`、`framework_lifecycle`、`parser_lifetime`、`drd`。
- `proof_confidence` 第一阶段建议只使用 `high`、`medium`、`debug`，避免过早引入细粒度分数。

### 候选分层策略

第一部分输出三层候选，而不是只输出 high-risk：

| 层级 | 条件 | 用途 |
| --- | --- | --- |
| `confirmed_sink` | 有具体 mutation call、growth driver、receiver proof | Phase 3/4 主输入 |
| `needs_flow` | 有 receiver proof，但 request data flow 尚未证明 | 第二部分 taint 扩展输入 |
| `debug_rejected` | 有 mutation call，但 receiver 是 request-local、header、builder、测试路径或 proof 缺失 | 噪声审计，不进入 P0/P1 |

这能避免第一阶段因为 entry/data-flow 还不完整而丢失真实 retained object，同时保证 Phase 4 不再把无 proof 的 `HeaderMap.add` 排到前面。

### 设计任务

1. 建立 `WebRetentionSink` sink 家族。
   - `CollectionRetainedSink`：`Map.put/putIfAbsent/compute/merge`，`List.add`，`Set.add`，`Queue.offer`。
   - `AttributeRetentionSink`：`HttpSession.setAttribute`、`ServletContext.setAttribute`、framework context attributes。
   - `RegistryRetentionSink`：`register`、`addNode`、`addHost`、`addBalancer`、`addDestination`、`addProvider`。
   - `NestedRetentionSink`：`outer.get(k).put(innerKey, value)`；outer bounded 但 inner unbounded 时仍保留为高危 sink。
   - `ParserRetentionSink`：multipart `bodyParts.add`、MIME part/header accumulator、temp file bookkeeping。
   - `ProtocolSessionRetentionSink`：HTTP/2 stream table、priority tree、connection pending queue。

2. 新增 receiver proof 规则。
   - R1 static field receiver：receiver 可追到 static container field。
   - R2 lifecycle class field：receiver 可追到 servlet、filter、handler、provider、client 或 manager 的实例字段。
   - R3 retained object chain：receiver 可追到 `this.field.innerField`，深度先限制为 2-3 层。
   - R4 getter proof：receiver 来自 `getX()`，且 `getX()` 返回 retained field 或 retained object field。
   - R5 framework-managed object：receiver 被 `ServletContext`、HK2、Jetty lifecycle、Undertow handler tree 等框架生命周期根持有。
   - R6 parser/protocol lifetime：receiver 属于 parser transaction、connection、HTTP/2 session 等非 request-local 生命周期。

3. 新增 lifecycle root fact 层，接入 Dr.D long-life class 识别结果。
   - 统一事实格式：`source`、`class_fqn`、`field`、`lifetime`、`confidence`、`evidence`。
   - `source` 可取 `drd`、`web_taxonomy`、`static_field`、`framework_lifecycle`、`llm_checked`。
   - Dr.D long-life class 结果导入为 `source=drd`、`evidence=drd_long_life_class`、`lifetime=ProcessLifetime` 或 `ComponentLifetime`。
   - Dr.D 结果只能作为 receiver proof 的证据来源；不能因为 class long-lived 就把类内所有 collection 写入都当 sink。

4. 新增 request/local scope 过滤与降级。
   - `HeaderMap`、response headers、request attachments 默认不进入 P0/P1。
   - 方法局部 `new HashMap/new ArrayList` 默认过滤，除非被写回 retained field、session、context 或 framework manager。
   - builder、temporary parser-local object、测试、示例和 smoke path 默认降级，仅保留 debug 输出。

5. 新增 proof-carrying 输出字段。
   - 输出候选时保存 `sink_id`、`sink_shape`、`growth_dimension`、`growth_driver_kind`、`receiver_expr`。
   - 输出 `lifecycle_root`、`retained_object`、`retention_path`、`receiver_proof`、`proof_source`、`proof_confidence`。
   - 后续 Phase 4 排序只能消费这些证明项，不再凭 `container_kind=static_container` 直接高分。

6. 建立 known-vuln 对照表，作为第一部分本地验收基准。
   - 表格记录 `WEB-REAL-*`、期望 mutation call、期望 receiver proof、期望 growth driver、应降级的相邻噪声 sink。
   - 第一阶段不要求完整 HTTP 到 sink call path，但要求 retained sink 本身可被查询输出。
   - 该表后续迁移到第三部分 regression manifest。

7. 保留 debug 输出，支持人工审计误杀。
   - `debug_rejected` 应包含 reject reason，例如 `request_local_collection`、`header_map`、`builder_object`、`test_or_example_path`、`missing_receiver_proof`。
   - Debug 输出可以进入 `results/phase3/debug_retention_sinks.csv`，但不进入 Phase 4 ranked candidates。

### 第一阶段实现顺序

1. 新增 `codeql/lib/RetentionSinks.qll`，先实现 `CollectionRetainedSink`、`AttributeRetentionSink`、`RegistryRetentionSink` 三类。
2. 在 `Persistence.qll` 中新增 `LifecycleRootFact`、`RetainedField`、`ReceiverProof` 的基础事实，覆盖 static field、servlet/filter/handler/provider/client/manager instance field、getter proof。
3. 修改 `SessionState.qll`，让 `WebClientStateWrite` 消费 `WebRetentionSink`，保留旧 `WebContainerWrite` 作为 debug/rejected 输入。
4. 修改 `phase3_candidate_features.ql`，输出 proof schema；新增或同步更新 debug query。
5. 用 `WEB-REAL-0001/0003/0004/0005` 做静态 smoke 验收：先看 sink/proof 是否命中，再看 HeaderMap/request-local 是否降级。
6. 运行 Phase 3 consistency 和 Phase 4 analyze，确认 schema 消费链没有断裂；AOSP verdict 语义未改时仍运行 monotonicity/regression 作为守护验证。

### 相关文件

- `codeql/lib/Persistence.qll`
  - 新增 `LifecycleRootFact`、`WebLifecycleRoot`、`RetainedField`、`ReceiverProof`。
  - 接入 Dr.D long-life class 识别结果，作为 `proof_source=drd` 的生命周期证据。
- `codeql/lib/SessionState.qll`
  - 修改 `WebClientStateWrite`，用 `WebRetentionSink` 替代裸 `WebContainerWrite` 作为 Phase 3 主候选。
  - 扩展 `containerKind`，不再把未知 `WebContainerWrite` 默认标为 `static_container`。
- 建议新增 `codeql/lib/RetentionSinks.qll`
  - 专门承载 `WebRetentionSink` 家族、sink shape、growth driver 和 receiver proof。
- `codeql/lib/CommonDoS.qll`
  - 增加 `sink_shape`、`growth_dimension`、proof 字段抽象。
- `codeql/queries/phase3_candidate_features.ql`
  - 增加 proof-carrying sink schema 输出列。
- `results/phase4/verified_vulnerabilities.json`
  - 作为已验证真阳驱动的设计回归依据。

### 已验证漏洞覆盖目标

- `WEB-REAL-0001`：`DefaultOAuth1Provider.requestTokenByTokenString.put`，`proof_source=static_field/drd`，`growth_driver=OAuth request token`。
- `WEB-REAL-0003`：`LearningPushHandler.cache -> inner map put`，`sink_shape=nested_retained_map_put`，生命周期根为 handler field。
- `WEB-REAL-0004`：`MCMPHandler.container -> ModClusterContainer.nodes/balancers/hosts`，`sink_shape=registry_retention`，避免把 `HeaderMap.add` 当作主 sink。
- `WEB-REAL-0005`：`ProxyServlet._client -> HttpClient.destinations.compute`，`proof_source=servlet_field/framework_lifecycle`，生命周期根为 managed `HttpClient`。

### Known-Vuln Sink/Proof 对照表

| ID | 期望 sink | receiver proof | growth driver | 必须降级的噪声 |
| --- | --- | --- | --- | --- |
| `WEB-REAL-0001` | `requestTokenByTokenString.put(token, requestToken)` | `static_field:DefaultOAuth1Provider.requestTokenByTokenString` | token / request token object | provider helper 内局部 map |
| `WEB-REAL-0002` | `bodyParts.add(part)` 或 MIME part accumulator | `parser_lifetime:MultiPart/MIMEMessage transaction` | part count / part metadata / body stream | 临时 header copy、builder-local list |
| `WEB-REAL-0003` | `cache.get(referer).put(path, ...)` | `handler_field:LearningPushHandler.cache` | referer + path nested key | Undertow request/response `HeaderMap.add` |
| `WEB-REAL-0004` | `nodes/balancers/hosts` registry update | `handler_field:MCMPHandler.container -> ModClusterContainer` | node/balancer/host id | MCMP response header writes |
| `WEB-REAL-0005` | `HttpClient.destinations.compute(origin, ...)` | `servlet_field:ProxyServlet._client -> HttpClient.destinations` | origin/tag/host | per-request proxy header map |

第一阶段硬性目标是覆盖 `WEB-REAL-0001/0003/0004/0005`。`WEB-REAL-0002` 属于 parser/body 查询族，若第一阶段只实现 parser lifetime stub，可先输出为 `needs_flow`，第二部分再补完整 source/body flow。

### 风险与约束

- Buildless CodeQL 数据库可能缺少完整继承关系，因此 receiver proof 不能依赖单一路径上的 `getASupertype*()`；需要名称、字段声明、getter body 和局部 AST 证据共同兜底。
- Getter proof 容易过召回，第一阶段只允许 getter 返回 retained field 或 retained field 的直接子对象；不做无限调用链。
- Dr.D long-life class 只能提高 proof confidence，不能单独把类内所有 collection mutation 变成 confirmed sink。
- Parser transaction 的 lifetime 不是 process lifetime，但在单请求 body 处理期间也可形成内存/磁盘耗尽；必须用独立 `parser_lifetime` 标签，避免污染普通 retained-state 排序。
- Debug 输出可能显著增加结果体积，应按框架和 query 分文件输出，不覆盖现有 Phase 3 权威 CSV。

### 交付产物

- 新增或扩展 CodeQL retention sink library。
- 新版 Phase 3 proof-carrying sink schema。
- 面向 5 个 `WEB-REAL-*` 的 sink/proof 对照表。
- 设计说明需同步进入 `results/phase3_report.md` 或独立报告，供论文方法章节引用。

### 验收条件

- 每个 high-risk sink 都是具体 `MethodCall`。
- 每个 high-risk sink 都有 `receiver_proof`。
- 每个 high-risk sink 都有 `growth_driver`，可直接作为后续 taint analysis 的 sink 端。
- `HeaderMap`、request-local collection 和未写回 retained object 的局部集合不再进入 P0/P1。
- Dr.D long-life class 结果可以作为 `proof_source` 接入，但不会绕过 receiver proof。

## 第二部分：Entry / Data Flow / Parser 工程化支撑

优先级: 第二阶段。

对应原始任务: P1、P3、P4。

论文定位: 这是第一部分 long-lived object 证明的工程基础，用于提升覆盖面和召回，但创新点应服务于第一部分，不单独作为主要贡献包装。

### 目标

- 补齐 Jakarta、Servlet filter、JAX-RS provider、Jetty proxy、Undertow parser 等真实 entry。
- 从 direct / one-hop helper 扩展到 bounded multi-hop data flow。
- 将 body/parser 型 DoS 作为独立查询族，而不是硬塞进 map retention。

### Brainstorming 结论

第一部分实现后，Phase 3 已从裸 sink 扫描收敛为 25 条 proof-carrying 候选，`unknown_container=0`，`HeaderMap/getResponseHeaders` 不再进入主候选。剩余缺口不是 receiver proof，而是 request flow 无法跨越框架边界：

1. Jersey OAuth1：JAX-RS resource 调用 `OAuth1Provider` interface，真实 retained sink 在 `DefaultOAuth1Provider` implementation 的 static map。
2. Jersey multipart：entry 是 `MessageBodyReader.readFrom` / multipart reader，sink 是 parser transaction 内部 part accumulator，不应依赖普通 HTTP handler entry。
3. Jetty ProxyServlet：Servlet entry 经过 `newProxyRequest/send` 进入 managed `HttpClient.resolveDestination`，request-derived `Origin.tag/host` 驱动 `destinations.compute`。
4. Undertow LearningPush：HTTP handler 注册 exchange completion listener，真实 nested map 写入发生在 callback `exchangeEvent`。
5. Undertow MCMP：`MCMPHandler.handleRequest` 派发到 action-specific helper，registry mutation 发生在 `processConfig` / container helper 调用中。

因此第二部分的核心不是增加更多 sink 名称，而是补齐 `request entry -> bounded call path -> proof-carrying sink` 的工程桥接，并把 parser/body DoS 作为独立候选流合并回 Phase 3。

第二部分的实现应采用“多条窄桥接规则”而不是一次引入通用全程序 taint：

- 对已验证真阳先建立 framework-specific bridge，保证真实路径能进入候选。
- 对每条 bridge 输出 `request_flow_proof` 和 `call_path`，避免 Phase 4 无法解释为什么 request data 可到达 sink。
- 对 parser/body 单独输出 parser-specific evidence，避免重新引入 HeaderMap/response header 噪声。

### Baseline 缺口

当前第一部分完成后的结果基线：

| Framework | Phase 3 rows | 当前状态 | 第二部分目标 |
| --- | ---: | --- | --- |
| Tomcat | 20 | proof sink 可用，多为 servlet/session/context | 保持兼容，补 Jakarta/filter/service 覆盖 |
| Spring Boot | 2 | proof sink 可用，覆盖有限 | 保持兼容，补 controller/helper 多跳 |
| Jetty | 0 | source/proxy/client flow 未桥接 | 覆盖 `ProxyServlet -> HttpClient.destinations.compute` |
| Undertow | 3 | handler direct proof sink 可用 | 覆盖 LearningPush listener 与 MCMP helper/registry |
| Jersey | 0 | provider/parser flow 未桥接 | 覆盖 OAuth1 provider 与 multipart reader |

当前推进状态（2026-06-19 21:40）：第二部分已经通过多条 auxiliary bridge 覆盖 5 个 `WEB-REAL-*` 静态路径。全量 Phase 3 为 37 条候选，其中 Jetty 由 `phase3_jetty_proxy_candidate_features.ql` 输出 1 条 `candidate_family=client_destination` 候选，命中 `WEB-REAL-0005`。通用 `RequestFlow.qll` 仍只覆盖 direct / one-hop；Jersey OAuth、Jersey parser、Undertow listener/MCMP 和 Jetty proxy 跨组件路径暂由窄 bridge 承担，后续可再上沉为通用 bounded flow。

### 设计任务

1. Entry discovery 扩展。
   - Servlet 同时支持 `javax.servlet` 和 `jakarta.servlet`。
   - 增加 `Filter.doFilter`、Servlet `service` 的 Jakarta 版本。
   - 增加 JAX-RS resource、provider、`MessageBodyReader.readFrom`、container filter。
   - 增加 Jetty `ProxyServlet`、`AbstractProxyServlet`、handler chain。
   - 增加 Undertow `HttpHandler`、`parseFormData`、`loadParts`、`FormDataParser.parseBlocking/doParse`。

2. Request data flow 扩展。
   - 支持 bounded multi-hop call path。
   - 支持 interface dispatch / override 的保守匹配。
   - 支持 injected field 到 provider implementation 的近似解析。
   - 支持 request-derived object：`Origin`、`Request.tag()`、OAuth parameters、multipart part metadata。

3. Parser/body 查询族。
   - 单独新增 parser retention 查询，覆盖 multipart/form-urlencoded/XML/MIME。
   - 建模 request body stream、part count、headers per part、deferred parsing API。
   - 输出 parser-specific evidence：loop source、part accumulator、body source、bound check。

4. Sink 形态补齐。
   - 增加 `Map.compute`、`merge`、`replace`、factory/register methods。
   - 识别 container getter 后写入，例如 `getBodyParts().add()`、`getHeaders().add()`，再由第一部分决定是否 long-lived 或 parser-retained。

5. 新增 request-flow proof 层。
   - 输出 `request_flow_kind`、`request_flow_proof`、`call_path`、`entry_data_expr`、`sink_driver_expr`。
   - `request_flow_kind` 可取 `direct`、`one_hop_helper`、`bounded_call_path`、`interface_dispatch`、`provider_field`、`listener_callback`、`parser_body_flow`、`client_request_flow`。
   - `call_path` 采用稳定字符串格式：`Entry.method -> helper1 -> helper2 -> Sink.method`，深度第一版限制为 4。
   - 主候选需要同时满足第一部分的 `receiver_proof` 和第二部分的 `request_flow_proof`；暂时缺 flow 但有 receiver proof 的 retained sink 保留为 `needs_flow` debug。

6. 建立 framework bridge，而不是无界全程序 taint。
   - Jersey OAuth bridge：`@Context` / injected `OAuth1Provider` field 或 constructor parameter 近似到 `DefaultOAuth1Provider` implementation。
   - Jersey multipart bridge：`MessageBodyReader.readFrom(InputStream, ...) -> MIMEMessage.getAttachments -> bodyParts.add`。
   - Jetty proxy bridge：`ProxyServlet.service -> newProxyRequest -> send -> HttpClient.resolveDestination -> destinations.compute`。
   - Undertow listener bridge：`exchange.addExchangeCompleteListener(new Listener(... request data ...)) -> Listener.exchangeEvent -> nested retained map put`。
   - Undertow MCMP bridge：`handleRequest -> processConfig/processCommand -> container.addNode/enableContext`。

7. Parser/body 查询族独立输出。
   - 新增 parser candidate schema：`parser_entry`、`body_source`、`parser_loop`、`part_accumulator`、`part_count_driver`、`header_count_driver`、`temp_file_driver`、`bound_check`。
   - Parser sink 的 `lifecycle_root` 使用 `parser_transaction` 或 `parser_temp_storage`，不伪装成 process lifetime。
   - HeaderMap/response header mutation 默认排除；只有 MIME part/header accumulator 且由 request body loop 驱动时才输出 parser 候选。

8. 负样例和降级规则。
   - `getResponseHeaders().add/put`、request header copy、proxy header forwarding、builder-local collection 仍必须降级。
   - `LRUCache`、bounded path cache、configured max entries 的候选输出 `capacity_hint=bounded_or_evicted`，避免 Phase 4 误排 P0。
   - 测试、examples、smoke path 进入 debug 或低优先级，不作为论文主漏洞候选。

### 建议接口

建议新增 `codeql/lib/RequestFlow.qll`，只负责证明 request data 能到达 proof-carrying sink，不负责判断 receiver 生命周期。同时引入 `RequestCarrier`，覆盖无显式 request 参数但有注入上下文的框架入口。

```ql
abstract class RequestCarrier extends TTop {
  abstract HttpEntryPoint getEntry();
  abstract Expr getCarrierExpr();
  abstract string getCarrierKind();
  abstract string getSourceKind();
  abstract string getEvidence();
}
```

`RequestCarrier` 第一版覆盖：

- `param`：`HttpServletRequest`、`HttpServerExchange`、Jetty `Request`、JAX-RS `ContainerRequestContext`、`InputStream`。
- `injected_context_field`：Jersey resource/provider 中的 `@Context`、`@Inject` 字段，例如 `ContainerRequestContext`、`UriInfo`、`HttpHeaders`。
- `derived_request_object`：`OAuthServerRequest`、`OAuth1Parameters`、Jetty `Request`、`Origin`、Undertow `NodeConfig`。
- `parser_stream`：`MessageBodyReader.readFrom` 的 `InputStream`、boundary、multipart metadata。

```ql
abstract class WebRequestFlowPath extends TTop {
  abstract HttpEntryPoint getEntry();
  abstract WebRetentionSink getSink();
  abstract Expr getEntryDataExpr();
  abstract Expr getSinkDriverExpr();
  abstract string getFlowKind();
  abstract string getCallPath();
  abstract string getFlowProof();
  abstract string getConfidence();
}
```

第一版实现顺序：

- `DirectOrOneHopFlowPath`：迁移现有 `writeInEntryOrOneHop`，保持 Phase 3 兼容。
- `BoundedCallPathFlow`：entry 调用 helper，helper 再调用 helper，深度限制 3-4；只在同类型、同 package、或已知 framework bridge 内展开。
- `InterfaceDispatchFlow`：call target 是 interface method 时，按方法名、参数数量、实现类型包名匹配 implementation。
- `ProviderFieldFlow`：entry/resource 中的 provider field 调用到 provider implementation。
- `ListenerCallbackFlow`：entry 内创建 listener，构造参数/捕获字段来自 request，listener callback 内写入 `WebRetentionSink`。
- `ClientRequestFlow`：request-derived host/path/tag/origin 进入 client request object，再进入 `resolveDestination` / destination map。

Phase 3 统一输出建议追加：

```text
candidate_family
call_path
call_path_depth
request_flow_proof
request_carrier_kind
source_kind
source_expr
deployment_condition
capacity_hint
```

其中 `candidate_family` 可取 `retained_state`、`parser_body`、`debug_rejected`；`deployment_condition` 用于 MCMP management endpoint、ProxyServlet deployment、multipart provider enabled 这类动态验证前置条件。

### Parser 查询 Schema

Parser/body 查询不直接复用普通 Phase 3 query 的 entry 约束，输出后由 `scripts/run_phase3.py` 合并。

```text
framework
parser_entry_fqn
parser_entry_file
parser_entry_line
body_source_kind
body_source_expr
parser_loop
part_accumulator
sink_file
sink_line
sink_shape
growth_dimension
growth_driver_expr
receiver_proof
proof_source
proof_confidence
request_flow_kind
request_flow_proof
bound_check
axis_r
axis_v
axis_m
axis_c
axis_l
verdict
```

合并到 `phase3_candidate_features.csv` 时，parser-specific 字段进入 `debug_notes` 或扩展字段，核心字段仍填充 `sink_id`、`sink_shape`、`growth_dimension`、`receiver_proof`、`request_flow_kind`。

### 第二阶段实现顺序

1. 扩展 `WebSources.qll` 和 `phase2_source_discovery.ql`：Jakarta Servlet、Filter、JAX-RS provider、MessageBodyReader、Jetty ProxyServlet、Undertow parser/form handlers。
2. 新增 `RequestFlow.qll`：先迁移 direct/one-hop，再实现 bounded call path 和 interface dispatch。
3. 将 `SessionState.qll` 的 `writeInEntryOrOneHop` 替换为 `WebRequestFlowPath`，Phase 3 输出 `request_flow_proof` 与 `call_path`。
4. 新增 `ParserRetention.qll` 和 `phase3_parser_candidate_features.ql`，只处理 body/parser 类候选。
5. 修改 `scripts/run_phase3.py`，支持 retained-state query 与 parser query 合并，输出统一 schema。
6. 为 `WEB-REAL-0001/0002/0003/0004/0005` 建立 coverage smoke 查询或脚本，先报告命中/缺失，不在本阶段做完整 regression gate。
7. 重跑 Phase 2/3/4，确认 Jetty/Jersey 不再为空，且 HeaderMap/response header 噪声不回流到 P0/P1。

### WEB-REAL 覆盖路径

| ID | 第二部分必须补齐的桥接 | 关键输出 |
| --- | --- | --- |
| `WEB-REAL-0001` | JAX-RS 无参 entry + injected `requestContext` + `OAuth1Provider` interface dispatch 到 `DefaultOAuth1Provider` | `request_flow_kind=provider_field/interface_dispatch`，`call_path=RequestTokenResource.postReqTokenRequest -> DefaultOAuth1Provider.newRequestToken -> requestTokenByTokenString.put` |
| `WEB-REAL-0002` | `MessageBodyReader.readFrom` body stream 到 MIME multipart parser accumulator | `candidate_family=parser_body`，`growth_dimension=part_count/header_count/byte_volume` |
| `WEB-REAL-0003` | `LearningPushHandler.handleRequest` 到 completion listener `exchangeEvent`，referer/path 到 nested map | `request_flow_kind=listener_callback`，`growth_dimension=outer_referer_cardinality + inner_path_cardinality` |
| `WEB-REAL-0004` | MCMP command/form parser 到 `ModClusterContainer` registry mutation | `deployment_condition=management_endpoint_exposed`，`sink_shape=registry_register` |
| `WEB-REAL-0005` | `ProxyServlet.service` 到 `HttpClient.resolveDestination` / `destinations.compute` | `request_flow_kind=client_request_flow`，`growth_driver_kind=origin_key`，`growth_dimension=destination_count` |

### 噪声守护

第二部分扩展 source/data-flow 时必须保留第一部分的降噪边界：

- `HeaderMap.add/put`、`getResponseHeaders()`、proxy request/response header forwarding 不进入 P0/P1。
- `builder-local`、`temporary parser-local object`、test/example/smoke path 进入 `debug_rejected` 或低优先级。
- Bounded/LRU cache 输出 `capacity_hint=bounded_or_evicted`，由第三部分再做正式 capacity proof。
- 多实现 interface dispatch 输出多条 `needs_flow` 或 `confidence=medium`，不强行合并成单一真阳。

### 相关文件

- `codeql/lib/WebSources.qll`
  - 扩展 Jakarta Servlet、Filter、JAX-RS provider、MessageBodyReader、container-specific handlers。
- 建议新增 `codeql/lib/RequestFlow.qll`
  - 承载 `RequestCarrier`、bounded call path、interface dispatch、provider field、listener callback 和 client request flow。
- `codeql/lib/SessionState.qll`
  - 从 `writeInEntryOrOneHop` 迁移为消费 `WebRequestFlowPath`。
- `codeql/lib/RetentionSinks.qll`
  - 配合第二部分补充 `origin_key`、nested double-cardinality、registry-specific growth driver 等 sink driver 标注。
- `codeql/queries/phase2_source_discovery.ql`
  - 与 `WebSources.qll` 保持 source discovery 一致。
- `codeql/queries/phase3_candidate_features.ql`
  - 消费新的 entry/data-flow/proof 字段，输出 call path 和 request flow proof。
- 建议新增 `codeql/lib/ParserRetention.qll`
  - 独立承载 parser/body 型 DoS 模型。
- 建议新增 `codeql/queries/phase3_parser_candidate_features.ql`
  - 输出 parser/body 候选。
- 新增 `codeql/lib/JettyRetention.qll`
  - 建模 `ProxyServlet.service -> newProxyRequest/sendProxyRequest -> HttpClient.destinations.compute`。
- 新增 `codeql/queries/phase3_jetty_proxy_candidate_features.ql`
  - 输出 `candidate_family=client_destination` 的 Jetty ProxyServlet / HttpClient destination map 候选。
- `scripts/run_phase3.py`
  - 支持合并 retained-state、parser/body 和 debug rejected 查询结果。
- 新增 `scripts/check_web_real_coverage.py`
  - 检查 5 个 `WEB-REAL-*` 的 expected entry/sink/proof/flow 是否命中。

### 已验证漏洞覆盖目标

- `WEB-REAL-0001`：`RequestTokenResource.postReqTokenRequest -> provider.newRequestToken -> DefaultOAuth1Provider.put`。
- `WEB-REAL-0002`：`MultiPartReaderClientSide.readFrom/getMimeParts -> MIMEMessage.getAttachments -> MultiPart.bodyParts.add`。
- `WEB-REAL-0003`：`LearningPushHandler.handleRequest -> addExchangeCompleteListener -> PushCompletionListener.exchangeEvent -> pushes.put`。
- `WEB-REAL-0004`：`MCMPHandler.handleRequest -> processConfig/processCommand -> ModClusterContainer registry mutation`。
- `WEB-REAL-0005`：`ProxyServlet.service -> newProxyRequest/send -> HttpClient.resolveDestination -> destinations.compute`。

### 交付产物

- Phase 2/3 source coverage 报告中 Jetty/Jersey 不再为空候选。
- 新增 parser/body 查询结果。
- 每条候选输出 call path，便于人工复核和后续生成 validation recipe。
- Phase 3 输出 `candidate_family`、`request_carrier_kind`、`request_flow_proof`、`call_path`、`deployment_condition`。
- `WEB-REAL-*` coverage smoke 报告，说明每个已验证漏洞是 `hit` 还是 `missing`。

### 验收条件

- `WEB-REAL-0001`、`WEB-REAL-0002`、`WEB-REAL-0003`、`WEB-REAL-0004`、`WEB-REAL-0005` 至少达到 `partial`，其中 Jetty/Jersey 不再因 source/flow 缺失为 0 候选。
- Parser/body 候选进入独立 `candidate_family=parser_body`，不依赖普通 `Map/List` retention sink。
- 每条主候选同时有第一部分的 `receiver_proof` 和第二部分的 `request_flow_proof`。
- Phase 4 top 队列中不重新出现 response header / `HeaderMap` 噪声作为 P0/P1。
- Phase 3 consistency、Phase 4 analyze、AOSP monotonicity 和 AOSP regression 全部通过。

当前实现状态：`python3 scripts/check_web_real_coverage.py` 已确认 `WEB-REAL-0001` 至 `WEB-REAL-0005` 全部为 `hit`；后续第三部分仍需把这些 smoke checks 升级为正式 regression manifest。

## 第三部分：回归基准、Capacity/Lifespan 证明与排序

优先级: 最后阶段。

对应原始任务: P0、P5、P6。

论文定位: 继承 Dr.D 的 evaluation discipline，用于保证方法有效性、可复现性和人工复核效率。该阶段依赖第一、第二部分产出的正确候选和证明项。

### 目标

- 将已验证漏洞和 Dr.D 关键案例变成回归集。
- 让 `C/L/verdict` 基于证明项，而不是基于同方法名字启发式。
- Phase 4 排序只在正确候选集合上做优先级，而不再承担修正基础建模错误的责任。

### 设计任务

1. Dr.D 兼容回归集。
   - 建立 manifest，记录目标框架、版本、入口、retained field、预期 sink、预期 proof。
   - 首批覆盖本仓库 5 个 `WEB-REAL-*`。
   - 后续加入 Dr.D 表中 Tomcat、Jetty、Undertow、Resin 的关键方法。

2. Capacity proof。
   - `C=Unbounded` 需要证明没有 hard cap，且不是 LRU/cacheSize/queue max/parameter count 保护。
   - 支持 nested container：outer bounded 不等于整体 bounded。
   - 区分 per-element size check 与 total element count bound。

3. Lifespan proof。
   - `L=ProcessLifetime` 需要 lifecycle root。
   - `L=RebootPersistent` 需要文件/DB/Redis/session persistence 证据。
   - `Evicted` 需要可达清理路径，而不是只看同方法是否出现 cleanup 名字。

4. Phase 4 重新排序。
   - 输入字段增加 `database_id`、`lifecycle_root`、`retained_field`、`receiver_proof`、`request_flow_proof`、`capacity_proof`。
   - 无 long-lived proof 的候选默认不进入 P0/P1。
   - 测试、示例、docs、smoke test 默认从论文候选集中剔除，仅保留 debug 输出。

5. Validation recipe 生成。
   - 每条 high-risk 候选输出部署条件、handler/filter/feature 启用方式、触发 HTTP 请求、观测 retained object size 的方式、预期增长 key/value。

### 相关文件

- 建议新增 `intel/regression/web_real_manifest.json`
  - 记录本仓库已验证漏洞的静态回归预期。
- 建议新增 `intel/regression/drd_compat_manifest.json`
  - 记录 Dr.D 兼容案例。
- `scripts/check_phase3_consistency.py`
  - 扩展为校验 proof schema 和 known-vuln coverage。
- `scripts/run_phase4.py`
  - 重写排序，消费 proof 字段。
- `results/phase4/ranked_candidates.csv`
  - 新 schema 输出。
- `results/phase4/review_queue_top50.md`
  - 增加 validation recipe。
- `results/phase4/evaluation_summary.json`
  - 增加 known-vuln recall、proof coverage、noise rate。

### 交付产物

- 回归 manifest。
- Known-vuln recall 报告。
- Proof-aware Phase 4 排序产物。
- high-risk validation recipe 队列。

## 实施顺序

1. 第一部分先完成 long-lived object proof，至少让 `WEB-REAL-0001`、`WEB-REAL-0003`、`WEB-REAL-0004`、`WEB-REAL-0005` 能对应到正确 retained field。
2. 第二部分再补 entry/data-flow/parser，使 Jersey multipart 和跨组件 Jetty/Jersey 路径进入候选。
3. 第三部分最后重做回归和排序，避免在错误候选集合上过早优化分数。

## 非目标

- 不在第一阶段优先调整 Phase 4 权重。
- 不用更多 sink 名称替代 long-lived proof。
- 不把 Spring smoke test / examples 作为论文漏洞候选。
- 不修改 AOSP 侧 `../dos-analysis/` 的 verdict 语义。
