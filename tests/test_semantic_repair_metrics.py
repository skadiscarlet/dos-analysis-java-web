import pytest
from dosweb.benchmark.poc33_demo import build_demo_metrics, classify_hard_negative_outcome, precision_review_metrics


def metric(families=(), reviews=(), truth=(), final_findings=None):
    return build_demo_metrics(statuses=[], truth_dispositions=truth, static_findings=families, dynamic_results=[], reviews=reviews, final_findings=final_findings)


def family(i, verdict='static_unknown'):
    return {'family_id':f'family:{i}', 'member_finding_ids':[f'finding:{i}'], 'verdict':verdict}


def test_all_unknown_and_zero_positive_are_not_a_review_queue():
    m = metric([family(i) for i in range(4)], [{'family_id':'family:0','review_status':'confirmed_positive'}])
    assert (m['predicted_positive_families'],m['queue'],m['tp'],m['fp'],m['unreviewed_positive']) == (0,0,0,0,0)
    assert m['analysis_unknown_families'] == 4
    assert m['precision'] is m['confirmed_precision'] is m['conservative_precision_lower_bound'] is None
    assert m['precision_review_status'] == 'not_evaluable_no_positive'


def test_partial_reviews_use_only_deduplicated_positive_families():
    p=[family(i,'static_vulnerable') for i in range(3)]
    m=metric(p+[p[0],family('u')],[{'family_id':'family:0','review_status':'confirmed_positive'},{'finding_id':'finding:1','review_status':'false_positive'}])
    assert (m['predicted_positive_families'],m['tp'],m['fp'],m['unreviewed_positive']) == (3,1,1,1)
    assert m['confirmed_precision'] == 0.5
    assert m['conservative_precision_lower_bound'] == 0.333333
    assert m['analysis_unknown_families'] == 1
    assert m['threshold_origin'] == 'proposed_default'
    assert m['false_positive_rate'] == 'not_measured'


def test_new_positive_outside_known_records_affects_precision_not_recall_denominator():
    m=metric([family('new','static_vulnerable')],truth=[{'record_id':'old','matched_finding_ids':[]}])
    assert m['novel_positive_families'] == 1
    assert m['known_case_recall'] == {'numerator':0,'denominator':1,'ratio':0.0}
    assert m['unreviewed_positive'] == 1
    assert m['confirmed_precision'] is None
    assert m['conservative_precision_lower_bound'] == 0.0


def test_family_positive_does_not_upgrade_unknown_member_to_known_hit():
    f={'family_id':'f','member_finding_ids':['a','b'],'verdict':'static_vulnerable'}
    truth=[{'record_id':'r','matched_finding_ids':['b']}]
    m=metric([f],truth=truth,final_findings=[{'finding_id':'a','verdict':'static_vulnerable'},{'finding_id':'b','verdict':'static_unknown'}])
    assert m['known_case_matches'] == 0
    assert metric([f],truth=truth)['known_case_matches'] == 0


def test_exact_positive_member_counts_as_known_match():
    m=metric([family(1,'static_vulnerable')],truth=[{'record_id':'r','matched_finding_ids':['finding:1']}])
    assert m['known_case_recall']['numerator'] == 1


def test_unmatched_negative_is_not_invented_extraction_failure():
    assert classify_hard_negative_outcome(set()) == 'unmatched_static_evidence'
    assert classify_hard_negative_outcome({'bounded_under_modeled_assumptions','static_unknown'}) == 'analysis_unknown'
    assert classify_hard_negative_outcome({'extraction_failure'}) == 'extraction_failure'


def test_conflicting_reviews_remain_unreviewed():
    m=metric([family(1,'static_vulnerable')],[{'family_id':'family:1','review_status':'confirmed_positive'},{'family_id':'family:1','review_status':'false_positive'}])
    assert (m['tp'],m['fp'],m['unreviewed_positive']) == (0,0,1)


def test_review_partition_must_match_predictions():
    with pytest.raises(ValueError):
        precision_review_metrics(predicted_positive=0,true_positives=1,false_positives=0,unreviewed_positives=0)
    with pytest.raises(ValueError):
        precision_review_metrics(predicted_positive=-1,true_positives=-1,false_positives=0,unreviewed_positives=0)
