from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from dosweb.artifacts.identifiers import canonical_json
from dosweb.artifacts.metadata import read_upstream_artifact_bytes, resolve_upstream_artifact
import dosweb.artifacts.metadata as metadata_module
from dosweb.cli import dispatch, main, parse_cli_values
from dosweb.errors import AnalyzerError
from dosweb.pipeline import Pipeline, SCHEMA_VERSION, TOOL_VERSION, StageOutput, STAGES, StageFingerprint


class PipelineRecoveryTests(unittest.TestCase):
    def _executors(self, calls: dict[str, int], *, fail: str | None = None):
        def make(stage: str):
            def execute(context):
                calls[stage] += 1
                if stage == fail:
                    raise AnalyzerError("LLM_LOCAL_FAILURE", "local fake failure")
                return StageOutput(
                    {
                        f"{stage}.jsonl": [{"stage": stage, "sequence": calls[stage]}],
                    },
                    {"local_only": True},
                )

            return execute

        return {stage: make(stage) for stage in STAGES}

    def test_finalizer_runs_once_before_completed_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observed_statuses: list[str] = []

            def finalizer() -> None:
                observed_statuses.append(
                    json.loads((root / "run.json").read_text(encoding="utf-8"))["status"]
                )

            result = Pipeline(
                root,
                self._executors({stage: 0 for stage in STAGES}),
                finalizer=finalizer,
            ).run("entries")
            self.assertEqual(observed_statuses, ["running"])
            self.assertEqual(result["status"], "completed")

    def test_finalizer_runs_on_stage_failure_and_failure_overrides_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = 0

            def failing_finalizer() -> None:
                nonlocal calls
                calls += 1
                raise AnalyzerError(
                    "CODEQL_EXECUTION_SNAPSHOT_FAILED",
                    "Private CodeQL execution database snapshot failed.",
                    {"stage": "cleanup", "reason": "UNSAFE_OR_UNREMOVABLE"},
                )

            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(
                    root,
                    self._executors({stage: 0 for stage in STAGES}),
                    finalizer=failing_finalizer,
                ).run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_EXECUTION_SNAPSHOT_FAILED")
            self.assertEqual(calls, 1)
            persisted = json.loads((root / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(
                persisted["error"]["code"], "CODEQL_EXECUTION_SNAPSHOT_FAILED"
            )

            cleanup_calls = 0

            def successful_finalizer() -> None:
                nonlocal cleanup_calls
                cleanup_calls += 1

            with self.assertRaises(AnalyzerError) as stage_raised:
                Pipeline(
                    root / "stage-failure",
                    self._executors(
                        {stage: 0 for stage in STAGES}, fail="entries"
                    ),
                    finalizer=successful_finalizer,
                ).run("entries")
            self.assertEqual(stage_raised.exception.code, "LLM_LOCAL_FAILURE")
            self.assertEqual(cleanup_calls, 1)

    def test_finalizer_keyboard_interrupt_persists_path_free_failed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_marker = str(root / ".codeql-execution-private")

            def interrupted_finalizer() -> None:
                raise KeyboardInterrupt(private_marker)

            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(
                    root,
                    self._executors({stage: 0 for stage in STAGES}),
                    finalizer=interrupted_finalizer,
                ).run("entries")

            self.assertEqual(
                raised.exception.code,
                "ANALYSIS_FINALIZATION_FAILED",
            )
            self.assertEqual(
                raised.exception.details.get("error_type"),
                "KeyboardInterrupt",
            )
            self.assertNotIn(private_marker, repr(raised.exception.details))
            persisted_text = (root / "run.json").read_text(encoding="utf-8")
            self.assertNotIn(private_marker, persisted_text)
            persisted = json.loads(persisted_text)
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(
                persisted["error"]["code"],
                "ANALYSIS_FINALIZATION_FAILED",
            )

    def test_stage_failure_is_cause_of_system_exit_finalization_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_marker = str(root / ".codeql-execution-private")

            def interrupted_finalizer() -> None:
                raise SystemExit(private_marker)

            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(
                    root,
                    self._executors(
                        {stage: 0 for stage in STAGES}, fail="entries"
                    ),
                    finalizer=interrupted_finalizer,
                ).run("entries")

            self.assertEqual(
                raised.exception.code,
                "ANALYSIS_FINALIZATION_FAILED",
            )
            self.assertEqual(
                raised.exception.details.get("error_type"),
                "SystemExit",
            )
            self.assertIsInstance(raised.exception.__cause__, AnalyzerError)
            self.assertEqual(
                raised.exception.__cause__.code,
                "LLM_LOCAL_FAILURE",
            )
            self.assertNotIn(private_marker, repr(raised.exception.details))
            persisted_text = (root / "run.json").read_text(encoding="utf-8")
            self.assertNotIn(private_marker, persisted_text)
            persisted = json.loads(persisted_text)
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(
                persisted["error"]["code"],
                "ANALYSIS_FINALIZATION_FAILED",
            )
            self.assertEqual(
                persisted["stages"]["entries"]["status"],
                "failed",
            )

    def test_failure_write_base_exception_still_finalizes_and_repersists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage_marker = str(root / ".private-stage-interrupt")
            write_marker = str(root / ".private-failure-write")
            finalizer_calls = 0
            write_failure_injected = False

            def interrupted_stage(_context):
                raise KeyboardInterrupt(stage_marker)

            def finalizer() -> None:
                nonlocal finalizer_calls
                finalizer_calls += 1

            pipeline = Pipeline(
                root,
                {"entries": interrupted_stage},
                finalizer=finalizer,
            )
            real_write_run = pipeline._write_run  # noqa: SLF001

            def interrupt_first_failure_write() -> None:
                nonlocal write_failure_injected
                if (
                    pipeline._run.get("status") == "failed"  # noqa: SLF001
                    and not write_failure_injected
                ):
                    write_failure_injected = True
                    raise SystemExit(write_marker)
                real_write_run()

            with mock.patch.object(
                pipeline,
                "_write_run",
                side_effect=interrupt_first_failure_write,
            ):
                with self.assertRaises(SystemExit) as raised:
                    pipeline.run("entries")

            self.assertTrue(write_failure_injected)
            self.assertEqual(finalizer_calls, 1)
            self.assertEqual(str(raised.exception), write_marker)
            self.assertIsInstance(
                raised.exception.__cause__,
                KeyboardInterrupt,
            )
            persisted_text = (root / "run.json").read_text(encoding="utf-8")
            self.assertNotIn(stage_marker, persisted_text)
            self.assertNotIn(write_marker, persisted_text)
            persisted = json.loads(persisted_text)
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(
                persisted["error"],
                {
                    "code": "ANALYSIS_PIPELINE_FAILED",
                    "message": "Pipeline execution failed.",
                    "details": {"error_type": "KeyboardInterrupt"},
                },
            )

    def test_resume_preflight_failure_replaces_completed_run_transactionally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = {stage: 0 for stage in STAGES}
            completed = Pipeline(root, self._executors(calls)).run("entries")
            self.assertEqual(completed["status"], "completed")
            original_attempt = completed["attempt"]

            def unsafe_stale_preflight() -> None:
                raise AnalyzerError(
                    "CODEQL_EXECUTION_SNAPSHOT_FAILED",
                    "Private CodeQL execution database snapshot failed.",
                    {
                        "stage": "stale_cleanup",
                        "reason": "UNSAFE_OR_UNREMOVABLE",
                    },
                )

            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(
                    root,
                    self._executors({stage: 0 for stage in STAGES}),
                    resume=True,
                    preflight=unsafe_stale_preflight,
                ).run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_EXECUTION_SNAPSHOT_FAILED")
            persisted = json.loads((root / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(persisted["attempt"], original_attempt + 1)
            self.assertEqual(
                persisted["error"],
                {
                    "code": "CODEQL_EXECUTION_SNAPSHOT_FAILED",
                    "message": "Private CodeQL execution database snapshot failed.",
                    "details": {
                        "stage": "stale_cleanup",
                        "reason": "UNSAFE_OR_UNREMOVABLE",
                    },
                },
            )

    def test_cleanup_failure_overrides_stage_failure_and_keeps_stage_as_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def cleanup_failure() -> None:
                raise AnalyzerError(
                    "CODEQL_EXECUTION_SNAPSHOT_FAILED",
                    "Private CodeQL execution database snapshot failed.",
                    {"stage": "cleanup", "reason": "UNSAFE_OR_UNREMOVABLE"},
                )

            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(
                    root,
                    self._executors(
                        {stage: 0 for stage in STAGES}, fail="entries"
                    ),
                    finalizer=cleanup_failure,
                ).run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_EXECUTION_SNAPSHOT_FAILED")
            self.assertIsInstance(raised.exception.__cause__, AnalyzerError)
            self.assertEqual(raised.exception.__cause__.code, "LLM_LOCAL_FAILURE")
            persisted = json.loads((root / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(
                persisted["error"]["code"], "CODEQL_EXECUTION_SNAPSHOT_FAILED"
            )
            self.assertEqual(persisted["stages"]["entries"]["status"], "failed")

    def test_stage_order_and_exact_resume_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = {stage: 0 for stage in STAGES}
            Pipeline(tmp, self._executors(calls), database_fingerprint="db", model_fingerprint="model", report_fingerprint="report", config_fingerprint="cfg").run()
            self.assertEqual([calls[stage] for stage in STAGES], [1] * len(STAGES))
            Pipeline(tmp, self._executors(calls), database_fingerprint="db", model_fingerprint="model", report_fingerprint="report", config_fingerprint="cfg", resume=True).run()
            self.assertEqual([calls[stage] for stage in STAGES], [1] * len(STAGES))
            self.assertEqual(set(json.loads((Path(tmp) / "run.json").read_text())["stages"]), set(STAGES))

    def test_schema_27_reexecutes_every_schema_26_stage(self):
        self.assertEqual("2.7", SCHEMA_VERSION)
        self.assertEqual("0.6.0", TOOL_VERSION)
        with tempfile.TemporaryDirectory() as tmp:
            initial_calls = {stage: 0 for stage in STAGES}
            Pipeline(
                tmp,
                self._executors(initial_calls),
                schema_version="2.6",
                tool_version="0.5.0",
            ).run()
            resumed_calls = {stage: 0 for stage in STAGES}

            result = Pipeline(
                tmp,
                self._executors(resumed_calls),
                resume=True,
            ).run()

            self.assertEqual([1] * len(STAGES), [resumed_calls[stage] for stage in STAGES])
            self.assertEqual("2.7", result["schema_version"])
            self.assertEqual("0.6.0", result["tool_version"])
            for stage in STAGES:
                manifest = json.loads(
                    (Path(tmp) / ".stage-manifests" / f"{stage}.json").read_text(encoding="utf-8")
                )
                self.assertEqual("2.7", manifest["fingerprint"]["schema_version"])
                self.assertTrue(
                    all(artifact["schema_version"] == "2.7" for artifact in manifest["artifacts"])
                )

    def test_resume_updates_root_run_identity_and_records_prior_identity_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = {stage: 0 for stage in STAGES}
            Pipeline(
                tmp, self._executors(calls), run_identity={"analysis_mode": "exploratory_entries"},
            ).run("entries")
            Pipeline(
                tmp, self._executors(calls), resume=True,
                run_identity={"analysis_mode": "formal"},
                config_fingerprint="formal-config",
            ).run("entries")
            run = json.loads((Path(tmp) / "run.json").read_text(encoding="utf-8"))
            self.assertEqual({"analysis_mode": "formal"}, run["identity"])
            self.assertRegex(run["previous_identity_hash"], r"^[0-9a-f]{64}$")
            self.assertEqual(2, run["attempt"])

    def test_named_upstream_artifact_resolution_verifies_manifest_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = {stage: 0 for stage in STAGES}
            result = Pipeline(tmp, self._executors(calls)).run("entries")
            upstream = {"entries": result["stages"]["entries"]}
            path = resolve_upstream_artifact(
                Path(tmp),
                upstream,
                "entries",
                "entries.jsonl",
                schema_version=SCHEMA_VERSION,
            )
            self.assertEqual(path, Path(tmp) / "entries.jsonl")

    def test_authenticated_upstream_bytes_reject_replacement_between_validation_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = {stage: 0 for stage in STAGES}
            result = Pipeline(tmp, self._executors(calls)).run("entries")
            original = metadata_module._verify_upstream_file  # noqa: SLF001
            attempts = 0

            def replace_after_first(path: Path, **kwargs: object) -> bytes:
                nonlocal attempts
                attempts += 1
                payload = original(path, **kwargs)
                if attempts == 1:
                    path.write_text('{"tampered":true}\n', encoding="utf-8")
                return payload

            with mock.patch.object(metadata_module, "_verify_upstream_file", side_effect=replace_after_first):
                with self.assertRaises(AnalyzerError) as raised:
                    read_upstream_artifact_bytes(
                        Path(tmp), {"entries": result["stages"]["entries"]},
                        "entries", "entries.jsonl", schema_version=SCHEMA_VERSION,
                    )
            self.assertEqual("ARTIFACT_UPSTREAM_HASH_MISMATCH", raised.exception.code)

    def test_named_upstream_artifact_resolution_rejects_metadata_and_file_tampering(self):
        mutations = ("missing", "path", "hash", "count", "bytes", "file")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                calls = {stage: 0 for stage in STAGES}
                result = Pipeline(tmp, self._executors(calls)).run("entries")
                metadata = json.loads(json.dumps(result["stages"]["entries"]))
                artifacts = metadata["artifacts"]
                if mutation == "missing":
                    artifacts[0]["path"] = "other.jsonl"
                elif mutation == "path":
                    artifacts[0]["path"] = "../entries.jsonl"
                elif mutation == "hash":
                    artifacts[0]["sha256"] = "0" * 64
                elif mutation == "count":
                    artifacts[0]["record_count"] += 1
                elif mutation == "bytes":
                    artifacts[0]["byte_count"] += 1
                elif mutation == "file":
                    (Path(tmp) / "entries.jsonl").write_text("tampered\n", encoding="utf-8")
                metadata["output_hash"] = hashlib.sha256(canonical_json(artifacts)).hexdigest()
                with self.assertRaises(AnalyzerError) as raised:
                    resolve_upstream_artifact(
                        Path(tmp),
                        {"entries": metadata},
                        "entries",
                        "entries.jsonl",
                        schema_version=SCHEMA_VERSION,
                    )
                self.assertIn(
                    raised.exception.code,
                    {"ARTIFACT_UPSTREAM_MISSING", "ARTIFACT_UPSTREAM_INVALID", "ARTIFACT_UPSTREAM_HASH_MISMATCH"},
                )

    def test_named_upstream_artifact_schema_mismatch_has_stable_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = {stage: 0 for stage in STAGES}
            result = Pipeline(tmp, self._executors(calls)).run("entries")
            with self.assertRaises(AnalyzerError) as raised:
                resolve_upstream_artifact(Path(tmp), {"entries": result["stages"]["entries"]}, "entries", "entries.jsonl", schema_version="incompatible")
            self.assertEqual(raised.exception.code, "ARTIFACT_SCHEMA_MISMATCH")

    def test_failed_stage_publishes_no_partial_artifact_and_preserves_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = {stage: 0 for stage in STAGES}
            first = Pipeline(tmp, self._executors(calls), database_fingerprint="db", model_fingerprint="model", report_fingerprint="report")
            first.run("entries")
            complete = (Path(tmp) / "entries.jsonl").read_bytes()
            failing = Pipeline(tmp, self._executors(calls, fail="growth"), database_fingerprint="db", model_fingerprint="model", report_fingerprint="report", resume=True)
            with self.assertRaises(AnalyzerError) as raised:
                failing.run()
            self.assertEqual(raised.exception.code, "LLM_LOCAL_FAILURE")
            self.assertEqual((Path(tmp) / "entries.jsonl").read_bytes(), complete)
            self.assertFalse((Path(tmp) / "growth.jsonl").exists())
            run = json.loads((Path(tmp) / "run.json").read_text())
            self.assertEqual(run["status"], "failed")
            self.assertEqual(run["error"]["code"], "LLM_LOCAL_FAILURE")

    def test_codeql_failure_persists_only_bounded_actionable_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fail(_context):
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                    {
                        "stage": "query_run",
                        "diagnostic": "command deadline exceeded" + "x" * 3000,
                        "returncode": 124,
                        "query_path": "/secret/source/query.ql",
                    },
                )

            with self.assertRaises(AnalyzerError):
                Pipeline(tmp, {"entries": fail}).run("entries")

            run = json.loads((Path(tmp) / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["error"]["details"]["stage"], "query_run")
            self.assertEqual(run["error"]["details"]["returncode"], 124)
            self.assertLessEqual(len(run["error"]["details"]["diagnostic"]), 2048)
            self.assertNotIn("query_path", run["error"]["details"])
            self.assertEqual(run["stages"]["entries"]["details"], run["error"]["details"])

    def test_database_change_invalidates_every_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_calls = {stage: 0 for stage in STAGES}
            Pipeline(tmp, self._executors(first_calls), database_fingerprint="db-a", model_fingerprint="m", report_fingerprint="r", resume=False).run()
            calls = {stage: 0 for stage in STAGES}
            Pipeline(tmp, self._executors(calls), database_fingerprint="db-b", model_fingerprint="m", report_fingerprint="r", resume=True).run()
            self.assertEqual(calls, {stage: 1 for stage in STAGES})

    def test_model_change_reuses_entries_but_invalidates_growth_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_calls = {stage: 0 for stage in STAGES}
            Pipeline(tmp, self._executors(first_calls), database_fingerprint="db", model_fingerprint="m-a", report_fingerprint="r").run()
            calls = {stage: 0 for stage in STAGES}
            Pipeline(tmp, self._executors(calls), database_fingerprint="db", model_fingerprint="m-b", report_fingerprint="r", resume=True).run()
            self.assertEqual(calls["entries"], 0)
            self.assertEqual([calls[stage] for stage in STAGES[1:]], [1] * (len(STAGES) - 1))

    def test_report_change_invalidates_report_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_calls = {stage: 0 for stage in STAGES}
            Pipeline(tmp, self._executors(first_calls), database_fingerprint="db", model_fingerprint="m", report_fingerprint="r-a").run()
            calls = {stage: 0 for stage in STAGES}
            Pipeline(tmp, self._executors(calls), database_fingerprint="db", model_fingerprint="m", report_fingerprint="r-b", resume=True).run()
            self.assertEqual(calls, {stage: (1 if stage == "report" else 0) for stage in STAGES})

    def test_fingerprint_is_deterministic_and_order_independent(self):
        first = StageFingerprint(stage="growth", upstream_hashes={"entries": "a", "config": "b"}, database_fingerprint="db")
        second = StageFingerprint(stage="growth", upstream_hashes={"config": "b", "entries": "a"}, database_fingerprint="db")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.digest, second.digest)

    def test_resume_rejects_metadata_manifest_and_artifact_tampering(self):
        mutations = ("schema", "count", "manifest_missing", "manifest_content", "output_hash")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                calls = {stage: 0 for stage in STAGES}
                arguments = dict(database_fingerprint="db", model_fingerprint="m", report_fingerprint="r")
                Pipeline(tmp, self._executors(calls), **arguments).run("entries")
                root = Path(tmp)
                run = json.loads((root / "run.json").read_text())
                if mutation == "schema":
                    run["stages"]["entries"]["artifacts"][0]["schema_version"] = "wrong"
                    (root / "run.json").write_text(json.dumps(run))
                elif mutation == "count":
                    run["stages"]["entries"]["artifacts"][0]["record_count"] = 999
                    (root / "run.json").write_text(json.dumps(run))
                elif mutation == "manifest_missing":
                    (root / ".stage-manifests" / "entries.json").unlink()
                elif mutation == "manifest_content":
                    manifest = root / ".stage-manifests" / "entries.json"
                    value = json.loads(manifest.read_text())
                    value["metadata"] = {"tampered": True}
                    manifest.write_text(json.dumps(value))
                else:
                    run["stages"]["entries"]["output_hash"] = "0" * 64
                    (root / "run.json").write_text(json.dumps(run))
                resumed = {stage: 0 for stage in STAGES}
                Pipeline(tmp, self._executors(resumed), resume=True, **arguments).run("entries")
                self.assertEqual(resumed["entries"], 1)

    def test_resume_hashes_artifacts_streamingly(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = {stage: 0 for stage in STAGES}
            arguments = dict(database_fingerprint="db", model_fingerprint="m", report_fingerprint="r")
            Pipeline(tmp, self._executors(calls), **arguments).run("entries")
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("must stream")):
                resumed = {stage: 0 for stage in STAGES}
                Pipeline(tmp, self._executors(resumed), resume=True, **arguments).run("entries")
            self.assertEqual(resumed["entries"], 0)

    def test_payload_bounds_and_strict_canonical_records_fail_without_publication(self):
        invalid_payloads = (
            b"x" * (16 * 1024 * 1024 + 1),
            [{"value": float("nan")}],
            [{"value": index} for index in range(4097)],
        )
        for payload in invalid_payloads:
            with self.subTest(kind=type(payload).__name__), tempfile.TemporaryDirectory() as tmp:
                executor = {"entries": lambda _context, value=payload: StageOutput({"entries.jsonl": value})}
                with self.assertRaises(AnalyzerError):
                    Pipeline(tmp, executor).run("entries")
                self.assertFalse((Path(tmp) / "entries.jsonl").exists())

    def test_duplicate_normalized_paths_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = {"entries": lambda _context: StageOutput({"facts.jsonl": b"a\n", "./facts.jsonl": b"b\n"})}
            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(tmp, executor).run("entries")
            self.assertEqual(raised.exception.code, "ARTIFACT_DUPLICATE_PATH")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(link, {}).run("entries")
            self.assertEqual(raised.exception.code, "ARTIFACT_UNSAFE_OUTPUT_PATH")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "external"
            external.mkdir()
            output = root / "out"
            output.mkdir()
            (output / "nested").symlink_to(external, target_is_directory=True)
            executor = {"entries": lambda _context: StageOutput({"nested/facts.jsonl": b"a\n"})}
            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(output, executor).run("entries")
            self.assertEqual(raised.exception.code, "ARTIFACT_UNSAFE_OUTPUT_PATH")

    def test_failed_replacement_restores_old_artifacts_manifest_and_unrelated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = {"entries": lambda _context: StageOutput({"a.jsonl": b"old-a\n", "b.jsonl": b"old-b\n"})}
            Pipeline(root, first, database_fingerprint="a").run("entries")
            old_manifest = (root / ".stage-manifests" / "entries.json").read_bytes()
            unrelated = root / "unrelated.txt"
            unrelated.write_bytes(b"keep")
            second = {"entries": lambda _context: StageOutput({"a.jsonl": b"new-a\n", "c.jsonl": b"new-c\n"})}
            real_replace = os.replace

            def fail_on_second_artifact(source, destination):
                if Path(destination).name == "c.jsonl":
                    raise OSError("injected replace failure")
                return real_replace(source, destination)

            with mock.patch("dosweb.pipeline.os.replace", side_effect=fail_on_second_artifact):
                with self.assertRaises(AnalyzerError):
                    Pipeline(root, second, database_fingerprint="b", resume=True).run("entries")
            self.assertEqual((root / "a.jsonl").read_bytes(), b"old-a\n")
            self.assertEqual((root / "b.jsonl").read_bytes(), b"old-b\n")
            self.assertFalse((root / "c.jsonl").exists())
            self.assertEqual((root / ".stage-manifests" / "entries.json").read_bytes(), old_manifest)
            self.assertEqual(unrelated.read_bytes(), b"keep")

    def test_successful_replacement_removes_stale_stage_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Pipeline(root, {"entries": lambda _context: StageOutput({"old.jsonl": b"old\n", "keep.jsonl": b"v1\n"})}, database_fingerprint="a").run("entries")
            Pipeline(root, {"entries": lambda _context: StageOutput({"keep.jsonl": b"v2\n"})}, database_fingerprint="b", resume=True).run("entries")
            self.assertFalse((root / "old.jsonl").exists())
            self.assertEqual((root / "keep.jsonl").read_bytes(), b"v2\n")

    def test_non_resume_replacement_uses_prior_manifest_but_preserves_unknown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Pipeline(root, {"entries": lambda _context: StageOutput({"old.jsonl": b"old\n"})}, database_fingerprint="a").run("entries")
            unknown_file = root / "unknown.txt"
            unknown_file.write_bytes(b"keep")
            unknown_directory = root / "unknown-dir"
            unknown_directory.mkdir()
            (unknown_directory / "nested.txt").write_bytes(b"keep nested")

            Pipeline(root, {"entries": lambda _context: StageOutput({"new.jsonl": b"new\n"})}, database_fingerprint="b", resume=False).run("entries")

            self.assertFalse((root / "old.jsonl").exists())
            self.assertEqual((root / "new.jsonl").read_bytes(), b"new\n")
            self.assertEqual(unknown_file.read_bytes(), b"keep")
            self.assertEqual((unknown_directory / "nested.txt").read_bytes(), b"keep nested")

    def test_malformed_prior_manifest_does_not_authorize_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "unmanifested.jsonl"
            candidate.write_bytes(b"keep\n")
            manifests = root / ".stage-manifests"
            manifests.mkdir()
            (manifests / "entries.json").write_text("{malformed", encoding="utf-8")

            Pipeline(root, {"entries": lambda _context: StageOutput({"new.jsonl": b"new\n"})}, resume=False).run("entries")

            self.assertEqual(candidate.read_bytes(), b"keep\n")
            self.assertEqual((root / "new.jsonl").read_bytes(), b"new\n")

    def test_first_publication_failure_removes_new_stage_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor = {"entries": lambda _context: StageOutput({"entry.jsonl": b"new\n"})}
            real_replace = os.replace

            def fail_after_manifest(source, destination):
                result = real_replace(source, destination)
                if Path(destination).name == "entries.json":
                    raise OSError("manifest post-replace failure")
                return result

            with mock.patch("dosweb.pipeline.os.replace", side_effect=fail_after_manifest):
                with self.assertRaises(AnalyzerError):
                    Pipeline(root, executor).run("entries")
            self.assertFalse((root / "entry.jsonl").exists())
            self.assertFalse((root / ".stage-manifests" / "entries.json").exists())

    def test_resume_fails_closed_on_malformed_run_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(exist_ok=True)
            (root / "run.json").write_text("{malformed", encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                Pipeline(root, self._executors({stage: 0 for stage in STAGES}), resume=True).run("entries")
            self.assertEqual(raised.exception.code, "ARTIFACT_RUN_METADATA_INVALID")


class CliDispatchTests(unittest.TestCase):
    def test_parser_exposes_subcommands(self):
        self.assertEqual(parse_cli_values(["analyze", "--resume"])["command"], "analyze")
        self.assertEqual(parse_cli_values(["report"])["command"], "report")

    def test_injected_pipeline_receives_command_and_analyzer_errors_are_controlled(self):
        seen: list[str] = []

        class Fake:
            def run(self, command):
                seen.append(command)
                return {"status": "completed"}

        result = dispatch({"command": "entries"}, pipeline_factory=lambda _values: Fake())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(seen, ["entries"])
        self.assertEqual(main(["entries"], pipeline_factory=lambda _values: Fake()), 0)

    def test_keyword_only_factory_receives_values_and_environment_snapshot(self):
        seen: list[tuple[dict[str, object], dict[str, str]]] = []

        class Fake:
            def run(self, command):
                return {"status": "completed", "command": command}

        def factory(*, values, environ):
            seen.append((dict(values), dict(environ)))
            return Fake()

        with mock.patch.dict(os.environ, {"DOSWEB_TEST_ENV": "snapshot"}, clear=False):
            result = dispatch({"command": "entries"}, pipeline_factory=factory)
        self.assertEqual(result["command"], "entries")
        self.assertEqual(seen[0][0], {"command": "entries"})
        self.assertEqual(seen[0][1]["DOSWEB_TEST_ENV"], "snapshot")

    def test_main_returns_stable_status_for_invalid_arguments(self):
        with mock.patch("sys.stderr", new_callable=__import__("io").StringIO) as stderr:
            self.assertEqual(main(["unknown-command"]), 2)
        self.assertEqual(
            stderr.getvalue(),
            "CONFIG_INVALID_VALUE: Command-line arguments are invalid.\n",
        )

    def test_default_invocation_requires_production_paths_and_fails_closed_at_unwired_stage(self):
        self.assertEqual(main(["analyze"]), 2)
        with self.assertRaises(AnalyzerError) as raised:
            dispatch({"command": "analyze"})
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_VALUE")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "database"
            (database / "db-java").mkdir(parents=True)
            (database / "codeql-database.yml").write_text(
                f"sourceLocationPrefix: {root / 'source'}\n",
                encoding="utf-8",
            )
            (root / "source").mkdir()
            with mock.patch("dosweb.production._DEFAULT_SECRETS_PATH", root / "absent-secrets.json"):
                with self.assertRaises(AnalyzerError) as raised:
                    dispatch(
                        {
                            "command": "growth",
                            "database": database,
                            "output": root / "output",
                            "allow_remote_llm": True,
                        }
                    )
        self.assertEqual(raised.exception.code, "CONFIG_MISSING_DEEPSEEK_API_KEY")

    def test_factory_exceptions_are_wrapped_and_unknown_commands_rejected(self):
        def fail(_values):
            raise RuntimeError("secret factory detail")

        with self.assertRaises(AnalyzerError) as raised:
            dispatch({"command": "entries"}, pipeline_factory=fail)
        self.assertEqual(raised.exception.code, "INTERNAL_PIPELINE_FACTORY_FAILED")
        with self.assertRaises(AnalyzerError) as raised:
            dispatch({"command": "unknown"}, pipeline_factory=lambda _values: object())
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_COMMAND")


if __name__ == "__main__":
    unittest.main()
