## [2026-09-18] Production resource lifecycle integration

- 修复 formal Flow 对同一程序点、同一精确 attacker demand 的多资源维度 Growth 身份误判为 `FLOW_REFERENCE_AMBIGUOUS`：单条 source-to-sink 证据现在按稳定 Growth ID 分别生成路径，仍拒绝位置不一致、demand 不兼容、canonical Entry 不匹配和重复路径；XXL-JOB 同一 queue insertion 的 retained entries / accepted tasks 双重建模不再中止正式分析。
- 将 RC1 source snapshot declaration coverage insufficiency 改为明确 typed gap：production 仅对该类缺口降级，为相关 async task Growth 路径发布 path-bound unresolved decision 并得到 `static_unknown`；不生成伪造 solver facts/results。归档字节不匹配、数据库身份错配、selected query failure 与 malformed result 仍 fail closed。
- 按用户提供的新 provider 配置将正式 Responses endpoint 迁移到 `https://api.api2cn.com/v1/`，模型保持 `grok-4.6`，provider/cache identity 改为 `api2cn_responses`；旧 RightAPI endpoint 从 production allowlist 移除。新凭据仅写入 gitignored、owner-only `config/local_secrets.json`，旧 RightAPI full plan/cache 不复用，必须用新 run ID 重建 immutable plan。
- 固定 RightAPI PoC-33 run `lifecycle-e2e-poc33-rightapi-20260918_165304`：entries 21/21 completed、168 selected queries、0 diagnostics、0 skipped。formal full 首项在 Growth 收到 `LLM_AUTHENTICATION_FAILED`，独立无源码最小探针确认 HTTP 401，环境无备用 key；停止后续确定性失败并交付真实 partial ledger、33 行未评价记录、null TP/FP/U、immutable plan 和恢复命令，不宣称 33/33 或 precision。
- 将正式 Responses provider 与当前项目配置统一为 `https://rightapi.ai/grok/v1/` / `grok-4.6`，provider/cache identity 改为 `rightapi_responses`；旧 APIBasis full archive 的 `LLM_RETRIES_EXHAUSTED` 保留为配置漂移证据，不复用其 plan/cache。
- 将 RC1 生命周期后端接入正式 lifecycle/conclude：项目级只运行一次提取与求解，按 Growth submit/execute 程序点的完整 `dispatch` 事实绑定 `TaskBinding -> instance -> resource family -> executor contract`，拒绝仅凭文件/行号或 create 点关联。
- 新增独立 `ResourceLifecycleDecision`；`accepted_task_population` 仅在 exact executor scope、`arbitrary_finite_repetitions` cut、无 coverage gap 且上界为正时反驳 A2。未再伪造 legacy `BoundCandidate` 的 reject/phase/result_checked/scope 字段，异步释放与关闭义务语义保持不变。
- 生命周期结果和证书持久化 binding/property/result 引用；正式输出新增 `resource_lifecycle_bindings.jsonl` 以及可回放的 private facts/results，聚合器同步纳入 allowlist 与 binding 聚合。冻结 query-pack、DB/source/query/facts/result/implementation identity 进入证据和 resume identity。
- production lifecycle 在消费后端结果前强制核对 CodeQL database fingerprint，拒绝把其他数据库的 RC1 facts/property 绑定到当前 Growth 候选。
- 新增显式 lifecycle propagation 消融开关：full/off 都执行同一 provider 并保留相同 raw facts/results，只切换严格绑定性质是否进入 lifecycle/conclude；传播模式进入 run/config fingerprint，禁止跨模式 resume。
- schema/tool 升至 2.8/0.7.0；新增同位置错 callable/receiver、dispatch 歧义、unknown property、A2 refute/unknown、provider 单次执行与证书传播回归。

## [2026-09-17] Resource lifecycle RC1 delivery

- R1–R6 验收通过，工程 rc_ready、研究 unvalidated；被测实现 1a2d01aa2b605d8a9cbc76d1da0f05345845b5c4。九输入全部提取、8方法解析、4非空单元在3模块完成求解及回放、0预算退出。
- 原 readLog selector 返回包过期，保留 method_missing 和入口非零退出；4项 resource_unmodeled 不当作求解或安全。full/消融均1 bounded+17 unknown，独立增益0，无相关call/task关系和独立oracle。
- 原十二例两模式12/12，普通性质与语义回放一致，合成增益6；最终同环境全仓1212 passed，原12 failures/1 collection error持续，零新增失败/错误ID，新增默认skip均有明确独立验收。
- 发布紧凑门槛、九请求前后账本、性质/同事实对照、成本与源码/DB/查询/预算/实现身份；报告仅记录ready_for_push，实际交付SHA在提交后远端核验。

## [2026-09-16] Resource lifecycle RC1

- 在固定 v1.2 基线的隔离分支增量修复；保留原源码、DB、归档、十二例 oracle 和主工作区无关修改，仅执行防御性离线静态验收。
- 将源码全树/DB 归档分开记录，逐文件核对已归档字节；仅完整注释/空白缺失可接受，声明缺失或词法不确定保留可审阅 scope 并 fail closed。
- 生命周期查询使用 65,536 行专用传输额度，保留 JSON/字符串/单片限制；独立 callable inventory 区分方法定位、零资源规则覆盖与求解执行，零资源不计非空求解、不发布上界零。
- 循环 SCC 使用关系分区、抽象包含与有限延迟 widening；历史分配与持有/义务/峰值分开，retired recent 可复用，重复实例释放/丢弃弱更新；证据明确记录抽象推导，新增求解诊断计数。
- 修复支持深度内精确 wrapper 的 executor rejection 异常出口/返回，保留 caller catch/finally；拒绝不虚构 task capture。只对完整且精确非重复分配的显式任务完成条件切面检查有限持有上界，不用评价 oracle 补 bound。
- 最终全仓暴露的五个旧 all_exits 语义回归已通过收紧条件切面修复，保留原人工 IR oracle；可达循环下 worklist 收敛不再被误记为 termination_guaranteed。
- 紧凑报告补充 DB fingerprint、归档/查询输出 hash、实际行数、恢复依赖包与原过期 selector 的候选差异；严格保留输入分母，未替换错误返回类型。
- 同步程序按控制点与完整资源状态精确去重，避免不同历史边集合重复求解；任务阶段/路径分区保持原样，新增 diamond 回归保留互斥关闭后的未关闭实例。
- 增加三种循环真实源码回归、包装异常/额外 holder 反例、接入与完整分母测试；新增固定九输入复跑入口和沿用既有格式的紧凑报告，成本未测量为 null，工程门槛与研究有效性分开。

## [2026-09-16] Resource lifecycle v1.2 independent input intake

- 用户明确允许使用 PoC 所属本地源码与 CodeQL DB；冻结 3 个已有模块、9 个方法（XXL-JOB core、HertzBeat common-core/common-spring），没有导入 PoC verdict 或执行样例。
- 现有 DB 归档源码与 live 字节一致，但 live 有未归档文件，严格全树检查拒绝；改为完整主源码原样镜像与 build-mode=none 新 DB，保留未解析依赖和非编译验收限制。XXL-JOB 仍未通过全树匹配，失败输入保留分母。
- 最终 9 条输入全部留账：3 提取失败、4 未映射、1 iteration_limit 预算退出、1 完成分析与语义回放。完整/消融均 12 条 unknown 性质，独立增益为 0；H4 blocked，缺口不再是授权或源码路径缺失。
- 新增可复核源码镜像脚本、四份范围/尝试manifest、独立分层报告及精确CSV忽略例外；核心代码/查询未变，既有A–C验收保留。

## [2026-09-16] Resource lifecycle v1.2 partial delivery

- 从固定 v1.1 基线建立独立工作树；新增共享正式性质发布、多资源选择、项目清单与已有候选导入、完整阶段台账、内容寻址分片与源码重绑定语义回放。P0 schema/tool 和双份 CodeQL 查询保持不变。
- 修复 task_queue 消费进度缺口误用于已到达的精确 TaskExit；保留缺少 caller 异常 CFG 的两例 unknown。冻结旧 oracle 不变，完整模式 10/12、消融 12/12，评价器不再从状态计数生成 bound。
- 真实编译提取的 1×/2×/4× 规模组在最终实现上复用事实、重新分析并完成迁移目录后的复算：总字节 8,972,744 / 17,883,020 / 35,703,572，最大分片 34,408 bytes；仅作为同一 fixture 的规模副本。全仓同环境差分零新增失败/错误，原有 101 failed、1 collection error 保留。
- 为三份必需紧凑 CSV 报告添加精确 gitignore 例外，大型本地运行产物继续忽略。
- 新增缺分片 CLI 非零退出、范围隔离、源码多资源、预算失败及候选分母回归。最终九项报告与 HANDOFF 落盘；独立已有模块输入尚缺，H4 blocked，整轮 implementation_status=partial。全仓当前为 1102 passed、41 skipped、101 failed、1 error；源码一致性与 CLI 损坏拒绝补充各 1 passed。

## [2026-09-14] Resource lifecycle v1.1 G8 delivery closure

- G1–G8 全部通过，implementation_status=complete、delivery_state_at_commit=ready_for_push。最终 fresh 源码双模式各 12/12、606 facts、6 gains，当前实现 hash 与报告一致；全仓最终 1146 passed、39 skipped、12 个持续失败、1 个持续收集错误、710 subtests，零新增失败/错误 ID。README 数据库编译和真实 extract/analyze/replay 已验证，报告与 HANDOFF 正式落盘；历史限制和支持范围保持明确。

- 修复真实 SourcePairs evidence 体积：子证明依赖保留在自身 evidence_ids，取消顶层重复展开；路径规则通过 result_sha256 绑定的 scope/event/index 引用求解结果，保留具体 transition、state、出口位置与全局 rule dependencies。16 MiB 读取上限不变，真实 evidence 从 28,797,293 降至 16,704,007 bytes；新增精确路径可恢复及真实 facts 回放回归。

- 按完整迭代合同启动最终交付审计：重建固定基线 detached worktree，在同一环境比较全仓测试 ID 集合；两版本共同的全局 skill 路径收集错误保留为显式环境缺口。
- 重新生成当前实现的十二例源码评价，以消除旧持久化结果与后续 adapter 修复之间的实现哈希差异；G8 和整体交付仍为 partial，待正式报告、文档、HANDOFF 与推送验证完成。
- 同环境差分已得到零新增失败/错误 ID（持续 12 failed、1 collection error）；fresh 源码双模式各 12/12、606 facts、6 gains，同源码旧/新提取覆盖和人工 IR/契约测试分类指标已落盘。README 实测发现 analyze 的 28,797,293-byte evidence 超过 replay 16 MiB 限额，G8 暂不关闭，待修复并重新验收。

## [2026-09-14] Resource lifecycle v1.1 Task 6 fresh CodeQL closure

- 首轮 fresh 十二例 CodeQL 验收真实执行完成，612 条 raw facts 均保存在独立 diagnostic 目录；full 6/12、关闭跨事件传播 8/12 匹配冻结期望。差异定位为：内部 dataclass `asdict()` 保留 tuple reason 时 evaluator 只接受 list；unknown population 仍展示局部 K+W；共享 callback 的 exact empty source close 缺 typed exception successor 而触发 terminal gap。
- evaluator 现同时接受内部 list/tuple reason，并且只有 `bounded` population 才发布 total upper bound。task terminal 对缺 exception successor 继续默认 fail-closed，仅对 exact captured allocation、exact source dispatch、空方法体的 singleton-finally close 建立窄 no-throw proof；非空、非精确或无 source body 的 close 不获豁免。新增相应 Python/QL contract 回归，冻结期望未放宽。
- fresh 两文件全 CodeQL 首轮 `75 passed, 3 failed, 65 subtests passed` 暴露两个与 task query 无关的遗留 base-path 断言：多 allocation 方法把同一 unit-level CFG row 按 instance 复制为平行 transition，路径证据组合触发 `iteration_limit`；旧 queue fixture 仍期待 Task 5 已禁止的 capacity-only `bounded`。adapter 现只合并 source/target/guard/effects/assumptions 全部等价、仅稳定 ID 不同的 CFG transition，保留不同效果与路径；queue 回归改为要求缺 TaskBinding/executor K/W/terminal population proof 时输出 `unknown` 及明确原因，不恢复 legacy bound。
- 最终持久化 fresh 结果 `/tmp/task6-fresh-fix2-20260914/` 含 606 条 raw facts：full 与 `disable_cross_event_propagation` 均 12/12 匹配冻结期望，unknown 分别为 3/9；相同 raw-fact snapshot 上获得 6 个 determinacy gains，五个正控 terminal gap 已消失，LLM calls 为 0。S2/S3 关闭释放与持有收益门槛，S5/S6 关闭 K/W/K+W 群体归纳门槛；未知容量、未解析 executor 与异常出口缺口继续 fail closed。
- 最终 Java→CodeQL→adapter→solver 两文件全套为 `77 passed, 67 subtests passed in 2622.68s`；全 lifecycle 为 `449 passed, 17 skipped, 235 subtests passed`，config/CLI/production/recovery 为 `135 passed, 4 skipped, 119 subtests passed`。`compileall`、fixture `javac`/`javap`、manifest JSON、direct/embedded task QL 字节一致性与 `git diff --check` 均通过；task query SHA-256 为 `facf5dd7a76296af7e1987582613ff7e2834a79a19c22bfa787724fdf42a89bd`。Task 6 与 G4–G7 完成；G8 尚未生成可审阅交付，整体状态继续为 `partial`。

## [2026-09-11] Resource lifecycle v1.1 Task 6 source-pair evaluator（待 fresh CodeQL 验收）

- 冻结 `source-cases.json` 的 S1–S6 六组十二个真实 Java 变体及 full/`disable_cross_event_propagation` 两模式期望：同步/精确包装任务、task-only/static-field holder、全出口/遗漏异常出口 close、direct/depth-2 wrapper、已验证/未知容量、支持 TPE/无法解析 executor receiver。既有 Task 2–5 `caller` 源码位置保持不动，新变体可由同一 fixture 编译。
- 新增纯本地 `resource-source-evaluate` 路径：显式接收 source suite、live source root 与匹配的 CodeQL database，拒绝远程 provider、LLM 和导入 facts 覆盖，执行双查询→adapter→主 solver→report；输出 raw facts/coverage、full 与消融结果、逐例 CSV/JSON、metrics、run manifest 和 summary。消融复用完全相同的 entry/candidate/raw-fact snapshot，仅删除跨 callable/task relation 驱动的 transitions 与关系集合、添加明确 coverage gap 后重算，不补写 edge、容量或最终标签。
- 审阅加固 source evaluator：suite payload 与 SHA-256 改为同一次受限读取，且外层 database fingerprint 必须与双 query 抽取 provenance 一致，以消除冻结期望/数据库身份 TOCTOU；条件 state 只有在 solver 完整终止、目标 state 无 unknown reason 且相关 coverage gap 已清除时才可记为 `bounded`；内部求解/消融失败统一包装为稳定错误码；CSV 保留冻结的 `property`，run manifest 记录 implementation、provenance 与双模式 result digest，并用精确字段不变/transition 差集、完整成功产物集回归约束纯删除消融和交付面。
- 非 CodeQL 复核结果：source evaluator `8 passed, 1 skipped`，全 lifecycle `447 passed, 17 skipped, 235 subtests passed`，config/CLI/production/recovery `135 passed, 119 subtests passed`；fixture `javac`/`javap`、完整 `compileall`、manifest JSON 与 diff 检查通过。fresh CodeQL 仍未获准、未执行，G4–G7 保持 `fail`。
- 新增 manifest/CLI/纯删除消融回归及 opt-in 真实 CodeQL 十二例验收。当前按约束只运行 javac 与非 CodeQL 测试；修改后的 source snapshot 已使 `/tmp/task5-sourcepairs-readapted-facts.json` 不再适用，fresh CodeQL 未执行前 G4–G7 与 Task 6 必须保持未完成，不把 skip/mock 或旧缓存算作 G6。
- fresh 验收失败时现在直接打印全部逐例 expected/observed 差异，避免只暴露一个无诊断布尔断言；该改动不放宽任何冻结期望。

## [2026-09-11] Resource lifecycle v1.1 Task 5 review closure

- 新增从 `PopulationEffect`、`TaskBinding`、`TaskExit` 与 `ExecutorContract` 派生的 `PopulationProperty`：以 `(q,a)=(0,0)` 为初态，对 direct accept、enqueue、assign slot、start、normal/exceptional terminate、reject 及显式 phase-matched cancellation 建立转移方程，检查 `0<=q<=K`、`0<=a<=W`、`q+a<=K+W` 在任意有限次外部接纳重复下保持。task queue 的兼容 `InvariantCandidate` 布尔证明位不再提供结论；候选容量只核对 K，task holder 的 `held_instances` 上界发布为 K+W。
- 首轮 fresh quality/spec review 分别为 `Ready: No` / `Spec compliant: no`，无 Critical，共定位四类 Important：normal/exceptional terminal、cancellation 与额外 dispatch writer 覆盖漏检；coverage gap 未按 queue scope 隔离；非 task queue `InvariantCandidate` 仍消费兼容布尔；atomic contract 原始依赖、contract ID 冲突和 model-only 正式 artifact/replay 不完整。对应审查反例先得到 `6 failed`（`/tmp/task5-review-red.xml`），再逐项修复。
- 当前对未知/符号 K/C/W、非原子容量、CallerRuns、DiscardOldest、伪造 guard、同一 executor transition 的多 population effects、缺 normal/exceptional 任一 TaskExit/terminate、无 count effect 的 cancellation、未绑定 dispatch writer、同 executor 第二个 TaskBinding 覆盖不全均 fail closed；每条 equation 独立计算 `preserves_bounds`。coverage gap 仅接受 `*` 或当前 binding 的 queue scope；显式 cancellation 只消费可信、phase-matched 的 `PopulationEffect`，不把 executor capture-cleanup enum 当成 q/a 证据。
- 非 queue candidate 一律以 `derived_invariant_model_unavailable` 保持 unknown，`g09-fixed-replacement` 不再凭兼容 flags 自证。`lifecycle-results.json` 的 `population_properties` 与顶层 `model_count_properties`、`evidence.json` 的 `population_derivations` 与 `model_count_derivations` 均可重算；population/model-only result/evidence 篡改均由 replay 检出。atomic invariant raw fact 进入 proof dependencies；同 evidence ID 的不同 executor contract body 被拒绝。
- 首个 API RED 为 collection error（`/tmp/task5-population-red.xml`）；K-only held bound RED 为 `1 failed`（`/tmp/task5-total-bound-red.xml`），coverage/复合 transition RED 为 `3 failed`（`/tmp/task5-semantic-red.xml`），reserved cancellation guard RED 为 `1 failed`（`/tmp/task5-cancel-phase-red.xml`），fresh review RED 为 `6 failed`（`/tmp/task5-review-red.xml`）。修复后审查定向 `6 passed`（`/tmp/task5-review-fixes-focused.xml`），model replay/contract conflict `3 passed`（`/tmp/task5-model-replay.xml`），人工 regression `6 passed`（`/tmp/task5-regression-after-review.xml`）。
- 首轮修复后的 fresh spec/quality 复审继续定位 writer coverage：普通 `retain` 可向同 family/task holder 写入额外 distinct instances；错误/缺失 contract、部分匹配 holder/target、identity-less dispatch、`family_id=None` retain、同 Effect ID 的好坏 writer 以及 task terminal 后 retain 均曾可逃逸。对应 RED 包括 `/tmp/task5-retain-writer-red.xml`、`/tmp/task5-writer-normalization-red.xml`、`/tmp/task5-dispatch-identity-red.xml`、`/tmp/task5-bound-retain-red.xml` 与 `/tmp/task5-writer-id-red.xml`。当前按 current contract，或 same bound holder + relevant/unknown family，或 same queued/run target 收集 writer，再强制 exact contract/binding；全部相关 writer（含成功映射者）的 evidence 进入 property/proof dependencies，消费端另以 K+W 复核 observed peak。
- quality 复审另发现 fixed-position replacement 错误声称 `distinct_instances` 的 `N'=N`；反例 `/tmp/task5-model-dimension-red.xml` 为 `1 failed`。model-only 现区分量纲：replacement 证明 `occupied_positions` 不变，fresh insert/same-object retain 才报告 `distinct_instances`，正式 artifact/replay 定向 `/tmp/task5-model-dimension-green.xml` 为 `4 passed`。manual fixture 的 population 即使 effects 缺失且使用 trusted contract，也从绑定资源族 allocation provenance 保持 `model_only=true`，unknown-contract 分支同样不冒充源码能力。
- 同 kind 多个精确 TaskExit 现逐 relation 要求唯一 terminate，不再把合法互斥出口误判为多义；回归 RED `/tmp/task5-multi-exit-red.xml` 为 `1 failed`。population timeout 通过 `AnalysisBudget.timeout_ms` 传入，起始、writer scan 与 equation 构造后均 fail closed 为独立 `population_solver_timeout`；RED `/tmp/task5-population-timeout-red.xml` 为 `1 failed`。条件 path 通过私有 helper 复用同一 internally-derived population proof，公开 API 不接受外部 proof 注入，顶层 analyze 实测只派生一次；evidence 消费该次结果而不重启 wall-clock deadline，replay 则重新派生完整 result/evidence 后比较，临界 timeout 可正常落盘为 unknown。
- population checker 将 TaskExit/terminal/cancellation/writer 关系预索引后，100/200/300 tasks 的五次运行中位数由旧实现约 `0.129/0.526/1.227s` 降为 `0.0032/0.0065/0.0100s`。最新含 cached raw facts 重新适配的全 lifecycle 为 `442 passed, 13 skipped, 235 subtests passed in 9.79s`（`/tmp/task5-artifact-blockers-all.xml`）；focused invariants/replay/CodeQL synthetic 为 `160 passed, 13 skipped, 122 subtests`（`/tmp/task5-focused-postfix.xml`）。
- `/tmp/task5-sourcepairs-readapted-facts.json` 只复用 `/tmp/task4-sourcepairs-full-facts.json` 的既有真实 raw CodeQL facts，并由当前 adapter 重新派生/校验；没有运行 fresh CodeQL。该真实源码记录导出 K=3、W=2、K+W=5 与所需方程，且 `initial_holds/transitions_preserve=true`；原 raw facts 的 `task_terminal_coverage_incomplete` / `task_callback_effect_unmodeled` 仍使整体 population proof 为 unknown，不能当作 G5 已通过。G5 待 Task 6 无缺口源码对照关闭，G4/G6–G8 仍 fail；P0 schema/tool `2.5/0.4.0`、三态和 async Release 限制不变，不 push。
- 最终 fresh spec/semantics review 给出 `Spec compliant: yes`，fresh quality/artifact review 给出 `Ready: Yes`；两者 Critical/Important/Minor 均无。spec delta 核验为 `110 passed, 1 skipped, 76 subtests` 加 cached raw `1 passed`；quality 核验为定向 `150 passed, 152 subtests` 与全 lifecycle `442 passed, 13 skipped, 235 subtests`。Task 5 实现与复审关闭，但整体 `implementation_status` 仍为 partial、G5 仍 fail，下一步进入 Task 6 十二个真实 Java/CodeQL 变体。

## [2026-09-11] Resource lifecycle v1.1 Task 4 review closure

- fresh spec review 对 `b8cdb0e..f405c10` 给出 `Spec compliant: yes`，fresh quality review 对同一范围给出 `Ready: Yes`；两者 Critical/Important/Minor 均无。quality 额外核验跨 task/wrong binding、可达与不可达同 callable CFG、terminal source/target、registry/replay 篡改、A/B/C 旧反例及预算 fail-closed。
- review 验证为 Task 4 定向 `96 passed, 1 skipped`、cached focused `235 passed, 156 subtests`、全 lifecycle `403 passed, 13 skipped, 235 subtests`；cached evidence `9,036,068 / 16,777,216` bytes，caller `827 steps / terminated=true / termination_guaranteed=false`，`compileall`、`git diff --check` 与 clean worktree 均通过。未运行 fresh CodeQL query，证据继续明确为既有真实 raw facts 的当前实现回放。
- G3 改为 `pass`、Task 4 complete；整体仍 `partial`，G4–G8 fail。Task 5 开始实现从真实 `PopulationEffect`/`ExecutorContract` 推导的 q/a 群体归纳与重复事件检查；P0 schema/tool `2.5/0.4.0`、三态结论和 async Release 限制不变，本提交不 push。

## [2026-09-11] Resource lifecycle v1.1 Task 4 exact terminal source contract

- fresh review 的 singleton activation 与 source kind/callable 两项 Important 已修复实现，G3 仍 fail/pending fresh review。`resolve_task_exit` 无论候选数量均精确匹配 source activation 的真实 ProgramPoint，核对 source/target/point/TaskExit/TaskBinding kind、callable 与出口归属；active source 只允许 binding.run 或从该 run 经 internal、同 callable method CFG 可达的 method。合法 `task_run → task_exit` 保留；缺失、过滤后零个或多个、错误 source/target/task 均 fail closed。task normal/exceptional 边即使误指普通 request exit，也不再按普通 task 内部边执行，而保留 `task_exit_relation_unresolved:<task>`；真正的 caller request exit 不受影响。
- 先迁移人工 fixture 为独立 normal/exceptional terminal source，保留 body 节点及 CFG 77/88、terminal 99/109 精确位置。新 source 矩阵首轮 RED `38 failed, 12 passed`：其中公开 Program 边界的 source/solver 反例 20 项，另 18 项仅为绕过已有效构造校验后的 resolver 防御性检查，不冒充公开导入缺陷。补充 ordinary-target 反例 RED `2 failed, 2 passed`；已有 constructor/method/task_run/replay 正控不计 RED。wrong-target 早期 evidence 校验的错误消息断言曾需修正，仅属测试预期，不计新生产缺陷。
- 最终 focused `289 passed, 173 subtests`，完整 lifecycle `403 passed, 13 skipped, 235 subtests`；新 source/target 矩阵 54 项全部通过。async 与 dimension consumer 独立拒绝错绑，singleton source relation replay 篡改检测、既有同 kind 互斥出口位置隔离均通过。独立 cached analyze/replay 与 16 MiB gate `2 passed`；4-unit SourcePairs evidence 为 `9,036,068` bytes，低于 `16,777,216`，caller 保持 827 steps、termination_guaranteed=false。compileall/diff-check 通过。
- 本轮未改或重跑 QL、未改 adapter；验证继续使用同批完整真实缓存，不冒充新 query 执行，既有 source coverage gaps 不消除。P0 `2.5/0.4.0`、三态及 async Release 限制不变；Task 5 未启动，新 commit、不 amend/push。

## [2026-09-11] Resource lifecycle v1.1 Task 4 async terminal location fixes

- fresh双审确认async phase proof仍按共享exit event广播TaskExit位置，互斥路径各混入line99/119；先补normal/exceptional同kind反例，再与solver/child proof共用精确出口解析，缺失或多义fail closed。G3保持fail/pending fresh review，本轮新commit、不amend/push，Task5未启动。
- 新增共享 `resolve_task_exit`，按terminal edge的event/kind、同kind多出口时的source ProgramPoint选唯一关系；solver保留scoped unknown，async/child evidence缺失或多义直接拒绝。async不再按reached event广播位置，只引入该trace实际选中TaskExit的位置及registry relation IDs，并检查出口事实确在trace evidence中。async/child共用point relation registry入口，避免两套解析再次漂移。
- 有效RED为 `2 failed, 2 passed`：normal路径误含119、exceptional路径误含129；缺失/多义既有fail-closed正控不充作RED。最终新测试 `6 passed`，连同前轮位置回归 `15 passed`；含真实cached的focused `181 passed, 156 subtests`，全lifecycle `349 passed, 13 skipped, 235 subtests`。normal/exceptional互斥path、dimension child不回退、registry point错绑及async location污染的replay检测均通过；compileall/diff-check通过。
- 本轮未改/重跑QL或adapter；同批真实SourcePairs缓存CLI/replay和16MiB体积断言通过。未启动Task5，G3继续pending fresh review；新commit、不amend/push。

## [2026-09-10] Resource lifecycle v1.1 Task 4 terminal evidence fixes

- fresh quality final 发现 conditional child proof 只采集 effect location，漏实际 TaskExit/CFG ProgramPoint；按已执行 transition endpoints 补关系证据与位置，不混入互斥路径。另修 pure Abort reject-only 的 termination_guaranteed 被历史 async_states 误压为 false。先保存有效 RED，G3 继续 pending fresh review，Task5 / push 不启动。
- CFG 端点仅按 Event.activation_condition 的精确 ProgramPoint ID 解析，TaskExit 按 event/kind 与多出口情况下的 source point 解析；child proof 引用独立 `program_point_evidence` / `program_point_relation` registry IDs，并保留对应位置与依赖。同一事件多个正常出口的 solver evidence 现按 source point 选唯一 TaskExit，条件维度不再追加 event 级任意出口事实；不能唯一绑定则 scoped unknown。termination_guaranteed 根据 caller-exit cuts 的 queued/reserved/running pending 计算，reject-only 可为 true，但 obligation_gap 不变。
- 有效 RED：normal/exceptional × 有/无 close、真实 cached line39、pure reject 共 `6 failed`；同kind互斥出口证据混合另为 `1 failed`。最终本轮 `9 passed`，含真实cached的 focused `175 passed, 156 subtests`，全 lifecycle `343 passed, 13 skipped, 235 subtests`；compileall / diff-check 通过，TaskExit/CFG位置及关系删除篡改被 replay 检出。
- 集成回归首次发现重复嵌入 endpoint relation 令真实 evidence.json 达18,469,998 bytes，超现有16MiB限额；改为registry规范化、child引用精确ID后为8,998,683 bytes，未放宽读取上限，真实facts→CLI→replay通过。新增cached体积断言。未改/重跑QL或adapter，原SourcePairs source coverage gaps保持unknown；本轮新commit、不amend/push，G3仍pending fresh review。

## [2026-09-10] Resource lifecycle v1.1 Task 4 fresh re-review fixes

- fresh re-review 发现 A property trace 合并互斥接纳路径并支撑条件 bounded、B 纯 Abort reject 被误当 pending 而公开状态漏 obligation_gap、C dispatch matching 漏 family_id / Program 未校验 instance-family 一致性。G3 继续 fail；逐项补 RED 后修复，最终追加新提交，不 amend/push，Task5 不启动。
- A 保存 `PropertyDerivation` 的独立 state/trace，公共 `property_traces` 改为逐路径列表；条件性质逐路径检查并生成 `PropertyPathResult`，顶层仅聚合结果、不拼接 transition_ids。每个 child proof 明确引用原 property event/index、真实 trace/state/location；路径记录缺失或与状态投影不一致则 unknown。B 按每条 caller-exit configuration 的 queued/reserved/running 判断 pending，rejected/cancelled/terminated 不冒充活跃任务。C Program/JSON 导入统一拒绝 effect instance-family 不一致，matching dispatch 额外精确校验 family_id。
- 有效 RED 为 `6 failed`（A 三项、B 一项、C Program/JSON 两项）；最终 re-review `11 passed`，与前次 review 合计 `28 passed`；含真实 cached facts 的 focused `166 passed, 156 subtests`，全 lifecycle `334 passed, 13 skipped, 235 subtests`。compileall/diff-check 通过；serializer/all_tasks/path-evidence-missing 与 CLI/replay path tamper 已覆盖。初始 JSON 测试构造 tuple/list 错误先修正后才计入有效 RED。
- 同批真实 SourcePairs 经当前 validation/solver 默认预算仍为 `827 steps / terminated=true`，80 条独立 task terminal 路径；normal/exception obligation `[0,0]`，移除已有 release 后 `[1,1]`。未重跑/修改 QL，本轮未修改 adapter；当前 CLI/replay 使用此前已重新适配的完整4-unit真实事实。README/limitations 同步修正为 G1–G2 pass、G3 fail/pending fresh review，整体 partial。

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
## 2026-09-05

- 三目标 canary 放行后的首个 APIBasis 21-target fresh formal full `results/java_web_dos_batch/poc33-apibasis-full-20260905_195253-full/` 在 HertzBeat attempt 1 已取得 15 条有效 Growth/Auth cache 后收到 provider-side `LLM_AUTHENTICATION_FAILED`；同一 owner-only credential 的紧随 source-free probe 仍返回 HTTP 200、`status=completed` 与有效 `grok-4.6` strict-schema envelope，排除缺 key、全局凭据失效与请求格式错误，确认 provider 认证拒绝可呈非确定性。该错误原本不在 target requeue allowlist，HertzBeat 因而 terminal failed；批次随即人工中断封存为 1 failed、20 interrupted，不 resume、不聚合、不验收。TDD 先将真实 error code 加入 provider-failure regression 并得到 `1 failed, 1 passed, 4 subtests passed`，最小修复仅将 `LLM_AUTHENTICATION_FAILED` 加入既有 `--retry-failed --max-attempts 2` bounded target allowlist；focused runner/acceptance 门为 `37 passed, 5 subtests passed`。401/403 仍立即终止当前 provider call，missing local credential 仍不可重试，只有同一 fresh invocation 的一次 non-resume target attempt 可重试，第二次失败仍 terminal；下一轮 21-target 必须使用全新 run ID，178/205 rollout 继续暂停。
- 按用户明确指示将 `grok-4.6` formal provider 从 RightAPI 切换为 APIBasis：唯一生产 base URL 现为 `https://apibasis.com/v1/`，协议保持非流式 `POST /responses`，provider/cache/audit identity 改为 `apibasis_responses`，旧 RightAPI URL 在 production endpoint gate 中被拒绝。base URL 已进入既有 model/stage identity，base URL/provider identity 已进入 Growth/Auth cache identity；新凭据同时轮换 cache HMAC，因此 fresh APIBasis run 不 resume 或复用任何 RightAPI stage/cache。PoC-33 immutable plan 与 README 现统一明确 digest-bind `model`、`base_url`、`timeout_seconds`、`max_retries`、`allow_remote_llm` 五字段。API key 只写 owner-only、gitignored `config/local_secrets.json`，不得进入命令、日志、报告、回复或提交。source-free live canary 已获 HTTP 200、`status=completed`、有效 strict `json_schema` 合约；fresh formal v32 三目标 canary `results/java_web_dos_batch/poc33-apibasis-v32-20260905_165938-provider-canary/` 已 3/3 completed（HertzBeat、ThingsBoard attempt 1；WGCLOUD bounded attempt 2），六 stage fingerprints、24/24 Entry queries、0 diagnostics/skipped、61 条 0600 private audit/cache provider/base URL/model identity 与公开 artifact secret/header 零命中均通过独立门禁。PoC-33 21-target formal full 必须使用全新 run ID，178/205 rollout 继续暂停。

## 2026-09-04

- source-free RightAPI health gate 在连续 8 次 HTTP 500 后执行一次不含源码的脱敏错误体诊断，远端明确返回 `api_error: Grok requires Postgres (DATABASE_URL)`。这把当前 blocker 收敛为 `rightapi.ai/grok/v1` 服务端缺失数据库配置，而非本地 API key、请求格式、bounded-source payload、strict schema、CodeQL 或 batch requeue；12 小时轮询已停止，预留的 fresh 输出 `poc33-handler-v32-healthgate-20260904_190500-full/` 未创建，任何 formal target 源码均未由该健康门发送。待远端修复后仍须使用全新 run ID 执行 21-target full，既有 failed/interrupted 批次不 resume，178/205 rollout 继续暂停。
- 修复 Growth v32 route-free same-handler association 的 canonicalization 落穿：Netty handler-base 专用分支已要求所有 link status 一致，但 mixed complete/partial rows 此前会继续进入 generic duplicate-registration canonicalizer，并在 route aliases 上错误强选或抛出 `ANALYSIS_GROWTH_ENTRY_AMBIGUOUS`。通用 canonicalization 现同样要求 uniform link status；状态不一致时保留全部 links，固定输出 `inventory_unresolved/ambiguous` 与空 canonical Entry，禁止 partial-status averaging。该修复使实现符合唯一规范既有第 21.2 节及 growth-v32 identity，不改变 schema/tool、stage fingerprint、provider contract 或 formal retry 边界。
- 修复后全新 PoC-33 v32 formal run `results/java_web_dos_batch/poc33-handler-v32-requeue2-20260903_203522-full/` 已自然终止为 `completed_with_failures`，不 resume、不聚合、不验收：10/21 targets completed、11/21 targets 在 attempt 2 仍以 `LLM_RETRIES_EXHAUSTED` 失败。21/21 Entries 均完成正式 8-query coverage、0 diagnostics/skipped；10 个 completed targets 具备六 stage 与固定 fingerprints entries-v17/growth-v32/flows-v21/lifecycle-v14/conclude-v5/report-v1，11 个 failed targets 只发布 Entries。10 个正式 private audit 均为 0600（95 records，3 个无需 LLM 的 completed target 合法为空）；443 个非隐藏、非 cache/private 公开文件中实际 provider key、`Authorization:`、`Bearer ` 命中均为 0，acceptance/aggregate 不存在。失败集中于 Dependency-Track、ThingsBoard、WGCLOUD、Concord、XXL-JOB、RuoYi-Vue-fast、Citrus、Druid、Solr、Presto、DataCompare，并在次日 source-free health probes 继续表现为 HTTP 500 与 TLS EOF，确认当前阻塞是持续 provider outage，而不是本地死循环、CodeQL gap 或 target-requeue 缺口。新的 fresh full 仅在 provider 健康门恢复后启动；178/205 rollout 继续暂停。

## 2026-09-03

- fresh 21-target v32 requeue run `results/java_web_dos_batch/poc33-handler-v32-requeue-20260903_181500-full/` 在 4 个目标 completed 后，Rebuild attempt 1 的第 18 个 Growth contract 遇到 malformed/incomplete/mismatched Responses envelope 并以 `LLM_RESPONSE_INVALID` 原子失败；该 error 对单 provider call 按协议永久失败、无 safe correction/cache/audit，但遗漏在同 invocation target-retry allowlist，故 Rebuild 不会重新入队，批次已在 GROBID 启动后立即中断封存为 4 completed、1 failed、16 interrupted，不 resume/聚合/验收。TDD 先把 fresh single-invocation regression 改为该真实错误并稳定得到 `completed_with_failures`，最小修复仅把 `LLM_RESPONSE_INVALID` 加入既有 bounded target allowlist；单调用协议、strict schema/sensitive gates、无 rejected-response reuse、第二 target attempt terminal、stage fingerprints 均不变。README 与唯一规范同步明确“permanent”是 provider-call 边界，新的 non-resume target attempt 才可重试；下一轮仍必须使用全新目录，178/205 rollout 继续暂停。
- Rebuild owner-only provider capture `results/java_web_dos_batch/poc33-rebuild-handler-v32-schema-debug-20260903_171702/` 以与 formal full 相同的 v32/fail-closed/non-resume/provider 设置完成终态诊断：13 个 unique Growth slices 共收到 20 条 Growth responses，其中 7 次 initial 违反空 attacker-options alias binding 或 unknown-status consistency 并进入唯一 safe correction，前 6 次 correction 恢复合法，第 7 次 correction 再次返回空 options 域外 attacker alias，目标因此按 `LLM_RESPONSE_SCHEMA_INVALID` 原子失败且只发布 Entries stage。另有 10 条 Auth transport responses；原始 30-record capture 仅保存在 `/tmp/dosweb-rebuild-v32-schema-debug.private.jsonl` 且 mode 0600，不进入公开 artifacts。16 个非隐藏、非 cache/private 的公开文件中实际 provider key、`Authorization:`、`Bearer ` 命中均为 0。该 fresh debug 不用于 acceptance/resume/aggregate；它稳定证明 Rebuild 的终止来自 provider 非确定性 schema/binding 违约，而不是本地死循环，并直接验证同一 fresh batch invocation 内 bounded target requeue 的必要性。PoC-33 正式 full 仍必须使用全新目录，第二次 target attempt 失败即 terminal；178/205 rollout 继续暂停。
- PoC-33 v32 21-target `retry1` fresh full `results/java_web_dos_batch/poc33-handler-v32-retry1-20260903_151934-full/` 在 4 个目标 completed 后由 Rebuild 的 `LLM_RESPONSE_SCHEMA_INVALID` 失去 21/21 资格并被立即中断封存，未 resume/聚合。连续两次 whole-batch fresh 重启分别被 Dependency-Track 与 Rebuild 的非确定性 provider schema failure 提前终止，暴露出既有 batch retry 的编排缺口：runner 已把 schema/sensitive/一次性 network/provider failure 定义为可由新 target attempt 重试，但单次 invocation 的目标迭代器不会重新入队，因而只能依赖另一次 `--resume --retry-failed`，与本轮“不复用失败批次”门禁冲突。runner 现使用 bounded deque，在同一个 fresh invocation 内仅将仍满足既有 error allowlist 与 attempt ceiling 的目标重新入队；PoC-33 acceptance 显式使用 `--no-resume --retry-failed --max-attempts 2`，第二次 target attempt 仍为 non-resume、不会接受/复用 rejected response，只允许正常 HMAC-authenticated schema-valid cache replay。full archive validator 要求每目标 attempt 为 1..2 并输出 `retried_targets`；non-retryable 或第二次失败仍 terminal。TDD RED 为 2 个目标失败，最小修复后 batch/acceptance focused gate 为 `37 passed, 3 subtests passed`；stage artifacts/fingerprints、strict schema、binding、positive gate、CodeQL fail-closed 与 per-request retries 均不变，178/205 rollout 继续暂停。
- v32 canary 放行后的首个 21-target fresh formal full `results/java_web_dos_batch/poc33-handler-v32-20260903_135529-full/` 在完成 HertzBeat、jMQTT 后，Dependency-Track 首个 Growth contract 的 initial 与唯一 safe correction 均未通过 strict schema，目标以 `LLM_RESPONSE_SCHEMA_INVALID` 原子失败；该批已立即中断并封存为 2 completed、1 failed、18 interrupted，顶层 `running` 是中断后的 stale 字段，不 resume、不聚合、不用于 acceptance。随后 fresh 单目标 owner-only capture `results/java_web_dos_batch/poc33-dependencytrack-handler-v32-schema-debug-20260903_145221/` 以相同 formal/fail-closed/provider 设置 1/1 completed、六 stage 完整、entries-v17/growth-v32/flows-v21/lifecycle-v14/conclude-v5/report-v1、0600 audit 12 records、6 个 exact `static_unknown` findings；13 条私有 transport responses 中 6 条为 Auth、7 条为 Growth，唯一 Growth 初答在空 attacker options 下错误输出 positive，安全 correction 返回合法非 positive contract，其余 Growth 直接通过，故原终止错误未稳定复现，归类为 provider 非确定性而非确定性本地实现缺陷。107 个公开文件中 provider key、`Authorization:`、`Bearer ` 均为 0；严格 schema、evidence binding、positive gate 和 exactly-one correction 均未放宽。下一次 21-target 必须使用全新目录，178/205 rollout 继续暂停。
- fresh v32 三目标 formal provider canary `results/java_web_dos_batch/poc33-schema27-handler-strict-v32-20260903_114332-provider-canary/` 通过：HertzBeat、ThingsBoard、WGCLOUD 均在 attempt 1 completed，batch 为 `completed`；每目标 Entries/Growth/Flows/Lifecycle/Conclude/Report 六 stage 完整，fingerprints 精确为 entries-v17、growth-v32、flows-v21、lifecycle-v14、conclude-v5、report-v1，每目标 6 条 framework coverage、8 条 selected CodeQL queries、0 diagnostics、0 skipped。0600 `llm_audit.private.jsonl` 分别为 19/25/17 records；307 个公开文件中实际 provider key、`Authorization:` 与 `Bearer ` 命中均为 0。三库共输出 45 个 exact findings（HertzBeat 11、ThingsBoard 19、WGCLOUD 15），均为 `static_unknown`，聚合为 43 个 finding families；这只放行全新 PoC-33 21-target formal full，不表示安全、动态确认或 recall/precision 通过，178/205 rollout 继续暂停。
- 接管第二次 PoC-33 21-target fresh v31 formal full `results/java_web_dos_batch/poc33-flat-v31-retry1-20260903_081700-full/` 后确认 acceptance/batch 子进程均已退出；中断后的 `batch_state.json.status=running` 是顶层 stale 字段，目标状态已持久化为 3 completed、2 `LLM_RETRIES_EXHAUSTED`、1 `ANALYSIS_FLOW_INVALID`、1 running-at-interrupt 与其余 interrupted。该目录不 resume、不聚合、不作为 formal acceptance。GROBID 本地重放 6 条 Flow raw rows（4 条与正式 E/G 域相交）定位到 `FLOW_CANONICAL_ENTRY_MISMATCH`：POST line 484 与 PUT line 522 两个不同 JAX-RS handler 共用 Dropwizard Guice application registration line 44，Growth 仅按 registration identity 将两条 partial association 错合并为 line 522 canonical Entry，Flow 随后遇到 line 484 的真实路径而 fail closed。TDD 回归先稳定失败，再把 generic duplicate-registration canonicalization 收紧为完整 same-handler registration-site/Auth/input/materialization identity；相同真实 CodeQL Association/Flow rows复验得到 2 links、`inventory_unresolved/ambiguous`、空 canonical Entry，GROBID 冲突候选不再进入 LLM/Flow。Growth production fingerprint 轮换为 v32，formal resume 禁止复用 growth-v5..v31；schema/tool、entries-v17、flows-v21、lifecycle-v14、conclude-v5 不变。
- 两轮 v31 full 的 provider 失败均发生在目标已成功缓存多次 Growth/Auth 调用之后（第二轮 Dependency-Track 15 个、Rebuild 36 个 cache records），结合首轮后 10/10 source-free health probe，确认是单调用间歇 transport/provider 窗口而非持续 key/DNS 失效。PoC-33 formal plan 继续固定 180 秒超时、fresh/no-resume、`max_workers=1`、sole safe schema correction 与全部本地 typed/binding/positive gates，仅将已有合法 transport attempt 上限从 3 提至 5，并把该值纳入 immutable plan/archive validation；目标 acceptance 测试先红后绿。用户已明确批准 HertzBeat、ThingsBoard、WGCLOUD 及 canary 通过后的 PoC-33 21 库 bounded 源码发送至 `rightapi.ai/grok-4.6`。必须先执行 fresh v32 三目标 canary，21-target/open discovery 仍暂停，178/205 rollout 始终暂停。
- v31 三目标 canary 通过后执行首轮 PoC-33 21-target fresh formal full：`results/java_web_dos_batch/poc33-flat-v31-20260903_000500-full/`。batch 最终 `completed_with_failures`，13/21 completed、8/21 failed；全部目标 formal Entries coverage 均为 6 rows、0 diagnostics/skipped。失败由 1 个 `LLM_RESPONSE_SCHEMA_INVALID`（Dependency-Track）与 7 个 `LLM_RETRIES_EXHAUSTED`（Rebuild、GROBID、JetLinks、Zipkin、WGCLOUD、Concord、XXL-JOB）构成，失败目标仅保留 completed Entries stage，未发布伪造下游结果；13 个 completed 目标均有完整六 stage 和 0600 private audit，但总 finding 为 0，acceptance/aggregate 未生成。因此该批不满足 formal full 验收，open discovery、178/205 rollout 继续暂停。结束后以 10 个不含源码的极小 RightAPI health 请求复测，10/10 HTTP 200、Responses `completed`、model `grok-4.6`，说明七个 retry exhaustion 更符合运行时段的间歇 transport/provider 故障，而不是持续配置或 DNS 失败。

## 2026-09-02

- 第二次 fresh v31 formal canary `results/java_web_dos_batch/poc33-schema27-flat-strict-v31-retry1-20260902_213817-provider-canary/` 通过：HertzBeat、ThingsBoard、WGCLOUD 均 attempt 1 completed，batch `completed`；每目标 Entries/Growth/Flows/Lifecycle/Conclude/Report 六 stage 完整，fingerprints 精确为 entries-v17、growth-v31、flows-v21、lifecycle-v14、conclude-v5，每目标 6 条 coverage、0 diagnostics、0 skipped，0600 `llm_audit.private.jsonl` 分别 19/25/17 records。公开 artifacts 中实际 provider key、`Authorization:` 与 `Bearer ` 命中均为 0。三库本轮均未产生 finding，因此该 canary 只证明 formal provider/protocol/stage/私有审计链可完成，不等同 PoC-33 recall/precision 通过；21-target fresh formal full 现可按门禁放行，178/205 rollout 继续暂停。
- 获得当前线程对三目标及后续 PoC-33 21 库 bounded 源码发送至 `rightapi.ai/grok-4.6` 的显式授权后，执行 fresh v31 canary `results/java_web_dos_batch/poc33-schema27-flat-strict-v31-20260902_182102-provider-canary/`：HertzBeat 与 ThingsBoard 均在 attempt 1 formal completed，六个 stages 完整、各 6 条 Entry coverage、0 diagnostics/skipped，0600 private audit 分别 19/25 records；WGCLOUD 在 Growth 以 `LLM_RESPONSE_SCHEMA_INVALID` 原子失败，batch 为 `completed_with_failures`，21-target 未启动。随后用独立 0600 本地 capture 对 WGCLOUD 做一次 fresh 单目标诊断 `poc33-schema27-wgcloud-flat-debug-v31-20260902_204803`，该次 1/1 completed、六 stages 完整、0 diagnostics/skipped、0600 formal audit 17 records；脱敏诊断显示 flat schema 始终返回完整 17 keys，但 provider 偶发违反 `unknown => is_resource_growth=unknown` 或在空 `attacker_evidence_options` 时返回非空 alias，sole safe correction 在本次诊断中均恢复合法，说明 canary 失败是 provider cross-field/alias correction 的非确定性而非缺键或网络根因。诊断原文仅保存在 `/tmp/dosweb-wgcloud-flat-v31-debug.private.jsonl`（0600），未进入公开 artifacts；21-target 与 178/205 rollout 继续暂停。
- 接管旧 session 后独立复验 flat strict Growth schema 修复：8 项版本/schema/resume 定向门为 `8 passed, 6 subtests passed`，无 localhost focused 门为 `182 passed, 30 subtests passed`，宿主侧仅绑定 `127.0.0.1` 的 provider/client focused 门为 `303 passed, 2 warnings, 181 subtests passed`；`compileall`、`git diff --check` 与 24 个 direct/embedded CodeQL mirror 均通过。已创建全新 formal/fail-closed/no-resume 三目标 v31 canary 计划 `results/java_web_dos_batch/poc33-schema27-flat-strict-v31-20260902_182102-provider-canary/`，目标仍为 HertzBeat、ThingsBoard、WGCLOUD，`max_workers=1`、provider timeout 180 秒/3 retries。当前线程的远程执行审批因缺少本线程内对 bounded 源码发送至 `rightapi.ai/grok-4.6` 的显式授权而被拒；未发出源码、未调用 provider、未启动 batch，PoC-33 21-target 与 178/205 rollout 继续暂停。

- 修复 strict Growth JSON Schema 在 RightAPI/grok-4.6 上的 provider-compatibility 根因。fresh formal v30 三目标 canary `results/java_web_dos_batch/poc33-schema27-jsonschema-strict-v30-20260902_163604-provider-canary` 为 0/3：HertzBeat、ThingsBoard、WGCLOUD 均完成 formal Entry extraction，但 Growth stage 以 `LLM_RESPONSE_SCHEMA_INVALID` 原子失败，batch 为 `completed_with_failures`，未进入 PoC-33 21-target。脱敏 owner-only diagnosis 证明 Auth strict schema 返回完整四键，而 Growth initial/correction 在请求确实携带 `type=json_schema`、17 required、`additionalProperties=false`、三分支 `oneOf` 时仅返回分支少数字段；不含源码的 RightAPI A/B 又证明相同 17 字段 schema 带 `oneOf` 只返回 5 键，移除 composition 的 flat schema 返回全部 17 键且 unknown 三元组一致。Growth wire schema 现保留 exact 17 keys、enum/pattern、unique/maxItems、bounded text 与 `additionalProperties=false`，移除 wire `oneOf`/`const`；prompt 与本地 typed cross-field/evidence ownership/binding/safe correction/positive gate 均保持 fail closed。Growth prompt/cache/HMAC domain/production fingerprint 轮换为 v9/v14/v14/v31，response schema 保持 growth-v5；Auth v5/v5/auth-v3 与 entries-v17/flows-v21/lifecycle-v14/conclude-v5 不变，formal resume 不复用 growth-v5..v30，Growth v13 及更早 cache 为 cold miss。TDD RED 为 `7 failed, 1 passed, 6 subtests passed`，最小修复后目标 GREEN 为 `8 passed, 6 subtests passed`；不含 localhost server suite 的 focused gate 为 `182 passed, 30 subtests passed`。完整指定 focused 命令的 `tests/test_deepseek_client.py` 因当前 sandbox 禁止绑定 `127.0.0.1` 而在 94 个 class setup 中触发 `PermissionError`，不是断言回归；`compileall`、24 个 direct/embedded CodeQL mirror 与 `git diff --check` 通过。本轮未调用远程 provider、未启动 batch、未 commit；fresh v31 canary、PoC-33 21-target 与 178/205 rollout 继续暂停。
- 将正式 Growth/Auth Responses wire contract 从 best-effort `json_object` 收紧为 strict JSON Schema structured output。首轮真实 provider canary `results/java_web_dos_batch/poc33-schema27-provider-canary-v17-t180-20260902_134913-provider-canary` 中 ThingsBoard completed，HertzBeat 因 `LLM_RESPONSE_SCHEMA_INVALID`、WGCLOUD 因 `LLM_NETWORK_FAILED` 失败，batch 为 `completed_with_failures`，因此没有进入 PoC-33 21-target。HertzBeat 的 owner-only private diagnosis 证明 `json_object` 不强制 exact keys/enums/cross-field invariants：初答违反 unknown-status consistency，唯一 correction 又漏 mandatory `confidence`；两个不含源码的 RightAPI live probe 则分别确认 `text.format.type=json_schema` 支持 enum 以及 `oneOf` + `const`。Growth/Auth 请求现在提交 exact required keys、`additionalProperties=false`、enum 与 Growth status `oneOf`/`const` 的 strict schema，同时继续执行本地 schema、cross-field 与 evidence-binding 二次验证；Growth prompt/cache/HMAC domain 轮换为 v8/v13/v13，Auth prompt/cache 轮换为 v5/v5，response schema 仍分别为 growth-v5/auth-v3，Growth production fingerprint 轮换为 v30，entries-v17/flows-v21/lifecycle-v14/conclude-v5 不变。网络重试新增 TLS EOF、无 errno 的 transient proxy/tunnel 408/425/429/500/502/503/504，以及 timeout/temporary/reset/aborted/remote EOF；DNS `EAI_NONAME`、certificate verification、permission 与 `EINVAL` 仍永久失败。定向门为 `123 passed`，宽门为 `333 passed, 2 warnings, 181 subtests passed`。fresh 三目标 canary 尚未重跑，PoC-33 21-target 与 178/205 rollout 继续暂停；本轮文档同步未调用 provider、未启动 batch、未 commit。
- 收紧正式 P0 artifact acceptance：`candidate_entry_links.jsonl` 现在在 schema 边界验证与 production `CandidateEntryLink` 完全同构的 semantic identity。`evidence_ids` 与 `reason_codes` 必须为非空、排序、去重字符串，`link_id` 必须等于除自身外完整 record 的 `stable_identifier("candidate_link", semantic)`；因此篡改 status/evidence/reason 后即便同步重建 disposition ID，也会在 aggregate 前被标为 malformed，合法 link 保持通过。该 artifact-acceptance 变更轮换所有 formal resume fingerprints 为 entries-v17、growth-v29、flows-v21、lifecycle-v14、conclude-v5，并冻结 entries-v16、growth-v28、flows-v20、lifecycle-v13、conclude-v4 及更早产物。新增 aggregate status/evidence/reason tamper（含重建 disposition）与合法 link 回归；本轮未调用 provider、未启动 batch、未 commit、未清理保留资产。
- 修复 P0 aggregator 只对 eligible disposition 校验 canonical link、因而可能把 noneligible 旁的 orphan/cross-owned link 错记为 completed 的最后一个 quality Important。聚合边界现在对完整 raw Growth/disposition/link domain 做与 production 同构的 reconciliation：每个 link 必须属于 raw Growth、引用现有 Entry，并被同 Growth disposition 精确引用一次；complete/partial 只允许 sole canonical link 且 Entry/status 一致，missing 不得有 link/canonical Entry，ambiguous 不得有 canonical Entry 或 sole-link canonical shape。unresolved/rejected 旁的 orphan、wrong growth/entry/status 与 duplicate ownership 全部使 target `malformed`。这是独立 aggregate acceptance 收紧，不改变 formal stage artifact，故 production fingerprints 保持 entries-v16、growth-v28、flows-v20、lifecycle-v13、conclude-v4。目标 RED 为 `5 failed, 1 passed`，GREEN 后 batch+production focused gate 为 `114 passed, 42 subtests passed in 9.57s`；`compileall`、unchanged-fingerprint check 与 `git diff --check` 通过。本轮未调用 provider、未启动 batch、未 commit。
- 闭合 static-unknown root-cause 后续 review 的 `RETURN_VALUE` opcode 窗口与 Python 首 opcode 语言边界。execution-snapshot factory 在 owner callback/parent transfer 前为 owned `DatabaseInfo` 注册 non-cyclic `weakref.finalize`，callback 只捕获 persistent `ExecutionDatabaseBinding` 且禁用 interpreter-exit 执行；`factory_succeeded=true` 与后续 return 不再宣称 source-line atomic，flag 后、`RETURN_VALUE` 前的 opcode trace/真实 `SIGINT` 在无外部 owner 时由 GC finalizer 清理，在 production owner 已接管时由 owner/finalizer caller pair 清理。正常显式 cleanup 消费同一 close-once transaction，随后 GC finalizer no-op，不会重关 ABA 复用 fd。standalone cleanup 拆成 public paired wrapper 与 internal reacquiring core；`dis.Bytecode` 回归固定 public 首个 traceable `NOP` offset 2 位于 exception-table start 4 之前，因此 call-entry must-reach 明确由 formal caller lexical pair 承担，callee 只保证进入 protected body 后的双 reacquire。新增全 `dosweb/**/*.py` direct formal cleanup caller 审计；production fingerprints 轮换为 entries-v16、growth-v28、flows-v20、lifecycle-v13、conclude-v4，formal resume 冻结 entries pre-v16、growth v5-v27、flows v3-v19 与 lifecycle pre-v13。最终 focused gate 为 `336 passed, 5 skipped, 157 subtests passed in 14.11s`；24 个 direct/embedded query mirror 为 `2 passed, 22 subtests passed`；ownership/formal-caller/fingerprint AST gate 为 `11 passed, 6 subtests passed`；最小真实 JAX-RS CodeQL 为 `1 passed in 25.40s`，`compileall`、active fingerprint check 与 `git diff --check` 通过。本轮未调用远程 provider，未启动 PoC-33/178/205 batch，未重复 Netty 长测，未 commit，未删除 `.test-tmp/`、隐藏 CodeQL 临时文件或其他保留资产。
- 闭合 static-unknown root-cause spec review2 的两个 Important。execution-snapshot success action 现在只 transfer parent structural owner 并返回 binding，整个 action、`run_with_deferred_interrupts` restoration 与异常 handler 期间 `factory_succeeded` 始终为 false；只有 helper 完全正常返回后，inner `try/except BaseException` 内同一 source line 才提交 true 并立即 return，删除了“action 先置 true、handler 再 reset”窗口。helper restoration `OSError`、handler-line `KeyboardInterrupt`、next/return-line trace 在 owner callback 有/无六种组合均由 outer cleanup 通过 transferred binding 删除 snapshot 并消费 parent fd。standalone cleanup 删除 outer `try` 前的 `binding=None`，函数第一结构即 owning `try/finally`，两个 nested attempt 都直接从输入 `DatabaseInfo.execution` reacquire，不读取可能未赋值的 local；first owned-line trace 同次归零。production finalizer 又把 `snapshot_cleanup(database)` 展开为同参数 caller-local lexical pair，cleanup call-entry/profile 或 first-line/trace 逃逸仍执行第二次，之后才清 `owned_database`/`validated_database`。目标 RED 为 `5 failed, 1 passed, 4 subtests passed` 与 `3 failed, 1 passed`，GREEN 后 focused gate 为 `332 passed, 5 skipped, 155 subtests passed in 13.83s`；最小真实 JAX-RS CodeQL 为 `1 passed in 24.78s`。production fingerprints 轮换为 entries-v15、growth-v27、flows-v19、lifecycle-v12、conclude-v4；formal resume 冻结 entries pre-v15、growth v5-v26、flows v3-v18 与 lifecycle pre-v12。按 review 决策，本轮仅 cleanup/finalizer 变化，不重复 Netty 长测；未调用远程 provider，未启动 PoC-33/178/205 batch，未 commit，未删除共享 `.test-tmp/`、隐藏 CodeQL 临时文件或其他保留资产。
- 闭合 static-unknown root-cause review3 的三个 Important ownership escape。execution-snapshot factory 的 deferred success helper 与紧随其后的 return line 现在位于显式 `try/except BaseException` 中；helper restoration、return-event 或 next-line trace 在 parent owner transfer 后逃逸时会先恢复 `factory_succeeded=false`，再由最外 cleanup 通过 transferred binding 删除 snapshot 并消费 parent fd，owner callback 有/无四个组合均覆盖。standalone `cleanup_execution_database_snapshot()` 的 outer `finally` 不再信任一次 caller-local assignment：两个 nested cleanup attempt 都只接受 schema-valid binding，否则从输入 `DatabaseInfo.execution` 重新取得，assignment-line trace 逃逸在同一次调用内完成清理。fixture classes factory 在 return 前通过 deferred transfer 把完整 pinned object 放入 `_build_database()` 预建的 caller owner slot；callee transfer 后不再本地 cleanup，caller 验证 slot/object identity，并用幂等 lexical pair 消费 exact classes name、两个 fd transaction 与 owner slot，因此 profile return event 不能越过 caller assignment 泄漏 2 fd 或留下合法 `.classes.tmp-*` 终态。三组目标 RED 分别为 `4 subtests failed`、`1 failed`、`1 failed`，修复后 focused gate 为 `329 passed, 5 skipped, 151 subtests passed in 12.98s`；最小真实 JAX-RS CodeQL 为 `1 passed in 24.18s`；全新 project-local TMPDIR 强制重建 classes/DB 的 Netty formal full（real CodeQL + bounded in-memory mock Responses transport）为 `1 passed in 670.59s`。production fingerprints 轮换为 entries-v14、growth-v26、flows-v18、lifecycle-v11、conclude-v4；formal resume 冻结 entries pre-v14、growth v5-v25、flows v3-v17 与 lifecycle pre-v11。24 对 direct/embedded query mirror、database/runner/production/fixture acquisition-handoff-release AST、`compileall`、active/stale fingerprint gate 与 `git diff --check` 通过。本轮未调用远程 provider，未启动 PoC-33/178/205 batch，未删除共享 `.test-tmp/`、隐藏 CodeQL 临时文件或其他保留资产。
- 闭合 static-unknown root-cause re-review 后续的两个 Important 与一个 Minor。execution-snapshot factory 现在从 parent acquisition 前即进入最外 lexical cleanup，standalone cleanup 也把 binding acquisition 放入 outer `try/finally`；handler/prologue 的 profile、trace 或真实 `SIGINT` 不能越过 snapshot removal、parent release 与 consumed 后的 closed commit。production query workspace 新增 persistent reverse-order descriptor-chain owner，典型 ancestry/output/workspace/results 六 fd 在 `_WorkspaceDescriptorOwner.close()`、四处 `_release_workspace_descriptors()` caller 与 family/Entry 最终 cleanup 中均由同参数 lexical pair 接管；首调用未进入、first-success/second-call 中断、actual-close 后异常与 fd-number ABA 均不会泄漏或重关 replacement。fixture classes 的 cache-root 与 classes-leaf acquisition 均改为 `open_owned_descriptor`，在打开前建立 structural owner 与 persistent `DeferredCloseFdOnceOutcome`，factory failure/normal cleanup 使用 nested caller-local release pairs；补测又捕获并修复了 release-helper return event 已消费 transaction 后仍二次 close ABA fd 的 blocker。production fingerprints 轮换为 entries-v13、growth-v25、flows-v17、lifecycle-v10、conclude-v4；formal resume 冻结 entries pre-v13、growth v5-v24、flows v3-v16 与 lifecycle pre-v10。最终 focused gate 为 `326 passed, 5 skipped, 147 subtests passed in 12.83s`；最小真实 JAX-RS CodeQL 为 `1 passed in 26.47s`；全新 project-local TMPDIR 强制重建 classes/DB 的 Netty formal full（real CodeQL + bounded in-memory mock Responses transport）为 `1 passed in 663.88s`。24 对 direct/embedded query mirror、database/runner/production/fixture release AST、`compileall` 与 `git diff --check` 通过。本轮未调用远程 provider，未启动 PoC-33/178/205 batch，未删除共享 `.test-tmp/` 或其他保留资产。
- 闭合本轮 static-unknown root-cause re-review 的四个 Important。execution snapshot factory/standalone cleanup 不再在 tree-cleanup 与 parent-release `finally` 建立前提交 `cleanup_state.closed`：factory 统一为 binding-lock 内的 cleanup-failure capture + parent owner/transferred binding lexical release pair，parent-release `finally` 在任何残留 snapshot-root release retry 前建立，private-tree cleanup 又嵌入该 retry 的 `finally`；仅在 persistent transaction consumed 后以 duplicated deferred commit 标记 closed，保持 cleanup failure precedence；database owner/direct AST 相应收敛为 20/2 个 caller-local pair。runner 的 10 个 `_release_descriptor_owners_or_raise` 外部调用点全部显式展开同参数 caller-local `try/finally`，新增 query-source profile/trace call-entry、first-success/second-call、actual-close ABA 与精确 caller-distribution AST gate。Flow reconciliation 现在要求完整 raw `growth_candidates` 与 `candidate_dispositions` 精确双射：missing/duplicate 为 `ARTIFACT_UPSTREAM_INVALID`，phantom 为 `ANALYSIS_DANGLING_FACT_REFERENCE`。fixture classes 目录在 pinned cache-root dirfd 内创建后以 `O_DIRECTORY|O_NOFOLLOW` pin/rebind，只允许 `fchmod(fd)`；javac `-d` 使用仍存活的 `/proc/<helper-pid>/fd/<classes-fd>` capability，source/classes fd 同时进入 `pass_fds`，build 前后和 cleanup 均验证 captured identity，swap substitute 的 mode/bytes 保持不变。四个核心文件门为 `272 passed, 1 skipped, 133 subtests passed`，合并 focused 门为 `316 passed, 5 skipped, 138 subtests passed`；最小真实 JAX-RS CodeQL 为 `1 passed in 24.91s`，全新 project-local TMPDIR 强制重建 classes/DB 的 Netty formal full（real CodeQL + bounded in-memory mock Responses transport）为 `1 passed in 663.59s`。24 对 direct/embedded query mirror、`compileall`、release AST 与 `git diff --check` 通过。production fingerprints 轮换为 entries-v12、growth-v24、flows-v16、lifecycle-v9、conclude-v4；formal resume 冻结 entries pre-v12、growth v5-v23、flows v3-v15 与 lifecycle pre-v9。本轮未调用 provider，未启动 PoC-33/178/205 batch。
- 闭合 transferred long-lived `ExecutionDatabaseBinding.parent_descriptor` 的最后三处 direct release caller-entry 中断窗口：factory exception 的 cleanup-success/cleanup-failure 两个分支与 `cleanup_execution_database_snapshot()` 最终释放均显式展开同参数 `_release_database_descriptor_must_reach` lexical `try/finally` pair。即使 `cleanup_state.closed` 已先置 true，profile/trace/helper-call 或真实 `SIGINT` 在首调用入口打断，第二调用仍消费 persistent transaction；first-success 或 actual-close-then-exception 后第二调用不重关 ABA 复用 fd。新增 direct-release 3 pair/6 call AST gate、cleanup call-entry profile/trace、SIGINT+repeat cleanup、两条 post-transfer factory exception 与 ABA 回归；目标 RED 为 `7 failed`，最小 GREEN 为 `6 passed`。snapshot suite 为 `100 passed, 90 subtests passed`，focused gate 为 `213 passed, 115 subtests passed`，最小真实 JAX-RS CodeQL 为 `1 passed in 27.71s`；24 对 mirror、module AST、`compileall` 与 `git diff --check` 通过。production fingerprints 轮换为 entries-v11、growth-v23、flows-v15、lifecycle-v8、conclude-v4；formal resume 冻结 entries pre-v11、growth v5-v22、flows v3-v14 与 lifecycle pre-v8。未调用 provider，未启动 PoC-33/178/205 batch，未重复 Netty 长测。
- 闭合 database descriptor owner-release helper 的 caller 入口异步中断窗口。`dosweb/codeql/database.py` 全部 21 个 owner release 点都在持有 owner/transaction 的 lexical layer 显式展开同参数 `try/finally` 双调用；双 fd 路径继续以 peer nested `finally` 为外层、每个 owner lexical pair 为内层。第一次 helper call/first-line 被 profile、trace 或真实 `SIGINT` 打断时，第二次调用仍释放 owner；第一次已成功或 actual-close 后抛异常时，persistent transaction/空 owner 使第二次调用不重关 ABA 复用 fd。新增 call-entry、SIGINT、first-success/second-call、actual-close ABA 与全模块 AST pair gate；目标 RED 为 `6 failed`，最小 GREEN 为 `5 passed`。snapshot suite 为 `94 passed, 88 subtests passed`，focused gate 为 `207 passed, 113 subtests passed`，最小真实 JAX-RS CodeQL 为 `1 passed in 25.69s`；24 对 mirror、module AST、`compileall` 与 `git diff --check` 通过。production fingerprints 轮换为 entries-v10、growth-v22、flows-v14、lifecycle-v7、conclude-v4；formal resume 冻结 entries pre-v10、growth v5-v21、flows v3-v13 与 lifecycle pre-v7。未调用 provider，未启动 PoC-33/178/205 batch，未重复 Netty 长测。
- 将 `dosweb/codeql/database.py` 的 descriptor ownership 全域收口，不再只修 factory 两个 fd。metadata bounded read/hash、`_tree_root_identity`、`_validate_safe_tree` root/递归 file+directory child、private binding、reflink file/root/递归 source+destination，以及 stale/private cleanup parent/root/child 全部改为 `open_owned_descriptor` + open 前预分配 `DeferredCloseFdOnceOutcome` + must-reach owner release；双 fd 路径使用 nested `finally`，一个 release 失败也不会跳过 peer。binding 路径复用既有 capability，standalone 入口在首个 fd 前 probe；shared owned-open primitive 新增 `mode` 透传以支持 `O_CREAT` reflink destination。`database.py` AST 现为 direct `os.open/os.close` 0，真实 syscall 仅保留在 `dosweb/filesystem.py`。root identity profile/trace/SIGINT、validation/clone recursive child 与 cleanup child RED 为 `6 failed, 2 passed, 3 subtests passed`，目标 GREEN 为 `5 passed, 6 subtests passed`；迁移后 snapshot suite 为 `89 passed, 86 subtests passed`。production fingerprints 轮换为 entries-v9、growth-v21、flows-v13、lifecycle-v6、conclude-v4；formal resume 冻结 entries pre-v9、growth v5-v20、flows v3-v12 与 lifecycle pre-v6。最终 focused gate 为 `192 passed, 1 skipped, 111 subtests passed`；最小真实 JAX-RS CodeQL 为 `1 passed in 24.59s`；24 对 mirror、module/factory AST、runner absence、`compileall` 与 `git diff --check` 通过。未调用 provider，未启动 PoC-33/178/205 batch，未重复 Netty 长测。
- 闭合 execution-snapshot spec re-review 的两个 owner gap。descriptor owner release 不再先 `owner.pop()`：先保留 slot 读取 fd，执行 persistent close transaction，只有 transaction 明确 consumed/released 后才在独立 deferred-interrupt window 校验并清 slot；clear setup/restoration 逃逸后，outer cleanup 复用同一 committed transaction 只清 owner，绝不重关已 ABA 复用的 fd number。factory 也删除 capability/owner 之前的 `_tree_root_identity(output)` 裸 open：第一个 output-root open 现在就是 retained-parent `open_owned_descriptor`，其 `fstat` 为 authoritative identity，并与 no-follow lexical `lstat` 绑定；stale cleanup 继续复用同一 parent fd。profile/trace、真实 SIGINT、clear-before/after escape 与 ABA、AST/runtime RED 为 `8 failed, 3 passed, 4 subtests passed`，目标 GREEN 为 `9 passed, 14 subtests passed`，完整 snapshot suite 为 `84 passed, 80 subtests passed`。production fingerprints 轮换为 entries-v8、growth-v20、flows-v12、lifecycle-v5、conclude-v4；formal resume 冻结 entries pre-v8、growth v5-v19、flows v3-v11 与 lifecycle pre-v5。最终 focused gate 为 `187 passed, 1 skipped, 105 subtests passed`；最小真实 JAX-RS CodeQL 为 `1 passed in 25.29s`；24 对 direct/embedded mirror、factory AST、runner absence、`compileall` 与 `git diff --check` 通过。未调用 provider，未启动 PoC-33/178/205 batch，按 review 决策未重复 Netty 长测。
- 闭合 execution-snapshot factory 的 `os.open` C-return→caller assignment descriptor leak：retained parent 与 snapshot-root 两个 acquisition 都在打开前预留 structural owner slot，并复用 shared `open_owned_descriptor` 在 trace/profile 与 `SIGINT` deferred window 内完成 slot 写入；完整 binding/owner callback 建立后才原子转移 parent ownership。profile/trace、真实 SIGINT、actual-close-then-exception 与 fd-number ABA 回归先为 `3 failed, 1 passed, 1 subtest passed`，修复后 snapshot suite 为 `80 passed, 76 subtests passed`；factory AST gate 确认 0 个 direct `os.open`、2 个 owned acquisitions。相邻 stale-cleanup/private-tree walkers 不参与 factory pre-return 的长期 binding ownership transfer，且其递归删除不变量需要独立 RED，故本轮未做无测试的全域重构。production fingerprints 轮换为 entries-v7、growth-v19、flows-v11、lifecycle-v4、conclude-v4；formal resume 冻结 entries pre-v7、growth v5-v18、flows v3-v10 与 lifecycle pre-v4。
- 闭合 P0 batch maturation 的全域一致性缺口：aggregation 现在要求完整 raw `growth_candidates` 与 `candidate_dispositions` 精确一一对应；missing、duplicate、phantom disposition 均将 target 标为 malformed，不再允许未处置 raw Growth 或脱离 raw domain 的处置记录进入 aggregate。对应 RED/GREEN 覆盖三类异常与正常 exact bijection。
- 闭合 fixture source capture 的无界排序与 cache-root chmod TOCTOU：`_bounded_java_sources()` 先 streaming 消费 `os.scandir(fd)` 并执行全局 65,536-entry bound，再只对已 bounded entries 按 encoded name 排序；`_prepare_cache_root()` 改为 lexical parent dirfd 上的 `mkdirat/statat/openat(O_DIRECTORY|O_NOFOLLOW)`，验证 type/uid/link/inode 后仅 `fchmod` pinned root fd，并最终重绑 fd、parent-relative name、lexical name 与 parent。外部 substitute inode 的 bytes/mode 保持不变。
- 闭合 runner `.generations`、query snapshot、BQRS/decoded output 的 path-chmod TOCTOU：共同 helper 通过 parent dirfd + `O_NOFOLLOW` pin leaf，校验 type/uid/link/inode/size 后只执行 fd-relative `fchmod`，并重绑 fd/name/lexical/parent；`dosweb/codeql/runner.py` 不再存在 direct `os.chmod`/`Path.chmod`。失败统一 fail closed 为 `CODEQL_QUERY_FAILED`。
- 闭合 query/execution-snapshot descriptor async close must-reach：`run_query()` 在任何 query-source/output owned fd 前探测 close-once capability；runner local owners、snapshot root 与长期 snapshot-parent fd 使用预分配 mutable transaction、deferred-interrupt release、post-action close commit 与 no-retry ABA 语义。`ExecutionDatabaseBinding` 持有 `close_capability`/`parent_release`，重复或并发 cleanup 不会再次关闭已消费或复用的 fd number。该轮 fingerprints 曾轮换为 entries-v6、growth-v18、flows-v10、lifecycle-v3、conclude-v4；已由本日更晚的 structural-acquisition 修复再次轮换。
- I1-I5 focused gate：`180 passed, 1 skipped, 97 subtests passed in 3.05s`。本轮未调用 RightAPI provider，未启动 PoC-33/178/205 batch，未删除共享 `.test-tmp/` 或任何保留资产。
- 当前 worktree 的网络无关宽门在允许 `127.0.0.1` mock HTTP、排除 linked worktree 未挂载的四个保留资产测试文件后为 `1258 passed, 36 skipped, 792 subtests passed in 69.24s`；从主仓库读取这些未修改测试/保留资产并强制 import 当前 worktree 代码的补充门为 `37 passed, 2 failed in 625.44s`。两项剩余失败分别是历史 schema-2.0 Entry archive 使用当前 exact registration-pattern `FrameworkCoverage` 解析，以及 query-pack/fingerprint 轮换后仍断言旧 PoC-29 plan digest；按 v2 禁止恢复 legacy compatibility 的边界未盲修。最小真实 JAX-RS CodeQL query 为 `1 passed in 25.83s`；fresh project-local TMPDIR 的 Netty production E2E（real CodeQL + bounded in-memory mock Responses transport）为 `1 passed in 641.81s`。`compileall`、24 对 direct/embedded query byte identity、runner 无 direct path chmod/`os.close`、`git diff --check` 均通过。

## 2026-09-01

- 消灭 fixture snapshot/DB 的 conditional directory publication。reviewer 在 source identity check→`renameat2` 窗口把 checked temporary root 换成 current-uid substitute，旧实现确实让 substitute 短暂获得共享 `<digest>.sources` 正式名，post-check 只能事后 retention；source/DB alias hook 与 fresh-process RED 初始为 `3 failed`，candidate invalid/count/root-scan RED 为 `4 failed`，unbounded sorted candidate-tree validation RED 为 `1 failed`，legacy alias/staging cleanup-name RED 为 `2 failed, 1 passed, 2 subtests passed`。cache domain 升至 v5：source 从首次创建即使用 `<digest>.sources-<128-bit-nonce>` 最终唯一名，pin/materialize/validate/chmod 后永不 rename；CodeQL 直接创建 `<digest>.db-<128-bit-nonce>` 且移除 `--overwrite`，DB 同样永不 rename 到 digest alias。digest lock 内以 pinned streaming cache-root scan 限制 4,096 entries/每 digest 8 candidates，source full-tree validation 改为 65,536-entry 两遍 streaming count+validation；全部 exact candidate 与 DB provenance 均验证，invalid/malformed 不 mutate，多个 valid 按 lexical bytes 稳定选择；旧 `<digest>.sources`/`<digest>.db` alias 与 `.sources.tmp-*`/`.db.tmp-*` staging names 连 cleanup legal-name 都不再接受。两个 fresh Python process 复用同一随机 source/DB path 且只 build 一次；fixture GREEN 为 `31 passed, 4 subtests passed`，focused 为 `185 passed, 12 skipped, 133 subtests passed in 8.64s`。fresh project-local TMPDIR 的真实 Netty production E2E（real CodeQL、mock Responses transport）为 `1 passed in 678.84s`；随后第三个 fresh process 在零新增 DB candidate 下复用同一随机 source/DB path。`compileall`、24 对 direct/embedded mirror、no-publication/`--overwrite`/legacy-alias absence gate 与 `git diff --check` 通过。failure cleanup 的 no-delete retention 仍保留，但正常消费路径不再创建 `<digest>.sources`/`<digest>.db` alias；formal artifacts 与 production fingerprint 不变。
- 收紧 final quality review 修复的保证边界：snapshot 只保证 root/descendant 成功 pin/rebind 后的 authoritative mutation/materialization 为 descriptor-relative，附加 lexical validation 可 `O_NOFOLLOW` reopen 后重新绑定；不再声称原子捕获 `mkdtemp` 创建 inode，也不把 same-uid `mkdtemp→pin`、`mkdirat→openat` substitution window 包装成 hard creation-identity guarantee。digest lock 的 post-`flock` rebind 只关闭进入 critical section 前的 name-substitution window；named flock 只串行 cooperating helpers，不保证抵御 same-uid post-entry lock-name replacement。对应 hard guarantee 需要 credential/mount isolation 或更强 filesystem primitive；实现与测试未改变。
- 闭合 final quality review 的五个 Important。fixture snapshot/DB publication 由普通覆盖式 `os.rename` 改为 pinned cache-parent dirfd 上的 `renameat2(RENAME_NOREPLACE)`；snapshot 与 DB 两条 racing empty-directory held-fd RED 均证明旧实现把 unknown inode `nlink 2→0`（`2 failed`），现 `EEXIST` 只允许 strict revalidate/reuse 或 fail closed，GREEN 为 `2 passed`。`mkdtemp` snapshot root 在成功 `O_DIRECTORY|O_NOFOLLOW` pin/rebind 后，authoritative materialization/chmod/publication binding 改为 pinned/root-relative fd，附加 lexical validation 可 no-follow reopen/rebind；mode-`0000` post-pin substitute RED 证明旧实现把 unknown root 改成 `0500` 并写入，现该 substitute 保持 `0000`/empty（`1 passed`）。digest lock 改为 pinned parent-dirfd `O_EXCL` create-or-open：existing inode 必须预先通过 type/uid/nlink/`0600` gate，仅新建已验证 inode允许 fchmod，`flock` 后重验 lexical name→locked inode；pre-entry nested-second-lock swap RED 从 `1 failed` 变为 `1 passed`。Flow 对 links/dispositions/growth candidates/verified Growth 全部先做 strict `validate_records`，inventory/rejected 也必须属于完整 raw Growth domain，formal/gap 继续额外要求 retained Growth；unexpected-field/phantom RED 为 `3 failed, 1 passed, 2 subtests passed`，GREEN 为 `2 passed, 4 subtests passed`。`normalize_flow_rows()` 对任意重复 `path_id`（含 byte-identical）在 map insertion 前稳定 fail closed，正反 CodeQL 行序 RED 为 `4 failed`、GREEN 为 `1 passed, 3 subtests passed`。flows fingerprint 升至 v9并冻结 v3..v8；README、唯一 spec 与 version test 已同步。fixture 为 `22 passed`，focused 为 `176 passed, 12 skipped, 129 subtests passed in 8.31s`；fresh project-local TMPDIR 的真实 Netty production E2E（real CodeQL、mock Responses transport）为 `1 passed in 646.09s`。
- 闭合 deliberate-retention cleanup 的 cache-root namespace inventory 漂移缺口。独立 reviewer 指出 global flock 只串行 cooperating helper cleanup，不能阻止其他 cooperating helper 在 `_retained_cleanup_usage()` 的 `scandir(fd)` 期间改变 cache-root namespace；deterministic transient add/remove RED 为 `1 failed`，旧实现会接受可能漏项的 observed count budget。helper 现在在完整 cache-root inventory 前后比较 pinned dirfd 的 stable identity，任何 namespace/metadata drift 均以 `fixture cleanup cache root changed during retention inventory` fail closed；目标 GREEN 为 `1 passed`，完整 fixture 为 `18 passed`，focused 为 `169 passed, 12 skipped, 122 subtests passed in 8.40s`。README 与唯一 spec 已同步；不改变 build/query 路径、formal artifacts 或 production fingerprint。
- 闭合 final fixture cleanup 两轮 re-review 的 root/child/final-delete TOCTOU。第一条 deterministic RED 在 `_make_helper_tree_writable()` final check 返回后把 original root 移到 held path、让 outside tree 占据合法名称，证明旧裸 `shutil.rmtree(path)` 会删除 substitute（`1 failed`）。改为 root quarantine 后，独立 reviewer 又在 child current-stat→`unlink` 与 final root rebind→`rmdir` 窗口稳定换入 outside inode：删除 syscall 已使 outside `nlink 1→0`/directory `nlink 2→0`，事后 fstat 只能报错，不能撤销；新增 child destructive-call、retention count/aggregate-size、final cache-fstat fd-leak 四条真实 RED 为 `4 failed`；另以 quarantine-before-root-hardening 顺序门证明旧次序仍在合法名上遍历（`1 failed`）；reviewer 随后把 outside `0400` inode 在 retained-root scan 窗口注入，旧 descendant `fchmod(fd,0600)` 已把 unknown inode 改成 `0600` 才因 directory drift 报错，injected-mode 与 global-lock 两条 RED 各为 `1 failed`；最后用 preexisting legal-name outside substitute root 锁定 root-only fchmod 仍会把 unknown root `0500→0700`（`1 failed`）。同 uid 持有 parent/root dirfd 的模型下不存在 inode-conditional unlink/rmdir，故最终实现彻底移除 cleanup 的 `unlink`、`rmdir`、destructive recursive traversal/deletion 与 lexical `shutil.rmtree`。helper pin owner-only cache-root dirfd，先以 `renameat2(RENAME_NOREPLACE)` 把 exact current legal root 原子隔离为可审计 `.<legal>.retained-<dev>-<ino>-<nonce>`；identity mismatch 仅在无歧义时 no-replace 回滚 substitute，否则保留 private quarantine并失败；exact quarantine 与 descendants 全部 no-follow read-only inventory、final file/name/root recheck，任何 mode 均保持不变，然后 deliberate retain the subtree behind the owner-only `0700` cache-root boundary，释放原 legal name 供后续 build 使用。`0600` global cleanup flock 串行 cooperating helper cleanup；no-follow inventory 的 observed admission budget 为 64 tombstones、1 GiB aggregate logical `st_size`、65,536 entries/depth，达到 count 或超过 size/entry/identity/type/owner/link contract 时 fail closed，新隔离 exact root 只有无歧义时才回滚。该 budget 明确不是对 same-uid held-fd/name mutation 的 filesystem hard quota；自动路径不 mutate/delete unknown inode；人工回收仅允许全部 fixture process 退出后从 dedicated TMPDIR 的外部 quiescent boundary 删除整个 cache root。final cache-root fstat 即使异常也由嵌套 finally 关闭 fd。fixture 为 `17 passed`，focused 为 `168 passed, 12 skipped, 122 subtests passed in 8.38s`；README 与唯一 spec 已同步；该 cache 只含 artificial fixtures、不含 formal target bounded slices，不改变 formal artifacts 或 flows-v8 fingerprint。此前 retention 前 fresh Netty production E2E 已以全新 project-local TMPDIR 强制重建 DB/classes 并通过（`1 passed in 637.40s`）；本轮只改变失败 cleanup 的 no-delete retention，不改变构建/query 路径，按 review 决策不重复第三次长测。`compileall`、24 对 direct/embedded mirror、no-delete/retained-tree-chmod absence gate 与 `git diff --check` 通过。
- 闭合 final fixture cleanup spec re-review 的 symlink-swap Important。旧 `_make_helper_tree_writable()` 在 `entry.stat(follow_symlinks=False)` 后调用 `child.chmod()` 重新解析路径；deterministic RED 在两者之间把合法 `Fixture.java` 换成 outside symlink，outside bytes 未变但 mode 从 `0400` 被错误改为 `0600`（`1 failed`）。cleanup 现从 exact helper root 开始全程使用 pinned dirfd：每级 directory 以 parent dirfd + `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC` 打开，文件以 parent dirfd + `O_NOFOLLOW` 打开，并在 `fchmod(fd,0600)` 前验证 discovered/opened identity、current uid、regular type 与 `nlink=1`；child directory/root 仅通过已打开 fd postorder `fchmod(0700)`，lexical root 最后必须仍绑定 pinned inode。symlink、identity drift、foreign/special/hardlink node 只会安全失败，绝不 follow 或 chmod target；RED 现 GREEN，fixture 为 `8 passed`。README、唯一 spec 已同步；仅 test-cache cleanup 变化，formal artifacts 与 flows-v8 fingerprint 不变。最终 focused 为 `159 passed, 12 skipped, 122 subtests passed in 8.31s`；使用全新 project-local TMPDIR 强制重建 fixture DB/classes 的 Netty production E2E 为 `1 passed in 654.53s`。
- 闭合 fixture immutable snapshot spec re-review 的最后一个 Important。shared `.sources` 旧实现虽然复制了 bytes，却以 `0700/0600` 可写发布，CodeQL build 仍使用 mutable lexical path；published root A→B→A 与 transient `Missing.java` add/remove 两个真实 RED 均被旧实现 accepted（`2 failed`）。snapshot cache domain 升至 v4，发布前把 dirs/files 降为 owner-only read-only `0500/0400`；build 以 `O_DIRECTORY|O_NOFOLLOW` root fd pin 住 capability，subprocess 使用 `/proc/self/fd/<fd>` cwd + `pass_fds` + `--source-root=.`。build 前、subprocess 后与 final publication 逐次要求 lexical binding、pinned root 及 exact full-tree inode/owner/mode/size/mtime/ctime/bytes/no-extra state 不变；中途关闭原 fd 后先验证 DatabaseInfo provenance，再 reopen/rebind 同一 state，排除持久 metadata 依赖活跃 `/proc` alias。任一 drift 清理 temp/final DB 与 classes；read-only source cleanup 先 owner chmod、拒绝 foreign node、再无 symlink-follow 删除。fixture GREEN 为 `7 passed`。真实 CodeQL v4 build 将 `sourceLocationPrefix` 固化为 stable `.sources` absolute path，关闭 fd 后跨进程复用仍通过且模式保持 `0500/0400`。这是 test harness/cache 修复，不改变 formal artifacts，production flows-v8 fingerprint 保持不变。最终 focused 为 `158 passed, 12 skipped, 122 subtests passed in 8.39s`；fresh Netty production E2E 为 `1 passed in 635.66s`。
- 闭合 final re-review 剩余两个 Important。fixture helper 旧实现虽然重算 source identity，却仍以原 fixture root 作为 CodeQL/javac `cwd` 与 `--source-root`，subprocess 窗口内整树 A→B→A 或 transient `*.java` add/remove 仍可能污染数据库；两个真实 RED 为 `2 failed, 1 passed`。helper 现在通过 root/dir/file descriptor、`O_NOFOLLOW` 与前后 stable identity 捕获最多 4096 文件、单文件 4 MiB/总计 64 MiB 的冻结 bytes snapshot，限制 tree/path bytes/parts，只向跨进程复用的 owner-only content-addressed `.sources` 原子发布 exact Java tree；per-digest `0600` flock 串行化 snapshot/DB reuse，复用前严格校验 owner/mode/bytes/无额外节点，CodeQL/javac 仅消费 private snapshot，temp source/DB/classes 失败清理，production E2E provenance 改用 `database.source_root`。后续自审又以两条独立真实 RED 锁定 source/DB rename 后 publication validation 失败的残留，失败路径现同时删除 helper-owned final/temp source、DB 与 classes；fixture GREEN 为 `5 passed`。Flow loader 原先对同一 `growth_id` 的多条 `verified_growth` last-write-wins；正序、反序和 byte-identical duplicate RED 为 `3 failed, 1 passed`，现在 materialize 后先检查 Growth ownership 唯一性，统一以 `ARTIFACT_UPSTREAM_INVALID` fail closed。flows fingerprint 升至 v8，formal resume 冻结 flows-v3..v7，README、唯一 spec 与 version test 同步。最终 focused 为 `156 passed, 12 skipped, 122 subtests passed in 8.35s`；fresh shared-cache/private-snapshot Netty production E2E 为 `1 passed in 650.26s`。
- 闭合 final quality re-review 的 fixture build-window TOCTOU 与 non-retained Flow disposition 缺口。fixture cache 虽已 content-addressed，但 CodeQL subprocess 期间源码 A→B→A 时，旧实现会把 B 构建的 DB 以 A key validate/缓存；恢复时序真实 RED 为 `1 failed`。bounded snapshot 现在除 relative path+bytes 外还绑定 dev/inode/mode/size/mtime/ctime，单文件读取前后校验 stable identity；新建 DB 在 validate 前和 return 前均重算 exact snapshot，任何变化都安全删除该 helper-owned DB/classes 并 fail，不进入 LRU。Flow v6 又仅对 retained candidates 比对 association/link status，会放过 non-retained inventory one-link status mismatch，也会忽略不在 `verified_growth` 的额外 formal/gap disposition；真实 RED 为 `3 failed, 1 passed`。reconciliation 现先对全部 disposition 强制 complete/partial 唯一 link status/Entry 一致、missing 无 link/canonical Entry、ambiguous 无 canonical single-link shape，然后要求全部 formal/gap Growth 必须在 retained results；inventory/rejected 可不 retained，但 ownership/status 仍必须完整一致。flows fingerprint 升至 v7，formal resume 冻结 flows-v3..v6，README、唯一 spec、version tests 同步。mutation cache 回归为 `2 passed`，full reconciliation 定向门为 `4 passed, 4 subtests passed`，focused 为 `152 passed, 12 skipped, 119 subtests passed in 8.20s`，重建稳定身份 DB 后的真实 Netty production E2E 为 `1 passed in 670.18s`。
- 闭合 final quality review 的 stale fixture DB 与 Netty canonical Flow 两个 Important。`tests/support/fixture_database.py` 原先仅以 PID+源码路径命名并以路径作 `lru_cache` key，同进程修改 fixture 后仍复用 stale CodeQL DB；source-mutation 真实 RED 为 `1 failed`。fixture helper 现在受限地读取最多 4096 个 Java 文件、单文件 4 MiB/总计 64 MiB，cache identity 绑定 resolved source root、sorted relative paths+bytes 与 CodeQL/javac file identity；源码变化必然选择新 DB path，旧 DB 不会复用。Flow 阶段原先把 Growth 已 canonicalize 的 Netty handler-base 或 route-specific link 按 raw source location 重新展开为 base/`/beat`/`/trigger` 三条 partial；完整 executor 真实 RED 为 `3 failed, 1 passed`。新 generic reconciliation 先对 authenticated `candidate_entry_links`/`candidate_dispositions` 的 eligible 与 non-eligible 所有 ownership 做 duplicate/dangling/Growth/Entry/status 严格校验，再以唯一 `growth_id -> canonical_entry_id` 约束 formal 与 gap Flow normalization；route-qualified 保留 exact alias，handler-base 只发布 base pair，不得先扩 alias 再过滤。flows fingerprint 升至 v6，formal resume 冻结 flows-v3..v5，README、唯一 spec 与 version test 同步。定向 GREEN 为 `14 passed, 4 subtests passed`，focused 为 `149 passed, 12 skipped, 117 subtests passed in 8.34s`，全新 content-addressed DB 的真实 Netty production E2E 为 `1 passed in 638.44s`。
- 闭合 strict loop witness 第三轮审查、G3/G4 proof-carrying demand 缺口与第四轮 shared witness 测试合同归属问题。第三轮真实 RED 证明旧 `growth.getEnclosingStmt()` 逻辑会把 argument、return、throw、conditional RHS 与 body 内 bound mutation 五类 shape 错标为 complete multiplicity；shared `LoopAmplification.qll` 现采用正向白名单：Container/Async 只接受 sole top-level `ExprStmt` 且整个 expression 就是 Growth，Direct 仅额外接受 simple `AssignExpr` 且 RHS 精确等于 allocation，同时禁止 body 对 induction 或 attacker bound 的 assignment/`++`/`--`。request-local exact Map/List candidate 新增同 site `iteration_count` driver，async exact loop 以 receiver `getASourceSupertype*()` 同时识别声明于 `Executor` 的 `execute` 与 generic `ArrayBlockingQueue<byte[]>`，并输出 complete `submission_count`；Flow domain 复用同一 canonical witness 携带两类 count demand。真实 Growth→Association→Flow→candidate association→relevance→maturation 链对 G3/G4 均达到 complete/formal-eligible，未手造 link。Growth/flows fingerprints 升至 v17/v5，formal resume 冻结 growth-v5..v16 与 flows-v3..v4；README、唯一 spec、version tests 和 direct/embedded mirrors 同步。第四轮精确 RED 为 `3 failed, 1 passed, 36 subtests passed`：`tests/test_codeql_growth_queries.py` 错把 induction `int`、`PostIncExpr` 与 `PreIncExpr` 三个 shared witness 实现 marker 归给 `ContainerGrowth.ql`；测试合同现改为在 `LoopAmplification.qll` 断言这三个 marker，Container query 仅断言 `import LoopAmplification` 及 canonical/shared witness 调用。精确 GREEN 为 `1 passed, 40 subtests passed in 0.14s`，第四轮 focused 为 `65 passed, 12 skipped, 105 subtests passed in 0.27s`。fresh Direct shape gate 为 `2 passed, 9 subtests passed in 41.14s`，完整 Direct edge 为 `5 passed, 11 subtests passed in 221.50s`，最终 G3/G4 真链为 `1 passed, 2 subtests passed in 179.34s`，G1–G4 为 `1 passed, 9 subtests passed in 387.46s`，focused contract/version 为 `65 passed, 12 skipped, 105 subtests passed`，P0 exact E2E 为 `1 passed, 2 subtests passed in 657.72s`；`compileall`、direct/embedded mirrors、`git diff --check` 与 fingerprint/stale-semantics 门通过。
- 闭合 DirectAllocation 第二轮 spec re-review 的 Critical+Important。`Flows/EntryGrowthDomain.qll` 原先仍只读 `getDimension(0)` 且没有 loop-count demand，导致 Growth 已识别 `width/count`，真实 Association/Flow 却各为 0 matching row，candidate 只能靠 source-order partial，不能形成 formal link；旧 `attackerControlsLoop` 又只证明条件受输入影响，会把带 `break` 的 canonical-header loop 误标 complete，并漏掉 nested lambda/anonymous-callable 的 multiplicity gap。新增真实 RED 覆盖 multi-dimensional size、fixed allocation loop iteration count、break、server cap、nested lambda 与 nested callable，并把完整链锁为真实 Growth→Association→Flow→`_candidate_association`→`_mature_disposition`，测试禁止手造 complete link。`Growth/LoopAmplification.qll` 现集中定义 strict shared witness：仅接受 exact `for (int i = 0; i < directAttackerIntParameter; i++|++i)`、zero init、唯一 update、body 不写 induction、same-callable 且唯一 top-level unconditional growth statement；其他 attacker-dependent/lexically enclosing loop 一律 partial/unmodeled。Direct/Container/Async Growth 与 Flow 共用该 witness；Flow 同时以 `getADimension()` 携带全部 array-size demand，并以 exact bound access 携带 `iteration_count`。Growth/flows fingerprints 分别升至 v16/v4，formal resume 冻结 growth-v5..v15 与 flows-v3；README、权威 spec、version tests 和 direct/embedded mirrors 同步。真实 unsafe edge 为 `1 passed, 4 subtests passed in 14.93s`，真实 proof-carrying maturation 为 `1 passed, 2 subtests passed in 131.36s`，既有 multi-dimension/safe-loop/unmodeled-loop 为 `3 passed in 46.63s`，G1–G4 为 `1 passed, 9 subtests passed in 234.21s`，focused 为 `74 passed, 9 skipped, 95 subtests passed`，P0 exact E2E 为 `1 passed, 2 subtests passed in 649.21s`；`compileall`、七个 direct/embedded query mirrors、`git diff --check` 与 fingerprint/stale-semantics 门均通过。
- 修复 DirectAllocation 对多维数组与 loop multiplicity 的两类 false negative。真实 edge fixture 的初始 RED 为 `3 failed in 49.47s`：query 只读 `getDimension(0)`，会把 `new byte[1][width]` 错归为 fixed；loop 内 `new byte[1]` 又因 expression-parent containment 无法跨到 statement body，既不输出 attacker-controlled iteration witness，也不标记 unresolved loop gap。direct/embedded query 现用 `getADimension()` 枚举全部显式维度，并以 `loop.getBody().getAChild*() = allocation.getEnclosingStmt()` 建立 enclosing-loop 关系：exact attacker bound 输出 complete `allocation_loop_multiplicity` / `direct_allocation:attacker_controlled_loop_multiplicity_proven`，未建模 bound 输出 partial `direct_allocation:loop_multiplicity_unmodeled`。fixed/server-metadata hard negative 仅在全部 normalized drivers 均属已建模 server-controlled domain 且无 multiplicity obligation 时成立；amplification 对 exact witness 为 `proven`、对 loop gap 为 `unknown`。Growth fingerprint 升至 v15，README、权威 spec、resume tests 与 direct/embedded mirror 同步。fresh 真实 edge query 为 `3 passed in 134.73s`，focused regression 为 `68 passed, 7 skipped, 41 subtests passed`，真实 P0 E2E 为 `1 passed, 2 subtests passed in 676.57s`。
- 修复真实 CodeQL production fixtures 的两个 candidate maturation 断点。Netty source-switch Entry 先用 `entry>netty_json_switch>async>service>growth` call path 中的 exact route 过滤 alias，普通 same-handler path 则只在 handler/installation/security/input identity 全等且状态一致时收敛到 exact `netty_pipeline_registration` base Entry；`request.content().toString(...)` 与 `/trigger` service-chain field growth 不再因 generic/`/beat`/`/trigger` 三路 Entry fanout 降为 inventory。DirectAllocation direct/embedded query 将 `CompileTimeConstantExpr` size 建模为 complete `server_controlled_fixed_size`，relevance 以 typed server-controlled source negative proof 在 finding 前拒绝 P0 fixture 的 `new byte[1]`，不再把确定性常量 allocation 留作 `size_origin_unclassified`。Growth fingerprint 升至 v14。最小 RED 为 Netty association `2 failed`、fixed relevance `1 failed`、query marker `1 failed`；GREEN 分别为 `2 passed`、`1 passed`、`1 passed, 32 subtests passed`，真实 P0 DirectAllocation query 证明 lines 36/115 均为 complete fixed-size negative，direct/embedded query byte-identical。真实 P0 E2E 还暴露旧 expected set 未同步 one-shot async relevance 语义；fixture 现精确保留 `/executor`、`/finite`、`/async-consumer` 的 `async_work_growth` finding，并断言在 capacity/synchronous-release proof 未闭合时只能为 `static_unknown`，不得为追求旧结果而删掉新增候选。最终真实 Netty fixture 通过，修正后的 P0 fixture 为 `1 passed in 661.55s`；相关单元门为 `29 passed, 3 skipped, 10 subtests passed`，`compileall`、query mirror 与 `git diff --check` 均通过。
- 闭合上述 fixture 修复的 spec review。DirectAllocation 多维 rows 会按同一 site/resource 归一，fixed/server-metadata hard negative 现仅在 complete candidate 的全部 normalized notes 都属于已建模 server-controlled domain 时成立；`new BufferedImage(width, 1, ...)` 的 attacker-controlled width 不再被 fixed height note 吞掉，任何 attacker-backed、unclassified、partial 或 attacker-controlled multiplicity note 都禁止生成 `server_controlled_source` proof。真实临时 CodeQL fixture 证明 width/fixed 两 rows 归一后仍为 `contract_eligible`。Netty base canonicalization 新增 handler、registration site、Auth、input、materialization 与 link-status 六维负向回归，任一不一致均保持 ambiguous inventory。README、权威 spec 两处及 resume-version tests 同步 growth-v14；P0 真实 E2E 新增 lines 36/115 的 exact complete note、rejected disposition、typed proof kind/reason 与 candidate-evidence ownership 断言。Critical RED 为 mixed dimensions 与 multiplicity 两条 `rejected` 误判，最小修复后 focused 为 `65 passed, 4 skipped, 38 subtests passed`；真实 mixed-dimension CodeQL 为 `1 passed in 21.65s`，P0 production E2E 为 `1 passed, 2 subtests passed in 685.23s`。
- 闭合第五轮 LLM cache cleanup window re-review 的两个 Important，并把同构动作收敛到 centralized retirement。hierarchy walker 的 previous handoff、child unwind、outer finally 与 unsafe regular-file rejection 不再裸 `os.close` unregistered fd，全部走 `_close_unregistered_descriptor()`：显式 PRE close 只执行一次 `closerange(fd, fd+1)`，POST/ambiguous 不重试；四条 production-path RED 均显示 registry 已空但 `fd_delta=1`，GREEN 为 `4 passed`，并验证后续 hierarchy/file open 正常。后续补齐 unsafe regular-file POST/ABA regression：真实 close 后立即复用同一 fd number 并抛 `KeyboardInterrupt`，replacement 保持可 `fstat`、`closerange` 零调用，清理 replacement 后回到 fd baseline；PRE/POST focused 为 `2 passed`，生产实现无需改动。Growth/Auth publication temporary name 新增 one-shot structural owner，destructive unlink 前先退休 name ownership；成功 link 后 unlink 实际完成再异步逃逸时，outer cleanup 不会按已复用的 mutable name 二次删除竞争 substitute，已发布 authenticated destination 仍可被后续 lookup 消费，ambiguous owner-only temporary 保留并计入容量。两路真实 link+unlink POST/ABA RED 为 `2 failed`，GREEN 为 `2 passed`；最终 path focused 为 `43 passed, 7 warnings`。
- 闭合 LLM cache spec re-review 的两个 cleanup must-reach Important。capacity cleanup 现在把 `_active_flock_is_owned()` 与 unlock 包在 flock retirement 的外层 `finally` 内，即使 ownership predicate 在动作前/后收到异步 `BaseException`，flock PID/token、fd、pinned directory 与 thread-local state 仍全部退休，后续 reservation 可正常执行。Growth/Auth publication outer cleanup 现在用 nested `try/finally` 保证 link 失败后的 temporary-name unlink 在动作前/后被异步打断时，duplicated/opened directory transient owner 仍必达 one-shot retirement；post-close 异常会退休 token 且绝不重试已复用的 fd number。production-path RED 分别为 `2 failed` 与 `4 failed`，最小修复后分别为 `2 passed` 与 `4 passed`；最终 path focused 为 `36 passed, 7 warnings`。
- 闭合 LLM cache code-quality review 的两个 descriptor lifecycle Important。其一，capacity/stripe cleanup 改为 nested must-reach 链：LOCK_UN 的 `BaseException` 仍必达 flock one-shot retirement，flock close 的 PRE/POST 异常仍必达 pinned directory retirement；PID/object token 保持登记到 close action 完成，显式 `CloseRangePreActionError` 仅在 fork guard 内执行一次 `closerange(fd, fd+1)` fallback，post/ambiguous close 异常退休 token 后绝不重试可能复用的 fd number。其二，新增 process-global `_ACTIVE_TRANSIENT_FDS`，把 transaction 内 cache-directory duplicate/open、Growth/Auth entry 与 publication temporary fd 全部纳入 fork guard 下 acquire→register / unregister→close；temporary publication 改为 tracked descriptor + bounded `os.write`，不再把 ownership 转给未登记 file object。child reset 现在关闭所有父线程 inherited active/transient cache capabilities，parent 继续完成真实 Growth/Auth lookup/publication。cleanup fault injection RED 为 `5 failed, 1 passed`、GREEN 为 `6 passed`；duplicate/entry/temporary cross-thread fork production-path RED 为 `3 failed`、GREEN 为 `3 passed`；最终 path focused 为 `30 passed, 7 warnings`。
- 修复 LLM cache spec review 的 fork-child fd ABA 与 relative-path cwd drift 两个 Important，并闭合自审发现的 cross-thread fork lifecycle 及 register/retire window。flock active ownership 现在绑定 allocating PID 与唯一 token；capacity/stripe finally 只有在 current PID registry 仍以同一 token 持有 fd 时才 unlock/close，因此 at-fork reset 后 parent context 的 child-side unwind不会误关复用旧 fd number 的无关文件。active directory state 除 thread-local authority 外同时进入 process-global PID/state-token lifecycle registry，使非持锁线程调用 `fork()` 时 child reset 也能关闭所有已消失 parent threads 的 pinned directory fd；normal end 只退休同 PID、同 state token 的 ownership。统一 fork lifecycle guard 覆盖 directory/flock 的 open→register 与 unregister→close，at-fork before/parent/child hooks 分别 acquire/release/reset，fork 不再能落入未登记已打开或已退登记未关闭窗口。`ContractCache` 构造时只做一次 lexical absolute freeze（不 `resolve` symlink），path key、no-follow walker 与 entry transaction 后续只使用固定路径；事务中切换 cwd、原 cwd 祖先改名后 nested lookup 仍复用 A 的 pinned inode，事务后缺失 frozen path fail closed，不会读取 cwd 下同名 B。原始四条 capacity/stripe fork child unwind+fd reuse 与 cwd-switch+ancestor-rename nested Auth lookup 回归 RED 为 `4 failed`、GREEN 为 `4 passed`；cross-thread stable-state capacity/stripe fork RED 为 `2 failed`、GREEN 为 `2 passed`；capacity/stripe acquire-transfer 与 retire-close 四窗口 RED 为 `4 failed`、GREEN 为 `4 passed`，最终 path 门为 `21 passed, 4 warnings`。review 前 LLM cache/deepseek/Auth/Growth 门为 `236 passed, 2 warnings, 149 subtests passed`；最终 `compileall` 与 `git diff --check` 通过。
- 修复 cross-cache nested capacity 的确定性 self-deadlock Important：`capacity_reservation()` 原先只检查当前 cache path 的 active state；同线程持有 cache A reservation 后请求 cache B 时看不到 A，继而再次 acquire 全局非重入 `_CAPACITY_LOCK` 并永久自锁。现在进入全局锁前枚举当前线程全部 active directory states；只有请求 path 的唯一 reserved state 且 reservation 集合精确等于当前 reservation 时允许 nested 复用，任何其他非空 reservation（包括另一 cache path）立即以 `LLM_CACHE_LOCK_FAILED` fail closed。新增两个不同 `ContractCache` path 与可探测 non-reentrant lock 的 RED，旧实现抛 `WOULD_SELF_DEADLOCK`；GREEN focused 为 `1 passed`，path 门为 `11 passed`，deepseek/cache 门为 `120 passed, 2 warnings, 149 subtests passed`，并断言只 acquire/release 全局锁各一次、active state 与 fd 回到 baseline。
- 修复 active cache transaction nested `dup` metadata/identity validation failure 的 close-once Important：`_open_cache_dir` 原先在 drift 分支显式 `os.close(duplicate)` 后直接 `return`，但 `finally` 仍把同一非空 owner 再 close，一旦 fd number 被复用就可能误关无关 descriptor。失败分支现在只返回，唯一 `finally` owner 负责一次 close；active pinned directory fd 仍由 transaction end 独立关闭一次。新增 post-dup mode drift RED，精确记录 duplicate 与 pinned descriptor 的 close call 数；RED 为 `1 failed`（duplicate `2` 次），GREEN focused 为 `1 passed`，path 门为 `10 passed`，deepseek/cache 门为 `120 passed, 2 warnings, 149 subtests passed`。
- 修复 cache path spec 二次复审的 transaction-directory identity Important：capacity reservation 或 stripe single-flight 原先只在局部持有 directory fd/lock，nested `put`/Auth publication 仍靠 thread-local 字符串 marker 跳过锁后重新 walker；foreign owner 可在锁后把 safe anchor 换成另一 current-owned safe anchor，造成 lock 留在 original、entry 写入 redirect，或不必要 fail closed。现在 active state 结构化保存 thread owner、pinned directory fd、device/inode 与该 inode 上的 reservation membership；同一事务的 Growth/Auth lookup、nested capacity 与 publication 仅使用 pinned fd 或经 metadata+identity 复核的 `dup`，不再把 path/key marker 当 authority。nested same-entry reservation复用同一 state，异 key/stripe 错序拒绝，其他线程不可借用；normal/exception exit 唯一关闭 fd，fork child reset 同时关闭继承的 flock 与 pinned directory fd。新增 capacity-lock 后 Auth anchor substitution、stripe-lock 后 Growth substitution RED，证明 redirect 零 entry/lock且 original lock/entry identity一致；新增 capacity/stripe exception close-once、fork inherited directory fd 与既有并发/process single-flight 回归。RED 为 `2 failed`，GREEN focused 为 `2 passed`，最终 path+cache/deepseek 为 `129 passed, 2 warnings, 149 subtests passed`。
- 修复 foreign readonly ancestor 放宽后的首次 spec review Important：`_create_private_hierarchy` 原先验证 root-to-leaf 后关闭 final fd、只返回 bool，`_open_cache_dir` 随即用 absolute `lstat/open` 重走可变路径，foreign `0755` owner 可在窗口中 swap current-owned anchor 或插入 intermediate symlink，将 `single_flight` lock/create/read 重定向到另一安全外观目录。现在 create 与 read/open 统一走同一 descriptor-relative、逐层 `O_DIRECTORY|O_NOFOLLOW` walker；final exact current-uid `0700` fd 在验证后直接结构化转交 caller，绝不 absolute reopen。新增 create/read intermediate-anchor swap RED，分别证明 redirect 目录不产生 lock、redirect cache/lock 不被读取，并新增 validation exception parent/child fd 零泄漏回归；并发 hierarchy 测试显式验证并释放 transferred fd。RED 为 `2 failed, 6 passed`，GREEN path-focused 为 `9 passed`，沙箱外 loopback cache/deepseek 门为 `126 passed, 2 warnings, 147 subtests passed`；真实 `/home/.../results/java_web_dos_batch` formal cache path smoke、`compileall` 与 `git diff --check` 通过。production 五文件门仍为 `234 passed, 5 skipped, 114 subtests passed, 1 failed`，唯一失败仍是独立的 CodeQL rollback-slot retirement hook 未触发。
- 修复 sandbox 映射下 `/home` 等 foreign-owned `0755` 祖先导致 formal LLM `single_flight` 错报 `LLM_CACHE_UNSAFE`。cache hierarchy 继续 descriptor-relative/`O_NOFOLLOW` 遍历：foreign-owned 且 group/world 不可写的非 target 只允许只读穿越，遇到缺失层前必须先进入现有 current-uid、group/world 不可写 anchor；foreign sticky 仍要求现有 current-uid exact `0700` private anchor。foreign writable non-sticky、symlink、unsafe target 继续 fail closed，target 与 lock/entry 仍分别要求 current-uid exact `0700`/`0600`。新增精确单层 `fstat` owner 模拟、只读祖先 direct-create 拒绝/anchor 后 single-flight 成功、foreign writable/symlink/unsafe target/sticky anchor 回归。RED 为 `1 failed, 5 passed`，GREEN path-focused 为 `6 passed`；沙箱外 loopback cache/deepseek 门为 `123 passed, 2 warnings, 147 subtests passed`，真实 `/home/.../results/java_web_dos_batch` 临时 formal cache path smoke 通过，`compileall` 与 `git diff --check` 通过。production 五文件门当前为 `234 passed, 5 skipped, 114 subtests passed, 1 failed`；唯一失败是共享工作区既有 CodeQL rollback-slot retirement hook 未触发，与本次 LLM cache path 改动独立，未改动该子系统。
- 修复 generic `RENAME_NOREPLACE` capability probe 的 descriptor ownership 与 mutable-name ABA 两个 Important。probe source 创建后立即以 no-follow fd 进入 publication-scope structural owner，正常路径及 PRE/POST release failure 统一走 shared one-shot/local fallback；local 两层 setup 均逃逸时，未退休 slot 继续由 outer `release_owned_state`、unassigned-owner safety tuple 与 allocation-free emergency drain 接管，且不截断其余 publication owners 或 execution lock。probe 成功、pre-action 与 post-action cleanup 均复用 pinned empty-directory cross-dirfd tombstone helper，不再对 mutable source/target 执行 `rmdir`/`unlink`；target stat 后若 original 被移到 competitor、同名空 substitute 被装回，则 original/substitute inode 与 xattr 全部保留并 fail closed，绝不删除或覆盖。新增 descriptor PRE/POST/persistent setup escape 与 target-name ABA RED/GREEN；新鲜 focused 为 `2 passed, 3 subtests passed`，execution snapshot 为 `68 passed, 72 subtests passed`，adapter+production 为 `120 passed, 1 skipped, 26 subtests passed`，五文件门为 `235 passed, 5 skipped, 114 subtests passed`；`compileall`、`git diff --check`、AST publication-owner/tombstone、mutable-name destructive-call 与 raw-close gates 通过，fresh reviewer 对 Critical/Important/Minor 均无发现并批准。
- 修复 exchange-probe descriptor release 的三层连续 setup escape、成功 publication 后最外 entry escape 残留 normal generation，以及 outer action 已完整执行后 restoration exception 又把 valid commit 错翻成失败的后续 Important。probe/generations descriptor 均有 publication-scope structural owner；local 两层均逃逸时 slot 留给最外 finalizer。最外 entry failure 不叠第四个 deferred helper，而先用 live final rollback/rollback-directory/generations anchor 执行 normal rollback、independent recovery 与 force isolation，证明 normal `Entries-*` 不再可消费，再对 probe、decoded/private binding、rollback、pending、generations owners 逐项退休并唯一 raw `closerange`；owner group 以嵌套 `finally` 继续，lock 位于 ultimate `finally`，已消费 owner 不重触 ABA 号。`release_owned_state_completed` 仅在全部 owner/private-binding 决策结束且 lock 已释放后提交；只有它与完整 transaction、clean housekeeping、valid commit、零 release/rollback failure 同时成立时，随后 restoration exception 才分类为 post-action，不再产生“API 失败 + normal consumable generation”。新增 `outermost_setup_escape`、action-before `outermost_post_publication_escape`、action-completed `outermost_post_action_escape` RED/GREEN，并保留双层 persistent、direct trace/fallback/ABA 回归。纯 Python 下不声称持续任意 trace/profile bytecode 原子性。新鲜 focused 为 `2 passed, 10 subtests passed`，execution snapshot 为 `66 passed, 69 subtests passed`，adapter+production 为 `120 passed, 1 skipped, 26 subtests passed`，五文件门为 `233 passed, 5 skipped, 111 subtests passed`；`compileall`、`git diff --check`、structural completion、emergency recovery/drain 与 scoped raw-close gates 通过。
- 修复 internal exchange-probe fd 绕开 deferred one-shot release 的最终 Important。旧 `_isolate_bound_empty_directory_no_replace` 在未传 fd 时自行 `_open_owned_descriptor`，`finally` 却直接 `os.close`；profile/trace 在 close action 前打断会让已移入 pending-generation tombstone 的 probe fd 永久泄漏。probe 目录现在创建后立即进入 structural owner/pin，slot isolation 复用 caller-owned slot fd；empty-directory isolation helper 强制接收 pinned fd，自身不再 acquire/release。全部 probe-local owners 由完整 `run_with_deferred_interrupts` batch 逐项执行 `release_owned_descriptor_once`，PRE_ACTION 只做一次 fd-range fallback，actual-close-then POST_ACTION 不重试 fd number，首个 release failure 记录后仍由 outer transaction 释放后续 generation owners 与 execution lock。新增 pre-action、post-action 与 first-failure-continues release RED/GREEN，断言 fd baseline、lock、无 normal generation 及 path-free error。新鲜 release focused 为 `1 passed, 2 subtests passed`，probe/ABA focused 为 `5 passed, 9 subtests passed`，execution snapshot 为 `65 passed, 61 subtests passed`，adapter+production 为 `120 passed, 1 skipped, 26 subtests passed`，五文件门为 `232 passed, 5 skipped, 103 subtests passed`；`compileall`、`git diff --check`、AST owner/release、helper raw acquisition/release 与 scoped raw-close gates 通过。
- 将 rollback-slot 的 non-destructive contract 从 successful retirement 扩展到 exchange-probe failure 与 post-probe/pre-publication failure。旧 `_probe_rename_exchange` failure cleanup 和 outer pre-publication cleanup 都会在 check 后对 mutable `.rollback-slot-*` 执行 `rmdir`，同名 ABA 可让 original 被攻击者改名保留后再删除 substitute。现在 exchange probe 的 slot/probe 与 early rollback slot 均通过 pinned pending-generation identity、pinned empty-directory fd 和 cross-dirfd `renameat2(RENAME_NOREPLACE)` 进入 internal tombstone/retained quarantine；source/destination 按 inode 分类，若搬走 substitute 只允许反向 no-replace 恢复 exact source name，original/competitor/substitute 均不删除、不覆盖。新增 probe failure 与 post-probe/pre-publication 两窗口、retain=false/true 四个 inode+xattr RED/GREEN 子用例，并显式禁止 rollback-slot `rmdir` 调用。新鲜 early-window RED/GREEN 为 `2 passed, 4 subtests passed`，exchange-probe+retirement focused 为 `14 passed, 13 subtests passed`，旧 exchange-probe/final-anchor focused 为 `6 passed, 7 subtests passed`，execution snapshot 为 `64 passed, 59 subtests passed`，adapter+production 为 `120 passed, 1 skipped, 26 subtests passed`，五文件门为 `231 passed, 5 skipped, 101 subtests passed`；`compileall`、`git diff --check`、exchange/early-slot destructive-call gate 与 scoped raw-close gate 通过。
- 撤销 2026-08-31 successful-publication retirement 中 destructive `rmdir`/`st_nlink==0` 叙事并修复 re-review 的两个 fail-closed 缺口。mutable `.rollback-slot-*` 名称现在永不执行 `unlink`/`rmdir`；exact slot 通过跨 dirfd `renameat2(RENAME_NOREPLACE)` 移入 normal generation 内部的 `.rollback-slot-tombstone-*`，因此 `.generations` 根 inventory 仍只含 normal generations。若 namespace ABA 导致 substitute 被搬走，runner 以 source/destination inode 分类并只用反向 `RENAME_NOREPLACE` 恢复其 exact dynamic slot name，原 slot 与 substitute 的 inode/xattr 均不得删除或覆盖；任何恢复歧义都会 force quarantine normal generation。rollback-slot fd release 的 `PRE_ACTION_FAILURE` 现在通过 `before_fallback` 在 descriptor 仍存活时 recovery，`POST_ACTION_EXCEPTION` 通过结构化 release outcome 触发相同的 identity+parent recovery；retain=false/true 都不得留下 normal consumable generation。同步新增 direct/retained namespace ABA、post-isolation fsync/verification、cleanup-anchor PRE_ACTION、published mode drift，以及 slot release PRE/POST RED/GREEN 回归。新鲜 retirement focused 为 `10 passed, 6 subtests passed`，旧 final-anchor focused 为 `4 passed, 4 subtests passed`，execution snapshot 为 `64 passed, 59 subtests passed`，adapter+production 为 `118 passed, 1 skipped, 22 subtests passed`，五文件门为 `229 passed, 5 skipped, 97 subtests passed`；`compileall`、`git diff --check` 与 scoped raw-call gate 通过。

## 2026-08-31

- 修复 successful publication 遗留 `.rollback-slot-*` 及其 quality review 的三个 retirement 缺口。根因一是早期 cleanup 只接受 `publication_state.resolved`，而正常 commit 按契约保持 `committed=True`、`rollback_required=False`、`resolved=False`；根因二是 slot 只有 stat snapshot，`stat→rmdir→absence` 可被同名空目录 ABA 欺骗；根因三是 slot 删除后 generation identity 已释放、rollback 仍假定 slot 可 exchange，且 published cleanup 前后只比 inode。`resolved` 继续只表示 rollback/recovery 完成；slot 现在于 exchange probe/publication 前以 no-follow exact fd pin，retain=false 使用独立 `.generations` cleanup anchor，retain=true 复用 private binding generations fd，并把 exact generation identity fd 延寿穿过 retirement 与 cleanup-anchor transaction。final rollback anchor 结构化 `RELEASED` 后，retirement 同时验证 parent、published fd+name、slot fd+name 的 exact inode/DIR/current uid/`0700`，要求 slot fd-relative empty；`rmdir` 后立即 commit 显式 `slot_retired` 相位，再执行 parent `fsync`、pinned slot `st_nlink==0`、name absent 与 parent/published 双绑定复验。slot 已由本事务删除后的 fsync/verification/cleanup-anchor PRE_ACTION failure 改用 live generation identity + cleanup anchor 执行 `RENAME_NOREPLACE` hidden quarantine/force recovery，不覆盖竞争者、不留下 normal consumable generation。新增 direct/retained namespace ABA、post-rmdir fsync、post-rmdir verification、cleanup-anchor PRE_ACTION、published mode drift，以及原单次/多 query/cleanup failure RED/GREEN；新鲜 execution snapshot 门为 `64 passed, 59 subtests passed`，adapter+production 门为 `117 passed, 1 skipped, 18 subtests passed`，五文件门为 `228 passed, 5 skipped, 93 subtests passed`。
- 归一 runner/production 全部 descriptor release transaction，修复 shared helper 的 Python return-event 仍可在首个 fd 后打断三 fd loop，以及 close 已实际完成、随后 outcome 分配失败会把空 holder 误当 pre-action并对 ABA 复用 fd 执行 fallback 的复审 blocker。`dosweb.filesystem.release_owned_descriptor_once` 现在要求 caller 在 primary action 前传入预分配 mutable state，raw close 后只做 allocation-free `RELEASED`/`PRE_ACTION_FAILURE`/`POST_ACTION_EXCEPTION` assignment；只有 action 前 setup escape 或 proved `PRE_ACTION_FAILURE` 才允许唯一 `closerange` fallback。caller-side wrapper 的 transaction allocation 也位于外层 batch；若分配本身抛 `MemoryError`，仍由唯一 local descriptor owner直接执行 fallback、记录失败并继续剩余 fd，不再因字段已退休而永久泄漏。runner binding、execution-query source/destination、pending/generations/identity/final anchors、production binding/workspace/ancestry 均把 owner retirement、shared-helper call、result commit、完整 descriptor loop 与 execution-lock release包进同一外层 deferred transaction；helper return-event 只能在全部 fd/lock 清理后恢复，primary/transaction/callback/fallback exception 逐项收集且不截断后续 owner。runner/production 已删除所有裸 `close_fd_once(_outcome)` call site；新增 binding/workspace 三 fd helper-return、transaction-allocation 首次失败仍全量释放、final anchor+execution lock、post-close `MemoryError`+同号 fd reuse RED/GREEN，并将 final-anchor post-close异常固定为 path-free `CODEQL_QUERY_FAILED`。新鲜 adapter+production 门为 `110 passed, 1 skipped, 16 subtests passed`，五文件门为 `221 passed, 5 skipped, 91 subtests passed`；`compileall`、`git diff --check` 与 scoped raw-call gate 通过。
- 修复 execution-query tempfile 在 source/destination close 已实际完成后抛 `BaseException` 时阻断 return、遗留 `.Q.dosweb.*.ql` 的最终复审边角：helper 现在在任何 fd acquisition 前 probe one-shot close capability，完整 copy+fsync 后两个 fd 都以 explicit outcome 释放；outcome call 与 holder assignment 进入同一 deferred transaction，只有显式存入的 `RELEASED`/`POST_ACTION_EXCEPTION` 才 commit path transfer，pre-call escape 必须对仍 owned fd 执行唯一 fallback、传播原异常并清理未转交 exact path。`POST_ACTION_EXCEPTION` 不 retry fd number且继续把 exact path 转交 caller cleanup，proved `PRE_ACTION` 才走已知-owner fallback。新增 source/destination actual-close-then-`KeyboardInterrupt` 以及 outcome pre-call `KeyboardInterrupt` 回归，caller 收尾后 query 目录严格不含任何额外 leaf、fd 回 baseline，不靠改前缀 quarantine 隐藏残留；修后新鲜 adapter+production 门为 `103 passed, 1 skipped, 16 subtests passed`，五文件门为 `213 passed, 5 skipped, 91 subtests passed`，`compileall`、`git diff --check` 与 scoped raw acquisition gate 通过。
- 收口 decoded content identity 与 descriptor ownership 复审：`bqrs decode` 后 decoded leaf 只执行一次 reserve/deferred owned-open，首次 name/inode/mode 验证、bounded `pread`、schema/query contract、fd fsync、publication 与 retained binding 全部复用同一 descriptor；transaction 固化 immutable bytes、exact size 与 SHA-256，并在 fsync、replace 前后、binding capture 前以及 JSON parse 后/decoder 前复核 live fd/name/digest。production 与 injected fixture boundary 只解析 snapshot bytes，等长同 inode 原地覆盖在 family 与 formal Entry/Pipeline 均固定 `CODEQL_QUERY_FAILED`、decoder 不调用、`run.json=failed`、无 stage artifact/manifest且 resume 重跑。所有 runner/production `os.open`、`os.dup` 与 `tempfile.mkstemp` acquisition 分别统一到共享预留 holder + trace/profile/SIGINT deferred transaction，tempfile fd 与 exact cleanup path 在 factory return 前共同 owned；setup 的 `setprofile(None)`、`settrace(None)`、`SIG_BLOCK` 均在动作前建立对应恢复 `finally`，post-action exception 仍恢复完整进程状态。binding 三 fd release、decoded owner、rollback anchors 与 execution lock 现在逐项收集 outcome；pre-action fallback `closerange` 的 actual-close-then-`BaseException` 不外溢、不 retry fd number且不跳过后续 owner。新增 decoded leaf exchange、open/dup/mkstemp return-event、binding/fallback release post-action、三类 deferral setup/restore 与 family parse-time/formal pre-read 等长覆盖 RED/GREEN；新鲜 adapter+production 门为 `101 passed, 1 skipped, 14 subtests passed`，五文件门为 `211 passed, 5 skipped, 89 subtests passed`，`compileall`、`git diff --check` 与 raw acquisition 单入口检查通过。
- 收口 query-output/workspace ownership 二轮复审的 3 Critical + 1 Important：publication 后不再按 mutable decoded name 重新开文件，而是把已完成内容验证的 decoded fd/info 直接转交 retained binding；binding holder 的 post-action exception 以结构性 membership 判定唯一 owner，production 仅在 workspace list 实际完成注册后设置 `attached=True`，registration 前中断仍由 local transaction one-shot 释放。Lexical ancestry 改由 factory holder transaction 管理，完整 tuple 在 helper return 前进入 caller holder；holder append→membership 窗口临时关闭 trace/profile 并阻塞 `SIGINT`，output/workspace/results 三个后续目录同样先预留 owner slot再执行 `os.open`，所有异常只从唯一 owner 逆序释放，避免 fd-number reuse 后二次关闭。完整 workspace 也在 factory return 前注册到 formal executor holder，family/Entry caller 从 `CALL` 前即进入 cleanup transaction，factory-return event 中断不再遗漏 ancestry/output/workspace/results fd。instrumentation 恢复使用嵌套 `finally`，profile restore 失败也不会跳过 signal-mask 恢复。新增 decoded-leaf exchange、holder post-action、attachment pre-registration、ancestry append/open/helper-return、workspace factory-return 与 signal restore RED/GREEN；最终新鲜门统一记录于上一条。
- 修复 post-publication/pre-binding 仍可交换并采纳 forged `.generations` 的 Critical：`run_query` 现在在原 publication anchors 释放前，从仍存活的原 `.generations` fd 复制 retained descriptor，并同时要求 named root 等于初始 generations inode、published generation 等于 publication expected inode；binding factory 在返回前通过 owner callback 进入本地 transaction holder，后续 housekeeping/rollback/release 任一失败均 one-shot 释放 partial/complete binding。新增真实 adapter exchange RED/GREEN，replacement 不再成为可信根或返回 `QueryResult`。
- 修复只绑定 output leaf/direct parent、替换更高祖先仍可通过的 Critical：query workspace 现在从 filesystem `/` 起逐 component `O_NOFOLLOW` 打开并保存完整 lexical ancestry，runner/decode/finalization 复验每层 parent/name/inode/uid/mode 后才接受 output/workspace/results；ancestor rename+replacement 在 decode 前固定 path-free `CODEQL_QUERY_FAILED`。所有 ancestry fd 纳入 one-shot reverse-order release，component open 后/fstat 前异常的 unbound fd 也有独立 RED/GREEN 验证回到基线。
- 收口 private result ownership transfer Important 与 serialization Minor：production 向真实 runner 传 pre-return `result_owner_callback`，callback 内 capture、验证并注册 binding；`run_query` return-event `KeyboardInterrupt` 时 workspace 已拥有全部 fd。非协作 injected runner 的 unattached `QueryResult` 仅由 private finalizer兜底回收。result registry 现强引用 `(QueryResult, binding)`，避免 Python `id()` 重用把新 query 错绑到旧 decoded fd；pickle 只保存六个 public fields，round-trip 明确恢复 `_output_binding=None`。新增真实 runner return-event、非协作 injected return-event、id-reuse 全图回归与 pickle RED/GREEN；五文件门为 `193 passed, 5 skipped, 87 subtests passed`。
- 修复 runner 已返回 private `_QueryOutputBinding`、但 output-root 在 production boundary 复验前已被换名时的 fd ownership Important：`_run_workspace_query` 现在先 capture/验证返回 binding，再执行独立 workspace 复验；失效 binding 会立即进入 one-shot decoded/generation/`.generations` release，不再因先抛 workspace binding error 而遗漏在最终 close transaction 之外。新增带真实 pinned private binding 的 output-root swap RED/GREEN，验证三个 binding fd 全部置为 `-1`、decoder 不调用且 fd 回到仅含测试持有锚点的基线。
- 修复首次 inventory 后、decoded JSON 读取前交换 `.generations` 仍可消费 forged result 的 Critical：formal `run_query` 返回前建立仅内存 private result binding，持续 pin 最初 `.generations` fd/inode、published generation fd/name/inode 与 decoded regular-file fd/name/inode/uid/mode；该 binding 不属于 `QueryResult` dataclass serialization/repr/equality/hash/artifact/path identity。production 对 injected runner 同样立即 capture binding，decoded bytes 只从 pinned file fd bounded `pread`，读取前后复验 results→original generations→generation→file 全链；final inventory 复用首次 expected generations inode，绝不重新打开 replacement 并把它当可信 root。post-inventory/pre-read exchange 现在保留 original/competitor/workspace，固定 path-free `CODEQL_QUERY_FAILED`，不调用 decoder、不发布 artifact，formal Entry `run.json=failed` 且 resume 重跑。所有 retained decoded/generation/generations fds 纳入既有 outcome release transaction。新增 family、formal Entry/Pipeline exchange-forged-JSON 与 private serialization surface RED/GREEN；五文件门为 `186 passed, 5 skipped, 87 subtests passed`。
- 收口 query workspace 的 lexical output-root replacement 与 fd-release Critical/Important：workspace 现在先 probe `close_range`，再 pin output parent fd，并以 parent-relative no-follow 打开 output leaf，保存 parent/name/device/inode/uid/mode binding；runner 调用前后、decoded JSON 读取前后与 finalization 全部复验 lexical leaf。结果接口改为 descriptor-stable `/proc/self/fd/<results-fd>`，`run_query(output_descriptor=...)` 强制 path/fd/inode/mode 配对，并向 query/decode 两个 CodeQL subprocess 传 `pass_fds`；output root rename 后重建 replacement 及伪造 JSON 只能得到 path-free `CODEQL_QUERY_FAILED`，不再解码或发布伪造 artifact，formal Entry 保持 `run.json=failed` 且 resume 重跑。`.generations`、results、workspace、output 与 output-parent fd 全部改用 `close_fd_once_outcome` transaction；PRE_ACTION 仅单次 `os.closerange(fd, fd+1)` 收尾，POST_ACTION 禁止 retry，单 fd 失败不跳过其余释放并固定失败。新增 family/Entry root-swap、subprocess fd inheritance、generation PRE_ACTION 与 results actual-close-then-exception RED/GREEN；五文件门为 `183 passed, 5 skipped, 87 subtests passed`。
- 继续收紧 formal query workspace cleanup 的两层 substitution window：target output、workspace、`results` 与 `.generations` 全部改为 no-follow fd + inode/current-uid/mode binding，generation inventory 只用 bounded `os.scandir(fd)`，scan 后重验全部 descriptor/name binding；`.generations` 扫描窗口换 inode、hidden/unsafe/drift/enum error 均只保留 workspace。无 hidden 的成功 workspace 也不再进入 lexical check-then-`rmtree`，而是经 pinned output dirfd 的 fresh `RENAME_NOREPLACE` 隔离到 `.dosweb-<family>-quarantine-*`、复验 expected inode/source absent、fsync 后保留；workspace name 在 isolation 前被 competitor 交换时重建为 ambiguous 并固定失败，original/competitor name/inode/nlink/marker 均不删除。`_run_codeql_family` finalization 返回非 proved-isolated success 时现在固定 path-free `CODEQL_QUERY_FAILED`，Entry formal 路径保持相同；新增 generation fd-scan exchange 与 workspace pre-isolation exchange RED/GREEN、late final-scan `run.json=failed`/无 artifact/resume 重跑/retained unchanged 回归。focused production `50 passed, 12 subtests passed`。
- 修复 formal executor 外层 lifetime 重新删除 retained quarantine：Entry executor 与 `_run_codeql_family` 的 query results 改为 target output 内 owner-only hidden `.dosweb-<family>-queries-*` workspace，query-pack temporary 与 results ownership 分离。异常展开和正常收尾都先 streaming 检查 `.generations`；只要存在 hidden generation、binding/枚举异常或超界，就 detach 并完整保留受信 workspace，禁止 outer `rmtree`，固定让 formal stage/run 保持 failed、无 `QueryResult` artifact，resume 必须重跑而不能消费 hidden output；仅无 retained hidden output 的已消费 workspace允许普通清理。新增真实 `run_query`→formal Entry→Pipeline 集成 RED/GREEN和 family helper 回归，持有 original/competitor fd 跨 executor unwind/retry 复验 name/inode/nlink/marker，确认 `run.json=failed`、无 stage artifact、fd/lock baseline，并显式断言 retained workspace 上零 recursive cleanup 调用。
- Publication rollback Quality Final TOCTOU 修正：删除所有针对 mutable normal `Entries-*` name 的 direct `rmdir`/raw `unlinkat(AT_REMOVEDIR)` fallback，并移除不再合法的 filesystem raw-unlink primitive。Actual generation 必须先经 fresh `.rollback-final-*` `RENAME_NOREPLACE` 原子隔离，exchange 后的 empty placeholder 也必须先经 fresh `.rollback-placeholder-*` 隔离；expected output inode 一旦在 hidden rollback/pending name 下完成复验，就只保留 quarantine，禁止继续枚举、`unlink` children 或 `rmdir` hidden root，避免 hidden namespace substitution 误删 competitor。所有 rename `BaseException`（包括 `FileExistsError`）统一从双 name/inode 重建；只有 source 仍为 expected、destination 为 unrelated inode 才视为真实 collision 重试，source substitution 把 competitor 移入 fresh hidden 时先 NOREPLACE 恢复 competitor 原名再固定失败。所有 cleanup/rename primitive 持续不可用时优先 source integrity：安全保留 hidden pending/actual/placeholder、固定 path-free `CODEQL_QUERY_FAILED`、不返回/消费 `QueryResult`，formal run 保持 failed 且 hidden output 不可 resume，同时全部 owned fds 与 execution lock 回 baseline。新增 primitive-outage actual/placeholder 安全保留及 normal/hidden root/hidden child substitution RED/GREEN，验证 competitor name/inode/nlink/marker 不变；旧“失败后 `.generations` 必须为空”断言改为“无可消费 normal generation、允许且要求 retained hidden quarantine”。
- Exchange capability probe Quality Final 收口：probe 新增显式双 name/双 inode transaction state 与 exchange/restore attempted/committed 相位；first exchange 真正完成后抛 `OSError` 或 `KeyboardInterrupt` 均从两侧 `stat` 重建 exchanged pairing，restore 持续 pre-action failure 不再强求第二次 exchange，而是按当前 pairing 经 pinned no-follow descriptors 清理两个空 transaction dirs。正常 probe 只删除 probe 并保留 rollback slot，失败 probe 无条件关闭自身打开的 descriptors，outer publication cleanup 继续释放全部 owned generation fds；调用边界捕获全部 `BaseException` 并固定规范化为 path-free `CODEQL_QUERY_FAILED`。新增 post-action/interrupt/restore-persistent 三态 RED/GREEN，验证零 probe dir、零 fd/lock 泄漏。
- Actual-generation fd release window 收口：pending root 建立后立即打开第二个同 inode `pending_identity_anchor`，primary pending fd 的 one-shot release 始终发生在 identity + final parent anchors 仍存活时。即使 primary `close_range` 已实际关闭后再抛 `OSError`/`KeyboardInterrupt`，同时普通 `_publication_replace_completed` 持续 `EIO`，direct recovery 仍从独立 actual-generation fd `fstat` expected inode并经 parent anchor隐藏 normal generation；rollback决策完成后 identity anchor 再以明确 release outcome 单次释放。新增精确组合 RED/GREEN，覆盖两类 `BaseException`、无正常 `Entries-*`、所有 primary/identity/parent descriptors 回到 baseline 及 execution lock 释放。
- Pending/publication ownership final 收口：彻底移除 `shutil.rmtree(pending)`，pending generation 改为 pinned `.generations` dirfd 下创建并从创建后一直保留 owner-only directory fd/expected inode。replace 未完成时只经 pending fd bounded 枚举、no-follow 复验并 dirfd-relative unlink/rmdir expected inode；replace 已完成时只双重验证旧 pending name 不存在，absence check 后重建的 competitor 原 inode/link/marker 全部保留并固定失败。final rollback anchor 新增不调用 `_publication_replace_completed` 的独立恢复：直接复验 actual generation fd 与 known pending/published names，persistent caller rebuild `EIO` 时仍将 expected normal generation 移入 hidden quarantine；只有两次证明 normal name 不含 expected inode后才释放 pending/anchor ownership。新增 pending-name competitor 与 persistent rebuild + quarantine-cleanup failure RED/GREEN，验证 competitor 不被误删、失败最多留下 hidden `.rollback-*`、无正常 `Entries-*`/`QueryResult`、零 fd/lock 泄漏。
- Publication `os.replace` assignment window 收口：新增 `_PublicationReplaceState`，在 dirfd replace 前绑定 pending/published name 与 expected inode，并预登记 `attempted + rollback_required`；replace return-event 的 `KeyboardInterrupt` 不再依赖 caller-side `publication_visible=True` 才触发 rollback。publication/housekeeping/fd release/final anchor 统一从 pinned names 重建 replace 结果；首次 rebuild `EIO` 保持 unresolved，由最终 anchor 重试。rollback 一旦启动则直接恢复 inode-bound exchange/quarantine state，避免 generation 已移入 hidden slot 后再按 pending/published 二元状态误判；只有证明 replace 未完成或 rollback 完成后才允许清理 pending/slot。新增 `sys.setprofile` replace-return interrupt 与首次 state rebuild failure RED/GREEN，验证无正常 `Entries-*`、零 fd 泄漏且 execution lock 释放。
- Private snapshot/publication failure-window final 收口三项：published generation rollback 继续优先对 fresh hidden UUID 执行 `renameat2(RENAME_NOREPLACE)` 并仅对 destination collision 重试；发布前新增 inode-bound empty `.rollback-slot-*` 与 `renameat2(RENAME_EXCHANGE)` exchange/restore capability probe，NOREPLACE 持续非 collision `EIO` 时把正常 generation 与预绑定 slot 原子交换、复验双 inode、fsync 并删除正常名下的空 placeholder，再从 hidden slot 做 descriptor-safe cleanup。Exchange rollback 现在显式保存 normal generation/empty slot 两侧 expected inode 与 `exchange_committed`/`placeholder_removed` 相位；每次 retry 都从两侧 dirfd name 重新恢复唯一合法状态，post-exchange inode check、fsync、placeholder `rmdir` 任一单次异常都不会再把 normal 侧 empty slot 误当 generation，恢复后清空真实 hidden generation 且不留 `Entries-*`。彻底删除 dirfd `os.replace` check-then-overwrite fallback，竞争者在 absence check 后创建的 leaf 保持原 inode/link，不使用 `os.rename`；cleanup 失败最多留下 hidden quarantine，不再留下正常 `Entries-*`。Snapshot factory 新增 return 前 `owner_callback`：完整 binding 在 factory transaction 内注册到 finalizer holder，factory-return profile event 的 `KeyboardInterrupt` 已无法抢在 ownership 前；callback 自身 `BaseException` 由 factory 删除 tree、关闭 parent fd并将 binding 标记为已清理。Pipeline failure persistence 与 finalizer 改为真正外层 `finally` transaction：首次 failed-state `_write_run()` 即使抛 `KeyboardInterrupt`/`SystemExit` 也必定恰好 finalization 一次，finalizer 后重试 path-free `failed` 元数据，并保持 finalizer > failure-write > stage 的异常优先级及 cause chain。新增 persistent rollback EIO + destination race、exchange capability preflight、post-exchange inode-check/fsync/rmdir fault、owner-callback interruption、factory-return `sys.setprofile` interruption、stage interrupt + failure-write interrupt 的 RED/GREEN，验证无正常 generation、竞争者不被覆盖、零 fd/lock 泄漏、snapshot tree/parent fd 回收及最终 `run.json=failed`。
- Pipeline finalizer 现在覆盖全部 `BaseException`，不再让 private snapshot cleanup 中的 `KeyboardInterrupt`/`SystemExit` 绕过 failure persistence 并将 `run.json` 停在 `running`。非 `AnalyzerError` finalization 中断统一转为 path-free `ANALYSIS_FINALIZATION_FAILED`，只持久 bounded `error_type`；成功 stage 后 cleanup 中断固定落盘 `failed`，已有 stage/preflight 原始失败时继续以 finalization failure 为优先语义，并将原始 `AnalyzerError` 保留为 cause。新增成功路径 `KeyboardInterrupt` 与 stage failure + finalizer `SystemExit` RED/GREEN，验证 exception details/持久元数据均不含 private path。
- Private snapshot/publication final Quality 四项 Important 收口：新增显式 `publication_rollback_required` transaction state，initial rollback/quarantine 首次 rename `EIO` 后即使 primary/rollback fd 都正常释放，finalizer 也必须用仍 pinned 的 final anchor 重试并完成隐藏，失败不得遗留正常 `Entries-*`。primary/rollback generation fd 与 snapshot root fd 遇到明确 `CloseRangePreActionError` 时，由于 ownership 仍可证，先完成必要 rollback/tree cleanup，再以单次 noexcept `os.closerange(fd, fd+1)` 释放，不再将注入错误合理化为 fd `+1` 泄漏。`CloseRangeCapability` 现同时绑定 `sys.platform == linux`、`platform.system() == Linux` 与 supported architecture；Darwin/FreeBSD/Windows 即使同为 `x86_64` 也在调用 syscall 436 前以 `ENOSYS` fail closed。新增 initial rollback 单次 EIO 重试、generation/snapshot pre-action 零 fd 泄漏与非 Linux 同架构平台矩阵 RED/GREEN，同时验证无正常 generation 残留且 execution lock 释放。
- Private snapshot/publication final Quality re-review 否定了 failed `close()` 后以 `kcmp(KCMP_FILE)` 检查再 retry 的方案：identity check 与第二次 close 之间仍存在 fd-number ABA，可误关同 inode 或任意 replacement。新增共享 `CloseRangeCapability`，snapshot root 与 generation publication 在创建 owned fd 前都先以空高位区间 probe 并绑定 Linux `close_range` syscall，释放时只执行一次 `close_range(fd, fd, 0)`。raw syscall `rc<0` 现在以专用 `CloseRangePreActionError` 显式表示动作前失败；成功返回后观察到的其他 `BaseException` 与正常释放分别记录为 `POST_ACTION_EXCEPTION` / `RELEASED`，不再无条件吞掉 pre-action error。snapshot 删除 identity anchor；generation 只保留 rollback duplicate/anchor 用于隐藏失败 publication，不用于 retry close。primary/rollback descriptor 的所有失败都在 final anchor 释放前完成 rollback 决策；final anchor 若明确 pre-action failure，仍用确定存活的 anchor 隐藏 publication，再以单次 noexcept `os.closerange(fd, fd+1)` 释放并固定 `CODEQL_QUERY_FAILED`；若是 actual-close-then-`OSError|KeyboardInterrupt`，则 durable commit 保持成功，不再触碰该 fd number，返回 `QueryResult` 并保留唯一正常 generation。新增 kcmp-check→retry 窗口中强制 fd reuse、primitive unavailable/error/errno、preflight、primary/rollback pre-action failure、final-anchor raw pre-action 与 post-action 异常的 RED/GREEN；replacement 保持可用，失败 publication 无正常 generation，execution lock 必定释放。
- Private snapshot cleanup finalization re-review 补齐 quarantine 首次复验后的同 inode mode race：`remove_contents()` 完成后、root `rmdir` 前同时重验 quarantine name 与 pinned root fd 的 inode/current uid/exact `0700` mode，删除后继续以 pinned fd 验证相同 uid/mode/inode 及零 link count；递归删除起点或 `rmdir` 内发生的 `fchmod(0755)` 均固定 finalization failure，不再静默成功。新增 remove-contents-start 与 root-rmdir 两个确定性 RED/GREEN checkpoint。
- Private snapshot cleanup Important re-review 补齐两个剩余 lifetime race：root fd 打开后重新绑定 snapshot inode/current uid/exact `0700` mode，quarantine rename 后、递归删除前再同时通过 pinned root `fstat()` 与 quarantine-name `stat(..., follow_symlinks=False)` 复核相同 inode/uid/mode，任一同 inode `chmod` 漂移均 fail closed 且 victim 保留。`ExecutionDatabaseBinding` 新增 lock-protected one-shot cleanup closed state，并在首次访问/关闭持久 parent fd 前消费；重复、并发 cleanup 直接 no-op，不再把复用的 fd number 当 parent fd访问或关闭。新增 before-open/after-quarantine mode drift、fd reuse、并发与串行重复 cleanup 的确定性 RED/GREEN。
- Private snapshot transaction re-review 再收口四个 failure window：stale scan 不再只保存 leaf name，而是把 `st_dev/st_ino/st_uid/st_mode` binding 传到同一 parent-fd quarantine/delete，scan 后同名换 inode 固定 `stale_cleanup` fail closed 且 replacement victim 不动。runner 新增显式 `publication_visible` transaction state；dirfd `os.replace` 抛出任何 `BaseException` 后以 pinned fd 核对 pending/destination inode，已完成 replace 必须先 rollback/quarantine，覆盖普通异常与 `KeyboardInterrupt`。run-query housekeeping 改为嵌套 cleanup stack：execution query unlink 失败会在 generation fd 关闭前回滚已发布 generation，generation fd 与 execution lock 无条件恰好释放，随后以固定 publication error 失败。final snapshot cleanup 无论 quarantine/delete 成败都在 locked 出口关闭持久 parent fd；失败残留由下一次 stale cleanup 以新 bound fd 回收，连续故障不再增长 `/proc/self/fd`。新增 stale same-name inode race、replace-then-raise、post-publication unlink failure 与 repeated cleanup-fd 四组 RED/GREEN。
- Private snapshot Important re-review 收口三类 alias/parent-swap 缺口：execution tree 的 regular file 现在强制 `st_nlink == 1`，clone 后与每次 execution validation 都拒绝指向 canonical/out-of-tree inode 的 hardlink，canonical read-only tree 仍由原 identity/checkpoint 合同验证；回归证明 query subprocess 在 validation 前置失败后零调用且 canonical bytes 不变。`ExecutionDatabaseBinding` 现在持有创建时验证的 output parent fd/device/inode/uid，final cleanup 不再重开 lexical parent；stale scan、candidate quarantine rename、递归删除与 parent fsync 全程共用同一 output fd，parent swap 只能清理原 snapshot，replacement victim 原样保留。runner 在 publication 前 pin `.generations` fd/inode，capability probe、dirfd-relative `os.replace`、fsync、path-binding recheck 与 drift rollback/quarantine 全部复用该 fd；post-replace `.generations` 换父不再遗留正常 `Entries-*`。新增 hardlink write、final/stale parent swap 与 generation parent swap 确定性 RED/GREEN，继续禁止 `os.rename` 覆盖 fallback。
- Private DB final spec re-review：所有 canonical `_validate_safe_tree()` 结果现在都把 descriptor-validated root `st_dev/st_ino` 重新绑定到 `DatabaseInfo.canonical_device/canonical_inode`；即使 identity 校验与 tree validation 之间被替换成 current-uid、owner-only、不同 fingerprint 的新 root，也固定 `CANONICAL_DATABASE_CHANGED`。正常 generation publication 现在先在当前 `.generations` filesystem 上以随机隐藏 source/target、dirfd-relative `renameat2(RENAME_NOREPLACE)` 完成 capability probe、绑定清理与 fsync；`ENOSYS`、`EINVAL`、`EOPNOTSUPP` 均在 `os.replace` 前 fail closed，使正常 `Entries-<uuid>` 从未出现，且绝无 `os.rename` fallback。rollback 不再保留 unsupported 时直接删除正常 generation 的危险分支。新增 canonical 两阶段换根 race 与三类 no-replace fault-injection RED/GREEN；`ENOSYS` case 同时注入 rollback cleanup failure，证明 publication 前置失败不依赖 rollback cleanup。
- Private DB spec re-review Important 收口：新增共享 Linux `renameat2(RENAME_NOREPLACE)` dirfd primitive，snapshot cleanup 不再使用“precheck + overwriting rename”；`EEXIST`/`ENOSYS` 固定 cleanup failure且无 fallback。quarantine 删除完成后若同 uid 重建原 `.codeql-execution-*` 名，replacement 原样保留，但 cleanup/Pipeline 固定失败并将 `run.json` 持久化为 `failed`。execution binding 下 `run_query` 在创建输出或启动 subprocess 前拒绝 resolved `output_dir` 等于/位于 execution root，确保 `QueryResult.query_path/bqrs_path/decoded_path` 均不含随机 snapshot。post-replace drift rollback 先以 no-replace 将正常 generation 隐藏到 `.rollback-*`、验证 inode 并 fsync `.generations`，再做 dirfd/no-follow inode/link-count cleanup；目标竞态以新 hidden name 重试，cleanup `OSError` 也只能留下不可识别 quarantine，绝不留下正常 `Entries-*` generation 或返回 `QueryResult`。新增 replacement→Pipeline failed、unsupported/raced no-replace、output containment、rollback cleanup failure/target race RED/GREEN。
- Private CodeQL DB critical re-review：Pipeline 现在先原子持久化递增 attempt 的 `running`，再执行 preflight，并在 preflight identity 完成后再次落盘；preflight/stale failure 不再保留旧 `completed`。snapshot factory 对 `KeyboardInterrupt`/`SystemExit` 等全部 `BaseException` 清理 partial clone，cleanup error 优先，既有 fixed `stale_cleanup` error 保持原 stage/reason。canonical root 与全部 nested entries 强制 current uid。clone/validation/stale/cleanup 枚举改为 bounded streaming `os.scandir(fd)`；cleanup 先同 parent 原子 quarantine rename，再以 dirfd/no-follow 删除并用 open-fd inode/link-count 验证 file/directory/root removal，root replacement 不会被误删。runner 在 publication hash、file/pending fsync、replace 前后及 generation fsync 后重验 canonical/private binding；post-replace drift 删除刚发布 generation并 fsync `.generations`，固定 path-free `CODEQL_QUERY_FAILED`。新增真实 default `FICLONE` 独立性/cleanup integration、late-publication 五 checkpoint、foreign-owner、BaseException、stale-error、streaming bound 与 quarantine race RED/GREEN；finalizer cleanup failure 持久化并覆盖 stage error，后者仅作 cause。
- 修复 `codeql query run` 修改 canonical CodeQL DB（包括 `db-java/default/strings/`）后破坏 fingerprint/resume 的生产隔离缺口：locked preflight 现在为每 target pipeline 在正式 output root 内只创建一次隐藏 0700 private execution DB，全部 selected queries 共用，clone 强制 Linux `FICLONE` reflink-only 且不允许 full-copy fallback；canonical `DatabaseInfo.path/source_root/fingerprint` 仍是 stage/run/batch/resume 的唯一身份。clone 前后、query 提交检查点及 pipeline finalizer 验证 canonical exact identity 与 private path/inode/uid/mode/source-root/无 symlink-special-file，允许 CodeQL 仅改变 private fingerprint；canonical mutation 终止 publication 并在 replace 后按需回滚 generation。新增 completed 落盘前 finalizer，成功、stage/preflight/exception、全量 resume reuse 均验证并以 no-follow bounded cleanup 删除 snapshot；安全 stale root 可回收，unsafe/foreign/mode/inode/cleanup/reflink/capacity failure 统一固定 path-free `CODEQL_EXECUTION_SNAPSHOT_FAILED`，cleanup failure 不得留下 completed run。新增 snapshot、Pipeline finalizer 与 production one-clone/resume/stage-failure RED/GREEN，并保证随机 snapshot path 不进入 QueryResult、diagnostics、run/artifacts/manifests/report。
- 收紧 Responses assistant content-part 协议边界：exact allowlist 现在只接受 `type=output_text` 且每项 `text` 为 string；`refusal`、缺失 type 或任何 unknown/future part type 一律作为 permanent `LLM_RESPONSE_INVALID`，即使旁边存在合法 schema contract 也不进入 Growth/Auth safe correction、不缓存、不审计。新增 Growth/Auth 端到端与 parser RED/GREEN，覆盖 unknown part 内的 email PII、Growth source echo 与普通 marker，固定一次 provider call，并验证 cache/audit/exception context/traceback locals 无残留。
- 修复 Responses inner contract 以 JSON `\\uNNNN` 转义绕过 semantic sensitive scan 与 cache replay raw/typed 分裂：Growth/Auth 现在在 typed construction 前执行唯一 bounded canonical pass，依次解析并扫描 decoded outer envelope（fixed credential-only）、decoded inner semantic object/canonical key-value context（fixed credential + email/phone/SSN，Growth 另含 source echo）及 provider request ID（fixed credential-only）。immutable snapshot acceptance 再按 caller API key/`extra_secret_patterns` 重扫相同 decoded layers，并从 raw semantic 重新执行 Growth slice/fact-alias binder 或 Auth `security:<ordinal>` alias binder，要求 rebound `to_dict()` 与 authenticated typed snapshot及 raw/snapshot actual model 精确一致后才允许 audit；cache replay mismatch/escaped sensitive 固定零回源、零 audit，strict-owner/lax-waiter 仍共享一次已完成 flight。Growth cache/HMAC 升至 v12、Auth cache/HMAC 升至 v4、Growth production fingerprint 升至 v13；DeepSeek Auth identity 显式加入来自 cache 模块单一常量的 `auth_cache_format=auth-contract-cache-v4`，使真实 HMAC-valid v3 旧记录与 v4 使用不同 immutable key，旧文件原样保留且不再阻塞 provider call/v4 publication；Growth v11/Auth v3 及更早记录 cold miss。新增 fresh/correction、semantic credential/JWT/URI/PII/source-echo、per-waiter extra、HMAC-valid escaped replay 与 raw/typed mismatch RED/GREEN。
- 修复 response-side `extra_secret_patterns` 错误扫描 outbound Growth/Auth initial/correction prompt：DeepSeek client 的全部发送前扫描现在只运行 fixed request credential policy，caller extra 仅在 immutable response snapshot 已 publication 且 shared flight 已完成后检查 raw body/request ID。新增 initial-prompt-only 与 correction-prompt-only pattern 的 strict-owner→lax-waiter 并发 RED/GREEN；正常响应保持一次 provider flight，首轮 schema-invalid + safe correction 保持整条共享 flight 恰好两次 provider call，不再由 lax waiter 重跑成三次。
- 修复真实 Responses envelope metadata 中 phone-like provider ID 被 generic phone PII regex 误报：raw envelope 与 request ID 现在只执行 configured key、credential assignment/Bearer/API-key/private-key、JWT、credential URI 及 caller `extra_secret_patterns`，parsed assistant semantic `content` 继续执行完整 credential + email/phone/SSN + Growth source-echo gate。fixed universal policy 仍在 publication 前，caller extra policy 仍在 immutable snapshot publication/flight completion 后执行，未污染 strict-owner/lax-waiter single-flight 次序；新增 Growth/Auth phone-like ID `0600` audit/cache、semantic phone terminal、各层 fixed/extra credential 与 universal failure 回归。
- Quality re-review 收紧 Auth ownership/alias/publication 与 Growth publication：Auth cache/single-flight identity 新增不外传的 SHA-256 ownership digest，绑定 original Entry 与有序 security/configuration semantic bindings；同形不同 owner 不再复用，disk replay 对 de-aliased evidence 执行 current-fact ownership 校验。provider evidence 仅允许当前 exact `security:<ordinal>` alias，未知 alias 首次进入唯一 safe correction、二次 terminal。Auth 在 provider 前持有 `auth-<identity>` capacity reservation，容量失败零调用；Auth/Growth cache put 异常或 false return 均先清空 response/parsed/request/model/contract/snapshot locals，再以固定 unchained `LLM_CACHE_WRITE_FAILED` 失败，且 publication failure 优先于 caller custom policy。新增 ownership/config binding、foreign signed replay、unknown alias、preflight capacity、publication traceback 与确定性双向 single-flight 回归。
- 收口 Auth provider strict-schema/sensitive-response failure：`auth-contract-v4` / `auth-contract-schema-v3` 在首次 `LLM_RESPONSE_SCHEMA_INVALID` 或 `LLM_RESPONSE_SENSITIVE_CONTENT` 时仅允许一次 safe correction，只重发 unchanged aliased security/configuration facts，并明确 exact four keys、`evidence_ids`/`assumptions` JSON arrays（可空）及 `confidence=high|medium|low`；不携带 rejected body/request ID，不做 scalar-to-array normalization，第二次失败保持原错误码 terminal。
- Auth rejected-response 清理达到 Growth 同级边界：response envelope/content/parsed object、request ID、actual model 与 typed contract 在 retry/terminal 路径清空，拒绝原文不进入 cache、audit、exception cause/context 或 traceback frame locals。新增独立 Auth thread single-flight；owner/waiter 共享 policy-neutral immutable snapshot，但每个 client 重新执行自身 raw-body/request-ID policy，policy rejection 不回源、不污染其他 waiter，same identity 仅一次 provider flight。
- Auth authenticated cache/HMAC domain 升至 v3，并认证 `accepted_prompt_variant=initial|correction` 与 bounded actual provider model；disk replay 对 requested model alias fail closed，并在 fresh/cache-hit audit 中保留实际 alias、确定性重建 exact accepted prompt，Auth v2 及更早缓存 cold miss。Growth-stage production fingerprint 升至 `production-v2.7-open-world-maturation-growth-v12`，阻止 formal resume 复用修复前 Auth 产物；同步唯一设计规范、README 与回归测试。
- 修复 Growth/Auth policy-neutral single-flight 的 strict-owner 反向顺序缺口：live flight 在共享 snapshot 前只执行固定 built-in credential/PII/source-echo gate 与实际 owner transport API-key 检查；`extra_secret_patterns` 仅在 snapshot accept 阶段按 caller 执行。snapshot/cache/flight 先完成，再生成 owner `cache_hit=false` audit；strict owner 本地拒绝不会进入 correction、二次覆盖 shared state、删除 cache 或迫使 lax waiter 回源。universal 两次 sensitive failure 作为同一 terminal flight failure 共享，strict-owner→lax-waiter 的 Growth/Auth 回归均保持一个 provider request。
- Auth content 从普通 `json.loads` 改为 bounded unique-key strict parser，duplicate members、non-finite/depth/node/string bounds 首次失败进入唯一 safe correction，第二次保持 terminal/no-cache/no-audit，并清理 rejected traceback locals。Auth prompt 同时确定性 alias Entry、security fact ID/location、modeled configuration ID/source path；configuration 先经过 exact `ModeledConfigurationFact` schema，仅发布 allowlisted key/typed-value/source-line/profile/provenance/default/status 语义，initial/correction payload 完全一致且 cache replay exact。上述修复仍属于本轮未发布的 Auth v4/schema-v3/cache-v3 与 growth-v12 identity baseline，无额外格式轮换。

## 2026-08-30

- Quality re-review 收紧 Growth false-negative 与 rejected-body 内存边界：`ProviderGrowthContract` 和本地 `GrowthContract` 现共同强制 `contract_status=dos_relevant => is_resource_growth=yes`，provider 返回 `no|unknown + dos_relevant` 时首轮只进入唯一 safe correction，第二轮保持 terminal `LLM_RESPONSE_SCHEMA_INVALID`，不缓存、不审计。每个 provider attempt 前及失败路径显式清空 `reply/content/request_id/actual_model/contract` 等响应引用；malformed Responses envelope 在清空 body/envelope/parts 等局部变量后以固定错误 `from None` 抛出，第二次 schema/sensitive terminal 与首轮 sensitive 后 correction transport failure 的最终 traceback frame locals 均不得保留 rejected marker。Disk cache hit 与 concurrent single-flight waiter 的 per-client body/request-ID policy rejection 同样先在 `_accept_growth_snapshot` 清空 snapshot，再由 caller 清空 `cached_snapshot` 或抽取 immutable waiter snapshot 后解除 `state` 引用，且不修改其他 waiter 仍需使用的 shared snapshot；不同 policy waiter 保持单 provider call，合法 waiter audit/cache 仍保留 exact accepted body，disk request ID 仍只存 HMAC digest。Growth production fingerprint 升至 v11；为隔离修复前可认证的 false-negative cache，Growth cache/HMAC domain 升至 v11，v10 及更早缓存不可复用；prompt/schema 仍为 v7/v5。
- 修复 fresh t180 provider canary 的 attacker-evidence binder 失败：安全结构诊断确认有效 worktree run 的 initial/correction response 可满足 provider-v5 17-key shape，却可能选择无法通过本地 `flow|driver_origin + source|flows_to + unique attacker_target` 绑定的 alias；prompt 现只发布确定性 `attacker_evidence_options`（aliased evidence ID + local target context），provider 只能回传其中的 `evidence_id`，空 options 禁止 `dos_relevant`，correction 同时明确 `confidence` 必填且仍只有一次。未放宽 schema、alias ownership、binder、static evidence 或 positive gate；Growth prompt identity 升至 `growth-contract-v7`，production Growth fingerprint 升至 v10，response schema/cache format 保持 v5/v10，并新增 scripted provider RED/GREEN。PoC-33 real-provider acceptance full plan 同步 digest-bind `timeout_seconds=180` / `max_retries=3`，不再依赖 CLI 默认 60 秒 deadline。
- Spec re-review 补齐 t180/archive 与 binder 边界：`validate_full_archive()` 现在要求 plan provider 映射精确等于 `allow_remote_llm=true, timeout_seconds=180, max_retries=3`，即使 60/1 计划自身 digest/target binding/state 全部一致也拒绝，且 60/1 与 180/3 plan ID/digest 差异有独立回归。Growth prompt 新增 eligible/wrong-relation/missing-target/multiple-target/zero-option 精确过滤矩阵；binder-invalid initial 后 correction 缺唯一 `confidence`（其余 16 键合法）保持 terminal strict failure，不本地填补、不缓存、不审计；成功 correction 回归继续保留。唯一设计的当前 Growth fingerprint 统一为 v10。
- Code-quality re-review 修复 Growth provider/cache/single-flight 相邻边界：provider envelope 与 cache raw response 统一为 131072-byte safe limit，合法约 80.9KB envelope 可缓存重放，direct oversize cache write 固定为不含原文的 `LLM_CACHE_WRITE_FAILED`；thread single-flight 改为共享 policy-neutral immutable accepted snapshot，每个 waiter 使用自身 API key 与 `extra_secret_patterns` 重新验证 raw response及 in-memory provider request ID并生成自己的 replay audit，header-only/sensitive policy failure 不再作为共享结论且不同 policy 并发仍仅一次 provider call；disk cache 继续只保留 request-ID digest，replay snapshot 使用空 request-ID。DeepSeek cache hit 改为一次 authenticated snapshot 读取 typed contract、raw response、prompt variant 与 HMAC-bound `actual_model`，消除 `get()+audit_payload()` 双读 TOCTOU，并保留 provider model alias。Growth fingerprint 升至 v9；新增 large-envelope、body/header-only 不同 policy 并发、cache-file replacement 与 model-alias replay RED/GREEN。
- 第三轮 provider cache spec review 收紧 `request_audit` identity binding：`provider` 与 `protocol` 现在都必须是 bounded string，并分别 exact-equal cache identity 的 provider/protocol；API-key 可重签的 arbitrary provider object、错误 provider、protocol object 或错误 protocol 均由 shared strict validator 的两个读取入口一致拒绝。signed-malformed 矩阵扩展至 19 类。
- Provider correction cache re-review 消除 v10 两读取入口的验证分叉：`authenticated_contract()` 与 `audit_payload()` 现在共同委托唯一 strict Growth entry validator，对 exact top-level fields、cache key/format/schema/identity、identity/audit/raw/contract/entry hashes、request audit、`accepted_prompt_variant` enum、typed contract 与 HMAC 执行同一 fail-closed 验证；signed malformed entry 不再出现 contract reader 接受而 audit reader 拒绝或反向接受。新增 15 类 signed/tampered malformed 双入口一致拒绝矩阵。
- Provider correction spec re-review 收口两条可重现边界：Growth cache 现在以 HMAC-authenticated `accepted_prompt_variant=initial|correction` 持久化实际 accepted prompt 路径，cache-hit 从同一 bounded slice 确定性重建该 prompt，fresh/cache-hit `normalized_prompt` 不再漂移；cache/HMAC domain 因结构变更诚实升至 v10 并进入 cache identity，v9 只作 cold miss且不会占用相同 cache key。第二次 schema/sensitive terminal failure 现在在离开原 exception handler 后重建固定无 details 的 `AnalyzerError`，JSON parser 也不再把带完整 rejected body 的 `JSONDecodeError.doc` 接入 cause/context 链；失败原文不得通过 message、details、cause 或 context 泄漏。Growth production fingerprint 升至 v7；新增 schema→sensitive、correction cache replay 与 malformed JSON exception-graph RED/GREEN。
- 修复 fresh schema-2.7 provider canary 的 Growth completion 边界：首个 `LLM_RESPONSE_SCHEMA_INVALID` 或 `LLM_RESPONSE_SENSITIVE_CONTENT` 现在统一只触发一次 safe correction，correction 只重发未变 bounded slice 与 deterministic 17-key/status/evidence-alias/local-binding 约束，绝不回显、缓存、审计或记录被拒原文；第二个 schema/sensitive failure 保持原错误码 terminal。request credential scan、16/32 evidence limits、strict schema、positive gate、local evidence binding 与 single-flight 均未放宽。Growth prompt identity 升至 `growth-contract-v6`，production growth fingerprint 经 re-review 升至 `production-v2.7-open-world-maturation-growth-v7`，禁止 formal resume 复用修复前 growth artifacts；response schema 保持 v5，cache/HMAC format 经 re-review 升至 v10，并新增 scripted transport RED/GREEN 回归。
- 收口 Auth final-quality 三项 fail-closed 边界：当前 Entry/bounded slice 内任一 non-deployment `partial`/`unsupported` security fact 现在都是 Auth coverage gap，local derivation 与 provider selective citation 均不能隐藏，固定输出 `REACH_AUTH_COVERAGE_PARTIAL`、unknown Auth/Reach；partial deployment 继续由独立 resolver 处理。32-ID proof budget 先保留最小 gap representative，再保留 complete Auth context、deployment status 与 provider citations，正反序和高基数结果一致。`@ConditionalOnProperty` 完整建模 static prefix canonicalization 与 `matchIfMissing` absence semantics，只允许唯一 static name、非空 static `havingValue`、static prefix、`matchIfMissing=false` 产 complete exact-key gate；`prefix` 与 `prefix.` 均归一到同一 key，unprefixed fallback 禁止，其余保持 partial。Auth annotation 从 simple-name heuristic 改为 `javax`/`jakarta` PermitAll/RolesAllowed、Spring PreAuthorize/Secured、Vaadin AnonymousAllowed exact qualified-name allowlist，项目自定义同名 annotation 不再误报。新增 unit、production selective-citation 与真实 CodeQL fixtures；entries/growth fingerprints 升至 v5，flows-v3、lifecycle-v2、conclude-v4 保持不变。
- 修复 EntrySecurity/Auth/Reach quality review 的 fail-closed 边界：concrete route matcher 现在绑定全部语义匹配 Entry，zero-match 不再错误回退 handler；仅缺失/非具体 route 可使用唯一 exact handler identity，输出与输入顺序无关。`ROLE_USER`、混合/普通 role 与非 exact role expression 一律只产 partial unknown，仅 exact `ADMIN`/`ROLE_ADMIN` 及 exact admin `hasRole`/`hasAuthority` 可产 complete privileged；`ConditionalOnBean/Class/Expression` 与 generic `@Conditional` 改为 partial optional，复杂/负向/多值 `@Profile` 改为 partial，resolver 也拒绝旧 complete complex-profile fact。显式 partial deployment fact 继续抑制 synthetic `default_enabled`，保持 Reach unknown。新增 binder/resolver、真实 CodeQL Spring fixture 与 production artifact/decision 回归；direct/embedded `EntrySecurity.ql` byte-identical，entries fingerprint 升至 v4，并同步唯一规范/README 的完整 fingerprint 总表（flows-v3、growth-v4、lifecycle-v2、conclude-v4）。
- 收紧 CandidateCoverage 与 lifecycle certificate 的 exact registration-coverage 边界：generic coverage 仍可表达 framework gap，但其每个非空 `supported_patterns` 现在也必须是归属于该 framework 的 modeled exact pattern ID，invented/cross-framework/broad-kind 值全部拒绝，`unsupported_patterns` 继续保留为自由 gap note。具体 certificate 不再把空 scope 当 wildcard，必须同时精确绑定当前 `registration_pattern_id`、`entry_id` 与 `growth_id`；`path_id` 继续保留既有 grouped-path 可选语义。新增 generic constructor、unscoped current/sibling、缺 Entry/Growth scope、canonical reconstruction 与 production exact-positive 回归；conclude fingerprint 升至 v4，禁止复用修复前 certificate artifacts。
- 完成 open-discovery CLI ancestor 发布合同的最后收口：parent dirfd pin 后不再调用 path-based `_output_exists(output)`，destination preflight 与 publication 前复核仅使用固定 parent fd 的 no-follow leaf check，parent identity drift 与最终 `renameat2(RENAME_NOREPLACE)` 继续 fail closed。竞态回归改在首次 pin 前 existence check 内真实注入 `missing ancestor -> immutable batch` symlink，并断言 callback 已执行、CLI 返回 2、batch tree 无新增目录或 leaf；atomic leaf race 直接注入到 `renameat2` 调用窗口，竞争者 inode/内容保持不变。focused evaluator/CLI `41 passed, 58 subtests passed`。
- 修复 Entry registration coverage 的同 kind 跨 pattern 继承：complete raw row 现在必须由 exact `(framework, registration.kind, coverage_note)` 派生不可伪造的 `registration_pattern_id`，并将其纳入 Entry semantic identity、strict roundtrip、artifact schema、normalize merge key 与 flow/association identity；未知 complete note、跨 framework/kind ID 和反序列化漂移均 fail closed。`coverage.json.supported_patterns` 改存 exact IDs，conclude/CandidateCoverage/certificate 只绑定当前 Entry exact ID；同 framework、同 registration kind 的 sibling supported pattern 不再能把当前 Entry 升为 complete，缺失 exact match 经 proof gate 固定输出 `static_unknown` / `VERDICT_ENTRY_COVERAGE_INCOMPLETE`。entries/flows/conclude fingerprints 升至 v3；新增 model/schema/normalize、candidate scope 与 production conclude RED/GREEN 回归。
- Quality re-review 收紧 Auth/Reach 事实域：Auth 语义只接受 exact `(kind,value)` allowlist，`dependency_coverage + unauthenticated_annotation` 等错配不再参与 derivation、conflict 或 cited support；deployment facts 同时要求 current Entry 与 current bounded slice，外部 Entry gate 不再污染状态/evidence。modeled configuration index 改为全量 typed-value collect：同 type/value 可折叠，冲突值视为 absent/unknown，`True` 与 `1` 明确不同且输入逆序结果一致。production 注入错配 security fact 后 unique privileged Entry 仍正常；growth fingerprint 升至 v4，并同步唯一规范 Section 21.6 的 formal resume 边界。
- 修复 Auth Contract selective-citation 绕过与高基数 evidence overflow：verifier 不再只检查 provider 引用的事实，而是对当前 Entry、当前 bounded security slice 内全部 complete Auth facts 重建语义 context 集；`unauthenticated`/`low_privilege`/`privileged` 多 context 冲突固定保持 `auth_context=unknown`，provider 只引用 public 或 privileged 一侧也不能升级 Reach。deployment gate 不参与 Auth 冲突，仍由独立 resolver 对全部 facts 解析。local unique Auth 固定引用最小 supporting fact；Reach 的 32-ID proof budget 先保留每个 Auth context 与每个独立 deployment-status bucket 的最小代表，再按序填充 provider citations，既不因 33+ duplicate facts 终止，也不因截断隐藏冲突。新增 unit/model、32-citation conflict、multiple-deployment、deployment 独立性与 injected production selective-citation 回归；禁止 formal resume 复用修复前 Reach/Auth artifacts。
- 终审收紧 open-discovery evaluator/CLI：finding 只允许绑定 formal/gap disposition，gap 只能产 `static_unknown`，三态 verdict、disposition 与 same-Growth typed negative-proof ownership 全部 fail closed；每条 proof 必须被恰好一个 rejected disposition 引用，missing/orphan/wrong-Growth/non-rejected proof 不再降为 unresolved。analysis ID 禁止跨 repository 重用，seed-side missing concrete finding/Growth ID 也登记全局 owner（同 repo 可共享、跨 repo fail closed）；non-linking seed 携带 stale concrete ID、ordinary matched status/verdict 冲突及 finding/Growth 链不一致均拒绝。真实 multi-Growth seed 现在允许 finding mapped Growth 是 declared Growth 的严格子集；`matched_*`、ordinary `chain`、nested `candidate` 逐 carrier 校验后才 union，合法 superset/singleton 组合保留，novel conflict 也 fail closed。所有未链接 positive seed 输出 deterministic seed-only `unresolved_discovery`（`recall_miss=true`、保留固定 identity/status、analysis 字段为 null），linked row 固定 `recall_miss=false`。CLI 发布改用 component-wise no-follow output-parent dirfd walk：output parent 必须预先存在，CLI 禁止 pin 前 recursive mkdir，missing-ancestor symlink race 不会在 immutable batch产生目录副作用；temp 创建/写入/清理、destination 检查及 Linux `renameat2(RENAME_NOREPLACE)` 全部 dirfd-relative，pin 前后竞态 output leaf/ancestor symlink 均不能重定向或覆盖 immutable input；所需 syscall/flags 不可用时不退化，path-resolution/symlink-loop RuntimeError 统一 rc=2 且无 traceback。focused evaluator/CLI `40 passed, 58 subtests passed`。
- 修复终审发现的 proof-gate bounded bypass：`apply_positive_proof_gate` 现在对 `static_vulnerable` 与 `bounded_under_modeled_assumptions` 使用同一 fail-closed 合同，Entry、ordinary Reach、verified Growth、proven flow、任一适用 assertion lifecycle coverage 或 candidate-gap obligation 缺失都会降为 `static_unknown`，并无损附加全部 exact `VERDICT_*` missing reasons；原本的 `static_unknown` 保持 unknown 但同样记录原因。actual bounded-to-unknown downgrade 同时移除矛盾的 `STATIC_EVIDENCE_COVERAGE_COMPLETE` assumption，保留有证据的 `MODELED_DEFAULT_CONFIGURATION` 与 modeled refs；原生 unknown 不制造 modeled-bounded assumptions。`not_entry_reachable` 继续在 maturation 以 same-Growth typed negative proof 进入 `rejected`，不作为 bounded bypass。新增 bounded+candidate gap、bounded+适用 lifecycle incomplete、7 obligations 全 false、unknown reason accumulation、certificate recomputation 与 production effective-Bound gap E2E 回归；conclude fingerprint 升至 v2，禁止复用修复前 conclude artifacts。assertions/certificates/production focused `99 passed, 4 skipped, 28 subtests passed`。
- 收紧 candidate maturation 四态不变量：`gap_eligible` 现在必须在 `local_growth_status` 或 `association_status` 至少一个维度明确为 `partial`，`complete/complete` 只能表示 `formal_eligible`；model 与 artifact validator 同时 fail closed。production 在 relevance 为 `dos_relevant_partial`、canonical association 已 complete 时显式把 Growth-local 维度保留为 `partial`，不再生成伪 all-complete gap。新增 Growth-partial/complete-link、association-partial/partial-link、all-complete gap 拒绝及 formal complete/partial 矩阵回归；focused Growth/maturation/artifact/production `160 passed, 4 skipped, 64 subtests passed`。
- Quality re-review 收紧最后两个相邻合同：request-local ArrayList 的 complete shape 只接受 exact one-argument append `add(E)`，indexed `add(int,E)` 即使位于 canonical attacker-bound loop 也保持 `partial` 且无 cardinality-proven marker。candidate link ownership 从 `(growth_id, entry_id)` 扩展为 `(growth_id, entry_id, link_status)`，reference validation、production 与 P0 aggregate 均要求 disposition `association_status` 精确等于唯一 link `status`；`formal_eligible` 因而只能引用 complete link，`gap_eligible` 可引用 partial 或 complete link但必须与自身 association status 一致。新增 indexed-add 真实 CodeQL fixture、partial-link 冒充 formal、gap partial/complete exact-match 及 P0 malformed 回归；真实 G1–G4 fixture `1 passed, 9 subtests passed`，focused Growth/maturation/artifact/production `152 passed, 4 skipped, 58 subtests passed`。
- Re-review 继续收紧 request-local cardinality proof：relevance 不再对拼接后的 coverage note 文本做 substring 晋级，只精确接受单条 canonical `request_local_container_write:<allowed-driver>:attacker_controlled_loop_cardinality_proven`，其中 allowed driver 限于 query complete 域实际可输出的 `key_driver_unclassified`、`attacker_value_driver`、`value_driver_unclassified`；拆分 marker、`_but_unproven`、任意前后缀和不可能的 `attacker_key_driver` 均保持 unresolved。Map 与 ArrayList complete 现在共用 `canonicalAttackerBoundForLoop`，固定为 non-wrapping canonical `for (int i = 0; i < directAnnotatedIntParameter; i++|++i)`：exact integer literal zero initializer、direct int attacker bound、唯一 increment、body 无 induction write缺一不可，Map 另要求 exact induction key；仅有 `attackerControlsLoop` 不足以让 List 晋级。byte/float/long、非零起点、derived bound、decrement、stable multi-statement、`count - 2` 起点的 fixed-two List、`count` 起点的 infeasible List、`i < 2 && count == count` attacker-tautology List 与 `i < count && false` infeasible-condition List fixtures 均锁定为 `partial` 且不得携带 cardinality-proven marker。真实 G1–G4 fixture `1 passed, 9 subtests passed`，query contract `1 passed, 30 subtests passed`，focused Growth/maturation/artifact/production `149 passed, 4 skipped, 54 subtests passed`。
- 激活并进一步收紧 request-local attacker cardinality 的真实 discovery：direct/embedded `ContainerGrowth.ql` 识别 supported handler 内由 concrete `Map`/`Collection` allocation 初始化的 exact local receiver，输出 handler-qualified receiver、local `field_path` 与 `escape_scope=request`。`complete` 同时要求 source-backed attacker loop、loop 外 zero-argument allocation 对 loop 的 lexical/CFG dominance、无第二 local access、逐迭代确定执行与新 entry 证明；当前 P0 Map 域仅接受 zero-argument concrete `HashMap.put` 加 exact canonical `ForStmt` induction `VarAccess` key，不再接受 string concat，stable zero-argument `ArrayList.add` 也必须是 unbraced direct body 或 braced loop body 的唯一 statement。conditional/continue/early-exit/multi-statement body 输出 `attacker_controlled_loop_per_iteration_execution_unproven`，same-key/concat Map 输出 new-entry-unproven，fresh-per-iteration Map 输出 instance-stability-unproven；只有 `attacker_controlled_loop_cardinality_proven` 可让 request-local candidate 进入 relevance，stored key/value 本身无需 annotated attacker parameter。新增 Spring 真实 CodeQL exact-key、concat、conditional Map/List、same-key、fresh-map、list 与 one-shot 回归；真实 G1–G4 fixture `1 passed, 9 subtests passed`，focused Growth/maturation/artifact/production `148 passed, 4 skipped, 49 subtests passed`。
- 收紧 disposition ownership：`evidence_ids` 中全部 `negative_proof:*` 必须与 `negative_proof_ids` 精确相等，缺失引用、额外未声明 proof 和跨 Growth proof evidence 均 fail closed；formal/gap 的唯一 candidate link 必须同时拥有 disposition 的 `growth_id` 与 `canonical_entry_id`。production 与 P0 aggregate 均重建 `link_id -> (growth_id, entry_id)` ownership，wrong-growth/wrong-entry link 会将 target 标为 malformed。
- 收紧 open-world candidate maturation：无 enclosing loop 的 async submission 不再按单次调用误删，保留到 repeatability、queue capacity 与 lifecycle；request-local container 只有 source-backed finite cardinality/byte bound 或确定低放大证明才可 negative reject，attacker-controlled loop witness 可进入单请求 cardinality Growth。`rejected` disposition 现在必须引用同 Growth 的 typed `negative_proof:*`，其 evidence 只能来自该 Growth 的 `candidate_evidence` `fact:*`；formal/gap/inventory 禁止携带 negative proof，`not_entry_reachable` 也发布同 Growth proof。exact `Math.min` clamp 仅接受严格正值的语法级 `IntegerLiteral` 与 supported Spring handler 中 exact annotated attacker-parameter `VarAccess`；constant expression、`static final` constant variable、server-derived nonconstant、零/负数均不得发布 complete clamp。hex/binary/octal/underscore integer literal 统一输出 canonical decimal，避免 downstream 十进制 Bound verifier 误判。Growth implementation fingerprint 升至 v2，禁止复用本修复前的 schema-2.7 growth stage。
- 修复 P0 aggregate reference validation 被 artifact-name/id-kind 键错配整体跳过的问题：aggregation 现在仅从 Growth candidate evidence 与 Entry security facts 重建可信 fact ownership，并构造 `growth_fact_ids`、`entry_security_fact_ids`、`security_fact_ids`、`negative_proof_growth_ids` 后对全部 parsed schemas 执行 reference validation；跨 Growth disposition/proof、跨 Growth proof evidence 与 `fact:oracle_label` 自授权输入均将 target 标为 `malformed`。schema-invalid `candidate_evidence` 类型也只记 target malformed，不再在 known-map 重建时抛出未处理异常。
- 将 schema/tool 升至 `2.7/0.6.0`，raw Growth 改为 `formal_eligible`、`gap_eligible`、`rejected`、`inventory_unresolved` 四态 maturation；新增 `candidate_negative_proofs.jsonl`，高 fanout 保留 inventory，request-local、finite-keyspace、server-controlled 等确定性负例携带 source-backed negative proof。formal resume 重新执行 2.6/0.5.0 stages，P0 aggregate 新增 `aggregate_candidate_negative_proofs.jsonl`。
- Growth Contract 升至 v5/provider schema v5/cache v9：kind、dimension、attacker target 改由 bounded static facts 本地推导；provider 只回传 attacker evidence IDs。semantic-invalid 仅允许一次不回显原响应的 correction request，第二次 fail closed，invalid response 不入 cache。唯一 complete Auth facts 本地派生 Auth Contract，partial/冲突才调用 provider。
- positive verdict proof gate 改为 assertion-scoped lifecycle coverage；registration coverage 改为 framework-specific exact pattern identity。修复 conclude 仍比较旧 `verified_relevant` 状态导致 formal candidates 全部降为 unknown 的迁移残留。
- Bound modeled domain新增 direct `ByteBuffer.allocate/allocateDirect` absence proof 与 exact `Math.min(..., positiveLiteral)` typed `clamp` candidate；decoder、artifact schema、deterministic Bound evaluator和 direct/embedded CodeQL pack 同步。unsupported/custom/reflection domain 继续 partial，未放宽 async Release。
- 新增只读 open-discovery evaluator `scripts/evaluate_open_discovery.py`：静态扫描完成后才与 PoC seed matches 做差集，固定输出 `seed_linked_static_vulnerable`、`novel_static_vulnerable`、`novel_bounded`、`source_proven_negative`、`unresolved_discovery`；PoC 未命中不会自动计为 FP，production 不读取 novelty/seed 标签。evaluator 同时接受普通 `matches.jsonl` 与 PoC-33 `truth_dispositions.jsonl`，只按 strict `owner/repository` scope 内的具体 finding/Growth ID 链接，拒绝重复 identity、非法 collection、跨 artifact disposition/proof 不一致；output 必须不存在，并经 0700 同父临时目录一次原子发布，既存 symlink/hardlink 不得覆写输入。
- 修复 P0 与 framework-limit 真实 CodeQL E2E 的迁移断言：direct allocation modeled domain 会在同一 `/post-guard` Entry 下发现额外 `direct_allocation` Growth，Servlet 未晋级候选保持 `inventory_unresolved`；framework-limit fixture 现在精确绑定四条原 framework limit 与一条 `numeric_min_literal` clamp 的 anchor/evidence/configuration/encoding，不以旧四项集合遮蔽新增真候选。

## 2026-08-28

- 更新工具对 PoC-33 21 库做 formal full：`results/java_web_dos_batch/poc33-p02-20260828_174800-full/`。18/21 completed，3 个 target 在 16 次真实 provider 重试后仍失败（HertzBeat `LLM_RESPONSE_SENSITIVE_CONTENT`，ThingsBoard/WGCLOUD `LLM_RETRIES_EXHAUSTED`）。产出 87 条 `static_unknown` finding / 84 个 family，0 `static_vulnerable`。离线 recall 14/33 `full_chain_finding`；人工审查 family 级 TP=17、FP=67、precision=17/84=0.202，33 条基准审查覆盖 16/33。报告：`results/java_web_dos_batch/poc33-p02-20260828_174800-eval/TP_FP_REPORT.md`。
- Growth relevance 与 candidate association 不再把 >64 条 Entry link 的 fanout 当成 target failure。Rebuild 一类同文件 source-order 高扇出会保持 `unresolved`（`RELEVANCE_LINK_FANOUT_EXCEEDED` / `ASSOCIATION_ENTRY_FANOUT_UNRESOLVED`），不中断其余候选。新增 RED/GREEN 回归。
- Task 10 新增只编排静态验收的 `scripts/run_poc33_demo_acceptance.py` 与完整回归：`fast`、`codeql-fixtures`、`poc33-entries`、`poc33-real-provider-full`、`poc33-offline-eval` 五层均使用 immutable run ID、canonical 205 manifest 与 `poc/manifest.json` 的 digest-bound 21-target selection；driver 不运行动态 DoS，不用 mock 冒充 provider completed，并在 full/offline 层严格校验 formal/fail-closed、0600 私有 audit、P0 aggregate、同 run ID 派生产物和 rollout blocker matrix。
- 首轮真实 entries canary `poc33-p02-20260828_001609` 暴露 exploratory source-hint 筛选把每库实际查询静默缩减为 3–8 条，因而被 8/8 gate 正确拒绝。新增 RED/GREEN 回归后，formal 与 explicit exploratory entries 都执行六个 Entry family 加 interposition/security 共 8 条 selected queries；exploratory 只改变 query failure policy，不再改变 coverage surface。删除已失效 hint scanner，并把 entries implementation fingerprint 升为 `production-v2.6-poc33-demo-repair-entries-v2`，阻止 pre-fix stage resume。
- flows stage 仅为唯一 canonical、`dos_relevant_partial` 且 partial-link、同时缺正式 flow 的 E/G pair 生成一个 `unmodeled/partial` gap path；generic unresolved 不生成，complete link 缺 flow 继续视为损坏。stage metadata 新增 `partial_gap_flow_count`，flows fingerprint 升为 `production-v2.6-poc33-demo-repair-flows-v2`。持久化 production resume 复验覆盖 P0 13/13、MQTT 2/2、Netty 2/2、Servlet 6/6 finding-eligible pairs，所有未完成 Reach/lifecycle proof 的结论保持 `static_unknown`，provider 重复调用为 0。
- evaluator 的 supported-chain recall 只排除同时带 `ENTRY_DYNAMIC_REGISTRATION_UNPROVEN` 与 `GROWTH_SINK_MATCHED` 的 explicit deferred Growth；新 run 直接消费 formal `finding_families.jsonl` 或 aggregate `aggregate_finding_families.jsonl`，两者并存时拒绝歧义，`--static-audit` 继续只用于 historical baseline。
- 最终 immutable entries canary `results/java_web_dos_batch/poc33-p02-20260828_152629-entries/` 通过：21/21 completed、每库 8/8 selected queries、总计 168 queries、0 diagnostics、0 skipped，并生成 selection/plan digest 与 `acceptance_manifest.json`。无显式远程授权的同 run ID provider prerequisite 检查返回 exit 3 / `REMOTE_LLM_AUTHORIZATION_MISSING`，仅写入 `poc33-p02-20260828_152629-provider-prerequisite.json`；未创建 `-full/`，未运行 offline recall/evaluation，也未启动 178/205-target full。
- Task 10 最终验证：network-free fast gate `797 passed, 26 skipped, 548 subtests passed`（734.29s；仅两个既有 fork DeprecationWarning）；真实 CodeQL Entry/Growth/Lifecycle/production-E2E gate `35 passed, 131 subtests passed`（4170.45s）；focused acceptance/evaluator/production `59 passed, 17 subtests passed`；`compileall` 与 `git diff --check` 通过。

## 2026-08-27

- Task 9 关闭剩余 supported Entry→Growth 形状但不放宽 deferred 边界：Servlet `doFilter` 中 constructor-injected final interface field 仅在 exact method signature 只有一个 source concrete implementation 时进入 depth≤3 proof-carrying path，multiple implementation 继续 fail closed；source-backed `InputStream` handler 到 bounded `ByteArrayOutputStream.toByteArray` 在缺少 global data-flow witness 时只发布 exact-call-path `partial/static_unknown`，不得升级 proven/complete。新增中性 HertzBeat/Grobid 等价 fixtures，association 与 formal flow 共用 source/sink/call-path evidence。
- JAX-RS route 统一按 class/method path canonical slash join，annotation-only gap 也不再产生 `//`；CodeQL 只把“Guice Binder + Class 参数、唯一 singleton bind、唯一 Component multibinding”的 source helper视为 static registration，并把未注解 `InputStream` 统一标为 `stream`。bounded source fallback 新增 Sisu `WireModule(SpaceModule(..., GLOBAL_INDEX))` → `@Named` Guice root → 唯一 installed child → semantics-verified helper 链，支持显式与 static-wildcard helper import，duplicate install/bind、helper lookalike 和多义 owner 均 fail closed；真实本地 Concord 源码已恢复规范化 `POST /api/v2/process/{id}/log/segment/{segmentId}/data` 三个 attacker-input rows。
- gRPC 新增完全中性的 legacy generated streaming、local-variable service construction、唯一 0–2 forwarding registration 与 ternary two-observer fixture；现有 generic `GrpcEntries.ql` 已直接产生两个 complete streaming handler，因此未加入目标特判。旧数据库缺少 handler compilation unit 时只作为 `database_source_coverage_missing` coverage gap 审计，不能伪造 Entry；四条 custom Reactor MQTT dispatch 回归固定保持 `entry_gap + growth_only`、无 finding/verdict。
- Task 9 fresh gate 通过：JAX-RS source/truth disposition `47 passed, 4 subtests passed`；Entry CodeQL `11 passed, 21 subtests passed`；Flow/lifecycle CodeQL `17 passed, 84 subtests passed`。production oracle leakage 扫描为零，三份变更 query direct/embedded mirror byte-identical，`compileall` 与 `git diff --check` 通过。
- conclude stage 新增 strict `FindingFamily` 聚合与 `finding_families.jsonl` 原子产物：family identity 绑定 framework/protocol、registration、handler、Auth/deployment、resource、Reach 与 verdict，route alias 可合并但安全上下文、资源或结论不同绝不合并；全部 member finding/certificate/Entry/Growth 引用无损保留，primary 只按 coverage、unresolved completeness、amplification 与 stable ID 选择，family ID 从公开 semantic record canonical hash 重算，拒绝 truth/oracle 输入和伪造 identity。
- candidate disposition 新增严格 `dos_relevant_partial` 状态；`verified_relevant` 与 `dos_relevant_partial` 均要求且只允许一个 canonical link，只有这两类能进入 conclude。rejected、not-entry-reachable 与 generic unresolved 不再生成 finding/family；高价值 partial 以 `GROWTH_DOS_RELEVANT_PARTIAL` 保留 unresolved Growth，且只能得到 family-level `static_unknown`。
- certificate/conclude 新增 positive proof gate，逐项重算 complete Entry coverage、ordinary-attacker Reach、verified Growth、proven flow、complete lifecycle family coverage 与 candidate-relevant gap-free；调用方提供的 verdict 不能越过 gate，positive verdict 的任一 obligation 缺失均降为 `static_unknown` 并发布稳定 `VERDICT_*` reason code。报告首屏改为 family-level priority/verdict/amplification/Reach/Bound/missing-evidence 表，exact finding/certificate 移入 audit section；summary 同时保留 family-level 与 exact-finding 计数，batch 新增 `aggregate_finding_families.jsonl`，私有 audit 聚合边界不变。
- Task 8 fresh gate 通过：family/assertion/report/aggregation `53 passed, 17 subtests passed`；production/artifact/candidate/P0 end-to-end `80 passed, 41 subtests passed`；`compileall` 与 `git diff --check` 通过。
- lifecycle Bound 新增 path-exact framework-limit normalization 与四类 complete source domain：Jackson `StreamReadConstraints.maxStringLength(literal)` 必须通过同一 fluent constraint 的 `validateStringLength` 约束 exact Growth driver；Netty pipeline 中先于 exact `FullHttpRequest` handler 注册的 `HttpObjectAggregator(maxContentLength)` 必须约束 body-derived allocation；Servlet `@MultipartConfig(maxRequestSize)` 仅绑定 request-derived allocation；Solr `formdataUploadLimitInKB` 要有 form-urlencoded pre-parse terminal reject。四类 provenance 统一标为 `literal`，不再把显式配置冒充未证明的 library default。formal lifecycle executor 显式调用 framework normalizer；只有 exact framework/encoding、同 Growth receiver/field、request scope、pre-growth path coverage、finite literal、checked rejection 与 complete query evidence 同时成立才为 `effective`，encoding/profile/provenance mismatch、post-growth、fail-open、partial coverage 保持 unknown/ineffective。
- `LifecycleCoverage.ql` 不再因“查询执行过”就对所有 Growth/family 发布 complete absence：Guard、Bound、Release 各自具有显式 `familyModeledDomain`，未覆盖 API/config domain 固定输出 `partial/lifecycle_family_api_domain_unmodeled`；reflection/custom dispatch、未知 finite queue capacity 与 Netty async dispatch继续 partial，worker/timer/callback/consumer/ACK 等异步 Release 仍不作为同步减少证明。
- 新增独立 framework-limit CodeQL fixture，四类 family 均发布 growth-anchored complete Bound row 与 exact bound coverage；未绑定 Jackson builder、Object 型 Netty message、与 request 无关的 multipart allocation 均不得发布 complete Bound。direct/embedded query 与 shared QLL 保持 byte-identical。Task 7 fast/contract suite 为 `92 passed, 10 skipped, 132 subtests passed`，五条 selected lifecycle query 全部 compile，真实 framework-limit CodeQL fixture 通过；完整多框架 fixture 留到 Task 10 最终 gate，避免对中间态重复执行超长编库。
- Growth Contract 升级为 strict 19-field DoS Growth Contract：显式记录 attacker value space、growth function、amplification、requests-to-pressure、retention、failure mechanism、contract status 与 rejection reason；缺失/额外字段、超长或含 secret/source-code 的自由文本全部 fail closed。prompt/schema/cache identity 升至 `growth-contract-v4` / `growth-contract-schema-v4` / cache v8，旧 v7 cache 即使带合法旧 HMAC 也只作 cold miss。
- bounded slice 新增 driver origin、value space、escape scope、retention、amplification、loop multiplicity、field identity、materialization phase 与 known-limit location typed facts；feature-state 配置不再伪装成 limit。deterministic verifier 仅在 DoS-relevant status、可支持的 failure pressure、attacker-backed driver/value space、retention/amplification citation 全部与 static facts 精确一致时发布 `verified`，server-controlled、low-amplification、false citation 与语义未知均保持 rejected/unresolved。
- Task 6 定向回归通过：Growth/schema/artifact/production `103 passed, 67 subtests passed`；完整 provider/cache 套件 `117 passed, 146 subtests passed`（仅两个既有 fork DeprecationWarning）；`compileall` 与 `git diff --check` 通过。
## 2026-08-26

- association 与 formal flow 现共用 `Flows/EntryGrowthDomain.qll` proof-carrying domain：framework source、exact Growth demand、global data-flow、unique concrete/interface target 与 depth≤3 callable path 只建模一次，same-handler、unique helper、constructor/lambda、Servlet request wrapper 与 Armeria aggregation 可携带同一 complete row，custom async/reflection/ambiguous skeleton 继续 partial。bounded call path 显式展开 depth 0–3，避免递归 string path 物化写爆 CodeQL predicate cache。production 仅在 association row 与 formal row 的 source/sink、Entry attacker source、demand、call path、phase 完全一致时发布 complete `CandidateEntryLink`，缺 row 固定记录 `FLOW_CODEQL_ROW_MISSING`；删除从 partial links 合成 `unmodeled_flow` 的交叉乘积，route alias canonicalization 只保留一个 proven flow，无关 handler 不再获得 synthetic path。Flow verifier 改用 identifier-token 绑定 source/sink，校验 Entry/Growth location identity、entry-rooted bounded call edges 与 proof provenance，并把 path/Entry/Growth IDs 纳入 evidence；新增 route-alias/unrelated fixture、CodeQL shared-domain mirror/compile、association/flow witness、path-cache 与 substring/call-path fail-closed 回归。
- Growth stage 新增 LLM 前 deterministic DoS relevance gate，固定区分 `contract_eligible`、`dos_relevant_partial`、`rejected`、`unresolved` 及 seven-class amplification；attacker-sized direct allocation、request body materialization、field-backed high-cardinality retention、attacker-loop queue submission 才能进入 Growth Contract，高置信 server-sized/server-file、fixed-key、single-submit 和 test/benchmark-only screening row 直接拒绝，普通 partial noise 只留 disposition，parser/read-all、field retention、queue 等高价值 partial 最多保留一个 canonical Entry 的 `static_unknown` gap。production 在 relevance precheck 后才调用 Auth/Growth LLM；privileged/default-disabled/optional Entry 转 `not_entry_reachable` 后不再调用 Growth provider，rejected/no-entry/multi-entry ambiguity 不生成 verified Growth、flow、certificate 或 finding cross product；同一 Entry 的多候选会显式复用其 cached Auth/Reachability decision，不再继承上一候选的循环局部状态。G1–G4 raw queries 同步收紧：allocation size 要有 handler attacker-parameter witness，否则 partial；field container 分离 key/value driver、fixed key 与 escape scope；async loop 输出真实 `submission_count`，one-shot 保持 low amplification；read-all 区分 request stream、unclassified stream、server file 与 BAOS/parser partial。direct/embedded Growth queries 与 shared loop witness 保持 byte-identical，并新增 10 类 relevance RED/GREEN、provider-call funnel、Auth cache ordering 和真实 CodeQL fixture 回归。
- formal entries 新增第八条 `EntrySecurity.ql`（direct/embedded byte-identical）及独立 strict decoder/query-family contract，提取 source-backed method/type auth annotation、Servlet `@ServletSecurity`、静态 Spring Security matcher 与显式 profile/property/optional deployment gate；selected security query failure 在 formal 模式继续 fail-closed，只有显式 exploratory partial 模式记录 query gap。typed fact 只能按唯一 handler identity 或唯一静态 route 绑定 normalized Entry，dynamic matcher 不做近邻绑定；文本 fallback 全部降为 `partial`，不再从 annotation 文本证明 public。normalized complete registration 作为正向 `default_enabled` deployment evidence，显式 conditional gate 原子替换该默认，未通过“缺少 conditional annotation”反推部署状态。`ReachabilityDecision` 现携带 `deployment_status` 与稳定 reason codes，只有 complete `unauthenticated|low_privilege` auth 加 `default_enabled` 才发布 `ordinary_attacker_reachable`，privileged/default-disabled/optional 分别闭合为 `not_entry_reachable`，其余保持 `unknown`。配置 allowlist 同步支持安全的 active profile 与 feature/module enabled defaults，敏感 key 规则不变；新增真实 CodeQL security fixture、query mirror、schema、production 和 reachability 回归。
- 批准 P0.2 evidence-funnel repair 并把 artifact/tool baseline 升至 `2.6/0.5.0`、Growth Contract response schema 升至 `growth-contract-schema-v4`；six-stage production fingerprints 全部切换为 `production-v2.6-poc33-demo-repair-*`，2.5 stage manifest 只能作为历史输入、不得 formal resume。新增 strict `finding_families` artifact schema/allowlist，生成与报告逻辑留待后续 family task 原子接入。
- 新增只读 PoC-33 21 库 demo evaluator：冻结 `eligible_positive`、`hard_negative`、`weak_negative`、`unscored` taxonomy，分别报告 supported-chain recall、ordinary-scope positive recall、hard-negative safety 与历史 TP/FP precision；CLI 显式接收 static batch、recall、historical static audit（仅基线）和 dynamic 根目录，输出 `case_matrix.jsonl`、`metrics.json`、`REPORT.md`，并拒绝向任何输入目录写回。
- 新增 21 库 demo 的证据驱动修复计划：`docs/research/2026-08-26-poc33-21-library-demo-repair-plan.md`。计划基于当前 formal batch 的 10,678 raw Growth、95/1,177 complete/partial links、44/1,234 proven/partial flows、14/319 verified/unresolved Growth、1,277 条全 unknown findings，以及独立动态队列 TP=9/FP=29/blocked=11，确认主因是 evidence funnel、Reach/Bound 和输出交叉乘积，而不是 provider 或 batch retry。
- 计划保留 v2 固定公式、三态结论、formal fail-closed 与 async/custom/reflection deferred 边界；推荐按离线 evaluator -> candidate relevance -> proof-carrying E→G -> DoS Growth Contract -> Reach/EffectiveB -> finding-family report -> immutable PoC-33 gate 的顺序修复。当前仅新增计划与分析记录，未修改 analyzer、CodeQL query 或历史 results。
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
