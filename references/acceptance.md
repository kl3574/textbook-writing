# TextbookReleaseManifest/v2：统一发布验收

v3 HTML 的唯一发布入口是 `scripts/verify_release.py`。旧 TextbookAcceptanceManifest/v1 和旧 CLI 保留为局部迁移检查，不能替代新发布流程；原始 v2.2 检查器冻结在 legacy_contract.py，仅用于基线重放。

原生 `latex-pdf` 不使用这个 HTML 清单或验收器；模板、编译和 PDF 验收见 [LaTeX 规范](latex-format.md)。HTML 下游投影仍须独立执行本合同。

## 三个 HTML profile

- authoring-master：稳定对象身份、公式注册表、任务和来源定位；不要求独立浏览器运行。
- note-fragment：单一 `<div data-schema-version="9">`；被动元素/属性/URL 允许列表；不含脚本、样式、事件属性、活动 URL 或独立运行时。不是 Zotero 宿主的安全审计或写入授权。
- standalone-publication：完整 HTML、离线资源、参考链接可以外连但不能自动请求外部资源；桌面 1440×900 和窄屏 390×844 验证正文、展开解答和组件滚动。

渲染可选自包含 KaTeX 或预渲染原生 MathML；原生 MathML 仍保留 LaTeX 并做相同 KaTeX 语法验证，不需要分发字体。KaTeX 路径需要字体资源时，构建端应检查所需字体完整性和许可，不应把操作系统字体文件打包分发。

## 清单字段

根对象：schema、profile、artifact、inventory、task、content；按对象类型自动启用数学、代码与浏览器检查，不能仅以开关关闭必需检查。

```json
{
  "schema": "TextbookReleaseManifest/v2",
  "profile": "standalone-publication",
  "artifact": {"sha256": "HTML原始UTF-8字节的SHA-256"},
  "inventory": {"math": ["eq-1"], "code": ["code-1"], "output": ["out-1"]},
  "task": {"proof_policy": "full", "prerequisites": ["高中代数"]},
  "content": {"path": "content.json", "sha256": "注册表SHA-256"},
  "math": {"path": "/absolute/katex.js", "sha256": "运行时SHA-256", "version": "固定版本", "macros": {}},
  "runtime": {"python_executable": "/absolute/python", "required_imports": [], "timeout_seconds": 30},
  "browser": {"executable": "/absolute/chromium", "renderer": "native-mathml", "font_families": []},
  "reviews": {}
}
```

这是字段说明，不是可直接通过的清单：必须使用真实摘要。可执行完整案例由 examples/gls/build.py 生成。inventory 是编写阶段固定的预期 ID 顺序，与 DOM 独立重读比较；不要删除实际漏掉的 ID 来凑数。公式需有 `.math`，代码 `code.language-python` 和 `data-example-id`；展示输出 `pre.program-output` 的 `data-for` 指向对应 example-id。各自还有唯一 DOM id。

代码输出采用**规范格式后的 stdout 精确比较**，一例一输出；它不是通用浮点/图像等价判断。随机或容差实验应在代码中实现有理论依据的数值断言并输出稳定摘要，记录种子、容差和适用范围。不能为了通过测试任意放宽容差。

## 执行与状态

```bash
python scripts/verify_release.py --html book.html --manifest manifest.json \
  --expected-manifest-sha256 "$(cat manifest.sha256)" \
  --allow-execution --report release-receipt.json
```

清单的外部固定摘要和全部绑定文件在两轮分别重新读取；报告路径默认不得覆盖。两轮必须相同，不把旧报告当新结果。命令返回值：0=完整 PASS，1=失败，2=未验证或环境受阻。

`mechanical_status` 汇总结构、内容关系、公式语法、执行、浏览器；总 status 还包含内容审查与独立教学回执。任一实际缺陷为 FAIL；必需环境不可用为 BLOCKED；没有执行/证据为 UNVERIFIED；没有该类对象为 NOT_APPLICABLE。没有审查回执时，即便机械通过，总状态也不为 PASS。

对数学节点支持四种定界符和含 LaTeX annotation 的预渲染 MathML。KaTeX 固定版本与哈希，throwOnError=true、strict=error、trust=false；检查残留实体、制表符与未登记公式定界符。它不检查维度或数学真理，也不能保证发现所有没有任何数学标记的自然语言公式。

浏览器检查实际 .math 渲染、错误、图片、离线请求、初始/展开答案状态、组件滚动、裁切、字体声明与加载；不单独以 document.fonts.check(true) 当作字体存在。字体与渲染不等同于全字符字形覆盖认证；还应对高风险图形进行人工视觉核对。没有浏览器时不得用静态计数冒充。

## 安全与重放

`--allow-execution` 只适用于已审阅、可信代码。独立临时目录、受限环境变量、超时及 Python -I 减少偶然依赖，**不是操作系统安全沙箱**。不可信教材代码须在调用方提供的容器/受限环境执行。运行时路径显式给定，不默默继承；记录二进制摘要，不用目录名充当版本证据。

旧 CLI 为兼容而保留原执行方式；不要对不可信输入使用它。发布不自动上传附件、改写用户库、改动权限或联网下载资源。
