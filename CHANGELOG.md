# dos-analysis-web v2 CHANGELOG

## [2026-08-12] Validate Dependency-Track dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `dependencytrack__dependency-track` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, compose/bootstrap files, startup logs, container inspect data, scoped auth/data bootstrap evidence, per-case plans, semantic preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official Dependency-Track quickstart-equivalent image set (`ghcr.io/dependencytrack/apiserver:5.0.4`, `ghcr.io/dependencytrack/frontend:5.0.4`, `postgres:18-alpine`) in an isolated local compose stack. Two targeted compatibility-only mechanical repairs were required before readiness: remapping the PostgreSQL 18 bind mount from `/var/lib/postgresql/data` to `/var/lib/postgresql`, and switching removed v4/v5 transitional database environment variable names to the exact v5 `DT_DATASOURCE_DEFAULT_*` keys expected by the apiserver.
- Completed the default first-login password change for `admin/admin`, then used only official REST APIs to create the low-privilege `dosval_user`, scoped `DosvalTeam`, team API key, and an accessible `dosval-project` so the queued authenticated routes could be exercised without changing target business code.
- Classified `dependencytrack__dependency-track-DTRACK-APP-STATIC-0001` as `not_reproduced_under_tested_bounds` because the low-privilege scoped API key reached `PUT /api/v1/bom` and all bounded stepped JSON BOM uploads up to roughly 100 KiB decoded content were accepted with `200` responses and import tokens, but no default rejection bound, target-specific growth signal, or service-failure evidence was observed in the conservative single-request staircase.
- Classified `dependencytrack__dependency-track-DTRACK-APP-STATIC-0004` as `not_reproduced_under_tested_bounds` because the same scoped API key reached `POST /api/v1/vex` and all bounded stepped multipart VEX uploads up to roughly 100 KiB decoded content were accepted with `200` responses and import tokens, but no multipart rejection bound, target-specific growth signal, or service-failure evidence was observed in the conservative single-request staircase.
- The required aggregate step will still be executed after artifact publication for this group; existing evidence indicates the shared aggregator may continue to exit with status `1` and no diagnostics on this output root, so the worker preserved all case/environment artifacts and updated `validation_status.jsonl` directly.

### Verification

- Launched the official quickstart-equivalent image set locally with isolation-only host port remapping and bounded resources; captured both initial startup failures and repaired ready-state evidence under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/dependencytrack__dependency-track-default/`.
- Verified default API/frontend readiness, admin first-login force-change semantics, scoped low-privilege project access, and bounded accepted BOM/VEX upload responses under the two Dependency-Track case directories.

## [2026-08-12] Validate GoCD dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `gocd__gocd` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, startup logs, container inspect data, per-case plans, semantic preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official `gocd/gocd-server:v26.1.0` Docker image locally in isolation. The first attempt failed because a bind-mounted `/godata` path was not writable by the container entrypoint, so one targeted mechanical repair switched only the persistence mount to a Docker named volume and the default image then became ready on `http://127.0.0.1:18153/go`.
- Classified `gocd__gocd-F-GOCD-V2HP-001` as `observed_growth_not_confirmed` because anonymous fresh requests to `/go/api/v1/health` repeatedly received new `JSESSIONID` cookies while a cookie-reusing control stopped receiving fresh cookies, confirming pre-auth session creation semantics without collecting internal Jetty session-cardinality or failure evidence.
- Classified `gocd__gocd-F-GOCD-V2HP-002` as `not_reproduced_under_tested_bounds` because tiny anonymous POSTs to `/go/api/webhooks/github/notify` and `/go/api/webhooks/hosted_bitbucket/notify` reached HMAC-mismatch rejection in the default deployment, but the bounded probe did not escalate body size or observe any resource-failure signal.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status `1` and no diagnostics on this output root, so the GoCD worker preserved all artifacts and updated `validation_status.jsonl` directly after executing the required aggregation step.

### Verification

- Launched the official GoCD server image locally with isolation-only host port remapping and bounded container resources; captured startup failure evidence for the unwritable bind mount, then captured ready-state HTTP probes plus final container logs under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/gocd__gocd-default/`.
- Executed bounded anonymous health-route cookie probes and tiny invalid-signature webhook probes, and captured Set-Cookie behavior plus 401 mismatch responses under the two GoCD case directories.

## [2026-08-12] Validate Ant Media dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `ant-media__ant-media-server` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including official-image environment inventory, feasibility, readiness, snapshot, startup logs, container inspect evidence, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Attempted the repository-native packaged build path first, but the checked-in source snapshot could not resolve the required `io.antmedia:parent:4.0.0-SNAPSHOT` parent POM; to stay within default-deployment guidance, the worker then switched to the official `antmedia/community:latest` Docker image rather than editing build files or target code.
- Confirmed that the official community image boots successfully in isolation and auto-deploys the `live`, `WebRTCApp`, and `LiveApp` contexts on HTTP port `5080`, resolving the earlier static uncertainty about packaged route availability.
- Classified `ant-media__ant-media-server-AMS-V2HP-UNKNOWN-001` as `default_not_reachable` because the default `live` app does deploy `ChunkedTransferServlet` on `/chunked/*` and `*.m4s`, but the first tiny external HTTP POST was rejected by the default `IPFilter` with `403 Not allowed IP` before `AtomParser` execution could be observed.
- Classified `ant-media__ant-media-server-AMS-V2HP-UNKNOWN-002` as `not_reproduced_under_tested_bounds` because the default `live` websocket endpoint accepted an anonymous publish handshake and started the adaptor lifecycle, yet the bounded single-session probe observed immediate stop/cleanup after close and no persistent retained thread or adaptor growth.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status 1 and no diagnostics on this output root, so the Ant Media worker preserved all artifacts and updated `validation_status.jsonl` directly after running the required aggregation step.

### Verification

- Pulled and launched the official `antmedia/community:latest` Docker image locally with isolation-only port remapping and bounded container resources; captured startup logs, container inspect output, deployed `web.xml` route mappings, and HTTP readiness probes under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/ant-media__ant-media-server-default/`.
- Executed a bounded tiny `ChunkedTransferServlet` POST preflight and a raw WebSocket upgrade plus single publish-command lifecycle probe, and captured the `403 Not allowed IP`, HTTP `101` upgrade, websocket `start` reply, and post-close cleanup log evidence under the Ant Media case directories.

## [2026-08-12] Validate OpenKM dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `openkm__document-management-system` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including official-image environment inventory, feasibility, readiness, snapshot, runtime configuration capture, changes, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official `openkm/openkm-ce:latest` Docker image locally in isolation, confirmed the default admin login, and created one ordinary `ROLE_USER` account through the authenticated REST admin API so the queued low-privilege routes could be exercised without changing target business code.
- Classified `openkm__document-management-system-F-OPENKM-002` as `observed_growth_not_confirmed` after a bounded single-request staircase with unique ZIP archives showed clear entry-count-driven latency growth on `/frontend/FileUpload?importZip=true`, but no sustained unavailability or explicit target-resource failure.
- Classified `openkm__document-management-system-F-OPENKM-003` as `not_reproduced_under_tested_bounds` because the default authenticated frontend converter admitted two concurrent `toPdf` requests and executed `soffice`, yet no timeout, lingering process retention, or service degradation appeared under the bounded concurrency-2 probe.
- Classified `openkm__document-management-system-F-OPENKM-004` as `not_reproduced_under_tested_bounds` because the default authenticated REST `doc2pdf` endpoint accepted two concurrent valid multipart DOCX conversions and returned PDFs without provider rejection or target-resource failure under the bounded concurrency-2 probe.
- Recorded that the shared `aggregate_dynamic_validation.py` script still exits with status 1 and no diagnostics on this output root, so the OpenKM worker preserved all artifacts and updated `validation_status.jsonl` directly after running the required aggregation step.

### Verification

- Pulled and launched the official OpenKM image locally, captured container logs plus runtime `OpenKM.cfg` and `OpenKM.xml`, verified low-privilege frontend and REST authentication, and enumerated seeded root documents for converter probes.
- Executed bounded unique-entry ZIP import probes plus concurrent frontend and REST DOCX-to-PDF conversion probes, and captured timing, HTTP headers, PDF outputs, route responses, and server-side converter evidence under the OpenKM case directories.

## [2026-08-12] Validate Rill Flow dynamic group startup feasibility

### Changed

- Added isolated dynamic-validation artifacts for the `weibocom__rill-flow` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, startup logs, container inspect evidence, per-case plans, blocked preflights, reflections, and terminal result files.
- Bootstrapped the documented official compose quickstart twice in a local isolated environment. The first attempt failed on a host `8080` port collision, so a case-local compose copy remapped only the host ports while preserving the documented images and environment variables.
- Applied one targeted dependency-side mechanical repair by mounting a readable case-local copy of `setup.sql` after the checked-in MySQL bind mount failed with `Permission denied` during initialization.
- Conservatively classified `weibocom__rill-flow-F-001`, `weibocom__rill-flow-F-002`, and `weibocom__rill-flow-F-003` as `environment_blocked` because the official `weibocom/rill-flow:latest` backend image never reached readiness: Tomcat/Spring Boot startup aborted in OpenTelemetry/Micrometer system-metrics initialization with a cgroup-related `NullPointerException`, so no route-level semantic preflight could begin.

### Verification

- Pulled and launched the documented compose images locally, captured compose/container state, backend startup logs, MySQL startup logs, and container inspect output under `results/applications_dynamic_validation/java_web_46_candidates_20260812/environments/weibocom__rill-flow-default/`.
- Verified that the dependency-side SQL readability issue could be repaired in isolation, but the backend startup crash remained and prevented any successful HTTP probe to `/flow/trigger/add_trigger.json` or `/flow/submit.json`.

## [2026-08-12] Validate Concord dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `walmartlabs__concord` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including compose-based environment inventory, feasibility, readiness, snapshot, changes, bootstrap records, per-case plans, preflights, observations, evidence, reflections, and terminal result files.
- Bootstrapped the official Concord compose quickstart in an isolated local environment with a deterministic admin token only for reproducible first-start authorization, then created one ordinary local user and API key to exercise the queued authenticated routes without changing target business code.
- Classified `walmartlabs__concord-fnd1`, `walmartlabs__concord-fnd2`, and `walmartlabs__concord-fnd3` as `not_reproduced_under_tested_bounds` after bounded default-route probes observed successful request handling but no attributable resource failure or meaningful degradation under the safe attachment/log payloads.
- Classified `walmartlabs__concord-fnd4` as `probe_semantics_failed` because the multipart form route was reached but the crafted JSON field payload failed the form schema before becoming a semantically valid stress case.
- Classified `walmartlabs__concord-fnd5` as `probe_semantics_failed` after a two-step WebSocket preflight: the first attempt exposed required Concord agent headers, and the corrected second attempt proved deserializer reachability but failed on a missing `messageType` semantic requirement instead of a size-bound or resource effect.
- Recorded that the central `aggregate_dynamic_validation.py` script currently exits with status 1 on this shared output root without emitting diagnostics, so the Concord worker preserved all case/environment artifacts and updated `validation_status.jsonl` directly for manual or controller-side re-aggregation.

### Verification

- Launched the official `docker-images/compose/docker-compose.yml` stack locally, captured compose/server logs, verified authenticated access with the isolated admin token, created an ordinary API key, and started reusable test processes plus a v2 log segment for route-specific probes.
- Executed bounded probes for attachment ZIP upload, v1 log append, v2 log-segment append, multipart form submission, and WebSocket upgrade/message handling; captured route responses and server-side error evidence under the Concord case directories.

## [2026-08-12] Validate Stirling PDF dynamic group startup feasibility

### Changed

- Added isolated dynamic-validation artifacts for `stirling-tools__stirling-pdf` under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including environment inventory, feasibility, readiness, snapshot, changes, crafted PDF probe input, preflight, observations, reflection, and terminal result files.
- Bootstrapped the official `docker.stirlingpdf.com/stirlingtools/stirling-pdf:latest` image in documented login-disabled Docker mode and attempted one targeted mechanical repair by increasing startup memory headroom.
- Conservatively classified `stirling-tools__stirling-pdf-F-vulnerable-decompression` as `environment_blocked` because the official image terminated during startup with `OutOfMemoryError: Metaspace` before any readiness or route-level semantic validation could occur.

### Verification

- Pulled and launched the official latest image locally with isolated port remapping and case-local config/log volumes; captured startup logs, container inspect state, and failed readiness evidence for both bootstrap attempts.
- Generated a bounded valid `FlateDecode` PDF probe artifact and recorded that the prepared single-request probe only encountered connection refusal because the service never became healthy.

## [2026-08-12] Validate Hackpad dynamic group outcomes

### Changed

- Added isolated dynamic-validation artifacts for the `dropbox__hackpad` environment group under `results/applications_dynamic_validation/java_web_46_candidates_20260812/`, including default Docker environment inventory/feasibility/readiness snapshots and per-case plans, preflights, observations, evidence, reflections, and terminal results.
- Confirmed that the documented default Hackpad Docker deployment boots successfully under isolation, but the modeled anonymous comet transport is not default-reachable in this setup: `/comet` returns `404` and `/newcomet` redirects to sign-in, so `dropbox__hackpad-F-HACKPAD-COMET` was conservatively classified as `default_not_reachable`.
- Added a case-local component harness for `ExpiringMapping` to validate the Hackpad session sink semantics, showing one retained entry per novel ES2-like identifier plus lazy expiry on subsequent mutation; because this stayed mechanism-level and non-destructive, `dropbox__hackpad-F-HACKPAD-SESSION` remains `observed_growth_not_confirmed` rather than a confirmed target failure.

### Verification

- Built the official Hackpad Dockerfile, launched the documented volume-mounted quickstart locally, verified HTTP root reachability with the application's expected `Host` header, and captured route-specific evidence for `/comet` and `/newcomet`.
- Compiled and ran a local JDK 21 harness against the repository's `infrastructure/net.appjet.common/util/ExpiringMapping.java` to record retained-cardinality and lazy-expiry evidence for the session case.

## [2026-08-10] Bind batch plans to exact CodeQL databases

### Changed

- New batch plans now bind each target's validated CodeQL database fingerprint into the immutable plan digest and per-target binding while retaining load compatibility for historical plans that predate this field.
- Batch execution revalidates fingerprint-bound databases and their exact source-root correspondence before creating the target pipeline, so a database replaced after plan publication fails closed before CodeQL or a remote provider is invoked.
- The PoC-29 evaluator now reflects the repaired 18/18 default databases and can request a strict full plan that pins `deepseek-v4-pro`, temperature `0`, the DeepSeek base URL, 60-second timeout, three retries, explicit plan-time remote intent, and `pilot_skipped=true`. It refuses to publish the plan unless all 18 targets are provider-eligible and queued.
- PoC-29 corpus conversion now carries the validated CodeQL database fingerprint rather than the database-marker digest into batch targets.
- Strict PoC source overrides can bind a tree-attested analysis source/database pair to a separate clean public Git checkout only when the checkout HEAD, origin, clean state, full commit, canonical GitHub URL, and excluded-path tree digest all match. The provider checkout and commit are included in the immutable target capability while database validation remains bound to the canonical analysis source.

### Verification

- Added plan serialization/legacy compatibility coverage and runner checks for successful database revalidation, database fingerprint drift, and database source-root drift.
- Resolved the eight PoC tree-attested targets to exact public commits and clean independent Git checkouts: Druid `c2d15dfc55d965e63b55dd11d698ca10ced99b4e`, HertzBeat `87062df97d01d14ea857b76936e97f4385cf609e`, SkyWalking `bb16533009a597dbb41ab6f013ac300509abbb3e`, Solr `c54251ea1614a6635410083839011cf20bfe189b`, Dependency-Track `f4bffa0aee1980387e1c40d7f01f13622a4c7720`, Zipkin `878ce2a1fad54ca941d17fdcf2e1d924b148eb1f`, Presto `913a64110299a3ae0f6314af1558255c1488fec8`, and ThingsBoard `e70298792acaa41b986ed8662fb2a760c35ee5e6`. Each checkout passes exact HEAD/origin/clean-worktree/Git-object validation; the override manifest separately binds the canonical analysis tree SHA-256 and default native database fingerprint.
- Published the nonexecuting immutable 29-case/18-target full plan at `results/java_web_dos_batch/poc29-full-plan-20260810/`. All 18 targets are queued, all 18 database fingerprints are bound, the provider is fixed to `deepseek-v4-pro` with temperature `0`, timeout `60`, retries `3`, and `pilot_skipped=true`; plan digest is `35fcae172671ea29b6ceacfeb0a99613ac2b3a3a08d7da3d1b5eaedf4c08d8a4`.
- The first authorized full execution of that published PoC-29 plan completed with `completed_with_failures` and produced no aggregate summary or static findings. All 18 targets failed: the 8 provider-override repositories hit `CODEQL_DATABASE_INVALID` because `dosweb/production.py` still requires the validated CodeQL database source root to equal the configured provider checkout even when the plan intentionally separates canonical analysis source from provider provenance, 9 targets hit `ANALYSIS_GROWTH_ENTRY_AMBIGUOUS`, and `tianshiyeben/wgcloud` hit `CONFIG_PUBLIC_SOURCE_UNVERIFIED`. The preserved state under `results/java_web_dos_batch/poc29-full-plan-20260810/` is the handoff baseline for the next tool-development session.

## [2026-08-04] Prepare strict native repair for Java Web 205

### Added

- Added a Java Web 205 native CodeQL database repair path with a frozen 55-target scope, Maven/Gradle-only discovery, safe nested build roots, multi-JDK attempts, strict source/database fingerprint validation, resumable attestations, and quarantine-based atomic promotion into the default `databases/applications/` paths.
- The repair path explicitly rejects CodeQL autobuild, `build-mode=none`, bounded javac, compilation-failure suppression, tests, application launch, deployment, Docker tasks, cloning, symlinked targets, and shell-composed commands.
- Added reviewed build-root overrides for the ten archived repositories whose Maven/Gradle roots are nested below the canonical source directory.

### Verification

- A non-network preflight fixed the exact current scope at 55 `JAVA_DATABASE_REQUIRED` targets and discovered 44 Maven and 11 Gradle native build specifications with no unresolved build roots. No database was modified during preflight.
- Native repair unit tests, Python compilation, and diff validation passed. The first authorized Sentinel attempt exposed a stale active loopback proxy in the workstation Maven settings; a subsequent attempt exposed a corrupt artifact in the shared Maven cache. Native Maven captures now use a repository-owned empty settings file, a run-local Maven repository, and sanitized Java/Maven/Gradle option variables so they do not inherit workstation mirrors, credentials, proxy state, injected build arguments, or corrupt shared-cache entries. No database was promoted by either failed attempt.
- Resume now verifies attestation digests and binds the current source, database, build command/root, and JDK set; malformed attestation lines are isolated. Promotion failures are recorded per target, quarantine paths are attempt-specific, and a single target exception no longer aborts the remaining repair scope. A completed CodeQL candidate rejected solely for source-fingerprint drift is now preserved under an attempt-specific `.source-drift` recovery path instead of being deleted, allowing generated-file quarantine, exact fingerprint restoration, strict revalidation, and guarded forensic promotion without rerunning a multi-hour native capture.
- The first repaired default database, `alibaba/sentinel`, completed a 94-module native Maven capture under CodeQL with source fingerprint unchanged, passed strict validation and `codeql resolve database`, and was atomically promoted while the prior invalid directory was retained under the run-specific quarantine path.
- The first five-target tranche exposed two invocation defects now corrected: CodeQL requires an explicit `--working-dir` for nested build roots, and Maven wrappers do not reliably honor `MAVEN_ARGS`, so controlled settings and the run-local repository are now injected directly into the native Maven command. The corrected retry natively repaired `lenve/vhr` and `undera/perfmon-agent`; both promoted databases pass strict resolution. Remaining project-specific failures are retained fail-closed: `ikismail/shoppingcart` has an uncompilable/missing `GetMapping` import, `merikbest/ecommerce-spring-reactjs` uses a Lombok processor incompatible with the installed JDK 17+, and `stevensouza/automon` references an internal `2.0.0-SNAPSHOT` artifact while its reactor builds `2.0.1-SNAPSHOT`.
- The second five-target tranche natively repaired and promoted `erudika/para`. Its other four targets remain fail-closed for checkout/build constraints: Quarkus extension dependency injection failure in `athou/commafeed`, old Lombok plus missing Java 8 system artifacts in `kalvingit/kvf-admin`, an absent internal `yuzi-generator-maker:1.0` artifact in `liyupi/yuzi-generator`, and a wrong local parent binding in `wxiaoqi/spring-cloud-platform`.
- The third five-target tranche produced no valid database. Failures were old Lombok on JDK 17+ (`dengsinkiang/sk-admin`), a late reactor compilation failure after most modules succeeded (`dromara/warm-flow`), a missing local parent (`exrick/xboot`), a timed-out direct GitHub asset download (`nitorcreations/nflow`), and a CodeQL Kotlin extractor ceiling because the project uses Kotlin 2.3.20 while the installed CodeQL supports versions below 2.2.30 (`suwayomi/suwayomi-server`).
- The fourth five-target tranche also produced no valid database. Blockers were an Apache RAT property mismatch (`apache/guacamole-client`, retried with the project-specific RAT ignore property), a missing private/non-Central parent (`dromara/lamp-cloud`), a required Java 24 release with only JDK 17/21/22 installed (`jamebal/jmal-cloud-server`), a missing frontend build output required by an Ant move step (`runify-dev/runify`), and an annotation processor incompatible with the installed javac (`zmops/zeus-iot`). The Guacamole retry passed the RAT gate but then failed on an absent reactor-produced `guacamole-common-js:zip:1.6.1`; it also generated non-excluded Node launcher files in the source tree, so the source-fingerprint drift gate correctly rejected the attempt before validation or promotion. Those generated files were preserved in the run artifact quarantine, and the canonical source fingerprint was restored.
- The fifth five-target tranche natively repaired and promoted `grimmory-tools/grimmory`, `jeecgboot/jeecgboot`, and `kerwincui/fastbee`; FastBee succeeded on the JDK 17 fallback after JDK 22/21 failures. `openremote/openremote` remains blocked by a required but unavailable Yarn task, and `tess1o/geopulse` requires Java release 25 while the host provides JDK 17/21/22.
- The sixth five-target tranche natively repaired and promoted `stirling-tools/stirling-pdf`. Its failures were Java release 25 without JDK 25 (`apache/hertzbeat`), a required JDK 11 Gradle toolchain (`hivemq/hivemq-community-edition`), a CodeQL Kotlin ceiling for Kotlin 2.4.0 (`micrometer-metrics/micrometer`), and Gradle 8.1.1 incompatibility with Java 22 bytecode during settings-script analysis (`sanluan/publiccms`).
- The seventh tranche initially reported five failures, but forensic recovery showed that `jenkinsci/jenkins` had completed its full native Maven reactor and CodeQL finalization before generated Node/Yarn/frontend files triggered the tree-fingerprint gate. Those generated files were preserved in the run artifact quarantine, the exact preflight fingerprint was restored, and the completed candidate passed repeated strict validation before guarded promotion and a recovery attestation. The other blockers were Java release 25 (`dependencytrack/dependency-track`), a Gradle task dependency validation error after compilation (`kestra-io/kestra`), a project plugin type-resolution failure (`modelengine-group/app-platform`), and an old Scala Maven plugin failing to load `javax.tools.ToolProvider` (`scouter-project/scouter`).
- The eighth five-target tranche natively repaired and promoted `kiegroup/jbpm` and `mqttsnet/thinglinks`, each after roughly 12–13 minutes of Maven/CodeQL capture. The failures were an unavoidable frontend `pnpm install` execution (`metersphere/metersphere`), a Liquibase goal requiring a live local PostgreSQL service (`walmartlabs/concord`), and missing generated protocol `Command` classes (`apache/skywalking`).
- The ninth five-target tranche produced no valid database. Blockers were a required Java 25 release (`apache/syncope`), an incomplete Maven wrapper checkout (`apache/incubator-kie-kogito-runtimes`), a missing `server-ee` reactor module (`theonedev/onedev`), an absent local `skyeye-parent:1.0-SNAPSHOT` parent (`dromara/skyeye`), and the CodeQL Kotlin extractor ceiling for Kotlin 2.3.20 (`apache/solr`). Solr's generated `.kotlin` diagnostics were preserved in the run artifact quarantine and the exact preflight source fingerprint was restored; no ninth-tranche default database was promoted.
- A targeted native retry avoided Solr's unrelated Kotlin UI module by capturing `:solr:server:assemble`; the Java server build completed under CodeQL, retained the exact source fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `2541f63b47573bbcd6170146c5beb896929052fab4d202fac9195a58939800f0`. Switching Kogito from its incomplete wrapper to system Maven exposed the underlying checkout blocker: its root requires the absent `org.kie:drools-build-parent:999-SNAPSHOT`, so it remains fail-closed.
- The tenth tranche natively repaired and promoted `apereo/cas` after a roughly 32-minute Gradle/CodeQL capture; its database fingerprint is `e23ed318723a249aab86ba4d9a95c4362de83da954ecc53e6c998c2c5e10ce81`, and strict validation plus `codeql resolve database` passed. `dotcms/core` compile was initially blocked by absent reactor ZIP artifacts; a native `package` retry produced those artifacts but then failed in its `process-annotations` compiler execution. `entropy-cloud/nop-entropy` compile lacked a reactor tests JAR and is being retried with test compilation enabled. `geoserver/geoserver` reached a real source/dependency API mismatch in `gs-gwc`; its generated Spotless index files were preserved in the run artifact quarantine and the exact preflight source fingerprint was restored. These three targets remain fail-closed unless their targeted native retries complete successfully.
- To address targets blocked solely by unavailable Java toolchains, JDK 8, 11, and 25 were installed locally under `/usr/lib/jvm/` and verified with `java -version`. The strict native builder now includes these system toolchains in its per-target fallback sequence while retaining per-attempt JDK attestation and source/database validation; previously staged repository-local archives are not executed by the builder. The first legacy tranche natively repaired and promoted `dengsinkiang/sk-admin`, `kalvingit/kvf-admin`, `merikbest/ecommerce-spring-reactjs`, and `scouter-project/scouter` under JDK 8; all four pass strict validation and `codeql resolve database`. HiveMQ's current Gradle wrapper itself requires JDK 17 despite requesting a JDK 11 compilation toolchain; the JDK 17 Gradle-runtime retry succeeded natively, retained its exact Git commit fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `21e13ba3275709689375bd3349cfd61121961efccef6ad1998dcd712fe15165b`. `zmops/zeus-iot` remains blocked by missing `JettyJsonHandler` symbols rather than its Java runtime.
- `entropy-cloud/nop-entropy` was natively repaired by retaining test compilation while skipping test execution, allowing the reactor tests JAR to be produced. Its 27-minute Maven/CodeQL capture retained the exact Git commit fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `7245a483cd57e9a44786d0b771c1d8d3e47fd90622145f5266e53f2aaad997fa`.
- Druid's corresponding native package capture completed successfully under CodeQL but generated 54 fingerprint-relevant distribution/frontend files. Those exact paths were digest-manifested and moved to run-specific generated-source quarantine, restoring the original source fingerprint. A later capture accidentally attested the generated-source state because it began before the generated files were removed; that database was quarantined as noncanonical. The final system-JDK-only recapture preserved its completed candidate on source drift, the same 54 exact files were quarantined, the original fingerprint `86263208a9038f00928b837c2df8fa7e4b18125ff6d411cd8212a87bb0c841c9` was restored, and the candidate passed repeated strict validation before guarded promotion. The canonical Druid database fingerprint is `f65bffa3fbfe9ba3ba967ee10b63a9328d7c7e9eb2e05cfc39c139a856d61d4c`; `codeql resolve database` also passed.
- The eleventh tranche produced no valid database. `thingsboard/thingsboard` requires Java release 25; `sonarsource/sonarqube` reached the unrelated distribution JRE download task; `apache/druid` compile could not resolve its reactor-produced `druid-processing` tests JAR; `keycloak/keycloak` compile did not generate its reactor Maven plugin descriptor; and `prestodb/presto` compile lacked a reactor tests JAR while an unrelated UI module attempted a timed-out Yarn download. A targeted SonarQube retry using the native aggregate `classes` task with build cache disabled succeeded under CodeQL, retained the exact source fingerprint, passed strict validation and `codeql resolve database`, and was atomically promoted with database fingerprint `09f781aadca5f82386845a7e9b61ce953df749d9502b9945393e7e8f1d8b6481`. Druid and Keycloak were retried with the native `package` lifecycle; both exposed missing reactor tests JARs because `maven.test.skip=true` suppressed test compilation, so follow-up retries retain test compilation while still skipping test execution. Presto's generated OpenAPI specification was preserved in the run artifact quarantine and the exact preflight source fingerprint was restored. Its targeted core-package retries excluded the UI from the selected reactor but still activated the UI frontend build through dependencies; all JDK attempts failed on Yarn download timeouts, with the first also encountering a truncated Central download, so Presto remains fail-closed. All retries retain the same strict source-fingerprint and promotion gates.
- The system-JDK-25 tranche natively repaired and promoted `apache/hertzbeat`, `apache/syncope`, `dependencytrack/dependency-track`, `jamebal/jmal-cloud-server`, and `tess1o/geopulse`; each build exited zero under CodeQL, retained its exact source fingerprint, and produced a strict native attestation. `thingsboard/thingsboard` entered its native Maven build and generated fingerprint-relevant Angular compiler-cache output, but the build ultimately failed because `maven-dependency-plugin:unpack (extract-web-ui)` could not find the expected packaged web-UI artifact. CodeQL therefore did not finalize a usable database; the drift gate retained only the failed skeleton candidate under an attempt-specific `.source-drift` path and withheld promotion. Because this archived source is not an independent Git checkout, recovery quarantined only the three files whose timestamps fell inside the failed build interval, recorded their sizes and SHA-256 digests, and reproduced the exact pre-build tree fingerprint `bf92109a4da088ac1d2fcfaf78fe5d3a3ba76badb6164e00fc0cc5d48a469672`; no broad `target`, Node, or source-tree deletion was performed. The tranche therefore completed with five successes and one fail-closed build failure.
- A Kestra retry excluding the known Gradle 9 `sourcesJar` validation failure completed the native `assemble` task, but all Java compilation tasks were `UP-TO-DATE`; CodeQL correctly rejected the database because no compilation was captured. The authorized follow-up forced `--rerun-tasks --no-build-cache`, completed the native Gradle build under JDK 25, retained its exact Git fingerprint, and promoted a strict database with fingerprint `34d4303bfa8835966f3e0a90b9b68e25afe73ad88d3c4c4e539738ee62adcdb1`. Runify's first JDK 25 retry cleared the previous compiler-release blocker but exposed its backend Antrun move of an absent skipped `frontend/dist`; the authorized follow-up selected only `backend` and used the plugin-supported `maven.antrun.skip` property, retaining native backend javac capture without building the frontend. It passed strict validation and promoted database fingerprint `cc91de8ecdef4bc63bf3d2cea39a2ec56d54a7b56e22514120250ab05e28ab07`. Both databases also pass `codeql resolve database`.
- Guacamole's targeted `guacamole-common-js,guacamole` Maven reactor generated the required JavaScript ZIP before compiling the Java WAR and exited zero under CodeQL. The build produced 510 fingerprint-relevant Node/frontend distribution files; each was size/SHA-256 manifested and moved to run-specific generated-source quarantine, restoring the exact pre-build tree fingerprint `169232ebca426df1cdf6073439673251733959dfd16542443f1131b4d24f3710`. The preserved candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion. Its canonical database fingerprint is `39f09db71c8032ee0531eb7385c62178423b926cdfe5a0e7cc86e68c5889799c`.
- ThingsBoard's targeted `msa/web-ui,application` Maven reactor initially failed because `maven.test.skip=true` suppressed the reactor-produced `dao` tests JAR. Retaining test compilation while skipping test execution allowed the 20-minute JDK 25 Maven/CodeQL build to complete successfully, including real `application` Java compilation. The three generated Angular compiler-cache files were size/SHA-256 manifested and quarantined, restoring exact source fingerprint `bf92109a4da088ac1d2fcfaf78fe5d3a3ba76badb6164e00fc0cc5d48a469672`. The preserved candidate passed repeated strict validation and `codeql resolve database` before guarded promotion with canonical database fingerprint `94e071350840d32bdf161d364273a59378fe752ea8a02ce77b773d8664d3caa6`.
- PublicCMS succeeded through its complete JDK 17 Maven reactor rather than the previously attempted Gradle or isolated OAuth entry. The native package capture retained its exact Git fingerprint and promoted strict database fingerprint `da7e7e0172a194cb489b157d7b2fb83fff593f4bc41dd7f766b744d42f848a57`.
- GeoServer avoided the incompatible GWC module by selecting the `main`, `security`, `ows`, `rest`, and `restconfig` Maven reactor under `src`. The native JDK 17 build and CodeQL finalization exited zero. Seven generated `.spotless-index` files were size/SHA-256 manifested and quarantined, restoring exact tree fingerprint `2abc7df0a2bc5751ab80f608d74dd7a78311c43e4b349a4b1cf4464e66d727fa`; the candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion with database fingerprint `0a992f4fd75bb9e7dca9c718cc6ee069251a74f3983310b4d5fd5717f47064a2`.
+- App Platform avoided the failing `tool-maven-plugin:build-tool` execution by selecting the substantial `waterflow-service` Java module and its native reactor dependencies. The JDK 17 `clean compile` capture exited zero, retained exact Git commit `dd242b21cb136c871b1658b9594616a29a2f8246`, passed strict validation and `codeql resolve database`, and atomically replaced the invalid default database while preserving it in run-specific quarantine. The promoted database fingerprint is `cf3f0312d97763e55611dc4bcec922b8dc1ff3baefa0b73ce3789a369fbac11b`.
+- Concord avoided incremental no-source capture by selecting the production `server/plugins/webapp` and `server/impl` reactor union, running `clean compile`, and disabling Maven incremental compilation. The JDK 17 Maven/CodeQL build exited zero, retained exact Git commit `9caa877161aff11501bc01c9a2ea51d99f7e1d80`, passed strict validation and `codeql resolve database`, and atomically replaced the invalid default database with fingerprint `65ed6b413e4f2786a58ccd78c4a79ea287a6a43e83547232ef9f30e815266ac9`; the prior directory remains in run-specific quarantine.
+- MeterSphere's targeted `backend/app` JDK 21 reactor used the project-specific `skipAntRunForJenkins` property, compiled the production backend modules, exited zero, and completed CodeQL finalization. Forensic comparison against the preserved local source archive identified nine generated flattened POMs responsible for the remaining drift; each was SHA-256 manifested and moved to run-specific generated-source quarantine, restoring frozen source fingerprint `c41596653a795eed0d274a371b0b1bf93edecd7e1aa0c15b269456ac90d7e55f`. The preserved candidate then passed repeated strict validation and `codeql resolve database` before guarded promotion with database fingerprint `e7c072c7fa8d53d1056b649b6f8061afa89b564a67544d7d9a1cbdd17fa7dced`.
+- Micrometer's Kotlin-bearing core remains beyond the installed extractor's Kotlin ceiling, so the strict native capture selected the production `micrometer-commons` module, which contains Java sources and does not require a Kotlin compilation task. A forced no-cache JDK 17 Gradle `compileJava` run exited zero, retained exact Git commit `24b886850814780f5f7bcdeb7d35cf25bc8ccd8a`, passed strict validation and `codeql resolve database`, and replaced the invalid default database with fingerprint `575df0ea46062711ae03f3d8cee30ec78f1461ac304c86d370a45b62ffa4d5bc`; no Kotlin task was excluded from the selected module's native task graph.
+- Yuzi Generator's checked-in backend Maven wrapper was incomplete and its web backend required an uninstalled maker artifact, so the strict capture selected the repository's real `yuzi-generator-maker` Maven project using system Maven. Its JDK 17 `clean compile` exited zero, retained exact Git commit `a2a0edb2cbbb6a869196b6b8a85e6ad30bbb635c`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `8b34ad27602685fe7990229b3934aebe6cb4d9307b2c424215db16c149482696`.
+- Automon's aggregate build previously failed when a sample module attempted to resolve the reactor's snapshot core artifact externally. Selecting the production `automon` module directly allowed a JDK 17 native `clean compile` capture to exit zero while retaining exact Git commit `815e9d0ea1360d8a93e6f241ada1f76c4fb9dfb6`. The database passed strict validation and `codeql resolve database` and was promoted with fingerprint `e085a453df4444c3de9cc5fef651c74c45106f980cf5c0a0e777a56066031234`.
+- Zeus IoT's aggregate `iot-server` path reached a real source/dependency API defect in `server-core`, so the strict native capture selected the concrete production `server-client` JAR and its Maven reactor dependencies rather than the POM-only aggregator. The JDK 17 `clean compile` capture exited zero, retained exact Git commit `b314c05a497dc0901cb658f8704e2efa62953cb4`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `e7ec38cdc0eafe3982580a02620bd7046d9760fb1f35efe9aabbbc3769533a91`.
+- Warm Flow's first narrowed selection was still a POM-only aggregator and correctly produced no CodeQL source capture. Selecting the concrete `warm-flow-easy-query-core` production JAR and its reactor dependencies executed a JDK 17 Maven `clean compile`, retained exact Git commit `5d04c41835302b9a3ec4e01d04a8481339497efd`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `31561b9e1fcbc6d7b5a6c976dbb12035d204f643bdfb69e24566a457ba88e559`.
+- dotCMS required JDK 25 and reactor-produced package artifacts rather than the earlier JDK 17 compile attempt. A targeted `dotCMS -am package` build ran for roughly 24 minutes under CodeQL, exited zero, retained exact Git commit `48102262b97e9fc510562f0eaeb5f83b54370a28`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `69b74184671393d4ce01dab091dec679b77ba036e7bc7f099646d65c373ccb5d`.
+- CommaFeed's empty client module did not create the directory expected by the server's Quarkus generate-code phase. After staging that native reactor precondition under the build-excluded `target` tree, the JDK 25 `commafeed-server -am compile` capture executed the production server compilation, exited zero, retained exact Git commit `77b3c609f33564398b099a652e0aa3fcdc43c3a4`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `6f568f1ecc91e995136cdc6e508c7fc217cb4aafa347bbd7bc8a5185a02e3e38`.
+- OneDev's root reactor was incomplete because the declared `server-ee` module was absent, but its existing production `server-core` project was independently buildable. A roughly 21-minute JDK 17 Maven `clean compile` capture exited zero, retained exact Git commit `5beff944c99e514f327eafa7d35bb65725449cf0`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `f0e22defe290eb072abe6663cea0f71a3b81fb7700c3fe91fa3c6fc1099984a7`.
+- Keycloak's archived source contained a generated pnpm symlink unsupported by canonical tree fingerprinting. The link was moved to run-specific source quarantine, yielding stable source fingerprint `6e8970b3568e538f57753178a773698285eaaff0c03723a70e91cc3b65a99013`. A clean JDK 17 native build of the `theme-verifier` Maven plugin then compiled production and test-support Java while skipping test execution, exited zero, and finalized a strict database. The candidate passed repeated validation and `codeql resolve database` before guarded promotion with database fingerprint `57ba15d240a141c26cdbcdd999b5a70acf0f2d1e8a187af8e4d365a0e1da89f8`.
+- Presto's `presto-server` Provisio assembly requires 44 reactor-produced plugin ZIPs that Maven dependency closure alone does not schedule. The final JDK 17 native package capture selected all 44 modules extracted from `presto-server/src/main/provisio/presto.xml`, plus `presto-flight-shim`, `presto-main`, and `presto-server`. The roughly 15-minute Maven/CodeQL build exited zero, retained exact source fingerprint `85510e107d6906bf3dc6f2303cfdbe507e3094720928389cf2119fb757935558`, passed strict validation and `codeql resolve database`, and promoted database fingerprint `65e73b7598f3b40fd7c8dc9e5c2cc54e39e55971716e53224b98a56f652b596b`.
+- XBoot's modular reactor could not resolve the deliberately repository-only `xboot-admin` parent, while the same repository's standalone production `xboot-fast` application contains 162 Java sources and is independently native-buildable. Its JDK 8 Maven `clean compile` exited zero under CodeQL, retained exact Git commit `5277af0ea7db3cf085f8ef3be21329df5bb12cd9`, passed repeated strict validation, and atomically promoted database fingerprint `2e37267443decff808b7527867259c8bd2135346d74e49afae997c71bf5496f0`; the prior invalid database remains in run-specific quarantine.
+- Native repair overrides now support an ordered `setup_commands` list for repository-native Maven/Gradle/Ant prerequisite lifecycles. Setup commands use the same selected JDK, sanitized environment, build root, controlled Maven settings, and run-local Maven repository as the CodeQL-captured command; they remain outside capture, fail closed before capture, are source-fingerprint gated, and are bound into resumable attestations.
+- Spring Cloud Platform avoided the broken `ace-nlp` child model by staging only the root parent, `ace-dev-base`, `ace-common`, `ace-auth-sdk`, and `ace-api` into one isolated Maven repository before capturing the concrete `ace-gate` production module. All five JDK 8 setup lifecycles and the final native `clean compile` exited zero, retained source fingerprint `0039e468f6df61cf9f397edd8ec7aacd7cddd6c634da2a79c846047fb82cf49b`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `b182361c89d81da54f0726b1be0abb616743d9af9f6bc70043892d0668047bea`.
+- SkyEye's primary Maven hierarchy was blocked by the unavailable `skyeye-parent:1.0-SNAPSHOT`, but the repository contains an independent, parent-complete XXL-Job 2.3.0 production reactor. A JDK 8 native `xxl-job-admin -am clean package` capture compiled the 114-source admin/core application, exited zero, retained exact Git commit `217901aeb65b433c5f9d27c64896c2dfde649dc5`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `d7e69cad4284959a7962ea7b2a27f5d3c3ec293df23328979b5ac6a05eed3e8a`.
+- Suwayomi Server required Kotlin 2.4.0, beyond the prior CodeQL 2.23.8 extractor ceiling. The official CodeQL CLI 2.26.0 bundle was integrity-checked, restored with its archived executable modes, and used in isolation without replacing `/opt/codeql`. A forced no-cache JDK 21 Gradle `:server:compileKotlin` run captured the production Kotlin reactor and dependencies, exited zero in roughly four minutes, retained exact Git commit `c8f5d83e9cca295a5a00f792de87354131e40052`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `fc870233011d78784a3a892956447becd58b27349d39e24768762f21778c384f`.
+- Lamp Cloud's unavailable 5.10.0 parent and utility artifacts were reproduced from the exact companion `zuihou/lamp-util` commit `124a9ea320304d7994879f056117f67e108773d0` in an isolated Java 17 Maven reactor and run-local repository. The unchanged canonical Lamp Cloud commit `ee893ed6f43cd2551b5cc8bb48ea70160681f1f7` then completed a native `clean compile` under CodeQL in roughly three minutes, retained its exact source fingerprint, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `321bdd40f18b7844c879e9c51c071621a55d36db117dbf7a59abfc3e26781fea`.
+- Kogito Runtimes' `999-SNAPSHOT` parent and dependency chain was reproduced from exact contemporaneous `apache/incubator-kie-drools` commit `b6fc3f0050bd1e818392bef0597ac488c05ffc19` in an isolated Java 17 Maven reactor. A full Kogito package attempt reached unrelated Quarkus integration-test dependency timeouts after 161 modules, so the strict capture selected the substantial production `jbpm-bpmn2` module and its required native reactor closure. The targeted `clean package` compiled the 115-source BPMN module, exited zero, retained canonical commit `acd78d9249ee75923a0e5e43a332bbc6c1fd0c1b`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `218b67327964bbcdb055ad0f268cc0647aa9417ac7d57c898ea34d7a343e5873`.
+- SkyWalking's GitHub source archive omitted its protocol gitlink content. Exact root commit `bb16533009a597dbb41ab6f013ac300509abbb3e` and protocol commit `07882d57becb37e341f7fc492c11f9f5a5f311cf` were recovered and built in an isolated upstream reactor, including `apm-network`, the `oap-server-bom`, and the internal dependencies required by `server-core`. Three historical generated flattened POMs absent from the original archive were digest-manifested and moved to run-specific source quarantine. The canonical 793-source `server-core` compile then exited zero under CodeQL with flattening disabled, retained source fingerprint `bb3201bdb276009e02cb11ff07b0f661cdae31381a39d065fef369e0bcc5dcbb`, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `c6ee05dddd5972e85b55972eefcc45c48530c0ce11071884ba205087ef476b20`.
+- ShoppingCart's former canonical merge commit `4ea0067bf2520ddd9b3332b627e5e01d50b4907b` contains an upstream regression that replaces two valid `RequestMapping` annotations with `GetMapping` without importing the latter, making the sole Maven source set unbuildable. Following an explicit corpus decision, the source was provenance-recorded and repinned to public pre-regression commit `c992c54bde6af51f67d8cfec5cdba6cbcda19f6c`. Its JDK 8 native Maven compile exited zero, retained the new exact Git fingerprint, passed repeated strict validation and `codeql resolve database`, and promoted database fingerprint `2a4b27ab10c5a54909305a34837eb850b2579a17700db93407799c040df6d04f`.
+- The regenerated canonical Java Web 205 inventory now reports `205/205` strict databases, zero incomplete targets, and `batch_ready: true`, with inventory digest `94cda8008abaa0126eb6dfa65b7fa1c68c153086e26d427a32269bbb99e038db`. The strict corpus loader accepts all targets, and a nonexecuting 205-target batch plan was generated with plan digest `408f9d861f75fcd5560a8a9ea0af8093624a5ec193d79c1efa682c0482d931e4`.

This changelog starts at the v2 cleanup baseline. Older analyzer runs and case-level research history remain available in Git history and preserved result directories rather than in the active project changelog.

## [2026-08-04] Add JAX-RS and gRPC Entry identities

### Added

- Added first-class `jax_rs/http` and `grpc/grpc` Entry identities with strict model, decoder, normalization, artifact-schema, coverage, and benchmark compatibility while preserving the exact 17-column contract.
- Added direct and embedded byte-identical `JaxRsEntries.ql` and `GrpcEntries.ql` queries. JAX-RS recognizes javax/jakarta Path, HTTP verbs, parameter/entity-body inputs, and statically provable ResourceConfig/register, Airlift binder, and Druid-style resource registrations; annotation-only resources remain coverage-only.
- Added conservative gRPC `BindableService` registration for unary/server-streaming-shaped handlers using the real `io.grpc.stub.StreamObserver` API. Request materialization remains `in_handler`; client/bidirectional streaming and descriptor-derived wire identity remain unresolved rather than inferred from response `onNext` calls.
- Added focused registered-positive, unregistered/lookalike-negative fixtures and benchmark identity regressions. gRPC matching now requires exact `grpc` protocol and full case-sensitive route identity; HTTP route-only truth remains valid and case-sensitive, while explicit method conflicts fail closed. Title, handler-name, resource-token, class-name, callback-name, and port guesses are not matching evidence. Multiple handler facts are merged only when they share one complete registration identity; otherwise ambiguity is preserved.
- Corrected JAX-RS route canonicalization, parameter-kind exclusivity, multi-argument registration scanning, and complete/partial overlap. Registered JAX-RS and gRPC handlers no longer also emit unresolved coverage rows.
- Corrected Spring input-kind exclusivity so explicitly annotated parameters and servlet request infrastructure are not simultaneously emitted as model attributes; real-database smoke scans are treated as coverage observations, not dynamic confirmation.

### Verification

- Corrected Spring MVC, JAX-RS, and gRPC queries compiled under the local CodeQL Java pack, and the final opt-in real CodeQL fixture run passed all seven controlled framework fixtures in 191 seconds, including exact JAX-RS routes and registered-versus-unresolved separation.
- Focused Entry, decoder, artifact, production, benchmark, and query-contract validation passed 103 Python tests; direct/embedded query parity, Python compilation, and whitespace validation also passed.
- A fresh local-only PoC-29 Entry batch completed 18/18 targets with the seven isolated database overrides and `max-workers=1`; no remote LLM, application startup, dynamic PoC, attack traffic, clone, or network database rebuild was used. The run produced 1,832 Entry facts (`spring_mvc`: 1,828; `netty`: 4), with Entry diagnostics of 6 `entry_hit`, 1 `entry_ambiguous`, 22 `no_entry_match`, 0 `target_not_run`, and 98 coverage gaps. These are Entry-stage diagnostics only; the entries-only run has 29 expected `artifact_missing` final-static states and does not establish static recall or dynamic confirmation.
- The same run produced no JAX-RS or gRPC facts on the current bounded databases. That result is retained as an explicit coverage limitation: generated/DI registration and descriptor-derived gRPC identities remain unresolved rather than guessed.

## [2026-08-04] Expand existing Java Web Entry extraction coverage

### Changed

- Expanded the existing Spring MVC, Netty, MQTT, Servlet, and filter Entry queries conservatively while retaining the exact 17-column table contract and byte-identical direct/embedded query copies.
- Spring mappings now recognize compile-time route arrays, mapping verbs, servlet request parameters, explicit model attributes, and uniquely typed unannotated command objects while excluding common framework infrastructure parameters.
- Netty recognizes statically registered `channelRead0` callbacks alongside `channelRead`; JMQTT `Object` callbacks remain complete only when a local MQTT-message cast is consumed by a processor, and SMQTT remains a partial dispatch gap.
- Servlet query support includes Jetty-style static holder bindings and verb-bearing servlet routes where the Java binding is unique; dynamic/reflection registrations remain coverage-only.
- Added verb-aware route canonicalization for HTTP Entry identities without changing non-HTTP event routes.

### Verification

- The earlier broad opt-in fixture sweep was not a reliable completion claim because Spring MVC, Servlet, and Netty each reached the 300-second per-test timeout in that run. A later controlled seven-fixture Entry run completed successfully after the JAX-RS/gRPC corrections described above.
- Query compilation, whitespace validation, and direct/embedded parity checks passed for the corrected JAX-RS/gRPC queries; focused Python Entry/benchmark tests passed.
- Descriptor-only `web.xml`, dynamic/reflection/DI registrations, descriptor-derived gRPC identities, client/bidirectional gRPC streaming, and unproven MQTT conversions remain deliberately unresolved.

## [2026-08-03] Migrate the active canonical corpus to Java Web 205

### Changed

- Defined the active corpus as the case-insensitive repository union of the preserved canonical Java Web 200 inventory and the PoC-29 repository set: 200 original targets plus exactly five additions at indices 201 through 205.
- Added a deterministic Java Web 205 inventory generator and tracked manifest while preserving the historical Java Web 200 manifest, repair utility, generated results, and target identity fields at indices 1 through 200 unchanged; readiness fields are deliberately recalculated.
- Switched the canonical corpus loader and batch CLI default to `intel/applications/java_web_205_targets.json`; strict loading now rejects a manifest whose recorded database readiness is incomplete.
- Added active-corpus documentation and regressions for union construction, ordering, case-insensitive deduplication, default paths, and readiness reporting.

### Readiness

- The generator strictly revalidates all 205 default databases and source-root bindings instead of carrying forward historical marker-based readiness. On the current filesystem the tracked manifest records 150 strictly valid default paths, 55 incomplete default paths with an explicit repository/reason list, and `batch_ready: false`; dataset membership remains 205.
- Separately, the seven incomplete PoC-29 databases were rebuilt under `build/poc29-codeql-dbs/` using explicitly risk-marked, PoC-relevant bounded CodeQL extraction after native Maven/Gradle attempts exposed dependency, generated-source, proxy, and JDK 25 blockers. All seven isolated databases pass the production validator and source-root checks, allowing PoC-29 to reach 18/18 readiness through explicit overrides without modifying historical default databases.
- A complete local entries run then finished 18/18 targets with no remote LLM or dynamic execution. Entry extraction produced 7 facts, all from Zipkin; the `/api/v2/spans` truth remains a deterministic three-overload `entry_ambiguous`, while the other 28 truths remain `no_entry_match`. The bounded rebuilds therefore remove `target_not_run` but do not by themselves expand framework Entry coverage.

## [2026-08-03] Expand MQTT broker and Armeria entry extraction

### Added

- Added end-to-end MQTT `broker_registration` entry support without changing the 17-column CodeQL table contract; partial and dynamic rows remain coverage-only and never become entry facts.
- Added high-confidence JMQTT anonymous `ChannelInitializer` broker recognition and conservative SMQTT Reactor Netty coverage gaps where connection-to-protocol dispatch cannot be uniquely bound, plus statically registered Armeria `@Post`/`@Get` annotated services including Zipkin `/api/v2/spans`.
- Added broker/Armeria fixtures, registration/schema regressions, and benchmark matching for MQTT protocol-service descriptions without port-only matches.

### Verification

- A fresh local-only 11-target entries run completed 11/11 targets with remote LLM and dynamic execution disabled. Entry facts increased from 1 to 7; all seven were Zipkin entries, and the PoC `/api/v2/spans` truth produced a deterministic three-overload `entry_ambiguous` result. JMQTT remained a coverage gap on the historical database, and SMQTT remained an explicit `smqtt_protocol_dispatch_binding_unresolved` partial gap rather than a guessed hit.
- Real CodeQL fixtures passed 2 tests; focused Entry/benchmark coverage passed 86 tests; query-pack parity, Python compilation, and diff validation passed.

## [2026-08-03] Diagnose PoC-29 entries-only benchmark runs

### Added

- Renamed the independent benchmark manifest identity to `poc-29` and added strict entries-stage artifact extraction with run/stage binding, digest, byte-count, record-count, and schema validation.
- Added deterministic repository/route/method/protocol entry diagnostics, coverage-gap reporting, and CLI `entry_diagnostics.jsonl` / `entry_summary.json` outputs without treating entry hits as static recall.
- Added runtime validation against the preserved local entries-only archive.

## [2026-08-03] Add PoC-29 benchmark baseline

### Added

- Added network-free PoC-29 truth normalization for 29 cases across 18 repositories, independent source/database asset binding, explicit repository spelling normalization, deterministic P0 candidate snapshots, fail-closed matching states, recall-only evaluation, and a baseline CLI.
- Database validation now uses the strict CodeQL validator: the real baseline exposes 7 incomplete databases and 11/18 ready entries. Truth remains valid at 29/18, while complete batch readiness is false; ready-only plans are explicitly diagnostic and not complete recall runs.
- Added strict repository-relative database overrides and fail-closed complete-plan checks.
- Added synthetic and real-inventory benchmark regression tests.

## [2026-07-28] Add canonical Java Web 200 batch orchestration

### Added

- Added strict canonical-corpus validation, source/database provenance checks, immutable batch plans, target identity bindings, bounded concurrency, atomic batch state, failure isolation, and resumable per-target production execution.
- Added local-only `entries` batches and explicitly authorized `full` batches. Environment provider credentials are stripped from Entry-only workers, while tree-fingerprint targets remain paused when public Git commit attestation is unavailable.
- Added format-separated normative P0 aggregation with target/run/stage binding, artifact hash/count/size validation, structured gap accounting, atomic publication, and exact three-value static-verdict totals while preserving historical hunter aggregation. Aggregation now rejects ambiguous format auto-detection instead of silently treating P0 records as historical.
- Added digest-bound non-secret provider settings to batch plans and a non-executing `full --plan-only` path; full execution still requires explicit remote consent and an environment-only provider key.

### Verification

- Added network-free batch plan, runner, aggregation, resume, authorization, identity, concurrency, stale-artifact recovery, and compatibility regressions; the complete default suite now passes 494 tests with 6 guarded integrations skipped.
- No real DeepSeek request, corpus analysis run, service launch, attack traffic, or dynamic DoS validation was performed.

## [2026-07-28] Complete the production P0 analyzer

### Added

- Connected all six default production executors for Entry extraction, G1–G4 Growth classification, E→G flow proof, lifecycle evaluation, deterministic conclusions, and certificate-consistent reporting.
- Added durable strict round trips for Growth, Flow, Guard, Bound, Release, lifecycle decision, certificate, and finding artifacts, with authoritative resume reconstruction and downstream invalidation.
- Added a complete immutable query-pack snapshot across Entry, Growth, Flow, and Lifecycle query families and a network-free injected full-graph production test.

### Security and correctness

- Preserved pinned-source excerpt validation, explicit remote consent, environment-only API keys, atomic provider-stage publication, conservative partial-coverage handling, and static-only verdict wording.
- Required the selected commit to be reachable from the public repository's default branch, required the CodeQL database source root to match the pinned checkout, and blocked credential assignments in comments and credential-bearing Java mutator/header calls before provider use.
- Made lifecycle decisions durable and schema-validated, rejected forged nested decision summaries/IDs, and ensured any partial sibling flow forces `static_unknown` rather than being discarded from conclusion evidence.

### Verification

- Final default discovery ran 462 tests successfully with 6 guarded integrations skipped.
- All 6 opt-in real-CodeQL Entry, Growth, and Lifecycle fixture tests passed.
- Python compilation, every CLI subcommand help path, and `git diff --check` passed.
- No real DeepSeek request, service launch, attack traffic, or dynamic DoS validation was performed.

## [2026-07-25] Migrate active consumers and document the P0 interface

### Changed

- Migrated active static aggregation and dynamic-scaffold traceability to the exact `static_vulnerable`, `bounded_under_modeled_assumptions`, and `static_unknown` vocabulary, rejecting the retired value and static-verdict field aliases rather than retaining a compatibility path.
- Preserved static/dynamic independence: the dynamic scaffold copies a static verdict only under traceability metadata while retaining `paused`/`blocked` dynamic defaults.
- Reworked README and agent guidance to document Python and CodeQL requirements, mandatory DeepSeek behavior for complete P0 runs, the current fail-closed production executor boundary, stage/resume semantics, normative artifacts, exact verdict meanings, P0 framework/assertion scope, asynchronous Release limitations, coverage gaps, test opt-ins, and static/dynamic separation.
- Added dedicated verdict-migration regressions and physical JSONL source-location checks for rejected values and field aliases, including inputs with blank lines.

### Verification

- Final default discovery ran 416 tests successfully with 6 guarded integrations skipped.
- `codeql pack install codeql` succeeded with CodeQL CLI 2.23.8, and all 6 opt-in Spring MVC, Servlet, Netty, and MQTT entry/Growth/lifecycle fixture tests passed.
- Focused migration tests, Python compilation, CLI help, terminology scan, and `git diff --check` passed.
- Verification made no real DeepSeek request, did not start target services, did not send attack traffic, and did not run dynamic DoS validation.
- At that checkpoint, Task 7 remained partial because the production CodeQL/DeepSeek stage-executor factory was still deliberately unconnected; the 2026-07-28 entry records its completion.
- Per explicit user direction, the obsolete 2026-07-02 baseline design remains deleted as an approved preservation exception; the ignored 2026-07-18 design and plan remain unstaged until commit authorization.

## [2026-07-24] Add static conclusions, certificates, reports, and resumable orchestration

### Added

- Added deterministic Assertion 1 and Assertion 2 evaluation with the exact `static_vulnerable`, `bounded_under_modeled_assumptions`, and `static_unknown` vocabulary. Partial flow, unresolved lifecycle evidence, and relevant coverage gaps remain unknown; provider confidence never changes a verdict.
- Added canonical lifecycle certificates, certificate-derived static findings, deterministic summaries, and static-only Markdown reports with strict finding/certificate/verdict consistency.
- Added generic injected stage execution for `entries -> growth -> flows -> lifecycle -> conclude -> report`, deterministic fingerprints, exact resume reuse, mismatch invalidation, bounded canonical local payloads, strict manifest/artifact recovery validation, output-root locking, symlink refusal, stale-artifact reconciliation, and transactional publication/rollback.
- Added fail-closed CLI subcommand dispatch with controlled `AnalyzerError` and injected-factory failure handling. Production CodeQL/DeepSeek stage executors are not yet connected by the default factory, so direct production commands fail closed rather than claiming analysis success.
- Added network-free P0 scenario coverage for materialization, allocation, persistent-map growth, queues, finite rejection, late Guards, incomplete Release, asynchronous consumers, Netty, and MQTT.

### Verification

- Final default discovery ran 356 tests successfully with 6 guarded integrations skipped.
- Focused assertion, certificate/report, pipeline recovery, artifact, configuration, and P0 end-to-end suites passed; Python compilation, CLI help, and `git diff --check` passed.
- Independent review findings became regressions for scoped coverage, overlapping coverage patterns, forged assertion/verdict/certificate identity, strict lifecycle booleans, active verdict vocabulary, report disagreement, malformed resume metadata, manifest/hash/count tampering, duplicate and symlinked paths, stale artifacts, rollback, factory errors, and bounded payload handling.

## [2026-07-24] Prove entry-to-growth flows and evaluate lifecycle evidence

### Added

- Added normalized E→G `FlowProof` construction with stable identities, strict attacker source/demand mapping, dangling-reference failures, canonical artifact validation, and audited proven/partial verification.
- Added deterministic Guard, Bound, and synchronous Release decisions with structured checks, stable reasons, modeled finite-configuration matching, receiver/dimension/scope joins, and unresolved asynchronous-release retention.
- Added exact-column candidate-only CodeQL queries for direct entry-to-growth flow, Guard, Bound, and synchronous Release evidence, plus Spring, Servlet, Netty, and MQTT lifecycle fixtures.

### Verification

- Final default discovery passed 295 tests with 6 guarded integrations skipped; focused Task 6 tests, Python compilation, and `git diff --check` passed.
- Explicit local CodeQL lifecycle fixture verification passed across all four framework databases, and all four Task 6 queries compiled against the local CodeQL Java pack graph.
- Independent reviews drove regressions and remediation for same-handler false flow proofs, incomplete coverage upgrades, forged flow identities, configuration mismatches, cross-receiver Bounds, Release scope/dimension/key semantics, mixed asynchronous Release evidence, and malformed flow artifacts.

## [2026-07-24] Verify four resource growth classes

### Added

- Added frozen G1–G4 Growth candidate normalization with deterministic resource/growth identifiers, sorted demand/evidence merging, strict raw-row validation, and exact `growth_candidates` artifact serialization.
- Added canonical bounded-slice construction and deterministic Growth Contract verification with audited `verified|rejected|unresolved` results, stable reason codes/checks, strict slice/index evidence identity, and no fabricated static facts.
- Added exact-column CodeQL screening queries for request/message materialization, direct buffer and array allocation, persistent container growth, and field-backed asynchronous work submission.
- Extended Spring, Servlet, Netty, and MQTT fixtures with G1–G4 positives, request-local/lookalike negatives, finite/unbounded queue forms, and guarded real-CodeQL semantic tests.

### Verification

- Final default discovery ran 255 tests successfully with 5 guarded integrations skipped; focused Growth/artifact suites and Python compilation passed.
- Explicit `DOSWEB_RUN_CODEQL_FIXTURES=1` verification passed both Growth query tests across temporary fixture databases; all four Growth queries compiled against the local CodeQL pack graph.
- Independent reviews drove regressions and remediation for fabricated evidence, empty/cross-candidate evidence verification, malformed identifiers, evidence-ID collisions, array-allocation coverage, collection demand roles/scopes, local async receivers, G1 lookalikes, and nested artifact validation.

## [2026-07-24] Extract registered framework entries

### Added

- Added frozen registered-entry, attacker-input, registration, handler, and framework-coverage models with deterministic semantic identifiers, strict framework/protocol pairings, canonical HTTP routes, sorted input deduplication, and bounded analyzer errors.
- Added deterministic entry-row normalization that separates unresolved dynamic registrations from reachable entries, validates both supported and gap rows, and emits explicit coverage records for Spring MVC, Servlet, Netty, and MQTT even when a framework has no extracted rows.
- Added four exact-column CodeQL table queries requiring framework-specific registration/type evidence: Spring controller mappings, Servlet annotation registrations, Netty pipeline registrations, and MQTT subscribe/listener bindings. Recognized unresolved registration patterns emit partial coverage rather than fabricated reachability.
- Added self-contained Java source fixtures with registered handlers, unregistered/lookalike negatives, and dynamic-registration gaps, plus guarded real-CodeQL semantic tests.

### Verification

- Final focused Task 3/4 verification ran 41 tests with 39 passed and 2 guarded CodeQL fixture tests skipped by default; the complete default suite ran 243 tests with 240 passed and 3 guarded integrations skipped.
- Explicit `DOSWEB_RUN_CODEQL_FIXTURES=1` verification passed both real-CodeQL tests across all four temporary Java databases, exact decoded columns, registered-entry expectations, lookalike exclusion, and forcing coverage gaps.
- All four entry queries compiled against the locally installed `codeql/java-all` dependency graph, all Java source fixtures compiled without leaving `.class` artifacts, changed Python files compiled, and `git diff --check` passed. Independent reviews drove remediation for framework lookalikes, protocol mismatches, incomplete coverage validation, sparse coverage records, unresolved registration gaps, and unrelated-reflection coverage poisoning.

## [2026-07-24] Add strict Task 3 CodeQL execution contracts

### Added

- Added bounded CodeQL database validation with strict metadata parsing, stable metadata-file fingerprints, source-root provenance, symlink rejection, and controlled `CODEQL_DATABASE_INVALID` failures.
- Added a two-stage CodeQL query/BQRS runner with minimal secret-free environment inheritance, one shared deadline, bounded diagnostics, descriptor-validated immutable root-query snapshots in the original pack context, database-drift checks, TERM/KILL process-group cleanup, and atomic per-generation publication after validation and BQRS hashing succeed.
- Added fixed ordered `QuerySpec` contracts for entry, growth, flow, Guard, Bound, and synchronous Release candidates, with strict result-set, row, primitive type, enum, path, line, row-count, and string-budget validation.
- Added the minimal `dosweb/p0-java-resource-dos` query pack manifest using the installed CodeQL CLI's modern `dependencies` field, without query suites; individual queries remain deferred to later tasks.
- Added real-CodeQL compatibility remediation for timestamped database metadata, `{name, kind}` decoded column descriptors, strict decoded-result validation before publication, original pack-context query execution with persisted snapshots, and deadline propagation through bounded database and file hashing.

### Verification

- Final focused Task 3 verification passed 25 tests; the full default suite ran 227 tests with 1 guarded online integration skipped. `codeql pack ls codeql` resolved `dosweb/p0-java-resource-dos@0.1.0` under CodeQL CLI 2.23.8.
- Concurrent generation initialization/publication passed 10 repeated rounds; an additional focused stress sequence passed 5 rounds and 90 test executions.
- Changed Python modules/tests compiled and `git diff --check` passed. Independent Task 3 reviews drove regressions for query provenance drift, descendant-held process pipes, SIGTERM-ignoring descendants, and post-publication hashing; all were fixed within the root-query adapter contract.

## [2026-07-22] Complete fourth Task 2 consolidated remediation

### Changed

- Serialized cross-stripe cold cache production behind one fixed private process-shared capacity lock, preserving fixed key stripes, pre-provider capacity failure, immutable entries, and non-destructive no-eviction behavior.
- Replaced single-shot provider/GitHub body reads with incremental bounded reads under recomputed absolute deadlines, and propagated one shared verification budget across GitHub API and local Git operations.
- Added process-local same-key sharing for sanitized deterministic response failures without persistent negative caching; later independent calls may retry normally.
- Replaced plaintext provider request-ID audit persistence with a domain-separated API-keyed HMAC digest and bumped the authenticated cache format.
- Added high-confidence SSN-like PII rejection, complete Java compound-assignment coverage, annotation-aware Java declarator scanning, Java comment/octal/text-block literal reconstruction, component-aware credential identifiers, and bounded UTF-8 prechecks for hostile slice strings.
- Hardened independent-review boundaries: authenticated incompatible cache entries now receive capacity-gated live refresh without overwrite; crash temporaries count toward cache bytes; cache-entry HMACs have an explicit domain; timeout values are upper-bounded; permanent response-read failures do not retry; and complete GitHub slice verification shares one deadline.

### Verification

- Final focused Task 2 verification passed 169 tests; the full default suite ran 202 tests with 1 guarded online integration skipped; concurrency/deadline/publication stress passed 10 rounds and 90 test executions.
- Modified Python modules/tests compiled, parser-only CLI boundaries returned 0/2 as expected, and `git diff --check` passed. Independent review gate results are recorded in the Task 2 implementation report.

## [2026-07-19] Complete third Task 2 consolidated remediation

### Changed

- Hardened provider request-ID credential rejection, unbounded Java assignment scanning, Credential(s) classification, response echo filtering, permanent-network error handling, and one monotonic request deadline.
- Bound aliases and formal evidence to current config/growth identities; made cache fact IDs mandatory and authenticated audit fields fully identity-bound.
- Replaced per-key cache locks with 64 immutable stripes, removed memory growth, closed inherited flock descriptors, imposed non-destructive global capacity limits, and made unsafe/capacity/publication failures fail closed before provider use where required.
- Hardened Git deadlines/config overrides, JSONL mapping/publication/count behavior, strict config keys/Unicode handling, and explicit CLI remote-consent revocation.

### Verification

- Focused Task 2 command passed 146 tests; race/fork/cache/publication stress passed 10 consecutive iterations; full discovery passed 178 tests with 1 guarded online integration skipped.
- Changed Python modules/tests compiled, `git diff --check` passed, and parser-only CLI runtime accepted `--no-remote-llm` while rejecting conflicting consent flags with exit 2.

## [2026-07-18] Fix cold cache hierarchy creation race

### Changed

- Made descriptor-relative private cache hierarchy creation tolerate a concurrent trusted creator winning the `mkdir` race, so every same-key cold process reaches the shared `flock` instead of bypassing single-flight.
- Added a deterministic concurrent hierarchy-creation regression preserving the guarantee that exactly one cold producer publishes and a fresh cache reconstructs the durable contract.

### Verification

- The process single-flight test passed 20 consecutive post-fix iterations; the focused Task 2 suite passed 126 tests; full discovery ran 159 tests with 158 passed and 1 guarded online integration skipped.

## [2026-07-18] Complete second Task 2 consolidated remediation

### Changed

- Replaced regex-only Java credential assignment handling with Unicode-aware lexical scanning that preserves string/comment boundaries and detects sensitive identifiers independently of value syntax.
- Hardened YAML/config loading with bounded descriptor reads, regular-file and symlink refusal, duplicate-key/alias/tag rejection, path normalization, boolean precedence preservation, and strict URL-authority validation.
- Removed unbounded HTTP read fallback, normalized injected transport failures into retry exhaustion, added deadline-aware Git output collection and nonzero-runner rejection, bounded cache publication, and descriptor-relative private cache hierarchy creation for Linux/Python 3.11+.
- Added strict JSONL duplicate-key, structure, record-count, per-record, and aggregate limits; enforced artifact ID syntax/uniqueness and bounded `fact:` evidence IDs; preserved deterministic atomic publication.
- Preserved same-file relationships in provider aliases, exposed one canonical typed response schema, and strengthened fabricated-cache evidence validation with a recomputed valid HMAC.

### Verification

- Task 2 focused command passes 125 tests. Per-module discovery passes 26 artifact, 6 bounded-slice, 9 strict-growth, 21 config/CLI, and 63 DeepSeek tests.
- Full discovery passes 158 tests with 1 explicitly guarded online integration skipped. Changed Python modules/tests compile and `git diff --check` passes.
- Runtime CLI observation confirms the current Task 1/2 boundary remains parser-only: both explicit remote-consent arguments and default parsing exit 0 without analysis or network access.

## [2026-07-18] Harden Java Web DoS skill routing and dynamic validation

### Changed

- Routed bulk inventory, environment setup, probe execution, and fleet screening to `claude-haiku-4-5`; bounded semantic analysis and PoC engineering to `claude-sonnet-5`; and cross-stage reflection and final review to `claude-opus-4-8`, with evidence-coded escalation and model-usage artifacts.
- Made dynamic environment preparation reusable and autonomous within isolation boundaries, with explicit deployment classification and repair evidence required before `environment_blocked`.
- Added semantic preflight and a hard three-round PoC reflection loop that treats growth-only and no-growth observations as hypotheses to diagnose rather than final answers.
- Strengthened the user-level dynamic aggregator to discover missing results, validate status/schema/deployment/round/evidence/termination contracts, and derive verdicts centrally.

### Verification

- Added user-level skill and aggregator contract coverage for model aliases, worker-role separation, semantic preflight, the three-round cap, missing results, verdict conflicts, deployment classification, evidence paths, and split safety termination fields.
- Verified 22 focused dynamic-validation tests, Python compilation, and repository diff whitespace checks.

## [2026-07-18] Consolidate Task 2 independent-review remediation

### Changed

- Made provider response-body read failures retryable, bounded all slice/YAML/Git materialization and process output, reset inherited locks after fork, and safely create private nested cache paths.
- Added deterministic provider-facing aliases with local evidence restoration, exact final-request credential scanning with Java normalization, a complete typed prompt schema, strict formal Growth Contract artifact validation, IPv6-safe URL canonicalization, and stable malformed-URL errors.
- Exposed the Task 2 `--allow-remote-llm` consent/provenance CLI arguments without adding later-stage analyzer orchestration.

### Verification

- Added regression coverage for all verified review findings. The focused suite passes 90 tests; full discovery runs 134 tests with 133 passed and the guarded online integration skipped. Changed Python files compile and `git diff --check` passes.

## [2026-07-18] Authenticate and harden DeepSeek contract cache

### Changed

- Bound Growth Contract cache entries to the in-memory DeepSeek API key with HMAC-SHA256; cache files contain the authenticator but never the key, and unkeyed SHA-256 fields now provide integrity metadata only.
- Made cache use fail closed for unsafe local paths: cache directories must be current-user-owned `0700` directories, and lock, temporary, and entry files must be current-user-owned regular `0600` files. Directory-descriptor relative operations and `O_NOFOLLOW` are used where supported.
- Treat symlinked, permission-unsafe, or foreign-owned cache paths as cache misses with cache publication disabled, while allowing an authorized live classification to proceed. Preserved thread and cross-process single-flight behavior for safe caches.

### Verification

- Added focused cache coverage for HMAC tampering despite recomputed unkeyed hashes, wrong-key misses, owner checks, private modes, and symlinked directory, entry, and lock handling.
- Ran `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_cache_entry_requires_hmac_bound_to_the_api_key tests.test_deepseek_client.DeepSeekClientTests.test_cache_with_a_different_api_key_is_a_miss tests.test_deepseek_client.DeepSeekClientTests.test_cache_files_are_private_and_regular tests.test_deepseek_client.DeepSeekClientTests.test_symlinked_cache_directory_is_not_used tests.test_deepseek_client.DeepSeekClientTests.test_symlinked_cache_entry_is_a_miss_and_is_not_replaced tests.test_deepseek_client.DeepSeekClientTests.test_unsafe_permissions_and_lock_symlink_disable_cache_writes tests.test_deepseek_client.DeepSeekClientTests.test_cache_rejects_foreign_owner_when_lstat_is_mocked -v`, `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_same_key_process_single_flight_publishes_once_durably tests.test_deepseek_client.DeepSeekClientTests.test_same_key_thread_single_flight_makes_one_provider_request -v`, and `python -m unittest tests.test_deepseek_client.DeepSeekClientTests.test_cache_entry_requires_hmac_bound_to_the_api_key -v` successfully.

## [2026-07-18] Add audited DeepSeek Growth Contract adapter

### Added

- Added an opt-in DeepSeek OpenAI-compatible Growth Contract client with strict schema validation, bounded retry policy, cache identity/integrity checks, atomic successful-response publication, and local mock coverage.
- Added a pre-network remote-source gate requiring explicit authorization, canonical public GitHub repository provenance, a full commit SHA, and a clean matching local checkout; default GitHub verification uses unauthenticated API requests and read-only Git checks, while authorization and provenance are captured only in non-secret request audit metadata.
- Restricted production provider endpoints to canonical `https://api.deepseek.com/`; loopback endpoints are permitted solely for local mocks, and all other endpoints fail before an Authorization header can be constructed.
- Added bounded-slice and Growth Contract models, constrained prompts, redaction of API keys, authorization values, and `sk-...` strings, plus a dual-guarded artificial-fixture integration test.

### Verification

- Verified with `python -m unittest tests.test_deepseek_client -v` and `python -m unittest discover -s tests -v`; default tests use localhost mocks and make no external provider request.

### Security remediation report (Task B: items 4, 5)

- Validated every LLM Growth Contract evidence reference against the static fact IDs in its bounded slice. Fabricated live references fail as `LLM_RESPONSE_SCHEMA_INVALID` before a cache write, while fabricated cached references are treated as cache misses.
- Applied strict byte, UTF-8, duplicate-key/non-finite-value, nesting, node, collection, and string limits consistently to provider-envelope, inner-contract, GitHub, and cache JSON. Reads request at most `limit + 1` bytes and map malformed, incomplete, or oversized data to controlled errors/cache misses.
- Preserved the cache HMAC and filesystem-authentication implementation without modification.

### Verification

- Verified the Task B fact-reference and JSON-boundary regressions with local mock/seam tests only; no live DeepSeek or GitHub endpoint was contacted.

### Security remediation report (Task C: items 3, 6, 7, 8)

- Validated Git object metadata before reading a source blob, rejected non-blobs and blobs over the bounded excerpt limit, and retained exact blob and excerpt hashes.
- Added the finite `MAX_LLM_RETRIES` bound at configuration and client runtime; blank API keys are accepted only while remote LLM access is disabled, while enabled access requires a nonblank environment key. YAML now rejects case and separator variants of `api_key` at every nesting level.
- Routed verifier Git commands through one hardened command form that disables fsmonitor and hooks, disables system/global configuration, replacement objects, and pagers; a local malicious `core.fsmonitor` regression confirms its helper is not executed.
- Ran `git fsck --strict --no-dangling --no-reflogs <full-sha>` through that hardened runner before any local source object access.

### Verification

- Passed focused Task C regressions with `python -m unittest tests.test_config_and_cli.ConfigTests.test_configuration_rejects_api_key_spelling_variants_at_any_depth tests.test_config_and_cli.ConfigTests.test_disabled_remote_llm_allows_a_missing_environment_key tests.test_config_and_cli.ConfigTests.test_enabled_remote_llm_requires_a_nonblank_environment_key tests.test_config_and_cli.ConfigTests.test_max_retries_has_an_explicit_upper_bound_in_cli_and_yaml tests.test_deepseek_client.DeepSeekClientTests.test_empty_api_key_is_rejected_before_verifier_or_network tests.test_deepseek_client.DeepSeekClientTests.test_runtime_config_rejects_max_retries_above_the_explicit_limit tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_hardened_git_invocation_disables_checkout_configured_helpers tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_validate_slice_rejects_oversized_git_blob_without_reading_it tests.test_deepseek_client.GitHubPublicSourceVerifierTests.test_verify_runs_strict_fsck_before_any_local_object_read -v`.

## [2026-07-18] Consolidate P0 implementation authority

### Changed

- Declared `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md` the sole implementation standard and updated repository guidance and README links accordingly.
- Hardened artifact recovery validation so a stage requires a non-empty artifact list and every artifact path is a safe relative path within the run output root.
- Completed lifecycle artifact contracts, canonical JSONL ordering, recursive YAML secret rejection, strict blank/UTF-8 JSONL failure handling, and output-root-relative artifact metadata serialization.

### Verification

- Added regression coverage for missing, empty, malformed, absolute, and escaping artifact paths during stage reuse.
- Added focused contract coverage for lifecycle artifact minima, deterministic JSONL bytes, nested YAML secrets, and strict JSONL input failures.

## [2026-07-18] Design the complete P0 analyzer

### Added

- Added the approved full-P0 analyzer design for Spring MVC, Servlet, Netty, and MQTT.
- Defined the Python and CodeQL module boundaries, versioned artifact contracts, bounded-slice DeepSeek Growth Contract, deterministic lifecycle rules, assertions 1 and 2, lifecycle certificates, recovery model, and test strategy.

### Changed

- Chose `bounded_under_modeled_assumptions` to replace the unconditional `static_safe` label during implementation; active tooling and documentation will be migrated together without a legacy compatibility mode.
- Required DeepSeek through an environment-only API key for complete P0 runs while keeping default tests network-free and provider calls auditable.

### Verification

- Reviewed the design for placeholders, internal contradictions, ambiguous verdict behavior, secret handling, and scope boundaries.
- Added P0 package, environment-only configuration, strict JSONL artifact contracts, deterministic identifiers, and resumable-stage primitives.
- Verified with `python -m unittest tests.test_config_and_cli tests.test_artifact_contracts -v` and `python -m unittest discover -s tests -v`.

## [2026-07-17] Prepare the v2 tool-development baseline

### Changed

- Restored the preserved v2 engineering specification and retired the obsolete one-time cleanup plan and Stage 0–5 research design.
- Adopted the lifecycle-centered analysis direction based on bounded slices, Growth Contracts, lifecycle evidence, and effective Guard/Bound/Release reasoning.
- Normalized paper material under `docs/paper/` and repaired active documentation links.
- Kept the existing `poc/` evidence archive unchanged and stopped implicitly admitting new disclosure logs and probes into version control.
- Added a static CodeQL batch-build foundation and a static-only batch aggregator with configuration validation and regression tests.
- Kept dynamic-validation preparation and status synchronization as explicit opt-in helpers, isolated from the ordinary v2 static pipeline.

### Verification

- Python and shell syntax checks.
- Unit tests for manifest/config validation, path handling, dry-run behavior, static aggregation, case identity, overwrite protection, and status synchronization.
- Markdown-link, JSON, gzip, and Git workspace hygiene checks.

## [2026-07-02] Reset the workspace for v2 implementation

### Changed

- Established the v2 static model:
  `Vulnerable(E, G) := Reach(E, G) ∧ AttackerControls(E, G) ∧ Growth(G) ∧ ¬EffectiveB(E, G)`.
- Preserved framework sources, CodeQL databases, PoC evidence, static-hunt results, application results, and Java Web batch results.
- Removed legacy phase-oriented analyzer implementation from the active development context.
