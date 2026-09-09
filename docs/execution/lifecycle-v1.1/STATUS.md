# Resource Lifecycle v1.1 执行状态

- task: `resource-lifecycle-v1.1`
- implementation_status: `partial`
- delivery_state_at_commit: `partial`
- actual_base_commit: `f62d6f2343d160a320dbb7aaec6d22c307d892f0`
- branch: `codex/resource-lifecycle-v1_1-20260908`
- current_stage: `task2_relation_ir_green`
- next_action: `Task 3：从真实 Java/CodeQL 提取 CFG、调用、捕获、执行器和出口事实`

## 适用标准

- 唯一 P0 实施标准：`docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md`
- 本轮增量合同：工作区外层的 `CODEX_GOAL_LIFECYCLE_V1_1.md`（2026-09-08，`resource-lifecycle-v1.1`）
- P0 schema/tool 保持 `2.5/0.4.0`；本轮只扩展并行的离线 `resource-*` 链，不把异步模型性质升级成旧 P0 漏洞结论。

## 实际基线

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| remote | `origin = ssh://git@ssh.github.com:443/skadiscarlet/dos-analysis-java-web.git` | 与合同仓库匹配 |
| lifecycle 固定起点 | `f62d6f2` | 当前分支直接从已审阅提交创建 |
| 全仓 network-free baseline | `101 failed, 797 passed, 26 skipped, 389 subtests passed` | `python3 -m pytest -q --junitxml=/tmp/resource-lifecycle-v1_1-baseline.xml`；失败来自 ignored 大型资产未挂载及沙箱 socket `EPERM`，最终按 test ID 比较 |
| lifecycle baseline | `179 passed, 4 skipped, 34 subtests passed` | `python3 -m pytest -q tests/test_resource_lifecycle_*.py` |
| real CodeQL lifecycle baseline | `27 passed, 10 subtests passed` | `DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_resource_lifecycle_codeql.py`；CodeQL 2.23.8 / javac 21.0.12.1 |

## Task 2 完成证据

- lifecycle Program/facts 及全部 `resource-*` JSON 输出统一为 schema `1.1`，tool identity 为 `resource-lifecycle-v1.1`；旧 `1.0` Program/facts 只在无 v1.1 relation/population/executor 字段时兼容读取，legacy raw facts 会在旧 ID/snapshot/derived-unit 校验后归一化为当前模型；旧 named-v1 recording 只由 exact-field/typed loader 受限读取，新 private recording 与 validation 输出均为 `1.1`。P0 schema/tool `2.5/0.4.0` 未改。
- 关系/群体 IR 定向：`8 passed, 44 deselected, 2 subtests passed`；solver/CLI/CodeQL 非 Fixture：`77 passed, 4 deselected, 13 subtests passed`。
- Task 2 reviewer 四项定向：`5 passed, 6 subtests passed`；CodeQL + recorded LLM：`62 passed, 4 skipped, 23 subtests passed`；lifecycle 全量：`209 passed, 4 skipped, 48 subtests passed`。
- 真实 CodeQL：query compile `Done [1/1]`，四个 source fixture 为 `31 passed, 12 subtests passed`；direct/embedded QL 字节一致。

## G1–G8 当前状态

| Gate | 状态 | 当前证据/缺口 |
| --- | --- | --- |
| G1 实例一致性 | `pass` | `tests/test_resource_lifecycle_solver.py`：旧实现定向 `3 failed, 2 passed`，扩展 per-instance 断言为 `5 failed`；修复后 solver+CLI `42 passed, 6 subtests`，全 lifecycle `183 passed, 4 skipped, 34 subtests` |
| G2 源码关系 | `fail` | Task 2 schema `1.1` IR 已通过严格 round-trip/reference GREEN；Task 3 仍需让真实 query 输出可组合 CFG/call/capture/termination 关系 |
| G3 主求解异步 | `fail` | `commands._analyze_payload` 先 `solve`，后 `_async_stages` 展示后继 |
| G4 释放与持有收益 | `fail` | 尚无 S2/S3 源码成对主求解差异 |
| G5 群体检查 | `fail` | `InvariantCandidate` 仍接受 `initial_holds/transitions_preserve/covers_writers` 输入布尔值，未从 q/a 转移检查归纳性 |
| G6 源码验收 | `fail` | 尚无六组十二变体的真实 CodeQL 验收 |
| G7 固定输入增益 | `fail` | 当前 local/full 对照来自人工 IR，未对相同源码事实删除跨事件传播能力 |
| G8 可审阅交付 | `fail` | v1.1 报告、门槛证据、失败集合差分和 HANDOFF 尚未生成 |

## 失败与环境记录

- 第一次 `git worktree add` 因 `.git` 在沙箱内只读失败；经显式审批后成功创建隔离分支，没有修改外层脏工作区。
- zsh 初始化会打印 `iptables: Failed to initialize nft: Operation not permitted`；它不是测试失败。
- 本轮不恢复 ignored `frameworks/`、`databases/`、历史 `results/` 到 worktree，不运行服务、PoC 或动态 DoS。
