# Read-all / Lombok 中断修复交付（2026-10-06）

## 结论

已恢复上次结束但未消费的进程终态（16项源码回归通过），保留13个未交付文件的原始快照，并完成本轮read-all覆盖边界修复。分支为 `codex/readall-proof-repair-20261006`，实际工作树为 `.worktrees/resume-proof-closure-20261001`。不是新的21库33记录正式验收，当前同版本召回仍未评价。

## 实际修复

原中断补丁已加入 `StreamUtils.copyToString`、Servlet Filter到request wrapper及Lombok异常壳的初步支持。本轮没有将其直接作为完成品：独立源码反例表明，原来的Filter准入检查会漏掉未知构造器、Object类型别名、字段逃逸及发生在读取前的FilterChain；Lombok检查仅依据注解行和存在sneakyThrow，会把同一源码行上的额外catch/finally作用也误认为透明。

现在按具体程序关系验证：wrapper实参必须来自未改写请求及不变局部别名；元数据摘要绑定Servlet API声明而非任意同名override；未知调用、其他构造器、字段/数组写入和复杂控制流保留partial。FilterChain还需绑定同一chain参数，且CFG证明其执行不能到达当前wrapper构造点。这里是局部读取峰值的有限模型，不是任意框架/全服务器的安全证明。未建模配置/日志/辅助方法也不会因为未显式接收request就被默许。

Lombok只规范化透明异常壳：无finally/resources、唯一catch、catch内唯一throw、以未改写的同一catch变量作为真实库sneakyThrow的唯一实参。普通业务try/throw、副作用、同名源码方法以及无法满足这些关系的生成代码保留partial。它不会产生资源释放或字节上界证据。

`lifecycle` implementation从v22升至v23。旧v22缓存的新增回归修复前失败、修复后通过，要求重算lifecycle/conclude/report；没有改schema、oracle、匹配规则或漏洞标签。

## 真实验证

| 验证范围 | 结果 |
|---|---|
| 独立8项边界：原中断补丁 | 6 failed / 2 positive controls passed |
| 独立相同8项：当前模型 | 8 passed / 0 failed，测试源码及预期标签未变 |
| 组合自有Java/CodeQL源码回归 | 25 passed / 0 failed，185.72秒 |
| 默认全仓（/tmp、子进程umask022） | 2082 passed / 0 failed / 142 skipped；1100 subtests passed，114.78秒 |
| 旧v22缓存失效反例 | RED 1 failed；GREEN包含于默认全仓 |

独立8项已包含在组合25项中，不能把两者相加冒充不同用例。源码回归实际编译仓库夹具并执行生产CodeQL，Lombok场景使用本机真实注解处理器。默认全仓的142个skip并非已验证通过；本轮未排除测试文件，也未为求绿放宽测试标签。

`boundary-transitions.csv`逐行记录原样源码的3类coverage转移；`test-evidence.json`保存指标、版本和验证范围；`source-hashes.json`列出本次核对的源码；原始测试日志原样保留。独立证据在 `reports/readall-peer-20261006/`。

## 科研结果边界

本轮没有新的第三方源码扫描、远程模型调用、目标服务启动、PoC或压力请求。原v5仅有1项目2条基准记录：1条正式阳性、1条unknown，另31条not_in_run；这是旧实现的历史结果，不能与历史5条命中或本次25项测试累加。没有依据把当前版本写成33/33，也没有依据声称剩余真实记录的首阻塞已全部消失。

下一阶段的研究验证必须与本工程交付分开：先审阅仍不在封闭域内的调用效果和假设，再以清楚的输入/版本/运行范围评价。保留unknown，不能用“未发现直接request调用”代替缺失的副作用分析。

## 中断恢复

先读MCP主任务 `task_04725d453b274a108585` 的summary并检查needs_reconciliation。旧v5及本轮所有已结束测试不要重复启动。本分支包含继承的未交付补丁和本轮修复；原 `.worktrees/poc33-final-closure-20260925` 未覆盖，不能假设它已经包含这份新代码。实际交接见 `docs/execution/readall-proof-repair-20261006/HANDOFF.md`。提交后的收据保存在 `.verification/readall-proof-20261006/delivery.json`，最终SHA以MCP日志和该收据为准。

## 语义依据

Lombok官方SneakyThrows文档说明异常会原样抛出而不是被吞掉、包装或替换；它本身不证明任何资源减少。AST接口使用本机 `codeql/java-all/9.2.1` 的Statement/Expr源码核对，特别是CatchClause.getVariable返回LocalVariableDeclExpr，需再取实际变量。

官方参考：
```text
https://projectlombok.org/features/SneakyThrows
```
