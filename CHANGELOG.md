## [2026-09-10] Resource lifecycle v1.1 Task 4 review fixes

- I1：任务 phase 移到独立控制 cursor；工作列表不再合并不同已执行边集合的 trace，保留一条真实交错 witness。输出按 task/phase/path 保存独立 `AsyncDerivation`，每条 proof 绑定真实 source/target/transition 与自身状态；便捷 submitted/completed 只聚合资源状态，不携带混合 phase 或全阶段共享证明。
- I2：adapter 按同批 base CFG 的 submit operation outcome 标记 success/exceptional continuation，solver 要求匹配 TaskBinding 与 `cfg_fact`。缺证据 scoped unknown，成功接纳后取消不阻塞 caller；匹配 instance/holder/contract/queued-or-run target 的 caller dispatch 只保留 evidence，不重复 capture，任何 identity mismatch 仍 unknown。QL 未修改。
- I3/I4：全部 caller exit 合并后仅生成一次 all-tasks 条件维度，并拒绝重复 DimensionResult identity；条件 evidence/transition/location 来自对应 property trace。evidence registry 使用独立 `evidence_kind` 与完整 claims，保留同源多 context / create-retain-drop claims，拒绝来源位置、primitive、同 claim identity 或 exit kind 冲突。公共 serializer 完整保存 solver cuts、阶段 trace/origin/derivation 与终止保证字段。
- 验证：初始有效 RED 为 8 failed，matching dispatch 单项另为 1 failed；扩展 claim identity 反例亦取得有效 RED。最终 review `17 passed`，含真实缓存回放 focused `155 passed, 156 subtests`，全 lifecycle `323 passed, 13 skipped, 235 subtests`；compileall 与 diff-check 通过。一次扩展测试误要求清除业务 field，修正为检查 task holder，不算生产缺陷。
- 同批真实 SourcePairs raw facts 经当前 adapter 重新构造完整 4 units 并 validate，原 raw/snapshot/coverage 保持不变；当前默认预算 caller 为 827 steps、terminated=true，真实 facts→CLI→replay 通过。未重跑 QL，不将首轮 query 时的 solver/adapter 版本冒充最终实现；原有 source coverage gaps 和缺失 reject continuation 仍显式 unknown。G3 保持 pending fresh review / fail，整体 partial；Task 5 未启动、不 push，P0 2.5/0.4.0 与三态限制不变。

## [2026-09-10] Resource lifecycle v1.1 Task 4 main solver（首轮历史）

- fresh review 重新打开 G3：I1 phase/trace 投影、I2 caller accept/reject CFG 对应、I3 条件维度 identity 重复、I4 evidence 类型/冲突/出口依赖与公共 serializer 不完整。当前回退 fail/in_progress；先保存逐项有效 RED，再修复，不以既有 GREEN 覆盖 review 反例。
- G3 主求解异步接通：唯一、同 callable 的 `source_submit_binding` 接入 caller/task 控制位置乘积工作列表；排队/直接接纳才 capture，reserved→running 不重复 capture，真实 callback CFG effect 与 TaskExit 之后的 task holder drop 使用共享状态操作。request return 不结束 task，close 不删除 field 引用；重复 task context 保持独立。
- `exit_states` 保留 request 出口语义；新增 `property_states/property_traces` 明确记录 task normal/exception、拒绝/取消及 request 返回后已提交任务均终止的条件切面。对应 DimensionResult 使用 `after_task_termination:<task_id>:<kind>` 等 scope；缺调度/终止、取消或拒绝回接证据时整体维度按捕获资源族输出 unknown。`_async_stages` 只序列化主求解保存状态，不再执行完成/取消语义；legacy 无 TaskBinding 只保留 conservative capture，后继为 null，不能由 executor termination 标志推导 callback close。
- 有效 RED：主状态 6 failed、connector 结构 5 failed。源码 SourcePairs 真实双 query→adapter→默认预算 solver 为 1 passed（267.53s），caller 327 steps；normal/exception 两出口关闭义务归零，删除已有 release 后重新为 1。该 fixture 自有 coverage gap，因此条件维度仍 unknown，不算 G4 通过。人工完整 Program 验证关闭维度 bounded→obligation_gap、额外 field holder 和拒绝分支差异；已完成真实缓存 facts→CLI→replay。
- G1–G3 pass，G4–G8 fail，整体 partial；Task 5 群体归纳证明未实现。每控制配置更新超限命名为 `iteration_limit`，不再假称 widening。P0 schema/tool 2.5/0.4.0、三态与异步 Release 限制不变；本轮不 push。
- 最终 Task4 定向 `138 passed, 156 subtests`、全 lifecycle `306 passed, 13 skipped, 235 subtests`，均包含真实 SourcePairs 完整 facts→CLI→replay；`compileall`、`git diff --check` 通过。首次真实查询验收为 1 passed；最终 solver 修改由该同批 facts 回放覆盖，没有声称最后实现后重新运行整套真实 query。

## [2026-09-10] Resource lifecycle v1.1 Task 3 source relations follow-up

- V4 最终关闭 G2/Task 3：fresh quality `Ready: Yes`、Critical/Important/Minor 均无，fresh spec `Spec compliant`。最终非 fixture `285 passed, 13 skipped, 235 subtests passed in 4.79s`；冻结批次既有四项真实全部通过，唯一新测试错误分层记录如下。仅改出口 evidence 集合断言后，RepeatedSubmit 四形态真实 Java→双 query→最终 adapter 为 `1 passed, 18 deselected in 267.94s`（`/tmp/task3-v4-final-repeated.xml`）；两次最终真实运行间 production/fixture 未变。depth1/depth2/mixed/same-depth-prefix 为 2/2/4/4 tasks，stage/holder/invariant/exit/CFG/population 归属保持独立且共享 executor。最终 `compileall`、两对 QL `cmp`、`git diff --check` 通过；整体仍 `partial`，G3–G8 未完成，Task 4 与 push 不启动。
- `12e297e` 后 fresh quality review 重新打开 G2（I1–I4）：重复 submit 的 task 身份冲突、上下文深度/预算缺口、adapter 源码读取期间 TOCTOU、related-location provenance 未完整绑定。STATUS 回退 `fail / in_progress`，逐项 TDD 修复，Task 4 与 push 继续暂停；以下 GREEN 属此前里程碑。
- I3/I4 修复：恢复 adapter 完成后的源码快照复核，失败必须在 facts/coverage publication 前 fatal；related SourceLocation 全字段纳入 current fact identity，并对主/related 两位置统一检查 static source kind 与 extractor。故障注入和重建 derived/snapshot 后的四种 related 篡改取得有效 RED `5 failed`（均为未拒绝），legacy 1.0 仍按旧 identity 校验后迁移，不接受篡改的 v1.1。
- I1/I2 修复：task-query queued stage/capture holder 按 instance+submit point+callable 隔离，TaskExit 与 callback attached effect 纳入 task_id，executor contract 继续共享；重复 submit 的有效内存 RED 为两种 identity 异常，真实 Java 双 query→adapter 已通过 `1 passed in 272.66s`（最终回归仍待）。call context 展开严格匹配声明 depth-1 前缀，缺失关系不生成 CallBinding、保留 scoped gap；超深上下文不借用浅层证据，CFG/effect/submit 附着同步检查 depth。每 unit context/expanded binding 上限 4096，超限 fatal 而非依 hash 顺序截断。depth3/缺失前缀/超预算有效 RED `3 failed, 1 passed`，合并 GREEN `65 passed, 13 skipped, 46 subtests passed`。
- Minor：正式 source CFG 不再构造随后丢弃的 fallback path effects/base relation transitions；定向 RED 记录仅需 3 个 effect 却构造 9 个，修复后仅构造实际 CFG effect。
- V3 冻结真实回归完成：`5 passed, 74 deselected, 11 subtests passed in 1215.62s`（`/tmp/task3-v3-final-real.xml`）。独立 quality 再审仍为 No：同一 submit 在不同 call context 下碰撞，G2 不关闭。V4 将完整前缀展开前移至 task dispatch/invariant normalization：task/holder/queue scope/invariant/TaskExit/CFG/population 按 context 隔离，shared executor 不拆分；任务 body 只消费本 dispatch depth 与 entry 的证据。depth1/2 单独正控通过，mixed-depth、same-depth 两前缀、错 depth body 与 task-context 乘积预算取得有效 RED `4 failed, 2 passed`；新离线定向 GREEN `18 passed`。旧 synthetic helper 把 depth2 dispatch 的 body 错写成 depth0，已同步到真实 QL depth 合同，不放宽 production gate。最终 V4 真实验收与质量复审仍待。
- V4 fresh quality 最终 `Ready: Yes`（Critical/Important/Minor 均无），fresh spec `Spec compliant`；独立非 fixture `285 passed, 13 skipped, 235 subtests passed`。冻结真实五项批次为 `1 failed, 4 passed, 80 deselected, 11 subtests passed in 1220.24s`（`/tmp/task3-v4-final-real.xml`）：唯一失败是新测试硬猜每 task 三个出口，而此空 close fixture 的 raw query 实为一个出口，不是生产缺陷 RED。仅将该测试改为逐 task 按 raw instance/depth/entry/target 的完整出口 evidence 集合精确比对，production/fixture 未改；单项真实补验与最终检查仍待。
- V2 follow-up 完成并通过 fresh spec rereview3（`Spec compliant`）：G2 `pass`、Task 3 complete，整体仍 `partial`，G3–G8 未完成，Task 4 仅 next。Task QL SHA `19b78920abd44927b627d29b1ea9e726cb38c9a38e1654a44122de59ae33cbae`；depth=2 overwrite、独立 callback effect gap、间接 unsupported task 的真实 query RED 为 14 条失败，修复后 0 失败（115→102 rows）。field-initializer executor alias 是额外显式加固，旧查询已能保守覆盖该 fixture，不计作旧缺陷 RED。最后 owner 修复前完整 suite 为 `65 passed, 1 failed, 58 subtests passed`，唯一失败是新测试不应要求完整建模的拒绝 capture unit 必有 gap；最终受影响双 query→adapter 为 `2 passed, 11 subtests passed in 531.24s`，最终非 fixture 为 `267 passed, 12 skipped, 235 subtests passed`。QL cmp、`compileall`、`git diff --check` 通过。nested task depth>1/capture/local-alias propagation 仍 unsupported，gap 完整覆盖未获证明；不 push、不进入 Task 4。
- `d2311f6` 后 fresh spec 复审重新打开 G2：depth=2 overwrite task 错绑、exact close 遮住 field escape gap、间接 unsupported callback 静默、executor field-initializer alias mutation 漏检四项尚未关闭。STATUS 回退 `fail / in_progress`，Task 4 与 push 继续不启动；以下完成/验收数据保留为先前里程碑，不覆盖本次反例。
- adapter 新增独立跨 query capture 校验：非 root task dispatch 必须有同 instance/callee/depth 的完整 base CallBinding 链和受支持的 task argument slot；缺失、断开、partial 或 slot 错位时不创建 TaskBinding、不执行 task release/population，raw 事实保留并发布三维 `task_capture_call_binding_unverified` gap。`dispatch.binding_index=0` 表示 execute 任务槽，不冒充被捕获 callee 参数位置，非零 callee 参数位置另有正控。链校验 RED 为 `4 failed, 1 passed, 13 subtests passed`；新增 callback gap related-point callable 归属的有效合成 RED 为 `1 failed`（将 lambda 效应点错归 caller），实际 body effect 现按该类静态 evidence 与 canonical site 的 target callable 记录。合并 focused GREEN 为 `1 passed, 18 subtests passed`，同时验证 exact close 与独立 callback escape gap 可共存。
- fresh spec 复审继续发现 fallback `effect=lambda` AST 应归 enclosing wrapper，而非生成的 lambda body；合成 RED 为 `1 failed, 4 subtests passed`，现依据 canonical related body-site identity 限定 target 归属，fallback 保留 source callable，focused GREEN 为 `1 passed, 18 subtests passed`。V2 完整真实 suite 在此修复前为 `1 failed, 65 passed, 58 subtests passed in 2172.11s`：唯一失败是新测试误要求已拒绝 replacement capture 的完整建模 unit 必有 gap，现替换为“原 allocation obligation 在出口仍存、无 task/release/population”状态断言，不算生产修复；最终 fresh-review/TaskTerminals 双 query adapter 复验已通过，见本节首条。
- G2 源码关系验收关闭，Task 3 完成；整体仍为 `partial`，G3–G8 未完成，本次不启动 Task 4、不 push。最后 base gate 修复前完整真实套件为 `62 passed, 45 subtests passed in 1829.42s`；base gate 修复后受影响 wrapper/source-state 为 `2 passed, 5 subtests passed in 275.32s`。该真实进程在最后无 CFG fallback 修复前已加载 adapter；最终 fallback 另由 `267 passed, 11 skipped, 229 subtests passed` 的非 fixture 集与最终 adapter 的 35-unit 真实 facts 回放复验。14 条 partial release 均无负效应，三个 alias 保持 obligation，sync close 与 queue 上界 2/3 保持。两对 QL 字节一致、`compileall` 与 `git diff --check` 通过。
- 缺 caller CFG 的 formal source fallback 反例补获三种 coverage 的入边 release（RED：`3 failed, 1 passed`）；现 real-source fallback 不附 release，synthetic partial/unsupported 同样不附，只保留 synthetic complete 的既有导入测试语义。complete 缺 CFG release 保留 `unverified_base_release` 与 `callable_cfg_unavailable` gap，不能因子图断开而容忍错误负效应。定向 GREEN：`7 passed, 7 subtests passed`。
- 最终状态审查发现 base CFG 对 partial/unsupported alias/parameter release 仍执行强负效应；真实 cached `conditionalAlias` 显示 obligation 1→0，状态级 RED 为 `4 failed, 1 passed, 1 subtests passed`。现仅允许 complete singleton-finally exact-local contract、exact recent instance 与实际成功 CFG 边执行 base release；其余保留 raw/ProgramPoint/evidence/scoped coverage gap，不附负效应，不用全局 unknown condition 污染独立容量维度。此 gate 修复未改 QL，最终复验见本节首条。
- 冻结 task QL 后，callback release 只按 exact source+related PP/location/depth 与可信 normal-success CFG 证据附着；terminal close 经 `#normal-success:call-cfg-v1` continuation，success 后 normal/exceptional task exits 与 close 自身异常严格分流，不再直接在 TaskExit 上释放。同类多出口保留，synthetic identity/CFG/terminal provenance 伪造反例均拒绝负向效应。focused 为 `1 passed, 12 subtests passed`；SourcePairs/TaskCfgCoverage/TaskTerminals 真实双查询定向为 `3 passed, 7 subtests passed in 625.75s`。以下早期 follow-up 中的入边 release／显式 return-throw terminal 描述是已被审计否决的历史状态，不是当前接口。
- CFG operation outcome 仅按 source 的第一条 normal/exceptional successor 分类；后续 synthetic finally bridge 恢复 pending exception 不再被误读为当前操作失败。有限 call continuation 同样按当前调用 outcome 选择 callee exit，最终 callable exceptional exit 与调用自身抛异常分开。真实 rows 已恢复同步 close 的 bounded 结果；wrapper finally/pending-exception 源码定向为 `1 passed, 60 deselected in 198.12s`，最终全套仍待运行。
- first-step 分类额外保留 Return/Break/Continue 等非 ExceptionSuccessor 的 abrupt transfer，避免有返回值函数在 return 点断尾；source Program 的出口集合跟随实际 annotated exit，不为 normal-only callable 虚构 exceptional 出口。完全缺少出口证据时仍保留不可达出口并由既有检查报告 unknown，不能得到空出口的虚假 bounded。
- finalizer 复核发现旧 follow-up 仍有断开的 call/CFG 子图、顶层源码位置执行序与 target location 错配；新增 callable entry/逐步 CFG/annotated exit、parameter-entry 与 caller continuation 连接，真实源码通过 CFG 执行效应，缺少 CFG 时显式 `callable_cfg_unavailable`。callee 事件以资源实例隔离，static field/executor identity 跨 callable 共享。G2 与 current_stage 保持 `fail / in_progress`，尚未完成最终真实查询与独立复审，不开始 Task 4。
- task adapter 不再要求恰好一 normal/exceptional 出口，保留单出口和同类多个不同程序点；重复出口点、跨 task/callable/event 附着仍被拒绝。callback release 只接受明确 complete 来源契约并附在成功调用出边，伪造 release RED 修复后定向为 `1 passed, 4 subtests passed`。TPE 接受合法 core=0，直接接纳守卫补齐队列已满且 a<W 的非 core worker 分支；未验证 cancellation/termination 继续不生成计数转移。
- follow-up：Task CFG callback release 现只接受 caller allocation -> depth<=2 exact wrapper parameter -> lambda capture -> static-final AbortPolicy executor -> lambda 内单语句 `finally { captured.close(); }` 的完整 source chain。task query 以 close statement program point 输出同 instance/lambda 的 complete `release`（normal/exceptional 均为 true），adapter 仅在该真实 release point 是同 task CFG edge target 时附着 `release` effect，禁止从 executor completion/termination 推导。SourcePairs 真实 RED 为缺少 release 的 `StopIteration`，GREEN 为 `1 passed, 60 deselected`（263.75s）；同数据库 direct Base/Task query run 分别为 2m20.92s 与 1m58.66s（eval 550ms/565ms）。G2 仍为 `fail / in_progress`，未因该局部事实改写状态。
- follow-up：Task 3 G2 仍为 `fail / in_progress`；为五种尚未建模的 task/executor 形式新增 caller-bound `unknown_call` gap：`submit(Callable)`（含 `Future.cancel`）、anonymous `Runnable`、method reference、local executor alias 和 local resource capture 一律以 `unsupported` coverage 输出，不得伪造 dispatch/invariant/task exit/callback release。真实 Java 回归逐项验证 `depth=1`/`binding_index=0`/submit-site identity。
- follow-up：static-final JDK `ThreadPoolExecutor.execute` 的 source contract 现明确提取 core/max workers、ArrayBlockingQueue capacity 与 rejection policy；AbortPolicy 仅标示 rejection drops capture，completion 不标示 release，cancellation/termination 仍为 unknown。
- follow-up：task CFG 不再只挑 entry/terminal/method call 而丢失 Try/If/finally AST 节点；同 lambda callable 的 Expr/Stmt 均有 stable program point，边只走到下一个 AST CFG node（可递归穿越 non-AST synthetic node）。SourcePairs 真实回归固定 `try -> try-block -> if` 与 `finally-block -> close` 的逐步 edge，未恢复 `getASuccessor+()`。
- follow-up：task terminal 只把未被 enclosing `try`/`catch` 截获的显式 `throw` 作为 exceptional exit；caught throw、implicit normal 和调用点异常继续由 `partial/task_terminal_coverage_incomplete` 覆盖缺口，不能伪造 complete terminal coverage。
- follow-up：depth<=2 的 exact parameter summary 补出 `return parameter` ownership escape，作为 `partial/returned_resource_ownership_unmodeled` 的 caller-bound `unknown_call`，不把 wrapper 返回误判成 release 或无副作用。
- follow-up：wrapper parameter -> field effect 现在只对 static field 发出带 `#static` 的 exact global holder identity；instance field 保留 field 名，但 receiver identity 明确标为 `partial/field_receiver_identity_unresolved`，避免把未知 receiver 误写成精确持有。
- follow-up：真实 wrapper 回归把 instance-field 断言限定在 `holder_kind=field`，不再把 caller local initializer 的独立 retain 行误当成 field receiver 证据。
- follow-up：base query 的 wrapper summary CFG 关系改为标准库等价的单步 `getASuccessor()` non-AST bridge；只穿越没有 AST identity 的 synthetic CFG node，绝不跨越第二个 AST program point，以准确连接 field retain、`close()` release 与 `return` effect target。
- follow-up：`ResourceLifecycleFacts` 把递归 `rootCallBinding` 关系携带的真实 target `Parameter` 位置移至 `resourceLifecycleRow` 投影；保留精确 related source location，避免位置三元组进入递归关系导致 CodeQL optimizer 放大。相同 `SourcePairs` 数据库上，改前完整 base query 为 compile `1m55s` / eval `494ms` / total `1m58.15s`，改后为 compile `1m5s` / eval `578ms` / total `1m08.79s`；解码 BQRS 逐字一致。
- follow-up：task CFG relation 改为 `ControlFlowNode.getASuccessor()` 的直接边，移除传递闭包 `getASuccessor+()`；新增结构回归先失败后通过，direct/embedded task query 的 `compile --check-only` 均通过。G2 仍为 `fail / in_progress`：终止精度、cancel/reject 契约、unsupported task/executor 形式与纵向验收尚未关闭。
- 完成 Task 3 的真实 Java/CodeQL 双查询提取：基础 `ResourceLifecycleFacts` 只负责 allocation/lifecycle、stable program point、depth<=2 exact call binding 与 depth coverage gap；新增 `ResourceLifecycleTaskRelations` 独立负责 lambda capture、静态 `ThreadPoolExecutor` 配置、task CFG、normal/exceptional exit 与 task partial facts。direct/embedded query 保持字节一致，runner 以 anchored family matcher 区分两者；最终两份 query `compile --check-only` 均为 `Done [1/1]`，独立完整执行分别约 `2m50.15s` 与 `4m06.22s`，均低于单 query 300 秒上限。
- formal `codeql_database` extraction 固定按 ordered suite 先执行完两份 query，再 decode/merge/publish；任一 selected query 失败时不调用 adapter、不发布 `facts.json`/`coverage.json`。每条 raw fact 保存 query name/SHA，fact identity 纳入 row origin；coverage 固化 ordered query/BQRS digests、suite SHA、database fingerprint、source snapshot 与聚合 provenance SHA，并在 load/validation 时复核。跨 query duplicate semantic row、orphan instance、unknown base unit、dangling task relation 均 fail closed，且只有 task-query dispatch 能满足 task relation 绑定；legacy schema `1.0` 继续先拒绝夹带 v1.1 relation semantics，再按旧单-query identity/ID/snapshot/derived-unit 合同迁移。
- adapter 现从真实 rows 组合 `ProgramPoint`、`CallBinding`、`TaskBinding`、`TaskExit`、七个 task-stage event、task method CFG/transitions 与八类原子 `PopulationEffect`，不会把 callback 折叠成 caller 原子效果。新增 `SourcePairs.java` fixture 覆盖 caller -> wrapper1 -> wrapper2、lambda capture、`W=2/K=3/AbortPolicy`、显式 return/throw 与 finally close。双查询/provenance RED 为 `8 failed, 37 deselected`，GREEN 为 `8 passed, 37 deselected, 9 subtests passed`；最终真实组合 fixture 为 `1 passed, 45 deselected`（436.13s）。另补 partial `cfg_edge/task_exit` 的 relation-only coverage 回归，RED 为 `2 subtests failed`，GREEN 为 `1 passed, 2 subtests passed`；最终 lifecycle 为 `253 passed, 6 skipped, 205 subtests passed`。P0 schema/tool 保持 `2.5/0.4.0`，resource lifecycle 保持 `1.1/resource-lifecycle-v1.1`，Task 4 solver 未提前实现。

## [2026-09-09] Resource lifecycle v1.1 execution started

- 关闭 Task 2 population attachment 复审缺口：`TaskBinding` 现显式拥有 submit/queued/run/normal/exceptional/rejected/cancelled 七个 stage event，新增 `task_reject`/`task_cancel` event kind，拒绝跨 binding 复用任一 stage event；submit callable 可保留 caller，其余 stage 必须绑定 task callable。八类 `PopulationEffect` 均按 source/target/exit-kind 精确三元组校验，`terminate`/`cancel_active` 额外允许从 run 经同 task callable、`exit_kind=internal` 的真实 `Program.transitions` CFG 可达 method event 发出，断开或跨 callable 的伪内部节点 fail closed。`io.py` 的 `1.0/1.1` Program/Transition exact field sets 改为显式不可变集合，不再从 dataclass 动态推导；旧 `1.0` 不迁移不存在的 TaskBinding 字段。定向 RED 为 `6 failed, 1 passed`，核心 GREEN 为 `7 passed, 34 subtests passed`，相邻 schema GREEN 为 `4 passed, 13 subtests passed`；最终 lifecycle 为 `244 passed, 5 skipped, 194 subtests passed`，真实 CodeQL 为 `36 passed, 16 subtests passed`。P0 schema/tool 保持 `2.5/0.4.0`，未实现 Task 4 solver。
- 关闭 Task 2 code-quality review 的五个 Important：`TaskBinding` 四阶段 event callable、`TaskExit` 与八类 `PopulationEffect` 现按 task/phase/transition endpoint 精确绑定；executor dispatch 改为消费 `termination`/`rejection_policy`，boolean 与 enum 冲突 fail closed，旧 `1.0` completion boolean 只迁移可证明的 termination，旧 rejection boolean 不再虚构 policy；manual fixture 的 ProgramPoint/PopulationEffect provenance 在 manifest adapter 与 artifact validator 两个入口均限定为 `manual_fixture`；双份 lifecycle QL 的 program-point identity 改为 callable + file + 完整 start/end span，不再包含 fact kind，同一 queue submission 的 dispatch/invariant 共享 site identity；Program/Transition 以集中式 `1.0/1.1` exact field sets 解析，`1.1 coverage_gaps` 必填，`1.0` 即使携带空 relation/population 字段也拒绝，迁移只在精确旧 schema 后补新增空集合并保留旧 coverage evidence。最终 lifecycle 为 `232 passed, 5 skipped, 128 subtests passed`，真实 CodeQL compile/query/CLI 为 `36 passed, 16 subtests passed`；双份 QL `cmp` 与相关 diff-check 通过，P0 schema/tool 保持 `2.5/0.4.0`。
- 关闭 Task 2 第三次 spec 复审的 executor contract schema 漏洞：facts loader 现在把外层 schema 显式传入 contract parser；schema `1.1` 必须精确包含 `max_workers`、`rejection_policy`、`termination`，删除任一字段均 fail closed，只有外层 facts `1.0` 才接受精确旧字段集并补 `None/unknown/unknown`。manual extraction manifest 与 facts artifact 的兼容版本边界保持分离，其 contract 继续默认按 current `1.1` 严格解析。table-driven 有效 RED 为 `3 failed, 2 passed`，定向 GREEN 为 `2 passed, 3 subtests passed`；最终 lifecycle 为 `215 passed, 4 skipped, 61 subtests passed`，真实 CodeQL 为 `33 passed, 15 subtests passed`；`compileall`、双份 QL `cmp`、`git diff --check` 与 P0 `2.5/0.4.0` 固定检查均通过。
- 关闭 Task 2 第二次 spec 复审的两个版本边界缺口：真实旧 `1.0` `create + dispatch(capacity=2)` facts 现在先用旧 executor contract identity（不含 `max_workers/rejection_policy`）严格核对 raw-derived units，再重建当前 `1.1` identity，既不跳过旧工件一致性验证，也不错误地用新 ID 拒绝合法旧工件；schema `1.1` Program 不再为缺失的 `program_points`、`call_bindings`、`task_bindings`、`task_exits` 或 transition `population_effects` 自动补空，外层 facts `1.1` 也拒绝 nested Program `1.0`，所有缺省升级只绑定 schema `1.0`。legacy migration RED 为 `1 failed`，严格 parser RED 为 `6 failed, 1 passed`；定向 GREEN 为 `3 passed, 5 subtests passed`，最终 lifecycle 为 `214 passed, 4 skipped, 58 subtests passed`，真实 CodeQL 为 `32 passed, 12 subtests passed`；`compileall`、双份 QL `cmp`、`git diff --check` 与 P0 `2.5/0.4.0` 固定检查均通过。
- 修复 Task 2 spec review 的四个 fail-closed 缺口：外层 facts schema `1.0` 现在拒绝嵌套 1.1 relation/population/executor semantics，真实旧 raw facts 缺少七个 relation/config 字段时以确定性 conservative defaults 重建，并先核对旧 fact ID、snapshot 与 derived units，再归一化为当前 ID/snapshot/units；executor numeric-string limit 与整数走同一正数规则，bool 继续拒绝、非数值 symbolic 保持支持；ProgramPoint/CallBinding/TaskBinding/TaskExit 的 relation ID 改为跨类型全局唯一，普通 Effect ID 不受影响；recorded-summary private snapshot 与 validation artifact 新输出统一 schema `1.1`，旧 named-v1 recording 仅由既有 exact-field/typed loader 受限读取。四项 RED 分别为 `2 failed`、`4 failed, 1 passed, 2 subtests passed`、`1 failed`、`1 failed`，定向 GREEN 为 `5 passed, 6 subtests passed`；最终 lifecycle 为 `209 passed, 4 skipped, 48 subtests passed`，真实 CodeQL 为 `31 passed, 12 subtests passed`。
- 完成 Task 2 relation/population IR：resource lifecycle `Program` 与 facts artifact 升为 schema `1.1`（P0 schema/tool `2.5/0.4.0` 不变），新增 immutable `TaskExit` 并把 normal/exceptional task terminal 与 task、program point、event、callable 精确绑定；全局拒绝重复 relation/population identity、dangling point/task/executor/callable、depth>2、未知 relation/population kind、非正容量/worker 数和 `llm_proposed` relation source。`PopulationEffect` 继续原子附着于 `Transition`，并校验其 executor 必须等于对应 `TaskBinding` 的 executor contract；`AnalysisUnit` 再验证 contract 实体存在。
- `ExecutorContract` 现 round-trip 保存 `max_workers`、`rejection_policy` 与显式 `termination`，连同既有 queue capacity/rejection/cancellation 语义；旧 `1.0` Program/facts 读取时仅升级 lifecycle schema 并为空 relation 集补缺省，不修改 P0 工件。严格 loader 不再把 relation/population evidence 的非字符串值静默 `str()` 化。`facts.json`/snapshot、results、evidence、run manifest、replay 与 evaluation 输出现统一为 schema `1.1`，resource tool identity 升为 `resource-lifecycle-v1.1`；外层 extraction manifest 继续接受 `1.0`/`1.1`，但 replay 只接受当前 tool/schema identity。统一工件 RED 为 `1 failed, 21 deselected`，修复后 `1 passed`。
- 修复 v1.1 raw fact identity 回归：生成 ID 已纳入 `site_callable/program_point/related_point/relation_depth/binding_index/max_workers/rejection_policy`，validation 重算现使用完全相同的 semantic payload；修复前 CodeQL+recorded-LLM 为 `33 failed, 38 passed, 4 skipped`，修复后为 `62 passed, 4 skipped, 23 subtests passed`。Task 2 schema RED 为 `4 failed, 44 deselected`，最终严格筛选为 `8 passed, 44 deselected, 2 subtests passed`，三文件非 Fixture GREEN 为 `77 passed, 4 deselected, 13 subtests passed`，lifecycle 全量为 `202 passed, 4 skipped, 36 subtests passed`。
- 额外真实 CodeQL 自审先暴露新增 `programPointIdentity(Expr,string)` 缺 input binding set，四个 fixture 同源报 query compile failure；为 helper 声明 `bindingset[site, factKind]` 后 query compile `Done [1/1]`，真实 source→CodeQL→adapter/CLI 验收为 `30 passed, 12 subtests passed`，双份 QL 保持字节一致。
- 真实源码关系提取先固定 strict decoder RED，初始为 `1 failed`：lifecycle row 必须携带 actual site callable、stable program point、related point、depth≤2 binding position、max workers 与 rejection policy。decoder/raw fact 现严格验证新列与 relation enums；双份 QL 先为现有 effect 输出 AST callable/location 构成的稳定 program point 和 conservative relation/config sentinel，旧 bare synthetic rows 仅在 adapter 测试入口补受限 legacy defaults，真实 decoded CodeQL rows 不允许缺列。
- Executor contract schema RED 要求显式保存 positive/symbolic/unknown `max_workers` 和具体 rejection policy，初始为 `1 failed`（字段缺失）；`ExecutorContract` 现严格接受正整数/符号/unknown worker limit 及 `abort|caller_runs|discard|discard_oldest|unknown`，拒绝零 worker 或虚构策略，facts loader 对旧缺省字段安全降级为 unknown。这是后续从真实 TPE 配置推导 `a<=W` 与拒绝分支的前提。
- 阶段 B schema RED 固定 `ProgramPoint`、depth≤2 `CallBinding`、resource `TaskBinding` 与带 q/a delta/phase 的 `PopulationEffect` 严格 round-trip；初始为 `2 failed`（缺少类型）。现有 `Program`/`Transition` 增量保存并严格验证这些关系，拒绝 unsupported point/depth、dangling point/event/instance/task/holder 和不符合操作语义的 q/a delta；`io.py` 提供精确 JSON round-trip，同时对旧 transition/program 中缺少新增可选关系字段的输入保持安全空集合默认。
- 阶段 A 先加入精确双实例 release、重复/alias release、多 holder、重复/不存在 drop、分支部分 release 与 summary 弱更新的实例/族计数联合断言；旧 solver 定向结果为 `3 failed, 2 passed`，扩展 per-instance 断言后为 `5 failed`。`ResourceState` 现显式维护 per-instance obligation interval：精确 release 只递减仍 open 的目标实例并立即更新该实例状态，重复/alias release 为 no-op；drop 只有实际删除目标实例最后一条 holder edge 才递减族 held count，分支 join 同步合并实例/族区间，summary 继续弱更新。
- 从已审阅 `f62d6f2343d160a320dbb7aaec6d22c307d892f0` 创建隔离分支 `codex/resource-lifecycle-v1_1-20260908`，新增 `docs/execution/lifecycle-v1.1/STATUS.md` 与逐门槛实施计划；P0 schema/tool `2.5/0.4.0`、静态三态语义和 preserved assets 约束保持不变。
- 固定实现前证据：全仓为 `101 failed, 797 passed, 26 skipped, 389 subtests passed`，失败来自隔离 worktree 缺 ignored 大型资产和沙箱 socket `EPERM`；lifecycle 专项为 `179 passed, 4 skipped, 34 subtests passed`；启用真实 CodeQL 后为 `27 passed, 10 subtests passed`（CodeQL 2.23.8 / javac 21.0.12.1）。最终按 test ID 比较，不以同一失败总数代替回归审计。

## [2026-09-08] Resource lifecycle v1 async production closure

- 最终验收：生命周期自包含 `179 passed, 4 skipped, 34 subtests passed`；真实 javac/CodeQL `27 passed, 10 subtests passed`；旧 P0 release `14 passed, 24 subtests passed`；compileall、双份 QL cmp、diff-check 全部 exit 0。固定 suite SHA `8506931faf8971684931102d1c41e7f91a4f32e533a183d24477706c93334411`，报告 full 24/24、CSV 144 data rows且无 private/credential 命中。全仓为 `101 failed, 797 passed, 26 skipped, 389 subtests passed`，101 个失败与开工基线同数，fresh traceback 仍是隔离 worktree 缺 ignored `results/frameworks` 资产与 sandbox socket `EPERM`；未降低断言或跳过语义路径。
- 完成 M6 双重终审与交接文档：spec/soundness 与 code-quality reviewer 对最终 source snapshot、call column、exact callee、effect 去重、artifact lock、单-fd replay、0600 私有文件和 audit-only 口径均给出 `Ready`，Critical/Important 为 0；`docs/execution/HANDOFF.md` 记录 M0–M6 交付、最终验证、报告哈希、明确未支持边界及四项非阻塞 Minor，最终 Git SHA 由远端分支引用记录而不写入该提交自身。
- 关闭同一 run directory 的跨进程 publication race：新增 owner-owned、0600、single-link regular lock file，使用 `O_NOFOLLOW`/`O_CLOEXEC` 打开并以 bounded non-blocking `flock` 轮询；`resource-analyze` 在 managed artifact preflight 与完整发布期间持锁，`resource-replay` 从首个 artifact 读取、重算直到 `replay.json` 发布全程持锁，锁文件不进入公开报告。replay 的 facts、private recording 与 private summaries 改为同一 bounded file descriptor 上读取 JSON bytes、计算 SHA-256 并解析，private snapshot 同时校验 owner/0600/single-link，消除 follow-symlink、无界 hash 与 lstat→hash→reopen TOCTOU。新增并发确定性交错、unsafe lock/input 与 single-snapshot hash RED→GREEN；当前九个 lifecycle 文件为 `179 passed, 4 skipped, 34 subtests passed`，未运行真实 CodeQL、PoC、probe、动态 DoS 或目标服务。
- 修复 `resource-analyze --out` 复用时的 artifact hygiene：analyze 先完成 facts/recording/summary/result/evidence 的内存构造，再进入单一发布边界；边界只识别固定 managed artifact 名单，发布前验证既有路径均为 non-symlink regular file，并仅删除当前 mode 不适用的 `llm-recording.private.json`、`llm-summaries.json` 与旧 `replay.json`。replay→off、off→replay 均不再混入私有源码 snapshot 或旧 consistency 声明，未知用户文件保持原样；symlink、目录等陷阱在任何现有 run artifact 被改写前 fail closed。新增双向复用与 unsafe path RED→GREEN 回归；当前九个 lifecycle 文件为 `173 passed, 4 skipped, 24 subtests passed`，未运行真实 CodeQL、PoC、probe、动态 DoS 或目标服务。
- 修复 recorded positive effect 重复执行：apply 层以完整 operation identity 对比 caller program 已存在的 static Effect，proposal 若只是复述相同 create/retain/dispatch 则记录 `llm_proposed_effect_already_static`、保留 verified/display provenance，但不再插入 transition，避免 create 重复计数或 dispatch 重复建 stage。当前 QL 没有独立于 caller executable Effect 的 callee-summary witness，因此 production replay 是 audit/display-only、不会增强 solver；未来只有新增独立 static witness 且 operation 尚未执行时，正向 may-effect 才具备进入状态的接口。
- 补齐 replay publication 完整性：以有界、`O_NOFOLLOW` 的 UTF-8 reader 重算 `summary.md` 并把 `summary_markdown_consistent` 纳入总一致性；私有 recording/summary snapshot replay 前必须是有界 0600 regular file，权限放宽、symlink 或非 regular input 均 fail closed。相关反例均为 RED→GREEN。
- 增加 field-save holder-kind 反例并把 caller Program 的精确 field holder 集接入 Summary FactIndex：proposal 把 local/request-stack retain 声称为 field save 时以 `field_save_holder_kind_unresolved` 拒绝进入 usable effects，不能只因 holder ID 相等就通过参数层。
- 收紧 SourceLocation 类型边界：`start_line`/`end_line` 必须是严格正整数，拒绝可比较但不可作为源码坐标的 float/bool；新增四个 RED→GREEN 子用例。
- 增加 recorded summary evidence 完整性反例并修复 evidence builder：summary derivation 与 proof dependencies 现对 effect 容器及其 evidence 容器同时兼容内存 tuple 与重放 JSON array，一致收集 proposal 各 normal/exceptional effect 自身引用的 static evidence，同时继续记录顶层声明与 unknown trigger，避免 usable effect 的支持事实从证据图消失。
- 增加 source interface 多实现 dispatch 反例：仅 canonical declaration identity 不足以授权 recorded summary；static/private/final method 或 final declaring type等可证明唯一的 source callee 才允许进入摘要 eligibility，普通虚调用保留 `source_callee_dispatch_target_unresolved`，不可被 recording 注入效应。
- 增加同行多语句 recorded-summary 反例并贯通双份 QL、strict decoder、raw fact identity、serialization/rebuild、request schema 与 operation slice：call-site identity 现包含 CodeQL AST start column，operation evidence 只能来自该 exact call site，禁止同行 field assignment 或重复 wrapper call 借证；合成 row fixtures 同步声明明确 column。
- recorded summary request 现绑定受限枚举得到的完整 Java source-tree snapshot SHA-256，而非只绑定 caller 文件与行摘要；导入静态 facts 与真实 CodeQL 都在提取前后核对同一源码快照，run manifest、recording、summary artifact、cache identity 与 replay 使用统一 `source_snapshot_sha256`，callee body 或任意 Java 源文件变化都会使旧 recording fail closed。
- 收紧 recorded LLM replay 的 bounded-slice 信任边界：每条 static fact 固化真实 call-site 行摘要，录制 snippet、source SHA、call-site、canonical callee、目标 `unknown_call` 与 resource instance 必须逐项一致；Return escape 等非方法 sentinel 不可请求摘要。operation/dataflow 仅可引用目标 instance slice，proposal 的全部 precondition、capture、field save 与资源身份都需静态支持；JSON 非有限数、浮点 budget/usage 统一 fail closed。MethodCall unknown 的双份 CodeQL query 现输出真实 callee canonical ID，Return escape 继续输出 `none`。新增跨 call、伪造 snippet、跨资源借证、同 unit 换行和 `1e309` RED→GREEN 回归；非真实 CodeQL lifecycle 集为 `158 passed, 4 skipped, 16 subtests passed`，真实 source→CodeQL→state 定向验收为 `1 passed, 2 subtests passed`。
- 收紧 lifecycle fact allocation binding：每个 fact 的 `instance_key` 必须恰好绑定一个 create，并与该 allocation 的 `resource_type`/`requires_close` 一致；orphan、重复 create 和 metadata mismatch 现在显式 `ValueError`，不再静默跳过或覆盖。coverage gap 严格迁移为 `(dimension, family_id, canonical_scope, reason, evidence_id)` 五元组，queue gap 只影响同 family、同 canonical queue scope，未覆盖 writer 合并自身 scoped reason/evidence；per-queue proof location 不再吸收 sibling queue dispatch。async stage 现保存 prefix/dispatch 的精确 `rule_dependencies`，derivation 同时发布 solver prefix 与 dispatch expansion rule，并按真实 rule/evidence pair 注册 implementation，移除全规则×全证据笛卡尔积。新增 RED→GREEN 回归后九个 lifecycle 文件为 `151 passed, 4 skipped, 14 subtests passed`；未运行真实 CodeQL、PoC、probe、动态 DoS 或目标服务。
- 接通正式 `resource-analyze --llm replay --config <recording>`：只接受严格、限额、source-snapshot 绑定的 `unknown_call` 录制响应，逐层调用既有摘要 validator；operation/identity/location/exit/evidence 验证结果、display effect 与 provenance 会进入私有审计 artifact，但当前 QL 支持的同位正向 operation 已由 caller program 执行，apply 层会去重并保持 `usable_effect_ids=[]`，不能把 replay 描述为 solver enrichment。原 `unknown_call` 与 coverage gap 继续保守保留，`drop`/`release` 永不成为负向安全证明。run 保存 0600 recording snapshot、validation/display artifact、provider/model/calls/token budget 与 summary derivations；`resource-replay` 从私有 recording snapshot 重新验证、求解并检测 summary/result/evidence/Markdown 篡改。live mode 继续明确拒绝，`--llm off` 保持完整可运行。
- 为每个 lifecycle analysis unit 增加严格、版本化且 contract ID 唯一的 `executor_contracts` 输入，并贯通 manual manifest、facts serialization/reload、static adapter 与重建校验；`llm_proposed` 不可驱动 stage semantics，manual/trusted contract 只在显式 manual 输入中接受。CodeQL queue dispatch 只生成保守 static contract：queued、rejection no capture、completion/cancellation unresolved；只有 complete numeric matching invariant 才标记 atomic capacity，unknown/partial capacity 不证明 bound。
- `resource-analyze` 现从 solver 的 transition source state 按 effect 顺序重放 dispatch 前缀，并经共享 `events.expand_dispatch`/`state_to_dict` 发布 deterministic submit/start/complete/reject/cancel 五阶段；missing、untrusted 或 identity-unknown contract 保守保留 capture/unknown。显式 completion/cancel drop 只移除 task holder，不消除 close obligation；queue capacity 仍仅约束声明的 `task_queue` dimension/scope，不解释为总 held-resource bound。
- `evidence.json` 新增 async derivations、五阶段 conclusions、effect evidence dependencies 与 dispatch code locations，async rule registry 明确指向 `resource_lifecycle.events.expand_dispatch`；replay 重新计算 async result/evidence，并将 evidence result identity 绑定 stored observed result，async state/rule/evidence 篡改均会使一致性检查失败。定向快速回归为 `107 passed, 4 skipped, 10 subtests passed`，未运行真实 CodeQL fixture、PoC、probe、动态 DoS 或目标服务。
- 收紧 queue capacity identity soundness：static adapter 以 unit、resolved holder/key、raw/resolved target event 与 capacity 生成稳定 executor contract ID，并在 invariant artifact 中显式绑定 contract/holder/target。checker 现在读取真实 `ExecutorContract`，逐项校验可信来源、queued scheduling、相同 capacity 与 `capacity_atomic=true`；同 resource family 的多个 queue 分别发布可区分的 per-queue scope，未覆盖 writer 单独降级为 `unknown`，不再把同容量 queue 折叠或误发 family 总上界。新增 mismatch、dual-queue、contract tamper、untrusted contract、uncovered writer 与 serialization/reload 回归；最终定向验证为 `120 passed, 4 skipped, 10 subtests passed`，`compileall` 与 `git diff --check` 通过。未修改 QL，未运行真实 CodeQL、PoC、probe、动态 DoS 或目标服务。
- static fact import 现在严格拒绝 holder kind/scope 非 queue/task，或 holder/target identity 为 `none` 的 dispatch row，并在 contract 构造边界保留显式 fail-closed 检查，不再泄漏裸 `AssertionError`。dimension evidence matching 复用 checker 的 canonical per-queue expanded scope；dual-queue proof 各自只绑定对应 candidate ID、candidate evidence 和 proof dependency，不交叉吸收同 family 的另一个 queue invariant。最终七文件回归为 `122 passed, 4 skipped, 12 subtests passed`，相关非真实 CodeQL/CLI/replay/invariant 定向集为 `83 passed, 4 skipped, 9 subtests passed`；`compileall` 与 `git diff --check` 通过。

## [2026-09-07] Resource lifecycle v1 execution baseline

- 收紧资源生命周期真实 CodeQL 提取契约：raw schema 新增严格 boolean `requires_close` 与枚举 `holder_scope`（`none|instance|global|task`），并贯通 decoder、事实哈希/重算、adapter 与 `ResourceFamily`/`Holder`；普通 POJO/array 只在 field、container 或显式 task capture 时跟踪，非 closeable 的 `close_obligation` 固定为 `not_applicable`。
- finally must-release 仅支持“allocation 位于对应 try body、finally 顶层只有一个 exact close statement”的 singleton subset；local release binding 必须来自唯一 initializer，或 `null`/无 initializer 后 try 内唯一直接 assignment。conditional/phi、多来源、overwrite alias 仍保留 candidate，但 path flags 为 false、coverage 为 partial，不能消除 obligation；normal-only release 也因缺少异常出口证明保持 partial。
- complete release 额外要求 allocation AST 不位于任何 `LoopStmt` ancestry；for init/update、condition、body 统一按 conservative single-execution gate 降级。循环内重复 allocation 的 release candidate 仍保留，但 path flags 为 false、coverage 为 partial/`allocation_in_loop_release_not_must`，最后一次 close 不会替先前实例消除 obligation。
- release method 必须是零参数调用，且 resolved method 等于或覆盖 `java.lang.AutoCloseable.close()`；同名 `close(boolean)` 等非契约 overload 不再生成 release effect，而是作为 partial unmodeled call 保守保留，不能消除 close obligation。
- allocation family identity 纳入完整 `instance_key`，同一源码行同类型的多个 allocation 不再碰撞；callable identity 统一为 `java-callable-v1:<qualified-name><method-descriptor>`，用于 unit、local holder 与 queue target event，overload entry selection 继续按 canonical ID 精确匹配。
- field initializer 现在直接产生 retain evidence，并区分 instance/global scope；container/task capture 按真实存储参数位绑定：Collection `add`/`offer` 与 Executor task 使用参数 0，Map `put`/`putIfAbsent`、双参数 `replace` 和 `merge` 使用参数 1，三参数 `replace` 使用参数 2；`merge` callback 及 `compute*`/`replaceAll` callback 不再被误判为存储对象。
- queue submission 以已解析 receiver Field 的 declared type 判定，精确接受 `Queue`/`BlockingQueue` 接口和 `ArrayBlockingQueue`/`LinkedBlockingQueue` concrete field，并固定 `add`/`offer` 单参数；不通过 supertype closure 接受未知 subclass。有限容量仍只来自 final field 的精确 concrete initializer，mutable 或 custom subtype 不生成 invariant。
- 扩展自包含 Java/CodeQL 回归，覆盖 POJO/array holder、field initializer、`Map.merge` value/callback、显式 task capture、predecessor may-throw、conditional/overwritten/selected alias、同址 twin allocation、overloaded callable、精确 bounded queue 与 mutable/reassigned queue；direct/embedded `ResourceLifecycleFacts.ql` 继续保持字节一致。
- 在独立分支 `codex/resource-lifecycle-v1-20260907` 建立 M0 执行状态、仓库复用映射和逐里程碑实施计划；现有 v2 P0 schema/tool `2.5/0.4.0` formal pipeline 保持不变。
- 记录实现前全仓基线 `101 failed, 618 passed, 22 skipped, 355 subtests passed`：失败来自隔离 worktree 缺少 ignored 历史资产及 sandbox 禁止本地监听 socket，后续与 lifecycle-v1 自包含/CodeQL 验收分开报告。
- 新增 lifecycle-v1 `1.0` IR 与共享状态求解器：严格区分 resource family、recent/summary instance、holder、event、effect、transition 和 close obligation；六类 effect 经同一操作函数，支持 may-hold union、must-release intersection、强弱更新、工作列表、超时与更新预算。
- M1 定向验证为 `25 passed, 24 subtests passed`，并保留现有 P0 release 回归；预算或 widening 不会被解释为无界。
- 新增显式 executor contract 和 dispatch 阶段展开，区分 submit/start/complete/reject/cancel；有限上界检查独立输出 held instances、item size 和 close obligation，非原子检查、写入者缺口、归纳失败、timeout 或不可信来源统一保守为带原因的 `unknown`。
- 扩展同一 CLI，新增 `resource-extract/resource-analyze/resource-replay/resource-evaluate` 路由；当前 extract/analyze/replay 支持 owner-only 无网络 manual IR、导入静态 facts 和真实 CodeQL database 模式，既有 P0 命令不变。
- 新增双份一致的 `ResourceLifecycleFacts.ql`、严格 decoder contract、事实溯源和 Java fixture；真实 javac→CodeQL→facts→IR→solver 验收为 `2 passed`，覆盖 finally close、未知容量异步 queue 和容量 2 queue，查询不输出最终 lifecycle status。
- 新增分层摘要验证、显式调用/token/timeout/retry budget、0600/0700 版本化缓存和证据重放；validator 只为具备静态 operation/identity/location/exit/evidence 的正向 create/retain/dispatch 保留 may-effect 接口，当前 production QL 未提供独立 callee witness，故 recorded proposal 只用于 audit/display且不改变 solver；drop/release 不能消除 may-hold、证明 must-release 或 bounded，M4 早期无网络测试为 `14 passed`。
- 新增 12 组 24 例性质先验回归、完整模式与五种信息删除消融；完整模式 24/24 匹配，所有消融只保持原状态或退化 `unknown`。评价产物固定写入 `reports/lifecycle-v1/`，legacy 等价实现标记 `N/A`，29 条历史 source record 仅入 metadata manifest 且 0 条进入生命周期指标分母。

## 2026-08-26

- Completed PoC-33 independent static-positive queue dynamic validation for 49 family-deduplicated candidates from 1,277 findings / 21 libraries.
- Aggregator accepted 49/49 cases (`confirmed_oom` 9, `observed_growth_not_confirmed` 13, other not_confirmed 16, blocked 11).
- Dynamic TP/FP: TP=9, FP=29, blocked/unscored=11, precision=9/38=0.237. See `results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-dynamic-validation/TP_FP_REPORT.md`.

## [2026-08-25] PoC-33 independent static-positive queue and dynamic-validation scaffold

- 对 `results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233/` 的 21 库 **1,277** 条 pipeline `static_unknown` finding 做独立静态证据审计：join entry/growth/flow/contract/lifecycle/recall，按 resource 去重为 **189** 簇，再按 handler+operation 家族合并。审计脚本 `scripts/audit_poc33_static_positive_queue.py`，产物 `results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-static-positive-audit/`。
- 独立队列 **49** 条（47 `independent_static_positive` + 2 高危 `independent_static_unknown`；P0 31 / P1 1 / P2 17），覆盖 17 个 target。该标签只用于动态验证排队，不改写 pipeline 三态产物。
- 动态验证脚手架已用 `scripts/prepare_dynamic_validation_output.py` 写入 `results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-dynamic-validation/`（49 paused cases）。随后按 `$java-web-dos-dynamic-validator` 分组隔离验证并计算 TP/FP。

## [2026-08-25] PoC-33 real-provider full batch completed 21/21

- 在用户明确知悉本地代码片段、源码路径与提示词可能包含未公开或组织私有信息并批准外发后，PoC-33 真实 provider immutable batch `results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233/` 以 `max_workers=1` 继续 bounded retry：Rebuild 在 target attempt 11 完成，ThingsBoard 在 attempt 11/12 遇到 `LLM_RESPONSE_SENSITIVE_CONTENT`、attempt 13/14 遇到 `LLM_RESPONSE_SCHEMA_INVALID` 后于 attempt 15 完成；attempt 16 未使用。Datacompare 保持 attempt 5 completed，未重跑。最终 batch state 与 P0 aggregate 均为 **21 completed / 0 failed / 0 malformed**。
- 最终 `poc33_real_llm_completion_audit.json` 验证 21 个 target 的 schema/tool `2.5/0.4.0`、六阶段 completed、formal/fail-closed、每库 7/7 entry queries 且 0 skipped/diagnostics、630 个 stage artifact ref 的 byte/hash/schema、单一 query-pack hash、全部 0600 私有 audit，以及 **172 个** API-key HMAC 认证的真实 RightAPI Responses cache/audit/contract record；所有响应均为 `grok-4.6`、completed、非 `fixture-` request ID，未发现 scripted transport 证据。
- 最终 benchmark-only recall 位于 `results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-recall-p0-final/`：33 条 truth 中 25 `full_chain_finding`、2 `association_missing`、2 `entry_only`、4 `growth_only`、0 `stage_failed`、0 `static_vulnerable`。该 oracle 映射不改变普通扫描的静态三态口径，也不表示动态 confirmed。

## [2026-08-24] Extended bounded real-provider retry and lifecycle candidate schema repair

- Batch target attempt ceiling由 10 显式扩展到 16，使已耗尽原上限的 formal target 可在新的人工授权下继续最多 6 次真实 provider attempt；默认仍为 2，只有 `--retry-failed --max-attempts 16` 才会重试既有 transient/provider-output failure，completed target 继续复用且不会被重跑。
- `guard_candidates.jsonl`、`bound_candidates.jsonl`、`release_candidates.jsonl` 的 schema 现与三个生产 Candidate `to_dict()` 完整字段契约一致，并校验新增 boolean/string/coverage 字段；lifecycle stage 在发布前显式校验三类 raw candidate，避免生产产物先写出、聚合阶段才发现 schema drift。新增模型到 artifact schema 的 RED/GREEN 回归。
- PoC-33 真实 LLM 批次新增 `poc33_real_llm_completion_audit.json` 派生审计：逐目标验证 formal/fail-closed、六阶段完成状态、stage artifact byte/hash/schema、统一 query-pack hash、0600 私有 audit，以及 API-key HMAC 认证 cache record 的 RightAPI Responses 元数据、`grok-4.6` model、completed status 与非 fixture request ID；最终 21/21 状态与计数见 2026-08-25 条目。

## [2026-08-24] Bounded retry for rejected real-provider target attempts

- Batch `--retry-failed` 现在允许在既有 `max_attempts` 上限内重新执行 `LLM_NETWORK_FAILED`、`LLM_RESPONSE_SCHEMA_INVALID` 与 `LLM_RESPONSE_SENSITIVE_CONTENT` 目标。三类错误对单次调用仍然 fail-closed；仅新的 target attempt 可再次调用真实 provider，不复用或接受被拒响应，也不放宽 Auth/Growth schema、敏感内容扫描或正式查询失败策略。新增 runner 回归先 RED 后 GREEN，凭据/授权失败仍明确不可重试。
- PoC-33 benchmark 报告器现在通过 `targets/<index>-<slug>/batch_target.json` 的 digest-bound identity 解析 v2 P0 batch target，而不是只接受历史平铺 `<slug>/` 输出；malformed、symlink 或重复 binding 继续 fail closed。该修复先用真实 P0 目录形状复现全量误报 `stage_failed` 的 RED，再转 GREEN。
- P0 aggregator 的 target binding 验证现在与 runner 写入格式一致，在当前计划中同时校验 `analysis_mode` 与 `query_failure_policy`；旧实现遗漏这两个 digest-bound 字段，会把 runner 正式产物统一误判为 binding mismatch。现有 legacy binding 路径保持不变，回归同样先 RED 后 GREEN。
- P0 aggregator 从陈旧 schema `2.0`/14-artifact 白名单切换到当前 `SCHEMA_VERSION=2.5` 的 30-artifact正式契约，覆盖 modeled configuration/security、entry gap/interposition、candidate links/dispositions、repeatability/amplification、Auth/Reachability 与 path-bound lifecycle evidence/coverage/summaries；`llm_audit.private.jsonl` 只做私有 schema/hash/reference 验证，绝不进入 aggregate 输出。新增公开 aggregate JSONL 均为 additive，当前 artifact-set 与 normative aggregation 回归先 RED 后 GREEN。

## [2026-08-23] PoC-33 majority recall: Presto, JMQTT and Citrus

- Presto/Airlift source fallback 现从本地源码恢复 `POST /v1/statement` 的 JAX-RS Entry，并将 `QueuedStatementResource.postStatement:213 -> queries.put:269` 保留为 source-backed partial E→G 证据；正式 full 位于 `results/java_web_dos_batch/poc33-recall-v2-20260823_001047-presto-source-jaxrs-v1/`，全部 stage completed、0 query diagnostic、0 remote provider request、private audit 为 0600，truth 产出 certificate-backed `static_unknown`。
- MQTT Entry/association 覆盖增加 validated `Object` callback 与严格 JMQTT async QoS2 skeleton：`NettyMqttHandler.channelRead -> MQTTConnection.processProtocol -> PublishProcessor.processRequest/processPublishMessage/processQos2 -> MqttSession.receivedPublishQos2 -> qos2Receiving.put`。跨 async processor table 的 dispatch 未被 CFG/path 完整证明，因此固定为 `partial`，不伪造 proven flow；generic-port MQTT benchmark matching 只对已匹配协议 Entry 生效。正式 full 位于 `results/java_web_dos_batch/poc33-recall-v2-20260823_144239-jmqtt-async-qos2-v1/`，4 links/flows/findings、0 diagnostic、0 remote provider request、private audit 为 0600。
- Spring MVC 对源码可解析的 SpEL route default 同时发布 modeled complete Entry（`spring_spel_source_default_modeled_entry`）与原 runtime-binding partial gap，避免把部署时 override 风险静默当作完整覆盖。Citrus 现恢复 `POST /rest/authenticate` 与 `GET /rest/verify/{type}`，同时保留 `spring_spel_route_default_requires_runtime_binding` / `spring_spel_class_route_default_requires_runtime_binding`。
- Growth domain 新增精确 `javax/jakarta HttpSession.setAttribute` session-retention candidate（`resource_dimension=objects`、`demand_input_role=value`、fresh-session cardinality 保持 partial）；Citrus 增加两个 bounded partial skeleton：`AuthenticateController -> RequestWrapperFilter -> RequestWrapper -> IoUtil.readBytes:47`，以及 `VerificationController -> VerificationProcessor -> CaptchaProcessor -> VerificationRepository -> SessionVerificationRepository -> HttpSession.setAttribute:26`。direct/embedded Growth、Association、Flow、Lifecycle domain 同步，package-accurate fixtures 覆盖正例及无关 lookalike。
- Citrus 首轮 formal 暴露 source-backed `InputStream` raw screening 会命中未注册的 `FileResourceService.makeIdentify:61`，随后在 strict flow normalizer 触发 `FLOW_REFERENCE_AMBIGUOUS`。production 现先按 authoritative normalized Entry 与 retained Growth 的 exact file/start-line 双端 reconciliation，再对保留行执行严格 normalization；flow implementation version 升为 `production-v2.5-poc33-recall-flow-source-reconciliation-v1`，阻止 pre-fix flow artifact resume。该行为先由失败回归锁定，再转 GREEN；被 version bump 中止的中间批次已写入 `ABORTED.json`，未作为正式结果使用。
- 全量 lifecycle fixture 额外暴露 `unmodeledLifecycleDispatch` 的 depth-2 分支把“任意两跳 source call”误当 lifecycle custom dispatch，导致 Netty request-body materialization 的 Guard/Bound/Release coverage 全部误降 partial。二跳分支现额外要求 nested target 具备对应 `lifecycleShape`；Netty line 76 request materialization 恢复 complete，而真正的 JSON async service Growth 仍由 `nettyProtocolDispatchGrowth` 保留 partial。该失败先在真实 CodeQL fixture 中复现，再由 direct/embedded 同步修复转 GREEN。
- 最终 Citrus immutable formal full 位于 `results/java_web_dos_batch/poc33-recall-v2-20260823_171704-citrus-spel-session-v1/`：24 Entries、36 Growth candidates、5 links/partial flows/certificates/findings，全部 stage completed、7 条 formal entry queries、0 diagnostic、2 次本地 scripted contract interaction、0 remote provider request、`llm_audit.private.jsonl` 为 0600；两条 Citrus truth 均为 certificate-backed `static_unknown`。
- 最新 immutable overlay `/tmp/poc33-overlay-citrus-lifecycle-v2-20260823_172904` 与报告 `/tmp/poc33-citrus-lifecycle-v2-report-20260823_172904` 达到 **27/33 `full_chain_finding`（81.8%）**、6 `entry_only`、0 `growth_only`、0 `stage_failed`、0 `static_vulnerable`。未覆盖项仅余 SkyWalking 1 条、SMQTT 4 条与 Concord 1 条；普通扫描 verdict 口径仍严格限定为 v2 三态，benchmark oracle 未被表述为动态确认。
- PoC-29 严格 full-plan digest 随 direct/embedded query pack 同步更新为 `8d75d8b55226680373483f8f36a42a1893e1d60b096febec76b6cee0ac3c70e1`。Netty fixture 扩展造成的 lifecycle callable 单测源码行号漂移已修正，未改动 production binding 语义。最终验证：Entry CodeQL `7 passed, 20 subtests`，Growth CodeQL `3 passed, 13 subtests`，Lifecycle CodeQL `11 passed, 71 subtests`，网络无关全套 `716 passed, 20 skipped, 477 subtests`；18 份 tracked direct/embedded `.ql` 全部 byte-identical，`compileall` 与 `git diff --check` 通过。

## [2026-08-22] ThingsBoard RequestBody String recall and large-DB query bound

- `EntryToGrowthAssociations.ql` 与 `EntryToGrowth.ql` 不再通过全库 `Method.overrides` 枚举 interface target；真实 ThingsBoard evaluator log 证明旧实现生成约 31.6 亿中间元组并在 300 秒 production deadline 超时。新实现仅接受 source concrete direct call，或 `final` field 的精确 constructor initializer + exact method signature + source-supertype ambiguity check；multiple implementations 继续 fail closed。interface 单实现/多实现、source `InputStream` 一跳/两跳 fixture 均保持预期。
- Spring `@RequestBody java.lang.String` 现作为精确 request-time byte materialization 同步进入 G1、candidate association、Entry→Growth flow 与 lifecycle coverage 四个 domain；operation 固定为 `spring_request_body_string_materialization`，`resource_dimension=bytes`、`demand_input_role=size`、`escape_scope=request`、coverage complete。新增 package-accurate fixture，覆盖 annotated Java String 正例、unannotated String 与 annotated lookalike 负例；四域测试先 RED 后 GREEN。
- 真实 ThingsBoard DB 查询均低于 formal 300 秒门槛：InputMaterialization 20.7s/38 rows、association 25.5s/23 rows、flow 69.4s/20 rows、LifecycleCoverage 23.6s/63 rows；`DeviceApiController.postTelemetry` 与 `TelemetryController` attributes/telemetry handlers 均有 exact source/sink line、complete materialization association/flow，lifecycle custom-dispatch gap 保守为 partial。
- ThingsBoard immutable formal full 位于 `results/java_web_dos_batch/poc33-recall-v2-20260822_184159-thingsboard-string-v3/`：全部 stage completed、7 条 formal entry queries、0 diagnostics、1875 Growth candidates、20 mapped/19 relevant candidates、25 flows/certificates/findings、38 次纯本地 scripted contract interactions、无远程 provider 请求，`llm_audit.private.jsonl` 为 0600。两条 truth 均从 `stage_failed` 推进为 `full_chain_finding/static_unknown`。
- 最新合并 overlay 报告 `/tmp/poc33-thingsboard-string-v3-report-20260822_185353/` 为 **20/33 `full_chain_finding`**、7 `entry_only`、6 `growth_only`、0 `stage_failed`。当前 60.6% 仍不足“绝大多数”，目标继续 active；下一优先级为 XXL-JOB 三条 growth-only 与 SMQTT 四条 entry-only。

## [2026-08-22] Solr pre-handler form parser recall

- G1 现有 `java.io.ByteArrayOutputStream.toByteArray` 模型在真实 Solr DB 中识别 `SolrRequestParsers.parseFormDataContent` 的 `keyStream`/`valueStream` full-copy materialization（`SolrRequestParsers.java:293`）。新增 bounded、source-backed Solr P0.1 form pipeline association：要求精确 `SolrServlet.service -> dispatch -> HttpSolrCall.call -> init -> SolrRequestParsers.parse -> StandardRequestParser -> FormDataRequestParser -> parseFormDataContent` 方法链、精确 `application/x-www-form-urlencoded` 常量与 BAOS sink；因 request field/custom interface path 尚无完整 field-sensitive witness，固定输出 `partial`/`static_unknown`，不伪造 complete flow。
- 新增 package-accurate Servlet fixture，覆盖真实 Solr form pre-handler 正例和同文件 unrelated BAOS 负例；定向测试先观察 0 association 的 RED，再转为唯一 `SolrServlet.service -> toByteArray` partial association GREEN。direct/embedded `EntryToGrowthAssociations.ql` 保持字节一致；真实 Solr DB 定向查询得到目标 `80 -> 293` partial 行。
- Solr immutable formal full 位于 `results/java_web_dos_batch/poc33-recall-v2-20260822_164548-solr-form-v1/`：全部 stage completed、7 条 formal entry queries 零 diagnostic、1763 Growth candidates、2 partial links/flows/certificate-backed findings、provider requests 0，`llm_audit.private.jsonl` 为 0600。`SOLR-APP-STATIC-0001` 已从 `entry_only` 推进为 `full_chain_finding/static_unknown`。
- 最新合并 overlay 报告 `/tmp/poc33-solr-form-v1-report-20260822_165828/` 为 **18/33 `full_chain_finding`**、7 `entry_only`、6 `growth_only`、2 `stage_failed`；仍未达到“绝大多数”，下一步继续处理 ThingsBoard formal query timeout 与 Spring `@RequestBody String` materialization。

## [2026-08-22] Grobid source-backed JAX-RS and output-buffer recall

- PoC benchmark 的 Entry 选择现在允许已关联同一 truth Growth 的 wildcard Entry 胜过未关联的 exact business route，但仍必须通过既有 `_routes_match`，不放宽 route pattern。Druid 两条与 PowerJob 因而进入 finding-backed `full_chain_finding/static_unknown`。
- 新增有界 `dosweb.entries.jaxrs_source` fallback：在 CodeQL annotation/type resolution 不完整时，从精确 Dropwizard `Application`、`GuiceBundle`、`DropwizardAwareModule`/`AbstractModule` imports、唯一 application bundle installation、唯一 resource bind 与 `environment.jersey().setUrlPattern` 恢复静态 JAX-RS registration；遍历限制为 8192 files、300000 nodes、512 KiB/file、64 MiB total、depth 64，symlink/excluded-dir/多安装/多 bind 均 fail closed。entries implementation version 升为 `production-v2.5-poc33-recall-source-jaxrs-v1`。
- G1 新增 `java.io.ByteArrayOutputStream.toByteArray` 的 request-local full-copy materialization；Association、Flow demand 与 Lifecycle Coverage 同步同一 Growth domain。对 framework annotation 在 DB 中不可见的 source method，查询仅以 source-backed `InputStream` 参数扩展候选 handler/source，production 仍按已归一化 Entry 的 exact file/start-line 绑定，未产生任意新正式 Entry。
- 新增 package-accurate `SourceStreamResource` CodeQL fixture，覆盖无 annotation 的 `InputStream` handler、`readAllBytes` flow、`ByteArrayOutputStream.toByteArray` association 与 lifecycle anchor；direct/embedded 三类查询保持字节一致。真实 Grobid DB 定向查询得到 G1 4 rows（目标 748/1101）、association 74 rows（484→748、904→1101 均存在）、flow 0 rows（按 partial/unmodeled 保留）、lifecycle coverage 42 rows（两个目标各三 family partial）。
- benchmark truth seed 现接受 `sinks.jsonl` 的有界字符串行范围（如 `"712-751"`），并把 `SINK-ID: descriptive text` 规范化回 `SINK-ID` 后再与 referenced finding/sink record 对齐；该逻辑仅用于 post-hoc oracle，不影响普通扫描。
- Grobid immutable formal full 位于 `results/java_web_dos_batch/poc33-recall-v2-20260822_142244-grobid-baos-v9/`：全部 stage completed、provider requests 0、41 Entries、207 Growth candidates、8 links/flows/findings、private audit mode 0600；两条 truth 均产生 certificate-backed `static_unknown`。最新合并 overlay 报告 `/tmp/poc33-grobid-baos-v9-report-fixed-QWiCuA/` 为 **17/33 `full_chain_finding`**、8 `entry_only`、6 `growth_only`、2 `stage_failed`，仍未达到“绝大多数”，目标继续 active。
- 本轮变更均先复现 RED 再转 GREEN；已通过 source-handler 定向 CodeQL fixture（1 test）、G1–G4 fixture（1 test / 8 subtests）及 symbolic-sink 定向 pytest。

## [2026-08-21] PoC-33 full-chain recall crash and disposition fixes

- 修复 Growth provider payload 对 modeled `ConfigFact.source_location_ref == config_id` 的合法 config-backed 引用处理：此类引用现在进入匿名化 `config_aliases`，不再被误送到 excerpt alias 表而触发 `KeyError`。Growth stage implementation version 单独升至 `production-v2.5-poc33-recall-growth-config-v2`，阻止旧 Growth artifact 被错误 resume。
- `ConfigFact.normalized_value` 的整数域与上游 modeled configuration 对齐为 signed 64-bit 正值上界，允许 JetLinks `logging.logback.rollingpolicy.total-size-cap=10000000000` 进入严格 bounded slice；bool、负越界与 `2**63` 继续 fail-closed。
- Growth CFG evidence 对同一 `(entry, growth, call_path, phase_sequence)` 上的多 attacker inputs 只保留一个稳定 path identity，同时保留各自独立 `flows_to` fact；修复 JetLinks captcha `width`/`height` 共用 CFG path 时的重复 path-ID schema 失败。
- PoC benchmark disposition 先选择精确 literal route，再按 truth method 与目标 Growth 的实际 candidate link 选择同 registration 的 canonical route variant，避免 placeholder/methodless 变体掩盖完整链。alias 只在 registration 与 handler callable/file/line identity 均一致时复用，避免 JAX-RS 全局 package registration 串错 endpoint。严格 context-path suffix 仅允许长 route 在前方多 context prefix，且 downstream Growth identity/link 仍须匹配；WGCLOUD 的 `/wgcloud/agent/minTask` 因而可与应用 route `/agent/minTask` 对齐。
- 后验 truth seed 会在 repo-root 内有界解析 `source_result.static_traceability` 引用的 `sinks.jsonl`，把 `S-CAPTCHA-BITMAP` 等 symbolic sink 映射回源码位置；同时读取 `static_finding.json`、`source_result.json`、`case_plan.json` 的顶层及 nested `static_traceability.evidence`。benchmark 还可在同文件、truth marker 明确包含 receiver type 且仅源码行号漂移时，用 receiver declaring type 对齐 semantic sink，并支持 truth 指向 receiver 字段声明、candidate 位于调用点的 owner 匹配；这些逻辑仅属于 benchmark oracle，不进入普通扫描。
- G1/Association/Flow/Lifecycle 统一 read-all materialization domain：`IoUtil.readBytes`、Commons `IOUtils.toByteArray`、Spring `StreamUtils.copyToByteArray/copyToString`、`InputStream.readAllBytes` 与 `ServletUtils.getRequestString` 在四个查询中一致建模。Spring handler 的原生 `javax/jakarta HttpServletRequest` 参数进入 attacker-source 域，utility 参数 0 或 `readAllBytes` qualifier 作为精确 byte-size demand。新增 package-accurate Spring fixture，覆盖所有六类 API、跨 helper gateway flow、association 与 lifecycle coverage；direct/embedded query 保持字节一致。
- 真实本地 CodeQL + scripted provider 回归：Datacompare（15 findings）两条 truth、RuoYi-Vue-Fast（4 findings）一条 truth、Rebuild barcode、WGCLOUD 与 JetLinks 均推进为 `full_chain_finding/static_unknown`。JetLinks attempt 3 完成 710 entries、406 Growth candidates、239 candidate links、3 certificate-backed findings，`JL-STAGEA-0001` 现在为完整链；7 条 formal entry queries 均无 diagnostic。当前合并 overlay 为 8/33 `full_chain_finding`，仍不代表“绝大多数”或 full recall 完成。
- 新增 config-backed alias、signed-64-bit config、同-path 多输入、精确 route/link canonicalization、context-path、semantic sink line drift/receiver owner、nested case-plan evidence、symbolic sink location和统一 read-all 查询回归；所有行为修复均先复现 RED 再转 GREEN。

## [2026-08-21] gRPC generated-identity and generic-builder hardening

- modern nested `AsyncService` 现在额外要求 generated outer `*Grpc` 具有精确 `@io.grpc.stub.annotations.GrpcGenerated` 证据；同形但未注解的自定义 `FooGrpc.AsyncService` 不再产生 entry/gap，legacy nested `*ImplBase` 兼容分支不受影响。
- gRPC builder native-registration 匹配只接受方法实际声明在精确 `io.grpc` package 中的 `ServerBuilder` / `ForwardingServerBuilder`；同时兼容 CodeQL 对泛型声明呈现的 `ServerBuilder<>` 与 `ForwardingServerBuilder<T>`。删除“任意子类只要继承 ServerBuilder 即可信”的旁路，应用 `FakeBuilder extends ServerBuilder` 覆写 no-op `addService` 现在仅留下 partial，不会伪造 complete。fixture 同时覆盖未注解 lookalike、泛型 `ForwardingServerBuilder<T>` 子类、direct legacy registration 和 no-op subtype override。
- 验证：CodeQL entry fixtures `4 passed, 20 subtests passed`；相关 entries/production pytest `25 passed, 26 subtests passed`；direct/embedded query 字节一致，`compileall`、`git diff --check`、无 staged 检查通过。真实 `apache__skywalking-pprof-staging-db` 仍产 5 行，其中 `/skywalking.v10.PprofTask/collect` 精确为 1 partial、0 complete，handler 为 `PprofServiceHandler.collect`；由于注册唯一性未证明，结论继续为 `static_unknown`。

## [2026-08-21] gRPC modern AsyncService and ForwardingServerBuilder partial recall

- `GrpcEntries.ql`（direct/embedded 字节一致）将 generated RPC override 的保守形状从仅 nested `*ImplBase` 扩展至同一 generated outer `*Grpc` 下的 nested `AsyncService` interface；仍要求 source implementation 的真实 `overrides`、唯一编译期 `SERVICE_NAME` 与既有 route 推导，未加入项目/FQN/route 特判。
- native registration 同时识别 gRPC 的 `ServerBuilder` hierarchy 与精确 `io.grpc.ForwardingServerBuilder` declaration，不扩展至任意同名 `addService`/`addHandler`。唯一 registration、0–2 forwarding、concrete-target 歧义和 streaming `onNext` attacker-input 证明均未放宽。
- 新增 generic fixture 的 modern `AsyncService` complete streaming 正例及 two-concrete-wrapper → `ForwardingServerBuilder` 歧义负例；后者仅产 partial。真实 `apache__skywalking-pprof-staging-db` 查询产 5 行，其中 `/skywalking.v10.PprofTask/collect` 为 `PprofServiceHandler.collect` 的 1 行 partial、0 complete，故仍为 `static_unknown`，未声称 formal full 或漏洞结论完成。临时 CSV：`/tmp/dosweb-skywalking-grpc-async-20260821_002208/grpc.csv`。

## [2026-08-20] Switch formal LLM provider to RightAPI Codex Responses

- 生产 host 确认为 `https://rightapi.ai/grok/v1/`：非流式 Responses 请求固定发送 `User-Agent: pi-coding-agent`，不使用 Cloudflare Cookie、Origin、Referer 或浏览器 sec headers；HTTP 403 一律 fail-closed，不实现 SSE。
- 收紧完整 Responses envelope 的私有持久化边界：Growth/Auth 在 parser、cache、audit 或 `last_audit` 接触 `reply.body` 前均扫描完整原始 envelope（含 reasoning/metadata）；命中 configured key、Bearer、既有 credential/extra pattern 时 fail-closed。Growth cache format 升至 v7，HMAC domain 同步为 v7；Auth cache 升至 v2。匹配当前 identity 且通过严格结构、hash 与旧 v1 HMAC 认证的 Auth v1 文件会以 dir_fd/inode 校验后删除并 fsync，形成 cold miss，允许安全 v2 原子重写；伪造、损坏、unsafe 文件不会删除或信任。回放 raw response 亦复查；`LlmAuditRecord` 同步拒绝 Bearer 或 key-shaped raw envelope。新增 Growth/Auth metadata 回显零 cache/零 audit 与 Auth v1 退役回归。
- 最终真实合成 canary 已通过：Growth 与 Auth 均返回 HTTP 2xx、actual model `grok-4.6`，严格 contract/evidence 与完整 envelope 检查通过，等价第二次调用均命中本地 cache；脱敏证据位于 `results/provider_canary/rightapi-responses-final-20260820_154025/`。
- 首次 Auth synthetic canary 曾因响应漏掉必填 `confidence` 被严格 parser 按 `LLM_RESPONSE_SCHEMA_INVALID` 拒绝。Auth prompt 现明确要求四个键 `auth_context`、`evidence_ids`、`assumptions`、`confidence`，且未知时仍输出 `unknown`/`low` 与全部键；`AUTH_PROMPT_VERSION` 升至 `auth-contract-v3` 隔离旧缓存，未放宽 parser/schema，并已由上方最终 canary 重测通过。
- 最终网络无关全套验证为 `679 passed, 10 skipped, 456 subtests`；`compileall`、`git diff --check` 与无 staged 检查通过，fresh reviewer 最终 GO（无 blocker/high/medium）。

## [2026-08-20] RightAPI migration details

- fresh-reviewer 收尾：credential preflight 现序列化并扫描与实际发送完全一致的 Responses payload；Auth wire regression 显式锁定 `/responses`、typed `input_text`、JSON text format、`store=false`/`stream=false`，并拒绝遗留 Chat Completions 字段。
- 正式 LLM provider 现唯一使用 `https://rightapi.ai/grok/v1/`、`grok-4.6` 与非流式 `/responses` 协议；不再接受旧 Chat Completions production endpoint 或 DeepSeek model。
- Growth/Auth 请求改为 typed `input_text` Responses payload，并以 `store=false`、`stream=false` 和 JSON-object text format 固定约束；响应仅接受 completed、唯一 assistant message 的 `output_text`，reasoning item 可忽略，refusal/incomplete/ambiguity fail-closed。
- cache/audit identity 迁移为 `rightapi_codex_responses` / `responses-v1`，旧缓存自动冷 miss；现有 API-key 存储字段和环境变量兼容不变，错误文案改为 provider-neutral。
- 网络无关全套迁移基线验证为 `676 passed, 10 skipped, 454 subtests`，fresh reviewer 给出 GO。历史 canary `results/provider_canary/rightapi-responses-20260820_111859/` 的 HTTP 403 后续定位为 provider 拒绝默认客户端 User-Agent，而非凭据无效；该历史失败已由上方固定 `pi-coding-agent` UA 及成功 canary 取代。

## [2026-08-19] Reviewer hardening: generated gRPC streaming and SMQTT gap identity

- `GrpcEntries.ql`（direct/embedded 字节一致）不再将 RPC 的 response `StreamObserver` 当 attacker input。client/bidi complete entry 仅在 source method override generated `*ImplBase` RPC declaration、outer `*Grpc.SERVICE_NAME` compile-time identity、service 唯一注册均可恢复，且每个顶层 conditional return leaf 都是 source `StreamObserver` construction、具唯一 `onNext(request)` 时发布；每个 leaf 的 `onNext` 为同一路由的 `stream` handler。native registration 识别 `ServerBuilder` 子类；source forwarding 以参数 0 直传、唯一 concrete interface dispatch 的非递归 0–2 wrapper 展开建模。其余 generated streaming RPC 仅输出 concrete partial gap。
- 删除 Pprof/SkyWalking/fixture FQN 和 route 特判。route 从 generated outer `SERVICE_NAME` 和 generated method name 推导为 `/<SERVICE_NAME>/<rpcMethod>`；partial 在 identity 可恢复时同样保留该精确 route，缺 identity 才使用 source handler identity。fixture 改为 generic generated `SampleGrpc.SERVICE_NAME`/`SampleImplBase`，覆盖 interface→两层 forwarding→NettyServerBuilder、顶层 ternary 的两个 observer、unregistered/helper/lookalike/no-forward/double-forward/multi-implementation/unsupported leaf/no-identity/duplicate-registration negative。
- 第三轮 fresh-review 收紧：每个 forwarding method 必须只有一个参数 0 直传的 outbound call，因而 native 与任意 wrapper depth 的混合转发均拒绝；`uniqueConcreteTarget` 现在把 dependency 内非 abstract concrete override 也计为歧义，仅最终选定 target 可为 source。fixture 将多实现、无/反射 forwarding、mixed direct+wrapper 和两次 service 注册拆为 identity/observer 均完整的独立 partial negative，并使用独立 generated service route 断言不会泄漏 complete observer entry；registered 与 ternary complete RPC 则断言无同 service partial。
- SMQTT `mqtt_protocol` partial gap 现额外要求 exact diagnostic、exact `io.github.quickmsg.core.mqtt.MqttReceiver.newTcpServer` handler/registration FQN、同一 `.java` file 和正行号；同 note 的 synthetic/mismatched shape 继续拒绝。ordinary verdict 仍由 partial coverage 导出 `static_unknown`。
- 历史初版查询的旧 DB 证据是 `/tmp/dosweb-skywalking-grpc-final-1044439/grpc.json`：`raw_rows=3`、严格 decode/normalize `entries=0`、`gaps=3`、0 query diagnostic。收紧 generated-identity 后的当前 run 为 `/tmp/dosweb-skywalking-grpc-reviewer-final2-1117123/grpc.json`：`raw_rows=0`、`entries=0`、`gaps=0`，同样无 query failure。两者均因该 DB 未包含 `PprofServiceHandler.java`；未声称 Pprof 召回已完成，需 DB 重建后重验。

## [2026-08-19] Close final Solr web.xml descriptor review findings

- descriptor 发现改为 fd-relative、增量 `os.scandir` DFS：单条目录项立即计数，命中 tree/file limit 立刻停止、关闭待处理目录 FD；不再调用 `os.walk` 或预物化路径列表。新增单目录 tree-limit iterator 回归。
- descriptor coverage 的 complete/partial 计数改为 candidate 维度（多 URL pattern 仍可产生多 complete entry），validator 校验计数关系、最大值与受控 diagnostics 枚举。解析时独立保留 declaration identity，因此第二个 descriptor 即使没有有效 mapping，也会使相同 FQN 的 candidate 降为 partial。
- 新增真实 Solr 源树 resolver integration 回归，验证 `SolrServlet.service -> /*`、static registration、unknown auth 和 schema 计数。

## [2026-08-19] Harden Solr web.xml descriptor entry binding

- 根据独立审查收紧 descriptor 遍历与选择：改用有界 `os.walk(followlinks=False)`，限制访问节点和最多 64 个 descriptor；拒绝最终文件及父目录 symlink，并使用 `dir_fd`/`O_NOFOLLOW` 逐组件读取。超过文件、树、字节、XML 元素或深度上限均保留 partial 诊断。
- 相同 `servlet-name` 即使重复相同 class 也不再被 set 去重；同一 candidate 出现在多个 descriptor 时发布 concrete partial `web_xml_descriptor_selection_ambiguous`，不提升 complete。单一 descriptor 的多个 URL pattern 仍逐条 complete。
- `descriptor_coverage.json` 固化为版本化 1.0 schema（发现/解析/映射/candidate 计数与有界 diagnostics），entries executor 生成后再次校验。`web_xml_servlet_mapping` placeholder 不再进入 concrete gap artifact。

## [2026-08-19] Solr web.xml Servlet descriptor entry binding

- `ServletEntries.ql`（direct/embedded 字节一致）仅为 source-backed、声明 `service(HttpServletRequest,HttpServletResponse)` 的 `HttpServlet` 子类发布 descriptor candidate；candidate 在 Python resolver 前均为 partial，绝不直接成为 Entry。
- 新增有界、安全的 `dosweb.entries.webxml`：只读取 root-contained regular `WEB-INF/web.xml`，拒绝 symlink、DTD/entity/external declaration、非法 UTF-8、超限文件/元素/嵌套；仅以完整 FQN 和同一描述符内唯一 `servlet-name → servlet-class → url-pattern` 链提升为 `static_registration`。解析/结构问题只留下 partial descriptor coverage，不会伪造 complete 或造成 CodeQL query failure。
- entries stage 新增审计产物 `descriptor_coverage.json`。Solr 真实 DB 查询并经 resolver 得到 `org.apache.solr.servlet.SolrServlet.service`、`web.xml:SolrServlet`、`/*` 的 complete entry；认证与 filter/order 仍为 unknown/deferred，未将 form parser 或 filter 安全边界标为已证。
- 新增 web.xml happy/namespace/conflict/malformed/DTD/UTF-8/symlink/element-limit 回归和 servlet fixture；定向 pytest 与真实 javac/CodeQL fixture 均通过。

## [2026-08-19] PoC-33 SMQTT protocol gaps and gRPC client-streaming entries

- `normalize_gap_entry_rows` 现在只为 source-backed `smqtt_protocol_dispatch_binding_unresolved` 保留 `mqtt_protocol` partial gap；generic protocol placeholder、synthetic query gap 与 `dynamic_topic` 继续丢弃，ordinary verdict 不会被升级。
- 此条 gRPC 初版 client/bidi-streaming 记录已被上方同日「Reviewer hardening」替代：complete 条件现要求 generated override、`SERVICE_NAME`、唯一 forwarding registration 与 source `onNext` proof；不再含任何 Pprof/SkyWalking/fixture 特判。
- 初版验证记录已被上方同日 reviewer hardening 的 fixture/DB 结果替代；旧 `apache__skywalking-db` 未编译 `PprofServiceHandler.java`，因此不作为 Pprof 召回完成证据。

## [2026-08-19] Remote provider credential and endpoint rotation

- 将默认 OpenAI-compatible provider 切换到 `https://apibasis.com/v1/` / `grok-4.6`；旧 DeepSeek 模型仍保留为显式兼容选项，但不再是默认值。
- production endpoint allowlist 增加新的规范化 HTTPS endpoint；仅显式接受 provider 返回的 `grok-4.6-build` 模型别名，其他模型不匹配继续 fail-closed。
- 本地凭据已轮换到 gitignored、owner-only `config/local_secrets.json`（`0600`），未写入日志、报告或版本控制；配置/endpoint 定向回归及无源码 provider canary 通过。API-key 轮换会改变私有 cache HMAC，旧 provider cache 不可跨 key resume，应使用新的 immutable output。当前 query-pack 冻结后的 PoC-29 临时 full-plan digest 为 `38aa5eb7fb91672c89fdfe4045d2a8c34abd131bea45b56d10063042c3362c43`；未重写历史计划资产。

## [2026-08-19] Track A3 partial-first entry interposition extraction

- 新增 `EntryInterpositions.ql`（direct/embedded 字节一致）、严格 `entry_interposition` decoder 合约及 `entry_interposition_facts.jsonl` schema/entries-stage 产物。
- 仅提取 source-backed `FilterRegistrationBean` 静态注册、常量 URL/order 与 filter action/chain 位置；CFG 未被严格证明时固定发布 `partial`/`cfg_action_before_chain_unproven`，不把 interposition 或 HertzBeat 链声明为 complete。
- `EntryToGrowthAssociations.ql` 与 `EntryToGrowth.ql` 新增 source-defined `doFilter`、depth≤3 唯一 interface implementation、`computeIfAbsent/putIfAbsent/merge` key demand 和 request-URI regex group taint witness；所有跨 callable 结果仍固定为 partial，不改变普通 verdict。
- HertzBeat 真实数据库回归精确提取 controller 43、filter 53、registration 42、action 63、chain 66/69/72/76、sink 77，并形成 partial association、partial flow 与 certificate-backed `static_unknown` finding；0 query diagnostic。formal entries 将 interposition 作为第七个必跑查询，仅 exploratory 允许失败降级。
- G1 `InputMaterialization.ql` 新增 `IoUtil.readBytes`、Commons `IOUtils.toByteArray`、Spring `StreamUtils.copyToByteArray`、JDK `readAllBytes` 及 HttpServletRequestWrapper reader-loop/StringBuilder 物化；Citrus `RequestWrapperFilter.java:47` 与 PowerJob `CachingRequestBodyFilter.java:72` 已通过真实数据库严格查询及 scripted-provider production canary。链级结果分别推进为 `growth_only` 与 `association_missing`，未伪造 Entry→Growth 证明。
- Spring MVC Entry 对 source-defined SpEL 默认 route 增加保守解析：方法级 `authenticateEndpoint` 及类级 `verifyEndpointPrefix` 只发布 `dynamic_unresolved/partial` concrete gap route，不再把原始 `#{...}` placeholder 误当 complete route；Citrus 真实数据库已提取 `/rest/authenticate` 与 `/rest/verify/{type}`。
- 冻结 query pack 后的 21-target formal entries wave 已发布到 `results/java_web_dos_batch/poc33-recall-v2-20260819_093248-entries/`：21/21 completed、全部 query_count=7、0 skipped/query diagnostics、七类 entries artifact 集完整；`AUDIT.json` 记录逐目标证据。
- 新增 schema/production/contract、route-variant canonicalization、Servlet `/*` benchmark matching、sink-location truth matching及 interposition/unique-interface fixture 回归；benchmark entry reader 同时严格识别冻结 2.0 两文件集合与当前 2.5 七文件集合。前两次 21-target entries wave 分别因执行期间 query pack 继续变更、以及新 gap artifact 暴露重复 semantic ID 而主动终止，均保留为 `ABORTED.json` 标记的非正式资产，不参与 recall；`normalize_gap_entry_rows` 现按覆盖状态在内的完整身份确定性去重，Citrus/Solr/Dependency-Track formal entries 定向重跑均成功。网络无关全套为 `656 passed, 10 skipped, 447 subtests`，real CodeQL entry/growth/lifecycle-flow 为 `4/20 + 2/12 + 3/53`。

## [2026-08-18] PoC-33 recall hardening: configuration pruning, credential redaction, chain-level dispositions

### 修改时间
2026-08-18

### 变更类型
- [修复]
- [分析语义]
- [安全]
- [测试]
- [文档]
- [评估]

### 核心改动
- **schema/tool 升版**：artifact schema 升至 **2.5**、tool 升至 **0.4.0**（`dosweb/pipeline.py`、`dosweb/artifacts/schemas.py`）；per-stage implementation version 更新为 `production-v2.5-poc33-recall`。旧 2.4 artifact 保留但不可 resume。
- **approved design amendment**：在 `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md` 新增第 19 章（PoC-33 recall hardening / P0.1 extension），明确 Track A 为 P0 修复、Track B 为显式扩展，纠正 remote LLM 授权口径（显式 `allow_remote_llm` + 非空 key + 可读 checkout 为硬门禁，URL/SHA 仅为可选审计元数据），并写清 JAX-RS/gRPC/Armeria/Solr 的 complete/partial 边界。
- **Track 1.1 配置遍历剪枝**：`dosweb/configuration/extract.py` 新增与 corpus 一致的 `_EXCLUDED_DIRS` 剪枝（`.git/.gradle/.idea/.mvn/build/node_modules/out/target`），并将配置读取限定到 root、`config/conf/WEB-INF`、`src/main/resources`；新增 `extract_modeled_configuration_with_coverage` 返回可审计 `configuration_coverage.json`（visited/pruned/config-file/truncated）。entries stage 现发布该 artifact，修复 Druid/ThingsBoard 因 node_modules 超过 100k 遍历上限而 `CONFIG_MODELED_DEFAULT_INVALID` 失败。
- **Track 1.2 decoder 安全诊断**：`dosweb/codeql/runner.py` 的 bqrs_decode 失败保留 query name、contract reason、column、row（序列化为安全 JSON），不泄露绝对路径或源码内容；`_decode_contract_diagnostic` 负责白名单字段。
- **Track 1.3 凭据 redaction**：新增 `dosweb/growth/redaction.py`，行号保持地替换 credential assignment/mutator/header 的值为固定 token；`SourceExcerpt` 新增 `original_excerpt_sha256`、`redaction_events`、`redaction_version`，`content` 为 redacted（transmitted）内容；`_scan_transmitted_request` 与 `_sensitive_java_assignment`/`_CREDENTIAL_ASSIGNMENT` 改为对 `[REDACTED]` 值感知，避免业务 `password`/`token` 赋值造成误报，同时真实 key/JWT/AWS/私钥仍 fail-closed。`_slice_for` 为 `LLM_BOUNDED_SLICE_INVALID` 附加 candidate id、repo-relative path 与 line。
- **Track 1.4 case-preserving asset resolver**：`dosweb/benchmark/truth.py` 新增 `resolve_asset_directory`，按大小写不敏感且拒绝歧义/symlink 的方式解析 `grobidOrg__grobid` 等大小写保留目录；`build_asset_manifest` 改用该解析器，修复 Grobid 误判 `asset_missing`。
- **Track A1 formal entry selection**：formal 模式现在执行全部 6 个已启用 P0 entry families，源码 hint 仅用于 exploratory entries 成本侦察，不再决定 formal 是否运行查询。
- **Track 0.2 链级 disposition**：新增 `dosweb/benchmark/disposition.py`（`compute_disposition` + 11 态 status）与 `scripts/generate_poc33_recall.py`，从 `poc/manifest.json` 生成版本化 truth seed，逐条产出 `truth_dispositions.jsonl`/`summary.json`/`REPORT.md`；主匹配使用 repo + entry identity + sink/growth identity + finding/certificate，route marker 仅为次级诊断。
- **CodeQL 查询端召回修复**：
  - `EntryToGrowthAssociations.ql`：`growthSite` 对齐真实 Growth 查询（put/add 限 Map/Collection、submit/execute/offer/schedule 限 ExecutorService/BlockingQueue、均要求 field-backed receiver），transitive 调用链限制 depth≤3，并把 JAX-RS（`javax/jakarta.ws.rs`）handler 纳入 association；修复 Rebuild 10840 行超限导致的 `ROWS_INVALID`（降至 1165 行）。
  - `LifecycleCoverage.ql`：`modeledGrowth` 对齐真实 Growth 查询的 declaring-type 约束，并新增 `entryReachableGrowth`（handler + callsWithin depth≤3）把 coverage 限定到入口可达的 growth site；修复 Dependency-Track 10221 行超限（降至 21 行），并把 JAX-RS handler 纳入。
  - `JaxRsEntries.ql`：`dynamic_unresolved` 分支现在仍合成实际路由（verb + classPath + methodPath），不再输出字面 `unresolved_jax_rs_resource`；修复 Concord/Presto 等动态注册 JAX-RS 资源的 route 缺失。
  - `SpringMvcEntries.ql`：`getMappingPath` 对无 value/path 的 `@PostMapping()`/`@RequestMapping` 回退为 `""`，修复 HertzBeat `PushPrometheusController`（`@RequestMapping("/api/push/prometheus/**")` + 空 `@PostMapping`）这类空路径映射缺失。
  - `dosweb/benchmark/disposition.py`：`_match_entries` 支持 Spring `/**` 多段通配与 `{}` 单段占位（`_routes_match`），使 HertzBeat 等 `/**` 路由与具体 truth 路由可匹配。
  - `ContainerGrowth.ql`/`EntryToGrowthAssociations.ql`/`LifecycleCoverage.ql`：新增 `computeIfAbsent`/`putIfAbsent`/`merge` 作为 Map container 写（demand role=key），使 HertzBeat `jobInstanceMap.computeIfAbsent` 等持久 Map 写进入 growth candidate 与 association/coverage 域。
  - 以上查询的 direct/embedded 副本已同步保持字节一致。

### 验证
- 定向回归：`test_configuration_reachability.py`（11）、`test_config_and_cli.py`、`test_growth_redaction.py`（9）、`test_truth_disposition.py`（8）、`test_codeql_adapter.py`/`test_codeql_decoder.py`（14）、`test_deepseek_client.py`（108 passed / 141 subtests）、`test_production.py`（32）、`test_benchmark_truth.py` 快速子集、`test_batch_plan.py`/`test_batch_runner.py` 全绿。
- `python3 -m compileall -q dosweb scripts` 通过；`python3 -m pytest -q` **636 passed、9 skipped、436 subtests、2 warnings**。
- 真实 CodeQL 验证：Druid entries（25 行，含 `POST /druid/v2/sql`）、ThingsBoard entries（1045 行）不再 `CONFIG_MODELED_DEFAULT_INVALID`；HertzBeat 提取 `POST /api/push/prometheus/**/`；Rebuild association 1165 行、Dependency-Track lifecycle coverage 21 行均通过 decoder 契约；Concord JAX-RS 输出实际路由（如 `POST /api/v2/process/{id}/log/segment/{segmentId}`）；HertzBeat `jobInstanceMap.computeIfAbsent` 进入 ContainerGrowth candidate。
- 21 库 entries 全量重跑（`poc33-recall-v2/`）：19/21 rc=0 产出 entry facts；其中 SkyWalking（0，gRPC 未建模）、Solr（0，web.xml 注册未建模）、SMQTT（0，MQTT Reactor 分发未建模）、Grobid（0，`GrobidRestService` 未编译入 DB）、Concord（0，动态 JAX-RS 仅 partial 未持久化）与 Presto（2，`QueuedStatementResource` 不在 DB）仍需后续 Track A2/B3/B4 与 DB 重建。
- 链级 recall 脚本对既有 `poc33-recall` 结果生成 33/33 disposition（4 full_chain_finding、2 entry_and_growth_linked、14 entry_only、13 stage_failed，0 static_vulnerable），全部有 reason code。

### 保留
- 未修改 `../dos-analysis/`，未 reset 既有未提交改动，未删除/重写保留资产。
- 动态 truth 仍仅作 oracle label，不改变 ordinary scan verdict；不设 static_vulnerable 数量 KPI。

## [2026-08-18] Remove git-commit provenance gate

### 修改时间
2026-08-18

### 变更类型
- [安全]（用户明确授权）
- [批处理]
- [测试]
- [文档]

### 核心改动
- 用户明确决定：工具不再需要 git-commit provenance 作为门槛。`tree-sha256` 目标与 `git-commit` 目标同等对待，全部可 full 执行，不再 paused。
- `dosweb/batch/corpus.py` 与 `dosweb/benchmark/truth.py`：`provider_eligible` 不再依赖 `fingerprint_type`，统一为 True；`reason` 不再产出 `attestation_unavailable`；`attestation` 仅保留指纹类型作为身份元数据。
- `dosweb/batch/plan.py`：full 模式不再因缺 provider provenance 而 paused，所有目标 queued。
- `dosweb/batch/runner.py`：移除 full 模式的 commit 校验与 worktree 固定（`_prepared_provider_checkout`、`_git_checkout` 及 `verify_local_checkout_at_commit` 导入），full 直接使用本地源码树；`source_commit_sha` 对 tree-sha256 目标为 None。
- `dosweb/llm/deepseek.py`：remote 门禁降级为显式 `--allow-remote-llm` + 非空 API key + 可读本地 source checkout；`_verified_attestation` 不再调用 verifier，直接返回本地源码树 attestation（`verified_public`/`verified_clean_checkout` 记录为 False，不再是失败条件）；`PublicSourceAttestation.source_commit_sha` 允许 None。
- `dosweb/llm/cache.py`：cache/audit identity 的 provenance 字段统一为可选元数据（缺失记为 ""，`verified_*` 固定 False），避免 None/字符串规范化不一致破坏 HMAC 缓存校验；`public_source_url`/`source_commit_sha` 仍作为 cache/audit 追溯元数据保留（用于区分不同源码与记录来源），不再参与任何失败判定。
- `GitHubPublicSourceVerifier` 与 `verify_local_checkout_at_commit` 等保留为可选工具（不再被门禁路径强制调用）；benchmark 的 `--source-overrides` 同样保留为可选增强（显式提供才校验其格式与 checkout 绑定），不再是 full plan 门槛。
- 重新生成 205-target formal plan：`results/java_web_dos_batch/java-web-205-formal-ready-gate23-20260818/`，205 全部 queued，digest `7fb0dc310b1523fedb084b7596e8568170d9349b248f808c88ee3382bb608023`。
- PoC-29 benchmark full plan 不再因缺 public commit attestation 而 fail closed；对应 plan digest 更新为 `bc40e56958f89a731c2fc871d49392ca5d30f8dea5c1e504ac5e22d07e7031fb`。
- 更新 README、AGENTS、corpus 与 research 文档口径：由“178 queued + 27 paused / tree-only paused”统一为“205 全部 queued，不需要 git-commit provenance”。

### 验证
- `python3 -m pytest -q`：611 passed、9 skipped、436 subtests passed、2 warnings。
- `python3 -m compileall -q dosweb scripts tests`、`git diff --check` 通过。
- 定向回归：`test_deepseek_client.py` 108 passed / 141 subtests；`test_batch_runner.py`、`test_batch_plan.py`、`test_benchmark_truth.py` 全绿。

### 保留
- 显式 `--allow-remote-llm` 授权、非空 API key、可读本地源码目录仍是 remote LLM 的硬门槛。
- API key 永不进入 report/日志/提交/artifact；`config/local_secrets.json` 仍为 gitignored 0600。
- 历史结果资产（`poc29-full-plan-20260810`、`java-web-205-ready-plan-20260810`）未改写。

## [2026-08-18] Complete approved P0 Gate 2/3 and true-positive formal canary

### 修改时间
2026-08-18

### 变更类型
- [修复]
- [分析语义]
- [安全]
- [测试]
- [文档]

### 核心改动
- Growth stage 现在先执行真实 `EntryToGrowth.ql`，bounded slice 同时包含 Entry handler、registration、Growth site 与 CodeQL proven flow facts；删除在 Growth site 无条件合成 attacker `source` fact 的行为。没有 matching proven flow 时，LLM `yes` 也无法生成 verified Growth。
- `EntryToGrowthAssociations.ql` 补齐严格 13 列别名和 G1 materialization anchor；Spring MVC/Servlet/Netty/MQTT 使用真实 qualified API，Servlet request accessor 结果作为受支持 attacker source，same-handler flow 可 proven，跨过程/custom 模式保持 partial。
- G1 materialization demand 改为 `size`；`submit(task)` 改为 `value`。Container/async query 区分无 enclosing loop 的单次操作与 loop multiplicity 未建模，A1 不再把单次 `put/submit` 当单请求放大。
- Entry security 提取改为 bounded、source-root-contained、拒绝 symlink 的显式 annotation evidence；`@PermitAll`/`permitAll()`、`isAuthenticated()`、role-based annotation 分别映射可验证的 unauthenticated、low-privilege、privileged facts，Auth verifier 要求 cited fact 语义与模型结论匹配。A1 与 A2 均消费 ReachabilityDecision。
- lifecycle linker 修复 `analysis_source_root` wiring，按 `(E,G,path,family)` 发布 coverage；candidate-only query 的无匹配结果继续 partial，不能伪造 absence。有限 `ArrayBlockingQueue` 容量从构造器 literal 提取，checked submission 可得到 effective Bound；字面量 Guard/Bound 不再错误要求外部配置。
- 修复 Netty bootstrap 类型绑定；补真实 Spring/Servlet/Netty/MQTT package stubs、Servlet `@WebServlet` 和 FilterRegistrationBean positive fixture、uninstalled Netty initializer negative fixture。
- 新增完整 production executor/artifact/report 测试：受约束 Auth + verified Growth + proven flow 在 lifecycle absence 未证明时生成 certificate-backed `static_unknown` finding，验证 fail-closed 全链而不伪造 vulnerability。
- 应用 modeled configuration 改为 lifecycle/security key allowlist 与安全 typed value；password/token/api-key/credential/private-key 等键和任意业务字符串不再写入 artifact 或发送给 LLM。remote provider 现在强制 public GitHub URL、origin、公开仓库 API 与 commit SHA 同时验证，`verified_public=false` 禁止请求。
- Auth cache 条目纳入全局 entry/byte 容量锁；resume 原子更新根 run identity 并记录前一 identity hash；production downstream 从同一已认证 FD 读取 bytes snapshot，消除验证后重新按路径打开的 TOCTOU 窗口。
- 基于源码文本的 Guard 与 finally Release 候选统一降为 partial，不再声称 CFG dominance/post-dominance 或 normal+exception path complete，从而阻止 false-bounded。
- schema/tool 保持 `2.4/0.3.0`；更新 README、approved design、AGENTS 和 2026-08-17 compliance audit 状态说明。历史 plans/results/cache 不改写。
- corpus 口径统一为 **205 个库**，全部 active 文档将 “178-target full” 更正为 “205-target full”。（后随用户授权移除 git-commit provenance 门槛，205 全部 queued，见顶部条目。）
- DeepSeek API key 改由 gitignored 的 `config/local_secrets.json` 提供（`deepseek_api_key`），环境变量 `DEEPSEEK_API_KEY` 仍可优先覆盖；读取时用同一 FD 强制 owner UID、regular、精确 `0600` 和 4KiB 上限，不安全文件以 `CONFIG_SECRET_FILE_UNSAFE` 拒绝。`load_config` 新增 keyword-only `secrets_path`，batch/scripts 统一经 `resolve_api_key` 解析。
- 新增硬门槛 2/3 解决方案 `docs/research/2026-08-17-v2-p0-gates-2-3-solution-plan.md`：bounded CFG-effective Guard/Bound/Release、depth≤1 跨过程 wrapper、循环倍数证明，以及十场景 production E2E harness 与验收顺序。
- G3/G4 amplification 现在复用 `LoopAmplification.qll` 的真实 P0 handler/source → `LoopStmt` condition global-dataflow witness；仅 loop body 的 field-backed write/submission 才可标记 `attacker_controlled_loop_multiplicity_proven`。single/fixed/unknown loop、fan-out 仍为 unknown，finite queue 明确阻止 `proven`；production 再次检查 witness note，不能按 demand role 推断放大。
- Gate 3 最终实现：Guard 要求同一 attacker origin 同时流入 condition 与 Growth demand，并验证 CFG 节点顺序、终止 reject 与不可达性；Bound 仅认可 `ArrayBlockingQueue`/`LinkedBlockingQueue` literal hard capacity + `if (!offer) return/throw`；Release 区分 finally complete 与 success-only ineffective；depth≤1 wrapper 仅接受 uncaught direct throw，return/caught/post-order/depth3 均显式非 effective/partial。Map initial capacity 永不作为 bound。
- 新增 `LifecycleCoverage.ql`、`LifecycleSummary.ql`、`FiniteQueueDomain.qll` 与严格 decoder/schema/production linking；candidate-only 零行不再证明 absence，direct/nested custom/reflection 保持 partial；partial association 生成 certificate-backed `static_unknown`，不再停在内部 disposition。
- Gate 2 完成：`tests/support/fixture_database.py` 使用真实 javac + CodeQL DB，`tests/support/mock_deepseek.py` 使用真实 DeepSeekClient 仅替换 transport/verifier；`tests/test_production_e2e.py` 覆盖 Spring P0 1–8、Servlet、Netty、MQTT 的 finding/certificate/report/audit/resume 精确语义。
- DeepSeek live canary 修复真实阻塞：GitHub attestation 改用 bounded git-commit API、缓存同一 checkout attestation、source blob 上限与 extractor 对齐、JSON mode + v3 strict prompt、private audit 的语义 authorization 文本不再误判凭据；API key 仍不进入 tracked 文件/artifact。
- Erupt/Citrus/DataCompare 三个动态真阳性 seed formal static canary 全部 completed，0 query diagnostics，resume stage hash/time 全复用，0 credential leak；目标均保守输出 certificate-backed `static_unknown` 并记录具体 auth/flow/lifecycle gap，truth 仅 post-hoc。
- 发布新 205-target formal plan：`results/java_web_dos_batch/java-web-205-formal-ready-gate23-20260818/batch_plan.json`，205 targets 全部 queued，digest `7fb0dc310b1523fedb084b7596e8568170d9349b248f808c88ee3382bb608023`；未启动执行。

### 验证
- offline：`611 passed、9 skipped、437 subtests passed、2 warnings`。
- real CodeQL entry/growth：`5 passed、30 subtests`；real lifecycle：`3 passed、50 subtests`。
- production E2E：4 个真实 framework tests 全部通过；P0 aggregate test同时验证非空 private audit、0600、首轮 provider 请求及全 stage resume hash/time 不变。
- `python3 -m compileall -q dosweb scripts tests`、`git diff --check` 通过；direct/embedded pack 字节一致；0 个 execution snapshots。
- Gate 3 fresh reviewer 最终：0 BLOCKER / 0 HIGH；canary fresh reviewer：全部 PASS。

### 明确保留的 deferred 边界
- depth>1 arbitrary lifecycle、custom/reflection dispatch、异步 Release capacity、producer/consumer rate、TTL/timeout、WebSocket、任意 custom protocol 继续输出 partial/`static_unknown`；这不是 Gate 2/3 未完成项。
- 205-target formal plan 已 ready，但执行仍是独立授权操作，本次没有启动全量批次。

## [2026-08-17] Close cache-hit audit replay and real-framework flow fixtures

### 修改时间
2026-08-17

### 变更类型
- [修复]
- [安全]
- [测试]

### 核心改动
- Growth cache 升至 `growth-contract-cache-v6`：成功 entry 以私有、HMAC、原子方式保存有界 exact provider body、parsed contract 与 hash；cache hit 的 audit 现在可完整回放，旧格式不复用。
- Auth Contract 从 process-local dict 扩展为独立的私有 HMAC/atomic persistent cache；fresh client cache hit 仍保留 exact raw response，且不写入 key/header/environment。
- Spring MVC、Servlet、MQTT fixtures 改为真实 framework qualified API stub；Flow query 只以真实 Spring/Servlet/Netty/MQTT source 为入口，`submit(task)` 仅是 task/value，不再假称 submission count。
- 同步 direct/embedded Growth pack；复核 lifecycle direct/embedded query 一致、无 execution snapshot。高级 field/alias、多 wrapper、reflection/custom dispatch、未证明 loop/fan-out 仍显式 partial，不升级为 complete。

### 验证
- `python3 -m pytest -q tests/test_deepseek_client.py`：107 passed、141 subtests passed。
- `python3 -m pytest -q tests/test_codeql_entry_queries.py tests/test_codeql_growth_queries.py tests/test_flow_verification.py tests/test_deepseek_client.py`：116 passed、3 skipped、155 subtests passed。
- `python3 -m pytest -q tests/test_codeql_lifecycle_queries.py tests/test_lifecycle_evidence.py tests/test_lifecycle_bounds.py`：15 passed、1 skipped、31 subtests passed。

## [2026-08-17] Bind lifecycle screening to E→G paths

### 修改时间
2026-08-17

### 变更类型
- [修复]
- [分析语义]
- [测试]

### 核心改动
- 新增 `LifecycleEvidence` 和 `LifecycleCoverage` artifacts；每条 relevant flow 的 Guard/Bound/Release family 都有 coverage record，conclude 缺失任一 family coverage 时 fail closed。
- lifecycle executor 不再把全局候选传给每条 flow；现在要求同一 Java callable，且 Bound/Release 必须与 Growth 的 canonical receiver 一致。带 complete same-callable witness 的候选才可进入 effective 判定；跨 handler、纯字符串 receiver、alias/custom/interprocedural 模式保持 partial。
- Guard/Bound/Release evaluator 只有 coverage complete 且无候选才返回 absence；partial/unsupported empty coverage 返回 unknown。production 现在消费 entries 产生的 modeled configuration facts，拒绝 conflicting default configuration。
- artifact/pipeline schema 升至 2.4，旧运行不可 resume。

### 验证
- `codeql query compile dosweb/codeql/pack/dosweb/Lifecycle/*.ql`
- `python3 -m pytest -q tests/test_lifecycle_guards.py tests/test_lifecycle_bounds.py tests/test_lifecycle_releases.py tests/test_production.py tests/test_certificates_and_reports.py`：83 passed、65 subtests passed。
- `python3 -m compileall -q dosweb scripts`、`git diff --check`。
- 后续补强：Guard/Bound/Release lifecycle query 增加 same-callable CFG-shaped complete witness；Netty fixture 覆盖 checked finite queue 与 finally remove；`tests/test_lifecycle_evidence.py` 覆盖跨 handler 候选不可复用。

## [2026-08-17] Make candidate completeness and assertion applicability fail closed

### 修改时间
2026-08-17

### 变更类型
- [修复]
- [分析语义]
- [测试]

### 核心改动
- 增加 candidate-entry partial association、candidate disposition 和 repeatability/amplification decision artifact schemas；raw Growth 无 Entry 不再 silent continue。
- 旧 source-order association 明确标为 partial；没有完整 call-graph evidence 时不能伪装为 formal relevant association。无 Entry 的 complete screening 记录 `not_entry_reachable`，不完整 coverage 记录 `unresolved`。
- flows 对已关联 Growth 的零 CodeQL row 发布 partial flow，而非遗漏；A1 仅接受 direct size demand 或 proven amplification，A2 可接入受约束 reachability/repeatability decision。

### 验证
- `python3 -m pytest -q tests/test_candidate_completeness.py tests/test_production.py tests/test_assertions.py tests/test_certificates_and_reports.py tests/test_flow_verification.py`
- `python3 -m compileall -q dosweb tests`
- `git diff --check`

## [2026-08-17] Wire constrained Auth/Growth provider audit artifacts

### 修改时间
2026-08-17

### 变更类型
- [修复]
- [安全]
- [测试]

### 核心改动
- 将 constrained Auth Contract 接入 formal growth：Entry security/configuration facts 是唯一输入；Auth transport/schema/provider failure 沿用 DeepSeek fail-closed 行为；无 transport 的离线 test seam 只能得到 `unknown`。
- growth 发布 `auth_contracts.jsonl`、`reachability_decisions.jsonl` 与 0600 的 `llm_audit.private.jsonl`。Growth/Auth audit 记录 normalized prompt、bounded raw envelope、parsed contract、非秘密 settings、attestation 和 cache hit；正式 contract/artifact 不含 provider envelope。
- Growth prompt/cache identity 升为 v2；Auth 使用独立 prompt/schema 与独立内存 identity cache。具体 bounded slice 校验会绑定 configured GitHub origin，防止 standalone provider 调用将无关 checkout 伪装成公开来源。
- private audit 拒绝 Authorization/API-key 字段；pipeline 对 `.private.jsonl` 强制 0600。

### 验证
- `python3 -m pytest -q tests/test_configuration_reachability.py tests/test_deepseek_client.py tests/test_production.py`：140 passed、141 subtests passed、2 warnings。
- `python3 -m compileall -q dosweb`
- `git diff --check`

### 已知限制
- Auth cache 当前为 process-local；跨进程持久 HMAC auth-cache 和 raw provider body 的 cache-hit 保留需要随下一次 cache-format migration 落地。cache hit audit 明确以空 raw body 标记，不伪造远端响应。

## [2026-08-17] Modeled defaults and constrained reachability artifacts

### 修改时间
2026-08-17

### 变更类型
- [修复]
- [安全]
- [测试]

### 核心改动
- schema/tool 版本升至 2.2/0.3.0；entries 离线发布严格 `modeled_configuration.jsonl` 和 `entry_security_facts.jsonl`，并以 source-root-contained、无 symlink、有限文件/字节数的 extractor 解析 properties/YAML/web.xml 默认配置。
- 新增 `analysis.modeled_defaults` 和重复 `--modeled-default key=value`，CLI 覆盖配置文件和提取默认值，且 provenance 写入 artifact。
- 新增受约束 Auth Contract/ReachabilityDecision/LlmAuditRecord 模型与 verifier：模型引用超出 security slice、跨 Entry 或不完整 public-security coverage 时 fail closed/unknown；privileged 产生显式 not-entry-reachable。
- 更新 README 和 approved design 接口说明；未启动远程 provider、未改写历史 results。

### 验证
- `python3 -m pytest -q tests/test_configuration_reachability.py tests/test_config_and_cli.py tests/test_production.py`
- `python3 -m compileall -q dosweb`

### 已知限制
- Auth Contract 的 provider transport/cache/audit JSONL production wiring 将在下一批接入；本批优先完成严格模型、离线提取、schema 和 deterministic verifier。

## [2026-08-17] P0 formal/exploratory execution boundary and artifact identity baseline

### 修改时间
2026-08-17

### 变更类型
- [修复]
- [安全]
- [测试]

### 核心改动
- formal entries 对选中 CodeQL query failure 改为 fail-closed，不发布 entries manifest；仅显式 `entries --allow-partial-codeql` 可将该失败记录为 coverage gap。
- exploratory entries 的 config fingerprint、run/stage identity 和 metadata 记录 `analysis_mode=exploratory_entries`、`query_failure_policy=coverage_gap`；formal 使用独立 `formal/fail_closed` identity，避免复用 exploratory stage。
- schema/tool 版本升至 2.1/0.2.0；stage manifest 增加非秘密 identity、started/ended/duration；run.json 增加 terminal 时间和 error 记录。
- upstream schema/hash 错误分别映射为 `ARTIFACT_SCHEMA_MISMATCH` 与 `ARTIFACT_UPSTREAM_HASH_MISMATCH`；Markdown report 拒绝 orphan certificate。
- 新 batch plan schema 使用 immutable `analysis_mode` 与 `query_failure_policy`；旧 v1 plan 保留可读取，不能伪装成新 formal plan。

### 验证
- 覆盖 formal abort、exploratory coverage gap、batch plan identity、artifact hash/schema mapping、certificate 双向一致性和 pipeline recovery 的定向 pytest。

### 影响与边界
- 不修改历史 plans/results，不实现 auth/flow/lifecycle/LLM audit 的后续大改；205-target formal full 继续暂停。

## [2026-08-17] P0 Entry/association/global-flow fourth repair batch

### 核心改动
- 新增 `EntryToGrowthAssociations.ql`，production Growth stage 只接受 complete handler/growth association；遗留 source-order 关系仅为 partial 审计证据。
- `EntryToGrowth.ql` 改用 CodeQL `DataFlow::Global`；真实 Spring MVC、Servlet、Netty、MQTT qualified API 才是 source，`submit(task)` 标记 value 而非 submission count。
- Netty complete entry 需要 `ServerBootstrap.childHandler/handler` 安装 initializer；未安装 initializer 产 partial gap。
- flows 对被 Growth Contract 拒绝的 raw screening row 先过滤，避免为不存在的 verified Growth 构造引用错误。

### 验证
- `codeql query compile`：`NettyEntries.ql`、`EntryToGrowth.ql`、`EntryToGrowthAssociations.ql` 通过。
- 相关 pytest 与 `compileall` 通过；详见本次工作记录。

## [2026-08-17] Re-audit v2 production code against the approved P0 design

### 修改时间
2026-08-17

### 变更类型
- [审计]
- [文档]
- [测试]

### 核心改动
- 以 `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md` 为唯一 P0 标准，对 pipeline、CodeQL E/G/flow、lifecycle、assertions、provider、batch、benchmark 和测试做零信任复核；新增 `docs/research/2026-08-17-v2-p0-design-compliance-audit.md`。
- 校正上一轮只聚焦 corpus/entries readiness 的结论：205 entries 仍可做覆盖侦察，但 production E→G、candidate completeness、lifecycle path binding/default config、Assertion applicability、provider replay/provenance 尚有 P0 blockers，205-target 正式 full 实验继续暂停。
- 记录可执行反例：persistent `container_growth(key)` 即使存在 effective synchronous Release，当前 A1 仍 matched，导致 A2 refuted 后最终仍为 `static_vulnerable`。
- 在 `docs/research/2026-08-14-v2-lifecycle-analyzer-audit.md` 顶部增加后续校正链接，避免 corpus Gate-A 结论被误读为完整 P0 合规。

### 验证
- `python3 -m pytest -q tests/test_assertions.py tests/test_flow_verification.py tests/test_growth_verification.py tests/test_lifecycle_guards.py tests/test_lifecycle_bounds.py tests/test_lifecycle_releases.py tests/test_certificates_and_reports.py tests/test_p0_end_to_end.py tests/test_production.py tests/test_deepseek_client.py tests/test_batch_plan.py tests/test_batch_runner.py tests/test_benchmark_matching.py`
- 结果：262 passed、233 subtests passed、2 warnings。
- 通过静态检查确认 approved design 要求的 `ARTIFACT_SCHEMA_MISMATCH`、`ARTIFACT_UPSTREAM_HASH_MISMATCH` 尚未实现；`run.json` 也未记录完整 CodeQL/provider/prompt/timing identity。

### 依赖与影响
- 本轮不修改 analyzer 源码、CodeQL 规则或历史 results，只发布审计证据和修复优先级。
- Assertion 3、异步 Release capacity、TTL、WebSocket、ML/GNN 和动态执行仍按 approved P0 明确 deferred，不误报为本轮 blocker。

## [2026-08-16] Repair canonical corpus integrity and restore P0 attestation gates

### 修改时间
2026-08-16

### 变更类型
- [Bug 修复]
- [功能改进]
- [测试]
- [文档]

### 核心改动
- tree fingerprint 精确排除 source snapshot 下由分析器生成的 `results/applications_static_analysis/**`，同时继续计入项目自身的其他 `results` 文件；配置层拒绝继续向该保留子树写入新 v2 输出。
- 重新生成 Java Web 205 inventory，保持 205 个 source/database pair 全部 ready，并同步 README 的 205/0 readiness 口径。
- 恢复 `public_source_url`、`source_commit_sha`、clean checkout/commit 校验和 detached worktree fallback；full plan 对缺少 Git provenance 的 tree-only targets 标记 paused，entries 仍允许本地分析。
- Entry preflight 现在区分 framework evidence absent、evidence scan truncated 和 query failed；失败 query 的裁剪诊断写入 stage metadata，所有未覆盖框架显式进入 `coverage.json`。
- benchmark 唯一匹配结果新增可回放的 finding/entry/growth/flow/certificate ID 链。
- DeepSeek cache identity/audit 与完整 public-source attestation 契约重新对齐，避免恢复 commit/clean-checkout 证明后 cache 写入被错误拒绝。
- 发布 205 entries 非执行计划（205 queued）和 full-ready 非执行计划（178 queued、27 tree-only paused；历史口径，后于 2026-08-18 移除 provenance 门槛改为 205 全部 queued）；两者均未调用真实 provider。
- 将 pytest 默认 collection 根限定为仓库自身 `tests/`，避免误收集 205 source snapshots 内第三方测试插件。
- PoC-29 benchmark normalization 只读取其冻结的历史 audited batches；现行 binary truth 增长到 33 条时不再悄然改变 PoC-29 oracle 和 18-repository corpus。
- 全部 Entry query 现在要求入口行来自源码（`fromSource()` / `.java` path），过滤依赖 JAR 里解析出的 `.class` 字节码行；修复 Druid/Presto 上 `JaxRsEntries.ql` 因 `LINE_INVALID`（line=0 的字节码行）触发 "decoded result violates its query contract"、导致整条 query 被 fail-closed 丢弃的问题。
- 同步 `codeql/dosweb/Entries/` 与 `dosweb/codeql/pack/dosweb/Entries/` 两份 query 镜像，满足字节一致契约。
- 重算 `config/poc29_full_source_overrides.json` 的 `analysis_tree_sha256` 与 tree fingerprint 新口径一致；PoC-29 full plan digest 由 `35fcae172671ea29b6ceacfeb0a99613ac2b3a3a08d7da3d1b5eaedf4c08d8a4` 更新为 `6c81990e0877c21df662dfba8676ebd133807032816cc9dc200c29ac9b65d808`，同步更新 `docs/java-web-205-corpus.md` 与测试冻结值。
- `test_benchmark_truth.py` 的 invalid-truth fail-closed 用例补 `source_batch: "p0"`，与冻结 batch 过滤口径一致。

### 验证
- `python3 -m pytest -q tests/test_config_and_cli.py tests/test_batch_runner.py tests/test_production.py`
- `DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_codeql_entry_queries.py tests/test_codeql_growth_queries.py tests/test_codeql_lifecycle_queries.py`
- `python3 -m pytest -q tests/test_deepseek_client.py`（通过，123 tests/subtests）
- `python3 -m pytest -q tests/test_java_web_205_inventory.py`
- PoC-18 entries Gate-A batch：`results/java_web_dos_batch/poc18-entries-gatea2-20260816/`，18/18 completed、0 failed；首轮 Druid/Presto 各出现 1 条 JAX-RS `bqrs_decode` 诊断，修复后重跑 `results/java_web_dos_batch/druid-presto-entries-fix-20260816/` 得到 0 diagnostics、`jax_rs` 恢复 `complete`。
- 全套离线测试：`python3 -m pytest -q` → 572 passed、5 skipped、422 subtests passed；`python3 -m compileall -q dosweb scripts` 通过。
- 205 entries plan digest：`dff06ae8ccf57c0551735e97cb251551f1b102dede40b5c297471050a16425e5`。
- 205 full-ready plan digest：`433a0ee83213a45eed5e77dab1d4ac2a112ec1339dfd4a4cb52f9b4c9ade2d5c`。

### 依赖与影响
- 不删除或移动历史 source-local analyzer outputs；只将其从源码身份 hash 中排除，避免运行分析改变 canonical source identity。
- 本轮不使用真实 DeepSeek；full provider canary 仍需显式凭据和授权。

## [2026-08-15] Scope Codex skills to Java Web DoS and research workflows

### 修改时间
2026-08-15

### 变更类型
- [配置]

### 核心改动
- 新增项目级 `.codex/config.toml`，仅启用 3 个 Java Web DoS skill 与现有科研、论文、实验和学术检索 skill。
- 在本项目范围禁用 Sites、Visualize、Superpowers 插件、默认 Apps/Connectors、remote plugin catalog，以及系统、Seagull、Figma、GitHub、模板等无关 skill。
- 用户级 `~/.codex/config.toml` 未改动；离开本仓库后不受影响。

### 验证
- 使用 Python `tomllib` 解析 `.codex/config.toml`，断言启用 37 个 skill、禁用 66 个 skill，且仅包含 3 个 `java-web-dos-*` skill。
- 检查插件、Apps/Connectors 与 remote plugin catalog 的项目级禁用开关。

### 依赖与影响
- 需要重新启动该仓库中的 Codex 会话，现有会话不会热更新启动时注入的 skill 描述。

## [2026-08-15] Archive four newly confirmed application PoCs and refresh current truth counts

### 修改时间
2026-08-15 01:35

### 变更类型
- [文档]
- [功能改进]

### 核心改动
- 在 `poc/` 下新增 4 个最新 confirmed application PoC 归档：`grobidorg__grobid-GROBID-STATIC-001`、`grobidorg__grobid-GROBID-STATIC-002`、`jetlinks__jetlinks-community-JL-STAGEA-0001`、`walmartlabs__concord-fnd3`。
- 为每个新归档补齐双语 advisory、`reproduce.sh` 与 `attachments/` 证据索引，复用 `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/*` 下的 `result.json`、`case_plan.json`、`environment.md`、probe 和关键日志摘录。
- 将当前现行计数口径从 29 更新到 33，并同步刷新 `poc/README.md`、`poc/manifest.json`、`results/applications_dynamic_validation/binary_truth_collection.json`、`results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md` 以及研究笔记中“当前 confirmed positive 数量”的表述。
- 保留 `PoC-29`、`29 truths`、`29 cases across 18 repositories` 等历史 benchmark 名称不变，不做机械替换。

### 验证
- `python -m json.tool poc/manifest.json`
- `python -m json.tool results/applications_dynamic_validation/binary_truth_collection.json`
- 检查 `poc/README.md` 的数量与目录表是否更新为 33
- 检查新建 4 个 `poc/` 目录是否包含 advisory、`reproduce.sh` 和 `attachments/ATTACHMENTS.md`

### 依赖与影响
- 仅整理 PoC 归档与现行计数字段，不修改业务源码和原始动态验证结果目录。
- `results/applications_dynamic_validation/binary_truth_collection.*` 的当前真阳性计数现为 33，可继续作为 `poc/` 的现行来源索引。

# dos-analysis-web v2 CHANGELOG

## [2026-08-15] Allow larger source files in Growth excerpts

### 修改时间
2026-08-15 01:02

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 将 `dosweb/growth/excerpts.py` 的单文件源码摘录上限从 16 KiB 放宽到 1 MiB，避免真实仓库中体积较大的资源类被误判为 `SOURCE_FILE_INVALID`。
- 保留原有本地源码树安全约束：路径规范化、regular file、UTF-8、读取期间 inode/mtime 不变与 excerpt 自身大小受控；本轮仅移除对正常大型源码文件过严的体积门槛。
- 该修复直接恢复了 Dependency-Track `BomResource.java` 这类真实 `growth` 入口的 slice 构造，为继续推进 `POST /v1/bom` 的 growth/flows 分析扫清前置阻塞。

### 验证
- 计划复跑 `tests/test_source_excerpts.py` 与 Dependency-Track fake/full pipeline，确认大文件不再触发 `SOURCE_FILE_INVALID`。

### 依赖与影响
- 仅放宽本地源码读取上限，不改变 excerpt 输出 schema 与 bounded slice 总体积约束。
- 对较大的真实源码文件，Growth 阶段不再因为文件体积而提前失败。

## [2026-08-15] Cap lifecycle decision checks for large candidate sets

### 修改时间
2026-08-15 00:38

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 修复 `dosweb/production.py` 中 lifecycle decision artifact 的序列化逻辑：当 guard/bound/release 候选很多时，`checks` 现在按稳定顺序截断到 schema 允许的 64 条，不再因大仓库候选噪声把 `lifecycle_results.jsonl` 写出阶段直接打爆。
- 保持 `status`、`reason_codes`、`evidence_ids`、`candidate_ids` 与 `classification` 原样输出，只限制诊断性 checks 明细的体积，避免 Zipkin 这类 Armeria handler 恢复 flow 后马上在 lifecycle artifact 上失败。
- 该修复让本地 verified Growth 合同调试可以继续推进到 conclude/report，用于分离真正的生命周期/结论问题与单纯的 artifact schema 容量问题。

### 验证
- 计划复跑 Zipkin fake verified/full pipeline，检查 `lifecycle_results.jsonl`、`lifecycle_certificates.jsonl`、`static_findings.jsonl` 是否能完整生成。

### 依赖与影响
- 仅影响 lifecycle artifact 的诊断性 checks 明细大小，不改变 guard/bound/release 决策语义。
- 同步把 lifecycle artifact schema 中 decision collections/checks 的容量上限从 64 放宽到 256，以匹配真实仓库候选规模，避免 schema 限制把后续 conclude/report 阶段误阻塞。

## [2026-08-15] Restore packaged flow forwarding for Armeria helper sinks

### 修改时间
2026-08-15 00:20

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 同步修复打包版 `dosweb/codeql/pack/dosweb/Flows/EntryToGrowth.ql`，补齐与直连版一致的 helper forwarding 语义，不再把 flow 命中限制为 handler 方法体内的同方法 sink。
- 让 Armeria `@Post` handler 将 `HttpRequest` 继续传给 helper 后，helper 内部的 `aggregateWithPooledObjects(...)` 仍可被识别为 `entry -> growth` 候选，覆盖 Zipkin `uploadSpans(...) -> validateAndStoreSpans(...) -> aggregateWithPooledObjects(...)` 这类真实链路。
- 本轮保持 growth/local-source 直读模型不变，只修复 packaged CodeQL query 与直连 query 之间的语义漂移，避免 fake/full pipeline 在 `flows` 阶段出现 0 命中。

### 验证
- 计划复跑 Zipkin fake/full pipeline，重点检查 `flow_proofs.jsonl`、`lifecycle_results.jsonl`、`static_findings.jsonl` 与 `report.md` 是否恢复非空产物。

### 依赖与影响
- 仅修改仓库内打包版 CodeQL flow 查询与 changelog，不修改目标应用源码。
- 该修复直接影响 packaged query 驱动的 `flows` 阶段，并为后续 Zipkin 以及同类 handler->helper 路径恢复静态流证明。

## [2026-08-15] Tighten rill-flow strict-default blockers after compose and companion re-check

### 修改时间
2026-08-15 00:12

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只处理 `weibocom__rill-flow-F-002` 与 `weibocom__rill-flow-F-003`，先复读两个 case 的 `result.json`，再复核仓库官方 `docker/docker-compose.yml`、`README.md`、`docs/samples/executor/main.py`、`docs/samples/parallel-async-dag.yaml`、`rill-flow-web/src/main/resources/application.properties`、`FlowAuthHeaderGenerator.java` 与当前隔离环境容器状态，专门回答 strict default 下是否还存在被错判为 non-default 的 companion 路径。
- `F-002`：确认此前 default 与 helper 的边界并未画得过严。官方 compose 仅交付 `rill-flow`、`ui`、`sample-executor`、MySQL、Redis、Jaeger；仓库内没有任何 Kafka broker/ZooKeeper/KRaft companion 或可直接归入 default 的同仓资产，因此 strict default 下只能做到 Kafka 注册路由 reachability，不能形成真实 broker/consumer 语义闭环。
- `F-003`：确认此前 blocker 还能进一步收紧，但仍不能转成 default 闭环。新证据显示并非“sample-executor 自带 callback 语义天然非默认”，而是 shipped backend 实际读取的 `rill.flow.server.host` 默认值是 `http://127.0.0.1:8080`，而 compose 仅设置了未被该路径消费的 `RILL_FLOW_CALLBACK_URL=http://rill-flow:8080/flow/finish.json`。实测从 `sample-executor` 容器访问 `127.0.0.1:8080/flow/finish.json` 直接 connection refused，而访问 `http://rill-flow:8080/flow/finish.json` 可达，说明 default blocker 精确收敛为“官方 compose 与应用实际 host 配置键不匹配”。
- 同步更新两个 case 的 `result.json` 与 `environment.md`，把上述更精确 blocker 写回工件；未修改目标业务源码，也未把任何 helper 证据重归类成 default success。

### 验证
- `docker inspect weibocom__rill-flow-default-rill-flow-1 --format '{{range .Config.Env}}{{println .}}{{end}}'`
- `docker exec weibocom__rill-flow-default-sample-executor-1 python -c "import requests; ..."` against `http://127.0.0.1:8080/flow/finish.json` and `http://rill-flow:8080/flow/finish.json`
- `docker logs --tail 120 weibocom__rill-flow-default-sample-executor-1`
- repository reads of official compose/sample/backend config assets listed above

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/weibocom__rill-flow-F-002`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/weibocom__rill-flow-F-003`

### 依赖与影响
- 本轮未修改任何目标业务代码。
- 当前最精确结论为：`F-002` strict default 仍缺少仓库内 Kafka companion，无法闭环；`F-003` strict default 仍受 shipped callback host 配置不匹配阻塞，也无法闭环；两案都没有新增可重归入 default 的 companion 证据。

## [2026-08-14] Tighten dromara lamp-cloud dynamic blocker after assisted sibling-asset replay

### 修改时间
2026-08-14 22:20

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只处理 `dromara__lamp-cloud-FND-001`，先复读既有 `result.json`、`environment.md`、环境目录日志、仓库 `README.md`、`lamp-dependencies-parent/pom.xml`、`OpenApi3Controller.java` 与 docker/Nacos 文档，确认默认结论不能被“可辅助运行”证据覆盖。
- 在用户授权的最小非默认诊断路径下，新增官方 sibling `lamp-util` `java17/5.x` 源码补齐验证：将其 5.10.0 工件安装到本地 Maven 仓库后，成功重新构建 `lamp-gateway-server`、`lamp-base-server`、`lamp-system-server`，证明此前 default blocker 确为缺失 sibling parent/依赖，而不是业务代码或仓库内容损坏。
- 继续用隔离辅助栈验证“补齐 sibling 后能否跑通 baseline”：导入仓库自带 Nacos 配置包、拉起独立 MySQL/Redis/Nacos 并启动 gateway。结果显示当前 5.10.0 构建物经 `lamp-util` 引入 `nacos-client 3.2.1`，而仓库文档/资产仍围绕 Nacos 1.1.3/1.3.1；辅助 runtime 中导入结果虽返回 success，但运行时仍将相关 dataId 视为空配置并最终以 `Failed to determine suitable jdbc url` 退出，说明 blocker 已从“完全不可构建”收紧到“官方 sibling 补齐后仍受 control-plane/config 兼容缺口阻塞”。
- 同步更新 case `result.json`、`environment.md`、环境 `feasibility.json` 与批次 `validation_status.jsonl`：明确 default 结论仍为 `environment_blocked`，辅助路径只作为 separated evidence 记录“可编译但未可运行到语义 preflight”。

### 验证
- `git clone --depth 1 --branch java17/5.x https://github.com/zuihou/lamp-util.git /home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/work/lamp-util-java17-5x`
- `mvn -q -DskipTests install` (in `.../work/lamp-util-java17-5x`)
- `mvn -q -pl lamp-gateway/lamp-gateway-server -am -DskipTests package`
- `mvn -q -pl lamp-base/lamp-base-server -am -DskipTests package`
- `mvn -q -pl lamp-system/lamp-system-server -am -DskipTests package`
- bounded helper bootstrap with Docker `mysql:8.0`, `redis:7.2-alpine`, `nacos/nacos-server:1.3.1`, then `java -jar` for gateway/base jars

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- 辅助环境证据：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`
- 官方 sibling 工作区：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/work/lamp-util-java17-5x`

### 依赖与影响
- 本次未修改任何目标业务代码，也未把带外补齐 sibling `lamp-util` 或隔离 Nacos/MySQL helper 栈包装成默认验证成功。
- 当前最精确动态结论为：默认交付链仍 blocked；若仅补齐官方 sibling `lamp-util`，可恢复 5.10.0 构建，但仍会在 Nacos/client 与配置装载兼容层面卡住，因而尚不足以进入 `/v3/api-docs/swagger-config` 的受控动态探测。

## [2026-08-14] Re-run final two rill-flow dynamic cases and separate helper-only evidence

### 修改时间
2026-08-14 22:20

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只处理 `weibocom__rill-flow-F-002` 与 `weibocom__rill-flow-F-003`，先复读既有 case/result/environment/logs 后，在不改默认终态的前提下，各追加一轮严格分离的 helper-only 动态验证。
- `F-002`：默认口径仍因官方 compose 无 Kafka broker companion 而 `precondition_blocked`；新增 round-2 辅助证据 `kafka_auxiliary_growth_and_consume_20260814.json` / `kafka_auxiliary_cleanup_20260814.json`，记录临时 Kafka KRaft broker 下 trigger task 总数从 1 增至 511、跨过静态 500 worker 阈值，且 1 条 benign message 触发真实 `choiceSample` submit；随后取消 510 个临时 registrations 并停止 helper broker。
- `F-003`：默认口径仍因 shipped sample-executor async callback 指向 executor 容器内 `127.0.0.1:8080` 而 `precondition_blocked`；新增 round-2 辅助证据 `foreach_auxiliary_callback_and_integer_payload_20260814.json`，记录在 assisted callback completion 下官方 `parallelAsyncTask` 能真实完成 foreach 并得到 `callback_result_list [300, 600, 0]` 与 `sum 900`，从而把 blocker 精确收敛到 callback routing，而不是 payload 本身不可达；helper integer foreach descriptor 则仍在 bounded n=1/50/200 下因 sync dispatch timeout 失败。
- 同步更新两个 case 的 `result.json`、`environment.md`、`reflection.jsonl`、`rounds/round-2/*`、批次 `validation_status.jsonl`，并重新运行动态聚合脚本刷新汇总产物。

### 验证
- `python3` bounded HTTP probes against `http://127.0.0.1:18083` for `parallelAsyncTask`, `foreachSyncSample`, and Kafka trigger APIs
- `docker run --rm apache/kafka:3.7.0 ...` on network `weibocom__rill-flow-default_default` as a temporary helper broker, followed by `kafka-console-producer.sh`
- `python /home/furina/.qoder-cn/skills/java-web-dos-dynamic-validator/scripts/aggregate_dynamic_validation.py --output-root /home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本轮未修改任何目标业务代码，也未把 helper Kafka broker 或 assisted callback completion 包装成默认动态确认。
- 当前最精确结论为：`F-002` 与 `F-003` 的默认终态都仍是 `precondition_blocked`，但两者都新增了严格分离的 non-default helper 证据，说明默认 blocker 已分别精确收敛到“缺少官方 Kafka companion”和“sample-executor callback 路由错误”。

## [2026-08-14] Strengthen OpenMeetings assisted upload-conversion probe and keep default blocked verdict

### 修改时间
2026-08-14 22:15

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只处理 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`，先复读既有 `result.json`、`environment.md`、`reflection.jsonl`、`observations.json`、`preflight.json` 与已保存的 non-default `path.office` 辅助证据，确认默认路径 blocker 仍仅是宿主缺少可自动发现的 system-wide LibreOffice/OpenOffice。
- 在不改业务代码前提下，保留 case-local 官方 LibreOffice + 显式 `path.office` 作为最小 non-default 辅助修复，并把动态测试从先前 4 路极小 benign 上传强化为“真实 browser room context 下 12 路并发、每个约 641 KiB 的 benign `.docx` 同源 upload-conversion”。为避免丢失房间态，本轮使用 headless Chromium DevTools Protocol 在 live `/hash` 页面上下文内执行 `fetch`，而不是脱离浏览器会话直接重放请求。
- 新增 round-2 结构化产物与证据：一个仅提取 SID 后从浏览器外直连的控制性重放全部返回 `Access denied`，因此被明确记为语义失配对照；真正的 browser-context stronger probe 则 12/12 返回 `SUCCESS`，但线程仅短暂 `218 -> 230`、RSS 约 `792032 -> 802184 -> 799720 KiB`、`/openmeetings/signin` 与 `/openmeetings/ping` 全程 `200`，未见 OOM、重启、5xx、持续不可用或明确 conversion worker 持续堆积。
- 同步更新 case `result.json`、`environment.md`、`reflection.jsonl` 与批次 `validation_status.jsonl`，把“default-path 仍 blocked；non-default stronger probe 也未见 meaningful growth/failure；不得写成默认 confirmed”写清，并重新运行动态聚合脚本刷新汇总产物。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`
- 新增 round-2 证据：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS/rounds/round-2`
- 批次状态：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/validation_status.jsonl`

### 依赖与影响
- 本次未修改任何目标业务代码，也未把 case-local LibreOffice + `path.office` 辅助路径包装成默认部署成功。
- 当前最精确结论进一步收敛为：默认路径仍因缺少可自动发现的 system-wide office suite 而 `environment_blocked`；在授权的 non-default browser-context 强探针下也未见 meaningful growth/failure，因此该辅助结果仅是否定性补充证据。

## [2026-08-14] Re-run minimal Cryostat diagnostic bridge and separate packaged /api WS evidence

### 修改时间
2026-08-14 21:45

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只处理 `cryostatio__cryostat-legacy-F-WS-001`，先复读既有 case/environment/result/logs/source/docs 后，按本轮授权追加一次最小非默认 diagnostic datasource bridge replay，不改目标业务代码，只验证 notifications 语义是否真实存在以及能否进入有界动态探测。
- 新增 `logs/diagnostic_bridge_probe_20260814.json`、`diagnostic_bridge_app_20260814.log`、`diagnostic_bridge_db_20260814.log`、`diagnostic_bridge_inspect_20260814.json` 与 cleanup 日志；新证据表明在官方镜像 + 文档化 PostgreSQL companion + 未文档化 `QUARKUS_DATASOURCE_*` bridge 下，`/health` 可再次达到 200，但文档要求的 `/api/v1/notifications_url` 与 `/api/v1/notifications` 仍返回 SPA HTML，而原始握手对 `/api/notifications` 返回 `101 Switching Protocols`。
- 同步更新 `cases/cryostatio__cryostat-legacy-F-WS-001/{environment.md,result.json}`、环境 `readiness.json` / `changes.jsonl` 以及批次 `validation_status.jsonl`，把结论精确收敛为：默认口径仍因 datasource 契约失配 + `/api` vs `/api/v1` notifications 语义分歧而 `environment_blocked`；新拿到的 packaged `/api/notifications` WebSocket 仅作为非默认诊断证据保留，不能当作默认动态验证放行条件。

### 验证
- `docker run` official Cryostat image with documented PostgreSQL companion values plus the existing diagnostic `QUARKUS_DATASOURCE_*` bridge on isolated port `18188`
- `python3` one-shot HTTP/WS semantic probe writing `cases/cryostatio__cryostat-legacy-F-WS-001/logs/diagnostic_bridge_probe_20260814.json`
- `python /home/furina/.qoder-cn/skills/java-web-dos-dynamic-validator/scripts/aggregate_dynamic_validation.py --output-root /home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本轮仍未修改任何目标业务代码，也未把带 `QUARKUS_DATASOURCE_*` 的 diagnostic bridge 路径包装成默认验证成功。
- 当前最精确结论更新为：非默认 bridge 下确有 packaged `/api/notifications` WebSocket listener，但文档化 `/api/v1` notifications JSON/WS 语义仍未出现，因此 queued default case 不能进入有界动态探测，终态继续保持 `environment_blocked`。

## [2026-08-14] Remove pinned-source provenance gate and read local source trees directly

### 修改时间
2026-08-14 20:10

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 移除 Growth 阶段对 git commit / public source / clean checkout 的前置证明流程，`dosweb/growth/excerpts.py` 现在只忠实读取 `source_checkout` 下的本地源码文件并生成 excerpt，不再要求 pinned blob 一致性。
- 精简 `dosweb/config.py`、`dosweb/llm/cache.py`、`dosweb/llm/deepseek.py` 与 `dosweb/batch/runner.py` 中的 provenance 字段和校验链，删除 `public_source_url` / `source_commit_sha` 的核心依赖，远端分类只要求显式授权、非空 API key 与输入源码目录可读。
- 保持 `analysis_source_root` 只用于 CodeQL database source root 一致性校验，不再与 git 证明耦合；同步更新本地回归与真实 CodeQL fixture 测试，确认 Zipkin `growth` 已不再被源码证明阻塞，而是进入真实 provider 调用。

### 验证
- `python3 -m pytest -q tests/test_source_excerpts.py tests/test_config_and_cli.py tests/test_batch_runner.py tests/test_production.py`
- `DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_codeql_growth_queries.py::CodeqlGrowthQueryTests::test_g1_through_g4_against_temporary_databases tests/test_codeql_lifecycle_queries.py::CodeqlLifecycleFixtureTests::test_fixture_semantics`
- `python3 -m dosweb.cli entries --database ...openzipkin__zipkin-db --output ...openzipkin__zipkin_iter5 --source-checkout .../frameworks/applications/openzipkin__zipkin --analysis-source-root .../frameworks/applications/openzipkin__zipkin`
- `DEEPSEEK_API_KEY=test-key python3 -m dosweb.cli growth --database ...openzipkin__zipkin-db --output ...openzipkin__zipkin_iter5 --source-checkout .../frameworks/applications/openzipkin__zipkin --analysis-source-root .../frameworks/applications/openzipkin__zipkin --allow-remote-llm`

### 依赖与影响
- 本轮改变了 Growth 源码摘录与远端分类的 provenance 模型：后续如果要保留任何 commit 级绑定，需要另行以“本地源码树”语义重新设计，而不是恢复 public-source 证明链。
- 当前 Zipkin `growth` 的下一真实阻塞已变为 provider 认证，不再是源码摘录或 checkout 证明失败。

## [2026-08-14] Restore direct CodeQL Armeria coverage and secure config loading

### 修改时间
2026-08-14 19:20

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 同步修复直连查询 `codeql/dosweb/Growth/InputMaterialization.ql` 与 `codeql/dosweb/Flows/EntryToGrowth.ql`，补齐 Armeria `HttpRequest.aggregateWithPooledObjects()` 材料化识别、Armeria handler/request 建模以及一跳 handler -> helper 参数转发，使直连查询与嵌入式 query pack 的 Zipkin 风格链路建模重新一致。
- 修复 `dosweb/config.py` 被破坏的配置加载逻辑：移除硬编码 `DEEPSEEK_API_KEY`，恢复仅在 `allow_remote_llm=true` 时要求非空环境密钥；新增递归 YAML 结构校验，稳定拒绝任意层级 `api_key` 变体、过深嵌套、过大集合、过长字符串与无效 Unicode。
- 回归确认 `tests/test_config_and_cli.py` 与 `tests/test_production.py` 全部恢复通过；CodeQL fixture 测试当前仍受环境前置条件控制，需要显式设置 `DOSWEB_RUN_CODEQL_FIXTURES=1` 且本机具备 `codeql`/`javac` 才会执行真实查询。

### 验证
- `python3 -m pytest -q tests/test_config_and_cli.py`
- `python3 -m pytest -q tests/test_production.py`

### 依赖与影响
- 本轮未改变 v2 verdict 口径，只修复直连查询覆盖与配置前置条件校验。
- Zipkin 下一步仍需在具备真实 CodeQL/LLM 前置条件下继续复跑 `entries -> growth`，确认 `aggregateWithPooledObjects()` 主链是否被恢复命中。

## [2026-08-14] Re-run final narrow Cryostat semantic probe and tighten route-mismatch blocker

### 修改时间
2026-08-14 19:00

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只处理 `cryostatio__cryostat-legacy-F-WS-001`，先重读既有 `result.json`、`environment.md`、`final_attempts_20260814.json`、`postgres_bridge_probe_20260814.json`、`postgres_bridge_app_20260814.log`、源码 `MessagingServer` / `NotificationsUrlGetHandler`、集成测试 `NotificationsUrlIT` / `StandardSelfTest` 与 `docs/HTTP_API.md`，限定在 notifications base path / auth 前缀 / diagnostic request chain 三类窄问题内收敛证据。
- 复核确认官方源码、文档与集成测试都一致声明 `GET /api/v1/notifications_url` 应返回 JSON、`/api/v1/notifications` 应提供 WebSocket 语义；但已保存的 packaged-image 启动日志同时记录 `UT026003 ... path /api/notifications`，说明当前 official latest 打包物还存在 `/api` 对 `/api/v1` 的路由前缀分歧，而不是单纯“请求打错 base path”。
- 新增 `logs/final_semantic_probe_20260814_retry.json`，对上轮唯一 health-ready 的 diagnostic PostgreSQL + `QUARKUS_DATASOURCE_*` bridge 端口仅做定点 HTTP/原始 WebSocket 复探；结果显示该 listener 当时已消失，`/health`、`/api/v1/notifications_url`、`/api/v1/notifications`、`/api/notifications_url`、`/api/notifications` 全部 connection refused。按本轮要求不再重启/泛化环境，因此把它仅作为“即使 diagnostic 路径也无可重复 notifications 语义入口”的收敛证据。
- 同步更新 case `environment.md`、`result.json`、批次 `validation_status.jsonl`，把 blocker 精确收敛为：official latest 同时存在 datasource 打包契约失配与 notifications 路由语义/前缀失配；随后重新运行动态聚合脚本刷新汇总产物。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001`
- 新增诊断证据：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001/logs/final_semantic_probe_20260814_retry.json`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未把带 `QUARKUS_DATASOURCE_*` 的 diagnostic bridge 路径包装成默认验证成功。
- 当前最精确结论为：官方 latest 不仅 datasource 契约与 README/compose 不一致，notifications 入口本身还存在 `/api` vs `/api/v1` 打包语义分歧；在不再扩展环境的约束下，默认动态验证仍只能保守停在 `environment_blocked`。

## [2026-08-14] Fix growth-entry association to skip unmapped noise candidates

### 修改时间
2026-08-14 18:40

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 修复 `dosweb/production.py` 中 growth 阶段的 entry 绑定策略：当 growth 候选完全无法匹配任何已恢复入口时，不再以 `ANALYSIS_GROWTH_ENTRY_AMBIGUOUS` 直接中止整个分析，而是把该候选视为无入口噪声并跳过；仍然保留真正多入口歧义的失败行为。
- 为 `tests/test_production.py` 增加回归覆盖，显式验证 growth 元数据会区分 `candidate_count`、`mapped_candidate_count` 与 `skipped_unmapped_candidate_count`，并确保重复 registration 场景不回退。
- 在 Zipkin 首轮自迭代复跑中确认此前阻塞来自可选/非默认 collector 噪声候选无法映射到任何默认入口，而不是 HTTP collector 主链本身缺失。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/production.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_production.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`

### 依赖与影响
- 该修复只放宽“零匹配入口”候选的 growth 进入条件，不改变 entries、flow、lifecycle 或最终 verdict 的保守口径。
- 当前 Zipkin 复跑仍存在后续问题待修：本地 `python -m dosweb.cli` 不会执行 CLI 主入口；真实 CodeQL entries 阶段还会被无关框架查询超时拖慢；远端 LLM 复跑也出现了 provider retries exhausted。

## [2026-08-14] Finalize OpenMeetings assisted conversion probe without changing default blocked verdict

### 修改时间
2026-08-14 17:05

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只处理 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`，重读 case `result.json`、`environment.md`、`preflight.json`、`observations.json`、`reflection.jsonl` 与批次 `validation_status.jsonl`，确认默认安装、登录、public room、`/hash` 入房、`omws-upload-sid` 获取和同源 `/room/file/upload` 都已打通，且默认 blocker 仍只是 office suite 自动发现缺失。
- 复核并采信已完成的单次受控 non-default 辅助验证：使用 case-local 官方 LibreOffice 解包和显式 `path.office` 后，同一 low-privilege presenter 路径可成功接受 4 个并发 benign `.docx` 上传；但配套 `thread_rss_probe_summary.json` 显示 JVM 线程数维持 `152 -> 152`、RSS 仅 `840672 -> 841256 KiB`、signin 健康检查持续 200，未出现 OOM、重启、5xx 或持续不可用。
- 因此不把该案改写成默认 confirmed，也不把辅助结果单列成 `non_default_only` 成功终态；保持默认口径 `environment_blocked`，并把“non-default 仅用于继续验证且未见增长/故障”的分界更明确写入 `result.json` 与 `validation_status.jsonl`，随后重新运行动态聚合脚本刷新汇总产物。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 结果：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS/result.json`
- 批次状态：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/validation_status.jsonl`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未把 case-local LibreOffice + `path.office` 辅助路径包装成默认部署成功。
- 当前最精确结论为：默认路径仍因缺少可自动发现的 system-wide LibreOffice/OpenOffice 而 blocked；非默认辅助路径下虽然能继续完成 benign conversion upload，但在已执行的小有界探针中未见增长或故障证据。

## [2026-08-14] Audit v2 lifecycle analyzer and start PoC-29 chain repair loop

### 修改时间
2026-08-14 16:45

### 变更类型
- [审计]
- [计划]
- [测试]

### 核心改动
- 以 2026-07-18 approved P0 design 为唯一实施标准，对照 2026-07-14 lifecycle-centered research idea 完成设计—代码—测试—PoC benchmark 审计；明确异步 Release、Assertion 3 和速率推理仍是 deferred 能力，相关链路必须保守输出 `static_unknown`。
- 新增 `docs/research/2026-08-14-v2-lifecycle-analyzer-audit.md`，记录模块级已满足项、真实 PoC 项目入口查询超时、默认 CodeQL fixture 未执行、完整 suite 缺少快慢分层、benchmark 缺少逐 PoC E→G→lifecycle 严格映射、失败诊断丢失和 mandatory provider 前置条件等问题。
- 新增 `docs/superpowers/plans/2026-08-14-poc29-lifecycle-chain-repair.md`，把后续修复拆为诊断保真、查询并发/预算、Spring query 性能、链路 matcher、G/flow 召回、lifecycle 保守结论和四层回归七个任务。
- 创建并启动 `results/java_web_dos_batch/poc29-lifecycle-audit-20260814` 的 18 项目 entries 基线；首批大型数据库在固定 300 秒 query deadline 下出现 `CODEQL_QUERY_FAILED`，HertzBeat 单 query 的 30 秒最小复现确认 root cause 类型为 `query_run: command deadline exceeded`。
- 修复 pipeline 失败元数据过度丢失：`run.json` 现在只允许持久化有界的 `stage`、`diagnostic`、`returncode`，拒绝 query path 等额外 details；新增回归测试并确认该行为通过。

### 验证
- `python3 -m pytest -q tests/test_assertions.py tests/test_lifecycle_bounds.py tests/test_lifecycle_guards.py tests/test_lifecycle_releases.py tests/test_flow_verification.py tests/test_growth_verification.py tests/test_p0_end_to_end.py`
- 结果：`77 passed, 90 subtests passed`。
- `python3 -m pytest -q tests/test_pipeline_recovery.py::PipelineRecoveryTests::test_codeql_failure_persists_only_bounded_actionable_diagnostics`：`1 passed`。

### 依赖与影响
- 本轮只新增审计、计划、基线结果与 changelog，未修改 analyzer verdict 逻辑，也未使用 PoC 动态 truth 改写普通静态结论。
- 当前环境未设置 `DEEPSEEK_API_KEY`；按 approved design 不允许用 mock 绕过 mandatory Growth Contract。可以继续完成 network-free CodeQL 和 deterministic stages，真实 full acceptance 等待显式 provider 前置条件。

## [2026-08-14] Finalize OpenMeetings blocked verdict as missing default office auto-discovery condition

### 修改时间
2026-08-14 16:13

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS` 做最后一轮严格默认口径复核，先重读既有 `result.json`、`environment.md`、`data_prep.md`、共享环境 `inventory/feasibility/readiness/snapshot` 与批次 `validation_status.jsonl`，确认默认安装、登录、public room、`/hash` 入房、`omws-upload-sid` 获取与同源 `/room/file/upload` 预检都已打通，当前只剩 office conversion 环节阻塞。
- 新增默认链路审计证据：重读仓库 `openmeetings-server/src/site/xdoc/OpenOfficeConverter.xml`、`openmeetings-install/.../ImportInitvalues.java`、`openmeetings-core/.../DocumentConverter.java`、install wizard office path 校验逻辑，并复查 release runtime/宿主 `libreoffice`、`soffice` 发现路径，确认官方默认语义一致为“运行 OpenMeetings 的机器需要预装 LibreOffice/OpenOffice，默认保持 `officeHome/path.office` 为空，仅在自动发现失败时才显式指定路径”；仓库文档、运行包与默认启动链中均未发现先前未用上的隐含 office 安装器、默认 `path.office` bootstrap 或其他默认 conversion 前置。
- 因此把该案 `environment_blocked` 精确收敛为“默认 runtime 缺少可自动发现的 system-wide office suite 条件”：当前宿主默认 runtime 既无 `libreoffice/soffice` system-wide 可执行文件，accepted office upload 又会在 `DocumentConverter` 处以 `officeHome must not be null` 提前失败。保留 case-local 官方 LibreOffice 下载/显式 `path.office` 的 supplemental 路径仅作为非默认辅助证据，不把它包装成默认可利用结论。
- 同步更新 case `result.json`、`environment.md`、`data_prep.md`、共享环境 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json`、批次 `validation_status.jsonl` 与项目 `CHANGELOG.md`，随后重新运行聚合脚本刷新汇总产物。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__openmeetings-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未把 case-local LibreOffice 解包或显式 `path.office` 辅助配置包装成默认部署成功。
- 新证据将 OpenMeetings 的剩余 blocker 最终固定为：当前默认 runtime 缺少 JODConverter 可自动发现的 system-wide LibreOffice/OpenOffice 条件，且仓库文档、运行包与默认启动链中不存在隐藏的默认 office bootstrap；只有当宿主按默认方式提供该 system-wide office suite 后，默认 upload-conversion worker 压力验证才能继续。

## [2026-08-14] Finalize Cryostat default-path blocker as image-contract plus route-semantics mismatch

### 修改时间
2026-08-14 16:12

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 仅针对 `cryostatio__cryostat-legacy-F-WS-001` 做最后一轮严格默认口径复核，复查仓库 `README.md`、`compose/compose-cryostat.yaml`、`compose/compose-postgres.yaml`、`run-docker.sh`、`smoketest-docker.sh`，以及 case/environment 既有工件，确认不存在遗漏的官方 auth/profile、路由基址或 companion 参数能把通知语义带回默认路径。
- 补充本地已拉取官方 latest 镜像的精确锚点：`quay.io/cryostat/cryostat:latest@sha256:80f82599e8aa755cabfb819125332c895ea41f1d265a9819096264cbbc9d1183`；其本地标签显示 build-date 为 `2026-08-04T19:57:50`。该信息仅用于把 blocker 绑定到当前官方 latest，不改变默认/非默认判定。
- 结合源码 `NotificationsUrlGetHandler`、`MessagingServer` 与 `docs/HTTP_API.md` 的路由约定，再次收紧结论：即便在仅用于诊断的 PostgreSQL + `QUARKUS_DATASOURCE_*` bridge 路径上已拿到 `/health` 200，`/api/v1/notifications_url` 与 `/api/v1/notifications` 仍返回 SPA HTML，而非源码/文档声明的 JSON `notificationsUrl` 与 WebSocket 语义入口，因此 notifications_url / notifications WebSocket 在默认口径下仍不可验证。
- 保持 `environment_blocked`，并将 case `result.json` 与批次 `validation_status.jsonl` 更新为上述最精确结论；随后重新运行聚合脚本刷新汇总工件。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 结果：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001/result.json`
- 批次状态：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/validation_status.jsonl`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未把带 `QUARKUS_DATASOURCE_*` 的诊断 bridge 路径包装成默认验证成功。
- 当前最精确结论为：官方 latest 镜像的 datasource 打包契约与 README/compose 不一致，且在唯一 health-ready 的诊断路径上，通知 API 仍未兑现源码/文档声明的 JSON/WebSocket 语义，因此默认动态验证无法继续。

## [2026-08-14] Finalize lamp-cloud blocked verdict as missing sibling-only default chain failure

### 修改时间
2026-08-14 05:45

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `dromara__lamp-cloud-FND-001` 做最后一轮严格默认口径复核，重读 `result.json`、共享环境 `inventory/feasibility/readiness`、仓库 `README.md`、`lamp-dependencies-parent/pom.xml`、`A极其重要/01-docs/docker/03.docker运行项目.md`、本地 Maven 缓存证据以及批次 `validation_status.jsonl`。
- 在既有“缺失 sibling lamp-util 派生 parent artifact”基础上，再补充两条最终排除证据：`lamp-dependencies-parent/pom.xml` 仅声明 `dev`/`prod` 两个 profile，二者都不绕过 `top.tangyh.basic:lamp-parent:5.10.0` 父 POM 依赖；官方 GitHub `releases` 页面明确无 release，`tags` 页面仅提供源码 `zip/tar.gz` 归档，没有预构建运行时资产。
- 因此将该案最终固定为：默认交付链硬依赖缺失 sibling 资产且无默认替代路径。同步更新 `result.json`、`validation_status.jsonl`、共享环境 `changes.jsonl`，并重新运行聚合脚本刷新汇总产物。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未伪造 sibling 项目、手工补 parent POM、切换非官方镜像或引入非默认交付方式来制造 gateway 就绪。
- 新证据把 lamp-cloud 的默认阻塞点最终收敛为：只有当官方默认构建所需的 sibling `lamp-util` 派生 `top.tangyh.basic:lamp-parent:5.10.0` 能正常提供时，Nacos + gateway + downstream swagger baseline 才能继续；在此之前该案保持 `environment_blocked`。

## [2026-08-14] Tighten Cryostat blocked verdict to image packaging plus notifications-route mismatch

### 修改时间
2026-08-14 05:20

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `cryostatio__cryostat-legacy-F-WS-001` 做最后一轮官方镜像/README 口径复核，先重读既有 `result.json`、`environment.md`、共享环境 `inventory/feasibility/readiness/snapshot`、`changes.jsonl` 与失败日志，再确认旧 blocker 仍主要停留在 “H2 datasource/Flyway 启动失败” 的粒度。
- 在不修改业务代码、不引入组外 case 的前提下，新增两条最小机械复测：其一是按仓库 `compose/compose-postgres.yaml` 的文档化 PostgreSQL companion 路径重启官方镜像；其二是在同一 PostgreSQL companion 基础上，只额外补入未文档化但与打包 Quarkus 运行时相匹配的 `QUARKUS_DATASOURCE_JDBC_URL/USERNAME/PASSWORD` bridge，目的是压缩 blocker，而不是把该路径当作默认验证成功。
- 新证据进一步收紧了官方镜像缺陷：镜像 `/deployments/lib/main` 中实际只包含 `io.quarkus.quarkus-jdbc-postgresql`、`org.postgresql.postgresql` 与 PostgreSQL 侧 Flyway 依赖，并无 H2 JDBC jar，因此 README 与 compose 默认声称支持的 `CRYOSTAT_JDBC_*` H2 file / H2 mem 路径在打包镜像里天然不可用；而文档化 PostgreSQL companion 路径本身也仍不会激活默认 datasource，只有补入未文档化 `QUARKUS_DATASOURCE_*` bridge 后 `/health` 才首次返回 200。
- 即便如此，bridge 仅用于诊断的问题仍未结束：在该 health-ready 诊断路径上，`GET /api/v1/notifications_url` 与 `GET /api/v1/notifications` 依旧返回前端 SPA `text/html`，而不是源码/文档声明的 JSON notificationsUrl 语义或可继续预检的通知 WebSocket 入口。因此保留 `environment_blocked`，但将失败点压缩为 “官方镜像 latest 的打包 datasource 合约与 README/compose 不一致，且即便桥接到健康状态，通知 API 路由仍与文档语义不符”。同步更新 `result.json`、`environment.md`、`data_prep.md`、`rounds/round-1/preflight.json`、共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl` 与批次 `validation_status.jsonl`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cryostatio__cryostat-legacy-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未把带 `QUARKUS_DATASOURCE_*` 的 PostgreSQL bridge 诊断路径包装成默认部署成功。
- 新证据表明当前 blocker 已精确推进为：官方 latest 镜像与 README/compose 的 datasource/notifications API 契约不一致；只有当官方镜像重新对齐其文档化 datasource 路径，并真实暴露 `/api/v1/notifications_url` JSON 语义后，通知 WebSocket 的默认动态验证才可继续。

## [2026-08-14] Confirm lamp-cloud has no default-compatible prebuilt fallback path

### 修改时间
2026-08-14 02:08

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `dromara__lamp-cloud-FND-001` 复核既有 `environment_blocked` 结论，先重读 case `result/environment/logs/changes` 与批次 `validation_status.jsonl`，确认旧 blocker 已收紧到缺失 sibling `lamp-util` 派生 parent artifact，但仍缺少“是否存在官方替代交付路径”的最终证据。
- 在不修改业务代码前提下，补做默认兼容 fallback 路径审查：重读仓库 `README.md`、`lamp-dependencies-parent/pom.xml`、`A极其重要/01-docs/docker/03.docker运行项目.md`，枚举仓库内 `jar/compose/Dockerfile` 资产，并额外检查 `dromara/lamp-cloud` 官方 GitHub Releases / Packages 页面是否存在 release、镜像或可下载预构建产物。
- 新证据表明默认路径没有可替代发布方式：仓库只文档化“先编译整个项目再构建镜像”的路径，明确声明编译顺序必须是 `lamp-util -> lamp-cloud -> lamp-job`；仓库内不存在可直接运行的 gateway jar、也不存在自包含 compose；GitHub Releases 页面明确显示 “There aren’t any releases here”，Packages 页面也未显示任何 `lamp-cloud` 包或镜像。
- 因此该案继续保留 `environment_blocked`，并把阻塞点精确固定为“默认构建硬依赖缺失的 sibling 资产”：即 `top.tangyh.basic:lamp-parent:5.10.0` 既不在 workspace sibling、也不在配置镜像仓库、也不在本地 Maven 缓存中，同时不存在仓库内或官方发布面上的默认兼容预构建替代路径。同步更新 `result.json`、`environment.md`、`data_prep.md`、共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`notes.txt`、`changes.jsonl` 与批次 `validation_status.jsonl`，随后重新运行聚合脚本刷新汇总。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未伪造 sibling 项目、手工补 parent POM、切换非官方镜像或采用未文档化交付方式来制造 gateway 就绪。
- 新证据将 lamp-cloud 的默认阻塞点最终固定为：默认构建链硬依赖缺失的 sibling `lamp-util` 派生 parent artifact，且仓库内与官方发布面上都不存在默认兼容的预构建替代路径；只有当官方默认构建所需的 `top.tangyh.basic:lamp-parent:5.10.0` 能通过 sibling 项目正常安装到本地仓库后，Nacos + gateway + downstream swagger baseline 才能继续。

## [2026-08-14] Tighten lamp-cloud blocked verdict to unresolved sibling parent artifact

### 修改时间
2026-08-14 01:43

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `dromara__lamp-cloud-FND-001` 做最后一轮默认部署/默认流程口径复核，先重读既有 `result.json`、`environment.md`、共享环境 `inventory/feasibility/readiness/snapshot`、`changes.jsonl` 与批次 `validation_status.jsonl`，确认旧 blocker 仍停留在“缺失 sibling lamp-util 项目”的较粗粒度表述。
- 在不修改业务代码、不引入组外 case 的前提下，补做两次环境修复尝试：其一是按文档化路径重跑 `mvn -q -pl lamp-gateway/lamp-gateway-server -am -DskipTests package`；其二是 `-o` 离线重试，验证是否已有可复用的本地 Maven 缓存足以支撑默认构建。
- 新证据表明 blocker 可进一步收紧：两次 Maven 尝试都在 `lamp-dependencies-parent/pom.xml` 处因 `top.tangyh.basic:lamp-parent:5.10.0` 解析失败而在运行前终止；配置的 `aliyunmaven` mirror 不提供该 parent POM，而本机 `~/.m2/repository/top/tangyh/basic/lamp-parent/5.10.0/` 仅有 `lamp-parent-5.10.0.pom.lastUpdated`，并不存在可复用的已安装 parent artifact。
- 因此该案继续保留 `environment_blocked`，但把阻塞点从泛化的“缺失 sibling lamp-util 源码树”推进为“默认构建所需的 sibling lamp-util 派生 parent POM 既不在镜像仓库中，也不在本地 Maven 缓存中”；同时保留另一默认前提：即便 Nacos export archive 已随仓库提供，仍需成功构建 gateway 与至少一个下游 swagger 服务才能进入 `/v3/api-docs/swagger-config` 语义预检。同步更新 `result.json`、`environment.md`、`data_prep.md`、共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`notes.txt`、`changes.jsonl` 与批次 `validation_status.jsonl`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过伪造 sibling 项目、手工补 parent POM、切换非官方构建路径或启用非默认 feature flag 来制造 gateway 就绪。
- 新证据把 lamp-cloud 的默认阻塞点精确推进为：默认构建链在 sibling lamp-util 派生 parent artifact 缺失处即终止；只有当官方默认构建所需的 `top.tangyh.basic:lamp-parent:5.10.0` 能通过 sibling 项目正常安装到本地仓库后，Nacos + gateway + downstream swagger baseline 才能继续。

## [2026-08-14] Tighten Rill Flow blocked verdict to JDK cgroup v2 deployment failure

### 修改时间
2026-08-14 01:25

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `weibocom__rill-flow-F-001`、`weibocom__rill-flow-F-002`、`weibocom__rill-flow-F-003` 做最后一轮默认部署/默认流程复核，先重读既有 `result.json`、共享环境 `inventory/feasibility/readiness/snapshot`、`changes.jsonl`、启动日志与批次 `validation_status.jsonl`，确认旧 blocker 仍停留在较粗粒度的 “Micrometer ProcessorMetrics NPE”。
- 在不修改业务代码、不启用非默认 feature 的前提下，补做一轮运行时兼容性诊断：继续保留官方 compose、官方镜像与仅隔离 host 端口的部署口径，同时新增官方镜像 `--cgroupns=host` + `/sys/fs/cgroup:ro` 诊断采样，记录镜像内 `/proc/self/cgroup`、`/proc/self/mountinfo` 与 `/sys/fs/cgroup` 视图到 `cgroup_diag_20260814.txt`。
- 新证据把 blocker 收紧为默认镜像/JDK/运行时组合问题：`weibocom/rill-flow:latest` 内置 OpenJDK `17.0.2+8-86` 在当前 cgroup v2 + systemd scope 宿主布局下始终把 controller 解析为空，先在 OpenTelemetry runtime metrics 初始化阶段抛错，再在 Spring Boot Micrometer `processorMetrics` bean 创建时以同一 `anyController=null` 终止 webapp 部署；即便容器状态保持 `running`，最终对 `http://127.0.0.1:18083/flow/bg/manage/descriptor/get_business.json` 的探测也只得到 TCP reset，而不是可用 HTTP 响应。
- 因此三案继续保留 `environment_blocked`，但阻塞点已从“backend 启动失败”推进为“官方默认镜像绑定的 OpenJDK 17.0.2 无法在当前 cgroup v2/systemd scope 运行时完成部署”；同步更新三份 `result.json`、三份 `environment.md`、共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl` 与批次 `validation_status.jsonl`，随后重新运行聚合脚本刷新汇总。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/weibocom__rill-flow-F-001`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/weibocom__rill-flow-F-002`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/weibocom__rill-flow-F-003`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过禁用 tracing、关闭 metrics、切换非官方镜像或引入非默认 feature flag 来制造 backend 就绪。
- 新证据表明三条候选路径当前都被同一个默认镜像/JDK/cgroup 兼容性问题阻断；只有当官方镜像或宿主运行时允许该镜像不改行为地完成 Spring Boot/Tomcat 部署后，cron trigger、Kafka trigger 与 foreach submit 的默认语义预检才可继续。

## [2026-08-14] Tighten Cryostat blocked verdict to packaged datasource bootstrap failure

### 修改时间
2026-08-14 01:11

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `cryostatio__cryostat-legacy-F-WS-001` 做最后一轮默认部署/默认流程口径复核，先重读既有 `result.json`、环境 `inventory/feasibility/readiness/snapshot`、`changes.jsonl` 与失败日志，再确认旧 blocker 仍停留在“datasource 未激活 / build-time db-kind 不匹配”的较粗粒度表述。
- 在不修改业务代码、不引入组外 case 的前提下，补做两条最终官方镜像路径验证：其一是仓库 `run-docker.sh` 等价的 `NoopAuthManager` 路径；其二是按 `smoketest-docker.sh` 文档化方式补齐 `cryostat-users.properties` 后的 `BasicAuthManager` 路径。两条路径都继续保留隔离端口、官方镜像、官方 bind-mount 目录和仅为满足打包运行时所需的有界 `QUARKUS_S3_*` 值。
- 新证据表明 blocker 可进一步收紧：在 `quarkus.s3.*` 已补齐后，官方镜像不仅会拒绝此前已见的 README 支持 H2 file URL，连 README 明确支持的 H2 mem URL 也会在 Noop 与带文档化用户文件的 BasicAuth 两条官方路径上，被打包镜像内置 Agroal/Flyway 一致报出 `Driver does not support the provided URL`；容器均在 `/health` 绑定前退出，`/api/v1/notifications_url` 与通知 WebSocket 始终不可达。
- 因此保留 `environment_blocked`，但把阻塞点从“缺少默认 BasicAuth 用户文件/Quarkus datasource 未激活”推进为“官方镜像打包的 datasource/Flyway 启动链对 README 支持的 H2 file 与 H2 mem URL 都不可用”，并同步更新 `result.json`、`environment.md`、`data_prep.md`、共享环境 `feasibility/readiness/snapshot/changes`、批次 `validation_status.jsonl` 与 `blocked_or_rejected.jsonl`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cryostatio__cryostat-legacy-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过非默认 feature flag、关闭鉴权或自定义 sibling 资产绕过默认路径。
- 新证据证明即便按官方 `smoketest-docker.sh` 口径补齐 BasicAuth 用户文件，真正阻塞点仍位于官方镜像自身打包的 datasource/Flyway 启动链，因此当前默认镜像无法进入 WebSocket 语义预检阶段。

## [2026-08-14] Tighten OpenMeetings blocked verdict from room preconditions to office-conversion environment

### 修改时间
2026-08-14 00:55

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 只针对 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS` 继续执行最后一轮默认部署/默认流程口径复核，先重读既有 `result.json`、`environment.md`、`data_prep.md`、`preflight.json`、`observations.json`、共享环境 `readiness/feasibility/inventory/snapshot` 与运行日志，确认旧 `precondition_blocked` 描述已经落后于最新证据。
- 复核结果表明默认业务前置其实已经补齐：默认 H2 安装和前后台登录均已成功；通过默认 service API 创建 public non-moderated room 后，low-privilege external attendee 已经经正常 `/hash` UI/WebSocket 流程进入房间，页面真实暴露 `omws-upload-sid`，且同源 benign `.docx` `POST /openmeetings/room/file/upload` 返回 `{"status":"SUCCESS","message":"OK"}`。
- 新终态阻塞不再是 presenter 会话或 room SID，而是默认转换环境：accepted office 文档进入 `DocumentConverter` 后，`openmeetings.log` 记录 `doJodConvert` 在 `DocumentConverter.createOfficeManager()` 处抛出 `java.lang.NullPointerException: officeHome must not be null`；同时宿主侧 `command -v libreoffice` 与 `command -v soffice` 均为空，说明当前 documented source-build release runtime 未自动发现 LibreOffice/OpenOffice，也未完成 `path.office` bootstrap。
- 因此将该 case 从 `precondition_blocked` 收紧推进为 `environment_blocked`，并同步改写 `result.json`、`case_plan.json`、`environment.md`、`data_prep.md`、共享环境 `readiness.json`、`feasibility.json`、`inventory.json`、`snapshot.json`、`changes.jsonl` 与批次 `validation_status.jsonl`，使 blocker 精确落到默认 office conversion 依赖缺失，随后重新运行聚合脚本刷新批次汇总。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`
- 环境目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__openmeetings-default`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过手工设置 `path.office`、安装非文档化自定义组件或绕过默认 room/upload 鉴权来制造成功。
- 新证据将 OpenMeetings 的剩余 blocked 点从“默认 low-privilege presenter/room 前置未补齐”精确推进为“默认 source-build release runtime 缺少可用 office conversion bootstrap，因此 accepted upload 在进入真正 worker 压力前即失败”。

## [2026-08-14] Re-drive Airavata default launch and bounded file-download preflight

### 修改时间
2026-08-14 00:35

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续只针对 `apache__airavata-FND-200-1` 复核既有 `precondition_blocked` 结论，先重读该 case 的 result/environment/data-prep/log 工件，再在不修改业务代码、不启用非默认 feature 的前提下，重新尝试默认部署与默认流程口径下的实验/文件前置补齐。
- 新证据表明真正可行的默认路径不是 host-side `AiravataOperator.make_experiment_dir()`：该 SDK 路径仍会把 `default-admin` bearer token 当作 SFTP 密码而失败；但默认 server-side `LaunchExperiment` 会按 seeded storage preference 的 `login_user_name=airavata` 成功创建实验目录、启动 Echo 作业并产出 own-process `Echo.stdout` 文件。
- 随后完成了目标入口的语义预检：`GET /api/v1/files/list/false/{processId}` 与 `GET /api/v1/files/download/false/{processId}/Echo.stdout` 在 bearer token 下均返回 200，服务端日志明确记录 `AirvataFileService` 通过 SFTP 下载远端 `Echo.stdout` 到本地临时文件后再由 `FileController` 返回响应，说明静态候选路由已真实可达。
- 在默认路径上执行单轮有界小文件下载爬坡（33B / 129B / 241B 响应体），同步记录 `docker stats` 与健康检查；Airavata 容器内存稳定在约 1.278-1.282 GiB，健康始终 200，未出现 OOM、重启、持续 5xx 或持续不可用，因此该案从 `precondition_blocked` 推进为 `not_reproduced_under_tested_bounds`。
- 同时记录新的默认业务上界：继续放大同一 seeded Echo 路径时，`CreateExperiment` 会先被默认数据库 `RESEARCH_IO_PARAM.PARAM_VALUE=tinytext` 拦截，1024B 及以上输入直接报 `Data too long`，因此本轮未再进入更大下载压力阶段。
- 同步更新该 case 的 `result.json`、`environment.md`、`data_prep.md`、`reflection.jsonl`、新增 `rounds/round-1/` 工件，并回写批次 `validation_status.jsonl`，准备重新运行聚合脚本刷新共享汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__airavata-FND-200-1`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未关闭鉴权、伪造 portal、改 seed 或启用非默认配置来制造成功。
- 新证据把 Airavata 的默认阻塞结论推进为真实可执行后的终态：默认 server-side launch 与文件下载链路可达，但在当前默认 seeded Echo 业务路径下，只观察到有界小文件成功下载，未观察到资源耗尽；更大的同路径输入会先命中默认数据库 tinytext 上界。

## [2026-08-14] Remove GitHub attestation fallback from full-mode local commit verification

### 修改时间
2026-08-14 00:18

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续收紧 `dosweb/llm/deepseek.py` 的 provenance 逻辑：即使旧 `batch_plan.json` 或 target capability 仍带有 `public_source_url`，full 模式也不再回退到 GitHub API 做 public-source attestation，而是统一只验证本地 `source_checkout + source_commit_sha` 的 clean commit 绑定。
- 同步修正 `dosweb/llm/cache.py` 与 request audit 写入逻辑，确保缓存身份、审计字段和新的本地 commit 证明口径一致，避免 `invalid cache entry` 回归。
- 新增 `tests/test_deepseek_client.py` 回归测试，覆盖“带 `public_source_url` 但仍只走本地 commit 校验且不访问 GitHub API”的场景。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/llm/deepseek.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/llm/cache.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_deepseek_client.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`

### 依赖与影响
- 旧 plan 无需重建也能直接受益；只要本地 checkout 和 commit 可验证，full batch 就不会再被 GitHub provenance 卡住。

## [2026-08-13] Re-drive Bonita low-privilege default bootstrap and upload probe

### 修改时间
2026-08-14 00:10

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 只针对 `bonitasoft__bonita-engine-FND1` 继续复核既有 `auth_blocked` 结论，重读该 case 的 `result.json`、preflight、environment 工件与 Bonita 默认权限/REST 路径源码，不修改业务代码、不启用非默认 feature、不用管理员账号直接代替低权限攻击者。
- 在官方 `bonita:latest` 默认镜像与兼容 Postgres companion 的隔离复现环境中，确认首次阻塞并非“默认流程无法得到普通用户”，而是默认镜像只暴露 `install/install` bootstrap 技术账号、不会自动 seed 组织成员；但该默认 bootstrap 账号可通过内置 `API/identity/{group,role,user,membership}` 与 `API/portal/profileMember` 路径完成最小组织初始化，创建普通非管理员 `lowuser` 并赋予默认 `User` profile。
- 进一步以该 `lowuser` 完成语义预检：`GET /portal/fileUpload` 对低权限用户返回 403，但静态入口对应的 `POST /portal/fileUpload` multipart 上传在默认会话下返回 200，因此真正相关的是已认证 POST 语义，而不是 GET 页面访问。
- 在低权限账号下执行有界 multipart part-count 爬坡（1 / 100 / 400 个 16B 文本 part），同步记录容器内存与 HTTP 可用性；三轮请求全部 200，Bonita 容器内存维持在约 459-460 MiB，未触发 OOM、重启、持续 5xx 或持续不可用，因此该案从 `auth_blocked` 收紧改判为 `not_reproduced_under_tested_bounds`。
- 同步更新该 case 的 `case_plan.json`、`environment.md`、`data_prep.md`、`reflection.jsonl`、`result.json`、新增 `round-2/` 工件，并回写批次 `validation_status.jsonl`，准备重新运行聚合脚本刷新共享汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/bonitasoft__bonita-engine-FND1`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过管理员账号直接充当攻击者、关闭鉴权、恢复非默认行为或注入自定义 seed 制造成功。
- 新证据将 Bonita 的默认阻塞点从“拿不到普通账号”精确收紧为：默认镜像不会自动给出普通用户，但 bootstrap 管理员可经内置默认组织/profile API 创建最小低权限账号；即便如此，在当前有界 part-count 与单请求测试范围内仍未复现动态资源耗尽。

## [2026-08-13] Tighten Airavata dynamic precondition blocker semantics

### 修改时间
2026-08-13 23:59

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续复核 `apache__airavata-FND-200-1` 的既有 `precondition_blocked` 证据，只沿默认文档化 quickstart、默认 Keycloak、默认 SDK 和现有 companion services 检查是否还能补齐 Echo 实验/项目/文件前置，不修改业务代码。
- 新增宿主侧与容器网络内认证探测工件，明确区分两类现象：宿主 `127.0.0.1:18080` 并未暴露可直接使用的 Keycloak token endpoint；但在默认 Docker 网络内，`keycloak:18080` 可成功签发默认 `pga` client 的 token，且该 token 能通过 gRPC 成功枚举 seeded `Default Project`，说明默认 API 认证链本身并未缺失。
- 进一步以容器内 `AiravataOperator` 复核默认 SDK 业务链：`get_project_id("Default Project")` 与 `get_preferred_storage()` 都成功返回，且 seeded storage preference 明确解析到 `storage_resource_id=sftp_877f4ac0-0670-4d4e-94dc-726ab14db77a`、`login_user_name=airavata`、`root=/storage`；真正阻塞发生在 `make_experiment_dir()`，SDK 默认以 `username=default-admin` 且 `password=<bearer token>` 对 `sftp:22` 做 Paramiko 认证并返回 `Authentication failed`，因此实验目录、进程文件与下载路由预检仍无法建立。
- 保留并收紧另一条阻塞：README 文档化的 portal UI 备选路径仍依赖 sibling `airavata-portals` 仓库，而当前 worker 主机缺失 `/home/furina/new_tool/airavata-portals`，因此无法通过该默认 UI 流程补齐 Echo 实验。
- 同步更新该 case 的 `result.json`、批次 `validation_status.jsonl` 与证据路径，并准备重新运行聚合脚本刷新共享汇总。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__airavata-FND-200-1`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过关闭鉴权、伪造 portal、手工改 seed、替换 storage 凭据或引入非默认 feature flag 制造成功。
- 新证据把该案阻塞点从泛化的“默认 SDK 路径缺认证”收紧为：默认 API 鉴权可达，但默认 SDK/seeded storage preference 组合无法为 `default-admin` 建立实验目录所需的 SFTP 认证；同时文档化 UI 备选路径所需 sibling portal 资产缺失。

## [2026-08-13] Re-drive OpenMeetings install-to-login transition

### 修改时间
2026-08-13 23:59

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 只针对 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS` 继续沿文档化 source-build release package / 默认 H2 安装路径排查，不修改业务代码、不切换部署模型。
- 复读既有 case/environment 工件、运行日志、访问日志与默认 `persistence.xml` 后，确认此前“日志 ready 但前台仍回 install”的根因不是默认 H2 永久不可安装，而是 `startup.sh` 与 `admin.sh` 共用 `jdbc:h2:./omdb`：当二者从不同工作目录执行时，会各自落到不同的相对 H2 文件。
- 在同一 release runtime 目录内重跑 `./bin/startup.sh` 与 `./admin.sh -i ...` 后，runtime-local `omdb.mv.db` 明确增长，`GET /openmeetings/signin` 返回 200 登录页，前台 `POST /openmeetings/signin` 对 `omadmin` 返回 302 到 `.`，REST `POST /openmeetings/services/user/login` 也返回成功 SID，证明默认安装态已真正推进到可登录前台。
- 同时收紧该案终态：当前已不再是 `environment_blocked`，而是 `precondition_blocked`。剩余阻塞点是默认低权限 presenter 业务前置仍未补齐——尚未通过默认 room UI/WebSocket 流程建立 low-privilege presenter 房间会话并捕获实时 `omws-upload-sid`，因此仍不能合法执行 `/room/file/upload` 动态探测。
- 同步更新该 case 的 `result.json`、`environment.md`、`data_prep.md`、`reflection.jsonl`，共享环境 `readiness.json`、`changes.jsonl`，以及批次 `validation_status.jsonl`，并准备重新运行聚合脚本刷新汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`
- environment 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__openmeetings-default`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过关闭安全控制、管理员替代低权限攻击模型或非默认 feature flag 制造成功。
- 新证据把 OpenMeetings 的默认阻塞点从“安装未完成”收紧为“安装与管理员登录已成功，但 low-privilege presenter 房间会话 / `omws-upload-sid` 业务前置仍缺失”。

## [2026-08-13] Re-drive Openfire default autosetup and BOSH preflight

### 修改时间
2026-08-13 23:59

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 只针对 `igniterealtime__openfire-F0154` 继续沿官方 GHCR 镜像与仓库 `documentation/install-guide.html` 的文档化 autosetup 路径排查，不修改业务代码，不切换非官方镜像，也不关闭任何安全/资源控制。
- 复盘第一次 case-local autosetup 失败后，进一步提取官方镜像 `/sbin/entrypoint.sh` 与默认 `conf_org`/`security_org` 布局，确认此前的空指针并非“autosetup 本身不可用”，而是第一次修复只替换了 `conf/openfire.xml`，却没有保留镜像默认 `conf/security.xml` 与 `conf/security/` 资产，导致 `JiveGlobals.setupPropertyEncryptionAlgorithm` 在旧算法值为空时崩溃。
- 新建第二个 case-local `/var/lib/openfire` 数据目录，保留镜像默认 `conf/security.xml`、`conf/security/`、`crowd.properties` 等 entrypoint 期望资产，仅按文档化 autosetup 方式替换 `conf/openfire.xml`。在该布局下，官方镜像成功完成 embedded-database setup、安装 schema，并明确记录 `HTTP bind service started`。
- 在修通后的默认兼容环境上完成匿名 `/http-bind/` 语义预检：最小有效 BOSH POST 返回 200 且包含正常 `stream:features`。随后执行 3 个单请求体爬坡（128KiB、512KiB、1MiB），分别记录 JVM RSS 与 `docker stats` 容器内存，结果仅出现小幅正增长，未触发 OOM、重启、请求拒绝或持续不可用，因此该案从 `environment_blocked` 改为 `observed_growth_not_confirmed`。
- 同步更新该 case 的 `result.json`、`reflection.jsonl`、`environment.md`、`data_prep.md`，共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl`，以及批次 `validation_status.jsonl`，并准备重新运行聚合脚本刷新汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/igniterealtime__openfire-F0154`
- environment 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/igniterealtime__openfire-default`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过管理员-only 路径、非默认 feature flag 或关闭安全控制制造成功。
- 新证据将 Openfire 的默认安装阻塞点从“官方 autosetup 空指针”精确收紧为“第一次 case-local bootstrap 缺失镜像默认 security 资产”；一旦按官方 entrypoint 预期保留这些资产，默认文档化 autosetup 即可成立，后续阻塞不再是环境，而是仅观察到 bounded growth、尚未达到动态确认阈值。

## [2026-08-13] Re-drive rill-flow default-image startup failure group

### 修改时间
2026-08-13 23:59

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 继续复核 `weibocom__rill-flow-F-001`、`weibocom__rill-flow-F-002`、`weibocom__rill-flow-F-003` 的既有 blocked 原因、环境工件与默认 compose 路径，只允许默认部署、隔离端口/资源、文档化 companion services 和行为中性的运行时兼容修复，不修改业务代码、不关闭安全控制。
- 在此前已修复 host 端口冲突与 MySQL `setup.sql` 可读性的基础上，确认官方 `weibocom/rill-flow:latest` backend 仍会在默认镜像启动链内于 Spring Boot 2.7 / Micrometer `ProcessorMetrics` 初始化阶段触发 `jdk.internal.platform.cgroupv2.CgroupV2Subsystem.getInstance` 的 `anyController` 空指针，导致 `processorMetrics` bean 创建失败，HTTP 路由始终无法 ready。
- 新增一次兼容性重试：复用同一默认 companion services、相同环境变量和官方镜像，仅额外施加 `--cgroupns=host` 与只读 `/sys/fs/cgroup` 挂载，验证是否是容器 cgroup 可见性问题。结果该重试仍复现同一 `anyController null -> processorMetrics` 崩溃，说明阻塞点不是启动顺序、伴随服务缺失或简单 cgroup namespace 可见性，而是官方默认镜像内 OpenJDK 17.0.2 与当前 cgroup v2 宿主组合下的运行时缺陷。
- 同步更新共享环境 `feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl` 与三个 case 的 `result.json`、`reflection.jsonl`、批次 `validation_status.jsonl`，将 blocked 语义进一步收紧为“默认镜像/运行时组合缺陷导致 backend 无法进入语义预检”，并准备重新运行聚合脚本刷新汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- 新增环境日志：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default/backend_cgroupns_host_retry_20260813.log`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过关闭鉴权、关闭指标、变更 feature flag 或替换非官方镜像制造成功。
- 新证据把 `weibocom/rill-flow` 三案的默认环境阻塞原因从泛化的“backend 未 ready”进一步收紧为：官方 backend 镜像携带的 OpenJDK 17.0.2 / Micrometer `ProcessorMetrics` 在当前 cgroup v2 宿主上启动即崩，而不是 MySQL、Redis、Jaeger、sample-executor、端口或 descriptor seed 缺失。

## [2026-08-13] Trust local pinned commits for full batch provenance

### 修改时间
2026-08-13 23:58

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 调整 `dosweb/llm/deepseek.py` 的 provenance 语义：当 `source_checkout` 与 `source_commit_sha` 已提供时，full 模式允许不再要求每次通过 GitHub public-source API 重新证明；未配置 `public_source_url` 时改为仅校验本地 git checkout 绑定到目标 commit、工作树干净且无 replace refs。
- 保留已有公开源码校验路径：只有显式提供 `public_source_url` 时才继续执行 GitHub public-source attestation 与 origin 一致性检查，因此公开仓库基线仍可复用原有严格证明逻辑。
- 调整 `dosweb/batch/runner.py` 与 `dosweb/batch/plan.py`：full batch 不再因为 `provider_eligible=false` 自动 paused；对非 `git-commit` 指纹目标，runner 会直接从本地 provider checkout 解析当前 `HEAD` 作为 provider commit，并在必要时用 detached worktree 固定到该 commit 后继续执行。
- 调整 `dosweb/llm/cache.py` 与相关测试，使本地 provenance 模式下 `verified_public=false`、`verified_clean_checkout=true` 的缓存身份和校验逻辑保持一致。
- 新增并更新 `tests/test_deepseek_client.py`、`tests/test_batch_runner.py`、`tests/test_batch_plan.py` 回归测试，覆盖本地 commit 绑定、tree-sha256 full 调度、worktree fallback 与 helper 语义更新。
- 运行 `python -m pytest -q tests/test_deepseek_client.py tests/test_batch_runner.py tests/test_batch_plan.py tests/test_config_and_cli.py`，结果 `157 passed`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/llm/deepseek.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/batch/runner.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/batch/plan.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/dosweb/llm/cache.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_deepseek_client.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_batch_runner.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/tests/test_batch_plan.py`
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`

### 依赖与影响
- full 模式现在默认信任“已在本地固定并可自校验的当前 commit”，不再把重复 GitHub attestation 当作运行前置，因此可继续处理已验证过一轮的本地源码样本。
- 若调用方仍提供 `public_source_url`，原有公开来源证明链保持启用，不影响需要严格 public-source provenance 的场景。

## [2026-08-13] Re-drive lamp-cloud non-simple environment-blocked case

### 修改时间
2026-08-13 23:42

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核 `dromara__lamp-cloud-FND-001` 的既有 blocked 原因、环境工件、默认部署文档与 round-1 阻塞日志，继续只按默认 `lamp-cloud` 路径检查可补齐的环境前置，不修改业务代码、不启用非默认行为。
- 重新执行文档化构建命令 `mvn -q -pl lamp-gateway/lamp-gateway-server -am -DskipTests package`，再次确认默认启动链在 bootstrap 之前就被 `lamp-dependencies-parent/pom.xml` 的外部前置拦住：该仓库明确要求先单独下载并构建 sibling `lamp-util`，把 `top.tangyh.basic:lamp-parent:5.10.0` 等 artifacts 安装进本地 Maven 仓库；当前 workspace 中缺失该 sibling 源码，且配置镜像也不提供该 parent POM。
- 纠正此前过泛的“Nacos 配置缺失”表述：仓库实际内置了 `A极其重要/01-third-party/nacos/nacos_config_export_20260615232624.zip`，其中包含 `common.yml`、`redis.yml`、`mysql.yml`、`rabbitmq.yml` 与 `lamp-gateway-server.yml`。因此本轮将 `inventory.json`、`readiness.json`、`notes.txt`、`changes.jsonl`、`environment.md`、`result.json` 与 `validation_status.jsonl` 全部收紧为更精确的阻塞语义——默认路径真正无法补齐的是缺失的 `lamp-util` 构建资产，以及由此无法启动 gateway/downstream services。
- 保持该案终态为 `environment_blocked`：即使 Nacos seed material 可用，默认 `/v3/api-docs/swagger-config` 聚合路径仍需要 buildable gateway 和至少一个向 Nacos 注册 swagger route 的下游 lamp 服务；在缺失 `lamp-util` sibling 源码的当前 workspace 中，这一步无法通过默认流程完成。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- case 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- environment 目录：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过管理员路径、关闭安全控制、非默认 feature flag 或伪造服务图来制造成功。
- 新证据把阻塞点从笼统的“默认环境缺配置”收紧为：默认源码构建依赖仓库外的 `lamp-util` sibling 资产，而当前 workspace 未提供它；因此该案属于默认流程下无法机械补齐的外部构建资产缺失。

## [2026-08-13] Re-drive environment-repairable dynamic blocked group

### 修改时间
2026-08-13 20:35

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核并重试 `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS`、`cryostatio__cryostat-legacy-F-WS-001`、`igniterealtime__openfire-F0154`、`weibocom__rill-flow-F-001`、`weibocom__rill-flow-F-002`、`weibocom__rill-flow-F-003` 的既有 blocked 原因、环境工件与默认部署路径，只允许默认部署、隔离端口/资源与文档化 companion services。
- 对 `weibocom/rill-flow` 先修复共享工作站上的 host 端口冲突：把 backend/UI/Jaeger/MySQL 映射改为 `18083/18003/16689/13316` 后，官方 compose 已能完整拉起容器，从而确认早先 `backend_inspect.json` 里的 18080 bind 错误只是外部冲突；但 backend 随后仍在默认镜像启动链内因 OpenTelemetry/Micrometer 访问 cgroup v2 时 `anyController` 为空而空指针退出，`processorMetrics` bean 创建失败，三案继续 `environment_blocked`，阻塞语义已从泛化的“未 ready”收紧为默认镜像内部启动失败。
- 对 `cryostatio/cryostat-legacy` 继续按官方 `run-docker.sh`/README 路径补齐环境变量：新增三次 bounded retry，分别验证文档化 `CRYOSTAT_JDBC_*`、其与 `QUARKUS_S3_*` 的组合，以及再叠加 `QUARKUS_DATASOURCE_*` 的情况。结果表明官方镜像始终在 HTTP 监听前退出：先要求 `quarkus.s3.*`，再无法激活默认 Quarkus datasource，继续强行叠加后又暴露 `quarkus.datasource.db-kind` 构建期固定与 Agroal/Flyway 拒绝文档化 H2 URL 的不兼容，因此继续 `environment_blocked`，且阻塞点已更精确。
- 对 `igniterealtime/openfire` 重读仓库 `documentation/install-guide.html`，确认 autosetup 的确是文档化默认路径之一；结合既有容器日志，将 blocked 原因收紧为：official image 的 case-local embedded autosetup 在 `JiveGlobals.setupPropertyEncryptionAlgorithm` 处因旧算法值为空而空指针退出，而不是笼统的“autosetup 失败”。
- 对 `apache/openmeetings` 复核启动日志后收紧 blocked 原因：clean case-local 源码副本构建出的默认 release 包实际已经启动并记录 `Openmeetings is up and ready to use`，但 `admin.sh -i` 后前台 HTTPS signin 仍回落到 `/install`，说明默认 H2 安装态并未真正完成到可登录 UI，因此仍无法补齐 presenter 房间会话与 upload SID。
- 同步更新六案 `result.json`、共享环境 `changes.jsonl`、新增 retry 日志工件、批次 `validation_status.jsonl`，并准备重新运行聚合脚本刷新汇总报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- 新增环境日志：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cryostatio__cryostat-legacy-default/retry_20260813.log`
- 新增环境日志：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default/backend_retry_20260813.log`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过管理员-only 路径、非默认 feature flag 或关闭安全控制制造成功。
- `weibocom/rill-flow` 的 retry 证明当前首要阻塞已不再是 host 端口冲突，而是默认 backend 镜像自身在 cgroup 指标初始化阶段的启动失败。
- `cryostatio/cryostat-legacy` 的 retry 证明即使沿文档化 JDBC 路径继续补齐，官方镜像仍卡在 Quarkus datasource/build-time 属性不兼容，无法进入 `/health`。

## [2026-08-13] Re-drive blocked dynamic preconditions for Airavata, Bonita, and Stirling

### 修改时间
2026-08-13 20:20

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核 `apache__airavata-FND-200-1`、`bonitasoft__bonita-engine-FND1` 与 `stirling-tools__stirling-pdf-F-vulnerable-decompression` 的既有 blocked 原因、环境工件、轮次证据与 `result.json`，重点重新检查默认部署、普通账号/业务前置与默认流程可补齐性。
- 对 Stirling 进一步排除了持久化配置副作用：保留官方 `latest` 镜像与仅隔离资源余量，清空旧 `/configs` 后按文档化无登录默认模式 `SECURITY_ENABLELOGIN=false` 重启，补做 round-2 单请求语义预检与 round-3 32 路并发有界解压验证。新证据显示匿名 `POST /api/v1/misc/decompress-pdf` 在默认无登录模式下可达，32/32 请求均返回 200，峰值容器内存约 `1.274GiB / 1.5GiB`，但未触发 OOM、重启或持续不可用，因此将该案从 `auth_blocked` 修正为 `not_reproduced_under_tested_bounds`。
- 对 Bonita 进一步收紧阻塞表述：环境已证明默认镜像可启动且会种入 `Administrator`/`User` profile，但本轮仍未找到默认自助注册或普通非管理员账号创建链路，只有 `install/install` bootstrap 账号有证据，因此继续保持 `auth_blocked`。
- 对 Airavata 进一步收紧阻塞表述：环境、默认资源与管理员认证仍正常，但默认 Echo 实验/文件前置仍卡在 seeded SFTP 存储认证，且 README 依赖的 sibling `airavata-portals` 仓库仍缺失，故继续保持 `precondition_blocked`。
- 同步更新三案的 `reflection.jsonl`、Stirling 的新增 `round-2/round-3` 工件、三案 `result.json`/共享 `validation_status.jsonl`，并准备重新运行聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- Airavata case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__airavata-FND-200-1`
- Bonita case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/bonitasoft__bonita-engine-FND1`
- Stirling case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/stirling-tools__stirling-pdf-F-vulnerable-decompression`

### 依赖与影响
- 本次未修改任何目标业务代码，也未通过非默认 feature flag、关闭安全控制或管理员替代低权限模型来制造成功。
- Stirling 的修正说明此前 `auth_blocked` 结论受持久化配置副作用干扰；在恢复官方默认无登录路径后，该案已不再 blocked，但在测试边界内仍未动态确认。
- Airavata 与 Bonita 仍 blocked，且阻塞点已细化到默认流程中具体无法补齐的步骤。

## [2026-08-13] Final aggressive round for zfile multipart growth-only case

### 修改时间
2026-08-13 23:03

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核 `/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zfile-dev__zfile-ZFILE-APP-STATIC-0001/` 的既有 `rounds/`、`reflection.jsonl` 与 `result.json`，确认该案仍处于 `observed_growth_not_confirmed` 且还剩最后一轮预算，因此仅新增并执行唯一允许的 round-3 更激进但仍有界确认尝试。
- 将默认 local-build 隔离实例在相同 runtime-home 上重启到更低但仍安全的 `-Xmx384m`，为 round-3 新增 `hypothesis.json`、`preflight.json`、`probe.py`、`observations.json`、`metrics.jsonl` 与目标侧日志证据，并把攻击强化为三波连续的 8 路并发 1000-part metadata-only multipart burst。
- 新证据显示 24 个请求全部继续返回 200，`/api/install/status` 在每波后与最终等待后始终返回 200；目标 RSS 从约 `511512 kB` 台阶式抬升到约 `547392 kB` 并保留，线程/fd 很快回落，但未触发 OOM、重启、默认 parser rejection 或持续不可用，因此终态保持 `observed_growth_not_confirmed`。
- 同步更新该 case 的 `reflection.jsonl`、`result.json`、批次 `validation_status.jsonl`，并重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- zfile case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zfile-dev__zfile-ZFILE-APP-STATIC-0001`
- zfile environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/zfile-dev__zfile-default`

### 依赖与影响
- 本次只执行一轮新增 destructive probe，严格停在第 3 轮上限内，且未通过关闭默认安全控制或启用非默认功能制造成功。
- 当前证据证明默认路径匿名 multipart metadata burst 仍可带来目标侧 retained RSS growth，但即使在更低隔离堆下连续多波也未跨过失败阈值，因此不得误报为 confirmed。

## [2026-08-13] Final aggressive round for GoCD fresh-session growth-only case

### 修改时间
2026-08-13 18:55

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 复核 `/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/gocd__gocd-F-GOCD-V2HP-001/` 的既有 `rounds/`、`reflection.jsonl` 与 `result.json`，确认该案仍有一轮预算，因此仅新增一轮更激进但仍有界的确认尝试。
- 为 round-2 新增 `hypothesis.json`、`preflight.json`、`probe.py`、`observations.json`、`metrics.jsonl` 与目标侧日志证据，在 fresh official GoCD 容器上把隔离上限收紧到 `768m` 容器/`512m` JVM heap，并提升到 2048 个匿名 fresh session、并发 32 的 `/go/api/v1/health` burst。
- 最终轮中全部 2048 个请求仍返回 200 且发放 2048 个唯一 `JSESSIONID`；target-side JVM `VmHWM` 升到 `755076 kB`、线程从 128 升到 150、容器内存升到 `762.6MiB / 768MiB`，20 秒后几乎不回落，但未触发 OOM、重启、拒绝请求或持续不可用，因此终态保持 `observed_growth_not_confirmed`。
- 更新 `case_plan.json`、`reflection.jsonl`、`result.json`、`validation_status.jsonl`，并准备重新运行共享聚合脚本刷新汇总结果。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- GoCD case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/gocd__gocd-F-GOCD-V2HP-001`
- round-2 观测：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/gocd__gocd-F-GOCD-V2HP-001/rounds/round-2/observations.json`
- 共享状态：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/validation_status.jsonl`

### 依赖与影响
- 仅执行一轮新增 destructive probe，未新增第 3 轮之后的越界尝试，也未通过关闭默认安全控制制造成功。
- 当前证据证明更强的默认路径 session/heap/thread growth，但仍不能表述为 confirmed DoS；后续如无新的默认路径证据，应继续保持非 confirmed 口径。

## [2026-08-13] Re-drive QuickDrop upload-task case

### 修改时间
2026-08-13 02:10

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 复核 `roastslav__quickdrop-FND-QUICKDROP-UPLOAD-TASKS` 的既有 `result.json`、`reflection.jsonl`、`preflight.json`、`probe.sh` 与前两轮证据，确认上轮并非语义未打通，而是只做了串行 16 次低强度 staircase，尚未检验 cached-thread burst growth 是否会跨过默认容量阈值。
- 在不新增第 4 轮的前提下补齐并执行现有 `round-3`：复用官方 `roastslav/quickdrop:latest` 默认镜像与既有持久化数据目录，只提高 distinct incomplete upload 基数到 96、并发到 8，并持续采集 `/proc/1/status` 线程/RSS、fd 数、`/app/files` 文件数、`/actuator/health` 与根路由状态。
- 新证据显示 96 个匿名不完整上传全部返回 200，threads 从 58 升至 159、fd 从 23 升至 120、持久文件数从 22 升至 118，10 秒后仍几乎完全保留；但健康检查始终 `UP`、root 维持默认 302，未触发 OOM、重启或持续不可用，因此终态仍必须保守维持为 `observed_growth_not_confirmed`。
- 同步更新该 case 的 `case_plan.json`、`environment.md`、`data_prep.md`、`hypothesis.json`、`preflight.json`、`probe.sh`、`metrics.jsonl`、`observations.json`、`reflection.jsonl`、`result.json` 与批次 `validation_status.jsonl`，并准备重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- QuickDrop case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/roastslav__quickdrop-FND-QUICKDROP-UPLOAD-TASKS`
- QuickDrop environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/roastslav__quickdrop-default`

### 依赖与影响
- 依赖官方 `roastslav/quickdrop:latest` 默认镜像、既有一次性 admin setup 结果与持久化 `/app/db` `/app/log` `/app/files` 数据目录；本次未修改业务代码、认证语义或默认路由行为。
- 该 case 已在三轮上限内完成更强 PoC 重打：第三轮把证据从低强度串行增长推进到 96 请求 burst 后仍保留的高 threads/fd/file growth，但仍不能误报为 confirmed。
- 后续若继续，只能基于新的 failure 假设或不同默认边界单开任务，不能在本轮再追加第 4 个 destructive round。

## [2026-08-13] Re-drive Guacamole dynamic group

### 修改时间
2026-08-13 01:47

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 复核 `apache__guacamole-client-GUAC-APP-STATIC-0001` 与 `apache__guacamole-client-GUAC-APP-STATIC-0002` 的既有 `result.json`、`reflection.jsonl`、`preflight.json`、`probe.py` 与 round-3 证据，确认两案上轮卡点都不是语义未打通，而是压力与目标特异指标还不够强：0001 仅做到 4000 retained sessions，0002 仅做到 96 tunnel/84 activeConnections。
- 在不新增第 4 轮的前提下直接重打现有 round-3：0001 提升到 12000 次成功登录、24 并发、180 秒 hold；0002 提升到 256 次 tunnel、32 路 burst、180 秒 keepalive，并保留 fresh-container 默认部署语义。
- 0001 新证据显示 GuacamoleSession 最终与成功 token 数对齐到 12000，容器内存约从 280.7MiB 升至 539.8MiB、堆升至约 125225 KiB 且 180 秒内未自动回落，但根路径持续 200，仍只能保守维持 `observed_growth_not_confirmed`。
- 0002 新证据显示 activeConnections 峰值达到 160、guacd TCP 达到 187，active set 清零后 Guacamole RSS/线程仍继续爬升到约 695268 KiB / 250 threads，说明默认路径存在更强的目标侧增长信号；但根路径始终 200，仍未达到 confirmed failure threshold，因此同样维持 `observed_growth_not_confirmed`。
- 同步更新两个 case 的 `case_plan.json`、`hypothesis.json`、`preflight.json`、`observations.json`、`reflection.jsonl`、`result.json` 与批次 `validation_status.jsonl`，并重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- Guacamole cases：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__guacamole-client-GUAC-APP-STATIC-0001`、`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__guacamole-client-GUAC-APP-STATIC-0002`
- Guacamole environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__guacamole-client-default`

### 依赖与影响
- 依赖官方 `guacamole/guacamole:1.6.0`、`guacamole/guacd:1.6.0` 与 PostgreSQL 默认镜像路径；本次未修改业务代码、认证语义或默认部署行为，只强化了现有第 3 轮探针。
- 两案现都完成了三轮上限内的更强重打：0001 证明更大 retained session 基数仍未触发失败，0002 则把证据从短暂 active-set 增长推进到 cleanup 后仍保留的高 RSS/线程增长，但都不能误报为 confirmed。
- 后续若继续，只能基于新的 failure 假设或不同默认边界建模单开任务，不能在本轮再追加第 4 个 destructive round。

## [2026-08-13] Correct ZAP proxy dynamic retest outcome

### 修改时间
2026-08-13 01:20

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 复核 `zaproxy__zaproxy-FIND-ZAP-001` 的既有三轮工件，确认该 case 并非只执行了早期 8 MiB 单轮，而是已完成 round-2 的 fresh-container 32 MiB plain-vs-gzip 同尺寸对照和 round-3 的 64 MiB 强化探针。
- 根据 round-2/3 证据修正终态：same-size 32 MiB 对照中 gzip 比 plain 额外抬升约 59.8 MiB cgroup memory 与约 61.6 MiB Java RSS，说明上轮真正卡点是“目标特异指标最初不足、需用同尺寸控制消解语义歧义”，而不是路由未打通；但 round-3 仍未触发 OOM、重启或持续不可用。
- 同步更新该 case 的 `result.json`、`reflection.jsonl`、`case_plan.json` 与批次 `validation_status.jsonl`，把错误的 `not_reproduced_under_tested_bounds` 修正为 `observed_growth_not_confirmed`，避免遗漏已存在的 growth-only 证据。
- 准备重新运行共享聚合脚本刷新总表、报告与 findings/blocklist 归档。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- ZAP case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zaproxy__zaproxy-FIND-ZAP-001`
- ZAP environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/zaproxy__zaproxy-default`

### 依赖与影响
- 依赖既有官方 `zaproxy/zap-stable:latest` 默认镜像、受控上游 companion 与已存档的 round-1/2/3 证据；本次未新增第 4 轮，也未改变默认部署语义。
- 修正后该 case 被正确计入 growth-only，而非 not reproduced；这会增加聚合层的 `observed_growth_not_confirmed` 计数并减少 `not_reproduced_under_tested_bounds` 计数。
- 三轮上限已经用尽；如需继续只能基于新的 deployment bound 或 failure 假设单开后续任务，不能在本轮再追加 destructive round。


## [2026-08-12] Re-drive GROBID dynamic group

### 修改时间
2026-08-12 16:35

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `grobidorg__grobid-GROBID-STATIC-001` 与 `grobidorg__grobid-GROBID-STATIC-002` 补齐 `round-2`/`round-3` 工件，修复上轮仅有路由与响应大小、缺失目标特异 JVM 指标的语义预检缺口。
- 新 PoC 复用官方 `grobid/grobid:0.9.0-crf` 默认镜像和既有 baseline-memory headroom 修复，只提高有效大 PDF 的并发度，并改从 Dropwizard admin `/metrics` 采集 heap、old-gen、GC 与线程指标。
- `GROBID-STATIC-001` 在 round-2 的 6 并发 8.2 MiB PDF 下先观察到 1.88 GiB heap / 1.31 GiB old-gen 增长，round-3 的 8 并发下再触发 `processFulltextAssetDocument` 中 `ByteArrayOutputStream`/`ZipOutputStream` 的目标侧 `OutOfMemoryError` 与 HTTP 500，终态更新为 `confirmed_oom`。
- `GROBID-STATIC-002` 在 round-2 的 8 并发 8.2 MiB PDF + `type=1` 下先观察到 2.13 GiB heap / 2.04 GiB old-gen 增长，round-3 的 10 并发 fresh-container 下再触发容器 `OOMKilled=true`、客户端空回复和健康检查丢失，终态更新为 `confirmed_oom`。
- 更新两个 case 的 `case_plan.json`、`reflection.jsonl`、`result.json`、`validation_status.jsonl`，并准备重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- GROBID cases：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/grobidorg__grobid-GROBID-STATIC-001`、`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/grobidorg__grobid-GROBID-STATIC-002`
- GROBID environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/grobidorg__grobid-default`

### 依赖与影响
- 依赖官方 `grobid/grobid:0.9.0-crf` 默认镜像与既有 baseline headroom 修复；本次未改业务代码、认证状态或路由行为。
- 两案现已从“指标不足导致的语义未打通”收敛到默认匿名 HTTP 路径上的目标资源失败证据，不再只是 growth-only 或 probe_semantics_failed。
- 该修复完成了本 group 在三轮上限内的 PoC 重打；后续如需继续只能针对新的 deployment bound 或 failure 假设，而不是新增第 4 轮。

## [2026-08-12] Re-drive HertzBeat anonymous SSE dynamic group

### 修改时间
2026-08-12 23:59

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `apache__hertzbeat-FND1`、`apache__hertzbeat-FND2`、`apache__hertzbeat-FND3` 新增 fresh-container 的 `round-2`/`round-3` 工件，包括 `hypothesis.json`、`preflight.json`、`probe.sh`、`metrics.jsonl`、`observations.json` 与容器日志，按技能要求把三案从仅有 20 连接 growth 证据扩展到更强但有界的 256/1024 SSE 长连接重打。
- 新 PoC 改为 raw HTTP socket 持续保持匿名 SSE 连接，并在每轮用 fresh 官方 Docker 容器采集 fd、线程、RSS 与 `jcmd 11 GC.class_histogram`；避免旧串行基线污染后，三案在 round-3 都稳定达到约 `+1025` fd 与 `+1025` `SseEmitter`，其中 `FND3` 还达到 `+1025` `LogSseManager$SseSubscriber`。
- 尽管增长与断连后未及时清理都被重复观察到，但根路径 `/` 在 live/post 阶段始终返回 200，未出现 OOM、重启、持续不可用或 admission failure，因此三案终态统一保守维持为 `observed_growth_not_confirmed`，而不误报 confirmed。
- 更新 3 个 case 的 `result.json`、`reflection.jsonl`、`case_plan.json` 与 `validation_status.jsonl`，并准备重新运行共享聚合脚本刷新总表与报告。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- HertzBeat cases：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__hertzbeat-FND1`、`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__hertzbeat-FND2`、`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__hertzbeat-FND3`
- HertzBeat environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__hertzbeat-default`

### 依赖与影响
- 依赖官方 `apache/hertzbeat` 单容器默认部署路径；本次未引入任何业务配置或权限变更，只复用既有隔离端口映射。
- 现有证据说明默认匿名 SSE 路径存在可线性放大的 retained growth，但在三轮上限内仍未触达默认部署 failure threshold，因此不能宣称 confirmed DoS。
- 该修复把 HertzBeat group 从“单轮压力不足”提升为“三轮上限内已完成强 PoC 重打”的终态，后续若继续只能基于新的 failure 假设而非重复放大同一轮次。

## [2026-08-12] Validate lamp-cloud dynamic group

### 修改时间
2026-08-12 20:50

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `dromara__lamp-cloud` group 新增 `environments/dromara__lamp-cloud-default/` 下的 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl`、`build_attempt.log` 等环境工件，结构化记录默认路径依赖的 Nacos/MySQL/Redis/RabbitMQ/下游服务前置条件与本地构建失败证据。
- 新增 `dromara__lamp-cloud-FND-001` 的 `case_plan.json`、`environment.md`、`data_prep.md`、`rounds/round-1/`、`reflection.jsonl` 与终态 `result.json`，将该 group 唯一 queued case 收敛到技能规范要求的终态。
- 受控本地构建 `lamp-gateway/lamp-gateway-server` 时，`mvn -q -pl lamp-gateway/lamp-gateway-server -am -DskipTests package` 因缺失外部父 POM `top.tangyh.basic:lamp-parent:5.10.0` 立即失败；结合仓库未提供已检入的 Nacos 导出与自包含默认 compose/镜像，无法在不臆造部署状态的前提下完成默认环境 bootstrap。
- 因 `/v3/api-docs/swagger-config` 还依赖下游 lamp 服务注册到 Nacos 并暴露各自 swagger-config，语义预检无法开始；最终将 `dromara__lamp-cloud-FND-001` 保守落为 `environment_blocked`，而非误报 confirmed 或 not_confirmed。
- 更新 `validation_status.jsonl` 中该 case 的终态与 failure_reason，并重新运行共享聚合脚本刷新 `summary.json`、`summary.csv`、`blocked_or_rejected.jsonl` 与 `DYNAMIC_VALIDATION_REPORT.md`。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- lamp-cloud case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/dromara__lamp-cloud-FND-001`
- lamp-cloud environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dromara__lamp-cloud-default`

### 依赖与影响
- 依赖 `frameworks/applications/dromara__lamp-cloud/README.md`、`A极其重要/01-docs/docker/03.docker运行项目.md` 与 gateway `application.yml` 中的默认部署说明；本次未引入源码或行为变更。
- 当前证据只说明默认环境未能自举，不构成默认部署下的 confirmed DoS，也不能据此反证静态候选无害。
- 该修复消除了本 group 唯一 queued case，后续若要继续只能先补齐官方可复现的 Nacos 配置与下游服务启动材料。

## [2026-08-12] Fix full-batch provenance and entry resolution failures

### 修改时间
2026-08-12 21:10

### 变更类型
- [Bug 修复]
- [测试]

### 核心改动
- 为 production/config/CLI 增加独立的 `analysis_source_root` 语义，并让 `dosweb/production.py` 的 preflight 仅用它校验 `database.source_root`，不再把 provider `source_checkout` 误当作 CodeQL database provenance 目标。
- 保留 `source_checkout` 作为 provider/pinned checkout，用于 Growth excerpt 与公开源码 attestation；同时在 `dosweb/batch/runner.py` full 模式下前移本地 provider checkout 预检，提前暴露 `CONFIG_PUBLIC_SOURCE_UNVERIFIED`，避免 target 跑到 growth 阶段才失败。
- 强化 `dosweb/production.py` 的 growth→entry 关联逻辑：优先最近 handler，并在必要时按 attacker input / demand input 收窄候选，且对仅 registration 不同的语义重复 entry 做稳定收敛，不再因同一 handler 多 registration 直接报 `ANALYSIS_GROWTH_ENTRY_AMBIGUOUS`。
- 同步更新 `dosweb/flows/models.py` 的 flow 引用解析，使 flow 阶段对同一 handler 位置的重复 entry 采用与 growth 一致的稳定收敛策略。
- 扩展 `dosweb/batch/aggregate.py` 输出，新增 `authoritative_status_counts` 并在 gap 摘要中显示 authoritative status / failure reason，便于区分 preflight 失败与普通缺失产物。
- 补充 `tests/test_config_and_cli.py`、`tests/test_production.py`、`tests/test_batch_runner.py`、`tests/test_batch_aggregation.py`、`tests/test_deepseek_client.py` 回归测试，覆盖 checkout 语义拆分、duplicate registration 收敛、本地 provider 预检与聚合状态可见性。

### 验证
- 运行 `python -m pytest -q tests/test_config_and_cli.py tests/test_production.py tests/test_batch_runner.py tests/test_batch_aggregation.py tests/test_deepseek_client.py`
- 结果：177 passed, 167 subtests passed

## [2026-08-12] Validate Suwayomi GraphQL websocket dynamic group

### 修改时间
2026-08-12 20:36

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `suwayomi__suwayomi-server` group 新增 `environments/suwayomi__suwayomi-server-default/` 的 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl`，记录本地文档化 `shadowJar` 启动、headless 环境下 jar 路径修正以及禁用可选 browser/system tray/KCEF 钩子的最小环境修复。
- 新增 `suwayomi__suwayomi-server-F-graphql-ws-retained-operation-state` 的 `case_plan.json`、`environment.md`、`data_prep.md`、两轮 `hypothesis.json`/`preflight.json`/`observations.json`、`reflection.jsonl` 和终态 `result.json`，将该 queued case 收敛到技能要求的终态。
- 动态语义预检确认默认匿名 `/api/graphql` WebSocket 可完成 `graphql-transport-ws` 握手并返回 `connection_ack`；活动重复 ID 会以 4409 关闭连接，而 `complete` 后可用同一 ID 重新订阅，吻合 static 对 `activeOperations` 与 `sessionToOperationId` 分离的建模。
- 两轮单连接唯一 subscribe/complete 阶梯（1000 个 128 字节 ID、5000 个 256 字节 ID）在会话存活期间观察到 JVM `java.lang.String` / `[B` 直方图增长，其中第二轮 live-session 增量达到 `+5132` 个 String 与 `+5138` 个 byte array，但 `/api/graphql` 始终健康且断开后大部分增长回落，因此保守落为 `observed_growth_not_confirmed`。
- 更新 `validation_status.jsonl` 中 Suwayomi case 的终态与 failure_reason，并准备重新运行共享聚合脚本刷新汇总结果。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- Suwayomi case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/suwayomi__suwayomi-server-F-graphql-ws-retained-operation-state`
- Suwayomi environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/suwayomi__suwayomi-server-default`

### 依赖与影响
- 依赖 `frameworks/applications/suwayomi__suwayomi-server/README.md` 中的本地 jar 运行路径；本次未使用官方 Docker 镜像，而是本地构建并在 headless 环境中关闭可选 GUI/KCEF 钩子。
- 该证据只证明 live-session retained-ID growth，不构成默认部署 confirmed DoS；后续若要继续只能在不超过三轮的前提下寻找更强的 target-resource failure 信号。
- 该修复消除了本 group 唯一 queued case，便于统一聚合脚本刷新总表。

## [2026-08-12] Validate wgcloud dynamic group

### 修改时间
2026-08-12 19:52

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 为 `tianshiyeben__wgcloud` group 补齐 `environments/tianshiyeben__wgcloud-default/` 的 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json`、`changes.jsonl` 以及本地构建配置、MySQL companion、延迟 SMTP stub、MAIL_SET seed 等最小环境工件。
- 新增 `tianshiyeben__wgcloud-FND1` 与 `tianshiyeben__wgcloud-FND2` 的 `case_plan.json`、`environment.md`、`data_prep.md`、round-1 `hypothesis.json`/`preflight.json`/`observations.json`、`reflection.jsonl` 和终态 `result.json`，并按技能要求将两案从 queued 收敛到终态。
- 将 `FND1` 保守落为 `non_default_only`：匿名 `/wgcloud/agent/minTask` 可用默认 `wgToken` 推导值命中，但观察到的告警邮件线程池阻塞依赖预置 MAIL_SET 与受控延迟 SMTP harness，不能表述为默认部署 confirmed。
- 将 `FND2` 落为 `observed_growth_not_confirmed`：受控数组 JSON 能在线性放大 `AppInfo`/`AppState`/`DeskState` 临时对象数量，但计划内 drain 后未见持久积压、数据库堆积或服务不可用。
- 更新 `validation_status.jsonl` 中 wgcloud 两案状态并准备重新运行共享聚合脚本刷新汇总产物。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- wgcloud case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/tianshiyeben__wgcloud-FND1`
- wgcloud case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/tianshiyeben__wgcloud-FND2`
- wgcloud environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/tianshiyeben__wgcloud-default`

### 依赖与影响
- 依赖 `frameworks/applications/tianshiyeben__wgcloud/` 仓库自带的本地构建+MySQL 文档路径；无官方 compose/image 可直接复用。
- `FND1` 的阻塞证据仅作为非默认组件级复现实验保存，不改变静态候选默认部署下未确认的口径。
- `FND2` 为 growth-only 证据，后续若要继续只能在不突破三轮上限的前提下针对 drain/persistence 吞吐做更强区分。

## [2026-08-12] Repair OpenGrok dynamic validation artifacts

### 修改时间
2026-08-12 19:24

### 变更类型
- [Bug 修复]
- [文档]

### 核心改动
- 修复 `oracle__opengrok-FIND-UI-SEARCH-COLLECTOR` 缺失 `result.json` 导致聚合报错的问题，补齐该 case 的 `case_plan.json`、`environment.md`、`data_prep.md`、`reflection.jsonl`、两轮 `hypothesis.json`/`preflight.json`/`observations.json` 以及终态 `result.json`。
- 补齐 `environments/oracle__opengrok-default/` 下缺失的 `inventory.json`、`feasibility.json`、`readiness.json`、`snapshot.json` 与 `changes.jsonl`，把已执行的官方 Docker 默认部署、最小一文档索引准备、JFR 重试与环境结论结构化落盘。
- 根据现有两轮证据将该 case 终态保守落为 `probe_semantics_failed`：默认匿名 `/search` 语义可达，但启动期与显式 `jcmd` 启动的 JFR 都未建立 target-specific collector allocation 遥测，因此不能提升为 confirmed 或 observed growth。
- 更新 `validation_status.jsonl` 中该 case 的终态与 failure_reason，并在补齐产物后重新运行聚合脚本刷新 `summary.json`、`blocked_or_rejected.jsonl` 与报告统计。

### 交付成果
- 修改文件：`/home/furina/new_tool/dos-analysis-web/CHANGELOG.md`
- 动态验证结果根：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812`
- OpenGrok case：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/oracle__opengrok-FIND-UI-SEARCH-COLLECTOR`
- OpenGrok environment：`/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/oracle__opengrok-default`

### 依赖与影响
- 依赖此前已保留的 OpenGrok 两轮 HTTP/JFR 原始证据文件，不重新执行更强探针。
- 该修复消除了输出根中的缺失 `result.json` 聚合错误，使 group 结果可被统一汇总。
- 无破坏性接口变更；仅补齐动态验证工件并收敛终态。

## [2026-08-12] Validate JetLinks default captcha dynamic group

### Changed

- Added isolated dynamic-validation artifacts for the `jetlinks__jetlinks-community` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflection, and terminal result files.
- Bootstrapped the repository's checked-in `docker/run-all/docker-compose.yml` default deployment locally with documented Redis and Timescale/Postgres companions, plus isolation-only host-port remapping and bounded JVM/container memory caps for a disposable safety harness.
- Confirmed that the anonymous default route `GET /authorize/captcha/image` is reachable without login and that a normal `130x40` request returns a Base64 captcha payload under the default compose deployment.
- Classified `jetlinks__jetlinks-community-JL-STAGEA-0001` as `confirmed_oom` because a bounded single-request staircase showed `15000x15000` driving memory to 98.54% of a 1.5 GiB container, and a follow-up `16384x16384` request immediately triggered repeated `java.lang.OutOfMemoryError: Java heap space` from `DataBufferInt`/`BufferedImage` on the target route while returning HTTP 500.
- Ran the required aggregate step after writing artifacts; if the shared aggregation script still reports issues on this output root, controller-side follow-up should focus on the aggregate outputs rather than this JetLinks case directory.

### Verification

- Preserved compose bootstrap logs, container inspect snapshot, readiness evidence, and environment change records under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/jetlinks__jetlinks-community-default/`.
- Preserved preflight samples, per-round metrics, observations, OOM log evidence, reflection, and the final result under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/jetlinks__jetlinks-community-JL-STAGEA-0001/`.

## [2026-08-12] Validate ZAP default proxy dynamic group

### Changed

- Added isolated dynamic-validation artifacts for the `zaproxy__zaproxy` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflection, and terminal result files.
- Bootstrapped the official `zaproxy/zap-stable:latest` Docker image locally with isolation-only host-port remapping and a 768 MiB container cap, then added a host-gateway mapping plus a disposable upstream companion container so the default external proxy path could fetch controlled plain and gzip responses without modifying target code or enabling non-default features.
- Confirmed that anonymous absolute-form proxy requests to the attacker-controlled upstream succeed by default and return client-visible decoded bodies for both plain and gzip responses, resolving the static add-on reachability uncertainty.
- Conservatively classified `zaproxy__zaproxy-FIND-ZAP-001` as `not_reproduced_under_tested_bounds` because bounded single-request probes up to 8 MiB decoded bodies produced observable target memory growth but no failure, and the clean-slate 8 MiB plain control consumed at least as much immediate memory as the gzip variant, so a stronger decompression-specific amplification effect was not isolated under the tested limits.

### Verification

- Preserved official-image startup logs, upstream-companion logs, container snapshot metadata, and bootstrap change records under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/zaproxy__zaproxy-default/`.
- Preserved control-vs-gzip probe evidence, semantic preflight, metrics, observations, reflection, and terminal result artifacts under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zaproxy__zaproxy-FIND-ZAP-001/`.

## [2026-08-12] Validate zfile multipart metadata dynamic group

### Changed

- Added isolated dynamic-validation artifacts for the `zfile-dev__zfile` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflection, and terminal result files.
- Built the repository's default Spring Boot jar locally with `mvn -q -DskipTests package` and launched an isolated disposable instance on port `38080` with a case-local `user.home` runtime directory after confirming host port `8080` was already occupied by an unrelated service.
- Completed the required first-run `POST /api/install` bootstrap against the fresh SQLite runtime, then validated that anonymous `PUT /file/upload/invalidStorageKey/x` requests reach multipart parsing before storage lookup: a non-multipart control failed with `Current request is not a multipart request`, while multipart requests progressed to the modeled invalid-storage error.
- Conservatively classified `zfile-dev__zfile-ZFILE-APP-STATIC-0001` as `not_reproduced_under_tested_bounds` because a bounded metadata-only staircase at 1/100/500/1000 parts with a 1-byte file payload caused only small transient RSS/thread movement and no meaningful retained growth, parser threshold below defaults, or service unavailability.

### Verification

- Preserved startup, install-status, and runtime-database evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/zfile-dev__zfile-default/`.
- Preserved control-vs-attack responses, bounded round metrics, and reflection/result artifacts under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/zfile-dev__zfile-ZFILE-APP-STATIC-0001/`.

## [2026-08-12] Validate Openfire dynamic group setup-gated BOSH path

### Changed

- Added isolated dynamic-validation artifacts for the `igniterealtime__openfire` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, blocked semantic preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `ghcr.io/igniterealtime/openfire:latest` image locally with isolation-only host-port remapping for the default BOSH and admin-console listeners; plain default startup reached the admin setup wizard on port `9090` but anonymous `/http-bind/` probes on port `7070` reset the TCP connection before any semantic response.
- Applied one targeted case-local embedded autosetup repair by bind-mounting a generated `openfire.xml` derived from the repository autosetup example so the official image could move beyond the initial setup gate without editing target code, but the packaged startup path still failed with a `NullPointerException` in `JiveGlobals.setupPropertyEncryptionAlgorithm` before HTTP/BOSH readiness.
- Conservatively classified `igniterealtime__openfire-F0154` as `environment_blocked` because no default-compatible ready BOSH environment was reached, so the queued anonymous body-materialization candidate could not pass semantic preflight or execute a bounded growth round.

### Verification

- Pulled and launched the official GHCR image locally, captured default setup-page behavior plus BOSH connection-reset evidence, and preserved container logs and inspect output under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/igniterealtime__openfire-F0154/` and `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/igniterealtime__openfire-default/`.
- Re-ran the image with one case-local embedded autosetup bootstrap repair, then captured the startup `NullPointerException` evidence showing that the official image still failed before a semantically testable `/http-bind/` state.

## [2026-08-12] Validate Cryostat legacy dynamic group bootstrap failure

### Changed

- Added isolated dynamic-validation artifacts for the `cryostatio__cryostat-legacy` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap change records, per-case planning, blocked semantic preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `quay.io/cryostat/cryostat:latest` image locally with isolation-only host-port remapping and case-local bind mounts that mirror the repository `run-docker.sh` path layout.
- Applied two targeted environment-side repairs before blocking: first added bounded dummy `quarkus.s3.endpoint-override` and `quarkus.s3.aws.region` runtime values because the packaged image refused to start without them, then added Quarkus default datasource environment keys because the packaged image ignored the legacy `CRYOSTAT_JDBC_*` values alone.
- Conservatively classified `cryostatio__cryostat-legacy-F-WS-001` as `environment_blocked` because the official image still exited before binding the HTTP listener: after the two repairs it reported an incompatible packaged datasource/db-kind expectation and rejected the documented H2 datasource path, so `/health`, `/api/v1/notifications_url`, and the queued notifications WebSocket semantic preflight never became reachable.

### Verification

- Pulled and launched the official Cryostat image locally, captured all three bounded startup attempts plus final container inspect evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cryostatio__cryostat-legacy-F-WS-001/` and `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cryostatio__cryostat-legacy-default/`.
- Confirmed that no attempt reached HTTP readiness on `http://127.0.0.1:18181/`, so no WebSocket retention round was executed and the worker stopped after environment diagnosis.

## [2026-08-12] Validate jmqtt dynamic group WebSocket idle retention

### Changed

- Added isolated dynamic-validation artifacts for the `cicizz__jmqtt` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflections, and terminal result files.
- Followed the repository's documented source-build quickstart (`mvn -Ppackage-all -DskipTests clean install` plus local `jmqtt-broker-3.0.0.jar` startup) instead of switching to a non-documented deployment model, and copied the checked-in default broker config into a case-local runtime directory with isolation-only port remapping.
- Bootstrapped a disposable `mysql:5.7` companion because the broker's checked-in default config requires MySQL; one compatibility-only repair created `jmqtt_session` with a `CURRENT_TIMESTAMP` default for `online_time` after the bundled `jmqtt.sql` timestamp definition failed under the tested MySQL defaults.
- Classified `cicizz__jmqtt-FND-002` as `observed_growth_not_confirmed` because anonymous WebSocket handshakes to `/mqtt` succeeded, a handshake-only pre-CONNECT channel remained alive through 70 seconds despite the configured 60-second idle path, and bounded 1/3/5-channel probes increased established sockets proportionally, but the conservative run did not pursue service degradation or target-resource failure.

### Verification

- Built the broker locally, launched the disposable MySQL companion plus the local jar with copied default config, and captured startup/readiness evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/cicizz__jmqtt-default/`.
- Executed a raw WebSocket handshake readiness probe, a 70-second idle-retention probe, and a bounded connection staircase, and captured the resulting evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/cicizz__jmqtt-FND-002/rounds/round-1/evidence/`.

## [2026-08-12] Validate CommaFeed dynamic group bounded refresh-queue behavior

### Changed

- Added isolated dynamic-validation artifacts for the `athou__commafeed` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, bootstrap changes, per-case planning, semantic preflight, bounded round artifacts, reflections, and terminal result files.
- Bootstrapped the official `athou/commafeed:latest-h2` Docker image locally with only isolation-only host-port remapping and a fixed session-encryption key for repeatable local login cookies; the default deployment otherwise remained unchanged and used the built-in H2 database.
- Completed the default `POST /rest/user/initialSetup` flow to create the first admin account, then created one ordinary `USER` account through the default admin API because `commafeed.users.allow-registrations=false` in the default deployment.
- Tried a case-local delayed mock feed first, but the default fetch path rejected `host.docker.internal` as a local address, so the executed bounded probe conservatively switched to five public RSS/Atom feeds reachable under the default deployment.
- Classified `athou__commafeed-F0002` as `not_reproduced_under_tested_bounds` because two overlapping authenticated `GET /rest/feed/refreshAll` calls over five persisted subscriptions caused `FeedRefreshEngine.queue.size` to rise only transiently to `5`, with default `worker.active` peaking at `3` and draining back to `0` within about two seconds, without sustained retained queue growth or service unavailability.

### Verification

- Launched the official CommaFeed Docker image locally, verified `/rest/server/get`, completed initial setup, authenticated as both admin and ordinary user, and collected `/rest/admin/metrics` evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/athou__commafeed-F0002/`.
- Executed a bounded concurrency-2 `refreshAll` probe and captured queue-depth, worker-activity, feed-fetch meter, server info, container logs, and container inspect evidence under the CommaFeed case directory.

## [2026-08-12] Validate Bonita dynamic group auth preflight

### Changed

- Added isolated dynamic-validation artifacts for the `bonitasoft__bonita-engine` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, changes, startup/container logs, route/auth probe evidence, per-case plan, blocked preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `bonita:latest` Docker image locally with a disposable `postgres:15-alpine` companion on an isolated Docker network. Two targeted compatibility-only repairs were required before readiness: retrying startup after the Postgres companion became ready, and creating the expected `businessdb` / `businessuser` companion database objects required by the image defaults.
- Confirmed that the default deployment serves `/bonita/` and redirects anonymous `/bonita/portal/fileUpload` requests to `login.jsp`. The default `install/install` account can authenticate and complete a tiny multipart upload, but this run did not establish a documented ordinary non-admin account for the queued low-privilege attacker model.
- Conservatively classified `bonitasoft__bonita-engine-FND1` as `auth_blocked` because the static probe plan requires an ordinary authenticated non-admin user for `/portal/fileUpload`, and only installer-level credentials were validated before semantic preflight stopped.
- Ran the required aggregate step after writing artifacts; the shared `aggregate_dynamic_validation.py` script still exited non-zero on this output root without emitting diagnostics, so the worker preserved artifacts and updated `validation_status.jsonl` directly.

### Verification

- Pulled and launched the official Bonita image with an isolated Postgres companion, captured successful Tomcat/Bonita startup evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/bonitasoft__bonita-engine-default/`, and recorded the compatibility repairs applied during bootstrap.
- Verified anonymous login redirection, successful `install/install` authentication, and a tiny authenticated multipart upload under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/bonitasoft__bonita-engine-FND1/rounds/round-1/evidence/auth_and_upload_probe.json`, while preserving the low-privilege auth gap as the terminal blocker.

## [2026-08-12] Validate OpenMeetings dynamic group startup and preflight

### Changed

- Added isolated dynamic-validation artifacts for the `apache__openmeetings` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, changes, clean rebuild workspace notes, per-case plans, blocked semantic preflight, observations, reflection, and terminal result files.
- The repository snapshot’s local static-analysis artifacts under `frameworks/applications/apache__openmeetings/results/` caused the documented `mvn ... -PallModules` build path to fail the ASF RAT gate, so one targeted mechanical repair rebuilt the official release package from a clean case-local source copy that excluded those non-upstream result files.
- Bootstrapped the clean official `apache-openmeetings-9.2.0-SNAPSHOT` release package locally with isolation-only port remapping from `5080/5443` to `15080/15443`; Tomcat and the OpenMeetings webapp reached runtime startup, but the bundled `admin.sh` default-H2 install attempt still left the application redirecting `/openmeetings/signin` back to `/openmeetings/install`.
- Conservatively classified `apache__openmeetings-FND-UPLOAD-CONVERSION-WORKERS` as `environment_blocked` because the candidate requires a fully installed deployment plus an authenticated presenter already inside a room with a live `omws-upload-sid`, and that semantic room bootstrap could not begin while the default deployment remained in install mode.
- Ran the required aggregate step after writing artifacts; as with other groups on this shared output root, central re-aggregation may still need controller-side review if the shared script continues exiting non-zero without detailed diagnostics.

### Verification

- Rebuilt the documented release package from a clean case-local source copy, extracted the official tarball, applied only isolated port remaps, and captured successful Tomcat/OpenMeetings startup plus persistent install-mode evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__openmeetings-default/`.
- Verified that `/openmeetings/services/UserService?wsdl` was deployed while `/openmeetings/signin` still redirected to `/openmeetings/install`, preventing any valid presenter-room upload preflight.

## [2026-08-12] Validate Airavata dynamic group bootstrap and block state

### Changed

- Added isolated dynamic-validation artifacts for the `apache__airavata` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, compose override/bootstrap records, container inspection, token/bootstrap evidence, per-case planning, environment/data-prep notes, reflection, launch-attempt logs, and terminal result files.
- Built the repository-native `airavata-server:dev` and `airavata-slurm:dev` images from the checked-out source and bootstrapped a case-local approximation of the documented quickstart stack (`compose.yml`) in isolated Docker networking because this worker host lacks the repository's expected Tilt/Colima/mkcert devstack substrate.
- Applied one targeted environment-side repair by changing the case-local Keycloak hostname override from `localhost` to the in-network service name `keycloak`, so JWT `iss` values became resolvable by the Airavata server container for JWKS verification without changing target business code.
- Classified `apache__airavata-FND-200-1` as `precondition_blocked` because the default documented stack became healthy and the seeded default-admin token could enumerate the seeded `Default Project`, `Echo`, `slurm`, and `sftp` resources, but the only safe default-flow route to an own-process file failed earlier at the SDK's seeded SFTP experiment-directory bootstrap with `paramiko` SSH protocol-banner errors, so no semantic preflight or bounded file-download probe could begin.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status `1` and no diagnostics on this output root, so the Airavata worker preserved all artifacts and updated `validation_status.jsonl` directly after executing the required aggregation step.

### Verification

- Built the Airavata server and SLURM images locally, launched the documented dependency stack plus the local server image in isolated Docker networking, and captured healthy HTTP, Keycloak, SFTP, MariaDB, and SLURM readiness evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/apache__airavata-default/`.
- Retrieved a real default-admin Keycloak token over the Docker network, verified the repaired issuer claim, confirmed seeded project/application/resource visibility over the live Airavata gRPC API, and captured the blocking SFTP bootstrap failure under `results/applications_dynamic_validation/java_web_46_candidates_20260812/cases/apache__airavata-FND-200-1/`.

## [2026-08-12] Validate Dependency-Track dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `dependencytrack__dependency-track` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, compose/bootstrap files, startup logs, container inspect data, scoped auth/data bootstrap evidence, per-case plans, semantic preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official Dependency-Track quickstart-equivalent image set (`ghcr.io/dependencytrack/apiserver:5.0.4`, `ghcr.io/dependencytrack/frontend:5.0.4`, `postgres:18-alpine`) in an isolated local compose stack. Two targeted compatibility-only mechanical repairs were required before readiness: remapping the PostgreSQL 18 bind mount from `/var/lib/postgresql/data` to `/var/lib/postgresql`, and switching removed v4/v5 transitional database environment variable names to the exact v5 `DT_DATASOURCE_DEFAULT_*` keys expected by the apiserver.
- Completed the default first-login password change for `admin/admin`, then used only official REST APIs to create the low-privilege `dosval_user`, scoped `DosvalTeam`, team API key, and an accessible `dosval-project` so the queued authenticated routes could be exercised without changing target business code.
- Classified `dependencytrack__dependency-track-DTRACK-APP-STATIC-0001` as `not_reproduced_under_tested_bounds` because the low-privilege scoped API key reached `PUT /api/v1/bom` and all bounded stepped JSON BOM uploads up to roughly 100 KiB decoded content were accepted with `200` responses and import tokens, but no default rejection bound, target-specific growth signal, or service-failure evidence was observed in the conservative single-request staircase.
- Classified `dependencytrack__dependency-track-DTRACK-APP-STATIC-0004` as `not_reproduced_under_tested_bounds` because the same scoped API key reached `POST /api/v1/vex` and all bounded stepped multipart VEX uploads up to roughly 100 KiB decoded content were accepted with `200` responses and import tokens, but no multipart rejection bound, target-specific growth signal, or service-failure evidence was observed in the conservative single-request staircase.
- The required aggregate step will still be executed after artifact publication for this group; existing evidence indicates the shared aggregator may continue to exit with status `1` and no diagnostics on this output root, so the worker preserved all case/environment artifacts and updated `validation_status.jsonl` directly.

### Verification

- Launched the official quickstart-equivalent image set locally with isolation-only host port remapping and bounded resources; captured both initial startup failures and repaired ready-state evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dependencytrack__dependency-track-default/`.
- Verified default API/frontend readiness, admin first-login force-change semantics, scoped low-privilege project access, and bounded accepted BOM/VEX upload responses under the two Dependency-Track case directories.

## [2026-08-12] Validate GoCD dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `gocd__gocd` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, startup logs, container inspect data, per-case plans, semantic preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official `gocd/gocd-server:v26.1.0` Docker image locally in isolation. The first attempt failed because a bind-mounted `/godata` path was not writable by the container entrypoint, so one targeted mechanical repair switched only the persistence mount to a Docker named volume and the default image then became ready on `http://127.0.0.1:18153/go`.
- Classified `gocd__gocd-F-GOCD-V2HP-001` as `observed_growth_not_confirmed` because anonymous fresh requests to `/go/api/v1/health` repeatedly received new `JSESSIONID` cookies while a cookie-reusing control stopped receiving fresh cookies, confirming pre-auth session creation semantics without collecting internal Jetty session-cardinality or failure evidence.
- Classified `gocd__gocd-F-GOCD-V2HP-002` as `not_reproduced_under_tested_bounds` because tiny anonymous POSTs to `/go/api/webhooks/github/notify` and `/go/api/webhooks/hosted_bitbucket/notify` reached HMAC-mismatch rejection in the default deployment, but the bounded probe did not escalate body size or observe any resource-failure signal.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status `1` and no diagnostics on this output root, so the GoCD worker preserved all artifacts and updated `validation_status.jsonl` directly after executing the required aggregation step.

### Verification

- Launched the official GoCD server image locally with isolation-only host port remapping and bounded container resources; captured startup failure evidence for the unwritable bind mount, then captured ready-state HTTP probes plus final container logs under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/gocd__gocd-default/`.
- Executed bounded anonymous health-route cookie probes and tiny invalid-signature webhook probes, and captured Set-Cookie behavior plus 401 mismatch responses under the two GoCD case directories.

## [2026-08-12] Validate Ant Media dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `ant-media__ant-media-server` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including official-image environment inventory, feasibility, readiness, snapshot, startup logs, container inspect evidence, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Attempted the repository-native packaged build path first, but the checked-in source snapshot could not resolve the required `io.antmedia:parent:4.0.0-SNAPSHOT` parent POM; to stay within default-deployment guidance, the worker then switched to the official `antmedia/community:latest` Docker image rather than editing build files or target code.
- Confirmed that the official community image boots successfully in isolation and auto-deploys the `live`, `WebRTCApp`, and `LiveApp` contexts on HTTP port `5080`, resolving the earlier static uncertainty about packaged route availability.
- Classified `ant-media__ant-media-server-AMS-V2HP-UNKNOWN-001` as `default_not_reachable` because the default `live` app does deploy `ChunkedTransferServlet` on `/chunked/*` and `*.m4s`, but the first tiny external HTTP POST was rejected by the default `IPFilter` with `403 Not allowed IP` before `AtomParser` execution could be observed.
- Classified `ant-media__ant-media-server-AMS-V2HP-UNKNOWN-002` as `not_reproduced_under_tested_bounds` because the default `live` websocket endpoint accepted an anonymous publish handshake and started the adaptor lifecycle, yet the bounded single-session probe observed immediate stop/cleanup after close and no persistent retained thread or adaptor growth.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status 1 and no diagnostics on this output root, so the Ant Media worker preserved all artifacts and updated `validation_status.jsonl` directly after running the required aggregation step.

### Verification

- Pulled and launched the official `antmedia/community:latest` Docker image locally with isolation-only port remapping and bounded container resources; captured startup logs, container inspect output, deployed `web.xml` route mappings, and HTTP readiness probes under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/ant-media__ant-media-server-default/`.
- Executed a bounded tiny `ChunkedTransferServlet` POST preflight and a raw WebSocket upgrade plus single publish-command lifecycle probe, and captured the `403 Not allowed IP`, HTTP `101` upgrade, websocket `start` reply, and post-close cleanup log evidence under the Ant Media case directories.

## [2026-08-12] Validate OpenKM dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `openkm__document-management-system` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including official-image environment inventory, feasibility, readiness, snapshot, runtime configuration capture, changes, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official `openkm/openkm-ce:latest` Docker image locally in isolation, confirmed the default admin login, and created one ordinary `ROLE_USER` account through the authenticated REST admin API so the queued low-privilege routes could be exercised without changing target business code.
- Classified `openkm__document-management-system-F-OPENKM-002` as `observed_growth_not_confirmed` after a bounded single-request staircase with unique ZIP archives showed clear entry-count-driven latency growth on `/frontend/FileUpload?importZip=true`, but no sustained unavailability or explicit target-resource failure.
- Classified `openkm__document-management-system-F-OPENKM-003` as `not_reproduced_under_tested_bounds` because the default authenticated frontend converter admitted two concurrent `toPdf` requests and executed `soffice`, yet no timeout, lingering process retention, or service degradation appeared under the bounded concurrency-2 probe.
- Classified `openkm__document-management-system-F-OPENKM-004` as `not_reproduced_under_tested_bounds` because the default authenticated REST `doc2pdf` endpoint accepted two concurrent valid multipart DOCX conversions and returned PDFs without provider rejection or target-resource failure under the bounded concurrency-2 probe.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status 1 and no diagnostics on this output root, so the OpenKM worker preserved all artifacts and updated `validation_status.jsonl` directly after running the required aggregation step.

### Verification

- Pulled and launched the official OpenKM image locally, captured container logs plus runtime `OpenKM.cfg` and `OpenKM.xml`, verified low-privilege frontend and REST authentication, and enumerated seeded root documents for converter probes.
- Executed bounded unique-entry ZIP import probes plus concurrent frontend and REST DOCX-to-PDF conversion probes, and captured timing, HTTP headers, PDF outputs, route responses, and server-side converter evidence under the OpenKM case directories.

## [2026-08-12] Validate Rill Flow dynamic group startup feasibility

### Changed

- Added isolated dynamic-validation artifacts for the `weibocom__rill-flow` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, startup logs, container inspect evidence, per-case plans, blocked preflights, reflections, and terminal result files.
- Bootstrapped the documented official compose quickstart twice in a local isolated environment. The first attempt failed on a host `8080` port collision, so a case-local compose copy remapped only the host ports while preserving the documented images and environment variables.
- Applied one targeted dependency-side mechanical repair by mounting a readable case-local copy of `setup.sql` after the checked-in MySQL bind mount failed with `Permission denied` during initialization.
- Conservatively classified `weibocom__rill-flow-F-001`, `weibocom__rill-flow-F-002`, and `weibocom__rill-flow-F-003` as `environment_blocked` because the official `weibocom/rill-flow:latest` backend image never reached readiness: Tomcat/Spring Boot startup aborted in OpenTelemetry/Micrometer system-metrics initialization with a cgroup-related `NullPointerException`, so no route-level semantic preflight could begin.

### Verification

- Pulled and launched the documented compose images locally, captured compose/container state, backend startup logs, MySQL startup logs, and container inspect output under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default/`.
- Verified that the dependency-side SQL readability issue could be repaired in isolation, but the backend startup crash remained and prevented any successful HTTP probe to `/flow/trigger/add_trigger.json` or `/flow/submit.json`.

## [2026-08-12] Validate Concord dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `walmartlabs__concord` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including compose-based environment inventory, feasibility, readiness, snapshot, changes, bootstrap records, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official Concord compose quickstart in an isolated local environment with a deterministic admin token only for reproducible first-start authorization, then created one ordinary local user and API key to exercise the queued authenticated routes without changing target business code.
- Classified `walmartlabs__concord-fnd1`, `walmartlabs__concord-fnd2`, and `walmartlabs__concord-fnd3` as `not_reproduced_under_tested_bounds` after bounded default-route probes observed successful request handling but no attributable resource failure or meaningful degradation under the safe attachment/log payloads.
- Classified `walmartlabs__concord-fnd4` as `probe_semantics_failed` because the multipart form route was reached but the crafted JSON field payload failed the form schema before becoming a semantically valid stress case.
- Classified `walmartlabs__concord-fnd5` as `probe_semantics_failed` after a two-step WebSocket preflight: the first attempt exposed required Concord agent headers, and the corrected second attempt proved deserializer reachability but failed on a missing `messageType` semantic requirement instead of a size-bound or resource effect.
- Recorded that the central `aggregate_dynamic_validation.py` script currently exits with status 1 on this shared output root without emitting diagnostics, so the Concord worker preserved all case/environment artifacts and updated `validation_status.jsonl` directly for manual or controller-side re-aggregation.

### Verification

- Launched the official `docker-images/compose/docker-compose.yml` stack locally, captured compose/server logs, verified authenticated access with the isolated admin token, created an ordinary API key, and started reusable test processes plus a v2 log segment for route-specific probes.
- Executed bounded probes for attachment ZIP upload, v1 log append, v2 log-segment append, multipart form submission, and WebSocket upgrade/message handling; captured route responses and server-side error evidence under the Concord case directories.

## [2026-08-12] Validate Stirling PDF dynamic group startup feasibility

### Changed

- Added isolated dynamic-validation artifacts for `stirling-tools__stirling-pdf` under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, changes, crafted PDF probe input, preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `docker.stirlingpdf.com/stirlingtools/stirling-pdf:latest` image in documented login-disabled Docker mode and attempted one targeted mechanical repair by increasing startup memory headroom.
- Conservatively classified `stirling-tools__stirling-pdf-F-vulnerable-decompression` as `environment_blocked` because the official image terminated during startup with `OutOfMemoryError: Metaspace` before any readiness or route-level semantic validation could occur.

### Verification

- Pulled and launched the official latest image locally with isolated port remapping and case-local config/log volumes; captured startup logs, container inspect state, and failed readiness evidence for both bootstrap attempts.
- Generated a bounded valid `FlateDecode` PDF probe artifact and recorded that the prepared single-request probe only encountered connection refusal because the service never became healthy.

## [2026-08-12] Validate Hackpad dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `dropbox__hackpad` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including default Docker environment inventory/feasibility/readiness snapshots and per-case plans, preflights, observations, evidence, reflections, and terminal results.
- Confirmed that the documented default Hackpad Docker deployment boots successfully under isolation, but the modeled anonymous comet transport is not default-reachable in this setup: `/comet` returns `404` and `/newcomet` redirects to sign-in, so `dropbox__hackpad-F-HACKPAD-COMET` was conservatively classified as `default_not_reachable`.
- Added a case-local component harness for `ExpiringMapping` to validate the Hackpad session sink semantics, showing one retained entry per novel ES2-like identifier plus lazy expiry on subsequent mutation; because this stayed mechanism-level and non-destructive, `dropbox__hackpad-F-HACKPAD-SESSION` remains `observed_growth_not_confirmed` rather than a confirmed target failure.

### Verification

- Built the official Hackpad Dockerfile, launched the documented volume-mounted quickstart locally, verified HTTP root reachability with the application's expected `Host` header, and captured route-specific evidence for `/comet` and `/newcomet`.
- Compiled and ran a local JDK 21 harness against the repository's `infrastructure/net.appjet.common/util/ExpiringMapping.java` to record retained-cardinality and lazy-expiry evidence for the session case.

## [2026-08-10] Bind batch plans to exact CodeQL databases

### Changed

- New batch plans now bind each target's validated CodeQL database fingerprint into the immutable plan digest and per-target binding while retaining load compatibility for historical plans that predate this field.
- Batch execution revalidates fingerprint-bound databases and their exact source-root correspondence before creating the target pipeline, so a database replaced after plan publication fails closed before CodeQL or a remote provider is invoked.
- The PoC-29 evaluator now reflects the repaired 18/18 default databases and can request a strict full plan that pins `deepseek-v4-pro`, temperature `0`, the DeepSeek base URL, 60-second timeout, three retries, explicit plan-time remote intent, and `pilot_skipped=true`. It refuses to publish the plan unless all 18 targets are provider-eligible and queued.
- PoC-29 corpus conversion now carries the validated CodeQL database fingerprint rather than the database-marker digest into batch targets.
- Strict PoC source overrides can bind a tree-attested analysis source/database pair to a separate clean public Git checkout only when the checkout HEAD, origin, clean state, full commit, canonical GitHub URL, and excluded-path tree digest all match. The provider checkout and commit are included in the immutable target capability while database validation remains bound to the canonical analysis source.

### Verification

- Added plan serialization/legacy compatibility coverage and runner checks for successful database revalidation, database fingerprint drift, and database source-root drift.
- Resolved the eight PoC tree-attested targets to exact public commits and clean independent Git checkouts: Druid `c2d15dfc55d965e63b55dd11d698ca10ced99b4e`, HertzBeat `87062df97d01d14ea857b76936e97f4385cf609e`, SkyWalking `bb16533009a597dbb41ab6f013ac300509abbb3e`, Solr `c54251ea1614a6635410083839011cf20bfe189b`, Dependency-Track `f4bffa0aee1980387e1c40d7f01f13622a4c7720`, Zipkin `878ce2a1fad54ca941d17fdcf2e1d924b148eb1f`, Presto `913a64110299a3ae0f6314af1558255c1488fec8`, and ThingsBoard `e70298792acaa41b986ed8662fb2a760c35ee5e6`. Each checkout passes exact HEAD/origin/clean-worktree/Git-object validation; the override manifest separately binds the canonical analysis tree SHA-256 and default native database fingerprint.
- Published the nonexecuting immutable 29-case/18-target full plan at `results/java_web_dos_batch/poc29-full-plan-20260810/`. All 18 targets are queued, all 18 database fingerprints are bound, the provider is fixed to `deepseek-v4-pro` with temperature `0`, timeout `60`, retries `3`, and `pilot_skipped=true`; plan digest is `35fcae172671ea29b6ceacfeb0a99613ac2b3a3a08d7da3d1b5eaedf4c08d8a4`.
- The first authorized full execution of that published PoC-29 plan completed with `completed_with_failures` and produced no aggregate summary or static findings. All 18 targets failed: the 8 provider-override repositories hit `CODEQL_DATABASE_INVALID` because `dosweb/production.py` still requires the validated CodeQL database source root to equal the configured provider checkout even when the plan intentionally separates canonical analysis source from provider provenance, 9 targets hit `ANALYSIS_GROWTH_ENTRY_AMBIGUOUS`, and `tianshiyeben/wgcloud` hit `CONFIG_PUBLIC_SOURCE_UNVERIFIED`. The preserved state under `results/java_web_dos_batch/poc29-full-plan-20260810/` is the handoff baseline for the next tool-development session.

## [2026-08-04] Prepare strict native repair for Java Web 205

### Added

- Added a Java Web 205 native CodeQL database repair path with a frozen 55-target scope, Maven/Gradle-only discovery, safe nested build roots, multi-JDK attempts, strict source/database fingerprint validation, resumable attestations, and quarantine-based atomic promotion into the default `databases/applications/` paths.
- The repair path explicitly rejects CodeQL autobuild, `build-mode=none`, bounded javac, compilation-failure suppression, tests, application launch, deployment, Docker tasks, cloning, symlinked targets, and shell-composed commands.
- Added reviewed build-root overrides for the ten archived repositories whose Maven/Gradle roots are nested below the canonical source directory.

### Verification

- A non-network preflight fixed the exact current scope at 55 `JAVA_DATABASE_REQUIRED` targets and discovered 44 Maven and 11 Gradle native build specifications with no unresolved build roots. No database was modified during preflight.
- Native repair unit tests, Python compilation, and diff validation passed. The first authorized Sentinel attempt exposed a stale active loopback proxy in the workstation Maven settings; a subsequent attempt exposed a corrupt artifact in the shared Maven cache. Native Maven captures now use a repository-owned empty settings file, a run-local Maven repository, and sanitized Java/Maven/Gradle option variables so they do not inherit workstation mirrors, credentials, proxy state, injected build arguments, or corrupt shared-cache entries. No database was promoted by either failed attempt.
- Resume now verifies attestation digests and binds the current source, database, build command/root, and JDK set; malformed attestation lines are isolated. Promotion failures are recorded per target, quarantine paths are attempt-specific, and a single target exception no longer aborts the remaining repair scope. A completed CodeQL candidate rejected solely for source-fingerprint drift is now preserved under an attempt-specific `.source-drift` recovery path instead of being deleted, allowing generated-file quarantine, exact fingerprint restoration, strict revalidation, and guarded forensic promotion without rerunning a multi-hour native capture.
- The first repaired default database, `alibaba/sentinel`, completed a 94-module native Maven capture under CodeQL with source fingerprint unchanged, passed strict validation and `codeql resolve database`, and was atomically promoted while the prior invalid directory was retained under the run-specific quarantine path.
- The first five-target tranche exposed two invocation defects now corrected: CodeQL requires an explicit `--working-dir` for nested build roots, and Maven wrappers do not reliably honor `MAVEN_ARGS`, so controlled settings and the run-local repository are now injected directly into the native Maven command. The corrected retry natively repaired `lenve/vhr` and `undera/perfmon-agent`; both promoted databases pass strict resolution. Remaining project-specific failures are retained fail-closed: `ikismail/shoppingcart` has an uncompilable/missing `GetMapping` import, `merikbest/ecommerce-spring-reactjs` uses a Lombok processor incompatible with the installed JDK 17+, and `stevensouza/automon` references an internal `2.0.0-SNAPSHOT` artifact while its reactor builds `2.0.1-SNAPSHOT`.
- The second five-target tranche natively repaired and promoted `erudika/para`. Its other four targets remain fail-closed for checkout/build constraints: Quarkus extension dependency injection failure in `athou/commafeed`, old Lombok plus missing Java 8 system artifacts in `kalvingit/kvf-admin`, an absent internal `yuzi-generator-maker:1.0` artifact in `liyupi/yuzi-generator`, and a wrong local parent binding in `wxiaoqi/spring-cloud-platform`.
- The third five-target tranche produced no valid database. Failures were old Lombok on JDK 17+ (`dengsinkiang/sk-admin`), a late reactor compilation failure after most modules succeeded (`dromara/warm-flow`), a missing local parent (`exrick/xboot`), a timed-out direct GitHub asset download (`nitorcreations/nflow`), and a CodeQL Kotlin extractor ceiling because the project uses Kotlin 2.3.20 while the installed CodeQL supports versions below 2.2.30 (`suwayomi/suwayomi-server`).
- The fourth five-target tranche also produced no valid database. Blockers were an Apache RAT property mismatch (`apache/guacamole-client`, retried with the project-specific RAT ignore property), a missing private/non-Central parent (`dromara/lamp-cloud`), a required Java 24 release with only JDK 17/21/22 installed (`jamebal/jmal-cloud-server`), a missing frontend build output required by an Ant move step (`runify-dev/runify`), and an annotation processor incompatible with the installed javac (`zmops/zeus-iot`). The Guacamole retry passed the RAT gate but then failed on an absent reactor-produced `guacamole-common-js:zip:1.6.1`; it also generated non-excluded Node launcher files in the source tree, so the source-fingerprint drift gate correctly rejected the attempt before validation or promotion. Those generated files were preserved in the run artifact quarantine, and the canonical source fingerprint was restored.
- The fifth five-target tranche natively repaired and promoted `grimmory-tools/grimmory`, `jeecgboot/jeecgboot`, and `kerwincui/fastbee`; FastBee succeeded on the JDK 17 fallback after JDK 22/21 failures. `openremote/openremote` remains blocked by a required but unavailable Yarn task, and `tess1o/geopulse` requires Java release 25 while the host provides JDK 17/21/22.
- The sixth five-target tranche natively repaired and promoted `stirling-tools/stirling-pdf`. Its failures were Java release 25 without JDK 25 (`apache/hertzbeat`), a required JDK 11 Gradle toolchain (`hivemq/hivemq-community-edition`), a CodeQL Kotlin ceiling for Kotlin 2.4.0 (`micrometer-metrics/micrometer`), and Gradle 8.1.1 incompatibility with Java 22 bytecode during settings-script analysis (`sanluan/publiccms`).
- The seventh tranche initially reported five failures, but forensic recovery showed that `jenkinsci/jenkins` had completed its full native Maven reactor and CodeQL finalization before generated Node/Yarn/frontend files triggered the tree-fingerprint gate. Those generated files were preserved in the run artifact quarantine, the exact preflight fingerprint was restored, and the completed candidate passed repeated strict validation before guarded promotion and a recovery attestation. The other blockers were Java release 25 (`dependencytrack/dependency-track`), a Gradle task dependency validation error after compilation (`kestra-io/kestra`), a project plugin type-resolution failure (`modelengine-group/app-platform`), and an old Scala Maven plugin failing to load `javax.tools.ToolProvider` (`scouter-project/scouter`).
- The eighth five-target tranche natively repaired and promoted `kiegroup/jbpm` and `mqttsnet/thinglinks`, each after roughly 12–13 minutes of Maven/CodeQL capture. The failures were an unavoidable frontend `pnpm install` execution (`metersphere/metersphere`), a Liquibase goal requiring a live local PostgreSQL service (`walmartlabs/concord`), and missing generated protocol `Command` classes (`apache/skywalking`).
- The ninth five-target tranche produced no valid database. Blockers were a required Java 25 release (`apache/syncope`), an incomplete Maven wrapper checkout (`apache/incubator-kie-kogito-runtimes`), a missing `server-ee` reactor module (`theonedev/onedev`), an absent local `skyeye-parent:1.0-SNAPSHOT` parent (`dromara/skyeye`), and the CodeQL Kotlin extractor ceiling for Kotlin 2.3.20 (`apache/solr`). Solr's generated `.kotlin` diagnostics were preserved in the run artifact quarantine and the exact preflight source fingerprint was restored; no ninth-tranche default database was promoted.
- A targeted native retry avoided Solr's unrelated Kotlin UI module by capturing `:solr:server:assemble`; the Java server build completed under CodeQL, retained the exact source fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `2541f63b47573bbcd6170146c5beb896929052fab4d202fac9195a58939800f0`. Switching Kogito from its incomplete wrapper to system Maven exposed the underlying checkout blocker: its root requires the absent `org.kie:drools-build-parent:999-SNAPSHOT`, so it remains fail-closed.
- The tenth tranche natively repaired and promoted `apereo/cas` after a roughly 32-minute Gradle/CodeQL capture; its database fingerprint is `e23ed318723a249aab86ba4d9a95c4362de83da954ecc53e6c998c2c5e10ce81`, and strict validation plus `codeql resolve database` passed. `dotcms/core` compile was initially blocked by absent reactor ZIP artifacts; a native `package` retry produced those artifacts but then failed in its `process-annotations` compiler execution. `entropy-cloud/nop-entropy` compile lacked a reactor tests JAR and is being retried with test compilation enabled. `geoserver/geoserver` reached a real source/dependency API mismatch in `gs-gwc`; its generated Spotless index files were preserved in the run artifact quarantine and the exact preflight source fingerprint was restored. These three targets remain fail-closed unless their targeted native retries complete successfully.
- To address targets blocked solely by unavailable Java toolchains, JDK 8, 11, and 25 were installed locally under `/usr/lib/jvm/` and verified with `java -version`. The strict native builder now includes these system toolchains in its per-target fallback sequence while retaining per-attempt JDK attestation and source/database validation; previously staged repository-local archives are not executed by the builder. The first legacy tranche natively repaired and promoted `dengsinkiang/sk-admin`, `kalvingit/kvf-admin`, `merikbest/ecommerce-spring-reactjs`, and `scouter-project/scouter` under JDK 8; all four pass strict validation and `codeql resolve database`. HiveMQ's current Gradle wrapper itself requires JDK 17 despite requesting a JDK 11 compilation toolchain; the JDK 17 Gradle-runtime retry succeeded natively, retained its exact Git commit fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `21e13ba3275709689375bd3349cfd61121961efccef6ad1998dcd712fe15165b`. `zmops/zeus-iot` remains blocked by missing `JettyJsonHandler` symbols rather than its Java runtime.
- `entropy-cloud/nop-entropy` was natively repaired by retaining test compilation while skipping test execution, allowing the reactor tests JAR to be produced. Its 27-minute Maven/CodeQL capture retained the exact Git commit fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `7245a483cd57e9a44786d0b771c1d8d3e47fd90622145f5266e53f2aaad997fa`.
- Druid's corresponding native package capture completed successfully under CodeQL but generated 54 fingerprint-relevant distribution/frontend files. Those exact paths were digest-manifested and moved to run-specific generated-source quarantine, restoring the original source fingerprint. A later capture accidentally attested the generated-source state because it began before the generated files were removed; that database was quarantined as noncanonical. The final system-JDK-only recapture preserved its completed candidate on source drift, the same 54 exact files were quarantined, the original fingerprint `86263208a9038f00928b837c2df8fa7e4b18125ff6d411cd8212a87bb0c841c9` was restored, and the candidate passed repeated strict validation before guarded promotion. The canonical Druid database fingerprint is `f65bffa3fbfe9ba3ba967ee10b63a9328d7c7e9eb2e05cfc39c139a856d61d4c`; `codeql resolve database` also passed.
- The eleventh tranche produced no valid database. `thingsboard/thingsboard` requires Java release 25; `sonarsource/sonarqube` reached the unrelated distribution JRE download task; `apache/druid` compile could not resolve its reactor-produced `druid-processing` tests JAR; `keycloak/keycloak` compile did not generate its reactor Maven plugin descriptor; and `prestodb/presto` compile lacked a reactor tests JAR while an unrelated UI module attempted a timed-out Yarn download. A targeted SonarQube retry using the native aggregate `classes` task with build cache disabled succeeded under CodeQL, retained the exact source fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `09f781aadca5f82386845a7e9b61ce953df749d9502b9945393e7e8f1d8b6481`. Druid and Keycloak were retried with the native `package` lifecycle; both exposed missing reactor tests JARs because `maven.test.skip=true` suppressed test compilation, so follow-up retries retain test compilation while still skipping test execution. Presto's generated OpenAPI specification was preserved in the run artifact quarantine and the exact preflight source fingerprint was restored. Its targeted core-package retries excluded the UI from the selected reactor but still activated the UI frontend build through dependencies; all JDK attempts failed on Yarn download timeouts, with the first also encountering a truncated Central download, so Presto remains fail-closed. All retries retain the same strict source-fingerprint and promotion gates.
- The system-JDK-25 tranche natively repaired and promoted `apache/hertzbeat`, `apache/syncope`, `dependencytrack/dependency-track`, `jamebal/jmal-cloud-server`, and `tess1o/geopulse`; each build exited zero under CodeQL, retained its exact source fingerprint, and produced a strict native attestation. `thingsboard/thingsboard` entered its native Maven build and generated fingerprint-relevant Angular compiler-cache output, but the build ultimately failed because `maven-dependency-plugin:unpack (extract-web-ui)` could not find the expected packaged web-UI artifact. CodeQL therefore did not finalize a usable database; the drift gate retained only the failed skeleton candidate under an attempt-specific `.source-drift` path and withheld promotion. Because this archived source is not an independent Git checkout, recovery quarantined only the three files whose timestamps fell inside the failed build interval, recorded their sizes and SHA-256 digests, and reproduced the exact pre-build tree fingerprint `bf92109a4da088ac1d2fcfaf78fe5d3a3ba76badb6164e00fc0cc5d48a469672`; no broad `target`, Node, or source-tree deletion was performed. The tranche therefore completed with five successes and one fail-closed build failure.
- A Kestra retry excluding the known Gradle 9 `sourcesJar` validation failure completed the native `assemble` task, but all Java compilation tasks were `UP-TO-DATE`; CodeQL correctly rejected the database because no compilation was captured. The authorized follow-up forced `--rerun-tasks --no-build-cache`, completed the native Gradle build under JDK 25, retained its exact Git fingerprint, and promoted a strict database with fingerprint `34d4303bfa8835966f3e0a90b9b68e25afe73ad88d3c4c4e539738ee62adcdb1`. Runify's first JDK 25 retry cleared the previous compiler-release blocker but exposed its backend Antrun move of an absent skipped `frontend/dist`; the authorized follow-up selected only `backend` and used the plugin-supported `maven.antrun.skip` property, retaining native backend javac capture without building the frontend. It passed strict validation and promoted database fingerprint `cc91de8ecdef4bc63bf3d2cea39a2ec56d54a7b56e22514120250ab05e28ab07`. Both databases also pass `codeql resolve database`.
- Guacamole's targeted `guacamole-common-js,guacamole` Maven reactor generated the required JavaScript ZIP before compiling the Java WAR and exited zero under CodeQL. The build produced 510 fingerprint-relevant Node/frontend distribution files; each was size/SHA-256 manifested and moved to run-specific generated-source quarantine, restoring the exact pre-build tree fingerprint `169232ebca426df1cdf6073439673251733959dfd16542443f1131b4d24f3710`. The preserved candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion. Its canonical database fingerprint is `39f09db71c8032ee0531eb7385c62178423b926cdfe5a0e7cc86e68c5889799c`.
- ThingsBoard's targeted `msa/web-ui,application` Maven reactor initially failed because `maven.test.skip=true` suppressed the reactor-produced `dao` tests JAR. Retaining test compilation while skipping test execution allowed the 20-minute JDK 25 Maven/CodeQL build to complete successfully, including real `application` Java compilation. The three generated Angular compiler-cache files were size/SHA-256 manifested and quarantined, restoring exact source fingerprint `bf92109a4da088ac1d2fcfaf78fe5d3a3ba76badb6164e00fc0cc5d48a469672`. The preserved candidate passed repeated strict validation and `codeql resolve database` before guarded promotion with canonical database fingerprint `94e071350840d32bdf161d364273a59378fe752ea8a02ce77b773d8664d3caa6`.
- PublicCMS succeeded through its complete JDK 17 Maven reactor rather than the previously attempted Gradle or isolated OAuth entry. The native package capture retained its exact Git fingerprint and promoted strict database fingerprint `da7e7e0172a194cb489b157d7b2fb83fff593f4bc41dd7f766b744d42f848a57`.
- GeoServer avoided the incompatible GWC module by selecting the `main`, `security`, `ows`, `rest`, and `restconfig` Maven reactor under `src`. The native JDK 17 build and CodeQL finalization exited zero. Seven generated `.spotless-index` files were size/SHA-256 manifested and quarantined, restoring exact tree fingerprint `2abc7df0a2bc5751ab80f608d74dd7a78311c43e4b349a4b1cf4464e66d727fa`; the candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion with database fingerprint `0a992f4fd75bb9e7dca9c718cc6ee069251a74f3983310b4d5fd5717f47064a2`.
+- App Platform avoided the failing `tool-maven-plugin:build-tool` execution by selecting the substantial `waterflow-service` Java module and its native reactor dependencies. The JDK 17 `clean compile` capture exited zero, retained exact Git commit `dd242b21cb136c871b1658b9594616a29a2f8246`, passed strict validation and `codeql resolve database`, and atomically replaced the invalid default database while preserving it in run-specific quarantine. The promoted database fingerprint is `cf3f0312d97763e55611dc4bcec922b8dc1ff3baefa0b73ce3789a369fbac11b`.
+- Concord avoided incremental no-source capture by selecting the production `server/plugins/webapp` and `server/impl` reactor union, running `clean compile`, and disabling Maven incremental compilation. The JDK 17 Maven/CodeQL build exited zero, retained exact Git commit `9caa877161aff11501bc01c9a2ea51d99f7e1d80`, passed strict validation and `codeql resolve database`, and atomically replaced the invalid default database with fingerprint `65ed6b413e4f2786a58ccd78c4a79ea287a6a43e83547232ef9f30e815266ac9`; the prior directory remains in run-specific quarantine.
+- MeterSphere's targeted `backend/app` JDK 21 reactor used the project-specific `skipAntRunForJenkins` property, compiled the production backend modules, exited zero, and completed CodeQL finalization. Forensic comparison against the preserved local source archive identified nine generated flattened POMs responsible for the remaining drift; each was SHA-256 manifested and moved to run-specific generated-source quarantine, restoring frozen source fingerprint `c41596653a795eed0d274a371b0b1bf93edecd7e1aa0c15b269456ac90d7e55f`. The preserved candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion with database fingerprint `e7c072c7fa8d53d1056b649b6f8061afa89b564a67544d7d9a1cbdd17fa7dced`.
+- Micrometer's Kotlin-bearing core remains beyond the installed extractor's Kotlin ceiling, so the strict native capture selected the production `micrometer-commons` module, which contains Java sources and does not require a Kotlin compilation task. A forced no-cache JDK 17 Gradle `compileJava` run exited zero, retained exact Git commit `24b886850814780f5f7bcdeb7d35cf25bc8ccd8a`, passed strict validation and `codeql resolve database`, and replaced the invalid default database with fingerprint `575df0ea46062711ae03f3d8cee30ec78f1461ac304c86d370a45b62ffa4d5bc`; no Kotlin task was excluded from the selected module's native task graph.
+- Yuzi Generator's checked-in backend Maven wrapper was incomplete and its web backend required an uninstalled maker artifact, so the strict capture selected the repository's real `yuzi-generator-maker` Maven project using system Maven. Its JDK 17 `clean compile` exited zero, retained exact Git commit `a2a0edb2cbbb6a869196b6b8a85e6ad30bbb635c`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `8b34ad27602685fe7990229b3934aebe6cb4d9307b2c424215db16c149482696`.
+- Automon's aggregate build previously failed when a sample module attempted to resolve the reactor's snapshot core artifact externally. Selecting the production `automon` module directly allowed a JDK 17 native `clean compile` capture to exit zero while retaining exact Git commit `815e9d0ea1360d8a93e6f241ada1f76c4fb9dfb6`. The database passed strict validation and `codeql resolve database` and was promoted with fingerprint `e085a453df4444c3de9cc5fef651c74c45106f980cf5c0a0e777a56066031234`.
+- Zeus IoT's aggregate `iot-server` path reached a real source/dependency API defect in `server-core`, so the strict native capture selected the concrete production `server-client` JAR and its Maven reactor dependencies rather than the POM-only aggregator. The JDK 17 `clean compile` capture exited zero, retained exact Git commit `b314c05a497dc0901cb658f8704e2efa62953cb4`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `e7ec38cdc0eafe3982580a02620bd7046d9760fb1f35efe9aabbbc3769533a91`.
+- Warm Flow's first narrowed selection was still a POM-only aggregator and correctly produced no CodeQL source capture. Selecting the concrete `warm-flow-easy-query-core` production JAR and its reactor dependencies executed a JDK 17 Maven `clean compile`, retained exact Git commit `5d04c41835302b9a3ec4e01d04a8481339497efd`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `31561b9e1fcbc6d7b5a6c976dbb12035d204f643bdfb69e24566a457ba88e559`.
+- dotCMS required JDK 25 and reactor-produced package artifacts rather than the earlier JDK 17 compile attempt. A targeted `dotCMS -am package` build ran for roughly 24 minutes under CodeQL, exited zero, retained exact Git commit `48102262b97e9fc510562f0eaeb5f83b54370a28`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `69b74184671393d4ce01dab091dec679b77ba036e7bc7f099646d65c373ccb5d`.
+- CommaFeed's empty client module did not create the directory expected by the server's Quarkus generate-code phase. After staging that native reactor precondition under the build-excluded `target` tree, the JDK 25 `commafeed-server -am compile` capture executed the production server compilation, exited zero, retained exact Git commit `77b3c609f33564398b099a652e0aa3fcdc43c3a4`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `6f568f1ecc91e995136cdc6e508c7fc217cb4aafa347bbd7bc8a5185a02e3e38`.
+- OneDev's root reactor was incomplete because the declared `server-ee` module was absent, but its existing production `server-core` project was independently buildable. A roughly 21-minute JDK 17 Maven `clean compile` capture exited zero, retained exact Git commit `5beff944c99e514f327eafa7d35bb65725449cf0`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `f0e22defe290eb072abe6663cea0f71a3b81fb7700c3fe91fa3c6fc1099984a7`.
+- Keycloak's archived source contained a generated pnpm symlink unsupported by canonical tree fingerprinting. The link was moved to run-specific source quarantine, yielding stable source fingerprint `6e8970b3568e538f57753178a773698285eaaff0c03723a70e91cc3b65a99013`. A clean JDK 17 native build of the `theme-verifier` Maven plugin then compiled production and test-support Java while skipping test execution, exited zero, and finalized a strict database. The candidate passed repeated validation and `codeql resolve database` before guarded promotion with database fingerprint `57ba15d240a141c26cdbcdd999b5a70acf0f2d1e8a187af8e4d365a0e1da89f8`.
+- Presto's `presto-server` Provisio assembly requires 44 reactor-produced plugin ZIPs that Maven dependency closure alone does not schedule. The final JDK 17 native package capture selected all 44 modules extracted from `presto-server/src/main/provisio/presto.xml`, plus `presto-flight-shim`, `presto-main`, and `presto-server`. The roughly 15-minute Maven/CodeQL build exited zero, retained exact source fingerprint `85510e107d6906bf3dc6f2303cfdbe507e3094720928389cf2119fb757935558`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `65e73b7598f3b40fd7c8dc9e5c2cc54e39e55971716e53224b98a56f652b596b`.
+- XBoot's modular reactor could not resolve the deliberately repository-only `xboot-admin` parent, while the same repository's standalone production `xboot-fast` application contains 162 Java sources and is independently native-buildable. Its JDK 8 Maven `clean compile` exited zero under CodeQL, retained exact Git commit `5277af0ea7db3cf085f8ef3be21329df5bb12cd9`, passed repeated strict validation, and atomically promoted database fingerprint `2e37267443decff808b7527867259c8bd2135346d74e49afae997c71bf5496f0`; the prior invalid database remains in run-specific quarantine.
+- Native repair overrides now support an ordered `setup_commands` list for repository-native Maven/Gradle/Ant prerequisite lifecycles. Setup commands use the same selected JDK, sanitized environment, build root, controlled Maven settings, and run-local Maven repository as the CodeQL-captured command; they remain outside capture, fail closed before capture, are source-fingerprint gated, and are bound into resumable attestations.
+- Spring Cloud Platform avoided the broken `ace-nlp` child model by staging only the root parent, `ace-dev-base`, `ace-common`, `ace-auth-sdk`, and `ace-api` into one isolated Maven repository before capturing the concrete `ace-gate` production module. All five JDK 8 setup lifecycles and the final native `clean compile` exited zero, retained source fingerprint `0039e468f6df61cf9f397edd8ec7aacd7cddd6c634da2a79c846047fb82cf49b`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `b182361c89d81da54f0726b1be0abb616743d9af9f6bc70043892d0668047bea`.
+- SkyEye's primary Maven hierarchy was blocked by the unavailable `skyeye-parent:1.0-SNAPSHOT`, but the repository contains an independent, parent-complete XXL-Job 2.3.0 production reactor. A JDK 8 native `xxl-job-admin -am clean package` capture compiled the 114-source admin/core application, exited zero, retained exact Git commit `217901aeb65b433c5f9d27c64896c2dfde649dc5`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `d7e69cad4284959a7962ea7b2a27f5d3c3ec293df23328979b5ac6a05eed3e8a`.
+- Suwayomi Server required Kotlin 2.4.0, beyond the prior CodeQL 2.23.8 extractor ceiling. The official CodeQL CLI 2.26.0 bundle was integrity-checked, restored with its archived executable modes, and used in isolation without replacing `/opt/codeql`. A forced no-cache JDK 21 Gradle `:server:compileKotlin` run captured the production Kotlin reactor and dependencies, exited zero in roughly four minutes, retained exact Git commit `c8f5d83e9cca295a5a00f792de87354131e40052`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `fc870233011d78784a3a892956447becd58b27349d39e24768762f21778c384f`.
+- Lamp Cloud's unavailable 5.10.0 parent and utility artifacts were reproduced from the exact companion `zuihou/lamp-util` commit `124a9ea320304d7994879f056117f67e108773d0` in an isolated Java 17 Maven reactor and run-local repository. The unchanged canonical Lamp Cloud commit `ee893ed6f43cd2551b5cc8bb48ea70160681f1f7` then completed a native `clean compile` under CodeQL in roughly three minutes, retained its exact source fingerprint, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `321bdd40f18b7844c879e9c51c071621a55d36db117dbf7a59abfc3e26781fea`.
+- Kogito Runtimes' `999-SNAPSHOT` parent and dependency chain was reproduced from exact contemporaneous `apache/incubator-kie-drools` commit `b6fc3f0050bd1e818392bef0597ac488c05ffc19` in an isolated Java 17 Maven reactor. A full Kogito package attempt reached unrelated Quarkus integration-test dependency timeouts after 161 modules, so the strict capture selected the substantial production `jbpm-bpmn2` module and its required native reactor closure. The targeted `clean package` compiled the 115-source BPMN module, exited zero, retained canonical commit `acd78d9249ee75923a0e5e43a332bbc6c1fd0c1b`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `218b67327964bbcdb055ad0f268cc0647aa9417ac7d57c898ea34d7a343e5873`.
+- SkyWalking's GitHub source archive omitted its protocol gitlink content. Exact root commit `bb16533009a597dbb41ab6f013ac300509abbb3e` and protocol commit `07882d57becb37e341f7fc492c11f9f5a5f311cf` were recovered and built in an isolated upstream reactor, including `apm-network`, the `oap-server-bom`, and the internal dependencies required by `server-core`. Three historical generated flattened POMs absent from the original archive were digest-manifested and moved to run-specific source quarantine. The canonical 793-source `server-core` compile then exited zero under CodeQL with flattening disabled, retained source fingerprint `bb3201bdb276009e02cb11ff07b0f661cdae31381a39d065fef369e0bcc5dcbb`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `c6ee05dddd5972e85b55972eefcc45c48530c0ce11071884ba205087ef476b20`.
+- ShoppingCart's former canonical merge commit `4ea0067bf2520ddd9b3332b627e5e01d50b4907b` contains an upstream regression that replaces two valid `RequestMapping` annotations with `GetMapping` without importing the latter, making the sole Maven source set unbuildable. Following an explicit corpus decision, the source was provenance-recorded and repinned to public pre-regression commit `c992c54bde6af51f67d8cfec5cdba6cbcda19f6c`. Its JDK 8 native Maven compile exited zero, retained the new exact Git fingerprint, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `2a4b27ab10c5a54909305a34837eb850b2579a17700db93407799c040df6d04f`.
+- The regenerated canonical Java Web 205 inventory now reports `205/205` strict databases, zero incomplete targets, and `batch_ready: true`, with inventory digest `94cda8008abaa0126eb6dfa65b7fa1c68c153086e26d427a32269bbb99e038db`. The strict corpus loader accepts all targets, and a nonexecuting 205-target batch plan was generated with plan digest `408f9d861f75fcd5560a8a9ea0af8093624a5ec193d79c1efa682c0482d931e4`.

This changelog starts at the v2 cleanup baseline. Older analyzer runs and case-level research history remain available in Git history and preserved result directories rather than in the active project changelog.

## [2026-08-04] Add JAX-RS and gRPC Entry identities

### Added

- Added first-class `jax_rs/http` and `grpc/grpc` Entry identities with strict model, decoder, normalization, artifact-schema, coverage, and benchmark compatibility while preserving the exact 17-column contract.
- Added direct and embedded byte-identical `JaxRsEntries.ql` and `GrpcEntries.ql` queries. JAX-RS recognizes javax/jakarta Path, HTTP verbs, parameter/entity-body inputs, and statically provable ResourceConfig/register, Airlift binder, and Druid-style resource registrations; annotation-only resources remain coverage-only.
- Added conservative gRPC `BindableService` registration for unary/server-streaming-shaped handlers using the real `io.grpc.stub.StreamObserver` API. Request materialization remains `in_handler`; client/bidirectional streaming and descriptor-derived wire identity remain unresolved rather than inferred from response `onNext` calls.
- Added focused registered-positive, unregistered/lookalike-negative fixtures and benchmark identity regressions. gRPC matching now requires exact `grpc` protocol and full case-sensitive route identity; HTTP route-only truth remains valid and case-sensitive, while explicit method conflicts fail closed. Title, handler-name, resource-token, class-name, callback-name, and port guesses are not matching evidence. Multiple handler facts are merged only when they share one complete registration identity; otherwise ambiguity is preserved.
- Corrected JAX-RS route canonicalization, parameter-kind exclusivity, multi-argument registration scanning, and complete/partial overlap. Registered JAX-RS and gRPC handlers no longer also emit unresolved coverage rows.
- Corrected Spring input-kind exclusivity so explicitly annotated parameters and servlet request infrastructure are not simultaneously emitted as model attributes; real-database smoke scans are treated as coverage observations, not dynamic confirmation.

### Verification

- Corrected Spring MVC, JAX-RS, and gRPC queries compiled under the local CodeQL Java pack, and the final opt-in real CodeQL fixture run passed all seven controlled framework fixtures in 191 seconds, including exact JAX-RS routes and registered-versus-unresolved separation.
- Focused Entry, decoder, artifact, production, benchmark, and query-contract validation passed 103 Python tests; direct/embedded query parity, Python compilation, and whitespace validation also passed.
- A fresh local-only PoC-29 Entry batch completed 18/18 targets with the seven isolated database overrides and `max-workers=1`; no remote LLM, application startup, dynamic PoC, attack traffic, clone, or network database rebuild was used. The run produced 1,832 Entry facts (`spring_mvc`: 1,828; `netty`: 4), with Entry diagnostics of 6 `entry_hit`, 1 `entry_ambiguous`, 22 `no_entry_match`, 0 `target_not_run`, and 98 coverage gaps. These are Entry-stage diagnostics only; the entries-only run has 29 expected `artifact_missing` final-static states and does not establish static recall or dynamic confirmation.
- The same run produced no JAX-RS or gRPC facts on the current bounded databases. That result is retained as an explicit coverage limitation: generated/DI registration and descriptor-derived gRPC identities remain unresolved rather than guessed.

## [2026-08-04] Expand existing Java Web Entry extraction coverage

### Changed

- Expanded the existing Spring MVC, Netty, MQTT, Servlet, and filter Entry queries conservatively while retaining the exact 17-column table contract and byte-identical direct/embedded query copies.
- Spring mappings now recognize compile-time route arrays, mapping verbs, servlet request parameters, explicit model attributes, and uniquely typed unannotated command objects while excluding common framework infrastructure parameters.
- Netty recognizes statically registered `channelRead0` callbacks alongside `channelRead`; JMQTT `Object` callbacks remain complete only when a local MQTT-message cast is consumed by a processor, and SMQTT remains a partial dispatch gap.
- Servlet query support includes Jetty-style static holder bindings and verb-bearing servlet routes where the Java binding is unique; dynamic/reflection registrations remain coverage-only.
- Added verb-aware route canonicalization for HTTP Entry identities without changing non-HTTP event routes.

### Verification

- The earlier broad opt-in fixture sweep was not a reliable completion claim because Spring MVC, Servlet, and Netty each reached the 300-second per-test timeout in that run. A later controlled seven-fixture Entry run completed successfully after the JAX-RS/gRPC corrections described above.
- Query compilation, whitespace validation, and direct/embedded parity checks passed for the corrected JAX-RS/gRPC queries; focused Python Entry/benchmark tests passed.
- Descriptor-only `web.xml`, dynamic/reflection/DI registrations, descriptor-derived gRPC identities, client/bidirectional gRPC streaming, and unproven MQTT conversions remain deliberately unresolved.

## [2026-08-03] Migrate the active canonical corpus to Java Web 205

### Changed

- Defined the active corpus as the case-insensitive repository union of the preserved canonical Java Web 200 inventory and the PoC-29 repository set: 200 original targets plus exactly five additions at indices 201 through 205.
- Added a deterministic Java Web 205 inventory generator and tracked manifest while preserving the historical Java Web 200 manifest, repair utility, generated results, and target identity fields at indices 1 through 200 unchanged; readiness fields are deliberately recalculated.
- Switched the canonical corpus loader and batch CLI default to `intel/applications/java_web_205_targets.json`; strict loading now rejects a manifest whose recorded database readiness is incomplete.
- Added active-corpus documentation and regressions for union construction, ordering, case-insensitive deduplication, default paths, and readiness reporting.

### Readiness

- The generator strictly revalidates all 205 default databases and source-root bindings instead of carrying forward historical marker-based readiness. On the current filesystem the tracked manifest records 150 strictly valid default paths, 55 incomplete default paths with an explicit repository/reason list, and `batch_ready: false`; dataset membership remains 205.
- Separately, the seven incomplete PoC-29 databases were rebuilt under `build/poc29-codeql-dbs/` using explicitly risk-marked, PoC-relevant bounded CodeQL extraction after native Maven/Gradle attempts exposed dependency, generated-source, proxy, and JDK 25 blockers. All seven isolated databases pass the production validator and source-root checks, allowing PoC-29 to reach 18/18 readiness through explicit overrides without modifying historical default databases.
- A complete local entries run then finished 18/18 targets with no remote LLM or dynamic execution. Entry extraction produced 7 facts, all from Zipkin; the `/api/v2/spans` truth remains a deterministic three-overload `entry_ambiguous`, while the other 28 truths remain `no_entry_match`. The bounded rebuilds therefore remove `target_not_run` but do not by themselves expand framework Entry coverage.

## [2026-08-03] Expand MQTT broker and Armeria entry extraction

### Added

- Added end-to-end MQTT `broker_registration` entry support without changing the 17-column CodeQL table contract; partial and dynamic rows remain coverage-only and never become entry facts.
- Added high-confidence JMQTT anonymous `ChannelInitializer` broker recognition and conservative SMQTT Reactor Netty coverage gaps where connection-to-protocol dispatch cannot be uniquely bound, plus statically registered Armeria `@Post`/`@Get` annotated services including Zipkin `/api/v2/spans`.
- Added broker/Armeria fixtures, registration/schema regressions, and benchmark matching for MQTT protocol-service descriptions without port-only matches.

### Verification

- A fresh local-only 11-target entries run completed 11/11 targets with remote LLM and dynamic execution disabled. Entry facts increased from 1 to 7; all seven were Zipkin entries, and the PoC `/api/v2/spans` truth produced a deterministic three-overload `entry_ambiguous` result. JMQTT remained a coverage gap on the historical database, and SMQTT remained an explicit `smqtt_protocol_dispatch_binding_unresolved` partial gap rather than a guessed hit.
- Real CodeQL fixtures passed 2 tests; focused Entry/benchmark coverage passed 86 tests; query-pack parity, Python compilation, and diff validation passed.

## [2026-08-03] Diagnose PoC-29 entries-only benchmark runs

### Added

- Renamed the independent benchmark manifest identity to `poc-29` and added strict entries-stage artifact extraction with run/stage binding, digest, byte-count, record-count, and schema validation.
- Added deterministic repository/route/method/protocol entry diagnostics, coverage-gap reporting, and CLI `entry_diagnostics.jsonl` / `entry_summary.json` outputs without treating entry hits as static recall.
- Added runtime validation against the preserved local entries-only archive.

## [2026-08-03] Add PoC-29 benchmark baseline

### Added

- Added network-free PoC-29 truth normalization for 29 cases across 18 repositories, independent source/database asset binding, explicit repository spelling normalization, deterministic P0 candidate snapshots, fail-closed matching states, recall-only evaluation, and a baseline CLI.
- Database validation now uses the strict CodeQL validator: the real baseline exposes 7 incomplete databases and 11/18 ready entries. Truth remains valid at 29/18, while complete batch readiness is false; ready-only plans are explicitly diagnostic and not complete recall runs.
- Added strict repository-relative database overrides and fail-closed complete-plan checks.
- Added synthetic and real-inventory benchmark regression tests.

## [2026-07-28] Add canonical Java Web 200 batch orchestration

### Added

- Added strict canonical-corpus validation, source/database provenance checks, immutable batch plans, target identity bindings, bounded concurrency, atomic batch state, failure isolation, and resumable per-target production execution.
- Added local-only `entries` batches and explicitly authorized `full` batches. Environment provider credentials are stripped from Entry-only workers, while tree-fingerprint targets remain paused when public Git commit attestation is unavailable.
- Added format-separated normative P0 aggregation with target/run/stage binding, artifact hash/count/size validation, structured gap accounting, atomic publication, and exact three-value static-verdict totals while preserving historical hunter aggregation. Aggregation now rejects ambiguous format auto-detection instead of silently treating P0 records as historical.
- Added digest-bound non-secret provider settings to batch plans and a non-executing `full --plan-only` path; full execution still requires explicit remote consent and an environment-only provider key.

### Verification

- Added network-free batch plan, runner, aggregation, resume, authorization, identity, concurrency, stale-artifact recovery, and compatibility regressions; the complete default suite now passes 494 tests with 6 guarded integrations skipped.
- No real DeepSeek request, corpus analysis run, service launch, attack traffic, or dynamic DoS validation was performed.

## [2026-07-28] Complete the production P0 analyzer

### Added

- Connected all six default production executors for Entry extraction, G1–G4 Growth classification, E→G flow proof, lifecycle evaluation, deterministic conclusions, and certificate-consistent reporting.
- Added durable strict round trips for Growth, Flow, Guard, Bound, Release, lifecycle decision, certificate, and finding artifacts, with authoritative resume reconstruction and downstream invalidation.
- Added a complete immutable query-pack snapshot across Entry, Growth, Flow, and Lifecycle query families and a network-free injected full-graph production test.

### Security and correctness

- Preserved pinned-source excerpt validation, explicit remote consent, environment-only API keys, atomic provider-stage publication, conservative partial-coverage handling, and static-only verdict wording.
- Required the selected commit to be reachable from the public repository's default branch, required the CodeQL database source root to match the pinned checkout, and blocked credential assignments in comments and credential-bearing Java mutator/header calls before provider use.
- Made lifecycle decisions durable and schema-validated, rejected forged nested decision summaries/IDs, and ensured any partial sibling flow forces `static_unknown` rather than being discarded from conclusion evidence.

### Verification

- Final default discovery ran 462 tests successfully with 6 guarded integrations skipped.
- All 6 opt-in real-CodeQL Entry, Growth, and Lifecycle fixture tests passed.
- Python compilation, every CLI subcommand help path, and `git diff --check` passed.
- No real DeepSeek request, service launch, attack traffic, or dynamic DoS validation was performed.

## [2026-07-25] Migrate active consumers and document the P0 interface

### Changed

- Migrated active static aggregation and dynamic-scaffold traceability to the exact `static_vulnerable`, `bounded_under_modeled_assumptions`, and `static_unknown` vocabulary, rejecting the retired value and static-verdict field aliases rather than retaining a compatibility path.
- Preserved static/dynamic independence: the dynamic scaffold copies a static verdict only under traceability metadata while retaining `paused`/`blocked` dynamic defaults.
- Reworked README and agent guidance to document Python and CodeQL requirements, mandatory DeepSeek behavior for complete P0 runs, the current fail-closed production executor boundary, stage/resume semantics, normative artifacts, exact verdict meanings, P0 framework/assertion scope, asynchronous Release limitations, coverage gaps, test opt-ins, and static/dynamic separation.
- Added dedicated verdict-migration regressions and physical JSONL source-location checks for rejected values and field aliases, including inputs with blank lines.

### Verification

- Final default discovery ran 416 tests successfully with 6 guarded integrations skipped.
- `codeql pack install codeql` succeeded with CodeQL CLI 2.23.8, and all 6 opt-in Spring MVC, Servlet, Netty, and MQTT entry/Growth/lifecycle fixture tests passed.
- Focused migration tests, Python compilation, CLI help, terminology scan, and `git diff --check` passed.
- Verification made no real DeepSeek request, did not start target services, did not send attack traffic, and did not run dynamic DoS validation.
- At that checkpoint, Task 7 remained partial because the production CodeQL/DeepSeek stage-executor factory was still deliberately unconnected; the 2026-07-28 entry records its completion.
- Per explicit user direction, the obsolete 2026-07-02 baseline design remains deleted as an approved preservation exception; the ignored 2026-07-18 design and plan remain unstaged until commit authorization.

## [2026-07-24] Add static conclusions, certificates, reports, and resumable orchestration

### Added

- Added deterministic Assertion 1 and Assertion 2 evaluation with the exact `static_vulnerable`, `bounded_under_modeled_assumptions`, and `static_unknown` vocabulary. Partial flow, unresolved lifecycle evidence, and relevant coverage gaps remain unknown; provider confidence never changes a verdict.
- Added canonical lifecycle certificates, certificate-derived static findings, deterministic summaries, and static-only Markdown reports with strict finding/certificate/verdict consistency.
- Added generic injected stage execution for `entries -> growth -> flows -> lifecycle -> conclude -> report`, deterministic fingerprints, exact resume reuse, mismatch invalidation, bounded canonical local payloads, strict manifest/artifact recovery validation, output-root locking, symlink refusal, stale-artifact reconciliation, and transactional publication/rollback.
- Added fail-closed CLI subcommand dispatch with controlled `AnalyzerError` and injected-factory failure handling. Production CodeQL/DeepSeek stage executors are not yet connected by the default factory, so direct production commands fail closed rather than claiming analysis success.
- Added network-free P0 scenario coverage for materialization, allocation, persistent-map growth, queues, finite rejection, late Guards, incomplete Release, asynchronous consumers, Netty, and MQTT.

### Verification

- Final default discovery ran 356 tests successfully with 6 guarded integrations skipped.
- Focused assertion, certificate/report, pipeline recovery, artifact, configuration, and P0 end-to-end suites passed; Python compilation, CLI help, and `git diff --check` passed.
- Independent review findings became regressions for scoped coverage, overlapping coverage patterns, forged assertion/verdict/certificate identity, strict lifecycle booleans, active verdict vocabulary, report disagreement, malformed resume metadata, manifest/hash/count tampering, duplicate and symlinked paths, stale artifacts, rollback, factory errors, and bounded payload handling.

## [2026-07-24] Prove entry-to-growth flows and evaluate lifecycle evidence

### Added

- Added normalized E→G `FlowProof` construction with stable identities, strict attacker source/demand mapping, dangling-reference failures, canonical artifact validation, and audited proven/partial verification.
- Added deterministic Guard, Bound, and synchronous Release decisions with structured checks, stable reasons, modeled finite-configuration matching, receiver/dimension/scope joins, and unresolved asynchronous-release retention.
- Added exact-column candidate-only CodeQL queries for direct entry-to-growth flow, Guard, Bound, and synchronous Release evidence, plus Spring, Servlet, Netty, and MQTT lifecycle fixtures.

### Verification

- Final default discovery passed 295 tests with 6 guarded integrations skipped; focused Task 6 tests, Python compilation, and `git diff --check` passed.
- Explicit local CodeQL lifecycle fixture verification passed across all four framework databases, and all four Task 6 queries compiled against the local CodeQL Java pack graph.
- Independent reviews drove regressions and remediation for same-handler false flow proofs, incomplete coverage upgrades, forged flow identities, configuration mismatches, cross-receiver Bounds, Release scope/dimension/key semantics, mixed asynchronous Release evidence, and malformed flow artifacts.

## [2026-07-24] Verify four resource growth classes

### Added

- Added frozen G1–G4 Growth candidate normalization with deterministic resource/growth identifiers, sorted demand/evidence merging, strict raw-row validation, and exact `growth_candidates` artifact serialization.
- Added canonical bounded-slice construction and deterministic Growth Contract verification with audited `verified|rejected|unresolved` results, stable reason codes/checks, strict slice/index evidence identity, and no fabricated static facts.
- Added exact-column CodeQL screening queries for request/message materialization, direct buffer and array allocation, persistent container growth, and field-backed asynchronous work submission.
- Extended Spring, Servlet, Netty, and MQTT fixtures with G1–G4 positives, request-local/lookalike negatives, finite/unbounded queue forms, and guarded real-CodeQL semantic tests.

### Verification

- Final default discovery ran 255 tests successfully with 5 guarded integrations skipped; focused Growth/artifact suites and Python compilation passed.
- Explicit `DOSWEB_RUN_CODEQL_FIXTURES=1` verification passed both Growth query tests across temporary fixture databases; all four Growth queries compiled against the local CodeQL pack graph.
- Independent reviews drove regressions and remediation for fabricated evidence, empty/cross-candidate evidence verification, malformed identifiers, evidence-ID collisions, array-allocation coverage, collection demand roles/scopes, local async receivers, G1 lookalikes, and nested artifact validation.

## [2026-07-24] Extract registered framework entries

### Added

- Added frozen registered-entry, attacker-input, registration, handler, and framework-coverage models with deterministic semantic identifiers, strict framework/protocol pairings, canonical HTTP routes, sorted input deduplication, and bounded analyzer errors.
- Added deterministic entry-row normalization that separates unresolved dynamic registrations from reachable entries, validates both supported and gap rows, and emits explicit coverage records for Spring MVC, Servlet, Netty, and MQTT even when a framework has no extracted rows.
- Added four exact-column CodeQL table queries requiring framework-specific registration/type evidence: Spring controller mappings, Servlet annotation registrations, Netty pipeline registrations, and MQTT subscribe/listener bindings. Recognized unresolved registration patterns emit partial coverage rather than fabricated reachability.
- Added self-contained Java source fixtures with registered handlers, unregistered/lookalike negatives, and dynamic-registration gaps, plus guarded real-CodeQL semantic tests.

### Verification

- Final focused Task 3/4 verification ran 41 tests with 39 passed and 2 guarded CodeQL fixture tests skipped by default; the complete default suite ran 243 tests with 240 passed and 3 guarded integrations skipped.
- Explicit `DOSWEB_RUN_CODEQL_FIXTURES=1` verification passed both real-CodeQL tests across all four temporary Java databases, exact decoded columns, registered-entry expectations, lookalike exclusion, and forcing coverage gaps.
- All four entry queries compiled against the locally installed `codeql/java-all` dependency graph, all Java source fixtures compiled without leaving `.class` artifacts, changed Python files compiled, and `git diff --check` passed. Independent reviews drove remediation for framework lookalikes, protocol mismatches, incomplete coverage validation, sparse coverage records, unresolved registration gaps, and unrelated-reflection coverage poisoning.

## [2026-07-24] Add strict Task 3 CodeQL execution contracts

### Added

- Added bounded CodeQL database validation with strict metadata parsing, stable metadata-file fingerprints, source-root provenance, symlink rejection, and controlled `CODEQL_DATABASE_INVALID` failures.
- Added a two-stage CodeQL query/BQRS runner with minimal secret-free environment inheritance, one shared deadline, bounded diagnostics, descriptor-validated immutable root-query snapshots in the original pack context, database-drift checks, TERM/KILL process-group cleanup, and atomic per-generation publication after validation and BQRS hashing succeed.
- Added fixed ordered `QuerySpec` contracts for entry, growth, flow, Guard, Bound, and synchronous Release candidates, with strict result-set, row, primitive type, enum, path, line, row-count, and string-budget validation.
- Added the minimal `dosweb/p0-java-resource-dos` query pack manifest using the installed CodeQL CLI's modern `dependencies` field, without query suites; individual queries remain deferred to later tasks.
- Added real-CodeQL compatibility remediation for timestamped database metadata, `{name, kind}` decoded column descriptors, strict decoded-result validation before publication, original pack-context query execution with persisted snapshots, and deadline propagation through bounded database and file hashing.

### Verification

- Final focused Task 3 verification passed 25 tests; the full default suite ran 227 tests with 1 guarded online integration skipped. `codeql pack ls codeql` resolved `dosweb/p0-java-resource-dos@0.1.0` under CodeQL CLI 2.23.8.
- Concurrent generation initialization/publication passed 10 repeated rounds; an additional focused stress sequence passed 5 rounds and 90 test executions.
- Changed Python modules/tests compiled and `git diff --check` passed. Independent Task 3 reviews drove regressions for query provenance drift, descendant-held process pipes, SIGTERM-ignoring descendants, and post-publication hashing; all were fixed within the root-query adapter contract.

## [2026-07-22] Complete fourth Task 2 consolidated remediation

### Changed

- Serialized cross-stripe cold cache production behind one fixed private process-shared capacity lock, preserving fixed key stripes, pre-provider capacity failure, immutable entries, and non-destructive no-eviction behavior.
- Replaced single-shot provider/GitHub body reads with incremental bounded reads under recomputed absolute deadlines, and propagated one shared verification budget across GitHub API and local Git operations.
- Added process-local same-key sharing for sanitized deterministic response failures without persistent negative caching; later independent calls may retry normally.
- Replaced plaintext provider request-ID audit persistence with a domain-separated API-keyed HMAC digest and bumped the authenticated cache format.
- Added high-confidence SSN-like PII rejection, complete Java compound-assignment coverage, annotation-aware Java declarator scanning, Java comment/octal/text-block literal reconstruction, component-aware credential identifiers, and bounded UTF-8 prechecks for hostile slice strings.
- Hardened independent-review boundaries: authenticated incompatible cache entries now receive capacity-gated live refresh without overwrite; crash temporaries count toward cache bytes; cache-entry HMACs have an explicit domain; timeout values are upper-bounded; permanent response-read failures do not retry; and complete GitHub slice verification shares one deadline.

### Verification

- Final focused Task 2 verification passed 169 tests; the full default suite ran 202 tests with 1 guarded online integration skipped; concurrency/deadline/publication stress passed 10 rounds and 90 test executions.
- Modified Python modules/tests compiled, parser-only CLI boundaries returned 0/2 as expected, and `git diff --check` passed. Independent review gate results are recorded in the Task 2 implementation report.

## [2026-07-19] Complete third Task 2 consolidated remediation

### Changed

- Hardened provider request-ID credential rejection, unbounded Java assignment scanning, Credential(s) classification, response echo filtering, permanent-network error handling, and one monotonic request deadline.
- Bound aliases and formal evidence to current config/growth identities; made cache fact IDs mandatory and authenticated audit fields fully identity-bound.
- Replaced per-key cache locks with 64 immutable stripes, removed memory growth, closed inherited flock descriptors, imposed non-destructive global capacity limits, and made unsafe/capacity/publication failures fail closed before provider use where required.
- Hardened Git deadlines/config overrides, JSONL mapping/publication/count behavior, strict config keys/Unicode handling, and explicit CLI remote-consent revocation.

### Verification

- Focused Task 2 command passed 146 tests; race/fork/cache/publication stress passed 10 consecutive iterations; full discovery passed 178 tests with 1 guarded online integration skipped.
- Changed Python modules/tests compiled, `git diff --check` passed, and parser-only CLI runtime accepted `--no-remote-llm` while rejecting conflicting consent flags with exit 2.

## [2026-07-18] Fix cold cache hierarchy creation race

### Changed

- Made descriptor-relative private cache hierarchy creation tolerate a concurrent trusted creator winning the `mkdir` race, so every same-key cold process reaches the shared `flock` instead of bypassing single-flight.
- Added a deterministic concurrent hierarchy-creation regression preserving the guarantee that exactly one cold producer publishes and a fresh cache reconstructs the durable contract.

### Verification

- The process single-flight test passed 20 consecutive post-fix iterations; the focused Task 2 suite passed 126 tests; full discovery ran 159 tests with 158 passed and 1 guarded online integration skipped.

## [2026-07-18] Complete second Task 2 consolidated remediation

### Changed

- Replaced regex-only Java credential assignment handling with Unicode-aware lexical scanning that preserves string/comment boundaries and detects sensitive identifiers independently of value syntax.
- Hardened YAML/config loading with bounded descriptor reads, regular-file and symlink refusal, duplicate-key/alias/tag rejection, path normalization, boolean precedence preservation, and strict URL-authority validation.
- Removed unbounded HTTP read fallback, normalized injected transport failures into retry exhaustion, added deadline-aware Git output collection and nonzero-runner rejection, bounded cache publication, and descriptor-relative private cache hierarchy creation for Linux/Python 3.11+.
- Added strict JSONL duplicate-key, structure, record-count, per-record, and aggregate limits; enforced artifact ID syntax/uniqueness and bounded `fact:` evidence IDs; preserved deterministic atomic publication.
- Preserved same-file relationships in provider aliases, exposed one canonical typed response schema, and strengthened fabricated-cache evidence validation with a recomputed valid HMAC.

### Verification

- Task 2 focused command passes 125 tests. Per-module discovery passes 26 artifact, 6 bounded-slice, 9 strict-growth, 21 config/CLI, and 63 DeepSeek tests.
- Full discovery passes 158 tests with 1 explicitly guarded online integration skipped. Changed Python modules/tests compile and `git diff --check` passes.
- Runtime CLI observation confirms the current Task 1/2 boundary remains parser-only: both explicit remote-consent arguments and default parsing exit 0 without analysis or network access.

## [2026-07-18] Harden Java Web DoS skill routing and dynamic validation

### Changed

- Routed bulk inventory, environment setup, probe execution, and fleet screening to `claude-haiku-4-5`; bounded semantic analysis and PoC engineering to `claude-sonnet-5`; and cross-stage reflection and final review to `claude-opus-4-8`, with evidence-coded escalation and model-usage artifacts.
- Made dynamic environment preparation reusable and autonomous within isolation boundaries, with explicit deployment classification and repair evidence required before `environment_blocked`.
- Added semantic preflight and a hard three-round PoC reflection loop that treats growth-only and no-growth observations as hypotheses to diagnose rather than final answers.
- Strengthened the user-level dynamic aggregator to discover missing results, validate status/schema/deployment/round/evidence/termination contracts, and derive verdicts centrally.

### Verification

- Added user-level skill and aggregator contract coverage for model aliases, worker-role separation, semantic preflight, the three-round cap, missing results, verdict conflicts, deployment classification, evidence paths, and split safety termination fields.
- Verified 22 focused dynamic-validation tests, Python compilation, and repository diff whitespace checks.

## [2026-07-18] Consolidate Task 2 independent-review remediation

### Changed

- Made provider response-body read failures retryable, bounded all slice/YAML/Git materialization and process output, reset inherited locks after fork, and safely create private nested cache paths.
- Added deterministic provider-facing aliases with local evidence restoration, exact final-request credential scanning with Java normalization, a complete typed prompt schema, strict formal Growth Contract artifact validation, IPv6-safe URL canonicalization, and stable malformed-URL errors.
- Exposed the Task 2 `--allow-remote-llm` consent/provenance CLI arguments without adding later-stage analyzer orchestration.

### Verification

- Added regression coverage for all verified review findings. The focused suite passes 90 tests; full discovery runs 134 tests with 133 passed and the guarded online integration skipped. Changed Python files compile and `git diff --check` passes.

## [2026-07-18] Authenticate and harden DeepSeek contract cache

### Changed

- Bound Growth Contract cache entries to the in-memory DeepSeek API key with HMAC-SHA256; cache files contain the authenticator but never the key, and unkeyed SHA-256 fields now provide integrity metadata only.
- Made cache use fail closed for unsafe local paths: cache directories must be current-user-owned `0700` directories, and lock, temporary, and entry files must be current-user-owned regular `0600` files. Directory-descriptor relative operations and `O_NOFOLLOW` are used where supported.
- Treat symlinked, permission-unsafe, or foreign-owned cache paths as cache misses with cache publication disabled, while allowing an authorized live classification to proceed. Preserved thread and cross-process single-flight behavior for safe caches.

### Verification

- Added focused cache coverage for HMAC tampering despite recomputed unkeyed hashes, wrong-key misses, owner checks, private modes, and symlinked directory, entry, and lock handling.
- Ran `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_cache_entry_requires_hmac_bound_to_the_api_key tests.test_deepseek_client.DeepSeekClientTests.test_cache_with_a_different_api_key_is_a_miss tests.test_deepseek_client.DeepSeekClientTests.test_cache_files_are_private_and_regular tests.test_deepseek_client.DeepSeekClientTests.test_symlinked_cache_directory_is_not_used tests.test_deepseek_client.DeepSeekClientTests.test_symlinked_cache_entry_is_a_miss_and_is_not_replaced tests.test_deepseek_client.DeepSeekClientTests.test_unsafe_permissions_and_lock_symlink_disable_cache_writes tests.test_deepseek_client.DeepSeekClientTests.test_cache_rejects_foreign_owner_when_lstat_is_mocked -v`, `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_same_key_process_single_flight_publishes_once_durably tests.test_deepseek_client.DeepSeekClientTests.test_same_key_thread_single_flight_makes_one_provider_request -v`, and `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_cache_entry_requires_hmac_bound_to_the_api_key -v` successfully.

## [2026-07-18] Add audited DeepSeek Growth Contract adapter

### Added

- Added an opt-in DeepSeek OpenAI-compatible Growth Contract client with strict schema validation, bounded retry policy, cache identity/integrity checks, atomic successful-response publication, and local mock coverage.
- Added a pre-network remote-source gate requiring explicit authorization, canonical public GitHub repository provenance, a full commit SHA, and a clean matching local checkout; default GitHub verification uses unauthenticated API requests and read-only Git checks, while authorization and provenance are captured only in non-secret request audit metadata.
- Restricted production provider endpoints to canonical `https://api.deepseek.com/`; loopback endpoints are permitted solely for local mocks, and all other endpoints fail before an Authorization header can be constructed.
- Added bounded-slice and Growth Contract models, constrained prompts, redaction of API keys, authorization values, and `sk-...` strings, plus a dual-guarded artificial-fixture integration test.

### Verification

- Verified with `python -m unittest tests.test_deepseek_client -v` and `python -m unittest discover -s tests -v`; default tests use localhost mocks and make no external provider request.

### Security remediation report (Task B: items 4, 5)

- Validated every LLM Growth Contract evidence reference against the static fact IDs in its bounded slice. Fabricated live references fail as `LLM_RESPONSE_SCHEMA_INVALID` before a cache write, while fabricated cached references are treated as cache misses.
- Applied strict byte, UTF-8, duplicate-key/non-finite-value, nesting, node, collection, and string limits consistently to provider-envelope, inner-contract, GitHub, and cache JSON. Reads request at most `limit + 1` bytes and map malformed, incomplete, or oversized data to controlled errors/cache misses.
- Preserved the cache HMAC and filesystem-authentication implementation without modification.

### Verification

- Verified the Task B fact-reference and JSON-boundary regressions with local mock/seam tests only; no live DeepSeek or GitHub endpoint was contacted.

### Security remediation report (Task C: items 3, 6, 7, 8)

- Validated Git object metadata before reading a source blob, rejected non-blobs and blobs over the bounded excerpt limit, and retained exact blob and excerpt hashes.
- Added the finite `MAX_LLM_RETRIES` bound at configuration and client runtime; blank API keys are accepted only while remote LLM access is disabled, while enabled access requires a nonblank environment key. YAML now rejects case and separator variants of `api_key` at every nesting level.
- Routed verifier Git commands through one hardened command form that disables fsmonitor and hooks, disables system/global configuration, replacement objects, and pagers; a local malicious `core.fsmonitor` regression confirms its helper is not executed.
- Ran `git fsck --strict --no-dangling --no-reflogs <full-sha>` through that hardened runner before any local source object access.

### Verification

- Passed focused Task C regressions with `python -m unittest tests.test_config_and_cli.ConfigTests.test_configuration_rejects_api_key_spelling_variants_at_any_depth tests.test_config_and_cli.ConfigTests.test_disabled_remote_llm_allows_a_missing_environment_key tests.test_config_and_cli.ConfigTests.test_enabled_remote_llm_requires_a_nonblank_environment_key tests.test_config_and_cli.ConfigTests.test_max_retries_has_an_explicit_upper_bound_in_cli_and_yaml tests.test_deepseek_client.DeepSeekClientTests.test_empty_api_key_is_rejected_before_verifier_or_network tests.test_deepseek_client.DeepSeekClientTests.test_runtime_config_rejects_max_retries_above_the_explicit_limit tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_hardened_git_invocation_disables_checkout_configured_helpers tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_validate_slice_rejects_oversized_git_blob_without_reading_it tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_verify_runs_strict_fsck_before_any_local_object_read -v`.

## [2026-07-18] Consolidate P0 implementation authority

### Changed

- Declared `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md` the sole implementation standard and updated repository guidance and README links accordingly.
- Hardened artifact recovery validation so a stage requires a non-empty artifact list and every artifact path is a safe relative path within the run output root.
- Completed lifecycle artifact contracts, canonical JSONL ordering, recursive YAML secret rejection, strict blank/UTF-8 JSONL failure handling, and output-root-relative artifact metadata serialization.

### Verification

- Added regression coverage for missing, empty, malformed, absolute, and escaping artifact paths during stage reuse.
- Added focused contract coverage for lifecycle artifact minima, deterministic JSONL bytes, nested YAML secrets, and strict JSONL input failures.

## [2026-07-18] Design the complete P0 analyzer

### Added

- Added the approved full-P0 analyzer design for Spring MVC, Servlet, Netty, and MQTT.
- Defined the Python and CodeQL module boundaries, versioned artifact contracts, bounded-slice DeepSeek Growth Contract, deterministic lifecycle rules, assertions 1 and 2, lifecycle certificates, recovery model, and test strategy.

### Changed

- Chose `bounded_under_modeled_assumptions` to replace the unconditional `static_safe` label during implementation; active tooling and documentation will be migrated together without a legacy compatibility mode.
- Required DeepSeek through an environment-only API key for complete P0 runs while keeping default tests network-free and provider calls auditable.

### Verification

- Reviewed the design for placeholders, internal contradictions, ambiguous verdict behavior, secret handling, and scope boundaries.
- Added P0 package, environment-only configuration, strict JSONL artifact contracts, deterministic identifiers, and resumable-stage primitives.
- Verified with `python -m unittest tests.test_config_and_cli tests.test_artifact_contracts -v` and `python -m unittest discover -s tests -v`.

## [2026-07-17] Prepare the v2 tool-development baseline

### Changed

- Restored the preserved v2 engineering specification and retired the obsolete one-time cleanup plan and Stage 0–5 research design.
- Adopted the lifecycle-centered analysis direction based on bounded slices, Growth Contracts, lifecycle evidence, and effective Guard/Bound/Release reasoning.
- Normalized paper material under `docs/paper/` and repaired active documentation links.
- Kept the existing `poc/` evidence archive unchanged and stopped implicitly admitting new disclosure logs and probes into version control.
- Added a static CodeQL batch-build foundation and a static-only batch aggregator with configuration validation and regression tests.
- Kept dynamic-validation preparation and status synchronization as explicit opt-in helpers, isolated from the ordinary v2 static pipeline.

### Verification

- Python and shell syntax checks.
- Unit tests for manifest/config validation, path handling, dry-run behavior, static aggregation, case identity, overwrite protection, and status synchronization.
- Markdown-link, JSON, gzip, and Git workspace hygiene checks.

## [2026-07-02] Reset the workspace for v2 implementation

### Changed

- Established the v2 static model:
  `Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)`.
- Preserved framework sources, CodeQL databases, PoC evidence, static-hunt results, application results, and Java Web batch results.
- Removed legacy phase-oriented analyzer implementation from the active development context.
