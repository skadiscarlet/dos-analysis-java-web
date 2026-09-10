# Resource Lifecycle v1.1 执行状态

- task: `resource-lifecycle-v1.1`
- implementation_status: `partial`
- delivery_state_at_commit: `partial`
- actual_base_commit: `f62d6f2343d160a320dbb7aaec6d22c307d892f0`
- branch: `codex/resource-lifecycle-v1_1-20260908`
- current_stage: `task3_source_relations_complete`
- next_action: `Task 4 仅作为后续任务，未启动；不 push`

## 适用标准

- 唯一 P0 实施标准：`docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md`
- 本轮增量合同：工作区外层的 `CODEX_GOAL_LIFECYCLE_V1_1.md`（2026-09-08，`resource-lifecycle-v1.1`）
- P0 schema/tool 保持 `2.5/0.4.0`；本轮只扩展并行的离线 `resource-*` 链，不把异步模型性质升级成旧 P0 漏洞结论。

## 实际基线

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| remote | `origin = ssh://git@ssh.github.com:443/skadiscarlet/dos-analysis-java-web.git` | 与合同仓库匹配 |
| lifecycle 固定起点 | `f62d6f2` | 当前分支直接从已审阅提交创建 |
| 全仓 network-free baseline | `101 failed, 797 passed, 26 skipped, 389 subtests passed` | `python3 -m pytest -q --junitxml=/tmp/resource-lifecycle-v1_1-baseline.xml`；失败来自 ignored 大型资产未挂载及沙箱 socket `EPERM`，最终按 test ID 比较 |
| lifecycle baseline | `179 passed, 4 skipped, 34 subtests passed` | `python3 -m pytest -q tests/test_resource_lifecycle_*.py` |
| real CodeQL lifecycle baseline | `27 passed, 10 subtests passed` | `DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_resource_lifecycle_codeql.py`；CodeQL 2.23.8 / javac 21.0.12.1 |

## Task 2 完成证据

- population attachment 复审已关闭：`TaskBinding` 显式绑定 submit/queued/run/normal/exceptional/rejected/cancelled 七个 task-stage event，七类 ID 跨 binding 唯一；submit 可属于 caller，其余 stage callable 必须等于 task callable。八类 population effect 以 source/target/exit-kind 精确附着；active termination/cancellation source 可为 run 或从 run 经 `Program.transitions` 的 internal、同 callable CFG 边可达的 method event，断开或跨 callable method 拒绝。Program/Transition 的 `1.0/1.1` exact field sets 已改为显式不可变集合，旧 `1.0` 不迁移新增 TaskBinding 字段。真实 RED 为 `6 failed, 1 passed`；核心 GREEN 为 `7 passed, 34 subtests passed`，相邻 schema 为 `4 passed, 13 subtests passed`，lifecycle 全量为 `244 passed, 5 skipped, 194 subtests passed`，真实 CodeQL 为 `36 passed, 16 subtests passed`（530.26s）。P0 schema/tool 保持 `2.5/0.4.0`；Task 4 solver 未提前实现。
- Task 2 code-quality review 的五个 Important 已关闭：task event/callable/exit 与 population transition endpoint 精确绑定；executor enum 成为 dispatch 语义唯一来源且与 legacy boolean 冲突时 fail closed；manual ProgramPoint/PopulationEffect provenance 在两个导入/验证入口均限定为 `manual_fixture`；QL program-point identity 改为 callable + file + start/end span 的 site identity，同 site dispatch/invariant 不再因 fact kind 分裂；Program/Transition 使用集中式 `1.0/1.1` exact field sets，`1.1 coverage_gaps` 必填，旧 schema 携带任何新增空 relation/population 字段也拒绝。旧 `1.0` coverage evidence 保留，只有新增 relation/population collection 在 exact schema 校验后迁移为空。
- 五项 review 最终验收：lifecycle 全量 `232 passed, 5 skipped, 128 subtests passed`；真实 Java/CodeQL compile、query、decode、adapter 与 CLI `36 passed, 16 subtests passed`（526.12s）；direct/embedded QL 字节一致，P0 schema/tool 仍为 `2.5/0.4.0`。Item 4 focused 真实反例先观测到同 location 的 `#dispatch/#invariant` identity 分裂，修复后同 site program point 相等；Item 5 focused exact-schema 用例为 `4 passed, 10 subtests passed`。
- lifecycle Program/facts 及全部 `resource-*` JSON 输出统一为 schema `1.1`，tool identity 为 `resource-lifecycle-v1.1`；旧 `1.0` Program/facts 只在无 v1.1 relation/population/executor 字段时兼容读取，legacy raw facts 会在旧 ID/snapshot/derived-unit 校验后归一化为当前模型；旧 named-v1 recording 只由 exact-field/typed loader 受限读取，新 private recording 与 validation 输出均为 `1.1`。P0 schema/tool `2.5/0.4.0` 未改。
- 关系/群体 IR 定向：`8 passed, 44 deselected, 2 subtests passed`；solver/CLI/CodeQL 非 Fixture：`77 passed, 4 deselected, 13 subtests passed`。
- Task 2 reviewer 四项定向：`5 passed, 6 subtests passed`；CodeQL + recorded LLM：`62 passed, 4 skipped, 23 subtests passed`；lifecycle 全量：`209 passed, 4 skipped, 48 subtests passed`。
- Task 2 第二次 spec 复审补齐版本绑定：真实旧 `1.0` executor contract identity 先按不含 `max_workers/rejection_policy` 的旧字段集合核对 derived units，再归一化为 `1.1` identity；schema `1.1` Program 必须显式携带四组 relation collection 和每条 transition 的 `population_effects`，外层 facts 与 nested Program schema 必须精确一致，缺省兼容只保留给 `1.0`。legacy migration RED 为 `1 failed`，严格 parser RED 为 `6 failed, 1 passed`；定向 GREEN 为 `3 passed, 5 subtests passed`，lifecycle 全量为 `214 passed, 4 skipped, 58 subtests passed`。
- Task 2 第三次 spec 复审把 executor contract loader 绑定到外层 facts schema：`1.1` 要求 `max_workers/rejection_policy/termination` 与其余 contract 字段一起精确存在，只有显式外层 `1.0` facts 才补 `None/unknown/unknown`；manual extraction manifest 是独立输入边界，继续按 current contract 严格解析，不借其 manifest 版本启用 facts compatibility。有效 RED 为 `3 failed, 2 passed`，定向 GREEN 为 `2 passed, 3 subtests passed`，lifecycle 全量为 `215 passed, 4 skipped, 61 subtests passed`。
- 真实 CodeQL：query compile `Done [1/1]`，四个 source fixture 为 `33 passed, 15 subtests passed`；direct/embedded QL 字节一致。

## Task 3 完成证据（V4 follow-up，限定 G2 源码关系范围）

- V4 最终验收完成，G2 `pass`、Task 3 complete；整体仍 `partial`，G3–G8 仍 `fail`，不启动 Task 4、不 push。fresh quality 为 `Ready: Yes`（Critical/Important/Minor 均无），fresh spec 为 `Spec compliant`。最终非 fixture `285 passed, 13 skipped, 235 subtests passed in 4.79s`（`/tmp/task3-v4-final-nonfixture.xml`）。四项既有真实 wrapper/task/fresh-review 在冻结批次中全部通过；该批次唯一失败是新增 RepeatedSubmit 测试误猜每 task 三出口，而 raw query 实为一个出口，详见下面分层记录，不计生产缺陷 RED。仅修正测试后，四形态 Java→双 query→最终 adapter 补验为 `1 passed, 18 deselected in 267.94s`（`/tmp/task3-v4-final-repeated.xml`）：depth1/depth2/mixed/same-depth-prefix 分别 2/2/4/4 tasks，14/14/28/28 stage events，逐 task 出口 evidence 与 matching raw instance/depth/entry/target 的完整集合相等。production/fixture 在这两次最终真实运行间没有变化。最终 `compileall`、两对 QL `cmp`、`git diff --check` 通过；QL SHA 维持冻结值，P0 未改。

- `12e297eb586e1407a5aab49e1fe1b31fcb7bf231` 后 fresh quality review 为 `No`，G2 回退 `fail / in_progress`：I1 重复 submit 的 task instance identity、I2 声明深度/上下文预算、I3 adapter 读取源码期间 TOCTOU、I4 related-location provenance 均须修复并重新验收。下列 spec/GREEN 为先前里程碑，不覆盖此次质量 blocker。
- V3 follow-up 实施已完成，尚待最终真实回归与独立复审，G2 不提前改 pass。新增 `tests/test_resource_lifecycle_review_safety.py`：I1 单 submit 正控通过、双 submit 的两种 identity 异常取得有效 RED `2 failed`；I2 给定四边图越界深度/孤立前缀/预算取得有效 RED `3 failed, 1 passed`；I3 adapter 期间修改临时源码后旧实现仍发布，I4 四种 related-location 篡改在重建 derived/snapshot 与 JSON 往返后旧实现仍通过，合计有效 RED `5 failed`。Minor source CFG 构造 9 个 effect 而仅需 3 个的有效 RED 已修复。
- V3 首轮非 fixture 全 lifecycle：`279 passed, 13 skipped, 235 subtests passed in 4.41s`（`/tmp/task3-v3-nonfixture.xml`）；单独真实 RepeatedSubmit Java→Base+Task query→adapter 为 `1 passed in 272.66s`（`/tmp/task3-v3-repeated-java.xml`），两次 submit 保留同资源/共享 executor，但拥有独立 14 stage events、holders、TaskExit、population 与 callback release attachment IDs。最终五项真实回归正在执行，不能以此前进程代表最终代码验收。
- V3 context 展开仅允许声明 depth-1 的已证明前缀，缺失关系不生成 CallBinding 并输出 family/evidence scoped gap，深度不匹配不得串用 CFG/effect/submit 证据；每 unit 非空 contexts 与 expanded bindings 均硬限 4096，超过即 fatal，不按 hash 顺序截断。I3 publication 前复核 adaptation 后 source snapshot；I4 current fact identity 绑定完整 related SourceLocation，主/related 均校验 static source kind 与 extractor，legacy 1.0 仍先核验原始 identity 再迁移。`compileall`、两对 QL `cmp` 与 `git diff --check` 已通过；两 QL SHA 与 V2 冻结值一致，未改变 P0 或 Task 4。
- V3 五项冻结真实回归已结束：`5 passed, 74 deselected, 11 subtests passed in 1215.62s`（`/tmp/task3-v3-final-real.xml`）。quality 复审仍为 No，仅余 I1 同 site 的跨 call-context 归属；不能把该批次作为 V4 最终验收。V4 完整前缀 normalization 的有效 RED 为 `4 failed, 2 passed`（两种单 depth 正控先通过），修复后同 depth 双前缀与 mixed-depth 均为 2 tasks/14 stages/2 exits、共享 executor；缺深层 body 时保留 2 tasks 但仅 1 exit/CFG/release 并有 scoped gap。task-context 乘积同样硬限 4096，dispatch/invariant 任一先出现均先预算检查。最终非 fixture `285 passed, 13 skipped, 235 subtests passed in 4.56s`（`/tmp/task3-v4-nonfixture.xml`），真实 fixture 已扩为 depth1/depth2/mixed/same-depth-prefix 四形态；最终真实验收与 quality 复审仍待，G2 不提前 pass。
- 最终 fresh spec rereview3：`Spec compliant`。G2 恢复 `pass`、Task 3 完成；整体保持 `partial`，G3–G8 未通过，Task 4 仅为下一步。本次 follow-up 以 `d2311f64c61a665fa52932f8b8c498919e01caf6` 为父提交，不 amend、不 push。
- V2 最终受影响真实双 query→adapter 验收为 `2 passed, 64 deselected, 11 subtests passed in 531.24s`（`/tmp/task3-v2-final-owner-codeql.xml`）：覆盖 TaskReviewGaps 原 allocation obligation 保留、depth=2 正控、独立 escape gap、间接 unsupported task/configuration gap，以及 TaskTerminals 实际 body/fallback LambdaExpr 的程序点归属/位置/coverage。最终非 fixture 为 `267 passed, 12 skipped, 235 subtests passed in 4.24s`（`/tmp/task3-v2-final-nonfixture.xml`）；两对 QL 字节一致、`compileall`、`git diff --check` 通过。此最终定向证据与下列完整 suite 的版本范围分别记录，不声称最后 owner 修复后又跑过完整 suite。
- `d2311f64c61a665fa52932f8b8c498919e01caf6` 后 fresh spec 复审提出四项源码关系核查：depth=2 参数 overwrite task 错绑；exact callback close 遮住 field escape gap；间接 anonymous/member-reference/local capture 静默；field-initializer executor alias mutator 是否漏检。当时 G2 回退 `fail / in_progress`，此前历史 GREEN 不覆盖这些反例；现经修复、真实源码验收与再次复审关闭。第四项的实际核验结果见下文，不把审查假设当作已复现缺陷。
- V2 Task QL 已冻结为 `19b78920abd44927b627d29b1ea9e726cb38c9a38e1654a44122de59ae33cbae`；前三类真实 query RED 为 14 条断言失败，修复后 0 失败（115→102 rows）。第四类 field alias 在旧 CodeQL 结果中已保守降级，本轮只补显式 initializer alias 加固/回归，不宣称复现了该项旧缺陷。完整真实 suite 为 `1 failed, 65 passed, 58 subtests passed in 2172.11s`（`/tmp/task3-v2-full-codeql.xml`），唯一失败是新测试错误要求完整建模的 rejected capture unit 必有 gap；已换成原 allocation obligation 仍存的状态断言。
- fresh spec 复审确认最后 blocker 是 callback gap fallback LambdaExpr owner。现区分实际 lambda body effect site 与 wrapper 内 LambdaExpr AST，合成 RED→GREEN 为 `1 failed` → `1 passed, 18 subtests passed`；最终 fresh-review 与 TaskTerminals 双 query adapter 复验已通过，见上文。
- 明确限制：已支持 wrapper call-depth<=2 不等于支持嵌套 task；nested task depth>1、nested capture/local-alias propagation 仍为 unsupported，相关 gap 覆盖尚未证明完整。本轮未实现嵌套异步闭环，不将这些形态声称为完整静态覆盖或无条件安全；后续必须补独立源码验收。

- 最终 release gate 验收分层记录：最后 base gate 修复前的完整真实 CodeQL 套件为 `62 passed, 45 subtests passed in 1829.42s`，JUnit `/tmp/task3-final-codeql.xml`；不能据此声称最终 adapter 又跑过全套查询。最新 adapter 非 fixture 为 `267 passed, 11 skipped, 229 subtests passed in 4.16s`，JUnit `/tmp/task3-final-nonfixture.xml`。
- base partial release 的状态级 RED 为 `4 failed, 1 passed, 1 subtests passed`，缺 caller CFG fallback 的 RED 为 `3 failed, 1 passed`；当前定向 GREEN 为 `7 passed, 7 subtests passed`。只允许 complete singleton-finally exact-local release 在可信成功 CFG 出边执行；partial/unsupported/未证明 receiver identity/缺 CFG 一律保留 raw、程序点和 scoped gap，不附 release 负效应。synthetic complete 旧导入例显式隔离，不作为真实源码验收证据。
- 最终 adapter 对相同 query SHA 的真实 facts 回放覆盖 35 units、14 条 partial release：`conditionalAlias` obligation `1→1`，`overwrittenAlias`/`selectedAlias` `2→2`；`syncClosed.close_obligation=(bounded,0)`、`boundedQueued.held_instances=(bounded,2)`、`concreteBoundedQueued.held_instances=(bounded,3)`。回放路径 `/tmp/task3-base-release-gate-replay.json`。受影响 wrapper/source-state 真实重跑为 `2 passed, 62 deselected, 5 subtests passed in 275.32s`，JUnit `/tmp/task3-final-gate-affected-codeql.xml`；该进程在最后缺 CFG fallback 修复前已加载 adapter，覆盖有 CFG 的 base-release gate，最后无 CFG 分支改动由最终非 fixture 与最终 adapter 真实 facts 回放单独复验。
- 当前 finalizer：真实 callable CFG、depth<=2 call-site context、parameter-entry/callee-exit/caller-continuation 已接通；同一行重复 wrapper 调用不产生虚假回边，返回参数经两层精确摘要后仍绑定原实例，参数 overwrite 不再错绑第二层。static field/executor identity 跨 callable 共享。真实 wrapper 定向为 `1 passed, 60 deselected in 198.12s`，包含 finally 中 wrapper 成功返回后恢复 caller pending exception 的图断言。
- 同步 baseline 的 CFG 回归已关闭：synthetic finally bridge 的 pending exception 不能算作 close 自身失败；操作结果按第一步 SuccessorType 分类，保留非 exception 的 return/break/continue，source Program 只声明实际 annotated exit。完整真实套件、受影响定向与最终 adapter 回放的版本范围按上文分别记录，不混用为最终全套证据。
- callback release 已冻结为 exact source+related PP/location/depth 与可信成功 CFG 出边；terminal close 经 `#normal-success:call-cfg-v1`，成功后的 normal/exceptional terminal 与 close 自身失败严格分离，不在 TaskExit 直接释放。Task QL SHA 为 `a027b70cbbace1efd1746bcf2f6ec256b999e93be3d9e65b057f4e74e3e8f6f8`；SourcePairs/TaskCfgCoverage/TaskTerminals 定向为 `3 passed, 7 subtests passed in 625.75s`。下列历史 follow-up 的入边 release 和显式 return/throw terminal 证据已被独立审计否决，不代表当前实现。
- 最终自审：同类多 terminal 与平行 normal/exception 边保留；合法 TPE core=0 与队列已满但 a<W 的接纳分支保留；未知 worker limits、mutable/escaped executor、unsupported callback/cancellation 等不生成未经证明的计数或释放效应。两对 QL 字节一致、`compileall` 与 `git diff --check` 通过。G2 仅证明窄范围源码关系提取/附着，不证明 G3 主求解异步闭环或 G4–G8；P0 输出口径未改，不运行服务、PoC、动态验证或远程 LLM。

- CodeQL 已拆成真实双查询架构：base `ResourceLifecycleFacts` 只提取 allocation/lifecycle、stable program point、depth<=2 exact call binding 与 depth gap；task `ResourceLifecycleTaskRelations` 独立提取 lambda capture、静态 `ThreadPoolExecutor` 配置、task CFG、normal/exceptional exit 与 task partial facts。两份 direct/embedded QL 分别字节一致；最终 `compile --check-only` 均为 `Done [1/1]`。独立完整执行记录为 base compile `2m43s`、eval `1.1s`、total `2m50.15s`，task compile `4m0s`、eval `1s`、total `4m06.22s`，均低于 runner 固定 300 秒单-query 上限。
- runner 使用 anchored family matcher，formal `codeql_database` extraction 固定按 base -> task 顺序先执行完整 suite，再 decode/adapt；第二 query 失败的反例确认 adapter 未调用且 `facts.json`/`coverage.json` 不发布。query snapshot、BQRS、database fingerprint 与 source snapshot 在执行/发布边界复核，`_implementation_sha256()` 同时绑定两份 packed QL。
- 每条 `RawLifecycleFact` 保存 `query_name/query_sha256`，fact ID 绑定 row origin；formal coverage 保存 ordered `query_provenance`、两个 query SHA、两个 BQRS SHA、顺序敏感 suite SHA、database fingerprint、source snapshot SHA 与 provenance SHA。validation 的 suite order、BQRS、database 与 source tamper 反例均 fail closed；legacy `1.0` 只在拒绝 v1.1 relation semantics 后走旧单-query identity/ID/snapshot/derived-unit 验证与迁移。
- merge 明确拒绝跨 query duplicate semantic row、task orphan `instance_key`、unknown base unit 与 dangling `cfg_edge/task_exit`，且只有 task-query dispatch 能满足 task relation 绑定；partial relation-only fact 显式转为适用资源维度的 coverage gap（closeable fixture 为三个），不再触发 `KeyError` 或静默丢失 unknown。coverage 边角 RED 为 `2 subtests failed`，GREEN 为 `1 passed, 2 subtests passed`；query-origin dangling 反例 RED 为 `1 failed`，GREEN 为 `1 passed`。
- adapter 从真实 rows 合成 `ProgramPoint`、`CallBinding`、`TaskBinding`、`TaskExit`、七个 task-stage event、task method CFG/transitions 与八类原子 `PopulationEffect`，不把 callback 原子折叠。真实 fixture `SourcePairs.java` 覆盖 caller -> wrapper1 -> wrapper2、`W=2/K=3/AbortPolicy`、lambda capture、显式 return/throw 与 finally close。
- 双查询/provenance RED 为 `8 failed, 37 deselected`，GREEN 为 `8 passed, 37 deselected, 9 subtests passed`；非真实 fixture contract 为 `39 passed, 6 deselected, 20 subtests passed`；最终源码组合为 `1 passed, 45 deselected in 436.13s`；最终 lifecycle 全量为 `253 passed, 6 skipped, 205 subtests passed`。P0 schema/tool 仍为 `2.5/0.4.0`，resource lifecycle 为 `1.1/resource-lifecycle-v1.1`。
- Task 3 follow-up 已从真实 `SourcePairs.java` 取得 caller allocation -> wrapper1 -> wrapper2 -> lambda capture -> `finally { resource.close(); }` 的 callback release relation：Task QL 仅对 depth<=2 exact parameter、static-final AbortPolicy executor、单语句 finally 的 captured `AutoCloseable.close()` 输出 complete `release`；release 的 program point 与 `finally block -> close statement` 的 task CFG target 对齐。adapter 只在同 instance、同 lambda target、同 CFG target 的 raw release 上附着 `task_cfg_edge` release effect，不能由 executor completion/termination 推导。RED 为 release row 缺失的 `StopIteration`；GREEN 为定向真实源码 `1 passed, 60 deselected in 263.75s`，最终 lifecycle 为 `264 passed, 10 skipped, 210 subtests passed`、完整真实 CodeQL fixture 为 `61 passed, 26 subtests passed in 1611.28s`。direct Base/Task query run 分别为 2m20.92s / 1m58.66s，均成功。

## G1–G8 当前状态

| Gate | 状态 | 当前证据/缺口 |
| --- | --- | --- |
| G1 实例一致性 | `pass` | `tests/test_resource_lifecycle_solver.py`：旧实现定向 `3 failed, 2 passed`，扩展 per-instance 断言为 `5 failed`；修复后 solver+CLI `42 passed, 6 subtests`，全 lifecycle `183 passed, 4 skipped, 34 subtests` |
| G2 源码关系 | `pass` | I1–I4 与 Minor 完成有效 RED→GREEN；任务与完整调用前缀隔离、depth/budget fail-closed、post-adapter snapshot 复核、related provenance 全字段绑定。最终非 fixture 285 passed；既有四项真实通过，四形态新 fixture 单项真实补验通过；fresh quality Ready Yes、fresh spec compliant。 |
| G3 主求解异步 | `fail` | `commands._analyze_payload` 先 `solve`，后 `_async_stages` 展示后继 |
| G4 释放与持有收益 | `fail` | 尚无 S2/S3 源码成对主求解差异 |
| G5 群体检查 | `fail` | `InvariantCandidate` 仍接受 `initial_holds/transitions_preserve/covers_writers` 输入布尔值，未从 q/a 转移检查归纳性 |
| G6 源码验收 | `fail` | 尚无六组十二变体的真实 CodeQL 验收 |
| G7 固定输入增益 | `fail` | 当前 local/full 对照来自人工 IR，未对相同源码事实删除跨事件传播能力 |
| G8 可审阅交付 | `fail` | v1.1 报告、门槛证据、失败集合差分和 HANDOFF 尚未生成 |

## 失败与环境记录

- 第一次 `git worktree add` 因 `.git` 在沙箱内只读失败；经显式审批后成功创建隔离分支，没有修改外层脏工作区。
- zsh 初始化会打印 `iptables: Failed to initialize nft: Operation not permitted`；它不是测试失败。
- 本轮不恢复 ignored `frameworks/`、`databases/`、历史 `results/` 到 worktree，不运行服务、PoC 或动态 DoS。
