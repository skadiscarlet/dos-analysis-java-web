---
name: java-web-dos-dynamic-validator
description: Use when dynamically validating Java Web resource-exhaustion DoS candidates from prior static-analysis outputs, dynamic_validation_queue.jsonl, findings.jsonl, or static result reports. Orchestrates subagents to prepare default-deploy environments, run services with Docker or release packages, seed required data or low-privilege accounts, execute controlled HTTP/protocol probes, and write machine-readable exploitability results with explicit utilization conditions to a target folder.
---

# Java Web DoS Dynamic Validator

## Mission

Validate a previous Java Web DoS static-analysis result in an isolated default-deployment environment. Inputs are a static result file and a target output folder. The deliverable is not chat text; write reproducible dynamic evidence under the target folder, including the environment recipe, data preparation, probe steps, resource observations, exploitability judgment, and required utilization conditions.

Use subagents for case execution. The main agent normalizes input, spawns bounded workers, verifies their files, and aggregates results. Each worker owns exactly one candidate unless the user asks for a different split.

## Scope Defaults

Use these defaults unless the user explicitly overrides them:

- `deployment_model`: official Docker image, official quickstart compose, release package, or documented default start command.
- `attacker_model`: anonymous or ordinary low-privilege HTTP/protocol client.
- `dynamic_goal`: prove or disprove service unavailability under default deployment, not maximize damage.
- `evidence_threshold`: confirmed true positive requires externally triggered OOM, GC death, watchdog/restart, thread/connection pool exhaustion, sustained HTTP unavailability, or equivalent target-JVM resource failure.
- `growth_only`: keep as `observed_growth_not_confirmed`; do not promote to confirmed DoS.
- `config_change`: record separately. Do not mix non-default config into default exploitable claims.
- `safety`: run only local or disposable targets; cap request count, duration, heap, disk, and container resources; stop on first strong failure signal.

## Inputs

Accept any of these as the static result file:

```text
dynamic_validation_queue.jsonl
findings.jsonl
aggregate_findings.jsonl
aggregate_dynamic_probe_plan.jsonl
all_candidates_dynamic_validation.md
STATIC_DOS_HUNT_REPORT.md
summary.md with linked JSONL files
```

Preferred record fields:

```text
target, slug, repo_path, static_output_dir, finding_id, probe_id, title,
verdict, resource_dimension, source, sink, driver, request_shape,
parameters, loop_variable, resource_metric, expected_growth,
safety_limit, success_condition, stop_condition, cleanup,
evidence, missing_evidence
```

If the input is Markdown, extract candidate IDs, target names, endpoint hints, request shapes, expected resource, and referenced static files. If extraction is ambiguous, create a `paused` case with `missing_static_fields` instead of inventing facts.

The second required input is the target output folder. Create it if missing.

## Output Layout

Write all dynamic validation artifacts under the user-provided target folder:

```text
manifest.normalized.jsonl
validation_status.jsonl
summary.json
summary.csv
findings.jsonl
blocked_or_rejected.jsonl
DYNAMIC_VALIDATION_REPORT.md
cases/<case_id>/
  case_plan.json
  environment.md
  docker-compose.yml or start_commands.sh when used
  data_prep.md
  probe.sh or probe.py
  result.json
  logs/
  evidence/
```

Never write dynamic results back into the static-analysis source folder unless that folder is the explicit target folder.

## Case IDs

Use a stable case id:

```text
<slug>-<finding_id or probe_id>
```

Sanitize to `[A-Za-z0-9_.-]`. Preserve original `finding_id` and `probe_id` in JSON.

## Result Schema

Each worker must write `cases/<case_id>/result.json` as one JSON object:

```json
{
  "case_id": "target-FINDING-0001",
  "target": "owner/repo or product",
  "slug": "owner__repo",
  "finding_id": "FINDING-0001",
  "probe_id": "PROBE-0001",
  "status": "confirmed_oom",
  "verdict": "confirmed",
  "resource_dimension": "memory",
  "default_deployment": {
    "is_default": true,
    "source": "official_docker_image|official_compose|release_package|documented_quickstart|local_build",
    "image_or_version": "image:tag or release",
    "commands": [],
    "config_changes": [],
    "non_default_reason": null
  },
  "reachability": {
    "attacker_model": "anonymous|low_privilege|admin|operator|unknown",
    "entry": "HTTP method/path or protocol entry",
    "auth_required": false,
    "account_used": null,
    "network_exposure": "external_http_default",
    "required_roles": []
  },
  "data_preparation": {
    "required": false,
    "steps": [],
    "seed_data": [],
    "low_privilege_account": null,
    "default_credentials_used": false
  },
  "trigger": {
    "request_shape": "curl/protocol shape",
    "parameters": {},
    "loop_variable": "host|path|body_size|part_count|...",
    "request_count": 0,
    "duration_seconds": 0,
    "bandwidth_notes": null
  },
  "resource_observation": {
    "metric": "heap|rss|threads|connections|gc|http_availability",
    "baseline": null,
    "peak": null,
    "failure_signal": "OutOfMemoryError|GC overhead|restart|timeout|5xx_sustained|none",
    "log_paths": [],
    "evidence_paths": []
  },
  "utilization_conditions": {
    "summary": "短句说明利用条件",
    "requires_default_exposure": true,
    "requires_low_privilege_account": false,
    "requires_admin": false,
    "requires_config_change": false,
    "requires_optional_component": false,
    "requires_seed_data": false,
    "limits_or_mitigations": [],
    "not_affected_when": []
  },
  "safety": {
    "request_cap": null,
    "time_cap_seconds": null,
    "heap_or_container_limit": null,
    "stop_condition_hit": true,
    "cleanup_done": true
  },
  "static_traceability": {
    "static_result_file": "path",
    "source": "static source summary",
    "sink": "static sink summary",
    "driver": "static driver summary",
    "missing_static_evidence": []
  },
  "notes": []
}
```

Allowed `status` values:

```text
confirmed_oom
confirmed_gc_death
confirmed_restart
confirmed_thread_exhaustion
confirmed_connection_exhaustion
confirmed_sustained_unavailable
observed_growth_not_confirmed
not_reproduced
precondition_blocked
environment_blocked
auth_blocked
default_not_reachable
non_default_only
probe_error
skipped
paused
```

Map `status` to `verdict`:

- `confirmed_*` -> `confirmed`
- `observed_growth_not_confirmed`, `not_reproduced` -> `not_confirmed`
- `*_blocked`, `non_default_only`, `probe_error`, `skipped`, `paused` -> same status or `blocked`

Every result must include `utilization_conditions.summary`. This is the field that explains exploitation conditions in human terms.

## Main-Agent Workflow

1. Resolve repository root and the user-provided output folder.
2. Normalize the static input into `manifest.normalized.jsonl`.
3. Pick candidates for execution. Prefer `likely`, `confirmed`, and `needs_dynamic_probe`; skip rejected records unless the user explicitly asks.
4. Spawn subagents with controlled concurrency. Default `max_concurrency` is `2`; use `1` for heavy Docker targets; never exceed `4` unless the user explicitly accepts local resource contention.
5. While workers run, prepare aggregation scaffolding and review completed case files.
6. Validate each worker output:
   - `case_plan.json`, `environment.md`, `data_prep.md`, and `result.json` exist.
   - `result.json` parses and includes `status`, `verdict`, `default_deployment`, `reachability`, `trigger`, `resource_observation`, `utilization_conditions`, and `static_traceability`.
   - evidence paths are relative to the case directory or absolute existing paths.
7. Retry a malformed or missing-result case once with a focused correction prompt. Do not retry destructive probes repeatedly.
8. Aggregate with:

```bash
python <skill_dir>/scripts/aggregate_dynamic_validation.py --output-root <target_folder>
```

If the script is unavailable, manually write equivalent `summary.json`, `summary.csv`, `findings.jsonl`, `blocked_or_rejected.jsonl`, and `DYNAMIC_VALIDATION_REPORT.md`.

## Worker Prompt Template

For each case, spawn one subagent. Attach this skill as a skill item if the tool supports skill attachments. Use this prompt shape:

```text
Use $java-web-dos-dynamic-validator worker protocol to dynamically validate one Java Web DoS candidate.

You are not alone in the repository. Do not revert edits made by others. Write only under this case directory:
<absolute_output_root>/cases/<case_id>/

Static candidate:
<compact JSON object from manifest.normalized.jsonl>

Required work:
1. Prepare an isolated default-deploy environment for the target application or component.
   - Prefer official Docker image, official compose, release package, or documented quickstart.
   - Prefer China-friendly mirrors when downloading: use existing Docker registry mirrors if configured; prefer official images mirrored by registry.cn-hangzhou.aliyuncs.com, docker.m.daocloud.io, mirror.ccs.tencentyun.com, or other reachable accelerators only when they preserve the same upstream image/tag.
   - For Maven/Gradle builds, prefer repository-local settings first; otherwise use Aliyun/Tencent/Huawei mirrors without changing target source semantics.
   - Record exact image, tag, digest if available, commands, ports, heap/container limits, and every config change.
2. Run the service and wait for readiness. Save startup logs.
3. Prepare required data or low-privilege account only when needed for the candidate.
   - Prefer documented default credentials or public signup flows.
   - If admin bootstrap is required only to create a normal user or seed ordinary data, record it in data_preparation and do not claim anonymous exploitability.
4. Execute a controlled probe derived from the static candidate.
   - Use HTTP/protocol requests from outside the target JVM/container.
   - Cap requests, duration, body size, and concurrency.
   - Stop immediately on OOM, restart, sustained unavailability, or configured stop condition.
5. Capture evidence: request script, HTTP responses, target logs, docker stats or JVM metrics, ps/top/jcmd output when available, and availability checks.
6. Clean up containers/processes created for this case unless preserving them is necessary and explicitly noted.
7. Write case_plan.json, environment.md, data_prep.md, probe.sh or probe.py, logs/evidence files, and result.json using the required schema.

Do not:
- attack third-party services or production systems;
- silently edit application source or enable non-default vulnerable features;
- mark growth-only behavior as confirmed;
- omit utilization_conditions.summary.

Final response:
Return compact JSON with case_id, status, verdict, result_json, confirmed_failure_signal, utilization_conditions_summary, and any cleanup risk.
```

## Docker And Environment Guidance

Prefer reproducible commands over manual steps:

- Use `docker compose` when the official project provides compose.
- Use pinned image tags, not floating `latest`, unless the official quickstart only provides `latest`; record that fact.
- Set memory limits deliberately for reproduction, for example `--memory 384m` or compose `mem_limit`, but record that this is a test harness limit. Do not call it a production default if it is not.
- If the service requires dependencies such as MySQL, PostgreSQL, Redis, Kafka, RocketMQ, or Elasticsearch, use official companion images from the quickstart or matching documented versions.
- If a China mirror serves a stale or altered image, fall back to the upstream official image and record download issues in `environment.md`.
- Keep host paths under the case directory when possible. Avoid mounting repository roots writable into containers unless the application requires it.

## Exploitability Judgment

Use this decision table:

| Dynamic evidence | Default reachability | Result |
| --- | --- | --- |
| OOM, GC death, restart, pool exhaustion, or sustained HTTP unavailable | anonymous or low privilege under default deployment | `confirmed_*` |
| Same failure only after enabling optional feature or changing config | non-default | `non_default_only` |
| Clear resource growth but no failure before safety cap | default reachable | `observed_growth_not_confirmed` |
| Probe executes but no meaningful growth or failure | default reachable | `not_reproduced` |
| Cannot start official/default service because dependency or image is unavailable | unknown | `environment_blocked` |
| Endpoint requires admin/operator or management exposure | admin/operator | `auth_blocked` or `default_not_reachable` |
| Candidate needs business data or account that cannot be created through default flows | unknown | `precondition_blocked` |

The utilization conditions must mention:

- exact entry and attacker privilege;
- default deployment source;
- required optional component, feature flag, seeded data, or low-privilege account;
- observed or inferred bounds: body limit, quota, TTL, rate limit, auth, per-user/per-IP limit, cache eviction, container heap;
- conditions that make the target not affected.

## Aggregation Rules

`findings.jsonl` contains only cases with `status` beginning with `confirmed_` or `observed_growth_not_confirmed`. `blocked_or_rejected.jsonl` contains all other terminal statuses. `DYNAMIC_VALIDATION_REPORT.md` must include:

- input file and output root;
- candidate totals by status and verdict;
- confirmed cases table with `case_id`, target, entry, trigger, failure signal, and utilization conditions;
- blocked/not reproduced table with reason;
- environment notes, mirror/download issues, and cleanup notes;
- explicit statement that static candidates not dynamically confirmed remain unconfirmed.

## If Subagents Are Unavailable

Do not pretend dynamic validation happened. Create:

```text
manifest.normalized.jsonl
validation_status.jsonl
DYNAMIC_VALIDATION_PLAN.md
```

`DYNAMIC_VALIDATION_PLAN.md` must contain one worker prompt per case, recommended concurrency, and exact case directories. Mark every case `paused` with `failure_reason: subagent_unavailable`.

## Final Response

Keep the final response short and point to files:

- output root;
- counts by `confirmed`, `observed_growth_not_confirmed`, `not_confirmed`, `blocked`, and `probe_error`;
- path to `DYNAMIC_VALIDATION_REPORT.md`;
- validation or cleanup gaps.

Do not paste full PoC logs into chat.
