# Lifecycle E2E acceptance summary

日期：2026-09-22

RC1 resource lifecycle 已接入 production lifecycle/conclude/certificate/report 链；固定 PoC-33 输入保持 33 条记录、21 个规范化项目，检测输入与评价 oracle 分离。正式 API2CN entries/full 批次均已完成，P0 aggregate 为 21 completed、0 malformed、0 missing。

本轮工程和项目执行完成，但验收结果没有通过：132 条 finding 去重为 126 个 family，全部为 `static_unknown`，没有 `static_vulnerable`。因此已知记录正式阳性覆盖是 0/33；20 条 certificate-backed full-chain unknown、7 条 entry+growth linked、2 条 entry only、4 条 growth only 都不能算命中。离线 gate 状态为 `failed`，178-target full 继续暂停。

| Metric | Value |
| --- | --- |
| frozen records / normalized projects | 33 / 21 |
| entries/full completed | 21/21 / 21/21 |
| selected entry queries | 168 |
| diagnostics / skipped | 0 / 0 |
| aggregate status | 21 completed, 0 malformed, 0 missing |
| raw findings / deduplicated families | 132 / 126 |
| verdicts | 0 `static_vulnerable`, 126 `static_unknown` |
| known records matched as formal positives | 0/33 |
| supported chain | 20/29 (0.689655) |
| ordinary eligible-positive recall | 0/6 |
| hard-negative safety | 15/15 |
| TP / FP / U | 0 / 0 / 126 |
| confirmed precision | undefined (`null`) |
| conservative precision lower bound | 0.0 |
| FPR | `not_measured` |
| precision threshold | 0.8, `proposed_default` |

## G1–G6

- G1 complete：33 条记录、21 个项目、源码/DB 身份和 canonical scope 已冻结；oracle 未进入 analyzer。
- G2 complete：RC1 性质通过独立 `ResourceLifecycleDecision` 进入 lifecycle/conclude/certificate/report。只有 verified、premise-satisfied 的 `async_work_growth`/`tasks` flow 才执行并消费 accepted-task population；无关或前提 unresolved 的候选不会触发无关全项目 RC1 查询。
- G3 complete：21/21 formal full targets 完成；每库 8 条 selected entry queries，0 diagnostics、0 skipped；历史失败和 attempt 均保留，未把失败改写成成功。
- G4 fail：0/33 是正式阳性覆盖；unknown、full-chain candidate 和运行完成均未算命中。
- G5 pending_manual_review：不存在可计算 precision 的正式阳性，126 个 unknown family 保留在 review queue；0.8 只是 `proposed_default`，不能声明达到阈值。
- G6 complete：输入、计划、stage artifacts、0600 private audit、aggregate、offline evaluation、报告和重跑入口均已保存；本地测试与已知 historical canonical-200 资产失败分别记录。

状态：`implementation_status=complete`、`project_execution_status=complete`、`known_case_acceptance=fail`、`precision_review_status=pending_manual_review`、`acceptance_status=partial`。

## Evidence

- entries：`results/java_web_dos_batch/lifecycle-e2e-poc33-api2cn-20260920_003322-entries/`
- full：`results/java_web_dos_batch/lifecycle-e2e-poc33-api2cn-20260920_003322-full/`
- recall：`results/java_web_dos_batch/lifecycle-e2e-poc33-api2cn-20260920_003322-recall/`
- offline evaluation：`results/java_web_dos_batch/lifecycle-e2e-poc33-api2cn-20260920_003322-eval/`
- full acceptance manifest：21/21 completed、168 selected queries、0 diagnostics、0 skipped、private audit 0600、`max_target_attempts=16`。

动态证据只复用了既有 `poc33-real-llm-full-v2-20260824_110233-dynamic-validation`；本轮没有启动服务、PoC、负载、OOM 或新的动态验证。密钥未进入报告、日志或 Git。
