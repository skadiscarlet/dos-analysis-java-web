from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dosweb.batch.corpus import load_canonical_corpus
from dosweb.codeql.database import DatabaseInfo

from dosweb.batch.models import CanonicalCorpus, CorpusTarget, TargetCapability, TargetIdentity

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUN = load_script("run_java_web_dos_batch_cli", "run_java_web_dos_batch.py")
AGG = load_script("aggregate_java_web_dos_batch_cli", "aggregate_java_web_dos_batch.py")


class BatchCliTests(unittest.TestCase):
    def corpus(self, total: int = 200) -> CanonicalCorpus:
        targets = []
        for index in range(1, total + 1):
            identity = TargetIdentity(
                index, f"owner{index}/repo{index}", "git-commit", f"{index:040x}",
                f"sources/{index}", f"databases/{index}",
            )
            targets.append(CorpusTarget(
                identity, Path(identity.source_path), Path(identity.database_path),
                TargetCapability(True, f"https://github.com/{identity.name}", "git-commit"),
                f"{index:064x}",
            ))
        return CanonicalCorpus(1, "canonical", "java-web-200", total, "a" * 64, tuple(targets), Path("local.json"))

    def test_full_plan_only_builds_canonical_200_without_key_or_pipeline(self) -> None:
        manifest = ROOT / "intel/applications/java_web_200_targets.json"
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        fingerprint_by_source = {
            (ROOT / row["source_path"]).resolve(): (row["fingerprint_type"], row["checkout_fingerprint"])
            for row in raw["projects"]
        }
        source_by_database = {
            (ROOT / row["codeql_path"]).resolve(): (ROOT / row["source_path"]).resolve()
            for row in raw["projects"]
        }

        def lightweight_fingerprint(source: Path):
            return fingerprint_by_source[source.resolve()]

        def lightweight_database(database: Path):
            source = source_by_database[database.resolve()]
            return DatabaseInfo(database, source, "d" * 64)

        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "dosweb.batch.corpus._fingerprint", side_effect=lightweight_fingerprint
        ):
            output = Path(tmp) / "batch"
            called = False

            def forbidden_factory(*args, **kwargs):
                nonlocal called
                called = True
                raise AssertionError("plan-only mode must not construct a pipeline")

            status = RUN.main(
                [
                    "full", "--plan-only", "--run-id", "canonical-200",
                    "--output", str(output), "--allow-remote-llm",
                    "--model", "deepseek-v4-flash", "--base-url", "https://example.invalid/",
                    "--timeout-seconds", "17", "--max-retries", "2", "--temperature", "0.2",
                    "--cache-dir", str(output / "cache"), "--codeql-binary", "codeql-local",
                ],
                corpus_loader=lambda path, **kwargs: load_canonical_corpus(
                    path, database_validator=lightweight_database, **kwargs
                ),
                pipeline_factory=forbidden_factory,
                environ={},
            )
            self.assertEqual(0, status)
            self.assertFalse(called)
            plan = json.loads((output / "batch_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(200, len(plan["targets"]))
            self.assertEqual("deepseek-v4-flash", plan["provider"]["model"])
            self.assertEqual("codeql-local", plan["provider"]["codeql_binary"])
            self.assertNotIn("DEEPSEEK_API_KEY", json.dumps(plan))

    def test_full_plan_only_cannot_gain_late_remote_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "batch"
            plan = output / "batch_plan.json"
            status = RUN.main(
                ["full", "--plan-only", "--run-id", "full", "--output", str(output)],
                corpus_loader=lambda *args, **kwargs: self.corpus(1), environ={},
            )
            self.assertEqual(status, 0)
            status = RUN.main(
                ["full", "--plan", str(plan), "--output", str(output), "--allow-remote-llm"],
                corpus_loader=lambda *args, **kwargs: self.corpus(1), environ={"DEEPSEEK_API_KEY": "secret"},
                pipeline_factory=lambda values, environ: None,
            )
            self.assertNotEqual(status, 0)

    def test_external_plan_execution_publishes_self_contained_p0_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "plans"
            output = root / "archive"
            status = RUN.main(
                ["entries", "--plan-only", "--run-id", "entries", "--output", str(plan_dir)],
                corpus_loader=lambda *args, **kwargs: self.corpus(1), environ={},
            )
            self.assertEqual(status, 0)

            class Pipeline:
                def __init__(self, values):
                    self.values = values

                def run(self, _command):
                    output_dir = Path(self.values["output"])
                    (output_dir / "run.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
                    return {"status": "completed"}

            status = RUN.main(
                ["entries", "--plan", str(plan_dir / "batch_plan.json"), "--output", str(output)],
                pipeline_factory=lambda values, environ: Pipeline(values), environ={},
            )
            self.assertEqual(status, 0)
            self.assertTrue((output / "batch_plan.json").is_file())
            self.assertTrue((output / "manifest.normalized.jsonl").is_file())
            self.assertTrue((output / "batch_state.json").is_file())
            plan = json.loads((output / "batch_plan.json").read_text(encoding="utf-8"))
            manifest = [json.loads(line) for line in (output / "manifest.normalized.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(plan["targets"], manifest)
            self.assertNotIn("DEEPSEEK_API_KEY", json.dumps(plan))

    def test_external_plan_execution_rejects_conflicting_archive_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "plans"
            output = root / "archive"
            self.assertEqual(RUN.main(
                ["entries", "--plan-only", "--run-id", "entries", "--output", str(plan_dir)],
                corpus_loader=lambda *args, **kwargs: self.corpus(1), environ={},
            ), 0)
            output.mkdir()
            conflict = output / "batch_plan.json"
            conflict.write_text("{}\n", encoding="utf-8")
            status = RUN.main(
                ["entries", "--plan", str(plan_dir / "batch_plan.json"), "--output", str(output)],
                pipeline_factory=lambda values, environ: None, environ={},
            )
            self.assertNotEqual(status, 0)
            self.assertEqual(conflict.read_text(encoding="utf-8"), "{}\n")
            self.assertFalse((output / "batch_state.json").exists())

    def test_full_execution_requires_authorization_and_key_but_plan_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "batch"
            status = RUN.main(
                ["full", "--run-id", "full", "--output", str(output)],
                corpus_loader=lambda *args, **kwargs: self.corpus(1), environ={},
            )
            self.assertNotEqual(0, status)
            self.assertFalse((output / "batch_plan.json").exists())


class AggregationCliTests(unittest.TestCase):
    def test_ambiguous_manifest_requires_explicit_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.normalized.jsonl").write_text(
                json.dumps({"target_id": "target:1", "identity": {"name": "owner/repo", "slug": "owner__repo"}}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                AGG.main(["--batch-root", str(root)])


if __name__ == "__main__":
    unittest.main()
