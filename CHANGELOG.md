# dos-analysis-web v2 CHANGELOG

This changelog starts at the v2 cleanup baseline. Older analyzer runs and case-level research history remain available in Git history and preserved result directories rather than in the active project changelog.

## [2026-07-28] Add canonical Java Web 200 batch orchestration

### Added

- Added strict canonical-corpus validation, source/database provenance checks, immutable batch plans, target identity bindings, bounded concurrency, atomic batch state, failure isolation, and resumable per-target production execution.
- Added local-only `entries` batches and explicitly authorized `full` batches. Environment provider credentials are stripped from Entry-only workers, while tree-fingerprint targets remain paused when public Git commit attestation is unavailable.
- Added format-separated normative P0 aggregation with target/run/stage binding, artifact hash/count/size validation, structured gap accounting, atomic publication, and exact three-value static-verdict totals while preserving historical hunter aggregation. Aggregation now rejects ambiguous format auto-detection instead of silently treating P0 records as historical.
- Added digest-bound non-secret provider settings to batch plans and a non-executing `full --plan-only` path; full execution still requires explicit remote consent and an environment-only provider key.

### Verification

- Added network-free batch plan, runner, aggregation, resume, authorization, identity, concurrency, stale-artifact recovery, and compatibility regressions; the complete default suite now passes 494 tests with 6 guarded integrations skipped.
- No real DeepSeek request, corpus analysis run, service launch, attack traffic, or dynamic DoS validation was performed.

## [2026-07-28] Complete the production P0 analyzer

### Added

- Connected all six default production executors for Entry extraction, G1–G4 Growth classification, E→G flow proof, lifecycle evaluation, deterministic conclusions, and certificate-consistent reporting.
- Added durable strict round trips for Growth, Flow, Guard, Bound, Release, lifecycle decision, certificate, and finding artifacts, with authoritative resume reconstruction and downstream invalidation.
- Added a complete immutable query-pack snapshot across Entry, Growth, Flow, and Lifecycle query families and a network-free injected full-graph production test.

### Security and correctness

- Preserved pinned-source excerpt validation, explicit remote consent, environment-only API keys, atomic provider-stage publication, conservative partial-coverage handling, and static-only verdict wording.
- Required the selected commit to be reachable from the public repository's default branch, required the CodeQL database source root to match the pinned checkout, and blocked credential assignments in comments and credential-bearing Java mutator/header calls before provider use.
- Made lifecycle decisions durable and schema-validated, rejected forged nested decision summaries/IDs, and ensured any partial sibling flow forces `static_unknown` rather than being discarded from conclusion evidence.

### Verification

- Final default discovery ran 462 tests successfully with 6 guarded integrations skipped.
- All 6 opt-in real-CodeQL Entry, Growth, and Lifecycle fixture tests passed.
- Python compilation, every CLI subcommand help path, and `git diff --check` passed.
- No real DeepSeek request, service launch, attack traffic, or dynamic DoS validation was performed.

## [2026-07-25] Migrate active consumers and document the P0 interface

### Changed

- Migrated active static aggregation and dynamic-scaffold traceability to the exact `static_vulnerable`, `bounded_under_modeled_assumptions`, and `static_unknown` vocabulary, rejecting the retired value and static-verdict field aliases rather than retaining a compatibility path.
- Preserved static/dynamic independence: the dynamic scaffold copies a static verdict only under traceability metadata while retaining `paused`/`blocked` dynamic defaults.
- Reworked README and agent guidance to document Python and CodeQL requirements, mandatory DeepSeek behavior for complete P0 runs, the current fail-closed production executor boundary, stage/resume semantics, normative artifacts, exact verdict meanings, P0 framework/assertion scope, asynchronous Release limitations, coverage gaps, test opt-ins, and static/dynamic separation.
- Added dedicated verdict-migration regressions and physical JSONL source-location checks for rejected values and field aliases, including inputs with blank lines.

### Verification

- Final default discovery ran 416 tests successfully with 6 guarded integrations skipped.
- `codeql pack install codeql` succeeded with CodeQL CLI 2.23.8, and all 6 opt-in Spring MVC, Servlet, Netty, and MQTT entry/Growth/lifecycle fixture tests passed.
- Focused migration tests, Python compilation, CLI help, terminology scan, and `git diff --check` passed.
- Verification made no real DeepSeek request, did not start target services, did not send attack traffic, and did not run dynamic DoS validation.
- At that checkpoint, Task 7 remained partial because the production CodeQL/DeepSeek stage-executor factory was still deliberately unconnected; the 2026-07-28 entry records its completion.
- Per explicit user direction, the obsolete 2026-07-02 baseline design remains deleted as an approved preservation exception; the ignored 2026-07-18 design and plan remain unstaged until commit authorization.

## [2026-07-24] Add static conclusions, certificates, reports, and resumable orchestration

### Added

- Added deterministic Assertion 1 and Assertion 2 evaluation with the exact `static_vulnerable`, `bounded_under_modeled_assumptions`, and `static_unknown` vocabulary. Partial flow, unresolved lifecycle evidence, and relevant coverage gaps remain unknown; provider confidence never changes a verdict.
- Added canonical lifecycle certificates, certificate-derived static findings, deterministic summaries, and static-only Markdown reports with strict finding/certificate/verdict consistency.
- Added generic injected stage execution for `entries -> growth -> flows -> lifecycle -> conclude -> report`, deterministic fingerprints, exact resume reuse, mismatch invalidation, bounded canonical local payloads, strict manifest/artifact recovery validation, output-root locking, symlink refusal, stale-artifact reconciliation, and transactional publication/rollback.
- Added fail-closed CLI subcommand dispatch with controlled `AnalyzerError` and injected-factory failure handling. Production CodeQL/DeepSeek stage executors are not yet connected by the default factory, so direct production commands fail closed rather than claiming analysis success.
- Added network-free P0 scenario coverage for materialization, allocation, persistent-map growth, queues, finite rejection, late Guards, incomplete Release, asynchronous consumers, Netty, and MQTT.

### Verification

- Final default discovery ran 356 tests successfully with 6 guarded integrations skipped.
- Focused assertion, certificate/report, pipeline recovery, artifact, configuration, and P0 end-to-end suites passed; Python compilation, CLI help, and `git diff --check` passed.
- Independent review findings became regressions for scoped coverage, overlapping coverage patterns, forged assertion/verdict/certificate identity, strict lifecycle booleans, active verdict vocabulary, report disagreement, malformed resume metadata, manifest/hash/count tampering, duplicate and symlinked paths, stale artifacts, rollback, factory errors, and bounded payload handling.

## [2026-07-24] Prove entry-to-growth flows and evaluate lifecycle evidence

### Added

- Added normalized E→G `FlowProof` construction with stable identities, strict attacker source/demand mapping, dangling-reference failures, canonical artifact validation, and audited proven/partial verification.
- Added deterministic Guard, Bound, and synchronous Release decisions with structured checks, stable reasons, modeled finite-configuration matching, receiver/dimension/scope joins, and unresolved asynchronous-release retention.
- Added exact-column candidate-only CodeQL queries for direct entry-to-growth flow, Guard, Bound, and synchronous Release evidence, plus Spring, Servlet, Netty, and MQTT lifecycle fixtures.

### Verification

- Final default discovery passed 295 tests with 6 guarded integrations skipped; focused Task 6 tests, Python compilation, and `git diff --check` passed.
- Explicit local CodeQL lifecycle fixture verification passed across all four framework databases, and all four Task 6 queries compiled against the local CodeQL Java pack graph.
- Independent reviews drove regressions and remediation for same-handler false flow proofs, incomplete coverage upgrades, forged flow identities, configuration mismatches, cross-receiver Bounds, Release scope/dimension/key semantics, mixed asynchronous Release evidence, and malformed flow artifacts.

## [2026-07-24] Verify four resource growth classes

### Added

- Added frozen G1–G4 Growth candidate normalization with deterministic resource/growth identifiers, sorted demand/evidence merging, strict raw-row validation, and exact `growth_candidates` artifact serialization.
- Added canonical bounded-slice construction and deterministic Growth Contract verification with audited `verified|rejected|unresolved` results, stable reason codes/checks, strict slice/index evidence identity, and no fabricated static facts.
- Added exact-column CodeQL screening queries for request/message materialization, direct buffer and array allocation, persistent container growth, and field-backed asynchronous work submission.
- Extended Spring, Servlet, Netty, and MQTT fixtures with G1–G4 positives, request-local/lookalike negatives, finite/unbounded queue forms, and guarded real-CodeQL semantic tests.

### Verification

- Final default discovery ran 255 tests successfully with 5 guarded integrations skipped; focused Growth/artifact suites and Python compilation passed.
- Explicit `DOSWEB_RUN_CODEQL_FIXTURES=1` verification passed both Growth query tests across temporary fixture databases; all four Growth queries compiled against the local CodeQL pack graph.
- Independent reviews drove regressions and remediation for fabricated evidence, empty/cross-candidate evidence verification, malformed identifiers, evidence-ID collisions, array-allocation coverage, collection demand roles/scopes, local async receivers, G1 lookalikes, and nested artifact validation.

## [2026-07-24] Extract registered framework entries

### Added

- Added frozen registered-entry, attacker-input, registration, handler, and framework-coverage models with deterministic semantic identifiers, strict framework/protocol pairings, canonical HTTP routes, sorted input deduplication, and bounded analyzer errors.
- Added deterministic entry-row normalization that separates unresolved dynamic registrations from reachable entries, validates both supported and gap rows, and emits explicit coverage records for Spring MVC, Servlet, Netty, and MQTT even when a framework has no extracted rows.
- Added four exact-column CodeQL table queries requiring framework-specific registration/type evidence: Spring controller mappings, Servlet annotation registrations, Netty pipeline registrations, and MQTT subscribe/listener bindings. Recognized unresolved registration patterns emit partial coverage rather than fabricated reachability.
- Added self-contained Java source fixtures with registered handlers, unregistered/lookalike negatives, and dynamic-registration gaps, plus guarded real-CodeQL semantic tests.

### Verification

- Final focused Task 3/4 verification ran 41 tests with 39 passed and 2 guarded CodeQL fixture tests skipped by default; the complete default suite ran 243 tests with 240 passed and 3 guarded integrations skipped.
- Explicit `DOSWEB_RUN_CODEQL_FIXTURES=1` verification passed both real-CodeQL tests across all four temporary Java databases, exact decoded columns, registered-entry expectations, lookalike exclusion, and forcing coverage gaps.
- All four entry queries compiled against the locally installed `codeql/java-all` dependency graph, all Java source fixtures compiled without leaving `.class` artifacts, changed Python files compiled, and `git diff --check` passed. Independent reviews drove remediation for framework lookalikes, protocol mismatches, incomplete coverage validation, sparse coverage records, unresolved registration gaps, and unrelated-reflection coverage poisoning.

## [2026-07-24] Add strict Task 3 CodeQL execution contracts

### Added

- Added bounded CodeQL database validation with strict metadata parsing, stable metadata-file fingerprints, source-root provenance, symlink rejection, and controlled `CODEQL_DATABASE_INVALID` failures.
- Added a two-stage CodeQL query/BQRS runner with minimal secret-free environment inheritance, one shared deadline, bounded diagnostics, descriptor-validated immutable root-query snapshots in the original pack context, database-drift checks, TERM/KILL process-group cleanup, and atomic per-generation publication after validation and BQRS hashing succeed.
- Added fixed ordered `QuerySpec` contracts for entry, growth, flow, Guard, Bound, and synchronous Release candidates, with strict result-set, row, primitive type, enum, path, line, row-count, and string-budget validation.
- Added the minimal `dosweb/p0-java-resource-dos` query pack manifest using the installed CodeQL CLI's modern `dependencies` field, without query suites; individual queries remain deferred to later tasks.
- Added real-CodeQL compatibility remediation for timestamped database metadata, `{name, kind}` decoded column descriptors, strict decoded-result validation before publication, original pack-context query execution with persisted snapshots, and deadline propagation through bounded database and file hashing.

### Verification

- Final focused Task 3 verification passed 25 tests; the full default suite ran 227 tests with 1 guarded online integration skipped. `codeql pack ls codeql` resolved `dosweb/p0-java-resource-dos@0.1.0` under CodeQL CLI 2.23.8.
- Concurrent generation initialization/publication passed 10 repeated rounds; an additional focused stress sequence passed 5 rounds and 90 test executions.
- Changed Python modules/tests compiled and `git diff --check` passed. Independent Task 3 reviews drove regressions for query provenance drift, descendant-held process pipes, SIGTERM-ignoring descendants, and post-publication hashing; all were fixed within the root-query adapter contract.

## [2026-07-22] Complete fourth Task 2 consolidated remediation

### Changed

- Serialized cross-stripe cold cache production behind one fixed private process-shared capacity lock, preserving fixed key stripes, pre-provider capacity failure, immutable entries, and non-destructive no-eviction behavior.
- Replaced single-shot provider/GitHub body reads with incremental bounded reads under recomputed absolute deadlines, and propagated one shared verification budget across GitHub API and local Git operations.
- Added process-local same-key sharing for sanitized deterministic response failures without persistent negative caching; later independent calls may retry normally.
- Replaced plaintext provider request-ID audit persistence with a domain-separated API-keyed HMAC digest and bumped the authenticated cache format.
- Added high-confidence SSN-like PII rejection, complete Java compound-assignment coverage, annotation-aware Java declarator scanning, Java comment/octal/text-block literal reconstruction, component-aware credential identifiers, and bounded UTF-8 prechecks for hostile slice strings.
- Hardened independent-review boundaries: authenticated incompatible cache entries now receive capacity-gated live refresh without overwrite; crash temporaries count toward cache bytes; cache-entry HMACs have an explicit domain; timeout values are upper-bounded; permanent response-read failures do not retry; and complete GitHub slice verification shares one deadline.

### Verification

- Final focused Task 2 verification passed 169 tests; the full default suite ran 202 tests with 1 guarded online integration skipped; concurrency/deadline/publication stress passed 10 rounds and 90 test executions.
- Modified Python modules/tests compiled, parser-only CLI boundaries returned 0/2 as expected, and `git diff --check` passed. Independent review gate results are recorded in the Task 2 implementation report.

## [2026-07-19] Complete third Task 2 consolidated remediation

### Changed

- Hardened provider request-ID credential rejection, unbounded Java assignment scanning, Credential(s) classification, response echo filtering, permanent-network error handling, and one monotonic request deadline.
- Bound aliases and formal evidence to current config/growth identities; made cache fact IDs mandatory and authenticated audit fields fully identity-bound.
- Replaced per-key cache locks with 64 immutable stripes, removed memory growth, closed inherited flock descriptors, imposed non-destructive global capacity limits, and made unsafe/capacity/publication failures fail closed before provider use where required.
- Hardened Git deadlines/config overrides, JSONL mapping/publication/count behavior, strict config keys/Unicode handling, and explicit CLI remote-consent revocation.

### Verification

- Focused Task 2 command passed 146 tests; race/fork/cache/publication stress passed 10 consecutive iterations; full discovery passed 178 tests with 1 guarded online integration skipped.
- Changed Python modules/tests compiled, `git diff --check` passed, and parser-only CLI runtime accepted `--no-remote-llm` while rejecting conflicting consent flags with exit 2.

## [2026-07-18] Fix cold cache hierarchy creation race

### Changed

- Made descriptor-relative private cache hierarchy creation tolerate a concurrent trusted creator winning the `mkdir` race, so every same-key cold process reaches the shared `flock` instead of bypassing single-flight.
- Added a deterministic concurrent hierarchy-creation regression preserving the guarantee that exactly one cold producer publishes and a fresh cache reconstructs the durable contract.

### Verification

- The process single-flight test passed 20 consecutive post-fix iterations; the focused Task 2 suite passed 126 tests; full discovery ran 159 tests with 158 passed and 1 guarded online integration skipped.

## [2026-07-18] Complete second Task 2 consolidated remediation

### Changed

- Replaced regex-only Java credential assignment handling with Unicode-aware lexical scanning that preserves string/comment boundaries and detects sensitive identifiers independently of value syntax.
- Hardened YAML/config loading with bounded descriptor reads, regular-file and symlink refusal, duplicate-key/alias/tag rejection, path normalization, boolean precedence preservation, and strict URL-authority validation.
- Removed unbounded HTTP read fallback, normalized injected transport failures into retry exhaustion, added deadline-aware Git output collection and nonzero-runner rejection, bounded cache publication, and descriptor-relative private cache hierarchy creation for Linux/Python 3.11+.
- Added strict JSONL duplicate-key, structure, record-count, per-record, and aggregate limits; enforced artifact ID syntax/uniqueness and bounded `fact:` evidence IDs; preserved deterministic atomic publication.
- Preserved same-file relationships in provider aliases, exposed one canonical typed response schema, and strengthened fabricated-cache evidence validation with a recomputed valid HMAC.

### Verification

- Task 2 focused command passes 125 tests. Per-module discovery passes 26 artifact, 6 bounded-slice, 9 strict-growth, 21 config/CLI, and 63 DeepSeek tests.
- Full discovery passes 158 tests with 1 explicitly guarded online integration skipped. Changed Python modules/tests compile and `git diff --check` passes.
- Runtime CLI observation confirms the current Task 1/2 boundary remains parser-only: both explicit remote-consent arguments and default parsing exit 0 without analysis or network access.

## [2026-07-18] Harden Java Web DoS skill routing and dynamic validation

### Changed

- Routed bulk inventory, environment setup, probe execution, and fleet screening to `claude-haiku-4-5`; bounded semantic analysis and PoC engineering to `claude-sonnet-5`; and cross-stage reflection and final review to `claude-opus-4-8`, with evidence-coded escalation and model-usage artifacts.
- Made dynamic environment preparation reusable and autonomous within isolation boundaries, with explicit deployment classification and repair evidence required before `environment_blocked`.
- Added semantic preflight and a hard three-round PoC reflection loop that treats growth-only and no-growth observations as hypotheses to diagnose rather than final answers.
- Strengthened the user-level dynamic aggregator to discover missing results, validate status/schema/deployment/round/evidence/termination contracts, and derive verdicts centrally.

### Verification

- Added user-level skill and aggregator contract coverage for model aliases, worker-role separation, semantic preflight, the three-round cap, missing results, verdict conflicts, deployment classification, evidence paths, and split safety termination fields.
- Verified 22 focused dynamic-validation tests, Python compilation, and repository diff whitespace checks.

## [2026-07-18] Consolidate Task 2 independent-review remediation

### Changed

- Made provider response-body read failures retryable, bounded all slice/YAML/Git materialization and process output, reset inherited locks after fork, and safely create private nested cache paths.
- Added deterministic provider-facing aliases with local evidence restoration, exact final-request credential scanning with Java normalization, a complete typed prompt schema, strict formal Growth Contract artifact validation, IPv6-safe URL canonicalization, and stable malformed-URL errors.
- Exposed the Task 2 `--allow-remote-llm` consent/provenance CLI arguments without adding later-stage analyzer orchestration.

### Verification

- Added regression coverage for all verified review findings. The focused suite passes 90 tests; full discovery runs 134 tests with 133 passed and the guarded online integration skipped. Changed Python files compile and `git diff --check` passes.

## [2026-07-18] Authenticate and harden DeepSeek contract cache

### Changed

- Bound Growth Contract cache entries to the in-memory DeepSeek API key with HMAC-SHA256; cache files contain the authenticator but never the key, and unkeyed SHA-256 fields now provide integrity metadata only.
- Made cache use fail closed for unsafe local paths: cache directories must be current-user-owned `0700` directories, and lock, temporary, and entry files must be current-user-owned regular `0600` files. Directory-descriptor relative operations and `O_NOFOLLOW` are used where supported.
- Treat symlinked, permission-unsafe, or foreign-owned cache paths as cache misses with cache publication disabled, while allowing an authorized live classification to proceed. Preserved thread and cross-process single-flight behavior for safe caches.

### Verification

- Added focused cache coverage for HMAC tampering despite recomputed unkeyed hashes, wrong-key misses, owner checks, private modes, and symlinked directory, entry, and lock handling.
- Ran `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_cache_entry_requires_hmac_bound_to_the_api_key tests.test_deepseek_client.DeepSeekClientTests.test_cache_with_a_different_api_key_is_a_miss tests.test_deepseek_client.DeepSeekClientTests.test_cache_files_are_private_and_regular tests.test_deepseek_client.DeepSeekClientTests.test_symlinked_cache_directory_is_not_used tests.test_deepseek_client.DeepSeekClientTests.test_symlinked_cache_entry_is_a_miss_and_is_not_replaced tests.test_deepseek_client.DeepSeekClientTests.test_unsafe_permissions_and_lock_symlink_disable_cache_writes tests.test_deepseek_client.DeepSeekClientTests.test_cache_rejects_foreign_owner_when_lstat_is_mocked -v`, `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_same_key_process_single_flight_publishes_once_durably tests.test_deepseek_client.DeepSeekClientTests.test_same_key_thread_single_flight_makes_one_provider_request -v`, and `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_cache_entry_requires_hmac_bound_to_the_api_key -v` successfully.

## [2026-07-18] Add audited DeepSeek Growth Contract adapter

### Added

- Added an opt-in DeepSeek OpenAI-compatible Growth Contract client with strict schema validation, bounded retry policy, cache identity/integrity checks, atomic successful-response publication, and local mock coverage.
- Added a pre-network remote-source gate requiring explicit authorization, canonical public GitHub repository provenance, a full commit SHA, and a clean matching local checkout; default GitHub verification uses unauthenticated API requests and read-only Git checks, while authorization and provenance are captured only in non-secret request audit metadata.
- Restricted production provider endpoints to canonical `https://api.deepseek.com/`; loopback endpoints are permitted solely for local mocks, and all other endpoints fail before an Authorization header can be constructed.
- Added bounded-slice and Growth Contract models, constrained prompts, redaction of API keys, authorization values, and `sk-...` strings, plus a dual-guarded artificial-fixture integration test.

### Verification

- Verified with `python -m unittest tests.test_deepseek_client -v` and `python -m unittest discover -s tests -v`; default tests use localhost mocks and make no external provider request.

### Security remediation report (Task B: items 4, 5)

- Validated every LLM Growth Contract evidence reference against the static fact IDs in its bounded slice. Fabricated live references fail as `LLM_RESPONSE_SCHEMA_INVALID` before a cache write, while fabricated cached references are treated as cache misses.
- Applied strict byte, UTF-8, duplicate-key/non-finite-value, nesting, node, collection, and string limits consistently to provider-envelope, inner-contract, GitHub, and cache JSON. Reads request at most `limit + 1` bytes and map malformed, incomplete, or oversized data to controlled errors/cache misses.
- Preserved the cache HMAC and filesystem-authentication implementation without modification.

### Verification

- Verified the Task B fact-reference and JSON-boundary regressions with local mock/seam tests only; no live DeepSeek or GitHub endpoint was contacted.

### Security remediation report (Task C: items 3, 6, 7, 8)

- Validated Git object metadata before reading a source blob, rejected non-blobs and blobs over the bounded excerpt limit, and retained exact blob and excerpt hashes.
- Added the finite `MAX_LLM_RETRIES` bound at configuration and client runtime; blank API keys are accepted only while remote LLM access is disabled, while enabled access requires a nonblank environment key. YAML now rejects case and separator variants of `api_key` at every nesting level.
- Routed verifier Git commands through one hardened command form that disables fsmonitor and hooks, disables system/global configuration, replacement objects, and pagers; a local malicious `core.fsmonitor` regression confirms its helper is not executed.
- Ran `git fsck --strict --no-dangling --no-reflogs <full-sha>` through that hardened runner before any local source object access.

### Verification

- Passed focused Task C regressions with `python -m unittest tests.test_config_and_cli.ConfigTests.test_configuration_rejects_api_key_spelling_variants_at_any_depth tests.test_config_and_cli.ConfigTests.test_disabled_remote_llm_allows_a_missing_environment_key tests.test_config_and_cli.ConfigTests.test_enabled_remote_llm_requires_a_nonblank_environment_key tests.test_config_and_cli.ConfigTests.test_max_retries_has_an_explicit_upper_bound_in_cli_and_yaml tests.test_deepseek_client.DeepSeekClientTests.test_empty_api_key_is_rejected_before_verifier_or_network tests.test_deepseek_client.DeepSeekClientTests.test_runtime_config_rejects_max_retries_above_the_explicit_limit tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_hardened_git_invocation_disables_checkout_configured_helpers tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_validate_slice_rejects_oversized_git_blob_without_reading_it tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_verify_runs_strict_fsck_before_any_local_object_read -v`.

## [2026-07-18] Consolidate P0 implementation authority

### Changed

- Declared `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md` the sole implementation standard and updated repository guidance and README links accordingly.
- Hardened artifact recovery validation so a stage requires a non-empty artifact list and every artifact path is a safe relative path within the run output root.
- Completed lifecycle artifact contracts, canonical JSONL ordering, recursive YAML secret rejection, strict blank/UTF-8 JSONL failure handling, and output-root-relative artifact metadata serialization.

### Verification

- Added regression coverage for missing, empty, malformed, absolute, and escaping artifact paths during stage reuse.
- Added focused contract coverage for lifecycle artifact minima, deterministic JSONL bytes, nested YAML secrets, and strict JSONL input failures.

## [2026-07-18] Design the complete P0 analyzer

### Added

- Added the approved full-P0 analyzer design for Spring MVC, Servlet, Netty, and MQTT.
- Defined the Python and CodeQL module boundaries, versioned artifact contracts, bounded-slice DeepSeek Growth Contract, deterministic lifecycle rules, assertions 1 and 2, lifecycle certificates, recovery model, and test strategy.

### Changed

- Chose `bounded_under_modeled_assumptions` to replace the unconditional `static_safe` label during implementation; active tooling and documentation will be migrated together without a legacy compatibility mode.
- Required DeepSeek through an environment-only API key for complete P0 runs while keeping default tests network-free and provider calls auditable.

### Verification

- Reviewed the design for placeholders, internal contradictions, ambiguous verdict behavior, secret handling, and scope boundaries.
- Added P0 package, environment-only configuration, strict JSONL artifact contracts, deterministic identifiers, and resumable-stage primitives.
- Verified with `python -m unittest tests.test_config_and_cli tests.test_artifact_contracts -v` and `python -m unittest discover -s tests -v`.

## [2026-07-17] Prepare the v2 tool-development baseline

### Changed

- Restored the preserved v2 engineering specification and retired the obsolete one-time cleanup plan and Stage 0–5 research design.
- Adopted the lifecycle-centered analysis direction based on bounded slices, Growth Contracts, lifecycle evidence, and effective Guard/Bound/Release reasoning.
- Normalized paper material under `docs/paper/` and repaired active documentation links.
- Kept the existing `poc/` evidence archive unchanged and stopped implicitly admitting new disclosure logs and probes into version control.
- Added a static CodeQL batch-build foundation and a static-only batch aggregator with configuration validation and regression tests.
- Kept dynamic-validation preparation and status synchronization as explicit opt-in helpers, isolated from the ordinary v2 static pipeline.

### Verification

- Python and shell syntax checks.
- Unit tests for manifest/config validation, path handling, dry-run behavior, static aggregation, case identity, overwrite protection, and status synchronization.
- Markdown-link, JSON, gzip, and Git workspace hygiene checks.

## [2026-07-02] Reset the workspace for v2 implementation

### Changed

- Established the v2 static model:
  `Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)`.
- Preserved framework sources, CodeQL databases, PoC evidence, static-hunt results, application results, and Java Web batch results.
- Removed legacy phase-oriented analyzer implementation from the active development context.
