#!/usr/bin/env python3
"""Two fresh rounds, one pinned manifest; absent required evidence cannot become PASS."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from bs4 import BeautifulSoup
from release_contract import SCHEMA, aggregate, check_content, check_execution, check_math, check_structure, digest, ordinary, pinned, read_json
from browser_checks import run_browser


def review(spec, root, html_sha, registry_sha, role):
    if not spec:
        return {"status":"UNVERIFIED","reason":role.upper()+"_REVIEW_NOT_RUN"}
    try:
        data=read_json(pinned(spec,root))
        if data.get("schema")!="TextbookReview/v1" or data.get("role")!=role:
            raise ValueError("review schema or role mismatch")
        if data.get("html_sha256")!=html_sha or data.get("registry_sha256")!=registry_sha:
            raise ValueError("stale review receipt")
        if data.get("status") not in {"PASS","FAIL"}:
            return {"status":"UNVERIFIED","reason":"review not completed"}
        if not data.get("reviewer") or data.get("independent") is not True or not data.get("evidence"):
            raise ValueError("missing independent reviewer/evidence")
        for item in data["evidence"]:
            pinned(item,root)
        if data.get("blocking_findings"):
            return {"status":"FAIL","findings":data["blocking_findings"]}
        return {"status":data["status"],"reviewer":data["reviewer"],"receipt_sha256":spec["sha256"],"scope":"RECORDED_REVIEW_NOT_AUTHENTICATED_IDENTITY"}
    except (OSError,ValueError,KeyError,TypeError) as error:
        return {"status":"FAIL","reason":str(error)}


def verify_once(html_path: Path, manifest_path: Path, expected: str, allow_execution: bool=False) -> dict:
    html_path,manifest_path=ordinary(html_path),ordinary(manifest_path)
    if digest(manifest_path.read_bytes())!=expected:
        raise ValueError("manifest hash mismatch")
    m=read_json(manifest_path)
    if m.get("schema")!=SCHEMA:
        raise ValueError("release requires TextbookReleaseManifest/v2; v1 is a component check only")
    html=html_path.read_text(encoding="utf-8")
    html_sha=digest(html_path.read_bytes())
    if html_sha!=m.get("artifact",{}).get("sha256"):
        raise ValueError("artifact hash mismatch")
    root=manifest_path.parent
    registry_path=pinned(m["content"],root)
    registry=read_json(registry_path)
    soup=BeautifulSoup(html,"html.parser")
    task=m.get("task",{})
    if task.get("proof_policy") not in {"full","declared-omissions"} or not isinstance(task.get("prerequisites"),list):
        raise ValueError("declare task.proof_policy and task.prerequisites")
    checks={"structure":check_structure(soup,m),"content":check_content(soup,registry,task["proof_policy"]),"math":check_math(soup,m.get("math"),root)}
    # Broken structural bindings must not trigger arbitrary embedded code execution.
    checks["execution"]=(check_execution(soup,m.get("runtime"),allow_execution) if checks["structure"]["status"]=="PASS" else {"status":"UNVERIFIED","reason":"STRUCTURE_FAILED"})
    checks["browser"]=(run_browser(html_path,m.get("browser"),len(soup.select('.math'))) if m.get("profile")=="standalone-publication" else {"status":"NOT_APPLICABLE"})
    mechanical=aggregate([x["status"] for x in checks.values()])
    reviews={role:review(m.get("reviews",{}).get(role),root,html_sha,m["content"]["sha256"],role) for role in ("content","pedagogy")}
    if digest(html_path.read_bytes())!=html_sha or digest(manifest_path.read_bytes())!=expected or digest(registry_path.read_bytes())!=m["content"]["sha256"]:
        raise ValueError("input changed during validation")
    return {"schema":"TextbookReleaseCheck/v2","status":aggregate([mechanical]+[r["status"] for r in reviews.values()]),"mechanical_status":mechanical,"html_sha256":html_sha,"manifest_sha256":expected,"registry_sha256":m["content"]["sha256"],"checks":checks,"reviews":reviews}


def verify_release(html_path: Path, manifest_path: Path, expected: str, allow_execution=False) -> dict:
    rounds=[verify_once(html_path,manifest_path,expected,allow_execution) for _ in range(2)]
    same=rounds[0]==rounds[1]
    return {"schema":"TextbookReleaseRounds/v2","status":aggregate([x["status"] for x in rounds]+(["FAIL"] if not same else [])),"mechanical_status":aggregate([x["mechanical_status"] for x in rounds]+(["FAIL"] if not same else [])),"rounds_identical":same,"rounds":rounds}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--html',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--expected-manifest-sha256',required=True)
    p.add_argument('--allow-execution',action='store_true',help='Run only reviewed/trusted textbook code; not a sandbox')
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    try:
        result=verify_release(a.html,a.manifest,a.expected_manifest_sha256,a.allow_execution)
    except (OSError,ValueError,KeyError,TypeError) as error:
        result={"schema":"TextbookReleaseRounds/v2","status":"FAIL","reason":str(error)}
    a.report.parent.mkdir(parents=True,exist_ok=True)
    with a.report.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
        f.write('\n')
    print(json.dumps({"status":result['status'],"mechanical_status":result.get('mechanical_status'),"report":str(a.report)},ensure_ascii=False))
    return {'PASS':0,'FAIL':1,'UNVERIFIED':2,'BLOCKED':2}[result['status']]

if __name__=='__main__':
    raise SystemExit(main())
