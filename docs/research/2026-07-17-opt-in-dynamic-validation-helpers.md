# 独立 opt-in 动态验证辅助工具

`scripts/prepare_dynamic_validation_output.py` 与 `scripts/sync_dynamic_validation_status.py` 是独立、显式 opt-in 的本地证据管理辅助工具。它们**不属于静态分析流水线**：不会被静态扫描调用，不会改变静态结论，也不会把静态候选标记为动态确认。

两者均不启动服务、不发起 HTTP/协议请求、不生成压测、不访问网络或外部目标。任何动态验证都必须另行授权，并由操作者在隔离、可处置的本地环境中执行；其运行证据只能写入独立输出目录。

## 创建暂停中的证据骨架

```bash
python scripts/prepare_dynamic_validation_output.py \
  --input /absolute/path/to/static_candidates.jsonl \
  --output-root /absolute/path/to/dynamic-validation-output
```

输入为每行一个 JSON object 的 JSONL。常用字段为 `target`（或 `batch_target_name`）、`slug`（或 `batch_target_slug`）、`finding_id`、`probe_id`，以及静态候选的 source/sink/driver/request 信息。

输出目录包含：

- `manifest.normalized.jsonl`：规范化静态追溯记录；
- `validation_status.jsonl`：初始为 `paused` 的独立状态索引；
- `cases/<case-id>/`：每个候选的计划、环境/数据准备占位文件、日志和证据目录、暂停的 `result.json`；
- `DYNAMIC_VALIDATION_PLAN.md`：人工操作者的安全边界和候选清单，**不是执行器**。

`case_id` 由已清理的 `slug`、`finding_id`、`probe_id` 与原始静态记录的稳定 SHA-256 截断指纹组成。缺少 finding 或 probe 时使用显式的 `no-finding` / `no-probe` 段；这既保留候选身份，也避免名称碰撞。

默认情况下，输出根必须不存在或为空。非空根、已有 case、已有状态文件都会被拒绝，报错中会包含冲突路径。`--force` 是窄幂等选项：它只接受内容完全相同、从未触碰的 `paused` 骨架，并直接保留现有目录，不重写任何 case 文件。若任一 `result.json` 的状态不是 `paused`，或目录内容存在任何差异，`--force` 都会拒绝且绝不覆盖。

## 更新状态索引

在经独立授权的人工流程写入某个 `cases/<case-id>/result.json` 后，可运行：

```bash
python scripts/sync_dynamic_validation_status.py \
  --output-root /absolute/path/to/dynamic-validation-output
```

该命令只读取规范化 manifest 与各 case 的本地 `result.json`，生成状态索引；它不执行验证，也不修改 case 证据。写入 `validation_status.jsonl` 时，脚本会先在同一目录创建临时文件、flush/fsync，再用 `os.replace` 原子替换，避免读者看到半写入 JSONL。

结果文件的 `case_id` 必须与 manifest 对应 case 匹配；JSON 格式错误、缺少 manifest、重复 case ID、错误的字段类型或 case ID 不一致都会提供包含具体文件路径（JSONL 同时含行号）的错误。

## 结论边界

暂停占位结果固定为 `status: "paused"` 与 `verdict: "blocked"`，并明确说明它不是动态确认。状态同步只索引人工写入的结果，不能将任何动态结果回写为静态流水线 verdict。动态记录应保留独立部署条件、可达性、资源观测、失败信号、安全上限、停止条件、清理与利用条件摘要。
