# WEB-REAL Regression Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the hard-coded `WEB-REAL-*` smoke check into a manifest-driven regression gate with machine-readable output.

**Architecture:** Keep static expectations in `intel/regression/web_real_manifest.json`, put matching and reporting logic in a new focused Python CLI, and preserve `scripts/check_web_real_coverage.py` as a compatibility wrapper. The first implementation only reads Phase 3 CSV rows and writes `results/phase3/web_real_regression.json`; Phase 4 ranking remains unchanged.

**Tech Stack:** Python 3 standard library (`argparse`, `csv`, `json`, `datetime`, `pathlib`), existing Phase 3 CSV schema, existing shell-based verification commands.

---

## File Structure

- Create `intel/regression/web_real_manifest.json`: manifest for the 5 dynamically verified `WEB-REAL-*` cases.
- Create `scripts/check_web_real_regression.py`: generic manifest matcher, CLI, terminal summary, JSON report writer.
- Modify `scripts/check_web_real_coverage.py`: compatibility wrapper that delegates to `check_web_real_regression.py`.
- Modify `CHANGELOG.md`: record implementation and verification results after the work is complete.
- Generate `results/phase3/web_real_regression.json`: machine-readable regression report; this is an expected pipeline artifact.

## Task 1: Add Manifest Fixture

**Files:**
- Create: `intel/regression/web_real_manifest.json`

- [ ] **Step 1: Create the manifest with all 5 WEB-REAL cases**

Use `apply_patch` to add `intel/regression/web_real_manifest.json`:

```json
{
  "schema_version": 1,
  "description": "Static regression expectations for dynamically verified WEB-REAL cases.",
  "cases": [
    {
      "id": "WEB-REAL-0001",
      "framework": "jersey",
      "component": "security/oauth1-server",
      "dynamic_verdict": "default_heap_oom_confirmed",
      "required": [
        {"field": "framework", "op": "equals", "value": "jersey"},
        {"field": "candidate_family", "op": "equals", "value": "provider_state"},
        {"field": "retained_field", "op": "contains", "value": "requestTokenByTokenString"},
        {"field": "request_flow_kind", "op": "equals", "value": "provider_field"}
      ],
      "expected": [
        {"field": "sink_shape", "op": "equals", "value": "retained_map_put"},
        {"field": "receiver_proof", "op": "contains", "value": "requestTokenByTokenString"},
        {"field": "growth_driver_kind", "op": "one_of", "values": ["map_key", "stored_value", "token_key"]}
      ],
      "deployment_condition": "Jersey OAuth1 provider is enabled and request token endpoint is reachable.",
      "notes": "Request token strings are retained in DefaultOAuth1Provider.requestTokenByTokenString."
    },
    {
      "id": "WEB-REAL-0002",
      "framework": "jersey",
      "component": "media/multipart",
      "dynamic_verdict": "default_heap_oom_confirmed_with_large_tempdir",
      "required": [
        {"field": "framework", "op": "equals", "value": "jersey"},
        {"field": "candidate_family", "op": "equals", "value": "parser_body"},
        {"field": "sink_shape", "op": "equals", "value": "parser_part_accumulator"}
      ],
      "expected": [
        {"field": "container_kind", "op": "equals", "value": "parser_transaction"},
        {"field": "growth_dimension", "op": "one_of", "values": ["part_count", "header_count", "byte_volume"]},
        {"field": "request_flow_kind", "op": "equals", "value": "parser_body_flow"}
      ],
      "deployment_condition": "Jersey multipart MessageBodyReader is enabled for attacker-controlled multipart requests.",
      "notes": "Multipart body parts are accumulated during parser transaction lifetime."
    },
    {
      "id": "WEB-REAL-0003",
      "framework": "undertow",
      "component": "core LearningPushHandler",
      "dynamic_verdict": "real_http_default_heap_oom_confirmed",
      "required": [
        {"field": "framework", "op": "equals", "value": "undertow"},
        {"field": "candidate_family", "op": "equals", "value": "listener_state"},
        {"field": "request_flow_kind", "op": "equals", "value": "listener_callback"},
        {"field": "retained_field", "op": "contains", "value": "cache"}
      ],
      "expected": [
        {"field": "sink_shape", "op": "equals", "value": "nested_retained_map_put"},
        {"field": "receiver_proof", "op": "contains", "value": "LearningPushHandler.cache"},
        {"field": "growth_dimension", "op": "contains", "value": "referer"}
      ],
      "deployment_condition": "Undertow LearningPushHandler is installed in the handler chain.",
      "notes": "Outer cache is bounded, but each per-referer inner map can grow by request path."
    },
    {
      "id": "WEB-REAL-0004",
      "framework": "undertow",
      "component": "core mod_cluster MCMP",
      "dynamic_verdict": "default_heap_oom_confirmed",
      "required": [
        {"field": "framework", "op": "equals", "value": "undertow"},
        {"field": "candidate_family", "op": "equals", "value": "management_state"},
        {"field": "request_flow_kind", "op": "equals", "value": "bounded_call_path"},
        {"field": "retained_field", "op": "one_of", "values": ["nodes", "balancers"]}
      ],
      "expected": [
        {"field": "sink_shape", "op": "equals", "value": "registry_register"},
        {"field": "receiver_proof", "op": "contains", "value": "ModClusterContainer"},
        {"field": "deployment_condition", "op": "contains", "value": "management"}
      ],
      "deployment_condition": "MCMP management endpoint is exposed to low-trust clients.",
      "notes": "Registry state grows through node, balancer, and virtual host registration."
    },
    {
      "id": "WEB-REAL-0005",
      "framework": "jetty",
      "component": "jetty-proxy / jetty-client",
      "dynamic_verdict": "real_http_default_heap_oom_confirmed",
      "required": [
        {"field": "framework", "op": "equals", "value": "jetty"},
        {"field": "candidate_family", "op": "equals", "value": "client_destination"},
        {"field": "request_flow_kind", "op": "equals", "value": "client_request_flow"},
        {"field": "sink_shape", "op": "equals", "value": "retained_map_compute"},
        {"field": "retained_field", "op": "contains", "value": "destinations"}
      ],
      "expected": [
        {"field": "receiver_proof", "op": "contains", "value": "HttpClient.destinations"},
        {"field": "growth_driver_kind", "op": "equals", "value": "origin_key"},
        {"field": "growth_dimension", "op": "equals", "value": "destination_count"}
      ],
      "deployment_condition": "ProxyServlet deployment maps attacker-controlled request data to HttpClient destination origin or tag.",
      "notes": "Harness maps attacker parameter to Jetty Request.tag() for the retained Origin.tag path."
    }
  ]
}
```

- [ ] **Step 2: Validate JSON syntax**

Run:

```bash
python3 -m json.tool intel/regression/web_real_manifest.json >/tmp/web_real_manifest.pretty.json
```

Expected: command exits 0 and prints no error.

- [ ] **Step 3: Commit the manifest**

```bash
git add intel/regression/web_real_manifest.json
git commit -m "test: add WEB-REAL regression manifest"
```

## Task 2: Add Regression Checker

**Files:**
- Create: `scripts/check_web_real_regression.py`
- Generated by test run: `results/phase3/web_real_regression.json`

- [ ] **Step 1: Write the checker implementation**

Use `apply_patch` to add `scripts/check_web_real_regression.py`:

```python
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
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"manifest root must be an object: {path}")
    return data


def load_rows(path: Path) -> list[Row]:
    if not path.exists():
        raise ValueError(f"Phase 3 CSV not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Phase 3 CSV has no header: {path}")
        return [{field: norm(row.get(field)) for field in reader.fieldnames} for row in reader]


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
    field = norm(rule.get("field"))
    op = norm(rule.get("op"))
    if not field:
        raise ValueError(f"{case_id}.{group} rule is missing field")
    if op not in {"equals", "contains", "one_of"}:
        raise ValueError(f"{case_id}.{group}.{field} has unsupported op: {op}")
    if op in {"equals", "contains"} and "value" not in rule:
        raise ValueError(f"{case_id}.{group}.{field} requires value")
    if op == "one_of":
        values = rule.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError(f"{case_id}.{group}.{field} requires non-empty values")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="WEB-REAL regression manifest")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Phase 3 merged CSV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Regression JSON report")
    parser.add_argument("--no-write", action="store_true", help="Do not write the JSON report")
    return parser.parse_args()


def run(manifest_path: Path = DEFAULT_MANIFEST, input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT, write: bool = True) -> int:
    manifest = load_json(manifest_path)
    cases = validate_manifest(manifest)
    rows = load_rows(input_path)
    report = build_report(manifest_path, input_path, cases, rows)
    if write:
        write_report(output_path, report)
    print_summary(report)
    return 0 if report["partial"] == 0 and report["missing"] == 0 else 1


def main() -> int:
    args = parse_args()
    try:
        return run(args.manifest, args.input, args.output, write=not args.no_write)
    except ValueError as exc:
        print(f"WEB-REAL regression error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the checker**

Run:

```bash
python3 scripts/check_web_real_regression.py
```

Expected: exits 0, prints one `hit` line for each `WEB-REAL-0001` through `WEB-REAL-0005`, and prints `WEB-REAL regression: 5/5 hit, 0 partial, 0 missing`.

- [ ] **Step 3: Inspect generated report**

Run:

```bash
python3 -m json.tool results/phase3/web_real_regression.json >/tmp/web_real_regression.pretty.json
```

Expected: exits 0. Then run:

```bash
rg -n '"known_vuln_recall": 1.0|"status": "hit"' results/phase3/web_real_regression.json
```

Expected: output includes one `known_vuln_recall` line and five `"status": "hit"` lines.

- [ ] **Step 4: Commit the checker and report**

```bash
git add scripts/check_web_real_regression.py results/phase3/web_real_regression.json
git commit -m "test: add WEB-REAL regression checker"
```

## Task 3: Convert Coverage Script to Compatibility Wrapper

**Files:**
- Modify: `scripts/check_web_real_coverage.py`

- [ ] **Step 1: Replace the hard-coded matcher script with a wrapper**

Use `apply_patch` to replace the entire contents of `scripts/check_web_real_coverage.py`:

```python
#!/usr/bin/env python3
"""Compatibility wrapper for WEB-REAL static coverage checks."""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from check_web_real_regression import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the compatibility command**

Run:

```bash
python3 scripts/check_web_real_coverage.py
```

Expected: exits 0 and prints the same 5/5 hit summary as `scripts/check_web_real_regression.py`.

- [ ] **Step 3: Commit the wrapper**

```bash
git add scripts/check_web_real_coverage.py
git commit -m "refactor: delegate WEB-REAL coverage check to regression gate"
```

## Task 4: Verification and Changelog

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run focused verification**

Run:

```bash
python3 scripts/check_web_real_regression.py
python3 scripts/check_web_real_coverage.py
python3 scripts/check_phase3_consistency.py
./dos-web-analyzer analyze
PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity
PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py
```

Expected:

```text
WEB-REAL regression: 5/5 hit, 0 partial, 0 missing
```

`check_phase3_consistency.py` should report all Phase 3 rows matched. `./dos-web-analyzer analyze` should regenerate Phase 4 outputs without errors. AOSP monotonicity should pass 288 lattice points. AOSP regression should report `0 regression(s)`.

- [ ] **Step 2: Update CHANGELOG.md**

Run:

```bash
date '+%Y-%m-%d %H:%M'
```

Use the returned timestamp in the `修改时间` field. Add a new top entry above the existing latest entry:

```markdown
## [2026-06-19] 第三部分 WEB-REAL 回归门禁实现

### 修改时间
2026-06-19 22:30

### 变更类型
- [新增功能] WEB-REAL manifest 回归门禁
- [功能改进] WEB-REAL coverage 兼容入口

### 核心改动
- 新增 `intel/regression/web_real_manifest.json`，将 5 个已动态验证真阳的静态期望从 Python lambda 迁移到可审计 manifest。
- 新增 `scripts/check_web_real_regression.py`，支持 `equals`、`contains`、`one_of` 规则，输出 `hit`、`partial`、`missing` 和机器可读 JSON 报告。
- 将 `scripts/check_web_real_coverage.py` 改为兼容 wrapper，保留现有命令入口。
- 关键技术决策：本轮只固定 known-vuln regression gate，不改变 Phase 4 排序权重或 CodeQL 查询。

### 交付成果
- 新增 manifest：`intel/regression/web_real_manifest.json`
- 新增脚本：`scripts/check_web_real_regression.py`
- 修改脚本：`scripts/check_web_real_coverage.py`
- 新增结果：`results/phase3/web_real_regression.json`
- 修改文档：`CHANGELOG.md`
- 测试/验证结果：`python3 scripts/check_web_real_regression.py` 5/5 hit；`python3 scripts/check_web_real_coverage.py` 5/5 hit；`python3 scripts/check_phase3_consistency.py` 37/37 matched；`./dos-web-analyzer analyze` 生成 37 条 Phase 4 候选；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 -m eval.monotonicity` 通过 288 个积格点；`PYTHONPATH=/home/furina/new_tool/dos-analysis python3 /home/furina/new_tool/dos-analysis/intel/regression/check_regression.py` 通过，0 regression(s)。

### 依赖与影响
- 依赖：当前 Phase 3 proof/request-flow schema 和 5/5 WEB-REAL smoke hit 基线。
- 对后续工作的影响：Phase 4 evaluation summary、capacity/lifespan proof 和 Dr.D compatibility manifest 可复用该 regression report 结构。
- 破坏性变更：无；旧 coverage 命令仍可使用。
```

If the actual verification counts differ, replace only the numbers in the example sentence with the observed values.

- [ ] **Step 3: Commit the changelog and any regenerated outputs**

```bash
git add CHANGELOG.md results/phase4 results/phase4_report.md
git commit -m "docs: record WEB-REAL regression gate verification"
```

If `./dos-web-analyzer analyze` does not change Phase 4 outputs, only commit `CHANGELOG.md`.

## Self-Review Checklist

- Spec coverage: Task 1 implements the manifest; Task 2 implements the checker and JSON report; Task 3 preserves compatibility; Task 4 covers verification and changelog.
- Placeholder scan: no implementation step uses undefined placeholders.
- Type consistency: rules use `field`, `op`, `value`, and `values`; checker validates and consumes the same names.
- Scope check: Phase 4 ranking and validation recipe generation are intentionally deferred, matching the approved spec non-goals.
