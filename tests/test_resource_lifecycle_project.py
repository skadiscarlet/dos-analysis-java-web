from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dosweb.errors import AnalyzerError
from dosweb.entries.models import EntryFact, HandlerFact, RegistrationFact, AttackerInputFact
from dosweb.growth.slices import GrowthCandidate, SourceLocation, DemandInput
from dosweb.resource_lifecycle.adapters import adapt_codeql_rows
from dosweb.resource_lifecycle.commands import _analyze_payload, _java_source_snapshot
from dosweb.resource_lifecycle.project import resource_project
from tests.test_resource_lifecycle_codeql import lifecycle_row, SYNTHETIC_HANDLE_ID


class ResourceLifecycleProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "Fixture.java").write_text("class Fixture { Object a, b; }\n")
        self.tree_hash = _java_source_snapshot(self.source)[1]
        self.extracted = adapt_codeql_rows([
            lifecycle_row(),
            lifecycle_row(instance_key="Fixture.java:1:20", site_start_column=20,
                          program_point="point:Fixture.java:1:20:create"),
        ], source_root=self.source, query_sha256="a" * 64, entry_methods=[SYNTHETIC_HANDLE_ID])
        self.extracted = replace(self.extracted, coverage={**self.extracted.coverage, "source_snapshot_sha256": self.tree_hash})
        self.families = sorted(f.family_id for f in self.extracted.units[0].program.families)
        self.payload = {"version": "resource-project-v1.2", "project_id": "local-fixture",
            "source_root": "source", "tree_hash": self.tree_hash, "database": "database",
            "selection": [{"input_id": "method", "kind": "method", "entry_callable": SYNTHETIC_HANDLE_ID}],
            "dependency_scope": {"sources": ["Fixture.java"], "dependencies": [], "unknown_dependencies": []},
            "budgets": {}, "output": "output"}

    def analyze(self, extracted):
        result = _analyze_payload(extracted)
        result["units"][0]["terminated"] = True
        result["units"][0]["properties"] = [{"property_id": "property:" + family,
            "resource_family_id": family, "status": "bounded"} for family in self.families]
        return result

    def run_project(self, *, extract_error=None, analyze=None):
        self.payload["output"] = "output-" + str(len(list(self.root.glob("output-*"))))
        path = self.root / "project.json"
        path.write_text(json.dumps(self.payload))
        with patch("dosweb.resource_lifecycle.project.validate_database", return_value=SimpleNamespace(source_root=self.source)), \
             patch("dosweb.resource_lifecycle.project._codeql_facts", return_value=self.extracted, side_effect=extract_error) as extraction, \
             patch("dosweb.resource_lifecycle.commands._analyze_payload", side_effect=analyze or self.analyze) as analysis:
            result = resource_project({"manifest": path})
            return result, extraction.call_count, analysis.call_count

    def test_mixed_inputs_keep_denominator_and_share_computation(self):
        common = {"kind": "candidate", "entry_callable": SYNTHETIC_HANDLE_ID}
        self.payload["selection"] += [
            {**common, "input_id": "candidate", "resource_family_id": self.families[0]},
            {**common, "input_id": "duplicate", "resource_family_id": self.families[0]},
            {**common, "input_id": "ambiguous"},
            {**common, "input_id": "stale", "source_sha256": "f" * 64},
            {"input_id": "missing", "kind": "method", "entry_callable": "absent"},
        ]
        result, extraction, analysis = self.run_project()
        self.assertEqual((result["requested"], extraction, analysis), (6, 1, 1))
        rows = {row["input_id"]: row for row in result["ledger"]}
        self.assertEqual(rows["candidate"]["property_ids"], rows["duplicate"]["property_ids"])
        self.assertTrue(set(rows["candidate"]["property_ids"]) < set(rows["method"]["property_ids"]))
        self.assertEqual(rows["ambiguous"]["mapping"], "mapping_ambiguous")
        self.assertEqual(rows["stale"]["mapping"], "stale_source")
        self.assertEqual(rows["missing"]["mapping"], "mapping_missing")
        self.assertEqual(sum(result["stage_counts"]["mapping"].values()), 6)
        self.assertEqual(result["status"], "partial")
        self.payload["selection"].reverse()
        reordered, _, _ = self.run_project()
        self.assertEqual(result, reordered)

    def test_exact_same_line_allocation_is_not_ambiguous(self):
        self.payload["selection"] += [{"input_id": "precise", "kind": "candidate",
            "entry_callable": SYNTHETIC_HANDLE_ID, "allocation": {"instance_key": "Fixture.java:1:20", "start_column": 20}}]
        result, _, _ = self.run_project()
        row = next(row for row in result["ledger"] if row["input_id"] == "precise")
        self.assertEqual(row["mapping"], "mapped")
        self.assertEqual(len(row["property_ids"]), 1)

    def test_shared_query_failure_invalidates_every_input(self):
        result, extraction, analysis = self.run_project(extract_error=ValueError("query failed"))
        self.assertEqual((extraction, analysis), (1, 0))
        self.assertEqual(result["stage_counts"]["extraction"], {"failed": 1})
        self.assertEqual(result["status"], "partial")

    def test_stale_tree_stops_before_extraction(self):
        self.payload["tree_hash"] = "0" * 64
        result, extraction, analysis = self.run_project()
        self.assertEqual((extraction, analysis), (0, 0))
        self.assertEqual(result["ledger"][0]["mapping"], "stale_source")

    def test_old_verdicts_and_line_only_selectors_are_rejected(self):
        for field, value in (("static_vulnerable", True), ("effective_bound", {}),
                             ("allocation", {"path": "Fixture.java", "start_line": 1})):
            with self.subTest(field=field):
                item = {"input_id": "candidate", "kind": "candidate", "entry_callable": SYNTHETIC_HANDLE_ID, field: value}
                self.payload["selection"] = [item]
                with self.assertRaises(AnalyzerError):
                    self.run_project()

    def test_missing_published_property_is_unknown_not_zero_bound(self):
        def empty(extracted):
            result = self.analyze(extracted)
            result["units"][0]["properties"] = []
            return result
        result, _, _ = self.run_project(analyze=empty)
        self.assertEqual(result["ledger"][0]["analysis"], "unknown")
        self.assertEqual(result["ledger"][0]["reason"], "missing_property")
        self.assertEqual(result["ledger"][0]["property_ids"], [])

    def test_result_budget_keeps_failed_input(self):
        self.payload["budgets"] = {"max_decoded_bytes": 5000}
        result, _, _ = self.run_project()
        self.assertEqual(result["requested"], 1)
        self.assertEqual(result["ledger"][0]["analysis"], "budget_exit")
        self.assertEqual(result["ledger"][0]["reason"], "storage_budget_exit")

    def test_analyzer_failure_keeps_input(self):
        def fail(_):
            raise ValueError("invalid unit")
        result, _, _ = self.run_project(analyze=fail)
        self.assertEqual(result["ledger"][0]["analysis"], "failed")

    def test_source_root_can_be_rebound_without_changing_identity(self):
        self.payload["source_root"] = None
        self.payload["output"] = "output-" + str(len(list(self.root.glob("output-*"))))
        path = self.root / "project.json"
        path.write_text(json.dumps(self.payload))
        with patch("dosweb.resource_lifecycle.project.validate_database", return_value=SimpleNamespace(source_root=self.source)), \
             patch("dosweb.resource_lifecycle.project._codeql_facts", return_value=self.extracted), \
             patch("dosweb.resource_lifecycle.commands._analyze_payload", side_effect=self.analyze):
            result = resource_project({"manifest": path, "source_root": self.source})
        self.assertEqual(result["source_tree_hash"], self.tree_hash)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_real_solver_properties_are_shared_by_method_and_candidate(self):
        self.payload["selection"].append({"input_id": "candidate", "kind": "candidate",
            "entry_callable": SYNTHETIC_HANDLE_ID, "resource_family_id": self.families[0]})
        result, _, analysis_count = self.run_project(analyze=_analyze_payload)
        self.assertEqual(analysis_count, 1)
        rows = {row["input_id"]: row for row in result["ledger"]}
        ordinary = _analyze_payload(self.extracted)["units"][0]["properties"]
        self.assertTrue(ordinary)
        self.assertEqual(rows["method"]["property_ids"], sorted({prop["property_id"] for prop in ordinary}))
        self.assertEqual(rows["candidate"]["property_ids"], sorted({prop["property_id"] for prop in ordinary
            if prop.get("resource_family_id") == self.families[0]}))

    def test_default_project_delivery_is_sharded_and_replays_without_second_analysis(self):
        from dosweb.resource_lifecycle.sharded_run import replay_sharded
        result, _, calls = self.run_project(analyze=_analyze_payload)
        self.assertEqual(calls, 1)
        self.assertEqual(result["replay_directory"], "analysis")
        output = self.root / self.payload["output"]
        self.assertTrue((output / "analysis/run-index.json").is_file())
        self.assertFalse((output / "units").exists())
        self.assertEqual(result["serialized_evidence_bytes"], sum(p.stat().st_size for p in (output / "analysis").rglob("*.json")))
        self.assertLessEqual(result["max_shard_bytes"], 16 * 1024 * 1024)
        replay = replay_sharded(output / "analysis", source_root=self.source)
        self.assertEqual(replay["scope"], "selected")
        self.assertEqual(replay["mode"], "semantic_replay")

    def test_ledger_has_an_explicit_byte_budget(self):
        self.payload["budgets"] = {"max_ledger_bytes": 100}
        with self.assertRaises(AnalyzerError):
            self.run_project()

    def growth_record(self):
        return GrowthCandidate.create(site=SourceLocation("Fixture.java", 1), kind="direct_allocation",
            operation="new", resource_dimension="objects", receiver="fixture", field_path="none",
            demand_inputs=(DemandInput("argument", "size"),), escape_scope="request",
            evidence_ids=frozenset({"fact:original-source"})).to_dict()

    def imported_selection(self, record):
        return {"input_id": "imported", "kind": "candidate", "entry_callable": SYNTHETIC_HANDLE_ID,
            "candidate_file": "growth_candidates.jsonl", "record_id": record["growth_id"],
            "allocation": {"instance_key": "Fixture.java:1:20"},
            "source_sha256": self.extracted.units[0].program.families[0].allocation.source_sha256}

    def test_existing_growth_jsonl_import_ignores_old_judgments(self):
        record = self.growth_record()
        path = self.root / "growth_candidates.jsonl"
        path.write_text(json.dumps({**record, "actual_reduction": True, "effective_bound": 123,
                                    "static_vulnerable": True}) + "\n")
        self.payload["selection"].append(self.imported_selection(record))
        result, _, count = self.run_project(analyze=_analyze_payload)
        self.assertEqual(count, 1)
        imported = next(row for row in result["ledger"] if row["input_id"] == "imported")
        self.assertEqual(imported["mapping"], "mapped")
        self.assertTrue(imported["property_ids"])
        self.assertEqual(imported["imported_observation"]["candidate_evidence"], ["fact:original-source"])
        self.assertNotIn("effective_bound", imported["imported_observation"])
        path.write_text(json.dumps({**record, "actual_reduction": False, "effective_bound": None,
                                    "static_vulnerable": False}) + "\n")
        changed, _, _ = self.run_project(analyze=_analyze_payload)
        changed_row = next(row for row in changed["ledger"] if row["input_id"] == "imported")
        self.assertEqual(imported["property_ids"], changed_row["property_ids"])
        self.assertEqual(imported["imported_observation"], changed_row["imported_observation"])

    def test_existing_candidate_without_exact_identity_stays_in_denominator(self):
        record = self.growth_record()
        (self.root / "growth_candidates.jsonl").write_text(json.dumps(record) + "\n")
        item = self.imported_selection(record)
        del item["allocation"]
        self.payload["selection"].append(item)
        result, _, _ = self.run_project()
        row = next(row for row in result["ledger"] if row["input_id"] == "imported")
        self.assertEqual(result["requested"], 2)
        self.assertEqual(row["mapping"], "mapping_missing")
        self.assertEqual(row["reason"], "candidate_has_no_exact_allocation_identity")

    def test_duplicate_or_missing_import_record_is_not_silently_dropped(self):
        record = self.growth_record()
        self.payload["selection"] = [self.imported_selection(record)]
        path = self.root / "growth_candidates.jsonl"
        path.write_text((json.dumps(record) + "\n") * 2)
        result, extraction, _ = self.run_project()
        self.assertEqual(extraction, 0)
        self.assertEqual(result["ledger"][0]["mapping"], "mapping_ambiguous")
        path.write_text("")
        result, extraction, _ = self.run_project()
        self.assertEqual(extraction, 0)
        self.assertEqual(result["ledger"][0]["mapping"], "mapping_missing")

    def test_imported_candidate_requires_snapshot_and_detects_staleness(self):
        record = self.growth_record()
        (self.root / "growth_candidates.jsonl").write_text(json.dumps(record) + "\n")
        item = self.imported_selection(record)
        del item["source_sha256"]
        self.payload["selection"] = [item]
        result, extraction, _ = self.run_project()
        self.assertEqual(extraction, 0)
        self.assertEqual(result["ledger"][0]["reason"], "candidate_source_snapshot_unbound")
        item["source_sha256"] = "b" * 64
        result, _, _ = self.run_project()
        self.assertEqual(result["ledger"][0]["mapping"], "stale_source")

    def test_candidate_reader_rejects_symlink_and_oversized_record(self):
        record = self.growth_record()
        self.payload["selection"] = [self.imported_selection(record)]
        target = self.root / "actual.jsonl"
        target.write_text(json.dumps(record) + "\n")
        link = self.root / "growth_candidates.jsonl"
        link.symlink_to(target)
        result, extraction, _ = self.run_project()
        self.assertEqual(extraction, 0)
        self.assertEqual(result["ledger"][0]["reason"], "candidate_artifact_invalid_or_unavailable")
        link.unlink()
        link.write_text(json.dumps({**record, "ignored": "x" * 262145}) + "\n")
        result, extraction, _ = self.run_project()
        self.assertEqual(extraction, 0)
        self.assertEqual(result["ledger"][0]["reason"], "candidate_artifact_invalid_or_unavailable")

    def test_existing_entry_record_preserves_callable_and_input_references(self):
        entry = EntryFact.create(framework="spring_mvc", protocol="http",
            handler=HandlerFact(SYNTHETIC_HANDLE_ID, "Fixture.java", 1),
            registration=RegistrationFact("annotation_mapping", SYNTHETIC_HANDLE_ID, "Fixture.java", 1),
            route_or_event="GET /fixture", auth_context="unauthenticated",
            attacker_inputs=(AttackerInputFact("input", "java.lang.String", "request_parameter"),),
            materialization_phase="in_handler")
        (self.root / "entries.jsonl").write_text(json.dumps(entry.to_dict()) + "\n")
        self.payload["selection"] = [{"input_id": "entry", "kind": "candidate", "candidate_file": "entries.jsonl",
            "record_id": entry.entry_id, "resource_family_id": self.families[0],
            "source_sha256": self.extracted.units[0].program.families[0].allocation.source_sha256}]
        result, _, _ = self.run_project()
        row = result["ledger"][0]
        self.assertEqual(row["mapping"], "mapped")
        self.assertEqual(row["entry_callable"], SYNTHETIC_HANDLE_ID)
        self.assertEqual(row["imported_observation"]["attacker_inputs"], [entry.attacker_inputs[0].to_dict()])


if __name__ == "__main__":
    unittest.main()


class ProjectPathResolutionTests(unittest.TestCase):
    def test_cli_paths_are_cwd_relative_and_manifest_paths_are_manifest_relative(self):
        from dosweb.resource_lifecycle.project import _path
        base = Path("/tmp/project-manifest-location")
        self.assertEqual(Path.cwd() / "relative-run", _path({"output": "other"}, {"out": Path("relative-run")}, "output", base, "out"))
        self.assertEqual(base / "relative-run", _path({"output": "relative-run"}, {}, "output", base, "out"))
