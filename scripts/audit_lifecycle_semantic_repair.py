#!/usr/bin/env python3
"""Read-only prerequisite audit of frozen static artifacts; no queries or services.

Oracle joins occur only after static evidence is loaded. Reporting order is not
an assertion that overlapping gaps have one exclusive cause.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ORDER = ['entries', 'growth', 'reachability', 'flow', 'lifecycle', 'cause_unresolved']


def load(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('audit input exceeds bounded size')
    rows = [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError('JSONL must contain objects')
    return rows


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def write_csv(path, rows, fields=None):
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def scoped(row, field):
    return row['batch_target_slug'], row[field]


def indexed(rows, field):
    result = {scoped(r, field): r for r in rows}
    if len(result) != len(rows):
        raise ValueError(f'duplicate scoped identifier: {field}')
    return result


def unit_counts(rows, field):
    units = defaultdict(set)
    for row in rows:
        for reason in row['all_blockers']:
            units[reason].add((row['project_id'], row[field]))
    return {reason: len(ids) for reason, ids in sorted(units.items())}


def audit(batch, recall, known_cases, output):
    from dosweb.pipeline import StageContext, StageFingerprint
    from dosweb.production import _load_entries, _load_verified_growth
    from dosweb.flows import FlowProof, verify_flow
    batch, output = Path(batch).resolve(), Path(output).resolve()
    if output.exists() or output == batch or batch in output.parents:
        raise ValueError('output must be a new directory outside frozen input')
    names = ['findings', 'finding_families', 'lifecycle_certificates', 'verified_growth', 'flows', 'lifecycle_coverage', 'resource_lifecycle_bindings', 'reachability_decisions', 'repeatability_decisions', 'amplification_decisions', 'status', 'entries', 'growth_candidates', 'entry_security_facts']
    data = {n: load(batch / f'aggregate_{n}.jsonl') for n in names}
    hashes = {f'aggregate_{n}.jsonl': digest(batch / f'aggregate_{n}.jsonl') for n in names}
    flow_details, identities = {}, []
    for status in data['status']:
        target = Path(status['batch_output_dir']).resolve()
        if batch not in target.parents:
            raise ValueError('target escaped frozen batch')
        run = json.loads((target / 'run.json').read_text())
        checked, errors = 0, []
        for stage, record in run['stages'].items():
            for artifact in record.get('artifacts', []):
                rel = Path(artifact['path'])
                if rel.is_absolute() or '..' in rel.parts:
                    raise ValueError('unsafe artifact path')
                if '.private.' in rel.name:
                    continue
                path = target / rel
                if not path.is_file() or digest(path) != artifact['sha256']:
                    errors.append(f'{stage}/{rel}:hash_mismatch_or_missing')
                else:
                    checked += 1
        try:
            if errors:
                raise ValueError('public artifact identity validation failed')
            context = StageContext('conclude', target, StageFingerprint.for_stage('conclude'), run['stages'], run)
            entries, growth = _load_entries(context), _load_verified_growth(context)
            for raw in load(target / 'flow_proofs.jsonl'):
                flow = verify_flow(FlowProof.from_dict(raw), entries, growth)
                g = growth.get(flow.growth_id)
                c = g.candidate if g else None
                applicable = bool(c and c.kind == 'async_work_growth' and c.resource_dimension == 'tasks')
                flow_details[(status['batch_target_slug'], flow.path_id)] = {
                    'status': flow.status, 'reason_codes': list(flow.reason_codes),
                    'kind_and_dimension_applicable': applicable,
                    'growth_verified': bool(g and g.status == 'verified'),
                    'flow_premise_satisfied': flow.satisfies_premise,
                    'backend_gate_satisfied': applicable and bool(g and g.status == 'verified') and flow.satisfies_premise,
                }
        except Exception as exc:
            errors.append(f'{type(exc).__name__}:{str(exc)[:200]}')
        identities.append({'project_id': status['batch_target_slug'], 'status': status['status'], 'manifest_sha256': digest(target / 'run.json'), 'public_artifacts_verified': checked, 'errors': errors, 'schema_version': run.get('schema_version'), 'database_fingerprint': run.get('identity', {}).get('database_fingerprint'), 'stage_implementations': {s: r.get('fingerprint', {}).get('implementation_version') for s, r in run['stages'].items()}})
    certs = indexed(data['lifecycle_certificates'], 'certificate_id')
    growth = indexed(data['verified_growth'], 'growth_id')
    reach = indexed(data['reachability_decisions'], 'entry_id')
    entries = indexed(data['entries'], 'entry_id')
    candidates = indexed(data['growth_candidates'], 'growth_id')
    security = indexed(data['entry_security_facts'], 'fact_id')
    families, coverage, bindings = {}, defaultdict(list), defaultdict(list)
    decisions = {}
    for n in ['repeatability_decisions', 'amplification_decisions']:
        decisions[n] = {(r['batch_target_slug'], r['entry_id'], r['growth_id']): r for r in data[n]}
    for family in data['finding_families']:
        for fid in family['member_finding_ids']:
            k = family['batch_target_slug'], fid
            if k in families:
                raise ValueError('finding belongs to multiple families')
            families[k] = family['family_id']
    for r in data['lifecycle_coverage']:
        coverage[scoped(r, 'path_id')].append(r)
    for r in data['resource_lifecycle_bindings']:
        bindings[scoped(r, 'path_id')].append(r)
    rows = []
    for finding in data['findings']:
        slug = finding['batch_target_slug']
        cert = certs.get(scoped(finding, 'certificate_id'), {})
        g, r = growth.get(scoped(finding, 'growth_id'), {}), reach.get(scoped(finding, 'entry_id'), {})
        paths = cert.get('path_ids', [])
        details = [flow_details.get((slug, p), {'status': 'evidence_missing', 'reason_codes': ['TYPED_FLOW_EVIDENCE_MISSING']}) for p in paths]
        cov = [c for p in paths for c in coverage[(slug, p)]]
        bound = [b for p in paths for b in bindings[(slug, p)]]
        blockers = set(cert.get('unresolved_facts', [])) | set(cert.get('coverage_gaps', []))
        for upstream, complete in [(g, 'verified'), (r, 'ordinary_attacker_reachable'), *[(f, 'verified') for f in details]]:
            if upstream.get('status') != complete:
                blockers.update(upstream.get('reason_codes', ['EVIDENCE_MISSING']))
        blockers.update(f"{c['family']}:{c['reason']}" for c in cov if c['status'] != 'complete')
        for name in ['guard', 'bound', 'release']:
            decision = cert.get(name + '_decision', {})
            if decision.get('status') == 'unknown':
                blockers.update(decision.get('reason_codes', []))
                blockers.update(decision.get('unresolved_facts', []))
        for assertion in cert.get('assertions', []):
            if assertion.get('status') == 'unknown':
                blockers.update(assertion.get('reason_codes', []))
        if not cert:
            blockers.add('CERTIFICATE_EVIDENCE_MISSING')
        row = {'project_id': slug, 'finding_id': finding['finding_id'], 'family_id': families.get(scoped(finding, 'finding_id'), 'evidence_missing'), 'certificate_id': finding['certificate_id'], 'entry_id': finding['entry_id'], 'growth_id': finding['growth_id'], 'verdict': finding['verdict'], 'entry_present': scoped(finding, 'entry_id') in entries, 'growth_status': g.get('status', 'not_executed_or_unmapped'), 'growth_failed_checks': [c for c in g.get('checks', []) if not c.get('passed')], 'reachability_status': r.get('status', 'evidence_missing'), 'auth_context': r.get('auth_context', 'evidence_missing'), 'deployment_status': r.get('deployment_status', 'evidence_missing'), 'flow_status': 'verified' if details and all(f['status'] == 'verified' for f in details) else 'unresolved', 'flow_prerequisites': details, 'path_ids': paths, 'coverage': [{k: c[k] for k in ['coverage_id', 'path_id', 'family', 'status', 'reason']} for c in cov], 'assertions': cert.get('assertions', []), 'binding_ids': [b['binding_id'] for b in bound], 'binding_states': [b['binding_status'] for b in bound]}
        for name in ['repeatability_decisions', 'amplification_decisions']:
            dec = decisions[name].get((slug, finding['entry_id'], finding['growth_id']), {})
            row[name] = {k: dec.get(k, 'evidence_missing') for k in ['status', 'decision_id', 'reason_codes', 'evidence_ids']}
            if dec.get('status') == 'unknown':
                blockers.update(dec.get('reason_codes', []))
        candidate = candidates.get(scoped(finding, 'growth_id'), {})
        row['candidate_coverage_status'] = candidate.get('coverage_status', 'evidence_missing')
        row['candidate_coverage_notes'] = candidate.get('coverage_notes', [])
        row['security_evidence'] = [{k: fact.get(k) for k in ['fact_id','kind','value','coverage','location','line']} for evidence_id in r.get('evidence_ids', []) if (fact := security.get((slug, evidence_id))) is not None]
        if candidate.get('coverage_status') != 'complete':
            blockers.update(candidate.get('coverage_notes', []))
        row['all_blockers'] = sorted(blockers)
        row['all_observed_reason_codes'] = cert.get('reason_codes', [])
        row['first_observed_missing_premise'] = 'entries' if not row['entry_present'] else 'growth' if row['growth_status'] != 'verified' else 'reachability' if row['reachability_status'] != 'ordinary_attacker_reachable' else 'flow' if row['flow_status'] != 'verified' else 'lifecycle' if blockers else 'cause_unresolved'
        row['evidence_refs'] = [f"{batch.name}/aggregate_findings.jsonl#{finding['finding_id']}", f"{batch.name}/aggregate_lifecycle_certificates.jsonl#{finding['certificate_id']}"]
        rows.append(row)
    # Evaluation-only oracle joins: none of these values are passed to analyzer.
    truth = {r['record_id']: r for r in load(Path(recall) / 'truth_dispositions.jsonl')}
    with Path(known_cases).open(newline='') as stream:
        known = list(csv.DictReader(stream))
    if len(known) != len(truth) or {r['record_id'] for r in known} != set(truth):
        raise ValueError('frozen oracle denominator differs')
    by_finding = {r['finding_id']: r for r in rows}
    for row in known:
        t = truth[row['record_id']]
        attached = [by_finding[f] for f in row['matched_finding_ids'].split(';') if f in by_finding]
        row['all_blockers'] = sorted({s for r in attached for s in r['all_blockers']}) if attached else sorted(set(t.get('reason_codes', [])) | {'NO_CERTIFICATE_BACKED_MATCH'})
        row['first_observed_missing_premise'] = min((r['first_observed_missing_premise'] for r in attached), key=ORDER.index) if attached else row['first_missing_stage']
        slug = row['project_id'].lower().replace('/', '__')
        row['matched_growth_prerequisites'] = [{
            'growth_id': gid,
            'verification_status': growth.get((slug, gid), {}).get('status', 'not_executed_or_unmapped'),
            'reason_codes': growth.get((slug, gid), {}).get('reason_codes', []),
            'coverage_status': candidates.get((slug, gid), {}).get('coverage_status', 'evidence_missing'),
            'coverage_notes': candidates.get((slug, gid), {}).get('coverage_notes', []),
        } for gid in t.get('matched_growth_ids', [])]
        if not attached:
            reasons = set(row['all_blockers'])
            for item in row['matched_growth_prerequisites']:
                if item['verification_status'] != 'verified':
                    reasons.update(item['reason_codes'])
                    reasons.update(item['coverage_notes'])
            row['all_blockers'] = sorted(reasons)
        row['matched_entry_ids'] = t.get('matched_entry_ids', [])
        row['matched_growth_ids'] = t.get('matched_growth_ids', [])
        row['evidence_status'] = 'certificate_and_upstream_traced' if attached else 'oracle_match_and_upstream_gap_only'
    fs = list(flow_details.values())
    bs = data['resource_lifecycle_bindings']
    bridge = {'unit': 'formal_flow_path', 'candidates_considered': len(data['flows']), 'typed_paths_checked': len(fs), **{k: sum(bool(r[k]) for r in fs) for k in ['kind_and_dimension_applicable', 'growth_verified', 'flow_premise_satisfied', 'backend_gate_satisfied']}, 'historical_backend_executed': None, 'historical_backend_execution_status': 'exact_call_count_not_in_authenticated_metadata', 'historical_binding_projects': len({b['batch_target_slug'] for b in bs}), 'binding_records': len(bs), 'property_produced': sum(b.get('property_id') is not None for b in bs), 'binding_succeeded': sum(bool(b.get('property_id')) and b.get('binding_status') == 'refutes_relevant_growth' for b in bs), 'property_consumed_by_assertion': sum(any(x.get('decision', {}).get('status') == 'refutes_relevant_growth' for x in c['resource_lifecycle_decisions']) for c in data['lifecycle_certificates']), 'binding_status_counts': dict(Counter(b['binding_status'] for b in bs)), 'skip_reasons': dict(Counter(b['reason_code'] for b in bs)), 'cross_states': [{'kind_applicable': k[0], 'growth_verified': k[1], 'flow_satisfied': k[2], 'count': n} for k, n in sorted(Counter((r['kind_and_dimension_applicable'], r['growth_verified'], r['flow_premise_satisfied']) for r in fs).items())]}
    summary = {'format': 'lifecycle-semantic-repair-frozen-audit-v1', 'source_batch': str(batch), 'findings': len(rows), 'families': len(data['finding_families']), 'known_records': len(known), 'first_observed_premise_counts': dict(Counter(r['first_observed_missing_premise'] for r in rows)), 'known_first_observed_premise_counts': dict(Counter(r['first_observed_missing_premise'] for r in known)), 'finding_reason_counts': unit_counts(rows, 'finding_id'), 'family_reason_counts': unit_counts(rows, 'family_id'), 'known_record_reason_counts': unit_counts(known, 'record_id'), 'reason_counts_overlap': True, 'reporting_order_not_causal_proof': ORDER, 'bridge': bridge, 'target_artifact_identity': identities, 'consumed_aggregate_sha256': hashes, 'private_envelopes_read': False, 'live_source_or_database_revalidated': False}
    output.mkdir(parents=True)
    write_csv(output / 'prerequisite-status.csv', rows)
    write_csv(output / 'known-case-matches.csv', known)
    write_csv(output / 'analysis-unknown.csv', [r for r in rows if r['verdict'] == 'static_unknown'], list(rows[0]) if rows else ['finding_id'])
    write_json(output / 'prerequisite-audit.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['batch', 'recall', 'known-cases', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.batch, args.recall, args.known_cases, args.output)
    print(json.dumps({k: result[k] for k in ['findings', 'families', 'known_records', 'first_observed_premise_counts', 'known_first_observed_premise_counts', 'bridge']}, indent=2))
    print('identity_error_targets=', sum(bool(r['errors']) for r in result['target_artifact_identity']))


if __name__ == '__main__':
    main()
