# Wave B 语义修复：实际交付

日期：2026-09-27。交付分支 `codex/waveb-semantic-maintenance-20260927`。

**已修复工具并完成实际自有Java源码端到端回归。最小补丁已同步回原本地agent工作树；真实21库/33记录验收仍未完成，本轮未重跑Wave B v4。**

## 实际修改

- **Spring Security**：新增有界单链首次匹配/fallback，识别AbstractRequestMatcherRegistry继承声明；不把anyRequest当所有入口的全局低权限结论，多链/条件/动态/受限配置仍partial。
- **MVC**：精确同实例私有字段初始化及受限唯一注入绑定；歧义、重赋值、条件注册、另一个实例不提升。整条InterceptorRegistration的自定义PathMatcher、未知setter和对象逃逸会保留partial，包括位于排除规则之后的setter。
- **Lifecycle**：补齐已识别read-all和受控wrapper构造器的局部扫描域。有限流、自定义helper、caller guard、控制流、非请求来源及未覆盖释放证据均不伪造complete。
- **生产覆盖消费**：同anchor部分覆盖不能被同位置complete行吞掉。另一方面，已验证且严格绑定的有效防护反证不需要证明“寻找所有其它防护”已完成；原始scan partial保留，只有refuted断言有此例外，漏洞阳性的matched/unknown与Entry/Growth/Flow/候选gap门槛不放宽。

entries v22、lifecycle v21、conclude v10，旧相关阶段和下游缓存正确失效。API配置和生产Growth契约未更改；仅修正测试scripted响应缺必需的既有same-flow引用。

## 验证

| 验证范围 | 实际结果 | 限制 |
|---|---|---|
| 最终默认全仓 | 2076 passed，0 failed，124 skipped，1100 subtests；9 warnings | 未启用的可选CodeQL/外部集成仍skip，没有排除测试文件；不能称所有外部集成都验证 |
| Auth/MVC实际源码 | 16 passed；另1个Registration逃逸场景passed | 使用自有Java源码编译并执行生产CodeQL；包括已有MVC回归，不与全仓简单相加 |
| Lifecycle实际源码 | 14 passed | 同一14例修复前3failed/11passed；原始源码没有为了绿色而改标签 |
| 完整原生production源码E2E | 1 passed，2 subtests，452.68秒 | 原有全部三态、证书、报告、resume断言未删改；真实CodeQL及production client，模型响应是本地scripted transport |
| 同源证明义务修复核验 | 5 static_vulnerable / 1 bounded / 11 unknown | 自有fixture，不是33基准；严格只重算conclude/report，0新模型调用，后续resume不重跑 |
| 原用户工作树补丁后回归 | 见original-applied-regression.txt | 原HEAD和index不动，所有补丁文件after hash匹配 |

默认全仓测试前后533个Python/QL/Java源文件hash一致。源码级新增测试使用实际编译与查询，不靠fabricated raw事实冒充提取。完整production测试的模型部分仍是可重复的本地测试替身，不代表APIBasis当前响应质量。

## 不是掩盖测试失败

最初完整E2E在/tmp tmpfs无法FICLONE，被生产保护拒绝；改为项目盘btrfs的TMPDIR，未降低保护。随后发现旧scripted测试缺新协议所需引用，用RED2failed→对应125passed验证测试替身修复，生产schema未改。

最后实际源码产生/wrapper-guard的A1_EFFECTIVE_GUARD/refuted却仍unknown，证明是最终gate把存在有效防护与额外扫描完整性混淆；RED3failed/1passed→相关151passed验证后，再执行全新原生E2E通过。未删除原三态断言，不靠硬编码fixture route/FQN改变生产判断。

## 原目录已同步，未覆盖用户工作

原目录 `.worktrees/poc33-final-closure-20260925` 已应用29个源/测试文件的本轮最小补丁，逐文件before/after hash检查，并保留原HEAD `42a15c8de64c190be6d5adaeea403d0dc5035f9a` 及原index。125个未受修复影响的本地agent已改文件hash保持不变。CHANGELOG只前插本轮记录，原有字节完整保留。

原132项改动已在维护分支快照 `a5f0e7c08d05ff72083e719d4296c058fba6e5a8` 保存。该快照属于用户此前工作，不当作本轮新增贡献。应用前备份及receipt见application-receipt.json；它不是把整个快照覆盖原工作树。最小patch仅供审阅/其它同前像副本使用；**原目录已应用，不要再应用一次**。

## 真实科研结果边界

接管时核验的历史Wave B v3：7/7项目完成，45findings中7正式阳性；固定33记录实际匹配5/33。选中的10条记录是5positive+5unknown。未选记录不等于真实执行失败。

**本轮没有重新执行Wave B v4或21库fresh评价，不能据此宣称5/33提升、剩余5条已全部检出或33/33完成。** 代码支持的是上述可证子集，不是所有Spring DSL、任意有状态注入、任意wrapper/反射/异步生命周期。

没有运行任何目标服务、Java目标程序、PoC或压力请求；没有新增实际远程模型调用。原始DB、源码资产和历史结果未改写。详细语义边界与复跑命令见docs/execution/waveb-semantic-maintenance/。
