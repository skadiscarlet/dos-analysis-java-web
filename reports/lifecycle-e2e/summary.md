# Lifecycle E2E acceptance summary

日期：2026-09-18

RC1 resource lifecycle 已接入 schema 2.8/tool 0.7.0 的 production lifecycle/conclude/certificate/report 链。固定 PoC-33 输入保持 33 条记录、21 个规范化项目，分析输入与评价 oracle 分离。

正式 entries 批次 `lifecycle-e2e-poc33-rightapi-20260918_165304-entries` 已完成：21/21 targets、168 selected queries、0 diagnostics、0 skipped。随后创建的新 RightAPI full immutable plan 使用 `https://rightapi.ai/grok/v1/`、`grok-4.6`、180 秒 timeout 和 5 次 provider retry；首项 apache/hertzbeat 在 Growth 阶段收到 `LLM_AUTHENTICATION_FAILED`。独立最小认证探针返回 HTTP 401，环境无备用 key，因此停止余下批次，避免把同一确定性凭据错误扩散为 21 次长时间失败。

| Metric | Value |
| --- | --- |
| frozen records | 33 |
| normalized projects | 21 |
| entries fully completed | 21/21 |
| formal full projects completed | 0/21 |
| known records matched | 0/33 (not evaluated) |
| TP / FP / U | null / null / null |
| confirmed precision | null |
| conservative precision lower bound | null |
| acceptance status | partial |

## G1–G6

- G1 complete：33 条记录、21 个项目与源码/DB 身份冻结；oracle 不进入 analyzer。
- G2 complete：独立 `ResourceLifecycleDecision` 被 A1/A2、certificate 和 report 消费；production full/off 合成 E2E 在同候选、flow 和 RC1 raw facts/results 上产生预期 verdict 差异。
- G3 blocked：entries 21/21 完成，formal full 因当前 provider 凭据 HTTP 401 未完成。
- G4 blocked：无完整 full findings，unknown、失败或中断均未计为命中。
- G5 pending_manual_review：没有完整正式阳性集合，TP/FP/U 与 precision 不可计算；0.8 仅为 `proposed_default`。
- G6 partial：实现、测试、输入、immutable plans、entries 证据和失败证据可重跑；full/eval 仍需有效 owner-only key。

恢复时替换 gitignored、0600 的 `config/local_secrets.json` 中 `deepseek_api_key`，先用无源码最小探针确认非 401，再对现有 full archive 执行 `scripts/run_java_web_dos_batch.py full --retry-failed --allow-remote-llm`。不得把本报告视为 33/33 recall、precision 通过或完整工具验收。
