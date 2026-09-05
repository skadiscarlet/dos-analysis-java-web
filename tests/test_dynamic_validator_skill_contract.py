#!/usr/bin/env python3
"""Regression tests for the user-level Java Web DoS validation skills."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


CODEX_SKILLS = Path("/home/furina/.codex/skills")
AGGREGATOR_PATH = (
    CODEX_SKILLS
    / "java-web-dos-dynamic-validator"
    / "scripts"
    / "aggregate_dynamic_validation.py"
)


def load_aggregator():
    spec = importlib.util.spec_from_file_location("dynamic_validation_aggregator", AGGREGATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {AGGREGATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AGGREGATOR = load_aggregator()


class DynamicValidationAggregatorTests(unittest.TestCase):
    def result(self, case_id: str = "case-1", **overrides: object) -> dict:
        record: dict[str, object] = {
            "case_id": case_id,
            "target": "example/app",
            "slug": "example__app",
            "finding_id": "FIND-1",
            "probe_id": "PROBE-1",
            "status": "observed_growth_not_confirmed",
            "verdict": "not_confirmed",
            "evidence_level": "growth_observed",
            "resource_dimension": "memory",
            "default_deployment": {
                "classification": "exact_default",
                "is_default": True,
                "source": "official_docker_image",
                "image_or_version": "example/app:1",
                "commands": [],
                "config_changes": [],
                "non_default_reason": None,
            },
            "reachability": {
                "attacker_model": "anonymous",
                "entry": "POST /parse",
                "auth_required": False,
                "account_used": None,
                "network_exposure": "external_http_default",
                "required_roles": [],
            },
            "data_preparation": {
                "required": False,
                "steps": [],
                "seed_data": [],
                "low_privilege_account": None,
                "default_credentials_used": False,
            },
            "trigger": {
                "request_shape": "POST /parse",
                "parameters": {},
                "loop_variable": "body_size",
                "request_count": 3,
                "wire_bytes": 300,
                "decoded_bytes": 3000,
                "concurrency": 1,
                "duration_seconds": 2,
                "bandwidth_notes": None,
            },
            "resource_observation": {
                "metric": "heap",
                "baseline": 10,
                "ramp_levels": [10, 20, 30],
                "peak": 30,
                "post_wait": 12,
                "growth_slope": 10,
                "cleanup_rate": 9,
                "failure_signal": "none",
                "log_paths": [],
                "evidence_paths": [],
            },
            "utilization_conditions": {
                "summary": "Default anonymous endpoint; growth observed below the safety cap.",
                "requires_default_exposure": True,
                "requires_low_privilege_account": False,
                "requires_admin": False,
                "requires_config_change": False,
                "requires_optional_component": False,
                "requires_seed_data": False,
                "limits_or_mitigations": [],
                "not_affected_when": [],
            },
            "safety": {
                "request_cap": 10,
                "time_cap_seconds": 30,
                "heap_or_container_limit": "512m",
                "termination_reason": "request_cap",
                "failure_stop_hit": False,
                "safety_cap_hit": True,
                "cleanup_done": True,
            },
            "rounds": [
                {
                    "round": 1,
                    "hypothesis": "The request controls retained parser growth.",
                    "preflight_passed": True,
                    "result": "growth",
                }
            ],
            "static_traceability": {
                "static_result_file": "static/findings.jsonl",
                "source": "request body",
                "sink": "parser objects",
                "driver": "body size",
                "missing_static_evidence": [],
            },
            "notes": [],
        }
        record.update(overrides)
        return record

    def write_case(self, root: Path, record: dict | None, case_id: str = "case-1") -> Path:
        case_dir = root / "cases" / case_id
        case_dir.mkdir(parents=True)
        if record is not None:
            (case_dir / "result.json").write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
        return case_dir

    def aggregate(self, root: Path) -> tuple[int, dict, list[dict]]:
        code = AGGREGATOR.aggregate(root)
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        rejected = [
            json.loads(line)
            for line in (root / "blocked_or_rejected.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        return code, summary, rejected

    def test_case_directory_without_result_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_case(root, None)

            code, summary, rejected = self.aggregate(root)

            self.assertEqual(1, code)
            self.assertEqual(1, len(summary["result_errors"]))
            self.assertIn("missing", summary["result_errors"][0]["error"])
            self.assertEqual("case-1", rejected[0]["case_id"])

    def test_worker_verdict_conflict_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_case(root, self.result(verdict="confirmed"))

            code, summary, _ = self.aggregate(root)

            self.assertEqual(1, code)
            self.assertIn("verdict", summary["result_errors"][0]["error"])

    def test_probe_semantics_failed_maps_to_not_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = self.result(
                status="probe_semantics_failed",
                verdict="not_confirmed",
                evidence_level="deployment_reachable",
            )
            self.write_case(root, record)

            code, summary, rejected = self.aggregate(root)

            self.assertEqual(0, code)
            self.assertEqual({"not_confirmed": 1}, summary["verdict_counts"])
            self.assertEqual("not_confirmed", rejected[0]["verdict"])

    def test_confirmed_status_on_behavior_changing_deployment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deployment = dict(self.result()["default_deployment"])
            deployment.update(
                classification="default_with_behavior_change",
                is_default=False,
                non_default_reason="disabled guard",
            )
            record = self.result(
                status="confirmed_oom",
                verdict="confirmed",
                evidence_level="target_resource_failure",
                default_deployment=deployment,
            )
            self.write_case(root, record)

            code, summary, _ = self.aggregate(root)

            self.assertEqual(1, code)
            self.assertIn("deployment", summary["result_errors"][0]["error"])

    def test_more_than_three_rounds_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rounds = [
                {
                    "round": number,
                    "hypothesis": f"distinct hypothesis {number}",
                    "preflight_passed": True,
                    "result": "no_growth",
                }
                for number in range(1, 5)
            ]
            self.write_case(root, self.result(rounds=rounds))

            code, summary, _ = self.aggregate(root)

            self.assertEqual(1, code)
            self.assertIn("three", summary["result_errors"][0]["error"])

    def test_missing_and_escaping_evidence_paths_are_rejected(self) -> None:
        for evidence_path in ("evidence/missing.log", "../outside.log"):
            with self.subTest(evidence_path=evidence_path), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                resource = dict(self.result()["resource_observation"])
                resource["evidence_paths"] = [evidence_path]
                self.write_case(root, self.result(resource_observation=resource))

                code, summary, _ = self.aggregate(root)

                self.assertEqual(1, code)
                self.assertIn("evidence", summary["result_errors"][0]["error"])

    def test_legacy_stop_condition_requires_split_stop_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safety = dict(self.result()["safety"])
            safety.pop("failure_stop_hit")
            safety.pop("safety_cap_hit")
            safety["stop_condition_hit"] = True
            self.write_case(root, self.result(safety=safety))

            code, summary, _ = self.aggregate(root)

            self.assertEqual(1, code)
            self.assertIn("failure_stop_hit", summary["result_errors"][0]["error"])
            self.assertIn("safety_cap_hit", summary["result_errors"][0]["error"])

    def test_confirmed_status_requires_failure_round_and_failure_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = self.result(
                status="confirmed_resource_exhaustion",
                verdict="confirmed",
                evidence_level="target_resource_failure",
            )
            self.write_case(root, record)

            code, summary, _ = self.aggregate(root)

            self.assertEqual(1, code)
            error = summary["result_errors"][0]["error"]
            self.assertIn("failure round", error)
            self.assertIn("confirmed_failure", error)

    def test_nonfailure_status_rejects_failure_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rounds = [
                {
                    "round": 1,
                    "hypothesis": "The request can exhaust the target heap.",
                    "preflight_passed": True,
                    "result": "failure",
                }
            ]
            self.write_case(root, self.result(rounds=rounds))

            code, summary, _ = self.aggregate(root)

            self.assertEqual(1, code)
            self.assertIn("failure round", summary["result_errors"][0]["error"])


class SkillTextContractTests(unittest.TestCase):
    def read_skill(self, name: str) -> str:
        return (CODEX_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")

    def test_all_skills_use_current_model_aliases(self) -> None:
        for name in (
            "java-web-dos-hunter",
            "java-web-dos-batch-hunter",
            "java-web-dos-dynamic-validator",
        ):
            with self.subTest(skill=name):
                text = self.read_skill(name)
                self.assertIn("claude-haiku-4-5", text)
                self.assertNotIn("claude-haiku-4-5-20251001", text)
                self.assertIn("claude-sonnet-5", text)
                self.assertIn("claude-opus-4-8", text)

    def test_dynamic_skill_requires_semantic_preflight_and_three_round_reflection(self) -> None:
        text = self.read_skill("java-web-dos-dynamic-validator")

        self.assertIn("Semantic Preflight", text)
        self.assertIn("Round 1", text)
        self.assertIn("Round 2", text)
        self.assertIn("Round 3", text)
        self.assertIn("different falsifiable hypothesis", text)
        self.assertIn("observed_growth_not_confirmed", text)
        self.assertIn("no_growth", text)
        self.assertNotIn("`not_reproduced`", text)

    def test_dynamic_skill_separates_environment_trigger_poc_and_controller_roles(self) -> None:
        text = self.read_skill("java-web-dos-dynamic-validator")

        self.assertIn("Environment Worker Prompt", text)
        self.assertIn("Trigger Worker Prompt", text)
        self.assertIn("PoC Engineer Prompt", text)
        self.assertIn("Opus Reflection Controller Prompt", text)
        self.assertIn("complex_environment_failure", text)
        self.assertIn("poc_revision_required", text)


if __name__ == "__main__":
    unittest.main()
