# 基于生命周期的 Java Web 资源耗尽漏洞检测

## 1. 技术路线

codeql + LLM + CFG

## 2. 威胁模型

攻击者是远程或低信任主体，能够在接口允许的范围内：

- 重复调用 HTTP、WebSocket、MQTT、RPC、消息处理器或其他外部入口；
- 控制请求参数、body、header、路径、协议字段或消息内容；
- 创建不同的 key、topic、session、connection、job 或业务标识；
- 保持连接，延迟 ACK、轮询、断连、重连或其他终止操作；
- 并发发起多个合法或半合法请求。

研究覆盖 heap、direct memory、容器状态、pending protocol state、异步任务、线程、连接和其他可以从 Java 代码中识别增长与释放关系的资源。

纯 CPU 算法复杂度、死循环和栈耗尽不属于第一版核心范围，除非它们直接造成 R 的执行能力受限。

## 3. 完整生命周期建模

现有资源耗尽漏洞检测通常从危险 API 或资源增长操作出发，例如大对象分配、容器插入、任务提交和连接创建。这种方法能够找到大量候选，却难以回答候选是否真的能够造成资源耗尽。

本项目的动态验证集合已经说明了这一问题：静态分析能够发现许多外部输入可达的增长操作，但只有部分案例在受控实验中触发了 OOM、线程耗尽或服务失效。其余案例混合了真实限制机制、有限实验造成的右删失、环境阻断、路由或权限问题，以及存在增长但尚未达到故障阈值的情况。因此，静态发现增长点和有限实验未复现都不能独立决定漏洞是否成立。

真正决定资源是否持续扩大的因素位于一次资源增长请求的完整生命周期中：

```text
E    →    [Guard]   →    G(P)  →    [R(P)]
                     └─[Bound]─┘
```

其中：

- `E` 是携带攻击者 payload 到达系统的外部入口；
- `G` 是受 E 输入控制的资源增长操作；
- `P` 是被 G 增长的资源点；
- `Guard` 是 G 前的权限、输入上界、表示大小、频率或并发检查；
- `Bound` 是 P 自身的容量、数量、字节数、连接数或并发上界；
- `R` 是后续同步或异步执行中对 P 产生释放效果的操作。

本文的核心目标是恢复 `E–G(P)–R(P)` 的完整生命周期，并判断 Guard、Bound 和 R 是否真正限制了攻击者控制的资源增长。


## 4. 核心漏洞断言

漏洞类型又生命周期建模自然推导得出。

### 4.1 断言一：无有效 Guard 和 Bound 的直接增长

```text
E controls G ∧ not Guard ∧ not Bound
```

`E controls G` 表示攻击者输入能够控制增长大小、展开规模、分配参数、创建次数或并发数量。该前件排除固定小分配。

`not Guard` 包括：

- 没有 Guard；
- Guard 没有覆盖通向 G 的路径；
- Guard 位于 G 之后；
- Guard 只记录或告警而不拒绝；
- Guard 检查错误的表示维度，例如 compressed bytes 而 G 消耗 decoded bytes；
- Guard 的配置默认关闭、无穷大或不可解析；
- Guard 可通过另一入口或 wrapper 顺序绕过。

`not Bound` 包括：

- P 没有容量或预算；
- Bound 约束的不是同一资源点；
- Bound 约束错误的资源维度；
- Bound 只限制单项，而 E 可以控制单项本身超过预算；
- Bound 在并发执行中不成立；
- 配置值可能已经超过实际资源预算。

本断言中 R 不影响结果。即使请求结束后存在 `close()` 或对象最终可由 GC 回收，资源也可能在执行到 R 前耗尽。

### 4.2 断言二：无有效 Bound 且无 Release 的持续增长

```text
E controls G
∧ not Bound
∧ not Release
```

该断言主要覆盖只增不减的跨生命周期资源点，例如：

- process-global map 或 registry；
- 只注册不注销的 listener/subscription；
- 没有 eviction/cleanup 的 cache；
- 没有消费路径的 pending state；
- attacker-controlled key 持续形成新 entry。

`not Release` 不是指附近没有任何 `remove` 或 `close`，而是分析在同一 P 的同步和异步生命周期中没有发现能够降低该增长的 R。若只找到 may-alias、key 不匹配、未注册 callback 或不可达 cleanup，则记录为“未验证 Release”，不能作为有效反证。

### 4.3 断言三：无有效 Bound，Release 存在但受到限制

```text
E controls repeatable G
∧ not Bound
∧ Release is constrained
```

该断言不依赖 G 的具体类型。只要 E 能够重复触发 G，P 没有有效 Bound，且 R 虽然真实影响 P 却不能充分抵消增长，就形成候选。


## 5. Guard、Bound 和 Release 的有效性

三条断言的准确性取决于能否判断限制机制是否有效。

### 5.1 有效 Guard

有效 Guard 至少满足：

1. 位于 G 前并控制通向 G 的路径；
2. 超限或未授权分支不能继续到达 G；
3. 检查与 G 相同的输入表示或资源维度；
4. 使用有限、默认生效的配置；
5. 覆盖该 E 到 G 的所有相关入口和 wrapper 顺序。

权限 Guard 只有在默认攻击者无法满足权限条件时才有效。需要默认凭据、匿名协议或低权限账号即可通过的检查不能自动排除候选。

### 5.2 有效 Bound

有效 Bound 至少满足：

1. 直接作用于 P 或 G 实际写入的 receiver；
2. 限制正确的资源维度，如 entry count、retained bytes、queue items、connections 或 threads；
3. 满载后真正阻止增长，例如 reject、block 或 atomic eviction；
4. 调用者没有忽略 `offer=false`、rejection 或 quota failure；
5. 覆盖所有 producer；
6. 限制范围与攻击者可创建的资源范围一致。

例如，每连接 65,535 个 packet ID 是局部 Bound，但如果连接数量没有全局上界，它不能形成进程级 Bound。单消息大小限制也不能替代 retained-state 总字节预算。

工具内部可将 Bound 记录为：

```text
absent
present_but_scope_mismatched
present_but_dimension_mismatched
present_but_possibly_over_budget
effective
unknown
```

论文顶层仍统一称为有效或无效 Bound。

### 5.3 R 是否影响 P

R 只有满足下列证据，才被视为真实 Release：

- 作用于 G 所增长的同一 receiver 或资源点；
- map、protocol state 或 registry 中的 key/item 能够匹配；
- R 位于 G 后的可行同步路径，或通过真实异步注册关系可达；
- callback、worker、timer、listener 或 protocol handler 已经注册；
- R 的操作语义确实降低 P，而不是仅修改状态、复制对象或移动到另一个容器。

精确 receiver/key 关系优先由静态分析确认。`may-alias` 只能产生候选 R，不足以直接证明 R 有效。

## 6. 四类资源增长操作 G

四类 G 用于候选生成、特征提取和实验分层，不作为互斥或完备的漏洞分类。一个生命周期可以同时包含多种 G。

### 6.1 G1：输入材料化

攻击者控制输入表示及其内存材料化规模，例如：

```text
request body → parse / decode / decompress → in-memory object
```

典型操作包括：

- request body aggregation；
- JSON/XML/表单反序列化；
- gzip/deflate 解压；
- Base64 或其他编码解码；
- multipart field materialization；
- 字符串、数组、集合或对象图构建。

该类主要检查 Guard 与 Bound，R 通常不参与漏洞判定，因为 OOM 可能发生在材料化完成之前。

### 6.2 G2：直接资源分配

攻击者控制分配参数或资源创建次数，例如：

```text
height → new BufferedImage(width, height)
size   → allocateDirect(size)
request → new Thread / open connection / acquire handle
```

该类不仅包括 Java heap allocation，也包括 direct buffer、线程、连接、文件描述符等资源。请求结束后的 GC eligibility 不能替代增长前的 Guard 或 P 上的 Bound。

### 6.3 G3：跨生命周期容器增长

攻击者输入被保存到请求结束后仍然存活的资源点，例如：

```text
map.put
list.add
cache.put
registry.register
session.setAttribute
pendingState.put
```

危险性取决于：

- E 是否能够重复触发 G；
- 是否能够创建不同 key 或新的资源单元；
- P 是否存在有效 Bound；
- 是否存在影响同一 P 的 R；
- R 是否受到限制。

### 6.4 G4：异步队列或任务增长

攻击者输入被提交到异步执行系统，例如：

```text
queue.add / offer
executor.submit / execute
schedule
future / callback registration
reactive pipeline submission
```

异步提交意味着资源所有权从请求线程转移到 queue、executor、worker、callback、channel 或其他长期组件。请求结束不表示资源释放。该类必须同时恢复生产路径、异步注册、消费路径和释放路径。


## 7. 工具总体架构

```text
Java application + dependencies + default configuration
                          │
                          ▼
              Stage 1: Cross-framework E recovery
                          │
                          ▼
              Stage 2: G/P candidate discovery
                CodeQL features + semantic model
                          │
                          ▼
              Stage 3: E → G connectivity proof
                   taint/data-flow/call graph
                          │
                          ▼
              Stage 4: Lifecycle reconstruction
          Guard + Bound + sync R + async R + registration
                          │
                          ▼
              Stage 5: Rule-first effectiveness analysis
                          │
              ┌───────────┴───────────┐
              │                       │
       deterministic result     unresolved slice
              │                       │
              │                       ▼
              │             Stage 6: constrained LLM
              │              semantics/efficiency judge
              └───────────┬───────────┘
                          ▼
              Stage 7: Three-assertion engine
                          │
                          ▼
         certificate + verdict + dynamic validation plan
```


## 8. Stage 1：跨架构入口 E 恢复

入口识别需要覆盖不同 Java Web 架构，而不局限于 Spring MVC。

第一版入口模型包括：

- Servlet、Filter、Spring MVC/WebFlux；
- JAX-RS/Jakarta REST；
- WebSocket；
- Netty channel handler；
- MQTT/protocol handler；
- gRPC/RPC handler；
- message listener/consumer；
- framework callback 中由外部事件触发的方法。

每个 E 需要记录：

- 注册位置和框架类型；
- URL、topic、protocol event 或 callback trigger；
- 默认认证和权限条件；
- 攻击者可控参数；
- 是否允许重复或并发触发；
- 配置和 profile 来源。

CodeQL 和框架模型负责确定注册与可达性。LLM 可以帮助识别自定义 annotation、wrapper 或非标准权限语义，但不能在没有静态证据时直接断言入口可达。

## 9. Stage 2：G/P 候选识别

### 9.1 CodeQL 特征提取

CodeQL 先以高召回提取资源增长特征：

- allocation type、constructor 和 size argument；
- parser、decoder、decompressor 和 materializer；
- collection/map/cache/registry mutation；
- queue、executor、scheduler 和 callback submission；
- receiver 类型、字段路径和创建位置；
- key/value 来源；
- 返回值、字段写入和跨方法传播；
- request-local 或 request-escaping 特征；
- 同一资源点附近和跨调用图的 capacity/configuration 信息。

### 9.2 G/P 识别器

G/P 识别可以采用两种可替换实现：

1. CodeQL 规则加 LLM 语义分类；
2. CodeQL 特征加可解释传统 ML/GNN 排序，再由 LLM 处理低置信候选。

第一版建议采用 CodeQL + LLM，因为真实应用存在大量自定义 wrapper，且当前首要目标是验证生命周期 Idea，而不是同时证明一个新的学习模型。ML/GNN 可在第二阶段用于候选排序和跨项目泛化实验。

LLM 的输入必须是 bounded slice，而不是整个仓库。输入包括：

- 候选调用及其封装方法；
- receiver/type/argument；
- E 到候选的 data-flow 摘要；
- 字段和配置引用；
- 附近 Guard/Bound/R 候选；
- 框架和调用上下文。

LLM 输出结构化候选：

```json
{
  "is_growth": true,
  "growth_type": ["container", "async_queue"],
  "resource_point": "JobThread.triggerQueue",
  "controlled_growth_feature": "one distinct trigger per attacker-controlled logId",
  "resource_dimension": "queued_items_and_retained_payload",
  "evidence_locations": []
}
```

该输出用于构建候选，不直接决定最终漏洞结论。

## 10. Stage 3：E 到 G 的连通性与控制关系

CodeQL 污点分析和 interprocedural data flow 负责证明：

```text
E payload → G argument / key / size / submission / owner creation
```

需要识别的控制关系包括：

- 参数直接控制 allocation size；
- payload 控制 parser/decompressor 输入；
- payload 控制 map key，使 overwrite 变为新增 entry；
- payload 控制 value cost；
- payload 控制循环次数或 fan-out 数量；
- 一次 E 固定增长一次，但 E 本身可重复调用；
- payload 控制新 session、topic、job、connection 或 owner 创建。

对 G1/G2，重点判断 E 是否控制单次增长规模或并发增长。

对 G3/G4，重点判断 E 是否能够重复执行 G，以及重复执行是否产生新资源，而不是覆盖同一个固定 key。

若 E–G 连通性只能由 LLM 猜测、反射或未解析框架关系支持，则输出 unknown，不形成高置信断言。

## 11. Stage 4：完整生命周期重建

### 11.1 生命周期内同步分析

CFG 和 call graph 提取：

- G 前的 Guard；
- G 后的 remove、close、release、complete、cancel、poll、take、evict；
- normal、exception、cancel、disconnect 和 timeout 路径；
- Guard 是否支配 G；
- R 是否位于 G 后且真实可达；
- 多分支下 G 与 R 的数量和覆盖关系。

### 11.2 跨请求与字段生命周期

工具沿 field flow 和 receiver flow 识别 P 是否存活于：

- static/singleton field；
- session/connection/channel；
- cache/map/registry；
- queue/executor；
- framework-managed bean；
- protocol state；
- native resource wrapper。

### 11.3 异步生命周期

异步函数不能只依赖普通调用图，需要建立 registration edge：

```text
submit/register/schedule
        → runtime trigger
        → callback/worker/handler
        → R(P)
```

第一版显式支持：

- `Executor.execute/submit`；
- `Thread.start`；
- `ScheduledExecutorService.schedule*`；
- `Timer.schedule*`；
- Spring `@Scheduled`、`TaskScheduler`；
- `CompletableFuture.whenComplete/handle`；
- Netty future/listener/close callback；
- Reactor `doFinally/timeout`；
- cache expiration；
- 已建模的 protocol handler registry。

仅发现 `cleanup()` 方法定义不能建立异步 R。必须发现 registration、trigger 和 handler 之间的连接。

异步提交本身不是 Release。dequeue 也不一定完成资源释放：任务可能在执行中继续占有 payload，或产生新的 downstream task/state。因此工具应跟踪 R 最终影响的 P，而不是把 queue.poll 机械当作所有资源的释放。

## 12. Stage 5：静态规则优先的 R 判断

静态规则先处理可以从程序结构中明确判断的情况。

### 12.1 R 缺失规则

```text
no same-P synchronous R
∧ no registered same-P asynchronous R
→ Release absent
```

### 12.2 客户端触发受限规则

```text
R only appears in ACK/PUBREL/poll/reconnect/client-close handler
∧ no server timeout/capacity fallback
→ Release trigger constrained
```

### 12.3 异步处理能力受限规则

```text
unbounded P
∧ repeatable producer
∧ finite/single consumer
∧ R occurs only after consumer progress
→ Release capacity constrained
```

若没有足够证据判断 producer 是否能够支配 consumer，则保留为 unresolved，而不是直接宣称漏洞。

### 12.4 阻塞 R 规则

```text
R occurs after attacker-dependent blocking call
∧ no finite server deadline
→ Release execution constrained
```

建模调用包括 `Future.get`、`join`、`await`、socket/stream read、外部 callback 和协议 ACK wait。

### 12.5 时间窗口规则

```text
registered timeout/cleanup R
∧ finite TTL/period
∧ no aggregate Bound on P
→ Release time-window constrained
```

若 E 能重写 R 使用的 timestamp/deadline 且没有 absolute deadline，则进一步标记 renewable timeout。

### 12.6 覆盖范围规则

```text
G affects paths/items not covered by R
∨ G multiplicity structurally exceeds R multiplicity
∨ terminal paths lack R
→ Release coverage constrained
```

### 12.7 Bound 反证规则

若发现同一 P 上的有限容量，并确认满载行为可靠阻止 G，则断言二和断言三不成立：

```text
finite Bound on P
∧ enforced reject/block/evict
∧ all producers covered
→ growth bounded structurally
```

容量是否低于实际资源预算可以作为后续配置和动态验证问题，但不能再称为“无界增长”。

## 13. Stage 6：受约束的 LLM 语义与效率判断

静态规则不能覆盖所有真实业务语义。LLM 只处理 Stage 5 留下的 unresolved slice。

### 13.1 LLM 可以判断的问题

- 自定义方法是否真正减少 P；
- wrapper 内部操作是 Release、状态转移还是复制；
- R 是否需要特定业务前置状态；
- 一次 G 与一次 R 大致对应一对一、一对多还是多对一；
- R 是否只释放上游对象而把 payload 转移到下游；
- custom worker 的处理能力是否明显受攻击者输入控制；
- 非标准异步框架中的 callback 是否承担释放作用；
- R 的限制属于触发、执行能力、时间窗口还是覆盖范围。

### 13.2 LLM 输入约束

输入仅包括与一个 `Lifecycle(E,P)` 相关的 bounded slice：

- E、G、P 和候选 R；
- CodeQL data-flow path；
- CFG 摘要；
- receiver/key/field facts；
- registration facts；
- producer/consumer 数量特征；
- blocking/configuration facts；
- unresolved question。

LLM 不重新搜索整个代码库，也不忽略 CodeQL 已确定的事实。

### 13.3 LLM 结构化输出

```json
{
  "release_affects_P": "yes|no|unknown",
  "release_constraint": "none|trigger|capacity|time_window|coverage|unknown",
  "growth_release_relation": "G>R|G≈R|G<R|unknown",
  "reason": "short explanation",
  "required_static_evidence": [],
  "confidence": "high|medium|low"
}
```

其中 `G>R` 是结构和语义层面的相对关系，不要求 LLM预测真实运行时请求率或精确吞吐量。

### 13.4 结果约束

LLM 结论分为两类：

- **可回放结论**：能映射回具体代码位置、CFG/data-flow/registration/configuration 特征，可参与断言；
- **不可回放结论**：只作为 unknown 的解释和动态验证建议，不能单独形成高置信漏洞 verdict。

这样保留 LLM 理解自定义业务逻辑的优势，同时避免让“R 是否足够快”变成没有证据的自由文本判断。

## 14. Stage 7：断言引擎与工具输出

### 14.1 断言匹配

工具依次评估：

```text
Assertion 1:
E controls G
+ ineffective Guard
+ ineffective Bound

Assertion 2:
E controls repeatable G
+ ineffective Bound
+ absent R

Assertion 3:
E controls repeatable G
+ ineffective Bound
+ R affects P
+ constrained R
```

一个生命周期可以命中多条断言。例如解压后的大对象被提交到无界队列，可以同时命中断言一和断言三。

### 14.2 内部分析状态

```text
direct_growth_candidate
release_absent_accumulation_candidate
release_constrained_accumulation_candidate
verified_guard
verified_bound
verified_unconstrained_release
rate_or_semantics_unknown
static_unknown
```

### 14.3 面向用户的结论

建议使用：

- `static_vulnerable`：至少一条断言具有完整且高置信的可回放证据；
- `bounded_under_modeled_assumptions`：有效 Guard、Bound 或 R 在明确配置和作用域假设下反驳全部适用断言；
- `static_unknown`：关键入口、资源点、异步注册、配置或 R 效率证据不足。

不要使用无条件 `static_safe`。

### 14.4 生命周期证书

每个结果输出一份机器可读和人可读证书：

```text
E and attacker-controlled payload
G type and source location
P and resource dimension
E→G path
Guard candidates and effectiveness
Bound candidates and effectiveness
R candidates, registration and affected P
R constraints
matched assertion
configuration assumptions
unresolved facts
recommended dynamic measurements
```

证书的解释围绕三条断言组织，不向使用者暴露过多内部形式化符号。

## 15. 真实案例如何被统一解释

### 15.1 Zipkin gzip 解压

```text
E: anonymous POST /api/v2/spans with gzip body
G: aggregate and decode gzip content
P: heap memory used by decoded representation
Guard: no verified decoded-size guard
Bound: no decoded representation bound
R: request data is closed after processing
```

E 控制 G，Guard 和 Bound 无效，命中断言一。R 位于增长之后，不影响候选。动态证据显示约 3.37 MiB wire payload 展开到约 1.356 GiB，并触发目标 heap OOM。

### 15.2 Erupt captcha image

```text
E: attacker-controlled height
G: new SpecCaptcha(150, height, 4)
P: BufferedImage/heap allocation
Guard: no maximum height
Bound: no effective allocation bound
R: image becomes GC-eligible after request
```

命中断言一。GC 不能阻止超大单次分配在 R 前失败。

### 15.3 DCMP static user map

```text
E: externally reachable user creation
G: static map insertion with new user ID
P: process-lifetime user map
Bound: absent
R: only explicit/manual cleanup; no lifecycle R found
```

命中断言二。动态验证中重复创建不同 ID 最终触发 OOM。

### 15.4 JMQTT QoS2 pending state

```text
E: anonymous QoS2 PUBLISH
G: qos2Receiving.put(packetId, message)
P: per-connection pending map
Bound: message size and packet-ID range are local, not process-wide byte Bound
R: PUBREL removes matching packet ID
Constraint: R depends on attacker sending PUBREL
```

R 确实影响 P，但触发受限，命中断言三。攻击者可保持连接并拒绝发送 PUBREL；多个连接还会放大局部上界。

### 15.5 Presto queued statements

```text
E: POST /v1/statement
G: queries.put(queryId, query)
P: queued statement registry
Bound: no effective aggregate state bound for tested legal statements
R: polling/completion/timeout lifecycle
Constraint: client can avoid polling; timeout creates accumulation window
```

命中断言三。动态验证中攻击者不轮询 `nextUri`，在 timeout 产生作用前积累大量 Query 状态并触发 OOM。

### 15.6 XXL-JOB trigger queue

```text
E: repeated trigger requests with unique logId
G: unbounded LinkedBlockingQueue.add
P: trigger queue and retained logId set
Bound: absent
R: worker poll and subsequent processing
Constraint: finite worker, rate-dependent drain, possible blocking job execution
```

R 存在但执行能力受限，命中断言三。存在 consumer 不能证明 queue 有界。

### 15.7 Solr multipart 反例

```text
E: multipart non-file form field
Guard: Jetty counts field bytes and rejects over 200000 bytes
G: String materialization
P: heap memory
```

Guard 在 G 前生效、检查正确表示维度，超限分支无法到达 G，因此断言一不成立。这是机制性反例，而不是仅凭“未 OOM”得出的安全结论。

### 15.8 JMQTT bounded protocol queue 反例

```text
G: protocol work enqueue
P: bounded LinkedBlockingQueue
Bound: finite capacity with rejection handling
```

只要 Bound 覆盖所有 producer 且 rejection 被执行，断言二和断言三不成立。容量是否过大属于配置预算问题，而非结构性无界增长。

## 16. 研究问题

### RQ1：生命周期分析是否提高资源漏洞判断准确性？

与只检测 G 或只证明 E→G 的 baseline 相比，完整生命周期分析能否减少由 Guard、Bound 和 R 造成的误报，同时保持对确认漏洞的召回？

### RQ2：三条断言是否能够解释不同增长机制？

三条断言能否统一覆盖输入材料化、直接分配、跨生命周期容器和异步队列，并对真实限制案例给出正确反证？

### RQ3：异步生命周期重建是否必要？

加入 worker、timer、callback、protocol handler 和配置注册模型后，能否减少把未注册 cleanup 当作 Release，以及把 request return 当作释放的错误？

### RQ4：规则优先加 LLM 是否优于纯规则或 LLM-only？

静态规则处理确定性结构、LLM 处理 unresolved 语义，是否能够在可复现性、候选召回、误报率和人工审查时间之间取得更好的平衡？

### RQ5：R 限制分析是否是跨生命周期漏洞的关键增益？

分别移除触发限制、执行能力限制、时间窗口限制和覆盖范围限制后，系统的 false-bounded 和 false-negative 是否显著增加？

## 17. Baseline 与消融实验

### 17.1 Baseline

1. **G-only**：只识别四类增长操作；
2. **E→G taint**：证明攻击者输入到达增长点，但不分析 Guard、Bound 和 R；
3. **Lexical lifecycle**：附近出现 Guard/容量/remove/timeout/consumer 即认为受到限制；
4. **Rule-only lifecycle**：执行完整静态分析，但不使用 LLM；
5. **LLM-only lifecycle**：向 LLM 提供代码 slice，由其直接判断生命周期；
6. **完整方案**：CodeQL/CFG/异步模型 + 静态规则优先 + 受约束 LLM。

如果能够公平复现成熟的 Java resource leak 或 resource-DoS 工具，可以加入外部 baseline，但必须统一分析单元和漏洞定义。

### 17.2 消融

- 移除 Guard 分析；
- 移除 Bound 分析；
- 移除 R 分析；
- 移除异步 registration；
- 移除 receiver/key 匹配；
- 移除配置解析；
- 移除 R 触发限制；
- 移除 R 执行能力限制；
- 移除 R 时间窗口限制；
- 移除 R 覆盖范围限制；
- 移除 LLM；
- 将三断言替换为四类 G 的直接分类。

## 18. Ground Truth 与数据集设计

动态验证状态不能直接作为二分类安全标签。需要区分两个维度。

### 18.1 安全证据

```text
CV: Confirmed Vulnerable
VB: Verified Bounded under explicit assumptions
I:  Indeterminate
```

### 18.2 动态执行状态

```text
DG: observed/censored growth
DNF: finite experiment without target failure
BLK: environment, route, auth or prerequisite blocked
NR: not run
```

`DNF`、`BLK`、`NR` 不能作为 negative。`VB` 必须通过独立代码与配置证据确认 Guard、Bound 或 R 的有效性。

每个标注单元应记录：

- E、G、P；
- E 控制 G 的证据；
- Guard 及有效性；
- Bound 及有效性；
- 同步与异步 R；
- R 是否影响 P；
- R 限制类型；
- 命中的断言；
- 默认配置和部署假设；
- 动态状态与资源测量；
- 最终 CV/VB/I 标签。

至少两名评审者独立标注，第三名仲裁。系统输出不得作为 ground truth 证据。

## 19. 评价指标

主要指标：

- vulnerable precision、recall、F1；
- `CV` 被错误判断为 bounded 的 false-bounded rate；
- `VB` 被报告为漏洞的 false-positive rate；
- unknown rate 和 selective coverage；
- 四类 G 和三条断言上的分层结果；
- 生命周期证书人工复核通过率。

LLM/ML 相关指标：

- G/P 候选召回；
- R 语义判断准确率；
- R 限制类型 macro-F1；
- 相对 rule-only 的增益；
- unsupported claim rate；
- 每案例人工审查时间；
- 多次运行一致性。

统计分析按 project 做 cluster bootstrap，报告 95% confidence interval。配对系统比较可使用 McNemar 或 paired permutation test，并对多个消融比较进行校正。

当前集合有 33 个严格 confirmed positive，但正式顶会评价还需要补充独立确认的 CV、真实 VB 和 I，避免仅在正例丰富的 POC 集合上报告结果。

## 20. 动态验证在方案中的角色

动态验证不是静态生命周期结论的替代品，而是用于：

1. 验证高置信断言是否能在受控资源预算下触发目标故障；
2. 为 R 执行能力 unresolved 的案例测量 producer/consumer 行为；
3. 验证 Guard、Bound 和 timeout 配置是否在实际部署中生效；
4. 区分增长、平台、下降和阻断状态；
5. 生成新的真实反例和规则。

对于断言三中的效率 unknown，工具生成定向 profiling plan：

```text
growth count/rate
release count/rate
live size of P
queue length
owner/connection count
worker busy time
blocking duration
cleanup period and latency
resource usage and service availability
```

有限运行未发生 OOM 只能说明该工作负载下没有达到故障阈值，不能自动反驳静态生命周期候选。

## 21. 预期论文贡献

在完成实现和评价后，论文可争取主张以下贡献。

### 21.1 生命周期中心洞见

提出一个简洁统一的资源增长生命周期：

```text
E → Guard → G(P) → synchronous/asynchronous processing → R(P)
```

并通过三条断言解释直接增长、无 Release 累积和受限 Release 累积。

### 21.2 完整生命周期恢复

构建跨框架入口、污点传播、CFG、字段流、异步注册、配置和 R 语义相结合的分析，恢复请求内与请求后的完整生命周期。

### 21.3 受限 Release 分析

将“存在 cleanup/consumer”进一步分析为触发限制、执行能力限制、时间窗口限制和覆盖范围限制。这是解释大量真实跨生命周期漏洞和动态验证反例的关键。

### 21.4 规则优先的 LLM 混合架构

静态规则处理可机械验证的关系，LLM 只处理自定义业务语义和无法静态确定的 G/R 效率关系，并要求输出可回放证据。

### 21.5 删失感知的真实评价

分离安全证据和动态执行状态，避免把有限 non-OOM、环境阻断和增长未达阈值误标为安全负例。

## 22. 与相邻研究的差异

论文不能只声称“首次使用生命周期”，因为资源 leak、typestate、escape analysis、admission control、bounded queue 和 timeout analysis 均有大量相关工作。

需要验证并强调的差异是：

1. 分析对象是攻击者控制的资源增长，而不是一般程序 leak；
2. 同时覆盖请求内直接增长和跨请求/异步累积；
3. 生命周期从跨架构 E 出发，并恢复到具体 P；
4. 将 Guard、Bound 和 R 放在统一增长生命周期中；
5. 把 R 存在但受到限制作为独立漏洞断言；
6. 显式恢复异步 registration 和 callback/worker/timer 生命周期；
7. 使用真实 POC 与真实限制反例评价，而不是把 non-OOM 当作安全标签；
8. LLM 只补充规则无法表达的业务语义，并由静态证据约束。

正式投稿前必须完成系统性的相关工作检索与 novelty comparison，尤其比较 resource leak analysis、typestate、async callback analysis、resource-bound analysis、algorithmic complexity/DoS 和 LLM-assisted static analysis。

## 23. 审稿风险与设计防线

### 风险一：三条断言只是常识分类

防线：论文贡献不能停留在断言文字，而要证明从真实失败和反例中抽象出的断言能够驱动跨架构、跨线程、配置感知的完整生命周期分析，并通过 baseline/消融证明其必要性。

### 风险二：LLM 决定 R 是否足够，缺乏可复现性

防线：静态规则优先；LLM 只处理 unresolved slice；使用固定模型、版本、prompt 和结构化输出；要求代码位置和静态证据；单独报告 unsupported claim rate 与运行一致性。

### 风险三：无法静态证明真实 G/R 速率

防线：不要求静态预测精确吞吐量。规则只输出结构性缺失、明确受限或 unknown；真实速率依赖案例生成 profiling plan，由动态测量补充。

### 风险四：Bound 存在但容量仍可导致 OOM

防线：区分结构性有界和预算内有界。有限容量可以反驳“无限增长”，但只有结合 item cost、作用域和部署预算后，才能输出 `bounded_under_modeled_assumptions`。

### 风险五：数据集把未复现当负例

防线：采用 CV/VB/I 与 DG/DNF/BLK/NR 双轴标签；只有独立验证的 Guard、Bound 或 R 才能产生 VB。

### 风险六：四类 G 不完备或彼此重叠

防线：明确四类仅用于候选生成和实验分层；三条生命周期断言才是统一判断逻辑；允许多标签和 `other` 类型。

## 24. 实施路线

### P0：最小可验证原型

1. HTTP/Spring/Servlet/Netty/MQTT 入口模型；
2. 四类 G/P 的 CodeQL 候选提取；
3. E→G 污点与数据流；
4. Guard dominance 与 reject-path 分析；
5. bounded/unbounded collection 和 queue 模型；
6. 同步 R、receiver/key 关系；
7. 断言一和断言二；
8. 在 Zipkin、Erupt、DCMP、Solr 和 bounded JMQTT queue 上验证。

### P1：异步与受限 R

1. executor、scheduler、callback、Netty 和 protocol registration；
2. 客户端触发 R；
3. worker/consumer 与 blocking call；
4. timeout/TTL 和 renewable timestamp；
5. terminal path 与覆盖范围；
6. 断言三；
7. 在 Presto、JMQTT QoS2、XXL-JOB、Guacamole 和 HertzBeat SSE 上验证。

### P2：LLM 与规模化实验

1. bounded lifecycle slice；
2. G/P 和 custom R 结构化 prompt；
3. rule-only、LLM-only 和完整方案；
4. evidence certificate；
5. 20-case pilot annotation；
6. project-level held-out evaluation；
7. 动态 profiling plan 与定向续测。

### P3：可解释 ML/GNN 扩展

在生命周期事实图稳定后，再研究 ML/GNN 是否能在固定人工预算下提高 G/P 或 unresolved R 的 top-k recall。学习模型不进入最终漏洞证明路径。

## 25. 最终论文主线

建议论文围绕以下逻辑展开：

```text
静态资源增长检测产生大量候选
        ↓
真实漏洞与真实限制的差异存在于完整生命周期
        ↓
统一模型：E → Guard → G(P) → processing/async → R(P)
        ↓
三条漏洞断言：
  1. Guard/Bound 无效的直接增长
  2. Bound 无效且 R 缺失的持续增长
  3. Bound 无效且 R 存在但受限的持续增长
        ↓
CodeQL/CFG/异步注册恢复生命周期
        ↓
静态规则优先判断 Guard、Bound 和明确的 R 限制
        ↓
LLM 判断剩余的业务语义和 G/R 效率关系
        ↓
真实 POC、真实 Bound 反例和删失感知评价
```

论文最需要强调的不是又发现了四类资源增长 API，而是：

> **资源释放不是一个二元的“存在/不存在”属性。即使 R 确实作用于 P，只要 R 的触发、执行能力、时间窗口或覆盖范围受到限制，在缺少有效 Bound 时，攻击者控制的 G 仍然能够形成资源耗尽。完整恢复并判断这种受限 Release，是从静态增长候选走向真实漏洞判断的关键。**

这应当作为标题、摘要、引言、方法和消融实验共同围绕的核心 Idea。
