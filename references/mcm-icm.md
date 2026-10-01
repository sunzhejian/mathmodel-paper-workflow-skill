# MCM/ICM 美赛路线

核对日期：2026-10-01。COMAP 当前规则页面面向 **2027 届**；本指南用该届规则核对提交要求，用 **2026 年 A、B、C、F 题**研究任务和论文表达方式。赛前仍须检查官方更新，历史训练采用对应年份题面；不能将下一届规则自动套到历史论文。只在本次任务确属 MCM/ICM 时读取本页，既有国赛项目配置不因此改变。

## 已核对的官方要求

| 项目 | 2027 路线采用的要求 |
| --- | --- |
| 语言与文件 | 英文，正式提交一个 PDF，字体清晰且至少12pt |
| 第一页 | Summary Sheet；不另交独立摘要文件 |
| 方案页数 | 最多25页，包含摘要、目录、文献、附录、代码及题面指定材料 |
| 目录 | 允许且建议；题面另有要求时执行题面要求 |
| 页眉与匿名 | 按要求显示 Team Control Number 和页码；不显示姓名、导师或学校 |
| 正式提交附件 | 不额外提交程序或数据包；本地复现材料可另交给用户 |
| 提交版本 | 文件名使用该队控制号，当前文件大小须小于25MB；结束时点后停止修订 |

来源：[COMAP 2027 Rules and Instructions](https://contest.comap.com/undergraduate/contests/mcm/instructions.html)。方案末页须按实际文档定位，不能默认把总PDF前25页都当作方案；不要套用国赛31页、附录不限、匿名正文无队号的做法。

AI 使用需按真实情况在正文相关位置和参考文献披露，方案后附 `Report on Use of AI Tools`；该报告不计入25页方案上限。记录涵盖实际使用的模型、目的与适用交互，翻译/代码辅助同样不能漏记；引用与内容仍须核实。不能只把国赛简短声明搬到美赛。来源：[COMAP AI Policy，v102025](https://contest.comap.com/undergraduate/contests/mcm/flyer/Contest_AI_Policy.pdf)。普通运行日志和文件清单仍留在后台，必要的AI披露按官方位置保留。

## 核对来源版本，模板文件只作起点

- 官网当前规则明确面向2027届；其 Tips PDF 标记 `V20240912`，其中个别题型标签和文件大小说明与当前网页不同。冲突时采用匹配当届的规则和题面，不把旧 Tips 作为唯一规范。[官方 Tips](https://contest.comap.com/undergraduate/contests/mcm/flyer/MCM-ICM_Tips.pdf)
- 本轮读取的[官方 Summary LaTeX 文件](https://contest.comap.com/undergraduate/contests/mcm/flyer/MCM-ICM_Summary.tex)注释标为2027，页面文字仍有2026。开始新稿时核对实际年份、题号、队号与页序，不能原样保留样例信息。
- 旧模板或通用建议中的“300–500词”、固定篇幅分配和图数量不是已核验的硬性规定。摘要在规定页面内说明实际问题、方法、核心结果和含义；不靠缩小字体或凑满25页完成验收。

## 题面分析要适应开放任务

美赛任务可能有编号、项目符号、连续段落和可选建议。内部任务表逐项区分：**必做任务、嵌套要求、示例/启发、指定交付物**；再按真实模型关系组织章节，不固定套成三问，也不把每个启发性问题都当作必答小问。

| 研读样本 | 对本 skill 的实际启示 |
| --- | --- |
| [2026 MCM A：手机电池](https://contest.comap.com/undergraduate/contests/mcm/contests/2026/problems/2026_MCM_Problem_A.pdf) | 题面明确要求连续时间机理；不能只给黑箱拟合。模型类别、假设、参数依据、耗尽时间与不确定性要对应 |
| [2026 MCM B：月球运输](https://contest.comap.com/undergraduate/contests/mcm/contests/2026/problems/2026_MCM_Problem_B.pdf) | 多情景比较、非理想运行、水需求和环境影响需要有共同模型基础；题面另要求一页 letter，不能遗漏或放在25页之外 |
| [2026 MCM C：投票分析](https://contest.comap.com/undergraduate/contests/mcm/contests/2026/problems/2026_MCM_Problem_C.pdf) | 潜在票数推断需要一致性与确定性说明；要求一至两页 memo。源数据中的未发生、缺失、淘汰后零值不能无差别当作普通零观测 |
| [2026 ICM F：AI与职业教育](https://contest.comap.com/undergraduate/contests/mcm/contests/2026/problems/2026_ICM_Problem_F.pdf) | 明确必需的三类职业与对应建议，同时辨认题面列出的可选思考方向；政策建议应由模型结果支撑，解释推广条件 |

题型选择依据当年题面和队伍能力，不永久把某个字母绑定一种模型。选型先给合理基准模型，说明新增机制/约束解决哪个真实问题；复杂算法、模型名称或图形数量不独立构成创新。

## 英文论文的组织

先建立任务—模型—结果—检验的对应，再写英文稿。可用问题背景、假设与理由、符号、模型设计、求解与结果、科学检验、局限和结论作组织参考，但章节名称和数量随题面调整。模型解释要让评阅者读懂为何采用、如何计算、结果意味着什么。

1. **Summary Sheet 最后完成。** 突出问题、主要模型/算法、关键量化结果及建议；不能只是题目复述、引言复制或软件名列表。报告确定后的结果再校对摘要。
2. **正文直接回答任务。** 提供必要数学定义、推导、参数来源及求解方法；图表围绕比较、预测、机制或验证的具体结论安排。
3. **检验具有对象和量化结果。** 可行性、误差、不确定性、敏感性或稳定性按模型需求选择；正文说明科学结论，详细运行命令、哈希和状态表留在 `reports/qa`。
4. **题目要求的 memo/letter 面向其收件人。** 写结论、建议、依据与限制；与论文模型保持一致，不只是再复制一遍摘要。此类材料计入方案页数。
5. **英文表达优先清楚、简洁。** 保持符号、单位和术语一致；不要用生僻词、夸张形容词或无证据的“显著提升”增加篇幅。中文分析可以留在后台，正式稿依规则用英文。

以上为本 skill 根据所读材料制定的写作方法，不是固定评分公式。官方强调摘要质量、组织清楚和有依据的模型分析，参考其[规则中的写作指导](https://contest.comap.com/undergraduate/contests/mcm/instructions.html)和[官方 Tips](https://contest.comap.com/undergraduate/contests/mcm/flyer/MCM-ICM_Tips.pdf)。

## 本项目维护的双引擎模板

已提供本项目原创的 [LaTeX 模板](../assets/templates/en/mcm-latex/main.tex)和 [Typst 模板](../assets/templates/en/mcm/main.typ)。同一语言/模板id的盘点优先显示本项目适配版，`template_source=project-adaptation`；固定上游文件保留。已有用户论文继续按原源文件修订，不因新版本可用便替换整稿。

两套骨架只有一个Summary Sheet，目录自动生成，页眉使用实际页码及整个PDF总页数，方案和AI报告分别记录边界。年份、控制号、题号、标题及可选目录/附录/AI报告在配置文件中填写。报告边界只输出到侧文件，不渲染为正文内容。主体字号为12pt，LaTeX基础版不要求系统特定字体或 `hyperref`。

从用户选定的赛题项目目录调用skill脚本，新稿写在该项目下的新目录。不要把正式论文、队伍配置或私有结果放在用于公开维护的skill仓库。下面脚本路径须替换为实际安装路径：

```sh
python /path/to/skill/scripts/prepare_mcm_template.py --engine latex --output paper-mcm-new
# Typst 改用 --engine typst，并选择另一个新的目标目录。
```

初始化拒绝覆盖任何既有目录或项目配置。填好 `config.tex`/`config.typ`，替换摘要、任务正文、参考文献和按真实用途启用的AI报告；`REPLACE_` 标记、零控制号与题号X会被验收检查指出。memo/letter按题面写在方案中，模板不生成虚构内容。

LaTeX：先创建 `build/`，从模板目录执行至少两遍并使引用稳定（合成回归使用三遍）：

```sh
xelatex -interaction=nonstopmode -halt-on-error -no-shell-escape -output-directory=build main.tex
xelatex -interaction=nonstopmode -halt-on-error -no-shell-escape -output-directory=build main.tex
```

生成 `build/main.pdf` 与 `build/main.mcm.json`。如本机依赖需要额外处理，先按工具指南定位，不在模板研发中更新系统TeX。基础版已在当前MiKTeX上编译验证。

Typst 0.15+：

```sh
typst compile main.typ build/main.pdf
typst eval 'query(<mcm-boundary>).first().value' --in main.typ > build/main.mcm.json
```

Windows PowerShell 的JSON导出使用明确的UTF-8编码：

```powershell
typst eval 'query(<mcm-boundary>).first().value' --in main.typ | Out-File -LiteralPath build/main.mcm.json -Encoding utf8
```

旧版CLI可用 `typst query main.typ '<mcm-boundary>' --field value --one` 取出同一JSON。测试会检测eval是否可用；本轮验证使用官方Typst 0.15.1便携版。

编译后使用安装的skill脚本路径运行（以下命令中的脚本路径按本机实际位置替换）：

```sh
python /path/to/skill/scripts/check_mcm_pdf.py build/main.pdf --metadata build/main.mcm.json --year 2027 --report build/mcm-check-round-01.json
```

检查器校验摘要页位置/数量、真实方案上限、AI报告起始页、每页队号/页码/总页数及显式占位内容。报告不输出控制号原值，新报告路径不会覆盖输入或旧报告。可单独使用的编译边界不是数学验证；它也不证明实际AI披露、引用、字体、所有图文位置或COMAP最终合规。仍需按源文件、逐页渲染和真实使用记录复核，不能手工改边界JSON把超页方案藏到AI报告中。

## 固定上游版本模板审查结果

研究阶段只读检查了 MathModelAgent 固定版本 `487f3508` 的 `templates/en/mcm-latex/main.tex` 与 `templates/en/mcm/main.typ`。下表说明这些上游文件的问题；本轮编译验证的是上面的本项目适配版，没有修改上游或用户论文。

| 源文件中的实际发现 | 后续适配方式 |
| --- | --- |
| 独立 Title Page 再重复完整摘要 | 正式稿保留一个 Summary Sheet；额外页只在内容确有用途时保留 |
| 手写目录项目和页码，样例固定三问 | 用自动目录与实际章节；按题面任务组织，清除通用预测/优化/集成占位内容 |
| LaTeX `TotalPages=4`；Typst 用物理页数减2 | 总页数与实际编译文档对应；方案页数单独统计，不能隐藏摘要或目录页 |
| 摘要/Title/目录有关闭页眉的设置 | 按当届每页队号和页码要求核对；不套国赛删除队号的处理 |
| 2026年份及样例日期 | 从本次明确的年份和配置赋值；不覆盖既有用户配置 |
| 没有独立 AI Use Report 接入点 | 按真实记录追加报告并明确方案末页；相关正文与文献披露保持一致 |
| 附录默认 Core Code，部分小字号设置 | 只放必要材料，附录和代码计入25页；检查字号和可读性，不缩字规避篇幅 |

模板适配在本项目副本/适配层进行，既有稿件先报告差异。不要直接改固定上游子模块，更不要为了美赛研发修改当前国赛论文。

## 页数检查与交付出口

使用[美赛页数检查示例](../examples/mcm-audit-contract.json)时，先填写真实PDF路径和方案范围。样例以只含方案的PDF检查最多25页；若最终文件已追加AI报告，应使用 `pdf_scope=combined` 并填写**实际方案末页**。边距值只定义该示例的测量区，不是COMAP统一边距；没有用户留白要求时保持阈值为空。

```sh
python scripts/audit_contract.py reports/mcm-audit-contract.json --project-root . --report qa/mcm-round-01/layout.json --render-dir qa/mcm-round-01/pages
```

此命令使用已有工具检查声明范围内的页数与疑似未编译公式；配合上面的 `check_mcm_pdf.py` 检查摘要位置、页眉及编译边界。字号、AI正文引用及语义正确性仍须源文件/视觉核查。

正式提交目录按本次规则准备单一PDF；源码、数据、图源、完整运行日志和本地复现包可另交给用户，但不自动作为COMAP额外附件发送。参考文献应覆盖真正使用的数据、理论、图形与AI工具；“知网中文文献”只在用户明确要求且确实适用时采用，不能继承为美赛默认。比赛结束后的处理遵守当届截止要求；skill维护、对外发布和测试仅操作通用材料或匿名合成夹具。

## 接下来优先开发

1. **基础模板与页数边界已实现：**本项目双引擎骨架、初始化与编译边界检查已通过合成测试；下一步在不同篇幅、图表与真实获授权项目副本中扩展验证，不把骨架通过当成整篇论文质量合格。
2. **任务解析：**支持编号/项目符号/段落，区别必需任务和启发；把memo/letter列为明确交付项。
3. **Summary 与正文一致性：**核对方法、数字、单位、建议和局限；先基于真实结果再写英文，不硬套词数或最低页数。
4. **合成回归：**覆盖26页方案拒绝、AI报告独立计数、漏memo、硬编码目录、三问占位和题号/年份错配；后台报告不进入正文。

模板之后还有模型比较、不确定性与决策稳定性、memo/letter、英文一致性、页数取舍和限时接续等开发包，见[路线图中的后续计划](../docs/roadmap.md#美赛模板之后的开发包)。这些模块按当前任务需要使用，不要求每题套同样模型、图表或检验。
