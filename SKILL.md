---
name: mathmodel-paper-workflow
description: 从赛题和附件完成可复现建模、求解与数学建模竞赛论文及材料，支持国赛中文、美赛英文及MathorCup大数据预备适配；也可接续现稿核对证据、扩写、修订图表排版、保留附录及验收交付。适用于数模全流程与论文修订。
---

# 数学建模论文与材料工作流

贯通“题目要求—逐问求解—结果证据—正文表达—图表排版—最终交付”。从零任务按题面覆盖全部子问，已有成果从所需阶段接续；两者都保留可复现证据。不要求安装特定上游技能。

当前默认采用[参考项目协作](references/upstream-assisted-mode.md)：按阶段实际读取 MathModelAgent 与适用的 BZD、sci-box、EditaPlot、Sivia 参考，落实到本题方法和产物，并在后台留下采用记录。使用者只调用本入口，不必另外启动多个 skill；未知来源或仅提项目名字不记为使用。必读文件缺失时报告并补齐，不能静默只用自有指导，也不能自称成熟后自动切换自主模式。专用软件是否执行与方法是否借鉴分别记录。

## 在使用者项目中调用

本入口面向不同模型、IDE 与代理环境，按宿主已有的文件读写、程序运行、绘图、文档编译和预览能力执行，不要求使用者采用本项目的模型账户、编程客户端或 MCP。使用者在当前项目提供题面和附件即可开始；内部材料清单、逐问要求和阶段记录由代理建立，不先要求使用者编写 JSON、工具启动配置或准备测试目录。

用户给出完整赛题并要求完整成果时，直接从读题贯通求解、制图、论文和相关材料；已明确的局部任务按其范围执行。复用现有项目的软件、模板和目录，只有影响结果的未定项才询问。仓库中的 Python 脚本是可选的确定性助手；上游文件按当前阶段读取，专用模型试验接口用于开发验收，不限制宿主已有的求解工具。

原题、数据与输出留在使用者授权的项目目录，用户项目可以使用 Git；不把用户资料复制进本 skill 的分发目录，也不自动提交或发布。大数据保留完整可访问原件，由实际程序处理全量数据；模型读取字段、单位、关键条件、质量统计及必要样本，不要求把每行数据塞入上下文。记录模型理解范围和程序处理范围，不能相互冒充。

优先使用当前可用的等价工具：例如已有 Python/MATLAB/R 完成数值计算，已有 LaTeX/Typst/Word 完成相应文档路线。先验证所选路线需要的能力，缺项时补最小可行步骤；实际没有执行或编译的产物保持待验证状态，不用计划代替运行结果。支持目标与已实测的后端、模型、系统范围分别报告。

## 接手与确定约束

1. 读取项目 `AGENTS.md`，以及存在时的 `.mathmodel/paper/config.json`。模板、队伍档案和入口文件属于用户数据，不覆盖已有配置。姓名、学校等身份信息只进入模板明确要求的非匿名页面；美赛 Team Control Number 作为规则要求的匿名编号按规定显示。**国赛 CUMCM 匿名论文首页保留论文标题，不在标题上方写“题号/题目：A”“参赛队号”等配置字段。**
   新稿或大幅改版且方向不明时，按[首轮选项与模板选择](references/template-selection.md)先让使用者单选主要方向：修订现稿、已有结果写稿、从零到完整论文及相关材料全交付、只审查、只制图或只修排版。选定后再核对缺少的材料与交付范围；赛制和年份未明确时先选择比赛类型，再选必要的排版引擎、论文和图示模板。先读已有决策记录，已明确的小修不重复发问；新决定写回项目报告并验证。
2. 确定最新**用户指定**文件、可编辑源、输出目录及保留区域。用户改过附录的 PDF 可能比 TeX/Word 更权威，不能用旧源重建这部分。
3. 留存原文件及 SHA-256。在授权目录创建修订源，不覆盖其他方案、历史提交或外部聊天附件。
4. 记录简短约束表：页数口径（含不含摘要/声明/文献）、上限还是精确页数、边距、缩进、图片可见宽度、留白口径、文献要求、附录保留方式、交付格式。最新明确指示覆盖旧值。

从零任务或交给另一 AI 的独立试用，先按[完整材料交接](references/case-materials.md)核对完整题面、题内附录、全部附件/工作表、原始输出样表和逐问要求映射。用明确白名单保留使用者提供的原件；研发独立基线放在私有研究目录，普通项目沿用使用者目录。独立基线不包含旧论文、已填结果或参考答案。材料可访问、必要语义实际读取、程序全量处理、模型正确理解与求解完成分别记录；原 DOC 保留但未解析仍需说明。补充材料、图片和公式不能被题意概述替代，工具不支持读取或求解时明示当前可完成的阶段。

**后台与论文正文分开。** skill 研发、测试和清单检查默认只读既有论文；日志、哈希、内部路径、制作清单和验收状态写入 `reports/` 或 `qa/`，不生成正文段落或“模型优点”。写作/修订任务中的正文只表达题意、假设、数学方法、结果及必要的科学检验；代码清单、附录和真实 AI 声明按当届赛事规定放置。上游技能与当届官方规则冲突时，在本项目适配层处理，不直接照搬。

**不要固化某篇论文的参数。** 31 页、四边 2.5 cm、首行两字、20% 页尾留白都是一种项目配置，不是竞赛通用标准。只有页数上限时不为凑满页数添加文字；模板与用户要求冲突时说明具体冲突。

## 发现能力并接续当前阶段

先确定本轮是题意/建模、求解、作图、写作还是验收，只读取下面对应路由的参考及实际所用上游 `SKILL.md`。保留输入文件、允许修改范围、预期输出与进入下一阶段的条件；阶段交付只写该阶段要求的文件，不能用提前生成的摘要或论文掩盖尚未通过的求解。

盘点当前可用的文件读取/编辑、求解运行、图件导出、排版编译、PDF 检查与预览能力。读取配置和工具返回的实际路径、版本、字体 family 与格式支持；已安装、已阅读、已调用、已验收分别记录。缺少特定 MCP 时用本机已验证的等价工具；没有执行能力的会话只交付文本或待执行源，并明确未执行范围。工具名称和接口以当前发现结果为准，不模拟调用，也不把上游文件存在当成已运行。

运行前核对宿主实际登记、发布、文件列表、下载与打包的输出范围。`result/`、`results_full/`、`code/outputs/` 等都是可能的项目目录，不为统一命名改动用户原件或旧论文。按[产物发布与回读](references/build-and-delivery.md#产物发布与回读)登记本问实际交付路径；运行后从用户可见列表及下载文件或支撑包回读同版字节/哈希。退出0、`published=true` 或有报告，不证明全部结果已发布；文件仅在候选快照时保留候选状态并定位范围缺口，不能称已交付。

**分析阶段交接先补齐实际上下文。** 进入题意/建模阶段时，实际读取本项目[完整材料规则](references/case-materials.md)、[逐问证据规则](references/evidence-and-writing.md)，再读取选用的上游 `2analysis-modeling/SKILL.md` 及其引用的共享规范所需章节；MathModelAgent 的对应文件为 `vendor/MathModelAgent/skills/_references/math_modeling_norms.md`。已登记的 `_references` 是按阶段读取的知识入口，不是独立执行阶段。宿主将本次必要规范文件列入交接/读取名单，分开检查材料覆盖与项目规范覆盖，不以材料已读完替代规范已送达。

在分析报告交给代码阶段前，依据原题将每问事实分为“正文抽样/展示范围”和“完整电子输出范围”，明确各自时间/空间边界、采样间隔、工作表与终点记录，并绑定原始要求/样表来源；按[既有证据规则](references/evidence-and-writing.md#逐问证据链)核对。展示区间不能缩短完整文件，不能等到写作阶段再补查。交接包含本阶段允许产物、输入/规范来源、实现口径与尚未明确的条件，缺必要上下文时先补读再定模型。

数值求解或题面给出结果样表时，进入编程前读取[数值与结果合同](references/numerical-result-contract.md)。核对原式与实际离散系数、坐标抽样/单位、全量时间输出、未舍入终点状态及文件名大小写冲突；支持图像的宿主须实际查看关键公式原页和最终图件/PDF，文字抽取或文件存在不能记为看过。可用独立工作簿检查器复核声明的输出合同，机械通过与科学正确分开。

新稿在选定模板后、批量写作前，先用模板的字体和一张真实图件完成短页编译与查看；字体职责、SVG 兼容与最终 PDF 核验按[渲染合同](references/rendering-contract.md)。这一小步用于发现引擎/字体/导入问题，不能替代完整稿的逐页检查。

CTeX 字体适配先检查去除普通注释后的实际 `\documentclass` 参数，不能用第一次字符串替换把注释改了就记为完成。新模板的 Windows/macOS/Linux 策略、明确自选字体及宏配置按[CTeX 声明检查](references/rendering-contract.md#ctex-声明检查与平台适配)处理；复查改后声明、实际编译日志与 PDF 字体，平台策略不等于当届官方规范。

模板选择必须落实到实际入口文件及摘要/正文宏：新稿复用已选择且存在的完整模板，不另造主文件绕过摘要分页、目录或页码规则；已有稿在其源上修订，不覆盖。按[模板选择](references/template-selection.md#将模板选择落实到结构合同)记录结构要求的用户/赛制/模板来源，编译后检查真实 PDF。摘要是否独页、占几页按当前合同；通用“中国赛摘要一般不超过两页”不能覆盖已选 CUMCM 模板的摘要后换页或用户明确的一页要求。

失败反馈写明位置、证据、影响与负责的源：日号或训练/验证/测试范围错回求解，关系错回模型/图源，字体错回模板与字体配置，黑块/丢字回导出与嵌入，分页错回排版。修最早出错处，重跑受影响步骤和检查后再交接。科学适用条件保留在正文；制作状态、诊断和试用成绩留在 `reports/` 或 `qa/`。实测项目工具与纯文本试用的区别见[模型评测](references/model-trials.md)。

## 选择本次需要的步骤

- **美赛 MCM/ICM**：先读[美赛路线](references/mcm-icm.md)，核对年份、英文 Summary Sheet、方案页数口径、题面指定memo/letter、队号页眉与AI报告。新稿优先使用本项目双引擎适配版；已有论文不自动替换。编译后用 `check_mcm_pdf.py` 核对侧文件边界及页眉，再做科学内容与视觉检查。
- **MathorCup 大数据竞赛**：读[大数据赛路线](references/mathorcup-bigdata.md)。单列 `mathorcup-bigdata` 家族，核对年份与初/复赛阶段；当前双引擎模板按2025格式做2026预备适配，盘点与检查报告必须保留规则年份及预备状态。保留官方样表的匿名队号/赛道表格、动态目录与正文起始页码，不能套用国赛首页或美赛页眉。
- **用户需要搭环境、安装编程/排版/绘图工具**：读[工具安装与第一次使用](docs/toolchain.md)，先区分 Git/Python 基础依赖与按路线选择的数值库、TeX/Typst、draw.io、Word 或商业软件；给出官方安装入口和验证命令，不把“安装成功”记为模型已验证。
- **完整赛题、数据准备或交给其他 AI 独立解题**：读[材料合同与读取证据](references/case-materials.md)。逐页/逐附件/逐工作表查漏，原始结果样表标为 `output-template`；可用 `prepare_case_materials.py` 或宿主已有的读取/分析工具，核对覆盖和处理范围。专用只读材料 MCP 仅在该试用路线中使用；普通项目继续通过宿主实际工具执行求解和交付。
- **扫描资料、无法读取的旧表或 OCR 返回格式不符**：按[材料转写规则](references/case-materials.md#扫描资料与旧工作簿)核对真正可读内容。页码标记、空白表头和文件存在不算数据；可用 `extract_scanned_pdf.py` 保留原页、原文、识别框与分数。识别文字仍须核对数值和表格结构；现代 OCR 属性结果不能照旧元组拆包，打不开的加密工作簿不猜密码。
- **多轮反馈、每问公式或检查失败**：读 [修订细则](references/revision-playbook.md)，按需使用反馈记录与逐问证据模板；遇到具体失败查 [恢复手册](references/failure-recovery.md)。简单修改不强制建完整台账。
- **多技能协作或完整复现**：读[默认协作与采用记录](references/upstream-assisted-mode.md)、[技能协作](references/skill-orchestration.md)及按需的[复现手册](references/reproduction-guide.md)。实际读取本阶段所需的 `SKILL.md` 和其引用，落实方法；文件存在不等于已经执行。源码维护时，[vendor](vendor/README.md) 缺失子模块可用 `git submodule update --init --recursive` 初始化，并由 `check_vendor_skills.py` 核版本；普通使用者无需配置这条研发命令。必读来源缺失时报告并补齐，不能静默降为纯自有流程。仓库演示另用 `run_demo.py`，不代替用户赛题。
- **模型、数值、摘要或措辞**：读 [证据与写作](references/evidence-and-writing.md)。建立每问“输入—假设—方程—算法—输出—验证”对应后写结论。只做排版时不擅自重算或替换模型。
- **清理写作穿帮、润色或处理防御性表达**：读[论文表达](references/paper-voice.md)。保留有依据的强调、科学反驳、适用范围和真实不确定性；清理制作痕迹与重复辩解。按原稿证据修改，不将更强的语气当成更强的结论。
- **图、公式、线稿、分页**：读 [图表与排版](references/figures-and-layout.md)。先修标注和图文顺序，再量化留白；优先编辑矢量源。
- **字体不符、图件变黑/丢字或跨引擎导入**：读[渲染合同](references/rendering-contract.md)。核对所选字体、PDF实际嵌入与SVG能力；先适配导出格式，再检查真正交付的PDF，不用编译成功代替显示正确。
- **数据分析、求解结果图或用户希望多用高级图**：读[主动科研绘图](references/advanced-figures.md)。在数据图属于本次范围时主动按逐问结论与真实输入选图，读取并调用可用的 `mathmodel-figure-templates`；已接通20类CSV入口，涵盖趋势、分布、矩阵、模型评价与优化分析。给定区间说明含义，Pareto确认目标方向，模型比较核对同样本与划分；先确认数据和统计证据，不能用模拟模板或写死指标充当正式结果，也不为填页增加图。
- **算法流程、反馈、数据划分或并行模块汇流**：用 `render_flowchart.py` 的显式语义合同或所选 sci-box 版式，参考[4份匿名合同](examples/flowcharts)。明确输入/输出、判断条件、各分支标签与回路通道；拒绝碰撞/不可读字号后仍须查看真正导出和嵌入稿，不宣称自动科学布局或算法已经执行。
- **科研机制图、模型总览或复杂可编辑图件**：读[科研机制图](references/scientific-mechanisms.md)，按需读取固定 Sivia 的设计/审阅入口，并沿用实际可用的矢量后端；模型关系绑定来源，实际图源与最新导出分别核对，关键条件和标签不能被装饰遮挡。
- **需要选论文/流程图/科研图模板**：读 [模板选择](references/template-selection.md)，运行 `scripts/template_inventory.py` 列出本机实际存在的候选，按用途向使用者问少量关键问题；已指定模板不强行改。
- **模板选择已答复或项目存在旧记录**：运行 `scripts/validate_template_decisions.py` 检查所选入口和真实数据路径；记录冲突时按用户最新指示修订，不把配置默认值当成用户确认。
- **用户要求论文达到页数下限**：读 [证据驱动扩写](references/longform-paper.md)。先列证据支持的新增论证单元，再编译验证下限与上限；不靠拉行距、重复图表或空泛背景凑页。
- **附录、Word/PDF、支撑包或复现**：读 [编译与交付](references/build-and-delivery.md)。先编译检查正文，最后接回原附录。
- **从零全交付或多个成果一起交付**：按[交付清单](references/build-and-delivery.md#按本次范围检查交付清单)逐项记录实际必需文件和每问代码/结果；用 `scripts/check_project_delivery.py` 查漏，无原附录时也能使用。只改一处文字不强制建全套清单。
- **维护本仓库的上游技能版本**：读 [上游维护](references/upstream-maintenance.md)。先只读比较远端，再审查差异、更新固定提交和入口、运行验证；没有变化时不修改文件。
- **使用者要求多模型试用或迭代本 skill**：读[真实模型行为评测](references/model-trials.md)，用匿名合成任务取得实际产物、独立核对、局部修订并复测。鉴权、响应截断与解题错误分开记录；不自动创建长期调用任务或改写论文。

请求完整长稿实例时，按用户页数口径交付论文、可编辑源、逐问代码、实际数据/结果、图源与支撑包；模型生成、宿主执行、审阅修复分别记录。例如用户选择“20 页以上及全部支撑材料”，只写入该次实例合同，不成为所有赛制的默认门槛。不能把模型片段、失败会话、宿主补稿或脚本测试通过称为模型已独立完成实例。新版自有内容仅允许非商业使用，范围与历史/第三方例外见 LICENSE 和 NOTICE。

## 可重复的检查工具

需要时安装本技能根目录 `requirements.txt` 的依赖。`python` 指当前环境可用的 Python，不写死盘符。

```sh
# 按项目合同检查；合同示例须先替换成该项目的真实路径和约束。
python scripts/audit_contract.py project-contract.json --project-root project --report qa/round-01/layout.json --render-dir qa/round-01/pages

# 只审核正文范围；示例参数按项目替换，页号从 1 开始。
python scripts/pdf_workflow.py audit paper.pdf --last-page 31 --margins-cm 2.5 2.5 2.5 2.5 --blank-limit 20 --report qa/layout.json --render-dir qa/pages

# 国赛匿名正文额外检查首页字段；有项目配置时，还检查队号是否进入正文。报告不输出队号原值。
python scripts/pdf_workflow.py audit body.pdf --cumcm-anonymous --project-config .mathmodel/paper/config.json --report qa/anonymous.json

# 对仅含正文部分的 PDF 校验页数上限；确切要求才用 --exact-pages。
python scripts/pdf_workflow.py audit body.pdf --max-pages 31 --report qa/body.json

# 同时校验下限与上限；例如“20 页以上且不超过 31 页”。
python scripts/pdf_workflow.py audit body.pdf --min-pages 21 --max-pages 31 --report qa/body-range.json

# 接回原 PDF 第 30 页起的附录；默认完全保留，不改页码。
python scripts/pdf_workflow.py append body.pdf original.pdf final.pdf --appendix-start 30 --report qa/appendix.json

# 已授权补页码且页脚空白时增加：
# --number-pages --footer-height-pt 42 --footer-baseline-from-bottom-pt 25

# 根据白名单打包，生成 SHA-256 清单。
python scripts/package_support.py support-root support-files.json support.zip

# 交付前核对正文、原附录、最终 PDF、检查报告和支撑包是否来自同一版。
python scripts/verify_delivery.py body.pdf original.pdf final.pdf qa/layout.json qa/appendix.json --support-zip support.zip --support-root support-root --report qa/delivery.json

# 筛查制作痕迹并单列人工复核候选；不把正常强调或科学限定当禁词。
python -X utf8 scripts/check_paper_voice.py paper/main.tex paper/sections --json

# 检查本次必需文件及每问代码/结果；原附录可不存在。先按实际范围改清单。
python scripts/check_project_delivery.py reports/project-delivery.json --project-root . --report qa/round-01/inventory.json

# 美赛新稿模板；目标须位于用户赛题项目且尚不存在。示例路径按项目替换。
python scripts/prepare_mcm_template.py --engine latex --output paper-mcm-new

# 美赛实际编译PDF与模板导出的边界侧文件；检查报告不会改写正文。
python scripts/check_mcm_pdf.py paper-mcm-new/build/main.pdf --metadata paper-mcm-new/build/main.mcm.json --year 2027 --report qa/mcm-round-01/check.json

# MathorCup 大数据赛预备模板；2026正式格式尚须核对，不能将预备版称为官方模板。
python -X utf8 scripts/template_inventory.py --project-root project --category paper --family mathorcup-bigdata
python -X utf8 scripts/prepare_mathorcup_bigdata_template.py --engine latex --output paper-bigdata-new
python -X utf8 scripts/check_mathorcup_bigdata_pdf.py paper-bigdata-new/build/main.pdf --metadata paper-bigdata-new/build/main.bigdata.json --year 2026 --report qa/bigdata-round-01/check.json
```

`audit` 测量版心内整行宽度连续无内容的竖向区间，报告页尾及最大空白带。**不是总白色像素比例，也不能自动证明没有文字重叠。** 它跳过范围外附录，检测疑似未编译公式，输出逐页预览。超标退出码 1，输入错误 2；未提供留白限制时只报告，不发明门槛。

`audit_contract.py` 读取合同的 `audit`、页数、边距与留白字段；其余字段供代理执行，不代表已自动核验。合并 PDF 必须指定正文末页，报告和预览采用新路径；`--dry-run` 仅打印参数。详细字段和命令见 [复现手册](references/reproduction-guide.md#8-让合同直接驱动检查)。

`append` 复核每页原附录的渲染和文字；加页码前检查页脚文字与图形为空，之后验证页脚外一致。已有页码、扫描污点、旋转页或不合适区域会停止，不用白块覆盖。数字签名等 PDF 级元数据不属于视觉保真保证。

`check_project_delivery.py` 的 `inventory_complete` 只表示声明的非空文件完整、保留源哈希一致；它不执行运行命令，也不证明文件内容、模型或格式合格。输出清单由用户实际要求决定，不能把可选 Word/商业软件变成强制项。

`check_paper_voice.py` 报告制作指令/助手自述候选和需判断的内部记录引用，均不自动改文。`review_required=true` 须人工复核；`passed` 仅表示未命中高确定性规则。代码、注释和按约定排除的附录不作为正文语气判断；范围选择与退出码见[论文表达](references/paper-voice.md#自动筛查的用法与边界)。

## 每轮完成标准

- 变更对应用户反馈；新增分析有数据或推导支持，不以套话填页。
- 数值和结果表可追溯，显示与计算精度分开；不冒充实测或未经运行的验证。
- 从零交付或外部模型试用已提供完整原始题面、附件/工作表、输出样表及每问要求；逐项区分材料准备、实际读取覆盖、含义核对和求解证据。不能以文件存在或读取收据替代完整题意理解。
- 对照题面分别核验“正文展示范围”和“电子文件完整范围”：每问的起止时间、采样间隔、空间列、工作表及额外终点记录均满足要求，不能用典型时刻小表替代全过程文件。
- 编译没有未解决引用、缺字、明显越界；重点页原尺寸查看，正文逐页检查。
- 公式保持完整数学关系：Typst行内用`$x_t$`，独立公式才用首尾空白的`$ ... $`；不把关系拆成编号单变量，不把等号/min/运算符留在正文，不将数据字段和程序标识符按下划线批量转为数学。默认运行`check_formula_integrity.py`或宿主等价结构检查；命中严重碎裂必须回修后重验，待复核项明确查看。该项通过不代表数学推导正确，编译成功也不替代该项。
- 默认协作的本阶段参考有实际读取、具体方法与本题采用位置；不凭名字、文件存在或工具次数声明已经使用，不将采用日志写入正文。
- 原始数据来源、可读文本/OCR和核验后的科学输入分开。扫描资料的转写完成不计为数值已核验；源清单按文件与工作表分别计数，表头、地区标签和跨年口径实际核对。客户端文字中的工具调用标签不计为运行，只有真实执行记录参与验收。
- 图例、引线、尺寸线和文字互不遮挡；公式及黑框不裁切；标题后有正文。
- 图表就近放在完整段落之后，同一问的结果不被下一问标题隔开。
- 标题、图题、表题和摘要只表达研究对象、方法与结果；制作指令留在后台。重要结果可强调，有依据的反驳与必要限定保留；自动筛查逐条复核，润色前后核对数字、范围和主张强度。
- 国赛匿名首页直接从论文标题开始；编译后查看第一页并运行匿名字段检查，不能把项目配置中的题号、队号行带进正文。
- 对照结构合同检查实际 PDF 的摘要页范围、正文起始、目录和页码；摘要要求独页时，该页不能出现正文标题或段落，摘要溢出时回到摘要内容与模板排版修订。
- PDF 与被要求的 Word 分别核验；仅检查 PDF 就只报告 PDF 合格。
- 对照运行中实际产生的文件逐项核对宿主登记、用户可见列表和下载/归档回读；候选快照中存在的文件不冒充已发布文件，不为目录规范覆盖原件或旧论文。
- 原附录按约定保留，新增页码连续；源、图和支撑包对应同一最终版本。
- 修改正文或最终 PDF 后重新生成相关检查报告；用 `verify_delivery.py` 拒绝旧报告和变更后的支撑文件。该工具只核对文件与报告一致性，不替代人工内容审查。

交付先给最终文件链接，再报告实际页数、留白口径、附录状态及未完成事项，只写已验证内容。用户继续反馈时从最新授权版本修订，不重新解释整套流程。
