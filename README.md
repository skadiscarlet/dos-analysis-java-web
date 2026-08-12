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

The active research corpus contains exactly **205 Java Web projects**, with source snapshots under `frameworks/applications/` and Java CodeQL databases under `databases/applications/`. It is the case-insensitive repository union of the preserved canonical Java Web 200 inventory and the PoC-29 repository set: 200 original targets plus 5 previously absent repositories.

- Active corpus definition: `docs/java-web-205-corpus.md`
- Active canonical inventory: `intel/applications/java_web_205_targets.json`
- Deterministic inventory generator: `scripts/generate_java_web_205_inventory.py`
- Preserved Java Web 200 definition/inventory: `docs/java-web-200-corpus.md` and `intel/applications/java_web_200_targets.json`

Earlier 50-project and 183-project inventories, the Java Web 200 generated run, and its repair outputs are historical evidence and do not define current corpus membership. Membership and readiness are distinct: the active dataset has 205 targets, while the current tracked manifest reports 150 strictly ready databases and 55 incomplete databases.

The canonical batch layer validates all source fingerprints and CodeQL database source roots before publishing an immutable plan. Planning is local and network-free:

```bash
python scripts/run_java_web_dos_batch.py plan \
  --run-id java-web-205-plan \
  --output results/java_web_dos_batch/java-web-205-plan
```

`entries` runs only local Entry extraction with bounded concurrency and strips any inherited provider credential. `full` requires both `--allow-remote-llm` and `DEEPSEEK_API_KEY` for execution. Use `full --plan-only` to construct and publish a non-executing full plan without a key or network; this still records only non-secret provider settings (`--model`, `--base-url`, `--timeout-seconds`, `--max-retries`, `--temperature`, `--cache-dir`, `--config`, and `--codeql-binary`) in the digest-bound plan. Targets represented only by `tree-sha256` remain explicitly paused because that fingerprint cannot satisfy public Git commit attestation. Per-target stage reuse remains governed by the production pipeline's strict manifests and hashes:

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
