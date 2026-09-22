# Lifecycle E2E status

更新时间：2026-09-22

| Gate | Status | Evidence |
| --- | --- | --- |
| G1 fixed population | complete | 33 records、21 projects；input manifest 与 oracle 分离 |
| G2 production integration | complete | RC1 decision 被正式 lifecycle/conclude/certificate/report 消费；full/off 合成回归保留 |
| G3 project execution | complete | API2CN entries/full 均 21/21；168 queries；0 diagnostics/skipped；aggregate 21 completed |
| G4 known-case coverage | fail | 0 `static_vulnerable`；0/33；20 full-chain records 均为 `static_unknown` |
| G5 positive quality | pending_manual_review | TP/FP/U=0/0/126；precision undefined；0.8 为 proposed_default |
| G6 rerun delivery | complete | acceptance manifest、aggregate、offline eval、33-row ledger、126-row review queue 与重跑命令已保存 |

整体状态：`implementation_status=complete`、`project_execution_status=complete`、`known_case_acceptance=fail`、`precision_review_status=pending_manual_review`、`acceptance_status=partial`。

关键修复：

- Growth contract 使用的 typed StaticFact 正式归档并参与离线引用验证；Growth implementation v33。
- `--refresh-completed` 在一次 invocation 中每个 completed target 只 refresh 一次。
- RC1 backend 只在 verified、premise-satisfied 的 async task Growth path 上执行；PoC-33 中相关 task candidates 的 Growth 均 unresolved，因此保留 premise unknown，避免生成 129–857 MB 无关 decoded JSON，同时不提高 64 MiB 通用安全上限。
- 修复型 archive 如实保留历史 attempts；validator 以显式上限 16 验证。

验证结果：production/resource/batch 定向套件 `127 passed, 37 subtests passed`；batch runner/CLI `34 passed, 7 subtests passed`，另有 1 个依赖 historical canonical-200 corpus 的既有资产失败。最终必要套件结果见 run manifest 与 HANDOFF。
