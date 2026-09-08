# Resource Lifecycle v1 仓库审计

## 结论

现有仓库已经具备成熟的 CLI、CodeQL 执行、严格 JSON、稳定标识、artifact 发布和 P0 生命周期候选判断。本轮不复制这些设施，也不改变 schema/tool `2.5/0.4.0` 的 P0 formal pipeline；新增独立 `resource-*` 纵向链路，将状态推导与旧的预计算候选字段隔离。

## 复用

| 路径 | 用途 |
| --- | --- |
| `dosweb/cli.py` | 同一命令入口和错误码风格 |
| `dosweb/artifacts/identifiers.py` | canonical JSON、SHA-256、stable id |
| `dosweb/codeql/runner.py` | 有界、可审计的 CodeQL query/bqrs 执行 |
| `dosweb/codeql/database.py` | 数据库与 source root 验证 |
| `dosweb/errors.py` | 受控错误与退出状态 |
| `tests/support/fixture_database.py` | 自包含 Java fixture 的真实 CodeQL 数据库 |

## 修改

| 路径 | 修改 |
| --- | --- |
| `dosweb/cli.py` | 添加 `resource-extract/analyze/replay/evaluate` 离线命令，保留原命令行为 |
| `dosweb/codeql/decoder.py` | 增加 lifecycle raw fact 的严格列契约和正整数 call-site column |
| `dosweb/codeql/runner.py` | 注册 lifecycle query output kind |
| `tests/support/fixture_database.py` | 扩充自包含 Java fixture 的真实 CodeQL 数据库内容 |
| `README.md` | 增加生命周期链路的安装、运行、重放和评价实命令 |
| `CHANGELOG.md` | 记录本轮新增语义、测试、报告和限制 |

## 新增

| 路径 | 职责 |
| --- | --- |
| `dosweb/resource_lifecycle/models.py` | 版本化 IR 与严格合法性检查 |
| `dosweb/resource_lifecycle/solver.py` | holder/obligation/size 状态与工作列表 |
| `dosweb/resource_lifecycle/events.py` | dispatch、队列、运行、完成、拒绝、取消 |
| `dosweb/resource_lifecycle/invariants.py` | 区间和简单线性有限上界检查 |
| `dosweb/resource_lifecycle/contracts.py` | 已验证 executor/API 契约 |
| `dosweb/resource_lifecycle/adapters.py` | CodeQL/JSON 事实转 IR 与覆盖统计 |
| `dosweb/resource_lifecycle/io.py` | 有界严格 JSON、IR round-trip 与原子 artifact 写入 |
| `dosweb/resource_lifecycle/summaries.py` | LLM 局部候选 schema、分层验证与 cache identity |
| `dosweb/resource_lifecycle/evidence.py` | 推导依赖和重新求解式 replay |
| `dosweb/resource_lifecycle/evaluation.py` | 固定输入回归、消融和指标 |
| `dosweb/resource_lifecycle/commands.py` | 四个 CLI 工作流 |
| `codeql/dosweb/ResourceLifecycle/`、`dosweb/codeql/pack/dosweb/ResourceLifecycle/` | 字节一致、不携带结论的 direct/embedded 源码事实查询；绑定 exact source callee 与 call-site column |
| `tests/fixtures/resource_lifecycle/` | 无网络 Java、人工 IR 和 24+ 语义回归 |
| `tests/test_resource_lifecycle_recorded_llm.py` | recorded summary 的 source snapshot、call-site/evidence、0600 私有 artifact 与 replay 完整性反例 |
| `reports/lifecycle-v1/` | 脱敏的固定输入评价产物 |
| `evaluation/historical_manifest.json` | 29 条历史 source record 的只读元数据清单，不作为 lifecycle ground truth |

## 弃用或明确不复用为证明前提

| 项目 | 处理 |
| --- | --- |
| `dosweb/lifecycle/*` 的 P0 candidate decision | 保留现状；不把其中 `actual_reduction`、`effective` 等字段输入新 solver |
| 历史动态验证状态 | 仅离线列清单，不提升本轮静态 lifecycle status |
| 方法名启发式、正则源码提取、LLM 最终结论 | 不作为 CodeQL 能力或确定性证明 |
| recorded LLM 的 solver enrichment | 当前 production QL 未提取独立 callee-summary witness；recording 仅验证/audit/display，重复 static operation 不再次执行，不能冒充 live LLM |
| 旧阶段化叙事和 legacy verdict compatibility | 不恢复；legacy 对照不可运行时写 N/A |

## 权威边界

现有 v2 P0 formal `analyze` 继续遵守 `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md` 和 schema/tool `2.5/0.4.0`。本轮目标文档的跨事件资源状态语义作为新增并行工具交付，不将其冒充为已扩展的 P0 formal verdict。
