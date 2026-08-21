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
