# 增长前缀效果：独立源码验收

日期：2026-10-09。主任务 `task_04725d453b274a108585`；独立验收 `task_c9b2dcdc7bf74dbeaa97`。

## 结果

同一份自有Java源码、相同19个期望标签：基线为 **7 failed / 12 passed**，候选为 **19 passed / 0 failed**。测试实际调用 javac 和 CodeQL，仅编译并分析自有Java夹具，没有执行Java目标程序、发送请求、运行PoC、调用模型或扫描第三方目标。

基线提交为 `01a8062aefd50ab021785927f8528f4f46ffde12`。候选生产文件 `RequestReadAllDomain.qll` 的SHA-256为 `5e137a3131b14f448f0503e5cca1754e7aec076c17017efda0f5610721453edc`，它来自主任务工作树的只读快照；direct/embedded一致后才运行。测试期间包hash再次核验不变，因此并发修改没有混入结果。

| 分组 | 基线 | 候选 |
|---|---:|---:|
| 七项后置/互斥效果 | 7项误拒绝为partial | 7项符合complete期望 |
| 基础无副作用对照 | 1项complete | 1项complete |
| 前置/求值顺序/循环/异常/别名/多调用点负例 | 11项partial | 11项partial |

这里的complete只是已声明**局部读取峰值**域的覆盖完整性，不是正式漏洞命中、不是全服务器安全、不是任意跨过程/异步生命周期证明。不能将19个夹具当成19个PoC，也不能将这些数字相加到已有真实库召回。

## 独立覆盖的边界

后置组包括读取后才执行的未知方法、未知构造器、字段写、数组写、右侧方法实参及size分支，以及无法走到该读取点的互斥return分支。其共同点不是源码行号更大，而是局部CFG上不存在effect到当前wrapper构造点的路径。

负例组保留真正前置的方法、构造器、字段/数组写，先求值的左侧实参、数组赋值LHS中的前置调用、循环回达、前置finally、wrapper实参中的未知转发、Object别名，以及同一wrapper构造器被一个闭合调用点和另一个未闭合调用点共享的情形。所有19项均实际生成了guard/bound/release三类coverage行。

方法实参的左右顺序不是文字游戏：Java规范要求按顺序求值实参，数组赋值的左侧选择也有规定的求值次序。测试用这两个独立结构检查实现是否真的使用控制流，而非简单比较源代码行号。

规范依据（只作语义解释，实际测试以本机CodeQL输出为准）：
```text
https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.7.4
https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.26.1
```

## 可复核身份

- 自有生成Java源码：`29f6f020d5687a4860a1414d4b6018e4b5d30ab974a1d4cb80498eba7d27097d`
- 独立测试文件：`1489ea3376640d4cc9ace92341eec1417c076afb6e9bf0f9dfde435902d06921`
- 基线helper：`111b5e2d709b61b7b86d7471d2b526aec285d7d855db19b3acfffce0de2d572e`
- 候选helper：`5e137a3131b14f448f0503e5cca1754e7aec076c17017efda0f5610721453edc`

`status.json`和`transitions.csv`记录结果；`red/green-manifest.json`记录包hash、源hash和标签；`red/green-rows.json`记录实际解码行；`red/green.log`保留真实pytest输出。基线33.83秒，候选36.23秒，均包含构建及静态查询，不能据此推算21库的总时间。

## 主任务集成

只需集成 `tests/test_prefix_effect_independent_20261009.py` 与本报告目录；**不要合并本独立工作树的旧生产代码**。在主任务当前代码下直接运行测试；在本独立基线树中复验候选时需明确提供已固定的候选query pack路径：

```bash
DOSWEB_RUN_CODEQL_FIXTURES=1 \
DOSWEB_PREFIX_PEER_PACK=/absolute/path/to/candidate/codeql \
python3 -m pytest -q tests/test_prefix_effect_independent_20261009.py
```

环境不支持显式Java/CodeQL验证时会skip；本次19项没有skip。普通默认单元测试数字与本源码集需分开报告。

## 仍未解决

该改动不能自动消除发生在读取之前的配置访问、记录对象构造或ThreadLocal/辅助方法的未建模副作用。它也没有重新运行真实21库/33记录评价。已存Erupt v7中的第二条unknown不能因为这些夹具转绿而被改写。后续需要带资源身份和具体调用目标的副作用摘要，或明确保留相关模型缺口。
