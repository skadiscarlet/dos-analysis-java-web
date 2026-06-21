---
name: java-web-dos-hunter
description: Use when hunting resource-exhaustion DoS vulnerabilities in Java Web or HTTP server projects, including Servlet, Spring, JAX-RS, Jetty, Undertow, Tomcat, Netty, filters, handlers, parsers, clients, proxies, and framework registries.
---

# Java Web DoS Hunter

## Scope

Use this skill to run a large-scale, evidence-driven hunt for Java Web resource-exhaustion DoS. The goal is to discover attacker-controlled HTTP inputs that drive unbounded memory, disk, CPU, thread, connection, session, parser, cache, or registry growth.

Do not depend on any project-specific analyzer, query pack, or verdict script. Use local tools such as `rg`, AST search, CodeQL, call graphs, dependency graphs, build metadata, and subagents when they are available, but keep the process portable.

## Operating Rule

Build inventories first, then judge paths. Do not start from a favorite vulnerability shape and search only for confirming evidence.

Every finding must identify:

- `source`: attacker-controlled HTTP data.
- `sink`: resource-consuming operation.
- `driver`: the specific value, count, size, or cardinality controlled by the attacker.
- `dimension`: distinguish count, key cardinality, byte volume, CPU work, thread count, file count, and connection count.
- `retention`: why the resource survives long enough to matter.
- `bound`: quota, limit, eviction, timeout, auth gate, or cleanup that does or does not stop growth.
- `verdict`: confirmed, likely, needs dynamic probe, or rejected.

## Workflow

1. Create a target profile.
2. Enumerate sinks broadly.
3. Enumerate sources from HTTP parsing outward.
4. Link source-to-sink paths.
5. Judge true positives.
6. Produce PoC and dynamic-probe plans for high-value candidates.

Keep intermediate outputs as CSV, JSONL, Markdown tables, or task lists. Prefer append-only records with stable IDs.

## Stage 0: Target Profile

Map the service before scanning.

Record:

- Frameworks: Servlet, Spring MVC/WebFlux, JAX-RS, Jetty, Undertow, Tomcat, Netty, Jersey, filters, proxies, WebSocket, multipart.
- Entry patterns: controller methods, servlet `service/doGet/doPost`, filters, handlers, resource methods, protocol callbacks.
- Request object types: `HttpServletRequest`, `ServerHttpRequest`, `ContainerRequestContext`, `HttpServerExchange`, Jetty `Request`, Netty `HttpRequest`, multipart abstractions.
- Lifecycle roots: static fields, application singletons, servlet/filter/handler instances, DI providers, context/session stores, connection/session managers, parser transactions, clients, registries.
- Deployment gates: auth, management endpoints, reverse-proxy-only paths, optional modules, disabled-by-default features.
- Recent risk areas: CVEs or advisories involving multipart parsing, compression, header/cookie growth, cache poisoning, proxy destinations, session/state stores, registries, async queues, HTTP/2 streams, WebDAV locks.

Use these retained-state templates when recording lifecycle evidence:

| Template | Retention evidence | Typical lifetime |
| --- | --- | --- |
| Static field | `static Map/Cache/Registry` or static holder | process |
| Java/Spring singleton | singleton bean, provider, servlet, filter, handler, manager instance with mutable field | process/component |
| Session/context store | `HttpSession`, `ServletContext`, distributed session, DB/Redis-backed state | session/process/persistent |
| Connection/client manager | client destinations, connection pools, stream maps, proxy registries | connection/process |
| Parser transaction | request parser state that can grow before request completion | request-burst |

## Stage 1: Sink Inventory

Scan all operations that can consume resources, not only obvious `Map.put`.

Prioritize these sink families:

| Family | Examples | Driver |
| --- | --- | --- |
| Collection growth | `put`, `compute`, `merge`, `add`, `offer` | key cardinality, element count |
| Cache/session/context | cache insert, `setAttribute`, token store | key, value, session id |
| Parser accumulation | multipart parts, MIME headers, form fields | part count, header count, byte volume |
| Registry/state tables | node, host, route, provider, destination, lock | name, path, host, tag, token |
| Buffer/temp storage | byte buffers, temp files, file items | byte volume, file count |
| Async/thread queues | executor submit, pending callbacks, scheduled tasks | task count, delay count |
| Network state | client destinations, connection pools, HTTP/2 stream maps | host, origin, stream id |
| CPU amplifiers | regex, decompression, parsing loops, normalization | input size, nesting, repetition |

For each sink, record:

```text
sink_id
file
line
method
operation
resource_type
driver_expr
receiver_expr
retention_hypothesis
bound_hypothesis
local_evidence
subagent_judgment
confidence
```

Delegate local sink triage to low-strength subagents when useful. Give each subagent one file or one small cluster and require only this output:

```text
For each possible resource-exhaustion sink, report:
sink_id, operation, resource_type, driver_expr, receiver_lifetime, possible_bound, why_not_noise.
Do not decide exploitability. Do not inspect unrelated files.
```

Demote sinks immediately when the receiver is clearly request-local, response-local, a builder, a test fixture, or a bounded fixed-size collection.

Treat request-header-to-response-header copying as response amplification or reflection, not retention DoS, unless the copied data is also stored in a lifecycle root outside the response.

## Stage 2: Source Inventory

Start at HTTP parsing and adapter layers, then move outward to application APIs.

Enumerate:

- Method, path, query string, path variables, matrix params.
- Headers: `Host`, `Origin`, `Referer`, cookies, auth headers, custom headers.
- Body: raw stream, JSON/XML/form fields, multipart parts, filenames, content types, part headers.
- Protocol metadata: HTTP/2 stream id, WebSocket frames, connection attributes, remote address when spoofable through proxy headers.
- Framework wrappers: request context, exchange attachments, route params, security context, resource method params.

Record:

```text
source_id
file
line
api
source_kind
value_space
attacker_control
normalization
default_limit
notes
```

Use `value_space` values:

- `stream`: arbitrary body or part stream.
- `unlimited`: attacker can create many distinct values, such as custom header values, tenant IDs, token strings, path segments, host/origin/referer values, multipart filenames, or query values used as keys.
- `large`: attacker controls size but not unbounded cardinality.
- `limited`: enum, boolean, small bounded integer, fixed header set.
- `server_controlled`: not attacker-controlled in normal deployment.

For headers, classify custom header values as `unlimited` when they drive map keys, registry names, cache keys, session attribute names, or tenant-like identifiers. Classify fixed protocol header names as `limited` unless the attacker can create many distinct names and the server retains them.

## Stage 3: Source-To-Sink Linking

Try strongest evidence first:

1. Static taint or CodeQL data flow from source expression to sink driver.
2. Bounded call path where request-derived values are passed to helper methods.
3. Field or lifecycle correlation where a request handler stores data into an object later mutated by the sink.
4. Manual/subagent-reviewed path with exact files, methods, and assignments.

Each path candidate must record:

```text
flow_id
source_id
sink_id
driver_match
path_kind
path_depth
call_path
taint_evidence
missing_link
confidence
```

Do not mark a path true positive when the only evidence is that source and sink are in the same project. If the path is plausible but incomplete, mark the intermediate path status as `needs_path_proof`; the final verdict should usually be `needs_dynamic_probe` or `rejected`, with the missing link stated explicitly.

## Stage 4: True Positive Judgment

Use these axes. Keep the labels even if the project has its own scoring system.

| Axis | High-risk condition |
| --- | --- |
| Reachability | unauthenticated, weakly authenticated, or exposed by common deployment |
| Value space | stream, unlimited cardinality, or attacker-controlled large size |
| Amplification | attacker controls distinct key/name/path/token/part/host or repeated work |
| Capacity | no hard quota, no per-client quota, no small global cap, weak eviction |
| Lifetime | request-burst OOM, session lifetime, connection lifetime, process lifetime, persistent store |

Judge each resource dimension independently. A bound on multipart `part_count` does not bound per-part `byte_volume`; a cache size limit does not necessarily bound CPU parsing work; a per-request cleanup does not bound request-burst memory if parsing can OOM before cleanup.

Classify:

- `confirmed`: source-to-sink evidence is concrete and no effective bound blocks exploitability.
- `likely`: path and bound evidence are strong but dynamic behavior is not yet measured.
- `needs_dynamic_probe`: static evidence is plausible but capacity, cleanup, or deployment gate is uncertain.
- `rejected`: request-local state, server-controlled driver, effective bound, unreachable endpoint, or non-amplifiable operation.

Treat cleanup as a real bound only when it is guaranteed on failure paths and adversarial inputs cannot outrun it.

## Stage 5: Dynamic Probe Plan

For `confirmed`, `likely`, and selected `needs_dynamic_probe` candidates, write a safe local probe plan:

```text
finding_id
request_shape
loop_variable
resource_metric
expected_growth
safety_limit
isolation_requirements
success_condition
stop_condition
```

Prefer low-risk measurements first: object count, map size, temp file count, heap slope, thread count, queue length, connection destinations. Only propose OOM tests inside an isolated local harness with explicit heap, timeout, and cleanup.

## Subagent Discipline

Use subagents for breadth, not authority.

Good delegated tasks:

- "Inspect this package for parser accumulation sinks."
- "Classify these 30 collection mutations by receiver lifetime."
- "Trace whether this request header can reach this registry key."

Bad delegated tasks:

- "Find all vulnerabilities in the project."
- "Decide whether this project is vulnerable."
- "Scan the whole repository without limits."

Require subagents to quote file paths, lines, and exact expressions. The main agent owns deduplication, final verdicts, and reporting.

## Output Report

Final reports should include:

- Target profile summary.
- Sink inventory count by family.
- Source inventory count by source kind.
- Flow candidates grouped by confidence.
- Confirmed/likely findings with evidence table.
- Rejected high-noise patterns and rejection reasons.
- Dynamic probe plan for each high-value candidate.
- Explicit gaps: modules not scanned, build failures, missing dependencies, unavailable CodeQL database, or unverified deployment assumptions.

Never hide uncertainty. A scalable hunt is useful only if weak evidence is labeled weak.
