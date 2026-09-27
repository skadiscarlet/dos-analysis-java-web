"""A partial row at a colliding line anchor must survive production selection."""
import json
import pytest
import dosweb.production as production
from tests.test_fse_offline_e2e import run_synthetic_case


@pytest.mark.parametrize('family', ['guard', 'bound', 'release'])
@pytest.mark.parametrize('gap_first', [False, True])
def test_partial_domain_row_cannot_be_overruled_by_complete_row(tmp_path, monkeypatch, family, gap_first):
    original = production._run_codeql_family
    def add_gap(*args, **kwargs):
        rows = original(*args, **kwargs)
        if args[2] == 'lifecycle':
            row = next(r for r in rows if r.get('query_name') == 'lifecycle_coverage' and r['family'] == family)
            partial = {**row, 'coverage_status': 'partial', 'coverage_note': 'synthetic_same_line_unmodeled_resource'}
            rows = [partial, *rows] if gap_first else [*rows, partial]
        return rows
    monkeypatch.setattr(production, '_run_codeql_family', add_gap)
    # Isolate the Guard/Bound/Release consumer, with no independent task-population proof.
    result, output, *_ = run_synthetic_case(tmp_path, 'off')
    assert result['status'] == 'completed'
    coverage = [json.loads(l) for l in (output/'lifecycle_coverage.jsonl').read_text().splitlines()]
    assert next(r for r in coverage if r['family'] == family)['status'] == 'partial'
    finding = json.loads((output/'static_findings.jsonl').read_text())
    assert finding['verdict'] == 'static_unknown'


def test_unrelated_anchor_gap_does_not_pollute_current_resource(tmp_path, monkeypatch):
    original = production._run_codeql_family
    def add_gap(*args, **kwargs):
        rows = original(*args, **kwargs)
        if args[2] == 'lifecycle':
            row = next(r for r in rows if r.get('query_name') == 'lifecycle_coverage')
            rows = [*rows, {**row, 'anchor_start_line':999, 'coverage_status':'partial', 'coverage_note':'unrelated_fixture_anchor'}]
        return rows
    monkeypatch.setattr(production,'_run_codeql_family',add_gap)
    _, output, *_ = run_synthetic_case(tmp_path,'full')
    assert json.loads((output/'static_findings.jsonl').read_text())['verdict'] == 'bounded_under_modeled_assumptions'
