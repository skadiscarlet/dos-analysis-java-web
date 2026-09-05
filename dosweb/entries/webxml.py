"""Bounded, descriptor-only Servlet registration resolution."""
from __future__ import annotations

import os
import re
import stat
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Final

from dosweb.errors import AnalyzerError

_CANDIDATE_NOTE: Final = "web_xml_servlet_mapping_requires_descriptor_binding"
_COMPLETE_NOTE: Final = "web_xml_servlet_mapping"
_SCHEMA_VERSION: Final = "1.0"
_MAX_FILES: Final = 64
_MAX_VISITED: Final = 100_000
_MAX_FILE_BYTES: Final = 256 * 1024
_MAX_ELEMENTS: Final = 512
_MAX_DEPTH: Final = 32
_MAX_TEXT_BYTES: Final = 4096
_MAX_DIAGNOSTICS: Final = 64
_DIAGNOSTIC_REASONS: Final = frozenset({"web_xml_file_limit", "web_xml_tree_limit", "web_xml_parent_symlink", "web_xml_parse_or_scope_unresolved", "web_xml_servlet_declaration_unresolved", "web_xml_mapping_unresolved", "web_xml_mapping_ambiguous"})
_FORBIDDEN_XML: Final = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)|\b(?:SYSTEM|PUBLIC)\b", re.I)
_EXCLUDED_PARTS: Final = frozenset({"build", "target", "out", ".git", ".gradle"})
_TAG_LINE: Final = re.compile(r"<\s*(?:[A-Za-z_][\w.-]*:)?(servlet|servlet-mapping)(?=\s|>)")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _text(element: ET.Element, name: str) -> str | None:
    values = [child.text.strip() for child in element if _local(child.tag) == name and child.text]
    if len(values) != 1 or not values[0] or len(values[0].encode("utf-8")) > _MAX_TEXT_BYTES:
        return None
    return values[0]


def _append_diagnostic(items: list[dict[str, object]], reason: str, file: str = "", line: int = 1) -> None:
    if reason in _DIAGNOSTIC_REASONS and len(items) < _MAX_DIAGNOSTICS:
        items.append({"reason": reason, "file": file[:4096], "line": line})


def _safe_read(root: Path, relative: str) -> bytes:
    parts = tuple(Path(relative).parts)
    if not parts or Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("unsafe_path")
    root_stat = os.lstat(root)
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise ValueError("unsafe_root")
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            os.close(directory_fd); directory_fd = next_fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
                raise ValueError("unsafe_or_oversize")
            data = os.read(fd, _MAX_FILE_BYTES + 1)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    if len(data) > _MAX_FILE_BYTES:
        raise ValueError("oversize")
    return data


def _iter_descriptors(root: Path, diagnostics: list[dict[str, object]]) -> Iterator[str]:
    """Incremental DFS with fd-relative scandir; every yielded entry is bounded."""
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stack: list[tuple[int, tuple[str, ...]]] = [(root_fd, ())]
    visited = descriptors = 0
    try:
        while stack:
            directory_fd, prefix = stack.pop()
            try:
                with os.scandir(directory_fd) as iterator:
                    for entry in iterator:
                        visited += 1
                        if visited > _MAX_VISITED:
                            _append_diagnostic(diagnostics, "web_xml_tree_limit")
                            return
                        relative_parts = (*prefix, entry.name)
                        relative = "/".join(relative_parts)
                        try:
                            if entry.is_symlink():
                                if entry.name == "web.xml" and prefix and prefix[-1] == "WEB-INF":
                                    _append_diagnostic(diagnostics, "web_xml_parse_or_scope_unresolved", relative)
                                elif entry.is_dir(follow_symlinks=True):
                                    _append_diagnostic(diagnostics, "web_xml_parent_symlink", relative)
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if entry.name in _EXCLUDED_PARTS:
                                    continue
                                child_fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                                stack.append((child_fd, relative_parts))
                                continue
                            if entry.name != "web.xml" or not prefix or prefix[-1] != "WEB-INF":
                                continue
                            if descriptors >= _MAX_FILES:
                                _append_diagnostic(diagnostics, "web_xml_file_limit")
                                return
                            descriptors += 1
                            yield relative
                        except OSError:
                            _append_diagnostic(diagnostics, "web_xml_parse_or_scope_unresolved", relative)
            finally:
                os.close(directory_fd)
    finally:
        for directory_fd, _ in stack:
            try:
                os.close(directory_fd)
            except OSError:
                pass


def _parse_descriptor(root: Path, relative: str, diagnostics: list[dict[str, object]]) -> tuple[list[tuple[str, dict[str, object]]], set[str]] | None:
    try:
        data = _safe_read(root, relative)
        if _FORBIDDEN_XML.search(data):
            raise ValueError("forbidden_xml")
        text = data.decode("utf-8")
        tree = ET.fromstring(text); elements = list(tree.iter())
        if len(elements) > _MAX_ELEMENTS:
            raise ValueError("element_limit")
        def check_depth(node: ET.Element, depth: int = 1) -> None:
            if depth > _MAX_DEPTH:
                raise ValueError("depth_limit")
            for child in node: check_depth(child, depth + 1)
        check_depth(tree)
    except (OSError, UnicodeError, ET.ParseError, ValueError):
        _append_diagnostic(diagnostics, "web_xml_parse_or_scope_unresolved", relative)
        return None
    lines = {"servlet": [], "servlet-mapping": []}
    for line, source in enumerate(text.splitlines(), 1):
        for match in _TAG_LINE.finditer(source): lines[match.group(1)].append(line)
    counters = {"servlet": 0, "servlet-mapping": 0}; declarations: dict[str, list[tuple[str, int]]] = {}; mappings: list[tuple[str | None, str | None, int]] = []
    for element in elements:
        kind = _local(element.tag)
        if kind not in counters: continue
        index = counters[kind]; counters[kind] += 1; line = lines[kind][index] if index < len(lines[kind]) else 1
        if kind == "servlet":
            name, servlet_class = _text(element, "servlet-name"), _text(element, "servlet-class")
            if name is None or servlet_class is None: _append_diagnostic(diagnostics, "web_xml_servlet_declaration_unresolved", relative, line)
            else: declarations.setdefault(name, []).append((servlet_class, line))
        else: mappings.append((_text(element, "servlet-name"), _text(element, "url-pattern"), line))
    identities = {klass for values in declarations.values() for klass, _ in values}
    output: list[tuple[str, dict[str, object]]] = []
    for name, pattern, line in mappings:
        declaration = declarations.get(name or "", [])
        if name is None or pattern is None or not pattern.startswith("/"): _append_diagnostic(diagnostics, "web_xml_mapping_unresolved", relative, line)
        elif len(declaration) != 1: _append_diagnostic(diagnostics, "web_xml_mapping_ambiguous", relative, line)
        else:
            servlet_class, declaration_line = declaration[0]
            output.append((relative, {"servlet_name": name, "servlet_class": servlet_class, "pattern": pattern, "line": line, "declaration_line": declaration_line}))
    return output, identities


def _partial_row(row: Mapping[str, object], *, route: str, registration_file: str, line: int, note: str) -> dict[str, object]:
    result = dict(row); result.update({"registration_kind": "dynamic_unresolved", "registration_fqn": "web.xml:unresolved", "registration_file": registration_file, "registration_start_line": line, "route_or_event": route, "coverage_status": "partial", "coverage_note": note}); return result


def validate_descriptor_coverage(coverage: Mapping[str, object]) -> None:
    fields = {"schema_version", "discovered_count", "parsed_count", "mapped_descriptor_count", "candidate_count", "complete_candidate_count", "partial_candidate_count", "diagnostics"}
    if not isinstance(coverage, Mapping) or set(coverage) != fields or coverage.get("schema_version") != _SCHEMA_VERSION: raise AnalyzerError("ANALYSIS_ENTRY_INVALID", "Descriptor coverage is invalid.")
    for name in fields - {"schema_version", "diagnostics"}:
        if not isinstance(coverage[name], int) or isinstance(coverage[name], bool) or coverage[name] < 0: raise AnalyzerError("ANALYSIS_ENTRY_INVALID", "Descriptor coverage is invalid.")
    if coverage["discovered_count"] > _MAX_FILES or coverage["parsed_count"] > coverage["discovered_count"] or coverage["mapped_descriptor_count"] > coverage["parsed_count"] or coverage["complete_candidate_count"] + coverage["partial_candidate_count"] != coverage["candidate_count"]: raise AnalyzerError("ANALYSIS_ENTRY_INVALID", "Descriptor coverage is invalid.")
    diagnostics = coverage["diagnostics"]
    if not isinstance(diagnostics, list) or len(diagnostics) > _MAX_DIAGNOSTICS: raise AnalyzerError("ANALYSIS_ENTRY_INVALID", "Descriptor coverage is invalid.")
    for item in diagnostics:
        if not isinstance(item, Mapping) or set(item) != {"reason", "file", "line"} or item.get("reason") not in _DIAGNOSTIC_REASONS or not isinstance(item.get("file"), str) or len(item["file"].encode("utf-8")) > 4096 or not isinstance(item.get("line"), int) or item["line"] < 1: raise AnalyzerError("ANALYSIS_ENTRY_INVALID", "Descriptor coverage is invalid.")


def resolve_webxml_servlet_candidates(rows: Sequence[Mapping[str, object]], source_root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    root = source_root.resolve(strict=True); candidates = [dict(row) for row in rows if row.get("coverage_note") == _CANDIDATE_NOTE]; output = [dict(row) for row in rows if row.get("coverage_note") != _CANDIDATE_NOTE]; diagnostics: list[dict[str, object]] = []
    mappings: list[tuple[str, dict[str, object]]] = []; declarations: dict[str, set[str]] = {}; discovered = parsed_count = 0
    for relative in _iter_descriptors(root, diagnostics):
        discovered += 1; parsed = _parse_descriptor(root, relative, diagnostics)
        if parsed is None: continue
        parsed_count += 1; parsed_mappings, identities = parsed; mappings.extend(parsed_mappings)
        for identity in identities: declarations.setdefault(identity, set()).add(relative)
    by_class: dict[str, list[tuple[str, dict[str, object]]]] = {}
    for file, mapping in mappings: by_class.setdefault(str(mapping["servlet_class"]), []).append((file, mapping))
    complete_count = partial_count = 0
    for candidate in candidates:
        handler = candidate.get("handler_fqn"); class_fqn = handler.rsplit(".", 1)[0] if isinstance(handler, str) and handler.endswith(".service") else ""; matched = by_class.get(class_fqn, []); declaration_files = declarations.get(class_fqn, set())
        if len(declaration_files) != 1:
            partial_count += 1
            for file, mapping in matched: output.append(_partial_row(candidate, route=str(mapping["pattern"]), registration_file=file, line=int(mapping["line"]), note="web_xml_descriptor_selection_ambiguous"))
            if not matched: output.append(_partial_row(candidate, route="web_xml_servlet_mapping", registration_file=str(candidate["registration_file"]), line=int(candidate["registration_start_line"]), note="web_xml_descriptor_selection_ambiguous" if declaration_files else _CANDIDATE_NOTE))
        elif not matched:
            partial_count += 1; output.append(_partial_row(candidate, route="web_xml_servlet_mapping", registration_file=str(candidate["registration_file"]), line=int(candidate["registration_start_line"]), note=_CANDIDATE_NOTE))
        else:
            complete_count += 1
            for file, mapping in matched:
                result = dict(candidate); result.update({"registration_kind": "static_registration", "registration_fqn": "web.xml:" + str(mapping["servlet_name"]), "registration_file": file, "registration_start_line": int(mapping["line"]), "route_or_event": str(mapping["pattern"]), "coverage_status": "complete", "coverage_note": _COMPLETE_NOTE}); output.append(result)
    for diagnostic in diagnostics:
        file, line = str(diagnostic["file"] or "WEB-INF/web.xml"), int(diagnostic["line"])
        output.append({"framework": "servlet", "protocol": "http", "handler_fqn": "web.xml.descriptor", "handler_file": file, "handler_start_line": line, "registration_kind": "dynamic_unresolved", "registration_fqn": "web.xml:unresolved", "registration_file": file, "registration_start_line": line, "route_or_event": "web_xml_servlet_mapping", "auth_context": "unknown", "attacker_input_name": "unknown", "attacker_input_type": "unknown", "attacker_input_kind": "unknown", "materialization_phase": "unknown", "coverage_status": "partial", "coverage_note": str(diagnostic["reason"])})
    coverage: dict[str, object] = {"schema_version": _SCHEMA_VERSION, "discovered_count": discovered, "parsed_count": parsed_count, "mapped_descriptor_count": len({file for file, _ in mappings}), "candidate_count": len(candidates), "complete_candidate_count": complete_count, "partial_candidate_count": partial_count, "diagnostics": diagnostics}; validate_descriptor_coverage(coverage); return output, coverage


__all__ = ["resolve_webxml_servlet_candidates", "validate_descriptor_coverage"]
