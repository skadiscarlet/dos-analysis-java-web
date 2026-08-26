from __future__ import annotations

import re

_SENSITIVE_KEY = re.compile(
    r"(^|[._-])(password|passwd|pwd|secret|token|credential|api[._-]?key|private[._-]?key|client[._-]?secret|access[._-]?key|keystore|truststore)([._-]|$)",
    re.IGNORECASE,
)
_RELEVANT_KEY = re.compile(
    r"(max|limit|cap|capacity|quota|size|timeout|queue|buffer|payload|body|upload|multipart|content[._-]?length|request|security|auth|anonymous|permit|profile|feature|module|enabled|conditional)",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"\$\{|\{\{")
_SAFE_ENUMS = {
    "enabled", "disabled", "finite", "unbounded", "none", "anonymous",
    "authenticated", "permitall", "denyall", "true", "false",
}
_UNIT = re.compile(r"([0-9]+)\s*(b|kb|kib|mb|mib|gb|gib|ms|s|min|h)", re.IGNORECASE)


def modeled_key_allowed(key: object) -> bool:
    return (
        isinstance(key, str)
        and bool(key)
        and "\x00" not in key
        and _SENSITIVE_KEY.search(key) is None
        and _RELEVANT_KEY.search(key) is not None
        and len(key.encode("utf-8")) <= 1024
    )


def normalize_modeled_value(key: str, value: object) -> str | int | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "\x00" in text or _PLACEHOLDER.search(text) or len(text.encode("utf-8")) > 1024:
        return None
    lowered = text.lower()
    if key.lower() == "spring.profiles.active" and re.fullmatch(
        r"[A-Za-z0-9_.-]+(?:\s*,\s*[A-Za-z0-9_.-]+)*", text
    ):
        return ",".join(part.strip() for part in text.split(","))
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"-?[0-9]+", text):
        try:
            return int(text)
        except ValueError:
            return None
    if lowered in _SAFE_ENUMS:
        return lowered
    match = _UNIT.fullmatch(lowered)
    if match is None:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit in {"b", "kb", "kib", "mb", "mib", "gb", "gib"}:
        multiplier = {
            "b": 1, "kb": 1000, "kib": 1024, "mb": 1000**2,
            "mib": 1024**2, "gb": 1000**3, "gib": 1024**3,
        }[unit]
    elif "timeout" in key.lower():
        multiplier = {"ms": 1, "s": 1000, "min": 60_000, "h": 3_600_000}.get(unit)
        if multiplier is None:
            return None
    else:
        return None
    result = amount * multiplier
    return result if result <= 2**63 - 1 else None


__all__ = ["modeled_key_allowed", "normalize_modeled_value"]
