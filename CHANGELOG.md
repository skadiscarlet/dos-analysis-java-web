# dos-analysis-web 变更日志

本文档记录 dos-analysis-web 项目的所有重要变更。

---

## [2026-06-30] 应用级 29 条真阳性 Security Advisory PoC 生成

### 修改时间
2026-06-30 22:42

### 变更类型
- [文档] 安全公告 PoC 材料生成
- [新增功能] 二值真阳性 advisory PoC 生成脚本

### 核心改动
- 基于 `results/applications_dynamic_validation/binary_truth_collection.json` 和 `BINARY_TRUTH_COLLECTION.md` 中 29 条 `confirmed_true_positive`，在 `poc/` 下为每条真阳性生成独立目录。
- 每个目录包含中英文 `SECURITY_ADVISORY`、本地受控 `reproduce.sh`、标准化 evidence JSON、truth source record、附件索引，并尽量复制 case-local probe / compose / 小日志附件。
- 对 `new/new_retest` 中部分旧 result commands 与严格 1GiB 复测口径不一致的条目，生成脚本内置严格复测命令覆盖，避免 advisory 复现步骤落回小堆历史口径。
- P0/P1 条目统一使用现有动态验证 runner 的 `--case <ID> --min-heap 1g` 本地复测入口，保持与当前二值真相口径一致。

### 交付成果
- 新增脚本：`scripts/generate_advisory_pocs.py`
- 修改忽略规则：`.gitignore` 放行标准化 `poc/<true-positive-id>/` advisory 文本、JSON evidence、复现脚本和小附件，继续避免把任意私有披露草稿整体纳入。
- 新增索引：`poc/README.md`、`poc/manifest.json`
- 新增 PoC 目录：`poc/<true-positive-id>/`
- 每个 PoC 目录包含：`SECURITY_ADVISORY.zh-CN.md`、`SECURITY_ADVISORY.en.md`、`reproduce.sh`、`attachments/`
- 测试/验证结果：`python3 -m py_compile scripts/generate_advisory_pocs.py` 通过；`python3 scripts/generate_advisory_pocs.py` 成功生成 29 个目录；结构检查确认 29 个目录均包含中英文报告、复现脚本和 evidence；`python3 -m json.tool poc/manifest.json` 通过。

### 依赖与影响
- 依赖：当前二值真相集合 `results/applications_dynamic_validation/binary_truth_collection.json` 与既有 P0/P1/new/new_retest 动态验证证据。
- 对后续工作的影响：后续 security advisory、私有 issue、披露材料可直接从 `poc/<true-positive-id>/` 取用，并可通过生成脚本按最新 truth 集合再生成。
- 版本化影响：`.gitignore` 只放行本次标准化 PoC 包固定文件名和小日志附件；其他任意 `poc/` 私有草稿仍默认忽略。
- 破坏性变更：无；未执行任何 DoS 探针，未修改 CodeQL 查询、ranking、verdict 或动态验证逻辑。

---

## [2026-06-30] 应用级动态二值集合恢复全批次去重口径

### 修改时间
2026-06-30 22:03

### 变更类型
- [Bug 修复] 动态验证二值真阳性集合批次范围修正
- [文档] 全批次去重结果刷新

### 核心改动
- 修正 `scripts/collect_dynamic_validation_binary_truth.py` 的严格审计批次：`p0`、`p1`、`p2`、`new`、`new_retest` 全部参与去重后的 `confirmed_true_positive` 判定。
- 保留原有去重优先级 `new_retest > new > p2 > p1 > p0`；同 ID 多批次出现时选择优先级更高的记录。
- 重新覆盖 `BINARY_TRUTH_COLLECTION.md` 和 `binary_truth_collection.json`，当前全批次去重结果为 29 条 `confirmed_true_positive`、160 条 `unconfirmed_or_non_oom`；来源分布为 P0 8、P1 11、new 8、new_retest 2、P2 0。
- 更正上一轮因只聚焦 `new/new_retest/p2` 导致的 10 条 confirmed 中间口径；P0/P1 动态真阳性现在纳入该二值集合。

### 交付成果
- 修改脚本：`scripts/collect_dynamic_validation_binary_truth.py`
- 覆盖结果：`results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md`、`results/applications_dynamic_validation/binary_truth_collection.json`
- 测试/验证结果：`python3 scripts/collect_dynamic_validation_binary_truth.py` 执行成功；`python3 -m py_compile scripts/collect_dynamic_validation_binary_truth.py` 通过；`python3 -m json.tool results/applications_dynamic_validation/binary_truth_collection.json` 通过。

### 依赖与影响
- 依赖：既有 `p0/p1/p2/new/new_retest` 动态验证结果。
- 对后续工作的影响：论文/报告若引用应用级动态二值真阳性集合，应使用当前 29 条全批次去重 confirmed 口径。
- 破坏性变更：只修正结果聚合范围；未修改动态 PoC、CodeQL 查询、ranking 或 AOSP verdict 语义。

---

## [2026-06-30] new/P2 五条候选 PoC 补强与二值集合刷新

### 修改时间
2026-06-30 21:58

### 变更类型
- [功能改进] 应用级动态验证 PoC 补强
- [文档] new/new_retest/P2 二值真阳性集合刷新

### 核心改动
- 按用户要求补强 `DRUID-APP-STATIC-0001`、`SKYWALKING-APP-STATIC-0003`、`HERTZBEAT-DOS-0001`、`TB-APP-STATIC-0001`、`SBA-APP-STATIC-0002` 五条此前证据不足的候选，并坚持至少 1GiB JVM heap/direct 或目标容器内存口径。
- `DRUID-APP-STATIC-0001` 修复 size ladder 未覆盖 512MiB 的问题，改为流式发送大 body；在 `DRUID_XMS=1g` / `DRUID_XMX=1g` 下单个 512MiB `text/plain` SQL body 触发 Router `OutOfMemoryError: Java heap space`。
- `TB-APP-STATIC-0001` 新增 large-value/timeseries-large-value chunked JSON payload；在 ThingsBoard `-Xmx1024m` / 2g 容器下，512MiB telemetry body 触发 `Handler dispatch failed: java.lang.OutOfMemoryError: Java heap space`。
- `HERTZBEAT-DOS-0001` 将 HertzBeat 补测提升到 2g 容器、1g heap/direct，并补回 Apache Arrow Java 21 `--add-opens`；约 21.7k 个唯一 job/instance 后触发 1GiB direct-buffer OOM，push 面出现重复 502。
- `SBA-APP-STATIC-0002` 增加每实例 retained bytes（8 个 4KiB cookie、4KiB metadata、30k instances）并以 `--min-heap 1g` 补测，仍为 `completed_without_oom`；`SKYWALKING-APP-STATIC-0003` 增加 ack 解码和诊断采样，32 条 AsyncProfiler 流均被接受但 1g/2g 下未 OOM，继续保持 `observed_growth_not_confirmed`。
- 将二值真相 collector 的严格审计范围恢复为本轮要求的 `new/new_retest/p2`，P1 结果保留在 P1 动态报告中，不纳入当前 `BINARY_TRUTH_COLLECTION`。

### 交付成果
- 修改脚本/PoC：`scripts/collect_dynamic_validation_binary_truth.py`、`scripts/run_application_p2_dynamic_validation.py`、`results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/probe.py`、`results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/probe.py`、`results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/probe.py`、`results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/start_commands.sh`、`results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0003/probe.py`
- 覆盖 case 结果：`results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/result.json`、`results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/result.json`、`results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/result.json`、`results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0003/result.json`
- 覆盖汇总：`results/applications_dynamic_validation/new/summary.json`、`results/applications_dynamic_validation/new/findings.jsonl`、`results/applications_dynamic_validation/new/summary.csv`、`results/applications_dynamic_validation/new/DYNAMIC_VALIDATION_REPORT.md`、`results/applications_dynamic_validation/p2/summary.json`、`results/applications_dynamic_validation/p2/P2_DYNAMIC_VALIDATION_REPORT.md`
- 二值汇总：`results/applications_dynamic_validation/binary_truth_collection.json`、`results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md`，当前为 10 条 `confirmed_true_positive` 与 179 条 `unconfirmed_or_non_oom`
- 新增/补强关键证据：Druid `evidence/router_oom_reinforce_excerpt.txt`、ThingsBoard `logs/probe_results_reinforce_telemetry_large.jsonl`、HertzBeat `evidence/probe_summary_reinforce.json` / `evidence/oom_reinforce_excerpt.txt`、SkyWalking `evidence/probe_reinforce_diag_32x30m.json`

### 依赖与影响
- 依赖：本地 Docker、既有应用源码/镜像缓存、Spring Boot Admin 构建产物、SkyWalking OAP/BanyanDB 镜像。
- 对后续工作的影响：`new/new_retest/p2` 强证据集合从 7 条更新为 10 条；Druid SQL、ThingsBoard telemetry、HertzBeat push 可进入论文强真阳性数据，SkyWalking AsyncProfiler 与 SBA CookieStore 仍不能按 confirmed 表述。
- 破坏性变更：二值集合范围从上一条 P1 实验口径恢复为 `new/new_retest/p2`；未修改 CodeQL 查询、ranking 或 AOSP verdict 语义。

---

## [2026-06-30] P1 三条优先 PoC 补强与 1G 复测

### 修改时间
2026-06-30 21:13

### 变更类型
- [功能改进] 应用级 P1 动态验证 PoC 补强
- [文档] P1 与二值真阳性集合刷新

### 核心改动
- 优先补强 `JMQTT-APP-STATIC-0002`、`ERUPT-APP-STATIC-0002`、`XXL-JOB-APP-STATIC-0003` 三条此前未确认的 P1 候选，并使用 `--min-heap 1g` 复测覆盖旧结果。
- `JMQTT-APP-STATIC-0002` 将 QoS2 PUBLISH payload 固定在默认 `maxMsgSize=512KiB` 以下，保留半握手 in-flight 消息；1G 堆下发送 2030 条后触发 `java.lang.OutOfMemoryError: Java heap space`。
- `ERUPT-APP-STATIC-0002` 将探针入口从 GET-only `/erupt-api/login` 修正为真实 POST `/erupt-api/data/table/EruptUser`，匿名 JSON body 先经过 `HttpServletRequestFilter$EruptRequestWrapper` 复制；1G 堆下 13 个约 36MiB body 触发 Java heap OOM。
- `XXL-JOB-APP-STATIC-0003` 将 GLUE_GROOVY handler 改为阻塞型执行，按默认 token 触发大量唯一 `jobId` 的 `JobThread`；1G 堆下 780 次触发后出现 `unable to create native thread`，按线程耗尽型 target failure 计为确认。
- 将 P1 报告文案从单一 OOM 真阳性扩展为目标资源失败真阳性，覆盖 `verified_oom` 和 `confirmed_thread_exhaustion`；二值真相 collector 将 P1 纳入严格审计批次。
- 当前 P1 严格 1G confirmed 更新为 11 条；全局二值集合更新为 18 条 `confirmed_true_positive` 与 171 条 `unconfirmed_or_non_oom`。

### 交付成果
- 修改脚本：`scripts/run_application_p1_dynamic_validation.py`、`scripts/collect_dynamic_validation_binary_truth.py`
- 覆盖结果：`results/applications_dynamic_validation/p1/summary.json`、`results/applications_dynamic_validation/p1/findings.jsonl`、`results/applications_dynamic_validation/p1/summary.csv`、`results/applications_dynamic_validation/p1/P1_DYNAMIC_VALIDATION_REPORT.md`
- 二值汇总：`results/applications_dynamic_validation/binary_truth_collection.json`、`results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md`
- 关键日志：`results/applications_dynamic_validation/p1/logs/JMQTT-APP-STATIC-0002.log`、`results/applications_dynamic_validation/p1/logs/ERUPT-APP-STATIC-0002.log`、`results/applications_dynamic_validation/p1/logs/XXL-JOB-APP-STATIC-0003.log`
- 测试/验证结果：`python3 scripts/run_application_p1_dynamic_validation.py --min-heap 1g --case JMQTT-APP-STATIC-0002 --case ERUPT-APP-STATIC-0002 --case XXL-JOB-APP-STATIC-0003` 执行成功；`python3 scripts/collect_dynamic_validation_binary_truth.py` 执行成功；三条补强 case 均进入 `confirmed_true_positive`。

### 依赖与影响
- 依赖：本地 Docker、MySQL 镜像缓存、P1 目标应用既有源码与构建产物。
- 对后续工作的影响：论文/报告中的 P1 confirmed 集合应使用当前 11 条严格 1G 结果；线程耗尽类证据按 confirmed target failure 单独表述，不再混写为 heap OOM。
- 破坏性变更：统计口径将 P1 纳入严格审计批次；未修改 CodeQL 查询、ranking 或 verdict 语义。

---

## [2026-06-30] new/new_retest/P2 动态真阳性 1G 证据复核

### 修改时间
2026-06-30 20:57

### 变更类型
- [功能改进] 应用级动态验证证据门槛收紧
- [文档] 强证据二元真阳性集合刷新

### 核心改动
- 按用户要求复核 `results/applications_dynamic_validation/` 下 P2、`new`、`new_retest` 批次的真阳性；实际目录为 `new_retest`，未发现 `new_reset` 目录。
- 将旧低堆 confirmed 记录按至少 1GiB JVM heap 或目标进程/容器内存证据重新审计：保留 Zipkin、Solr、SkyWalking pprof、Druid Avatica 的 1G 补测 OOM 证据，并继续保留既有 1G+ 证据的 Presto、ThingsBoard TB-0002、Dependency-Track。
- 覆盖降级证据不足或未复现的旧记录：Druid SQL 在 `DRUID_XMS=1g` / `DRUID_XMX=1g` 下完成探针且 HTTP 仍可用；SkyWalking AsyncProfiler 在 `-Xmx1g` / 2GiB OAP 容器下 48/96 条流未 OOM；HertzBeat 与 ThingsBoard TB-0001 仅保留低内存历史证据，不进入强真阳性集合。
- 收紧 `scripts/collect_dynamic_validation_binary_truth.py`：只把审计批次 `p2/new/new_retest` 中 confirmed target failure 且有 >=1GiB heap、`-Xmx` 或目标进程/容器内存证据的记录归为 `confirmed_true_positive`；旧 P0/P1 未纳入本轮强真阳性集合。
- 刷新二元集合为 7 条 `confirmed_true_positive` 与 182 条 `unconfirmed_or_non_oom`。

### 交付成果
- 修改脚本：`scripts/collect_dynamic_validation_binary_truth.py`
- 覆盖结果：`results/applications_dynamic_validation/binary_truth_collection.json`、`results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md`
- 更新 case 结果：`results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/result.json`、`results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/result.json`、`results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002/result.json`、`results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0003/result.json`、`results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001/result.json`、`results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002/result.json`、`results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001/result.json`、`results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001/result.json`
- 新增/补强关键证据：Zipkin `logs/probe_results_1g_confirmed.jsonl`、Solr `evidence/probe_observations.json`、SkyWalking pprof `logs/probe-failure-1g-48stream-30m.json`、Druid Avatica `logs/router_after_1g_oom.log` 与对应 inspect/log 文件。
- 测试/验证结果：`python3 scripts/collect_dynamic_validation_binary_truth.py` 执行成功；`python3 -m json.tool results/applications_dynamic_validation/binary_truth_collection.json` 通过；`python3 -m py_compile scripts/collect_dynamic_validation_binary_truth.py` 通过；`python3 scripts/check_phase3_consistency.py` 通过，结果为 37/37 matched；`python3 scripts/check_web_real_regression.py` 通过，结果为 6/6 phase3 hit、6 dynamic-only pending query；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过，288 个积格点单调；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression；`git diff --check` 通过。

### 依赖与影响
- 依赖：本地 Docker 镜像缓存、既有 `new/new_retest/p2` 动态验证 case 目录和本轮 1G 补测证据。
- 对后续工作的影响：论文和披露材料中应用级强真阳性集合应使用当前 7 条 >=1GiB 证据集合；低堆 OOM 只能作为历史弱证据或待增强候选。
- 破坏性变更：统计口径收紧会排除旧低内存真阳性；未修改 CodeQL 查询、ranking 或 verdict 语义。

---

## [2026-06-30] P1 11 条增强 PoC 1G 补测

### 修改时间
2026-06-30 20:55

### 变更类型
- [功能改进] 应用级 P1 动态验证增强
- [文档] P1 1G confirmed 真阳性集合刷新

### 核心改动
- 按第一优先级 5 条、第二优先级 6 条对 P1 PoC 做增强并使用 `--min-heap 1g` 补测，继续坚持真实外部 HTTP/协议请求触发目标 JVM `OutOfMemoryError` 才提升为真阳性。
- 第一优先级中 `ERUPT-APP-STATIC-0001`、`SMQTT-APP-STATIC-0003`、`SMQTT-APP-STATIC-0006` 在 1G 堆下确认 OOM；`JMQTT-APP-STATIC-0002`、`XXL-JOB-APP-STATIC-0003` 增强后仍未确认 OOM。
- 第二优先级中 `REBUILD-APP-STATIC-0003`、`CITRUS-APP-STATIC-0002` 在 1G 堆下确认 OOM；`OPSLI-BOOT-APP-STATIC-0001`、`XXL-BOOT-APP-STATIC-0001`、`RYVF-APP-STATIC-0002`、`ERUPT-APP-STATIC-0002` 增强后仍未确认 OOM。
- 增强内容包括更高 captcha height、更大的 JSON/body payload、更大的 MQTT QoS2 payload 与 topic key 空间、更高触发次数和更长探针窗口；新增 OOM 后已覆盖 `results/applications_dynamic_validation/p1/` 下旧结果。
- P1 严格 1G 真阳性从 3 条更新为 8 条；全局二值集合更新为 18 条 `confirmed_true_positive` 与 171 条 `unconfirmed_or_non_oom`。

### 交付成果
- 修改脚本：`scripts/run_application_p1_dynamic_validation.py`
- 覆盖结果：`results/applications_dynamic_validation/p1/summary.json`、`findings.jsonl`、`summary.csv`、`P1_DYNAMIC_VALIDATION_REPORT.md`
- 二值汇总：`results/applications_dynamic_validation/binary_truth_collection.json`、`results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md`
- 新增/补强关键日志：`results/applications_dynamic_validation/p1/logs/ERUPT-APP-STATIC-0001.log`、`SMQTT-APP-STATIC-0003.log`、`SMQTT-APP-STATIC-0006.log`、`REBUILD-APP-STATIC-0003.log`、`CITRUS-APP-STATIC-0002.log`
- 测试/验证结果：`python3 scripts/run_application_p1_dynamic_validation.py --min-heap 1g --case ...` 执行成功，本轮 11 条中 5 条新增 1G confirmed；`python3 scripts/collect_dynamic_validation_binary_truth.py` 执行成功；8 条 P1 confirmed 日志均包含 `-Xmx1g` 与 `OutOfMemoryError`；`python3 -m py_compile scripts/run_application_p1_dynamic_validation.py scripts/collect_dynamic_validation_binary_truth.py` 通过；`python3 scripts/check_phase3_consistency.py` 通过，结果为 37/37 matched；`python3 scripts/check_web_real_regression.py` 通过，结果为 6/6 phase3 hit、6 dynamic-only pending query；`git diff --check` 通过

### 依赖与影响
- 依赖：本地 Docker、MySQL/Redis 镜像缓存、P1 目标应用既有源码与构建产物。
- 对后续工作的影响：论文/报告中的 P1 confirmed 集合应使用当前 8 条严格 1G 结果；本轮未确认的 6 条保留为弱证据或低优先级候选，不再按真阳性表述。
- 破坏性变更：无；未修改 CodeQL 查询、ranking 或 verdict 语义。

---

## [2026-06-30] 应用级动态验证严格 1G 堆真阳性统计口径

### 修改时间
2026-06-30 20:30

### 变更类型
- [功能改进] 动态验证统计口径收敛
- [文档] 权威应用级真阳性数量刷新

### 核心改动
- 统一应用级动态验证统计口径：只有 confirmed target failure 且显式 JVM heap / `-Xmx` 至少 1GiB 的结果才计为真阳性。
- 将 P0/P1/P2 runner 导出的 `summary.json`、`findings.jsonl`、`summary.csv` 中 `true_positive` 字段改为严格 1G 堆口径；小堆 OOM 仍保留原始 `status`、日志和 OOM 信号，但不再计入真阳性。
- 将二值真相归并脚本改为只接受显式 JVM heap / `-Xmx` 证据，container memory limit-only 证据统一归入 `unconfirmed_or_non_oom`。
- 刷新当前权威统计：P0 为 8 条严格真阳性，P1 为 3 条，P2 为 0 条；五批次归并二值真相为 13 条 `confirmed_true_positive` 与 176 条 `unconfirmed_or_non_oom`。

### 交付成果
- 修改脚本：`scripts/run_application_p0_dynamic_validation.py`、`scripts/run_application_p1_dynamic_validation.py`、`scripts/run_application_p2_dynamic_validation.py`、`scripts/collect_dynamic_validation_binary_truth.py`
- 覆盖结果：`results/applications_dynamic_validation/p0/summary.json`、`results/applications_dynamic_validation/p1/summary.json`、`results/applications_dynamic_validation/p2/summary.json` 及对应 `findings.jsonl`、`summary.csv`、动态验证报告
- 二值汇总：`results/applications_dynamic_validation/binary_truth_collection.json`、`results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md`
- 文档：`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：`python3 scripts/collect_dynamic_validation_binary_truth.py` 执行成功；严格汇总检查显示 P0/P1/P2 真阳性分别为 8/3/0，二值集合为 13/176；`python3 -m py_compile scripts/collect_dynamic_validation_binary_truth.py scripts/run_application_p0_dynamic_validation.py scripts/run_application_p1_dynamic_validation.py scripts/run_application_p2_dynamic_validation.py` 通过；`git diff --check` 通过；`python3 scripts/check_phase3_consistency.py` 通过，结果为 37/37 matched；`python3 scripts/check_web_real_regression.py` 通过，结果为 6/6 phase3 hit、6 dynamic-only pending query

### 依赖与影响
- 依赖：现有 `results/applications_dynamic_validation/` 下五个批次的动态验证产物，不重新执行破坏性或高负载探针。
- 对后续工作的影响：论文统计、补测队列和披露材料均应使用严格 1G 堆真阳性口径；旧小堆 OOM 只能作为待增强证据或候选。
- 破坏性变更：统计口径收紧会降低 confirmed 数量；未修改 CodeQL 查询、ranking 或 verdict 语义。

---

## [2026-06-30] P1 旧真阳性 1G 严格复测与二值真相收敛

### 修改时间
2026-06-30 20:29

### 变更类型
- [功能改进] 应用级 P1 动态验证严格复测
- [文档] 1G 证据门槛下的二值真相集合刷新

### 核心改动
- 对旧二值真相集合中属于 P1 的 17 条真阳性按 `--min-heap 1g` 重新执行动态验证，并覆盖 `results/applications_dynamic_validation/p1/` 下的汇总结果。
- 复测后仅 `REBUILD-APP-STATIC-0002`、`WGCLOUD-APP-STATIC-0002`、`XXL-JOB-APP-STATIC-0004` 在 1G 堆限制下仍由外部 HTTP/协议请求触发目标 JVM `java.lang.OutOfMemoryError`。
- 将旧小堆证据依赖较强的 14 条 P1 结果降级为 `completed_without_oom`，包括 `CITRUS-APP-STATIC-0002`、`ERUPT-APP-STATIC-0001`、`ERUPT-APP-STATIC-0002`、`JMQTT-APP-STATIC-0002`、`OPSLI-BOOT-APP-STATIC-0001`、`REBUILD-APP-STATIC-0003`、`RYVF-APP-STATIC-0002`、`SBA-APP-STATIC-0001`、`SMQTT-APP-STATIC-0001`、`SMQTT-APP-STATIC-0003`、`SMQTT-APP-STATIC-0006`、`XXL-BOOT-APP-STATIC-0001`、`XXL-BOOT-APP-STATIC-0003`、`XXL-JOB-APP-STATIC-0003`。
- 扩展 `scripts/collect_dynamic_validation_binary_truth.py` 的输出字段，保留 `heap_or_limit`、`requests_sent`、`failure_signal`、`log_path` 和证据摘要，并按严格 1G 证据口径生成二值真相集合。
- 识别下一轮值得增强 PoC 的候选：优先 `SMQTT-APP-STATIC-0006`、`JMQTT-APP-STATIC-0002`、`ERUPT-APP-STATIC-0001`、匿名 JSON body copy 系列和 `XXL-JOB-APP-STATIC-0003`；`SBA-APP-STATIC-0001` 需要更高注册上限但日志/耗时成本较高，暂列次优先级。

### 交付成果
- 修改脚本：`scripts/collect_dynamic_validation_binary_truth.py`
- 覆盖结果：`results/applications_dynamic_validation/p1/summary.json`、`findings.jsonl`、`summary.csv`、`P1_DYNAMIC_VALIDATION_REPORT.md`
- 二值汇总：`results/applications_dynamic_validation/binary_truth_collection.json`、`BINARY_TRUTH_COLLECTION.md`
- 关键日志：`results/applications_dynamic_validation/p1/logs/REBUILD-APP-STATIC-0002.log`、`WGCLOUD-APP-STATIC-0002.log`、`XXL-JOB-APP-STATIC-0004.log`
- 测试/验证结果：`python3 scripts/run_application_p1_dynamic_validation.py --min-heap 1g --case ...` 执行成功，旧 P1 17 条真阳性收敛为 3 条 1G confirmed；`python3 -m py_compile scripts/collect_dynamic_validation_binary_truth.py scripts/run_application_p1_dynamic_validation.py` 通过；`python3 scripts/collect_dynamic_validation_binary_truth.py` 执行成功，严格二值集合当前为 `13` 条 `confirmed_true_positive` 与 `176` 条 `unconfirmed_or_non_oom`；`python3 scripts/check_phase3_consistency.py` 通过；`python3 scripts/check_web_real_regression.py` 通过；`git diff --check` 通过

### 依赖与影响
- 依赖：本地 Docker、MySQL/Redis 镜像缓存、P1 目标应用既有本地源码与构建产物。
- 对后续工作的影响：论文/报告中的 P1 真阳性统计应使用 1G 严格口径下的 3 条 confirmed；小堆 OOM 只能保留为候选或弱证据，除非后续增强 PoC 在 1G 下重新确认。
- 破坏性变更：无；未修改 CodeQL 查询、ranking 或 verdict 语义。

---

## [2026-06-30] P0 三条旧真阳性 1G 增强 PoC 补测与二值汇总刷新

### 修改时间
2026-06-30 20:00

### 变更类型
- [功能改进] 应用级 P0 动态验证增强
- [文档] 1G 堆补测结果归档与二值真相汇总刷新

### 核心改动
- 为 P0 动态验证 runner 增加 `--min-heap` 下限能力，并在 1G 补测模式下增强 `CITRUS-APP-STATIC-0001`、`POWERJOB-APP-STATIC-0002`、`RYVF-APP-STATIC-0001` 的 PoC 参数。
- `CITRUS-APP-STATIC-0001` 保持默认验证码尺寸和匿名 `/rest/verify/captcha` 入口，仅提高新 session 基数与并发，避免把非默认配置混入证据。
- `POWERJOB-APP-STATIC-0002` 使用更大的匿名 JSON body 与并发请求放大请求期 body copy/parse 压力。
- `RYVF-APP-STATIC-0001` 使用更高吞吐的低权限 `/test/user/save` static map 写入，保留 1G 下请求参数和并发信息。
- 重新运行 `scripts/collect_dynamic_validation_binary_truth.py` 覆盖二值真相汇总；全局严格 1G 堆统计随后以 20:30 条目为准。

### 交付成果
- 修改脚本：`scripts/run_application_p0_dynamic_validation.py`
- 相关下限参数入口：`scripts/run_application_p1_dynamic_validation.py`、`scripts/run_application_p2_dynamic_validation.py`
- 覆盖结果：`results/applications_dynamic_validation/p0/summary.json`、`findings.jsonl`、`summary.csv`、`P0_DYNAMIC_VALIDATION_REPORT.md`
- 二值汇总：`results/applications_dynamic_validation/binary_truth_collection.json`、`BINARY_TRUTH_COLLECTION.md`
- 原始日志：`results/applications_dynamic_validation/p0/logs/CITRUS-APP-STATIC-0001.log`、`POWERJOB-APP-STATIC-0002.log`、`RYVF-APP-STATIC-0001.log`
- 测试/验证结果：`python3 -m py_compile scripts/run_application_p0_dynamic_validation.py` 通过；`python3 scripts/run_application_p0_dynamic_validation.py --min-heap 1g --case CITRUS-APP-STATIC-0001 --case POWERJOB-APP-STATIC-0002 --case RYVF-APP-STATIC-0001` 执行成功，三条均在 1G 堆下触发目标 JVM `java.lang.OutOfMemoryError`；`python3 scripts/collect_dynamic_validation_binary_truth.py` 执行成功

### 依赖与影响
- 依赖：本地 Docker、MySQL/Redis 镜像缓存、三个目标应用既有本地源码与构建产物。
- 对后续工作的影响：这三条旧 P0 真阳性可从“小堆证据”提升为 1G 堆强动态证据；二值真相汇总已反映当前 P0/P1/P2/new/new_retest 的最新覆盖结果。
- 破坏性变更：无；未修改 CodeQL 查询、ranking 或 verdict 语义。

---

## [2026-06-30] 动态验证结果二值真相归并

### 修改时间
2026-06-30 17:17

### 变更类型
- [新增功能] 动态验证结果二值归并脚本
- [文档] 应用级动态验证确认/未确认两类清单

### 核心改动
- 新增 `scripts/collect_dynamic_validation_binary_truth.py`，统一读取 `results/applications_dynamic_validation/` 下的 `p0`、`p1`、`p2`、`new`、`new_retest` 五个批次结果。
- 对 `p0/p1/p2` 的旧式 `findings.jsonl` 和 `new/new_retest` 的 `cases/*/result.json` 做统一标准化，并仅保留两类结果：`confirmed_true_positive` 与 `unconfirmed_or_non_oom`。
- 对跨批次重复 case 按批次新旧顺序去重，优先保留 `new_retest > new > p2 > p1 > p0` 的较新结论，解决 `openzipkin__zipkin-ZIPKIN-APP-STATIC-0001`、`dependencytrack__dependency-track-DTRACK-APP-STATIC-0001`、`apache__inlong-INLONG-APP-STATIC-0001` 等补测覆盖问题。
- 生成机器可读和人工可读汇总；该初始二值集合已由 20:30 的严格 1G 堆统计口径覆盖。

### 交付成果
- 新增脚本：`scripts/collect_dynamic_validation_binary_truth.py`
- 机器可读汇总：`results/applications_dynamic_validation/binary_truth_collection.json`
- 人工可读汇总：`results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md`
- 测试/验证结果：`python3 scripts/collect_dynamic_validation_binary_truth.py` 执行成功；`python3 scripts/check_phase3_consistency.py` 通过；`python3 scripts/check_web_real_regression.py` 通过；`git diff --check` 通过

### 依赖与影响
- 依赖：现有 `results/applications_dynamic_validation/` 下五个批次的动态验证产物。
- 对后续工作的影响：后续在论文统计、补测挑选和披露材料中，可直接使用该二值归并结果，而不再手工在多个批次间交叉去重。
- 破坏性变更：无；未修改 CodeQL 查询、ranking、verdict 语义或动态验证执行逻辑。

---

## [2026-06-30] 6 条高潜力阻塞样本补测归档到 new_retest

### 修改时间
2026-06-30 16:07

### 变更类型
- [功能改进] 应用级动态验证补测结果归档
- [文档] 高潜力 blocked/growth-only 样本利用条件刷新

### 核心改动
- 基于 `results/applications_dynamic_validation/new/manifest.normalized.jsonl` 中挑出的 6 条高潜力阻塞样本，新建 `results/applications_dynamic_validation/new_retest/` 作为独立补测批次，避免覆盖既有 `new/` 结果。
- 重新验证 `openzipkin__zipkin-ZIPKIN-APP-STATIC-0001` 与 `dependencytrack__dependency-track-DTRACK-APP-STATIC-0001`，分别确认匿名 Zipkin spans gzip 解压路径和低权限 Dependency-Track BOM 上传路径都能在默认部署下稳定触发目标 JVM `OutOfMemoryError`。
- 补跑 `apache__inlong-INLONG-APP-STATIC-0001` 的默认 Manager 登录路径：修正 case-local MySQL SQL 挂载权限后完成匿名登录探针，确认 `5000` 个唯一失败用户名会保留 `5005` 个 `UserLoginLockStatus` 实例并推高堆占用，但在 `2g` harness 下仍未触发 OOM 或持续不可用，因此收敛为 `observed_growth_not_confirmed`。
- 将 `apache__ambari-AMBARI-APP-STATIC-0001`、`apache__ranger-RANGER-APP-STATIC-0001`、`apache__linkis-LINKIS-APP-STATIC-0001` 的既有阻塞证据目录纳入 `new_retest/` 聚合，保留其 `environment_blocked` 结论，作为后续专项环境补齐的基线。
- 运行动态验证聚合脚本，生成 `summary.json`、`summary.csv`、`findings.jsonl`、`blocked_or_rejected.jsonl`、`DYNAMIC_VALIDATION_REPORT.md`，并补齐技能规范要求的 `validation_status.jsonl`。

### 交付成果
- 补测输出根：`results/applications_dynamic_validation/new_retest/`
- 聚合摘要：`results/applications_dynamic_validation/new_retest/summary.json`、`summary.csv`
- 聚合结果：`results/applications_dynamic_validation/new_retest/findings.jsonl`、`blocked_or_rejected.jsonl`、`validation_status.jsonl`
- 人工报告：`results/applications_dynamic_validation/new_retest/DYNAMIC_VALIDATION_REPORT.md`
- 单 case 证据：`results/applications_dynamic_validation/new_retest/cases/<case_id>/`
- 测试/验证结果：`python3 scripts/check_phase3_consistency.py` 通过；`python3 scripts/check_web_real_regression.py` 通过；补测批次聚合统计为 2 个 `confirmed_oom`、1 个 `observed_growth_not_confirmed`、3 个 `environment_blocked`

### 依赖与影响
- 依赖：既有 `results/applications_dynamic_validation/new/` case 证据目录、`docker.1ms.run/inlong/manager:latest` 本地镜像缓存，以及补测期间生成的 case-local compose 运行状态。
- 对后续工作的影响：`new_retest/` 可直接用于挑选下一轮最值得继续补环境的 blocked 样本；其中 InLong 现已从“镜像未就绪”推进到“默认匿名入口存在 retained growth 但未证实真实故障”。
- 破坏性变更：无；未修改 CodeQL 查询、ranking、verdict 语义或主 pipeline 逻辑。

---

## [2026-06-30] 51 条应用级 Java Web DoS 候选动态验证收敛到 new 批次

### 修改时间
2026-06-30 12:42

### 变更类型
- [功能改进] 应用级动态验证结果归档
- [文档] 批量动态验证汇总与利用条件说明

### 核心改动
- 使用 `$java-web-dos-dynamic-validator` 对 `manifest.normalized.jsonl` 中 51 条应用级候选执行默认部署动态验证，结果统一写入 `results/applications_dynamic_validation/new/`。
- 为每个 case 补齐 `case_plan.json`、`environment.md`、`data_prep.md`、`result.json` 以及按需的探针、日志和证据文件，并通过主控校验将完整性结果追加到 `validation_status.jsonl`。
- 运行聚合脚本生成 `summary.json`、`summary.csv`、`findings.jsonl`、`blocked_or_rejected.jsonl` 和 `DYNAMIC_VALIDATION_REPORT.md`；本批次收敛为 9 个 `confirmed_oom`、22 个 `observed_growth_not_confirmed`、20 个 blocked/restricted 类结果。
- 对默认环境未就绪、依赖镜像不可用、鉴权前置条件或默认入口不可达的目标保持 `environment_blocked`、`auth_blocked`、`precondition_blocked`、`default_not_reachable` 或 `non_default_only`，未将 growth-only 行为提升为 confirmed。

### 交付成果
- 动态验证总目录：`results/applications_dynamic_validation/new/`
- 聚合摘要：`results/applications_dynamic_validation/new/summary.json`、`summary.csv`
- 聚合结果：`results/applications_dynamic_validation/new/findings.jsonl`、`blocked_or_rejected.jsonl`
- 人工报告：`results/applications_dynamic_validation/new/DYNAMIC_VALIDATION_REPORT.md`
- 单 case 证据：`results/applications_dynamic_validation/new/cases/<case_id>/`
- 测试/验证结果：51/51 个 manifest case 均存在 `result.json`，聚合脚本执行成功，`python3 scripts/check_phase3_consistency.py` 与 `python3 scripts/check_web_real_regression.py` 待本次结果归档后复核

### 依赖与影响
- 依赖：前序静态批次 `results/java_web_dos_batch/20260628-233819/dynamic_validation_queue.jsonl` 与 `results/applications_dynamic_validation/new/manifest.normalized.jsonl`。
- 对后续工作的影响：`results/applications_dynamic_validation/new/` 可直接作为论文和复核阶段的新一批应用级默认部署动态证据输入；其中 blocked 类结果为环境/前置条件结论，不应视为 negative。
- 破坏性变更：无；未修改 CodeQL 查询、ranking、verdict 语义或 pipeline 逻辑。

---

## [2026-06-29] Java Web DoS 动态验证 Skill

### 修改时间
2026-06-29 13:51

### 变更类型
- [新增功能] 动态验证 Skill
- [文档] Subagent 动态验证流程与结果格式

### 核心改动
- 新增 `$java-web-dos-dynamic-validator`，用于接收上一轮静态分析结果文件和目标输出目录，按候选开启 subagent 执行默认部署动态验证。
- 约束 worker 必须完成环境准备、默认服务运行、必要数据或低权限账户准备、受控 HTTP/协议探测、证据采集和清理，并把利用条件写入 `utilization_conditions`。
- 明确 Docker/compose/release package 默认部署优先级、国内镜像加速使用原则、动态 confirmed 门槛、growth-only 降级规则和 blocked/not reproduced 分类。
- 新增聚合脚本，将各 case 的 `result.json` 汇总为 `summary.json`、`summary.csv`、`findings.jsonl`、`blocked_or_rejected.jsonl` 和 `DYNAMIC_VALIDATION_REPORT.md`。

### 交付成果
- 新增 Skill 主文件：`.codex/skills/java-web-dos-dynamic-validator/SKILL.md`
- 新增 UI 元数据：`.codex/skills/java-web-dos-dynamic-validator/agents/openai.yaml`
- 新增聚合脚本：`.codex/skills/java-web-dos-dynamic-validator/scripts/aggregate_dynamic_validation.py`
- 测试/验证结果：`quick_validate.py` 校验通过；聚合脚本使用临时样例执行成功并生成预期摘要文件。

### 依赖与影响
- 依赖：Codex subagent 工具可用时才能实际并发执行动态验证；不可用时 skill 会生成暂停状态和执行计划。
- 对后续工作的影响：可直接用于 `dynamic_validation_queue.jsonl`、`findings.jsonl` 或 Markdown 静态结果到默认部署动态证据的闭环验证。
- 破坏性变更：无；未修改 CodeQL 查询、runner、ranking、verdict 或既有动态验证脚本。

---

## [2026-06-29] 用户指定 34 个 Java Web 应用 DoS 批量静态猎取

### 修改时间
2026-06-29 01:09

### 变更类型
- [新增功能] 批量静态分析结果聚合
- [文档] 应用级 DoS 候选与动态验证队列归档

### 核心改动
- 使用 `$java-web-dos-batch-hunter` 编排用户指定的 34 个 Java Web 应用，每个目标由独立 worker 显式使用 `$java-web-dos-hunter` 执行 static-only 资源耗尽 DoS 分析。
- 保持默认并发 3，保留每个目标自己的 hunter 输出目录：`frameworks/applications/<slug>/results/applications_static_analysis/<slug>/`，并仅在 orchestration 仓库下写入 batch 汇总。
- 完成 34/34 个目标，聚合 52 条 finding，其中 29 条 `likely`、22 条 `needs_dynamic_probe`、1 条 `rejected`，生成 51 条动态验证队列候选；未执行动态 exploit/fuzz/load/OOM/network 测试。

### 交付成果
- 新增 batch manifest 与状态：`results/java_web_dos_batch/20260628-233819/manifest.normalized.jsonl`、`batch_status.jsonl`
- 新增聚合摘要：`results/java_web_dos_batch/20260628-233819/batch_summary.md`
- 新增聚合 JSONL：`aggregate_target_profiles.jsonl`、`aggregate_sinks.jsonl`、`aggregate_sources.jsonl`、`aggregate_flows.jsonl`、`aggregate_findings.jsonl`、`aggregate_rejected.jsonl`、`aggregate_dynamic_probe_plan.jsonl`、`aggregate_subagent_reviews.jsonl`、`aggregate_status.jsonl`
- 新增动态验证队列：`results/java_web_dos_batch/20260628-233819/dynamic_validation_queue.jsonl`
- 新增聚合 gap 与 inventory：`aggregate_gaps.md`、`aggregate_inventory.json`
- 测试/验证结果：batch 聚合脚本执行成功；必需 batch 文件均存在，聚合统计为 34 个 complete repository、0 个 missing hunter output、0 个 malformed JSONL record。

### 依赖与影响
- 依赖：34 个目标本地源码目录和 `$java-web-dos-hunter` worker 输出文件。
- 对后续工作的影响：可基于 `dynamic_validation_queue.jsonl` 选择高价值 `likely` / `needs_dynamic_probe` 候选进入隔离动态验证；当前结果均为静态分析结论，不应提升为 confirmed DoS。
- 破坏性变更：无；不修改目标应用源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache RocketMQ Dashboard 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 01:12

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/rocketmq-dashboard` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Spring MVC controller、Spring Security/auth 默认边界、RocketMQ client 生命周期、Guava cache、线程池队列和服务单例集合。
- 识别 1 个 `likely` 候选：默认开放的 `GET /test/runTask.do` 每次请求都会启动 RocketMQ consumer、producer 和一个无限循环 sender 线程，未见停止路径、全局 cap 或 per-client quota。
- 将消息分页 cache、Dashboard 采集 cache、consumer group map、collector executor queue、AutoCloseConsumerWrapper、CSRF token endpoint、monitor/ops 配置路径和 actuator 管理面按 bounded、server_controlled、request_local、disk_out_of_scope、not_amplifiable 或 admin_required 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__rocketmq-dashboard/results/applications_static_analysis/apache__rocketmq-dashboard/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：JSON/JSONL 格式校验通过，必需 hunter 文件无缺失；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改目标应用源码、CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__rocketmq-dashboard` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 `/test/runTask.do` 触发后的 live thread、RocketMQ client/remoting state、连接数、heap slope 和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache RocketMQ Dashboard 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Ranger 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 01:12

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/ranger` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Ranger KMS Jersey API、security-admin Spring Security/Jersey 配置、multipart import、匿名下载配置和 session 相关状态。
- 识别 1 个 `likely` 候选：KMS `generateEncryptedKeys()` 的 `num_keys` 查询参数直接驱动 `EncryptedKeyVersion` 列表和响应 JSON 列表增长，默认 KMS `GENERATE_EEK` ACL 为普通认证用户可达。
- 识别 1 个 `needs_dynamic_probe` 候选：KMS re-encrypt batch JSON 数组会被完整反序列化并复制到响应对象，但受默认 POST 大小、有效 encrypted-key 结构和运行时容器边界影响，未静态升级。
- 将 security-admin multipart 导入、匿名下载开关、未证明注册的 session listener 和有界 KMS ValueQueue cache 按 admin_required、requires_config_change、missing_path_proof 或 bounded 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__ranger/results/applications_static_analysis/apache__ranger/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：`target_profile.json` 与所有 JSONL 文件格式校验通过，必需 hunter 文件无缺失；`python3 scripts/check_phase3_consistency.py` 通过（37/37 matched），`python3 scripts/check_web_real_regression.py` 通过（6/6 phase3 hit，0 missing，6 dynamic-only pending query）；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、runner、ranking 或 verdict 语义。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__ranger` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离 KMS 实例中测量 `num_keys` 和 re-encrypt batch 的 heap slope、对象数、默认容器边界和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache Ranger 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache InLong 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 01:00

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/inlong` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 InLong Manager Spring MVC/Shiro、DataProxy Netty HTTP ingest、TubeMQ manager/broker web 面和默认 Docker/compose 暴露面。
- 识别 1 个 `likely` 候选：匿名 `POST /inlong/manager/api/anno/login` 失败登录路径把攻击者可控 `username` 保留到 Spring singleton `loginLockStatusMap`，未见 key cardinality 上限、TTL 或清理逻辑。
- 将 Manager request wrapper、DataProxy HTTP 参数/body 解析、SourceSnapshot cache、cluster install queue、multipart Excel import 和 TubeMQ broker admin servlet 按 request_local、bounded、admin_required 或 management_only 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__inlong/results/applications_static_analysis/apache__inlong/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：`target_profile.json` 与所有 JSONL 文件格式校验通过，必需 hunter 文件无缺失；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__inlong` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 login lockout map size、heap slope、默认请求速率/容器边界和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache InLong 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Guacamole Client 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:56

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/guacamole-client` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Jersey REST token/session、Guice `/tunnel`、WebSocket tunnel、auth-ban/TOTP/Duo/JSON/QuickConnect 扩展状态和 stream 转发路径。
- 识别 1 个 `likely` 候选：成功 `POST /api/tokens` 可在 singleton `HashTokenSessionMap` 中保留新的 `GuacamoleSession`，默认 60 分钟空闲回收且未见全局/每用户 session 数量上限。
- 识别 1 个 `needs_dynamic_probe` 候选：认证后 tunnel 创建可保留 per-session `UserTunnel` 和 HTTP tunnel registry，但受 15 秒空闲清理、连接权限、guacd/backend 和运行时连接边界影响，未静态升级。
- 将 auth-ban Caffeine cache、TOTP used-code map、Duo/SSO deferred session、JSON auth active connection registry、stream upload、admin 管理 API 和文件/历史记录路径按 bounded、cleanup_effective、disabled_by_default、request_local、admin_required 或 requires_config_change 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__guacamole-client/results/applications_static_analysis/apache__guacamole-client/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：`target_profile.json` 与所有 JSONL 文件格式校验通过，必需 hunter 文件无缺失；`python3 scripts/check_phase3_consistency.py` 通过（37/37 matched），`python3 scripts/check_web_real_regression.py` 通过（6/6 phase3 hit，0 missing）；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__guacamole-client` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 token session map 和 active tunnel map 的对象数、heap slope、默认认证 provider/连接配置边界和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache Guacamole Client 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Atlas 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 01:05

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/atlas` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Atlas Jersey/Spring Security REST 面、搜索任务、SearchTracker、RequestContext/ThreadLocal cache、admin import/export 和登录 session 标记。
- 未发现满足默认外部非管理员范围的 `confirmed`、`likely` 或 `needs_dynamic_probe` finding；将登录成功后的 `ServletContext` session-id 标记、搜索任务队列、active search registry、request-local 搜索结果集合、admin multipart import 和关系搜索按 admin_required、bounded、cleanup_effective、request_local 或 disabled_by_default 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__atlas/results/applications_static_analysis/apache__atlas/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：JSON/JSONL 格式校验通过；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__atlas` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：当前无默认外部非管理员动态补测候选；如后续扩大到普通有效用户或默认 admin 账户，可单独验证 `ServletContext` session-id 标记是否随 session 过期清理。
- 破坏性变更：无；未修改 Apache Atlas 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Solr 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:57

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/solr` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Solr Jetty/Servlet 分发、默认 `_default` configset、请求解析器、隐式 `/stream` handler、默认查询缓存和管理端点边界。
- 识别 3 个 `likely` 候选：默认 form-urlencoded 解析器近似无界堆内参数构造、multipart 非文件字段堆内字符串构造、默认 `/stream` daemon 表达式保留 attacker-named daemon/queue/thread。
- 将默认 query/filter/document cache、URL/header 参数膨胀、replication/backup/file upload、admin/node management 和 lazy/sample handler 按 `bounded`、`disk_out_of_scope`、`management_only` 或 `disabled_by_default` 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__solr/results/applications_static_analysis/apache__solr/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__solr` 源码快照，提交 `4eb42f0`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 parser heap slope、multipart 非文件字段 heap slope 和 `/stream` daemon map/thread 增长；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache Solr 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Ambari 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:50

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/ambari` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Ambari Jetty/Jersey API、Spring Security 过滤链、agent 证书入口、API 查询谓词解析、View provider 和 alert cache。
- 识别 1 个 `needs_dynamic_probe` 候选：默认 `/api/*` Spring Security 链在认证前执行 `RequestBodyCachingFilter`，对匿名请求 body 调用 `readAllBytes()` 缓存到堆内，且 Ambari 代码中未见 filter 级 body 上限；因默认连接器/反代 body limit 和实际不可用阈值未静态证实，未提升为 `likely` 或 `confirmed`。
- 将证书签名、查询谓词解析、View body buffering、alert cache 和重复 JAX-RS parser 路径按 server_controlled、request_local、requires_config_change、bounded 或 duplicate 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__ambari/results/applications_static_analysis/apache__ambari/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__ambari` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 pre-auth body caching 的 heap slope、默认 body-size 边界和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache Ambari 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] RuoYi-Vue-Plus 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:54

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `dromara/RuoYi-Vue-Plus` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Sa-Token 鉴权边界、默认启用 SSE、默认打包 demo 队列接口、验证码 Redis key、WebSocket、Actuator、上传导出和本地缓存。
- 识别 3 个 `likely` 候选：默认 SSE 静态 `SseEmitter` per-token 保留、demo delayed queue Redis 延迟队列保留、demo priority queue attacker-chosen queueName 基数增长；识别 1 个 `needs_dynamic_probe` 匿名短信验证码 Redis key 基数候选。
- 将 WebSocket、Actuator、邮箱验证码、登录欢迎任务、captcha image、本地 Caffeine cache 和磁盘上传导出类路径按 disabled_by_default、management_only、requires_config_change、bounded 或 disk_out_of_scope 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/dromara__ruoyi-vue-plus/results/applications_static_analysis/dromara__ruoyi-vue-plus/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：`target_profile.json` 与所有 JSONL 文件格式校验通过；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/dromara__ruoyi-vue-plus` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 SSE emitter map、Redisson delayed/priority queue、短信验证码/限流 Redis key 的对象数、内存斜率、默认 demo surface 暴露和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 RuoYi-Vue-Plus 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] GeoServer 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:46

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `geoserver/geoserver` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认 Servlet/Spring MVC/OWS Dispatcher、WMS GetMap/UTFGrid 渲染、REST 上传/配置接口、WFS stored query、GeoWebCache transient cache 和 header ThreadLocal。
- 未发现满足默认外部非管理员、无有效容量边界条件的 `confirmed`、`likely` 或 `needs_dynamic_probe` finding；将 WMS 大尺寸渲染、UTFGrid、REST 上传、WFS stored query、GWC cache 和 header map 按 bounded、admin_required、request_local、cleanup_effective 或 missing_path_proof 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/geoserver__geoserver/results/applications_static_analysis/geoserver__geoserver/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：JSON/JSONL 格式校验通过；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/geoserver__geoserver` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：当前无默认外部非管理员动态补测候选；如后续扩大范围，可单独审计非默认数据目录、放宽 REST/服务安全配置、可选扩展模块或 GeoWebCache 外部依赖内部实现。
- 破坏性变更：无；未修改 GeoServer 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Dependency-Track 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:45

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `DependencyTrack/dependency-track` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Alpine/Jersey 鉴权过滤器、匿名接口、BOM/VEX 上传、CEL 表达式缓存、session token、分页 token 和 memory cache provider。
- 识别 2 个 `needs_dynamic_probe` 低权限业务上传候选：BOM 与 VEX 上传路径会将请求体或 multipart part 累积为堆内 `byte[]` 后再验证/入队；因默认请求体限制、multipart buffering 和默认权限分配未静态证实，未提升为 `likely` 或 `confirmed`。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/dependencytrack__dependency-track/results/applications_static_analysis/dependencytrack__dependency-track/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：JSON/JSONL 格式校验通过；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/dependencytrack__dependency-track` 源码快照，提交 `4eb42f0`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 BOM/VEX 上传的 heap slope、请求体限制、multipart buffering 和 workflow backlog 行为；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Dependency-Track 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Linkis 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 03:05

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/linkis` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Linkis Gateway、Eureka 服务发现、ContextService、context cache、multipart 默认限制和管理/管理员端点。
- 识别 1 个 `likely` 普通认证用户候选：`/contextservice/setValue*` 可将攻击者控制的 context key/value 写入进程内 per-context map 与倒排索引；外层 contextID cache 有默认 3000/3h 边界，但单个 contextID 内 key/index 未见容量上限。
- 将网关请求体聚合、multipart/BML 文件路径、Eureka 注册表和管理员 cleanup/search 路径按 bounded、management_only 或 admin_required 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__linkis/results/applications_static_analysis/apache__linkis/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__linkis` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 ContextService per-context map/index 对象数、堆增长和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache Linkis 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache StreamPark 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:39

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/streampark` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认 Shiro 匿名链、WebSocket endpoint、代理服务、multipart 上传、线程池队列、OpenAPI 作业启动和 MyBatis 缓存。
- 识别 1 个 `likely` 默认匿名候选：`/websocket/{id}` 将攻击者控制的 path id 作为静态 WebSocket session map key，缺少应用级 session 数量、id cardinality 或 per-client quota；将代理体/响应体复制、multipart 上传、bounded executor、future map 和 statement cache 按 scope 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__streampark/results/applications_static_analysis/apache__streampark/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：JSON/JSONL 格式校验通过；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__streampark` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 WebSocket session map、连接数、堆和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache StreamPark 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Pinot 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 02:05

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/pinot` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认 Broker Jersey/JAX-RS 查询 API、cached executor、ManagedAsync 默认 executor、response store、controller/server admin 资源和 workload config 管理路径。
- 识别 2 个 `likely` 默认外部 Broker 线程耗尽候选：`POST /query/compare` 每请求向 unbounded cached executor 提交双查询任务，以及默认关闭 bounded Jersey executor 下 `@ManagedAsync` 查询端点的无界异步线程处理风险；将磁盘型 response store、request-local parser/map、controller/server admin 面和 workload config 管理路径按 scope 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__pinot/results/applications_static_analysis/apache__pinot/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：JSON/JSONL 格式校验通过；本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__pinot` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 Broker thread count、async-task-thread 数量、请求延迟和服务可用性；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache Pinot 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache NiFi 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 01:30

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/nifi` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认 Jetty/JAX-RS Web API、`/access/token`、HTTP Site-to-Site transaction map、流程导入/替换异步请求、SAML/OIDC/logout cache 和内容长度/速率过滤器。
- 未发现满足默认外部非管理员、无有效容量边界条件的 `confirmed`、`likely` 或 `needs_dynamic_probe` finding；将事务表、异步请求、上传解析、SAML/OIDC、两阶段提交和可选 Processor servlet 按 bounded、requires_config_change、cleanup_effective、management_only 或 missing_path_proof 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__nifi/results/applications_static_analysis/apache__nifi/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__nifi` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：当前无默认外部非管理员动态补测候选；如后续扩大范围，可单独审计启用 public port 的 Site-to-Site、OIDC/SAML SSO 或 operator-created processor HTTP servlet。
- 破坏性变更：无；未修改 Apache NiFi 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache HertzBeat 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 01:07

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/hertzbeat` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认 Sureness 鉴权排除、Prometheus push gateway、匿名 SSE 订阅管理器、OTLP/log ingestion 和默认 memory queue。
- 识别 4 个 `likely` 默认匿名候选：Prometheus push `jobInstanceMap` key cardinality，以及 alert/log/manager 三组 SSE emitter/subscriber 无应用级连接保留上限；识别 1 个 `needs_dynamic_probe` 普通用户日志内存队列候选。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__hertzbeat/results/applications_static_analysis/apache__hertzbeat/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__hertzbeat` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 push map、SSE subscriber map、连接数、队列长度和堆曲线；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 HertzBeat 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Zeppelin 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:24

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/zeppelin` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 Jersey/JAX-RS REST、Shiro 默认 URL 门禁、WebSocket 会话表、SessionManagerService、NotebookService 执行路径和 interpreter scheduler。
- 识别 2 个 `likely` 默认普通认证候选：`POST /api/session` 可保留无上限 `SessionInfo` map entries；重复 paragraph run 可进入默认无容量上限的 interpreter scheduler queue。WebSocket map、TicketContainer、notebook import、JMX/管理面路径按 cleanup_effective、server_controlled、disk_out_of_scope、requires_config_change 或 admin_required 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__zeppelin/results/applications_static_analysis/apache__zeppelin/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__zeppelin` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 `/api/session` map/heap 增长、scheduler queue 长度、清理路径和服务影响；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Apache Zeppelin 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Graylog2 Server 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:46

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `Graylog2/graylog2-server` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认 Jersey REST、Shiro 认证门禁、搜索执行线程池、SearchJob cache、静态资源 cache、协议 input/parser 和 support bundle 管理路径。
- 识别 1 个 `likely` 默认低权限候选：普通已认证用户搜索执行可向默认无界 `QueryEngine` worker queue 提交任务；将 SearchJob cache、静态资源 cache、Netflow input parser、support bundle 和 request-local parser 集合按 bounded、requires_config_change、admin_required 或 request_local 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/graylog2__graylog2-server/results/applications_static_analysis/graylog2__graylog2-server/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/graylog2__graylog2-server` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量默认搜索查询队列长度、堆增长、取消行为和服务影响；当前 finding 不应表述为 confirmed。
- 破坏性变更：无；未修改 Graylog2 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache ShenYu 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:32

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/shenyu` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 bootstrap 网关请求链、admin 白名单 `/alert/report`、`/websocket`、metrics raw-path label、multipart body 聚合和本地插件控制面。
- 未发现满足默认外部非管理员、无有效容量边界条件的 `confirmed` 或 `likely` finding；将告警队列、metrics、multipart、websocket 和 local plugin cache mutation 按 bounded、requires_config_change 或 missing_path_proof 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__shenyu/results/applications_static_analysis/apache__shenyu/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：已校验 `target_profile.json` 与全部 JSONL 文件可解析；本轮未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑；按约束未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__shenyu` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：当前无默认外部非管理员动态补测候选；如后续扩大范围，可单独审计启用 metrics 后的 raw-path label cardinality 或管理面/插件配置依赖路径。
- 破坏性变更：无；未修改 Apache ShenYu 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] SonarQube 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:14

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `SonarSource/sonarqube` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认 WebService/SSE push API、Tomcat connector body/connection 边界、request body parser、webhook async queue 和权限门禁。
- 识别 1 个 `likely` 默认低权限候选：`/api/push/sonarlint_events` 对普通登录且具备项目 `USER` 权限的客户端保留无应用级上限的 SSE async client/heartbeat 状态；管理权限、配置依赖、request-local 和缺少路径证明的候选按范围约束拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/sonarsource__sonarqube/results/applications_static_analysis/sonarsource__sonarqube/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/sonarsource__sonarqube` 源码快照，提交 `4eb42f0`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量默认 SSE 连接保留、`SonarLintClientsRegistry` 规模、heartbeat 队列和堆/FD 曲线。
- 破坏性变更：无；未修改 SonarQube 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Flowable Engine 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:17

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `flowable/flowable-engine` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认 `flowable-rest` 安全配置、匿名 `/docs/**`、REST 部署上传、流程/任务变量写入、分页查询和管理 job 批量操作。
- 未发现满足默认外部非管理员、非磁盘 retained resource 条件的 `confirmed`、`likely` 或 `needs_dynamic_probe` finding；将默认 REST 写入口按默认 admin gate、磁盘/数据库持久化、request-local 或缺少默认非管理员路径证明拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/flowable__flowable-engine/results/applications_static_analysis/flowable__flowable-engine/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/flowable__flowable-engine` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：如后续范围允许默认管理员凭据或单独证明默认非管理员 `access-rest-api` 用户，可重新评估部署上传和变量写入的 request-burst parser/memory 行为；当前无动态补测候选。
- 破坏性变更：无；未修改 Flowable 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Apache Druid 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:08

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/druid` 本地源码执行 static-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP/SQL query 入口和非磁盘资源；复核 SQL raw-body parser-state、Router Avatica protobuf buffering、SQL lifecycle registry、native query scheduler、listener/lookup/basic-security/test-tool 管理路径。
- 未发现可在静态阶段提升为 confirmed/likely 的默认外部非管理员漏洞；保留 2 个 request-burst memory/parser-state 候选为 `needs_dynamic_probe`，并将生命周期清理有效、管理面、管理员和测试工具路径按范围约束拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__druid/results/applications_static_analysis/apache__druid/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：已校验 `target_profile.json` 与全部 JSONL 文件可解析；本轮未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑；按约束未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__druid` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境确认默认 SQL raw-body 和 Router Avatica protobuf 请求体大小边界及堆增长曲线。
- 破坏性变更：无；未修改 Apache Druid 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] Trino 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:20

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `trinodb/trino` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 `/v1/statement` 查询提交、`QueuedStatementResource` 预分发查询保留、`DispatchManager` / `QueryTracker` 生命周期、OAuth2 token exchange、spooling 下载和 Web UI worker proxy。
- 未发现满足默认外部非管理员、无有效容量边界条件的 `confirmed` 或 `likely` finding；将查询生命周期状态、OAuth2 cache、spooling handle、worker proxy 和可选 trino-proxy 按 bounded、requires_config_change、request_local、missing_path_proof 或 disabled_by_default 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/trinodb__trino/results/applications_static_analysis/trinodb__trino/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/trinodb__trino` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：当前无动态补测候选；如后续扩大范围，可单独审计可选 connector/service HTTP 面和部署配置。
- 破坏性变更：无；未修改 Trino 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] CAS 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:10

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apereo/cas` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核默认登录 webflow、accept-users 默认凭据、内存 TicketRegistry、TGT/ST 票据保留、webflow 会话状态、actuator 管理面和可选 OAuth/OIDC/REST 支持模块。
- 识别 1 个 `likely` 默认配置内存保留候选：默认登录可创建不同 TGT 并写入无最大容量的默认 `ConcurrentHashMap` TicketRegistry；另保留 1 个服务票据 fanout 候选为 `needs_dynamic_probe`，因默认 registered-service 可达性未完全证明。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apereo__cas/results/applications_static_analysis/apereo__cas/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apereo__cas` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量默认登录驱动的 TicketRegistry map、堆和 GC 曲线，并先澄清 accept-users 默认凭据是否纳入论文默认生产口径。
- 破坏性变更：无；未修改 CAS 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] OpenSearch 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:05

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `opensearch-project/OpenSearch` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核 REST dispatch、PIT/scroll reader context、msearch 解析、aggregation bucket 上限、cancellable REST channel/task 跟踪和 admin/plugin 部署门槛。
- 未发现满足默认外部非管理员、无有效容量边界条件的 `confirmed` 或 `likely` finding；将 PIT、scroll、aggregation、msearch 和 cancellable client 模式分别按 bounded、request-local 或 cleanup-effective 拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/opensearch-project__opensearch/results/applications_static_analysis/opensearch-project__opensearch/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/opensearch-project__opensearch` 源码快照，提交 `4eb42f0`。
- 对后续工作的影响：如后续扩展范围，可针对 PIT/scroll 默认权限和插件安全角色做独立配置审计；当前无动态补测候选。
- 破坏性变更：无；未修改 OpenSearch 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-28] Presto 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-28 23:56

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `prestodb/presto` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；重点复核 `/v1/statement` 查询提交、`QueuedStatementResource` 预分发查询保留、`QueryTracker` 清理边界、rate limiter cache、presto-proxy 和 OAuth2 配置门槛。
- 识别 1 个默认外部可达的 `likely` 内存保留候选：未轮询的 `/v1/statement` 初始提交会在 dispatch 前保留 `Query` 对象，且静态清理逻辑跳过 `querySubmissionFuture == null` 的条目；其他 bounded、配置依赖、管理面或重复模式已拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/prestodb__presto/results/applications_static_analysis/prestodb__presto/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，按约束未运行动态 exploit/fuzz/load/OOM/network 测试；未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/prestodb__presto` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量未轮询查询提交的 `queries` map 和 heap slope。
- 破坏性变更：无；未修改 Presto 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-28] MeterSphere 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-28 23:59

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `metersphere/metersphere` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP/WebSocket 入口和非磁盘资源；复核匿名 WebSocket 会话表、任务运行缓存、导出 Future 管理、插件注册表、脚本黑名单缓存和上传/权限门控路径。
- 保留 2 个默认匿名 WebSocket session registry 连接/内存增长候选为 `likely`；将有 TTL/cleanup/权限门槛、server-controlled 注册和磁盘相关路径按范围或边界约束拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/metersphere__metersphere/results/applications_static_analysis/metersphere__metersphere/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑；按约束未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/metersphere__metersphere` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量默认匿名 `/ws/api/{reportId}` 与 `/ws/export/{fileId}` WebSocket session map、堆和连接数曲线。
- 破坏性变更：无；未修改 MeterSphere 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-28] yudao-cloud 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-28 23:53

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `YunaiV/yudao-cloud` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP/WebSocket 入口和非磁盘资源；复核 WebSocket 会话表、网关 token cache、匿名文件上传、验证码、签名 webhook、admin 导入导出和 IoT 协议连接管理路径。
- 保留 1 个默认 authenticated WebSocket session registry 连接/内存增长候选为 `likely`；将 gateway cache、multipart 上传、captcha、签名 webhook、admin/import 和非 HTTP IoT 协议路径按有效边界或范围约束拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/yunaiv__yudao-cloud/results/applications_static_analysis/yunaiv__yudao-cloud/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑；按约束未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/yunaiv__yudao-cloud` 源码快照，提交 `4eb42f0`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量默认 `/infra/ws` authenticated WebSocket session map、堆和连接数曲线。
- 破坏性变更：无；未修改 yudao-cloud 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-28] Zipkin 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-28 23:53

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `openzipkin/zipkin` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP/gRPC 入口和非磁盘资源；复核 Armeria HTTP collector、gRPC collector、Query API、默认 in-memory storage、storage throttle、broker collectors 和 actuator 管理面。
- 未发现满足默认外部非管理员门槛的 confirmed/likely 漏洞；保留 HTTP/gzip collector 与 gRPC unary proto3 span batch 两个 parser/request-burst 候选为 `needs_dynamic_probe`，并将默认 in-memory storage retained indexes 按 `max-spans` 逐出边界拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/openzipkin__zipkin/results/applications_static_analysis/openzipkin__zipkin/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑；按约束未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/openzipkin__zipkin` 源码快照，提交 `4eb42f0`。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境确认默认 Armeria HTTP/gRPC 消息大小边界和 collector parser-state 资源曲线。
- 破坏性变更：无；未修改 Zipkin 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-28] ThingsBoard 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-28 23:50

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `thingsboard/thingsboard` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；将 WebSocket pending session、WebSocket outbound queue、HTTP transport long-poll session、默认 Caffeine cache、上传/安装/管理类路径按有效边界或范围约束拒绝。
- 保留 2 个 payload size 过滤器与 chunked/no-`Content-Length` 请求相关的 JSON parser-state 候选为 `needs_dynamic_probe`，未升级为 confirmed/likely，因为默认容器运行态 body-size 行为尚未动态确认。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/thingsboard__thingsboard/results/applications_static_analysis/thingsboard__thingsboard/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：已校验 `target_profile.json` 与全部 JSONL 文件可解析；本轮未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑；按约束未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/thingsboard__thingsboard` 源码和人工静态代码复核。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境确认默认 Servlet 容器对 no-`Content-Length` 大请求的实际拦截边界。
- 破坏性变更：无；不修改目标源码、查询、runner 或既有权威结果。

---

## [2026-06-28] SkyWalking 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-28 23:47

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `apache/skywalking` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP/gRPC 入口和非磁盘资源；将 admin-server、文件模式 profiling、Zipkin body parsing 和泛化 gRPC executor 噪声按范围或证据不足降级/拒绝。
- 保留 1 个 PromQL regex CPU 候选为 `likely`，2 个 profiling gRPC per-stream heap retention 候选为 `needs_dynamic_probe`。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/apache__skywalking/results/applications_static_analysis/apache__skywalking/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：已执行 JSON/JSONL 格式校验与必需文件存在性检查；本轮仅写静态分析结果，未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/apache__skywalking` 源码和人工静态代码复核；未使用 CodeQL 数据库。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 PromQL regex CPU、pprof 和 async-profiler per-stream heap retention。
- 破坏性变更：无；不修改 SkyWalking 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-29] DataEase 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-29 00:20

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 按 `$java-web-dos-hunter` 流程对 `dataease/dataease` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；复核匿名白名单、TokenFilter、缓存、导出线程池、GeoJSON 解析、Datasource Provider 静态连接状态和延迟队列。
- 未发现满足默认外部非管理员门槛的 confirmed/likely 漏洞；保留导出队列和 GeoJSON parser 两个 authenticated `needs_dynamic_probe` 候选，并将固定 cache key、request-local crypto、server-controlled cache、配置依赖连接状态等模式拒绝。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/dataease__dataease/results/applications_static_analysis/dataease__dataease/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑；按约束未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/dataease__dataease` 源码快照，提交 `4eb42f06501bc480692221b9b233a6c69bee3e20`。
- 对后续工作的影响：后续如扩展到 authenticated 动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量导出队列和 GeoJSON parser 的资源曲线。
- 破坏性变更：无；未修改 DataEase 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-28] Keycloak 应用级 Java Web DoS 静态猎取

### 修改时间
2026-06-28 23:41

### 变更类型
- [文档] 应用级静态分析结果归档

### 核心改动
- 使用 `$java-web-dos-hunter` 方法论对 `keycloak/keycloak` 本地源码执行静态-only Java Web 资源耗尽 DoS 复核。
- 聚焦默认生产配置、外部非管理员 HTTP 入口和非磁盘资源；将 SCIM、AuthZen、SSF、admin import 和 action-token 噪声按默认部署门槛或有效边界降级/拒绝。
- 保留 1 个 OIDC root authentication session cache cardinality 候选为 `needs_dynamic_probe`，未升级为 confirmed/likely，因为默认运行态 cache 增长、TTL 清理和内存斜率尚未动态测量。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/keycloak__keycloak/results/applications_static_analysis/keycloak__keycloak/`
- 新增必需产物：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：本轮仅写静态分析结果，未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑；按约束未运行动态 exploit/fuzz/load/OOM/network 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/keycloak__keycloak` 源码和人工静态代码复核。
- 对后续工作的影响：后续如进入动态阶段，可按 `dynamic_probe_plan.jsonl` 在隔离环境测量 OIDC auth-session root entry 增长与清理边界。
- 破坏性变更：无；不修改目标源码、查询、runner 或既有权威结果。

---

## [2026-06-28] Jenkins 应用级静态 DoS Hunter 结果

### 修改时间
2026-06-28 23:55

### 变更类型
- [文档] 应用级静态分析结果

### 核心改动
- 按 `java-web-dos-hunter` 静态流程复核 `jenkinsci/jenkins` 的 Stapler/Servlet HTTP 入口、Remote API、Queue、搜索、CSP report 和管理面路径。
- 在默认生产、外部非管理员、非磁盘资源范围内保守判定：未提升 confirmed/likely；保留 Remote API XML request-burst 内存/CPU 与参数化构建 Queue retention 两个 `needs_dynamic_probe` 候选。
- 将搜索建议、CSP report、AvatarContributor、管理配置/XML、文件参数和 setup wizard 等高噪声路径按 bounded、missing path、admin、disk out of scope 或 test/dev only 拒绝。

### 交付成果
- 新增 hunter 结果目录：`frameworks/applications/jenkinsci__jenkins/results/applications_static_analysis/jenkinsci__jenkins/`
- 新增必需文件：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：已执行 JSON/JSONL 格式校验与必需文件存在性检查；本轮仅新增静态 hunter 结果，未运行动态、网络、负载、OOM 或 CodeQL pipeline 验证。

### 依赖与影响
- 依赖：本地 Jenkins 源码 `frameworks/applications/jenkinsci__jenkins`，静态人工代码审查；未使用 CodeQL 数据库。
- 对后续工作的影响：后续如需提升候选，应在隔离本地 Jenkins harness 中按 `dynamic_probe_plan.jsonl` 执行低风险度量，不能直接对生产服务测试。
- 破坏性变更：无；不修改 Jenkins 目标源码、CodeQL 查询、runner、ranking 或 verdict 语义。

---

## [2026-06-28] Conductor 应用级 Java Web DoS 静态猎查

### 修改时间
2026-06-28 23:50

### 变更类型
- [文档] 应用级静态分析结果

### 核心改动
- 按 `$java-web-dos-hunter` 流程对 `conductor-oss/conductor` 执行默认生产配置、外部非管理员 HTTP 入口范围内的静态资源耗尽 DoS 复核。
- 识别默认 `/api/workflow` 动态 fork 输入膨胀为 `likely` 候选，并将 JSON/JQ transform CPU/结果列表放大记录为 `needs_dynamic_probe`。
- 明确拒绝 isolated system task 线程池膨胀、Workflow Message Queue、`/api/admin/*`、文件存储和 bulk list 噪声路径，原因分别落到 disabled-by-default、management-only、disk-out-of-scope 或 bounded。

### 交付成果
- 新增 hunter 输出目录：`frameworks/applications/conductor-oss__conductor/results/applications_static_analysis/conductor-oss__conductor/`
- 新增必需文件：`summary.md`、`target_profile.json`、`sinks.jsonl`、`sources.jsonl`、`flows.jsonl`、`findings.jsonl`、`rejected.jsonl`、`dynamic_probe_plan.jsonl`、`subagent_reviews.jsonl`、`gaps.md`
- 测试/验证结果：执行 JSON/JSONL 结构校验；本轮未修改 CodeQL、ranking、verdict 或 pipeline 逻辑，未运行动态、网络、负载或 OOM 测试。

### 依赖与影响
- 依赖：本地 `frameworks/applications/conductor-oss__conductor` 源码快照，提交短哈希 `4eb42f0`。
- 对后续工作的影响：可对 `CONDUCTOR-APP-STATIC-0001` 优先做隔离动态验证，确认默认请求体/堆限制下的真实服务影响；`CONDUCTOR-APP-STATIC-0002` 需要先补具体 jq 表达式和 payload 限制证据。
- 破坏性变更：无；未修改目标源码、查询、runner 或既有权威结果。

---

## [2026-06-28] 用户指定 34 个 Java Web 应用 CodeQL build-mode 数据库批量构建

### 修改时间
2026-06-28 22:21

### 变更类型
- [新增功能] 应用级目标批量构建产物
- [文档] 构建状态报告

### 核心改动
- 为用户指定的 34 个 Java Web 应用建立独立目标 manifest，并基于 `scripts/build_application_databases.py` 执行 build-mode CodeQL 数据库构建。
- 使用中国境内 Maven/Gradle 镜像、JDK 22/21/17 自动重试和已有本地源码目录推进构建；以 `db-java` 与 `src.zip` 同时存在作为完整数据库判定标准。
- 当前形成 11 个完整 build-mode 数据库，23 个目标保留为待定制构建；失败原因集中在项目专用构建 profile、前端 Node/npm 下载、Maven wrapper 缺失、JDK 版本要求、超时和部分依赖解析问题。

### 交付成果
- 新增目标 manifest：`results/application_dbs/requested_20260628/requested_targets_manifest.json`
- 新增重试 manifest：`results/application_dbs/requested_20260628/requested_targets_retry_manifest.json`
- 更新构建状态：`results/application_dbs/requested_20260628/application_db_build_status.jsonl`
- 更新构建摘要：`results/application_dbs/requested_20260628/application_db_build_summary.md`
- 新增构建报告：`results/application_dbs/requested_20260628/REQUESTED_BUILD_FINAL_REPORT.md`
- 完整数据库目录：`databases/applications/` 下 11 个 `<target_id>-db`
- 测试/验证结果：已执行严格完整性检查，确认 11 个数据库同时具备 `db-java` 与 `src.zip`；本轮未修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：本地 `frameworks/applications/` 源码目录、CodeQL CLI 2.23.8、JDK 22/21/17、Maven/Gradle 依赖缓存和外部依赖下载网络。
- 对后续工作的影响：后续可直接对 11 个完整数据库运行应用级静态查询；剩余 23 个目标需要按项目定制定制构建命令或拆分模块继续补齐。
- 破坏性变更：无；不修改查询、runner、verdict 语义或既有权威结果。

---

## [2026-06-28] XXL-Boot 漏洞申报稿合并为中文 GitHub Issue 格式

### 修改时间
2026-06-28 16:11

### 变更类型
- [文档] 漏洞申报材料调整

### 核心改动
- 将 `XXL-BOOT-APP-STATIC-0001` 与 `XXL-BOOT-APP-STATIC-0003` 合并到同一份中文 GitHub issue 提交稿中，覆盖匿名 `/login` / `/register` JSON 请求体复制和匿名登录失败异步日志队列两个子问题。
- 去除 issue 正文中的附件位置引用，改为内联描述源码证据、动态验证摘要、服务端 OOM 日志信号、影响和修复建议。
- 将 `XXL-BOOT-APP-STATIC-0003` 原目录的提交指南和漏洞报告改为指向 `XXL-BOOT-APP-STATIC-0001` 合并稿，避免重复分开发送。

### 交付成果
- 更新合并稿：`poc/high_probability_disclosures_2026-06-28/XXL-BOOT-APP-STATIC-0001__xxl-boot-repeatablefilter-login-body-oom/VULNERABILITY_REPORT.md`
- 更新提交指南：`poc/high_probability_disclosures_2026-06-28/XXL-BOOT-APP-STATIC-0001__xxl-boot-repeatablefilter-login-body-oom/SUBMISSION_GUIDE.md`
- 更新 0003 指向说明：`poc/high_probability_disclosures_2026-06-28/XXL-BOOT-APP-STATIC-0003__xxl-boot-login-failure-async-queue-oom/VULNERABILITY_REPORT.md`、`SUBMISSION_GUIDE.md`
- 更新申报包索引：`poc/high_probability_disclosures_2026-06-28/README.md`
- 测试/验证结果：`python3 scripts/check_phase3_consistency.py` 通过，Phase 3 consistency 37/37；`python3 scripts/check_web_real_regression.py` 通过，WEB-REAL 回归 6/6 phase3 hit，6 个 dynamic-only pending query 保持既有状态；`git diff --check` 通过。

### 依赖与影响
- 依赖：已有 XXL-Boot P1 动态验证真阳性和静态 finding 证据。
- 对后续工作的影响：XXL-Boot 两个匿名登录面 DoS 子问题建议以一个 GitHub issue 提交，必要时再按维护者要求补私密日志。
- 破坏性变更：无；不修改 CodeQL 查询、runner 或 verdict 语义。

---

## [2026-06-28] Erupt 漏洞申报稿合并为中文 GitHub Issue 格式

### 修改时间
2026-06-28 11:00

### 变更类型
- [文档] 漏洞申报材料调整

### 核心改动
- 将 `ERUPT-APP-STATIC-0001` 与 `ERUPT-APP-STATIC-0002` 合并到同一份中文 GitHub issue 提交稿中，覆盖匿名验证码 `height` 参数大图分配和 `/erupt-api/*` JSON 请求体 pre-auth 复制两个子问题。
- 去除 issue 正文中的附件位置引用，改为内联描述源码证据、动态验证摘要、影响和修复建议。
- 将 `ERUPT-APP-STATIC-0002` 原目录的提交指南和漏洞报告改为指向 `ERUPT-APP-STATIC-0001` 合并稿，避免重复分开发送。

### 交付成果
- 更新合并稿：`poc/high_probability_disclosures_2026-06-28/ERUPT-APP-STATIC-0001__erupt-captcha-height-bufferedimage-oom/VULNERABILITY_REPORT.md`
- 更新提交指南：`poc/high_probability_disclosures_2026-06-28/ERUPT-APP-STATIC-0001__erupt-captcha-height-bufferedimage-oom/SUBMISSION_GUIDE.md`
- 更新 0002 指向说明：`poc/high_probability_disclosures_2026-06-28/ERUPT-APP-STATIC-0002__erupt-operation-log-json-body-copy-oom/VULNERABILITY_REPORT.md`、`SUBMISSION_GUIDE.md`
- 更新申报包索引：`poc/high_probability_disclosures_2026-06-28/README.md`
- 测试/验证结果：`python3 scripts/check_phase3_consistency.py` 通过，Phase 3 consistency 37/37；`python3 scripts/check_web_real_regression.py` 通过，WEB-REAL 回归 6/6 phase3 hit，6 个 dynamic-only pending query 保持既有状态；`git diff --check` 通过。

### 依赖与影响
- 依赖：已有 Erupt P1 动态验证真阳性和静态 finding 证据。
- 对后续工作的影响：Erupt 两个匿名 DoS 子问题建议以一个 GitHub issue 提交，必要时再按维护者要求补私密日志。
- 破坏性变更：无；不修改 CodeQL 查询、runner 或 verdict 语义。

---

## [2026-06-28] 高概率应用 DoS 漏洞申报包整理

### 修改时间
2026-06-28 01:36

### 变更类型
- [文档] 漏洞申报材料与附件归档

### 核心改动
- 基于 `results/applications_dynamic_validation/` 中真实触发 OOM、且前置条件较低的应用级真阳性，筛选 16 个高概率被上游认可的申报对象。
- 在 `poc/high_probability_disclosures_2026-06-28/` 下为每个漏洞建立独立目录，按 GitHub 私密漏洞报告、项目 `SECURITY.md`、项目公开邮箱和 CNVD/CVE 后续协调路径写明申报顺序。
- 每个漏洞目录包含中文 `SUBMISSION_GUIDE.md`、英文 `VULNERABILITY_REPORT.md` 和 `attachments/`，附件内归档动态验证 JSON、静态 finding JSON、压缩原始动态日志与校验索引。

### 交付成果
- 新增申报包索引：`poc/high_probability_disclosures_2026-06-28/README.md`
- 新增 16 个漏洞申报目录：覆盖 PowerJob、smqtt、JMQTT、Erupt、Rebuild、OPSLI、WGCloud 和 XXL-Boot 的高概率默认/匿名/默认 token DoS 真阳性。
- 新增附件：每个目录下的 `attachments/dynamic_finding.json`、`static_finding.json`、`*.log.gz` 和 `ATTACHMENTS.md`
- 更新文档：`CHANGELOG.md`
- 测试/验证结果：`python3 scripts/check_phase3_consistency.py` 通过，Phase 3 consistency 37/37；`python3 scripts/check_web_real_regression.py` 通过，WEB-REAL 回归 6/6 phase3 hit，6 个 dynamic-only pending query 保持既有状态；`git diff --check` 通过。

### 依赖与影响
- 依赖：已有 P0/P1 动态验证真阳性结果、本地静态 finding、目标仓库 `SECURITY.md` / README 中的安全联系信息。
- 对后续工作的影响：可直接按目录逐项向上游提交私密报告；同一项目多漏洞可按维护者反馈合并为一个 advisory 或拆分为多个 CVE/GHSA。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、动态验证 runner 或 verdict 语义。

---

## [2026-06-27] 应用级 P2 动态验证执行

### 修改时间
2026-06-27 22:54

### 变更类型
- [新增功能] 应用级 P2 动态验证 runner
- [文档] P2 动态验证结果归档与口径同步

### 核心改动
- 新增 `scripts/run_application_p2_dynamic_validation.py`，以 `p2_dynamic_validation_triage.md` 为输入，按 P2 triage 维护 34 条候选的动态验证状态，并支持 `--case`、`--recommended-only`、`--runnable-only` 单项或子队列重跑。
- 为 `SBA-APP-STATIC-0002` 实现默认 insecure Spring Boot Admin sample 探针：外部注册唯一 `/instances`，指向攻击者控制 health endpoint，由默认 status updater 接收 `Set-Cookie` 响应并写入 per-instance JDK CookieStore。
- 保持严格真阳性门槛：只有真实外部 HTTP/协议请求触发目标 JVM `OutOfMemoryError`、GC death、线程/连接池耗尽或持续服务不可用才提升；未补齐默认服务环境、业务数据、登录态或依赖栈的候选保持 `precondition_blocked`，P2 triage 未选入主队列的候选保持 `triage_not_selected`。

### 交付成果
- 新增脚本：`scripts/run_application_p2_dynamic_validation.py`
- 更新动态验证结果：`results/applications_dynamic_validation/p2/summary.json`、`summary.csv`、`findings.jsonl`
- 新增人工报告：`results/applications_dynamic_validation/p2/P2_DYNAMIC_VALIDATION_REPORT.md`
- 新增原始日志：`results/applications_dynamic_validation/p2/logs/SBA-APP-STATIC-0002.log`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：`python3 -m py_compile scripts/run_application_p2_dynamic_validation.py` 通过；`python3 scripts/run_application_p2_dynamic_validation.py` 生成完整 P2 结果；`python3 scripts/run_application_p2_dynamic_validation.py --case SBA-APP-STATIC-0002` 确认 `SBA-APP-STATIC-0002` 为 `verified_oom`。当前 P2 为 1 个 `verified_oom`、7 个 `precondition_blocked`、26 个 `triage_not_selected`、0 个 `probe_error`。

### 依赖与影响
- 依赖：本地 Spring Boot Admin 源码和已构建 classpath、本地 Maven 依赖缓存、可绑定本地端口的宿主环境。
- 对后续工作的影响：P2 首个默认 HTTP 触发 OOM 已归档；后续可继续补 Astron、JetLinks、Mall、Kafka WebView 和 Rill Flow 的默认依赖栈、登录态与业务数据初始化。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、Phase 3/4 pipeline 或 verdict 语义。

---

## [2026-06-27] 应用级 P1 A 组前置条件补环境重测

### 修改时间
2026-06-27 21:44

### 变更类型
- [功能改进] 应用级 P1 动态验证 runner
- [Bug 修复] 默认服务依赖与协议 harness
- [文档] P1 动态验证结果口径同步

### 核心改动
- 对 P1 `precondition_blocked` 中 10 个 A 组候选补齐默认环境或协议 harness：Nacos ConfigService gRPC listener、CAT 官方 Docker Web+MySQL、DIYHI BBS MySQL、JPom 首次安装态、UJCMS MySQL、litemall 多模块 MySQL、ShoppingCart WAR/Tomcat、OPSLI MySQL+Redis。
- 修复补测中的依赖和运行时问题：Litemall/OPSLI 使用 Maven classpath 优先，补 OPSLI MySQL driver 和 Java 22 启动顺序，修复 ShoppingCart Tomcat harness Java 版本，CAT 改为 runtime 可读 SQL 初始化目录、本地已有镜像优先和并发 projectUpdate burst。
- 继续保持真阳门槛：只有外部协议或 HTTP 请求触发目标 JVM `OutOfMemoryError` 才标为 `verified_oom`，启动期失败、环境缺口和未 OOM 的执行完成均不提升。

### 交付成果
- 修改脚本：`scripts/run_application_p1_dynamic_validation.py`
- 更新动态验证结果：`results/applications_dynamic_validation/p1/summary.json`、`summary.csv`、`findings.jsonl`
- 更新人工报告：`results/applications_dynamic_validation/p1/P1_DYNAMIC_VALIDATION_REPORT.md`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：A 组 10 个候选均完成补测；`OPSLI-BOOT-APP-STATIC-0001` 为 `verified_oom`，其余 9 个为 `completed_without_oom`。当前 P1 为 17 个 `verified_oom`、18 个 `completed_without_oom`、0 个 `probe_error`、54 个 `precondition_blocked`。

### 依赖与影响
- 依赖：本地应用源码、已有 Maven 依赖缓存、Docker MySQL/Redis/CAT 镜像、可绑定本地端口的宿主环境。
- 对后续工作的影响：P1 第一优先级队列已压缩到 11 个 `precondition_blocked`；后续可继续补 Cryostat、CAT config、JPom cluster、itranswarp、SPMS 和 Rill Flow 等仍缺默认服务/业务态/protocol harness 的候选。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、Phase 3/4 pipeline 或 verdict 语义。

---

## [2026-06-27] 应用级 P2 动态验证准入复核

### 修改时间
2026-06-27 15:53

### 变更类型
- [文档] 应用级 P2 候选动态验证 triage

### 核心改动
- 基于 `_static_validation` 的 P2 队列，复核 34 条候选的默认可达性、部署条件、权限前置和资源类型边界。
- 将 P2 候选拆分为 8 条建议进入动态验证、10 条低成本观测/代表性 Redis TTL 子实验、16 条暂不进入动态验证，避免短 TTL 小值 Redis、纯磁盘/DB 持久化、admin-only 或非默认 handler 路径占用 OOM 动态验证资源。
- 明确下一轮 P2 动态验证仍需区分 `precondition_blocked`、`completed_without_oom`、`verified_oom` 和服务不可用证据，不把静态可疑点或单纯增长曲线提升为 confirmed。

### 交付成果
- 新增文档：`results/applications_static_analysis/_static_validation/p2_dynamic_validation_triage.md`
- 输入依据：`results/applications_static_analysis/_static_validation/all_candidates_dynamic_validation.md`、`all_candidates.csv` 和各应用 `findings.*`
- 测试/验证结果：`python3 scripts/check_phase3_consistency.py` 通过，Phase 3 consistency 37/37；`python3 scripts/check_web_real_regression.py` 通过，WEB-REAL 回归 6/6 phase3 hit，6 个 dynamic-only pending query 保持既有状态。

### 依赖与影响
- 依赖：已有应用级静态汇总、P0/P1 动态验证结果和本地应用源码快照。
- 对后续工作的影响：为 P2 runner 或手工动态验证提供优先队列，首批建议覆盖 SBA CookieStore、Astron embedding 线程、JetLinks thumbnail/WebSocket、Mall RabbitMQ、Kafka WebView WebSocket/JSON body 和 Rill Flow Redis runtime state。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、Phase 3/4 pipeline 或 verdict 语义。

---

## [2026-06-27] 应用级 P1 probe_error 修复与补测

### 修改时间
2026-06-27 12:44

### 变更类型
- [Bug 修复] 应用级 P1 动态验证 runner
- [文档] P1 动态验证结果口径同步

### 核心改动
- 修复 `NACOS-APP-STATIC-0001` 的动态探针启动问题：补齐 Nacos classpath fallback、Prometheus 运行时依赖、JDK legacy opens、standalone/auth-disabled 启动参数和端口级 readiness，避免因依赖缺失或健康检查端点差异落入 `probe_error`。
- 修复 `REBUILD-APP-STATIC-0001..0004` 的动态探针环境问题：为 Rebuild classpath 增加 CodeQL `javac.args` fallback，启动时写入默认安装态 `.rebuild` 配置，并以应用日志中的 installed ready state 作为 readiness 条件。
- 对 5 个原 `probe_error` 候选执行动态补测，继续只把目标 JVM 真实 `OutOfMemoryError` 作为真阳性；Nacos instance registration、Rebuild session/captcha 两类探针执行完成但未确认 OOM，Rebuild barcode 和 pre-auth JSON body 两类探针确认 OOM。

### 交付成果
- 修改脚本：`scripts/run_application_p1_dynamic_validation.py`
- 更新动态验证结果：`results/applications_dynamic_validation/p1/summary.json`、`summary.csv`、`findings.jsonl`
- 更新人工报告：`results/applications_dynamic_validation/p1/P1_DYNAMIC_VALIDATION_REPORT.md`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：`python3 -m py_compile scripts/run_application_p1_dynamic_validation.py` 通过；5 个原 `probe_error` 均已补测完成，当前 P1 为 16 个 `verified_oom`、9 个 `completed_without_oom`、0 个 `probe_error`、64 个 `precondition_blocked`。

### 依赖与影响
- 依赖：已有 P1 动态验证准备清单、本地 Nacos/Rebuild 源码与 CodeQL DB 构建日志、本地 Maven 依赖缓存、Docker MySQL 镜像和可绑定本地端口的宿主环境。
- 对后续工作的影响：P1 第一优先级队列已无探针错误，后续可转向剩余 `precondition_blocked` 的默认部署初始化、低权限账号、业务数据或协议 harness 补齐。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、Phase 3/4 pipeline 或 verdict 语义。

---

## [2026-06-27] 应用级 P1 第一优先级补测

### 修改时间
2026-06-27 00:24

### 变更类型
- [功能改进] 应用级 P1 动态验证 runner
- [文档] P1 第一优先级补测结果归档
- [文档] README/AGENTS 结果口径同步

### 核心改动
- 扩展 `scripts/run_application_p1_dynamic_validation.py` 的 P1 探针覆盖，补测第一优先级 38 个候选，并新增 `--first-priority` 选择器以便只重跑该子集。
- 补齐 JMQTT、Spring Boot Admin、Erupt、WGCloud、Socket-MQTT 和 XXL-Boot 等候选的默认环境或协议 harness；继续只把真实外部协议/HTTP 请求触发目标 JVM `OutOfMemoryError` 作为真阳性。
- 拆分报告统计口径，把 `completed_without_oom`、`probe_error` 和 `precondition_blocked` 分开呈现，避免把探针依赖失败混入已执行未确认项。

### 交付成果
- 修改脚本：`scripts/run_application_p1_dynamic_validation.py`
- 更新动态验证结果：`results/applications_dynamic_validation/p1/summary.json`、`summary.csv`、`findings.jsonl`
- 更新人工报告：`results/applications_dynamic_validation/p1/P1_DYNAMIC_VALIDATION_REPORT.md`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：P1 当前 89 个候选中 14 个 `verified_oom` 真阳性、6 个 `completed_without_oom`、5 个 `probe_error`、64 个 `precondition_blocked`；第一优先级 38 个候选中 7 个真实 OOM、5 个已执行未确认 OOM、5 个探针错误、21 个前置条件阻塞。

### 依赖与影响
- 依赖：已有 P1 动态验证准备清单、本地应用源码/构建产物、Docker、MySQL 镜像、Maven 依赖缓存和可绑定本地端口的宿主环境。
- 对后续工作的影响：后续可优先处理 `probe_error` 的 Nacos/Rebuild 依赖解析问题，以及仍处于 `precondition_blocked` 的生产默认部署可达性、初始化数据、低权限账号或 agent/compose 前置条件缺口。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、Phase 3/4 pipeline 或 verdict 语义。

---

## [2026-06-26] 应用级 P1 动态 OOM 验证

### 修改时间
2026-06-26 21:57

### 变更类型
- [新增功能] 应用级 P1 动态验证 runner
- [文档] P1 动态验证结果归档
- [文档] 运行指南同步

### 核心改动
- 新增 `scripts/run_application_p1_dynamic_validation.py`，基于 `results/applications_static_analysis/_static_validation/all_candidates_dynamic_validation.md` 的 P1 队列执行应用级动态验证，并继续以真实外部协议或 HTTP 请求触发目标 JVM `OutOfMemoryError` 作为真阳性门槛。
- 覆盖 89 个 P1 候选：对已脚本化的 PowerJob、SMQTT、XXL-JOB、RuoYi-Vue-Fast 和 Citrus 候选运行完整依赖环境或协议 harness，其余候选记录为 `precondition_blocked`，不当作阴性。
- 修正 SMQTT P1 探针的收尾和隔离：MQTT 客户端异常统一进入 `finish_probe`，不同 SMQTT case 使用独立端口，并提升 empty-topic key 负载以稳定触发目标 JVM OOM。
- 修正 PowerJob remote HTTP 探测：从日志发现实际 remote bind host，避免把非 localhost 绑定误判为服务未启动；该候选在 22,914 次 heartbeat 后仍未触发 OOM，保留 `completed_without_oom`。

### 交付成果
- 新增脚本：`scripts/run_application_p1_dynamic_validation.py`
- 新增动态验证结果目录：`results/applications_dynamic_validation/p1/`
- 新增机器可读结果：`results/applications_dynamic_validation/p1/summary.json`、`summary.csv`、`findings.jsonl`
- 新增人工报告：`results/applications_dynamic_validation/p1/P1_DYNAMIC_VALIDATION_REPORT.md`
- 新增原始日志：`results/applications_dynamic_validation/p1/logs/`
- 修改文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：`python3 -m py_compile scripts/run_application_p1_dynamic_validation.py` 通过；P1 动态验证完成，89 个候选中 7 个 `verified_oom` 真阳性、1 个 `completed_without_oom` 未确认、81 个 `precondition_blocked`。

### 依赖与影响
- 依赖：已有 P1 动态验证准备清单、`frameworks/applications/*` 对应目标源码、本地 Maven 依赖缓存、Docker、MySQL/Redis 镜像和可绑定本地端口的宿主环境。
- 对后续工作的影响：P1 结果为下一轮补齐 Nacos、Spring Boot Admin、Cryostat、JMQTT、CAT 等未脚本化默认环境提供了明确阻塞清单；当前真阳性只来自已由外部协议/HTTP 请求触发目标 JVM OOM 的 case。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、Phase 3/4 pipeline 或 verdict 语义。

---

## [2026-06-26] 应用级 P0 动态 OOM 验证

### 修改时间
2026-06-26 19:58

### 变更类型
- [新增功能] 应用级 P0 动态验证 runner
- [文档] P0 动态验证结果归档
- [文档] 运行指南同步

### 核心改动
- 新增 `scripts/run_application_p0_dynamic_validation.py`，基于 `results/applications_static_analysis/_static_validation/all_candidates_dynamic_validation.md` 的 P0 队列执行应用级动态验证，并用真实外部协议或 HTTP 请求触发目标 JVM OOM 作为真阳性门槛。
- 覆盖 15 个 P0 候选：对 quickmsg/smqtt、xuxueli/xxl-job、powerjob、dromara/datacompare、yangzongzhuan/ruoyi-vue-fast、yiuman/citrus、1024-lab/smart-admin、xnx3/wangmarket 和 tianshiyeben/wgcloud 执行外部协议或 HTTP 动态验证。
- 使用 Docker 启动 MySQL/Redis 等完整依赖环境，优先使用国内镜像前缀；Citrus 为进入目标 `/rest/verify/captcha` 路径额外使用运行时 properties、MDA classpath patch 和与目标无关的 MDA 自动配置排除，未修改应用源码。
- 对 SmartAdmin、WGCloud、WangMarket 保留 `completed_without_oom`，对需要 Java agent 注入默认形态的 EaseAgent 两项保留 `blocked_environment`，不把静态可疑点、启动失败、增长曲线或非目标阶段错误提升为 confirmed。
- 支持 `--case` 单候选补跑，并在补跑时合并保留已有 `summary.json` 结果，避免覆盖其他候选证据。

### 交付成果
- 新增脚本：`scripts/run_application_p0_dynamic_validation.py`
- 新增动态验证结果目录：`results/applications_dynamic_validation/p0/`
- 新增机器可读结果：`results/applications_dynamic_validation/p0/summary.json`、`summary.csv`、`findings.jsonl`
- 新增人工报告：`results/applications_dynamic_validation/p0/P0_DYNAMIC_VALIDATION_REPORT.md`
- 新增原始日志：`results/applications_dynamic_validation/p0/logs/`
- 修改文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：`python3 -m py_compile scripts/run_application_p0_dynamic_validation.py` 通过；P0 动态验证完成，15 个候选中 10 个 `verified_oom` 真阳性、3 个 `completed_without_oom` 未确认、2 个 `blocked_environment`。

### 依赖与影响
- 依赖：已有 P0 动态验证准备清单、`frameworks/applications/*` 对应目标源码、本地 Maven 依赖缓存、Docker、MySQL/Redis 镜像和可绑定本地端口的宿主环境。
- 对后续工作的影响：后续应用级动态验证可复用该 runner 的 `ProbeResult`/报告格式，继续扩展 P1 或补齐 blocked P0 的默认部署环境。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、Phase 3/4 pipeline 或 verdict 语义。

---

## [2026-06-26] 应用级静态候选默认 OOM 汇总复核

### 修改时间
2026-06-26 14:06

### 变更类型
- [新增功能] 应用级静态候选汇总脚本
- [文档] 默认外部 OOM 静态复核报告
- [文档] 运行指南同步

### 核心改动
- 新增 `scripts/summarize_application_static_findings.py`，聚合 `results/applications_static_analysis/*/findings.jsonl` 与 `findings.csv`，统一输出全量候选、应用级汇总和默认外部 OOM 动态验证优先队列。
- 对 48 个已有应用结果目录中的 216 条候选做静态复核，按默认外部可达性、非磁盘 OOM 相关资源类型、默认边界/TTL/cleanup 和动态证据缺口打上 `P0` 到 `P3` 优先级。
- 新增 `all_candidates_dynamic_validation.md`，把 216 条候选全部整理为按 `P0/P1/P2/P3` 和应用分组的动态验证准备文档，逐条保留 entry、source、sink、driver、dimension、retention、bound、impact、动态验证建议和原始证据位置。
- 将二阶段 DB-backed heap amplification、磁盘/DB-only、管理面/特殊配置/已拒绝候选与直接 session/map/cache/body/thread/queue 类路径区分开，避免把增长曲线或静态可疑点直接提升为 confirmed DoS。
- 同步更新 `README.md` 与 `AGENTS.md`，记录应用级静态汇总脚本和 `_static_validation` 输出目录。

### 交付成果
- 新增脚本：`scripts/summarize_application_static_findings.py`
- 新增静态验证报告：`results/applications_static_analysis/_static_validation/default_oom_static_validation.md`
- 新增全量候选：`results/applications_static_analysis/_static_validation/all_candidates.csv`、`all_candidates.jsonl`
- 新增动态验证准备清单：`results/applications_static_analysis/_static_validation/all_candidates_dynamic_validation.md`
- 新增应用汇总：`results/applications_static_analysis/_static_validation/application_summary.csv`
- 新增动态验证队列：`results/applications_static_analysis/_static_validation/default_oom_probe_queue.csv`
- 修改文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：`python3 -m py_compile scripts/summarize_application_static_findings.py` 通过；轻量回归见最终回复。

### 依赖与影响
- 依赖：已有 `results/applications_static_analysis/<target_id>/` 静态结果、`intel/applications/java_web_application_targets.json` manifest。
- 对后续工作的影响：后续默认部署动态验证可优先从 `default_oom_probe_queue.csv` 的 `P0`/`P1` 队列选取目标，并用报告中的分类原因决定是否先补默认可达性或边界证据。
- 破坏性变更：无；不修改 CodeQL 查询、ranking、verdict、Phase 3/4 pipeline 或动态验证语义。

---

## [2026-06-26] linlinjava/litemall 应用级静态 DoS 挖掘

### 修改时间
2026-06-26 12:25

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `linlinjava/litemall` 做只静态资源耗尽 DoS 挖掘，覆盖默认 `litemall-all` 的 `admin`/`wx` profiles、官方 Docker compose 8080 HTTP 面、Shiro 匿名登录前接口、wx 商城匿名分页接口、低权限订单延迟任务队列和默认配置开关。
- 按用户限定范围排除磁盘/DB/对象存储耗尽、需要管理权限的 `/admin/**` 业务接口、默认关闭的短信/邮件/快递/外部 provider、特殊上线配置、bounded thread pool、disabled HomeCache 和 Druid stat view。
- 静态复核结论为 0 个 `confirmed`、1 个 `likely`、2 个 `needs_dynamic_probe`：匿名 `/admin/auth/kaptcha`/失败登录可驱动 Shiro `MemorySessionDAO` 6 小时内存 session 基数增长；匿名 `/wx/*/list`/search page-size 与低权限 unpaid-order `DelayQueue` 保留为动态探针。
- 通过本地 `shiro-core-1.6.0.jar` 字节码核对确认 `DefaultSessionManager` 默认创建 `MemorySessionDAO`，且 `MemorySessionDAO` 使用 `ConcurrentHashMap` 保存 session；所有候选均未执行动态验证，不能提升为 confirmed DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/linlinjava__litemall/`
- 新增报告：`results/applications_static_analysis/linlinjava__litemall/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/linlinjava__litemall/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/linlinjava__litemall` 源码、`databases/applications/linlinjava__litemall-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `linlinjava/litemall` target 信息。
- 对后续工作的影响：后续可优先用固定小堆和隔离 Docker/MySQL 验证匿名 captcha session 基数增长、匿名大 `limit` 请求和低权限 unpaid-order queue 是否能达到 OOM、GC death、线程/连接池耗尽或持续 HTTP 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-26] codecentric/spring-boot-admin 应用级静态 DoS 挖掘

### 修改时间
2026-06-26 12:38

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `codecentric/spring-boot-admin` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Admin Server/starter setup、无内置默认认证、`POST /instances` 注册 API、in-memory event store、snapshot repository、status/info monitor、默认 instance WebClient cookie store、proxy fan-out 和 SSE event streams。
- 按用户限定范围排除磁盘/DB/日志、样例 `insecure` profile、需要 `secure` profile/管理权限的路径、`FilteringNotifier` 样例自定义、Hazelcast/Discovery 特殊配置和 Actuator 管理面操作。
- 静态复核结论为 0 个 `confirmed`、1 个 `likely`、3 个 `needs_dynamic_probe`：默认开放 `/instances` 可由唯一 `healthUrl` 驱动 eventLog/snapshot/monitor map 基数增长；registered endpoint cookie store、同名 application proxy fan-out 和 SSE/backpressure 保留为动态探针。
- 明确所有候选均未执行动态验证，不能提升为 confirmed DoS；磁盘存储不纳入问题范围。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/codecentric__spring-boot-admin/`
- 新增报告：`results/applications_static_analysis/codecentric__spring-boot-admin/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/codecentric__spring-boot-admin/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/codecentric__spring-boot-admin` 源码、`databases/applications/codecentric__spring-boot-admin-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `codecentric/spring-boot-admin` target 信息。
- 对后续工作的影响：若后续扩大到动态验证，可优先用 minimal unsecured SBA server、固定 JVM heap 和本地 mock health endpoint 验证 `/instances` 注册 retained state、per-instance cookie store、application proxy fan-out 与 SSE/backpressure 是否能造成 OOM、GC death、连接耗尽或持续 HTTP 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-26] alibaba/nacos 应用级静态 DoS 挖掘

### 修改时间
2026-06-26 12:07

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `alibaba/nacos` 做只静态资源耗尽 DoS 挖掘，覆盖默认 `8848` HTTP server、默认 `/nacos` context、SDK gRPC 默认 `9848`、`nacos.core.auth.enabled=false` 的 OpenAPI/SDK/gRPC 边界，以及 `admin/console` 默认 auth、AI registry 默认关闭、multipart/form size 默认上限等部署条件。
- 按用户限定范围排除磁盘/DB/日志/上传/配置导入导出、`/v3/admin/*`、`/v3/console/*`、AI MCP/Skill registry 特殊配置、Config/Naming fuzzy watch bounded paths、RPC ack bounded cache 和其他需要管理权限或非默认开启的路径。
- 静态复核结论为 0 个 `confirmed`、2 个 `likely`、1 个 `needs_dynamic_probe`：默认开放 Naming instance 注册可驱动 ephemeral client/service/publisher/index 进程内状态增长；默认 SDK gRPC Config batch listen 可驱动 `ConfigChangeListenContext` 双向索引增长；legacy HTTP config long polling 因 10000 listener cap、2MB form cap、timeout cleanup 和路径 wiring 缺口保留为动态探针。
- 明确所有候选均未执行动态验证，不能提升为 confirmed DoS；`likely` 仅表示默认可达性和 source-to-sink 静态证据较强。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/alibaba__nacos/`
- 新增报告：`results/applications_static_analysis/alibaba__nacos/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/alibaba__nacos/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/alibaba__nacos` 源码、`databases/applications/alibaba__nacos-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `alibaba/nacos` target 信息。
- 对后续工作的影响：若后续扩大到动态验证，可优先用默认单机 Nacos、固定 JVM heap 和隔离网络验证 `/nacos/v3/client/ns/instance` 注册状态增长、SDK gRPC `ConfigBatchListenRequest` listener 索引增长和 legacy long-poll `allSubs` 请求窗口压力是否能造成 OOM、GC death、连接/线程耗尽或持续 HTTP/gRPC 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-26] dromara/Jpom 应用级静态 DoS 挖掘

### 修改时间
2026-06-26 11:42

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `dromara/Jpom` 做只静态资源耗尽 DoS 挖掘，覆盖默认 `server`/`agent` 模块、`docker-compose.yml`、`docker-compose-local.yml`、cluster compose、匿名登录前接口、`/api/**` open API、agent authorize 边界、session/cache/map/queue/body-copy sinks。
- 按用户限定范围排除磁盘存储耗尽、上传/temp file/解压输出、需要管理权限或业务 trigger token 的构建/脚本/SSH/项目触发器、特殊 `transport-encryption=BASE64` 配置和 server-only compose 中未被 `randomIdSign()` 使用的 `jpom.authorize.token`。
- 保留 2 个 `likely` 候选：匿名 `GET /rand-code` 可创建并保留 1 小时 server servlet sessions；官方 local/cluster compose 默认 `SERVER_TOKEN` 注入 `JPOM_SERVER_TEMP_TOKEN` 时，`/api/node/receive_push` 可按攻击者控制的 `ips` 增长进程级 static `CACHE_RECEIVE_PUSH`。
- 明确降级/拒绝 agent pre-authorize JSON body copy、build trigger queue、server decryption body copy、WebSocket session maps、bounded LRU/LFU/timed caches 和磁盘/管理面路径。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/dromara__jpom/`
- 新增报告：`results/applications_static_analysis/dromara__jpom/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/dromara__jpom/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/dromara__jpom` 源码、`databases/applications/dromara__jpom-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `dromara/Jpom` target 信息。
- 对后续工作的影响：后续可优先用固定小堆和隔离 Docker 网络验证匿名 captcha session 基数增长、local/cluster 默认 token receive-push static cache 增长是否能达到 OOM、GC death 或持续 HTTP 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-26] macrozheng/mall 应用级静态 DoS 挖掘

### 修改时间
2026-06-26 11:41

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `macrozheng/mall` 做只静态资源耗尽 DoS 挖掘，覆盖官方 compose 默认发布的 `mall-admin:8080`、`mall-search:8081`、`mall-portal:8085`，以及 `mall-security` 白名单、会员 SSO、商品/首页/品牌公开分页、订单延迟取消队列、Redis cache、Elasticsearch 搜索和对象存储/支付回调降噪项。
- 按用户限定范围排除磁盘/DB/对象存储持久化耗尽、需要管理权限或管理面语义的后台控制器、`mall-demo` 非默认部署、MinIO/OSS 上传、ES index import/create/delete、Alipay 特殊支付 provider 和 request-local 参数复制。
- 静态复核结论为 0 个 `confirmed`、1 个 `likely`、4 个 `needs_dynamic_probe`：低权限 `/order/cancelOrder` 可在订单校验前投递 RabbitMQ TTL 消息；匿名 storefront 和 `mall-search` 分页缺少应用级 `pageSize` 上限；匿名 `/sso/getAuthCode` 与自助注册登录可驱动 Redis key/cardinality 增长。
- 明确将 RabbitMQ/Redis/JVM/ES 影响与磁盘持久化副作用分开标注，所有候选均未执行动态验证，不能提升为 confirmed DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/macrozheng__mall/`
- 新增报告：`results/applications_static_analysis/macrozheng__mall/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/macrozheng__mall/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/macrozheng__mall` 源码、`databases/applications/macrozheng__mall-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `macrozheng/mall` target 信息。
- 对后续工作的影响：若后续扩大到动态验证，可优先用默认 compose、固定 RabbitMQ/Redis/ES/JVM 资源验证 `/order/cancelOrder` TTL queue 堆积、匿名大 `pageSize` 请求、`/sso/getAuthCode` Redis key 增长和会员 cache key 增长是否能造成 OOM、GC death、broker/Redis/ES backpressure 或持续 HTTP 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-26] macrozheng/mall-tiny 应用级静态 DoS 挖掘

### 修改时间
2026-06-26 11:04

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `macrozheng/mall-tiny` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Docker/MySQL/Redis 部署、Spring Security 白名单、匿名注册/登录、JWT refresh、动态权限资源表、Redis admin/resource cache、Swagger/Actuator/Druid 白名单和 UMS 管理控制器。
- 按用户限定范围排除磁盘/DB 持久化存储、登录日志、需要 `/admin/**`、`/role/**`、`/menu/**`、`/resource/**` 管理权限的接口、特殊安全配置、上传/temp file 和纯文档/监控面。
- 静态复核结论为 0 个 `confirmed`、0 个 `likely`、1 个 `needs_dynamic_probe`：匿名注册加成功登录可能制造 24h Redis admin-cache key 基数，但因 Redis TTL、DB 行增长排除、自注册用户无资源权限、缓存异常传播不确定，未提升为 likely。
- 明确拒绝匿名注册 DB 行增长、自注册用户访问管理端点、成功登录日志、固定成本 BCrypt、resourceList cache、管理大分页/批量 relation list、动态权限 map 膨胀、Swagger/Actuator/Druid 和 JWT header parser 等高噪声路径。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/macrozheng__mall-tiny/`
- 新增报告：`results/applications_static_analysis/macrozheng__mall-tiny/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/macrozheng__mall-tiny/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/macrozheng__mall-tiny` 源码、`databases/applications/macrozheng__mall-tiny-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `macrozheng/mall-tiny` target 信息。
- 对后续工作的影响：若后续扩大到动态验证，可优先用一次性 MySQL/Redis、固定 Redis `maxmemory` 和固定 JVM heap 验证匿名注册/登录驱动的 Redis admin cache key 增长是否能实际造成 Redis OOM、登录失败传播或持续 HTTP 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-26] xuxueli/xxl-job 应用级静态 DoS 挖掘

### 修改时间
2026-06-26 10:59

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `xuxueli/xxl-job` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Docker compose、`xxl-job-admin` SSO/OpenAPI 边界、sample executor 默认 `9999` 暴露面、默认 `default_token`、executor `/trigger`、`JobThread`、GLUE Groovy class cache 和 Netty 聚合/业务线程池。
- 按用户限定范围排除磁盘存储耗尽、日志/callback/script 文件、DB 表增长、普通 admin UI、需要登录或管理权限的控制器、特殊安全配置和纯命令执行/RCE 语义，只判断默认配置下外部请求可导致的非磁盘资源耗尽问题。
- 保留 2 个 `likely` 候选：默认 sample executor 弱默认 token 下唯一 `jobId` 可创建进程级 `JobThread`/线程 registry；同一 jobId 唯一 `logId` 可堆积无界 `LinkedBlockingQueue<TriggerRequest>` 与 `triggerLogIdSet`。
- 保留 2 个 `needs_dynamic_probe` 候选：`GLUE_GROOVY` 唯一 `glueSource` 驱动 `GlueFactory.CLASS_CACHE`/Groovy class metadata 增长；executor Netty `HttpObjectAggregator(5MiB)` 与 content-to-String 在 pre-dispatch 阶段形成 request-burst heap/线程池压力。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/xuxueli__xxl-job/`
- 新增报告：`results/applications_static_analysis/xuxueli__xxl-job/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/xuxueli__xxl-job/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/xuxueli__xxl-job` 源码、`databases/applications/xuxueli__xxl-job-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `xuxueli/xxl-job` target 信息。
- 对后续工作的影响：后续可优先用默认 compose 或 executor-only 部署、固定 heap/Metaspace 和隔离网络验证 jobId -> JobThread 基数增长、same-job triggerQueue 积压、GLUE class cache 增长和 pre-auth body aggregation 是否能达到 OOM、GC death、线程耗尽或持续 HTTP 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-25] cryostatio/cryostat-legacy 应用级静态 DoS 挖掘

### 修改时间
2026-06-25 16:56

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `cryostatio/cryostat-legacy` 做只静态资源耗尽 DoS 挖掘，覆盖默认 `run.sh`/compose 鉴权边界、Vert.x Web/WebSocket、`/api/v1/notifications`、`/api/v2/targets`、JMX target connection manager、GraphQL 和通用 BodyHandler 请求体处理。
- 按用户限定范围排除磁盘存储耗尽、archive/report/recording/temp file、dev-only GraphiQL、compose BasicAuth 场景、需要 target/recording 权限或特殊安全配置的路径，只判断默认配置下外部 HTTP/WebSocket 请求可导致的非磁盘资源耗尽问题。
- 保留 2 个 `likely` 候选：`run.sh` 默认 NoopAuthManager 下 WebSocket accepted connections/ping timers 无实际小上限；`POST /api/v2/targets` 唯一失败 `connectUrl` 可能遗留 `TargetConnectionManager.targetLocks` key。
- 保留 1 个 `needs_dynamic_probe` 候选：多个 `BodyHandler.create(true)` 入口缺少 body limit，普通非 multipart body 可形成 request-burst heap pressure；因请求期释放和 runtime 门槛未测，未提升为 likely。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/cryostatio__cryostat-legacy/`
- 新增报告：`results/applications_static_analysis/cryostatio__cryostat-legacy/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/cryostatio__cryostat-legacy/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/cryostatio__cryostat-legacy` 源码、`databases/applications/cryostatio__cryostat-legacy-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `cryostatio/cryostat-legacy` target 信息。
- 对后续工作的影响：后续可优先在隔离 `run.sh` NoopAuthManager 部署、固定 JVM heap 和受限网络/FD 环境下验证 WebSocket accepted connection retention、失败 targetLocks 增长和非 multipart body request-burst heap pressure。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] eclipse-tahu/tahu 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 23:43

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `eclipse-tahu/tahu` 做只静态资源耗尽 DoS 挖掘，覆盖 Java reactor、Sparkplug MQTT core/edge/host libraries、edge/host compat 默认运行方式、MQTT callback、topic cache、sequence reorder、edge/device/metric maps、protobuf/DataSet/Template parser 和本地 command listener。
- 按用户限定范围排除磁盘存储、本地 `/tmp/commands` 文件路径、非 HTTP/Web MQTT broker 消息面、examples 模块和需要宿主应用集成的库路径，只判断默认配置下外部 HTTP/Web 请求可触发的非磁盘资源耗尽问题。
- 静态复核结论为 0 个 `confirmed`、0 个 `likely`、0 个 `needs_dynamic_probe`；目标默认形态是 Sparkplug/MQTT library 与 MQTT compat application，不是默认可启动 Java Web 应用。
- 记录 MQTT 范围外复核点：`TopicUtil.SPLIT_TOPIC_CACHE`、`TahuHostCallback` 无界 executor queue、`EdgeNodeManager` / `HostApplicationMetricMap` retained maps、`SequenceReorderMap` buffering 和 Sparkplug payload parser burst memory，均因非 HTTP/Web source 未进入本轮主 findings。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/eclipse-tahu__tahu/`
- 新增报告：`results/applications_static_analysis/eclipse-tahu__tahu/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/eclipse-tahu__tahu/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/eclipse-tahu__tahu` 源码、`databases/applications/eclipse-tahu__tahu-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `eclipse-tahu/tahu` target 信息。
- 对后续工作的影响：后续若扩大到 MQTT broker DoS，可优先验证 topic cache、executor queue、edge/device/metric retained maps 和 sequence reorder buffering；若继续应用级 Web 主线，应选择真实默认部署宿主应用，确认是否把 HTTP/WebSocket 请求映射到 Tahu MQTT publish/host processing。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] inspectIT/inspectit-ocelot 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 23:51

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `inspectIT/inspectit-ocelot` 做只静态资源耗尽 DoS 挖掘，覆盖主 Java Agent 默认部署边界、configuration server 默认 Spring Boot 8090 HTTP 面、Spring Security `permitAll` 列表、agent configuration/command 接口、agent status/config cache、webhook、actuator 和 Swagger/OpenAPI。
- 按用户限定范围排除磁盘存储耗尽、默认 `admin/admin` 后的管理 API、远程 Git/webhook 特殊配置、认证/管理权限路径、Kapacitor/file/search/YAML documentation 控制面和纯 metadata/static 响应。
- 静态复核结论为 0 个 `confirmed`、0 个 `likely`、2 个 `needs_dynamic_probe`：默认匿名 `/api/v1/agent/configuration` 可填充有界 configuration/status caches；默认匿名 `/api/v1/agent/command?wait-for-command=true` 可保持 30 秒长轮询请求并创建有界 queue cache entry。
- 因默认 `max-agents=10000`、`agent-eviction-delay=1h`、`agentCommandCache.maximumSize(1000)`、`command-timeout=2m`、`agent-polling-timeout=30s` 和默认 virtual threads 存在明确边界，未将上述候选提升为 likely/confirmed。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/inspectit__inspectit-ocelot/`
- 新增报告：`results/applications_static_analysis/inspectit__inspectit-ocelot/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/inspectit__inspectit-ocelot/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/inspectit__inspectit-ocelot` 源码、`databases/applications/inspectit__inspectit-ocelot-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `inspectIT/inspectit-ocelot` target 信息。
- 对后续工作的影响：后续可优先用默认 configuration server、固定堆和隔离 HTTP harness 验证 10000 个 agent attribute/status cache entry 与 30 秒匿名 long poll 是否能造成 OOM、GC death、连接/请求耗尽或持续 HTTP 不可用；若扩大到默认弱口令管理面，需单独审计 authenticated 管理 API。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] xingshuangs/iot-communication 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 23:08

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `xingshuangs/iot-communication` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Maven `jar` 目标、生产 `App.main`、README/tutorial 默认使用方式、可选 `TcpServerBasic` / `ModbusTcpServer` / `S7PLCServer`、RTSP/fMP4 client/proxy 和 SDP parser。
- 按用户限定范围排除磁盘存储耗尽、外部 Web monitor demo、宿主应用显式启动的非默认 server、特殊配置和管理面，只判断当前仓库默认配置下外部请求可触发的非磁盘资源耗尽问题。
- 静态复核结论为 0 个 `confirmed`、0 个 `likely`、0 个 `needs_dynamic_probe`；目标本身是 IoT 通信库而非默认可启动 Java Web 应用，默认 `App.main` 不启动 HTTP/TCP/UDP 服务。
- 记录可选库 API 风险边界：Modbus/S7 frame buffer 是 16-bit 协议长度驱动的 request-local parser pressure；RTSP/fMP4 queue 和 SDP attributes 需要宿主创建 outbound client/proxy，不属于当前默认部署外部面。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/xingshuangs__iot-communication/`
- 新增报告：`results/applications_static_analysis/xingshuangs__iot-communication/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/xingshuangs__iot-communication/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/xingshuangs__iot-communication` 源码、`databases/applications/xingshuangs__iot-communication-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `xingshuangs/iot-communication` target 信息。
- 对后续工作的影响：后续应优先选择真实默认部署的 Web/IoT 宿主应用，确认其是否把外部 HTTP/WebSocket 请求映射到本库的 Modbus/S7 server、RTSP/fMP4 proxy 或 parser API；不建议对当前 library 目标单独做默认部署 OOM harness。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] Cicizz/jmqtt 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 22:58

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `Cicizz/jmqtt` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Netty MQTT/TCP、MQTT over WebSocket、匿名认证、CONNECT/SUBSCRIBE/PUBLISH/QoS inflight、订阅树、协议处理器队列、连接 registry 和 retain/message DB 边界。
- 按用户限定范围排除磁盘/DB 存储耗尽、retain/message/event 表增长、WebSocket 单帧/HTTP 聚合有界路径、特殊鉴权配置和管理隔离假设，只判断默认配置下外部 MQTT 请求可触发的非磁盘资源耗尽问题。
- 保留 3 个 `likely` 候选：默认匿名 SUBSCRIBE 可增长进程级 CTrie 订阅树且 cleanSession 断开只清 DB 不清内存树；QoS2 PUBLISH 半握手可在 `qos2Receiving` 中保留 payload `byte[]`；恶意订阅端不 ACK 可使 `outboundFlowMessages` 累积待确认消息对象。
- 保留 2 个 `needs_dynamic_probe` 候选：协议处理器大有界队列和 `ConnectManager.clientCache` 在线连接 registry；二者因存在硬上限或通用连接/OS 边界未提升为 likely。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/cicizz__jmqtt/`
- 新增报告：`results/applications_static_analysis/cicizz__jmqtt/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/cicizz__jmqtt/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/cicizz__jmqtt` 源码、`databases/applications/cicizz__jmqtt-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `Cicizz/jmqtt` target 信息。
- 对后续工作的影响：后续可优先用默认 broker、固定堆和隔离 MQTT harness 验证 CTrie 订阅树清理缺口、QoS2 入站半握手 payload retention、出站 inflight ACK 拖延是否能造成 OOM、GC death 或持续 broker 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] megaease/easeagent 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 22:32

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `megaease/easeagent` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Java Agent 部署、内置 9900 HTTP server、配置/健康/Prometheus routes、NanoHTTPD fork、Servlet/Tomcat/Spring Gateway 插件和 Dropwizard/Prometheus metric registry。
- 按用户限定范围排除磁盘 temp file 存储耗尽、配置篡改安全影响、特殊网络暴露假设、需要目标应用特定业务路径证明的中间件 metric key，以及 Servlet/Tomcat 已模板化 route metric 噪声。
- 保留 2 个 `likely` 候选：默认内置 NanoHTTPD server 对每个外部连接创建无界 daemon thread；默认无鉴权配置 routes 在校验前解析无界 POST/PUT body 并复制到堆/JSON map。
- 保留 1 个 `needs_dynamic_probe` 候选：Spring Gateway metric fallback 在无 route attr 时可能用攻击者控制的完整 URI 作为进程级 metric key，但需要默认 gateway 运行链路确认 no-route 请求是否触发。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/megaease__easeagent/`
- 新增报告：`results/applications_static_analysis/megaease__easeagent/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/megaease__easeagent/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/megaease__easeagent` 源码、`databases/applications/megaease__easeagent-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `megaease/easeagent` target 信息。
- 对后续工作的影响：后续可优先用隔离 JVM 验证 9900 thread-per-connection、配置 routes 大 body heap/JSON parser 压力，以及 Spring Gateway no-route metric cardinality 是否能在默认配置、有界堆下造成 OOM、native thread exhaustion、GC death 或持续 HTTP 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] daoshenzzg/socket-mqtt 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 22:07

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `daoshenzzg/socket-mqtt` 做只静态资源耗尽 DoS 挖掘，覆盖 Netty MQTT/MQTT_WS broker 默认 README 启动面、`Server` 默认 executor、MQTT decoder、WebSocket codec、自定义协议 decoder、status 端口、连接 registry 和测试订阅 demo 边界。
- 按用户限定范围排除磁盘/DB 存储耗尽、`src/test` HSQL 订阅表、center 特殊配置、status 固定响应和需要应用显式安装的 NORMAL JSON/custom protocol 路径作为默认主发现。
- 保留 2 个 `likely` 候选：默认 MQTT/MQTT_WS PUBLISH 在 `EventDispatcher` 中 `ByteBufHolder.retain()` 后未见 release，远端消息可造成 direct/heap buffer 与队列保留增长；默认业务线程池 `LinkedBlockingQueue` 容量 1,000,000，外部消息速率可填充队列并持有 `ctx/channel/msg`。
- 保留 2 个 `needs_dynamic_probe` 候选：自定义 `ProtocolDecoder` 无 bodyLength 上限，以及 `Server.channels` 无应用级连接数上限；二者分别因需要显式安装 handler或通用连接容量边界而不提升为 likely。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/daoshenzzg__socket-mqtt/`
- 新增报告：`results/applications_static_analysis/daoshenzzg__socket-mqtt/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/daoshenzzg__socket-mqtt/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/daoshenzzg__socket-mqtt` 源码、`databases/applications/daoshenzzg__socket-mqtt-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `daoshenzzg/socket-mqtt` target 信息，以及本地 `.build-cache` 中 `netty-all-4.1.68.Final` 字节码复核。
- 对后续工作的影响：后续可优先用默认 MQTT/MQTT_WS server、固定堆和 Netty leak detector 动态验证 PUBLISH retain/no-release 与 executor queue 增长是否造成 direct memory exhaustion、OOM、GC death 或持续 broker 不可用；自定义协议和连接数候选需按隔离 harness 单独验证。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

## [2026-06-24] dromara/dataCompare 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 21:59

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `dromara/dataCompare` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot 2.5/Shiro/RuoYi 风格部署、默认账号、Shiro 匿名白名单、默认 `demoEnabled=true`、`swagger.enabled=true`、Druid/JDBC、session/cache、上传、数据对比/探测任务和 demo/test 控制器。
- 按用户限定范围排除磁盘存储耗尽、Druid 管理面、数据对比/探测管理权限路径、特殊配置和持久化 DB 行增长，只判断默认配置下外部低权限请求可触发的非磁盘资源耗尽问题。
- 保留 2 个 `likely` 候选：默认 demo `/demo/operate/add` / `importData` 与默认 Swagger test `/test/user/save` 均可由低权限登录用户向进程级 static map 写入无 TTL/容量限制对象。
- 保留 1 个 `needs_dynamic_probe` 候选：`/system/dbconfig/testConnection` 缺少 `@RequiresPermissions`，低权限用户可同步发起攻击者指定 JDBC 连接并占用 request thread/outbound connection，但可利用性依赖 JDBC/网络超时行为。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/dromara__datacompare/`
- 新增报告：`results/applications_static_analysis/dromara__datacompare/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/dromara__datacompare/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/dromara__datacompare` 源码、`databases/applications/dromara__datacompare-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `dromara/dataCompare` target 信息。
- 对后续工作的影响：后续可优先动态验证 demo/test static map 的 heap 增长和 `testConnection` 慢 JDBC 目标对 Tomcat worker 的占用是否能在默认配置、有界堆下造成 OOM、GC death、线程耗尽或持续 HTTP 不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

## [2026-06-24] 9tigerio/db2rest 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 21:42

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `9tigerio/db2rest` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot/Docker compose、默认 `ENABLE_AUTH=false`、RDBMS read/bulk/_expand/admin/sql/rpc/actuator 边界。
- 按用户限定范围排除磁盘/DB 持久化存储耗尽、需要特殊 `SQL_TEMPLATE_PATH` 或数据库 routine 的路径、特殊安全配置和纯环境定义行为，只判断默认配置下外部请求可触发的非磁盘资源耗尽问题。
- 保留 2 个 `likely` 候选：默认开放读接口接受任意正 `limit` 并将 JDBC 结果完整 materialize 为 `List<Map<String,Object>>`；默认开放 `/bulk` JSON/CSV 在应用内全量解析并构造整批 JDBC batch 参数。
- 保留 2 个 `needs_dynamic_probe` 候选：默认开放 `/_expand` join body 无数量/SQL 长度上限；默认开放 `/admin/reloadCache` 可反复触发 JDBC metadata reload。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/9tigerio__db2rest/`
- 新增报告：`results/applications_static_analysis/9tigerio__db2rest/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/9tigerio__db2rest/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/9tigerio__db2rest` 源码、`databases/applications/9tigerio__db2rest-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `9tigerio/db2rest` target 信息。
- 对后续工作的影响：后续可优先动态验证显式大 `limit` 读取真实大表和 `/bulk` 大 JSON/CSV body 在默认 auth=false、默认 Hikari pool、有界堆下是否造成 OOM、GC death、连接/worker 长期占用或持续 HTTP 不可用；`_expand` 和 `reloadCache` 需要使用本地合成 schema 验证。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

## [2026-06-24] s-pms/SPMS-Server 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 21:31

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `s-pms/SPMS-Server` 做只静态资源耗尽 DoS 挖掘，覆盖 Spring Boot 3 / AirPower 6.3.1 默认 production profile、`@Api` 路由、`@Permission` 权限语义、Redis 验证码/OAuth2 code 缓存、WebSocket、通知队列、全局 request wrapper、MCP/OpenAPI、设备匿名读接口和上传路径。
- 按用户限定范围排除磁盘/对象存储、DB/Influx 持久化存储耗尽、管理权限路径、特殊配置和非 HTTP 外部入口，只判断默认配置下外部请求可触发的非磁盘资源耗尽问题。
- 保留 1 个 `likely` 候选：匿名 `/user/sendSms` 与 `/user/sendEmail` 可用不同手机号/邮箱制造 5 分钟 TTL 的 Redis 验证码 key 高基数增长；其中短信路径当前只写 Redis 与日志，默认触发更稳定。
- 保留 1 个 `needs_dynamic_probe` 候选：登录后 `/oauth2/createCode` 在有效 `OpenApp` 下每次请求写入两个 5 分钟 TTL Redis code key，但需要登录和已有 OpenApp，不按默认匿名漏洞表述。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/s-pms__spms-server/`
- 新增报告：`results/applications_static_analysis/s-pms__spms-server/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/s-pms__spms-server/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/s-pms__spms-server` 源码、`databases/applications/s-pms__spms-server-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `s-pms/SPMS-Server` target 信息，以及本地 `.build-cache` 中 AirPower 6.3.1 依赖字节码复核。
- 对后续工作的影响：后续可优先在隔离 Redis/MySQL/SMTP 环境动态验证验证码 key cardinality 是否能在默认 compose、有界 Redis/JVM 下造成 Redis OOM、eviction、GC death 或持续 HTTP 不可用；OAuth2 code 候选需先构造普通用户和有效 OpenApp。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

## [2026-06-24] LiuYuYang01/ThriveX-Server 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 21:23

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `LiuYuYang01/ThriveX-Server` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot/MyBatis-Plus/Docker release 边界、`@NoTokenRequired` 匿名入口、JWT 拦截器、限流、RSS 聚合、评论/留言列表、异步邮件、文件管理和统计代理。
- 按用户限定范围排除磁盘/对象存储/DB 持久化存储耗尽本身、admin/JWT-gated 控制面、特殊配置和管理权限路径，只判断默认配置下外部请求可触发的非磁盘资源耗尽。
- 保留 2 个 `likely` 候选：匿名友链 `status` mass assignment 可把攻击者 RSS 直接送入已审核聚合，公开 `/api/rss` 对所有已审核 RSS 做无上限 fan-out 和完整 feed 解析；匿名评论/留言 `status` mass assignment 可进入公开已审核列表，公开列表在分页前全量加载并构树/映射。
- 保留 1 个 `needs_dynamic_probe` 候选：匿名评论、留言和友链新增会调度 `@Async` 邮件发送，项目未配置显式有界 async executor；但 SMTP 单任务超时有配置，因此需动态确认 executor 队列/线程行为。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/liuyuyang01__thrivex-server/`
- 新增报告：`results/applications_static_analysis/liuyuyang01__thrivex-server/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/liuyuyang01__thrivex-server/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/liuyuyang01__thrivex-server` 源码、`databases/applications/liuyuyang01__thrivex-server-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `LiuYuYang01/ThriveX-Server` target 信息。
- 对后续工作的影响：后续可优先动态验证 RSS fan-out/parser 压力和评论/留言公开列表 heap/CPU 曲线是否能在默认配置、有界堆下造成 OOM、GC death、线程/连接耗尽或持续 HTTP 不可用；异步邮件候选需使用受控慢 SMTP，避免对真实邮箱或第三方服务造成影响。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] shashirajraja/shopping-cart 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 20:17

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `shashirajraja/shopping-cart` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Servlet/JSP WAR、Tomcat/MySQL/Jakarta Mail 运行边界、公开 JSP/contact/register/login、默认 guest 购物/订单路径、JDBC 资源生命周期和邮件发送线程阻塞。
- 按用户限定范围排除磁盘/DB 持久化存储耗尽、admin-only 产品/库存/发货管理、产品图片 BLOB、表行增长和请求期列表/图片响应对象，只判断默认配置下外部请求可触发的非磁盘资源耗尽问题。
- 保留 2 个 `likely` 候选：匿名 JSP 默认 `session=true` 创建 server-side session 且应用未配置 session 数量上限；默认 guest/普通用户路径可在 `DBUtil` static MySQL connection 上累积未关闭 `PreparedStatement`/`ResultSet`。
- 保留 1 个 `needs_dynamic_probe` 候选：公开 contact、匿名注册和低权限下单邮件路径同步调用 `Transport.send`，且未配置 `mail.smtp.connectiontimeout` / `timeout` / `writetimeout`，可能在 SMTP 慢或不可达时耗尽 request threads。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/shashirajraja__shopping-cart/`
- 新增报告：`results/applications_static_analysis/shashirajraja__shopping-cart/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/shashirajraja__shopping-cart/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/shashirajraja__shopping-cart` 源码、`databases/applications/shashirajraja__shopping-cart-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `shashirajraja/shopping-cart` target 信息，以及本地 Maven 缓存中的 `mysql-connector-j-8.0.33` 和 `jakarta.mail-2.0.1` jar 反编译证据。
- 对后续工作的影响：后续可优先动态验证匿名 JSP session-count 增长和 Connector/J active statement count 是否能在默认 Tomcat/MySQL/有界堆下造成 OOM、GC death 或持续 HTTP 不可用；邮件线程候选需使用可控 SMTP 故障注入避免外部副作用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] SourceLabOrg/kafka-webview 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 20:11

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `SourceLabOrg/kafka-webview` 做只静态资源耗尽 DoS 挖掘，覆盖官方 Docker/release 默认配置、Spring Security 边界、普通消费 API、STOMP websocket consumer manager、Actuator、登录/重置密码和配置上传边界。
- 按用户限定范围排除磁盘存储耗尽、admin-only 配置/上传/topic 管理、禁用认证 anonymous-admin 特殊配置和仅由既有 Kafka 集群状态决定的 metadata 放大路径。
- 保留 3 个 `needs_dynamic_probe` 候选：低权限 `/api/consumer/view/{id}` 按 topic partition 向全局 fixed pool 提交任务且未见 queue cap；`/websocket/consume/{viewId}` 在 executor 提交前写入 `consumers` map 的饱和异常路径；普通 JSON consume/offset API 在业务校验前构造 unbounded request object graph。
- 明确记录默认首次启动无 cluster/view，`KWV-APP-STATIC-0001/0002` 属于默认配置、正常使用态、有低权限账号和已有 Kafka view 的候选，不能表述为全新空实例匿名触发。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/sourcelaborg__kafka-webview/`
- 新增报告：`results/applications_static_analysis/sourcelaborg__kafka-webview/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/sourcelaborg__kafka-webview/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/sourcelaborg__kafka-webview` 源码、`databases/applications/sourcelaborg__kafka-webview-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `SourceLabOrg/kafka-webview` target 信息。
- 对后续工作的影响：后续可优先动态验证 `/api/consumer/view/{id}` 的 fixed pool queue 增长和 websocket consumers map 饱和异常路径，再测大 JSON request-burst 的 heap/GC 门槛。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] weibocom/rill-flow 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 17:46

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `weibocom/rill-flow` 做只静态资源耗尽 DoS 挖掘，覆盖官方 Docker compose、UI nginx `/flow/` 反代、默认 `AuthUserResolver` 边界、submit/trigger/convert/dependency_check、触发器、runtime Redis、Aviator cache、Prometheus meter 和默认 executor 队列。
- 按用户限定范围排除磁盘存储耗尽、后台/管理权限入口、生产默认不会开启或需要特殊基础设施的路径，只判断默认配置下外部 HTTP 请求可触发的非磁盘资源耗尽问题。
- 保留 3 个 `needs_dynamic_probe` 候选：默认无有效鉴权的 `/flow/submit.json` 在存在可提交 descriptor 时驱动 runtime Redis execution/context 增长；匿名 `/flow/trigger.json` 在任务存在性检查和 6144 字节 context 限制前解析 context；`/flow/convert.json` 与 `/flow/dependency_check.json` raw DAG YAML/JSON parser request-burst 压力。
- 明确拒绝 cron/kafka trigger 管理态 map/consumer、后台 descriptor/template/customized storage、Aviator bounded cache、bounded executor queues、Prometheus meter cardinality 和既有状态列表放大等高噪声或范围外路径。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/weibocom__rill-flow/`
- 新增报告：`results/applications_static_analysis/weibocom__rill-flow/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/weibocom__rill-flow/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/weibocom__rill-flow` 源码、`databases/applications/weibocom__rill-flow-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `weibocom/rill-flow` target 信息。
- 对后续工作的影响：后续可优先动态验证 submit runtime Redis retained-state 增长是否能造成默认服务不可用，再测 trigger/convert/dependency_check parser request-burst 的 heap/CPU/GC 门槛。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] xnx3/wangmarket 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 17:26

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `xnx3/wangmarket` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot/JSP/Shiro、根级匿名 `.do`/`.html`、验证码/登录校验、公开站点页面、UEditor 和安装态边界。
- 按用户限定范围排除磁盘存储耗尽、后台/管理权限入口、首次安装一次性状态、特殊云存储配置和不属于当前仓库的插件入口，只判断默认配置下外部请求可触发的非磁盘资源耗尽问题。
- 保留 1 个 `likely` 候选：默认匿名 `/captcha.do` 和带非空 `code` 的 `/wangmarketLoginSubmit.do` 会通过 `CaptchaUtil` 创建 server-side session；默认 Shiro 使用 `MemorySessionDAO` 且 100 分钟超时，未见 session 数量或 per-IP 上限。
- 保留 1 个 `needs_dynamic_probe` 候选：安装完成并配置站点域名后，公开 `*.html` 站点页面成功命中站点时会把 `SImpleSiteVO` 写入匿名 session，同样可能驱动 session count 增长。
- 明确拒绝后台模板导入/还原、新闻/站点管理、UEditor 文件存储、云存储页面源缓存、日志持久化、phoneCreateSite 外部插件、安装流程和登录后空间统计线程等高噪声或范围外路径。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/xnx3__wangmarket/`
- 新增报告：`results/applications_static_analysis/xnx3__wangmarket/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/xnx3__wangmarket/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/xnx3__wangmarket` 源码、`databases/applications/xnx3__wangmarket-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `xnx3/wangmarket` target 信息、内置 SQLite 快照和 `wm-3.28.jar` 字节码反编译证据。
- 对后续工作的影响：后续可优先动态验证匿名验证码/登录校验 session-count 增长在默认堆和默认 Shiro cleanup 下的 OOM/GC/不可用门槛；公开站点页面候选需要先完成默认安装域名/站点态。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] xuxueli/xxl-boot 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 16:50

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `xuxueli/xxl-boot` 做只静态资源耗尽 DoS 挖掘，覆盖 `xxl-boot-api` 默认 Spring Security 匿名面、`RepeatableFilter` JSON body 包装、验证码 Redis key、登录失败异步日志队列，以及 `xxl-boot-admin` SSO 边界。
- 按用户限定范围排除磁盘存储耗尽、DB 行增长、后台/管理权限入口、生产默认不会开放或需要管理登录的功能，只判断默认配置下外部 HTTP 请求可触发的非磁盘资源耗尽问题。
- 保留 1 个 `likely` 候选：默认匿名 `/login` 与 `/register` JSON body 会先经过全局 `RepeatableFilter` 完整读入 `StringBuilder`/`String` 并复制为 `byte[]`，未见应用级 JSON body 上限。
- 保留 2 个 `needs_dynamic_probe` 候选：匿名 `/captchaImage` 生成 2 分钟 TTL Redis captcha key 和验证码图片；匿名 `/login` 验证码失败路径会在用户名长度校验前提交登录失败 `TimerTask` 到 scheduled executor。
- 明确拒绝 Druid/Swagger 管理或文档面、`xxl-boot-admin` 后台业务控制器、文件上传/下载、Excel/代码生成、XSS wrapper 认证路径、默认关闭注册账号增长、未使用的 `@RateLimiter`/`@RepeatSubmit` 等高噪声模式。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/xuxueli__xxl-boot/`
- 新增报告：`results/applications_static_analysis/xuxueli__xxl-boot/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/xuxueli__xxl-boot/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/xuxueli__xxl-boot` 源码、`databases/applications/xuxueli__xxl-boot-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `xuxueli/xxl-boot` target 信息。
- 对后续工作的影响：后续可优先动态验证匿名 JSON body request-burst 的 heap/GC/不可用门槛，再测 `/captchaImage` Redis key 窗口和 `/login` 验证码失败异步队列/DB pool 压力。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] dromara/ujcms 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 16:30

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `dromara/ujcms` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Docker/compose、Spring Boot/Spring MVC/Spring Security、公开前台 API、访问统计、multipart、验证码、注册/留言、投票/问卷、分页和缓存路径。
- 按用户限定范围排除磁盘存储耗尽、后台/管理权限入口、默认关闭功能、特殊配置和仅数据库行增长路径，只判断默认配置下外部 HTTP 请求可触发的非磁盘资源耗尽问题。
- 保留 1 个 `likely` 候选：默认公开 `POST /frontend/visit/{siteId}` 与 `POST /api/visit/{siteId}` 可将攻击者控制的 `referrer` host 构造为未截断 `source` 字符串，并在写库前保留于 singleton `VisitService.visitLogCache`。
- 保留 1 个 `needs_dynamic_probe` 候选：同一公开访问统计入口每次请求都构造 `ua_parser.Parser`，反复加载和初始化 `regexes.yaml` 解析规则，可能造成 request-burst CPU/GC 压力。
- 明确拒绝后台 WebFile/ZIP、头像上传、Captcha/IP 登录/IP SMS bounded cache、默认关闭注册、默认需登录加验证码留言、投票/问卷选项校验、公开列表分页上限和浏览计数静态 map/cache 等高噪声模式。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/dromara__ujcms/`
- 新增报告：`results/applications_static_analysis/dromara__ujcms/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/dromara__ujcms/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`、`dynamic_probe_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/dromara__ujcms` 源码、`databases/applications/dromara__ujcms-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `dromara/ujcms` target 信息，以及本地 Maven 缓存中的 `uap-java-1.6.1` jar 反编译证据。
- 对后续工作的影响：后续可优先动态验证访问统计 `referrer` source 未截断路径在默认 Tomcat/Spring 接受阈值、异步写库失败/积压和有界堆下的服务不可用门槛；`Parser` per-request 构造候选需要对比 singleton 复用前后的 CPU/GC 曲线。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] ytyht226/taskflow 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 15:54

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `ytyht226/taskflow` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Maven 多模块 jar/pom 目标、DAG `wrapperMap`/依赖集合、`DagContext`、`TaskUtil` 批处理集合、`CustomThreadPool` 无界队列和 Gson/JsonPath/opConfig 参数解析路径。
- 按用户限定范围排除磁盘/文件存储耗尽、特殊配置、生产默认不开启功能、管理权限或管理面依赖路径，只判断默认配置下外部 HTTP 请求可触发的非磁盘资源耗尽问题。
- 未发现默认配置下可由外部 HTTP 请求直接触发的 `confirmed`、`likely` 或值得保留为 `needs_dynamic_probe` 的 DoS 候选；核心原因是该目标为 DAG 编排 jar library，没有默认 Web server、controller、servlet/filter、JAX-RS resource、request/session/multipart 入口。
- 明确拒绝 DAG wrapper graph 增长、依赖集合增长、TaskUtil taskList/batch 放大、无界 executor queue、Gson/JsonPath/opConfig 解析、listener map/list 和 DagContext 结果保留等库级误用模式，理由是均需要宿主应用把外部请求映射到 taskflow Java API。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/ytyht226__taskflow/`
- 新增报告：`results/applications_static_analysis/ytyht226__taskflow/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/ytyht226__taskflow/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/ytyht226__taskflow` 源码、`databases/applications/ytyht226__taskflow-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `ytyht226/taskflow` target 信息和本地 CodeQL build log。
- 对后续工作的影响：后续若要继续跟 taskflow 相关风险，应转向真实默认部署的宿主 Web 应用，查找匿名或低权限 HTTP 参数是否直接控制 DAG wrapper graph、TaskUtil taskList/batch 参数、opConfig/jsonPathList、递归参数解析、无界 executor queue 或跨请求保留的 DagEngine/DagContext。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] quickmsg/smqtt 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 15:44

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `quickmsg/smqtt` 做只静态资源耗尽 DoS 挖掘，覆盖官方 Docker 默认 MQTT TCP 1883、no-config fallback、默认匿名认证、CONNECT/PUBLISH/SUBSCRIBE/QoS2/offline session/retain message/topic registry 路径。
- 按用户限定范围排除磁盘/DB/Redis 持久化存储、需要挂载配置才开启的 HTTP/WS/cluster/admin/API、固定认证/ACL 等非默认配置路径，只判断默认配置下外部 MQTT 请求可触发的非磁盘资源耗尽问题。
- 保留 6 个 `likely` 默认匿名候选：persistent session 断开后保留 channel registry；retained PUBLISH 填充无界 `retainMessages`；普通 PUBLISH 对未订阅 topic 创建空 topic key；offline persistent subscription 累积 session message 队列；SUBSCRIBE 增长 fixed/wildcard topic index；QoS2 半握手缓存 publish message 与 retry ack state。
- 明确拒绝 HTTP `/smqtt/*` API、HTTP 管理/UI、WebSocket、cluster、Redis/DB persistent registry、ACL FILE/JDBC、固定认证、boundedElastic 队列和单帧 MQTT parser 大包等高噪声或非默认模式。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/quickmsg__smqtt/`
- 新增报告：`results/applications_static_analysis/quickmsg__smqtt/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/quickmsg__smqtt/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/quickmsg__smqtt` 源码、`databases/applications/quickmsg__smqtt-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `quickmsg/smqtt` target 信息。
- 对后续工作的影响：后续可优先动态验证 retained message、offline session queue、empty topic key cardinality 三条默认匿名 MQTT 路径，再测 persistent channel registry、subscription trie 和 QoS2 cache/ackMap 的服务不可用阈值。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] michaelliao/itranswarp 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 13:33

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `michaelliao/itranswarp` 做只静态资源耗尽 DoS 挖掘，覆盖默认 quickstart Docker Compose、Spring Boot/Tomcat、全局 Redis rate limiter、`/api` JSON body 解析、Passkey/WebAuthn、external gpt/remoteCodeRun、search、avatar、attachment、Markdown、view counter 和 Redis cache 路径。
- 按用户限定范围排除磁盘/DB 存储耗尽、特殊配置、生产默认不开启功能、管理权限或管理面依赖路径，只判断默认配置下外部 HTTP 请求可触发的非磁盘资源耗尽问题。
- 保留 2 个 `likely` 候选：可伪造代理 IP 头驱动 Redis rate-limit timestamp key 基数增长并绕过默认限流；`@RequestBody` JSON 在 `@RoleWith` 角色检查或默认禁用 feature flag 前被 Jackson 解析，可能造成 request-burst heap/CPU 压力。
- 保留 1 个 `needs_dynamic_probe` 候选：匿名 `/api/passkey/signin` 在 challenge/credential 校验前解码并解析攻击者控制的 WebAuthn 字段，需要动态确认 webauthn4j 对大字段的拒绝阶段和资源曲线。
- 明确拒绝 passkey challenge DB row、search、avatar、attachment 下载/上传存储、Markdown、remote-code-runner executor、ChatGPT outbound、OAuth provider、manage/admin 业务逻辑、public view counters、Redis first-page caches、本地/eth 登录和大 `pageIndex` 等高噪声模式。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/michaelliao__itranswarp/`
- 新增报告：`results/applications_static_analysis/michaelliao__itranswarp/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/michaelliao__itranswarp/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/michaelliao__itranswarp` 源码、`databases/applications/michaelliao__itranswarp-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `michaelliao/itranswarp` target 信息。
- 对后续工作的影响：后续可优先动态验证 Redis key cardinality/限流绕过和 pre-auth JSON parser heap 压力；Passkey/WebAuthn parser 候选需要先构造 valid-enough 字段再测量。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] aizuda/flowlong 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 13:14

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `aizuda/flowlong` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot/Solon example、`/process/deploy`、`/process/instance-start`、固定 `process.json`、流程模型 cache、实例启动、提醒调度、事件发布、ThreadLocal 和 SpEL/SnEL 表达式路径。
- 按用户限定范围排除磁盘/DB 持久化存储增长、特殊配置、管理权限或管理面依赖路径，只判断默认配置下外部 HTTP 请求可触发的非磁盘资源耗尽问题。
- 未发现默认配置下可由外部 HTTP 请求直接触发的 `confirmed`、`likely` 或值得保留为 `needs_dynamic_probe` 的非磁盘 DoS 候选；核心原因是默认 HTTP 面只暴露固定示例入口，外部请求不能控制模型内容、流程 key、变量大小、缓存 key、表达式、队列/线程或 body/multipart 字节。
- 明确拒绝默认 `/process/deploy` 任意模型上传、固定 `process.json` parse、`FlowSimpleCache` key cardinality、`/process/instance-start` DB row 增长、per-instance process model cache、reminder scheduler scan、event publish、`FlowDataTransfer` ThreadLocal、SpEL/SnEL eval 和 Solon `maxBodySize=1024mb` 等高噪声模式。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/aizuda__flowlong/`
- 新增报告：`results/applications_static_analysis/aizuda__flowlong/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/aizuda__flowlong/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/aizuda__flowlong` 源码、`databases/applications/aizuda__flowlong-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `aizuda/flowlong` target 信息。
- 对后续工作的影响：后续若要继续跟 FlowLong 相关风险，应转向真实默认部署的宿主 Web 应用，查找匿名或低权限 HTTP 参数是否直接控制 workflow JSON 部署、process/tenant key、启动变量、dynamicAssignee、条件表达式、提醒/trigger/timer 配置、per-instance model cache 或自定义无界 `FlowCache`/event/executor。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] j-easy/easy-flows 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 13:05

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `j-easy/easy-flows` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Maven jar 目标、库 API source、`WorkContext`、`RepeatFlow`、`TimesPredicate`、`ParallelFlow`、`SequentialFlow`、executor/report/context merge 等资源敏感点。
- 按用户限定范围排除磁盘存储耗尽、特殊配置、管理权限或管理面依赖路径，只判断默认配置下外部 HTTP 请求可触发的非磁盘资源耗尽问题。
- 未发现默认配置下可由外部 HTTP 请求直接触发的 `confirmed`、`likely` 或值得保留为 `needs_dynamic_probe` 的 DoS 候选；核心原因是该目标为 workflow engine jar library，没有默认 Web server、controller、servlet/filter、JAX-RS resource、request/session/multipart 入口。
- 明确拒绝 `WorkContext` map 增长、`RepeatFlow.times(0/负数)` 长循环、custom predicate、`ParallelFlow` workUnits/task/future/report cardinality、executor/thread 压力和 `ParallelFlowReport` context merge 等库级误用模式，理由是均需要宿主应用把外部请求映射到 easy-flows API。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/j-easy__easy-flows/`
- 新增报告：`results/applications_static_analysis/j-easy__easy-flows/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/j-easy__easy-flows/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/j-easy__easy-flows` 源码、`databases/applications/j-easy__easy-flows-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `j-easy/easy-flows` target 信息和本地 CodeQL build log。
- 对后续工作的影响：后续若要继续跟 easy-flows 相关风险，应转向真实默认部署的宿主 Web 应用，查找匿名或低权限 HTTP 参数是否直接控制 `RepeatFlow.times(...)`、workflow work unit count、长生命周期 `WorkContext` 或 caller-provided executor。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] getrebuild/rebuild 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 12:24

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `getrebuild/rebuild` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Docker 部署、Spring Boot/Tomcat session、Ehcache、匿名白名单、验证码、条码/二维码生成、OpenAPI 网关、登录失败 retry cache、`X-ReqRandom` re-entry cache、任务队列、分享/文件/OnlyOffice/邮件/2FA 等路径。
- 按用户限定范围排除磁盘存储耗尽、需要特殊配置、生产默认不会开启的安全性配置、管理权限或管理面依赖路径；Ehcache `overflowToDisk` 只作为排除项记录，非磁盘判断以 `maxElementsInMemory=10000` 为边界。
- 保留 2 个 `likely` 默认匿名候选：拦截器在认证前通过 `ServletUtils.getSessionAttribute` 创建 120 分钟 Tomcat session；匿名 `/commons/barcode/render*` 可由长 `t` 和 `w=1200` 放大 ZXing `BitMatrix`/`BufferedImage` request-burst heap/CPU。
- 保留 4 个 `needs_dynamic_probe` 候选：`/gw/api/**` 在签名验证前读取并 FastJSON parse raw body；`/user/captcha?k=` 的 session/MobKey 增长；`/user/user-login` 失败路径的 `LoginRetry-*` cache 增长；`X-ReqRandom` 预认证 re-entry cache 增长。
- 明确拒绝文件/磁盘、admin/setup、OnlyOffice、邮件验证码、2FA/temp-auth/auto-login、登录成功队列、API 日志队列、共享仪表盘 token 依赖、map/mermaid/search/metadata auth-gated 路径、头像和 live-wallpaper 固定 upstream 等高噪声模式。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/getrebuild__rebuild/`
- 新增报告：`results/applications_static_analysis/getrebuild__rebuild/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/getrebuild__rebuild/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/getrebuild__rebuild` 源码、`databases/applications/getrebuild__rebuild-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `getrebuild/rebuild` target 信息，以及本地 Maven 缓存中的 `easy-captcha` / `devezhao commons` jar 反编译证据。
- 对后续工作的影响：后续可优先动态验证 `REBUILD-APP-STATIC-0001` 的匿名 session OOM/GC 门槛和 `REBUILD-APP-STATIC-0002` 的条码渲染 OOM 门槛，再验证 `/gw/api/**` pre-auth JSON parse、captcha/LoginRetry/ReqRandom cache 在默认 Ehcache 和有界堆下是否能造成持续服务不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] Tencent/APIJSON 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 12:36

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `Tencent/APIJSON` 做只静态资源耗尽 DoS 挖掘，覆盖本地 build-mode DB 实际包含的 `APIJSONORM 8.1.8` jar 模块、Parser/Verifier/SQLExecutor/FunctionParser/script executor 等默认资源面。
- 按用户限定范围排除磁盘存储耗尽、需要特殊配置、生产部署通常不会开启的安全性配置、管理权限或管理面依赖路径，只判断默认配置下外部请求可能导致的非磁盘资源耗尽。
- 未发现默认配置下可落为 `confirmed`、`likely` 或需要单独动态验证的外部请求直接 DoS 候选；核心原因是该目标为 ORM library 且无默认 HTTP entry，表访问、query count/page、对象/数组/深度、SQL 数量、where/having/combine 复杂度均有默认边界。
- 明确拒绝任意表 GET/HEAD 查询、超大 count/page、SQL cache/connection map cardinality、compiledScriptMap、FUNCTION_MAP、REQUEST_MAP、`@combine/@having` CPU、`@explain` 和 raw SQL/SQL function 等高噪声模式。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/tencent__apijson/`
- 新增报告：`results/applications_static_analysis/tencent__apijson/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/tencent__apijson/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/tencent__apijson` 源码、`databases/applications/tencent__apijson-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `Tencent/APIJSON` target 信息。
- 对后续工作的影响：如果继续分析 APIJSON 生态，应转向官方 APIJSON-Demo 或真实默认部署集成应用，单独记录 HTTP controller、默认 seed/Access/Request/Function 表和是否修改 `MAX_*`、`ENABLE_SCRIPT_FUNCTION`、`Log.DEBUG`、`needVerify` 或 parser/executor 生命周期。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] diyhi/bbs 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 11:57

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `diyhi/bbs` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot 4.0.3、Spring Security 前台/后台边界、JCache/Ehcache、Kaptcha、Lucene 搜索、访问量统计队列、登录失败频控、OAuth token、短信/邮箱验证码、异步线程池和文件/视频跳转等资源 sink。
- 按用户限定范围排除磁盘存储耗尽、需要特殊安全配置、生产默认不会开启的安全性配置、管理权限或管理面依赖路径。
- 保留 4 个 `likely` 默认外部请求候选：匿名 `/search` 的无上限 `page` 放大 Lucene `TopDocs`/sort collector；匿名 `/captcha/{captchaKey}` 可向高容量 Ehcache 写入攻击者控制 key；匿名 `/login` 失败路径可制造 `submitQuantity` 高基数缓存键；匿名 `/statistic/add` 可填充进程级 100 万容量 PV 队列。
- 明确拒绝成功注册后的 OAuth token cache、短信/邮箱验证码、第三方登录、文件/富文本上传、文件下载/视频 redirect、range download、`/control/**` 管理接口、install/upgrade、异步会员卡任务和 hot-topic 去重队列等高噪声路径。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/diyhi__bbs/`
- 新增报告：`results/applications_static_analysis/diyhi__bbs/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/diyhi__bbs/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/diyhi__bbs` 源码、`databases/applications/diyhi__bbs-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `diyhi/bbs` target 信息。
- 对后续工作的影响：后续可优先动态验证 `DIYHI-BBS-APP-STATIC-0004` 的匿名 PV 队列 heap/OOM 门槛和 `DIYHI-BBS-APP-STATIC-0001` 的 Lucene page 放大 OOM/GC 门槛，再验证 captcha cache 和 login submitQuantity cache 在默认 JCache/Ehcache、有界堆下是否能造成持续服务不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] Yiuman/citrus 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 11:33

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `Yiuman/citrus` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot 2.5.2、Spring Security/JWT、验证码 session repository、全局 request wrapper、匿名登录、CRUD/Excel/文件/工作流等资源 sink。
- 按用户限定范围排除磁盘存储耗尽、需要特殊安全配置、生产默认不会开启的安全性配置、管理权限或管理面依赖路径。
- 保留 1 个 `likely` 默认匿名候选：`/rest/verify/captcha` 可创建新 `HttpSession` 并保留 `Captcha/BufferedImage`，默认未见 session 数、每 IP 或速率边界。
- 保留 1 个 `needs_dynamic_probe` 默认匿名候选：`/rest/authenticate` JSON body 在全局 `RequestWrapperFilter` 和认证 `JsonServletRequestWrapper` 中被完整缓存、复制和 Jackson 解析，可能造成 request-burst heap/CPU 压力。
- 明确拒绝 base64image、sms verify no-op、Redis verify store 特殊配置、文件上传、CRUD import/export、流程部署、ThreadUtils bounded queue 和 CrudHelper class-key cache 等高噪声路径。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/yiuman__citrus/`
- 新增报告：`results/applications_static_analysis/yiuman__citrus/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/yiuman__citrus/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/yiuman__citrus` 源码、`databases/applications/yiuman__citrus-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `Yiuman/citrus` target 信息。
- 对后续工作的影响：后续可优先动态验证 `CITRUS-APP-STATIC-0001` 的 session/heap OOM 门槛，再比较 `CITRUS-APP-STATIC-0002` 在 backend 8080 直连和 nginx 80 代理路径下的大 JSON body request-burst 行为。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] hiparker/opsli-boot 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 11:33

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `hiparker/opsli-boot` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot 3.4.6、默认 `local` profile、匿名登录/验证码/common create-code 入口、默认 WAF、`@Limiter`、Redis captcha/verification-code key、SMTP/SMS 同步调用、Druid、multipart、Excel、代码生成和登录失败计数等路径。
- 按用户限定范围排除磁盘存储耗尽、生产中不会开启或属于监控/管理面的 Druid 路径、需要管理权限的后台业务接口、上传/Excel/代码生成文件面，以及默认不启用的 WAF SQL filter。
- 未发现默认配置下可静态确认的 `confirmed` 非磁盘资源耗尽 DoS。
- 保留 1 个 `likely` 默认匿名候选：默认 WAF 对匿名 JSON request body 完整读入 `String`、执行多轮 XSS regex/string 处理并再创建 `byte[]` / `ByteArrayInputStream`，可造成 request-burst heap/CPU 压力。
- 保留 3 个 `needs_dynamic_probe`：匿名 `/captcha` Redis key 增长与 spoofable header 限流绕过支撑、匿名 email/mobile create-code 的 5 分钟 Redis key 与同步外部 I/O、`@Limiter` 进程级 cache 可被 spoofed IP header 填充到 100000/5 分钟边界。
- 明确拒绝登录失败任意 username Redis key 增长、`/system/slipCount`、`/api/*/common/public-key`、Druid、multipart/upload/static file、Excel、代码生成、Swagger/doc 和 WAF 参数/header 过滤 standalone finding。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/hiparker__opsli-boot/`
- 新增报告：`results/applications_static_analysis/hiparker__opsli-boot/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/hiparker__opsli-boot/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/hiparker__opsli-boot` 源码、`databases/applications/hiparker__opsli-boot-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `hiparker/opsli-boot` target 信息。
- 对后续工作的影响：后续可优先动态验证 `OPSLI-BOOT-APP-STATIC-0001` 的默认匿名 JSON/WAF heap 与 regex CPU 门槛，再验证 `/captcha` 和 create-code Redis/限流/外部 I/O 在默认 Redis/MySQL 与受限 heap 下是否能造成持续服务不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] javamelody/javamelody 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 10:27

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `javamelody/javamelody` 做只静态资源耗尽 DoS 挖掘，覆盖默认 `MonitoringFilter /*`、Spring Boot starter 默认启用、默认 `/monitoring`、JVM 诊断报告、`system-actions-enabled`、`HttpAuth` 默认开放语义和 `javamelody-collector-server` 注册面。
- 按用户限定范围排除磁盘存储耗尽、需要特殊安全配置、生产中不会默认开启的管理端点配置、管理破坏动作以及宿主应用自身会话/业务状态增长。
- 未发现默认配置下可静态确认的 `confirmed` 或 `likely` 非磁盘资源耗尽 DoS。
- 保留 3 个 `needs_dynamic_probe`：默认 HTTP counter request-name cardinality burst、默认开放 `/monitoring` 昂贵 JVM 诊断请求、collector-server 默认 POST 注册面驱动 registry/周期采集负载增长。
- 明确拒绝 random 404 path、query string cardinality、Spring route variable 聚合后路径、JavaMelody 固定 session metadata、heap dump、RRD/serialized 文件、`authorized-users`、`allowed-addr-pattern`、management endpoint monitoring、mail/exporters/custom reports/sampling 和 clear/kill/pause 等管理动作。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/javamelody__javamelody/`
- 新增报告：`results/applications_static_analysis/javamelody__javamelody/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/javamelody__javamelody/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/javamelody__javamelody` 源码、`databases/applications/javamelody__javamelody-db`、项目内 `skills/java-web-dos-hunter`、应用 manifest 中的 `javamelody/javamelody` target 信息。
- 对后续工作的影响：后续可优先动态验证 `JAVAMELODY-APP-STATIC-0001` 的 60 秒/10000 清理前 burst heap 门槛，再验证默认 `/monitoring` 诊断请求和 collector-server 注册面在受限 heap 下是否能造成持续服务不可用。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-24] yangzongzhuan/RuoYi-Vue-fast 应用级静态 DoS 挖掘

### 修改时间
2026-06-24 10:16

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `yangzongzhuan/RuoYi-Vue-fast` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot 2.5.15、Spring Security/JWT、Redis captcha/token、Swagger 测试控制器、全局 JSON repeatable filter、异步登录日志、上传/Excel/缓存监控等资源 sink。
- 按用户限定范围排除磁盘存储耗尽、默认关闭注册、需要管理权限的 Excel/Redis monitor/Quartz/代码生成路径，以及特殊配置或管理面依赖路径。
- 保留 2 个 `likely` 默认外部请求候选：低权限 `/test/user/save` 可向进程级 static `LinkedHashMap` 持续写入可控 `UserEntity`；匿名 JSON 请求在全局 `RepeatableFilter` 中被完整读入 `StringBuilder` 并复制为 `byte[]`，默认匿名 `/login` 可触发 request-burst heap 压力。
- 保留 3 个 `needs_dynamic_probe` 候选：匿名 `/captchaImage` 短 TTL Redis key 增长、匿名登录失败异步日志任务队列压力、成功登录生成 30 分钟 Redis token key。
- 明确拒绝上传/头像、Excel import/export、Redis cache monitor、Quartz、代码生成、Druid、referer filter、默认关闭 `/register` 等高噪声路径，避免将磁盘存储、管理面或默认关闭功能误报为默认直接 DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/yangzongzhuan__ruoyi-vue-fast/`
- 新增报告：`results/applications_static_analysis/yangzongzhuan__ruoyi-vue-fast/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/yangzongzhuan__ruoyi-vue-fast/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/yangzongzhuan__ruoyi-vue-fast` 源码、项目内 `skills/java-web-dos-hunter`、默认 `application.yml` / `application-druid.yml` / `sql/ry_20260417.sql` 配置证据。
- 对后续工作的影响：后续可优先动态验证 `RYVF-APP-STATIC-0001` static map heap/OOM 门槛和 `RYVF-APP-STATIC-0002` 匿名大 JSON body request-burst OOM 门槛，再按需验证 Redis captcha/token 与 async login-log 队列的真实服务不可用条件。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] prometheus/jmx_exporter 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 23:17

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `prometheus/jmx_exporter` 做只静态资源耗尽 DoS 挖掘，覆盖 Java agent / standalone HTTP mode、默认 `/metrics`、JMX scrape、Prometheus exposition、HTTP worker pool、MBean/rule cache、Basic auth 和 SSL/OpenTelemetry 等配置依赖路径。
- 按用户限定范围排除磁盘存储耗尽、需要生产中不会默认开启的安全配置、特殊启动参数、管理权限或非外部 HTTP 请求驱动的问题。
- 未发现默认配置下可由外部 HTTP 请求直接导致 confirmed / likely 非磁盘资源耗尽 DoS 的候选。
- 保留 1 个低可信 `needs_dynamic_probe`：匿名 `/metrics` 可重复触发完整 JMX scrape、per-request response encoding 和最多 10 个默认 worker 占用，但线程/队列有硬边界，资源规模主要由目标 JVM MBean/属性集合和配置决定，不由 HTTP 输入制造长生命周期状态。
- 明确拒绝 `name[]`、`debug`、`Accept`、`Accept-Encoding`、MBean/rule cache、Basic auth credential cache / PBKDF2、SSL reload、OpenTelemetry 和 isolator 多实例等高噪声路径。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/prometheus__jmx_exporter/`
- 新增报告：`results/applications_static_analysis/prometheus__jmx_exporter/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/prometheus__jmx_exporter/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/prometheus__jmx_exporter` 源码、`databases/applications/prometheus__jmx_exporter-db`、项目内 `skills/java-web-dos-hunter`、本地 Maven 缓存中的 `io.prometheus:prometheus-metrics-exporter-common:1.8.0` bytecode 用于 `javap` 复核。
- 对后续工作的影响：后续如需动态验证，可只聚焦匿名 `/metrics` 并发 scrape 在默认 Java agent / standalone HTTP mode 下的 worker 饱和、heap/GC 峰值、remote JMX 连接占用和持续可用性。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] TaleLin/lin-cms-spring-boot 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 23:01

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `TaleLin/lin-cms-spring-boot` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot 2.5.2、Lin CMS starter 鉴权、匿名 `/v1/book`、登录、multipart、日志、WebSocket 和管理接口。
- 按用户限定范围排除磁盘存储耗尽、需要管理权限、需要特殊安全配置或默认未启用的路径；不把 DB/disk 持久增长本身作为漏洞结论。
- 保留 1 个 `likely` 默认外部请求候选：匿名 `/v1/book` 可写入 bounded-size 记录，随后匿名全量列表/LIKE 搜索无分页，造成请求期 MyBatis/Jackson heap、DB scan 和响应字节放大。
- 保留 1 个 `needs_dynamic_probe` 候选：默认验证码关闭且无登录限速，`/cms/user/login` 对已有用户名执行 PBKDF2-SHA256 64000 轮密码校验，密码字段缺少长度上限。
- 明确拒绝 `/cms/file` 上传、WebSocket session set、管理/日志分页、权限结构化 Map、MDC/ThreadLocal 和默认关闭 captcha 等高噪声路径，避免把权限依赖、特殊配置或磁盘存储误报为默认直接 DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/talelin__lin-cms-spring-boot/`
- 新增报告：`results/applications_static_analysis/talelin__lin-cms-spring-boot/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/talelin__lin-cms-spring-boot/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/talelin__lin-cms-spring-boot` 源码、`databases/applications/talelin__lin-cms-spring-boot-db`、项目内 `skills/java-web-dos-hunter`、本地 Maven 缓存中的 Lin CMS starter/core 与 JHash jar 用于 `javap` 鉴权和 PBKDF2 证据。
- 对后续工作的影响：后续可优先动态验证匿名 `/v1/book` 无分页结果物化在默认 heap/MySQL 下的服务不可用门槛，再验证登录 PBKDF2 CPU/thread 饱和风险。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] LinShunKang/MyPerf4J 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 22:59

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `LinShunKang/MyPerf4J` 做只静态资源耗尽 DoS 挖掘，覆盖默认 JavaAgent bootstrap、内置 JDK `HttpServer`、`/switch/debugMode`、HTTP parser、method tag/recorder、Influx exporter 和官方默认配置模板。
- 按用户限定范围排除磁盘存储耗尽、特殊 exporter 配置和非外部请求驱动路径；不把本地类加载、metrics 日志文件或 InfluxDB 配置依赖路径表述为默认应用 DoS。
- 保留 1 个 `likely` 默认外部请求候选：默认内置 HTTP server 在 dispatcher 路由判断前对匿名 POST body 执行无应用层大小限制的全量堆内读取。
- 保留 1 个 `needs_dynamic_probe` 候选：默认 `max_workers=2` 的内置 HTTP server 可能被慢速/大 body POST 占用导致管理 HTTP 面不可用。
- 明确降级 query/header request-local 解析，并拒绝 method registry、recorder arrays、scheduler queue、Influx async queue 等高噪声路径。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/linshunkang__myperf4j/`
- 新增报告：`results/applications_static_analysis/linshunkang__myperf4j/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/linshunkang__myperf4j/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/linshunkang__myperf4j` 源码、`databases/applications/linshunkang__myperf4j-db`、项目内 `skills/java-web-dos-hunter`、README 指向的官方 `MyPerf4J-3.x.properties` 默认配置模板。
- 对后续工作的影响：后续可优先动态验证 `MYPERF4J-APP-STATIC-0001` 的默认 JavaAgent HTTP body OOM/GC death 门槛，再验证慢 body 对 `2048` 内置 HTTP server worker 的占用效果。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] tianshiyeben/wgcloud 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 22:29

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `tianshiyeben/wgcloud` 做只静态资源耗尽 DoS 挖掘，覆盖默认 Spring Boot server、`AuthRestFilter`、agent 上报 API、公众看板和登录/static allowlist。
- 按用户限定范围排除磁盘存储耗尽、管理权限路径和特殊配置路径；不把 DB 行/日志/监控表增长作为主问题。
- 保留 2 个 `likely` 默认外部请求候选：未登录请求在鉴权前创建 120 分钟服务端 session；默认共享 token 的 `/agent/minTask` 通过 raw JSON 解析、实体列表化和 `BatchData` 静态列表造成 heap/batch-copy 压力。
- 保留 1 个 `needs_dynamic_probe` 数据依赖候选：公众看板 `dashView` 放行后，`pageSize` 可放大已有监控数据的分页物化和 per-host 明细查询。
- 明确降级 `/appInfo/agentList`、告警邮件线程池、后台 CRUD、验证码和登录暴力等高噪声路径，避免将管理面、邮件配置依赖或磁盘持久增长误报为默认直接 DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/tianshiyeben__wgcloud/`
- 新增报告：`results/applications_static_analysis/tianshiyeben__wgcloud/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/tianshiyeben__wgcloud/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅新增静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/tianshiyeben__wgcloud` 源码、`databases/applications/tianshiyeben__wgcloud-db`、项目内 `skills/java-web-dos-hunter`。
- 对后续工作的影响：后续可优先动态验证匿名 session retention 和默认 token `/agent/minTask` heap/OOM 门槛，再确认 `dashView: yes` 运行时绑定和公众看板 `pageSize` 数据依赖风险。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] erupts/erupt 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 22:12

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `erupts/erupt` 做只静态资源耗尽 DoS 挖掘，覆盖官方 sample 默认配置、Spring MVC `/erupt-api` 管理 API、UPMS 验证码/登录、默认操作日志过滤器、AI MCP SSE、Excel、Terminal 和 WebSocket。
- 按用户限定范围排除磁盘存储耗尽、需要管理权限或特殊配置的路径；默认保留非磁盘资源候选，不把静态增长路径表述为已确认 DoS。
- 保留 3 个 `likely` 候选：匿名 `/erupt-api/code-img` 的 `height` 参数驱动 EasyCaptcha `BufferedImage` 堆分配；默认操作日志过滤器在鉴权前复制 `/erupt-api` JSON body 且可能在线程本地变量中滞留；官方 sample 默认开启的 `/mcp/sse` 匿名连接每连接创建 executor/scheduler 线程并使用无超时 emitter。
- 明确拒绝或降级 Excel POI 导入/导出、Terminal PTY、普通 WebSocket session map、数据分页和文件上传等高噪声路径，避免将权限依赖、磁盘存储或通用连接生命周期误报为默认直接 DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/erupts__erupt/`
- 新增报告：`results/applications_static_analysis/erupts__erupt/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/erupts__erupt/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：静态挖掘未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/erupts__erupt` 源码、`databases/applications/erupts__erupt-db`、项目内 `skills/java-web-dos-hunter`、本地 Maven 缓存中的 EasyCaptcha 1.6.2 jar 用于 `javap` 分配证据。
- 对后续工作的影响：后续可优先动态验证 `ERUPT-APP-STATIC-0003` 的匿名 SSE thread exhaustion，再验证 `ERUPT-APP-STATIC-0001` 的验证码 OOM 门槛和 `ERUPT-APP-STATIC-0002` 的大 JSON body/ThreadLocal retained heap。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] jetlinks-community 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 21:51

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 本地 ignored 证据产物

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `jetlinks/jetlinks-community` 做只静态资源耗尽 DoS 挖掘，覆盖默认 `run-all` 部署、Spring WebFlux 管理面、文件管理、缩略图、设备物模型导入、Messaging WebSocket 和设备网关配置路径。
- 按用户补充范围修订结果：磁盘存储耗尽、持久文件增长和 DB 文件元数据增长不纳入问题范围；管理权限、`@SaveAction`、设备/产品配置写入和网关启动等管理面路径不纳入问题范围。
- 删除原 `JETLINKS-APP-STATIC-0001` 文件上传持久存储候选和原 `JETLINKS-APP-STATIC-0003` 设备/产品 metadata import 管理权限候选，并同步清理 findings、source/sink/flow 结构化结果。
- 当前仅保留两个默认外部请求相关候选：公开 `/file/{fileId}?thumb=...` 缩略图在解码前整文件入堆，以及 `/messaging/{token}` WebSocket 唯一订阅 id 导致连接生命周期订阅增长。
- 明确降级或拒绝公开系统信息、配置、菜单、通知、captcha、HTTP device gateway route map、dashboard SSE 等高噪声模式，避免把配置依赖、磁盘存储或管理面路径表述为默认直接 DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/jetlinks__jetlinks-community/`
- 新增报告：`results/applications_static_analysis/jetlinks__jetlinks-community/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/jetlinks__jetlinks-community/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅修订静态结果和文档，未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/jetlinks__jetlinks-community` 源码、`databases/applications/jetlinks__jetlinks-community-db`、项目内 `skills/java-web-dos-hunter`。
- 对后续工作的影响：后续可优先动态验证 `JETLINKS-APP-STATIC-0002`，重点观测缩略图 heap/GC、公开文件前置条件和 `8848` HTTP 可用性；`JETLINKS-APP-STATIC-0004` 可作为低权限 WebSocket 连接生命周期资源 probe。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] PowerJob/PowerJob 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 21:25

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `PowerJob/PowerJob` 默认 compose、Spring Boot 2.7.18 / Undertow 管理面和 Vert.x HTTP remote 面完成只静态资源耗尽 DoS 挖掘。
- 保留 2 个 `likely` 候选：默认 OpenAPI 鉴权关闭时基于有效 `appId` 的 job/workflow node 持久化增长，以及认证前 `CachingRequestBodyFilter` 对普通 POST body 全量入堆导致默认 512MiB heap 下的 request-burst 内存风险。
- 保留 2 个 `needs_dynamic_probe` 候选：默认暴露 `10010` 的 HTTP remote worker heartbeat 进程内 cluster map 基数增长，以及匿名 container template 生成导致的临时文件 churn。
- 明确降级 container jar upload、普通管理端 job/workflow 写入、OpenAPI auth/assert、runJob/workflow run、worker log report 等高噪声或路径证明不足模式，避免把静态增长路径表述为 confirmed DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/powerjob__powerjob/`
- 新增报告：`results/applications_static_analysis/powerjob__powerjob/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/powerjob__powerjob/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：静态挖掘未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/powerjob__powerjob` 源码、`databases/applications/powerjob__powerjob-db`、`skills/java-web-dos-hunter`、本地 Maven 缓存中的 Spring Boot 2.7.18 / Vert.x 4.3.7 依赖。
- 对后续工作的影响：后续可优先动态验证 `POWERJOB-APP-STATIC-0002` 的默认 512MiB heap OOM 门槛和 `POWERJOB-APP-STATIC-0003` 的 remote heartbeat map 增长，再验证 OpenAPI appId 前提与 MySQL/调度侧服务不可用门槛。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] iflytek/astron-agent 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 21:05

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 本地 ignored 证据产物

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `iflytek/astron-agent` 的默认 Docker compose、Spring Boot 3.5.4 console-hub/toolkit 后端、nginx gateway、MinIO/S3、知识库文件处理、SSE 和 MCP 调试入口完成只静态资源耗尽 DoS 挖掘。
- 保留一个 P1 `needs_dynamic_probe` 候选：认证用户可通过 `/console-api/api/s3/presign` 获取默认 bucket 的 MinIO PUT 预签名 URL，应用层未绑定 object size、object count 或用户配额；因默认 `OSS_REMOTE_ENDPOINT` 对客户端可达性需运行态确认，未提升为 `likely`。
- 保留两个 `likely` 应用逻辑候选：`/file/embedding` 与 `/file/embedding-back` 使用 `fileIds.size()` 创建未 shutdown 的自建 fixed thread pool，并在任务中无 sleep/backoff 轮询 DB；`/file/create-html-file` 可按无上限 `htmlAddressList` 持久写入 `file_info_v2` 行。
- 将普通 multipart 上传、skill-file 上传、`sliceFiles`/`retry` 线程池、全局 `@Async` executor、SSE retained map 和 MCP URL list 等路径按默认边界、timeout 或证据缺口降级记录，避免把静态增长线索表述为 confirmed DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/iflytek__astron-agent/`
- 新增报告：`results/applications_static_analysis/iflytek__astron-agent/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/iflytek__astron-agent/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：静态挖掘未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/iflytek__astron-agent` 源码、`databases/applications/iflytek__astron-agent-db`、默认 Docker/nginx 配置和项目内 `skills/java-web-dos-hunter`。
- 对后续工作的影响：后续可优先动态验证 `ASTRON-AGENT-APP-STATIC-0002` 的线程/CPU/DB pool 饱和门槛，并确认 `ASTRON-AGENT-APP-STATIC-0001` 返回的 MinIO 预签名 URL 在默认部署中的客户端可达性与对象存储配额状态。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] halo-dev/halo 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 19:16

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `halo-dev/halo` 的默认 Docker / Spring WebFlux HTTP 面完成只静态资源耗尽 DoS 挖掘，覆盖 endpoint profile、默认 RBAC、附件 policy、插件/主题安装、迁移恢复、评论、tracker、session/cache/queue 噪声。
- 发现 1 个低权限 `likely` 候选：默认本地附件 policy 未配置 `maxFileSize`，UC/console 附件上传和 URL 拉取路径可持续写入 `${halo.work-dir}/attachments/upload`，存在磁盘耗尽风险。
- 记录 3 个管理面 `needs_dynamic_probe` 候选：插件远程或 multipart JAR 写入临时文件、主题 ZIP 安装/升级解压、迁移恢复备份 ZIP 解压与 workdir/extension restore；均明确标注为管理角色依赖，不能按默认匿名漏洞表述。
- 明确拒绝公开评论默认匿名路径、tracker 任意 key 基数增长、session index、模板引擎 cache 和 extension queue 等高噪声模式。

### 交付成果
- 新增结果目录：`results/applications_static_analysis/halo-dev__halo/`
- 新增报告：`results/applications_static_analysis/halo-dev__halo/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/halo-dev__halo/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：详见本次最终回复；未执行动态验证，原因是用户明确要求“只静态挖掘”。

### 依赖与影响
- 依赖：本地源码 `frameworks/applications/halo-dev__halo`、应用级 CodeQL DB `databases/applications/halo-dev__halo-db`、项目内 `skills/java-web-dos-hunter`。
- 对后续工作的影响：后续可优先对 `HALO-APP-STATIC-0001` 做默认 Docker 真实 HTTP 动态验证，重点观测附件目录磁盘增长、低权限角色边界、请求延迟、GC 和服务可用性；管理面候选应仅在 disposable 实例中验证。
- 破坏性变更：无；未修改目标应用源码、CodeQL 查询、ranking、verdict、pipeline 或动态验证 harness。

---

## [2026-06-23] elunez/eladmin 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 20:45

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 本地 ignored 证据产物

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `elunez/eladmin` 做只静态资源耗尽 DoS 挖掘，覆盖 Spring Boot 2.7.18 安全配置、匿名认证接口、multipart 配置、本地/S3 存储、代码生成器、Excel 导出和运维上传。
- 发现一个 P1 `likely` 候选：`POST /api/localStorage/pictures` 只要求认证、无方法级 `@PreAuthorize`，自定义 `MultipartConfigElement` 未设置 max file/request size，且文件持久化缺少总量、用户或 IP 配额。
- 记录两个 Redis retained-state 候选：匿名 `/auth/code` 按请求创建 TTL captcha key，成功登录在默认 `single-login=false` 下按随机 JWT uid 保留多个 `online_token:*` key。
- 保留 S3 上传和代码生成下载为 `needs_dynamic_probe` / 配置依赖候选，并将 Excel 导出、数据库/部署上传、限流测试接口等高噪声模式降级记录，避免过度包装为默认低权限 DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/elunez__eladmin/`
- 新增报告：`results/applications_static_analysis/elunez__eladmin/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/elunez__eladmin/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`、`rejected_patterns.csv`
- 测试/验证结果：静态挖掘未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/elunez__eladmin` 源码、`databases/applications/elunez__eladmin-db`、Spring Boot 2.7.18 本地依赖 bytecode 反查和默认配置文件。
- 对后续工作的影响：后续可优先动态验证 `ELADMIN-APP-STATIC-0001`，重点观测 servlet multipart 临时目录、`/home/eladmin/file` 持久目录、DB 行增长、HTTP 可用性和磁盘耗尽行为。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] dianping/cat 应用级静态 DoS 挖掘

### 修改时间
2026-06-23 18:54

### 变更类型
- [文档] 应用级静态挖掘结果
- [新增功能] 本地 ignored 证据产物

### 核心改动
- 使用 `skills/java-web-dos-hunter` 对 `dianping/cat` 的默认 Docker/Tomcat HTTP 面做静态资源耗尽 DoS 挖掘，聚焦 `/r/*`、`/s/*` Unidal MVC 入口、默认权限配置、持久 DB 写入、进程内 map 和无上限查询物化。
- 发现两个高价值 `likely` 候选：匿名 `/s/project?op=projectUpdate` 可按唯一 `project.domain` 追加 `project` 表并增长 `ProjectService` 进程内 map；匿名 `/r/alert`、`/r/alteration` 插入可膨胀持久告警/变更表，并可通过无 `LIMIT` 宽时间范围查询放大堆和 CPU。
- 记录一个 `needs_dynamic_probe` 候选：匿名 `/s/permission?op=resource` 可替换大 `resource-config` 并刷新为 `m_permissions` map，但默认请求体边界和覆盖式写入使其暂不提升为 `likely`。
- 明确降级 `/s/config`、`/s/business` 等带 `@PreInboundActionMeta("login")` 的配置写入路径，避免把登录态依赖误判为默认匿名 DoS。

### 交付成果
- 新增本地结果目录：`results/applications_static_analysis/dianping__cat/`
- 新增报告：`results/applications_static_analysis/dianping__cat/STATIC_DOS_HUNT_REPORT.md`
- 新增明细：`results/applications_static_analysis/dianping__cat/source_inventory.csv`、`sink_inventory.csv`、`flow_candidates.csv`、`findings.jsonl`
- 测试/验证结果：静态挖掘未改 CodeQL、ranking、verdict 或 pipeline 逻辑；验证见最终回复。

### 依赖与影响
- 依赖：本地 `frameworks/applications/dianping__cat` 源码、`databases/applications/dianping__cat-db`、默认 Docker compose 与 `resource-config.xml` 静态证据。
- 对后续工作的影响：后续可优先对 `CAT-APP-STATIC-0001` 和 `CAT-APP-STATIC-0002` 做默认 compose 真实 HTTP 动态验证，重点观测 MySQL 表增长、CAT heap/GC、宽查询延迟和服务可用性。
- 破坏性变更：无；不修改 analyzer、CodeQL 查询、基座 Phase 3/4 结果或动态验证语义。

---

## [2026-06-23] smart-admin 应用级静态资源耗尽 DoS 挖掘

### 修改时间
2026-06-23 20:45

### 变更类型
- [文档] 应用级静态挖掘报告
- [新增功能] 应用级 static-analysis 结果归档

### 核心改动
- 使用 `skills/java-web-dos-hunter` 工作流对 `1024-lab/smart-admin` Java 17 / Spring Boot 3 后端完成只静态资源耗尽 DoS 审计。
- 建立目标画像、HTTP source 清单、资源 sink 清单和 source-to-sink 手工路径证据，重点覆盖代码生成、文件下载、Excel 导入导出、验证码、重复提交、分页边界、任务调度和 outbound client 噪声。
- 记录 4 个保留候选：低权限代码生成大对象生成、文件下载整文件入堆、企业全量 Excel 导出、商品 Excel 同步导入/导出；同时明确拒绝匿名验证码、默认文件上传磁盘填充、内存 RepeatSubmit、分页 page size、outbound client 和 SmartJob 等噪声。
- 补齐独立 source/sink/flow 明细和后续动态探针计划，并复核 Java 17 后端 `src/main` 中 Excel、文件、ZIP、缓存、线程池、Redis 和 outbound client 相关 sink，未发现比既有 4 个候选更强的默认应用级静态路径。
- 运行 smart-admin 应用 DB 上的通用 Phase 3 CodeQL 交叉检查，确认现有 retained-state 通用规则 0 条命中，人工候选按应用级路径单独归档。

### 交付成果
- 新增报告：`results/applications_static_analysis/1024-lab__smart-admin/report.md`
- 新增 findings：`results/applications_static_analysis/1024-lab__smart-admin/findings.csv`
- 新增 source 清单：`results/applications_static_analysis/1024-lab__smart-admin/source_inventory.csv`
- 新增 sink 清单：`results/applications_static_analysis/1024-lab__smart-admin/sink_inventory.csv`
- 新增 flow 清单：`results/applications_static_analysis/1024-lab__smart-admin/flow_candidates.csv`
- 新增探针计划：`results/applications_static_analysis/1024-lab__smart-admin/dynamic_probe_plan.md`
- 新增 inventory：`results/applications_static_analysis/1024-lab__smart-admin/inventory.jsonl`
- 新增 rejected/noise：`results/applications_static_analysis/1024-lab__smart-admin/rejected.csv`
- 新增 CodeQL 交叉检查输出：`results/applications_static_analysis/1024-lab__smart-admin/phase3_candidate_features.bqrs`、`results/applications_static_analysis/1024-lab__smart-admin/phase3_candidate_features.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：详见本次最终回复；未执行动态验证，原因是用户明确要求“只静态挖掘”。

### 依赖与影响
- 依赖：本地源码 `frameworks/applications/1024-lab__smart-admin`、应用级 CodeQL DB `databases/applications/1024-lab__smart-admin-db`、项目内 `skills/java-web-dos-hunter`。
- 对后续工作的影响：后续可优先对 `SMARTADMIN-STATIC-0001` 设计隔离动态探针，量化默认请求体限制、DB 字段长度和堆大小共同作用下的 OOM/GC death 阈值；其余候选需要先确认默认账号权限和数据规模。
- 破坏性变更：无；未修改目标应用源码、CodeQL 查询、ranking、verdict、pipeline 或动态验证 harness。

---

## [2026-06-22] 应用级 Java Web 目标采集与 CodeQL 建库

### 修改时间
2026-06-23 14:20

### 变更类型
- [新增功能] 应用级目标采集
- [新增功能] build-mode CodeQL 批量建库
- [功能改进] 国内源与 GitHub fallback
- [测试] 脚本单元测试
- [文档] 应用级流程记录

### 核心改动
- 新增 GitHub Java Web 应用目标采集脚本，按高星、HTTP/Web 信号、默认部署简单度和 Maven/Gradle 可建库性筛选 50 个真实应用目标。
- 新增应用级批量 clone 与 build-mode CodeQL 建库脚本，支持本地 `.build-cache/` Maven/Gradle 缓存、clone retry、嵌套 Maven/Gradle build root 自动识别、`--target` 子集重跑、`--java-home-candidate` 多 JDK 重试和 GitHub 加速/archive fallback。
- 生成中国 Maven settings 与 Gradle init script，优先使用阿里云、腾讯云 Maven/Gradle 相关源，并将 Gradle wrapper distribution URL 重写到腾讯云 Gradle 镜像。
- Maven/Gradle build-mode 命令默认跳过测试、前端、GPG、license、antrun 等非 Java 抽取步骤，减少真实应用因前端产物或发布插件导致的建库失败。
- 多轮重试、替换和补充目标后，本地状态中 51 个目标成功创建 build-mode CodeQL 数据库；最终 `intel/applications/java_web_application_targets.json` 固定其中 50 个更贴近 HTTP/Web 应用的成功目标。

### 交付成果
- 新增脚本：`scripts/collect_application_targets.py`、`scripts/build_application_databases.py`
- 新增测试：`tests/test_collect_application_targets.py`、`tests/test_build_application_databases.py`
- 新增/更新 manifest：`intel/applications/java_web_application_targets.json`（50 个 `build_succeeded` 目标）
- 本地源码：`frameworks/applications/`
- 本地数据库：`databases/applications/`
- 本地状态与日志：`results/application_dbs/application_db_build_status.jsonl`、`results/application_dbs/application_db_build_summary.md`、`results/application_dbs/logs/`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`

### 依赖与影响
- 依赖：GitHub clone 或 archive fallback、CodeQL CLI、Maven/Gradle 网络依赖解析、本机 Java 22/21/17。
- 对后续工作的影响：后续应用级 DoS 挖掘可直接从 50 个成功 build-mode DB 开始；额外成功和失败尝试可按 `results/application_dbs/` 状态日志复核或替换。
- 破坏性变更：无；不改变基座 Phase 3/4 查询、ranking、verdict 或动态验证语义。

---

## [2026-06-22] 冻结基座成果并切换到默认部署应用 DoS 规划

### 修改时间
2026-06-22 22:20

### 变更类型
- [文档] 研究方向调整
- [功能删除] 过时过程文档清理

### 核心改动
- 将仓库定位从继续扩展 Java Web 框架/基座层 retained-state DoS，调整为冻结现有 `WEB-REAL-*` 基座成果，并把下一阶段主线转向具体 Java Web 应用默认部署下的直接 DoS 挖掘。
- 在 `AGENTS.md` 中新增 `DefaultDeployAppDoS` 方法论、默认部署真阳性门槛、目标应用选择原则和下一阶段论文 RQ。
- 在 `README.md` 中记录基座成果冻结口径、权威索引、当前 evidence root 和下一阶段应用级 DoS 规划。
- 删除早期 Phase 2 顶层过程总结，避免旧入口发现阶段文档继续干扰当前主线。

### 交付成果
- 修改文档：`AGENTS.md`、`README.md`、`CHANGELOG.md`
- 删除过时文档：`EXECUTION_SUMMARY.md`、`PHASE2_FINAL_SUMMARY.md`
- 保留权威成果：`intel/regression/web_real_manifest.json`、`results/phase4/verified_vulnerabilities.*`、`results/phase4/dynamic_verification/`、`results/static_hunts/dynamic_verification/`
- 测试/验证结果：本次变更为文档和过时文件清理；验证见最终回复。

### 依赖与影响
- 依赖：现有 12 个 `WEB-REAL-*` manifest、已归档真实 HTTP 动态验证证据和 Dr.D 论文对 Java Web container 层工作的覆盖。
- 对后续工作的影响：后续默认从真实 Java Web 应用、官方默认部署和低权限 HTTP 入口开始；框架/基座层默认只做回归、证据刷新或披露材料整理。
- 破坏性变更：删除两个过时 Phase 2 过程总结；不影响 analyzer、CodeQL 查询、动态验证 runner 或权威结果。

---

## [2026-06-22] 新框架 Static-Hunt 真阳性提升为 WEB-REAL-0010..0012

### 修改时间
2026-06-22 12:05

### 变更类型
- [功能改进] WEB-REAL catalog
- [文档] 利用条件标注
- [测试] 回归门禁

### 核心改动
- 将 `SB3-STATIC-0002`、`MN-STATIC-0002`、`VERTX-STATIC-0003` 提升为稳定 `WEB-REAL-0010`、`WEB-REAL-0011`、`WEB-REAL-0012`，并在 dynamic runner 中保留旧 static ID 到新 WEB-REAL ID 的别名。
- 在 `intel/regression/web_real_manifest.json` 中为三项新增 `exploitability`，统一记录利用难度、默认是否可利用、必要前置条件和限制因素；三项均为 context-constrained confirmed cases。
- 将三项 PoC 和 OOM 日志归档到 `results/phase4/dynamic_verification/`，并更新 `verified_vulnerabilities.*` 本地证据库。
- 同步 README 和 AGENTS 中的动态验证覆盖范围、static ID 兼容映射和 WEB-REAL 真阳性列表。

### 交付成果
- 修改 runner：`scripts/run_dynamic_verification.py`
- 修改 manifest：`intel/regression/web_real_manifest.json`
- 更新测试：`tests/test_run_dynamic_verification.py`、`tests/test_web_real_catalog.py`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 本地 ignored 证据：`results/phase4/verified_vulnerabilities.json`、`results/phase4/verified_vulnerabilities.md`、`results/phase4/dynamic_verification/poc/`、`results/phase4/dynamic_verification/logs/`

### 依赖与影响
- 依赖：上一条 static-hunt 动态验证归档中的真实 HTTP 384MiB heap OOM 日志。
- 对后续工作的影响：`WEB-REAL-0010..0012` 已进入稳定 catalog，但 Phase 3 专项静态查询覆盖仍待补齐，因此 manifest 标记为 `dynamic_only_pending_query`。
- 破坏性变更：无；不改变已有 `WEB-REAL-0001..0009` 判定。

---

## [2026-06-22] Spring Boot 3 / Micronaut / Vert.x Static-Hunt 动态验证归档

### 修改时间
2026-06-22 11:33

### 变更类型
- [新增功能] 动态验证 harness
- [功能改进] static-hunt runner
- [文档] 验证归档
- [测试] runner 回归

### 核心改动
- 为 Spring Boot 3、Micronaut 和 Vert.x 的 8 个 2026-06-21 static-hunt 候选新增真实 HTTP 动态验证 probe，并接入 `scripts/run_dynamic_verification.py --suite static-hunt`。
- 扩展 runner 的 static-hunt registry、retained metric 提取、非 OOM verdict 归一化和 Maven 本地仓库路径，保证 `BLOCKED_*`、`NOT_VERIFIED_*` 不会被误提升为真阳性，并将 Maven 依赖缓存固定到项目 `.build-cache/m2/repository`。
- 完成 smoke 与 384MiB heap OOM profile 验证；严格按“真实 HTTP 请求触发服务 JVM heap OOM”门槛归档，确认 `SB3-STATIC-0002`、`MN-STATIC-0002`、`VERTX-STATIC-0003` 为真阳性，其余 5 项保留为 request-local、configuration-dependent、default-bounded、disk-only 或 timeout-bounded。
- 生成完整 8 项 consolidated summary 与人工归档报告，记录每项利用条件、限制因素和默认可利用性判断。

### 交付成果
- 修改 runner：`scripts/run_dynamic_verification.py`
- 修改依赖：`dynamic-verification/pom.xml`
- 新增 Spring Boot 3 probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/SpringBoot3WebFluxMultipartHttpProbe.java`、`dynamic-verification/src/main/java/org/example/dos/dynamic/SpringBoot3ClientObservationHttpProbe.java`
- 新增 Micronaut probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/MicronautClientPoolHttpProbe.java`、`dynamic-verification/src/main/java/org/example/dos/dynamic/MicronautInMemorySessionHttpProbe.java`、`dynamic-verification/src/main/java/org/example/dos/dynamic/MicronautMultipartHttpProbe.java`
- 新增 Vert.x probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/VertxBodyHandlerUploadHttpProbe.java`、`dynamic-verification/src/main/java/org/example/dos/dynamic/VertxSockJsSessionHttpProbe.java`、`dynamic-verification/src/main/java/org/example/dos/dynamic/VertxCachingWebClientHttpProbe.java`
- 更新测试：`tests/test_run_dynamic_verification.py`
- 本地 ignored 归档：`results/static_hunts/dynamic_verification/static_hunt_dynamic_verification_summary.json`、`results/static_hunts/dynamic_verification/new_framework_static_hunt_dynamic_verification_2026-06-21.md`、`results/static_hunts/dynamic_verification/logs/*.log`
- 实施计划：`docs/superpowers/plans/2026-06-21-new-framework-static-hunt-dynamic-verification.md`

### 依赖与影响
- 依赖：Maven 可解析 Spring Framework 6.2.19、Micrometer 1.15.12、Micronaut 3.10.8 和 Vert.x 4.5.28 运行时依赖；动态验证需要本地 HTTP socket 权限。
- 对后续工作的影响：3 个 confirmed static-hunt case 具备真实 HTTP heap OOM 证据，但尚未提升到 `WEB-REAL-*` catalog；如需提升，应同步 `intel/regression/web_real_manifest.json`、`results/phase4/verified_vulnerabilities.*`、`AGENTS.md` 和回归测试。
- 破坏性变更：无；未修改 CodeQL、ranking、verdict 或 Phase 3/4 pipeline 逻辑。

---

## [2026-06-21] Spring Boot 3 静态资源耗尽 DoS 挖掘

### 修改时间
2026-06-21 22:10

### 变更类型
- [文档] 静态挖掘报告

### 核心改动
- 按项目内 `java-web-dos-hunter` 工作流对 Spring Boot 3.5.15 做静态资源耗尽 DoS hunt，覆盖 WebFlux multipart、Servlet multipart、HTTP client observations、server observations、actuator repositories/cache 和 embedded server resource knobs。
- 运行 Spring Boot 3-only generic Phase 3 CodeQL 交叉检查，确认输出 0 条 data rows，未覆盖本轮源码审计得到的专项 patterns。
- 确认 `SB3-STATIC-0001`：WebFlux multipart 默认 `maxParts=-1` 与 `maxDiskUsagePerPart=-1` 仍存在，标为 `needs_dynamic_probe`。
- 确认 `SB3-STATIC-0002`：Boot 3 HTTP client observation 默认只限制 `uri` tag，Spring Framework 6.2.19 默认 convention 仍从 outbound URI host 生成低基数 `client.name`，标为 `needs_path_proof`。
- 将 Servlet multipart、httpexchanges、audit repository、server observations、MetricsEndpoint、CachingOperationInvoker、embedded server queue/header knobs 和 GraphQL observation 作为 rejected / low-priority patterns 记录。
- 关键技术决策：只做静态源码、依赖 bytecode 和 CodeQL 交叉检查，不刷新 Phase 3/4 全量 baseline，不执行真实 HTTP 动态 harness。

### 交付成果
- 新增本地静态挖掘报告：`results/static_hunts/spring_boot_3_static_hunt_2026-06-21.md`
- 新增静态 findings CSV：`results/static_hunts/spring_boot_3_static_findings_2026-06-21.csv`
- 新增 source/sink inventory：`results/static_hunts/spring_boot_3_static_inventory_2026-06-21.jsonl`
- 新增 rejected/noise CSV：`results/static_hunts/spring_boot_3_static_rejected_2026-06-21.csv`
- 新增 Spring Boot 3-only CodeQL 交叉检查输出：`results/static_hunts/spring-boot-3_phase3_candidate_features.bqrs`、`results/static_hunts/spring-boot-3_phase3_candidate_features.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：Spring Boot 3-only CodeQL generic Phase 3 query 成功执行并解码，输出 0 rows；后续一致性和 WEB-REAL 回归验证见本次最终回复。未运行动态验证，原因是用户明确要求“只静态挖掘”。

### 依赖与影响
- 依赖：本地 `frameworks/spring-boot-3.5.15` 源码、`databases/spring-boot-3-db` CodeQL 数据库、现有 Phase 3 查询、项目内 `skills/java-web-dos-hunter`，以及本地 `.build-cache` 中的 Spring Framework 6.2.19 `spring-web` / `spring-webflux` 依赖 jar。
- 对后续工作的影响：后续可将 WebFlux multipart 默认无限边界和 Observation `client.name` tag cardinality patterns 补进 Spring Boot 3 专项 CodeQL 查询；如果允许动态验证，可优先验证 reactive multipart 默认配置在受控临时目录和小磁盘配额下的增长曲线。
- 破坏性变更：无；仅新增 ignored 本地静态结果和报告，未修改 analyzer 代码、ranking、pipeline 或 verdict 语义。

---

## [2026-06-21] Micronaut 静态资源耗尽 DoS 挖掘

### 修改时间
2026-06-21 22:12

### 变更类型
- [文档] 静态挖掘报告
- [新增功能] Micronaut static-hunt 结果归档

### 核心改动
- 对 Micronaut Core `v3.10.8` 的 `http-server-netty`、`http-client`、`session`、`router`、`management`、`websocket` 等模块完成只静态资源耗尽 DoS 审计。
- 发现三个保留候选：HTTP client `RequestKey` connection pool cardinality、in-memory session active count、multipart/form parser request-burst pressure。
- 明确利用条件：Micronaut core 默认没有低信任入口直连这些 sink；HTTP client 候选需要应用将入站参数映射为出站 absolute URI，session 候选需要开放 session-creating route 且未配置 `maxActiveSessions`，multipart 候选默认 bounded，仅配置抬高边界后成立。
- 运行 Micronaut-only generic Phase 3 与 parser Phase 3 CodeQL 交叉检查，均为 0 data rows，结果保存在 `results/static_hunts/`，不覆盖全量 Phase 3 baseline。

### 交付成果
- 新增报告：`results/static_hunts/micronaut_static_hunt_2026-06-21.md`
- 新增 findings：`results/static_hunts/micronaut_static_findings_2026-06-21.csv`
- 新增 inventory：`results/static_hunts/micronaut_static_inventory_2026-06-21.jsonl`
- 新增 rejected/noise：`results/static_hunts/micronaut_static_rejected_2026-06-21.csv`
- 新增 CodeQL 交叉检查输出：`results/static_hunts/micronaut_phase3_candidate_features.bqrs`、`results/static_hunts/micronaut_phase3_candidate_features.csv`、`results/static_hunts/micronaut_parser_candidate_features.bqrs`、`results/static_hunts/micronaut_parser_candidate_features.csv`

### 依赖与影响
- 依赖：Micronaut build-extraction CodeQL 数据库 `databases/micronaut-3-db` 与源码 `frameworks/micronaut-core-3.10.8`。
- 对后续工作的影响：后续可补 Micronaut 专项 CodeQL 查询，优先寻找 inbound source 到 outbound `DefaultHttpClient` / `ProxyHttpClient` absolute URI 的应用路径，以及开放 session creation route 的配置证明。
- 破坏性变更：无；未修改 CodeQL 查询、ranking、verdict、pipeline 或动态验证 harness。

---

## [2026-06-21] Vert.x 静态资源耗尽挖掘

### 修改时间
2026-06-21 22:13

### 变更类型
- [文档] 静态挖掘报告
- [功能改进] static-hunt 证据归档

### 核心改动
- 使用 `java-web-dos-hunter` workflow 对 Vert.x 4.5.28 进行只静态资源耗尽型 DoS 挖掘，覆盖 `vert.x` core HTTP、`vertx-web` handler/session/SockJS、`vertx-web-client` cache/session/cookie 和 `vertx-web-proxy`。
- 将 `BodyHandler` multipart 上传文件默认留存、SockJS attacker-chosen session id map、`CachingWebClient` 无容量 cache/variation registry 作为主候选，并分别标注利用条件、容量边界、生命周期和后续动态探针计划。
- 明确降级/拒绝项：普通 `SessionHandler` 匿名 session、`StaticHandler` LRU cache、EventBus bridge reply map、CSRF token、WebClient CookieStore 和 core HttpClient endpoint pool，避免后续重复追踪低证据噪声。
- 归档 Vert.x Phase 3 空结果到 `results/static_hunts`，作为通用查询暂未覆盖本轮 Vert.x 静态候选的交叉检查证据。

### 交付成果
- 新增报告：`results/static_hunts/vertx_static_hunt_2026-06-21.md`
- 新增发现表：`results/static_hunts/vertx_static_findings_2026-06-21.csv`
- 新增库存/拒绝项：`results/static_hunts/vertx_static_inventory_2026-06-21.jsonl`
- 归档交叉检查：`results/static_hunts/vertx_phase3_candidate_features.csv`、`results/static_hunts/vertx_phase3_candidate_features.bqrs`
- 验证：仅静态挖掘，未执行动态验证；运行 `python3 scripts/check_phase3_consistency.py` 和 `python3 scripts/check_web_real_regression.py`。

### 依赖与影响
- 依赖：Vert.x 4.5.28 build extraction 数据库和本地源码快照；现有 Phase 3 通用查询仅作交叉检查。
- 对后续工作的影响：`VERTX-STATIC-0001` 可优先进入隔离 disk-fill/cleanup 动态验证；`VERTX-STATIC-0002` 需要并发/timeout 量化；`VERTX-STATIC-0003` 需要具体应用 proxy/SSRF-like source-to-sink 证明。
- 破坏性变更：无；未修改 CodeQL、ranking、verdict、pipeline 或动态验证逻辑。

---

## [2026-06-21] WEB-REAL 利用难度标注与 Static-Hunt 提升

### 修改时间
2026-06-21 20:25

### 变更类型
- [功能改进] WEB-REAL catalog
- [文档] 利用条件标注
- [测试] 回归门禁

### 核心改动
- 将 `TOMCAT-STATIC-0003`、`JETTY-STATIC-0002`、`JETTY-STATIC-0004` 提升为稳定 `WEB-REAL-0007`、`WEB-REAL-0008`、`WEB-REAL-0009`，并在 dynamic runner 中保留旧 static ID 到新 WEB-REAL ID 的别名。
- 为所有 `WEB-REAL-*` 在 `intel/regression/web_real_manifest.json` 中新增 `exploitability`，统一记录 `difficulty`、`default_exploitable`、`preconditions`、`limiting_factors` 和 `rationale`。
- 明确高条件样例不能按默认可利用表述：Tomcat dead properties 要求 `readonly=false` 且 PROPPATCH 可达；Jetty push cache 两项要求显式部署 push filter 并具备 HTTP/2 / non-null `PushBuilder` 环境。
- 扩展 WEB-REAL 回归脚本，允许 `phase3_regression=dynamic_only_pending_query` 的动态已确认项进入 catalog，同时不把暂未进入 Phase 3 查询覆盖的 0007-0009 计为 Phase 3 missing。

### 交付成果
- 修改 runner：`scripts/run_dynamic_verification.py`
- 修改回归脚本：`scripts/check_web_real_regression.py`
- 修改 manifest：`intel/regression/web_real_manifest.json`
- 更新测试：`tests/test_run_dynamic_verification.py`、`tests/test_web_real_catalog.py`、`tests/test_web_real_regression.py`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 本地 ignored 摘要：`results/phase4/verified_vulnerabilities.json`、`results/phase4/verified_vulnerabilities.md`

### 依赖与影响
- 依赖：上一轮 static-hunt 真实 HTTP OOM 日志与 probe。
- 对后续工作的影响：后续论文或披露材料应引用 manifest 中的 `exploitability`，不要把 context-constrained confirmed case 写成默认开放漏洞；Phase 3 查询仍需后续补齐 0007-0009 的静态覆盖。
- 破坏性变更：`check_web_real_regression.py` 输出新增 `phase3_regression_cases` 和 `dynamic_only_pending_query` 统计字段。

---

## [2026-06-21] Static-Hunt 真实 HTTP 动态验证实现

### 修改时间
2026-06-21 19:35

### 变更类型
- [新增功能] 动态验证 harness
- [功能改进] static-hunt runner 输出隔离
- [文档] 验证结果记录

### 核心改动
- 为 `scripts/run_dynamic_verification.py` 新增 `--suite static-hunt` 模式，static-hunt 候选 registry、日志目录和 summary 与现有 `WEB-REAL-*` 动态验证证据分离。
- 新增 Tomcat WebDAV dead-property、Jetty `PushSessionCacheFilter`、Jetty `PushCacheFilter` 和 Undertow multipart 四类真实 HTTP probe，统一输出 `candidate_id`、`status`、`verdict`、请求数、保留指标和日志路径。
- 继续执行严格真阳性门槛：只有真实 HTTP 请求驱动服务 JVM heap OOM 才标记 `verified`；非 OOM、cleanup、bounded 或 request-burst 证据保留为 `not_verified`。
- Jetty push cache probe 在 embedded harness 中包装 push-capable request，用于覆盖 `PushBuilder` 存在的 servlet 环境；日志显式记录该模式。
- Undertow multipart probe 记录默认 `MAX_PARAMETERS=1000`、配置后的 bounded stress、temp file 指标和 cleanup 状态，最终未提升为真阳性。

### 交付成果
- 修改 runner：`scripts/run_dynamic_verification.py`
- 新增 probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/TomcatWebdavDeadPropertiesHttpProbe.java`
- 新增 probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/JettyPushSessionCacheHttpProbe.java`
- 新增 probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/JettyPushCacheFilterHttpProbe.java`
- 新增 helper：`dynamic-verification/src/main/java/org/example/dos/dynamic/JettyPushProbeSupport.java`
- 新增 probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/UndertowMultipartHttpProbe.java`
- 修改依赖：`dynamic-verification/pom.xml`
- 更新测试：`tests/test_run_dynamic_verification.py`
- 结果位置：`results/static_hunts/dynamic_verification/static_hunt_dynamic_verification_summary.json` 与 `results/static_hunts/dynamic_verification/logs/*.log`
- 动态验证：已运行 static-hunt smoke suite，`TOMCAT-STATIC-0003`、`JETTY-STATIC-0002`、`JETTY-STATIC-0004`、`UNDERTOW-STATIC-0003` 均为 `completed_without_oom`；随后运行四个 OOM profile。
- OOM verdict：`TOMCAT-STATIC-0003`、`JETTY-STATIC-0002`、`JETTY-STATIC-0004` 达到 `verified` / `CONFIRMED_HEAP_OOM_REAL_HTTP`；`UNDERTOW-STATIC-0003` 保持 `not_verified` / `NOT_VERIFIED_CLEANUP_BOUNDED`。
- 回归验证：`pytest tests/test_run_dynamic_verification.py -q`、`mvn -q -f dynamic-verification/pom.xml -DskipTests package`、`python3 scripts/check_phase3_consistency.py`、`python3 scripts/check_web_real_regression.py` 均已通过。

### 依赖与影响
- 依赖：本地 Maven 依赖可用，Jetty `jetty-servlets` 11.0.15 作为 dynamic harness 依赖加入。
- 对后续工作的影响：`TOMCAT-STATIC-0003`、`JETTY-STATIC-0002`、`JETTY-STATIC-0004` 已具备真实 HTTP heap OOM 证据，可进入后续人工复核和 catalog 提升讨论；`UNDERTOW-STATIC-0003` 当前仅保留为 request-burst / cleanup bounded 证据。
- 破坏性变更：无；不修改 `WEB-REAL-*` catalog，不覆盖 `results/phase4/dynamic_verification/`。

---

## [2026-06-21] Spring Boot 3 / Vert.x / Micronaut Build Mode 建库修正

### 修改时间
2026-06-21 17:50

### 变更类型
- [功能改进] CodeQL 数据库构建
- [文档] 构建流程同步

### 核心改动
- 将新增的 Spring Boot 3.x、Vert.x 4.x、Micronaut 3.x 数据库构建从 buildless 模式切换为 CodeQL build extraction，通过 `--command` 跟踪真实 Gradle/Maven 编译。
- 新增三个构建 helper：Spring Boot 3 先编译可稳定落地的 core 模块；Vert.x 在同一次 CodeQL trace 中编译 `vert.x` core 与 `vertx-web` 的 Web 相关模块；Micronaut 编译 core/context/http/server/client/router/session/management/websocket 等 Web 分析相关模块。
- 将 Gradle/Maven 依赖缓存固定到本仓库 ignored 的 `.build-cache/`，避免受限执行环境写入用户 home，也避免依赖缓存进入 Git。
- 将 Spring Boot 3 和 Micronaut 的 `source_dir` 指向真实上游源码目录；Vert.x 保留 core + web 聚焦组合源码视图作为 CodeQL `--source-root`，避免把 `frameworks/` 下其他框架归入同一个数据库。
- 为 Micronaut 3 build helper 注入 Aliyun plugin/public mirror，并将 Gradle wrapper 从本机不完整的 `gradle-7.5.1-bin.zip` 切到可复用的 `gradle-7.5.1-all.zip` 缓存。
- 扩展框架注册测试，强制新增三类构建目标包含 `--command` 且不再使用 `--build-mode=none`。

### 交付成果
- 修改构建入口：`scripts/build_databases.sh`
- 新增构建 helper：`scripts/codeql_build_spring_boot_3.sh`、`scripts/codeql_build_vertx_4.sh`、`scripts/codeql_build_micronaut_3.sh`
- 更新配置与忽略规则：`config.yaml`、`.gitignore`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 更新测试：`tests/test_framework_registry.py`
- 测试/验证结果：见本次最终回复。

### 依赖与影响
- 依赖：GitHub/Maven Central/Gradle distribution 可访问；本机提供 Java 21 和 Java 17，其中 Micronaut 3 的 Gradle 7.5.1 使用 Java 17 运行。
- 对后续工作的影响：后续刷新这三个数据库会执行真实编译，抽取精度高于 buildless，但耗时和网络依赖更高；若依赖下载失败，应优先检查 `.build-cache/` 和网络代理状态。Spring Boot 3 的 autoconfigure/actuator optional integration 依赖面很宽，本轮先不纳入默认 build-mode 命令，待 Maven/Gradle 缓存或 mirror 稳定后再扩展。Vert.x 的分析源码入口为 build-time 生成的 `frameworks/vertx-4.5.28-build-sources`，真实上游源码仍保留在 `frameworks/vert.x-4.5.28` 与 `frameworks/vertx-web-4.5.28`。
- 破坏性变更：旧的 Spring Boot 3 `frameworks/*-analysis-sources` 聚焦源码视图不再作为新建库配置入口；本地遗留目录可保留但不参与新建库。

---

## [2026-06-21] 静态挖掘动态验证实施计划

### 修改时间
2026-06-21 17:45

### 变更类型
- [文档] 实施计划

### 核心改动
- 将 `docs/superpowers/specs/2026-06-20-static-hunt-dynamic-verification-design.md` 转换为可执行的静态挖掘动态验证实施计划。
- 明确后续实现分为 static-hunt runner 输出隔离、Tomcat WebDAV dead-property probe、Jetty push cache probes、Undertow multipart probe 和最终验证五个任务。
- 保持真阳性门槛不变：只有真实 HTTP 请求触发服务端 JVM heap OOM 才能进入 verified；增长、磁盘填充、request-local buffering 或正常 cleanup 不自动提升为真阳性。
- 明确新增动态结果写入 `results/static_hunts/dynamic_verification/`，不覆盖现有 `WEB-REAL-*` 证据库。

### 交付成果
- 新增实施计划：`docs/superpowers/plans/2026-06-21-static-hunt-dynamic-verification.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次只新增计划文档，未修改 harness、CodeQL、ranking、verdict 或 pipeline 逻辑；已运行文档级格式和项目轻量回归检查，详见本次最终回复。

### 依赖与影响
- 依赖：静态挖掘动态验证设计文档、人工复核规格、现有 `dynamic-verification/` Maven harness 和 `scripts/run_dynamic_verification.py`。
- 对后续工作的影响：下一步应按计划从 Python runner 的 TDD 测试开始实现，随后逐个新增 probe 并执行 smoke/OOM profile。
- 破坏性变更：无；仅新增计划文档和变更日志记录。

---

## [2026-06-20] 静态挖掘候选动态验证设计

### 修改时间
2026-06-20 22:51

### 变更类型
- [文档] 动态验证设计

### 核心改动
- 为 `results/static_hunts/static_hunt_manual_review_spec_2026-06-20.md` 中非 `WEB-REAL-*` 已覆盖候选制定 OOM-first 动态验证设计。
- 明确真阳性门槛：必须由真实 HTTP 请求进入服务端入口，并触发服务端 JVM heap OOM；仅静态路径、资源增长、磁盘填充或正常 cleanup 不足以标记真阳性。
- 将第一批验证范围限定为 `TOMCAT-STATIC-0003`、`JETTY-STATIC-0002`、`JETTY-STATIC-0004`、`UNDERTOW-STATIC-0003`，并要求 `TOMCAT-STATIC-0002` 与 `SB-STATIC-0001` 先做默认边界和可达性预筛。
- 设计独立 static-hunt 动态验证输出目录，避免覆盖现有 `WEB-REAL-*` 动态验证摘要。

### 交付成果
- 新增设计文档：`docs/superpowers/specs/2026-06-20-static-hunt-dynamic-verification-design.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：本次仅写设计文档，未修改 harness、CodeQL、ranking、verdict 或 pipeline 逻辑；后续实现阶段需运行 dynamic-verification Maven 构建、probe smoke/OOM、`python3 scripts/check_phase3_consistency.py` 和 `python3 scripts/check_web_real_regression.py`。

### 依赖与影响
- 依赖：目标人工复核规格、现有 `dynamic-verification/` harness 风格和 `WEB-REAL-*` 证据门槛。
- 对后续工作的影响：后续实现应先做 smoke profile，再做 OOM profile；新增真阳性不会自动入库，必须另行更新 `WEB-REAL-*` catalog。
- 破坏性变更：无；仅新增设计文档和变更日志记录。

---

## [2026-06-20] 静态挖掘候选人工复核规格

### 修改时间
2026-06-20 22:13

### 变更类型
- [文档] 人工复核规格

### 核心改动
- 汇总 `results/static_hunts/` 下 Tomcat、Jetty、Undertow、Jersey、Spring Boot 五个大规模 LLM 静态挖掘报告，整理出 15 个主候选漏洞复核对象。
- 定义统一人工判定口径，包括必填证据、结果枚举、五轴映射、duplicate / WEB-REAL anchor 处理方式和 request-burst 候选的生命周期标注。
- 按 P0/P1/P2 优先级给出每个候选的复核目标、关键检查项和预期判定出口，避免把已动态验证 root cause、request-local burst、app-dependent footgun 和 bounded noise 混在同一结论层。
- 增加 rejected-pattern audit 要求，用于抽查各框架已拒绝项的容量、TTL、LRU、cleanup 或协议边界是否真实存在。

### 交付成果
- 新增人工复核规格：`results/static_hunts/static_hunt_manual_review_spec_2026-06-20.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：后续一致性和 WEB-REAL 回归验证见本次最终回复；本次未执行动态验证，因为该变更只整理人工复核规格，未修改 CodeQL、ranking、verdict 或 pipeline 逻辑。

### 依赖与影响
- 依赖：`results/static_hunts/*_static_hunt_2026-06-20.md`、现有 `WEB-REAL-*` 动态验证目录和项目五轴判定语义。
- 对后续工作的影响：后续人工复核可按该 spec 逐项落地 review note，并将通过复核的新候选推进到专项 CodeQL 查询、Phase 3/4 建模或动态验证。
- 破坏性变更：无；仅新增 ignored 本地结果规格和更新 `CHANGELOG.md`，未修改 analyzer 代码、ranking、pipeline 或 verdict 语义。

---

## [2026-06-20] Spring Boot 3 / Vert.x / Micronaut CodeQL 数据库扩展

### 修改时间
2026-06-20 22:23

### 变更类型
- [功能改进] 框架数据库覆盖扩展
- [文档] 构建流程同步

### 核心改动
- 将 Spring Boot 3.x、Vert.x 4.x、Micronaut 3.x 从后续扩展对象推进为当前可构建分析目标，固定版本为 Spring Boot `v3.5.15`、Vert.x `4.5.28`、Micronaut Core `v3.10.8`。
- 扩展 `scripts/build_databases.sh`，新增 `spring-boot-3`、`vertx`、`micronaut` 三个目标，统一使用 CodeQL buildless 模式生成数据库，降低上游完整构建对本机依赖和发布仓库状态的敏感性。
- Spring Boot 3 目标生成 `frameworks/spring-boot-3.5.15-analysis-sources` 聚焦源码视图，覆盖 core/autoconfigure/actuator 主模块，避免全仓 buildSrc、docs 和大量 smoke tests 拉长 CodeQL 抽取。
- Vert.x 目标同时下载 `eclipse-vertx/vert.x` core 与 `vert-x3/vertx-web`，生成 `frameworks/vertx-4.5.28-analysis-sources` 聚焦源码视图后建库，避免缺失 Router、handler、session 等 Web 层源码。
- 同步 `config.yaml`、Phase 2 数据库列表、legacy Phase 1 Spring Boot 3 路径和 README/AGENTS 运行说明。
- 新增框架注册回归测试，确保后续新增框架不会只更新部分入口。

### 交付成果
- 新增/修改构建入口：`scripts/build_databases.sh`、`scripts/download_frameworks.sh`
- 更新 pipeline 配置：`config.yaml`
- 更新分析脚本注册：`scripts/run_phase2.py`、`scripts/run_phase1.sh`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 新增测试：`tests/test_framework_registry.py`
- 新增本地源码快照：`frameworks/spring-boot-3.5.15`、`frameworks/spring-boot-3.5.15-analysis-sources`、`frameworks/vert.x-4.5.28`、`frameworks/vertx-web-4.5.28`、`frameworks/vertx-4.5.28-analysis-sources`、`frameworks/micronaut-core-3.10.8`
- 新增本地 CodeQL 数据库：`databases/spring-boot-3-db`、`databases/vertx-4-db`、`databases/micronaut-3-db`
- 测试/验证结果：见本次最终回复。

### 依赖与影响
- 依赖：GitHub 可访问对应固定 tag；CodeQL CLI 2.23.8+；Java 21 本地运行环境。
- 对后续工作的影响：Phase 2/3 全量运行会自动看到新数据库，后续需要为 Vert.x/Micronaut 增强 Web entry 和 retained-state 专项建模，以提高非 Servlet/Spring/JAX-RS 风格框架的召回。
- 破坏性变更：无；源码快照和数据库目录保持 ignored，不进入版本库。

---

## [2026-06-20] Undertow 静态资源耗尽 DoS 挖掘

### 修改时间
2026-06-20 21:45

### 变更类型
- [文档] 静态挖掘报告

### 核心改动
- 按 `java-web-dos-hunter` 工作流对 Undertow `2.3.7.Final` 做静态资源耗尽 DoS hunt，覆盖 `LearningPushHandler`、mod_cluster MCMP、multipart parser、path cache、stuck-thread monitor、resource cache、session manager、WebSocket/SSE 和 HTTP/2 state。
- 复核并确认 `LearningPushHandler` per-referer inner map 静态路径，与 `WEB-REAL-0003` / `WEB-P4-0006` 对齐；外层 `LRUCache` 只限制 referer entries，内层 `Map<String,PushedRequest>` 未见容量上限。
- 复核并确认 mod_cluster MCMP registration state 静态路径，与 `WEB-REAL-0004` / `WEB-P4-0010` 对齐；`CONFIG` form data 可驱动 `balancers`、`nodes`、`hosts` 和 context mappings 增长，暴露面依赖 management endpoint 部署配置。
- 将 `MultiPartParserDefinition` 记录为 request-burst heap/temp storage `needs_dynamic_probe` 候选；明确它不是 process-lifetime retained-state finding。
- 将 `PathHandler.cache`、`StuckThreadDetectionHandler`、resource cache、session manager、WebSocket/SSE 和 HTTP/2 stream/priority state 作为 rejected / low-priority patterns 记录，理由是存在 LRU、固定池、max session、timeout、remove、close 或协议 accounting。
- 关键技术决策：只做静态源码审计和现有 CodeQL 交叉检查；不刷新 Phase 3/4 全量 baseline，不执行真实 HTTP 动态 harness。

### 交付成果
- 新增本地静态挖掘报告：`results/static_hunts/undertow_static_hunt_2026-06-20.md`
- 新增静态 findings CSV：`results/static_hunts/undertow_static_findings_2026-06-20.csv`
- 新增 Undertow-only CodeQL 交叉检查输出：`results/static_hunts/undertow_phase3_candidate_features.bqrs`、`results/static_hunts/undertow_phase3_candidate_features.csv`、`results/static_hunts/undertow_learning_push_candidate_features.bqrs`、`results/static_hunts/undertow_learning_push_candidate_features.csv`、`results/static_hunts/undertow_mcmp_candidate_features.bqrs`、`results/static_hunts/undertow_mcmp_candidate_features.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：Undertow-only CodeQL generic Phase 3 query 输出 3 条并全部降级/拒绝；LearningPush 专项 query 输出 1 条并匹配 `UNDERTOW-STATIC-0001`；MCMP 专项 query 输出 2 条并匹配 `UNDERTOW-STATIC-0002`。未运行动态验证，原因是用户明确要求“只静态挖掘”。

### 依赖与影响
- 依赖：本地 `frameworks/undertow-2.3.7` 源码快照 `b7c54c4`、`databases/undertow-2-db` CodeQL 数据库和现有 Phase 3 / Undertow 专项查询。
- 对后续工作的影响：后续可对 multipart request-burst 候选做部署 body-limit 静态审计或隔离动态 probe；也可补充更细的 MCMP context/host registry 专项 CodeQL 输出。
- 破坏性变更：无；仅新增 ignored 本地静态结果和报告，未修改 analyzer 代码、ranking、pipeline 或 verdict 语义。

---

## [2026-06-20] Jersey 静态资源耗尽 DoS 挖掘

### 修改时间
2026-06-20 21:44

### 变更类型
- [文档] 静态挖掘报告

### 核心改动
- 按项目内 `java-web-dos-hunter` 工作流对 Jersey 3.1.3 做静态资源耗尽 DoS hunt，覆盖 OAuth1 server、multipart provider、默认 message body providers、core-server monitoring/async/runtime 和主要 HTTP containers。
- 运行 Jersey-only generic/parser/OAuth Phase 3 CodeQL 交叉检查，确认 generic 查询 0 条数据行，parser 专项 3 条数据行，OAuth 专项 1 条数据行。
- 复核并确认现有 `WEB-REAL-0001` OAuth1 request token map 与 `WEB-REAL-0002` multipart MIME parser 两类静态路径；本轮未重新执行动态验证。
- 新增 app-dependent 静态候选：默认 `FileProvider` 将任意请求实体流写入 `Utils.createTempFile()`，框架层只注册 `deleteOnExit()`，需要具体应用 `File` 实体参数或 `readEntity(File.class)` 路径证明。
- 将 OAuth nonce cache、OAuth helper/admin maps、monitoring queues、sliding-window reservoirs、Broadcaster/ChunkedOutput、request-local property maps 和 response/header copying 作为 rejected / low-priority patterns 记录。
- 关键技术决策：只做静态源码和 CodeQL 交叉检查，不刷新 Phase 3/4 全量 baseline，不执行真实 HTTP 动态 harness。

### 交付成果
- 新增本地静态挖掘报告：`results/static_hunts/jersey_static_hunt_2026-06-20.md`
- 新增静态 findings CSV：`results/static_hunts/jersey_static_findings_2026-06-20.csv`
- 新增 Jersey-only CodeQL 交叉检查输出：`results/static_hunts/jersey_phase3_candidate_features.bqrs`、`results/static_hunts/jersey_phase3_candidate_features.csv`、`results/static_hunts/jersey_parser_candidate_features.bqrs`、`results/static_hunts/jersey_parser_candidate_features.csv`、`results/static_hunts/jersey_oauth_candidate_features.bqrs`、`results/static_hunts/jersey_oauth_candidate_features.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：Jersey-only CodeQL 查询均成功执行并解码；后续一致性和 WEB-REAL 回归验证见本次最终回复。未运行动态验证，原因是用户明确要求“只静态挖掘”。

### 依赖与影响
- 依赖：本地 `frameworks/jersey-3.1.3` 源码、`databases/jersey-3.1-db` CodeQL 数据库、现有 Phase 3 parser/OAuth 查询和项目内 `skills/java-web-dos-hunter`。
- 对后续工作的影响：后续可将 `FileProvider`、`EntityPartReader` 和 `@FormDataParam File` alias patterns 补进 Jersey 专项 CodeQL 查询；如果允许动态验证，可优先验证 `FileProvider` 在受控临时目录和小磁盘配额下的增长曲线。
- 破坏性变更：无；仅新增 ignored 本地静态结果和报告，未修改 analyzer 代码、ranking、pipeline 或 verdict 语义。

---

## [2026-06-20] Spring Boot 静态资源耗尽 DoS 挖掘

### 修改时间
2026-06-20 21:40

### 变更类型
- [文档] 静态挖掘报告

### 核心改动
- 按项目内 `java-web-dos-hunter` 工作流对 Spring Boot 2.7.x 做静态资源耗尽 DoS hunt，覆盖 actuator trace、actuator metrics、WebFlux multipart、Servlet multipart、WebClient metrics 和 WebMvc/WebFlux request instrumentation。
- 运行 Spring Boot-only generic Phase 3 CodeQL 交叉检查，确认输出 2 条候选均来自 `src/test` blocking servlet fixture，生产源码候选为 0。
- 新增高价值静态候选：WebFlux multipart 默认 `maxParts=-1` 与 `maxDiskUsagePerPart=-1` 的 part-count / disk-burst 风险。
- 新增 app-dependent 静态候选：WebClient metrics 默认 `client.name=request.url().getHost()` 进入 `MeterRegistry`，而默认自动配置只对 `uri` tag 安装 100 个值上限；该项需要具体应用入口证明。
- 将 HTTP trace、server metrics、Servlet multipart、long-task timer samples 和 actuator endpoint read operations 作为 rejected/default-bounded patterns 记录，避免误报默认有界路径。
- 关键技术决策：本轮只做静态源码和 CodeQL 交叉检查，不刷新 Phase 3/4 全量 baseline，不执行真实 HTTP 动态 harness。

### 交付成果
- 新增本地静态挖掘报告：`results/static_hunts/spring_boot_static_hunt_2026-06-20.md`
- 新增静态 findings CSV：`results/static_hunts/spring_boot_static_findings_2026-06-20.csv`
- 新增 source/sink inventory：`results/static_hunts/spring_boot_static_inventory_2026-06-20.jsonl`
- 新增 rejected/noise CSV：`results/static_hunts/spring_boot_static_rejected_2026-06-20.csv`
- 新增 Spring Boot-only CodeQL 交叉检查输出：`results/static_hunts/spring-boot_phase3_candidate_features.bqrs`、`results/static_hunts/spring-boot_phase3_candidate_features.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：Spring Boot-only CodeQL generic Phase 3 query 成功执行并解码，输出 2 rows，均为 `src/test` 噪声；`spring_boot_static_inventory_2026-06-20.jsonl` 逐行 JSON 解析通过，10 records；`python3 scripts/check_phase3_consistency.py` 输出 `37/37 matched, pass=True`；`python3 scripts/check_web_real_regression.py` 输出 `6/6 hit, 0 partial, 0 missing`；`git diff --check` 通过。未运行动态验证，原因是用户明确要求“只静态挖掘”。

### 依赖与影响
- 依赖：本地 `frameworks/spring-boot` 2.7.x 源码、`databases/spring-boot-2.7-db` CodeQL 数据库、现有 Phase 3 查询和项目内 `skills/java-web-dos-hunter`。
- 对后续工作的影响：后续可将 WebFlux multipart 和 WebClient metrics tag cardinality patterns 补进 Spring Boot 专项 CodeQL 查询；如果允许动态验证，可优先验证 reactive multipart 默认配置在受控临时目录和小磁盘配额下的增长曲线。
- 破坏性变更：无；仅新增 ignored 本地静态结果和报告，未修改 analyzer 代码、ranking、pipeline 或 verdict 语义。

## [2026-06-20] Tomcat 静态资源耗尽 DoS 挖掘

### 修改时间
2026-06-20 21:09

### 变更类型
- [文档] 静态挖掘报告

### 核心改动
- 按 `java-web-dos-hunter` 工作流对 Tomcat `9.0.x` 做静态资源耗尽 DoS hunt，覆盖 WebDAV、multipart、静态资源 cache、WebSocket、HTTP/2、Form Auth saved request、CSRF nonce 和 SSO cache 等模块。
- 复核并确认现有 `WebdavServlet` LOCK retained lock maps 静态路径，与 `WEB-REAL-0006` / `WEB-P4-0025..0027` 对齐；本轮未重新执行动态验证。
- 新增源码级静态候选：`WebdavServlet.doProppatch` 未复用 `readRequestBody()` 的请求体完整缓冲路径，以及默认 `MemoryPropertyStore.deadProperties` 对 PROPPATCH dead properties 的 process-lifetime retention。
- 将 multipart parser、static resource cache、WebSocket session maps、HTTP/2 stream maps、Form Auth saved request、CSRF nonce cache 和 SSO cache 作为 rejected / low-priority patterns 记录，理由是源码中存在容量、TTL、timeout、LRU、覆盖、unregister 或部署 gate。
- 关键技术决策：只做静态源码和 CodeQL 交叉检查；不刷新 Phase 3/4 全量 baseline，不执行真实 HTTP 动态 harness。

### 交付成果
- 新增本地静态挖掘报告：`results/static_hunts/tomcat_static_hunt_2026-06-20.md`
- 新增静态 findings CSV：`results/static_hunts/tomcat_static_findings_2026-06-20.csv`
- 新增 Tomcat-only CodeQL 交叉检查输出：`results/static_hunts/tomcat_phase3_candidate_features.bqrs`、`results/static_hunts/tomcat_phase3_candidate_features.csv`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：Tomcat-only CodeQL generic Phase 3 query 成功执行并解码，输出 24 rows，其中生产源码候选为 3 条 `WebdavServlet` lock-map rows，其余为 examples/tests 噪声；`python3 scripts/check_phase3_consistency.py` 输出 `37/37 matched, pass=True`；`python3 scripts/check_web_real_regression.py` 输出 `6/6 hit, 0 partial, 0 missing`。未运行动态验证，原因是用户明确要求“只静态挖掘”。

### 依赖与影响
- 依赖：本地 `frameworks/tomcat` 源码快照 `55fdb4f`、`databases/tomcat-9.0-db` CodeQL 数据库和现有 Phase 3 查询。
- 对后续工作的影响：后续可将 `doProppatch` body buffering 与 `MemoryPropertyStore.deadProperties` 候选补进 Tomcat 专项 CodeQL 查询，并在隔离 harness 中选择性验证。
- 破坏性变更：无；仅新增 ignored 本地静态结果和报告，未修改 analyzer 代码、ranking、pipeline 或 verdict 语义。

---

## [2026-06-20] Jetty 静态资源耗尽 DoS 挖掘

### 修改时间
2026-06-20 20:52

### 变更类型
- [文档] 静态挖掘报告

### 核心改动
- 按 `java-web-dos-hunter` 工作流对 Jetty 11.0.15 做静态资源耗尽 DoS hunt，先建立 target profile，再枚举 retained-state sinks、HTTP sources、source-to-sink 路径和拒绝项。
- 复核并确认现有 Jetty `ProxyServlet -> HttpClient.destinations` 静态候选，同时新增源码级静态候选：`PushSessionCacheFilter` 的全局 path cache / per-target association map / session timestamp map，以及 `PushCacheFilter` 的 primary-resource cache。
- 将 `DoSFilter`、`QoSFilter`、session cache internals 和 request-local buffering 作为低优先级或 rejected patterns 记录，理由是存在 timeout、poll/remove、scheduler cleanup、session eviction/scavenging 或 request-local 生命周期约束。
- 关键技术决策：本轮只做静态证据整理，不执行动态 harness，也不修改 CodeQL 查询、ranking、verdict 或 pipeline 逻辑。

### 交付成果
- 新增本地静态挖掘报告：`results/static_hunts/jetty_static_hunt_2026-06-20.md`
- 刷新本地静态结果以恢复全量 baseline：`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase4/`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：`python3 scripts/run_phase3.py --framework jetty` 显示 Jetty generic query 0 rows、Jetty proxy auxiliary query 1 row、Phase 3 consistency 1/1 matched；随后运行 `./dos-web-analyzer analyze --refresh-phase3` 恢复全量结果，输出 37 total candidates、Phase 3 consistency 37/37 matched、Phase 4 ranked 37 candidates。未运行动态验证，原因是用户明确要求“先只静态”。

### 依赖与影响
- 依赖：本地 `frameworks/jetty-11.0.15` 源码、`databases/jetty-11-db` CodeQL 数据库和现有 Phase 3/4 pipeline。
- 对后续工作的影响：后续可将 `PushSessionCacheFilter` / `PushCacheFilter` 候选补进 Jetty 专项 CodeQL 查询，再选择性做真实 HTTP 动态验证。
- 破坏性变更：无；仅新增 ignored 本地报告并刷新 ignored 本地结果，未修改 analyzer 代码或 verdict 语义。

---

## [2026-06-20] Java Web 资源耗尽 DoS 挖掘技能

### 修改时间
2026-06-20 19:15

### 变更类型
- [文档] Agent 技能

### 核心改动
- 新增项目内技能 `java-web-dos-hunter`，用于指导 agent 在 Java Web/HTTP 服务中大规模、证据驱动地挖掘资源耗尽型 DoS。
- 技能与当前 Phase 3/4 analyzer 代码脱钩，不依赖本仓库 CodeQL 库、pipeline 或结果格式；仅沉淀可迁移的 source/sink/flow/verdict 工作流。
- 明确 sink 全量枚举、HTTP source 全量枚举、source-to-sink 关联、真阳性判定、动态验证计划和低强度 subagent 委派纪律。
- 关键技术决策：采用“先清单、再路径、后判定”的 evidence-driven pipeline，避免把局部可增长操作直接误判为可利用漏洞。

### 交付成果
- 新增技能正文：`skills/java-web-dos-hunter/SKILL.md`
- 新增技能 UI 元数据：`skills/java-web-dos-hunter/agents/openai.yaml`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：`python3 /home/furina/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/java-web-dos-hunter` 通过；`grep` 结构检查确认技能包含 Stage 0-5、subagent 纪律、输出报告和真阳性判定字段；使用合成 Java Web 场景做轻量 forward-test，技能能将 Spring singleton registry header-key 增长判为 likely，并拒绝 response-local header copy 与 `maxParts=32` 的 part-count multipart 路径，随后补充 header 值空间、singleton retained-state、multipart 多维度 bound 和 `needs_path_proof` 口径说明。

### 依赖与影响
- 依赖：无运行时依赖；后续 agent 可按技能说明自行选择 `rg`、AST、CodeQL、调用图或 subagent。
- 对后续工作的影响：可作为独立于当前 analyzer 的通用漏洞挖掘流程，用于后续 Java Web/HTTP 框架或服务的大规模资源耗尽 DoS hunting。
- 破坏性变更：无；未修改 analyzer 查询、脚本、pipeline、结果或 verdict 语义。

---

## [2026-06-20] WEB-REAL 私有披露材料准备

### 修改时间
2026-06-20 19:10

### 变更类型
- [文档] 私有漏洞报告材料

### 核心改动
- 新增本地私有披露材料目录 `security-disclosures/`，按 `WEB-REAL-0001` 至 `WEB-REAL-0006` 分别准备上游安全团队报告草稿、附件清单、复跑命令和 CVE 请求措辞。
- 按项目拆分报告入口：Jersey 走 Eclipse/Jersey 安全流程，Undertow 走 Red Hat Product Security，Jetty 走 Jetty Security Team，Tomcat 走 Tomcat Security Team。
- 将每个 `WEB-REAL` 整理为独立目录，内含 `REPORT.md` 与 `attachments/`；附件包括对应 PoC、验证日志和裁剪版 evidence JSON。
- 清理报告与 evidence JSON 中的内部结果目录引用，统一改为 `attachments/...` 相对路径，便于直接打包提交给上游安全团队。
- 将 `security-disclosures/` 加入 `.gitignore`，避免 PoC 附件、日志摘要、厂商往来和未公开漏洞细节误入版本库。
- 关键技术决策：报告正文使用英文，便于直接提交给上游；本地步骤和注意事项使用中文，便于后续执行和复核。

### 交付成果
- 新增本地忽略目录：`security-disclosures/`
- 新增私有披露 runbook：`security-disclosures/README.md`
- 新增 6 份本地报告草稿：`security-disclosures/WEB-REAL-0001-jersey-oauth1-request-token-map/REPORT.md` 至 `security-disclosures/WEB-REAL-0006-tomcat-webdav-lock-maps/REPORT.md`
- 新增 6 组本地附件目录：每组 `attachments/` 包含 PoC、日志和 `evidence-WEB-REAL-*.json`
- 修改忽略规则：`.gitignore`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：`git check-ignore -v security-disclosures/README.md` 确认命中 `.gitignore:18:security-disclosures/`；`git check-ignore -v security-disclosures/WEB-REAL-0001-jersey-oauth1-request-token-map/attachments/JerseyOAuth1HttpProbe.java` 确认附件也被忽略；`rg -n "results/phase4" security-disclosures` 无匹配；附件引用存在性校验通过；`jq -e . security-disclosures/WEB-REAL-*/attachments/evidence-WEB-REAL-*.json` 通过；`git status --short --ignored security-disclosures .gitignore CHANGELOG.md` 显示披露目录为 ignored，仅 `.gitignore` 与 `CHANGELOG.md` 为可跟踪变更；`python3 scripts/check_phase3_consistency.py` 输出 `37/37 matched, pass=True`；`python3 scripts/check_web_real_regression.py` 输出 `6/6 hit, 0 partial, 0 missing`。

### 依赖与影响
- 依赖：当前 `results/phase4/verified_vulnerabilities.json`、动态验证 PoC 和日志作为证据来源。
- 对后续工作的影响：后续向上游报告时可直接从本地私有目录复制正文并附对应 PoC/log；发送前仍应按报告内命令复跑对应 case。
- 破坏性变更：无；新增披露材料目录被 Git 忽略，不会进入公开版本历史。

---

## [2026-06-20] 真实 HTTP 动态验证 harness 与 WEB-REAL-0006 入库

### 修改时间
2026-06-20 18:19

### 变更类型
- [新增功能] 真实 HTTP 动态验证 harness
- [功能改进] WEB-REAL 动态证据刷新
- [文档] 验证结果记录

### 核心改动
- 新增 `dynamic-verification/` Maven 项目，使用真实本地 HTTP server/request 路径复现 Jersey、Undertow、Jetty 和 Tomcat retained-state DoS 行为。
- 新增 `scripts/run_dynamic_verification.py`，支持 `smoke` 与 `oom` profile、单 case 选择、受控 JVM 堆和统一日志/summary 输出。
- 将 `WEB-REAL-0001`、`WEB-REAL-0002`、`WEB-REAL-0004` 从 direct/半 direct harness 补齐为真实 HTTP 入口验证；保留旧默认堆日志作为对照。
- 新增 `WEB-REAL-0006` Tomcat `WebdavServlet` 真实 WebDAV `LOCK` 验证，覆盖 `WEB-P4-0025` 的 `sharedLocks` token put，以及 `WEB-P4-0026`、`WEB-P4-0027` 的 `resourceLocks` path put。
- 将 Tomcat WebDAV 从 Phase4 补充证据提升为正式 WEB-REAL catalog 条目，并在 `intel/regression/web_real_manifest.json` 中加入静态回归规则。
- runner 会识别服务线程日志中的 `java.lang.OutOfMemoryError: Java heap space`，用于处理 Jersey/Grizzly 等容器在线程内吞掉 OOM、main 线程只看到客户端写失败的真实 HTTP 场景。
- 关键技术决策：OOM profile 使用 384MiB 受控堆，降低对本机默认大堆和系统资源的依赖；结果日志记录 `maxHeapBytes`，需要默认堆复现实验时可用同一 harness 调整 `--heap` 重跑。

### 交付成果
- 新增 Maven harness：`dynamic-verification/pom.xml`
- 新增 Java probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/JerseyOAuth1HttpProbe.java`
- 新增 Java probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/JerseyMultipartHttpProbe.java`
- 新增 Java probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/UndertowLearningPushHttpProbe.java`
- 新增 Java probe：`dynamic-verification/src/main/java/io/undertow/server/handlers/proxy/mod_cluster/UndertowModClusterHttpProbe.java`
- 新增 Java probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/JettyProxyServletHttpProbe.java`
- 新增 Java probe：`dynamic-verification/src/main/java/org/example/dos/dynamic/TomcatWebdavLocksHttpProbe.java`
- 新增 runner 与测试：`scripts/run_dynamic_verification.py`、`tests/test_run_dynamic_verification.py`
- 更新文档：`README.md`、`AGENTS.md`、`CHANGELOG.md`
- 更新本地结果：`results/phase4/dynamic_verification/dynamic_verification_summary.json`、`results/phase4/dynamic_verification/logs/*real-http*.log`、`results/phase4/verified_vulnerabilities.json`、`results/phase4/verified_vulnerabilities.md`
- 测试/验证结果：`pytest tests/test_run_dynamic_verification.py tests/test_web_real_catalog.py -q` 8 passed；`mvn -q -DskipTests package dependency:build-classpath -Dmdep.outputFile=target/classpath.txt` 通过；`python3 scripts/run_dynamic_verification.py --profile smoke --heap 384m --port-base 28800` 覆盖 6/6 case；`python3 scripts/run_dynamic_verification.py --profile oom --heap 384m --port-base 28900` 输出 6/6 `verified (CONFIRMED_HEAP_OOM_REAL_HTTP)`；`python3 scripts/check_phase3_consistency.py` 输出 `37/37 matched`；`python3 scripts/check_web_real_regression.py` 输出 `6/6 hit`。

### 依赖与影响
- 依赖：Maven、Java 17+，以及 Maven Central 可下载 Tomcat 9.0.106、Jersey 3.1.3、Undertow 2.3.7.Final、Jetty 11.0.15 依赖。
- 对后续工作的影响：后续论文 RQ4 和漏洞报告可用真实 HTTP harness 复跑，不再依赖临时 direct harness；Tomcat WebDAV 0025~0027 已从 pending 复核候选升级为 `WEB-REAL-0006`。
- 破坏性变更：无；`dynamic-verification/target/` 为本地构建/运行产物并已忽略。

---

## [2026-06-20] 旧文档与旧结果清理

### 修改时间
2026-06-20 11:04

### 变更类型
- [文档] 清理记录
- [功能改进] 本地结果目录维护

### 核心改动
- 清理过时的 `docs/superpowers/` 设计/计划过程文档，仅保留当前核心设计文档 `docs/drd_inspired_rearchitecture_plan.md`。
- 清理旧 Phase 1/2 结果、临时 test 查询结果，以及 Phase 3 单框架/辅助查询的中间 BQRS 和 CSV。
- 保留最新权威产物：Phase 3 合并候选、一致性报告、WEB-REAL 回归结果、Phase 4 排序/复核队列/评估摘要、已验证漏洞库、动态验证 PoC 和日志。
- 同步更新 `AGENTS.md`，修正当前全量框架、运行命令、保留产物、WEB-REAL Phase4 ID 和清理约束。
- 关键技术决策：只删除可再生成的旧中间产物和过程文档，不删除框架源码、CodeQL 数据库、查询、脚本、已验证漏洞证据或最新 Phase 3/4 汇总结果。

### 交付成果
- 删除旧文档目录：`docs/superpowers/`
- 删除旧结果：`results/phase1/`、`results/phase2/`、`results/phase1_report.md`、`results/phase2_report.md`、`results/test_*.bqrs`、`results/test_*.csv`
- 删除 Phase 3 中间结果：`results/phase3/*_candidate_features.bqrs`、`results/phase3/*_candidate_features.csv`（保留 `phase3_candidate_features.csv`）
- 保留最新结果：`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase3/web_real_regression.json`、`results/phase3_report.md`、`results/phase4/`
- 修改文档：`AGENTS.md`、`CHANGELOG.md`
- 测试/验证结果：`find docs -maxdepth 4 -type f` 仅显示核心设计文档；`find results -maxdepth 5 -type f` 仅显示最新 Phase 3/4 汇总产物、verified vulnerabilities、PoC 和日志；`python3 scripts/check_phase3_consistency.py` 输出 `Phase 3 consistency: 1.000 (37/37 matched), pass=True`；`python3 scripts/check_web_real_regression.py` 输出 5/5 hit。

### 依赖与影响
- 依赖：2026-06-20 10:49 全量 Web 分析结果刷新已经完成。
- 对后续工作的影响：结果目录更聚焦，后续复核默认从最新 Phase 3/4 汇总和 WEB-REAL 证据开始；若需要旧 Phase 1/2 或单框架中间 CSV，可通过现有 CLI/脚本重新生成。
- 破坏性变更：删除 ignored 本地旧结果和过程文档；未删除源码、数据库、动态验证证据或最新权威汇总结果。

---

## [2026-06-20] 全量 Web 分析结果刷新

### 修改时间
2026-06-20 10:49

### 变更类型
- [文档] 全量分析运行记录

### 核心改动
- 使用当前统一 CLI 对 `config.yaml` 中登记的 Tomcat、Spring Boot、Jetty、Undertow、Jersey 五个 Web 框架重新运行 Phase 3/4 分析链路。
- 重新生成 Phase 3 候选合并结果、verdict 一致性报告、Phase 4 排序候选、top-50 复核队列和评估摘要。
- 关键技术决策：本轮只刷新分析产物和运行记录，不修改 CodeQL 查询、ranking 权重、verdict 语义或 pipeline 逻辑；`results/` 仍作为 ignored 本地产物保留。

### 交付成果
- 重新生成结果：`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase3_report.md`
- 重新生成结果：`results/phase4/ranked_candidates.csv`、`results/phase4/ranked_candidates.json`、`results/phase4/review_queue_top50.md`、`results/phase4/review_queue_top50.json`、`results/phase4/evaluation_summary.json`、`results/phase4_report.md`
- 更新回归结果：`results/phase3/web_real_regression.json`
- 修改文档：`CHANGELOG.md`
- 测试/验证结果：`./dos-web-analyzer analyze --refresh-phase3` 生成 37 条候选，Phase 3 consistency 37/37 matched；`./dos-web-analyzer report` 和 `./dos-web-analyzer verify --top 50` 正常刷新 Phase 4 产物；`python3 scripts/check_phase3_consistency.py` 输出 `Phase 3 consistency: 1.000 (37/37 matched), pass=True`；`python3 scripts/check_web_real_regression.py` 与 `python3 scripts/check_web_real_coverage.py` 均为 5/5 hit；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过 288 个积格点；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 输出 `OK: 0 regression(s)`。

### 依赖与影响
- 依赖：当前本地 CodeQL 数据库和 `config.yaml` 中登记的五个框架数据库。
- 对后续工作的影响：复核队列和评估摘要已同步到最新 Phase 3/4 结果，可直接用于人工复核和论文统计。
- 破坏性变更：无。

---

## [2026-06-20] 第三部分 WEB-REAL 回归门禁实现

### 修改时间
2026-06-20 00:38

### 变更类型
- [新增功能] WEB-REAL manifest 回归门禁
- [功能改进] WEB-REAL coverage 兼容入口
- [文档] 回归验证记录

### 核心改动
- 新增 `intel/regression/web_real_manifest.json`，将 5 个已动态验证真阳的静态期望从 Python lambda 迁移到可审计 manifest。
- 新增 `scripts/check_web_real_regression.py`，支持 `equals`、`contains`、`one_of` 规则，输出 `hit`、`partial`、`missing` 和机器可读 JSON 报告。
- 将 `scripts/check_web_real_coverage.py` 改为兼容 wrapper，保留现有命令入口并委托给新 regression checker。
- 加强 manifest、输入 CSV 和输出报告路径的错误处理，确保 CLI 对预期 I/O 和 manifest 错误返回 exit 2 且不泄露 traceback。
- 关键技术决策：本轮只固定 known-vuln regression gate，不改变 Phase 4 排序权重或 CodeQL 查询；`results/` 仍按当前仓库策略作为 ignored 本地产物保留。

### 交付成果
- 新增 manifest：`intel/regression/web_real_manifest.json`
- 新增脚本：`scripts/check_web_real_regression.py`
- 修改脚本：`scripts/check_web_real_coverage.py`
- 生成结果：`results/phase3/web_real_regression.json`（ignored 本地产物，未提交）
- 重新生成结果：`results/phase3/phase3_consistency.json`、`results/phase4/`、`results/phase4_report.md`（ignored 本地产物，未提交）
- 修改文档：`CHANGELOG.md`
- 测试/验证结果：`python3 scripts/check_web_real_regression.py` 5/5 hit，0 partial，0 missing；`python3 scripts/check_web_real_coverage.py` 5/5 hit，0 partial，0 missing；`python3 scripts/check_phase3_consistency.py` 输出 `Phase 3 consistency: 1.000 (37/37 matched), pass=True`；`./dos-web-analyzer analyze` 输出 `Phase 4 complete: 37 candidates, top 37 queued, outputs under results/phase4`；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过 288 个积格点；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 输出 `OK: 0 regression(s)`。

### 依赖与影响
- 依赖：当前 Phase 3 proof/request-flow schema、5/5 WEB-REAL smoke hit 基线，以及 AOSP 侧权威 verdict 模型。
- 对后续工作的影响：Phase 4 evaluation summary、capacity/lifespan proof 和 Dr.D compatibility manifest 可复用该 regression report 结构。
- 破坏性变更：无；旧 coverage 命令仍可使用。

---

## [2026-06-19] 隔离 worktree 忽略规则

### 修改时间
2026-06-19 23:16

### 变更类型
- [功能改进] 仓库维护
- [文档] 忽略规则

### 核心改动
- 将项目内 `.worktrees/` 加入 `.gitignore`，用于后续按 subagent-driven 流程创建隔离实现工作区。
- 关键技术决策：worktree 目录只承载本地执行环境，不作为项目源码或可复现实验产物版本化。
- 影响范围仅限仓库忽略规则和变更日志。

### 交付成果
- 修改忽略规则：`.gitignore`
- 修改文档：`CHANGELOG.md`
- 测试/验证结果：仓库维护变更，未运行 CodeQL、Phase 3/4 pipeline 或 AOSP regression。

### 依赖与影响
- 依赖：`superpowers:using-git-worktrees` 要求项目内 worktree 目录必须被忽略。
- 对后续工作的影响：允许在 `.worktrees/` 下创建隔离分支执行 WEB-REAL regression gate 实现。
- 破坏性变更：无。

---

## [2026-06-19] 仓库忽略规则与生成产物清理

### 修改时间
2026-06-19 22:37

### 变更类型
- [功能改进] 仓库维护
- [文档] 忽略规则

### 核心改动
- 扩展 `.gitignore`，递归忽略 `frameworks/`、`databases/`、`results/`、`docs/superpowers/` 以及本地数据/临时分析产物。
- 将已跟踪的结果产物和 agent 流程文档从 Git 索引移除但保留本地文件，避免后续提交混入可再生成数据。
- 保留 `README.md`、`CHANGELOG.md`、`AGENTS.md` 和 `docs/drd_inspired_rearchitecture_plan.md` 作为核心项目文档继续纳入版本控制。

### 交付成果
- 修改忽略规则：`.gitignore`
- 修改文档：`CHANGELOG.md`
- 从索引移除：`results/`、`docs/superpowers/`
- 测试/验证结果：仓库维护变更，未运行 CodeQL、Phase 3/4 pipeline 或 AOSP regression。

### 依赖与影响
- 依赖：当前工作区已有多轮 Phase 1-4 结果与 agent 设计/计划文档。
- 对后续工作的影响：后续提交默认只包含源码、脚本、配置和核心说明文档；结果产物仍保留在本地用于复核和复现实验。
- 破坏性变更：无；未删除本地结果文件。

---

## [2026-06-19] 第三部分 WEB-REAL 回归门禁实施计划

### 修改时间
2026-06-19 22:12

### 变更类型
- [文档] 实施计划

### 核心改动
- 使用 writing-plans 将已批准的 WEB-REAL regression gate 设计拆成可执行任务。
- 明确新增 manifest、通用 checker、coverage 兼容 wrapper、验证和 changelog 更新的实施顺序。
- 计划采用 manifest 驱动的 `hit` / `partial` / `missing` 判定，第一轮保持 Phase 4 排序不变。
- 关键技术决策：现有项目没有 Python 单测框架，本计划使用临时 fixture/真实 Phase 3 CSV 加 CLI 断言完成 TDD 式验证。

### 交付成果
- 新增实施计划：`docs/superpowers/plans/2026-06-19-web-real-regression-gate.md`
- 修改文档：`CHANGELOG.md`
- 测试/验证结果：文档变更，未运行 CodeQL、Phase 3/4 pipeline 或 AOSP regression。

### 依赖与影响
- 依赖：`docs/superpowers/specs/2026-06-19-web-real-regression-gate-design.md` 已通过用户 review。
- 对后续工作的影响：下一步可按计划使用 subagent-driven 或 inline execution 落地第三部分第一轮实现。
- 破坏性变更：无。

---

## [2026-06-19] 第三部分 WEB-REAL 回归门禁设计

### 修改时间
2026-06-19 22:01

### 变更类型
- [文档] 第三部分回归基准设计

### 核心改动
- 使用 brainstorming 梳理 `docs/drd_inspired_rearchitecture_plan.md` 第三部分的启动方式，确认第一轮采用回归门禁优先路线。
- 明确将现有 `scripts/check_web_real_coverage.py` 的 hard-coded smoke check 升级为 manifest 驱动的 known-vuln regression gate。
- 设计 `intel/regression/web_real_manifest.json`、`scripts/check_web_real_regression.py`、`results/phase3/web_real_regression.json` 的职责边界和判定语义。
- 关键技术决策：第一轮只固定 5 个 `WEB-REAL-*` 的静态覆盖事实，不同时重写 Phase 4 排序或生成完整 validation recipe，避免扩大范围。

### 交付成果
- 新增设计文档：`docs/superpowers/specs/2026-06-19-web-real-regression-gate-design.md`
- 修改文档：`CHANGELOG.md`
- 测试/验证结果：文档变更，未运行 CodeQL、Phase 3/4 pipeline 或 AOSP regression。

### 依赖与影响
- 依赖：第一部分 proof-carrying schema、第二部分 bridge 覆盖和当前 `python3 scripts/check_web_real_coverage.py` 5/5 hit 基线。
- 对后续工作的影响：下一步可按该设计新增 manifest 和 checker，并把 WEB-REAL smoke 升级为第三部分正式回归门禁。
- 破坏性变更：无。

---

## [2026-06-19] 第二部分 Jetty ProxyServlet Bridge 接入

### 修改时间
2026-06-19 21:40

### 变更类型
- [新增功能] Jetty ProxyServlet / HttpClient destination bridge 查询
- [功能改进] WEB-REAL 静态覆盖 smoke
- [文档] 第一/二部分状态复核

### 核心改动
- 使用 brainstorming 复核 `docs/drd_inspired_rearchitecture_plan.md` 第一/二部分与当前实现，确认剩余核心缺口是 `WEB-REAL-0005` Jetty ProxyServlet / HttpClient destination map 路径。
- 新增 `codeql/lib/JettyRetention.qll`，建模 `ProxyServlet.service -> newProxyRequest/sendProxyRequest -> HttpClient.resolveDestination -> destinations.compute`。
- 新增 `codeql/queries/phase3_jetty_proxy_candidate_features.ql`，通过 Phase 3 auxiliary query 输出 `candidate_family=client_destination`、`request_flow_kind=client_request_flow`、`growth_driver_kind=origin_key` 和 `receiver_proof=servlet_field:AbstractProxyServlet._client -> HttpClient.destinations`。
- 新增 `scripts/check_web_real_coverage.py`，将 5 个已动态验证真阳作为轻量静态 coverage smoke；实现前该检查仅缺 `WEB-REAL-0005`，实现后 5/5 hit。
- 更新 `docs/drd_inspired_rearchitecture_plan.md` 和 `README.md`，说明当前通用 `RequestFlow.qll` 仍只覆盖 direct/one-hop，跨组件真实路径暂由 Jersey/OAuth、Jersey/parser、Undertow 和 Jetty 窄 bridge 承担，最新 Phase 3 基线为 37 条候选。

### 交付成果
- 新增设计/计划记录：`docs/superpowers/specs/2026-06-19-jetty-proxy-bridge-design.md`、`docs/superpowers/plans/2026-06-19-jetty-proxy-bridge.md`
- 新增 CodeQL 库：`codeql/lib/JettyRetention.qll`
- 新增查询：`codeql/queries/phase3_jetty_proxy_candidate_features.ql`
- 新增脚本：`scripts/check_web_real_coverage.py`
- 修改配置与文档：`config.yaml`、`README.md`、`docs/drd_inspired_rearchitecture_plan.md`、`CHANGELOG.md`
- 更新结果：`results/phase3/jetty_proxy_candidate_features.csv`、`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase3_report.md`、`results/phase4/`、`results/phase4_report.md`
- 测试/验证结果：`python3 scripts/check_web_real_coverage.py` 在实现前缺 `WEB-REAL-0005`，实现后 5/5 hit；`python3 scripts/run_phase3.py --framework jetty` 生成 1 条 Jetty `client_destination` 候选；`python3 scripts/run_phase3.py` 生成 37 条候选，Phase 3 consistency 37/37 matched；`./dos-web-analyzer analyze` 生成 37 条 Phase 4 候选；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过 288 个积格点；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression(s)。

### 依赖与影响
- 依赖：Phase 3 auxiliary query 合并机制、第一部分 proof-carrying schema 和第二部分已接入的 parser/provider/listener bridge 模式。
- 对后续工作的影响：5 个 `WEB-REAL-*` 已全部有静态 coverage smoke 命中；第三部分可将该 smoke 升级为正式 regression manifest，并把专用 bridge 中可复用的 bounded multi-hop/client request flow 上沉到通用 `RequestFlow.qll`。
- 破坏性变更：无；Phase 3 schema 未新增字段，只新增 Jetty auxiliary query 结果和 coverage smoke 脚本。

---

## [2026-06-19] 第二部分 Undertow LearningPush/MCMP Bridge 接入

### 修改时间
2026-06-19 21:14

### 变更类型
- [新增功能] Undertow listener/management bridge 查询
- [功能改进] WEB-REAL 静态覆盖
- [文档] 运行基线更新

### 核心改动
- 使用 brainstorming 继续推进第二部分，按只读源码复核结果补入 Undertow `LearningPushHandler` completion listener 和 MCMP management endpoint 两类真实路径。
- 新增 `codeql/lib/UndertowRetention.qll`，建模 `LearningPushHandler.handleRequest -> PushCompletionListener.exchangeEvent -> pushes.put(fullPath, ...)`，以及 `MCMPHandler.handleRequest/processConfig -> ModClusterContainer.addNode -> balancers/nodes.put`。
- 新增 `codeql/queries/phase3_undertow_learning_push_candidate_features.ql` 和 `codeql/queries/phase3_undertow_mcmp_candidate_features.ql`，通过 Phase 3 auxiliary query 机制输出 `candidate_family=listener_state` 与 `candidate_family=management_state`。
- LearningPush 候选显式区分外层 bounded `LRUCache` 和内层 per-referer unbounded map；MCMP 候选输出 `mcmp_management_endpoint_exposed` 部署条件，并落到 `ModClusterContainer.balancers/nodes` 的真实 retained map 行号。

### 交付成果
- 新增 CodeQL 库：`codeql/lib/UndertowRetention.qll`
- 新增查询：`codeql/queries/phase3_undertow_learning_push_candidate_features.ql`、`codeql/queries/phase3_undertow_mcmp_candidate_features.ql`
- 修改配置与文档：`config.yaml`、`README.md`、`CHANGELOG.md`
- 更新结果：`results/phase3/undertow_learning_push_candidate_features.csv`、`results/phase3/undertow_mcmp_candidate_features.csv`、`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase3_report.md`、`results/phase4/`、`results/phase4_report.md`
- 测试/验证结果：`python3 scripts/run_phase3.py --framework undertow` 生成 6 条 Undertow 候选，其中 LearningPush 1 条、MCMP 2 条；`python3 scripts/run_phase3.py` 生成 36 条候选，Phase 3 consistency 36/36 matched；`./dos-web-analyzer analyze` 生成 36 条 Phase 4 候选，LearningPush 为 `WEB-P4-0005`，MCMP 为 `WEB-P4-0008`/`WEB-P4-0009`；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过 288 个积格点；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression(s)。

### 依赖与影响
- 依赖：Phase 3 auxiliary query 合并机制和第一部分 proof-carrying schema。
- 对后续工作的影响：已覆盖 `WEB-REAL-0003`、`WEB-REAL-0004` 的静态候选入口；后续仍需补 Jetty ProxyServlet / HttpClient destination flow，以及把部分专用 bridge 上沉为通用 bounded callback/multi-hop flow。
- 破坏性变更：无；Phase 3 schema 未新增字段，只新增 Undertow auxiliary query 结果。

---

## [2026-06-19] 第二部分 Jersey OAuth1 Provider Flow 接入

### 修改时间
2026-06-19 21:01

### 变更类型
- [新增功能] OAuth provider-state 查询
- [功能改进] Phase 3 辅助查询合并
- [文档] 运行基线更新

### 核心改动
- 使用 brainstorming 继续推进第二部分，将 `RequestTokenResource.postReqTokenRequest -> OAuth1Provider.newRequestToken -> DefaultOAuth1Provider.requestTokenByTokenString.put` 建模为独立 provider-state 候选流。
- 新增 `codeql/lib/OAuthRetention.qll` 和 `codeql/queries/phase3_oauth_candidate_features.ql`，覆盖 `WEB-REAL-0001` 的 request token static map retained-state 路径，输出 `candidate_family=provider_state`、`request_flow_kind=provider_field`、`proof_source=static_field`。
- 扩展 `scripts/run_phase3.py`，从硬编码 parser query 升级为 `auxiliary_queries` 列表，同时保留 `parser_query` 兼容路径，为后续 Jetty/Undertow 独立 bridge 查询预留接入口。
- 更新 `config.yaml` 和 `README.md`，显式登记 Jersey OAuth auxiliary query 和当前 Phase 3/4 基线。

### 交付成果
- 新增 CodeQL 库：`codeql/lib/OAuthRetention.qll`
- 新增查询：`codeql/queries/phase3_oauth_candidate_features.ql`
- 修改脚本：`scripts/run_phase3.py`
- 修改配置与文档：`config.yaml`、`README.md`、`CHANGELOG.md`
- 更新结果：`results/phase3/jersey_oauth_candidate_features.csv`、`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase3_report.md`、`results/phase4/`、`results/phase4_report.md`
- 测试/验证结果：`python3 scripts/run_phase3.py --framework jersey` 生成 4 条 Jersey 候选，其中 OAuth provider-state 1 条；`python3 scripts/run_phase3.py` 生成 33 条候选，Phase 3 consistency 33/33 matched；`./dos-web-analyzer analyze` 生成 33 条 Phase 4 候选，OAuth 候选为 `WEB-P4-0007`；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过 288 个积格点；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression(s)。

### 依赖与影响
- 依赖：第二部分最小实现中的 Jersey 聚焦 buildless DB 和统一 Phase 3 schema。
- 对后续工作的影响：已覆盖 `WEB-REAL-0001` 的静态候选入口；下一步可沿用 auxiliary query 机制补 Jetty ProxyServlet destination flow、Undertow LearningPush 和 MCMP helper flow。
- 破坏性变更：无；Phase 3 schema 未新增字段，仅增加一个辅助查询族和 1 条 Jersey provider-state 候选。

---

## [2026-06-19] 第二部分 Entry/Data Flow/Parser 最小实现

### 修改时间
2026-06-19 20:52

### 变更类型
- [新增功能] Request flow proof
- [新增功能] Parser/body 候选查询
- [功能改进] Phase 3/4 schema 与结果合并
- [功能改进] Jersey buildless 数据库

### 核心改动
- 新增 `codeql/lib/RequestFlow.qll`，将 Phase 3 retained-state 主查询迁移到 direct / one-hop helper 的 request-flow proof 输出，补充 `request_flow_proof`、`call_path`、`request_carrier_kind`、`source_expr` 等字段。
- 新增 `codeql/lib/ParserRetention.qll` 和 `codeql/queries/phase3_parser_candidate_features.ql`，将 Jersey multipart `MessageBodyReader.readFrom/readMultiPart -> getMimeParts/getAttachments -> getBodyParts().add(bodyPart)` 作为独立 `candidate_family=parser_body` 查询族接入。
- 修改 `scripts/run_phase3.py`，支持 retained-state query 与 parser/body query 合并为统一 Phase 3 schema；修改 `scripts/check_phase3_consistency.py`，把 proof/request-flow/parser 字段纳入 schema 校验。
- 修改 `scripts/run_phase4.py`，透传 request-flow/parser 字段并对 `request_flow_proof` 给出排序信号；Phase 4 top 队列现在可直接展示 Jersey multipart parser/body 候选。
- 修改 `scripts/build_jersey_db.sh`，使用聚焦 buildless 源码视图 `frameworks/jersey-3.1.3-analysis-sources`，稳定抽取 `media/multipart` 与 `security/oauth1-*`，避免全仓 Maven trace 漏掉 multipart 源码。

### 交付成果
- 新增 CodeQL 库：`codeql/lib/RequestFlow.qll`、`codeql/lib/ParserRetention.qll`
- 修改 CodeQL 库：`codeql/lib/SessionState.qll`
- 新增查询：`codeql/queries/phase3_parser_candidate_features.ql`
- 修改查询：`codeql/queries/phase3_candidate_features.ql`
- 修改脚本：`scripts/run_phase3.py`、`scripts/run_phase4.py`、`scripts/check_phase3_consistency.py`、`scripts/build_jersey_db.sh`
- 修改配置与文档：`config.yaml`、`README.md`、`CHANGELOG.md`
- 更新结果：`results/phase3/phase3_candidate_features.csv`、`results/phase3/jersey_parser_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase4/`、`results/phase4_report.md`
- 测试/验证结果：`./scripts/build_jersey_db.sh --force` 成功生成聚焦 Jersey DB；`python3 scripts/run_phase3.py` 生成 32 条候选，其中 3 条 Jersey multipart parser/body 候选，Phase 3 consistency 32/32 matched；`./dos-web-analyzer analyze` 生成 32 条 Phase 4 候选；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过 288 个积格点；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression(s)。

### 依赖与影响
- 依赖：第一部分 proof-carrying retention sink schema 和第二部分 brainstorming 设计。
- 对后续工作的影响：已覆盖 `WEB-REAL-0002` 的 parser/body 静态候选入口；后续应继续补 Jersey OAuth1 provider flow、Jetty ProxyServlet client flow、Undertow LearningPush/MCMP helper flow。
- 破坏性变更：Phase 3 schema 继续向后扩展；Jersey 数据库改为第二部分聚焦源码视图，适合当前 parser/OAuth 分析但不是全仓 Jersey 统计。

---

## [2026-06-19] 第二部分 Entry/Data Flow/Parser Brainstorming 完成

### 修改时间
2026-06-19 20:18

### 变更类型
- [文档] 改造计划
- [文档] 设计细化

### 核心改动
- 使用 brainstorming 方式补全 `docs/drd_inspired_rearchitecture_plan.md` 第二部分，将 entry/data-flow/parser 支撑从提纲扩展为可执行工程蓝图。
- 基于第一部分实现后的 25 条 proof-carrying 候选基线，明确剩余缺口集中在 Jersey provider/interface dispatch、Jersey multipart parser、Jetty ProxyServlet client flow、Undertow listener callback 和 MCMP command/helper flow。
- 新增 `RequestCarrier`、`WebRequestFlowPath`、bounded call path、interface dispatch、provider field、listener callback、client request flow、parser/body 独立查询族和双查询合并方案。
- 明确 `candidate_family`、`request_flow_proof`、`call_path`、`request_carrier_kind`、`deployment_condition`、`capacity_hint` 等 Phase 3 输出字段，以及 5 个 `WEB-REAL-*` 的第二部分覆盖路径。

### 交付成果
- 修改设计文档：`docs/drd_inspired_rearchitecture_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：文档变更，未运行 CodeQL、Phase 3/4 pipeline 或动态验证。

### 依赖与影响
- 依赖：第一部分 proof-carrying retention sink 实现结果和当前 Phase 3 基线。
- 对后续工作的影响：后续实现应优先新增 `RequestFlow.qll`、`ParserRetention.qll`、parser/body 查询和 `WEB-REAL-*` coverage smoke，再改造 `SessionState.qll` 消费 request-flow proof。
- 破坏性变更：无。

---

## [2026-06-19] Proof-Carrying Retention Sink 第一部分实现

### 修改时间
2026-06-19 20:10

### 变更类型
- [新增功能] CodeQL retention sink proof
- [功能改进] Phase 3 proof-carrying schema
- [功能改进] Phase 4 proof 字段透传

### 核心改动
- 新增 `codeql/lib/RetentionSinks.qll`，实现 `WebRetentionSink`、collection/attribute/registry/nested/parser sink 形态，以及 `growth_driver`、`sink_shape`、`receiver_proof` 等 proof-carrying 接口。
- 扩展 `codeql/lib/Persistence.qll`，新增 lifecycle root、retained field 和 receiver proof 基础规则，覆盖 static field、Web lifecycle field、getter/字段链的保守证明。
- 修改 `codeql/lib/SessionState.qll`，让 Phase 3 主候选只消费带 proof 的 `WebRetentionSink`；未知裸 `WebContainerWrite` 不再默认标为 `static_container`。
- 扩展 `codeql/queries/phase3_candidate_features.ql` 和 `scripts/run_phase3.py`，在旧字段兼容基础上追加 proof schema；扩展 `scripts/run_phase4.py`，透传 proof 字段并对 receiver proof / unknown container 做 proof-aware 排序调整。
- 收紧 parser/header 规则，避免 `HeaderMap`、response headers 和 request-local 写入进入 proof-carrying 主候选。

### 交付成果
- 新增 CodeQL 库：`codeql/lib/RetentionSinks.qll`
- 修改 CodeQL 库：`codeql/lib/Persistence.qll`、`codeql/lib/SessionState.qll`
- 修改查询：`codeql/queries/phase3_candidate_features.ql`
- 修改脚本：`scripts/run_phase3.py`、`scripts/run_phase4.py`
- 更新结果：`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase3/<framework>_candidate_features.*`
- 更新报告：`results/phase3_report.md`、`results/phase4_report.md`、`results/phase4/`
- 测试/验证结果：`python3 scripts/run_phase3.py` 生成 25 条 proof-carrying 候选，Phase 3 consistency 25/25 matched；`./dos-web-analyzer analyze` 生成 25 条 Phase 4 候选；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过 288 个积格点；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression(s)。

### 依赖与影响
- 依赖：第一部分 brainstorming 设计和现有 Phase 3/4 pipeline。
- 对后续工作的影响：第二部分需要补 bounded multi-hop data flow / listener flow / provider flow，以覆盖 Jetty ProxyServlet、Jersey OAuth1 和 Undertow LearningPush 等跨组件路径。
- 破坏性变更：Phase 3 schema 向后兼容旧字段但追加 proof 字段；候选集合从裸 sink 扫描收敛为 proof-carrying sink，候选数量由旧结果收敛为 25 条。

---

## [2026-06-19] Proof-Carrying Retention Sink 第一部分 Brainstorming 完成

### 修改时间
2026-06-19 00:18

### 变更类型
- [文档] 改造计划
- [文档] 设计细化

### 核心改动
- 使用 brainstorming 方式补全 `docs/drd_inspired_rearchitecture_plan.md` 第一部分，将 proof-carrying retention sink 从概念方案细化为可执行设计蓝图。
- 增加 CodeQL 落地接口草案、Phase 3 proof schema、候选分层策略、第一阶段实现顺序、known-vuln sink/proof 对照表和风险约束。
- 关键技术决策：第一阶段优先产出 `confirmed_sink` / `needs_flow` / `debug_rejected` 三层结果，确保只有带 `receiver_proof` 与 `growth_driver` 的具体 mutation call 进入 Phase 3/4 主候选。
- 影响范围：后续实现应新增 `RetentionSinks.qll`，扩展 `Persistence.qll` 的 lifecycle/proof fact，并让 `SessionState.qll` 从裸 `WebContainerWrite` 迁移到 `WebRetentionSink`。

### 交付成果
- 修改设计文档：`docs/drd_inspired_rearchitecture_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：文档变更，未运行 CodeQL、Phase 3/4 pipeline 或动态验证。

### 依赖与影响
- 依赖：当前已验证漏洞库、现有 Phase 3/4 噪声分析和 Dr.D-inspired 改造计划。
- 对后续工作的影响：为第一部分实现提供稳定接口、输出字段、known-vuln 验收样例和降级规则。
- 破坏性变更：无。

---

## [2026-06-19] Proof-Carrying Retention Sink 方案替换

### 修改时间
2026-06-19 00:13

### 变更类型
- [文档] 改造计划
- [文档] 论文方法论路线

### 核心改动
- 将 `docs/drd_inspired_rearchitecture_plan.md` 的第一部分从 long-lived object 建模清单替换为 proof-carrying retention sink 改造方案。
- 关键技术决策：第一部分的直接产物定义为可供后续污点分析消费的具体 `WebRetentionSink`，每个 high-risk sink 必须携带 `receiver_proof` 与 `growth_driver`。
- 明确 Dr.D long-life class 识别结果作为 `LifecycleRootFact` / `proof_source=drd` 接入，但不能绕过 receiver proof 直接把类内所有 collection 写入升级为 sink。
- 影响范围：后续 CodeQL 改造应优先新增 `RetentionSinks.qll`、proof-carrying Phase 3 schema，以及 HeaderMap/request-local collection 的过滤降级。

### 交付成果
- 修改设计文档：`docs/drd_inspired_rearchitecture_plan.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：文档变更，未运行 CodeQL、Phase 3/4 pipeline 或动态验证。

### 依赖与影响
- 依赖：当前已验证漏洞库和 Dr.D-inspired 改造讨论。
- 对后续工作的影响：第一阶段实现目标从“识别 long-lived object”收敛为“产出带生命周期证明的具体 taint sink 清单”。
- 破坏性变更：无。

---

## [2026-06-18] Dr.D 启发式改造计划落库

### 修改时间
2026-06-18 23:53

### 变更类型
- [文档] 改造计划
- [文档] 论文方法论路线

### 核心改动
- 新增 Dr.D-inspired 改造计划，将任务按论文优先级重排为三部分：第一部分优先实现 long-lived object proof，第二部分补 entry/data-flow/parser 工程覆盖，第三部分再做回归、capacity/lifespan 证明和 Phase 4 排序。
- 关键技术决策：把 P2 作为首要创新点，要求候选成立必须证明 sink receiver 可追溯到跨请求保留对象；P1/P3/P4 作为支撑该证明的工程化需求；P0/P5/P6 放到最后，避免过早调分掩盖基础建模错误。
- 影响范围：后续 CodeQL 设计、Phase 3 schema、Phase 4 排序和论文方法章节应以该计划为优先级依据。

### 交付成果
- 新增设计文档：`docs/drd_inspired_rearchitecture_plan.md`
- 修改文档入口：`README.md`
- 修改变更日志：`CHANGELOG.md`
- 测试/验证结果：文档变更，无需运行 CodeQL 或动态验证。

### 依赖与影响
- 依赖：`results/phase4/verified_vulnerabilities.json` 和已完成的 Phase 3/4 设计审查。
- 对后续工作的影响：明确下一步首先重构 `codeql/lib/Persistence.qll` 与 `codeql/lib/SessionState.qll` 的 long-lived object 模型，再补 source/data-flow/parser，最后重做排序。
- 破坏性变更：无。

---

## [2026-06-18] 独立 AGENTS 工作指南落库

### 修改时间
2026-06-18 23:30

### 变更类型
- [文档] 项目级自动化助手工作指南

### 核心改动
- 为 `dos-analysis-web` 单独新增 `AGENTS.md`，将原先依赖上层或 AOSP 项目的协作约束移植为 Web 项目本地规则。
- 关键技术决策：保留简体中文交流、五轴 verdict 复用、可复现性、验证和变更日志要求；同时裁剪 AOSP 专用目录和 Binder 语义，改为 Web source、session/state retention、Phase 4 产物和动态验证真阳说明。
- 影响范围：后续自动化助手直接在 `dos-analysis-web/` 下工作时，可以按本项目语境设计非 AOSP 的 Java Web 分析任务。

### 交付成果
- 新增文档：`AGENTS.md`
- 修改文档：`CHANGELOG.md`
- 测试/验证结果：文档变更，无需运行 CodeQL 或动态验证。

### 依赖与影响
- 依赖：现有 `README.md`、Phase 4 结果和 verified 漏洞库。
- 对后续工作的影响：降低 Web 项目工作对 `dos-analysis/AGENTS.md` 的上下文依赖，避免将 AOSP 专用规则误用于非 AOSP 设计。
- 破坏性变更：无。

---

## [2026-06-18] Phase 4 动态验证真阳落库

### 修改时间
2026-06-18 22:58

### 变更类型
- [新增功能] verified 漏洞库
- [文档] 动态验证证据摘要

### 核心改动
- 将 5 个已经动态验证的 Web 资源耗尽型漏洞落入 Phase 4 verified 漏洞库，统一分配 `WEB-REAL-0001` 至 `WEB-REAL-0005` 编号。
- 新增机器可读 JSON 与 Markdown 摘要，并把临时 PoC 源码和 OOM 原始日志复制到 `results/phase4/dynamic_verification/`，避免后续依赖 `/tmp` 临时目录。
- 关键技术决策：verified 库与 Phase 4 静态候选队列分离；能对应静态候选的记录保留 `phase4_ids`，直接 agent 动态挖掘确认的记录不强行绑定候选 ID。

### 交付成果
- 新增漏洞库：`results/phase4/verified_vulnerabilities.json`
- 新增摘要：`results/phase4/verified_vulnerabilities.md`
- 新增 PoC 归档：`results/phase4/dynamic_verification/poc/`
- 新增日志归档：`results/phase4/dynamic_verification/logs/`
- 验证结果：Jersey OAuth1、Jersey multipart、Undertow LearningPush、Undertow mod_cluster、Jetty ProxyServlet destination 均有默认堆 OOM 证据；其中 Undertow LearningPush 和 Jetty ProxyServlet 使用真实 HTTP 请求验证。

### 依赖与影响
- 依赖：Phase 4 静态候选和本轮动态验证 PoC。
- 对后续工作的影响：后续 CVE/issue 报告、论文 RQ4、复现实验应以 `verified_vulnerabilities.json` 为权威入口。
- 破坏性变更：无；不修改 CodeQL 查询、排序 pipeline 或既有 Phase 1-4 结果语义。

---

## [2026-06-18] Phase 4 Large-Scale Mining 启动

### 修改时间
2026-06-18 13:48

### 变更类型
- [新增功能] Phase 4 候选排序与复核队列
- [新增功能] dos-web-analyzer 统一 CLI 入口
- [文档] Phase 4 运行说明和结果报告

### 核心改动
- 新增 Phase 4 pipeline，消费 Phase 3 统一候选 CSV，生成排序候选、top-N 人工复核队列、评估摘要和 Markdown 报告。
- 排序策略以五轴 verdict 为主信号，叠加 R/V/M/C/L、sink/container 类型、key 可控性，并对测试/示例路径和疑似请求局部 evidence 做降权，保证 Phase 4 优先服务人工复核和动态验证。
- 新增 `dos-web-analyzer` 入口，支持 `phase1`、`phase2`、`phase3`、`analyze`、`report`、`verify --top N`，将 Phase 4 的 expected workflow 固化为可复现命令。

### 交付成果
- 新增脚本：`scripts/run_phase4.py`
- 新增 CLI：`dos-web-analyzer`
- 修改配置：`config.yaml`
- 更新文档：`README.md`
- 结果产物：`results/phase4/ranked_candidates.csv`、`results/phase4/ranked_candidates.json`、`results/phase4/review_queue_top50.md`、`results/phase4/review_queue_top50.json`、`results/phase4/evaluation_summary.json`、`results/phase4_report.md`
- 验证结果：`./dos-web-analyzer analyze` 基于 Phase 3 的 103 条候选生成 Phase 4 产物

### 依赖与影响
- 依赖：Phase 3 已生成的 `results/phase3/phase3_candidate_features.csv`
- 对后续工作的影响：为 top-50 人工复核、动态验证和论文 RQ4 漏洞发现提供统一队列
- 破坏性变更：无；不修改 Phase 1-3 查询语义和 AOSP 工具

---

## [2026-06-16] Phase 3 Unified Modeling 实施完成

### 修改时间
2026-06-16 23:59

### 变更类型
- [新增功能] Web 统一五轴候选提取
- [新增功能] Phase 3 自动化运行与一致性验证
- [文档] Phase 3 结果报告

### 核心改动
- 实现 Web 侧 `CommonDoS.qll` 五轴抽象、`SessionState.qll` retained state 写入模型、`WebGuards.qll` 可达性模型和 `phase3_candidate_features.ql` 主查询。
- 新增 `scripts/run_phase3.py` 批量运行 5 个 Web 数据库并生成统一候选 CSV；新增 `scripts/check_phase3_consistency.py` 使用 AOSP `eval/verdict.py` 校验 CodeQL verdict。
- 第一版采用方法内与一层 helper call 的最小统一闭环，输出 evidence 和保守假设，为 Phase 4 排序与人工复核提供输入。

### 交付成果
- 新增 CodeQL：`codeql/lib/CommonDoS.qll`、`codeql/lib/SessionState.qll`、`codeql/lib/WebGuards.qll`、`codeql/queries/phase3_candidate_features.ql`
- 修改 CodeQL：`codeql/lib/WebSources.qll`、`codeql/lib/Persistence.qll`
- 新增脚本：`scripts/run_phase3.py`、`scripts/check_phase3_consistency.py`
- 新增结果：`results/phase3/phase3_candidate_features.csv`、`results/phase3/phase3_consistency.json`、`results/phase3_report.md`
- 验证结果：`python3 scripts/run_phase3.py` 对 Tomcat、Spring Boot、Jetty、Undertow、Jersey 运行完成，生成 103 条候选；`phase3_consistency.json` 记录 103/103 matched，consistency 100%
- 验证结果：`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过，288 个积格点单调性成立
- 验证结果：`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression(s)

### 依赖与影响
- 依赖：Phase 2 已完成的 5 个 Web CodeQL 数据库和 `results/phase2_report.md`。
- 输出：为 Phase 4 大规模挖掘、top candidate 排序、人工复核和论文 RQ1/RQ3/RQ4 评估提供统一候选 schema。
- 影响：不修改 AOSP 工具语义；仅复用 AOSP `eval/verdict.py` 作为 verdict 权威实现。
- 破坏性变更：无。

---

## [2026-06-17] Phase 2 补齐 Spring Boot 与 JAX-RS 入口结果

### 修改时间
2026-06-17 00:20

### 变更类型
- [功能改进] Source discovery 覆盖扩展
- [Bug 修复] Spring Boot 数据库构建修复
- [文档] Phase 2 结果报告更新

### 核心改动
- 修复 Spring Boot 数据库构建：原先 Gradle 7.6.3 在 Java 21 下触发 `Unsupported class file major version 65`，改为使用 `JAVA_HOME=/usr/lib/jvm/java-17-openjdk` 并采用 CodeQL `--build-mode=none`，成功生成 `finalised: true` 数据库。
- 扩展 JAX-RS 入口识别：`phase2_source_discovery.ql` 与 `WebSources.qll` 同时支持 `javax.ws.rs` 和 `jakarta.ws.rs`，覆盖 Jersey 3.x 的 Jakarta 包名。
- 将 Spring Boot 与 Jersey/JAX-RS 结果补入 Phase 2：Spring Boot 产生 278 条参数记录，其中 Spring controller 89 条、JAX-RS 3 条；Jersey 产生 31 条参数记录，其中 JAX-RS 3 条。

### 交付成果
- 修改查询：`codeql/queries/phase2_source_discovery.ql`
- 修改模型：`codeql/lib/WebSources.qll`
- 新增测试查询：`codeql/queries/test_jaxrs_entries.ql`
- 新增/修改构建脚本：`scripts/build_springboot_db.sh`、`scripts/build_jersey_db.sh`
- 新增结果：`results/phase2/spring-boot_sources.csv`、`results/phase2/spring-boot_sources.bqrs`
- 新增结果：`results/phase2/jersey_sources.csv`、`results/phase2/jersey_sources.bqrs`
- 更新报告：`results/phase2_report.md`

### 依赖与影响
- 依赖：本机 `/usr/lib/jvm/java-17-openjdk`，CodeQL 2.23.8。
- 影响：Phase 2 结果覆盖从 3 个数据集扩展到 5 个数据集；总参数记录达到 1328 条，其中 Spring controller 89 条、JAX-RS 6 条。
- 后续：Phase 3 可以基于 Spring/JAX-RS source 清单继续做 L3 write target / retention sink 检测。

---
