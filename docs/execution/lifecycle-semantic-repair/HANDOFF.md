# Semantic Repair 交接

交付分支：`codex/lifecycle-semantic-repair-20260922`。`delivery_state_at_commit=ready_for_push`。本轮研究验收partial，工具初验fail；提交与push应在完成后用Git远端SHA单独核验。源代码已经完整测试，不需要为了提交重新跑目标程序。

## 结果与停止点

固定21项目认证冻结事实的下游回放21/21成功；132 findings、126 families全unknown，0/33正式命中，阳性TP/FP/未复核0/0/0，两precision为null。真实bridge性质消费0，历史backend精确调用次数未知。S1/S2/S4/S5通过，S3因真实前提未建模而partial，S6待提交后核验。

已修复评价统计、资源身份/切面/假设消费和旧非证明兼容。旧bounded及篡改/错绑继续拒绝；27个finding ID按新canonical身份更新、所有verdict不变。7条具体假设进入断言、结论、证书与人读报告。

全仓可收集1913 passed /13 failed /60 skipped /1095 subtests，新增失败0；另1个已知依赖缺失的收集项明确排除。不要写“全仓通过”。详细失败ID、命令和测试时dirty源码身份见`reports/lifecycle-semantic-repair/test-evidence.json`；概要见`summary.md`。

## 输入与实现身份

测试时HEAD：`3e2690ec55e14bd62fcea85e97d17cec2a71b43b`，包含dirty修复。完整234个Python文件内容hash：`bbf32d6175cedea3d2439d2ead33c82417fef4169fde783e34edf94278226b7e`。回放dosweb范围hash：`9a94aba5806d59805f39d1d8659a17d993c44b07f1a578f83d403c2f100c9eec`。不要将旧HEAD误认为已包含修复。

- 主资产根：`/home/furina/new_tool/dos-analysis-web`，只读。
- 冻结run：`lifecycle-e2e-poc33-api2cn-20260920_003322`，full/recall目录保留。
- 历史动态记录：`poc33-real-llm-full-v2-20260824_110233-dynamic-validation`，只作事后评价，不运行复现。
- 生命周期实现v17、结论v9、报告v2；完整版本和旧生产者身份见run-manifest。
- 本次原始回放输出：本工作树`.verification/independent-legacy-nonproof-replay-v3`；旧失败v1/v2保留，不覆盖。
- 最终独立审计：`.verification/final-frozen-audit-v1`；最终评价：`.verification/final-evaluation-v1`；紧凑结果复制到reports/lifecycle-semantic-repair。

## 可复跑的离线命令

在已交付分支的工作树根执行。所有输出必须使用尚不存在的新目录；不覆盖本次证据。没有原始冻结资产时，下面的真实输入复跑不可完成，不能用合成结果替代。

```bash
set -euo pipefail
MAIN=/home/furina/new_tool/dos-analysis-web
RUN=lifecycle-e2e-poc33-api2cn-20260920_003322
BATCH="$MAIN/results/java_web_dos_batch/$RUN-full"
RECALL="$MAIN/results/java_web_dos_batch/$RUN-recall"
DYNAMIC="$MAIN/results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-dynamic-validation"
AUDIT="$PWD/.verification/manual-semantic-audit"
REPLAY="$PWD/.verification/manual-semantic-replay"
EVAL="$PWD/.verification/manual-semantic-evaluation"
test ! -e "$AUDIT" && test ! -e "$REPLAY" && test ! -e "$EVAL"

PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_lifecycle_semantic_repair.py   --batch "$BATCH" --recall "$RECALL"   --known-cases reports/lifecycle-semantic-repair/audit-input-known-cases.csv   --output "$AUDIT"

PYTHONDONTWRITEBYTECODE=1 python3 scripts/replay_lifecycle_frozen_conclusions.py   --batch "$BATCH" --implementation-root "$PWD" --output "$REPLAY"

PYTHONDONTWRITEBYTECODE=1 python3 docs/execution/lifecycle-semantic-repair/rebuild_evaluation.py   --batch "$BATCH" --recall "$RECALL" --dynamic "$DYNAMIC"   --replay "$REPLAY" --audit "$AUDIT" --output "$EVAL"
```

`audit-input-known-cases.csv`是原有33记录的评价侧唯一别名规范化，原短ID另列保存；源CSV与truth hash见`audit-input-provenance.json`。分析器不消费该文件。重放校验原始stage产物哈希，再重算受影响conclude/report；不启动CodeQL、LLM、服务、PoC或压力负载。不能把168条历史selected-query元数据说成本次执行。

### 回归测试

```bash
umask 0022
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider   tests/test_production.py tests/test_production_e2e.py   tests/test_poc33_demo_evaluator.py tests/test_benchmark_evaluator.py   tests/test_resource_lifecycle_production_bridge.py   tests/test_resource_lifecycle_binding_consumer_isolation.py   tests/test_assertions.py tests/test_certificates_and_reports.py   tests/test_semantic_repair_metrics.py tests/test_semantic_repair_audit.py   tests/test_semantic_repair_assumption_chain.py tests/test_semantic_repair_legacy_nonproof.py

# 全仓可收集测试仍有13条基线失败，期望记录真实exit1，不当作绿灯。
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider   --ignore=tests/test_dynamic_validator_skill_contract.py
```

被排除的一项仍引用已迁移的全局skill脚本，原始收集错误已保存。固定umask是命令级测试环境，不修改主机全局权限。两个旧proof-gate测试改为完整canonical record和认证字节层fixture，原判定断言与真实schema验证未放宽。

## Git核验与协作来源

`source-provenance.json`记录从同目标并发任务固定复制的已验证源码hash；本分支加入独立审阅、旧非证明兼容和最终验证。20260923工作树及外层用户dirty文件没有被覆盖。只提交本分支明确拥有的源码、测试、文档与紧凑报告，不提交临时源码备份、数据库或大原始产物。

提交后执行普通push和精确比对，不force、不合并默认分支：

```bash
set -euo pipefail
branch="$(git branch --show-current)"
test "$branch" = codex/lifecycle-semantic-repair-20260922
git push --set-upstream origin "$branch"
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git ls-remote --exit-code origin "refs/heads/$branch" | cut -f1)"
test "$local_sha" = "$remote_sha"
printf 'push_status=verified\nbranch=%s\ncommit=%s\n' "$branch" "$local_sha"
```

本轮交付完成后停止。保留真实模型覆盖和可达性缺口，178-target保持暂停；不自行开启新目标、动态验证或下一轮方法扩展。

## 交付文本格式

本分支CSV由生成器的CRLF行尾规范为LF，逐文件确认解析后的全部单元格完全一致；生成时原字节和交付字节的SHA均在run-manifest.json的delivery_csv_line_ending_normalization中保留。原始冻结run与本地重放输出未改动。复跑生成的CSV可能仍为CRLF，应比较解析记录或执行同样的显式行尾规范化，不能把这一文本格式差异当作判定变化。
