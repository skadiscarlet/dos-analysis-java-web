from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.batch.models import CanonicalCorpus, CorpusTarget, TargetCapability, TargetIdentity
from dosweb.batch.plan import build_batch_plan, load_batch_plan, publish_batch_plan, write_target_binding
from dosweb.batch.corpus import _tree_fingerprint, resolve_repo_relative
from dosweb.errors import AnalyzerError


class BatchPlanTests(unittest.TestCase):
    def _corpus(self, total: int = 2) -> CanonicalCorpus:
        targets = []
        for index in range(1, total + 1):
            identity = TargetIdentity(
                index=index,
                name=f"owner{index}/repo{index}",
                fingerprint_type="git-commit",
                fingerprint="a" * 40,
                source_path=f"frameworks/applications/owner{index}__repo{index}",
                database_path=f"databases/applications/owner{index}__repo{index}-db",
            )
            targets.append(CorpusTarget(
                identity=identity,
                source=Path(identity.source_path),
                database=Path(identity.database_path),
                capability=TargetCapability(True, f"https://github.com/{identity.name}", "git-commit"),
                database_fingerprint="b" * 64,
            ))
        return CanonicalCorpus(1, "canonical", "java-web-200", total, "c" * 64, tuple(targets), Path("manifest.json"))

    def test_plan_identity_and_json_publication_are_deterministic(self) -> None:
        corpus = self._corpus()
        first = build_batch_plan(corpus, run_id="run-1", mode="entries")
        second = build_batch_plan(corpus, run_id="run-1", mode="entries")
        self.assertEqual(first.plan_id, second.plan_id)
        self.assertTrue(first.verify_digest())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path, jsonl_path = publish_batch_plan(first, root)
            loaded = load_batch_plan(json_path)
            self.assertEqual(loaded.plan_digest, first.plan_digest)
            self.assertEqual("b" * 64, loaded.targets[0].database_fingerprint)
            self.assertEqual("b" * 64, json.loads(json_path.read_text())["targets"][0]["database_fingerprint"])
            self.assertEqual(jsonl_path.read_text().count("\n"), 2)
            binding = write_target_binding(first, first.targets[0], root / "target")
            payload = json.loads(binding.read_text())
            self.assertEqual(payload["plan_id"], first.plan_id)
            self.assertEqual("b" * 64, payload["target"]["database_fingerprint"])
            self.assertNotIn("DEEPSEEK_API_KEY", binding.read_text())

    def test_provider_source_binding_is_plan_digest_bound(self) -> None:
        corpus = self._corpus(1)
        target = corpus.targets[0]
        capability = TargetCapability(
            True,
            "https://github.com/owner1/repo1",
            "git-commit",
            provider_source_path="build/poc29/owner1__repo1",
            provider_source_commit="e" * 40,
        )
        corpus = CanonicalCorpus(
            corpus.schema_version,
            corpus.status,
            corpus.corpus,
            corpus.total,
            corpus.inventory_digest,
            (CorpusTarget(target.identity, target.source, target.database, capability, target.database_fingerprint),),
            corpus.manifest_path,
        )

        plan = build_batch_plan(corpus, run_id="provider", mode="full")

        self.assertEqual("build/poc29/owner1__repo1", plan.targets[0].capability.provider_source_path)
        self.assertEqual("e" * 40, plan.targets[0].capability.provider_source_commit)
        self.assertTrue(plan.verify_digest())

    def test_full_keeps_tree_attestation_targets_queued(self) -> None:
        corpus = self._corpus(1)
        identity = TargetIdentity(1, "owner/repo", "tree-sha256", "b" * 64, "src", "db")
        target = CorpusTarget(
            identity,
            Path("src"),
            Path("db"),
            TargetCapability(False, None, "tree-sha256", "attestation_unavailable"),
            "d" * 64,
        )
        corpus = CanonicalCorpus(1, "canonical", "java-web-200", 1, "d" * 64, (target,), Path("manifest.json"))
        plan = build_batch_plan(corpus, run_id="run", mode="full")
        self.assertEqual(plan.targets[0].initial_state, "queued")

    def test_tree_fingerprint_uses_inventory_nul_separators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Fixture.java").write_bytes(b"class Fixture {}\n")
            expected = __import__("hashlib").sha256(
                b"Fixture.java\0class Fixture {}\n\0"
            ).hexdigest()
            self.assertEqual(_tree_fingerprint(root), expected)

    def test_load_rejects_noncanonical_target_output_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = build_batch_plan(self._corpus(1), run_id="run", mode="entries")
            path, _ = publish_batch_plan(plan, root)
            value = json.loads(path.read_text())
            value["targets"][0]["output_path"] = "other/targets/001-owner1__repo1"
            value["plan_digest"] = sha256_canonical_json({key: value[key] for key in value if key not in {"plan_id", "plan_digest"}})
            value["plan_id"] = f"plan:{value['plan_digest'][:24]}"
            path.write_text(json.dumps(value))
            with self.assertRaises(AnalyzerError):
                load_batch_plan(path)

    def test_legacy_plan_without_database_fingerprint_remains_loadable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = build_batch_plan(self._corpus(1), run_id="run", mode="entries")
            path, _ = publish_batch_plan(plan, root)
            value = json.loads(path.read_text())
            value["targets"][0].pop("database_fingerprint")
            unsigned = {key: value[key] for key in value if key not in {"plan_id", "plan_digest"}}
            value["plan_digest"] = sha256_canonical_json(unsigned)
            value["plan_id"] = f"plan:{value['plan_digest'][:24]}"
            path.write_text(json.dumps(value))

            loaded = load_batch_plan(path)

            self.assertEqual("", loaded.targets[0].database_fingerprint)
            self.assertTrue(loaded.verify_digest())

    def test_tampered_plan_and_unsafe_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = build_batch_plan(self._corpus(1), run_id="run", mode="plan")
            path, _ = publish_batch_plan(plan, root)
            value = json.loads(path.read_text())
            value["run_id"] = "other"
            path.write_text(json.dumps(value))
            with self.assertRaises(AnalyzerError):
                load_batch_plan(path)
            with self.assertRaises(AnalyzerError):
                resolve_repo_relative(root, "../outside")


if __name__ == "__main__":
    unittest.main()
