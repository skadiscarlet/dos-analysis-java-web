from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.batch.models import BatchPlan, BatchTargetPlan, TargetCapability, TargetIdentity
from dosweb.batch.runner import BatchRunner, run_batch
from dosweb.batch.state import batch_lock
from dosweb.codeql.database import DatabaseInfo
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
        output = self.values.get("output")
        if isinstance(output, Path):
            (output / "run.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
        return {"status": "completed"}


def _plan(
    mode: str = "entries",
    count: int = 2,
    *,
    paused_last: bool = False,
    database_fingerprint: str = "",
) -> BatchPlan:
    targets = []
    for index in range(1, count + 1):
        identity = TargetIdentity(index, f"owner/repo{index}", "git-commit", f"{index:040x}", f"sources/repo{index}", f"db/repo{index}")
        capability = TargetCapability(True, f"https://github.com/{identity.name}", "git-commit")
        initial = "paused" if paused_last and index == count else "queued"
        targets.append(BatchTargetPlan(
            identity,
            f"batch/targets/{index:03d}-{identity.slug}",
            capability,
            initial,
            identity.identity_id,
            database_fingerprint,
        ))
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
            with mock.patch("dosweb.batch.runner._DEFAULT_SECRETS_PATH", Path(directory) / "absent-secrets.json"):
                with self.assertRaises(AnalyzerError) as raised:
                    run_batch(_plan("full", 1), output, pipeline_factory=lambda values: None, environ={})
            self.assertEqual(raised.exception.code, "BATCH_REMOTE_LLM_NOT_AUTHORIZED")
            self.assertFalse(output.exists())

    def test_database_binding_is_revalidated_before_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fingerprint = "b" * 64
            plan = _plan(count=1, database_fingerprint=fingerprint)
            self._tree(root, plan)
            calls: list[dict[str, object]] = []
            events: list[str] = []

            def validator(database: Path) -> DatabaseInfo:
                events.append("validated")
                return DatabaseInfo(
                    database.resolve(),
                    (root / plan.targets[0].identity.source_path).resolve(),
                    fingerprint,
                )

            def factory(values, environ):
                events.append("pipeline")
                return _Pipeline(dict(values), calls)

            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=factory,
                repo_root=root,
                environ={},
                database_validator=validator,
            )

            self.assertEqual("completed", state["status"])
            self.assertEqual(["validated", "pipeline"], events)

    def test_database_fingerprint_drift_fails_before_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan(count=1, database_fingerprint="b" * 64)
            self._tree(root, plan)
            pipeline_calls: list[dict[str, object]] = []

            def validator(database: Path) -> DatabaseInfo:
                return DatabaseInfo(
                    database.resolve(),
                    (root / plan.targets[0].identity.source_path).resolve(),
                    "c" * 64,
                )

            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), pipeline_calls),
                repo_root=root,
                environ={},
                database_validator=validator,
            )

            record = state["targets"][plan.targets[0].target_id]
            self.assertEqual("BATCH_DATABASE_FINGERPRINT_MISMATCH", record["error_code"])
            self.assertEqual([], pipeline_calls)

    def test_database_source_root_drift_fails_before_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fingerprint = "b" * 64
            plan = _plan(count=1, database_fingerprint=fingerprint)
            self._tree(root, plan)
            other = root / "sources" / "other"
            other.mkdir(parents=True)
            pipeline_calls: list[dict[str, object]] = []

            def validator(database: Path) -> DatabaseInfo:
                return DatabaseInfo(database.resolve(), other.resolve(), fingerprint)

            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), pipeline_calls),
                repo_root=root,
                environ={},
                database_validator=validator,
            )

            record = state["targets"][plan.targets[0].target_id]
            self.assertEqual("BATCH_DATABASE_SOURCE_ROOT_MISMATCH", record["error_code"])
            self.assertEqual([], pipeline_calls)

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

    def test_refresh_completed_reenters_target_with_pipeline_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan); calls = []
            first = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                repo_root=root,
                environ={},
            )
            second = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                repo_root=root,
                environ={},
                refresh_completed=True,
                max_attempts=3,
            )
            record = second["targets"][plan.targets[0].target_id]
            self.assertEqual(first["targets"][plan.targets[0].target_id]["attempt"], 1)
            self.assertEqual(record["attempt"], 2)
            self.assertEqual(len(calls), 2)
            self.assertEqual(second["status"], "completed")

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

    def test_retry_failed_reexecutes_nondeterministic_provider_output_failures(self) -> None:
        for error_code in (
            "LLM_AUTHENTICATION_FAILED",
            "LLM_NETWORK_FAILED",
            "LLM_RESPONSE_INVALID",
            "LLM_RESPONSE_SCHEMA_INVALID",
            "LLM_RESPONSE_SENSITIVE_CONTENT",
        ):
            with self.subTest(error_code=error_code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); plan = _plan(count=1); self._tree(root, plan); calls = []

                class ProviderFailure:
                    def run(self, _command: str) -> dict[str, str]:
                        raise AnalyzerError(error_code, "provider output rejected")

                run_batch(
                    plan,
                    root / "out",
                    pipeline_factory=lambda values, environ: ProviderFailure(),
                    repo_root=root,
                    environ={},
                )
                state = run_batch(
                    plan,
                    root / "out",
                    pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                    repo_root=root,
                    environ={},
                    retry_failed=True,
                )
                self.assertEqual(state["status"], "completed")
                self.assertEqual(len(calls), 1)

    def test_retry_failed_reexecutes_execution_snapshot_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan); calls = []

            class SnapshotFailure:
                def run(self, _command: str) -> dict[str, str]:
                    raise AnalyzerError(
                        "CODEQL_EXECUTION_SNAPSHOT_FAILED",
                        "private snapshot validation failed",
                    )

            run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: SnapshotFailure(),
                repo_root=root,
                environ={},
            )
            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                repo_root=root,
                environ={},
                retry_failed=True,
            )
            self.assertEqual(state["status"], "completed")
            self.assertEqual(len(calls), 1)

    def test_retry_failed_rechecks_restored_plan_database_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1, database_fingerprint="b" * 64); self._tree(root, plan); calls = []
            validations = 0

            def validator(_database: Path) -> DatabaseInfo:
                nonlocal validations
                validations += 1
                target = plan.targets[0]
                fingerprint = (
                    "f" * 64 if validations == 1 else target.database_fingerprint
                )
                return DatabaseInfo(
                    path=root / target.identity.database_path,
                    source_root=root / target.identity.source_path,
                    fingerprint=fingerprint,
                )

            first = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                repo_root=root,
                environ={},
                database_validator=validator,
            )
            record = first["targets"][plan.targets[0].target_id]
            self.assertEqual(record["error_code"], "BATCH_DATABASE_FINGERPRINT_MISMATCH")
            self.assertEqual(calls, [])

            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                repo_root=root,
                environ={},
                database_validator=validator,
                retry_failed=True,
            )
            self.assertEqual(state["status"], "completed")
            self.assertEqual(len(calls), 1)

    def test_retry_failed_only_retries_structured_query_publication_cleanup(self) -> None:
        for diagnostic, expected_calls in (
            ("generation directory release failed", 1),
            ("selected query execution failed", 0),
        ):
            with self.subTest(diagnostic=diagnostic), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); plan = _plan(count=1); self._tree(root, plan); calls = []

                class QueryFailure:
                    def __init__(self, values: dict[str, object]) -> None:
                        self.values = values

                    def run(self, _command: str) -> dict[str, str]:
                        output = self.values["output"]
                        assert isinstance(output, Path)
                        (output / "run.json").write_text(
                            json.dumps(
                                {
                                    "status": "failed",
                                    "error": {
                                        "code": "CODEQL_QUERY_FAILED",
                                        "message": "CodeQL query execution failed.",
                                        "details": {
                                            "stage": "publication",
                                            "diagnostic": diagnostic,
                                        },
                                    },
                                }
                            ),
                            encoding="utf-8",
                        )
                        raise AnalyzerError(
                            "CODEQL_QUERY_FAILED",
                            "CodeQL query execution failed.",
                        )

                run_batch(
                    plan,
                    root / "out",
                    pipeline_factory=lambda values, environ: QueryFailure(dict(values)),
                    repo_root=root,
                    environ={},
                )
                state = run_batch(
                    plan,
                    root / "out",
                    pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                    repo_root=root,
                    environ={},
                    retry_failed=True,
                )
                self.assertEqual(len(calls), expected_calls)
                self.assertEqual(
                    state["status"],
                    "completed" if expected_calls else "completed_with_failures",
                )

    def test_retry_failed_reexecutes_provider_failure_within_one_fresh_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan(count=1)
            self._tree(root, plan)
            calls: list[str] = []

            class FlakyProvider:
                def __init__(self, values: dict[str, object]) -> None:
                    self.values = values

                def run(self, command: str) -> dict[str, str]:
                    calls.append(command)
                    if len(calls) == 1:
                        raise AnalyzerError(
                            "LLM_RESPONSE_INVALID",
                            "provider output rejected",
                        )
                    output = self.values["output"]
                    assert isinstance(output, Path)
                    (output / "run.json").write_text(
                        json.dumps({"status": "completed"}),
                        encoding="utf-8",
                    )
                    return {"status": "completed"}

            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: FlakyProvider(dict(values)),
                repo_root=root,
                environ={},
                resume=False,
                retry_failed=True,
                max_attempts=2,
            )

            record = state["targets"][plan.targets[0].target_id]
            self.assertEqual("completed", state["status"])
            self.assertEqual("completed", record["state"])
            self.assertEqual(2, record["attempt"])
            self.assertEqual(["entries", "entries"], calls)

    def test_fresh_provider_retry_stops_at_the_attempt_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan(count=1)
            self._tree(root, plan)
            calls: list[str] = []

            class AlwaysInvalidProvider:
                def run(self, command: str) -> dict[str, str]:
                    calls.append(command)
                    raise AnalyzerError(
                        "LLM_RESPONSE_SCHEMA_INVALID",
                        "provider output rejected",
                    )

            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: AlwaysInvalidProvider(),
                repo_root=root,
                environ={},
                resume=False,
                retry_failed=True,
                max_attempts=2,
            )

            record = state["targets"][plan.targets[0].target_id]
            self.assertEqual("completed_with_failures", state["status"])
            self.assertEqual("failed", record["state"])
            self.assertEqual(2, record["attempt"])
            self.assertEqual(["entries", "entries"], calls)

    def test_batch_lock_excludes_concurrent_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan); output = root / "out"
            output.mkdir()
            with batch_lock(output / ".batch.lock"):
                with self.assertRaises(AnalyzerError) as raised:
                    run_batch(plan, output, pipeline_factory=lambda values, environ: _Pipeline(dict(values), []), repo_root=root, environ={})
            self.assertEqual(raised.exception.code, "BATCH_LOCKED")

    def test_full_mode_passes_separate_analysis_and_provider_checkouts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_plan = _plan("full", 1)
            capability = replace(
                base_plan.targets[0].capability,
                provider_source_path="provider/repo1",
                provider_source_commit="f" * 40,
            )
            target = replace(base_plan.targets[0], capability=capability)
            unsigned = {**base_plan.unsigned_dict(), "targets": [target.to_dict()]}
            digest = sha256_canonical_json(unsigned)
            plan = replace(base_plan, targets=(target,), plan_id=f"plan:{digest[:24]}", plan_digest=digest)
            self._tree(root, plan)
            provider = root / "provider" / "repo1"
            provider.mkdir(parents=True)
            calls: list[dict[str, object]] = []

            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                repo_root=root,
                environ={"DEEPSEEK_API_KEY": "x"},
            )
            self.assertEqual(state["status"], "completed")
            self.assertEqual(calls[0]["analysis_source_root"], root / target.identity.source_path)
            self.assertEqual(calls[0]["source_checkout"], provider)

    def test_full_mode_invalid_query_failure_policy_stops_before_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_plan = _plan("full", 1)
            plan = replace(base_plan, analysis_mode="formal", query_failure_policy="coverage_gap")
            unsigned = plan.unsigned_dict()
            digest = sha256_canonical_json(unsigned)
            plan = replace(plan, plan_id=f"plan:{digest[:24]}", plan_digest=digest)
            self._tree(root, plan)
            pipeline_calls: list[dict[str, object]] = []
            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), pipeline_calls),
                repo_root=root,
                environ={"DEEPSEEK_API_KEY": "x"},
            )
            record = state["targets"][plan.targets[0].target_id]
            self.assertEqual(record["error_code"], "BATCH_PLAN_INVALID")
            self.assertEqual(pipeline_calls, [])

    def test_paused_target_is_not_scheduled_in_full(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan("full", 2, paused_last=True); self._tree(root, plan); calls = []
            state = run_batch(plan, root / "out", pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls), repo_root=root, environ={"DEEPSEEK_API_KEY": "x"})
            self.assertEqual(len(calls), 1)
            self.assertEqual(state["targets"][plan.targets[-1].target_id]["state"], "paused")
            self.assertEqual(state["status"], "completed_with_gaps")

    def test_full_mode_tree_sha_target_uses_local_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan("full", 1)
            identity = replace(plan.targets[0].identity, fingerprint_type="tree-sha256", fingerprint="a" * 64)
            capability = replace(plan.targets[0].capability, provider_eligible=True, public_source_url=None, provider_source_commit=None)
            target = replace(plan.targets[0], identity=identity, capability=capability)
            unsigned = {**plan.unsigned_dict(), "targets": [target.to_dict()]}
            digest = sha256_canonical_json(unsigned)
            plan = replace(plan, targets=(target,), plan_id=f"plan:{digest[:24]}", plan_digest=digest)
            self._tree(root, plan)
            calls: list[dict[str, object]] = []

            state = run_batch(
                plan,
                root / "out",
                pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls),
                repo_root=root,
                environ={"DEEPSEEK_API_KEY": "x"},
            )
            self.assertEqual(state["status"], "completed")
            self.assertIsNone(calls[0]["source_commit_sha"])

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

    def test_explicit_six_attempt_extension_is_bounded_at_sixteen(self) -> None:
        runner = BatchRunner(
            _plan(count=1),
            "out",
            pipeline_factory=lambda values: None,
            max_attempts=16,
        )
        self.assertEqual(runner.max_attempts, 16)
        with self.assertRaises(AnalyzerError) as raised:
            BatchRunner(
                _plan(count=1),
                "out",
                pipeline_factory=lambda values: None,
                max_attempts=17,
            )
        self.assertEqual(raised.exception.code, "BATCH_RETRY_INVALID")

    def test_completed_target_missing_artifacts_becomes_gap_at_attempt_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan)
            output = root / "out"
            class NoArtifacts:
                def run(self, _command: str) -> dict[str, str]:
                    return {"status": "completed"}
            state = run_batch(plan, output, pipeline_factory=lambda values, environ: NoArtifacts(), repo_root=root, environ={}, max_attempts=2)
            state = run_batch(plan, output, pipeline_factory=lambda values, environ: NoArtifacts(), repo_root=root, environ={}, max_attempts=2)
            record = state["targets"][plan.targets[0].target_id]
            self.assertEqual(record["state"], "completed_with_gaps")
            self.assertEqual(state["status"], "completed_with_gaps")

    def test_target_output_setup_error_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=2); self._tree(root, plan)
            output = root / "out"
            blocked = output / "targets" / f"001-{plan.targets[0].identity.slug}"
            blocked.parent.mkdir(parents=True)
            blocked.write_text("not a directory", encoding="utf-8")
            state = run_batch(plan, output, pipeline_factory=lambda values, environ: _Pipeline(dict(values), []), repo_root=root, environ={})
            self.assertEqual(state["targets"][plan.targets[0].target_id]["state"], "failed")
            self.assertEqual(state["targets"][plan.targets[1].target_id]["state"], "completed")
            self.assertEqual(state["status"], "completed_with_failures")

    def test_exhausted_llm_retries_are_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(count=1); self._tree(root, plan); calls = []
            class Exhausted:
                def run(self, _command: str) -> dict[str, str]:
                    raise AnalyzerError("LLM_RETRIES_EXHAUSTED", "transient")
            run_batch(plan, root / "out", pipeline_factory=lambda values, environ: Exhausted(), repo_root=root, environ={})
            state = run_batch(plan, root / "out", pipeline_factory=lambda values, environ: _Pipeline(dict(values), calls), repo_root=root, environ={}, retry_failed=True)
            self.assertEqual(state["status"], "completed")
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
