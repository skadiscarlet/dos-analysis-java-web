#!/usr/bin/env python3
"""Summarize application static DoS findings and triage default OOM risk."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = BASE_DIR / "results/applications_static_analysis"
DEFAULT_MANIFEST = BASE_DIR / "intel/applications/java_web_application_targets.json"
DEFAULT_OUTPUT_DIR = DEFAULT_INPUT_DIR / "_static_validation"

OUTPUT_FIELDS = [
    "application",
    "finding_id",
    "title",
    "original_verdict",
    "oom_static_verdict",
    "probe_priority",
    "resource_class",
    "reachability_class",
    "validation_reason",
    "entry",
    "source",
    "sink",
    "driver",
    "dimension",
    "retention",
    "bound",
    "impact",
    "dynamic_probe",
    "source_artifact",
]

APP_SUMMARY_FIELDS = [
    "application",
    "candidate_count",
    "p0_count",
    "p1_count",
    "p2_count",
    "p3_count",
    "likely_count",
    "needs_dynamic_probe_count",
    "rejected_or_out_of_scope_count",
    "top_probe_ids",
]

REJECTED_VERDICTS = {
    "rejected",
    "rejected_out_of_scope",
    "rejected_effective_bound",
    "rejected_context_dependent",
    "rejected_special_config",
    "out_of_scope_management_config",
    "out_of_scope_disk_storage",
    "out_of_scope_management_permission",
}

MEMORY_TOKENS = (
    "heap",
    "oom",
    "memory",
    "session",
    "httpsession",
    "shiro",
    "map",
    "cache",
    "queue",
    "linkedblockingqueue",
    "arrayblockingqueue",
    "thread",
    "executor",
    "connection",
    "websocket",
    "sse",
    "emitter",
    "bytearray",
    "bytebuf",
    "buffer",
    "body",
    "json",
    "xml",
    "string",
    "bufferedimage",
    "bitmatrix",
    "image",
    "parse",
    "class_cache",
    "metaspace",
    "registry",
    "index",
    "listener",
    "inflight",
    "retained",
    "process-lifetime",
    "process heap",
    "jvm",
    "redis",
    "rabbitmq",
    "broker memory",
    "elasticsearch",
    "direct buffer",
    "direct/heap",
    "堆",
    "内存",
    "会话",
    "线程",
    "队列",
    "缓存",
    "连接",
)

PERSISTENT_STORAGE_TOKENS = (
    "disk",
    "file",
    "local storage",
    "object storage",
    "oss",
    "minio",
    "temp file",
    "upload storage",
    "磁盘",
    "文件",
    "对象存储",
)

DB_ONLY_TOKENS = (
    "db_row_count",
    "db row",
    "database row",
    "mysql",
    "postgres",
    "table",
    "row count",
    "db growth",
    "db rows",
    "persistent db",
    "写库",
    "数据库",
)

SECONDARY_HEAP_TOKENS = (
    "heap materialization",
    "heap_materialization",
    "unbounded view",
    "result materialization",
    "materialization",
    "full result",
    "full-list",
    "list materialization",
    "full-list",
    "response serialization",
    "json response",
    "request-burst heap",
    "collector",
    "topdocs",
    "workbook",
    "zip",
    "bytearrayoutputstream",
)

DEFAULT_REACH_TOKENS = (
    "anonymous",
    "default-open",
    "default open",
    "default no auth",
    "no auth",
    "unauthenticated",
    "permitall",
    "public",
    "default token",
    "weak default",
    "low-privilege",
    "low privilege",
    "self-registered",
    "external",
    "exposed",
    "default port",
    "docker compose",
    "default deployment",
    "默认匿名",
    "默认开放",
    "默认",
    "匿名",
    "低权限",
)

NON_DEFAULT_TOKENS = (
    "admin-only",
    "admin gated",
    "management",
    "requires admin",
    "requires management",
    "special config",
    "non-default",
    "not default",
    "disabled by default",
    "default-disabled",
    "context-constrained",
    "library",
    "no default web",
    "no default external",
    "out of scope",
    "管理权限",
    "管理面",
    "特殊配置",
    "默认关闭",
    "非默认",
)

BOUND_TOKENS = (
    "bounded",
    "hard cap",
    "max size",
    "max-size",
    "quota",
    "limit",
    "ttl",
    "cleanup",
    "eviction",
    "expire",
    "fixed",
    "capacity",
    "有界",
    "上限",
    "清理",
    "过期",
)

NO_BOUND_TOKENS = (
    "unbounded",
    "no quota",
    "no hard",
    "no max",
    "no size",
    "without capacity",
    "no application-level maximum",
    "no per-client",
    "无上限",
    "无配额",
)


def norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(norm(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def compact_space(value: str) -> str:
    return " ".join(value.split())


def field_text(row: dict[str, Any], *fields: str) -> str:
    return " ".join(compact_space(norm(row.get(field))) for field in fields if norm(row.get(field)))


def lower_text(row: dict[str, Any]) -> str:
    return field_text(
        row,
        "title",
        "entry",
        "source",
        "sink",
        "sinks",
        "driver",
        "dimension",
        "resource_dimension",
        "resource_dimensions",
        "retention",
        "bound",
        "impact",
        "impact_claim",
        "impact_hypothesis",
        "default_reachability",
        "default_deployment",
        "reachability",
        "scope_notes",
        "scope_note",
        "excluded_scope_notes",
        "reason",
        "reason_not_likely",
        "why_not_confirmed",
        "dynamic_probe",
        "next_probe",
    ).lower()


def contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def read_manifest_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = data.get("targets", [])
    return [norm(target.get("id")) for target in targets if norm(target.get("id"))]


def read_findings(input_dir: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for jsonl_path in sorted(input_dir.glob("*/findings.jsonl")):
        app = jsonl_path.parent.name
        for line_number, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            item["_application"] = app
            item["_source_artifact"] = relative_path(jsonl_path)
            item["_source_line"] = line_number
            item["_format"] = "jsonl"
            findings.append(item)

    for csv_path in sorted(input_dir.glob("*/findings.csv")):
        app = csv_path.parent.name
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for line_number, row in enumerate(reader, start=2):
                item = dict(row)
                item["_application"] = app
                item["_source_artifact"] = relative_path(csv_path)
                item["_source_line"] = line_number
                item["_format"] = "csv"
                findings.append(item)
    return findings


def classify_reachability(row: dict[str, Any], text: str, verdict: str) -> str:
    reach_text = field_text(row, "default_reachability", "default_deployment", "reachability").lower()
    if verdict in REJECTED_VERDICTS or verdict == "context_constrained":
        return "not_default_or_rejected"
    if contains_any(reach_text, NON_DEFAULT_TOKENS):
        return "preconditioned_or_non_default"
    if contains_any(reach_text, DEFAULT_REACH_TOKENS):
        if "low-privilege" in reach_text or "low privilege" in reach_text or "低权限" in reach_text:
            return "default_low_privilege"
        if "default token" in reach_text or "weak default" in reach_text:
            return "default_weak_token"
        return "default_external"
    if contains_any(text, ("library", "no default web", "no default external", "not a web", "库级")):
        return "not_default_or_rejected"
    if contains_any(text, DEFAULT_REACH_TOKENS):
        return "default_external_inferred"
    return "unknown"


def classify_resource(row: dict[str, Any], text: str) -> str:
    dimension_text = field_text(
        row,
        "dimension",
        "resource_dimension",
        "resource_dimensions",
        "sink",
        "sinks",
        "retention",
        "impact",
        "impact_claim",
        "impact_hypothesis",
    ).lower()
    has_memory = contains_any(dimension_text, MEMORY_TOKENS)
    has_storage = contains_any(dimension_text, PERSISTENT_STORAGE_TOKENS)
    has_db = contains_any(dimension_text, DB_ONLY_TOKENS)
    has_secondary_heap = contains_any(dimension_text, SECONDARY_HEAP_TOKENS)
    has_row_driver = contains_any(
        dimension_text,
        (
            " row",
            "rows ",
            "row count",
            "approved row",
            "attacker-created",
            "persist and later",
            "persist across requests",
            "数据库行",
        ),
    )

    if (has_db or has_row_driver) and has_secondary_heap:
        return "db_backed_heap_amplification"
    if has_memory:
        if "redis" in dimension_text:
            return "external_cache_memory"
        if "rabbitmq" in dimension_text or "broker memory" in dimension_text:
            return "broker_or_queue_memory"
        if "session" in dimension_text or "httpsession" in dimension_text or "shiro" in dimension_text:
            return "jvm_or_process_memory"
        if "body" in dimension_text or "byte" in dimension_text or "buffer" in dimension_text or "image" in dimension_text:
            return "request_burst_heap"
        if "thread" in dimension_text or "executor" in dimension_text or "connection" in dimension_text:
            return "threads_connections_or_queue"
        return "jvm_or_process_memory"
    if has_storage and not has_memory:
        return "disk_or_file_storage_only"
    if has_db and not has_memory:
        return "db_persistence_only"
    if "cpu" in dimension_text:
        return "cpu_without_oom_proof"
    if contains_any(text, MEMORY_TOKENS):
        return "memory_inferred"
    return "unknown"


def classify_bound(text: str) -> str:
    if contains_any(text, NO_BOUND_TOKENS):
        return "no_effective_bound_static"
    if contains_any(text, BOUND_TOKENS):
        return "has_default_bound_or_cleanup"
    return "bound_unknown"


def static_validate(row: dict[str, Any]) -> dict[str, str]:
    verdict = norm(row.get("verdict")).lower()
    text = lower_text(row)
    reachability_class = classify_reachability(row, text, verdict)
    resource_class = classify_resource(row, text)
    bound_class = classify_bound(text)

    has_default_surface = reachability_class in {
        "default_external",
        "default_external_inferred",
        "default_low_privilege",
        "default_weak_token",
    }
    memory_candidate = resource_class not in {
        "disk_or_file_storage_only",
        "db_persistence_only",
        "cpu_without_oom_proof",
        "unknown",
    }
    direct_memory = resource_class in {
        "jvm_or_process_memory",
        "threads_connections_or_queue",
        "request_burst_heap",
        "memory_inferred",
    }

    if verdict in REJECTED_VERDICTS:
        return {
            "oom_static_verdict": "not_default_external_oom",
            "probe_priority": "P3",
            "resource_class": resource_class,
            "reachability_class": reachability_class,
            "validation_reason": "原始结论已拒绝或标出范围外，未进入默认外部 OOM 候选。",
        }
    if verdict == "context_constrained":
        return {
            "oom_static_verdict": "not_default_external_oom",
            "probe_priority": "P3",
            "resource_class": resource_class,
            "reachability_class": reachability_class,
            "validation_reason": "原始结论为 context_constrained，默认配置或默认可达性不足。",
        }
    if not has_default_surface:
        return {
            "oom_static_verdict": "needs_reachability_review",
            "probe_priority": "P2",
            "resource_class": resource_class,
            "reachability_class": reachability_class,
            "validation_reason": "现有结果未给出足够默认外部可达性证据，需先复核部署/auth 面。",
        }
    if not memory_candidate:
        return {
            "oom_static_verdict": "not_oom_primary",
            "probe_priority": "P2",
            "resource_class": resource_class,
            "reachability_class": reachability_class,
            "validation_reason": "主要影响不是内存/线程/连接/队列或只证明持久存储增长，不能作为 OOM 优先项。",
        }

    if verdict == "likely" and direct_memory and bound_class != "has_default_bound_or_cleanup":
        return {
            "oom_static_verdict": "possible_default_external_oom",
            "probe_priority": "P0",
            "resource_class": resource_class,
            "reachability_class": reachability_class,
            "validation_reason": "默认外部入口、内存/线程/队列类资源增长和缺少有效硬上限的静态证据同时成立。",
        }
    if verdict == "likely":
        return {
            "oom_static_verdict": "possible_default_external_oom_needs_measurement",
            "probe_priority": "P1",
            "resource_class": resource_class,
            "reachability_class": reachability_class,
            "validation_reason": "静态证据较强，但存在默认清理/TTL/依赖组件/二阶段放大或边界不明，需动态测 OOM 门槛。",
        }
    if verdict == "needs_dynamic_probe":
        return {
            "oom_static_verdict": "possible_but_unproven_default_oom",
            "probe_priority": "P1" if direct_memory else "P2",
            "resource_class": resource_class,
            "reachability_class": reachability_class,
            "validation_reason": "source-to-sink 形状可疑，但关键边界、触发路径或默认资源曲线仍缺动态证据。",
        }

    return {
        "oom_static_verdict": "needs_manual_review",
        "probe_priority": "P2",
        "resource_class": resource_class,
        "reachability_class": reachability_class,
        "validation_reason": "原始 verdict 不在标准集合中，保留为人工复核项。",
    }


def normalize_row(row: dict[str, Any]) -> dict[str, str]:
    validation = static_validate(row)
    title = norm(row.get("title"))
    if not title:
        title = compact_space(field_text(row, "source", "sink"))[:160]
    dynamic_probe = field_text(row, "dynamic_probe", "next_probe", "dynamic_probe_status")
    impact = field_text(row, "impact", "impact_claim", "impact_hypothesis")
    source_artifact = f"{norm(row.get('_source_artifact'))}:{norm(row.get('_source_line'))}"
    normalized = {
        "application": norm(row.get("_application")),
        "finding_id": norm(row.get("finding_id")),
        "title": title,
        "original_verdict": norm(row.get("verdict")),
        "entry": norm(row.get("entry")),
        "source": norm(row.get("source")),
        "sink": field_text(row, "sink", "sinks"),
        "driver": norm(row.get("driver")),
        "dimension": field_text(row, "dimension", "resource_dimension", "resource_dimensions"),
        "retention": norm(row.get("retention")),
        "bound": norm(row.get("bound")),
        "impact": impact,
        "dynamic_probe": dynamic_probe,
        "source_artifact": source_artifact,
    }
    normalized.update(validation)
    return normalized


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def count_by(rows: list[dict[str, str]], field: str) -> Counter[str]:
    return Counter(row.get(field, "") for row in rows)


def build_app_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["application"], []).append(row)

    summary_rows: list[dict[str, str]] = []
    for app, app_rows in sorted(grouped.items()):
        verdicts = count_by(app_rows, "original_verdict")
        priorities = count_by(app_rows, "probe_priority")
        top_ids = [
            row["finding_id"]
            for row in app_rows
            if row["probe_priority"] in {"P0", "P1"} and row["finding_id"]
        ]
        rejected_count = sum(verdicts.get(verdict, 0) for verdict in REJECTED_VERDICTS)
        summary_rows.append(
            {
                "application": app,
                "candidate_count": str(len(app_rows)),
                "p0_count": str(priorities.get("P0", 0)),
                "p1_count": str(priorities.get("P1", 0)),
                "p2_count": str(priorities.get("P2", 0)),
                "p3_count": str(priorities.get("P3", 0)),
                "likely_count": str(verdicts.get("likely", 0)),
                "needs_dynamic_probe_count": str(verdicts.get("needs_dynamic_probe", 0)),
                "rejected_or_out_of_scope_count": str(rejected_count),
                "top_probe_ids": ";".join(top_ids),
            }
        )
    return summary_rows


def top_rows(rows: list[dict[str, str]], priorities: set[str]) -> list[dict[str, str]]:
    return [row for row in rows if row["probe_priority"] in priorities]


def md_table(rows: list[dict[str, str]], columns: list[tuple[str, str]], limit: int | None = None) -> list[str]:
    selected = rows if limit is None else rows[:limit]
    lines = [
        "| " + " | ".join(title for title, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        values = []
        for _, field in columns:
            value = compact_space(row.get(field, ""))
            value = value.replace("|", "\\|")
            if len(value) > 110:
                value = value[:107].rstrip() + "..."
            values.append(value)
        lines.append("| " + " | ".join(values) + " |")
    if limit is not None and len(rows) > limit:
        lines.append(f"| ... | 另有 {len(rows) - limit} 条，见 CSV/JSONL 明细 |  |  |  |")
    return lines


def format_detail(value: str, fallback: str = "未记录") -> str:
    value = compact_space(value)
    if not value:
        return fallback
    return value.replace("|", "\\|")


def build_dynamic_validation_catalog(
    rows: list[dict[str, str]],
    app_summary: list[dict[str, str]],
    raw_count: int,
    manifest_ids: list[str],
    result_apps: list[str],
    input_dir: Path,
    output_dir: Path,
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    priority_counts = count_by(rows, "probe_priority")
    original_counts = count_by(rows, "original_verdict")
    missing_results = sorted(set(manifest_ids) - set(result_apps)) if manifest_ids else []

    lines = [
        "# 应用级 216 条候选动态验证准备清单",
        "",
        "## 使用说明",
        "",
        f"- 生成时间：{generated_at}",
        f"- 输入目录：`{relative_path(input_dir)}`",
        f"- 输出目录：`{relative_path(output_dir)}`",
        f"- 已解析候选：{raw_count}",
        f"- 已覆盖应用结果目录：{len(result_apps)}",
        f"- manifest 目标数：{len(manifest_ids) if manifest_ids else '未读取'}",
        "- 用途：给下一步动态验证做排期和用例设计，不代表 confirmed DoS。",
        "- 验证门槛：必须在默认部署或清晰标注的默认 quickstart 环境中，由外部 client 请求触发 OOM、GC death、线程/连接池耗尽、watchdog/restart 或持续 HTTP/协议服务不可用；单纯增长曲线只能作为中间证据。",
        "- 排序：`P0` 优先验证，`P1` 次优先，`P2` 先补默认可达性/边界证据，`P3` 暂不进入默认 OOM 动态验证。",
        "",
    ]
    if missing_results:
        lines.append(f"- manifest 中尚无本地静态结果目录的目标：`{', '.join(missing_results)}`")
        lines.append("")

    lines += [
        "## 总览",
        "",
        "### 优先级统计",
        "",
    ]
    for priority in ("P0", "P1", "P2", "P3"):
        lines.append(f"- `{priority}`: {priority_counts.get(priority, 0)}")

    lines += ["", "### 原始 verdict 统计", ""]
    for verdict, count in sorted(original_counts.items()):
        lines.append(f"- `{verdict}`: {count}")

    lines += [
        "",
        "### 应用摘要",
        "",
    ]
    lines += md_table(
        app_summary,
        [
            ("app", "application"),
            ("all", "candidate_count"),
            ("P0", "p0_count"),
            ("P1", "p1_count"),
            ("P2", "p2_count"),
            ("P3", "p3_count"),
            ("top ids", "top_probe_ids"),
        ],
        limit=None,
    )

    for priority in ("P0", "P1", "P2", "P3"):
        priority_rows = [row for row in rows if row["probe_priority"] == priority]
        lines += [
            "",
            f"## {priority} 候选",
            "",
        ]
        if priority == "P0":
            lines.append("优先进入动态 OOM/不可用验证。静态证据显示默认外部入口、内存/线程/队列类资源增长和缺少有效硬上限同时成立。")
        elif priority == "P1":
            lines.append("适合作为第二批动态探针。通常存在 TTL/cleanup、默认组件边界、低权限前置、二阶段放大或 request-burst 门槛。")
        elif priority == "P2":
            lines.append("先补默认可达性、部署条件或资源类型边界；不建议直接投入 OOM 压测。")
        else:
            lines.append("原始报告已拒绝、标注范围外、非默认或非 OOM 主路径，默认不进入动态 OOM 验证。")
        lines.append("")

        current_app = ""
        for index, row in enumerate(priority_rows, start=1):
            if row["application"] != current_app:
                current_app = row["application"]
                lines += ["", f"### {current_app}", ""]
            title = format_detail(row["title"], fallback="未命名候选")
            lines += [
                f"#### {index}. `{row['finding_id'] or 'NO-ID'}` - {title}",
                "",
                f"- 原始 verdict：`{row['original_verdict'] or 'unknown'}`",
                f"- OOM 静态复核：`{row['oom_static_verdict']}`",
                f"- 资源类型：`{row['resource_class']}`",
                f"- 可达性：`{row['reachability_class']}`",
                f"- 复核原因：{format_detail(row['validation_reason'])}",
                f"- Entry：{format_detail(row['entry'])}",
                f"- Source：{format_detail(row['source'])}",
                f"- Sink：{format_detail(row['sink'])}",
                f"- Driver：{format_detail(row['driver'])}",
                f"- Dimension：{format_detail(row['dimension'])}",
                f"- Retention：{format_detail(row['retention'])}",
                f"- Bound：{format_detail(row['bound'])}",
                f"- Impact：{format_detail(row['impact'])}",
                f"- 动态验证建议：{format_detail(row['dynamic_probe'])}",
                f"- 原始证据：`{row['source_artifact']}`",
                "",
            ]

    lines += [
        "## 关联机器产物",
        "",
        f"- 全量 CSV：`{relative_path(output_dir / 'all_candidates.csv')}`",
        f"- 全量 JSONL：`{relative_path(output_dir / 'all_candidates.jsonl')}`",
        f"- P0/P1 队列 CSV：`{relative_path(output_dir / 'default_oom_probe_queue.csv')}`",
        f"- 应用汇总 CSV：`{relative_path(output_dir / 'application_summary.csv')}`",
        f"- 默认 OOM 复核摘要：`{relative_path(output_dir / 'default_oom_static_validation.md')}`",
    ]
    return "\n".join(lines) + "\n"


def build_report(
    rows: list[dict[str, str]],
    app_summary: list[dict[str, str]],
    raw_count: int,
    manifest_ids: list[str],
    result_apps: list[str],
    input_dir: Path,
    output_dir: Path,
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    original_counts = count_by(rows, "original_verdict")
    static_counts = count_by(rows, "oom_static_verdict")
    priority_counts = count_by(rows, "probe_priority")
    resource_counts = count_by(rows, "resource_class")
    missing_results = sorted(set(manifest_ids) - set(result_apps)) if manifest_ids else []
    extra_results = sorted(set(result_apps) - set(manifest_ids)) if manifest_ids else []

    p0_rows = top_rows(rows, {"P0"})
    p1_rows = top_rows(rows, {"P1"})
    possible_rows = top_rows(rows, {"P0", "P1"})

    lines = [
        "# 应用级静态候选默认 OOM 复核报告",
        "",
        "## 基本信息",
        "",
        f"- 生成时间：{generated_at}",
        f"- 输入目录：`{relative_path(input_dir)}`",
        f"- 输出目录：`{relative_path(output_dir)}`",
        f"- manifest 目标数：{len(manifest_ids) if manifest_ids else '未读取'}",
        f"- 已有结果目录数：{len(result_apps)}",
        f"- 已解析候选数：{raw_count}",
        "- 复核范围：默认配置/默认启动方式下，外部 client 可达的非磁盘资源耗尽；重点检查 JVM/process heap、session/cache/map/queue/thread/connection/request-burst heap，以及 Redis/RabbitMQ/ES 等默认依赖的内存压力。",
        "- 复核边界：本轮只做静态汇总与报告级复核，未启动真实服务、未发送 PoC、未将任何候选提升为 confirmed DoS。",
        "",
    ]
    if missing_results:
        lines.append(f"- manifest 中尚无静态结果目录的目标：`{', '.join(missing_results)}`")
    if extra_results:
        lines.append(f"- 结果目录中不在 manifest 的目标：`{', '.join(extra_results)}`")

    lines += [
        "",
        "## 汇总计数",
        "",
        "### 原始 verdict",
        "",
    ]
    for key, value in sorted(original_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "### 默认 OOM 静态复核", ""]
    for key, value in sorted(static_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "### 动态验证优先级", ""]
    for key in ("P0", "P1", "P2", "P3"):
        lines.append(f"- `{key}`: {priority_counts.get(key, 0)}")
    lines += ["", "### 资源类型", ""]
    for key, value in sorted(resource_counts.items()):
        lines.append(f"- `{key}`: {value}")

    lines += [
        "",
        "## P0：优先动态 OOM 验证候选",
        "",
        "这些候选同时具备默认外部入口、内存/线程/队列类资源增长和缺少有效硬上限的静态证据；仍需真实默认部署下测量 OOM、GC death、线程/连接耗尽或持续不可用。",
        "",
    ]
    lines += md_table(
        p0_rows,
        [
            ("app", "application"),
            ("id", "finding_id"),
            ("title", "title"),
            ("resource", "resource_class"),
            ("reason", "validation_reason"),
        ],
        limit=60,
    )

    lines += [
        "",
        "## P1：可能默认 OOM，但必须先测边界",
        "",
        "这些候选存在 TTL/cleanup、依赖组件默认上限、request-burst 并发门槛、低权限前置步骤、二阶段数据填充或路径证明缺口；适合作为第二批动态探针。",
        "",
    ]
    lines += md_table(
        p1_rows,
        [
            ("app", "application"),
            ("id", "finding_id"),
            ("title", "title"),
            ("resource", "resource_class"),
            ("reason", "validation_reason"),
        ],
        limit=80,
    )

    lines += [
        "",
        "## 应用级候选概览",
        "",
    ]
    lines += md_table(
        app_summary,
        [
            ("app", "application"),
            ("all", "candidate_count"),
            ("P0", "p0_count"),
            ("P1", "p1_count"),
            ("top ids", "top_probe_ids"),
        ],
        limit=80,
    )

    lines += [
        "",
        "## 判定说明",
        "",
        "- `possible_default_external_oom`：报告中已有默认外部可达证据，并且资源 sink 是 JVM/process 内存、线程、连接、队列或 request-burst heap，静态上未见有效硬上限。",
        "- `possible_default_external_oom_needs_measurement`：路径看起来可造成默认 OOM 或依赖组件内存压力，但有 TTL、cleanup、外部组件、低权限前置、二阶段放大或默认上限不明。",
        "- `possible_but_unproven_default_oom`：原始候选本身就是 `needs_dynamic_probe`，本轮不能仅凭静态证据提升。",
        "- `not_oom_primary`：主要是磁盘、DB 持久化或纯 CPU/业务放大，不作为 OOM 主候选；若存在二阶段 heap materialization 会保留在 P1/P2。",
        "- `not_default_external_oom`：原始报告已拒绝、标出范围外，或默认部署/外部可达性不成立。",
        "",
        "## 输出文件",
        "",
        f"- 全量 CSV：`{relative_path(output_dir / 'all_candidates.csv')}`",
        f"- 全量 JSONL：`{relative_path(output_dir / 'all_candidates.jsonl')}`",
        f"- 应用汇总 CSV：`{relative_path(output_dir / 'application_summary.csv')}`",
        f"- P0/P1 候选 CSV：`{relative_path(output_dir / 'default_oom_probe_queue.csv')}`",
        f"- 216 条候选动态验证准备清单：`{relative_path(output_dir / 'all_candidates_dynamic_validation.md')}`",
        f"- 本报告：`{relative_path(output_dir / 'default_oom_static_validation.md')}`",
    ]
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()

    raw_findings = read_findings(input_dir)
    rows = [normalize_row(row) for row in raw_findings]
    rows.sort(key=lambda row: (row["probe_priority"], row["application"], row["finding_id"]))

    result_apps = sorted({row["application"] for row in rows})
    manifest_ids = read_manifest_ids(args.manifest)
    possible_rows = top_rows(rows, {"P0", "P1"})
    app_summary = build_app_summary(rows)

    write_csv(output_dir / "all_candidates.csv", rows, OUTPUT_FIELDS)
    write_jsonl(output_dir / "all_candidates.jsonl", rows)
    write_csv(output_dir / "application_summary.csv", app_summary, APP_SUMMARY_FIELDS)
    write_csv(output_dir / "default_oom_probe_queue.csv", possible_rows, OUTPUT_FIELDS)
    report = build_report(rows, app_summary, len(raw_findings), manifest_ids, result_apps, input_dir, output_dir)
    (output_dir / "default_oom_static_validation.md").write_text(report, encoding="utf-8")
    catalog = build_dynamic_validation_catalog(
        rows,
        app_summary,
        len(raw_findings),
        manifest_ids,
        result_apps,
        input_dir,
        output_dir,
    )
    (output_dir / "all_candidates_dynamic_validation.md").write_text(catalog, encoding="utf-8")

    print(f"parsed_findings={len(raw_findings)}")
    print(f"result_apps={len(result_apps)}")
    if manifest_ids:
        missing = sorted(set(manifest_ids) - set(result_apps))
        print(f"manifest_targets={len(manifest_ids)}")
        print(f"missing_result_dirs={len(missing)}")
        if missing:
            print("missing=" + ",".join(missing))
    for key, count in sorted(count_by(rows, "probe_priority").items()):
        print(f"{key}={count}")
    print(f"wrote={relative_path(output_dir / 'default_oom_static_validation.md')}")
    print(f"wrote={relative_path(output_dir / 'all_candidates_dynamic_validation.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
