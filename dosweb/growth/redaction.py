"""Line-number-preserving credential redaction for bounded source slices.

Source excerpts may contain business identifiers such as ``password``, ``token``,
or ``secret`` that are not real credentials.  These must not abort a formal run as
false positives, but real credentials must still fail closed downstream.  This
module redacts only the *value* of an unambiguous credential assignment, mutator
call, or explicit header call to a fixed token, preserving line structure so the
excerpt identity and audit trail stay deterministic.  Matching happens on a
comment/string-masked copy so text that merely mentions ``token`` inside a string
literal is never corrupted.  The configured API key and any pattern that cannot be
redacted safely are left untouched and re-scanned by the caller's credential gate,
which then fails closed.
"""
from __future__ import annotations

import re
from typing import Final

REDACTION_VERSION: Final = "1"
REDACTED_TOKEN: Final = "[REDACTED]"

_CREDENTIAL_LABEL = (
    r"authorization|api[_-]?key|private[_-]?key|access[_-]?(?:token|key)|"
    r"refresh[_-]?token|client[_-]?secret|db[_-]?password|password|passwd|pwd|"
    r"oauth[_-]?token|token|secret|credential|credentials"
)

_ASSIGNMENT = re.compile(rf"(?ix)\b(?P<label>{_CREDENTIAL_LABEL})\s*(?P<op>:|=)\s*")
_MUTATOR = re.compile(
    rf"(?ix)\b(?P<call>set|with|add|put|update|configure)"
    rf"[A-Za-z0-9_$]*(?P<label>authorization|api[_-]?key|private[_-]?key|"
    rf"access[_-]?(?:token|key)|refresh[_-]?token|client[_-]?secret|password|passwd|"
    rf"oauth[_-]?token|token|secret|credential|credentials)[A-Za-z0-9_$]*\s*\("
)
_HEADER_CALL = re.compile(r"(?ix)\b(?P<call>set|add|put|header)\s*\(")
_HEADER_LABEL = re.compile(rf"(?ix)^(?P<label>{_CREDENTIAL_LABEL})$")
_STRING = re.compile(r'''(?s)^("""(?:.*?)"""|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''')

_MAX_EVENTS = 256
_DELIMITERS = " \t;,)}\n"


def _mask_code(content: str) -> str:
    """Replace comments and string/char literals with ``#``, preserving positions and newlines.

    ``#`` is neither a word character nor whitespace, so word boundaries and
    ``\\s*`` quantifiers in the credential patterns do not over-consume masked
    literal values.
    """
    chars = list(content)
    i = 0
    n = len(content)
    while i < n:
        if content.startswith("//", i):
            while i < n and content[i] not in "\r\n":
                chars[i] = "#"
                i += 1
            continue
        if content.startswith("/*", i):
            closed = False
            while i < n - 1:
                if content.startswith("*/", i):
                    chars[i] = chars[i + 1] = "#"
                    i += 2
                    closed = True
                    break
                chars[i] = "#" if content[i] not in "\r\n" else content[i]
                i += 1
            if not closed:
                i = n
            continue
        if content.startswith('"""', i):
            chars[i : i + 3] = "###"
            i += 3
            closed = False
            while i < n - 2:
                if content.startswith('"""', i):
                    chars[i : i + 3] = "###"
                    i += 3
                    closed = True
                    break
                chars[i] = "#" if content[i] not in "\r\n" else content[i]
                i += 1
            if not closed:
                i = n
            continue
        if content[i] == '"':
            chars[i] = "#"
            i += 1
            while i < n:
                if content[i] == "\\":
                    chars[i] = "#"
                    i += 1
                    if i < n:
                        chars[i] = "#"
                        i += 1
                    continue
                if content[i] == '"':
                    chars[i] = "#"
                    i += 1
                    break
                chars[i] = "#" if content[i] not in "\r\n" else content[i]
                i += 1
            continue
        if content[i] == "'":
            chars[i] = "#"
            i += 1
            while i < n:
                if content[i] == "\\":
                    chars[i] = "#"
                    i += 1
                    if i < n:
                        chars[i] = "#"
                        i += 1
                    continue
                if content[i] == "'":
                    chars[i] = "#"
                    i += 1
                    break
                chars[i] = "#" if content[i] not in "\r\n" else content[i]
                i += 1
            continue
        i += 1
    return "".join(chars)


def _value_end(line: str, start: int) -> int:
    """Return the exclusive end of a value token (string/char/text-block or bare token)."""
    n = len(line)
    i = start
    while i < n and line[i] in " \t":
        i += 1
    if i >= n:
        return i
    if line.startswith('"""', i):
        j = i + 3
        while j < n - 2 and not line.startswith('"""', j):
            j += 1
        return j + 3 if line.startswith('"""', j) else n
    if line[i] in "\"'":
        quote = line[i]
        j = i + 1
        while j < n:
            if line[j] == "\\":
                j += 2
                continue
            j += 1
            if line[j - 1] == quote:
                break
        return j
    j = i
    while j < n and line[j] not in _DELIMITERS:
        j += 1
    return j


def _redact_spans(line: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return line
    spans = sorted(spans)
    output: list[str] = []
    cursor = 0
    for start, end in spans:
        if start < cursor:
            continue
        output.append(line[cursor:start])
        output.append(REDACTED_TOKEN)
        cursor = end
    output.append(line[cursor:])
    return "".join(output)


def _append(events: list[dict[str, object]], absolute: int, pattern_id: str) -> None:
    if len(events) < _MAX_EVENTS:
        events.append({"line": absolute, "pattern_id": pattern_id})


def redact_source_content(content: str, base_line: int) -> tuple[str, tuple[dict[str, object], ...]]:
    """Return ``(redacted_content, events)`` where events carry absolute line numbers."""
    if not isinstance(base_line, int) or isinstance(base_line, bool) or base_line < 1:
        raise ValueError("base_line must be a positive integer")
    masked = _mask_code(content)
    events: list[dict[str, object]] = []
    original_lines = content.splitlines(keepends=True)
    masked_lines = masked.splitlines(keepends=True)
    output: list[str] = []
    for offset, (line, mline) in enumerate(zip(original_lines, masked_lines)):
        absolute = base_line + offset
        spans: list[tuple[int, int]] = []
        for match in _ASSIGNMENT.finditer(mline):
            spans.append((match.end(), _value_end(line, match.end())))
            _append(events, absolute, "credential_assignment")
        for match in _MUTATOR.finditer(mline):
            spans.append((match.end(), _value_end(line, match.end())))
            _append(events, absolute, "credential_mutator")
        for match in _HEADER_CALL.finditer(mline):
            redacted = _redact_header_argument(line, match.end())
            if redacted is not None:
                spans.append(redacted)
                _append(events, absolute, "credential_header")
        output.append(_redact_spans(line, spans))
    return "".join(output), tuple(events)


def _redact_header_argument(line: str, open_paren_end: int) -> tuple[int, int] | None:
    """If the first argument is a credential header name, return the span of the second argument."""
    n = len(line)
    first = _STRING.match(line[open_paren_end:])
    if first is None:
        return None
    name_text = first.group(0)
    stripped = name_text[3:-3] if name_text.startswith('"""') else name_text[1:-1]
    if not _HEADER_LABEL.fullmatch(stripped.strip()):
        return None
    after = open_paren_end + first.end()
    i = after
    while i < n and line[i] in " \t":
        i += 1
    if i >= n or line[i] != ",":
        return None
    return (i + 1, _value_end(line, i + 1))


__all__ = ["REDACTION_VERSION", "REDACTED_TOKEN", "redact_source_content"]
