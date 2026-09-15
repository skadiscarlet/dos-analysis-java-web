# Resource Lifecycle v1.2 分析语义

v1.2 实施中：正式性质由 `properties.py` 统一发布，评价只选择并比较，不从 `property_states` 推断上界。项目接入、证据分片和源码验收进度见 `docs/execution/lifecycle-v1.2/STATUS.md`；以下 v1.1 完成数字仅作历史基线，不代表 v1.2 验收。

## 定位与入口

Resource Lifecycle v1.1 是独立于现有 v2 P0 formal pipeline 的离线状态分析链。它不读取旧 lifecycle candidate 中的 `actual_reduction`、`effective_bound` 等预计算结论，也不改变 schema/tool `2.5/0.4.0` 和三值静态结论。入口是同一 `dos-web-analyzer` 中的五个 `resource-*` 命令，包含真实源码成对评价 `resource-source-evaluate`。

输入来源分为：真实 CodeQL 源码事实 `static_verified`、可信契约 `trusted_contract`、仅供局部候选验证的 `llm_proposed` 和显式标记的 `manual_fixture`。报告必须区分真实源码、导入静态事实和人工 IR；人工 IR 中正确填写的 holder/transition 不算作 CodeQL 提取能力。

## IR 与状态

一个 `ResourceFamily` 由分配位置、有限上下文和资源类型确定；`AbstractInstance` 区分可强更新的 `recent` 与代表历史集合的 `summary`。`Holder` 明确请求栈、任务、容器、字段或局部持有位置，并记录 request/task/session/connection/instance/global scope。`Event` 表示请求、方法或异步阶段，`Transition` 保存 guard、有序 effects、正常/异常/拒绝/取消类别和前提。

求解状态分别保存：

- 可能持有边 `(instance, holder)`；
- 各资源族的分配数、被持有实例数和方法内峰值区间；
- 显式 close obligation、所有路径均已释放的 must-release 事实；
- 身份、资源类型、单项大小上界和精度损失原因。

这三个维度不合并成一个无单位 resource 值：`held_instances`、`item_size_bytes`、`close_obligation` 各自产生 `DimensionResult`，并携带 scope、assumptions、reason codes 和 evidence ids。

## 状态转移

| Effect | 状态含义 |
| --- | --- |
| `create` | 新增抽象实例计数；需要显式关闭的族同时产生 obligation。 |
| `retain` | 新增指定 holder edge；同一实例的额外引用不重复算作新对象。 |
| `drop` | 只删除指定 holder edge。recent+exact 可强更新；summary/不确定身份只记录 weak-update unknown。 |
| `release` | 满足显式 close obligation，不删除 Java heap holder edge。summary 的一次 release 不关闭整个历史集合。 |
| `dispatch` | 未绑定任务时只保留保守 capture 与 unknown；真实 TaskBinding 由主工作列表在接纳成功时调用同一 `apply_effect(retain)`。 |
| `unknown_call` | 保留相关状态并记录精确调用原因，不默认纯函数或释放。 |

转交由 retain/drop 组合，复制必须产生新的 create。请求返回只解除请求 holder；无 holder 表示对象可达性证据已结束，不承诺 GC 已执行或物理内存已下降。

条件当前作为路径事实保存在 effect/transition 中。求解器保守遍历所有已提取 transition，不在 Python 内重新解释任意 Java 布尔表达式；分支可行性必须由上游静态事实或可信契约限定，缺口通过 `coverage_complete=false` 进入 unknown。

## 分支、循环与跨事件

分支汇合对 may-hold、已创建实例和未关闭义务取并集；must-release 取交集。计数区间下界取各分支最小值，上界取最大值；任何无穷/未知上界传播为未知。峰值取所有路径最大值。

工作列表按稳定 transition id 顺序迭代。v1.1 的求解键同时含 caller/task 控制位置与资源状态；同一状态路径在负效应前保持分离，报告快照才合并。`max_steps`、每控制配置更新次数与 wall-clock timeout 均有显式预算；超限分别记录 `analysis_budget_exhausted`、`iteration_limit`、`solver_timeout`，不假称已实现 widening，也不产生“已证明无界”。

异步契约区分 submit、start/dequeue、complete、reject 和 cancel：

- 唯一、同 callable 的 internal `source_submit_binding` 接通任务；接受提交后才建立任务捕获，支持的拒绝分支不 capture；
- dequeue 只是 task holder 的阶段变化，不等于完成；
- 正常/异常终止先沿真实可达 callback CFG 应用效应，再只 drop 对应 task holder；executor termination 字段不能代替 callback close；
- cancel 只有明确 phase-matched removal relation 才 drop capture，仍不等于 close；缺取消关系保留 unknown；
- inline 与 queued 是契约字段，不根据 `Executor` 接口名猜测。

`exit_states` 只保留 request 出口，不能把 request 返回时任务仍在途的 obligation 判成泄漏。主求解同时保存 `property_states/property_traces`；`after_task_termination:<task_id>:normal|exceptional` 的 DimensionResult 仅适用于确已到达的 task 出口，`all_tasks_terminated_after_request` 仅适用于 request 已返回且该路径已提交任务全部终止的切面。`termination_guaranteed` 独立记录；未知调度、非终止、取消或缺失拒绝回接不能由存在 TaskExit 边消除。时间缺口按 capture 所属 family 作用，源码 coverage 与 identity/budget 缺口在条件切面仍保留。`_async_stages` 只序列化已求解状态，无单独完成/取消计算。

## 有限上界检查

候选上界只接受 `static_verified` 或 `trusted_contract`。检查器同时要求：初始状态成立、相关转移保持、写入者覆盖完整、并发容量操作具有原子性，且状态求解没有 identity/coverage/budget/unknown-call 精度缺口。queue 候选还必须显式绑定同一个可信 `ExecutorContract`、resolved holder 和 target event，并与 writer 逐项一致；contract 的 scheduling、capacity 和 atomicity 由 checker 读取，不能由 candidate 自报替代。任一条件失败都返回带原因的 `unknown`；候选不归纳不等于程序无界。

v1.1 的 task population 从 `(q,a)=(0,0)` 开始，按实际 TaskBinding、TaskExit、PopulationEffect 与可信 ExecutorContract 检查转移：direct accept 为 `(q,a+1)`，enqueue 为 `(q+1,a)`，assign slot 为 `(q-1,a+1)`，start 不增计数，正常/异常终止为 `(q,a-1)`，拒绝和 phase-matched cancellation 按各自契约处理。逐项验证守卫、身份、全部 writer 与出口覆盖，导出任意有限次外部接纳下 `0<=q<=K`、`0<=a<=W` 和 `q+a<=K+W`。a 包括已保留但尚未开始运行的执行槽。

`initial_holds/transitions_preserve/covers_writers` 是派生结果；兼容 candidate 布尔值不能自证。未知或符号 K/W、未支持拒绝策略、缺 terminal 或额外 writer 均保持 unknown。非 task queue 候选因 `derived_invariant_model_unavailable` 保守退化。人工计数对照独立标为 model-only：fresh insert 的 distinct instances 增加 1，fixed replacement 的 occupied positions 不变，同对象 retain 不增加 distinct instances。

该上界仅覆盖一个已建模执行器的已接纳任务，不包括等待提交的调用者、其他执行器、结果缓存或字段持有；它不是总内存上界。单项大小未知时 `item_size_bytes` 仍为 unknown。无通用 SMT、吞吐率或调度最终性证明。

## 真实源码固定输入评价

`resource-source-evaluate` 固定十二例的源码、入口、候选和 raw facts，先运行完整模型，再仅删除跨 callable/task relations 及其驱动 transitions，添加明确 coverage gap 后重新求解。两个模式均消费同一份事实快照；新增提取覆盖须另行与基线比较，不计入此传播消融。

条件切面只有在求解完整终止、相关 coverage gap 已清除且 state 无 unknown reason 时才能发布 bounded。unknown population 不发布局部 K+W。task terminal 缺 exception successor 默认保留缺口；仅 exact captured allocation、exact source dispatch 且 source body 为空的 singleton-finally close 可提供窄 no-throw 证明。

## 输出与证据

`lifecycle_status` 只有 `bounded`、`obligation_gap`、`unknown`、`not_applicable`：

- `bounded`：只表示记录的 dimension/scope/assumptions 下有已检查上界；
- `obligation_gap`：支持语义下至少一个具体出口仍有显式关闭义务；
- `unknown`：身份、覆盖、调用、契约、大小或预算不足；
- `not_applicable`：该资源族不要求对应义务。

`impact_status` 默认 `not_evaluated`。Resource Lifecycle v1 不输出 vulnerability 布尔量，不把 unknown 改称 unbounded，也不把静态性质提升为动态 confirmed。

每次 analyze 保存 facts snapshot、输入与契约 identity、预算、LLM mode、结果摘要和 `evidence.json`。每个出口 derivation 记录 transition、规则、evidence ids、guard/assumption/effect condition、出口状态结论及代码位置。analyze/replay 共用 owner-only、bounded run-directory lock；同一目录的并发发布会被串行化，mode 切换只清理已知 stale artifact。`resource-replay` 从同一个有界 `O_NOFOLLOW` fd 获取 facts/private snapshot 的 bytes、SHA 和 JSON，校验完整 Java source-tree snapshot、extractor、contract version、tool version、budget、LLM identity 和 cache identity，然后重新验证 recording、调用 solver、重建 evidence 与 `summary.md`；它不重复打印已存结果。

## 子证明依赖编码

证据存储中的 `path_dependency_encoding` 明确子证明依赖位于各 child 的 `evidence_ids`，不在顶层重复展开。child 的 `unit_id/scope/property_event_id/property_derivation_index` 解析到 `lifecycle-results.json` 中同一 solved property record；完整 rule_ids/rule_dependencies 从该 trace 获取，整个结果由 `result_sha256` 绑定。child 保留 transition_ids、trace evidence_ids、state、源码位置和 relation refs。replay 重新生成并比较全部结构，错绑索引或修改证据仍会不一致。JSON 读取上限保持 16 MiB；超大输出仍是支持范围限制，不能自动扩大读取预算。

## LLM 摘要信任边界

LLM 只能提出局部方法摘要。当前实现只支持 `--llm replay` 的离线接口与证据闭环，`--llm live` 明确拒绝；recording 不是一次真实 provider 调用通过的证据。验证依次检查 schema、call-site 路径/行/列、caller 文件与完整 Java source-tree SHA、canonical exact source callee、参数映射、操作/数据流、资源身份和正常/异常出口覆盖。普通 interface/base virtual dispatch、external callee、return escape、源码快照变化或同行其他 AST 的事实都不能借证。

正向 proposal 只可能消费目标 call-local slice 中由 `static_verified` 事实支持的 may-effect。当前 CodeQL query 没有独立的、非 executable callee-summary witness：若 proposal 复述 caller program 已存在的 `create`、`retain` 或 `dispatch` operation，validation 可保持 `verified` 且保留 `display_effect_ids`/provenance，但 apply 层会记录 `llm_proposed_effect_already_static`、清空对应 `usable_effect_ids`，避免 create 重复计数或 dispatch 重复展开。因此当前生产路径的 recorded summary 是 audit/display-only，不增强 solver；未来只有在新增独立静态 witness 且 operation 尚未执行时，正向 may-effect 才具备进入状态的语义接口。LLM 提议的 `drop`/`release` 即使结构完整也只展示，不能删除 may-hold、证明 must-release 或 bounded；exceptional callee effect 也没有 CFG 证明。原 `unknown_call`、出口缺口和 coverage gap 始终保留，缓存命中不提升 source trust。
