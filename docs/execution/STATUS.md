# Resource Lifecycle v1 执行状态

- 目标：完成离线资源生命周期 IR、共享状态求解、事件连接、上界检查、静态事实适配、重放、评价、报告和 Git 推送。
- 实际基线 SHA：`93195ce8bbc4642ae103b928b51cbd984d4aef46`
- 实现分支：`codex/resource-lifecycle-v1-20260907`
- 隔离工作树：`.worktrees/resource-lifecycle-v1-20260907`
- 远端：`origin` 对应预期仓库 `skadiscarlet/dos-analysis-java-web`
- 当前阶段：M0–M6 完成。

## 工作区保护

开工时主工作树已有用户改动：`CHANGELOG.md` 已修改、一个会话 HTML 已删除、目标文档和一份研究文档未跟踪。本轮从确认基线新建隔离 worktree；没有 reset、clean、删除或暂存这些用户改动。

## 基线检查

命令：

```bash
python3 -m pytest -q --tb=no
```

结果：`101 failed, 618 passed, 22 skipped, 355 subtests passed`。

失败分类：

- 隔离 worktree 不包含主工作树中未跟踪或 ignored 的大型 `build/`、`results/`、`frameworks/`、`databases/` 运行资产，导致历史 benchmark/corpus 断言失败。
- 当前受限执行环境禁止创建本地监听 socket，导致 `tests/test_deepseek_client.py` 的 HTTP server setup 批量失败。
- 上述失败发生于任何本轮实现前，作为环境/资产基线保留；本轮不会通过改弱断言或跳过语义路径消除它们。

## 里程碑记录

| 里程碑 | 状态 | 证据 |
| --- | --- | --- |
| M0 仓库映射与基线 | complete | 本文件、`REPO_AUDIT.md`、实施计划 |
| M1 共享资源状态求解器 | complete | `25 passed, 24 subtests passed`（含现有 release 回归） |
| M2 事件连接和上界检查 | complete | `26 passed`（M1+M2 定向集） |
| M3 离线源码到报告 | complete | 最终真实 CodeQL fixture `27 passed, 10 subtests passed` |
| M4 摘要与证据闭环 | complete | recorded replay、完整 Java source snapshot/call column/exact callee 绑定、0600 私有 artifacts、result/evidence/summary 重算；无 live 调用 |
| M5 固定输入对照与消融 | complete | 24 个成对 case；完整模式 24/24 匹配；144 行模式结果 |
| M6 整理、回归、提交和推送 | complete | 双 reviewer `Ready`、0 Critical/Important；报告、全套验收与交付审计完成，最终 commit/push SHA 由会话回复和远端 branch ref 记录 |

## 执行命令

- `git worktree add .worktrees/resource-lifecycle-v1-20260907 -b codex/resource-lifecycle-v1-20260907 93195ce...`
- `python3 -m pytest -q --tb=no`
- `codeql version --format=json`

## 结果路径

- 计划：`docs/superpowers/plans/2026-09-07-resource-lifecycle-v1.md`
- 最终评价：`reports/lifecycle-v1/`
- 最终交接：`docs/execution/HANDOFF.md`

## 阻塞与下一动作

当前无本轮必需实现或外部访问阻塞。spec/soundness 与 code-quality reviewer 都已基于最终锁、单-fd snapshot 和 audit-only 文档给出 `Ready`，Critical/Important 均为 0。终审确认 recorded summary 在现有 production QL 下是 audit/display-only：同位 static operation 会记录 `llm_proposed_effect_already_static` 且不重复执行；独立 callee-summary witness 与 live provider 仍未实现并明确列为限制。全仓历史资产测试在隔离 worktree 中不可作为干净基线，最终同时报告生命周期自包含测试、真实 CodeQL fixture 结果和该环境型全仓基线。

最终验证命令与结果：

- `python3 -m pytest -q tests/test_resource_lifecycle_*.py` → `179 passed, 4 skipped, 34 subtests passed`。
- `DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_resource_lifecycle_codeql.py` → `27 passed, 10 subtests passed in 171.48s`。
- `python3 -m pytest -q tests/test_lifecycle_releases.py` → `14 passed, 24 subtests passed`。
- `python3 -m compileall -q dosweb scripts`、direct/embedded QL `cmp`、`git diff --check` → 全部 exit 0。
- `python3 -m pytest -q --tb=no` → `101 failed, 797 passed, 26 skipped, 389 subtests passed`。101 个失败与实现前基线同数；fresh traceback 分别确认 `results/applications_dynamic_validation/binary_truth_collection.json`、`frameworks/` 等 ignored 资产在隔离 worktree 缺失，以及 `ThreadingHTTPServer` 创建 socket 被 sandbox 以 `PermissionError: [Errno 1] Operation not permitted` 拒绝。

### M1 结果

命令：`python3 -m pytest -q tests/test_resource_lifecycle_solver.py tests/test_lifecycle_releases.py`

结果：`25 passed, 24 subtests passed`。直接状态断言覆盖多持有者、recent/summary 强弱更新、close/heap 引用分离、unknown call、分支 merge、正常/异常出口和预算耗尽。下一动作：写 M2 event/invariant 红灯测试。

### M2 结果

命令：`python3 -m pytest -q tests/test_resource_lifecycle_solver.py tests/test_resource_lifecycle_events.py tests/test_resource_lifecycle_invariants.py`

结果：`26 passed`。事件验收区分 request return、submit、dequeue、completion、reject 和 cancel；上界验收区分原子容量、写入者覆盖、归纳失败、item size 与 timeout。

### M3 结果

- 无网络 CLI/contract：`python3 -m pytest -q tests/test_resource_lifecycle_cli.py tests/test_resource_lifecycle_codeql.py` → `5 passed, 1 skipped`。
- 真实源码链最终复测：`DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_resource_lifecycle_codeql.py` → `27 passed, 10 subtests passed in 171.48s`。
- 真实链使用 javac、CodeQL 2.23.8、`ResourceLifecycleFacts.ql`、严格 decoder、IR adapter、共享 solver 与 invariant checker；同步 finally、异步未知容量和容量 2 反例均从源码事实得出。

### M4 结果

早期命令：`python3 -m pytest -q tests/test_resource_lifecycle_summaries.py tests/test_resource_lifecycle_replay.py`

早期结果：`14 passed`。此后已增加 recorded replay 全链：请求绑定 exact call path/line/column、caller file SHA、完整 Java source snapshot、canonical exact callee、model/contract/budget；recording 与 validation snapshot 固定 0600 regular file；重放重新验证 proposal、求解 state、重建 evidence/`summary.md` 并检测篡改。analyze/replay 通过 owner-only bounded `flock` 串行化同目录发布，私有 JSON 的 bytes/SHA/parse 来自同一有界 `O_NOFOLLOW` fd。当前生命周期全套为 `179 passed, 4 skipped, 34 subtests passed`；真实 QL 不提供独立 callee-summary witness，故 replay 是 audit/display 接口测试，不是 live LLM 或 solver enrichment 验收。

### M5 结果

命令：`python3 -m pytest -q tests/test_resource_lifecycle_regression_suite.py` 与 `python3 -m dosweb.cli resource-evaluate --suite tests/fixtures/resource_lifecycle/regression-suite.json --out reports/lifecycle-v1`

结果：`6 passed`；最终报告已由定稿代码重新生成并逐项核对：12 组 24 个性质先验 case 的完整模式 24/24 匹配，完整模式加五种信息删除消融共产生 144 行逐例结果，suite SHA 为 `8506931faf8971684931102d1c41e7f91a4f32e533a183d24477706c93334411`。29 条历史记录只静态读取 metadata，因未完成独立 lifecycle 标签与源码适配，0 条进入指标分母。最终远端提交 SHA 不写入被该提交自身包含的文档，由分支引用和执行结束回复核对。
