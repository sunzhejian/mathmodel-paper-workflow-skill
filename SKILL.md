---
name: mathmodel-paper-workflow
description: 从赛题和附件完成可复现建模、求解与数学建模竞赛论文及材料，支持国赛中文、美赛英文及MathorCup大数据预备适配；也可接续现稿核对证据、扩写、修订图表排版、保留附录及验收交付。适用于数模全流程与论文修订。
---

# 数学建模论文与材料工作流

贯通“题目要求—逐问求解—结果证据—正文表达—图表排版—最终交付”。从零任务按题面覆盖全部子问，已有成果从所需阶段接续；两者都保留可复现证据。不要求安装特定上游技能。

## 接手与确定约束

1. 读取项目 `AGENTS.md`，以及存在时的 `.mathmodel/paper/config.json`。模板、队伍档案和入口文件属于用户数据，不覆盖已有配置。姓名、学校等身份信息只进入模板明确要求的非匿名页面；美赛 Team Control Number 作为规则要求的匿名编号按规定显示。**国赛 CUMCM 匿名论文首页保留论文标题，不在标题上方写“题号/题目：A”“参赛队号”等配置字段。**
   新稿或大幅改版且方向不明时，按[首轮选项与模板选择](references/template-selection.md)先让使用者单选主要方向：修订现稿、已有结果写稿、从零到完整论文及相关材料全交付、只审查、只制图或只修排版。选定后再核对缺少的材料与交付范围；赛制和年份未明确时先选择比赛类型，再选必要的排版引擎、论文和图示模板。先读已有决策记录，已明确的小修不重复发问；新决定写回项目报告并验证。
2. 确定最新**用户指定**文件、可编辑源、输出目录及保留区域。用户改过附录的 PDF 可能比 TeX/Word 更权威，不能用旧源重建这部分。
3. 留存原文件及 SHA-256。在授权目录创建修订源，不覆盖其他方案、历史提交或外部聊天附件。
4. 记录简短约束表：页数口径（含不含摘要/声明/文献）、上限还是精确页数、边距、缩进、图片可见宽度、留白口径、文献要求、附录保留方式、交付格式。最新明确指示覆盖旧值。

**后台与论文正文分开。** skill 研发、测试和清单检查默认只读既有论文；日志、哈希、内部路径、制作清单和验收状态写入 `reports/` 或 `qa/`，不生成正文段落或“模型优点”。写作/修订任务中的正文只表达题意、假设、数学方法、结果及必要的科学检验；代码清单、附录和真实 AI 声明按当届赛事规定放置。上游技能与当届官方规则冲突时，在本项目适配层处理，不直接照搬。

**不要固化某篇论文的参数。** 31 页、四边 2.5 cm、首行两字、20% 页尾留白都是一种项目配置，不是竞赛通用标准。只有页数上限时不为凑满页数添加文字；模板与用户要求冲突时说明具体冲突。

## 选择本次需要的步骤

- **美赛 MCM/ICM**：先读[美赛路线](references/mcm-icm.md)，核对年份、英文 Summary Sheet、方案页数口径、题面指定memo/letter、队号页眉与AI报告。新稿优先使用本项目双引擎适配版；已有论文不自动替换。编译后用 `check_mcm_pdf.py` 核对侧文件边界及页眉，再做科学内容与视觉检查。
- **MathorCup 大数据竞赛**：读[大数据赛路线](references/mathorcup-bigdata.md)。单列 `mathorcup-bigdata` 家族，核对年份与初/复赛阶段；当前双引擎模板按2025格式做2026预备适配，盘点与检查报告必须保留规则年份及预备状态。保留官方样表的匿名队号/赛道表格、动态目录与正文起始页码，不能套用国赛首页或美赛页眉。
- **用户需要搭环境、安装编程/排版/绘图工具**：读[工具安装与第一次使用](docs/toolchain.md)，先区分 Git/Python 基础依赖与按路线选择的数值库、TeX/Typst、draw.io、Word 或商业软件；给出官方安装入口和验证命令，不把“安装成功”记为模型已验证。
- **多轮反馈、每问公式或检查失败**：读 [修订细则](references/revision-playbook.md)，按需使用反馈记录与逐问证据模板；遇到具体失败查 [恢复手册](references/failure-recovery.md)。简单修改不强制建完整台账。
- **多技能协作或完整复现**：读 [技能协作](references/skill-orchestration.md) 和 [复现手册](references/reproduction-guide.md)。本仓库的固定上游项目文件位于 [vendor](vendor/README.md)：先运行 `git submodule update --init --recursive`，再用 `python scripts/check_vendor_skills.py` 核对提交及入口。只读取当前阶段所需的本地 `SKILL.md` 和其引用文件；子模块存在不等于技能已执行。需要可运行示例时执行 `python scripts/run_demo.py --output qa/demo`。
- **模型、数值、摘要或措辞**：读 [证据与写作](references/evidence-and-writing.md)。建立每问“输入—假设—方程—算法—输出—验证”对应后写结论。只做排版时不擅自重算或替换模型。
- **清理写作穿帮、润色或处理防御性表达**：读[论文表达](references/paper-voice.md)。保留有依据的强调、科学反驳、适用范围和真实不确定性；清理制作痕迹与重复辩解。按原稿证据修改，不将更强的语气当成更强的结论。
- **图、公式、线稿、分页**：读 [图表与排版](references/figures-and-layout.md)。先修标注和图文顺序，再量化留白；优先编辑矢量源。
- **需要选论文/流程图/科研图模板**：读 [模板选择](references/template-selection.md)，运行 `scripts/template_inventory.py` 列出本机实际存在的候选，按用途向使用者问少量关键问题；已指定模板不强行改。
- **模板选择已答复或项目存在旧记录**：运行 `scripts/validate_template_decisions.py` 检查所选入口和真实数据路径；记录冲突时按用户最新指示修订，不把配置默认值当成用户确认。
- **用户要求论文达到页数下限**：读 [证据驱动扩写](references/longform-paper.md)。先列证据支持的新增论证单元，再编译验证下限与上限；不靠拉行距、重复图表或空泛背景凑页。
- **附录、Word/PDF、支撑包或复现**：读 [编译与交付](references/build-and-delivery.md)。先编译检查正文，最后接回原附录。
- **从零全交付或多个成果一起交付**：按[交付清单](references/build-and-delivery.md#按本次范围检查交付清单)逐项记录实际必需文件和每问代码/结果；用 `scripts/check_project_delivery.py` 查漏，无原附录时也能使用。只改一处文字不强制建全套清单。
- **维护本仓库的上游技能版本**：读 [上游维护](references/upstream-maintenance.md)。先只读比较远端，再审查差异、更新固定提交和入口、运行验证；没有变化时不修改文件。
- **使用者要求多模型试用或迭代本 skill**：读[真实模型行为评测](references/model-trials.md)，用匿名合成任务取得实际产物、独立核对、局部修订并复测。鉴权、响应截断与解题错误分开记录；不自动创建长期调用任务或改写论文。

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
- 对照题面分别核验“正文展示范围”和“电子文件完整范围”：每问的起止时间、采样间隔、空间列、工作表及额外终点记录均满足要求，不能用典型时刻小表替代全过程文件。
- 编译没有未解决引用、缺字、明显越界；重点页原尺寸查看，正文逐页检查。
- 图例、引线、尺寸线和文字互不遮挡；公式及黑框不裁切；标题后有正文。
- 图表就近放在完整段落之后，同一问的结果不被下一问标题隔开。
- 标题、图题、表题和摘要只表达研究对象、方法与结果；制作指令留在后台。重要结果可强调，有依据的反驳与必要限定保留；自动筛查逐条复核，润色前后核对数字、范围和主张强度。
- 国赛匿名首页直接从论文标题开始；编译后查看第一页并运行匿名字段检查，不能把项目配置中的题号、队号行带进正文。
- PDF 与被要求的 Word 分别核验；仅检查 PDF 就只报告 PDF 合格。
- 原附录按约定保留，新增页码连续；源、图和支撑包对应同一最终版本。
- 修改正文或最终 PDF 后重新生成相关检查报告；用 `verify_delivery.py` 拒绝旧报告和变更后的支撑文件。该工具只核对文件与报告一致性，不替代人工内容审查。

交付先给最终文件链接，再报告实际页数、留白口径、附录状态及未完成事项，只写已验证内容。用户继续反馈时从最新授权版本修订，不重新解释整套流程。
