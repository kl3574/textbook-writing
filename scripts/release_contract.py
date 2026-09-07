#!/usr/bin/env python3
"""Object-bound textbook checks. These checks do not certify mathematical truth."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any
from bs4 import BeautifulSoup, Comment, Doctype

SCHEMA = "TextbookReleaseManifest/v2"
PROFILES = {"authoring-master", "note-fragment", "standalone-publication"}
HEX = re.compile(r"^[0-9a-f]{64}$")


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def read_json(path: Path) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def ordinary(path: Path) -> Path:
    # Check before resolve: resolving first silently follows symlinks.
    path = path.expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"not an ordinary file: {path}")
    return path


def pinned(spec: dict, root: Path) -> Path:
    path = ordinary(root / spec["path"])
    if not HEX.fullmatch(str(spec.get("sha256", ""))) or digest(path.read_bytes()) != spec["sha256"]:
        raise ValueError(f"hash mismatch: {path.name}")
    return path


def tex_of(node) -> tuple[str, bool]:
    annotation = node.find("annotation", attrs={"encoding": "application/x-tex"})
    explicit = node.get("data-tex")
    display = node.get("data-display") == "true"
    if explicit is not None or annotation is not None:
        text = explicit if explicit is not None else annotation.get_text()
        if not text.strip():
            raise ValueError("empty TeX")
        return text.strip(), display
    text = node.get_text().strip()
    for left, right, block in ((r"\[", r"\]", True), (r"\(", r"\)", False), ("$$", "$$", True), ("$", "$", False)):
        if text.startswith(left) and text.endswith(right) and len(text) > len(left) + len(right):
            body = text[len(left):-len(right)]
            if left == "$" and (text.startswith("$$") or text.endswith("$$")):
                continue
            return body, display or block
    raise ValueError("expected balanced \\(…\\), \\[…\\], $…$ or $$…$$")


def aggregate(statuses: list[str]) -> str:
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if any(x not in {"PASS", "NOT_APPLICABLE"} for x in statuses):
        return "UNVERIFIED"
    return "PASS"


def node_hash(node) -> str:
    return digest(str(node))


def check_structure(soup, manifest: dict) -> dict:
    errors = []
    ids = [n.get("id") for n in soup.select("[id]")]
    if len(ids) != len(set(ids)) or any(not x for x in ids):
        errors.append("duplicate_or_empty_dom_id")
    for n in soup.select('a[href^="#"]'):
        if n["href"][1:] not in ids:
            errors.append("broken_link:" + n["href"])
    inventory = manifest.get("inventory", {})
    selectors = {"math": ".math", "code": "code.language-python", "output": "pre.program-output"}
    for kind, selector in selectors.items():
        actual = [n.get("id") for n in soup.select(selector)]
        declared = inventory.get(kind)
        if not isinstance(declared, list) or any(not isinstance(x, str) or not x for x in declared) or len(declared) != len(set(declared)) or declared != actual:
            errors.append("inventory:" + kind)
    for text in soup.find_all(string=True):
        if isinstance(text, (Comment, Doctype)):
            continue
        if any(p.name in {"script", "style", "pre", "code", "math", "annotation"} or "math" in p.get("class", []) or "katex" in p.get("class", []) for p in text.parents):
            continue
        if re.search(r"\\[\[\]() ]|\$\$|\$[^$\n]+\$", str(text)):
            errors.append("unregistered_math:" + str(text)[:80])
    profile = manifest.get("profile")
    if profile not in PROFILES:
        errors.append("profile")
    if profile == "standalone-publication":
        if not any(isinstance(x, Doctype) and str(x).lower() == "html" for x in soup.contents):
            errors.append("doctype")
        for tag in ("html", "head", "body"):
            if len(soup.find_all(tag)) != 1:
                errors.append("document_tag:" + tag)
        for n in soup.select("script[src],link[href],img[src],source[src],iframe,object,embed"):
            value = n.get("src", n.get("href", ""))
            if n.name in {"iframe", "object", "embed"} or not value.startswith("data:"):
                errors.append("external_asset:" + n.name)
    if profile == "note-fragment":
        if any(isinstance(n, Doctype) for n in soup.contents):
            errors.append("note_doctype")
        roots = [n for n in soup.contents if getattr(n, "name", None)]
        if len(roots) != 1 or roots[0].name != "div" or roots[0].get("data-schema-version") != "9":
            errors.append("note_root")
        allowed = set("div p span h1 h2 h3 h4 h5 h6 a em strong b i u s sub sup br hr ul ol li dl dt dd blockquote pre code table caption colgroup col thead tbody tfoot tr th td details summary figure figcaption img".split())
        attrs = {"id", "class", "title", "lang", "dir", "href", "src", "alt", "width", "height", "colspan", "rowspan", "scope", "open", "start", "type"}
        for n in soup.find_all(True):
            if n.name not in allowed:
                errors.append("active_note_element:" + n.name)
            for key, value in n.attrs.items():
                if key not in attrs and not key.startswith(("data-", "aria-")):
                    errors.append("active_note_attribute:" + key)
                if key in {"href", "src"}:
                    normalized = re.sub(r"[\x00-\x20\x7f]", "", str(value)).lower()
                    if not normalized.startswith(("https://", "http://", "#", "mailto:")) and not (key == "src" and normalized.startswith("data:image/png;base64,")):
                        errors.append("active_note_url")
    return {"status": "FAIL" if errors else "PASS", "errors": errors}


def check_math(soup, config: dict | None, root: Path) -> dict:
    nodes = soup.select(".math")
    if not nodes:
        return {"status": "NOT_APPLICABLE", "count": 0}
    rows, errors = [], []
    for n in nodes:
        try:
            tex, display = tex_of(n)
            if "\t" in tex or re.search(r"&(?:amp;)*(?:lt|gt);|&#(?:60|62);|&#x(?:3c|3e);", tex, re.I):
                raise ValueError("tab or residual HTML entity")
            rows.append({"id": n.get("id"), "tex": tex, "display": display})
        except ValueError as error:
            errors.append({"id": n.get("id"), "error": str(error)})
    if errors:
        return {"status": "FAIL", "errors": errors}
    if not config:
        return {"status": "UNVERIFIED", "reason": "KATEX_NOT_CONFIGURED", "count": len(rows)}
    try:
        path = pinned(config, root)
        js = """const fs=require('fs'),k=require(process.argv[1]);const p=JSON.parse(fs.readFileSync(0,'utf8'));const errors=[];for(const r of p.rows){try{k.renderToString(r.tex,{displayMode:r.display,throwOnError:true,strict:'error',trust:false,maxExpand:1000,macros:p.macros});}catch(e){errors.push({id:r.id,error:String(e)});}}console.log(JSON.stringify({version:k.version,errors}));"""
        done = subprocess.run(["node", "-e", js, str(path)], input=json.dumps({"rows": rows, "macros": config.get("macros", {})}), capture_output=True, text=True, timeout=60, check=False)
        if done.returncode:
            raise RuntimeError(done.stderr[-1000:])
        result = json.loads(done.stdout)
        if result["version"] != config.get("version"):
            result["errors"].append({"error": "katex_version_mismatch"})
        return {"status": "FAIL" if result["errors"] else "PASS", "count": len(rows), **result}
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        return {"status": "BLOCKED", "reason": str(error)}


def run_code(code: str, executable: str, imports: list[str], timeout: int = 30) -> dict:
    path = ordinary(Path(executable).resolve())
    if not Path(executable).is_absolute() or not os.access(path, os.X_OK):
        raise ValueError("Python executable must be explicit, absolute and executable")
    if not isinstance(imports, list) or any(not isinstance(x, str) or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", x) for x in imports):
        raise ValueError("invalid required_imports")
    # Reduces incidental state/secret inheritance; NOT a security sandbox.
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR"}}
    env["PYTHONHASHSEED"] = "0"
    with tempfile.TemporaryDirectory(prefix="textbook-example-") as cwd:
        preflight = subprocess.run([str(path), "-I", "-c", "\n".join("import " + x for x in imports) or "pass"], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)
        if preflight.returncode:
            return {"status": "FAIL", "reason": "runtime_preflight", "stderr": preflight.stderr[-1000:]}
        done = subprocess.run([str(path), "-I", "-c", code], cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, check=False)
    return {"status": "PASS" if done.returncode == 0 else "FAIL", "returncode": done.returncode, "stdout": done.stdout.strip(), "stderr": done.stderr[-1000:], "code_sha256": digest(code), "python_sha256": digest(path.read_bytes())}


def check_execution(soup, runtime: dict | None, allow: bool) -> dict:
    codes, outputs = soup.select("code.language-python"), soup.select("pre.program-output")
    if not codes and not outputs:
        return {"status": "NOT_APPLICABLE", "results": []}
    errors, bindings = [], {}
    for n in codes:
        key = n.get("data-example-id")
        if not key or key in bindings:
            errors.append("missing_or_duplicate_example_id")
        bindings[key] = n
    seen = set()
    for n in outputs:
        target = n.get("data-for")
        if target not in bindings or target in seen:
            errors.append("invalid_or_reused_output_binding")
        seen.add(target)
    if seen != set(bindings):
        errors.append("missing_example_output")
    if errors:
        return {"status": "FAIL", "errors": errors, "results": []}
    if not runtime or not allow:
        return {"status": "UNVERIFIED", "reason": "RUNTIME_NOT_CONFIGURED" if not runtime else "EXECUTION_NOT_AUTHORIZED", "results": []}
    results = []
    for output in outputs:
        key = output["data-for"]
        try:
            result = run_code(bindings[key].get_text(), runtime["python_executable"], runtime.get("required_imports", []), min(120, max(1, int(runtime.get("timeout_seconds", 30)))))
            result.update(example_id=key, output_id=output.get("id"))
            if result["status"] == "PASS" and result["stdout"] != output.get_text().strip():
                result.update(status="FAIL", reason="program_output_mismatch", displayed=output.get_text().strip())
        except subprocess.TimeoutExpired:
            result = {"status": "FAIL", "reason": "TIMEOUT", "example_id": key}
        except (OSError, ValueError, KeyError) as error:
            result = {"status": "BLOCKED", "reason": str(error), "example_id": key}
        results.append(result)
    return {"status": aggregate([x["status"] for x in results]), "results": results}


def check_content(soup, registry: dict, proof_policy: str = "full") -> dict:
    errors = []
    if registry.get("schema") != "TextbookContent/v1":
        errors.append("content_schema")
    objects = registry.get("objects", [])
    by_id = {o["id"]: o for o in objects}
    if len(by_id) != len(objects):
        errors.append("duplicate_object_id")
    actual = {n.get("id"): n for n in soup.select("[data-object-type]")}
    if set(actual) != set(by_id):
        errors.append("object_inventory")
    sources = {s["id"]: s for s in registry.get("sources", [])}
    allowed_roles = {"necessary-proved", "sufficient", "technical", "redundant", "unknown"}
    for key, obj in by_id.items():
        node = actual.get(key)
        if node is None or node.get("data-object-type") != obj.get("type"):
            errors.append("object_node:" + key)
            continue
        if node_hash(node) != obj.get("content_sha256"):
            errors.append("stale_object:" + key)
        if not node.get_text(strip=True):
            errors.append("empty_object:" + key)
        for dep in obj.get("depends_on", []):
            if dep not in by_id:
                errors.append("missing_dependency:" + key + ":" + dep)
        kind = obj["type"]
        if kind in {"theorem", "lemma", "proposition"}:
            proof = by_id.get(obj.get("proof_id"), {})
            if proof.get("type") != "proof" or proof.get("proves") != key:
                errors.append("proof_binding:" + key)
            for field in ("variables", "assumptions", "quantifiers", "conclusion", "source_ids"):
                if not obj.get(field):
                    errors.append("missing_" + field + ":" + key)
            for var in obj.get("variables", []):
                if not all(var.get(x) for x in ("symbol", "domain", "shape")):
                    errors.append("variable_domain_shape:" + key)
            for assumption in obj.get("assumptions", []):
                if not assumption.get("statement") or assumption.get("role") not in allowed_roles:
                    errors.append("assumption_role:" + key)
                if assumption.get("role") == "necessary-proved" and assumption.get("evidence_id") not in by_id:
                    errors.append("necessity_evidence:" + key)
        if kind == "proof" and proof_policy == "full" and (obj.get("omitted") or re.search("证明略|易证|显然", node.get_text())):
            errors.append("proof_omission:" + key)
        if kind == "exercise":
            solutions = [o for o in objects if o.get("type") == "solution" and o.get("for") == key]
            if len(solutions) != 1:
                errors.append("solution_cardinality:" + key)
        if kind == "solution":
            if by_id.get(obj.get("for"), {}).get("type") != "exercise" or node.get("data-solution-for") != obj.get("for"):
                errors.append("solution_binding:" + key)
            if node.name != "details" or node.has_attr("open") or not node.find("summary") or not node.get_text(strip=True).removeprefix(node.find("summary").get_text(strip=True)):
                errors.append("solution_not_collapsed_or_empty:" + key)
        for sid in obj.get("source_ids", []):
            source = sources.get(sid, {})
            if source.get("kind") == "original-derivation":
                if not source.get("locator"):
                    errors.append("source_locator:" + sid)
            elif not all(source.get(x) for x in ("url", "locator", "version", "accessed")):
                errors.append("source_metadata:" + sid)
    active, done = set(), set()
    def visit(key):
        if key in active:
            errors.append("dependency_cycle:" + key)
            return
        if key in done or key not in by_id:
            return
        active.add(key)
        for dep in by_id[key].get("depends_on", []):
            visit(dep)
        active.remove(key)
        done.add(key)
    for key in by_id:
        visit(key)
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "object_count": len(objects), "scope": "STRUCTURE_AND_PROVENANCE_NOT_MATHEMATICAL_TRUTH"}


def affected_objects(before: dict, after: dict) -> dict:
    old = {x["id"]: x for x in before["objects"]}
    new = {x["id"]: x for x in after["objects"]}
    changed = {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
    old_sources = {x["id"]: x for x in before.get("sources", [])}
    new_sources = {x["id"]: x for x in after.get("sources", [])}
    source_changes = {k for k in old_sources.keys() | new_sources.keys() if old_sources.get(k) != new_sources.get(k)}
    affected = set(changed)
    for obj in list(old.values()) + list(new.values()):
        if set(obj.get("source_ids", [])) & source_changes:
            affected.add(obj["id"])
    while True:
        prior = set(affected)
        for obj in list(old.values()) + list(new.values()):
            if set(obj.get("depends_on", [])) & affected:
                affected.add(obj["id"])
        if prior == affected:
            return {"changed": sorted(changed), "changed_sources": sorted(source_changes), "requires_review": sorted(affected)}


def learner_projection(html: str) -> tuple[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    removed = []
    for node in list(soup.select('[data-object-type="solution"],[data-solution-for],.solution,.answer,[data-eval-private]')):
        if node.parent is not None:
            removed.append(node.get("id", "unlabelled"))
            node.decompose()
    # A passive copy: CSS generated content, scripts, comments and templates can leak answers.
    for node in list(soup.select("script,style,template,iframe,object,embed,[hidden]")):
        if node.parent is not None:
            node.decompose()
    for node in soup.find_all(string=lambda x: isinstance(x, Comment)):
        node.extract()
    for node in soup.find_all(True):
        for key in list(node.attrs):
            if key.startswith("on") or key == "style" or (key.startswith("data-") and key not in {"data-tex", "data-display", "data-object-type"}):
                del node[key]
    ids = {n.get("id") for n in soup.select("[id]")}
    for node in list(soup.select('a[href^="#"]')):
        if node["href"][1:] not in ids:
            node.unwrap()
    result = str(soup)
    return result, {"schema": "TextbookLearnerProjection/v1", "source_sha256": digest(html), "learner_sha256": digest(result), "removed_solution_ids": removed, "scope": "REMOVES_LABELLED_PRIVATE_CONTENT_NOT_A_SEMANTIC_LEAK_PROOF"}
