# 阶段 D：已授权本地模块的静态源码评价

用户于本轮明确允许使用 `poc/` 所属源码和 CodeQL DB。授权解除后固定方法清单再提取；不导入原 PoC 判定、不执行 PoC 或项目代码。分析核心保持 `4c4b32cc7bbfa915b222a86b6c9621b1f4398627c55cb7a20cb5de4d4403d8b8`，不因独立输入修改规则。

## 输入与范围

- XXL-JOB core：原仓库 `frameworks/applications/xuxueli__xxl-job`，52 个主源码 Java 文件，3 个方法。
- HertzBeat common-core：原仓库 `frameworks/applications/apache__hertzbeat`，初始 158 个主源码 Java 文件，3 个方法；完整模块的第一条查询产生 8,885 行，超出解码器 4,096 行上限。后续完整保留 `org/apache/hertzbeat/common/util` 包的 29 个文件，选择方法及方法体不变，排除其余包并逐文件记录 hash。
- HertzBeat common-spring：同一已有仓库的独立模块，67 个主源码 Java 文件，3 个方法。

共 9 个原始请求。范围修订属于同一输入的重试，不新增独立样本。HertzBeat 两模块只计一个项目。具体可执行 JVM callable 和 tree hash 见 `inputs/*.json`；源文件/排除文件身份见 `reports/lifecycle-v1.2/independent/input-freeze.json`。

## 为什么新建数据库

现有数据库归档的 Java 文件均与 live 字节一致，但还有未归档源码：XXL-JOB 为 archive 123/live 168，HertzBeat 为 archive 926/live 1261。冻结检查器要求全树相等，因此拒绝旧 DB；没有改写原目录、删除源码或放宽校验。

新建 `--build-mode=none` 数据库，仅作静态源码提取，不声称项目编译完成。XXL-JOB 镜像仍有注释占位文件未被归档，严格检查继续拒绝，3 个失败保留。HertzBeat 主源码镜像/缩小后的完整 util 包保留原字节。测试、其他模块及外部依赖实现不在范围；buildless解析不能代替依赖完整性，未知关系继续保留。

## 持久原始证据

工作树：`/home/furina/new_tool/dos-analysis-web/.worktrees/resource-lifecycle-v1_2-20260914`

相对目录 `.local-runs/v1.2/independent-20260916/` 包含所有镜像源码、数据库、实际查询日志、初始失败、最终 project 台账及 replay.json：

- `xxl-job-core/`：严格快照失败，未绕过。
- `hertzbeat-common-core/`：完整模块初次失败；`diagnostic-extraction/failure.json` 和 database/log 中的 8,885 行原始查询证据。
- `hertzbeat-common-core-util-scope/`：完整 util 包的后续范围检查。
- `hertzbeat-common-spring/`：第二个已有模块。
- `selected-attempts.json`：最终报告采用的尝试目录；早期失败仍保留。

Git仅发布紧凑报告、输入清单、逐文件hash和重跑脚本；完整源码、DB及日志不提交。

## 从零重跑

依赖沿用 HANDOFF 的 Python/Java/CodeQL 版本。运行者须已有明确允许的原源码；没有自动下载。`--asset-root` 指主资产工作区，`--out` 必须为新目录。

```bash
python3 scripts/prepare_lifecycle_v12_independent.py \
  --asset-root /home/furina/new_tool/dos-analysis-web \
  --out .local-runs/v1.2/independent-new
```

该命令先核对全部冻结文件 hash，再按记录范围镜像；不修改方法或运行项目。以 common-core 为例（其他模块用同名目录与 manifest；core 必须用 util-scope manifest）：

```bash
codeql database create .local-runs/v1.2/independent-new/hertzbeat-common-core/database \
  --language=java --build-mode=none --threads=2 --ram=2048 \
  --source-root .local-runs/v1.2/independent-new/hertzbeat-common-core/source
python3 -m dosweb.cli resource-project \
  --manifest docs/execution/lifecycle-v1.2/inputs/hertzbeat-common-core-util-scope.json \
  --source-root .local-runs/v1.2/independent-new/hertzbeat-common-core/source \
  --database .local-runs/v1.2/independent-new/hertzbeat-common-core/database \
  --out .local-runs/v1.2/independent-new/hertzbeat-common-core/project
python3 -m dosweb.cli resource-replay \
  --run .local-runs/v1.2/independent-new/hertzbeat-common-core/project/analysis \
  --source-root .local-runs/v1.2/independent-new/hertzbeat-common-core/source
```

CLI replay 的结果返回给 dispatch，并不打印 JSON；若需要持久 JSON，调用同一公开 CLI dispatch：

```python
import json
from pathlib import Path
from dosweb.cli import dispatch, parse_cli_values
base = Path('.local-runs/v1.2/independent-new/hertzbeat-common-core')
result = dispatch(parse_cli_values(['resource-replay', '--run', str(base/'project/analysis'),
                                   '--source-root', str(base/'source')]))
(base/'replay.json').write_text(json.dumps(result, indent=2) + '\n')
```

从本轮保留结果生成报告：

```bash
python3 scripts/report_lifecycle_v12_independent.py \
  --root-run .local-runs/v1.2/independent-20260916 \
  --out reports/lifecycle-v1.2/independent
python3 scripts/report_lifecycle_v12.py \
  --root-run .local-runs/v1.2/final --out reports/lifecycle-v1.2 \
  --independent-report reports/lifecycle-v1.2/independent --delivery-reviewed
```

`--delivery-reviewed` 仅在核查完整台账、性质引用、实现身份和重跑路径后使用。新的运行目录要相应记录 selected-attempts.json；根报告保留原A–C验收身份，独立源码结果单独分层。没有可靠oracle，因此只报告覆盖、unknown、失败和同事实传播差异；不以旧OOM标签评估准确率。
