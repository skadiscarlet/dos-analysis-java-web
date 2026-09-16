# Resource Lifecycle v1.2 交接

implementation_status: partial
delivery_state_at_commit: ready_for_push
actual_base_commit: 2ee16220e78dd088ab5c67277696429e71d53c71
branch: codex/resource-lifecycle-v1_2-20260914

## H1–H6

| 门槛 | 状态 | 证据 |
| --- | --- | --- |
| H1 正式性质一致 | pass | reports/lifecycle-v1.2/gates.json；本地 tests/source-frozen.xml |
| H2 项目输入与完整分母 | pass | reports/lifecycle-v1.2/input-ledger.csv；本地 project-frozen-01/project-results.json |
| H3 分片与完整语义重放 | pass | reports/lifecycle-v1.2/scaling.json；本地 tests/cli-sharded.xml |
| H4 两个独立已有模块 | blocked | 未提供明确的独立源码输入，实际模块数 0 |
| H5 诚实分层评价 | pass | reports/lifecycle-v1.2/comparison.csv、metrics.json |
| H6 可审阅交付 | pass | 已核查九项报告、126 条分层台账、性质引用、脚本 hash、失败 ID 差分及本轮文件清单；gates.json |

## new_capabilities

唯一 `properties` 发布接口供普通分析、评价和回放共享；多资源逐条输出。`resource-project` 支持精确方法与已有 GrowthCandidate/EntryFact 观测导入，旧判断不进入求解，完整记录阶段状态，重复输入复用计算。`lifecycle-run-2` 保存有界分片与完整选中单元 facts 目录，绑定身份并重新求解、比较性质和证据，支持相同源码树的跨目录重绑定。缺失/篡改/不一致 CLI 返回非零。

P0 schema/tool 2.5/0.4.0 与双份 CodeQL 查询未改；LLM off，无服务启动或动态验证。

## source_inputs 与 property_consistency

- 独立已有项目/模块：0。H4 缺资产，不能用新造样例或重命名副本抵充。
- 多资源自包含 Java fixture：6 条请求，3 mapped/analyzed（方法、重复方法、候选），1 ambiguous、1 missing、1 stale；唯一计算单元 1、资源族 2、正式性质 6。候选准确引用其中 3 条，重复方法复用原性质 ID。
- 十二例源码对照：复用规模 1× 的同一 raw facts；不增加独立实验。
- 规模副本：1×/2×/4× 分别 12/24/48 个单元，全部分析、完整语义重放。
- 人工 IR：24 个模型输入，独立列为工程回归，非源码结果。

真实多资源测试重新调用普通分析、评价选择与搬迁后回放，性质 ID/维度/scope/cut/语义相同；修改 oracle 不改变分析结果。

## scaling_and_replay

| 规模 | 选中 facts | event states | 性质 | 总序列化 bytes | 最大分片 bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1× | 370 | 337 | 71 | 8,972,744 | 34,408 |
| 2× | 740 | 674 | 142 | 17,883,020 | 34,408 |
| 4× | 1,480 | 1,348 | 284 | 35,703,572 | 34,408 |

2×/4× 超过旧单文件 16 MiB，所有单片仍低于原上限。最终运行复用历史真实 javac/CodeQL 提取：`extraction_reused=true`，本次编译/提取时间 null，历史日志/hash/成本单列；新实现重新验证、求解、序列化和迁移回放。峰值分析器 RSS 分别 81,760,256 / 118,509,568 / 195,792,896 bytes，不含外部编译器/CodeQL。

完整规模回放为 `semantic_replay/full_run`；partial 项目为 `semantic_replay/selected`。原始全量 raw snapshot 仅作 provenance（`original_input_snapshot_recomputed=false`），完整选中单元 facts 目录实际校验。哈希不是签名认证，分片不解决单元状态爆炸。

## evaluation

原 oracle 保留。full 10/12 匹配、5 unknown；消融 12/12、9 unknown；确定性质增益 4。`s2-task-only`、`s2-field-holder` 的 callee execute rejection → wrapper/caller 异常 CFG 缺口没有被证明，后端保持 unknown。删除旧评价器计数推断后暴露不匹配，不以标签或计数补出 bound。

人工 IR full 24/24、11 unknown。期望 unknown 的匹配不是检出。关系数量与按维度确定比例见 metrics.json，均为已观测模型覆盖，不是穷尽召回率。

同环境全仓 baseline：1056 passed、40 skipped、101 failed、1 error；当前：1102 passed、41 skipped、101 failed、1 error。失败/错误新增 ID 为 0；skip 新增 2、移除 1、持续 39。所有 ID 在 baseline-test-diff.json；不是全绿。真实源码一致性补充 1 passed，CLI 必需分片损坏拒绝 1 passed。

## 实现身份与交付范围

被测核心源码 SHA-256：`4c4b32cc7bbfa915b222a86b6c9621b1f4398627c55cb7a20cb5de4d4403d8b8`。同内容实现 commit：`a4295d417c15a1673ec2eb1a2315c13c13b0bfe6`。

实际启动运行时 HEAD 是固定基线且 dirty=true；不将后续 commit 冒充运行时 HEAD。最终报告另记 report-generation HEAD、核心内容 hash、查询来源及两个编排脚本 hash。规模脚本排序修复与最终报告在后续交付提交中记录。

GitHub 仅包含代码、合成 fixture/清单、紧凑汇总和文档；数据库、分片、真实日志不提交。公开报告能审阅分母、性质、对照、失败 ID 和 hash，但仅 Git checkout 不能读取本地原始证据，需要以下重跑或本地路径。

## 本地持久结果

worktree：`/home/furina/new_tool/dos-analysis-web/.worktrees/resource-lifecycle-v1_2-20260914`

以下均相对于该 worktree：

- `.local-runs/v1.2/final/`：最终原始验收根目录。
- `.local-runs/v1.2/final/project-frozen-01/`、`.local-runs/v1.2/final/project-replay.json`：项目实际提取、分片和回放。
- `.local-runs/v1.2/final/scaling-frozen-01/`：最终 1×/2×/4× 源码副本、分片与完整回放。
- `.local-runs/v1.2/scaling-frozen-01/`：此前真实编译提取的来源与成本证据。
- `.local-runs/v1.2/final/scaling-input-order-failure/`：顺序规范化修复前失败证据，未覆盖。
- `.local-runs/v1.2/final/tests/`、`.local-runs/v1.2/final/manual-ir/`：XML、日志及人工 IR。

## reproduce

依赖：Python 3.12.9、Java 21.0.12.1、CodeQL 2.23.8；安装项目及开发测试依赖。命令从 worktree 根目录运行，输出必须用新目录，CodeQL 查询串行执行。

```bash
# 从零真实编译、提取、求解和跨目录回放规模组。
python3 scripts/evaluate_lifecycle_v12_scaling.py --out .local-runs/v1.2/scaling-new

# 复用已核对的真实提取，仅重新验证/求解/分片/回放。
python3 scripts/evaluate_lifecycle_v12_scaling.py \
  --reuse-from .local-runs/v1.2/scaling-frozen-01 \
  --out .local-runs/v1.2/scaling-replay-new

# 最终源码一致性测试使用持久项目事实，未 mock。
DOSWEB_RUN_CODEQL_FIXTURES=1 \
DOSWEB_V12_PROJECT_RUN="$PWD/.local-runs/v1.2/final/project-frozen-01/analysis" \
python3 -m pytest -q tests/test_resource_lifecycle_properties_source.py

python3 -m pytest -q tests/test_resource_lifecycle_v12_cli.py
python3 -m pytest -q --continue-on-collection-errors --junitxml=/tmp/lifecycle-current-new.xml

# 从保留的原始验收目录再生紧凑报告，默认 H6 pending，审查后才加 delivery-reviewed。
python3 scripts/report_lifecycle_v12.py \
  --root-run .local-runs/v1.2/final --out reports/lifecycle-v1.2
```

项目从零 CodeQL database 编译、接入和 replay 的完整命令见根 README 的 v1.2 示例。正式模板以该 fixture manifest 为 schema 参考；替换 project_id、source_root/tree_hash、匹配数据库与精确 selection，不沿用样例身份。全仓 baseline 比较须在固定基线独立 checkout、同环境执行相同 pytest 命令。

## remaining_gaps / next_action

提供至少两个独立已有模块的明确本地路径、版本、离线构建配置和合计 6–10 个精确检查单元；冻结选择后执行真实提取与同事实对照，补齐 H4。未收到输入前整轮保持 partial，不扩大扫描范围。一般终止性、总字节上界、nested tasks、未知分派/alias/容量继续不在支持范围。

本提交只记录 ready_for_push；推送和远端 SHA 对齐在提交后验证，最终回复给出实际结果。
