#!/usr/bin/env python3
"""Regression tests for the active P0 static-verdict migration."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_STATIC_VERDICTS = {
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
}
RETIRED_STATIC_VERDICT = "static_" + "safe"


def load_script(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "scripts" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AGGREGATE = load_script("verdict_migration_aggregate", "aggregate_java_web_dos_batch.py")
PREPARE = load_script("verdict_migration_prepare", "prepare_dynamic_validation_output.py")


class VerdictMigrationTests(unittest.TestCase):
    def test_active_scripts_expose_exact_static_verdict_vocabulary(self) -> None:
        self.assertEqual(EXPECTED_STATIC_VERDICTS, AGGREGATE.STATIC_VERDICTS)
        self.assertEqual(EXPECTED_STATIC_VERDICTS, PREPARE.STATIC_VERDICTS)

    def test_dynamic_scaffold_preserves_static_verdict_only_as_traceability(self) -> None:
        for static_verdict in sorted(EXPECTED_STATIC_VERDICTS):
            with self.subTest(verdict=static_verdict), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                candidates = root / "candidates.jsonl"
                candidates.write_text(
                    json.dumps(
                        {
                            "target": "Example App",
                            "slug": "example/app",
                            "finding_id": "FIND-001",
                            "probe_id": "PROBE-GET",
                            "verdict": static_verdict,
                            "request_shape": "GET /items",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                output = root / "output"

                PREPARE.prepare(candidates, output)

                manifest = json.loads((output / "manifest.normalized.jsonl").read_text(encoding="utf-8"))
                case_id = manifest["case_id"]
                result = json.loads((output / "cases" / case_id / "result.json").read_text(encoding="utf-8"))
                status = json.loads((output / "validation_status.jsonl").read_text(encoding="utf-8"))
                self.assertEqual(static_verdict, result["static_traceability"]["static_verdict"])
                self.assertEqual("paused", result["status"])
                self.assertEqual("blocked", result["verdict"])
                self.assertEqual("paused", status["status"])
                self.assertEqual("blocked", status["verdict"])
                self.assertNotIn("static_verdict", status)

    def test_active_code_and_primary_docs_have_no_retired_ordinary_verdict(self) -> None:
        targets = [REPO_ROOT / "README.md", REPO_ROOT / "AGENTS.md"]
        targets.extend(sorted((REPO_ROOT / "dosweb").rglob("*.py")))
        targets.extend(sorted((REPO_ROOT / "scripts").glob("*.py")))
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for path in targets
            if RETIRED_STATIC_VERDICT in path.read_text(encoding="utf-8")
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
