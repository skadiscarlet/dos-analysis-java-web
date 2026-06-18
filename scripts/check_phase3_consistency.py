#!/usr/bin/env python3
"""Phase 3 verdict 一致性检查脚本。"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "results/phase3/phase3_candidate_features.csv"
DEFAULT_OUTPUT = BASE_DIR / "results/phase3/phase3_consistency.json"
AOSP_VERDICT_PATH = BASE_DIR.parent / "dos-analysis" / "eval" / "verdict.py"
PASS_THRESHOLD = 0.95
MAX_MISMATCHES = 50

AXIS_VALUES = {
    "axis_r": {"Blocked", "PermGated", "WeakGated", "Open"},
    "axis_v": {"Uncontrollable", "Limited", "Unlimited", "Stream"},
    "axis_m": {"CallerBounded", "Amplifiable"},
    "axis_c": {"Bounded", "PerElementUnbounded", "Unbounded"},
    "axis_l": {"Evicted", "ProcessLifetime", "RebootPersistent"},
}

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
]


def load_verdict_model() -> ModuleType:
    """动态加载 AOSP 五轴 verdict 模型。"""
    if not AOSP_VERDICT_PATH.exists():
        raise FileNotFoundError(f"verdict 模型不存在: {AOSP_VERDICT_PATH}")

    spec = importlib.util.spec_from_file_location("aosp_verdict_model", AOSP_VERDICT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 verdict 模型: {AOSP_VERDICT_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for function_name in ("verdict", "drd_verdict"):
        if not callable(getattr(module, function_name, None)):
            raise AttributeError(f"verdict 模型缺少函数: {function_name}")
    return module


def normalize(value: str | None) -> str:
    """标准化 CSV 单元格，兼容空值。"""
    return (value or "").strip()


def row_identity(row: dict[str, str]) -> dict[str, str]:
    """提取 mismatch 定位字段。"""
    return {
        "framework": normalize(row.get("framework")),
        "entry_fqn": normalize(row.get("entry_fqn")),
        "entry_file": normalize(row.get("entry_file")),
        "entry_line": normalize(row.get("entry_line")),
        "sink_kind": normalize(row.get("sink_kind")),
        "sink_file": normalize(row.get("sink_file")),
        "sink_line": normalize(row.get("sink_line")),
    }


def validate_input(input_path: Path) -> None:
    """检查输入 CSV 存在且 schema 完整。"""
    if not input_path.exists():
        raise FileNotFoundError(f"输入 CSV 不存在: {input_path}")

    with input_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"输入 CSV 为空: {input_path}") from exc

    missing = [field for field in FIELDNAMES if field not in header]
    if missing:
        raise ValueError(f"输入 CSV 缺少字段: {', '.join(missing)}")


def validate_axes(row_number: int, axes: dict[str, str]) -> None:
    """显式校验轴值，避免依赖 assert。"""
    for axis_name, axis_value in axes.items():
        if axis_value not in AXIS_VALUES[axis_name]:
            allowed = ", ".join(sorted(AXIS_VALUES[axis_name]))
            raise ValueError(f"第 {row_number} 行 {axis_name} 非法: {axis_value!r}; allowed: {allowed}")


def check_consistency(input_path: Path, verdict_model: ModuleType) -> dict[str, Any]:
    """读取 Phase 3 CSV 并重新计算 verdict 一致性。"""
    validate_input(input_path)
    total = 0
    matched = 0
    mismatches: list[dict[str, Any]] = []
    total_mismatches = 0

    with input_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row_number, row in enumerate(reader, start=2):
            total += 1
            axis_r = normalize(row.get("axis_r"))
            axis_v = normalize(row.get("axis_v"))
            axis_m = normalize(row.get("axis_m"))
            axis_c = normalize(row.get("axis_c"))
            axis_l = normalize(row.get("axis_l"))
            actual_verdict = normalize(row.get("verdict"))
            actual_drd = normalize(row.get("verdict_drd"))

            axes = {
                "axis_r": axis_r,
                "axis_v": axis_v,
                "axis_m": axis_m,
                "axis_c": axis_c,
                "axis_l": axis_l,
            }

            try:
                validate_axes(row_number, axes)
                expected_verdict = verdict_model.verdict(axis_r, axis_v, axis_m, axis_c, axis_l)
                expected_drd = verdict_model.drd_verdict(axis_v, axis_c, axis_l)
                row_matched = actual_verdict == expected_verdict and actual_drd == expected_drd
                error = None
            except Exception as exc:  # noqa: BLE001 - 保留每行失败原因用于审计
                expected_verdict = None
                expected_drd = None
                row_matched = False
                error = str(exc)

            if row_matched:
                matched += 1
            else:
                total_mismatches += 1
                if len(mismatches) < MAX_MISMATCHES:
                    mismatch = {
                        "row_number": row_number,
                        **row_identity(row),
                        "axes": axes,
                        "expected": {
                            "verdict_drd": expected_drd,
                            "verdict": expected_verdict,
                        },
                        "actual": {
                            "verdict_drd": actual_drd,
                            "verdict": actual_verdict,
                        },
                        "evidence": normalize(row.get("evidence")),
                    }
                    if error is not None:
                        mismatch["error"] = error
                    mismatches.append(mismatch)

    consistency = matched / total if total else 0.0
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "input": str(input_path),
        "total": total,
        "matched": matched,
        "mismatched": total - matched,
        "consistency": consistency,
        "pass": total > 0 and consistency >= PASS_THRESHOLD,
        "mismatches_truncated": total_mismatches > len(mismatches),
        "mismatch_sample_limit": MAX_MISMATCHES,
        "mismatches": mismatches,
    }


def write_result(output_path: Path, result: dict[str, Any]) -> None:
    """写出 JSON 结果。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 Phase 3 CSV verdict 与 AOSP verdict.py 的一致性")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help=f"输入 CSV，默认 {DEFAULT_INPUT}")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"输出 JSON，默认 {DEFAULT_OUTPUT}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    verdict_model = load_verdict_model()
    result = check_consistency(args.input, verdict_model)
    write_result(args.output, result)

    print(
        f"Phase 3 consistency: {result['consistency']:.3f} "
        f"({result['matched']}/{result['total']} matched), pass={result['pass']}"
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
