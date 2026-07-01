# Security Advisory PoC: Zipkin HTTP collector gzip-expanded spans can exhaust JVM heap

## Summary

When the default Zipkin HTTP collector is anonymously exposed, a small wire-size but highly expanded gzip Zipkin v2 spans request can trigger Java heap OOM. In the 1 GiB heap, 2 GiB container retest, a roughly 3.37 MiB gzip request expanded to about 1.356 GiB and caused container exit code 3 plus sustained `/health` 502.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `openzipkin/zipkin` |
| Local true-positive ID | `openzipkin__zipkin-ZIPKIN-APP-STATIC-0001` |
| Dynamic batch | `new_retest` |
| Dynamic status | `confirmed_oom` |
| Entry | `POST /api/v2/spans with Content-Type: application/json and optional Content-Encoding: gzip` |
| Required privilege | anonymous |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST a valid Zipkin v2 JSON span list to `/api/v2/spans` with `Content-Encoding: gzip` to amplify decompressed size.
- Root cause summary: The collector decompresses and parses the complete spans list without an effective default bound on decompressed size, span count, or gzip ratio.
- Exploitation conditions: HTTP collector is anonymously reachable, gzip is allowed, and decompressed size/span count is not limited before Zipkin decodes the body.
- Static source: `External POST /api/v2/spans or /api/v1/spans body with optional Content-Encoding: gzip`
- Static sink: `ZipkinHttpCollector.validateAndStoreSpans aggregates request, UnzippingBytesRequestConverter decodes gzip, Collector.acceptSpans decodes List<Span>`
- Attacker-controlled driver: `compressed/decompressed body byte volume and encoded span count in one request`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001
docker run --name dosval-openzipkin-zipkin-static-0001-1g -d --memory=2g --memory-swap=2g -e JAVA_OPTS='-Xms256m -Xmx1g -XX:+ExitOnOutOfMemoryError' -p 127.0.0.1:29411:9411 docker.m.daocloud.io/openzipkin/zipkin-slim:latest
python3 probe.py --base-url http://127.0.0.1:29411 --container dosval-openzipkin-zipkin-static-0001-1g --out logs/probe_results_1g_confirmed.jsonl --metrics-out evidence/metrics_snapshots_1g_confirmed.txt --mode plain --pause 1 --extra-gzip 160000:8192
docker rm -f dosval-openzipkin-zipkin-static-0001-1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Java heap space` |
| Heap / memory evidence | `JVM -Xms256m -Xmx1g -XX:+ExitOnOutOfMemoryError; Docker --memory=2g --memory-swap=2g` |
| Requests sent | `4` |
| Strict 1 GiB evidence | `-xmx1g` |
| Original log path | `logs/probe_results_1g_confirmed.jsonl` |

Evidence summary:

```text
When the default Zipkin HTTP collector is anonymously exposed, a small wire-size but highly expanded gzip Zipkin v2 spans request can trigger Java heap OOM. In the 1 GiB heap, 2 GiB container retest, a roughly 3.37 MiB gzip request expanded to about 1.356 GiB and caused container exit code 3 plus sustained `/health` 502.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- Disable external exposure of the Zipkin HTTP collector for untrusted clients.
- Reject or strictly bound gzip Content-Encoding, decompressed size, span count, per-request body size, and request rate before collector decoding.
- Ingress or Armeria request-size limits may block larger plain requests, but this 1GiB retest shows gzip decompression can reach heap pressure before an effective decompressed-size rejection.

Not affected or substantially reduced risk when:

- HTTP collector is disabled or reachable only from trusted instrumentation clients.
- Authentication, network ACLs, or gateway controls block anonymous POST /api/v2/spans.
- A front proxy or application filter enforces decompressed-size, span-count, or gzip-ratio limits before Zipkin decodes spans.

## Attachments

| Field | Value |
| --- | --- |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/probe.py |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/start_commands.sh |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/case_plan.json |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/environment.md |
| poc/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/attachments/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/logs/probe_results_1g_confirmed.jsonl |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
