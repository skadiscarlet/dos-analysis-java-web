"""Narrow source supplement for JAX-RS handlers absent from CodeQL AST facts.

This is not a general Java parser.  It only recovers a field-backed ``Map.put``
inside an already-normalized, exact Airlift ``JaxrsBinder`` handler.  Both the
candidate and its association stay partial so this supplement can only lead to
``static_unknown`` until CodeQL supplies data-flow and lifecycle coverage.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from dosweb.entries import EntryFact


_MAX_HANDLER_FILES: Final = 1024
_MAX_FILE_BYTES: Final = 512 * 1024
_MAX_TOTAL_BYTES: Final = 16 * 1024 * 1024
_SCANNER_SHA256: Final = hashlib.sha256(b"dosweb-source-jaxrs-map-put-v1").hexdigest()
_AIRLIFT_BIND: Final = "com.facebook.airlift.jaxrs.JaxrsBinder.bind"
_FIELD_MAP = re.compile(
    r"\b(?P<visibility>private|protected|public)\s+"
    r"(?P<static>static\s+)?(?P<final>final\s+)?"
    r"(?P<type>(?:java\.util\.)?(?:Map|SortedMap|NavigableMap|ConcurrentMap|ConcurrentHashMap))"
    r"\s*<[^;={}]{1,2048}>\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?:=|;)",
)


def _mask(source: str, *, literals: bool) -> str:
    output = list(source)
    state = "code"
    escaped = False
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and following == "/":
                output[index] = output[index + 1] = " "
                state = "line"
                index += 2
                continue
            if char == "/" and following == "*":
                output[index] = output[index + 1] = " "
                state = "block"
                index += 2
                continue
            if char == '"':
                state = "string"
                escaped = False
                if literals:
                    output[index] = " "
            elif char == "'":
                state = "char"
                escaped = False
                if literals:
                    output[index] = " "
        elif state == "line":
            if char in "\r\n":
                state = "code"
            else:
                output[index] = " "
        elif state == "block":
            if char == "*" and following == "/":
                output[index] = output[index + 1] = " "
                state = "code"
                index += 2
                continue
            if char not in "\r\n":
                output[index] = " "
        else:
            if literals and char not in "\r\n":
                output[index] = " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "code"
        index += 1
    return "".join(output)


def _matching(source: str, opening: int, left: str = "(", right: str = ")") -> int | None:
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == left:
            depth += 1
        elif source[index] == right:
            depth -= 1
            if depth == 0:
                return index
    return None


def _top_level_arguments(source: str) -> tuple[str, ...] | None:
    structure = _mask(source, literals=False)
    parts: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    for index, char in enumerate(structure):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
        elif char in "(<[{":
            depth += 1
        elif char in ")>]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(source[start:index].strip())
            start = index + 1
    if quote or depth != 0:
        return None
    parts.append(source[start:].strip())
    return tuple(parts) if all(parts) else None


def _read_handler(root: Path, relative: str) -> str | None:
    try:
        candidate = root.joinpath(*Path(relative).parts)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        if candidate.is_symlink():
            return None
        descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
                return None
            data = os.read(descriptor, _MAX_FILE_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(data) > _MAX_FILE_BYTES:
            return None
        return data.decode("utf-8")
    except (OSError, UnicodeError, ValueError):
        return None


def _method_body(structure: str, method_name: str, expected_line: int) -> tuple[int, int] | None:
    pattern = re.compile(
        rf"\b(?:public|protected|private)\s+(?:(?:static|final|synchronized)\s+)*"
        rf"(?:<[^;{{}}]+>\s+)?[A-Za-z_$][\w.$<>, ?\[\]]*?\s+"
        rf"(?P<name>{re.escape(method_name)})\s*\([^;{{}}]*\)\s*"
        rf"(?:throws\s+[^;{{}}]+)?\{{",
        re.DOTALL,
    )
    matches: list[tuple[int, int]] = []
    for match in pattern.finditer(structure):
        line = structure.count("\n", 0, match.start("name")) + 1
        if line != expected_line:
            continue
        opening = structure.find("{", match.start(), match.end())
        closing = _matching(structure, opening, "{", "}")
        if closing is not None:
            matches.append((opening + 1, closing))
    return matches[0] if len(matches) == 1 else None


def source_backed_same_handler_growth(
    entries: Sequence[EntryFact], source_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return partial raw Growth and association rows for exact Airlift entries."""
    if not isinstance(entries, (tuple, list)) or not all(isinstance(item, EntryFact) for item in entries):
        return [], []
    try:
        root = source_root.resolve(strict=True)
        root_info = os.lstat(root)
    except OSError:
        return [], []
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        return [], []

    handlers = {
        (entry.handler.callable, entry.handler.file, entry.handler.start_line): entry
        for entry in entries
        if entry.framework == "jax_rs"
        and entry.registration.kind == "static_registration"
        and entry.registration.callable == _AIRLIFT_BIND
    }
    if not handlers or len(handlers) > _MAX_HANDLER_FILES:
        return [], []

    growth: dict[tuple[str, int, str], dict[str, object]] = {}
    associations: dict[tuple[str, int, str, int], dict[str, object]] = {}
    total_bytes = 0
    for (callable_name, relative, handler_line), entry in sorted(handlers.items()):
        text = _read_handler(root, relative)
        if text is None:
            continue
        total_bytes += len(text.encode("utf-8"))
        if total_bytes > _MAX_TOTAL_BYTES:
            return [], []
        clean = _mask(text, literals=False)
        structure = _mask(text, literals=True)
        method_name = callable_name.rsplit(".", 1)[-1]
        body_bounds = _method_body(structure, method_name, handler_line)
        if body_bounds is None:
            continue
        body_start, body_end = body_bounds
        body_structure = structure[body_start:body_end]
        body_clean = clean[body_start:body_end]
        fields = {match.group("name"): match for match in _FIELD_MAP.finditer(structure[:body_start])}
        for field_name, field in sorted(fields.items()):
            if re.search(
                rf"\b(?:Map|SortedMap|NavigableMap|ConcurrentMap|ConcurrentHashMap)\s*<[^;=]+>\s+{re.escape(field_name)}\b",
                body_structure,
            ):
                continue
            call_pattern = re.compile(rf"\b(?:this\s*\.\s*)?{re.escape(field_name)}\s*\.\s*put\s*\(")
            for call in call_pattern.finditer(body_structure):
                opening = body_structure.find("(", call.start(), call.end())
                closing = _matching(body_structure, opening)
                if closing is None:
                    continue
                arguments = _top_level_arguments(body_clean[opening + 1:closing])
                if arguments is None or len(arguments) != 2:
                    continue
                key_expression = " ".join(arguments[0].split())
                if not key_expression or len(key_expression.encode("utf-8")) > 4096:
                    continue
                site_offset = body_start + call.start()
                site_line = text.count("\n", 0, site_offset) + 1
                owner = callable_name.rsplit(".", 1)[0]
                receiver = f"{owner}.{field_name}"
                note = "source_jaxrs_same_handler_container_write_codeql_ast_unavailable"
                site_location = f"{relative}:{site_line}"
                growth_key = (relative, site_line, field_name)
                growth[growth_key] = {
                    "site_file": relative,
                    "site_start_line": site_line,
                    "growth_kind": "container_growth",
                    "operation": "java.util.Map.put",
                    "resource_dimension": "entries",
                    "receiver": receiver,
                    "field_path": field_name,
                    "demand_input_name": key_expression,
                    "demand_input_role": "key",
                    "escape_scope": "global" if field.group("static") else "instance",
                    "candidate_evidence": "source_field_backed_container_write",
                    "coverage_status": "partial",
                    "coverage_note": note,
                    "query_name": "source_jaxrs_container_growth",
                    "query_sha256": _SCANNER_SHA256,
                    "site_location": site_location,
                }
                association_key = (relative, handler_line, relative, site_line)
                associations[association_key] = {
                    "source_file": relative,
                    "source_start_line": handler_line,
                    "sink_file": relative,
                    "sink_start_line": site_line,
                    "attacker_target": "key",
                    "attacker_source": entry.attacker_inputs[0].name,
                    "attacker_sink": key_expression,
                    "call_path": callable_name,
                    "phase_sequence": "entry>source_same_handler>growth",
                    "flow_kind": "unmodeled",
                    "confidence": "partial",
                    "coverage_status": "partial",
                    "coverage_note": note,
                    "query_name": "source_jaxrs_growth_association",
                    "query_sha256": _SCANNER_SHA256,
                    "source_location": f"{relative}:{handler_line}",
                    "sink_location": site_location,
                }
    return (
        [growth[key] for key in sorted(growth)],
        [associations[key] for key in sorted(associations)],
    )


__all__ = ["source_backed_same_handler_growth"]
