# dos-analysis-web v2

Static analyzer for resource-exhaustion denial-of-service patterns in Java Web and adjacent Java network applications.

## Status

The Java Web DoS P0 analyzer is complete: the default CLI connects the full CodeQL → bounded-slice DeepSeek Growth Contract → deterministic verification pipeline across all six resumable stages. Unsupported, partial, ambiguous, or unresolved evidence remains fail-closed as `static_unknown`.

Ordinary development tests are network-free. They do not contact DeepSeek or GitHub, start target services, send attack traffic, or perform dynamic DoS validation.

## Requirements and installation

Requirements:

- Python 3.11 or newer;
- a Java CodeQL database for the target;
- CodeQL CLI available as `codeql`, or selected with `--codeql-binary`;
- for every complete production P0 run, `DEEPSEEK_API_KEY` supplied through the environment and explicit authorization for remote Growth Contract evaluation. Previously exposed keys must be rotated before use.

Install the local package in a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

API keys must never be placed in YAML configuration, command-line arguments, manifests, reports, caches, diagnostics, or tests. Remote LLM use is disabled unless `--allow-remote-llm` is explicitly supplied. The source URL, exact commit, and clean local checkout must also be attested before source slices may be sent.

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

Recognized but unresolved registration, entry, Growth, path, configuration, or lifecycle patterns are recorded as coverage gaps rather than guessed away.

## Assertions and verdicts

Assertion 1 matches when a verified Growth site is reached by a proven attacker-controlled E→G flow and no effective Guard or Bound prevents that Growth.

Assertion 2 applies to escaping or repeatable Growth driven by attacker-controlled persistent key, value, submission, or resource-creation demand. It matches only when no effective Bound or effective synchronous Release limits the resource.

P0 does not prove asynchronous Release. A potential asynchronous consumer, expiry mechanism, background cleanup, or completion path remains unresolved unless a supported synchronous reduction is established. Relevant unresolved evidence or incomplete coverage forces an unknown conclusion.

Static conclusions use exactly three values:

- `static_vulnerable`: at least one applicable assertion is statically matched, with no relevant unresolved evidence or coverage gap;
- `bounded_under_modeled_assumptions`: all applicable assertions are refuted by effective Guard, Bound, or synchronous Release evidence under modeled default configuration, with relevant entries and paths covered, explicit assumptions and stable reason codes recorded, and no candidate-relevant coverage gap; this is not an unconditional safety claim;
- `static_unknown`: the available static evidence or candidate-relevant coverage is insufficient for either of the preceding conclusions.

Provider confidence is audit metadata only and never changes a verdict.

## CLI

A complete production invocation has this shape:

```bash
export DEEPSEEK_API_KEY='set-in-your-shell-only'
dos-web-analyzer analyze \
  --database databases/applications/example-db \
  --output results/p0/example \
  --codeql-binary codeql \
  --allow-remote-llm \
  --public-source-url https://github.com/example/project \
  --source-commit-sha 0123456789abcdef0123456789abcdef01234567 \
  --source-checkout frameworks/applications/example-project
```

Remote classification remains disabled unless consent is explicit, the API key is present only in the environment, the selected commit is reachable from the public repository's default branch, the checkout is clean and pinned, and the CodeQL database source root matches that checkout.

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
├── growth_contracts.jsonl
├── verified_growth.jsonl
├── flow_proofs.jsonl
├── guard_candidates.jsonl
├── bound_candidates.jsonl
├── release_candidates.jsonl
├── lifecycle_results.jsonl
├── static_findings.jsonl
├── lifecycle_certificates.jsonl
├── summary.json
└── report.md
```

The provider-neutral pipeline also maintains `.pipeline.lock` and per-stage metadata under `.stage-manifests/`. For each successful stage publication, its formal artifacts and stage manifest are installed before the corresponding `run.json` checkpoint is updated. Lifecycle certificates are the durable detailed conclusion records; static findings reference certificates, and summaries and Markdown reports must agree with those certificate verdicts.

## Verification

Run the default network-free suite:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q dosweb scripts
```

Real CodeQL fixture checks are explicit opt-ins and require a local CodeQL installation:

```bash
codeql pack install codeql
DOSWEB_RUN_CODEQL_FIXTURES=1 python -m unittest \
  tests.test_codeql_entry_queries \
  tests.test_codeql_growth_queries \
  tests.test_codeql_lifecycle_queries -v
```

These fixture checks create local test databases; they do not authorize remote LLM use or dynamic validation. No default test requires `DEEPSEEK_API_KEY`.

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

The research corpus contains exactly **200 Java Web projects**, with source snapshots under `frameworks/applications/` and Java CodeQL databases under `databases/applications/`.

- Corpus definition: `docs/java-web-200-corpus.md`
- Canonical inventory: `intel/applications/java_web_200_targets.json`
- Local generated run: `results/application_dbs/java_web_200_20260725/`

Earlier 50-project and 183-project inventories are historical evidence and do not define current corpus membership.

Development utilities:

- `scripts/repair_java_web_200_inventory.py` validates a replacement target, creates its source-only Java CodeQL database, and publishes the canonical inventory;
- `scripts/aggregate_java_web_dos_batch.py` aggregates static v2 artifacts only;
- `scripts/prepare_dynamic_validation_output.py` and `scripts/sync_dynamic_validation_status.py` manage the separate opt-in dynamic evidence scaffold;
- `scripts/build_top50_codeql_dbs.py` and `scripts/reselect_java_web_dos_top50.py` reproduce superseded historical selection runs only.

Use `--help` on each script for its input and safety requirements. Dry-run modes do not clone, build, or publish target assets.
