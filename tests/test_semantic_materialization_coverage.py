"""Real production CodeQL on repository-owned Java; no target execution."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import pytest
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/semantic_materialization_coverage/src/main/java"
RUN = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
pytestmark = pytest.mark.skipif(not RUN, reason="explicit self-owned CodeQL fixture opt-in")

@pytest.fixture(scope="module")
def extracted():
    codeql, javac = shutil.which("codeql"), shutil.which("javac")
    assert codeql and javac, "requested real-source validation requires CodeQL and javac"
    selected = os.environ.get("DOSWEB_SEMANTIC_QA_OUTPUT")
    holder = None
    if selected:
        output = Path(selected).resolve(); output.mkdir(parents=True, exist_ok=False)
    else:
        holder = tempfile.TemporaryDirectory(prefix="dosweb-semantic-source-")
        output = Path(holder.name)
    source = output / "source"
    shutil.copytree(FIXTURE, source)
    original = {str(p.relative_to(FIXTURE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.rglob("*.java")}
    classes = output / "classes"; classes.mkdir()
    db = output / "database"
    command = [codeql, "database", "create", str(db), "--language=java", f"--source-root={source}",
        f"--command={javac} -d {classes} " + " ".join(str(p.relative_to(source)) for p in sorted(source.rglob("*.java")))]
    started = time.monotonic()
    compiled = subprocess.run(command, cwd=source, text=True, capture_output=True, timeout=180)
    (output / "database-build.txt").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr[-4000:]
    database = validate_database(db)
    manifest = {"source_hashes": original, "queries": [], "source_kind": "real_source_codeql", "target_program_executed": False}
    rows = {}
    wrapper = _codeql_wrapper(output)
    for relative, kind in (
        ("Growth/InputMaterialization.ql", "growth"),
        ("Lifecycle/LifecycleCoverage.ql", "lifecycle_coverage"),
        ("Lifecycle/SynchronousReleaseCandidates.ql", "release"),
    ):
        query = ROOT / "dosweb/codeql/pack/dosweb" / relative
        t = time.monotonic()
        result = run_query(query, database, output / query.stem, codeql_binary=str(wrapper), timeout_seconds=600)
        rows[kind] = decode_bqrs_json(kind, json.loads(result.decoded_path.read_text()), DecodeSource(database.source_root, result.query_sha256))
        manifest["queries"].append({"query": relative, "sha256":result.query_sha256,"seconds":time.monotonic()-t,"rows":len(rows[kind])})
        (output / (kind + ".json")).write_text(json.dumps(rows[kind], indent=2))
        (output / "run-manifest.json").write_text(json.dumps(manifest,indent=2))
    assert original == {str(p.relative_to(FIXTURE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.rglob("*.java")}
    lines=(source/"fixture/semantics/MaterializationFixture.java").read_text().splitlines()
    anchors={line.split("CASE:",1)[1].strip():i for i,line in enumerate(lines,1) if "CASE:" in line}
    manifest["seconds"]=time.monotonic()-started
    (output/"run-manifest.json").write_text(json.dumps(manifest,indent=2))
    yield rows, anchors
    if holder: holder.cleanup()

@pytest.mark.parametrize("case", ["plain", "library", "wrapper", "filter-wrapper-metadata"])
def test_exact_straight_line_request_read_has_scanned_local_families(extracted,case):
    rows, anchors = extracted
    growth=[r for r in rows['growth'] if r['site_start_line']==anchors[case] and r['site_file'].endswith('MaterializationFixture.java')]
    assert growth and all(r['coverage_status']=='complete' for r in growth)
    coverage=[r for r in rows['lifecycle_coverage'] if r['anchor_start_line']==anchors[case] and r['anchor_file'].endswith('MaterializationFixture.java')]
    assert len(coverage)==3 and {r['family'] for r in coverage}=={'guard','bound','release'}
    assert all(r['coverage_status']=='complete' for r in coverage), coverage

@pytest.mark.parametrize("case", ["conditional", "helper", "limited", "local", "guarded-wrapper", "closed", "reassigned", "spring-plain", "spring-library", "caller-guarded-wrapper", "filter-wrapper-size-guard"])
def test_unmodeled_control_stream_or_effect_does_not_gain_complete_coverage(extracted,case):
    rows, anchors = extracted
    coverage=[r for r in rows['lifecycle_coverage'] if r['anchor_start_line']==anchors[case] and r['anchor_file'].endswith('MaterializationFixture.java')]
    assert coverage, case
    assert all(r['coverage_status']=='partial' for r in coverage), coverage

def test_closing_request_stream_does_not_release_materialized_heap_bytes(extracted):
    rows, anchors = extracted
    assert not [r for r in rows['release'] if r['anchor_start_line']==anchors['closed'] and r['anchor_file'].endswith('MaterializationFixture.java')]
