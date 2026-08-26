from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from dosweb.benchmark.poc33_demo import (
    build_demo_metrics,
    classify_dynamic_case,
    main,
)


def _dynamic_result(
    finding_id: str,
    *,
    verdict: str,
    status: str,
    attacker_model: str = "anonymous",
    is_default: bool = True,
    requires_admin: bool = False,
    requires_config_change: bool = False,
    requires_optional_component: bool = False,
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "target": "example/project",
        "verdict": verdict,
        "status": status,
        "default_deployment": {"is_default": is_default},
        "reachability": {"attacker_model": attacker_model},
        "utilization_conditions": {
            "requires_admin": requires_admin,
            "requires_config_change": requires_config_change,
            "requires_optional_component": requires_optional_component,
        },
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _tree_snapshot(root: Path) -> dict[str, tuple[str, int]]:
    return {
        str(path.relative_to(root)): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _historical_asset_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    expected = root / "results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233"
    if expected.is_dir():
        return root
    # Linked worktrees intentionally omit gitignored benchmark assets.  The
    # common checkout remains the immutable source for this historical test.
    common_checkout = root.parent.parent
    if (common_checkout / expected.relative_to(root)).is_dir():
        return common_checkout
    raise AssertionError("PoC-33 historical benchmark assets are missing")


class DynamicCaseTaxonomyTests(unittest.TestCase):
    def test_confirmed_default_ordinary_case_is_eligible_positive(self):
        result = _dynamic_result(
            "finding:positive",
            verdict="confirmed",
            status="confirmed_oom",
            attacker_model="low_privilege",
        )

        self.assertEqual("eligible_positive", classify_dynamic_case(result))

    def test_confirmed_admin_or_non_default_case_is_unscored(self):
        admin = _dynamic_result(
            "finding:admin",
            verdict="confirmed",
            status="confirmed_oom",
            attacker_model="admin",
            requires_admin=True,
        )
        configured = _dynamic_result(
            "finding:configured",
            verdict="confirmed",
            status="confirmed_oom",
            requires_config_change=True,
        )
        optional = _dynamic_result(
            "finding:optional",
            verdict="confirmed",
            status="confirmed_oom",
            requires_optional_component=True,
        )
        non_default = _dynamic_result(
            "finding:non-default",
            verdict="confirmed",
            status="confirmed_oom",
            is_default=False,
        )

        self.assertEqual("unscored", classify_dynamic_case(admin))
        self.assertEqual("unscored", classify_dynamic_case(configured))
        self.assertEqual("unscored", classify_dynamic_case(optional))
        self.assertEqual("unscored", classify_dynamic_case(non_default))

    def test_only_proven_bound_or_reachability_failures_are_hard_negatives(self):
        for status in (
            "effective_bound_confirmed",
            "default_not_reachable",
            "auth_blocked",
            "precondition_blocked",
        ):
            with self.subTest(status=status):
                result = _dynamic_result(
                    f"finding:{status}",
                    verdict="not_confirmed" if "confirmed" in status else "blocked",
                    status=status,
                )
                self.assertEqual("hard_negative", classify_dynamic_case(result))

    def test_growth_probe_and_tested_bound_results_are_weak_not_hard(self):
        for status in (
            "observed_growth_not_confirmed",
            "probe_semantics_failed",
            "not_reproduced_under_tested_bounds",
            "inconclusive_probe",
        ):
            with self.subTest(status=status):
                result = _dynamic_result(
                    f"finding:{status}",
                    verdict="not_confirmed",
                    status=status,
                )
                self.assertEqual("weak_negative", classify_dynamic_case(result))


class DemoMetricsTests(unittest.TestCase):
    def test_metrics_keep_legacy_precision_separate_from_demo_gates(self):
        statuses = [
            {
                "batch_target_slug": "a",
                "status": "completed",
                "stage_metrics": {"entries": {"query_count": 7, "query_diagnostic_count": 0}},
            },
            {
                "batch_target_slug": "b",
                "status": "completed",
                "stage_metrics": {"entries": {"query_count": 7, "query_diagnostic_count": 1}},
            },
            {"batch_target_slug": "c", "status": "failed", "stage_metrics": {}},
        ]
        truth = [
            {"record_id": "truth:1", "status": "full_chain_finding"},
            {"record_id": "truth:2", "status": "full_chain_finding"},
            {"record_id": "truth:3", "status": "growth_only"},
        ]
        static_findings = [
            {"finding_id": "finding:positive", "family_key": "family:1", "verdict": "static_vulnerable"},
            {"finding_id": "finding:admin", "family_key": "family:1", "pipeline_verdict": "static_unknown"},
            {"finding_id": "finding:bound", "family_key": "family:2", "static_conclusion": "static_vulnerable"},
            {"finding_id": "finding:growth", "family_key": "family:3", "pipeline_verdict": "static_unknown"},
            {"finding_id": "finding:auth", "family_key": "family:4", "pipeline_verdict": "static_unknown"},
        ]
        dynamic = [
            _dynamic_result("finding:positive", verdict="confirmed", status="confirmed_oom"),
            _dynamic_result(
                "finding:admin",
                verdict="confirmed",
                status="confirmed_oom",
                attacker_model="admin",
                requires_admin=True,
            ),
            _dynamic_result("finding:bound", verdict="not_confirmed", status="effective_bound_confirmed"),
            _dynamic_result("finding:growth", verdict="not_confirmed", status="observed_growth_not_confirmed"),
            _dynamic_result("finding:auth", verdict="blocked", status="auth_blocked"),
        ]

        metrics = build_demo_metrics(
            statuses=statuses,
            truth_dispositions=truth,
            static_findings=static_findings,
            dynamic_results=dynamic,
        )

        self.assertEqual(3, metrics["targets"])
        self.assertEqual(2, metrics["completed_targets"])
        self.assertEqual(14, metrics["selected_queries"])
        self.assertEqual(1, metrics["query_diagnostics"])
        self.assertEqual(3, metrics["truth"])
        self.assertEqual(2, metrics["full_chain_finding"])
        self.assertEqual(5, metrics["queue"])
        self.assertEqual(4, metrics["families"])
        self.assertEqual(1, metrics["eligible_positive"])
        self.assertEqual(2, metrics["hard_negative"])
        self.assertEqual(1, metrics["weak_negative"])
        self.assertEqual(1, metrics["unscored"])
        self.assertEqual(2, metrics["tp"])
        self.assertEqual(2, metrics["fp"])
        self.assertEqual(1, metrics["blocked"])
        self.assertEqual(0.5, metrics["precision"])
        self.assertEqual(1, metrics["eligible_positive_static_vulnerable"])
        self.assertEqual(1, metrics["hard_negative_static_vulnerable"])
        self.assertEqual(
            {"numerator": 1, "denominator": 1, "ratio": 1.0},
            metrics["ordinary_positive_recall"],
        )
        self.assertEqual(
            {"numerator": 1, "denominator": 2, "ratio": 0.5},
            metrics["hard_negative_safety"],
        )

    def test_historical_baseline_numbers_are_frozen(self):
        root = _historical_asset_root()
        batch = root / "results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233"
        recall = root / "results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-recall-p0-final"
        audit = root / "results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-static-positive-audit"
        dynamic = root / "results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-dynamic-validation"

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evaluation"
            self.assertEqual(
                0,
                main(
                    [
                        "--static-batch", str(batch),
                        "--recall", str(recall),
                        "--static-audit", str(audit),
                        "--dynamic", str(dynamic),
                        "--output", str(output),
                    ]
                ),
            )
            metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
            case_rows = [
                json.loads(line)
                for line in (output / "case_matrix.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(21, metrics["targets"])
        self.assertEqual(33, metrics["truth"])
        self.assertEqual(6, metrics["eligible_positive"])
        self.assertEqual(15, metrics["hard_negative"])
        self.assertEqual(9, metrics["tp"])
        self.assertEqual(29, metrics["fp"])
        self.assertEqual(11, metrics["blocked"])
        self.assertEqual(0.236842, metrics["precision"])
        self.assertEqual(49, len(case_rows))


class DemoEvaluatorIsolationTests(unittest.TestCase):
    def test_production_modules_do_not_import_demo_oracle(self):
        root = Path(__file__).resolve().parents[1]
        production_sources = [root / "dosweb/production.py"]
        for package in ("growth", "flows", "lifecycle", "conclude"):
            production_sources.extend(sorted((root / "dosweb" / package).rglob("*.py")))
        for path in production_sources:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "dosweb.benchmark.poc33_demo",
                source,
                str(path.relative_to(root)),
            )

    def test_cli_is_read_only_and_rejects_output_inside_inputs(self):
        statuses = [{"batch_target_slug": "a", "status": "completed", "stage_metrics": {}}]
        truth = [{"record_id": "truth:1", "status": "full_chain_finding"}]
        static_findings = [{"finding_id": "finding:1", "pipeline_verdict": "static_unknown"}]
        dynamic_results = [_dynamic_result("finding:1", verdict="confirmed", status="confirmed_oom")]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch = root / "batch"
            recall = root / "recall"
            audit = root / "audit"
            dynamic = root / "dynamic"
            _write_jsonl(batch / "aggregate_status.jsonl", statuses)
            _write_jsonl(recall / "truth_dispositions.jsonl", truth)
            _write_jsonl(audit / "static_positive_queue.jsonl", static_findings)
            _write_jsonl(dynamic / "findings.jsonl", dynamic_results)
            _write_jsonl(dynamic / "blocked_or_rejected.jsonl", [])
            before = {
                name: _tree_snapshot(path)
                for name, path in (("batch", batch), ("recall", recall), ("audit", audit), ("dynamic", dynamic))
            }

            output = root / "evaluation"
            self.assertEqual(
                0,
                main(
                    [
                        "--static-batch", str(batch),
                        "--recall", str(recall),
                        "--static-audit", str(audit),
                        "--dynamic", str(dynamic),
                        "--output", str(output),
                    ]
                ),
            )
            after = {
                name: _tree_snapshot(path)
                for name, path in (("batch", batch), ("recall", recall), ("audit", audit), ("dynamic", dynamic))
            }
            self.assertEqual(before, after)
            self.assertTrue((output / "REPORT.md").is_file())

            with self.assertRaises(ValueError):
                main(
                    [
                        "--static-batch", str(batch),
                        "--recall", str(recall),
                        "--static-audit", str(audit),
                        "--dynamic", str(dynamic),
                        "--output", str(batch / "forbidden-output"),
                    ]
                )


if __name__ == "__main__":
    unittest.main()
