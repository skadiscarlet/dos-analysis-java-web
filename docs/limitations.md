# Resource Lifecycle v1.2 实际限制

v1.2 当前工程交付为 partial（独立源码 H4 blocked）：正式性质由 `properties.py` 统一发布，评价只选择并比较，不从 `property_states` 推断上界。项目接入、证据分片和源码验收进度见 `docs/execution/lifecycle-v1.2/STATUS.md`；当前验收见 `reports/lifecycle-v1.2/summary.md`；以下 v1.1 完成数字仅作历史基线，不代表 v1.2 验收。

2026-09-14 v1.1 限定验收完成：真实 caller/task CFG 进入同一主工作列表，十二个源码变体在 full 与固定输入消融中均匹配冻结期望，G1–G8 已通过。`property_states` 仅为状态聚合，条件性质从独立 state/trace 检查；证据缺失时 unknown。任务终止后的 close/drop 性质不保证最终一定终止；出队不结束 holder，close 不清空其他字段持有，无 holder 不代表 GC 已执行。

群体检查已从真实任务关系、转移和执行器契约导出 q/a 初态与保持性，支持已解析有限队列及固定最大线程数的 ThreadPoolExecutor；a 包括已预留执行槽。重复接纳下 `q+a<=K+W` 只覆盖已接纳任务，不包括阻塞提交者、其他 executor、字段或结果缓存，也不证明总内存。符号/未知容量、CallerRuns、DiscardOldest、额外 writer、缺正常/异常终止关系均 unknown。非 task queue 的兼容布尔 candidate 不再提供 bounded 结论。

两层精确包装调用已支持；nested task、递归、native、反射、未知虚分派、任意 alias 和未知 executor 仍保守处理。有限乘积状态可能触发 iteration_limit / analysis_budget_exhausted / solver_timeout；这些结果不证明无界。无 TaskBinding 的旧 dispatch 只有 capture 与 unknown。

下表为 2026-09-07 v1 历史能力清单，用于基线追溯；其中旧容量候选与评价数字不代表 v1.1 当前结果，当前语义以上文及 `analysis-semantics.md` 为准。当前十二例来自一个自包含源码 fixture，不能用于跨项目泛化结论。

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

端到端能力必须分开解读：真实源码模式执行 javac/CodeQL query/strict decoder/adapter/solver；导入事实模式信任调用方提供但仍按 schema 与 source snapshot 绑定的静态 rows；人工 IR 只验证状态语义，不证明提取覆盖。任务群体 K+W 依赖精确 scope 与全部 writer 覆盖，不能直接扩展为 family 总持有上界。所有普通输出都是静态性质。

## v1.2 未完成项与评价边界

- 已获准并纳入 3 个已有模块、9 条请求：3 条因严格源码快照失败、4 条未映射、1 条 iteration_limit 预算退出、1 条完成分析与回放。H4 仍 blocked，原因是工具覆盖和预算限制，不是缺少授权或路径。两个 HertzBeat 模块属于同一项目。
- `s2-task-only`、`s2-field-holder` 缺 callee execute rejection 到 wrapper/caller 的异常 CFG 事实；正式后端保持 unknown。删除旧评价器的状态计数推断后，原 oracle 不匹配被显式暴露，full 为 10/12、5 unknown；消融为 12/12、9 unknown，确定性增益 4。
- 规模最终运行复用已真实编译提取的事实；本次重新验证、求解、分片、迁移回放。编译/提取时间为 null，历史成本单列。没有把副本当独立样本，也不承诺一般线性复杂度。
- 分片不解决单元内部状态爆炸；哈希绑定不提供签名认证。GitHub 只含紧凑报告，本地完整证据和复现路径见 HANDOFF。


## RC1 支持范围增量

- 源码身份与提取范围分开：每个归档文件字节严格匹配；未归档文件仅在词法证明只有空白/完整注释时可忽略其语义，记录原文件 hash。含声明或词法不确定仍拒绝，buildless 不等于编译/外部依赖完备。
- 生命周期专用传输上限 65,536 行，保留 64 MiB JSON、16 MiB 累计字符串及既有字段限制；其他查询默认 4,096 行，分片读取仍为 16 MiB。不截取前 N 行。
- callable inventory 独立于资源族：方法找到但没有资源事实只表示模型未覆盖或没有当前规则命中；不构成无资源/安全证明，不能计为非空资源求解。
- 循环区间 join/widening 以保留实例关系和任务阶段的配置分区。累计历史分配与持有、关闭义务、峰值分开；重复位置仅在旧实例无 holder 且义务归零后恢复 recent。摘要实例只弱更新，无穷上界不构成无界增长证明。
- 精确已建模 wrapper 的 executor rejection 返回 caller 的异常 continuation；已有 catch/finally 必须经实际 CFG。新增循环 close/drop 提取限于无别名/无逃逸且显式置空的局部形式，未扩为一般 points-to、动态分派或任意深度调用。
- 旧事实可重新分析；旧运行语义回放仍检查实现/query 身份，不假称跨版本结果相同。正式性质 schema 和 lifecycle-run-2 分片格式继续复用，新增诊断只记录抽象推导和计数。
- 固定九方法是开发/回归集；是否稳定运行、模型内是否算对、独立输入是否有增益是不同问题。最终门槛与剩余缺口以 RC1 报告为准。

RC1 非零精确实例上界只用于显式任务完成条件切面，顶层 `all_exits` 仍要求原有效容量 invariant。可达循环的 worklist 求解完成不推出程序/任务保证终止；`terminated` 与 `termination_guaranteed` 分开。
