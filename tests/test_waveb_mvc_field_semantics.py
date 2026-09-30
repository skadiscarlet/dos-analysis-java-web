"""Static source regressions for exact MVC field-registration ownership."""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
import pytest
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query
from tests.support.fixture_database import fixture_database
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper

ROOT = Path(__file__).resolve().parents[1]


def source_tree(root: Path, variant: str) -> Path:
    source = root / 'source'
    fixture = ROOT / 'tests/fixtures/spring_mvc_interceptor_security/src/main/java'
    for p in fixture.rglob('*.java'):
        if p.parts[-3:-1] == ('fixture', 'interceptor'):
            continue
        target = source / p.relative_to(fixture)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    stubs = {
        'org/springframework/context/annotation/Configuration.java': 'package org.springframework.context.annotation; public @interface Configuration {}',
        'org/springframework/stereotype/Component.java': 'package org.springframework.stereotype; public @interface Component { String value() default ""; }',
        'org/springframework/stereotype/Service.java': 'package org.springframework.stereotype; public @interface Service { String value() default ""; }',
        'org/springframework/beans/factory/annotation/Autowired.java': 'package org.springframework.beans.factory.annotation; public @interface Autowired { boolean required() default true; }',
        'jakarta/annotation/Resource.java': 'package jakarta.annotation; public @interface Resource { String name() default ""; }',
    }
    field = 'private final TokenGate gate = new TokenGate();'
    gate_annotation = '@Component'
    gate_decl = 'final class TokenGate'
    gate_state = ''
    extra = ''
    statement = 'registry.addInterceptor(gate).excludePathPatterns("/open/**");'
    if variant == 'injected':
        field = '@Autowired private TokenGate gate;'
    elif variant == 'ambiguous':
        field = '@Autowired private HandlerInterceptor gate;'
    elif variant == 'reassigned':
        field = 'private TokenGate gate = new TokenGate();'
        extra = 'public void replace(TokenGate other) { gate = other; }'
    elif variant == 'conditional':
        statement = 'if (Boolean.getBoolean("test.enabled")) { ' + statement + ' }'
    elif variant == 'other_instance':
        statement = 'registry.addInterceptor(new FieldRegistration().gate).excludePathPatterns("/open/**");'
    elif variant == 'resource_multi':
        # @Resource without an explicit name uses the field name as its default
        # bean name. Keep the positive case on the exact Spring default bean
        # name so the analyzer never needs type-fallback guessing.
        field = '@Resource private TokenGate tokenGate;'
        gate_annotation = '@Service'
        gate_decl = 'class TokenGate'
        gate_state = 'private Object state;'
        statement = ('registry.addInterceptor(tokenGate).addPathPatterns("/secure/**"); '
                     'registry.addInterceptor(tokenGate).excludePathPatterns("/open/**");')
    elif variant == 'resource_name_mismatch':
        field = '@Resource private TokenGate gate;'
        gate_annotation = '@Service'
        gate_decl = 'class TokenGate'
        gate_state = 'private Object state;'
        statement = 'registry.addInterceptor(gate).excludePathPatterns("/open/**");'
    text = '''package fixture.field;
import javax.servlet.http.*;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.*;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import jakarta.annotation.Resource;
GATE_ANNOTATION GATE_DECL implements HandlerInterceptor {
 GATE_STATE
 public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
   if (request.getHeader("session") == null) { response.sendError(401); return false; }
   return true;
 }
}
@Configuration public class FieldRegistration implements WebMvcConfigurer {
 FIELD
 public void addInterceptors(InterceptorRegistry registry) { STATEMENT }
 EXTRA
}'''.replace('FIELD',field).replace('STATEMENT',statement).replace('EXTRA',extra).replace('GATE_ANNOTATION', gate_annotation).replace('GATE_DECL', gate_decl).replace('GATE_STATE', gate_state)
    stubs['fixture/field/FieldRegistration.java'] = text
    for name, content in stubs.items():
        p = source / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content+'\n')
    return source


@pytest.mark.skipif(os.environ.get('DOSWEB_RUN_CODEQL_FIXTURES') != '1' or not shutil.which('codeql') or not shutil.which('javac'), reason='Explicit self-owned Java/CodeQL fixture opt-in required')
@pytest.mark.parametrize('variant', ['initialized', 'injected', 'ambiguous', 'reassigned', 'conditional', 'other_instance', 'resource_multi', 'resource_name_mismatch'])
def test_mvc_field_registration_from_real_java(tmp_path: Path, variant: str) -> None:
    source = source_tree(tmp_path, variant)
    database = fixture_database(str(source))
    query = Path(os.environ.get('DOSWEB_AUTH_QUERY_UNDER_TEST', str(ROOT/'codeql/dosweb/Entries/EntrySecurity.ql')))
    result = run_query(query, database, tmp_path/'query', codeql_binary=str(_codeql_wrapper(tmp_path)))
    rows = decode_bqrs_json('entry_security',json.loads(result.decoded_path.read_text()),DecodeSource(database.source_root,result.query_sha256))
    evidence = os.environ.get('DOSWEB_AUTH_TEST_EVIDENCE')
    if evidence:
        p=Path(evidence);p.mkdir(parents=True,exist_ok=True)
        (p/('field-'+variant+'.json')).write_text(json.dumps({'query_sha256':result.query_sha256,'rows':rows},indent=2)+'\n')
    complete=[r for r in rows if r['route_or_event']=='/open/**' and r['value']=='unauthenticated_filter' and r['coverage_status']=='complete']
    if variant in {'initialized','injected','resource_multi'}:
        assert len(complete)==1, 'Statically unique same-instance registration must retain its exclusion evidence'
    else:
        assert not complete, 'Unproven instance/conditional registration must not create a public fact'


def inherited_handler_method_source(root: Path) -> Path:
    """Mirror real Spring where getMethodAnnotation is declared on AnnotatedMethod."""
    source = root / 'source'
    fixture = ROOT / 'tests/fixtures/spring_mvc_interceptor_security/src/main/java'
    shutil.copytree(fixture, source)
    annotated = source / 'org/springframework/core/annotation/AnnotatedMethod.java'
    annotated.parent.mkdir(parents=True, exist_ok=True)
    annotated.write_text(
        'package org.springframework.core.annotation; '
        'public class AnnotatedMethod { '
        'public <T extends java.lang.annotation.Annotation> T getMethodAnnotation(Class<T> type) { return null; } '
        '}\n'
    )
    handler = source / 'org/springframework/web/method/HandlerMethod.java'
    handler.write_text(
        'package org.springframework.web.method; '
        'public class HandlerMethod extends org.springframework.core.annotation.AnnotatedMethod {}\n'
    )
    return source


@pytest.mark.skipif(os.environ.get('DOSWEB_RUN_CODEQL_FIXTURES') != '1' or not shutil.which('codeql') or not shutil.which('javac'), reason='Explicit self-owned Java/CodeQL fixture opt-in required')
def test_mvc_annotation_lookup_accepts_inherited_handler_method_api(tmp_path: Path) -> None:
    source = inherited_handler_method_source(tmp_path)
    database = fixture_database(str(source))
    query = ROOT / 'codeql/dosweb/Entries/EntrySecurity.ql'
    result = run_query(query, database, tmp_path/'query', codeql_binary=str(_codeql_wrapper(tmp_path)))
    rows = decode_bqrs_json('entry_security', json.loads(result.decoded_path.read_text()), DecodeSource(database.source_root, result.query_sha256))
    public = [
        row for row in rows
        if row['route_or_event'] == '/ordered/open'
        and row['value'] == 'unauthenticated_filter'
        and row['coverage_status'] == 'complete'
        and row['coverage_note'] == 'spring_mvc_annotation_absent_interceptor_bypass'
    ]
    protected = [
        row for row in rows
        if row['route_or_event'] == '/ordered/protected'
        and row['value'] == 'unauthenticated_filter'
        and row['coverage_status'] == 'complete'
    ]
    assert len(public) == 1, 'Inherited HandlerMethod API must preserve the annotation-absent bypass proof'
    assert not protected, 'A handler carrying the protected annotation must never inherit the public bypass fact'
