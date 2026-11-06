# 模板选择与 LaTeX/PDF 规范

本文件约束 `format=latex`、`profile=latex-pdf` 的教材。六项写作标准仍适用；
TeX 编译成功不证明教材数学正确或教学闭环完成。HTML 的 DOM、KaTeX、
移动端和折叠答案门不套用到 PDF。

## 先选模板，再写内容

按以下顺序确定模板：

1. 本次用户明确提供的模板及构建说明。
2. 现有教材项目已经固定的模板、版本和编译命令。
3. 随技能的 `assets/latex-template/` 默认快照，源自
   `/home/lkx/textbook_template`，文件摘要在 `template-source.json`。

不得通过任意当前目录、缓存或另一门课的工程猜测模板。用户提供的是 HTML
模板时，走 HTML 分支；不要把它喂给 TeX 初始化器或强行转成默认 TeX 版式。

用户模板先检查入口、文档类、目录、宏/环境定义、字体、计数器、引用规则、
参考文献后端、构建命令和实际依赖，再写一个代表性小样实测。模板目录只读，
复制到新的工作目录；修订已有稿件则在原项目边界内修改，不覆盖其模板。

用户模板不必叫 `main.tex`，也不必有 `preamble/` 或采用 `article`。保留其
真实约定；这里后续的具体目录、颜色和环境表仅描述**默认模板**。如模板
缺少教学所需的提示/解答环境，可先用其已有章节/列表结构承载内容；确需
扩展时按该模板风格最小增补并记录，不能偷偷换成默认模板。

模板附带的程序、构建脚本和安装器不因“提供模板”而自动执行。只有明确
需要且在任务授权范围内的构建命令才运行；默认关闭 TeX shell escape。
外部图片、字体、宏包或数据缺失时据实报告，不用占位图或系统字体静默顶替。

## 初始化新项目

从技能根目录运行，或把脚本路径替换为实际安装位置：

```bash
# 默认模板的中文写作骨架；建议 XeLaTeX。
python3 scripts/init_latex_project.py --output /absolute/new-chapter \
  --language zh --title '估计理论基础' --course-name '统计学习'

# 默认模板的英文写作骨架；建议 pdfLaTeX。
python3 scripts/init_latex_project.py --output /absolute/new-lecture --language en

# 用户模板：按原字节复制，不改字体、宏、内容或文档类。
python3 scripts/init_latex_project.py --output /absolute/new-book \
  --template /absolute/user-template --main book.tex --engine xelatex
```

`--output` 必须是不存在的新目录；已有目录即使为空也拒绝覆盖。
自定义入口必须位于模板内。未指定入口时优先 `main.tex`，否则只有根目录
唯一的文档入口可以自动选择；多个入口不能猜。初始化器不解包不可信归档、
不跟随符号链接、不执行模板命令；压缩模板先在独立目录安全解包并检查。

`--language`、`--title` 和 `--course-name` 只配置内置模板。自定义模板的
语言、元信息和布局由它自己定义，不能用这几个通用参数覆盖。引擎可以通过
`--engine` 指定；自定义模板未声明引擎时按其构建文档核实，不默认猜 pdfLaTeX。

输出的 `textbook-template.receipt.json` 记录模板身份、入口、引擎及初始文件
摘要，是**创建回执**，不是教材验收清单。后续写作改变源码后，最终验收须
重新固定真实输入与产物摘要。初始化骨架中的“待撰写”不算教材内容。

字面引用的 `.out`、`.log` 等文件可能是真实输入，不能仅按扩展名当缓存删除；
初始化器为此保留可识别的字面输入。它不执行 TeX 宏展开，也不是完整依赖
分析器：动态生成的路径或特殊构建规则仍须用真实构建核对闭包。

## 默认模板的目录与样式

参考快照完整保留了 17 个原始文件；初始化器的默认输出只取实际需要的
前导与写作骨架，不把归并排序、Dijkstra 等示范课内容混入新教材。

```text
main.tex                 入口、课程元信息、目标框、目录、章节 input
preamble/packages.tex    编码/字体、排版、数学、盒子、算法、绘图、引用包
preamble/style.tex       调色板、标题、页眉页脚、课程标题块
preamble/macros.tex      数学宏与行内代码宏
preamble/boxes.tex       定义/定理/例子/习题及非编号提示框
preamble/code.tex        listings 与算法的显示样式
sections/                按节拆分正文
figures/                 TikZ、pgfplots 或实际引用的图片
code/                    lstinputlisting 展示的实际代码
```

默认入口为 `article[11pt,a4paper]`。保持
`packages → style → macros → boxes → code` 的前导载入顺序；不要独立载入
后面文件却漏掉它使用的颜色或宏包。色彩在 `style.tex` 集中定义：

| 名称 | 值/用途 |
|---|---|
| `accent` | `1F5FBF`，蓝色标题/定理 |
| `accent2` | `C2410C`，橙色例子/链接 |
| `accent3` | `15803D`，绿色定义/引用 |
| `codebg` | `F6F8FA`，代码背景 |

版式为约 1 英寸页边距、1.1 倍行距、无衬线标题、breakable 浅色块和左色条。
页眉显示课程与讲次；页脚显示作者/学期、课程代码以及当前页/总页数。
默认元信息为 `coursecode`、`coursename`、`lecnumber`、`lectitle`、`lecturer`、
`semester`。按书的实际身份改写，不能把教授名、课程码或示例年份当成事实。
目录、`LastPage` 等引用必须在最终构建收敛后验证。

原始英文模板注明 pdfLaTeX，使用 T1/inputenc/Latin Modern 和 Helvetica 标题。
内置中文派生项目使用 XeLaTeX、ctex/Fandol 预置，保持同一目录、配色与盒子
体系；不能把含中文的稿件直接按英文引擎和字体链交付。用户模板优先使用其
自己的中文方案，不额外叠加重复的字体包。

原快照的 `pgfplots compat=newest` 是移动目标。内置派生项目固定为 `1.18`，
并记录实际 TeX Live/PGFPlots 版本；自定义模板则遵守其已有兼容约定。
原 `headheight=15pt` 也不是所有内容的通用正确值：用实际页眉长度和字体
构建后检查，按日志修正派生项目的高度或缩短页眉，不掩盖版面警告。

## 默认环境、计数器与引用

默认模板的 `theorem` 等是 tcolorbox 环境，使用两个必选参数：

```tex
\begin{definition}{估计量}{estimator}
定义正文。
\end{definition}
参见定义~\ref{def:estimator}。

\begin{theorem}{定理标题}{main-result}
准确列出全部假设与结论。
\end{theorem}
\begin{proof}
按编号步骤给出证明，结尾由 amsthm 放置 QED。
\end{proof}
参见定理~\ref{thm:main-result}。
```

| 环境 | 标签前缀 | 编号 |
|---|---|---|
| `theorem` | `thm:` | 按 section 重置 |
| `lemma` | `lem:` | 与 theorem 共享 |
| `definition` | `def:` | 与 theorem 共享 |
| `example` | `ex:` | 与 theorem 共享 |
| `exercise` | `exc:` | 独立计数，按 section 重置 |

不要另造与模板冲突的 `\newtheorem` 或再次给相同内容编号。
`keyidea`、`notebox`、`warnbox` 是带可选标题的非编号框；`objectives` 是目标框。
模板没有预定义 `proposition`、`hint`、`solution`：不得直接使用不存在的环境。
可用独立提示/解答节与 `\label`/`\ref`，或在派生 `boxes.tex` 中按既有
`thmbase` 风格增加确实需要的环境。自定义模板的环境参数及前缀以实际定义为准。

保留既有数学宏的语义：`\R`、`\N`、`\Z`、`\E`、`\Pr`、`\norm{}`、
`\abs{}`、`\inner{}{}`、`\argmin`、`\argmax`。默认 `\O` 在数学模式是
大 O、文本模式保留原字母；不要再把它定义成无条件数学宏。

## 教学结构、图与代码

开篇先给受众、先修知识、证明/提示程度和学习目标，再给目录与动机。
正文沿“目的地 → 动机 → 定义/定理 → 证明 → 直觉/假设检查 → 算例/反例 →
习题”的节奏写。默认模板的七个演示 section 只是语法示范，不是所有科目
必须照搬的七章内容，也不替代完整证明与独立教学评估。

算法使用 `algorithm` + `algpseudocode`，保留 `\Require`/`\Ensure`、编号行和
独立标签。代码在 `code/` 维护，以带 `language`、`caption`、`label` 的
`\lstinputlisting` 引入；同一代码不在正文与附件各维护一份不同版本。
代码通过排版不表示通过运行，须另给同一源码的驱动、输入和期望输出。

图表有标题、标签和正文引用；TikZ/PGFPlots 源码放 `figures/` 再 `\input`。
PDF/PNG 等真实图源也随闭包交付。表格沿用 `booktabs`，宽代码换行，宽表/
公式按实际纸宽排版；不要用 HTML 的横向滚动或隐藏溢出来处理印刷版。
保留基础题提示、挑战题标记、正文↔习题↔解答引用、章末总结、Notes and
References 和符号索引；PDF 解答用章节或附录，不要求 HTML 折叠交互。

## 编译与验收

先做小样：至少覆盖中文/英文标题、目标框、定义/定理/证明、交叉引用、
代码、算法、图表和习题/解答，再扩展全章。用户模板有自己的构建脚本时先
阅读和核实；不是所有模板都可直接用下面的默认命令。

```bash
# 在派生项目根目录。英文预置使用 -pdf，中文预置使用 -xelatex。
latexmk -xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  -no-shell-escape -outdir=build main.tex

# 查阅 PDF 元信息、实际字体和可提取文字；这些检查不替代看版面。
pdfinfo build/main.pdf
pdffonts build/main.pdf
pdftotext -layout build/main.pdf build/main.txt
pdftoppm -f 1 -singlefile -scale-to 1500 -png build/main.pdf build/page-1
```

编译必须保存精确命令、工作目录、引擎绝对路径与版本、stdout/stderr、最终
`.log`/`.fls` 和 PDF。记录本地输入 TeX/图片/代码/bib/cls/sty 的摘要，以及
外部宏包、字体、参考文献程序等环境版本；不得因“本机恰好有”而漏报依赖。
初始化创建回执不是这份最终清单。

机械检查至少包括：

- 编译退出成功，最终日志无错误、未定义命令、未解析引用/引用文献、重复
  标签和缺字；引用需要的多次 pass 必须真的完成，不用 `??` 占位交付。
- 对 overfull、页眉高度、浮动体等警告逐项处理或明确限定并人工检查；
  不能将成功退出码等同于无排版问题。
- 阅读 PDF 首页、代表性正文/证明、图表/长代码、习题与解答页，检查字体、
  断行、盒子跨页、页眉页脚、目录和链接；中文可提取文字与字体嵌入也核对。
- 引用的源码/图片/数据存在且包含在交付闭包中；可计算案例按声明的解释器
  或编译器实际执行，结果与教材一致。
- 冻结最终源码输入和 PDF，从磁盘独立读取并跑两轮适用检查，分别保存
  结果；latexmk 为引用收敛执行的多次编译不算多轮验收。

`verify_release.py` 与旧 `check_textbook_contract.py` 都只接受 HTML；不得将 TeX 传给它们。当前没有通用 TeX 语义审稿器。
TeX 分支依上述编译、PDF、来源及代码检查形成 `latex-acceptance.json`，如实
逐项写 PASS/FAIL/NOT_RUN，不把人工未看的页面或未执行的代码自动标成通过。
不同构建的 PDF 可能因时间/元数据不同而字节不同：每份实际交付 PDF 记录
自己的摘要；若声称字节可复现，另固定构建日期/环境并实际验证，不把差异
抹掉。对同一冻结 PDF 的两轮验收则必须核对同一摘要。

缺引擎/字体/依赖、未构建、未看版面或教学评估未运行时，分别明确报告
`BLOCKED_DEPENDENCY`、`PDF_BUILD_NOT_RUN`、`VISUAL_REVIEW_NOT_RUN`、
`PEDAGOGICAL_REVIEW_NOT_RUN`，不能合并成“全部验证通过”。
