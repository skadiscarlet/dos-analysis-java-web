import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dosweb.benchmark.candidates import extract_candidates_from_target


class BenchmarkCandidateTests(unittest.TestCase):
    def test_static_finding_joins_entry_growth_certificate_and_flow(self):
        rows = {
            "entry_facts": [
                {
                    "entry_id": "entry:e",
                    "route_or_event": "POST /api/items/{id}",
                    "protocol": "http",
                    "handler": {"callable": "Controller.create", "file": "A.java", "start_line": 1},
                }
            ],
            "growth_candidates": [
                {
                    "growth_id": "growth:g",
                    "site": {"file": "A.java", "start_line": 2},
                }
            ],
            "flow_proofs": [
                {
                    "path_id": "flow:p",
                    "entry_id": "entry:e",
                    "growth_id": "growth:g",
                }
            ],
            "lifecycle_certificates": [
                {
                    "certificate_id": "certificate:c",
                    "entry_id": "entry:e",
                    "growth_id": "growth:g",
                    "path_ids": ["flow:p"],
                    "resource_point": {"dimension": "bytes", "receiver": "body"},
                }
            ],
            "static_findings": [
                {
                    "finding_id": "finding:f",
                    "certificate_id": "certificate:c",
                    "entry_id": "entry:e",
                    "growth_id": "growth:g",
                    "verdict": "static_vulnerable",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "run.json").write_text(json.dumps({"status": "completed"}))
            paths = {f"{name}.jsonl": target / f"{name}.jsonl" for name in rows}
            for path in paths.values():
                path.write_text("{}\n")
            with mock.patch("dosweb.benchmark.candidates._artifact_paths", return_value=paths), mock.patch(
                "dosweb.benchmark.candidates.read_jsonl_strict",
                side_effect=lambda path, schema: rows[schema],
            ), mock.patch("dosweb.benchmark.candidates.validate_records"):
                candidates, error = extract_candidates_from_target(
                    target,
                    target_id="target:t",
                    repository="owner/repo",
                )
        self.assertIsNone(error)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["entry"]["entry_id"], "entry:e")
        self.assertEqual(candidates[0]["growth"]["growth_id"], "growth:g")
        self.assertEqual(candidates[0]["flows"][0]["path_id"], "flow:p")
        self.assertEqual(candidates[0]["certificate"]["certificate_id"], "certificate:c")
