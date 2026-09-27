# Wave B 语义修复交接

交付分支：`codex/waveb-semantic-maintenance-20260927`。
维护工作树：`.worktrees/waveb-semantic-maintenance-20260927`。
来源：原本地 agent 工作树 `.worktrees/poc33-final-closure-20260925` 的132项未提交源/测试改动已逐文件保全，快照提交 `a5f0e7c08d05ff72083e719d4296c058fba6e5a8`，父提交为 `42a15c8de64c190be6d5adaeea403d0dc5035f9a`。快照不是本轮新增贡献。

## 生产改动

1. Spring Security 有界单链 first-match/fallback，包括继承的 AbstractRequestMatcherRegistry API；未知、多链、条件或自定义配置不自动提升。
2. MVC 精确同实例字段注册，保留歧义注入、重赋值、条件注册、PathMatcher 和 Registration 逃逸的未知状态。
3. Lifecycle 精确 request read-all / wrapper 局部扫描域；有限流、自定义调用、调用者guard与未知来源仍保守处理。
4. 同anchor的partial不被complete覆盖；已经验证且严格绑定的防护反证不被“寻找其它防护不完整”错误否定。不存在有效防护的漏洞阳性仍需要原严格门槛。
5. entries v22 / lifecycle v21 / conclude v10；旧阶段和下游按内容/版本身份失效，不手工篡改manifest强制resume。

API提供方、密钥和生产Growth响应schema未更改。test-only scripted transport仅补齐新协议要求的已有same-flow事实引用。

## 验证与边界

实际自有Java源码通过javac和生产CodeQL查询；不是手填raw facts代替源码。完整原生生产回归使用真正的production client，但模型响应由本地scripted transport提供，不代表真实远程provider质量或真实库召回。

最终默认suite、原生E2E及同源重算结果以 `reports/waveb-semantic-maintenance/test-evidence.json`、`summary.md` 和对应输出摘要为准；不同运行不能重复相加。

已测旧Wave B v3的固定基准命中是5/33。修复后的Wave B v4/21库33记录召回本轮未重跑；不能把自有源码通过换算成33/33。

## 安全接续

`repair-transfer.json`记录仅本轮代码补丁的逐路径前后hash；只有原工作树前像全部相同且没有正在编辑它的进程，才能将该补丁应用回原目录。应用状态以单独 `application-receipt.json` 为准。不要将整个维护快照覆盖原目录，不更改原HEAD/index或用户未关联修改。

## 可重跑的自有源码回归

从交付代码所在目录执行。TMPDIR必须处于支持FICLONE的项目文件系统；本机/tmp是tmpfs，不应绕过原生数据库保护。

```bash
mkdir -p .verification/local-native-tmp
TMPDIR="$PWD/.verification/local-native-tmp" \
DOSWEB_RUN_CODEQL_FIXTURES=1 DOSWEB_RUN_DEEPSEEK_INTEGRATION=0 \
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_waveb_auth_semantics.py \
  tests/test_waveb_mvc_field_semantics.py \
  tests/test_waveb_custom_matcher.py \
  tests/test_waveb_registration_escape.py \
  tests/test_semantic_materialization_coverage.py

TMPDIR="$PWD/.verification/local-native-tmp" \
DOSWEB_RUN_CODEQL_FIXTURES=1 DOSWEB_RUN_DEEPSEEK_INTEGRATION=0 \
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_production_e2e.py::ProductionFixtureE2ETests::test_real_database_real_queries_real_client_cover_p0_scenarios_and_resume
```

普通全仓回归：

```bash
DOSWEB_RUN_CODEQL_FIXTURES=0 DOSWEB_RUN_DEEPSEEK_INTEGRATION=0 \
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
```

本轮未运行目标服务、Java程序、PoC、压力负载或第三方自主发现；未调用实际远程分析模型；历史证据资产保留。
