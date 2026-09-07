#!/usr/bin/env python3
"""Validate package layout, version, links and frozen baseline identity."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

REQUIRED=("references/authoring.md","references/content-and-review.md","references/acceptance.md","references/evaluation.md","scripts/verify_release.py","scripts/release_contract.py","scripts/browser_checks.py","scripts/content_tools.py","scripts/behavior_eval.py","scripts/check_textbook_contract.py","scripts/browser_acceptance.py","tests/test_textbook_contract.py","tests/test_release_v3.py","evals/behavior_cases.json","examples/gls/build.py","requirements.txt","VERSION")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',nargs='?',type=Path,default=Path.cwd());a=p.parse_args();root=a.root.resolve();errors=[]
    text=(root/'SKILL.md').read_text(encoding='utf-8')
    version=(root/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):errors.append('VERSION must be semantic x.y.z')
    if not text.startswith('---\n') or not re.search(r'^name:\s*["\']?textbook-writing["\']?\s*$',text,re.M):errors.append('invalid frontmatter/name')
    description=re.search(r'^description:\s*(.+)$',text,re.M)
    if not description or len(description.group(1))<40:errors.append('description missing/too short')
    if 'v'+version not in text:errors.append('SKILL version does not match VERSION')
    for relative in REQUIRED:
        path=root/relative
        if not path.is_file() or path.is_symlink():errors.append('missing/not ordinary: '+relative)
    for relative in re.findall(r'\]\(((?:references|scripts)/[^)#]+)\)',text):
        if not (root/relative).is_file():errors.append('broken resource link: '+relative)
    for relative,expected in [('scripts/legacy_contract.py','bbd4cf8a223b98887def13dd1f21ab9781ee8658'),('scripts/legacy_browser.py','04c02a387edd35535d0b25e651819462118cc45b')]:
        b=(root/relative).read_bytes();actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if actual!=expected:errors.append('frozen baseline changed: '+relative)
    print(json.dumps({'status':'FAIL' if errors else 'PASS','version':version,'errors':errors},ensure_ascii=False))
    return 1 if errors else 0

if __name__=='__main__':raise SystemExit(main())
