# E2E Semantic Repair：交付报告

日期：2026-09-23。分支：`codex/lifecycle-semantic-repair-20260922`。

**本轮工程修复已实现并验证，研究门槛为 partial，最终工具初验为 fail。** 固定21项目的认证冻结事实已完成下游回放；132条finding、126个family仍全部为`static_unknown`，正式已知记录召回仍为**0/33**。这不是“检测器已完成，只差人工复核”。

`delivery_state_at_commit=ready_for_push`。本文件描述提交时可核验的状态；实际提交和远端40位SHA一致性由提交后的Git核验及MCP持久日志记录，不在提交前声称已推送。

## 1. 本轮门槛与工具门槛

| 门槛 | 提交时状态 | 证据与限制 |
|---|---|---|
| S1 统计正确 | pass | 126个分析未知与0个待复核阳性分开；0/33保留，两种precision为null。 |
| S2 原因可追踪 | pass | 132 findings、126 families、33记录全部纳入；20条certificate-backed unknown追踪到上游；缺失证据明确标记。 |
| S3 实际修复 | partial | 已修复评价统计、消费者身份/假设丢失及其旧非证明记录兼容性，并有正反例；真实输入的Growth、可达性、循环/释放覆盖等主缺口超出本轮修复范围。 |
| S4 证据贯通 | pass | 7条具体假设贯通性质、绑定、decision、assertion、verdict、certificate及人读报告；错误资源/执行器/切面/假设被拒绝，实际性质消费量为0。 |
| S5 可比较 | pass | 同一冻结输入21/21回放，132条逐项unknown→unknown；27条canonical finding身份因旧非证明重建而变化，显式记录映射；33条全部保留。 |
| S6 可交付 | ready_for_push | 源码/实现身份、回归、可审阅报告及复跑命令齐备；实际commit/push/SHA一致性须在提交后验证。 |

最终工具初验：`overall_tool_acceptance=fail`。本轮未测得真实召回增长，也没有把合成反例通过解释为新漏洞发现。

## 2. 正式指标

| 指标 | 正确口径重算的旧批次 | 修复后的冻结下游回放 |
|---|---:|---:|
| 完成项目 | 21/21 | 21/21 |
| Findings / families | 132 / 126 | 132 / 126 |
| 正式阳性family | 0 | 0 |
| 阳性TP / FP / 未复核 | 0 / 0 / 0 | 0 / 0 / 0 |
| 分析unknown family | 126 | 126 |
| bounded family | 0 | 0 |
| 正式已知记录命中 | 0/33 | 0/33 |
| 已确认precision | null | null |
| 保守precision下界 | null | null |

Precision仅对正式阳性family计算：TP/(TP+FP)，保守下界TP/(TP+FP+阳性未复核)。零分母为null，状态`not_evaluable_no_positive`；126个unknown不是126个待复核阳性。0.8阈值仍是`proposed_default`，FPR仍是`not_measured`。

原有supported-chain子集20/29只是链路覆盖统计，不等于正式漏洞检出；ordinary-positive子集为0/6，也不能替换33分母。`metrics.json`保留两子集的成员、筛选口径和排除项。15条历史hard-negative全部为`unmatched_static_evidence`；已证实bounded、错误阳性、已匹配unknown、明确提取失败均为0。缺少匹配finding既不能证明提取失败，也不能证明安全；不以“不报阳性15/15”包装为有界证明。

## 3. 真实修复及为何不产生虚假召回

### 3.1 统计集合与具体匹配证据

正式阳性按family去重，unknown和bounded独立统计；未知对象上的误填阳性review标签不进入precision。阳性family中的另一条阳性成员不能替代oracle实际匹配到的unknown成员。合成检查覆盖零阳性、全unknown、部分阳性未复核、重复family、33集合之外的新阳性和具体finding级见证；1TP/1FP/1待复核的确认precision为0.5，保守下界为0.333333。合成数字不是实际benchmark结果。

### 3.2 资源性质消费完整性

原始基线上，一个真实合成solver得到的任务数量上界可被直接consumer API错配到另一executor、bytes分配或不同执行切面，并在混线的合成输入下传到bounded证书；binding保存的7条具体假设在中途丢失，证书仅有通用标签。这是接口与证据完整性缺陷，不是冻结真实批次已有false-bounded的证明。

修复后，decision与binding携带并校验entry/growth/path、性质、维度、作用域、切面、具体假设和canonical身份。消费端验证当前资源及执行上下文，不接受跨对象借用；具体假设进入断言、结论、证书和报告。最终源码的`assumption-chain-evidence.json`记录7条具体假设逐项到达报告；删除必要证书假设触发`ANALYSIS_CERTIFICATE_INVALID`。相关6项独立消费者检查由原5失败/1通过变为6通过。

### 3.3 旧非证明记录的认证重建

严格新校验使旧冻结结果中4项目、27条旧resource decision不可直接读取。它们为25条unresolved和2条not_applicable，全部没有性质或上界。仅增加显式保守兼容路径：先校验原始artifact字节、旧内层decision ID、旧外层lifecycle ID、完整binding和entry/growth/path；只对精确旧形状的非证明记录生成当前内存视图和新ID，再进行完整schema校验。冻结文件及其producer身份不改，旧绑定保留溯源。

严格`from_dict`不放宽；旧bounded、部分缺字段的新记录、错误/缺失binding、错上下文、unknown夹带上界、改旧ID均拒绝。conclude实现身份升至v9。两次失败回放17/21保留；最终合法回放21/21，132个verdict均不变。27条finding ID变化是认证重建后的身份变化，不是检出收益。

## 4. 未解决的真实前提

`prerequisite-status.csv`逐条保留同时阻塞项，`known-case-matches.csv`保留全部33条及新旧身份。按预设报告顺序，132条finding首先观察到的缺口为Growth 100、可达性19、生命周期13；这是报告顺序，不是互斥的因果证明。20条有证书但未命中的记录中，19条可达性未知、15条Growth未验证、14条Growth覆盖不完整，原因重叠，不能相加为记录数。

证据指向未覆盖或未证明的安全上下文、增长语义、循环/批处理放大、相关bound/release及CFG/别名等前提；不能通过删除相关coverage gap、把查询零行解释为不存在限制、或接受未验证的模型意见制造阳性。当前证据不足以把全部缺口收敛为一两个通用传递bug，因此S3保留partial。没有扩展一般循环证明、任意动态分派或新漏洞发现agent。

### Bridge实用量与交叉状态

统计单位为formal flow path，不与132条finding混同：共133条路径，其中6条kind/dimension适用；33条Growth和Flow前提已满足，但这33条均不属于当前可消费的task种类。交叉集合为空，因此当前backend eligibility gate满足数为0。三类交叉状态是94条kind/Growth/Flow均不满足、33条只有Growth/Flow满足、6条只有kind满足。

历史有27条binding记录，但性质产出0、成功性质绑定0、断言消费0，不能将“有binding记录”称为“已实际利用生命周期性质”。历史backend精确调用次数没有认证元数据，保留null及`exact_call_count_not_in_authenticated_metadata`，不由当前gate倒推出历史调用0。132条新旧verdict无变化；本轮没有重新开展full/off配对消融，`paired_full_off_gain=null`，只报告前后正式命中增长0。

## 5. 性质的正确消费边界

| 性质/证据 | 可支持的断言 | 单位 | 作用域与切面 | 不支持的结论 |
|---|---|---|---|---|
| accepted_task_population有限上界 | A2中同一executor对应任务数量增长的反证 | 任务个数 | 同task binding、实例及executor；保留性质原有cut和任意有限外部接受次数的归纳假设 | 不能反驳任意bytes分配；不能证明所有资源安全；不能单独生成漏洞阳性 |
| 旧unresolved/not_applicable记录认证重建 | 仅保留原非证明状态与溯源 | 无新增资源性质 | 原entry/growth/path及binding | 不能恢复旧bounded，不能将缺失假设补成证明 |

没有额外接入同步性质：本轮未取得同一真实候选上完整、适用的现成性质与绑定证据；这不等于断言后端完全没有同步性质。仍保留：出口不持有≠峰值有界，close≠GC，单项大小≠总体数量，任务终止后的释放≠及时终止，unknown或widening∞≠已证明可积累，不同资源/持有者不能借用上界。

## 6. 验证、身份与成本

全仓可收集测试：**1913 passed、13 failed、60 skipped、1095 subtests passed**，pytest真实退出码1。与相同umask0022基线的1878 passed/13 failed比较，新增失败ID为0，13条失败仍存在；包括已有版本期待和未挂载canonical/历史资产依赖。另有1个全局skill迁移导致的已知收集错误明确排除，不能称全仓全绿。首次集成新增的两项失败是旧proof-gate测试mock边界与完整record契约不符，已更新fixture，并保留原unknown断言与真实schema校验；前后失败日志留在本地复核目录。

生产/统计/证据/兼容相关回归230 passed、110 subtests；最终proof-gate fixture与证据测试35 passed、4 skipped、5 subtests。这些是不同测试运行，不能相加当作唯一测试数。完整命令、失败ID、源码hash与日志hash见`test-evidence.json`。

实际测试时HEAD为`3e2690ec55e14bd62fcea85e97d17cec2a71b43b`，工作树含修复，不能仅凭该旧commit复现修复。234个dosweb/scripts/tests Python文件的测试内容hash为`bbf32d6175cedea3d2439d2ead33c82417fef4169fde783e34edf94278226b7e`，核验前后不变。回放的dosweb源码范围hash为`9a94aba5806d59805f39d1d8659a17d993c44b07f1a578f83d403c2f100c9eec`，范围不同，勿混用。提交时逐文件校验与已测源码一致；评估辅助脚本另记录hash并已实际执行。

本轮重新校验21项目693个公共产物身份，复用原始源码/DB/配置/查询指纹；没有重新校验当前live源码或canonical DB内容。168 selected queries是历史entries阶段的元数据，不是本轮新增执行。**新增CodeQL查询0、模型调用0、目标程序/服务/PoC执行0**。

## 7. 文件与贡献来源

`run-manifest.json`记录源码/实现/输入/预算/输出身份，`replay-run-manifest.json`和132条`finding-transitions.jsonl`提供逐项目与逐finding复查。33条已知记录及其原始短ID保留，评价侧只做同仓库、唯一别名对应，不把oracle送入生产分析器。`positive-review.csv`只有表头，`analysis-unknown.csv`为126个unknown family，详细前提在132行表中。

检测到同一目标的并发任务后，先独立复核并将缺陷反馈给其子代理；随后对其已验证代码做带hash的固定快照，加入本分支的旧非证明兼容修复、最终集成验证与交付。`source-provenance.json`记录来源，不把合作实现冒称独立重写。另一个20260923工作树、外层AGENTS/CHANGELOG等用户修改、canonical资产和历史报告均未被覆盖。

完整DB、源码资产副本、私有模型响应、密钥、原始大型回放输出不提交。重现冻结评价需要本地保留的run目录；没有这些资产时只能执行合成和可用的回归测试，不能独立声称重现0/33真实结果。复跑步骤见同分支`docs/execution/lifecycle-semantic-repair/HANDOFF.md`。交付后停止，178-target保持暂停。
