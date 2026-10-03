# 完整赛题材料与实际读取证据

从零建模、完整解题或把项目交给另一 AI 时读取本页。入口材料包括完整原始题面、题内附录、全部授权附件/数据集、每个工作表、原始输出样表和每问交付要求。准备材料、模型实际读取、正确理解与求解完成分别核验。

## 使用者提供文件即可开始

正常项目由使用者提供题面和附件，代理按当前任务自行建立内部材料/要求清单，使用宿主已有工具执行，不要求用户先填写本页 JSON 或设置 MCP。下面的准备器与只读接口是可选助手和专用试用方案。原件留在用户授权项目内；已有 Git 仓库也可以生成新的材料包，原件、项目配置和 Git 文件不改写。真实题面和数据不进入本 skill 分发目录，不自行提交或发布。

小型原题可以完整读取文本和表格。大数据则保留全量可访问原件，模型读取结构、单位、关键语义、质量统计及必要样本，由实际程序处理全量数据并记录行数、过滤依据和输出范围；程序处理全量不能冒称模型逐行阅读。只读接口的“所有CSV行送达”是已执行小型回归的覆盖口径，不是所有用户项目的调用门槛。

## 先确定原始白名单

逐个声明哪些文件是题面、数据、规则补充或输出模板。原始 ZIP 只取明确指定的固定成员；不自动扫描目录挑选题面或答案。题面中的公式、附录参数、边界条件和样例说明保持完整，不用自写概述、摘要、开头几页或截图代替。

独立解题基线使用用户授权的原始资料。旧论文、已填结果、旧求解代码、参考答案、另一模型的结论及评审建议保留在别处；后续确有修订任务时再按该次范围交接，不能混入独立基线。原始结果样表作为 `output-template`，其中的表头、坐标、索引和空位说明填写要求，不能当作已计算的参考答案。

## 材料合同

[`prepare_case_materials.py`](../scripts/prepare_case_materials.py)接受 `--manifest` 与 `--output`。合同只允许已实现字段，题数与必需角色必须显式声明：

| 字段 | 用途 |
| --- | --- |
| `schema_version` / `case_id` | 当前版本为整数1；案例标识采用小写 ASCII 标识符 |
| `expected_question_count` / `questions` | 声明实际题数，并逐问列唯一 `id`、`label`、完整题面中的 `source_pages` 和 `required_roles` |
| `statement` | `id/role/path/label`；主题面 `role=statement` 且必须为 PDF |
| `inputs` | 全部附件与规则补充，各有唯一 `id`、人工声明的 `role`、`path`、`label`；可选 `kind=data/statement-supplement/output-template` |
| `member` / `filename_encoding` | ZIP 的确切成员名；旧编码可显式声明 `cp437/utf-8/gbk/gb18030`，不猜编码或成员 |
| `required_roles` | 非空角色数组，须包含 `statement`；缺任一必需角色即拒绝 |
| `required_source_ids` | 顶层及各问可显式列需要的具体 source id；同角色含多个数据文件时逐项列出，角色存在不替代必需文件完整 |
| `deliverable_requirements` | 每问至少一个要求：唯一 `id`、`question_id`、`description`；可用 `template_id` 绑定原始 XLSX 输出样表的 source id |

`path` 相对合同目录解析，也可显式使用绝对路径。输入角色是使用者声明的语义，不从文件名推断；`role=output-template` 不能重分类成数据。当前输出样表适配器要求 XLSX。四问赛题须列四个问题及其要求；其他赛题按其实际题数声明，不能沿用别题的题数、参数或单位。

下面是四问合同的结构示例，文件名和描述均是占位示例，不能代替用户实际赛题。生产合同必须覆盖实际全部来源与每问的完整要求：

```json
{
  "schema_version": 1,
  "case_id": "anonymous-original-case",
  "expected_question_count": 4,
  "statement": {"id": "statement", "role": "statement", "path": "originals.zip", "member": "problem.pdf", "label": "完整原始题面及题内附录"},
  "inputs": [
    {"id": "measurements", "role": "measurements", "path": "originals.zip", "member": "data/measurements.xlsx", "label": "全部测量数据"},
    {"id": "parameters", "role": "parameters", "path": "originals.zip", "member": "data/parameters.xlsx", "label": "全部外部参数"},
    {"id": "template-1", "role": "output-template", "path": "originals.zip", "member": "templates/result-q1.xlsx", "label": "问题一原始样表"},
    {"id": "template-2", "role": "output-template", "path": "originals.zip", "member": "templates/result-q2.xlsx", "label": "问题二原始样表"},
    {"id": "template-3", "role": "output-template", "path": "originals.zip", "member": "templates/result-q3.xlsx", "label": "问题三原始样表"},
    {"id": "template-4", "role": "output-template", "path": "originals.zip", "member": "templates/result-q4.xlsx", "label": "问题四原始样表"}
  ],
  "required_roles": ["statement", "measurements", "parameters", "output-template"],
  "required_source_ids": ["statement", "measurements", "parameters", "template-1", "template-2", "template-3", "template-4"],
  "questions": [
    {"id": "q1", "label": "问题一", "source_pages": [1], "required_roles": ["statement", "measurements", "parameters"], "required_source_ids": ["statement", "measurements", "parameters", "template-1"]},
    {"id": "q2", "label": "问题二", "source_pages": [2], "required_roles": ["statement", "measurements", "parameters"], "required_source_ids": ["statement", "measurements", "parameters", "template-2"]},
    {"id": "q3", "label": "问题三", "source_pages": [3], "required_roles": ["statement", "measurements", "parameters"], "required_source_ids": ["statement", "measurements", "parameters", "template-3"]},
    {"id": "q4", "label": "问题四", "source_pages": [4], "required_roles": ["statement", "measurements", "parameters"], "required_source_ids": ["statement", "measurements", "parameters", "template-4"]}
  ],
  "deliverable_requirements": [
    {"id": "result-1", "question_id": "q1", "description": "按原题完整填写问题一输出", "template_id": "template-1"},
    {"id": "result-2", "question_id": "q2", "description": "按原题完整填写问题二输出", "template_id": "template-2"},
    {"id": "result-3", "question_id": "q3", "description": "按原题完整填写问题三输出", "template_id": "template-3"},
    {"id": "result-4", "question_id": "q4", "description": "按原题完整填写问题四输出", "template_id": "template-4"}
  ]
}
```

每问可跨多个题面页，来源页按原题填写；不能把示例中的1–4页照抄为真实分页。全部声明的 `output-template` 必须各自绑定到交付要求的 `template_id`，不能只放进目录而遗漏问题映射。规则补充可在 `inputs` 中显式加入 DOC/DOCX 原件与完整 UTF-8 文本，声明 `kind=statement-supplement` 和各自角色。JSON/CSV/图片、其他支持的原始二进制数据同样列入白名单；支持范围以实际脚本和返回的解析说明为准。

## 准备与检查

合同由代理保存在授权项目目录；输出目录须尚不存在，且位于 skill 分发目录之外。用户项目可以使用 Git。研发独立基线另放私有研究目录。以下可选命令从 skill 根目录执行，路径替换为实际授权目录：

```sh
python -X utf8 scripts/prepare_case_materials.py --manifest /path/to/project/source-manifest.json --output /path/to/project/data/packet-new
```

输出包含 `material_contract.json`、`file_manifest.json`、`raw/<source-id>/原文件名`，以及对应的 `pdf/`、`spreadsheets/` 和 `readable/`。核对全部声明的 source id、角色、bytes/hash、题数、来源页、各问要求和所有输出样表均在清单中，不能只确认主 PDF 存在。

- PDF 保留完整原件，逐页提取文本并生成144 DPI PNG，另存有页号边界的完整提取文本。提取顺序、下标、分式和数学符号仍须对照原页；文字稀少、提取失败或缺 PDF 适配器会报告限制。已有页图不会被文字提取失败替代为空白结论，`formula_transcription_status` 始终保留未验证状态。
- XLSX 使用标准库 ZIP/XML读取全部工作表，包括隐藏页；从 A1 按原始维度与实际坐标导出矩形 CSV，不新增表头、不裁掉空位、不计算公式或转换单位。记录 `raw_dimension`、非空行、公式格及原始单元格属性；日期序列与数字词法值保持原样。CSV无法完整表达源类型/格式，单元格 JSON 与原工作簿继续交付。无表达式的共享公式格以 `=` 标记并保留公式属性，不伪造展开结果。
- UTF-8 TXT/MD/CSV 等保留完整可读副本；CSV 值不被分析或重写。其他编码不猜测。DOC/DOCX、图片及未实现解析的数据格式保留原件和哈希，标为 `content_extraction.status=not-covered`；这表示文件已提供、内容解析尚须相应阅读器或人工核查。
- ZIP 拒绝路径穿越、绝对/歧义路径、符号链接、重复/casefold冲突、加密及不合理大小/扩张比例；输出拒绝已有目录及 skill 分发目录。用户 Git 项目内的新输出允许，不自动更改 `.gitignore` 或提交。解析不主动执行脚本、Office 宏或 provider 调用。

`prepared` 的 CLI 退出码为0；`prepared_with_limitations` 为2，表示已保存材料但存在明确解析限制；失败为1。所有成功材料仍有 `review_required=true`，文件存在、哈希一致及角色齐全均不证明题文数学语义完整或求解正确。原始输入身份与角色来自宿主 manifest 声明；`reference_answer_status` 明确保留未自动检验状态，工具不自动识别旧答案或保证文件确属原始空模板。带 DOC 的原件包可能完整而状态仍有限，不能丢弃原 DOC 来把状态改成“通过”。

## 给其他 AI 的只读入口

[`case_materials_server.py`](../scripts/case_materials_server.py)以已准备材料包启动，只读提供材料清单、文本分段、项目参考、题面页图及读取收据：

```sh
python -X utf8 scripts/case_materials_server.py --materials /path/to/research/packet-new --audit-log /path/to/research/model-read-events-new.jsonl
```

`--audit-log` 是可选的新读取日志路径，放在材料包和仓库之外。`--transcript` 则是可选的既有 UTF-8 TXT/Markdown 题面/公式转录输入；只包含忠实来源转录，不夹带参考答案，并与不可变原 PDF/页图分开记录。宿主转录尚须对照原页，不能因文字可读就宣布数学公式已正确转录。

工具名称和参数先通过当前 `tools/list` 发现：`list_case_materials`、`read_material_text`、`read_project_file`、`read_statement_page`、`material_read_receipt`。首轮核对原文件清单和各问要求，按页查看题面与附录；读取所有实际数据工作表、单元格/公式说明和全部输出样表。文本响应标示截断或还有后续范围时继续分段读取，不能把返回的第一页或首160行当成完整文件。页图返回也不证明客户端/模型支持视觉或理解了公式，仍须单列解析与理解缺口。

### 分析阶段的必要规范交接

宿主同时选择本次分析阶段需要的项目规范，不能只把题面、数据或一个上游入口送给模型。实际读取本项目 `SKILL.md`、本页、[逐问证据规则](evidence-and-writing.md)，以及选用的上游分析入口与其引用的共享规范所需章节。MathModelAgent 当前分析入口引用 [`_references/math_modeling_norms.md`](../vendor/MathModelAgent/skills/_references/math_modeling_norms.md)；共享 `_references` 已登记为知识入口，供阶段按需读取。

在分析报告交接代码阶段前，按原题分别记录“正文抽样/展示范围”与“完整电子输出范围”，绑定每问来源、时间/空间范围、间隔、工作表和终点要求。核对方法沿用[已有逐问证据链](evidence-and-writing.md#逐问证据链)，不等到写作才查，也不能让正文展示区间缩短完整文件。

只读服务器支持宿主重复 `--required-project-file` 来冻结必要规范文件。例如分析任务可声明以下文件，其他阶段换成其必要入口及引用，不加载全部技能：

```sh
python -X utf8 scripts/case_materials_server.py --materials /path/to/research/packet-new --audit-log /path/to/research/model-read-events-new.jsonl \
  --required-project-file SKILL.md \
  --required-project-file references/case-materials.md \
  --required-project-file references/evidence-and-writing.md \
  --required-project-file vendor/MathModelAgent/skills/2analysis-modeling/SKILL.md \
  --required-project-file vendor/MathModelAgent/skills/_references/math_modeling_norms.md
```

这是 shell 换行示例；Windows 可将各参数放在同一行。路径相对 skill 根目录，须是实际已允许的项目/上游规范文件。宿主只选择当前阶段必要文件，模型按分页接口完成声明范围；规范名单及其 hash 进入交接/收据。

`all_required_text_supplied` 核对材料文本覆盖，`all_required_project_text_supplied` 独立核对宿主声明的阶段规范覆盖。前者通过不能替代后者；未声明规范名单时，也不能据此认定阶段上下文完整。读取覆盖仍不证明理解或解答，后续要对原题的完整输出口径与实际产物再验收。

用 [`run_opencode_trial.py`](../scripts/run_opencode_trial.py) 接入已授权模型时，启动 JSON 选择该接口。下面按分析阶段声明必要规范，其他阶段换成其实际所需名单：

```json
{
  "name": "case_materials",
  "command": [
    "/path/to/python", "-X", "utf8",
    "/path/to/mathmodel-paper-workflow/scripts/case_materials_server.py",
    "--materials", "/path/to/research/packet-new",
    "--audit-log", "/path/to/research/model-read-events-new.jsonl",
    "--required-project-file", "SKILL.md",
    "--required-project-file", "references/case-materials.md",
    "--required-project-file", "references/evidence-and-writing.md",
    "--required-project-file", "vendor/MathModelAgent/skills/2analysis-modeling/SKILL.md",
    "--required-project-file", "vendor/MathModelAgent/skills/_references/math_modeling_norms.md"
  ]
}
```

```sh
python scripts/run_opencode_trial.py --routes /path/to/private/routes.json --route authorized-route --prompt /path/to/research/read-task.txt --output /path/to/research/model-read-run --project-tools /path/to/research/material-tools.json --effort low
```

这是启动结构示例，路径与路线须替换；配置不含密钥。该运行器每次只选一个白名单接口，其他工具保持 deny；材料模式记录 `mode=case-materials-task` 与 `selected_tool_interface=case_materials`。它让模型读取完整输入，不提供逐问程序写入、任意 shell、求解或论文编译能力。完整解题须另有本次实际可用且被验证的工具链，不能向只读阶段要求“已经求解完毕”。

## 分开报告六类证据

| 证据 | 能说明什么 | 下一步仍须核验 |
| --- | --- | --- |
| 文件清单及原件 bytes/hash | 声明白名单已提供、原件复制一致 | 白名单是否真的覆盖完整题面与全部原始资料 |
| PDF逐页/全部工作表导出 | 适配器对声明来源的覆盖范围 | 公式、单位、类型、附录和原模板含义 |
| 模型读取 range/页图收据 | 对应内容实际返回给该模型，记录截断与缺口 | 模型是否正确理解、是否遗漏条件或输出要求 |
| 宿主声明的阶段规范读取收据 | 本阶段必要项目/上游规则的实际返回范围 | 规范是否被正确应用，交接是否遗漏当前阶段所需引用 |
| 每问程序、运行记录及完整结果 | 模型/宿主实际完成的求解步骤 | 约束、数值精度、完整范围和独立验证 |
| 论文源、实际 PDF/Word及支撑包 | 同版交付产物与相关检查 | 科学结论、引用、逐页视觉及赛事要求 |

材料包准备完成后，再核对接收模型的实际读取记录。未覆盖页、工作表或必需资料单列；DOC 原件保留而未解析也单列。工具调用次数和模型自称“已读完”不构成范围覆盖证据，范围覆盖也不等于理解或解答。

研发试用的真实题面、附件、完整文本、页图、电子表和日志留在私有研究目录；正常调用沿用使用者授权项目。公开 skill 分发内容仅发布通用工具、文档与合成小夹具，不加入用户赛题数据或参赛正文。匿名与身份字段继续遵循项目配置及当届赛事要求。完整模型试用分层见[模型评测](model-trials.md)。
