# 增长前缀语义修复与既有v7评价

日期：2026-10-09。分支：`codex/growth-prefix-repair-20261009`。基线：`01a8062aefd50ab021785927f8528f4f46ffde12`。实际工作树：`.worktrees/resume-proof-closure-20261001`。

## 本轮结论

已修复一个确定的建模错误：分析器把资源增长之后的调用、构造或写操作，也当作当前局部读取峰值的前置未知效果，从而错误维持partial。本轮用控制流前缀关系纠正这一点，不把任意未知helper解释为无副作用。同时修复既有PoC-33评价中“未选中运行”被记为“运行失败”的统计错误。21库33记录的同版本全量目标仍未完成，没有新的真实召回提升可报告。

## 核心语义变化

对于同一调用者中的效果e和request wrapper构造点g，只有两者均有CFG节点、且不存在从e到g的控制流路径时，才能把e排除出g的执行前缀。判断不是依靠源码行号，也不是因为e没有显式接收request。

例子：先读取完整请求，再调用校验函数，校验不能反向限制已经出现的读取峰值。反过来，先校验再读取，或有循环使后续效果能回到读取点，则仍需建模这些效果。互斥且直接返回的分支同样通过CFG判定，不靠文本顺序。

生产修复覆盖后置方法调用、独立构造器、字段/数组写；外层构造器如`new Outer(new Wrapper(request))`不据此视为纯后置，因为其初始化及实参求值边界不同。缺失CFG、真正前置调用、Object别名中的未知效果、循环/异常复杂控制、同一wrapper共享不闭合调用点仍保持partial。后置效果可能影响后续保留/释放；本修复只处理局部读取峰值，不证明全生命周期或服务器安全。

修改位于两份镜像`RequestReadAllDomain.qll`；`lifecycle`版本升至v24，旧v23缓存必须重算lifecycle/conclude/report。没有修改Growth/Auth verifier、oracle标签或生产判定门槛。

## 实际验证

| 验证 | 结果 |
|---|---|
| 主线原9个前缀场景修复前 | 4 failed / 5 passed |
| 同一源码同一期望修复后 | 9 passed |
| 扩展12个前缀场景 + 原25个Java/CodeQL/Lombok回归 | 37 passed / 0 failed，207.71秒 |
| 独立19个前缀边界：基线 | 7 failed / 12 passed |
| 独立19个前缀边界：候选及主树复验 | 均19 passed / 0 failed；主树34.17秒 |
| 原生运行范围新测试 | 修复前10 failed；修复后10 passed |
| 运行范围与既有truth/evaluator组合 | 77 passed / 52 subtests passed |
| 旧v23缓存失效 | 修复前1 failed；修复后纳入全仓通过 |
| 最终默认全仓 | 2093 passed / 0 failed / 173 skipped / 1100 subtests passed，111.12秒 |

源测试实际编译自有Java并执行生产CodeQL；没有执行Java目标程序。默认173个skip包含未启用的源码/外部集成场景，不代表全部已验证通过。以上为不同或重叠运行，不能将重复通过数相加冒充唯一用例总数。

## v7后置正式评价

复用的是已结束批次的产物，不是重跑v7或从历史结果拼出新版结果。原评价与新评价的33个record ID和顺序保持一致；对实际运行的两条记录，剔除新增scope字段后，完整disposition逐项一致。

- `ERUPT-APP-STATIC-0001`：`static_vulnerable`。
- `ERUPT-APP-STATIC-0002`：`static_unknown`。
- 另外31条：`not_in_run`，不再误记31次stage_failed。

新scope以已验证plan digest和精确target binding为依据。被选中但没有结果的项目仍记失败；缺少可信计划时保留unverified_scope，不能仅凭没有目录就排除。损坏计划、跨run绑定、缺失binding和冲突产物被拒绝。报告格式为v3，固定33条分母没有缩减。`in_run`仅表示在运行计划内，并不自动表示成功完成。

v7的33个非私有声明产物均核验hash和字节数，私有audit未读取；原结果文件未更改。归档truth中的动态标签不代表本轮开展过动态验证。

## 剩余研究边界

真实Erupt第二条仍有发生在资源增长之前的配置访问、记录对象构造、ThreadLocal及辅助调用等未建模效果。它们不能被本轮“增长之后的效果无关”规则自动消除，仍需绑定具体调用目标和资源身份的副作用摘要及正反例证明。本轮未产生它的新正式阳性，也未执行新的21项目同版full。研究主Goal保持partial。

## 文件与可恢复性

`test-evidence.json`记录版本和验证范围；`prefix-transitions.csv`保存主线前后变化；独立报告位于`reports/prefix-independent-20261009/`；`v7-record-ledger.csv`保留完整33条；`v7-public-artifact-audit.json`记录原产物核验。

最终545个稳定Python/QL/Qll/Java源码hash已逐项核对。第一次并发采样的546项包含1个测试执行期间生成、随后自动删除的临时`.LifecycleCoverage.dosweb.*.ql`；原采样与排除说明均保留，未把临时生成query当成交付源码。此次报告生成失败日志也在MCP中保留，不影响已完成测试结果。

本轮未运行目标服务、PoC、压力负载、新第三方扫描或远程模型。没有合并默认分支，也不覆盖原poc33脏工作树。提交后的SHA、推送核验和进程终态以最新MCP检查点及`.verification/growth-prefix-20261009/delivery.json`为准。
