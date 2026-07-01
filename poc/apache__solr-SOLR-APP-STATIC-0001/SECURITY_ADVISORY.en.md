# Security Advisory PoC: Apache Solr form-urlencoded /select requests can exhaust JVM heap

## Summary

In the official Solr Docker deployment with default security disabled, an anonymous client can send a large form-url-encoded POST to a default core `/select` handler. With SOLR_HEAP=1g and a 2 GiB container, a 256 MiB form request triggered Java heap OOM and process exit.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `apache/solr` |
| Local true-positive ID | `apache__solr-SOLR-APP-STATIC-0001` |
| Dynamic batch | `new` |
| Dynamic status | `confirmed_oom` |
| Entry | `POST /solr/doscore/select with Content-Type: application/x-www-form-urlencoded` |
| Required privilege | anonymous |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: POST `application/x-www-form-urlencoded` to `/solr/{core}/select` with `q=*:*` plus many attacker-controlled parameters.
- Root cause summary: `SolrRequestParsers.parseFormDataContent` accumulates key/value bytes, decoded strings, and parameter arrays before handler execution, and the tested default path did not reject large forms below the failure threshold.
- Exploitation conditions: Solr HTTP endpoints are anonymously reachable, a core exists, and no strict `formdataUploadLimit` or proxy body limit blocks the request.
- Static source: `External POST application/x-www-form-urlencoded body to default core handlers such as /solr/{core}/select or /solr/{core}/query`
- Static sink: `SolrRequestParsers.parseFormDataContent accumulates key/value bytes, optional charset buffer entries, decoded strings, and MultiMapSolrParams arrays before handler execution`
- Attacker-controlled driver: `form body byte length, parameter count, key length, and value length`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001
docker run -d --name dos-solr-form-apache-solr-static-0001-1g --memory=2g --memory-swap=2g -e SOLR_HEAP=1g -p 127.0.0.1:28983:8983 solr:9.8.1 solr-precreate doscore
python3 probe.py --case-dir "$PWD" --container dos-solr-form-apache-solr-static-0001-1g --base-url http://127.0.0.1:28983/solr --core doscore --sizes 134217728,268435456,536870912,805306368 --request-timeout 300 --ready-timeout 60
docker rm -f -v dos-solr-form-apache-solr-static-0001-1g
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Java heap space` |
| Heap / memory evidence | `SOLR_HEAP=1g; Docker --memory=2g --memory-swap=2g` |
| Requests sent | `2` |
| Strict 1 GiB evidence | `solr_heap=1g` |
| Original log path | `logs/container_logs_after_probe.txt` |

Evidence summary:

```text
In the official Solr Docker deployment with default security disabled, an anonymous client can send a large form-url-encoded POST to a default core `/select` handler. With SOLR_HEAP=1g and a 2 GiB container, a 256 MiB form request triggered Java heap OOM and process exit.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- Validation was repeated with SOLR_HEAP=1g; larger production heaps raise the required body-size threshold.
- Default _default configset did not enforce a small formdataUploadLimitInKB in this deployment path.
- Reverse-proxy/client body limits, Solr requestParsers formdataUploadLimitInKB, authentication, rate limits, or per-client quotas can block or raise the attack cost.
- Strict binary-truth reproduction used SOLR_HEAP=1g and Docker memory/swap limits of 2g; the confirmed signal is Java heap OOM, not Docker OOMKilled.

Not affected or substantially reduced risk when:

- Solr HTTP endpoints are not reachable by low-trust clients.
- A strict form-url-encoded body-size limit rejects the request before SolrRequestParsers materializes parameters.
- Authentication/authorization, reverse proxy controls, or rate limits prevent anonymous large POST requests.

## Attachments

| Field | Value |
| --- | --- |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/probe.py |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/start_commands.sh | copied from results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/start_commands.sh |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/case_plan.json |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/environment.md |
| poc/apache__solr-SOLR-APP-STATIC-0001/attachments/apache__solr-SOLR-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/logs/container_logs_after_probe.txt |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
