# Lifecycle E2E status

更新时间：2026-09-18

| Gate | Status | Evidence |
| --- | --- | --- |
| G1 fixed population | complete | RightAPI run 冻结 33-record/21-project input-manifest.json；record 映射不进入 analyzer |
| G2 production integration | complete | 独立 ResourceLifecycleDecision 接入 A1/A2、lifecycle result、certificate 和 report；同候选/raw facts 的 full/off production E2E 使 bounded 与 static vulnerable 结论发生预期变化；真实 CodeQL dispatch fixture 通过 |
| G3 project execution | blocked | entries 21/21、168 queries、0 diagnostics、0 skipped；formal full 首项在 Growth 收到 `LLM_AUTHENTICATION_FAILED`，最小探针确认 HTTP 401，0/21 full complete |
| G4 known-case coverage | blocked | full 未完成，0/33 仅表示未评价；失败/中断未计为命中 |
| G5 positive quality | pending manual review | 尚无完整正式阳性集合，TP/FP/U 与 precision 均为 null |
| G6 rerun delivery | partial | schema/tool 2.8/0.7.0、frozen query pack、backend identity、immutable entries/full plans、entries 证据与认证失败证据均已保存；full/eval 待有效 key |

当前整体状态：implementation_status=complete、project_execution_status=partial、known_case_acceptance=blocked、precision_review_status=pending_manual_review、acceptance_status=partial。

已验证：

- resource lifecycle：522 passed、24 skipped、242 subtests；
- production/assertion/schema/certificate/batch/recovery focused：272 passed、128 subtests；
- RightAPI 配置/cache/PoC-33 综合 focused：348 passed、154 subtests；provider loopback：121 passed、151 subtests；
- full/off production E2E：相同 Growth candidates、flow proofs 与 RC1 private facts/results；full=`bounded_under_modeled_assumptions`，propagation off=`static_vulnerable`；
- 真实 CodeQL dispatch/program-point fixture：1 passed in 160.88s；
- 正式 entries archive：`lifecycle-e2e-poc33-rightapi-20260918_165304-entries`，21/21 completed；
- 正式 full archive：`lifecycle-e2e-poc33-rightapi-20260918_165304-full`，当前 provider 凭据返回 HTTP 401；
- 全仓受工作树缺少大型资产、sandbox 禁止本地 socket 及全局 dynamic-validator skill 路径缺失影响，不能作为本轮新增回归；定向相关套件全绿。
