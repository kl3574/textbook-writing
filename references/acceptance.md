# 教材 HTML 交付形态与验收契约

本参考只处理可机械检验的交付边界。数学论断是否正确、来源是否真的支撑
论断、证明是否完整，仍由教材正文审查和独立教学评估负责。

## 1. 先声明一种交付形态

同一内容可以有多个 HTML 表示，但每个产物必须只声明一种 profile。

### `authoring-master`

面向继续修订和回放的权威主稿。

- 保留公式锚点、任务标识、来源定位和审查所需的局部属性。
- 记录全部 ID、公式节点和任务标识的顺序与数量。
- 修订必须保留既有稳定标识，除非另有经过审查的迁移表。
- 不能因为下游投影不需要某个锚点，就从主稿中删除它。

### `note-fragment`

面向 Zotero 等宿主应用的被动 HTML 片段。

- 只有一个顶层 `<div data-schema-version="9">`。
- 不含 `<html>`、`<head>`、`<body>`、`<script>`、`<style>`、`<link>`、
  `<iframe>`、`<object>`、`<embed>` 或独立运行时。
- 删除仅供本地工作流使用的隐藏锚点时，必须记录源主稿摘要、投影摘要、
  变换指标和 profile 专属计数。
- 该 profile 只约束笔记表示；它不授权创建、修改或删除 Zotero 条目、
  父项、附件、PDF 或下载文件。

### `standalone-publication`

面向浏览器离线阅读的完整文档。

- 有完整 HTML 文档结构；渲染所需 CSS、JavaScript 和字体全部内嵌。
- 参考文献链接可以指向外部来源，但页面加载不得自动请求外部运行时。
- 表格、代码、长 URL 和宽公式必须在组件内部可滚动；不得靠
  `body`/`html` 的 `overflow-x: hidden|clip` 掩盖内容。
- 桌面和窄屏浏览器均需验证文档级无横向溢出。

不同 profile 的字节数和公式节点数可以不同。只允许在同一 profile、同一
源摘要和同一变换契约内做精确比较，不能把跨 profile 的差异误报为数据丢失。

## 2. `TextbookAcceptanceManifest/v1`

验收前创建一个外部固定的构建清单。计数和摘要由构建者写入，验收器重新
计算；不要在构建脚本和验收脚本中分别维护两套常量。

```json
{
  "schema": "TextbookAcceptanceManifest/v1",
  "profile": "standalone-publication",
  "artifact": {
    "sha256": "64-lowercase-hex"
  },
  "counts": {
    "chapters": 1,
    "math_nodes": 2,
    "python_blocks": 1,
    "program_outputs": 1,
    "details": 1,
    "formula_anchors": 0,
    "task_ids": 0
  },
  "math": {
    "require_katex": true
  },
  "runtime": {
    "python_executable": "/absolute/path/to/python",
    "required_imports": []
  },
  "interaction_probe": {
    "query": "岭回归",
    "min_matches": 1,
    "max_matches": 1
  }
}
```

规则：

- 清单本身需要调用方提供的外部 SHA-256；自报摘要不能自证。
- `artifact.sha256` 必须等于待验收 HTML 原始字节摘要。
- `counts` 中出现的每个字段都必须精确相等；不需要的字段可以省略。
- `details` 只统计章节 `<article class="chapter">` 内的折叠答案；如需约束全书
  所有折叠块，另声明 `document_details`，避免目录说明等全局组件混入章节计数。
- `interaction_probe.query` 必须来自已接受的教材内容，并声明预期命中范围；
  禁止在通用技能中硬编码某一教材的词语。
- 变换后公式数量改变时，更新相应 profile 的清单并保留源清单，不能修改
  历史报告来假装旧产物具有新计数。

## 3. 分层数学验证

在 `authoring-master`、每次投影后以及 `standalone-publication` 组装后分别执行：

1. DOM 提取每个声明的数学节点；不从整份 HTML 用正则猜公式。
2. 拒绝数学节点中的制表符、未配对定界符、DOM 解码后仍残留的双重编码
   实体，以及被放进定界符的解释性 prose。HTML 序列化器把 `<`/`>` 写成
   `&lt;`/`&gt;` 属于正常的一层转义，验收器必须先按 DOM 解码，不能直接
   扫描原始序列化文本误报；TeX 对齐符使用的 `&amp;` 同理解码为 `&`。
3. 用与交付一致的 KaTeX 版本、`throwOnError: true` 和明确的
   `displayMode` 渲染全部节点。
4. 浏览器展示可以选择容错回退；验收通道不能用 `throwOnError: false`
   把解析失败算作成功。
5. 对源主稿额外核对公式锚点和任务 ID 的精确顺序；对投影核对变换指标。

KaTeX 通过只证明语法可渲染，不证明公式语义、维度或定理正确。

## 4. 可执行示例运行时

- 清单声明一个绝对 Python 可执行文件及课程真正需要的导入项。
- 先运行依赖预检，再用同一可执行文件运行所有示例并核对静态输出。
- 不允许因当前验证进程的 `sys.executable` 恰好可用就隐式继承它。
- 若环境不可复现，状态是 `UNVERIFIED_RUNTIME`，不能把代码块数量当成运行通过。
- 数值复算是教学与实现检查，不替代理论证明。

## 5. 响应式与浏览器验收

`standalone-publication` 至少检查一个桌面视口和一个窄屏视口；推荐
`1440×900` 与 `390×844`。

每个视口都核对：

- `document.documentElement.scrollWidth <= clientWidth + 1`；
- 所有宽表格都有最近的 `.table-wrap`，宽公式和代码有组件级滚动；
- `html` 和 `body` 没有用横向隐藏来掩盖溢出；
- 公式节点数、实际 `.katex` 节点数和静态验收计数一致；
- 字体加载完成且要求的 KaTeX 字体可用；
- 页面没有自动发起 HTTP(S) 运行时请求；
- 搜索、答案展开/收起等交互按清单中的 fixture-derived 预期工作。

浏览器验收脚本必须由与 Playwright 原生扩展 ABI 匹配的 Python 解释器启动，
并显式传入 Playwright 根目录和 Chromium 可执行文件。仅记录包目录而不确认
解释器版本，不能视为可重放环境。

## 6. 两类互不替代的闭环

### 教学闭环

由不参与写作的学习者完成做题、反例和代码复算。可以是独立 agent、人工
读者或隔离的评估会话。若用户明确禁用相应协作方式，保留这个边界并报告
`PEDAGOGICAL_REVIEW_NOT_RUN`；机械测试不能替代独立理解。

### 机械闭环

对同一未变化的产物连续运行两次完整验收，两份报告都为 PASS，且 HTML、
源清单和关键运行时摘要完全相同。第二轮不是读取第一轮结果，而是重新打开
全部输入并复算。

最终交付要分别报告两个闭环的状态；“连续两轮”不能只指其中一个却笼统写成
“全部验证完成”。

## 7. 配套脚本

- `scripts/check_textbook_contract.py`：profile、摘要、计数、公式结构、运行时、
  输出和交互 fixture 的确定性静态/可执行检查。
- `scripts/browser_acceptance.py`：在显式提供 Playwright 与 Chromium 时生成
  桌面/窄屏浏览器回执。

脚本是可复用底线，不是完整教材审稿人。项目可以增加更强的来源、证明、
可访问性和视觉检查，但不得删除上述边界后仍沿用 PASS 名称。
