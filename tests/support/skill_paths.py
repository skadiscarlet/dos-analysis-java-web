"""Locate the outer project Java Web DoS skills without using ~/.codex/skills.

The worktree does not vendor `.agents/skills`. The project-local installed skills live
in the outer repository `.agents/skills/` and are read-only. This helper only
discovers paths and never launches hunter or validator workers.
"""
from __future__ import annotations

import os
from pathlib import Path


REQUIRED_SKILLS = (
    "java-web-dos-hunter",
    "java-web-dos-batch-hunter",
    "java-web-dos-dynamic-validator",
)
_AGGREGATOR_RELATIVE = Path("java-web-dos-dynamic-validator") / "scripts" / "aggregate_dynamic_validation.py"


def _is_skills_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    return all((path / name / "SKILL.md").is_file() for name in REQUIRED_SKILLS)


def discover_skills_root() -> Path | None:
    """Return the first existing project skills root, or None if it is absent."""
    candidates: list[Path] = []
    env = os.environ.get("DOSWEB_SKILLS_ROOT", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / ".agents" / "skills")
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if _is_skills_root(resolved):
            return resolved
    return None


def skill_markdown(name: str) -> Path | None:
    root = discover_skills_root()
    if root is None:
        return None
    path = root / name / "SKILL.md"
    return path if path.is_file() else None


def aggregator_script_path() -> Path | None:
    root = discover_skills_root()
    if root is None:
        return None
    path = root / _AGGREGATOR_RELATIVE
    return path if path.is_file() else None


def missing_skills_reason() -> str:
    return (
        "project Java Web DoS skills missing under .agents/skills "
        f"(required {', '.join(REQUIRED_SKILLS)}; looked from this worktree "
        "upward, not ~/.codex/skills)"
    )
