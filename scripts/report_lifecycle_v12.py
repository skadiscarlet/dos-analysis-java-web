#!/usr/bin/env python3
"""Build compact v1.2 reports from completed frozen local acceptance artifacts."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dosweb.artifacts.identifiers import canonical_json
from dosweb.resource_lifecycle.adapters import extracted_from_dict, validate_extracted
from dosweb.resource_lifecycle.commands import _analyze_payload, _implementation_sha256, _QUERY
from dosweb.resource_lifecycle.io import atomic_write_json, atomic_write_text, load_json_regular
from dosweb.resource_lifecycle.shards import ShardReader
from dosweb.resource_lifecycle.sharded_run import iter_run_units
from dosweb.resource_lifecycle.source_evaluation import _disable_cross_event_propagation, _expected, _matches, _observation

CASES = ROOT / "tests/fixtures/resource_lifecycle_v1_1/source-cases.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "<external-local-artifact>/" + Path(path).name


def sanitized(value):
    if isinstance(value, dict):
        return {key: sanitized(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT) + "/", "") if str(ROOT) in value else (relative(value) if value.startswith("/") else value)
    return value


def xml_results(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError(f"test XML has no completed test cases: {relative(path)}")
    statuses = {status: set() for status in ("passed", "failure", "error", "skipped")}
    for case in cases:
        identity = case.get("classname", "") + "::" + case.get("name", "")
        status = next((name for name in ("error", "failure", "skipped") if case.find(name) is not None), "passed")
        statuses[status].add(identity)
    return {"path": relative(path), "sha256": digest(path), "testcases": len(cases),
            "ids": {status: sorted(ids) for status, ids in statuses.items()},
            "counts": {status: len(ids) for status, ids in statuses.items()}}


def diff_tests(baseline, current):
    result = {"baseline": baseline, "current": current}
    for status in ("failure", "error", "skipped"):
        before, after = set(baseline["ids"][status]), set(current["ids"][status])
        result[status] = {"added_ids": sorted(after - before), "removed_ids": sorted(before - after),
                          "persistent_ids": sorted(before & after)}
    result["new_test_ids"] = sorted(set().union(*map(set, current["ids"].values())) - set().union(*map(set, baseline["ids"].values())))
    return result


def passed_test(xml, method):
    unsuccessful = set().union(*(set(xml["ids"][status]) for status in ("failure", "error", "skipped")))
    return any(identity.endswith("::" + method) and identity not in unsuccessful for identity in xml["ids"]["passed"])


def csv_file(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
                             for key, value in row.items() if key in fields})


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def committed_implementation_hash():
    """Hash HEAD blobs using the same ordered identity as the running backend."""
    dosweb = ROOT / "dosweb"
    paths = tuple((dosweb / "resource_lifecycle").glob("*.py")) + (
        dosweb / "cli.py", dosweb / "codeql/decoder.py", dosweb / "codeql/runner.py", *_QUERY)
    identity = []
    try:
        for path in sorted(paths, key=str):
            content = subprocess.check_output(["git", "show", "HEAD:" + path.relative_to(ROOT).as_posix()],
                                              cwd=ROOT, stderr=subprocess.DEVNULL)
            identity.append({"path": path.relative_to(dosweb).as_posix(), "sha256": hashlib.sha256(content).hexdigest()})
    except subprocess.CalledProcessError:
        return None
    return hashlib.sha256(canonical_json(identity)).hexdigest()


def build(root_run, output, *, delivery_reviewed=False):
    inputs = {"scaling": root_run / "scaling-frozen-01/scaling-results.json",
        "project": root_run / "project-frozen-01/project-results.json",
        "baseline": root_run / "tests/baseline.xml", "current": root_run / "tests/current.xml",
        "source": root_run / "tests/source-frozen.xml", "cases": CASES,
        "execution_context": root_run / "execution-context.json", "cli_sharded": root_run / "tests/cli-sharded.xml"}
    execution_context = load_json_regular(inputs["execution_context"])
    scaling = load_json_regular(inputs["scaling"])
    project = load_json_regular(inputs["project"])
    suite = load_json_regular(CASES)
    if scaling.get("status") == "running" or project.get("status") == "running":
        raise ValueError("acceptance inputs are still running; no final report was generated")
    if sorted(group["factor"] for group in scaling["groups"]) != [1, 2, 4]:
        raise ValueError("fixed scaling denominator is incomplete")
    if len(suite["cases"]) != 12:
        raise ValueError("frozen source-case denominator changed")
    baseline, current, source_tests = [xml_results(inputs[name]) for name in ("baseline", "current", "source")]
    cli_tests = xml_results(inputs["cli_sharded"])
    test_diff = diff_tests(baseline, current)
    run = root_run / "scaling-frozen-01/scale-1x/run"
    reader = ShardReader(run)
    if reader.index["identity"].get("analysis_status") != "complete":
        raise ValueError("scale-1x run is incomplete; cannot invent the full/ablation comparison")
    full_by_id = {}
    ablated_by_id = {}
    units = {}
    provenance = []
    fact_hashes = {}
    properties = []
    for unit_id, payload in iter_run_units(reader):
        if payload.get("status") != "analyzed":
            raise ValueError("failed source unit cannot disappear from comparison")
        single = validate_extracted(extracted_from_dict(payload["facts"]))
        if len(single.units) != 1 or single.units[0].unit_id != unit_id:
            raise ValueError("source shard identity mismatch")
        unit = single.units[0]
        full = payload["results"]["units"][0]
        ablated, _ = _disable_cross_event_propagation(unit)
        ablated_facts = replace(single, units=(ablated,))
        if ablated_facts.facts != single.facts or ablated_facts.snapshot_sha256 != single.snapshot_sha256:
            raise ValueError("ablation changed raw source facts")
        altered = _analyze_payload(ablated_facts)["units"][0]
        units[unit_id] = (unit, ablated)
        full_by_id[unit_id], ablated_by_id[unit_id] = full, altered
        fact_hashes[unit_id] = single.snapshot_sha256
        provenance = single.coverage.get("query_provenance", [])
        for mode, result in (("full", full), ("disable_cross_event_propagation", altered)):
            for prop in result["properties"]:
                properties.append({"data_source": "source_fixture_12_cases", "mode": mode, **prop})
    if len(full_by_id) != 12:
        raise ValueError("scale-1x must retain twelve source units")
    project_reader = ShardReader(root_run / "project-frozen-01/analysis")
    project_property_ids = set()
    project_family_ids = set()
    project_units = set()
    for unit_id, payload in iter_run_units(project_reader):
        if payload.get("status") != "analyzed":
            continue
        project_units.add(unit_id)
        for result in payload["results"]["units"]:
            for prop in result["properties"]:
                if prop["property_id"] in project_property_ids:
                    raise ValueError("project published a duplicate property identity")
                project_property_ids.add(prop["property_id"])
                if prop.get("resource_family_id"):
                    project_family_ids.add(prop["resource_family_id"])
                properties.append({"data_source": "project_mixed_inputs", "mode": "full", **prop})
    if any(not set(row.get("property_ids", [])).issubset(project_property_ids) for row in project["ledger"]):
        raise ValueError("project ledger references an unpublished property")
    comparisons = []
    for case in suite["cases"]:
        unit_id = case["entry_callable"].replace(".SourcePairs.", ".SourcePairsScale001.")
        if unit_id not in full_by_id:
            raise ValueError("frozen source case has no extracted unit")
        for value in case["expectations"]:
            expected = _expected(value)
            mode_index = 0 if expected.mode == "full" else 1
            result = full_by_id[unit_id] if mode_index == 0 else ablated_by_id[unit_id]
            observed = _observation(expected, result, units[unit_id][mode_index])
            comparisons.append({"case_id": case["case_id"], "analysis_unit_id": unit_id,
                "mode": expected.mode, "raw_fact_snapshot_sha256": fact_hashes[unit_id],
                "dimension": expected.dimension, "scope": expected.scope, "cut": expected.cut,
                "expected_status": expected.lifecycle_status, "expected_upper_bound": expected.upper_bound,
                "expected_reason_contains": expected.reason_contains,
                "property_id": observed["property_id"], "actual_status": observed["lifecycle_status"],
                "actual_upper_bound": observed["upper_bound"], "unknown_reasons": observed["reason_codes"],
                "analysis_terminated": result.get("terminated") is True,
                "matches": _matches(expected, observed)})
    modes = {}
    for mode in ("full", "disable_cross_event_propagation"):
        rows = [row for row in comparisons if row["mode"] == mode]
        modes[mode] = {"requested_cases": 12, "compared_cases": len(rows), "matches": sum(row["matches"] for row in rows),
            "unknown": sum(row["actual_status"] == "unknown" for row in rows),
            "analysis_budget_exits": sum(not row["analysis_terminated"] for row in rows),
            "expected_unknown_matches": sum(row["expected_status"] == "unknown" and row["matches"] for row in rows),
            "mismatch_case_ids": [row["case_id"] for row in rows if not row["matches"]]}
    ledger = [{"data_source": "project_mixed_inputs", **row} for row in project["ledger"]]
    if project["requested"] != len(project["ledger"]):
        raise ValueError("project request denominator differs from ledger")
    for group in scaling["groups"]:
        factor = group["factor"]
        receipt_rows = group.get("analysis_receipt", {}).get("units", [])
        known = {row["unit_id"]: row["status"] for row in receipt_rows}
        for copy in range(1, factor + 1):
            for case in suite["cases"]:
                unit_id = case["entry_callable"].replace(".SourcePairs.", f".SourcePairsScale{copy:03d}.")
                ledger.append({"data_source": f"scaling_{factor}x_repeated_fixture", "input_id": unit_id,
                    "entry_callable": unit_id, "mapping": "mapped" if unit_id in known else "unavailable",
                    "extraction": "extracted" if unit_id in known else "unknown",
                    "analysis": known.get(unit_id, "failed"), "reason": None if unit_id in known else group.get("status")})
    for case in suite["cases"]:
        ledger.append({"data_source": "source_fixture_12_cases", "input_id": case["case_id"],
            "entry_callable": case["entry_callable"].replace(".SourcePairs.", ".SourcePairsScale001."),
            "mapping": "mapped", "extraction": "extracted", "analysis": "analyzed",
            "reason": "full_and_ablated_comparison_reuses_scaling_1x"})
    current_impl = _implementation_sha256()
    impl_matches = current_impl == reader.index["identity"].get("implementation_sha256") == execution_context.get("implementation_sha256")
    report_head = git("rev-parse", "HEAD")
    implementation_commit = report_head if impl_matches and committed_implementation_hash() == current_impl else None
    h1_tests = ["test_multiple_resources_oracle_independence_and_order", "test_real_solver_properties_are_shared_by_method_and_candidate",
                "test_state_only_zero_does_not_publish_a_bound"]
    h2_tests = ["test_mixed_inputs_keep_denominator_and_share_computation", "test_existing_growth_jsonl_import_ignores_old_judgments",
                "test_duplicate_or_missing_import_record_is_not_silently_dropped", "test_shared_query_failure_invalidates_every_input"]
    project_ok = (project["requested"] > 0 and any(row["kind"] == "method" and row["analysis"] == "analyzed" for row in project["ledger"])
        and any(row["kind"] == "candidate" and row["analysis"] == "analyzed" for row in project["ledger"])
        and any(row.get("imported_record_id") and row["analysis"] == "analyzed" for row in project["ledger"])
        and all(sum(project["stage_counts"][stage].values()) == project["requested"] for stage in ("mapping", "extraction", "analysis")))
    replay_ok = all(group.get("replay", {}).get("consistent") is True and group.get("replay", {}).get("mode") == "semantic_replay"
                    and group.get("replay", {}).get("scope") == "full_run" and group.get("status") == "complete" for group in scaling["groups"])
    source_xml_ok = not source_tests["counts"]["failure"] and not source_tests["counts"]["error"] and source_tests["counts"]["passed"] > 0
    gates = {
        "H1": {"status": "pass" if impl_matches and replay_ok and source_xml_ok
               and passed_test(source_tests, "test_compiled_multiple_families_cli_evaluation_relocated_replay")
               and all(passed_test(current, name) for name in h1_tests) else "pending",
               "evidence": [relative(inputs["current"]), relative(inputs["source"]), relative(inputs["scaling"])], "required_test_names": h1_tests},
        "H2": {"status": "pass" if project_ok and all(passed_test(current, name) for name in h2_tests) else "pending",
               "evidence": [relative(inputs["project"]), relative(inputs["current"])], "required_test_names": h2_tests},
        "H3": {"status": "pass" if replay_ok and scaling.get("real_bytes_exceed_old_limit_with_full_replay") is True
               and passed_test(current, "test_valid_hashes_cannot_mask_semantic_tamper")
               and passed_test(cli_tests, "test_missing_required_shard_returns_nonzero") else "pending",
               "evidence": [relative(inputs["scaling"]), relative(inputs["current"]), relative(inputs["cli_sharded"])]},
        "H4": {"status": "blocked", "independent_modules": 0, "reason": "未提供两个独立已有模块；固定 fixture 与规模副本均不计独立模块。"},
        "H5": {"status": "pass" if len(comparisons) == 24 and source_xml_ok and impl_matches else "pending",
               "evidence": ["comparison.csv", "metrics.json", relative(inputs["source"])], "oracle_modified": False},
        "H6": {"status": "pass" if delivery_reviewed and implementation_commit else "pending",
               "delivery_review_attested": delivery_reviewed,
               "reason": "已通过 --delivery-reviewed 记录交付审查，且实现 commit 与运行源码 hash 一致。" if delivery_reviewed and implementation_commit
                         else "等待最终文档、交付清单、失败 ID 差分和 Git 提交审查。"},
    }
    metrics = {"implementation_status": "partial", "independent_modules": 0,
        "project_mixed_inputs": {"requested": project["requested"], "stage_counts": project["stage_counts"], "status": project["status"],
            "unique_analysis_units": len(project_units), "unique_resource_families": len(project_family_ids),
            "unique_published_properties": len(project_property_ids), "repeated_input_references_are_not_independent_resources": True},
        "source_fixture": {"independent_projects": 0, "requested_cases": 12, "modes": modes,
            "published_property_records": sum(prop["data_source"] == "source_fixture_12_cases" for prop in properties),
            "unknown_is_not_detection": True, "facts_reused_from": "scaling_1x", "independent_experiments_added": 0},
        "scaling_repeated_fixture": {"requested_by_factor": {str(g["factor"]): 12 * g["factor"] for g in scaling["groups"]},
                                    "independent_projects": 0},
        "tests": {"baseline": baseline["counts"], "current": current["counts"], "source_frozen": source_tests["counts"],
                  "cli_sharded_supplement": cli_tests}}
    manual_path = root_run / "manual-ir/metrics.json"
    if manual_path.exists():
        metrics["manual_ir_regression"] = sanitized(load_json_regular(manual_path))
    metrics["source_fixture"]["extracted_relation_counts"] = {
        "families": sum(len(pair[0].program.families) for pair in units.values()),
        "call_bindings": sum(len(pair[0].program.call_bindings) for pair in units.values()),
        "task_bindings": sum(len(pair[0].program.task_bindings) for pair in units.values()),
        "coverage_gap_reasons": dict(Counter(gap[3] for pair in units.values() for gap in pair[0].program.coverage_gaps)),
        "interpretation": "observed model relations and explicit gaps, not exhaustive relation recall",
    }
    for mode, mode_metrics in modes.items():
        selected = [prop for prop in properties if prop["data_source"] == "source_fixture_12_cases" and prop["mode"] == mode]
        mode_metrics["by_dimension"] = {}
        for dimension in sorted({prop["dimension"] for prop in selected}):
            rows = [prop for prop in selected if prop["dimension"] == dimension]
            statuses = dict(Counter(prop["status"] for prop in rows))
            mode_metrics["by_dimension"][dimension] = {
                "published_properties": len(rows), "status_counts": statuses,
                "determinate_fraction": sum(prop["status"] != "unknown" for prop in rows) / len(rows),
                "unknown_reasons": dict(Counter(reason for prop in rows if prop["status"] == "unknown" for reason in prop["unknown_reasons"])),
            }
    paired = {(row["case_id"], row["mode"]): row for row in comparisons}
    metrics["source_fixture"]["determinacy_gains"] = sum(
        paired[case["case_id"], "full"]["actual_status"] != "unknown" and
        paired[case["case_id"], "disable_cross_event_propagation"]["actual_status"] == "unknown"
        for case in suite["cases"]
    )
    manifest = {"format": "lifecycle-v1.2-report-v1", "report_generation_head": report_head,
        "runtime_head": execution_context["runtime_head"],
        "runtime_implementation_dirty": execution_context["runtime_implementation_dirty"],
        "implementation_commit": implementation_commit,
        "branch": git("branch", "--show-current"), "worktree_status": git("status", "--short"),
        "fixed_v1_1_baseline": "2ee16220e78dd088ab5c67277696429e71d53c71",
        "implementation_sha256": current_impl, "frozen_run_identity": reader.index["identity"],
        "frozen_implementation_matches_current": impl_matches, "query_provenance": provenance,
        "inputs": {name: {"path": relative(path), "sha256": digest(path)} for name, path in inputs.items()},
        "raw_fact_snapshots": fact_hashes, "report_script_sha256": digest(Path(__file__)),
        "source_selection": "twelve frozen v1.1 cases mapped to SourcePairsScale001; expectations never passed to analysis",
        "rerun_commands": ["python scripts/evaluate_lifecycle_v12_scaling.py --out <new-persistent-scaling-directory>",
            f"python scripts/report_lifecycle_v12.py --root-run {relative(root_run)} --out {relative(output)}"],
        "command_evidence": [group.get("reused_extraction", {}).get("compilation_log", {}).get("path")
            or relative(root_run / f"scaling-frozen-01/scale-{group['factor']}x/logs/database-create.log")
            for group in scaling["groups"]],
        "distribution": "仅紧凑汇总；源码、数据库、分片及原始日志保留在本地运行目录，不随报告提交。"}
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("metrics.json", metrics), ("scaling.json", scaling), ("gates.json", gates),
                         ("run-manifest.json", manifest), ("baseline-test-diff.json", test_diff)):
        atomic_write_json(output / name, sanitized(value))
    csv_file(output / "input-ledger.csv", ledger, ["data_source", "input_id", "kind", "entry_callable", "mapping", "extraction", "analysis",
        "reason", "resource_family_ids", "property_ids", "imported_record_id", "candidate_file_sha256", "source_sha256"])
    csv_file(output / "properties.csv", properties, ["data_source", "mode", "property_id", "analysis_unit_id", "resource_family_id", "executor_id",
        "dimension", "scope", "cut", "status", "upper_bound", "relation", "assumptions", "coverage_gaps", "unknown_reasons", "evidence_refs"])
    csv_file(output / "comparison.csv", comparisons, ["case_id", "analysis_unit_id", "mode", "raw_fact_snapshot_sha256", "dimension", "scope", "cut",
        "property_id", "expected_status", "expected_upper_bound", "expected_reason_contains", "actual_status", "actual_upper_bound", "unknown_reasons", "analysis_terminated", "matches"])
    full, ablated = modes["full"], modes["disable_cross_event_propagation"]
    summary = f"""# 资源生命周期 v1.2 验收汇总

整轮状态：**partial**。独立已有模块为 0，H4 blocked；H6 {gates['H6']['status']}。

## 输入分母

- 项目混合输入：{project['requested']} 条，状态 `{project['status']}`；逐阶段去向见 input-ledger.csv。
- 冻结源码：同一 fixture 的 12 个检查案例，直接复用规模 1× 的同一事实，不增加独立实验。
- 规模组：1×/2×/4× 共分别 12/24/48 个方法；仅为固定结构重命名副本，不计独立项目。
- 项目重复引用按原始输入保留台账，资源/性质仅按唯一身份计数；公开 properties.csv 包含其全部引用对象。

## 同事实评价

完整传播匹配 {full['matches']}/12，unknown {full['unknown']}；消融匹配 {ablated['matches']}/12，unknown {ablated['unknown']}。
完整模式不匹配案例：{', '.join(full['mismatch_case_ids']) or '无'}。原 oracle 未修改；backend unknown 如实保留。
期望 unknown 的匹配不是漏洞检出。评价仅选择正式发布性质；缺失或歧义不会生成上界零。

## 验收

{chr(10).join('- ' + name + ': ' + gate['status'] for name, gate in gates.items())}

规模、实际字节数、峰值 RSS 和迁移目录后的语义重放见 scaling.json。测试失败、错误和 skip 按测试 ID 比较，见 baseline-test-diff.json。

## 限制

未提供两个独立已有模块，本报告不作泛化结论。任务终止切面不证明任务最终调度或总内存上界。
GitHub 交付仅含紧凑报告；真实源码、数据库、分片和日志仍位于本地持久运行目录。
运行时 HEAD/dirty、报告生成时 HEAD、同内容实现 commit、查询/实现/事实 hash 和重跑命令见 run-manifest.json。
"""
    atomic_write_text(output / "summary.md", summary)
    return {"report_status": "generated", "implementation_status": "partial", "gates": {name: gate["status"] for name, gate in gates.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-run", type=Path, default=ROOT / ".local-runs/v1.2")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/lifecycle-v1.2")
    parser.add_argument("--delivery-reviewed", action="store_true", help="attest completed delivery/file/test-ID/baseline/command review; default H6 remains pending")
    args = parser.parse_args(argv)
    try:
        result = build(args.root_run.resolve(), args.out.resolve(), delivery_reviewed=args.delivery_reviewed)
    except Exception as exc:
        print(json.dumps({"report_status": "not_generated", "reason": type(exc).__name__, "detail": sanitized(str(exc))}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
