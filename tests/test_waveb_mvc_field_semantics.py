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
        'org/springframework/stereotype/Component.java': 'package org.springframework.stereotype; public @interface Component {}',
        'org/springframework/beans/factory/annotation/Autowired.java': 'package org.springframework.beans.factory.annotation; public @interface Autowired { boolean required() default true; }',
    }
    field = 'private final TokenGate gate = new TokenGate();'
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
    text = '''package fixture.field;
import javax.servlet.http.*;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.*;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Autowired;
@Component final class TokenGate implements HandlerInterceptor {
 public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
   if (request.getHeader("session") == null) { response.sendError(401); return false; }
   return true;
 }
}
@Configuration public class FieldRegistration implements WebMvcConfigurer {
 FIELD
 public void addInterceptors(InterceptorRegistry registry) { STATEMENT }
 EXTRA
}'''.replace('FIELD',field).replace('STATEMENT',statement).replace('EXTRA',extra)
    stubs['fixture/field/FieldRegistration.java'] = text
    for name, content in stubs.items():
        p = source / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content+'\n')
    return source


@pytest.mark.skipif(os.environ.get('DOSWEB_RUN_CODEQL_FIXTURES') != '1' or not shutil.which('codeql') or not shutil.which('javac'), reason='Explicit self-owned Java/CodeQL fixture opt-in required')
@pytest.mark.parametrize('variant', ['initialized', 'injected', 'ambiguous', 'reassigned', 'conditional', 'other_instance'])
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
    if variant in {'initialized','injected'}:
        assert len(complete)==1, 'Statically unique same-instance registration must retain its exclusion evidence'
    else:
        assert not complete, 'Unproven instance/conditional registration must not create a public fact'
