# dos-analysis-web v2

Static analyzer for resource-exhaustion denial-of-service patterns in Java Web and adjacent Java network applications.

## Status

The Java Web DoS P0 analyzer now closes the approved P0 Gate 2/3 implementation scope: the default CLI connects the full CodeQL → bounded-slice RightAPI Codex Responses Growth/Auth Contracts → deterministic verification pipeline across all six resumable stages, with same-CFG/depth≤1 lifecycle evidence and attacker-controlled loop witnesses. Unsupported depth>1/custom/reflection/async-capacity semantics remain explicitly fail-closed as `static_unknown`. A new 205-target formal plan is published and ready for an independently authorized batch execution; no 205-target batch was started by the acceptance run.

Schema/tool 2.5/0.4.0 adds offline `modeled_configuration.jsonl`, `entry_security_facts.jsonl`, `configuration_coverage.json`, `entry_gap_facts.jsonl`, partial-first `entry_interposition_facts.jsonl`, candidate disposition/applicability records, path-bound lifecycle evidence/coverage, and private LLM audit artifacts. Use non-secret `analysis.modeled_defaults` or repeated `--modeled-default key=value` (CLI wins) for explicit modeled defaults. The Auth Contract interface is constrained: a model may cite only matching extracted security/config slice facts; unverifiable authentication remains `unknown`.

Ordinary development tests are network-free. They do not contact RightAPI or GitHub, start target services, send attack traffic, or perform dynamic DoS validation.

## Requirements and installation

Requirements:

- Python 3.11 or newer;
- a Java CodeQL database for the target;
- CodeQL CLI available as `codeql`, or selected with `--codeql-binary`;


Install the local package in a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

## Resource Lifecycle v1.2（实施中）

当前接口新增统一 `properties`：普通分析、源码评价与分片复算使用同一组性质，包含稳定 ID、资源/执行器身份、维度、scope/cut、上界、假设及证据引用。评价器不再从状态计数重建结论。源码树相同的重绑定不改变性质身份；缺失或歧义选择保留 unknown。

```bash
# 明确本地项目与方法/已有候选选择；清单不含 oracle。
python3 -m dosweb.cli resource-project --manifest project.json \
  --source-root /path/to/local/java --database /path/to/matching/database \
  --out /path/to/new/project-results

# 将已提取的事实按单元保存为有界分片，LLM off。
python3 -m dosweb.cli resource-analyze --facts /path/to/facts.json \
  --out /path/to/new/sharded-run --llm off --sharded
python3 -m dosweb.cli resource-replay --run /path/to/copied/sharded-run \
  --source-root /path/to/same/java-tree
# 无源码时只能检查存储完整性，不表示完成语义复算。
python3 -m dosweb.cli resource-replay --run /path/to/copied/sharded-run --integrity-only
```

项目清单版本为 `resource-project-v1.2`，字段为 `project_id/source_root/tree_hash/database/selection/dependency_scope/budgets/output`。`selection` 每条含 `input_id/kind/entry_callable`；method 保留全部资源，candidate 通过精确 `resource_family_id` 或 `allocation.program_point/instance_key` 绑定。已有 JSONL 候选可提供 `candidate_file/record_id`，缺少分配与源码身份时明确 mapping_missing。完整格式和验收报告仍在补齐。

仓库自包含多资源示例（6 个输入：方法、重复引用、导入候选、缺失方法、歧义及过期资源；不是独立项目）：

```bash
lifecycle_source="$PWD/tests/fixtures/resource_lifecycle_v1_2/src/main/java"
lifecycle_output="$PWD/.local-runs/v1.2/multi-demo"
mkdir -p "$lifecycle_output/classes"
codeql database create "$lifecycle_output/database" --language=java \
  --source-root="$lifecycle_source" \
  --command="javac -d '$lifecycle_output/classes' '$lifecycle_source/fixture/lifecyclev12/MultiResource.java'"
python3 -m dosweb.cli resource-project \
  --manifest tests/fixtures/resource_lifecycle_v1_2/project.json \
  --database "$lifecycle_output/database" --out "$lifecycle_output/project"
python3 -m dosweb.cli resource-replay --run "$lifecycle_output/project/analysis" \
  --source-root "$lifecycle_source"
```

源码和清单固定 hash 已包含在示例中；候选只提供已有 schema 的观测字段，不提供结论。清单中的路径按清单目录解析，CLI 相对路径按当前工作目录解析。混合输入项目预期为 partial，已映射的独立单元仍可复算，回放明确标为 selected。

状态与实际限制见 [v1.2 STATUS](docs/execution/lifecycle-v1.2/STATUS.md)。H1–H6 尚未完成；分片存储单测不能代替编译源码的规模与语义重放验收，独立模块输入尚待明确。`resource-project` 默认将完整证据写入 `out/analysis/`，可用 `resource-replay --run out/analysis --source-root ...` 复算，`project-results.json` 保留全部输入账本。

## Resource Lifecycle v1.1 历史工作流


Resource Lifecycle v1 是并行的离线状态分析链，不修改现有 P0 schema/tool `2.5/0.4.0`，也不把 lifecycle property 映射为 vulnerability 布尔量。干净 checkout 不需要 API key 或网络即可运行仓库内人工 IR、重放证据并重新生成固定评价：

v1.1 将真实 TaskBinding、逐步 callback CFG 与 caller continuation 放入同一主求解工作列表。`property_states` 是资源状态聚合，`property_derivations` 保存逐路径 state/trace；条件维度使用 `after_task_termination:<task_id>:<kind>` 等 scope。`termination_guaranteed=false` 表示未证明任务最终一定结束。已解析 ThreadPoolExecutor 的群体检查从转移推导 `q<=K`、`a<=W` 与 `q+a<=K+W`，覆盖任意有限次接纳；未知容量、未覆盖 writer 或出口缺口保持 unknown。G1–G8 已通过，限定 v1.1 迭代实现完成；报告见 `reports/lifecycle-v1.1/summary.md`，交接见 `docs/execution/lifecycle-v1.1/HANDOFF.md`。

从仓库根目录编译自包含 Java fixture 并运行真实源码固定输入对照（需要本地 CodeQL CLI、Java 与 jq）：

```bash
lifecycle_source="$PWD/tests/fixtures/resource_lifecycle_v1_1/src/main/java"
lifecycle_work=$(mktemp -d /tmp/lifecycle-v11-demo.XXXXXX)
mkdir "$lifecycle_work/classes"
codeql database create "$lifecycle_work/database" --language=java \
  --source-root="$lifecycle_source" \
  --command="javac -d '$lifecycle_work/classes' '$lifecycle_source/fixture/lifecyclev11/SourcePairs.java'"
python3 -m dosweb.cli resource-source-evaluate \
  --suite tests/fixtures/resource_lifecycle_v1_1/source-cases.json \
  --source-root "$lifecycle_source" --database "$lifecycle_work/database" \
  --out "$lifecycle_work/source-evaluation"
jq '.metrics' "$lifecycle_work/source-evaluation/source-evaluation.json"
jq '.units[].population_properties' "$lifecycle_work/source-evaluation/full-results.json"

# Extract one supported entry for a standalone analyze/replay run.
jq -n --arg database "$lifecycle_work/database" \
  '{schema_version:"1.1",mode:"codeql_database",database:$database,
    entry_methods:["java-callable-v1:fixture.lifecyclev11.SourcePairs.s5VerifiedCapacity(I)V"],
    budget:{max_steps:50000,max_updates_per_event:64,timeout_ms:15000}}' \
  > "$lifecycle_work/extraction.json"
python3 -m dosweb.cli resource-extract --manifest "$lifecycle_work/extraction.json" \
  --out "$lifecycle_work/extracted"
python3 -m dosweb.cli resource-analyze --facts "$lifecycle_work/extracted/facts.json" \
  --out "$lifecycle_work/analyzed" --llm off
python3 -m dosweb.cli resource-replay --run "$lifecycle_work/analyzed"
jq '.units[].population_properties' "$lifecycle_work/analyzed/lifecycle-results.json"

# Opt-in real Java/CodeQL acceptance, separate from contract-only tests.
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q \
  tests/test_resource_lifecycle_source_evaluation.py
```

该命令内部执行两条真实 CodeQL 查询与严格适配，保存 `facts.json`、full/关闭跨事件传播两模式结果及逐例 CSV。十二个变体来自同一个自包含 fixture，不代表十二个独立项目。声明切面上的静态性质不等于动态确认。

```bash
dos-web-analyzer resource-extract \
  --manifest tests/fixtures/resource_lifecycle/manual-manifest.json \
  --out /tmp/resource-lifecycle-facts

dos-web-analyzer resource-analyze \
  --facts /tmp/resource-lifecycle-facts/facts.json \
  --out /tmp/resource-lifecycle-run \
  --llm off

dos-web-analyzer resource-replay \
  --run /tmp/resource-lifecycle-run

dos-web-analyzer resource-evaluate \
  --suite tests/fixtures/resource_lifecycle/regression-suite.json \
  --out /tmp/resource-lifecycle-evaluation
```

对用户提供的离线 Java CodeQL database，使用以下严格 manifest 并传给 `resource-extract`；`database` 只在本地解析，不启动目标服务：

```json
{
  "schema_version": "1.1",
  "mode": "codeql_database",
  "database": "/absolute/path/to/offline-java-codeql-db",
  "entry_methods": [
    "java-callable-v1:com.example.Handler.handle()V"
  ],
  "budget": {"max_steps": 1024, "max_updates_per_event": 32, "timeout_ms": 5000}
}
```

`entry_methods` 是显式选择的 canonical callable id 数组；不指定外部入口时仍必须写空数组 `[]`，提取到的方法会作为 local method unit 分析。

录制摘要回放使用下面的独立命令；`--config` 指向严格的 recording JSON，而不是 provider 配置：

```bash
dos-web-analyzer resource-analyze \
  --facts /path/to/facts.json \
  --out /tmp/resource-lifecycle-recorded-run \
  --llm replay \
  --config /path/to/recording.json
```

`resource-analyze` 写出 `facts.snapshot.json`、`run-manifest.json`、`lifecycle-results.json`、`evidence.json` 和 `summary.md`。replay 模式还写出 owner-only `0600` 的 `llm-recording.private.json` 与 `llm-summaries.json`；它们可能包含局部源码摘要，不属于可公开评价报告。recording identity 绑定目标 unknown call、源码路径/行/列、caller 文件 SHA、完整 Java source snapshot SHA、canonical exact callee、model、contract 和 budget。当前 CodeQL adapter 尚未提取与 caller executable Effect 分离的 callee-summary witness，因此已验证的同位 `create`/`retain`/`dispatch` 仅保留为 audit/display，并以 `llm_proposed_effect_already_static` 阻止重复执行；它不会增强生产 solver。`drop`/`release` 永不作为消除或有界证明。`--llm live` 明确未实现并会拒绝运行。复用同一个 `--out` 时，工具只清理自身已知的 mode-specific/stale artifact 并保留未知用户文件；已知 artifact 若被替换成 symlink 或目录则在改写旧 run 前 fail closed。

`resource-replay` 校验 facts、完整 source snapshot、extractor、contract、tool、budget、私有 recording/summary 权限与 identity，并重新计算 result、evidence 和 `summary.md`。已跟踪评价报告位于 `reports/lifecycle-v1/`；状态语义和准确支持边界见 `docs/analysis-semantics.md` 与 `docs/limitations.md`。

Task4 状态/CLI/replay 回归和真实离线 Java 验收：

```bash
python3 -m pytest -q tests/test_resource_lifecycle_async_solver.py tests/test_resource_lifecycle_solver.py tests/test_resource_lifecycle_cli.py tests/test_resource_lifecycle_replay.py
DOSWEB_RUN_CODEQL_FIXTURES=1 DOSWEB_TASK4_FACTS_OUT=/tmp/lifecycle-task4-facts.json python3 -m pytest -q tests/test_resource_lifecycle_codeql.py::ResourceLifecycleCodeqlFixtureTests::test_v1_1_source_relations_are_extracted_from_java
DOSWEB_TASK4_CACHED_FACTS=/tmp/lifecycle-task4-facts.json python3 -m pytest -q tests/test_resource_lifecycle_async_solver.py -k cached
```


## Analysis model

```text
Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)
```

The recoverable P0 pipeline has six stages:

```text
entries -> growth -> flows -> lifecycle -> conclude -> report
```

Growth verification follows:

```text
CodeQL raw screening -> bounded slice -> LLM Growth Contract -> rule/static verification
```

The P0 framework scope is:

- Spring MVC registered controller routes;
- Servlet registered endpoints;
- Netty registered channel handlers;
- MQTT registered message callbacks.

Recognized but unresolved registration, entry, Growth, path, configuration, or lifecycle patterns are recorded as coverage gaps rather than guessed away. Flow sources use real Spring MVC, Servlet, Netty, and MQTT qualified APIs; direct/global data-flow witnesses are proven only for supported callable paths, while multi-wrapper, field/alias, reflection, custom dispatch, and unproven loop/fan-out paths remain explicit partial coverage.

## Assertions and verdicts

Assertion 1 matches only for verified direct input/allocation size demand, or container/async Growth with separately proven single-request amplification; one `put(key,value)` or `submit(task)` is not amplification.

Assertion 2 requires ordinary-attacker reachability, a proven repeatable E→G path, escaping attacker-controlled persistent key/value/submission/resource creation, and no effective Bound or synchronous Release. Unknown authentication, repeatability, amplification, association, or flow remains `static_unknown`.

Every raw Growth has an internal auditable disposition (`rejected`, `verified_relevant`, `not_entry_reachable`, or `unresolved`). Legacy source-order association is explicitly partial and never a complete call-graph proof.

P0 does not prove asynchronous Release. Growth and Auth LLM cache entries are private (`0600`), HMAC-authenticated, atomically published audit records: a fresh or cache-hit audit retains the bounded exact provider body, normalized prompt, parsed contract, settings and hashes without API keys, authorization headers, or environment data. Old cache formats are not reused.

P0 does not prove asynchronous Release. A potential asynchronous consumer, expiry mechanism, background cleanup, or completion path remains unresolved unless a supported synchronous reduction is established. Relevant unresolved evidence or incomplete coverage forces an unknown conclusion.

Static conclusions use exactly three values:

- `static_vulnerable`: at least one applicable assertion is statically matched, with no relevant unresolved evidence or coverage gap;
- `bounded_under_modeled_assumptions`: all applicable assertions are refuted by effective Guard, Bound, or synchronous Release evidence under modeled default configuration, with relevant entries and paths covered, explicit assumptions and stable reason codes recorded, and no candidate-relevant coverage gap; this is not an unconditional safety claim;
- `static_unknown`: the available static evidence or candidate-relevant coverage is insufficient for either of the preceding conclusions.

Provider confidence is audit metadata only and never changes a verdict.

## CLI

A complete production invocation has this shape:

```bash
# Optional override. Without this export, the gitignored 0600
# config/local_secrets.json is used.
export DEEPSEEK_API_KEY='set-in-your-shell-only'
dos-web-analyzer analyze \
  --database databases/applications/example-db \
  --output results/p0/example \
  --codeql-binary codeql \
  --allow-remote-llm \
  --source-checkout frameworks/applications/example-project
# The provenance flags below are optional metadata, not a gate:
#   --public-source-url https://github.com/example/project \
#   --source-commit-sha 0123456789abcdef0123456789abcdef01234567
```

The CLI also exposes individual production stage targets:

```text
entries
growth
flows
lifecycle
conclude
report
```

The same database/output/configuration options run through the selected stage; `analyze` targets the complete graph and `report` targets the final report stage. Add `--resume` to reuse a stage only when its schema, tool/database/query-pack/configuration fingerprint, upstream hashes, manifest, artifact hashes, and record counts all match exactly. The first mismatch invalidates that stage and every downstream stage.

Run `dos-web-analyzer --help` for the complete option list.

## Output layout

The normative production artifact contract is:

```text
OUTPUT/
├── run.json
├── coverage.json
├── entry_facts.jsonl
├── growth_candidates.jsonl
├── candidate_entry_links.jsonl
├── candidate_dispositions.jsonl
├── repeatability_decisions.jsonl
├── amplification_decisions.jsonl
├── growth_contracts.jsonl
├── verified_growth.jsonl
├── flow_proofs.jsonl
├── guard_candidates.jsonl
├── bound_candidates.jsonl
├── release_candidates.jsonl
├── lifecycle_evidence.jsonl
├── lifecycle_coverage.jsonl
├── lifecycle_results.jsonl
├── static_findings.jsonl
├── lifecycle_certificates.jsonl
├── summary.json
└── report.md
```

Lifecycle screening rows are never global counterexamples: `lifecycle_evidence.jsonl` binds each usable row to `(entry_id, growth_id, path_id)`. `lifecycle_coverage.jsonl` records a Guard/Bound/Release family decision for every relevant path; candidate-query zero rows never prove absence—only an explicit complete modeled-domain no-match witness may mean `absent`. Partial, unsupported, ambiguous CFG, string-only receiver, unproven alias, depth>1 wrapper, reflection, or custom dispatch evidence forces `static_unknown`.

The provider-neutral pipeline also maintains `.pipeline.lock` and per-stage metadata under `.stage-manifests/`. For each successful stage publication, its formal artifacts and stage manifest are installed before the corresponding `run.json` checkpoint is updated. Lifecycle certificates are the durable detailed conclusion records; static findings reference certificates, and summaries and Markdown reports must agree with those certificate verdicts.

## Verification

Run the default network-free suite:

```bash
python3 -m pytest -q
python3 -m compileall -q dosweb scripts
```

Real CodeQL fixture checks are explicit opt-ins and require a local CodeQL installation:

```bash
codeql pack install codeql
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q \
  tests/test_codeql_entry_queries.py \
  tests/test_codeql_growth_queries.py \
  tests/test_codeql_lifecycle_queries.py

# Full real production E2E: real fixture DB/queries + real RightAPI Codex Responses client with mock transport
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_production_e2e.py
```

Current accepted baseline: the network-free suite passes 656 tests plus 447 subtests (10 opt-in skips); real entry fixtures pass 4 tests plus 20 subtests, real growth fixtures pass 2 tests plus 12 subtests, and real lifecycle/flow fixtures pass 3 tests plus 53 subtests. The four production E2E scenarios remain covered across Spring, Servlet, Netty, and MQTT; an additional real HertzBeat scripted-provider canary now yields a certificate-backed `static_unknown` for the filter→`jobInstanceMap.computeIfAbsent` chain without promoting partial evidence.

These fixture checks create local test databases; the production E2E uses the real RightAPI Codex Responses client with a bounded in-memory mock transport and does not contact the provider. No default test requires `DEEPSEEK_API_KEY`.

The PoC-33 hardening entries wave at `results/java_web_dos_batch/poc33-recall-v2-20260819_093248-entries/` resolves all 21 truth repositories to unique source/database assets and completes formal extraction for 21/21 targets. Every target ran all seven required entry/interposition queries with zero skipped query or query diagnostic, and the current seven-artifact entries set is hash-manifested; see `AUDIT.json`. Zero complete entries for SkyWalking, Solr, SMQTT, Grobid, and Concord remains explicit gap/coverage evidence rather than a failed stage.

A separate authorized formal static canary was run against three archived dynamic true-positive seeds (Erupt, Citrus, DataCompare). All three completed with strict CodeQL policy, zero query diagnostics, replayable certificates/audits, no credential leak, and honest `static_unknown` results where auth/flow/lifecycle evidence remained incomplete. See `results/java_web_dos_batch/p0-true-positive-canary-20260817/{canary_manifest.json,canary_summary.json}`. Dynamic truth was used only for post-hoc target selection and never entered ordinary verdict derivation.

## Static and dynamic separation

The repository contains opt-in helpers for preparing and synchronizing an independently authorized, isolated dynamic-validation evidence scaffold. The static pipeline never invokes those helpers. A static verdict may be copied into the scaffold only as traceability metadata; it does not set or imply a dynamic status or verdict.

Dynamic validation is not required to produce a static conclusion and must never rewrite one. Historical dynamic evidence may be used as oracle or benchmark material, but ordinary v2 scans do not start services, execute probes, or claim dynamic confirmation.

## Preserved evidence and design authority

The rewrite preserves:

- `databases/`
- `frameworks/`
- `poc/`
- `results/static_hunts/`
- `results/application*`
- `results/java_web_dos_batch/`

`poc/` remains an unchanged evidence archive.

The sole implementation standard is:

- `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md`

Supporting research and paper documents provide context only:

- `docs/research/2026-07-14-lifecycle-centered-resource-dos-idea-design.md`
- `docs/paper/2026-07-15-lifecycle-static-analysis-paper-front-half.md`

## Canonical Java Web corpus and utilities

The active research corpus contains exactly **205 Java Web projects**, with source snapshots under `frameworks/applications/` and Java CodeQL databases under `databases/applications/`. It is the case-insensitive repository union of the preserved canonical Java Web 200 inventory and the PoC-29 repository set: 200 original targets plus 5 previously absent repositories.

- Active corpus definition: `docs/java-web-205-corpus.md`
- Active canonical inventory: `intel/applications/java_web_205_targets.json`
- Deterministic inventory generator: `scripts/generate_java_web_205_inventory.py`
- Preserved Java Web 200 definition/inventory: `docs/java-web-200-corpus.md` and `intel/applications/java_web_200_targets.json`

Earlier 50-project and 183-project inventories, the Java Web 200 generated run, and its repair outputs are historical evidence and do not define current corpus membership. Membership and readiness are distinct: the active dataset has 205 targets, and the 2026-08-16 repinned manifest reports 205 strictly ready source/database pairs and no incomplete databases.

The canonical batch layer validates all source fingerprints and CodeQL database source roots before publishing an immutable plan. Planning is local and network-free:

```bash
python scripts/run_java_web_dos_batch.py plan \
  --run-id java-web-205-plan \
  --output results/java_web_dos_batch/java-web-205-plan
```

`entries` runs only local Entry extraction with bounded concurrency and strips any inherited provider credential. Formal growth additionally writes 0600 private `llm_audit.private.jsonl` records for constrained Growth/Auth Contract calls (normalized prompt, bounded raw response, parsed response, non-secret settings, attestation and cache provenance); they are never included in reports. The current default provider is RightAPI Codex Responses at `https://rightapi.ai/grok/v1/` with model `grok-4.6` using the non-streaming Responses API; the owner-only API key remains in the gitignored `config/local_secrets.json` and must never be copied into reports or commits. The endpoint is non-streaming Responses only and sends the fixed provider User-Agent `pi-coding-agent`; HTTP 403 fails closed. Rotating that key rotates private-cache HMAC authentication, so provider runs must not resume an old cache across key changes; use a new immutable output directory. Remote calls require explicit `--allow-remote-llm` authorization, a non-empty provider API key, and a readable local source checkout; git-commit provenance (public URL, commit SHA, clean-checkout attestation) is optional metadata and no longer gates the remote path. Auth Contract decisions may cite only the entry security/configuration facts in their bounded slice, and unresolved authentication remains `unknown`. Formal analyzer stages fail closed when a selected CodeQL query fails. Only the explicit exploratory command `dos-web-analyzer entries --allow-partial-codeql` may record such a failure as a coverage gap; its manifest identity cannot be reused by formal analysis. `full` requires both `--allow-remote-llm` and a provider API key (from the `DEEPSEEK_API_KEY` environment variable or the gitignored local `config/local_secrets.json`, with the environment taking precedence). Use `full --plan-only` to construct and publish a non-executing full plan without a key or network; this still records only non-secret provider settings (`--model`, `--base-url`, `--timeout-seconds`, `--max-retries`, `--temperature`, `--cache-dir`, `--config`, and `--codeql-binary`) in the digest-bound plan. All 205 targets are queueable in full plans; a target whose source has only a `tree-sha256` fingerprint is executed against its local source tree, without requiring git-commit provenance. Per-target stage reuse remains governed by the production pipeline's strict manifests and hashes:

```bash
python scripts/run_java_web_dos_batch.py entries \
  --run-id java-web-205-entries \
  --output results/java_web_dos_batch/java-web-205-entries \
  --max-workers 3
```

These commands do not authorize service startup, attack traffic, or dynamic DoS validation. A real corpus run—especially `full` mode—is a separate operational action and is not part of the default test suite.

Development utilities:

- `scripts/generate_java_web_205_inventory.py` deterministically constructs the active 205 inventory from the preserved 200 inventory and PoC-29 repository set, recording strict readiness without rebuilding databases;
- `scripts/repair_java_web_200_inventory.py` remains the historical Java Web 200 replacement/database repair and publication utility;
- `scripts/run_java_web_dos_batch.py` creates or resumes canonical `plan`, local `entries`, and explicitly authorized `full` batches;
- `scripts/aggregate_java_web_dos_batch.py --format p0` validates and aggregates normative P0 batch artifacts; `--format historical` preserves old hunter archives. Omitting `--format` is permitted only when every manifest row is unambiguously historical and explicitly contains `hunter_output_dir`; ambiguous manifests are rejected rather than interpreted as historical;
- `scripts/prepare_dynamic_validation_output.py` and `scripts/sync_dynamic_validation_status.py` manage the separate opt-in dynamic evidence scaffold;
- `scripts/build_top50_codeql_dbs.py` and `scripts/reselect_java_web_dos_top50.py` reproduce superseded historical selection runs only.

Use `--help` on each script for its input and safety requirements. Dry-run modes do not clone, build, or publish target assets.

### 2026-08-17 P0 flow closure update

Formal flow extraction uses CodeQL `DataFlow::Global` and recognizes only real Spring MVC, Servlet, Netty, and MQTT qualified APIs as attacker sources. `EntryToGrowthAssociations.ql` emits semantic handler/growth associations; source-order is only partial triage evidence. A Netty `ChannelInitializer` is complete only when a supported `ServerBootstrap.childHandler` or `handler` installation is present. Missing association, flow, or coverage remains an explicit unknown chain.
