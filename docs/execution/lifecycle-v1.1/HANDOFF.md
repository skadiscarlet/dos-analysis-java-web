# Resource Lifecycle v1.1 交接

implementation_status: complete
delivery_state_at_commit: ready_for_push
push_verification: 由结束回复给出；后续可直接检查远端分支
actual_base_commit: f62d6f2343d160a320dbb7aaec6d22c307d892f0
branch: codex/resource-lifecycle-v1_1-20260908
G1–G8: 见 reports/lifecycle-v1.1/gates.json
supported_source_path: exact allocation → 两层精确 wrapper → captured task → callback CFG → 正常/异常 TaskExit
async_in_solver: accept/enqueue/assign-slot/start/normal/exception/reject 和显式 phase-matched cancellation
population_property: 一个已解析 ThreadPoolExecutor 的已接纳任务；初态 q=a=0，任意有限次接纳下 q<=K、a<=W、q+a<=K+W；源码正控 K=3/W=2
source_evaluation: 十二变体 full 12/12、消融 12/12 匹配；unknown 3/9，六例确定性增益，真实源码评价无 skip/mock
regressions: 同环境新增失败 ID 0、新增错误 ID 0；持续 12 个资产相关失败和 1 个历史 skill 路径收集错误，详见 baseline-test-diff.json
llm: off；0 calls；recorded replay audit/display-only，live 未实现
remaining_gaps: nested tasks、递归/反射/native、未知虚分派/alias/executor、符号容量、未覆盖 writer、一般调度最终性、总内存上界
next_action: 提交推送；结束回复核对远程 SHA，后续按需处理明确未支持范围

## 证据入口

- [正式 summary](../../../reports/lifecycle-v1.1/summary.md)
- [源码逐例 CSV](../../../reports/lifecycle-v1.1/source-cases.csv)
- [指标](../../../reports/lifecycle-v1.1/metrics.json)
- [版本与运行 manifest](../../../reports/lifecycle-v1.1/run-manifest.json)
- [失败集合差分](../../../reports/lifecycle-v1.1/baseline-test-diff.json)
- [同源码提取覆盖比较](../../../reports/lifecycle-v1.1/extraction-coverage-diff.json)

运行合同为外层 `CODEX_GOAL_LIFECYCLE_V1_1.md`。README 包含从 Java 编译 CodeQL database、source evaluation、单入口提取、分析、population 检查、replay 与真实验收的命令。旧 `reports/lifecycle-v1/` 保留原样。

分析代码为 `f59fc6e9d2eb624afc2252330eac5aab1e246d63` 加 evidence 去重修复。精确 implementation hash 为 `5b2cfcb3f616288a0244386cd4ab475c5310ec246e42a926ae0cdc58eef4b28d`；不要用父提交或包含该文档的提交自身 SHA 冒充运行时已知信息。

## 测试解释

原样全仓测试在基线/最终均因全局 skill 路径缺失停止收集；使用 `--continue-on-collection-errors` 获取其余测试。基线 874 passed，最终 1146 passed（额外启用新的 cached facts evidence 回归），持续失败 ID 精确相同。比较脚本保留 XML SHA 和所有 skip 原因；未收集模块及缺失资产不具有全绿证明。

当前 fresh 源码运行 `/tmp/lifecycle-v11-g8-source-fixed` 保留完整 facts 与双模式求解产物；基线同源码提取为 `/tmp/lifecycle-v11-g8-baseline-extraction`。真实回放 `/tmp/lifecycle-v11-g8-compact-run/replay.json` 为 consistent=true，证据 16,704,007 bytes，读取上限仍 16 MiB。公开报告包含派生结果而不提交数据库或原始日志。`/tmp` 可能被清理，可用 README 重建。

## 支持边界

有条件的 task 终止后性质不等于任务必然终止。关闭义务、heap holder、群体任务数与单项字节大小分别检查。未知容量/receiver、未支持拒绝策略或任何相关身份/覆盖/预算缺口保持 unknown；P0 schema/tool 2.5/0.4.0 与三态协议不变。
