from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bs4 import BeautifulSoup
from release_contract import *
from verify_release import verify_release, review
from browser_checks import PROBE_JS, run_browser


def soup(html):
    return BeautifulSoup(html,'html.parser')


def example_html(swapped=False):
    a,b=('2.000000','1.400000') if swapped else ('1.400000','2.000000')
    return f'''<!doctype html><html><head><meta charset="utf-8"></head><body><article class="chapter" id="gls">
<pre><code id="code-gls" class="language-python" data-example-id="gls">y=(1,3); v=(1,4)
print(f"{{sum(a/b for a,b in zip(y,v))/sum(1/b for b in v):.6f}}")</code></pre><pre id="out-gls" class="program-output" data-for="gls">{a}</pre>
<pre><code id="code-mean" class="language-python" data-example-id="mean">print(f"{{(1+3)/2:.6f}}")</code></pre><pre id="out-mean" class="program-output" data-for="mean">{b}</pre></article></body></html>'''


def inventory(s):
    return {k:[n.get('id') for n in s.select(sel)] for k,sel in {'math':'.math','code':'code.language-python','output':'pre.program-output'}.items()}


class ReleaseTests(unittest.TestCase):
    def test_all_delimiters(self):
        for text,display in [(r'\(x^2\)',False),(r'\[x^2\]',True),('$x^2$',False),('$$x^2$$',True)]:
            with self.subTest(text=text):
                self.assertEqual(tex_of(soup('<span>'+text+'</span>').span),('x^2',display))

    def test_unbalanced_delimiter(self):
        for text in (r'\(x\]','$x','$$x$','$$'):
            with self.subTest(text=text),self.assertRaises(ValueError):
                tex_of(soup('<span>'+text+'</span>').span)

    def test_missing_math_runtime_not_pass(self):
        self.assertEqual(check_math(soup(r'<span class="math">\(x\)</span>'),None,Path('.'))['status'],'UNVERIFIED')

    def test_entity_decoding(self):
        good=soup('<span class="math">$x&gt;y$</span>')
        bad=soup('<span class="math">$x&amp;gt;y$</span>')
        self.assertEqual(check_math(good,None,Path('.'))['status'],'UNVERIFIED')
        self.assertEqual(check_math(bad,None,Path('.'))['status'],'FAIL')

    def test_unregistered_math(self):
        s=soup(r'<div>\(x+1\)</div>')
        self.assertIn('unregistered_math:',str(check_structure(s,{'profile':'authoring-master','inventory':inventory(s)})['errors']))

    def test_code_is_exempt_from_math_scan(self):
        s=soup(r'<pre>print("\\(x\\)")</pre>')
        self.assertEqual(check_structure(s,{'profile':'authoring-master','inventory':inventory(s)})['status'],'PASS')

    def test_inventory_missing_formula(self):
        s=soup('<div></div>')
        m={'profile':'authoring-master','inventory':{'math':['eq-required'],'code':[],'output':[]}}
        self.assertEqual(check_structure(s,m)['status'],'FAIL')

    def test_inventory_duplicate_id(self):
        s=soup('<div id="x"></div><p id="x">x</p>')
        self.assertEqual(check_structure(s,{'profile':'authoring-master','inventory':inventory(s)})['status'],'FAIL')

    def test_active_note_events_and_urls(self):
        for fragment in ('<p onclick="x()">a</p>','<a href="java&#x09;script:alert(1)">a</a>','<form>x</form>','<img src="data:image/svg+xml,x">'):
            s=soup('<div data-schema-version="9">'+fragment+'</div>')
            with self.subTest(fragment=fragment):
                self.assertEqual(check_structure(s,{'profile':'note-fragment','inventory':inventory(s)})['status'],'FAIL')

    def test_passive_note(self):
        s=soup('<div data-schema-version="9"><a href="https://example.org">来源</a></div>')
        self.assertEqual(check_structure(s,{'profile':'note-fragment','inventory':inventory(s)})['status'],'PASS')

    def test_missing_local_asset(self):
        s=soup('<!doctype html><html><head></head><body><img src="missing.png"></body></html>')
        self.assertEqual(check_structure(s,{'profile':'standalone-publication','inventory':inventory(s)})['status'],'FAIL')

    def test_correct_gls_outputs(self):
        r=check_execution(soup(example_html()),{'python_executable':sys.executable},True)
        self.assertEqual(r['status'],'PASS',r)

    def test_swapped_gls_outputs(self):
        r=check_execution(soup(example_html(True)),{'python_executable':sys.executable},True)
        self.assertEqual(r['status'],'FAIL')
        self.assertEqual([x.get('reason') for x in r['results']],['program_output_mismatch']*2)

    def test_reused_output_binding(self):
        s=soup(example_html().replace('data-for="mean"','data-for="gls"'))
        self.assertEqual(check_execution(s,{'python_executable':sys.executable},True)['status'],'FAIL')

    def test_execution_requires_authorization(self):
        self.assertEqual(check_execution(soup(example_html()),{'python_executable':sys.executable},False)['status'],'UNVERIFIED')

    def test_missing_runtime(self):
        self.assertEqual(check_execution(soup(example_html()),None,True)['status'],'UNVERIFIED')

    def test_preflight_injection_rejected(self):
        with self.assertRaises(ValueError):
            run_code('print(1)',sys.executable,['os;print(2)'])

    def test_code_failure(self):
        r=run_code('raise RuntimeError("test")',sys.executable,[])
        self.assertEqual(r['status'],'FAIL')

    def test_isolated_working_directory(self):
        r=run_code('from pathlib import Path; print(Path.cwd().name.startswith("textbook-example-"))',sys.executable,[])
        self.assertEqual(r['stdout'],'True')

    def test_empty_solution_is_rejected(self):
        s=soup('<p id="e" data-object-type="exercise">问题</p><details id="s" data-object-type="solution" data-solution-for="e"><summary>答案</summary></details>')
        r={'schema':'TextbookContent/v1','objects':[{'id':'e','type':'exercise','content_sha256':node_hash(s.find(id='e'))},{'id':'s','type':'solution','for':'e','content_sha256':node_hash(s.find(id='s'))}]}
        self.assertEqual(check_content(s,r)['status'],'FAIL')

    def test_solution_wrong_target(self):
        s=soup('<p id="e" data-object-type="exercise">问题</p><details id="s" data-object-type="solution" data-solution-for="other"><summary>答案</summary><p>解答</p></details>')
        r={'schema':'TextbookContent/v1','objects':[{'id':'e','type':'exercise','content_sha256':node_hash(s.find(id='e'))},{'id':'s','type':'solution','for':'e','content_sha256':node_hash(s.find(id='s'))}]}
        self.assertEqual(check_content(s,r)['status'],'FAIL')

    def test_dependency_cycle(self):
        s=soup('<p id="a" data-object-type="definition">A</p><p id="b" data-object-type="definition">B</p>')
        r={'schema':'TextbookContent/v1','objects':[{'id':x,'type':'definition','depends_on':[y],'content_sha256':node_hash(s.find(id=x))} for x,y in [('a','b'),('b','a')]]}
        self.assertIn('dependency_cycle',str(check_content(s,r)['errors']))

    def test_missing_dependency(self):
        s=soup('<p id="a" data-object-type="definition">A</p>')
        r={'schema':'TextbookContent/v1','objects':[{'id':'a','type':'definition','depends_on':['missing'],'content_sha256':node_hash(s.p)}]}
        self.assertIn('missing_dependency',str(check_content(s,r)['errors']))

    def test_change_invalidates_transitive_users(self):
        old={'objects':[{'id':'d','value':1},{'id':'t','depends_on':['d']},{'id':'e','depends_on':['t']},{'id':'s','depends_on':['e']}]}
        new=copy.deepcopy(old); new['objects'][0]['value']=2
        self.assertEqual(affected_objects(old,new)['requires_review'],['d','e','s','t'])

    def test_removed_dependency_still_invalidates(self):
        old={'objects':[{'id':'d'},{'id':'e','depends_on':['d']}]}
        new={'objects':[{'id':'e','depends_on':[]}]}
        self.assertEqual(affected_objects(old,new)['requires_review'],['d','e'])

    def test_learner_physically_removes_answer(self):
        html='<p id="q">Question</p><details id="a" data-solution-for="q"><summary>答案</summary>ANSWER_SENTINEL</details><script>ANSWER_SENTINEL</script><!--ANSWER_SENTINEL--><style>p:before{content:"ANSWER_SENTINEL"}</style>'
        text,receipt=learner_projection(html)
        self.assertNotIn('ANSWER_SENTINEL',text)
        self.assertIn('Question',text)
        self.assertEqual(receipt['removed_solution_ids'],['a'])

    def test_learner_removes_dangling_answer_link(self):
        text,_=learner_projection('<a href="#s">答案</a><details id="s" data-solution-for="e">secret</details>')
        self.assertNotIn('href="#s"',text)

    def test_status_lattice(self):
        self.assertEqual(aggregate(['PASS','UNVERIFIED']),'UNVERIFIED')
        self.assertEqual(aggregate(['BLOCKED','PASS']),'BLOCKED')
        self.assertEqual(aggregate(['UNVERIFIED','FAIL']),'FAIL')
        self.assertEqual(aggregate(['PASS','NOT_APPLICABLE']),'PASS')

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x.json';p.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError):read_json(p)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'real';p.write_text('x');q=Path(t)/'link';q.symlink_to(p)
            with self.assertRaises(ValueError):ordinary(q)

    def test_two_rounds_do_not_invent_review(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); html=root/'a.html';html.write_text('<div>正文</div>',encoding='utf-8')
            registry=root/'content.json';registry.write_text(json.dumps({'schema':'TextbookContent/v1','objects':[]}))
            m={'schema':SCHEMA,'profile':'authoring-master','artifact':{'sha256':digest(html.read_bytes())},'inventory':{'math':[],'code':[],'output':[]},'task':{'proof_policy':'full','prerequisites':[]},'content':{'path':'content.json','sha256':digest(registry.read_bytes())}}
            path=root/'manifest.json';path.write_text(json.dumps(m))
            report=verify_release(html,path,digest(path.read_bytes()))
            self.assertEqual(report['mechanical_status'],'PASS')
            self.assertEqual(report['status'],'UNVERIFIED')
            self.assertTrue(report['rounds_identical'])

    def test_stale_review_is_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'review.json';p.write_text(json.dumps({'schema':'TextbookReview/v1','role':'content','status':'PASS','html_sha256':'old'}))
            self.assertEqual(review({'path':p.name,'sha256':digest(p.read_bytes())},root,'new','registry','content')['status'],'FAIL')

    def test_true_math_parsing_when_configured(self):
        katex=os.environ.get('KATEX_JS')
        if not katex:
            self.skipTest('KATEX_JS not provided: actual KaTeX not run')
        config={'path':katex,'sha256':digest(Path(katex).read_bytes()),'version':os.environ['KATEX_VERSION']}
        good=check_math(soup(r'<span class="math">\(x^2\)</span>'),config,Path('.'))
        bad=check_math(soup(r'<span class="math">\(\DefinitelyInvalidCommand{x}\)</span>'),config,Path('.'))
        self.assertEqual(good['status'],'PASS',good)
        self.assertEqual(bad['status'],'FAIL',bad)


class BrowserPredicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('TEXTBOOK_BROWSER_TESTS'):
            raise unittest.SkipTest('set TEXTBOOK_BROWSER_TESTS=1 for actual Chromium tests')
        from playwright.sync_api import sync_playwright
        cls.p=sync_playwright().start()
        cls.executable=os.environ.get('CHROMIUM') or shutil.which('chromium') or cls.p.chromium.executable_path
        cls.browser=cls.p.chromium.launch(executable_path=cls.executable,headless=True,args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.p.stop()

    def probe(self,html,families=None):
        results=[]
        for width in (1440,390):
            page=self.browser.new_page(viewport={'width':width,'height':844})
            page.set_content(html)
            results.append(page.evaluate(PROBE_JS,{'renderer':'native-mathml','families':families or []}))
            page.close()
        return results

    def test_clipped_table_fails(self):
        for r in self.probe('<div class="table-wrap" style="width:300px;overflow-x:clip"><table style="width:1200px"><tr><td>x</td></tr></table></div>'):
            self.assertTrue(r['errors'])

    def test_scrollable_table_passes(self):
        for r in self.probe('<div class="table-wrap" style="width:300px;overflow-x:auto"><table style="width:1200px"><tr><td>x</td></tr></table></div>'):
            self.assertEqual(r['errors'],[])

    def test_missing_font_fails(self):
        for r in self.probe('<p>x</p>',['DefinitelyMissingFont_482976']):
            self.assertIn('font_unavailable:DefinitelyMissingFont_482976',r['errors'])

    def test_missing_image_fails(self):
        for r in self.probe('<img src="missing-image.png">'):
            self.assertTrue(any('broken_image' in x for x in r['errors']))

    def test_full_file_navigation(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'a.html';path.write_text('<!doctype html><html><head></head><body><details data-solution-for="e"><summary>答案</summary><p>解答</p></details></body></html>')
            import subprocess
            script='import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from browser_checks import run_browser; print(json.dumps(run_browser(Path(sys.argv[2]),{"executable":sys.argv[3],"renderer":"native-mathml"},0)))'
            done=subprocess.run([sys.executable,'-c',script,str(Path(__file__).resolve().parents[1]/'scripts'),str(path),self.executable],capture_output=True,text=True,timeout=30)
            self.assertEqual(done.returncode,0,done.stderr)
            result=json.loads(done.stdout)
            if os.environ.get('TEXTBOOK_ALLOW_POLICY_SKIP') and 'ERR_BLOCKED_BY_ADMINISTRATOR' in result.get('reason',''):
                self.skipTest('local browser policy blocks file://; full offline test NOT RUN')
            self.assertEqual(result['status'],'PASS',result)

if __name__=='__main__':
    unittest.main()
