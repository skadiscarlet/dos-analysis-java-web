#!/usr/bin/env python3
"""Phase 4 大规模挖掘、排序、复核队列与报告生成。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - 环境错误路径
    raise SystemExit("PyYAML is required. Install with: python3 -m pip install pyyaml") from exc

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config.yaml"

INPUT_FIELDS = [
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
]

PROOF_FIELDS = [
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

OUTPUT_FIELDS = [
    "phase4_id",
    "score",
    "priority",
    "review_status",
    "review_focus",
    *INPUT_FIELDS,
    *PROOF_FIELDS,
]

VERDICT_WEIGHT = {
    "Irrecoverable": 1000,
    "Unconstrained": 800,
    "Time-Constrained": 520,
    "Context-Constrained": 260,
    "Unexploitable": 0,
}

AXIS_WEIGHT = {
    "axis_r": {"Open": 80, "WeakGated": 45, "PermGated": 15, "Blocked": -200},
    "axis_v": {"Stream": 120, "Unlimited": 90, "Limited": 20, "Uncontrollable": -120},
    "axis_m": {"Amplifiable": 110, "CallerBounded": -160},
    "axis_c": {"Unbounded": 130, "PerElementUnbounded": 85, "Bounded": -130},
    "axis_l": {"RebootPersistent": 160, "ProcessLifetime": 90, "Evicted": 15},
}

SINK_WEIGHT = {
    "session_attribute": 80,
    "servlet_context_attribute": 75,
    "container_put": 65,
    "container_add": 60,
}

CONTAINER_WEIGHT = {
    "persistent_store": 120,
    "session_store": 95,
    "servlet_context": 80,
    "session": 70,
    "static_container": 55,
    "lifecycle_field_container": 70,
    "framework_registry": 80,
    "parser_transaction": 55,
    "unknown_container": -160,
}

NOISE_PATH_MARKERS = (
    "/test/",
    "/tests/",
    "/src/test/",
    "webapps/examples/",
    "spring-boot-smoke-tests/",
    "/examples/",
    "Test",
)

LIKELY_REQUEST_LOCAL_EVIDENCE = (
    "HeaderMap.",
    "Setter<",
    "RepresentationModel<",
)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误: {CONFIG_PATH}")
    return data


def phase4_config(config: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "input_csv": "results/phase3/phase3_candidate_features.csv",
        "results_dir": "results/phase4",
        "ranked_csv": "results/phase4/ranked_candidates.csv",
        "ranked_json": "results/phase4/ranked_candidates.json",
        "review_queue_md": "results/phase4/review_queue_top50.md",
        "review_queue_json": "results/phase4/review_queue_top50.json",
        "evaluation_json": "results/phase4/evaluation_summary.json",
        "report": "results/phase4_report.md",
        "top_n": 50,
    }
    merged = dict(defaults)
    user_config = config.get("phase4", {})
    if isinstance(user_config, dict):
        merged.update(user_config)
    return merged


def resolve(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else BASE_DIR / path


def normalize(value: str | None) -> str:
    return (value or "").strip()


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Phase 4 输入不存在: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Phase 4 输入为空: {path}")
        missing = [field for field in INPUT_FIELDS if field not in reader.fieldnames]
        if missing:
            raise ValueError(f"{path} 缺少字段: {', '.join(missing)}")
        return [
            {
                **{field: normalize(row.get(field)) for field in INPUT_FIELDS},
                **{field: normalize(row.get(field)) for field in PROOF_FIELDS},
            }
            for row in reader
        ]


def is_noise_path(row: dict[str, str]) -> bool:
    combined = f"{row['entry_file']} {row['sink_file']}"
    return any(marker in combined for marker in NOISE_PATH_MARKERS)


def is_likely_request_local(row: dict[str, str]) -> bool:
    evidence = row.get("evidence", "")
    return any(marker in evidence for marker in LIKELY_REQUEST_LOCAL_EVIDENCE)


def score_row(row: dict[str, str]) -> tuple[int, list[str]]:
    score = VERDICT_WEIGHT.get(row["verdict"], 0)
    focus: list[str] = []

    for axis, weights in AXIS_WEIGHT.items():
        score += weights.get(row.get(axis, ""), 0)

    score += SINK_WEIGHT.get(row["sink_kind"], 0)
    score += CONTAINER_WEIGHT.get(row["container_kind"], 0)

    if row.get("receiver_proof"):
        score += 80
        focus.append("已有 receiver_proof，复核 retained path 和 growth driver")
    elif row["container_kind"] == "unknown_container":
        score -= 240
        focus.append("缺少 receiver proof，默认不作为 P0/P1 主候选")

    if row.get("proof_confidence") == "debug":
        score -= 180
        focus.append("proof confidence 为 debug，仅作噪声审计")

    if row.get("request_flow_proof"):
        score += 35
        focus.append("已有 request_flow_proof，复核 call path")

    if row["key_kind"] in {"request_derived", "unknown"}:
        score += 70
        focus.append("确认 key 是否真正由攻击者控制且可制造大基数")
    elif row["key_kind"] == "constant":
        score -= 220
        focus.append("常量 key，优先确认是否只是覆盖同一元素")

    if row["axis_c"] in {"Unbounded", "PerElementUnbounded"}:
        focus.append("检查是否存在隐藏容量上限、LRU、quota 或清理路径")
    if row["axis_l"] == "RebootPersistent":
        focus.append("确认状态是否跨重启或外部持久化")
    if row["verdict"] in {"Irrecoverable", "Unconstrained"}:
        focus.append("优先做源码复核和最小动态验证设计")

    if is_noise_path(row):
        score -= 260
        focus.append("路径位于测试、示例或 smoke test，默认不作为漏洞候选")

    if is_likely_request_local(row):
        score -= 180
        focus.append("evidence 像请求局部状态，确认是否长生命 retained state")

    if row["axis_m"] == "CallerBounded":
        focus.append("CallerBounded 通常不可放大，复核是否存在多主体绕过")

    return max(score, 0), focus


def priority(score: int, verdict: str) -> str:
    if verdict in {"Irrecoverable", "Unconstrained"} and score >= 900:
        return "P0"
    if score >= 700:
        return "P1"
    if score >= 420:
        return "P2"
    return "P3"


def rank_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    ranked: list[dict[str, str]] = []
    for row in rows:
        score, focus = score_row(row)
        enriched = {
            "phase4_id": "",
            "score": str(score),
            "priority": priority(score, row["verdict"]),
            "review_status": "pending",
            "review_focus": " | ".join(dict.fromkeys(focus)),
            **row,
        }
        ranked.append(enriched)

    ranked.sort(
        key=lambda item: (
            int(item["score"]),
            VERDICT_WEIGHT.get(item["verdict"], 0),
            item["entry_fqn"],
            item["sink_file"],
            item["sink_line"],
        ),
        reverse=True,
    )
    for index, row in enumerate(ranked, start=1):
        row["phase4_id"] = f"WEB-P4-{index:04d}"
    return ranked


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def summarize(rows: list[dict[str, str]], top_rows: list[dict[str, str]]) -> dict[str, Any]:
    by_verdict = Counter(row["verdict"] for row in rows)
    by_priority = Counter(row["priority"] for row in rows)
    by_framework = Counter(row["framework"] for row in rows)
    by_sink = Counter(row["sink_kind"] for row in rows)
    by_container = Counter(row["container_kind"] for row in rows)
    production_like = sum(1 for row in rows if not is_noise_path(row))
    request_local = sum(1 for row in rows if is_likely_request_local(row))
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_candidates": len(rows),
        "top_queue_size": len(top_rows),
        "production_like_candidates": production_like,
        "test_or_example_candidates": len(rows) - production_like,
        "likely_request_local_candidates": request_local,
        "by_verdict": dict(sorted(by_verdict.items())),
        "by_priority": dict(sorted(by_priority.items())),
        "by_framework": dict(sorted(by_framework.items())),
        "by_sink": dict(sorted(by_sink.items())),
        "by_container": dict(sorted(by_container.items())),
        "top_ids": [row["phase4_id"] for row in top_rows],
    }


def md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def write_review_queue(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 4 Top Candidate Review Queue",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 复核规则",
        "",
        "- 先确认 entry 是否真实暴露给远程/低权限客户端。",
        "- 再确认 key 是否可由攻击者制造大基数，而不是固定覆盖。",
        "- 最后确认 container 是否跨请求保留且缺少硬上限、LRU、quota 或移除路径。",
        "",
        "| ID | Priority | Score | Verdict | Entry | Sink | Evidence | Review Focus | Status |",
        "|---|---|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        entry = f"{row['entry_fqn']} ({row['entry_file']}:{row['entry_line']})"
        sink = f"{row['sink_kind']} ({row['sink_file']}:{row['sink_line']})"
        lines.append(
            "| "
            + " | ".join(
                [
                    row["phase4_id"],
                    row["priority"],
                    row["score"],
                    row["verdict"],
                    md_escape(entry),
                    md_escape(sink),
                    md_escape(row["evidence"]),
                    md_escape(row["review_focus"]),
                    row["review_status"],
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items()) if counts else "-"


def write_report(path: Path, summary: dict[str, Any], cfg: dict[str, Any], top_rows: list[dict[str, str]]) -> None:
    lines = [
        "# Phase 4 Large-Scale Mining Report",
        "",
        f"生成时间: {summary['generated_at']}",
        "状态: 已生成 Phase 4 排序候选、top-N 人工复核队列和评估摘要。",
        "",
        "## 输入与产物",
        "",
        f"- 输入: `{cfg['input_csv']}`",
        f"- 排序 CSV: `{cfg['ranked_csv']}`",
        f"- 排序 JSON: `{cfg['ranked_json']}`",
        f"- 复核队列 Markdown: `{cfg['review_queue_md']}`",
        f"- 复核队列 JSON: `{cfg['review_queue_json']}`",
        f"- 评估摘要: `{cfg['evaluation_json']}`",
        "",
        "## 总体统计",
        "",
        f"- 总候选: {summary['total_candidates']}",
        f"- Top 队列大小: {summary['top_queue_size']}",
        f"- 生产路径候选: {summary['production_like_candidates']}",
        f"- 测试/示例路径候选: {summary['test_or_example_candidates']}",
        f"- 疑似请求局部状态候选: {summary['likely_request_local_candidates']}",
        "",
        "## 分布",
        "",
        f"- Verdict: {render_counts(summary['by_verdict'])}",
        f"- Priority: {render_counts(summary['by_priority'])}",
        f"- Framework/source kind: {render_counts(summary['by_framework'])}",
        f"- Sink: {render_counts(summary['by_sink'])}",
        f"- Container: {render_counts(summary['by_container'])}",
        "",
        "## Top 候选预览",
        "",
        "| ID | Priority | Score | Verdict | Entry | Sink |",
        "|---|---|---:|---|---|---|",
    ]
    for row in top_rows[:10]:
        entry = f"{row['entry_fqn']} ({row['entry_file']}:{row['entry_line']})"
        sink = f"{row['sink_kind']} ({row['sink_file']}:{row['sink_line']})"
        lines.append(
            f"| {row['phase4_id']} | {row['priority']} | {row['score']} | "
            f"{row['verdict']} | {md_escape(entry)} | {md_escape(sink)} |"
        )

    lines.extend(
        [
            "",
            "## Phase 4 人工验证策略",
            "",
            "1. 按 `review_queue_top50.md` 从 P0/P1 开始复核，先剔除测试、示例和请求局部状态。",
            "2. 对剩余生产路径候选补源码证据：entry 暴露面、攻击者可控 key、retained container、缺失容量边界。",
            "3. 对 high-risk 候选补最小动态验证计划，并将确认真阳归档到 `/home/furina/new_tool/poc/<vuln-id>/`。",
            "",
            "## 当前限制",
            "",
            "- Phase 4 排序不会改变 Phase 3 的 CodeQL 判定，只对候选做优先级和复核提示。",
            "- `framework` 字段沿用 Phase 3 输出，当前更接近 source kind；跨项目统计仍需后续补充 database/framework identity。",
            "- HeaderMap、Setter 等 evidence 被降权，但仍保留在队列中，避免过早丢召回。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(top_n: int | None = None) -> dict[str, Any]:
    config = load_config()
    cfg = phase4_config(config)
    if top_n is None:
        top_n = int(cfg.get("top_n", 50))

    rows = read_rows(resolve(str(cfg["input_csv"])))
    ranked = rank_rows(rows)
    top_rows = ranked[:top_n]
    summary = summarize(ranked, top_rows)

    write_csv(resolve(str(cfg["ranked_csv"])), ranked)
    write_json(resolve(str(cfg["ranked_json"])), ranked)
    write_review_queue(resolve(str(cfg["review_queue_md"])), top_rows)
    write_json(resolve(str(cfg["review_queue_json"])), top_rows)
    write_json(resolve(str(cfg["evaluation_json"])), summary)
    write_report(resolve(str(cfg["report"])), summary, cfg, top_rows)

    print(
        "Phase 4 complete: "
        f"{summary['total_candidates']} candidates, "
        f"top {summary['top_queue_size']} queued, "
        f"outputs under {cfg['results_dir']}"
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 Phase 4 排序候选、复核队列和报告")
    parser.add_argument("--top", type=int, default=None, help="复核队列大小，默认读取 config.yaml phase4.top_n")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="兼容 CLI 的 verify 子命令；当前会重新生成 top-N 复核队列",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="兼容 CLI 的 report 子命令；当前会基于 Phase 3 CSV 重新生成报告和派生产物",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run(top_n=args.top)
    if args.verify_only:
        print("Verify queue refreshed. 请从 results/phase4/review_queue_top50.md 开始人工复核。")
    if args.report_only:
        print("Report refreshed: results/phase4_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
