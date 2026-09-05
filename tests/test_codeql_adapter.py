from __future__ import annotations

import ast
import errno
import json
import math
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections import Counter
from contextlib import ExitStack
from dataclasses import fields
from pathlib import Path
from unittest import mock

import yaml

import dosweb.codeql.runner as codeql_runner
import dosweb.filesystem as dosweb_filesystem
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

    def _assert_retained_hidden_generation(self, output: Path) -> set[str]:
        names = {
            candidate.name
            for candidate in (output / ".generations").iterdir()
        }
        self.assertTrue(names)
        self.assertTrue(all(name.startswith(".") for name in names))
        self.assertTrue(
            any(name.startswith(".Entries.pending.") for name in names)
        )
        self.assertFalse(any(name.startswith("Entries-") for name in names))
        return names

    def test_runner_descriptor_owner_release_calls_have_caller_local_lexical_pairs(
        self,
    ) -> None:
        module = ast.parse(
            Path(codeql_runner.__file__).read_text(encoding="utf-8")
        )
        parents = {
            child: parent
            for parent in ast.walk(module)
            for child in ast.iter_child_nodes(parent)
        }

        def is_release_call(candidate: ast.AST) -> bool:
            return (
                isinstance(candidate, ast.Call)
                and isinstance(candidate.func, ast.Name)
                and candidate.func.id
                == "_release_descriptor_owners_or_raise"
            )

        def direct_release_call(
            statements: list[ast.stmt],
        ) -> ast.Call | None:
            if (
                len(statements) != 1
                or not isinstance(statements[0], ast.Expr)
                or not is_release_call(statements[0].value)
            ):
                return None
            return statements[0].value

        def owning_function(candidate: ast.AST) -> str | None:
            current = parents.get(candidate)
            while current is not None:
                if isinstance(
                    current, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    return current.name
                current = parents.get(current)
            return None

        all_calls = [
            candidate
            for candidate in ast.walk(module)
            if is_release_call(candidate)
        ]
        paired_calls: list[ast.Call] = []
        pair_owners: list[str | None] = []
        for candidate in ast.walk(module):
            if not isinstance(candidate, ast.Try):
                continue
            body_call = direct_release_call(candidate.body)
            final_call = direct_release_call(candidate.finalbody)
            if body_call is None or final_call is None:
                continue
            if candidate.handlers or candidate.orelse:
                continue
            if ast.dump(body_call, include_attributes=False) != ast.dump(
                final_call,
                include_attributes=False,
            ):
                continue
            paired_calls.extend((body_call, final_call))
            pair_owners.append(owning_function(candidate))

        expected_pair_owners = Counter(
            {
                "_harden_owned_path": 1,
                "_fsync_file": 1,
                "_fsync_directory": 1,
                "_deadline_file_sha256": 1,
                "_pin_generation_directory": 1,
                "_cleanup_rollback_quarantine": 1,
                "_rollback_published_generation": 1,
                "_read_query_source": 1,
                "_write_query_snapshot": 1,
                "remove_empty_placeholder": 1,
            }
        )
        paired_call_ids = [id(call) for call in paired_calls]
        self.assertEqual(len(all_calls), 20)
        self.assertEqual(len(paired_calls), 20)
        self.assertEqual(len(set(paired_call_ids)), 20)
        self.assertEqual(
            set(paired_call_ids),
            {id(call) for call in all_calls},
        )
        self.assertEqual(Counter(pair_owners), expected_pair_owners)

    def test_query_source_release_call_entry_interrupt_uses_lexical_retry(
        self,
    ) -> None:
        for instrumentation in ("profile", "trace"):
            with self.subTest(
                instrumentation=instrumentation
            ), tempfile.TemporaryDirectory() as temporary:
                query = Path(temporary) / "query.ql"
                query.write_text("select 1\n", encoding="utf-8")
                real_open = codeql_runner._open_owned_descriptor
                target_descriptor = -1
                injected = False

                def capture_open(owner, path, flags, *args, **kwargs):
                    nonlocal target_descriptor
                    descriptor = real_open(
                        owner, path, flags, *args, **kwargs
                    )
                    if Path(path) == query:
                        target_descriptor = descriptor
                    return descriptor

                def interrupt_release_entry(frame, event, _arg):
                    nonlocal injected
                    if (
                        event == "call"
                        and frame.f_code
                        is codeql_runner._release_descriptor_owners_or_raise.__code__
                        and frame.f_locals.get("diagnostic")
                        == "query source descriptor release failed"
                        and not injected
                    ):
                        injected = True
                        raise KeyboardInterrupt(
                            f"query source {instrumentation} release entry interruption"
                        )
                    return interrupt_release_entry

                baseline_fds = len(os.listdir("/proc/self/fd"))
                try:
                    with mock.patch.object(
                        codeql_runner,
                        "_open_owned_descriptor",
                        side_effect=capture_open,
                    ):
                        if instrumentation == "profile":
                            sys.setprofile(interrupt_release_entry)
                        else:
                            sys.settrace(interrupt_release_entry)
                        try:
                            with self.assertRaises(KeyboardInterrupt):
                                codeql_runner._read_query_source(
                                    query,
                                    time.monotonic() + 10,
                                    time.monotonic,
                                )
                        finally:
                            sys.setprofile(None)
                            sys.settrace(None)

                    self.assertTrue(injected)
                    self.assertGreaterEqual(target_descriptor, 0)
                    with self.assertRaises(OSError):
                        os.fstat(target_descriptor)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                finally:
                    sys.setprofile(None)
                    sys.settrace(None)
                    if target_descriptor >= 0:
                        try:
                            os.close(target_descriptor)
                        except OSError:
                            pass

    def test_query_source_second_release_call_interrupts_after_first_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            query = Path(temporary) / "query.ql"
            query.write_text("select 1\n", encoding="utf-8")
            real_open = codeql_runner._open_owned_descriptor
            real_release = codeql_runner._release_descriptor_owners_or_raise
            target_descriptor = -1
            release_calls = 0

            def capture_open(owner, path, flags, *args, **kwargs):
                nonlocal target_descriptor
                descriptor = real_open(owner, path, flags, *args, **kwargs)
                if Path(path) == query:
                    target_descriptor = descriptor
                return descriptor

            def interrupt_second_release(owner, capability, diagnostic):
                nonlocal release_calls
                release_calls += 1
                if release_calls == 2:
                    raise KeyboardInterrupt("second runner release interrupted")
                return real_release(owner, capability, diagnostic)

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with (
                    mock.patch.object(
                        codeql_runner,
                        "_open_owned_descriptor",
                        side_effect=capture_open,
                    ),
                    mock.patch.object(
                        codeql_runner,
                        "_release_descriptor_owners_or_raise",
                        side_effect=interrupt_second_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_runner._read_query_source(
                        query,
                        time.monotonic() + 10,
                        time.monotonic,
                    )

                self.assertEqual(release_calls, 2)
                self.assertGreaterEqual(target_descriptor, 0)
                with self.assertRaises(OSError):
                    os.fstat(target_descriptor)
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                if target_descriptor >= 0:
                    try:
                        os.close(target_descriptor)
                    except OSError:
                        pass

    def test_query_source_lexical_retry_never_recloses_aba_fd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            query = Path(temporary) / "query.ql"
            query.write_text("select 1\n", encoding="utf-8")
            real_open_owned = codeql_runner._open_owned_descriptor
            real_release = codeql_runner._release_descriptor_owners_or_raise
            real_close_once = dosweb_filesystem.close_fd_once
            real_close = os.close
            real_open = os.open
            target_descriptor = -1
            replacement_descriptor = -1
            release_calls = 0
            close_actions = 0

            def capture_open(owner, path, flags, *args, **kwargs):
                nonlocal target_descriptor
                descriptor = real_open_owned(
                    owner, path, flags, *args, **kwargs
                )
                if Path(path) == query:
                    target_descriptor = descriptor
                return descriptor

            def count_release(owner, capability, diagnostic):
                nonlocal release_calls
                release_calls += 1
                return real_release(owner, capability, diagnostic)

            def close_then_reuse(descriptor, capability):
                nonlocal replacement_descriptor, close_actions
                if descriptor != target_descriptor:
                    return real_close_once(descriptor, capability)
                close_actions += 1
                real_close(descriptor)
                replacement = real_open("/dev/null", os.O_RDONLY)
                if replacement != descriptor:
                    os.dup2(replacement, descriptor)
                    real_close(replacement)
                replacement_descriptor = descriptor
                raise KeyboardInterrupt("runner close post-action interruption")

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with (
                    mock.patch.object(
                        codeql_runner,
                        "_open_owned_descriptor",
                        side_effect=capture_open,
                    ),
                    mock.patch.object(
                        codeql_runner,
                        "_release_descriptor_owners_or_raise",
                        side_effect=count_release,
                    ),
                    mock.patch.object(
                        dosweb_filesystem,
                        "close_fd_once",
                        side_effect=close_then_reuse,
                    ),
                    self.assertRaises(OSError),
                ):
                    codeql_runner._read_query_source(
                        query,
                        time.monotonic() + 10,
                        time.monotonic,
                    )

                self.assertEqual(release_calls, 2)
                self.assertEqual(close_actions, 1)
                self.assertEqual(replacement_descriptor, target_descriptor)
                os.fstat(replacement_descriptor)
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 1
                )
            finally:
                if replacement_descriptor >= 0:
                    try:
                        real_close(replacement_descriptor)
                    except OSError:
                        pass
                elif target_descriptor >= 0:
                    try:
                        real_close(target_descriptor)
                    except OSError:
                        pass
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

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
            generation_names = {
                candidate.name
                for candidate in (output / ".generations").iterdir()
            }
            self.assertEqual(
                generation_names,
                {result.query_path.parent.name},
            )
            self.assertFalse(
                any(name.startswith(".") for name in generation_names)
            )

    def test_descriptor_bound_output_is_inherited_by_both_codeql_subprocesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir(mode=0o700)
            output_descriptor = os.open(
                output,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
            inherited: list[tuple[int, ...]] = []
            try:
                descriptor_path = Path(
                    f"/proc/self/fd/{output_descriptor}"
                )

                def successful_run(argv, **kwargs):
                    inherited.append(tuple(kwargs["pass_fds"]))
                    target = Path(argv[argv.index("--output") + 1])
                    if argv[1:3] == ["query", "run"]:
                        target.write_bytes(b"bqrs-bytes")
                    else:
                        target.write_text(
                            self._decoded_entries_json(), encoding="utf-8"
                        )
                    return subprocess.CompletedProcess(
                        argv, 0, stdout="", stderr=""
                    )

                result = run_query(
                    query,
                    database,
                    descriptor_path,
                    output_descriptor=output_descriptor,
                    retain_output_binding=True,
                    subprocess_run=successful_run,
                )

                self.assertEqual(
                    inherited,
                    [(output_descriptor,), (output_descriptor,)],
                )
                self.assertEqual(
                    result.decoded_path.read_text(encoding="utf-8"),
                    self._decoded_entries_json(),
                )
                self.assertEqual(
                    result.decoded_path.parts[:4],
                    ("/", "proc", "self", "fd"),
                )
                generation_names = {
                    candidate.name
                    for candidate in (output / ".generations").iterdir()
                }
                self.assertEqual(
                    generation_names,
                    {result.query_path.parent.name},
                )
                self.assertFalse(
                    any(name.startswith(".") for name in generation_names)
                )
            finally:
                if "result" in locals():
                    binding = getattr(result, "_output_binding", None)
                    if binding is not None:
                        codeql_runner._release_owned_query_output_binding(
                            binding
                        )
                os.close(output_descriptor)

    def test_multiple_successful_queries_retire_every_rollback_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            output = root / "output"
            calls = 0
            queries = (
                root / "Entries.ql",
                root / "SpringMvcEntries.ql",
            )
            for query in queries:
                query.write_text("select 1", encoding="utf-8")

            def successful_run(argv, **_kwargs):
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls % 2:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            results = [
                run_query(
                    query,
                    database,
                    output,
                    subprocess_run=successful_run,
                )
                for query in queries
            ]
            generation_names = {
                candidate.name
                for candidate in (output / ".generations").iterdir()
            }
            self.assertEqual(
                generation_names,
                {result.query_path.parent.name for result in results},
            )
            self.assertFalse(
                any(name.startswith(".") for name in generation_names)
            )

    def test_successful_publication_slot_cleanup_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            calls = 0
            faulted = False
            real_no_replace = codeql_runner.renameat2_no_replace

            def successful_run(argv, **_kwargs):
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            def fail_slot_cleanup_once(
                source_directory_fd,
                source_name,
                destination_directory_fd,
                destination_name,
            ):
                nonlocal faulted
                if (
                    not faulted
                    and source_name.startswith(".rollback-slot-")
                    and destination_name.startswith(
                        ".rollback-slot-tombstone-"
                    )
                ):
                    faulted = True
                    raise OSError(errno.EIO, "rollback slot cleanup failed")
                return real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            with mock.patch.object(
                codeql_runner,
                "renameat2_no_replace",
                side_effect=fail_slot_cleanup_once,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    run_query(
                        query,
                        database,
                        output,
                        subprocess_run=successful_run,
                    )

            self.assertTrue(faulted)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            names = {
                candidate.name
                for candidate in (output / ".generations").iterdir()
            }
            self.assertFalse(
                any(name.startswith("Entries-") for name in names)
            )
            self.assertTrue(
                any(name.startswith(".rollback-slot-") for name in names)
            )

    def test_slot_retirement_namespace_aba_fails_closed_for_both_binding_modes(
        self,
    ):
        for retain_output_binding in (False, True):
            with self.subTest(
                retain_output_binding=retain_output_binding
            ), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                database = validate_database(self._database(root))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                output = root / "output"
                output.mkdir(mode=0o700)
                output_descriptor = os.open(
                    output,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                calls = 0
                attacked = False
                original_slot_info: os.stat_result | None = None
                substitute_slot_info: os.stat_result | None = None
                substitute_slot_name: str | None = None
                attacker_slot_name = ".attacker-retained-rollback-slot"
                real_scandir = codeql_runner.os.scandir
                result: QueryResult | None = None

                def successful_run(argv, **_kwargs):
                    nonlocal calls
                    calls += 1
                    destination = Path(argv[argv.index("--output") + 1])
                    if calls == 1:
                        destination.write_bytes(b"bqrs")
                    else:
                        destination.write_text(
                            self._decoded_entries_json(), encoding="utf-8"
                        )
                    return subprocess.CompletedProcess(
                        argv, 0, stdout="", stderr=""
                    )

                def attack_after_empty_slot_scan(slot_descriptor: int) -> None:
                    nonlocal attacked
                    nonlocal original_slot_info
                    nonlocal substitute_slot_info
                    nonlocal substitute_slot_name
                    if attacked:
                        return
                    descriptor_path = os.readlink(
                        f"/proc/self/fd/{slot_descriptor}"
                    )
                    slot_name = Path(descriptor_path).name
                    if not slot_name.startswith(".rollback-slot-"):
                        return
                    attacked = True
                    substitute_slot_name = slot_name
                    original_slot_info = os.fstat(slot_descriptor)
                    os.setxattr(
                        slot_descriptor,
                        b"user.dosweb_test_marker",
                        b"original",
                    )
                    generations = output / ".generations"
                    os.rename(
                        generations / slot_name,
                        generations / attacker_slot_name,
                    )
                    substitute = generations / slot_name
                    substitute.mkdir(mode=0o700)
                    os.setxattr(
                        substitute,
                        b"user.dosweb_test_marker",
                        b"substitute",
                    )
                    substitute_slot_info = substitute.stat(
                        follow_symlinks=False
                    )

                class AttackAfterEmptyScan:
                    def __init__(self, iterator, descriptor: int) -> None:
                        self.iterator = iterator
                        self.descriptor = descriptor

                    def __enter__(self):
                        return self

                    def __exit__(self, exc_type, exc, traceback):
                        return self.iterator.__exit__(
                            exc_type,
                            exc,
                            traceback,
                        )

                    def __iter__(self):
                        return self

                    def __next__(self):
                        try:
                            return next(self.iterator)
                        except StopIteration:
                            attack_after_empty_slot_scan(self.descriptor)
                            raise

                def replace_slot_after_empty_scan(path):
                    iterator = real_scandir(path)
                    if isinstance(path, int):
                        try:
                            descriptor_path = os.readlink(
                                f"/proc/self/fd/{path}"
                            )
                        except OSError:
                            descriptor_path = ""
                        if Path(descriptor_path).name.startswith(
                            ".rollback-slot-"
                        ):
                            return AttackAfterEmptyScan(iterator, path)
                    return iterator

                try:
                    descriptor_path = Path(
                        f"/proc/self/fd/{output_descriptor}"
                    )
                    with mock.patch.object(
                        codeql_runner.os,
                        "scandir",
                        side_effect=replace_slot_after_empty_scan,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            result = run_query(
                                query,
                                database,
                                descriptor_path,
                                output_descriptor=output_descriptor,
                                retain_output_binding=retain_output_binding,
                                subprocess_run=successful_run,
                            )

                    self.assertTrue(attacked)
                    self.assertEqual(
                        raised.exception.code,
                        "CODEQL_QUERY_FAILED",
                    )
                    self.assertIsNotNone(original_slot_info)
                    self.assertIsNotNone(substitute_slot_info)
                    self.assertIsNotNone(substitute_slot_name)
                    retained_original = (
                        output / ".generations" / attacker_slot_name
                    ).stat(follow_symlinks=False)
                    assert original_slot_info is not None
                    self.assertEqual(
                        (
                            retained_original.st_dev,
                            retained_original.st_ino,
                        ),
                        (
                            original_slot_info.st_dev,
                            original_slot_info.st_ino,
                        ),
                    )
                    self.assertEqual(
                        os.getxattr(
                            output / ".generations" / attacker_slot_name,
                            b"user.dosweb_test_marker",
                        ),
                        b"original",
                    )
                    assert substitute_slot_info is not None
                    assert substitute_slot_name is not None
                    retained_substitute = (
                        output / ".generations" / substitute_slot_name
                    ).stat(follow_symlinks=False)
                    self.assertEqual(
                        (
                            retained_substitute.st_dev,
                            retained_substitute.st_ino,
                        ),
                        (
                            substitute_slot_info.st_dev,
                            substitute_slot_info.st_ino,
                        ),
                    )
                    self.assertEqual(
                        os.getxattr(
                            output / ".generations" / substitute_slot_name,
                            b"user.dosweb_test_marker",
                        ),
                        b"substitute",
                    )
                    names = {
                        candidate.name
                        for candidate in (
                            output / ".generations"
                        ).iterdir()
                    }
                    self.assertFalse(
                        any(name.startswith("Entries-") for name in names)
                    )
                finally:
                    if result is not None:
                        binding = getattr(result, "_output_binding", None)
                        if binding is not None:
                            codeql_runner._release_owned_query_output_binding(
                                binding
                            )
                    os.close(output_descriptor)

    def _assert_early_rollback_slot_cleanup_preserves_aba(
        self,
        *,
        failure_window: str,
        retain_output_binding: bool,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir(mode=0o700)
            output_descriptor = os.open(
                output,
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NOFOLLOW", 0),
            )
            calls = 0
            attacked = False
            destructive_slot_cleanup_called = False
            post_probe_failure = False
            probe_completed = False
            original_slot_info: os.stat_result | None = None
            substitute_slot_info: os.stat_result | None = None
            substitute_slot_name: str | None = None
            attacker_slot_name = ".attacker-retained-rollback-slot"
            real_rmdir = codeql_runner.os.rmdir
            real_no_replace = codeql_runner.renameat2_no_replace
            real_probe = codeql_runner._probe_rename_exchange
            real_require_deadline = codeql_runner._require_deadline

            def successful_run(argv, **_kwargs):
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(),
                        encoding="utf-8",
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            def attack_slot(name: str) -> None:
                nonlocal attacked
                nonlocal original_slot_info
                nonlocal substitute_slot_info
                nonlocal substitute_slot_name
                if (
                    not attacked
                    and name.startswith(".rollback-slot-")
                ):
                    attacked = True
                    substitute_slot_name = name
                    generations = output / ".generations"
                    original = generations / name
                    original_slot_info = original.stat(
                        follow_symlinks=False
                    )
                    os.setxattr(
                        original,
                        b"user.dosweb_test_marker",
                        b"original",
                    )
                    os.rename(
                        original,
                        generations / attacker_slot_name,
                    )
                    substitute = generations / name
                    substitute.mkdir(mode=0o700)
                    os.setxattr(
                        substitute,
                        b"user.dosweb_test_marker",
                        b"substitute",
                    )
                    substitute_slot_info = substitute.stat(
                        follow_symlinks=False
                    )

            def attack_slot_before_destructive_cleanup(
                path,
                *args,
                **kwargs,
            ):
                nonlocal destructive_slot_cleanup_called
                name = os.fspath(path)
                if isinstance(name, str):
                    if name.startswith(".rollback-slot-"):
                        destructive_slot_cleanup_called = True
                    attack_slot(name)
                return real_rmdir(path, *args, **kwargs)

            def attack_slot_before_noreplace_isolation(
                source_directory_fd,
                source_name,
                destination_directory_fd,
                destination_name,
            ):
                attack_slot(source_name)
                return real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            def complete_probe(*args, **kwargs):
                nonlocal probe_completed
                result = real_probe(*args, **kwargs)
                probe_completed = True
                return result

            def fail_after_probe(*args, **kwargs):
                nonlocal post_probe_failure
                if probe_completed and not post_probe_failure:
                    post_probe_failure = True
                    raise TimeoutError(
                        "injected post-probe pre-publication failure"
                    )
                return real_require_deadline(*args, **kwargs)

            descriptor_path = Path(
                f"/proc/self/fd/{output_descriptor}"
            )
            patchers = [
                mock.patch.object(
                    codeql_runner.os,
                    "rmdir",
                    side_effect=attack_slot_before_destructive_cleanup,
                ),
                mock.patch.object(
                    codeql_runner,
                    "renameat2_no_replace",
                    side_effect=attack_slot_before_noreplace_isolation,
                ),
            ]
            if failure_window == "probe_failure":
                patchers.append(
                    mock.patch.object(
                        codeql_runner,
                        "renameat2_exchange",
                        side_effect=OSError(
                            errno.ENOSYS,
                            "injected exchange probe failure",
                        ),
                    )
                )
            elif failure_window == "post_probe_pre_publication":
                patchers.extend(
                    (
                        mock.patch.object(
                            codeql_runner,
                            "_probe_rename_exchange",
                            side_effect=complete_probe,
                        ),
                        mock.patch.object(
                            codeql_runner,
                            "_require_deadline",
                            side_effect=fail_after_probe,
                        ),
                    )
                )
            else:
                self.fail(f"unsupported failure window: {failure_window}")

            try:
                with ExitStack() as stack:
                    for patcher in patchers:
                        stack.enter_context(patcher)
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            database,
                            descriptor_path,
                            output_descriptor=output_descriptor,
                            retain_output_binding=retain_output_binding,
                            subprocess_run=successful_run,
                        )

                self.assertTrue(attacked)
                self.assertFalse(destructive_slot_cleanup_called)
                if failure_window == "post_probe_pre_publication":
                    self.assertTrue(probe_completed)
                    self.assertTrue(post_probe_failure)
                self.assertEqual(
                    raised.exception.code,
                    "CODEQL_QUERY_FAILED",
                )
                self.assertIsNotNone(original_slot_info)
                self.assertIsNotNone(substitute_slot_info)
                self.assertIsNotNone(substitute_slot_name)

                retained_original = (
                    output / ".generations" / attacker_slot_name
                ).stat(follow_symlinks=False)
                assert original_slot_info is not None
                self.assertEqual(
                    (
                        retained_original.st_dev,
                        retained_original.st_ino,
                    ),
                    (
                        original_slot_info.st_dev,
                        original_slot_info.st_ino,
                    ),
                )
                self.assertEqual(
                    os.getxattr(
                        output / ".generations" / attacker_slot_name,
                        b"user.dosweb_test_marker",
                    ),
                    b"original",
                )

                assert substitute_slot_name is not None
                substitute = (
                    output / ".generations" / substitute_slot_name
                )
                self.assertTrue(substitute.exists())
                retained_substitute = substitute.stat(
                    follow_symlinks=False
                )
                assert substitute_slot_info is not None
                self.assertEqual(
                    (
                        retained_substitute.st_dev,
                        retained_substitute.st_ino,
                    ),
                    (
                        substitute_slot_info.st_dev,
                        substitute_slot_info.st_ino,
                    ),
                )
                self.assertEqual(
                    os.getxattr(
                        substitute,
                        b"user.dosweb_test_marker",
                    ),
                    b"substitute",
                )
                names = {
                    candidate.name
                    for candidate in (
                        output / ".generations"
                    ).iterdir()
                }
                self.assertFalse(
                    any(name.startswith("Entries-") for name in names)
                )
            finally:
                os.close(output_descriptor)

    def test_exchange_probe_failure_cleanup_never_deletes_slot_substitute(
        self,
    ):
        for retain_output_binding in (False, True):
            with self.subTest(
                retain_output_binding=retain_output_binding
            ):
                self._assert_early_rollback_slot_cleanup_preserves_aba(
                    failure_window="probe_failure",
                    retain_output_binding=retain_output_binding,
                )

    def test_post_probe_pre_publication_cleanup_never_deletes_slot_substitute(
        self,
    ):
        for retain_output_binding in (False, True):
            with self.subTest(
                retain_output_binding=retain_output_binding
            ):
                self._assert_early_rollback_slot_cleanup_preserves_aba(
                    failure_window="post_probe_pre_publication",
                    retain_output_binding=retain_output_binding,
                )

    def test_post_slot_isolation_fsync_failure_quarantines_normal_generation(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            calls = 0
            slot_retired = False
            faulted = False
            real_no_replace = codeql_runner.renameat2_no_replace
            real_fsync = codeql_runner.os.fsync

            def successful_run(argv, **_kwargs):
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            def track_slot_isolation(
                source_directory_fd,
                source_name,
                destination_directory_fd,
                destination_name,
            ):
                nonlocal slot_retired
                result = real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )
                if source_name.startswith(
                    ".rollback-slot-"
                ) and destination_name.startswith(
                    ".rollback-slot-tombstone-"
                ):
                    slot_retired = True
                return result

            def fail_first_post_retirement_fsync(descriptor):
                nonlocal faulted
                if slot_retired and not faulted:
                    faulted = True
                    raise OSError(
                        errno.EIO,
                        "post-slot-isolation fsync failed",
                    )
                return real_fsync(descriptor)

            with mock.patch.object(
                codeql_runner,
                "renameat2_no_replace",
                side_effect=track_slot_isolation,
            ), mock.patch.object(
                codeql_runner.os,
                "fsync",
                side_effect=fail_first_post_retirement_fsync,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    run_query(
                        query,
                        database,
                        output,
                        subprocess_run=successful_run,
                    )

            self.assertTrue(slot_retired)
            self.assertTrue(faulted)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            names = {
                candidate.name
                for candidate in (output / ".generations").iterdir()
            }
            self.assertFalse(
                any(name.startswith("Entries-") for name in names)
            )

    def test_post_slot_isolation_verification_failure_quarantines_normal_generation(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            calls = 0
            slot_retired = False
            faulted = False
            real_no_replace = codeql_runner.renameat2_no_replace
            real_require_binding = (
                codeql_runner._require_generation_directory_binding
            )

            def successful_run(argv, **_kwargs):
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            def track_slot_isolation(
                source_directory_fd,
                source_name,
                destination_directory_fd,
                destination_name,
            ):
                nonlocal slot_retired
                result = real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )
                if source_name.startswith(
                    ".rollback-slot-"
                ) and destination_name.startswith(
                    ".rollback-slot-tombstone-"
                ):
                    slot_retired = True
                return result

            def fail_first_post_retirement_verification(*args, **kwargs):
                nonlocal faulted
                if slot_retired and not faulted:
                    faulted = True
                    raise OSError(
                        errno.EIO,
                        "post-slot-isolation verification failed",
                    )
                return real_require_binding(*args, **kwargs)

            with mock.patch.object(
                codeql_runner,
                "renameat2_no_replace",
                side_effect=track_slot_isolation,
            ), mock.patch.object(
                codeql_runner,
                "_require_generation_directory_binding",
                side_effect=fail_first_post_retirement_verification,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    run_query(
                        query,
                        database,
                        output,
                        subprocess_run=successful_run,
                    )

            self.assertTrue(slot_retired)
            self.assertTrue(faulted)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            names = {
                candidate.name
                for candidate in (output / ".generations").iterdir()
            }
            self.assertFalse(
                any(name.startswith("Entries-") for name in names)
            )

    def test_cleanup_anchor_pre_action_failure_quarantines_retired_publication(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            calls = 0
            slot_retired = False
            faulted = False
            duplicates: list[int] = []
            real_no_replace = codeql_runner.renameat2_no_replace
            real_duplicate = codeql_runner.os.dup
            real_close_range = dosweb_filesystem._close_range

            def successful_run(argv, **_kwargs):
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            def track_slot_isolation(
                source_directory_fd,
                source_name,
                destination_directory_fd,
                destination_name,
            ):
                nonlocal slot_retired
                result = real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )
                if source_name.startswith(
                    ".rollback-slot-"
                ) and destination_name.startswith(
                    ".rollback-slot-tombstone-"
                ):
                    slot_retired = True
                return result

            def record_duplicate(descriptor):
                duplicate = real_duplicate(descriptor)
                duplicates.append(duplicate)
                return duplicate

            def fail_cleanup_anchor_before_action(
                capability,
                first_fd,
                last_fd,
            ):
                nonlocal faulted
                cleanup_anchor = duplicates[2] if len(duplicates) >= 3 else -1
                if (
                    slot_retired
                    and not faulted
                    and first_fd == cleanup_anchor
                    and last_fd == cleanup_anchor
                ):
                    faulted = True
                    raise dosweb_filesystem.CloseRangePreActionError(
                        errno.EIO,
                        "cleanup anchor pre-action failure",
                    )
                return real_close_range(capability, first_fd, last_fd)

            with mock.patch.object(
                codeql_runner,
                "renameat2_no_replace",
                side_effect=track_slot_isolation,
            ), mock.patch.object(
                codeql_runner.os,
                "dup",
                side_effect=record_duplicate,
            ), mock.patch.object(
                dosweb_filesystem,
                "_close_range",
                side_effect=fail_cleanup_anchor_before_action,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    run_query(
                        query,
                        database,
                        output,
                        subprocess_run=successful_run,
                    )

            self.assertTrue(slot_retired)
            self.assertTrue(faulted)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            names = {
                candidate.name
                for candidate in (output / ".generations").iterdir()
            }
            self.assertFalse(
                any(name.startswith("Entries-") for name in names)
            )

    def test_published_generation_mode_drift_during_slot_retirement_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            calls = 0
            changed_mode = False
            real_no_replace = codeql_runner.renameat2_no_replace

            def successful_run(argv, **_kwargs):
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            def change_mode_before_slot_isolation(
                source_directory_fd,
                source_name,
                destination_directory_fd,
                destination_name,
            ):
                nonlocal changed_mode
                if (
                    not changed_mode
                    and source_name.startswith(".rollback-slot-")
                    and destination_name.startswith(
                        ".rollback-slot-tombstone-"
                    )
                ):
                    with os.scandir(source_directory_fd) as entries:
                        published_name = next(
                            entry.name
                            for entry in entries
                            if entry.name.startswith("Entries-")
                        )
                    os.chmod(
                        published_name,
                        0o755,
                        dir_fd=source_directory_fd,
                        follow_symlinks=False,
                    )
                    changed_mode = True
                return real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            with mock.patch.object(
                codeql_runner,
                "renameat2_no_replace",
                side_effect=change_mode_before_slot_isolation,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    run_query(
                        query,
                        database,
                        output,
                        subprocess_run=successful_run,
                    )

            self.assertTrue(changed_mode)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            names = {
                candidate.name
                for candidate in (output / ".generations").iterdir()
            }
            self.assertFalse(
                any(name.startswith("Entries-") for name in names)
            )

    def test_slot_descriptor_release_failures_quarantine_for_both_binding_modes(
        self,
    ):
        for retain_output_binding in (False, True):
            for failure_phase in ("pre_action", "post_action"):
                with self.subTest(
                    retain_output_binding=retain_output_binding,
                    failure_phase=failure_phase,
                ), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    database = validate_database(self._database(root))
                    query = root / "Entries.ql"
                    query.write_text("select 1", encoding="utf-8")
                    output = root / "output"
                    output.mkdir(mode=0o700)
                    output_descriptor = os.open(
                        output,
                        os.O_RDONLY
                        | os.O_DIRECTORY
                        | getattr(os, "O_NOFOLLOW", 0),
                    )
                    calls = 0
                    slot_descriptor = -1
                    faulted = False
                    real_open = codeql_runner.os.open
                    real_close_once = dosweb_filesystem.close_fd_once
                    result: QueryResult | None = None

                    def successful_run(argv, **_kwargs):
                        nonlocal calls
                        calls += 1
                        destination = Path(
                            argv[argv.index("--output") + 1]
                        )
                        if calls == 1:
                            destination.write_bytes(b"bqrs")
                        else:
                            destination.write_text(
                                self._decoded_entries_json(),
                                encoding="utf-8",
                            )
                        return subprocess.CompletedProcess(
                            argv, 0, stdout="", stderr=""
                        )

                    def record_slot_open(path, flags, *args, **kwargs):
                        nonlocal slot_descriptor
                        descriptor = real_open(
                            path,
                            flags,
                            *args,
                            **kwargs,
                        )
                        name = os.fspath(path)
                        if (
                            isinstance(name, str)
                            and name.startswith(".rollback-slot-")
                        ):
                            slot_descriptor = descriptor
                        return descriptor

                    def fail_slot_release(descriptor, capability):
                        nonlocal faulted
                        if descriptor == slot_descriptor and not faulted:
                            faulted = True
                            if failure_phase == "pre_action":
                                raise (
                                    dosweb_filesystem.CloseRangePreActionError(
                                        errno.EIO,
                                        "slot release pre-action failure",
                                    )
                                )
                            real_close_once(descriptor, capability)
                            raise OSError(
                                errno.EIO,
                                "slot release post-action failure",
                            )
                        return real_close_once(descriptor, capability)

                    try:
                        descriptor_path = Path(
                            f"/proc/self/fd/{output_descriptor}"
                        )
                        with mock.patch.object(
                            codeql_runner.os,
                            "open",
                            side_effect=record_slot_open,
                        ), mock.patch.object(
                            dosweb_filesystem,
                            "close_fd_once",
                            side_effect=fail_slot_release,
                        ):
                            with self.assertRaises(AnalyzerError) as raised:
                                result = run_query(
                                    query,
                                    database,
                                    descriptor_path,
                                    output_descriptor=output_descriptor,
                                    retain_output_binding=(
                                        retain_output_binding
                                    ),
                                    subprocess_run=successful_run,
                                )

                        self.assertTrue(faulted)
                        self.assertEqual(
                            raised.exception.code,
                            "CODEQL_QUERY_FAILED",
                        )
                        names = {
                            candidate.name
                            for candidate in (
                                output / ".generations"
                            ).iterdir()
                        }
                        self.assertFalse(
                            any(
                                name.startswith("Entries-")
                                for name in names
                            )
                        )
                    finally:
                        if result is not None:
                            binding = getattr(
                                result,
                                "_output_binding",
                                None,
                            )
                            if binding is not None:
                                codeql_runner._release_owned_query_output_binding(
                                    binding
                                )
                        os.close(output_descriptor)

    def test_private_output_binding_is_not_a_query_result_serialization_field(self):
        self.assertNotIn(
            "_output_binding",
            {item.name for item in fields(QueryResult)},
        )
        result = QueryResult(
            "Entries",
            Path("Entries.ql"),
            Path("Entries.bqrs"),
            Path("Entries.json"),
            "a" * 64,
            "b" * 64,
        )
        self.assertFalse(hasattr(result, "__dict__"))

    def test_query_result_pickle_restores_empty_private_binding_slot(self):
        result = QueryResult(
            "Entries",
            Path("Entries.ql"),
            Path("Entries.bqrs"),
            Path("Entries.json"),
            "a" * 64,
            "b" * 64,
        )
        restored = pickle.loads(pickle.dumps(result))
        self.assertEqual(restored, result)
        self.assertEqual(hash(restored), hash(result))
        self.assertIsNone(restored._output_binding)

    def test_retained_binding_rejects_generations_exchange_before_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir(mode=0o700)
            output_descriptor = os.open(
                output,
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NOFOLLOW", 0),
            )
            result: QueryResult | None = None
            exchanged = False

            def successful_run(argv, **kwargs):
                target = Path(argv[argv.index("--output") + 1])
                if argv[1:3] == ["query", "run"]:
                    target.write_bytes(b"bqrs-bytes")
                else:
                    target.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            real_pin = codeql_runner._pin_query_output_binding

            def exchange_before_pin(
                results_descriptor,
                generation_name,
                decoded_name,
                capability,
                *args,
                **kwargs,
            ):
                nonlocal exchanged
                competitor_name = ".generations-competitor"
                os.mkdir(
                    competitor_name,
                    mode=0o700,
                    dir_fd=results_descriptor,
                )
                competitor_descriptor = os.open(
                    competitor_name,
                    os.O_RDONLY | os.O_DIRECTORY,
                    dir_fd=results_descriptor,
                )
                try:
                    os.mkdir(
                        generation_name,
                        mode=0o700,
                        dir_fd=competitor_descriptor,
                    )
                    generation_descriptor = os.open(
                        generation_name,
                        os.O_RDONLY | os.O_DIRECTORY,
                        dir_fd=competitor_descriptor,
                    )
                    try:
                        decoded_descriptor = os.open(
                            decoded_name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=generation_descriptor,
                        )
                        try:
                            os.write(
                                decoded_descriptor,
                                self._decoded_entries_json("Forged").encode(
                                    "utf-8"
                                ),
                            )
                        finally:
                            os.close(decoded_descriptor)
                    finally:
                        os.close(generation_descriptor)
                finally:
                    os.close(competitor_descriptor)
                codeql_runner.renameat2_exchange(
                    results_descriptor,
                    ".generations",
                    results_descriptor,
                    competitor_name,
                )
                exchanged = True
                return real_pin(
                    results_descriptor,
                    generation_name,
                    decoded_name,
                    capability,
                    *args,
                    **kwargs,
                )

            try:
                with mock.patch.object(
                    codeql_runner,
                    "_pin_query_output_binding",
                    side_effect=exchange_before_pin,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        result = run_query(
                            query,
                            database,
                            Path(f"/proc/self/fd/{output_descriptor}"),
                            output_descriptor=output_descriptor,
                            retain_output_binding=True,
                            subprocess_run=successful_run,
                        )
                self.assertTrue(exchanged)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertNotIn(str(root), json.dumps(raised.exception.details))
            finally:
                if result is not None:
                    binding = getattr(result, "_output_binding", None)
                    if binding is not None:
                        for field in (
                            "decoded_descriptor",
                            "generation_descriptor",
                            "generations_descriptor",
                        ):
                            descriptor = getattr(binding, field)
                            if descriptor >= 0:
                                os.close(descriptor)
                                setattr(binding, field, -1)
                os.close(output_descriptor)

    def test_retained_binding_rejects_decoded_leaf_exchange_before_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir(mode=0o700)
            output_descriptor = os.open(
                output,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            result: QueryResult | None = None
            replaced = False

            def successful_run(argv, **kwargs):
                target = Path(argv[argv.index("--output") + 1])
                if argv[1:3] == ["query", "run"]:
                    target.write_bytes(b"bqrs-bytes")
                else:
                    target.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            real_pin = codeql_runner._pin_query_output_binding

            def replace_decoded_before_pin(
                results_descriptor,
                generation_name,
                decoded_name,
                capability,
                *args,
                **kwargs,
            ):
                nonlocal replaced
                generations_descriptor = os.open(
                    ".generations",
                    os.O_RDONLY | os.O_DIRECTORY,
                    dir_fd=results_descriptor,
                )
                try:
                    generation_descriptor = os.open(
                        generation_name,
                        os.O_RDONLY | os.O_DIRECTORY,
                        dir_fd=generations_descriptor,
                    )
                    try:
                        os.rename(
                            decoded_name,
                            f".{decoded_name}.genuine",
                            src_dir_fd=generation_descriptor,
                            dst_dir_fd=generation_descriptor,
                        )
                        forged = os.open(
                            decoded_name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=generation_descriptor,
                        )
                        try:
                            os.write(
                                forged,
                                self._decoded_entries_json("Forged").encode(
                                    "utf-8"
                                ),
                            )
                        finally:
                            os.close(forged)
                    finally:
                        os.close(generation_descriptor)
                finally:
                    os.close(generations_descriptor)
                replaced = True
                return real_pin(
                    results_descriptor,
                    generation_name,
                    decoded_name,
                    capability,
                    *args,
                    **kwargs,
                )

            try:
                with mock.patch.object(
                    codeql_runner,
                    "_pin_query_output_binding",
                    side_effect=replace_decoded_before_pin,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        result = run_query(
                            query,
                            database,
                            Path(f"/proc/self/fd/{output_descriptor}"),
                            output_descriptor=output_descriptor,
                            retain_output_binding=True,
                            subprocess_run=successful_run,
                        )
                self.assertTrue(replaced)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            finally:
                if result is not None:
                    binding = getattr(result, "_output_binding", None)
                    if binding is not None:
                        for field in (
                            "decoded_descriptor",
                            "generation_descriptor",
                            "generations_descriptor",
                        ):
                            descriptor = getattr(binding, field)
                            if descriptor >= 0:
                                os.close(descriptor)
                                setattr(binding, field, -1)
                os.close(output_descriptor)

    def test_retained_binding_rejects_decoded_leaf_exchange_before_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir(mode=0o700)
            output_descriptor = os.open(
                output,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            result: QueryResult | None = None
            replaced = False

            def successful_run(argv, **kwargs):
                target = Path(argv[argv.index("--output") + 1])
                if argv[1:3] == ["query", "run"]:
                    target.write_bytes(b"bqrs-bytes")
                else:
                    target.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            real_read = codeql_runner._read_decoded_json

            def replace_decoded_before_read(path, *args, **kwargs):
                nonlocal replaced
                genuine = path.with_name(f".{path.name}.genuine")
                path.rename(genuine)
                path.write_text(
                    self._decoded_entries_json("Forged"),
                    encoding="utf-8",
                )
                replaced = True
                return real_read(path, *args, **kwargs)

            try:
                with mock.patch.object(
                    codeql_runner,
                    "_read_decoded_json",
                    side_effect=replace_decoded_before_read,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        result = run_query(
                            query,
                            database,
                            Path(f"/proc/self/fd/{output_descriptor}"),
                            output_descriptor=output_descriptor,
                            retain_output_binding=True,
                            subprocess_run=successful_run,
                        )
                self.assertTrue(replaced)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            finally:
                if result is not None:
                    binding = getattr(result, "_output_binding", None)
                    if binding is not None:
                        for field in (
                            "decoded_descriptor",
                            "generation_descriptor",
                            "generations_descriptor",
                        ):
                            descriptor = getattr(binding, field)
                            if descriptor >= 0:
                                os.close(descriptor)
                                setattr(binding, field, -1)
                os.close(output_descriptor)

    def test_decoded_binding_factory_owns_fd_before_return_event(self):
        factory = getattr(
            codeql_runner,
            "_pin_decoded_output",
            None,
        )
        self.assertTrue(callable(factory))
        assert callable(factory)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decoded = root / "Entries.json"
            decoded.write_text(
                self._decoded_entries_json(), encoding="utf-8"
            )
            parent_descriptor = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            owner: list[object] = []
            injected = False

            def interrupt_factory_return(frame, event, _arg):
                nonlocal injected
                if (
                    not injected
                    and frame.f_code is factory.__code__
                    and event == "return"
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "decoded binding factory return interrupted"
                    )

            try:
                sys.setprofile(interrupt_factory_return)
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        factory(
                            parent_descriptor,
                            decoded.name,
                            codeql_runner.require_close_fd_once(),
                            owner,
                        )
                finally:
                    sys.setprofile(None)
                self.assertTrue(injected)
                self.assertEqual(len(owner), 1)
                snapshot = owner[0]
                descriptor = getattr(snapshot, "descriptor")
                os.fstat(descriptor)
            finally:
                if owner:
                    codeql_runner._release_query_output_descriptor(
                        getattr(owner[0], "descriptor"),
                        codeql_runner.require_close_fd_once(),
                    )
                os.close(parent_descriptor)

    def test_duplicate_factory_owns_fd_before_return_event(self):
        factory = getattr(
            codeql_runner,
            "_duplicate_owned_descriptor",
            None,
        )
        self.assertTrue(callable(factory))
        assert callable(factory)
        source = os.open("/dev/null", os.O_RDONLY)
        owner: list[int] = []
        injected = False

        def interrupt_factory_return(frame, event, _arg):
            nonlocal injected
            if (
                not injected
                and frame.f_code is factory.__code__
                and event == "return"
            ):
                injected = True
                raise KeyboardInterrupt(
                    "duplicate factory return interrupted"
                )

        try:
            sys.setprofile(interrupt_factory_return)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    factory(owner, source)
            finally:
                sys.setprofile(None)
            self.assertTrue(injected)
            self.assertEqual(len(owner), 1)
            os.fstat(owner[0])
        finally:
            for descriptor in owner:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(source)

    def test_tempfile_factory_owns_fd_and_path_before_return_event(self):
        factory = getattr(
            codeql_runner,
            "_create_owned_tempfile",
            None,
        )
        self.assertTrue(callable(factory))
        assert callable(factory)
        with tempfile.TemporaryDirectory() as temporary:
            owner: list[object] = []
            injected = False

            def interrupt_factory_return(frame, event, _arg):
                nonlocal injected
                if (
                    not injected
                    and frame.f_code is factory.__code__
                    and event == "return"
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "tempfile factory return interrupted"
                    )

            try:
                sys.setprofile(interrupt_factory_return)
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        factory(
                            owner,
                            directory=Path(temporary),
                            prefix=".owned-",
                            suffix=".tmp",
                        )
                finally:
                    sys.setprofile(None)
                self.assertTrue(injected)
                self.assertEqual(len(owner), 1)
                descriptor = getattr(owner[0], "descriptor")
                path = Path(getattr(owner[0], "path"))
                os.fstat(descriptor)
                self.assertTrue(path.is_file())
            finally:
                if owner:
                    descriptor = getattr(owner[0], "descriptor")
                    path = Path(getattr(owner[0], "path"))
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                    path.unlink(missing_ok=True)

    def test_binding_release_post_action_interrupt_continues_all_fds(self):
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(3)]
        capability = codeql_runner.require_close_fd_once()
        info = os.fstat(source)
        binding = codeql_runner._QueryOutputBinding(
            close_capability=capability,
            generations_descriptor=descriptors[2],
            generations_info=info,
            generation_name="Entries-normal",
            generation_descriptor=descriptors[1],
            generation_info=info,
            decoded_name="Entries.json",
            decoded_descriptor=descriptors[0],
            decoded_info=info,
            decoded_size=0,
            decoded_sha256="e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
            decoded_bytes=b"",
        )
        real_close_once = dosweb_filesystem.close_fd_once
        calls: list[int] = []

        def close_then_interrupt(descriptor, close_capability):
            real_close_once(descriptor, close_capability)
            calls.append(descriptor)
            if len(calls) == 1:
                raise KeyboardInterrupt(
                    "binding release post-action interrupt"
                )

        try:
            with mock.patch.object(
                dosweb_filesystem,
                "close_fd_once",
                side_effect=close_then_interrupt,
            ):
                released = codeql_runner._release_owned_query_output_binding(
                    binding
                )
            self.assertFalse(released)
            self.assertEqual(calls, descriptors)
            self.assertEqual(binding.decoded_descriptor, -1)
            self.assertEqual(binding.generation_descriptor, -1)
            self.assertEqual(binding.generations_descriptor, -1)
            for descriptor in descriptors:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
        finally:
            for descriptor in descriptors:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(source)

    def test_binding_release_precall_interrupt_falls_back_and_continues(self):
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(3)]
        capability = codeql_runner.require_close_fd_once()
        info = os.fstat(source)
        binding = codeql_runner._QueryOutputBinding(
            close_capability=capability,
            generations_descriptor=descriptors[2],
            generations_info=info,
            generation_name="Entries-normal",
            generation_descriptor=descriptors[1],
            generation_info=info,
            decoded_name="Entries.json",
            decoded_descriptor=descriptors[0],
            decoded_info=info,
            decoded_size=0,
            decoded_sha256="e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
            decoded_bytes=b"",
        )
        real_close_once = dosweb_filesystem.close_fd_once
        calls: list[int] = []

        def interrupt_before_first_close(descriptor, close_capability):
            calls.append(descriptor)
            if len(calls) == 1:
                raise dosweb_filesystem.CloseRangePreActionError(
                    errno.EINTR,
                    "binding release pre-call interrupt",
                )
            real_close_once(descriptor, close_capability)

        try:
            with mock.patch.object(
                dosweb_filesystem,
                "close_fd_once",
                side_effect=interrupt_before_first_close,
            ):
                released = codeql_runner._release_owned_query_output_binding(
                    binding
                )
            self.assertFalse(released)
            self.assertEqual(calls, descriptors)
            self.assertEqual(binding.decoded_descriptor, -1)
            self.assertEqual(binding.generation_descriptor, -1)
            self.assertEqual(binding.generations_descriptor, -1)
            for descriptor in descriptors:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
        finally:
            for descriptor in descriptors:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(source)

    def test_binding_release_defers_shared_helper_return_event(self):
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(3)]
        capability = codeql_runner.require_close_fd_once()
        info = os.fstat(source)
        binding = codeql_runner._QueryOutputBinding(
            close_capability=capability,
            generations_descriptor=descriptors[2],
            generations_info=info,
            generation_name="Entries-normal",
            generation_descriptor=descriptors[1],
            generation_info=info,
            decoded_name="Entries.json",
            decoded_descriptor=descriptors[0],
            decoded_info=info,
            decoded_size=0,
            decoded_sha256="e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
            decoded_bytes=b"",
        )
        injected = False

        def interrupt_helper_return(frame, event, _arg):
            nonlocal injected
            if (
                not injected
                and frame.f_code
                is dosweb_filesystem.release_owned_descriptor_once.__code__
                and event == "return"
            ):
                injected = True
                raise KeyboardInterrupt("shared release helper return interrupted")

        try:
            sys.setprofile(interrupt_helper_return)
            try:
                released = codeql_runner._release_owned_query_output_binding(
                    binding
                )
            finally:
                sys.setprofile(None)
            self.assertFalse(injected)
            self.assertTrue(released)
            self.assertEqual(binding.decoded_descriptor, -1)
            self.assertEqual(binding.generation_descriptor, -1)
            self.assertEqual(binding.generations_descriptor, -1)
            for descriptor in descriptors:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
        finally:
            for descriptor in descriptors:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(source)

    def test_binding_release_allocation_failure_falls_back_and_continues(self):
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(3)]
        capability = codeql_runner.require_close_fd_once()
        info = os.fstat(source)
        binding = codeql_runner._QueryOutputBinding(
            close_capability=capability,
            generations_descriptor=descriptors[2],
            generations_info=info,
            generation_name="Entries-normal",
            generation_descriptor=descriptors[1],
            generation_info=info,
            decoded_name="Entries.json",
            decoded_descriptor=descriptors[0],
            decoded_info=info,
            decoded_size=0,
            decoded_sha256="e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
            decoded_bytes=b"",
        )
        real_transaction = (
            dosweb_filesystem.DeferredCloseFdOnceOutcome
        )
        allocations = 0

        def fail_first_allocation():
            nonlocal allocations
            allocations += 1
            if allocations == 1:
                raise MemoryError("release transaction allocation failed")
            return real_transaction()

        try:
            with mock.patch.object(
                dosweb_filesystem,
                "DeferredCloseFdOnceOutcome",
                side_effect=fail_first_allocation,
            ):
                released = codeql_runner._release_owned_query_output_binding(
                    binding
                )
            self.assertFalse(released)
            self.assertEqual(allocations, 3)
            self.assertEqual(binding.decoded_descriptor, -1)
            self.assertEqual(binding.generation_descriptor, -1)
            self.assertEqual(binding.generations_descriptor, -1)
            for descriptor in descriptors:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
        finally:
            for descriptor in descriptors:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(source)

    def test_pre_action_fallback_close_postaction_interrupt_is_noexcept(self):
        descriptor = os.open("/dev/null", os.O_RDONLY)
        real_closerange = os.closerange
        capability = dosweb_filesystem.require_close_fd_once()
        pre_action_error = dosweb_filesystem.CloseRangePreActionError(
            5,
            "injected pre-action failure",
        )

        def close_then_interrupt(first: int, last: int) -> None:
            real_closerange(first, last)
            raise KeyboardInterrupt(
                "fallback close post-action interrupt"
            )

        try:
            with mock.patch.object(
                codeql_runner.os,
                "closerange",
                side_effect=close_then_interrupt,
            ):
                def fail_before_close(
                    _descriptor: int,
                    _capability: dosweb_filesystem.CloseRangeCapability,
                ) -> None:
                    raise pre_action_error

                outcome = dosweb_filesystem.release_owned_descriptor_once(
                    descriptor,
                    capability,
                    transaction=(
                        dosweb_filesystem.DeferredCloseFdOnceOutcome()
                    ),
                    close_fn=fail_before_close,
                )
            self.assertTrue(outcome.fallback_attempted)
            self.assertIs(outcome.failures[0], pre_action_error)
            self.assertIsInstance(outcome.failures[1], KeyboardInterrupt)
            with self.assertRaises(OSError):
                os.fstat(descriptor)
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def test_release_status_commit_precedes_post_close_allocation_failure(self):
        descriptor = os.open("/dev/null", os.O_RDONLY)
        capability = dosweb_filesystem.require_close_fd_once()
        real_close_once = dosweb_filesystem.close_fd_once
        reused: list[int] = []

        def close_then_reuse_and_fail(descriptor, close_capability):
            real_close_once(descriptor, close_capability)
            reused.append(os.open("/dev/null", os.O_RDONLY))
            raise MemoryError("post-close outcome allocation failed")

        try:
            outcome = dosweb_filesystem.release_owned_descriptor_once(
                descriptor,
                capability,
                transaction=(
                    dosweb_filesystem.DeferredCloseFdOnceOutcome()
                ),
                close_fn=close_then_reuse_and_fail,
            )
            self.assertEqual(reused, [descriptor])
            self.assertFalse(outcome.fallback_attempted)
            self.assertEqual(
                outcome.status,
                dosweb_filesystem.CloseFdOnceStatus.POST_ACTION_EXCEPTION,
            )
            os.fstat(reused[0])
        finally:
            for candidate in reused:
                try:
                    os.close(candidate)
                except OSError:
                    pass
            try:
                os.close(descriptor)
            except OSError:
                pass

    def test_pin_owner_post_action_exception_never_double_closes_reused_fd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results_descriptor = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            os.mkdir(
                ".generations",
                mode=0o700,
                dir_fd=results_descriptor,
            )
            generations_descriptor = os.open(
                ".generations",
                os.O_RDONLY | os.O_DIRECTORY,
                dir_fd=results_descriptor,
            )
            generations_info = os.fstat(generations_descriptor)
            os.mkdir(
                "Entries-normal",
                mode=0o700,
                dir_fd=generations_descriptor,
            )
            generation_descriptor = os.open(
                "Entries-normal",
                os.O_RDONLY | os.O_DIRECTORY,
                dir_fd=generations_descriptor,
            )
            generation_info = os.fstat(generation_descriptor)
            decoded_descriptor = os.open(
                "Entries.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=generation_descriptor,
            )
            os.write(decoded_descriptor, b"{}")
            os.close(decoded_descriptor)
            os.close(generation_descriptor)
            class AppendThenInterrupt(
                list[codeql_runner._QueryOutputBinding]
            ):
                def append(
                    self,
                    binding: codeql_runner._QueryOutputBinding,
                ) -> None:
                    super().append(binding)
                    raise KeyboardInterrupt("owner holder post-action")

            owned = AppendThenInterrupt()
            reused: list[int] = []

            try:
                with self.assertRaises(AnalyzerError):
                    codeql_runner._pin_query_output_binding(
                        results_descriptor,
                        "Entries-normal",
                        "Entries.json",
                        codeql_runner.require_close_fd_once(),
                        source_generations_descriptor=generations_descriptor,
                        expected_generations_info=generations_info,
                        expected_generation_info=generation_info,
                        owner_holder=owned,
                    )
                binding = owned[0]
                stale = (
                    binding.decoded_descriptor,
                    binding.generation_descriptor,
                    binding.generations_descriptor,
                )
                reused.extend(os.open("/dev/null", os.O_RDONLY) for _ in stale)
                codeql_runner._release_owned_query_output_binding(binding)
                for descriptor in reused:
                    os.fstat(descriptor)
            finally:
                for descriptor in reused:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                os.close(generations_descriptor)
                os.close(results_descriptor)

    def test_decode_failure_preserves_outputs_and_retains_hidden_quarantine(self):
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
            self._assert_retained_hidden_generation(output)

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

    def test_execution_snapshot_close_postaction_transfers_exact_tempfile(self):
        for interrupted_owner in ("source", "destination"):
            with self.subTest(interrupted_owner=interrupted_owner):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    query = root / "Entries.ql"
                    query.write_text("select 1", encoding="utf-8")
                    snapshot = root / "snapshot.ql"
                    snapshot.write_text("select 1", encoding="utf-8")
                    snapshot_info = snapshot.stat()
                    real_close_once = dosweb_filesystem.close_fd_once
                    injected = False

                    def close_then_interrupt(
                        descriptor: int,
                        capability,
                    ) -> None:
                        nonlocal injected
                        current = os.fstat(descriptor)
                        is_source = (
                            current.st_dev == snapshot_info.st_dev
                            and current.st_ino == snapshot_info.st_ino
                        )
                        real_close_once(descriptor, capability)
                        if not injected and is_source == (
                            interrupted_owner == "source"
                        ):
                            injected = True
                            raise KeyboardInterrupt(
                                "execution snapshot close interrupted"
                            )

                    execution: Path | None = None
                    try:
                        with mock.patch.object(
                            dosweb_filesystem,
                            "close_fd_once",
                            side_effect=close_then_interrupt,
                        ):
                            execution = codeql_runner._create_execution_snapshot(
                                snapshot,
                                query,
                                deadline=100.0,
                                monotonic=lambda: 0.0,
                            )

                        self.assertTrue(injected)
                        self.assertEqual(
                            execution.read_text(encoding="utf-8"),
                            "select 1",
                        )
                    finally:
                        if execution is not None:
                            execution.unlink(missing_ok=True)

                    self.assertEqual(
                        {candidate.name for candidate in root.iterdir()},
                        {"Entries.ql", "snapshot.ql"},
                    )

    def test_execution_snapshot_outcome_precall_interrupt_fails_and_cleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            snapshot = root / "snapshot.ql"
            snapshot.write_text("select 1", encoding="utf-8")
            baseline_fds = set(os.listdir("/proc/self/fd"))
            real_close_once = dosweb_filesystem.close_fd_once
            calls = 0

            def interrupt_before_outcome(descriptor, capability):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise dosweb_filesystem.CloseRangePreActionError(
                        errno.EINTR,
                        "execution snapshot close pre-action interrupted",
                    )
                real_close_once(descriptor, capability)

            with mock.patch.object(
                dosweb_filesystem,
                "close_fd_once",
                side_effect=interrupt_before_outcome,
            ):
                with self.assertRaises(
                    dosweb_filesystem.CloseRangePreActionError
                ):
                    codeql_runner._create_execution_snapshot(
                        snapshot,
                        query,
                        deadline=100.0,
                        monotonic=lambda: 0.0,
                    )

            self.assertEqual(calls, 2)
            self.assertEqual(
                {candidate.name for candidate in root.iterdir()},
                {"Entries.ql", "snapshot.ql"},
            )
            self.assertEqual(set(os.listdir("/proc/self/fd")), baseline_fds)

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
            self.assertEqual(raised.exception.details["stage"], "publication")
            self._assert_retained_hidden_generation(output)

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

            def recording_hash(
                path,
                deadline,
                monotonic,
                stage,
                close_capability=None,
            ):
                hash_stages.append(stage)
                return original_hash(
                    path,
                    deadline,
                    monotonic,
                    stage,
                    close_capability,
                )

            original_replace = os.replace

            def asserting_replace(source, destination, *args, **kwargs):
                self.assertEqual(hash_stages[-1], "publication")
                return original_replace(source, destination, *args, **kwargs)

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
            self._assert_retained_hidden_generation(output)

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
