#!/usr/bin/env python3
"""运行 Phase 3 Web 统一候选特征提取。"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - 环境错误路径
    raise SystemExit("PyYAML is required. Install with: python3 -m pip install pyyaml") from exc

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config.yaml"

FIELDNAMES = [
    "framework",
    "entry_fqn",
    "entry_file",
    "entry_line",
    "sink_kind",
    "sink_file",
    "sink_line",
    "key_kind",
    "container_kind",
    "axis_r",
    "axis_v",
    "axis_m",
    "axis_c",
    "axis_l",
    "verdict_drd",
    "verdict",
    "evidence",
    "sink_id",
    "sink_fqn",
    "sink_shape",
    "growth_dimension",
    "growth_driver_kind",
    "growth_driver_expr",
    "growth_driver_index",
    "receiver_expr",
    "lifecycle_root",
    "retained_object",
    "retained_field",
    "retention_path",
    "receiver_proof",
    "proof_source",
    "proof_confidence",
    "proof_evidence",
    "request_flow_kind",
    "request_flow_proof",
    "call_path",
    "call_path_depth",
    "request_carrier_kind",
    "source_kind",
    "source_expr",
    "candidate_family",
    "deployment_condition",
    "capacity_hint",
    "demotion_reason",
    "debug_notes",
]


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"配置文件格式错误: {CONFIG_PATH}")
    return config


def run_command(command: list[str]) -> None:
    print("$ " + " ".join(command))
    subprocess.run(command, cwd=BASE_DIR, check=True)


def read_feature_rows(csv_path: Path, framework: str) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        required = [field for field in FIELDNAMES if field != "framework"]
        missing = [field for field in required if field not in reader.fieldnames]
        if missing:
            raise ValueError(f"{csv_path} 缺少字段: {', '.join(missing)}")
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized = {field: (row.get(field) or "") for field in FIELDNAMES}
            normalized["framework"] = normalized["framework"] or framework
            rows.append(normalized)
        return rows


def write_merged_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def run_framework(
    name: str,
    meta: dict[str, Any],
    query: Path,
    results_dir: Path,
    codeql_config: dict[str, Any],
    output_prefix: str = "candidate_features",
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    codeql = str(codeql_config.get("binary", "/usr/bin/codeql"))
    database = BASE_DIR / str(meta["database"])
    run_info: dict[str, Any] = {
        "framework": name,
        "database": str(database),
        "status": "pending",
        "rows": 0,
        "commands": [],
    }
    if not database.exists():
        run_info["status"] = "skipped"
        run_info["reason"] = f"database not found: {database}"
        print(f"SKIP: {name} database not found: {database}")
        return [], run_info

    bqrs_path = results_dir / f"{name}_{output_prefix}.bqrs"
    csv_path = results_dir / f"{name}_{output_prefix}.csv"
    query_command = [codeql, "query", "run", f"--database={database}", f"--output={bqrs_path}"]
    if codeql_config.get("threads") is not None:
        query_command.append(f"--threads={codeql_config['threads']}")
    if codeql_config.get("ram_mb") is not None:
        query_command.append(f"--ram={codeql_config['ram_mb']}")
    query_command.append(str(query))
    decode_command = [codeql, "bqrs", "decode", "--format=csv", f"--output={csv_path}", str(bqrs_path)]
    run_info["commands"] = [" ".join(query_command), " ".join(decode_command)]
    run_command(query_command)
    run_command(decode_command)
    rows = read_feature_rows(csv_path, name)
    run_info["status"] = "completed"
    run_info["rows"] = len(rows)
    print(f"{name}: {len(rows)} {output_prefix} rows")
    return rows, run_info


def parser_query_for(phase3: dict[str, Any]) -> Path | None:
    query_text = phase3.get("parser_query", "codeql/queries/phase3_parser_candidate_features.ql")
    query = BASE_DIR / str(query_text)
    return query if query.exists() else None


def auxiliary_queries_for(phase3: dict[str, Any]) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = []
    parser_query = parser_query_for(phase3)
    if parser_query is not None:
        queries.append({
            "framework": "jersey",
            "label": "parser",
            "query": str(parser_query),
            "output_prefix": "parser_candidate_features",
        })
    for item in phase3.get("auxiliary_queries", []) or []:
        if not isinstance(item, dict):
            raise ValueError(f"phase3.auxiliary_queries 项格式错误: {item!r}")
        framework = str(item.get("framework", "")).strip()
        label = str(item.get("label", "")).strip()
        query_text = str(item.get("query", "")).strip()
        output_prefix = str(item.get("output_prefix", "")).strip()
        if not framework or not label or not query_text or not output_prefix:
            raise ValueError(f"phase3.auxiliary_queries 项缺少必要字段: {item!r}")
        query = BASE_DIR / query_text
        if query.exists():
            queries.append({
                "framework": framework,
                "label": label,
                "query": str(query),
                "output_prefix": output_prefix,
            })
    return queries


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_framework: dict[str, Counter[str]] = defaultdict(Counter)
    by_verdict: Counter[str] = Counter()
    by_sink: Counter[str] = Counter()
    for row in rows:
        framework = row.get("framework", "unknown") or "unknown"
        verdict = row.get("verdict", "unknown") or "unknown"
        sink_kind = row.get("sink_kind", "unknown") or "unknown"
        by_framework[framework][verdict] += 1
        by_verdict[verdict] += 1
        by_sink[sink_kind] += 1
    return {
        "total": len(rows),
        "by_framework": {framework: dict(counts) for framework, counts in sorted(by_framework.items())},
        "by_verdict": dict(sorted(by_verdict.items())),
        "by_sink": dict(sorted(by_sink.items())),
    }


def render_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def write_report(
    path: Path,
    config: dict[str, Any],
    selected: set[str],
    run_infos: list[dict[str, Any]],
    summary: dict[str, Any],
    consistency: dict[str, Any],
) -> None:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Phase 3 Unified Modeling Report",
        "",
        f"生成时间: {generated_at}",
        "状态: ✅ 已生成 Phase 3 统一候选特征",
        "",
        "## 运行配置",
        "",
        f"- Query: `{config['phase3']['query']}`",
        f"- Selected frameworks: {', '.join(sorted(selected))}",
        f"- CodeQL binary: `{config.get('codeql', {}).get('binary', '/usr/bin/codeql')}`",
        f"- CodeQL threads: `{config.get('codeql', {}).get('threads', 'default')}`",
        f"- CodeQL RAM MB: `{config.get('codeql', {}).get('ram_mb', 'default')}`",
        "- CSV schema: `" + ", ".join(FIELDNAMES) + "`",
        "",
        "## 输入数据库",
        "",
        "| Framework | Database | Status |",
        "|---|---|---|",
    ]
    for framework, meta in config["frameworks"].items():
        if framework not in selected:
            continue
        database = BASE_DIR / str(meta["database"])
        status = "present" if database.exists() else "missing"
        lines.append(f"| {framework} | `{meta['database']}` | {status} |")

    lines.extend([
        "",
        "## 执行记录",
        "",
        "| Framework | Status | Rows | Notes |",
        "|---|---|---:|---|",
    ])
    for run_info in run_infos:
        note = run_info.get("reason") or "; ".join(run_info.get("commands", []))
        lines.append(f"| {run_info['framework']} | {run_info['status']} | {run_info.get('rows', 0)} | `{note}` |")

    lines.extend([
        "",
        "## 数据库候选分布",
        "",
        "| Database Framework | Status | Candidate Rows |",
        "|---|---|---:|",
    ])
    for run_info in run_infos:
        lines.append(
            f"| {run_info['framework']} | {run_info['status']} | {run_info.get('rows', 0)} |"
        )

    lines.extend([
        "",
        "## 候选统计",
        "",
        f"总候选行数: {summary['total']}",
        "",
        "### Verdict 分布",
        "",
        "| Verdict | Count |",
        "|---|---:|",
    ])
    for verdict, count in summary["by_verdict"].items():
        lines.append(f"| {verdict} | {count} |")

    lines.extend([
        "",
        "### Framework 分布",
        "",
        "| Framework | Verdict Counts |",
        "|---|---|",
    ])
    for framework, counts in summary["by_framework"].items():
        lines.append(f"| {framework} | {render_counts(counts)} |")

    lines.extend([
        "",
        "### Sink 分布",
        "",
        "| Sink Kind | Count |",
        "|---|---:|",
    ])
    for sink_kind, count in summary["by_sink"].items():
        lines.append(f"| {sink_kind} | {count} |")

    lines.extend([
        "",
        "## Verdict 一致性",
        "",
        f"- 总行数: {consistency.get('total', 0)}",
        f"- 匹配行数: {consistency.get('matched', 0)}",
        f"- 不一致行数: {consistency.get('mismatched', 0)}",
        f"- 一致率: {consistency.get('consistency', 0.0):.2%}",
        f"- 是否通过: {consistency.get('pass', False)}",
        "",
        "## 当前保守假设",
        "",
        "- 数据流仅覆盖入口方法内直接写入和一层同类/同包 helper 写入。",
        "- 未识别的 auth guard 默认不降为 Blocked，避免误压真阳。",
        "- 无法证明固定 key 时默认 Amplifiable，以保证召回。",
        "- 日志、metrics、warning 不视为容量边界。",
        "",
        "## 输出文件",
        "",
        "```text",
        str(config["phase3"]["merged_csv"]),
        str(config["phase3"]["consistency_json"]),
        "results/phase3/<framework>_candidate_features.csv",
        "results/phase3/<framework>_parser_candidate_features.csv",
        "results/phase3/<framework>_oauth_candidate_features.csv",
        "```",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", action="append", help="只运行指定 framework；可重复传入")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    phase3 = config["phase3"]
    codeql = str(config.get("codeql", {}).get("binary", "/usr/bin/codeql"))
    query = BASE_DIR / str(phase3["query"])
    auxiliary_queries = auxiliary_queries_for(phase3)
    results_dir = BASE_DIR / str(phase3["results_dir"])
    merged_csv = BASE_DIR / str(phase3["merged_csv"])
    consistency_json = BASE_DIR / str(phase3["consistency_json"])
    report = BASE_DIR / str(phase3["report"])
    results_dir.mkdir(parents=True, exist_ok=True)

    selected = set(args.framework or config["frameworks"].keys())
    unknown = selected - set(config["frameworks"].keys())
    if unknown:
        raise ValueError(f"未知 framework: {', '.join(sorted(unknown))}")

    rows: list[dict[str, str]] = []
    run_infos: list[dict[str, Any]] = []
    for framework, meta in config["frameworks"].items():
        if framework not in selected:
            continue
        framework_rows, run_info = run_framework(framework, meta, query, results_dir, config.get("codeql", {}))
        rows.extend(framework_rows)
        run_infos.append(run_info)
        for auxiliary_query in auxiliary_queries:
            if auxiliary_query["framework"] != framework:
                continue
            auxiliary_rows, auxiliary_run_info = run_framework(
                framework, meta, Path(auxiliary_query["query"]), results_dir, config.get("codeql", {}),
                output_prefix=auxiliary_query["output_prefix"],
            )
            rows.extend(auxiliary_rows)
            auxiliary_run_info["framework"] = f"{framework}:{auxiliary_query['label']}"
            run_infos.append(auxiliary_run_info)

    completed = [info for info in run_infos if info["status"] == "completed"]
    if not completed:
        summary = summarize([])
        consistency = {
            "total": 0,
            "matched": 0,
            "mismatched": 0,
            "consistency": 0.0,
            "pass": False,
            "mismatches": [],
        }
        write_report(report, config, selected, run_infos, summary, consistency)
        raise RuntimeError("所有选中的 framework 都被跳过，未生成任何 Phase 3 查询结果")

    write_merged_csv(merged_csv, rows)
    if rows:
        consistency_script = BASE_DIR / "scripts" / "check_phase3_consistency.py"
        run_command(["python3", str(consistency_script), "--input", str(merged_csv), "--output", str(consistency_json)])
        consistency = json.loads(consistency_json.read_text(encoding="utf-8"))
    else:
        consistency = {
            "total": 0,
            "matched": 0,
            "mismatched": 0,
            "consistency": 0.0,
            "pass": True,
            "mismatches": [],
        }
        consistency_json.write_text(json.dumps(consistency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = summarize(rows)
    write_report(report, config, selected, run_infos, summary, consistency)
    print(f"Wrote {merged_csv}")
    print(f"Wrote {consistency_json}")
    print(f"Wrote {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
