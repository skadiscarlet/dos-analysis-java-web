#!/usr/bin/env python3
"""Report explicitly frozen local module evaluations; no oracle or target discovery."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dosweb.resource_lifecycle.adapters import extracted_from_dict, validate_extracted
from dosweb.resource_lifecycle.commands import _analyze_payload, _implementation_sha256
from dosweb.resource_lifecycle.shards import ShardReader
from dosweb.resource_lifecycle.sharded_run import iter_run_units
from dosweb.resource_lifecycle.source_evaluation import _disable_cross_event_propagation

MODULES = ('xxl-job-core', 'hertzbeat-common-core', 'hertzbeat-common-spring')

def read(path):
    return json.loads(path.read_text())

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def csvwrite(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list,tuple)) else v for k,v in row.items()})

def key(prop):
    return tuple(prop.get(k) for k in ('analysis_unit_id','resource_family_id','executor_id','dimension','scope','cut'))

def build(run, output):
    output.mkdir(parents=True, exist_ok=True)
    ledger, properties, comparison, modules = [], [], [], []
    implementation = _implementation_sha256()
    attempts = read(run / "selected-attempts.json")
    for name in MODULES:
        base = run / attempts[name]
        freeze = read(base / 'input-freeze.json')
        if freeze['implementation_sha256'] != implementation:
            raise ValueError('frozen implementation changed')
        result = read(base / 'project/project-results.json')
        if result.get('status') == 'running':
            raise ValueError('project still running')
        if result['requested'] != 3 or len(result['ledger']) != 3:
            raise ValueError('module denominator changed')
        ledger.extend({'module':name, **row} for row in result['ledger'])
        item = {'module':name, 'revision':freeze['revision'], 'tree_hash':freeze['tree_hash'],
                'source_repository':freeze['source_repository'], 'original_scope':freeze['original_scope'],
                'java_files':len(freeze['files']), 'selected_attempt':attempts[name], 'requested':3, 'stage_counts':result['stage_counts'],
                'build_mode':'none','compilation_verified':False,'status':result['status'],
                'dependency_limits':freeze['dependency_limits'], 'exclusions':freeze['exclusions'],
                'analyzed_units':0, 'completed_solver_units':0, 'solver_budget_exits':0, 'raw_fact_count':0, 'solver_steps':0,
                'serialized_evidence_bytes':result.get('serialized_evidence_bytes'),
                'max_shard_bytes':result.get('max_shard_bytes'),
                'wall_clock_seconds':None, 'wall_clock_measurement':'not separately instrumented; native logs retained',
                'relations':Counter(), 'modes':{}, 'replay':None}
        if (base / 'project/analysis/run-index.json').exists():
            reader = ShardReader(base / 'project/analysis')
            if reader.index['identity']['implementation_sha256'] != implementation:
                raise ValueError('saved implementation differs')
            for unit_id, payload in iter_run_units(reader):
                if payload.get('status') != 'analyzed':
                    continue
                facts = validate_extracted(extracted_from_dict(payload['facts']))
                unit = facts.units[0]
                item['analyzed_units'] += 1
                for label in ('families','call_bindings','task_bindings'):
                    item['relations'][label] += len(getattr(unit.program,label))
                full = payload['results']['units'][0]
                item['raw_fact_count'] += len(facts.facts)
                item['solver_steps'] += full['steps']
                item['completed_solver_units'] += full['terminated'] is True
                item['solver_budget_exits'] += full['terminated'] is not True
                disabled, _ = _disable_cross_event_propagation(unit)
                ablated_facts = replace(facts, units=(disabled,))
                assert ablated_facts.facts == facts.facts and ablated_facts.snapshot_sha256 == facts.snapshot_sha256
                ablated = _analyze_payload(ablated_facts)['units'][0]
                for mode, observed in (('full',full),('disable_cross_event_propagation',ablated)):
                    properties.extend({'module':name,'mode':mode,**p} for p in observed['properties'])
                full_by_key = {key(p):p for p in full['properties']}
                ablated_by_key = {key(p):p for p in ablated['properties']}
                for identity in sorted(set(full_by_key)|set(ablated_by_key), key=str):
                    f,a = full_by_key.get(identity),ablated_by_key.get(identity)
                    representative = f or a
                    comparison.append({'module':name,'analysis_unit_id':unit_id,
                        'dimension':representative['dimension'],'scope':representative['scope'],'cut':representative['cut'],
                        'resource_family_id':representative.get('resource_family_id'),'executor_id':representative.get('executor_id'),
                        'raw_fact_snapshot_sha256':facts.snapshot_sha256,
                        'full_property_id':f['property_id'] if f else None,'ablated_property_id':a['property_id'] if a else None,
                        'full_status':f['status'] if f else 'missing_property',
                        'ablated_status':a['status'] if a else 'missing_property',
                        'full_upper_bound':f.get('upper_bound') if f else None,'ablated_upper_bound':a.get('upper_bound') if a else None,
                        'full_unknown_reasons':f.get('unknown_reasons',[]) if f else ['missing_property'],
                        'ablated_unknown_reasons':a.get('unknown_reasons',[]) if a else ['missing_property'],
                        'determinate_gain':bool(f and f['status'] not in ('unknown','missing_property') and (not a or a['status']=='unknown'))})
            replay_path = base / 'replay.json'
            item['replay'] = read(replay_path) if replay_path.exists() else None
        for mode in ('full','disable_cross_event_propagation'):
            selected = [p for p in properties if p['module']==name and p['mode']==mode]
            item['modes'][mode] = {'requested_inputs':3,'analyzed_units':item['analyzed_units'],
                'published_properties':len(selected),
                'determinate_fraction':sum(p['status']!='unknown' for p in selected)/len(selected) if selected else None, 'status_counts':dict(Counter(p['status'] for p in selected)),
                'unknown_reasons':dict(Counter(r for p in selected if p['status']=='unknown' for r in p['unknown_reasons'])),
                'by_dimension':{d:dict(Counter(p['status'] for p in selected if p['dimension']==d)) for d in sorted({p['dimension'] for p in selected})}}
        modules.append(item)
    completed = [m for m in modules if m['analyzed_units'] and m['replay'] and m['replay'].get('consistent') is True]
    history = {}
    if attempts['hertzbeat-common-core'] != 'hertzbeat-common-core':
        previous = read(run / 'hertzbeat-common-core/project/project-results.json')
        diagnostic = read(run / 'hertzbeat-common-core/diagnostic-extraction/failure.json')
        history['hertzbeat-common-core'] = {'initial_full_module_attempt': previous['stage_counts'],
            'diagnostic': diagnostic, 'reason': '8885 raw rows exceed 4096 decoder cap; original failure retained',
            'revised_scope': 'entire original util package; selected method bodies unchanged',
            'dependency_omissions': 'other common-core packages including generated CollectRep'}
    report = {'attempt_history':history,'implementation_sha256' :implementation,'requested_inputs':len(ledger),'requested_modules':3,
              'modules_with_analysis_and_replay':len(completed),
              'projects_with_analysis_and_replay':len({m['source_repository'] for m in completed}),
              'H4':'pass' if len(completed)>=2 else 'blocked','oracle_available':False,
              'interpretation':'maintenance resource-property coverage only; no vulnerability labels, exploitability or dynamic conclusions',
              'rules_changed_for_inputs':False,'determinacy_gains':sum(r['determinate_gain'] for r in comparison),
              'modules':modules,'report_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write(output/'metrics.json',report)
    csvwrite(output/'input-ledger.csv',ledger)
    csvwrite(output/'properties.csv',properties)
    csvwrite(output/'comparison.csv',comparison)
    write(output/'input-freeze.json',[read(run/attempts[name]/'input-freeze.json') for name in MODULES])
    summary = ['# v1.2 独立模块静态源码评价','',f"H4: **{report['H4']}**；9 条请求，3 个已有模块；实际完成分析与回放 {len(completed)} 个模块，来自 {report['projects_with_analysis_and_replay']} 个项目。",'',
        '源码来自用户允许的 PoC 所属本地仓库。仅检查所选方法的维护性资源性质，没有执行 PoC、服务或负载。',
        'common-core最初完整模块产出8885行，触发4096行解码上限；后续限制为完整util包，排除包及文件hash留存，不修改所选方法或分析规则。原 DB 的归档字节匹配，但 live 有未归档文件，未放宽严格校验。完整主源码按原字节镜像，重新 build-mode=none 提取；不代表项目编译或外部依赖完整。XXL-JOB失败输入仍保留，新增HertzBeat common-spring后总分母为9。',
        '无独立 oracle，不计算准确率或漏洞检出。完整/消融使用同一raw facts和正式properties；缺性质显式missing_property。', '',
        f"确定性质增益：{report['determinacy_gains']}。模型未因这些输入修改，零增益也如实保留。",'']
    for m in modules:
        summary.append(f"- {m['module']}: {m['completed_solver_units']}/3 完成求解，预算退出 {m['solver_budget_exits']}，{m['status']}；full性质 {m['modes']['full']['status_counts']}。")
    (output/'summary.md').write_text('\n'.join(summary)+'\n')
    print(json.dumps({'H4':report['H4'],'modules':len(completed),'gains':report['determinacy_gains']}))

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    build(args.root_run,args.out)
