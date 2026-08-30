# textbook-writing

数学/统计教材 HTML 讲义的写作技能：六项正交标准 + 独立教学评估 + 可重放机械验收。v2.2.0（2026-08-30）新增三种 HTML 交付形态、分层公式门、哈希绑定清单、显式代码运行时、响应式浏览器门和连续双轮验收。

适用于估计理论、优化算法等数学/统计课程讲义（HTML）的创建与修订。

## 定位

面向零基础自学读者，锚定"富教学工程"路线（Axler / Strang / Stein-Shakarchi 端），而非极简风格（Rudin 端）——紧凑留白在课堂场景是优点，在自学场景是硬伤。

## 六项正交标准

每条标准对应一个独立职能，检查清单互不重叠：

| 标准 | 职能 | 要点 |
|---|---|---|
| 正确性 | 数学上对 | 证明无跳步、证明分级（压缩处显式标注"证明略"）、变量就地标注形状、引用注明、章末 Notes and References |
| 符号系统 | 记号统一 | 符号约定表、学界主流锚定、系列一致、公式 LaTeX 化细则（禁裸 "="/裸数值比较/DOM 解码后残留的双重编码实体，豁免文献元数据与交叉引用）、书末符号索引 |
| 结构 | 知识组织 | 系列大纲先行（首次出现/回访/延迟困难）、节级模板（目的地框→动机段→定理→证明→直觉解释→假设检查→算例→边界情形→习题）、五要素、章末要点总结 |
| 教学法 | 学得懂 | 类比/算例/反例、反例制度化四件套（假设检查段、证明或给反例句式、概念缺口预埋、复用清单）、习题两级体系（提示/星号/扩展/双向引用/出处标注） |
| 验证 | 检验过 | 特例代码实测、显式解释器与依赖预检、独立教学评估、分层公式门、哈希绑定清单 |
| 交付 | 拿得到 | authoring-master / note-fragment / standalone-publication 三种形态、解答折叠、离线 KaTeX、响应式双视口、连续双轮验收 |

## 交付流程

1. 声明交付 profile，建立外部哈希绑定的验收清单与执行环境
2. 按六项标准起草、自审，并在权威主稿层运行严格公式门
3. 由不参与写作的学习者完成做题、反例和代码复算；无独立通道时明确报告未运行
4. 对每次 note-fragment 投影重新验证源摘要、变换指标、公式与禁止元素
5. 对 standalone-publication 执行严格 KaTeX、代码输出、字体、链接、交互和桌面/窄屏检查
6. 在所有输入未变化时从磁盘重新运行两次完整机械验收
7. 分别报告教学闭环与机械闭环状态后交付

本循环定位为**缺陷发现器**而非质量认证：通过只说明本轮未发现对应问题。有效反例的判定由主会话负责；独立学习者只出报告与修改建议，不改权威文件。

机械验收细则见 [`references/acceptance.md`](references/acceptance.md)。仓库提供：

- `scripts/check_textbook_contract.py`：profile、摘要、计数、公式结构、运行时、输出和交互 fixture 检查；
- `scripts/browser_acceptance.py`：显式 Playwright/Chromium 环境下的桌面与窄屏回执；
- `tests/test_textbook_contract.py`：旧失败形态、负例和不同输入的前向用例。

## 变更记录

- **v2.2.0**（2026-08-30）：根据 44 篇估计理论教材与 Zotero 投影的哈希回放复盘，新增 `TextbookArtifactProfile/v1`、`TextbookAcceptanceManifest/v1`、三层公式验证、显式 Python 运行时预检、组件级宽内容容器、双视口浏览器门和 fixture-derived 交互探针；把独立教学评估与连续双轮机械验收分开报告。
- **v2.1.2**（2026-08-25）：补充 KaTeX 字体文件与 `@font-face` 数量一致性，以及浏览器级字体检查。
- **v2.1**（2026-08-25）：新增 HTML 渲染与作图规范——公式 LaTeX 化细则（禁止裸 "="、裸数值比较、数学内 HTML 实体；豁免文献元数据与交叉引用编号；SVG 文字用 Unicode 数学字符）、作图格式（figure+figcaption、SVG 响应式/无障碍/暗色主题适配、图注 LaTeX）、KaTeX 完全自包含（woff2 data URI 内嵌、禁 CDN）、构建链路备忘（heredoc+python raw 防反斜杠翻倍）、交付前渲染验证三件套（全量 KaTeX 渲染 0 失败、jsdom 端到端、裸数学扫描）。实战来源：Todros & Tabrikian 2010 Part I 文献讲义重写（957+ 数学片段 0 失败）。
- **v2.0**（2026-08-19）：六部主流教材（Linear Algebra Done Right、Rudin 数学分析原理、Stein-Shakarchi 分析四卷、Strang 线性代数、Convex Optimization、Numerical Optimization）调研后全面升级——节级模板、系列动机叙事线、反例制度化四件套、习题两级体系、证明分级、书末符号索引、章末 Notes、开篇声明、算例代码交付、勘误维护。
- **v1.0**（2026-08-19）：初版——六项正交职能整合 + 子 agent 教学迭代循环。

## 安装

- Claude 桌面应用：设置 → Skills → 将 `SKILL.md` 放入 skills 目录（或通过 Save skill 安装）
- Codex：可通过 `skill-installer` 从 `kl3574/textbook-writing` 的不可变版本标签安装；安装后运行仓库单元测试和一次真实 HTML 验收
- 其他支持技能的环境：克隆本仓库后配置技能路径指向 `SKILL.md`

## 使用

写作或修订教材章节时引用本技能（如 `/textbook-writing`），Claude 将按六项标准写作并执行交付前验证循环。
