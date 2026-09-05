#!/usr/bin/env python3
"""Classify post-scan discoveries after subtracting benchmark positive seeds."""
from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dosweb.artifacts.identifiers import canonical_json
from dosweb.benchmark.evaluator import (
    OPEN_DISCOVERY_CLASSES,
    evaluate_open_discovery,
)


_MAX_INPUT_BYTES = 64 * 1024 * 1024
_MAX_ROWS = 1_000_000
_RENAME_NOREPLACE = 1


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: expected a regular JSONL file")
    if path.stat().st_size > _MAX_INPUT_BYTES:
        raise ValueError(f"{path}: JSONL input exceeds the bounded evaluator limit")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        if len(rows) >= _MAX_ROWS:
            raise ValueError(f"{path}: too many JSONL records")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        rows.append(value)
    return rows


def _write_bytes_at(directory_fd: int, name: str, value: bytes) -> None:
    required_flags = ("O_CLOEXEC", "O_NOFOLLOW")
    if any(not hasattr(os, flag) for flag in required_flags):
        raise OSError(errno.ENOSYS, "required no-follow file flags unavailable")
    descriptor = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_CLOEXEC
        | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        view = memoryview(value)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(errno.EIO, "short write while publishing evaluation")
            view = view[written:]
    finally:
        os.close(descriptor)


def _write_json_at(directory_fd: int, name: str, value: object) -> None:
    _write_bytes_at(directory_fd, name, canonical_json(value) + b"\n")


def _write_jsonl_at(
    directory_fd: int, name: str, rows: list[dict[str, Any]]
) -> None:
    _write_bytes_at(
        directory_fd,
        name,
        b"".join(canonical_json(row) + b"\n" for row in rows),
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _output_path(path: Path) -> Path:
    absolute = path.expanduser()
    if not absolute.is_absolute():
        absolute = Path.cwd() / absolute
    return absolute.parent.resolve(strict=False) / absolute.name


def _output_exists(path: Path) -> bool:
    return os.path.lexists(path)


def _open_directory_no_follow(path: Path) -> int:
    required_flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, flag) for flag in required_flags):
        raise OSError(errno.ENOSYS, "required directory flags unavailable")
    if not path.is_absolute():
        raise ValueError("output parent must be absolute")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            next_descriptor = os.open(
                component,
                flags,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except (OSError, RuntimeError):
        os.close(descriptor)
        raise


def _leaf_exists_at(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _directory_fd_matches_path(directory_fd: int, path: Path) -> bool:
    try:
        current = path.stat()
    except OSError:
        return False
    opened = os.fstat(directory_fd)
    return (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino)


def _create_private_temp_directory(
    parent_fd: int, output_name: str
) -> tuple[str, int]:
    for _ in range(128):
        name = f".{output_name}.tmp-{secrets.token_hex(8)}"
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        except (OSError, RuntimeError):
            os.rmdir(name, dir_fd=parent_fd)
            raise
        return name, descriptor
    raise OSError(errno.EEXIST, "unable to allocate private output directory")


def _renameat2_no_replace(
    source_directory_fd: int,
    source_name: str,
    destination_directory_fd: int,
    destination_name: str,
) -> None:
    """Atomically publish one dirfd-relative leaf without replacement."""

    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise OSError(errno.ENOSYS, "renameat2(RENAME_NOREPLACE) unavailable") from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        source_directory_fd,
        os.fsencode(source_name),
        destination_directory_fd,
        os.fsencode(destination_name),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            destination_name,
        )


def _cleanup_private_temp(
    parent_fd: int | None,
    temporary_fd: int | None,
    temporary_name: str | None,
) -> None:
    if temporary_fd is not None:
        for name in ("discovery_matrix.jsonl", "summary.json", "REPORT.md"):
            try:
                os.unlink(name, dir_fd=temporary_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        os.close(temporary_fd)
    if parent_fd is not None and temporary_name is not None:
        try:
            os.rmdir(temporary_name, dir_fd=parent_fd)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post-hoc open-discovery evaluator for formal static batch output."
    )
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--seed-matches", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    parent_fd: int | None = None
    temporary_fd: int | None = None
    temporary_name: str | None = None
    try:
        batch_root = args.batch_root.resolve()
        seed_matches_path = args.seed_matches.resolve()
        output = _output_path(args.output)
        if _inside(output, batch_root) or output == seed_matches_path:
            raise ValueError(
                "output must be separate from the immutable scan and seed inputs"
        )
        if _output_exists(output):
            raise ValueError("output already exists")
        parent_fd = _open_directory_no_follow(output.parent)
        if _leaf_exists_at(parent_fd, output.name):
            raise ValueError("output already exists")
        result = evaluate_open_discovery(
            findings=_read_jsonl(batch_root / "aggregate_findings.jsonl"),
            dispositions=_read_jsonl(
                batch_root / "aggregate_candidate_dispositions.jsonl"
            ),
            negative_proofs=_read_jsonl(
                batch_root / "aggregate_candidate_negative_proofs.jsonl"
            ),
            seed_matches=_read_jsonl(seed_matches_path),
        )
        temporary_name, temporary_fd = _create_private_temp_directory(
            parent_fd, output.name
        )

        discoveries = result["discoveries"]
        summary = {
            "format": "dosweb-open-discovery-evaluation-v1",
            "schema_version": result["schema_version"],
            "discovery_count": len(discoveries),
            "category_counts": result["category_counts"],
            "seed_comparison_phase": "post_scan",
            "production_knows_novelty": False,
            "unmatched_seed_is_false_positive": False,
        }
        _write_jsonl_at(
            temporary_fd, "discovery_matrix.jsonl", discoveries
        )
        _write_json_at(temporary_fd, "summary.json", summary)
        report = [
            "# Open Discovery Evaluation",
            "",
            f"- discovery_count: {summary['discovery_count']}",
            "- seed comparison: post-scan only",
            "- unmatched PoC seed: not an automatic false positive",
            "",
            "## Categories",
            "",
        ]
        report.extend(
            f"- {category}: {result['category_counts'][category]}"
            for category in OPEN_DISCOVERY_CLASSES
        )
        report.append("")
        _write_bytes_at(
            temporary_fd,
            "REPORT.md",
            "\n".join(report).encode("utf-8"),
        )
        if not _directory_fd_matches_path(parent_fd, output.parent):
            raise ValueError("output parent changed during publication")
        if _leaf_exists_at(parent_fd, output.name):
            raise ValueError("output already exists")
        _renameat2_no_replace(
            parent_fd,
            temporary_name,
            parent_fd,
            output.name,
        )
        os.close(temporary_fd)
        temporary_fd = None
        temporary_name = None
        return 0
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        _cleanup_private_temp(parent_fd, temporary_fd, temporary_name)
        if parent_fd is not None:
            os.close(parent_fd)


if __name__ == "__main__":
    raise SystemExit(main())
