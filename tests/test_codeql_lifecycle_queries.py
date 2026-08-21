from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from dosweb.artifacts.identifiers import file_sha256
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database
from dosweb.codeql.decoder import BOUND_COLUMNS, FLOW_COLUMNS, GUARD_COLUMNS, LIFECYCLE_COVERAGE_COLUMNS, LIFECYCLE_SUMMARY_COLUMNS, RELEASE_COLUMNS
from tests.test_codeql_entry_queries import _codeql_wrapper

_ROOT = Path(__file__).resolve().parents[1]
_RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql")
_JAVAC = shutil.which("javac")


class CodeqlLifecycleQueryContractTests(unittest.TestCase):
    def test_embedded_and_direct_pack_match_for_lifecycle_and_loop_growth(self) -> None:
        embedded = _ROOT / "dosweb" / "codeql" / "pack" / "dosweb"
        direct = _ROOT / "codeql" / "dosweb"
        relatives = (
            "Entries/EntryInterpositions.ql",
            "Flows/EntryToGrowth.ql", "Flows/EntryToGrowthAssociations.ql",
            "Lifecycle/GuardCandidates.ql", "Lifecycle/BoundCandidates.ql",
            "Lifecycle/SynchronousReleaseCandidates.ql", "Lifecycle/LifecycleCoverage.ql",
            "Lifecycle/LifecycleSummary.ql", "Growth/LoopAmplification.qll",
            "Growth/ContainerGrowth.ql", "Growth/AsyncWorkGrowth.ql",
        )
        for relative in relatives:
            with self.subTest(query=relative):
                self.assertEqual((embedded / relative).read_bytes(), (direct / relative).read_bytes())

    def test_queries_use_exact_candidate_only_contracts(self) -> None:
        queries = (
            ("codeql/dosweb/Flows/EntryToGrowth.ql", FLOW_COLUMNS),
            ("codeql/dosweb/Flows/EntryToGrowthAssociations.ql", FLOW_COLUMNS),
            ("codeql/dosweb/Lifecycle/GuardCandidates.ql", GUARD_COLUMNS),
            ("codeql/dosweb/Lifecycle/BoundCandidates.ql", BOUND_COLUMNS),
            ("codeql/dosweb/Lifecycle/SynchronousReleaseCandidates.ql", RELEASE_COLUMNS),
            ("codeql/dosweb/Lifecycle/LifecycleCoverage.ql", LIFECYCLE_COVERAGE_COLUMNS),
            ("codeql/dosweb/Lifecycle/LifecycleSummary.ql", LIFECYCLE_SUMMARY_COLUMNS),
        )
        forbidden = ("static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown", "assertion", "verdict", "lifecycle_result")
        for relative, columns in queries:
            with self.subTest(query=relative):
                content = (_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("@kind table", content)
                self.assertIn("import java", content)
                positions = [
                    content.index(f"as {column}")
                    if f"as {column}" in content
                    else content.rindex("confidence,")
                    if column == "confidence"
                    else -1
                    for column in columns
                ]
                self.assertNotIn(-1, positions)
                self.assertEqual(positions, sorted(positions))
                for term in forbidden:
                    self.assertNotIn(term, content.lower())


@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class CodeqlLifecycleFixtureTests(unittest.TestCase):
    def _database(self, source_root: Path, temporary: Path, name: str):
        database_path = temporary / f"{name}-database"
        classes = temporary / f"{name}-classes"
        classes.mkdir()
        java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
        completed = subprocess.run(
            [
                _CODEQL, "database", "create", str(database_path), "--language=java",
                f"--source-root={source_root}",
                f"--command={_JAVAC} -d {classes} " + " ".join(str(path) for path in java_files),
                "--overwrite",
            ], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
        return validate_database(database_path)

    def _rows(self, query_name: str, database, temporary: Path) -> list[dict[str, object]]:
        query = _ROOT / "codeql" / "dosweb" / query_name
        try:
            result = run_query(query, database, temporary / query_name.replace("/", "-"), codeql_binary=str(_codeql_wrapper(temporary)))
            decoded_path, query_sha256 = result.decoded_path, result.query_sha256
        except Exception as exc:
            if not (getattr(exc, "code", None) == "CODEQL_QUERY_FAILED" and getattr(exc, "details", {}).get("diagnostic") == "database changed during query execution"):
                raise
            bqrs = temporary / f"{query.stem}.bqrs"
            decoded_path = temporary / f"{query.stem}.json"
            completed = subprocess.run([str(_codeql_wrapper(temporary)), "query", "run", str(query), "--database", str(database.path), "--output", str(bqrs)], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            completed = subprocess.run([str(_codeql_wrapper(temporary)), "bqrs", "decode", str(bqrs), "--format=json", "--output", str(decoded_path)], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            query_sha256 = file_sha256(query)
        payload = json.loads(decoded_path.read_text(encoding="utf-8"))
        return decode_bqrs_json(
            {"EntryToGrowth": "flow", "EntryToGrowthAssociations": "flow", "GuardCandidates": "guard", "BoundCandidates": "bound", "SynchronousReleaseCandidates": "release", "LifecycleCoverage": "lifecycle_coverage", "LifecycleSummary": "lifecycle_summary"}[query.stem],
            payload,
            DecodeSource(database.source_root, query_sha256),
        )

    def test_fixture_semantics(self) -> None:
        cases = {
            "spring": {"association": True, "flow": True, "guard": True, "bound": False, "release": False, "coverage": True, "summary": False},
            "servlet": {"association": True, "flow": True, "guard": True, "bound": False, "release": True, "coverage": True, "summary": False},
            "netty": {"association": True, "flow": True, "guard": False, "bound": True, "release": True, "coverage": True, "summary": False},
            "mqtt": {"association": True, "flow": True, "guard": True, "bound": False, "release": False, "coverage": True, "summary": False},
            "armeria": {"association": False, "flow": False, "guard": False, "bound": False, "release": False, "coverage": False, "summary": False},
        }
        query_names = {
            "association": "Flows/EntryToGrowthAssociations.ql",
            "flow": "Flows/EntryToGrowth.ql",
            "guard": "Lifecycle/GuardCandidates.ql",
            "bound": "Lifecycle/BoundCandidates.ql",
            "release": "Lifecycle/SynchronousReleaseCandidates.ql",
            "coverage": "Lifecycle/LifecycleCoverage.ql",
            "summary": "Lifecycle/LifecycleSummary.ql",
        }
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            wrapper = _codeql_wrapper(temporary)
            self.assertTrue(wrapper.exists())
            for fixture, expectations in cases.items():
                source_root = _ROOT / "tests" / "fixtures" / fixture / "src" / "main" / "java"
                database = self._database(source_root, temporary, fixture)
                for family, query_name in query_names.items():
                    with self.subTest(fixture=fixture, query=family):
                        rows = self._rows(query_name, database, temporary)
                        if expectations[family]:
                            self.assertTrue(rows, f"expected {family} candidates for {fixture}")
                        for row in rows:
                            self.assertIn("coverage_status", row)
                            self.assertNotIn("verdict", row)
                            self.assertNotIn("assertion", row)
                        if family == "coverage":
                            self.assertTrue(all(row["family"] in {"guard", "bound", "release"} for row in rows))
                        if family == "guard":
                            for row in (item for item in rows if item["coverage_status"] == "complete"):
                                if row["coverage_note"] == "same_cfg_shared_source_guard_witness":
                                    self.assertTrue(row["dominates_growth"])
                                    self.assertFalse(row["reject_path_reaches_growth"])
                                    self.assertTrue(row["covers_materialization"])
                                    self.assertEqual("before_growth", row["phase"])
                                else:
                                    self.assertEqual("same_cfg_guard_ineffective_after_growth", row["coverage_note"])
                                    self.assertFalse(row["dominates_growth"])
                                    self.assertTrue(row["reject_path_reaches_growth"])
                                    self.assertFalse(row["covers_materialization"])
                                    self.assertEqual("after_growth", row["phase"])
                        if family == "release":
                            for row in (item for item in rows if item["coverage_status"] == "complete"):
                                self.assertTrue(row["after_growth"])
                                self.assertTrue(row["normal_path"])
                                self.assertTrue(row["actual_reduction"])
                                if row["exceptional_path"]:
                                    self.assertEqual("same_cfg_finally_release_witness", row["coverage_note"])
                                else:
                                    self.assertEqual("success_only_exception_path_missing", row["coverage_note"])
                        if fixture == "netty" and family == "bound":
                            self.assertTrue(any(row["coverage_status"] == "complete" for row in rows))


if __name__ == "__main__":
    unittest.main()
