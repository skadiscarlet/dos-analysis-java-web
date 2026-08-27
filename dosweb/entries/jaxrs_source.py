"""Bounded source fallback for unresolved source-registered JAX-RS entries.

The fallback is deliberately narrower than the CodeQL JAX-RS query.  It only
publishes a complete entry for an exact Airlift binder, one source-defined
Dropwizard application/module installation, or a Sisu GLOBAL_INDEX-discovered
``@Named`` Guice root with one installed child and one semantics-verified
resource-binding helper.  Duplicate installation/binding paths fail closed.
It exists for databases where dependency bytecode is missing and CodeQL keeps
the annotations or registration calls as unresolved AST nodes.
"""
from __future__ import annotations

import ast
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final


_MAX_FILES: Final = 8192
_MAX_VISITED: Final = 300_000
_MAX_FILE_BYTES: Final = 512 * 1024
_MAX_TOTAL_BYTES: Final = 64 * 1024 * 1024
_MAX_DEPTH: Final = 64
_EXCLUDED_DIRS: Final = frozenset({
    ".agents", ".git", ".gradle", ".idea", ".mvn", "build",
    "node_modules", "out", "target",
})
_HTTP_VERBS: Final = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")
_IDENTIFIER: Final = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$")
_PACKAGE: Final = re.compile(r"\bpackage\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*;")
_IMPORT: Final = re.compile(r"\bimport\s+(?:static\s+)?([A-Za-z_$][\w$]*(?:\.[A-Za-z_$*][\w$*]*)*)\s*;")
_TYPE: Final = re.compile(
    r"\b(?P<kind>class|interface)\s+(?P<name>[A-Za-z_$][\w$]*)"
    r"(?P<tail>[^{};]{0,1024})\{",
)
_CLASS_STRING = re.compile(
    r"\b(?:public\s+|protected\s+|private\s+)?static\s+final\s+String\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?P<expr>[^;]{1,2048});",
)
_INTERFACE_STRING = re.compile(
    r"\b(?:public\s+static\s+final\s+)?String\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?P<expr>[^;]{1,2048});",
)
_METHOD_DECL = re.compile(
    r"^[ \t]*(?:(?:public|protected|private|static|final|synchronized|default)\s+)+"
    r"(?:<[^;{}]+>\s+)?[A-Za-z_$][\w.$<>, ?\[\]]*?\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*\((?P<params>.*?)\)\s*"
    r"(?:throws\s+[^;{}]+)?\{",
    re.MULTILINE | re.DOTALL,
)
_BIND = re.compile(r"\bbind\s*\(\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\.class\s*\)")
_AIRLIFT_JAXRS_BIND = re.compile(
    r"\bjaxrsBinder\s*\(\s*[A-Za-z_$][\w$]*\s*\)\s*\.bind\s*\(\s*"
    r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\.class\s*\)",
)
_INSTALL_NEW_MODULE = re.compile(
    r"\b[A-Za-z_$][\w$]*\s*\.\s*install\s*\(\s*new\s+"
    r"(?P<module>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(",
)
_SOURCE_BINDING_HELPER_CALL = re.compile(
    r"\b(?P<helper>[A-Za-z_$][\w$]*)\s*\(\s*"
    r"(?P<binder>[A-Za-z_$][\w$]*)\s*,\s*"
    r"(?P<resource>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)"
    r"\s*\.class\s*\)",
)


@dataclass(frozen=True)
class _JavaUnit:
    relative: str
    text: str
    clean: str
    structure: str
    package: str
    imports: tuple[str, ...]
    kind: str
    name: str
    tail: str
    class_start: int

    @property
    def fqn(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name


@dataclass(frozen=True)
class _JavaMethod:
    annotations: str
    name: str
    params: str
    name_start: int


def _mask_comments(source: str) -> str:
    output = list(source)
    state = "code"
    escaped = False
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and following == "/":
                output[index] = output[index + 1] = " "; state = "line"; index += 2; continue
            if char == "/" and following == "*":
                output[index] = output[index + 1] = " "; state = "block"; index += 2; continue
            if char == '"': state = "string"; escaped = False
            elif char == "'": state = "char"; escaped = False
        elif state == "line":
            if char in "\r\n": state = "code"
            else: output[index] = " "
        elif state == "block":
            if char == "*" and following == "/":
                output[index] = output[index + 1] = " "; state = "code"; index += 2; continue
            if char not in "\r\n": output[index] = " "
        else:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "code"
        index += 1
    return "".join(output)


def _mask_literals(source: str) -> str:
    output = list(source)
    state = "code"
    escaped = False
    for index, char in enumerate(source):
        if state == "code":
            if char == '"': state = "string"; output[index] = " "; escaped = False
            elif char == "'": state = "char"; output[index] = " "; escaped = False
        else:
            if char not in "\r\n": output[index] = " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "code"
    return "".join(output)


def _is_source_path(relative: Path) -> bool:
    parts = relative.parts
    return relative.suffix == ".java" and any(
        parts[index:index + 3] == ("src", "main", "java")
        for index in range(max(0, len(parts) - 2))
    )


def _read_source(root: Path, relative: Path) -> str | None:
    candidate = root / relative
    try:
        descriptor = os.open(candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
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
    except (OSError, UnicodeError):
        return None


def _load_units(source_root: Path) -> list[_JavaUnit] | None:
    try:
        root = source_root.resolve(strict=True)
        root_info = os.lstat(root)
    except OSError:
        return None
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        return None
    units: list[_JavaUnit] = []
    visited = total_bytes = 0
    for current, directories, files in os.walk(root, followlinks=False):
        try:
            relative_dir = Path(current).relative_to(root)
        except ValueError:
            return None
        if len(relative_dir.parts) > _MAX_DEPTH:
            directories[:] = []
            continue
        kept: list[str] = []
        for name in sorted(directories):
            visited += 1
            candidate = Path(current) / name
            if visited > _MAX_VISITED:
                return None
            if name in _EXCLUDED_DIRS or candidate.is_symlink():
                continue
            kept.append(name)
        directories[:] = kept
        for name in sorted(files):
            visited += 1
            if visited > _MAX_VISITED:
                return None
            relative = relative_dir / name
            if not _is_source_path(relative):
                continue
            candidate = Path(current) / name
            if candidate.is_symlink():
                continue
            if len(units) >= _MAX_FILES:
                return None
            text = _read_source(root, relative)
            if text is None:
                return None
            total_bytes += len(text.encode("utf-8"))
            if total_bytes > _MAX_TOTAL_BYTES:
                return None
            clean = _mask_comments(text)
            structure = _mask_literals(clean)
            type_match = _TYPE.search(structure)
            if type_match is None:
                continue
            package_match = _PACKAGE.search(clean)
            units.append(_JavaUnit(
                relative.as_posix(), text, clean, structure,
                package_match.group(1) if package_match else "",
                tuple(match.group(1) for match in _IMPORT.finditer(clean)),
                type_match.group("kind"), type_match.group("name"),
                type_match.group("tail"), type_match.start(),
            ))
    return units


def _split(expression: str, separator: str = "+") -> list[str] | None:
    parts: list[str] = []
    start = 0
    quote = ""
    escaped = False
    depth = 0
    for index, char in enumerate(expression):
        if quote:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == quote: quote = ""
            continue
        if char in {'"', "'"}: quote = char; continue
        if char in "(<[{": depth += 1
        elif char in ")>]}": depth -= 1
        elif char == separator and depth == 0:
            parts.append(expression[start:index].strip()); start = index + 1
    if quote or depth != 0:
        return None
    parts.append(expression[start:].strip())
    return parts if all(parts) else None


def _resolve_type(
    name: str,
    unit: _JavaUnit,
    by_fqn: Mapping[str, _JavaUnit],
    by_simple: Mapping[str, tuple[_JavaUnit, ...]],
) -> _JavaUnit | None:
    if name in by_fqn:
        return by_fqn[name]
    if "." in name:
        return by_fqn.get(f"{unit.package}.{name}")
    explicit = [value for value in unit.imports if value.endswith(f".{name}")]
    candidates = [by_fqn[value] for value in explicit if value in by_fqn]
    same_package = by_fqn.get(f"{unit.package}.{name}")
    if same_package is not None:
        candidates.append(same_package)
    if not candidates:
        candidates.extend(by_simple.get(name, ()))
    unique = {candidate.fqn: candidate for candidate in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _constant_fields(units: Sequence[_JavaUnit]) -> dict[tuple[str, str], str]:
    raw: dict[tuple[str, str], tuple[_JavaUnit, str]] = {}
    for unit in units:
        pattern = _INTERFACE_STRING if unit.kind == "interface" else _CLASS_STRING
        for match in pattern.finditer(unit.clean):
            raw[(unit.fqn, match.group("name"))] = (unit, match.group("expr").strip())
    by_fqn = {unit.fqn: unit for unit in units}
    by_simple: dict[str, tuple[_JavaUnit, ...]] = {}
    for unit in units:
        by_simple[unit.name] = (*by_simple.get(unit.name, ()), unit)
    resolved: dict[tuple[str, str], str] = {}

    def identifier_value(identifier: str, owner: _JavaUnit) -> str | None:
        candidates: set[str] = set()
        if "." in identifier:
            type_name, field = identifier.rsplit(".", 1)
            target = _resolve_type(type_name, owner, by_fqn, by_simple)
            if target is not None and (value := resolved.get((target.fqn, field))) is not None:
                candidates.add(value)
        else:
            if (value := resolved.get((owner.fqn, identifier))) is not None:
                candidates.add(value)
            implemented = re.search(r"\bimplements\s+([^{}]+)", owner.tail)
            if implemented:
                for name in implemented.group(1).split(","):
                    target = _resolve_type(name.strip(), owner, by_fqn, by_simple)
                    if target is not None and (value := resolved.get((target.fqn, identifier))) is not None:
                        candidates.add(value)
            for (type_fqn, field), value in resolved.items():
                if field == identifier:
                    candidates.add(value)
        return next(iter(candidates)) if len(candidates) == 1 else None

    def evaluate(expression: str, owner: _JavaUnit) -> str | None:
        terms = _split(expression)
        if terms is None:
            return None
        values: list[str] = []
        for term in terms:
            if term.startswith('"') and term.endswith('"'):
                try:
                    value = ast.literal_eval(term)
                except (SyntaxError, ValueError):
                    return None
                if not isinstance(value, str):
                    return None
                values.append(value)
            elif _IDENTIFIER.fullmatch(term):
                value = identifier_value(term, owner)
                if value is None:
                    return None
                values.append(value)
            else:
                return None
        result = "".join(values)
        return result if len(result.encode("utf-8")) <= 4096 else None

    for _ in range(16):
        changed = False
        for key, (owner, expression) in raw.items():
            if key in resolved:
                continue
            value = evaluate(expression, owner)
            if value is not None:
                resolved[key] = value; changed = True
        if not changed:
            break
    return resolved


def _constant_value(
    expression: str,
    owner: _JavaUnit,
    fields: Mapping[tuple[str, str], str],
    by_fqn: Mapping[str, _JavaUnit],
    by_simple: Mapping[str, tuple[_JavaUnit, ...]],
) -> str | None:
    parts = _split(expression)
    if parts is None:
        return None
    output: list[str] = []
    for part in parts:
        if part.startswith('"') and part.endswith('"'):
            try:
                value = ast.literal_eval(part)
            except (SyntaxError, ValueError):
                return None
            if not isinstance(value, str):
                return None
            output.append(value); continue
        if not _IDENTIFIER.fullmatch(part):
            return None
        candidates: set[str] = set()
        if "." in part:
            type_name, field = part.rsplit(".", 1)
            target = _resolve_type(type_name, owner, by_fqn, by_simple)
            if target is not None and (value := fields.get((target.fqn, field))) is not None:
                candidates.add(value)
        else:
            if (value := fields.get((owner.fqn, part))) is not None:
                candidates.add(value)
            implemented = re.search(r"\bimplements\s+([^{}]+)", owner.tail)
            if implemented:
                for name in implemented.group(1).split(","):
                    target = _resolve_type(name.strip(), owner, by_fqn, by_simple)
                    if target is not None and (value := fields.get((target.fqn, part))) is not None:
                        candidates.add(value)
            for (type_fqn, field), value in fields.items():
                if field == part:
                    candidates.add(value)
        if len(candidates) != 1:
            return None
        output.append(next(iter(candidates)))
    result = "".join(output)
    return result if len(result.encode("utf-8")) <= 4096 else None


def _matching_delimiter(source: str, opening: int, left: str = "(", right: str = ")") -> int | None:
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == left: depth += 1
        elif source[index] == right:
            depth -= 1
            if depth == 0: return index
    return None


def _annotation_block(unit: _JavaUnit, method_start: int) -> str | None:
    boundary = unit.structure.rfind("}", 0, method_start) + 1
    for opening in (
        index for index in range(boundary, method_start)
        if unit.structure[index] == "@"
    ):
        cursor = opening
        count = 0
        while cursor < method_start:
            annotation = re.match(r"@[A-Za-z_$][\w.$]*", unit.structure[cursor:])
            if annotation is None:
                break
            count += 1
            cursor += annotation.end()
            while cursor < method_start and unit.structure[cursor].isspace():
                cursor += 1
            if cursor < method_start and unit.structure[cursor] == "(":
                closing = _matching_delimiter(unit.structure, cursor)
                if closing is None or closing >= method_start:
                    break
                cursor = closing + 1
            while cursor < method_start and unit.structure[cursor].isspace():
                cursor += 1
            if cursor == method_start and count:
                return unit.clean[opening:method_start]
            if cursor >= method_start or unit.structure[cursor] != "@":
                break
    return None


def _annotated_methods(unit: _JavaUnit) -> list[_JavaMethod]:
    methods: list[_JavaMethod] = []
    for declaration in _METHOD_DECL.finditer(unit.clean):
        annotations = _annotation_block(unit, declaration.start())
        if annotations is None:
            continue
        methods.append(_JavaMethod(
            annotations=annotations,
            name=declaration.group("name"),
            params=declaration.group("params"),
            name_start=declaration.start("name"),
        ))
    return methods


def _call_argument(statement: str, name: str) -> str | None:
    structure = _mask_literals(statement)
    match = re.search(rf"\.{re.escape(name)}\s*\(", structure)
    if match is None:
        return None
    opening = structure.find("(", match.start())
    closing = _matching_delimiter(structure, opening)
    return statement[opening + 1:closing].strip() if closing is not None else None


def _method_bodies(unit: _JavaUnit, name: str) -> list[tuple[int, int]]:
    bodies: list[tuple[int, int]] = []
    pattern = re.compile(rf"\b{re.escape(name)}\s*\([^;{{}}]*\)\s*(?:throws\s+[^;{{}}]+)?\{{")
    for match in pattern.finditer(unit.structure):
        opening = unit.structure.find("{", match.start(), match.end())
        closing = _matching_delimiter(unit.structure, opening, "{", "}")
        if closing is not None:
            bodies.append((opening + 1, closing))
    return bodies


def _module_expression_types(expression: str, application: _JavaUnit) -> set[str]:
    result = set(re.findall(r"\bnew\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(", expression))
    for method_name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(\s*\)", expression):
        for start, end in _method_bodies(application, method_name):
            result.update(re.findall(
                r"\breturn\s+new\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(",
                application.clean[start:end],
            ))
    return result


def _installed_modules(
    units: Sequence[_JavaUnit],
    fields: Mapping[tuple[str, str], str],
    by_fqn: Mapping[str, _JavaUnit],
    by_simple: Mapping[str, tuple[_JavaUnit, ...]],
) -> dict[str, set[tuple[str, str]]]:
    installed: dict[str, set[tuple[str, str]]] = {}
    for application in units:
        if (
            "io.dropwizard.core.Application" not in application.imports
            or "ru.vyarus.dropwizard.guice.GuiceBundle" not in application.imports
            or not re.search(r"\bextends\s+Application\s*<", application.tail)
        ):
            continue
        prefixes: set[str] = set()
        for match in re.finditer(r"\.jersey\s*\(\s*\)\s*\.setUrlPattern\s*\(([^;]{1,2048})\)\s*;", application.clean):
            value = _constant_value(match.group(1), application, fields, by_fqn, by_simple)
            if value is not None and value.startswith("/") and value.endswith("/*"):
                prefixes.add(value[:-2] or "/")
        if len(prefixes) != 1 or "GuiceBundle.builder" not in application.clean:
            continue
        prefix = next(iter(prefixes))
        cursor = 0
        while True:
            builder = application.clean.find("GuiceBundle.builder", cursor)
            if builder < 0:
                break
            cursor = builder + 1
            end = application.clean.find(";", builder, builder + 8192)
            if end < 0:
                continue
            statement_start = max(application.clean.rfind(";", 0, builder), application.clean.rfind("{", 0, builder)) + 1
            statement = application.clean[statement_start:end + 1]
            if ".build" not in statement:
                continue
            variable_match = re.search(r"([A-Za-z_$][\w$]*)\s*=\s*GuiceBundle\.builder", statement)
            if variable_match is None or not re.search(
                rf"\.addBundle\s*\(\s*{re.escape(variable_match.group(1))}\s*\)", application.clean[end + 1:],
            ):
                continue
            module_expression = _call_argument(statement, "modules")
            if module_expression is None:
                continue
            for module_name in _module_expression_types(module_expression, application):
                module = _resolve_type(module_name, application, by_fqn, by_simple)
                if module is not None:
                    installed.setdefault(module.fqn, set()).add((application.fqn, prefix))
    return installed


def _has_sisu_global_index_scan(units: Sequence[_JavaUnit]) -> bool:
    return any(
        {
            "org.eclipse.sisu.space.BeanScanning",
            "org.eclipse.sisu.space.SpaceModule",
            "org.eclipse.sisu.wire.WireModule",
        }.issubset(unit.imports)
        and re.search(r"\bnew\s+WireModule\s*\(", unit.structure)
        and re.search(r"\bnew\s+SpaceModule\s*\(", unit.structure)
        and "BeanScanning.GLOBAL_INDEX" in unit.clean
        for unit in units
    )


def _is_named_guice_module(unit: _JavaUnit) -> bool:
    if (
        "com.google.inject.Binder" not in unit.imports
        or "com.google.inject.Module" not in unit.imports
        or not any(value in unit.imports for value in ("javax.inject.Named", "jakarta.inject.Named"))
        or not re.search(r"\bimplements\s+(?:[A-Za-z_$][\w$]*\s*,\s*)*Module\b", unit.tail)
    ):
        return False
    prefix = unit.clean[max(0, unit.class_start - 4096):unit.class_start]
    return re.search(r"@Named(?:\s*\([^)]*\))?\s*$", prefix, re.MULTILINE) is not None


def _sisu_installed_modules(
    units: Sequence[_JavaUnit],
    by_fqn: Mapping[str, _JavaUnit],
    by_simple: Mapping[str, tuple[_JavaUnit, ...]],
) -> dict[str, list[tuple[_JavaUnit, re.Match[str], int]]]:
    if not _has_sisu_global_index_scan(units):
        return {}
    installed: dict[str, list[tuple[_JavaUnit, re.Match[str], int]]] = {}
    for root in units:
        if not _is_named_guice_module(root):
            continue
        configure_bodies = _method_bodies(root, "configure")
        if len(configure_bodies) != 1:
            continue
        body_start, body_end = configure_bodies[0]
        body = root.clean[body_start:body_end]
        for installation in _INSTALL_NEW_MODULE.finditer(body):
            child = _resolve_type(
                installation.group("module"), root, by_fqn, by_simple
            )
            if child is not None:
                installed.setdefault(child.fqn, []).append(
                    (root, installation, body_start)
                )
    return installed


def _source_binding_helper(
    caller: _JavaUnit,
    method_name: str,
    by_fqn: Mapping[str, _JavaUnit],
) -> tuple[_JavaUnit, str, str] | None:
    imported = {
        value.rsplit(".", 1)[0]
        for value in caller.imports
        if value.endswith(f".{method_name}")
    }
    imported.update(
        value[:-2]
        for value in caller.imports
        if value.endswith(".*") and value[:-2] in by_fqn
    )
    if len(imported) != 1:
        return None
    helper = by_fqn.get(next(iter(imported)))
    if helper is None or "com.google.inject.Binder" not in helper.imports:
        return None
    if (
        "com.google.inject.Scopes.SINGLETON" not in helper.imports
        or "com.google.inject.multibindings.Multibinder.newSetBinder" not in helper.imports
    ):
        return None
    declaration = re.compile(
        rf"\bpublic\s+static\s+(?:<[^;{{}}]+>\s+)?void\s+"
        rf"{re.escape(method_name)}\s*\((?P<params>[^;{{}}]+)\)\s*\{{"
    )
    matches = list(declaration.finditer(helper.structure))
    if len(matches) != 1:
        return None
    match = matches[0]
    parsed = _parameters(match.group("params"))
    if parsed is None or len(parsed) != 2:
        return None
    binder_name, binder_type, _ = parsed[0]
    class_name, class_type, _ = parsed[1]
    if binder_type.rsplit(".", 1)[-1] != "Binder" or not class_type.startswith("Class<"):
        return None
    opening = helper.structure.find("{", match.start(), match.end())
    closing = _matching_delimiter(helper.structure, opening, "{", "}")
    if closing is None:
        return None
    body = helper.clean[opening + 1:closing]
    direct_bind = re.compile(
        rf"\b{re.escape(binder_name)}\s*\.\s*bind\s*\(\s*"
        rf"{re.escape(class_name)}\s*\)\s*\.\s*in\s*\(\s*SINGLETON\s*\)\s*;"
    )
    component_bind = re.compile(
        rf"\bnewSetBinder\s*\(\s*{re.escape(binder_name)}\s*,\s*"
        rf"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\s*\.class\s*\)"
        rf"\s*\.\s*addBinding\s*\(\s*\)\s*\.\s*to\s*\(\s*"
        rf"{re.escape(class_name)}\s*\)\s*;"
    )
    if len(direct_bind.findall(body)) != 1 or len(component_bind.findall(body)) != 1:
        return None
    return helper, binder_name, class_name


def _class_path(
    resource: _JavaUnit,
    fields: Mapping[tuple[str, str], str],
    by_fqn: Mapping[str, _JavaUnit],
    by_simple: Mapping[str, tuple[_JavaUnit, ...]],
) -> str | None:
    if not any(value.startswith(("jakarta.ws.rs", "javax.ws.rs")) for value in resource.imports):
        return None
    prefix = resource.clean[max(0, resource.class_start - 4096):resource.class_start]
    matches = list(re.finditer(r"@Path\s*\(([^)]{1,1024})\)", prefix, re.DOTALL))
    if not matches:
        return None
    return _constant_value(matches[-1].group(1), resource, fields, by_fqn, by_simple)


def _strip_parameter_annotations(parameter: str) -> str:
    output = list(parameter)
    structure = _mask_literals(parameter)
    index = 0
    while index < len(parameter):
        if parameter[index] != "@":
            index += 1; continue
        match = re.match(r"@[A-Za-z_$][\w.$]*", parameter[index:])
        if match is None:
            index += 1; continue
        end = index + match.end()
        while end < len(parameter) and parameter[end].isspace(): end += 1
        if end < len(parameter) and parameter[end] == "(":
            closing = _matching_delimiter(structure, end)
            end = len(parameter) if closing is None else closing + 1
        for position in range(index, end):
            if output[position] not in "\r\n": output[position] = " "
        index = end
    return "".join(output)


def _parameters(value: str) -> list[tuple[str, str, str]] | None:
    if not value.strip():
        return []
    parts: list[str] = []
    start = 0
    depth = 0
    structure = _mask_literals(value)
    for index, char in enumerate(structure):
        if char in "(<[": depth += 1
        elif char in ")>]": depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index]); start = index + 1
    if depth != 0:
        return None
    parts.append(value[start:])
    result: list[tuple[str, str, str]] = []
    for original in parts:
        stripped = _strip_parameter_annotations(original).strip()
        stripped = re.sub(r"\bfinal\b\s*", "", stripped)
        match = re.fullmatch(r"(?P<type>[A-Za-z_$][\w.$]*(?:\s*<.*>)?(?:\s*\[\s*\])?)\s+(?P<name>[A-Za-z_$][\w$]*)", stripped, re.DOTALL)
        if match is None:
            return None
        type_name = " ".join(match.group("type").split())
        annotations = original
        if re.search(r"@PathParam\b", annotations): kind = "path_parameter"
        elif type_name.rsplit(".", 1)[-1] == "InputStream": kind = "stream"
        elif re.search(r"@(QueryParam|HeaderParam|CookieParam|MatrixParam|FormParam|FormDataParam)\b", annotations): kind = "request_parameter"
        elif re.search(r"@BeanParam\b", annotations): kind = "model_attribute"
        else: kind = "request_body"
        result.append((match.group("name"), type_name, kind))
    return result


def _join_route(prefix: str, class_path: str, method_path: str) -> str:
    parts = [part.strip("/") for part in (prefix, class_path, method_path) if part.strip("/")]
    return "/" + "/".join(parts)


def augment_source_backed_jaxrs_entries(
    rows: Sequence[Mapping[str, object]], source_root: Path,
) -> list[dict[str, object]]:
    """Append only source-proven entries absent from the decoded CodeQL rows."""
    output = [dict(row) for row in rows]
    units = _load_units(source_root)
    if units is None:
        return output
    by_fqn = {unit.fqn: unit for unit in units}
    by_simple: dict[str, tuple[_JavaUnit, ...]] = {}
    for unit in units:
        by_simple[unit.name] = (*by_simple.get(unit.name, ()), unit)
    fields = _constant_fields(units)
    installed = _installed_modules(units, fields, by_fqn, by_simple)
    sisu_installed = _sisu_installed_modules(units, by_fqn, by_simple)
    complete_keys = {
        (row.get("handler_fqn"), row.get("route_or_event"))
        for row in output
        if row.get("coverage_status") == "complete" and row.get("framework") == "jax_rs"
    }
    additions: list[dict[str, object]] = []

    def append_resource_entries(
        resource: _JavaUnit,
        *,
        route_prefix: str,
        registration_fqn: str,
        registration_file: str,
        registration_line: int,
        coverage_note: str,
    ) -> None:
        class_path = _class_path(resource, fields, by_fqn, by_simple)
        if class_path is None:
            return
        for method in _annotated_methods(resource):
            annotations = method.annotations
            verb_match = re.search(r"@(" + "|".join(_HTTP_VERBS) + r")\b", annotations)
            if verb_match is None:
                continue
            path_match = re.search(r"@Path\s*\(([^)]{1,1024})\)", annotations, re.DOTALL)
            method_path = "" if path_match is None else _constant_value(
                path_match.group(1), resource, fields, by_fqn, by_simple,
            )
            if method_path is None:
                continue
            parameters = _parameters(method.params)
            if not parameters:
                continue
            handler_fqn = f"{resource.fqn}.{method.name}"
            route = f"{verb_match.group(1)} {_join_route(route_prefix, class_path, method_path)}"
            if (handler_fqn, route) in complete_keys:
                continue
            handler_line = resource.text.count("\n", 0, method.name_start) + 1
            for input_name, input_type, input_kind in parameters:
                additions.append({
                    "framework": "jax_rs",
                    "protocol": "http",
                    "handler_fqn": handler_fqn,
                    "handler_file": resource.relative,
                    "handler_start_line": handler_line,
                    "registration_kind": "static_registration",
                    "registration_fqn": registration_fqn,
                    "registration_file": registration_file,
                    "registration_start_line": registration_line,
                    "route_or_event": route,
                    "auth_context": "unknown",
                    "attacker_input_name": input_name,
                    "attacker_input_type": input_type,
                    "attacker_input_kind": input_kind,
                    "materialization_phase": "before_handler",
                    "coverage_status": "complete",
                    "coverage_note": coverage_note,
                })
            complete_keys.add((handler_fqn, route))

    for module in units:
        if (
            "com.facebook.airlift.jaxrs.JaxrsBinder.jaxrsBinder" not in module.imports
            or "com.facebook.airlift.configuration.AbstractConfigurationAwareModule" not in module.imports
            or not re.search(r"\bextends\s+AbstractConfigurationAwareModule\b", module.tail)
        ):
            continue
        setup_bodies = _method_bodies(module, "setup")
        if len(setup_bodies) != 1:
            continue
        body_start, body_end = setup_bodies[0]
        body = module.clean[body_start:body_end]
        bindings: dict[str, list[tuple[_JavaUnit, re.Match[str]]]] = {}
        for bind in _AIRLIFT_JAXRS_BIND.finditer(body):
            resource = _resolve_type(bind.group(1), module, by_fqn, by_simple)
            if resource is not None:
                bindings.setdefault(resource.fqn, []).append((resource, bind))
        for resource_bindings in bindings.values():
            if len(resource_bindings) != 1:
                continue
            resource, bind = resource_bindings[0]
            append_resource_entries(
                resource,
                route_prefix="/",
                registration_fqn="com.facebook.airlift.jaxrs.JaxrsBinder.bind",
                registration_file=module.relative,
                registration_line=module.text.count("\n", 0, body_start + bind.start()) + 1,
                coverage_note="airlift_jaxrs_source_registration",
            )

    for module_fqn, installations in sorted(sisu_installed.items()):
        if len(installations) != 1:
            continue
        module = by_fqn.get(module_fqn)
        if module is None or (
            "com.google.inject.Binder" not in module.imports
            or "com.google.inject.Module" not in module.imports
            or not re.search(
                r"\bimplements\s+(?:[A-Za-z_$][\w$]*\s*,\s*)*Module\b",
                module.tail,
            )
        ):
            continue
        configure_bodies = _method_bodies(module, "configure")
        if len(configure_bodies) != 1:
            continue
        body_start, body_end = configure_bodies[0]
        body = module.clean[body_start:body_end]
        bindings: dict[
            str,
            list[tuple[_JavaUnit, re.Match[str], _JavaUnit, str]],
        ] = {}
        for call in _SOURCE_BINDING_HELPER_CALL.finditer(body):
            helper = _source_binding_helper(
                module, call.group("helper"), by_fqn
            )
            if helper is None:
                continue
            helper_unit, _, _ = helper
            resource = _resolve_type(
                call.group("resource"), module, by_fqn, by_simple
            )
            if resource is not None:
                bindings.setdefault(resource.fqn, []).append(
                    (resource, call, helper_unit, call.group("helper"))
                )
        for resource_bindings in bindings.values():
            if len(resource_bindings) != 1:
                continue
            resource, call, helper_unit, helper_name = resource_bindings[0]
            append_resource_entries(
                resource,
                route_prefix="/",
                registration_fqn=f"{helper_unit.fqn}.{helper_name}",
                registration_file=module.relative,
                registration_line=module.text.count(
                    "\n", 0, body_start + call.start()
                ) + 1,
                coverage_note="sisu_named_guice_source_registration",
            )

    for module_fqn, installations in sorted(installed.items()):
        if len(installations) != 1:
            continue
        _, route_prefix = next(iter(installations))
        module = by_fqn.get(module_fqn)
        if module is None:
            continue
        dropwizard_module = (
            "ru.vyarus.dropwizard.guice.module.support.DropwizardAwareModule" in module.imports
            and re.search(r"\bextends\s+DropwizardAwareModule\b", module.tail)
        )
        guice_module = (
            "com.google.inject.AbstractModule" in module.imports
            and re.search(r"\bextends\s+AbstractModule\b", module.tail)
        )
        if not dropwizard_module and not guice_module:
            continue
        configure_bodies = _method_bodies(module, "configure")
        if len(configure_bodies) != 1:
            continue
        body_start, body_end = configure_bodies[0]
        body = module.clean[body_start:body_end]
        bindings: dict[str, list[tuple[_JavaUnit, re.Match[str]]]] = {}
        for bind in _BIND.finditer(body):
            resource = _resolve_type(bind.group(1), module, by_fqn, by_simple)
            if resource is None:
                continue
            bindings.setdefault(resource.fqn, []).append((resource, bind))
        for resource_bindings in bindings.values():
            if len(resource_bindings) != 1:
                continue
            resource, bind = resource_bindings[0]
            registration_line = module.text.count("\n", 0, body_start + bind.start()) + 1
            append_resource_entries(
                resource,
                route_prefix=route_prefix,
                registration_fqn=f"{module.fqn}.bind",
                registration_file=module.relative,
                registration_line=registration_line,
                coverage_note="dropwizard_guice_source_registration",
            )
    additions.sort(key=lambda row: tuple(str(row[key]) for key in (
        "handler_file", "handler_start_line", "route_or_event", "attacker_input_name",
    )))
    output.extend(additions)
    return output


__all__ = ["augment_source_backed_jaxrs_entries"]
