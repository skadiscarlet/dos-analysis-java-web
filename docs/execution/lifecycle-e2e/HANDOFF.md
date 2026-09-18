# Lifecycle E2E handoff

当前实现使用 dispatch submit 点而非资源 create 点绑定 production Growth：精确核对源码文件/行、call path callable、receiver/field identity，再沿 TaskBinding -> instance -> family -> executor contract 消费同 executor scope 的 accepted_task_population。

正式性质保留原始 dimension/scope/cut/status/upper bound/assumptions/gaps。只有 bounded、正上界、arbitrary_finite_repetitions、无 coverage gap 的任务群体性质能形成 refutes_relevant_growth；它以独立 decision 反驳适用的 A1/A2，不伪装成 synchronous release 或 legacy bound。

production full/off 消融使用同一 provider、候选、查询与 raw facts/results，仅由版本化 propagation 开关控制性质是否进入 lifecycle/conclude；该模式进入 fingerprint，不能跨模式 resume。后端 database fingerprint 与当前正式 CodeQL DB 不一致时直接终止。

本轮 run ID 为 `lifecycle-e2e-poc33-rightapi-20260918_165304`。entries 已通过 21/21、168 queries、0 diagnostics、0 skipped。full immutable plan 已固定 RightAPI/grok-4.6，但当前 owner-only key 在真实首项和无源码最小探针上均返回 HTTP 401；为避免重复确定性失败，批次已停止并保留 1 failed + 20 interrupted 的证据。不要删除或把它们记为 unknown/命中。

更新 gitignored、0600 的 `config/local_secrets.json` 后，先做最小认证探针。认证恢复后从现有 archive 重试，不重建输入或 plan：

    MAIN=/home/furina/new_tool/dos-analysis-web
    RUN_ID=lifecycle-e2e-poc33-rightapi-20260918_165304
    python3 scripts/run_java_web_dos_batch.py full \
      --plan "$MAIN/results/java_web_dos_batch/$RUN_ID-full/batch_plan.json" \
      --output "$MAIN/results/java_web_dos_batch/$RUN_ID-full" \
      --repo-root "$MAIN" \
      --max-workers 1 \
      --retry-failed \
      --max-attempts 3 \
      --allow-remote-llm

full 和 aggregate 完成后再执行 `poc33-offline-eval`；未完成 full 时 evaluator 会 fail closed。新批次从零执行入口保留如下：

    MAIN=/home/furina/new_tool/dos-analysis-web
    RUN_ID=lifecycle-e2e-poc33-$(date +%Y%m%d_%H%M%S)
    python3 scripts/run_poc33_demo_acceptance.py poc33-entries \
      --run-id "$RUN_ID" \
      --repo-root "$MAIN" \
      --results-root "$MAIN/results/java_web_dos_batch" \
      --canonical-manifest "$MAIN/intel/applications/java_web_205_targets.json" \
      --truth-manifest "$PWD/poc/manifest.json" \
      --max-workers 3

entries 21/21 gate 完成后，使用相同 RUN_ID 执行 poc33-real-provider-full --allow-remote-llm --max-workers 1。不得 resume 旧 schema 或 APIBasis 结果。
