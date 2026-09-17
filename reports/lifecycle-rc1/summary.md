# Lifecycle RC1

工程状态：**rc_ready**；research_evidence：**unvalidated**。

固定两个项目、三个模块、九个请求；均为本轮开发/回归输入。只做离线静态提取与性质检查。

| 门槛 | 状态 | 证据 |
| --- | --- | --- |
| R1 | pass | Three original XXL requests retried; 52/39 Java source/archive files, 13 lexical-trivia-only exclusions with hashes; all used archive bytes match. All three module source-scope.json complete. Byte mismatch/declaration-gap rejection tested. |
| R2 | pass | Complete 158-file common-core admits 8,891 raw rows (old query: 8,885), no truncation. Nine original IDs/selectors retained. Eight exact methods resolve; the ninth has a proven stale return-package descriptor, kept method_missing. Old zero-resource inputs separately show model coverage or recovered resource facts. |
| R3 | pass | Three real-source loops and final 11 tests pass; full common-core loop finishes in 272 steps with semantic replay. XXL synchronous history enumeration fixed: 248 steps, no budget exit. Widening infinity is not a growth or termination proof. |
| R4 | pass | Original source/oracle unchanged. Both modes match 12/12; S2 bounds 0/1 from ordinary properties; 12-unit property fields and semantic replay agree. Four fresh caller-cleanup/extra-holder counterexamples pass; old manual suite stays 24/24. |
| R5 | pass | Four nonempty resource units in all three original modules complete solve/selected replay; two projects, nine-request denominator; same-fact ablation, costs, unknowns and zero call/task bindings explicitly reported. |
| R6 | pass | Final same-environment suite: 1212 passed, 12 failed, 46 skipped, 1 collection error; zero new failure/error IDs. All added default opt-in skips have separate execution evidence. Delivery artifacts reviewed; this report records ready_for_push only. Remote SHA verification is performed after the report commit. |

阶段计数：`{'mapping': {'mapped': 8, 'mapping_missing': 1}, 'method_resolution': {'method_resolved': 8, 'method_missing': 1}, 'extraction': {'extracted': 9}, 'resource_recognition': {'resource_unmodeled': 4, 'not_attempted': 1, 'modeled_resource': 4}, 'analysis': {'not_applicable': 4, 'skipped': 1, 'analyzed': 4}}`。
非空资源单元完成 4，完成求解及选中范围回放的模块 3。
正式性质：full `{'unknown': 17, 'bounded': 1}`；消融 `{'unknown': 17, 'bounded': 1}`；确定性增益 0。
无独立 oracle，不能计算准确率/召回率，运行完成不构成方法有效性证据。

| 输入 | 原分析状态 | 方法身份 | 资源识别 | 当前分析 | 原因 |
| --- | --- | --- | --- | --- | --- |
| xxl-job-core-1 | skipped | method_resolved | resource_unmodeled | not_applicable | calls_without_modeled_resource_family |
| xxl-job-core-2 | skipped | method_missing | not_attempted | skipped | callable_not_in_extracted_inventory |
| xxl-job-core-3 | skipped | method_resolved | modeled_resource | analyzed | property_unknown |
| hertzbeat-common-core-1 | budget_exit | method_resolved | modeled_resource | analyzed | property_unknown |
| hertzbeat-common-core-2 | skipped | method_resolved | resource_unmodeled | not_applicable | calls_without_modeled_resource_family |
| hertzbeat-common-core-3 | skipped | method_resolved | modeled_resource | analyzed | property_unknown |
| hertzbeat-common-spring-1 | analyzed | method_resolved | modeled_resource | analyzed | property_unknown |
| hertzbeat-common-spring-2 | skipped | method_resolved | resource_unmodeled | not_applicable | calls_without_modeled_resource_family |
| hertzbeat-common-spring-3 | skipped | method_resolved | resource_unmodeled | not_applicable | calls_without_modeled_resource_family |

源码、DB、查询、选择与预算身份见 run-manifest.json 及其本地证据引用。common-core 从 29 文件 util 范围恢复 158 文件完整模块；旧/新 hash 见 metrics.json，不能将跨范围 steps 差异当算法收益。

同环境测试：baseline {'passed': 1191, 'failure': 12, 'error': 1, 'skipped': 41}；current {'passed': 1212, 'failure': 12, 'error': 1, 'skipped': 46}。逐 ID 差分见 baseline-test-diff.json。

成本、solver steps/抽象配置/widening/subsumption、关系数量和未测量字段均列在 metrics.json。

局限：build-mode=none 不证明编译或依赖完备；未知外部库行为保持 unknown。累计历史分配上界无穷不等于漏洞或结构性无界增长；不覆盖一般动态分派、深度>1、自定义异步或总字节预算。

复跑入口和下一阶段实验接续见 docs/execution/lifecycle-rc1/HANDOFF.md。

补充验收与解释：

- 合成回归：{'disable_cross_event_propagation': {'cases': 12, 'expected_matches': 12, 'unknown': 9}, 'full': {'cases': 12, 'expected_matches': 12, 'unknown': 3}}；合成确定性增益 6。它们是开发回归，不是独立研究证据。
- 固定九输入关系数量：{'call_bindings': 0, 'task_bindings': 0}；独立确定性增益 0。
- 原精确请求未被候选方法替换，方法身份差异的位置/hash/descriptor 见 input-ledger.csv。
- 入口对真实方法身份失败返回非零；rc_ready 表示 R1–R6 的受支持工程门槛通过，不表示九个方法均已分析成功。

| 模块 | 提取+适配 s | 求解+序列化 s | 回放 s | Python peak RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| xxl-job-core | 294.477 | 3.953 | 0.592 | 62.961 |
| hertzbeat-common-core | 334.817 | 6.487 | 0.987 | 157.762 |
| hertzbeat-common-spring | 306.673 | 0.860 | 0.102 | 36.738 |

同一冻结 ArrowUtil facts：steps 798 → 272；配置 798 → 259；最终 widening 40、subsumption 14。耗时 0.110377 → 0.055382 s，peak RSS 26580 → 24960 KiB。
这些是同机实际测量，包含并发负载影响；完整模块的不同源码范围成本另列，不作跨范围收益比较。
