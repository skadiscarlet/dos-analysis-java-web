# Lifecycle E2E handoff

正式 run ID：`lifecycle-e2e-poc33-api2cn-20260920_003322`。

entries 与 full 均为 21/21 completed；full acceptance manifest 验证 168 selected queries、0 diagnostics、0 skipped、0600 private audits。P0 aggregate 为 21 completed、0 malformed、0 missing。离线评价真实失败：126 个去重 family 全部为 `static_unknown`，正式阳性 0，已知记录 0/33，rollout 178-target full 保持暂停。

RC1 production bridge 只消费 accepted-task population。provider gate 要求正式 flow 的 Growth 为 verified、flow premise satisfied、kind=`async_work_growth`、dimension=`tasks`；前提 unresolved 时后端性质不可能改变 candidate-local unknown，因此不执行无关全项目 RC1 query。真实 async positive 合成 E2E 仍执行 provider，full/off 使用相同候选和 raw facts，并产生 `bounded_under_modeled_assumptions` / `static_vulnerable` 的预期差异。

重跑入口（会创建新 immutable run；凭据只从环境或 gitignored 0600 secrets 读取）：

```bash
MAIN=/home/furina/new_tool/dos-analysis-web
RUN_ID="lifecycle-e2e-poc33-api2cn-$(date +%Y%m%d_%H%M%S)"
python3 scripts/run_poc33_demo_acceptance.py poc33-entries \
  --run-id "$RUN_ID" --repo-root "$MAIN" \
  --results-root "$MAIN/results/java_web_dos_batch" \
  --canonical-manifest "$MAIN/intel/applications/java_web_205_targets.json" \
  --truth-manifest "$PWD/poc/manifest.json" --max-workers 3
python3 scripts/run_poc33_demo_acceptance.py poc33-real-provider-full \
  --run-id "$RUN_ID" --repo-root "$MAIN" \
  --results-root "$MAIN/results/java_web_dos_batch" \
  --canonical-manifest "$MAIN/intel/applications/java_web_205_targets.json" \
  --truth-manifest "$PWD/poc/manifest.json" \
  --allow-remote-llm --max-workers 1
python3 scripts/run_poc33_demo_acceptance.py poc33-offline-eval \
  --run-id "$RUN_ID" --repo-root "$MAIN" \
  --results-root "$MAIN/results/java_web_dos_batch" \
  --dynamic "$MAIN/results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-dynamic-validation"
```

本轮没有执行动态 DoS。Ruoyi canonical DB 的原始 `db-java/default/strings/` 已在 archive/aggregate validation 后从隔离区原样恢复；两份 regenerated 副本保留在结果目录作为证据。不要将当前结果描述成 33/33、precision 通过或动态 confirmed。
