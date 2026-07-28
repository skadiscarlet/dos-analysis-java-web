from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dosweb.artifacts.identifiers import sha256_canonical_json, stable_identifier
from dosweb.batch.aggregate import P0_ARTIFACTS, STAGES, aggregate, validate_manifest


def canonical_fixture() -> tuple[dict, dict, dict]:
    semantic = {"index": 1, "name": "owner/repo", "fingerprint_type": "git-commit", "fingerprint": "a" * 40, "source_path": "sources/owner__repo", "database_path": "databases/owner__repo"}
    identity = {"target_id": stable_identifier("target", semantic), **semantic, "slug": "owner__repo"}
    capability = {"provider_eligible": False, "public_source_url": None, "attestation": "unavailable", "reason": None}
    item = {"target_id": identity["target_id"], "identity": identity, "output_path": "results/targets/001-owner__repo", "capability": capability, "initial_state": "queued"}
    unsigned = {"schema_version": 1, "tool_version": "dosweb-v2", "batch_schema_version": "java-web-dos-batch-v1", "run_id": "run-1", "mode": "entries", "output_root": "results", "inventory_digest": "b" * 64, "provider": {}, "targets": [item]}
    digest = sha256_canonical_json(unsigned)
    plan = {**unsigned, "plan_id": f"plan:{digest[:24]}", "plan_digest": digest}
    state = {"schema_version": 1, "batch_id": plan["plan_id"], "mode": "entries", "status": "completed", "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00", "targets": {item["target_id"]: {"target_id": item["target_id"], "state": "completed", "status": "completed", "attempt": 1}}}
    return item, plan, state


class BatchAggregationContractTests(unittest.TestCase):
    def test_p0_manifest_requires_nested_target_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.normalized.jsonl"
            manifest.write_text(json.dumps({"slug": "legacy"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "P0 manifest requires nested identity"):
                validate_manifest([{"slug": "legacy"}], manifest, "p0")

    def test_p0_requires_plan_and_authoritative_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.normalized.jsonl").write_text(
                json.dumps({
                    "target_id": "target:one",
                    "identity": {"name": "owner/repo", "slug": "owner__repo"},
                    "output_path": "targets/one",
                    "capability": {},
                    "initial_state": "queued",
                }) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "batch_plan.json and batch_state.json"):
                aggregate(root, format="p0")

    def test_valid_normative_aggregation_counts_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item, plan, state = canonical_fixture()
            target = root / "targets" / "001-owner__repo"
            target.mkdir(parents=True)
            (target / ".stage-manifests").mkdir()
            (root / "manifest.normalized.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
            (root / "batch_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            (root / "batch_state.json").write_text(json.dumps(state), encoding="utf-8")
            (target / "batch_target.json").write_text(json.dumps({"plan_id": plan["plan_id"], "plan_digest": plan["plan_digest"], "run_id": "run-1", "mode": "entries", "target": item}), encoding="utf-8")
            entry_id, growth_id = "entry:fixture", "growth:fixture"
            resource = {"resource_id": stable_identifier("resource", {"dimension": "bytes", "receiver": "fixture.Handler", "field_path": "buffer"}), "dimension": "bytes", "receiver": "fixture.Handler", "field_path": "buffer"}
            entry = {"entry_id": entry_id, "framework": "servlet", "protocol": "http", "handler": {"callable": "fixture.Handler", "file": "Handler.java", "start_line": 1}, "registration": {}, "route_or_event": "/fixture", "auth_context": "unauthenticated", "attacker_inputs": [], "materialization_phase": "in_handler"}
            growth = {"growth_id": growth_id, "site": {"file": "Handler.java", "start_line": 2}, "kind": "direct_allocation", "operation": "allocate", "resource_point": resource, "demand_inputs": [{"name": "size", "role": "size"}], "escape_scope": "request", "candidate_evidence": ["fact:fixture"], "coverage_status": "complete", "coverage_notes": ["fixture"]}
            flow_id = stable_identifier("flow", {"entry_id": entry_id, "growth_id": growth_id, "attacker_control": {"target": "size", "source": "request", "sink": "allocate"}, "call_path": ["fixture.Handler"], "phase_sequence": ["handler"], "confidence": "proven"})
            flow = {"path_id": flow_id, "entry_id": entry_id, "growth_id": growth_id, "attacker_control": {"target": "size", "source": "request", "sink": "allocate"}, "call_path": ["fixture.Handler"], "phase_sequence": ["handler"], "confidence": "proven", "flow_kind": "direct", "coverage_status": "complete", "coverage_note": "fixture"}
            certificate_id = "certificate:fixture"
            certificate = {"certificate_id": certificate_id, "entry_id": entry_id, "growth_id": growth_id, "attacker_inputs": [], "resource_point": resource, "path_ids": [flow_id], "guard_decision": {}, "bound_decision": {}, "release_decision": {}, "assertions": [], "verdict": "static_unknown", "reason_codes": [], "assumptions": [], "coverage_gaps": [], "unresolved_facts": [], "suggested_follow_up_measurements": []}
            records = {"entry_facts.jsonl": [entry], "growth_candidates.jsonl": [growth], "flow_proofs.jsonl": [flow], "static_findings.jsonl": [{"finding_id": "finding:fixture", "certificate_id": certificate_id, "entry_id": entry_id, "growth_id": growth_id, "verdict": "static_unknown", "reason_codes": []}], "lifecycle_certificates.jsonl": [certificate]}
            artifacts = {}
            for name in P0_ARTIFACTS:
                if name.endswith(".jsonl"):
                    data = ("".join(json.dumps(row) + "\n" for row in records.get(name, []))).encode()
                else:
                    data = ("{}\n" if name.endswith(".json") else "report\n").encode()
                path = target / name
                path.write_bytes(data)
                artifacts[name] = {"path": name, "schema_version": "2.0", "sha256": __import__("hashlib").sha256(data).hexdigest(), "record_count": data.count(b"\n"), "byte_count": len(data)}
            for stage in STAGES:
                names = [name for name in P0_ARTIFACTS if name in ({"entries": {"coverage.json", "entry_facts.jsonl"}, "growth": {"growth_candidates.jsonl", "growth_contracts.jsonl", "verified_growth.jsonl"}, "flows": {"flow_proofs.jsonl"}, "lifecycle": {"guard_candidates.jsonl", "bound_candidates.jsonl", "release_candidates.jsonl", "lifecycle_results.jsonl"}, "conclude": {"static_findings.jsonl", "lifecycle_certificates.jsonl"}, "report": {"summary.json", "report.md"}}[stage])]
                entries = [artifacts[name] for name in names]
                manifest = {"stage": stage, "status": "completed", "artifacts": entries, "output_hash": __import__("hashlib").sha256(json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()).hexdigest()}
                (target / ".stage-manifests" / f"{stage}.json").write_text(json.dumps(manifest), encoding="utf-8")
            run = {"run_id": "run-1", "status": "completed", "stages": {stage: json.loads((target / ".stage-manifests" / f"{stage}.json").read_text()) for stage in STAGES}}
            (target / "run.json").write_text(json.dumps(run), encoding="utf-8")
            aggregate(root, format="p0")
            inventory = json.loads((root / "aggregate_inventory.json").read_text())
            self.assertEqual("completed", inventory["targets"][0]["status"], inventory["targets"][0])
            self.assertEqual(1, inventory["verdict_counts"].get("static_unknown", 0))

    def test_p0_binding_mismatch_is_accounted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item, plan, state = canonical_fixture()
            (root / "manifest.normalized.jsonl").write_text(json.dumps(item) + "\n")
            (root / "batch_plan.json").write_text(json.dumps(plan))
            (root / "batch_state.json").write_text(json.dumps(state))
            target = root / "targets" / "001-owner__repo"; target.mkdir(parents=True)
            (target / "batch_target.json").write_text(json.dumps({"run_id": "wrong", "target": item}))
            aggregate(root, format="p0")
            status = json.loads((root / "aggregate_status.jsonl").read_text().splitlines()[0])
            self.assertEqual("malformed", status["status"])

    def test_format_must_be_explicitly_normative_for_p0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "unknown aggregation format"):
                aggregate(root, format="normative")


if __name__ == "__main__":
    unittest.main()
