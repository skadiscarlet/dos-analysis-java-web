# Semantic Repair 状态

branch=codex/lifecycle-semantic-repair-20260922
execution_task=task_2ae65d0c4ec847ad819c
delivery_state_at_commit=ready_for_push
semantic_repair_acceptance=partial
overall_tool_acceptance=fail
S1=pass
S2=pass
S3=partial
S4=pass
S5=pass
S6=ready_for_push

固定事实回放21/21；132 findings /126 families均unknown，正式阳性0，TP/FP/阳性未复核0/0/0，已知召回0/33，precision及保守下界null。7条具体假设贯通到报告，错误绑定与缺失假设拒绝。旧非证明认证重建仅恢复兼容，27条ID变更、0条verdict变化。

最终可收集全仓1913passed/13同基线failed/60skipped/1095subtests，新增失败ID0；另1个已知缺失全局skill收集项明确排除。源码已按测试内容hash冻结。commit/push和40位远端SHA一致性必须在提交后验证，不在本文件预先宣称成功。

真实未知前提与方法覆盖缺口仍在，不能包装成工具已完成。报告位于仓库根reports/lifecycle-semantic-repair/summary.md。交付后停止，不启动178-target、动态复现或新目标。
