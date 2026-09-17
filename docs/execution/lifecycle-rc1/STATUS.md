# Lifecycle RC1 状态

- 阶段：实现与验收完成，报告已审计，等待正常推送与远端 SHA 核验。
- 分支：`codex/resource-lifecycle-rc1-20260916`；基线 `3ee3ea72ada4a0f3d7e65679fc8a1b2520052b3a`。
- 被测提交：`1a2d01aa2b605d8a9cbc76d1da0f05345845b5c4`，源码/查询/runner hash 见 run-manifest。
- 工程：R1–R6 pass、rc_ready；研究：unvalidated。九输入提取9、方法解析8、资源单元4、resource_unmodeled4、真实method_missing1、预算退出0，三个模块均完成范围回放。
- 固定输入命令：`python3 scripts/evaluate_lifecycle_rc1.py --asset-root /home/furina/new_tool/dos-analysis-web --out .local-runs/rc1/release-nine`；实际 exit1，原因仅为原过期readLog返回类型，非求解失败。
- 原十二例：release-synthetic 两模式12/12，unknown3/9，合成增益6，12单元普通性质/评价/回放一致。九输入性质1 bounded/17 unknown、增益0，无call/task关系。
- 测试：最终非沙箱同环境1212 passed/12 failed/46 skipped/1 error，基线1191/12/41/1；新增失败/错误ID为0。11项最终循环回归全部通过，20项真实提取回归0 skipped，必要opt-in evidence单列。
- 真正修复：源码范围/预算/身份、循环数值收敛、同步历史状态重复、wrapper拒绝返回；修复收尾时发现的过宽all_exits界限与终止保证误用，未改oracle。
- 原始证据：`.local-runs/rc1/release-nine/`、`release-synthetic/`、`tests/`、`loop-comparison/`；完整早期失败、中断与环境差异仍保留。
- 实际报告命令：`python3 scripts/report_lifecycle_rc1.py --root-run .local-runs/rc1/release-nine --acceptance .local-runs/rc1/acceptance.json --out reports/lifecycle-rc1`。
- 下一动作：仅提交紧凑报告/文档、正常push、核对远端SHA；不自动启动新输入实验或RC2。
- delivery_state_at_commit：ready_for_push。主工作区无关改动及源码/DB/PoC资产保持原样。
