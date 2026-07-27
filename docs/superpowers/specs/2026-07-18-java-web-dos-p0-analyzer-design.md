# Java Web DoS P0 Analyzer Design

**Date:** 2026-07-18
**Status:** Approved design
**Scope:** Full P0 static-analysis prototype for Spring MVC, Servlet, Netty, and MQTT

## 1. Purpose

This design defines the first complete v2 analyzer implementation slice. The analyzer identifies Java Web and adjacent network-service resource-exhaustion risks through explicit lifecycle evidence:

```text
E -> [Guard] -> G(P) -> [synchronous R(P)]
                \-[Bound]-/
```

The P0 analyzer will:

- recover externally reachable entries for Spring MVC, Servlet, Netty, and MQTT;
- detect four resource-growth classes;
- prove attacker-controlled `E -> G` flows;
- evaluate Guards, Bounds, and synchronous Releases;
- implement lifecycle assertions 1 and 2;
- use a constrained DeepSeek Growth Contract for bounded-slice semantic classification;
- emit auditable lifecycle certificates and static conclusions.

P0 does not implement asynchronous Release capacity analysis, lifecycle assertion 3, dynamic DoS execution, ML/GNN ranking, or broad support for additional frameworks.

## 2. Core Principles

1. **Static evidence owns the conclusion.** DeepSeek may classify local semantics but cannot independently produce a vulnerability verdict.
2. **Every conclusion is replayable.** Evidence must resolve to code locations, CodeQL facts, CFG/data-flow facts, registration facts, configuration facts, or deterministic rules.
3. **Coverage gaps are explicit.** Unsupported registration, routing, reflection, framework patterns, and lifecycle semantics must be reported rather than silently ignored.
4. **The ordinary analyzer remains static-only.** Historical PoCs and dynamic-validation results do not influence ordinary scan verdicts.
5. **Artifacts are stable and recoverable.** Every stage writes versioned, validated, content-addressed artifacts.
6. **Secrets never enter repository configuration or artifacts.** The DeepSeek API key is accepted only through the process environment.

## 3. Architecture

### 3.1 Analysis flow

```text
Java source / CodeQL database
              |
              v
       CodeQL fact extraction
 E / raw G / flow / guard / bound / release
              |
              v
      Python artifact pipeline
 schema validation + fact normalization
              |
              v
        Bounded-slice builder
              |
              v
    DeepSeek Growth Contract
 structured semantic classification
              |
              v
   Deterministic static verification
 E->G / Guard / Bound / synchronous Release
              |
              v
       Assertion 1 / Assertion 2
              |
              v
 Lifecycle certificates + static findings
```

### 3.2 Python package boundaries

```text
dos-web-analyzer
dosweb/
  cli.py
  config.py
  errors.py

  artifacts/
    schemas.py
    jsonl.py
    metadata.py
    identifiers.py

  codeql/
    runner.py
    database.py
    decoder.py

  entries/
    models.py
    normalize.py

  growth/
    models.py
    slices.py
    contracts.py
    verify.py

  flows/
    models.py
    verify.py

  lifecycle/
    guards.py
    bounds.py
    releases.py
    certificates.py

  conclude/
    assertions.py
    verdicts.py

  llm/
    client.py
    deepseek.py
    prompts.py
    schemas.py
    cache.py

  report/
    markdown.py
    summary.py
```

Each package has one responsibility. Query execution, provider calls, semantic verification, conclusion logic, and reporting must not be combined in a single module.

### 3.3 CodeQL package boundaries

```text
codeql/
  qlpack.yml
  dosweb/
    Entries/
      SpringMvcEntries.ql
      ServletEntries.ql
      NettyEntries.ql
      MqttEntries.ql
    Growth/
      InputMaterialization.ql
      DirectAllocation.ql
      ContainerGrowth.ql
      AsyncWorkGrowth.ql
    Flows/
      EntryToGrowth.ql
    Lifecycle/
      GuardCandidates.ql
      BoundCandidates.ql
      SynchronousReleaseCandidates.ql
```

The initial framework models cover common statically registered patterns. Unsupported patterns force an explicit coverage gap and, where they may affect a candidate, a conservative unknown conclusion.

## 4. CLI and Configuration

### 4.1 User-facing command

```bash
dos-web-analyzer analyze \
  --database databases/example \
  --output results/v2/example \
  --model deepseek-v4-pro
```

The complete run follows a fixed order and stops on a failed required stage.

### 4.2 Recoverable internal commands

```bash
dos-web-analyzer entries
dos-web-analyzer growth
dos-web-analyzer flows
dos-web-analyzer lifecycle
dos-web-analyzer conclude
dos-web-analyzer report
```

Each command validates upstream artifact versions, schemas, hashes, and reference integrity before running.

### 4.3 Configuration precedence

```text
CLI arguments > configuration file > environment variables > safe defaults
```

DeepSeek environment variables:

```bash
export DEEPSEEK_API_KEY='...'
export DEEPSEEK_BASE_URL='https://api.deepseek.com/'
```

A configuration file may contain non-secret provider settings:

```yaml
llm:
  provider: deepseek
  model: deepseek-v4-pro
  base_url: https://api.deepseek.com/
  timeout_seconds: 60
  max_retries: 3
  temperature: 0
```

An `api_key` field in a configuration file is rejected with `CONFIG_SECRET_IN_FILE`. The analyzer never persists the key, authorization headers, or the complete process environment.

### 4.4 Provider behavior

The Python provider calls DeepSeek through its OpenAI-compatible HTTP API. Supported configured model names are:

- `deepseek-v4-pro`, the default formal-analysis model;
- `deepseek-v4-flash`, an explicitly selected development model.

The remote API remains authoritative about actual model availability. An unknown local model name is rejected before a request; a configured name rejected by the remote API fails the run.

DeepSeek is mandatory for P0 runs. Missing credentials, exhausted retryable failures, authentication errors, invalid responses, empty responses, refusal without a valid contract, and response-schema violations fail the run. A valid contract whose semantic answer is `unknown` is a successful provider call and produces a conservative analysis result.

## 5. Artifact Contract

Every stage emits versioned JSON or JSONL under `results/v2/<run-id>/`:

```text
run.json
coverage.json
entry_facts.jsonl
growth_candidates.jsonl
growth_contracts.jsonl
verified_growth.jsonl
flow_proofs.jsonl
guard_candidates.jsonl
bound_candidates.jsonl
release_candidates.jsonl
lifecycle_results.jsonl
static_findings.jsonl
lifecycle_certificates.jsonl
summary.json
report.md
```

`run.json` records:

- tool and schema versions;
- CodeQL CLI and query-pack versions;
- database fingerprint;
- non-secret configuration hash;
- provider, model, base-URL identity, decoding parameters, and prompt version;
- input and output artifact hashes;
- stage status, timing, and terminal error code.

Artifacts use deterministic identifiers derived from normalized semantic identity and content. Downstream references to absent or incompatible facts are fatal artifact errors rather than silently dropped records.

## 6. Fact Model

### 6.1 Entry fact `E`

```json
{
  "entry_id": "entry:...",
  "framework": "spring_mvc|servlet|netty|mqtt",
  "protocol": "http|tcp|mqtt",
  "handler": {
    "callable": "...",
    "file": "...",
    "start_line": 1
  },
  "registration": {},
  "route_or_event": "...",
  "auth_context": "unauthenticated|low_privilege|privileged|unknown",
  "attacker_inputs": [],
  "materialization_phase": "before_handler|in_handler|streaming|unknown"
}
```

A handler definition alone does not prove external reachability. Registration, route/event, protocol trigger, authentication context, and attacker-controlled values remain separate evidence fields.

### 6.2 Growth fact `G(P)`

P0 recognizes:

- `input_materialization`;
- `direct_allocation`;
- `container_growth`;
- `async_work_growth`.

```json
{
  "growth_id": "growth:...",
  "site": {},
  "kind": "container_growth",
  "operation": "Map.put",
  "resource_point": {
    "resource_id": "resource:...",
    "dimension": "entries|bytes|tasks|connections|objects",
    "receiver": "...",
    "field_path": "..."
  },
  "demand_inputs": [],
  "escape_scope": "request|session|instance|global|unknown",
  "candidate_evidence": []
}
```

The resource point identifies the actual receiver and resource dimension. An API name alone is not a verified growth fact.

### 6.3 Flow proof

```json
{
  "path_id": "flow:...",
  "entry_id": "entry:...",
  "growth_id": "growth:...",
  "attacker_control": {
    "target": "size|key|value|iteration_count|submission_count",
    "source": "...",
    "sink": "..."
  },
  "call_path": [],
  "phase_sequence": [],
  "confidence": "proven|partial"
}
```

Only a `proven` flow can satisfy the flow premise of `static_vulnerable`. A `partial` flow remains useful evidence but forces `static_unknown` unless another proven path exists.

## 7. Bounded Slice and Growth Contract

Each Growth candidate receives one normalized bounded slice containing only the relevant entry, candidate operation, surrounding code, proven data-flow facts, CFG summary, receiver/key facts, registration facts, and configuration facts.

The model returns a strict structure:

```json
{
  "is_resource_growth": "yes|no|unknown",
  "growth_kind": "input_materialization|direct_allocation|container_growth|async_work_growth|unknown",
  "resource_dimension": "entries|bytes|tasks|connections|objects|unknown",
  "attacker_influence": [],
  "resource_effect": "...",
  "required_static_evidence": [],
  "confidence": "high|medium|low"
}
```

Deterministic verification enforces that:

1. every cited location belongs to the input slice;
2. enum values conform to the response schema;
3. required evidence maps to extracted static facts;
4. a model `yes` does not directly create `verified_growth`;
5. unsupported or unprovable claims produce `unresolved` rather than a vulnerability fact.

The complete normalized prompt, response schema version, model settings, raw response body, parsed response, and content hashes are retained for audit. Authentication material is excluded.

## 8. Lifecycle Analysis

### 8.1 Effective Guard

A Guard is effective for `(E, G, path)` only when it:

- executes before or inside G;
- dominates the relevant `E -> G` path;
- prevents the rejected branch from reaching G;
- limits the same resource representation and dimension;
- is finite and enabled under the modeled default configuration;
- covers the relevant entry and materialization phase.

### 8.2 Effective Bound

Internal Bound states are:

```text
absent
scope_mismatched
dimension_mismatched
possibly_over_budget
effective
unknown
```

A Bound is `effective` only when it satisfies all of:

```text
same resource dimension
and before or inside growth
and covers the E->G path
and applies to the same resource scope
and reliably rejects, blocks, or atomically evicts
```

Ignored return values, fail-open behavior, bypass paths, unbounded defaults, or capacity limits on a different resource dimension prevent an effective result.

### 8.3 Effective synchronous Release

P0 confirms a Release only when static evidence proves:

- the same receiver or resource point;
- matching key or item identity where relevant;
- a feasible path after G;
- an actual reduction in P rather than state copying or transfer;
- coverage of the modeled normal and exceptional paths.

Workers, timers, callbacks, protocol acknowledgements, consumer throughput, and other asynchronous Release mechanisms are not proven safe in P0. Potential asynchronous Release evidence is recorded and forces `static_unknown` for assertion 2 rather than being treated as absent.

## 9. P0 Assertions

### 9.1 Assertion 1: unbounded direct growth

```text
proven E->G
and attacker controls resource demand
and verified growth
and no effective Guard
and no effective Bound
```

This primarily covers input materialization and direct allocation, while permitting a single request to amplify container or asynchronous-work growth.

### 9.2 Assertion 2: persistent accumulation without Release

```text
proven repeatable E->G
and attacker controls key, value, submission, or resource creation
and verified escaping growth
and no effective Bound
and no effective synchronous Release
and no unresolved asynchronous-Release evidence
```

If plausible asynchronous Release exists but P0 cannot validate it, the candidate is `static_unknown`. Assertion 3 will later analyze trigger, capacity, time-window, and coverage constraints.

## 10. Verdict Semantics

P0 replaces the unconditional-safe label with:

```text
static_vulnerable
bounded_under_modeled_assumptions
static_unknown
```

`bounded_under_modeled_assumptions` requires:

- an effective Guard, Bound, or synchronous Release proof sufficient to refute the applicable P0 assertion;
- modeled default-configuration evidence;
- covered entries and paths;
- explicit assumptions;
- coverage gaps;
- stable reason codes.

It is a static conclusion under stated assumptions, not a dynamic safety proof. Implementing this design requires updating the active project instructions, README, schemas, existing static aggregator, and dynamic-validation scaffold validators so they use the new vocabulary consistently. No legacy `static_safe` compatibility mode will be retained.

## 11. Coverage Model

Every run writes framework coverage records:

```json
{
  "framework": "netty",
  "status": "complete|partial|unsupported",
  "supported_patterns": [],
  "unsupported_patterns": [],
  "effect_on_verdict": "none|forces_unknown"
}
```

Unsupported reflection, dynamic routing, custom registration, wrapper semantics, or protocol behavior cannot disappear from the report. A gap forces unknown whenever it may invalidate a vulnerable or bounded conclusion for the candidate.

## 12. Error Handling

Stable error families are:

```text
CONFIG_*        configuration or environment errors
CODEQL_*        CodeQL CLI, database, or query errors
ARTIFACT_*      JSONL, schema, hash, or artifact errors
LLM_*           DeepSeek request, response, or contract errors
ANALYSIS_*      fact-linking or deterministic-analysis errors
COVERAGE_*      framework-model coverage errors
INTERNAL_*      otherwise unclassified internal errors
```

Required initial codes include:

```text
CONFIG_MISSING_DEEPSEEK_API_KEY
CONFIG_SECRET_IN_FILE
CODEQL_DATABASE_INVALID
CODEQL_QUERY_FAILED
ARTIFACT_SCHEMA_MISMATCH
ARTIFACT_UPSTREAM_HASH_MISMATCH
LLM_RETRIES_EXHAUSTED
LLM_RESPONSE_SCHEMA_INVALID
ANALYSIS_DANGLING_FACT_REFERENCE
```

CLI exit status:

- `0`: complete analysis;
- `2`: command or configuration error;
- `3`: CodeQL or database failure;
- `4`: mandatory LLM failure;
- `5`: artifact or schema corruption;
- `6`: internal analyzer error.

`static_unknown` is a valid completed analysis outcome, not a process failure.

## 13. Atomic Publication and Recovery

A stage:

1. validates upstream schemas, hashes, and references;
2. writes to a same-directory temporary file;
3. flushes and `fsync`s the file;
4. validates schema, reference integrity, and record counts;
5. atomically renames the completed artifact;
6. publishes the stage manifest;
7. updates `run.json` last.

A failed stage does not publish a partial formal artifact. Successful upstream artifacts remain reusable.

Recovery is explicit:

```bash
dos-web-analyzer analyze ... --resume
```

A stage is reusable only if these match:

- schema version;
- compatible tool version;
- database fingerprint;
- query-pack hash;
- non-secret configuration hash;
- upstream artifact hashes;
- stage implementation version.

The first mismatch invalidates that stage and every downstream stage.

## 14. LLM Cache and Request Policy

### 14.1 Cache identity

```text
SHA-256(
  provider
  + base-URL identity
  + model
  + decoding parameters
  + prompt version
  + response-schema version
  + normalized bounded slice
)
```

Successful schema-valid responses may be reused. Network failures, rate limits, empty responses, parse failures, and schema-invalid responses are not successful cache entries.

### 14.2 Request defaults

- temperature: `0`;
- timeout: `60` seconds;
- maximum retries: `3`;
- retry only timeouts, interrupted connections, HTTP 429, and retryable 5xx responses;
- fail immediately on authentication, invalid-request, and response-schema errors;
- use bounded exponential backoff with jitter;
- redact credentials and probable secrets from logs.

## 15. Testing Strategy

### 15.1 Python unit tests

Network-free tests cover:

- valid and invalid schemas;
- deterministic identifiers and hashes;
- strict JSONL parsing;
- configuration precedence;
- rejection of secrets in configuration files;
- verdicts and reason codes;
- Guard, Bound, and synchronous Release decisions;
- assertions 1 and 2;
- coverage-driven unknown conclusions;
- secret redaction;
- stage invalidation and resume behavior.

### 15.2 Provider contract tests

A local mock HTTP server tests:

- valid structured output;
- HTTP 429 and 5xx retries;
- immediate HTTP 401 failure;
- timeout handling;
- non-JSON and empty responses;
- response-schema violations;
- a valid semantic `unknown` response;
- cache reuse;
- credential redaction.

Default tests do not contact DeepSeek.

### 15.3 CodeQL fixture tests

```text
tests/fixtures/
  spring/
  servlet/
  netty/
  mqtt/
```

Each fixture includes:

- an externally reachable entry;
- a similar but non-entry handler;
- representative G1-G4 operations;
- effective and ineffective Guards;
- bounded and unbounded containers or queues;
- matching and mismatching receiver/key Releases;
- reflection or asynchronous behavior that must force unknown.

Tests assert fact contents and relationships, not only row counts.

### 15.4 End-to-end scenarios

P0 acceptance fixtures cover:

1. unbounded request-body or parser materialization;
2. attacker-controlled direct allocation;
3. global-map accumulation under distinct keys without Release;
4. an unbounded executor queue;
5. a finite queue with reliable rejection;
6. a Guard that executes after materialization;
7. Release only on the success path;
8. a potential asynchronous consumer that P0 must classify as unknown;
9. a Netty handler registration chain;
10. an MQTT topic or QoS callback entry.

End-to-end tests verify artifact parsing, reference integrity, expected verdicts, certificate completeness, JSON/report consistency, and resume behavior without duplicate CodeQL or LLM calls.

### 15.5 Opt-in online test

A separate integration test may contact DeepSeek only when explicitly invoked with a newly issued environment key. It sends an artificial repository fixture slice and does not upload code from real analysis targets.

CI remains network-free and does not require a DeepSeek credential.

## 16. Compatibility with Existing Assets

- Keep `scripts/build_top50_codeql_dbs.py` as the database-preparation layer.
- Keep dynamic-validation helpers separate from the static analyzer.
- Update the existing static aggregator to accept the new verdict vocabulary.
- Do not delete or rewrite preserved `databases/`, `frameworks/`, `poc/`, static-hunt results, application results, or Java Web batch results.
- Do not use historical dynamic evidence to alter ordinary static conclusions.
- Do not start services, send attack traffic, or perform dynamic DoS validation as part of P0.

## 17. Explicitly Deferred Work

P0 excludes:

- asynchronous registration-to-callback Release proof;
- producer/consumer rate and service-capacity reasoning;
- client-triggered ACK, reconnect, or close semantics;
- timeout, renewable TTL, and terminal-path coverage analysis for assertion 3;
- ML/GNN candidate ranking;
- JAX-RS, WebSocket, gRPC, and arbitrary custom protocol support;
- automated dynamic validation;
- deployment-budget proof beyond modeled static configuration.

These exclusions must appear as coverage or lifecycle limitations rather than being treated as evidence of safety.

## 18. P0 Acceptance Criteria

P0 is complete only when all of the following are true:

- baseline Spring MVC, Servlet, Netty, and MQTT entry models run on fixtures;
- G1-G4 candidates pass through Growth Contract and deterministic verification;
- the analyzer proves `E -> G` and the attacker-controlled demand dimension;
- Guard, Bound, and synchronous Release analysis is available;
- assertions 1 and 2 produce certificate-backed results;
- the new three-value verdict vocabulary is used consistently across active tooling and documentation;
- coverage gaps are visible and can force unknown;
- mandatory provider failures fail the run;
- the default test suite is network-free;
- an opt-in real-provider test is available;
- ordinary conclusions remain independent from historical and current dynamic evidence;
- P0 performs no dynamic DoS execution.
