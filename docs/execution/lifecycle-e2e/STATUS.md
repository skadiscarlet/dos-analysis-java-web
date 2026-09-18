# Lifecycle E2E status

更新时间：2026-09-18

| Gate | Status | Evidence |
| --- | --- | --- |
| G1 fixed population | implementation complete, run pending | acceptance 脚本生成 33-record/21-project input-manifest.json，record 映射不进入 analyzer |
| G2 production integration | complete | 独立 ResourceLifecycleDecision 接入 A1/A2、lifecycle result、certificate 和 report；同候选/raw facts 的 full/off production E2E 使 bounded 与 static vulnerable 结论发生预期变化；真实 CodeQL dispatch fixture 通过 |
| G3 project execution | pending | 尚未启动本实现的新 21-target entries/full |
| G4 known-case coverage | pending | 尚无本实现冻结后的 full findings |
| G5 positive quality | pending manual review | 尚无本实现去重阳性队列 |
| G6 rerun delivery | partial | schema/tool 2.8/0.7.0、frozen query pack、backend identity、facts/results artifacts 已实现；commit/push 待最终运行 |

当前整体状态：implementation_status=complete、project_execution_status=partial、known_case_acceptance=blocked、precision_review_status=pending_manual_review、acceptance_status=partial。

已验证：

- resource lifecycle：522 passed、24 skipped、242 subtests；
- production/assertion/schema/certificate/batch/recovery focused：272 passed、128 subtests；
- full/off production E2E：相同 Growth candidates、flow proofs 与 RC1 private facts/results；full=`bounded_under_modeled_assumptions`，propagation off=`static_vulnerable`；
- 真实 CodeQL dispatch/program-point fixture：1 passed in 160.88s；
- 全仓受工作树缺少大型资产、sandbox 禁止本地 socket 及全局 dynamic-validator skill 路径缺失影响，不能作为本轮新增回归；定向相关套件全绿。
