# Security Advisory PoC: Presto /v1/statement abandoned submissions can exhaust the default 1 GiB heap

## Summary

When the official Presto coordinator exposes `/v1/statement` without authentication, an anonymous client can repeatedly submit roughly 700 KiB SQL statements and never poll the returned `nextUri`, causing retained Query/session state to grow until the default 1 GiB heap is exhausted.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `prestodb/presto` |
| Local true-positive ID | `prestodb__presto-PRESTO-APP-STATIC-0001` |
| Dynamic batch | `new` |
| Dynamic status | `confirmed_oom` |
| Entry | `POST /v1/statement` |
| Required privilege | anonymous |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST `/v1/statement` with `X-Presto-User`, submit unique padded SQL, and intentionally do not follow the returned queued `nextUri`.
- Root cause summary: Queued statements are stored in the `queries` map with SQL and session/header state; unpolled or unfinished queries lack an effective default retention quota.
- Exploitation conditions: `/v1/statement` is reachable by anonymous or low-trust clients, HTTP auth is disabled, and no proxy limits large SQL bodies or submission rate.
- Static source: `External POST /v1/statement with SQL body and X-Presto-* headers`
- Static sink: `presto-main/src/main/java/com/facebook/presto/server/protocol/QueuedStatementResource.java:269 queries.put(query.getQueryId(), query)`
- Attacker-controlled driver: `number of distinct POST submissions that do not poll their queued nextUri; retained bytes include SQL body up to dispatch-time maxQueryLength and parsed session/header state`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001
docker run -d --name dos-presto-prestodb-presto-static-0001 --memory=2g --memory-swap=2g -p 127.0.0.1:18080:8080 prestodb/presto:0.298.1
curl -fsS http://127.0.0.1:18080/v1/info
./probe.py
docker rm -f -v dos-presto-prestodb-presto-static-0001
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError` |
| Heap / memory evidence | `Presto image default -Xmx1G; Docker harness --memory=2g --memory-swap=2g` |
| Requests sent | `974` |
| Strict 1 GiB evidence | `-xmx1g` |
| Original log path | `logs/container_final.log` |

Evidence summary:

```text
When the official Presto coordinator exposes `/v1/statement` without authentication, an anonymous client can repeatedly submit roughly 700 KiB SQL statements and never poll the returned `nextUri`, causing retained Query/session state to grow until the default 1 GiB heap is exhausted.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- Default query.max-length is 1,000,000 characters, but the observed abandoned-initial-POST path retains the statement before dispatch-time maxQueryLength enforcement.
- The probe did not observe a pre-dispatch request-body cap below 700000 bytes.
- Enabling HTTP authentication or putting /v1/statement behind trusted network access changes attacker reachability.
- Reverse-proxy body-size, rate, or per-client request quotas can raise or remove exploitability.
- A server-side TTL/quota for unpolled queued statements would mitigate this retention path.

Not affected or substantially reduced risk when:

- /v1/statement is not reachable by anonymous or low-trust clients.
- HTTP authentication is enabled and only trusted users can submit statements.
- A proxy or gateway rejects large or high-rate statement submissions before Presto allocates Query state.
- The implementation removes or bounds unpolled queued statements independently of query dispatch completion.

## Attachments

| Field | Value |
| --- | --- |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/probe.py |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/start_commands.sh |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/case_plan.json |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/environment.md |
| poc/prestodb__presto-PRESTO-APP-STATIC-0001/attachments/prestodb__presto-PRESTO-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001/logs/container_final.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
