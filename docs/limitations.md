# Resource Lifecycle v1.1 实际限制

2026-09-10 Task4 增量：caller 与真实 task CFG 已进入同一主状态工作列表，normal/exception/reject/cancel 切面和条件维度可从保存的状态导出。G1–G2 pass、G3 fail（pending fresh review）、G4–G8 fail。`property_states` 仅为状态聚合；条件性质从 `property_derivations` 的独立 state/trace 逐路径检查，aggregate proof 不声明一条由互斥边合成的路径，缺失路径证据时 unknown。纯拒绝任务不算 pending，open obligation 不可被抹成 bounded；Program 与 dispatch matching 均校验 instance-family 一致性。任务终止后 close/drop 的性质不代表最终一定终止；缺调度/取消/拒绝回接证据仍为 unknown。任务出队不结束 holder，close 不清空其他 field/heap holder，无 holder 不代表 GC 已执行。完整 Program 的人工状态回归与含 coverage gap 的真实 SourcePairs 验收分别计数；后者正常/异常终止状态义务归零仍不能消除 gap 或作为 G4 精确源码收益。

群体 `PopulationEffect` 在主转移中校验 task identity/阶段并保留原始计数语义和证据，但 Task5 的 q/a 归纳证明与重复接纳上界尚未实现。重复 task context 再入、nested task、无法证明的 callback effect、复杂调度和未知 executor 均不扩展支持范围。乘积状态可能增加预算开销；超限准确返回 iteration_limit / analysis_budget_exhausted / solver_timeout。当前无 TaskBinding 的旧 dispatch 不再生成 contract-only 完成快照，未求解阶段为 null。

下表保留 2026-09-07 v1 基线边界；异步主求解的增量和仍未完成的门槛以上述 Task4 说明为准。

| 领域 | 已支持 | 未支持或保守处理 |
| --- | --- | --- |
| 输入 | 人工 IR manifest、严格导入的静态 JSON facts、用户提供的本地 Java CodeQL database。 | 自动选择/下载第三方目标、在线扫描、服务启动、请求生成、动态 DoS。 |
| Java 提取 | 自包含 fixture 中的资源构造、close、字段/队列保留、`ArrayBlockingQueue` 常量容量、精确 call-site column 及正常/异常路径 raw facts。 | 通用框架穷尽、reflection、复杂 interprocedural alias、任意 wrapper depth、完整 async callback 图。显式 `entry_methods` 只选择 callable identity，不复用 P0 的完整 E extraction/call graph；缺口为 partial/unknown。 |
| 资源身份 | recent exact 强更新；summary/family/unknown 弱更新。 | 通用 points-to 精化、跨反射或 native identity；一次 summary release 不清除历史集合。 |
| Holder | request、task、container、field、local；多 holder may-edge。 | GC 时间、物理内存归还、JVM heap region 或 native allocator 的精确回收。 |
| Effect | create/retain/drop/release/dispatch/unknown_call 和 guard/condition 证据。 | 在 Python 中求解任意 Java path predicate；不可判定条件要求上游限定，否则 coverage unknown。 |
| 异步 | 显式、版本化 executor contract；submit/start/complete/reject/cancel 分阶段，inline/queued 分开，queue contract/holder/target identity 精确绑定。 | 通用 Executor 实现推断、吞吐率、公平性、运行时间、后台过期/消费者释放证明。unknown completion/cancel 保留引用；P0 不把异步 Release 当同步资源减少证据。 |
| 上界 | 非负计数区间、常量/符号容量候选、初始/归纳/写入者/原子性门槛、per-queue scope、item count 与 item size 分离。 | 通用 SMT、非线性/概率/吞吐约束、跨未覆盖写入者的全局证明、多个 queue 的 family aggregate。候选失败仅为 unknown。 |
| 关闭义务 | exact recent 实例的显式 close；正常/异常出口独立检查。 | close 对 heap 引用或物理内存的隐含释放；未知 alias 下的 obligation gap 确证。 |
| 方法摘要 | 已知可信契约；recorded proposal schema、分层证据验证、0600 私有 snapshot、显式 budget；exact source callee 与完整 Java source snapshot 绑定。 | `--llm live` 未实现、没有真实 provider 调用验收；当前 QL 未提取独立 callee-summary witness，故已验证同位正向 effect 仅 audit/display，不增强 solver。LLM drop/release 永不成为消除证据，exceptional callee CFG 也未证明。 |
| 证据 | facts snapshot、稳定 hash、规则依赖、前提、出口结论、代码位置，以及重新验证 recording、求解 result、重建 evidence/`summary.md` 的 replay；同目录 analyze/replay 由 bounded lock 串行化。 | summary derivation 的直接 `code_locations` 尚不含 call-site column（可由 raw fact/request 恢复）；replay 不一致写 `consistent=false` 但 CLI 仍返回 0；run 逐 artifact 原子 replace 而非目录级事务。跨机器绝对性能不可保证；私有 recording/summary 不是公开报告。 |
| 评价 | 12 组 24 个性质先验人工 IR、完整模式加五种消融、逐例 CSV/JSON/Markdown。 | 29 条历史资料未完成独立 lifecycle 标签和源码适配，0 条进入指标分母；legacy/文献工具未运行，标记 N/A。 |
| 结论 | `bounded` / `obligation_gap` / `unknown` / `not_applicable` 与独立 `impact_status`。 | vulnerability 布尔量、服务可用性证明、实际资源耗尽、动态 confirmed、维护者认可结论。 |

Resource Lifecycle v1 与 v2 P0 formal pipeline 并行存在。它没有修改旧 schema/tool `2.5/0.4.0`，也没有把新 lifecycle status 映射为 P0 的 `static_vulnerable`、`bounded_under_modeled_assumptions` 或 `static_unknown`。

端到端能力必须分开解读：真实源码模式执行 javac/CodeQL query/strict decoder/adapter/solver；导入事实模式信任调用方提供但仍按 schema 与 source snapshot 绑定的静态 rows；人工 IR 只验证状态语义，不证明提取覆盖。per-queue capacity 只证明该 canonical queue scope 的 item count，不是同 family 的 aggregate total-held 上界。所有普通输出都是静态性质，不是动态 confirmed、服务可用性或实际资源耗尽证明。
