"""An existing verified refutation is not a proof of absence of all bounds.

Reuse the canonical production boundary tests; do not fabricate a new verdict.
Only vary the coverage of discovering additional candidates.
"""
from unittest import mock
import pytest
import dosweb.production as production
import tests.test_production_e2e as existing


def with_incomplete_scan(monkeypatch, families):
    make = production.make_conclude_executor
    def wrapped_factory():
        execute = make()
        def wrapped(context):
            original_records = production._strict_records
            def records(context, stage, artifact):
                rows = original_records(context, stage, artifact)
                if artifact == 'lifecycle_coverage.jsonl':
                    from dosweb.lifecycle import LifecycleCoverage
                    return [LifecycleCoverage(r['entry_id'],r['growth_id'],r['path_id'],r['family'],
                        'partial' if r['family'] in families else r['status'],
                        'additional_candidate_scan_incomplete' if r['family'] in families else r['reason']).to_dict() for r in rows]
                return rows
            with mock.patch.object(production,'_strict_records',side_effect=records):
                return execute(context)
        return wrapped
    monkeypatch.setattr(production,'make_conclude_executor',wrapped_factory)


@pytest.mark.parametrize('families', [('guard',), ('bound',), ('guard','bound')])
def test_verified_refutation_still_requires_exact_entry_but_not_complete_absence_scan(monkeypatch, families):
    with_incomplete_scan(monkeypatch, families)
    # Preserves both original assertions: wrong Entry stays unknown; the exact
    # Entry with a verified bound remains bounded under modeled assumptions.
    existing.ProductionProofGateE2ETests().test_other_supported_pattern_of_same_registration_kind_cannot_complete_entry()


def test_independent_refutation_does_not_erase_candidate_relevant_gap(monkeypatch):
    with_incomplete_scan(monkeypatch, ('guard','bound','release'))
    existing.ProductionProofGateE2ETests().test_gap_eligible_effective_bound_is_still_static_unknown()
