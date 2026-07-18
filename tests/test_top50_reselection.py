from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dosweb.errors import AnalyzerError
from dosweb.top50.contracts import (
    read_jsonl_strict,
    validate_reviewed_candidates,
    validate_selected_targets,
    write_jsonl_atomically,
)


def target(slug: str, *, old: bool = False, new: bool = True) -> dict[str, object]:
    return {
        "slug": slug,
        "slug_normalized": slug.casefold(),
        "commit_sha": "a" * 40,
        "in_old_top50": old,
        "in_initial_snapshot": not new,
        "score": {
            "default_public_entry": 20,
            "dos_relevance": 24,
            "low_privilege_reachability": 10,
            "impact_usage": 10,
            "codeql_feasibility": 8,
            "maintenance_evidence": 4,
            "total": 76,
        },
        "hard_gates": {"passed": True},
        "negative_review": {"outcome": "passed"},
    }


class StrictArtifactTests(unittest.TestCase):
    def test_jsonl_rejects_blank_non_object_and_nonfinite_records(self) -> None:
        for content, code in (
            ("\n", "TOP50_INVALID_JSONL"),
            ("[]\n", "TOP50_RECORD_NOT_OBJECT"),
            ('{"x": NaN}\n', "TOP50_INVALID_JSON"),
            ('{"nested": [1e9999]}\n', "TOP50_INVALID_JSON"),
        ):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "records.jsonl"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(AnalyzerError) as raised:
                    read_jsonl_strict(path, "records")
                self.assertEqual(code, raised.exception.code)

    def test_jsonl_converts_invalid_utf8_to_analyzer_error_with_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            path.write_bytes(b'{"x":"\xff"}\n')
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "records")
            self.assertEqual("TOP50_INVALID_JSON", raised.exception.code)
            self.assertIn(str(path), raised.exception.message)

    def test_selected_targets_requires_exactly_fifty(self) -> None:
        document = {"targets": [target(f"owner/repo-{index}") for index in range(49)], "reserve_pool": []}
        with self.assertRaises(AnalyzerError) as raised:
            validate_selected_targets(document, set(), set())
        self.assertEqual("TOP50_CONSTRAINT_VIOLATION", raised.exception.code)

    def test_selected_targets_rejects_eleven_old_overlaps(self) -> None:
        targets = [target(f"owner/repo-{index}", old=index < 11) for index in range(50)]
        old = {item["slug_normalized"] for item in targets[:11]}
        with self.assertRaisesRegex(AnalyzerError, "old Top-50 overlap"):
            validate_selected_targets({"targets": targets, "reserve_pool": []}, old, set())

    def test_selected_targets_rejects_fewer_than_seventeen_new(self) -> None:
        targets = [target(f"owner/repo-{index}", new=index < 16) for index in range(50)]
        initial = {item["slug_normalized"] for item in targets[16:]}
        with self.assertRaisesRegex(AnalyzerError, "at least 17"):
            validate_selected_targets({"targets": targets, "reserve_pool": []}, set(), initial)

    def test_reviewed_candidates_validates_identity_and_shape(self) -> None:
        validate_reviewed_candidates([target("Owner/Repo")])
        incomplete = target("owner/repo")
        incomplete.pop("commit_sha")
        with self.assertRaisesRegex(AnalyzerError, "commit_sha"):
            validate_reviewed_candidates([incomplete])

    def test_selected_targets_rejects_spoofed_normalized_slug(self) -> None:
        targets = [target(f"owner/repo-{index}") for index in range(50)]
        targets[0]["slug_normalized"] = "owner/different-repo"
        with self.assertRaisesRegex(AnalyzerError, "slug_normalized"):
            validate_selected_targets({"targets": targets, "reserve_pool": []}, set(), set())

    def test_selected_targets_normalizes_comparison_sets(self) -> None:
        targets = [target(f"owner/repo-{index}") for index in range(50)]
        old = {str(item["slug_normalized"]).upper() for item in targets[:11]}
        with self.assertRaisesRegex(AnalyzerError, "old Top-50 overlap"):
            validate_selected_targets({"targets": targets, "reserve_pool": []}, old, set())

        initial = {str(item["slug_normalized"]).upper() for item in targets[16:]}
        with self.assertRaisesRegex(AnalyzerError, "at least 17"):
            validate_selected_targets({"targets": targets, "reserve_pool": []}, set(), initial)

    def test_jsonl_writer_uses_unique_temporary_file_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            stale_temp = path.with_name(f".{path.name}.tmp")
            stale_temp.write_text("keep", encoding="utf-8")
            write_jsonl_atomically(path, [{"slug": "owner/repo"}])
            self.assertEqual('{"slug": "owner/repo"}\n', path.read_text(encoding="utf-8"))
            self.assertEqual("keep", stale_temp.read_text(encoding="utf-8"))
            self.assertEqual([stale_temp], list(path.parent.glob(f".{path.name}.*")))
