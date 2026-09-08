# Resource Lifecycle v1 分析语义

## 定位与入口

Resource Lifecycle v1 是独立于现有 v2 P0 formal pipeline 的离线状态分析链。它不读取旧 lifecycle candidate 中的 `actual_reduction`、`effective_bound` 等预计算结论，也不改变 schema/tool `2.5/0.4.0` 和三值静态结论。入口是同一 `dos-web-analyzer` 中的四个 `resource-*` 命令。

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
| `dispatch` | 要求明确 executor contract；捕获与阶段展开由事件模块调用同一 `apply_effect`。 |
| `unknown_call` | 保留相关状态并记录精确调用原因，不默认纯函数或释放。 |

转交由 retain/drop 组合，复制必须产生新的 create。请求返回只解除请求 holder；无 holder 表示对象可达性证据已结束，不承诺 GC 已执行或物理内存已下降。

条件当前作为路径事实保存在 effect/transition 中。求解器保守遍历所有已提取 transition，不在 Python 内重新解释任意 Java 布尔表达式；分支可行性必须由上游静态事实或可信契约限定，缺口通过 `coverage_complete=false` 进入 unknown。

## 分支、循环与跨事件

分支汇合对 may-hold、已创建实例和未关闭义务取并集；must-release 取交集。计数区间下界取各分支最小值，上界取最大值；任何无穷/未知上界传播为未知。峰值取所有路径最大值。

工作列表按稳定 transition id 顺序迭代。`max_steps`、每事件更新次数和 wall-clock timeout 都有显式预算。预算耗尽、timeout 或 widening 只产生不同 reason code 的 `unknown`，绝不产生“已证明无界”。正常与异常出口独立保存，最终 all-exits 结论检查所有可达出口。

异步契约区分 submit、start/dequeue、complete、reject 和 cancel：

- 接受提交后才建立任务捕获；拒绝分支按契约决定是否捕获；
- dequeue 只是 task holder 的阶段变化，不等于完成；
- completion 只有可信契约明确允许时才 drop capture；
- cancel contract 未知时保留捕获并返回 unknown；
- inline 与 queued 是契约字段，不根据 `Executor` 接口名猜测。

## 有限上界检查

候选上界只接受 `static_verified` 或 `trusted_contract`。检查器同时要求：初始状态成立、相关转移保持、写入者覆盖完整、并发容量操作具有原子性，且状态求解没有 identity/coverage/budget/unknown-call 精度缺口。queue 候选还必须显式绑定同一个可信 `ExecutorContract`、resolved holder 和 target event，并与 writer 逐项一致；contract 的 scheduling、capacity 和 atomicity 由 checker 读取，不能由 candidate 自报替代。任一条件失败都返回带原因的 `unknown`；候选不归纳不等于程序无界。

当前 v1 数值域是非负计数区间和由静态/契约层提供的简单参数化上界。符号上界会附加“符号值有限且为正”的显式前提。它不内置通用 SMT 后端；没有伪造 sat/unsat 记录，数值域之外的问题直接保守为 unknown。容量只证明精确 queue scope 的 item count；同一 resource family 的多个 queue 分别输出，当前不合成 family 总上界。单项大小未知时 `item_size_bytes` 仍为 unknown。

## 输出与证据

`lifecycle_status` 只有 `bounded`、`obligation_gap`、`unknown`、`not_applicable`：

- `bounded`：只表示记录的 dimension/scope/assumptions 下有已检查上界；
- `obligation_gap`：支持语义下至少一个具体出口仍有显式关闭义务；
- `unknown`：身份、覆盖、调用、契约、大小或预算不足；
- `not_applicable`：该资源族不要求对应义务。

`impact_status` 默认 `not_evaluated`。Resource Lifecycle v1 不输出 vulnerability 布尔量，不把 unknown 改称 unbounded，也不把静态性质提升为动态 confirmed。

每次 analyze 保存 facts snapshot、输入与契约 identity、预算、LLM mode、结果摘要和 `evidence.json`。每个出口 derivation 记录 transition、规则、evidence ids、guard/assumption/effect condition、出口状态结论及代码位置。analyze/replay 共用 owner-only、bounded run-directory lock；同一目录的并发发布会被串行化，mode 切换只清理已知 stale artifact。`resource-replay` 从同一个有界 `O_NOFOLLOW` fd 获取 facts/private snapshot 的 bytes、SHA 和 JSON，校验完整 Java source-tree snapshot、extractor、contract version、tool version、budget、LLM identity 和 cache identity，然后重新验证 recording、调用 solver、重建 evidence 与 `summary.md`；它不重复打印已存结果。

## LLM 摘要信任边界

LLM 只能提出局部方法摘要。当前实现只支持 `--llm replay` 的离线接口与证据闭环，`--llm live` 明确拒绝；recording 不是一次真实 provider 调用通过的证据。验证依次检查 schema、call-site 路径/行/列、caller 文件与完整 Java source-tree SHA、canonical exact source callee、参数映射、操作/数据流、资源身份和正常/异常出口覆盖。普通 interface/base virtual dispatch、external callee、return escape、源码快照变化或同行其他 AST 的事实都不能借证。

正向 proposal 只可能消费目标 call-local slice 中由 `static_verified` 事实支持的 may-effect。当前 CodeQL query 没有独立的、非 executable callee-summary witness：若 proposal 复述 caller program 已存在的 `create`、`retain` 或 `dispatch` operation，validation 可保持 `verified` 且保留 `display_effect_ids`/provenance，但 apply 层会记录 `llm_proposed_effect_already_static`、清空对应 `usable_effect_ids`，避免 create 重复计数或 dispatch 重复展开。因此当前生产路径的 recorded summary 是 audit/display-only，不增强 solver；未来只有在新增独立静态 witness 且 operation 尚未执行时，正向 may-effect 才具备进入状态的语义接口。LLM 提议的 `drop`/`release` 即使结构完整也只展示，不能删除 may-hold、证明 must-release 或 bounded；exceptional callee effect 也没有 CFG 证明。原 `unknown_call`、出口缺口和 coverage gap 始终保留，缓存命中不提升 source trust。
