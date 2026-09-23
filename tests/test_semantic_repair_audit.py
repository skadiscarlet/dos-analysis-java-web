from pathlib import Path
import importlib.util
import json
import pytest

spec = importlib.util.spec_from_file_location('semantic_audit', Path(__file__).resolve().parents[1] / 'scripts/audit_lifecycle_semantic_repair.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_scoped_identifiers_do_not_join_different_projects():
    rows = [{'batch_target_slug':'a','finding_id':'x'}, {'batch_target_slug':'b','finding_id':'x'}]
    assert len(audit.indexed(rows, 'finding_id')) == 2
    with pytest.raises(ValueError, match='duplicate'):
        audit.indexed([rows[0], rows[0]], 'finding_id')


def test_overlap_counts_are_per_distinct_unit_not_frequency():
    rows = [{'project_id':'a','family_id':'f','all_blockers':['A','B']}, {'project_id':'a','family_id':'f','all_blockers':['A']}, {'project_id':'b','family_id':'f','all_blockers':['B']}]
    assert audit.unit_counts(rows, 'family_id') == {'A': 1, 'B': 2}


def test_reject_reusing_output_before_reading_inputs(tmp_path):
    dest = tmp_path / 'exists'
    dest.mkdir()
    with pytest.raises(ValueError, match='new directory'):
        audit.audit(tmp_path / 'missing', tmp_path, tmp_path/'missing.csv', dest)


def test_jsonl_rejects_nonobjects(tmp_path):
    p = tmp_path/'input.jsonl'
    p.write_text('[1,2]\n')
    with pytest.raises(ValueError, match='objects'):
        audit.load(p)


def test_csv_roundtrips_explicit_empty_and_nested_evidence(tmp_path):
    import csv
    p = tmp_path/'rows.csv'
    audit.write_csv(p, [{'id':'f','evidence':[],'state':{'status':'unknown'}}])
    with p.open() as stream:
        row = next(csv.DictReader(stream))
    assert json.loads(row['evidence']) == []
    assert json.loads(row['state']) == {'status':'unknown'}
