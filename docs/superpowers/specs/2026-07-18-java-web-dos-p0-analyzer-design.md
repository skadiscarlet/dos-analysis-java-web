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
6. **Secrets never enter repository configuration or artifacts.** The DeepSeek API key is accepted only through the process environment or a gitignored local secrets file (`config/local_secrets.json`).

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

#### 3.1.1 Compliance-repair interfaces (2026-08-17)

`entries` remains offline and additionally publishes bounded `ModeledConfigurationFact` and `EntrySecurityFact` artifacts. A formal Growth run may use a separate constrained Auth Contract: its answer is accepted only when every cited security/configuration fact belongs to the candidate's bounded slice; unresolved authentication remains `unknown`. `analysis.modeled_defaults` and repeated non-secret `--modeled-default key=value` are provenance-bearing modeled defaults (CLI > config > extracted default > unknown). Formal stages fail on selected CodeQL query failure; only explicit exploratory `entries --allow-partial-codeql` may publish a coverage-gap result, which formal full runs cannot resume. Formal Growth/Auth calls additionally publish a bounded 0600 private audit artifact containing normalized prompt, schema/version, non-secret settings, raw provider envelope, parsed result, attestation, hashes and cache provenance; credentials, headers and environment are prohibited. Application configuration extraction is allowlist-based and never persists or transmits password/token/key/credential fields or arbitrary business strings. Remote provider use requires a public GitHub URL whose local origin, unauthenticated public-repository API result, and exact commit SHA all match; a local-only commit attestation cannot authorize source upload.

## 3.2 Python package boundaries

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

Alternatively the API key may be pinned in a gitignored local secrets file `config/local_secrets.json`:

```json
{"deepseek_api_key": "sk-..."}
```

The environment variable takes precedence over the local secrets file.

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

An `api_key` field in a configuration file is rejected with `CONFIG_SECRET_IN_FILE` (it belongs in the separate gitignored `config/local_secrets.json`, never in the tracked YAML). The analyzer never persists the key, authorization headers, or the complete process environment.

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
  "framework": "spring_mvc|servlet|netty|mqtt|jax_rs|grpc",
  "protocol": "http|tcp|mqtt|grpc",
  "handler": {
    "callable": "...",
    "file": "...",
    "start_line": 1
  },
  "registration": {},
  "registration_pattern_id": "entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
  "route_or_event": "...",
  "auth_context": "unauthenticated|low_privilege|privileged|unknown",
  "attacker_inputs": [],
  "materialization_phase": "before_handler|in_handler|streaming|unknown"
}
```

A handler definition alone does not prove external reachability. Registration, route/event, protocol trigger, authentication context, and attacker-controlled values remain separate evidence fields. A complete raw Entry row derives `registration_pattern_id` from the exact `(framework, registration.kind, coverage_note)` modeled binding. The derived ID is part of `entry_id` semantic identity and survives strict serialization; an unmodeled complete note is an error, not generic registration-kind coverage.

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

The complete normalized prompt, response schema version, model settings, raw response body, parsed response, and content hashes are retained for audit. Authentication material is excluded. Cache hits are replayable only from a private, HMAC-authenticated, atomically published cache entry containing the same bounded raw response and parsed contract; old cache schemas are not reusable.

P0 flow sources use real Spring MVC, Servlet, Netty, and MQTT qualified APIs. Global data-flow may prove supported callable paths, but unproven multi-wrapper, field/alias, reflection, custom dispatch, loop/fan-out or submission-count semantics must be emitted as partial coverage rather than upgraded from expression-string matching.

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

Lifecycle screening is path-bound: every usable Guard, Bound, or Release row is emitted as `LifecycleEvidence(entry_id, growth_id, path_id, growth_anchor, candidate_location, canonical_resource_identity, cfg_relation, coverage)`. Every relevant path/family also has a `LifecycleCoverage` row. Absence is valid only for that exact path/family when an explicit modeled-domain coverage witness is complete and it has no linked candidate; candidate-query zero rows alone never prove absence. Partial/unsupported/ambiguous CFG, alias, receiver, or configuration evidence is `unknown`. Global same-name receiver/key matching is forbidden.

## 9. P0 Assertions

### 9.1 Assertion 1: unbounded direct growth

```text
proven E->G
and attacker controls direct size demand, or proven single-request loop/batch/submission amplification
and verified growth
and no effective Guard
and no effective Bound
```

This primarily covers input materialization and direct allocation. A single `put(key,value)` or `submit(task)` is not amplification; container or asynchronous-work growth requires separately proven loop/batch/submission multiplicity.

### 9.2 Assertion 2: persistent accumulation without Release

```text
ordinary-attacker reachability proven by constrained security evidence
and proven repeatable E->G
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
- no candidate-relevant coverage gap;
- stable reason codes.

The same proof gate protects both `static_vulnerable` and
`bounded_under_modeled_assumptions`: complete Entry coverage,
ordinary-attacker Reach, verified Growth, proven flow, complete lifecycle
coverage for every applicable assertion, and candidate-relevant gap freedom are
all mandatory. Missing any obligation downgrades either determinate conclusion
to `static_unknown` and appends every exact missing `VERDICT_*` reason. An
already unknown conclusion remains unknown and may receive those audit reasons;
it does not acquire modeled-bounded assumptions. When the gate actually
downgrades `bounded_under_modeled_assumptions`, it removes the contradictory
`STATIC_EVIDENCE_COVERAGE_COMPLETE` assumption. Evidence-backed
`MODELED_DEFAULT_CONFIGURATION` and modeled configuration references are
preserved. There is no bounded-result bypass. It is a static conclusion under
stated assumptions, not a dynamic safety proof. Implementing this design requires
updating the active project instructions, README, schemas, existing static
aggregator, and dynamic-validation scaffold validators so they use the new
vocabulary consistently. No legacy `static_safe` compatibility mode will be
retained.

## 11. Coverage Model

Every run writes framework coverage records:

```json
{
  "framework": "netty",
  "status": "complete|partial|unsupported",
  "supported_patterns": [
    "entry-registration-coverage:netty:pipeline_registration:netty_pipeline_registration"
  ],
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
- retry TLS EOF and timeout/temporary/reset/aborted/remote-EOF conditions;
- retry direct HTTP 429 and all 5xx responses;
- retry errno-less proxy/tunnel messages only when they report
  408/425/429/500/502/503/504;
- treat DNS `EAI_NONAME`, certificate verification, permission failures, and
  `EINVAL` as permanent network errors;
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

The real fixture database helper must not execute CodeQL or javac against the
mutable fixture checkout or a writable cache tree. It captures a bounded,
content-addressed Java byte snapshot. Each directory is first consumed through
streaming `os.scandir(fd)` while incrementing the global 65,536-entry counter;
the bound is enforced before that already-bounded list is sorted by encoded
entry name. Deterministic traversal therefore cannot use an unbounded
`sorted(os.scandir(...))` materialization. The helper prepares its cache root
through a pinned lexical parent dirfd: `mkdirat`, no-follow `statat`, and
`openat(O_DIRECTORY|O_NOFOLLOW)` establish the current-uid directory binding;
only that opened fd may receive `fchmod(0700)`, after which the fd, parent-
relative name, lexical name, and parent inode are all rebound. A symlink or
same-uid pathname substitute is never chmoded as the cache root. A new source candidate is created at its
final, unpredictable `<digest>.sources-<128-bit-nonce>` name; after that root
has been successfully opened with `O_DIRECTORY|O_NOFOLLOW` and rebound,
authoritative snapshot mutation and materialization use the pinned root and
verified parent-relative fds. The exact Java tree is reduced to owner-only
read-only `0500` directories and `0400` files. The candidate is never renamed
to a shared `<digest>.sources` alias. Additional lexical validation may reopen
the root with `O_NOFOLLOW` and rebind it. From a successful pin onward, a later
mode-`0000` or other lexical substitute receives neither snapshot bytes nor
chmod through the authoritative mutation path, and a detached pinned root is
retained or causes a safe failure. The same-uid unique-name-creation-to-pin and
descendant `mkdirat`-to-`openat` substitution windows are not claimed as hard
creation-identity guarantees; closing those windows requires credential or
mount isolation, or a stronger filesystem primitive.

While holding the digest lock, reuse performs a descriptor-pinned streaming
scan of at most 4,096 cache-root entries and accepts at most eight exact digest
candidates. Every exact source candidate must pass no-follow, full-tree,
owner/mode/identity/byte validation with the existing 65,536-entry and source-
size bounds; malformed or invalid candidates fail closed without mutation.
When multiple exact valid candidates exist, lexical byte order selects one
deterministically. CodeQL creates a database directly at its final
`<digest>.db-<128-bit-nonce>` path without `--overwrite`; there is no temporary-
directory-to-digest-alias rename. A later helper uses the same bounded scan,
validates every exact database candidate and its source-root provenance, and
deterministically reuses the first valid candidate. Database provenance is
therefore bound to the selected stable random source path. Neither
`<digest>.sources` nor `<digest>.db` is a normal consumable alias or a legal
helper-cleanup leaf; obsolete `.sources.tmp-*` and `.db.tmp-*` staging names are
also illegal. Candidate-shaped names are never treated as proof of trust by
themselves.

Per-digest lock creation also uses the pinned parent: an existing inode must
already be a current-uid regular single-link `0600` file, while fchmod is
permitted only for a newly `O_EXCL`-created inode after its type/owner/link
gate. After `flock`, the lexical name and descriptor are rebound before the
critical section may run, so a substitution completed before that rebind
cannot enter the critical section. This named flock serializes cooperating
helpers only; it is not a hard lock against same-uid replacement of the lock
name after a helper has entered its critical section. The selected source root
is opened with
`O_DIRECTORY|O_NOFOLLOW` and remains descriptor-
pinned for the CodeQL build. Because `subprocess` does not accept an integer
directory fd as `cwd`, the child uses `/proc/self/fd/<dirfd>` with that fd in
`pass_fds`; `--source-root=.` is therefore resolved from the pinned cwd rather
than a mutable lexical path. The javac classes directory follows the same
capability discipline: `mkdtemp` creates a private `0700` name inside the
pinned cache-root dirfd, the helper immediately opens it with
`O_DIRECTORY|O_NOFOLLOW`, and fd, parent-relative, lexical, uid, mode, and
cache-root identities must all agree. The cache-root and classes-leaf opens
both reserve a structural owner slot and preallocate a mutable close-once
transaction before `open_owned_descriptor`; factory failure and normal cleanup
release the classes leaf and then the cache root through nested caller-local
`try/finally` pairs. A profile/trace callback or `SIGINT` at either owned-open
return or first release call therefore cannot leak an fd, and a consumed
transaction cannot reclose an ABA-reused number. Before the classes factory
returns, a deferred transfer places the complete pinned object in an empty
caller-owned slot. `_build_database` establishes its outer `try/finally` before
that call and drains the slot through an idempotent paired cleanup helper; if a
profile return event prevents the caller-local assignment, the slot still owns
both descriptors and the exact legal classes name. A transferred factory does
not also perform local cleanup, while a normal return must prove slot/object
identity before use. Once both close transactions are consumed, slot cleanup
only clears ownership and never repeats name/fd cleanup. Only `fchmod(classes-fd, 0700)` is
permitted; lexical `Path.chmod`/`os.chmod` is forbidden. Both source and
classes fds are included in `pass_fds`. CodeQL's trace-command intermediary
does not preserve the classes fd into javac, so javac `-d` uses the equivalent
live helper-process capability `/proc/<helper-pid>/fd/<classes-fd>` rather than
a mutable lexical path or a grandchild-local `/proc/self/fd` alias. That
capability and every classes binding are verified before and after the build,
and cleanup may act only on the captured classes identity. A lexical classes
swap must fail closed without changing the substitute's mode or bytes. Before
and after the build, and before the stable
database candidate is returned, the helper requires the lexical source root to
bind the pinned inode and
the exact full tree to retain every inode/owner/mode/size/mtime/ctime/byte value
with no extra node. It also closes the original pinned fd once and revalidates
database provenance before reopening and rebinding the same immutable state,
so persisted CodeQL metadata cannot depend on a live `/proc/self/fd` alias.
Root A-to-B-to-A swaps, file replacement-and-restore, and transient node add-
remove therefore fail closed, detach failed helper-owned DB/classes from normal
consumable names, and retain them as tombstones. Cleanup does not chmod the root
or any child node: a same-uid actor can make an unrelated inode occupy even the
legal helper-shaped name before cleanup, so provenance cannot be inferred from
name, uid, or an opened descriptor alone. Privacy comes from the already pinned
owner-only `0700` cache-root boundary; all retained modes remain unchanged.
Bounded tree inventory is read-only: directories/files are opened
relative to pinned parents with `O_NOFOLLOW`, must retain discovered inode,
current uid, supported type, and a single link for regular files, and are
rechecked before descriptor release. Identity drift, symlinks, foreign nodes,
special files, and hard links fail safely.
Destructive cleanup must not close the verified root and then call lexical
`shutil.rmtree`. It pins the owner-only cache-root dirfd and atomically moves
the exact current legal leaf to an auditable same-parent
`.<legal>.retained-<dev>-<ino>-<nonce>` tombstone with
`renameat2(RENAME_NOREPLACE)`. A quarantined identity mismatch is never
traversed: an unambiguous substitute is restored to the legal name with another
no-replace rename, while ambiguous state is retained inside the private cache
and fails closed. The exact root is opened and rebound at the retained name but
never chmoded. Even an exact
matching quarantine is never passed to
`unlink`, `rmdir`, recursive deletion, or chmod: Linux has no inode-conditional
unlink primitive that remains safe against a same-uid actor holding a parent or
root dirfd and swapping the last name after its final stat. The complete
owner-only quarantine is therefore deliberately retained after descriptor/name
revalidation. Recreating the original legal name preserves that replacement and
turns cleanup into an error rather than a second cleanup attempt.

Retention admission is helper-cooperative, bounded, and fail closed. A private
`0600` global cleanup flock serializes all digest cleanup operations. Under that
lock, the helper admits at most 64 observed audited tombstones, 1 GiB observed
aggregate logical `st_size`, and 65,536 observed inventory entries. Reaching
the count budget or exceeding the size, entry, depth, owner, type, link-count,
audited-name, or identity contract prevents another helper cleanup; if a newly
isolated exact root itself crosses the observed budget, it is no-replace-
restored to the legal name only when that rollback is unambiguous. Each audited
root name is rebound after its inventory before the observation is accepted.
The pinned cache-root stable identity is also captured before and after the
complete namespace inventory; any concurrent add/remove, replacement, mode, or
metadata drift rejects the observation rather than admitting an incomplete
cooperative count/size budget.
These are admission budgets for cooperating helper operations, not a filesystem
quota against a same-uid process retaining fds and mutating files or names after
the last observation; an adversarial hard cap requires a filesystem quota,
different credential, or isolated mount. No online or automatic GC mutates or
deletes retained or unknown inodes.
Manual reclamation requires a quiescent external boundary: after all fixture
processes using a dedicated temporary root have exited, the operator may remove
the entire dedicated `$TMPDIR/dosweb-fixture-codeql`, but must not delete
individual tombstones while the helper is active. These tombstones contain only
artificial fixture databases, classes, and source snapshots; formal target
bounded slices never enter this test cache.
This is a test-harness/cache contract only; it changes no formal stage artifact
and requires no production fingerprint rotation.

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

> **2026-08-18 P0.1 amendment.** JAX-RS and gRPC entry modeling are no longer
> deferred: they are covered by the explicit P0.1 extension in section 19 with
> the same fail-closed three-value verdict semantics. WebSocket, arbitrary custom
> protocol dispatch, and reflection-based registration remain deferred and must
> stay `partial`/`static_unknown`.

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

### 2026-08-17 implementation clarification: formal entry-to-growth evidence

A formal P0 flow must use real framework qualified APIs and a CodeQL global data-flow witness. Source-order proximity is not an association proof. Candidate/entry association is a distinct artifact: only complete call-graph association permits a Growth Contract; ambiguous or unsupported association emits partial coverage and must remain `static_unknown`. For Netty, `initChannel` plus `addLast` alone is partial; a supported `ServerBootstrap.childHandler` or `handler` installation is required for complete registration. A submitted task value is not evidence that the attacker controls submission count; a loop or batch-count witness is required.

## 19. PoC-33 Recall Hardening / P0.1 Extension (2026-08-18)

This section hardens the analyzer for the PoC-33 true-positive recall without
changing the P0 core model. The fixed formula, phase order, three-value verdict
(`static_vulnerable` / `bounded_under_modeled_assumptions` / `static_unknown`),
and fail-closed semantics are unchanged.

### 19.1 Scope split

- **Track A — approved P0 support-domain repair.** Fixes confined to the already
  approved Spring MVC, Servlet, Netty, and MQTT entry families plus the shared
  pipeline (configuration traversal, decoder diagnostics, bounded-slice
  redaction, formal entry-query selection, entry interposition, bounded
  interprocedural E→G). These are P0 repairs, not extensions.
- **Track B — explicit P0.1 extension.** Adds JAX-RS, gRPC streaming, Armeria,
  and Solr form pre-handler entry modeling as an *explicit* amendment. It does
  not silently widen P0; anything not provable remains `partial`/`static_unknown`.

### 19.2 Remote LLM authorization (corrected wording)

The only hard gates for a remote Growth/Auth call are: explicit
`allow_remote_llm`, a non-empty API key resolved from the gitignored local
secrets file (environment override allowed), and a readable, traversable local
`source_checkout`. `public_source_url`, `source_commit_sha`, `verified_public`,
and `verified_clean_checkout` are optional audit metadata only — they are never a
scheduling or call-permission gate. Secret configuration values must never be
persisted, transmitted, or placed in a prompt; bounded-slice redaction applies
before any remote call.

### 19.2a Track A interposition and bounded-flow boundaries

- `FilterRegistrationBean` interposition may bind a source-defined filter to a
  Spring handler only through a constant URL mapping and a unique normalized
  registration identity. A static order value is recorded but does not prove
  pre-auth execution. Until CFG action-before-chain is proven, the fact remains
  `partial` with `phase=unknown` and cannot by itself verify Growth or change a
  verdict.
- Filter-to-Growth call associations resolve only concrete source methods or one
  unique source-defined implementation within depth ≤ 3. Multiple
  implementations, reflection, custom dispatch, and deeper paths emit no
  complete edge. Any cross-call association/flow remains `partial` unless its
  full path coverage is independently proven.
- G1 recognizes bounded read-all APIs (`readAllBytes`, Hutool/Commons/Spring
  equivalents) and source-defined `HttpServletRequestWrapper` reader-loop /
  `StringBuilder` materialization. These are screening facts only; entry
  coverage, attacker flow, content-type predicates, and effective bounds remain
  independent proof obligations.

### 19.3 Track B complete/partial boundaries

- **JAX-RS**: `javax/jakarta.ws.rs` class/method path synthesis, HTTP verb,
  entity/InputStream/multipart parameters, `@PermitAll`/`@RolesAllowed`, and
  source-defined resource registration with a unique application/package
  registration are `complete`. Auto-scanning or dynamic registration is
  `partial`.
- **gRPC streaming**: generated `*ImplBase` overrides, `bindService`/`addService`
  registration, and unary/client/server/bidi streaming method identity are
  `complete` when the service is uniquely bound. Unproven concurrent-stream
  multiplicity, interceptor/auth, or ambiguous server registration stay
  `partial`/`static_unknown`.
- **Armeria**: annotated-service registration bound to a specific handler method
  is `complete`; a shared request-aggregation candidate linked ambiguously to
  multiple routes is `partial`. Decompressed-size bounds remain `unknown`.
- **Solr**: a Servlet/Jetty `application/x-www-form-urlencoded` parser running
  before the business handler is an interposition fact; `formdataUploadLimitInKB`
  is an effective Bound only when default configuration, current path, and
  pre-parse rejection are all provable.
- Reflection, unresolvable dispatch, and asynchronous Release capacity remain
  `partial`/`static_unknown` and are never promoted to `complete`.

### 19.4 Truth independence and chain-level disposition

Ordinary scans never read PoC truth. Dynamic truth is consumed only by the
benchmark/post-hoc recall stage, where each of the 33 records receives a
chain-level disposition spanning entry → growth → association → flow →
lifecycle/certificate → finding, with an explicit reason code and the furthest
reached stage. String route markers are secondary diagnostics only; the primary
match uses canonical repository identity plus entry and sink/growth identity.

### 19.5 Artifact and version impact

New artifacts: `entry_gap_facts.jsonl`, `entry_interposition_facts.jsonl`,
`configuration_coverage.json`, and benchmark-only `truth_dispositions.jsonl`. Entry registration/event, Growth
operation, and reason-code enums are extended; the four core Growth kinds and the
three-value verdict are unchanged. LLM audit adds original/transmitted excerpt
hashes and redaction metadata without storing the original secret. Query
diagnostics keep the safe contract reason. This amendment raises the artifact
schema to **2.5** and the tool version to **0.4.0**; legacy 2.4 artifacts are
preserved but are not resumable.

## 20. PoC-33 Evidence Funnel Repair / P0.2 Extension (2026-08-26)

This extension approves the evidence-funnel repair without changing the fixed
v2 vulnerability formula, ordered analysis phases, three static verdicts, or
formal fail-closed behavior. It supersedes only the implementation versions and
artifact contracts amended below; sections 1–19 remain authoritative for all
unchanged behavior.

### 20.1 Candidate relevance precedes finding publication

Raw CodeQL Growth screening output is not finding-eligible by itself. Every
Growth candidate receives a deterministic disposition before LLM classification
or finding publication. Rejected and demonstrably non-entry-reachable candidates
remain inventory evidence and do not generate lifecycle certificates or static
findings. Candidate-relevant partial evidence remains eligible only for an
explicit `static_unknown` gap path.

### 20.2 DoS Growth Contract

Growth Contract v4 adds attacker value-space, growth function and unit,
retention, pressure, amplification, failure mechanism and signal, contract
status, and rejection-reason fields. Collection mutation or allocation alone is
not proof of DoS-relevant Growth. Deterministic verification must bind every DoS
claim to bounded static facts; free-form model prose never replaces source-backed
evidence.

### 20.3 Candidate-relevant partial evidence

Partial association, flow, reachability, configuration, or lifecycle evidence
continues to force `static_unknown` when the candidate has first been shown
DoS-relevant. Generic unresolved screening candidates do not create an unknown
finding cross product. Unsupported custom dispatch, reflection, depth overflow,
and asynchronous Release capacity retain concrete coverage gaps and remain
`static_unknown` where a candidate-relevant chain exists.

### 20.4 Path-exact certificates and deterministic families

Lifecycle certificates and `static_findings.jsonl` remain exact to Entry,
Growth, flow path, and lifecycle evidence. Reporting may additionally publish
strict deterministic finding families for actionability and deduplication.
Family aggregation must retain every member finding and certificate identifier,
must not merge different resource, reachability, deployment, or verdict
identities, and must never use benchmark truth to choose a primary member.

### 20.5 Truth-independent static-only operation

Ordinary `entries`, `analyze`, and `full` execution remains static-only and may
not read PoC labels, dynamic cases, benchmark dispositions, or post-hoc scores.
Dynamic evidence is accepted only by the explicit read-only benchmark evaluator
after static artifacts are complete, and it never rewrites production output.

### 20.6 Version and resume boundary

This extension raises the artifact schema to **2.6**, the tool version to
**0.5.0**, and the Growth Contract response schema to
`growth-contract-schema-v4`. All six production stages use new
`production-v2.6-poc33-demo-repair-*` implementation fingerprints. Schema 2.5
artifacts and manifests remain immutable historical inputs but are not reusable
by a formal 2.6 resume.

## 21. Open-World Candidate Maturation / P0.3 Extension (2026-08-30)

This extension supersedes section 20 only where the artifact, provider-contract,
candidate-maturation, lifecycle-coverage, and evaluator contracts below differ.
The v2 formula, ordered phases, formal CodeQL fail-closed rule, static-only
production boundary, asynchronous-Release restriction, and three public static
verdicts remain unchanged.

### 21.1 Open-world objective and truth independence

The 21-library PoC corpus is a set of positive seeds, not an exhaustive list of
all vulnerabilities in those repositories. Production analysis therefore does
not optimize for a closed list, does not read seed identifiers, and does not
label a finding `novel`, TP, or FP. Candidate discovery, proof construction, and
static conclusion complete before any seed comparison.

A read-only post-scan evaluator computes the seed difference and emits exactly:

- `seed_linked_static_vulnerable`;
- `novel_static_vulnerable`;
- `novel_bounded`;
- `source_proven_negative`;
- `unresolved_discovery`.

An unmatched positive seed is a recall miss; it does not turn an unmatched
static finding into an FP. A novel static vulnerable result remains a validation
candidate until independently reviewed or dynamically validated. The evaluator
never rewrites production artifacts. Every seed that does not link to a current
discovery, whether because it has no concrete analysis ID or because its
concrete IDs are absent from the current scan, receives one deterministic
seed-only `unresolved_discovery` row. That row has `seed_ids=[seed_id]`,
`seed_status` copied from the seed, `recall_miss=true`, and null finding,
Growth, disposition, and verdict fields. Analysis-backed rows always have
`recall_miss=false`.

The seed input may be ordinary benchmark `matches.jsonl` or PoC-33
`truth_dispositions.jsonl`. Linkage consumes only concrete `matched_finding_ids`
or `matched_growth_ids` (plus the equivalent ordinary matched-chain IDs) inside
one strictly normalized `owner/repository` scope. Entry-only ambiguity never
fans out to arbitrary findings. Identity precedence is exactly
`record_id > case_id > truth_id`; a present but malformed higher-priority field
is not skipped. Explicitly non-linking seed statuses, including `no_candidate`,
`stage_failed`, and `entry_only`, may not carry stale finding or Growth IDs. If
both concrete finding and Growth IDs are present, every resolved finding's
mapped Growth must be a member of the declared Growth set. The mapped set may
be a strict subset: one seed may legitimately declare multiple exact Growth
candidates while only one currently owns a finding.

`matched_*`, ordinary `chain`, and nested `candidate.finding/growth` are three
equivalent ID carriers, not untrusted fragments to union first. Each carrier is
shape-checked and checked for its own finding-to-Growth consistency before
union. When more than one carrier declares the same dimension, their nonempty
ID sets must be nested, allowing a matched multi-Growth superset plus an exact
chain/candidate singleton while rejecting disjoint or partially overlapping
conflicts even when every ID is absent from the current scan. Multiple carriers
must also form one connected equivalence graph through at least one shared,
compatible finding or Growth dimension; complementary novel fragments with no
common anchor cannot manufacture a chain through union. A seed with only one
carrier remains valid.

Concrete analysis IDs are globally single-repository within an evaluation,
even though lookup also uses normalized repository scope. Seed-side
concrete finding/Growth IDs participate in that global owner registry even when
the referenced analysis artifact is absent: multiple seeds in the same
normalized repository may cite one missing ID, but cross-repository reuse of
that missing ID is malformed rather than two independent recall misses.

The evaluator accepts only the three public static verdicts. A finding must
bind a same-Growth `formal_eligible` or `gap_eligible` disposition, and a gap
may emit only `static_unknown`; rejected/inventory dispositions cannot own a
finding. A rejected disposition has a nonempty proof list, every referenced
proof has a supported type and the same scope and Growth, and every proof row
is referenced by exactly one such rejected disposition. Formal, gap, and
inventory dispositions carry no proofs. Missing, orphaned, cross-Growth, or
untyped proofs are malformed, never unresolved negatives. Duplicate seed
identities, malformed ID lists, missing finding dispositions, illegal
disposition/verdict pairs, invalid repository aliases, inconsistent seed
status/IDs, or cross-repository ID reuse all fail closed with `ValueError`.

The output path must not exist. The evaluator builds a mode-0700 sibling
temporary directory and on Linux publishes it with
`renameat2(RENAME_NOREPLACE)`. The no-replace check is part of the atomic
syscall, so a racing file, empty directory, symlink, or other leaf is never
overwritten. If that syscall is unavailable, publication fails closed; there
is no check-then-`rename` fallback. Publication pins the resolved output parent
with a component-wise no-follow directory-fd walk before temporary creation,
so swapping any ancestor before the fd is pinned also fails closed. The output
parent must already exist as a trusted directory; the CLI never performs a
pin-before recursive `mkdir`, because a missing ancestor could be replaced by a
symlink and redirect directory-creation side effects into immutable input.
Temporary creation,
file writes, cleanup, destination checks, and `renameat2` are dirfd-relative;
they never re-resolve a mutable output ancestor. Parent identity drift before
publication is a controlled failure, so an ancestor symlink race cannot redirect
output into immutable batch input. Path-resolution and symlink-loop
`RuntimeError` conditions likewise return CLI status 2 without traceback.

### 21.2 Candidate maturation and negative proof

Every raw Growth candidate receives exactly one `candidate_dispositions` row
with one of four statuses:

- `formal_eligible`: complete local Growth screening and one complete canonical
  Entry association;
- `gap_eligible`: one canonical association exists, but a candidate-relevant
  Growth or association proof remains partial;
- `rejected`: a deterministic source-backed negative primitive is recorded;
- `inventory_unresolved`: no safe canonical promotion or rejection is proven.

High fanout is inventory ambiguity, not target failure. Generic unresolved
candidates do not synthesize Growth Contracts, flows, or findings. A rejected
candidate must reference `candidate_negative_proofs.jsonl`, whose typed domains
include server-controlled source, source-proven non-retained owner, finite
keyspace, generated/test-only code, guaranteed synchronous cleanup, effective
local bound, false Entry→Growth flow, and not-entry-reachable. Every rejected
disposition cites at least one same-Growth typed proof; formal, gap, and
inventory dispositions cite none. Proof evidence consists only of `fact:*`
identifiers from that Growth candidate's `candidate_evidence`, and reference
validation rejects cross-Growth proof or evidence reuse. For a rejected
disposition, the set of `negative_proof:*` identifiers cited by `evidence_ids`
must equal `negative_proof_ids` exactly: missing citations and undeclared extra
proof evidence are both malformed. Every formal/gap disposition has exactly one
link, and that link's reconstructed `(growth_id, entry_id, link_status)`
ownership must equal the disposition's
`(growth_id, canonical_entry_id, association_status)`; existence of a link ID
alone is insufficient. A `formal_eligible` disposition therefore requires a
complete link. A `gap_eligible` disposition may use a partial or complete link
according to whether the gap is association-local or Growth-local, but its
`association_status` must exactly match that link's status. In addition,
`gap_eligible` requires at least one explicitly partial dimension:
`local_growth_status=partial` or `association_status=partial`. A
`complete/complete` pair is valid only as `formal_eligible`; publishing it as a
gap is malformed at both the in-memory model and artifact-validation layers.
When deterministic relevance remains `dos_relevant_partial` despite a complete
canonical association, production records the unresolved obligation as
`local_growth_status=partial` rather than hiding it behind an all-complete gap.
Negative proof identity and evidence remain independent of benchmark labels.

Direct-allocation query rows that share one allocation site/resource identity
are normalized into one candidate, including multi-dimensional constructors.
For an `ArrayCreationExpr`, the query enumerates every explicit dimension with
`getADimension()` rather than inspecting only dimension zero. Each enclosing
loop is also a separate multiplicity obligation. The shared Growth/Flow
complete witness accepts only exact
`for (int i = 0; i < directAttackerIntParameter; i++|++i)` syntax with integer
zero initialization, one increment update, and no induction-variable or bound-
parameter write in the body. Container and async Growth must be the entire
expression of the sole top-level `ExprStmt`; Direct allocation additionally
admits only a simple `=` assignment whose RHS is exactly the allocation. That
exact witness emits a complete
`direct_allocation:attacker_controlled_loop_multiplicity_proven` row, while an
attacker-dependent or other enclosing loop outside this domain emits a partial
`direct_allocation:loop_multiplicity_unmodeled` gap row. Loop containment is
defined from the loop body to the allocation's enclosing statement and also
retains lexically nested lambda/anonymous-callable sites as incomplete
obligations. A generic condition-flow fact such as `attackerControlsLoop` is
not a complete multiplicity proof. Break/return/throw, argument or conditional
subexpressions, compound/derived assignments, compound or server-capped
conditions, conditional/multi-statement bodies, and nested callables remain
partial/unmodeled.

`EntryGrowthDomain.qll` consumes the same exact witness. Its size domain uses
`getADimension()` for every explicit array dimension. Its shared loop domain
binds the exact attacker parameter access as `iteration_count` for Direct and
exact request-local container Growth, and as `submission_count` for exact async
Growth. Therefore multi-dimensional, cardinality, and submission-count
candidates can mature a complete association only when real Growth,
Association, and Flow rows agree on the site, demand, Entry, and proof-carrying
path; callers may not synthesize a complete link.
`server_controlled_source` is therefore valid only when coverage is complete
and every normalized dimension/source note is one of the explicitly modeled
server-controlled fixed or server-metadata domains, with no multiplicity row or
gap. The presence of any attacker-backed, unclassified, partial, or
attacker-controlled multiplicity note forbids this hard negative. For example,
`new BufferedImage(width, 1, TYPE_INT_RGB)` retains the attacker-controlled
`width` dimension even though the fixed height row is also present; the merged
candidate cannot be rejected merely because one note is
`direct_allocation:server_controlled_fixed_size`. Likewise,
`new byte[1][width]` retains its second attacker-controlled dimension, and
`new byte[1]` inside an attacker-controlled or unresolved loop cannot be
rejected from its fixed element size alone. An unresolved loop bound remains
partial and statically unresolved.

For the exact modeled Netty JSON source-switch path, candidate association may
read the route carried by the bounded call path and bind only the matching route
alias. A route-free same-handler row may collapse aliases to the base
`netty_pipeline_registration` Entry only when handler identity, registration
site, Auth context, attacker-input identity, materialization phase, and every
link status are identical. Any mismatch remains ambiguous
`inventory_unresolved`; source proximity or partial-status averaging cannot
select a canonical Entry. The same handler-identity requirement applies to
generic duplicate-registration canonicalization: a shared application-level
registration site, such as one JAX-RS/Dropwizard Guice binding, MUST NOT collapse
distinct resource handlers or HTTP methods into one canonical Entry.

The Flow stage MUST consume the authenticated Growth-stage canonical
disposition/link mapping for every retained Growth result. A route-qualified
canonical link emits only that specific alias; a route-free same-handler link
canonicalized to `netty_pipeline_registration` emits only the base Entry pair.
Flow normalization MUST NOT expand a shared handler source location back into
sibling aliases and then downgrade them to partial. It validates all eligible
and non-eligible disposition/link ownership before normalization; duplicate,
dangling, wrong-Growth, wrong-Entry, or link-status mismatches are malformed
upstream evidence rather than filterable noise. Complete/partial association
statuses must equal their sole link status for every disposition, including
inventory and rejected Growth; missing/ambiguous dispositions retain only
their non-canonical schema shapes. Every formal/gap disposition MUST refer to
a retained verified/unresolved Growth result, even when no raw Flow row selects
that disposition.

Absence of an enclosing loop is not a negative primitive for async submission:
an ordinary attacker may repeat the Entry, so the candidate continues through
repeatability, queue-capacity, Growth Contract, and lifecycle analysis. Likewise,
request-local container ownership alone does not prove low resource pressure.
Source-backed attacker-controlled loop/cardinality evidence may establish
single-request Growth; otherwise the candidate stays unresolved unless a finite
cardinality/byte bound or another deterministic low-amplification primitive is
proved.

`ContainerGrowth.ql` must make this request-local branch executable rather than
leaving it as a downstream-only policy. For an exact local variable initialized
by a concrete `java.util.Map`/`Collection` allocation and used as the receiver of
`put`/`add`/`computeIfAbsent`/`putIfAbsent`/`merge` in a supported handler, the
raw row records the handler-qualified receiver, the local variable as
`field_path`, and `escape_scope=request`. An attacker-controlled enclosing loop
is necessary but not sufficient for `complete`. The selected zero-argument
allocation must be lexically outside the loop, its CFG node must dominate the
loop, and the exact local receiver must have no second access that could rebind,
alias, or pre-populate a different instance. The current P0 Map proof is complete
only for zero-argument concrete `HashMap.put` whose key is an exact `VarAccess`
to the canonical `ForStmt` induction variable; compound expressions, including
string concatenation carrying that variable, do not prove injective new-entry
growth. The current non-wrapping canonical loop domain is exactly
`for (int i = 0; i < attackerBound; i++)`, also accepting prefix `++i`:
`i` is a locally declared primitive `int`, its only initializer is the exact
integer literal zero, `attackerBound` is a direct `VarAccess` to a supported
annotated primitive-`int` attacker parameter, the condition is exactly
`i < attackerBound`, the sole header update is `i++` or `++i`, and the body
contains no other write to `i`. Byte, float, long, non-zero-initialized,
derived-bound, reversed/decrementing, and otherwise non-canonical induction
forms remain `partial`. A zero-argument concrete `ArrayList.add` on the same
stable instance has the required per-iteration `+1` shape only when its loop
also satisfies this same `canonicalAttackerBoundForLoop` domain. A generic
`attackerControlsLoop` witness is not sufficient for List cardinality:
attacker-referencing conditions can still be fixed, tautological, infeasible,
wrapping, or otherwise non-canonical. For example, a `count - 2` initializer
with `i < count` is at most two iterations, while a `count` initializer with
the same condition executes zero iterations; both remain `partial`. The
explicit fixed-two attacker-tautology condition
`i < 2 && count == count` and infeasible condition `i < count && false` are
also real negative fixtures and must remain `partial` without the
cardinality-proven marker. The List operation itself must be exact
one-argument append `add(E)` (`getNumArgument() = 1`); indexed insertion
`add(int,E)` is outside the complete shape and remains `partial` even in an
otherwise canonical loop.

For either supported shape, the call must also be statically proven to execute
exactly once per loop iteration: it is either the unbraced loop-body
`ExprStmt`, or the sole immediate statement of a braced loop body. Calls below
an `if`, `continue`, or early exit, and calls in multi-statement loop bodies,
remain `partial` with
`attacker_controlled_loop_per_iteration_execution_unproven`. Same-key or
compound-key Map writes use `attacker_controlled_loop_new_entry_unproven`;
fresh-per-iteration allocations use
`attacker_controlled_loop_instance_stability_unproven`. Only the complete note
`attacker_controlled_loop_cardinality_proven` may promote a request-local
candidate through relevance. Relevance checks one whole canonical coverage
note for exact equality; it never searches a concatenation of notes or accepts
prefix/suffix variants. The only accepted complete note shapes are
`request_local_container_write:<driver>:attacker_controlled_loop_cardinality_proven`,
where `<driver>` is `key_driver_unclassified`, `attacker_value_driver`, or
`value_driver_unclassified`, matching the complete query domain. This
cardinality witness derives from the
attacker-controlled loop, stable container, unconditional call, and exact
per-iteration `+1` shape; it does not require the stored key or value itself to
be an annotated attacker parameter. Other collection shapes and ordinary
one-shot add/put also remain `partial` and inventory/unresolved. Request
completion alone cannot reject any of these candidates.

### 21.3 Growth Contract v5 and safe correction

The current formal provider is RightAPI Responses at the canonical production
base URL `https://rightapi.ai/grok/v1/`, using model `grok-4.6`, non-streaming
`POST /responses`, and provider identity `rightapi_responses`. The former
RightAPI endpoint is no longer an accepted production endpoint. The base URL
and provider identity participate in Growth/Auth cache identity, while the base
URL also participates in formal model/stage identity; switching credentials
changes cache HMAC authentication. Therefore no RightAPI stage or cache is
reused by a fresh RightAPI formal run. Credentials remain restricted to the
process environment or owner-only gitignored `config/local_secrets.json`.

The provider response schema is `growth-contract-schema-v5`. The provider no
longer chooses `growth_kind`, `resource_dimension`, or a free attacker-influence
structure. It returns `attacker_evidence_ids`; the analyzer derives the Growth
kind, resource dimension, and attacker target locally from bounded static facts.
Every cited identifier must belong to the current bounded slice.
Both the provider-only and locally bound typed models enforce the same strict
semantic invariant: `contract_status=dos_relevant` implies
`is_resource_growth=yes`. A `no` or `unknown` growth value paired with
`dos_relevant` is schema-invalid; it cannot become a negative/unknown Growth
Contract or a cacheable false negative.

The Growth prompt identity is `growth-contract-v9`; the provider response schema
remains `growth-contract-schema-v5`. Every initial/correction Responses request
uses strict `text.format.type=json_schema`, requires the exact 17 keys, forbids
additional properties, and constrains all enum/alias/collection/bounded-text
domains. The Growth provider wire schema is deliberately flat: it contains no
`oneOf`, `anyOf`, `allOf`, `const`, or conditional composition. Status-branch
consistency remains stated in both initial and correction prompts and is
enforced by the local typed schema/cross-field checks before acceptance. The
flat wire shape is a provider-compatibility boundary, not a relaxation of the
Growth conclusion gate, evidence ownership/binding, positive gate, or
raw-to-typed equality verification. Provider enforcement also does not replace
the bounded unique-key parser. If the
first response fails either strict
schema/local evidence binding (`LLM_RESPONSE_SCHEMA_INVALID`) or the layered
sensitive-response scanner (`LLM_RESPONSE_SENSITIVE_CONTENT`), the client may
issue exactly one safe correction request. The rejected body is unavailable to
that request and is never echoed, cached, audited, logged, or added to an error
message, details mapping, cause, context chain, or rejected-path traceback
frame local.

The provider-compatibility evidence for this boundary is explicit. The fresh
formal v30 three-target canary at
`results/java_web_dos_batch/poc33-schema27-jsonschema-strict-v30-20260902_163604-provider-canary`
completed formal Entry extraction for HertzBeat, ThingsBoard, and WGCLOUD but
all three failed atomically in Growth with `LLM_RESPONSE_SCHEMA_INVALID`; the
batch was `completed_with_failures` and no 21-target run started. Sanitized
owner-only diagnosis showed that Auth returned its complete four-key strict
shape, while Growth initial/correction replies returned only a small status
branch subset even though the request carried strict `json_schema`, all 17
required keys, `additionalProperties=false`, and the three-branch composition.
A source-free RightAPI A/B then held the same 17-field schema constant: the
composed `oneOf` form returned only five keys, while the flat form returned all
17 keys with a locally consistent unknown-status triple. No repository source
was included in that A/B. The subsequent fresh v31 three-target canary completed
3/3. Its first 21-target formal run completed 13/21 and failed eight provider
calls; a second fresh run was stopped after two more retry exhaustions and one
deterministic GROBID Flow failure. Growth v32 closes that local canonicalization
failure, and a fresh v32 three-target canary is required before another
21-target run. The 178/205 rollout remains paused.

The initial and correction prompts publish a deterministic
`attacker_evidence_options` list containing only aliased evidence IDs that the
local binder has already proven to be a `flow`/`driver_origin` source with one
exact attacker target. Provider output may select only an option's
`evidence_id`; the paired target remains local context and is never a response
field. An empty option list cannot support `dos_relevant`.
The correction prompt re-sends only the unchanged bounded slice and a
deterministic statement of the exact seventeen keys, status combinations,
unique exact `fact:<ordinal>` aliases, 16/32 evidence limits, and local
attacker-target binding, and makes `confidence=high|medium|low` mandatory. It
also forbids provider output for the locally derived
Growth kind, resource dimension, and attacker target. The final serialized
correction request passes the same fixed credential scan as the initial
request. Response-side `extra_secret_patterns` are never applied to either
outbound request; they run only after immutable response snapshot publication.
Before any typed Growth/Auth contract is constructed, one bounded canonical
response pass parses the outer Responses envelope, scans its decoded strings
and canonical key/value context with fixed credential rules, bounded-parses the
inner assistant JSON, scans every decoded semantic value and canonical
key/value context with fixed credential plus email/phone/SSN rules, and scans
the provider request ID with fixed credential rules. Growth semantic scanning
also retains source-echo detection. This ordering makes JSON `\uNNNN` escapes
irrelevant to the sensitive-content decision.
The completed envelope must contain exactly one assistant message. Its
`content` list has an exact protocol allowlist: every item is
`type=output_text` and has a string `text` value. A `refusal`, missing type, or
any unknown/future assistant content-part type makes the entire envelope
malformed and fails permanently as `LLM_RESPONSE_INVALID`, even when another
legal `output_text` part contains a schema-valid contract. This failure is not
contract schema/sensitive rejection, receives no safe correction, and cannot
publish cache or audit state. “Permanently” applies to that provider call: the
PoC-33 runner may make one new non-resume target attempt under its explicit
two-attempt ceiling, but the rejected envelope is never accepted or reused.
Rejected part payloads, including generic PII or
Growth source echoes, must not survive in exception chains or traceback locals.

A second schema or sensitive-response failure is terminal with its own stable
error code. The terminal error is reconstructed outside the rejected parser/
scanner exception handler with a fixed message and empty details; JSON parser
exceptions carrying the full input in `JSONDecodeError.doc` are not retained as
cause or context. Every Growth response attempt initializes and clears
`reply`, `content`, `request_id`, `actual_model`, and typed-contract references
before reuse and on failure. Malformed Responses-envelope parsing clears the
reply/body/envelope/parts references before raising a fixed error `from None`.
Other permanent response failures do not enter this correction path. Rejected
responses never enter cache or audit; a successful correction
audit binds only the actual correction prompt and accepted response. Network
retry bounds remain unchanged. In-process thread single-flight shares one
policy-neutral immutable accepted snapshot, not the owner's sensitive-content
decision. The in-memory live snapshot carries the syntax-validated provider
request ID in addition to the accepted body/contract metadata. Every waiter
applies its own API key and `extra_secret_patterns` to the decoded envelope,
decoded semantic values/canonical key-value context, and provider request ID.
It also reparses the raw inner contract, rebinds it through the current Growth
slice and fact aliases, requires exact `to_dict()` equality with the immutable
typed snapshot, and requires the raw actual model to equal the snapshot model
before emitting a replay audit; one
same-key flight still performs only one provider request. Header-only sensitive
policy failures are not shared as deterministic cross-client errors. The disk
cache retains only the authenticated request-ID digest, so disk replay uses an
empty request-ID value and never reconstructs or persists plaintext there.
When a disk-cache hit or an in-memory waiter rejects an accepted immutable
snapshot under its own body/request-ID policy, `_accept_growth_snapshot`
reconstructs one fixed unchained error only after dropping its snapshot
reference. Each caller also clears its local `cached_snapshot` or extracts the
waiter snapshot/error and drops its `state` reference before acceptance. A
rejecting waiter never mutates `state.snapshot`, because concurrent legal
waiters must still consume the same exact accepted body with one provider call.
Cross-process single-flight remains cache-backed.

An unexpected Growth cache-publication exception or false return clears every
reply/content/request-ID/model/contract/audit/snapshot reference before raising
one fixed `LLM_CACHE_WRITE_FAILED` outside the original exception chain. It is
therefore evaluated before any caller-specific snapshot policy and neither the
provider body nor the publication exception survives in traceback locals,
cause, or context.

Growth cache format/HMAC domain is v14. The v14 rotation prevents any v13 entry
whose identity bound the provider-incompatible composed Growth wire schema from
being replayed after the flat strict schema replaced it. The earlier v13
rotation prevented v12 records accepted before strict Responses JSON Schema
identity was bound into the cache key and authenticated record
from occupying the same immutable key. Each authenticated entry includes
exactly one `accepted_prompt_variant` enum (`initial` or `correction`). A cache
hit deterministically reconstructs that prompt variant from the current
digest-bound bounded slice and therefore emits the same `normalized_prompt` as
the fresh accepted audit. The variant is covered by entry hash and HMAC; it is
not caller-selected. The cache format itself participates in cache identity, so
v13 and older entries are cold misses under different keys rather than immutable
same-key conflicts. Typed-contract lookup and audit-payload replay must delegate
to one strict entry validator. That validator checks the exact top-level field
set, cache key/format/response schema/identity, identity/audit/raw/contract
hashes, request-audit semantics, prompt-variant enum, typed Growth Contract,
entry hash, and HMAC before either reader may return data. In particular,
request-audit `provider` and `protocol` are bounded strings and exact-equal the
corresponding cache-identity fields. Signed malformed entries cannot produce
asymmetric reader decisions. Provider transport and Growth cache raw responses
share one 131072-byte UTF-8 limit; direct oversize cache input produces a fixed
controlled error without response content. A production cache hit reads one
authenticated immutable snapshot containing the typed contract, exact raw
response, accepted prompt variant, and HMAC-bound actual provider model. It
does not reopen the cache path for audit data, and authorized model aliases are
preserved in replayed audit settings.

Cache hierarchy creation and existing-cache reads use the same root-to-leaf,
descriptor-relative `O_DIRECTORY|O_NOFOLLOW` walk.  After the final target has
passed its descriptor metadata check, that exact still-open descriptor is
structurally transferred to the cache caller; the caller must not discard it
and re-resolve the absolute path through `lstat`/`open`.  Thus an intermediate
foreign ancestor that renames the accepted current-uid anchor or replaces its
name with a symlink after validation cannot redirect lock creation or cache
reads.  A foreign-owned non-target ancestor whose group and world write bits
are both clear may be crossed only as a read-only namespace prefix; it is not a
trusted target and does not authorize creation below it.
After crossing such a prefix, a missing component may be created only after the
walk has opened an existing current-uid directory with group/world write bits
clear.  A foreign-owned sticky shared ancestor is stricter: creation remains
disabled until an existing current-uid exact-`0700` private anchor is opened.
Foreign-owned group/world-writable non-sticky ancestors and symlink components
are rejected.  The cache target itself always remains a current-uid exact-
`0700` directory under both metadata and opened-descriptor checks; these prefix
exceptions never relax cache-entry/lock exact-`0600` checks.

Capacity reservation and stripe single-flight extend that directory identity
through the complete cache transaction.  The outer lock scope stores a
thread-owned active directory record containing the pinned target fd and its
device/inode; reservation membership belongs to this record, not to a lexical
path/key marker.  Nested Growth/Auth lookup, capacity checking, and immutable
publication either operate on that fd or on a freshly duplicated fd whose
current-uid exact-`0700` metadata and device/inode equal the active record.
They never re-resolve the cache path while the transaction is active.  Thus an
anchor substitution cannot leave the capacity/stripe lock on one directory and
publish an entry to another.  Nested same-entry capacity reservations reuse the
same record; a different reservation or stripe acquisition in the wrong lock
order fails closed.  Active directory records are thread-local and carry the
owning PID and thread identity, so descriptors cannot be borrowed across
threads.  The same state object is also indexed in a process-global ownership
registry solely for descriptor lifecycle; nested cache authority remains in the
owning thread-local record.  This lifecycle index lets a child reset enumerate
and retire pinned directory descriptors inherited from every vanished parent
thread, not only descriptors owned by the thread that called `fork()`.  One
process-wide fork lifecycle guard covers active-directory open-through-register
and unregister-through-close, plus the equivalent flock open/register and
unregister/close transitions.  The at-fork `before` hook acquires that guard,
the parent hook releases it, and the child reset replaces it only after closing
the complete registered snapshot.  Fork therefore cannot observe an owned fd
in either the pre-registration or post-unregistration close window.  The same
PID/object-token registry and guard cover every transaction-scoped transient
cache capability: duplicated/opened cache-directory fds, authenticated entry
fds, and publication temporary fds.  Growth/Auth lookup and publication acquire
and register each capability before releasing the fork guard, unregister and
close it under that guard, and use raw descriptor writes rather than transferring
temporary ownership into an untracked file object.  Child reset closes the
complete active and transient snapshot inherited from every parent thread.
Descriptors that have been opened but are not yet in a process registry use one
central unregistered-descriptor retirement primitive at every hierarchy-walk
handoff, child/outer unwind, and unsafe-file rejection.  It performs the same
single PRE-only range fallback and never retries a POST/ambiguous close outcome;
raw descriptor close remains confined to that primitive, registered retirement,
and the child at-fork reset.

Lock-scope cleanup is a nested must-reach chain: an asynchronous failure before
or after the active-ownership predicate, or during unlock, cannot bypass flock
retirement, and flock retirement failure cannot bypass active-directory
retirement.  Growth/Auth publication cleanup has the same must-reach shape:
temporary-name cleanup failure cannot bypass retirement of the duplicated/opened
cache-directory capability.  Descriptor ownership remains registered through
the one-shot close action.  A specifically classified pre-action close failure
may use one bounded `closerange(fd, fd+1)` fallback while the fork guard still
excludes reuse; any post-action or ambiguous `BaseException` retires the PID/token
and must never retry that fd number.  Cleanup re-raises asynchronous failures
only after all later owners and thread-local/global registries have been retired.
Publication temporary names likewise have one mutable structural owner.  The
owner is retired before its sole destructive unlink attempt, because an escaping
exception cannot distinguish PRE from POST action.  Outer cleanup must not retry
that mutable name: an owner-only bounded temporary may therefore remain after an
ambiguous failure, including a competitor that reused the name, but it is never
deleted by a second attempt.  If the immutable destination link had already
succeeded, it remains the authoritative authenticated cache entry and later
lookup may consume it even though the interrupted publication call propagated
an error; any retained temporary continues to count against cache capacity.
Normal exit and exceptional exit retire the record and close its pinned fd
once, while the post-fork reset closes inherited flock and active-directory fds
before discarding child state.  Every flock descriptor also has an active
ownership record bound to its allocating PID and one exact ownership token.
Capacity/stripe unwind may unlock or close that integer only while the current
PID's registry still maps it to the same token.  A child-side unwind left over
from a parent context therefore cannot operate on an unrelated file that reused
the inherited descriptor number after post-fork reset.

`ContractCache` freezes a caller-supplied relative cache directory into one
lexical absolute path at construction time.  This conversion occurs exactly
once and must not resolve or follow symlinks; the descriptor-relative no-follow
walker remains the authority for component safety.  Path keys, hierarchy walks,
and entry transactions subsequently use only that frozen path, so a later cwd
change cannot make a transaction lock one directory and read or publish in a
same-named directory elsewhere.  Renaming an ancestor does not rebase the
lexical identity: an already pinned transaction continues on its verified inode,
while a later unpinned open of the now-missing frozen path fails closed.

### 21.4 Deterministic Auth and exact registration coverage

A unique, complete, semantically consistent set of source-backed Auth facts is
resolved locally into a high-confidence Auth Contract. Partial, absent, or
conflicting facts alone may invoke the provider. Local derivation does not reuse
an unrelated prior provider audit.

The remote Auth identity is `auth-contract-v5` with strict response schema
`auth-contract-schema-v3`. Every initial/correction Responses request uses
strict `text.format.type=json_schema`; the schema requires exactly four keys,
sets `additionalProperties=false`, and constrains the enum, alias, collection,
and bounded-text domains. The local bounded parser, typed schema validation,
alias ownership binding, and raw-to-typed equality checks remain mandatory.
The response has exactly four keys:
`auth_context`, `evidence_ids`, `assumptions`, and `confidence`.
`evidence_ids` and `assumptions` are JSON arrays (either may be empty), and
`confidence` is exactly `high`, `medium`, or `low`; scalar-to-array
normalization is forbidden. Auth content uses the same bounded unique-key JSON
parser as the provider envelope: duplicate members, non-finite constants,
oversize strings/collections, excess depth, and excess node count fail strict
schema before typed construction. If the first Auth response fails strict schema or
the unchanged sensitive-response policy, the client may issue exactly one safe
correction. That request contains only the unchanged aliased security and
configuration facts plus the deterministic four-key/array/enum invariants. It
cannot contain the rejected response or provider request ID. A second schema or
sensitive rejection is terminal with the original stable error code; transport
and other permanent errors do not enter this correction path.

Every returned Auth evidence ID must be an exact `security:<ordinal>` alias
owned by the current bounded security slice. An unknown alias is a strict
schema failure: the first occurrence enters the sole safe correction and a
second occurrence is terminal. Fallback preservation of arbitrary provider
identifiers is forbidden.

Before prompt construction, the caller Entry ID becomes `entry:1`; security
fact IDs and locations become deterministic `security:<ordinal>` and
`source/security/<ordinal>` aliases; modeled configuration IDs and source files
become `config:<ordinal>` and `source/config/<ordinal>` aliases. Configuration
input is first reconstructed through the exact `ModeledConfigurationFact`
schema, then only `config_id`, `key`, typed `value`, aliased `source_file`,
`source_line`, `profile`, `provenance`, `default_effective`, and `status` are
published. Arbitrary fields and original Entry/security/configuration IDs or
repository paths are not transmitted. Initial and correction payloads reuse
the same deterministic aliased objects, and authenticated replay reconstructs
the exact accepted prompt variant. Cache and in-process single-flight identity
also includes one non-forwarded SHA-256 ownership digest over the original
Entry ID and ordered original security/configuration semantic bindings. Only
that digest is stored in identity metadata; its preimage is never transmitted
or persisted. Replay accepts a de-aliased cached contract only when every cited
evidence ID belongs to the current security facts. Immutable snapshot
acceptance reparses the raw assistant JSON, constructs the provider Auth
Contract, rebinds every `security:<ordinal>` through the current
alias-to-original map, and requires exact equality with the authenticated typed
Auth snapshot before audit. A raw/typed mismatch, unknown alias, or raw/snapshot
actual-model mismatch fails closed without audit or provider fallback.

Every rejected Auth attempt clears response envelope/content/parsed-object,
request-ID, model, and typed-contract references before continuing or raising.
Rejected content is absent from cache, audit, error message/details,
cause/context, and rejected-path traceback frame locals. A successful initial
or correction response persists `accepted_prompt_variant=initial|correction`
and the bounded actual provider model inside private HMAC-authenticated Auth
cache v5. Replay validates that model against the requested model's authorized
aliases and preserves the actual alias in audit settings. Cache replay
reconstructs the exact accepted prompt variant, so fresh and replayed
normalized prompts agree; v4 and older Auth records are cold misses. Auth uses
a fixed exported `auth_cache_format=auth-contract-cache-v5` identity field;
the field participates in the Auth identity digest and cache filename. A real
HMAC-valid v4 record produced by the earlier Auth v4 prompt/schema/messages
therefore remains cold at its old path, while the v5 request selects a distinct
key and may call the provider and atomically publish the new record. Cold-cache
handling must not delete, rename, overwrite, or reserve the old record's path.
Auth uses a dedicated in-process single-flight map. Before its first provider call, the
owner reserves `auth-<identity>` capacity and holds that reservation through
immutable publication; capacity failure therefore performs zero provider
calls. A false cache-write return or unexpected publication exception clears
reply/content/parsed/raw/request-ID/model/contract/snapshot references and is
rebuilt outside the original exception chain as one fixed unchained
`LLM_CACHE_WRITE_FAILED`. Publication failure precedes caller-specific policy.
Before publishing any immutable snapshot/cache record, the live owner applies
the bounded canonical decoded-response pass described in Section 21.3 with the
actual transport API key and no caller extra patterns. The decoded outer
envelope and provider request ID reject credential assignments and
Bearer/API-key/private-key forms, JWTs, and credential URIs, but do not apply
generic email/phone/SSN regexes to ordinary provider metadata or identifier
strings. The decoded assistant semantic object receives the complete credential
plus email/phone/SSN policy; Growth additionally retains its source-echo check.
Thus a phone-like or numeric provider request ID is not PII
by shape alone, while a real phone/email/SSN emitted in assistant contract text
still enters safe correction and is terminal when repeated. An accepted raw
envelope, including harmless provider metadata, may be retained only in the
existing HMAC-authenticated `0600` cache/audit path. A repeated universal
sensitive failure is one shared terminal flight failure.
`extra_secret_patterns` remain caller policy and run only during
immutable-snapshot acceptance against the decoded envelope, decoded semantic
values/canonical key-value context, and in-memory request ID;
they never scan initial/correction outbound prompts and never enter the owner's
universal pre-publication decision. Every
owner/waiter also rechecks its own API key there. Thus a strict-policy owner may reject locally only after
the snapshot is cached and the flight is finished, while a lax waiter consumes
that same snapshot with no refetch. A custom-policy rejection clears only local
references, raises a fixed unchained error, and cannot overwrite the finished
state, delete the cache, or mutate the snapshot required by other waiters. One
Auth identity performs one provider flight; a successful fresh owner audit is
`cache_hit=false`, and waiter/cache replay is `cache_hit=true`.

Deterministic verification is not limited to the facts selected by the
provider. It re-evaluates every Auth fact for the current Entry whose identifier
belongs to the current bounded security slice. If complete facts map to more
than one of `unauthenticated`, `low_privilege`, and `privileged`, the verified
Auth context remains `unknown`; citing only one compatible fact cannot remove
the conflict or establish ordinary/privileged reachability. Any non-deployment
fact with `partial` or `unsupported` coverage in that same Entry/slice is an
Auth coverage gap: local derivation is disabled, provider selective citation
cannot hide it, and verification emits `REACH_AUTH_COVERAGE_PARTIAL` with
`auth_context=unknown` and `status=unknown`. Deployment-gate facts are excluded
from this Auth gap/conflict resolution and continue through the independent
deployment resolver, including partial deployment coverage. These Auth rules
first required growth-v5; the current Growth-stage implementation fingerprint
is v32. Growth v32 binds duplicate-registration canonicalization to a complete
same-handler registration identity; Growth v31 binds the flat strict 17-key Growth provider wire schema,
prompt v9, and cache/HMAC v14 while retaining local status/evidence/positive
validation. Growth v30 bound the composed strict Responses JSON Schema
identities and transient transport classification in Sections 14 and
21.3/21.4; Growth v29
added the candidate-link semantic-ID acceptance boundary. Growth v28 added
the pre-transfer non-cyclic weakref owner for the post-commit
`RETURN_VALUE` window, the explicit public-wrapper/internal-core first-opcode
boundary, and the formal-caller cleanup audit. Growth v27 added the post-
restoration-only factory success commit, first-structure standalone binding
reacquisition, and production-finalizer cleanup retry pair.
Growth v26 added execution-snapshot success-boundary rollback, standalone
binding reacquisition, and caller-owned fixture classes return handoff. Growth
v25 added outermost execution-snapshot cleanup coverage, persistent production-
workspace descriptor-chain release, and structurally owned fixture classes
cache-root acquisition. Growth v24 added the runner's caller-local
release pairs, cleanup-state ordering, exact raw-Growth/disposition bijection,
and descriptor-bound fixture classes output; v23 added the long-lived binding
direct-release lexical retry, v22 the caller-local owner-release lexical retry,
v21 the module-wide descriptor ownership migration, v20 the persistent-owner
release and pre-owner-open removal, v19 structural execution-snapshot
acquisition ownership, and v18 no-follow/deferred-close hardening. Growth v17 followed the positive
statement-shape whitelist, bound-parameter
immutability, and request-local-container/async count drivers were added to
v16's shared strict canonical-loop Growth/Flow witness and proof-carrying
dimension/iteration demands, which were added to v15's explicit array
dimensions and enclosing-loop obligations, on top of the v14 Netty
exact-route/base-registration association and mixed-dimension fixed-allocation
negative boundary, on top of v13 decoded
canonical response scanning, raw-to-typed snapshot equality, and the Auth alias rebind boundary
in this section, on top of Section 21.3's strict typed-growth/traceback-local
boundary and binder-eligible provider options. Formal resume cannot reuse
artifacts produced before any of these boundaries.

An Auth fact is recognized only by an exact `(kind, value)` allowlist:
annotation values require `annotation`, Servlet constraint values require
`servlet_constraint`, filter values require `security_filter_chain` or
`filter`, and configuration values require `configuration`. A value-shaped
string under `dependency_coverage`, a deployment kind, or any other mismatched
kind cannot support local derivation, create a conflict, or satisfy a provider
citation. Deployment resolution likewise consumes only facts for the current
Entry whose IDs belong to the current bounded slice; another Entry's gate
cannot change its status or evidence.

Modeled configuration indexing collects all default-effective known values for
each key before deployment evaluation. Duplicate values collapse only when
both their Python type and value match. Multiple typed values make the key
absent/unknown, independent of input order; in particular, boolean `true` and
integer `1` are distinct rather than equal aliases.

`EntrySecurity.ql` and its binder are fail-closed at the Entry boundary. A
concrete static route matcher binds to every normalized Entry whose route
semantically matches it; matching multiple Entries is expected fanout, not
ambiguity. A concrete matcher that matches no Entry cannot fall back to handler
identity. Only a missing or non-concrete route may use exact
`(handler_fqn, handler_file, handler_start_line)` fallback, and that identity
must select exactly one Entry. Source proximity and source-order fanout are
forbidden, and output is stable under row and Entry reordering.

Administrative Auth evidence is intentionally narrow. Auth annotations are
recognized only by an exact qualified-name allowlist: `javax`/`jakarta`
`annotation.security.PermitAll`, `javax`/`jakarta`
`annotation.security.RolesAllowed`, Spring Security `PreAuthorize` and
`Secured`, and Vaadin `AnonymousAllowed`. A project-local annotation with the
same simple name cannot publish Auth evidence. Only exact `ADMIN` or
`ROLE_ADMIN` annotation/Servlet roles, exact `hasRole('ADMIN')` (including the
double-quoted literal form), and exact `hasAuthority('ROLE_ADMIN')` (including
the double-quoted literal form) may publish complete privileged evidence.
`ROLE_USER`, mixed role sets, other authorities, and other expressions publish
partial `security_matcher_unknown`; substring or keyword heuristics cannot
establish privileged reachability. Likewise, `ConditionalOnBean`,
`ConditionalOnClass`, `ConditionalOnExpression`, and generic `@Conditional`
prove only condition presence, so they publish partial `optional` evidence and
cannot close deployment. `@Profile` is complete only for one simple positive
profile name matching `[A-Za-z0-9][A-Za-z0-9._-]*`; negation, conjunction,
disjunction, multiple distinct names, and other expressions stay partial. The
deployment resolver independently refuses complex profile facts even if an
older or malformed producer labels one complete. Any explicit partial
deployment fact suppresses synthetic `default_enabled` evidence for that
Entry, leaving deployment `unknown` rather than inventing a default.

`@ConditionalOnProperty` complete evidence requires one statically extractable
property name, one non-empty statically extractable `havingValue`, a statically
extractable prefix (the annotation default is the empty prefix), and
`matchIfMissing=false`. The canonical key is `name` for an empty prefix,
`prefix + name` when the prefix already ends in `.`, and otherwise
`prefix + "." + name`. The deployment resolver performs only this exact-key
lookup and never falls back to the unprefixed name. Multiple/distinct names,
unknown name/value/prefix, empty `havingValue`, or `matchIfMissing=true` publish
only partial `conditional_property_unknown` evidence.

Both `AuthContract.evidence_ids` and `ReachabilityDecision.evidence_ids` retain
their strict 32-ID bound. A locally derived unique Auth context cites the
lexicographically smallest supporting fact ID; the verifier still checks the
whole complete slice before choosing that representative. Reach evidence uses
a deterministic proof budget: first one smallest fact ID for every observed
Auth context in the fixed order unauthenticated, low privilege, privileged;
then one smallest complete deployment fact for every independently resolved
deployment-status bucket in the fixed order enabled, disabled, optional,
unknown; then sorted provider citations until the 32-ID limit. Deployment and
Auth resolution both run over all applicable facts before this evidence
projection. Thus high-cardinality duplicate facts cannot terminate analysis,
and evidence truncation cannot discard a conflicting Auth context or the facts
needed to distinguish deployment statuses.
When an Auth coverage gap exists, its lexicographically smallest fact ID is
reserved before Auth-context representatives, deployment-status
representatives, and provider citations, preserving the same 32-ID bound and
input-order independence.

Registration coverage uses an explicit framework-specific identity mapping for
Spring, Servlet/web.xml/filter, Netty, MQTT, JAX-RS, and gRPC. Substring matches
are forbidden. Every complete raw row derives an exact
`registration_pattern_id` from `(framework, registration.kind, coverage_note)`;
that ID is persisted in `EntryFact`, included in Entry semantic identity, and
stored as an exact ID in `coverage.json.supported_patterns`. Normalization must
not merge rows whose exact pattern IDs differ. Candidate coverage and lifecycle
certificate scope bind the current Entry's exact pattern ID, not the broad
registration kind. Conclude may mark Entry coverage complete only when that
same exact ID occurs in the authenticated framework coverage artifact; a
same-framework/same-kind sibling pattern, unknown complete note, dynamic
pattern, or missing exact ID forces `static_unknown` through
`VERDICT_ENTRY_COVERAGE_INCOMPLETE`.

Generic `CandidateCoverage` remains valid for framework-level accounting, but
every item in its non-empty `supported_patterns` is still required to be an
exact modeled registration-pattern ID belonging to that framework. Invented
IDs, cross-framework IDs, and broad registration-kind labels are invalid;
`unsupported_patterns` may continue to carry deterministic free-form gap notes.
A concrete lifecycle certificate has a stronger non-wildcard scope gate:
`coverage.registration_pattern_id == entry.registration_pattern_id`,
`coverage.entry_id == entry.entry_id`, and
`coverage.growth_id == growth.growth_id`. Generic coverage, a missing concrete
scope, or sibling scope cannot sign a certificate. `coverage.path_id` remains
optional for an Entry/Growth path group, but when present it must identify one
of that certificate's paths. Conclude artifacts produced before this gate are
not resumable under the conclude-v4 implementation fingerprint.

### 21.5 Assertion-scoped lifecycle coverage

Positive proof gates are evaluated per path and per applicable assertion:

- Assertion 1 requires complete Guard and Bound coverage only when Assertion 1
  is applicable;
- Assertion 2 requires complete Bound and synchronous Release coverage only
  when Assertion 2 is applicable;
- a `not_applicable` assertion does not require an unrelated lifecycle family.

After applicability scoping, the gate has no verdict-specific bypass. Any false
Entry, Reach, Growth, flow, applicable-lifecycle, or candidate-gap obligation
forces both a prospective `static_vulnerable` and a prospective
`bounded_under_modeled_assumptions` to `static_unknown`, preserving all exact
missing-reason codes. An actual bounded-to-unknown downgrade must also remove
`STATIC_EVIDENCE_COVERAGE_COMPLETE`; it may retain evidence-backed modeled
defaults and their references. A conclusion that was already unknown receives
missing reasons without manufacturing modeled-bounded assumptions.
`not_entry_reachable` is handled earlier as a maturation `rejected` disposition
with a same-Growth typed negative proof; it is not a reason to retain an
otherwise under-proven bounded conclusion.

Complete absence remains valid only inside an explicit modeled source domain.
Direct `ByteBuffer.allocate/allocateDirect` demand is a modeled Bound domain;
exact same-expression `Math.min(attackerDemand, positiveLiteral)` is emitted as
a path-bound `clamp` candidate only when the bound is a strictly positive
syntactic `IntegerLiteral` and the other argument is an exact source-modeled
attacker demand. The current P0 clamp domain accepts an exact `VarAccess` to a
`@RequestBody`, `@RequestParam`, `@PathVariable`, or `@RequestHeader` parameter
of a supported Spring handler. Constant expressions, constant variables
(including `static final` fields), server-derived non-constant expressions,
zero, negative, and constant-only `Math.min` forms cannot publish a complete clamp.
Accepted hexadecimal, binary, octal, and underscore-separated integer literals
are emitted as canonical decimal configuration values before deterministic Bound
evaluation.
Plain direct allocation can therefore prove
Bound absence, while an exact literal clamp refutes the unbounded premise.
Custom dispatch, reflection, unsupported allocation shapes, and uncertain
configuration remain partial.

### 21.6 Artifact and resume boundary

This extension raises the artifact schema to **2.7**, the tool version to
**0.6.0**, and the Growth Contract response schema to
`growth-contract-schema-v5`. Formal resume rejects schema 2.6/tool 0.5.0 stage
manifests. `candidate_entry_links.jsonl` is a formal semantic-identity boundary:
`evidence_ids` and `reason_codes` must each be nonempty, sorted, unique strings,
and `link_id` must equal `stable_identifier("candidate_link", semantic)` for all
fields except `link_id`. P0 aggregation validates this before trusted link
ownership/reconciliation, so a status, evidence, or reason mutation with an old
link ID is malformed even when a disposition ID has been recomputed. Production
fingerprints use `production-v2.7-open-world-maturation-*`; entries is v17,
growth is v32, flows is v21, lifecycle is v14, and conclude is v5. Growth v32
binds generic duplicate-registration canonicalization to the complete handler,
registration, Auth, attacker-input, and materialization identity, preventing a
shared JAX-RS application registration from selecting one of multiple distinct
handlers. These
rotations bind formal query execution and artifact acceptance to the structural acquisition ownership,
no-follow fd hardening, and deferred close-once semantics described in Section
22. The current rotation rejects source-line atomicity as an ownership boundary.
Before callback/parent-owner transfer, the factory attaches a non-cyclic
`weakref.finalize` owner to the returned `DatabaseInfo`; its callback captures
only the persistent `ExecutionDatabaseBinding`. This owner covers an opcode or
`SIGINT` escape after `factory_succeeded=true` but before `RETURN_VALUE` when no
external owner retained the object, while a registered production owner is
drained by the production finalizer's same-argument lexical pair. The public
cleanup wrapper has a distinct internal core: `dis.Bytecode` places the first
traceable public `NOP` at offset 2 before the exception-table start at offset 4,
so call-entry must-reach belongs to the caller's lexical pair; the callee only
guarantees its double input reacquisition after control enters the protected
body. The preceding rotation kept `factory_succeeded=false` through deferred
restoration, made standalone cleanup start with its owning `try/finally`, and
gave the production finalizer its cleanup retry pair. The earlier rotation bound
the success helper/next return boundary,
standalone input reacquisition, and fixture classes acquisition to a deferred
caller-owned return handoff. The earlier rotation bound the snapshot factory and
standalone cleanup to an outer lexical fallback before any owned parent can
escape, gives the complete production ancestry/output/workspace/results chain
one persistent reverse-order owner with paired workspace/family/Entry
finalizers, and moves fixture cache-root plus classes-leaf acquisition to
`open_owned_descriptor` with preallocated release transactions. The preceding
runner rotation bound the runner's ten caller-local descriptor-owner lexical retry
pairs, the execution-snapshot rule that commits `cleanup_state.closed` only
after cleanup/release `finally` coverage exists and the persistent parent
transaction is consumed, exact raw-Growth/disposition bijection, and
descriptor-bound fixture classes output. Lifecycle v2 previously followed the direct
allocation/typed-clamp modeled-domain change; growth v17 followed the positive
statement-shape whitelist, bound-parameter immutability, and request-local-
container/async count drivers were added to v16's shared strict canonical-loop
Growth/Flow witness and proof-carrying dimension/iteration demands, which were
added to v15's explicit dimensions and loop
obligations, on top of the v14 Netty exact-route/base-registration association and
mixed-dimension fixed-allocation negative boundary, on top of v13 decoded canonical response
scanning and raw-to-typed Growth/Auth snapshot equality. It
retains the v12 Auth v4 strict-array safe-correction/cache/single-flight
boundary and the v11 typed `dos_relevant => is_resource_growth=yes` invariant and rejected
Growth response traceback-local cleanup, plus the v10 binder-eligible
attacker-evidence alias options and mandatory correction confidence, the v9
per-waiter provider-request-ID policy validation,
the v8 unified response/cache
byte bound, policy-neutral thread single-flight snapshot, single-read cache
replay, and actual-model preservation, plus the v7
safe schema/sensitive correction, prompt identity, authenticated prompt-variant
cache replay, and exception-chain change plus the
earlier Auth conflict/selective-citation and partial/unsupported coverage-gap hardening.
Entries v5 followed the fail-closed EntrySecurity extraction/binding,
conditional-property, and qualified-annotation changes; flows v9 followed all
Flow upstream records became strict-schema inputs, every link/disposition
Growth identity (including inventory/rejected) became a member of the complete
raw candidate domain, and every duplicate normalized `path_id` began failing
before insertion independent of CodeQL row order; v8 rejected every duplicate
`verified_growth` owner for one `growth_id`, including identical records, before
constructing its map; v7 added
full-disposition association/link status validation and unknown eligible-Growth
rejection to close v6's non-retained reconciliation gap; v6 introduced authenticated
canonical disposition/link reconciliation so Flow could not re-expand Netty
handler-base or route-qualified aliases, on top of v5's
exact request-local-container `iteration_count` and async `submission_count`
demands joined v4's explicit-array/direct-loop shared proof-carrying
Entry-to-Growth domain on top of v3's Entry-exact registration coverage
boundary, and conclude v4 was the exact certificate-scope boundary. Conclude v5
adds the candidate-link semantic-ID acceptance boundary.
A formal resume may not reuse entries before v17, growth-v5 through growth-v31,
flows-v3 through flows-v20, lifecycle artifacts before v14, or conclude
artifacts before v5 even when
their schema/tool versions are already 2.7/0.6.0. Growth provider cache format
v14 authenticates the accepted initial/correction prompt variant, flat strict
typed-growth domain, strict response-format schema identity, and decoded-response/raw-to-typed acceptance
boundary; v13 and older records are not replayable. Auth cache format v5 likewise makes v4 and
older records cold, and the fixed Auth cache-format identity field places those
records under different immutable keys rather than turning a cold miss into a
same-path publication conflict. P0 batch aggregation includes
`candidate_negative_proofs.jsonl` and publishes
`aggregate_candidate_negative_proofs.jsonl`. Before a target contributes to an
aggregate, the aggregator reconstructs trusted fact ownership from Growth
candidate evidence and Entry security facts, reconstructs negative-proof to
Growth ownership, reconstructs each candidate link's
`(growth_id, entry_id, link_status)` ownership, and runs schema/reference
validation for every parsed JSONL artifact. It also requires an exact bijection
between the complete raw `growth_candidates` domain and
`candidate_dispositions`: every raw Growth has exactly one disposition, and a
missing, duplicate, or phantom disposition makes the target malformed. The
aggregator then reconciles the complete disposition/link graph without first
filtering to `formal_eligible` or `gap_eligible`: every link must belong to the
raw Growth domain, reference an existing Entry, and be cited exactly once by
the disposition for that same Growth. A `complete` or `partial` association
must own exactly one link whose Entry and status equal its canonical fields;
`missing` owns neither links nor a canonical Entry; `ambiguous` has no
canonical Entry and may not collapse to a sole-link canonical shape. Orphan,
cross-Growth, wrong-Entry, wrong-status, or multiply owned links make the target
`malformed`, never `completed`, including when the disposition is rejected or
inventory-only. This tightens only the independent P0 aggregate acceptance
boundary and does not change a formal stage artifact, so production stage
fingerprints remain unchanged.

The PoC-33 real-provider acceptance layer binds `model=grok-4.6`,
`base_url=https://rightapi.ai/grok/v1/`, `timeout_seconds=180`, `max_retries=5`, and
`allow_remote_llm=true` into the immutable formal full plan. Archive validation
requires exactly that five-field provider mapping; a digest-consistent plan with
any missing, extra, or different provider setting is rejected. These settings alter only
the network deadline/retry budget; they do not change strict response schemas,
local binder/ownership checks, selected CodeQL policy, or verdict gates.
Wrong-Growth/wrong-Entry eligible links, missing or extra disposition proof
citations, cross-Growth proof references/evidence, and provider/oracle-shaped
facts absent from the referenced Growth candidate fail the target as malformed.

The acceptance execution is one fresh `--no-resume` invocation with
`--retry-failed --max-attempts 2`. The runner initially queues every target
once. After a target attempt persists one of the existing explicitly retryable
authentication/provider-output/network error codes—including nondeterministic
`LLM_RESPONSE_INVALID` envelope rejection and provider-returned
`LLM_AUTHENTICATION_FAILED`—it may append that target once to the same in-process
bounded queue. Missing local credentials remain a non-retryable authorization
failure, and authentication errors still fail the current provider call
immediately; only the one bounded fresh target attempt may retry a provider-side
authentication rejection. The new target attempt remains non-resume: formal
stages are rebuilt, rejected responses were never cached or accepted, and only
prior schema-valid HMAC-authenticated cache entries may be replayed under the
normal cache contract. A non-retryable error or failure at attempt two is
terminal. Thus no already-terminated failed batch is resumed, while one
non-deterministic provider response cannot force a complete 21-target restart.
Archive validation requires each completed target to have an integer attempt
count in `[1,2]` and publishes the number of retried targets in the acceptance
manifest. This bounded orchestration does not change production stage artifacts
or fingerprints and does not relax provider schemas, local evidence binding,
the positive gate, selected CodeQL fail-closed behavior, or per-request retry
bounds.

## 22. Private CodeQL execution database invariant (2026-09-01)

`codeql query run` is a mutating operation: supported CodeQL releases may write
query-derived data below locations such as `db-java/default/strings/`.  Formal
identity therefore separates the immutable **canonical database** from a
private **execution database**.  `DatabaseInfo.path`, `source_root`,
`fingerprint`, stage fingerprints, batch plans, `run.json`, manifests, reports,
and resume decisions remain bound exclusively to the canonical database.  The
optional execution binding is in-memory state and is never serialized.

The output transaction starts before production preflight: while holding the
target output lock the pipeline loads or creates `run.json`, increments
`attempt`, and atomically persists `status=running`.  Only then may preflight
create the execution database.  Preflight-enriched canonical/query-pack
identity is atomically persisted again before any stage.  Consequently, an
unsafe stale snapshot or other preflight failure replaces an older
`status=completed` with `status=failed` for the new attempt.

Production preflight creates exactly one
hidden `.codeql-execution-*` root for the target pipeline.  The root is inside
the formal output root (never an independent `/tmp` allocation), mode `0700`, owned by the current uid,
and bound to its original path/device/inode until finalization.  All selected
queries in that pipeline share this one execution database.  Files are cloned
with Linux `FICLONE` only; unsupported reflink, quota/capacity failure, unsafe
tree content, or any clone race fails closed and must never fall back to a
byte-for-byte full copy.  Clone interruption by any `BaseException` also enters
the cleanup path; cleanup failure takes precedence.  A fixed `stale_cleanup`
error is propagated as-is rather than relabeled as clone failure.  Before cloning and after cloning, canonical and
execution trees reject symlinks, FIFOs, devices, sockets, foreign-owned private
entries, and observable inode swaps.  The canonical root and every nested
canonical entry must likewise belong to the current uid.  The initial execution fingerprint and
`sourceLocationPrefix` must equal the canonical fingerprint/source root, and
the canonical fingerprint/source root/path/inode are revalidated after the
clone.
Once the complete execution binding has passed those checks, the snapshot
factory must register it with the pipeline-owned finalization holder before
the factory returns.  Registration is part of the factory transaction, not a
caller-side assignment after `CALL`: an exception delivered at the factory
return event therefore cannot precede cleanup ownership.  Any `BaseException`
raised by the registration callback remains inside the factory transaction and
removes the private tree and closes its retained parent descriptor before
propagating.

The snapshot root descriptor and the retained snapshot-parent descriptor are
created only after a successful one-shot close-capability probe and after their
mutable `DeferredCloseFdOnceOutcome` transactions have been allocated. Before
either `os.open`, the factory reserves its descriptor's structural owner slot;
trace/profile callbacks and `SIGINT` delivery are deferred across the C return
and owner-slot write. Thus an exception at restoration or helper return finds
exactly one owner even when the caller-local descriptor assignment has not run.
The factory no longer calls `_tree_root_identity(output)` before capability
probing/ownership. Its first output-root open is the owned retained-parent
acquisition; `fstat` is authoritative, a no-follow lexical `lstat` must bind the
same device/inode/uid/mode, and stale cleanup receives that same pinned fd.
The parent slot transfers only after the complete binding and pipeline owner
callback exist; an exception before transfer releases the local slot, while an
exception after transfer releases through the binding, never both. Immediately
after constructing the owned `DatabaseInfo`, and before either the owner
callback or parent-slot transfer, the factory registers
`weakref.finalize(owned_database, cleanup_binding_callback, binding)` and disables
its interpreter-exit callback. The callback captures the binding, not the
`DatabaseInfo`, so it introduces no owner cycle. The success action performs
only the transfer and returns the binding; it never writes `factory_succeeded`.
The deferred call and the success commit remain inside an explicit
`try/except BaseException`, so restoration failure and an exception on the
handler line observe the original false flag without needing a vulnerable reset
statement. After the helper returns, `factory_succeeded=true` and the following
return are separate bytecode-bearing operations and are not claimed atomic. If
an opcode trace or `SIGINT` escapes after the flag commit but before
`RETURN_VALUE`, an unretained object unwinds and its GC finalizer drains the
binding; if the production owner callback already retained it, the production
owner/finalizer caller pair drains the same binding. Normal explicit cleanup
consumes that persistent transaction, making a later GC finalizer a no-op rather
than an ABA fd-number reclose. Root release and long-lived parent release execute inside deferred-interrupt
transactions. Owner release first reads `owner[0]` without removing it, executes
the persistent transaction to a proved consumed/released state, and only then
validates and clears that exact slot inside a second deferred-interrupt window.
If clear setup or restoration escapes, later cleanup uses the same committed
transaction to clear the remaining slot without retrying close. Repeated or
concurrent cleanup therefore never retries a consumed fd number after an
actual-close-then-exception or after that number has been reused for an
unrelated file.

The same structural rule applies to the complete
`dosweb/codeql/database.py` descriptor domain, not only the factory's first two
fds. Metadata byte/hash reads, `_tree_root_identity`, `_validate_safe_tree`
roots and recursive regular/directory children, `_assert_private_binding`,
reflink file/root/recursive source and destination descriptors, and private/
stale cleanup roots and children all receive one already-probed capability.
Each acquisition has an owner slot plus preallocated persistent release
transaction before `open_owned_descriptor`; nested two-fd paths release through
nested `finally` so one release failure cannot strand its peer. Every individual
owner release is itself expanded at the caller's lexical layer as
`try: release(owner, capability, transaction); finally: release(...)`; a
profile/trace exception or `SIGINT` at the first helper call/first line therefore
still reaches the second call. If the first call consumed the fd, the persistent
transaction and cleared structural owner make the second call a no-op, so an
ABA-reused fd number is never closed again. This pair is written explicitly rather
than hidden behind another helper whose own call boundary would recreate the
same interruption gap. Binding paths
reuse `ExecutionDatabaseBinding.close_capability`; standalone entry points probe
before their first descriptor. `database.py` contains no direct `os.open` or
`os.close`; the actual syscall is centralized in `dosweb/filesystem.py`, whose
owned-open primitive also carries the creation mode for `O_CREAT` reflink
destinations.

The factory-exception and final-cleanup sites that directly release a
transferred, long-lived `ExecutionDatabaseBinding.parent_descriptor` obey the
same caller-local rule. Factory cleanup now has one nested cleanup/release
transaction rather than separate success/failure release branches: private-tree
cleanup failure is retained for fixed-error precedence, while the parent owner
or transferred binding release is unconditionally reached through an explicit
same-argument `try/finally` pair. That parent-release `finally` is established
before retrying any still-owned snapshot-root descriptor, and private-tree
cleanup is itself nested in the snapshot-root release `finally`; an escape from
either snapshot release call therefore cannot strand the tree or parent fd.
The binding lock covers this complete path.
`cleanup_state.closed` is not committed until the tree-cleanup/release
`finally` layers already exist and the persistent parent transaction reports
consumed; the commit itself is a duplicated deferred-interrupt lexical pair.
Standalone cleanup is split into a public paired wrapper and an internal core.
The internal core's first body structure is the outer `try/finally`; there is no
pre-try binding initialization. Each of two nested core cleanup attempts reads
`database.execution` directly from a schema-valid input and never depends on the
body-local assignment. Once execution has entered the core's protected bytecode,
an exception on its first assignment line therefore still removes the exact
private root and consumes the parent transaction during the same public call.
The public wrapper duplicates the internal-core call in `try/finally`, but this
does not make the Python function-entry boundary self-protecting: disassembly
places its first traceable `NOP` at offset 2, outside the exception table whose
first protected range starts at offset 4. A call-entry/first-opcode exception can
therefore prevent the callee from running either attempt. Every formal owner
must supply the outer must-reach boundary; the production finalizer does so with
a caller-local `try/finally` pair around `snapshot_cleanup(database)`, and the
source audit rejects any additional direct formal caller. Call-entry or first-
opcode interruption of the first public call therefore reaches the second call,
and `owned_database`/`validated_database` are cleared only after both attempts.
Therefore a profile/trace
callback or `SIGINT` cannot combine `cleanup_state.closed=true` with
`parent_release.status=None` and a live parent fd, and a later cleanup may
return early only after release consumption. If the first call completed the
raw close or observed an actual-close-then-exception, the second call consumes
only committed transaction state and never retries an ABA-reused fd number.

With an execution binding, `run_query` passes only the private path to
`codeql query run --database`.  Before and after each query it validates the
canonical database exactly and validates the private root binding, ownership,
mode, source root, and absence of links/special files.  CodeQL may legitimately
change the execution fingerprint after its initial clone; this never changes
the canonical identity and does not invalidate later queries in the same
pipeline.  The resolved `output_dir` must be strictly outside the execution
root; equality or descendant containment fails at validation before any
subprocess or output creation.  Therefore every returned `query_path`,
`bqrs_path`, and `decoded_path` is outside the random private snapshot.
Publication revalidates canonical and private bindings after BQRS
hashing, after output-file fsync, immediately before `os.replace`, immediately
after `os.replace`, and after fsync of `.generations`.  Drift observed after
replacement first uses dirfd-relative Linux
`renameat2(RENAME_NOREPLACE)` to move the recognizable `Entries-<uuid>` leaf to
a hidden `.rollback-*` quarantine, verifies the inode, and fsyncs
`.generations`.  The verified quarantine is retained; rollback never traverses
or deletes it by its mutable hidden name.  Destination collisions retry with
another fresh hidden name.  Before exposing the normal
generation, publication first records an attempted/unknown replace transaction
containing the pinned pending name, normal generation name, and expected
generation inode, and marks rollback required before invoking dirfd-relative
`os.replace`.  No caller-side success boolean or assignment after the call is
authoritative: publication exceptions, housekeeping exceptions, descriptor
release failures, and the final rollback anchor reconstruct the replace result
from those pinned names and inode.  A transient reconstruction failure leaves
the transaction unresolved so the final anchor retries it before releasing its
last pinned descriptor.  Pending output is never destructively cleaned through
its mutable hidden name.  Once rollback has started, retries resume the
inode-bound rollback state directly because the generation may already have
moved from the normal name to hidden quarantine.  The pending generation is
created relative to the pinned `.generations` descriptor and retains its own
open directory descriptor and expected inode through final recovery.  It also
opens an independent descriptor for the same actual generation inode before
publication.  The primary pending descriptor may enter its one-shot release
only while this identity anchor and the final parent anchor remain live; an
actual-close-then-exception on the primary therefore cannot erase recovery
authority.  No pending cleanup may use path-level `shutil.rmtree`, enumerate
or unlink pending children, or call `rmdir` on the pending root.  If replacement
did not complete, recovery verifies the pinned owner-only pending descriptor
and its hidden-name binding, retains the pending generation intact, and
terminates with path-free `CODEQL_QUERY_FAILED`.  If replacement completed,
cleanup only verifies
that the old pending name remains absent.  A competitor that recreates that
name after an absence check is preserved and makes the transaction fail; it is
never traversed or deleted.

The final rollback anchor also owns an independent recovery path that does not
call the normal publication-state rebuild helper.  Persistent failure of that
helper therefore cannot strand the expected inode at the normal generation
name: final recovery revalidates the still-open actual generation descriptor,
reads the known pending/published names directly through the pinned parent,
then either proves an uncompleted replace and retains the expected pending inode
or starts/resumes inode-bound quarantine/exchange rollback.  The independent
actual-generation identity descriptor and final parent anchor remain live
through the final safe-recovery decision.  Recovery either proves twice that
the normal name no longer contains the expected generation inode, or
classifies an atomic-filesystem-primitive outage and leaves the bound leaf
untouched while the run fails.  Thus even a post-action exception from primary
pending-fd release combined with persistent normal rebuild failure still
enters direct recovery.  Both identity and parent anchors then use explicit
one-shot release outcomes; successful and failed transactions return to the
descriptor baseline and release the execution lock.

Final recovery never calls `rmdir`, `unlinkat`, or another deletion primitive
on the mutable normal generation name.  A normal name still bound to the actual
generation must first move atomically to a fresh `.rollback-final-*` name with
`RENAME_NOREPLACE`; a normal empty exchange placeholder must likewise first
move to a fresh `.rollback-placeholder-*` name.  After any rename exception,
including `FileExistsError`, both source and destination are inspected through
one transaction rebuild.  A collision retry is allowed only when the source
still contains the expected inode and the destination contains an unrelated
inode.  Commit is accepted only when the fresh hidden name contains the
expected inode and the normal name is absent.
If source substitution caused an unrelated inode to move to the fresh hidden
name, recovery uses `RENAME_NOREPLACE` to restore that inode to its original
normal name before failing.  Once the expected output inode has been isolated
and verified under any fresh hidden rollback/pending name, no destructive
namespace cleanup is allowed: recovery does not enumerate or unlink children
and does not call `rmdir` on that hidden root.  It retains the quarantine,
closes every owned descriptor, releases the execution lock, and terminates
with path-free `CODEQL_QUERY_FAILED`.  There is no raw normal- or hidden-name
`unlinkat(AT_REMOVEDIR)`, `rmdir`, or check-then-delete fallback.  Hidden
quarantine is not a completed generation and is never accepted by formal
resume or any consumer.

The production Entry executor and every `_run_codeql_family` caller keep query
results in a random owner-only hidden `.dosweb-<family>-queries-*` workspace
directly below the target output root.  Query-pack materialization may use a
separate ordinary temporary directory, but result ownership must not be nested
under `TemporaryDirectory`: unwinding such a context would recursively delete
the retained generation and any competing inode after `run_query` had already
failed closed.  Workspace creation probes the Linux one-shot fd-release
capability before opening any owned descriptor, opens the filesystem root and
then every lexical component through the output parent with component-relative
no-follow descriptors, and saves every parent/name/device/inode/uid/mode
binding.  The output leaf is opened relative to the final pinned parent.  All
ancestry components, the output leaf, workspace, and `results` directories are
revalidated as one chain; replacement of the output parent or any higher
ancestor therefore fails just like direct output-leaf replacement.  The query
workspace descriptor factory treats acquisition and ownership transfer as one
transaction.  Each directory open first reserves an owner slot, temporarily
disables Python trace/profile callbacks, and blocks `SIGINT` across the
`os.open` C-return-to-slot-assignment window.  Trace/profile and the prior
signal mask are restored through nested `finally` blocks only after the fd is
structurally owned.  The prior signal mask is first queried without changing
it; every `setprofile(None)`, `settrace(None)`, and `SIG_BLOCK` setup call is
already inside its matching restoration `finally` before the mutating call is
made.  A post-action exception from any setup or restoration call therefore
cannot leave trace/profile state disabled or `SIGINT` blocked.  All runner and
production descriptor acquisitions use reserve/deferred-owner primitives:
`os.open`, `os.dup`, and `tempfile.mkstemp` exist only inside their shared
factories, and the tempfile factory binds both fd and exact cleanup path before
return.  They are not duplicated at individual acquisition sites.  The
execution-query copy probes the one-shot close capability before acquiring its
source or destination descriptor.  After the complete copy is fsynced, both
descriptors release through a preallocated mutable transaction state.  The raw
close is followed only by allocation-free assignment into that existing state;
no result object, tuple, or holder is constructed between the close action and
its `RELEASED`/`POST_ACTION_EXCEPTION` commit.  A proved
`PRE_ACTION_FAILURE` or setup escape before the action may use the single
known-owner fallback, while a post-action exception never retries the fd number
and does not cancel transfer of the completed exact path to the caller.  Source
and destination owner retirement, shared-helper calls, state inspection, exact
path cleanup, and failure propagation are one outer deferred transaction, so a
shared-helper return event cannot split the two-descriptor loop.  Only committed
`RELEASED` or `POST_ACTION_EXCEPTION` state transfers the path; pre-action
failure uses the still-owned fallback exactly once, propagates the original
release failure, and cleans the untransferred exact path.  Caller
ownership therefore exists even when either close
actually completes and then raises, and the ordinary caller transaction removes
the exact tempfile; the helper must not hide such files under a retained
quarantine prefix merely to make the original glob empty.  The ancestry
factory likewise registers the complete
root-to-parent tuple in its caller-owned holder before its return event; holder
append and structural-membership confirmation run inside the same deferred
interrupt window.  Before that transfer only the factory-local descriptor
list may release ancestry fds, and after it only the caller holder may release
them.  Output, workspace, and `results` fds use a separate single owner list,
so every acquisition failure, callback exception, or deferred interrupt
performs one reverse-order one-shot release without an append/reset overlap or
fd-number retry.  Once those bindings form a complete workspace object, the
workspace factory registers that object in the formal executor's owner holder
before the factory return event.  Family and Entry executors enter their outer
cleanup transaction before invoking the factory, so an exception delivered at
factory return cleans the registered workspace through the holder even though
caller-side assignment never completed; formal ownership does not depend on a
destructor.

Before reading the query source, `run_query` probes and binds the one-shot fd-
release capability. Consequently no query-source, snapshot, BQRS, decoded-
output, pending-generation, generation, or publication-anchor descriptor can
be acquired when close-once semantics are unavailable. `.generations`
initialization, query-snapshot publication, and BQRS/decoded regular-output
hardening all use a common parent-dirfd helper: it opens the leaf with
`O_NOFOLLOW`, verifies type/current uid/link count/inode and the applicable size
bound, changes mode only through `fchmod(fd)`, and then rebinds the fd, parent-
relative name, lexical name, and parent. Direct path `chmod` is forbidden.
Runner-local descriptor owner lists are retired through preallocated
close-once outcomes under one outer deferred-interrupt cleanup. All ten
external `_release_descriptor_owners_or_raise` callers explicitly repeat the
same call in a caller-local lexical `try/finally`; there is no fallback wrapper
that recreates the call-entry window. A profile/trace interruption before the
first helper line therefore reaches the second call with the still-owned list.
If the first call succeeds, pops the persistent owner, or observes an actual
close followed by an exception, the second call sees retired ownership and
cannot close an ABA-reused fd number. An observed post-action exception commits
retirement and forbids retry of that fd number; only a proved pre-action
failure may use the single known-owner fallback.
Release, rebind, or hardening failure is a fixed path-free query failure and
cannot leave a normal completed generation.

The query output interface is
`/proc/self/fd/<results-fd>` instead of a reconstruction through the mutable
output path.  `run_query` accepts that exact descriptor binding, validates the
path/fd/inode/mode pairing, and passes the result fd to both CodeQL subprocesses
with `pass_fds`; a mismatched path or descriptor fails before execution.
Production revalidates the lexical output leaf immediately before and after
every runner call, immediately before decoded JSON is read, after decode, and
during finalization.  Renaming the original output root and creating a
replacement therefore cannot redirect result decode or artifact publication:
the run terminates with fixed path-free `CODEQL_QUERY_FAILED`, leaves
`run.json=failed`, publishes no stage artifact, and resume reruns the stage.

Path-stable workspace ownership alone is insufficient for result consumption.
Immediately after `bqrs decode`, `run_query` opens the decoded leaf exactly
once as one owned transaction.  Initial regular-file/name/inode/uid/mode
validation, bounded `pread`, JSON/query-contract validation, output fsync, and
publication all use that same descriptor; no later path reopen can become a
new trusted leaf.  The transaction records immutable decoded bytes, their
exact size, and SHA-256, and revalidates the live descriptor/name plus exact
bytes digest before and after fsync, immediately before and after publication,
and before retained binding capture.  Before the original publication
`.generations` anchors are released, `run_query` duplicates the still-open
original descriptor, requires
that its initial inode still occupies the `.generations` name, binds the
published generation to the publication transaction's expected inode, and
opens the decoded regular file relative to that bound generation.  A
post-publication/pre-binding exchange can never be adopted as a new trusted
root.  The resulting private, in-memory-only binding contains the initially
opened `.generations` descriptor and inode, the published generation
descriptor/name/inode, and the decoded regular-file
descriptor/name/inode/uid/mode together with the immutable decoded bytes,
exact size, and SHA-256.  The private binding is
excluded from `QueryResult` dataclass fields, representation, equality, hashes,
serialization, artifact payloads, and path identity.  Injected fixture runners
are normalized to the same binding immediately at the production boundary.
The default runner also receives a production owner callback and registers the
bound `QueryResult` inside the workspace transaction before the runner return
event; an interrupt at that event therefore cannot precede ownership.  A
non-cooperating injected result remains responsible for an unattached binding
and releases it through its private finalizer if its return is interrupted.
Registration retains the result object as well as its binding so reuse of a
Python object id cannot alias a later query to an older decoded descriptor.
Pickle reconstruction restores `_output_binding=None` while serializing only
the six public result fields.
Production parses only the immutable bytes snapshot; it never reopens or
parses current bytes from `QueryResult.decoded_path`.  Before and after snapshot
selection/parsing it revalidates the entire results -> original `.generations`
-> published generation -> decoded-file descriptor/name chain and bounded-
`pread` hashes the live fd to require the exact captured size and SHA-256.
The live chain and digest are checked again after JSON parsing and before the
decoder is called, so a mutation performed by or during the parser cannot reach
semantic decode.
Injected/fixture runners are captured through the same single owned-open,
immutable-bytes, exact-size, and digest contract.  An equal-length in-place
rewrite therefore keeps neither a forged row nor a metadata-only bypass: both
family execution and formal Entry/Pipeline fail with `CODEQL_QUERY_FAILED`,
publish no stage artifact, persist `run.json=failed`, and rerun on resume before
the decoder consumes the forged bytes.  Final inventory streams the
first pinned `.generations` descriptor and requires its original inode still to
occupy the `.generations` name; it never adopts a newly opened replacement as
the expected generation root.  Exchanging `.generations` after initial
inventory but before decode therefore reads no forged row, preserves both
original and competitor roots and the unchanged workspace, fails with fixed
path-free `CODEQL_QUERY_FAILED`, publishes no stage artifact, leaves
`run.json=failed`, and forces resume to rerun.

Final inventory opens `.generations` relative to the pinned
`results` descriptor, binds its inode/current uid/exact `0700` mode, streams it
through `os.scandir(fd)` with a hard bound, then revalidates all four descriptor
and name bindings.  A hidden name, name/inode/mode drift, unsafe directory,
enumeration failure, or bound overflow preserves the whole workspace.  The
executor never performs lexical `lstat -> scandir -> rmtree` cleanup.

A no-hidden, fully rebound workspace is not deleted either.  It first moves
through dirfd-relative `renameat2(RENAME_NOREPLACE)` to a fresh
`.dosweb-<family>-quarantine-*` name, reconstructs source/destination state
after every exception, verifies that the destination is the original pinned
workspace inode and the source is absent, fsyncs the pinned output directory,
and then retains that isolated workspace.  Collision retry is allowed only
while the original source name still binds the expected workspace inode.
Workspace-name substitution, `.generations` substitution during fd streaming,
an unavailable isolation primitive, or any other ambiguous state therefore
deletes neither original nor competitor.  `rmtree` is never called on query
result workspaces.  If final inventory/isolation returns anything other than a
proved isolated success, `_run_codeql_family` and formal Entry execution must
raise fixed path-free `CODEQL_QUERY_FAILED`; they may not return decoded rows or
publish stage artifacts.  `run.json` remains `failed`, resume executes the
stage again, and retained state is not consumed.  All workspace descriptors,
query-owned descriptors, and the execution lock still return to baseline.
The temporary `.generations` descriptor and the retained results/workspace/
output/output-parent chain all use the shared deferred
`release_owned_descriptor_once` transaction.  No runner or production call
site invokes `close_fd_once` or `close_fd_once_outcome` directly.  Each
transaction state is allocated before its primary action.  The raw close and
allocation-free status assignment execute with trace/profile callbacks and
`SIGINT` deferred; only committed `RELEASED` or `POST_ACTION_EXCEPTION`
consumes the primary action.  A setup escape before the action or proved
`PRE_ACTION_FAILURE` remains owned long enough to run any required
descriptor-bound rollback callback and exactly one
`os.closerange(fd, fd+1)` fallback.  Transaction allocation itself also occurs
inside the outer batch before the raw action; allocation failure keeps the
local descriptor value as the sole owner, records the allocation failure,
performs the same single fallback without constructing another outcome, and
continues the remaining descriptor loop.  Every retained decoded-file,
published-generation, and `.generations` binding descriptor participates in
the same release transaction before the workspace chain is released.
Runner binding, execution-query, publication anchor, production binding, and
workspace cleanup each place the complete owner-field retirement, every shared
helper call and result commit, the remaining descriptor loops, and the final
execution-lock release inside one outer deferred transaction.  The profile/
trace state and `SIGINT` mask are restored only after no owned descriptor or
lock remains, so a shared-helper return event cannot stop at the first fd.  All
primary, transaction, callback, and fallback exceptions are collected without
stopping the remaining descriptor loop.  Descriptor fields are retired once,
and any recorded release failure becomes fixed path-free
`CODEQL_QUERY_FAILED`; a post-close allocation failure cannot leave an empty
holder that retries an fd number after ABA reuse.

The production workspace chain is represented by one persistent reverse-order
descriptor owner rather than a copied tuple of fd numbers.  Its slots remain
owned until the associated mutable transaction is explicitly consumed or has
entered the one-shot fallback; an interruption before the release helper body
therefore leaves the slot for the next deferred attempt, while an interruption
after an actual close retires the committed slot and cannot touch an ABA-reused
number.  `_CodeqlQueryWorkspace.close()` duplicates the descriptor-chain
release at its own lexical boundary, catches a first/second-call escape only
after that fallback has run, synchronizes public descriptor fields from the
persistent owner, and reports success only when every slot is retired without
a recorded failure.  The inventory/factory/local fallback release sites and
all family/Entry calls to `_cleanup_codeql_query_workspace()` use the same
caller-local `try/finally` pair.  A call-entry callback or real `SIGINT` can
therefore change the final result to failure but cannot strand the six-fd
ancestry/output/workspace/results chain or reclose a replacement fd.

If both no-replace and exchange primitives remain unavailable, source
integrity takes priority over cleanup completeness: the actual generation or
the already-exchanged empty placeholder may remain at the normal name, the
operation terminates with path-free `CODEQL_QUERY_FAILED`, no `QueryResult` is
returned, and the formal run remains `failed`.  Such output is never consumed
as a completed/resumable run.  Rollback-slot cleanup failure still must not
skip primary, identity, rollback, or final-anchor release.

The generic `RENAME_NOREPLACE` capability probe follows the same source-
integrity and ownership contract as publication rollback.  Its empty source
directory is opened immediately through a no-follow descriptor into a
publication-scope structural owner before the capability action.  Whether the
source-to-target rename succeeds, fails before action, or raises after action,
cleanup classifies the two mutable names by the pinned expected inode and
moves only that exact empty directory, through cross-dirfd
`RENAME_NOREPLACE`, into a fresh
`.rename-noreplace-probe-tombstone-*` below the pinned pending-generation
identity.  It never calls `unlink` or `rmdir` on either mutable probe name.  If
a target-name ABA preserves the original under a competitor name and installs
an empty same-name substitute, neither mutable object is removed or
overwritten: the ambiguous state is retained and the query fails closed.  The
probe fd normally retires through the shared local one-shot owner batch; if
both local deferred setup windows escape, its unretired slot remains visible
to `release_owned_state`, the final unassigned-owner safety tuple, and the
allocation-free emergency drain.  Those outer paths continue through all
remaining publication owners and release the execution lock in the ultimate
`finally`; a slot consumed by any earlier release action is absent and its fd
number is never retried after reuse.

Publication also creates and inode-binds an empty owner-only
`.rollback-slot-*` in the pinned `.generations` directory and proves
`renameat2(RENAME_EXCHANGE)` support by an exchange-and-restore probe.  If the
no-replace operation later fails persistently for a non-collision reason, the
normal generation and that bound empty slot are atomically exchanged; both
post-exchange inode bindings are verified and fsynced.  The actual generation
is then reachable only through the hidden slot and enters the same
retained-quarantine contract.  The empty placeholder is not deleted at
its mutable normal name: it must pass the fresh hidden no-replace isolation
rule above first and is then retained under that hidden name.  The rollback
transaction retains both expected inodes and
explicit exchange/placeholder-isolation commit state.  On every retry it
reconstructs the only accepted state from the two names: generation at normal
plus empty slot, empty placeholder at normal plus generation at hidden slot,
or normal absent plus generation at hidden slot.  Therefore an exception in
post-exchange inode verification, parent fsync, or hidden placeholder isolation
can never reinterpret the empty normal-side slot as the generation.  No
rollback path may use `os.replace`, overwriting `rename`, or a
check-then-overwrite fallback; a leaf created after any absence check must
remain untouched.  A filesystem-primitive outage may retain the verified
actual generation or empty placeholder at the normal name, but it can never
return a `QueryResult`; every other rollback failure retains only hidden
quarantine state and terminates with path-free `CODEQL_QUERY_FAILED`.  Neither
hidden actual output nor hidden placeholder is traversed or destructively
removed.
The exchange capability probe is itself a two-name/two-inode transaction.  It
records the rollback-slot and probe names, both expected inodes, and explicit
exchange/restore attempted and committed state.  After any exception from the
first exchange, it stats both names to distinguish the prepared pairing from
the already-exchanged pairing; a post-action exception therefore cannot lose
which inode is in which slot.  A persistent pre-action failure while restoring
does not require another exchange: cleanup verifies the current exchanged
pairing and opens each expected empty directory through a pinned, no-follow
descriptor.  It never applies `unlink` or `rmdir` to either mutable transaction
name.  Instead it uses cross-dirfd `renameat2(RENAME_NOREPLACE)` to move the
exact expected inode into the already pinned pending-generation identity as a
retained internal probe/slot quarantine.  Successful probing moves only the
exact probe inode into an internal
`.rollback-exchange-probe-tombstone-*` and preserves the bound, empty rollback
slot at the `.generations` root for later publication rollback.  A failure in
the prepared or exchanged phase isolates whichever expected inode occupies
each name into the pending generation.  If a namespace ABA causes an unrelated
substitute to be moved, source/destination inode classification permits only a
reverse `RENAME_NOREPLACE` restoration to the exact mutable source name; the
original competitor and substitute are never deleted or overwritten.  Probe
directory creation immediately opens the exact inode into a structurally
reserved publication-owned slot whose lifetime outlives the probe frame; slot
isolation reuses the caller-owned exact slot fd.  The shared empty-directory
isolation helper requires a pinned descriptor and performs no descriptor
acquisition or release itself.  Probe descriptors normally retire through
`release_owned_descriptor_once` inside one complete
`run_with_deferred_interrupts` owner loop.  A proved pre-action failure receives
the single fd-range fallback, an actual-close-then-post-action exception never
retries the fd number, and either failure is recorded without preventing outer
publication cleanup from releasing its remaining generation descriptors and
lock.  If the local outer deferred transaction escapes before `release_all`
runs, the helper enters a second complete deferred window before it retires
only descriptors still structurally present in the owner list and gives each
one exactly one direct fd-range fallback.  Restored trace/profile hooks
therefore cannot split owner retirement from that fallback or truncate the
remaining local batch.  If that second setup also escapes, the still-unretired
slot remains in the publication-owned list and the final
`release_owned_state` transaction releases it before the generation anchors
and execution lock.  Descriptors already popped by any per-fd transaction are
absent from this list, so a committed or ambiguous close is never retried after
fd-number reuse; one fallback failure is recorded without truncating retirement
of later owners.
The outermost `release_owned_state` entry has no fourth recursive deferred
retry.  If its own deferred setup escapes before the action, the publication
finalizer first marks any attempted publication rollback-required and uses the
still-live final rollback, rollback-directory, or generations anchor to run the
normal rollback, independent recovery, and descriptor-bound force-isolation
chain until the normal generation name is proved non-consumable.  This applies
even when publication had committed successfully before finalization began; a
release-entry failure may not leave `Entries-*` or its rollback slot as a
consumable completed result.  The finalizer then performs an independent
emergency drain over the still-structural
probe, decoded-output, private-binding, rollback, pending, and generations
owner slots.  It allocates no close outcome, retires each slot once, invokes
exactly one raw `os.closerange(fd, fd+1)` fallback, and nests each owner group in
the next group's `finally`; the execution lock is released in the ultimate
`finally`.  Recovery failure is retained as the path-free publication failure,
but the drain and lock release still execute.  Owner slots already consumed by a completed or ambiguous per-fd
transaction are empty and cannot be retried.  This emergency boundary covers
deferred entry/setup escape and per-fd fallback exceptions; it does not claim
that arbitrary, continuously firing Python trace/profile callbacks can make
unprotected bytecode atomic.
The outer action also commits an allocation-free
`release_owned_state_completed` bit only after every owner group is retired,
the private binding decision is final, and the execution lock is released.
An exception raised by deferred-state restoration after this bit, the complete
release-transaction bit, clean housekeeping, a valid commit, and zero recorded
release/rollback failures is classified as post-action restoration rather than
a failed publication; it does not retroactively turn the already valid normal
generation into a failed-but-consumable result.  Any exception before that
complete state follows emergency recovery and drain.  Every probe or
pre-completion release `BaseException` at the publication boundary is
normalized to fixed, path-free `CODEQL_QUERY_FAILED` details.
Successful publication does not set the publication transaction's `resolved`
bit: that bit remains reserved for completed rollback/recovery.  The bound
rollback slot is opened no-follow and pinned by exact directory fd before the
exchange probe and before publication.  A direct adapter call that does not
retain a result binding duplicates a dedicated `.generations` cleanup anchor
before releasing the rollback descriptor; a production call that retains the
private result binding reuses that binding's pinned `.generations` descriptor.
The exact pending/published-generation identity fd is the retained destination
for probe and pre-publication isolation and remains live through slot
retirement and the cleanup-anchor release transaction.  If execution fails
after a successful probe but before publication is attempted, or after a
resolved rollback, outer cleanup applies the same pinned-empty-directory,
cross-dirfd no-replace isolation to the rollback slot and retains it inside the
pending generation; it never removes the mutable slot name.  Only after the
final rollback anchor is structurally `RELEASED`, no earlier release/rollback
failure exists, and the commit is still valid may successful retirement begin.

The rollback-slot lifecycle is dirfd-relative, non-recursive, and
non-destructive from exchange probing through pre-publication failure and
successful retirement: no phase issues `unlink` or `rmdir` against its mutable
name.  Before retirement isolation it revalidates the named `.generations`
binding; the published fd and normal name must both be the expected directory
inode, current-uid, and exact `0700`; and the rollback-slot fd and name must
both be the expected current-uid `0700` directory inode with an empty
fd-relative enumeration.  It then allocates a fresh
`.rollback-slot-tombstone-<uuid>` name inside the exact published generation
and uses cross-dirfd `renameat2(RENAME_NOREPLACE)` to move the slot from the
pinned `.generations` parent into that internal tombstone.  The tombstone is
successful-generation transaction metadata: it is retained inside the normal
generation and is not a leaf in the `.generations` root inventory.

After every isolation attempt, source and destination are classified by their
live inodes.  Success requires the internal tombstone to bind the originally
pinned slot inode and the mutable source name to be absent.  If a namespace ABA
renames the original slot and substitutes another directory, and that
substitute is moved instead, the implementation uses only a reverse
cross-dirfd `RENAME_NOREPLACE` to restore the substitute to its exact dynamic
slot name.  It verifies that restoration, fsyncs both directories, and never
deletes or overwrites either the attacker-retained original inode or the
substitute inode.  A failed restore or any ambiguous source/destination state
has no destructive fallback and fails closed.

Verified isolation records `slot_retired=true` and the exact tombstone name,
fsyncs both the published generation and `.generations` parent, and revalidates
the pinned slot fd against the tombstone name, current uid, exact `0700`, and an
empty fd-relative enumeration.  It then revalidates the parent plus published
fd/name safety contract and requires the mutable slot name to remain absent.
Any move or ambiguity after which exchange rollback is no longer trustworthy
also records the retired phase before recovery.

Any retirement or descriptor-release exception records release failure and
re-arms recovery.  Once `slot_retired=true`, rollback no longer assumes that
exchange is possible; it uses the still-live cleanup anchor plus exact
published-generation identity to move the expected normal generation to a
fresh hidden name with `RENAME_NOREPLACE`, never overwriting a competitor.
The rollback-slot fd release transaction installs this recovery as its
pre-action fallback; a proved `PRE_ACTION_FAILURE` therefore recovers before
the fallback close, while a `POST_ACTION_EXCEPTION` is detected from the
release outcome and triggers the same recovery using the still-live generation
identity and parent anchor.  The cleanup-anchor pre-action fallback likewise
marks rollback required before recovery.  Post-isolation fsync/verification,
rollback-slot release in either phase, and cleanup-anchor pre-action failure
therefore terminate with fixed, path-free `CODEQL_QUERY_FAILED` and cannot
leave the expected generation consumable at its normal name.  Successful
single or repeated queries leave only their normal generation directories in
the `.generations` root and never accumulate root-level
`.rollback-slot-*` leaves.  Direct adapter calls without an execution binding
retain their fixture-compatible behavior, but the default production graph
always supplies the private binding.

Pipeline finalization runs for success, stage failure, pre-publication failure,
and exceptions, and runs before `status=completed` is persisted.  It first
revalidates canonical identity and then removes the private tree with a
descriptor-relative, no-follow bounded cleanup.  Tree and stale-root enumeration
use streaming `os.scandir(fd)` with per-entry bounds, never unbounded
`listdir`/`iterdir` or pre-sorted materialization.  Cleanup first atomically
renames the bound root to a same-parent random quarantine with dirfd-relative
Linux `renameat2(RENAME_NOREPLACE)`, then verifies its inode.  Unsupported
no-replace operation or an occupied destination fails with the fixed cleanup
error and never falls back to overwriting `rename`.
Cleanup performs every unlink/rmdir relative to pinned fds.  Open-fd inode and
link-count checks after each removal detect file, directory, and root swaps;
the race remains confined to quarantine and fails closed.  Before returning,
cleanup also verifies that the original `.codeql-execution-*` name is still
absent.  If a same-uid process recreated it, the replacement is preserved but
cleanup fails, so Pipeline persists `status=failed` rather than `completed`.
Safe owner-only stale roots
of the same hidden format are removed during the next locked preflight;
symlink, special-file, foreign-owner, mode, inode, or cleanup races fail closed.
Clone/validation/cleanup failures use the fixed path-free
`CODEQL_EXECUTION_SNAPSHOT_FAILED` error.  A finalizer cleanup failure is the
raised and persisted error while the original preflight/stage error remains its
cause.  A cleanup failure leaves the run
failed even when every requested stage artifact was already reusable or
published; it can never leave a newly written completed run.

The random execution path is secret operational state: it is prohibited from
`QueryResult`, diagnostics, `run.json`, stage manifests, public/private formal
artifacts, reports, and batch identities.  A fresh `--resume` invocation may
create and clean a different private path while still reusing every stage when
the canonical fingerprint and all existing resume inputs match.
