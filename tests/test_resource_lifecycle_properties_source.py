"""Actual Java extraction acceptance, separate from independent-module evaluation."""
from dataclasses import asdict, replace
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from dosweb.resource_lifecycle.adapters import extracted_from_dict, validate_extracted
from dosweb.resource_lifecycle.commands import _analyze_payload, _codeql_facts
from dosweb.resource_lifecycle.models import AnalysisBudget, SCHEMA_VERSION
from dosweb.resource_lifecycle.sharded_run import analyze_sharded, replay_sharded
from dosweb.resource_lifecycle.shards import ShardReader
from dosweb.resource_lifecycle.source_evaluation import SourceExpectedOutcome, _observation
from tests.support.fixture_database import fixture_database


@unittest.skipUnless(os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1", "real CodeQL opt-in")
class MultiResourceSourceTests(unittest.TestCase):
    def test_compiled_multiple_families_cli_evaluation_relocated_replay(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "tests/fixtures/resource_lifecycle_v1_2/src/main/java"
        reused_run = os.environ.get("DOSWEB_V12_PROJECT_RUN")
        database = None if reused_run else fixture_database(str(source))
        entry = "java-callable-v1:fixture.lifecyclev12.MultiResource.twoResources()V"
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            if reused_run:
                # Reuse actual project extraction to avoid racing CodeQL's DB
                # cache lock. This branch never creates or mocks raw facts.
                saved = next(payload for name, payload in ShardReader(Path(reused_run)).iter_objects() if name == entry)
                facts = validate_extracted(extracted_from_dict(saved["facts"]))
                self.assertEqual("static_verified", facts.source_kind)
                self.assertEqual("real_source_codeql", facts.coverage["end_to_end_mode"])
            else:
                facts = _codeql_facts({"schema_version": SCHEMA_VERSION, "mode": "codeql_database",
                    "database": str(database.path), "entry_methods": [entry],
                    "budget": asdict(AnalysisBudget(max_steps=50000, timeout_ms=15000))}, {}, work / "extracted")
            unit = next(unit for unit in facts.units if unit.unit_id == entry)
            self.assertGreaterEqual(len(unit.program.families), 2)
            # Preserve all extraction provenance; ordinary analysis is authoritative.
            results = _analyze_payload(facts)
            result = next(item for item in results["units"] if item["unit_id"] == entry)
            for property in result["properties"]:
                if property["scope"] not in {"all_exits", "per_instance"}:
                    continue
                expected = SourceExpectedOutcome("full", property["dimension"], property["scope"],
                    property["cut"], property["status"], property["upper_bound"], None)
                actual = _observation(expected, result, unit, property["resource_family_id"])
                self.assertEqual(property["property_id"], actual["property_id"])
                self.assertEqual(property["status"], actual["lifecycle_status"])
                self.assertEqual(actual, _observation(replace(expected, lifecycle_status="unknown", upper_bound=123),
                                                     result, unit, property["resource_family_id"]))
            analyze_sharded(facts, work / "run", source_root=source)
            copied = work / "copied"
            shutil.copytree(work / "run", copied)
            rebound = work / "source"
            shutil.copytree(source, rebound)
            replay = replay_sharded(copied, rebound)
            self.assertEqual("semantic_replay", replay["mode"])
            saved = next(payload for name, payload in ShardReader(copied).iter_objects() if name == entry)
            self.assertEqual(result["properties"], saved["results"]["units"][0]["properties"])
