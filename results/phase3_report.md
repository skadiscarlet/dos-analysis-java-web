# Phase 3 Unified Modeling Report

生成时间: 2026-06-18 09:59
状态: ✅ 已生成 Phase 3 统一候选特征

## 运行配置

- Query: `codeql/queries/phase3_candidate_features.ql`
- Selected frameworks: jersey, jetty, spring-boot, tomcat, undertow
- CodeQL binary: `/usr/bin/codeql`
- CodeQL threads: `16`
- CodeQL RAM MB: `20480`
- CSV schema: `framework, entry_fqn, entry_file, entry_line, sink_kind, sink_file, sink_line, key_kind, container_kind, axis_r, axis_v, axis_m, axis_c, axis_l, verdict_drd, verdict, evidence`

## 输入数据库

| Framework | Database | Status |
|---|---|---|
| tomcat | `databases/tomcat-9.0-db` | present |
| spring-boot | `databases/spring-boot-2.7-db` | present |
| jetty | `databases/jetty-11-db` | present |
| undertow | `databases/undertow-2-db` | present |
| jersey | `databases/jersey-3.1-db` | present |

## 执行记录

| Framework | Status | Rows | Notes |
|---|---|---:|---|
| tomcat | completed | 31 | `/usr/bin/codeql query run --database=/home/furina/new_tool/dos-analysis-web/databases/tomcat-9.0-db --output=/home/furina/new_tool/dos-analysis-web/results/phase3/tomcat_candidate_features.bqrs --threads=16 --ram=20480 /home/furina/new_tool/dos-analysis-web/codeql/queries/phase3_candidate_features.ql; /usr/bin/codeql bqrs decode --format=csv --output=/home/furina/new_tool/dos-analysis-web/results/phase3/tomcat_candidate_features.csv /home/furina/new_tool/dos-analysis-web/results/phase3/tomcat_candidate_features.bqrs` |
| spring-boot | completed | 30 | `/usr/bin/codeql query run --database=/home/furina/new_tool/dos-analysis-web/databases/spring-boot-2.7-db --output=/home/furina/new_tool/dos-analysis-web/results/phase3/spring-boot_candidate_features.bqrs --threads=16 --ram=20480 /home/furina/new_tool/dos-analysis-web/codeql/queries/phase3_candidate_features.ql; /usr/bin/codeql bqrs decode --format=csv --output=/home/furina/new_tool/dos-analysis-web/results/phase3/spring-boot_candidate_features.csv /home/furina/new_tool/dos-analysis-web/results/phase3/spring-boot_candidate_features.bqrs` |
| jetty | completed | 0 | `/usr/bin/codeql query run --database=/home/furina/new_tool/dos-analysis-web/databases/jetty-11-db --output=/home/furina/new_tool/dos-analysis-web/results/phase3/jetty_candidate_features.bqrs --threads=16 --ram=20480 /home/furina/new_tool/dos-analysis-web/codeql/queries/phase3_candidate_features.ql; /usr/bin/codeql bqrs decode --format=csv --output=/home/furina/new_tool/dos-analysis-web/results/phase3/jetty_candidate_features.csv /home/furina/new_tool/dos-analysis-web/results/phase3/jetty_candidate_features.bqrs` |
| undertow | completed | 42 | `/usr/bin/codeql query run --database=/home/furina/new_tool/dos-analysis-web/databases/undertow-2-db --output=/home/furina/new_tool/dos-analysis-web/results/phase3/undertow_candidate_features.bqrs --threads=16 --ram=20480 /home/furina/new_tool/dos-analysis-web/codeql/queries/phase3_candidate_features.ql; /usr/bin/codeql bqrs decode --format=csv --output=/home/furina/new_tool/dos-analysis-web/results/phase3/undertow_candidate_features.csv /home/furina/new_tool/dos-analysis-web/results/phase3/undertow_candidate_features.bqrs` |
| jersey | completed | 0 | `/usr/bin/codeql query run --database=/home/furina/new_tool/dos-analysis-web/databases/jersey-3.1-db --output=/home/furina/new_tool/dos-analysis-web/results/phase3/jersey_candidate_features.bqrs --threads=16 --ram=20480 /home/furina/new_tool/dos-analysis-web/codeql/queries/phase3_candidate_features.ql; /usr/bin/codeql bqrs decode --format=csv --output=/home/furina/new_tool/dos-analysis-web/results/phase3/jersey_candidate_features.csv /home/furina/new_tool/dos-analysis-web/results/phase3/jersey_candidate_features.bqrs` |

## 数据库候选分布

| Database Framework | Status | Candidate Rows |
|---|---|---:|
| tomcat | completed | 31 |
| spring-boot | completed | 30 |
| jetty | completed | 0 |
| undertow | completed | 42 |
| jersey | completed | 0 |

## 候选统计

总候选行数: 103

### Verdict 分布

| Verdict | Count |
|---|---:|
| Context-Constrained | 14 |
| Irrecoverable | 2 |
| Time-Constrained | 5 |
| Unconstrained | 47 |
| Unexploitable | 35 |

### Framework 分布

| Framework | Verdict Counts |
|---|---|
| servlet | Context-Constrained=8, Time-Constrained=5, Unconstrained=13, Unexploitable=7 |
| spring | Unexploitable=28 |
| undertow | Context-Constrained=6, Irrecoverable=2, Unconstrained=34 |

### Sink 分布

| Sink Kind | Count |
|---|---:|
| container_add | 31 |
| container_put | 63 |
| servlet_context_attribute | 4 |
| session_attribute | 5 |

## Verdict 一致性

- 总行数: 103
- 匹配行数: 103
- 不一致行数: 0
- 一致率: 100.00%
- 是否通过: True

## 当前保守假设

- 数据流仅覆盖入口方法内直接写入和一层同类/同包 helper 写入。
- 未识别的 auth guard 默认不降为 Blocked，避免误压真阳。
- 无法证明固定 key 时默认 Amplifiable，以保证召回。
- 日志、metrics、warning 不视为容量边界。

## 输出文件

```text
results/phase3/phase3_candidate_features.csv
results/phase3/phase3_consistency.json
results/phase3/<framework>_candidate_features.csv
```
