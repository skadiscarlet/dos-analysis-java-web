# Resource Lifecycle v1.1 执行状态

- task: `resource-lifecycle-v1.1`
- implementation_status: `partial`
- delivery_state_at_commit: `partial`
- actual_base_commit: `f62d6f2343d160a320dbb7aaec6d22c307d892f0`
- branch: `codex/resource-lifecycle-v1_1-20260908`
- current_stage: `task3_source_relations_complete`
- next_action: `Task 4 主求解异步语义；本次不启动`

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

## Task 3 完成证据（G2 源码关系范围）

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
| G2 源码关系 | `pass` | 真实 caller CFG、depth<=2 call-site context、参数/返回 identity、静态字段/executor identity、lambda capture、TPE 契约、task AST CFG/annotated 多出口与成功出边 callback release 已完成源码验收；partial/unsupported/缺 CFG release 不执行负效应并保留 gap。完整真实、定向真实与最终 adapter 回放按上文分层记录；不将此门槛外推为 G3–G8 通过。 |
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
