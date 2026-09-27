"""Static-only control: an escaping registration is not a closed default matcher."""
import json
import os
import shutil
from pathlib import Path
import pytest
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query
from tests.support.fixture_database import fixture_database
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper
import tests.test_waveb_mvc_field_semantics as helper
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.skipif(os.environ.get('DOSWEB_RUN_CODEQL_FIXTURES') != '1' or not shutil.which('codeql') or not shutil.which('javac'), reason='Explicit self-owned Java/CodeQL fixture opt-in required')

def test_registration_passed_to_unknown_helper_cannot_keep_public_exclusion(tmp_path):
    source=helper.source_tree(tmp_path,'initialized')
    p=source/'fixture/field/FieldRegistration.java';s=p.read_text()
    old='registry.addInterceptor(gate).excludePathPatterns("/open/**");'
    assert old in s
    s=s.replace(old,'customize(registry.addInterceptor(gate).excludePathPatterns("/open/**"));')
    i=s.rindex('}')
    s=s[:i]+''' private static void customize(InterceptorRegistration registration) {
      registration.pathMatcher(new NeverMatcher());
    }
'''+s[i:]+'''\nclass NeverMatcher implements org.springframework.util.PathMatcher {
 public boolean match(String pattern,String path) { return false; }
}\n'''
    p.write_text(s)
    p=source/'org/springframework/util/PathMatcher.java';p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('package org.springframework.util; public interface PathMatcher { boolean match(String pattern,String path); }\n')
    p=source/'org/springframework/web/servlet/config/annotation/InterceptorRegistration.java';s=p.read_text();i=s.rindex('}')
    p.write_text(s[:i]+' public InterceptorRegistration pathMatcher(org.springframework.util.PathMatcher matcher) { return this; }\n'+s[i:])
    database=fixture_database(str(source))
    result=run_query(Path(os.environ.get('DOSWEB_AUTH_QUERY_UNDER_TEST', str(ROOT/'codeql/dosweb/Entries/EntrySecurity.ql'))),database,tmp_path/'query',codeql_binary=str(_codeql_wrapper(tmp_path)),timeout_seconds=600)
    rows=decode_bqrs_json('entry_security',json.loads(result.decoded_path.read_text()),DecodeSource(database.source_root,result.query_sha256))
    complete=[r for r in rows if r.get('route_or_event')=='/open/**' and r.get('value')=='unauthenticated_filter' and r.get('coverage_status')=='complete']
    (tmp_path/'escaped-registration.json').write_text(json.dumps({'query_sha256':result.query_sha256,'unexpected_complete':complete},indent=2))
    local=[r for r in rows if r.get('route_or_event')=='/open/**']
    assert local and all(r['coverage_status']=='partial' for r in local)
    assert not complete, 'Passing the registration to another method leaves its matcher mutation unresolved'
