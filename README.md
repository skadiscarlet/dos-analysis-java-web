# dos-analysis-web v2

Static analyzer for resource-exhaustion DoS patterns in Java Web and adjacent Java network applications.

## Model

```text
Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)
```

The v2 pipeline is static-only in its first release:

```text
entries -> growth -> flows -> bounds -> conclude -> benchmark -> report
```

`growth` follows the required sequence:

```text
CodeQL raw screening -> ML filter/ranker -> LLM summary -> rule/static verification
```

## Preserved Evidence

The rewrite preserves:

- `databases/`
- `frameworks/`
- `poc/`
- `results/static_hunts/`
- `results/application*`
- `results/java_web_dos_batch/`

`poc/` remains an unchanged evidence archive. Existing dynamic evidence is imported only as oracle material, ML seeds, and benchmark evidence. v2 does not run dynamic validation in its first release.

## Design

The approved v2 design is:

- `docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md`

## Status

The workspace is being cleaned for v2 implementation. Legacy phase-based analyzer code and reports are intentionally removed to avoid contaminating future agent context.
