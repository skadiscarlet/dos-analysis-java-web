# Static Hunt Dynamic Verification Design

Date: 2026-06-20

## Goal

Validate non-`WEB-REAL-*` candidates from
`results/static_hunts/static_hunt_manual_review_spec_2026-06-20.md` with a
strict true-positive bar: a candidate can be promoted only when real HTTP
requests make the server-side JVM hit an out-of-memory condition.

Existing `WEB-REAL-*` findings are not rerun in this pass. They remain stable
anchors unless a later evidence-refresh task explicitly targets them.

## True-Positive Standard

A dynamic true positive requires all of the following:

- The probe starts a real embedded HTTP service for the target framework.
- The attack path enters through HTTP requests, not direct calls into sinks.
- The service JVM produces a clear heap OOM signal, either as
  `OutOfMemoryError` in the log or as a structured verdict such as
  `CONFIRMED_HEAP_OOM_REAL_HTTP`.
- The log records enough request-count and retained-resource evidence to tie
  the OOM to attacker-controlled HTTP input.

The following are not sufficient for true-positive promotion:

- Static source-to-sink evidence only.
- Monotonic growth that does not reach server OOM.
- Disk growth without service heap OOM.
- Request-local buffering that completes normally or is cleaned up.
- App-dependent paths without a concrete reachable HTTP endpoint.

## Candidate Scope

### First Batch

`TOMCAT-STATIC-0003` tests whether WebDAV `PROPPATCH` can drive the default
`MemoryPropertyStore` dead-property map to process-lifetime heap growth and
server OOM through attacker-controlled paths and property names.

`JETTY-STATIC-0002` tests whether `PushSessionCacheFilter` can retain global
path cache entries and same-host `Referer` associations until server OOM.

`JETTY-STATIC-0004` tests whether `PushCacheFilter` primary-resource keys are
unbounded even when `_maxAssociations` limits only child associations.

`UNDERTOW-STATIC-0003` tests whether multipart parsing can create server heap
OOM through real multipart HTTP requests. If it only fills temp storage or
cleans up after each request, it stays below the true-positive bar.

### Pre-Screen Before Harness Work

`TOMCAT-STATIC-0002` is reviewed for default connector/body/XML parser limits
and `doProppatch` body-buffering behavior. It gets an OOM harness only if the
review shows a plausible real HTTP heap-OOM path.

`SB-STATIC-0001` is reviewed for concrete WebFlux multipart endpoint
requirements and default body/part/disk limits. Without a reachable endpoint
and heap-OOM path, it remains `needs_dynamic_probe` or `needs_path_proof`.

`JETTY-STATIC-0003`, `JERSEY-STATIC-0003`, and `SB-STATIC-0002` are deferred
unless source review supplies the missing reachable path proof.

## Harness Architecture

New probes follow the existing Maven harness style under
`dynamic-verification/src/main/java/org/example/dos/dynamic/`.

Each probe provides:

- A smoke profile that completes and records baseline growth metrics.
- An OOM profile that loops until the server OOMs or a conservative guard fails.
- A real embedded server using the relevant framework implementation.
- A real HTTP client workload with attacker-controlled paths, headers,
  referers, multipart parts, or XML bodies.
- Structured log key-value lines for the Python runner.

The runner should avoid mixing this static-hunt pass with existing `WEB-REAL-*`
execution. Static-hunt logs and summaries are written under
`results/static_hunts/dynamic_verification/`.

## Output Format

The summary file is:

`results/static_hunts/dynamic_verification/static_hunt_dynamic_verification_summary.json`

Each record contains:

- `candidate_id`
- `status`
- `verdict`
- `oomSignal`
- `heap`
- `requestsSent`
- `retainedMetric`
- `log`
- `notes`

Expected statuses are:

- `verified` when real HTTP server OOM is confirmed.
- `completed_without_oom` when smoke or bounded execution completes.
- `not_verified` when the probe runs but does not meet the OOM bar.
- `blocked_path_proof` when no concrete HTTP path exists yet.
- `blocked_bounded` when default limits prevent the intended growth.

## Validation

Implementation changes must run the narrowest relevant checks:

- Maven compile/package for `dynamic-verification/`.
- Smoke profile for each new probe before any OOM run.
- OOM profile for candidates selected for promotion.
- `python3 scripts/check_phase3_consistency.py`
- `python3 scripts/check_web_real_regression.py`

If a candidate cannot be run to OOM, the final review note must state the exact
missing proof or bound.

## Documentation And Change Control

Every project modification updates `CHANGELOG.md`.

New true positives are not added to `WEB-REAL-*` automatically. Promotion
requires a separate catalog update that records stable ID, affected component,
entry, source, sink, five axes, limitations, PoC path, and OOM log path.

Existing user or local changes in `.gitignore`, `CHANGELOG.md`, `skills/`, and
ignored result directories must be preserved.
