# Lifecycle RC1 状态

- 基线：`3ee3ea72ada4a0f3d7e65679fc8a1b2520052b3a`。
- 分支：`codex/resource-lifecycle-rc1-20260916`；隔离 worktree，主目录改动未纳入。
- 阶段：最终固定输入验收及报告。
- 已提交：`32c4735` 实现接入/收敛/异常传播；`047f884` 收紧非零上界到任务完成条件切面，区分worklist收敛与终止保证。
- 实际验收：baseline `pytest -q --continue-on-collection-errors` 为1191 passed/12 failed/41 skipped/1 error；047f884为1211 passed/12 failed/46 skipped/1 error，新增失败/错误ID为零。新增默认skip均有显式真实提取或冻结事实复验记录。
- 原十二例：fresh提取保留于 `.local-runs/rc1/final-synthetic/`；047f884复用已核验原事实重算与回放于 `final-synthetic-reused/`，full和消融均12/12，unknown3/9，合成增益6。
- 真实三循环 + inventory：20 passed/0 skipped；最终冻结事实10 passed/0 skipped。证据于 `.local-runs/rc1/tests/`、`loop-evidence/`、`loop-comparison/`。
- 九输入当前尝试：`python3 scripts/evaluate_lifecycle_rc1.py --asset-root /home/furina/new_tool/dos-analysis-web --out .local-runs/rc1/final-nine-fixed`。第一轮 `final-nine` 因已确认scope回归主动停止，原因留 `aborted.json`；没有因观察超时重启。
- 新证据：XXL三请求已解除注释占位整批拒绝；input2原selector指旧返回包，严格保留method_missing并附实际descriptor；input3仅3种ResourceState却被历史edge-set枚举耗尽预算。隔离同步精确state去重修复已通过，待本轮提取terminal后应用。
- common-core完整158文件已实际接入，两个非空资源单元完成求解及回放；不再使用29文件util缩包。scope/hash与原选择固定。
- 下一动作：完成当前spring提取，应用并提交同步精确去重补丁，重新九输入/相关回归，生成R1–R6紧凑报告，正常push并核对远端SHA。
- 限制：仅离线静态分析；不执行目标/PoC/动态负载。固定九输入属于开发集，无独立oracle，工程状态不代表研究有效性。
