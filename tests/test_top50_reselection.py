from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dosweb.errors import AnalyzerError
from dosweb.top50.contracts import (
    read_json_strict,
    read_jsonl_strict,
    validate_reserve_candidates,
    validate_reviewed_candidates,
    validate_selected_targets,
    write_jsonl_atomically,
)
from dosweb.top50.selection import (
    audit_selection,
    capture_snapshot,
    choose_replacement,
    render_intel_json,
    render_markdown,
    select_targets,
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


def reviewed(slug: str) -> dict[str, object]:
    official = {
        "evidence_id": "e-1",
        "source_kind": "repository_readme",
        "url": "https://github.com/o/r/blob/a/README.md",
        "claim": "default public HTTP service",
        "official": True,
    }
    return {
        "candidate_id": f"candidate:{slug.casefold()}",
        "slug": slug,
        "slug_normalized": slug.casefold(),
        "selection_commit": {"default_branch": "main", "commit_sha": "a" * 40},
        "deployment": {"protocol": "http", "required_external_dependencies": ["postgresql"]},
        "evidence": [official],
        "hard_gate_evidence_ids": ["e-1"],
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
        "build_plan": {"strategy": "maven", "expected_coverage_status": "complete"},
        "review_outcome": "eligible",
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

    def test_jsonl_rejects_duplicate_keys_at_any_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            path.write_text('{"outer":{"x":1,"x":2}}\n', encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "records")
            self.assertEqual("TOP50_INVALID_JSON", raised.exception.code)

    def test_jsonl_preserves_unicode_line_separators_and_writer_round_trips_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            records = [{"text": "first second"}, {"text": "third fourth"}]
            write_jsonl_atomically(path, records)
            self.assertEqual(records, read_jsonl_strict(path, "records"))
            self.assertEqual(2, len(path.read_bytes().splitlines()))

    def test_jsonl_converts_recursion_and_input_os_errors_to_analyzer_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            path.write_text("{}\n", encoding="utf-8")
            with mock.patch("dosweb.top50.contracts._reject_nonfinite", side_effect=RecursionError):
                with self.assertRaises(AnalyzerError) as raised:
                    read_jsonl_strict(path, "records")
            self.assertEqual("TOP50_INVALID_JSON", raised.exception.code)

            with mock.patch("dosweb.top50.contracts.json.loads", side_effect=RecursionError):
                with self.assertRaises(AnalyzerError) as raised:
                    read_jsonl_strict(path, "records")
            self.assertEqual("TOP50_INVALID_JSON", raised.exception.code)

            with mock.patch.object(Path, "read_text", side_effect=OSError("unavailable")):
                with self.assertRaises(AnalyzerError) as raised:
                    read_jsonl_strict(path, "records")
            self.assertEqual("TOP50_INVALID_JSONL", raised.exception.code)
            self.assertIn(str(path), raised.exception.message)

    def test_selected_targets_requires_exactly_fifty(self) -> None:
        document = {"targets": [target(f"owner/repo-{index}") for index in range(49)], "reserve_pool": []}
        with self.assertRaises(AnalyzerError) as raised:
            validate_selected_targets(document, set(), set())
        self.assertEqual("TOP50_CONSTRAINT_VIOLATION", raised.exception.code)

    def test_selected_targets_requires_mapping_root_and_commit_sha(self) -> None:
        with self.assertRaises(AnalyzerError) as raised:
            validate_selected_targets([], set(), set())  # type: ignore[arg-type]
        self.assertEqual("TOP50_INVALID_FIELD", raised.exception.code)

        targets = [target(f"owner/repo-{index}") for index in range(50)]
        targets[0]["commit_sha"] = "not-a-sha"
        with self.assertRaisesRegex(AnalyzerError, "commit_sha"):
            validate_selected_targets({"targets": targets}, set(), set())

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

    def test_reviewed_candidates_rejects_legacy_only_commit_shape(self) -> None:
        legacy = reviewed("Owner/Repo")
        legacy["commit_sha"] = legacy.pop("selection_commit")["commit_sha"]  # type: ignore[index]
        with self.assertRaisesRegex(AnalyzerError, "selection_commit"):
            validate_reviewed_candidates([legacy])

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
            with mock.patch("dosweb.top50.contracts.os.fsync", wraps=__import__("os").fsync) as fsync:
                write_jsonl_atomically(path, [{"slug": "owner/repo"}])
            self.assertEqual('{"slug": "owner/repo"}\n', path.read_text(encoding="utf-8"))
            self.assertEqual("keep", stale_temp.read_text(encoding="utf-8"))
            self.assertEqual([stale_temp], list(path.parent.glob(f".{path.name}.*")))
            self.assertGreaterEqual(fsync.call_count, 2)

    def test_jsonl_writer_rejects_non_mapping_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AnalyzerError) as raised:
                write_jsonl_atomically(Path(tmp) / "records.jsonl", [["not", "a record"]])  # type: ignore[list-item]
            self.assertEqual("TOP50_RECORD_NOT_OBJECT", raised.exception.code)


class ReviewContractTests(unittest.TestCase):
    def test_review_recomputes_score_and_thresholds(self) -> None:
        item = reviewed("Owner/Repo")
        item["score"]["total"] = 99  # type: ignore[index]
        with self.assertRaisesRegex(AnalyzerError, "score total"):
            validate_reviewed_candidates([item])

    def test_review_rejects_dependency_count_above_three(self) -> None:
        item = reviewed("Owner/Repo")
        item["deployment"]["required_external_dependencies"] = ["a", "b", "c", "d"]  # type: ignore[index]
        with self.assertRaisesRegex(AnalyzerError, "zero to three"):
            validate_reviewed_candidates([item])

    def test_review_rejects_third_party_only_hard_gate_evidence(self) -> None:
        item = reviewed("Owner/Repo")
        item["evidence"][0]["source_kind"] = "third_party_discovery"  # type: ignore[index]
        item["evidence"][0]["official"] = False  # type: ignore[index]
        with self.assertRaisesRegex(AnalyzerError, "official evidence"):
            validate_reviewed_candidates([item])

    def test_review_accepts_canonical_selection_commit_and_legacy_commit_sha_when_matching(self) -> None:
        item = reviewed("Owner/Repo")
        item["commit_sha"] = "a" * 40
        self.assertEqual({item["candidate_id"]: item}, validate_reviewed_candidates([item]))

    def test_review_rejects_mismatched_selection_and_legacy_commits(self) -> None:
        item = reviewed("Owner/Repo")
        item["commit_sha"] = "b" * 40
        with self.assertRaisesRegex(AnalyzerError, "commit_sha"):
            validate_reviewed_candidates([item])

    def test_reserve_rejects_fewer_than_fifteen_contiguous_records(self) -> None:
        item = reviewed("Owner/Repo")
        reviewed_by_id = validate_reviewed_candidates([item])
        reserves = [
            {"candidate_id": item["candidate_id"], "slug": item["slug"], "reserve_rank": rank, "eligible_for_replacement": True}
            for rank in range(1, 15)
        ]
        with self.assertRaisesRegex(AnalyzerError, "at least 15"):
            validate_reserve_candidates(reserves, reviewed_by_id, set())

    def test_reserve_rejects_reviewed_candidate_without_eligible_outcome(self) -> None:
        item = reviewed("Owner/Repo")
        item["review_outcome"] = "ineligible"
        reviewed_by_id = validate_reviewed_candidates([item])
        reserves = [
            {"candidate_id": item["candidate_id"], "slug": item["slug"], "reserve_rank": rank, "eligible_for_replacement": True}
            for rank in range(1, 16)
        ]
        with self.assertRaisesRegex(AnalyzerError, "eligible candidate"):
            validate_reserve_candidates(reserves, reviewed_by_id, set())


class SelectionTests(unittest.TestCase):
    def _reviewed_pool(self, count: int = 65) -> dict[str, dict[str, object]]:
        records = [reviewed(f"Owner/Repo-{index:02d}") for index in range(count)]
        return validate_reviewed_candidates(records)

    def _reserves(self, reviewed_by_id: dict[str, dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "candidate_id": f"candidate:owner/repo-{index:02d}",
                "slug": f"Owner/Repo-{index:02d}",
                "reserve_rank": index - 49,
                "eligible_for_replacement": True,
            }
            for index in range(50, 65)
        ]

    def test_cli_help_runs_from_repository_root(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/reselect_java_web_dos_top50.py", "--help"],
            cwd=repository_root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("validate-review", result.stdout)
        self.assertIn("audit", result.stdout)

    def test_render_cli_rejects_selected_document_without_exactly_fifty_targets(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.json"
            old_manifest = root / "old.txt"
            initial_manifest = root / "initial.txt"
            selected.write_text(json.dumps({"targets": [target(f"owner/repo-{index}") for index in range(49)]}), encoding="utf-8")
            old_manifest.write_text("owner/old\n", encoding="utf-8")
            initial_manifest.write_text("owner/initial\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/reselect_java_web_dos_top50.py",
                    "render",
                    "--selected",
                    str(selected),
                    "--old-manifest",
                    str(old_manifest),
                    "--initial-manifest",
                    str(initial_manifest),
                    "--markdown-output",
                    str(root / "selected.md"),
                    "--intel-output",
                    str(root / "intel.json"),
                    "--overlap-output",
                    str(root / "overlap.json"),
                ],
                cwd=repository_root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertFalse((root / "selected.md").exists())

    def test_snapshot_captures_only_initial_first_level_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            (assets / "Owner__Repo").mkdir(parents=True)
            (assets / ".temporary").mkdir()
            source_link = root / "sources"
            source_link.symlink_to(assets, target_is_directory=True)
            document = capture_snapshot(source_link, root / "dbs")
            self.assertEqual(["owner/repo"], [item["slug_normalized"] for item in document["projects"]])
            self.assertEqual(str(assets / "Owner__Repo"), document["projects"][0]["source_dir"])

    def test_snapshot_preserves_safe_name_with_double_underscore_in_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "sources"
            (source_root / "Owner__repo__extra").mkdir(parents=True)
            document = capture_snapshot(source_root, Path(tmp) / "dbs")
            self.assertEqual("owner/repo__extra", document["projects"][0]["slug_normalized"])
            self.assertEqual("Owner__repo__extra", document["projects"][0]["safe_name"])

    def test_snapshot_rejects_unsafe_source_directory_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "sources"
            (source_root / "owner__").mkdir(parents=True)
            with self.assertRaisesRegex(AnalyzerError, "owner__repository"):
                capture_snapshot(source_root, Path(tmp) / "dbs")

    def test_select_uses_snapshot_json_and_skips_ranked_old_overlap(self) -> None:
        reviewed_by_id = self._reviewed_pool(66)
        for index in range(11):
            reviewed_by_id[f"candidate:owner/repo-{index:02d}"]["selection_rank"] = index + 1
        for index in range(11, 50):
            reviewed_by_id[f"candidate:owner/repo-{index:02d}"]["selection_rank"] = index + 1
        reviewed_by_id["candidate:owner/repo-50"]["selection_rank"] = 51
        reserves = [
            {"candidate_id": f"candidate:owner/repo-{index:02d}", "slug": f"Owner/Repo-{index:02d}", "reserve_rank": index - 50, "eligible_for_replacement": True}
            for index in range(51, 66)
        ]
        document = select_targets(
            reviewed_by_id,
            reserves,
            {f"owner/repo-{index:02d}" for index in range(11)},
            set(),
        )
        self.assertNotIn("owner/repo-10", {item["slug_normalized"] for item in document["targets"]})
        self.assertIn("owner/repo-50", {item["slug_normalized"] for item in document["targets"]})

    def test_select_targets_projects_reviewed_commit_and_reserves(self) -> None:
        reviewed_by_id = self._reviewed_pool()
        document = select_targets(reviewed_by_id, self._reserves(reviewed_by_id), set(), set())
        self.assertEqual(50, len(document["targets"]))
        self.assertEqual(15, len(document["reserve_pool"]))
        self.assertEqual("a" * 40, document["targets"][0]["commit_sha"])
        self.assertEqual(
            "a" * 40,
            document["targets"][0]["reviewed_selection_commit"]["commit_sha"],
        )
        self.assertEqual("owner/repo-00", document["targets"][0]["slug_normalized"])
        self.assertEqual("owner__repo-00", document["targets"][0]["safe_name"])
        validate_selected_targets(document, set(), set())

    def test_replacement_skips_candidate_that_breaks_old_overlap(self) -> None:
        targets = [target(f"owner/repo-{index}", old=index < 10, new=index < 20) for index in range(50)]
        reserves = [target("legacy/extra", old=True), target("fresh/extra", old=False)] + [target(f"reserve/extra-{index}") for index in range(14)]
        for rank, reserve in enumerate(reserves, start=1):
            reserve["reserve_rank"] = rank
            reserve["eligible_for_replacement"] = True
            reserve["review_outcome"] = "eligible"
        document = {"targets": targets, "reserve_pool": reserves, "replacement_history": []}
        old = {item["slug_normalized"] for item in targets[:10]} | {"legacy/extra"}
        result = choose_replacement(document, "owner/repo-20", set(), old, {item["slug_normalized"] for item in targets[20:]})
        self.assertEqual("fresh/extra", result["targets"][-1]["slug_normalized"])
        self.assertEqual(
            [{"outgoing_slug": "owner/repo-20", "incoming_slug": "fresh/extra"}],
            result["replacement_history"],
        )

    def test_replacement_rejects_consuming_fifteenth_reserve(self) -> None:
        targets = [target(f"owner/repo-{index}") for index in range(50)]
        reserves = [target(f"reserve/repo-{index}") for index in range(15)]
        for rank, reserve in enumerate(reserves, start=1):
            reserve.update({"reserve_rank": rank, "eligible_for_replacement": True, "review_outcome": "eligible"})
        with self.assertRaisesRegex(AnalyzerError, "reserve"):
            choose_replacement({"targets": targets, "reserve_pool": reserves}, "owner/repo-0", set(), set(), set())

    def test_strict_json_object_and_status_readers_reject_malformed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = root / "document.json"
            for content, code in (('{"x": 1, "x": 2}', "TOP50_INVALID_JSON"), ('{"x": NaN}', "TOP50_INVALID_JSON"), ("[]", "TOP50_RECORD_NOT_OBJECT")):
                with self.subTest(content=content):
                    document.write_text(content, encoding="utf-8")
                    with self.assertRaises(AnalyzerError) as raised:
                        read_json_strict(document, "document")
                    self.assertEqual(code, raised.exception.code)
            document.write_bytes(b'{"x":"\xff"}')
            with self.assertRaises(AnalyzerError) as raised:
                read_json_strict(document, "document")
            self.assertEqual("TOP50_INVALID_JSON", raised.exception.code)
            with mock.patch.object(Path, "read_text", side_effect=OSError("unavailable")):
                with self.assertRaises(AnalyzerError) as raised:
                    read_json_strict(document, "document")
            self.assertEqual("TOP50_INVALID_JSON", raised.exception.code)
            statuses = root / "status.jsonl"
            statuses.write_text('{"slug":"owner/repo"}\n\n', encoding="utf-8")
            with self.assertRaisesRegex(AnalyzerError, "blank line"):
                read_jsonl_strict(statuses, "status events")

    def test_rendering_derives_markdown_and_intel_from_same_selected_targets(self) -> None:
        reviewed_by_id = self._reviewed_pool()
        document = select_targets(reviewed_by_id, self._reserves(reviewed_by_id), set(), set())
        markdown = render_markdown(document)
        intel = render_intel_json(document)
        self.assertIn("`owner/repo-00`", markdown)
        self.assertEqual(
            [item["slug_normalized"] for item in document["targets"]],
            [item["slug_normalized"] for item in intel["targets"]],
        )

    def test_snapshot_cli_rejects_asset_file_output(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "sources"
            db_root = root / "dbs"
            project = source_root / "owner__repo"
            project.mkdir(parents=True)
            pom = project / "pom.xml"
            pom.write_text("<project />", encoding="utf-8")
            marker = db_root / "owner__repo-db" / "codeql-database.yml"
            marker.parent.mkdir(parents=True)
            marker.write_text("name: test\n", encoding="utf-8")
            for output, original in ((pom, "<project />"), (marker, "name: test\n")):
                with self.subTest(output=output):
                    result = subprocess.run(
                        [sys.executable, "scripts/reselect_java_web_dos_top50.py", "snapshot", "--source-root", str(source_root), "--db-root", str(db_root), "--output", str(output)],
                        cwd=repository_root, text=True, capture_output=True, check=False,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual(original, output.read_text(encoding="utf-8"))

    def test_render_cli_rejects_colliding_outputs(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        reviewed_by_id = self._reviewed_pool()
        document = select_targets(reviewed_by_id, self._reserves(reviewed_by_id), set(), set())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.json"
            old_manifest = root / "old.txt"
            initial_manifest = root / "initial.txt"
            selected.write_text(json.dumps(document), encoding="utf-8")
            old_manifest.write_text("owner/old\n", encoding="utf-8")
            initial_manifest.write_text("owner/initial\n", encoding="utf-8")
            output = root / "shared-output"
            result = subprocess.run(
                [
                    sys.executable, "scripts/reselect_java_web_dos_top50.py", "render",
                    "--selected", str(selected), "--old-manifest", str(old_manifest),
                    "--initial-manifest", str(initial_manifest), "--markdown-output", str(output),
                    "--intel-output", str(output), "--overlap-output", str(root / "overlap.json"),
                ], cwd=repository_root, text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())

    def test_audit_accepts_uppercase_commit_sha_and_rejects_non_object_intel_target(self) -> None:
        reviewed_by_id = self._reviewed_pool()
        document = select_targets(reviewed_by_id, self._reserves(reviewed_by_id), set(), set())
        for item in document["targets"]:
            item["commit_sha"] = "A" * 40
        intel = render_intel_json(document)
        intel["targets"].append("unexpected")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "sources"
            db_root = root / "dbs"
            for item in document["targets"]:
                safe_name = item["safe_name"]
                (source_root / safe_name).mkdir(parents=True)
                database = db_root / f"{safe_name}-db"
                database.mkdir(parents=True)
                (database / "codeql-database.yml").write_text("name: test\n", encoding="utf-8")
                (database / "db-java").mkdir()
                (database / "db-java" / "default").write_text("test", encoding="utf-8")
            statuses = [
                event
                for item in document["targets"]
                for event in (
                    {"slug": item["slug"], "status": "source_ready", "stage": "source", "commit": "a" * 40},
                    {"slug": item["slug"], "status": "success", "verification_status": "verified", "compilation_unit_count": 1, "coverage_status": "complete"},
                )
            ]
            with mock.patch("dosweb.top50.selection._git_head", return_value="a" * 40):
                with self.assertRaisesRegex(AnalyzerError, "intel JSON"):
                    audit_selection(document, set(), set(), source_root, db_root, statuses, [item["slug"] for item in document["targets"]], intel)

    def test_audit_requires_verified_terminal_database_status(self) -> None:
        reviewed_by_id = self._reviewed_pool()
        document = select_targets(reviewed_by_id, self._reserves(reviewed_by_id), set(), set())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "sources"
            db_root = root / "dbs"
            for item in document["targets"]:
                safe_name = item["safe_name"]
                (source_root / safe_name).mkdir(parents=True)
                database = db_root / f"{safe_name}-db"
                (database / "db-java").mkdir(parents=True)
                (database / "codeql-database.yml").write_text("name: test\n", encoding="utf-8")
                (database / "db-java" / "default").write_text("test", encoding="utf-8")
            statuses = [
                event
                for item in document["targets"]
                for event in (
                    {"slug": item["slug"], "status": "source_ready", "stage": "source", "commit": "a" * 40},
                    {"slug": item["slug"], "status": "success", "verification_status": "unverified", "compilation_unit_count": 1, "coverage_status": "complete"},
                )
            ]
            with mock.patch("dosweb.top50.selection._git_head", return_value="a" * 40):
                with self.assertRaisesRegex(AnalyzerError, "verified"):
                    audit_selection(document, set(), set(), source_root, db_root, statuses)

    def test_audit_rejects_partial_database_status(self) -> None:
        reviewed_by_id = self._reviewed_pool()
        document = select_targets(reviewed_by_id, self._reserves(reviewed_by_id), set(), set())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "sources"
            db_root = root / "dbs"
            for item in document["targets"]:
                safe_name = item["safe_name"]
                (source_root / safe_name).mkdir(parents=True)
                database = db_root / f"{safe_name}-db"
                database.mkdir(parents=True)
                (database / "codeql-database.yml").write_text("name: test\n", encoding="utf-8")
            statuses = [
                {
                    "slug": item["slug"],
                    "status": "success",
                    "database_structure": "valid",
                    "coverage_status": "capture_completed",
                }
                for item in document["targets"][:-1]
            ]
            with self.assertRaisesRegex(AnalyzerError, "partial"):
                audit_selection(document, set(), set(), source_root, db_root, statuses)
