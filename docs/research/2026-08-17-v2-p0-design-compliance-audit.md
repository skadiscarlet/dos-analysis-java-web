# v2 P0 Design 零信任代码一致性审计

> **最终实施更新（2026-08-18）：** 本文第 1–8 节保留修复前审计证据，不再代表当前结论。approved P0 Gate 2/3 已按边界完成：same-CFG/depth≤1 lifecycle、attacker-controlled loop、candidate/flow completeness、Auth/config、private LLM audit、run identity、artifact contracts，以及真实 Spring/Servlet/Netty/MQTT production E2E 全部落地。offline 为 611 passed / 9 skipped / 436 subtests；real CodeQL entry/growth 为 5/30，lifecycle 为 3/50；Gate 3 fresh reviewer 最终 0 BLOCKER/0 HIGH。Erupt/Citrus/DataCompare 三个动态真阳性 seed 的 formal static canary 全部 completed、0 query diagnostics、resume 可复用、无 credential leak；`static_unknown` 均保留精确 auth/flow/lifecycle 理由，未把动态 truth 输入普通 verdict。新 205-target formal plan 已发布但未执行，且 205 全部 queued——git-commit provenance 已不再作为门槛（tree-sha256 目标以本地源码树直接 full 执行）。depth>1/custom/reflection/async-capacity 继续按批准 deferred 边界 fail-closed。

**日期：** 2026-08-17
**唯一 P0 标准：** `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md`
**完整研究路线对照：** `docs/research/2026-07-14-lifecycle-centered-resource-dos-idea-design.md`
**审计范围：** 当前工作区代码、CodeQL pack、production wiring、artifact/recovery、DeepSeek、batch/corpus、benchmark 与测试

## 1. 结论（历史：修复前）

以下结论是修复前零信任审计快照；当前验收结论以上方“最终实施更新”为准。

本轮不能确认“完整 P0 analyzer 已达到 approved design”。当时状态应准确表述为：

- **205 corpus/entries orchestration 已可用于入口覆盖侦察和 CodeQL 稳定性批次。**
- **不应启动 205-target 正式 full 实验，即使补齐 DeepSeek 凭据。** 当前仍有会造成 silent omission、false-vulnerable、无法证明 bounded 和不可完整回放 provider 决策的 P0 blockers。
- 现有测试全绿主要证明 schema、纯函数、恢复和人工构造场景正确，**没有证明 production CodeQL → flow → lifecycle → certificate 的真实语义闭环**。

最关键的差距集中在四处：

1. E→G 仍是窄语法匹配，缺少设计要求的 interprocedural/data-flow/field-flow 证明，并会静默丢弃零 flow 或无法映射的 Growth。
2. production lifecycle 尚不能证明有效 Guard/Bound/同步 Release：默认配置永远为空，CodeQL lifecycle query 只产 partial 候选，且候选没有 `(entry,growth,path)` 绑定。
3. Assertion 1/2 的适用前件不完整：A1 会错误覆盖 fixed-per-request key/value accumulation；A2 未证明 repeatability；`auth_context=unknown` 不会强制 unknown。
4. bounded slice/provider audit 未满足 approved design 的可回放要求：CFG/config/真实 flow facts 为空或合成，raw prompt/response 未归档；普通 CLI 的 public URL 未绑定 Git origin。

## 2. P0 blockers

### B1. 未映射 Growth 和零 flow Growth 被静默遗漏

**证据：**

- `dosweb/production.py:491-514`：`ANALYSIS_GROWTH_ENTRY_AMBIGUOUS(match_count=0)` 仅递增 `skipped_unmapped_candidate_count` 后 `continue`。
- `dosweb/production.py:709-748`：conclude 只遍历已有 flow 的 `(entry_id,growth_id)` 分组。
- `dosweb/production.py:532-541`：flows stage 可以合法发布空 `flow_proofs.jsonl`。

**后果：**

- raw Growth 存在但无法关联 E 时，没有 unresolved Growth、coverage gap、certificate 或 `static_unknown`。
- verified Growth 没有任何 flow row 时同样完全消失。
- 这违反 design §2.3、§6.3、§7、§11：未证明/不支持的候选必须显式 unresolved/unknown，不能静默漏报。

**测试现状：** `tests/test_production.py` 当前接受 skipped-unmapped 行为，缺少“每个 candidate-relevant omission 都有 unknown/gap”的 invariant。

### B2. E→G query 不是设计要求的跨过程 data flow

**证据：**

- `dosweb/codeql/pack/dosweb/Flows/EntryToGrowth.ql:93-120` 只支持参数直接访问、一个局部 initializer 和一层 helper forwarding。
- `EntryToGrowth.ql:52,57,62` 对 Servlet/Netty/MQTT flow 只识别 `fixture.*` 类型，不识别真实 `javax/jakarta.servlet`、`io.netty`、Paho handler。
- `EntryToGrowth.ql:135-136` 对上述窄语法匹配无条件输出 `proven` / `complete`。
- 没有 CodeQL data-flow library、field flow、多层 wrapper、DTO/service、循环/fan-out、owner/session/connection 创建或多态 dispatch 证明。

**后果：**

- 真实 Servlet/Netty/MQTT production flow 基本无法命中。
- `handler -> a -> b -> sink`、字段写入后消费、循环计数控制、wrapper executor/queue 都会零 row，随后触发 B1 的 silent omission。
- `call_path` 不是实际完整调用路径。

**额外语义错误：** `submit/execute(task)` 的 task 参数被标成 `submission_count`。任务内容可控不等于提交次数可控；循环次数、entry repeatability 和单次提交必须分开建模。

### B3. Growth Contract 的“静态 attacker influence”来自合成事实

**证据：**

- `dosweb/growth/evidence.py:78-79` 注释明确说明 Growth query 不证明 E→G。
- 同文件 `108-116` 却为每个 demand 无条件创建 `relation="source"`，位置仍在 Growth excerpt。
- `134,138` 的 `CfgSummary` 与 `config_facts` 恒为空。
- `dosweb/growth/verify.py:178-196` 只要求 LLM 引用这些合成的 `source|flows_to` fact 即可通过 attacker influence 检查。
- `_slice_for()` 只截取 Growth site 与 registration site，没有保证包含 handler、真实 E→G path、receiver/key 定义或默认配置。

**后果：** raw API screening + LLM `yes` 可得到 `verified_growth`，但所谓 attacker influence 并非 CodeQL/CFG 证明。最终 flow 若缺失又会被 B1 静默丢弃。

### B4. production 无法证明有效 Guard/Bound/同步 Release

**证据：**

- `dosweb/production.py:676-677` 恒传 `ModeledConfiguration(())`，没有把默认配置解析结果送入 Guard/Bound evaluator。
- `GuardCandidates.ql:38-43` 恒输出 representation/phase unknown、`covers_materialization=false`、`coverage_status=partial`。
- `BoundCandidates.ql:54-60` 恒输出 phase unknown、`covers_flow=false`、`product_bound=false`、`coverage_status=partial`。
- `SynchronousReleaseCandidates.ql:40-44` 恒输出 `after_growth=false`、`coverage_status=partial`，异常路径也未证明。
- Bound query 的 queue receiver/field 表示与 `AsyncWorkGrowth.ql` 的 field-backed receiver identity 不一致；Release receiver 仅为 qualifier 字符串。

**后果：** production 的真实 CodeQL 路径当前不能得到 design §8 所需的 effective Guard/Bound/synchronous Release。单元测试能得到 effective，是因为测试直接构造 complete candidate 和显式 `ModeledConfiguration`，不是 production 能力。

### B5. lifecycle candidate 没有 `(E,G,path)` 绑定，absence 也没有 coverage 证明

**证据：**

- Guard/Bound/Release candidate schema 没有 `entry_id`、`growth_id`、`path_id`。
- `dosweb/production.py:667-680` 把同一全局 candidate list 送给每条 flow。
- evaluators 主要靠 receiver/scope/dimension/key 等字符串比较。
- `guards.py`、`bounds.py`、`releases.py` 在 candidate list 为空时直接判 `ineffective/absent`。

**后果：**

- 未被窄 CodeQL 模式找到的真实 Guard/Bound/Release 会被当作确定性 absence，可能造成 false-vulnerable。
- 将来只要 query 能产 complete candidate，同名但无关路径的 candidate 又可能错误反驳另一条 flow，造成 false-bounded。
- 与 design 中 `EffectiveB(E,G,path,B)`、Guard dominance、same-P/path Release 约束不一致。

### B6. Assertion 1/2 的适用前件不完整

**可执行复现：** 对 persistent `container_growth(key)` 构造 effective synchronous Release，当前结果为：

```text
A1 = matched
A2 = refuted
verdict = static_vulnerable
```

复现命令已在审计中通过现有 `P0EndToEndTests` helper 执行。

**根因：**

- `evaluate_assertion_1()` 不限制 growth kind 或 attacker target；fixed-per-request key/value accumulation 也命中 A1。
- 按 design §9.1，container/async 只有“单请求能够放大资源需求”时才适用 A1；普通 distinct-key 一次一项应由 A2 判断。
- `evaluate_assertion_2()` 将 key/value/submission + escaping 当作 repeatable growth，但 Entry/Flow model 没有 repeatability evidence。
- 所有 Entry query 几乎都写死 `auth_context="unknown"`，assertion/verdict 不会因攻击者 reachability 未知而强制 `static_unknown`。

**后果：** effective synchronous Release 无法反驳普通 persistent accumulation；未知认证入口也可能得到 `static_vulnerable`。

### B7. Netty entry 未证明 server bootstrap 注册

**证据：** `NettyEntries.ql` 只证明 `ChannelInitializer.initChannel()` 内存在 `pipeline.addLast()`，没有证明 initializer 被 `ServerBootstrap.childHandler(...)` 或等价启动链使用，却输出 complete entry。

**后果：** 从未安装/启动的 initializer 也会被视为外部入口，违反 design §6.1 “handler definition alone does not prove external reachability”。现有 fixture 正好未绑定 bootstrap，却把它当 registered positive。

### B8. Growth/provider 审计工件不满足 design 的可回放合同

**证据：**

- Growth stage 只发布 `growth_candidates.jsonl`、解析后的 `growth_contracts.jsonl`、`verified_growth.jsonl`。
- `ContractCache.put()` 只保存 identity、request audit 与 parsed contract。
- 没有持久化 bounded slice、完整 normalized prompt、raw provider response body/parsed response 对照。
- `run.json` 只有 tool/schema/status/stages；缺少 CodeQL CLI version、query-pack version、stage timing、显式 provider/model/base URL/temperature/prompt version。

**后果：** 无法按 design §5、§7 对 provider 判定进行独立完整回放，也不能从 `run.json` 恢复实验环境。

### B9. 普通 CLI 的 public URL 没有绑定 Git origin

**证据：**

- `GitHubPublicSourceVerifier._verify()` 与 `_validate_slice()` 调用 `_verify_checkout(checkout, sha)` 时未传 `source_url`。
- `_verify_checkout()` 只有 `source_url is not None` 才校验 origin。
- audit 记录 `verified_public=false`。

**后果：** 普通 CLI 可以把任意 clean local checkout/commit 与格式正确但无关的 GitHub URL 组合。batch runner 有额外绑定，不能覆盖 standalone CLI。

## 3. 重要但次于 blockers 的差距

### H1. Entry query failure 策略与 approved design 不一致

当前单条 selected Entry query 的 `CODEQL_QUERY_FAILED` 被转成 partial coverage 并让 stage completed。这个行为符合上一轮 205 可恢复批次计划，但与 approved design §4.1/§12 “required CodeQL stage/query failure 退出 3”存在冲突。

必须明确二选一：

1. 恢复 fatal CodeQL failure；或
2. 正式修订 design，区分 optional framework-family failure 与 required stage failure，并保留独立 reason/exit policy。

### H2. framework-wide coverage 过粗

coverage 以 framework 聚合。一个同框架的 dynamic/reflection gap 会让所有该框架候选 unknown；这通常 fail-closed，但造成大量 false-unknown，不符合“candidate-relevant gap”目标。需要 entry/registration/growth/path scoped coverage。

### H3. run/artifact 错误合同未完全对齐

approved design 要求的初始错误码中，当前缺少：

- `ARTIFACT_SCHEMA_MISMATCH`
- `ARTIFACT_UPSTREAM_HASH_MISMATCH`

Pipeline publication 主要验证 canonical encoding/hash/count；schema/reference validation 分散在 executor，pipeline 本身不会按 artifact type 统一执行发布前 schema/reference gate。

### H4. 报告只校验 finding → certificate

`render_report()` 会拒绝 finding 引用缺失 certificate，但不会拒绝额外 orphan certificate。报告可能遗漏 certificate 而成功发布。

## 4. 符合项

以下实现与 approved design 基本一致：

- 固定顺序：`entries -> growth -> flows -> lifecycle -> conclude -> report`。
- stage manifest、fingerprint、artifact hash/record count、原子发布和下游 invalidation。
- 三态 verdict vocabulary，无 `static_safe` compatibility。
- partial flow、unresolved lifecycle、framework coverage gap 可在已形成 candidate chain 时强制 unknown。
- Certificate 会重算 assertions/verdict 并拒绝伪造 ID、证据和路径。
- DeepSeek mandatory gate、API key 仅从环境读取、默认测试不联网。
- cache identity/HMAC/immutable publication/symlink 防护。
- 205 corpus source/database binding；full-ready 为 205 targets（205 全部 queued；git-commit provenance 不再是门槛）。
- benchmark dynamic oracle 与普通静态 conclusion 隔离。
- opt-in online test 仅上传固定公开人工 fixture。
- 异步 Release 不被误判为安全证据，依赖它的 A2 输出 unknown。

## 5. 与 2026-07-14 完整研究设计的 deferred 差距

以下不计入 P0 blocker，但必须保持 limitation/unknown：

- Assertion 3；
- async registration → callback/worker/timer → Release 证明；
- producer/consumer capacity、客户端 ACK/reconnect/close；
- blocking Release、TTL/renewable timeout、terminal path/multiplicity；
- WebFlux、WebSocket、message consumer、自定义 wrapper 的广泛支持；
- custom Release 的 LLM semantics/efficiency judge；
- ML/GNN ranking、自动动态验证、deployment budget proof。

JAX-RS/gRPC 虽已增加 query，但 approved P0 并不以其为完成条件；不能用额外框架数量替代 Spring/Servlet/Netty/MQTT 主链闭环。

## 6. 测试结果与测试可信度

本轮执行：

```text
python3 -m pytest -q \
  tests/test_assertions.py tests/test_flow_verification.py \
  tests/test_growth_verification.py tests/test_lifecycle_guards.py \
  tests/test_lifecycle_bounds.py tests/test_lifecycle_releases.py \
  tests/test_certificates_and_reports.py tests/test_p0_end_to_end.py \
  tests/test_production.py tests/test_deepseek_client.py \
  tests/test_batch_plan.py tests/test_batch_runner.py \
  tests/test_benchmark_matching.py

262 passed, 233 subtests passed, 2 warnings
```

上一轮全套离线回归：572 passed / 5 skipped / 422 subtests；真实 CodeQL entry/growth/lifecycle fixtures 也已单独通过。

这些结果不能消除本报告的 blockers，原因是：

- `test_p0_end_to_end.py` 直接构造 Entry/Growth/Flow/complete lifecycle decisions，不走真实 production CodeQL/LLM wiring。
- lifecycle fixture 只断言 partial candidate 被提取，没有证明 effective Guard/Bound/Release。
- production test 当前显式接受 skipped-unmapped candidate。
- 没有测试“verified Growth 零 flow 必须 unknown”“unknown auth 必须 unknown”“container + effective sync Release 不得被 A1 保持 vulnerable”。

## 7. 开跑门槛

### 可以继续

- 205 `entries` 批次：可作为 framework coverage、query 稳定性、row distribution 和 error taxonomy 侦察。
- 单 query / fixture / 小型 canary：可用于逐项修规则。

### 暂停

- 205-target 正式 `full` 实验；
- 任何“P0 analyzer 已完成”的论文或实验口径；
- 任何把当前 absence 判定或 `static_vulnerable` 当作可信全量结果的发布。

### 建议修复顺序

1. **Assertion/reachability gate：** 修 A1 applicability；显式建模 auth 与 repeatability；补回归。
2. **Candidate completeness：** 未映射 G、零 flow、partial flow 全部形成可追踪 unresolved chain/unknown。
3. **Flow redesign：** real framework types + CodeQL interprocedural/field/wrapper/loop/fan-out/submit semantics。
4. **Lifecycle Evidence Graph：** candidate 绑定 E/G/path/P；无候选只有在 coverage complete 时才能判 absent。
5. **Default config + effective counterexamples：** production 真正证明 Solr-style Guard、finite checked queue Bound、same-P sync Release。
6. **Bounded slice/audit：** 使用真实 flow/CFG/config facts；持久化可回放 prompt/response 或正式修订 audit policy。
7. **Provenance/run metadata：** origin binding、CodeQL/provider/prompt/timing 记录、错误码对齐。
8. **重新做代表性 full canary：** Zipkin/Erupt/DCMP/JMQTT bounded queue + Netty/MQTT real registration/flow，再决定是否启动 205-target full。
