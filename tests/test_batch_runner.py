from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.batch.models import BatchPlan, BatchTargetPlan, TargetCapability, TargetIdentity
from dosweb.batch.runner import BatchRunner, run_batch
from dosweb.batch.state import batch_lock
from dosweb.errors import AnalyzerError


class _Pipeline:
    def __init__(self, values: dict[str, object], calls: list[dict[str, object]], *, fail: bool = False, gate: threading.Barrier | None = None) -> None:
        self.values, self.calls, self.fail, self.gate = values, calls, fail, gate

    def run(self, command: str) -> dict[str, str]:
        if self.gate is not None:
            self.gate.wait(timeout=2)
        self.calls.append({**self.values, "run_command": command})
        if self.fail:
            raise RuntimeError("secret detail must not persist")
        return {"status": "completed"}


def _plan(mode: str = "entries", count: int = 2, *, paused_last: bool = False) -> BatchPlan:
    targets = []
    for index in range(1, count + 1):
        identity = TargetIdentity(index, f"owner/repo{index}", "git-commit", f"{index:040x}", f"sources/repo{index}", f"db/repo{index}")
        capability = TargetCapability(True, f"https://github.com/{identity.name}", "git-commit")
        initial = "paused" if paused_last and index == count else "queued"
        targets.append(BatchTargetPlan(identity, f"batch/targets/{index:03d}-{identity.slug}", capability, initial, identity.identity_id))
    provider = {"allow_remote_llm": mode == "full"}
    unsigned = {
        "schema_version": 1, "tool_version": "test", "batch_schema_version": "test-v1",
        "run_id": "run", "mode": mode, "output_root": "batch", "inventory_digest": "a" * 64,
        "provider": provider, "targets": [target.to_dict() for target in targets],
    }
    digest = sha256_canonical_json(unsigned)
    return BatchPlan(1, "test", "test-v1", "run", mode, "batch", "a" * 64, tuple(targets), f"plan:{digest[:24]}", digest, provider)


class BatchRunnerTests(unittest.TestCase):
    def _tree(self, root: Path, plan: BatchPlan) -> None:
        for target in plan.targets:
            (root / target.identity.source_path).mkdir(parents=True)
            (root / target.identity.database_path).mkdir(parents=True)

    def test_entries_strip_provider_auth_and_use_absolute_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan); calls = []
            factory = lambda values, environ: _Pipeline(dict(values), calls)
            state = run_batch(plan, root / "out", pipeline_factory=factory, repo_root=root, environ={"DEEPSEEK_API_KEY": "secret"}, clock=lambda: "2026-01-01T00:00:00+00:00")
            self.assertEqual(state["status"], "completed")
            self.assertEqual(calls[0]["run_command"], "entries")
            self.assertFalse(calls[0]["allow_remote_llm"])
            self.assertTrue(Path(calls[0]["database"]).is_absolute())
            self.assertTrue((root / "out" / "batch_status.jsonl").is_file())

    def test_full_requires_auth_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            with self.assertRaises(AnalyzerError) as raised:
                run_batch(_plan("full", 1), output, pipeline_factory=lambda values: None, environ={})
            self.assertEqual(raised.exception.code, "BATCH_REMOTE_LLM_NOT_AUTHORIZED")
            self.assertFalse(output.exists())

    def test_failure_isolated_and_error_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=2); self._tree(root, plan); calls = []
            def factory(values, environ):
                return _Pipeline(dict(values), calls, fail=str(values["database"]).endswith("repo1"))
            state = run_batch(plan, root / "out", pipeline_factory=factory, repo_root=root, environ={})
            records = state["targets"]
            self.assertEqual(records[plan.targets[0].target_id]["state"], "failed")
            self.assertEqual(records[plan.targets[1].target_id]["state"], "completed")
            serialized = json.dumps(state)
            self.assertNotIn("secret detail", serialized)

    def test_resume_skips_completed_and_retry_failed_reexecutes_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan); calls = []
            run_batch(plan, root / "out", pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls, fail=True), repo_root=root, environ={})
            run_batch(plan, root / "out", pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls), repo_root=root, environ={}, retry_failed=False)
            self.assertEqual(len(calls), 1)
            state = run_batch(plan, root / "out", pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls), repo_root=root, environ={}, retry_failed=True)
            self.assertEqual(len(calls), 2)
            self.assertEqual(state["status"], "completed")

    def test_retry_failed_only_retries_transient_error_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan); calls = []
            class AuthFailure:
                def run(self, _command: str) -> dict[str, str]:
                    raise AnalyzerError("BATCH_REMOTE_LLM_NOT_AUTHORIZED", "credentials")
            run_batch(plan, root / "out", pipeline_factory=lambda values, environ: AuthFailure(), repo_root=root, environ={})
            state = run_batch(plan, root / "out", pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls), repo_root=root, environ={}, retry_failed=True)
            self.assertEqual(state["status"], "completed_with_failures")
            self.assertEqual(calls, [])

    def test_batch_lock_excludes_concurrent_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan); output = root / "out"
            output.mkdir()
            with batch_lock(output / ".batch.lock"):
                with self.assertRaises(AnalyzerError) as raised:
                    run_batch(plan, output, pipeline_factory=lambda values, environ: _Pipeline(dict(values), []), repo_root=root, environ={})
            self.assertEqual(raised.exception.code, "BATCH_LOCKED")

    def test_paused_tree_sha_is_not_scheduled_in_full(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan("full", 2, paused_last=True); self._tree(root, plan); calls = []
            state = run_batch(plan, root / "out", pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls), repo_root=root, environ={"DEEPSEEK_API_KEY": "x"})
            self.assertEqual(len(calls), 1)
            self.assertEqual(state["targets"][plan.targets[-1].target_id]["state"], "paused")
            self.assertEqual(state["status"], "completed_with_gaps")

    def test_rejects_mismatched_existing_target_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan)
            output = root / "out" / "targets" / f"001-{plan.targets[0].identity.slug}"
            output.mkdir(parents=True); (output / "batch_target.json").write_text("{}\n")
            state = run_batch(plan, root / "out", pipeline_factory=lambda values, environ: _Pipeline(dict(values), []), repo_root=root, environ={})
            record = state["targets"][plan.targets[0].target_id]
            self.assertEqual(record["error_code"], "BATCH_TARGET_IDENTITY_MISMATCH")

    def test_pipeline_must_report_completed_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan)
            class IncompletePipeline:
                def run(self, _command: str) -> dict[str, str]:
                    return {"status": "failed"}
            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: IncompletePipeline(),
                repo_root=root,
                environ={},
            )
            record = state["targets"][plan.targets[0].target_id]
            self.assertEqual(record["error_code"], "BATCH_PIPELINE_INCOMPLETE")

    def test_resume_rejects_invalid_target_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan)
            output = root / "out"
            state = run_batch(
                plan,
                output,
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), []),
                repo_root=root,
                environ={},
            )
            state["targets"][plan.targets[0].target_id]["state"] = "completed"
            state["targets"][plan.targets[0].target_id]["target_id"] = "target:forged"
            (output / "batch_state.json").write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                run_batch(
                    plan,
                    output,
                    pipeline_factory=lambda values, environ: _Pipeline(dict(values), []),
                    repo_root=root,
                    environ={},
                )
            self.assertEqual(raised.exception.code, "BATCH_STATE_INVALID")

    def test_concurrency_is_bounded_to_five(self) -> None:
        with self.assertRaises(AnalyzerError):
            BatchRunner(_plan(count=1), "out", pipeline_factory=lambda values: None, max_workers=6)


if __name__ == "__main__":
    unittest.main()
