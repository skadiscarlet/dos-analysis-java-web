from __future__ import annotations

import ast
from collections import Counter
import dis
import gc
import json
import errno
import hashlib
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import os
import weakref
from pathlib import Path
from unittest import mock

import yaml

import dosweb.codeql.database as codeql_database
import dosweb.codeql.runner as codeql_runner
import dosweb.filesystem as filesystem
from dosweb.codeql.runner import run_query
from dosweb.errors import AnalyzerError
from dosweb.pipeline import Pipeline, StageOutput


class CodeqlExecutionSnapshotTests(unittest.TestCase):
    def _database(self, root: Path) -> Path:
        database = root / "database"
        source = root / "source"
        (database / "db-java").mkdir(parents=True)
        source.mkdir()
        (database / "codeql-database.yml").write_text(
            yaml.safe_dump(
                {
                    "primaryLanguage": "java",
                    "sourceLocationPrefix": str(source),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (database / "db-java" / "database-relations.json").write_text(
            '{"relations":[]}', encoding="utf-8"
        )
        return database

    @staticmethod
    def _copy_clone(source: Path, destination: Path) -> None:
        shutil.copytree(source, destination, dirs_exist_ok=True)
        destination.chmod(0o700)

    @staticmethod
    def _decoded_entries_json() -> str:
        columns = [
            {"name": name, "kind": "String"}
            for name in (
                "framework", "protocol", "handler_fqn", "handler_file",
                "handler_start_line", "registration_kind", "registration_fqn",
                "registration_file", "registration_start_line", "route_or_event",
                "auth_context", "attacker_input_name", "attacker_input_type",
                "attacker_input_kind", "materialization_phase", "coverage_status",
                "coverage_note",
            )
        ]
        row = [
            "servlet", "http", "fixture.Handler.handle", "src/Handler.java", 10,
            "annotation_mapping", "fixture.Handler.handle", "src/Handler.java", 8,
            "/items", "unknown", "body", "byte[]", "request_body",
            "before_handler", "complete", "",
        ]
        return json.dumps({"#select": {"columns": columns, "tuples": [row]}})

    def _assert_only_hidden_generation_quarantine(
        self,
        generations: Path,
    ) -> set[str]:
        names = {candidate.name for candidate in generations.iterdir()}
        self.assertTrue(names)
        self.assertTrue(all(name.startswith(".") for name in names))
        self.assertFalse(any(name.startswith("Entries-") for name in names))
        return names

    def test_regular_output_never_uses_path_chmod_that_can_follow_a_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "result.bqrs"
            output.write_bytes(b"owned output\n")
            output.chmod(0o644)
            outside = root / "outside.bin"
            outside_bytes = b"outside output substitute\n"
            outside.write_bytes(outside_bytes)
            outside.chmod(0o640)
            held = root / "held-result.bqrs"
            real_chmod = os.chmod
            path_chmod_called = False

            def swap_on_path_chmod(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                mode: int,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal path_chmod_called
                if Path(path) == output and not path_chmod_called:
                    output.rename(held)
                    output.symlink_to(outside)
                    path_chmod_called = True
                real_chmod(path, mode, *args, **kwargs)

            with mock.patch.object(
                codeql_runner.os,
                "chmod",
                side_effect=swap_on_path_chmod,
            ):
                codeql_runner._require_regular_output(  # noqa: SLF001
                    output,
                    1024,
                    "query_run",
                )

            self.assertFalse(path_chmod_called)
            self.assertEqual(output.read_bytes(), b"owned output\n")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(outside.read_bytes(), outside_bytes)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o640)

    def test_regular_output_open_window_substitute_fails_without_chmod(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "result.bqrs"
            output.write_bytes(b"owned output\n")
            outside = root / "outside.bin"
            outside_bytes = b"outside output substitute\n"
            outside.write_bytes(outside_bytes)
            outside.chmod(0o640)
            held = root / "held-result.bqrs"
            real_open = os.open
            swapped = False

            def swap_before_output_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                nonlocal swapped
                if (
                    os.fsdecode(path) == output.name
                    and dir_fd is not None
                    and not swapped
                ):
                    output.rename(held)
                    output.symlink_to(outside)
                    swapped = True
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with (
                mock.patch.object(
                    codeql_runner.os,
                    "open",
                    side_effect=swap_before_output_open,
                ),
                self.assertRaises(AnalyzerError) as raised,
            ):
                codeql_runner._require_regular_output(  # noqa: SLF001
                    output,
                    1024,
                    "query_run",
                )

            self.assertTrue(swapped)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertEqual(outside.read_bytes(), outside_bytes)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o640)

    def test_generations_initialization_never_path_chmods_a_swap_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = codeql_database.validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir()
            generations = output / ".generations"
            generations.mkdir(mode=0o755)
            generations.chmod(0o755)
            outside = root / "outside"
            outside.mkdir(mode=0o755)
            outside.chmod(0o755)
            outside_file = outside / "KEEP.bin"
            outside_bytes = b"outside generations substitute\n"
            outside_file.write_bytes(outside_bytes)
            held = output / ".held-generations"
            real_chmod = os.chmod
            path_chmod_called = False
            calls = 0

            def successful_run(
                argv: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
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

            def swap_on_path_chmod(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                mode: int,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal path_chmod_called
                if Path(path) == generations and not path_chmod_called:
                    generations.rename(held)
                    generations.symlink_to(outside, target_is_directory=True)
                    path_chmod_called = True
                real_chmod(path, mode, *args, **kwargs)

            with mock.patch.object(
                codeql_runner.os,
                "chmod",
                side_effect=swap_on_path_chmod,
            ):
                run_query(
                    query,
                    database,
                    output,
                    subprocess_run=successful_run,
                )

            self.assertFalse(path_chmod_called)
            self.assertEqual(stat.S_IMODE(generations.stat().st_mode), 0o700)
            self.assertEqual(outside_file.read_bytes(), outside_bytes)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)

    def test_generations_open_window_substitute_fails_without_chmod(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = codeql_database.validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir()
            generations = output / ".generations"
            generations.mkdir(mode=0o755)
            generations.chmod(0o755)
            outside = root / "outside"
            outside.mkdir(mode=0o755)
            outside.chmod(0o755)
            outside_file = outside / "KEEP.bin"
            outside_bytes = b"outside generations substitute\n"
            outside_file.write_bytes(outside_bytes)
            held = output / ".held-generations"
            real_open = os.open
            swapped = False

            def swap_before_generations_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                nonlocal swapped
                if (
                    os.fsdecode(path) == generations.name
                    and dir_fd is not None
                    and flags & getattr(os, "O_DIRECTORY", 0)
                    and not swapped
                ):
                    generations.rename(held)
                    generations.symlink_to(outside, target_is_directory=True)
                    swapped = True
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with (
                mock.patch.object(
                    codeql_runner.os,
                    "open",
                    side_effect=swap_before_generations_open,
                ),
                self.assertRaises(AnalyzerError) as raised,
            ):
                run_query(
                    query,
                    database,
                    output,
                    subprocess_run=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                        [], 0, stdout="", stderr=""
                    ),
                )

            self.assertTrue(swapped)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertEqual(outside_file.read_bytes(), outside_bytes)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)

    def test_query_snapshot_never_uses_path_chmod_that_can_follow_a_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pending = root / "pending"
            pending.mkdir(mode=0o700)
            destination = pending / "Entries.ql"
            outside = root / "outside.ql"
            outside_bytes = b"outside snapshot substitute\n"
            outside.write_bytes(outside_bytes)
            outside.chmod(0o640)
            held = pending / "held-Entries.ql"
            real_chmod = os.chmod
            path_chmod_called = False

            def swap_on_path_chmod(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                mode: int,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal path_chmod_called
                if Path(path) == destination and not path_chmod_called:
                    destination.rename(held)
                    destination.symlink_to(outside)
                    path_chmod_called = True
                real_chmod(path, mode, *args, **kwargs)

            with mock.patch.object(
                codeql_runner.os,
                "chmod",
                side_effect=swap_on_path_chmod,
            ):
                codeql_runner._write_query_snapshot(  # noqa: SLF001
                    b"select 1\n",
                    destination,
                    10.0,
                    lambda: 0.0,
                )

            self.assertFalse(path_chmod_called)
            self.assertEqual(destination.read_bytes(), b"select 1\n")
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            self.assertEqual(outside.read_bytes(), outside_bytes)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o640)

    def test_query_release_preflight_precedes_query_source_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = codeql_database.validate_database(self._database(root))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            opened: list[object] = []
            real_open_owned = codeql_runner._open_owned_descriptor

            def record_open(*args: object, **kwargs: object) -> int:
                opened.append((args, kwargs))
                return real_open_owned(*args, **kwargs)

            with (
                mock.patch.object(
                    codeql_runner,
                    "require_close_fd_once",
                    side_effect=OSError("injected release preflight failure"),
                ) as preflight,
                mock.patch.object(
                    codeql_runner,
                    "_open_owned_descriptor",
                    side_effect=record_open,
                ),
                self.assertRaises(AnalyzerError) as raised,
            ):
                run_query(query, database, root / "output")

            preflight.assert_called_once_with()
            self.assertEqual(opened, [])
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertFalse((root / "output").exists())

    def test_query_source_release_defers_profile_and_never_recloses_aba_fd(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            query = root / "Entries.ql"
            query_bytes = b"select 1\n"
            query.write_bytes(query_bytes)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            real_close = os.close
            replacement_descriptor = -1
            injected = False

            def close_then_reuse(descriptor: int) -> None:
                nonlocal replacement_descriptor
                real_close(descriptor)
                replacement = os.open("/dev/null", os.O_RDONLY)
                if replacement != descriptor:
                    os.dup2(replacement, descriptor)
                    real_close(replacement)
                replacement_descriptor = descriptor

            def interrupt_close_return(frame, event, _arg):
                nonlocal injected
                if (
                    event == "return"
                    and frame.f_code is close_then_reuse.__code__
                    and not injected
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "query source close return was preempted"
                    )

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "close",
                    side_effect=close_then_reuse,
                ):
                    sys.setprofile(interrupt_close_return)
                    try:
                        resolved, payload, digest = (
                            codeql_runner._read_query_source(  # noqa: SLF001
                                query,
                                10.0,
                                lambda: 0.0,
                            )
                        )
                    finally:
                        sys.setprofile(None)

                self.assertFalse(injected)
                self.assertEqual(resolved, query.resolve(strict=True))
                self.assertEqual(payload, query_bytes)
                self.assertEqual(
                    digest,
                    hashlib.sha256(query_bytes).hexdigest(),
                )
                self.assertEqual(replacement_descriptor, -1)
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
            finally:
                sys.setprofile(None)
                if replacement_descriptor >= 0:
                    try:
                        real_close(replacement_descriptor)
                    except OSError:
                        pass

    def test_snapshot_root_release_defers_profile_and_never_recloses_aba_fd(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            real_close = os.close
            replacement_descriptor = -1
            injected = False
            returned: codeql_database.DatabaseInfo | None = None

            def close_once_then_reuse(
                descriptor: int,
                _capability: object,
            ) -> None:
                nonlocal replacement_descriptor
                real_close(descriptor)
                replacement = os.open("/dev/null", os.O_RDONLY)
                if replacement != descriptor:
                    os.dup2(replacement, descriptor)
                    real_close(replacement)
                replacement_descriptor = descriptor

            def interrupt_close_return(frame, event, _arg):
                nonlocal injected
                if (
                    event == "return"
                    and frame.f_code is close_once_then_reuse.__code__
                    and not injected
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "snapshot close return was preempted"
                    )

            try:
                with mock.patch.object(
                    codeql_database,
                    "close_fd_once",
                    side_effect=close_once_then_reuse,
                ):
                    sys.setprofile(interrupt_close_return)
                    try:
                        returned = (
                            codeql_database.create_execution_database_snapshot(
                                canonical,
                                output,
                                clone_tree=self._copy_clone,
                            )
                        )
                    finally:
                        sys.setprofile(None)

                self.assertFalse(injected)
                self.assertIsNotNone(returned)
                self.assertGreaterEqual(replacement_descriptor, 0)
                os.fstat(replacement_descriptor)
            finally:
                sys.setprofile(None)
                if replacement_descriptor >= 0:
                    try:
                        real_close(replacement_descriptor)
                    except OSError:
                        pass
                if returned is not None:
                    codeql_database.cleanup_execution_database_snapshot(
                        returned
                    )

    def test_snapshot_parent_cleanup_defers_profile_and_never_recloses_aba_fd(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            parent_descriptor = bound.execution.parent_descriptor
            real_close = os.close
            replacement_descriptor = -1
            injected = False

            def close_then_reuse(descriptor: int) -> None:
                nonlocal replacement_descriptor
                real_close(descriptor)
                if descriptor != parent_descriptor:
                    return
                replacement = os.open("/dev/null", os.O_RDONLY)
                if replacement != descriptor:
                    os.dup2(replacement, descriptor)
                    real_close(replacement)
                replacement_descriptor = descriptor

            def interrupt_close_return(frame, event, _arg):
                nonlocal injected
                if (
                    event == "return"
                    and frame.f_code is close_then_reuse.__code__
                    and replacement_descriptor >= 0
                    and not injected
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "snapshot parent close return was preempted"
                    )

            try:
                with mock.patch.object(
                    codeql_database.os,
                    "close",
                    side_effect=close_then_reuse,
                ):
                    sys.setprofile(interrupt_close_return)
                    try:
                        codeql_database.cleanup_execution_database_snapshot(
                            bound
                        )
                    finally:
                        sys.setprofile(None)

                self.assertFalse(injected)
                self.assertFalse(bound.execution.path.exists())
                self.assertEqual(replacement_descriptor, -1)
                codeql_database.cleanup_execution_database_snapshot(bound)
            finally:
                sys.setprofile(None)
                if replacement_descriptor >= 0:
                    try:
                        real_close(replacement_descriptor)
                    except OSError:
                        pass

    def test_snapshot_parent_and_root_open_return_are_owned_before_profile_or_trace(
        self,
    ) -> None:
        for acquisition in ("parent", "snapshot_root"):
            for instrumentation in ("profile", "trace"):
                with self.subTest(
                    acquisition=acquisition,
                    instrumentation=instrumentation,
                ), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    canonical = codeql_database.validate_database(
                        self._database(root)
                    )
                    output = root / "output"
                    output.mkdir()
                    real_open = os.open
                    target_descriptor = -1
                    output_open_count = 0
                    injected = False
                    returned: codeql_database.DatabaseInfo | None = None
                    failure: BaseException | None = None

                    def interruptible_open(
                        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                        flags: int,
                        *args: object,
                        **kwargs: object,
                    ) -> int:
                        nonlocal target_descriptor, output_open_count
                        descriptor = real_open(path, flags, *args, **kwargs)
                        is_target = False
                        if kwargs.get("dir_fd") is None and Path(path) == output:
                            output_open_count += 1
                            is_target = (
                                acquisition == "parent"
                                and output_open_count == 1
                            )
                        elif (
                            acquisition == "snapshot_root"
                            and kwargs.get("dir_fd") is not None
                            and isinstance(path, str)
                            and path.startswith(".codeql-execution-")
                        ):
                            is_target = True
                        if is_target:
                            target_descriptor = descriptor
                        return descriptor

                    def interrupt_open_return(frame, event, _arg):
                        nonlocal injected
                        if (
                            event
                            == (
                                "return"
                                if instrumentation == "profile"
                                else "line"
                            )
                            and frame.f_code is interruptible_open.__code__
                            and frame.f_locals.get("is_target") is True
                            and not injected
                        ):
                            injected = True
                            raise KeyboardInterrupt(
                                f"snapshot {acquisition} {instrumentation} return interruption"
                            )

                    baseline_fds = len(os.listdir("/proc/self/fd"))
                    try:
                        with mock.patch.object(
                            codeql_database.os,
                            "open",
                            side_effect=interruptible_open,
                        ):
                            if instrumentation == "profile":
                                sys.setprofile(interrupt_open_return)
                            else:
                                sys.settrace(interrupt_open_return)
                            try:
                                returned = codeql_database.create_execution_database_snapshot(
                                    canonical,
                                    output,
                                    clone_tree=self._copy_clone,
                                )
                            except BaseException as exc:
                                failure = exc
                            finally:
                                sys.setprofile(None)
                                sys.settrace(None)

                        self.assertIsNone(failure)
                        self.assertFalse(injected)
                        self.assertIsNotNone(returned)
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)
                        if returned is not None:
                            codeql_database.cleanup_execution_database_snapshot(
                                returned
                            )
                        if target_descriptor >= 0:
                            try:
                                real_opened = os.fstat(target_descriptor)
                            except OSError:
                                pass
                            else:
                                self.assertTrue(
                                    stat.S_ISDIR(real_opened.st_mode)
                                )
                                os.close(target_descriptor)
                        self.assertEqual(
                            len(os.listdir("/proc/self/fd")), baseline_fds
                        )

    def test_snapshot_parent_sigint_open_boundary_has_structural_owner(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            real_open = os.open
            target_descriptor = -1
            output_open_count = 0

            def interruptible_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal target_descriptor, output_open_count
                descriptor = real_open(path, flags, *args, **kwargs)
                if kwargs.get("dir_fd") is None and Path(path) == output:
                    output_open_count += 1
                    if output_open_count == 1:
                        target_descriptor = descriptor
                        os.kill(os.getpid(), signal.SIGINT)
                return descriptor

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with (
                    mock.patch.object(
                        codeql_database.os,
                        "open",
                        side_effect=interruptible_open,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database.create_execution_database_snapshot(
                        canonical,
                        output,
                        clone_tree=self._copy_clone,
                    )

                self.assertGreaterEqual(target_descriptor, 0)
                with self.assertRaises(OSError):
                    os.fstat(target_descriptor)
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
            finally:
                if target_descriptor >= 0:
                    try:
                        os.close(target_descriptor)
                    except OSError:
                        pass

    def test_snapshot_parent_interrupted_acquisition_release_never_recloses_aba_fd(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            real_open = os.open
            real_close = os.close
            target_descriptor = -1
            replacement_descriptor = -1
            output_open_count = 0
            close_calls = 0

            def interruptible_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal target_descriptor, output_open_count
                descriptor = real_open(path, flags, *args, **kwargs)
                if kwargs.get("dir_fd") is None and Path(path) == output:
                    output_open_count += 1
                    if output_open_count == 1:
                        target_descriptor = descriptor
                        os.kill(os.getpid(), signal.SIGINT)
                return descriptor

            def close_once_then_reuse(
                descriptor: int,
                _capability: object,
            ) -> None:
                nonlocal replacement_descriptor, close_calls
                close_calls += 1
                real_close(descriptor)
                replacement = real_open("/dev/null", os.O_RDONLY)
                if replacement != descriptor:
                    os.dup2(replacement, descriptor)
                    real_close(replacement)
                replacement_descriptor = descriptor
                raise KeyboardInterrupt(
                    "snapshot parent close completed before interruption"
                )

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with (
                    mock.patch.object(
                        codeql_database.os,
                        "open",
                        side_effect=interruptible_open,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "close_fd_once",
                        side_effect=close_once_then_reuse,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database.create_execution_database_snapshot(
                        canonical,
                        output,
                        clone_tree=self._copy_clone,
                    )

                self.assertEqual(close_calls, 1)
                self.assertEqual(replacement_descriptor, target_descriptor)
                os.fstat(replacement_descriptor)
                self.assertEqual(
                    os.readlink(f"/proc/self/fd/{replacement_descriptor}"),
                    "/dev/null",
                )
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
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )

    def test_snapshot_factory_has_no_pre_owner_root_open(self) -> None:
        module = ast.parse(
            Path(codeql_database.__file__).read_text(encoding="utf-8")
        )
        factory = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "create_execution_database_snapshot"
        )
        direct_open_lines: list[int] = []
        pre_owner_root_identity_lines: list[int] = []
        owned_open_lines: list[int] = []
        for node in ast.walk(factory):
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "open"
            ):
                direct_open_lines.append(node.lineno)
            elif isinstance(node.func, ast.Name):
                if node.func.id == "_tree_root_identity":
                    if (
                        node.args
                        and isinstance(node.args[0], ast.Name)
                        and node.args[0].id == "output"
                    ):
                        pre_owner_root_identity_lines.append(node.lineno)
                elif node.func.id == "open_owned_descriptor":
                    owned_open_lines.append(node.lineno)

        self.assertEqual(direct_open_lines, [])
        self.assertEqual(pre_owner_root_identity_lines, [])
        self.assertEqual(len(owned_open_lines), 2)

    def test_database_module_has_no_direct_open_or_close_calls(self) -> None:
        module = ast.parse(
            Path(codeql_database.__file__).read_text(encoding="utf-8")
        )
        direct_calls: list[tuple[str, int]] = []
        for node in ast.walk(module):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr in {"open", "close"}
            ):
                direct_calls.append((node.func.attr, node.lineno))
        self.assertEqual(direct_calls, [])

    def test_database_owner_release_calls_have_lexical_retry_pairs(self) -> None:
        module = ast.parse(
            Path(codeql_database.__file__).read_text(encoding="utf-8")
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
                == "_release_database_descriptor_owner_must_reach"
            )

        def direct_release_call(statements: list[ast.stmt]) -> ast.Call | None:
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
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return current.name
                current = parents.get(current)
            return None

        all_calls = [candidate for candidate in ast.walk(module) if is_release_call(candidate)]
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
                "_bounded_regular_bytes": 1,
                "_bounded_file_hash": 1,
                "_tree_root_identity": 1,
                "validate_directory": 2,
                "_validate_safe_tree": 1,
                "_reflink_file": 2,
                "clone_directory": 2,
                "_reflink_clone_tree": 2,
                "remove_contents": 2,
                "_remove_private_tree_at": 1,
                "_remove_private_tree": 1,
                "cleanup_stale_execution_database_snapshots": 1,
                "create_execution_database_snapshot": 1,
                "cleanup_failed_factory": 2,
            }
        )
        paired_call_ids = [id(call) for call in paired_calls]
        self.assertEqual(len(all_calls), 40)
        self.assertEqual(len(paired_calls), 40)
        self.assertEqual(len(set(paired_call_ids)), 40)
        self.assertEqual(set(paired_call_ids), {id(call) for call in all_calls})
        self.assertEqual(Counter(pair_owners), expected_pair_owners)

    def test_database_direct_release_calls_have_lexical_retry_pairs(self) -> None:
        module = ast.parse(
            Path(codeql_database.__file__).read_text(encoding="utf-8")
        )
        parents = {
            child: parent
            for parent in ast.walk(module)
            for child in ast.iter_child_nodes(parent)
        }

        def is_direct_release_call(candidate: ast.AST) -> bool:
            return (
                isinstance(candidate, ast.Call)
                and isinstance(candidate.func, ast.Name)
                and candidate.func.id
                == "_release_database_descriptor_must_reach"
            )

        def direct_release_call(statements: list[ast.stmt]) -> ast.Call | None:
            if (
                len(statements) != 1
                or not isinstance(statements[0], ast.Expr)
                or not is_direct_release_call(statements[0].value)
            ):
                return None
            return statements[0].value

        def owning_function(candidate: ast.AST) -> str | None:
            current = parents.get(candidate)
            while current is not None:
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return current.name
                current = parents.get(current)
            return None

        all_calls = [
            candidate
            for candidate in ast.walk(module)
            if is_direct_release_call(candidate)
        ]
        internal_calls = [
            call
            for call in all_calls
            if owning_function(call)
            == "_release_database_descriptor_owner_must_reach"
        ]
        external_calls = [call for call in all_calls if call not in internal_calls]
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

        paired_call_ids = [id(call) for call in paired_calls]
        self.assertEqual(len(all_calls), 5)
        self.assertEqual(len(internal_calls), 1)
        self.assertEqual(len(external_calls), 4)
        self.assertEqual(len(paired_calls), 4)
        self.assertEqual(len(set(paired_call_ids)), 4)
        self.assertEqual(
            set(paired_call_ids),
            {id(call) for call in external_calls},
        )
        self.assertEqual(
            Counter(pair_owners),
            Counter(
                {
                    "cleanup_failed_factory": 1,
                    "_cleanup_execution_database_binding_must_reach": 1,
                }
            ),
        )

    def test_tree_root_release_call_entry_interrupt_uses_lexical_retry(
        self,
    ) -> None:
        for instrumentation in ("profile", "trace"):
            with self.subTest(
                instrumentation=instrumentation
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                real_open = os.open
                target_descriptor = -1
                injected = False

                def capture_open(path, flags, *args, **kwargs):
                    nonlocal target_descriptor
                    descriptor = real_open(path, flags, *args, **kwargs)
                    if Path(path) == root:
                        target_descriptor = descriptor
                    return descriptor

                def interrupt_release_entry(frame, event, _arg):
                    nonlocal injected
                    if (
                        event == "call"
                        and frame.f_code
                        is codeql_database._release_database_descriptor_owner_must_reach.__code__
                        and not injected
                    ):
                        injected = True
                        raise KeyboardInterrupt(
                            f"tree root {instrumentation} release entry interruption"
                        )

                baseline_fds = len(os.listdir("/proc/self/fd"))
                try:
                    with mock.patch.object(
                        codeql_database.os,
                        "open",
                        side_effect=capture_open,
                    ):
                        if instrumentation == "profile":
                            sys.setprofile(interrupt_release_entry)
                        else:
                            sys.settrace(interrupt_release_entry)
                        try:
                            with self.assertRaises(KeyboardInterrupt):
                                codeql_database._tree_root_identity(root)
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

    def test_tree_root_release_sigint_at_first_call_uses_lexical_retry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_open = os.open
            real_release = (
                codeql_database._release_database_descriptor_owner_must_reach
            )
            target_descriptor = -1
            release_calls = 0

            def capture_open(path, flags, *args, **kwargs):
                nonlocal target_descriptor
                descriptor = real_open(path, flags, *args, **kwargs)
                if Path(path) == root:
                    target_descriptor = descriptor
                return descriptor

            def interrupt_first_release(owner, capability, transaction):
                nonlocal release_calls
                release_calls += 1
                if release_calls == 1:
                    os.kill(os.getpid(), signal.SIGINT)
                return real_release(owner, capability, transaction)

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with (
                    mock.patch.object(
                        codeql_database.os,
                        "open",
                        side_effect=capture_open,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "_release_database_descriptor_owner_must_reach",
                        side_effect=interrupt_first_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database._tree_root_identity(root)

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

    def test_tree_root_second_release_call_interrupts_after_first_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_open = os.open
            real_release = (
                codeql_database._release_database_descriptor_owner_must_reach
            )
            target_descriptor = -1
            release_calls = 0

            def capture_open(path, flags, *args, **kwargs):
                nonlocal target_descriptor
                descriptor = real_open(path, flags, *args, **kwargs)
                if Path(path) == root:
                    target_descriptor = descriptor
                return descriptor

            def interrupt_second_release(owner, capability, transaction):
                nonlocal release_calls
                release_calls += 1
                if release_calls == 2:
                    raise KeyboardInterrupt("second release call interrupted")
                return real_release(owner, capability, transaction)

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with (
                    mock.patch.object(
                        codeql_database.os,
                        "open",
                        side_effect=capture_open,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "_release_database_descriptor_owner_must_reach",
                        side_effect=interrupt_second_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database._tree_root_identity(root)

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

    def test_tree_root_lexical_retry_never_recloses_reused_aba_fd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_close = os.close
            real_open = os.open
            real_release = (
                codeql_database._release_database_descriptor_owner_must_reach
            )
            target_descriptor = -1
            replacement_descriptor = -1
            close_actions = 0
            release_calls = 0

            def capture_open(path, flags, *args, **kwargs):
                nonlocal target_descriptor
                descriptor = real_open(path, flags, *args, **kwargs)
                if Path(path) == root:
                    target_descriptor = descriptor
                return descriptor

            def close_then_reuse(candidate, _capability):
                nonlocal replacement_descriptor, close_actions
                close_actions += 1
                real_close(candidate)
                replacement = real_open("/dev/null", os.O_RDONLY)
                if replacement != candidate:
                    os.dup2(replacement, candidate)
                    real_close(replacement)
                replacement_descriptor = candidate
                raise KeyboardInterrupt("close post-action interruption")

            def count_release(owner, capability, transaction):
                nonlocal release_calls
                release_calls += 1
                return real_release(owner, capability, transaction)

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with (
                    mock.patch.object(
                        codeql_database.os,
                        "open",
                        side_effect=capture_open,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "close_fd_once",
                        side_effect=close_then_reuse,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "_release_database_descriptor_owner_must_reach",
                        side_effect=count_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database._tree_root_identity(root)

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

    def test_cleanup_binding_release_call_entry_uses_lexical_retry(self) -> None:
        for instrumentation in ("profile", "trace"):
            with self.subTest(
                instrumentation=instrumentation
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                baseline_fds = len(os.listdir("/proc/self/fd"))
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                binding = bound.execution
                assert binding is not None
                descriptor = binding.parent_descriptor
                injected = False

                def interrupt_release_entry(frame, event, _arg):
                    nonlocal injected
                    if (
                        event == "call"
                        and frame.f_code
                        is codeql_database._release_database_descriptor_must_reach.__code__
                        and frame.f_locals.get("transaction")
                        is binding.parent_release
                        and not injected
                    ):
                        injected = True
                        raise KeyboardInterrupt(
                            f"cleanup binding {instrumentation} release entry interruption"
                        )

                try:
                    if instrumentation == "profile":
                        sys.setprofile(interrupt_release_entry)
                    else:
                        sys.settrace(interrupt_release_entry)
                    try:
                        with self.assertRaises(KeyboardInterrupt):
                            codeql_database.cleanup_execution_database_snapshot(
                                bound
                            )
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)

                    self.assertTrue(injected)
                    self.assertTrue(binding.cleanup_state.closed)
                    self.assertFalse(binding.path.exists())
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)
                    codeql_database.cleanup_execution_database_snapshot(bound)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                finally:
                    sys.setprofile(None)
                    sys.settrace(None)
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_cleanup_never_commits_closed_before_release_finally_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            binding = bound.execution
            assert binding is not None
            descriptor = binding.parent_descriptor
            injected = False
            failure: BaseException | None = None

            def interrupt_premature_closed(frame, event, _arg):
                nonlocal injected
                if (
                    event == "line"
                    and frame.f_code
                    is codeql_database.cleanup_execution_database_snapshot.__code__
                    and binding.cleanup_state.closed
                    and binding.parent_release.status is None
                    and not injected
                ):
                    injected = True
                    raise KeyboardInterrupt("closed committed before release finally")
                return interrupt_premature_closed

            try:
                sys.settrace(interrupt_premature_closed)
                try:
                    codeql_database.cleanup_execution_database_snapshot(bound)
                except BaseException as exc:
                    failure = exc
                finally:
                    sys.settrace(None)

                codeql_database.cleanup_execution_database_snapshot(bound)
                self.assertFalse(injected)
                self.assertIsNone(failure)
                self.assertTrue(binding.cleanup_state.closed)
                self.assertFalse(binding.path.exists())
                self.assertTrue(binding.parent_release.explicitly_consumed)
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                sys.settrace(None)
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def test_factory_exception_never_commits_closed_before_cleanup_finally(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            owned: list[codeql_database.DatabaseInfo] = []
            injected = False
            failure: BaseException | None = None

            def retain_then_fail(database):
                owned.append(database)
                raise ValueError("owner callback interruption")

            def interrupt_premature_closed(frame, event, _arg):
                nonlocal injected
                binding = owned[0].execution if owned else None
                if (
                    event == "line"
                    and frame.f_code
                    is codeql_database.create_execution_database_snapshot.__code__
                    and binding is not None
                    and binding.cleanup_state.closed
                    and binding.parent_release.status is None
                    and not injected
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "factory closed committed before cleanup finally"
                    )
                return interrupt_premature_closed

            descriptor = -1
            try:
                sys.settrace(interrupt_premature_closed)
                try:
                    codeql_database.create_execution_database_snapshot(
                        canonical,
                        output,
                        clone_tree=self._copy_clone,
                        owner_callback=retain_then_fail,
                    )
                except BaseException as exc:
                    failure = exc
                finally:
                    sys.settrace(None)

                self.assertEqual(len(owned), 1)
                binding = owned[0].execution
                assert binding is not None
                descriptor = binding.parent_descriptor
                self.assertFalse(injected)
                self.assertIsInstance(failure, AnalyzerError)
                self.assertTrue(binding.cleanup_state.closed)
                self.assertFalse(binding.path.exists())
                self.assertTrue(binding.parent_release.explicitly_consumed)
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                sys.settrace(None)
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_factory_snapshot_release_escape_still_reaches_root_and_parent_cleanup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            real_open = codeql_database.open_owned_descriptor
            real_release = (
                codeql_database._release_database_descriptor_owner_must_reach
            )
            parent_descriptor = -1
            snapshot_descriptor = -1
            snapshot_release_calls = 0

            def capture_open(owner, path, flags, *args, **kwargs):
                nonlocal parent_descriptor, snapshot_descriptor
                descriptor = real_open(owner, path, flags, *args, **kwargs)
                if Path(path) == output and parent_descriptor < 0:
                    parent_descriptor = descriptor
                elif str(path).startswith(codeql_database._EXECUTION_PREFIX):
                    snapshot_descriptor = descriptor
                return descriptor

            def interrupt_snapshot_release(owner, capability, transaction):
                nonlocal snapshot_release_calls
                if owner and owner[0] == snapshot_descriptor:
                    snapshot_release_calls += 1
                    if snapshot_release_calls <= 3:
                        raise KeyboardInterrupt(
                            "snapshot release escaped before factory parent cleanup"
                        )
                return real_release(owner, capability, transaction)

            def interrupted_clone(_source: Path, destination: Path) -> None:
                (destination / "partial").write_text(
                    "partial", encoding="utf-8"
                )
                raise ValueError("force factory exception cleanup")

            try:
                with (
                    mock.patch.object(
                        codeql_database,
                        "open_owned_descriptor",
                        side_effect=capture_open,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "_release_database_descriptor_owner_must_reach",
                        side_effect=interrupt_snapshot_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database.create_execution_database_snapshot(
                        canonical,
                        output,
                        clone_tree=interrupted_clone,
                    )

                self.assertGreaterEqual(snapshot_release_calls, 4)
                self.assertGreaterEqual(parent_descriptor, 0)
                self.assertGreaterEqual(snapshot_descriptor, 0)
                with self.assertRaises(OSError):
                    os.fstat(snapshot_descriptor)
                with self.assertRaises(OSError):
                    os.fstat(parent_descriptor)
                self.assertFalse(list(output.glob(".codeql-execution-*")))
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                for descriptor in (snapshot_descriptor, parent_descriptor):
                    if descriptor >= 0:
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass

    def test_factory_exception_prologue_interrupt_still_cleans_parent_and_snapshot(
        self,
    ) -> None:
        for instrumentation in ("trace", "profile", "sigint"):
            with self.subTest(
                instrumentation=instrumentation
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                baseline_fds = len(os.listdir("/proc/self/fd"))
                owned: list[codeql_database.DatabaseInfo] = []
                injected = False

                def retain_then_fail(database):
                    owned.append(database)
                    raise ValueError("enter factory exception handler")

                def interrupt_handler_prologue(frame, event, _arg):
                    nonlocal injected
                    if (
                        frame.f_code
                        is codeql_database.create_execution_database_snapshot.__code__
                        and "exc" in frame.f_locals
                        and not injected
                        and (
                            (instrumentation != "profile" and event == "line")
                            or (instrumentation == "profile" and event == "c_call")
                        )
                    ):
                        injected = True
                        if instrumentation == "sigint":
                            os.kill(os.getpid(), signal.SIGINT)
                        else:
                            raise KeyboardInterrupt(
                                f"factory {instrumentation} handler prologue"
                            )
                    return interrupt_handler_prologue

                try:
                    if instrumentation == "profile":
                        sys.setprofile(interrupt_handler_prologue)
                    else:
                        sys.settrace(interrupt_handler_prologue)
                    try:
                        with self.assertRaises(KeyboardInterrupt):
                            codeql_database.create_execution_database_snapshot(
                                canonical,
                                output,
                                clone_tree=self._copy_clone,
                                owner_callback=retain_then_fail,
                            )
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)

                    self.assertTrue(injected)
                    self.assertEqual(len(owned), 1)
                    binding = owned[0].execution
                    assert binding is not None
                    self.assertTrue(binding.cleanup_state.closed)
                    self.assertFalse(binding.path.exists())
                    with self.assertRaises(OSError):
                        os.fstat(binding.parent_descriptor)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                finally:
                    sys.setprofile(None)
                    sys.settrace(None)
                    if owned:
                        binding = owned[0].execution
                        if (
                            binding is not None
                            and not binding.cleanup_state.closed
                        ):
                            codeql_database.cleanup_execution_database_snapshot(
                                owned[0]
                            )

    def test_cleanup_prologue_interrupt_uses_outer_fallback(self) -> None:
        for instrumentation in ("trace", "profile", "sigint"):
            with self.subTest(
                instrumentation=instrumentation
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                baseline_fds = len(os.listdir("/proc/self/fd"))
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                binding = bound.execution
                assert binding is not None
                injected = False

                def interrupt_cleanup_prologue(frame, event, _arg):
                    nonlocal injected
                    if (
                        frame.f_code
                        is codeql_database._cleanup_execution_database_snapshot.__code__
                        and frame.f_locals.get("binding") is binding
                        and not injected
                        and (
                            (instrumentation != "profile" and event == "line")
                            or (instrumentation == "profile" and event == "c_call")
                        )
                    ):
                        injected = True
                        if instrumentation == "sigint":
                            os.kill(os.getpid(), signal.SIGINT)
                        else:
                            raise KeyboardInterrupt(
                                f"cleanup {instrumentation} prologue"
                            )
                    return interrupt_cleanup_prologue

                try:
                    if instrumentation == "profile":
                        sys.setprofile(interrupt_cleanup_prologue)
                    else:
                        sys.settrace(interrupt_cleanup_prologue)
                    try:
                        with self.assertRaises(KeyboardInterrupt):
                            codeql_database.cleanup_execution_database_snapshot(
                                bound
                            )
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)

                    self.assertTrue(injected)
                    self.assertTrue(binding.cleanup_state.closed)
                    self.assertFalse(binding.path.exists())
                    with self.assertRaises(OSError):
                        os.fstat(binding.parent_descriptor)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                finally:
                    sys.setprofile(None)
                    sys.settrace(None)
                    if not binding.cleanup_state.closed:
                        codeql_database.cleanup_execution_database_snapshot(
                            bound
                        )

    def test_factory_success_restoration_or_next_line_interrupt_rolls_back_transfer(
        self,
    ) -> None:
        for instrumentation in (
            "profile_restoration_oserror",
            "profile_oserror_then_handler_line",
            "trace_next_return_line",
        ):
            for use_owner_callback in (False, True):
                with self.subTest(
                    instrumentation=instrumentation,
                    use_owner_callback=use_owner_callback,
                ), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    canonical = codeql_database.validate_database(
                        self._database(root)
                    )
                    output = root / "output"
                    output.mkdir()
                    baseline_fds = len(os.listdir("/proc/self/fd"))
                    captured: list[codeql_database.DatabaseInfo] = []
                    callback_owned: list[codeql_database.DatabaseInfo] = []
                    injected = False
                    helper_failure_injected = False
                    helper_returned = False
                    real_replace = codeql_database.replace

                    def capture_replace(instance, **changes):
                        result = real_replace(instance, **changes)
                        if (
                            isinstance(result, codeql_database.DatabaseInfo)
                            and result.execution is not None
                        ):
                            captured.append(result)
                        return result

                    def interrupt_helper_restoration(frame, event, _arg):
                        nonlocal helper_failure_injected, injected
                        action = frame.f_locals.get("action")
                        if (
                            not helper_failure_injected
                            and event == "return"
                            and frame.f_code
                            is codeql_database.run_with_deferred_interrupts.__code__
                            and getattr(action, "__name__", "")
                            == "complete_factory_success"
                        ):
                            helper_failure_injected = True
                            if instrumentation == "profile_restoration_oserror":
                                injected = True
                            raise OSError(
                                "factory success restoration interrupted"
                            )

                    def interrupt_success_boundary(frame, event, _arg):
                        nonlocal helper_returned, injected
                        if (
                            instrumentation == "trace_next_return_line"
                            and event == "return"
                            and frame.f_code
                            is codeql_database.run_with_deferred_interrupts.__code__
                            and getattr(
                                frame.f_locals.get("action"), "__name__", ""
                            )
                            == "complete_factory_success"
                        ):
                            helper_returned = True
                        elif (
                            not injected
                            and event == "line"
                            and frame.f_code
                            is codeql_database.create_execution_database_snapshot.__code__
                            and not frame.f_locals.get(
                                "parent_descriptor_owner"
                            )
                            and (
                                (
                                    instrumentation
                                    == "profile_oserror_then_handler_line"
                                    and helper_failure_injected
                                )
                                or (
                                    instrumentation
                                    == "trace_next_return_line"
                                    and helper_returned
                                )
                            )
                        ):
                            injected = True
                            raise KeyboardInterrupt(
                                f"factory success {instrumentation} interrupted"
                            )
                        return interrupt_success_boundary

                    owner_callback = (
                        callback_owned.append
                        if use_owner_callback
                        else None
                    )
                    try:
                        with mock.patch.object(
                            codeql_database,
                            "replace",
                            side_effect=capture_replace,
                        ):
                            if instrumentation.startswith("profile_"):
                                sys.setprofile(interrupt_helper_restoration)
                            if instrumentation != "profile_restoration_oserror":
                                sys.settrace(interrupt_success_boundary)
                            try:
                                expected_exception = (
                                    codeql_database.AnalyzerError
                                    if instrumentation
                                    == "profile_restoration_oserror"
                                    else KeyboardInterrupt
                                )
                                with self.assertRaises(expected_exception):
                                    codeql_database.create_execution_database_snapshot(
                                        canonical,
                                        output,
                                        clone_tree=self._copy_clone,
                                        owner_callback=owner_callback,
                                    )
                            finally:
                                sys.setprofile(None)
                                sys.settrace(None)

                        self.assertTrue(injected)
                        if instrumentation.startswith("profile_"):
                            self.assertTrue(helper_failure_injected)
                        self.assertEqual(len(captured), 1)
                        self.assertEqual(
                            len(callback_owned),
                            1 if use_owner_callback else 0,
                        )
                        binding = captured[0].execution
                        assert binding is not None
                        self.assertTrue(binding.cleanup_state.closed)
                        self.assertFalse(binding.path.exists())
                        with self.assertRaises(OSError):
                            os.fstat(binding.parent_descriptor)
                        self.assertEqual(
                            len(os.listdir("/proc/self/fd")), baseline_fds
                        )
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)
                        if captured:
                            binding = captured[0].execution
                            if (
                                binding is not None
                                and not binding.cleanup_state.closed
                            ):
                                codeql_database.cleanup_execution_database_snapshot(
                                    captured[0]
                                )

    def test_factory_success_flag_commit_has_finalizer_for_return_opcode_window(
        self,
    ) -> None:
        module = ast.parse(
            Path(codeql_database.__file__).read_text(encoding="utf-8")
        )
        factory = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef)
            and node.name == "create_execution_database_snapshot"
        )
        success_helper = next(
            node
            for node in ast.walk(factory)
            if isinstance(node, ast.FunctionDef)
            and node.name == "complete_factory_success"
        )
        helper_flag_stores = [
            node
            for node in ast.walk(success_helper)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == "factory_succeeded"
        ]
        self.assertEqual(helper_flag_stores, [])

        success_call = next(
            call
            for call in ast.walk(factory)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "run_with_deferred_interrupts"
            and call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "complete_factory_success"
        )
        parents = {
            child: parent
            for parent in ast.walk(factory)
            for child in ast.iter_child_nodes(parent)
        }
        success_owner = parents[success_call]
        while not isinstance(success_owner, ast.Try):
            success_owner = parents[success_owner]
        success_try = success_owner
        flag_assignments = [
            statement
            for statement in success_try.body
            if isinstance(statement, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "factory_succeeded"
                for target in statement.targets
            )
        ]
        returns = [
            statement
            for statement in success_try.body
            if isinstance(statement, ast.Return)
        ]
        self.assertEqual(len(flag_assignments), 1)
        self.assertEqual(len(returns), 1)
        self.assertEqual(
            success_try.body.index(returns[0]),
            success_try.body.index(flag_assignments[0]) + 1,
        )
        self.assertEqual(len(success_try.handlers), 1)
        self.assertEqual(
            [type(statement) for statement in success_try.handlers[0].body],
            [ast.Raise],
        )
        finalizers = [
            call
            for call in ast.walk(factory)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "weakref"
            and call.func.attr == "finalize"
        ]
        self.assertEqual(len(finalizers), 1)
        self.assertGreaterEqual(len(finalizers[0].args), 3)
        self.assertIsInstance(finalizers[0].args[0], ast.Name)
        self.assertEqual(finalizers[0].args[0].id, "owned_database")
        self.assertIsInstance(finalizers[0].args[1], ast.Name)
        self.assertEqual(
            finalizers[0].args[1].id,
            "_cleanup_execution_database_binding_finalizer",
        )
        self.assertIsInstance(finalizers[0].args[2], ast.Name)
        self.assertEqual(finalizers[0].args[2].id, "binding")
        self.assertLess(finalizers[0].lineno, success_call.lineno)

    def test_factory_return_opcode_interrupt_gc_finalizer_cleans_binding(
        self,
    ) -> None:
        return_offsets = {
            instruction.offset
            for instruction in dis.get_instructions(
                codeql_database.create_execution_database_snapshot
            )
            if instruction.opname == "RETURN_VALUE"
        }
        self.assertTrue(return_offsets)
        for instrumentation in ("opcode_keyboard", "opcode_sigint"):
            with self.subTest(
                instrumentation=instrumentation
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                baseline_fds = len(os.listdir("/proc/self/fd"))
                captured_binding: codeql_database.ExecutionDatabaseBinding | None = None
                injected = False
                real_replace = codeql_database.replace

                def capture_binding(instance, **changes):
                    nonlocal captured_binding
                    result = real_replace(instance, **changes)
                    if isinstance(
                        result.execution,
                        codeql_database.ExecutionDatabaseBinding,
                    ):
                        captured_binding = result.execution
                    return result

                def interrupt_return_opcode(frame, event, _arg):
                    nonlocal injected
                    if (
                        event == "call"
                        and frame.f_code
                        is codeql_database.create_execution_database_snapshot.__code__
                    ):
                        frame.f_trace_opcodes = True
                    elif (
                        not injected
                        and event == "opcode"
                        and frame.f_code
                        is codeql_database.create_execution_database_snapshot.__code__
                        and frame.f_lasti in return_offsets
                        and frame.f_locals.get("factory_succeeded") is True
                        and not frame.f_locals.get("parent_descriptor_owner")
                    ):
                        injected = True
                        if instrumentation == "opcode_sigint":
                            os.kill(os.getpid(), signal.SIGINT)
                        raise KeyboardInterrupt(
                            "factory return opcode interrupted"
                        )
                    return interrupt_return_opcode

                try:
                    with mock.patch.object(
                        codeql_database,
                        "replace",
                        side_effect=capture_binding,
                    ):
                        sys.settrace(interrupt_return_opcode)
                        try:
                            codeql_database.create_execution_database_snapshot(
                                canonical,
                                output,
                                clone_tree=self._copy_clone,
                            )
                        except KeyboardInterrupt:
                            pass
                        else:
                            self.fail("return opcode interruption was not raised")
                        finally:
                            sys.settrace(None)
                    self.assertTrue(injected)
                    self.assertIsNotNone(captured_binding)
                    assert captured_binding is not None
                    gc.collect()
                    self.assertTrue(captured_binding.cleanup_state.closed)
                    self.assertFalse(captured_binding.path.exists())
                    with self.assertRaises(OSError):
                        os.fstat(captured_binding.parent_descriptor)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                finally:
                    sys.settrace(None)
                    if (
                        captured_binding is not None
                        and not captured_binding.cleanup_state.closed
                    ):
                        codeql_database._cleanup_execution_database_binding_must_reach(
                            captured_binding
                        )

    def test_database_binding_gc_finalizer_does_not_reclose_aba_fd(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            binding = bound.execution
            assert binding is not None
            descriptor = binding.parent_descriptor
            codeql_database.cleanup_execution_database_snapshot(bound)
            replacement = os.open("/dev/null", os.O_RDONLY)
            if replacement != descriptor:
                os.dup2(replacement, descriptor)
                os.close(replacement)
                replacement = descriptor
            bound_ref = weakref.ref(bound)
            try:
                del bound
                gc.collect()
                self.assertIsNone(bound_ref())
                os.fstat(replacement)
            finally:
                os.close(replacement)

    def test_cleanup_binding_assignment_interrupt_reacquires_input_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            binding = bound.execution
            assert binding is not None
            module = ast.parse(
                Path(codeql_database.__file__).read_text(encoding="utf-8")
            )
            cleanup_function = next(
                node
                for node in ast.walk(module)
                if isinstance(node, ast.FunctionDef)
                and node.name == "cleanup_execution_database_snapshot"
            )
            outer_try = cleanup_function.body[0]
            assert isinstance(outer_try, ast.Try)
            first_owned_line = outer_try.body[0].lineno
            injected = False

            def interrupt_before_assignment(frame, event, _arg):
                nonlocal injected
                if (
                    not injected
                    and event == "line"
                    and frame.f_code
                    is codeql_database.cleanup_execution_database_snapshot.__code__
                    and frame.f_lineno == first_owned_line
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "cleanup binding assignment interrupted"
                    )
                return interrupt_before_assignment

            try:
                sys.settrace(interrupt_before_assignment)
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        codeql_database.cleanup_execution_database_snapshot(
                            bound
                        )
                finally:
                    sys.settrace(None)
                self.assertTrue(injected)
                self.assertTrue(binding.cleanup_state.closed)
                self.assertFalse(binding.path.exists())
                with self.assertRaises(OSError):
                    os.fstat(binding.parent_descriptor)
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                sys.settrace(None)
                if not binding.cleanup_state.closed:
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_cleanup_snapshot_first_structure_reacquires_only_from_input(
        self,
    ) -> None:
        module = ast.parse(
            Path(codeql_database.__file__).read_text(encoding="utf-8")
        )
        public_cleanup = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef)
            and node.name == "cleanup_execution_database_snapshot"
        )
        cleanup = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_cleanup_execution_database_snapshot"
        )
        self.assertIsInstance(public_cleanup.body[0], ast.Try)
        public_try = public_cleanup.body[0]
        assert isinstance(public_try, ast.Try)
        public_calls = [
            call
            for call in ast.walk(public_cleanup)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_cleanup_execution_database_snapshot"
        ]
        self.assertEqual(len(public_calls), 2)
        self.assertEqual(
            ast.dump(public_calls[0], include_attributes=False),
            ast.dump(public_calls[1], include_attributes=False),
        )
        self.assertIsInstance(cleanup.body[0], ast.Try)
        outer = cleanup.body[0]
        assert isinstance(outer, ast.Try)
        input_reacquisitions = [
            node
            for node in ast.walk(ast.Module(body=outer.finalbody))
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "database"
            and node.attr == "execution"
        ]
        binding_reads = [
            node
            for node in ast.walk(ast.Module(body=outer.finalbody))
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "binding"
        ]
        self.assertEqual(len(input_reacquisitions), 2)
        self.assertEqual(binding_reads, [])

    def test_public_cleanup_first_opcode_is_outside_exception_table(
        self,
    ) -> None:
        bytecode = dis.Bytecode(
            codeql_database.cleanup_execution_database_snapshot
        )
        instructions = list(bytecode)
        first_after_resume = next(
            instruction
            for instruction in instructions
            if instruction.opname != "RESUME"
        )
        self.assertEqual(first_after_resume.opname, "NOP")
        self.assertFalse(
            any(
                entry.start
                <= first_after_resume.offset
                < entry.end
                for entry in bytecode.exception_entries
            )
        )
        self.assertEqual(
            min(entry.start for entry in bytecode.exception_entries),
            4,
        )

    def test_cleanup_binding_release_sigint_uses_lexical_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            binding = bound.execution
            assert binding is not None
            descriptor = binding.parent_descriptor
            real_release = codeql_database._release_database_descriptor_must_reach
            release_calls = 0

            def interrupt_first_release(candidate, capability, transaction):
                nonlocal release_calls
                if transaction is binding.parent_release:
                    release_calls += 1
                    if release_calls == 1:
                        os.kill(os.getpid(), signal.SIGINT)
                return real_release(candidate, capability, transaction)

            try:
                with (
                    mock.patch.object(
                        codeql_database,
                        "_release_database_descriptor_must_reach",
                        side_effect=interrupt_first_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database.cleanup_execution_database_snapshot(bound)

                self.assertEqual(release_calls, 2)
                self.assertTrue(binding.cleanup_state.closed)
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
                codeql_database.cleanup_execution_database_snapshot(bound)
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def test_factory_post_transfer_exception_release_uses_lexical_retry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            owned: list[codeql_database.DatabaseInfo] = []
            real_transfer = codeql_database._transfer_database_descriptor_owner
            real_release = codeql_database._release_database_descriptor_must_reach
            release_calls = 0

            def transfer_then_interrupt(owner, descriptor):
                real_transfer(owner, descriptor)
                raise ValueError("post-transfer factory interruption")

            def interrupt_first_release(candidate, capability, transaction):
                nonlocal release_calls
                binding = owned[0].execution if owned else None
                if binding is not None and transaction is binding.parent_release:
                    release_calls += 1
                    if release_calls == 1:
                        raise KeyboardInterrupt("factory release entry interruption")
                return real_release(candidate, capability, transaction)

            descriptor = -1
            try:
                with (
                    mock.patch.object(
                        codeql_database,
                        "_transfer_database_descriptor_owner",
                        side_effect=transfer_then_interrupt,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "_release_database_descriptor_must_reach",
                        side_effect=interrupt_first_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database.create_execution_database_snapshot(
                        canonical,
                        output,
                        clone_tree=self._copy_clone,
                        owner_callback=owned.append,
                    )

                self.assertEqual(len(owned), 1)
                binding = owned[0].execution
                assert binding is not None
                descriptor = binding.parent_descriptor
                self.assertEqual(release_calls, 2)
                self.assertTrue(binding.cleanup_state.closed)
                self.assertFalse(binding.path.exists())
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_factory_cleanup_failure_release_uses_lexical_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            owned: list[codeql_database.DatabaseInfo] = []
            real_transfer = codeql_database._transfer_database_descriptor_owner
            real_release = codeql_database._release_database_descriptor_must_reach
            release_calls = 0

            def transfer_then_interrupt(owner, descriptor):
                real_transfer(owner, descriptor)
                raise ValueError("post-transfer factory interruption")

            def interrupt_first_release(candidate, capability, transaction):
                nonlocal release_calls
                binding = owned[0].execution if owned else None
                if binding is not None and transaction is binding.parent_release:
                    release_calls += 1
                    if release_calls == 1:
                        raise KeyboardInterrupt("cleanup-failure release interruption")
                return real_release(candidate, capability, transaction)

            descriptor = -1
            try:
                with (
                    mock.patch.object(
                        codeql_database,
                        "_transfer_database_descriptor_owner",
                        side_effect=transfer_then_interrupt,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "_remove_private_tree",
                        side_effect=OSError("injected cleanup failure"),
                    ),
                    mock.patch.object(
                        codeql_database,
                        "_release_database_descriptor_must_reach",
                        side_effect=interrupt_first_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database.create_execution_database_snapshot(
                        canonical,
                        output,
                        clone_tree=self._copy_clone,
                        owner_callback=owned.append,
                    )

                self.assertEqual(len(owned), 1)
                binding = owned[0].execution
                assert binding is not None
                descriptor = binding.parent_descriptor
                self.assertEqual(release_calls, 2)
                self.assertTrue(binding.cleanup_state.closed)
                self.assertTrue(binding.path.exists())
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_cleanup_binding_lexical_retry_never_recloses_aba_fd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            binding = bound.execution
            assert binding is not None
            descriptor = binding.parent_descriptor
            real_close = os.close
            real_open = os.open
            real_close_once = codeql_database.close_fd_once
            real_release = codeql_database._release_database_descriptor_must_reach
            replacement_descriptor = -1
            close_actions = 0
            release_calls = 0

            def close_then_reuse(candidate, capability):
                nonlocal replacement_descriptor, close_actions
                if candidate != descriptor:
                    return real_close_once(candidate, capability)
                close_actions += 1
                real_close(candidate)
                replacement = real_open("/dev/null", os.O_RDONLY)
                if replacement != candidate:
                    os.dup2(replacement, candidate)
                    real_close(replacement)
                replacement_descriptor = candidate
                raise KeyboardInterrupt("binding close post-action interruption")

            def count_release(candidate, capability, transaction):
                nonlocal release_calls
                if transaction is binding.parent_release:
                    release_calls += 1
                return real_release(candidate, capability, transaction)

            try:
                with (
                    mock.patch.object(
                        codeql_database,
                        "close_fd_once",
                        side_effect=close_then_reuse,
                    ),
                    mock.patch.object(
                        codeql_database,
                        "_release_database_descriptor_must_reach",
                        side_effect=count_release,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    codeql_database.cleanup_execution_database_snapshot(bound)

                self.assertEqual(release_calls, 2)
                self.assertEqual(close_actions, 1)
                self.assertEqual(replacement_descriptor, descriptor)
                self.assertTrue(binding.cleanup_state.closed)
                os.fstat(replacement_descriptor)
                codeql_database.cleanup_execution_database_snapshot(bound)
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
                else:
                    try:
                        real_close(descriptor)
                    except OSError:
                        pass
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_tree_root_identity_open_return_is_structurally_owned(self) -> None:
        for instrumentation in ("profile", "trace"):
            with self.subTest(
                instrumentation=instrumentation
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                real_open = os.open
                target_descriptor = -1
                injected = False
                failure: BaseException | None = None

                def interruptible_open(path, flags, *args, **kwargs):
                    nonlocal target_descriptor
                    descriptor = real_open(path, flags, *args, **kwargs)
                    is_target = Path(path) == root
                    if is_target:
                        target_descriptor = descriptor
                    return descriptor

                def interrupt_return(frame, event, _arg):
                    nonlocal injected
                    if (
                        event
                        == ("return" if instrumentation == "profile" else "line")
                        and frame.f_code is interruptible_open.__code__
                        and frame.f_locals.get("is_target") is True
                        and not injected
                    ):
                        injected = True
                        raise KeyboardInterrupt(
                            f"tree root {instrumentation} return interruption"
                        )

                baseline_fds = len(os.listdir("/proc/self/fd"))
                try:
                    with mock.patch.object(
                        codeql_database.os,
                        "open",
                        side_effect=interruptible_open,
                    ):
                        if instrumentation == "profile":
                            sys.setprofile(interrupt_return)
                        else:
                            sys.settrace(interrupt_return)
                        try:
                            codeql_database._tree_root_identity(root)
                        except BaseException as exc:
                            failure = exc
                        finally:
                            sys.setprofile(None)
                            sys.settrace(None)

                    self.assertIsNone(failure)
                    self.assertFalse(injected)
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

    def test_tree_root_identity_sigint_after_open_closes_owned_fd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_open = os.open
            target_descriptor = -1

            def interruptible_open(path, flags, *args, **kwargs):
                nonlocal target_descriptor
                descriptor = real_open(path, flags, *args, **kwargs)
                if Path(path) == root:
                    target_descriptor = descriptor
                    os.kill(os.getpid(), signal.SIGINT)
                return descriptor

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    codeql_database.os,
                    "open",
                    side_effect=interruptible_open,
                ), self.assertRaises(KeyboardInterrupt):
                    codeql_database._tree_root_identity(root)
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

    def test_nested_validation_and_clone_opens_defer_profile_and_trace(self) -> None:
        for operation in ("validation", "clone"):
            for instrumentation in ("profile", "trace"):
                with self.subTest(
                    operation=operation,
                    instrumentation=instrumentation,
                ), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source = root / "source"
                    nested = source / "nested"
                    nested.mkdir(parents=True)
                    (nested / "payload.bin").write_bytes(b"payload")
                    destination = root / "destination"
                    destination.mkdir()
                    real_open = os.open
                    target_descriptors: list[int] = []
                    injected = False
                    failure: BaseException | None = None

                    def interruptible_open(path, flags, *args, **kwargs):
                        descriptor = real_open(path, flags, *args, **kwargs)
                        is_target = (
                            kwargs.get("dir_fd") is not None
                            and os.fspath(path) == "nested"
                        )
                        if is_target:
                            target_descriptors.append(descriptor)
                        return descriptor

                    def interrupt_return(frame, event, _arg):
                        nonlocal injected
                        if (
                            event
                            == (
                                "return"
                                if instrumentation == "profile"
                                else "line"
                            )
                            and frame.f_code is interruptible_open.__code__
                            and frame.f_locals.get("is_target") is True
                            and not injected
                        ):
                            injected = True
                            raise KeyboardInterrupt(
                                f"{operation} child {instrumentation} interruption"
                            )

                    baseline_fds = len(os.listdir("/proc/self/fd"))
                    try:
                        with mock.patch.object(
                            codeql_database.os,
                            "open",
                            side_effect=interruptible_open,
                        ), mock.patch.object(
                            codeql_database.fcntl,
                            "ioctl",
                            return_value=0,
                        ):
                            if instrumentation == "profile":
                                sys.setprofile(interrupt_return)
                            else:
                                sys.settrace(interrupt_return)
                            try:
                                if operation == "validation":
                                    codeql_database._validate_safe_tree(
                                        source,
                                        require_owner=True,
                                    )
                                else:
                                    codeql_database._reflink_clone_tree(
                                        source,
                                        destination,
                                    )
                            except BaseException as exc:
                                failure = exc
                            finally:
                                sys.setprofile(None)
                                sys.settrace(None)

                        self.assertIsNone(failure)
                        self.assertFalse(injected)
                        self.assertTrue(target_descriptors)
                        for descriptor in target_descriptors:
                            with self.assertRaises(OSError):
                                os.fstat(descriptor)
                        self.assertEqual(
                            len(os.listdir("/proc/self/fd")), baseline_fds
                        )
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)
                        for descriptor in target_descriptors:
                            try:
                                os.close(descriptor)
                            except OSError:
                                pass

    def test_cleanup_child_sigint_open_boundary_has_structural_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / ".codeql-execution-test"
            nested = private / "nested"
            nested.mkdir(parents=True, mode=0o700)
            private.chmod(0o700)
            (nested / "payload.bin").write_bytes(b"payload")
            real_open = os.open
            target_descriptor = -1

            def interruptible_open(path, flags, *args, **kwargs):
                nonlocal target_descriptor
                descriptor = real_open(path, flags, *args, **kwargs)
                if (
                    kwargs.get("dir_fd") is not None
                    and os.fspath(path) == private.name
                ):
                    target_descriptor = descriptor
                    os.kill(os.getpid(), signal.SIGINT)
                return descriptor

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    codeql_database.os,
                    "open",
                    side_effect=interruptible_open,
                ), self.assertRaises(KeyboardInterrupt):
                    codeql_database._remove_private_tree(private)
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

    def test_snapshot_owner_release_cannot_be_interrupted_between_pop_and_owner(
        self,
    ) -> None:
        for instrumentation in ("profile", "trace"):
            with self.subTest(instrumentation=instrumentation):
                descriptor = os.open("/dev/null", os.O_RDONLY)
                owner = [descriptor]
                capability = codeql_database.require_close_fd_once()
                transaction = codeql_database.DeferredCloseFdOnceOutcome()
                injected = False
                failure: BaseException | None = None

                def interrupt_owner_pop(frame, event, arg):
                    nonlocal injected
                    if injected or frame.f_code is not codeql_database._release_database_descriptor_owner_must_reach.__code__:
                        return
                    if instrumentation == "profile":
                        matches = event == "c_return" and getattr(arg, "__name__", "") == "pop"
                    else:
                        matches = (
                            event == "line"
                            and frame.f_locals.get("descriptor") == descriptor
                            and not owner
                        )
                    if matches:
                        injected = True
                        raise KeyboardInterrupt(
                            f"snapshot owner {instrumentation} pop interruption"
                        )

                try:
                    if instrumentation == "profile":
                        sys.setprofile(interrupt_owner_pop)
                    else:
                        sys.settrace(interrupt_owner_pop)
                    try:
                        codeql_database._release_database_descriptor_owner_must_reach(
                            owner,
                            capability,
                            transaction,
                        )
                    except BaseException as exc:
                        failure = exc
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)

                    self.assertIsNone(failure)
                    self.assertFalse(injected)
                    self.assertEqual(owner, [])
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)
                finally:
                    sys.setprofile(None)
                    sys.settrace(None)
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_snapshot_owner_release_sigint_after_pop_keeps_structural_owner(
        self,
    ) -> None:
        descriptor = os.open("/dev/null", os.O_RDONLY)

        class InterruptingOwner(list[int]):
            def pop(self, index: int = -1) -> int:
                owned = super().pop(index)
                os.kill(os.getpid(), signal.SIGINT)
                return owned

        owner = InterruptingOwner([descriptor])
        capability = codeql_database.require_close_fd_once()
        transaction = codeql_database.DeferredCloseFdOnceOutcome()
        try:
            with self.assertRaises(KeyboardInterrupt):
                codeql_database._release_database_descriptor_owner_must_reach(
                    owner,
                    capability,
                    transaction,
                )
            self.assertEqual(owner, [])
            with self.assertRaises(OSError):
                os.fstat(descriptor)
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def test_snapshot_owner_release_clear_escape_never_recloses_aba_fd(
        self,
    ) -> None:
        for escape in ("before_clear", "after_clear"):
            with self.subTest(escape=escape):
                descriptor = os.open("/dev/null", os.O_RDONLY)
                owner = [descriptor]
                capability = codeql_database.require_close_fd_once()
                transaction = codeql_database.DeferredCloseFdOnceOutcome()
                real_close = os.close
                real_open = os.open
                real_deferred = codeql_database.run_with_deferred_interrupts
                replacement_descriptor = -1
                close_calls = 0
                clear_escape_injected = False

                def close_then_reuse(
                    candidate: int,
                    _capability: object,
                ) -> None:
                    nonlocal replacement_descriptor, close_calls
                    close_calls += 1
                    real_close(candidate)
                    replacement = real_open("/dev/null", os.O_RDONLY)
                    if replacement != candidate:
                        os.dup2(replacement, candidate)
                        real_close(replacement)
                    replacement_descriptor = candidate

                def interrupt_clear(action):
                    nonlocal clear_escape_injected
                    if (
                        action.__name__ == "clear_owner"
                        and not clear_escape_injected
                    ):
                        clear_escape_injected = True
                        if escape == "before_clear":
                            raise KeyboardInterrupt("clear setup interruption")
                        result = real_deferred(action)
                        raise KeyboardInterrupt("clear restoration interruption")
                    return real_deferred(action)

                try:
                    with mock.patch.object(
                        codeql_database,
                        "close_fd_once",
                        side_effect=close_then_reuse,
                    ), mock.patch.object(
                        codeql_database,
                        "run_with_deferred_interrupts",
                        side_effect=interrupt_clear,
                    ), self.assertRaises(KeyboardInterrupt):
                        codeql_database._release_database_descriptor_owner_must_reach(
                            owner,
                            capability,
                            transaction,
                        )

                    self.assertTrue(clear_escape_injected)
                    self.assertEqual(close_calls, 1)
                    self.assertEqual(replacement_descriptor, descriptor)
                    os.fstat(replacement_descriptor)

                    codeql_database._release_database_descriptor_owner_must_reach(
                        owner,
                        capability,
                        transaction,
                    )
                    self.assertEqual(owner, [])
                    self.assertEqual(close_calls, 1)
                    os.fstat(replacement_descriptor)
                finally:
                    if replacement_descriptor >= 0:
                        try:
                            real_close(replacement_descriptor)
                        except OSError:
                            pass
                    else:
                        try:
                            real_close(descriptor)
                        except OSError:
                            pass

    def test_close_fd_once_uses_one_fail_before_action_linux_syscall(self) -> None:
        for failure_kind in ("unavailable", "syscall_error"):
            with self.subTest(failure_kind=failure_kind):
                descriptor = os.open("/dev/null", os.O_RDONLY)
                try:
                    if failure_kind == "unavailable":
                        patcher = mock.patch.object(
                            filesystem.platform,
                            "machine",
                            return_value="unsupported",
                        )
                    else:
                        class FailingLibc:
                            @staticmethod
                            def syscall(*_args: object) -> int:
                                filesystem.ctypes.set_errno(errno.EIO)
                                return -1

                        patcher = mock.patch.object(
                            filesystem.ctypes,
                            "CDLL",
                            return_value=FailingLibc(),
                        )
                    with patcher, self.assertRaises(OSError) as raised:
                        filesystem.close_fd_once(descriptor)
                    self.assertEqual(
                        raised.exception.errno,
                        errno.ENOSYS
                        if failure_kind == "unavailable"
                        else errno.EIO,
                    )
                    if failure_kind == "syscall_error":
                        self.assertEqual(
                            type(raised.exception).__name__,
                            "CloseRangePreActionError",
                        )
                    os.fstat(descriptor)
                finally:
                    os.close(descriptor)

        descriptor = os.open("/dev/null", os.O_RDONLY)
        filesystem.close_fd_once(descriptor)
        with self.assertRaises(OSError) as closed:
            os.fstat(descriptor)
        self.assertEqual(closed.exception.errno, errno.EBADF)

    def test_close_range_capability_rejects_non_linux_same_arch(self) -> None:
        for sys_platform, system_name in (
            ("darwin", "Darwin"),
            ("freebsd14", "FreeBSD"),
            ("win32", "Windows"),
        ):
            with self.subTest(
                sys_platform=sys_platform,
                system_name=system_name,
            ), mock.patch.object(
                filesystem.sys,
                "platform",
                sys_platform,
            ), mock.patch.object(
                filesystem.platform,
                "system",
                return_value=system_name,
            ), mock.patch.object(
                filesystem.platform,
                "machine",
                return_value="x86_64",
            ), mock.patch.object(
                filesystem.ctypes,
                "CDLL",
            ) as cdll:
                with self.assertRaises(OSError) as raised:
                    filesystem.require_close_fd_once()
                self.assertEqual(raised.exception.errno, errno.ENOSYS)
                cdll.assert_not_called()

    def test_snapshot_close_range_preflight_precedes_owned_fd_creation(
        self,
    ) -> None:
        for failure_type in (OSError, KeyboardInterrupt):
            with self.subTest(failure_type=failure_type.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                expected = (
                    AnalyzerError
                    if failure_type is OSError
                    else KeyboardInterrupt
                )
                with mock.patch.object(
                    codeql_database,
                    "require_close_fd_once",
                    side_effect=failure_type("injected close-range preflight"),
                    create=True,
                ) as preflight:
                    with self.assertRaises(expected):
                        codeql_database.create_execution_database_snapshot(
                            canonical,
                            output,
                            clone_tree=self._copy_clone,
                        )

                preflight.assert_called_once_with()
                self.assertFalse(list(output.glob(".codeql-execution-*")))

    def test_snapshot_root_pre_action_failure_releases_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            real_fchmod = codeql_database.os.fchmod
            real_close = codeql_database.os.close
            real_close_fd_once = codeql_database.close_fd_once
            snapshot_descriptor = -1
            injected = False

            def record_snapshot_root(descriptor: int, mode: int) -> None:
                nonlocal snapshot_descriptor
                real_fchmod(descriptor, mode)
                opened = os.fstat(descriptor)
                if mode == 0o700 and stat.S_ISDIR(opened.st_mode):
                    snapshot_descriptor = descriptor

            def fail_before_snapshot_release(
                descriptor: int,
                capability: object,
            ) -> None:
                nonlocal injected
                if descriptor == snapshot_descriptor and not injected:
                    injected = True
                    raise filesystem.CloseRangePreActionError(
                        errno.EIO,
                        "injected snapshot root pre-action failure",
                    )
                real_close_fd_once(descriptor, capability)

            try:
                with mock.patch.object(
                    codeql_database.os,
                    "fchmod",
                    side_effect=record_snapshot_root,
                ), mock.patch.object(
                    codeql_database,
                    "close_fd_once",
                    side_effect=fail_before_snapshot_release,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        codeql_database.create_execution_database_snapshot(
                            canonical,
                            output,
                            clone_tree=self._copy_clone,
                        )

                self.assertTrue(injected)
                self.assertEqual(
                    raised.exception.code,
                    "CODEQL_EXECUTION_SNAPSHOT_FAILED",
                )
                self.assertFalse(list(output.glob(".codeql-execution-*")))
                with self.assertRaises(OSError) as closed:
                    os.fstat(snapshot_descriptor)
                self.assertEqual(closed.exception.errno, errno.EBADF)
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")),
                    baseline_fds,
                )
            finally:
                if snapshot_descriptor >= 0:
                    try:
                        real_close(snapshot_descriptor)
                    except OSError:
                        pass

    def test_snapshot_owner_callback_base_exception_cleans_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(
                self._database(root)
            )
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            owned: list[codeql_database.DatabaseInfo] = []

            def interrupt_owner(
                database: codeql_database.DatabaseInfo,
            ) -> None:
                owned.append(database)
                assert database.execution is not None
                raise KeyboardInterrupt(str(database.execution.path))

            with self.assertRaises(KeyboardInterrupt):
                codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                    owner_callback=interrupt_owner,
                )

            self.assertEqual(len(owned), 1)
            binding = owned[0].execution
            assert binding is not None
            self.assertFalse(binding.path.exists())
            with self.assertRaises(OSError) as closed:
                os.fstat(binding.parent_descriptor)
            self.assertEqual(closed.exception.errno, errno.EBADF)
            self.assertEqual(
                len(os.listdir("/proc/self/fd")),
                baseline_fds,
            )
            self.assertFalse(list(output.glob(".codeql-execution-*")))

    def test_query_mutates_private_execution_database_not_canonical_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            canonical_relations = canonical.path / "db-java" / "database-relations.json"
            original = canonical_relations.read_bytes()
            calls = 0

            def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    execution = Path(argv[argv.index("--database") + 1])
                    self.assertEqual(execution, bound.execution.path)
                    (execution / "db-java" / "database-relations.json").write_text(
                        '{"relations":["query-cache"]}', encoding="utf-8"
                    )
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(self._decoded_entries_json(), encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            try:
                result = run_query(query, bound, output / "query", subprocess_run=fake_run)
                self.assertEqual(result.bqrs_path.read_bytes(), b"bqrs")
                self.assertEqual(canonical_relations.read_bytes(), original)
                for result_path in (
                    result.query_path,
                    result.bqrs_path,
                    result.decoded_path,
                ):
                    with self.assertRaises(ValueError):
                        result_path.resolve().relative_to(bound.execution.path.resolve())
            finally:
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_query_output_equal_to_or_inside_execution_database_is_rejected_early(self) -> None:
        for nested in (False, True):
            with self.subTest(nested=nested), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=self._copy_clone
                )
                assert bound.execution is not None
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                forbidden_output = bound.execution.path
                if nested:
                    forbidden_output /= "query-output"
                subprocess_runner = mock.Mock(
                    return_value=subprocess.CompletedProcess(
                        [], 0, stdout="", stderr=""
                    )
                )
                try:
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            forbidden_output,
                            subprocess_run=subprocess_runner,
                        )
                    self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                    self.assertEqual(raised.exception.details.get("stage"), "validation")
                    self.assertNotIn(
                        str(bound.execution.path), repr(raised.exception.details)
                    )
                    subprocess_runner.assert_not_called()
                    if nested:
                        self.assertFalse(forbidden_output.exists())
                finally:
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_canonical_mutation_during_query_aborts_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")

            def mutate_canonical(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                destination = Path(argv[argv.index("--output") + 1])
                (canonical.path / "db-java" / "database-relations.json").write_text(
                    '{"relations":["canonical-mutation"]}', encoding="utf-8"
                )
                destination.write_bytes(b"unpublishable")
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            try:
                with self.assertRaises(AnalyzerError) as raised:
                    run_query(query, bound, output / "query", subprocess_run=mutate_canonical)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                generations = output / "query" / ".generations"
                names = self._assert_only_hidden_generation_quarantine(
                    generations
                )
                self.assertTrue(
                    any(name.startswith(".Entries.pending.") for name in names)
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                # The test deliberately poisons canonical identity; snapshot cleanup
                # must remain independently safe.
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_canonical_root_swap_between_identity_and_tree_binding_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            replacement = root / "replacement-database"
            shutil.copytree(canonical.path, replacement)
            (replacement / "db-java" / "database-relations.json").write_text(
                '{"relations":["different-fingerprint"]}', encoding="utf-8"
            )
            original = root / "original-database"
            real_validate_tree = codeql_database._validate_safe_tree
            swapped = False

            def swap_then_validate(
                path: Path,
                *,
                require_owner: bool,
                **kwargs: object,
            ):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    canonical.path.rename(original)
                    replacement.rename(canonical.path)
                return real_validate_tree(
                    path,
                    require_owner=require_owner,
                    **kwargs,
                )

            try:
                with mock.patch.object(
                    codeql_database,
                    "_validate_safe_tree",
                    side_effect=swap_then_validate,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        codeql_database.validate_canonical_database(
                            canonical,
                            actual_database=canonical,
                        )
                self.assertTrue(swapped)
                self.assertEqual(
                    raised.exception.details,
                    {
                        "stage": "canonical_validation",
                        "reason": "CANONICAL_DATABASE_CHANGED",
                    },
                )
                self.assertNotIn(str(canonical.path), repr(raised.exception.details))
            finally:
                if swapped:
                    canonical.path.rename(replacement)
                    original.rename(canonical.path)

    def test_canonical_drift_at_each_publication_checkpoint_never_survives(self) -> None:
        checkpoints = (
            "after_hash",
            "during_file_fsync",
            "before_replace",
            "after_replace",
            "during_generation_fsync",
        )
        for checkpoint in checkpoints:
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=self._copy_clone
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                mutated = False

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def mutate() -> None:
                    nonlocal mutated
                    if mutated:
                        return
                    mutated = True
                    (
                        canonical.path / "db-java" / "database-relations.json"
                    ).write_text('{"relations":["late-drift"]}', encoding="utf-8")

                original_hash = codeql_runner._deadline_file_sha256
                original_fsync_file = codeql_runner._fsync_file
                original_fsync_directory = codeql_runner._fsync_directory
                original_replace = os.replace

                def hashing(
                    path: Path,
                    deadline: float,
                    monotonic,
                    stage: str,
                    close_capability=None,
                ):
                    result = original_hash(
                        path,
                        deadline,
                        monotonic,
                        stage,
                        close_capability,
                    )
                    if checkpoint == "after_hash" and stage == "publication":
                        mutate()
                    return result

                def syncing_file(path: Path, close_capability=None) -> None:
                    original_fsync_file(path, close_capability)
                    if checkpoint == "during_file_fsync":
                        mutate()

                def replacing(
                    source: object,
                    destination: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    if checkpoint == "before_replace":
                        mutate()
                    original_replace(source, destination, *args, **kwargs)
                    if checkpoint == "after_replace":
                        mutate()

                def syncing_directory(
                    path: Path | int,
                    close_capability=None,
                ) -> None:
                    original_fsync_directory(path, close_capability)
                    if checkpoint == "during_generation_fsync" and isinstance(
                        path, int
                    ):
                        mutate()

                try:
                    with mock.patch.object(
                        codeql_runner, "_deadline_file_sha256", side_effect=hashing
                    ), mock.patch.object(
                        codeql_runner, "_fsync_file", side_effect=syncing_file
                    ), mock.patch.object(
                        codeql_runner.os, "replace", side_effect=replacing
                    ), mock.patch.object(
                        codeql_runner,
                        "_fsync_directory",
                        side_effect=syncing_directory,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )
                    self.assertTrue(mutated)
                    self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                    self.assertNotIn(
                        str(bound.execution.path), repr(raised.exception.details)
                    )
                    generations = output / "query" / ".generations"
                    self._assert_only_hidden_generation_quarantine(
                        generations
                    )
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_post_replace_drift_hides_normal_generation_before_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            real_replace = os.replace

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            def replace_then_drift(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                real_replace(source, destination, *args, **kwargs)
                if Path(destination).name.startswith("Entries-"):
                    (
                        canonical.path / "db-java" / "database-relations.json"
                    ).write_text('{"relations":["post-commit"]}', encoding="utf-8")

            cleanup_calls = 0

            def fail_rollback_cleanup(*_args: object, **_kwargs: object) -> None:
                nonlocal cleanup_calls
                cleanup_calls += 1
                raise OSError("injected rollback cleanup failure")

            try:
                with mock.patch.object(
                    codeql_runner.os, "replace", side_effect=replace_then_drift
                ), mock.patch.object(
                    codeql_runner,
                    "_cleanup_rollback_quarantine",
                    side_effect=fail_rollback_cleanup,
                    create=True,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )
                self.assertEqual(cleanup_calls, 1)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                generations = output / "query" / ".generations"
                names = {path.name for path in generations.iterdir()}
                self.assertFalse(any(name.startswith("Entries-") for name in names))
                self.assertTrue(any(name.startswith(".rollback-") for name in names))
            finally:
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_initial_rollback_failure_retries_through_final_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            rollback_calls = 0
            replaced = False
            real_replace = codeql_runner.os.replace
            real_rollback = codeql_runner._rollback_published_generation

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def replace_then_raise(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal replaced
                real_replace(source, destination, *args, **kwargs)
                if Path(destination).name.startswith("Entries-"):
                    replaced = True
                    raise OSError(
                        errno.EIO,
                        "injected post-publication failure",
                    )

            def fail_first_rollback(
                descriptor: int,
                rollback_state: object,
                close_capability=None,
            ) -> None:
                nonlocal rollback_calls
                rollback_calls += 1
                if rollback_calls == 1:
                    raise OSError(
                        errno.EIO,
                        "injected initial rollback rename failure",
                    )
                real_rollback(
                    descriptor,
                    rollback_state,
                    close_capability,
                )

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "replace",
                    side_effect=replace_then_raise,
                ), mock.patch.object(
                    codeql_runner,
                    "_rollback_published_generation",
                    side_effect=fail_first_rollback,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                self.assertTrue(replaced)
                self.assertGreaterEqual(rollback_calls, 2)
                self.assertEqual(
                    raised.exception.code,
                    "CODEQL_QUERY_FAILED",
                )
                generations = output / "query" / ".generations"
                self._assert_only_hidden_generation_quarantine(
                    generations
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")),
                    baseline_fds,
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_persistent_noreplace_failure_quarantines_published_generation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(
                self._database(root)
            )
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            replaced = False
            real_replace = codeql_runner.os.replace
            real_no_replace = codeql_runner.renameat2_no_replace
            real_stat = codeql_runner.os.stat
            competitor_descriptors: list[
                tuple[str, int, os.stat_result]
            ] = []

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def replace_then_raise(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal replaced
                real_replace(source, destination, *args, **kwargs)
                if Path(destination).name.startswith("Entries-"):
                    replaced = True
                    raise OSError(
                        errno.EIO,
                        "injected post-publication failure",
                    )

            def fail_published_no_replace(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                if source_name.startswith("Entries-"):
                    raise OSError(
                        errno.EIO,
                        "injected persistent no-replace failure",
                    )
                real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            def race_hidden_absence_check(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> os.stat_result:
                try:
                    return real_stat(path, *args, **kwargs)
                except FileNotFoundError:
                    name = os.fspath(path)
                    directory_fd = kwargs.get("dir_fd")
                    if (
                        isinstance(name, str)
                        and name.startswith(".rollback-")
                        and not name.startswith(
                            (
                                ".rollback-exchange-probe-",
                                ".rollback-slot-",
                            )
                        )
                        and isinstance(directory_fd, int)
                    ):
                        os.mkdir(name, mode=0o700, dir_fd=directory_fd)
                        info = real_stat(
                            name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                        descriptor = os.open(
                            name,
                            os.O_RDONLY | os.O_DIRECTORY,
                            dir_fd=directory_fd,
                        )
                        competitor_descriptors.append(
                            (name, descriptor, info)
                        )
                    raise

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "replace",
                    side_effect=replace_then_raise,
                ), mock.patch.object(
                    codeql_runner,
                    "renameat2_no_replace",
                    side_effect=fail_published_no_replace,
                ), mock.patch.object(
                    codeql_runner.os,
                    "stat",
                    side_effect=race_hidden_absence_check,
                ), mock.patch.object(
                    codeql_runner.os,
                    "rename",
                    side_effect=AssertionError(
                        "unsafe rollback rename fallback"
                    ),
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                self.assertTrue(replaced)
                self.assertEqual(
                    raised.exception.code,
                    "CODEQL_QUERY_FAILED",
                )
                generations = output / "query" / ".generations"
                names = {candidate.name for candidate in generations.iterdir()}
                normal = [
                    candidate
                    for candidate in generations.iterdir()
                    if candidate.name.startswith("Entries-")
                ]
                self.assertEqual(len(normal), 1)
                self.assertTrue(normal[0].is_dir())
                self.assertFalse(any(normal[0].iterdir()))
                self.assertTrue(
                    all(
                        name.startswith(".rollback-")
                        for name in names
                        if not name.startswith("Entries-")
                    )
                )
                self.assertGreaterEqual(len(competitor_descriptors), 1)
                for name, descriptor, expected in competitor_descriptors:
                    current = (generations / name).lstat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino),
                        (expected.st_dev, expected.st_ino),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (
                            expected.st_dev,
                            expected.st_ino,
                            expected.st_nlink,
                        ),
                    )
                    os.close(descriptor)
                competitor_descriptors.clear()
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")),
                    baseline_fds,
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                for _name, descriptor, _expected in competitor_descriptors:
                    os.close(descriptor)
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_post_exchange_faults_resume_bound_generation_rollback(
        self,
    ) -> None:
        for checkpoint in ("inode_check", "fsync", "rmdir"):
            with self.subTest(
                checkpoint=checkpoint
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                exchange_completed = False
                faulted = False
                real_replace = codeql_runner.os.replace
                real_no_replace = codeql_runner.renameat2_no_replace
                real_exchange = codeql_runner.renameat2_exchange
                real_stat = codeql_runner.os.stat
                real_fsync = codeql_runner.os.fsync
                real_rmdir = codeql_runner.os.rmdir

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def replace_then_raise(
                    source: object,
                    destination: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    real_replace(source, destination, *args, **kwargs)
                    if Path(destination).name.startswith("Entries-"):
                        raise OSError(
                            errno.EIO,
                            "injected post-publication failure",
                        )

                def fail_published_no_replace(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    if source_name.startswith("Entries-"):
                        raise OSError(
                            errno.EIO,
                            "injected persistent no-replace failure",
                        )
                    real_no_replace(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )

                def record_exchange(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    nonlocal exchange_completed
                    real_exchange(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )
                    if source_name.startswith("Entries-"):
                        exchange_completed = True

                def fail_inode_check_once(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> os.stat_result:
                    nonlocal faulted
                    name = os.fspath(path)
                    if (
                        checkpoint == "inode_check"
                        and exchange_completed
                        and not faulted
                        and isinstance(name, str)
                        and name.startswith(".rollback-slot-")
                    ):
                        faulted = True
                        raise OSError(errno.EIO, "injected inode-check failure")
                    return real_stat(path, *args, **kwargs)

                def fail_fsync_once(descriptor: int) -> None:
                    nonlocal faulted
                    if (
                        checkpoint == "fsync"
                        and exchange_completed
                        and not faulted
                    ):
                        faulted = True
                        raise OSError(errno.EIO, "injected exchange fsync failure")
                    real_fsync(descriptor)

                def fail_rmdir_once(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    nonlocal faulted
                    if (
                        checkpoint == "rmdir"
                        and exchange_completed
                        and not faulted
                        and os.fspath(path).startswith("Entries-")
                    ):
                        faulted = True
                        raise OSError(errno.EIO, "injected placeholder rmdir failure")
                    real_rmdir(path, *args, **kwargs)

                try:
                    with mock.patch.object(
                        codeql_runner.os,
                        "replace",
                        side_effect=replace_then_raise,
                    ), mock.patch.object(
                        codeql_runner,
                        "renameat2_no_replace",
                        side_effect=fail_published_no_replace,
                    ), mock.patch.object(
                        codeql_runner,
                        "renameat2_exchange",
                        side_effect=record_exchange,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "stat",
                        side_effect=fail_inode_check_once,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "fsync",
                        side_effect=fail_fsync_once,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "rmdir",
                        side_effect=fail_rmdir_once,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    self.assertTrue(exchange_completed)
                    if checkpoint == "rmdir":
                        self.assertFalse(faulted)
                    else:
                        self.assertTrue(faulted)
                    self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                    generations = output / "query" / ".generations"
                    normal = [
                        candidate
                        for candidate in generations.iterdir()
                        if candidate.name.startswith("Entries-")
                    ]
                    self.assertEqual(len(normal), 1)
                    self.assertTrue(normal[0].is_dir())
                    self.assertFalse(any(normal[0].iterdir()))
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")),
                        baseline_fds,
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_post_replace_rollback_quarantine_retries_noreplace_target_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            real_replace = os.replace
            real_no_replace = getattr(codeql_runner, "renameat2_no_replace", None)

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                nonlocal calls
                calls += 1
                destination = Path(argv[argv.index("--output") + 1])
                if calls == 1:
                    destination.write_bytes(b"bqrs")
                else:
                    destination.write_text(
                        self._decoded_entries_json(), encoding="utf-8"
                    )
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            def replace_then_drift(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                real_replace(source, destination, *args, **kwargs)
                if Path(destination).name.startswith("Entries-"):
                    (
                        canonical.path / "db-java" / "database-relations.json"
                    ).write_text('{"relations":["post-commit"]}', encoding="utf-8")

            rename_calls = 0

            def race_first_target(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal rename_calls
                if source_name.startswith("Entries-"):
                    rename_calls += 1
                    if rename_calls == 1:
                        os.mkdir(
                            destination_name,
                            mode=0o700,
                            dir_fd=destination_directory_fd,
                        )
                if real_no_replace is None:
                    raise OSError(errno.ENOSYS, "missing no-replace primitive")
                real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            try:
                with mock.patch.object(
                    codeql_runner.os, "replace", side_effect=replace_then_drift
                ), mock.patch.object(
                    codeql_runner,
                    "renameat2_no_replace",
                    side_effect=race_first_target,
                    create=True,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )
                self.assertGreaterEqual(rename_calls, 2)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                generations = output / "query" / ".generations"
                names = {path.name for path in generations.iterdir()}
                self.assertFalse(any(name.startswith("Entries-") for name in names))
                self.assertTrue(any(name.startswith(".rollback-") for name in names))
            finally:
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_noreplace_capability_errors_abort_before_normal_generation_publication(
        self,
    ) -> None:
        for error_number in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            with self.subTest(
                error_number=error_number
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=self._copy_clone
                )
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                publication_replace_calls = 0
                rollback_cleanup_calls = 0
                real_replace = os.replace

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def replace_then_drift(
                    source: object,
                    destination: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    nonlocal publication_replace_calls
                    publication_replace_calls += 1
                    real_replace(source, destination, *args, **kwargs)
                    if Path(destination).name.startswith("Entries-"):
                        (
                            canonical.path / "db-java" / "database-relations.json"
                        ).write_text(
                            '{"relations":["post-commit"]}', encoding="utf-8"
                        )

                def fail_rollback_cleanup(
                    *_args: object, **_kwargs: object
                ) -> None:
                    nonlocal rollback_cleanup_calls
                    rollback_cleanup_calls += 1
                    raise OSError("injected rollback cleanup failure")

                try:
                    with mock.patch.object(
                        codeql_runner.os, "replace", side_effect=replace_then_drift
                    ), mock.patch.object(
                        codeql_runner,
                        "renameat2_no_replace",
                        side_effect=OSError(
                            error_number, "injected no-replace capability error"
                        ),
                    ), mock.patch.object(
                        codeql_runner,
                        "_cleanup_rollback_quarantine",
                        side_effect=fail_rollback_cleanup,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "rename",
                        side_effect=AssertionError("unsafe rollback rename fallback"),
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )
                    self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                    self.assertEqual(publication_replace_calls, 0)
                    self.assertEqual(rollback_cleanup_calls, 0)
                    generations = output / "query" / ".generations"
                    names = {path.name for path in generations.iterdir()}
                    self.assertFalse(
                        any(name.startswith("Entries-") for name in names)
                    )
                finally:
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_exchange_capability_error_aborts_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            publication_replace_calls = 0
            real_replace = codeql_runner.os.replace

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def record_publication_replace(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal publication_replace_calls
                publication_replace_calls += 1
                real_replace(source, destination, *args, **kwargs)

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "replace",
                    side_effect=record_publication_replace,
                ), mock.patch.object(
                    codeql_runner,
                    "renameat2_exchange",
                    side_effect=OSError(
                        errno.ENOSYS,
                        "injected exchange capability error",
                    ),
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertEqual(publication_replace_calls, 0)
                generations = output / "query" / ".generations"
                names = self._assert_only_hidden_generation_quarantine(
                    generations
                )
                self.assertTrue(
                    any(name.startswith(".Entries.pending.") for name in names)
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_post_replace_parent_swap_rolls_back_through_pinned_generations_fd(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            real_replace = os.replace
            generations = output / "query" / ".generations"
            moved_generations = output / "query" / ".generations-original"
            real_rename = os.rename
            swapped = False

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def replace_then_swap_parent(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal swapped
                real_replace(source, destination, *args, **kwargs)
                if not swapped and Path(destination).name.startswith("Entries-"):
                    real_rename(generations, moved_generations)
                    generations.mkdir(mode=0o700)
                    (
                        canonical.path / "db-java" / "database-relations.json"
                    ).write_text(
                        '{"relations":["post-commit"]}', encoding="utf-8"
                    )
                    swapped = True

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "replace",
                    side_effect=replace_then_swap_parent,
                ), mock.patch.object(
                    codeql_runner.os,
                    "rename",
                    side_effect=AssertionError("unsafe rollback rename fallback"),
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )
                self.assertTrue(swapped)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                for directory in (moved_generations, generations):
                    names = {path.name for path in directory.iterdir()}
                    self.assertFalse(
                        any(name.startswith("Entries-") for name in names)
                    )
            finally:
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_replace_then_raise_rolls_back_published_generation(self) -> None:
        for failure_type in (OSError, KeyboardInterrupt):
            with self.subTest(
                failure_type=failure_type.__name__
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=self._copy_clone
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                real_replace = os.replace

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def replace_then_raise(
                    source: object,
                    destination: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    real_replace(source, destination, *args, **kwargs)
                    raise failure_type("injected post-replace failure")

                try:
                    with mock.patch.object(
                        codeql_runner.os,
                        "replace",
                        side_effect=replace_then_raise,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "rename",
                        side_effect=AssertionError(
                            "unsafe rollback rename fallback"
                        ),
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )
                    self.assertEqual(
                        raised.exception.code, "CODEQL_QUERY_FAILED"
                    )
                    generations = output / "query" / ".generations"
                    self._assert_only_hidden_generation_quarantine(
                        generations
                    )
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_publication_replace_return_interrupt_rebuilds_transaction_state(
        self,
    ) -> None:
        for fail_first_rebuild in (False, True):
            with self.subTest(
                fail_first_rebuild=fail_first_rebuild
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                armed = False
                interrupted = False
                rebuild_calls = 0
                real_replace = codeql_runner.os.replace
                real_rebuild = codeql_runner._publication_replace_completed

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def replace_and_arm(
                    source: object,
                    destination: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    nonlocal armed
                    real_replace(source, destination, *args, **kwargs)
                    if Path(destination).name.startswith("Entries-"):
                        armed = True

                def interrupt_on_replace_return(frame, event, _arg):
                    nonlocal armed, interrupted
                    if (
                        armed
                        and event == "return"
                        and frame.f_code is replace_and_arm.__code__
                    ):
                        armed = False
                        interrupted = True
                        raise KeyboardInterrupt(
                            str(root / ".private-publication-return")
                        )
                    return interrupt_on_replace_return

                def fail_initial_rebuild(
                    *args: object,
                    **kwargs: object,
                ) -> bool:
                    nonlocal rebuild_calls
                    rebuild_calls += 1
                    if fail_first_rebuild and rebuild_calls == 1:
                        raise OSError(
                            errno.EIO,
                            "injected first publication-state rebuild failure",
                        )
                    return real_rebuild(*args, **kwargs)

                try:
                    with mock.patch.object(
                        codeql_runner.os,
                        "replace",
                        side_effect=replace_and_arm,
                    ), mock.patch.object(
                        codeql_runner,
                        "_publication_replace_completed",
                        side_effect=fail_initial_rebuild,
                    ):
                        sys.setprofile(interrupt_on_replace_return)
                        with self.assertRaises(
                            (AnalyzerError, KeyboardInterrupt)
                        ):
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )
                finally:
                    sys.setprofile(None)

                try:
                    self.assertTrue(interrupted)
                    self.assertGreaterEqual(rebuild_calls, 1)
                    generations = output / "query" / ".generations"
                    self.assertFalse(
                        any(
                            candidate.name.startswith("Entries-")
                            for candidate in generations.iterdir()
                        )
                    )
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")),
                        baseline_fds,
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_recreated_pending_name_is_preserved_and_fails_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            real_replace = codeql_runner.os.replace
            real_stat = codeql_runner.os.stat
            competitor: tuple[str, int, os.stat_result] | None = None

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def replace_then_raise(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                real_replace(source, destination, *args, **kwargs)
                if Path(destination).name.startswith("Entries-"):
                    raise OSError(
                        errno.EIO,
                        "injected post-publication failure",
                    )

            def recreate_pending_after_absence(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> os.stat_result:
                nonlocal competitor
                try:
                    return real_stat(path, *args, **kwargs)
                except FileNotFoundError:
                    name = os.fspath(path)
                    directory_fd = kwargs.get("dir_fd")
                    if (
                        competitor is None
                        and isinstance(name, str)
                        and name.startswith(".Entries.pending.")
                        and isinstance(directory_fd, int)
                    ):
                        os.mkdir(name, mode=0o700, dir_fd=directory_fd)
                        descriptor = os.open(
                            name,
                            os.O_RDONLY | os.O_DIRECTORY,
                            dir_fd=directory_fd,
                        )
                        marker_fd = os.open(
                            "competitor-marker",
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=descriptor,
                        )
                        os.close(marker_fd)
                        info = real_stat(
                            name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                        competitor = (name, descriptor, info)
                    raise

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "replace",
                    side_effect=replace_then_raise,
                ), mock.patch.object(
                    codeql_runner.os,
                    "stat",
                    side_effect=recreate_pending_after_absence,
                ):
                    with self.assertRaises(AnalyzerError):
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                self.assertIsNotNone(competitor)
                assert competitor is not None
                name, descriptor, expected = competitor
                generations = output / "query" / ".generations"
                current = (generations / name).lstat()
                opened = os.fstat(descriptor)
                self.assertEqual(
                    (current.st_dev, current.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
                self.assertEqual(
                    (opened.st_dev, opened.st_ino, opened.st_nlink),
                    (expected.st_dev, expected.st_ino, expected.st_nlink),
                )
                self.assertFalse(
                    any(
                        candidate.name.startswith("Entries-")
                        for candidate in generations.iterdir()
                    )
                )
                os.close(descriptor)
                competitor = None
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")),
                    baseline_fds,
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                if competitor is not None:
                    os.close(competitor[1])
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_persistent_publication_rebuild_failure_hides_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            rebuild_calls = 0
            cleanup_calls = 0
            real_replace = codeql_runner.os.replace

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def replace_then_raise(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                real_replace(source, destination, *args, **kwargs)
                if Path(destination).name.startswith("Entries-"):
                    raise OSError(
                        errno.EIO,
                        "injected post-publication failure",
                    )

            def fail_rebuild(*_args: object, **_kwargs: object) -> bool:
                nonlocal rebuild_calls
                rebuild_calls += 1
                raise OSError(
                    errno.EIO,
                    "injected persistent publication-state rebuild failure",
                )

            def fail_quarantine_cleanup(
                *_args: object, **_kwargs: object
            ) -> None:
                nonlocal cleanup_calls
                cleanup_calls += 1
                raise OSError(
                    errno.EIO,
                    "injected persistent quarantine cleanup failure",
                )

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "replace",
                    side_effect=replace_then_raise,
                ), mock.patch.object(
                    codeql_runner,
                    "_publication_replace_completed",
                    side_effect=fail_rebuild,
                ), mock.patch.object(
                    codeql_runner,
                    "_cleanup_rollback_quarantine",
                    side_effect=fail_quarantine_cleanup,
                ):
                    with self.assertRaises(AnalyzerError):
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                self.assertGreaterEqual(rebuild_calls, 2)
                self.assertGreaterEqual(cleanup_calls, 1)
                generations = output / "query" / ".generations"
                names = {candidate.name for candidate in generations.iterdir()}
                self.assertFalse(
                    any(name.startswith("Entries-") for name in names)
                )
                self.assertTrue(
                    any(name.startswith(".rollback-") for name in names)
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")),
                    baseline_fds,
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_primitive_outage_retains_normal_generation_without_name_delete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            no_replace_failures = 0
            exchange_failures = 0
            normal_rmdir_calls = 0
            real_replace = codeql_runner.os.replace
            real_no_replace = codeql_runner.renameat2_no_replace
            real_exchange = codeql_runner.renameat2_exchange
            real_rmdir = codeql_runner.os.rmdir

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def replace_then_raise(
                source: object,
                destination: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                real_replace(source, destination, *args, **kwargs)
                if Path(destination).name.startswith("Entries-"):
                    raise OSError(errno.EIO, "injected publication failure")

            def fail_published_no_replace(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal no_replace_failures
                if source_name.startswith("Entries-"):
                    no_replace_failures += 1
                    raise OSError(errno.EIO, "persistent no-replace failure")
                real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            def fail_published_exchange(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal exchange_failures
                if source_name.startswith("Entries-"):
                    exchange_failures += 1
                    raise OSError(errno.EIO, "persistent exchange failure")
                real_exchange(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            def reject_normal_rmdir(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal normal_rmdir_calls
                if Path(path).name.startswith("Entries-"):
                    normal_rmdir_calls += 1
                    raise AssertionError("normal generation rmdir is forbidden")
                real_rmdir(path, *args, **kwargs)

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "replace",
                    side_effect=replace_then_raise,
                ), mock.patch.object(
                    codeql_runner,
                    "renameat2_no_replace",
                    side_effect=fail_published_no_replace,
                ), mock.patch.object(
                    codeql_runner,
                    "renameat2_exchange",
                    side_effect=fail_published_exchange,
                ), mock.patch.object(
                    codeql_runner.os,
                    "rmdir",
                    side_effect=reject_normal_rmdir,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                self.assertGreaterEqual(no_replace_failures, 1)
                self.assertGreaterEqual(exchange_failures, 1)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertEqual(normal_rmdir_calls, 0)
                generations = output / "query" / ".generations"
                normal = [
                    candidate
                    for candidate in generations.iterdir()
                    if candidate.name.startswith("Entries-")
                ]
                self.assertEqual(len(normal), 1)
                self.assertTrue(normal[0].is_dir())
                self.assertGreater(
                    len(list(normal[0].iterdir())),
                    0,
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_persistent_post_exchange_failures_preserve_normal_placeholder(
        self,
    ) -> None:
        for checkpoint in ("inode_check", "fsync", "rmdir"):
            with self.subTest(
                checkpoint=checkpoint
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                exchange_completed = False
                fault_count = 0
                real_replace = codeql_runner.os.replace
                real_no_replace = codeql_runner.renameat2_no_replace
                real_exchange = codeql_runner.renameat2_exchange
                real_stat = codeql_runner.os.stat
                real_fsync = codeql_runner.os.fsync
                real_rmdir = codeql_runner.os.rmdir

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def replace_then_raise(
                    source: object,
                    destination: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    real_replace(source, destination, *args, **kwargs)
                    if Path(destination).name.startswith("Entries-"):
                        raise OSError(errno.EIO, "injected publication failure")

                def fail_published_no_replace(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    if source_name.startswith("Entries-"):
                        raise OSError(errno.EIO, "force exchange fallback")
                    real_no_replace(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )

                def record_exchange(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    nonlocal exchange_completed
                    real_exchange(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )
                    if source_name.startswith("Entries-"):
                        exchange_completed = True

                def fail_post_exchange_stat(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> os.stat_result:
                    nonlocal fault_count
                    name = os.fspath(path)
                    if (
                        checkpoint == "inode_check"
                        and exchange_completed
                        and isinstance(name, str)
                        and name.startswith(".rollback-slot-")
                    ):
                        fault_count += 1
                        raise OSError(errno.EIO, "persistent inode failure")
                    return real_stat(path, *args, **kwargs)

                def fail_post_exchange_fsync(descriptor: int) -> None:
                    nonlocal fault_count
                    if checkpoint == "fsync" and exchange_completed:
                        fault_count += 1
                        raise OSError(errno.EIO, "persistent fsync failure")
                    real_fsync(descriptor)

                def fail_placeholder_rmdir(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    nonlocal fault_count
                    if (
                        checkpoint == "rmdir"
                        and exchange_completed
                        and os.fspath(path).startswith("Entries-")
                    ):
                        fault_count += 1
                        raise AssertionError(
                            "normal placeholder rmdir is forbidden"
                        )
                    real_rmdir(path, *args, **kwargs)

                try:
                    with mock.patch.object(
                        codeql_runner.os,
                        "replace",
                        side_effect=replace_then_raise,
                    ), mock.patch.object(
                        codeql_runner,
                        "renameat2_no_replace",
                        side_effect=fail_published_no_replace,
                    ), mock.patch.object(
                        codeql_runner,
                        "renameat2_exchange",
                        side_effect=record_exchange,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "stat",
                        side_effect=fail_post_exchange_stat,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "fsync",
                        side_effect=fail_post_exchange_fsync,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "rmdir",
                        side_effect=fail_placeholder_rmdir,
                    ):
                        with self.assertRaises(AnalyzerError):
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    self.assertTrue(exchange_completed)
                    if checkpoint == "rmdir":
                        self.assertEqual(fault_count, 0)
                    else:
                        self.assertGreaterEqual(fault_count, 1)
                    generations = output / "query" / ".generations"
                    normal = [
                        candidate
                        for candidate in generations.iterdir()
                        if candidate.name.startswith("Entries-")
                    ]
                    self.assertEqual(len(normal), 1)
                    self.assertTrue(normal[0].is_dir())
                    self.assertFalse(any(normal[0].iterdir()))
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_normal_name_substitution_never_deletes_competitor(self) -> None:
        for checkpoint in (
            "pre_rmdir",
            "post_action",
            "post_action_file_exists",
            "raw_unlink",
        ):
            with self.subTest(
                checkpoint=checkpoint
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                normal_rmdir_calls = 0
                raw_normal_unlinks = 0
                competitor: tuple[str, int, os.stat_result] | None = None
                real_replace = codeql_runner.os.replace
                real_no_replace = codeql_runner.renameat2_no_replace
                real_exchange = codeql_runner.renameat2_exchange
                real_rmdir = codeql_runner.os.rmdir

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def replace_then_raise(
                    source: object,
                    destination: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    real_replace(source, destination, *args, **kwargs)
                    if Path(destination).name.startswith("Entries-"):
                        raise OSError(errno.EIO, "publication post-action failure")

                def create_competitor(
                    directory_fd: int,
                    normal_name: str,
                ) -> None:
                    nonlocal competitor
                    self.assertIsNone(competitor)
                    os.mkdir(normal_name, mode=0o700, dir_fd=directory_fd)
                    descriptor = os.open(
                        normal_name,
                        os.O_RDONLY | os.O_DIRECTORY,
                        dir_fd=directory_fd,
                    )
                    marker = os.open(
                        "competitor-marker",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=descriptor,
                    )
                    os.close(marker)
                    info = os.fstat(descriptor)
                    competitor = (normal_name, descriptor, info)

                def isolate_then_substitute(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    if source_name.startswith("Entries-"):
                        if destination_name.startswith(".rollback-final-"):
                            if checkpoint in {
                                "post_action",
                                "post_action_file_exists",
                            }:
                                real_no_replace(
                                    source_directory_fd,
                                    source_name,
                                    destination_directory_fd,
                                    ".attacker-preserved-generation",
                                )
                                create_competitor(
                                    source_directory_fd,
                                    source_name,
                                )
                            real_no_replace(
                                source_directory_fd,
                                source_name,
                                destination_directory_fd,
                                destination_name,
                            )
                            if checkpoint not in {
                                "post_action",
                                "post_action_file_exists",
                            }:
                                create_competitor(
                                    source_directory_fd,
                                    source_name,
                                )
                            if checkpoint == "post_action":
                                raise OSError(
                                    errno.EIO,
                                    "isolation post-action failure",
                                )
                            if checkpoint == "post_action_file_exists":
                                raise FileExistsError(
                                    errno.EEXIST,
                                    "isolation post-action collision",
                                )
                            return
                        raise OSError(
                            errno.EIO,
                            "persistent no-replace failure",
                        )
                    real_no_replace(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )

                def fail_published_exchange(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    if source_name.startswith("Entries-"):
                        raise OSError(errno.EIO, "persistent exchange failure")
                    real_exchange(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )

                def forbid_normal_rmdir(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    nonlocal normal_rmdir_calls
                    if Path(path).name.startswith("Entries-"):
                        normal_rmdir_calls += 1
                        if checkpoint in {"pre_rmdir", "post_action"}:
                            real_rmdir(path, *args, **kwargs)
                        raise OSError(errno.EIO, "normal-name rmdir forbidden")
                    real_rmdir(path, *args, **kwargs)

                def forbid_raw_normal_unlink(
                    directory_fd: int,
                    name: str,
                ) -> None:
                    nonlocal raw_normal_unlinks
                    if name.startswith("Entries-"):
                        raw_normal_unlinks += 1
                    raise AssertionError("raw normal-name unlink is forbidden")

                try:
                    with mock.patch.object(
                        codeql_runner.os,
                        "replace",
                        side_effect=replace_then_raise,
                    ), mock.patch.object(
                        codeql_runner,
                        "renameat2_no_replace",
                        side_effect=isolate_then_substitute,
                    ), mock.patch.object(
                        codeql_runner,
                        "renameat2_exchange",
                        side_effect=fail_published_exchange,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "rmdir",
                        side_effect=forbid_normal_rmdir,
                    ), mock.patch.object(
                        codeql_runner,
                        "unlinkat_remove_dir",
                        side_effect=forbid_raw_normal_unlink,
                        create=True,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    self.assertEqual(
                        raised.exception.code,
                        "CODEQL_QUERY_FAILED",
                    )
                    self.assertEqual(normal_rmdir_calls, 0)
                    self.assertEqual(raw_normal_unlinks, 0)
                    self.assertIsNotNone(competitor)
                    assert competitor is not None
                    name, descriptor, expected = competitor
                    generations = output / "query" / ".generations"
                    current = (generations / name).lstat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino),
                        (expected.st_dev, expected.st_ino),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertTrue(
                        (generations / name / "competitor-marker").is_file()
                    )
                    os.close(descriptor)
                    competitor = None
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")),
                        baseline_fds,
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    if competitor is not None:
                        os.close(competitor[1])
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_hidden_rollback_root_substitution_is_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            generations = Path(temporary) / ".generations"
            generations.mkdir(mode=0o700)
            parent = os.open(generations, os.O_RDONLY | os.O_DIRECTORY)
            original_name = ".rollback-original"
            competitor_name = ".rollback-competitor"
            os.mkdir(original_name, mode=0o700, dir_fd=parent)
            os.mkdir(competitor_name, mode=0o700, dir_fd=parent)
            original = os.open(
                original_name,
                os.O_RDONLY | os.O_DIRECTORY,
                dir_fd=parent,
            )
            competitor = os.open(
                competitor_name,
                os.O_RDONLY | os.O_DIRECTORY,
                dir_fd=parent,
            )
            for descriptor, marker in (
                (original, "original-marker"),
                (competitor, "competitor-marker"),
            ):
                marker_descriptor = os.open(
                    marker,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=descriptor,
                )
                os.close(marker_descriptor)
            original_info = os.fstat(original)
            competitor_info = os.fstat(competitor)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            rmdir_calls = 0
            real_rmdir = codeql_runner.os.rmdir

            def substitute_root_before_rmdir(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal rmdir_calls
                if os.fspath(path) == original_name:
                    rmdir_calls += 1
                    filesystem.renameat2_exchange(
                        parent,
                        original_name,
                        parent,
                        competitor_name,
                    )
                real_rmdir(path, *args, **kwargs)

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "rmdir",
                    side_effect=substitute_root_before_rmdir,
                ):
                    with self.assertRaises(OSError) as raised:
                        codeql_runner._cleanup_rollback_quarantine(
                            parent,
                            original_name,
                            original_info,
                        )

                self.assertEqual(rmdir_calls, 0)
                self.assertEqual(
                    str(raised.exception),
                    "rollback quarantine retained for safe recovery",
                )
                current_original = os.stat(
                    original_name,
                    dir_fd=parent,
                    follow_symlinks=False,
                )
                current_competitor = os.stat(
                    competitor_name,
                    dir_fd=parent,
                    follow_symlinks=False,
                )
                self.assertEqual(
                    (current_original.st_dev, current_original.st_ino),
                    (original_info.st_dev, original_info.st_ino),
                )
                self.assertEqual(
                    (current_competitor.st_dev, current_competitor.st_ino),
                    (competitor_info.st_dev, competitor_info.st_ino),
                )
                self.assertEqual(os.fstat(original).st_nlink, original_info.st_nlink)
                self.assertEqual(
                    os.fstat(competitor).st_nlink,
                    competitor_info.st_nlink,
                )
                self.assertTrue(
                    (generations / original_name / "original-marker").is_file()
                )
                self.assertTrue(
                    (
                        generations
                        / competitor_name
                        / "competitor-marker"
                    ).is_file()
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
            finally:
                os.close(competitor)
                os.close(original)
                os.close(parent)

    def test_hidden_pending_child_substitution_is_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            generations = Path(temporary) / ".generations"
            generations.mkdir(mode=0o700)
            parent = os.open(generations, os.O_RDONLY | os.O_DIRECTORY)
            pending_name = ".Entries.pending.test"
            os.mkdir(pending_name, mode=0o700, dir_fd=parent)
            pending = os.open(
                pending_name,
                os.O_RDONLY | os.O_DIRECTORY,
                dir_fd=parent,
            )
            pending_info = os.fstat(pending)
            original_name = "result.json"
            competitor_name = "competitor.json"
            for name, payload in (
                (original_name, b"original"),
                (competitor_name, b"competitor"),
            ):
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=pending,
                )
                os.write(descriptor, payload)
                os.close(descriptor)
            original = os.open(original_name, os.O_RDONLY, dir_fd=pending)
            competitor = os.open(competitor_name, os.O_RDONLY, dir_fd=pending)
            original_info = os.fstat(original)
            competitor_info = os.fstat(competitor)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            unlink_calls = 0
            real_unlink = codeql_runner.os.unlink

            def substitute_child_before_unlink(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal unlink_calls
                name = os.fspath(path)
                directory_fd = kwargs.get("dir_fd")
                if directory_fd == pending:
                    unlink_calls += 1
                    if name != competitor_name:
                        filesystem.renameat2_exchange(
                            pending,
                            name,
                            pending,
                            competitor_name,
                        )
                real_unlink(path, *args, **kwargs)

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "unlink",
                    side_effect=substitute_child_before_unlink,
                ):
                    with self.assertRaises(OSError) as raised:
                        codeql_runner._cleanup_bound_pending_generation(
                            parent,
                            pending,
                            pending_name,
                            pending_info,
                            allow_expected_removal=True,
                        )

                self.assertEqual(unlink_calls, 0)
                self.assertEqual(
                    str(raised.exception),
                    "pending generation retained for safe recovery",
                )
                current_original = os.stat(
                    original_name,
                    dir_fd=pending,
                    follow_symlinks=False,
                )
                current_competitor = os.stat(
                    competitor_name,
                    dir_fd=pending,
                    follow_symlinks=False,
                )
                self.assertEqual(
                    (current_original.st_dev, current_original.st_ino),
                    (original_info.st_dev, original_info.st_ino),
                )
                self.assertEqual(
                    (current_competitor.st_dev, current_competitor.st_ino),
                    (competitor_info.st_dev, competitor_info.st_ino),
                )
                self.assertEqual(os.fstat(original).st_nlink, original_info.st_nlink)
                self.assertEqual(
                    os.fstat(competitor).st_nlink,
                    competitor_info.st_nlink,
                )
                self.assertEqual(
                    (generations / pending_name / original_name).read_bytes(),
                    b"original",
                )
                self.assertEqual(
                    (generations / pending_name / competitor_name).read_bytes(),
                    b"competitor",
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
            finally:
                os.close(competitor)
                os.close(original)
                os.close(pending)
                os.close(parent)

    def test_rename_noreplace_probe_descriptor_release_uses_structural_owner(
        self,
    ) -> None:
        for failure_phase in (
            "pre_action",
            "post_action",
            "persistent_setup_escape",
        ):
            with self.subTest(
                failure_phase=failure_phase
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                probe_descriptor = -1
                probe_info: os.stat_result | None = None
                injected = False
                setup_escapes = 0
                bare_probe_closes: list[int] = []
                release_order: list[int] = []
                real_open = codeql_runner.os.open
                real_close = codeql_runner.os.close
                real_close_once = filesystem.close_fd_once
                real_run_with_deferred_interrupts = (
                    codeql_runner.run_with_deferred_interrupts
                )

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def record_probe_open(path, flags, *args, **kwargs):
                    nonlocal probe_descriptor
                    nonlocal probe_info
                    descriptor = real_open(path, flags, *args, **kwargs)
                    name = os.fspath(path)
                    if (
                        isinstance(name, str)
                        and name.startswith(
                            ".rename-noreplace-probe-source-"
                        )
                    ):
                        probe_descriptor = descriptor
                        probe_info = os.fstat(descriptor)
                    return descriptor

                def is_live_probe(descriptor: int) -> bool:
                    if descriptor != probe_descriptor or probe_info is None:
                        return False
                    try:
                        current = os.fstat(descriptor)
                    except OSError:
                        return False
                    return codeql_runner._same_inode(current, probe_info)

                def record_bare_close(descriptor: int) -> None:
                    if is_live_probe(descriptor):
                        bare_probe_closes.append(descriptor)
                    real_close(descriptor)

                def fail_probe_release(
                    descriptor: int,
                    capability: filesystem.CloseRangeCapability,
                ) -> None:
                    nonlocal injected
                    release_order.append(descriptor)
                    if is_live_probe(descriptor) and not injected:
                        injected = True
                        if failure_phase == "pre_action":
                            raise filesystem.CloseRangePreActionError(
                                errno.EIO,
                                "injected no-replace probe pre-action failure",
                            )
                        if failure_phase == "post_action":
                            real_close_once(descriptor, capability)
                            raise OSError(
                                errno.EIO,
                                "injected no-replace probe post-action failure",
                            )
                    real_close_once(descriptor, capability)

                def fail_local_release_setup(action):
                    nonlocal injected
                    nonlocal setup_escapes
                    if (
                        failure_phase == "persistent_setup_escape"
                        and probe_descriptor >= 0
                        and action.__name__
                        in {
                            "release_all",
                            "release_remaining_after_outer_escape",
                        }
                    ):
                        injected = True
                        setup_escapes += 1
                        raise KeyboardInterrupt(
                            "injected no-replace probe release setup failure"
                        )
                    return real_run_with_deferred_interrupts(action)

                try:
                    with mock.patch.object(
                        codeql_runner.os,
                        "open",
                        side_effect=record_probe_open,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "close",
                        side_effect=record_bare_close,
                    ), mock.patch.object(
                        filesystem,
                        "close_fd_once",
                        side_effect=fail_probe_release,
                    ), mock.patch.object(
                        codeql_runner,
                        "run_with_deferred_interrupts",
                        side_effect=fail_local_release_setup,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    self.assertGreaterEqual(probe_descriptor, 0)
                    self.assertIsNotNone(probe_info)
                    self.assertTrue(injected)
                    self.assertEqual(bare_probe_closes, [])
                    self.assertGreaterEqual(len(release_order), 2)
                    if failure_phase == "persistent_setup_escape":
                        self.assertEqual(setup_escapes, 2)
                    else:
                        self.assertEqual(setup_escapes, 0)
                    self.assertEqual(
                        raised.exception.code,
                        "CODEQL_QUERY_FAILED",
                    )
                    self.assertNotIn(
                        str(root), repr(raised.exception.details)
                    )
                    generations = output / "query" / ".generations"
                    self.assertFalse(
                        any(
                            candidate.name.startswith("Entries-")
                            for candidate in generations.iterdir()
                        )
                    )
                    with self.assertRaises(OSError) as closed:
                        os.fstat(probe_descriptor)
                    self.assertEqual(closed.exception.errno, errno.EBADF)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    if probe_descriptor >= 0:
                        try:
                            real_close(probe_descriptor)
                        except OSError:
                            pass
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_rename_noreplace_probe_preserves_target_name_aba_substitute(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(
                self._database(root)
            )
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            injected = False
            probe_descriptor = -1
            target_name: str | None = None
            competitor_name: str | None = None
            original_info: os.stat_result | None = None
            substitute_info: os.stat_result | None = None
            mutable_removals: list[tuple[str, str]] = []
            real_open = codeql_runner.os.open
            real_stat = codeql_runner.os.stat
            real_rename = codeql_runner.os.rename
            real_rmdir = codeql_runner.os.rmdir
            real_unlink = codeql_runner.os.unlink
            generations = output / "query" / ".generations"
            original_marker = b"original-probe-inode"
            substitute_marker = b"target-name-substitute"

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def record_probe_open(path, flags, *args, **kwargs):
                nonlocal probe_descriptor
                descriptor = real_open(path, flags, *args, **kwargs)
                name = os.fspath(path)
                if (
                    isinstance(name, str)
                    and name.startswith(
                        ".rename-noreplace-probe-source-"
                    )
                ):
                    probe_descriptor = descriptor
                return descriptor

            def substitute_target_after_stat(path, *args, **kwargs):
                nonlocal injected
                nonlocal target_name
                nonlocal competitor_name
                nonlocal original_info
                nonlocal substitute_info
                current = real_stat(path, *args, **kwargs)
                name = os.fspath(path)
                directory_fd = kwargs.get("dir_fd")
                if (
                    not injected
                    and isinstance(name, str)
                    and name.startswith(
                        ".rename-noreplace-probe-target-"
                    )
                    and directory_fd is not None
                ):
                    injected = True
                    target_name = name
                    competitor_name = (
                        ".rename-noreplace-probe-competitor-"
                        f"{os.urandom(8).hex()}"
                    )
                    real_rename(
                        target_name,
                        competitor_name,
                        src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd,
                    )
                    os.mkdir(target_name, mode=0o700, dir_fd=directory_fd)
                    os.setxattr(
                        generations / competitor_name,
                        "user.dosweb.marker",
                        original_marker,
                    )
                    os.setxattr(
                        generations / target_name,
                        "user.dosweb.marker",
                        substitute_marker,
                    )
                    original_info = real_stat(
                        competitor_name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                    substitute_info = real_stat(
                        target_name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                return current

            def reject_mutable_rmdir(path, *args, **kwargs):
                name = os.fspath(path)
                if isinstance(name, str) and name.startswith(
                    (
                        ".rename-noreplace-probe-source-",
                        ".rename-noreplace-probe-target-",
                    )
                ):
                    mutable_removals.append(("rmdir", name))
                    raise OSError(
                        errno.EPERM,
                        "mutable probe name must not be removed",
                    )
                return real_rmdir(path, *args, **kwargs)

            def reject_mutable_unlink(path, *args, **kwargs):
                name = os.fspath(path)
                if isinstance(name, str) and name.startswith(
                    (
                        ".rename-noreplace-probe-source-",
                        ".rename-noreplace-probe-target-",
                    )
                ):
                    mutable_removals.append(("unlink", name))
                    raise OSError(
                        errno.EPERM,
                        "mutable probe name must not be unlinked",
                    )
                return real_unlink(path, *args, **kwargs)

            try:
                with mock.patch.object(
                    codeql_runner.os,
                    "open",
                    side_effect=record_probe_open,
                ), mock.patch.object(
                    codeql_runner.os,
                    "stat",
                    side_effect=substitute_target_after_stat,
                ), mock.patch.object(
                    codeql_runner.os,
                    "rmdir",
                    side_effect=reject_mutable_rmdir,
                ), mock.patch.object(
                    codeql_runner.os,
                    "unlink",
                    side_effect=reject_mutable_unlink,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                self.assertTrue(injected)
                self.assertGreaterEqual(probe_descriptor, 0)
                self.assertIsNotNone(target_name)
                self.assertIsNotNone(competitor_name)
                self.assertIsNotNone(original_info)
                self.assertIsNotNone(substitute_info)
                assert target_name is not None
                assert competitor_name is not None
                assert original_info is not None
                assert substitute_info is not None
                retained_original = real_stat(
                    generations / competitor_name,
                    follow_symlinks=False,
                )
                retained_substitute = real_stat(
                    generations / target_name,
                    follow_symlinks=False,
                )
                self.assertTrue(
                    codeql_runner._same_inode(
                        retained_original, original_info
                    )
                )
                self.assertTrue(
                    codeql_runner._same_inode(
                        retained_substitute, substitute_info
                    )
                )
                self.assertEqual(
                    os.getxattr(
                        generations / competitor_name,
                        "user.dosweb.marker",
                    ),
                    original_marker,
                )
                self.assertEqual(
                    os.getxattr(
                        generations / target_name,
                        "user.dosweb.marker",
                    ),
                    substitute_marker,
                )
                self.assertEqual(mutable_removals, [])
                self.assertEqual(
                    raised.exception.code, "CODEQL_QUERY_FAILED"
                )
                self.assertNotIn(str(root), repr(raised.exception.details))
                self.assertFalse(
                    any(
                        candidate.name.startswith("Entries-")
                        for candidate in generations.iterdir()
                    )
                )
                with self.assertRaises(OSError) as closed:
                    os.fstat(probe_descriptor)
                self.assertEqual(closed.exception.errno, errno.EBADF)
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                if probe_descriptor >= 0:
                    try:
                        os.close(probe_descriptor)
                    except OSError:
                        pass
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_exchange_probe_recovers_post_action_and_restore_failures(self) -> None:
        for checkpoint in (
            "first_post_action",
            "first_post_action_interrupt",
            "restore_persistent",
        ):
            with self.subTest(
                checkpoint=checkpoint
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                probe_exchange_calls = 0
                real_exchange = codeql_runner.renameat2_exchange

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def fail_probe_exchange_window(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    nonlocal probe_exchange_calls
                    is_probe = (
                        source_name.startswith(".rollback-slot-")
                        and destination_name.startswith(
                            ".rollback-exchange-probe-"
                        )
                    )
                    if is_probe:
                        probe_exchange_calls += 1
                        if (
                            checkpoint == "restore_persistent"
                            and probe_exchange_calls >= 2
                        ):
                            raise OSError(
                                errno.EIO,
                                "persistent restore pre-action failure",
                            )
                    real_exchange(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )
                    if (
                        is_probe
                        and checkpoint
                        in {"first_post_action", "first_post_action_interrupt"}
                        and probe_exchange_calls == 1
                    ):
                        if checkpoint == "first_post_action_interrupt":
                            raise KeyboardInterrupt(
                                "first exchange post-action interrupt"
                            )
                        raise OSError(errno.EIO, "first exchange post-action failure")

                try:
                    with mock.patch.object(
                        codeql_runner,
                        "renameat2_exchange",
                        side_effect=fail_probe_exchange_window,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    self.assertGreaterEqual(probe_exchange_calls, 1)
                    self.assertEqual(
                        raised.exception.code, "CODEQL_QUERY_FAILED"
                    )
                    self.assertNotIn(str(root), repr(raised.exception.details))
                    generations = output / "query" / ".generations"
                    names = self._assert_only_hidden_generation_quarantine(
                        generations
                    )
                    self.assertTrue(
                        any(
                            name.startswith(".Entries.pending.")
                            for name in names
                        )
                    )
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_exchange_probe_descriptor_release_is_one_shot_and_releases_remaining_owners(
        self,
    ) -> None:
        for failure_phase in (
            "pre_action",
            "post_action",
            "outer_setup_escape",
            "outermost_setup_escape",
            "outermost_post_publication_escape",
            "outermost_post_action_escape",
        ):
            with self.subTest(
                failure_phase=failure_phase
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                probe_descriptor = -1
                probe_info: os.stat_result | None = None
                injected = False
                release_api: str | None = None
                release_order: list[int] = []
                probe_release_indices: list[int] = []
                emergency_close_order: list[int] = []
                probe_emergency_indices: list[int] = []
                outer_setup_escapes = 0
                real_open = codeql_runner.os.open
                real_close = codeql_runner.os.close
                real_close_once = filesystem.close_fd_once
                real_closerange = codeql_runner.os.closerange
                real_run_with_deferred_interrupts = (
                    codeql_runner.run_with_deferred_interrupts
                )

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def record_probe_open(path, flags, *args, **kwargs):
                    nonlocal probe_descriptor
                    nonlocal probe_info
                    descriptor = real_open(path, flags, *args, **kwargs)
                    name = os.fspath(path)
                    if (
                        isinstance(name, str)
                        and name.startswith(
                            ".rollback-exchange-probe-"
                        )
                    ):
                        probe_descriptor = descriptor
                        probe_info = os.fstat(descriptor)
                        release_order.clear()
                        probe_release_indices.clear()
                        emergency_close_order.clear()
                        probe_emergency_indices.clear()
                    return descriptor

                def is_live_probe(descriptor: int) -> bool:
                    if descriptor != probe_descriptor or probe_info is None:
                        return False
                    try:
                        current = os.fstat(descriptor)
                    except OSError:
                        return False
                    return codeql_runner._same_inode(current, probe_info)

                def fail_bare_probe_close(descriptor: int) -> None:
                    nonlocal injected
                    nonlocal release_api
                    if (
                        descriptor == probe_descriptor
                        and not injected
                        and failure_phase in {"pre_action", "post_action"}
                    ):
                        injected = True
                        release_api = "bare_close"
                        if failure_phase == "post_action":
                            real_close(descriptor)
                        raise KeyboardInterrupt(
                            f"probe bare close {failure_phase} failure"
                        )
                    real_close(descriptor)

                def fail_one_shot_probe_release(
                    descriptor: int,
                    capability: filesystem.CloseRangeCapability,
                ) -> None:
                    nonlocal injected
                    nonlocal release_api
                    release_order.append(descriptor)
                    if is_live_probe(descriptor):
                        probe_release_indices.append(len(release_order) - 1)
                    if (
                        descriptor == probe_descriptor
                        and not injected
                        and failure_phase in {"pre_action", "post_action"}
                    ):
                        injected = True
                        release_api = "one_shot"
                        if failure_phase == "pre_action":
                            raise filesystem.CloseRangePreActionError(
                                errno.EIO,
                                "probe release pre-action failure",
                            )
                        real_close_once(descriptor, capability)
                        raise OSError(
                            errno.EIO,
                            "probe release post-action failure",
                        )
                    real_close_once(descriptor, capability)

                def fail_outer_release_setup(action):
                    nonlocal injected
                    nonlocal release_api
                    nonlocal outer_setup_escapes
                    if (
                        failure_phase == "outermost_post_action_escape"
                        and action.__name__ == "release_owned_state"
                    ):
                        real_run_with_deferred_interrupts(action)
                        injected = True
                        release_api = "outer_restore_escape"
                        outer_setup_escapes += 1
                        raise KeyboardInterrupt(
                            "injected outer owner release restoration failure"
                        )
                    if (
                        probe_descriptor >= 0
                        and failure_phase in {
                            "outer_setup_escape",
                            "outermost_setup_escape",
                            "outermost_post_publication_escape",
                        }
                        and action.__name__
                        in (
                            {
                                "release_all",
                                "release_remaining_after_outer_escape",
                                "release_owned_state",
                            }
                            if failure_phase == "outermost_setup_escape"
                            else {"release_owned_state"}
                            if failure_phase
                            == "outermost_post_publication_escape"
                            else {
                                "release_all",
                                "release_remaining_after_outer_escape",
                            }
                        )
                    ):
                        injected = True
                        release_api = "outer_setup_escape"
                        outer_setup_escapes += 1
                        raise KeyboardInterrupt(
                            "probe owner release outer setup failure"
                        )
                    return real_run_with_deferred_interrupts(action)

                def record_emergency_close(
                    first_fd: int,
                    last_fd: int,
                ) -> None:
                    self.assertEqual(last_fd, first_fd + 1)
                    emergency_close_order.append(first_fd)
                    if is_live_probe(first_fd):
                        probe_emergency_indices.append(
                            len(emergency_close_order) - 1
                        )
                    real_closerange(first_fd, last_fd)

                try:
                    raised_error: AnalyzerError | None = None
                    result = None
                    with mock.patch.object(
                        codeql_runner.os,
                        "open",
                        side_effect=record_probe_open,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "close",
                        side_effect=fail_bare_probe_close,
                    ), mock.patch.object(
                        filesystem,
                        "close_fd_once",
                        side_effect=fail_one_shot_probe_release,
                    ), mock.patch.object(
                        codeql_runner,
                        "run_with_deferred_interrupts",
                        side_effect=fail_outer_release_setup,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "closerange",
                        side_effect=record_emergency_close,
                    ):
                        if failure_phase == "outermost_post_action_escape":
                            try:
                                result = run_query(
                                    query,
                                    bound,
                                    output / "query",
                                    subprocess_run=successful_run,
                                )
                            except AnalyzerError as exc:
                                raised_error = exc
                        else:
                            with self.assertRaises(AnalyzerError) as raised:
                                run_query(
                                    query,
                                    bound,
                                    output / "query",
                                    subprocess_run=successful_run,
                                )
                            raised_error = raised.exception

                    self.assertGreaterEqual(probe_descriptor, 0)
                    self.assertTrue(injected)
                    if failure_phase == "outermost_post_action_escape":
                        self.assertEqual(
                            release_api,
                            "outer_restore_escape",
                        )
                        self.assertEqual(outer_setup_escapes, 1)
                        self.assertIsNone(raised_error)
                        self.assertIsNotNone(result)
                        self.assertEqual(emergency_close_order, [])
                    elif failure_phase == "outer_setup_escape":
                        self.assertEqual(
                            release_api,
                            "outer_setup_escape",
                        )
                        self.assertEqual(outer_setup_escapes, 2)
                        self.assertEqual(len(probe_release_indices), 1)
                        probe_release_index = probe_release_indices[0]
                        self.assertGreaterEqual(
                            len(release_order[probe_release_index + 1 :]),
                            1,
                        )
                    elif failure_phase == "outermost_setup_escape":
                        self.assertEqual(
                            release_api,
                            "outer_setup_escape",
                        )
                        self.assertEqual(outer_setup_escapes, 3)
                        self.assertEqual(probe_release_indices, [])
                        self.assertEqual(len(probe_emergency_indices), 1)
                        self.assertGreaterEqual(
                            len(emergency_close_order),
                            2,
                        )
                    elif (
                        failure_phase
                        == "outermost_post_publication_escape"
                    ):
                        self.assertEqual(
                            release_api,
                            "outer_setup_escape",
                        )
                        self.assertEqual(outer_setup_escapes, 1)
                        self.assertEqual(len(probe_release_indices), 1)
                        self.assertEqual(probe_emergency_indices, [])
                        self.assertGreaterEqual(
                            len(emergency_close_order),
                            1,
                        )
                    else:
                        self.assertEqual(release_api, "one_shot")
                        self.assertEqual(outer_setup_escapes, 0)
                        self.assertEqual(len(probe_release_indices), 1)
                        probe_release_index = probe_release_indices[0]
                        self.assertGreaterEqual(
                            len(release_order[probe_release_index + 1 :]),
                            1,
                        )
                    generations = output / "query" / ".generations"
                    if failure_phase == "outermost_post_action_escape":
                        self.assertEqual(
                            len(
                                [
                                    candidate
                                    for candidate in generations.iterdir()
                                    if candidate.name.startswith("Entries-")
                                ]
                            ),
                            1,
                        )
                    else:
                        assert raised_error is not None
                        self.assertEqual(
                            raised_error.code,
                            "CODEQL_QUERY_FAILED",
                        )
                        self.assertNotIn(
                            str(root),
                            repr(raised_error.details),
                        )
                        self.assertFalse(
                            any(
                                candidate.name.startswith("Entries-")
                                for candidate in generations.iterdir()
                            )
                        )
                    with self.assertRaises(OSError) as closed:
                        os.fstat(probe_descriptor)
                    self.assertEqual(closed.exception.errno, errno.EBADF)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")),
                        baseline_fds,
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    if probe_descriptor >= 0:
                        try:
                            real_close(probe_descriptor)
                        except OSError:
                            pass
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_local_descriptor_owner_outer_escape_protects_remaining_fallback_batch(
        self,
    ) -> None:
        for failure_phase in (
            "trace_after_pop",
            "fallback_failure_continues",
            "consumed_fd_not_retried",
            "persistent_setup_escape_retains_owner",
        ):
            with self.subTest(failure_phase=failure_phase):
                capability = filesystem.require_close_fd_once()
                descriptors = [
                    os.open("/dev/null", os.O_RDONLY),
                    os.open("/dev/null", os.O_RDONLY),
                ]
                descriptor_owner = list(descriptors)
                reused_descriptors: list[int] = []
                fallback_calls: list[int] = []
                outer_injected = False
                trace_injected = False
                previous_trace = sys.gettrace()
                real_closerange = os.closerange
                real_run_with_deferred_interrupts = (
                    codeql_runner.run_with_deferred_interrupts
                )

                def interrupt_after_owner_pop(frame, event, _arg):
                    nonlocal trace_injected
                    if (
                        failure_phase == "trace_after_pop"
                        and event == "line"
                        and frame.f_code.co_name
                        == "_release_local_descriptor_owners_once"
                        and len(descriptor_owner) == 1
                        and not trace_injected
                    ):
                        trace_injected = True
                        raise KeyboardInterrupt(
                            "injected trace interrupt after owner pop"
                        )
                    return interrupt_after_owner_pop

                def fail_outer_release(action):
                    nonlocal outer_injected
                    if (
                        failure_phase
                        == "persistent_setup_escape_retains_owner"
                        and action.__name__
                        in {
                            "release_all",
                            "release_remaining_after_outer_escape",
                        }
                    ):
                        outer_injected = True
                        raise KeyboardInterrupt(
                            "injected persistent owner release setup failure"
                        )
                    if action.__name__ == "release_all" and not outer_injected:
                        outer_injected = True
                        if failure_phase == "consumed_fd_not_retried":
                            real_run_with_deferred_interrupts(action)
                            reused_descriptors.extend(
                                os.open("/dev/null", os.O_RDONLY)
                                for _descriptor in descriptors
                            )
                        elif failure_phase == "trace_after_pop":
                            current_frame = sys._getframe()
                            while (
                                current_frame is not None
                                and current_frame.f_code.co_name
                                != "_release_local_descriptor_owners_once"
                            ):
                                current_frame = current_frame.f_back
                            self.assertIsNotNone(current_frame)
                            assert current_frame is not None
                            current_frame.f_trace = interrupt_after_owner_pop
                            sys.settrace(interrupt_after_owner_pop)
                        raise KeyboardInterrupt(
                            "injected outer owner release failure"
                        )
                    return real_run_with_deferred_interrupts(action)

                def record_fallback(first_fd: int, last_fd: int) -> None:
                    self.assertEqual(last_fd, first_fd + 1)
                    fallback_calls.append(first_fd)
                    if (
                        failure_phase == "fallback_failure_continues"
                        and len(fallback_calls) == 1
                    ):
                        raise OSError(
                            errno.EIO,
                            "injected first fallback failure",
                        )
                    real_closerange(first_fd, last_fd)

                escaped: BaseException | None = None
                failure: BaseException | None = None
                try:
                    with mock.patch.object(
                        codeql_runner,
                        "run_with_deferred_interrupts",
                        side_effect=fail_outer_release,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "closerange",
                        side_effect=record_fallback,
                    ):
                        try:
                            failure = codeql_runner._release_local_descriptor_owners_once(
                                descriptor_owner,
                                capability,
                            )
                        except BaseException as exc:
                            escaped = exc
                    sys.settrace(previous_trace)

                    self.assertIsNone(escaped)
                    self.assertTrue(outer_injected)
                    self.assertIsInstance(failure, KeyboardInterrupt)
                    if (
                        failure_phase
                        == "persistent_setup_escape_retains_owner"
                    ):
                        self.assertEqual(
                            descriptor_owner,
                            descriptors,
                        )
                        self.assertEqual(fallback_calls, [])
                        for descriptor in descriptors:
                            os.fstat(descriptor)
                    elif failure_phase == "consumed_fd_not_retried":
                        self.assertEqual(descriptor_owner, [])
                        self.assertEqual(fallback_calls, [])
                        self.assertEqual(
                            set(reused_descriptors),
                            set(descriptors),
                        )
                        for descriptor in reused_descriptors:
                            os.fstat(descriptor)
                    else:
                        self.assertEqual(descriptor_owner, [])
                        self.assertEqual(
                            fallback_calls,
                            list(reversed(descriptors)),
                        )
                        if failure_phase == "trace_after_pop":
                            self.assertFalse(trace_injected)
                            for descriptor in descriptors:
                                with self.assertRaises(OSError) as closed:
                                    os.fstat(descriptor)
                                self.assertEqual(
                                    closed.exception.errno,
                                    errno.EBADF,
                                )
                        else:
                            os.fstat(descriptors[-1])
                            with self.assertRaises(OSError) as closed:
                                os.fstat(descriptors[0])
                            self.assertEqual(
                                closed.exception.errno,
                                errno.EBADF,
                            )
                finally:
                    sys.settrace(previous_trace)
                    for descriptor in descriptors + reused_descriptors:
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass

    def test_pending_post_close_exception_keeps_identity_for_direct_recovery(
        self,
    ) -> None:
        for failure_type in (OSError, KeyboardInterrupt):
            with self.subTest(
                failure_type=failure_type.__name__
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                rebuild_calls = 0
                pending_descriptor = -1
                identity_descriptors: list[int] = []
                injected = False
                real_open = codeql_runner.os.open
                real_close = codeql_runner.os.close
                real_close_range = filesystem._close_range

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def record_pending_identity(
                    path: object,
                    flags: int,
                    *args: object,
                    **kwargs: object,
                ) -> int:
                    nonlocal pending_descriptor
                    descriptor = real_open(path, flags, *args, **kwargs)
                    name = os.fspath(path)
                    directory_fd = kwargs.get("dir_fd")
                    if (
                        isinstance(name, str)
                        and name.startswith(".Entries.pending.")
                        and isinstance(directory_fd, int)
                    ):
                        pending_descriptor = descriptor
                    elif (
                        name == "."
                        and directory_fd == pending_descriptor
                    ):
                        identity_descriptors.append(descriptor)
                    return descriptor

                def close_pending_then_raise(
                    capability: filesystem.CloseRangeCapability,
                    first_fd: int,
                    last_fd: int,
                ) -> None:
                    nonlocal injected
                    if (
                        pending_descriptor >= 0
                        and first_fd == pending_descriptor
                        and last_fd == pending_descriptor
                        and not injected
                    ):
                        real_close_range(capability, first_fd, last_fd)
                        injected = True
                        raise failure_type(
                            "injected pending post-close failure"
                        )
                    real_close_range(capability, first_fd, last_fd)

                def fail_rebuild(*_args: object, **_kwargs: object) -> bool:
                    nonlocal rebuild_calls
                    rebuild_calls += 1
                    raise OSError(
                        errno.EIO,
                        "injected persistent publication-state rebuild failure",
                    )

                descriptors: list[int] = []
                try:
                    with mock.patch.object(
                        codeql_runner.os,
                        "open",
                        side_effect=record_pending_identity,
                    ), mock.patch.object(
                        filesystem,
                        "_close_range",
                        side_effect=close_pending_then_raise,
                    ), mock.patch.object(
                        codeql_runner,
                        "_publication_replace_completed",
                        side_effect=fail_rebuild,
                    ):
                        with self.assertRaises(
                            (AnalyzerError, KeyboardInterrupt)
                        ):
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    descriptors = [
                        pending_descriptor,
                        *identity_descriptors,
                    ]
                    self.assertTrue(injected)
                    self.assertGreaterEqual(rebuild_calls, 1)
                    self.assertEqual(len(identity_descriptors), 1)
                    generations = output / "query" / ".generations"
                    self.assertFalse(
                        any(
                            candidate.name.startswith("Entries-")
                            for candidate in generations.iterdir()
                        )
                    )
                    for descriptor in descriptors:
                        with self.assertRaises(OSError) as closed:
                            os.fstat(descriptor)
                        self.assertEqual(closed.exception.errno, errno.EBADF)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    for descriptor in descriptors or [
                        pending_descriptor,
                        *identity_descriptors,
                    ]:
                        if descriptor < 0:
                            continue
                        try:
                            real_close(descriptor)
                        except OSError:
                            pass
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_housekeeping_unlink_failure_releases_fd_lock_and_generation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            pinned_descriptors: list[int] = []
            real_pin = codeql_runner._pin_generation_directory
            real_unlink = os.unlink

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def record_pin(
                path: Path,
                close_capability=None,
            ) -> tuple[int, os.stat_result]:
                descriptor, info = real_pin(path, close_capability)
                pinned_descriptors.append(descriptor)
                return descriptor, info

            def fail_execution_query_unlink(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                if (
                    kwargs.get("dir_fd") is None
                    and Path(path).name.startswith(".Entries.dosweb.")
                ):
                    raise OSError("injected execution query unlink failure")
                real_unlink(path, *args, **kwargs)

            try:
                with mock.patch.object(
                    codeql_runner,
                    "_pin_generation_directory",
                    side_effect=record_pin,
                ), mock.patch.object(
                    codeql_runner.os,
                    "unlink",
                    side_effect=fail_execution_query_unlink,
                ):
                    with self.assertRaises((AnalyzerError, OSError)):
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                self.assertEqual(len(pinned_descriptors), 1)
                generations = output / "query" / ".generations"
                with self.subTest(check="generation"):
                    names = {path.name for path in generations.iterdir()}
                    self.assertFalse(
                        any(name.startswith("Entries-") for name in names)
                    )
                with self.subTest(check="generation-fd"):
                    with self.assertRaises(OSError) as closed:
                        os.fstat(pinned_descriptors[0])
                    self.assertEqual(closed.exception.errno, errno.EBADF)

                acquired: list[bool] = []

                def acquire_from_other_thread() -> None:
                    locked = bound.execution.lock.acquire(timeout=0.2)
                    acquired.append(locked)
                    if locked:
                        bound.execution.lock.release()

                contender = threading.Thread(target=acquire_from_other_thread)
                contender.start()
                contender.join(timeout=1)
                with self.subTest(check="execution-lock"):
                    self.assertEqual(acquired, [True])
            finally:
                for descriptor in pinned_descriptors:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_generation_close_range_preflight_precedes_owned_fd_creation(
        self,
    ) -> None:
        for failure_type in (OSError, KeyboardInterrupt):
            with self.subTest(failure_type=failure_type.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                pinned_descriptors: list[int] = []
                real_pin = codeql_runner._pin_generation_directory

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def record_pin(
                    path: Path,
                    close_capability=None,
                ) -> tuple[int, os.stat_result]:
                    descriptor, info = real_pin(path, close_capability)
                    pinned_descriptors.append(descriptor)
                    return descriptor, info

                expected = (
                    AnalyzerError
                    if failure_type is OSError
                    else KeyboardInterrupt
                )
                try:
                    with mock.patch.object(
                        codeql_runner,
                        "require_close_fd_once",
                        side_effect=failure_type(
                            "injected close-range preflight"
                        ),
                        create=True,
                    ) as preflight, mock.patch.object(
                        codeql_runner,
                        "_pin_generation_directory",
                        side_effect=record_pin,
                    ):
                        with self.assertRaises(expected) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    preflight.assert_called_once_with()
                    self.assertEqual(pinned_descriptors, [])
                    if isinstance(raised.exception, AnalyzerError):
                        self.assertEqual(
                            raised.exception.code,
                            "CODEQL_QUERY_FAILED",
                        )
                    self.assertFalse((output / "query").exists())
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")),
                        baseline_fds,
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_generation_close_range_pre_action_failures_release_owned_fd(
        self,
    ) -> None:
        for failure_target in ("primary", "rollback"):
            with self.subTest(
                failure_target=failure_target,
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = (
                    codeql_database.create_execution_database_snapshot(
                        canonical,
                        output,
                        clone_tree=self._copy_clone,
                    )
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                primary_descriptors: list[int] = []
                duplicates: list[int] = []
                close_attempts: dict[int, int] = {}
                real_pin = codeql_runner._pin_generation_directory
                real_dup = codeql_runner.os.dup
                real_close = codeql_runner.os.close
                real_close_fd_once = filesystem.close_fd_once
                injected_descriptor = -1

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def record_pin(
                    path: Path,
                    close_capability=None,
                ) -> tuple[int, os.stat_result]:
                    descriptor, info = real_pin(path, close_capability)
                    primary_descriptors.append(descriptor)
                    return descriptor, info

                def record_duplicate(descriptor: int) -> int:
                    duplicate = real_dup(descriptor)
                    duplicates.append(duplicate)
                    close_attempts[duplicate] = 0
                    return duplicate

                def fail_before_close_range_action(
                    descriptor: int,
                    capability: object,
                ) -> None:
                    nonlocal injected_descriptor
                    close_attempts[descriptor] = (
                        close_attempts.get(descriptor, 0) + 1
                    )
                    ordered = [*primary_descriptors, *duplicates]
                    target_index = {
                        "primary": 0,
                        "rollback": 1,
                    }[failure_target]
                    if (
                        len(ordered) > target_index
                        and descriptor == ordered[target_index]
                        and injected_descriptor < 0
                    ):
                        injected_descriptor = descriptor
                        raise filesystem.CloseRangePreActionError(
                            errno.EIO,
                            f"injected {failure_target} pre-action failure",
                        )
                    real_close_fd_once(descriptor, capability)

                all_descriptors: list[int] = []
                try:
                    with mock.patch.object(
                        codeql_runner,
                        "_pin_generation_directory",
                        side_effect=record_pin,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "dup",
                        side_effect=record_duplicate,
                    ), mock.patch.object(
                        filesystem,
                        "close_fd_once",
                        side_effect=fail_before_close_range_action,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    all_descriptors = [
                        *primary_descriptors,
                        *duplicates,
                    ]
                    self.assertEqual(len(all_descriptors), 4)
                    self.assertGreaterEqual(injected_descriptor, 0)
                    self.assertEqual(
                        close_attempts[injected_descriptor],
                        1,
                    )
                    self.assertEqual(
                        raised.exception.code,
                        "CODEQL_QUERY_FAILED",
                    )
                    self.assertNotIn(
                        str(root),
                        repr(raised.exception.details),
                    )
                    generations = output / "query" / ".generations"
                    self.assertFalse(
                        any(
                            candidate.name.startswith("Entries-")
                            for candidate in generations.iterdir()
                        )
                    )
                    for descriptor in all_descriptors:
                        with self.assertRaises(OSError) as closed:
                            os.fstat(descriptor)
                        self.assertEqual(
                            closed.exception.errno,
                            errno.EBADF,
                        )
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")),
                        baseline_fds,
                    )
                    self.assertFalse(
                        bound.execution.lock._is_owned()
                    )
                finally:
                    for descriptor in all_descriptors or [
                        *primary_descriptors,
                        *duplicates,
                    ]:
                        try:
                            real_close(descriptor)
                        except OSError:
                            pass
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")),
                        baseline_fds,
                    )
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(
                        bound
                    )

    def test_final_rollback_anchor_post_close_exception_fails_closed(
        self,
    ) -> None:
        for failure_type in (OSError, KeyboardInterrupt):
            with self.subTest(failure_type=failure_type.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(
                    self._database(root)
                )
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical,
                    output,
                    clone_tree=self._copy_clone,
                )
                assert bound.execution is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                query = root / "Entries.ql"
                query.write_text("select 1", encoding="utf-8")
                calls = 0
                primary_descriptors: list[int] = []
                duplicates: list[int] = []
                real_pin = codeql_runner._pin_generation_directory
                real_dup = codeql_runner.os.dup
                real_close = codeql_runner.os.close
                real_close_range = filesystem._close_range
                injected = False

                def successful_run(
                    argv: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess[str]:
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

                def record_pin(
                    path: Path,
                    close_capability=None,
                ) -> tuple[int, os.stat_result]:
                    descriptor, info = real_pin(path, close_capability)
                    primary_descriptors.append(descriptor)
                    return descriptor, info

                def record_duplicate(descriptor: int) -> int:
                    duplicate = real_dup(descriptor)
                    duplicates.append(duplicate)
                    return duplicate

                def actual_close_range_then_raise(
                    capability: filesystem.CloseRangeCapability,
                    first_fd: int,
                    last_fd: int,
                ) -> None:
                    nonlocal injected
                    anchor = duplicates[1] if len(duplicates) >= 2 else -1
                    if (
                        first_fd == anchor
                        and last_fd == anchor
                        and not injected
                    ):
                        real_close_range(
                            capability,
                            first_fd,
                            last_fd,
                        )
                        injected = True
                        raise failure_type(
                            "injected final anchor post-close failure"
                        )
                    real_close_range(capability, first_fd, last_fd)

                descriptors: list[int] = []
                try:
                    with mock.patch.object(
                        codeql_runner,
                        "_pin_generation_directory",
                        side_effect=record_pin,
                    ), mock.patch.object(
                        codeql_runner.os,
                        "dup",
                        side_effect=record_duplicate,
                    ), mock.patch.object(
                        filesystem,
                        "_close_range",
                        side_effect=actual_close_range_then_raise,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            run_query(
                                query,
                                bound,
                                output / "query",
                                subprocess_run=successful_run,
                            )

                    descriptors = [*primary_descriptors, *duplicates]
                    self.assertTrue(injected)
                    self.assertEqual(len(descriptors), 4)
                    self.assertEqual(
                        raised.exception.code,
                        "CODEQL_QUERY_FAILED",
                    )
                    self.assertNotIn(
                        str(root),
                        json.dumps(raised.exception.details),
                    )
                    generations = output / "query" / ".generations"
                    self.assertEqual(
                        len([
                            candidate
                            for candidate in generations.iterdir()
                            if candidate.name.startswith("Entries-")
                        ]),
                        1,
                    )
                    for descriptor in descriptors:
                        with self.assertRaises(OSError) as closed:
                            os.fstat(descriptor)
                        self.assertEqual(
                            closed.exception.errno,
                            errno.EBADF,
                        )
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")),
                        baseline_fds,
                    )
                    self.assertFalse(bound.execution.lock._is_owned())
                finally:
                    for descriptor in descriptors or [
                        *primary_descriptors,
                        *duplicates,
                    ]:
                        try:
                            real_close(descriptor)
                        except OSError:
                            pass
                    while bound.execution.lock._is_owned():
                        bound.execution.lock.release()
                    codeql_database.cleanup_execution_database_snapshot(bound)

    def test_release_helper_return_event_cannot_preempt_final_anchor_or_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            primary_descriptors: list[int] = []
            duplicates: list[int] = []
            real_pin = codeql_runner._pin_generation_directory
            real_dup = codeql_runner.os.dup
            real_close = codeql_runner.os.close
            injected = False

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def record_pin(
                path: Path,
                close_capability=None,
            ) -> tuple[int, os.stat_result]:
                descriptor, info = real_pin(path, close_capability)
                primary_descriptors.append(descriptor)
                return descriptor, info

            def record_duplicate(descriptor: int) -> int:
                duplicate = real_dup(descriptor)
                duplicates.append(duplicate)
                return duplicate

            def interrupt_final_anchor_helper_return(frame, event, _arg):
                nonlocal injected
                final_anchor = duplicates[1] if len(duplicates) >= 2 else -1
                if (
                    not injected
                    and event == "return"
                    and frame.f_code
                    is filesystem.release_owned_descriptor_once.__code__
                    and frame.f_locals.get("descriptor") == final_anchor
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "final anchor release helper return interrupted"
                    )

            descriptors: list[int] = []
            try:
                with mock.patch.object(
                    codeql_runner,
                    "_pin_generation_directory",
                    side_effect=record_pin,
                ), mock.patch.object(
                    codeql_runner.os,
                    "dup",
                    side_effect=record_duplicate,
                ):
                    sys.setprofile(interrupt_final_anchor_helper_return)
                    try:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )
                    finally:
                        sys.setprofile(None)

                descriptors = [*primary_descriptors, *duplicates]
                self.assertFalse(injected)
                self.assertEqual(len(descriptors), 4)
                for descriptor in descriptors:
                    with self.assertRaises(OSError) as closed:
                        os.fstat(descriptor)
                    self.assertEqual(closed.exception.errno, errno.EBADF)
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")),
                    baseline_fds,
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                sys.setprofile(None)
                for descriptor in descriptors or [
                    *primary_descriptors,
                    *duplicates,
                ]:
                    try:
                        real_close(descriptor)
                    except OSError:
                        pass
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_final_rollback_anchor_raw_pre_action_error_rolls_back(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical,
                output,
                clone_tree=self._copy_clone,
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0
            primary_descriptors: list[int] = []
            duplicates: list[int] = []
            real_pin = codeql_runner._pin_generation_directory
            real_dup = codeql_runner.os.dup
            real_close = codeql_runner.os.close
            real_close_range = filesystem._close_range
            injected = False

            def successful_run(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
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

            def record_pin(
                path: Path,
                close_capability=None,
            ) -> tuple[int, os.stat_result]:
                descriptor, info = real_pin(path, close_capability)
                primary_descriptors.append(descriptor)
                return descriptor, info

            def record_duplicate(descriptor: int) -> int:
                duplicate = real_dup(descriptor)
                duplicates.append(duplicate)
                return duplicate

            def fail_raw_close_range_before_action(
                capability: filesystem.CloseRangeCapability,
                first_fd: int,
                last_fd: int,
            ) -> None:
                nonlocal injected
                anchor = duplicates[1] if len(duplicates) >= 2 else -1
                if (
                    first_fd == anchor
                    and last_fd == anchor
                    and not injected
                ):
                    injected = True
                    error_type = getattr(
                        filesystem,
                        "CloseRangePreActionError",
                        OSError,
                    )
                    raise error_type(
                        errno.EIO,
                        os.strerror(errno.EIO),
                    )
                real_close_range(capability, first_fd, last_fd)

            descriptors: list[int] = []
            try:
                with mock.patch.object(
                    codeql_runner,
                    "_pin_generation_directory",
                    side_effect=record_pin,
                ), mock.patch.object(
                    codeql_runner.os,
                    "dup",
                    side_effect=record_duplicate,
                ), mock.patch.object(
                    filesystem,
                    "_close_range",
                    side_effect=fail_raw_close_range_before_action,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        run_query(
                            query,
                            bound,
                            output / "query",
                            subprocess_run=successful_run,
                        )

                descriptors = [*primary_descriptors, *duplicates]
                self.assertTrue(injected)
                self.assertEqual(len(descriptors), 4)
                self.assertEqual(
                    raised.exception.code,
                    "CODEQL_QUERY_FAILED",
                )
                self.assertNotIn(
                    str(root),
                    repr(raised.exception.details),
                )
                cause = raised.exception.__cause__
                self.assertIsNotNone(cause)
                assert cause is not None
                self.assertIsInstance(cause, OSError)
                self.assertIn(
                    "retained for safe recovery",
                    str(cause),
                )
                generations = output / "query" / ".generations"
                self._assert_only_hidden_generation_quarantine(
                    generations
                )
                for descriptor in descriptors:
                    with self.assertRaises(OSError) as closed:
                        os.fstat(descriptor)
                    self.assertEqual(
                        closed.exception.errno,
                        errno.EBADF,
                    )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")),
                    baseline_fds,
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                for descriptor in descriptors or [
                    *primary_descriptors,
                    *duplicates,
                ]:
                    try:
                        real_close(descriptor)
                    except OSError:
                        pass
                while bound.execution.lock._is_owned():
                    bound.execution.lock.release()
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_initial_clone_mismatch_is_rejected_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()

            def mismatching_clone(source: Path, destination: Path) -> None:
                self._copy_clone(source, destination)
                (destination / "db-java" / "database-relations.json").write_text(
                    '{"relations":["mismatch"]}', encoding="utf-8"
                )

            with self.assertRaises(AnalyzerError) as raised:
                codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=mismatching_clone
                )
            self.assertEqual(raised.exception.code, "CODEQL_EXECUTION_SNAPSHOT_FAILED")
            self.assertFalse(list(output.glob(".codeql-execution-*")))

    def test_reflink_and_capacity_failures_are_fixed_and_path_free(self) -> None:
        for error_number in (errno.EOPNOTSUPP, errno.ENOSPC):
            with self.subTest(error_number=error_number), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()

                def fail_clone(_source: Path, _destination: Path) -> None:
                    raise OSError(error_number, "host-specific path /secret/snapshot")

                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.create_execution_database_snapshot(
                        canonical, output, clone_tree=fail_clone
                    )
                self.assertEqual(
                    raised.exception.code, "CODEQL_EXECUTION_SNAPSHOT_FAILED"
                )
                self.assertNotIn(str(output), repr(raised.exception.details))
                self.assertNotIn("secret", repr(raised.exception.details))
                self.assertFalse(list(output.glob(".codeql-execution-*")))

    def test_default_clone_never_falls_back_when_reflink_ioctl_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            with mock.patch.object(
                codeql_database.fcntl,
                "ioctl",
                side_effect=OSError(errno.EOPNOTSUPP, "reflink unavailable"),
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.create_execution_database_snapshot(
                        canonical, output
                    )
            self.assertEqual(raised.exception.code, "CODEQL_EXECUTION_SNAPSHOT_FAILED")
            self.assertFalse(list(output.glob(".codeql-execution-*")))

    def test_default_reflink_clone_is_independent_and_cleanup_succeeds(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            database = self._database(root)
            nested = database / "db-java" / "nested" / "payload.bin"
            nested.parent.mkdir()
            nested.write_bytes(b"canonical-payload")
            canonical = codeql_database.validate_database(database)
            output = root / "output"
            output.mkdir()
            try:
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output
                )
            except AnalyzerError as exc:
                current: BaseException | None = exc
                while current is not None:
                    if isinstance(current, OSError) and current.errno == errno.EOPNOTSUPP:
                        self.skipTest("filesystem explicitly rejects FICLONE")
                    current = current.__cause__
                raise
            assert bound.execution is not None
            cloned = bound.execution.path / "db-java" / "nested" / "payload.bin"
            self.assertEqual(cloned.read_bytes(), b"canonical-payload")
            cloned.write_bytes(b"execution-only")
            self.assertEqual(nested.read_bytes(), b"canonical-payload")
            codeql_database.cleanup_execution_database_snapshot(bound)
            self.assertFalse(bound.execution.path.exists())

    def test_default_reflink_clone_never_writes_parent_swap_replacement(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            moved_output = root / "output-original"
            real_assert = codeql_database._assert_private_binding
            replacement: Path | None = None
            snapshot_name: str | None = None
            swapped = False

            def assert_then_swap(
                binding: codeql_database.ExecutionDatabaseBinding,
            ) -> None:
                nonlocal replacement, snapshot_name, swapped
                real_assert(binding)
                if swapped:
                    return
                snapshot_name = binding.path.name
                output.rename(moved_output)
                output.mkdir()
                replacement = output / snapshot_name
                replacement.mkdir(mode=0o700)
                (replacement / "keep").write_text("victim", encoding="utf-8")
                swapped = True

            with mock.patch.object(
                codeql_database,
                "_assert_private_binding",
                side_effect=assert_then_swap,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.create_execution_database_snapshot(
                        canonical,
                        output,
                    )

            self.assertTrue(swapped)
            self.assertEqual(raised.exception.details.get("stage"), "clone")
            self.assertIsNotNone(replacement)
            assert replacement is not None
            self.assertEqual(
                (replacement / "keep").read_text(encoding="utf-8"),
                "victim",
            )
            self.assertFalse((replacement / "codeql-database.yml").exists())
            self.assertFalse((replacement / "db-java").exists())
            self.assertFalse(list(moved_output.glob(".codeql-execution-*")))
            self.assertEqual(
                {candidate.name for candidate in output.iterdir()},
                {snapshot_name},
            )

    def test_snapshot_release_has_no_kcmp_retry_aba_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            real_fchmod = codeql_database.os.fchmod
            real_close = codeql_database.os.close
            snapshot_descriptor = -1
            replacement_descriptor = -1
            close_failed = False
            aba_injected = False

            def record_snapshot_root(descriptor: int, mode: int) -> None:
                nonlocal snapshot_descriptor
                real_fchmod(descriptor, mode)
                opened = os.fstat(descriptor)
                if mode == 0o700 and stat.S_ISDIR(opened.st_mode):
                    snapshot_descriptor = descriptor

            def install_replacement(descriptor: int) -> None:
                nonlocal replacement_descriptor
                real_close(descriptor)
                replacement = os.open("/dev/null", os.O_RDONLY)
                if replacement != descriptor:
                    os.dup2(replacement, descriptor)
                    real_close(replacement)
                replacement_descriptor = descriptor

            def fail_legacy_close_before_action(descriptor: int) -> None:
                nonlocal close_failed
                if descriptor == snapshot_descriptor and not close_failed:
                    close_failed = True
                    raise OSError("injected legacy close failure")
                real_close(descriptor)

            def aba_after_legacy_identity_check(
                descriptor: int,
                anchor: int,
            ) -> bool:
                nonlocal aba_injected
                self.assertGreaterEqual(anchor, 0)
                still_bound = True
                if descriptor == snapshot_descriptor and not aba_injected:
                    self.assertTrue(still_bound)
                    install_replacement(descriptor)
                    aba_injected = True
                return still_bound

            def close_once_then_reuse(
                descriptor: int,
                _capability: object,
            ) -> None:
                install_replacement(descriptor)

            returned: codeql_database.DatabaseInfo | None = None
            failure: BaseException | None = None
            try:
                with mock.patch.object(
                    codeql_database.os,
                    "fchmod",
                    side_effect=record_snapshot_root,
                ), mock.patch.object(
                    codeql_database.os,
                    "close",
                    side_effect=fail_legacy_close_before_action,
                ), mock.patch.object(
                    codeql_database,
                    "same_open_file_description",
                    side_effect=aba_after_legacy_identity_check,
                    create=True,
                ), mock.patch.object(
                    codeql_database,
                    "close_fd_once",
                    side_effect=close_once_then_reuse,
                    create=True,
                ):
                    try:
                        returned = (
                            codeql_database.create_execution_database_snapshot(
                                canonical,
                                output,
                                clone_tree=self._copy_clone,
                            )
                        )
                    except BaseException as exc:
                        failure = exc

                self.assertGreaterEqual(replacement_descriptor, 0)
                os.fstat(replacement_descriptor)
                self.assertIsNone(failure)
                self.assertIsNotNone(returned)
            finally:
                if replacement_descriptor >= 0:
                    try:
                        real_close(replacement_descriptor)
                    except OSError:
                        pass
                if returned is not None:
                    codeql_database.cleanup_execution_database_snapshot(
                        returned
                    )

    def test_execution_hardlink_to_canonical_is_rejected_before_query_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            baseline_fds = len(os.listdir("/proc/self/fd"))
            canonical_relations = (
                canonical.path / "db-java" / "database-relations.json"
            )
            private_relations = (
                bound.execution.path / "db-java" / "database-relations.json"
            )
            original = canonical_relations.read_bytes()
            private_relations.unlink()
            os.link(canonical_relations, private_relations)
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            calls = 0

            def write_private_database(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                nonlocal calls
                calls += 1
                execution = Path(argv[argv.index("--database") + 1])
                (
                    execution / "db-java" / "database-relations.json"
                ).write_bytes(b'{"relations":["private-write"]}')
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            try:
                with self.assertRaises(AnalyzerError) as raised:
                    run_query(
                        query,
                        bound,
                        output / "query",
                        subprocess_run=write_private_database,
                    )
                self.assertEqual(
                    raised.exception.code, "CODEQL_QUERY_FAILED"
                )
                self.assertEqual(
                    (calls, canonical_relations.read_bytes()),
                    (0, original),
                )
                generations = output / "query" / ".generations"
                names = self._assert_only_hidden_generation_quarantine(
                    generations
                )
                self.assertTrue(
                    any(name.startswith(".Entries.pending.") for name in names)
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
                self.assertFalse(bound.execution.lock._is_owned())
            finally:
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_default_clone_detects_file_directory_and_root_inode_swaps(self) -> None:
        for swap_kind in ("file", "directory", "root"):
            with self.subTest(swap_kind=swap_kind), tempfile.TemporaryDirectory(
                dir=Path.cwd()
            ) as temporary:
                root = Path(temporary)
                database_path = self._database(root)
                canonical = codeql_database.validate_database(database_path)
                output = root / "output"
                output.mkdir()
                original_reflink = codeql_database._reflink_file
                real_mkdir = os.mkdir
                moved: Path | None = None
                swapped = False

                def reflink_then_swap(
                    source_directory: int,
                    destination_directory: int,
                    name: str,
                    expected: os.stat_result,
                    close_capability: object,
                ) -> None:
                    nonlocal moved, swapped
                    original_reflink(
                        source_directory,
                        destination_directory,
                        name,
                        expected,
                        close_capability,
                    )
                    if swapped:
                        return
                    if swap_kind == "file" and name == "database-relations.json":
                        swapped = True
                        os.rename(
                            name,
                            f"{name}.original",
                            src_dir_fd=source_directory,
                            dst_dir_fd=source_directory,
                        )
                        replacement = os.open(
                            name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=source_directory,
                        )
                        os.write(replacement, b'{"relations":[]}')
                        os.close(replacement)
                    elif swap_kind == "root":
                        swapped = True
                        moved = database_path.with_name(database_path.name + "-original")
                        os.rename(database_path, moved)
                        real_mkdir(database_path, 0o700)

                def mkdir_then_swap(
                    name: object, mode: int = 0o777, *args: object, **kwargs: object
                ) -> None:
                    nonlocal moved, swapped
                    real_mkdir(name, mode, *args, **kwargs)
                    if swap_kind == "directory" and not swapped and name == "db-java":
                        swapped = True
                        moved = database_path / "db-java-original"
                        os.rename(database_path / "db-java", moved)
                        real_mkdir(database_path / "db-java", 0o700)

                try:
                    with mock.patch.object(
                        codeql_database,
                        "_reflink_file",
                        side_effect=reflink_then_swap,
                    ), mock.patch.object(
                        codeql_database.os,
                        "mkdir",
                        side_effect=mkdir_then_swap,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            codeql_database.create_execution_database_snapshot(
                                canonical, output
                            )
                    self.assertEqual(
                        raised.exception.details.get("stage"), "clone"
                    )
                    self.assertTrue(swapped)
                    self.assertFalse(list(output.glob(".codeql-execution-*")))
                finally:
                    if swap_kind == "file" and swapped:
                        replacement = database_path / "db-java" / "database-relations.json"
                        replacement.unlink(missing_ok=True)
                        replacement.with_name(
                            "database-relations.json.original"
                        ).rename(replacement)
                    elif swap_kind == "directory" and moved is not None:
                        (database_path / "db-java").rmdir()
                        moved.rename(database_path / "db-java")
                    elif swap_kind == "root" and moved is not None:
                        database_path.rmdir()
                        moved.rename(database_path)

    def test_partial_clone_baseexception_is_cleaned_and_cleanup_failure_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()

            def interrupted_clone(_source: Path, destination: Path) -> None:
                (destination / "partial").write_text("partial", encoding="utf-8")
                raise KeyboardInterrupt("injected clone interruption")

            with self.assertRaises(KeyboardInterrupt):
                codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=interrupted_clone
                )
            self.assertFalse(list(output.glob(".codeql-execution-*")))

            original_remove = codeql_database._remove_private_tree

            def remove_then_fail(path: Path, **kwargs: object) -> None:
                original_remove(path, **kwargs)
                raise OSError("injected cleanup failure")

            with mock.patch.object(
                codeql_database, "_remove_private_tree", side_effect=remove_then_fail
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.create_execution_database_snapshot(
                        canonical, output, clone_tree=interrupted_clone
                    )
            self.assertEqual(raised.exception.details.get("stage"), "cleanup")
            self.assertIsInstance(raised.exception.__cause__, OSError)
            self.assertIsInstance(raised.exception.__cause__.__context__, KeyboardInterrupt)
            self.assertFalse(list(output.glob(".codeql-execution-*")))

    def test_stale_cleanup_fixed_error_is_not_rewrapped_as_clone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            stale_error = AnalyzerError(
                "CODEQL_EXECUTION_SNAPSHOT_FAILED",
                "Private CodeQL execution database snapshot failed.",
                {"stage": "stale_cleanup", "reason": "UNSAFE_OR_UNREMOVABLE"},
            )
            with mock.patch.object(
                codeql_database,
                "cleanup_stale_execution_database_snapshots",
                side_effect=stale_error,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.create_execution_database_snapshot(
                        canonical, output, clone_tree=self._copy_clone
                    )
            self.assertIs(raised.exception, stale_error)

    def test_canonical_nested_foreign_owner_is_rejected_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            real_stat = os.stat

            def foreign_nested(path: object, *args: object, **kwargs: object):
                result = real_stat(path, *args, **kwargs)
                if (
                    path == "database-relations.json"
                    and kwargs.get("dir_fd") is not None
                    and kwargs.get("follow_symlinks") is False
                ):
                    foreign = mock.Mock()
                    for field in (
                        "st_mode", "st_dev", "st_ino", "st_size",
                        "st_mtime_ns", "st_ctime_ns", "st_nlink",
                    ):
                        setattr(foreign, field, getattr(result, field))
                    foreign.st_uid = os.getuid() + 1
                    return foreign
                return result

            with mock.patch.object(codeql_database.os, "stat", side_effect=foreign_nested):
                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.validate_canonical_database(
                        canonical, actual_database=canonical
                    )
            self.assertEqual(
                raised.exception.details,
                {
                    "stage": "canonical_validation",
                    "reason": "CANONICAL_DATABASE_CHANGED",
                },
            )
            self.assertNotIn(str(canonical.path), repr(raised.exception.details))

    def test_execution_tree_and_stale_scan_use_streaming_bounded_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            stale = output / ".codeql-execution-stale"
            stale.mkdir(mode=0o700)
            with mock.patch.object(
                codeql_database.os,
                "listdir",
                side_effect=AssertionError("listdir must not materialize trees"),
            ), mock.patch.object(
                Path,
                "iterdir",
                side_effect=AssertionError("Path.iterdir must not materialize stale scans"),
            ):
                codeql_database.validate_canonical_database(
                    canonical, actual_database=canonical
                )
                codeql_database.cleanup_stale_execution_database_snapshots(output)
            self.assertFalse(stale.exists())

            for index in range(3):
                (output / f"unrelated-{index}").write_text("x", encoding="utf-8")
            with mock.patch.object(
                codeql_database, "_MAX_EXECUTION_TREE_ENTRIES", 2
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.cleanup_stale_execution_database_snapshots(output)
            self.assertEqual(raised.exception.details.get("stage"), "stale_cleanup")

    def test_cleanup_preserves_root_replacement_but_fails_pipeline_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            real_rename = getattr(codeql_database, "renameat2_no_replace", None)
            injected = False

            def replace_original_after_quarantine(
                source_directory_fd: int,
                source: str,
                destination_directory_fd: int,
                destination: str,
            ) -> None:
                nonlocal injected
                if real_rename is None:
                    os.rename(
                        source,
                        destination,
                        src_dir_fd=source_directory_fd,
                        dst_dir_fd=destination_directory_fd,
                    )
                else:
                    real_rename(
                        source_directory_fd,
                        source,
                        destination_directory_fd,
                        destination,
                    )
                if not injected and source == bound.execution.path.name:
                    injected = True
                    bound.execution.path.mkdir(mode=0o700)
                    (bound.execution.path / "keep").write_text("replacement")

            with mock.patch.object(
                codeql_database,
                "renameat2_no_replace",
                side_effect=replace_original_after_quarantine,
                create=True,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    Pipeline(
                        root / "run",
                        {
                            "entries": lambda _context: StageOutput(
                                {"entries.jsonl": b"ok\n"}
                            )
                        },
                        finalizer=lambda: codeql_database.cleanup_execution_database_snapshot(
                            bound
                        ),
                    ).run("entries")
            self.assertTrue(injected)
            self.assertEqual(raised.exception.details.get("stage"), "cleanup")
            persisted = json.loads(
                (root / "run" / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(
                persisted["error"]["code"], "CODEQL_EXECUTION_SNAPSHOT_FAILED"
            )
            self.assertEqual(
                (bound.execution.path / "keep").read_text(encoding="utf-8"),
                "replacement",
            )
            shutil.rmtree(bound.execution.path)

    def test_final_cleanup_uses_bound_parent_after_lexical_parent_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            snapshot_name = bound.execution.path.name
            moved_output = root / "output-original"
            output.rename(moved_output)
            output.mkdir()
            victim = output / snapshot_name
            victim.mkdir(mode=0o700)
            marker = victim / "keep"
            marker.write_text("victim", encoding="utf-8")

            codeql_database.cleanup_execution_database_snapshot(bound)

            self.assertFalse((moved_output / snapshot_name).exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "victim")

    def test_stale_scan_and_delete_keep_one_parent_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            output_info = output.stat()
            stale_name = ".codeql-execution-stale"
            stale = output / stale_name
            stale.mkdir(mode=0o700)
            (stale / "original").write_text("stale", encoding="utf-8")
            moved_output = root / "output-original"
            real_close = os.close
            matching_closes = 0
            swapped = False
            victim_marker = output / stale_name / "keep"

            def close_then_swap_parent(
                descriptor: int,
                _capability: object,
            ) -> None:
                nonlocal matching_closes, swapped
                try:
                    current = os.fstat(descriptor)
                except OSError:
                    real_close(descriptor)
                    return
                if (current.st_dev, current.st_ino) == (
                    output_info.st_dev,
                    output_info.st_ino,
                ):
                    matching_closes += 1
                    if matching_closes == 2:
                        real_close(descriptor)
                        output.rename(moved_output)
                        output.mkdir()
                        victim = output / stale_name
                        victim.mkdir(mode=0o700)
                        victim_marker.write_text("victim", encoding="utf-8")
                        swapped = True
                        return
                real_close(descriptor)

            with mock.patch.object(
                codeql_database,
                "close_fd_once",
                side_effect=close_then_swap_parent,
            ):
                codeql_database.cleanup_stale_execution_database_snapshots(output)

            self.assertTrue(swapped)
            self.assertFalse((moved_output / stale_name).exists())
            self.assertEqual(victim_marker.read_text(encoding="utf-8"), "victim")

    def test_stale_scan_rejects_same_name_inode_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            stale_name = ".codeql-execution-stale"
            stale = output / stale_name
            stale.mkdir(mode=0o700)
            (stale / "original").write_text("stale", encoding="utf-8")
            saved_name = f"{stale_name}.saved"
            saved = output / saved_name
            victim_marker = stale / "keep"
            real_remove = codeql_database._remove_private_tree_at
            swapped = False

            def replace_candidate_then_remove(
                parent_descriptor: int,
                name: str,
                **kwargs: object,
            ) -> None:
                nonlocal swapped
                if not swapped and name == stale_name:
                    os.rename(
                        name,
                        saved_name,
                        src_dir_fd=parent_descriptor,
                        dst_dir_fd=parent_descriptor,
                    )
                    os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
                    victim_marker.write_text("victim", encoding="utf-8")
                    swapped = True
                real_remove(parent_descriptor, name, **kwargs)

            with mock.patch.object(
                codeql_database,
                "_remove_private_tree_at",
                side_effect=replace_candidate_then_remove,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.cleanup_stale_execution_database_snapshots(
                        output
                    )

            self.assertTrue(swapped)
            self.assertEqual(raised.exception.details.get("stage"), "stale_cleanup")
            self.assertTrue(saved.is_dir())
            self.assertEqual(victim_marker.read_text(encoding="utf-8"), "victim")

    def test_cleanup_quarantine_rename_is_no_replace_and_never_falls_back(self) -> None:
        for error_number in (errno.EEXIST, errno.ENOSYS):
            with self.subTest(error_number=error_number), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=self._copy_clone
                )
                assert bound.execution is not None
                calls = 0

                def reject_no_replace(*_args: object, **_kwargs: object) -> None:
                    nonlocal calls
                    calls += 1
                    raise OSError(error_number, "injected no-replace failure")

                with mock.patch.object(
                    codeql_database,
                    "renameat2_no_replace",
                    side_effect=reject_no_replace,
                    create=True,
                ), mock.patch.object(
                    codeql_database.os,
                    "rename",
                    side_effect=AssertionError("unsafe rename fallback"),
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        codeql_database.cleanup_execution_database_snapshot(bound)
                self.assertEqual(calls, 1)
                self.assertEqual(raised.exception.details.get("stage"), "cleanup")
                self.assertTrue(bound.execution.path.is_dir())
                codeql_database.cleanup_stale_execution_database_snapshots(
                    output
                )

    def test_cleanup_rejects_same_inode_mode_drift(self) -> None:
        for drift_point in ("before_open", "after_quarantine"):
            with self.subTest(drift_point=drift_point), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=self._copy_clone
                )
                assert bound.execution is not None
                binding = bound.execution
                snapshot_name = binding.path.name
                marker_name = "cleanup-mode-drift-victim"
                (binding.path / marker_name).write_text("keep", encoding="utf-8")
                real_open = codeql_database.os.open
                real_rename = codeql_database.renameat2_no_replace
                quarantine_name: str | None = None
                drifted = False

                def chmod_before_root_open(*args: object, **kwargs: object) -> int:
                    nonlocal drifted
                    name = args[0] if args else kwargs.get("path")
                    if (
                        not drifted
                        and name == snapshot_name
                        and kwargs.get("dir_fd") == binding.parent_descriptor
                    ):
                        os.chmod(
                            snapshot_name,
                            0o755,
                            dir_fd=binding.parent_descriptor,
                        )
                        drifted = True
                    return real_open(*args, **kwargs)

                def chmod_after_quarantine(
                    source_directory_fd: int,
                    source: str,
                    destination_directory_fd: int,
                    destination: str,
                ) -> None:
                    nonlocal drifted, quarantine_name
                    real_rename(
                        source_directory_fd,
                        source,
                        destination_directory_fd,
                        destination,
                    )
                    if not drifted and source == snapshot_name:
                        os.chmod(
                            destination,
                            0o755,
                            dir_fd=destination_directory_fd,
                        )
                        quarantine_name = destination
                        drifted = True

                patcher = (
                    mock.patch.object(
                        codeql_database.os,
                        "open",
                        side_effect=chmod_before_root_open,
                    )
                    if drift_point == "before_open"
                    else mock.patch.object(
                        codeql_database,
                        "renameat2_no_replace",
                        side_effect=chmod_after_quarantine,
                    )
                )
                with patcher:
                    with self.assertRaises(AnalyzerError) as raised:
                        codeql_database.cleanup_execution_database_snapshot(bound)

                self.assertTrue(drifted)
                self.assertEqual(raised.exception.details.get("stage"), "cleanup")
                residual_name = (
                    snapshot_name
                    if drift_point == "before_open"
                    else quarantine_name
                )
                self.assertIsNotNone(residual_name)
                residual = output / str(residual_name)
                self.assertTrue(residual.is_dir())
                self.assertEqual(
                    (residual / marker_name).read_text(encoding="utf-8"),
                    "keep",
                )
                residual.chmod(0o700)
                codeql_database.cleanup_stale_execution_database_snapshots(output)
                self.assertFalse(residual.exists())

    def test_cleanup_rejects_root_mode_drift_during_finalization(self) -> None:
        for drift_point in ("remove_contents", "root_rmdir"):
            with self.subTest(drift_point=drift_point), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=self._copy_clone
                )
                assert bound.execution is not None
                binding = bound.execution
                snapshot_name = binding.path.name
                real_scandir = codeql_database.os.scandir
                real_rmdir = codeql_database.os.rmdir
                drifted = False

                def chmod_when_root_removal_starts(
                    descriptor: object,
                ) -> os.ScandirIterator[str]:
                    nonlocal drifted
                    if not drifted and isinstance(descriptor, int):
                        opened = os.fstat(descriptor)
                        if (opened.st_dev, opened.st_ino) == (
                            binding.device,
                            binding.inode,
                        ):
                            os.fchmod(descriptor, 0o755)
                            drifted = True
                    return real_scandir(descriptor)

                def chmod_inside_root_rmdir(
                    name: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    nonlocal drifted
                    if (
                        not drifted
                        and isinstance(name, str)
                        and name.startswith(f"{snapshot_name}.quarantine-")
                        and kwargs.get("dir_fd") == binding.parent_descriptor
                    ):
                        descriptor = os.open(
                            name,
                            os.O_RDONLY
                            | os.O_DIRECTORY
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=binding.parent_descriptor,
                        )
                        try:
                            os.fchmod(descriptor, 0o755)
                        finally:
                            os.close(descriptor)
                        drifted = True
                    real_rmdir(name, *args, **kwargs)

                patcher = (
                    mock.patch.object(
                        codeql_database.os,
                        "scandir",
                        side_effect=chmod_when_root_removal_starts,
                    )
                    if drift_point == "remove_contents"
                    else mock.patch.object(
                        codeql_database.os,
                        "rmdir",
                        side_effect=chmod_inside_root_rmdir,
                    )
                )
                with patcher:
                    with self.assertRaises(AnalyzerError) as raised:
                        codeql_database.cleanup_execution_database_snapshot(bound)

                self.assertTrue(drifted)
                self.assertEqual(raised.exception.details.get("stage"), "cleanup")
                self.assertFalse(binding.path.exists())
                quarantines = [
                    candidate
                    for candidate in output.iterdir()
                    if candidate.name.startswith(f"{snapshot_name}.quarantine-")
                ]
                if drift_point == "remove_contents":
                    self.assertEqual(len(quarantines), 1)
                    quarantines[0].chmod(0o700)
                    codeql_database.cleanup_stale_execution_database_snapshots(output)
                    self.assertFalse(quarantines[0].exists())
                else:
                    self.assertFalse(quarantines)

    def test_repeated_cleanup_does_not_close_reused_parent_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            descriptor = bound.execution.parent_descriptor

            codeql_database.cleanup_execution_database_snapshot(bound)
            with self.assertRaises(OSError) as closed:
                os.fstat(descriptor)
            self.assertEqual(closed.exception.errno, errno.EBADF)

            unrelated = os.open("/dev/null", os.O_RDONLY)
            if unrelated != descriptor:
                os.dup2(unrelated, descriptor)
                os.close(unrelated)
            try:
                codeql_database.cleanup_execution_database_snapshot(bound)
                reused = os.fstat(descriptor)
                self.assertGreater(reused.st_nlink, 0)
            finally:
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def test_cleanup_binding_is_consumed_once_across_concurrent_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            descriptor = bound.execution.parent_descriptor
            real_close_once = filesystem.close_fd_once
            close_attempts = 0
            close_guard = threading.Lock()
            start = threading.Barrier(3)
            failures: list[BaseException] = []

            def counting_close(
                candidate: int,
                capability: filesystem.CloseRangeCapability,
            ) -> None:
                nonlocal close_attempts
                if candidate == descriptor:
                    with close_guard:
                        close_attempts += 1
                real_close_once(candidate, capability)

            def cleanup_worker() -> None:
                start.wait()
                try:
                    codeql_database.cleanup_execution_database_snapshot(bound)
                except BaseException as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=cleanup_worker) for _ in range(2)]
            with mock.patch.object(
                codeql_database,
                "close_fd_once",
                side_effect=counting_close,
            ):
                for thread in threads:
                    thread.start()
                start.wait()
                for thread in threads:
                    thread.join(timeout=10)
                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertFalse(failures)
                codeql_database.cleanup_execution_database_snapshot(bound)

            self.assertEqual(close_attempts, 1)
            self.assertFalse(bound.execution.path.exists())

    def test_repeated_final_cleanup_failures_close_parent_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            baseline_fds = len(os.listdir("/proc/self/fd"))
            observed_descriptors: list[int] = []

            def reject_no_replace(*_args: object, **_kwargs: object) -> None:
                raise OSError(errno.ENOSYS, "injected no-replace failure")

            try:
                for _ in range(3):
                    bound = codeql_database.create_execution_database_snapshot(
                        canonical, output, clone_tree=self._copy_clone
                    )
                    assert bound.execution is not None
                    descriptor = bound.execution.parent_descriptor
                    observed_descriptors.append(descriptor)
                    with mock.patch.object(
                        codeql_database,
                        "renameat2_no_replace",
                        side_effect=reject_no_replace,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            codeql_database.cleanup_execution_database_snapshot(
                                bound
                            )
                    self.assertEqual(
                        raised.exception.details.get("stage"), "cleanup"
                    )
                    with self.assertRaises(OSError) as closed:
                        os.fstat(descriptor)
                    self.assertEqual(closed.exception.errno, errno.EBADF)
                    codeql_database.cleanup_stale_execution_database_snapshots(
                        output
                    )
                    self.assertFalse(
                        list(output.glob(".codeql-execution-*"))
                    )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds
                )
            finally:
                for descriptor in set(observed_descriptors):
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_cleanup_file_directory_and_root_swaps_fail_inside_quarantine(self) -> None:
        for swap_kind in ("file", "directory", "root"):
            with self.subTest(swap_kind=swap_kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                canonical = codeql_database.validate_database(self._database(root))
                output = root / "output"
                output.mkdir()
                bound = codeql_database.create_execution_database_snapshot(
                    canonical, output, clone_tree=self._copy_clone
                )
                assert bound.execution is not None
                real_unlink = os.unlink
                real_rmdir = os.rmdir
                real_rename = os.rename
                swapped = False

                def swapping_unlink(
                    name: object, *args: object, **kwargs: object
                ) -> None:
                    nonlocal swapped
                    directory_fd = kwargs.get("dir_fd")
                    if (
                        swap_kind == "file"
                        and not swapped
                        and name == "database-relations.json"
                        and isinstance(directory_fd, int)
                    ):
                        swapped = True
                        real_rename(
                            name,
                            f"{name}.original",
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                        )
                        replacement = os.open(
                            name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=directory_fd,
                        )
                        os.close(replacement)
                    real_unlink(name, *args, **kwargs)

                def swapping_rmdir(
                    name: object, *args: object, **kwargs: object
                ) -> None:
                    nonlocal swapped
                    directory_fd = kwargs.get("dir_fd")
                    is_target = (
                        swap_kind == "directory" and name == "db-java"
                    ) or (
                        swap_kind == "root"
                        and isinstance(name, str)
                        and ".quarantine-" in name
                    )
                    if not swapped and is_target and isinstance(directory_fd, int):
                        swapped = True
                        real_rename(
                            name,
                            f"{name}.original",
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                        )
                        os.mkdir(name, mode=0o700, dir_fd=directory_fd)
                    real_rmdir(name, *args, **kwargs)

                with mock.patch.object(
                    codeql_database.os, "unlink", side_effect=swapping_unlink
                ), mock.patch.object(
                    codeql_database.os, "rmdir", side_effect=swapping_rmdir
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        codeql_database.cleanup_execution_database_snapshot(bound)
                self.assertTrue(swapped)
                self.assertEqual(raised.exception.details.get("stage"), "cleanup")
                self.assertFalse(bound.execution.path.exists())
                self.assertTrue(
                    any(".quarantine-" in path.name for path in output.iterdir())
                )

    def test_canonical_root_symlink_and_special_file_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = self._database(root)
            alias = root / "database-alias"
            alias.symlink_to(database, target_is_directory=True)
            with self.assertRaises(AnalyzerError):
                codeql_database.validate_database(alias)
            alias.unlink()
            fifo = database / "db-java" / "unsafe-fifo"
            os.mkfifo(fifo)
            try:
                with self.assertRaises(AnalyzerError):
                    codeql_database.validate_database(database)
            finally:
                fifo.unlink()

    def test_snapshot_symlink_special_owner_and_inode_swaps_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            link = bound.execution.path / "db-java" / "unsafe-link"
            link.symlink_to(root / "source", target_is_directory=True)
            with self.assertRaises(AnalyzerError):
                codeql_database.validate_execution_database(bound)
            link.unlink()
            fifo = bound.execution.path / "db-java" / "unsafe-fifo"
            os.mkfifo(fifo)
            with self.assertRaises(AnalyzerError):
                codeql_database.validate_execution_database(bound)
            fifo.unlink()
            with mock.patch.object(codeql_database.os, "getuid", return_value=os.getuid() + 1):
                with self.assertRaises(AnalyzerError):
                    codeql_database.validate_execution_database(bound)
            moved = bound.execution.path.with_name(bound.execution.path.name + "-moved")
            bound.execution.path.rename(moved)
            bound.execution.path.mkdir(mode=0o700)
            try:
                with self.assertRaises(AnalyzerError):
                    codeql_database.validate_execution_database(bound)
            finally:
                bound.execution.path.rmdir()
                moved.rename(bound.execution.path)
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_snapshot_source_root_change_and_diagnostic_path_leak_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")

            def leak_path(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(
                    argv,
                    2,
                    stdout="",
                    stderr=f"failure in {bound.execution.path}",
                )

            try:
                with self.assertRaises(AnalyzerError) as raised:
                    run_query(query, bound, output / "query", subprocess_run=leak_path)
                self.assertNotIn(str(bound.execution.path), repr(raised.exception.details))
                metadata = bound.execution.path / "codeql-database.yml"
                payload = yaml.safe_load(metadata.read_text(encoding="utf-8"))
                payload["sourceLocationPrefix"] = str(root / "other-source")
                metadata.write_text(yaml.safe_dump(payload), encoding="utf-8")
                with self.assertRaises(AnalyzerError):
                    codeql_database.validate_execution_database(bound)
            finally:
                codeql_database.cleanup_execution_database_snapshot(bound)

    def test_safe_stale_cleanup_succeeds_and_unsafe_stale_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            stale = output / ".codeql-execution-stale"
            stale.mkdir(mode=0o700)
            (stale / "regular").write_text("stale", encoding="utf-8")
            codeql_database.cleanup_stale_execution_database_snapshots(output)
            self.assertFalse(stale.exists())

            external = output / "external"
            external.mkdir()
            unsafe = output / ".codeql-execution-unsafe"
            unsafe.symlink_to(external, target_is_directory=True)
            with self.assertRaises(AnalyzerError):
                codeql_database.cleanup_stale_execution_database_snapshots(output)
            self.assertTrue(external.is_dir())
            unsafe.unlink()

            wrong_mode = output / ".codeql-execution-world-readable"
            wrong_mode.mkdir(mode=0o755)
            wrong_mode.chmod(0o755)
            with self.assertRaises(AnalyzerError):
                codeql_database.cleanup_stale_execution_database_snapshots(output)
            wrong_mode.chmod(0o700)
            codeql_database.cleanup_stale_execution_database_snapshots(output)

    def test_cleanup_refuses_root_swap_and_never_follows_replacement_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            original = bound.execution.path.with_name(bound.execution.path.name + "-original")
            external = root / "external"
            external.mkdir()
            marker = external / "keep"
            marker.write_text("keep", encoding="utf-8")
            bound.execution.path.rename(original)
            bound.execution.path.symlink_to(external, target_is_directory=True)
            try:
                with self.assertRaises(AnalyzerError) as raised:
                    codeql_database.cleanup_execution_database_snapshot(bound)
                self.assertEqual(
                    raised.exception.details.get("stage"), "cleanup"
                )
                self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            finally:
                bound.execution.path.unlink()
                original.rename(bound.execution.path)
                codeql_database.cleanup_stale_execution_database_snapshots(
                    output
                )

    def test_shared_execution_database_serializes_concurrent_queries_without_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = codeql_database.validate_database(self._database(root))
            output = root / "output"
            output.mkdir()
            bound = codeql_database.create_execution_database_snapshot(
                canonical, output, clone_tree=self._copy_clone
            )
            assert bound.execution is not None
            query = root / "Entries.ql"
            query.write_text("select 1", encoding="utf-8")
            active = 0
            maximum_active = 0
            guard = threading.Lock()
            failures: list[BaseException] = []

            def worker(marker: str) -> None:
                calls = 0

                def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                    nonlocal active, maximum_active, calls
                    calls += 1
                    destination = Path(argv[argv.index("--output") + 1])
                    if calls == 1:
                        with guard:
                            active += 1
                            maximum_active = max(maximum_active, active)
                        try:
                            destination.write_bytes(marker.encode("utf-8"))
                        finally:
                            with guard:
                                active -= 1
                    else:
                        destination.write_text(self._decoded_entries_json(), encoding="utf-8")
                    return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

                try:
                    run_query(
                        query,
                        bound,
                        output / f"query-{marker}",
                        subprocess_run=fake_run,
                    )
                except BaseException as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=worker, args=(marker,)) for marker in ("a", "b")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            try:
                self.assertFalse(failures)
                self.assertEqual(maximum_active, 1)
                self.assertTrue(bound.execution.path.is_dir())
            finally:
                codeql_database.cleanup_execution_database_snapshot(bound)


if __name__ == "__main__":
    unittest.main()
