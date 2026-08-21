from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import yaml

import dosweb.codeql.runner as codeql_runner
from dosweb.artifacts.identifiers import file_sha256
from dosweb.codeql import DatabaseInfo, QueryResult, run_query, validate_database
from dosweb.errors import AnalyzerError


class CodeqlAdapterTests(unittest.TestCase):
    def _database(self, root: Path, *, source_root: Path | None = None) -> Path:
        database = root / "database"
        (database / "db-java").mkdir(parents=True)
        source = source_root or (root / "source")
        source.mkdir(parents=True, exist_ok=True)
        (database / "codeql-database.yml").write_text(
            yaml.safe_dump(
                {
                    "primaryLanguage": "java",
                    "sourceLocationPrefix": str(source),
                    "creationMetadata": {"cliVersion": "2.20.0"},
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (database / "db-java" / "database-relations.json").write_text(
            '{"relations":[]}', encoding="utf-8"
        )
        return database

    def _decoded_entries_json(self, marker: str = "") -> str:
        row = [
            "servlet", "http", f"fixture.Handler{marker}.handle", "src/Handler.java", 10,
            "annotation_mapping", f"fixture.Handler{marker}.handle", "src/Handler.java", 8,
            "/items", "unknown", "body", "byte[]", "request_body", "before_handler",
            "complete", "",
        ]
        columns = [{"name": name, "kind": "String"} for name in (
            "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
            "registration_kind", "registration_fqn", "registration_file",
            "registration_start_line", "route_or_event", "auth_context",
            "attacker_input_name", "attacker_input_type", "attacker_input_kind",
            "materialization_phase", "coverage_status", "coverage_note",
        )]
        return json.dumps({"#select": {"columns": columns, "tuples": [row]}})

    def test_database_requires_metadata_and_java_database_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "database"
            database.mkdir()
            with self.assertRaises(AnalyzerError) as raised:
                validate_database(database)
            self.assertEqual(raised.exception.code, "CODEQL_DATABASE_INVALID")

            (database / "codeql-database.yml").write_text(
                "sourceLocationPrefix: /source\n", encoding="utf-8"
            )
            with self.assertRaises(AnalyzerError) as raised:
                validate_database(database)
            self.assertEqual(raised.exception.code, "CODEQL_DATABASE_INVALID")

            (database / "db-java").mkdir()
            info = validate_database(database)
            self.assertIsInstance(info, DatabaseInfo)
            self.assertEqual(info.path, database.resolve())

    def test_database_fingerprint_changes_when_metadata_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            first = self._database(root / "one", source_root=source)
            second_root = root / "renamed-output"
            second_root.mkdir()
            second = second_root / "database-copy"
            shutil.copytree(first, second)

            first_info = validate_database(first)
            second_info = validate_database(second)
            self.assertEqual(first_info.fingerprint, second_info.fingerprint)

            metadata = second / "codeql-database.yml"
            metadata.write_text(
                metadata.read_text(encoding="utf-8").replace("2.20.0", "2.21.0"),
                encoding="utf-8",
            )
            self.assertNotEqual(
                first_info.fingerprint,
                validate_database(second).fingerprint,
            )

    def test_real_codeql_timestamp_metadata_is_accepted(self):
        real_database = Path(__file__).parents[1] / "databases" / "micronaut-3-db"
        if not real_database.is_dir():
            self.skipTest("Repository real CodeQL database fixture is unavailable.")
        info = validate_database(real_database)
        self.assertEqual(info.source_root.name, "micronaut-core-3.10.8")
        self.assertRegex(info.fingerprint, r"^[0-9a-f]{64}$")

    def test_database_fingerprint_tracks_stable_files_but_not_mutable_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = self._database(Path(tmp))
            original = validate_database(database).fingerprint
            (database / "log").mkdir()
            (database / "log" / "query.log").write_text("mutable", encoding="utf-8")
            query_cache = database / "db-java" / "default" / "cache"
            query_cache.mkdir(parents=True)
            query_cache.joinpath("query.pack").write_bytes(b"mutable-query-cache")
            self.assertEqual(original, validate_database(database).fingerprint)
            (database / "db-java" / "database-relations.json").write_text(
                '{"relations":["changed"]}', encoding="utf-8"
            )
            self.assertNotEqual(original, validate_database(database).fingerprint)

    def test_query_failure_reports_codeql_query_failed_without_secret_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            secret = "sk-never-include-this-value"
            captured_env: dict[str, str] = {}

            def failing_run(argv, **kwargs):
                captured_env.update(kwargs["env"])
                return subprocess.CompletedProcess(
                    argv, 2, stdout="", stderr=f"failure {secret} " + "x" * 10000
                )

            with self.assertRaises(AnalyzerError) as raised:
                run_query(
                    query,
                    database,
                    output,
                    environment={"PATH": "/bin", "DEEPSEEK_API_KEY": secret},
                    subprocess_run=failing_run,
                )
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            rendered = repr(raised.exception.details)
            self.assertNotIn(secret, rendered)
            self.assertNotIn("DEEPSEEK_API_KEY", rendered)
            self.assertNotIn("DEEPSEEK_API_KEY", captured_env)
            self.assertLess(len(rendered), 5000)
            self.assertFalse(output.joinpath("Entries.bqrs").exists())
            self.assertFalse(output.joinpath("Entries.json").exists())

    def test_runner_uses_exact_commands_and_publishes_after_both_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            calls: list[list[str]] = []

            def successful_run(argv, **kwargs):
                calls.append(list(argv))
                output_argument = Path(argv[argv.index("--output") + 1])
                if argv[1:3] == ["query", "run"]:
                    output_argument.write_bytes(b"bqrs-bytes")
                else:
                    output_argument.write_text(self._decoded_entries_json(), encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            result = run_query(
                query,
                database,
                output,
                codeql_binary="/tools/codeql",
                subprocess_run=successful_run,
            )
            self.assertIsInstance(result, QueryResult)
            self.assertEqual(calls[0][:3], ["/tools/codeql", "query", "run"])
            self.assertEqual(Path(calls[0][3]).parent, query.resolve().parent)
            self.assertNotEqual(calls[0][3], str(query.resolve()))
            self.assertEqual(
                calls[0][4:],
                ["--database", str(database.path), "--output", calls[0][-1]],
            )
            self.assertEqual(
                calls[1],
                [
                    "/tools/codeql", "bqrs", "decode", calls[0][-1],
                    "--format=json", "--output", calls[1][-1],
                ],
            )
            self.assertEqual(result.bqrs_path.read_bytes(), b"bqrs-bytes")
            self.assertEqual(result.query_sha256, file_sha256(query))
            self.assertEqual(result.bqrs_sha256, file_sha256(result.bqrs_path))

    def test_decode_failure_preserves_existing_outputs_and_cleans_temporaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir()
            final_bqrs = output / "Entries.bqrs"
            final_json = output / "Entries.json"
            final_bqrs.write_bytes(b"old-bqrs")
            final_json.write_text("old-json", encoding="utf-8")
            calls = 0

            def decode_failure(argv, **kwargs):
                nonlocal calls
                calls += 1
                output_argument = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    output_argument.write_bytes(b"new-bqrs")
                    return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="decode failed")

            with self.assertRaises(AnalyzerError) as raised:
                run_query(query, database, output, subprocess_run=decode_failure)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertEqual(final_bqrs.read_bytes(), b"old-bqrs")
            self.assertEqual(final_json.read_text(encoding="utf-8"), "old-json")
            self.assertEqual(final_bqrs.read_bytes(), b"old-bqrs")
            self.assertEqual(final_json.read_text(encoding="utf-8"), "old-json")
            self.assertFalse(any("pending" in path.name for path in (output / ".generations").iterdir()))

    def test_nonfinite_metadata_maps_to_controlled_database_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = self._database(root)
            (database / "codeql-database.yml").write_text(
                "sourceLocationPrefix: /source\npoison: .nan\n", encoding="utf-8"
            )
            with self.assertRaises(AnalyzerError) as raised:
                validate_database(database)
            self.assertEqual(raised.exception.code, "CODEQL_DATABASE_INVALID")

    def test_same_query_concurrent_runs_publish_separate_atomic_generations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            barrier = threading.Barrier(2)
            results: list[QueryResult] = []
            failures: list[BaseException] = []

            def worker(marker: str):
                calls = 0

                def fake_run(argv, **kwargs):
                    nonlocal calls
                    calls += 1
                    target = Path(argv[argv.index("--output") + 1])
                    if calls == 1:
                        target.write_bytes(f"{marker}-bqrs".encode())
                    else:
                        barrier.wait(timeout=5)
                        target.write_text(self._decoded_entries_json(marker), encoding="utf-8")
                    return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

                try:
                    results.append(run_query(query, database, output, subprocess_run=fake_run))
                except BaseException as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=worker, args=(marker,)) for marker in ("a", "b")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertFalse(failures)
            self.assertEqual(len(results), 2)
            self.assertNotEqual(results[0].bqrs_path.parent, results[1].bqrs_path.parent)
            for result in results:
                marker = result.bqrs_path.read_bytes().decode().split("-")[0]
                self.assertEqual(
                    result.decoded_path.read_text(encoding="utf-8"),
                    self._decoded_entries_json(marker),
                )
                self.assertEqual(result.bqrs_sha256, file_sha256(result.bqrs_path))

    def test_runner_uses_one_deadline_and_snapshots_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select original", encoding="utf-8")
            output = root / "output"
            current_time = 100.0

            def clock():
                return current_time
            timeouts: list[float] = []
            query_arguments: list[Path] = []
            calls = 0

            def fake_run(argv, **kwargs):
                nonlocal calls, current_time
                calls += 1
                timeouts.append(kwargs["timeout"])
                target = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    query_arguments.append(Path(argv[3]))
                    target.write_bytes(b"bqrs")
                    current_time += 2.0
                else:
                    target.write_text(self._decoded_entries_json(), encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            result = run_query(
                query,
                database,
                output,
                timeout_seconds=10,
                subprocess_run=fake_run,
                monotonic=clock,
            )
            self.assertEqual(query_arguments[0].parent, query.resolve().parent)
            self.assertNotEqual(query_arguments[0], query.resolve())
            self.assertEqual(result.query_path.read_text(encoding="utf-8"), "select original")
            self.assertLess(timeouts[1], timeouts[0])
            self.assertEqual(result.query_sha256, file_sha256(result.query_path))

    def test_runner_rejects_query_drift_after_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select original", encoding="utf-8")
            output = root / "output"

            def mutating_run(argv, **kwargs):
                target = Path(argv[argv.index("--output") + 1])
                query.write_text("select changed", encoding="utf-8")
                target.write_bytes(b"bqrs")
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaises(AnalyzerError) as raised:
                run_query(query, database, output, subprocess_run=mutating_run)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertEqual(raised.exception.details["stage"], "query_run")
            self.assertFalse(any((output / ".generations").iterdir()))

    def test_runner_hashes_bqrs_before_atomic_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            calls = 0
            hash_stages: list[str] = []

            def successful_run(argv, **kwargs):
                nonlocal calls
                calls += 1
                target = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    target.write_bytes(b"bqrs")
                else:
                    target.write_text(self._decoded_entries_json(), encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            original_hash = codeql_runner._deadline_file_sha256

            def recording_hash(path, deadline, monotonic, stage):
                hash_stages.append(stage)
                return original_hash(path, deadline, monotonic, stage)

            original_replace = os.replace

            def asserting_replace(source, destination):
                self.assertEqual(hash_stages[-1], "publication")
                return original_replace(source, destination)

            with mock.patch.object(codeql_runner, "_deadline_file_sha256", recording_hash), mock.patch.object(
                codeql_runner.os, "replace", asserting_replace
            ):
                result = run_query(query, database, output, subprocess_run=successful_run)
            self.assertEqual(result.bqrs_sha256, file_sha256(result.bqrs_path))

    def test_bounded_process_deadline_covers_descendant_held_pipes(self):
        descendant = "import time; time.sleep(3)"
        parent = (
            "import subprocess, sys; "
            f"subprocess.Popen([sys.executable, '-c', {descendant!r}]); "
            "print('parent done')"
        )
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            codeql_runner._bounded_process(
                [sys.executable, "-c", parent],
                {"PATH": os.environ.get("PATH", "")},
                0.3,
            )
        self.assertLess(time.monotonic() - started, 2.0)

    def test_bounded_process_kills_sigterm_ignoring_descendant(self):
        descendant = (
            "import signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "time.sleep(10)"
        )
        parent = (
            "import subprocess, sys; "
            f"subprocess.Popen([sys.executable, '-c', {descendant!r}]); "
            "print('parent done')"
        )
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            codeql_runner._bounded_process(
                [sys.executable, "-c", parent],
                {"PATH": os.environ.get("PATH", "")},
                0.3,
            )
        self.assertLess(time.monotonic() - started, 2.0)

    def test_runner_rejects_contract_invalid_decoded_json_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            calls = 0

            def invalid_decode(argv, **kwargs):
                nonlocal calls
                calls += 1
                target = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    target.write_bytes(b"bqrs")
                else:
                    target.write_text('{"#select":{"columns":[],"tuples":[]}}', encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaises(AnalyzerError) as raised:
                run_query(query, database, output, subprocess_run=invalid_decode)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertFalse(any((output / ".generations").iterdir()))

    def test_decode_contract_diagnostic_keeps_only_safe_fields(self):
        diagnostic = codeql_runner._decode_contract_diagnostic(
            "ENUM_INVALID",
            {"query_name": "growth", "column": "resource_dimension", "row": 7},
        )
        parsed = json.loads(diagnostic)
        self.assertEqual(parsed["reason"], "ENUM_INVALID")
        self.assertEqual(parsed["query_name"], "growth")
        self.assertEqual(parsed["column"], "resource_dimension")
        self.assertEqual(parsed["row"], 7)

    def test_decode_contract_diagnostic_drops_paths_and_source_content(self):
        diagnostic = codeql_runner._decode_contract_diagnostic(
            "PATH_OUTSIDE_SOURCE_ROOT",
            {"query_name": "entries", "column": "handler_file", "row": 2, "value": "/abs/secret/path"},
        )
        self.assertNotIn("secret", diagnostic)
        self.assertNotIn("/abs", diagnostic)
        parsed = json.loads(diagnostic)
        self.assertNotIn("value", parsed)
        self.assertEqual(parsed["reason"], "PATH_OUTSIDE_SOURCE_ROOT")

    def test_decode_contract_diagnostic_never_uses_path_reason_values(self):
        # A decoder contract failure must not leak the offending path value: only
        # the reason code, query name, column, and row are serialized.
        diagnostic = codeql_runner._decode_contract_diagnostic(
            "PATH_INVALID", {"query_name": "flow", "column": "source_file", "row": 9}
        )
        self.assertEqual(json.loads(diagnostic), {"column": "source_file", "query_name": "flow", "reason": "PATH_INVALID", "row": 9})

    def test_query_pack_manifest_is_minimal(self):
        manifest_path = Path(__file__).parents[1] / "codeql" / "qlpack.yml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest,
            {
                "name": "dosweb/p0-java-resource-dos",
                "version": "0.1.0",
                "dependencies": {"codeql/java-all": "*"},
            },
        )


if __name__ == "__main__":
    unittest.main()
