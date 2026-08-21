"""Reusable real Java fixture CodeQL databases for opt-in tests.

The cache is process-local and stored beneath the system temporary directory.
No database is written into the repository or committed artifacts.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile

from dosweb.codeql.database import DatabaseInfo, validate_database


_CODEQL = shutil.which("codeql") or "/usr/bin/codeql"
_JAVAC = shutil.which("javac") or "/usr/bin/javac"
_CACHE_ROOT = Path(tempfile.gettempdir()) / f"dosweb-fixture-codeql-{os.getpid()}"


@lru_cache(maxsize=16)
def fixture_database(source_root_text: str) -> DatabaseInfo:
    """Compile every Java source under ``source_root`` into one finalized DB.

    Callers must opt in at the test level. The cache key is the resolved source
    path, and each process owns an isolated temporary cache root.
    """
    source_root = Path(source_root_text).resolve(strict=True)
    java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
    if not java_files:
        raise AssertionError(f"fixture has no Java sources: {source_root}")
    _CACHE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    slug = hashlib.sha256(str(source_root).encode("utf-8")).hexdigest()[:16]
    database = _CACHE_ROOT / f"{slug}.db"
    classes = _CACHE_ROOT / f"{slug}.classes"
    if database.exists():
        return validate_database(database)
    classes.mkdir(mode=0o700, parents=True, exist_ok=True)
    command = " ".join(
        [shlex.quote(_JAVAC), "-d", shlex.quote(str(classes)), *(shlex.quote(str(item)) for item in java_files)]
    )
    completed = subprocess.run(
        [
            _CODEQL,
            "database",
            "create",
            str(database),
            "--language=java",
            f"--source-root={source_root}",
            f"--command={command}",
            "--overwrite",
        ],
        cwd=source_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=600,
    )
    if completed.returncode:
        raise AssertionError(f"CodeQL fixture DB build failed for {source_root}:\n{completed.stderr[-4000:]}")
    return validate_database(database)


__all__ = ["fixture_database"]
