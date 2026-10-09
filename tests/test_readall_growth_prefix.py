"""Growth-prefix effects, compiled from owned Java and queried with production QL."""
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
    "method_after": ("W value = new W(request); Gate.check(request); chain.doFilter(value, response);", "complete"),
    "constructor_after": ("W value = new W(request); new RequestGate(request); chain.doFilter(value, response);", "complete"),
    "store_after": ("W value = new W(request); this.saved = request; chain.doFilter(value, response);", "complete"),
    "disjoint_effect": ('if ("GET".equals(request.getMethod())) { Gate.check(request); return; } chain.doFilter(new W(request), response);', "complete"),
    "outer_constructor": ("new RequestGate(new W(request));", "partial"),
    "nested_argument_before": ("Gate.consume(Gate.checked(request), new W(request));", "partial"),
    "nullary_before": ("Gate.unknown(); chain.doFilter(new W(request), response);", "partial"),
    "method_before": ("Gate.check(request); chain.doFilter(new W(request), response);", "partial"),
    "constructor_before": ("new RequestGate(request); chain.doFilter(new W(request), response);", "partial"),
    "store_before": ("this.saved = request; chain.doFilter(new W(request), response);", "partial"),
    "loop_back": ('do { chain.doFilter(new W(request), response); Gate.check(request); } while ("POST".equals(request.getMethod()));', "partial"),
    "exception_before": ("try { Gate.check(request); } catch (IOException failure) {} chain.doFilter(new W(request), response);", "partial"),
}


def _source() -> str:
    parts = ['''package fixture.prefix;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import javax.servlet.*;
import javax.servlet.http.*;
import org.springframework.util.StreamUtils;
class Gate {
    static void check(HttpServletRequest request) throws IOException {
        if (request.getContentLengthLong() > 1024) throw new IOException();
    }
    static Object checked(HttpServletRequest request) throws IOException { check(request); return request; }
    static void consume(Object first, Object second) {}
    static void unknown() {}
}
class RequestGate { RequestGate(HttpServletRequest request) throws IOException { Gate.check(request); } }
''']
    for index, (case, (statements, _)) in enumerate(CASES.items()):
        name = "Wrapper" + str(index)
        parts.append(f'''class Filter{index} implements Filter {{
    private HttpServletRequest saved;
    public void doFilter(ServletRequest raw, ServletResponse response, FilterChain chain) throws IOException {{
        HttpServletRequest request = (HttpServletRequest) raw;
        {statements.replace('W', name)}
    }}
}}
class {name} extends HttpServletRequestWrapper {{
    final String body;
    {name}(HttpServletRequest request) throws IOException {{
        super(request);
        body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); // CASE:{case}
    }}
}}
''')
    return "\n".join(parts)


@pytest.fixture(scope="module")
def prefix_rows(tmp_path_factory):
    if os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") != "1":
        pytest.skip("explicit owned CodeQL fixture opt-in required")
    codeql, javac = shutil.which("codeql"), shutil.which("javac")
    assert codeql and javac, "opted-in source test requires CodeQL and javac"
    selected = os.environ.get("DOSWEB_PREFIX_QA_OUTPUT")
    output = Path(selected).resolve() if selected else tmp_path_factory.mktemp("growth-prefix")
    if selected:
        output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    shutil.copytree(BASE, source)
    # Older owned Servlet stubs intentionally contain only the methods used
    # by their original cases. This fixture adds one standard metadata method.
    request_stub = source / "javax/servlet/http/HttpServletRequest.java"
    text = request_stub.read_text()
    if "getMethod()" not in text:
        request_stub.write_text(text.replace("\n}", '\n    default String getMethod() { return "POST"; }\n}'))
    java_file = source / "fixture/prefix/PrefixReadAll.java"
    java_file.parent.mkdir(parents=True, exist_ok=True)
    java_file.write_text(_source())
    hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*.java")}
    classes = output / "classes"
    classes.mkdir()
    args = [javac, "-d", str(classes), *(str(p.relative_to(source)) for p in sorted(source.rglob("*.java")))]
    built = subprocess.run(
        [codeql, "database", "create", str(output / "database"), "--language=java", "--source-root=.", "--command=" + shlex.join(args)],
        cwd=source, capture_output=True, text=True, timeout=240, check=False,
    )
    (output / "build.log").write_text(built.stdout + built.stderr)
    assert built.returncode == 0, built.stderr[-4000:]
    db = validate_database(output / "database")
    query = ROOT / "codeql/dosweb/Lifecycle/LifecycleCoverage.ql"
    result = run_query(query, db, output / "query", codeql_binary=str(_codeql_wrapper(output)), timeout_seconds=600)
    rows = decode_bqrs_json("lifecycle_coverage", json.loads(result.decoded_path.read_text()), DecodeSource(db.source_root, result.query_sha256))
    anchors = {line.split("CASE:", 1)[1].strip(): n for n, line in enumerate(java_file.read_text().splitlines(), 1) if "CASE:" in line}
    rows = [r for r in rows if r["anchor_file"].endswith("PrefixReadAll.java")]
    (output / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"source_hashes": hashes, "anchors": anchors, "expected": {k: v[1] for k, v in CASES.items()}, "query_sha256": result.query_sha256, "helper_sha256": hashlib.sha256((query.parent / "RequestReadAllDomain.qll").read_bytes()).hexdigest(), "target_program_executed": False, "third_party_scan": False}, indent=2) + "\n")
    return rows, anchors


@pytest.mark.parametrize("case", tuple(CASES))
def test_only_effects_in_growth_prefix_may_block_local_peak_domain(prefix_rows, case):
    rows, anchors = prefix_rows
    selected = [row for row in rows if row["anchor_start_line"] == anchors[case]]
    assert len(selected) == 3 and {r["family"] for r in selected} == {"guard", "bound", "release"}, selected
    assert all(row["coverage_status"] == CASES[case][1] for row in selected), {"case": case, "rows": selected}
