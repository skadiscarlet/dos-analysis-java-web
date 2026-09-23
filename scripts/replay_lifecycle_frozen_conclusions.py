#!/usr/bin/env python3
"""Reexecute production conclusions on authenticated frozen static inputs.

This is an offline downstream replay, NOT a fresh full scan or CodeQL/LLM run.
No artifact, producer identity, or signature in the input run is rewritten.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--implementation-root', type=Path, required=True)
    args = parser.parse_args()
    root, batch, output = args.implementation_root.resolve(), args.batch.resolve(), args.output.resolve()
    if output.exists() or output == batch or batch in output.parents:
        raise ValueError('output must be new and outside the frozen batch')
    sys.path.insert(0, str(root))
    from dosweb.artifacts.identifiers import canonical_json
    from dosweb.pipeline import StageContext, StageFingerprint, _encode_payload
    from dosweb.production import make_conclude_executor, _coverage
    from dosweb.lifecycle.certificates import LifecycleCertificate, StaticFinding
    from dosweb.report.families import FindingFamily
    from dosweb.report.summary import build_summary
    from dosweb.report.markdown import render_report
    import dosweb.production as implementation
    if Path(implementation.__file__).resolve().parent.parent != root:
        raise ValueError('Python imported a different implementation root')
    source_files = sorted((root / 'dosweb').rglob('*.py'))
    source_hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    tested_hash = hashlib.sha256(canonical_json(source_hashes)).hexdigest()
    tested_commit = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    statuses = [json.loads(s) for s in (batch / 'aggregate_status.jsonl').read_text().splitlines() if s.strip()]
    output.mkdir(parents=True)
    rows, transitions = [], []
    started = time.monotonic()
    for record in statuses:
        target = Path(record['batch_output_dir']).resolve()
        if batch not in target.parents:
            raise ValueError('input target escaped batch')
        run = json.loads((target / 'run.json').read_text())
        dest = output / record['batch_target_slug']
        dest.mkdir()
        row = {'project_id': record['batch_target_slug'], 'input_target': str(target), 'frozen_run_sha256': hashlib.sha256((target / 'run.json').read_bytes()).hexdigest(), 'upstream_output_hashes': {s: r.get('output_hash') for s, r in run['stages'].items() if s in ['entries','growth','flows','lifecycle']}, 'status': 'failed', 'error': None}
        try:
            context = StageContext('conclude', target, StageFingerprint.for_stage('conclude'), run['stages'], run)
            result = make_conclude_executor()(context)
            for filename, payload in result.artifacts.items():
                if Path(filename).name != filename:
                    raise ValueError('unexpected artifact path')
                data, _ = _encode_payload(payload)
                (dest / filename).write_bytes(data)
            cert_records = list(result.artifacts['lifecycle_certificates.jsonl'])
            tuple_fields = ['attacker_inputs','path_ids','resource_lifecycle_decisions','assertions','reason_codes','assumptions','coverage_gaps','unresolved_facts','suggested_follow_up_measurements']
            certificates = [LifecycleCertificate(**{**r, **{k: tuple(r[k]) for k in tuple_fields}}) for r in cert_records]
            findings = [StaticFinding.from_dict(r) for r in result.artifacts['static_findings.jsonl']]
            families = [FindingFamily.from_dict(r) for r in result.artifacts['finding_families.jsonl']]
            summary = build_summary(families, findings, _coverage(context))
            (dest / 'summary.json').write_bytes(canonical_json(summary) + b'\n')
            (dest / 'report.md').write_text(render_report(summary, families, findings, certificates))
            old = [json.loads(s) for s in (target / 'static_findings.jsonl').read_text().splitlines() if s.strip()]
            before = {(r['entry_id'],r['growth_id']):r for r in old}
            after = {(r.entry_id,r.growth_id):r for r in findings}
            if len(before) != len(old) or len(after) != len(findings):
                raise ValueError('ambiguous entry-growth comparison')
            for key in sorted(before.keys() | after.keys()):
                old_f, new_f = before.get(key), after.get(key)
                transitions.append({'project_id': row['project_id'], 'entry_id': key[0], 'growth_id': key[1], 'old_finding_id': old_f['finding_id'] if old_f else None, 'new_finding_id': new_f.finding_id if new_f else None, 'before': old_f['verdict'] if old_f else 'absent', 'after': new_f.verdict if new_f else 'absent'})
            row.update(status='completed', finding_count=len(findings), family_count=len(families), verdict_counts=dict(Counter(f.verdict for f in families)), produced_artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir()})
        except Exception as exc:
            row['error'] = {'type': type(exc).__name__, 'message': str(exc)[:400]}
        rows.append(row)
    ending_hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    stable = ending_hashes == source_hashes
    manifest = {'mode': 'authenticated_frozen_downstream_replay', 'fresh_full_scan': False, 'target_programs_executed': 0, 'codeql_queries_executed': 0, 'llm_calls': 0, 'input_batch': str(batch), 'input_status_sha256': hashlib.sha256((batch / 'aggregate_status.jsonl').read_bytes()).hexdigest(), 'tested_source_commit': tested_commit, 'tested_implementation_root': str(root), 'tested_source_content_sha256': tested_hash, 'source_stable_during_replay': stable, 'source_file_sha256': source_hashes, 'project_total': len(rows), 'completed_projects': sum(r['status']=='completed' for r in rows), 'projects': rows, 'verdict_transitions': dict(Counter(f"{r['before']} -> {r['after']}" for r in transitions)), 'elapsed_seconds': time.monotonic()-started}
    (output/'run-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    (output/'finding-transitions.jsonl').write_text(''.join(json.dumps(r, sort_keys=True)+'\n' for r in transitions))
    print(json.dumps({k:manifest[k] for k in ['mode','tested_source_commit','tested_source_content_sha256','source_stable_during_replay','project_total','completed_projects','verdict_transitions']}, indent=2))
    for r in rows:
        if r['error']: print(r['project_id'], r['error'])
    if not stable or any(r['status']!='completed' for r in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
