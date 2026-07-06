# Stage0-Stage5 工具完整流程设计

日期：2026-07-06

## 背景

`dos-analysis-web` v2 面向 Java Web 与相邻 Java 网络服务的资源耗尽型 DoS 静态分析。工具实现服务于统一模型：

```text
Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)
```

本设计把 `docs/research/` 下已经确定的 Stage1、Stage2/5、Stage3/4 研究设计整合为可开发的完整工具 pipeline。第一版不是 mock、stub 或规则降级版，而是完整实现：真实 CodeQL 查询、真实 LLM 调用、真实 ML ranker、真实 GECG、真实 Stage3 path proof、真实 Stage4 bound extraction、真实 Stage5 obligation proof。

普通扫描只输出：

```text
static_vulnerable
static_safe
static_unknown
```

工具不得恢复旧阶段化流程，不得恢复 legacy verdict compatibility，不得运行动态 DoS 验证，不得把静态结论表述为动态 confirmed。

## 设计目标

- 严格执行用户指定的 `Step0 -> Stage1 -> Stage2 -> Stage3 -> Stage4 -> Stage5` 顺序。
- 将 CodeQL、LLM、ML、SMT 作为阶段内部采用的技术依赖，而不是独立 pipeline worker。
- 第一版主输入为已有 CodeQL DB 和 Java 项目源码，不负责自动构建 CodeQL DB。
- 每个阶段只读上游 artifact，只写本阶段 artifact。
- Stage5 是唯一 verdict producer。
- `static_unknown` 表示完整 Stage5 证明系统运行后仍有 obligation 不可判定，不是工具失败的替代结果。
- 所有 artifact 必须有 schema、run provenance、producer、tool/model 版本和 evidence 引用。

## 非目标

- 不实现动态 DoS 验证。
- 不修改 `poc/` 归档内容。
- 不对 `databases/`、`frameworks/`、`results/` 做无界全仓搜索。
- 不提供 mock provider、stub ranker 或 rule-only fallback 作为产品路径。
- 不把 benchmark oracle label 映射到普通扫描结论。

## 总体 Pipeline

工具只暴露一个顺序主流程：

```text
Step0 Project Profiling
  -> Stage1 E extraction
  -> Stage2 G detection
  -> Stage3 E -> G flow proof
  -> Stage4 B candidate extraction
  -> Stage5 EffectiveB proof
```

对应 runner：

```text
dosctl run
  --source-root <java_project>
  --codeql-db <existing_db>
  --out results/v2/runs/<run_id>

Stage0ProjectProfiler
Stage1EntryExtractor
Stage2GrowthDetector
Stage3FlowProver
Stage4BoundExtractor
Stage5EffectiveBProver
```

关键约束：

- Stage0-5 是唯一 pipeline 节点。
- Stage1 不能判断 G 或 B。
- Stage2 不能证明 E->G flow。
- Stage3 不能判断边界有效性。
- Stage4 不能输出 `effective=true/false`。
- Stage5 是唯一能输出 `static_vulnerable/static_safe/static_unknown` 的阶段。
- LLM 输出只作为当前阶段的 claim 或 summary，必须由当前阶段 verifier 复核后才能进入阶段 artifact。
- ML ranker 只排序 Stage2 候选，不决定最终 verdict。
- CodeQL 查询由各阶段 runner 调用，但 CodeQL executor 只是库组件，不是独立 worker。

## 仓库模块划分

第一版实现建议采用 Python 包 + CodeQL query pack：

```text
dos_analysis_web/
  cli.py
  pipeline/
    coordinator.py
    run_context.py
    stage0_profile.py
    stage1_entries.py
    stage2_growth.py
    stage3_flows.py
    stage4_bounds.py
    stage5_verdict.py
  codeql/
    executor.py
    packs/
      dos-java-queries/
  llm/
    client.py
    prompts/
    claim_schema.py
  ml/
    ranker.py
    features.py
  schema/
    artifacts.py
    validators.py
  reporting/
    evidence_report.py
```

说明：

- `pipeline/stage*.py` 是唯一拥有阶段 artifact 写权限的模块。
- `codeql/`、`llm/`、`ml/` 是库，不是 pipeline 节点。
- `schema/` 统一定义 artifact dataclass、Pydantic model 或 JSON Schema。
- `reporting/` 只消费 Stage5 artifact，不参与判定。

## Run 目录结构

每次运行创建固定目录：

```text
results/v2/runs/<run_id>/
  run_manifest.json
  logs/
  profile/
    project_profile.json
  stage1/
    stage1_entries.jsonl
    stage1_source_models.yml
    dos_entry_sources.qll
    interface_slices/
    llm_source_claims.jsonl
    stage1_summary.json
  stage2/
    resource_sink_rules.jsonl
    dos_resource_sinks.qll
    lifecycle_facts.jsonl
    growth_effect_contract_graph.jsonl
    stage2_evidence_slices/
    stage2_summary.json
  stage3/
    taint_paths.jsonl
    growth_flow_proofs.jsonl
    no_path_candidates.jsonl
    path_slices/
    stage3_summary.json
  stage4/
    bound_candidates.jsonl
    config_facts.jsonl
    release_facts.jsonl
    path_bound_index.jsonl
    stage4_summary.json
  stage5/
    verdicts.jsonl
    obligation_matrices.jsonl
    resource_upper_bounds.jsonl
    evidence_report.json
    evidence_report.md
    stage5_summary.json
```

`run_manifest.json` 必须记录 `run_id`、`source_root`、`codeql_db`、source git commit 或 source hash、enabled stages、CodeQL CLI version、query pack version、LLM provider/model/config 摘要、ML model id/checksum、SMT solver version、budgets/timeouts 和 artifact schema version。

## CLI

主命令：

```bash
dosctl run \
  --source-root /path/to/project \
  --codeql-db /path/to/codeql-db \
  --out results/v2/runs \
  --run-id optional-id \
  --llm-provider openai \
  --llm-model model-name \
  --ml-model path/to/ranker.pkl \
  --smt-solver z3 \
  --budget default
```

阶段调试命令：

```bash
dosctl stage0 --run results/v2/runs/<run_id>
dosctl stage1 --run results/v2/runs/<run_id>
dosctl stage2 --run results/v2/runs/<run_id>
dosctl stage3 --run results/v2/runs/<run_id>
dosctl stage4 --run results/v2/runs/<run_id>
dosctl stage5 --run results/v2/runs/<run_id>
dosctl resume --run results/v2/runs/<run_id> --from stage3
```

阶段命令只用于开发和复现。普通用户入口是 `dosctl run`。

## Preflight

完整实现要求所有必需能力在 run 开始前可用：

- CodeQL CLI 可执行。
- CodeQL query pack 可解析、可编译。
- `source_root` 存在且可读。
- `codeql_db` 存在且是 Java/Kotlin CodeQL database。
- LLM provider 配置完整，认证可用，模型可调用。
- ML ranker 文件存在、checksum 可记录、模型可加载。
- SMT solver 可执行。
- schema registry 可加载。

任一必需能力缺失，run 进入 `preflight_failed`，不进入 Stage0，不写最终 verdict。

## Stage0: Project Profiling

输入：Java 项目源码、Maven/Gradle 元数据、配置文件、已有 CodeQL DB、构建脚本。

输出：`profile/project_profile.json`。

目的：

- 建立后续阶段共享上下文。
- 识别 Spring、Servlet、JAX-RS、Netty、gRPC、MQTT、WebSocket 等框架。
- 建立配置索引和 CodeQL DB 状态。
- 避免后续阶段做无界全仓搜索。

采用技术：Maven/Gradle 解析、YAML/properties/XML/Java config bounded parser、CodeQL database metadata/status check、bounded file scan。

完整要求：

- 必须输出框架依赖、协议候选、配置文件索引、CodeQL DB 可用性、source root 校验、query pack 可用性。
- `source_root` 或 `codeql_db` 不满足要求时，run 在 Step0 失败，不进入 Stage1。

## Stage1: E Extraction

输入：`project_profile.json`、项目源码、CodeQL DB、框架配置。

输出：

- `stage1/stage1_entries.jsonl`
- `stage1/stage1_source_models.yml`
- `stage1/dos_entry_sources.qll`
- `stage1/interface_slices/`
- `stage1/llm_source_claims.jsonl`
- `stage1/stage1_summary.json`

目的：找到攻击者可触达入口 E，提取攻击者可控 source 及协议维度，例如 `http.body_bytes`、`mqtt.topic`、`grpc.message_bytes`。

采用技术：CodeQL deterministic entry query、AST/annotation/type hierarchy 解析、bounded interface slice、LLM source claim normalization、CodeQL/AST replay verifier。

完整要求：

- 必须覆盖 HTTP、WebSocket、MQTT、gRPC 的设计范围。
- 必须构造 interface slices。
- 必须调用真实 LLM provider 做 source claim normalization。
- 必须执行 CodeQL/AST replay verifier。
- LLM 不可用、claim schema 校验器运行失败、replay verifier 组件运行失败，都视为 Stage1 失败。单条 claim 被 replay refute 是正常分析结果，但不能进入默认 Stage3 source。
- 不允许跳过 LLM 或只用 deterministic entries 继续。

## Stage2: G Detection

输入：项目源码、CodeQL DB、Stage1 hints、框架依赖、配置索引。

输出：

- `stage2/resource_sink_rules.jsonl`
- `stage2/dos_resource_sinks.qll`
- `stage2/lifecycle_facts.jsonl`
- `stage2/growth_effect_contract_graph.jsonl`
- `stage2/stage2_evidence_slices/`
- `stage2/stage2_summary.json`

目的：识别资源增长点 G，并把裸 sink 升级成 Resource Effect Contract。

```text
DemandExpr + GrowthEffect + LifecycleHint + Obligations
```

采用技术：CodeQL raw sink screening、四类增长族规则、framework/protocol adapter、ML filter/ranker、LLM helper summary、AST/CodeQL verifier、compact GECG。

四类增长族：

- `parser_materialization`
- `allocator_growth`
- `queue_growth`
- `container_growth`

完整要求：

- 必须执行 CodeQL raw sink screening。
- 必须调用真实 ML ranker 对 candidates 排序。
- 必须调用真实 LLM helper summary 处理未知 helper/wrapper。
- 必须执行 AST/CodeQL verifier。
- 必须构造 compact GECG。
- ML model 不存在、LLM 不可用、AST/CodeQL verifier 组件运行失败、GECG schema 不完整，均导致 Stage2 失败。单个 candidate 被 verifier refute 是正常分析结果，但不能进入默认 Stage3 sink。
- 不使用规则分数替代 ML。

## Stage3: E -> G Flow Proof

输入：Stage1 entries/source models、Stage2 sink rules/GECG、CodeQL DB。

输出：

- `stage3/taint_paths.jsonl`
- `stage3/growth_flow_proofs.jsonl`
- `stage3/no_path_candidates.jsonl`
- `stage3/path_slices/`
- `stage3/stage3_summary.json`

目的：证明 `Reach(E,G)` 和 `AttackerControls(E,G)`，判断攻击者控制的入口值能否流到资源需求表达式 `G.demand_expr`。

采用技术：CodeQL global taint tracking、CodeQL path query、custom source/sink model、additional flow steps、framework phase normalization、dimension propagation、path slicing。

完整要求：

- 必须加载 Stage1 source model 和 Stage2 sink model。
- 必须执行 CodeQL global taint tracking 和 path query。
- 必须支持 additional flow steps、framework phase normalization、dimension propagation、path slicing。
- Query timeout、query pack 错误、source/sink model 编译失败都视为 Stage3 失败。
- `no_path` 是正常分析结果，不是降级；只有 query 成功且模型完整时才能输出。

## Stage4: B Candidate Extraction

输入：Stage3 taint paths、Stage2 lifecycle/GECG facts、源码、CodeQL DB、配置文件。

输出：

- `stage4/bound_candidates.jsonl`
- `stage4/config_facts.jsonl`
- `stage4/release_facts.jsonl`
- `stage4/path_bound_index.jsonl`
- `stage4/stage4_summary.json`

目的：只抽取候选边界 B，记录位置、维度、作用域、失败语义、默认部署状态；不判断 B 是否有效。

采用技术：path-local CodeQL scan、config parser、owner-local capacity/release scan、filter/interceptor order extraction、failure semantics classifier、dimension normalization。

完整要求：

- 必须执行 path-local CodeQL scan。
- 必须解析配置文件、框架默认值、profile 条件。
- 必须执行 owner-local capacity/release scan。
- 必须抽取 filter/interceptor order、failure semantics、dimension normalization。
- 配置解析器、order extractor、failure classifier 任一关键组件失败，Stage4 失败。
- 不允许只输出部分 bound 继续。
- Stage4 永远不写 `effective=true/false`。

## Stage5: EffectiveB Proof

输入：Stage3 proven paths、Stage4 bound candidates、Stage2 lifecycle/GECG、项目配置、预算策略。

输出：

- `stage5/verdicts.jsonl`
- `stage5/obligation_matrices.jsonl`
- `stage5/resource_upper_bounds.jsonl`
- `stage5/evidence_report.json`
- `stage5/evidence_report.md`
- `stage5/stage5_summary.json`

目的：判断 `EffectiveB(E,G,path,B)` 是否成立。若 `Reach/AttackerControls/Growth` 成立且有效边界被反驳，则输出 `static_vulnerable`。

采用技术：CFG/ICFG dominance、framework phase order adapter、dimension lattice、failure semantics proof、lifecycle aggregation、linear resource algebra、SMT/Max-SMT 修正、counterfactual attacker check。

完整要求：

- 必须执行 dominance、phase order、dimension lattice、failure semantics、lifecycle aggregation、resource algebra、SMT/Max-SMT、counterfactual attacker check。
- Stage5 是唯一输出 `static_vulnerable/static_safe/static_unknown` 的阶段。
- `static_unknown` 是完整证明系统在证据不足或 obligation 不可判定时的合法静态结论。
- SMT solver 不可用、dimension lattice 缺失、obligation schema 不完整，Stage5 失败，不输出最终 verdict。

## Run 状态机

工具层状态只描述执行是否成功，不等同于安全结论：

```text
created
  -> preflight_passed
  -> profiling_ok
  -> stage1_ok
  -> stage2_ok
  -> stage3_ok
  -> stage4_ok
  -> stage5_ok
  -> completed
```

失败状态：

```text
preflight_failed
profiling_failed
stage1_failed
stage2_failed
stage3_failed
stage4_failed
stage5_failed
```

规则：

- `*_failed` 表示工具或依赖没有完成完整分析，例如 LLM API 不可用、ML model 缺失、CodeQL query 编译失败、SMT solver 不可用。
- `static_unknown` 表示 Stage5 完整执行后，证据或 obligation 不足以证明安全或漏洞。
- `stage5_failed` 不能写 `static_unknown`。
- 只有 `stage5_ok` 后才允许出现 `verdicts.jsonl`。

## Schema 管理

每个 JSON artifact 必须包含：

```json
{
  "schema_version": "v2.0",
  "run_id": "...",
  "stage": "stage1",
  "producer": "Stage1EntryExtractor",
  "created_at": "...",
  "records": []
}
```

JSONL 每条记录必须包含：

```json
{
  "schema_version": "v2.0",
  "run_id": "...",
  "record_id": "...",
  "provenance": {
    "stage": "stage2",
    "codeql_queries": [],
    "llm_claim_ids": [],
    "ml_model": null,
    "source_locations": []
  }
}
```

核心 schema：

- `ProjectProfile`
- `Stage1Entry`
- `LLMSourceClaim`
- `ResourceSinkRule`
- `LifecycleFact`
- `GrowthEffectContractGraph`
- `TaintPath`
- `GrowthFlowProof`
- `BoundCandidate`
- `ReleaseFact`
- `PathBoundIndex`
- `EffectiveBObligationMatrix`
- `ResourceUpperBound`
- `StaticVerdict`

## Stage5 Verdict 规则

Stage5 对每个 `(E, G, path)` case 输出：

```text
static_vulnerable
static_safe
static_unknown
```

判定：

```text
static_vulnerable
  iff Reach(E,G)=proven
   ∧ AttackerControls(E,G)=proven
   ∧ Growth(G)=proven
   ∧ EffectiveB(E,G,path,B)=refuted
```

```text
static_safe
  iff Reach(E,G)=proven
   ∧ AttackerControls(E,G)=proven
   ∧ Growth(G)=proven
   ∧ exists B. EffectiveB(E,G,path,B)=proven
   ∧ resource_upper_bound <= policy_budget
```

```text
static_unknown
  iff Stage5 completed
   ∧ at least one required obligation is unknown
   ∧ neither static_vulnerable nor static_safe can be proven
```

`EffectiveB` obligation matrix 固定为：

```text
B1 path dominance
B2 same dimension or sound conversion
B3 before growth
B4 hard failure / backpressure / evict-before-add
B5 lifecycle aggregation scope coverage
B6 default deployment enabled
B7 bounded cost under policy budget
```

`static_vulnerable` 必须能明确反驳关键边界，而不是“没找到边界就报漏洞”。例如：

- 找到的 B 都是 wrong dimension、after growth、log only 或 scope too narrow。
- 或 Stage4 完整抽取后 `candidate_bounds=[]`，同时 Stage5 能证明该类增长需要 hard bound，且配置、owner、path-local scan 已覆盖必需范围。

## Evidence Report

`evidence_report.json/md` 只汇总 Stage5 证明链：

- entry 和 source。
- growth sink 和 resource contract。
- taint path。
- lifecycle owner。
- candidate bounds。
- obligation matrix。
- resource upper bound。
- final static verdict。
- unknown 或 failure 的具体原因。

报告中禁止出现 dynamic confirmed、runtime reproduced、exploit confirmed 等表述。

## 测试分层

`schema tests`

- 每个 artifact schema 都有正反例 fixture。
- JSONL 每条记录都能独立 validate。
- schema version、run_id、producer、provenance 必填。

`stage unit tests`

- Stage0: Maven/Gradle、配置文件、CodeQL DB metadata fixture。
- Stage1: Spring/Servlet/JAX-RS/Netty/WebSocket/MQTT/gRPC entry fixture，验证 entries、source dimensions、LLM claim replay。
- Stage2: 四类增长族 fixture，验证 sink rule、lifecycle fact、GECG obligation。
- Stage3: source/sink model fixture，验证 taint path、dimension propagation、path slicing。
- Stage4: bound/config/release fixture，验证 path relation、failure semantics、scope。
- Stage5: obligation matrix fixture，验证三类 verdict。

`integration tests`

- 用仓库已有小型 framework/sample DB 跑完整 Step0-5。
- 用 taxonomy 中代表性样本构造最小 case fixture。
- 验证 artifact 文件完整、stage 顺序正确、Stage5 verdict 口径正确。

`preflight tests`

- CodeQL CLI/query pack 可用。
- LLM provider 配置可用。
- ML model 文件可加载。
- SMT solver 可用。
- 缺任一项时 run 失败，且不会写最终 verdict。

## 验收标准

第一版完整实现完成标准：

- `dosctl run --source-root ... --codeql-db ...` 能执行 Step0-5。
- 每个阶段都生成本设计列出的 artifact。
- LLM claim、ML rank、CodeQL query、SMT proof 都有 provenance。
- Stage5 是唯一 verdict producer。
- 能区分 run failure 与 `static_unknown`。
- 能对至少一组 HTTP/Spring parser materialization、MQTT container/queue growth、gRPC allocator growth、Servlet/Netty bound case 跑出完整 evidence report。
- 所有修改更新 `CHANGELOG.md`。
- 不运行动态 DoS 验证，不修改 `poc/` 归档内容。

## 实施顺序

完整实现仍按依赖顺序开发：

1. 建立 Python 包、CLI、run manifest、schema registry、artifact writer。
2. 实现 Step0 profiler 和 preflight。
3. 建立 CodeQL query pack 与 query executor。
4. 实现 Stage1 entries、LLM source claim、replay verifier。
5. 实现 Stage2 growth rules、ML ranker、LLM helper summary、GECG builder。
6. 实现 Stage3 taint/path proof。
7. 实现 Stage4 bound extraction。
8. 实现 Stage5 EffectiveB prover、SMT integration、evidence report。
9. 补齐 integration tests 和 changelog。

这里的实施顺序不是功能降级承诺。合入完成标准仍是完整 Step0-5 可用。

## 需要保护的边界

- 不能把 CodeQL、LLM、ML 设计成独立 pipeline worker。
- 不能让 Stage1/2/3/4 输出最终安全结论。
- 不能让 LLM verdict 进入最终判断。
- 不能用 ML ranker 决定 `static_vulnerable/static_safe/static_unknown`。
- 不能在工具失败时输出 `static_unknown`。
- 不能运行动态 DoS 验证。
- 不能修改 `poc/` 证据归档。
