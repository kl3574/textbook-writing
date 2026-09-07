#!/usr/bin/env python3
"""Prepare independent old/new/no-skill packets; collect evidence, never invent runs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import shutil
from release_contract import digest, pinned, read_json


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')


def prepare(cases,old,new,out,seed):
    out.mkdir(parents=True,exist_ok=False)
    rng=random.Random(seed);records=[]
    for case in read_json(cases)['cases']:
        labels=['A','B','C'];rng.shuffle(labels)
        for condition,label in zip(('old','new','none'),labels):
            root=out/case['id']/label;root.mkdir(parents=True)
            prompt=case['prompt']
            if condition!='none':
                source=old if condition=='old' else new
                if not (source/'SKILL.md').is_file():raise ValueError('snapshot lacks SKILL.md: '+str(source))
                # No credentials, git database, dependency installs, or previous run outputs.
                target=root/'skill';target.mkdir()
                selected=['SKILL.md','VERSION','references','scripts','requirements.txt']
                for name in selected:
                    src=source/name
                    if src.is_file():shutil.copy2(src,target/name)
                    elif src.is_dir():shutil.copytree(src,target/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
                prompt+='\n\n执行时读取此独立目录内 skill/SKILL.md；不要读取其它评测目录。'
            prompt+='\n\n把产物保存到本目录 outputs/。此任务需全新隔离会话；不要读取评分答案。'
            (root/'prompt.md').write_text(prompt,encoding='utf-8')
            records.append({'case_id':case['id'],'label':label,'condition':condition,'path':str(root.relative_to(out)),'prompt_sha256':digest(prompt),'case_prompt_sha256':digest(case['prompt'])})
    write_json(out/'private'/'mapping.json',{'seed':seed,'runs':records,'status':'PREPARED_NOT_RUN'})
    return {'status':'PREPARED_NOT_RUN','packet_count':len(records),'workspace':str(out)}


def collect(workspace):
    mapping=read_json(workspace/'private'/'mapping.json');rows=[]
    for expected in mapping['runs']:
        root=workspace/expected['path'];path=root/'receipt.json'
        row={**expected,'status':'NOT_RUN'}
        if path.exists():
            try:
                r=read_json(path)
                if r.get('schema')!='TextbookBehaviorRun/v1' or r.get('prompt_sha256')!=expected['prompt_sha256']:
                    raise ValueError('receipt schema/prompt mismatch')
                for field in ('session_id','model','tool_policy_hash','budget','source_snapshot_hash','outputs','logs'):
                    if not r.get(field):raise ValueError('missing '+field)
                for spec in r['outputs']+r['logs']:pinned(spec,root)
                if r.get('status') not in {'PASS','FAIL'}:raise ValueError('run not completed')
                for field in ('tokens','duration_ms'):
                    if r.get(field) is not None and (type(r[field]) is not int or r[field]<0):raise ValueError('invalid measured '+field)
                row.update(status=r['status'],session_id=r['session_id'],model=r['model'],tool_policy_hash=r['tool_policy_hash'],budget=r['budget'],source_snapshot_hash=r['source_snapshot_hash'],tokens=r.get('tokens'),duration_ms=r.get('duration_ms'))
            except (OSError,ValueError,KeyError,TypeError) as error:row.update(status='INVALID_EVIDENCE',reason=str(error))
        rows.append(row)
    mismatches=[]
    for case_id in sorted({r['case_id'] for r in rows}):
        group=[r for r in rows if r['case_id']==case_id and r['status'] in {'PASS','FAIL'}]
        if len(group)==3:
            for field in ('model','tool_policy_hash','budget','source_snapshot_hash'):
                if len({json.dumps(r[field],sort_keys=True) for r in group})!=1:mismatches.append(case_id+':'+field)
            if len({r['session_id'] for r in group})!=3:mismatches.append(case_id+':non_independent_session_ids')
    complete=all(r['status'] in {'PASS','FAIL'} for r in rows) and not mismatches
    return {'schema':'TextbookBehaviorCollection/v1','status':'COMPLETE_RECORDS_NOT_LEARNING_CERTIFICATION' if complete else 'INCOMPLETE','runs':rows,'comparison_mismatches':mismatches,'note':'PASS/FAIL are recorded grader judgments, not independently established by this collector. No token estimate substitutes for unavailable usage.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    prep=subs.add_parser('prepare')
    for arg in ('cases','old','new','out'):prep.add_argument('--'+arg,type=Path,required=True)
    prep.add_argument('--seed',type=int,default=20260907)
    c=subs.add_parser('collect');c.add_argument('--workspace',type=Path,required=True)
    a=p.parse_args()
    result=prepare(a.cases,a.old,a.new,a.out,a.seed) if a.command=='prepare' else collect(a.workspace)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
