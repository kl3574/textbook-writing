#!/usr/bin/env python3
"""Prepare a passive learner view or invalidate dependent objects after a revision."""
import argparse
import json
from pathlib import Path
from release_contract import affected_objects, learner_projection, read_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='command',required=True)
    learner=commands.add_parser('learner')
    learner.add_argument('--html',type=Path,required=True)
    learner.add_argument('--out',type=Path,required=True)
    learner.add_argument('--receipt',type=Path,required=True)
    impact=commands.add_parser('impact')
    impact.add_argument('--before',type=Path,required=True)
    impact.add_argument('--after',type=Path,required=True)
    a=p.parse_args()
    if a.command=='learner':
        output,receipt=learner_projection(a.html.read_text(encoding='utf-8'))
        with a.out.open('x',encoding='utf-8') as f:
            f.write(output)
        with a.receipt.open('x',encoding='utf-8') as f:
            json.dump(receipt,f,ensure_ascii=False,indent=2)
        print(json.dumps(receipt,ensure_ascii=False))
    else:
        print(json.dumps(affected_objects(read_json(a.before),read_json(a.after)),ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
