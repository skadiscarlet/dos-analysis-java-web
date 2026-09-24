from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.reachability.models import EntrySecurityFact


_MAX_SOURCE_BYTES = 512 * 1024
_DEPLOYMENT_VALUES = frozenset(
    {"default_enabled", "default_disabled", "optional", "unknown"}
)
_SIMPLE_POSITIVE_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _bounded_source_text(source_root: Path, relative_file: str) -> str | None:
    relative = Path(relative_file)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        return None
    try:
        root = source_root.resolve(strict=True)
        candidate = root
        for part in relative.parts:
            candidate /= part
            if candidate.is_symlink():
                return None
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        descriptor = os.open(
            resolved,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_SOURCE_BYTES:
                return None
            raw = os.read(descriptor, _MAX_SOURCE_BYTES + 1)
            if len(raw) != info.st_size or len(raw) > _MAX_SOURCE_BYTES:
                return None
        finally:
            os.close(descriptor)
        return raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError, RuntimeError):
        return None


def extract_entry_security_fallback(
    entries: Sequence[Mapping[str, object]], source_root: Path
) -> tuple[EntrySecurityFact, ...]:
    """Publish source-text observations as partial facts only.

    The fallback is deliberately unable to prove public or default-enabled
    reachability. Complete facts are reserved for the typed CodeQL query.
    """

    facts: list[EntrySecurityFact] = []
    for entry in entries:
        entry_id = entry.get("entry_id")
        handler = entry.get("handler")
        if not isinstance(entry_id, str) or not isinstance(handler, Mapping):
            continue
        file_name, line = handler.get("file"), handler.get("start_line")
        if (
            not isinstance(file_name, str)
            or not isinstance(line, int)
            or isinstance(line, bool)
            or line < 1
        ):
            continue
        value, kind = "security_extraction_not_modeled", "dependency_coverage"
        declared_context = entry.get("auth_context")
        if declared_context in {"unauthenticated", "low_privilege", "privileged"}:
            value, kind = f"{declared_context}_annotation", "annotation"
        else:
            content = _bounded_source_text(source_root, file_name)
            if content is not None:
                lines = content.splitlines()
                index = min(max(line - 1, 0), max(len(lines) - 1, 0))
                selected: list[str] = []
                if lines:
                    selected.append(lines[index])
                    for previous in reversed(lines[max(0, index - 8):index]):
                        stripped = previous.strip()
                        if stripped.startswith("@"):
                            selected.insert(0, previous)
                        elif stripped:
                            break
                window = "\n".join(selected)
                compact = "".join(window.split())
                if (
                    "@PermitAll" in window
                    or "@AnonymousAllowed" in window
                    or ("@PreAuthorize" in window and "permitAll()" in compact)
                ):
                    value, kind = "unauthenticated_annotation", "annotation"
                elif "@PreAuthorize" in window and "isAuthenticated()" in compact:
                    value, kind = "low_privilege_annotation", "annotation"
                elif (
                    "@RolesAllowed" in window
                    or "@Secured" in window
                    or "@PreAuthorize" in window
                    or "@ServletSecurity" in window
                ):
                    value, kind = "privileged_annotation", "annotation"
        facts.append(EntrySecurityFact(entry_id, kind, file_name, line, value, "partial"))
    return tuple(sorted(facts, key=lambda fact: fact.fact_id))


def extract_entry_deployment_defaults(
    entries: Sequence[Mapping[str, object]],
    *,
    excluded_entry_ids: frozenset[str] = frozenset(),
) -> tuple[EntrySecurityFact, ...]:
    """Turn a normalized complete registration into positive default evidence.

    This does not infer deployment from the absence of a condition.  The Entry
    normalizer admits only complete registration rows.  A typed conditional
    deployment fact replaces this default rather than conflicting with it.
    """

    facts: list[EntrySecurityFact] = []
    for entry in entries:
        entry_id = entry.get("entry_id")
        registration = entry.get("registration")
        if (
            not isinstance(entry_id, str)
            or entry_id in excluded_entry_ids
            or not isinstance(registration, Mapping)
        ):
            continue
        location = registration.get("file")
        line = registration.get("start_line")
        if (
            not isinstance(location, str)
            or not location
            or not isinstance(line, int)
            or isinstance(line, bool)
            or line < 1
        ):
            continue
        facts.append(
            EntrySecurityFact(
                entry_id,
                "deployment_gate",
                location,
                line,
                "default_enabled",
                "complete",
            )
        )
    return tuple(sorted(facts, key=lambda fact: fact.fact_id))


def _route_path(route: str) -> str:
    value = route.strip()
    if " " in value and value.split(" ", 1)[0] in {
        "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS",
    }:
        value = value.split(" ", 1)[1]
    while "//" in value:
        value = value.replace("//", "/")
    if len(value) > 1:
        value = value.rstrip("/")
    return value


def _route_matches(matcher: str, route: str) -> bool:
    if matcher in {"", "dynamic_matcher", "*"}:
        return False
    # A method-qualified rule must not authorize a different method (or an
    # entry whose method is unknown). Path-only matchers retain their scope.
    methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
    matcher_parts, route_parts = matcher.strip().split(None, 1), route.strip().split(None, 1)
    matcher_method = matcher_parts[0] if len(matcher_parts) == 2 and matcher_parts[0] in methods else None
    route_method = route_parts[0] if len(route_parts) == 2 and route_parts[0] in methods else None
    if matcher_method is not None and route_method != matcher_method:
        return False
    expected, actual = _route_path(matcher), _route_path(route)
    if expected.endswith("/**"):
        prefix = expected[:-3].rstrip("/")
        return actual == prefix or actual.startswith(prefix + "/")
    if expected.endswith("/*"):
        prefix = expected[:-2].rstrip("/")
        return actual.startswith(prefix + "/") and "/" not in actual[len(prefix) + 1:]
    return expected == actual


def bind_entry_security_rows(
    rows: Sequence[Mapping[str, object]],
    entries: Sequence[Mapping[str, object]],
) -> tuple[EntrySecurityFact, ...]:
    """Bind typed security rows by route semantics or exact handler identity."""

    facts: dict[str, EntrySecurityFact] = {}
    for row in rows:
        route = row.get("route_or_event")
        concrete_route = (
            isinstance(route, str) and bool(route) and route != "dynamic_matcher"
        )
        candidates: list[Mapping[str, object]] = []
        if concrete_route:
            candidates = [
                entry
                for entry in entries
                if isinstance(entry.get("route_or_event"), str)
                and _route_matches(route, str(entry["route_or_event"]))
            ]
        else:
            handler_fqn = row.get("handler_fqn")
            handler_file = row.get("handler_file")
            handler_line = row.get("handler_start_line")
            for entry in entries:
                handler = entry.get("handler")
                if not isinstance(handler, Mapping):
                    continue
                if (
                    handler.get("callable") == handler_fqn
                    and handler.get("file") == handler_file
                    and handler.get("start_line") == handler_line
                ):
                    candidates.append(entry)
            # Typed method annotations/constraints and deployment gates apply
            # to the method, not just one of its registered route aliases.
            # Dynamic/untyped matchers must not gain that authority.
            handler_scoped = route == "" and row.get("kind") in {
                "annotation", "servlet_constraint", "deployment_gate",
            }
            if not handler_scoped and len(candidates) != 1:
                continue
        if not candidates:
            continue
        kind = row.get("kind")
        value = row.get("value")
        fact_file = row.get("fact_file")
        fact_line = row.get("fact_start_line")
        coverage = row.get("coverage_status")
        if not all(
            isinstance(item, str) and item
            for item in (kind, value, fact_file, coverage)
        ):
            continue
        if not isinstance(fact_line, int) or isinstance(fact_line, bool) or fact_line < 1:
            continue
        for candidate in candidates:
            entry_id = candidate.get("entry_id")
            if not isinstance(entry_id, str) or not entry_id:
                continue
            fact = EntrySecurityFact(
                entry_id,
                str(kind),
                str(fact_file),
                fact_line,
                str(value),
                str(coverage),
            )
            facts[fact.fact_id] = fact
    return tuple(sorted(facts.values(), key=lambda fact: fact.fact_id))


def _configuration_index(
    configuration_facts: Iterable[ModeledConfigurationFact | Mapping[str, object]],
) -> dict[str, object]:
    values_by_key: dict[str, dict[tuple[type[object], object], object]] = {}
    for raw in configuration_facts:
        fact = raw if isinstance(raw, ModeledConfigurationFact) else ModeledConfigurationFact.from_dict(raw)
        if fact.status == "known" and fact.default_effective:
            typed_value = (type(fact.value), fact.value)
            values_by_key.setdefault(fact.key, {})[typed_value] = fact.value
    return {
        key: next(iter(typed_values.values()))
        for key, typed_values in values_by_key.items()
        if len(typed_values) == 1
    }


def resolve_deployment_status(
    facts: Iterable[EntrySecurityFact],
    configuration_facts: Iterable[ModeledConfigurationFact | Mapping[str, object]],
) -> str:
    """Resolve a default deployment gate; absence and conflicts stay unknown."""

    configuration = _configuration_index(configuration_facts)
    statuses: set[str] = set()
    for fact in facts:
        if fact.kind != "deployment_gate" or fact.coverage != "complete":
            continue
        if fact.value in _DEPLOYMENT_VALUES:
            statuses.add(fact.value)
            continue
        if fact.value.startswith("profile:"):
            required = fact.value.removeprefix("profile:").strip()
            if _SIMPLE_POSITIVE_PROFILE.fullmatch(required) is None:
                continue
            active = configuration.get("spring.profiles.active")
            if isinstance(active, str):
                profiles = {item.strip() for item in active.split(",") if item.strip()}
                statuses.add("default_enabled" if required in profiles else "default_disabled")
            continue
        if fact.value.startswith("conditional_property:"):
            expression = fact.value.removeprefix("conditional_property:")
            key, separator, expected = expression.partition("=")
            if separator and key in configuration:
                actual = configuration[key]
                statuses.add(
                    "default_enabled"
                    if str(actual).lower() == expected.strip().lower()
                    else "default_disabled"
                )
    return next(iter(statuses)) if len(statuses) == 1 else "unknown"


__all__ = [
    "bind_entry_security_rows",
    "extract_entry_deployment_defaults",
    "extract_entry_security_fallback",
    "resolve_deployment_status",
]
