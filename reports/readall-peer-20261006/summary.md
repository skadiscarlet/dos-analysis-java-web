# Read-all 补丁独立边界复核

主任务：`task_04725d453b274a108585`。独立复核：`task_87f423ff9d0146dea8f2`。

## 已确认的修复前结果

被测冻结helper SHA-256：`e483106cf4365e65f3fad06bd64657d7b5dbfabf7277ca22a515e55fee461f63`。

真实自有Java编译、CodeQL LifecycleCoverage和原解码器执行结果：**4 failed / 1 passed，33.77秒**。这不是第三方项目扫描，也没有执行编译出的Java程序。

| 场景 | 预期覆盖 | 冻结补丁实际覆盖 |
|---|---|---|
| metadata_only | complete | complete（正例通过） |
| constructor_gate | partial | complete（错误闭合） |
| erased_alias_gate | partial | complete（错误闭合） |
| preceding_chain | partial | complete（错误闭合） |
| field_escape_gate | partial | complete（错误闭合） |

构造器门禁、Object类型别名传递和字段逃逸会使调用者中的请求大小检查消失于当前准入条件；在wrapper之前调用FilterChain则存在未分析的请求流消耗/修改。应保留partial或给出充分的路径/副作用证明，不能仅凭没有直接HttpServletRequest类型的未识别MethodCall就闭合。

## 专有测试与证据

- `tests/test_readall_peer_boundary_20261006.py`：五项Filter边界与三项Lombok异常壳边界；主线不应修改预期标签制造GREEN。
- `.verification/readall-peer-20261006/baseline-pack/`：修复前pack冻结副本。
- `.verification/readall-peer-20261006/red.log`：上述五项完整输出。
- `.verification/readall-peer-20261006/red/manifest.json`：源码、pack和锚点身份。
- `.verification/readall-peer-20261006/red/rows.json`：解码后的覆盖记录。

## Lombok 同源码行反例也已确认

真实Lombok annotation processor与同一个冻结旧pack结果：**2 failed / 1 passed / 5 deselected，33.63秒**。`generated_only`正例complete；`same_line_catch_effect`与`same_line_finally_effect`应partial却complete。

同源码行不能代替结构证明：catch除直接重抛以外的字段效果、finally效果都被旧谓词误当成生成代码忽略。建议只接受catch块唯一语句为对该catch变量的直接重抛，并排除finally/resources/额外效果；不得因行号相等信任任意source catch。

以上是两个独立运行，共8个互不重复测试场景：6个反例错误闭合，2个正例通过。测试源及预期标签已冻结，待主线生产修复后在原8项上验证GREEN。修复前日志/manifest/rows已复制到本报告目录，分别以`filter-red-*`和`lombok-red-*`命名。

## 所有权与结论范围

peer不改生产query、`production.py`、主线版本号或共享CHANGELOG，不提交/推送。生产修复和最终提交由主任务负责；最终应将本测试、证据摘要及必要CHANGELOG更新一起交付。这里复核的是分析器证明边界，不构成PoC-33召回增益，也不更新旧第三方运行的静态结论。

## 修复后独立验收已通过

主任务修复后的helper SHA-256：`111b5e2d709b61b7b86d7471d2b526aec285d7d855db19b3acfffce0de2d572e`。

原8个场景、原预期标签和相同测试文件（SHA-256 `4de24ce1240c49f25c23ed4de72f769885997bd5970dc4ad08237bd6077f33c4`）得到 **8 passed / 0 failed，80.84秒**。不是跳过失败用例，也没有改变测试标签。主线direct与embedded helper字节一致，并与独立冻结的受测helper相同。

六个反例现在保持partial；两个正例仍complete。GREEN日志、源码/pack/Lombok JAR身份及覆盖rows已保存为本目录的`green.log`、`filter-green-*`、`lombok-green-*`；机器可读总结见`status.json`。

本peer只交付专有测试和证据，不修改生产query或提交/push。主任务仍需完成版本/缓存回归、全仓验证和最终提交。8/8是边界回归结果，不是8条真实PoC命中，更不是21库33记录正式召回。
