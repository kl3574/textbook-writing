# 技能评测协议：不把软件测试当学习实验

## 三种不同证据

1. **确定性工程回归**：同一正常/故障注入 HTML，运行冻结 v2.2.0 检查器和新检查器。结果回答已知缺陷是否被拦截，不测模型生成质量。
2. **模型行为对照**：同模型/任务/工具/数据/预算，原版、新版、无技能三条件，全新独立会话，多次重复。回答实际生成是否改善和成本如何变化。
3. **真实学习效果**：独立人类读者的理解、迁移、延迟测试；模型读者成绩不能直接代替。

本版本提供第一种的实际可复现实验和第二种的评测工具。没有运行回执时，第二种与第三种均是 NOT_RUN；不得声称新版提高了正确率或节省了 token。

## 工程案例

`python examples/gls/build.py --out /absolute/new/output-directory`

脚本校验冻结原文件的 Git blob SHA，构造正常和故意交换输出的同一 GLS 例子，实际运行新旧检查。不得把故障注入页称为“原版模型生成结果”。随后生成小型读者页、无答案输入、内容注册表、清单与两轮发布回执。

本地没有 KaTeX 或不能 file:// 导航时，如实保留 UNVERIFIED/BLOCKED。CI 必须提供真实 KaTeX 和 Chromium，并要求 mechanical_status=PASS；即便如此，没有独立审稿/学习者回执时，总状态仍为 UNVERIFIED。

## 行为对照准备与汇总

```bash
python scripts/behavior_eval.py prepare --cases evals/behavior_cases.json \
  --old /absolute/frozen-v2.2.0 --new /absolute/current-skill \
  --out /absolute/new-eval-workspace
python scripts/behavior_eval.py collect --workspace /absolute/new-eval-workspace
```

prepare 生成每题三个独立目录和随机标签，映射在 private/mapping.json，勿交给评卷者。每个运行需新会话，只读取该目录，使用相同检索来源快照与工具策略；禁止访问别的条件、作者讨论和评分答案。公开题是开发集，另由未参与改写者准备真正留出变体；不得把仓库公开题宣称为盲留出题。

此工具不启动任何外部模型或付费 API；实际运行由已获授权的 agent/人工通道完成。各目录 receipt.json 使用 `TextbookBehaviorRun/v1`，保存 prompt_sha256、session_id、model、tool_policy_hash、budget、source_snapshot_hash、status、outputs 与 logs（每项 path/sha256），tokens/duration_ms 可为 null。source_snapshot_hash 指共同知识来源/输入数据，不是各不相同的技能快照。

collect 会检查产物/日志摘要、会话身份和可比性；没有记录显示 NOT_RUN，不记零成本或零错误。回执是证据记录，不是加密身份认证；判卷结论仍须人工/独立审稿校准。最终盲评使用去除版本标签的产物，保留原件与变换记录。

## 判据

关键数学错误、定理条件不成立、关键来源不支持结论、题解错配属于阻断项；不能与排版高分平均抵消。分别报告数学、来源、符号、可复算性、迁移表现、可访问性与成本，保留失败样例。使用同题不同数值的迁移变体，但避免作者提前见到答案；无教材基线用于区分已有模型知识和教材贡献。

## 对照来源（2026-09-07 核查）

- Agent Skills: Evaluating skill output quality — https://agentskills.io/skill-creation/evaluating-skills
- MyST: Exercises and Solutions — https://mystmd.org/guide/exercises
- MyST: Proofs and Theorems — https://mystmd.org/guide/proofs-and-theorems
- Quarto: Managing Execution — https://quarto.org/docs/projects/code-execution.html
- KaTeX: Options — https://katex.org/docs/options.html
- MDN: FontFaceSet.check — https://developer.mozilla.org/en-US/docs/Web/API/FontFaceSet/check

借鉴的是对照设计、稳定对象引用、代码与结果联动、API 的真实含义；没有运行这些竞品的完整教材生成流程，不据此给竞品或本技能编造质量排名。
