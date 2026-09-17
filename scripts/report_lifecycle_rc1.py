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


def source_identity(base):
    scope_path=base/'project/source-scope.json'
    inventory_path=base/'project/callable-inventory.json'
    scope=read(scope_path) if scope_path.exists() else {}
    inventory=read(inventory_path) if inventory_path.exists() else {}
    queries=[]
    for path in sorted((base/'project/codeql/.generations').glob('*/*.json')):
        if path.name not in ('ResourceLifecycleFacts.json','ResourceLifecycleTaskRelations.json','ResourceLifecycleCallables.json'):
            continue
        decoded=read(path)
        tables=[v for v in decoded.values() if isinstance(v,dict) and isinstance(v.get('tuples'),list)]
        queries.append({'query':path.stem,'decoded_path':str(path),'decoded_sha256':digest(path),
                        'row_count':sum(len(v['tuples']) for v in tables),'decoded_bytes':path.stat().st_size})
    return {'source_tree_hash':scope.get('source_snapshot_sha256'),
            'source_scope_sha256':digest(scope_path) if scope else None,
            'archive_sha256':scope.get('archive_sha256'),'database_fingerprint':inventory.get('database_fingerprint'),
            'source_files':len(scope['source_files']) if scope else None,
            'archived_files':len(scope['archived_files']) if scope else None,
            'unarchived_files':scope.get('unarchived_files'),
            'archived_mismatch_files':scope.get('archived_mismatch_files'),
            'scope_complete':scope.get('scope_complete'),
            'callable_inventory_sha256':digest(inventory_path) if inventory else None,
            'query_outputs':queries}


def build(run,output,acceptance):
    execution=read(run/'execution.json')
    checks=read(acceptance)
    if execution['requested_inputs']!=9 or set(execution['modules'])!=set(MODULES):
        raise ValueError('fixed denominator differs')
    old=read(ROOT/'reports/lifecycle-v1.2/independent/metrics.json')
    old_freezes={r['project_id']:r for r in read(ROOT/'reports/lifecycle-v1.2/independent/input-freeze.json')}
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
        inventory_path=base/'project/callable-inventory.json'
        inventory=read(inventory_path).get('callables',[]) if inventory_path.exists() else []
        for row in result['ledger']:
            if row.get('method_resolution')=='method_missing':
                prefix=row['entry_callable'].rsplit(')',1)[0]+')'
                candidates=[{k:item[k] for k in ('unit_id','source_file','start_line','start_column','source_sha256')}
                    for item in inventory if item['unit_id'].startswith(prefix)]
                row={**row,'identity_diagnostic':{'requested':row['entry_callable'],
                    'same_parameters_different_return_candidates':candidates,
                    'resolution_policy':'exact descriptor only; candidate is not substituted or analyzed'}}
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
        freeze_path=base/'input-freeze.json'
        frozen=read(freeze_path) if freeze_path.exists() else {}
        restored=sorted(set(frozen.get('files',{}))-set(old_freezes[name]['files']))
        modules.append({k:v for k,v in m.items() if k!='units'} | {
            'units':[{k:v for k,v in u.items() if k not in ('full','ablated')} for u in m.get('units',[])],
            'scope_dependency_change':{'restored_file_count':len(restored),
                'restored_packages':sorted({str(Path(f).parent) for f in restored}),
                'remaining_dependency_limits':frozen.get('dependency_limits'),
                'original_freeze_report_sha256':digest(ROOT/'reports/lifecycle-v1.2/independent/input-freeze.json'),
                'new_freeze_sha256':digest(freeze_path) if frozen else None},
            'completed_nonempty_units':len(complete),'before_solver_steps':prior_module['solver_steps'],
            'before_tree_hash':prior_module['tree_hash'],'after_tree_hash':m.get('original_tree_hash'),
            'same_scope_as_v12_report':prior_module['tree_hash']==m.get('original_tree_hash'),
            'scope_change':('Scope identity unavailable because intake did not complete.' if not m.get('original_tree_hash') else
                None if prior_module['tree_hash']==m.get('original_tree_hash') else
                'Restored entire frozen 158-file common-core; v1.2 report used 29-file util package. Before/after solver totals are not same-scope comparisons.'),
            'source_scope_artifact':str(base/'project/source-scope.json'),
            'source_identity':source_identity(base)})
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
        if (any(r.get('method_resolution') not in ('method_resolved','method_missing','ambiguous','source_mismatch')
                or r['extraction']!='extracted' or (r.get('method_resolution')!='method_resolved' and not r.get('reason')) for r in ledger)
                or next(m for m in modules if m['module']=='hertzbeat-common-core').get('java_files')!=158):
            raise ValueError('R2 contradicted by unexplained identity failures or incomplete module scope')
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
                  'run_index':str(run/m['module']/'project/analysis/run-index.json'),
                  'identity':m['source_identity'],'selection':m.get('selection'),'budgets':m.get('budgets'),
                  'before_tree_hash':m['before_tree_hash'],'after_tree_hash':m['after_tree_hash']} for m in modules},
              'transport_limits':{'lifecycle_rows':65536,'other_rows':4096,'decoded_json_bytes':67108864,
                                  'total_string_bytes':16777216,'single_shard_bytes':16777216}}
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
    synth=checks.get('synthetic',{}).get('metrics',{})
    relations={kind:sum(u.get('relations',{}).get(kind,0) for m in modules for u in m['units']) for kind in ('call_bindings','task_bindings')}
    lines.extend(['', '补充验收与解释：', '',
        f"- 合成回归：{synth.get('modes','未提供')}；合成确定性增益 {synth.get('determinacy_gains','未提供')}。它们是开发回归，不是独立研究证据。",
        f"- 固定九输入关系数量：{relations}；独立确定性增益 {metrics['determinate_gain']}。",
        '- 原精确请求未被候选方法替换，方法身份差异的位置/hash/descriptor 见 input-ledger.csv。',
        '- 入口对真实方法身份失败返回非零；rc_ready 表示 R1–R6 的受支持工程门槛通过，不表示九个方法均已分析成功。',
        '', '| 模块 | 提取+适配 s | 求解+序列化 s | 回放 s | Python peak RSS MiB |',
        '| --- | ---: | ---: | ---: | ---: |'])
    def number(value):
        return 'null' if value is None else f'{value:.3f}'
    for m in modules:
        cost=m.get('costs',{}); phases=m.get('phase_costs') or {}
        rss=cost.get('peak_analyzer_rss_bytes')
        lines.append(f"| {m['module']} | {number(phases.get('extraction_and_adaptation_seconds'))} | {number(phases.get('solve_and_serialization_seconds'))} | {number(cost.get('replay_seconds'))} | {number(rss/(1024*1024) if rss is not None else None)} |")
    measured=checks.get('same_facts_loop_comparison',{})
    if measured:
        b,a=measured['baseline'],measured['current']
        lines.extend(['',f"同一冻结 ArrowUtil facts：steps {b['steps']} → {a['steps']}；配置 {b.get('diagnostic_configuration_counts',{}).get('exact_configurations')} → {a['solver_metrics']['abstract_configurations']}；最终 widening {a['solver_metrics']['widening_count']}、subsumption {a['solver_metrics']['subsumption_count']}。耗时 {b['elapsed_seconds']:.6f} → {a['elapsed_seconds']:.6f} s，peak RSS {b['peak_rss_kib']} → {a['peak_rss_kib']} KiB。", '这些是同机实际测量，包含并发负载影响；完整模块的不同源码范围成本另列，不作跨范围收益比较。'])
    (output/'summary.md').write_text('\n'.join(lines)+'\n')
    return metrics

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--acceptance',type=Path,required=True)
    args=parser.parse_args()
    build(args.root_run,args.out,args.acceptance)
