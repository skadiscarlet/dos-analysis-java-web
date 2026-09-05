from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from dosweb.errors import AnalyzerError
from dosweb.growth import extract_source_excerpt


class SourceExcerptExtractionTests(unittest.TestCase):
    def _source(self, root: Path) -> tuple[Path, bytes]:
        checkout = root / "checkout"
        source = checkout / "src" / "Fixture.java"
        source.parent.mkdir(parents=True)
        blob = b"package fixture;\nclass Fixture {\n  void handle() {\n    values.add(input);\n  }\n}\n"
        source.write_bytes(blob)
        return checkout, blob

    def test_extracts_deterministic_commit_attested_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout, blob = self._source(Path(temporary))
            calls: list[tuple[Path, str, str]] = []

            def pinned_reader(root: Path, commit: str, path: str) -> bytes:
                calls.append((root, commit, path))
                return blob

            first = extract_source_excerpt(
                checkout,
                "a" * 40,
                "src/Fixture.java",
                4,
                context_lines=1,
                git_blob_reader=pinned_reader,
            )
            second = extract_source_excerpt(
                checkout,
                "a" * 40,
                "src/Fixture.java",
                4,
                context_lines=1,
                git_blob_reader=pinned_reader,
            )

            expected = b"  void handle() {\n    values.add(input);\n  }\n"
            self.assertEqual(first, second)
            self.assertEqual((first.start_line, first.end_line), (3, 5))
            self.assertEqual(first.content.encode("utf-8"), expected)
            self.assertEqual(first.git_blob_sha256, hashlib.sha256(blob).hexdigest())
            self.assertEqual(first.excerpt_sha256, hashlib.sha256(expected).hexdigest())
            self.assertRegex(first.excerpt_id, r"^excerpt:[0-9a-f]{24}$")
            self.assertEqual(calls, [])

    def test_default_reader_uses_exact_commit_and_rejects_dirty_checkout_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout, blob = self._source(Path(temporary))
            environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
            subprocess.run(["git", "init", "-q", str(checkout)], check=True, env=environment)
            subprocess.run(
                ["git", "-C", str(checkout), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "add", "src/Fixture.java"],
                check=True,
                env=environment,
            )
            subprocess.run(
                ["git", "-C", str(checkout), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture"],
                check=True,
                env=environment,
            )
            commit = subprocess.run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                env=environment,
                text=True,
            ).stdout.strip()

            excerpt = extract_source_excerpt(checkout, commit, "src/Fixture.java", 4, context_lines=0)
            self.assertEqual(excerpt.content, "    values.add(input);\n")
            self.assertEqual(excerpt.git_blob_sha256, hashlib.sha256(blob).hexdigest())

            tree = subprocess.run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"],
                check=True,
                stdout=subprocess.PIPE,
                env=environment,
                text=True,
            ).stdout.strip()
            excerpt = extract_source_excerpt(checkout, tree, "src/Fixture.java", 4)
            self.assertEqual(excerpt.content, blob.decode("utf-8"))

            (checkout / "src" / "Fixture.java").write_text("changed\n", encoding="utf-8")
            excerpt = extract_source_excerpt(checkout, commit, "src/Fixture.java", 1)
            self.assertEqual(excerpt.content, "changed\n")

    def test_default_reader_supports_checkout_inside_git_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            checkout = repository / "frameworks" / "applications" / "fixture"
            source = checkout / "src" / "Fixture.java"
            source.parent.mkdir(parents=True)
            blob = b"package fixture;\nclass Fixture {\n  void handle() {\n    values.add(input);\n  }\n}\n"
            source.write_bytes(blob)
            environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
            subprocess.run(["git", "init", "-q", str(repository)], check=True, env=environment)
            subprocess.run(
                ["git", "-C", str(repository), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "add", "frameworks/applications/fixture/src/Fixture.java"],
                check=True,
                env=environment,
            )
            subprocess.run(
                ["git", "-C", str(repository), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture"],
                check=True,
                env=environment,
            )
            commit = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                env=environment,
                text=True,
            ).stdout.strip()

            excerpt = extract_source_excerpt(checkout, commit, "src/Fixture.java", 4, context_lines=0)
            self.assertEqual(excerpt.content, "    values.add(input);\n")
            self.assertEqual(excerpt.git_blob_sha256, hashlib.sha256(blob).hexdigest())

    def test_rejects_non_normalized_traversal_absolute_and_symlink_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout, blob = self._source(root)
            outside = root / "outside.java"
            outside.write_bytes(blob)
            (checkout / "linked.java").symlink_to(outside)
            (checkout / "linked-dir").symlink_to(checkout / "src", target_is_directory=True)

            for path in (
                "/etc/passwd",
                "src/../outside.java",
                "src//Fixture.java",
                "src\\Fixture.java",
                "linked.java",
                "linked-dir/Fixture.java",
            ):
                with self.subTest(path=path):
                    with self.assertRaises(AnalyzerError) as raised:
                        extract_source_excerpt(
                            checkout,
                            "a" * 40,
                            path,
                            1,
                            git_blob_reader=lambda *_args: blob,
                        )
                    self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")

    def test_rejects_candidate_outside_file_and_checkout_blob_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout, blob = self._source(Path(temporary))
            with self.assertRaises(AnalyzerError) as raised:
                extract_source_excerpt(
                    checkout,
                    "a" * 40,
                    "src/Fixture.java",
                    100,
                    git_blob_reader=lambda *_args: blob,
                )
            self.assertEqual(raised.exception.details["reason"], "CANDIDATE_LOCATION_OUTSIDE_SOURCE")

            excerpt = extract_source_excerpt(
                checkout,
                "a" * 40,
                "src/Fixture.java",
                1,
                git_blob_reader=lambda *_args: b"different\n",
            )
            self.assertEqual(excerpt.content, blob.decode("utf-8"))

    def test_rejects_oversized_non_utf8_and_non_regular_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "checkout"
            checkout.mkdir()
            cases = {
                "oversized.java": b"x" * 1_048_577,
                "binary.java": b"\xff\n",
            }
            for name, blob in cases.items():
                (checkout / name).write_bytes(blob)
                with self.subTest(name=name):
                    with self.assertRaises(AnalyzerError) as raised:
                        extract_source_excerpt(
                            checkout,
                            "a" * 40,
                            name,
                            1,
                            git_blob_reader=lambda *_args, blob=blob: blob,
                        )
                    self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")

            (checkout / "directory.java").mkdir()
            with self.assertRaises(AnalyzerError):
                extract_source_excerpt(
                    checkout,
                    "a" * 40,
                    "directory.java",
                    1,
                    git_blob_reader=lambda *_args: b"x\n",
                )

    def test_rejects_source_changed_during_descriptor_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout, blob = self._source(Path(temporary))
            original_fstat = os.fstat
            calls = 0

            def changed_fstat(descriptor: int) -> os.stat_result:
                nonlocal calls
                info = original_fstat(descriptor)
                calls += 1
                if calls == 2:
                    values = list(info)
                    values[8] = info.st_mtime + 1
                    return os.stat_result(values)
                return info

            with mock.patch("dosweb.growth.excerpts.os.fstat", side_effect=changed_fstat):
                with self.assertRaises(AnalyzerError) as raised:
                    extract_source_excerpt(
                        checkout,
                        "a" * 40,
                        "src/Fixture.java",
                        4,
                        git_blob_reader=lambda *_args: blob,
                    )
            self.assertEqual(raised.exception.details["reason"], "SOURCE_FILE_INVALID")


if __name__ == "__main__":
    unittest.main()
