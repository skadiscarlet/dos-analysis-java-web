"""Independent source-only checks of MVC proof boundaries.

Only repository-owned toy Java is compiled; no services/provider/target source.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query
from tests.support.fixture_database import fixture_database
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper
from tests.test_waveb_mvc_field_semantics import inherited_handler_method_source, source_tree

ROOT = Path(__file__).resolve().parents[1]
_SOURCE_OPT_IN = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1" and shutil.which("codeql") and shutil.which("javac")


def _rows(tmp_path: Path, source: Path, variant: str) -> list[dict]:
    database = fixture_database(str(source))
    query = ROOT / "codeql/dosweb/Entries/EntrySecurity.ql"
    result = run_query(query, database, tmp_path / "query", codeql_binary=str(_codeql_wrapper(tmp_path)))
    rows = decode_bqrs_json("entry_security", json.loads(result.decoded_path.read_text()),
                           DecodeSource(database.source_root, result.query_sha256))
    evidence = os.environ.get("DOSWEB_PEER687_EVIDENCE")
    if evidence:
        dest = Path(evidence)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{variant}.json").write_text(json.dumps({
            "variant": variant, "query_sha256": result.query_sha256, "rows": rows,
        }, indent=2) + "\n")
    return rows


@pytest.mark.skipif(not _SOURCE_OPT_IN, reason="Self-owned Java/CodeQL opt-in required")
@pytest.mark.parametrize("variant", ["plain", "acronym_name", "conditional_competitor"])
def test_resource_name_and_competing_bean_scope(tmp_path: Path, variant: str) -> None:
    source = source_tree(tmp_path, "resource_multi")
    java = source / "fixture/field/FieldRegistration.java"
    text = java.read_text()
    if variant == "acronym_name":
        # JavaBeans decapitalization preserves a name whose first two letters
        # are uppercase: URLGate -> URLGate, not uRLGate.
        text = text.replace("TokenGate", "URLGate").replace("tokenGate", "URLGate")
    elif variant == "conditional_competitor":
        profile = source / "org/springframework/context/annotation/Profile.java"
        profile.write_text('package org.springframework.context.annotation; public @interface Profile { String[] value(); }\n')
        text += ('\n@Service("tokenGate") @org.springframework.context.annotation.Profile("alternate") '
                 'class AlternateGate extends TokenGate {}\n')
    java.write_text(text)
    rows = _rows(tmp_path, source, variant)
    selected = [r for r in rows if r["route_or_event"] == "/open/**"
                and r["value"] == "unauthenticated_filter" and r["coverage_status"] == "complete"]
    if variant == "conditional_competitor":
        assert not selected, "Unknown profile activation cannot prove a unique same-name bean"
    else:
        assert len(selected) == 1, "Exact default bean identity must respect JavaBeans acronym naming"


@pytest.mark.skipif(not _SOURCE_OPT_IN, reason="Self-owned Java/CodeQL opt-in required")
def test_custom_lookup_override_is_not_framework_annotation_api(tmp_path: Path) -> None:
    source = inherited_handler_method_source(tmp_path)
    java = source / "fixture/interceptor/InterceptorSecurityFixture.java"
    text = java.read_text()
    text = text.replace(
        "class AnnotationSecurityInterceptor implements HandlerInterceptor {",
        "class CustomHandlerMethod extends HandlerMethod {\n"
        " @Override public <T extends java.lang.annotation.Annotation> T getMethodAnnotation(Class<T> type) {\n"
        "  throw new UnsupportedOperationException();\n }\n}\n"
        "class AnnotationSecurityInterceptor implements HandlerInterceptor {",
    ).replace("handler instanceof HandlerMethod", "handler instanceof CustomHandlerMethod").replace(
        "((HandlerMethod) handler).getMethodAnnotation", "((CustomHandlerMethod) handler).getMethodAnnotation",
    )
    java.write_text(text)
    rows = _rows(tmp_path, source, "custom_lookup_override")
    selected = [r for r in rows if r["route_or_event"] == "/ordered/open"
                and r["coverage_note"] == "spring_mvc_annotation_absent_interceptor_bypass"
                and r["coverage_status"] == "complete" and r["value"] == "unauthenticated_filter"]
    assert not selected, "A user-defined overriding method must not inherit a framework proof summary"
