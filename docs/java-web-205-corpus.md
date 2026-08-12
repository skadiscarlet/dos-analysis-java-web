# Canonical Java Web 205 Corpus

The active research corpus contains exactly **205** Java Web server/service projects selected for static resource-exhaustion DoS analysis. It is the case-insensitive repository union of the preserved canonical Java Web 200 inventory and the repositories represented by the PoC-29 benchmark: **200 + 5 previously absent repositories = 205**.

## Canonical sources

- Active machine-readable inventory: `intel/applications/java_web_205_targets.json`
- Preserved base inventory: `intel/applications/java_web_200_targets.json`
- PoC-29 case manifest: `poc/manifest.json` (29 cases across 18 repositories)
- Deterministic generator: `scripts/generate_java_web_205_inventory.py`
- Source snapshots: `frameworks/applications/<owner>__<repository>/`
- Java CodeQL databases: `databases/applications/<owner>__<repository>-db/`

The generator preserves repository identity, paths, coverage metadata, and indices 1 through 200 as recorded in the historical canonical 200 manifest, while recalculating each source fingerprint and every readiness field from the live canonical source/database pair. This permits an explicitly provenance-recorded source repin, such as ShoppingCart's correction from the upstream-unbuildable merge commit to its public pre-regression commit, without carrying a stale fingerprint from the historical manifest. It normalizes PoC repository spellings such as `owner__repository` to `owner/repository`, deduplicates case-insensitively, records 13 overlapping repositories and 5 additions, and appends exactly these five repositories:

201. `apache/druid`
202. `apache/skywalking`
203. `apache/solr`
204. `prestodb/presto`
205. `dromara/datacompare`

New rows use the standard source and database paths shown above. Dataset membership is independent of execution readiness: all 205 repositories are canonical members, and the generator strictly validates every database and its exact source-root binding rather than trusting historical marker-based `codeql_built` values.

The current published inventory is strictly ready:

- `total: 205`
- `valid_codeql_databases: 205`
- `database_incomplete_count: 0`
- `batch_ready: true`
- inventory digest: `94cda8008abaa0126eb6dfa65b7fa1c68c153086e26d427a32269bbb99e038db`

The initial 55 incomplete targets were repaired only through native Maven, Gradle, or Ant builds captured by CodeQL. Repository-specific upstream prerequisites were built from exact public revisions into run-local dependency repositories; invalid default databases were preserved in run-specific quarantine before atomic promotion. No `build-mode=none`, autobuild, bounded javac, source-only extraction, or compilation-failure acceptance counted as success. ShoppingCart is explicitly pinned to public commit `c992c54bde6af51f67d8cfec5cdba6cbcda19f6c` because the former merge commit contains an upstream missing-import regression and cannot compile unchanged.

The canonical loader now accepts all 205 targets, and a nonexecuting full-corpus plan was published under `results/java_web_dos_batch/java-web-205-ready-plan-20260810/` with plan digest `408f9d861f75fcd5560a8a9ea0af8093624a5ec193d79c1efa682c0482d931e4`.

For the PoC-29 full static benchmark, the 18 canonical analysis source/database pairs remain unchanged. Eight archive-based sources are additionally bound to clean independent public Git checkouts through `config/poc29_full_source_overrides.json`; this provider provenance does not replace or relabel the canonical database source root. The immutable nonexecuting 29-case/18-target full plan is published under `results/java_web_dos_batch/poc29-full-plan-20260810/` with plan digest `35fcae172671ea29b6ceacfeb0a99613ac2b3a3a08d7da3d1b5eaedf4c08d8a4`. It binds all 18 database fingerprints, queues all 18 targets, records `pilot_skipped=true`, and fixes the remote provider settings without storing credentials.

## Historical inventories

The Java Web 200 inventory, its repair script, its generated inventories/results, and its corpus document remain preserved historical evidence. Earlier 50-project selection work, the initial 183-project snapshot, and the 2026-07-18 intermediate 200-project run are also historical and retain their original factual counts and semantics.
