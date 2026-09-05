from __future__ import annotations

import errno
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from scripts import evaluate_open_discovery as open_discovery_cli


ROOT = Path(__file__).resolve().parents[1]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _minimal_inputs(root: Path) -> tuple[Path, Path, Path]:
    batch = root / "batch"
    batch.mkdir()
    findings = batch / "aggregate_findings.jsonl"
    _write_jsonl(findings, [{
        "batch_target_name": "owner/repo",
        "finding_id": "finding:fixture",
        "growth_id": "growth:fixture",
        "verdict": "static_vulnerable",
    }])
    _write_jsonl(batch / "aggregate_candidate_dispositions.jsonl", [{
        "batch_target_name": "owner/repo",
        "disposition_id": "disposition:fixture",
        "growth_id": "growth:fixture",
        "status": "formal_eligible",
        "negative_proof_ids": [],
    }])
    _write_jsonl(batch / "aggregate_candidate_negative_proofs.jsonl", [])
    seeds = root / "seeds.jsonl"
    _write_jsonl(seeds, [{
        "case_id": "case:miss",
        "repository": "owner/repo",
        "status": "no_candidate",
    }])
    return batch, seeds, findings


class OpenDiscoveryCliTests(unittest.TestCase):
    def test_cli_compares_scan_output_to_seeds_after_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch = root / "batch"
            output = root / "evaluation"
            batch.mkdir()
            _write_jsonl(batch / "aggregate_findings.jsonl", [{
                "batch_target_name": "owner/repo",
                "finding_id": "finding:novel",
                "growth_id": "growth:novel",
                "verdict": "static_vulnerable",
            }])
            _write_jsonl(batch / "aggregate_candidate_dispositions.jsonl", [
                {
                    "batch_target_name": "owner/repo",
                    "disposition_id": "disposition:novel",
                    "growth_id": "growth:novel",
                    "status": "formal_eligible",
                    "negative_proof_ids": [],
                },
                {
                    "batch_target_name": "owner/repo",
                    "disposition_id": "disposition:negative",
                    "growth_id": "growth:negative",
                    "status": "rejected",
                    "negative_proof_ids": ["negative_proof:finite"],
                },
            ])
            _write_jsonl(batch / "aggregate_candidate_negative_proofs.jsonl", [{
                "batch_target_name": "owner/repo",
                "negative_proof_id": "negative_proof:finite",
                "growth_id": "growth:negative",
                "kind": "finite_keyspace",
            }])
            seeds = root / "matches.jsonl"
            _write_jsonl(seeds, [{
                "case_id": "seed:missed",
                "repository": "owner/repo",
                "status": "no_candidate",
                "candidate_ids": [],
            }])

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/evaluate_open_discovery.py"),
                    "--batch-root",
                    str(batch),
                    "--seed-matches",
                    str(seeds),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(1, summary["category_counts"]["novel_static_vulnerable"])
            self.assertEqual(1, summary["category_counts"]["source_proven_negative"])
            self.assertNotIn("false_positive", summary["category_counts"])
            matrix = [
                json.loads(line)
                for line in (output / "discovery_matrix.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(3, len(matrix))
            recall_miss = next(row for row in matrix if row["recall_miss"])
            self.assertEqual(["seed:missed"], recall_miss["seed_ids"])
            self.assertIn("novel_static_vulnerable", (output / "REPORT.md").read_text(encoding="utf-8"))
            self.assertEqual(0o700, stat.S_IMODE(output.stat().st_mode))

    def test_cli_accepts_poc33_truth_dispositions_as_seed_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch = root / "batch"
            output = root / "evaluation"
            batch.mkdir()
            _write_jsonl(batch / "aggregate_findings.jsonl", [{
                "batch_target_name": "owner/repo",
                "finding_id": "finding:poc33",
                "growth_id": "growth:poc33",
                "verdict": "static_vulnerable",
            }])
            _write_jsonl(batch / "aggregate_candidate_dispositions.jsonl", [{
                "batch_target_name": "owner/repo",
                "disposition_id": "disposition:poc33",
                "growth_id": "growth:poc33",
                "status": "formal_eligible",
                "negative_proof_ids": [],
            }])
            _write_jsonl(batch / "aggregate_candidate_negative_proofs.jsonl", [])
            truth_dispositions = root / "truth_dispositions.jsonl"
            _write_jsonl(truth_dispositions, [{
                "record_id": "poc33:record",
                "truth_id": "poc33:truth",
                "repository": "owner/repo",
                "status": "full_chain_finding",
                "matched_finding_ids": ["finding:poc33"],
                "matched_growth_ids": ["growth:poc33"],
            }])

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/evaluate_open_discovery.py"),
                    "--batch-root",
                    str(batch),
                    "--seed-matches",
                    str(truth_dispositions),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            matrix = [
                json.loads(line)
                for line in (output / "discovery_matrix.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual("seed_linked_static_vulnerable", matrix[0]["classification"])
            self.assertEqual(["poc33:record"], matrix[0]["seed_ids"])

    def test_cli_rejects_any_existing_output_leaf(self) -> None:
        for kind in ("file", "directory", "symlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                batch, seeds, _ = _minimal_inputs(root)
                output = root / "evaluation"
                if kind == "file":
                    output.write_text("occupied", encoding="utf-8")
                elif kind == "directory":
                    output.mkdir()
                else:
                    target = root / "symlink-target"
                    target.mkdir()
                    output.symlink_to(target, target_is_directory=True)

                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts/evaluate_open_discovery.py"),
                        "--batch-root",
                        str(batch),
                        "--seed-matches",
                        str(seeds),
                        "--output",
                        str(output),
                    ],
                    cwd=ROOT,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                self.assertNotEqual(0, completed.returncode)

    def test_cli_does_not_follow_existing_output_child_links(self) -> None:
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                batch, seeds, findings = _minimal_inputs(root)
                original = findings.read_bytes()
                original_digest = hashlib.sha256(original).hexdigest()
                output = root / "evaluation"
                output.mkdir()
                matrix = output / "discovery_matrix.jsonl"
                if kind == "symlink":
                    matrix.symlink_to(findings)
                else:
                    os.link(findings, matrix)

                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts/evaluate_open_discovery.py"),
                        "--batch-root",
                        str(batch),
                        "--seed-matches",
                        str(seeds),
                        "--output",
                        str(output),
                    ],
                    cwd=ROOT,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(original, findings.read_bytes())
                self.assertEqual(
                    original_digest,
                    hashlib.sha256(findings.read_bytes()).hexdigest(),
                )

    def test_cli_cleans_temporary_output_after_mid_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch, seeds, _ = _minimal_inputs(root)
            output = root / "evaluation"
            stderr = io.StringIO()
            with mock.patch.object(
                open_discovery_cli,
                "_write_json_at",
                side_effect=OSError("forced write failure"),
            ), redirect_stderr(stderr):
                try:
                    return_code = open_discovery_cli.main([
                        "--batch-root",
                        str(batch),
                        "--seed-matches",
                        str(seeds),
                        "--output",
                        str(output),
                    ])
                except OSError:
                    return_code = -1

            self.assertEqual(2, return_code)
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.glob(".evaluation.tmp-*")))

    def test_cli_atomic_publish_does_not_replace_racing_output_leaf(self) -> None:
        for kind in ("empty-directory", "file"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                batch, seeds, _ = _minimal_inputs(root)
                output = root / "evaluation"
                stderr = io.StringIO()
                racing_inode: int | None = None
                real_rename = open_discovery_cli._renameat2_no_replace

                def racing_rename(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    nonlocal racing_inode
                    if kind == "empty-directory":
                        os.mkdir(destination_name, dir_fd=destination_directory_fd)
                    else:
                        descriptor = os.open(
                            destination_name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=destination_directory_fd,
                        )
                        try:
                            os.write(descriptor, b"competitor")
                        finally:
                            os.close(descriptor)
                    racing_inode = os.stat(
                        destination_name,
                        dir_fd=destination_directory_fd,
                        follow_symlinks=False,
                    ).st_ino
                    real_rename(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )

                with mock.patch.object(
                    open_discovery_cli,
                    "_renameat2_no_replace",
                    side_effect=racing_rename,
                ), redirect_stderr(stderr):
                    return_code = open_discovery_cli.main([
                        "--batch-root",
                        str(batch),
                        "--seed-matches",
                        str(seeds),
                        "--output",
                        str(output),
                    ])

                self.assertEqual(2, return_code)
                self.assertIsNotNone(racing_inode)
                self.assertEqual(racing_inode, output.stat().st_ino)
                if kind == "file":
                    self.assertEqual("competitor", output.read_text(encoding="utf-8"))
                self.assertEqual([], list(root.glob(".evaluation.tmp-*")))

    def test_cli_output_ancestor_symlink_race_cannot_publish_into_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch, seeds, _ = _minimal_inputs(root)
            safe_parent = root / "safe-output-parent"
            safe_parent.mkdir()
            moved_parent = root / "moved-safe-output-parent"
            output = safe_parent / "evaluation"
            drift_checks = 0
            real_matches = open_discovery_cli._directory_fd_matches_path

            def race_ancestor(directory_fd: int, path: Path) -> bool:
                nonlocal drift_checks
                drift_checks += 1
                temporary_outputs = list(safe_parent.glob(".evaluation.tmp-*"))
                self.assertEqual(1, len(temporary_outputs))
                safe_parent.rename(moved_parent)
                safe_parent.symlink_to(batch, target_is_directory=True)
                return real_matches(directory_fd, path)

            stderr = io.StringIO()
            with mock.patch.object(
                open_discovery_cli,
                "_directory_fd_matches_path",
                side_effect=race_ancestor,
            ), redirect_stderr(stderr):
                return_code = open_discovery_cli.main([
                    "--batch-root",
                    str(batch),
                    "--seed-matches",
                    str(seeds),
                    "--output",
                    str(output),
                ])

            self.assertEqual(2, return_code)
            self.assertEqual(1, drift_checks)
            self.assertFalse((batch / "evaluation").exists())
            self.assertEqual([], list(moved_parent.glob(".evaluation.tmp-*")))

    def test_cli_rejects_ancestor_swap_before_parent_fd_is_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch, seeds, _ = _minimal_inputs(root)
            (batch / "parent").mkdir()
            trusted_ancestor = root / "trusted-ancestor"
            output_parent = trusted_ancestor / "parent"
            output_parent.mkdir(parents=True)
            moved_ancestor = root / "moved-trusted-ancestor"
            output = output_parent / "evaluation"
            existence_checks = 0

            def swap_ancestor(path: Path) -> bool:
                nonlocal existence_checks
                existence_checks += 1
                if existence_checks == 1:
                    trusted_ancestor.rename(moved_ancestor)
                    trusted_ancestor.symlink_to(batch, target_is_directory=True)
                    return False
                return os.path.lexists(path)

            stderr = io.StringIO()
            with mock.patch.object(
                open_discovery_cli,
                "_output_exists",
                side_effect=swap_ancestor,
            ), redirect_stderr(stderr):
                return_code = open_discovery_cli.main([
                    "--batch-root",
                    str(batch),
                    "--seed-matches",
                    str(seeds),
                    "--output",
                    str(output),
                ])

            self.assertEqual(2, return_code)
            self.assertEqual(1, existence_checks)
            self.assertFalse((batch / "parent" / "evaluation").exists())
            self.assertEqual([], list(moved_ancestor.rglob(".evaluation.tmp-*")))

    def test_cli_missing_output_ancestor_race_has_no_batch_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch, seeds, _ = _minimal_inputs(root)
            missing_ancestor = root / "missing-output-ancestor"
            output = missing_ancestor / "new-child" / "evaluation"
            existence_checks = 0

            def snapshot(directory: Path) -> list[tuple[str, int, int, bytes | None]]:
                rows: list[tuple[str, int, int, bytes | None]] = []
                for path in sorted(directory.rglob("*")):
                    metadata = path.lstat()
                    rows.append((
                        str(path.relative_to(directory)),
                        metadata.st_ino,
                        metadata.st_mode,
                        path.read_bytes() if path.is_file() else None,
                    ))
                return rows

            before = snapshot(batch)

            def swap_missing_ancestor(path: Path) -> bool:
                nonlocal existence_checks
                existence_checks += 1
                if existence_checks == 1:
                    missing_ancestor.symlink_to(batch, target_is_directory=True)
                    return False
                return os.path.lexists(path)

            stderr = io.StringIO()
            with mock.patch.object(
                open_discovery_cli,
                "_output_exists",
                side_effect=swap_missing_ancestor,
            ), redirect_stderr(stderr):
                return_code = open_discovery_cli.main([
                    "--batch-root",
                    str(batch),
                    "--seed-matches",
                    str(seeds),
                    "--output",
                    str(output),
                ])

            self.assertEqual(2, return_code)
            self.assertEqual(1, existence_checks)
            self.assertEqual(before, snapshot(batch))
            self.assertFalse((batch / "new-child").exists())
            self.assertEqual([], list(batch.rglob(".evaluation.tmp-*")))

    def test_cli_does_not_re_resolve_output_leaf_after_parent_fd_is_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch, seeds, _ = _minimal_inputs(root)
            output = root / "evaluation"
            existence_checks = 0

            def count_path_checks(path: Path) -> bool:
                nonlocal existence_checks
                existence_checks += 1
                return os.path.lexists(path)

            with mock.patch.object(
                open_discovery_cli,
                "_output_exists",
                side_effect=count_path_checks,
            ):
                return_code = open_discovery_cli.main([
                    "--batch-root",
                    str(batch),
                    "--seed-matches",
                    str(seeds),
                    "--output",
                    str(output),
                ])

            self.assertEqual(0, return_code)
            self.assertEqual(1, existence_checks)
            self.assertTrue(output.is_dir())

    def test_cli_fails_closed_when_atomic_no_replace_syscall_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            batch, seeds, _ = _minimal_inputs(root)
            output = root / "evaluation"
            stderr = io.StringIO()
            with mock.patch.object(
                open_discovery_cli,
                "_renameat2_no_replace",
                side_effect=OSError(errno.ENOSYS, "renameat2 unavailable"),
            ), redirect_stderr(stderr):
                return_code = open_discovery_cli.main([
                    "--batch-root",
                    str(batch),
                    "--seed-matches",
                    str(seeds),
                    "--output",
                    str(output),
                ])

            self.assertEqual(2, return_code)
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.glob(".evaluation.tmp-*")))

    def test_cli_symlink_loop_path_resolution_is_a_controlled_error(self) -> None:
        for kind in ("batch", "seed", "output-ancestor"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                batch, seeds, _ = _minimal_inputs(root)
                loop = root / f"{kind}-loop"
                loop.symlink_to(loop)
                selected_batch = loop if kind == "batch" else batch
                selected_seed = loop if kind == "seed" else seeds
                output = (
                    loop / "evaluation"
                    if kind == "output-ancestor"
                    else root / "evaluation"
                )
                stderr = io.StringIO()

                with redirect_stderr(stderr):
                    return_code = open_discovery_cli.main([
                        "--batch-root",
                        str(selected_batch),
                        "--seed-matches",
                        str(selected_seed),
                        "--output",
                        str(output),
                    ])

                self.assertEqual(2, return_code)
                self.assertNotIn("Traceback", stderr.getvalue())
                self.assertTrue(stderr.getvalue().strip())


if __name__ == "__main__":
    unittest.main()
