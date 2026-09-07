#!/usr/bin/env python3
"""Browser receipts for the same release manifest; no silent navigation fallback."""
from __future__ import annotations
from importlib.metadata import version
from pathlib import Path
from typing import Any
from release_contract import aggregate, digest, ordinary

PROBE_JS = r"""async ({renderer, families}) => {
 const math = [...document.querySelectorAll('.math')];
 const root = document.documentElement, body = document.body;
 const errors = [];
 if (root.scrollWidth > root.clientWidth + 1) errors.push('document_horizontal_overflow');
 for (const n of [root,body]) if (['hidden','clip'].includes(getComputedStyle(n).overflowX)) errors.push('document_overflow_mask');
 for (const n of document.querySelectorAll('table')) if (!n.closest('.table-wrap')) errors.push('unwrapped_table');
 for (const n of document.querySelectorAll('.table-wrap,.math,pre')) {
   if (!n.getClientRects().length) continue;
   if (n.scrollWidth > n.clientWidth + 1) {
     const style = getComputedStyle(n);
     if (!['auto','scroll'].includes(style.overflowX)) errors.push('unscrollable_component:'+(n.id||n.tagName));
     else {const before=n.scrollLeft; n.scrollLeft=n.scrollWidth; if(n.scrollLeft<1) errors.push('scroll_unreachable:'+(n.id||n.tagName)); n.scrollLeft=before;}
   }
   let p=n.parentElement;
   while(p && p!==body) {
     const style=getComputedStyle(p), a=n.getBoundingClientRect(), b=p.getBoundingClientRect();
     if (['hidden','clip'].includes(style.overflowX) && (a.right>b.right+1 || a.left<b.left-1)) errors.push('ancestor_clipping:'+(n.id||n.tagName));
     p=p.parentElement;
   }
 }
 for (const n of document.images) if (!n.complete || n.naturalWidth===0) errors.push('broken_image:'+(n.id||n.src));
 if(document.querySelector('.katex-error')) errors.push('katex_error');
 const rendered=math.filter(n=>renderer==='native-mathml'?n.querySelector('math'):n.querySelector('.katex')).length;
 if(rendered!==math.length) errors.push('unrendered_math');
 const fonts=[];
 for (const family of families) {
   const normalized=s=>s.replace(/["']/g,'').trim();
   const declared=[...document.fonts].filter(f=>normalized(f.family)===family);
   let loaded=[];
   try {loaded=await document.fonts.load('16px "'+family+'"','x=0123456789');} catch(e) {errors.push('font_load_error:'+family);}
   const ok=declared.length>0 && loaded.length>0 && loaded.every(f=>f.status==='loaded');
   fonts.push({family,declared:declared.length,loaded:loaded.length,ok});
   if(!ok) errors.push('font_unavailable:'+family);
 }
 return {errors,math_count:math.length,rendered_count:rendered,fonts,scroll_width:root.scrollWidth,client_width:root.clientWidth};
}"""


def run_browser(html_path: Path, config: dict | None, math_count: int) -> dict:
    if config is None:
        return {"status": "UNVERIFIED", "reason": "BROWSER_NOT_CONFIGURED"}
    try:
        from playwright.sync_api import sync_playwright
        executable = ordinary(Path(config["executable"]))
        renderer = config.get("renderer", "katex")
        if renderer not in {"katex", "native-mathml"}:
            raise ValueError("unsupported renderer")
        receipts = []
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(executable), headless=True, args=["--no-sandbox"])
            try:
                for label, width, height in (("desktop",1440,900),("mobile",390,844)):
                    context = browser.new_context(viewport={"width":width,"height":height})
                    page = context.new_page()
                    errors, external = [], []
                    page.on("pageerror", lambda error: errors.append("javascript:"+str(error)))
                    page.on("console", lambda msg: errors.append("console:"+msg.text) if msg.type=="error" else None)
                    page.on("websocket", lambda ws: external.append(ws.url))
                    def route(r):
                        if r.request.url.startswith(("file:","data:","about:")):
                            r.continue_()
                        else:
                            external.append(r.request.url)
                            r.abort()
                    page.route("**/*", route)
                    page.goto(html_path.as_uri(), wait_until="load", timeout=15000)
                    if config.get("ready_expression"):
                        page.wait_for_function(config["ready_expression"], timeout=10000)
                    page.evaluate("document.fonts.ready")
                    options = {"renderer":renderer,"families":config.get("font_families",[])}
                    initial = page.evaluate(PROBE_JS, options)
                    errors.extend(initial["errors"])
                    # Toggle with real clicks; then inspect content initially hidden in answers.
                    details = page.locator('details[data-solution-for]')
                    for i in range(details.count()):
                        node = details.nth(i)
                        if node.get_attribute("open") is not None:
                            errors.append("answer_initially_open")
                        node.locator("summary").first.click()
                        if node.get_attribute("open") is None:
                            errors.append("answer_did_not_open")
                    expanded = page.evaluate(PROBE_JS, options)
                    errors.extend(expanded["errors"])
                    for i in range(details.count()):
                        node = details.nth(i)
                        node.locator("summary").first.click()
                        if node.get_attribute("open") is not None:
                            errors.append("answer_did_not_close")
                    probe = config.get("search")
                    if probe:
                        search = page.locator(probe["selector"])
                        search.fill(probe["query"])
                        page.wait_for_timeout(100)
                        visible = page.locator('article.chapter:visible').count()
                        if not probe["min"] <= visible <= probe["max"]:
                            errors.append("search_matches")
                        search.fill("")
                        page.wait_for_timeout(100)
                        if page.locator('article.chapter:visible').count() != page.locator('article.chapter').count():
                            errors.append("search_restore")
                    if initial["math_count"] != math_count:
                        errors.append("manifest_math_count")
                    if external:
                        errors.append("external_requests")
                    receipts.append({"viewport":label,"status":"FAIL" if errors else "PASS","initial":initial,"expanded":expanded,"errors":errors,"external_requests":external})
                    context.close()
            finally:
                browser.close()
        return {"status":aggregate([r["status"] for r in receipts]),"navigation":"file","viewports":receipts,"runtime":{"chromium_sha256":digest(executable.read_bytes()),"playwright":version("playwright")}}
    except Exception as error:
        return {"status":"BLOCKED","reason":type(error).__name__+":"+str(error),"navigation":"file"}
