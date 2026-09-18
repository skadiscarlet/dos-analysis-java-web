# dos-analysis-web v2

Static analyzer for resource-exhaustion denial-of-service patterns in Java Web and adjacent Java network applications.

## Status

The Java Web DoS P0 analyzer now implements the approved P0.2 evidence-funnel repair: the default CLI connects CodeQL screening, bounded-slice APIBasis Responses Growth/Auth Contracts, proof-carrying Entry→Growth paths, path-bound Reach/lifecycle evidence, and certificate-preserving finding-family aggregation across all six resumable stages. Unsupported depth>1/custom/reflection/async-capacity semantics remain explicitly fail-closed as `static_unknown`.

Schema/tool 2.8/0.7.0 adds path-bound RC1 resource lifecycle decisions and replayable resource facts/results on top of open-world candidate maturation, `candidate_negative_proofs.jsonl`, Growth Contract v5, deterministic Auth derivation, assertion-scoped lifecycle proof gates, exact registration-coverage identities, and post-scan open-discovery evaluation. Raw candidates now mature into exactly `formal_eligible`, `gap_eligible`, `rejected`, or `inventory_unresolved`; a source-proven rejection carries a typed negative proof instead of disappearing. Use non-secret `analysis.modeled_defaults` or repeated `--modeled-default key=value` (CLI wins) for explicit modeled defaults. Model output is never a verdict by itself: every cited fact must belong to the bounded slice and pass deterministic verification.

The prior schema-2.6 PoC-33 full batch `poc33-p02-20260828_174800-full` completed 18/21 targets but produced only `static_unknown`; its independent root-cause audit is the repair input, not a passing acceptance result. A fresh immutable schema-2.8 21-target full and post-scan open-discovery evaluation are still required before rollout. The 178/205-target formal rollout remains paused pending that real-provider canary and final P0 review.

Ordinary development tests are network-free. They do not contact APIBasis or GitHub, start target services, send attack traffic, or perform dynamic DoS validation.

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

## Resource Lifecycle RC1

RC1 增量修复离线资源性质分析的源码归档范围、查询接入、方法身份、循环收敛和受支持包装调用异常返回。工程门槛与研究有效性分开记录，最终状态见 [RC1 summary](reports/lifecycle-rc1/summary.md) 与 [HANDOFF](docs/execution/lifecycle-rc1/HANDOFF.md)。固定九请求在本轮属于开发/回归集，没有独立漏洞 oracle。

```bash
# 仅复用已有冻结源码与 DB；输出必须为新目录，不下载或运行目标。
python3 scripts/evaluate_lifecycle_rc1.py \
  --asset-root /home/furina/new_tool/dos-analysis-web \
  --out .local-runs/rc1/reproduction-new
```

`--prior-run` 可指定已有 v1.2 冻结资产目录；默认从 asset root 的 v1.2 worktree 定位。该入口逐文件核对原源码/冻结镜像，恢复 common-core 全模块 158 文件，重新执行当前查询、求解、同事实消融和选中范围回放。失败返回非零并保留逐模块结果；`no_modeled_resource` 不计为已求解资源，也不发布上界零。所需本地资产与完整验收命令见 HANDOFF。

源码全树身份与 DB 实际归档分别保存；仅可证明完全由空白/注释组成的未归档文件可被接受，字节不一致或无法界定的声明缺失仍拒绝。生命周期查询专用传输最多 65,536 行，其他查询保持 4,096；原 JSON/字符串与单片读取限制保持有界。未知依赖、预算退出和模型缺口不转为安全结论。

## Resource Lifecycle v1.2（历史 partial 交付）

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

项目清单版本为 `resource-project-v1.2`，字段为 `project_id/source_root/tree_hash/database/selection/dependency_scope/budgets/output`。`selection` 每条含 `input_id/kind/entry_callable`；method 保留全部资源，candidate 通过精确 `resource_family_id` 或 `allocation.program_point/instance_key` 绑定。已有 JSONL 候选可提供 `candidate_file/record_id`，缺少分配与源码身份时明确 mapping_missing。可运行清单见 `tests/fixtures/resource_lifecycle_v1_2/project.json`，验收见 [汇总](reports/lifecycle-v1.2/summary.md)。

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

状态与实际限制见 [v1.2 STATUS](docs/execution/lifecycle-v1.2/STATUS.md)。H1/H2/H3/H5 已有验收证据，已纳入 3 个已有模块的 9 条请求，只有 1 个模块完成范围内分析与回放，H4 blocked；独立结果见 [模块评价](reports/lifecycle-v1.2/independent/summary.md)，最终门槛与重跑命令见 [HANDOFF](docs/execution/lifecycle-v1.2/HANDOFF.md)。完整传播在冻结十二例中为 10/12 匹配、5 unknown；消融 12/12、9 unknown。两项异常 CFG 缺口保留 unknown，未改 oracle。`resource-project` 默认将完整证据写入 `out/analysis/`，可用 `resource-replay --run out/analysis --source-root ...` 复算，`project-results.json` 保留全部输入账本。

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
- MQTT registered message callbacks;
- statically registered JAX-RS resources within the approved source-backed shapes;
- gRPC registered service handlers within the approved generated/forwarding shapes.

Recognized but unresolved registration, entry, Growth, path, configuration, or lifecycle patterns are recorded as coverage gaps rather than guessed away. Flow sources use real Spring MVC, Servlet, Netty, MQTT, JAX-RS, and gRPC qualified APIs; direct/global data-flow witnesses are proven only for supported callable paths, while multi-wrapper, field/alias, reflection, custom dispatch, and unproven loop/fan-out paths remain explicit partial coverage.

Every complete Entry persists an exact `registration_pattern_id` derived from the modeled `(framework, registration kind, raw coverage note)` binding. The ID participates in Entry identity, normalized rows with different exact patterns remain distinct, and `coverage.json.supported_patterns` contains these exact IDs rather than broad kinds. Every non-empty `CandidateCoverage.supported_patterns` item must likewise be an exact modeled ID for that framework, even for generic coverage; free-form `unsupported_patterns` remain valid gap notes. Conclude grants complete Entry coverage only when the current Entry's exact ID is present; another supported pattern of the same framework and registration kind cannot be inherited. A lifecycle certificate additionally requires exact registration-pattern, Entry, and Growth scope on its candidate coverage; generic or partially scoped coverage cannot sign a concrete certificate, while an optional path scope still follows the existing grouped-path semantics. Unknown complete notes and missing/mismatched exact IDs fail closed to `static_unknown`.

## Assertions and verdicts

Assertion 1 matches only for verified direct input/allocation size demand, or container/async Growth with separately proven single-request amplification; one `put(key,value)` or `submit(task)` is not amplification.

Assertion 2 requires ordinary-attacker reachability, a proven repeatable E→G path, escaping attacker-controlled persistent key/value/submission/resource creation, and no effective Bound or synchronous Release. Unknown authentication, repeatability, amplification, association, or flow remains `static_unknown`.

Every raw Growth has exactly one internal auditable maturation disposition: `formal_eligible`, `gap_eligible`, `rejected`, or `inventory_unresolved`. The raw `growth_candidates` domain and `candidate_dispositions` therefore form an exact bijection; P0 aggregation marks a target malformed for a missing, duplicate, or phantom disposition. It also reconciles every eligible and noneligible disposition/link: each link must reference one raw Growth and known Entry and be cited exactly once by that Growth's disposition; complete/partial associations require one matching canonical link, missing requires none, and ambiguous cannot carry a canonical or sole-link shape. `candidate_entry_links.link_id` is the stable `candidate_link` identifier of every field other than `link_id`; its nonempty `evidence_ids` and `reason_codes` are sorted unique strings. A status, evidence, or reason mutation therefore cannot retain an old link ID, even if a downstream disposition ID is recomputed. Orphan, cross-owned, wrong-Entry, wrong-status, or semantic-ID-tampered evidence is malformed rather than completed. Only the first two states may enter conclusion generation. `formal_eligible` requires complete local Growth and one complete canonical Entry association; `gap_eligible` preserves one candidate-relevant partial chain as `static_unknown`; rejected candidates require source-backed negative evidence. Legacy source-order association is explicitly partial and never a complete call-graph proof.

Growth and Auth LLM cache entries are private (`0600`), HMAC-authenticated, atomically published audit records: a fresh or cache-hit audit retains the bounded exact accepted provider body, accepted normalized prompt, parsed contract, settings and hashes without API keys, authorization headers, or environment data. Formal initial and correction requests use Responses `text.format.type=json_schema` with strict schemas: Growth requires exactly 17 keys and Auth exactly four, both forbid additional properties and constrain enum/alias/collection domains; the Growth wire schema is deliberately flat and contains no composition keywords. The prompt and local typed validation still bind all three status branches and reject every cross-field inconsistency before acceptance. Provider-side structured output is not trusted alone; the bounded unique-key parser, local schema/cross-field validation, fact-alias ownership, and raw-to-typed equality checks still run before acceptance. Responses scanning is deliberately layered rather than globally relaxed: before typed construction, the client bounded-parses the outer envelope, scans its decoded canonical strings with fixed credential rules, bounded-parses the inner assistant contract JSON, scans every decoded semantic value plus canonical key/value context with fixed credential and email/phone/SSN rules (plus Growth source-echo detection), and scans the provider request ID with fixed credential rules. Generic PII rules therefore do not apply to ordinary envelope metadata or phone-like/numeric request IDs. The single assistant message has an exact content-part allowlist: every part must be `type=output_text` with string `text`; `refusal`, a missing type, or any unknown/future part type is a permanent `LLM_RESPONSE_INVALID` protocol failure for that provider call, not a schema/sensitive safe-correction case, and produces no cache or audit even when a neighboring legal `output_text` contract exists. Only an explicitly bounded fresh target attempt may call the provider again after this nondeterministic envelope rejection; it never accepts or reuses the rejected response. Therefore harmless metadata can still enter the protected `0600` audit/cache, while real semantic PII remains a sensitive rejection. Outbound initial/correction requests always use only the fixed request credential scanner; response-side `extra_secret_patterns` never inspect prompts and execute only during immutable response-snapshot acceptance. Old cache formats are not reused. For either contract, a first strict-schema or sensitive-response rejection permits exactly one safe correction request; a second such rejection is terminal. A Growth correction reuses only the unchanged bounded slice and a deterministic statement of the exact 17-key, status, fact-alias, 16/32 evidence-limit, and local-binding invariants. An Auth correction reuses only the unchanged aliased security/configuration facts and restates the exact four-key contract: `auth_context`, JSON-array `evidence_ids`, JSON-array `assumptions` (both arrays may be empty), and `confidence=high|medium|low`. Neither correction includes the rejected body or provider request ID. The Growth prompt additionally publishes only locally binder-eligible `attacker_evidence_options` as aliased evidence/target pairs; provider output may return only an option's `evidence_id`, never the target, and an empty option set cannot support `dos_relevant`. Both provider and locally bound typed Growth models enforce `contract_status=dos_relevant => is_resource_growth=yes`; `no|unknown + dos_relevant` enters the sole safe correction path and a repeated violation is terminal without cache or audit. Auth remains strict, rejects duplicate JSON members through the bounded unique-key parser, and never normalizes scalar `evidence_ids` or `assumptions` into arrays. Provider `evidence_ids` must be exact aliases owned by the current bounded security slice; an unknown alias enters the sole safe correction path and a repeated unknown alias is terminal. Auth cache and single-flight identity additionally bind a non-forwarded SHA-256 digest over the original Entry plus ordered security/configuration semantic bindings, while replay revalidates every de-aliased evidence ID against the current security facts. Every rejected body remains absent from cache and audit as well as exception message, details, cause, context, and rejected-path traceback frame locals. The Growth prompt/schema identities are `growth-contract-v9`/`growth-contract-schema-v5`; Auth uses `auth-contract-v5`/`auth-contract-schema-v3`. Growth cache/HMAC format v14 and Auth cache/HMAC format v5 authenticate `accepted_prompt_variant=initial|correction`; Auth v5 also authenticates the bounded actual provider model, validates it against the requested model aliases, and preserves that alias in replay audit settings. Cache hits deterministically rebuild the exact prompt variant, so fresh and replayed audit prompts agree. Growth v13 and older records, plus Auth v4 and older records, are cold misses. The fixed `auth_cache_format=auth-contract-cache-v5` field participates in every DeepSeek Auth identity/key, so a real HMAC-valid v4 record remains untouched at its old path while the v5 call uses a different key and can publish normally; cold-cache handling never deletes or overwrites the old record. Auth reserves `auth-<identity>` cache capacity before the first provider call and holds that reservation through immutable publication. Auth/Growth cache publication exceptions or false returns clear all response/snapshot locals, are rebuilt as fixed unchained cache errors, and take precedence over caller-specific response policy. Growth's typed-contract and audit-payload read paths use one strict entry validator for the exact field set, key/format/response schema/identity, all component hashes, request audit, prompt variant, typed contract, entry hash, and HMAC; malformed signed state cannot be accepted by only one reader. Request-audit `provider` and `protocol` are bounded strings and must equal the corresponding cache-identity fields exactly. Provider envelope and cached raw-response limits are both 131072 UTF-8 bytes; an oversized direct cache write fails with a fixed controlled error. Production cache hits consume one immutable authenticated snapshot containing the typed contract, exact raw response, accepted prompt variant, and actual provider model, so contract/audit data cannot come from different file generations and model aliases survive replay. Separate Growth/Auth thread single-flight maps share policy-neutral snapshots rather than a caller-specific sensitive verdict. The live owner runs only the fixed universal decoded-envelope/decoded-semantic/request-ID layers before publication; caller-specific API-key and `extra_secret_patterns` checks execute over those same decoded layers during immutable-snapshot acceptance, after cache publication and flight completion, so strict-owner/lax-waiter order remains deterministic. Snapshot acceptance also bounded-parses and locally rebinds the raw contract under the current Growth slice/fact aliases or Auth security aliases, requires exact equality with the authenticated typed snapshot, and requires the raw actual model to equal the snapshot model before audit. Every owner/waiter also rechecks its own API key against the accepted decoded response layers and in-memory provider request ID. A custom-policy rejection therefore cannot start correction, overwrite the finished flight, delete the cache, or force a lax waiter back to the provider; a fresh accepting owner audit has `cache_hit=false`, while waiter/cache replay has `cache_hit=true`. The disk cache continues to omit plaintext provider request IDs; replay uses an empty request-ID value. A disk-cache hit or in-memory waiter that rejects an immutable snapshot under its own policy clears its local references and raises one fixed unchained policy error without returning to the provider or mutating the shared snapshot needed by other waiters. Auth verification always re-evaluates all Auth facts for the current Entry in the bounded security slice; conflicting complete semantic contexts remain `unknown` even if the provider selectively cites one side. Any partial/unsupported non-deployment fact in that Entry/slice is an Auth coverage gap, disables local derivation, and forces `REACH_AUTH_COVERAGE_PARTIAL` plus unknown Auth/Reach regardless of selective citation. Only exact Auth `(kind,value)` pairs participate, so value-shaped dependency/coverage facts cannot forge reachability. Deployment gates, including partial deployment coverage, remain independent and restricted to the same Entry and slice. Duplicate effective configuration values are folded only when type and value both agree; conflict makes that key unknown. Auth/Reach evidence remains deterministically bounded to 32 IDs: the smallest Auth-gap fact, semantic Auth-context representatives, and deployment-status representatives are reserved before remaining provider citations, so high-cardinality facts cannot overflow the artifact or hide a conflict/gap.

EntrySecurity binding is route-semantic and fail-closed: a concrete static matcher such as `/api/**` binds every matching Entry, while a concrete zero-match never falls back to a same-named handler. Exact handler identity is used only when the route is absent/non-concrete and uniquely identifies one Entry; source proximity is never used. Auth annotations use an exact qualified-name allowlist for `javax`/`jakarta` PermitAll/RolesAllowed, Spring PreAuthorize/Secured, and Vaadin AnonymousAllowed; a project-local same-simple-name annotation is ignored. Complete privileged evidence is limited to exact administrative roles/expressions (`ADMIN`, `ROLE_ADMIN`, exact admin `hasRole`/`hasAuthority` forms). `ROLE_USER`, other or mixed roles, and other expressions remain partial unknown. Bean/class/expression/generic conditional annotations publish only partial `optional` presence evidence. Only one simple positive `@Profile` name can be complete; negated or compound profile expressions remain partial and are also rejected by the deployment resolver. `@ConditionalOnProperty` complete evidence uses the canonical prefixed key (`prefix.name`, without duplicating an existing trailing dot), requires one static name/non-empty static `havingValue`/static prefix and `matchIfMissing=false`, and never falls back to an unprefixed configuration key; unresolved or absence-enabled forms remain partial. An explicit partial deployment fact suppresses synthetic `default_enabled`, so unresolved conditions keep Reach unknown. Netty source-switch associations use an exact modeled route when the bounded call path carries one; route aliases collapse to the base pipeline registration only when handler, installation site, security, attacker inputs, materialization phase, and link status are all identical. Generic duplicate-registration canonicalization applies the same identity boundary: a shared application-level registration site does not collapse distinct JAX-RS handlers or HTTP methods. Flow normalization consumes the authenticated Growth-stage canonical disposition/link mapping: a route-qualified link retains that exact alias, while a route-free handler-base link emits only the base pair; it never re-expands a shared source location into sibling aliases. Every Flow upstream JSONL is strict-schema validated before use. The raw `growth_candidates` domain and `candidate_dispositions` are an exact bijection: missing and duplicate dispositions fail as invalid upstream artifacts, while a phantom disposition fails as a dangling fact reference. Every link and disposition, including inventory/rejected records, must reference that complete domain; complete/partial associations must match their sole link status, missing/ambiguous shapes remain non-canonical, and every formal/gap disposition must additionally own a retained Growth result. The Flow loader requires exactly one `verified_growth` owner per `growth_id` and rejects every duplicate normalized `path_id` before map insertion, including byte-identical rows, so CodeQL row order cannot choose provenance. Direct allocation enumerates every explicit array dimension, and the shared Growth/Flow loop domain accepts a complete multiplicity witness only for exact `for (int i = 0; i < directAttackerIntParameter; i++|++i)` loops whose induction and bound parameters are not rewritten. Container and async Growth must be the whole expression of the sole top-level `ExprStmt`; Direct allocation additionally permits only a simple `=` whose RHS is exactly the allocation. Return/throw, argument or conditional subexpressions, compound/derived assignments, server-capped or compound conditions, conditional/multi-statement bodies, and nested lambda/anonymous-callable growth remain partial/unmodeled. The proof-carrying Flow domain carries every explicit array-size demand, Direct/request-local-container `iteration_count`, and async `submission_count`, so only real matching Growth/Association/Flow rows can mature a complete link. A complete fixed/server-metadata negative still requires every normalized driver to be server-controlled and no multiplicity obligation. Every structurally owned database descriptor and every runner-local descriptor-owner set is released by a caller-local lexical `try/finally` pair over persistent ownership state, so interruption at the first helper call boundary still reaches the second call without retrying a consumed fd number. Factory-exception and final-cleanup releases of a transferred long-lived snapshot-parent binding use the same lexical pair; factory parent-release coverage is established before any remaining snapshot-root release retry, private-tree cleanup is nested in that retry's `finally`, and `cleanup_state.closed` is committed only after these cleanup/release layers exist and the parent release transaction is consumed. The production query workspace now retains one persistent reverse-order owner for its ancestry/output/workspace/results descriptor chain; `close()`, family finalizers, and Entry finalizers duplicate the same cleanup call at their lexical boundary, while consumed transactions prevent ABA fd-number reclose after an actual close or a second-call interruption. The execution-snapshot success action only transfers the parent owner and returns its binding: `factory_succeeded` remains false through helper restoration and the exception handler, and is committed only after the deferred call fully returns. The flag commit and following `RETURN_VALUE` are not treated as atomic. Before owner callback or transfer, the factory attaches a non-cyclic `weakref.finalize` to the owned `DatabaseInfo`; its callback captures only the persistent binding. An opcode/SIGINT escape after the commit but before return is therefore drained by GC when no external owner retained the object, or by the production owner/finalizer lexical pair when the owner callback retained it. Normal explicit cleanup consumes the same transaction, so the later GC finalizer is a no-op and cannot reclose an ABA-reused fd number. Standalone cleanup uses a public paired wrapper around an internal core whose nested attempts directly reacquire a schema-valid binding from the input. `dis.Bytecode` shows the public wrapper's first traceable `NOP` at offset 2 before its exception-table start at offset 4, so call-entry must-reach is a caller responsibility; the production finalizer supplies that caller-local pair and clears `owned_database`/`validated_database` only after both calls. Fixture classes cache-root and classes-leaf opens also use structural owners and preallocated transactions; before `_open_pinned_classes_directory` returns, a deferred transfer registers the pinned object in a caller-owned slot, and `_build_database` drains that slot through paired must-reach cleanup even when the callee return event prevents caller assignment. Production fingerprints are entries-v17, growth-v32, flows-v21, lifecycle-v14, and conclude-v5. Formal resume cannot reuse entries before v17, growth v5-v31, flows v3-v20, lifecycle before v14, or conclude before v5.

P0 does not prove asynchronous Release. A potential asynchronous consumer, expiry mechanism, background cleanup, or completion path remains unresolved unless a supported synchronous reduction is established. Relevant unresolved evidence or incomplete coverage forces an unknown conclusion.

Static conclusions use exactly three values:

- `static_vulnerable`: at least one applicable assertion is statically matched, with no relevant unresolved evidence or coverage gap;
- `bounded_under_modeled_assumptions`: all applicable assertions are refuted by effective Guard, Bound, or synchronous Release evidence under modeled default configuration, with relevant entries and paths covered, explicit assumptions and stable reason codes recorded, and no candidate-relevant coverage gap; this is not an unconditional safety claim;
- `static_unknown`: the available static evidence or candidate-relevant coverage is insufficient for either of the preceding conclusions.

Before either `static_vulnerable` or `bounded_under_modeled_assumptions` is published, the proof gate requires complete Entry coverage, ordinary-attacker Reach, verified Growth, proven flow, complete lifecycle coverage for every applicable assertion, and no candidate-relevant gap. Missing any obligation downgrades either determinate conclusion to `static_unknown` and records every exact `VERDICT_*` missing-reason code; an already unknown conclusion stays unknown and receives the same audit reasons. When a modeled-bounded result is actually downgraded, the contradictory `STATIC_EVIDENCE_COVERAGE_COMPLETE` assumption is removed, while evidence-backed `MODELED_DEFAULT_CONFIGURATION` and modeled configuration references remain available; an originally unknown result does not acquire either assumption. There is no bounded-result bypass. `not_entry_reachable` candidates are rejected earlier during maturation with a typed negative proof rather than retained through this gate.

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

### Private CodeQL execution database

Production never executes `codeql query run` against the canonical database.
Under the locked output root, each attempt first atomically writes
`status=running`, then preflight creates one hidden owner-only
`.codeql-execution-*` database per target pipeline and shares it across all
selected queries.  The clone is Linux reflink-only (`FICLONE`): unsupported
reflink, quota/capacity exhaustion, unsafe symlink/special-file trees, identity
races, or cleanup failure abort with the fixed
`CODEQL_EXECUTION_SNAPSHOT_FAILED` error; there is no full-copy fallback.
Preflight failure atomically persists `failed` for the incremented attempt;
`BaseException` during a partial clone still cleans up, and a cleanup failure
takes precedence over the original failure.

The canonical `path`, source root, and fingerprint remain the sole inputs to
stage fingerprints, batch identity, artifacts, reports, and `--resume`.
CodeQL may mutate the private clone.  Canonical/private state is rechecked
through hash/fsync/replace commit checkpoints.  An output directory equal to
or below the execution DB is rejected before subprocess execution, so no
`QueryResult` path can contain the random snapshot.  Drift after replacement
first no-replace-renames the normal generation to hidden rollback quarantine
and fsyncs `.generations`; cleanup failure can leave hidden state but never a
normal published generation.  Finalization revalidates the canonical
database and removes the clone before writing `status=completed`, including
all-reused resume runs and failed stages.  Cleanup uses bounded streaming
`os.scandir(fd)`, same-parent
`renameat2(RENAME_NOREPLACE)` quarantine, and fd-relative inode/link-count
verification.  There is no overwriting rename fallback.  If the original
snapshot name is recreated, the replacement is preserved but cleanup and the
Pipeline fail closed.  A cleanup error is persisted and raised ahead of the original
stage error, which remains its cause.  Random private paths are redacted
from diagnostics and never enter formal output.  A fresh resume may therefore
use a different private path without invalidating reusable stages.

Runner-owned `.generations`, query snapshots, and CodeQL BQRS/decoded regular
outputs are hardened only after parent-dirfd pinning and `O_NOFOLLOW` open.
Type, current uid, link count, inode, mode, and bounded size are checked before
fd-relative `fchmod`, then the fd, parent-relative name, lexical name, and
parent binding are revalidated. A same-uid lexical substitute is therefore
never chmoded merely because it occupies the expected pathname. `run_query`
probes the one-shot close capability before it creates a query-source or output
descriptor. Query-source, snapshot-root, execution-snapshot-parent, pending,
generation, BQRS, decoded-output, and publication-anchor descriptors are owned
by preallocated close-once transactions inside deferred-interrupt cleanup.
The execution-snapshot factory reserves a structural owner slot before opening
either its retained parent or snapshot-root descriptor, and defers trace,
profile, and `SIGINT` delivery across the `os.open` return-to-slot boundary.
It performs no pre-owner `_tree_root_identity(output)` open: the retained parent
fd is authoritative and is compared with the current no-follow lexical `lstat`
binding before stale cleanup reuses that same fd.
Only a completed binding may consume the parent slot; every earlier exception
releases the still-owned descriptor exactly once. Release reads the descriptor
without removing its owner slot, commits the persistent close transaction, and
only then validates and clears the slot in another deferred-interrupt window.
If slot-clear setup/restoration escapes, outer cleanup observes the committed
transaction and clears ownership without closing a reused fd number.
This ownership rule now covers every explicit descriptor acquisition/release in
`dosweb/codeql/database.py`: metadata reads, root identity, recursive safe-tree
validation, private-binding checks, reflink source/destination walks, and stale/
private cleanup all preallocate per-fd transactions and use the shared owned
open/release primitives. The module contains no direct `os.open` or `os.close`;
the underlying syscall boundary remains centralized in `dosweb/filesystem.py`.
An actual-close-then-exception is committed without retrying the reused fd
number; concurrent/repeated execution-database cleanup consumes the retained
parent transaction exactly once. Any ownership, release, or rebind failure is
fail-closed as `CODEQL_QUERY_FAILED` or
`CODEQL_EXECUTION_SNAPSHOT_FAILED` and cannot publish a stage artifact.

Run `dos-web-analyzer --help` for the complete option list.

## Output layout

The normative production artifact contract is:

```text
OUTPUT/
├── run.json
├── coverage.json
├── entry_facts.jsonl
├── entry_gap_facts.jsonl
├── entry_interposition_facts.jsonl
├── modeled_configuration.jsonl
├── configuration_coverage.json
├── descriptor_coverage.json
├── entry_security_facts.jsonl
├── growth_candidates.jsonl
├── candidate_entry_links.jsonl
├── candidate_negative_proofs.jsonl
├── candidate_dispositions.jsonl
├── repeatability_decisions.jsonl
├── amplification_decisions.jsonl
├── growth_contracts.jsonl
├── auth_contracts.jsonl
├── reachability_decisions.jsonl
├── verified_growth.jsonl
├── flow_proofs.jsonl
├── guard_candidates.jsonl
├── bound_candidates.jsonl
├── release_candidates.jsonl
├── lifecycle_summaries.jsonl
├── lifecycle_evidence.jsonl
├── lifecycle_coverage.jsonl
├── lifecycle_results.jsonl
├── static_findings.jsonl
├── finding_families.jsonl
├── lifecycle_certificates.jsonl
├── llm_audit.private.jsonl
├── summary.json
└── report.md
```

Lifecycle screening rows are never global counterexamples: `lifecycle_evidence.jsonl` binds each usable row to `(entry_id, growth_id, path_id)`. `lifecycle_coverage.jsonl` records a Guard/Bound/Release family decision for every relevant path; candidate-query zero rows never prove absence—only an explicit complete modeled-domain no-match witness may mean `absent`. Partial, unsupported, ambiguous CFG, string-only receiver, unproven alias, depth>1 wrapper, reflection, or custom dispatch evidence forces `static_unknown`.

The provider-neutral pipeline also maintains `.pipeline.lock` and per-stage metadata under `.stage-manifests/`. For each successful stage publication, its formal artifacts and stage manifest are installed before the corresponding `run.json` checkpoint is updated. Lifecycle certificates are the durable detailed conclusion records; static findings reference certificates, and summaries and Markdown reports must agree with those certificate verdicts.

Novelty is deliberately absent from production artifacts. After a formal batch
has been aggregated and benchmark seeds have been matched, classify the complete
scan inventory without converting unmatched PoC seeds into false positives:

```bash
python3 scripts/evaluate_open_discovery.py \
  --batch-root results/java_web_dos_batch/RUN \
  --seed-matches results/java_web_dos_batch/RECALL/truth_dispositions.jsonl \
  --output results/java_web_dos_benchmark/RUN-open-discovery
```

The read-only evaluator emits `seed_linked_static_vulnerable`,
`novel_static_vulnerable`, `novel_bounded`, `source_proven_negative`, and
`unresolved_discovery`. `--seed-matches` accepts either ordinary benchmark
`matches.jsonl` or PoC-33 `truth_dispositions.jsonl`; only concrete finding or
Growth IDs inside the same normalized `owner/repository` scope establish a
seed link. Unlinked seeds remain visible as deterministic seed-only
`unresolved_discovery` rows with `recall_miss=true`; linked analysis rows carry
`recall_miss=false`. Evaluation fails closed on illegal static verdict/
disposition pairs, stale concrete IDs on non-linking seed statuses,
finding/Growth chain mismatch, globally cross-repository analysis-ID reuse, or
any missing, orphaned, untyped, cross-Growth, or multiply owned negative proof.
For a real multi-Growth seed, resolved finding→Growth mappings need only be a
subset of its declared Growth IDs. The `matched_*`, ordinary `chain`, and nested
`candidate` carriers are validated independently before union; exact carrier
subsets are accepted, conflicting carriers fail closed even for IDs absent from
the scan, and multiple carriers must remain connected by a shared compatible ID
dimension rather than manufacturing a chain from disconnected fragments.
The global owner check also claims seed-side concrete IDs that are absent from
the current scan, so the same missing ID cannot be reused by two repositories;
same-repository seeds may still share it.
The output path must not already exist. Results are assembled in a private
mode-0700 sibling temporary directory and published on Linux with atomic
`renameat2(RENAME_NOREPLACE)`; a racing output leaf is not overwritten, and an
unavailable no-replace syscall is an error rather than a check-then-rename
fallback. The output parent is pinned by a component-wise no-follow directory-fd
walk and must already exist as a trusted directory; create that parent in a
separate setup step. The CLI never recursively creates missing output ancestors.
Temp
creation, writes, cleanup, existence checks, and rename remain dirfd-relative;
ancestor symlink races cannot redirect publication into immutable scan input.
Symlink-loop/path-resolution failures return status 2 without traceback. The
evaluator never rewrites the immutable scan or seed inputs.

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

# Full real production E2E: real fixture DB/queries + real APIBasis Responses client with mock transport
DOSWEB_RUN_CODEQL_FIXTURES=1 python3 -m pytest -q tests/test_production_e2e.py
```

Current Task 10 baseline: the network-free suite passes 797 tests plus 548 subtests (26 opt-in skips); the real CodeQL Entry/Growth/Lifecycle/production-E2E gate passes 35 tests plus 131 subtests. The four production E2E scenarios remain covered across Spring, Servlet, Netty, and MQTT, and candidate-relevant unresolved evidence remains certificate-backed `static_unknown` rather than being promoted through missing Reach, flow, or lifecycle proof.

These fixture checks create local test databases; the production E2E uses the real APIBasis Responses client with a bounded in-memory mock transport and does not contact the provider. No default test requires `DEEPSEEK_API_KEY`. The fixture database helper captures a bounded content-addressed Java snapshot directly at an unpredictable final `<digest>.sources-<128-bit-nonce>` name. Each directory's `os.scandir(fd)` stream increments and enforces the global 65,536-entry bound before the already-bounded entries are sorted by encoded name, so deterministic ordering cannot first materialize an unbounded iterator. The cache root itself is created/opened through a pinned parent dirfd with `mkdirat`/`statat`/`openat(O_DIRECTORY|O_NOFOLLOW)`; only the verified current-uid directory fd is `fchmod(0700)`, followed by fd/name/lexical/parent rebinding. After the source root is successfully opened with `O_DIRECTORY|O_NOFOLLOW` and rebound, authoritative mutation/materialization is pinned/root-relative, additional lexical validation may no-follow reopen/rebind, and the final tree is owner-only read-only `0500`/`0400`. It is never renamed to a shared digest alias. The helper likewise asks CodeQL to create the DB directly at a final `<digest>.db-<128-bit-nonce>` path without `--overwrite`; neither `<digest>.sources` nor `<digest>.db` is a normal consumable alias or legal helper-cleanup leaf, and obsolete `.sources.tmp-*`/`.db.tmp-*` staging names are also illegal. Under the digest lock, cross-process reuse scans at most 4,096 cache-root entries and eight exact candidates, streams source validation under the 65,536-entry/source-size bounds, validates every exact candidate plus DB provenance, fails closed on malformed/invalid candidates without mutating them, and chooses valid candidates deterministically. A second fresh process therefore reuses the same stable source and DB path instead of republishing a mutable temporary directory.

The same-uid unique-name-creation-to-pin and descendant `mkdirat`-to-`openat` windows are not hard creation-identity guarantees; those require credential/mount isolation or a stronger filesystem primitive. Per-digest locks are parent-dirfd-relative: pre-existing locks must already be current-uid regular single-link `0600` files, only a newly `O_EXCL`-created verified inode may be fchmoded, and the lexical name must still bind the locked inode after `flock`. A substitution completed before that post-flock rebind cannot enter the critical section; the named flock serializes cooperating helpers only and is not a hard lock against same-uid post-entry lock-name replacement. The selected source root remains descriptor-pinned for the complete CodeQL build. The subprocess uses `/proc/self/fd/<source-dirfd>` as `cwd`, keeps that descriptor in `pass_fds`, and resolves `--source-root=.` from the pinned cwd. The javac classes directory is likewise created inside the pinned cache-root dirfd, immediately opened with `O_DIRECTORY|O_NOFOLLOW`, rebound by fd/parent-relative/lexical identity, and hardened only with `fchmod(classes-fd, 0700)`; no lexical classes path is chmoded. Both the cache-root and classes-leaf opens reserve structural owner slots and preallocate close-once transactions before acquisition, and factory failure/normal cleanup release them through nested caller-local lexical pairs, so profile/trace/SIGINT call-entry interruption cannot leak or ABA-reclose either fd. CodeQL's trace-command intermediary does not preserve the inherited classes fd into javac, so `-d` uses the equivalent still-live helper capability `/proc/<helper-pid>/fd/<classes-fd>` while both source/classes fds remain in `pass_fds`; the helper validates that capability and every lexical binding before and after the build and cleans only the captured classes identity. Pre/post/final checks require the lexical source root, pinned inode, exact full-tree inode/metadata/bytes, and no-extra-node state to remain identical. Any build-window root/classes swap or transient node drift fails closed without chmoding or writing the substitute and prevents the helper-owned DB/classes from remaining at a normal consumable name.

Failure cleanup never performs `unlink`, `rmdir`, lexical `shutil.rmtree`, or any chmod on the retained tree. Under a private global cleanup flock it pins the owner-only cache root and no-replace-renames the exact legal root to an auditable same-parent `.<legal>.retained-<dev>-<ino>-<nonce>` tombstone; an identity mismatch is rolled back only when unambiguous and is never traversed. The exact tombstone root and every descendant are inspected read-only through no-follow parent-relative fds, preserving all modes and preventing an injected or preexisting outside inode from being mutated. The complete subtree is deliberately retained behind the owner-only `0700` cache-root boundary. Cooperative helper admission observes at most 64 tombstones, 1 GiB aggregate logical `st_size`, and 65,536 entries, rebinds each audited root after inventory, and requires the pinned cache root's stable identity to remain unchanged across the complete namespace inventory before accepting those observations; namespace add/remove or replacement drift fails closed. A newly over-budget exact root is no-replace-restored when unambiguous. These limits prevent unbounded growth from cooperating helper cleanups; they are not a hard filesystem quota against a same-uid process mutating retained fds/names after observation. Such an adversarial hard cap requires filesystem quota or credential/mount isolation. There is no automatic tombstone GC and no unknown inode is mutated or deleted. Manual reclamation is allowed only after every fixture process using a dedicated temporary root has exited: remove the whole dedicated `$TMPDIR/dosweb-fixture-codeql` from that quiescent external boundary, never individual tombstones while the helper is active. This cache contains artificial test fixtures only, never formal target bounded slices; the retention hardening changes no formal artifact or production fingerprint.

The current PoC-33 exploratory coverage archive is `results/java_web_dos_batch/poc33-p02-20260828_152629-entries/`. Its immutable `selection.json`, digest-bound `batch_plan.json`, completed batch state, per-target run manifests, and `acceptance_manifest.json` prove 21/21 targets, 8/8 selected queries per target, 168 total queries, zero diagnostics, and zero skipped queries. This entries archive is provider-independent and is not eligible for formal resume.

`scripts/run_poc33_demo_acceptance.py` also gates the network-free suite, real CodeQL fixtures, an explicitly authorized real-provider full canary, and the post-hoc offline evaluator. The real-provider layer digest-binds `model=grok-4.6`, `base_url=https://apibasis.com/v1/`, `timeout_seconds=180`, `max_retries=5`, and `allow_remote_llm=true` into its immutable full plan, and archive validation requires that exact five-field provider mapping; a self-consistent plan with different settings is not an accepted PoC-33 archive. It starts one fresh `--no-resume` invocation with `--retry-failed --max-attempts 2`. The runner may place only a persisted retryable authentication/provider-output/network target failure back onto that same invocation's bounded queue; the second target attempt is again non-resume, accepts no rejected response, and remains subject to the identical strict schema, evidence binding, positive gate, CodeQL policy, and provider-request retry budget. This includes a provider-returned `LLM_AUTHENTICATION_FAILED`, while missing local credentials remain a non-retryable authorization failure. Authentication still fails the current provider call immediately; only the one bounded fresh target attempt may retry it. Other non-retryable failures and a second failed target attempt remain terminal. Archive validation requires every completed target attempt count to be in `[1,2]` and reports how many targets required the bounded retry, so a previously terminated failed batch is never resumed or accepted. This changes only the request/target retry budget and does not relax schema or evidence checks. For `poc33-p02-20260828_152629`, the provider prerequisite record is `results/java_web_dos_batch/poc33-p02-20260828_152629-provider-prerequisite.json`; no `-full/`, recall, evaluation, or large-target rollout was created.

The first schema-2.7 provider canary at `results/java_web_dos_batch/poc33-schema27-provider-canary-v17-t180-20260902_134913-provider-canary` completed ThingsBoard but failed HertzBeat with `LLM_RESPONSE_SCHEMA_INVALID` and WGCLOUD with `LLM_NETWORK_FAILED`; the batch ended `completed_with_failures` and did not enter the PoC-33 21-target run. Private diagnosis isolated best-effort `json_object` enforcement as the HertzBeat root cause, while two source-free RightAPI probes verified strict `json_schema` enum and `oneOf` + `const` syntax support.

The fresh formal v30 strict-schema canary at `results/java_web_dos_batch/poc33-schema27-jsonschema-strict-v30-20260902_163604-provider-canary` completed formal Entry extraction for HertzBeat, ThingsBoard, and WGCLOUD but failed all three atomically in Growth with `LLM_RESPONSE_SCHEMA_INVALID`; the batch ended `completed_with_failures` and again did not enter the 21-target run. Sanitized owner-only diagnosis showed complete four-key Auth output but only a small Growth status-branch subset even though the request carried strict `json_schema`, all 17 required keys, `additionalProperties=false`, and three `oneOf` branches. A source-free RightAPI A/B held the same 17-field Growth schema constant: the composed schema returned only five keys, whereas removing `oneOf` returned all 17 with a consistent unknown-status triple. Growth v31 therefore uses a flat exact 17-key wire schema and keeps all cross-field consistency, evidence ownership/binding, safe correction, and positive-gate checks local. The subsequent fresh v31 three-target canary completed 3/3. Its first 21-target formal run completed 13/21 and failed eight provider calls; a second fresh run was stopped after two further retry exhaustions and one deterministic GROBID Flow failure. Local replay traced that Flow failure to Growth canonicalizing two distinct JAX-RS handlers solely because they shared one application registration site. Growth v32 now requires the complete same-handler registration-site identity and leaves that case `inventory_unresolved/ambiguous`. A fresh v32 three-target canary is required before another 21-target run; 178/205 rollout remains paused.

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

`entries` runs only local Entry extraction with bounded concurrency and strips any inherited provider credential. Formal growth additionally writes 0600 private `llm_audit.private.jsonl` records for constrained Growth/Auth Contract calls (normalized prompt, bounded raw response, parsed response, non-secret settings, attestation and cache provenance); they are never included in reports. The current default provider is APIBasis Responses at `https://apibasis.com/v1/` with model `grok-4.6` using the non-streaming Responses API; the owner-only API key remains in the gitignored `config/local_secrets.json` and must never be copied into reports or commits. The endpoint is non-streaming Responses only and sends the fixed provider User-Agent `pi-coding-agent`; HTTP 403 fails closed. Retryable transport failures include TLS EOF, timeout/temporary/reset/aborted/remote-EOF conditions, and errno-less proxy/tunnel failures that report 408/425/429/500/502/503/504; DNS `EAI_NONAME`, certificate verification, permission errors, and `EINVAL` remain permanent failures. Rotating that key rotates private-cache HMAC authentication, so provider runs must not resume an old cache across key changes; use a new immutable output directory. Remote calls require explicit `--allow-remote-llm` authorization, a non-empty provider API key, and a readable local source checkout; git-commit provenance (public URL, commit SHA, clean-checkout attestation) is optional metadata and no longer gates the remote path. Auth Contract decisions may cite only the entry security/configuration facts in their bounded slice, and unresolved authentication remains `unknown`. Formal analyzer stages fail closed when a selected CodeQL query fails. Only the explicit exploratory command `dos-web-analyzer entries --allow-partial-codeql` may record such a failure as a coverage gap; its manifest identity cannot be reused by formal analysis. `full` requires both `--allow-remote-llm` and a provider API key (from the `DEEPSEEK_API_KEY` environment variable or the gitignored local `config/local_secrets.json`, with the environment taking precedence). Use `full --plan-only` to construct and publish a non-executing full plan without a key or network; this still records only non-secret provider settings (`--model`, `--base-url`, `--timeout-seconds`, `--max-retries`, `--temperature`, `--cache-dir`, `--config`, and `--codeql-binary`) in the digest-bound plan. All 205 targets are queueable in full plans; a target whose source has only a `tree-sha256` fingerprint is executed against its local source tree, without requiring git-commit provenance. Per-target stage reuse remains governed by the production pipeline's strict manifests and hashes:

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
