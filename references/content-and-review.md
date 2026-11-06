# 内容对象、修改影响与独立评审

以下 DOM 注册、投影脚本与 `html_sha256` 回执仅适用于 HTML。TeX/PDF 保留相同的定理—证明—来源—题解关系与独立审查要求，以源码文件/标签和实际输入/PDF 摘要定位；依 [LaTeX 规范](latex-format.md) 另存检查证据。学习者 TeX/PDF 副本也必须实际移除测试答案，并检查源码附件与生成 PDF；不能仅隐藏答案或用 HTML 投影脚本处理 TeX。

## 内容注册表 TextbookContent/v1

JSON 根包含 `schema`、`objects`、`sources`。所有 `[data-object-type]` HTML 节点都须有唯一 `id`，并与 objects 一一对应。对象的 `content_sha256` 是 `BeautifulSoup(..., 'html.parser')` 解析后 `str(node)` 的 UTF-8 SHA-256；构建与验收使用同一固定解析器版本。哈希只绑定内容，不证明内容正确。

每个对象：`id`、`type`、`content_sha256`、`depends_on`。依赖有向无环；关系 `proof_id`、`proves`、`for` 不要随意复制成双向依赖造成循环。

定理/引理/命题另外包含：

- `variables`：每项 `symbol`、`domain`、`shape`；`quantifiers`、`conclusion`。
- `assumptions`：每项 `statement`、`role`；role 为 `necessary-proved`、`sufficient`、`technical`、`redundant` 或 `unknown`。声称必要时提供注册对象 `evidence_id`。
- `proof_id` 指向 type=proof 且 `proves` 回指的对象；`source_ids` 指向来源。

证明对象用 `proves` 绑定；习题对象 type=exercise，必须恰有一个 type=solution 的完整解答。解答对象用 `for` 和 HTML `data-solution-for` 双重绑定，HTML 为没有 open 属性的 details，含 summary 和非空解答正文。

外部来源包含 `id`、`url`、`locator`（页码/定理号/提交+文件+行）、`version`、`accessed`。自给推导可标 `kind=original-derivation` 并定位到本书证明，不伪装为外部文献。注册元数据正确不代表来源支持论断；这必须由内容审查确认。

## 修订影响

`python scripts/content_tools.py impact --before old.json --after new.json`

报告修改/删除对象、变化的来源及传递依赖对象；所有列出的对象需重审，而不是只重算文件哈希。旧版和新版关系取并集，防止删掉依赖边后逃避重审。整个 HTML 或注册表变化会让旧审查回执失效。

## 无答案学习者视图

`python scripts/content_tools.py learner --html book.html --out learner.html --receipt learner-receipt.json`

物理删除标记的 solution、data-solution-for、answer、eval-private 节点，以及脚本、模板、注释、隐藏节点、原 CSS 和活动属性；删除悬空答案链接。保留正文、例题及测试题。该投影是被动评测输入，不是重新验收的出版物。

删除记录和前后摘要可审计，但不能证明任意未标记自然语言中完全没有泄漏。独立评卷者仍要检查题目重用、正文直接给出测试答案、例题与留出题同构到无需理解等问题。不要把公开 eval 题目称作保密留出题。

## 评审回执 TextbookReview/v1

内容审稿与教学评估分别保存回执，字段：`schema`、`role`（content/pedagogy）、`html_sha256`、`registry_sha256`、`reviewer`、`independent`、`status`（PASS/FAIL）、`blocking_findings` 和 `evidence`。evidence 为含 path/sha256 的真实日志或评分文件列表。

内容审稿核对数学正确性、假设、证明跳步、来源是否支持关键结论、例题和题解正确性；学习者完成外部锚点题、迁移题、反例与复算，评卷者持独立答案。学习者不应看到标准答案或拟议修复。记录模型/人工、输入范围、题号、判分依据与失败项，不用“模拟小白”冒充独立学习者。

回执解析器验证绑定和字段，不验证签名身份或数学真伪。作者不能凭填写 `independent=true` 获得真实独立性；用户和审阅者必须能打开证据检查。缺少审查时保持 UNVERIFIED，机械通过不得顶替。
