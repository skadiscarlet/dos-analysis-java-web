from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from dosweb.cli import main
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.evidence import replay
from dosweb.resource_lifecycle.commands import resource_replay
from tests.test_resource_lifecycle_cli import ResourceLifecycleCliTests


class ResourceLifecycleReplayTests(unittest.TestCase):
    def _run(self, root: Path) -> Path:
        manifest = ResourceLifecycleCliTests()._manifest(root)
        facts = root / "facts"
        run = root / "run"
        self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(facts)]))
        self.assertEqual(0, main(["resource-analyze", "--facts", str(facts / "facts.json"), "--out", str(run), "--llm", "off"]))
        return run

    def _async_run(self, root: Path) -> Path:
        manifest = ResourceLifecycleCliTests()._async_manifest(root)
        facts = root / "facts"
        run = root / "run"
        self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(facts)]))
        self.assertEqual(0, main(["resource-analyze", "--facts", str(facts / "facts.json"), "--out", str(run), "--llm", "off"]))
        return run

    def test_replay_recomputes_and_detects_stored_result_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            path = run / "lifecycle-results.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            original = value["units"][0]["dimensions"][0]["lifecycle_status"]
            value["units"][0]["dimensions"][0]["lifecycle_status"] = (
                "obligation_gap" if original != "obligation_gap" else "unknown"
            )
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            result = replay(run)

        self.assertFalse(result.consistent)
        self.assertTrue(result.recomputed)
        self.assertNotEqual(result.stored_result_sha256, result.recomputed_result_sha256)

    def test_replay_rejects_non_finite_exponent_numbers_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            path = run / "lifecycle-results.json"
            raw = path.read_text(encoding="utf-8")
            tampered, replacements = re.subn(r'("steps":)\d+', r'\g<1>1e309', raw, count=1)
            self.assertEqual(1, replacements)
            path.write_text(tampered, encoding="utf-8")

            status = main(["resource-replay", "--run", str(run)])

        self.assertEqual(5, status)

    def test_replay_rejects_changed_fact_snapshot_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            path = run / "facts.snapshot.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["snapshot_sha256"] = "0" * 64
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            with self.assertRaises(AnalyzerError) as raised:
                replay(run)

        self.assertEqual("ARTIFACT_INPUT_INVALID", raised.exception.code)

    def test_replay_rejects_manifest_contract_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            path = run / "run-manifest.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["contracts_versions"] = ["resource-lifecycle-contracts-v999"]
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            with self.assertRaises(AnalyzerError) as raised:
                replay(run)

        self.assertEqual("ARTIFACT_INPUT_INVALID", raised.exception.code)

    def test_evidence_records_premises_conclusions_and_code_locations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            evidence = json.loads((run / "evidence.json").read_text(encoding="utf-8"))

        self.assertTrue(evidence["derivations"])
        first = evidence["derivations"][0]
        self.assertTrue(first["rule_ids"])
        self.assertTrue(first["premises"])
        self.assertIn("held_edges", first["conclusion"])
        self.assertTrue(first["code_locations"])
        self.assertTrue(evidence["dimension_derivations"])
        self.assertTrue(all(item["evidence_id"] in evidence["facts"] for item in evidence["dependencies"]))
        release_dependencies = {
            item["evidence_id"]
            for item in evidence["dependencies"]
            if item["rule_id"] == "release_exact_obligation"
        }
        self.assertEqual({"fact:release"}, release_dependencies)

    def test_replay_recomputes_and_detects_evidence_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            path = run / "evidence.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["derivations"][0]["premises"] = ["fabricated:true"]
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            result = resource_replay({"run": run})

        self.assertFalse(result["consistent"])
        self.assertFalse(result["evidence_consistent"])
        self.assertNotEqual(result["stored_evidence_sha256"], result["recomputed_evidence_sha256"])

    def test_async_evidence_records_rules_dependencies_location_and_all_stage_conclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._async_run(Path(tmp))
            evidence = json.loads((run / "evidence.json").read_text(encoding="utf-8"))

        self.assertEqual(1, len(evidence["async_derivations"]))
        derivation = evidence["async_derivations"][0]
        self.assertRegex(derivation["derivation_id"], r"^[0-9a-f]{64}$")
        self.assertRegex(derivation["stage_id"], r"^async-stage:[0-9a-f]{24}$")
        self.assertEqual("effect:dispatch:task", derivation["dispatch_effect_id"])
        self.assertEqual(
            {"submitted"},
            set(derivation["conclusions"]),
        )
        self.assertEqual(1, len(derivation["code_locations"]))
        self.assertEqual("src/main/java/Fixture.java", derivation["code_locations"][0]["path"])
        self.assertEqual(
            ["fact:create", "fact:dispatch", "fact:retain"],
            derivation["evidence_ids"],
        )
        async_rule_ids = set(derivation["rule_ids"])
        async_rules = {
            item["rule_id"]: item["implementation"]
            for item in evidence["rules"]
            if item["rule_id"] in async_rule_ids
        }
        self.assertEqual(async_rule_ids, set(async_rules))
        self.assertEqual(
            "resource_lifecycle.solver.apply_effect",
            async_rules["create_instance"],
        )
        self.assertEqual(
            "resource_lifecycle.solver.apply_effect",
            async_rules["retain_holder_edge"],
        )
        dispatch_rule_ids = async_rule_ids - {"create_instance", "retain_holder_edge"}
        self.assertEqual(
            {"resource_lifecycle.solver.apply_effect"},
            {async_rules[rule_id] for rule_id in dispatch_rule_ids},
        )
        dependencies = {
            (item["rule_id"], item["evidence_id"])
            for item in evidence["dependencies"]
            if item["rule_id"] in async_rule_ids
        }
        self.assertEqual(
            {
                ("create_instance", "fact:create"),
                ("retain_holder_edge", "fact:retain"),
                *{(rule_id, "fact:dispatch") for rule_id in dispatch_rule_ids},
            },
            dependencies,
        )
        self.assertTrue(
            all(item["evidence_id"] in evidence["facts"] for item in evidence["dependencies"])
        )

    def test_replay_async_result_tampering_invalidates_result_and_evidence_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._async_run(Path(tmp))
            path = run / "lifecycle-results.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["units"][0]["async_stages"][0]["submitted"]["held_edges"].append(
                ["instance:fabricated", "holder:fabricated"]
            )
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            result = resource_replay({"run": run})

        self.assertFalse(result["consistent"])
        self.assertFalse(result["evidence_consistent"])

    def test_replay_async_evidence_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._async_run(Path(tmp))
            path = run / "evidence.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["async_derivations"][0]["rule_ids"] = ["fabricated_rule"]
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            result = resource_replay({"run": run})

        self.assertFalse(result["consistent"])
        self.assertFalse(result["evidence_consistent"])

    def test_replay_population_result_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._async_run(Path(tmp))
            path = run / "lifecycle-results.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            population = value["units"][0]["population_properties"]
            self.assertEqual(1, len(population))
            population[0]["queue_upper_bound"] = 999
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            result = resource_replay({"run": run})

        self.assertFalse(result["consistent"])
        self.assertFalse(result["evidence_consistent"])

    def test_replay_population_evidence_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._async_run(Path(tmp))
            path = run / "evidence.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            population = value["population_derivations"]
            self.assertEqual(1, len(population))
            population[0]["guards"] = ["fabricated guard"]
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            result = resource_replay({"run": run})

        self.assertFalse(result["consistent"])
        self.assertFalse(result["evidence_consistent"])

    def test_replay_model_count_result_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            path = run / "lifecycle-results.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            model_count = value["model_count_properties"]
            self.assertEqual(3, len(model_count))
            model_count[0]["relation"] = "N'=N"
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            result = resource_replay({"run": run})

        self.assertFalse(result["consistent"])
        self.assertFalse(result["evidence_consistent"])

    def test_replay_model_count_evidence_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            path = run / "evidence.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            derivations = value["model_count_derivations"]
            self.assertEqual(3, len(derivations))
            derivations[0]["relation"] = "N'=N+999"
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            result = resource_replay({"run": run})

        self.assertFalse(result["consistent"])
        self.assertFalse(result["evidence_consistent"])

    def test_replay_rejects_implementation_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp))
            path = run / "run-manifest.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["implementation_sha256"] = "0" * 64
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            with self.assertRaises(AnalyzerError) as raised:
                replay(run)

        self.assertEqual("ARTIFACT_INPUT_INVALID", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
