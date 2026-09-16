#!/usr/bin/env python3
"""Re-run only the nine frozen RC1 development inputs using existing local assets.

No downloads, target execution, oracle import or source edits. Each module runs
in a separate process so peak RSS is a per-module measurement. A partial project
remains partial; absence of modeled resources never counts as a solved unit.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dosweb.resource_lifecycle.commands import _implementation_sha256, _java_source_snapshot, _analyze_payload, _QUERY
from dosweb.resource_lifecycle.project import resource_project
from dosweb.resource_lifecycle.sharded_run import replay_sharded, iter_run_units
from dosweb.resource_lifecycle.shards import ShardReader
from dosweb.resource_lifecycle.adapters import extracted_from_dict, validate_extracted
from dosweb.resource_lifecycle.source_evaluation import _disable_cross_event_propagation
from report_lifecycle_v12_independent import MODULES, read, write


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity():
    return {
        'tested_source_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'tested_source_dirty': bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        'implementation_sha256': _implementation_sha256(),
        'query_sha256': {p.relative_to(ROOT).as_posix():digest(p)
                         for p in (*_QUERY, _QUERY[0].with_name('ResourceLifecycleCallables.ql'))},
        'runner_sha256':digest(Path(__file__)),
    }


def verify_input(asset_root, prior, name):
    base = prior / name
    frozen = read(base/'input-freeze.json')
    source = base/'source'
    files, tree_hash = _java_source_snapshot(source)
    if files != frozen['files'] or tree_hash != frozen['tree_hash']:
        raise ValueError('frozen mirror identity differs: '+name)
    scope = Path(frozen['original_scope'])
    if scope.is_absolute() or '..' in scope.parts:
        raise ValueError('unsafe original source scope')
    for rel, expected in files.items():
        relative = Path(rel)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe frozen file path')
        if digest(asset_root/scope/relative) != expected:
            raise ValueError('original frozen bytes differ: '+name+'/'+rel)
    manifest = ROOT/'docs/execution/lifecycle-v1.2/inputs'/f'{name}.json'
    selection = read(manifest)
    expected_counts = {'xxl-job-core':52, 'hertzbeat-common-core':158, 'hertzbeat-common-spring':67}
    if (selection['tree_hash'] != tree_hash or len(selection['selection']) != 3
            or len(files) != expected_counts[name]
            or {r['input_id'] for r in selection['selection']} != {f'{name}-{i}' for i in (1,2,3)}
            or [r['entry_callable'].removeprefix('java-callable-v1:') for r in selection['selection']] != frozen['methods']):
        raise ValueError('original full-module selection differs')
    return base, frozen, manifest


def worker(args):
    output = args.out.resolve()
    output.mkdir(parents=True,exist_ok=False)
    metric = {**identity(), 'module':args.worker, 'status':'running',
              'costs':{'database_creation_seconds':None,
                       'database_creation_note':'Existing byte-bound frozen DB reused; current queries re-executed',
                       'project_seconds':None,'replay_seconds':None,'ablation_seconds':None}}
    write(output/'execution.json',metric)
    started = time.monotonic()
    try:
        base, frozen, manifest = verify_input(args.asset_root,args.prior_run,args.worker)
        write(output/'input-freeze.json',frozen)
        metric.update(source=str(base/'source'),database=str(base/'database'),
                      original_tree_hash=frozen['tree_hash'],selection_sha256=digest(manifest),
                      selection=read(manifest)['selection'],budgets=read(manifest)['budgets'],
                      java_files=len(frozen['files']),source_repository=frozen['source_repository'])
        tick=time.monotonic()
        result = resource_project({'manifest':manifest,'source_root':base/'source',
                                   'database':base/'database','out':output/'project','llm':'off'})
        metric['costs']['project_seconds']=time.monotonic()-tick
        phase_path = output/'project/phase-costs.json'
        metric['phase_costs']=read(phase_path) if phase_path.exists() else None
        metric['project_status']=result['status']
        metric['stage_counts']=result['stage_counts']
        metric['replay']=None
        units=[]
        if (output/'project/analysis/run-index.json').exists():
            tick=time.monotonic()
            try:
                replay=replay_sharded(output/'project/analysis',source_root=base/'source')
            except Exception as exc:
                replay={'consistent':False,'error_type':type(exc).__name__,'error':str(exc)}
            metric['costs']['replay_seconds']=time.monotonic()-tick
            write(output/'replay.json',replay)
            metric['replay']=replay
            tick=time.monotonic()
            for unit_id,payload in iter_run_units(ShardReader(output/'project/analysis')):
                if payload.get('status')!='analyzed':
                    units.append({'unit_id':unit_id,'status':payload.get('status')})
                    continue
                facts=validate_extracted(extracted_from_dict(payload['facts']))
                unit=facts.units[0]
                disabled,_ = _disable_cross_event_propagation(unit)
                ablated_facts=replace(facts,units=(disabled,))
                assert facts.facts==ablated_facts.facts and facts.snapshot_sha256==ablated_facts.snapshot_sha256
                ablated=_analyze_payload(ablated_facts)['units'][0]
                full=payload['results']['units'][0]
                units.append({'unit_id':unit_id,'status':'analyzed','terminated':full['terminated'],
                    'raw_snapshot_sha256':facts.snapshot_sha256,'raw_fact_count':len(facts.facts),
                    'steps':full['steps'],'solver_metrics':full.get('solver_metrics'),
                    'relations':{k:len(getattr(unit.program,k)) for k in ('families','call_bindings','task_bindings')},
                    'binding_property_refs':{kind:[{'binding_id':binding.binding_id,
                        'property_ids':[prop['property_id'] for prop in full['properties']
                            if set(binding.evidence_ids).intersection(prop.get('evidence_refs',[]))]}
                        for binding in getattr(unit.program,kind)] for kind in ('call_bindings','task_bindings')},
                    'binding_property_ref_semantics':'direct evidence-reference overlap; does not imply causal necessity',
                    'full':full['properties'],'ablated':ablated['properties'],
                    'ablated_terminated':ablated['terminated'],'ablated_steps':ablated['steps']})
            metric['costs']['ablation_seconds']=time.monotonic()-tick
        metric['units']=units
        # Process completion is distinct from project/model coverage and RC gates.
        failures = any(row['extraction']!='extracted' or row.get('method_resolution')!='method_resolved'
                       or row['analysis'] not in ('analyzed','not_applicable') for row in result['ledger'])
        failures = failures or any(u.get('status')!='analyzed' or not u.get('terminated')
                                  or not u.get('ablated_terminated') for u in units)
        final_identity=identity()
        if any(final_identity[k]!=metric[k] for k in ('implementation_sha256','query_sha256','runner_sha256')):
            raise ValueError('implementation or query identity changed during worker execution')
        failed_replay = bool(units) and not (metric['replay'] or {}).get('consistent',False)
        metric['status']='failed' if failures or failed_replay else 'complete'
    except Exception as exc:
        metric.update(status='failed',error_type=type(exc).__name__,error=str(exc))
        (output/'failure.log').write_text(traceback.format_exc())
    finally:
        metric['costs']['worker_seconds']=time.monotonic()-started
        metric['costs']['peak_analyzer_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
        metric['costs']['peak_rss_scope']='worker process high-water mark; excludes CodeQL subprocesses'
        write(output/'execution.json',metric)
    return 0 if metric['status']=='complete' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-root',type=Path,required=True)
    parser.add_argument('--prior-run',type=Path,help='Existing v1.2 full-module frozen sources/databases')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--worker',choices=MODULES,help=argparse.SUPPRESS)
    args=parser.parse_args()
    args.asset_root=args.asset_root.resolve(strict=True)
    args.prior_run=(args.prior_run or args.asset_root/'.worktrees/resource-lifecycle-v1_2-20260914/.local-runs/v1.2/independent-20260916').resolve(strict=True)
    if args.worker:
        return worker(args)
    args.out=args.out.resolve()
    args.out.mkdir(parents=True,exist_ok=False)
    run={**identity(),'asset_root':str(args.asset_root),'prior_run':str(args.prior_run),
         'requested_inputs':9,'requested_modules':3,'requested_projects':2,
         'input_role':'development_regression','oracle_available':False,'modules':{}}
    write(args.out/'execution.json',run)
    codes=[]
    for name in MODULES:
        argv=[sys.executable,str(Path(__file__).resolve()),'--asset-root',str(args.asset_root),
              '--prior-run',str(args.prior_run),'--out',str(args.out/name),'--worker',name]
        with (args.out/f'{name}.log').open('w') as log:
            log.write(json.dumps({'argv':argv})+'\n'); log.flush()
            try:
                code=subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=1800).returncode
            except subprocess.TimeoutExpired:
                code=124
            codes.append(code)
        run['modules'][name]={'exit_code':code,'execution_path':str(args.out/name/'execution.json')}
        write(args.out/'execution.json',run)
    run['status']='complete' if not any(codes) else 'failed'
    write(args.out/'execution.json',run)
    print(json.dumps({'status':run['status'],'output':str(args.out)}))
    return 1 if any(codes) else 0

if __name__=='__main__':
    raise SystemExit(main())
