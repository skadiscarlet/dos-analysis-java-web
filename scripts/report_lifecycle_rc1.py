#!/usr/bin/env python3
"""Compact RC1 report using existing ledger/property/report conventions."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from report_lifecycle_v12_independent import MODULES, read, write, csvwrite, key
from report_lifecycle_v12 import digest, xml_results, diff_tests


def build(run,output,acceptance):
    execution=read(run/'execution.json')
    checks=read(acceptance)
    if execution['requested_inputs']!=9 or set(execution['modules'])!=set(MODULES):
        raise ValueError('fixed denominator differs')
    old=read(ROOT/'reports/lifecycle-v1.2/independent/metrics.json')
    with (ROOT/'reports/lifecycle-v1.2/independent/input-ledger.csv').open() as stream:
        before={row['input_id']:row for row in csv.DictReader(stream)}
    ledger,properties,comparison,modules=[],[],[],[]
    for name in MODULES:
        base=run/name
        m=read(base/'execution.json')
        if (m['implementation_sha256']!=execution['implementation_sha256']
                or m.get('query_sha256')!=execution.get('query_sha256')
                or m.get('runner_sha256')!=execution.get('runner_sha256')):
            raise ValueError('mixed implementation or query run')
        if m['status']=='running':
            if execution['modules'][name]['exit_code']==0:
                raise ValueError('unfinished worker with successful exit')
            m={**m, 'status':'failed', 'failure_reason':'worker_terminated_without_final_metric'}
        project_path=base/'project/project-results.json'
        if project_path.exists():
            result=read(project_path)
        else:
            # A failure before project intake must retain the original requests,
            # not erase that module from the denominator or invent solved units.
            selected=read(ROOT/'docs/execution/lifecycle-v1.2/inputs'/f'{name}.json')['selection']
            result={'requested':len(selected),'ledger':[
                {**r, 'mapping':'unavailable','method_resolution':'extraction_failed',
                 'extraction':'failed','resource_recognition':'not_attempted','analysis':'skipped',
                 'reason':'worker_failed_before_project_ledger','resource_family_ids':[],'property_ids':[]}
                for r in selected]}
        if result.get('status')=='running':
            raise ValueError('unfinished project ledger')
        if result['requested']!=3 or len(result['ledger'])!=3:
            raise ValueError('module denominator differs')
        for row in result['ledger']:
            prior=before[row['input_id']]
            ledger.append({'module':name,**row,
                'before_mapping':prior['mapping'],'before_extraction':prior['extraction'],
                'before_analysis':prior['analysis'],'before_reason':prior['reason'],
                'replay_consistent':(m.get('replay') or {}).get('consistent') if row['property_ids'] else None})
        for u in m.get('units',[]):
            if u['status']!='analyzed':
                continue
            for mode in ('full','ablated'):
                properties.extend({'module':name,'mode':mode,**p} for p in u[mode])
            full={key(p):p for p in u['full']}; ablated={key(p):p for p in u['ablated']}
            for identity in sorted(set(full)|set(ablated),key=str):
                f,a=full.get(identity),ablated.get(identity)
                representative=f or a
                comparison.append({'module':name,'analysis_unit_id':u['unit_id'],
                    **{k:representative.get(k) for k in ('resource_family_id','executor_id','dimension','scope','cut')},
                    'raw_fact_snapshot_sha256':u['raw_snapshot_sha256'],
                    'full_property_id':f['property_id'] if f else None,'ablated_property_id':a['property_id'] if a else None,
                    'full_status':f['status'] if f else 'missing_property','ablated_status':a['status'] if a else 'missing_property',
                    'full_upper_bound':f.get('upper_bound') if f else None,'ablated_upper_bound':a.get('upper_bound') if a else None,
                    'full_unknown_reasons':f.get('unknown_reasons') if f else ['missing_property'],
                    'ablated_unknown_reasons':a.get('unknown_reasons') if a else ['missing_property'],
                    'determinate_gain':bool(f and f['status']!='unknown' and a and a['status']=='unknown')})
        prior_module=next(x for x in old['modules'] if x['module']==name)
        complete=[u for u in m.get('units',[]) if u.get('terminated') and u.get('relations',{}).get('families',0)>0]
        modules.append({k:v for k,v in m.items() if k!='units'} | {
            'units':[{k:v for k,v in u.items() if k not in ('full','ablated')} for u in m.get('units',[])],
            'completed_nonempty_units':len(complete),'before_solver_steps':prior_module['solver_steps'],
            'before_tree_hash':prior_module['tree_hash'],'after_tree_hash':m.get('original_tree_hash'),
            'same_scope_as_v12_report':prior_module['tree_hash']==m.get('original_tree_hash'),
            'scope_change':('Scope identity unavailable because intake did not complete.' if not m.get('original_tree_hash') else
                None if prior_module['tree_hash']==m.get('original_tree_hash') else
                'Restored entire frozen 158-file common-core; v1.2 report used 29-file util package. Before/after solver totals are not same-scope comparisons.'),
            'source_scope_artifact':str(base/'project/source-scope.json')})
    if len(ledger)!=9 or {r['input_id'] for r in ledger}!=set(before):
        raise ValueError('original input IDs changed')
    testdiff=diff_tests(xml_results(Path(checks['baseline_xml'])),xml_results(Path(checks['current_xml'])))
    gates=checks['gates']
    if set(gates)!={f'R{i}' for i in range(1,7)}:
        raise ValueError('RC gates incomplete')
    for g in gates.values():
        if g['status'] not in ('pass','fail','blocked') or not g.get('evidence'):
            raise ValueError('RC gate lacks explicit evidence')
    unreviewed_skips = sorted(set(testdiff['skipped']['added_ids']) -
                             {k for k,v in checks.get('new_skip_explanations',{}).items() if v})
    testdiff['unexplained_new_skipped_ids']=unreviewed_skips
    if gates['R1']['status']=='pass':
        if any(not Path(m['source_scope_artifact']).exists()
               or not read(Path(m['source_scope_artifact'])).get('scope_complete') for m in modules):
            raise ValueError('R1 contradicted by incomplete source scope audit')
    if gates['R2']['status']=='pass':
        if (any(r.get('method_resolution')!='method_resolved' or r['extraction']!='extracted' for r in ledger)
                or next(m for m in modules if m['module']=='hertzbeat-common-core').get('java_files')!=158):
            raise ValueError('R2 contradicted by unresolved methods or incomplete module scope')
    ready_modules=[m for m in modules if m['completed_nonempty_units'] and (m.get('replay') or {}).get('consistent')]
    if gates['R5']['status']=='pass' and len(ready_modules)<2:
        raise ValueError('R5 contradicted by current runs')
    if gates['R6']['status']=='pass' and (any(testdiff[s]['added_ids'] for s in ('failure','error')) or unreviewed_skips):
        raise ValueError('R6 contradicted by new test failures or unexplained new skips')
    stage_fields=('mapping','method_resolution','extraction','resource_recognition','analysis')
    statuses={mode:dict(Counter(p['status'] for p in properties if p['mode']==mode)) for mode in ('full','ablated')}
    metrics={'engineering_status':'rc_ready' if all(g['status']=='pass' for g in gates.values()) else 'partial',
             'research_evidence':'unvalidated','oracle_available':False,'input_role':'development_regression',
             'requested_inputs':9,'distinct_methods':len({r['entry_callable'] for r in ledger}),
             'projects':2,'modules':3,'gates':gates,
             'stage_counts':{s:dict(Counter(str(r.get(s,'unavailable')) for r in ledger)) for s in stage_fields},
             'completed_nonempty_units':sum(m['completed_nonempty_units'] for m in modules),
             'modules_with_nonempty_analysis_and_replay':len(ready_modules),
             'resource_families':sum(u.get('relations',{}).get('families',0) for m in modules for u in m['units']),
             'property_status_counts':statuses,'determinate_gain':sum(r['determinate_gain'] for r in comparison),
             'properties_by_dimension_cut_status':{mode:[{'dimension':d,'scope':s,'cut':c,'status':st,'count':n}
                 for (d,s,c,st),n in sorted(Counter((p['dimension'],p['scope'],p['cut'],p['status']) for p in properties if p['mode']==mode).items())] for mode in ('full','ablated')},
             'module_results':modules,'acceptance':checks,
             'missing_measurements':'null means not measured or stage not executed; legacy peak RSS/stage costs absent',
             'research_limit':'No independent correctness oracle; no accuracy/recall or vulnerability claim. Synthetic regressions establish only supported-model engineering behavior.'}
    manifest={**execution,'raw_result_root':str(run.resolve()),'acceptance_sha256':digest(acceptance),
              'report_script_sha256':digest(Path(__file__)), 'delivery_state_at_commit':'ready_for_push',
              'source_db_query_identity_artifacts':{m['module']:{'input_freeze':str(run/m['module']/'input-freeze.json'),
                  'scope':m['source_scope_artifact'],'execution':str(run/m['module']/'execution.json'),
                  'run_index':str(run/m['module']/'project/analysis/run-index.json')} for m in modules}}
    output.mkdir(parents=True,exist_ok=True)
    write(output/'metrics.json',metrics); write(output/'run-manifest.json',manifest)
    write(output/'baseline-test-diff.json',testdiff)
    csvwrite(output/'input-ledger.csv',ledger); csvwrite(output/'properties.csv',properties); csvwrite(output/'comparison.csv',comparison)
    lines=['# Lifecycle RC1', '',f"工程状态：**{metrics['engineering_status']}**；research_evidence：**unvalidated**。",
           '', '固定两个项目、三个模块、九个请求；均为本轮开发/回归输入。只做离线静态提取与性质检查。',
           '', '| 门槛 | 状态 | 证据 |','| --- | --- | --- |']
    lines.extend(f"| {k} | {v['status']} | {v['evidence']} |" for k,v in gates.items())
    lines.extend(['',f"阶段计数：`{metrics['stage_counts']}`。",
        f"非空资源单元完成 {metrics['completed_nonempty_units']}，完成求解及选中范围回放的模块 {len(ready_modules)}。",
        f"正式性质：full `{statuses['full']}`；消融 `{statuses['ablated']}`；确定性增益 {metrics['determinate_gain']}。",
        '无独立 oracle，不能计算准确率/召回率，运行完成不构成方法有效性证据。',
        '', '| 输入 | 原分析状态 | 方法身份 | 资源识别 | 当前分析 | 原因 |', '| --- | --- | --- | --- | --- | --- |'])
    lines.extend(f"| {r['input_id']} | {r['before_analysis']} | {r.get('method_resolution')} | {r.get('resource_recognition')} | {r['analysis']} | {r['reason']} |" for r in ledger)
    lines.extend(['','源码、DB、查询、选择与预算身份见 run-manifest.json 及其本地证据引用。common-core 从 29 文件 util 范围恢复 158 文件完整模块；旧/新 hash 见 metrics.json，不能将跨范围 steps 差异当算法收益。',
        '',f"同环境测试：baseline {testdiff['baseline']['counts']}；current {testdiff['current']['counts']}。逐 ID 差分见 baseline-test-diff.json。",
        '', '成本、solver steps/抽象配置/widening/subsumption、关系数量和未测量字段均列在 metrics.json。',
        '', '局限：build-mode=none 不证明编译或依赖完备；未知外部库行为保持 unknown。累计历史分配上界无穷不等于漏洞或结构性无界增长；不覆盖一般动态分派、深度>1、自定义异步或总字节预算。',
        '', '复跑入口和下一阶段实验接续见 docs/execution/lifecycle-rc1/HANDOFF.md。'])
    (output/'summary.md').write_text('\n'.join(lines)+'\n')
    return metrics

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--acceptance',type=Path,required=True)
    args=parser.parse_args()
    build(args.root_run,args.out,args.acceptance)
