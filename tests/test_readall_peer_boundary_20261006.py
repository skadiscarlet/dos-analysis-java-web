"""Independent source-only regression: effects must not disappear at wrapper boundaries."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import pytest
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/fixtures/semantic_materialization_coverage/src/main/java"
CASES = {
    "metadata_only": ('if ("application/json".equals(request.getContentType())) { chain.doFilter(new WMetadata(request), response); return; }', "WMetadata", "complete"),
    "constructor_gate": ('new RequestGate(request); chain.doFilter(new WConstructor(request), response);', "WConstructor", "partial"),
    "erased_alias_gate": ('Object alias = request; Gate.check(alias); chain.doFilter(new WErased(request), response);', "WErased", "partial"),
    "preceding_chain": ('chain.doFilter(raw, response); chain.doFilter(new WChain(request), response);', "WChain", "partial"),
    "field_escape_gate": ('this.saved = request; checkSaved(); chain.doFilter(new WField(request), response);', "WField", "partial"),
}


def _source() -> str:
    parts = ['''package fixture.peer;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import javax.servlet.*;
import javax.servlet.http.*;
import org.springframework.util.StreamUtils;
class RequestGate {
    RequestGate(HttpServletRequest request) throws IOException {
        if (request.getContentLengthLong() > 1024) throw new IOException();
    }
}
class Gate {
    static void check(Object value) throws IOException {
        if (((HttpServletRequest) value).getContentLengthLong() > 1024) throw new IOException();
    }
}
''']
    for index, (case, (statements, wrapper, _expected)) in enumerate(CASES.items()):
        extra = ('''private HttpServletRequest saved;
    private void checkSaved() throws IOException {
        if (saved.getContentLengthLong() > 1024) throw new IOException();
    }''' if case == "field_escape_gate" else "")
        parts.append(f'''class Filter{index} implements Filter {{
    {extra}
    public void doFilter(ServletRequest raw, ServletResponse response, FilterChain chain) throws IOException {{
        HttpServletRequest request = (HttpServletRequest) raw;
        {statements}
    }}
}}
class {wrapper} extends HttpServletRequestWrapper {{
    final String body;
    {wrapper}(HttpServletRequest request) throws IOException {{
        super(request);
        body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); // CASE:{case}
    }}
}}
''')
    return "\n".join(parts)


@pytest.fixture(scope="module")
def peer_rows(tmp_path_factory):
    if os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") != "1":
        pytest.skip("explicit self-owned CodeQL fixture opt-in required")
    codeql, javac = shutil.which("codeql"), shutil.which("javac")
    assert codeql and javac, "opted-in validation requires CodeQL and javac"
    selected = os.environ.get("DOSWEB_PEER_BOUNDARY_OUTPUT")
    output = Path(selected).resolve() if selected else tmp_path_factory.mktemp("peer-boundary")
    if selected:
        output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    shutil.copytree(BASE, source)
    java_file = source / "fixture/peer/PeerReadAll.java"
    java_file.parent.mkdir(parents=True, exist_ok=True)
    java_file.write_text(_source())
    classes = output / "classes"
    classes.mkdir()
    db_path = output / "database"
    javac_args = [javac, "-d", str(classes), *(str(p.relative_to(source)) for p in sorted(source.rglob("*.java")))]
    build = subprocess.run(
        [codeql, "database", "create", str(db_path), "--language=java", "--source-root=.", f"--command={shlex.join(javac_args)}"],
        cwd=source, capture_output=True, text=True, timeout=240, check=False,
    )
    (output / "build.log").write_text(build.stdout + build.stderr)
    assert build.returncode == 0, build.stderr[-4000:]
    database = validate_database(db_path)
    pack = Path(os.environ.get("DOSWEB_PEER_QUERY_PACK", str(ROOT / "codeql"))).resolve()
    query = pack / "dosweb/Lifecycle/LifecycleCoverage.ql"
    files = [p for p in pack.rglob("*") if p.is_file() and p.suffix in {".ql", ".qll", ".yml"}]
    before = {str(p.relative_to(pack)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    result = run_query(query, database, output / "query", codeql_binary=str(_codeql_wrapper(output)), timeout_seconds=600)
    after = {str(p.relative_to(pack)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    assert before == after, "query pack changed during validation"
    rows = decode_bqrs_json("lifecycle_coverage", json.loads(result.decoded_path.read_text()), DecodeSource(database.source_root, result.query_sha256))
    anchors = {line.split("CASE:", 1)[1].strip(): n for n, line in enumerate(java_file.read_text().splitlines(), 1) if "CASE:" in line}
    relevant = [r for r in rows if r["anchor_file"].endswith("PeerReadAll.java")]
    (output / "rows.json").write_text(json.dumps(relevant, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({
        "query_pack_hashes": before,
        "source_sha256": hashlib.sha256(java_file.read_bytes()).hexdigest(),
        "anchors": anchors,
        "cases": {case: spec[2] for case, spec in CASES.items()},
        "target_program_executed": False, "third_party_scan": False,
    }, indent=2) + "\n")
    return relevant, anchors


@pytest.mark.parametrize("case", tuple(CASES))
def test_request_effects_are_not_lost_at_filter_wrapper_boundary(peer_rows, case):
    rows, anchors = peer_rows
    selected = [r for r in rows if r["anchor_start_line"] == anchors[case]]
    assert len(selected) == 3 and {r["family"] for r in selected} == {"guard", "bound", "release"}, selected
    assert all(r["coverage_status"] == CASES[case][2] for r in selected), {"case": case, "rows": selected}


LOMBOK_CASES = {
    "generated_only": "complete",
    "same_line_catch_effect": "partial",
    "same_line_finally_effect": "partial",
}


def _lombok_source() -> str:
    return '''package fixture.peer;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import javax.servlet.*;
import javax.servlet.http.*;
import org.springframework.util.StreamUtils;
import lombok.SneakyThrows;
class LFilter0 implements Filter {
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain) throws IOException {
        chain.doFilter(new LPlain((HttpServletRequest)request), response);
    }
}
class LFilter1 implements Filter {
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain) throws IOException {
        chain.doFilter(new LCatch((HttpServletRequest)request), response);
    }
}
class LFilter2 implements Filter {
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain) throws IOException {
        chain.doFilter(new LFinally((HttpServletRequest)request), response);
    }
}
class LPlain extends HttpServletRequestWrapper {
    String body;
    @SneakyThrows
    LPlain(HttpServletRequest request) {
        super(request);
        body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); // CASE:generated_only
    }
}
class LCatch extends HttpServletRequestWrapper {
    String body; static int caught;
    @SneakyThrows LCatch(HttpServletRequest request) { super(request); try { body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); } catch (Throwable failure) { caught++; throw lombok.Lombok.sneakyThrow(failure); } } // CASE:same_line_catch_effect
}
class LFinally extends HttpServletRequestWrapper {
    String body; static int finalized;
    @SneakyThrows LFinally(HttpServletRequest request) { super(request); try { body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); } catch (Throwable failure) { throw lombok.Lombok.sneakyThrow(failure); } finally { finalized++; } } // CASE:same_line_finally_effect
}
'''


@pytest.fixture(scope="module")
def lombok_peer_rows(tmp_path_factory):
    if os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") != "1":
        pytest.skip("explicit self-owned CodeQL fixture opt-in required")
    from tests.test_lombok_materialization_coverage import _lombok_jar
    jar = _lombok_jar()
    codeql, javac = shutil.which("codeql"), shutil.which("javac")
    assert jar and codeql and javac, "opted-in Lombok validation requires dependencies"
    selected = os.environ.get("DOSWEB_PEER_LOMBOK_OUTPUT")
    output = Path(selected).resolve() if selected else tmp_path_factory.mktemp("peer-lombok")
    if selected:
        output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    shutil.copytree(BASE, source)
    java_file = source / "fixture/peer/PeerLombok.java"
    java_file.parent.mkdir(parents=True, exist_ok=True)
    java_file.write_text(_lombok_source())
    classes = output / "classes"
    classes.mkdir()
    db_path = output / "database"
    args = [javac, "-cp", str(jar), "-processorpath", str(jar), "-d", str(classes), *(str(p.relative_to(source)) for p in sorted(source.rglob("*.java")))]
    build = subprocess.run(
        [codeql, "database", "create", str(db_path), "--language=java", "--source-root=.", f"--command={shlex.join(args)}"],
        cwd=source, capture_output=True, text=True, timeout=240, check=False,
    )
    (output / "build.log").write_text(build.stdout + build.stderr)
    assert build.returncode == 0, build.stderr[-4000:]
    database = validate_database(db_path)
    pack = Path(os.environ.get("DOSWEB_PEER_QUERY_PACK", str(ROOT / "codeql"))).resolve()
    query = pack / "dosweb/Lifecycle/LifecycleCoverage.ql"
    files = [p for p in pack.rglob("*") if p.is_file() and p.suffix in {".ql", ".qll", ".yml"}]
    before = {str(p.relative_to(pack)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    result = run_query(query, database, output / "query", codeql_binary=str(_codeql_wrapper(output)), timeout_seconds=600)
    after = {str(p.relative_to(pack)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    assert before == after, "query pack changed during validation"
    rows = decode_bqrs_json("lifecycle_coverage", json.loads(result.decoded_path.read_text()), DecodeSource(database.source_root, result.query_sha256))
    anchors = {line.split("CASE:", 1)[1].strip(): n for n, line in enumerate(java_file.read_text().splitlines(), 1) if "CASE:" in line}
    relevant = [r for r in rows if r["anchor_file"].endswith("PeerLombok.java")]
    (output / "rows.json").write_text(json.dumps(relevant, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({
        "query_pack_hashes": before, "lombok_jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(java_file.read_bytes()).hexdigest(), "anchors": anchors,
        "cases": LOMBOK_CASES, "target_program_executed": False, "third_party_scan": False,
    }, indent=2) + "\n")
    return relevant, anchors


@pytest.mark.parametrize("case", tuple(LOMBOK_CASES))
def test_annotation_line_is_not_sufficient_for_transparent_exception_shell(lombok_peer_rows, case):
    rows, anchors = lombok_peer_rows
    selected = [r for r in rows if r["anchor_start_line"] == anchors[case]]
    assert len(selected) == 3 and {r["family"] for r in selected} == {"guard", "bound", "release"}, selected
    assert all(r["coverage_status"] == LOMBOK_CASES[case] for r in selected), {"case": case, "rows": selected}
