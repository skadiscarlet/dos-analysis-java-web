#!/usr/bin/env python3
"""Regression tests for opt-in dynamic-validation scaffolding helpers."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "scripts" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREPARE = load_script("prepare_dynamic_validation_output", "prepare_dynamic_validation_output.py")
SYNC = load_script("sync_dynamic_validation_status", "sync_dynamic_validation_status.py")


class PrepareDynamicValidationOutputTests(unittest.TestCase):
    def write_candidates(self, root: Path, rows: list[dict]) -> Path:
        path = root / "candidates.jsonl"
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
        )
        return path

    def candidate(self, **overrides: object) -> dict:
        record: dict[str, object] = {
            "target": "Example App",
            "slug": "example/app",
            "finding_id": "FIND-001",
            "probe_id": "PROBE-GET",
            "verdict": "static_vulnerable",
            "request_shape": "GET /items",
        }
        record.update(overrides)
        return record

    def test_case_id_contains_finding_probe_and_stable_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = self.write_candidates(root, [self.candidate()])
            output = root / "output"

            PREPARE.prepare(candidates, output)

            manifest = json.loads((output / "manifest.normalized.jsonl").read_text(encoding="utf-8"))
            case_id = manifest["case_id"]
            self.assertIn("FIND-001", case_id)
            self.assertIn("PROBE-GET", case_id)
            self.assertRegex(case_id, r"^example_app-FIND-001-PROBE-GET-[0-9a-f]{20}$")
            self.assertEqual("paused", manifest["status"])
            self.assertEqual(str(output / "cases" / case_id), manifest["case_dir"])
            initial_status = json.loads((output / "validation_status.jsonl").read_text(encoding="utf-8"))
            self.assertEqual("blocked", initial_status["verdict"])
            self.assertEqual("none", initial_status["failure_signal"])
            placeholder = json.loads((output / "cases" / case_id / "result.json").read_text(encoding="utf-8"))
            self.assertEqual("blocked", placeholder["verdict"])
            self.assertIn("不能视为动态确认", placeholder["utilization_conditions"]["summary"])
            plan = (output / "DYNAMIC_VALIDATION_PLAN.md").read_text(encoding="utf-8")
            self.assertIn("not part of the static analysis pipeline", plan)
            self.assertIn("does not execute probes", plan)

    def test_identical_candidates_are_rejected_with_both_source_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = self.write_candidates(root, [self.candidate(), self.candidate()])

            with self.assertRaisesRegex(ValueError, r"candidates\.jsonl:1.*candidates\.jsonl:2.*duplicate case_id"):
                PREPARE.prepare(candidates, root / "output")

    def test_default_rejects_nonempty_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = self.write_candidates(root, [self.candidate()])
            output = root / "output"
            output.mkdir()
            (output / "unrelated.txt").write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"output.*non-empty.*unrelated\.txt"):
                PREPARE.prepare(candidates, output)

    def test_force_refuses_completed_result_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = self.write_candidates(root, [self.candidate()])
            output = root / "output"
            PREPARE.prepare(candidates, output)
            manifest = json.loads((output / "manifest.normalized.jsonl").read_text(encoding="utf-8"))
            result_path = output / "cases" / manifest["case_id"] / "result.json"
            completed = json.loads(result_path.read_text(encoding="utf-8"))
            completed["status"] = "completed"
            completed["verdict"] = "confirmed"
            result_path.write_text(json.dumps(completed), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"result\.json.*completed evidence.*--force"):
                PREPARE.prepare(candidates, output, force=True)

            self.assertEqual("completed", json.loads(result_path.read_text(encoding="utf-8"))["status"])

    def test_force_only_recreates_exact_paused_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = self.write_candidates(root, [self.candidate()])
            output = root / "output"
            PREPARE.prepare(candidates, output)

            PREPARE.prepare(candidates, output, force=True)

            self.assertTrue((output / "validation_status.jsonl").exists())

    def test_invalid_json_reports_input_path_and_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = root / "candidates.jsonl"
            candidates.write_text('{"target":"ok"}\nnot-json\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"candidates\.jsonl:2: invalid JSON"):
                PREPARE.prepare(candidates, root / "output")

    def test_rejects_nonstandard_json_and_wrong_identity_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = root / "candidates.jsonl"
            candidates.write_text('{"target":"ok","safety_limit":NaN}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"NaN.*not allowed"):
                PREPARE.prepare(candidates, root / "output")
            candidates.write_text(json.dumps({"target": "ok", "slug": ["bad"]}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"slug must be a non-empty string"):
                PREPARE.prepare(candidates, root / "output")

    def test_supports_static_conclusion_and_legacy_probe_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = self.write_candidates(
                root,
                [self.candidate(probe_id=None, dynamic_probe_id="DP-1", verdict=None, static_conclusion="static_unknown")],
            )
            PREPARE.prepare(candidates, root / "output")
            manifest = json.loads((root / "output" / "manifest.normalized.jsonl").read_text(encoding="utf-8"))
            self.assertEqual("DP-1", manifest["probe_id"])
            self.assertEqual("static_unknown", manifest["static_verdict"])


class SyncDynamicValidationStatusTests(unittest.TestCase):
    def prepare_one_case(self, root: Path) -> tuple[Path, str]:
        candidates = root / "candidates.jsonl"
        candidates.write_text(
            json.dumps(
                {
                    "target": "Example App",
                    "slug": "example/app",
                    "finding_id": "FIND-001",
                    "probe_id": "PROBE-GET",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output = root / "output"
        PREPARE.prepare(candidates, output)
        manifest = json.loads((output / "manifest.normalized.jsonl").read_text(encoding="utf-8"))
        return output, manifest["case_id"]

    def test_sync_atomically_replaces_status_from_completed_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output, case_id = self.prepare_one_case(Path(tmp))
            result_path = output / "cases" / case_id / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["status"] = "completed"
            result["verdict"] = "not_confirmed"
            result["utilization_conditions"]["summary"] = "bounded by default configuration"
            result["resource_observation"]["failure_signal"] = "none"
            result_path.write_text(json.dumps(result), encoding="utf-8")

            real_replace = SYNC.os.replace
            with mock.patch.object(SYNC.os, "replace", wraps=real_replace) as replace:
                SYNC.sync(output)

            self.assertTrue(
                any(call.args[1] == output / "validation_status.jsonl" for call in replace.call_args_list)
            )
            status = json.loads((output / "validation_status.jsonl").read_text(encoding="utf-8"))
            self.assertEqual("completed", status["status"])
            self.assertEqual("not_confirmed", status["verdict"])
            self.assertIsNone(status["failure_reason"])
            self.assertEqual("bounded by default configuration", status["utilization_conditions_summary"])

    def test_sync_rejects_result_for_a_different_case_with_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output, case_id = self.prepare_one_case(Path(tmp))
            result_path = output / "cases" / case_id / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["case_id"] = "other-case"
            result_path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"result\.json.*case_id.*other-case.*expected"):
                SYNC.sync(output)

    def test_sync_rejects_missing_result_invalid_state_and_wrong_nested_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output, case_id = self.prepare_one_case(Path(tmp))
            result_path = output / "cases" / case_id / "result.json"
            result_path.unlink()
            with self.assertRaisesRegex(ValueError, r"missing regular result file"):
                SYNC.sync(output)

        with tempfile.TemporaryDirectory() as tmp:
            output, case_id = self.prepare_one_case(Path(tmp))
            result_path = output / "cases" / case_id / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result.update({"status": "paused", "verdict": "confirmed"})
            result_path.write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"incompatible with status"):
                SYNC.sync(output)

        with tempfile.TemporaryDirectory() as tmp:
            output, case_id = self.prepare_one_case(Path(tmp))
            result_path = output / "cases" / case_id / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["resource_observation"] = []
            result_path.write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"resource_observation must be an object"):
                SYNC.sync(output)

    def test_sync_rejects_unsafe_case_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output, _ = self.prepare_one_case(Path(tmp))
            manifest_path = output / "manifest.normalized.jsonl"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["case_id"] = "../../outside"
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"invalid case_id"):
                SYNC.sync(output)


if __name__ == "__main__":
    unittest.main()
