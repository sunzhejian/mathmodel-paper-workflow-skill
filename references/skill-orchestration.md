# 技能协作：谁负责什么，怎样衔接

本技能是论文迭代与交付的协调层，并不取代建模、求解或专门审查技能。下列清单根据原项目的部署清单、阶段产物、专项审查报告和绘图验证记录整理；**安装、阅读、实际执行是不同状态**。不要求每篇论文运行所有技能。

## 1. 历史来源与证据等级

| 来源 | 当时的用途与证据 | 本仓库的接续方式 |
| --- | --- | --- |
| [MathModelAgent](https://github.com/jihe520/MathModelAgent) | 部署并读取阶段技能；存在分析建模、编程绘图、写作及验收产物。不据此宣称每个辅助技能都独立运行过 | 复用阶段接口；有已有成果时从当前阶段接续 |
| [sci-box](https://github.com/jihe520/sci-box) | 部署图形技能并用于图表/示意图工作；本仓库三张讲解图也使用 scibox-diagram 的版式检查与导出流程 | 数据图与概念线稿分开，保存可编辑源 |
| [BZD](https://github.com/BZDmathclub/bzd-math-modeling-skills) | 部署 16 个独立技能；`bzd-model-assumption-checker` 和 `bzd-model-solution-checker` 有明确专项执行报告 | 优先复核假设、模型与结果，再按需要选摘要/格式等审查 |
| [EditaPlot](https://github.com/hang-jin/editaplot) | 已部署，留有 Origin 尝试记录；指定的三曲线最终由 Python/Matplotlib 生成并逐点核验 | Origin 为可选路径；不能将环境自检通过写成 Origin 结果已验证 |
| `mma-paper` | 原项目本地工作流入口，有配置与论文源；没有已核验的公开上游地址 | 本地可用且项目要求时遵循其入口；否则按本技能接口执行，不虚构下载地址 |
| `mathmodel-paper-workflow` | 从上述实际迭代提炼的本仓库 | 反馈登记、证据约束、版面检查、附录保真与交付 |

历史版本锁定在 [upstream-lock.json](../examples/upstream-lock.json)。它们是当时的版本，**不代表最新版本**。其他软件如 Python、MATLAB、COMSOL、Stata、Origin、draw.io、LaTeX 是工具，不因此被计作独立 skill。安装过 `typst-author` 也不代表最终论文由 Typst 编译。

原流程提到但当时未发现可用入口的 `paper-diagram`、`paper-search`、`nature-figure`，不得写成已调用；分别使用可用的示意图工具、实际检索核验和一致的科研图形样式补足。

MathModelAgent 当时的十个部署入口为 `1start-mathmodel`、`2analysis-modeling`、`3coding-visual`、`4drawio`、`5writing`、`6verity`、`_references`、`doctor`、`mathmodel-figure-templates`、`typst-author`。其中 `_references` 提供共享规范，`doctor` 用于环境核查，`typst-author` 仅在选择 Typst 路线时需要。scibox-diagram 是额外的独立入口，绘图模板的同名问题见第 4 节。

## 2. 阶段接口与停止条件

| 阶段 | 主技能 / 可选审查 | 必需输入 | 必须落盘的输出 | 进入下一阶段的条件 |
| --- | --- | --- | --- | --- |
| 接手 | 本技能；新项目可用 `1start-mathmodel`、`doctor` | 用户最新指示、题面、附件、已有源及配置 | `plan.md`、约束合同、来源清单 | 找到权威文件，确认页数口径和保留区域；已有配置不覆盖 |
| 题意与设计 | `2analysis-modeling`；BZD 题意/思路/假设审查 | 每问要求、数据字段和物理定义 | `reports/ANALYSIS_MODELING_REPORT.md`、逐问证据表 | 每个子问都有输入、未知量、模型、输出和验证计划 |
| 求解与数据图 | `3coding-visual`；`mathmodel-figure-templates` | 已说明的假设、方程、参数和单位 | 每问独立脚本、原精度结果、导出表、数据图、运行日志 | 真实运行成功；表格/图/正文数值能回溯到同一结果 |
| 示意图 | `4drawio` / `scibox-diagram`；项目要求时 TikZ | 已确定的几何、边界、坐标与作用方向 | `.drawio`/`.tex`/`.svg` 源及 PDF/PNG | 可见/遮挡弧线正确，箭头不穿字，标注不压主体 |
| 论文 | `5writing` 或已有 `mma-paper`；本技能 | 验证后的结果、图、模板、真实文献 | 可编辑论文源、编译 PDF；需要时 Word | 每问有对应公式、参数/变量范围、结果和解释 |
| 专项审查 | BZD 假设、模型求解审查；必要时其他 BZD 技能 | 题面 + 代码 + 结果 + 论文，缺一要说明 | 带位置、证据、严重度和建议的报告 | 确定错误修复；不能将数值收敛包装成实验验证 |
| 版面与交付 | `6verity` + 本技能脚本 | 最新编译正文、原附录、白名单 | 逐页预览、检查 JSON、最终 PDF、支撑 ZIP | 人工视觉检查通过；附录比对通过；支撑包回读通过 |

各阶段允许返回前一步：例如边界量定义错误必须回到模型，不以润色掩盖。只有“图例遮挡”时只修改绘图和排版，不重算已验证结果。发现问题记录后继续做不依赖它的工作，不重复询问用户已给出的选择。

## 3. BZD 技能的完整分工

以下均在历史部署清单中，只有上文明确列出的两项可直接表述为有专项执行证据。新项目按需调用，另记运行记录。

| 用途 | 技能名 |
| --- | --- |
| 总体流程与题意 | `bzd-modeling-workflow`、`bzd-problem-translator`、`bzd-modeling-ideas`、`bzd-problem-restatement` |
| 模型审查 | `bzd-model-assumption-checker`、`bzd-model-solution-checker`、`bzd-model-dictionary` |
| 论文专项检查 | `bzd-abstract-checker`、`bzd-problem-analysis-checker`、`bzd-symbol-notation-checker`、`bzd-paper-format-checker`、`bzd-reference-appendix-checker` |
| 综合审阅与披露 | `bzd-review-paper`、`bzd-paper-aigc-auditor`、`bzd-ai-usage-disclosure` |
| 特定背景查询 | `bzd-cumcm-school-awards`，不属于论文定稿的必要步骤 |

“去穿帮”指清理工作记录口吻、模糊指代、未经执行的能力宣称和不对应的证据，**不是隐藏真实 AI 使用情况**。保留按实际参与程度编写的 AI 声明；不承诺绕过检测或获得奖项。不要把综合评分、院校信息采集强加给只要求修排版的任务。

## 4. 安装时以 frontmatter 为准

1. 先列出现有技能的 `SKILL.md` 顶部 `name`，再安装缺少的技能；不要仅比较文件夹名。
2. sci-box 的 `scibox-figure` 目录声明的名称为 `mathmodel-figure-templates`，可能与 MathModelAgent 中已安装的技能重复。保留一个明确来源即可。
3. BZD 在不同分类下可能有同名且内容相同的 `bzd-review-paper`、`bzd-problem-restatement`、`bzd-ai-usage-disclosure`；`bzd-reference-appendix-checker` 也有嵌套副本。安装一个入口，不叠加同名目录。
4. 上游有更新时核对差异、许可证和入口，再决定升级。本仓库不打包、复制或重新许可上游技能。
5. 记录实际执行：`技能名 / 来源提交 / 读取的规则 / 输入哈希 / 产物路径 / 检查结论`。只有部署记录时状态写 `installed`，读过写 `read`，产生了可验证产物后才写 `executed`。

## 5. 可直接使用的协作提示词

**模型审查：**“使用可用的 BZD 假设与模型求解检查技能，对照题面、源代码、原精度结果和当前论文审阅。报告每项问题的位置、证据、影响及最小修复方案；不要虚构实验，不改变已验证结果，不做未要求的排名预测。”

**作图：**“数据图从结果文件读取，不拟合、不补点，除非方法明确要求。示意图使用 scibox-diagram 或项目已有矢量路径，给出源文件、导出命令和预览；实线/虚线表达遮挡关系，尺寸线、文字和主体不得重叠。图注短，分析放正文。”

**写作定稿：**“使用已有写作技能与 mathmodel-paper-workflow。沿用最新约束合同和用户已修改附录。每问按方法—公式—参数—结果—解释组织；摘要突出已验证的方法与数值，关键结论适度黑色加粗，重要模型/终点可用细黑框。编译后逐页复核并交付验收报告。”
