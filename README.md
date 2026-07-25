# dos-analysis-web v2

Static analyzer for resource-exhaustion DoS patterns in Java Web and adjacent Java network applications.

## Model

```text
Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)
```

The first v2 release is a static analyzer:

```text
entries -> growth -> flows -> bounds -> lifecycle -> conclude -> benchmark -> report
```

`growth` follows the required sequence:

```text
CodeQL raw screening -> bounded slice -> LLM Growth Contract -> rule/static verification
```

Static conclusions use only:

- `static_vulnerable`
- `static_safe`
- `static_unknown`

The repository also contains opt-in helpers for preparing and synchronizing an explicitly authorized, isolated dynamic-validation run. Those helpers are not invoked by the static pipeline, and their results must remain separate from static conclusions.

## Preserved Evidence

The rewrite preserves:

- `databases/`
- `frameworks/`
- `poc/`
- `results/static_hunts/`
- `results/application*`
- `results/java_web_dos_batch/`

`poc/` remains an unchanged evidence archive. Existing dynamic evidence may be used as oracle or benchmark material, but it is not produced by an ordinary v2 static scan.

## Design

Current design documents:

- v2 engineering baseline: `docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md`
- lifecycle-centered research design: `docs/research/2026-07-14-lifecycle-centered-resource-dos-idea-design.md`
- paper draft: `docs/paper/2026-07-15-lifecycle-static-analysis-paper-front-half.md`

The lifecycle-centered design supersedes the old Stage 0–5 research direction. It does not replace the v2 engineering baseline.

## Canonical Java Web Corpus

The current research corpus contains exactly **200 Java Web projects** with source snapshots under `frameworks/applications/` and Java CodeQL databases under `databases/applications/`.

- Corpus definition: `docs/java-web-200-corpus.md`
- Machine-readable canonical inventory: `intel/applications/java_web_200_targets.json`
- Local generated run: `results/application_dbs/java_web_200_20260725/`

Earlier 50-project and 183-project inventories are retained only as historical evidence and do not define current corpus membership.

## Development Utilities

- `scripts/repair_java_web_200_inventory.py` validates a replacement target, creates its source-only Java CodeQL database, and publishes the canonical 200-project inventory.
- `scripts/aggregate_java_web_dos_batch.py` aggregates static v2 artifacts only.
- `scripts/prepare_dynamic_validation_output.py` and `scripts/sync_dynamic_validation_status.py` are opt-in helpers for an independently authorized dynamic-validation workflow.
- `scripts/build_top50_codeql_dbs.py` and `scripts/reselect_java_web_dos_top50.py` are retained for reproducing superseded historical selection runs; they are not current corpus entry points.

Use `--help` on each script for its input and safety requirements. Dry-run modes do not clone, build, or publish target assets.

## Status

The workspace is prepared for v2 implementation. Legacy phase-based analyzer code and reports remain outside the active implementation context so that new development follows the lifecycle-centered static model.
