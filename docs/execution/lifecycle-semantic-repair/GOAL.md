## 本次交付绑定（2026-09-23）

实际执行与交付：task_2ae65d0c4ec847ad819c / codex/lifecycle-semantic-repair-20260922。同目标并发任务的已验证实现通过记录hash的快照集成，本分支独立完成旧非证明兼容、21/21冻结回放及最终回归；不写入其20260923工作树。最终结论以本目录STATUS/HANDOFF及reports/lifecycle-semantic-repair/summary.md为准。研究门槛partial，最终工具初验fail；原任务的约束不变。

# E2E semantic repair：执行摘要

源任务：用户授权的 `CODEX_GOAL_E2E_SEMANTIC_REPAIR.md`，日期2026-09-22，分享会话 https://chatgpt.com/share/6ab3ec6f-a778-83e8-b13f-54fe05208958 。本摘要不替代原始287行任务。交流简体中文。

## 范围

本轮仅防御性离线静态工具维护、冻结基准评价与本仓库合成测试；不运行目标服务、PoC、攻击请求、压力负载或耗尽复现；不新增目标，178-target保持暂停。不可按项目名、路径、oracle或利用细节定制检测，不降低判定前提，不将unknown推为阳性，不接受未验证LLM结论。主资产只读，所有新输出写新目录，旧报告不可变；禁止reset/clean/force push。保留主工作区dirty文件，不改AOSP侧。

基线commit=3e2690ec55e14bd62fcea85e97d17cec2a71b43b；分支codex/lifecycle-semantic-repair-20260922。主资产根=/home/furina/new_tool/dos-analysis-web；冻结run=lifecycle-e2e-poc33-api2cn-20260920_003322；entries/full/recall/eval在主资产根results/java_web_dos_batch下。先复用冻结事实，不立即全量CodeQL/LLM。普通任务分支push已获授权，只由协调者执行。

## A：指标修正

只对正式static_vulnerable去重family统计predicted_positive_families和reviewed_positive_tp/fp/unreviewed_positive；analysis_unknown_families和bounded_families独立。precision=TP/(TP+FP)，保守下界=TP/(TP+FP+unreviewed_positive)，零分母必须null。冻结预期：阳性0，TP/FP/阳性未复核=0/0/0，analysis_unknown=126，recall=0/33，两precision=null，precision_review_status=not_evaluable_no_positive。未知不进入阳性复核分母和队列，分别输出表；阳性表空时保留表头。0.8仍proposed_default，FPR仍not_measured。

保留33所有记录及其匹配；20/29和0/6子集需筛选条件、成员与排除原因；15 hard-negative分为bounded、unknown、错误阳性、执行/提取失败，未报阳性不等于证明安全。测试零阳性/全unknown/待复核阳性/重复family/33集合外新阳性。统计修复不改verdict。

## B：真实前提诊断与实际修复

审计132 finding/126 family与评价侧33记录：entry/registration、growth verified、auth/reachability/config、flow、repeatability/amplification、bound/release、bridge、assertion/verdict。20 certificate-backed unknown追到unresolved_facts、coverage_gaps及上游；保留全部阻塞原因+最早观测缺口；证据不足明确evidence_missing/cause_unresolved。区分事实传递丢失、不相关gap传播、模型未覆盖、输入/版本/配置/提取问题、评价问题和证据不足。按finding/family/known-record分别计数，重叠频次不求和当输入数。

bridge分别测candidates_considered/kind_and_dimension_applicable/growth_verified/flow_premise_satisfied/backend_executed/property_produced/binding_succeeded/property_consumed_by_assertion/verdict_affected，必要时交叉表；真实消费零即零，不强制查询制造消费。最多选择两个有证据通用实现根因，记录原始事实→预期转换→实际错误→修复转换，合成正反例验证。方法缺失则partial，不新增一般循环证明/任意动态分派/漏洞发现agent。

## C：证据贯通

用显式非平凡假设验证property→binding→ResourceLifecycleDecision→assertion→verdict→certificate→report/replay。可追溯具体assumptions/config/维度单位/资源身份/作用域/执行切面；hash不能代替语义。缺失、篡改、跨输入替换binding/assumption须拒绝借用bounded。最小兼容修复，必要升级schema/implementation identity、校验、缓存、证书与回放。

accepted-task population仅反驳同executor相关任务数增长，不是所有资源有界，不单独产生阳性。性质→断言→单位→作用域→切面表；最多额外接入一种现成且匹配的同步性质，无则记语义缺口，不在adapter新造bound。出口无持有≠峰值有限；close≠GC；单项大小≠总量；终止后释放≠及时终止；unknown/widening∞≠证明累积；不同资源/持有者不能借bound。

## 验证与交付

合成反例含正确绑定、错误资源/切面/executor、前提不满足、缺失假设、同族不同实例、互斥释放。固定facts前后比较；受影响阶段离线重放或合法resume到新目录，保留21项目及33匹配/失败；full/off固定候选/facts/预算。不得回写canonical DB。测试记录真实tested_source_commit及dirty内容hash。

S1统计正确；S2全部原因可追踪；S3实际通用修复与测试；S4身份/假设/作用域/切面贯通且实际消费可核查；S5同输入前后比较；S6集成回归、报告、实际commit/push与40位远端SHA一致。与最终工具33/33初验分开，若仍0/33则overall_tool_acceptance=fail，不将本轮包装为工具完成。

交付本目录GOAL/STATUS/HANDOFF；reports/lifecycle-semantic-repair内summary.md、corrected-baseline-metrics.json、prerequisite-status.csv、known-case-matches.csv、metrics.json、run-manifest.json、分开的阳性复核与unknown表。报告状态delivery_state_at_commit=ready_for_push。每次变更同步CHANGELOG，由协调者合并并行变更说明。仅暂存拥有文件，不git add .，不提交DB/源码副本/密钥/私有响应/大型raw evidence。正常push，不自动合并默认分支，交付后停止。
