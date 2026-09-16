#!/usr/bin/env python3
"""Restore byte-identical, explicitly frozen module scopes; never runs project code."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def relative_path(value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('source path must remain under the explicit asset root')
    return path

def prepare(asset_root, freeze_path, output, verify_only=False):
    records = json.loads(freeze_path.read_text())
    if len(records) != 3:
        raise ValueError('frozen module denominator differs')
    for record in records:
        name = record['project_id']
        if name not in ('xxl-job-core','hertzbeat-common-core','hertzbeat-common-spring'):
            raise ValueError('unexpected module')
        original = relative_path(record['original_scope'].split('/src/main/java')[0] + '/src/main/java')
        source = asset_root / original
        selected = record['files']
        for rel, expected in {**record.get('excluded_java_files',{}), **selected}.items():
            path = source / relative_path(rel)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f'frozen source changed: {name}/{rel}')
        if not verify_only:
            destination = output / name / 'source'
            destination.mkdir(parents=True,exist_ok=False)
            for rel in selected:
                path = relative_path(rel)
                target = destination / path
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source/path,target)
            (destination.parent/'input-freeze.json').write_text(json.dumps(record,indent=2)+'\n')
        print(f'{name}: {len(selected)} files verified' + ('' if verify_only else ' and mirrored'))

    if not verify_only:
        (output/'selected-attempts.json').write_text(json.dumps({r['project_id']:r['project_id'] for r in records},indent=2)+'\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-root',type=Path,required=True)
    parser.add_argument('--freeze',type=Path,default=ROOT/'reports/lifecycle-v1.2/independent/input-freeze.json')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    prepare(args.asset_root,args.freeze,args.out,args.verify_only)
