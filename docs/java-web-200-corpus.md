# Canonical Java Web 200 Corpus

This preserved historical corpus contains exactly **200** Java Web server/service projects selected for static resource-exhaustion DoS analysis. The active corpus is now the 205-project union documented in `docs/java-web-205-corpus.md`; this document retains the original 200-project repair and inventory semantics.

## Canonical sources

- Machine-readable tracked inventory: `intel/applications/java_web_200_targets.json`
- Source snapshots: `frameworks/applications/<owner>__<repository>/`
- Java CodeQL databases: `databases/applications/<owner>__<repository>-db/`
- Full local generated inventory: `results/application_dbs/java_web_200_20260725/final_200_inventory.{md,csv,json}`

Historical databases retain their original build-status convention: the presence of `codeql-database.yml`. Every database created for the 2026-07 corpus expansion or repair is additionally required to contain `db-java/` and a non-empty `db-java/default/compilation_compiling_files.rel` relation. Git checkouts use their commit SHA as the source fingerprint; historical source trees without independent Git metadata use a deterministic tree SHA-256.

## Replacement of `jeecgboot/qiaoqiaoyun`

`jeecgboot/qiaoqiaoyun` is not part of the canonical corpus. Its public repository is a packaged deployment bundle containing a compiled JAR, SQL, configuration, and launch files, but no Java source files or Java build project. It therefore cannot provide a meaningful source-level Java CodeQL database.

The source snapshot remains in place as historical evidence. The canonical set replaces it with `apache/airavata`, a Java 17+ Spring Boot/Armeria service exposing gRPC and HTTP/JSON APIs for ordinary gateway users to submit and monitor computation workflows. Its job submission, transfer, monitoring, and result-retrieval paths provide relevant resource-exhaustion research surfaces. The pinned checkout and database details are recorded in the tracked inventory.

## Historical inventories

Earlier 50-project selection work, the initial 183-project snapshot, and the 2026-07-18 intermediate 200-project run are preserved for reproducibility. They are explicitly superseded and must not be used as the current target manifest. Historical scripts under `dosweb/top50/` and `scripts/*top50*` remain compatibility tools only.
