"""Independent static-source tests for effects before/after a read-all growth point.

No request is sent and no target program is executed. The expectation concerns
local peak-byte coverage, not a vulnerability verdict or a server-wide bound.
"""
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

# Frozen before candidate implementation is inspected. Each wrapper has an
# independent constructor so one deliberately unresolved caller cannot mask
# another case. Helpers are source-defined and never executed by this test.
CASES: dict[str, tuple[str, str]] = {
    "plain": ('chain.doFilter(new W_plain(request), response);', "complete"),
    "after_method": ('W_after_method w = new W_after_method(request); Gate.check(request); chain.doFilter(w, response);', "complete"),
    "after_constructor": ('W_after_constructor w = new W_after_constructor(request); new RequestGate(request); chain.doFilter(w, response);', "complete"),
    "after_field_store": ('W_after_field_store w = new W_after_field_store(request); saved = request; checkSaved(); chain.doFilter(w, response);', "complete"),
    "after_array_store": ('W_after_array_store w = new W_after_array_store(request); slots[0] = request; chain.doFilter(w, response);', "complete"),
    "after_argument": ('Use.accept(new W_after_argument(request), Gate.test(request));', "complete"),
    "after_size_branch": ('W_after_size_branch w = new W_after_size_branch(request); if (request.getContentLengthLong() > 1024) { Gate.check(request); } chain.doFilter(w, response);', "complete"),
    "disjoint_return": ('if ("skip".equals(request.getContentType())) { Gate.check(request); return; } chain.doFilter(new W_disjoint_return(request), response);', "complete"),
    "before_method": ('Gate.check(request); chain.doFilter(new W_before_method(request), response);', "partial"),
    "before_constructor": ('new RequestGate(request); chain.doFilter(new W_before_constructor(request), response);', "partial"),
    "before_field_store": ('saved = request; checkSaved(); chain.doFilter(new W_before_field_store(request), response);', "partial"),
    "before_array_store": ('slots[0] = request; Gate.check((HttpServletRequest)slots[0]); chain.doFilter(new W_before_array_store(request), response);', "partial"),
    "before_argument": ('Use.accept(Gate.test(request), new W_before_argument(request));', "partial"),
    "array_lhs_argument": ('slots[Gate.test(request)] = new W_array_lhs_argument(request);', "partial"),
    "loop_back": ('while (enabled) { chain.doFilter(new W_loop_back(request), response); Gate.check(request); }', "partial"),
    "finally_before": ('try { Gate.check(request); } finally { count++; } chain.doFilter(new W_finally_before(request), response);', "partial"),
    "wrapper_argument": ('chain.doFilter(new W_wrapper_argument(Gate.forward(request)), response);', "partial"),
    "erased_before": ('Object alias = request; Gate.checkObject(alias); chain.doFilter(new W_erased_before(request), response);', "partial"),
}


def source_text() -> str:
    pieces = ['''package fixture.prefixpeer;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import javax.servlet.*;
import javax.servlet.http.*;
import org.springframework.util.StreamUtils;
class Gate {
    static void check(HttpServletRequest request) throws IOException {
        if (request.getContentLengthLong() > 1024) throw new IOException();
    }
    static int test(HttpServletRequest request) throws IOException { check(request); return 0; }
    static void checkObject(Object request) throws IOException { check((HttpServletRequest)request); }
    static HttpServletRequest forward(HttpServletRequest request) throws IOException { check(request); return request; }
}
class RequestGate { RequestGate(HttpServletRequest request) throws IOException { Gate.check(request); } }
class Use {
    static void accept(Object wrapper, int value) {}
    static void accept(int value, Object wrapper) {}
}
''']
    for name, (statements, _expectation) in CASES.items():
        pieces.append(f'''class F_{name} implements Filter {{
    HttpServletRequest saved;
    Object[] slots = new Object[2];
    boolean enabled = true;
    int count;
    private void checkSaved() throws IOException {{ Gate.check(saved); }}
    public void doFilter(ServletRequest raw, ServletResponse response, FilterChain chain) throws IOException {{
        HttpServletRequest request = (HttpServletRequest) raw;
        {statements}
    }}
}}
class W_{name} extends HttpServletRequestWrapper {{
    final String body;
    W_{name}(HttpServletRequest request) throws IOException {{
        super(request);
        body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); // CASE:{name}
    }}
}}
''')
    # The same growth constructor is reachable from two source call sites:
    # one closed caller and one caller with a real pre-growth check.
    pieces.append('''class F_shared_a implements Filter {
    public void doFilter(ServletRequest raw, ServletResponse response, FilterChain chain) throws IOException {
        chain.doFilter(new SharedWrapper((HttpServletRequest)raw), response);
    }
}
class F_shared_b implements Filter {
    public void doFilter(ServletRequest raw, ServletResponse response, FilterChain chain) throws IOException {
        HttpServletRequest request = (HttpServletRequest)raw;
        Gate.check(request);
        chain.doFilter(new SharedWrapper(request), response);
    }
}
class SharedWrapper extends HttpServletRequestWrapper {
    final String body;
    SharedWrapper(HttpServletRequest request) throws IOException {
        super(request);
        body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); // CASE:shared_callsite
    }
}
''')
    return "\n".join(pieces)


EXPECTED = {name: specification[1] for name, specification in CASES.items()} | {"shared_callsite": "partial"}


def _inventory(pack: Path) -> dict[str, str]:
    return {
        str(path.relative_to(pack)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(pack.rglob("*"))
        if path.is_file() and path.suffix in {".ql", ".qll", ".yml"}
    }


@pytest.fixture(scope="module")
def prefix_rows(tmp_path_factory):
    if os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") != "1":
        pytest.skip("explicit self-owned Java/CodeQL opt-in required")
    codeql, javac = shutil.which("codeql"), shutil.which("javac")
    assert codeql and javac, "opted-in validation requires installed tools"
    selected = os.environ.get("DOSWEB_PREFIX_PEER_OUTPUT")
    output = Path(selected).resolve() if selected else tmp_path_factory.mktemp("prefix-peer")
    if selected:
        output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    shutil.copytree(BASE, source)
    java_file = source / "fixture/prefixpeer/PrefixPeerFixture.java"
    java_file.parent.mkdir(parents=True, exist_ok=True)
    java_file.write_text(source_text(), encoding="utf-8")
    classes = output / "classes"
    classes.mkdir()
    arguments = [javac, "-d", str(classes), *(str(p.relative_to(source)) for p in sorted(source.rglob("*.java")))]
    build = subprocess.run(
        [codeql, "database", "create", str(output / "database"), "--language=java", "--source-root=.", f"--command={shlex.join(arguments)}"],
        cwd=source, text=True, capture_output=True, check=False, timeout=240,
    )
    (output / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    assert build.returncode == 0, build.stderr[-4000:]
    database = validate_database(output / "database")
    pack = Path(os.environ.get("DOSWEB_PREFIX_PEER_PACK", str(ROOT / "codeql"))).resolve()
    before = _inventory(pack)
    result = run_query(
        pack / "dosweb/Lifecycle/LifecycleCoverage.ql", database, output / "query",
        codeql_binary=str(_codeql_wrapper(output)), timeout_seconds=600,
    )
    assert before == _inventory(pack), "query pack changed while testing"
    decoded = decode_bqrs_json("lifecycle_coverage", json.loads(result.decoded_path.read_text()), DecodeSource(database.source_root, result.query_sha256))
    rows = [row for row in decoded if row["anchor_file"].endswith("PrefixPeerFixture.java")]
    anchors = {line.split("CASE:", 1)[1].strip(): index for index, line in enumerate(java_file.read_text().splitlines(), 1) if "CASE:" in line}
    assert set(anchors) == set(EXPECTED)
    (output / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")
    manifest = {
        "query_pack_hashes": before,
        "source_sha256": hashlib.sha256(java_file.read_bytes()).hexdigest(),
        "anchors": anchors, "expected": EXPECTED,
        "target_program_executed": False, "new_third_party_scan": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return rows, anchors


@pytest.mark.parametrize("case", tuple(EXPECTED))
def test_growth_prefix_effect_boundary(prefix_rows, case):
    rows, anchors = prefix_rows
    selected = [row for row in rows if row["anchor_start_line"] == anchors[case]]
    assert len(selected) == 3 and {row["family"] for row in selected} == {"guard", "bound", "release"}, {"case": case, "rows": selected}
    assert {row["coverage_status"] for row in selected} == {EXPECTED[case]}, {"case": case, "rows": selected}
