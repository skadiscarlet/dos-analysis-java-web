# Resource Lifecycle v1.1 源码验收与交付

implementation_status: complete；delivery_state_at_commit: ready_for_push。G1–G8 全部通过；push 验证由结束回复给出。

当前源码评价基于 `f59fc6e9d2eb624afc2252330eac5aab1e246d63` 后的 evidence 去重修复；精确实现、源码、查询和结果哈希见 `run-manifest.json`，父提交本身不代表完整运行版本。

## 源码评价

同一个自包含 Java fixture 中的六组成对十二个变体实际经过 Java 编译、CodeQL、adapter、主 solver 和报告。冻结期望见仓库 `tests/fixtures/resource_lifecycle_v1_1/source-cases.json`，逐例结果见 `source-cases.csv`。

| 模式 | 例数 | 期望匹配 | unknown |
| --- | ---: | ---: | ---: |
| full | 12 | 12 | 3 |
| disable_cross_event_propagation | 12 | 12 | 9 |

unknown 期望匹配只验证保守行为，不算问题检出。十二个变体不是十二个独立项目；无外部项目准确率、动态确认或文献基线指标。

S2 task-only 在 request 和 task 均结束的切面上 held upper 为 0，额外静态字段 holder 版本为 1。S3 全出口 finally close 为 bounded 0，遗漏异常出口保持 unknown。S5/S6 已验证配置和支持执行器的已接纳任务上界为 5；未知容量和 receiver 保持明确 unknown。

## 固定事实的传播收益

两模式复用相同的 606 条 raw facts、入口和候选；消融只删除跨 callable/task relations 与相应 transitions，并记录缺口。六例确定性增益为 s1-task-wrapped、s2-task-only、s2-field-holder、s4-depth-two、s5-verified-capacity、s6-supported-executor。删除详情和精确 transition ID 位于 `source-evaluation.json` 的 ablation 字段。

具体 witness：s2TaskOnly 的 `instance:458f143ecfc13e3d1a9dba34` 由 `task-binding:de46ae1f6b7da1b554ca685d` 捕获，task 为 `task:aa400e675f4efc73d9590bd7`。callback 在 `SourcePairs.java:165` 调用 close，正常终止边 `transition:c290e40cf54c2d496f0ea0e6` 从 `event:c3230908ed66422b40ac3875` 到 `event:0a405921d61ee62b7af8424c`，带同 task 的 a 减 1；主求解结束该任务并只解除其 holder。异常出口也绑定同一资源与独立 TaskExit。请求 holder 结束后，task-only 无额外持有，field-holder 版本仍保留字段边。消融删除这些 task 关系，无法得到对应终止切面，因此为 unknown。

## 群体性质

初态 `(q,a)=(0,0)`；直接接纳增加 a，入队增加 q，分配执行槽使 q 减 1/a 加 1，进入 run 不再增加 a，正常/异常终止减少 a。检查每个相关 writer、guard 和实际 TaskExit，导出任意有限次外部接纳下 `0<=q<=3`、`0<=a<=2`、`q+a<=5`。a 包含预留执行槽。

只覆盖该执行器已接纳任务；不包括提交者、其他 executor、字段保留、结果缓存或单项字节大小。存在完成边不证明最终一定完成，所有结论受记录的切面和 modeled assumptions 限定。

## 提取覆盖与独立测试

`extraction-coverage-diff.json` 比较同一个 Java database 和十二个入口：基线 `f62d6f2` 的 54 facts/零 call-task-exit bindings，当前 606 facts/12 call bindings/6 task bindings/12 TaskExit。原始事实 schema 和提取能力改变，因此数量不是检出率；这不是固定事实消融。

人工 IR full 模式独立为 24/24 匹配：11 bounded、11 unknown、2 obligation_gap。两个明确契约测试类共 64 passed，独立于真实 Java 案例计数。旧 v1 的 13/9/2 分布保留在旧报告；当前不再接受 capacity-only 或兼容布尔的自证明。

同环境全仓基线：12 failed、874 passed、26 skipped、1 collection error；最终：12 failed、1146 passed、39 skipped、1 collection error。最终额外启用新的真实缓存 facts 回放测试（基线无此测试）。`baseline-test-diff.json` 逐 ID 比较：零新增失败/错误；12 个持续失败涉及未挂载的大型 ignored 资产，收集错误来自历史测试的全局 skill 路径。skip 原因逐项保存，不把 skip 当作源码验收。全仓不是全绿，也不对未收集模块声称零回归。

README 编译命令已实际创建新 CodeQL database。extract/analyze/replay 验证先暴露 28,797,293-byte evidence 超过 16 MiB 的问题；消除 child dependency 展开和重复路径规则后为 16,704,007 bytes，回放 consistent=true。回归验证 child scope/event/index 可恢复原始路径规则和状态，篡改索引得到 inconsistent。路径证据编码详见 analysis-semantics.md。

## 限制与复现

支持两层精确非递归包装和窄 ThreadPoolExecutor 契约。nested task、未知虚分派、反射/native、一般 alias、未解析配置、额外 writer、未证明 callback effect 及最终调度保证不在已证明范围。缺口或预算耗尽保留 unknown；不证明 P0 async Release。LLM off，调用 0；recorded summary 仍 audit/display-only，live 未实现。

README 提供真实源码编译、评价、提取、分析和回放命令。生成失败差分使用 `scripts/compare_lifecycle_test_runs.py`；分类指标与提取对照使用 `scripts/summarize_lifecycle_delivery.py`。输入 XML 与大型原始 facts 保留在本地 `/tmp/lifecycle-v11-*`，公开报告保留哈希和结果，不包含数据库、原始日志或私有录制。
