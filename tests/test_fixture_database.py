from __future__ import annotations

import ast
import fcntl
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from dosweb.codeql.database import DatabaseInfo
import dosweb.filesystem as filesystem
from tests.support import fixture_database as fixture_database_module


class FixtureDatabaseCacheTests(unittest.TestCase):
    def test_source_capture_stops_scandir_at_the_entry_bound_before_sorting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary) / "src"
            source_root.mkdir()
            for index in range(3):
                (source_root / f"ignored-{index}.txt").write_bytes(b"ignored\n")
            real_scandir = os.scandir
            consumed = 0

            class CountingScandir:
                def __init__(self, path: object) -> None:
                    self._entries = real_scandir(path)

                def __enter__(self) -> CountingScandir:
                    self._entries.__enter__()
                    return self

                def __exit__(self, *args: object) -> object:
                    return self._entries.__exit__(*args)

                def __iter__(self) -> CountingScandir:
                    return self

                def __next__(self) -> os.DirEntry[str]:
                    nonlocal consumed
                    consumed += 1
                    if consumed > 2:
                        raise AssertionError("fixture source scandir over-consumed")
                    return next(self._entries)

            with (
                mock.patch.object(
                    fixture_database_module,
                    "_MAX_TREE_ENTRIES",
                    1,
                ),
                mock.patch.object(
                    fixture_database_module.os,
                    "scandir",
                    side_effect=CountingScandir,
                ),
                self.assertRaisesRegex(
                    AssertionError,
                    "fixture exceeds 1 filesystem entries",
                ),
            ):
                fixture_database_module._bounded_java_sources(source_root)

            self.assertEqual(consumed, 2)

    def test_prepare_cache_root_never_uses_path_chmod_that_can_follow_a_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o755)
            outside = root / "outside"
            outside.mkdir(mode=0o755)
            outside_file = outside / "KEEP.bin"
            outside_bytes = b"outside cache substitute\n"
            outside_file.write_bytes(outside_bytes)
            held = root / "held-cache"
            real_chmod = Path.chmod
            path_chmod_called = False

            def swap_on_path_chmod(path: Path, mode: int) -> None:
                nonlocal path_chmod_called
                if path == cache_root and not path_chmod_called:
                    cache_root.rename(held)
                    cache_root.symlink_to(outside, target_is_directory=True)
                    path_chmod_called = True
                real_chmod(path, mode)

            with mock.patch.object(
                Path,
                "chmod",
                autospec=True,
                side_effect=swap_on_path_chmod,
            ):
                prepared = fixture_database_module._prepare_cache_root(cache_root)

            self.assertFalse(path_chmod_called)
            self.assertEqual(prepared, cache_root)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)
            self.assertEqual(outside_file.read_bytes(), outside_bytes)
            self.assertEqual(stat.S_IMODE(cache_root.stat().st_mode), 0o700)

    def test_prepare_cache_root_rejects_open_window_substitute_without_chmod(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o755)
            outside = root / "outside"
            outside.mkdir(mode=0o755)
            outside_file = outside / "KEEP.bin"
            outside_bytes = b"outside cache substitute\n"
            outside_file.write_bytes(outside_bytes)
            held = root / "held-cache"
            real_open = os.open
            swapped = False

            def swap_before_root_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                nonlocal swapped
                if (
                    os.fsdecode(path) == cache_root.name
                    and dir_fd is not None
                    and flags & getattr(os, "O_DIRECTORY", 0)
                    and not swapped
                ):
                    cache_root.rename(held)
                    cache_root.symlink_to(outside, target_is_directory=True)
                    swapped = True
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with (
                mock.patch.object(
                    fixture_database_module.os,
                    "open",
                    side_effect=swap_before_root_open,
                ),
                self.assertRaisesRegex(
                    AssertionError,
                    "fixture cache root changed before pinning",
                ),
            ):
                fixture_database_module._prepare_cache_root(cache_root)

            self.assertTrue(swapped)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)
            self.assertEqual(outside_file.read_bytes(), outside_bytes)

    def test_source_mutation_builds_a_new_content_addressed_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            source = source_root / "Fixture.java"
            source.write_text("class Fixture { int value() { return 1; } }\n")
            cache_root = root / "cache"
            builds: list[Path] = []
            source_roots_by_database: dict[Path, Path] = {}

            def fake_run(
                command: list[str],
                **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                database = Path(command[3])
                snapshot = Path(kwargs["cwd"]).resolve(strict=True)
                database.mkdir(parents=True)
                builds.append(database)
                source_roots_by_database[database] = snapshot
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                return DatabaseInfo(
                    database,
                    next(reversed(source_roots_by_database.values())),
                    "d" * 64,
                )

            with (
                mock.patch.object(fixture_database_module, "_CACHE_ROOT", cache_root),
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
            ):
                first = fixture_database_module.fixture_database(str(source_root))
                source.write_text("class Fixture { int value() { return 2; } }\n")
                second = fixture_database_module.fixture_database(str(source_root))

            self.assertNotEqual(first.path, second.path)
            self.assertEqual(len(builds), 2)

    def test_build_uses_private_snapshot_when_original_root_is_swapped_and_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            original = b"class Fixture { int value() { return 1; } }\n"
            (source_root / "Fixture.java").write_bytes(original)
            (source_root / "README.txt").write_text("not Java\n", encoding="utf-8")
            outside = root / "outside"
            outside.mkdir()
            (outside / "Escaped.java").write_text(
                "class Escaped {}\n", encoding="utf-8"
            )
            (source_root / "escaped").symlink_to(outside, target_is_directory=True)
            replacement = root / "replacement"
            replacement.mkdir()
            (replacement / "Fixture.java").write_text(
                "class Fixture { int value() { return 999; } }\n",
                encoding="utf-8",
            )
            cache_root = root / "cache"
            source_roots_by_database: dict[Path, Path] = {}

            def fake_run(
                command: list[str],
                **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                database = Path(command[3])
                snapshot = Path(kwargs["cwd"]).resolve(strict=True)
                self.assertNotEqual(Path(kwargs["cwd"]), source_root)
                self.assertEqual(Path(kwargs["cwd"]).resolve(strict=True), snapshot)
                self.assertTrue(snapshot.is_relative_to(cache_root))
                self.assertEqual(
                    {
                        path.relative_to(snapshot).as_posix(): path.read_bytes()
                        for path in snapshot.rglob("*")
                        if path.is_file()
                    },
                    {"Fixture.java": original},
                )

                original_away = root / "original-away"
                source_root.rename(original_away)
                replacement.rename(source_root)
                database.mkdir(parents=True)
                source_root.rename(replacement)
                original_away.rename(source_root)
                source_roots_by_database[database] = snapshot
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                snapshot = next(iter(source_roots_by_database.values()))
                return DatabaseInfo(database, snapshot, "d" * 64)

            with (
                mock.patch.object(fixture_database_module, "_CACHE_ROOT", cache_root),
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
            ):
                database = fixture_database_module.fixture_database(str(source_root))

            self.assertEqual((source_root / "Fixture.java").read_bytes(), original)
            self.assertTrue(database.source_root.is_relative_to(cache_root))
            self.assertEqual((database.source_root / "Fixture.java").read_bytes(), original)
            self.assertEqual(
                stat.S_IMODE(database.source_root.stat().st_mode),
                0o500,
            )
            self.assertEqual(
                stat.S_IMODE(
                    (database.source_root / "Fixture.java").stat().st_mode
                ),
                0o400,
            )
            self.assertFalse((database.source_root / "escaped").exists())
            self.assertFalse((database.source_root / "README.txt").exists())

    def test_transient_java_added_and_removed_during_build_is_not_consumed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            original = b"class Fixture { int value() { return 1; } }\n"
            (source_root / "Fixture.java").write_bytes(original)
            cache_root = root / "cache"
            source_roots_by_database: dict[Path, Path] = {}

            def fake_run(
                command: list[str],
                **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                database = Path(command[3])
                snapshot = Path(kwargs["cwd"]).resolve(strict=True)
                self.assertNotEqual(Path(kwargs["cwd"]), source_root)
                self.assertEqual(Path(kwargs["cwd"]).resolve(strict=True), snapshot)
                transient = source_root / "Transient.java"
                transient.write_text("class Transient {}\n", encoding="utf-8")
                try:
                    self.assertEqual(
                        sorted(
                            path.relative_to(snapshot).as_posix()
                            for path in snapshot.rglob("*.java")
                        ),
                        ["Fixture.java"],
                    )
                    self.assertEqual((snapshot / "Fixture.java").read_bytes(), original)
                    database.mkdir(parents=True)
                finally:
                    transient.unlink()
                source_roots_by_database[database] = snapshot
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                snapshot = next(iter(source_roots_by_database.values()))
                return DatabaseInfo(database, snapshot, "d" * 64)

            with (
                mock.patch.object(fixture_database_module, "_CACHE_ROOT", cache_root),
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
            ):
                database = fixture_database_module.fixture_database(str(source_root))

            self.assertFalse((source_root / "Transient.java").exists())
            self.assertEqual(
                sorted(
                    path.relative_to(database.source_root).as_posix()
                    for path in database.source_root.rglob("*.java")
                ),
                ["Fixture.java"],
            )

    def test_database_final_revalidation_failure_retains_owned_build_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            snapshot_root: Path | None = None
            validated_paths: list[Path] = []

            def fake_run(
                command: list[str],
                **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                nonlocal snapshot_root
                database = Path(command[3])
                snapshot_root = Path(kwargs["cwd"]).resolve(strict=True)
                database.mkdir(parents=True)
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                validated_paths.append(database)
                if len(validated_paths) == 2:
                    raise AssertionError("database final revalidation failed")
                assert snapshot_root is not None
                return DatabaseInfo(database, snapshot_root, "d" * 64)

            with (
                mock.patch.object(fixture_database_module, "_CACHE_ROOT", cache_root),
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
            ):
                with self.assertRaisesRegex(
                    AssertionError,
                    "database final revalidation failed",
                ):
                    fixture_database_module.fixture_database(str(source_root))

            self.assertEqual(len(validated_paths), 2)
            self.assertFalse(validated_paths[0].exists())
            self.assertFalse(validated_paths[1].exists())
            class_paths = [
                path for path in cache_root.iterdir() if ".classes" in path.name
            ]
            self.assertEqual(len(class_paths), 1)
            self.assertIn(".retained-", class_paths[0].name)
            self.assertEqual(stat.S_IMODE(class_paths[0].stat().st_mode), 0o700)

    def test_snapshot_final_revalidation_failure_retains_owned_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            validated_paths: list[Path] = []
            real_validate = fixture_database_module._validate_source_snapshot

            def fail_final_revalidation(path: Path, snapshot: object) -> None:
                validated_paths.append(path)
                if len(validated_paths) == 2:
                    raise AssertionError("snapshot final revalidation failed")
                real_validate(path, snapshot)

            with (
                mock.patch.object(fixture_database_module, "_CACHE_ROOT", cache_root),
                mock.patch.object(
                    fixture_database_module,
                    "_validate_source_snapshot",
                    side_effect=fail_final_revalidation,
                ),
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                ) as run,
            ):
                with self.assertRaisesRegex(
                    AssertionError,
                    "snapshot final revalidation failed",
                ):
                    fixture_database_module.fixture_database(str(source_root))

            run.assert_not_called()
            self.assertEqual(len(validated_paths), 2)
            self.assertFalse(validated_paths[0].exists())
            self.assertFalse(validated_paths[1].exists())

    def test_source_snapshot_never_renames_a_checked_directory_to_a_digest_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            real_no_replace = fixture_database_module.renameat2_no_replace
            publication_hook_calls = 0
            substitute_was_digest_alias = False

            def racing_no_replace(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal publication_hook_calls, substitute_was_digest_alias
                if destination_name == f"{snapshot.digest}.sources":
                    publication_hook_calls += 1
                    held_original = f".{source_name}.held-original"
                    os.rename(
                        source_name,
                        held_original,
                        src_dir_fd=source_directory_fd,
                        dst_dir_fd=source_directory_fd,
                    )
                    os.mkdir(source_name, mode=0o700, dir_fd=source_directory_fd)
                    substitute = os.stat(
                        source_name,
                        dir_fd=source_directory_fd,
                        follow_symlinks=False,
                    )
                    real_no_replace(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )
                    named = os.stat(
                        destination_name,
                        dir_fd=destination_directory_fd,
                        follow_symlinks=False,
                    )
                    substitute_was_digest_alias = (
                        named.st_dev,
                        named.st_ino,
                    ) == (
                        substitute.st_dev,
                        substitute.st_ino,
                    )
                    return
                real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            with mock.patch.object(
                fixture_database_module,
                "renameat2_no_replace",
                side_effect=racing_no_replace,
            ):
                stable = fixture_database_module._ensure_source_snapshot(
                    cache_root,
                    snapshot,
                )

            self.assertEqual(publication_hook_calls, 0)
            self.assertFalse(substitute_was_digest_alias)
            self.assertRegex(
                stable.name,
                rf"^{snapshot.digest}\.sources-[0-9a-f]{{32}}$",
            )
            self.assertFalse((cache_root / f"{snapshot.digest}.sources").exists())

    def test_fresh_processes_reuse_the_same_stable_snapshot_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            project_root = Path(__file__).resolve().parents[1]
            script = "\n".join(
                [
                    "from pathlib import Path",
                    "from tests.support.fixture_database import (",
                    "    _bounded_java_sources, _digest_lock,",
                    "    _ensure_source_snapshot, _prepare_cache_root,",
                    ")",
                    f"source_root = Path({str(source_root)!r})",
                    f"cache_root = _prepare_cache_root(Path({str(cache_root)!r}))",
                    "snapshot = _bounded_java_sources(source_root)",
                    "with _digest_lock(cache_root, snapshot.digest):",
                    "    print(_ensure_source_snapshot(cache_root, snapshot))",
                ]
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                value
                for value in (
                    str(project_root),
                    environment.get("PYTHONPATH", ""),
                )
                if value
            )

            paths = []
            for _attempt in range(2):
                completed = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=project_root,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                paths.append(Path(completed.stdout.strip()))

            self.assertEqual(paths[0], paths[1])
            self.assertRegex(
                paths[0].name,
                r"^[0-9a-f]{64}\.sources-[0-9a-f]{32}$",
            )
            self.assertEqual(
                len(tuple(cache_root.glob("*.sources-*"))),
                1,
            )

    def test_snapshot_candidate_scan_rejects_invalid_matching_candidate_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            invalid = cache_root / f"{snapshot.digest}.sources-{'0' * 32}"
            invalid.mkdir(mode=0o700)
            descriptor = os.open(
                invalid,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            invalid.chmod(0o000)
            before = os.fstat(descriptor)
            try:
                with self.assertRaisesRegex(
                    AssertionError,
                    "source snapshot candidate is invalid",
                ):
                    fixture_database_module._ensure_source_snapshot(
                        cache_root,
                        snapshot,
                    )

                after = os.fstat(descriptor)
                self.assertEqual(
                    (after.st_dev, after.st_ino, after.st_nlink),
                    (before.st_dev, before.st_ino, before.st_nlink),
                )
                self.assertEqual(stat.S_IMODE(after.st_mode), 0o000)
                self.assertEqual(os.listdir(descriptor), [])
            finally:
                os.close(descriptor)

    def test_legacy_digest_aliases_and_staging_names_are_not_legal_cleanup_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_root = Path(temporary) / "cache"
            cache_root.mkdir(mode=0o700)
            obsolete_names = (
                f"{'a' * 64}.sources",
                f"{'a' * 64}.db",
                f".{'a' * 64}.sources.tmp-obsolete",
                f".{'a' * 64}.db.tmp-obsolete",
            )
            for name in obsolete_names:
                with self.subTest(name=name):
                    legacy = cache_root / name
                    legacy.mkdir(mode=0o700)
                    descriptor = os.open(
                        legacy,
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                    )
                    before = os.fstat(descriptor)
                    try:
                        with self.assertRaisesRegex(
                            AssertionError,
                            "refusing to clean non-fixture cache path",
                        ):
                            fixture_database_module._remove_helper_owned_cache_path(
                                legacy,
                                cache_root,
                            )

                        after = os.fstat(descriptor)
                        self.assertEqual(
                            (after.st_dev, after.st_ino, after.st_nlink),
                            (before.st_dev, before.st_ino, before.st_nlink),
                        )
                        self.assertTrue(legacy.exists())
                    finally:
                        os.close(descriptor)

    def test_snapshot_candidate_scan_is_bounded_before_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            for index in range(9):
                (cache_root / f"{snapshot.digest}.sources-{index:032x}").mkdir(
                    mode=0o700
                )

            with self.assertRaisesRegex(
                AssertionError,
                "source snapshot candidate count bound exceeded",
            ):
                fixture_database_module._ensure_source_snapshot(
                    cache_root,
                    snapshot,
                )

    def test_snapshot_cache_root_scan_has_a_hard_entry_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            for index in range(3):
                (cache_root / f"unrelated-{index}").write_bytes(b"")

            with (
                mock.patch.object(
                    fixture_database_module,
                    "_MAX_CACHE_ROOT_ENTRIES",
                    2,
                    create=True,
                ),
                self.assertRaisesRegex(
                    AssertionError,
                    "fixture cache candidate scan entry bound exceeded",
                ),
            ):
                fixture_database_module._ensure_source_snapshot(
                    cache_root,
                    snapshot,
                )

    def test_snapshot_candidate_selection_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            source_bytes = b"class Fixture {}\n"
            (source_root / "Fixture.java").write_bytes(source_bytes)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            candidates = [
                cache_root / f"{snapshot.digest}.sources-{'f' * 32}",
                cache_root / f"{snapshot.digest}.sources-{'0' * 32}",
            ]
            for candidate in candidates:
                candidate.mkdir(mode=0o700)
                fixture = candidate / "Fixture.java"
                fixture.write_bytes(source_bytes)
                fixture.chmod(0o400)
                candidate.chmod(0o500)

            selected = fixture_database_module._ensure_source_snapshot(
                cache_root,
                snapshot,
            )

            self.assertEqual(selected, candidates[1])

    def test_snapshot_candidate_tree_validation_streams_with_an_entry_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            source_bytes = b"class Fixture {}\n"
            (source_root / "Fixture.java").write_bytes(source_bytes)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            candidate = cache_root / f"{snapshot.digest}.sources-{'0' * 32}"
            candidate.mkdir(mode=0o700)
            fixture = candidate / "Fixture.java"
            fixture.write_bytes(source_bytes)
            fixture.chmod(0o400)
            extra = candidate / "Z-extra.java"
            extra.write_bytes(b"class Extra {}\n")
            extra.chmod(0o400)
            candidate.chmod(0o500)

            with (
                mock.patch.object(
                    fixture_database_module,
                    "_MAX_TREE_ENTRIES",
                    1,
                ),
                self.assertRaisesRegex(
                    AssertionError,
                    "source snapshot validation entry bound exceeded",
                ),
            ):
                fixture_database_module._validate_source_snapshot(
                    candidate,
                    snapshot,
                )

    def test_database_build_never_renames_a_checked_directory_to_a_digest_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            immutable_source = fixture_database_module._ensure_source_snapshot(
                cache_root,
                snapshot,
            )
            real_no_replace = fixture_database_module.renameat2_no_replace
            publication_hook_calls = 0
            substitute_was_digest_alias = False
            commands: list[list[str]] = []

            def fake_run(
                command: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                Path(command[3]).mkdir(parents=True)
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                return DatabaseInfo(database, immutable_source, "d" * 64)

            def racing_no_replace(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal publication_hook_calls, substitute_was_digest_alias
                if destination_name == f"{snapshot.digest}.db":
                    publication_hook_calls += 1
                    held_original = f".{source_name}.held-original"
                    os.rename(
                        source_name,
                        held_original,
                        src_dir_fd=source_directory_fd,
                        dst_dir_fd=source_directory_fd,
                    )
                    os.mkdir(source_name, mode=0o700, dir_fd=source_directory_fd)
                    substitute = os.stat(
                        source_name,
                        dir_fd=source_directory_fd,
                        follow_symlinks=False,
                    )
                    real_no_replace(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )
                    named = os.stat(
                        destination_name,
                        dir_fd=destination_directory_fd,
                        follow_symlinks=False,
                    )
                    substitute_was_digest_alias = (
                        named.st_dev,
                        named.st_ino,
                    ) == (
                        substitute.st_dev,
                        substitute.st_ino,
                    )
                    return
                real_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            with (
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "renameat2_no_replace",
                    side_effect=racing_no_replace,
                ),
            ):
                database = fixture_database_module._build_database(
                    cache_root,
                    snapshot,
                    immutable_source,
                )

            self.assertEqual(publication_hook_calls, 0)
            self.assertFalse(substitute_was_digest_alias)
            self.assertRegex(
                database.path.name,
                rf"^{snapshot.digest}\.db-[0-9a-f]{{32}}$",
            )
            self.assertFalse((cache_root / f"{snapshot.digest}.db").exists())
            self.assertEqual(len(commands), 1)
            self.assertNotIn("--overwrite", commands[0])

    def test_classes_directory_swap_fails_closed_without_touching_substitute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            immutable_source = fixture_database_module._ensure_source_snapshot(
                cache_root,
                snapshot,
            )
            outside = root / "outside"
            outside.mkdir(mode=0o755)
            outside_file = outside / "KEEP.bin"
            outside_bytes = b"classes substitute must stay unchanged\n"
            outside_file.write_bytes(outside_bytes)
            outside_file.chmod(0o400)
            outside_mode = stat.S_IMODE(outside.stat().st_mode)
            outside_file_mode = stat.S_IMODE(outside_file.stat().st_mode)
            held_original = root / "held-classes"
            real_chmod = Path.chmod
            real_open = os.open
            swapped = False

            def is_classes_name(value: object) -> bool:
                return re.fullmatch(
                    rf"\.{snapshot.digest}\.classes\.tmp-[A-Za-z0-9_-]+",
                    os.path.basename(os.fsdecode(value)),
                ) is not None

            def install_substitute(classes: Path) -> None:
                nonlocal swapped
                classes.rename(held_original)
                classes.symlink_to(outside, target_is_directory=True)
                swapped = True

            def swap_on_path_chmod(path: Path, mode: int) -> None:
                if path.parent == cache_root and is_classes_name(path) and not swapped:
                    install_substitute(path)
                real_chmod(path, mode)

            def swap_before_descriptor_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                if (
                    dir_fd is not None
                    and flags & getattr(os, "O_DIRECTORY", 0)
                    and is_classes_name(path)
                    and not swapped
                ):
                    install_substitute(cache_root / os.fsdecode(path))
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            def fake_run(
                command: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                Path(command[3]).mkdir(parents=True)
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                return DatabaseInfo(database, immutable_source, "d" * 64)

            with (
                mock.patch.object(
                    Path,
                    "chmod",
                    autospec=True,
                    side_effect=swap_on_path_chmod,
                ),
                mock.patch.object(
                    fixture_database_module.os,
                    "open",
                    side_effect=swap_before_descriptor_open,
                ),
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
                self.assertRaises(AssertionError) as raised,
            ):
                fixture_database_module._build_database(
                    cache_root,
                    snapshot,
                    immutable_source,
                )

            self.assertTrue(swapped)
            self.assertTrue(held_original.is_dir())
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), outside_mode)
            self.assertEqual(
                stat.S_IMODE(outside_file.stat().st_mode),
                outside_file_mode,
            )
            self.assertEqual(outside_file.read_bytes(), outside_bytes)
            self.assertRegex(str(raised.exception), "fixture classes directory")

    def test_javac_output_uses_inherited_pinned_classes_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            immutable_source = fixture_database_module._ensure_source_snapshot(
                cache_root,
                snapshot,
            )
            observed_classes: Path | None = None

            def fake_run(
                command: list[str],
                **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                nonlocal observed_classes
                javac = shlex.split(
                    next(
                        item.removeprefix("--command=")
                        for item in command
                        if item.startswith("--command=")
                    )
                )
                classes_fd_path = Path(javac[javac.index("-d") + 1])
                descriptor_match = re.fullmatch(
                    r"/proc/(?P<pid>\d+)/fd/(?P<fd>\d+)",
                    str(classes_fd_path),
                )
                self.assertIsNotNone(descriptor_match)
                assert descriptor_match is not None
                self.assertEqual(int(descriptor_match.group("pid")), os.getpid())
                source_fd = int(str(kwargs["cwd"]).rsplit("/", 1)[1])
                classes_fd = int(descriptor_match.group("fd"))
                self.assertEqual(
                    tuple(kwargs["pass_fds"]),
                    (source_fd, classes_fd),
                )
                probe = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; import sys; "
                            "path = Path(sys.argv[1]); "
                            "assert path.is_dir(); print(path.resolve(strict=True))"
                        ),
                        str(classes_fd_path),
                    ],
                    close_fds=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                probe_stdout, probe_stderr = probe.communicate(timeout=10)
                self.assertEqual(probe.returncode, 0, probe_stderr)
                observed_classes = classes_fd_path.resolve(strict=True)
                self.assertEqual(
                    Path(probe_stdout.strip()),
                    observed_classes,
                )
                self.assertEqual(observed_classes.parent, cache_root)
                self.assertTrue(observed_classes.is_dir())
                Path(command[3]).mkdir(parents=True)
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                return DatabaseInfo(database, immutable_source, "d" * 64)

            with (
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
            ):
                fixture_database_module._build_database(
                    cache_root,
                    snapshot,
                    immutable_source,
                )

            self.assertIsNotNone(observed_classes)

    def test_classes_cache_root_owned_open_return_interrupt_releases_descriptor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_root = Path(temporary) / "cache"
            cache_root.mkdir(mode=0o700)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            pinned = None
            classes_owner: list[
                fixture_database_module._PinnedClassesDirectory
            ] = []
            injected = False

            def interrupt_owned_open_return(frame, event, _arg):
                nonlocal injected
                if (
                    not injected
                    and event == "return"
                    and frame.f_code is filesystem.open_owned_descriptor.__code__
                    and Path(frame.f_locals.get("path", "")) == cache_root
                ):
                    injected = True
                    raise KeyboardInterrupt(
                        "classes cache-root owned-open return interrupted"
                    )

            sys.setprofile(interrupt_owned_open_return)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    pinned = fixture_database_module._open_pinned_classes_directory(
                        cache_root,
                        "a" * 64,
                        owner_holder=classes_owner,
                    )
            finally:
                sys.setprofile(None)
                try:
                    fixture_database_module._cleanup_pinned_classes_owner_slot(
                        classes_owner
                    )
                finally:
                    fixture_database_module._cleanup_pinned_classes_owner_slot(
                        classes_owner
                    )
            self.assertTrue(injected)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_build_database_classes_factory_return_interrupt_cleans_caller_owner_slot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            immutable_source = fixture_database_module._ensure_source_snapshot(
                cache_root,
                snapshot,
            )
            baseline_fds = len(os.listdir("/proc/self/fd"))
            captured: list[fixture_database_module._PinnedClassesDirectory] = []
            injected = False

            def interrupt_classes_factory_return(frame, event, result):
                nonlocal injected
                if (
                    not injected
                    and event == "return"
                    and frame.f_code
                    is fixture_database_module._open_pinned_classes_directory.__code__
                ):
                    injected = True
                    if isinstance(
                        result,
                        fixture_database_module._PinnedClassesDirectory,
                    ):
                        captured.append(result)
                    raise KeyboardInterrupt(
                        "classes factory return event interrupted"
                    )

            try:
                sys.setprofile(interrupt_classes_factory_return)
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        fixture_database_module._build_database(
                            cache_root,
                            snapshot,
                            immutable_source,
                        )
                finally:
                    sys.setprofile(None)

                self.assertTrue(injected)
                self.assertEqual(len(captured), 1)
                self.assertEqual(
                    len(os.listdir("/proc/self/fd")),
                    baseline_fds,
                )
                legal_classes = [
                    candidate
                    for candidate in cache_root.iterdir()
                    if fixture_database_module._CACHE_NAME.fullmatch(
                        candidate.name
                    )
                    and ".classes.tmp-" in candidate.name
                ]
                self.assertEqual(legal_classes, [])
                retained_classes = [
                    candidate
                    for candidate in cache_root.iterdir()
                    if ".classes.tmp-" in candidate.name
                ]
                for candidate in retained_classes:
                    self.assertIsNotNone(
                        fixture_database_module._RETAINED_CACHE_NAME.fullmatch(
                            candidate.name
                        )
                    )
                    info = candidate.lstat()
                    self.assertTrue(stat.S_ISDIR(info.st_mode))
                    self.assertEqual(info.st_uid, os.getuid())
                    self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)
            finally:
                sys.setprofile(None)
                for pinned in captured:
                    if pinned.descriptor_owner or pinned.cache_root_owner:
                        fixture_database_module._cleanup_pinned_classes_directory(
                            pinned
                        )

    def test_classes_cache_root_sigint_after_structural_acquisition_releases_descriptor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_root = Path(temporary) / "cache"
            cache_root.mkdir(mode=0o700)
            baseline_fds = len(os.listdir("/proc/self/fd"))
            pinned = None
            classes_owner: list[
                fixture_database_module._PinnedClassesDirectory
            ] = []
            injected = False

            def interrupt_after_owner_commit(frame, event, _arg):
                nonlocal injected
                owner = frame.f_locals.get("cache_root_owner")
                if (
                    not injected
                    and event == "line"
                    and frame.f_code
                    is fixture_database_module._open_pinned_classes_directory.__code__
                    and isinstance(owner, list)
                    and owner
                    and owner[0] >= 0
                ):
                    injected = True
                    os.kill(os.getpid(), signal.SIGINT)
                return interrupt_after_owner_commit

            sys.settrace(interrupt_after_owner_commit)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    pinned = fixture_database_module._open_pinned_classes_directory(
                        cache_root,
                        "b" * 64,
                        owner_holder=classes_owner,
                    )
            finally:
                sys.settrace(None)
                try:
                    fixture_database_module._cleanup_pinned_classes_owner_slot(
                        classes_owner
                    )
                finally:
                    fixture_database_module._cleanup_pinned_classes_owner_slot(
                        classes_owner
                    )
            self.assertTrue(injected)
            self.assertEqual(len(os.listdir("/proc/self/fd")), baseline_fds)

    def test_classes_release_return_interrupt_does_not_reclose_aba_fd(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_root = Path(temporary) / "cache"
            cache_root.mkdir(mode=0o700)
            classes_owner: list[
                fixture_database_module._PinnedClassesDirectory
            ] = []
            pinned = fixture_database_module._open_pinned_classes_directory(
                cache_root,
                "c" * 64,
                owner_holder=classes_owner,
            )
            classes_descriptor = pinned.descriptor
            replacement = -1
            injected = False

            def interrupt_release_return(frame, event, _arg):
                nonlocal injected, replacement
                if (
                    not injected
                    and event == "return"
                    and frame.f_code
                    is filesystem.release_owned_descriptor_once.__code__
                    and frame.f_locals.get("descriptor")
                    == classes_descriptor
                ):
                    injected = True
                    replacement = os.open("/dev/null", os.O_RDONLY)
                    raise KeyboardInterrupt(
                        "classes release return interrupted"
                    )

            try:
                sys.setprofile(interrupt_release_return)
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        fixture_database_module._cleanup_pinned_classes_owner_slot(
                            classes_owner
                        )
                finally:
                    sys.setprofile(None)
                self.assertTrue(injected)
                self.assertEqual(replacement, classes_descriptor)
                os.fstat(replacement)
                with self.assertRaises(OSError):
                    os.fstat(pinned.cache_root_descriptor)
            finally:
                sys.setprofile(None)
                try:
                    fixture_database_module._cleanup_pinned_classes_owner_slot(
                        classes_owner
                    )
                finally:
                    fixture_database_module._cleanup_pinned_classes_owner_slot(
                        classes_owner
                    )
                if replacement >= 0:
                    try:
                        os.close(replacement)
                    except OSError:
                        pass
                for descriptor in (
                    pinned.descriptor,
                    pinned.cache_root_descriptor,
                ):
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_classes_directory_acquisition_and_release_are_structurally_owned(
        self,
    ) -> None:
        module = ast.parse(
            Path(fixture_database_module.__file__).read_text(encoding="utf-8")
        )
        functions = {
            node.name: node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef)
        }
        factory = functions["_open_pinned_classes_directory"]
        direct_opens = [
            call
            for call in ast.walk(factory)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "os"
            and call.func.attr == "open"
        ]
        owned_opens = [
            call
            for call in ast.walk(factory)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "open_owned_descriptor"
        ]
        self.assertEqual(direct_opens, [])
        self.assertEqual(len(owned_opens), 2)

        parents = {
            child: parent
            for parent in ast.walk(module)
            for child in ast.iter_child_nodes(parent)
        }

        def owner(candidate: ast.AST) -> str | None:
            current = parents.get(candidate)
            while current is not None:
                if isinstance(current, ast.FunctionDef):
                    return current.name
                current = parents.get(current)
            return None

        def release_calls(candidate: ast.AST) -> list[ast.Call]:
            return [
                call
                for call in ast.walk(candidate)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id
                == "_release_fixture_descriptor_owner_must_reach"
            ]

        all_calls = release_calls(module)
        paired: list[ast.Call] = []
        pair_owners: list[str | None] = []
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
                for call in release_calls(statement)
            ]
            final_calls = [
                call
                for statement in candidate.finalbody
                for call in release_calls(statement)
            ]
            if len(body_calls) != 1 or len(final_calls) != 1:
                continue
            if ast.dump(
                body_calls[0], include_attributes=False
            ) != ast.dump(final_calls[0], include_attributes=False):
                continue
            paired.extend((body_calls[0], final_calls[0]))
            pair_owners.append(owner(candidate))
        self.assertEqual(len(all_calls), 8)
        self.assertEqual(
            {id(call) for call in all_calls},
            {id(call) for call in paired},
        )
        self.assertEqual(
            sorted(pair_owners),
            sorted(
                [
                "_open_pinned_classes_directory",
                "_open_pinned_classes_directory",
                "_cleanup_pinned_classes_directory",
                "_cleanup_pinned_classes_directory",
                ]
            ),
        )

        self.assertEqual(
            [argument.arg for argument in factory.args.kwonlyargs],
            ["owner_holder"],
        )
        transfer = next(
            node
            for node in ast.walk(factory)
            if isinstance(node, ast.FunctionDef)
            and node.name == "transfer_to_caller"
        )
        transfer_appends = [
            call
            for call in ast.walk(transfer)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "owner_holder"
            and call.func.attr == "append"
        ]
        self.assertEqual(len(transfer_appends), 1)

        build = functions["_build_database"]
        factory_calls = [
            call
            for call in ast.walk(build)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_open_pinned_classes_directory"
        ]
        self.assertEqual(len(factory_calls), 1)
        owner_keywords = [
            keyword
            for keyword in factory_calls[0].keywords
            if keyword.arg == "owner_holder"
        ]
        self.assertEqual(len(owner_keywords), 1)
        self.assertIsInstance(owner_keywords[0].value, ast.Name)
        self.assertEqual(owner_keywords[0].value.id, "classes_owner")

        def slot_cleanup_calls(candidate: ast.AST) -> list[ast.Call]:
            return [
                call
                for call in ast.walk(candidate)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "_cleanup_pinned_classes_owner_slot"
            ]

        slot_calls = slot_cleanup_calls(build)
        slot_pairs: list[ast.Call] = []
        for candidate in ast.walk(build):
            if (
                not isinstance(candidate, ast.Try)
                or candidate.handlers
                or candidate.orelse
            ):
                continue
            body_calls = [
                call
                for statement in candidate.body
                for call in slot_cleanup_calls(statement)
            ]
            final_calls = [
                call
                for statement in candidate.finalbody
                for call in slot_cleanup_calls(statement)
            ]
            if (
                len(body_calls) == 1
                and len(final_calls) == 1
                and ast.dump(body_calls[0], include_attributes=False)
                == ast.dump(final_calls[0], include_attributes=False)
            ):
                slot_pairs.extend((body_calls[0], final_calls[0]))
        self.assertEqual(len(slot_calls), 4)
        self.assertEqual(
            {id(call) for call in slot_calls},
            {id(call) for call in slot_pairs},
        )

    def test_fresh_processes_reuse_the_same_stable_snapshot_and_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            build_count = root / "build-count.txt"
            project_root = Path(__file__).resolve().parents[1]
            script = "\n".join(
                [
                    "from pathlib import Path",
                    "import subprocess",
                    "from unittest import mock",
                    "from dosweb.codeql.database import DatabaseInfo",
                    "from tests.support import fixture_database as fixture_module",
                    f"source_root = Path({str(source_root)!r})",
                    f"cache_root = Path({str(cache_root)!r})",
                    f"build_count = Path({str(build_count)!r})",
                    "def fake_run(command, **kwargs):",
                    "    database = Path(command[3])",
                    "    database.mkdir(mode=0o700)",
                    "    private_source = Path(kwargs['cwd']).resolve(strict=True)",
                    "    (database / 'source-root.txt').write_text(str(private_source), encoding='utf-8')",
                    "    with build_count.open('a', encoding='utf-8') as stream:",
                    "        stream.write('build\\n')",
                    "    return subprocess.CompletedProcess(command, 0, '', '')",
                    "def fake_validate(database):",
                    "    private_source = Path(database, 'source-root.txt').read_text(encoding='utf-8')",
                    "    return DatabaseInfo(Path(database), Path(private_source), 'd' * 64)",
                    "with (",
                    "    mock.patch.object(fixture_module, '_CACHE_ROOT', cache_root),",
                    "    mock.patch.object(fixture_module.subprocess, 'run', side_effect=fake_run),",
                    "    mock.patch.object(fixture_module, 'validate_database', side_effect=fake_validate),",
                    "):",
                    "    info = fixture_module.fixture_database(str(source_root))",
                    "print(f'{info.path}\\t{info.source_root}')",
                ]
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                value
                for value in (
                    str(project_root),
                    environment.get("PYTHONPATH", ""),
                )
                if value
            )

            results: list[tuple[Path, Path]] = []
            for _attempt in range(2):
                completed = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=project_root,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                database_text, source_text = completed.stdout.strip().split("\t")
                results.append((Path(database_text), Path(source_text)))

            self.assertEqual(results[0], results[1])
            self.assertRegex(
                results[0][0].name,
                r"^[0-9a-f]{64}\.db-[0-9a-f]{32}$",
            )
            self.assertRegex(
                results[0][1].name,
                r"^[0-9a-f]{64}\.sources-[0-9a-f]{32}$",
            )
            self.assertEqual(build_count.read_text(encoding="utf-8"), "build\n")

    def test_invalid_database_candidate_fails_closed_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            immutable_source = fixture_database_module._ensure_source_snapshot(
                cache_root,
                snapshot,
            )
            invalid = cache_root / f"{snapshot.digest}.db-{'0' * 32}"
            invalid.mkdir(mode=0o700)
            descriptor = os.open(
                invalid,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            before = os.fstat(descriptor)

            try:
                with (
                    mock.patch.object(
                        fixture_database_module,
                        "validate_database",
                        side_effect=AssertionError("malformed database"),
                    ),
                    mock.patch.object(
                        fixture_database_module.subprocess,
                        "run",
                    ) as run,
                    self.assertRaisesRegex(
                        AssertionError,
                        "fixture database candidate is invalid",
                    ),
                ):
                    fixture_database_module._build_database(
                        cache_root,
                        snapshot,
                        immutable_source,
                    )

                run.assert_not_called()
                after = os.fstat(descriptor)
                self.assertEqual(
                    (after.st_dev, after.st_ino, after.st_nlink),
                    (before.st_dev, before.st_ino, before.st_nlink),
                )
                self.assertEqual(stat.S_IMODE(after.st_mode), 0o700)
                self.assertTrue(invalid.exists())
            finally:
                os.close(descriptor)

    def test_temporary_snapshot_substitute_is_never_chmoded_or_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = fixture_database_module._bounded_java_sources(source_root)
            real_materialize = fixture_database_module._materialize_source_snapshot
            substitute = cache_root / ".substitute"
            substitute.mkdir(mode=0o700)
            substitute_descriptor = os.open(
                substitute,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            substitute.chmod(0o000)
            substitute_identity = os.fstat(substitute_descriptor)
            swapped = False

            def swap_before_materialization(*args: object, **kwargs: object) -> None:
                nonlocal swapped
                temporary_snapshot = Path(args[0])
                held_original = cache_root / (
                    f".{snapshot.digest}.sources.tmp-held-original"
                )
                temporary_snapshot.rename(held_original)
                substitute.rename(temporary_snapshot)
                swapped = True
                real_materialize(*args, **kwargs)

            try:
                with mock.patch.object(
                    fixture_database_module,
                    "_materialize_source_snapshot",
                    side_effect=swap_before_materialization,
                ):
                    try:
                        fixture_database_module._ensure_source_snapshot(
                            cache_root,
                            snapshot,
                        )
                    except (AssertionError, OSError):
                        pass

                self.assertTrue(swapped)
                current = os.fstat(substitute_descriptor)
                self.assertEqual(
                    (current.st_dev, current.st_ino),
                    (substitute_identity.st_dev, substitute_identity.st_ino),
                )
                self.assertEqual(stat.S_IMODE(current.st_mode), 0o000)
                self.assertEqual(current.st_nlink, substitute_identity.st_nlink)
                self.assertEqual(os.listdir(substitute_descriptor), [])
            finally:
                os.close(substitute_descriptor)

    def test_digest_lock_rejects_name_swap_before_nested_lock_can_enter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_root = Path(temporary) / "cache"
            cache_root.mkdir(mode=0o700)
            digest = "a" * 64
            lock_path = cache_root / f"{digest}.lock"
            held_lock = cache_root / f".{digest}.lock-held"
            real_flock = fcntl.flock
            swapped = False
            nested_entered = False

            def swap_after_outer_flock(descriptor: int, operation: int) -> None:
                nonlocal swapped
                real_flock(descriptor, operation)
                if operation == fcntl.LOCK_EX and not swapped:
                    lock_path.rename(held_lock)
                    replacement = os.open(
                        lock_path,
                        os.O_RDWR
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_CLOEXEC", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )
                    os.close(replacement)
                    swapped = True

            with mock.patch.object(
                fixture_database_module.fcntl,
                "flock",
                side_effect=swap_after_outer_flock,
            ):
                with self.assertRaisesRegex(
                    AssertionError,
                    "cache lock changed after flock",
                ):
                    with fixture_database_module._digest_lock(cache_root, digest):
                        with fixture_database_module._digest_lock(
                            cache_root,
                            digest,
                        ):
                            nested_entered = True

            self.assertTrue(swapped)
            self.assertFalse(nested_entered)

    def test_readonly_cleanup_never_chmods_symlink_swap_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            fixture = snapshot / "Fixture.java"
            fixture.write_bytes(b"class Fixture {}\n")
            fixture.chmod(0o400)
            snapshot.chmod(0o500)
            attacker_root_descriptor = os.open(
                snapshot,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            outside = root / "outside.java"
            outside_bytes = b"class Outside { int secret = 7; }\n"
            outside.write_bytes(outside_bytes)
            outside.chmod(0o400)
            outside_mode = stat.S_IMODE(outside.stat().st_mode)
            real_scandir = os.scandir
            swapped = False

            class SwappingEntry:
                def __init__(self, entry: os.DirEntry[str]) -> None:
                    self._entry = entry
                    self.name = entry.name

                def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
                    nonlocal swapped
                    info = self._entry.stat(follow_symlinks=follow_symlinks)
                    if self.name == "Fixture.java" and not swapped:
                        os.fchmod(attacker_root_descriptor, 0o700)
                        os.unlink(
                            "Fixture.java",
                            dir_fd=attacker_root_descriptor,
                        )
                        os.symlink(
                            outside,
                            "Fixture.java",
                            dir_fd=attacker_root_descriptor,
                        )
                        swapped = True
                    return info

                def __getattr__(self, name: str) -> object:
                    return getattr(self._entry, name)

            class SwappingScandir:
                def __init__(self, path: object) -> None:
                    self._entries = real_scandir(path)

                def __enter__(self) -> SwappingScandir:
                    self._entries.__enter__()
                    return self

                def __exit__(self, *args: object) -> object:
                    return self._entries.__exit__(*args)

                def __iter__(self) -> SwappingScandir:
                    return self

                def __next__(self) -> SwappingEntry:
                    return SwappingEntry(next(self._entries))

            def swapping_scandir(path: object) -> SwappingScandir:
                return SwappingScandir(path)

            cleanup_error: BaseException | None = None
            try:
                with mock.patch.object(
                    fixture_database_module.os,
                    "scandir",
                    side_effect=swapping_scandir,
                ):
                    try:
                        fixture_database_module._remove_helper_owned_cache_path(
                            snapshot,
                            cache_root,
                        )
                    except (AssertionError, OSError) as exc:
                        cleanup_error = exc
            finally:
                os.close(attacker_root_descriptor)

            if not swapped and cleanup_error is not None:
                raise cleanup_error
            self.assertTrue(swapped)
            self.assertEqual(outside.read_bytes(), outside_bytes)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), outside_mode)

    def test_cleanup_inventory_never_chmods_injected_outside_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            database = cache_root / f"{'a' * 64}.db-{'0' * 32}"
            database.mkdir(mode=0o700)
            database_info = database.stat()
            attacker_root_descriptor = os.open(
                database,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            outside = root / "outside.bin"
            outside_bytes = b"outside inode must keep its mode\n"
            outside.write_bytes(outside_bytes)
            outside.chmod(0o400)
            outside_info = outside.stat()
            real_scandir = os.scandir
            injected = False

            class InjectingScandir:
                def __init__(self, path: object) -> None:
                    self._entries = real_scandir(path)
                    self._target = False
                    if isinstance(path, int):
                        info = os.fstat(path)
                        self._target = (
                            info.st_dev,
                            info.st_ino,
                        ) == (
                            database_info.st_dev,
                            database_info.st_ino,
                        )

                def __enter__(self) -> InjectingScandir:
                    nonlocal injected
                    self._entries.__enter__()
                    if self._target and not injected:
                        os.rename(
                            outside,
                            "Outside.bin",
                            dst_dir_fd=attacker_root_descriptor,
                        )
                        injected = True
                    return self

                def __exit__(self, *args: object) -> object:
                    return self._entries.__exit__(*args)

                def __iter__(self) -> InjectingScandir:
                    return self

                def __next__(self) -> os.DirEntry[str]:
                    return next(self._entries)

            cleanup_error: BaseException | None = None
            try:
                with mock.patch.object(
                    fixture_database_module.os,
                    "scandir",
                    side_effect=InjectingScandir,
                ):
                    try:
                        fixture_database_module._remove_helper_owned_cache_path(
                            database,
                            cache_root,
                        )
                    except (AssertionError, OSError) as exc:
                        cleanup_error = exc

                if not injected and cleanup_error is not None:
                    raise cleanup_error
                self.assertTrue(injected)
                retained_outside = os.stat(
                    "Outside.bin",
                    dir_fd=attacker_root_descriptor,
                    follow_symlinks=False,
                )
                self.assertEqual(
                    (retained_outside.st_dev, retained_outside.st_ino),
                    (outside_info.st_dev, outside_info.st_ino),
                )
                self.assertEqual(stat.S_IMODE(retained_outside.st_mode), 0o400)
                file_descriptor = os.open(
                    "Outside.bin",
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=attacker_root_descriptor,
                )
                try:
                    self.assertEqual(os.read(file_descriptor, 4096), outside_bytes)
                finally:
                    os.close(file_descriptor)
            finally:
                os.close(attacker_root_descriptor)

    def test_readonly_cleanup_never_deletes_root_swap_substitute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            fixture_bytes = b"class Fixture { int value = 1; }\n"
            fixture = snapshot / "Fixture.java"
            fixture.write_bytes(fixture_bytes)
            fixture.chmod(0o400)
            snapshot.chmod(0o500)
            original_root = snapshot.stat()
            original_file = fixture.stat()

            outside = root / "outside"
            outside.mkdir(mode=0o700)
            outside_bytes = b"class Outside { int secret = 7; }\n"
            outside_file = outside / "Outside.java"
            outside_file.write_bytes(outside_bytes)
            outside_root = outside.stat()
            outside_file_info = outside_file.stat()
            held_original = root / "held-original"
            real_rename_no_replace = (
                fixture_database_module.renameat2_no_replace
            )
            swapped = False

            def swap_before_quarantine(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal swapped
                if (
                    source_name == snapshot.name
                    and ".retained-" in destination_name
                    and not swapped
                ):
                    snapshot.chmod(0o700)
                    snapshot.rename(held_original)
                    outside.rename(snapshot)
                    swapped = True
                real_rename_no_replace(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            cleanup_error: BaseException | None = None
            with mock.patch.object(
                fixture_database_module,
                "renameat2_no_replace",
                side_effect=swap_before_quarantine,
            ):
                try:
                    fixture_database_module._remove_helper_owned_cache_path(
                        snapshot,
                        cache_root,
                    )
                except (AssertionError, OSError) as exc:
                    cleanup_error = exc

            if not swapped and cleanup_error is not None:
                raise cleanup_error
            self.assertTrue(swapped)
            self.assertTrue(held_original.is_dir())
            self.assertEqual(
                (held_original.stat().st_dev, held_original.stat().st_ino),
                (original_root.st_dev, original_root.st_ino),
            )
            self.assertEqual(
                (
                    (held_original / "Fixture.java").stat().st_dev,
                    (held_original / "Fixture.java").stat().st_ino,
                ),
                (original_file.st_dev, original_file.st_ino),
            )
            self.assertEqual(
                (held_original / "Fixture.java").read_bytes(),
                fixture_bytes,
            )
            self.assertTrue(snapshot.is_dir())
            self.assertEqual(
                (snapshot.stat().st_dev, snapshot.stat().st_ino),
                (outside_root.st_dev, outside_root.st_ino),
            )
            self.assertEqual(
                (
                    (snapshot / "Outside.java").stat().st_dev,
                    (snapshot / "Outside.java").stat().st_ino,
                ),
                (outside_file_info.st_dev, outside_file_info.st_ino),
            )
            self.assertEqual(
                (snapshot / "Outside.java").read_bytes(),
                outside_bytes,
            )

    def test_cleanup_never_chmods_preexisting_legal_name_substitute_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            substitute = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            substitute.mkdir(mode=0o700)
            keep = substitute / "KEEP.bin"
            keep_bytes = b"preexisting substitute must not be mutated\n"
            keep.write_bytes(keep_bytes)
            keep.chmod(0o400)
            substitute.chmod(0o500)
            substitute_info = substitute.stat()
            keep_info = keep.stat()

            fixture_database_module._remove_helper_owned_cache_path(
                substitute,
                cache_root,
            )

            self.assertFalse(substitute.exists())
            retained = list(cache_root.glob(".*.retained-*"))
            self.assertEqual(len(retained), 1)
            self.assertEqual(
                (retained[0].stat().st_dev, retained[0].stat().st_ino),
                (substitute_info.st_dev, substitute_info.st_ino),
            )
            self.assertEqual(stat.S_IMODE(retained[0].stat().st_mode), 0o500)
            retained_keep = retained[0] / "KEEP.bin"
            self.assertEqual(
                (retained_keep.stat().st_dev, retained_keep.stat().st_ino),
                (keep_info.st_dev, keep_info.st_ino),
            )
            self.assertEqual(stat.S_IMODE(retained_keep.stat().st_mode), 0o400)
            self.assertEqual(retained_keep.read_bytes(), keep_bytes)

    def test_cleanup_isolates_exact_root_before_inventory_retained_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            fixture = snapshot / "Fixture.java"
            fixture.write_bytes(b"class Fixture {}\n")
            fixture.chmod(0o400)
            snapshot.chmod(0o500)
            real_pin = fixture_database_module._pin_retained_root_binding
            observed_paths: list[Path] = []

            def require_isolated_root(
                cache_root_descriptor: int,
                quarantine_name: str,
                expected_root: os.stat_result,
            ) -> os.stat_result:
                path = cache_root / quarantine_name
                observed_paths.append(path)
                self.assertIn(".retained-", path.name)
                self.assertFalse(snapshot.exists())
                return real_pin(
                    cache_root_descriptor,
                    quarantine_name,
                    expected_root,
                )

            with mock.patch.object(
                fixture_database_module,
                "_pin_retained_root_binding",
                side_effect=require_isolated_root,
            ):
                fixture_database_module._remove_helper_owned_cache_path(
                    snapshot,
                    cache_root,
                )

            self.assertEqual(len(observed_paths), 1)
            self.assertFalse(snapshot.exists())

    def test_cleanup_retains_quarantine_without_child_unlink_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            fixture_bytes = b"class Fixture { int value = 1; }\n"
            fixture = snapshot / "Fixture.java"
            fixture.write_bytes(fixture_bytes)
            fixture.chmod(0o400)
            snapshot.chmod(0o500)
            fixture_info = fixture.stat()

            outside = root / "outside.java"
            outside_bytes = b"class Outside { int secret = 7; }\n"
            outside.write_bytes(outside_bytes)
            outside.chmod(0o600)
            outside_info = outside.stat()
            real_unlink = os.unlink
            destructive_calls: list[str] = []

            def swap_before_unlink(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                *,
                dir_fd: int | None = None,
            ) -> None:
                name = os.fsdecode(path)
                destructive_calls.append(name)
                if name == "Fixture.java" and dir_fd is not None:
                    os.rename(
                        name,
                        "held-original.java",
                        src_dir_fd=dir_fd,
                        dst_dir_fd=dir_fd,
                    )
                    os.rename(outside, name, dst_dir_fd=dir_fd)
                if dir_fd is None:
                    real_unlink(path)
                else:
                    real_unlink(path, dir_fd=dir_fd)

            cleanup_error: BaseException | None = None
            with mock.patch.object(
                fixture_database_module.os,
                "unlink",
                side_effect=swap_before_unlink,
            ):
                try:
                    fixture_database_module._remove_helper_owned_cache_path(
                        snapshot,
                        cache_root,
                    )
                except (AssertionError, OSError) as exc:
                    cleanup_error = exc

            if not destructive_calls and cleanup_error is not None:
                raise cleanup_error
            self.assertEqual(destructive_calls, [])
            self.assertFalse(snapshot.exists())
            self.assertTrue(outside.is_file())
            self.assertEqual(
                (outside.stat().st_dev, outside.stat().st_ino),
                (outside_info.st_dev, outside_info.st_ino),
            )
            self.assertEqual(outside.stat().st_nlink, 1)
            self.assertEqual(outside.read_bytes(), outside_bytes)
            retained_files = list(cache_root.glob(".*.retained-*/Fixture.java"))
            self.assertEqual(len(retained_files), 1)
            self.assertEqual(
                (retained_files[0].stat().st_dev, retained_files[0].stat().st_ino),
                (fixture_info.st_dev, fixture_info.st_ino),
            )
            self.assertEqual(retained_files[0].read_bytes(), fixture_bytes)

    def test_cleanup_retention_count_bound_fails_before_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            (snapshot / "Fixture.java").write_bytes(b"class Fixture {}\n")

            retained = cache_root / f"{'b' * 64}.sources-{'1' * 32}"
            retained.mkdir(mode=0o700)
            retained_info = retained.stat()
            retained.rename(
                cache_root
                / (
                    f".{retained.name}.retained-{retained_info.st_dev:x}-"
                    f"{retained_info.st_ino:x}-{'c' * 32}"
                )
            )

            with (
                mock.patch.object(
                    fixture_database_module,
                    "_MAX_RETAINED_CLEANUP_TOMBSTONES",
                    1,
                    create=True,
                ),
                self.assertRaisesRegex(AssertionError, "count bound"),
            ):
                fixture_database_module._remove_helper_owned_cache_path(
                    snapshot,
                    cache_root,
                )

            self.assertTrue(snapshot.is_dir())

    def test_cleanup_retention_lock_is_held_before_root_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            (snapshot / "Fixture.java").write_bytes(b"class Fixture {}\n")
            real_quarantine = (
                fixture_database_module._quarantine_helper_cache_root
            )

            def require_global_lock(
                cache_root_descriptor: int,
                legal_name: str,
                expected_root: os.stat_result,
            ) -> tuple[str, os.stat_result]:
                lock_descriptor = os.open(
                    ".cleanup-retention.lock",
                    os.O_RDWR
                    | os.O_CREAT
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=cache_root_descriptor,
                )
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(
                            lock_descriptor,
                            fcntl.LOCK_EX | fcntl.LOCK_NB,
                        )
                finally:
                    os.close(lock_descriptor)
                return real_quarantine(
                    cache_root_descriptor,
                    legal_name,
                    expected_root,
                )

            with mock.patch.object(
                fixture_database_module,
                "_quarantine_helper_cache_root",
                side_effect=require_global_lock,
            ):
                fixture_database_module._remove_helper_owned_cache_path(
                    snapshot,
                    cache_root,
                )

            self.assertFalse(snapshot.exists())

    def test_cleanup_retention_inventory_rejects_cache_root_namespace_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            (snapshot / "Fixture.java").write_bytes(b"class Fixture {}\n")
            cache_identity = (cache_root.stat().st_dev, cache_root.stat().st_ino)
            real_scandir = os.scandir
            drifted = False

            class DriftingScandir:
                def __init__(self, path: object) -> None:
                    self._entries = real_scandir(path)
                    self._target = False
                    if isinstance(path, int):
                        info = os.fstat(path)
                        self._target = (info.st_dev, info.st_ino) == cache_identity

                def __enter__(self) -> DriftingScandir:
                    nonlocal drifted
                    self._entries.__enter__()
                    if self._target and not drifted:
                        transient = cache_root / ".inventory-transient"
                        transient.write_bytes(b"transient\n")
                        transient.unlink()
                        drifted = True
                    return self

                def __exit__(self, *args: object) -> object:
                    return self._entries.__exit__(*args)

                def __iter__(self) -> DriftingScandir:
                    return self

                def __next__(self) -> os.DirEntry[str]:
                    return next(self._entries)

            with (
                mock.patch.object(
                    fixture_database_module.os,
                    "scandir",
                    side_effect=DriftingScandir,
                ),
                self.assertRaisesRegex(
                    AssertionError,
                    "cache root changed during retention inventory",
                ),
            ):
                fixture_database_module._remove_helper_owned_cache_path(
                    snapshot,
                    cache_root,
                )

            self.assertTrue(drifted)
            self.assertTrue(snapshot.is_dir())

    def test_cleanup_retention_aggregate_size_bound_rolls_back_exact_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            fixture_bytes = b"class Fixture { byte[] value = new byte[64]; }\n"
            fixture = snapshot / "Fixture.java"
            fixture.write_bytes(fixture_bytes)
            fixture_info = fixture.stat()

            with (
                mock.patch.object(
                    fixture_database_module,
                    "_MAX_RETAINED_CLEANUP_TOMBSTONES",
                    4,
                    create=True,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "_MAX_RETAINED_CLEANUP_BYTES",
                    1,
                    create=True,
                ),
                self.assertRaisesRegex(AssertionError, "aggregate size bound"),
            ):
                fixture_database_module._remove_helper_owned_cache_path(
                    snapshot,
                    cache_root,
                )

            self.assertTrue(snapshot.is_dir())
            self.assertEqual(fixture.read_bytes(), fixture_bytes)
            self.assertEqual(
                (fixture.stat().st_dev, fixture.stat().st_ino),
                (fixture_info.st_dev, fixture_info.st_ino),
            )

    def test_cleanup_closes_cache_root_fd_when_final_fstat_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_root = root / "cache"
            cache_root.mkdir(mode=0o700)
            snapshot = cache_root / f"{'a' * 64}.sources-{'0' * 32}"
            snapshot.mkdir(mode=0o700)
            cache_identity = (cache_root.stat().st_dev, cache_root.stat().st_ino)
            before = {
                int(entry.name)
                for entry in os.scandir("/proc/self/fd")
                if entry.name.isdigit()
            }
            real_fstat = os.fstat
            cache_fstat_calls = 0

            def fail_second_cache_fstat(descriptor: int) -> os.stat_result:
                nonlocal cache_fstat_calls
                info = real_fstat(descriptor)
                if (info.st_dev, info.st_ino) == cache_identity:
                    cache_fstat_calls += 1
                    if cache_fstat_calls == 2:
                        raise OSError("injected cache-root final fstat failure")
                return info

            leaked: set[int] = set()
            try:
                with (
                    mock.patch.object(
                        fixture_database_module.os,
                        "fstat",
                        side_effect=fail_second_cache_fstat,
                    ),
                    self.assertRaisesRegex(
                        OSError,
                        "injected cache-root final fstat failure",
                    ),
                ):
                    fixture_database_module._remove_helper_owned_cache_path(
                        snapshot,
                        cache_root,
                    )
                after = {
                    int(entry.name)
                    for entry in os.scandir("/proc/self/fd")
                    if entry.name.isdigit()
                }
                leaked = after - before
                self.assertEqual(leaked, set())
            finally:
                for descriptor in leaked:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_stable_snapshot_root_swap_and_restore_is_rejected_after_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture { int value() { return 1; } }\n",
                encoding="utf-8",
            )
            cache_root = root / "cache"
            observed: dict[str, object] = {}

            def fake_run(
                command: list[str],
                **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                database = Path(command[3])
                pinned_cwd = Path(kwargs["cwd"])
                snapshot = pinned_cwd.resolve(strict=True)
                observed.update(command=command, kwargs=kwargs, snapshot=snapshot)
                away = cache_root / "snapshot-away"
                replacement = cache_root / "snapshot-replacement"
                shutil.copytree(snapshot, replacement)
                replacement.chmod(0o700)
                poisoned = replacement / "Fixture.java"
                poisoned.chmod(0o600)
                poisoned.write_text(
                    "class Fixture { int value() { return 999; } }\n",
                    encoding="utf-8",
                )
                snapshot.rename(away)
                replacement.rename(snapshot)
                database.mkdir(parents=True)
                snapshot.rename(replacement)
                away.rename(snapshot)
                replacement.chmod(0o700)
                poisoned.chmod(0o600)
                shutil.rmtree(replacement)
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                return DatabaseInfo(
                    database,
                    observed["snapshot"],
                    "d" * 64,
                )

            with (
                mock.patch.object(fixture_database_module, "_CACHE_ROOT", cache_root),
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
            ):
                with self.assertRaisesRegex(
                    AssertionError,
                    "changed during CodeQL fixture DB build",
                ):
                    fixture_database_module.fixture_database(str(source_root))

            command = observed["command"]
            kwargs = observed["kwargs"]
            self.assertIn("--source-root=.", command)
            self.assertRegex(str(kwargs["cwd"]), r"^/proc/self/fd/\d+$")
            source_fd = int(str(kwargs["cwd"]).rsplit("/", 1)[1])
            inherited_fds = tuple(kwargs["pass_fds"])
            self.assertEqual(inherited_fds[0], source_fd)
            self.assertEqual(len(inherited_fds), 2)
            self.assertEqual(list(cache_root.glob("*.db")), [])
            class_paths = [
                path for path in cache_root.iterdir() if ".classes" in path.name
            ]
            self.assertEqual(len(class_paths), 1)
            self.assertIn(".retained-", class_paths[0].name)
            self.assertEqual(stat.S_IMODE(class_paths[0].stat().st_mode), 0o700)

    def test_transient_node_added_and_removed_from_stable_snapshot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "src"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                "class Fixture {}\n", encoding="utf-8"
            )
            cache_root = root / "cache"
            observed: dict[str, object] = {}

            def fake_run(
                command: list[str],
                **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                database = Path(command[3])
                snapshot = Path(kwargs["cwd"]).resolve(strict=True)
                observed.update(command=command, kwargs=kwargs, snapshot=snapshot)
                original_mode = stat.S_IMODE(snapshot.stat().st_mode)
                snapshot.chmod(0o700)
                transient = snapshot / "Missing.java"
                transient.write_text("class Missing {}\n", encoding="utf-8")
                database.mkdir(parents=True)
                transient.unlink()
                snapshot.chmod(original_mode)
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_validate(database: Path) -> DatabaseInfo:
                return DatabaseInfo(
                    database,
                    observed["snapshot"],
                    "d" * 64,
                )

            with (
                mock.patch.object(fixture_database_module, "_CACHE_ROOT", cache_root),
                mock.patch.object(
                    fixture_database_module.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    fixture_database_module,
                    "validate_database",
                    side_effect=fake_validate,
                ),
            ):
                with self.assertRaisesRegex(
                    AssertionError,
                    "changed during CodeQL fixture DB build",
                ):
                    fixture_database_module.fixture_database(str(source_root))

            command = observed["command"]
            kwargs = observed["kwargs"]
            self.assertIn("--source-root=.", command)
            self.assertRegex(str(kwargs["cwd"]), r"^/proc/self/fd/\d+$")
            self.assertEqual(list(cache_root.glob("*.db")), [])
            class_paths = [
                path for path in cache_root.iterdir() if ".classes" in path.name
            ]
            self.assertEqual(len(class_paths), 1)
            self.assertIn(".retained-", class_paths[0].name)
            self.assertEqual(stat.S_IMODE(class_paths[0].stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
