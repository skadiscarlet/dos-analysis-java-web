from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import pytest

from dosweb.codeql.database import DatabaseInfo
from dosweb.codeql.decoder import DecodeSource, QUERY_SPECS, decode_rows, RESOURCE_LIFECYCLE_MAX_ROWS
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle import commands
from dosweb.resource_lifecycle.project import resource_project
from tests.test_resource_lifecycle_codeql import lifecycle_row, SYNTHETIC_HANDLE_ID
from dosweb.resource_lifecycle.adapters import adapt_codeql_rows


def database(tmp_path, missing=b'// class Old { }\n/* complete comment */\n'):
    source = tmp_path / 'source'
    source.mkdir()
    java = source / 'Fixture.java'
    java.write_text('class Fixture { void f() {} }\n')
    (source / 'Old.java').write_bytes(missing)
    db = tmp_path / 'database'
    db.mkdir()
    with zipfile.ZipFile(db / 'src.zip', 'w') as archive:
        archive.write(java, java.as_posix().lstrip('/'))
    return DatabaseInfo(db, source, 'd' * 64)


def test_comment_only_archive_difference_preserves_full_tree_identity(tmp_path):
    db = database(tmp_path)
    before = commands._java_source_snapshot(db.source_root)[1]
    assert commands._verify_database_source_snapshot(db) == before
    scope = commands._database_source_scope(db)
    assert len(scope['source_files']) == 2
    assert len(scope['archived_files']) == 1
    assert scope['unarchived_files'][0]['classification'] == 'lexical_trivia_only'
    assert scope['source_files']['Old.java'] == hashlib.sha256((db.source_root / 'Old.java').read_bytes()).hexdigest()


@pytest.mark.parametrize('missing', [b'class Missing {}', b'package p;', b'/* unfinished', br'//\u000aclass Hidden {}'])
def test_missing_declarations_or_ambiguous_lexing_fail_closed(tmp_path, missing):
    db = database(tmp_path, missing)
    assert not commands._database_source_scope(db)['scope_complete']
    with pytest.raises(ValueError, match='unarchived'):
        commands._verify_database_source_snapshot(db)


def test_archived_byte_mismatch_still_fails(tmp_path):
    db = database(tmp_path)
    (db.source_root / 'Fixture.java').write_text('class Fixture { int changed; }')
    with pytest.raises(ValueError, match='archived live source bytes'):
        commands._verify_database_source_snapshot(db)


def test_lifecycle_complete_module_budget_is_bounded_and_not_global(tmp_path):
    columns = QUERY_SPECS['resource_lifecycle'].columns
    row = [lifecycle_row()[column] for column in columns]
    result = decode_rows('resource_lifecycle', columns, [row] * 8885, DecodeSource(tmp_path, 'a' * 64))
    assert len(result) == 8885
    with pytest.raises(AnalyzerError) as exc:
        decode_rows('resource_lifecycle', columns, [row] * (RESOURCE_LIFECYCLE_MAX_ROWS + 1), DecodeSource(tmp_path, 'a' * 64))
    assert exc.value.details['reason'] == 'ROW_LIMIT'
    assert exc.value.details['row_count'] == RESOURCE_LIFECYCLE_MAX_ROWS + 1
    assert exc.value.details['row_limit'] == RESOURCE_LIFECYCLE_MAX_ROWS
    with pytest.raises(AnalyzerError) as exc:
        decode_rows('entries', QUERY_SPECS['entries'].columns, [[]] * 4097, DecodeSource(tmp_path, 'a' * 64))
    assert exc.value.details['row_limit'] == 4096


def test_zero_resource_method_identity_and_duplicates_are_visible_without_properties(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'Fixture.java').write_text('class Fixture { void f() {} }\n')
    tree = commands._java_source_snapshot(source)[1]
    facts = adapt_codeql_rows([], source_root=source, query_sha256='a' * 64,
        entry_methods=['empty', 'external', 'absent', 'ambiguous', 'stale'])
    facts = replace(facts, coverage={**facts.coverage, 'source_snapshot_sha256': tree})
    selection = [{'input_id': name, 'kind': 'method', 'entry_callable': method} for name, method in
        [('empty', 'empty'), ('external', 'external'), ('duplicate', 'external'), ('absent', 'absent'), ('ambiguous', 'ambiguous'), ('stale', 'stale')]]
    selection[-1]['source_sha256'] = 'f' * 64
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'version': 'resource-project-v1.2', 'project_id': 'test',
        'source_root': str(source), 'tree_hash': tree, 'database': 'database', 'output': str(tmp_path / 'out'),
        'selection': selection, 'dependency_scope': {'sources': ['Fixture.java'], 'dependencies': [], 'unknown_dependencies': []}, 'budgets': {}}))
    def extract(_manifest, _values, output):
        records = []
        for method, count in [('empty', 0), ('external', 1), ('ambiguous', 0), ('ambiguous', 0), ('stale', 0)]:
            records.append({'unit_id': method, 'source_file': 'Fixture.java', 'start_line': 1,
                'start_column': 1, 'source_sha256': 'b' * 64, 'call_count': count,
                'external_call_count': count, 'resource_coverage_notes': []})
        commands.atomic_write_json(output / 'callable-inventory.json', {'callables': records, 'rule_scope': 'test tracked allocations'})
        return facts
    with patch('dosweb.resource_lifecycle.project.validate_database', return_value=SimpleNamespace(source_root=source)), \
         patch('dosweb.resource_lifecycle.project._codeql_facts', side_effect=extract) as extraction, \
         patch('dosweb.resource_lifecycle.commands._analyze_payload') as solver:
        result = resource_project({'manifest': manifest})
    rows = {row['input_id']: row for row in result['ledger']}
    assert result['requested'] == 6
    assert extraction.call_count == 1
    assert solver.call_count == 0
    assert result['unique_analyzed_units'] == 0
    assert rows['empty']['method_resolution'] == 'method_resolved'
    assert rows['empty']['resource_recognition'] == 'no_modeled_resource'
    assert rows['external']['resource_recognition'] == 'resource_unmodeled'
    assert rows['external']['external_dependency_status'] == 'missing_source_body'
    assert rows['duplicate']['resource_recognition'] == 'resource_unmodeled'
    assert rows['absent']['method_resolution'] == 'method_missing'
    assert rows['ambiguous']['method_resolution'] == 'ambiguous'
    assert rows['stale']['method_resolution'] == 'source_mismatch'
    assert all(not row['property_ids'] for row in rows.values())


@pytest.mark.skipif(__import__('os').environ.get('DOSWEB_RUN_CODEQL_FIXTURES') != '1',
                    reason='Set DOSWEB_RUN_CODEQL_FIXTURES=1 for real static extraction.')
def test_real_callable_inventory_keeps_empty_and_external_call_methods(tmp_path):
    from dosweb.codeql import run_query, decode_bqrs_json
    from tests.support.fixture_database import fixture_database
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'IdentityFixture.java').write_text('''class IdentityFixture {
        void empty() {}
        void empty(int value) {}
        String external(String value) { return value.trim(); }
        void local() { empty(); }
    }\n''')
    db = fixture_database(str(source))
    root = Path(__file__).resolve().parents[1]
    query = root / 'dosweb/codeql/pack/dosweb/ResourceLifecycle/ResourceLifecycleCallables.ql'
    assert query.read_bytes() == (root / 'codeql/dosweb/ResourceLifecycle/ResourceLifecycleCallables.ql').read_bytes()
    result = run_query(query, db, tmp_path / 'query')
    records = decode_bqrs_json(result.query_name, json.loads(result.decoded_path.read_text()),
        DecodeSource(source, result.query_sha256))
    inventory = {record['unit_id']: record for record in records}
    prefix = 'java-callable-v1:IdentityFixture.'
    assert inventory[prefix + 'empty()V']['call_count'] == 0
    assert inventory[prefix + 'empty()V']['call_targets'] == ''
    assert inventory[prefix + 'empty(I)V']['call_count'] == 0
    assert inventory[prefix + 'external(Ljava/lang/String;)Ljava/lang/String;']['external_call_count'] == 1
    assert inventory[prefix + 'local()V']['external_call_count'] == 0


@pytest.mark.parametrize('mismatch', [False, True])
def test_project_failed_scope_audit_retains_hashes_and_never_runs_queries(tmp_path, mismatch):
    from dataclasses import asdict
    from dosweb.resource_lifecycle.models import AnalysisBudget, SCHEMA_VERSION
    db = database(tmp_path, b'class UnarchivedDependency {}' if not mismatch else b'// old placeholder')
    if mismatch:
        (db.source_root / 'Fixture.java').write_text('class Fixture { int changed; }')
    output = tmp_path / 'output'
    output.mkdir()
    manifest = {'schema_version': SCHEMA_VERSION, 'mode': 'codeql_database', 'database': str(db.path),
        'entry_methods': ['java-callable-v1:Fixture.f()V'], 'budget': asdict(AnalysisBudget())}
    with patch.object(commands, 'validate_database', return_value=db), patch.object(commands, 'run_query') as query:
        with pytest.raises(ValueError):
            commands._codeql_facts(manifest, {'_project_intake_diagnostics': True}, output)
    query.assert_not_called()
    audit = json.loads((output / 'source-scope.json').read_text())
    assert audit['scope_complete'] is False
    assert audit['source_files']['Fixture.java']
    assert audit['archived_files']['Fixture.java']
    assert bool(audit['archived_mismatch_files']) is mismatch
    assert audit['requested_entry_methods'] == manifest['entry_methods']
