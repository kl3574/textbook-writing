#!/usr/bin/env python3
"""Build one GLS lesson and compare frozen-v2.2 vs v3 output-binding checks.
The compared defective artifact is deliberately mutated, not an LLM generation.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import html as h
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from bs4 import BeautifulSoup
from release_contract import SCHEMA, check_execution, digest, learner_projection, node_hash
from verify_release import verify_release


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def fixture(swapped=False):
    a,b=('2.000000','1.400000') if swapped else ('1.400000','2.000000')
    return f'''<!doctype html><html><head><meta charset="utf-8"></head><body><article class="chapter" id="gls">
<pre><code id="code-gls" class="language-python" data-example-id="gls">y=(1,3); v=(1,4)
print(f"{{sum(a/b for a,b in zip(y,v))/sum(1/b for b in v):.6f}}")</code></pre><pre id="out-gls" class="program-output" data-for="gls">{a}</pre>
<pre><code id="code-mean" class="language-python" data-example-id="mean">print(f"{{(1+3)/2:.6f}}")</code></pre><pre id="out-mean" class="program-output" data-for="mean">{b}</pre></article></body></html>'''


def regression(out):
    baseline=ROOT/'scripts/legacy_contract.py'
    raw=baseline.read_bytes()
    import hashlib
    blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if blob!='bbd4cf8a223b98887def13dd1f21ab9781ee8658':
        raise ValueError('frozen baseline changed')
    spec=importlib.util.spec_from_file_location('frozen_v220',baseline)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rows=[]
    for name,swapped in [('correct',False),('swapped-output',True)]:
        text=fixture(swapped); path=out/(name+'.html');path.write_text(text,encoding='utf-8')
        m={'schema':'TextbookAcceptanceManifest/v1','profile':'standalone-publication','artifact':{'sha256':digest(text)},'counts':{'chapters':1,'python_blocks':2,'program_outputs':2},'math':{'require_katex':False},'runtime':{'python_executable':sys.executable,'required_imports':[]}}
        mp=out/(name+'-v1-manifest.json');write_json(mp,m)
        before=old.validate(path,mp,digest(mp.read_bytes()),None)
        after=check_execution(BeautifulSoup(text,'html.parser'),m['runtime'],True)
        write_json(out/(name+'-v2.2-receipt.json'),before)
        write_json(out/(name+'-v3-receipt.json'),after)
        rows.append({'case':name,'artifact_sha256':digest(text),'v2.2_component':before['status'],'v2.2_execution':before['execution']['status'],'v3_execution':after['status'],'v3_reasons':[r.get('reason') for r in after['results']]})
    result={'scope':'DETERMINISTIC_DEFECT_REGRESSION_NOT_MODEL_AB','baseline_commit':'fc1a5c246409b1740145418034fb7eedbcf7ef66','baseline_blob':blob,'rows':rows,'model_ab_status':'NOT_RUN','human_learning_status':'NOT_RUN','tokens':None}
    assert rows[0]['v2.2_execution']==rows[0]['v3_execution']=='PASS'
    assert rows[1]['v2.2_execution']=='PASS' and rows[1]['v3_execution']=='FAIL'
    write_json(out/'comparison.json',result)
    return result


def build(out):
    katex=os.environ.get('KATEX_JS')
    math_ids=[]
    def math(key,tex,plain):
        math_ids.append(key)
        if katex:
            js="const k=require(process.argv[1]);process.stdout.write(k.renderToString(process.argv[2],{output:'mathml',displayMode:true,throwOnError:true,strict:'error',trust:false}));"
            done=subprocess.run(['node','-e',js,katex,tex],capture_output=True,text=True,check=True)
            rendered=done.stdout
        else:
            rendered='<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><semantics><mtext>'+h.escape(plain)+'</mtext><annotation encoding="application/x-tex">'+h.escape(tex)+'</annotation></semantics></math>'
        return '<div class="math" id="'+key+'" data-display="true" data-tex="'+h.escape(tex,quote=True)+'">'+rendered+'</div>'
    v=[Fraction(1),Fraction(4)];y=[Fraction(1),Fraction(3)];S=sum(1/x for x in v)
    estimate=sum(a/b for a,b in zip(y,v))/S
    variance=1/S;mean=sum(y)/2;meanvar=sum(v)/4
    assert (estimate,variance,mean,meanvar)==(Fraction(7,5),Fraction(4,5),Fraction(2),Fraction(5,4))
    code=fixture().split('<article class="chapter" id="gls">')[1].split('</article>')[0]
    content='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>两次精度不同的测量：GLS 教材案例</title><style>
body{font-family:system-ui,sans-serif;line-height:1.8;max-width:880px;margin:32px auto;padding:0 20px}h1,h2{line-height:1.35}section{margin:2em 0}.math,pre,.table-wrap{max-width:100%;overflow-x:auto}pre{padding:16px;background:#f4f5f6}details{padding:12px;border:1px solid #aaa;margin:16px 0}summary{cursor:pointer}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #bbb;text-align:left}a{overflow-wrap:anywhere}.note{padding:16px;border-left:4px solid #555}math{font-size:1.12em}
</style></head><body><h1>两次精度不同的测量，应该如何平均？</h1><p>对象：掌握高中代数、期望线性性及方差定义的自学者。本章完整证明线性无偏类中的最优性，不宣称对所有有偏或非线性估计器最优。主线：噪声不同→设计权重→证明→手算与复算→改变条件。</p><article class="chapter" id="chapter-gls"><section><h2>1. 从问题到权重</h2><p>目的地：解释为什么精度高的测量应有更大权重；算出加权结果；分清平均风险与一次误差。把两把精度不同的尺子的读数直接平均，会把可靠程度当成一样。</p><div id="def-model" data-object-type="definition"><h3>模型与符号</h3><p>固定未知参数 θ 是实数；下标 i 取 1、2。观测 y 与误差 ε 是二维实向量。噪声均值为零、互不相关；两个已知方差 σ₁²、σ₂² 严格为正。权重 a 与最优权重 a* 为二维实向量；S 为正实数。</p>'''
    content+=math('eq-model',r'y_i=\theta+\varepsilon_i,\quad \mathrm E[\varepsilon_i]=0,\quad \operatorname{Var}(\varepsilon_i)=\sigma_i^2>0,\quad \operatorname{Cov}(\varepsilon_1,\varepsilon_2)=0','yᵢ=θ+εᵢ，E[εᵢ]=0，Var(εᵢ)=σᵢ²>0，Cov(ε₁,ε₂)=0')
    content+='</div><div id="thm-blue" data-object-type="theorem"><h3>定理：最优线性无偏权重</h3><p>对上述所有 θ∈ℝ、σ₁²&gt;0、σ₂²&gt;0，以及满足 a₁+a₂=1 的所有 a∈ℝ²，估计量 Tₐ=a₁y₁+a₂y₂ 无偏。其方差的唯一最小值和达到该值的权重如下。</p>'
    content+=math('eq-blue',r'S=\sum_{i=1}^{2}\sigma_i^{-2},\qquad a_i^*=\frac{\sigma_i^{-2}}{S},\qquad \widehat\theta=\sum_{i=1}^{2}a_i^*y_i,\qquad \operatorname{Var}(\widehat\theta)=\frac1S','S=∑ᵢ σᵢ⁻²，aᵢ*=σᵢ⁻²/S，θ̂=∑ᵢ aᵢ*yᵢ，Var(θ̂)=1/S')
    content+='</div><div id="proof-blue" data-object-type="proof"><h3>完整证明</h3><p>第一步：由期望线性性，E[Tₐ]=(a₁+a₂)θ。权重和为一时，对每个 θ 都无偏。反之，要求对所有 θ 无偏，取 θ=1 就得到权重和为一。</p><p>第二步：把中心化误差 a₁ε₁+a₂ε₂ 平方并取期望。交叉项为 2a₁a₂Cov(ε₁,ε₂)=0，因此方差为 a₁²σ₁²+a₂²σ₂²。</p><p>第三步：S&gt;0；aᵢ*=1/(Sσᵢ²) 的和为一。展开以下平方和，使用 ∑ᵢaᵢ=1：</p>'
    content+=math('eq-proof',r'\sum_{i=1}^{2}\sigma_i^2(a_i-a_i^*)^2=\sum_{i=1}^{2}\sigma_i^2a_i^2-\frac{2}{S}\sum_{i=1}^{2}a_i+\frac{1}{S^2}\sum_{i=1}^{2}\sigma_i^{-2}=\operatorname{Var}(T_a)-\frac1S\geq0','∑ᵢσᵢ²(aᵢ−aᵢ*)²=∑ᵢσᵢ²aᵢ²−(2/S)∑ᵢaᵢ+(1/S²)∑ᵢσᵢ⁻²=Var(Tₐ)−1/S≥0')
    content+='<p>第四步：每个 σᵢ²&gt;0，平方和非负，并且等于零当且仅当每个 aᵢ=aᵢ*。因此最小方差为 1/S，且最优权重唯一。证明完成。</p></div><p>直觉：方差的倒数是本例中的相对精度；权重等于“自身精度/总精度”。不要求高斯分布也能得到这一线性无偏最优性。这里没有证明对全部估计方法的全局最优性。</p><h3>假设与边界</h3><p>正方差确保权重公式有定义和唯一性；互不相关用于消去交叉项。不能把这些条件的作用混为一谈。若观测相关，应保留交叉项；本章对角加权公式不能直接照搬。</p><p>反例：“普通平均永远是最优线性无偏估计”不成立，下一节的方差对比直接否定它。小结：先限定比较方法的集合，再讨论最优。</p></section><section><h2>2. 逐步手算、代码与迁移</h2><div id="example-gls" data-object-type="example"><p>目的地：测量为 1 与 3，方差为 1 与 4；第二次测量更不稳定。</p>'
    content+=math('eq-numbers',r'S=1+\frac14=\frac54,\quad a_1^*=\frac45,\quad a_2^*=\frac15,\quad \widehat\theta=\frac45\cdot1+\frac15\cdot3=\frac75=1.4','S=1+1/4=5/4，a₁*=4/5，a₂*=1/5，θ̂=(4/5)×1+(1/5)×3=7/5=1.4')
    content+=math('eq-variance',r'\operatorname{Var}(\widehat\theta)=\frac45=0.8,\qquad \overline y=2,\qquad \operatorname{Var}(\overline y)=\frac{1+4}{4}=1.25','Var(θ̂)=4/5=0.8；普通平均=2，Var(普通平均)=(1+4)/4=1.25')
    content+=f'<div class="table-wrap"><table><tr><th>方法</th><th>本次计算结果</th><th>重复测量下的方差</th></tr><tr><td>逆方差加权</td><td>{float(estimate):.6f}</td><td>{float(variance):.6f}</td></tr><tr><td>普通平均</td><td>{float(mean):.6f}</td><td>{float(meanvar):.6f}</td></tr></table></div><p>本表由 Fraction 精确计算结果生成，而不是另写一份常量。下面两段代码分别绑定各自输出。</p>'+code+'</div><p class="note">方差更小描述重复实验下的表现；由于 θ 未知，不能仅据此断言这一次的 1.4 必定比 2 更接近真值。</p><div id="exercise-transfer" data-object-type="exercise"><h3>迁移题</h3><p>把观测改为 2 与 4、方差改为 1 与 9。求逆方差权重、估计值与方差。提示：先求总精度，再归一化。</p></div><details id="solution-transfer" data-object-type="solution" data-solution-for="exercise-transfer"><summary>展开完整解答</summary><p>总精度为 1+1/9=10/9。权重为 9/10 与 1/10。估计值为 (9/10)×2+(1/10)×4=22/10=2.2。方差为 1/(10/9)=9/10=0.9。权重和为一，且精度较高的第一条数据权重较大。</p></details><h3>边界题与节小结</h3><p>当两个方差相同时，逆方差权重都为 1/2，此时两种方法相同；这不是前面反例的矛盾，而是适用条件不同。遇到相关误差时要重新推导方差。小结：公式、数值、代码输出和习题答案必须与各自条件一一对应。</p></section><h2>章节总结与符号索引</h2><p>先定义线性无偏类，再由非负平方证明最优性；使用已知方差归一化精度。<a href="#def-model">θ、y、ε、σ²</a>；<a href="#thm-blue">a、a*、S、Tₐ</a>。术语：本例是互不相关噪声下常数均值模型的 GLS。</p><h2>Notes and References</h2><p>本章证明为自给推导，见<a href="#proof-blue">完整证明</a>。版本改造的工程依据和对照协议见仓库 references/evaluation.md；不要把它们当作统计定理的来源。</p><h2>勘误</h2><p>此页是版本改造的演示案例。机械回执、独立审稿与学习者状态保存在独立报告；没有独立评审时不宣称本教材已全面验证。</p></article></body></html>'
    path=out/'reader.html';path.write_text(content,encoding='utf-8')
    soup=BeautifulSoup(content,'html.parser')
    specs=[{'id':'def-model','type':'definition','depends_on':[]},{'id':'thm-blue','type':'theorem','depends_on':['def-model'],'variables':[{'symbol':'theta','domain':'R','shape':'scalar'},{'symbol':'a,y,epsilon','domain':'R^2','shape':'2-vector'},{'symbol':'sigma_i^2','domain':'(0,infinity)','shape':'scalar'}],'assumptions':[{'statement':'zero mean, positive known variances, zero covariance','role':'sufficient'}],'quantifiers':'for every theta and every linear unbiased weight vector','conclusion':'a_i*=sigma_i^-2/S uniquely minimizes variance; minimum=1/S','proof_id':'proof-blue','source_ids':['derivation']},{'id':'proof-blue','type':'proof','proves':'thm-blue','depends_on':['def-model','thm-blue']},{'id':'example-gls','type':'example','depends_on':['thm-blue']},{'id':'exercise-transfer','type':'exercise','depends_on':['thm-blue','example-gls']},{'id':'solution-transfer','type':'solution','for':'exercise-transfer','depends_on':['exercise-transfer','thm-blue']}]
    for obj in specs:obj['content_sha256']=node_hash(soup.find(id=obj['id']))
    registry={'schema':'TextbookContent/v1','objects':specs,'sources':[{'id':'derivation','kind':'original-derivation','locator':'reader.html#proof-blue'}]}
    write_json(out/'content.json',registry)
    manifest={'schema':SCHEMA,'profile':'standalone-publication','artifact':{'sha256':digest(content)},'inventory':{'math':math_ids,'code':['code-gls','code-mean'],'output':['out-gls','out-mean']},'task':{'proof_policy':'full','prerequisites':['high-school algebra','linearity of expectation','definition of variance']},'content':{'path':'content.json','sha256':digest((out/'content.json').read_bytes())},'runtime':{'python_executable':str(Path(sys.executable).resolve()),'required_imports':[]},'reviews':{}}
    if katex:manifest['math']={'path':str(Path(katex).resolve()),'sha256':digest(Path(katex).read_bytes()),'version':os.environ['KATEX_VERSION']}
    chromium=os.environ.get('CHROMIUM')
    if chromium:manifest['browser']={'executable':chromium,'renderer':'native-mathml','font_families':[]}
    mp=out/'manifest.json';write_json(mp,manifest)
    (out/'manifest.sha256').write_text(digest(mp.read_bytes())+'\n')
    learner,receipt=learner_projection(content)
    (out/'learner.html').write_text(learner,encoding='utf-8');write_json(out/'learner-receipt.json',receipt)
    release=verify_release(path,mp,digest(mp.read_bytes()),True)
    write_json(out/'release-receipt.json',release)
    if os.environ.get('TEXTBOOK_REQUIRE_FULL_MECHANICAL')=='1' and release['mechanical_status']!='PASS':
        raise AssertionError(json.dumps(release,ensure_ascii=False))
    return release


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    result=regression(a.out);release=build(a.out)
    print(json.dumps({'comparison':result,'mechanical_status':release['mechanical_status'],'overall_status':release['status']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
