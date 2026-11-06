# textbook-writing v3.1.0

面向自学者的数学、统计、优化与算法教材技能。保留完整证明、统一符号、例题反例、练习全解与离线交付；新增对象绑定、统一发布检查、修订影响分析和可复现版本对照。

## LaTeX/PDF 与模板

新教材默认 TeX 源码 + PDF；用户提供模板优先，其次沿用现有稿件模板，无指定时使用 `assets/latex-template/` 的固定快照。已有 HTML 工程继续使用 v3 的对象绑定与统一验收，不自动迁移格式。

```bash
python scripts/init_latex_project.py --output /absolute/new-chapter \
  --language zh --title '统计估计' --course-name '统计学'
python scripts/init_latex_project.py --output /absolute/new-book \
  --template /absolute/my-template --main book.tex --engine xelatex
```

输出目录必须不存在。用户模板按原字节复制，保留自己的目录/宏/字体与构建约定；内置英文用 `--language en`。创建回执只证明初始化，不能代替 PDF 构建、视觉检查或教学评估。详见 [LaTeX 规范](references/latex-format.md)。

## 开始使用

Codex 个人安装使用 `${CODEX_HOME:-$HOME/.codex}/skills/textbook-writing`，与其他 agent 的共享目录分开。把仓库完整放入所用 agent 的技能目录，保留 SKILL.md 与 references/scripts 的相对路径。不要只复制入口而丢掉规范和检查工具。

```bash
python -m pip install -r requirements.txt
python scripts/validate_skill_package.py .
python -m unittest discover -s tests -v
python examples/gls/build.py --out /absolute/new/gls-case
```

测试会明确标出未配置的 KaTeX/浏览器项，不把跳过当完成。完整 CI 还安装固定 KaTeX 和 Chromium，并执行真实严格解析及 file:// 双视口验收。依赖安装需要网络授权；教材代码执行需要明确信任。

## 三步改造

| 阶段 | 实现 |
|---|---|
| 修复验收 | 统一公式定界符、公式 ID 清单、代码—输出绑定、未运行状态、被动笔记、组件滚动与字体声明检查 |
| 内容与评审 | 定理—证明—来源—算例—题解关系；修改/来源变动的传递影响；物理移除答案的学习者输入；分开的内容和教学回执 |
| 对照评测 | 冻结 v2.2.0 的实际故障回归；8 类公开行为任务；原版/新版/无技能的隔离输入与日志汇总 |

第三步中，工程对照已可执行并随 CI 重跑；模型行为盲测和真实人类学习实验**没有被本版本虚报为完成**。请查看实际回执，而不是从版本号推断教学质量。

## 版本对比案例

对两次测量 y=(1,3)、噪声方差=(1,4)，逆方差加权结果为 1.4，方差为 0.8；普通平均为 2，方差为 1.25。脚本使用精确有理数生成数值，并复算两段 Python。

正常输出：原版与新版均通过相应执行检查。故意交换这两个算例的展示输出：原版按章节查找字符串，仍通过；新版按 example-id 绑定，报告两个 program_output_mismatch。

这是同一人工故障输入的工程回归，**不是原版/新版模型生成质量 A/B**。优势是可复現地修复已知漏检；代价是更多对象元数据、依赖与审查记录。尚未量化生成成本或人类学习收益。

案例源：`examples/gls/build.py`；生成 reader.html、learner.html、content.json、manifest.json、comparison.json 与两轮回执。独立审稿或学习者回执缺失时，总状态保留 UNVERIFIED/BLOCKED，即使机械部分通过。

## 文档

- [技能入口](SKILL.md)
- [写作与教学要求](references/authoring.md)
- [内容对象、修改影响与独立评审](references/content-and-review.md)
- [发布验收与迁移](references/acceptance.md)
- [评测协议与一手参考](references/evaluation.md)
- [v3.1.0 发布说明](docs/release-v3.1.0.md)
- [v3.0.0 发布说明](docs/release-v3.0.0.md)

## 兼容性与发布

v3.1.0 合并本机原标为 v2.3.0 的 LaTeX 功能与远端 v3.0.0，不回退 HTML 检查。v3.0.0 升级主版本是因为发布批准改用 TextbookReleaseManifest/v2；旧 CLI 保留为局部迁移检查，不能再凭旧 PASS 宣称新版发布验收完成。冻结的 legacy 文件用于基线，不作为新发布入口。

CI 在隔离分支上验证；只有 main 上以 `release:` 开头的提交且所有测试通过，发布作业才创建 VERSION 对应标签与 GitHub Release。不会覆盖已有不同提交的标签，不改仓库保护规则。Release 附源代码包和真实 CI 证据，不附依赖/字体文件。

“技能软件发布通过”“教材机械验收通过”“数学审稿通过”“学习者理解通过”是四件不同的事。
