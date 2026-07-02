# Java Web Resource-Exhaustion DoS Analyzer v2 Rewrite Design

Date: 2026-07-02

## 1. Purpose

This design replaces the existing phase-based `dos-analysis-web` tool with a product-oriented static analysis platform for Java Web and adjacent Java network applications. The new tool is built around the user-specified model:

```text
Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)
```

The rewrite has three simultaneous goals:

- Paper readiness: produce a defensible ICSE/FSE/ASE/ISSTA-style methodology, benchmark, ablation data, and reproducible static conclusions.
- Vulnerability hunting: keep the workflow useful for finding new resource-exhaustion candidates in real Java applications.
- Engineering quality: provide a maintainable CLI, stable schemas, restartable stages, and testable modules.

The selected implementation strategy is CLI/Product-First: rebuild `dos-web-analyzer` and the repository layout first, then fill the stages with CodeQL fact extraction, ML-based growth classification, LLM-assisted local summaries, rule verification, flow proof, bound checking, benchmark import, and reporting.

## 2. Scope

The v2 first release is static-only. It does not run dynamic validation. Existing dynamic evidence under `poc/` and historical result directories is imported only as oracle evidence, ML labels, and paper benchmark material.

The analysis scope includes:

- HTTP, Servlet, Spring MVC/WebFlux, JAX-RS, filters, interceptors, message converters, and common Java Web framework routes.
- WebSocket entry points.
- gRPC services.
- MQTT and custom TCP protocol services when they are part of Java server applications.
- Four resource-growth families: `parser_materialization`, `allocator_growth`, `queue_growth`, and `container_growth`.

The rewrite removes the old Phase 1/2/3/4 model, the old five-axis `R/V/M/C/L` compatibility layer, old phase reports, and old changelog history during implementation. `WEB-REAL-*` and old reports are not part of the v2 public story.

## 3. Preservation And Cleanup Policy

Implementation must preserve these paths:

```text
databases/
frameworks/
poc/
results/static_hunts/
results/application*
results/java_web_dos_batch/
```

Implementation may delete or rewrite:

```text
codeql/
scripts/
tests/
dos-web-analyzer
old Phase 1/2/3/4 results and reports
old README phase narrative
old CHANGELOG.md history
```

`poc/` is an evidence archive and must remain unchanged in this rewrite. Existing bilingual advisory files stay as they are.

`CHANGELOG.md` will be reset as a v2 baseline during implementation, but every post-v2 project modification must still add a new changelog entry.

## 4. CLI Architecture

`dos-web-analyzer` remains the only user-facing executable. It becomes a thin wrapper over a Python package.

Primary commands:

```text
dos-web-analyzer entries
dos-web-analyzer growth
dos-web-analyzer flows
dos-web-analyzer bounds
dos-web-analyzer conclude
dos-web-analyzer benchmark
dos-web-analyzer report
dos-web-analyzer analyze
```

Command responsibilities:

- `entries`: extract and normalize entry facts `E`.
- `growth`: detect and verify resource-growth facts `G` using the required chain: CodeQL -> ML -> LLM -> rules.
- `flows`: prove concrete `E -> G` taint/path relationships.
- `bounds`: extract `B_candidate` facts and run path-specific `EffectiveB(E, G, path, B)`.
- `conclude`: apply the static vulnerability predicate and emit static findings.
- `benchmark`: import oracle labels and evaluate detector stages; it does not change ordinary scan verdicts.
- `report`: generate English Markdown/JSON/CSV reports.
- `analyze`: orchestrate the static pipeline in order: `entries -> growth -> flows -> bounds -> conclude`.

The earlier idea of a broad `facts` command is intentionally rejected. B evidence depends on concrete `E -> G` path information, so B effectiveness cannot be claimed during raw fact extraction.

## 5. Repository Layout

Target layout:

```text
dos-web-analyzer
dosweb/
  cli.py
  config.py
  codeql_runner.py
  entries/
  growth/
  flows/
  bounds/
  conclude/
  ml/
  llm/
  benchmark/
  report/
  schemas/
codeql/
  qlpack.yml
  lib/
    EntrySources.qll
    GrowthSources.qll
    FlowProof.qll
    BoundCandidates.qll
    ConfigFacts.qll
    ProtocolModels.qll
  queries/
    entries.ql
    raw_growth.ql
    flow_to_growth.ql
    bound_candidates.ql
    config_facts.ql
data/
  oracle/
    static_positive_seeds.jsonl
    strong_negative_seeds.jsonl
    weak_negative_seeds.jsonl
  models/
results/v2/
  facts/
  growth/
  flows/
  bounds/
  findings/
  benchmark/
  reports/
```

Python modules must be small and stage-oriented. CodeQL remains the primary static fact extractor; Python does not replace CodeQL data-flow analysis.

## 6. Core Pipeline

The pipeline order is fixed:

```text
EntrySet(E)
  -> RawGrowthCandidates
  -> ML-ranked G candidates
  -> LLM resource-effect summaries for unknown wrappers
  -> VerifiedGrowthSet(G)
  -> FlowProof(E -> G)
  -> BoundCandidates(B)
  -> EffectiveB(E, G, path, B)
  -> StaticFinding
```

Each stage writes stable JSONL artifacts so paper experiments and engineering runs can resume from any boundary:

```text
entry_facts.jsonl
growth_candidates.jsonl
verified_growth.jsonl
flow_proofs.jsonl
bound_candidates.jsonl
effective_bound_results.jsonl
static_findings.jsonl
```

## 7. Entry Model `E`

`E` represents an external entry and its initial tainted values.

Minimum schema:

```json
{
  "entry_id": "string",
  "entry_method": "string",
  "framework": "spring_mvc|servlet|jaxrs|grpc|websocket|mqtt|custom_tcp|unknown",
  "protocol": "http|websocket|grpc|mqtt|custom_tcp",
  "phase": "container_parse|servlet_filter|security_filter|interceptor|argument_resolver_or_message_converter|controller|service|async_enqueue|async_worker",
  "route": "string",
  "auth_context": "preauth|anonymous_allowed|weak_or_default_token|authenticated_user|admin_only|unknown",
  "taint_values": []
}
```

Important entry requirements:

- Record protocol-specific dimensions such as `body_bytes`, `body_chars`, `json_nodes`, `frame_bytes`, `protobuf_bytes`, `message_count`, and `value_space`.
- Record `already_materialized_by` for framework argument binding, message converters, filters, request wrappers, gzip/protobuf decoders, and protocol parsers.
- Do not decide vulnerability or risk at entry extraction time.

## 8. Growth Detection `G`

`growth` is the central subsystem. Its required order is:

```text
CodeQL raw screening -> ML filter/ranker -> LLM summary -> rule/static verification
```

ML is used to judge whether a raw candidate is a real resource-growth operation. It is not the final vulnerability ranker.

Supported G kinds:

```text
parser_materialization
allocator_growth
queue_growth
container_growth
```

Minimum `G` schema:

```json
{
  "growth_id": "string",
  "kind": "parser_materialization|allocator_growth|queue_growth|container_growth",
  "site": "string",
  "phase": "string",
  "resource_dimension": "string",
  "demand_expr": "string",
  "carrier": "string",
  "lifecycle": "request|session|connection|executor_pending|singleton|static|ttl_window",
  "taint_dependency": [],
  "ml_score": 0.0,
  "llm_summary_id": null,
  "verification_status": "verified|rejected|needs_review",
  "evidence": []
}
```

Raw CodeQL screening covers:

- Parser materialization: full stream/body reads, request wrappers, gzip/protobuf expansion, JSON tree/object parsing, DTO graph creation, `@RequestBody String`, `byte[]`, DTO, and list binding.
- Allocator growth: `new byte[n]`, `ByteBuffer.allocate(n)`, `BufferedImage(w,h)`, `BitMatrix(w,h)`, `StringBuilder.ensureCapacity`, barcode/captcha/pdf/excel render helpers, and tainted size expressions.
- Queue growth: executor submission, scheduler submission, `CompletableFuture`, unbounded queues, application event queues, protocol pending queues, and thread/job creation.
- Container growth: retained maps, lists, sets, caches, session attributes, singleton/static fields, protocol session registries, retained MQTT messages, offline queues, and cardinality-driven state.

ML training labels:

- Positive seeds: all records from `results/applications_dynamic_validation/binary_truth_collection.json` are treated as static high-value positive seeds for growth detection, including records dynamically marked unconfirmed. This label means "static positive seed", not "dynamic confirmed vulnerability".
- Strong negatives: request-local collections, constant-key overwrites, hard limits before growth, bounded queues with checked rejection, valid cache eviction, and test/example-only non-deployed paths.
- Weak negatives: low-risk raw G candidates from `results/static_hunts` and `frameworks/` not selected as positive seeds. These are used only for ranking regularization or ablation, not as clean main-training negatives.

LLM usage in growth detection:

- LLM summarizes local resource effects for unknown wrappers, business helpers, and third-party helpers.
- LLM outputs must be statically verified: referenced methods must exist, callees must contain read/copy/parse/allocation/enqueue/put evidence, resource dimensions must match the schema vocabulary, and taint dependencies must be checkable by CodeQL or local AST evidence.
- LLM never confirms a vulnerability verdict.

The rule/static verifier emits:

```text
verified
rejected
needs_review
```

Only `verified` G records enter default flow proof.

## 9. Flow Proof

`flows` proves concrete `E -> G` relationships only after `VerifiedGrowthSet(G)` exists.

Minimum flow schema:

```json
{
  "path_id": "string",
  "entry_id": "string",
  "growth_id": "string",
  "source_expr": "string",
  "sink_expr": "string",
  "call_path": [],
  "phase_sequence": [],
  "content_type_or_protocol_condition": "string",
  "confidence": "high|medium|low"
}
```

The flow proof target is `G.demand_expr`, `G.growth_driver`, or a tainted retained payload/size expression, depending on G kind.

Isolated growth sites without `E -> G` proof are not static vulnerabilities. They can remain debug or benchmark material.

## 10. Bound Candidates And EffectiveB

`B_candidate` is an independently extracted fact. It does not mean the bound is effective.

Minimum `B_candidate` schema:

```json
{
  "bound_id": "string",
  "kind": "limit|quota|capacity|reject|backpressure|release|expire|rate",
  "site": "string",
  "phase": "string",
  "resource_dimension": "string",
  "scope": "string",
  "target": "string",
  "behavior": "fail_closed|fail_open|release|truncate|unknown",
  "evidence": []
}
```

`EffectiveB(E, G, path, B)` is path-specific and checks exactly:

```text
SameDimension(B, G)
BeforeOrInside(B, G)
PathCover(B, E, G)
SameScope(B, G)
StopOrRelease(B, G)
```

Minimum result schema:

```json
{
  "entry_id": "string",
  "growth_id": "string",
  "path_id": "string",
  "bound_id": "string",
  "decision": "effective|ineffective|conditional|unknown",
  "reason_codes": [],
  "checks": {
    "same_dimension": true,
    "before_or_inside": true,
    "path_cover": "true|false|unknown",
    "same_scope": true,
    "stop_or_release": "true|false|unknown"
  }
}
```

Required reason-code behavior:

- Multipart limits do not cover JSON/raw body materialization.
- `@Valid` and DTO `@Size` do not cover filter/converter materialization that happened earlier.
- `corePoolSize` and `maxPoolSize` do not bound unbounded executor queues.
- `Content-Length` checks do not bound chunked requests without `Content-Length`.
- Single-dimension guards do not cover product growth such as `width * height`.
- Rate limit and TTL are conditional unless arrival/resource bounds prove capacity safety.
- Success-only removal does not cover exceptional retained-state paths.
- `catch OutOfMemoryError` is not a valid bound.

## 11. Static Conclusion

The conclusion stage applies:

```text
Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)
```

Static verdicts:

```text
static_vulnerable
static_safe
static_unknown
```

Rules:

- `static_vulnerable`: `E -> G` is proven, G is verified, and no effective B covers the path.
- `static_safe`: `E -> G` and G are present, but an effective B covers all feasible paths.
- `static_unknown`: flow, bound, configuration, path coverage, or runtime condition evidence is insufficient.

Ordinary scan output must not call a finding dynamically confirmed. Dynamic confirmation is only represented by imported oracle evidence in benchmark/report modes.

## 12. Benchmark Mode

Benchmark mode is separate from normal scanning.

It imports:

```text
poc/manifest.json
results/applications_dynamic_validation/binary_truth_collection.json
results/static_hunts/
results/application*
results/java_web_dos_batch/
```

Benchmark labels:

```text
positive_seed
strong_negative
weak_negative
unlabeled
dynamic_confirmed_reference
```

`positive_seed` is a static/ML training label. `dynamic_confirmed_reference` is a dynamic evidence label. They must not be conflated.

Benchmark reports cover:

- Growth detector performance.
- `E -> G` flow coverage.
- EffectiveB decision and reason-code distribution.
- ML ablation with and without weak negatives.
- LLM-assisted unknown-wrapper coverage.
- End-to-end static recall and precision proxy against the imported oracle.

## 13. Reports

Reports and machine-readable outputs are English-first.

Expected outputs:

```text
results/v2/reports/static_findings.md
results/v2/reports/static_findings.json
results/v2/reports/benchmark_summary.md
results/v2/reports/benchmark_tables.csv
results/v2/reports/ml_ablation.md
```

Each static finding includes:

- Entry `E`.
- Tainted source.
- Verified `G`.
- `E -> G` path evidence.
- B candidates.
- EffectiveB decision and reason codes.
- Static verdict.
- Suggested fix.
- Confidence and limitations.

## 14. Error Handling And Reproducibility

Each command must:

- Validate input schemas before processing.
- Write partial outputs only through atomic temp-file replacement.
- Emit structured run metadata with command, config hash, CodeQL version, target database, model version, and input artifact hashes.
- Allow restart from completed stage artifacts.
- Fail closed when schemas are missing or incompatible.
- Mark unknown or unverifiable facts as `needs_review` or `static_unknown`, not as vulnerabilities.

LLM calls must be cacheable and optional. A run without LLM access must still complete with lower unknown-wrapper coverage.

## 15. Testing Strategy

Minimum tests for v2:

- Schema tests for every JSONL artifact.
- CLI smoke tests for each subcommand.
- CodeQL query smoke tests on at least one small fixture project.
- Growth verifier unit tests for all four G kinds.
- EffectiveB unit tests for dimension mismatch, phase-too-late, path-not-covered, scope mismatch, fail-open, release-not-aliased, unbounded queue, thread-bound-not-queue-bound, rate-not-capacity, TTL conditional, and integer-overflow guard cases.
- Oracle import tests for `poc/manifest.json` and `binary_truth_collection`.
- ML training reproducibility tests with fixed seed and saved feature metadata.
- End-to-end dry run on a small database fixture.

No dynamic DoS probes are part of v2 first-release verification.

## 16. Implementation Milestones

Milestone 1: Repository baseline and CLI shell.

- Rewrite `dos-web-analyzer`.
- Create `dosweb/` package and command structure.
- Reset old phase-oriented docs and changelog history as v2 baseline.
- Preserve required evidence/database directories.

Milestone 2: Schemas and artifact pipeline.

- Define `E`, raw G, verified G, flow proof, B candidate, EffectiveB result, static finding, and benchmark label schemas.
- Add schema validation and artifact writers.

Milestone 3: CodeQL raw extraction.

- Implement entry, raw growth, flow, bound, config, and protocol model queries.
- Keep query outputs fact-oriented.

Milestone 4: Growth classifier.

- Import positive seeds from `binary_truth_collection`.
- Build strong/weak negative sampling.
- Train and persist first growth classifier.
- Add rule/static verifier.

Milestone 5: Flow and EffectiveB.

- Prove `E -> G`.
- Extract B candidates.
- Implement path-specific EffectiveB checker.

Milestone 6: Conclusions, benchmark, and reports.

- Emit static findings.
- Map oracle labels in benchmark mode.
- Generate English reports and paper tables.

## 17. Design Decisions

Confirmed decisions:

- Use CLI/Product-First rewrite.
- Use CodeQL as the main static fact extractor.
- Use ML as part of G detection, not final vulnerability ranking.
- Use LLM only for local, auditable resource-effect summaries and reason-code hints.
- Do not run dynamic validation in v2 first release.
- Output static verdict and benchmark labels on separate tracks.
- Cover HTTP, WebSocket, gRPC, MQTT, and custom TCP entries.
- Remove old five-axis verdict compatibility and old phase reports.
- Preserve `poc/` unchanged.
- Use English-first report artifacts.

No unresolved product decisions remain for the design phase.
