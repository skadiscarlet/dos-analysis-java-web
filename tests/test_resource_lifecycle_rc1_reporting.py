"""RC1 denominator and failure behavior, independent of solver semantics."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import evaluate_lifecycle_rc1 as evaluate
import report_lifecycle_rc1 as report


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def identity():
    return {'tested_source_commit':'a' * 40, 'tested_source_dirty':False,
            'implementation_sha256':'b' * 64, 'query_sha256':{'query':'c' * 64}, 'runner_sha256':'d' * 64}


@pytest.mark.parametrize('resolved, expected', [(True, 0), (False, 1)])
def test_worker_distinguishes_no_resource_from_identity_failure(tmp_path, resolved, expected):
    manifest = tmp_path / 'manifest.json'
    write(manifest, {'selection':[], 'budgets':{}})
    frozen = {'tree_hash':'a' * 64, 'files':{'Fixture.java':'b' * 64}, 'source_repository':'test'}
    result = {'status':'partial','stage_counts':{},'ledger':[{
        'method_resolution':'method_resolved' if resolved else 'method_missing',
        'extraction':'extracted','analysis':'not_applicable' if resolved else 'skipped'}]}
    def project(values):
        write(values['out'] / 'project-results.json', result)
        write(values['out'] / 'phase-costs.json', {'extraction_and_adaptation_seconds':1.25,
                                                'solve_and_serialization_seconds':None})
        return result
    args = SimpleNamespace(out=tmp_path/'out', worker='xxl-job-core', asset_root=tmp_path, prior_run=tmp_path)
    with patch.object(evaluate, 'identity', side_effect=identity), \
         patch.object(evaluate, 'verify_input', return_value=(tmp_path, frozen, manifest)), \
         patch.object(evaluate, 'resource_project', side_effect=project):
        assert evaluate.worker(args) == expected
    metric = json.loads((args.out/'execution.json').read_text())
    assert metric['units'] == []
    assert metric['phase_costs']['extraction_and_adaptation_seconds'] == 1.25
    assert metric['costs']['replay_seconds'] is None


def test_report_keeps_nine_requests_when_workers_fail_before_intake(tmp_path):
    run = tmp_path / 'run'
    write(run / 'execution.json', {**identity(), 'requested_inputs':9,
        'modules':{module:{'exit_code':1} for module in report.MODULES}})
    for module in report.MODULES:
        write(run / module / 'execution.json', {**identity(), 'module':module, 'status':'failed'})
    xml = tmp_path / 'tests.xml'
    xml.write_text('<testsuite tests="1"><testcase classname="fixture" name="passed"/></testsuite>')
    acceptance = tmp_path / 'acceptance.json'
    write(acceptance, {'baseline_xml':str(xml), 'current_xml':str(xml),
        'gates':{f'R{i}':{'status':'fail','evidence':'worker failed'} for i in range(1,7)}})
    metrics = report.build(run, tmp_path/'report', acceptance)
    assert metrics['requested_inputs'] == 9
    assert metrics['completed_nonempty_units'] == 0
    assert metrics['modules_with_nonempty_analysis_and_replay'] == 0
    assert metrics['stage_counts']['extraction'] == {'failed':9}
    assert metrics['engineering_status'] == 'partial'
    assert metrics['research_evidence'] == 'unvalidated'
