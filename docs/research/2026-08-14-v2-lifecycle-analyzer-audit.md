# v2 生命周期资源耗尽分析器审计

> **后续校正：** 2026-08-17 的零信任 production-code 审计发现 E→G、lifecycle path binding、Assertion applicability、默认配置和 provider audit 仍有 P0 blockers。本文件保留 corpus/entries Gate-A 历史结论；完整 P0 合规性以 `docs/research/2026-08-17-v2-p0-design-compliance-audit.md` 为准。

**日期：** 2026-08-14
**审计基准：** `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md`
**思想来源对照：** `docs/research/2026-07-14-lifecycle-centered-resource-dos-idea-design.md`

## 1. 口径

指定的 2026-07-14 文档描述完整研究路线，现行 P0 实施范围由 2026-07-18 approved design 收敛。因而本审计不把下列 deferred 能力误报为 P0 缺陷：异步 Release 证明、Assertion 3、生产者/消费者速率推理、自动动态 DoS 执行、ML/GNN。相关候选若依赖这些能力，必须输出 `static_unknown`。

## 2. 已满足项

| 要求 | 实现证据 | 状态 |
|---|---|---|
| 固定 `E -> G -> flow -> lifecycle -> conclude` 顺序 | `dosweb/pipeline.py:STAGES`、`dosweb/production.py` | 满足 |
| E、G、flow、Guard、Bound、同步 Release 分包 | `dosweb/entries/`、`growth/`、`flows/`、`lifecycle/` | 满足 |
| G1-G4 CodeQL 查询族 | `dosweb/codeql/pack/dosweb/Growth/*.ql` | 已实现，真实项目召回未验收 |
| Spring MVC、Servlet、Netty、MQTT 入口 | `Entries/*.ql`；另有 JAX-RS、gRPC 扩展 | 已实现；PoC-18 entries canary 18/18 完成 |
| bounded slice + Growth Contract + static verification | `dosweb/growth/{slices,contracts,evidence,verify}.py` | 满足单元契约 |
| Assertion 1/2 与三态结论 | `dosweb/conclude/` | 满足单元契约 |
| 生命周期证书和报告 | `dosweb/lifecycle/certificates.py`、`dosweb/report/` | 满足单元契约 |
| 可恢复、原子发布、内容绑定 | `dosweb/pipeline.py` | 满足单元契约 |
| 普通分析不执行动态 DoS | production pipeline 无动态执行器 | 满足 |
| 历史动态证据仅用于 benchmark oracle | `dosweb/benchmark/` | 满足架构隔离 |

针对核心逻辑的基线回归：

```text
python3 -m pytest -q \
  tests/test_assertions.py tests/test_lifecycle_bounds.py \
  tests/test_lifecycle_guards.py tests/test_lifecycle_releases.py \
  tests/test_flow_verification.py tests/test_growth_verification.py \
  tests/test_p0_end_to_end.py

77 passed, 90 subtests passed
```

## 3. Gate A+B 修复结果与剩余边界

### P0-A：真实 PoC 项目入口阶段稳定性（已解决）

PoC-29 的 18 个所属项目已生成完整、版本绑定的 batch plan。首次 `entries` 基线以 4 workers 执行时，Druid、HertzBeat、SkyWalking、Solr 均在入口阶段失败；对 HertzBeat 的 `SpringMvcEntries.ql` 独立 30 秒复现得到：

```text
CODEQL_QUERY_FAILED
stage=query_run
diagnostic=command deadline exceeded
```

当前 production 固定每条查询 300 秒，且 batch 默认允许并行大型数据库查询。失败工件只保存错误码和通用消息，丢弃 `stage/diagnostic/returncode`，导致批量运行无法区分超时、QL 编译错误和数据库错误。

修复后 Entry preflight 将 framework evidence absent、scan truncated 和 query failed 分开建模；未执行查询生成 coverage gap，查询失败的 `stage/diagnostic/returncode` 以有界 metadata 保留。Gate-A2 canary `poc18-entries-gatea2-20260816` 在 2 workers、单次尝试下 **18/18 completed，0 failed**，此前失败的 Druid、HertzBeat、SkyWalking 和 Solr 均完成入口阶段；但首轮 Druid/Presto 各出现 1 条 `JaxRsEntries.ql` 的 `bqrs_decode` 诊断（`decoded result violates its query contract`）。

根因定位为 entry query 的 `dynamic_unresolved` 分支把依赖 JAR 里解析出的 `.class` 字节码（如 `server/target/.../StatusResource.class`，`getStartLine()==0`）当作入口行，触发 decoder 的 `LINE_INVALID`，使整条 query 被 fail-closed 拒绝，连带丢弃同库真实源码入口。修复是在全部 6 条 entry query 上要求入口元素来自源码（`Method.fromSource()` 或 `getLocation().getFile().getRelativePath().matches("%.java")`），并同步 `codeql/dosweb/Entries/` 与 `dosweb/codeql/pack/dosweb/Entries/` 两份镜像。修复后重跑 `druid-presto-entries-fix-20260816`：Druid/Presto 均 0 diagnostics，`jax_rs` 由 `partial + query_failed` 恢复为 `complete`，真实源码 JAX-RS 入口被正常提取。

### P0-B：测试入口命令存在环境脆弱性，完整 suite 无快速反馈

直接执行 `pytest` 在当前环境中因 console-script 的 import path 不含仓库根目录而批量报 `ModuleNotFoundError: dosweb`；正确入口是 `python3 -m pytest`。完整 suite 又包含大型 inventory/资产检查，180 秒内未完成且 quiet 模式在 collection 阶段无进度，不能作为每次修复的短反馈环。

**影响：** 缺少明确的 fast/core、CodeQL fixture、asset/slow 分层，迭代容易把环境问题误判成实现问题。

### P0-C：fixture 契约测试默认不执行真实 CodeQL

`tests/test_codeql_entry_queries.py`、growth/lifecycle query fixture 受 `DOSWEB_RUN_CODEQL_FIXTURES=1` 控制。默认 536 个测试定义中，大量 query contract 只检查文本/schema，不能阻止“fixture 正确但大型数据库超时”的性能回归。

### P0-D：PoC benchmark 链级回放（部分解决）

现有 benchmark 能规范化 29 条 truth、绑定 18 个数据库并计算 entry/candidate recall，但没有强制每条 PoC 映射到同一条 `entry_id -> growth_id -> flow_id -> lifecycle_result -> certificate`，也没有区分：

- 当前 P0 可证明并应命中 `static_vulnerable` 的链路；
- 涉及异步 Release/Assertion 3，按现行规范应为 `static_unknown` 但仍须检出候选链路；
- oracle 元数据不足以唯一匹配 source/sink 的链路。

唯一匹配结果现已保存 `candidate_id/finding_id/entry_id/growth_id/flow_ids/certificate_id/static_conclusion`，可以回放实际命中链。剩余缺口是对全部 truth 完成真实 full run 后的逐 PoC source/sink/route 验收；当前不能用 fake provider 替代该验收。

### P0-E：错误工件不足以支撑自迭代（已解决）

`run.json` 和 batch state 仅保留 `CODEQL_QUERY_FAILED`，生产执行器未将安全裁剪后的 diagnostic 发布到 target-local 诊断工件。虽然 `AnalyzerError.details` 已做 2048-byte 限制和 secret redaction，信息仍在 pipeline failure publication 时丢失。

生产 Entry stage metadata 现保留有界、脱敏的 query diagnostic，batch 聚合同时发布 query count、skipped count、scan truncation 和 diagnostic count，无需人工重跑底层 query 才能分类失败。

### P0-F：全链路运行仍受 provider 授权门约束

现行 approved design 要求 full P0 的 DeepSeek Growth Contract 为 mandatory，当前进程没有 `DEEPSEEK_API_KEY`。不得通过 mock、历史动态 truth 或跳过 Growth Contract 来伪造普通 full 结论。入口、raw G、flow、lifecycle CodeQL 阶段仍可继续修复和验收；最终真实 full run 需要显式 remote authorization 与凭据。

### P0-G：205 corpus 与执行计划（已解决）

canonical inventory 已重算为 **205/205 valid CodeQL databases，0 incomplete**。源码 fingerprint 精确排除分析器自产的 `results/applications_static_analysis/**`，但项目自身其他 `results/**` 仍参与身份计算。已发布不可执行的正式计划：entries 为 205 queued。full-ready 计划现为 **205 全部 queued**——git-commit provenance 已不再作为门槛（本节下述 178 queued + 27 paused 是 2026-08-14 的历史口径）。full 计划只记录 provider intent，不代表已授权或已执行远程调用。

## 4. 审计结论

当前工具已满足开始 **205 entries 全量分析**的离线前置条件；205 databases 均可严格加载，PoC-18 entry canary 已稳定完成（含 JAX-RS 字节码行毒化的根因修复与 Druid/Presto 复验），覆盖缺口和查询失败可诊断，全套离线测试 572 passed / 5 skipped。**full 205 尚未获准执行**：真实 provider canary 和逐 PoC 全链验收仍待显式凭据与远程授权。（历史口径：2026-08-14 时 178 个 Git-attested target 已具备计划资格、27 个 tree-only target 保持 paused；该 provenance 门槛现已被移除，205 全部可 full 执行。）异步 Release 继续按 P0 规则保守输出 `static_unknown`。

## 5. 验收定义

修复完成必须同时满足：

1. 18/18 数据库完成 entry stage，失败时保留可操作的安全 diagnostic；
2. PoC-29 每条 truth 都有明确的 entry 匹配结果；
3. 每个 P0 可建模 PoC 至少有一条完整 `E -> G` flow；
4. lifecycle 工件记录 Guard、Bound、同步 Release 的候选和 effectiveness；
5. 依赖 deferred 异步语义的链路被检出但结论为 `static_unknown`；
6. 逐 PoC 证书与 truth 的 source/sink/route identity 可回放；
7. fast tests、CodeQL fixtures、PoC batch regression 分层通过；
8. 普通静态结果不读取动态 oracle 来改变结论。
