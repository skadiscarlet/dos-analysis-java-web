# Task 7 Report — Production Orchestration, Conclusions, Reports, and Recovery

Status: COMPLETE — P0 PRODUCTION PIPELINE AND STATIC GATES VERIFIED

## Scope completed

- Connected the fixed production stages:
  - `entries`
  - `growth`
  - `flows`
  - `lifecycle`
  - `conclude`
  - `report`
- Snapshotted and fingerprinted the complete packaged CodeQL query pack across Entry, Growth, Flow, and Lifecycle queries.
- Added strict durable serialization and reconstruction for Growth candidates/contracts/results, Flow proofs, lifecycle candidates/decisions, certificates, and findings.
- Reused pinned Git-blob source excerpts and bounded slices for DeepSeek Growth Contract classification without fabricating Entry→Growth, CFG, configuration, Guard, Bound, or Release evidence.
- Required exactly one deterministic Entry association for every Growth candidate; absent or ambiguous association fails closed.
- Persisted lifecycle decisions as authoritative stage output and consumed them in conclusion rather than recomputing them from raw candidates.
- Evaluated every sibling flow for a candidate. Partial or unsupported sibling paths remain auditable and force `static_unknown`.
- Published only the normative artifact contract and retained atomic stage publication, strict upstream hash/count/schema/reference checks, exact resume fingerprints, and downstream invalidation.

## Security and provenance invariants

> **已过时（2026-08-18）：** 以下“public repository default branch + clean/pinned commit + Git blob 一致”的 provenance 门槛已被用户明确授权移除；当前只保留显式授权、非空 API key、可读本地源码目录与凭据不落盘。保留此报告仅供历史追溯。

- Remote classification requires explicit authorization and `DEEPSEEK_API_KEY` from the environment.
- The key is absent from configuration, fingerprints, artifacts, manifests, cache identities, reports, diagnostics, and controlled errors.
- （历史）The selected source commit must be reachable from the public repository's current default branch, the local checkout must be clean and pinned to that commit, and each transmitted excerpt must match the pinned Git blob.
- The CodeQL database `sourceLocationPrefix` must resolve to the same configured checkout before production queries run.
- Credential assignments in code or comments and credential-bearing Java mutator/header calls are rejected before public-source verification, cache access, or provider transport.
- Default tests use injected seams and make no DeepSeek or GitHub request.

## Conservative conclusion invariants

- Static verdicts are exactly:
  - `static_vulnerable`
  - `bounded_under_modeled_assumptions`
  - `static_unknown`
- Sink evidence alone does not prove attacker influence.
- Partial Growth/Flow/lifecycle coverage, unknown configuration, unresolved evidence, or potential asynchronous Release forces `static_unknown`.
- Lifecycle result schemas validate complete nested decisions, summary consistency, reason aggregation, release classification, and canonical lifecycle IDs.
- Certificates recompute assertions and verdicts from all supplied paths and reject forged identities, evidence, assertions, decisions, or verdicts.
- Reports remain static-only and never claim dynamic confirmation or unconditional safety.

## Verification

```text
python -m unittest discover -s tests -p 'test_*.py' -v
Ran 462 tests in 42.931s
OK (skipped=6)
```

```text
DOSWEB_RUN_CODEQL_FIXTURES=1 python -m unittest -v \
  tests.test_codeql_entry_queries \
  tests.test_codeql_growth_queries \
  tests.test_codeql_lifecycle_queries
Ran 6 tests in 369.998s
OK
```

Additional gates passed:

- `python -m compileall -q dosweb scripts`
- main CLI and all seven subcommand `--help` paths
- `git diff --check`
- focused production, artifact, certificate, provider-secret, public-source provenance, and mixed-path regression suites
- independent correctness and security review with verified findings fixed and covered by regressions

Verification made no real DeepSeek request, did not start target services, did not send attack traffic, and did not run dynamic DoS validation.
