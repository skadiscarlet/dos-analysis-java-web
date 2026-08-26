# PoC-33 21-Library Demo Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 v2 核心公式、三态结论和 fail-closed 边界的前提下，把 21 库 demo 从“1,277 条全是 `static_unknown`、独立队列动态 precision=0.237”修成能区分高价值正例、有效 Bound、默认不可达路径和明确 deferred gap 的可审计静态分析器。

**Architecture:** 保留固定顺序 `E -> G screening/slice/Contract/verify -> E→G -> B/lifecycle -> EffectiveB -> conclusion`。修复采用“benchmark 隔离的证据漏斗”：先固化离线评估，再收紧 production surface 与 candidate disposition，随后修复精确 E→G、扩充 Growth Contract 的 DoS 语义、补 Reach/Bound/lifecycle，最后在 report 层做不丢证书的 finding-family 聚合。普通扫描永不读取 PoC 或动态结果；动态产物只用于离线 post-hoc 验收。

**Tech Stack:** Python 3.11+、CodeQL Java、pytest/unittest、严格 JSON/JSONL artifact contracts、当前 RightAPI Codex Responses adapter（仅在显式授权的 immutable full canary 中使用）。

---

## 0. 证据结论

### 0.1 当前结果不是运行失败，而是分析漏斗失败

权威输入：

- formal batch：`results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233/`
- chain recall：`results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-recall-p0-final/`
- independent audit：`results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-static-positive-audit/`
- dynamic scoring：`results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-dynamic-validation/`

已确认数据：

| 层 | 当前结果 | 诊断 |
|---|---:|---|
| formal targets | 21/21 completed | runner、schema、provider cache/audit 不是主因 |
| raw Growth | 10,678 | 7,888 `container_growth`、2,216 `direct_allocation`，筛选噪声过大 |
| candidate disposition | 93 `verified_relevant` / 10,585 unresolved | 99.1% 未进入有效语义分析 |
| candidate links | 95 complete / 1,177 partial | association 是第一主瓶颈 |
| flow proofs | 44 proven / 1,234 partial | 其中 1,205 为 `FLOW_CODEQL_ROW_MISSING`，是第二主瓶颈 |
| verified Growth | 14 verified / 319 unresolved / 1 rejected | Contract 靠后且语义验证命中极低 |
| Reach | 69 unknown / 10 privileged | 0 条 ordinary-attacker reachability 被证明 |
| lifecycle candidates | 2 bounds / 6 linked evidence | 不能支撑 EffectiveB 判定 |
| conclusions | 1,277 `static_unknown` | partial link × entry variant 形成 unknown 交叉乘积 |
| chain recall | 25/33 full-chain | 2 association missing、2 entry only、4 growth only |
| post-hoc compression | 1,277 findings -> 189 resource clusters -> 49 queue | 核心 pipeline 未提供该能力 |
| dynamic score | TP=9、FP=29、blocked=11、precision=0.237 | reachability、Bound、failure mechanism 和 sink semantics 未进入 queue gate |

### 0.2 根因优先级

1. **P0：partial association 被展开成大量 finding。** `dosweb/production.py:900-915` 为每个 partial link 生成 unresolved Growth，`dosweb/production.py:1044-1064` 再为缺失 CodeQL flow 的每个 entry-growth pair 合成 `unmodeled` flow，最终 334 个 Growth 扩成 1,277 个 finding。
2. **P0：association 与 flow 不共享同一个可验证 path witness。** 1,036 条 link 仅有 `transitive_callgraph_association_requires_flow_witness`；正式 flow 又有 1,205 条 row missing，两个阶段互相等待、没有形成 proof-carrying edge。
3. **P0：Growth Contract 只回答“是否增长”，不回答“是否 DoS-relevant”。** 当前 7 字段 schema 没有 `growth_function`、`requests_to_pressure`、`retention_window`、`failure_mechanism`、`amplification_class`，无法系统拒绝 request-local array、server-controlled read、fixed-size object、single-session value 和 one-shot schedule。
4. **P0：Reach 与 EffectiveB 证据严重不足。** `entry_security_facts` 基本只有 source-local annotation；Spring Security chain、Servlet constraint、默认模块/profile、body/parser limits 没有完成 path-bound 建模。动态结果中的 15 个硬反例（4 effective bound、5 default unreachable、2 auth blocked、4 precondition blocked）没有在静态漏斗前部被分流。
5. **P1：报告没有 actionability 层。** 证书按 exact path 保留是正确的，但用户报告直接列出每个证书，缺少 stable family 聚合、优先级和排除原因。
6. **非根因：provider 与 batch retry。** 21/21 completed、172 个真实 provider records 均已通过完整性审计；继续换模型、提高 retry 或扩大 prompt 不能解决上述静态证据缺口。

## 1. 路线比较与选择

### 路线 A：对 21 库逐项目加 FQN/route 特判

- 优点：短期能把 33 条 truth 的表面 recall 拉高。
- 缺点：oracle leakage、无法迁移到 178/205 target、会违反“普通扫描不读 truth”和 generic framework modeling。
- 结论：拒绝。fixture 可使用真实形状，但 production query 不允许出现 target/repository/advisory ID 特判。

### 路线 B：保留所有 unknown，只在外部脚本排序

- 优点：实现风险低，当前 `audit_poc33_static_positive_queue.py` 已证明可做。
- 缺点：核心工具仍输出 1,277 条无差别 finding；Reach/Bound/flow 的错误不会被修复；外部启发式已产生 29 个 FP。
- 结论：仅保留为回归 oracle，不作为最终架构。

### 路线 C：修复 evidence funnel，并在 report 层聚合（推荐）

- 优点：直接修复公式中的 `Reach`、`AttackerControls`、`Growth`、`EffectiveB` 四个前提；与唯一设计基线一致；可迁移到后续大批次。
- 代价：需要 schema/tool 升版，必须重跑 immutable full batch，旧 2.5 产物不可 resume。
- 结论：采用。实现按 Task 1-10 顺序推进，任何阶段不得用“finding 数增加”替代 proof quality gate。

## 2. 验收口径

### 2.1 不可退让的正确性门槛

1. 普通 pipeline、query、prompt 和 verifier 不得读取 `poc/`、`binary_truth_collection`、dynamic case 或 benchmark label。
2. formal selected CodeQL query failure 继续终止 target；exploratory partial 产物继续不可 formal resume。
3. 只保留三种普通结论：`static_vulnerable`、`bounded_under_modeled_assumptions`、`static_unknown`。
4. admin/management/default-disabled/optional-absent 路径不得成为 `static_vulnerable`。
5. async Release capacity、reflection/custom dispatch 和超出批准深度的 path 继续 `static_unknown`，不得伪造 Release absence。
6. 每个 `static_vulnerable` 必须同时引用 complete Entry、verified Growth、verified flow、ordinary reachability、path-bound lifecycle coverage、无 effective Bound 证明。

### 2.2 21 库 demo gate

离线 evaluator 必须同时报告而不是混成一个“accuracy”：

- **Infrastructure:** 21/21 completed、formal/fail-closed、所有 selected queries 成功、0 diagnostic、私有 audit 0600。
- **Supported-chain recall:** PoC-33 中除 4 条明确 custom SMQTT dispatch deferred 外，其余 29/29 达到 `full_chain_finding`；4 条 SMQTT 必须保留 concrete gap + matched Growth + `static_unknown`，不得算 stage failure。
- **Ordinary-scope positive recall:** 当前 49-case 动态集里 6 个 default、非 admin confirmed cases，至少 5/6 进入 `static_vulnerable`；未达到时不启动 178-target full。
- **Hard-negative safety:** 4 个 `effective_bound_confirmed`、5 个 `default_not_reachable`、2 个 `auth_blocked`、4 个 `precondition_blocked`，15/15 不得输出 `static_vulnerable`。
- **Actionable precision:** 对既有评分规则 TP/(TP+FP) 报告 current 与 new 两套值；P0/P1 queue 必须从 0.237 提升到至少 0.50，且不得通过删除已命中的 ordinary-scope confirmed case达标。
- **Dedup:** exact certificate 全保留；`finding_families.jsonl` 对同一 `(target, registration identity, resource_id, reachability class, verdict)` 只发布一个 family，family 内 member ID 无重复。
- **No oracle leakage:** production source scan 结果为 0 target slug、0 record ID、0 finding ID 常量。

---

## Task 1: 固化离线 demo evaluator 与 case taxonomy

**Files:**
- Create: `dosweb/benchmark/poc33_demo.py`
- Create: `scripts/evaluate_poc33_demo.py`
- Create: `tests/test_poc33_demo_evaluator.py`
- Modify: `dosweb/benchmark/__init__.py`

- [ ] **Step 1: 写 evaluator 的 RED tests**

测试固定以下分类函数，不让 `not_confirmed` 被粗暴等同于静态 false positive：

```python
def classify_dynamic_case(result: Mapping[str, object]) -> str:
    """Return eligible_positive, hard_negative, weak_negative, or unscored."""

def build_demo_metrics(
    *,
    statuses: Sequence[Mapping[str, object]],
    truth_dispositions: Sequence[Mapping[str, object]],
    static_findings: Sequence[Mapping[str, object]],
    dynamic_results: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    """Build infrastructure, recall, hard-negative, queue, and dedup metrics."""
```

`eligible_positive` 必须同时满足 `verdict=confirmed`、default deployment、非 admin、非 optional、非 config-change；`hard_negative` 只接受 `effective_bound_confirmed|default_not_reachable|auth_blocked|precondition_blocked`；growth-only、probe semantics 和 tested-bounds 未复现归入 `weak_negative`。

- [ ] **Step 2: 运行 RED command**

```bash
python3 -m pytest -q tests/test_poc33_demo_evaluator.py
```

Expected: import error for `dosweb.benchmark.poc33_demo`.

- [ ] **Step 3: 实现只读 evaluator**

CLI 必须显式接收四个根目录，输出 `case_matrix.jsonl`、`metrics.json`、`REPORT.md`；禁止从 production output path 反向猜 truth path。

```bash
python3 scripts/evaluate_poc33_demo.py \
  --static-batch results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233 \
  --recall results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-recall-p0-final \
  --static-audit results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-static-positive-audit \
  --dynamic results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-dynamic-validation \
  --output /tmp/poc33-demo-baseline
```

Expected baseline: `targets=21`、`truth=33`、`eligible_positive=6`、`hard_negative=15`、`tp=9`、`fp=29`、`blocked=11`、`precision=0.236842`。

- [ ] **Step 4: 加 oracle-isolation test**

测试 import graph：`dosweb.production`、`dosweb.growth`、`dosweb.flows`、`dosweb.lifecycle`、`dosweb.conclude` 不得 import `dosweb.benchmark.poc33_demo`；evaluator 不得写回 static batch。

- [ ] **Step 5: 运行 GREEN command**

```bash
python3 -m pytest -q tests/test_poc33_demo_evaluator.py tests/test_truth_disposition.py tests/test_benchmark_truth.py
```

Expected: PASS; baseline metrics 与上述冻结数字一致。

- [ ] **Step 6: Commit**

```bash
git add dosweb/benchmark/poc33_demo.py dosweb/benchmark/__init__.py scripts/evaluate_poc33_demo.py tests/test_poc33_demo_evaluator.py
git commit -m "test: freeze poc33 demo evaluation gates"
```

## Task 2: 在唯一设计标准中批准 P0.2 修复并升版

**Files:**
- Modify: `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md`
- Modify: `dosweb/pipeline.py`
- Modify: `dosweb/artifacts/schemas.py`
- Modify: `dosweb/llm/schemas.py`
- Modify: `tests/test_artifact_contracts.py`
- Modify: `tests/test_pipeline_recovery.py`
- Modify: `tests/test_deepseek_client.py`

- [ ] **Step 1: 在原设计末尾新增 Section 20，禁止创建第二份竞争 spec**

Section 20 必须写清：

```text
20.1 candidate relevance is decided before finding publication
20.2 Growth Contract adds DoS relevance, failure mechanism, and pressure fields
20.3 partial evidence remains static_unknown only when candidate-relevant
20.4 certificates remain path-exact; reports may add deterministic families
20.5 ordinary scan remains truth-independent and static-only
20.6 schema/tool become 2.6/0.5.0; growth contract schema becomes v4
```

- [ ] **Step 2: 写版本失配 RED tests**

断言 `SCHEMA_VERSION == "2.6"`、`TOOL_VERSION == "0.5.0"`、`RESPONSE_SCHEMA_VERSION == "growth-contract-schema-v4"`，并断言 2.5 stage manifest 不可 resume。

- [ ] **Step 3: 更新版本与 implementation fingerprints**

所有 six-stage implementation version 使用 `production-v2.6-poc33-demo-repair-*`，避免复用旧 2.5 cache/stage artifact；保留 2.5 结果目录只读。

- [ ] **Step 4: 更新当前 artifact allowlist**

新增 conclude-stage `finding_families.jsonl`；后续 Task 8 定义其严格 schema。在 Task 8 完成前测试必须保持 RED，不能用空白 permissive schema 过门。

- [ ] **Step 5: 运行版本与 artifact tests**

```bash
python3 -m pytest -q tests/test_artifact_contracts.py tests/test_pipeline_recovery.py tests/test_deepseek_client.py
```

Expected: PASS; 2.5 fixtures 只能作为 immutable historical input，不能 formal resume。

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md dosweb/pipeline.py dosweb/artifacts/schemas.py dosweb/llm/schemas.py tests/test_artifact_contracts.py tests/test_pipeline_recovery.py tests/test_deepseek_client.py
git commit -m "docs: approve p0.2 evidence funnel repair"
```

## Task 3: 补齐 default deployment 与 ordinary-attacker Reach

**Files:**
- Create: `codeql/dosweb/Entries/EntrySecurity.ql`
- Create: `dosweb/codeql/pack/dosweb/Entries/EntrySecurity.ql`
- Create: `dosweb/reachability/extract.py`
- Modify: `dosweb/codeql/decoder.py`
- Modify: `dosweb/reachability/models.py`
- Modify: `dosweb/reachability/verify.py`
- Modify: `dosweb/production.py`
- Modify: `dosweb/configuration/extract.py`
- Modify: `tests/test_codeql_entry_queries.py`
- Modify: `tests/test_configuration_reachability.py`
- Modify: `tests/test_production.py`

- [ ] **Step 1: 写 security/deployment RED fixtures**

覆盖以下互斥结果：匿名 `permitAll`、普通 authenticated account、admin role、Servlet security constraint、Spring `SecurityFilterChain.requestMatchers(...).permitAll/hasRole`、disabled profile、optional bean、未知 dynamic matcher。未知 matcher 必须 partial，不允许 absence => public。

- [ ] **Step 2: 定义新的 ReachabilityDecision contract**

```python
@dataclass(frozen=True)
class ReachabilityDecision:
    entry_id: str
    auth_contract_id: str
    auth_context: Literal["unauthenticated", "low_privilege", "privileged", "unknown"]
    deployment_status: Literal["default_enabled", "default_disabled", "optional", "unknown"]
    status: Literal["ordinary_attacker_reachable", "not_entry_reachable", "unknown"]
    evidence_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
```

`status=ordinary_attacker_reachable` 需要 complete auth fact + `default_enabled`；privileged/default-disabled/optional 统一 `not_entry_reachable` 并保留不同 reason code。

- [ ] **Step 3: 实现 EntrySecurity CodeQL fact extraction**

查询只发布 source-backed annotation、Servlet constraint 和静态 `SecurityFilterChain` matcher；route、method、entry handler 必须能绑定到唯一 normalized Entry。复杂 matcher、custom voter、reflection、runtime DB policy 只发 partial fact。

- [ ] **Step 4: 把 security query 加入 formal entries**

formal entries 从 7 queries 升为 8 queries；六个 Entry family 仍由 `decode_bqrs_json("entries", ...)` 解码，interposition 与 security 分别由独立 decoder contract 解码，不能把 security row 混入 `normalize_entry_rows`。`EntrySecurity.ql` 失败必须终止。`_extract_entry_security_facts` 的文本扫描降级为 partial fallback，不再与 CodeQL complete fact竞争。

- [ ] **Step 5: 建模 default profile/module gate**

`dosweb/configuration/extract.py` 只从既有 allowlisted config roots 提取 `spring.profiles.active`、conditional property default、server/body limit 和 feature-enabled default；secret key 规则不变。不存在配置仍为 unknown。

- [ ] **Step 6: 运行 tests**

```bash
python3 -m pytest -q tests/test_configuration_reachability.py tests/test_production.py
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_codeql_entry_queries.py
```

Expected: complete public/low-priv/admin/default-disabled cases判定稳定，dynamic matcher 保持 unknown，query mirrors byte-identical。

- [ ] **Step 7: Commit**

```bash
git add codeql/dosweb/Entries/EntrySecurity.ql dosweb/codeql/pack/dosweb/Entries/EntrySecurity.ql dosweb/reachability dosweb/codeql/decoder.py dosweb/production.py dosweb/configuration/extract.py tests/test_codeql_entry_queries.py tests/test_configuration_reachability.py tests/test_production.py
git commit -m "feat: prove entry reachability and deployment gates"
```

## Task 4: 在 LLM 前执行 DoS-relevance candidate disposition

**Files:**
- Create: `dosweb/growth/relevance.py`
- Modify: `dosweb/growth/completeness.py`
- Modify: `dosweb/production.py`
- Modify: `codeql/dosweb/Growth/DirectAllocation.ql`
- Modify: `codeql/dosweb/Growth/ContainerGrowth.ql`
- Modify: `codeql/dosweb/Growth/AsyncWorkGrowth.ql`
- Modify: `codeql/dosweb/Growth/InputMaterialization.ql`
- Mirror: `dosweb/codeql/pack/dosweb/Growth/`
- Create: `tests/test_growth_relevance.py`
- Modify: `tests/test_codeql_growth_queries.py`
- Modify: `tests/test_production.py`

- [ ] **Step 1: 写 10 类 RED cases**

必须区分：attacker-sized array、server-sized array、request `String/byte[]` materialization、server file read、field-backed high-cardinality map、fixed-key map、single-session fixed attribute、looped queue submission、one-shot schedule、test/benchmark-only sink。

- [ ] **Step 2: 实现 deterministic precheck**

```python
@dataclass(frozen=True)
class RelevanceDecision:
    status: Literal["contract_eligible", "dos_relevant_partial", "rejected", "unresolved"]
    amplification_class: Literal[
        "superlinear", "large_single_request", "queue_instability",
        "concurrent_retention", "high_cardinality_retention",
        "low_amplification", "unknown",
    ]
    reason_codes: tuple[str, ...]

def evaluate_candidate_relevance(
    entry: EntryFact | None,
    candidate: GrowthCandidate,
    links: Sequence[CandidateEntryLink],
) -> RelevanceDecision:
    """Reject benign growth without using project or oracle identities."""
```

硬拒绝仅在静态证据 complete 时发生；否则用 `unresolved`。`dos_relevant_partial` 只允许 parser/read-all、attacker-sized direct allocation、field-backed retention、queue/connection state 这些高价值 family。

- [ ] **Step 3: 收紧 raw query semantics**

- `DirectAllocation.ql`: size expression 必须有 request-derived/handler-parameter data-flow witness或明确 partial note；常量/field/server metadata size 不得 complete。
- `ContainerGrowth.ql`: complete retention 必须 field-backed，key/value driver 与 escape scope 分开；fixed key、request-local collection 降级。
- `AsyncWorkGrowth.ql`: one-shot submit 标记 low amplification；只有 attacker loop/batch/submission-count witness 才标记 amplification complete。
- `InputMaterialization.ql`: 区分 request stream/read-all、Spring pre-handler body、server-side file/response materialization。

- [ ] **Step 4: 改 production funnel**

`rejected` 与 `not_entry_reachable` 只进入 `candidate_dispositions.jsonl`，不生成 unresolved Growth/flow/finding；`dos_relevant_partial` 最多绑定一个 canonical entry family；multi-entry ambiguity 只保留 disposition + gap，不做 cross product。

- [ ] **Step 5: 运行 tests**

```bash
python3 -m pytest -q tests/test_growth_relevance.py tests/test_growth_verification.py tests/test_production.py
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_codeql_growth_queries.py
```

Expected: 10 类 case 全部命中预期 disposition；direct/embedded queries byte-identical。

- [ ] **Step 6: Commit**

```bash
git add dosweb/growth/relevance.py dosweb/growth/completeness.py dosweb/production.py codeql/dosweb/Growth dosweb/codeql/pack/dosweb/Growth tests/test_growth_relevance.py tests/test_codeql_growth_queries.py tests/test_production.py
git commit -m "feat: reject non-dos growth before llm classification"
```

## Task 5: 让 association 与 formal flow 共用 proof-carrying path

**Files:**
- Create: `codeql/dosweb/Flows/EntryGrowthDomain.qll`
- Create: `dosweb/codeql/pack/dosweb/Flows/EntryGrowthDomain.qll`
- Modify: `codeql/dosweb/Flows/EntryToGrowthAssociations.ql`
- Modify: `codeql/dosweb/Flows/EntryToGrowth.ql`
- Mirror: `dosweb/codeql/pack/dosweb/Flows/`
- Modify: `dosweb/flows/models.py`
- Modify: `dosweb/flows/verify.py`
- Modify: `dosweb/production.py`
- Modify: `tests/test_flow_verification.py`
- Modify: `tests/test_codeql_lifecycle_queries.py`
- Modify: `tests/test_production.py`

- [ ] **Step 1: 写 cross-product RED test**

构造同一 resource 被两个 route alias 和一个无关 handler看到的 fixture；期望 1 个 canonical complete link、1 个 proven flow、0 synthetic unrelated flow。当前实现应因生成多条 partial flow 而失败。

- [ ] **Step 2: 抽出 shared CodeQL domain**

`EntryGrowthDomain.qll` 统一 framework source、exact growth anchor、demand role、bounded callable path 和 global data-flow node。association complete 的必要条件是同一个 domain 能产生 formal flow row；只有 callgraph 没有 data-flow 时必须 partial。

- [ ] **Step 3: 扩充 exact supported paths**

支持 same-handler、unique source helper depth≤3、unique interface implementation depth≤3、Servlet filter interposition、Armeria aggregation、Solr pre-handler form parser。reflection、multiple implementation、async processor table、custom dispatcher 继续 partial。

- [ ] **Step 4: 删除 synthetic partial cross product**

删除 `dosweb/production.py:1044-1064` 的“每个 partial link 自动造 flow”行为。缺 flow 的 candidate 写 stable `FLOW_CODEQL_ROW_MISSING` disposition；只有 query/source-backed evidence 含 exact source/sink 时才发布 partial `FlowProof`。

- [ ] **Step 5: 强化 verifier**

`verify_flow` 除 demand role 外还校验 source expression、sink argument/receiver、call path edge IDs、entry/growth source locations。proof evidence 不能只来自 Growth candidate evidence。

- [ ] **Step 6: 运行 tests**

```bash
python3 -m pytest -q tests/test_flow_verification.py tests/test_production.py
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_codeql_lifecycle_queries.py
```

Expected: cross-product test 从 RED 变 GREEN；all partial/deferred fixtures 仍不升级为 proven。

- [ ] **Step 7: Commit**

```bash
git add codeql/dosweb/Flows dosweb/codeql/pack/dosweb/Flows dosweb/flows dosweb/production.py tests/test_flow_verification.py tests/test_codeql_lifecycle_queries.py tests/test_production.py
git commit -m "feat: bind associations to verified entry growth paths"
```

## Task 6: 把 Growth Contract 从“增长分类”升级为“DoS Growth Contract”

**Files:**
- Modify: `dosweb/growth/models.py`
- Modify: `dosweb/growth/contracts.py`
- Modify: `dosweb/growth/verify.py`
- Modify: `dosweb/growth/evidence.py`
- Modify: `dosweb/llm/schemas.py`
- Modify: `dosweb/llm/prompts.py`
- Modify: `dosweb/llm/deepseek.py`
- Modify: `dosweb/llm/cache.py`
- Modify: `dosweb/artifacts/schemas.py`
- Modify: `tests/test_strict_growth_payload.py`
- Modify: `tests/test_growth_static_evidence.py`
- Modify: `tests/test_growth_verification.py`
- Modify: `tests/test_deepseek_client.py`

- [ ] **Step 1: 写 schema-v4 RED tests**

Growth Contract 必须精确包含以下字段，缺一或多一均 fail closed：

```python
@dataclass(frozen=True)
class GrowthContract:
    is_resource_growth: Literal["yes", "no", "unknown"]
    growth_kind: Literal["input_materialization", "direct_allocation", "container_growth", "async_work_growth", "unknown"]
    resource_dimension: Literal["entries", "bytes", "tasks", "connections", "objects", "unknown"]
    attacker_influence: tuple[AttackerInfluence, ...]
    resource_effect: Literal["materializes_bytes", "allocates_objects", "adds_entries", "enqueues_tasks", "opens_connections", "unknown"]
    attacker_variable: str
    attacker_value_space: Literal["stream", "unlimited", "large", "limited", "server_controlled", "unknown"]
    growth_unit: str
    growth_function: str
    amplification_class: Literal["superlinear", "large_single_request", "concurrent_retention", "queue_instability", "high_cardinality_retention", "low_amplification", "unknown"]
    requests_to_pressure: Literal["one", "few", "many", "implausible", "unknown"]
    concurrency_model: str
    retention_window: Literal["request", "session", "process", "until_release", "unknown"]
    failure_mechanism: Literal["heap_exhaustion", "gc_thrashing", "cpu_starvation", "thread_exhaustion", "connection_exhaustion", "queue_latency_collapse", "none", "unknown"]
    failure_signal: str
    required_static_evidence: tuple[str, ...]
    contract_status: Literal["dos_relevant", "growth_not_dos_relevant", "unknown"]
    rejection_reason: Literal["none", "request_local_bounded", "server_controlled", "fixed_cardinality", "effective_precondition", "low_amplification", "no_failure_mechanism", "unknown"]
    confidence: Literal["high", "medium", "low"]
```

所有自由字符串必须有 UTF-8 byte 上限；不能包含 source code 或 secret。

- [ ] **Step 2: 扩充 bounded static facts**

`adapt_growth_static_evidence` 发布 driver origin、value-space、escape/retention、loop multiplicity、field/key identity、materialization phase、known limit location。LLM 只能引用这些 fact aliases。

- [ ] **Step 3: 更新 prompt/cache identity**

prompt 明确“collection mutation alone is not DoS”；`growth_not_dos_relevant` 需要 rejection reason；unknown 不能伪装成 no。schema/prompt version 变化必须使旧 cache miss，私有 audit 保持 0600。

- [ ] **Step 4: 强化 deterministic verification**

只有 `contract_status=dos_relevant`、failure mechanism 非 none、requests-to-pressure 非 implausible、driver/retention/amplification citations 全部映射时 `VerifiedGrowthResult.status=verified`。LLM 的 prose 不能替代 static fact。

- [ ] **Step 5: 运行 tests**

```bash
python3 -m pytest -q \
  tests/test_strict_growth_payload.py \
  tests/test_growth_static_evidence.py \
  tests/test_growth_verification.py \
  tests/test_deepseek_client.py
```

Expected: malformed/extra/missing field、false citation、server-controlled、low-amplification 全部 fail closed 或 rejected；high-value fixtures verified。

- [ ] **Step 6: Commit**

```bash
git add dosweb/growth dosweb/llm dosweb/artifacts/schemas.py tests/test_strict_growth_payload.py tests/test_growth_static_evidence.py tests/test_growth_verification.py tests/test_deepseek_client.py
git commit -m "feat: require dos-relevant growth contracts"
```

## Task 7: 补齐 path-bound Guard/Bound/lifecycle facts

**Files:**
- Modify: `codeql/dosweb/Lifecycle/GuardCandidates.ql`
- Modify: `codeql/dosweb/Lifecycle/BoundCandidates.ql`
- Modify: `codeql/dosweb/Lifecycle/LifecycleCoverage.ql`
- Modify: `codeql/dosweb/Lifecycle/LifecycleSummary.ql`
- Mirror: `dosweb/codeql/pack/dosweb/Lifecycle/`
- Create: `dosweb/lifecycle/framework_limits.py`
- Modify: `dosweb/lifecycle/bounds.py`
- Modify: `dosweb/lifecycle/guards.py`
- Modify: `dosweb/production.py`
- Modify: `tests/test_lifecycle_bounds.py`
- Modify: `tests/test_lifecycle_guards.py`
- Modify: `tests/test_lifecycle_evidence.py`
- Modify: `tests/test_codeql_lifecycle_queries.py`

- [ ] **Step 1: 写四个已知 hard-negative RED fixtures**

至少覆盖 Jackson `StreamReadConstraints`、Netty `HttpObjectAggregator(maxContentLength)`、Spring/Servlet multipart/body limit、Solr `formdataUploadLimitInKB`。Bound 必须证明 default value、encoding/path applicability、pre-growth rejection 和 concurrency scope。

- [ ] **Step 2: 实现 framework limit normalization**

```python
def normalize_framework_limit(
    *,
    entry: EntryFact,
    growth: VerifiedGrowthResult,
    flow: VerifiedFlow,
    candidate: BoundCandidate,
    configuration: ModeledConfiguration,
) -> BoundDecision:
    """Return effective only for the exact path, driver, encoding, and default."""
```

limit=unknown、profile mismatch、post-growth check、different encoding、ignored result、fail-open 都不得 effective。

- [ ] **Step 3: 扩充 CodeQL candidate families**

查询发布 anchor file/line、resource dimension、request encoding、configured/default value provenance、pre-growth CFG relation；字符串相似或 global receiver 同名不发布 complete。

- [ ] **Step 4: 修复 coverage 语义**

`same_callable_modeled_domain_scanned` 只有在该 family 的 exact API/config domain 确实覆盖时才可 complete；当前“查询跑过但 domain 太窄”的情况改 partial，防止错误 absence。

- [ ] **Step 5: 保持 async Release deferred**

任何 worker、callback、timeout、TTL、ACK、consumer rate 只记录 potential async evidence并强制 `static_unknown`；本 Task 不实现 Assertion 3。

- [ ] **Step 6: 运行 tests**

```bash
python3 -m pytest -q tests/test_lifecycle_bounds.py tests/test_lifecycle_guards.py tests/test_lifecycle_evidence.py
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_codeql_lifecycle_queries.py
```

Expected: 四个 hard-negative fixture 为 effective Bound；mismatch/fail-open/async fixtures 保持 unknown/ineffective。

- [ ] **Step 7: Commit**

```bash
git add codeql/dosweb/Lifecycle dosweb/codeql/pack/dosweb/Lifecycle dosweb/lifecycle dosweb/production.py tests/test_lifecycle_bounds.py tests/test_lifecycle_guards.py tests/test_lifecycle_evidence.py tests/test_codeql_lifecycle_queries.py
git commit -m "feat: prove path bound framework limits"
```

## Task 8: 收紧 conclusion eligibility，并增加 finding family 报告

**Files:**
- Create: `dosweb/report/families.py`
- Modify: `dosweb/lifecycle/certificates.py`
- Modify: `dosweb/conclude/assertions.py`
- Modify: `dosweb/conclude/verdicts.py`
- Modify: `dosweb/report/summary.py`
- Modify: `dosweb/report/markdown.py`
- Modify: `dosweb/production.py`
- Modify: `dosweb/artifacts/schemas.py`
- Modify: `dosweb/batch/aggregate.py`
- Create: `tests/test_finding_families.py`
- Modify: `tests/test_assertions.py`
- Modify: `tests/test_certificates_and_reports.py`
- Modify: `tests/test_batch_aggregation.py`

- [ ] **Step 1: 写 family identity RED test**

route normalization aliases必须同 family；不同 auth class、不同 deployment gate、不同 resource、不同 verdict 不得合并。member certificate/finding 全部保留。

- [ ] **Step 2: 定义 strict family record**

```python
@dataclass(frozen=True)
class FindingFamily:
    family_id: str
    verdict: StaticVerdictName
    priority: Literal["P0", "P1", "P2", "inventory"]
    primary_finding_id: str
    member_finding_ids: tuple[str, ...]
    member_certificate_ids: tuple[str, ...]
    entry_ids: tuple[str, ...]
    growth_ids: tuple[str, ...]
    resource_id: str
    reachability_status: str
    amplification_class: str
    reason_codes: tuple[str, ...]
```

identity key 为 `(registration identity, resource_id, reachability_status, verdict)`；primary 按 evidence completeness、amplification、stable ID 确定，不能由 truth 决定。

- [ ] **Step 3: 收紧 conclusion input**

只有 `verified_relevant` 或 deterministic `dos_relevant_partial` disposition 能进入 conclude。rejected、not-entry-reachable 和 generic unresolved candidate 不生成 finding；coverage gap 仍保留在 dispositions/gaps。`dos_relevant_partial` 只能产出 family-level `static_unknown`，不能 `static_vulnerable`。

- [ ] **Step 4: 增加 positive proof gate**

`static_vulnerable` 发布前逐项断言 complete Entry、ordinary reach、verified Growth、verified flow、complete lifecycle families、no effective Guard/Bound、无 candidate-relevant gap；任一缺失转 `static_unknown` 并写具体 reason code。

- [ ] **Step 5: 更新 summary/report/aggregate**

`make_conclude_executor` 从 Entry、Growth、Reach、amplification 与 certificate 构造 family，并与 `static_findings.jsonl` 同阶段原子发布。报告首屏按 family 列 P0/P1/P2、amplification、Reach、Bound、missing evidence；exact certificate 表移动到 audit section。batch aggregate 新增 `aggregate_finding_families.jsonl`，私有 audit 仍不聚合。

- [ ] **Step 6: 运行 tests**

```bash
python3 -m pytest -q tests/test_finding_families.py tests/test_assertions.py tests/test_certificates_and_reports.py tests/test_batch_aggregation.py
```

Expected: family dedup 0 duplicate；certificate/finding/family references complete；三态词汇不变。

- [ ] **Step 7: Commit**

```bash
git add dosweb/report dosweb/lifecycle/certificates.py dosweb/conclude dosweb/production.py dosweb/artifacts/schemas.py dosweb/batch/aggregate.py tests/test_finding_families.py tests/test_assertions.py tests/test_certificates_and_reports.py tests/test_batch_aggregation.py
git commit -m "feat: publish actionable static finding families"
```

## Task 9: 修复 PoC-33 剩余 supported chain，保留 SMQTT deferred

**Files:**
- Modify: `codeql/dosweb/Flows/EntryGrowthDomain.qll`
- Modify: `codeql/dosweb/Flows/EntryToGrowthAssociations.ql`
- Modify: `codeql/dosweb/Flows/EntryToGrowth.ql`
- Modify: `codeql/dosweb/Entries/GrpcEntries.ql`
- Modify: `codeql/dosweb/Entries/JaxRsEntries.ql`
- Mirror: `dosweb/codeql/pack/dosweb/{Entries,Flows}/`
- Modify: `dosweb/entries/jaxrs_source.py`
- Modify: `tests/test_jaxrs_source_entries.py`
- Modify: `tests/test_codeql_entry_queries.py`
- Modify: `tests/test_codeql_lifecycle_queries.py`
- Modify: `tests/test_truth_disposition.py`

- [ ] **Step 1: 为 4 个 supported misses 建独立 RED fixture**

- HertzBeat：filter/interposition 到 `jobInstanceMap.computeIfAbsent` exact path。
- Grobid：JAX-RS multipart/stream handler 到 BAOS/read-all growth。
- Concord：source-backed JAX-RS resource identity与实际 route。
- SkyWalking：generated gRPC service unique registration；若 DB 缺编译单元，记录 `database_source_coverage_missing`，在 immutable 新 DB 中验证，不重写旧 DB。

- [ ] **Step 2: 每类只补 generic framework predicate**

production query 禁止出现 `hertzbeat|grobid|concord|skywalking`、repository slug、truth ID、固定业务 route。fixture class/package 名使用中性 `fixture.*`。

- [ ] **Step 3: SMQTT 保持 explicit deferred**

4 条 SMQTT custom Reactor dispatch 继续 `entry_gap + growth_only + static_unknown`；不得用 source order 或 protocol name 抬成 complete。验收把这 4 条从 supported 29 分开报告。

- [ ] **Step 4: 运行 fixture 与 oracle tests**

```bash
python3 -m pytest -q tests/test_jaxrs_source_entries.py tests/test_truth_disposition.py
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_codeql_entry_queries.py tests/test_codeql_lifecycle_queries.py
```

Expected: 4 supported shapes 完成 generic proof；SMQTT negative fixture 仍 partial。

- [ ] **Step 5: 扫描 oracle leakage**

```bash
rg -n 'hertzbeat|grobid|concord|skywalking|SMQTT-APP|GROBID-STATIC|HERTZBEAT-DOS' codeql/dosweb dosweb/codeql/pack dosweb --glob '!dosweb/benchmark/**'
```

Expected: no production target-specific predicate or oracle ID；允许的 documentation/test-only match必须从命令 scope 排除或显式审查。

- [ ] **Step 6: Commit**

```bash
git add codeql/dosweb/Entries codeql/dosweb/Flows dosweb/codeql/pack/dosweb/Entries dosweb/codeql/pack/dosweb/Flows dosweb/entries/jaxrs_source.py tests/test_jaxrs_source_entries.py tests/test_codeql_entry_queries.py tests/test_codeql_lifecycle_queries.py tests/test_truth_disposition.py
git commit -m "fix: close supported poc33 entry growth gaps"
```

## Task 10: 分层回归、immutable 21 库 canary 与 rollout gate

**Files:**
- Create: `scripts/run_poc33_demo_acceptance.py`
- Create: `tests/test_poc33_demo_acceptance.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: 写 acceptance driver RED test**

driver 只编排命令和校验产物，不执行动态 DoS。支持四层：`fast`、`codeql-fixtures`、`poc33-entries`、`poc33-real-provider-full`、`poc33-offline-eval`；它从 canonical 205 manifest 与 `poc/manifest.json` 生成 21-target immutable selection，不复用旧 plan。full 层缺显式授权或 key 时返回 `paused_by_provider_prerequisite`，不能 mock completed。

- [ ] **Step 2: 跑 fast suite**

```bash
python3 -m compileall -q dosweb scripts tests
python3 -m pytest -q
```

Expected: exit 0；默认无网络；记录 test count、skip count、wall time。若完整 suite 超过约定预算，先用 `pytest --durations=30` 找慢测，不能直接删测试或提高全局 timeout。

- [ ] **Step 3: 跑 real CodeQL fixtures**

```bash
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q \
  tests/test_codeql_entry_queries.py \
  tests/test_codeql_growth_queries.py \
  tests/test_codeql_lifecycle_queries.py \
  tests/test_production_e2e.py
```

Expected: exit 0；direct/embedded query mirror一致；partial/deferred negatives不升级。

- [ ] **Step 4: 先做无 provider 的 immutable entries canary**

新建唯一 run ID，禁止覆盖 `poc33-recall-v2-20260819_093248-entries`。要求 21/21 completed、8/8 selected queries、0 diagnostic、0 skipped。

```bash
RUN_ID="poc33-p02-$(date +%Y%m%d_%H%M%S)"
python3 scripts/run_poc33_demo_acceptance.py poc33-entries --run-id "$RUN_ID"
```

Expected: new immutable entries root path printed to stdout; exit 0 only after all 21 targets pass the entries gate。

- [ ] **Step 5: 经用户显式批准后做 real-provider full canary**

输出到新的 `results/java_web_dos_batch/${RUN_ID}-full/`；不 resume 2.5；max_workers=1；credential 只从环境或 owner-only `config/local_secrets.json` 读取。

```bash
python3 scripts/run_poc33_demo_acceptance.py poc33-real-provider-full \
  --run-id "$RUN_ID" \
  --allow-remote-llm \
  --max-workers 1
```

Expected: without explicit authorization/key => `paused_by_provider_prerequisite`; with both => 21 immutable targets completed or a fail-closed nonzero exit。

- [ ] **Step 6: 生成新 recall 与 offline score**

```bash
python3 scripts/generate_poc33_recall.py \
  --results-root "results/java_web_dos_batch/${RUN_ID}-full" \
  --output "results/java_web_dos_batch/${RUN_ID}-recall"

python3 scripts/evaluate_poc33_demo.py \
  --static-batch "results/java_web_dos_batch/${RUN_ID}-full" \
  --recall "results/java_web_dos_batch/${RUN_ID}-recall" \
  --dynamic results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-dynamic-validation \
  --output "results/java_web_dos_batch/${RUN_ID}-eval"
```

同一个 `RUN_ID` 必须写入 selection、batch plan、recall 和 evaluation manifest；执行者不得为四个路径改用不同 ID。新 evaluator 直接消费 formal `finding_families.jsonl`；`--static-audit` 只用于 Task 1 的 historical baseline 对照，不是新 run 的前置条件。

- [ ] **Step 7: 执行 gate audit**

必须满足 Section 2.2 全部门槛；任一失败都保持 178-target full paused，并输出按 `entry -> relevance -> association -> contract -> flow -> reach -> bound -> lifecycle -> conclude` 聚合的 blocker matrix。

- [ ] **Step 8: 更新 README/CHANGELOG**

只写实际命令和已生成证据；不得把 static conclusion 写成 dynamic confirmed，不得把 weak-negative 当安全证明。

- [ ] **Step 9: Commit**

```bash
git add scripts/run_poc33_demo_acceptance.py tests/test_poc33_demo_acceptance.py README.md CHANGELOG.md
git commit -m "test: gate poc33 demo repair rollout"
```

---

## 3. 执行顺序与停止条件

1. Task 1-2 先冻结 metric 与契约；没有 evaluator 不准改 query。
2. Task 3-5 优先解决 Reach 与 E→G，目标是消灭 unknown 交叉乘积，而不是增加 Contract 调用数。
3. Task 6-7 再提升 Growth/EffectiveB 语义；不允许 LLM `yes` 直接成为 verified。
4. Task 8 只做证书无损聚合；不能通过隐藏 hard negative 提高 precision。
5. Task 9 只修批准 support domain；SMQTT custom dispatch继续 deferred。
6. Task 10 gate 未通过时停止在 PoC-33，不启动 178/205 full。

## 4. 明确不做

- 不恢复 legacy verdict compatibility。
- 不把 v2 工具改成动态 DoS runner。
- 不修改 `../dos-analysis/`。
- 不覆盖或删除任何现有 `databases/`、`frameworks/`、`poc/`、`results/` 资产。
- 不用 target-specific FQN/route/advisory ID 修 production recall。
- 不在本阶段证明 async Release capacity、producer/consumer rate、TTL、reflection 或 arbitrary custom dispatch。
- 不以“static_vulnerable 数量”作为唯一 KPI；Reach、flow、Growth Contract、EffectiveB 和 negative gate必须逐项通过。
