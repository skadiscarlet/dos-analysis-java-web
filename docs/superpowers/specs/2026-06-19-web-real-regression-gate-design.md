# WEB-REAL Regression Gate Design

日期: 2026-06-19

## 背景

`docs/drd_inspired_rearchitecture_plan.md` 的第一、第二部分已经把 Phase 3 从裸 sink 扫描推进到 proof-carrying 候选，并通过 Jersey OAuth、Jersey multipart、Undertow LearningPush、Undertow MCMP 和 Jetty ProxyServlet bridge 覆盖 5 个已动态验证真阳。当前 `scripts/check_web_real_coverage.py` 能确认 5/5 hit，但期望逻辑硬编码在 Python lambda 中，无法扩展为第三部分要求的回归资产、proof coverage 统计或 Phase 4 评估输入。

第三部分第一轮采用“回归门禁优先”路线：先把已验证漏洞变成 manifest 驱动的 known-vuln regression gate，再在后续迭代中扩展 capacity/lifespan proof 和 proof-aware ranking。

## 目标

- 新增 manifest，记录 `WEB-REAL-*` 的静态回归预期。
- 用通用 checker 读取 manifest 和 Phase 3 CSV，输出 `hit`、`partial`、`missing`。
- 生成机器可读 regression report，供 Phase 4 evaluation summary 后续消费。
- 保持现有 `scripts/check_web_real_coverage.py` 命令可用，避免破坏当前工作流。
- 第一轮 gate 要求当前 5 个 `WEB-REAL-*` 全部为 `hit`。

## 非目标

- 不修改 AOSP 侧 `../dos-analysis/` verdict 语义。
- 不在本轮重写 Phase 4 权重。
- 不新增 CodeQL 查询或扩大 source/data-flow 覆盖面。
- 不把 validation recipe 的动态复现实验步骤一次性塞进 manifest；本轮只保留部署条件和静态识别字段。

## 方案选择

推荐方案是 manifest + checker + summary 的最小闭环。相比直接调整 Phase 4 排序，这能先固定已验证真阳的静态覆盖事实，避免把“回归门禁”和“新候选优先级”混在一起。相比同时生成 validation recipe，这一轮范围更小，能更快成为第三部分后续工作的稳定入口。

## Manifest 结构

新增 `intel/regression/web_real_manifest.json`。顶层包含 manifest 元信息和 cases 列表：

```json
{
  "schema_version": 1,
  "description": "Static regression expectations for dynamically verified WEB-REAL cases.",
  "cases": []
}
```

每个 case 至少包含：

```json
{
  "id": "WEB-REAL-0005",
  "framework": "jetty",
  "component": "jetty-proxy / jetty-client",
  "dynamic_verdict": "default_heap_oom_confirmed",
  "required": [
    {"field": "framework", "op": "equals", "value": "jetty"},
    {"field": "candidate_family", "op": "equals", "value": "client_destination"},
    {"field": "request_flow_kind", "op": "equals", "value": "client_request_flow"},
    {"field": "sink_shape", "op": "equals", "value": "retained_map_compute"},
    {"field": "retained_field", "op": "contains", "value": "destinations"}
  ],
  "expected": [
    {"field": "receiver_proof", "op": "contains", "value": "HttpClient.destinations"},
    {"field": "growth_driver_kind", "op": "equals", "value": "origin_key"}
  ],
  "deployment_condition": "ProxyServlet deployment maps attacker-controlled request data to HttpClient destination origin/tag.",
  "notes": "Harness maps attacker parameter to Jetty Request.tag() for the retained Origin.tag path."
}
```

`required` 字段用于判定是否命中目标候选；`expected` 字段用于区分完整命中和部分命中。第一轮支持三种匹配操作：

- `equals`: 字段归一化后必须完全相等。
- `contains`: 字段归一化后必须包含指定字符串。
- `one_of`: 字段归一化后必须属于指定字符串数组。

## Checker 行为

新增 `scripts/check_web_real_regression.py`，默认读取：

- manifest: `intel/regression/web_real_manifest.json`
- 输入 CSV: `results/phase3/phase3_candidate_features.csv`
- 输出 JSON: `results/phase3/web_real_regression.json`

判定规则：

- `hit`: 至少一条候选满足该 case 的所有 `required` 和 `expected` 规则。
- `partial`: 至少一条候选满足所有 `required` 规则，但缺少一个或多个 `expected` 规则。
- `missing`: 没有候选满足所有 `required` 规则。

命令退出码：

- 全部 case 为 `hit` 时返回 0。
- 任意 case 为 `partial` 或 `missing` 时返回 1。
- manifest、CSV 或 schema 无效时返回 2。

终端输出保持简洁，每个 case 一行，包含状态、匹配到的 `sink_id` 和缺失字段摘要。JSON report 记录完整 case 结果、匹配候选摘要、缺失规则、总 recall 统计和生成时间。

## 兼容层

保留 `scripts/check_web_real_coverage.py`，将其改为调用新 checker 的默认配置。这样现有文档和命令仍然有效，但实际期望来源从 hard-coded matcher 迁移到 manifest。

## 输出报告

`results/phase3/web_real_regression.json` 建议结构：

```json
{
  "generated_at": "2026-06-19 22:01",
  "input_csv": "results/phase3/phase3_candidate_features.csv",
  "manifest": "intel/regression/web_real_manifest.json",
  "total_cases": 5,
  "hit": 5,
  "partial": 0,
  "missing": 0,
  "known_vuln_recall": 1.0,
  "cases": []
}
```

Phase 4 第一轮不强制消费该文件；后续 proof-aware ranking 可把 `known_vuln_recall`、`proof_coverage` 和 `noise_guard` 统计并入 `results/phase4/evaluation_summary.json`。

## 测试与验收

第一轮实现后应运行：

```bash
python3 scripts/check_web_real_regression.py
python3 scripts/check_web_real_coverage.py
python3 scripts/check_phase3_consistency.py
./dos-web-analyzer analyze
PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity
PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py
```

验收条件：

- 5 个 `WEB-REAL-*` 全部为 `hit`。
- `scripts/check_web_real_coverage.py` 仍可用，并与新 checker 返回一致结果。
- 新增 JSON report 可复现记录每个 case 匹配到的 `sink_id`。
- Phase 3 consistency、Phase 4 analyze、AOSP monotonicity 和 AOSP regression 不退化。

## 后续扩展

- 将 Dr.D 兼容案例加入独立 `intel/regression/drd_compat_manifest.json`。
- 给 manifest 增加 optional `capacity_expectations` 和 `lifespan_expectations`，支撑第三部分第二轮 proof checker。
- 让 `scripts/run_phase4.py` 消费 regression report，在 `evaluation_summary.json` 中输出 known-vuln recall、proof coverage 和 top-N visibility。
- 基于 high-risk 候选生成 validation recipe，但不影响本轮 gate 的静态回归语义。
