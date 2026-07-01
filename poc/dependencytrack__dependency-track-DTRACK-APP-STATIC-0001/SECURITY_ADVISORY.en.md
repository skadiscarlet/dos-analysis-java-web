# Security Advisory PoC: Dependency-Track BOM multipart upload can trigger apiserver JVM OOM

## Summary

In the official Dependency-Track 5.0.2 compose deployment with the default 2 GiB apiserver memory limit, a low-privilege API key with BOM_UPLOAD can trigger Java heap OOM with a single roughly 768 MiB multipart BOM part; the request returns HTTP 500 and logs confirm OOM.

## Affected Project

| Field | Value |
| --- | --- |
| Project | `DependencyTrack/dependency-track` |
| Local true-positive ID | `dependencytrack__dependency-track-DTRACK-APP-STATIC-0001` |
| Dynamic batch | `new_retest` |
| Dynamic status | `confirmed_oom` |
| Entry | `POST /api/v1/bom multipart/form-data` |
| Required privilege | low-privilege account or default token/API key |
| Suggested CVSS 3.1 | `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H` |

## Technical Details

- Trigger shape: Use a BOM_UPLOAD-only API key to POST multipart/form-data to `/api/v1/bom` with a large BOM file part.
- Root cause summary: `BomResource` reads the multipart part into a `byte[]` before validation/processing and lacks a default BOM part byte limit.
- Exploitation conditions: Requires a low-privilege BOM_UPLOAD API key and an accessible project; multipart/BOM size is not capped by a proxy or application limit.
- Static source: `PUT /v1/bom JSON base64 and POST /v1/bom multipart require BOM_UPLOAD; multipart bom part is attacker-controlled by that principal.`
- Static sink: `BomResource reads decoded BOM or multipart part with IOUtils.toByteArray into byte[] before validateBom and processUpload.`
- Attacker-controlled driver: `BOM byte volume per request; repeated accepted uploads also create workflow run metadata with unique upload tokens.`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

```bash
cd results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001
docker compose -p codex_dtrack_dos_retest_0001 -f docker-compose.yml up -d
DTRACK_COMPOSE_PROJECT=codex_dtrack_dos_retest_0001 DTRACK_APISERVER_CONTAINER=codex_dtrack_dos_retest_0001-apiserver-1 DTRACK_PUT_DECODED_MIB= DTRACK_POST_PART_MIB=768 DTRACK_REQUEST_TIMEOUT=900 ./probe.py
docker compose -p codex_dtrack_dos_retest_0001 -f docker-compose.yml down -v --remove-orphans
```

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

| Field | Value |
| --- | --- |
| Failure signal | `OutOfMemoryError: Java heap space` |
| Heap / memory evidence | `Official compose apiserver memory limit 2g` |
| Requests sent | `10` |
| Strict 1 GiB evidence | `compose apiserver memory limit 2g` |
| Original log path | `logs/docker_compose_up.log` |

Evidence summary:

```text
In the official Dependency-Track 5.0.2 compose deployment with the default 2 GiB apiserver memory limit, a low-privilege API key with BOM_UPLOAD can trigger Java heap OOM with a single roughly 768 MiB multipart BOM part; the request returns HTTP 500 and logs confirm OOM.
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

- BOM upload requires an authenticated principal with BOM_UPLOAD.
- Limit multipart body size, BOM part size, upload rate, and per-project/per-user upload quota before BomResource accumulates the stream.
- Avoid granting BOM_UPLOAD to low-trust users or restrict it to trusted automation paths.
- A reverse proxy or gateway body-size limit below the observed threshold would block this proof.

Not affected or substantially reduced risk when:

- No low-privilege principal has BOM_UPLOAD.
- No accessible project exists for the API key.
- Ingress rejects large multipart requests before they reach the apiserver.
- The application enforces a strict BOM byte limit before IOUtils.toByteArray materializes the part.

## Attachments

| Field | Value |
| --- | --- |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/source_record.json | binary truth record |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/evidence.json | normalized advisory evidence |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/source_result.json | copied dynamic result.json content |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/probe.py | copied from results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/probe.py |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/docker-compose.yml | copied from results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/docker-compose.yml |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/case_plan.json | copied from results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/case_plan.json |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/environment.md | copied from results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/environment.md |
| poc/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/attachments/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001.log.gz | gzip copy of results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/logs/docker_compose_up.log |

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
