#!/usr/bin/env python3
"""Check Phase 3 static regression coverage for WEB-REAL cases."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = BASE_DIR / "intel/regression/web_real_manifest.json"
DEFAULT_INPUT = BASE_DIR / "results/phase3/phase3_candidate_features.csv"
DEFAULT_OUTPUT = BASE_DIR / "results/phase3/web_real_regression.json"

Row = dict[str, str]
Rule = dict[str, Any]


def norm(value: Any) -> str:
    return str(value or "").strip()


def load_json(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"manifest not found: {path}") from exc
    except OSError as exc:
        raise ValueError(f"manifest is not readable: {path}: {exc}") from exc

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"manifest root must be an object: {path}")
    return data


def load_rows(path: Path) -> list[Row]:
    if not path.exists():
        raise ValueError(f"Phase 3 CSV not found: {path}")
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"Phase 3 CSV has no header: {path}")
            return [{field: norm(row.get(field)) for field in reader.fieldnames} for row in reader]
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"Phase 3 CSV is not readable: {path}: {exc}") from exc


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest cases must be a non-empty list")
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each manifest case must be an object")
        case_id = norm(case.get("id"))
        if not case_id:
            raise ValueError("each manifest case must have id")
        required = case.get("required")
        if not isinstance(required, list) or not required:
            raise ValueError(f"{case_id}.required must be a non-empty list")
        for group in ("required", "expected"):
            rules = case.get(group, [])
            if not isinstance(rules, list):
                raise ValueError(f"{case_id}.{group} must be a list")
            for rule in rules:
                validate_rule(case_id, group, rule)
    return cases


def validate_rule(case_id: str, group: str, rule: Any) -> None:
    if not isinstance(rule, dict):
        raise ValueError(f"{case_id}.{group} rule must be an object")
    field = rule.get("field")
    op = rule.get("op")
    if not is_non_empty_string(field):
        raise ValueError(f"{case_id}.{group} rule is missing field")
    if not isinstance(op, str):
        raise ValueError(f"{case_id}.{group}.{field} has unsupported op: {op}")
    if op not in {"equals", "contains", "one_of"}:
        raise ValueError(f"{case_id}.{group}.{field} has unsupported op: {op}")
    if op in {"equals", "contains"} and not is_non_empty_string(rule.get("value")):
        raise ValueError(f"{case_id}.{group}.{field} requires non-empty string value")
    if op == "one_of":
        values = rule.get("values")
        if not isinstance(values, list) or not values or not all(is_non_empty_string(value) for value in values):
            raise ValueError(f"{case_id}.{group}.{field} requires non-empty string values")


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def rule_matches(row: Row, rule: Rule) -> bool:
    actual = norm(row.get(norm(rule.get("field"))))
    op = norm(rule.get("op"))
    if op == "equals":
        return actual == norm(rule.get("value"))
    if op == "contains":
        return norm(rule.get("value")) in actual
    if op == "one_of":
        return actual in {norm(value) for value in rule.get("values", [])}
    raise ValueError(f"unsupported op: {op}")


def missing_rules(row: Row, rules: list[Rule]) -> list[Rule]:
    return [rule for rule in rules if not rule_matches(row, rule)]


def summarize_row(row: Row) -> dict[str, str]:
    fields = [
        "framework",
        "candidate_family",
        "sink_id",
        "sink_shape",
        "retained_field",
        "receiver_proof",
        "request_flow_kind",
        "growth_driver_kind",
        "growth_dimension",
        "deployment_condition",
    ]
    return {field: norm(row.get(field)) for field in fields}


def evaluate_case(case: dict[str, Any], rows: list[Row]) -> dict[str, Any]:
    required = case.get("required", [])
    expected = case.get("expected", [])
    required_matches = [row for row in rows if not missing_rules(row, required)]
    full_matches = [row for row in required_matches if not missing_rules(row, expected)]

    if full_matches:
        status = "hit"
        best = full_matches[0]
        missing: list[Rule] = []
    elif required_matches:
        status = "partial"
        best = required_matches[0]
        missing = missing_rules(best, expected)
    else:
        status = "missing"
        best = {}
        missing = required

    return {
        "id": norm(case.get("id")),
        "framework": norm(case.get("framework")),
        "component": norm(case.get("component")),
        "status": status,
        "matched_sink_id": norm(best.get("sink_id")) if best else "",
        "matched_candidate": summarize_row(best) if best else {},
        "required_match_count": len(required_matches),
        "full_match_count": len(full_matches),
        "missing_rules": missing,
        "deployment_condition": norm(case.get("deployment_condition")),
        "notes": norm(case.get("notes")),
    }


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def build_report(
    manifest_path: Path,
    input_path: Path,
    cases: list[dict[str, Any]],
    rows: list[Row],
) -> dict[str, Any]:
    case_results = [evaluate_case(case, rows) for case in cases]
    counts = {status: sum(1 for case in case_results if case["status"] == status) for status in ("hit", "partial", "missing")}
    total = len(case_results)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "manifest": display_path(manifest_path),
        "input_csv": display_path(input_path),
        "total_cases": total,
        "hit": counts["hit"],
        "partial": counts["partial"],
        "missing": counts["missing"],
        "known_vuln_recall": counts["hit"] / total if total else 0.0,
        "cases": case_results,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def print_summary(report: dict[str, Any]) -> None:
    for case in report["cases"]:
        line = f"{case['id']}: {case['status']}"
        if case.get("matched_sink_id"):
            line += f" sink={case['matched_sink_id']}"
        if case["status"] != "hit":
            missing = ", ".join(f"{rule.get('field')}:{rule.get('op')}" for rule in case.get("missing_rules", []))
            line += f" missing={missing}"
        print(line)
    print(
        "WEB-REAL regression: "
        f"{report['hit']}/{report['total_cases']} hit, "
        f"{report['partial']} partial, {report['missing']} missing"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="WEB-REAL regression manifest")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Phase 3 merged CSV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Regression JSON report")
    parser.add_argument("--no-write", action="store_true", help="Do not write the JSON report")
    return parser.parse_args(argv)


def run(manifest_path: Path = DEFAULT_MANIFEST, input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT, write: bool = True) -> int:
    manifest = load_json(manifest_path)
    cases = validate_manifest(manifest)
    rows = load_rows(input_path)
    report = build_report(manifest_path, input_path, cases, rows)
    if write:
        write_report(output_path, report)
    print_summary(report)
    return 0 if report["partial"] == 0 and report["missing"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args.manifest, args.input, args.output, write=not args.no_write)
    except ValueError as exc:
        print(f"WEB-REAL regression error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
