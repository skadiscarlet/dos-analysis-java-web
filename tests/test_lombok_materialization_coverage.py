"""Real Lombok annotation-processor regression for request read-all lifecycle coverage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/fixtures/semantic_materialization_coverage/src/main/java"
EXTRA = ROOT / "tests/fixtures/semantic_materialization_lombok/src/main/java"
RUN = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"


def _lombok_jar() -> Path | None:
    root = Path.home() / ".m2/repository/org/projectlombok/lombok"
    candidates = list(root.glob("*/lombok-*.jar"))
    if not candidates:
        return None
    def version(path: Path) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in path.parent.name.split("."))
        except ValueError:
            return ()
    return max(candidates, key=version)


@pytest.mark.skipif(not RUN, reason="explicit self-owned CodeQL fixture opt-in")
def test_lombok_sneakythrows_does_not_hide_filter_wrapper_lifecycle(tmp_path: Path) -> None:
    codeql, javac, lombok = shutil.which("codeql"), shutil.which("javac"), _lombok_jar()
    if not codeql or not javac or lombok is None:
        pytest.skip("requested Lombok/CodeQL source validation dependencies unavailable")

    source = tmp_path / "source"
    shutil.copytree(BASE, source)
    for item in EXTRA.rglob("*.java"):
        target = source / item.relative_to(EXTRA)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.read_bytes())

    classes = tmp_path / "classes"
    classes.mkdir()
    database_path = tmp_path / "database"
    java_files = [str(path.relative_to(source)) for path in sorted(source.rglob("*.java"))]
    javac_command = " ".join(
        [
            shutil.which("javac") or "javac",
            "-cp", str(lombok),
            "-processorpath", str(lombok),
            "-d", str(classes),
            *java_files,
        ]
    )
    completed = subprocess.run(
        [codeql, "database", "create", str(database_path), "--language=java", "--source-root=.", f"--command={javac_command}"],
        cwd=source,
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    database = validate_database(database_path)
    query = ROOT / "dosweb/codeql/pack/dosweb/Lifecycle/LifecycleCoverage.ql"
    result = run_query(query, database, tmp_path / "query", codeql_binary=str(_codeql_wrapper(tmp_path)), timeout_seconds=600)
    rows = decode_bqrs_json(
        "lifecycle_coverage",
        json.loads(result.decoded_path.read_text()),
        DecodeSource(database.source_root, result.query_sha256),
    )
    lines = (source / "fixture/lombok/LombokMaterializationFixture.java").read_text().splitlines()
    anchors = {line.split("CASE:", 1)[1].strip(): index for index, line in enumerate(lines, 1) if "CASE:" in line}

    metadata = [
        row for row in rows
        if row["anchor_file"].endswith("LombokMaterializationFixture.java")
        and row["anchor_start_line"] == anchors["lombok-metadata"]
    ]
    size_guard = [
        row for row in rows
        if row["anchor_file"].endswith("LombokMaterializationFixture.java")
        and row["anchor_start_line"] == anchors["lombok-size-guard"]
    ]
    assert len(metadata) == 3 and {row["family"] for row in metadata} == {"guard", "bound", "release"}
    assert all(row["coverage_status"] == "complete" for row in metadata), metadata
    assert len(size_guard) == 3 and {row["family"] for row in size_guard} == {"guard", "bound", "release"}
    assert all(row["coverage_status"] == "partial" for row in size_guard), size_guard
