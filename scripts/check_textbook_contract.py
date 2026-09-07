#!/usr/bin/env python3
"""Compatibility component checker. Use verify_release.py for publication decisions."""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import legacy_contract as legacy
from release_contract import digest, run_code

TextbookHTMLParser=legacy.TextbookHTMLParser
sha256_bytes=legacy.sha256_bytes
sha256_file=legacy.sha256_file


def extract_tex(node):
    text=str(node['text']).strip()
    for left,right,display in ((r'\[',r'\]',True),(r'\(',r'\)',False),('$$','$$',True),('$','$',False)):
        if text.startswith(left) and text.endswith(right) and len(text)>len(left)+len(right):
            if left=='$' and (text.startswith('$$') or text.endswith('$$')):
                continue
            return text[len(left):-len(right)],display or node['tag']=='pre'
    raise ValueError('math node must have balanced supported delimiters')


def run_examples(parser,runtime):
    if runtime is None:
        return {'status':'NOT_REQUESTED','runs':0,'passed':0,'results':[]},[]
    results,errors=[],[]
    outputs={}
    for n in parser.program_outputs:
        outputs.setdefault(n['article_index'],[]).append(n['text'].strip())
    positions={}
    for index,block in enumerate(parser.python_blocks,start=1):
        try:
            result=run_code(block['text'],runtime['python_executable'],runtime.get('required_imports',[]))
        except Exception as error:
            result={'status':'FAIL','reason':'python_failure','stderr':str(error),'returncode':None}
        article=block['article_index']
        position=positions.get(article,0)
        positions[article]=position+1
        expected=outputs.get(article,[])
        if result['status']!='PASS':
            errors.append({'kind':result.get('reason','python_failure'),'index':index})
        elif position>=len(expected) or expected[position]!=result['stdout']:
            errors.append({'kind':'program_output_mismatch','index':index})
        results.append({'index':index,'article_index':article,'returncode':result.get('returncode'),'stdout_sha256':digest(result.get('stdout',''))})
    if sum(map(len,outputs.values()))!=len(parser.python_blocks):
        errors.append({'kind':'program_output_cardinality'})
    return {'status':'FAIL' if errors else 'PASS','runs':len(results),'passed':sum(x.get('returncode')==0 for x in results),'results':results},errors


legacy.extract_tex=extract_tex
legacy.run_examples=run_examples


def validate(*args,**kwargs):
    result=legacy.validate(*args,**kwargs)
    result['scope']='LEGACY_COMPONENT_ONLY_NOT_RELEASE_APPROVAL'
    result.pop('report_sha256',None)
    result['report_sha256']=digest(json.dumps(result,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    return result


def main():
    args=legacy.parse_args()
    result=validate(args.html,args.manifest,args.expected_manifest_sha256,args.katex_js)
    if args.report:
        legacy.atomic_write_new(args.report,result)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':
    raise SystemExit(main())
