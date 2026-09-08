整体状态：complete
已完成：M0 仓库映射与基线；M1 共享资源状态求解；M2 事件连接与上界检查；M3 离线源码到报告；M4 摘要与证据闭环；M5 固定输入对照与消融；M6 双重终审、固定报告、最终验证、交付审计与独立分支交付全部完成。
尚未完成：无本轮必需模块；live LLM、独立 callee-summary witness、通用 async Release、aggregate total-held proof 及 reviewer Minor 是明确支持边界，不属于伪装完成项。
代码基线 SHA：93195ce8bbc4642ae103b928b51cbd984d4aef46
实现分支：codex/resource-lifecycle-v1-20260907
测试结果：生命周期自包含 `179 passed, 4 skipped, 34 subtests passed`；真实 javac/CodeQL `27 passed, 10 subtests passed`；旧 P0 release 回归 `14 passed, 24 subtests passed`；compileall、双份 QL cmp、diff-check 均 exit 0；全仓 `101 failed, 797 passed, 26 skipped, 389 subtests passed`，101 个失败与实现前基线同数且 fresh traceback 归因为隔离 worktree 缺 ignored `results/frameworks` 资产及 sandbox socket `EPERM`。
端到端模式：真实源码通过本地 javac→CodeQL query→strict decoder→IR adapter→共享 solver；导入事实要求 strict rows、query SHA、完整 Java source snapshot 和显式 entry callable；人工 IR 仅验证状态语义与消融，不计作提取能力。
LLM：`--llm off` 完整可运行；`--llm replay` 接口/权限/identity/篡改测试通过，但当前 production QL 下只用于 audit/display、不增强 solver；`--llm live` 未实现，真实调用验证阻塞。
报告位置：reports/lifecycle-v1/
最值得下一轮人工审阅的三个语义问题：1）通用 async completion/cancel、后台消费者或过期路径仍无同步 Release 证明；2）per-queue 容量只证明 canonical queue scope 的 item count，不是 family aggregate total-held 上界；3）若未来让 LLM proposal 执行，必须先新增与 caller executable Effect 分离的精确 callee witness 与 exceptional CFG 证明。

# Resource Lifecycle v1 交接

## 实现边界

Resource Lifecycle v1 是与 v2 P0 formal pipeline 并行的离线状态分析链。它没有改变 schema/tool `2.5/0.4.0`、formal query-failure 规则或普通扫描的三值静态结论。新链路使用独立的 `lifecycle_status` 与 `impact_status`，不输出 vulnerability 布尔量，也不把静态性质写成动态 confirmed。

共享模型严格区分 resource family、recent/summary instance、holder、event、effect、transition、close obligation、held count 和 item size。同步与异步操作调用同一状态转移；dispatch 展开 submit/start/complete/reject/cancel，未知契约、writer coverage、身份、大小、预算或 path coverage 都保守返回 `unknown`。

## 输入与运行

- `manual_fixture`：用于 12 组 24 例性质先验回归与五种信息删除消融。
- `static_verified_json`：要求本地 Java source root、query SHA、显式 `entry_methods` 和完整 source-tree snapshot；调用方提供的 rows 不等于本工具完成了源码提取。
- `codeql_database`：在用户提供的离线 Java CodeQL database 上运行双份字节一致的 `ResourceLifecycleFacts.ql`，不启动目标服务。

实际命令见 `README.md`。基本路径不需要网络或 API key：

```bash
dos-web-analyzer resource-extract --manifest tests/fixtures/resource_lifecycle/manual-manifest.json --out /tmp/resource-lifecycle-facts
dos-web-analyzer resource-analyze --facts /tmp/resource-lifecycle-facts/facts.json --out /tmp/resource-lifecycle-run --llm off
dos-web-analyzer resource-replay --run /tmp/resource-lifecycle-run
dos-web-analyzer resource-evaluate --suite tests/fixtures/resource_lifecycle/regression-suite.json --out /tmp/resource-lifecycle-evaluation
```

analyze/replay 使用同一 owner-only run-directory lock 串行化受管 artifact 发布。复用 `--out` 时只清理本工具已知的 stale/mode-specific 文件，未知用户文件保留；unsafe managed/lock path fail closed。facts、private recording 与 private summary 的 bytes、SHA 和 JSON 都来自同一个有界 `O_NOFOLLOW` fd。

## Recorded summary 的准确口径

recording 绑定 exact unknown call、source path/line/column、caller file SHA、完整 Java source snapshot、canonical exact source callee、model、contract 和 budget。普通虚调用、external callee、return escape、跨 instance/同行其他 AST 借证都不能进入验证。

当前 QL 没有独立 callee-summary witness。proposal 若复述 caller program 已存在的 static operation，会保留 `verified`/display provenance，同时记录 `llm_proposed_effect_already_static` 并保持 `usable_effect_ids=[]`，防止重复 create/dispatch。因此 replay 是可重算的 audit/display 接口，不是 live provider 或生产 solver enrichment。原 `unknown_call`、coverage gap 与 exceptional gap 始终保留；`drop`/`release` 永不作为消除或 bounded 证明。

## 审查结果与已知 Minor

最终 spec/soundness reviewer 与 code-quality reviewer 都给出 `Ready`，Critical=0、Important=0。保留四个非阻塞工程/审计问题：

1. summary derivation 的 `code_locations` 不直接携带 call-site column；精确列仍可由 raw fact 与 summary request 恢复。
2. `resource-replay` 检测内容不一致时写 `replay.json.consistent=false`，但 CLI 仍返回 0；自动化调用方必须读取该字段。
3. run directory 校验 owner，但未额外拒绝 group/world-writable mode；多用户本地威胁模型可继续加固。
4. 单个 artifact 使用原子 replace，但整个 run 不是目录级事务；进程崩溃可留下不完整 run，后续 replay 会 fail closed。

## 评价与报告

固定 suite SHA-256：`8506931faf8971684931102d1c41e7f91a4f32e533a183d24477706c93334411`。完整模式预期为 24/24，输出 24 cases × 6 modes = 144 data rows；29 条历史资料只建立 metadata manifest，0 条进入 lifecycle 指标分母。报告不包含 private recording、完整模型请求、API key、数据库或原始 PoC。

最终报告哈希：`metrics.json` 为 `5277d9c9b6d1bd49e5e03e45025914aead03e007d17981b90c3dc50bc45616f9`，`run-manifest.json` 为 `eb0f926d7eae8b926cf1be3aad57ca2cf3c7c12a802c4036c0f246a6f660d54e`，`cases.csv` 为 `de3877f0acc8041d7c8d7ff8d963adc2b307040637c7f1f893704387358dc714`，`summary.md` 为 `3ae322c3d3a2508b6993a4c2d55ea6bcd6e3a422924db062c1856358142ddc6d`。

## 安全与复现限制

本轮没有运行 `reproduce.sh`、`probe.py`、目标服务、动态 DoS、压力测试或历史案例复现，也没有修改 `../dos-analysis/`。保留资产目录未删除或重写。最终 Git commit SHA 不写进本文件，避免提交自引用；应以分支远端引用为准。
