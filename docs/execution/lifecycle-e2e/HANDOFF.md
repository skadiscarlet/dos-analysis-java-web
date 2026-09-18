# Lifecycle E2E handoff

当前实现使用 dispatch submit 点而非资源 create 点绑定 production Growth：精确核对源码文件/行、call path callable、receiver/field identity，再沿 TaskBinding -> instance -> family -> executor contract 消费同 executor scope 的 accepted_task_population。

正式性质保留原始 dimension/scope/cut/status/upper bound/assumptions/gaps。只有 bounded、正上界、arbitrary_finite_repetitions、无 coverage gap 的任务群体性质能形成 refutes_relevant_growth；它以独立 decision 反驳适用的 A1/A2，不伪装成 synchronous release 或 legacy bound。

production full/off 消融使用同一 provider、候选、查询与 raw facts/results，仅由版本化 propagation 开关控制性质是否进入 lifecycle/conclude；该模式进入 fingerprint，不能跨模式 resume。后端 database fingerprint 与当前正式 CodeQL DB 不一致时直接终止。

下一执行入口：

    MAIN=/home/furina/new_tool/dos-analysis-web
    RUN_ID=lifecycle-e2e-poc33-$(date +%Y%m%d_%H%M%S)
    python3 scripts/run_poc33_demo_acceptance.py poc33-entries \
      --run-id "$RUN_ID" \
      --repo-root "$MAIN" \
      --results-root "$MAIN/results/java_web_dos_batch" \
      --canonical-manifest "$MAIN/intel/applications/java_web_205_targets.json" \
      --truth-manifest "$PWD/poc/manifest.json" \
      --max-workers 3

entries 21/21 gate 完成后，使用相同 RUN_ID 执行 poc33-real-provider-full --allow-remote-llm --max-workers 1。不得 resume 旧 schema 结果。
