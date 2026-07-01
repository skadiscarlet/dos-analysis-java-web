# Security Advisory PoC: Apache SkyWalking OAP pprof collect streams can exhaust heap

## Summary

When the default OAP gRPC port 11800 is anonymously reachable and the pprof receiver uses the memory parser, multiple unfinished collect streams can allocate heap from `metadata.contentSize` before content upload and task validation. In the 1 GiB heap, 2 GiB container retest, 48 streams caused OAP exit code 3.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `apache/skywalking` |
| Local true-positive ID | `apache__skywalking-SKYWALKING-APP-STATIC-0002` |
| Dynamic batch | `new` |
| Dynamic status | `confirmed_oom` |
| Entry | `gRPC /skywalking.v10.PprofTask/collect on OAP core gRPC port 11800` |
| Required privilege | anonymous |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Open multiple bidirectional `/skywalking.v10.PprofTask/collect` gRPC streams, send metadata frames with contentSize near the default 30 MiB limit, and keep the streams unfinished.
- Root cause summary: `PprofByteBufCollectionObserver.onNext` directly allocates `ByteBuffer.allocate(contentSize)` when contentSize is within the default limit, while concurrent streams are not bounded by a default quota.
- Exploitation conditions: The OAP gRPC receiver is exposed to low-trust clients, authentication is empty, and the pprof receiver memory parser is enabled.
- Static source: `External gRPC PprofTask.collect stream on default receiver/core gRPC surface with PprofData metadata.`
- Static sink: `PprofByteBufCollectionObserver.onNext allocates ByteBuffer.allocate(contentSize) when contentSize <= pprofMaxSize.`
- Attacker-controlled driver: `PprofData.metadata.contentSize, up to default pprofMaxSize 31457280 bytes per stream.`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002
docker compose -p sw-pprof-case up -d
python3 probe.py --streams 48 --content-size 31457280 --hold-seconds 35 --stagger-seconds 0.05 --sample-interval 0.5 --out logs/probe-failure-1g-48stream-30m.json
docker compose -p sw-pprof-case down -v
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Java heap space` |
| Heap / memory evidence | `OAP JAVA_OPTS=-Xms1g -Xmx1g -XX:+ExitOnOutOfMemoryError; Docker mem_limit 2g` |
| Requests sent | `48` |
| Strict 1 GiB evidence | `java_opts=-xms1g` |
| Original log path | `logs/probe-failure-1g-48stream-30m.json` |

Evidence summary:

```text
When the default OAP gRPC port 11800 is anonymously reachable and the pprof receiver uses the memory parser, multiple unfinished collect streams can allocate heap from `metadata.contentSize` before content upload and task validation. In the 1 GiB heap, 2 GiB container retest, 48 streams caused OAP exit code 3.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- SW_AUTHENTICATION non-empty requires matching gRPC authentication token.
- Not exposing OAP core/receiver gRPC port 11800 to low-trust clients blocks the tested path.
- Disabling receiver-pprof or setting SW_RECEIVER_PPROF_MEMORY_PARSER_ENABLED=false avoids this specific heap-buffer allocation path.
- Lowering SW_RECEIVER_PPROF_MAX_SIZE reduces per-stream heap allocation.
- gRPC concurrent-call limits, rate limits, ingress policy, or per-client quotas can bound the number of held streams.
- The reproduction was repeated with a 1GiB JVM heap; larger heaps raise the stream count needed for OOM but do not add a per-client bound.

Not affected or substantially reduced risk when:

- The pprof receiver is disabled or not packaged.
- The OAP gRPC port is reachable only by trusted agents.
- gRPC authentication is enforced and the attacker lacks the token.
- The pprof receiver uses file mode instead of the memory parser for this path.
- Ingress or OAP configuration bounds concurrent collect streams and declared content size sufficiently.

## Attachments

| Field | Value |
| --- | --- |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/source_record.json | binary truth record |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/evidence.json | normalized advisory evidence |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/probe.py |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/docker-compose.yml |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/case_plan.json |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/environment.md |
| poc/apache__skywalking-SKYWALKING-APP-STATIC-0002/attachments/apache__skywalking-SKYWALKING-APP-STATIC-0002.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/logs/probe-failure-1g-48stream-30m.json |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
