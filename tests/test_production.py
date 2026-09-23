from __future__ import annotations

import ast
from collections import Counter
import dis
import errno
import gc
import json
import os
from pathlib import Path
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from dosweb.cli import main, parse_cli_values
from dosweb.codeql import DatabaseInfo, QueryResult
import dosweb.codeql.database as codeql_database
import dosweb.codeql.runner as codeql_runner
import dosweb.filesystem as filesystem
from dosweb.codeql.decoder import (
    BOUND_COLUMNS,
    ENTRY_COLUMNS,
    INTERPOSITION_COLUMNS,
    FLOW_COLUMNS,
    GROWTH_COLUMNS,
    GUARD_COLUMNS,
    LIFECYCLE_COVERAGE_COLUMNS,
    LIFECYCLE_SUMMARY_COLUMNS,
    RELEASE_COLUMNS,
    SECURITY_COLUMNS,
)
from dosweb.entries import AttackerInputFact, EntryFact, HandlerFact, RegistrationFact
from dosweb.errors import AnalyzerError
from dosweb.growth import (
    AttackerInfluence,
    CandidateDisposition,
    CandidateEntryLink,
    DemandInput,
    GrowthCandidate,
    GrowthContract,
    SourceExcerpt,
    SourceLocation,
    VerificationCheck,
    VerifiedGrowthResult,
)
from dosweb.lifecycle import (
    BoundDecision,
    DecisionCheck,
    GuardDecision,
    ModeledConfiguration,
    ReleaseDecision,
)
from dosweb.pipeline import Pipeline, STAGES, StageContext, StageFingerprint, StageOutput
from dosweb.production import build_production_pipeline
import dosweb.production as production


def _unknown_growth_contract() -> GrowthContract:
    return GrowthContract(
        is_resource_growth="unknown",
        growth_kind="input_materialization",
        resource_dimension="bytes",
        attacker_influence=(),
        resource_effect="unknown",
        attacker_variable="unknown",
        attacker_value_space="unknown",
        growth_unit="unknown",
        growth_function="unknown",
        amplification_class="unknown",
        requests_to_pressure="unknown",
        concurrency_model="unknown",
        retention_window="unknown",
        failure_mechanism="unknown",
        failure_signal="unknown",
        required_static_evidence=(),
        contract_status="unknown",
        rejection_reason="unknown",
        confidence="low",
    )


class ProductionFactoryTests(unittest.TestCase):
    """Network-free RED contract for the first production factory slice."""

    def _values(self, root: Path, *, allow_remote_llm: bool | None = None) -> dict[str, object]:
        values: dict[str, object] = {
            "command": "analyze",
            "database": root / "database",
            "output": root / "output",
            "config": None,
            "allow_remote_llm": allow_remote_llm,
            "source_checkout": root,
            "analysis_source_root": root,
            "model": None,
            "base_url": None,
            "timeout_seconds": None,
            "max_retries": None,
            "temperature": None,
            "cache_dir": None,
            "codeql_binary": "codeql",
            "resume": False,
        }
        return values

    def test_injected_resource_provider_requires_resume_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(AnalyzerError) as raised:
                build_production_pipeline(
                    self._values(root),
                    environ={},
                    run_query_fn=lambda *_args, **_kwargs: None,
                    resource_lifecycle_provider=lambda _database, _output: None,
                )
            self.assertEqual("CONFIG_INVALID_VALUE", raised.exception.code)

    def _netty_route_alias_entries(
        self,
    ) -> tuple[EntryFact, EntryFact, EntryFact]:
        common = {
            "framework": "netty",
            "protocol": "tcp",
            "handler_fqn": "fixture.netty.FullRequestHandler.channelRead0",
            "handler_file": "fixture/netty/NettyFixture.java",
            "handler_start_line": 74,
            "registration_kind": "pipeline_registration",
            "registration_fqn": "fixture.netty.NettyFixture.initChannel",
            "registration_file": "fixture/netty/NettyFixture.java",
            "registration_start_line": 24,
            "auth_context": "unknown",
            "attacker_input_name": "request",
            "attacker_input_type": "FullHttpRequest",
            "attacker_input_kind": "message_payload",
            "materialization_phase": "streaming",
            "coverage_status": "complete",
        }
        return tuple(
            EntryFact.from_raw(
                {
                    **common,
                    "route_or_event": route,
                    "coverage_note": note,
                }
            )
            for route, note in (
                ("channelRead", "netty_pipeline_registration"),
                ("/beat", "netty_source_switch_route_alias"),
                ("/trigger", "netty_source_switch_route_alias"),
            )
        )  # type: ignore[return-value]

    def test_production_uses_one_private_execution_database_and_resume_identity_is_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            (database / "db-java").mkdir(parents=True)
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependency>org.springframework</dependency></project>",
                encoding="utf-8",
            )
            (database / "codeql-database.yml").write_text(
                f"primaryLanguage: java\nsourceLocationPrefix: {source}\n",
                encoding="utf-8",
            )
            (database / "db-java" / "database-relations.json").write_text(
                '{"relations":[]}', encoding="utf-8"
            )
            canonical = codeql_database.validate_database(database)
            clone_count = 0
            execution_paths: list[Path] = []
            query_paths: list[Path] = []

            def clone_tree(source_path: Path, destination: Path) -> None:
                import shutil

                shutil.copytree(source_path, destination, dirs_exist_ok=True)
                destination.chmod(0o700)

            def create_snapshot(
                info: DatabaseInfo,
                output: Path,
                *,
                validate_database_fn,
                owner_callback,
            ) -> DatabaseInfo:
                nonlocal clone_count
                clone_count += 1
                result = codeql_database.create_execution_database_snapshot(
                    info,
                    output,
                    clone_tree=clone_tree,
                    validate_database_fn=validate_database_fn,
                    owner_callback=owner_callback,
                )
                assert result.execution is not None
                execution_paths.append(result.execution.path)
                return result

            def fake_run(
                query: Path,
                info: DatabaseInfo,
                output_dir: Path,
                **_kwargs: object,
            ) -> QueryResult:
                assert info.execution is not None
                query_paths.append(info.execution.path)
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(
                    json.dumps(self._payload_for_query(query)), encoding="utf-8"
                )
                return QueryResult(
                    query.name, query, query, decoded, "a" * 64, "b" * 64
                )

            values = self._values(root)
            values["command"] = "entries"
            values["database"] = database
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            first = build_production_pipeline(
                values,
                environ={},
                run_query_fn=fake_run,
                create_execution_snapshot_fn=create_snapshot,
            )
            result = first.run("entries")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(clone_count, 1)
            self.assertEqual(set(query_paths), {execution_paths[0]})
            self.assertFalse(execution_paths[0].exists())
            serialized = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in (root / "output").rglob("*")
                if path.is_file()
            )
            self.assertNotIn(str(execution_paths[0]), serialized)
            self.assertIn(canonical.fingerprint, serialized)

            resumed_calls = 0

            def unexpected_run(*_args: object, **_kwargs: object) -> QueryResult:
                nonlocal resumed_calls
                resumed_calls += 1
                raise AssertionError("fresh execution snapshot path must not invalidate resume")

            resumed = build_production_pipeline(
                {**values, "resume": True},
                environ={},
                run_query_fn=unexpected_run,
                create_execution_snapshot_fn=create_snapshot,
            ).run("entries")
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(clone_count, 2)
            self.assertEqual(resumed_calls, 0)
            self.assertNotEqual(execution_paths[0], execution_paths[1])
            self.assertFalse(execution_paths[1].exists())

    def test_production_stage_failure_still_cleans_private_execution_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            (database / "db-java").mkdir(parents=True)
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependency>org.springframework</dependency></project>",
                encoding="utf-8",
            )
            (database / "codeql-database.yml").write_text(
                f"primaryLanguage: java\nsourceLocationPrefix: {source}\n",
                encoding="utf-8",
            )
            (database / "db-java" / "database-relations.json").write_text(
                '{"relations":[]}', encoding="utf-8"
            )
            execution_paths: list[Path] = []

            def create_snapshot(
                info: DatabaseInfo,
                output: Path,
                *,
                validate_database_fn,
                owner_callback,
            ) -> DatabaseInfo:
                import shutil

                def clone(source_path: Path, destination: Path) -> None:
                    shutil.copytree(source_path, destination, dirs_exist_ok=True)
                    destination.chmod(0o700)

                result = codeql_database.create_execution_database_snapshot(
                    info,
                    output,
                    clone_tree=clone,
                    validate_database_fn=validate_database_fn,
                    owner_callback=owner_callback,
                )
                assert result.execution is not None
                execution_paths.append(result.execution.path)
                return result

            def fail_query(*_args: object, **_kwargs: object) -> QueryResult:
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                    {"stage": "query_run", "diagnostic": "fixture failure"},
                )

            values = self._values(root)
            values.update(
                command="entries",
                database=database,
                source_checkout=source,
                analysis_source_root=source,
            )
            pipeline = build_production_pipeline(
                values,
                environ={},
                run_query_fn=fail_query,
                create_execution_snapshot_fn=create_snapshot,
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertEqual(len(execution_paths), 1)
            self.assertFalse(execution_paths[0].exists())
            persisted = json.loads(
                (root / "output" / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["status"], "failed")

    def test_formal_entries_failure_retains_hidden_query_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            (database / "db-java").mkdir(parents=True)
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependency>org.springframework</dependency></project>",
                encoding="utf-8",
            )
            (database / "codeql-database.yml").write_text(
                f"primaryLanguage: java\nsourceLocationPrefix: {source}\n",
                encoding="utf-8",
            )
            (database / "db-java" / "database-relations.json").write_text(
                '{"relations":[]}', encoding="utf-8"
            )
            held: dict[str, object] = {}
            query_calls = 0
            returned_results: list[QueryResult] = []
            active_database: DatabaseInfo | None = None

            def clone_tree(source_path: Path, destination: Path) -> None:
                import shutil

                shutil.copytree(
                    source_path,
                    destination,
                    dirs_exist_ok=True,
                )
                destination.chmod(0o700)

            def create_snapshot(
                info: DatabaseInfo,
                output: Path,
                *,
                validate_database_fn,
                owner_callback,
            ) -> DatabaseInfo:
                return codeql_database.create_execution_database_snapshot(
                    info,
                    output,
                    clone_tree=clone_tree,
                    validate_database_fn=validate_database_fn,
                    owner_callback=owner_callback,
                )

            def failing_subprocess(
                argv: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                nonlocal query_calls
                query_calls += 1
                target = Path(argv[argv.index("--output") + 1])
                if query_calls == 1:
                    target.write_bytes(b"original-marker")
                    stable_target = target.resolve(strict=True)
                    pending = stable_target.parent
                    competitor = pending / "competitor-marker"
                    competitor.write_bytes(b"competitor-marker")
                    pending_fd = os.open(
                        pending,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    original_fd = os.open(target, os.O_RDONLY)
                    competitor_fd = os.open(competitor, os.O_RDONLY)
                    held.update(
                        pending=pending,
                        original=stable_target,
                        competitor=competitor,
                        pending_fd=pending_fd,
                        original_fd=original_fd,
                        competitor_fd=competitor_fd,
                        pending_info=os.fstat(pending_fd),
                        original_info=os.fstat(original_fd),
                        competitor_info=os.fstat(competitor_fd),
                    )
                    return subprocess.CompletedProcess(
                        argv, 0, stdout="", stderr=""
                    )
                return subprocess.CompletedProcess(
                    argv,
                    1,
                    stdout="",
                    stderr="decode failed",
                )

            def run_real_query(
                query: Path,
                info: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                nonlocal active_database
                active_database = info
                result = codeql_runner.run_query(
                    query,
                    info,
                    output_dir,
                    subprocess_run=failing_subprocess,
                    **kwargs,
                )
                returned_results.append(result)
                return result

            values = self._values(root)
            values.update(
                command="entries",
                database=database,
                source_checkout=source,
                analysis_source_root=source,
            )
            pipeline = build_production_pipeline(
                values,
                environ={},
                run_query_fn=run_real_query,
                create_execution_snapshot_fn=create_snapshot,
            )
            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with self.assertRaises(AnalyzerError) as raised:
                    pipeline.run("entries")

                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertEqual(returned_results, [])
                self.assertEqual(query_calls, 2)
                pending = held["pending"]
                original = held["original"]
                competitor = held["competitor"]
                assert isinstance(pending, Path)
                assert isinstance(original, Path)
                assert isinstance(competitor, Path)
                workspace = pending.parents[2]
                self.assertEqual(workspace.parent, root / "output")
                self.assertTrue(workspace.name.startswith(".dosweb-entry-queries-"))
                self.assertTrue(pending.name.startswith("."))
                self.assertIn(".pending.", pending.name)
                self.assertEqual(
                    {
                        candidate.name
                        for candidate in pending.parent.iterdir()
                    },
                    {pending.name},
                )
                pending_fd = held["pending_fd"]
                original_fd = held["original_fd"]
                competitor_fd = held["competitor_fd"]
                assert isinstance(pending_fd, int)
                assert isinstance(original_fd, int)
                assert isinstance(competitor_fd, int)
                for path, descriptor, expected in (
                    (pending, pending_fd, held["pending_info"]),
                    (original, original_fd, held["original_info"]),
                    (competitor, competitor_fd, held["competitor_info"]),
                ):
                    assert isinstance(expected, os.stat_result)
                    current = path.stat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino, current.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                self.assertEqual(
                    os.pread(original_fd, 64, 0), b"original-marker"
                )
                self.assertEqual(
                    os.pread(competitor_fd, 64, 0), b"competitor-marker"
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 3
                )
                self.assertIsNotNone(active_database)
                assert active_database is not None
                assert active_database.execution is not None
                self.assertFalse(active_database.execution.lock._is_owned())
                persisted = json.loads(
                    (root / "output" / "run.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(persisted["status"], "failed")
                self.assertFalse((root / "output" / "entries.jsonl").exists())
                self.assertFalse(
                    (
                        root
                        / "output"
                        / ".stage-manifests"
                        / "entries.json"
                    ).exists()
                )
            finally:
                for key in ("competitor_fd", "original_fd", "pending_fd"):
                    descriptor = held.get(key)
                    if isinstance(descriptor, int):
                        os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            resume_calls = 0

            def fail_resumed_query(
                *_args: object,
                **_kwargs: object,
            ) -> QueryResult:
                nonlocal resume_calls
                resume_calls += 1
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                    {"stage": "query_run"},
                )

            resumed = build_production_pipeline(
                {**values, "resume": True},
                environ={},
                run_query_fn=fail_resumed_query,
                create_execution_snapshot_fn=create_snapshot,
            )
            with self.assertRaises(AnalyzerError) as resumed_failure:
                resumed.run("entries")
            self.assertEqual(
                resumed_failure.exception.code,
                "CODEQL_QUERY_FAILED",
            )
            self.assertEqual(resume_calls, 1)
            pending = held["pending"]
            competitor = held["competitor"]
            assert isinstance(pending, Path)
            assert isinstance(competitor, Path)
            self.assertTrue(pending.is_dir())
            self.assertEqual(
                (competitor).read_bytes(),
                b"competitor-marker",
            )
            self.assertEqual(
                json.loads(
                    (root / "output" / "run.json").read_text(
                        encoding="utf-8"
                    )
                )["status"],
                "failed",
            )

    def test_codeql_family_failure_retains_hidden_query_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            pipeline = build_production_pipeline(
                {
                    **self._values(root),
                    "command": "entries",
                },
                environ={},
            )
            database = DatabaseInfo(root / "database", root, "d" * 64)
            held: dict[str, object] = {}

            def fail_with_hidden_quarantine(
                _query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                descriptor = kwargs.get("output_descriptor")
                stable_results = (
                    Path(os.readlink(f"/proc/self/fd/{descriptor}"))
                    if isinstance(descriptor, int)
                    else output_dir
                )
                generations = output_dir / ".generations"
                generations.mkdir()
                for name, marker in (
                    (".rollback-original", "original-marker"),
                    (".rollback-competitor", "competitor-marker"),
                ):
                    candidate = generations / name
                    stable_candidate = stable_results / ".generations" / name
                    candidate.mkdir(mode=0o700)
                    (candidate / marker).write_text(marker, encoding="utf-8")
                    descriptor = os.open(
                        candidate,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    held[name] = (
                        stable_candidate,
                        descriptor,
                        os.fstat(descriptor),
                        marker,
                    )
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                    {"stage": "publication"},
                )

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    shutil,
                    "rmtree",
                    side_effect=AssertionError(
                        "retained query workspace must not be recursively removed"
                    ),
                ) as recursive_cleanup:
                    with self.assertRaises(AnalyzerError) as raised:
                        production._run_codeql_family(
                            pipeline.config,
                            database,
                            "growth",
                            root / "pack",
                            fail_with_hidden_quarantine,
                        )
                recursive_cleanup.assert_not_called()
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertEqual(set(held), {
                    ".rollback-original",
                    ".rollback-competitor",
                })
                for value in held.values():
                    candidate, descriptor, expected, marker = value
                    assert isinstance(candidate, Path)
                    assert isinstance(descriptor, int)
                    assert isinstance(expected, os.stat_result)
                    assert isinstance(marker, str)
                    workspace = candidate.parents[2]
                    self.assertEqual(workspace.parent, output)
                    self.assertTrue(
                        workspace.name.startswith(".dosweb-growth-queries-")
                    )
                    current = candidate.stat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino, current.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertTrue((candidate / marker).is_file())
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 2
                )
            finally:
                for value in held.values():
                    descriptor = value[1]
                    assert isinstance(descriptor, int)
                    os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_family_output_root_swap_fails_before_decoding_replacement_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            (output / "original-marker").write_text(
                "original-marker", encoding="utf-8"
            )
            pipeline = build_production_pipeline(
                {**self._values(root), "command": "entries"},
                environ={},
            )
            database = DatabaseInfo(root / "database", root, "d" * 64)
            original_root = root / "output-original"
            held: dict[str, object] = {}

            def swap_root_and_return_replacement_json(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                descriptor = kwargs.get("output_descriptor")
                if isinstance(descriptor, int):
                    stable_results = Path(
                        os.readlink(f"/proc/self/fd/{descriptor}")
                    )
                else:
                    stable_results = output_dir
                workspace_name = stable_results.parent.name
                original_fd = os.open(
                    output,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                output.rename(original_root)
                output.mkdir(mode=0o700)
                (output / "replacement-marker").write_text(
                    "replacement-marker", encoding="utf-8"
                )
                replacement_fd = os.open(
                    output,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                held.update(
                    original_fd=original_fd,
                    replacement_fd=replacement_fd,
                )
                replacement_results = output / workspace_name / "results"
                replacement_results.mkdir(parents=True, mode=0o700)
                decoded = replacement_results / f"{query.stem}.json"
                decoded.write_text("{}", encoding="utf-8")
                held.update(
                    original_info=os.fstat(original_fd),
                    replacement_info=os.fstat(replacement_fd),
                )
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    production,
                    "_query_files",
                    return_value=(root / "Growth.ql",),
                ), mock.patch.object(
                    production,
                    "decode_bqrs_json",
                    return_value=[],
                ) as decode:
                    with self.assertRaises(AnalyzerError) as raised:
                        production._run_codeql_family(
                            pipeline.config,
                            database,
                            "growth",
                            root / "pack",
                            swap_root_and_return_replacement_json,
                        )

                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertNotIn(
                    str(root), json.dumps(raised.exception.details)
                )
                decode.assert_not_called()
                for path, fd_key, info_key, marker in (
                    (
                        original_root,
                        "original_fd",
                        "original_info",
                        "original-marker",
                    ),
                    (
                        output,
                        "replacement_fd",
                        "replacement_info",
                        "replacement-marker",
                    ),
                ):
                    descriptor = held[fd_key]
                    expected = held[info_key]
                    assert isinstance(descriptor, int)
                    assert isinstance(expected, os.stat_result)
                    current = path.stat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino, current.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (path / marker).read_text(encoding="utf-8"), marker
                    )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 2
                )
            finally:
                for key in ("replacement_fd", "original_fd"):
                    descriptor = held.get(key)
                    if isinstance(descriptor, int):
                        os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_family_output_root_swap_releases_returned_private_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            pipeline = build_production_pipeline(
                {**self._values(root), "command": "entries"},
                environ={},
            )
            database = DatabaseInfo(root / "database", root, "d" * 64)
            original_root = root / "output-original"
            held: dict[str, object] = {}

            def return_bound_result_after_root_swap(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                results_descriptor = kwargs["output_descriptor"]
                assert isinstance(results_descriptor, int)
                generations = output_dir / ".generations"
                generations.mkdir(mode=0o700)
                generation_name = "Growth-normal"
                generation = generations / generation_name
                generation.mkdir(mode=0o700)
                decoded_name = f"{query.stem}.json"
                decoded = generation / decoded_name
                decoded.write_text("{}", encoding="utf-8")
                binding = codeql_runner._pin_query_output_binding(
                    results_descriptor,
                    generation_name,
                    decoded_name,
                    filesystem.require_close_fd_once(),
                )
                original_fd = os.open(
                    output,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                output.rename(original_root)
                output.mkdir(mode=0o700)
                replacement_fd = os.open(
                    output,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                held.update(
                    binding=binding,
                    original_fd=original_fd,
                    replacement_fd=replacement_fd,
                )
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                    _output_binding=binding,
                )

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    production,
                    "_query_files",
                    return_value=(root / "Growth.ql",),
                ), mock.patch.object(
                    production,
                    "decode_bqrs_json",
                    return_value=[],
                ) as decode:
                    with self.assertRaises(AnalyzerError) as raised:
                        production._run_codeql_family(
                            pipeline.config,
                            database,
                            "growth",
                            root / "pack",
                            return_bound_result_after_root_swap,
                        )

                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                decode.assert_not_called()
                binding = held["binding"]
                assert isinstance(binding, codeql_runner._QueryOutputBinding)
                self.assertEqual(binding.decoded_descriptor, -1)
                self.assertEqual(binding.generation_descriptor, -1)
                self.assertEqual(binding.generations_descriptor, -1)
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 2
                )
            finally:
                binding = held.get("binding")
                if isinstance(binding, codeql_runner._QueryOutputBinding):
                    for field in (
                        "decoded_descriptor",
                        "generation_descriptor",
                        "generations_descriptor",
                    ):
                        descriptor = getattr(binding, field)
                        if isinstance(descriptor, int) and descriptor >= 0:
                            os.close(descriptor)
                            setattr(binding, field, -1)
                for key in ("replacement_fd", "original_fd"):
                    descriptor = held.get(key)
                    if isinstance(descriptor, int):
                        os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_family_output_ancestor_swap_fails_before_decode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "parent"
            output = parent / "output"
            output.mkdir(parents=True, mode=0o700)
            values = self._values(root)
            values.update(command="entries", output=output)
            pipeline = build_production_pipeline(values, environ={})
            database = DatabaseInfo(root / "database", root, "d" * 64)
            original_parent = root / "parent-original"
            held: dict[str, object] = {}

            def swap_output_ancestor(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **_kwargs: object,
            ) -> QueryResult:
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text("{}", encoding="utf-8")
                original_fd = os.open(
                    parent,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                parent.rename(original_parent)
                output.mkdir(parents=True, mode=0o700)
                (output / "replacement-marker").write_text(
                    "replacement-marker", encoding="utf-8"
                )
                replacement_fd = os.open(
                    parent,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                held.update(
                    original_fd=original_fd,
                    replacement_fd=replacement_fd,
                )
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    production,
                    "_query_files",
                    return_value=(root / "Growth.ql",),
                ), mock.patch.object(
                    production,
                    "decode_bqrs_json",
                    return_value=[],
                ) as decode:
                    with self.assertRaises(AnalyzerError) as raised:
                        production._run_codeql_family(
                            pipeline.config,
                            database,
                            "growth",
                            root / "pack",
                            swap_output_ancestor,
                        )

                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertNotIn(str(root), json.dumps(raised.exception.details))
                decode.assert_not_called()
                self.assertTrue(
                    (original_parent / "output").is_dir()
                )
                self.assertEqual(
                    (output / "replacement-marker").read_text(
                        encoding="utf-8"
                    ),
                    "replacement-marker",
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 2
                )
            finally:
                for key in ("replacement_fd", "original_fd"):
                    descriptor = held.get(key)
                    if isinstance(descriptor, int):
                        os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_workspace_creation_releases_unbound_ancestry_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "parent"
            output = parent / "output"
            output.mkdir(parents=True, mode=0o700)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            real_fstat = production.os.fstat
            held_descriptor = -1
            injected = False

            def fail_new_parent_binding(descriptor: int):
                nonlocal held_descriptor, injected
                if not injected:
                    try:
                        target = Path(
                            os.readlink(f"/proc/self/fd/{descriptor}")
                        )
                    except OSError:
                        target = Path()
                    if target == parent:
                        injected = True
                        held_descriptor = descriptor
                        raise OSError("ancestry fstat failed")
                return real_fstat(descriptor)

            try:
                with mock.patch.object(
                    production.os,
                    "fstat",
                    side_effect=fail_new_parent_binding,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        production._create_codeql_query_workspace(
                            output,
                            "growth",
                        )
                self.assertTrue(injected)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)
            finally:
                if held_descriptor >= 0:
                    try:
                        os.fstat(held_descriptor)
                    except OSError:
                        pass
                    else:
                        os.close(held_descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_workspace_ancestry_append_interrupt_never_double_closes_fd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "parent" / "output"
            output.mkdir(parents=True, mode=0o700)
            real_close_once = filesystem.close_fd_once
            release_calls: list[int] = []
            reused: list[int] = []
            armed = True
            injected = False
            ownership_states: list[bool] = []

            def interrupt_after_append(frame, event, _arg):
                nonlocal armed, injected
                if (
                    armed
                    and event == "line"
                    and frame.f_code
                    is production._pin_lexical_output_ancestry.__code__
                ):
                    bound = frame.f_locals.get("bound")
                    holder = frame.f_locals.get("owner_holder")
                    if (
                        isinstance(bound, tuple)
                        and isinstance(holder, list)
                        and any(item is bound for item in holder)
                    ):
                        armed = False
                        injected = True
                        ownership_states.append(
                            bool(frame.f_locals.get("transferred"))
                        )
                        raise KeyboardInterrupt(
                            "ancestry append interrupted"
                        )
                return interrupt_after_append

            def close_then_reuse(
                descriptor: int,
                capability: filesystem.CloseRangeCapability,
            ) -> None:
                real_close_once(descriptor, capability)
                release_calls.append(descriptor)
                if len(release_calls) == 1:
                    reused.append(os.open("/dev/null", os.O_RDONLY))

            try:
                workspace = None
                with mock.patch.object(
                    filesystem,
                    "close_fd_once",
                    side_effect=close_then_reuse,
                ):
                    sys.settrace(interrupt_after_append)
                    try:
                        with self.assertRaises(KeyboardInterrupt):
                            workspace = production._create_codeql_query_workspace(
                                output,
                                "growth",
                            )
                    finally:
                        sys.settrace(None)
                self.assertTrue(injected)
                self.assertEqual(ownership_states, [True])
                self.assertTrue(release_calls)
                self.assertEqual(len(release_calls), len(set(release_calls)))
                for descriptor in reused:
                    os.fstat(descriptor)
            finally:
                if workspace is not None:
                    workspace.close()
                for descriptor in reused:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_workspace_release_precall_interrupt_falls_back_and_continues(self) -> None:
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(3)]
        capability = filesystem.require_close_fd_once()
        info = os.fstat(source)
        workspace = production._CodeqlQueryWorkspace(
            output_root=Path("/unused"),
            stage="growth",
            name=".dosweb-growth-queries-test",
            close_capability=capability,
            output_parent_descriptor=-1,
            output_parent_info=info,
            output_ancestry=(),
            output_name="output",
            output_descriptor=descriptors[2],
            output_info=info,
            workspace_descriptor=descriptors[1],
            workspace_info=info,
            results_descriptor=descriptors[0],
            results_info=info,
        )
        real_close_once = filesystem.close_fd_once
        calls: list[int] = []

        def interrupt_before_first_close(descriptor, close_capability):
            calls.append(descriptor)
            if len(calls) == 1:
                raise filesystem.CloseRangePreActionError(
                    errno.EINTR,
                    "workspace release pre-call interrupt",
                )
            real_close_once(descriptor, close_capability)

        try:
            with mock.patch.object(
                filesystem,
                "close_fd_once",
                side_effect=interrupt_before_first_close,
            ):
                released = workspace.close()
            self.assertFalse(released)
            self.assertEqual(calls, descriptors)
            self.assertEqual(workspace.results_descriptor, -1)
            self.assertEqual(workspace.workspace_descriptor, -1)
            self.assertEqual(workspace.output_descriptor, -1)
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

    def test_workspace_release_defers_shared_helper_return_event(self) -> None:
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(3)]
        capability = filesystem.require_close_fd_once()
        info = os.fstat(source)
        workspace = production._CodeqlQueryWorkspace(
            output_root=Path("/unused"),
            stage="growth",
            name=".dosweb-growth-queries-test",
            close_capability=capability,
            output_parent_descriptor=-1,
            output_parent_info=info,
            output_ancestry=(),
            output_name="output",
            output_descriptor=descriptors[2],
            output_info=info,
            workspace_descriptor=descriptors[1],
            workspace_info=info,
            results_descriptor=descriptors[0],
            results_info=info,
        )
        injected = False

        def interrupt_helper_return(frame, event, _arg):
            nonlocal injected
            if (
                not injected
                and frame.f_code
                is filesystem.release_owned_descriptor_once.__code__
                and event == "return"
            ):
                injected = True
                raise KeyboardInterrupt("shared release helper return interrupted")

        try:
            sys.setprofile(interrupt_helper_return)
            try:
                released = workspace.close()
            finally:
                sys.setprofile(None)
            self.assertFalse(injected)
            self.assertTrue(released)
            self.assertEqual(workspace.results_descriptor, -1)
            self.assertEqual(workspace.workspace_descriptor, -1)
            self.assertEqual(workspace.output_descriptor, -1)
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

    def test_workspace_release_allocation_failure_falls_back_and_continues(
        self,
    ) -> None:
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(3)]
        capability = filesystem.require_close_fd_once()
        info = os.fstat(source)
        workspace = production._CodeqlQueryWorkspace(
            output_root=Path("/unused"),
            stage="growth",
            name=".dosweb-growth-queries-test",
            close_capability=capability,
            output_parent_descriptor=-1,
            output_parent_info=info,
            output_ancestry=(),
            output_name="output",
            output_descriptor=descriptors[2],
            output_info=info,
            workspace_descriptor=descriptors[1],
            workspace_info=info,
            results_descriptor=descriptors[0],
            results_info=info,
        )
        real_transaction = filesystem.DeferredCloseFdOnceOutcome
        allocations = 0

        def fail_first_allocation():
            nonlocal allocations
            allocations += 1
            if allocations == 1:
                raise MemoryError("release transaction allocation failed")
            return real_transaction()

        try:
            with mock.patch.object(
                filesystem,
                "DeferredCloseFdOnceOutcome",
                side_effect=fail_first_allocation,
            ):
                released = workspace.close()
            self.assertFalse(released)
            self.assertEqual(allocations, 3)
            self.assertEqual(workspace.results_descriptor, -1)
            self.assertEqual(workspace.workspace_descriptor, -1)
            self.assertEqual(workspace.output_descriptor, -1)
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

    def test_workspace_close_retries_deferred_release_call_entry_for_all_six_descriptors(
        self,
    ) -> None:
        for instrumentation in ("trace", "profile", "sigint"):
            with self.subTest(instrumentation=instrumentation):
                source = os.open("/dev/null", os.O_RDONLY)
                descriptors = [os.dup(source) for _ in range(6)]
                capability = filesystem.require_close_fd_once()
                info = os.fstat(source)
                ancestry = tuple(
                    production._LexicalDirectoryBinding(
                        f"ancestor-{index}", descriptor, info
                    )
                    for index, descriptor in enumerate(descriptors[:3])
                )
                workspace = production._CodeqlQueryWorkspace(
                    output_root=Path("/unused"),
                    stage="growth",
                    name=".dosweb-growth-queries-test",
                    close_capability=capability,
                    output_parent_descriptor=descriptors[2],
                    output_parent_info=info,
                    output_ancestry=ancestry,
                    output_name="output",
                    output_descriptor=descriptors[3],
                    output_info=info,
                    workspace_descriptor=descriptors[4],
                    workspace_info=info,
                    results_descriptor=descriptors[5],
                    results_info=info,
                )
                injected = False

                def interrupt_release_transaction(frame, event, _arg):
                    nonlocal injected
                    if (
                        not injected
                        and event == "call"
                        and frame.f_code
                        is filesystem.run_with_deferred_interrupts.__code__
                    ):
                        caller = frame.f_back
                        while caller is not None:
                            if (
                                caller.f_code
                                is production._CodeqlQueryWorkspace.close.__code__
                            ):
                                injected = True
                                if instrumentation == "sigint":
                                    os.kill(os.getpid(), signal.SIGINT)
                                else:
                                    raise KeyboardInterrupt(
                                        f"workspace {instrumentation} release entry"
                                    )
                            caller = caller.f_back
                    return interrupt_release_transaction

                try:
                    if instrumentation == "profile":
                        sys.setprofile(interrupt_release_transaction)
                    else:
                        sys.settrace(interrupt_release_transaction)
                    try:
                        released = workspace.close()
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)
                    self.assertTrue(injected)
                    self.assertFalse(released)
                    for descriptor in descriptors:
                        with self.assertRaises(OSError):
                            os.fstat(descriptor)
                    self.assertEqual(workspace.output_ancestry, ())
                    self.assertEqual(workspace.output_parent_descriptor, -1)
                    self.assertEqual(workspace.output_descriptor, -1)
                    self.assertEqual(workspace.workspace_descriptor, -1)
                    self.assertEqual(workspace.results_descriptor, -1)
                finally:
                    sys.setprofile(None)
                    sys.settrace(None)
                    workspace.close()
                    for descriptor in descriptors:
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass
                    os.close(source)

    def test_workspace_close_actual_close_then_exception_does_not_reclose_aba_fd(
        self,
    ) -> None:
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(6)]
        capability = filesystem.require_close_fd_once()
        info = os.fstat(source)
        workspace = production._CodeqlQueryWorkspace(
            output_root=Path("/unused"),
            stage="growth",
            name=".dosweb-growth-queries-test",
            close_capability=capability,
            output_parent_descriptor=descriptors[2],
            output_parent_info=info,
            output_ancestry=tuple(
                production._LexicalDirectoryBinding(
                    f"ancestor-{index}", descriptor, info
                )
                for index, descriptor in enumerate(descriptors[:3])
            ),
            output_name="output",
            output_descriptor=descriptors[3],
            output_info=info,
            workspace_descriptor=descriptors[4],
            workspace_info=info,
            results_descriptor=descriptors[5],
            results_info=info,
        )
        real_release = production._release_workspace_descriptor_once
        replacements: list[int] = []
        injected = False

        def close_then_interrupt(*args, **kwargs):
            nonlocal injected
            result = real_release(*args, **kwargs)
            if not injected:
                injected = True
                replacements.append(os.open("/dev/null", os.O_RDONLY))
                raise KeyboardInterrupt(
                    "workspace descriptor actual close then interruption"
                )
            return result

        try:
            with mock.patch.object(
                production,
                "_release_workspace_descriptor_once",
                side_effect=close_then_interrupt,
            ):
                released = workspace.close()
            self.assertTrue(injected)
            self.assertFalse(released)
            self.assertEqual(replacements, [descriptors[-1]])
            os.fstat(replacements[0])
            for descriptor in descriptors[:-1]:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
            self.assertEqual(workspace.output_ancestry, ())
            self.assertEqual(workspace.output_parent_descriptor, -1)
            self.assertEqual(workspace.output_descriptor, -1)
            self.assertEqual(workspace.workspace_descriptor, -1)
            self.assertEqual(workspace.results_descriptor, -1)
        finally:
            workspace.close()
            for descriptor in (*descriptors, *replacements):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(source)

    def test_workspace_close_second_release_call_interrupt_does_not_reclose_consumed_chain(
        self,
    ) -> None:
        source = os.open("/dev/null", os.O_RDONLY)
        descriptors = [os.dup(source) for _ in range(6)]
        capability = filesystem.require_close_fd_once()
        info = os.fstat(source)
        workspace = production._CodeqlQueryWorkspace(
            output_root=Path("/unused"),
            stage="growth",
            name=".dosweb-growth-queries-test",
            close_capability=capability,
            output_parent_descriptor=descriptors[2],
            output_parent_info=info,
            output_ancestry=tuple(
                production._LexicalDirectoryBinding(
                    f"ancestor-{index}", descriptor, info
                )
                for index, descriptor in enumerate(descriptors[:3])
            ),
            output_name="output",
            output_descriptor=descriptors[3],
            output_info=info,
            workspace_descriptor=descriptors[4],
            workspace_info=info,
            results_descriptor=descriptors[5],
            results_info=info,
        )
        real_release = production._release_workspace_descriptors
        calls = 0
        replacements: list[int] = []

        def interrupt_second_call(owner):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt(
                    "workspace second release call interrupted"
                )
            result = real_release(owner)
            replacements.extend(
                os.open("/dev/null", os.O_RDONLY)
                for _ in descriptors
            )
            return result

        try:
            with mock.patch.object(
                production,
                "_release_workspace_descriptors",
                side_effect=interrupt_second_call,
            ):
                released = workspace.close()
            self.assertFalse(released)
            self.assertEqual(calls, 2)
            self.assertEqual(replacements, descriptors)
            for descriptor in replacements:
                os.fstat(descriptor)
            self.assertEqual(workspace.output_ancestry, ())
            self.assertEqual(workspace.output_parent_descriptor, -1)
            self.assertEqual(workspace.output_descriptor, -1)
            self.assertEqual(workspace.workspace_descriptor, -1)
            self.assertEqual(workspace.results_descriptor, -1)
        finally:
            workspace.close()
            for descriptor in (*descriptors, *replacements):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(source)

    def test_workspace_release_and_final_cleanup_calls_have_lexical_retry_pairs(
        self,
    ) -> None:
        module = ast.parse(
            Path(production.__file__).read_text(encoding="utf-8")
        )
        parents = {
            child: parent
            for parent in ast.walk(module)
            for child in ast.iter_child_nodes(parent)
        }

        def owner(candidate: ast.AST) -> str | None:
            current = parents.get(candidate)
            while current is not None:
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return current.name
                current = parents.get(current)
            return None

        def calls_named(candidate: ast.AST, name: str) -> list[ast.Call]:
            return [
                item
                for item in ast.walk(candidate)
                if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == name
            ]

        def paired_owners(name: str) -> tuple[list[ast.Call], list[str | None]]:
            all_calls = calls_named(module, name)
            paired: list[ast.Call] = []
            owners: list[str | None] = []
            for candidate in ast.walk(module):
                if (
                    not isinstance(candidate, ast.Try)
                    or candidate.handlers
                    or candidate.orelse
                ):
                    continue
                body_calls = [
                    call
                    for statement in candidate.body
                    for call in calls_named(statement, name)
                ]
                final_calls = [
                    call
                    for statement in candidate.finalbody
                    for call in calls_named(statement, name)
                ]
                if len(body_calls) != 1 or len(final_calls) != 1:
                    continue
                if ast.dump(
                    body_calls[0], include_attributes=False
                ) != ast.dump(final_calls[0], include_attributes=False):
                    continue
                paired.extend((body_calls[0], final_calls[0]))
                owners.append(owner(candidate))
            self.assertEqual(
                {id(call) for call in all_calls},
                {id(call) for call in paired},
            )
            return all_calls, owners

        release_calls, release_owners = paired_owners(
            "_release_workspace_descriptors"
        )
        self.assertEqual(len(release_calls), 10)
        self.assertEqual(
            Counter(release_owners),
            Counter(
                {
                    "close": 1,
                    "_pin_lexical_output_ancestry": 1,
                    "_capture_query_output_binding": 1,
                    "_create_codeql_query_workspace": 1,
                    "_workspace_has_safe_generation_inventory": 1,
                }
            ),
        )
        cleanup_calls, cleanup_owners = paired_owners(
            "_cleanup_codeql_query_workspace"
        )
        self.assertEqual(len(cleanup_calls), 12)
        self.assertEqual(
            Counter(cleanup_owners),
            Counter(
                {
                    "_run_codeql_snapshot_suite": 2,
                    "_run_codeql_family": 2,
                    "execute": 2,
                }
            ),
        )
        snapshot_calls, snapshot_owners = paired_owners("snapshot_cleanup")
        self.assertEqual(len(snapshot_calls), 2)
        self.assertEqual(Counter(snapshot_owners), Counter({"finalizer": 1}))

    def test_formal_snapshot_cleanup_has_no_unpaired_direct_callers(self) -> None:
        package_root = Path(production.__file__).parent
        imports: list[tuple[str, str | None]] = []
        direct_calls: list[str] = []
        for source_path in sorted(package_root.rglob("*.py")):
            relative = source_path.relative_to(package_root).as_posix()
            module = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(module):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "dosweb.codeql.database"
                ):
                    imports.extend(
                        (relative, alias.asname)
                        for alias in node.names
                        if alias.name
                        == "cleanup_execution_database_snapshot"
                    )
                if not isinstance(node, ast.Call):
                    continue
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id
                    == "cleanup_execution_database_snapshot"
                ) or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr
                    == "cleanup_execution_database_snapshot"
                ):
                    direct_calls.append(f"{relative}:{node.lineno}")

        self.assertEqual(
            imports,
            [
                ("codeql/__init__.py", None),
                ("production.py", "_cleanup_execution_database_snapshot"),
            ],
        )
        self.assertEqual(direct_calls, [])

    def test_workspace_ancestry_open_return_interrupt_has_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "parent" / "output"
            output.mkdir(parents=True, mode=0o700)
            baseline = {
                int(name)
                for name in os.listdir("/proc/self/fd")
                if name.isdigit()
            }
            armed = True
            injected = False

            def interrupt_open_return(frame, event, arg):
                nonlocal armed, injected
                if (
                    armed
                    and frame.f_code
                    is production._pin_lexical_output_ancestry.__code__
                    and event == "return"
                    and isinstance(arg, tuple)
                ):
                    armed = False
                    injected = True
                    raise KeyboardInterrupt(
                        "ancestry factory return interrupted"
                    )

            workspace = None
            sys.setprofile(interrupt_open_return)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    workspace = production._create_codeql_query_workspace(
                        output,
                        "growth",
                    )
            finally:
                sys.setprofile(None)
                if workspace is not None:
                    workspace.close()
            self.assertTrue(injected)
            after = {
                int(name)
                for name in os.listdir("/proc/self/fd")
                if name.isdigit()
            }
            leaked = sorted(after - baseline)
            try:
                self.assertFalse(leaked)
            finally:
                for descriptor in leaked:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_workspace_results_open_return_interrupt_has_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "parent" / "output"
            output.mkdir(parents=True, mode=0o700)
            baseline = {
                int(name)
                for name in os.listdir("/proc/self/fd")
                if name.isdigit()
            }
            armed = True
            injected = False

            def interrupt_results_return(frame, event, _arg):
                nonlocal armed, injected
                if (
                    armed
                    and frame.f_code
                    is production._open_owned_directory_descriptor.__code__
                    and event == "return"
                    and frame.f_locals.get("name") == "results"
                ):
                    armed = False
                    injected = True
                    raise KeyboardInterrupt(
                        "results descriptor return interrupted"
                    )

            workspace = None
            sys.setprofile(interrupt_results_return)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    workspace = production._create_codeql_query_workspace(
                        output,
                        "growth",
                    )
            finally:
                sys.setprofile(None)
                if workspace is not None:
                    workspace.close()
            self.assertTrue(injected)
            after = {
                int(name)
                for name in os.listdir("/proc/self/fd")
                if name.isdigit()
            }
            leaked = sorted(after - baseline)
            try:
                self.assertFalse(leaked)
            finally:
                for descriptor in leaked:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_owned_open_restores_signal_mask_after_profile_restore_failure(
        self,
    ) -> None:
        if not hasattr(signal, "pthread_sigmask"):
            self.skipTest("pthread_sigmask is unavailable")
        owner: list[int] = []
        profile_sentinel = lambda *_args: None
        mask_calls: list[tuple[object, object]] = []
        profile_calls = 0

        def set_profile(value):
            nonlocal profile_calls
            profile_calls += 1
            if value is profile_sentinel:
                raise KeyboardInterrupt("profile restore interrupted")

        def set_mask(how, mask):
            mask_calls.append((how, mask))
            if how == signal.SIG_BLOCK:
                return {signal.SIGTERM}
            return set()

        try:
            with mock.patch.object(
                production.sys,
                "getprofile",
                return_value=profile_sentinel,
            ), mock.patch.object(
                production.sys,
                "setprofile",
                side_effect=set_profile,
            ), mock.patch.object(
                production.signal,
                "pthread_sigmask",
                side_effect=set_mask,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    production._open_owned_directory_descriptor(owner, "/")
            self.assertEqual(profile_calls, 2)
            self.assertEqual(
                mask_calls,
                [
                    (signal.SIG_BLOCK, set()),
                    (signal.SIG_BLOCK, {signal.SIGINT}),
                    (signal.SIG_SETMASK, {signal.SIGTERM}),
                ],
            )
            self.assertEqual(len(owner), 1)
            os.fstat(owner[0])
        finally:
            for descriptor in owner:
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_owned_open_restores_signal_mask_after_block_postaction(self) -> None:
        if not hasattr(signal, "pthread_sigmask"):
            self.skipTest("pthread_sigmask is unavailable")
        owner: list[int] = []
        current_mask: set[signal.Signals] = {signal.SIGTERM}
        calls: list[tuple[object, set[signal.Signals]]] = []

        def set_mask(how, mask):
            normalized = set(mask)
            calls.append((how, normalized))
            if how == signal.SIG_BLOCK:
                previous = set(current_mask)
                current_mask.update(normalized)
                if normalized == {signal.SIGINT}:
                    raise KeyboardInterrupt("signal block post-action")
                return previous
            if how == signal.SIG_SETMASK:
                current_mask.clear()
                current_mask.update(normalized)
                return set()
            raise AssertionError("unexpected signal mask operation")

        with mock.patch.object(
            production.signal,
            "pthread_sigmask",
            side_effect=set_mask,
        ):
            with self.assertRaises(KeyboardInterrupt):
                production._open_owned_directory_descriptor(owner, "/")
        self.assertEqual(current_mask, {signal.SIGTERM})
        self.assertIn((signal.SIG_BLOCK, set()), calls)
        self.assertIn(
            (signal.SIG_SETMASK, {signal.SIGTERM}),
            calls,
        )

    def test_owned_open_restores_instrumentation_after_disable_postaction(
        self,
    ) -> None:
        for setter_name, getter_name in (
            ("setprofile", "getprofile"),
            ("settrace", "gettrace"),
        ):
            with self.subTest(setter=setter_name):
                owner: list[int] = []
                sentinel = lambda *_args: None
                state = [sentinel]
                calls: list[object] = []

                def set_instrumentation(value):
                    calls.append(value)
                    state[0] = value
                    if value is None and len(calls) == 1:
                        raise KeyboardInterrupt(
                            f"{setter_name} disable post-action"
                        )

                with mock.patch.object(
                    production.sys,
                    getter_name,
                    return_value=sentinel,
                ), mock.patch.object(
                    production.sys,
                    setter_name,
                    side_effect=set_instrumentation,
                ):
                    with self.assertRaises(KeyboardInterrupt):
                        production._open_owned_directory_descriptor(owner, "/")
                self.assertIs(state[0], sentinel)
                self.assertIs(calls[-1], sentinel)
                for descriptor in owner:
                    if descriptor >= 0:
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass

    def test_family_owns_workspace_before_factory_return_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            baseline = {
                int(name)
                for name in os.listdir("/proc/self/fd")
                if name.isdigit()
            }
            injected = False

            def interrupt_factory_return(frame, event, _arg):
                nonlocal injected
                if (
                    not injected
                    and frame.f_code
                    is production._create_codeql_query_workspace.__code__
                    and event == "return"
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "workspace factory return interrupted"
                    )

            sys.setprofile(interrupt_factory_return)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    production._run_codeql_family(
                        SimpleNamespace(output=output),
                        object(),
                        "growth",
                        root,
                        lambda *_args, **_kwargs: None,
                    )
            finally:
                sys.setprofile(None)
            self.assertTrue(injected)
            after = {
                int(name)
                for name in os.listdir("/proc/self/fd")
                if name.isdigit()
            }
            leaked = sorted(after - baseline)
            try:
                self.assertFalse(leaked)
            finally:
                for descriptor in leaked:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_runner_return_interrupt_releases_unattached_private_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            workspace = production._create_codeql_query_workspace(
                output,
                "growth",
            )
            held: dict[str, object] = {}
            armed = False

            def interrupted_runner(
                query: Path,
                _database: object,
                _output_dir: Path,
                **_kwargs: object,
            ) -> QueryResult:
                nonlocal armed
                os.mkdir(
                    ".generations",
                    mode=0o700,
                    dir_fd=workspace.results_descriptor,
                )
                generations_descriptor = os.open(
                    ".generations",
                    os.O_RDONLY | os.O_DIRECTORY,
                    dir_fd=workspace.results_descriptor,
                )
                try:
                    os.mkdir(
                        "Growth-normal",
                        mode=0o700,
                        dir_fd=generations_descriptor,
                    )
                    generation_descriptor = os.open(
                        "Growth-normal",
                        os.O_RDONLY | os.O_DIRECTORY,
                        dir_fd=generations_descriptor,
                    )
                    try:
                        decoded_descriptor = os.open(
                            "Growth.json",
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=generation_descriptor,
                        )
                        try:
                            os.write(decoded_descriptor, b"{}")
                        finally:
                            os.close(decoded_descriptor)
                    finally:
                        os.close(generation_descriptor)
                finally:
                    os.close(generations_descriptor)
                binding = codeql_runner._pin_query_output_binding(
                    workspace.results_descriptor,
                    "Growth-normal",
                    "Growth.json",
                    workspace.close_capability,
                )
                held["binding"] = binding
                generation = (
                    workspace.results
                    / ".generations"
                    / "Growth-normal"
                )
                result = QueryResult(
                    query.name,
                    generation / query.name,
                    generation / "Growth.bqrs",
                    generation / "Growth.json",
                    "a" * 64,
                    "b" * 64,
                    _output_binding=binding,
                )
                armed = True
                return result

            def interrupt_return(frame, event, _arg):
                if (
                    armed
                    and frame.f_code is interrupted_runner.__code__
                    and event == "return"
                ):
                    raise KeyboardInterrupt("runner return interrupted")

            sys.setprofile(interrupt_return)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    production._run_workspace_query(
                        workspace,
                        interrupted_runner,
                        root / "Growth.ql",
                        object(),
                        SimpleNamespace(codeql_binary="codeql"),
                    )
            finally:
                sys.setprofile(None)
            binding = held["binding"]
            assert isinstance(binding, codeql_runner._QueryOutputBinding)
            try:
                self.assertEqual(binding.decoded_descriptor, -1)
                self.assertEqual(binding.generation_descriptor, -1)
                self.assertEqual(binding.generations_descriptor, -1)
                self.assertEqual(workspace.query_bindings, [])
            finally:
                for field in (
                    "decoded_descriptor",
                    "generation_descriptor",
                    "generations_descriptor",
                ):
                    descriptor = getattr(binding, field)
                    if descriptor >= 0:
                        os.close(descriptor)
                        setattr(binding, field, -1)
                self.assertTrue(workspace.close())
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_real_runner_registers_private_binding_before_return_event(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            database_path = root / "database"
            (database_path / "db-java").mkdir(parents=True)
            (database_path / "codeql-database.yml").write_text(
                "primaryLanguage: java\n"
                f"sourceLocationPrefix: {source}\n",
                encoding="utf-8",
            )
            (
                database_path
                / "db-java"
                / "database-relations.json"
            ).write_text('{"relations":[]}', encoding="utf-8")
            database = codeql_database.validate_database(database_path)
            query = root / "Growth.ql"
            query.write_text("select 1", encoding="utf-8")
            output = root / "output"
            output.mkdir(mode=0o700)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            workspace = production._create_codeql_query_workspace(
                output,
                "growth",
            )

            def successful_run(argv, **_kwargs):
                target = Path(argv[argv.index("--output") + 1])
                if argv[1:3] == ["query", "run"]:
                    target.write_bytes(b"bqrs")
                else:
                    target.write_text(
                        json.dumps(
                            {
                                "#select": {
                                    "columns": [
                                        {"name": name, "kind": "String"}
                                        for name in GROWTH_COLUMNS
                                    ],
                                    "tuples": [],
                                }
                            }
                        ),
                        encoding="utf-8",
                    )
                return subprocess.CompletedProcess(
                    argv, 0, stdout="", stderr=""
                )

            def real_runner(*args: object, **kwargs: object) -> QueryResult:
                kwargs["subprocess_run"] = successful_run
                return codeql_runner.run_query(*args, **kwargs)

            def interrupt_run_query_return(frame, event, arg):
                if (
                    frame.f_code is codeql_runner.run_query.__code__
                    and event == "return"
                    and isinstance(arg, QueryResult)
                ):
                    raise KeyboardInterrupt("run_query return interrupted")

            sys.setprofile(interrupt_run_query_return)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    production._run_workspace_query(
                        workspace,
                        real_runner,
                        query,
                        database,
                        SimpleNamespace(codeql_binary="codeql"),
                    )
            finally:
                sys.setprofile(None)
            try:
                self.assertEqual(len(workspace.query_bindings), 1)
                binding = workspace.query_bindings[0]
                self.assertTrue(binding.attached)
                self.assertGreaterEqual(binding.decoded_descriptor, 0)
                self.assertGreaterEqual(binding.generation_descriptor, 0)
                self.assertGreaterEqual(binding.generations_descriptor, 0)
            finally:
                self.assertTrue(workspace.close())
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_capture_interrupt_before_registration_keeps_binding_unattached(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            workspace = production._create_codeql_query_workspace(
                output,
                "growth",
            )
            results_descriptor = workspace.results_descriptor
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
            os.mkdir(
                "Growth-normal",
                mode=0o700,
                dir_fd=generations_descriptor,
            )
            generation_descriptor = os.open(
                "Growth-normal",
                os.O_RDONLY | os.O_DIRECTORY,
                dir_fd=generations_descriptor,
            )
            decoded_descriptor = os.open(
                "Growth.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=generation_descriptor,
            )
            os.write(decoded_descriptor, b"{}")
            os.close(decoded_descriptor)
            os.close(generation_descriptor)
            os.close(generations_descriptor)
            binding = codeql_runner._pin_query_output_binding(
                results_descriptor,
                "Growth-normal",
                "Growth.json",
                workspace.close_capability,
            )
            descriptors = (
                binding.decoded_descriptor,
                binding.generation_descriptor,
                binding.generations_descriptor,
            )
            generation = (
                workspace.results / ".generations" / "Growth-normal"
            )
            result = QueryResult(
                "growth",
                generation / "Growth.ql",
                generation / "Growth.bqrs",
                generation / "Growth.json",
                "a" * 64,
                "b" * 64,
                _output_binding=binding,
            )
            with mock.patch.object(
                production,
                "_query_output_binding_current",
                side_effect=KeyboardInterrupt("capture interrupted"),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    production._capture_query_output_binding(
                        workspace,
                        result,
                    )
            self.assertFalse(binding.attached)
            self.assertEqual(workspace.query_bindings, [])
            del result
            gc.collect()
            try:
                for descriptor in descriptors:
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)
            finally:
                for descriptor in descriptors:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                self.assertTrue(workspace.close())
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_family_generation_swap_after_inventory_rejects_forged_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            pipeline = build_production_pipeline(
                {**self._values(root), "command": "entries"},
                environ={},
            )
            database = DatabaseInfo(root / "database", root, "d" * 64)
            held: dict[str, object] = {}
            injected = False

            def runner_with_competing_generation(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                results_descriptor = kwargs["output_descriptor"]
                assert isinstance(results_descriptor, int)
                stable_results = Path(
                    os.readlink(f"/proc/self/fd/{results_descriptor}")
                )
                generations = output_dir / ".generations"
                competitor = output_dir / ".generations-competitor"
                generations.mkdir(mode=0o700)
                competitor.mkdir(mode=0o700)
                generation_name = "Growth-normal"
                original_generation = generations / generation_name
                forged_generation = competitor / generation_name
                original_generation.mkdir(mode=0o700)
                forged_generation.mkdir(mode=0o700)
                (original_generation / "original-marker").write_text(
                    "original-marker", encoding="utf-8"
                )
                (forged_generation / "forged-marker").write_text(
                    "forged-marker", encoding="utf-8"
                )
                decoded_name = f"{query.stem}.json"
                decoded = original_generation / decoded_name
                decoded.write_text(
                    '{"marker":"original"}', encoding="utf-8"
                )
                (forged_generation / decoded_name).write_text(
                    '{"marker":"forged"}', encoding="utf-8"
                )
                original_fd = os.open(
                    generations,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                forged_fd = os.open(
                    competitor,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                held.update(
                    results_descriptor=results_descriptor,
                    results=stable_results,
                    original_fd=original_fd,
                    forged_fd=forged_fd,
                    original_info=os.fstat(original_fd),
                    forged_info=os.fstat(forged_fd),
                    generation_name=generation_name,
                )
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            real_bounded_json = production._bounded_json_file

            def exchange_before_read(*args: object, **kwargs: object):
                nonlocal injected
                if not injected:
                    results_descriptor = held["results_descriptor"]
                    assert isinstance(results_descriptor, int)
                    filesystem.renameat2_exchange(
                        results_descriptor,
                        ".generations",
                        results_descriptor,
                        ".generations-competitor",
                    )
                    injected = True
                return real_bounded_json(*args, **kwargs)

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    production,
                    "_query_files",
                    return_value=(root / "Growth.ql",),
                ), mock.patch.object(
                    production,
                    "_bounded_json_file",
                    side_effect=exchange_before_read,
                ), mock.patch.object(
                    production,
                    "decode_bqrs_json",
                    return_value=[],
                ) as decode:
                    with self.assertRaises(AnalyzerError) as raised:
                        production._run_codeql_family(
                            pipeline.config,
                            database,
                            "growth",
                            root / "pack",
                            runner_with_competing_generation,
                        )

                self.assertTrue(injected)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertNotIn(
                    str(root), json.dumps(raised.exception.details)
                )
                decode.assert_not_called()
                results = held["results"]
                generation_name = held["generation_name"]
                assert isinstance(results, Path)
                assert isinstance(generation_name, str)
                for path, fd_key, info_key, marker in (
                    (
                        results / ".generations-competitor",
                        "original_fd",
                        "original_info",
                        "original-marker",
                    ),
                    (
                        results / ".generations",
                        "forged_fd",
                        "forged_info",
                        "forged-marker",
                    ),
                ):
                    descriptor = held[fd_key]
                    expected = held[info_key]
                    assert isinstance(descriptor, int)
                    assert isinstance(expected, os.stat_result)
                    current = path.stat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino, current.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (path / generation_name / marker).read_text(
                            encoding="utf-8"
                        ),
                        marker,
                    )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 2
                )
            finally:
                for key in ("forged_fd", "original_fd"):
                    descriptor = held.get(key)
                    if isinstance(descriptor, int):
                        os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_family_rejects_same_inode_decoded_overwrite_during_parse(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            pipeline = build_production_pipeline(
                {**self._values(root), "command": "entries"},
                environ={},
            )
            database = DatabaseInfo(root / "database", root, "d" * 64)
            held: dict[str, object] = {}
            genuine = b'{"marker":"original"}'
            forged = b'{"marker":"forged__"}'
            self.assertEqual(len(genuine), len(forged))

            def runner_with_decoded_file(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **_kwargs: object,
            ) -> QueryResult:
                generations = output_dir / ".generations"
                generation = generations / "Growth-normal"
                generations.mkdir(mode=0o700)
                generation.mkdir(mode=0o700)
                decoded = generation / f"{query.stem}.json"
                decoded.write_bytes(genuine)
                decoded.chmod(0o600)
                held["decoded"] = decoded
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            real_json_loads = production.json.loads
            injected = False

            def overwrite_during_parse(*args: object, **kwargs: object):
                nonlocal injected
                if not injected:
                    decoded = held["decoded"]
                    assert isinstance(decoded, Path)
                    with decoded.open("r+b") as stream:
                        stream.write(forged)
                        stream.flush()
                        os.fsync(stream.fileno())
                    injected = True
                return real_json_loads(*args, **kwargs)

            with mock.patch.object(
                production,
                "_query_files",
                return_value=(root / "Growth.ql",),
            ), mock.patch.object(
                production.json,
                "loads",
                side_effect=overwrite_during_parse,
            ), mock.patch.object(
                production,
                "decode_bqrs_json",
                return_value=[],
            ) as decode:
                with self.assertRaises(AnalyzerError) as raised:
                    production._run_codeql_family(
                        pipeline.config,
                        database,
                        "growth",
                        root / "pack",
                        runner_with_decoded_file,
                    )

            self.assertTrue(injected)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            decode.assert_not_called()

    def test_formal_entries_rejects_same_inode_decoded_overwrite_and_resume_reruns(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependency>org.springframework</dependency></project>",
                encoding="utf-8",
            )
            database = DatabaseInfo(root / "database", source, "d" * 64)
            values = self._values(root)
            values.update(
                command="entries",
                source_checkout=source,
                analysis_source_root=source,
            )
            holder = build_production_pipeline(
                values,
                environ={},
                stage_executors={
                    stage: (lambda _context: StageOutput({}))
                    for stage in STAGES
                },
            )
            output = root / "output"
            held: dict[str, Path] = {}
            query_calls = 0
            genuine = b'{"marker":"original"}'
            forged = b'{"marker":"forged__"}'
            self.assertEqual(len(genuine), len(forged))

            def runner_with_decoded_file(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **_kwargs: object,
            ) -> QueryResult:
                nonlocal query_calls
                query_calls += 1
                generations = output_dir / ".generations"
                generation = generations / f"{query.stem}-normal"
                generations.mkdir(mode=0o700)
                generation.mkdir(mode=0o700)
                decoded = generation / f"{query.stem}.json"
                decoded.write_bytes(genuine)
                decoded.chmod(0o600)
                held["decoded"] = decoded
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            executor = production.make_entries_executor(
                holder.config,
                database_info_fn=lambda: database,
                run_query_fn=runner_with_decoded_file,
            )
            real_bounded_json = production._bounded_json_file
            injected = False

            def overwrite_before_read(*args: object, **kwargs: object):
                nonlocal injected
                if not injected:
                    decoded = held["decoded"]
                    with decoded.open("r+b") as stream:
                        stream.write(forged)
                        stream.flush()
                        os.fsync(stream.fileno())
                    injected = True
                return real_bounded_json(*args, **kwargs)

            pipeline = Pipeline(
                output,
                {"entries": executor},
                implementation_versions={
                    "entries": "decoded-content-binding-test"
                },
            )
            with mock.patch.object(
                production,
                "_bounded_json_file",
                side_effect=overwrite_before_read,
            ), mock.patch.object(
                production,
                "decode_bqrs_json",
                wraps=production.decode_bqrs_json,
            ) as decode:
                with self.assertRaises(AnalyzerError) as raised:
                    pipeline.run("entries")

            self.assertTrue(injected)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertNotIn(str(root), json.dumps(raised.exception.details))
            decode.assert_not_called()
            self.assertEqual(query_calls, 1)
            self.assertEqual(
                json.loads(
                    (output / "run.json").read_text(encoding="utf-8")
                )["status"],
                "failed",
            )
            self.assertFalse((output / "entry_facts.jsonl").exists())
            self.assertFalse(
                (output / ".stage-manifests" / "entries.json").exists()
            )

            resume_calls = 0

            def fail_resume(
                *_args: object,
                **_kwargs: object,
            ) -> QueryResult:
                nonlocal resume_calls
                resume_calls += 1
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                )

            resumed_executor = production.make_entries_executor(
                holder.config,
                database_info_fn=lambda: database,
                run_query_fn=fail_resume,
            )
            with self.assertRaises(AnalyzerError) as resumed_failure:
                Pipeline(
                    output,
                    {"entries": resumed_executor},
                    implementation_versions={
                        "entries": "decoded-content-binding-test"
                    },
                    resume=True,
                ).run("entries")
            self.assertEqual(
                resumed_failure.exception.code, "CODEQL_QUERY_FAILED"
            )
            self.assertEqual(resume_calls, 1)
            self.assertEqual(
                json.loads(
                    (output / "run.json").read_text(encoding="utf-8")
                )["status"],
                "failed",
            )

    def test_formal_entries_output_root_swap_fails_and_resume_reruns(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependency>org.springframework</dependency></project>",
                encoding="utf-8",
            )
            database = DatabaseInfo(root / "database", source, "d" * 64)
            values = self._values(root)
            values.update(
                command="entries",
                source_checkout=source,
                analysis_source_root=source,
            )
            holder = build_production_pipeline(
                values,
                environ={},
                stage_executors={
                    stage: (lambda _context: StageOutput({}))
                    for stage in STAGES
                },
            )
            output = root / "output"
            original_root = root / "output-original"
            held: dict[str, object] = {}
            calls = 0

            def swap_root_and_forge_entry_json(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                nonlocal calls
                calls += 1
                descriptor = kwargs.get("output_descriptor")
                if isinstance(descriptor, int):
                    stable_results = Path(
                        os.readlink(f"/proc/self/fd/{descriptor}")
                    )
                else:
                    stable_results = output_dir
                if not held:
                    workspace_name = stable_results.parent.name
                    (output / "original-marker").write_text(
                        "original-marker", encoding="utf-8"
                    )
                    original_fd = os.open(
                        output,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    output.rename(original_root)
                    output.mkdir(mode=0o700)
                    (output / "replacement-marker").write_text(
                        "replacement-marker", encoding="utf-8"
                    )
                    replacement_fd = os.open(
                        output,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    held.update(
                        workspace_name=workspace_name,
                        original_fd=original_fd,
                        replacement_fd=replacement_fd,
                    )
                workspace_name = held["workspace_name"]
                assert isinstance(workspace_name, str)
                replacement_results = output / workspace_name / "results"
                replacement_results.mkdir(parents=True, exist_ok=True)
                decoded = replacement_results / f"{query.stem}.json"
                decoded.write_text(
                    json.dumps(self._payload_for_query(query)),
                    encoding="utf-8",
                )
                original_fd = held["original_fd"]
                replacement_fd = held["replacement_fd"]
                assert isinstance(original_fd, int)
                assert isinstance(replacement_fd, int)
                held.update(
                    original_info=os.fstat(original_fd),
                    replacement_info=os.fstat(replacement_fd),
                )
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            executor = production.make_entries_executor(
                holder.config,
                database_info_fn=lambda: database,
                run_query_fn=swap_root_and_forge_entry_json,
            )
            pipeline = Pipeline(
                output,
                {"entries": executor},
                implementation_versions={"entries": "root-binding-test"},
            )
            baseline_fds = len(os.listdir("/proc/self/fd"))
            real_decode = production.decode_bqrs_json
            try:
                with mock.patch.object(
                    production,
                    "decode_bqrs_json",
                    side_effect=real_decode,
                ) as decode:
                    with self.assertRaises(AnalyzerError) as raised:
                        pipeline.run("entries")

                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertNotIn(
                    str(root), json.dumps(raised.exception.details)
                )
                decode.assert_not_called()
                self.assertEqual(calls, 1)
                self.assertEqual(
                    json.loads(
                        (output / "run.json").read_text(encoding="utf-8")
                    )["status"],
                    "failed",
                )
                self.assertFalse((output / "entries.jsonl").exists())
                self.assertFalse(
                    (output / ".stage-manifests" / "entries.json").exists()
                )
                for path, fd_key, info_key, marker in (
                    (
                        original_root,
                        "original_fd",
                        "original_info",
                        "original-marker",
                    ),
                    (
                        output,
                        "replacement_fd",
                        "replacement_info",
                        "replacement-marker",
                    ),
                ):
                    descriptor = held[fd_key]
                    expected = held[info_key]
                    assert isinstance(descriptor, int)
                    assert isinstance(expected, os.stat_result)
                    current = path.stat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino, current.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (path / marker).read_text(encoding="utf-8"), marker
                    )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 2
                )
            finally:
                for key in ("replacement_fd", "original_fd"):
                    descriptor = held.get(key)
                    if isinstance(descriptor, int):
                        os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

            resume_calls = 0

            def fail_resume(
                *_args: object,
                **_kwargs: object,
            ) -> QueryResult:
                nonlocal resume_calls
                resume_calls += 1
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                )

            resumed_executor = production.make_entries_executor(
                holder.config,
                database_info_fn=lambda: database,
                run_query_fn=fail_resume,
            )
            with self.assertRaises(AnalyzerError) as resumed_failure:
                Pipeline(
                    output,
                    {"entries": resumed_executor},
                    implementation_versions={
                        "entries": "root-binding-test"
                    },
                    resume=True,
                ).run("entries")
            self.assertEqual(
                resumed_failure.exception.code, "CODEQL_QUERY_FAILED"
            )
            self.assertEqual(resume_calls, 1)
            self.assertEqual(
                json.loads(
                    (output / "run.json").read_text(encoding="utf-8")
                )["status"],
                "failed",
            )
            self.assertEqual(
                (original_root / "original-marker").read_text(
                    encoding="utf-8"
                ),
                "original-marker",
            )
            self.assertEqual(
                (output / "replacement-marker").read_text(
                    encoding="utf-8"
                ),
                "replacement-marker",
            )

    def test_formal_entries_generation_swap_after_inventory_fails_and_reruns(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependency>org.springframework</dependency></project>",
                encoding="utf-8",
            )
            database = DatabaseInfo(root / "database", source, "d" * 64)
            values = self._values(root)
            values.update(
                command="entries",
                source_checkout=source,
                analysis_source_root=source,
            )
            holder = build_production_pipeline(
                values,
                environ={},
                stage_executors={
                    stage: (lambda _context: StageOutput({}))
                    for stage in STAGES
                },
            )
            output = root / "output"
            held: dict[str, object] = {}
            query_calls = 0
            injected = False

            def runner_with_competing_generation(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                nonlocal query_calls
                query_calls += 1
                results_descriptor = kwargs["output_descriptor"]
                assert isinstance(results_descriptor, int)
                stable_results = Path(
                    os.readlink(f"/proc/self/fd/{results_descriptor}")
                )
                generations = output_dir / ".generations"
                generations.mkdir(mode=0o700, exist_ok=True)
                generation_name = f"{query.stem}-normal-{query_calls}"
                generation = generations / generation_name
                generation.mkdir(mode=0o700)
                decoded_name = f"{query.stem}.json"
                decoded = generation / decoded_name
                decoded.write_text(
                    json.dumps(self._payload_for_query(query)),
                    encoding="utf-8",
                )
                if not held:
                    competitor = output_dir / ".generations-competitor"
                    competitor.mkdir(mode=0o700)
                    forged_generation = competitor / generation_name
                    forged_generation.mkdir(mode=0o700)
                    (generation / "original-marker").write_text(
                        "original-marker", encoding="utf-8"
                    )
                    (forged_generation / "forged-marker").write_text(
                        "forged-marker", encoding="utf-8"
                    )
                    (forged_generation / decoded_name).write_text(
                        json.dumps(self._payload_for_query(query)),
                        encoding="utf-8",
                    )
                    original_fd = os.open(
                        generations,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    forged_fd = os.open(
                        competitor,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    held.update(
                        results_descriptor=results_descriptor,
                        results=stable_results,
                        generation_name=generation_name,
                        original_fd=original_fd,
                        forged_fd=forged_fd,
                        original_info=os.fstat(original_fd),
                        forged_info=os.fstat(forged_fd),
                    )
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            executor = production.make_entries_executor(
                holder.config,
                database_info_fn=lambda: database,
                run_query_fn=runner_with_competing_generation,
            )
            real_bounded_json = production._bounded_json_file

            def exchange_before_read(*args: object, **kwargs: object):
                nonlocal injected
                if not injected:
                    results_descriptor = held["results_descriptor"]
                    assert isinstance(results_descriptor, int)
                    filesystem.renameat2_exchange(
                        results_descriptor,
                        ".generations",
                        results_descriptor,
                        ".generations-competitor",
                    )
                    injected = True
                return real_bounded_json(*args, **kwargs)

            pipeline = Pipeline(
                output,
                {"entries": executor},
                implementation_versions={
                    "entries": "generation-binding-test"
                },
            )
            baseline_fds = len(os.listdir("/proc/self/fd"))
            real_decode = production.decode_bqrs_json
            try:
                with mock.patch.object(
                    production,
                    "_bounded_json_file",
                    side_effect=exchange_before_read,
                ), mock.patch.object(
                    production,
                    "decode_bqrs_json",
                    side_effect=real_decode,
                ) as decode:
                    with self.assertRaises(AnalyzerError) as raised:
                        pipeline.run("entries")

                self.assertTrue(injected)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertNotIn(
                    str(root), json.dumps(raised.exception.details)
                )
                decode.assert_not_called()
                self.assertEqual(query_calls, 1)
                self.assertEqual(
                    json.loads(
                        (output / "run.json").read_text(encoding="utf-8")
                    )["status"],
                    "failed",
                )
                self.assertFalse((output / "entries.jsonl").exists())
                self.assertFalse(
                    (output / ".stage-manifests" / "entries.json").exists()
                )
                results = held["results"]
                generation_name = held["generation_name"]
                assert isinstance(results, Path)
                assert isinstance(generation_name, str)
                for path, fd_key, info_key, marker in (
                    (
                        results / ".generations-competitor",
                        "original_fd",
                        "original_info",
                        "original-marker",
                    ),
                    (
                        results / ".generations",
                        "forged_fd",
                        "forged_info",
                        "forged-marker",
                    ),
                ):
                    descriptor = held[fd_key]
                    expected = held[info_key]
                    assert isinstance(descriptor, int)
                    assert isinstance(expected, os.stat_result)
                    current = path.stat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino, current.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (path / generation_name / marker).read_text(
                            encoding="utf-8"
                        ),
                        marker,
                    )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 2
                )
            finally:
                for key in ("forged_fd", "original_fd"):
                    descriptor = held.get(key)
                    if isinstance(descriptor, int):
                        os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

            resume_calls = 0

            def fail_resume(
                *_args: object,
                **_kwargs: object,
            ) -> QueryResult:
                nonlocal resume_calls
                resume_calls += 1
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                )

            resumed_executor = production.make_entries_executor(
                holder.config,
                database_info_fn=lambda: database,
                run_query_fn=fail_resume,
            )
            with self.assertRaises(AnalyzerError) as resumed_failure:
                Pipeline(
                    output,
                    {"entries": resumed_executor},
                    implementation_versions={
                        "entries": "generation-binding-test"
                    },
                    resume=True,
                ).run("entries")
            self.assertEqual(
                resumed_failure.exception.code, "CODEQL_QUERY_FAILED"
            )
            self.assertEqual(resume_calls, 1)
            self.assertEqual(
                json.loads(
                    (output / "run.json").read_text(encoding="utf-8")
                )["status"],
                "failed",
            )

    def test_generation_fd_pre_action_release_failure_closes_workspace_chain(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            pipeline = build_production_pipeline(
                {**self._values(root), "command": "entries"},
                environ={},
            )
            database = DatabaseInfo(root / "database", root, "d" * 64)
            injected = False
            released_paths: list[str] = []
            real_close_once = filesystem.close_fd_once

            def successful_runner(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **_kwargs: object,
            ) -> QueryResult:
                generations = output_dir / ".generations"
                generations.mkdir(mode=0o700)
                (generations / "Growth-normal").mkdir(mode=0o700)
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text("{}", encoding="utf-8")
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            def fail_generation_release(
                descriptor: int,
                capability: filesystem.CloseRangeCapability,
            ) -> None:
                nonlocal injected
                try:
                    path = os.readlink(f"/proc/self/fd/{descriptor}")
                except OSError:
                    path = "<closed>"
                released_paths.append(path)
                if not injected and path.endswith("/.generations"):
                    injected = True
                    raise filesystem.CloseRangePreActionError(
                        errno.EIO,
                        os.strerror(errno.EIO),
                    )
                real_close_once(descriptor, capability)

            baseline_fds = len(os.listdir("/proc/self/fd"))
            with mock.patch.object(
                production,
                "_query_files",
                return_value=(root / "Growth.ql",),
            ), mock.patch.object(
                production,
                "decode_bqrs_json",
                return_value=[],
            ) as decode, mock.patch.object(
                filesystem,
                "close_fd_once",
                side_effect=fail_generation_release,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    production._run_codeql_family(
                        pipeline.config,
                        database,
                        "growth",
                        root / "pack",
                        successful_runner,
                    )

            self.assertTrue(injected)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertNotIn(str(root), json.dumps(raised.exception.details))
            decode.assert_called_once()
            self.assertTrue(
                any(path.endswith("/.generations") for path in released_paths)
            )
            self.assertTrue(
                any(path.endswith("/results") for path in released_paths)
            )
            self.assertTrue(
                any(
                    ".dosweb-growth-quarantine-" in path
                    for path in released_paths
                )
            )
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_result_fd_post_action_exception_is_not_retried_and_closes_chain(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir(mode=0o700)
            pipeline = build_production_pipeline(
                {**self._values(root), "command": "entries"},
                environ={},
            )
            database = DatabaseInfo(root / "database", root, "d" * 64)
            injected_fd = -1
            close_attempts: list[int] = []
            fallback_ranges: list[tuple[int, int]] = []
            real_close_fd_once = filesystem.close_fd_once
            real_closerange = os.closerange

            def successful_runner(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **_kwargs: object,
            ) -> QueryResult:
                generations = output_dir / ".generations"
                generations.mkdir(mode=0o700)
                (generations / "Growth-normal").mkdir(mode=0o700)
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text("{}", encoding="utf-8")
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            def close_result_then_raise(
                descriptor: int,
                capability: filesystem.CloseRangeCapability,
            ) -> None:
                nonlocal injected_fd
                close_attempts.append(descriptor)
                try:
                    path = os.readlink(f"/proc/self/fd/{descriptor}")
                except OSError:
                    path = "<closed>"
                if injected_fd < 0 and path.endswith("/results"):
                    injected_fd = descriptor
                    real_closerange(descriptor, descriptor + 1)
                    raise OSError("actual close then exception")
                real_close_fd_once(descriptor, capability)

            def record_closerange(first: int, last: int) -> None:
                fallback_ranges.append((first, last))
                real_closerange(first, last)

            baseline_fds = len(os.listdir("/proc/self/fd"))
            with mock.patch.object(
                production,
                "_query_files",
                return_value=(root / "Growth.ql",),
            ), mock.patch.object(
                production,
                "decode_bqrs_json",
                return_value=[],
            ), mock.patch.object(
                filesystem,
                "close_fd_once",
                side_effect=close_result_then_raise,
            ), mock.patch.object(
                production.os,
                "closerange",
                side_effect=record_closerange,
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    production._run_codeql_family(
                        pipeline.config,
                        database,
                        "growth",
                        root / "pack",
                        successful_runner,
                    )

            self.assertGreaterEqual(injected_fd, 0)
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertNotIn(str(root), json.dumps(raised.exception.details))
            self.assertEqual(close_attempts.count(injected_fd), 1)
            self.assertNotIn(
                (injected_fd, injected_fd + 1), fallback_ranges
            )
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_entries_final_generation_scan_swap_fails_and_preserves_roots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependency>org.springframework</dependency></project>",
                encoding="utf-8",
            )
            info = DatabaseInfo(database, source, "d" * 64)
            held: dict[str, object] = {}
            injected = False

            def fake_validate(
                _path: Path,
                **_kwargs: object,
            ) -> DatabaseInfo:
                return info

            def fake_run(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                if not held:
                    descriptor = kwargs.get("output_descriptor")
                    stable_results = (
                        Path(os.readlink(f"/proc/self/fd/{descriptor}"))
                        if isinstance(descriptor, int)
                        else output_dir
                    )
                    generations = output_dir / ".generations"
                    competitor = output_dir / ".generations-competitor"
                    generations.mkdir(mode=0o700)
                    competitor.mkdir(mode=0o700)
                    normal = generations / "Entries-normal"
                    normal.mkdir(mode=0o700)
                    (normal / "original-marker").write_text(
                        "original-marker", encoding="utf-8"
                    )
                    (competitor / "competitor-marker").write_text(
                        "competitor-marker", encoding="utf-8"
                    )
                    original_fd = os.open(
                        generations,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    competitor_fd = os.open(
                        competitor,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    held.update(
                        results=stable_results,
                        generations=stable_results / ".generations",
                        competitor=stable_results / ".generations-competitor",
                        original_fd=original_fd,
                        competitor_fd=competitor_fd,
                        original_info=os.fstat(original_fd),
                        competitor_info=os.fstat(competitor_fd),
                    )
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(
                    json.dumps(self._payload_for_query(query)),
                    encoding="utf-8",
                )
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            real_scandir = production.os.scandir

            def exchange_at_fd_scan(path: object):
                nonlocal injected
                if isinstance(path, int) and not injected:
                    try:
                        opened = Path(os.readlink(f"/proc/self/fd/{path}"))
                    except OSError:
                        opened = Path("/")
                    generations = held.get("generations")
                    if isinstance(generations, Path) and opened == generations:
                        results = held["results"]
                        assert isinstance(results, Path)
                        parent = os.open(
                            results,
                            os.O_RDONLY | os.O_DIRECTORY,
                        )
                        try:
                            filesystem.renameat2_exchange(
                                parent,
                                ".generations",
                                parent,
                                ".generations-competitor",
                            )
                        finally:
                            os.close(parent)
                        injected = True
                return real_scandir(path)

            values = self._values(root)
            values.update(
                command="entries",
                source_checkout=source,
                analysis_source_root=source,
            )
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    production.os,
                    "scandir",
                    side_effect=exchange_at_fd_scan,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        pipeline.run("entries")

                self.assertTrue(injected)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                results = held["results"]
                original_fd = held["original_fd"]
                competitor_fd = held["competitor_fd"]
                original_info = held["original_info"]
                competitor_info = held["competitor_info"]
                assert isinstance(results, Path)
                assert isinstance(original_fd, int)
                assert isinstance(competitor_fd, int)
                assert isinstance(original_info, os.stat_result)
                assert isinstance(competitor_info, os.stat_result)
                original_after = results / ".generations-competitor"
                competitor_after = results / ".generations"
                for path, descriptor, expected in (
                    (original_after, original_fd, original_info),
                    (competitor_after, competitor_fd, competitor_info),
                ):
                    current = path.stat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino, current.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                self.assertTrue(
                    (
                        original_after
                        / "Entries-normal"
                        / "original-marker"
                    ).is_file()
                )
                self.assertTrue(
                    (competitor_after / "competitor-marker").is_file()
                )
                run = json.loads(
                    (root / "output" / "run.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(run["status"], "failed")
                self.assertFalse((root / "output" / "entries.jsonl").exists())
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 2
                )
            finally:
                for key in ("competitor_fd", "original_fd"):
                    descriptor = held.get(key)
                    if isinstance(descriptor, int):
                        os.close(descriptor)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

            resume_calls = 0

            def fail_resume(
                *_args: object,
                **_kwargs: object,
            ) -> QueryResult:
                nonlocal resume_calls
                resume_calls += 1
                raise AnalyzerError(
                    "CODEQL_QUERY_FAILED",
                    "CodeQL query execution failed.",
                )

            resumed = build_production_pipeline(
                {**values, "resume": True},
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fail_resume,
            )
            with self.assertRaises(AnalyzerError):
                resumed.run("entries")
            self.assertEqual(resume_calls, 1)
            self.assertTrue(
                (
                    held["results"]
                    / ".generations-competitor"
                    / "Entries-normal"
                    / "original-marker"
                ).is_file()
            )
            self.assertTrue(
                (
                    held["results"]
                    / ".generations"
                    / "competitor-marker"
                ).is_file()
            )

    def test_family_workspace_name_swap_before_isolation_preserves_inodes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            pipeline = build_production_pipeline(
                {**self._values(root), "command": "entries"},
                environ={},
            )
            database = DatabaseInfo(root / "database", root, "d" * 64)
            competitor_name = ".workspace-competitor"
            competitor = output / competitor_name
            competitor.mkdir(mode=0o700)
            (competitor / "competitor-marker").write_text(
                "competitor-marker", encoding="utf-8"
            )
            competitor_fd = os.open(
                competitor,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            competitor_info = os.fstat(competitor_fd)
            held: dict[str, object] = {}
            isolated_name: str | None = None
            injected = False

            def successful_runner(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **kwargs: object,
            ) -> QueryResult:
                descriptor = kwargs.get("output_descriptor")
                stable_results = (
                    Path(os.readlink(f"/proc/self/fd/{descriptor}"))
                    if isinstance(descriptor, int)
                    else output_dir
                )
                workspace = stable_results.parent
                if not held:
                    (workspace / "original-marker").write_text(
                        "original-marker", encoding="utf-8"
                    )
                    workspace_fd = os.open(
                        workspace,
                        os.O_RDONLY | os.O_DIRECTORY,
                    )
                    held.update(
                        workspace=workspace,
                        workspace_fd=workspace_fd,
                        workspace_info=os.fstat(workspace_fd),
                    )
                    generations = output_dir / ".generations"
                    generations.mkdir(mode=0o700)
                    (generations / "Entries-normal").mkdir(mode=0o700)
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text("{}", encoding="utf-8")
                return QueryResult(
                    query.name,
                    query,
                    query,
                    decoded,
                    "a" * 64,
                    "b" * 64,
                )

            real_no_replace = filesystem.renameat2_no_replace

            def exchange_workspace_before_isolation(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal injected, isolated_name
                workspace = held.get("workspace")
                if (
                    isinstance(workspace, Path)
                    and source_name == workspace.name
                    and not injected
                ):
                    filesystem.renameat2_exchange(
                        source_directory_fd,
                        source_name,
                        source_directory_fd,
                        competitor_name,
                    )
                    injected = True
                    isolated_name = destination_name
                real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            baseline_fds = len(os.listdir("/proc/self/fd"))
            try:
                with mock.patch.object(
                    production,
                    "_query_files",
                    return_value=(root / "Growth.ql",),
                ), mock.patch.object(
                    production,
                    "decode_bqrs_json",
                    return_value=[],
                ), mock.patch.object(
                    production,
                    "renameat2_no_replace",
                    side_effect=exchange_workspace_before_isolation,
                    create=True,
                ):
                    with self.assertRaises(AnalyzerError) as raised:
                        production._run_codeql_family(
                            pipeline.config,
                            database,
                            "growth",
                            root / "pack",
                            successful_runner,
                        )

                self.assertTrue(injected)
                self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
                self.assertIsNotNone(isolated_name)
                assert isolated_name is not None
                workspace_fd = held["workspace_fd"]
                workspace_info = held["workspace_info"]
                assert isinstance(workspace_fd, int)
                assert isinstance(workspace_info, os.stat_result)
                expected_after = output / competitor_name
                competitor_after = output / isolated_name
                for path, descriptor, expected in (
                    (expected_after, workspace_fd, workspace_info),
                    (competitor_after, competitor_fd, competitor_info),
                ):
                    current = path.stat()
                    opened = os.fstat(descriptor)
                    self.assertEqual(
                        (current.st_dev, current.st_ino, current.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                    self.assertEqual(
                        (opened.st_dev, opened.st_ino, opened.st_nlink),
                        (expected.st_dev, expected.st_ino, expected.st_nlink),
                    )
                self.assertTrue((expected_after / "original-marker").is_file())
                self.assertTrue(
                    (competitor_after / "competitor-marker").is_file()
                )
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")), baseline_fds + 1
                )
            finally:
                workspace_fd = held.get("workspace_fd")
                if isinstance(workspace_fd, int):
                    os.close(workspace_fd)
                os.close(competitor_fd)
            self.assertEqual(
                len(os.listdir("/proc/self/fd")),
                baseline_fds - 1,
            )

    def test_preflight_factory_return_interrupt_cleans_registered_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            (database / "db-java").mkdir(parents=True)
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependency>org.springframework</dependency></project>",
                encoding="utf-8",
            )
            (database / "codeql-database.yml").write_text(
                f"primaryLanguage: java\nsourceLocationPrefix: {source}\n",
                encoding="utf-8",
            )
            (database / "db-java" / "database-relations.json").write_text(
                '{"relations":[]}', encoding="utf-8"
            )
            snapshots: list[DatabaseInfo] = []
            cleanup_calls = 0

            def clone_tree(source_path: Path, destination: Path) -> None:
                import shutil

                shutil.copytree(
                    source_path,
                    destination,
                    dirs_exist_ok=True,
                )
                destination.chmod(0o700)

            def create_snapshot(
                info: DatabaseInfo,
                output: Path,
                *,
                validate_database_fn,
                owner_callback,
            ) -> DatabaseInfo:
                def capture_owner(candidate: DatabaseInfo) -> None:
                    snapshots.append(candidate)
                    owner_callback(candidate)

                return codeql_database.create_execution_database_snapshot(
                    info,
                    output,
                    clone_tree=clone_tree,
                    validate_database_fn=validate_database_fn,
                    owner_callback=capture_owner,
                )

            def cleanup_snapshot(info: DatabaseInfo) -> None:
                nonlocal cleanup_calls
                cleanup_calls += 1
                codeql_database.cleanup_execution_database_snapshot(info)

            return_offsets = {
                instruction.offset
                for instruction in dis.get_instructions(
                    codeql_database.create_execution_database_snapshot
                )
                if instruction.opname == "RETURN_VALUE"
            }
            injected = False

            def interrupt_on_factory_return(frame, event, _arg):
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
                    raise KeyboardInterrupt(
                        "registered factory return opcode interrupted"
                    )
                return interrupt_on_factory_return

            values = self._values(root)
            values.update(
                command="entries",
                database=database,
                source_checkout=source,
                analysis_source_root=source,
            )
            pipeline = build_production_pipeline(
                values,
                environ={},
                create_execution_snapshot_fn=create_snapshot,
                cleanup_execution_snapshot_fn=cleanup_snapshot,
            )
            try:
                sys.settrace(interrupt_on_factory_return)
                with self.assertRaises(KeyboardInterrupt):
                    pipeline.run("entries")
            finally:
                sys.settrace(None)

            self.assertTrue(injected)
            self.assertEqual(len(snapshots), 1)
            snapshot = snapshots[0]
            assert snapshot.execution is not None
            private_marker = str(snapshot.execution.path)
            try:
                self.assertEqual(cleanup_calls, 2)
                self.assertFalse(snapshot.execution.path.exists())
                with self.assertRaises(OSError):
                    os.fstat(snapshot.execution.parent_descriptor)
                persisted_text = (
                    root / "output" / "run.json"
                ).read_text(encoding="utf-8")
                self.assertNotIn(private_marker, persisted_text)
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
            finally:
                if not snapshot.execution.cleanup_state.closed:
                    codeql_database.cleanup_execution_database_snapshot(
                        snapshot
                    )

    def test_finalizer_cleanup_call_entry_or_first_line_uses_lexical_retry(
        self,
    ) -> None:
        for instrumentation in ("profile_call", "trace_first_line"):
            with self.subTest(
                instrumentation=instrumentation
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                database = root / "database"
                source = root / "source"
                (database / "db-java").mkdir(parents=True)
                source.mkdir()
                (database / "codeql-database.yml").write_text(
                    f"primaryLanguage: java\nsourceLocationPrefix: {source}\n",
                    encoding="utf-8",
                )
                (
                    database
                    / "db-java"
                    / "database-relations.json"
                ).write_text('{"relations":[]}', encoding="utf-8")
                snapshots: list[DatabaseInfo] = []
                cleanup_body_calls = 0
                injected = False

                def clone_tree(
                    source_path: Path,
                    destination: Path,
                ) -> None:
                    import shutil

                    shutil.copytree(
                        source_path,
                        destination,
                        dirs_exist_ok=True,
                    )
                    destination.chmod(0o700)

                def create_snapshot(
                    info: DatabaseInfo,
                    output: Path,
                    *,
                    validate_database_fn,
                    owner_callback,
                ) -> DatabaseInfo:
                    def capture_owner(candidate: DatabaseInfo) -> None:
                        snapshots.append(candidate)
                        owner_callback(candidate)

                    return codeql_database.create_execution_database_snapshot(
                        info,
                        output,
                        clone_tree=clone_tree,
                        validate_database_fn=validate_database_fn,
                        owner_callback=capture_owner,
                    )

                def cleanup_snapshot(info: DatabaseInfo) -> None:
                    nonlocal cleanup_body_calls
                    cleanup_body_calls += 1
                    codeql_database.cleanup_execution_database_snapshot(info)

                def interrupt_cleanup(frame, event, _arg):
                    nonlocal injected
                    expected_event = (
                        "call"
                        if instrumentation == "profile_call"
                        else "line"
                    )
                    if (
                        not injected
                        and event == expected_event
                        and frame.f_code is cleanup_snapshot.__code__
                    ):
                        injected = True
                        raise KeyboardInterrupt(
                            f"finalizer cleanup {instrumentation} interrupted"
                        )
                    return interrupt_cleanup

                values = self._values(root)
                values.update(
                    command="entries",
                    database=database,
                    source_checkout=source,
                    analysis_source_root=source,
                )
                pipeline = build_production_pipeline(
                    values,
                    environ={},
                    create_execution_snapshot_fn=create_snapshot,
                    cleanup_execution_snapshot_fn=cleanup_snapshot,
                )
                internal = pipeline._pipeline  # noqa: SLF001
                assert internal.preflight is not None
                assert internal.finalizer is not None
                baseline_fds = len(os.listdir("/proc/self/fd"))
                internal.preflight()
                self.assertEqual(len(snapshots), 1)
                snapshot = snapshots[0]
                assert snapshot.execution is not None
                try:
                    if instrumentation == "profile_call":
                        sys.setprofile(interrupt_cleanup)
                    else:
                        sys.settrace(interrupt_cleanup)
                    try:
                        with self.assertRaises(KeyboardInterrupt):
                            internal.finalizer()
                    finally:
                        sys.setprofile(None)
                        sys.settrace(None)

                    self.assertTrue(injected)
                    self.assertEqual(cleanup_body_calls, 1)
                    self.assertTrue(snapshot.execution.cleanup_state.closed)
                    self.assertFalse(snapshot.execution.path.exists())
                    with self.assertRaises(OSError):
                        os.fstat(snapshot.execution.parent_descriptor)
                    self.assertEqual(
                        len(os.listdir("/proc/self/fd")), baseline_fds
                    )
                    internal.finalizer()
                    self.assertEqual(cleanup_body_calls, 1)
                finally:
                    sys.setprofile(None)
                    sys.settrace(None)
                    if not snapshot.execution.cleanup_state.closed:
                        codeql_database.cleanup_execution_database_snapshot(
                            snapshot
                        )

    def test_production_path_bound_framework_limit_is_effective_only_for_exact_domain(self) -> None:
        from tests.test_lifecycle_bounds import BoundEvaluationTests

        helper = BoundEvaluationTests()
        helper.setUp()
        entry, flow = helper._framework_path("spring_mvc")  # noqa: SLF001
        candidate = helper._candidate(  # noqa: SLF001
            kind="limit",
            configuration_key="literal",
            configuration_value="1024",
            phase="before_growth",
            request_encoding="multipart",
            evidence=("servlet_multipart_config_literal",),
        )

        effective = production._evaluate_path_bounds(  # noqa: SLF001
            entry,
            helper.growth,
            flow,
            (candidate,),
            ModeledConfiguration(()),
            coverage_status="complete",
        )
        mismatch = production._evaluate_path_bounds(  # noqa: SLF001
            entry,
            helper.growth,
            flow,
            (helper._candidate(  # noqa: SLF001
                kind="limit",
                configuration_key="literal",
                configuration_value="1024",
                phase="before_growth",
                request_encoding="json",
                evidence=("servlet_multipart_config_literal",),
            ),),
            ModeledConfiguration(()),
            coverage_status="complete",
        )

        self.assertEqual("effective", effective.status)
        self.assertNotEqual("effective", mismatch.status)
        self.assertIn("BOUND_REQUEST_ENCODING_MISMATCH", mismatch.reason_codes)

    def test_flow_stage_does_not_cross_product_missing_rows_from_candidate_links(self) -> None:
        handler = HandlerFact("fixture.Alias.handle", "src/Alias.java", 20)
        registration = RegistrationFact(
            "annotation_mapping", "fixture.Alias.handle", "src/Alias.java", 18
        )
        first = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=handler,
            registration=registration,
            registration_pattern_id="entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
            route_or_event="POST /items",
            auth_context="unauthenticated",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )
        alias = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=handler,
            registration=registration,
            registration_pattern_id="entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
            route_or_event="POST /items-alias",
            auth_context="unauthenticated",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )
        unrelated = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact("fixture.Other.handle", "src/Other.java", 40),
            registration=RegistrationFact(
                "annotation_mapping", "fixture.Other.handle", "src/Other.java", 38
            ),
            registration_pattern_id="entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
            route_or_event="POST /other",
            auth_context="unauthenticated",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/Alias.java", 24),
            kind="input_materialization",
            operation="spring_request_body_materialization",
            resource_dimension="bytes",
            receiver="fixture.Alias.body",
            field_path="body",
            demand_inputs=(DemandInput("body", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_notes=("recognized_spring_request_body_bytes",),
        )
        growth = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:fixture",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        canonical = min((first, alias), key=lambda entry: entry.entry_id)
        link = CandidateEntryLink.create(
            candidate.growth_id,
            canonical.entry_id,
            "complete",
            (candidate.growth_id, canonical.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        disposition = CandidateDisposition.create(
            candidate.growth_id,
            "formal_eligible",
            canonical_entry_id=canonical.entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=(candidate.growth_id, link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )
        raw_flow = {
            "source_file": "src/Alias.java",
            "source_start_line": 20,
            "sink_file": "src/Alias.java",
            "sink_start_line": 24,
            "attacker_target": "size",
            "attacker_source": "body",
            "attacker_sink": "body",
            "call_path": "fixture.Alias.handle",
            "phase_sequence": "entry>global_dataflow>growth",
            "flow_kind": "data_flow",
            "confidence": "proven",
            "coverage_status": "complete",
            "coverage_note": "same_handler_global_dataflow",
        }
        entries = {entry.entry_id: entry for entry in (first, alias, unrelated)}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            database.mkdir()
            context = StageContext(
                "flows",
                root,
                StageFingerprint.for_stage("flows"),
                {},
                {},
            )
            def strict_records(
                _context: StageContext,
                _stage: str,
                artifact: str,
            ) -> list[dict[str, object]]:
                if artifact == "candidate_entry_links.jsonl":
                    return [link.to_dict()]
                if artifact == "candidate_dispositions.jsonl":
                    return [disposition.to_dict()]
                raise AssertionError(artifact)

            with (
                mock.patch.object(production, "_materialize_query_pack", return_value=root),
                mock.patch.object(production, "_run_codeql_family", return_value=[raw_flow]),
                mock.patch.object(production, "_load_entries", return_value=entries),
                mock.patch.object(
                    production,
                    "_load_verified_growth",
                    return_value={growth.growth_id: growth},
                ),
                mock.patch.object(
                    production,
                    "_strict_records",
                    side_effect=strict_records,
                ),
            ):
                output = production.make_flows_executor(
                    SimpleNamespace(codeql_binary="codeql"),
                    database_info_fn=lambda: DatabaseInfo(database, root, "d" * 64),
                    query_pack_snapshot_fn=lambda: {},
                )(context)

        proofs = output.artifacts["flow_proofs.jsonl"]
        self.assertEqual(len(proofs), 1)
        self.assertEqual(proofs[0]["entry_id"], canonical.entry_id)
        self.assertEqual(proofs[0]["confidence"], "proven")

    def test_flow_executor_reconciles_rows_to_authenticated_canonical_links(self) -> None:
        base, beat, trigger = self._netty_route_alias_entries()
        entries = {entry.entry_id: entry for entry in (base, beat, trigger)}
        candidate = GrowthCandidate.create(
            site=SourceLocation("fixture/netty/NettyFixture.java", 76),
            kind="input_materialization",
            operation="netty_full_http_request_string_materialization",
            resource_dimension="bytes",
            receiver="content(...)",
            field_path="request",
            demand_inputs=(DemandInput("request", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_notes=(
                "recognized_netty_full_http_request_string_materialization",
            ),
        )
        growth = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:netty-canonical-flow",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        raw_flow = {
            "source_file": base.handler.file,
            "source_start_line": base.handler.start_line,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
            "attacker_target": "size",
            "attacker_source": "request",
            "attacker_sink": "request",
            "call_path": base.handler.callable,
            "phase_sequence": "entry>global_dataflow>growth",
            "flow_kind": "data_flow",
            "confidence": "proven",
            "coverage_status": "complete",
            "coverage_note": "same_handler_global_dataflow",
        }

        cases = (
            ("handler-base", base, "complete", "formal_eligible", raw_flow),
            (
                "route-qualified",
                trigger,
                "partial",
                "gap_eligible",
                {
                    **raw_flow,
                    "call_path": (
                        "fixture.netty.FullRequestHandler.channelRead0[/trigger]>"
                        "fixture.netty.TriggerServiceImpl.trigger"
                    ),
                    "phase_sequence": "entry>netty_json_switch>service>growth",
                    "confidence": "partial",
                    "coverage_status": "partial",
                    "coverage_note": "netty_json_switch_route_path_partial",
                },
            ),
        )
        for case, canonical, link_status, disposition_status, row in cases:
            with self.subTest(case=case):
                link = CandidateEntryLink.create(
                    candidate.growth_id,
                    canonical.entry_id,
                    link_status,  # type: ignore[arg-type]
                    (candidate.growth_id, canonical.entry_id),
                    ("ASSOCIATION_QUERY_EVIDENCE",),
                )
                disposition = CandidateDisposition.create(
                    candidate.growth_id,
                    disposition_status,  # type: ignore[arg-type]
                    canonical_entry_id=canonical.entry_id,
                    local_growth_status="complete",
                    association_status=link_status,  # type: ignore[arg-type]
                    link_ids=(link.link_id,),
                    evidence_ids=(candidate.growth_id, link.link_id),
                    negative_proof_ids=(),
                    reason_codes=("MATURATION_CANONICAL_FLOW_FIXTURE",),
                )
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    database = root / "database"
                    database.mkdir()
                    context = StageContext(
                        "flows",
                        root,
                        StageFingerprint.for_stage("flows"),
                        {},
                        {},
                    )

                    def strict_records(
                        _context: StageContext,
                        _stage: str,
                        artifact: str,
                    ) -> list[dict[str, object]]:
                        if artifact == "candidate_entry_links.jsonl":
                            return [link.to_dict()]
                        if artifact == "candidate_dispositions.jsonl":
                            return [disposition.to_dict()]
                        raise AssertionError(artifact)

                    with (
                        mock.patch.object(
                            production, "_materialize_query_pack", return_value=root
                        ),
                        mock.patch.object(
                            production, "_run_codeql_family", return_value=[row]
                        ),
                        mock.patch.object(
                            production, "_load_entries", return_value=entries
                        ),
                        mock.patch.object(
                            production,
                            "_load_verified_growth",
                            return_value={growth.growth_id: growth},
                        ),
                        mock.patch.object(
                            production,
                            "_strict_records",
                            side_effect=strict_records,
                        ),
                    ):
                        output = production.make_flows_executor(
                            SimpleNamespace(codeql_binary="codeql"),
                            database_info_fn=lambda: DatabaseInfo(
                                database, root, "d" * 64
                            ),
                            query_pack_snapshot_fn=lambda: {},
                        )(context)

                proofs = output.artifacts["flow_proofs.jsonl"]
                self.assertEqual(len(proofs), 1, proofs)
                self.assertEqual(proofs[0]["entry_id"], canonical.entry_id)
                self.assertEqual(proofs[0]["growth_id"], candidate.growth_id)
                self.assertEqual(proofs[0]["confidence"], row["confidence"])

    def test_flow_executor_rejects_canonical_disposition_link_identity_mismatch(self) -> None:
        base, _beat, trigger = self._netty_route_alias_entries()
        entries = {entry.entry_id: entry for entry in (base, trigger)}
        candidate = GrowthCandidate.create(
            site=SourceLocation("fixture/netty/NettyFixture.java", 76),
            kind="input_materialization",
            operation="netty_full_http_request_string_materialization",
            resource_dimension="bytes",
            receiver="content(...)",
            field_path="request",
            demand_inputs=(DemandInput("request", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_notes=("recognized_netty_materialization",),
        )
        growth = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:netty-corrupt-link",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        link = CandidateEntryLink.create(
            candidate.growth_id,
            base.entry_id,
            "complete",
            (candidate.growth_id, base.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        disposition = CandidateDisposition.create(
            candidate.growth_id,
            "formal_eligible",
            canonical_entry_id=trigger.entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=(candidate.growth_id, link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )
        raw_flow = {
            "source_file": base.handler.file,
            "source_start_line": base.handler.start_line,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
            "attacker_target": "size",
            "attacker_source": "request",
            "attacker_sink": "request",
            "call_path": base.handler.callable,
            "phase_sequence": "entry>global_dataflow>growth",
            "flow_kind": "data_flow",
            "confidence": "proven",
            "coverage_status": "complete",
            "coverage_note": "same_handler_global_dataflow",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            database.mkdir()
            context = StageContext(
                "flows", root, StageFingerprint.for_stage("flows"), {}, {}
            )

            def strict_records(
                _context: StageContext,
                _stage: str,
                artifact: str,
            ) -> list[dict[str, object]]:
                if artifact == "candidate_entry_links.jsonl":
                    return [link.to_dict()]
                if artifact == "candidate_dispositions.jsonl":
                    return [disposition.to_dict()]
                raise AssertionError(artifact)

            with (
                mock.patch.object(
                    production, "_materialize_query_pack", return_value=root
                ),
                mock.patch.object(
                    production, "_run_codeql_family", return_value=[raw_flow]
                ),
                mock.patch.object(production, "_load_entries", return_value=entries),
                mock.patch.object(
                    production,
                    "_load_verified_growth",
                    return_value={growth.growth_id: growth},
                ),
                mock.patch.object(
                    production, "_strict_records", side_effect=strict_records
                ),
            ):
                with self.assertRaises(AnalyzerError) as raised:
                    production.make_flows_executor(
                        SimpleNamespace(codeql_binary="codeql"),
                        database_info_fn=lambda: DatabaseInfo(
                            database, root, "d" * 64
                        ),
                        query_pack_snapshot_fn=lambda: {},
                    )(context)

        self.assertEqual(raised.exception.code, "ANALYSIS_DANGLING_FACT_REFERENCE")

    def test_flow_reconciliation_rejects_nonretained_inventory_link_status_mismatch(self) -> None:
        base, _beat, _trigger = self._netty_route_alias_entries()
        candidate = GrowthCandidate.create(
            site=SourceLocation("fixture/netty/NettyFixture.java", 76),
            kind="input_materialization",
            operation="netty_full_http_request_string_materialization",
            resource_dimension="bytes",
            receiver="content(...)",
            field_path="request",
            demand_inputs=(DemandInput("request", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_notes=("recognized_netty_materialization",),
        )
        link = CandidateEntryLink.create(
            candidate.growth_id,
            base.entry_id,
            "complete",
            (candidate.growth_id, base.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        disposition = CandidateDisposition.create(
            candidate.growth_id,
            "inventory_unresolved",
            canonical_entry_id=base.entry_id,
            local_growth_status="complete",
            association_status="partial",
            link_ids=(link.link_id,),
            evidence_ids=(candidate.growth_id, link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_INVENTORY_UNRESOLVED",),
        )

        with self.assertRaises(AnalyzerError) as raised:
            production._canonical_flow_entry_ids(  # noqa: SLF001
                {base.entry_id: base},
                {},
                (link.to_dict(),),
                (disposition.to_dict(),),
            )

        self.assertEqual(raised.exception.code, "ANALYSIS_DANGLING_FACT_REFERENCE")

    def test_flow_reconciliation_rejects_unknown_formal_or_gap_growth(self) -> None:
        base, _beat, _trigger = self._netty_route_alias_entries()
        candidate = GrowthCandidate.create(
            site=SourceLocation("fixture/netty/NettyFixture.java", 76),
            kind="input_materialization",
            operation="netty_full_http_request_string_materialization",
            resource_dimension="bytes",
            receiver="content(...)",
            field_path="request",
            demand_inputs=(DemandInput("request", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_notes=("recognized_netty_materialization",),
        )
        for status, local_status, link_status in (
            ("formal_eligible", "complete", "complete"),
            ("gap_eligible", "partial", "complete"),
        ):
            with self.subTest(status=status):
                link = CandidateEntryLink.create(
                    candidate.growth_id,
                    base.entry_id,
                    link_status,  # type: ignore[arg-type]
                    (candidate.growth_id, base.entry_id),
                    ("ASSOCIATION_QUERY_EVIDENCE",),
                )
                disposition = CandidateDisposition.create(
                    candidate.growth_id,
                    status,  # type: ignore[arg-type]
                    canonical_entry_id=base.entry_id,
                    local_growth_status=local_status,  # type: ignore[arg-type]
                    association_status=link_status,  # type: ignore[arg-type]
                    link_ids=(link.link_id,),
                    evidence_ids=(candidate.growth_id, link.link_id),
                    negative_proof_ids=(),
                    reason_codes=("MATURATION_ELIGIBLE_UNKNOWN_GROWTH",),
                )

                with self.assertRaises(AnalyzerError) as raised:
                    production._canonical_flow_entry_ids(  # noqa: SLF001
                        {base.entry_id: base},
                        {},
                        (link.to_dict(),),
                        (disposition.to_dict(),),
                    )

                self.assertEqual(
                    raised.exception.code,
                    "ANALYSIS_DANGLING_FACT_REFERENCE",
                )

    def test_candidate_relevant_partial_link_gets_one_explicit_gap_flow(self) -> None:
        entry = EntryFact.create(
            framework="servlet",
            protocol="http",
            handler=HandlerFact("fixture.Upload.doPost", "src/Upload.java", 20),
            registration=RegistrationFact(
                "annotation_mapping", "fixture.Upload", "src/Upload.java", 18
            ),
            registration_pattern_id="entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
            route_or_event="POST /upload",
            auth_context="unauthenticated",
            attacker_inputs=(
                AttackerInputFact("request", "HttpServletRequest", "stream"),
            ),
            materialization_phase="in_handler",
        )
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/Upload.java", 29),
            kind="container_growth",
            operation="java.util.Map.put",
            resource_dimension="entries",
            receiver="fixture.Upload.registry",
            field_path="registry",
            demand_inputs=(DemandInput("valueOf(...)", "key"),),
            escape_scope="instance",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_status="partial",
            coverage_notes=("field_retention_partial",),
        )
        growth = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:partial",
            status="unresolved",
            reason_codes=("GROWTH_DOS_RELEVANT_PARTIAL",),
            checks=(
                VerificationCheck(
                    "candidate_relevance_and_entry_association",
                    False,
                    "GROWTH_DOS_RELEVANT_PARTIAL",
                ),
            ),
        )
        link = CandidateEntryLink.create(
            candidate.growth_id,
            entry.entry_id,
            "partial",
            (candidate.growth_id, entry.entry_id),
            ("ASSOCIATION_LEGACY_SOURCE_ORDER_PARTIAL", "FLOW_CODEQL_ROW_MISSING"),
        )
        disposition = CandidateDisposition.create(
            candidate.growth_id,
            "gap_eligible",
            canonical_entry_id=entry.entry_id,
            local_growth_status="partial",
            association_status="partial",
            link_ids=(link.link_id,),
            evidence_ids=("fact:growth", link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_GAP_ELIGIBLE",),
        )

        rows = production._candidate_relevant_partial_flow_rows(  # noqa: SLF001
            {entry.entry_id: entry},
            {candidate.growth_id: growth},
            (link.to_dict(),),
            (disposition.to_dict(),),
            set(),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["attacker_source"], "request")
        self.assertEqual(rows[0]["attacker_sink"], "valueOf(...)")
        self.assertEqual(rows[0]["attacker_target"], "key")
        self.assertEqual(rows[0]["flow_kind"], "unmodeled")
        self.assertEqual(rows[0]["confidence"], "partial")
        self.assertEqual(rows[0]["coverage_status"], "partial")
        proofs = production.normalize_flow_rows(  # noqa: SLF001
            rows,
            {entry.entry_id: entry},
            {candidate.growth_id: growth},
        )
        self.assertEqual(len(proofs), 1)
        self.assertEqual(proofs[0]["entry_id"], entry.entry_id)
        self.assertEqual(proofs[0]["growth_id"], candidate.growth_id)

        generic = CandidateDisposition.create(
            candidate.growth_id,
            "inventory_unresolved",
            canonical_entry_id="",
            local_growth_status="unknown",
            association_status="ambiguous",
            link_ids=(link.link_id,),
            evidence_ids=("fact:growth", link.link_id),
            negative_proof_ids=(),
            reason_codes=("ASSOCIATION_CALL_GRAPH_UNAVAILABLE",),
        )
        self.assertEqual(
            production._candidate_relevant_partial_flow_rows(  # noqa: SLF001
                {entry.entry_id: entry},
                {candidate.growth_id: growth},
                (link.to_dict(),),
                (generic.to_dict(),),
                set(),
            ),
            [],
        )
        self.assertEqual(
            production._candidate_relevant_partial_flow_rows(  # noqa: SLF001
                {entry.entry_id: entry},
                {candidate.growth_id: growth},
                (link.to_dict(),),
                (disposition.to_dict(),),
                {(entry.entry_id, candidate.growth_id)},
            ),
            [],
        )

    def _fake_executors(self, calls: list[str], secret: str = "", *, fail: bool = False):
        def execute(context: StageContext) -> StageOutput:
            calls.append(context.stage)
            if fail:
                raise RuntimeError(secret)
            # A production executor must not copy credentials into durable output.
            return StageOutput(
                {f"{context.stage}.jsonl": [{"stage": context.stage, "value": "ok"}]},
                {"executor": "fake"},
            )

        return {stage: execute for stage in STAGES}

    def test_amplification_requires_exact_global_flow_loop_witness(self) -> None:
        positive = SimpleNamespace(
            kind="container_growth",
            coverage_notes=("persistent_field_container_write:attacker_controlled_loop_multiplicity_proven",),
        )
        self.assertEqual(
            ("proven", "AMPLIFICATION_CFG_DATAFLOW_LOOP_WITNESS"),
            production._amplification_decision_for_candidate(positive),  # noqa: SLF001
        )
        for notes in (
            ("persistent_field_container_write:loop_bound_not_attacker_proven",),
            ("finite_queue_submission_candidate:finite_capacity_prevents_amplification",),
            ("persistent_field_container_write:loop_multiplicity_unmodeled",),
        ):
            with self.subTest(notes=notes):
                self.assertEqual(
                    ("unknown", "AMPLIFICATION_LOOP_OR_BATCH_UNMODELED"),
                    production._amplification_decision_for_candidate(
                        SimpleNamespace(kind="container_growth", coverage_notes=notes)  # noqa: SLF001
                    ),
                )
        self.assertEqual(
            ("not_applicable", "AMPLIFICATION_DIRECT_DEMAND_ASSERTION"),
            production._amplification_decision_for_candidate(
                SimpleNamespace(kind="async_work_growth", coverage_notes=("queue:single_submission_no_enclosing_loop",))
            ),
        )
        self.assertEqual(
            ("proven", "AMPLIFICATION_CFG_DATAFLOW_LOOP_WITNESS"),
            production._amplification_decision_for_candidate(
                SimpleNamespace(
                    kind="direct_allocation",
                    coverage_notes=(
                        "direct_allocation:attacker_controlled_loop_multiplicity_proven",
                    ),
                )
            ),
        )
        self.assertEqual(
            ("unknown", "AMPLIFICATION_LOOP_OR_BATCH_UNMODELED"),
            production._amplification_decision_for_candidate(
                SimpleNamespace(
                    kind="direct_allocation",
                    coverage_notes=(
                        "direct_allocation:loop_multiplicity_unmodeled",
                    ),
                )
            ),
        )

    def test_factory_loads_config_and_injects_environment_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=False),
                environ={"DEEPSEEK_API_KEY": "unused-secret"},
                stage_executors=self._fake_executors(calls),
            )
            self.assertEqual(pipeline.output_root, root / "output")
            self.assertEqual(pipeline.run("entries")["status"], "completed")
            self.assertEqual(calls, ["entries"])

    def test_entries_does_not_require_an_unused_remote_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            values = self._values(root, allow_remote_llm=True)
            values["command"] = "entries"
            pipeline = build_production_pipeline(
                values,
                environ={},
                stage_executors=self._fake_executors(calls),
            )
            self.assertEqual(pipeline.run("entries")["status"], "completed")
            self.assertEqual(calls, ["entries"])

    def test_complete_production_stages_require_consent_before_provider_or_codeql_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            validations: list[Path] = []

            def fake_validate(path: Path, **_kwargs: object) -> DatabaseInfo:
                validations.append(path)
                raise AssertionError("database validation must follow consent")

            with mock.patch("dosweb.production._query_pack_hash") as query_hash:
                pipeline = build_production_pipeline(
                    self._values(root),
                    environ={"DEEPSEEK_API_KEY": "provider-secret"},
                    validate_database_fn=fake_validate,
                )
                with self.assertRaises(AnalyzerError) as raised:
                    pipeline.run("analyze")

            self.assertEqual(raised.exception.code, "CONFIG_REMOTE_LLM_NOT_AUTHORIZED")
            self.assertEqual(calls, [])
            self.assertEqual(validations, [])
            query_hash.assert_not_called()
            self.assertFalse((root / "output" / "run.json").exists())

    def test_default_authorized_production_exposes_all_stages_without_provider_at_build_or_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values = self._values(root, allow_remote_llm=True)
            values["command"] = "entries"
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            info = DatabaseInfo(database, root, "d" * 64)

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            with mock.patch("dosweb.production.DeepSeekClient") as provider:
                pipeline = build_production_pipeline(
                    values,
                    environ={"DEEPSEEK_API_KEY": "provider-secret"},
                    validate_database_fn=lambda *_args, **_kwargs: info,
                    run_query_fn=fake_run,
                )
                self.assertEqual(pipeline._available_stages, frozenset(STAGES))  # noqa: SLF001
                self.assertEqual(pipeline.run("entries")["status"], "completed")
                provider.assert_not_called()

    def test_default_authorized_graph_exposes_provider_stage_without_constructing_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": "provider-secret"},
            )
            self.assertEqual(pipeline._available_stages, frozenset(STAGES))  # noqa: SLF001

    def test_api_key_is_absent_from_fingerprints_errors_and_artifacts(self) -> None:
        secret = "provider-secret-do-not-persist"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": secret},
                stage_executors=self._fake_executors(calls, secret),
            )
            pipeline.run("analyze")
            self.assertEqual(calls, list(STAGES))
            for path in (root / "output").rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes(), str(path))

            fingerprint = pipeline._fingerprint("entries", {})  # noqa: SLF001 - contract boundary test
            self.assertNotIn(secret, json.dumps(fingerprint.to_dict(), sort_keys=True))

    def test_provider_error_is_redacted_before_it_reaches_pipeline_metadata(self) -> None:
        secret = "provider-secret-do-not-persist"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": secret},
                stage_executors=self._fake_executors(calls, secret, fail=True),
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertNotIn(secret, str(raised.exception))
            run_path = root / "output" / "run.json"
            if run_path.exists():
                self.assertNotIn(secret, run_path.read_text(encoding="utf-8"))

    def _payload_for_query(self, query: Path) -> dict[str, object]:
        if query.name == "EntryInterpositions.ql":
            return {"#select": {"columns": list(INTERPOSITION_COLUMNS), "tuples": []}}
        if query.name == "EntrySecurity.ql":
            return {"#select": {"columns": list(SECURITY_COLUMNS), "tuples": []}}
        return self._entry_payload()

    def _entry_payload(self) -> dict[str, object]:
        columns = [
            {"name": name, "kind": "String"}
            for name in (
                "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
                "registration_kind", "registration_fqn", "registration_file",
                "registration_start_line", "route_or_event", "auth_context",
                "attacker_input_name", "attacker_input_type", "attacker_input_kind",
                "materialization_phase", "coverage_status", "coverage_note",
            )
        ]
        return {
            "#select": {
                "columns": columns,
                "tuples": [[
                    "servlet", "http", "fixture.Handler.handle", "src/Handler.java", 10,
                    "annotation_mapping", "fixture.Handler", "src/Handler.java", 8,
                    "/items", "unknown", "body", "byte[]", "request_body", "in_handler",
                    "complete", "servlet_annotation_mapping",
                ]],
            }
        }

    def test_default_entries_executor_validates_runs_four_queries_and_publishes_exact_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>", encoding="utf-8")
            info = DatabaseInfo(database, source, "d" * 64)
            validations: list[Path] = []
            query_databases: list[DatabaseInfo] = []
            queries: list[str] = []

            def fake_validate(path: Path, **_kwargs: object) -> DatabaseInfo:
                validations.append(path)
                return info

            def fake_run(query: Path, database_info: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                queries.append(query.name)
                query_databases.append(database_info)
                generation = output_dir / f"{query.stem}.json"
                generation.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
                return QueryResult(
                    query_name="entries",
                    query_path=query,
                    bqrs_path=query,
                    decoded_path=generation,
                    query_sha256="a" * 64,
                    bqrs_sha256="b" * 64,
                )

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            result = pipeline.run("entries")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(queries, [*production._ENTRY_QUERIES, production._INTERPOSITION_QUERY, production._SECURITY_QUERY])
            self.assertEqual(len(validations), 5)
            self.assertEqual(
                [path for path in validations if path == database],
                [database] * 4,
            )
            self.assertEqual(validations[2].parent, root / "output")
            self.assertTrue(validations[2].name.startswith(".codeql-execution-"))
            self.assertFalse(validations[2].exists())
            self.assertEqual(query_databases, [info] * (len(production._ENTRY_QUERIES) + 2))
            self.assertFalse(
                list((root / "output").glob(".dosweb-entry-queries-*"))
            )
            quarantines = list(
                (root / "output").glob(".dosweb-entry-quarantine-*")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(stat.S_IMODE(quarantines[0].stat().st_mode), 0o700)
            self.assertEqual(
                {
                    path.name
                    for path in (root / "output").iterdir()
                    if path not in quarantines
                },
                {"entry_facts.jsonl", "entry_gap_facts.jsonl", "entry_interposition_facts.jsonl", "coverage.json", "configuration_coverage.json", "descriptor_coverage.json", "modeled_configuration.jsonl", "entry_security_facts.jsonl", "run.json", ".stage-manifests", ".pipeline.lock"},
            )
            self.assertEqual(
                {item["path"] for item in result["stages"]["entries"]["artifacts"]},
                {"entry_facts.jsonl", "entry_gap_facts.jsonl", "entry_interposition_facts.jsonl", "coverage.json", "configuration_coverage.json", "descriptor_coverage.json", "modeled_configuration.jsonl", "entry_security_facts.jsonl"},
            )
            run_metadata = (root / "output" / "run.json").read_text(encoding="utf-8")
            self.assertNotIn("DEEPSEEK_API_KEY", run_metadata)
            self.assertNotIn("Authorization", run_metadata)
            self.assertIn('"analysis_mode":"formal"', run_metadata)
            self.assertEqual(pipeline._fingerprint("entries", {}).database_fingerprint, "d" * 64)  # noqa: SLF001
            self.assertRegex(pipeline._fingerprint("entries", {}).query_pack_hash, r"^[0-9a-f]{64}$")  # noqa: SLF001

    def test_entries_preserve_route_fanout_auth_conflicts_and_partial_deployment(self) -> None:
        from dosweb.reachability import (
            AuthContract,
            EntrySecurityFact,
            derive_auth_contract_from_facts,
            verify_auth_contract,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            (source / "pom.xml").write_text(
                "<project><dependencies><dependency>org.springframework</dependency></dependencies></project>",
                encoding="utf-8",
            )
            info = DatabaseInfo(database, source, "d" * 64)
            entry_rows = [
                [
                    "spring_mvc", "http", "fixture.Api.admin", "src/Api.java", 20,
                    "annotation_mapping", "fixture.Api", "src/Api.java", 18,
                    "GET /api/admin/jobs", "unknown", "body", "String", "request_body",
                    "in_handler", "complete", "spring_annotation_mapping",
                ],
                [
                    "spring_mvc", "http", "fixture.Api.user", "src/Api.java", 30,
                    "annotation_mapping", "fixture.Api", "src/Api.java", 28,
                    "GET /api/user/jobs", "unknown", "body", "String", "request_body",
                    "in_handler", "complete", "spring_annotation_mapping",
                ],
            ]
            security_rows = [
                [
                    "fixture.Security.configure", "src/Security.java", 10, "/api/**",
                    "src/Security.java", 11, "security_filter_chain",
                    "low_privilege_filter", "complete", "static_request_matcher_authenticated",
                ],
                [
                    "fixture.Security.configure", "src/Security.java", 10, "/api/admin/**",
                    "src/Security.java", 12, "security_filter_chain",
                    "privileged_filter", "complete",
                    "static_request_matcher_exact_administrative_role",
                ],
                [
                    "fixture.Api.admin", "src/Api.java", 20, "", "src/Api.java", 19,
                    "annotation", "unauthenticated_annotation", "complete", "permit_all",
                ],
                [
                    "fixture.Api.user", "src/Api.java", 30, "", "src/Api.java", 29,
                    "annotation", "security_matcher_unknown", "partial",
                    "role_requirement_not_proven_administrative",
                ],
                [
                    "fixture.Api.user", "src/Api.java", 30, "", "src/Api.java", 27,
                    "deployment_gate", "optional", "partial",
                    "conditional_presence_default_distribution_unresolved",
                ],
            ]

            def fake_run(
                query: Path,
                _database: DatabaseInfo,
                output_dir: Path,
                **_kwargs: object,
            ) -> QueryResult:
                if query.name == "SpringMvcEntries.ql":
                    columns, rows = ENTRY_COLUMNS, entry_rows
                elif query.name == "EntrySecurity.ql":
                    columns, rows = SECURITY_COLUMNS, security_rows
                elif query.name == "EntryInterpositions.ql":
                    columns, rows = INTERPOSITION_COLUMNS, []
                else:
                    columns, rows = ENTRY_COLUMNS, []
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(
                    json.dumps({"#select": {"columns": list(columns), "tuples": rows}}),
                    encoding="utf-8",
                )
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
            )

            self.assertEqual(pipeline.run("entries")["status"], "completed")
            entries = [
                json.loads(line)
                for line in (root / "output" / "entry_facts.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line
            ]
            security_facts = tuple(
                EntrySecurityFact.from_dict(json.loads(line))
                for line in (root / "output" / "entry_security_facts.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line
            )
            ids = {
                entry["handler"]["callable"].rsplit(".", 1)[-1]: entry["entry_id"]
                for entry in entries
            }
            values_by_entry = {
                name: {
                    fact.value for fact in security_facts if fact.entry_id == entry_id
                }
                for name, entry_id in ids.items()
            }

            self.assertEqual(
                values_by_entry["admin"],
                {
                    "default_enabled",
                    "low_privilege_filter",
                    "privileged_filter",
                    "unauthenticated_annotation",
                },
            )
            self.assertEqual(
                values_by_entry["user"],
                {"low_privilege_filter", "security_matcher_unknown", "optional"},
            )
            self.assertIsNone(
                derive_auth_contract_from_facts(ids["admin"], security_facts)
            )
            self.assertIsNone(
                derive_auth_contract_from_facts(ids["user"], security_facts)
            )
            user_auth = next(
                fact
                for fact in security_facts
                if fact.entry_id == ids["user"]
                and fact.value == "low_privilege_filter"
            )
            user_contract = AuthContract(
                "low_privilege", (user_auth.fact_id,), (), "high"
            )
            decision = verify_auth_contract(
                ids["user"],
                user_contract,
                security_facts,
                slice_fact_ids=frozenset(
                    fact.fact_id
                    for fact in security_facts
                    if fact.entry_id == ids["user"]
                ),
            )
            self.assertEqual(decision.auth_context, "unknown")
            self.assertEqual(decision.deployment_status, "unknown")
            self.assertEqual(decision.status, "unknown")
            self.assertIn(
                "REACH_AUTH_COVERAGE_PARTIAL", decision.reason_codes
            )

    def test_entries_recovers_dropwizard_guice_jaxrs_when_codeql_types_are_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            java = source / "service" / "src" / "main" / "java" / "example"
            database.mkdir()
            java.mkdir(parents=True)
            (java / "Paths.java").write_text(
                'package example; public interface Paths { String ROOT = "/"; String ASSET = "processAsset"; String ANNOTATE = "annotatePDF"; }',
                encoding="utf-8",
            )
            (java / "Resource.java").write_text(
                """package example;
import jakarta.ws.rs.*;
import org.glassfish.jersey.media.multipart.FormDataParam;
@Path(Paths.ROOT)
public class Resource implements Paths {
  @Path(ASSET) @POST
  public Object asset(@FormDataParam("input") java.io.InputStream input) { return null; }
  @POST @Path(ANNOTATE)
  public Object annotate(@FormDataParam("input") java.io.InputStream input) { return null; }
}
""",
                encoding="utf-8",
            )
            (java / "ServiceModule.java").write_text(
                """package example;
import ru.vyarus.dropwizard.guice.module.support.DropwizardAwareModule;
public class ServiceModule extends DropwizardAwareModule<Object> {
  protected void configure() { bind(Resource.class); }
}
""",
                encoding="utf-8",
            )
            (java / "ServiceApplication.java").write_text(
                """package example;
import io.dropwizard.core.Application;
import io.dropwizard.core.setup.Bootstrap;
import io.dropwizard.core.setup.Environment;
import ru.vyarus.dropwizard.guice.GuiceBundle;
public class ServiceApplication extends Application<Object> {
  private static final String RESOURCES = "/api";
  public void initialize(Bootstrap<Object> bootstrap) {
    GuiceBundle bundle = GuiceBundle.builder().modules(getModules()).build();
    bootstrap.addBundle(bundle);
  }
  private AbstractModule getModules() { return new ServiceModule(); }
  public void run(Object configuration, Environment environment) {
    environment.jersey().setUrlPattern(RESOURCES + "/*");
  }
}
""",
                encoding="utf-8",
            )
            info = DatabaseInfo(database, source, "d" * 64)

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                columns = SECURITY_COLUMNS if query.name == "EntrySecurity.ql" else INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else ENTRY_COLUMNS
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(
                    json.dumps({"#select": {"columns": list(columns), "tuples": []}}),
                    encoding="utf-8",
                )
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
            )

            self.assertEqual(pipeline.run("entries")["status"], "completed")
            entries = [
                json.loads(line)
                for line in (root / "output" / "entry_facts.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(
                {entry["route_or_event"] for entry in entries},
                {"POST /api/annotatePDF", "POST /api/processAsset"},
            )
            self.assertTrue(all(entry["framework"] == "jax_rs" for entry in entries))
            self.assertTrue(all(entry["registration"]["callable"] == "example.ServiceModule.bind" for entry in entries))
            self.assertTrue(all(entry["attacker_inputs"] == [{"kind": "stream", "name": "input", "type": "java.io.InputStream"}] for entry in entries))

    def test_formal_entries_query_failure_aborts_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"; source = root / "source"
            database.mkdir(); (source / "src/main/java/app").mkdir(parents=True)
            (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>", encoding="utf-8")
            info = DatabaseInfo(database, source, "d" * 64)
            def failing_run(*_args: object, **_kwargs: object) -> QueryResult:
                raise AnalyzerError("CODEQL_QUERY_FAILED", "CodeQL query execution failed.")
            values = self._values(root)
            values["source_checkout"] = source; values["analysis_source_root"] = source
            pipeline = build_production_pipeline(values, environ={}, validate_database_fn=lambda *_args, **_kwargs: info, run_query_fn=failing_run)
            with self.assertRaisesRegex(AnalyzerError, "CodeQL query execution failed") as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertFalse((root / "output" / ".stage-manifests" / "entries.json").exists())

    def test_exploratory_entries_runs_all_queries_and_marks_failures_as_partial_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            (source / "src/main/java/app").mkdir(parents=True)
            (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>", encoding="utf-8")
            info = DatabaseInfo(database, source, "d" * 64)

            def failing_run(_query: Path, _database: DatabaseInfo, _output_dir: Path, **_kwargs: object) -> QueryResult:
                raise AnalyzerError("CODEQL_QUERY_FAILED", "CodeQL query execution failed.", {"stage": "query_run", "diagnostic": "timeout"})

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            values["allow_partial_codeql"] = True
            values["command"] = "entries"
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=failing_run,
            )
            result = pipeline.run("entries")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["stages"]["entries"]["metadata"]["query_count"], 8)
            self.assertEqual(result["stages"]["entries"]["metadata"]["skipped_query_count"], 8)
            self.assertEqual(
                {
                    row["query_name"]
                    for row in result["stages"]["entries"]["metadata"]["query_diagnostics"]
                },
                {
                    *production._ENTRY_QUERIES,
                    production._INTERPOSITION_QUERY,
                    production._SECURITY_QUERY,
                },
            )
            coverage = json.loads((root / "output" / "coverage.json").read_text(encoding="utf-8"))
            spring = next(item for item in coverage if item["framework"] == "spring_mvc")
            self.assertEqual(spring["status"], "partial")
            self.assertIn("query_failed:SpringMvcEntries", spring["unsupported_patterns"])
            servlet = next(item for item in coverage if item["framework"] == "servlet")
            self.assertEqual(servlet["status"], "partial")
            self.assertIn("query_failed:ServletEntries", servlet["unsupported_patterns"])
            self.assertEqual((root / "output" / "entry_facts.jsonl").read_text(encoding="utf-8"), "")

    def test_exploratory_entries_does_not_reduce_queries_for_a_large_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            java = source / "src/main/java/app"
            java.mkdir(parents=True)
            for index in range(513):
                (java / f"A{index:03d}.java").write_text(
                    "class A {}\n" if index else "@RestController class A {}\n",
                    encoding="utf-8",
                )
            info = DatabaseInfo(database, source, "d" * 64)
            observed_queries: list[str] = []

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                observed_queries.append(query.name)
                payload = self._payload_for_query(query)
                if query.name in production._ENTRY_QUERIES:
                    payload["#select"]["tuples"][0][0] = "spring_mvc"  # type: ignore[index]
                    payload["#select"]["tuples"][0][16] = "spring_annotation_mapping"  # type: ignore[index]
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(payload), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            values["allow_partial_codeql"] = True
            values["command"] = "entries"
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
            )
            result = pipeline.run("entries")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(
                observed_queries,
                [
                    *production._ENTRY_QUERIES,
                    production._INTERPOSITION_QUERY,
                    production._SECURITY_QUERY,
                ],
            )
            self.assertEqual(result["stages"]["entries"]["metadata"]["query_count"], 8)
            self.assertFalse(
                result["stages"]["entries"]["metadata"]["entry_evidence_scan_truncated"]
            )

    def test_default_entries_executes_the_preflight_query_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>", encoding="utf-8")
            info = DatabaseInfo(database, source, "d" * 64)
            observed: list[tuple[Path, bytes]] = []

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                observed.append((query, query.read_bytes()))
                decoded = output_dir / f"{query.stem}.json"
                decoded.parent.mkdir(parents=True, exist_ok=True)
                decoded.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            import dosweb.production as production

            pack_hash, snapshot = production._query_pack_snapshot()  # noqa: SLF001

            with mock.patch(
                "dosweb.production._query_pack_snapshot",
                return_value=(pack_hash, snapshot),
            ):
                values = self._values(root)
                values["source_checkout"] = source
                values["analysis_source_root"] = source
                pipeline = build_production_pipeline(
                    values,
                    environ={},
                    validate_database_fn=lambda *_args, **_kwargs: info,
                    run_query_fn=fake_run,
                )
                self.assertEqual(pipeline.run("entries")["status"], "completed")

            original = production._ENTRY_QUERY_DIR / "SpringMvcEntries.ql"  # noqa: SLF001
            self.assertEqual(len(observed), len(production._ENTRY_QUERIES) + 2)
            self.assertNotEqual(observed[0][0], original)
            self.assertEqual(
                observed[0][1],
                snapshot["dosweb/Entries/SpringMvcEntries.ql"],
            )
            self.assertEqual(
                {query.name for query, _ in observed},
                {*production._ENTRY_QUERIES, production._INTERPOSITION_QUERY, production._SECURITY_QUERY},
            )

    def test_default_preflight_rejects_invalid_database_validator_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: None,  # type: ignore[arg-type]
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_DATABASE_INVALID")
            run = json.loads(
                (root / "output" / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(run["status"], "failed")
            self.assertEqual(run["attempt"], 1)
            self.assertEqual(run["error"]["code"], "CODEQL_DATABASE_INVALID")

    def test_default_preflight_rejects_database_from_different_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "other-source"
            database.mkdir()
            source.mkdir()
            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: DatabaseInfo(
                    database, source, "d" * 64
                ),
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_DATABASE_INVALID")
            run = json.loads(
                (root / "output" / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(run["status"], "failed")
            self.assertEqual(run["attempt"], 1)
            self.assertEqual(run["error"]["code"], "CODEQL_DATABASE_INVALID")

    def test_default_preflight_accepts_separate_analysis_and_provider_checkouts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            analysis = root / "analysis"
            provider = root / "provider"
            database.mkdir()
            analysis.mkdir()
            provider.mkdir()
            values = self._values(root)
            values["analysis_source_root"] = analysis
            values["source_checkout"] = provider

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: DatabaseInfo(
                    database, analysis, "d" * 64
                ),
                run_query_fn=fake_run,
            )
            self.assertEqual(pipeline.run("entries")["status"], "completed")

    def test_default_preflight_runs_under_the_pipeline_output_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            info = DatabaseInfo(root / "database", root, "d" * 64)
            (root / "database").mkdir()
            (root / "source").mkdir()

            def fake_validate(_path: Path, **_kwargs: object) -> DatabaseInfo:
                lock_path = root / "output" / ".pipeline.lock"
                self.assertTrue(lock_path.exists())
                return info

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                generation = output_dir / f"{query.stem}.json"
                generation.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
                return QueryResult(query.name, query, query, generation, "a" * 64, "b" * 64)

            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            self.assertEqual(pipeline.run("entries")["status"], "completed")

    def test_packaged_query_assets_are_available_to_the_default_executor(self) -> None:
        import dosweb.production as production

        expected = {*production._ENTRY_QUERIES, production._INTERPOSITION_QUERY, production._SECURITY_QUERY}  # noqa: SLF001 - packaging contract
        packaged = {path.name for path in production._ENTRY_QUERY_DIR.glob("*.ql")}  # noqa: SLF001
        self.assertEqual(packaged, expected)
        self.assertTrue((production._QUERY_PACK_DIR / "qlpack.yml").is_file())  # noqa: SLF001
        self.assertTrue((production._QUERY_PACK_DIR / "codeql-pack.lock.yml").is_file())  # noqa: SLF001
        self.assertRegex(production._query_pack_hash(), r"^[0-9a-f]{64}$")  # noqa: SLF001

    def test_default_entries_executor_rejects_aggregate_row_overflow_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            info = DatabaseInfo(root / "database", root, "d" * 64)
            (root / "database").mkdir()
            (root / "source").mkdir()

            def fake_validate(_path: Path, **_kwargs: object) -> DatabaseInfo:
                return info

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                payload = self._payload_for_query(query)
                payload["#select"]["tuples"] *= 1025  # type: ignore[index,operator]
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(payload), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")
            self.assertFalse((root / "output" / "entry_facts.jsonl").exists())

    def test_default_entries_executor_rejects_malformed_decoded_result_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            info = DatabaseInfo(root / "database", root, "d" * 64)
            (root / "database").mkdir()
            (root / "source").mkdir()

            def fake_validate(_path: Path, **_kwargs: object) -> DatabaseInfo:
                return info

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                malformed = output_dir / f"{query.stem}.json"
                malformed.write_text('{"#select":{"columns":[],"tuples":[]}}', encoding="utf-8")
                return QueryResult(query.name, query, query, malformed, "a" * 64, "b" * 64)

            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")
            self.assertFalse((root / "output" / "entry_facts.jsonl").exists())

    def _entry_and_candidate(self, *, handler_line: int = 20) -> tuple[EntryFact, GrowthCandidate]:
        entry = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact("fixture.Handler.handle", "src/Handler.java", handler_line),
            registration=RegistrationFact("annotation_mapping", "fixture.Handler", "src/Handler.java", 8),
            registration_pattern_id="entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
            route_or_event="/items",
            auth_context="unknown",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/Handler.java", handler_line + 4),
            kind="input_materialization",
            operation="request.getInputStream().readAllBytes",
            resource_dimension="bytes",
            receiver="fixture.Handler.body",
            field_path="this.body",
            demand_inputs=(DemandInput("body", "value"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
        )
        return entry, candidate

    def test_load_verified_growth_rejects_duplicate_growth_ownership_in_every_order(self) -> None:
        _entry, candidate = self._entry_and_candidate()
        first = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:first",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        second = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:second",
            status="unresolved",
            reason_codes=("GROWTH_ASSOCIATION_INCOMPLETE",),
            checks=(
                VerificationCheck(
                    "candidate_entry_association",
                    False,
                    "GROWTH_ASSOCIATION_INCOMPLETE",
                ),
            ),
        )
        sequences = {
            "forward": (first, second),
            "reverse": (second, first),
            "identical": (first, first),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = StageContext(
                "flows",
                root,
                StageFingerprint.for_stage("flows"),
                {},
                {},
            )
            for label, sequence in sequences.items():
                with self.subTest(order=label):
                    def records(
                        _context: StageContext,
                        _stage: str,
                        artifact: str,
                        _schema: str,
                    ) -> list[dict[str, object]]:
                        if artifact == "growth_candidates.jsonl":
                            return [candidate.to_dict()]
                        if artifact == "verified_growth.jsonl":
                            return [item.to_dict() for item in sequence]
                        raise AssertionError(artifact)

                    with mock.patch.object(
                        production,
                        "_records",
                        side_effect=records,
                    ):
                        with self.assertRaises(AnalyzerError) as raised:
                            production._load_verified_growth(context)  # noqa: SLF001
                    self.assertEqual(
                        raised.exception.code,
                        "ARTIFACT_UPSTREAM_INVALID",
                    )

    def test_flow_upstream_readers_reject_unexpected_fields(self) -> None:
        entry, candidate = self._entry_and_candidate()
        verified = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:strict-upstream",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        link = CandidateEntryLink.create(
            candidate.growth_id,
            entry.entry_id,
            "complete",
            (candidate.growth_id, entry.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        disposition = CandidateDisposition.create(
            candidate.growth_id,
            "formal_eligible",
            canonical_entry_id=entry.entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=(candidate.growth_id, link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )
        cases = (
            ("candidate_entry_links.jsonl", "candidate_entry_links", link.to_dict(), True),
            ("candidate_dispositions.jsonl", "candidate_dispositions", disposition.to_dict(), True),
            ("growth_candidates.jsonl", "growth_candidates", candidate.to_dict(), False),
            ("verified_growth.jsonl", "verified_growth", verified.to_dict(), False),
        )
        with tempfile.TemporaryDirectory() as temporary:
            context = StageContext(
                "flows",
                Path(temporary),
                StageFingerprint.for_stage("flows"),
                {},
                {},
            )
            for artifact, schema, record, strict in cases:
                with self.subTest(artifact=artifact):
                    payload = (
                        json.dumps(
                            {**record, "unexpected": True},
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                    with mock.patch.object(
                        production,
                        "_upstream_bytes",
                        return_value=payload,
                    ):
                        with self.assertRaises(AnalyzerError):
                            if strict:
                                production._strict_records(  # noqa: SLF001
                                    context,
                                    "growth",
                                    artifact,
                                )
                            else:
                                production._records(  # noqa: SLF001
                                    context,
                                    "growth",
                                    artifact,
                                    schema,
                                )

    def test_flow_reconciliation_rejects_missing_raw_candidate_disposition(self) -> None:
        entry, candidate_a = self._entry_and_candidate()
        _other_entry, candidate_b = self._entry_and_candidate(handler_line=30)
        verified_a = VerifiedGrowthResult.create(
            candidate=candidate_a,
            slice_id="slice:retained-a",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        link_a = CandidateEntryLink.create(
            candidate_a.growth_id,
            entry.entry_id,
            "complete",
            (candidate_a.growth_id, entry.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        disposition_a = CandidateDisposition.create(
            candidate_a.growth_id,
            "formal_eligible",
            canonical_entry_id=entry.entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link_a.link_id,),
            evidence_ids=(candidate_a.growth_id, link_a.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )

        class CandidateDomain(dict[str, VerifiedGrowthResult]):
            candidate_growth_ids = frozenset(
                {candidate_a.growth_id, candidate_b.growth_id}
            )

        with self.assertRaises(AnalyzerError) as raised:
            production._canonical_flow_entry_ids(  # noqa: SLF001
                {entry.entry_id: entry},
                CandidateDomain({candidate_a.growth_id: verified_a}),
                (link_a.to_dict(),),
                (disposition_a.to_dict(),),
            )
        self.assertEqual(raised.exception.code, "ARTIFACT_UPSTREAM_INVALID")

    def test_flow_reconciliation_rejects_duplicate_candidate_disposition(self) -> None:
        entry, candidate = self._entry_and_candidate()
        verified = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:retained",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        link = CandidateEntryLink.create(
            candidate.growth_id,
            entry.entry_id,
            "complete",
            (candidate.growth_id, entry.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        disposition = CandidateDisposition.create(
            candidate.growth_id,
            "formal_eligible",
            canonical_entry_id=entry.entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=(candidate.growth_id, link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )

        with self.assertRaises(AnalyzerError) as raised:
            production._canonical_flow_entry_ids(  # noqa: SLF001
                {entry.entry_id: entry},
                {candidate.growth_id: verified},
                (link.to_dict(),),
                (disposition.to_dict(), disposition.to_dict()),
            )
        self.assertEqual(raised.exception.code, "ARTIFACT_UPSTREAM_INVALID")

    def test_flow_reconciliation_rejects_phantom_inventory_growth_domain(self) -> None:
        entry, candidate = self._entry_and_candidate()
        verified = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:retained",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        retained_link = CandidateEntryLink.create(
            candidate.growth_id,
            entry.entry_id,
            "complete",
            (candidate.growth_id, entry.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        retained_disposition = CandidateDisposition.create(
            candidate.growth_id,
            "formal_eligible",
            canonical_entry_id=entry.entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(retained_link.link_id,),
            evidence_ids=(candidate.growth_id, retained_link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
        )
        phantom_growth_id = "growth:" + "f" * 64
        phantom_link = CandidateEntryLink.create(
            phantom_growth_id,
            entry.entry_id,
            "partial",
            (phantom_growth_id, entry.entry_id),
            ("ASSOCIATION_QUERY_PARTIAL",),
        )
        phantom_disposition = CandidateDisposition.create(
            phantom_growth_id,
            "inventory_unresolved",
            canonical_entry_id=entry.entry_id,
            local_growth_status="partial",
            association_status="partial",
            link_ids=(phantom_link.link_id,),
            evidence_ids=(phantom_growth_id, phantom_link.link_id),
            negative_proof_ids=(),
            reason_codes=("MATURATION_INVENTORY_UNRESOLVED",),
        )

        class CandidateDomain(dict[str, VerifiedGrowthResult]):
            candidate_growth_ids = frozenset({candidate.growth_id})

        with self.assertRaises(AnalyzerError) as raised:
            production._canonical_flow_entry_ids(  # noqa: SLF001
                {entry.entry_id: entry},
                CandidateDomain({candidate.growth_id: verified}),
                (retained_link.to_dict(), phantom_link.to_dict()),
                (
                    retained_disposition.to_dict(),
                    phantom_disposition.to_dict(),
                ),
            )
        self.assertEqual(raised.exception.code, "ANALYSIS_DANGLING_FACT_REFERENCE")

    def test_partial_relevance_maturation_marks_local_growth_partial(self) -> None:
        entry, candidate = self._entry_and_candidate()
        link = CandidateEntryLink.create(
            candidate.growth_id,
            entry.entry_id,
            "complete",
            (candidate.growth_id, entry.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        association = CandidateDisposition.create(
            candidate.growth_id,
            "formal_eligible",
            canonical_entry_id=entry.entry_id,
            local_growth_status="complete",
            association_status="complete",
            link_ids=(link.link_id,),
            evidence_ids=(candidate.growth_id, entry.entry_id, link.link_id),
            negative_proof_ids=(),
            reason_codes=("ASSOCIATION_QUERY_EVIDENCE",),
        )

        matured = production._mature_disposition(  # noqa: SLF001
            candidate,
            association,
            status="gap_eligible",
            relevance_status="dos_relevant_partial",
            reason_codes=("MATURATION_GAP_ELIGIBLE",),
        )

        self.assertEqual("gap_eligible", matured.status)
        self.assertEqual("partial", matured.local_growth_status)
        self.assertEqual("complete", matured.association_status)

    def test_candidate_entry_association_rejects_no_match_and_prefers_nearest_handler(self) -> None:
        entry, candidate = self._entry_and_candidate()
        with self.assertRaises(AnalyzerError) as no_match:
            production._entry_for_candidate({}, candidate)  # noqa: SLF001
        self.assertEqual(no_match.exception.code, "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS")
        other = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact("fixture.Other.handle", "src/Handler.java", 12),
            registration=RegistrationFact("annotation_mapping", "fixture.Other", "src/Other.java", 8),
            registration_pattern_id="entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
            route_or_event="/other",
            auth_context="unknown",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )
        self.assertEqual(production._entry_for_candidate({entry.entry_id: entry, other.entry_id: other}, candidate), entry)  # noqa: SLF001
        self.assertEqual(production._entry_for_candidate({entry.entry_id: entry}, candidate), entry)  # noqa: SLF001

    def test_candidate_entry_association_does_not_collapse_different_exact_registration_patterns(self) -> None:
        entry, candidate = self._entry_and_candidate()
        duplicate = EntryFact.create(
            framework=entry.framework,
            protocol=entry.protocol,
            handler=entry.handler,
            registration=RegistrationFact("static_registration", "fixture.Handler.register", "src/Config.java", 99),
            registration_pattern_id="entry-registration-coverage:spring_mvc:static_registration:armeria_annotated_service_registration",
            route_or_event=entry.route_or_event,
            auth_context=entry.auth_context,
            attacker_inputs=entry.attacker_inputs,
            materialization_phase=entry.materialization_phase,
        )
        with self.assertRaises(AnalyzerError) as raised:
            production._entry_for_candidate(  # noqa: SLF001
                {entry.entry_id: entry, duplicate.entry_id: duplicate}, candidate
            )
        self.assertEqual(raised.exception.code, "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS")

    def test_candidate_association_does_not_canonicalize_distinct_jaxrs_handlers_sharing_registration(self) -> None:
        registration = RegistrationFact(
            "static_registration",
            "fixture.ServiceModule.bind",
            "src/ServiceModule.java",
            44,
        )
        first = EntryFact.create(
            framework="jax_rs",
            protocol="http",
            handler=HandlerFact(
                "fixture.RestService.processDocumentPost",
                "src/RestService.java",
                484,
            ),
            registration=registration,
            registration_pattern_id=(
                "entry-registration-coverage:jax_rs:static_registration:"
                "dropwizard_guice_source_registration"
            ),
            route_or_event="POST /api/processDocument",
            auth_context="unknown",
            attacker_inputs=(
                AttackerInputFact("inputStream", "InputStream", "stream"),
            ),
            materialization_phase="before_handler",
        )
        second = EntryFact.create(
            framework="jax_rs",
            protocol="http",
            handler=HandlerFact(
                "fixture.RestService.processDocumentPut",
                "src/RestService.java",
                522,
            ),
            registration=registration,
            registration_pattern_id=first.registration_pattern_id,
            route_or_event="PUT /api/processDocument",
            auth_context="unknown",
            attacker_inputs=first.attacker_inputs,
            materialization_phase="before_handler",
        )
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/ProcessFiles.java", 748),
            kind="input_materialization",
            operation="java.io.ByteArrayOutputStream.toByteArray",
            resource_dimension="bytes",
            receiver="outputStream",
            field_path="outputStream",
            demand_inputs=(DemandInput("outputStream", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_status="partial",
            coverage_notes=(
                "recognized_byte_array_output_stream_materialization:"
                "parser_materialization_partial",
            ),
        )

        def row(entry: EntryFact) -> dict[str, object]:
            return {
                "source_file": entry.handler.file,
                "source_start_line": entry.handler.start_line,
                "sink_file": candidate.site.file,
                "sink_start_line": candidate.site.start_line,
                "attacker_target": "size",
                "attacker_source": "inputStream",
                "attacker_sink": "outputStream",
                "call_path": entry.handler.callable,
                "phase_sequence": "entry>bounded_call_path>output_copy",
                "flow_kind": "data_flow",
                "confidence": "partial",
                "coverage_status": "partial",
                "coverage_note": (
                    "source_input_stream_to_output_copy_requires_dataflow_witness"
                ),
            }

        rows = (row(first), row(second))
        links, disposition = production._candidate_association(  # noqa: SLF001
            {first.entry_id: first, second.entry_id: second},
            candidate,
            rows,
            rows,
        )

        self.assertEqual(
            {link.entry_id for link in links},
            {first.entry_id, second.entry_id},
        )
        self.assertEqual(disposition.status, "inventory_unresolved")
        self.assertEqual(disposition.association_status, "ambiguous")
        self.assertEqual(disposition.canonical_entry_id, "")

    def test_complete_candidate_association_requires_the_same_formal_flow_witness(self) -> None:
        entry, candidate = self._entry_and_candidate()
        association = {
            "source_file": entry.handler.file,
            "source_start_line": entry.handler.start_line,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
            "attacker_target": "value",
            "attacker_source": entry.handler.callable,
            "attacker_sink": candidate.demand_inputs[0].name,
            "call_path": entry.handler.callable,
            "phase_sequence": "entry>global_dataflow>growth",
            "flow_kind": "data_flow",
            "confidence": "proven",
            "coverage_status": "complete",
            "coverage_note": "same_handler_global_dataflow",
        }
        entries = {entry.entry_id: entry}

        missing_links, missing_disposition = production._candidate_association(  # noqa: SLF001
            entries,
            candidate,
            (association,),
            (),
        )
        self.assertEqual(len(missing_links), 1)
        self.assertEqual(missing_links[0].status, "partial")
        self.assertEqual(missing_disposition.status, "gap_eligible")
        self.assertIn("FLOW_CODEQL_ROW_MISSING", missing_disposition.reason_codes)

        wrong_source = {
            **association,
            "attacker_source": "not_an_entry_input",
        }
        invalid_links, invalid_disposition = production._candidate_association(  # noqa: SLF001
            entries,
            candidate,
            (association,),
            (wrong_source,),
        )
        self.assertEqual(len(invalid_links), 1)
        self.assertEqual(invalid_links[0].status, "partial")
        self.assertEqual(invalid_disposition.status, "gap_eligible")
        self.assertIn(
            "FLOW_FORMAL_PROOF_INCOMPLETE",
            invalid_disposition.reason_codes,
        )

        formal = {
            **association,
            "attacker_source": "body",
        }
        proven_links, proven_disposition = production._candidate_association(  # noqa: SLF001
            entries,
            candidate,
            (association,),
            (formal,),
        )
        self.assertEqual(len(proven_links), 1)
        self.assertEqual(proven_links[0].status, "complete")
        self.assertEqual(proven_disposition.status, "formal_eligible")

        fallback_links, fallback_disposition = production._candidate_association(  # noqa: SLF001
            entries,
            candidate,
            (),
            (),
        )
        self.assertEqual(len(fallback_links), 1)
        self.assertEqual(fallback_links[0].status, "partial")
        self.assertIn("FLOW_CODEQL_ROW_MISSING", fallback_disposition.reason_codes)

        partial_association = {
            **association,
            "confidence": "partial",
            "coverage_status": "partial",
            "coverage_note": "unique_call_graph_only",
        }
        partial_links, partial_disposition = production._candidate_association(  # noqa: SLF001
            entries,
            candidate,
            (partial_association,),
            (),
        )
        self.assertEqual(len(partial_links), 1)
        self.assertEqual(partial_links[0].status, "partial")
        self.assertIn("FLOW_CODEQL_ROW_MISSING", partial_disposition.reason_codes)

    def test_flow_screening_reconciles_broad_source_fallback_to_extracted_entries(self) -> None:
        entry, candidate = self._entry_and_candidate()
        growth = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:fixture",
            status="unresolved",
            reason_codes=("GROWTH_ASSOCIATION_INCOMPLETE",),
            checks=(
                VerificationCheck(
                    "candidate_entry_association",
                    False,
                    "GROWTH_ASSOCIATION_INCOMPLETE",
                ),
            ),
        )
        valid = {
            "source_file": entry.handler.file,
            "source_start_line": entry.handler.start_line,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
        }
        broad_non_entry = {
            **valid,
            "source_file": "src/UnregisteredService.java",
            "source_start_line": 61,
        }

        reconciled = production._reconcile_flow_rows(  # noqa: SLF001
            (valid, broad_non_entry),
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )

        self.assertEqual(reconciled, [valid])

    def test_poc33_repairs_invalidate_pre_fix_resume_artifacts(self) -> None:
        self.assertEqual(set(production._IMPLEMENTATION_VERSIONS), set(STAGES))  # noqa: SLF001
        for stage, version in production._IMPLEMENTATION_VERSIONS.items():  # noqa: SLF001
            with self.subTest(stage=stage):
                self.assertTrue(
                    version.startswith(f"production-v2.8-open-world-maturation-{stage}-"),
                    version,
                )
        self.assertEqual(  # noqa: SLF001
            production._IMPLEMENTATION_VERSIONS["flows"],
            "production-v2.8-open-world-maturation-flows-v22",
        )
        self.assertEqual(  # noqa: SLF001
            production._IMPLEMENTATION_VERSIONS["entries"],
            "production-v2.8-open-world-maturation-entries-v17",
        )
        self.assertEqual(  # noqa: SLF001
            production._IMPLEMENTATION_VERSIONS["growth"],
            "production-v2.8-open-world-maturation-growth-v33",
        )
        self.assertEqual(  # noqa: SLF001
            production._IMPLEMENTATION_VERSIONS["lifecycle"],
            "production-v2.8-open-world-maturation-lifecycle-v17",
        )
        self.assertEqual(  # noqa: SLF001
            production._IMPLEMENTATION_VERSIONS["conclude"],
            "production-v2.8-open-world-maturation-conclude-v9",
        )

    def test_growth_v31_stage_manifest_cannot_resume_under_v32(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            stale_versions = {
                **production._IMPLEMENTATION_VERSIONS,  # noqa: SLF001
                "growth": "production-v2.7-open-world-maturation-growth-v31",
            }
            with mock.patch.object(
                production, "_IMPLEMENTATION_VERSIONS", stale_versions
            ):
                stale = build_production_pipeline(
                    self._values(root, allow_remote_llm=True),
                    environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                    stage_executors=self._fake_executors(calls),
                )
                self.assertEqual(stale.run("growth")["status"], "completed")
            self.assertEqual(calls, ["entries", "growth"])

            calls.clear()
            resumed = build_production_pipeline(
                {
                    **self._values(root, allow_remote_llm=True),
                    "resume": True,
                },
                environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                stage_executors=self._fake_executors(calls),
            )
            self.assertEqual(resumed.run("growth")["status"], "completed")
            self.assertEqual(calls, ["growth"])

    def test_candidate_link_schema_hardening_invalidates_pre_fix_conclude_resume(self) -> None:
        self.assertEqual(  # noqa: SLF001
            production._IMPLEMENTATION_VERSIONS["conclude"],
            "production-v2.8-open-world-maturation-conclude-v9",
        )

    def test_only_formal_eligible_candidate_is_gap_free_for_positive_gate(self) -> None:
        self.assertTrue(production._candidate_relevant_gap_free("formal_eligible"))  # noqa: SLF001
        for status in ("gap_eligible", "rejected", "inventory_unresolved"):
            with self.subTest(status=status):
                self.assertFalse(production._candidate_relevant_gap_free(status))  # noqa: SLF001

    def test_candidate_entry_fallback_rejects_different_exact_registration_patterns(self) -> None:
        entry, _candidate = self._entry_and_candidate()
        duplicate = EntryFact.create(
            framework=entry.framework,
            protocol=entry.protocol,
            handler=entry.handler,
            registration=RegistrationFact("static_registration", "fixture.Handler.register", "src/Config.java", 99),
            registration_pattern_id="entry-registration-coverage:spring_mvc:static_registration:armeria_annotated_service_registration",
            route_or_event=entry.route_or_event,
            auth_context=entry.auth_context,
            attacker_inputs=entry.attacker_inputs,
            materialization_phase=entry.materialization_phase,
        )
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/Helper.java", 50),
            kind="direct_allocation",
            operation="new byte[size]",
            resource_dimension="bytes",
            receiver="byte[]",
            field_path="allocation",
            demand_inputs=(DemandInput("body", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
        )
        with self.assertRaises(AnalyzerError) as raised:
            production._entry_for_candidate(  # noqa: SLF001
                {entry.entry_id: entry, duplicate.entry_id: duplicate}, candidate
            )
        self.assertEqual(raised.exception.code, "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS")

    def _bqrs_payload(self, columns: tuple[str, ...], rows: list[list[object]]) -> dict[str, object]:
        return {"#select": {"columns": [{"name": name, "kind": "String"} for name in columns], "tuples": rows}}

    def test_ambiguous_duplicate_registrations_stay_disposition_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"; database.mkdir()
            source = root / "source"; source.mkdir()
            info = DatabaseInfo(database, root, "d" * 64)

            rows_by_query: dict[str, tuple[tuple[str, ...], list[list[object]]]] = {
                "SpringMvcEntries": (ENTRY_COLUMNS, [[
                    "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                    "annotation_mapping", "fixture.Handler", "src/Handler.java", 8, "/items",
                    "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                    "spring_annotation_mapping",
                ]]),
                "ServletEntries": (ENTRY_COLUMNS, [[
                    "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                    "static_registration", "fixture.Router", "src/Router.java", 40, "/items",
                    "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                    "armeria_annotated_service_registration",
                ]]),
                "InputMaterialization": (GROWTH_COLUMNS, [[
                    "src/Handler.java", 24, "input_materialization", "spring_request_body_materialization",
                    "bytes", "fixture.Handler.body", "this.body", "body", "size", "request",
                    "fact:growth", "complete", "recognized_spring_request_body_bytes",
                ]]),
                "EntryToGrowth": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ]]),
                "EntryToGrowthAssociations": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ]]),
                "GuardCandidates": (GUARD_COLUMNS, []),
                "BoundCandidates": (BOUND_COLUMNS, []),
                "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
                "LifecycleCoverage": (LIFECYCLE_COVERAGE_COLUMNS, []),
                "LifecycleSummary": (LIFECYCLE_SUMMARY_COLUMNS, []),
            }

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                columns, rows = rows_by_query.get(query.stem, (SECURITY_COLUMNS if query.name == "EntrySecurity.ql" else INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else ENTRY_COLUMNS if query.parent.name == "Entries" else GROWTH_COLUMNS, []))
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._bqrs_payload(columns, rows)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            def fake_excerpt(checkout: Path, commit: str, path: str, line: int) -> SourceExcerpt:
                import hashlib
                content = f"attested line {line}\n"
                return SourceExcerpt(
                    f"excerpt:{line}", path, line, line, content, "c" * 64,
                    hashlib.sha256(content.encode()).hexdigest(),
                )

            class FakeLlm:
                def classify_growth(self, bounded: object) -> GrowthContract:
                    return _unknown_growth_contract()

            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
                deepseek_client=FakeLlm(),
                source_excerpt_fn=fake_excerpt,
            )
            self.assertEqual(pipeline.run("analyze")["status"], "completed")
            verified = [
                json.loads(line)
                for line in (root / "output" / "verified_growth.jsonl").read_text().splitlines()
            ]
            self.assertEqual(verified, [])
            dispositions = [
                json.loads(line)
                for line in (root / "output" / "candidate_dispositions.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(dispositions), 1)
            self.assertEqual(dispositions[0]["status"], "inventory_unresolved")
            self.assertIn(
                "RELEVANCE_CANONICAL_ENTRY_UNPROVEN",
                dispositions[0]["reason_codes"],
            )

    def test_injected_query_llm_and_source_seams_exercise_the_full_default_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"; database.mkdir()
            source = root / "source"; source.mkdir()
            info = DatabaseInfo(database, root, "d" * 64)
            query_calls: list[str] = []
            excerpt_calls: list[tuple[Path, str, str, int]] = []
            llm_calls: list[object] = []
            auth_llm_calls: list[str] = []

            rows_by_query: dict[str, tuple[tuple[str, ...], list[list[object]]]] = {
                "SpringMvcEntries": (ENTRY_COLUMNS, [
                    [
                        "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                        "annotation_mapping", "fixture.Handler", "src/Handler.java", 8, "/items",
                        "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                        "spring_annotation_mapping",
                    ],
                    [
                        "spring_mvc", "http", "fixture.Other.handle", "src/OtherController.java", 40,
                        "annotation_mapping", "fixture.Other", "src/OtherController.java", 36, "/other",
                        "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                        "spring_annotation_mapping",
                    ],
                ]),
                "InputMaterialization": (GROWTH_COLUMNS, [
                    [
                        "src/Handler.java", 24, "input_materialization", "spring_request_body_materialization",
                        "bytes", "fixture.Handler.body", "this.body", "body", "size", "request",
                        "fact:growth", "complete", "recognized_spring_request_body_bytes",
                    ],
                    [
                        "src/Handler.java", 26, "input_materialization", "spring_request_body_string_materialization",
                        "bytes", "fixture.Handler.bodyString", "this.bodyString", "body", "size", "request",
                        "fact:growth-string", "complete", "recognized_spring_request_body_string",
                    ],
                    [
                        "src/Detached.java", 9, "input_materialization", "request.readAllBytes",
                        "bytes", "fixture.Detached.body", "this.body", "body", "size", "request",
                        "fact:other-growth", "complete", "input_materialization",
                    ],
                    [
                        "src/OtherController.java", 44, "input_materialization", "spring_request_body_materialization",
                        "bytes", "fixture.Other.body", "body", "body", "size", "request",
                        "fact:privileged-growth", "complete", "recognized_spring_request_body_bytes",
                    ],
                ]),
                "DirectAllocation": (GROWTH_COLUMNS, [[
                    "src/Handler.java", 25, "direct_allocation", "array_creation",
                    "bytes", "byte[]", "allocation", "serverLimit", "size", "request",
                    "fact:server-sized", "complete", "direct_allocation:server_metadata_size",
                ]]),
                "EntryToGrowth": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ], [
                    "src/Handler.java", 20, "src/Handler.java", 26, "size", "body", "body",
                    "fixture.Handler.handle", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ], [
                    "src/Handler.java", 20, "src/Handler.java", 25, "size", "body", "serverLimit",
                    "fixture.Handler.handle", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ], [
                    "src/OtherController.java", 40, "src/OtherController.java", 44,
                    "size", "body", "body", "fixture.Other.handle",
                    "entry>callgraph>growth", "data_flow", "proven", "complete",
                    "same_handler_call_graph_association",
                ]]),
                "EntryToGrowthAssociations": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ], [
                    "src/Handler.java", 20, "src/Handler.java", 26, "size", "body", "body",
                    "fixture.Handler.handle", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ], [
                    "src/Handler.java", 20, "src/Handler.java", 25, "size", "body", "serverLimit",
                    "fixture.Handler.handle", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ], [
                    "src/OtherController.java", 40, "src/OtherController.java", 44,
                    "size", "body", "body", "fixture.Other.handle",
                    "entry>callgraph>growth", "data_flow", "proven", "complete",
                    "same_handler_call_graph_association",
                ]]),
                "EntrySecurity": (SECURITY_COLUMNS, [[
                    "fixture.Handler.handle", "src/Handler.java", 20, "",
                    "src/Handler.java", 19, "annotation", "unauthenticated_annotation",
                    "complete", "permit_all",
                ], [
                    "fixture.Handler.handle", "src/Handler.java", 20, "",
                    "src/Handler.java", 18, "annotation", "privileged_annotation",
                    "partial", "role_requirement_not_proven_administrative",
                ], [
                    "fixture.Other.handle", "src/OtherController.java", 40, "",
                    "src/OtherController.java", 39, "annotation", "privileged_annotation",
                    "complete", "role_annotation",
                ], [
                    "fixture.Other.handle", "src/OtherController.java", 40, "",
                    "src/OtherController.java", 38, "dependency_coverage",
                    "unauthenticated_annotation", "complete",
                    "non_auth_kind_cannot_reclassify_entry",
                ]]),
                "GuardCandidates": (GUARD_COLUMNS, []),
                "BoundCandidates": (BOUND_COLUMNS, []),
                "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
                "LifecycleCoverage": (LIFECYCLE_COVERAGE_COLUMNS, []),
                "LifecycleSummary": (LIFECYCLE_SUMMARY_COLUMNS, []),
            }

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                query_calls.append(query.stem)
                if query.stem in rows_by_query:
                    columns, rows = rows_by_query[query.stem]
                else:
                    columns = SECURITY_COLUMNS if query.name == "EntrySecurity.ql" else INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else ENTRY_COLUMNS if query.parent.name == "Entries" else GROWTH_COLUMNS
                    rows = []
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._bqrs_payload(columns, rows)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            def fake_excerpt(checkout: Path, commit: str, path: str, line: int) -> SourceExcerpt:
                import hashlib
                excerpt_calls.append((checkout, commit, path, line))
                content = f"attested line {line}\n"
                return SourceExcerpt(
                    f"excerpt:{line}", path, line, line, content, "c" * 64,
                    hashlib.sha256(content.encode()).hexdigest(),
                )

            class FakeLlm:
                def classify_auth(self, entry_id: str, facts: object, configuration: object):
                    auth_llm_calls.append(entry_id)
                    from dosweb.reachability import AuthContract
                    auth_fact = next(
                        fact
                        for fact in tuple(facts)
                        if fact.value == "unauthenticated_annotation"
                    )
                    return AuthContract(
                        "unauthenticated", (auth_fact.fact_id,), (), "high"
                    )

                def classify_growth(self, bounded: object) -> GrowthContract:
                    llm_calls.append(bounded)
                    return _unknown_growth_contract()

            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
                deepseek_client=FakeLlm(),
                source_excerpt_fn=fake_excerpt,
            )
            result = pipeline.run("analyze")

            self.assertEqual(result["status"], "completed")
            self.assertTrue(all(result["stages"][stage]["status"] == "completed" for stage in STAGES))
            # The second public candidate is deliberately ordered after the
            # privileged Entry candidate. It must reuse the public Entry's
            # cached decision, not the previous loop iteration's decision.
            self.assertEqual(len(llm_calls), 2)
            entries_by_id = {
                item["entry_id"]: item
                for item in (
                    json.loads(line)
                    for line in (root / "output" / "entry_facts.jsonl").read_text().splitlines()
                )
            }
            entry_id_by_route = {
                item["route_or_event"]: entry_id
                for entry_id, item in entries_by_id.items()
            }
            self.assertEqual(auth_llm_calls, [entry_id_by_route["/items"]])
            auth_by_entry = {
                item["entry_id"]: item
                for item in (
                    json.loads(line)
                    for line in (root / "output" / "auth_contracts.jsonl").read_text().splitlines()
                )
            }
            reach_by_entry = {
                item["entry_id"]: item
                for item in (
                    json.loads(line)
                    for line in (root / "output" / "reachability_decisions.jsonl").read_text().splitlines()
                )
            }
            selectively_cited = entry_id_by_route["/items"]
            unique_privileged = entry_id_by_route["/other"]
            self.assertEqual(
                "unauthenticated", auth_by_entry[selectively_cited]["auth_context"]
            )
            self.assertEqual("unknown", reach_by_entry[selectively_cited]["auth_context"])
            self.assertEqual("unknown", reach_by_entry[selectively_cited]["status"])
            self.assertIn(
                "REACH_AUTH_COVERAGE_PARTIAL",
                reach_by_entry[selectively_cited]["reason_codes"],
            )
            self.assertEqual(
                "privileged", reach_by_entry[unique_privileged]["auth_context"]
            )
            self.assertEqual(
                "not_entry_reachable", reach_by_entry[unique_privileged]["status"]
            )
            self.assertEqual(len(excerpt_calls), 6)
            self.assertEqual({call[1] for call in excerpt_calls}, {None})
            self.assertEqual(
                {call[2:] for call in excerpt_calls},
                {
                    ("src/Handler.java", 8),
                    ("src/Handler.java", 20),
                    ("src/Handler.java", 24),
                    ("src/Handler.java", 26),
                },
            )
            self.assertEqual(result["stages"]["growth"]["metadata"]["candidate_count"], 5)
            self.assertEqual(result["stages"]["growth"]["metadata"]["mapped_candidate_count"], 2)
            self.assertEqual(result["stages"]["growth"]["metadata"]["inventory_unresolved_candidate_count"], 1)
            dispositions = [
                json.loads(line)
                for line in (root / "output" / "candidate_dispositions.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(dispositions), 5)
            self.assertEqual(sum(item["status"] == "rejected" for item in dispositions), 2)
            self.assertEqual(result["stages"]["growth"]["metadata"]["negative_proof_count"], 2)
            negative_proofs = [
                json.loads(line)
                for line in (root / "output" / "candidate_negative_proofs.jsonl").read_text().splitlines()
            ]
            proof_by_id = {
                item["negative_proof_id"]: item for item in negative_proofs
            }
            growth_by_id = {
                item["growth_id"]: item
                for item in (
                    json.loads(line)
                    for line in (root / "output" / "growth_candidates.jsonl").read_text().splitlines()
                )
            }
            for disposition in dispositions:
                if disposition["status"] == "rejected":
                    self.assertTrue(disposition["negative_proof_ids"])
                    for proof_id in disposition["negative_proof_ids"]:
                        proof = proof_by_id[proof_id]
                        self.assertEqual(disposition["growth_id"], proof["growth_id"])
                        self.assertTrue(
                            set(proof["evidence_ids"]).issubset(
                                growth_by_id[proof["growth_id"]]["candidate_evidence"]
                            )
                        )
            self.assertTrue(
                any(
                    proof["kind"] == "not_entry_reachable"
                    for proof in negative_proofs
                )
            )
            self.assertTrue(
                any(
                    "RELEVANCE_SERVER_SIZED_ALLOCATION" in item["reason_codes"]
                    for item in dispositions
                )
            )
            self.assertEqual(len(query_calls), 20)
            self.assertEqual(
                {item["path"] for item in result["stages"]["conclude"]["artifacts"]},
                {
                    "lifecycle_certificates.jsonl",
                    "static_findings.jsonl",
                    "finding_families.jsonl",
                },
            )
            self.assertEqual(
                {item["path"] for item in result["stages"]["report"]["artifacts"]},
                {"summary.json", "report.md"},
            )

    def test_full_production_graph_publishes_certificate_backed_unknown_when_lifecycle_absence_is_unproven(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "database").mkdir()
            source_file = root / "src" / "Handler.java"
            source_file.parent.mkdir()
            lines = ["// fixture"] * 30
            lines[0] = "import org.springframework.web.bind.annotation.PostMapping;"
            lines[7] = "@PostMapping(\"/items\")"
            lines[19] = "public void handle(byte[] body) {"
            lines[23] = "  byte[] materialized = body;"
            lines[25] = "}"
            source_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            info = DatabaseInfo(root / "database", root, "9" * 64)
            rows_by_query: dict[str, tuple[tuple[str, ...], list[list[object]]]] = {
                "SpringMvcEntries": (ENTRY_COLUMNS, [[
                    "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                    "annotation_mapping", "fixture.Handler", "src/Handler.java", 8, "/items",
                    "unauthenticated", "body", "byte[]", "request_body", "in_handler", "complete",
                    "spring_annotation_mapping",
                ]]),
                "InputMaterialization": (GROWTH_COLUMNS, [[
                    "src/Handler.java", 24, "input_materialization", "spring_request_body_materialization",
                    "bytes", "fixture.Handler.handle", "body", "body", "size", "request",
                    "fact:growth", "partial", "recognized_spring_request_body_bytes",
                ]]),
                "EntryToGrowth": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle", "entry>materialization", "data_flow", "proven",
                    "complete", "request_body_parameter_materialization",
                ]]),
                "EntryToGrowthAssociations": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "fixture.Handler.handle", "fixture.Handler.handle",
                    "fixture.Handler.handle", "entry>materialization", "data_flow", "proven",
                    "complete", "same_handler_request_body_materialization",
                ]]),
                "GuardCandidates": (GUARD_COLUMNS, []),
                "BoundCandidates": (BOUND_COLUMNS, []),
                "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
                "LifecycleCoverage": (LIFECYCLE_COVERAGE_COLUMNS, []),
                "LifecycleSummary": (LIFECYCLE_SUMMARY_COLUMNS, []),
            }

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                columns, rows = rows_by_query.get(
                    query.stem,
                    (SECURITY_COLUMNS if query.name == "EntrySecurity.ql" else INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else ENTRY_COLUMNS if query.parent.name == "Entries" else GROWTH_COLUMNS, []),
                )
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._bqrs_payload(columns, rows)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            def fake_excerpt(checkout: Path, commit: str, path: str, line: int) -> SourceExcerpt:
                import hashlib
                content = f"attested line {line}\n"
                return SourceExcerpt(
                    f"excerpt:{line}", path, line, line, content, "c" * 64,
                    hashlib.sha256(content.encode()).hexdigest(),
                )

            class FakeLlm:
                def classify_auth(self, entry_id: str, facts: object, configuration: object):
                    from dosweb.reachability import AuthContract
                    fact = tuple(facts)[0]
                    return AuthContract("unauthenticated", (fact.fact_id,), (), "high")

                def classify_growth(self, bounded: object) -> GrowthContract:
                    flow = next(
                        fact for fact in bounded.payload.static_facts
                        if fact.kind == "flow" and fact.relation == "flows_to"
                    )
                    sink = next(
                        fact for fact in bounded.payload.static_facts
                        if fact.kind == "input_materialization" and fact.relation == "sink"
                    )
                    value_space = next(
                        fact for fact in bounded.payload.static_facts
                        if fact.kind == "value_space"
                    )
                    retention = next(
                        fact for fact in bounded.payload.static_facts
                        if fact.kind == "retention"
                    )
                    amplification = next(
                        fact for fact in bounded.payload.static_facts
                        if fact.kind == "amplification"
                    )
                    return GrowthContract(
                        is_resource_growth="yes",
                        growth_kind="input_materialization",
                        resource_dimension="bytes",
                        attacker_influence=(AttackerInfluence("size", flow.fact_id),),
                        resource_effect="materializes_bytes",
                        attacker_variable="request body",
                        attacker_value_space="stream",
                        growth_unit="request bytes",
                        growth_function="request bytes are materialized",
                        amplification_class="large_single_request",
                        requests_to_pressure="one",
                        concurrency_model="one request",
                        retention_window="request",
                        failure_mechanism="heap_exhaustion",
                        failure_signal="request materialization exhausts heap",
                        required_static_evidence=(
                            sink.fact_id,
                            value_space.fact_id,
                            retention.fact_id,
                            amplification.fact_id,
                        ),
                        contract_status="dos_relevant",
                        rejection_reason="none",
                        confidence="high",
                    )

            resource_calls: list[str] = []

            def resource_provider(
                database: DatabaseInfo, _output: Path
            ):
                from dosweb.lifecycle.resource_properties import ResourceLifecycleCoverageGap

                resource_calls.append(database.fingerprint)
                raise ResourceLifecycleCoverageGap(
                    database_fingerprint=database.fingerprint,
                    source_snapshot_sha256="d" * 64,
                    implementation_sha256="e" * 64,
                )

            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
                resource_lifecycle_provider=resource_provider,
                resource_lifecycle_provider_identity="fixture-resource-v1",
                deepseek_client=FakeLlm(),
                source_excerpt_fn=fake_excerpt,
            )
            result = pipeline.run("analyze")
            self.assertEqual("completed", result["status"])
            # RC1 accepted-task population is irrelevant to byte
            # materialization, so the project-wide resource provider must not
            # run or inject an unrelated coverage gap.
            self.assertEqual([], resource_calls)
            self.assertTrue(
                (root / "output" / "resource_lifecycle_bindings.jsonl").is_file()
            )
            self.assertFalse(
                (root / "output" / "resource_lifecycle_facts.private.json").exists()
            )
            self.assertEqual(
                "",
                (root / "output" / "resource_lifecycle_bindings.jsonl")
                .read_text()
                .strip(),
            )
            disposition = json.loads(
                (root / "output" / "candidate_dispositions.jsonl").read_text().strip()
            )
            self.assertEqual("gap_eligible", disposition["status"])
            contracts = [
                json.loads(line)
                for line in (root / "output" / "growth_contracts.jsonl").read_text().splitlines()
            ]
            self.assertEqual(1, len(contracts))
            findings = json.loads((root / "output" / "static_findings.jsonl").read_text().strip())
            self.assertEqual("static_unknown", findings["verdict"])
            certificate = json.loads((root / "output" / "lifecycle_certificates.jsonl").read_text().strip())
            self.assertEqual(findings["certificate_id"], certificate["certificate_id"])
            self.assertEqual([], certificate["resource_lifecycle_decisions"])
            self.assertIn("VERDICT_UNRESOLVED_EVIDENCE", findings["reason_codes"])
            self.assertIn("VERDICT_CANDIDATE_RELEVANT_GAP", findings["reason_codes"])
            family = json.loads(
                (root / "output" / "finding_families.jsonl").read_text().strip()
            )
            self.assertEqual(family["verdict"], "static_unknown")
            self.assertEqual(family["member_finding_ids"], [findings["finding_id"]])
            self.assertEqual(
                family["member_certificate_ids"], [certificate["certificate_id"]]
            )
            self.assertEqual(family["amplification_class"], "large_single_request")
            self.assertIn("static_unknown", (root / "output" / "report.md").read_text())

    def test_bounded_resource_property_changes_formal_verdict_with_identical_raw_facts(self) -> None:
        rows_by_query: dict[str, tuple[tuple[str, ...], list[list[object]]]] = {
            "SpringMvcEntries": (ENTRY_COLUMNS, [[
                "spring_mvc", "http", "Fixture.handle",
                "src/main/java/Fixture.java", 2,
                "annotation_mapping", "Fixture",
                "src/main/java/Fixture.java", 1, "/submit",
                "unauthenticated", "count", "int", "request_parameter",
                "in_handler", "complete", "spring_annotation_mapping",
            ]]),
            "AsyncWorkGrowth": (GROWTH_COLUMNS, [[
                "src/main/java/Fixture.java", 3, "async_work_growth",
                "java.util.concurrent.Executor.execute", "tasks",
                "this.executor", "this.executor", "count",
                "submission_count", "instance", "async_submission", "complete",
                "queue_or_executor_capacity_requires_contract:attacker_controlled_loop_multiplicity_proven",
            ]]),
            "EntryToGrowth": (FLOW_COLUMNS, [[
                "src/main/java/Fixture.java", 2,
                "src/main/java/Fixture.java", 3,
                "submission_count", "count", "count", "Fixture.handle",
                "in_handler", "data_flow", "proven", "complete",
                "same_handler_call_graph_association",
            ]]),
            "EntryToGrowthAssociations": (FLOW_COLUMNS, [[
                "src/main/java/Fixture.java", 2,
                "src/main/java/Fixture.java", 3,
                "submission_count", "count", "count", "Fixture.handle",
                "in_handler", "data_flow", "proven", "complete",
                "same_handler_call_graph_association",
            ]]),
            "EntrySecurity": (SECURITY_COLUMNS, [[
                "Fixture.handle", "src/main/java/Fixture.java", 2, "",
                "src/main/java/Fixture.java", 1, "annotation",
                "unauthenticated_annotation", "complete", "permit_all",
            ]]),
            "GuardCandidates": (GUARD_COLUMNS, []),
            "BoundCandidates": (BOUND_COLUMNS, []),
            "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
            "LifecycleCoverage": (LIFECYCLE_COVERAGE_COLUMNS, [
                ["src/main/java/Fixture.java", 3, family, "complete", "exact_anchor_no_candidate"]
                for family in ("guard", "bound", "release")
            ]),
            "LifecycleSummary": (LIFECYCLE_SUMMARY_COLUMNS, []),
        }

        class FakeLlm:
            def classify_auth(self, entry_id: str, facts: object, configuration: object):
                from dosweb.reachability import AuthContract

                fact = tuple(facts)[0]
                return AuthContract("unauthenticated", (fact.fact_id,), (), "high")

            def classify_growth(self, bounded: object) -> GrowthContract:
                facts = tuple(bounded.payload.static_facts)
                flow = next(
                    fact for fact in facts
                    if fact.kind == "flow" and fact.relation == "flows_to"
                )
                sink = next(fact for fact in facts if fact.kind == "async_submission")
                value_space = next(fact for fact in facts if fact.kind == "value_space")
                retention = next(fact for fact in facts if fact.kind == "retention")
                amplification = next(fact for fact in facts if fact.kind == "amplification")
                return GrowthContract(
                    is_resource_growth="yes",
                    growth_kind="async_work_growth",
                    resource_dimension="tasks",
                    attacker_influence=(
                        AttackerInfluence("submission_count", flow.fact_id),
                    ),
                    resource_effect="enqueues_tasks",
                    attacker_variable="request count",
                    attacker_value_space="unlimited",
                    growth_unit="accepted tasks",
                    growth_function="request count controls task submissions",
                    amplification_class="queue_instability",
                    requests_to_pressure="one",
                    concurrency_model="bounded executor",
                    retention_window="process",
                    failure_mechanism="queue_latency_collapse",
                    failure_signal="accepted tasks exceed service rate",
                    required_static_evidence=(
                        sink.fact_id,
                        value_space.fact_id,
                        retention.fact_id,
                        amplification.fact_id,
                    ),
                    contract_status="dos_relevant",
                    rejection_reason="none",
                    confidence="high",
                )

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            provider_calls: list[tuple[str, bool]] = []

            def run_case(name: str, propagation_enabled: bool) -> Path:
                root = base / name
                (root / "database").mkdir(parents=True)
                source = root / "src/main/java/Fixture.java"
                source.parent.mkdir(parents=True)
                source.write_text(
                    "@PostMapping(\"/submit\")\n"
                    "void handle(int count) {\n"
                    "  this.executor.execute(task);\n"
                    "}\n",
                    encoding="utf-8",
                )
                info = DatabaseInfo(root / "database", root, "9" * 64)

                def fake_run(
                    query: Path,
                    _database: DatabaseInfo,
                    output_dir: Path,
                    **_kwargs: object,
                ) -> QueryResult:
                    columns, rows = rows_by_query.get(
                        query.stem,
                        (
                            SECURITY_COLUMNS
                            if query.name == "EntrySecurity.ql"
                            else INTERPOSITION_COLUMNS
                            if query.name == "EntryInterpositions.ql"
                            else ENTRY_COLUMNS
                            if query.parent.name == "Entries"
                            else GROWTH_COLUMNS,
                            [],
                        ),
                    )
                    decoded = output_dir / f"{query.stem}.json"
                    decoded.write_text(
                        json.dumps(self._bqrs_payload(columns, rows)),
                        encoding="utf-8",
                    )
                    return QueryResult(
                        query.name, query, query, decoded, "a" * 64, "b" * 64
                    )

                def fake_excerpt(
                    checkout: Path, commit: str, path: str, line: int
                ) -> SourceExcerpt:
                    import hashlib

                    content = f"attested line {line}\n"
                    return SourceExcerpt(
                        f"excerpt:{line}", path, line, line, content,
                        "c" * 64, hashlib.sha256(content.encode()).hexdigest(),
                    )

                def resource_provider(
                    database: DatabaseInfo, _output: Path
                ):
                    from tests.test_resource_lifecycle_production_bridge import _run

                    provider_calls.append((database.fingerprint, propagation_enabled))
                    return _run()

                pipeline = build_production_pipeline(
                    self._values(root, allow_remote_llm=True),
                    environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                    validate_database_fn=lambda *_args, **_kwargs: info,
                    run_query_fn=fake_run,
                    resource_lifecycle_provider=resource_provider,
                    resource_lifecycle_provider_identity="fixture-resource-v1",
                    resource_lifecycle_propagation_enabled=propagation_enabled,
                    deepseek_client=FakeLlm(),
                    source_excerpt_fn=fake_excerpt,
                )
                self.assertEqual("completed", pipeline.run("analyze")["status"])
                return root / "output"

            full = run_case("full", True)
            off = run_case("off", False)
            self.assertEqual(provider_calls, [("9" * 64, True), ("9" * 64, False)])
            for artifact in (
                "growth_candidates.jsonl",
                "flow_proofs.jsonl",
            ):
                self.assertEqual((full / artifact).read_bytes(), (off / artifact).read_bytes())
            for artifact in (
                "resource_lifecycle_facts.private.json",
                "resource_lifecycle_results.private.json",
            ):
                self.assertFalse((full / artifact).exists())
                self.assertFalse((off / artifact).exists())

            full_finding = json.loads((full / "static_findings.jsonl").read_text())
            off_finding = json.loads((off / "static_findings.jsonl").read_text())
            self.assertEqual(
                "bounded_under_modeled_assumptions",
                full_finding["verdict"],
                full_finding,
            )
            self.assertEqual("static_vulnerable", off_finding["verdict"])
            full_certificate = json.loads(
                (full / "lifecycle_certificates.jsonl").read_text()
            )
            self.assertEqual(
                "refutes_relevant_growth",
                full_certificate["resource_lifecycle_decisions"][0]["decision"]["status"],
            )
            self.assertEqual([], json.loads(
                (off / "lifecycle_certificates.jsonl").read_text()
            )["resource_lifecycle_decisions"])

    def test_lifecycle_decision_records_preserve_exact_boolean_checks_and_coverage(self) -> None:
        for decision in (
            GuardDecision("unknown", ("GUARD_CONFIGURATION_UNKNOWN",), (DecisionCheck("guard", False, "GUARD_CONFIGURATION_UNKNOWN", ("fact:g",)),), ("fact:g",), ("request.max",), ("guard:1",)),
            BoundDecision("effective", (), (DecisionCheck("bound", True, None, ("fact:b",)),), ("fact:b",), (), ("bound:1",)),
            ReleaseDecision("unknown", "potential_async", ("RELEASE_POTENTIAL_ASYNC",), (DecisionCheck("release", False, "RELEASE_POTENTIAL_ASYNC", ("fact:r",)),), ("fact:r",), ("consumer",), ("release:1",)),
        ):
            record = production._decision_record(decision)  # noqa: SLF001
            self.assertEqual([check["passed"] for check in record["checks"]], [item.passed for item in decision.checks])
            self.assertEqual(record["status"], decision.status)
            self.assertEqual(record["reason_codes"], list(decision.reason_codes))
            self.assertEqual(record["unresolved_facts"], list(decision.unresolved_facts))
        self.assertFalse(production._decision_record(ReleaseDecision("unknown", "potential_async", ("RELEASE_POTENTIAL_ASYNC",), (), (), ("consumer",), ())) ["checks"])  # noqa: SLF001

    def test_provider_failure_publishes_no_growth_or_downstream_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []

            def fail_growth(context: StageContext) -> StageOutput:
                calls.append(context.stage)
                if context.stage == "growth":
                    raise RuntimeError("provider failed")
                return StageOutput({f"{context.stage}.jsonl": [{"stage": context.stage}]})

            executors = {stage: fail_growth for stage in STAGES}
            pipeline = build_production_pipeline(self._values(root, allow_remote_llm=True), environ={"DEEPSEEK_API_KEY": "fixture-secret"}, stage_executors=executors)
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("analyze")
            self.assertEqual(raised.exception.code, "ANALYSIS_STAGE_FAILED")
            self.assertEqual(calls, ["entries", "growth"])
            output = root / "output"
            self.assertFalse((output / "growth.jsonl").exists())
            self.assertFalse((output / "flows.jsonl").exists())
            self.assertFalse((output / "lifecycle.jsonl").exists())
            self.assertFalse((output / "report.json").exists())
            run = json.loads((output / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["stages"]["growth"]["status"], "failed")
            self.assertEqual(run["stages"]["flows"]["status"], "pending")

    def test_production_resume_does_not_duplicate_injected_codeql_or_llm_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(self._values(root, allow_remote_llm=True), environ={"DEEPSEEK_API_KEY": "fixture-secret"}, stage_executors=self._fake_executors(calls))
            self.assertEqual(pipeline.run("analyze")["status"], "completed")
            resumed = build_production_pipeline({**self._values(root, allow_remote_llm=True), "resume": True}, environ={"DEEPSEEK_API_KEY": "fixture-secret"}, stage_executors=self._fake_executors(calls))
            self.assertEqual(resumed.run("analyze")["status"], "completed")
            self.assertEqual(calls, list(STAGES))

    def test_conclude_and_report_artifact_names_are_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(self._values(root, allow_remote_llm=True), environ={"DEEPSEEK_API_KEY": "fixture-secret"}, stage_executors=self._fake_executors(calls))
            result = pipeline.run("analyze")
            self.assertEqual(calls, list(STAGES))
            self.assertEqual({item["path"] for item in result["stages"]["conclude"]["artifacts"]}, {"conclude.jsonl"})
            self.assertEqual({item["path"] for item in result["stages"]["report"]["artifacts"]}, {"report.jsonl"})
            self.assertTrue((root / "output" / "run.json").is_file())
            self.assertEqual(result["stages"]["report"]["metadata"]["executor"], "fake")

    def test_cli_default_dispatch_uses_production_factory_and_preserves_stage_target(self) -> None:
        seen: list[tuple[dict[str, object], dict[str, str]]] = []

        class FakePipeline:
            def run(self, command: str) -> dict[str, str]:
                self.command = command
                return {"status": "completed"}

        def factory(values: dict[str, object], *, environ: dict[str, str] | None = None):
            seen.append((values, dict(environ or {})))
            return FakePipeline()

        with mock.patch("dosweb.production.build_production_pipeline", side_effect=factory):
            with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "cli-secret"}, clear=False):
                status = main(["report", "--database", "db", "--output", "out"])
        self.assertEqual(status, 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0]["command"], "report")
        self.assertEqual(seen[0][0]["database"], Path("db"))
        self.assertEqual(seen[0][1]["DEEPSEEK_API_KEY"], "cli-secret")

    def test_cli_parser_remains_parse_only_for_production_factory(self) -> None:
        values = parse_cli_values(["analyze", "--database", "db", "--output", "out"])
        self.assertEqual(values["command"], "analyze")
        self.assertIsNone(values["allow_remote_llm"])


if __name__ == "__main__":
    unittest.main()
