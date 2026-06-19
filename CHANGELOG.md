# dos-analysis-web 变更日志

本文档记录 dos-analysis-web 项目的所有重要变更。

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
