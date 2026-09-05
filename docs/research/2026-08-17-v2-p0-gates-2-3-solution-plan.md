# v2 P0 硬门槛 2 / 3 解决方案

> 状态：**approved P0 范围内已完成并验收（2026-08-18）**。已完成 same-CFG Guard/Bound/Release、显式 path/family `LifecycleCoverage.ql`、严格 throw-only depth≤1 `LifecycleSummary`、attacker-controlled loop witness、跨 handler/resource 隔离，以及真实 fixture DB + 真实 CodeQL + 真实 DeepSeekClient/mock transport 的十场景 production E2E。depth>1/custom/reflection/async-capacity 仍按批准边界显式 partial/`static_unknown`。另有 Erupt/Citrus/DataCompare 三个动态真阳性 seed 的 formal static canary 全部 completed、0 query diagnostics、resume 可复用、无凭据泄露。本文不改动主模型 `Vulnerable(E,G)` 或 deferred 边界。
>
> - **原始硬门槛 2（已关闭）**：十类 P0 场景已迁移为真实 fixture database + 真实 production executor/CodeQL + 真实 DeepSeekClient/mock transport E2E。
> - **原始硬门槛 3（approved 范围已关闭）**：same-CFG、严格 depth≤1 wrapper 与 attacker-controlled loop 已实现；仅 depth>1 arbitrary/custom/reflection/fan-out/async-capacity 保持批准的 deferred `partial`/`static_unknown`。

## 验收结果（2026-08-18）

- offline：`611 passed, 9 skipped, 437 subtests passed`；
- real CodeQL entry/growth：`5 passed, 30 subtests`；real lifecycle：`3 passed, 50 subtests`；
- production E2E：Spring P0 1–8、Servlet G2/Release、Netty bootstrap/finite Bound/async、MQTT registration/repeatability 共 4 tests 通过；stage hash/time 与 provider request count 验证 resume 不重跑；
- Gate 3 fresh reviewer 第四轮：0 BLOCKER / 0 HIGH；caught throw、post-order wrapper、return helper、depth3 chain 均不得产生 bounded；
- true-positive canary：`results/java_web_dos_batch/p0-true-positive-canary-20260817/` 三目标 formal completed，目标 truth 只作 post-hoc 映射；
- 新 205-target formal plan：`results/java_web_dos_batch/java-web-205-formal-ready-gate23-20260818/batch_plan.json`，205 targets（205 全部 queued；178 git-commit + 27 tree-sha256 指纹，git-commit provenance 不再是门槛），digest `7fb0dc310b1523fedb084b7596e8568170d9349b248f808c88ee3382bb608023`；未启动批次执行。

## 0. 两门槛的耦合关系（决定实施顺序）

门槛 2 的十场景里有四类必须依赖“effective lifecycle”证据才能落到非 `static_unknown` 的最终结论：

| 场景 | 依赖的 lifecycle 能力 | 归属 |
|---|---|---|
| 5. checked finite queue → `bounded_under_modeled_assumptions` | Bound complete（capacity/product bound + result check） | 门槛 3 |
| 6. post-materialization Guard | 不能反驳已发生 G1；仅可反驳其后独立、被 CFG 支配的 G2 | 门槛 3 |
| 7. success-only Release → `static_vulnerable`（release 无效） | Release 证明（normal+exception path 才 complete，否则 ineffective） | 门槛 3 |
| 8. async consumer unknown → `static_unknown` | Release 的 `potential_async` 判定 | 门槛 3 |

因此 **先实施门槛 3 的“可证明正例 + 反例隔离”子集，再实施门槛 2 的 E2E harness**；两者共用同一套真实 CodeQL fixture 数据库。

---

## 一、硬门槛 3：bounded effective lifecycle + amplification

目标不是消除所有 `partial`（反射、custom dispatch、任意框架拦截器等本质上不可静态证明），而是：

1. 对 **same-callable / bounded one-level wrapper** 的 Guard/Bound/Release，给出 **CFG 支配/后支配证据**，使有效正例可 `complete`（从而可反驳断言），反例保持 `ineffective`/`unknown`；
2. 对 **loop/fan-out multiplicity**，仅在“循环边界值可证明由 attacker 输入流入”时判 `proven`，其余 `partial`；
3. 保持跨 path 的同名 receiver/key 严格隔离（现有 `(entry_id,growth_id,path_id)` 绑定已有，但需补跨 path 反例回归）。

### 1.1 Guard complete：CFG 支配证明（`GuardCandidates.ql` + `dosweb/lifecycle/guards.py`）

当前 `GuardCandidates.ql` 全部输出 `partial` 且 `dominates=false`。改为：

- 在 `Lifecycle/GuardCandidates.ql` 内用 `ControlFlowGraph` 求同一 callable 内 guard 节点与 growth anchor 节点的 CFG 关系：
  - `dominates`：guard 基本块支配 growth 基本块（`bbGuard.dominates(bbGrowth)`，用 CodeQL `BasicBlock`/`CFG` 谓词）；
  - `reject_path_reaches_growth=false`：reject 分支（`return`/`throw`/`forbidden` sink 所在后继块）不与 growth 块存在任何 forward CFG 路径；
  - `covers_materialization`：guard 在 materialization 节点之后（源码行序 + CFG 序一致）。
- 仅当 `dominates ∧ ¬reject_path_reaches_growth ∧ covers_materialization` 时输出 `coverage_status=complete`；否则维持 `partial` + 明确 reason（`guard_cfg_dominance_unproven` 等）。
- `guards.py` 对应地把 complete 行判定为 effective，partial 行继续 `unknown`。

验收：Guard 必须位于被其反驳的 Growth 之前并有 CFG witness；post-materialization Guard 不得反驳已经发生的 G1，仅可反驳后续独立 G2；无关分支负例得 partial/ineffective。

### 1.2 Bound complete：有限容量 + 结果检查（`BoundCandidates.ql`）

当前仅 `ArrayBlockingQueue`（经 `getGenericType().hasQualifiedName`）得 complete。扩展（保持保守）：

- 只支持真正 hard capacity 的 `ArrayBlockingQueue(int)`、`LinkedBlockingQueue(int)`（容量参数为字面量或可证明的建模配置值）；`HashMap`/`LinkedHashMap`/`ConcurrentHashMap` 初始容量仅是 allocation hint，绝不能作为 bound；
- `result_checked`：仅 `offer` 返回值进入 if/throw 的可靠拒绝路径；`add`/`put` 的异常或返回语义未做 path 建模时保持 partial；
- `product_bound`：容量 × 单元素大小上界（仍只对字节/数量维度可用）。
- receiver/key 身份用字段 FQN + 分配锚点（现有），纯字符串 qualifier 维持 partial。

验收：Netty `finiteQueue` 保持 complete；`HashMap` 无界 put 负例与未检查 `offer` 结果负例保持 ineffective/partial。

### 1.3 Release complete：实际减少 + normal/exception path（`SynchronousReleaseCandidates.ql`）

当前 finally 形状一律 partial（`exceptional_path=false`）。改为：

- 同一 receiver/key 的 `remove`/`clear`/`evict`/`close` 调用点，用 CFG 后支配证明其覆盖 normal 与 exception 两条退出路径：
  - normal：release 调用基本块后支配 growth 块且可到达 callable 正常返回；
  - exception：release 位于 `finally` 块，且该 finally 覆盖 growth 块（try 范围），用 `TryStmt` + CFG 判定；
- 只有两者都成立才 `exceptional_path=true`、`coverage_status=complete`、`actual_reduction=true`；
- success-only release（无 finally、无异常覆盖）→ `actual_reduction=true` 但 `exceptional_path=false`、`coverage_status=complete`（“success-only”是语义可证明的无效 Release，用于场景 7 得到 `static_vulnerable`）——注意与“证据不足”的 `partial` 区分开；
- 异步消费者 / 无同步 reduce 证据 → `potential_async` → evaluator 归 `static_unknown`。

验收：success-only 场景 7 得 `static_vulnerable`；try/finally + 同 receiver 正例得 refuted（`bounded_under_modeled_assumptions`）；异步消费者负例得 `static_unknown`。

### 1.4 跨过程 bounded wrapper（depth ≤ 1）

对“growth 调用一个 helper 完成 guard/bound/release”的常见 wrapper 模式：

- 在 lifecycle 查询里用 `Call.getCallee()` + `getACall()` 建立一层调用关系；把 callee 内的 guard/bound/release 节点提升到 caller 的 call site，再按 1.1–1.3 的 CFG 规则判定；
- 深度 > 1 或 callee 不可解析（buildless DB 常见）→ `partial`（不伪装 complete）；
- 只对同一源码文件内的 callable 求 CFG，跨文件/跨编译单元保持 `partial`。

验收：一个 one-level helper guard 正例得 complete；two-wrapper 负例保持 partial（呼应 CHANGELOG 已有的 “two-wrapper partial” 约定）。

### 1.5 loop/fan-out multiplicity（Amplification）

- 在 `Growth/ContainerGrowth.ql`、`AsyncWorkGrowth.ql` 已区分“单次操作 / loop 内操作”基础上，增加“循环边界可证明由 attacker 输入流入”的判定：
  - 用 global dataflow 证明 `LoopStmt` 的边界/条件表达式的值来源为 entry demand（size/value）；
  - 仅当该流 `proven` 时 `single_request_amplification=proven`（A1 适用），否则 `partial`（A1 不适用）；
- fan-out（单次请求多线程/多写路径）不建模，保持 partial。

验收：`for (i=0;i<request.getParameter("n");i++) map.put(i,...)` 得 proven；`for (Entry e : fixedList)` 或未知边界得 partial。

### 1.6 跨 path 反例回归（防 false-bounded）

- 新增 fixture：两个 handler 各持同名字段（如 `queue`），A handler 有 effective Release、B handler 无；断言 B 的 lifecycle 决策不被 A 的候选反驳（现有 `(E,G,path)` 绑定已应隔离，补回归锁定）。
- 同 key 但不同 receiver 类型/字段 FQN 的候选不得互相反驳。

---

## 二、硬门槛 2：十场景 production E2E harness

### 2.1 复用与抽取

- **真实 CodeQL DB**：复用 `tests/test_codeql_lifecycle_queries.py` 已修好的“编译 fixture source_root 下全部 Java 源”建库逻辑，抽成 `tests/support/fixture_database.py::build_fixture_database(source_root)`，session 级缓存，避免每个场景重复建库。
- **Mock provider**：抽取 `tests/test_deepseek_client.py` 的 `_ScriptedHandler` + `ThreadingHTTPServer` 为 `tests/support/mock_deepseek.py::MockDeepSeekServer`，按场景返回预置 Growth/Auth Contract（含负例：LLM `yes` 但无 proven flow → 必须 unresolved）。
- **Harness**：新增 `tests/test_production_e2e.py::ProductionE2EHarness`，对每个场景：
  1. `build_production_pipeline(values, command="analyze", run_query_fn=真实 run_query, validate_database_fn=真实 validate_database, deepseek_client_factory=指向 mock 的 factory)`；
  2. 断言 `run("analyze")` 状态、`findings` verdict、matching certificate、`report.md` 输出、以及 finding 引用的 reachability/repeatability/amplification/config/flow/lifecycle evidence 非空且一致；
  3. 断言语义：`static_vulnerable` / `bounded_under_modeled_assumptions` / `static_unknown` 各按场景精确匹配，且 `reason_codes` 含预期 code。

### 2.2 十场景矩阵与期望 verdict

| # | 场景 | fixture 关键点 | 期望 verdict |
|---|---|---|---|
| 1 | request materialization | Spring `@RequestBody byte[]` → G1 size | `static_vulnerable` |
| 2 | attacker-controlled allocation | Servlet `doPost` body → `new byte[n]` | `static_vulnerable` |
| 3 | distinct-key global map | MQTT message key → `static Map` put | `static_vulnerable` |
| 4 | unbounded executor queue | Netty handler `submit(task)` 且存在普通 async consumer | `static_unknown`；仅明确无 consumer/reduction 时可 vulnerable |
| 5 | checked finite queue | Netty `ArrayBlockingQueue(8)` + offer 结果检查 | `bounded_under_modeled_assumptions` |
| 6 | post-materialization Guard | G1 materialization 已发生，后续 G2 才由 Guard 支配 | G1 `static_vulnerable`；后续 G2 可 `bounded_under_modeled_assumptions` |
| 7 | success-only Release | 同 receiver remove 但无 exception 覆盖 | `static_vulnerable` |
| 8 | async consumer unknown | 生产者写入、异步消费者 reduce | `static_unknown` |
| 9 | Netty bootstrap ± | installed initializer（positive）与 uninstalled（negative） | positive 按证据判定；uninstalled complete no-entry 可无 finding，partial registration 必须 disposition/gap→`static_unknown` |
| 10 | MQTT registration/repeatability | subscription_registration + repeatable trigger | `static_vulnerable`（repeatability=proven） |

### 2.3 验收

- 十场景全部在无网络、无真实 DeepSeek、无动态执行下通过，且每条断言落到 verdict/certificate/report，而非仅断言 row count。
- `python3 -m pytest -q tests/test_production_e2e.py` 全绿，且与 `tests/test_deepseek_client.py`、`tests/test_codeql_lifecycle_queries.py` 无冲突。

---

## 三、实施顺序与硬门槛关闭条件

1. **门槛 3 子集**（1.1–1.6）：effective Guard/Bound/Release 正例 + 跨 path 反例 + 循环倍数，离线 fixture 全绿；
2. **门槛 2 harness**（2.1–2.3）：十场景 production E2E 全绿；
3. 全套 `pytest`、`compileall`、`git diff --check`、direct/embedded pack 一致、无 execution snapshot；
4. 真实 DeepSeek 3–5 repository formal full canary（需真实凭据，仍为独立授权动作）确认无 query diagnostics / artifact corruption；
5. 更新 `docs/research/2026-08-17-v2-p0-design-compliance-audit.md` 状态矩阵与 `CHANGELOG.md`。

只有 1–3 完成且 4 通过后，才生成新的 **205-target** 正式执行计划（205 全部 queued；git-commit provenance 不再是门槛）。

## 四、明确保持 deferred（不变）

Assertion 3、异步 Release capacity、producer/consumer rate、TTL/timeout、WebSocket、任意 custom protocol、ML/GNN、自动动态验证、deployment-budget proof；以及 depth>1 的跨过程 lifecycle、反射/custom dispatch 路由——遇到即 `partial`/`static_unknown`，不得推断安全。
