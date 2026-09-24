# FSE 工具修复：本轮结果与剩余关键路径

日期：2026-09-24。分支：`codex/fse-tool-repair-20260924`。
基线：`98997bbb7fba3e9287d54654cd197fa644ec56be`。
FSE 2027 Research Papers 全文截止：2026-10-02 AoE。来源：https://conf.researchr.org/track/fse-2027/fse-2027-papers 。

## 本轮实际交付

修复同一精确handler注册多个route时类型化认证/部署事实被丢弃的问题；HTTP规则匹配保留显式方法，不能把GET证据借给POST或方法未知的入口。partial、冲突、dynamic matcher的保守判定不放宽。

修复Growth内存/反序列化记录的类型和形状校验：`passed`必须是真正bool，检查名和原因必须满足类型要求；畸形check不能被静默过滤。该缺陷由合成接口测试证实；文件级loader已有schema保护，不据此声称历史真实结果含伪造证明。

生产entries身份v17→v18、growth v33→v34。缓存回归确认相应旧阶段及受影响下游重新执行。合成生产流水线覆盖bounded、static_vulnerable、证据不足unknown、resume、跨方法隔离及证书/报告一致性；不是新的真实召回或真实消融。

恢复测试可运行性：六个依赖历史资产的普通单元测试改为临时合成29-record/18-repository小fixture；保留真实资产集成测试及其原断言，仅明确缺失资产时skip。空/损坏manifest、晚位非法路径、符号链接不能靠skip隐藏。已迁移的项目skill可发现，缺失时明确skip，不再在收集阶段崩溃。

## 最终验收

| 层级 | 实际结果 | 可支持的结论 |
|---|---|---|
| 冻结全仓 | 1980 passed、0 failed、0 collection error、66 skipped；1100 subtests passed、9 warnings | 可运行的离线回归通过，不等于所有外部集成已运行 |
| 47项新增FSE回归 | 已包含在上述全仓数字中，不重复相加 | 绑定、类型、证据门槛、缓存、生产串联和fixture可移植性 |
| 原13失败 | 7通过、6因明确缺失历史资产skip | 不是“原13个集成全部通过” |
| 冻结下游回放 | 21/21项目；132 findings、126 families，132条unknown→unknown | 兼容性通过；不是重跑entries/Growth/Flow，更不是新的0/33实验 |
| 真实研究效果 | 上次正式召回0/33；本轮未重测真实召回和full/off消融 | research unvalidated，真实工具验收仍fail |

241个Python文件的冻结集合hash：`4716a41d3127ffd3ce1c464b06b95f8e1df9481c085c2a0fb7da30fe9b969bb6`，最终测试前后一致。
最初集成进程遇到并行补丁导致源码变化，其14个新Growth检查失败的混合版本结果只保留诊断，不作为最终验收；冻结后新进程完整重跑通过。

## 额外实际源码验收：未完成

仅使用仓库固定自有SourcePairs样例及原始oracle，静态编译与既有查询，不执行Java程序。首次调用因fixture数据库的/tmp快照源根与suite声明不一致，查询前被拒绝（status 5）。保护未放宽。

改用字节完全相同、源根与suite一致的独占副本后，javac/CodeQL建库成功，第一条ResourceLifecycleFacts查询已生成产物；第二条ResourceLifecycleTaskRelations仍处于pending时，240秒外层执行预算耗尽（exit -15）。没有完整source-evaluation，没有12例/24模式通过结论，也没有据此重测真实召回。

源码与oracle前后及副本哈希一致；无匹配的编译器残留进程。超时留下的唯一临时选择器查询已从生产query pack移至本轮.verification保留，其原始哈希已记录。此次失败不被合并进默认1980通过数字，也不把既有12例历史通过当成本轮结果。下一项源码级验收必须先解决可重复运行与阶段预算归因，再检查提取到证书的实际语义，不重跑大型目标。


## 面向投稿的剩余关键路径

**P0：以源码级闭环代替继续扩写基础设施。** 下一项修复必须从自有小型Java源码的可重复失败出发，经真实提取、前提验证、求解到证书；不得靠手填事实或仅测内部消费者宣布完成。每个新增修复保留修复前失败和修复后正反例。

**P0：对齐声明范围与资源维度。** 先完成当前声明支持的路径，未证明的Reachability/Growth/Flow继续unknown；task数量性质不能跨维度证明bytes增长。若现有样本与性质适用域不相交，应调整研究声明/评价设计并保留完整分母，而不是跳过困难样本或补造前提。

**P0：闭环成立后才评价方法收益。** 固定输入与版本，独立记录完整流程和full/off配对结果，区分首次生成、缓存复用、未覆盖和失败；没有真实性质消费与配对增益，不把回归通过写成方法有效。178-target扩张继续暂停。

没有预定“必须提升到多少召回”的结果，也没有后台续跑承诺。本轮工程修复完成度与论文实验证据成熟度必须分别判断。

## 证据位置

`test-summary.json`：完整命令、skip明细、旧失败逐项结局、独立/合成与真实指标口径。
`source-hashes.json`：241个源码hash；`full-suite.txt`：最终真实输出。
`replay-manifest.json`：21项目冻结回放、来源与结果hash。
`reachability-red.txt`、`growth-record-red.txt`：修复前失败；对应新测试均在最终全仓内。
