# Lifecycle RC1 交接

工程状态：`rc_ready`；research_evidence：`unvalidated`；R1–R6 通过。

被测实现提交：`1a2d01aa2b605d8a9cbc76d1da0f05345845b5c4`。最终报告提交只包含报告、文档及报告展示补充，不冒充测试时 HEAD。完整证据见 [summary](../../../reports/lifecycle-rc1/summary.md)、[metrics](../../../reports/lifecycle-rc1/metrics.json)、[run-manifest](../../../reports/lifecycle-rc1/run-manifest.json)。

九请求全部提取，8 个精确方法解析成功；4 个非空单元（6 个资源族）在三个模块均完成求解和选中范围回放，预算退出为零；4 个方法为 resource_unmodeled，1 个原选择器 method_missing。该缺失来自原 readLog 返回包过期：请求 `com.xxl.job.core.biz.model.LogData`，冻结源码实际为 `com.xxl.job.core.openapi.executor.dto.LogData`，位置 XxlJobFileAppender.java:126；没有修改原选择器或用候选冒充成功。因此九输入复跑入口预期返回 **1**，台账完整保留这一真实身份失败，非空单元仍全部完成。

full/消融均为 1 bounded、17 unknown，确定性增益 0；call_bindings/task_bindings 均为 0，没有独立 oracle。原十二例两模式均 12/12，unknown 为 3/9、合成增益 6；这些工程回归不能证明独立研究收益。

最终同环境全仓：1212 passed、12 failed、46 skipped、1 collection error；相对基线零新增失败/错误 ID。新增默认 opt-in skip 的独立执行证据在 metrics 的 acceptance 中。沙箱禁用 socket 导致的另一轮 101 failures 单列为环境诊断，未混进对照。

最终原始验收：`.local-runs/rc1/release-nine/`、`release-synthetic/`、`tests/release-unrestricted.xml`、`tests/release-loops.xml`、`loop-comparison/current-release.json`。同事实 ArrowUtil steps 798→272、配置798→259；XXL 同步历史去重后248 steps。完整 common-core 为158文件、8,891事实行（旧查询8,885），传输未截断。

- 基线提交：`3ee3ea72ada4a0f3d7e65679fc8a1b2520052b3a`。
- 分支：`codex/resource-lifecycle-rc1-20260916`。
- delivery_state_at_commit：ready_for_push。提交后单独核验远端 SHA，不在提交中虚构自身 SHA。
- 输入固定为两个项目的三个模块、九个原 input_id。本轮属于开发/回归集；没有独立正确性 oracle，不报告准确率或召回率。
- 仅修改 resource-* 离线分析器。没有启动目标、执行 PoC、发送攻击请求或压力负载；原源码、数据库与归档不变。

## 本地资产与复跑

Python 3.12、Java 21、CodeQL 2.23.8，以及现有项目依赖。CodeQL 查询串行执行。

- 当前 worktree：`/home/furina/new_tool/dos-analysis-web/.worktrees/resource-lifecycle-rc1-20260916`。
- asset root：`/home/furina/new_tool/dos-analysis-web`。
- 冻结源码/DB：asset root 下 `.worktrees/resource-lifecycle-v1_2-20260914/.local-runs/v1.2/independent-20260916/`。
- 使用 `xxl-job-core`（52 文件）、`hertzbeat-common-core`（158 文件完整模块）、`hertzbeat-common-spring`（67 文件）；不使用旧 util-scope 重试目录替代完整模块。
- 原始固定方法清单复用 `docs/execution/lifecycle-v1.2/inputs/{module}.json`。原树 hash、每文件 hash、DB 归档 hash、query hash、选择与预算身份保留在运行目录和 run-manifest 引用的产物中。

```bash
python3 scripts/evaluate_lifecycle_rc1.py \
  --asset-root /home/furina/new_tool/dos-analysis-web \
  --out .local-runs/rc1/reproduction-new
# 原 readLog selector 已过期：预期 exit 1；检查各模块台账和回放，不能当作九项全成功。

# 资产位于不同路径时显式指定既有冻结目录；不复制整个大型资产树。
python3 scripts/evaluate_lifecycle_rc1.py \
  --asset-root /path/to/asset-root \
  --prior-run /path/to/frozen-independent-run \
  --out /path/to/new-output

# 必要真实源码回归，编译/提取但不运行 Java 目标。
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q \
  tests/test_resource_lifecycle_rc1_ingestion.py \
  tests/test_resource_lifecycle_rc1_loops.py \
  tests/test_resource_lifecycle_rc1_exceptions.py

# 常规离线回归与同环境失败 ID 对比的最终运行。
python3 -m pytest -q --continue-on-collection-errors \
  --junitxml=/tmp/lifecycle-rc1-current-new.xml
```

新输出目录不得已存在。入口逐模块保存 project 台账、源码范围、callable inventory、成本、正式性质/同事实消融以及选中范围语义回放；工程失败返回非零，正常零资源方法只记 not_applicable，不算非空求解。完整 Git checkout 不包含 ignored 大型原始资产。

紧凑报告可从保留的原始验收再生：

```bash
python3 scripts/report_lifecycle_rc1.py \
  --root-run .local-runs/rc1/release-nine \
  --acceptance .local-runs/rc1/acceptance.json \
  --out /tmp/lifecycle-rc1-report-new
```

`acceptance.json` 是按真实测试、回放、失败 ID 和源码身份审计生成的本地门槛记录；其完整内容与原始证据引用已嵌入已提交 metrics.json，可恢复后再生报告。最终合成验收明确复用经过 hash 绑定的真实提取，不把旧查询耗时记作本次测量。旧尝试和中断原因保留，未覆盖。

## 已实现边界

- 源码全树与提取归档分别建账；已用字节仍逐文件匹配，注释占位分类可审阅。缺声明/语义不确定仍 fail closed，build-mode=none 不代表成功编译。
- 生命周期传输最多 65,536 行，普通查询 4,096，保留 JSON、字符串、输出及单片大小限制；不截断 raw facts。
- 方法定位、资源识别、执行与性质状态分离；未知工厂/库方法不会被改为安全或上界零。
- 循环 SCC 配置使用包含关系、有限延迟 widening；历史分配与当前持有/义务/峰值分离，实例关系与任务阶段保留，摘要释放弱更新，抽象证据明确标注。
- 精确已建模 wrapper 的拒绝异常返回 caller cleanup；拒绝不建立成功派发/capture。保留原十二例源码和 oracle。
- 正式 properties、评价和回放复用原接口。新诊断沿用既有格式；旧运行由于实现 identity 不同需要重新分析，不宣称跨版本直接回放一致。

## 剩余限制与实验接续

工程可运行、支持模型内正确性、独立输入上的收益分别核验。RC1 没有独立 oracle；即使工程门槛通过，也不能称 paper-ready 或完整漏洞检测工具。外部依赖、深度>1、动态分派/反射、自定义嵌套任务、通用总内存和吞吐证明仍在范围外。

下一阶段仅留清单，本轮不自动执行：

1. 冻结真实输入总体、去重单位与独立标注规范，将这九方法标为开发集；另留未参与修复的评价输入。
2. 固定版本/规则/预算，对同一事实比较 full 与消融，区分覆盖、工程失败、unknown、确定结果、关系与成本。
3. 对支持范围匹配的强基线和真实反例做独立评价；合成 Java fixture 不计独立项目。
4. 仅修实验暴露的缺陷并记版本；语义修改后受影响样本转开发集。新框架、live LLM、总字节证明留后续。
