"""Do not lend default exclusion semantics to a custom PathMatcher."""
import json
import os
import shutil
from pathlib import Path
import pytest
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query
from tests.support.fixture_database import fixture_database
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper
from tests.test_waveb_mvc_field_semantics import source_tree

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.skipif(os.environ.get('DOSWEB_RUN_CODEQL_FIXTURES') != '1' or not shutil.which('codeql') or not shutil.which('javac'), reason='Explicit self-owned Java/CodeQL fixture opt-in required')
@pytest.mark.parametrize('after', [False, True])
def test_custom_matcher_before_or_after_exclusion_retains_unknown(tmp_path, after):
    source = source_tree(tmp_path, 'initialized')
    p = source/'fixture/field/FieldRegistration.java';text=p.read_text()
    old = 'registry.addInterceptor(gate).excludePathPatterns("/open/**")'
    new = old + '.pathMatcher(new NeverMatcher())' if after else 'registry.addInterceptor(gate).pathMatcher(new NeverMatcher()).excludePathPatterns("/open/**")'
    assert old in text
    p.write_text(text.replace(old,new)+'''\nclass NeverMatcher implements org.springframework.util.PathMatcher {
 public boolean match(String pattern, String path) { return false; }
}\n''')
    p=source/'org/springframework/util/PathMatcher.java';p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('package org.springframework.util; public interface PathMatcher { boolean match(String pattern,String path); }\n')
    p=source/'org/springframework/web/servlet/config/annotation/InterceptorRegistration.java';text=p.read_text();i=text.rindex('}')
    p.write_text(text[:i]+'public InterceptorRegistration pathMatcher(org.springframework.util.PathMatcher matcher) { return this; }\n'+text[i:])
    database=fixture_database(str(source))
    result=run_query(ROOT/'codeql/dosweb/Entries/EntrySecurity.ql',database,tmp_path/'query',codeql_binary=str(_codeql_wrapper(tmp_path)),timeout_seconds=600)
    rows=decode_bqrs_json('entry_security',json.loads(result.decoded_path.read_text()),DecodeSource(database.source_root,result.query_sha256))
    local=[r for r in rows if r['route_or_event']=='/open/**']
    assert local and all(r['coverage_status']=='partial' for r in local)
    assert not [r for r in local if r['value']=='unauthenticated_filter']
