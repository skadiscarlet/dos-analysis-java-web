from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Final

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError
from dosweb.growth.models import SourceExcerpt

_MAX_SOURCE_BYTES: Final = 16_384
_MAX_GIT_METADATA_BYTES: Final = 256
_MAX_PATH_BYTES: Final = 512
_MAX_LINE: Final = 2**31 - 1
_DEFAULT_CONTEXT_LINES: Final = 8
_GIT_TIMEOUT_SECONDS: Final = 10


def _invalid(reason: str, *, field: str | None = None) -> AnalyzerError:
    details: dict[str, object] = {"reason": reason[:128]}
    if field is not None:
        details["field"] = field[:128]
    return AnalyzerError(
        "LLM_BOUNDED_SLICE_INVALID",
        "Source excerpt could not be derived from the pinned checkout.",
        details,
    )


def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise _invalid("PATH_INVALID", field="repo_relative_path")
    try:
        if len(value.encode("utf-8")) > _MAX_PATH_BYTES:
            raise _invalid("PATH_LIMIT", field="repo_relative_path")
    except UnicodeEncodeError as exc:
        raise _invalid("PATH_INVALID", field="repo_relative_path") from exc
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise _invalid("PATH_INVALID", field="repo_relative_path")
    normalized = path.as_posix()
    if normalized != value:
        raise _invalid("PATH_NOT_NORMALIZED", field="repo_relative_path")
    return normalized


def _read_checkout_file(checkout: Path, relative_path: str) -> bytes:
    descriptors: list[int] = []
    try:
        root = os.open(
            checkout,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        descriptors.append(root)
        current = root
        parts = PurePosixPath(relative_path).parts
        for part in parts[:-1]:
            current = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            descriptors.append(current)
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=current,
        )
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_SOURCE_BYTES:
            raise ValueError("source is not a bounded regular file")
        raw = bytearray()
        while len(raw) <= _MAX_SOURCE_BYTES:
            chunk = os.read(descriptor, min(4096, _MAX_SOURCE_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        if len(raw) > _MAX_SOURCE_BYTES or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("source changed while it was read")
        return bytes(raw)
    except AnalyzerError:
        raise
    except (OSError, ValueError, MemoryError) as exc:
        raise _invalid("SOURCE_FILE_INVALID", field="repo_relative_path") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _git_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }


def _git_blob(checkout: Path, source_commit_sha: str, relative_path: str) -> bytes:
    if (
        not isinstance(source_commit_sha, str)
        or len(source_commit_sha) != 40
        or any(character not in "0123456789abcdef" for character in source_commit_sha)
    ):
        raise _invalid("SOURCE_COMMIT_INVALID", field="source_commit_sha")
    object_id = f"{source_commit_sha}:{relative_path}"
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "--no-pager",
        "-C",
        str(checkout),
    ]
    try:
        commit_type = subprocess.run(
            [*command, "cat-file", "-t", source_commit_sha],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_environment(),
        ).stdout
        if len(commit_type) > _MAX_GIT_METADATA_BYTES or commit_type.rstrip(b"\n") != b"commit":
            raise ValueError("source revision is not a commit")
        metadata = subprocess.run(
            [*command, "cat-file", "--batch-check=%(objecttype) %(objectsize)"],
            input=(object_id + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_environment(),
        ).stdout
        if len(metadata) > _MAX_GIT_METADATA_BYTES:
            raise ValueError("git metadata exceeds limit")
        object_type, size_text = metadata.rstrip(b"\n").split(b" ", 1)
        if object_type != b"blob" or not size_text.isdigit():
            raise ValueError("commit path is not a blob")
        size = int(size_text)
        if size > _MAX_SOURCE_BYTES:
            raise ValueError("git blob exceeds limit")
        blob = subprocess.run(
            [*command, "show", object_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_environment(),
        ).stdout
        if len(blob) != size:
            raise ValueError("git blob size changed")
        return blob
    except AnalyzerError:
        raise
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeError,
        ValueError,
        OverflowError,
        MemoryError,
    ) as exc:
        raise _invalid("PINNED_SOURCE_UNAVAILABLE", field="source_commit_sha") from exc


def extract_source_excerpt(
    source_checkout: Path,
    source_commit_sha: str,
    repo_relative_path: str,
    candidate_line: int,
    *,
    context_lines: int = _DEFAULT_CONTEXT_LINES,
    git_blob_reader: Callable[[Path, str, str], bytes] | None = None,
) -> SourceExcerpt:
    """Derive one deterministic excerpt from a regular file matching a pinned Git blob."""
    path = _normalized_path(repo_relative_path)
    if (
        not isinstance(candidate_line, int)
        or isinstance(candidate_line, bool)
        or not 1 <= candidate_line <= _MAX_LINE
    ):
        raise _invalid("CANDIDATE_LINE_INVALID", field="candidate_line")
    if (
        not isinstance(context_lines, int)
        or isinstance(context_lines, bool)
        or not 0 <= context_lines <= 256
    ):
        raise _invalid("CONTEXT_LINES_INVALID", field="context_lines")

    checkout_bytes = _read_checkout_file(source_checkout, path)
    reader = git_blob_reader or _git_blob
    try:
        blob = reader(source_checkout, source_commit_sha, path)
    except AnalyzerError:
        raise
    except (OSError, ValueError, TypeError, MemoryError) as exc:
        raise _invalid("PINNED_SOURCE_UNAVAILABLE", field="source_commit_sha") from exc
    if not isinstance(blob, bytes) or len(blob) > _MAX_SOURCE_BYTES or blob != checkout_bytes:
        raise _invalid("CHECKOUT_BLOB_MISMATCH", field="repo_relative_path")

    try:
        lines = blob.splitlines(keepends=True)
        if candidate_line > len(lines):
            raise _invalid("CANDIDATE_LOCATION_OUTSIDE_SOURCE", field="candidate_line")
        start_line = max(1, candidate_line - context_lines)
        end_line = min(len(lines), candidate_line + context_lines)
        excerpt_bytes = b"".join(lines[start_line - 1 : end_line])
        content = excerpt_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid("SOURCE_NOT_UTF8", field="repo_relative_path") from exc
    if not excerpt_bytes or len(excerpt_bytes) > _MAX_SOURCE_BYTES:
        raise _invalid("EXCERPT_SIZE_INVALID", field="repo_relative_path")

    blob_sha256 = hashlib.sha256(blob).hexdigest()
    excerpt_sha256 = hashlib.sha256(excerpt_bytes).hexdigest()
    identity = {
        "repo_relative_path": path,
        "start_line": start_line,
        "end_line": end_line,
        "git_blob_sha256": blob_sha256,
        "excerpt_sha256": excerpt_sha256,
    }
    return SourceExcerpt(
        excerpt_id=stable_identifier("excerpt", identity),
        repo_relative_path=path,
        start_line=start_line,
        end_line=end_line,
        content=content,
        git_blob_sha256=blob_sha256,
        excerpt_sha256=excerpt_sha256,
    )


__all__ = ["extract_source_excerpt"]
