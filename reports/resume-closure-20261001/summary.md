# 中断恢复与分析器修复交付

日期：2026-10-01。分支：`codex/resume-proof-closure-20261001`。

## 已恢复的真实结果，而不是重跑

上次 `poc33-final-closure-20260928-erupt-v5-full` 的进程已 exit 0，六个阶段均完成，耗时约1110.58秒。中断的是会话；本轮已读取终态并核对33个非私有产物的哈希及字节数，没有重复启动批次。

原始结果为1条 `static_vulnerable`、4条 `static_unknown`。原评价器离线匹配到 ERUPT-APP-STATIC-0001 为正式阳性，0002仍为unknown。本批次仅含1个项目/2条已知记录；另31条不在运行范围。原评价器的stage_failed字段在原文件中保留，但scope-aware ledger明确标为not_in_run，不能解释成31次运行失败。

这不是最新版21库全量结果，也不能把历史5条与本批次1条相加称为当前6/33。静态阳性不等于本轮动态确认，后续补丁没有在第三方目标上重新评价。21库/33记录科研验收仍未完成。

## 代码修复

1. 固化前轮的@Resource精确默认bean名、多条独立MVC注册以及HandlerMethod继承API修复；继续保留名字不匹配、歧义、条件注册、重赋值、不同实例等负面边界。
2. 本轮独立反例发现并修复三处边界：双首大写名字必须保留；未知Profile下的同名Bean不能视为不存在；用户重写getMethodAnnotation不能借用框架API的证明摘要。生产query direct/embedded镜像一致，没有项目/PoC特判。
3. 修复生命周期统计：旧实现把全部coverage记录都算partial。v5原始15行实际为9partial/6complete，而旧metadata错误显示15partial。新实现分别输出total、partial和complete；未修改或覆盖历史run.json，未改漏洞判定门槛。
4. entries版本升至v23，lifecycle升至v22；新增对旧entries-v22、lifecycle-v21缓存的失效回归。growth-v45、flows-v25、conclude-v10不变。

## 实际验证

| 范围 | 结果 |
|---|---|
| 独立MVC源码反例修复前 | 3 failed / 1 passed |
| 独立MVC源码反例修复后 | 4 passed / 0 failed；原测试与标签不变 |
| 原MVC源码回归 | 9 passed / 0 failed |
| coverage统计修复前 | 3 failed |
| 最终默认全仓（TMPDIR=/tmp、子进程umask022） | 2081 passed, 131 skipped, 9 warnings, 1100 subtests passed in 109.40s (0:01:49) |
| 受测源码一致性 | 535个Python/QL/Qll/Java文件全部匹配固定哈希 |

源码回归实际编译自有Java夹具并执行CodeQL；默认全仓中未启用的外部集成/CodeQL场景仍为skip，不能说所有外部集成都验证过。测试数字不相加冒充唯一用例总数。

### 保留的测试环境差异

MCP继承umask0077的首次全仓为4failed/2077passed/131skipped；四个夹具要求0755却实际创建为0700。未改测试/生产代码，单独子shell022下原4项全部通过。022+项目盘TMPDIR全仓出现另外6个失败（2075passed/131skipped），完整保留原日志，不宣称底层路径/文件系统差异已全部修复。最终在默认/tmp+022下完成上表回归。本轮没有为绿色删除测试、放宽缓存安全检查或全局修改主机umask。

## 实际位置与交接

原工作目录 `.worktrees/poc33-final-closure-20260925` 已含所有修复，不需要重复apply/cherry-pick。原HEAD/index与其他用户改动保持原样。独立交付worktree为 `.worktrees/resume-proof-closure-20261001`，从维护提交a2370a5建立；仅复制本轮和前轮未交付的10个源/测试文件，535个源文件与原受测树完全一致。

`v5-result-audit.json`记录原始运行/哈希和统计差异；`v5-record-ledger.csv`保留完整33行与运行范围；`test-evidence.json`和原始测试日志记录验证事实。交接见 `docs/execution/resume-closure-20261001/HANDOFF.md`。

## 剩余科研状态

既有第二条已知记录的Reach前提已经通过，但Lifecycle仍为request_read_all_stream_or_control_not_modeled，相关guard/bound/release覆盖partial；未将此类缺口删除或强改成阳性。当前有效边界只限上述静态子集，不覆盖任意注入、多个安全链、反射、复合注解或异步释放。本轮恢复没有新的目标扫描、远程模型调用、服务启动、PoC或压力请求。

主任务仍为partial/active，不将本轮工程交付标成33/33完成。之后恢复先读取MCP主任务与本HANDOFF；本轮所有已完成进程不得再次启动。

## 框架语义依据

Spring官方AnnotationBeanNameGenerator文档说明默认名的双首大写保留规则；Spring 6.2.6 AnnotatedMethod文档描述该类的getMethodAnnotation及HandlerMethod继承关系。代码只使用已验证的窄摘要，未声称实现全部注解查找语义。

- https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/AnnotationBeanNameGenerator.html
- https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/annotation/AnnotatedMethod.html
