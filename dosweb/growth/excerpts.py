from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Final

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError
from dosweb.growth.models import SourceExcerpt
from dosweb.growth.redaction import REDACTION_VERSION, redact_source_content

_MAX_SOURCE_BYTES: Final = 1_048_576
_MAX_PATH_BYTES: Final = 512
_MAX_LINE: Final = 2**31 - 1
_DEFAULT_CONTEXT_LINES: Final = 8


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


def extract_source_excerpt(
    source_checkout: Path,
    source_commit_sha: str | None,
    repo_relative_path: str,
    candidate_line: int,
    *,
    context_lines: int = _DEFAULT_CONTEXT_LINES,
    git_blob_reader: object | None = None,
) -> SourceExcerpt:
    """Derive one deterministic excerpt from the current source checkout."""
    del source_commit_sha, git_blob_reader
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

    blob = _read_checkout_file(source_checkout, path)
    try:
        lines = blob.splitlines(keepends=True)
        if candidate_line > len(lines):
            raise _invalid("CANDIDATE_LOCATION_OUTSIDE_SOURCE", field="candidate_line")
        start_line = max(1, candidate_line - context_lines)
        end_line = min(len(lines), candidate_line + context_lines)
        original_excerpt_bytes = b"".join(lines[start_line - 1 : end_line])
        original_content = original_excerpt_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid("SOURCE_NOT_UTF8", field="repo_relative_path") from exc
    if not original_excerpt_bytes or len(original_excerpt_bytes) > _MAX_SOURCE_BYTES:
        raise _invalid("EXCERPT_SIZE_INVALID", field="repo_relative_path")

    redacted_content, redaction_events = redact_source_content(original_content, start_line)
    try:
        transmitted_bytes = redacted_content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _invalid("SOURCE_NOT_UTF8", field="repo_relative_path") from exc
    if len(transmitted_bytes) > _MAX_SOURCE_BYTES:
        raise _invalid("EXCERPT_SIZE_INVALID", field="repo_relative_path")

    blob_sha256 = hashlib.sha256(blob).hexdigest()
    original_excerpt_sha256 = hashlib.sha256(original_excerpt_bytes).hexdigest()
    excerpt_sha256 = hashlib.sha256(transmitted_bytes).hexdigest()
    identity = {
        "repo_relative_path": path,
        "start_line": start_line,
        "end_line": end_line,
        "git_blob_sha256": blob_sha256,
        "original_excerpt_sha256": original_excerpt_sha256,
        "excerpt_sha256": excerpt_sha256,
    }
    return SourceExcerpt(
        excerpt_id=stable_identifier("excerpt", identity),
        repo_relative_path=path,
        start_line=start_line,
        end_line=end_line,
        content=redacted_content,
        git_blob_sha256=blob_sha256,
        excerpt_sha256=excerpt_sha256,
        original_excerpt_sha256=original_excerpt_sha256,
        redaction_events=redaction_events,
        redaction_version=REDACTION_VERSION,
    )


__all__ = ["extract_source_excerpt"]
