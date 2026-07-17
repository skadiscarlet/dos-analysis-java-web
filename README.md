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

## Development Utilities

- `scripts/build_top50_codeql_dbs.py` validates an explicit target manifest and prepares bounded CodeQL database builds.
- `scripts/aggregate_java_web_dos_batch.py` aggregates static v2 artifacts only.
- `scripts/prepare_dynamic_validation_output.py` and `scripts/sync_dynamic_validation_status.py` are opt-in helpers for an independently authorized dynamic-validation workflow.

Use `--help` on each script for its input and safety requirements. The build script does not clone or build targets in `--dry-run` mode.

## Status

The workspace is prepared for v2 implementation. Legacy phase-based analyzer code and reports remain outside the active implementation context so that new development follows the lifecycle-centered static model.
